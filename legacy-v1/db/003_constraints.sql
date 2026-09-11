-- =============================================================================
-- URace AI Sales Agent — 003: constraints, vector dimension, channel domain
--
-- Apply after 001_schema.sql and 002_seed_config.sql.
-- Assumes leads.close_reason / leads.closed_at already exist (added separately).
-- =============================================================================


-- =============================================================================
-- 1. CHANNEL VOCABULARY — one definition, not two copies
-- =============================================================================
--
-- leads.primary_channel had a CHECK and contacts.channel did not: the same
-- vocabulary written twice with different rigour. Adding a second CHECK would
-- repeat the mistake that produced the tool-list drift, the judge verdict
-- mismatch, and the close_lead enum with nowhere to land. A DOMAIN gives the
-- vocabulary one definition that both columns point at.
--
-- Adding a channel now means altering the domain once — both columns follow.

CREATE DOMAIN channel_type AS TEXT
    CHECK (VALUE IN ('whatsapp','instagram','tiktok','messenger',
                     'email','web_form','other'));

COMMENT ON DOMAIN channel_type IS
  'Channels connected through Kommo. Single source of truth for the vocabulary — '
  'do not re-declare it as a CHECK anywhere else.';

ALTER TABLE leads
    DROP CONSTRAINT IF EXISTS leads_primary_channel_check;
ALTER TABLE leads
    ALTER COLUMN primary_channel TYPE channel_type;

ALTER TABLE contacts
    ALTER COLUMN channel TYPE channel_type;

ALTER TABLE conversations
    ALTER COLUMN channel TYPE channel_type;


-- =============================================================================
-- 2. CHILD-SAFETY GATE — enforced, not documented
-- =============================================================================
--
-- The comment in 001 said a pending approval "must block a booking from being
-- created" and nothing enforced it. That is the one invariant in this system
-- that should not depend on the model behaving, on the prompt being right, or
-- on the orchestrator calling things in the correct order.
--
-- Two layers:
--   (a) a CHECK: an appointment in pending_human_approval must point at one;
--   (b) a trigger: no booking may reach scheduled/confirmed while the lead's
--       most recent age approval is anything other than 'approved'.

-- (a) --------------------------------------------------------------------------
ALTER TABLE appointments
    ADD CONSTRAINT pending_requires_approval
    CHECK (status <> 'pending_human_approval' OR approval_id IS NOT NULL);

-- (b) --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION block_booking_without_age_clearance()
RETURNS TRIGGER AS $$
DECLARE
    latest_status TEXT;
BEGIN
    IF NEW.status NOT IN ('scheduled','confirmed') THEN
        RETURN NEW;
    END IF;

    -- Only the age gate blocks a booking. An out-of-hours request concerns one
    -- specific slot, and a kart inspection does not bear on whether a child may
    -- be on track at all — neither should freeze unrelated bookings.
    SELECT status INTO latest_status
    FROM human_approvals
    WHERE lead_id = NEW.lead_id
      AND reason  = 'age_below_track_minimum'
    ORDER BY requested_at DESC
    LIMIT 1;

    -- No approval was ever needed for this lead: nothing to check.
    IF latest_status IS NULL THEN
        RETURN NEW;
    END IF;

    -- Covers 'pending' and 'rejected'. A later approval supersedes an earlier
    -- rejection, because ORDER BY takes the most recent request.
    IF latest_status <> 'approved' THEN
        RAISE EXCEPTION
            'Booking blocked: driver age clearance for lead % is %, not approved.',
            NEW.lead_id, latest_status
            USING ERRCODE = 'check_violation',
                  HINT = 'A human must clear the age gate before this lead is booked.';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_appointments_age_clearance
    BEFORE INSERT OR UPDATE ON appointments
    FOR EACH ROW EXECUTE FUNCTION block_booking_without_age_clearance();

COMMENT ON FUNCTION block_booking_without_age_clearance() IS
  'Last line of the child-safety gate. Everything above it — prompt, orchestrator, '
  'recommendation engine — can fail or be bypassed. This cannot.';


-- =============================================================================
-- 3. EMBEDDINGS — dimension must match the provider
-- =============================================================================
--
-- VECTOR(1536) was OpenAI text-embedding-3-small. Voyage (Anthropic's embedding
-- partner) defaults to 1024 and also offers 2048 / 512 / 256. Wrong dimension
-- fails on the first insert, not at migration time — a slow, confusing failure.
--
-- Set to 1024 for Voyage default. CHANGE THIS if you index with another provider
-- or a non-default output_dimension. Changing it later means re-embedding the
-- whole corpus, so decide before the first load.

ALTER TABLE knowledge_chunks
    ALTER COLUMN embedding TYPE VECTOR(1024);

COMMENT ON COLUMN knowledge_chunks.embedding IS
  'Dimension must match the embedding provider exactly. 1024 = Voyage default. '
  'OpenAI text-embedding-3-small is 1536, -3-large is 3072.';


-- =============================================================================
-- 4. VECTOR INDEX — HNSW instead of ivfflat
-- =============================================================================
--
-- ivfflat partitions the vector space using the data present when the index is
-- built. Built on an empty table it has nothing to learn from, and recall stays
-- quietly poor until someone reindexes — a failure with no error message, which
-- is the worst kind here: the agent would simply retrieve worse passages and
-- ground its answers on them.
--
-- HNSW builds incrementally and needs no training data, so it is correct from an
-- empty table. It costs more to build and more memory; at this corpus size that
-- trade is worth not having a silent recall cliff.

DROP INDEX IF EXISTS idx_chunks_vec;

CREATE INDEX idx_chunks_vec ON knowledge_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

COMMENT ON INDEX idx_chunks_vec IS
  'HNSW: valid from an empty table, no reindex after initial load. If you switch '
  'back to ivfflat, you MUST rebuild it after loading or recall degrades silently.';


-- =============================================================================
-- 5. VERIFICATION — run after applying
-- =============================================================================
--
-- Expected: the first two INSERTs succeed, the third fails with
-- 'Booking blocked: driver age clearance ... is pending, not approved.'
--
-- BEGIN;
--   INSERT INTO leads (kommo_lead_id, name) VALUES (999999, 'gate test')
--     RETURNING id \gset lead_
--
--   INSERT INTO human_approvals (lead_id, reason, driver_age, context)
--     VALUES (:'lead_id', 'age_below_track_minimum', 4, 'trigger test');
--
--   -- must fail:
--   INSERT INTO appointments (lead_id, closing_path, status, scheduled_at)
--     VALUES (:'lead_id', 'chat_close', 'confirmed', now() + interval '2 days');
-- ROLLBACK;
--
-- Then approve it and confirm the same INSERT succeeds:
--
-- BEGIN;
--   UPDATE human_approvals SET status = 'approved', decided_at = now()
--     WHERE lead_id = :'lead_id';
--   INSERT INTO appointments (lead_id, closing_path, status, scheduled_at)
--     VALUES (:'lead_id', 'chat_close', 'confirmed', now() + interval '2 days');
-- ROLLBACK;
--
-- A trigger that has never been shown to fire is not a gate. Run both.
-- =============================================================================

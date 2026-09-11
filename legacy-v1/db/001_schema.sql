-- =============================================================================
-- URace AI Sales Agent — schema
-- PostgreSQL 15+ · requires: pgcrypto (gen_random_uuid), vector (pgvector)
-- =============================================================================
--
-- RECONCILIATION NOTE
--
-- The DDL in the architecture document (section 9) predates several decisions.
-- This file is the current one. What changed and why:
--
--   1. programs.agent_action            NEW — recommend / handoff_to_owner / faq_only.
--                                       6 of 13 services are never sold by the agent.
--   2. programs.human_approval_below_age NEW — the age gate needs its own field.
--                                       age_min=4 (we serve) + this=5 (human decides).
--                                       A single age_min could only refuse or confirm;
--                                       neither matches the operation.
--   3. program_offers.agent_can_quote   NEW — a price can exist and still be
--                                       track-operator-only.
--   4. human_approvals                  NEW TABLE — the age gate is not an appointment.
--                                       Folding it into appointments.pending_human_approval
--                                       was wrong: an approval can exist with no booking.
--   5. appointments.closing_path        NEW — call_with_owner vs chat_close.
--   6. qualification_data               RENAMED to English field names, to match the
--                                       tool enum in tools/tools.json. Two vocabularies
--                                       for the same fields is a bug waiting to happen.
--
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- 1. LEADS AND CONTACTS
-- =============================================================================

CREATE TABLE leads (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kommo_lead_id       BIGINT UNIQUE NOT NULL,
    name                TEXT,
    preferred_language  TEXT NOT NULL DEFAULT 'en'
                        CHECK (preferred_language IN ('en','pt','es')),
    primary_channel     TEXT CHECK (primary_channel IN
                        ('whatsapp','instagram','tiktok','messenger','email','web_form','other')),
    lead_source         TEXT,
    current_stage       TEXT,
    status              TEXT NOT NULL DEFAULT 'active' CHECK (status IN
                        ('active','awaiting_response','qualified','scheduled',
                         'closed','escalated')),
    human_takeover      BOOLEAN NOT NULL DEFAULT FALSE,
    lead_master_summary TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_leads_status        ON leads(status) WHERE status <> 'closed';
CREATE INDEX idx_leads_takeover      ON leads(human_takeover) WHERE human_takeover;
CREATE INDEX idx_leads_source        ON leads(lead_source);

COMMENT ON COLUMN leads.human_takeover IS
  'When true the agent must not reply. Only a human clears this — never the agent.';
COMMENT ON COLUMN leads.lead_master_summary IS
  'Rolling cumulative summary. Replaced, never appended, so token cost stays O(1) '
  'in the lifetime of the lead.';

CREATE TABLE contacts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id     UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    channel     TEXT NOT NULL,
    external_id TEXT NOT NULL,       -- phone, @handle, email
    display_name TEXT,               -- name as it comes from the channel
    UNIQUE (channel, external_id)
);

CREATE INDEX idx_contacts_lead ON contacts(lead_id);

-- =============================================================================
-- 2. CONVERSATIONS AND MEMORY
-- =============================================================================

CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    channel         TEXT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    session_summary TEXT
);

CREATE INDEX idx_conversations_lead ON conversations(lead_id, started_at DESC);
CREATE INDEX idx_conversations_open ON conversations(lead_id) WHERE ended_at IS NULL;

CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sender_type     TEXT NOT NULL CHECK (sender_type IN ('lead','ai','human_agent')),
    content         TEXT NOT NULL,
    mode            TEXT,            -- which prompt mode produced it (ai only)
    tokens          INT,
    metadata        JSONB,           -- kb chunks used, tools called, confidence
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_messages_conv ON messages(conversation_id, created_at);

COMMENT ON COLUMN messages.metadata IS
  'For ai messages: which knowledge chunks and tool results grounded this reply. '
  'This is what makes "why did the agent say that" answerable.';

-- =============================================================================
-- 3. CATALOG — synced from Google Sheets, never edited here
-- =============================================================================

CREATE TABLE segments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    required_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    optional_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    default_agent_action TEXT CHECK (default_agent_action IN
                         ('recommend','handoff_to_owner','faq_only')),
    display_order   INT NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive'))
);

COMMENT ON COLUMN segments.required_fields IS
  'Which qualification fields this segment needs. A corporate lead has no driver age; '
  'a parent has no headcount. This is what stops the agent asking irrelevant questions.';

CREATE TABLE programs (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                     TEXT UNIQUE NOT NULL,
    name                     TEXT NOT NULL,
    segment_id               UUID REFERENCES segments(id),
    agent_action             TEXT NOT NULL DEFAULT 'faq_only' CHECK (agent_action IN
                             ('recommend','handoff_to_owner','faq_only')),
    category                 TEXT NOT NULL,
    description              TEXT,
    objective                TEXT,
    target_audience          TEXT,
    age_min                  INT CHECK (age_min IS NULL OR age_min >= 0),
    age_max                  INT,
    human_approval_below_age INT,
    recommended_level        TEXT,
    prerequisites            TEXT,
    benefits                 TEXT,
    differentiators          TEXT,
    keywords                 TEXT[],
    cross_sell               TEXT,
    upsell                   TEXT,
    recommendation_priority  INT NOT NULL DEFAULT 0,
    display_order            INT NOT NULL DEFAULT 0,
    status                   TEXT NOT NULL DEFAULT 'active'
                             CHECK (status IN ('active','inactive')),
    source_sheet_tab         TEXT,
    source_sheet_row         INT,
    synced_at                TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT age_range_sane CHECK (age_min IS NULL OR age_max IS NULL OR age_min <= age_max)
);

CREATE INDEX idx_programs_active   ON programs(status) WHERE status = 'active';
CREATE INDEX idx_programs_segment  ON programs(segment_id) WHERE status = 'active';
CREATE INDEX idx_programs_action   ON programs(agent_action);
CREATE INDEX idx_programs_keywords ON programs USING GIN(keywords);

COMMENT ON COLUMN programs.agent_action IS
  'recommend: agent sells it. handoff_to_owner: agent collects phone and routes to the '
  'owner, never quotes. faq_only: answers questions, does not offer.';
COMMENT ON COLUMN programs.human_approval_below_age IS
  'Below this age the agent may neither confirm nor refuse — it opens a human approval. '
  'Deliberately separate from age_min: age_min=4 means we serve from 4, this=5 means '
  'the track minimum is 5 and a person decides based on the child''s size.';
COMMENT ON COLUMN programs.description IS
  'NULL means the agent must NOT describe this program. It says it will confirm. '
  'Empty never means "make something reasonable up".';

CREATE TABLE program_offers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    offer_id            TEXT UNIQUE NOT NULL,   -- stable key from the sheet
    program_id          UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    offer_name          TEXT NOT NULL,
    context             TEXT,
    description         TEXT,
    price_amount        NUMERIC(10,2),
    price_currency      TEXT NOT NULL DEFAULT 'USD',
    price_unit          TEXT CHECK (price_unit IN
                        ('day','event','session','month','package','contract',
                         'person','service','3_days','4_days','5_days')),
    price_is_indicative BOOLEAN NOT NULL DEFAULT TRUE,
    price_variance_note TEXT,
    conditions_note     TEXT,
    agent_can_quote     BOOLEAN NOT NULL DEFAULT TRUE,
    status              TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','inactive')),
    source_sheet_tab    TEXT,
    source_sheet_row    INT,
    synced_at           TIMESTAMPTZ
);

CREATE INDEX idx_offers_program   ON program_offers(program_id) WHERE status = 'active';
CREATE INDEX idx_offers_quotable  ON program_offers(agent_can_quote) WHERE status = 'active';

COMMENT ON COLUMN program_offers.agent_can_quote IS
  'FALSE means the price is real but only the track operator may offer it. The agent '
  'keeps the row so it recognises the figure if a driver mentions it, and still never '
  'says the number. Deleting the row instead would create a blind spot.';
COMMENT ON COLUMN program_offers.price_is_indicative IS
  'The rate card itself says rates can vary. An exact quote that later moves is a '
  'commercial problem, so indicative offers are presented with their variance note.';

CREATE TABLE program_faq (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id    UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    question      TEXT NOT NULL,
    answer        TEXT NOT NULL,
    display_order INT NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE catalog_sync_runs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    triggered_by  TEXT NOT NULL CHECK (triggered_by IN ('schedule','manual')),
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    status        TEXT CHECK (status IN ('success','partial','failed')),
    rows_read     INT,
    rows_applied  INT,
    rows_rejected INT,
    diff_summary  JSONB,
    errors        JSONB
);

CREATE INDEX idx_sync_recent ON catalog_sync_runs(started_at DESC);

COMMENT ON TABLE catalog_sync_runs IS
  'A rejected row is reported and skipped — one malformed cell never takes the whole '
  'catalog down. This table answers "which catalog version was live when we told that '
  'driver that price".';

-- =============================================================================
-- 4. QUALIFICATION AND SCORING
-- =============================================================================

CREATE TABLE qualification_data (
    lead_id             UUID PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
    segment_id          UUID REFERENCES segments(id),
    segment_confidence  TEXT CHECK (segment_confidence IN ('low','medium','high')),
    segment_fields      JSONB NOT NULL DEFAULT '{}'::jsonb,

    for_whom            TEXT,
    driver_name         TEXT,
    responsible_name    TEXT,
    driver_age          INT,
    origin              TEXT,
    contact_phone       TEXT,
    contact_email       TEXT,
    goal                TEXT,
    experience_level    TEXT,
    competes            BOOLEAN,
    preferred_dates     TEXT,
    availability_window TEXT,
    budget_signal       TEXT,

    desired_program_id  UUID REFERENCES programs(id),
    desired_program_raw TEXT,

    inferred_fields     TEXT[] NOT NULL DEFAULT '{}',
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN qualification_data.inferred_fields IS
  'Field names the agent deduced rather than heard stated. Inferred values must not '
  'drive decisions and are re-checked when they matter.';
COMMENT ON COLUMN qualification_data.competes IS
  'The single most consequential field: TRUE routes the lead to the owner. Only set '
  'from an explicit answer, never inferred from "has driven karts before".';
COMMENT ON COLUMN qualification_data.segment_fields IS
  'Segment-specific fields (corporate headcount, company, etc). Kept as JSONB because '
  'a fixed column per segment would not survive the portfolio changing.';

CREATE TABLE lead_scores (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id            UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    score_total        INT NOT NULL CHECK (score_total BETWEEN 0 AND 100),
    classification     TEXT NOT NULL CHECK (classification IN ('hot','warm','cold')),
    criteria_breakdown JSONB NOT NULL,
    config_version     TEXT,
    calculated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_scores_lead ON lead_scores(lead_id, calculated_at DESC);

COMMENT ON COLUMN lead_scores.criteria_breakdown IS
  'Per criterion: points awarded AND the conversation excerpt that produced them. '
  'This is what answers "why was this lead classified hot".';
COMMENT ON COLUMN lead_scores.config_version IS
  'Which weight configuration produced this score, so historical scores stay '
  'interpretable after the weights are retuned.';

-- =============================================================================
-- 5. RECOMMENDATION ENGINE
-- =============================================================================

CREATE TABLE recommendation_rules (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 TEXT NOT NULL,
    rule_type            TEXT NOT NULL CHECK (rule_type IN ('match','boost','exclude')),
    conditions           JSONB NOT NULL,
    target_program_id    UUID REFERENCES programs(id) ON DELETE CASCADE,
    target_category      TEXT,
    score_impact         INT NOT NULL,
    explanation_template TEXT,
    priority_order       INT NOT NULL DEFAULT 0,
    status               TEXT NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active','draft','inactive')),
    created_by           TEXT,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT rule_has_target CHECK (
        target_program_id IS NOT NULL OR target_category IS NOT NULL)
);

CREATE INDEX idx_rules_active ON recommendation_rules(priority_order)
    WHERE status = 'active';

COMMENT ON COLUMN recommendation_rules.explanation_template IS
  'The justification text is DATA. The model only naturalises it — it never invents '
  'the reason a program was recommended.';

CREATE TABLE recommendation_log (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id                UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    input_profile          JSONB NOT NULL,
    segment_id             UUID REFERENCES segments(id),
    segment_confidence     TEXT,
    recommended_program_id UUID REFERENCES programs(id),
    confidence             TEXT CHECK (confidence IN ('low','medium','high')),
    status                 TEXT NOT NULL DEFAULT 'ok'
                           CHECK (status IN ('ok','insufficient_data')),
    missing_fields         TEXT[],
    rules_fired            JSONB,
    alternatives           JSONB,
    excluded               JSONB,
    evaluated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_reclog_lead ON recommendation_log(lead_id, evaluated_at DESC);

COMMENT ON COLUMN recommendation_log.excluded IS
  'Programs filtered out and why. Needed to answer "why was Summer Camp not offered '
  'to this family" — usually an age gate or a season rule.';

-- =============================================================================
-- 6. KNOWLEDGE BASE
-- =============================================================================

CREATE TABLE knowledge_documents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title         TEXT NOT NULL,
    category      TEXT NOT NULL,
    content       TEXT NOT NULL,
    language      TEXT NOT NULL DEFAULT 'en',
    status        TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active','draft','archived')),
    version       INT NOT NULL DEFAULT 1,
    source_type   TEXT NOT NULL DEFAULT 'manual'
                  CHECK (source_type IN ('manual','auto_generated')),
    source_ref_id UUID,
    updated_by    TEXT,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_kdocs_active ON knowledge_documents(category) WHERE status = 'active';
CREATE INDEX idx_kdocs_source ON knowledge_documents(source_ref_id)
    WHERE source_type = 'auto_generated';

COMMENT ON COLUMN knowledge_documents.source_type IS
  'auto_generated documents are rebuilt from the catalog on sync. Editing them by hand '
  'is pointless — the change is overwritten. Edit the sheet.';

CREATE TABLE knowledge_chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    chunk_text  TEXT NOT NULL,
    embedding   VECTOR(1536),
    metadata    JSONB
);

CREATE INDEX idx_chunks_doc ON knowledge_chunks(document_id);
CREATE INDEX idx_chunks_vec ON knowledge_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- =============================================================================
-- 7. HUMAN APPROVALS — the gate that blocks the agent
-- =============================================================================

CREATE TABLE human_approvals (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id           UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    reason            TEXT NOT NULL CHECK (reason IN
                      ('age_below_track_minimum','out_of_hours_request',
                       'own_kart_inspection','other')),
    driver_age        INT,
    driver_experience TEXT,
    requested_slot    TIMESTAMPTZ,
    context           TEXT NOT NULL,
    kommo_task_id     BIGINT,
    status            TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','approved','rejected')),
    decided_by        TEXT,
    decision_notes    TEXT,
    requested_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at        TIMESTAMPTZ
);

CREATE INDEX idx_approvals_pending ON human_approvals(requested_at)
    WHERE status = 'pending';
CREATE INDEX idx_approvals_lead    ON human_approvals(lead_id);

COMMENT ON TABLE human_approvals IS
  'Separate from appointments on purpose: an age approval can exist with no booking '
  'attached, and must block one from being created. Folding this into an appointment '
  'row would have allowed a booking to exist while approval was still pending.';
COMMENT ON COLUMN human_approvals.driver_experience IS
  'What the parent said about the child. The human evaluator needs it to judge size '
  'and readiness — this is the whole point of collecting it before escalating.';

-- =============================================================================
-- 8. APPOINTMENTS
-- =============================================================================

CREATE TABLE appointments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id             UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    closing_path        TEXT NOT NULL CHECK (closing_path IN
                        ('call_with_owner','chat_close')),
    kommo_task_id       BIGINT,
    google_event_id     TEXT,
    scheduled_at        TIMESTAMPTZ,
    timezone            TEXT NOT NULL DEFAULT 'America/New_York',
    status              TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN
                        ('pending_human_approval','scheduled','confirmed',
                         'attended','no_show','cancelled')),
    requested_slot      TIMESTAMPTZ,
    requested_slot_note TEXT,
    approval_id         UUID REFERENCES human_approvals(id),
    phone_collected     TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- A confirmed booking must have a time. Pending ones may not.
    CONSTRAINT scheduled_has_time CHECK (
        status = 'pending_human_approval' OR scheduled_at IS NOT NULL)
);

CREATE INDEX idx_appts_lead     ON appointments(lead_id);
CREATE INDEX idx_appts_upcoming ON appointments(scheduled_at)
    WHERE status IN ('scheduled','confirmed');

COMMENT ON COLUMN appointments.closing_path IS
  'call_with_owner: local lead wanting a recurring commitment. chat_close: single day / '
  'low commitment, closed in chat with a human task to finalise payment.';

-- =============================================================================
-- 9. FOLLOW-UP, ESCALATION, OBJECTIONS
-- =============================================================================

CREATE TABLE follow_ups (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id        UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    attempt_number INT NOT NULL CHECK (attempt_number >= 1),
    scheduled_at   TIMESTAMPTZ NOT NULL,
    sent_at        TIMESTAMPTZ,
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','sent','skipped','failed','cancelled')),
    skip_reason    TEXT,
    UNIQUE (lead_id, attempt_number)
);

CREATE INDEX idx_followups_due ON follow_ups(scheduled_at) WHERE status = 'pending';

COMMENT ON COLUMN follow_ups.skip_reason IS
  'Follow-ups are cancelled, not sent, when the lead was escalated, asked not to be '
  'contacted, or shared a personal hardship. An automated nudge after a bereavement '
  'is the worst thing this system could do.';

CREATE TABLE escalations (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id          UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    reason           TEXT NOT NULL CHECK (reason IN
                     ('competitor_profile','payment','discount_request','complaint',
                      'explicit_request','low_confidence','kb_gap','personal_hardship','other')),
    triggered_by     TEXT NOT NULL CHECK (triggered_by IN ('ai','rule','lead_request')),
    priority         TEXT NOT NULL DEFAULT 'normal'
                     CHECK (priority IN ('low','normal','high')),
    briefing         TEXT,
    verbatim_quote   TEXT,
    escalated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at      TIMESTAMPTZ,
    resolution_notes TEXT
);

CREATE INDEX idx_escalations_open ON escalations(escalated_at)
    WHERE resolved_at IS NULL;

COMMENT ON COLUMN escalations.verbatim_quote IS
  'For complaints: the driver''s own words, not the agent''s summary. A summarised '
  'complaint loses exactly what the human needs.';

CREATE TABLE objections_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id     UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    category    TEXT NOT NULL,
    excerpt     TEXT,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_objections_cat ON objections_log(category, detected_at DESC);

-- =============================================================================
-- 10. AUDIT AND CONFIGURATION
-- =============================================================================

CREATE TABLE audit_logs (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id    UUID REFERENCES leads(id) ON DELETE SET NULL,
    actor      TEXT NOT NULL CHECK (actor IN ('ai','system','human')),
    actor_id   TEXT,
    action     TEXT NOT NULL,
    details    JSONB,
    confidence NUMERIC(3,2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_lead   ON audit_logs(lead_id, created_at DESC);
CREATE INDEX idx_audit_action ON audit_logs(action, created_at DESC);

COMMENT ON TABLE audit_logs IS
  'Every consequential action, with its reason. Also covers Admin Panel writes — '
  'actor_id records who changed a rule.';

CREATE TABLE configurations (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category   TEXT NOT NULL,
    key        TEXT NOT NULL,
    value      JSONB NOT NULL,
    version    INT NOT NULL DEFAULT 1,
    updated_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (category, key)
);

COMMENT ON TABLE configurations IS
  'Business rules as data: business hours, scoring weights, follow-up intervals, '
  'escalation keywords, message templates, Kommo field mapping. Changing any of these '
  'is an edit, not a deploy.';

-- =============================================================================
-- 11. TRIGGERS
-- =============================================================================

CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_leads_touch     BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER trg_programs_touch  BEFORE UPDATE ON programs
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER trg_qual_touch      BEFORE UPDATE ON qualification_data
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- =============================================================================
-- 12. VIEWS
-- =============================================================================

-- Catalog completeness: what is still blocking automatic recommendation.
CREATE VIEW v_catalog_completeness AS
SELECT
    p.slug,
    p.name,
    p.agent_action,
    (p.segment_id IS NOT NULL)      AS has_segment,
    (p.description IS NOT NULL)     AS has_description,
    (p.age_min IS NOT NULL)         AS has_age_min,
    (p.recommended_level IS NOT NULL) AS has_level,
    (p.keywords IS NOT NULL AND array_length(p.keywords, 1) > 0) AS has_keywords,
    CASE
        WHEN p.agent_action <> 'recommend' THEN 'n/a — not sold by the agent'
        WHEN p.segment_id IS NULL THEN 'blocked: no segment'
        WHEN p.description IS NULL THEN 'partial: cannot describe the program'
        ELSE 'ready'
    END AS recommendation_readiness
FROM programs p
WHERE p.status = 'active';

COMMENT ON VIEW v_catalog_completeness IS
  'Powers the Admin Panel completeness screen. Makes the cost of an empty cell visible '
  'instead of silent.';

-- Leads blocked waiting on a human.
CREATE VIEW v_blocked_on_human AS
SELECT l.id, l.kommo_lead_id, l.name, 'approval' AS block_type,
       a.reason::text AS detail, a.requested_at AS since
FROM leads l JOIN human_approvals a ON a.lead_id = l.id
WHERE a.status = 'pending'
UNION ALL
SELECT l.id, l.kommo_lead_id, l.name, 'escalation',
       e.reason::text, e.escalated_at
FROM leads l JOIN escalations e ON e.lead_id = l.id
WHERE e.resolved_at IS NULL;

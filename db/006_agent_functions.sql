-- =============================================================================
-- 006: the tool layer, as database functions
--
-- WHY THIS EXISTS
--
-- The gates have to sit BELOW the model. That was already true for the age
-- gate, which is a trigger — everything above it can drift, be reworded or be
-- mutated, and the trigger still refuses.
--
-- Running the agent in n8n makes that reasoning general. n8n cannot run the
-- Python tool layer, and an HTTP tool pointing straight at the catalog would
-- hand the model a price it must not say. Moving the tools into SQL keeps the
-- structural property and leaves n8n needing nothing but HTTP:
--
--     n8n  --POST /rest/v1/rpc/agent_program-->  Postgres  -->  gated JSON
--
-- A model that never receives a number cannot be talked into saying it. That
-- is the whole design, restated in a place n8n can reach.
--
-- Called from n8n as:
--     POST https://<ref>.supabase.co/rest/v1/rpc/<function>
--     apikey: <service_role_key>
--     Authorization: Bearer <service_role_key>
--     { "p_lead_id": "...", ... }
--
-- SECURITY DEFINER so the calling role needs no direct table rights.
-- =============================================================================


-- =============================================================================
-- 1. CONTEXT — one call, everything routing needs
-- =============================================================================
CREATE OR REPLACE FUNCTION agent_context(p_session_id TEXT)
RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_lead   leads%ROWTYPE;
    v_qual   qualification_data%ROWTYPE;
    v_missing TEXT[];
    v_pending BOOLEAN;
BEGIN
    -- Identity is the channel handle, not the session key: the same person on
    -- WhatsApp and then by email is one lead, and treating them as two is how
    -- an agent re-asks questions the driver already answered.
    SELECT l.* INTO v_lead
    FROM leads l
    JOIN contacts c ON c.lead_id = l.id
    WHERE c.external_id = p_session_id
    ORDER BY l.created_at DESC LIMIT 1;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('found', false);
    END IF;

    SELECT * INTO v_qual FROM qualification_data WHERE lead_id = v_lead.id;

    v_missing := ARRAY(
        SELECT f FROM unnest(ARRAY['for_whom','driver_age','origin','goal',
                                   'experience_level']) f
        WHERE CASE f
            WHEN 'for_whom'         THEN v_qual.for_whom
            WHEN 'driver_age'       THEN v_qual.driver_age::text
            WHEN 'origin'           THEN v_qual.origin
            WHEN 'goal'             THEN v_qual.goal
            WHEN 'experience_level' THEN v_qual.experience_level
        END IS NULL);

    SELECT EXISTS (SELECT 1 FROM human_approvals
                   WHERE lead_id = v_lead.id AND status = 'pending')
      INTO v_pending;

    RETURN jsonb_build_object(
        'found', true,
        'lead_id', v_lead.id,
        'name', v_lead.name,
        'language', v_lead.preferred_language,
        'status', v_lead.status,
        -- Routing reads this first. A conversation a human owns must not be
        -- able to route itself back into selling.
        'human_takeover', v_lead.human_takeover,
        'summary', v_lead.lead_master_summary,
        'qualification', to_jsonb(v_qual) - 'lead_id',
        'missing_for_price', v_missing,
        'qualification_complete', (cardinality(v_missing) = 0),
        -- competes = true routes to the owner, before anything else is read.
        'competes', v_qual.competes,
        'pending_approval', v_pending
    );
END;
$$;


-- =============================================================================
-- 2. LEAD RESOLUTION — find or create, without duplicating a person
-- =============================================================================
CREATE OR REPLACE FUNCTION agent_resolve_lead(
    p_session_id TEXT,
    p_channel    TEXT DEFAULT 'kommo',
    p_name       TEXT DEFAULT NULL,
    p_phone      TEXT DEFAULT NULL,
    p_kommo_id   BIGINT DEFAULT NULL)
RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_external TEXT := COALESCE(p_phone, p_session_id);
    v_lead_id  UUID;
    v_conv_id  UUID;
BEGIN
    SELECT lead_id INTO v_lead_id FROM contacts
    WHERE channel = p_channel::channel_type AND external_id = v_external;

    IF v_lead_id IS NULL THEN
        INSERT INTO leads (kommo_lead_id, name, primary_channel, lead_source)
        VALUES (COALESCE(p_kommo_id, abs(hashtext(v_external)) % 10000000),
                p_name, p_channel::channel_type, 'kommo')
        ON CONFLICT (kommo_lead_id) DO UPDATE SET name = COALESCE(EXCLUDED.name, leads.name)
        RETURNING id INTO v_lead_id;

        INSERT INTO contacts (lead_id, channel, external_id, display_name)
        VALUES (v_lead_id, p_channel::channel_type, v_external, p_name)
        ON CONFLICT DO NOTHING;
    END IF;

    SELECT id INTO v_conv_id FROM conversations
    WHERE lead_id = v_lead_id AND ended_at IS NULL
    ORDER BY started_at DESC LIMIT 1;

    IF v_conv_id IS NULL THEN
        INSERT INTO conversations (lead_id, channel)
        VALUES (v_lead_id, p_channel::channel_type) RETURNING id INTO v_conv_id;
    END IF;

    RETURN jsonb_build_object('lead_id', v_lead_id, 'conversation_id', v_conv_id);
END;
$$;


-- =============================================================================
-- 3. PROGRAM DETAILS — the price gate, enforced here
--
-- This is the function that makes the whole arrangement work. When
-- qualification is incomplete, or the driver has not asked, the price is not
-- in the returned JSON at all. Not hidden, not flagged — absent.
-- =============================================================================
CREATE OR REPLACE FUNCTION agent_program(
    p_lead_id         UUID,
    p_slug            TEXT,
    p_price_requested BOOLEAN DEFAULT FALSE)
RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_p       programs%ROWTYPE;
    v_missing TEXT[];
    v_allowed BOOLEAN;
    v_reason  TEXT;
    v_offers  JSONB;
BEGIN
    SELECT * INTO v_p FROM programs WHERE slug = p_slug AND status = 'active';
    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'status', 'not_found',
            'note', 'No active program with that slug. Do not describe it; '
                    'say you will confirm with the team.');
    END IF;

    SELECT missing_for_price INTO v_missing
    FROM (SELECT (agent_context_by_lead(p_lead_id) ->> 'missing_for_price')::TEXT[]
          AS missing_for_price) x;

    v_allowed := p_price_requested AND cardinality(COALESCE(v_missing, '{}')) = 0;
    v_reason  := CASE
        WHEN NOT p_price_requested THEN 'the driver has not asked for a price'
        WHEN cardinality(COALESCE(v_missing,'{}')) > 0
            THEN 'qualification incomplete: missing ' || array_to_string(v_missing, ', ')
        ELSE NULL END;

    -- A driver being handed to the owner is never quoted, however complete
    -- their profile is. That conversation belongs to a person.
    IF v_p.agent_action IN ('handoff_to_owner', 'handoff_to_human') THEN
        v_allowed := FALSE;
        v_reason  := 'this program is not sold by you — route it to a person';
    END IF;

    SELECT jsonb_agg(jsonb_build_object(
        'offer_id', o.offer_id,
        'offer_name', o.offer_name,
        'context', o.context,
        'conditions_note', o.conditions_note,
        -- The number appears only when both conditions hold AND the offer is
        -- quotable. agent_can_quote = FALSE means the rate is real but only
        -- the track operator may offer it: the agent keeps knowing it exists
        -- so a driver mentioning it is not contradicted, and still never says
        -- the figure.
        'price', CASE WHEN v_allowed AND o.agent_can_quote
                      THEN o.price_amount ELSE NULL END,
        'unit', CASE WHEN v_allowed AND o.agent_can_quote
                     THEN o.price_unit ELSE NULL END,
        'currency', CASE WHEN v_allowed AND o.agent_can_quote
                         THEN o.price_currency ELSE NULL END,
        'variance_note', CASE WHEN v_allowed AND o.agent_can_quote
                              THEN o.price_variance_note ELSE NULL END,
        'price_withheld_because', CASE
            WHEN v_allowed AND o.agent_can_quote THEN NULL
            WHEN NOT o.agent_can_quote THEN
                'this rate exists but only the track operator may offer it'
            ELSE v_reason END,
        'must_add', CASE WHEN v_allowed AND o.agent_can_quote THEN
            'track fees are paid directly to Orlando Kart Center and are not included'
            ELSE NULL END))
    INTO v_offers
    FROM program_offers o
    WHERE o.program_id = v_p.id AND o.status = 'active';

    RETURN jsonb_build_object(
        'status', 'ok',
        'slug', v_p.slug,
        'name', v_p.name,
        'agent_action', v_p.agent_action,
        'description', v_p.description,
        'objective', v_p.objective,
        'target_audience', v_p.target_audience,
        'benefits', v_p.benefits,
        'differentiators', v_p.differentiators,
        'prerequisites', v_p.prerequisites,
        'age_min', v_p.age_min,
        'age_max', v_p.age_max,
        'human_approval_below_age', v_p.human_approval_below_age,
        'recommended_level', v_p.recommended_level,
        'offers', COALESCE(v_offers, '[]'::jsonb),
        -- An unfilled description is not a gap to paper over. Saying so is
        -- more reliable than hoping the model infers it from a null.
        'note', CASE WHEN v_p.description IS NULL THEN
            'This program has no description in the catalog. Do not describe '
            'it — say you will confirm the details with the team.' END);
END;
$$;


-- Helper: context by lead id, used by agent_program above.
CREATE OR REPLACE FUNCTION agent_context_by_lead(p_lead_id UUID)
RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_qual    qualification_data%ROWTYPE;
    v_missing TEXT[];
BEGIN
    SELECT * INTO v_qual FROM qualification_data WHERE lead_id = p_lead_id;
    v_missing := ARRAY(
        SELECT f FROM unnest(ARRAY['for_whom','driver_age','origin','goal',
                                   'experience_level']) f
        WHERE CASE f
            WHEN 'for_whom'         THEN v_qual.for_whom
            WHEN 'driver_age'       THEN v_qual.driver_age::text
            WHEN 'origin'           THEN v_qual.origin
            WHEN 'goal'             THEN v_qual.goal
            WHEN 'experience_level' THEN v_qual.experience_level
        END IS NULL);
    RETURN jsonb_build_object('missing_for_price', v_missing);
END;
$$;


-- =============================================================================
-- 4. QUALIFICATION — write, and report what is still missing
-- =============================================================================
CREATE OR REPLACE FUNCTION agent_qualify(
    p_lead_id  UUID,
    p_field    TEXT,
    p_value    TEXT,
    p_inferred BOOLEAN DEFAULT FALSE)
RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_seg UUID;
BEGIN
    IF p_field NOT IN ('for_whom','driver_name','responsible_name','driver_age',
                       'origin','contact_phone','contact_email','goal',
                       'experience_level','competes','preferred_dates',
                       'availability_window','budget_signal','segment') THEN
        RETURN jsonb_build_object('status','error',
                                  'error', format('%s is not writable', p_field));
    END IF;

    INSERT INTO qualification_data (lead_id) VALUES (p_lead_id)
    ON CONFLICT (lead_id) DO NOTHING;

    -- segment arrives as a slug and the column is a UUID. Resolving here
    -- rather than writing the slug keeps a bad value out of the table.
    IF p_field = 'segment' THEN
        SELECT id INTO v_seg FROM segments WHERE slug = p_value;
        IF v_seg IS NULL THEN
            RETURN jsonb_build_object('status','error',
                'error', format('no segment with slug %s', p_value));
        END IF;
        UPDATE qualification_data SET segment_id = v_seg, updated_at = now()
        WHERE lead_id = p_lead_id;

    ELSIF p_field = 'driver_age' THEN
        IF p_value !~ '^\d+$' THEN
            RETURN jsonb_build_object('status','error',
                                      'error','driver_age must be a number');
        END IF;
        UPDATE qualification_data SET driver_age = p_value::INT, updated_at = now()
        WHERE lead_id = p_lead_id;

    ELSIF p_field = 'competes' THEN
        UPDATE qualification_data
        SET competes = lower(p_value) IN ('true','yes','sim','1'),
            updated_at = now()
        WHERE lead_id = p_lead_id;

    ELSE
        EXECUTE format(
            'UPDATE qualification_data SET %I = $1, updated_at = now() '
            'WHERE lead_id = $2', p_field)
        USING p_value, p_lead_id;
    END IF;

    IF p_inferred THEN
        UPDATE qualification_data
        SET inferred_fields = array_append(
            array_remove(inferred_fields, p_field), p_field)
        WHERE lead_id = p_lead_id;
    END IF;

    RETURN agent_context_by_lead(p_lead_id) || jsonb_build_object('status','ok');
END;
$$;


-- =============================================================================
-- 5. AGE GATE — the agent may neither confirm nor refuse
-- =============================================================================
CREATE OR REPLACE FUNCTION agent_request_approval(
    p_lead_id    UUID,
    p_reason     TEXT,
    p_context    TEXT,
    p_age        INT DEFAULT NULL,
    p_experience TEXT DEFAULT NULL)
RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE v_id UUID;
BEGIN
    INSERT INTO human_approvals (lead_id, reason, driver_age,
                                 driver_experience, context)
    VALUES (p_lead_id, p_reason, p_age, p_experience, p_context)
    RETURNING id INTO v_id;

    RETURN jsonb_build_object(
        'status', 'pending',
        'approval_id', v_id,
        'note', 'A human now owns this decision. Tell the driver the team will '
                'confirm, and tie it to the child''s size. Do not predict what '
                'they will decide.');
END;
$$;


-- =============================================================================
-- 6. ESCALATION — irreversible, and it silences follow-ups
-- =============================================================================
CREATE OR REPLACE FUNCTION agent_escalate(
    p_lead_id  UUID,
    p_reason   TEXT,
    p_priority TEXT DEFAULT 'normal',
    p_briefing TEXT DEFAULT NULL,
    p_quote    TEXT DEFAULT NULL)
RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    INSERT INTO escalations (lead_id, reason, triggered_by, priority,
                             briefing, verbatim_quote)
    VALUES (p_lead_id, p_reason, 'ai', p_priority, p_briefing, p_quote);

    UPDATE leads SET human_takeover = TRUE, status = 'escalated'
    WHERE id = p_lead_id;

    -- No automated message may reach someone who was escalated — least of all
    -- someone who just disclosed a hardship.
    UPDATE follow_ups
    SET status = 'cancelled', skip_reason = 'escalated: ' || p_reason
    WHERE lead_id = p_lead_id AND status = 'pending';

    RETURN jsonb_build_object(
        'status', 'escalated',
        'note', 'A human owns this conversation now. Send one closing message '
                'and stop.');
END;
$$;


-- =============================================================================
-- 7. MESSAGE PERSISTENCE — the transcript the audit trail shows
-- =============================================================================
CREATE OR REPLACE FUNCTION agent_log_message(
    p_conversation_id UUID,
    p_sender          TEXT,
    p_content         TEXT,
    p_mode            TEXT DEFAULT NULL)
RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    INSERT INTO messages (conversation_id, sender_type, content, mode)
    VALUES (p_conversation_id, p_sender, p_content, p_mode);
    RETURN jsonb_build_object('status','ok');
END;
$$;


CREATE OR REPLACE FUNCTION agent_history(p_conversation_id UUID,
                                         p_limit INT DEFAULT 12)
RETURNS JSONB
LANGUAGE sql SECURITY DEFINER AS $$
    SELECT COALESCE(jsonb_agg(jsonb_build_object(
        'role', CASE WHEN sender_type = 'lead' THEN 'user' ELSE 'assistant' END,
        'content', content) ORDER BY created_at), '[]'::jsonb)
    FROM (SELECT sender_type, content, created_at FROM messages
          WHERE conversation_id = p_conversation_id
          ORDER BY created_at DESC LIMIT p_limit) t;
$$;


-- =============================================================================
-- 8. CATALOG LISTING — what the agent may offer at all
-- =============================================================================
CREATE OR REPLACE FUNCTION agent_sellable_programs()
RETURNS JSONB
LANGUAGE sql SECURITY DEFINER AS $$
    SELECT COALESCE(jsonb_agg(jsonb_build_object(
        'slug', slug, 'name', name, 'keywords', keywords,
        'age_min', age_min, 'recommended_level', recommended_level)
        ORDER BY recommendation_priority DESC), '[]'::jsonb)
    FROM programs WHERE status = 'active' AND agent_action = 'recommend';
$$;


-- =============================================================================
-- VERIFICATION
-- =============================================================================
-- The price gate, proved in four combinations. Expect NULL, NULL, NULL, 819.
--
-- SELECT jsonb_pretty(agent_program(
--   (SELECT id FROM leads LIMIT 1), 'one_day', false));   -- not asked
-- SELECT jsonb_pretty(agent_program(
--   (SELECT id FROM leads LIMIT 1), 'one_day', true));    -- asked, unqualified
--
-- Grant only what n8n needs:
-- GRANT EXECUTE ON FUNCTION agent_context, agent_resolve_lead, agent_program,
--   agent_qualify, agent_request_approval, agent_escalate, agent_log_message,
--   agent_history, agent_sellable_programs TO anon, authenticated;

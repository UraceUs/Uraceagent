-- =============================================================================
-- 005: handoff_to_human
--
-- Until now every non-sellable program routed to handoff_to_owner, which means
-- Italo. That is right for a racer asking about mechanic support at a national —
-- it is a commercial conversation with the team owner.
--
-- It is wrong for someone asking about a tyre change. The owner ends up triaging
-- workshop requests, and the agent generates a SALES BRIEFING for a maintenance
-- job: wrong artefact, wrong person.
--
-- Two destinations:
--   handoff_to_owner   Italo. Commercial conversation with a driver who competes.
--   handoff_to_human   The team. Operational request (workshop, kart rental).
--
-- faq_only stays in the enum but is no longer used by any program. Every request
-- outside the six sellable programs now reaches a person.
--
-- Apply after 003_constraints.sql.
-- =============================================================================

ALTER TABLE programs
    DROP CONSTRAINT IF EXISTS programs_agent_action_check;
ALTER TABLE programs
    ADD CONSTRAINT programs_agent_action_check
    CHECK (agent_action IN ('recommend', 'handoff_to_owner',
                            'handoff_to_human', 'faq_only'));

ALTER TABLE segments
    DROP CONSTRAINT IF EXISTS segments_default_agent_action_check;
ALTER TABLE segments
    ADD CONSTRAINT segments_default_agent_action_check
    CHECK (default_agent_action IN ('recommend', 'handoff_to_owner',
                                    'handoff_to_human', 'faq_only'));

-- The escalation reason has to distinguish the two as well, or the queue cannot
-- be split and both land in the same place regardless of the routing above.
ALTER TABLE escalations
    DROP CONSTRAINT IF EXISTS escalations_reason_check;
ALTER TABLE escalations
    ADD CONSTRAINT escalations_reason_check
    CHECK (reason IN ('competitor_profile', 'operational_request', 'payment',
                      'discount_request', 'complaint', 'explicit_request',
                      'low_confidence', 'kb_gap', 'personal_hardship', 'other'));

COMMENT ON COLUMN programs.agent_action IS
  'recommend: the agent sells it. handoff_to_owner: collect phone, brief Italo, '
  'never quote. handoff_to_human: operational request, route to the team without '
  'a sales briefing. faq_only: unused — every non-sellable request reaches a person.';

-- -----------------------------------------------------------------------------
-- Verification
-- -----------------------------------------------------------------------------
-- Expected after the catalog sync:
--   recommend         6   one_day, urace_academy, summer_camp, lead_follow,
--                         corporate_events, arrive_drive
--   handoff_to_owner  5   race_team_support, diy_program, mechanic_services,
--                         engine_rental, chassis_rental
--   handoff_to_human  2   kart_rental, workshop_services
--   faq_only          0
--
-- SELECT agent_action, count(*), string_agg(slug, ', ' ORDER BY slug)
-- FROM programs WHERE status = 'active' GROUP BY agent_action ORDER BY 1;

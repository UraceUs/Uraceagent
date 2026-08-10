-- =============================================================================
-- URace AI Sales Agent — configuration seed
--
-- Every decision URace made, as data. Changing any of these is an UPDATE,
-- never a deploy. Run after 001_schema.sql.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- BUSINESS HOURS  (Orlando — America/New_York)
-- -----------------------------------------------------------------------------
INSERT INTO configurations (category, key, value, updated_by) VALUES
('business_hours', 'timezone', '"America/New_York"', 'seed'),

('business_hours', 'support_hours', '{
  "monday":    {"open": "09:00", "close": "18:00"},
  "tuesday":   {"open": "09:00", "close": "18:00"},
  "wednesday": {"open": "09:00", "close": "18:00"},
  "thursday":  {"open": "09:00", "close": "18:00"},
  "friday":    {"open": "09:00", "close": "18:00"},
  "saturday":  {"open": "08:00", "close": "12:00"},
  "sunday":    {"open": "08:00", "close": "12:00"}
}', 'seed'),

-- Weekends are staffed, but calls are proactively offered on weekdays only.
('business_hours', 'preferred_booking_days',
 '["monday","tuesday","wednesday","thursday","friday"]', 'seed'),

('business_hours', 'out_of_hours_policy', '{
  "auto_confirm": false,
  "action": "create_human_approval",
  "message_intent": "tell the driver the team will confirm availability"
}', 'seed');

-- -----------------------------------------------------------------------------
-- LEAD SCORING  (weights sum to 100)
-- -----------------------------------------------------------------------------
INSERT INTO configurations (category, key, value, updated_by) VALUES
('scoring_rules', 'weights', '{
  "urgency":              25,
  "budget_fit":           20,
  "program_defined":      15,
  "driver_profile_fit":   15,
  "engagement":           15,
  "scheduling_readiness": 10
}', 'seed'),

('scoring_rules', 'thresholds', '{"hot": 70, "warm": 40}', 'seed'),

-- Investment-capacity signals, observed in conversation. Deliberately NOT
-- inferred from social profiles: the expensive error is the false negative —
-- the quiet parent who spends thousands a month.
('scoring_rules', 'budget_signals', '{
  "asks_about_monthly_or_contract":  "high",
  "travels_from_out_of_state":       "high",
  "owns_a_kart":                     "high",
  "asks_about_championship_season":  "high",
  "no_reaction_to_price":            "high",
  "asks_only_cheapest_option":       "low",
  "raises_price_objection_twice":    "low"
}', 'seed'),

('scoring_rules', 'config_version', '"2026-07-28.1"', 'seed');

-- -----------------------------------------------------------------------------
-- PRICE DISCLOSURE
-- -----------------------------------------------------------------------------
INSERT INTO configurations (category, key, value, updated_by) VALUES
('price_policy', 'disclosure_gate', '{
  "proactive_quoting": false,
  "requires_explicit_request": true,
  "requires_qualification_complete": true,
  "requires_lead_score_minimum": null,
  "one_price_at_a_time": true,
  "value_framing_before_number": true
}', 'seed'),

-- The five questions that make up "qualification complete".
('price_policy', 'qualification_required_fields',
 '["for_whom", "driver_age", "origin", "goal", "experience_level"]', 'seed'),

('price_policy', 'mandatory_disclaimer', '{
  "track_fees": "driver pass and pit pass are paid directly to Orlando Kart Center",
  "never_say": ["all-inclusive", "everything included"]
}', 'seed'),

-- The agent informs that add-ons exist; it never computes a total.
('price_policy', 'agent_computes_totals', 'false', 'seed');

-- -----------------------------------------------------------------------------
-- CLOSING PATH
-- -----------------------------------------------------------------------------
INSERT INTO configurations (category, key, value, updated_by) VALUES
('closing', 'routing', '{
  "call_with_owner": {
    "conditions": ["origin = local", "wants_recurring_commitment = true"],
    "action": "schedule call and hand off to owner"
  },
  "chat_close": {
    "conditions": ["single day or low commitment"],
    "action": "close in chat, then create human task to finalise payment"
  }
}', 'seed'),

('closing', 'required_before_scheduling',
 '["responsible_name", "driver_name", "driver_age", "origin",
   "contact_phone", "availability_window"]', 'seed'),

-- No payment is ever completed by the agent.
('closing', 'agent_takes_payment', 'false', 'seed');

-- -----------------------------------------------------------------------------
-- FOLLOW-UP
-- -----------------------------------------------------------------------------
INSERT INTO configurations (category, key, value, updated_by) VALUES
('follow_up', 'intervals_hours', '[24, 72, 168]', 'seed'),
('follow_up', 'max_attempts', '3', 'seed'),
('follow_up', 'close_reason_after_max', '"no_response"', 'seed'),

('follow_up', 'hard_stops', '[
  "lead_escalated",
  "lead_asked_not_to_be_contacted",
  "personal_hardship_disclosed",
  "channel_messaging_window_closed"
]', 'seed');

-- -----------------------------------------------------------------------------
-- ESCALATION
-- -----------------------------------------------------------------------------
INSERT INTO configurations (category, key, value, updated_by) VALUES
('escalation', 'keywords_en',
 '["discount", "refund", "cancel", "complaint", "manager", "lawyer",
   "chargeback", "speak to a human", "real person"]', 'seed'),
('escalation', 'keywords_pt',
 '["desconto", "reembolso", "cancelar", "reclamação", "gerente",
   "advogado", "falar com humano", "pessoa de verdade"]', 'seed'),
('escalation', 'keywords_es',
 '["descuento", "reembolso", "cancelar", "queja", "gerente",
   "abogado", "hablar con una persona"]', 'seed'),

('escalation', 'always_escalate',
 '["payment", "discount_request", "complaint", "personal_hardship"]', 'seed'),

('escalation', 'rag_confidence_threshold', '0.72', 'seed'),

-- Once escalated the agent stays silent until a human hands it back.
('escalation', 'agent_resumes_automatically', 'false', 'seed');

-- -----------------------------------------------------------------------------
-- CATALOG SYNC
-- -----------------------------------------------------------------------------
INSERT INTO configurations (category, key, value, updated_by) VALUES
('catalog_sync', 'sheet_tabs',
 '{"segments": "_segments", "programs": "_programs", "offers": "_offers"}', 'seed'),
('catalog_sync', 'interval_minutes', '15', 'seed'),

-- One malformed cell must never take the catalog down.
('catalog_sync', 'on_row_error', '"reject_row_and_report"', 'seed'),
-- A row that disappears is deactivated, never deleted: history depends on it.
('catalog_sync', 'on_missing_row', '"set_inactive"', 'seed'),
-- If the sheet is unreachable, keep serving the last good catalog and alert.
('catalog_sync', 'on_sheet_unavailable', '"keep_last_good_and_alert"', 'seed');

-- -----------------------------------------------------------------------------
-- SAFETY
-- -----------------------------------------------------------------------------
INSERT INTO configurations (category, key, value, updated_by) VALUES
('safety', 'age_gate', '{
  "below_program_threshold": "create_human_approval",
  "agent_may_confirm": false,
  "agent_may_refuse": false,
  "must_collect": ["driver_age", "driver_experience"],
  "rationale_to_driver": "clearance depends on the child''s size and is checked by the team"
}', 'seed'),

-- Empty catalog field means "do not evaluate", never "assume something sensible".
('safety', 'empty_field_policy', '{
  "age_min":           "do_not_filter_by_age",
  "segment_id":        "exclude_from_automatic_recommendation",
  "recommended_level": "do_not_filter_by_level",
  "description":       "do_not_describe_program_escalate_instead",
  "price_amount":      "never_estimate_escalate_instead"
}', 'seed'),

('safety', 'profile_enrichment', '{
  "default_result": "not_possible",
  "may_raise_priority": true,
  "may_lower_service_level": false,
  "allowed_signals": ["public_company_data", "role", "city"],
  "forbidden_signals": ["photo", "appearance", "surname", "neighbourhood", "follower_count"]
}', 'seed');

-- -----------------------------------------------------------------------------
-- KOMMO FIELD MAPPING  — fill with real IDs from the account
-- -----------------------------------------------------------------------------
INSERT INTO configurations (category, key, value, updated_by) VALUES
('pipeline_mapping', 'custom_fields', '{
  "interest":            {"field_id": null},
  "program":             {"field_id": null, "type": "text",
                          "note": "free text, not a select — avoids syncing option lists with the catalog"},
  "experience":          {"field_id": null},
  "driver_age":          {"field_id": null},
  "budget":              {"field_id": null},
  "urgency":             {"field_id": null},
  "lead_score":          {"field_id": null},
  "score_reason":        {"field_id": null}
}', 'seed'),

('pipeline_mapping', 'stages', '{
  "new":           {"status_id": null},
  "qualifying":    {"status_id": null},
  "qualified":     {"status_id": null},
  "scheduled":     {"status_id": null},
  "with_owner":    {"status_id": null},
  "closed_lost":   {"status_id": null}
}', 'seed');

-- -----------------------------------------------------------------------------
-- SEGMENTS
-- -----------------------------------------------------------------------------
INSERT INTO segments (slug, name, description, required_fields, optional_fields,
                      default_agent_action, display_order) VALUES
('corporate', 'Corporate / Group',
 'Company, family or group booking a private event (minimum 3 drivers)',
 '["headcount","preferred_date"]', '["company","total_budget","city"]',
 'recommend', 1),

('youth', 'Youth / Family',
 'Parent or guardian looking for an activity for a child or teenager',
 '["driver_age","experience_level","origin"]', '["goal","preferred_period"]',
 'recommend', 2),

('learner', 'Beginner / Recreational',
 'Beginner, or someone who has only driven recreationally (indoor, rental, arcade)',
 '["experience_level","origin"]', '["driver_age","goal","availability_window"]',
 'recommend', 3),

('competitor', 'Active racer',
 'Actually competes: runs a series, has a class, cites lap times',
 '["experience_level","contact_phone"]', '["category","target_event","dates"]',
 'handoff_to_owner', 4),

('owner_operator', 'Kart or team owner',
 'Already owns a kart or runs a team; wants maintenance, parts or support',
 '["need_type"]', '["owns_kart","category"]',
 'handoff_to_owner', 5);

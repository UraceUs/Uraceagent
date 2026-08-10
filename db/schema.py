"""
Schema spec — a definição executável do modelo de dados.

No Postgres isto era o DDL: CHECKs, NOT NULLs, DOMAINs. O Firestore não impõe
nada disso, então a especificação vira dado Python — e continua tendo um
checador (catalog/validate_mapping.py) e um validador de escrita (validate()).

A regra que produziu este arquivo continua a mesma de sempre: um vocabulário,
uma definição. Os enums abaixo são A definição — tools.json, mapping.py e o
código do agente são conferidos contra eles, nunca o contrário.
"""

from __future__ import annotations

# =============================================================================
# ENUMS — o que os CHECKs e DOMAINs do Postgres declaravam
# =============================================================================

CHANNELS = ("whatsapp", "instagram", "tiktok", "messenger",
            "email", "web_form", "other")

LANGUAGES = ("en", "pt", "es")

LEAD_STATUS = ("active", "awaiting_response", "qualified", "scheduled",
               "closed", "escalated")

SENDER_TYPES = ("lead", "ai", "human_agent")

AGENT_ACTIONS = ("recommend", "handoff_to_owner", "handoff_to_human", "faq_only")

PRICE_UNITS = ("day", "event", "session", "month", "package", "contract",
               "person", "service", "3_days", "4_days", "5_days")

ROW_STATUS = ("active", "inactive")

APPROVAL_REASONS = ("age_below_track_minimum", "out_of_hours_request",
                    "own_kart_inspection", "other")

APPROVAL_STATUS = ("pending", "approved", "rejected")

CLOSING_PATHS = ("call_with_owner", "chat_close")

APPOINTMENT_STATUS = ("pending_human_approval", "scheduled", "confirmed",
                      "attended", "no_show", "cancelled")

FOLLOW_UP_STATUS = ("pending", "sent", "skipped", "failed", "cancelled")

ESCALATION_REASONS = ("competitor_profile", "operational_request", "payment",
                      "discount_request", "complaint", "explicit_request",
                      "low_confidence", "kb_gap", "personal_hardship", "other")

ESCALATION_TRIGGERS = ("ai", "rule", "lead_request")

PRIORITIES = ("low", "normal", "high")

CONFIDENCE_LEVELS = ("low", "medium", "high")

SCORE_CLASSES = ("hot", "warm", "cold")

AUDIT_ACTORS = ("ai", "system", "human")

DOC_STATUS = ("active", "draft", "archived")

DOC_SOURCE_TYPES = ("manual", "auto_generated")

SYNC_TRIGGERS = ("schedule", "manual")

SYNC_STATUS = ("success", "partial", "failed")

EMBEDDING_DIMENSION = 1024  # Voyage default. Mudar = re-embed do corpus inteiro.


# =============================================================================
# COLEÇÕES — campos, enums e obrigatoriedade
#
# O formato espelha o que validate_mapping.py precisa: por coleção, um dict
# campo -> {"check": tuple|None, "required": bool}. "required" cobre o papel
# do NOT NULL sem default; "check" cobre o CHECK ... IN (...).
# =============================================================================

COLLECTIONS: dict[str, dict[str, dict]] = {
    "leads": {
        "kommo_lead_id":       {"check": None, "required": True},
        "name":                {"check": None, "required": False},
        "preferred_language":  {"check": LANGUAGES, "required": False},
        "primary_channel":     {"check": CHANNELS, "required": False},
        "lead_source":         {"check": None, "required": False},
        "current_stage":       {"check": None, "required": False},
        "status":              {"check": LEAD_STATUS, "required": False},
        "human_takeover":      {"check": None, "required": False},
        "lead_master_summary": {"check": None, "required": False},
        # qualification é um mapa embutido — campos em QUALIFICATION_FIELDS.
        "qualification":       {"check": None, "required": False},
    },
    "contacts": {
        "lead_id":      {"check": None, "required": True},
        "channel":      {"check": CHANNELS, "required": True},
        "external_id":  {"check": None, "required": True},
        "display_name": {"check": None, "required": False},
    },
    "conversations": {
        "lead_id":         {"check": None, "required": True},
        "channel":         {"check": CHANNELS, "required": True},
        "ended_at":        {"check": None, "required": False},
        "session_summary": {"check": None, "required": False},
    },
    "messages": {
        "conversation_id": {"check": None, "required": True},
        "sender_type":     {"check": SENDER_TYPES, "required": True},
        "content":         {"check": None, "required": True},
        "mode":            {"check": None, "required": False},
        "tokens":          {"check": None, "required": False},
        "metadata":        {"check": None, "required": False},
    },
    "segments": {
        "slug":                 {"check": None, "required": True},
        "name":                 {"check": None, "required": True},
        "description":          {"check": None, "required": False},
        "required_fields":      {"check": None, "required": False},
        "optional_fields":      {"check": None, "required": False},
        "default_agent_action": {"check": AGENT_ACTIONS, "required": False},
        "display_order":        {"check": None, "required": False},
        "status":               {"check": ROW_STATUS, "required": False},
    },
    "programs": {
        "slug":                     {"check": None, "required": True},
        "name":                     {"check": None, "required": True},
        "segment_id":               {"check": None, "required": False},
        "agent_action":             {"check": AGENT_ACTIONS, "required": False},
        "category":                 {"check": None, "required": True},
        "description":              {"check": None, "required": False},
        "objective":                {"check": None, "required": False},
        "target_audience":          {"check": None, "required": False},
        "age_min":                  {"check": None, "required": False},
        "age_max":                  {"check": None, "required": False},
        "human_approval_below_age": {"check": None, "required": False},
        "recommended_level":        {"check": None, "required": False},
        "prerequisites":            {"check": None, "required": False},
        "benefits":                 {"check": None, "required": False},
        "differentiators":          {"check": None, "required": False},
        "keywords":                 {"check": None, "required": False},
        "cross_sell":               {"check": None, "required": False},
        "upsell":                   {"check": None, "required": False},
        "recommendation_priority":  {"check": None, "required": False},
        "display_order":            {"check": None, "required": False},
        "status":                   {"check": ROW_STATUS, "required": False},
        "source_sheet_tab":         {"check": None, "required": False},
        "source_sheet_row":         {"check": None, "required": False},
        "synced_at":                {"check": None, "required": False},
    },
    "program_offers": {
        "offer_id":            {"check": None, "required": True},
        "program_id":          {"check": None, "required": True},
        "offer_name":          {"check": None, "required": True},
        "context":             {"check": None, "required": False},
        "description":         {"check": None, "required": False},
        "price_amount":        {"check": None, "required": False},
        "price_currency":      {"check": None, "required": False},
        "price_unit":          {"check": PRICE_UNITS, "required": False},
        "price_is_indicative": {"check": None, "required": False},
        "price_variance_note": {"check": None, "required": False},
        "conditions_note":     {"check": None, "required": False},
        "agent_can_quote":     {"check": None, "required": False},
        "status":              {"check": ROW_STATUS, "required": False},
        "source_sheet_tab":    {"check": None, "required": False},
        "source_sheet_row":    {"check": None, "required": False},
        "synced_at":           {"check": None, "required": False},
    },
    "human_approvals": {
        "lead_id":           {"check": None, "required": True},
        "reason":            {"check": APPROVAL_REASONS, "required": True},
        "driver_age":        {"check": None, "required": False},
        "driver_experience": {"check": None, "required": False},
        "requested_slot":    {"check": None, "required": False},
        "context":           {"check": None, "required": True},
        "kommo_task_id":     {"check": None, "required": False},
        "status":            {"check": APPROVAL_STATUS, "required": False},
        "decided_by":        {"check": None, "required": False},
        "decision_notes":    {"check": None, "required": False},
        "decided_at":        {"check": None, "required": False},
    },
    "appointments": {
        "lead_id":             {"check": None, "required": True},
        "closing_path":        {"check": CLOSING_PATHS, "required": True},
        "kommo_task_id":       {"check": None, "required": False},
        "google_event_id":     {"check": None, "required": False},
        "scheduled_at":        {"check": None, "required": False},
        "timezone":            {"check": None, "required": False},
        "status":              {"check": APPOINTMENT_STATUS, "required": False},
        "requested_slot":      {"check": None, "required": False},
        "requested_slot_note": {"check": None, "required": False},
        "approval_id":         {"check": None, "required": False},
        "phone_collected":     {"check": None, "required": False},
    },
    "follow_ups": {
        "lead_id":        {"check": None, "required": True},
        "attempt_number": {"check": None, "required": True},
        "scheduled_at":   {"check": None, "required": True},
        "sent_at":        {"check": None, "required": False},
        "status":         {"check": FOLLOW_UP_STATUS, "required": False},
        "skip_reason":    {"check": None, "required": False},
    },
    "escalations": {
        "lead_id":          {"check": None, "required": True},
        "reason":           {"check": ESCALATION_REASONS, "required": True},
        "triggered_by":     {"check": ESCALATION_TRIGGERS, "required": True},
        "priority":         {"check": PRIORITIES, "required": False},
        "briefing":         {"check": None, "required": False},
        "verbatim_quote":   {"check": None, "required": False},
        "resolved_at":      {"check": None, "required": False},
        "resolution_notes": {"check": None, "required": False},
    },
    "lead_scores": {
        "lead_id":            {"check": None, "required": True},
        "score_total":        {"check": None, "required": True},
        "classification":     {"check": SCORE_CLASSES, "required": True},
        "criteria_breakdown": {"check": None, "required": True},
        "config_version":     {"check": None, "required": False},
    },
    "audit_logs": {
        "lead_id":    {"check": None, "required": False},
        "actor":      {"check": AUDIT_ACTORS, "required": True},
        "actor_id":   {"check": None, "required": False},
        "action":     {"check": None, "required": True},
        "details":    {"check": None, "required": False},
        "confidence": {"check": None, "required": False},
    },
    "objections_log": {
        "lead_id":  {"check": None, "required": True},
        "category": {"check": None, "required": True},
        "excerpt":  {"check": None, "required": False},
    },
    "catalog_sync_runs": {
        "triggered_by":  {"check": SYNC_TRIGGERS, "required": True},
        "started_at":    {"check": None, "required": True},
        "finished_at":   {"check": None, "required": False},
        "status":        {"check": SYNC_STATUS, "required": False},
        "rows_read":     {"check": None, "required": False},
        "rows_applied":  {"check": None, "required": False},
        "rows_rejected": {"check": None, "required": False},
        "diff_summary":  {"check": None, "required": False},
        "errors":        {"check": None, "required": False},
    },
    "knowledge_documents": {
        "title":         {"check": None, "required": True},
        "category":      {"check": None, "required": True},
        "content":       {"check": None, "required": True},
        "language":      {"check": LANGUAGES, "required": False},
        "status":        {"check": DOC_STATUS, "required": False},
        "version":       {"check": None, "required": False},
        "source_type":   {"check": DOC_SOURCE_TYPES, "required": False},
        "source_ref_id": {"check": None, "required": False},
        "updated_by":    {"check": None, "required": False},
    },
    "knowledge_chunks": {
        "document_id": {"check": None, "required": True},
        "chunk_text":  {"check": None, "required": True},
        "embedding":   {"check": None, "required": True},
        "metadata":    {"check": None, "required": False},
    },
}

# O mapa 1:1 que era qualification_data. Vive embutido no doc do lead como
# o mapa `qualification`; a lista existe para validação e para o enum de
# campos graváveis do tool update_qualification_field.
QUALIFICATION_FIELDS = (
    "segment_id", "segment_confidence", "segment_fields",
    "for_whom", "driver_name", "responsible_name", "driver_age", "origin",
    "contact_phone", "contact_email", "goal", "experience_level", "competes",
    "preferred_dates", "availability_window", "budget_signal",
    "desired_program_id", "desired_program_raw", "inferred_fields",
)


# =============================================================================
# VALIDAÇÃO DE ESCRITA — o CHECK, agora em código
# =============================================================================

class SchemaViolation(ValueError):
    """Uma escrita que o Postgres teria recusado. Recusada aqui também."""


def validate(collection: str, data: dict) -> None:
    """Confere enums e required antes de escrever. Chamado pelos caminhos de
    escrita (gates, sync, indexer) — não é opcional, é o que sobrou do CHECK."""
    spec = COLLECTIONS.get(collection)
    if spec is None:
        raise SchemaViolation(f"coleção desconhecida: {collection!r}")

    for field, rules in spec.items():
        value = data.get(field)
        if value is None:
            if rules["required"] and field not in data:
                # required = tem que vir na escrita de criação.
                raise SchemaViolation(
                    f"{collection}.{field} é obrigatório e não veio")
            continue
        allowed = rules["check"]
        if allowed and value not in allowed:
            raise SchemaViolation(
                f"{collection}.{field} = {value!r} não está em {allowed}")

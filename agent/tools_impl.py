"""
Tool implementations — where the guardrails become structural.

The prompt tells the agent not to volunteer a price. This layer makes it
impossible: when qualification is incomplete, get_program_details does not
return the number at all. The model cannot leak what it was never given.

Since the Firestore migration the enforcement itself lives in db/gates.py —
price shaping, the age-gate transaction and the escalation transaction. This
module is the tool surface the model sees; every consequential write goes
through the gates, never around them. Two rules are enforced structurally:

    price      withheld until qualification is complete and the driver asked
    handoff    programs marked handoff_* never return prices at all

A model that never receives a number cannot be talked into saying it.

The first parameter of every tool is the Firestore client (kept positional so
the orchestrator's execute() stays unchanged in shape).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Pure predicates — importable with no SDK installed (dry-run depends on it).
from db.policy import (  # noqa: E402
    REQUIRED_FOR_PRICE, REQUIRED_FOR_SCHEDULING,
    missing_fields, price_disclosure_allowed,
)

__all__ = ["REQUIRED_FOR_PRICE", "REQUIRED_FOR_SCHEDULING",
           "missing_fields", "price_disclosure_allowed",
           "REGISTRY", "execute"]


def _fs():
    """SDK imports, deferred: tools that touch the database import here, so
    --dry-run and the self-tests never need google-cloud-firestore."""
    from google.cloud import firestore
    from google.cloud.firestore_v1.base_query import FieldFilter
    return firestore, FieldFilter


# =============================================================================
# CATALOG
# =============================================================================

def get_program_details(db, ctx: dict, program_slug: str,
                        include_offers: bool = True) -> dict:
    snap = db.collection("programs").document(program_slug).get()
    if not snap.exists or snap.get("status") != "active":
        return {"status": "not_found",
                "note": "No active program with that slug. Do not describe it; "
                        "say you will confirm with the team."}

    p = snap.to_dict()
    program = {k: p.get(k) for k in (
        "slug", "name", "agent_action", "category", "description", "objective",
        "target_audience", "age_min", "age_max", "human_approval_below_age",
        "recommended_level", "prerequisites", "benefits", "differentiators")}
    program["slug"] = program.get("slug") or snap.id
    program["segment"] = p.get("segment_id")

    # An unfilled description is not a gap to paper over. Saying so explicitly
    # is more reliable than hoping the model infers it from a null.
    if not program["description"]:
        program["note"] = ("This program has no description in the catalog. "
                           "Do not describe it — say you will confirm the details.")

    if include_offers:
        from db import gates
        program["offers"] = gates.shape_offers(
            db, snap.id, program.get("agent_action") or "faq_only",
            ctx.get("qualification", {}), ctx.get("price_requested", False))
    return program


def search_knowledge_base(db, ctx: dict, query: str,
                          category: str | None = None) -> dict:
    """Retrieval with the threshold contract the FAQ mode depends on.

    Firestore native vector search: COSINE distance, so similarity is
    1 - distance — same scale the Postgres operator produced, same threshold.
    """
    from kb.embed import get_provider

    threshold = _config(db, "escalation", "rag_confidence_threshold", 0.72)
    try:
        provider = get_provider()
        vector = provider.embed([query], input_type="query")[0]
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc),
                "note": "Search failed. Do not answer from your own knowledge — "
                        "tell the driver you will confirm."}

    from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
    from google.cloud.firestore_v1.vector import Vector
    _, FieldFilter = _fs()

    coll = db.collection("knowledge_chunks")
    try:
        snaps = list(coll.find_nearest(
            vector_field="embedding",
            query_vector=Vector(vector),
            distance_measure=DistanceMeasure.COSINE,
            limit=5,
            distance_result_field="distance",
        ).stream())
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc),
                "note": "Search failed (vector index missing?). Do not answer "
                        "from your own knowledge — tell the driver you will "
                        "confirm."}

    hits = []
    for snap in snaps:
        row = snap.to_dict()
        meta = row.get("metadata") or {}
        distance = row.get("distance")
        similarity = 1.0 - float(distance) if distance is not None else 0.0
        if similarity < threshold:
            continue
        if category and meta.get("category") != category:
            continue
        hits.append({"text": row.get("chunk_text"),
                     "source": meta.get("title"),
                     "category": meta.get("category"),
                     "similarity": round(similarity, 3)})

    if not hits:
        return {"status": "no_match_above_threshold", "results": [],
                "note": "Nothing grounded was found. Say you will confirm with "
                        "the team. Do not reconstruct an answer."}
    return {"status": "ok", "results": hits}


# =============================================================================
# QUALIFICATION
# =============================================================================

WRITABLE_FIELDS = {
    "for_whom", "driver_name", "driver_age", "responsible_name", "origin",
    "contact_phone", "contact_email", "goal", "experience_level", "competes",
    "preferred_dates", "availability_window", "budget_signal", "segment",
}


def update_qualification_field(db, ctx: dict, lead_id: str, field: str,
                               value: str, source_excerpt: str | None = None,
                               inferred: bool = False) -> dict:
    if field not in WRITABLE_FIELDS:
        return {"status": "error", "error": f"'{field}' is not writable"}

    coerced = value
    if field == "driver_age":
        try:
            coerced = int(str(value).strip())
        except ValueError:
            return {"status": "error", "error": "driver_age must be a number"}
    if field == "competes":
        coerced = str(value).strip().lower() in ("true", "yes", "sim", "1")
    if field == "segment":
        # The value arrives as a slug; keep it only if the segment exists,
        # so a bad value never lands in the profile.
        if not db.collection("segments").document(str(value)).get().exists:
            return {"status": "error",
                    "error": f"no segment with slug {value!r}"}
        field = "segment_id"

    firestore, _ = _fs()
    updates = {f"qualification.{field}": coerced,
               "qualification.updated_at": firestore.SERVER_TIMESTAMP}
    if inferred:
        updates[f"qualification.inferred_fields"] = firestore.ArrayUnion([field])
    db.collection("leads").document(lead_id).set(
        _nest(updates), merge=True)

    ctx.setdefault("qualification", {})[field] = coerced
    remaining = missing_fields(ctx["qualification"], REQUIRED_FOR_PRICE)
    return {"status": "ok", "field": field,
            "qualification_complete": not remaining,
            "still_missing": remaining}


def _nest(dotted: dict) -> dict:
    """{'a.b': 1} -> {'a': {'b': 1}} — set(merge=True) needs real nesting,
    and update() (which accepts dots) fails on a lead created without the
    qualification map."""
    out: dict = {}
    for key, value in dotted.items():
        node = out
        parts = key.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return out


# =============================================================================
# SAFETY GATES — thin wrappers over db/gates.py
# =============================================================================

def request_human_approval(db, ctx: dict, lead_id: str, reason: str,
                           context: str, driver_age: int | None = None,
                           driver_experience: str | None = None,
                           requested_slot: str | None = None) -> dict:
    from db import gates
    approval_id = gates.request_approval(
        db, lead_id, reason, context, driver_age=driver_age,
        driver_experience=driver_experience, requested_slot=requested_slot)

    ctx["pending_approval"] = approval_id
    return {"status": "pending", "approval_id": approval_id,
            "note": "A human now owns this decision. Tell the driver the team "
                    "will confirm. Do not predict what they will decide."}


def create_calendar_event(db, ctx: dict, lead_id: str, start_time: str,
                          driver_phone: str, duration_minutes: int = 30,
                          notes: str | None = None) -> dict:
    """Refuses to book when the age gate is open.

    The gate transaction would refuse anyway. Checking here first means the
    agent gets a usable message instead of an exception, and learns why.
    """
    from db import gates

    approval = gates.latest_age_approval(db, lead_id)
    if approval and approval.get("status") != "approved":
        return {"status": "blocked",
                "reason": f"age clearance is {approval.get('status')}, "
                          f"not approved",
                "note": "You cannot book this driver yet. Tell them the team "
                        "will confirm. Do not suggest it will probably be fine."}

    gaps = missing_fields(ctx.get("qualification", {}), REQUIRED_FOR_SCHEDULING)
    if gaps:
        return {"status": "insufficient_data", "missing_fields": gaps,
                "note": "Keep qualifying instead of booking."}

    try:
        appt_id = gates.create_appointment(
            db, lead_id, closing_path="call_with_owner",
            scheduled_at=start_time, phone_collected=driver_phone,
            status="scheduled")
    except gates.GateRefusal as exc:
        return {"status": "blocked", "reason": str(exc),
                "note": "You cannot book this driver yet. Tell them the team "
                        "will confirm."}

    # Google Calendar is created by the scheduler service; the doc is the
    # record of intent. Confirming to the driver happens only after this
    # succeeds.
    return {"status": "created", "appointment_id": appt_id,
            "scheduled_at": start_time}


def check_calendar_availability(db, ctx: dict, date_range_start: str,
                                date_range_end: str,
                                driver_availability_window: str,
                                driver_timezone: str | None = None) -> dict:
    hours = _config(db, "business_hours", "support_hours", {})
    preferred = _config(db, "business_hours", "preferred_booking_days", [])
    start = datetime.fromisoformat(date_range_start.replace("Z", "+00:00"))
    end = datetime.fromisoformat(date_range_end.replace("Z", "+00:00"))

    slots, day = [], start
    while day <= end and len(slots) < 6:
        name = day.strftime("%A").lower()
        window = hours.get(name)
        if window and name in preferred:
            for hour in (10, 14, 16):
                open_h = int(window["open"][:2])
                close_h = int(window["close"][:2])
                if open_h <= hour < close_h:
                    slots.append(day.replace(hour=hour, minute=0,
                                             second=0, microsecond=0).isoformat())
        day += timedelta(days=1)

    return {"status": "ok" if slots else "no_slots",
            "slots": slots[:6],
            "driver_window": driver_availability_window,
            "note": "Offer two of these. Never ask an open-ended 'what day works'. "
                    "If none fit the driver's window, open a human approval "
                    "instead of forcing a time."}


# =============================================================================
# ESCALATION AND RECORD-KEEPING
# =============================================================================

def escalate_to_human(db, ctx: dict, lead_id: str, reason: str,
                      priority: str = "normal", briefing: str | None = None,
                      verbatim_quote: str | None = None) -> dict:
    from db import gates
    # The gate transaction is atomic: takeover, the escalation record and the
    # cancellation of pending follow-ups land together or not at all. No
    # automated message may reach someone who was escalated — least of all
    # someone who just disclosed a hardship.
    gates.escalate(db, lead_id, reason, triggered_by="ai", priority=priority,
                   briefing=briefing, verbatim_quote=verbatim_quote)

    ctx["escalated"] = True
    return {"status": "escalated",
            "note": "A human owns this conversation now. Send one closing "
                    "message and stop. Do not resume."}


def add_note(db, ctx: dict, lead_id: str, note: str) -> dict:
    _audit(db, lead_id, "note_added", {"note": note})
    return {"status": "ok"}


def create_kommo_task(db, ctx: dict, lead_id: str, task_type: str,
                      title: str, details: str | None = None,
                      due_at: str | None = None) -> dict:
    _audit(db, lead_id, "task_created",
           {"type": task_type, "title": title, "details": details,
            "due_at": due_at})
    # Kommo write happens in the CRM sync service; blocked on field IDs.
    return {"status": "queued", "task_type": task_type}


def get_lead_profile(db, ctx: dict, lead_id: str) -> dict:
    snap = db.collection("leads").document(lead_id).get()
    if not snap.exists:
        return {"status": "not_found"}
    lead = snap.to_dict()

    qual = ctx.get("qualification", {})
    return {
        "name": lead.get("name"),
        "channel": lead.get("primary_channel"),
        "status": lead.get("status"),
        "human_takeover": lead.get("human_takeover", False),
        "history_summary": lead.get("lead_master_summary"),
        "qualification": qual,
        "still_missing": missing_fields(qual, REQUIRED_FOR_PRICE),
    }


def log_decision(db, ctx: dict, lead_id: str, action: str,
                 reasoning: str, confidence: float | None = None) -> dict:
    _audit(db, lead_id, action, {"reasoning": reasoning},
           confidence=confidence)
    return {"status": "ok"}


def close_lead(db, ctx: dict, lead_id: str, reason: str) -> dict:
    firestore, _ = _fs()
    db.collection("leads").document(lead_id).update({
        "status": "closed", "close_reason": reason,
        "closed_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP})
    return {"status": "closed", "reason": reason}


def calculate_lead_score(db, ctx: dict, lead_id: str) -> dict:
    """Deterministic, from configured weights. The model triggers it; it never
    decides the number."""
    weights = _config(db, "scoring_rules", "weights", {})
    thresholds = _config(db, "scoring_rules", "thresholds",
                         {"hot": 70, "warm": 40})
    qual = ctx.get("qualification", {})

    breakdown, total = {}, 0
    scores = {
        "urgency": 1.0 if qual.get("preferred_dates") else 0.0,
        "budget_fit": 1.0 if qual.get("budget_signal") else 0.0,
        "program_defined": 1.0 if qual.get("segment") or qual.get("segment_id")
                           else 0.0,
        "driver_profile_fit": 1.0 if qual.get("driver_age") else 0.0,
        "engagement": min(ctx.get("turn_count", 0) / 6, 1.0),
        "scheduling_readiness": 1.0 if qual.get("availability_window") else 0.0,
    }
    for name, weight in weights.items():
        points = round(weight * scores.get(name, 0.0))
        breakdown[name] = points
        total += points

    classification = ("hot" if total >= thresholds["hot"]
                      else "warm" if total >= thresholds["warm"] else "cold")

    firestore, _ = _fs()
    from db import schema
    data = {"lead_id": lead_id, "score_total": total,
            "classification": classification, "criteria_breakdown": breakdown,
            "calculated_at": firestore.SERVER_TIMESTAMP}
    schema.validate("lead_scores", data)
    db.collection("lead_scores").document().create(data)
    return {"score_total": total, "classification": classification,
            "breakdown": breakdown}


def get_program_recommendation(db, ctx: dict, lead_id: str) -> dict:
    """Placeholder until the recommendation engine lands.

    Returning insufficient_data is the honest answer and the safe one: it makes
    the agent keep qualifying rather than guess, which is exactly what the
    engine will tell it to do for an incomplete profile anyway.
    """
    qual = ctx.get("qualification", {})
    gaps = missing_fields(qual, REQUIRED_FOR_PRICE)
    if gaps:
        return {"status": "insufficient_data", "missing_fields": gaps}
    return {"status": "insufficient_data", "missing_fields": [],
            "note": "The recommendation engine is not implemented yet. Do not "
                    "recommend a program; keep the conversation going and "
                    "escalate if the driver asks which program suits them."}


# =============================================================================
# REGISTRY
# =============================================================================

REGISTRY = {
    "get_program_details": get_program_details,
    "search_knowledge_base": search_knowledge_base,
    "get_program_recommendation": get_program_recommendation,
    "update_qualification_field": update_qualification_field,
    "calculate_lead_score": calculate_lead_score,
    "check_calendar_availability": check_calendar_availability,
    "create_calendar_event": create_calendar_event,
    "create_kommo_task": create_kommo_task,
    "request_human_approval": request_human_approval,
    "escalate_to_human": escalate_to_human,
    "add_note": add_note,
    "get_lead_profile": get_lead_profile,
    "close_lead": close_lead,
    "log_decision": log_decision,
}


def execute(db, ctx: dict, name: str, args: dict) -> dict:
    fn = REGISTRY.get(name)
    if not fn:
        return {"status": "error", "error": f"unknown tool '{name}'"}
    try:
        return fn(db, ctx, **args)
    except TypeError as exc:
        return {"status": "error", "error": f"bad arguments: {exc}"}
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def _audit(db, lead_id: str, action: str, details: dict,
           confidence: float | None = None, actor: str = "ai"):
    firestore, _ = _fs()
    db.collection("audit_logs").document().create({
        "lead_id": lead_id, "actor": actor, "action": action,
        "details": details, "confidence": confidence,
        "created_at": firestore.SERVER_TIMESTAMP})


def _config(db, category: str, key: str, default):
    snap = db.collection("configurations").document(category).get()
    if not snap.exists:
        return default
    value = snap.to_dict().get(key)
    return default if value is None else value

"""
Tool implementations — where the guardrails become structural.

The prompt tells the agent not to volunteer a price. This layer makes it
impossible: when qualification is incomplete, get_program_details does not
return the number at all. The model cannot leak what it was never given.

That is the same reasoning as the database trigger on the age gate. Everything
above — prompt, mode, recommendation engine — can drift, be reworded, or be
mutated. These cannot. Two rules are enforced here rather than asked for:

    price      withheld until qualification is complete and the driver asked
    handoff    programs marked handoff_to_owner never return prices at all

A model that never receives a number cannot be talked into saying it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any


# =============================================================================
# GATE STATE
# =============================================================================

REQUIRED_FOR_PRICE = [
    "for_whom", "driver_age", "origin", "goal", "experience_level",
]

REQUIRED_FOR_SCHEDULING = [
    "driver_name", "driver_age", "origin", "contact_phone", "availability_window",
]


def missing_fields(qual: dict, required: list[str]) -> list[str]:
    return [f for f in required if not qual.get(f)]


def price_disclosure_allowed(qual: dict, price_requested: bool) -> tuple[bool, str]:
    """Both conditions, evaluated in code. Neither is the model's judgement."""
    if not price_requested:
        return False, "the driver has not asked for a price"
    gaps = missing_fields(qual, REQUIRED_FOR_PRICE)
    if gaps:
        return False, f"qualification incomplete: missing {', '.join(gaps)}"
    return True, "qualification complete and the driver asked"


# =============================================================================
# CATALOG
# =============================================================================

def get_program_details(conn, ctx: dict, program_slug: str,
                        include_offers: bool = True) -> dict:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.slug, p.name, p.agent_action, p.category, p.description,
                   p.objective, p.target_audience, p.age_min, p.age_max,
                   p.human_approval_below_age, p.recommended_level,
                   p.prerequisites, p.benefits, p.differentiators, s.slug
            FROM programs p
            LEFT JOIN segments s ON s.id = p.segment_id
            WHERE p.slug = %s AND p.status = 'active'
        """, (program_slug,))
        row = cur.fetchone()

    if not row:
        return {"status": "not_found",
                "note": "No active program with that slug. Do not describe it; "
                        "say you will confirm with the team."}

    keys = ["slug", "name", "agent_action", "category", "description", "objective",
            "target_audience", "age_min", "age_max", "human_approval_below_age",
            "recommended_level", "prerequisites", "benefits", "differentiators",
            "segment"]
    program: dict[str, Any] = dict(zip(keys, row))

    # An unfilled description is not a gap to paper over. Saying so explicitly
    # is more reliable than hoping the model infers it from a null.
    if not program["description"]:
        program["note"] = ("This program has no description in the catalog. "
                           "Do not describe it — say you will confirm the details.")

    if include_offers:
        program["offers"] = _offers_for(conn, ctx, program_slug,
                                        program["agent_action"])
    return program


def _offers_for(conn, ctx: dict, slug: str, agent_action: str) -> list[dict]:
    """Prices, withheld structurally when they must not be said."""
    allowed, reason = price_disclosure_allowed(
        ctx.get("qualification", {}), ctx.get("price_requested", False))

    # A driver being handed to the owner is never quoted, regardless of how
    # complete their qualification is. That conversation belongs to a person.
    if agent_action == "handoff_to_owner":
        allowed, reason = False, "this program is handled by the owner, not by you"

    with conn.cursor() as cur:
        cur.execute("""
            SELECT offer_id, offer_name, context, description, price_amount,
                   price_currency, price_unit, price_is_indicative,
                   price_variance_note, conditions_note, agent_can_quote
            FROM program_offers o
            JOIN programs p ON p.id = o.program_id
            WHERE p.slug = %s AND o.status = 'active'
            ORDER BY o.price_amount NULLS LAST
        """, (slug,))
        rows = cur.fetchall()

    out = []
    for r in rows:
        offer = {
            "offer_id": r[0], "offer_name": r[1], "context": r[2],
            "description": r[3], "conditions_note": r[9],
        }
        quotable = r[10]

        if not allowed:
            offer["price"] = None
            offer["price_withheld_because"] = reason
        elif not quotable:
            offer["price"] = None
            offer["price_withheld_because"] = (
                "this rate exists but only the track operator may offer it — "
                "you know it so you are not confused if the driver mentions it, "
                "and you never state the figure")
        else:
            offer["price"] = float(r[4]) if r[4] is not None else None
            offer["currency"] = r[5]
            offer["unit"] = r[6]
            offer["is_indicative"] = r[7]
            offer["variance_note"] = r[8]
            offer["must_add"] = ("track fees are paid directly to Orlando Kart "
                                 "Center and are not included")
        out.append(offer)
    return out


def search_knowledge_base(conn, ctx: dict, query: str,
                          category: str | None = None) -> dict:
    """Retrieval with the threshold contract the FAQ mode depends on."""
    from kb.embed import get_provider

    threshold = _config(conn, "escalation", "rag_confidence_threshold", 0.72)
    try:
        provider = get_provider()
        vector = provider.embed([query], input_type="query")[0]
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc),
                "note": "Search failed. Do not answer from your own knowledge — "
                        "tell the driver you will confirm."}

    filters, params = "", [vector]
    if category:
        filters = " AND kd.category = %s"
        params.append(category)
    params.append(vector)

    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT kc.chunk_text, kd.title, kd.category,
                   1 - (kc.embedding <=> %s::vector) AS similarity
            FROM knowledge_chunks kc
            JOIN knowledge_documents kd ON kd.id = kc.document_id
            WHERE kd.status = 'active'{filters}
            ORDER BY kc.embedding <=> %s::vector
            LIMIT 5
        """, params)
        rows = cur.fetchall()

    hits = [{"text": r[0], "source": r[1], "category": r[2],
             "similarity": round(float(r[3]), 3)}
            for r in rows if float(r[3]) >= threshold]

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


def update_qualification_field(conn, ctx: dict, lead_id: str, field: str,
                               value: str, source_excerpt: str | None = None,
                               inferred: bool = False) -> dict:
    if field not in WRITABLE_FIELDS:
        return {"status": "error", "error": f"'{field}' is not writable"}

    coerced: Any = value
    if field == "driver_age":
        try:
            coerced = int(str(value).strip())
        except ValueError:
            return {"status": "error", "error": f"driver_age must be a number"}
    if field == "competes":
        coerced = str(value).strip().lower() in ("true", "yes", "1")

    with conn.cursor() as cur:
        cur.execute(f"""
            INSERT INTO qualification_data (lead_id, {field})
            VALUES (%s, %s)
            ON CONFLICT (lead_id) DO UPDATE SET {field} = EXCLUDED.{field},
                                                updated_at = now()
        """, (lead_id, coerced))
        if inferred:
            cur.execute("""
                UPDATE qualification_data
                SET inferred_fields = array_append(
                    array_remove(inferred_fields, %s), %s)
                WHERE lead_id = %s
            """, (field, field, lead_id))

    ctx.setdefault("qualification", {})[field] = coerced
    remaining = missing_fields(ctx["qualification"], REQUIRED_FOR_PRICE)
    return {"status": "ok", "field": field,
            "qualification_complete": not remaining,
            "still_missing": remaining}


# =============================================================================
# SAFETY GATES
# =============================================================================

def request_human_approval(conn, ctx: dict, lead_id: str, reason: str,
                           context: str, driver_age: int | None = None,
                           driver_experience: str | None = None,
                           requested_slot: str | None = None) -> dict:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO human_approvals
                (lead_id, reason, driver_age, driver_experience,
                 requested_slot, context)
            VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
        """, (lead_id, reason, driver_age, driver_experience,
              requested_slot, context))
        approval_id = cur.fetchone()[0]

    ctx["pending_approval"] = str(approval_id)
    return {"status": "pending", "approval_id": str(approval_id),
            "note": "A human now owns this decision. Tell the driver the team "
                    "will confirm. Do not predict what they will decide."}


def create_calendar_event(conn, ctx: dict, lead_id: str, start_time: str,
                          driver_phone: str, duration_minutes: int = 30,
                          notes: str | None = None) -> dict:
    """Refuses to book when the age gate is open.

    The database trigger would refuse this anyway. Refusing here too means the
    agent gets a usable message instead of a transaction error, and learns why.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT status FROM human_approvals
            WHERE lead_id = %s AND reason = 'age_below_track_minimum'
            ORDER BY requested_at DESC LIMIT 1
        """, (lead_id,))
        row = cur.fetchone()

    if row and row[0] != "approved":
        return {"status": "blocked",
                "reason": f"age clearance is {row[0]}, not approved",
                "note": "You cannot book this driver yet. Tell them the team "
                        "will confirm. Do not suggest it will probably be fine."}

    gaps = missing_fields(ctx.get("qualification", {}), REQUIRED_FOR_SCHEDULING)
    if gaps:
        return {"status": "insufficient_data", "missing_fields": gaps,
                "note": "Keep qualifying instead of booking."}

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO appointments
                (lead_id, closing_path, scheduled_at, status, phone_collected)
            VALUES (%s, 'call_with_owner', %s, 'scheduled', %s)
            RETURNING id
        """, (lead_id, start_time, driver_phone))
        appt = cur.fetchone()[0]

    # Google Calendar is created by the scheduler service; the row is the record
    # of intent. Confirming to the driver happens only after this succeeds.
    return {"status": "created", "appointment_id": str(appt),
            "scheduled_at": start_time}


def check_calendar_availability(conn, ctx: dict, date_range_start: str,
                                date_range_end: str,
                                driver_availability_window: str,
                                driver_timezone: str | None = None) -> dict:
    hours = _config(conn, "business_hours", "support_hours", {})
    preferred = _config(conn, "business_hours", "preferred_booking_days", [])
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

def escalate_to_human(conn, ctx: dict, lead_id: str, reason: str,
                      priority: str = "normal", briefing: str | None = None,
                      verbatim_quote: str | None = None) -> dict:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO escalations
                (lead_id, reason, triggered_by, priority, briefing, verbatim_quote)
            VALUES (%s,%s,'ai',%s,%s,%s)
        """, (lead_id, reason, priority, briefing, verbatim_quote))
        cur.execute(
            "UPDATE leads SET human_takeover = TRUE, status = 'escalated' "
            "WHERE id = %s", (lead_id,))
        # No automated message may reach someone who was escalated — least of
        # all someone who just disclosed a hardship.
        cur.execute(
            "UPDATE follow_ups SET status = 'cancelled', "
            "skip_reason = %s WHERE lead_id = %s AND status = 'pending'",
            (f"escalated: {reason}", lead_id))

    ctx["escalated"] = True
    return {"status": "escalated",
            "note": "A human owns this conversation now. Send one closing "
                    "message and stop. Do not resume."}


def add_note(conn, ctx: dict, lead_id: str, note: str) -> dict:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO audit_logs (lead_id, actor, action, details)
            VALUES (%s, 'ai', 'note_added', %s)
        """, (lead_id, json.dumps({"note": note})))
    return {"status": "ok"}


def create_kommo_task(conn, ctx: dict, lead_id: str, task_type: str,
                      title: str, details: str | None = None,
                      due_at: str | None = None) -> dict:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO audit_logs (lead_id, actor, action, details)
            VALUES (%s, 'ai', 'task_created', %s)
        """, (lead_id, json.dumps({"type": task_type, "title": title,
                                   "details": details, "due_at": due_at})))
    # Kommo write happens in the CRM sync service; blocked on field IDs.
    return {"status": "queued", "task_type": task_type}


def get_lead_profile(conn, ctx: dict, lead_id: str) -> dict:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT l.name, l.primary_channel, l.status, l.human_takeover,
                   l.lead_master_summary
            FROM leads l WHERE l.id = %s
        """, (lead_id,))
        row = cur.fetchone()
    if not row:
        return {"status": "not_found"}

    qual = ctx.get("qualification", {})
    return {
        "name": row[0], "channel": row[1], "status": row[2],
        "human_takeover": row[3], "history_summary": row[4],
        "qualification": qual,
        "still_missing": missing_fields(qual, REQUIRED_FOR_PRICE),
    }


def log_decision(conn, ctx: dict, lead_id: str, action: str,
                 reasoning: str, confidence: float | None = None) -> dict:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO audit_logs (lead_id, actor, action, details, confidence)
            VALUES (%s, 'ai', %s, %s, %s)
        """, (lead_id, action, json.dumps({"reasoning": reasoning}), confidence))
    return {"status": "ok"}


def close_lead(conn, ctx: dict, lead_id: str, reason: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE leads SET status = 'closed', close_reason = %s, "
            "closed_at = now() WHERE id = %s", (reason, lead_id))
    return {"status": "closed", "reason": reason}


def calculate_lead_score(conn, ctx: dict, lead_id: str) -> dict:
    """Deterministic, from configured weights. The model triggers it; it never
    decides the number."""
    weights = _config(conn, "scoring_rules", "weights", {})
    thresholds = _config(conn, "scoring_rules", "thresholds",
                         {"hot": 70, "warm": 40})
    qual = ctx.get("qualification", {})

    breakdown, total = {}, 0
    scores = {
        "urgency": 1.0 if qual.get("preferred_dates") else 0.0,
        "budget_fit": 1.0 if qual.get("budget_signal") else 0.0,
        "program_defined": 1.0 if qual.get("segment") else 0.0,
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
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO lead_scores (lead_id, score_total, classification,
                                     criteria_breakdown)
            VALUES (%s,%s,%s,%s)
        """, (lead_id, total, classification, json.dumps(breakdown)))
    return {"score_total": total, "classification": classification,
            "breakdown": breakdown}


def get_program_recommendation(conn, ctx: dict, lead_id: str) -> dict:
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


def execute(conn, ctx: dict, name: str, args: dict) -> dict:
    fn = REGISTRY.get(name)
    if not fn:
        return {"status": "error", "error": f"unknown tool '{name}'"}
    try:
        return fn(conn, ctx, **args)
    except TypeError as exc:
        return {"status": "error", "error": f"bad arguments: {exc}"}
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def _config(conn, category: str, key: str, default):
    with conn.cursor() as cur:
        cur.execute("SELECT value FROM configurations WHERE category=%s AND key=%s",
                    (category, key))
        row = cur.fetchone()
    return row[0] if row else default

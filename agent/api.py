#!/usr/bin/env python3
"""
HTTP API — the seam between n8n and the agent.

n8n is transport: it receives from Kommo, calls this, returns the reply. The
agent stays here, which is the whole point — and since the Firestore migration
this service is the ONLY writer. The gates (price, age, escalation) run in
db/gates.py inside Firestore transactions; n8n never touches the database.
A prompt-only workflow cannot withhold a price the model already has.

    POST /message   {sessionId, channel, text, contact}  ->  {output, ...}
    GET  /health

Run:
    uvicorn agent.api:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import tools_impl as tools  # noqa: E402
from orchestrator import load_context, run_turn, persist  # noqa: E402

app = FastAPI(title="URace Sales Agent")

_client = None
_db = None


class Inbound(BaseModel):
    sessionId: str = Field(..., description="Stable per-conversation key.")
    text: str
    channel: str = "whatsapp"
    contact_name: str | None = None
    contact_phone: str | None = None
    kommo_lead_id: int | None = None


class Outbound(BaseModel):
    output: str
    sessionId: str
    mode: str | None = None
    tools_used: list[str] = []
    escalated: bool = False
    error: bool = False


# The agent must never improvise a reply when the turn failed. A driver reading
# half a sentence, or a fabricated one, is worse than a driver waiting.
FALLBACK = ("Sorry, something went wrong on my end. Someone from the team will "
            "pick this up shortly.")


def _startup():
    global _client, _db
    if _client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
        import anthropic
        from db.client import get_db
        _client = anthropic.Anthropic()
        _db = get_db()
    return _db


def _resolve_lead(db, payload: Inbound) -> tuple[str, str]:
    """Find or create the lead and its open conversation.

    Identity is the channel handle, not the session key: the same person
    reaching out on WhatsApp and then by email is one lead, and treating them
    as two is how an agent ends up asking a driver questions they already
    answered.

    The contact doc ID encodes UNIQUE(channel, external_id): create() on an
    existing ID fails, so two concurrent first messages cannot mint two leads.
    """
    from google.cloud import firestore
    from db.client import contact_id

    external = payload.contact_phone or payload.sessionId
    contact_ref = db.collection("contacts").document(
        contact_id(payload.channel, external))
    contact = contact_ref.get()

    if contact.exists:
        lead_id = contact.get("lead_id")
    else:
        lead_ref = db.collection("leads").document()
        lead_ref.create({
            "kommo_lead_id": payload.kommo_lead_id
                             or abs(hash(external)) % 10_000_000,
            "name": payload.contact_name,
            "primary_channel": payload.channel,
            "preferred_language": "en",
            "lead_source": "n8n",
            "status": "active",
            "human_takeover": False,
            "qualification": {},
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
        lead_id = lead_ref.id
        try:
            contact_ref.create({
                "lead_id": lead_id, "channel": payload.channel,
                "external_id": external,
                "display_name": payload.contact_name,
            })
        except Exception:
            # Lost the race: another request created the contact first.
            # Their lead wins; ours stays orphaned rather than duplicating
            # the person.
            lead_id = contact_ref.get().get("lead_id")

    from google.cloud.firestore_v1.base_query import FieldFilter
    open_convs = list(
        db.collection("conversations")
        .where(filter=FieldFilter("lead_id", "==", lead_id))
        .where(filter=FieldFilter("ended_at", "==", None))
        .order_by("started_at", direction=firestore.Query.DESCENDING)
        .limit(1).stream())

    if open_convs:
        conversation_id = open_convs[0].id
    else:
        conv_ref = db.collection("conversations").document()
        conv_ref.create({"lead_id": lead_id, "channel": payload.channel,
                         "started_at": firestore.SERVER_TIMESTAMP,
                         "ended_at": None})
        conversation_id = conv_ref.id

    return lead_id, conversation_id


def _history(db, conversation_id: str) -> list[dict]:
    """Replay from the database rather than trusting n8n's memory node.

    Two reasons. The transcript has to survive an n8n restart, and it has to be
    the same history the audit trail shows — a memory that lives only in the
    workflow can diverge from what was recorded without anyone noticing.
    """
    snaps = (db.collection("conversations").document(conversation_id)
             .collection("messages").order_by("created_at").stream())
    rows = [(s.get("sender_type"), s.get("content")) for s in snaps]
    return [{"role": "user" if s == "lead" else "assistant", "content": c}
            for s, c in rows[-12:]]


@app.get("/health")
def health():
    try:
        db = _startup()
        from google.cloud.firestore_v1.base_query import FieldFilter
        programs = len(list(
            db.collection("programs")
            .where(filter=FieldFilter("status", "==", "active"))
            .select([]).stream()))
        return {"status": "ok", "active_programs": programs}
    except Exception as exc:
        raise HTTPException(503, f"unhealthy: {exc}")


@app.post("/message", response_model=Outbound)
def message(payload: Inbound, x_api_key: str | None = Header(default=None)):
    expected = os.environ.get("AGENT_API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(401, "bad or missing X-Api-Key")

    db = _startup()
    lead_id, conversation_id = _resolve_lead(db, payload)
    ctx = load_context(db, lead_id)

    # A human owning the conversation outranks everything. The agent does
    # not get a turn, and n8n is told to stay silent rather than being
    # handed a message to send.
    if ctx["human_takeover"]:
        return Outbound(output="", sessionId=payload.sessionId,
                        mode="human_takeover", escalated=True)

    history = _history(db, conversation_id)
    persist(db, ctx, conversation_id, "user", payload.text)

    try:
        result = run_turn(_client, db, ctx, history, payload.text)
    except Exception as exc:
        # Firestore writes are per-document; there is no transaction to roll
        # back here. The audit row records the failed turn, and the driver
        # gets the fallback — never half a sentence.
        try:
            from google.cloud import firestore
            db.collection("audit_logs").document().create({
                "lead_id": lead_id, "actor": "system",
                "action": "turn_failed",
                "details": {"error": type(exc).__name__},
                "created_at": firestore.SERVER_TIMESTAMP})
        except Exception:
            pass
        return Outbound(output=FALLBACK, sessionId=payload.sessionId,
                        error=True)

    if result.get("error") or not result.get("text"):
        return Outbound(output=FALLBACK, sessionId=payload.sessionId,
                        mode=result.get("mode"), error=True)

    persist(db, ctx, conversation_id, "assistant",
            result["text"], result["mode"])

    return Outbound(output=result["text"], sessionId=payload.sessionId,
                    mode=result["mode"], tools_used=result.get("tools", []),
                    escalated=ctx.get("escalated", False))

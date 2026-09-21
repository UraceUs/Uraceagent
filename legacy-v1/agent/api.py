#!/usr/bin/env python3
"""
HTTP API — the seam between n8n and the agent.

n8n is transport: it receives from Kommo, calls this, returns the reply. The
agent stays here, which is the whole point. Rebuilding the conversation inside
n8n's LangChain node would mean reimplementing fourteen tools as n8n nodes and
losing the deterministic router — and with them the structural gates. A
prompt-only workflow cannot withhold a price the model already has.

    POST /message   {sessionId, channel, text, contact}  ->  {output, ...}
    GET  /health

Run:
    uvicorn agent.api:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
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
_pool = None


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
    global _client, _pool
    if _client is None:
        if not os.environ.get("DATABASE_URL"):
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
        import anthropic
        from psycopg_pool import ConnectionPool
        _client = anthropic.Anthropic()
        _pool = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=8)


@contextmanager
def _conn():
    _startup()
    with _pool.connection() as conn:
        yield conn


def _resolve_lead(conn, payload: Inbound) -> tuple[str, str]:
    """Find or create the lead and its open conversation.

    Identity is the channel handle, not the session key: the same person
    reaching out on WhatsApp and then by email is one lead, and treating them
    as two is how an agent ends up asking a driver questions they already
    answered.
    """
    with conn.cursor() as cur:
        external = payload.contact_phone or payload.sessionId
        cur.execute("""
            SELECT lead_id FROM contacts WHERE channel = %s AND external_id = %s
        """, (payload.channel, external))
        row = cur.fetchone()

        if row:
            lead_id = str(row[0])
        else:
            cur.execute("""
                INSERT INTO leads (kommo_lead_id, name, primary_channel, lead_source)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (kommo_lead_id) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
            """, (payload.kommo_lead_id or abs(hash(external)) % 10_000_000,
                  payload.contact_name, payload.channel, "n8n"))
            lead_id = str(cur.fetchone()[0])
            cur.execute("""
                INSERT INTO contacts (lead_id, channel, external_id, display_name)
                VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING
            """, (lead_id, payload.channel, external, payload.contact_name))

        cur.execute("""
            SELECT id FROM conversations
            WHERE lead_id = %s AND ended_at IS NULL
            ORDER BY started_at DESC LIMIT 1
        """, (lead_id,))
        row = cur.fetchone()
        if row:
            conversation_id = str(row[0])
        else:
            cur.execute("""
                INSERT INTO conversations (lead_id, channel) VALUES (%s,%s)
                RETURNING id
            """, (lead_id, payload.channel))
            conversation_id = str(cur.fetchone()[0])

    return lead_id, conversation_id


def _history(conn, conversation_id: str) -> list[dict]:
    """Replay from the database rather than trusting n8n's memory node.

    Two reasons. The transcript has to survive an n8n restart, and it has to be
    the same history the audit trail shows — a memory that lives only in the
    workflow can diverge from what was recorded without anyone noticing.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT sender_type, content FROM messages
            WHERE conversation_id = %s ORDER BY created_at
        """, (conversation_id,))
        rows = cur.fetchall()
    return [{"role": "user" if s == "lead" else "assistant", "content": c}
            for s, c in rows[-12:]]


@app.get("/health")
def health():
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM programs WHERE status='active'")
                programs = cur.fetchone()[0]
        return {"status": "ok", "active_programs": programs}
    except Exception as exc:
        raise HTTPException(503, f"unhealthy: {exc}")


@app.post("/message", response_model=Outbound)
def message(payload: Inbound, x_api_key: str | None = Header(default=None)):
    expected = os.environ.get("AGENT_API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(401, "bad or missing X-Api-Key")

    with _conn() as conn:
        lead_id, conversation_id = _resolve_lead(conn, payload)
        ctx = load_context(conn, lead_id)

        # A human owning the conversation outranks everything. The agent does
        # not get a turn, and n8n is told to stay silent rather than being
        # handed a message to send.
        if ctx["human_takeover"]:
            conn.commit()
            return Outbound(output="", sessionId=payload.sessionId,
                            mode="human_takeover", escalated=True)

        history = _history(conn, conversation_id)
        persist(conn, ctx, conversation_id, "user", payload.text)

        try:
            result = run_turn(_client, conn, ctx, history, payload.text)
        except Exception as exc:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO audit_logs (lead_id, actor, action, details)
                    VALUES (%s,'system','turn_failed',%s)
                """, (lead_id, f'{{"error": "{type(exc).__name__}"}}'))
            conn.commit()
            return Outbound(output=FALLBACK, sessionId=payload.sessionId,
                            error=True)

        if result.get("error") or not result.get("text"):
            conn.commit()
            return Outbound(output=FALLBACK, sessionId=payload.sessionId,
                            mode=result.get("mode"), error=True)

        persist(conn, ctx, conversation_id, "assistant",
                result["text"], result["mode"])
        conn.commit()

        return Outbound(output=result["text"], sessionId=payload.sessionId,
                        mode=result["mode"], tools_used=result.get("tools", []),
                        escalated=ctx.get("escalated", False))

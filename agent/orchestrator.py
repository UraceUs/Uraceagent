#!/usr/bin/env python3
"""
Orchestrator — the agent.

Everything else built so far supports this: prompts, catalog, knowledge base,
schema, gates. This is the loop that turns them into something a driver can
talk to.

    inbound  ->  load context  ->  route mode  ->  compose prompt
             ->  call Claude with that mode's tools
             ->  execute tool calls, feed results back
             ->  outbound message, persisted

Mode routing is deterministic. The model does not choose which prompt governs
it — that would let a conversation talk its way out of the escalation mode.

Usage:
    python agent/orchestrator.py --repl              # talk to it in the terminal
    python agent/orchestrator.py --repl --lead <id>  # resume a lead
    python agent/orchestrator.py --dry-run           # route and compose, no API
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "prompts"))   # compose.py mora lá

from compose import compose  # noqa: E402
import tools_impl as tools  # noqa: E402

MODEL = "claude-sonnet-5"
MAX_TOOL_ROUNDS = 6


# =============================================================================
# MODE ROUTING — rules, not the model's choice
# =============================================================================

def route(ctx: dict, message: str) -> str:
    """Which prompt governs this turn.

    Order is precedence, and it is deliberate: escalation outranks everything,
    because a conversation that has been handed to a human must not be able to
    route itself back into selling.
    """
    if ctx.get("escalated") or ctx.get("human_takeover"):
        return "escalation"

    qual = ctx.get("qualification", {})
    text = message.lower()

    # Hard triggers. Checked in code so the model cannot reason past them.
    if any(w in text for w in ("discount", "desconto", "refund", "reembolso",
                               "cancel", "complaint", "reclamação", "manager",
                               "lawyer", "speak to a human", "falar com humano")):
        return "escalation"

    # A driver who races is the owner's conversation, not a sale.
    if qual.get("competes") is True:
        return "escalation"

    if ctx.get("follow_up_attempt"):
        return "followup"

    # Scheduling once the driver signals readiness and there is enough to book.
    ready = not tools.missing_fields(qual, tools.REQUIRED_FOR_SCHEDULING)
    booking_intent = any(w in text for w in ("book", "schedule", "agendar",
                                             "marcar", "reservar", "call",
                                             "available", "when can"))
    if booking_intent and (ready or qual.get("driver_age") is not None):
        return "scheduling"

    # Questions get FAQ; everything else keeps qualifying.
    if "?" in message or text.startswith(("how", "what", "when", "where", "does",
                                          "is ", "can ", "quanto", "como",
                                          "qual", "onde")):
        return "faq"

    return "qualification"


def detect_price_request(message: str) -> bool:
    text = message.lower()
    return any(w in text for w in ("price", "cost", "how much", "quanto custa",
                                   "valor", "preço", "preco", "precio",
                                   "rate", "fee", "$"))


# =============================================================================
# CONTEXT
# =============================================================================

def load_context(db, lead_id: str) -> dict:
    snap = db.collection("leads").document(lead_id).get()
    if not snap.exists:
        raise SystemExit(f"lead {lead_id} not found")
    lead = snap.to_dict()

    # A qualificação vive embutida no doc do lead (mapa `qualification`) —
    # uma leitura traz tudo que o roteamento precisa, atomicamente.
    qual = {k: v for k, v in (lead.get("qualification") or {}).items()
            if v is not None and k != "updated_at"}

    return {
        "lead_id": lead_id,
        "lead_name": lead.get("name"),
        "channel": lead.get("primary_channel") or "whatsapp",
        "detected_language": lead.get("preferred_language") or "en",
        "lead_status": lead.get("status"),
        "human_takeover": lead.get("human_takeover", False),
        "lead_master_summary": lead.get("lead_master_summary"),
        "qualification": qual,
        "price_requested": False,
        "turn_count": 0,
        "escalated": lead.get("status") == "escalated",
    }


def render_context(ctx: dict, history: list) -> dict:
    """Flatten into the placeholders 01_context_template.md expects."""
    qual = ctx["qualification"]
    gaps = tools.missing_fields(qual, tools.REQUIRED_FOR_PRICE)
    recent = "\n".join(
        f"{'Driver' if m['role'] == 'user' else 'Agent'}: "
        f"{m['content'] if isinstance(m['content'], str) else '[tool use]'}"
        for m in history[-8:])

    flags = []
    if ctx.get("pending_approval"):
        flags.append("pending_human_approval")
    if ctx.get("escalated"):
        flags.append("escalated")

    return {
        "channel": ctx["channel"],
        "detected_language": ctx["detected_language"],
        "lead_name": ctx.get("lead_name"),
        "lead_status": ctx["lead_status"],
        "human_takeover": str(ctx["human_takeover"]),
        "lead_master_summary": ctx.get("lead_master_summary"),
        "for_whom": qual.get("for_whom"),
        "driver_age": qual.get("driver_age"),
        "origin": qual.get("origin"),
        "contact": qual.get("contact_phone") or qual.get("contact_email"),
        "goal": qual.get("goal"),
        "experience": qual.get("experience_level"),
        "segment": qual.get("segment"),
        "missing_fields": ", ".join(gaps) if gaps else None,
        "qualification_complete": str(not gaps).lower(),
        "price_requested": str(ctx["price_requested"]).lower(),
        "recent_messages": recent or "(first message)",
        "flags": ", ".join(flags) if flags else None,
    }


# =============================================================================
# THE TURN
# =============================================================================

def run_turn(client, db, ctx: dict, history: list, message: str,
             verbose: bool = False) -> dict:
    ctx["turn_count"] += 1
    if detect_price_request(message):
        ctx["price_requested"] = True

    mode = route(ctx, message)
    prompt, tool_defs = compose(mode, render_context(ctx, history))
    history.append({"role": "user", "content": message})

    if verbose:
        print(f"    [mode: {mode}, tools: {len(tool_defs)}]")

    calls_made: list[str] = []
    for round_num in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=MODEL, max_tokens=1024, system=prompt,
            tools=tool_defs, messages=history)

        history.append({"role": "assistant", "content": response.content})
        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if not tool_uses:
            text = "".join(b.text for b in response.content if b.type == "text")
            return {"text": text.strip(), "mode": mode, "tools": calls_made}

        results = []
        for use in tool_uses:
            args = dict(use.input)
            args.setdefault("lead_id", ctx["lead_id"])
            calls_made.append(use.name)
            if verbose:
                print(f"    [tool: {use.name}]")
            result = tools.execute(db, ctx, use.name, args)
            results.append({"type": "tool_result", "tool_use_id": use.id,
                            "content": json.dumps(result, default=str)})
        history.append({"role": "user", "content": results})

    # Hitting the ceiling means the agent is looping. Say so rather than
    # presenting whatever the last partial output happened to be.
    return {"text": None, "mode": mode, "tools": calls_made,
            "error": f"exceeded {MAX_TOOL_ROUNDS} tool rounds"}


def persist(db, ctx: dict, conversation_id: str, role: str, text: str,
            mode: str | None = None):
    from google.cloud import firestore
    db.collection("conversations").document(conversation_id) \
      .collection("messages").document().create({
          "conversation_id": conversation_id,
          "sender_type": "lead" if role == "user" else "ai",
          "content": text,
          "mode": mode,
          "created_at": firestore.SERVER_TIMESTAMP,
      })


# =============================================================================
# REPL
# =============================================================================

def ensure_lead(db, lead_id: str | None) -> tuple[str, str]:
    from google.cloud import firestore

    if lead_id:
        if not db.collection("leads").document(lead_id).get().exists:
            raise SystemExit(f"lead {lead_id} not found")
    else:
        kommo_id = int(uuid.uuid4().int % 10_000_000)
        lead_ref = db.collection("leads").document()
        lead_ref.create({
            "kommo_lead_id": kommo_id, "name": None,
            "primary_channel": "whatsapp", "lead_source": "repl",
            "preferred_language": "en", "status": "active",
            "human_takeover": False, "qualification": {},
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
        lead_id = lead_ref.id

    conv_ref = db.collection("conversations").document()
    conv_ref.create({"lead_id": lead_id, "channel": "whatsapp",
                     "started_at": firestore.SERVER_TIMESTAMP,
                     "ended_at": None})
    return lead_id, conv_ref.id


def repl(db, client, lead_id: str | None, verbose: bool):
    lead_id, conversation_id = ensure_lead(db, lead_id)
    ctx = load_context(db, lead_id)
    history: list = []

    print(f"lead {lead_id}")
    print("type a message as the driver. /quit to stop, /ctx to inspect state.\n")

    while True:
        try:
            message = input("driver> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not message:
            continue
        if message == "/quit":
            break
        if message == "/ctx":
            print(json.dumps({
                "qualification": ctx["qualification"],
                "price_requested": ctx["price_requested"],
                "missing_for_price": tools.missing_fields(
                    ctx["qualification"], tools.REQUIRED_FOR_PRICE),
                "escalated": ctx.get("escalated", False),
            }, indent=2, default=str))
            continue

        persist(db, ctx, conversation_id, "user", message)
        result = run_turn(client, db, ctx, history, message, verbose)

        if result.get("error"):
            print(f"\n[{result['error']}]\n")
            continue

        persist(db, ctx, conversation_id, "assistant",
                result["text"], result["mode"])
        print(f"\nagent> {result['text']}\n")

    print(f"\nconversation {conversation_id} saved.")


def dry_run():
    """Route and compose without an API key or a database — proves the wiring."""
    cases = [
        ("How much does it cost?", {}, "faq"),
        ("Hi, looking into karting for my son", {}, "qualification"),
        ("Any chance of a discount?", {}, "escalation"),
        ("I race Rotax Mini", {"competes": True}, "escalation"),
        ("Can we book Saturday?", {"driver_age": 9}, "scheduling"),
    ]
    print("mode routing\n")
    failures = 0
    for message, qual, expected in cases:
        ctx = {"qualification": qual, "turn_count": 0}
        actual = route(ctx, message)
        ok = actual == expected
        failures += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {message!r:42} -> {actual}"
              f"{'' if ok else f' (expected {expected})'}")

    print("\nprice gate\n")
    complete = {f: "x" for f in tools.REQUIRED_FOR_PRICE}
    checks = [
        ("nothing known, no request", {}, False, False),
        ("nothing known, driver asked", {}, True, False),
        ("qualified, did not ask", complete, False, False),
        ("qualified and asked", complete, True, True),
    ]
    for label, qual, asked, expected in checks:
        allowed, reason = tools.price_disclosure_allowed(qual, asked)
        ok = allowed == expected
        failures += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {label:28} -> "
              f"{'discloses' if allowed else 'withholds'}")

    print("\nprompt composition\n")
    for mode in ("faq", "qualification", "scheduling", "followup", "escalation"):
        prompt, tool_defs = compose(mode, {})
        print(f"  {mode:14} ~{len(prompt)//4:>5} tokens, {len(tool_defs)} tools")

    print()
    if failures:
        print(f"DRY RUN FAILED — {failures} checks")
        return 1
    print("DRY RUN PASSED — routing, gates and composition verified with no API, "
          "no database")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Run the URace sales agent.")
    ap.add_argument("--repl", action="store_true")
    ap.add_argument("--lead", help="Resume an existing lead id.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="Show mode and tools.")
    args = ap.parse_args()

    if args.dry_run:
        return dry_run()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")

    import anthropic
    from db.client import get_db

    client = anthropic.Anthropic()
    db = get_db()
    if args.repl:
        repl(db, client, args.lead, args.verbose)
    else:
        ap.error("--repl or --dry-run")
    return 0


if __name__ == "__main__":
    sys.exit(main())

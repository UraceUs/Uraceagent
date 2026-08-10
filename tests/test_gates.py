#!/usr/bin/env python3
"""
Gate tests — a prova de que os portões seguram, agora contra o Firestore.

No Postgres isto chamava as funções agent_* e tentava furar o trigger com um
INSERT direto. O Firestore não tem trigger que recusa: os portões vivem em
db/gates.py e a superfície de tools em agent/tools_impl.py — então é ISSO que
este teste exercita, pelos mesmos caminhos que o agente usa em produção.

Além das provas dinâmicas, uma estrutural: nenhum módulo fora de db/gates.py
escreve em appointments ou escalations. Se alguém criar um atalho, o grep
acusa antes de o atalho existir em produção.

Rodar:
    FIRESTORE_EMULATOR_HOST=localhost:8080 python tests/test_gates.py
    python tests/test_gates.py            # projeto real (cria e apaga docs de teste)
    python tests/test_gates.py --keep     # deixa os docs para inspeção

Exit 0 when every gate holds. Exit 1 when one does not, which is a blocker and
not a tuning issue.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent"))

QUALIFICATION = [
    ("for_whom", "son"),
    ("driver_age", "9"),
    ("origin", "Orlando, local"),
    ("goal", "try it out"),
    ("experience_level", "never raced"),
]

PREFIX = "gatetest"


class Report:
    def __init__(self):
        self.failures: list[str] = []
        self.skipped: list[str] = []

    def check(self, label: str, ok: bool, detail: str = ""):
        if ok:
            print(f"  PASS  {label}")
        else:
            print(f"  FAIL  {label}" + (f"  — {detail}" if detail else ""))
            self.failures.append(label)

    def skip(self, label: str, why: str):
        print(f"  SKIP  {label}  — {why}")
        self.skipped.append(label)


# =============================================================================
# ESTRUTURAL — o grep que impede o atalho
# =============================================================================

def structural_checks(r: Report):
    """appointments e escalations só nascem em db/gates.py.

    O trigger do Postgres era imune ao resto do código por construção. Aqui a
    imunidade é uma disciplina — e disciplina não verificada vira lenda. Este
    check varre o código e acusa qualquer collection("appointments") ou
    collection("escalations") fora de db/gates.py.
    """
    print("\n0 — estrutural: portões são o único caminho de escrita")
    offenders = []
    for py in ROOT.rglob("*.py"):
        rel = py.relative_to(ROOT).as_posix()
        if rel.startswith((".venv", "venv")) or rel == "tests/test_gates.py":
            continue
        text = py.read_text(encoding="utf-8")
        for target in ("appointments", "escalations"):
            for m in re.finditer(
                    rf"collection\(\s*['\"]{target}['\"]\s*\)", text):
                if rel != "db/gates.py":
                    offenders.append(f"{rel}: touches '{target}'")
    r.check("appointments/escalations referenced only in db/gates.py",
            not offenders, "; ".join(offenders))


# =============================================================================
# FIXTURES — catálogo mínimo, criado e removido pelo teste
# =============================================================================

def make_fixtures(db):
    programs = db.collection("programs")

    programs.document(f"{PREFIX}_one_day").set({
        "slug": f"{PREFIX}_one_day", "name": "Gate Test 1-Day",
        "agent_action": "recommend", "category": "Training",
        "description": "A full test day on track.", "status": "active",
    })
    programs.document(f"{PREFIX}_one_day").collection("offers") \
        .document(f"{PREFIX}_offer_1").set({
            "offer_id": f"{PREFIX}_offer_1", "offer_name": "Weekday",
            "program_id": f"{PREFIX}_one_day", "price_amount": 819.0,
            "price_currency": "USD", "price_unit": "day",
            "price_is_indicative": True, "agent_can_quote": True,
            "status": "active",
        })
    # A tarifa que só o operador da pista pode oferecer.
    programs.document(f"{PREFIX}_one_day").collection("offers") \
        .document(f"{PREFIX}_offer_2").set({
            "offer_id": f"{PREFIX}_offer_2", "offer_name": "Track-only rate",
            "program_id": f"{PREFIX}_one_day", "price_amount": 500.0,
            "price_currency": "USD", "price_unit": "day",
            "agent_can_quote": False, "status": "active",
        })

    programs.document(f"{PREFIX}_race_support").set({
        "slug": f"{PREFIX}_race_support", "name": "Gate Test Race Support",
        "agent_action": "handoff_to_owner", "category": "Racing",
        "description": "Full support at nationals.", "status": "active",
    })
    programs.document(f"{PREFIX}_race_support").collection("offers") \
        .document(f"{PREFIX}_offer_3").set({
            "offer_id": f"{PREFIX}_offer_3", "offer_name": "Season",
            "program_id": f"{PREFIX}_race_support", "price_amount": 9000.0,
            "price_currency": "USD", "price_unit": "month",
            "agent_can_quote": True, "status": "active",
        })

    programs.document(f"{PREFIX}_undescribed").set({
        "slug": f"{PREFIX}_undescribed", "name": "Gate Test Undescribed",
        "agent_action": "recommend", "category": "Training",
        "description": None, "status": "active",
    })


def cleanup(db):
    from google.cloud.firestore_v1.base_query import FieldFilter

    for slug in (f"{PREFIX}_one_day", f"{PREFIX}_race_support",
                 f"{PREFIX}_undescribed"):
        ref = db.collection("programs").document(slug)
        for offer in ref.collection("offers").stream():
            offer.reference.delete()
        ref.delete()

    for coll in ("human_approvals", "appointments", "escalations",
                 "follow_ups", "audit_logs", "lead_scores"):
        snaps = (db.collection(coll)
                 .where(filter=FieldFilter("lead_id", "==", f"{PREFIX}-lead"))
                 .stream())
        for snap in snaps:
            snap.reference.delete()

    db.collection("leads").document(f"{PREFIX}-lead").delete()
    db.collection("contacts").document(f"kommo__{PREFIX}-session").delete()


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="Prove the structural gates hold.")
    ap.add_argument("--keep", action="store_true",
                    help="Leave the test docs for inspection.")
    args = ap.parse_args()

    r = Report()
    structural_checks(r)

    from db.client import get_db, contact_id
    from db import gates
    import tools_impl as tools

    db = get_db()
    lead_id = f"{PREFIX}-lead"

    try:
        make_fixtures(db)

        # -------------------------------------------------------------------
        print("\n1 — lead resolution: a pessoa não duplica")
        db.collection("leads").document(lead_id).set({
            "kommo_lead_id": 999_999, "name": "Gate Test",
            "primary_channel": "whatsapp", "status": "active",
            "human_takeover": False, "qualification": {}})

        cid = contact_id("kommo", f"{PREFIX}-session")
        db.collection("contacts").document(cid).delete()
        db.collection("contacts").document(cid).create({
            "lead_id": lead_id, "channel": "email",
            "external_id": f"{PREFIX}-session"})
        duplicated = True
        try:
            db.collection("contacts").document(cid).create({
                "lead_id": "someone-else", "channel": "email",
                "external_id": f"{PREFIX}-session"})
        except Exception:
            duplicated = False
        r.check("creating the same contact twice fails structurally",
                not duplicated,
                "the doc-ID uniqueness did not hold")

        # -------------------------------------------------------------------
        print("\n2 — price gate: withheld")
        ctx = {"qualification": {}, "price_requested": False}
        p = tools.get_program_details(db, ctx, f"{PREFIX}_one_day")
        offer = (p.get("offers") or [{}])[0]
        r.check("price withheld before the driver asks",
                offer.get("price") is None, f"got {offer.get('price')!r}")
        r.check("and the reason says so",
                "has not asked" in (offer.get("price_withheld_because") or ""))

        ctx["price_requested"] = True
        p = tools.get_program_details(db, ctx, f"{PREFIX}_one_day")
        offer = (p.get("offers") or [{}])[0]
        r.check("price withheld while qualification is incomplete",
                offer.get("price") is None, f"got {offer.get('price')!r}")
        r.check("and the reason names the missing fields",
                "qualification incomplete" in
                (offer.get("price_withheld_because") or ""))

        # -------------------------------------------------------------------
        print("\n3 — completing qualification")
        remaining = None
        for field, value in QUALIFICATION:
            out = tools.update_qualification_field(db, ctx, lead_id,
                                                   field, value)
            r.check(f"{field} written", out.get("status") == "ok", str(out))
            remaining = out.get("still_missing")
        r.check("nothing is missing for price any more", not remaining,
                f"still missing {remaining}")

        # -------------------------------------------------------------------
        print("\n4 — price gate: released")
        p = tools.get_program_details(db, ctx, f"{PREFIX}_one_day")
        priced = [o for o in p["offers"] if o.get("price") is not None]
        r.check("price released once qualified and asked", bool(priced),
                "still withheld — the gate is stuck closed")
        if priced:
            o = priced[0]
            r.check("it carries a unit", o.get("unit") is not None)
            r.check("and the track-fee note",
                    "Orlando Kart Center" in (o.get("must_add") or ""))
            print(f"        {o['price']} / {o['unit']}")

        withheld = [o for o in p["offers"]
                    if o.get("offer_id") == f"{PREFIX}_offer_2"]
        r.check("the track-operator-only rate stays withheld even now",
                withheld and withheld[0].get("price") is None,
                "agent_can_quote=false leaked a number")

        # -------------------------------------------------------------------
        print("\n5 — handoff programs are never quoted")
        p = tools.get_program_details(db, ctx, f"{PREFIX}_race_support")
        r.check("handoff program: no price, however complete the profile",
                all(o.get("price") is None for o in p.get("offers") or []))

        # -------------------------------------------------------------------
        print("\n6 — empty catalog field")
        p = tools.get_program_details(db, ctx, f"{PREFIX}_undescribed")
        r.check("a null description is flagged, not papered over",
                "Do not describe" in (p.get("note") or ""))

        # -------------------------------------------------------------------
        print("\n7 — age gate")
        out = tools.request_human_approval(
            db, ctx, lead_id, reason="age_below_track_minimum",
            context="gate test", driver_age=4,
            driver_experience="never been in a kart")
        r.check("the approval opens as pending", out.get("status") == "pending")
        r.check("and the agent is told not to predict the outcome",
                "Do not predict" in (out.get("note") or ""))

        blocked, err = False, ""
        try:
            gates.create_appointment(
                db, lead_id, closing_path="chat_close",
                scheduled_at="2030-01-01T14:00:00Z", status="confirmed")
        except gates.GateRefusal as exc:
            blocked = "clearance" in str(exc) or "blocked" in str(exc).lower()
        except Exception as exc:  # índice ausente etc. — é falha, não skip
            err = f"{type(exc).__name__}: {exc}"
        r.check("the gate refuses the booking at the only write path",
                blocked, err or "the booking went through")

        appts = list(db.collection("appointments").where(
            filter=_ff("lead_id", "==", lead_id)).stream())
        r.check("and no appointment document exists", not appts,
                f"{len(appts)} created")

        # aprovar e provar que o MESMO caminho passa a aceitar
        pend = list(db.collection("human_approvals").where(
            filter=_ff("lead_id", "==", lead_id)).stream())
        for snap in pend:
            snap.reference.update({"status": "approved"})
        try:
            appt_id = gates.create_appointment(
                db, lead_id, closing_path="chat_close",
                scheduled_at="2030-01-01T14:00:00Z", status="confirmed")
            r.check("once approved, the same booking succeeds", bool(appt_id))
        except Exception as exc:
            r.check("once approved, the same booking succeeds", False,
                    f"{type(exc).__name__}: {exc}")

        # -------------------------------------------------------------------
        print("\n8 — escalation")
        db.collection("follow_ups").document(f"{lead_id}__1").set({
            "lead_id": lead_id, "attempt_number": 1,
            "scheduled_at": "2030-01-02T10:00:00Z", "status": "pending"})

        out = tools.escalate_to_human(db, ctx, lead_id,
                                      reason="personal_hardship",
                                      priority="high")
        r.check("the conversation is escalated",
                out.get("status") == "escalated")

        lead = db.collection("leads").document(lead_id).get().to_dict()
        r.check("the lead is marked as taken over",
                lead.get("human_takeover") is True)
        r.check("its status is escalated", lead.get("status") == "escalated")

        fu = db.collection("follow_ups").document(f"{lead_id}__1").get().to_dict()
        r.check("the pending follow-up is cancelled, not left to fire",
                fu.get("status") == "cancelled", f"got {fu.get('status')!r}")
        r.check("with the reason recorded",
                "personal_hardship" in (fu.get("skip_reason") or ""))

    finally:
        if args.keep:
            print("\n--keep: test docs left in place.")
        else:
            try:
                cleanup(db)
                print("\ncleaned up — no test docs remain")
            except Exception as exc:
                print(f"\ncleanup incomplete: {exc}")

    print()
    if r.skipped:
        print(f"{len(r.skipped)} checks skipped")
    if r.failures:
        print(f"GATES FAILED — {len(r.failures)}:")
        for f in r.failures:
            print(f"  {f}")
        print("\nA failing gate is a blocker. The agent must not talk to a "
              "driver until these hold.")
        return 1

    print("ALL GATES HOLD — price, age, escalation and empty-field handling "
          "verified against Firestore.")
    return 0


def _ff(field, op, value):
    from google.cloud.firestore_v1.base_query import FieldFilter
    return FieldFilter(field, op, value)


if __name__ == "__main__":
    sys.exit(main())

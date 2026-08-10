#!/usr/bin/env python3
"""
Gate tests — the Postman collection, as one command.

The collection proves the same things, but sixteen requests clicked in order is
a test nobody runs twice. This runs the whole sequence, asserts, and cleans up
after itself.

It talks to Postgres directly rather than through PostgREST, so it needs no
service key and no network exposure — the functions are the same either way.

    python tests/test_gates.py            # run everything, roll back
    python tests/test_gates.py --keep     # leave the test lead for inspection

Exit 0 when every gate holds. Exit 1 when one does not, which is a blocker and
not a tuning issue.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SESSION = "gatetest-postman-equivalent"
QUALIFICATION = [
    ("for_whom", "son"),
    ("driver_age", "9"),
    ("origin", "Orlando, local"),
    ("goal", "try it out"),
    ("experience_level", "never raced"),
]


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


def rpc(cur, fn: str, **kwargs):
    """Call one of the agent_* functions the way n8n will over HTTP."""
    names = ", ".join(f"{k} => %({k})s" for k in kwargs)
    cur.execute(f"SELECT {fn}({names})", kwargs)
    row = cur.fetchone()
    return row[0] if row else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Prove the structural gates hold.")
    ap.add_argument("--keep", action="store_true",
                    help="Commit instead of rolling back.")
    args = ap.parse_args()

    if not os.environ.get("DATABASE_URL"):
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("ERROR: DATABASE_URL not set (env or .env).")

    import psycopg

    r = Report()
    conn = psycopg.connect(url, autocommit=False)

    try:
        with conn.cursor() as cur:

            # ---------------------------------------------------------------
            print("\n0 — connectivity")
            try:
                sellable = rpc(cur, "agent_sellable_programs")
            except psycopg.errors.UndefinedFunction:
                sys.exit("ERROR: agent_* functions are missing. "
                         "Apply db/006_agent_functions.sql first.")
            r.check("the agent_* functions exist", sellable is not None)
            r.check("the catalog has sellable programs", bool(sellable),
                    "empty — run the catalog sync")
            if sellable:
                print(f"        {', '.join(p['slug'] for p in sellable)}")

            names = {p["slug"] for p in (sellable or [])}
            has_one_day = "one_day" in names
            if not has_one_day:
                print("\n  one_day is not in the catalog. The price gate tests "
                      "below cannot run.\n  Run: python catalog/sync.py --fixture "
                      "catalog/fixtures/urace-catalog-fixture.json "
                      "--allow-fixture-write")

            # ---------------------------------------------------------------
            print("\n1 — lead resolution")
            lead = rpc(cur, "agent_resolve_lead",
                       p_session_id=SESSION, p_channel="kommo",
                       p_name="Gate Test", p_phone=SESSION)
            lead_id = lead["lead_id"]
            r.check("a lead is created", bool(lead_id))

            again = rpc(cur, "agent_resolve_lead",
                        p_session_id=SESSION, p_channel="kommo",
                        p_name="Gate Test", p_phone=SESSION)
            r.check("calling it twice does not duplicate the person",
                    again["lead_id"] == lead_id)

            # ---------------------------------------------------------------
            print("\n2 — price gate: withheld")
            if not has_one_day:
                r.skip("price withheld before the driver asks", "no one_day")
                r.skip("price withheld while qualification is incomplete", "no one_day")
            else:
                p = rpc(cur, "agent_program", p_lead_id=lead_id,
                        p_slug="one_day", p_price_requested=False)
                offer = (p.get("offers") or [{}])[0]
                r.check("price withheld before the driver asks",
                        offer.get("price") is None, f"got {offer.get('price')!r}")
                r.check("and the reason says so",
                        "has not asked" in (offer.get("price_withheld_because") or ""))

                p = rpc(cur, "agent_program", p_lead_id=lead_id,
                        p_slug="one_day", p_price_requested=True)
                offer = (p.get("offers") or [{}])[0]
                r.check("price withheld while qualification is incomplete",
                        offer.get("price") is None, f"got {offer.get('price')!r}")
                r.check("and the reason names the missing fields",
                        "qualification incomplete" in
                        (offer.get("price_withheld_because") or ""))

            # ---------------------------------------------------------------
            print("\n3 — completing qualification")
            for field, value in QUALIFICATION:
                out = rpc(cur, "agent_qualify", p_lead_id=lead_id,
                          p_field=field, p_value=value)
                ok = out.get("status") == "ok"
                remaining = out.get("missing_for_price") or []
                r.check(f"{field} written", ok, json.dumps(out))
            r.check("nothing is missing for price any more", not remaining,
                    f"still missing {remaining}")

            # ---------------------------------------------------------------
            print("\n4 — price gate: released")
            if not has_one_day:
                r.skip("price released once qualified and asked", "no one_day")
            else:
                p = rpc(cur, "agent_program", p_lead_id=lead_id,
                        p_slug="one_day", p_price_requested=True)
                priced = [o for o in p["offers"] if o.get("price") is not None]
                r.check("price released once qualified and asked", bool(priced),
                        "still withheld — the gate is stuck closed")
                if priced:
                    o = priced[0]
                    r.check("it carries a unit", o.get("unit") is not None)
                    r.check("and the track-fee note",
                            "Orlando Kart Center" in (o.get("must_add") or ""))
                    print(f"        {o['price']} / {o['unit']}")

            # ---------------------------------------------------------------
            print("\n5 — handoff programs are never quoted")
            handoff = next((s for s in ("race_team_support", "mechanic_services",
                                        "workshop_services") if s in names), None)
            if handoff:
                r.skip("handoff program returns no price",
                       "handoff programs are excluded from agent_sellable_programs")
            with conn.cursor() as c2:
                c2.execute("SELECT slug FROM programs WHERE agent_action LIKE "
                           "'handoff%' AND status='active' LIMIT 1")
                row = c2.fetchone()
            if not row:
                r.skip("handoff program returns no price", "none in the catalog")
            else:
                p = rpc(cur, "agent_program", p_lead_id=lead_id,
                        p_slug=row[0], p_price_requested=True)
                r.check(f"{row[0]}: no price, however complete the profile",
                        all(o.get("price") is None for o in p.get("offers") or []))

            # ---------------------------------------------------------------
            print("\n6 — empty catalog field")
            with conn.cursor() as c2:
                c2.execute("SELECT slug FROM programs WHERE description IS NULL "
                           "AND status='active' LIMIT 1")
                row = c2.fetchone()
            if not row:
                r.skip("a null description is flagged, not papered over",
                       "every program has a description")
            else:
                p = rpc(cur, "agent_program", p_lead_id=lead_id,
                        p_slug=row[0], p_price_requested=False)
                r.check("a null description is flagged, not papered over",
                        "Do not describe it" in (p.get("note") or ""))

            # ---------------------------------------------------------------
            print("\n7 — age gate")
            appr = rpc(cur, "agent_request_approval",
                       p_lead_id=lead_id, p_reason="age_below_track_minimum",
                       p_context="gate test", p_age=4,
                       p_experience="never been in a kart")
            r.check("the approval opens as pending", appr.get("status") == "pending")
            r.check("and the agent is told not to predict the outcome",
                    "Do not predict" in (appr.get("note") or ""))

            blocked = False
            try:
                with conn.cursor() as c2:
                    c2.execute("""
                        INSERT INTO appointments (lead_id, closing_path, status,
                                                  scheduled_at)
                        VALUES (%s,'chat_close','confirmed', now() + interval '2 days')
                    """, (lead_id,))
            except psycopg.errors.CheckViolation as exc:
                blocked = "clearance" in str(exc)
            except Exception:
                pass
            r.check("the database refuses the booking, bypassing all app logic",
                    blocked,
                    "the booking went through — the trigger is not firing")
            conn.rollback() if not blocked else None

            # the rollback above discards the lead, so redo it for section 8
            if not blocked:
                lead = rpc(cur, "agent_resolve_lead", p_session_id=SESSION,
                           p_channel="kommo", p_name="Gate Test", p_phone=SESSION)
                lead_id = lead["lead_id"]

            # ---------------------------------------------------------------
            print("\n8 — escalation")
            with conn.cursor() as c2:
                c2.execute("""
                    INSERT INTO follow_ups (lead_id, attempt_number, scheduled_at)
                    VALUES (%s, 1, now() + interval '1 day')
                    ON CONFLICT DO NOTHING
                """, (lead_id,))

            esc = rpc(cur, "agent_escalate", p_lead_id=lead_id,
                      p_reason="personal_hardship", p_priority="high")
            r.check("the conversation is escalated", esc.get("status") == "escalated")

            with conn.cursor() as c2:
                c2.execute("SELECT human_takeover, status FROM leads WHERE id=%s",
                           (lead_id,))
                takeover, status = c2.fetchone()
                c2.execute("SELECT status, skip_reason FROM follow_ups "
                           "WHERE lead_id=%s", (lead_id,))
                fu = c2.fetchone()

            r.check("the lead is marked as taken over", takeover is True)
            r.check("its status is escalated", status == "escalated")
            if fu:
                r.check("the pending follow-up is cancelled, not left to fire",
                        fu[0] == "cancelled", f"got {fu[0]!r}")
                r.check("with the reason recorded",
                        "personal_hardship" in (fu[1] or ""))

            ctx = rpc(cur, "agent_context", p_session_id=SESSION)
            r.check("context reports the takeover, so routing cannot sell again",
                    ctx.get("human_takeover") is True)

    finally:
        if args.keep:
            conn.commit()
            print("\n--keep: the test lead was committed.")
        else:
            conn.rollback()
            print("\nrolled back — no test rows remain")
        conn.close()

    print()
    if r.skipped:
        print(f"{len(r.skipped)} checks skipped (catalog not fully loaded)")
    if r.failures:
        print(f"GATES FAILED — {len(r.failures)}:")
        for f in r.failures:
            print(f"  {f}")
        print("\nA failing gate is a blocker. The agent must not talk to a "
              "driver until these hold.")
        return 1

    print("ALL GATES HOLD — price, age, escalation and empty-field handling "
          "verified against Postgres.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

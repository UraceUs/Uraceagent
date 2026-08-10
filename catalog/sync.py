#!/usr/bin/env python3
"""
Catalog sync — Google Sheets to Firestore.

The sheet is the source of truth. It is NOT the operational store: the agent
never reads Google during a conversation. It reads programs/program_offers,
which this keeps in step. That protects conversation latency, and protects the
agent from the sheet being mid-edit when a driver asks a question.

Order of operations, and why:

    fetch      one read per tab
    parse      coerce and validate row by row; a bad row is rejected alone
    diff       compare against the live catalog BEFORE writing anything
    apply      upsert in one transaction; rows absent from the sheet go inactive
    reindex    hand the changed slugs to the KB indexer
    audit      record the run in catalog_sync_runs

Usage:
    python catalog/sync.py --fixture catalog/fixtures/sample_sheet.json --dry-run
    python catalog/sync.py --dry-run          # reads the real sheet, writes nothing
    python catalog/sync.py                    # applies
    python catalog/sync.py --show-diff        # apply and print every change
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mapping import SPECS, PROGRAMS, OFFERS, SEGMENTS, parse_row  # noqa: E402


# =============================================================================
# FETCH
# =============================================================================

def fetch_from_fixture(path: Path) -> dict[str, list[dict]]:
    """Local JSON shaped like the sheet. Lets the whole pipeline run with no
    credentials — which is how it gets tested before the service account
    exists, and how its behaviour on malformed input gets exercised on purpose."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {tab: rows for tab, rows in data.items()}


def fetch_from_sheets(sheet_id: str) -> dict[str, list[dict]]:
    """Read every mapped tab. Read-only scope: this service must never be able
    to write to the sheet, whatever a bug does."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not creds_path:
        sys.exit("ERROR: GOOGLE_SERVICE_ACCOUNT_JSON not set.")

    creds = service_account.Credentials.from_service_account_file(
        creds_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    api = build("sheets", "v4", credentials=creds).spreadsheets().values()

    out: dict[str, list[dict]] = {}
    for spec in SPECS:
        resp = api.get(spreadsheetId=sheet_id, range=f"{spec.tab}!A1:ZZ").execute()
        values = resp.get("values", [])
        if not values:
            out[spec.tab] = []
            continue

        header = [h.strip() for h in values[0]]
        rows = []
        for line in values[1:]:
            # A fully blank line ends the table. Trailing formatting and the
            # notes people leave under a table are not data.
            if not any(str(c).strip() for c in line):
                break
            padded = list(line) + [""] * (len(header) - len(line))
            rows.append(dict(zip(header, padded)))
        out[spec.tab] = rows
    return out


# =============================================================================
# PARSE
# =============================================================================

def parse_all(raw_tabs: dict) -> tuple[dict, list]:
    parsed: dict[str, list[dict]] = {}
    rejected: list[dict] = []

    for spec in SPECS:
        rows = raw_tabs.get(spec.tab)
        if rows is None:
            rejected.append({"tab": spec.tab, "row": None,
                             "reason": "tab missing from the sheet"})
            parsed[spec.tab] = []
            continue

        good = []
        seen: set = set()
        # Row 1 is the header, row 2 is the note line the template puts under it.
        for offset, raw in enumerate(rows, start=2):
            row, reason = parse_row(spec, raw, offset)
            if reason:
                rejected.append({"tab": spec.tab, "row": offset, "reason": reason})
                continue
            identity = row[spec.key]
            if identity in seen:
                rejected.append({"tab": spec.tab, "row": offset,
                                 "reason": f"duplicate {spec.key} '{identity}'"})
                continue
            seen.add(identity)
            good.append(row)
        parsed[spec.tab] = good

    return parsed, rejected


def check_references(parsed: dict) -> list:
    """Cross-tab integrity, before touching the database. A program pointing at
    a segment that does not exist, or an offer at a missing program, is caught
    here with a row number the team can act on — rather than as a foreign key
    error naming a UUID nobody can trace back to a cell."""
    problems = []
    segment_slugs = {r["slug"] for r in parsed[SEGMENTS.tab]}
    program_slugs = {r["slug"] for r in parsed[PROGRAMS.tab]}

    for row in parsed[PROGRAMS.tab]:
        seg = row.get("segment_id")
        if seg is not None and seg not in segment_slugs:
            problems.append({"tab": PROGRAMS.tab, "row": row["source_sheet_row"],
                             "reason": f"segment_slug '{seg}' is not in _segments"})

    for row in parsed[OFFERS.tab]:
        prog = row.get("program_id")
        if prog not in program_slugs:
            problems.append({"tab": OFFERS.tab, "row": row["source_sheet_row"],
                             "reason": f"program_slug '{prog}' is not in _programs"})

    return problems


# =============================================================================
# DIFF
# =============================================================================

def _live_docs(db, spec) -> dict[str, dict]:
    """The live catalog, keyed the same way the sheet is.

    segments/programs are top-level collections keyed by slug; offers are a
    subcollection under each program, read here as a collection group.
    """
    if spec.table == "program_offers":
        snaps = db.collection_group("offers").stream()
    else:
        snaps = db.collection(spec.table).stream()
    out = {}
    for snap in snaps:
        row = snap.to_dict()
        row.setdefault(spec.key, snap.id)
        out[row[spec.key]] = row
    return out


def diff_against_live(db, spec, rows: list[dict]) -> dict:
    """What would change. Computed before any write, so --dry-run reports the
    same thing an apply would do."""
    cols = [c.db for c in spec.columns]
    live = _live_docs(db, spec)

    incoming = {r[spec.key]: r for r in rows}
    created = sorted(set(incoming) - set(live))
    disappeared = sorted(
        k for k in set(live) - set(incoming)
        if live[k].get("status") != "inactive")

    updated = []
    for key in sorted(set(incoming) & set(live)):
        changes = {
            c: (live[key].get(c), incoming[key].get(c))
            for c in cols
            if _normalise(live[key].get(c)) != _normalise(incoming[key].get(c))
        }
        if changes:
            updated.append({"key": key, "changes": changes})

    return {"created": created, "updated": updated, "deactivated": disappeared}


def _normalise(value):
    """Números podem voltar como int/float, arrays como list. Compare shapes,
    not types, or every run reports phantom changes."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    if isinstance(value, bool):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value).strip()


# =============================================================================
# APPLY
# =============================================================================

def _doc_ref(db, spec, values: dict):
    """Onde cada linha mora. A planilha fala em slugs porque uma pessoa a
    mantém; no Firestore o slug É o doc ID — não há UUID para resolver."""
    if spec.table == "program_offers":
        return (db.collection("programs").document(values["program_id"])
                .collection("offers").document(values[spec.key]))
    return db.collection(spec.table).document(values[spec.key])


def apply_tab(db, spec, rows: list[dict], live: dict) -> int:
    cols = [c.db for c in spec.columns] + ["source_sheet_row", "source_sheet_tab"]
    if spec.table != "segments":
        cols.append("synced_at")

    from db import schema

    applied = 0
    batch = db.batch()
    ops = 0
    for row in rows:
        values = dict(row)
        if "synced_at" in cols:
            values["synced_at"] = datetime.now(timezone.utc)

        # Every mapped column is written, including the ones that are now
        # None. Merging around the Nones would silently keep a value the team
        # deliberately cleared — the bug that makes a stale price outlive
        # its deletion. set() sem merge substitui o documento inteiro.
        doc = {c: values.get(c) for c in cols}
        doc[spec.key] = values[spec.key]
        doc.setdefault("status", "active")
        schema.validate(spec.table, doc)

        batch.set(_doc_ref(db, spec, values), doc)
        applied += 1
        ops += 1
        if ops >= 400:              # limite de 500 writes por batch
            batch.commit()
            batch, ops = db.batch(), 0

    # Absent from the sheet means retired, not deleted: qualification data,
    # recommendation logs and appointments all reference these rows.
    #
    # Uma oferta que MUDOU de programa também retira o doc antigo: o caminho
    # do documento inclui o programa, então a mesma offer_id em outro programa
    # é outro doc — deixar o antigo ativo duplicaria a oferta.
    incoming = {r[spec.key]: r for r in rows}
    for key, row in live.items():
        if row.get("status") == "inactive":
            continue
        new = incoming.get(key)
        if new is not None and (spec.table != "program_offers"
                                or new["program_id"] == row.get("program_id")):
            continue
        ref = _doc_ref(db, spec, row)
        batch.update(ref, {"status": "inactive"})
        ops += 1
        if ops >= 400:
            batch.commit()
            batch, ops = db.batch(), 0

    if ops:
        batch.commit()
    return applied


# =============================================================================
# MAIN
# =============================================================================

def _storable_diffs(diffs: dict) -> dict:
    """changes como {before, after} em vez de tupla.

    O Firestore recusa array dentro de array: um update numa coluna de lista
    (keywords, required_fields) viraria [[antes], [depois]] e derrubaria o
    registro do run — o mapa não tem esse problema e lê melhor no console.
    """
    out = {}
    for tab, d in diffs.items():
        out[tab] = {
            "created": list(d["created"]),
            "deactivated": list(d["deactivated"]),
            "updated": [
                {"key": u["key"],
                 "changes": {col: {"before": json.loads(json.dumps(b, default=str)),
                                   "after": json.loads(json.dumps(a, default=str))}
                             for col, (b, a) in u["changes"].items()}}
                for u in d["updated"]],
        }
    return out


def render_diff(name: str, d: dict, verbose: bool):
    total = len(d["created"]) + len(d["updated"]) + len(d["deactivated"])
    if not total:
        print(f"  {name:16} no changes")
        return
    print(f"  {name:16} +{len(d['created'])} created  "
          f"~{len(d['updated'])} updated  -{len(d['deactivated'])} deactivated")
    if not verbose:
        return
    for key in d["created"]:
        print(f"      + {key}")
    for item in d["updated"]:
        print(f"      ~ {item['key']}")
        for col, (before, after) in item["changes"].items():
            print(f"          {col}: {before!r} -> {after!r}")
    for key in d["deactivated"]:
        print(f"      - {key} (gone from the sheet, set inactive)")


def main():
    ap = argparse.ArgumentParser(description="Sync the catalog sheet into Postgres.")
    ap.add_argument("--fixture", type=Path, help="Read a local JSON instead of Sheets.")
    ap.add_argument("--dry-run", action="store_true", help="Report the diff, write nothing.")
    ap.add_argument("--show-diff", action="store_true", help="Print every changed field.")
    ap.add_argument("--strict", action="store_true",
                    help="Exit non-zero if any row was rejected.")
    args = ap.parse_args()

    started = datetime.now(timezone.utc)

    # --- fetch ---------------------------------------------------------------
    if args.fixture:
        print(f"fetching from fixture {args.fixture}\n")
        raw = fetch_from_fixture(args.fixture)
    else:
        sheet_id = os.environ.get("CATALOG_SHEET_ID")
        if not sheet_id:
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
            sheet_id = os.environ.get("CATALOG_SHEET_ID")
        if not sheet_id:
            sys.exit("ERROR: CATALOG_SHEET_ID not set (env or .env).")
        print(f"fetching sheet {sheet_id}\n")
        try:
            raw = fetch_from_sheets(sheet_id)
        except Exception as exc:
            # The catalog in the database stays live and serving. A sync that
            # cannot read must never empty what the agent is using.
            print(f"SHEET UNAVAILABLE: {exc}")
            print("last good catalog remains in effect; alerting and exiting")
            return 2

    # --- parse ---------------------------------------------------------------
    parsed, rejected = parse_all(raw)
    rejected += check_references(parsed)

    read_count = sum(len(v) for v in raw.values())
    good_count = sum(len(v) for v in parsed.values())
    print(f"read {read_count} rows, {good_count} valid, {len(rejected)} rejected\n")

    for item in rejected:
        where = f"row {item['row']}" if item["row"] else "tab"
        print(f"  REJECTED  {item['tab']} {where}: {item['reason']}")
    if rejected:
        print()

    # --- database ------------------------------------------------------------
    from db.client import get_db

    db = get_db()

    diffs = {s.tab: diff_against_live(db, s, parsed[s.tab]) for s in SPECS}
    print("diff:")
    for spec in SPECS:
        render_diff(spec.tab, diffs[spec.tab], args.show_diff)
    print()

    if args.dry_run:
        print("dry run — nothing written")
        return 1 if (args.strict and rejected) else 0

    applied = 0
    # Segments before programs, programs before offers: a oferta mora numa
    # subcoleção do programa, então o pai tem que existir primeiro.
    for spec in SPECS:
        applied += apply_tab(db, spec, parsed[spec.tab], _live_docs(db, spec))

    changed = sorted(
        set(diffs[PROGRAMS.tab]["created"])
        | {u["key"] for u in diffs[PROGRAMS.tab]["updated"]})

    status = "partial" if rejected else "success"
    db.collection("catalog_sync_runs").document().create({
        "triggered_by": "manual", "started_at": started,
        "finished_at": datetime.now(timezone.utc), "status": status,
        "rows_read": read_count, "rows_applied": applied,
        "rows_rejected": len(rejected),
        "diff_summary": _storable_diffs(diffs),
        "errors": json.loads(json.dumps(rejected, default=str))})

    print(f"applied {applied} rows, status {status}")

    if changed:
        # Seam, not an implementation: the KB indexer does not exist yet.
        # Program description/benefits/FAQ are auto-indexed from the catalog,
        # so these slugs are what needs re-embedding — nothing else.
        print(f"\nreindex queue ({len(changed)} programs): {', '.join(changed)}")
        print("  (KB indexer not implemented — slugs printed, not enqueued)")

    return 1 if (args.strict and rejected) else 0


if __name__ == "__main__":
    sys.exit(main())

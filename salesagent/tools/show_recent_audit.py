#!/usr/bin/env python3
"""Mostra as últimas entradas do log de auditoria da sales-bridge.

Uso principal: depois de configurar o Salesbot no Kommo, mandar uma mensagem
de teste e rodar isto para ver o PAYLOAD BRUTO que o Kommo realmente enviou
(kind=hook_raw) — é assim que calibramos o parser da ponte contra o formato
real da conta, em vez de adivinhar.

Uso (no VPS):
    python3 salesagent/tools/show_recent_audit.py             # últimas 20
    python3 salesagent/tools/show_recent_audit.py -n 50
    python3 salesagent/tools/show_recent_audit.py --kind hook_raw
"""
import argparse
import datetime
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("URACE_DIR", Path.home() / ".urace")) / "salesbridge.db"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=20, help="quantas entradas")
    ap.add_argument("--kind", default=None,
                    help="filtrar por tipo (inbound, outbound, hook_raw, gate, "
                         "escalation, directives, error...)")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"banco não existe ainda: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    q = "SELECT ts, lead_id, kind, detail FROM audit"
    params: tuple = ()
    if args.kind:
        q += " WHERE kind=?"
        params = (args.kind,)
    q += " ORDER BY id DESC LIMIT ?"
    rows = conn.execute(q, (*params, args.n)).fetchall()
    conn.close()

    if not rows:
        print("nenhuma entrada" + (f" com kind={args.kind}" if args.kind else ""))
        return 0
    for r in reversed(rows):
        when = datetime.datetime.fromtimestamp(r["ts"]).strftime("%d/%m %H:%M:%S")
        lead = r["lead_id"] if r["lead_id"] is not None else "-"
        print(f"[{when}] lead={lead} {r['kind']}")
        print(f"    {r['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

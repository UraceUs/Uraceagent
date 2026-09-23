#!/usr/bin/env python3
"""
Rebuild NAO_TOCAR.csv and ENVIADOS_CONSOLIDADO.csv from data/leads_master.xlsx.

prompts/LOOP_URACE.md requires these two lists to exist, freshly regenerated,
before any batch first-contact dispatch — the CPU's version of this mistake
(Frankie Iadevaia, STOP 20/09) came from disparo running without them. This
script is the "reconstruir os dois a partir da master" step made real:

    NAO_TOCAR.csv            leads a batch must never touch: opt-out, active/
                              past client, not-a-lead, "NAO DISPARAR" (any
                              reason), frozen/live conversation.
    ENVIADOS_CONSOLIDADO.csv leads with SMS_enviado or Email_enviado already
                              filled in the master — anyone already contacted,
                              so a batch never repeats.

Usage:
    python agent/build_touch_lists.py               # rebuild both CSVs
    python agent/build_touch_lists.py --self-test    # no network, no file I/O
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MASTER_XLSX = REPO_ROOT / "data" / "leads_master.xlsx"
NAO_TOCAR_CSV = REPO_ROOT / "data" / "NAO_TOCAR.csv"
ENVIADOS_CSV = REPO_ROOT / "data" / "ENVIADOS_CONSOLIDADO.csv"

# Any of these substrings in Status (uppercased) puts a lead on NAO_TOCAR.
NAO_TOCAR_MARKERS = (
    "OPT-OUT", "CLIENTE", "NAO DISPARAR", "NAO E LEAD", "INTERNO",
    "CONVERSA VIVA", "NAO TOCAR",
)


def _row_dict(headers: list[str], row: tuple) -> dict:
    return dict(zip(headers, row))


def build_lists(master_path: Path = MASTER_XLSX) -> tuple[list[dict], list[dict]]:
    """Returns (nao_tocar_rows, enviados_rows) as lists of plain dicts —
    kept separate from the CSV-writing so --self-test can check the
    classification logic without touching the filesystem."""
    import openpyxl  # deferred: only needed here, not for --self-test import

    wb = openpyxl.load_workbook(master_path)
    ws = wb.active
    headers = [c.value for c in ws[1]]

    nao_tocar_rows: list[dict] = []
    enviados_rows: list[dict] = []

    for raw_row in ws.iter_rows(min_row=2, values_only=True):
        row = _row_dict(headers, raw_row)
        status = str(row.get("Status") or "").upper()

        if any(marker in status for marker in NAO_TOCAR_MARKERS):
            nao_tocar_rows.append({
                "Nome": row.get("Nome"),
                "Telefone": row.get("Telefone"),
                "Email": row.get("Email"),
                "Status": row.get("Status"),
                "Motivo_Proximo_passo": row.get("Proximo_passo"),
            })

        if row.get("SMS_enviado") or row.get("Email_enviado"):
            enviados_rows.append({
                "Nome": row.get("Nome"),
                "Telefone": row.get("Telefone"),
                "Email": row.get("Email"),
                "Status": row.get("Status"),
                "SMS_enviado": row.get("SMS_enviado"),
                "Email_enviado": row.get("Email_enviado"),
            })

    return nao_tocar_rows, enviados_rows


def write_csvs(nao_tocar_rows: list[dict], enviados_rows: list[dict]) -> None:
    with open(NAO_TOCAR_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "Nome", "Telefone", "Email", "Status", "Motivo_Proximo_passo"])
        w.writeheader()
        w.writerows(nao_tocar_rows)

    with open(ENVIADOS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "Nome", "Telefone", "Email", "Status", "SMS_enviado", "Email_enviado"])
        w.writeheader()
        w.writerows(enviados_rows)


def _self_test() -> None:
    """No network, no file I/O — exercises only the classification rule
    (NAO_TOCAR_MARKERS) that the loop's safety guarantee depends on."""
    checks = 0

    for status in ("OPT-OUT (STOP)", "CLIENTE ATIVO", "NAO DISPARAR - SEM TELEFONE",
                    "NAO E LEAD - SISTEMA/FORNECEDOR", "CONVERSA VIVA - THREAD DO LUCAS"):
        assert any(m in status.upper() for m in NAO_TOCAR_MARKERS), status
        checks += 1

    for status in ("NOVO - BASE LEADS", "CONTATADO 18/09", "QUENTE 19/09 - DEU IDADE",
                    "RESPONDEU - QUENTE"):
        assert not any(m in status.upper() for m in NAO_TOCAR_MARKERS), status
        checks += 1

    print(f"build_touch_lists --self-test: {checks}/9 OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return

    nao_tocar_rows, enviados_rows = build_lists()
    write_csvs(nao_tocar_rows, enviados_rows)
    print(f"{NAO_TOCAR_CSV.relative_to(REPO_ROOT)}: {len(nao_tocar_rows)} linhas")
    print(f"{ENVIADOS_CSV.relative_to(REPO_ROOT)}: {len(enviados_rows)} linhas")


if __name__ == "__main__":
    main()

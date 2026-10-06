#!/usr/bin/env python3
"""Mascara token, chave, URL de continuação e telefone nas linhas antigas da
auditoria da ponte (~/.urace/salesbridge.db).

A ponte já grava mascarado (state.mascarar). Este script limpa o que ficou
gravado antes disso, sobretudo as linhas hook_raw.

Uso (na VPS):
    python3 salesagent/tools/mascarar_auditoria.py            # só conta
    python3 salesagent/tools/mascarar_auditoria.py --aplicar  # reescreve
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bridge"))

import state  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true", help="reescreve as linhas (sem isto, só conta)")
    args = ap.parse_args()
    mudam = []
    with state.db() as conn:
        for rid, detail in conn.execute("SELECT id, detail FROM audit").fetchall():
            novo = state.mascarar(detail or "")
            if novo != (detail or ""):
                mudam.append((novo, rid))
        if args.aplicar and mudam:
            conn.executemany("UPDATE audit SET detail=? WHERE id=?", mudam)
    print(f"linhas com dado sensível: {len(mudam)}" + (" (mascaradas)" if args.aplicar else " (nada alterado; use --aplicar)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

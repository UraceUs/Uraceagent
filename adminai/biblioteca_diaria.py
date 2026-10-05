#!/usr/bin/env python3
"""A rodada diária da Biblioteca (#88) — programada, sem IA, sem gastar token.

Dono, 05/10: *"seria interessante que fosse todo dia, mas eu não quero que fique gastando
token. Quero que seja programado mesmo, com rotina"*.

    python3 adminai/biblioteca_diaria.py              # tudo: QuickBooks, contratos, waivers, históricos e Drive
    python3 adminai/biblioteca_diaria.py --sem-drive  # só junta aqui; não sobe nada

Roda pelo timer `urace-biblioteca.timer` toda madrugada (Flórida). Só LÊ o QuickBooks e o
DocuSign; no Drive, só escreve dentro da pasta "Command Center" que ela mesma criou.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adminai._venv import garantir_venv  # noqa: E402

garantir_venv()


def main():
    ap = argparse.ArgumentParser(description="Rodada diária da Biblioteca")
    ap.add_argument("--sem-drive", action="store_true")
    a = ap.parse_args()
    from command_center.db import aplicar_schema, conectar
    from command_center.providers import biblioteca
    con = conectar()
    aplicar_schema(con)
    r = biblioteca.rodada(con, usar_drive=not a.sem_drive)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    con.close()


if __name__ == "__main__":
    main()

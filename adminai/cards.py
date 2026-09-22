#!/usr/bin/env python3
"""Mostra cards pelo pedaço do nome, e as uniões que já aconteceram com eles. Só lê.

    python3 adminai/cards.py Alon Arroyo
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from adminai._venv import garantir_venv  # noqa: E402

garantir_venv()          # o python3 do sistema não tem as dependências (22/09)

from command_center.db import aplicar_schema, conectar, todos  # noqa: E402


def main():
    if len(sys.argv) < 2:
        sys.exit("passe um pedaço de nome: python3 adminai/cards.py Alon")
    con = conectar()
    aplicar_schema(con)
    try:
        for pedaco in sys.argv[1:]:
            print(f"\n=== {pedaco} ===")
            like = f"%{pedaco}%"
            for c in todos(con, "SELECT id, name, pilot_name, email, phone, kind FROM clients "
                                "WHERE name LIKE ? OR pilot_name LIKE ? ORDER BY id", (like, like)):
                n = todos(con, "SELECT COUNT(*) AS n FROM tasks WHERE client_id=?", (c["id"],))[0]["n"]
                print(f"  #{c['id']:<4} resp. {c['name']!r:<34} piloto {c['pilot_name']!r:<28} "
                      f"{c['email'] or '-':<28} {c['phone'] or '-':<16} {c['kind']}  serviços={n}")
            for m in todos(con, "SELECT keep_id, drop_id, drop_name, merged_by, reason, merged_at FROM client_merges "
                                "WHERE drop_name LIKE ? ORDER BY id", (like,)):
                print(f"  união: #{m['drop_id']} {m['drop_name']!r} -> #{m['keep_id']}  por {m['merged_by']}  ({m['reason']})")
    finally:
        con.close()


if __name__ == "__main__":
    main()

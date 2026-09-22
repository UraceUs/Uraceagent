#!/usr/bin/env python3
"""Onde está cada nome hoje, e o que a atribuição faria com ele. Só lê.

    python3 adminai/diag_atribuicao.py G.J Mike Sean
    python3 adminai/diag_atribuicao.py              # a lista de 22/09
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from adminai._venv import garantir_venv  # noqa: E402

garantir_venv()          # o python3 do sistema não tem as dependências (22/09)

from command_center.db import aplicar_schema, conectar, todos, um  # noqa: E402
from command_center.providers import atribuicao, identidade  # noqa: E402

PADRAO = ["G.J", "Mike", "Sean", "Savage", "Savege", "Alex", "Liam", "Aaron", "Brian", "Andres",
          "Lucca", "Mauricio", "Sanghera", "Martin", "Mikey", "Luciano", "Daneyza", "Axel", "Maya",
          "Italo", "Nardo", "Usf"]


def main():
    alvo = sys.argv[1:] or PADRAO
    con = conectar()
    aplicar_schema(con)          # a migração não espera o deploy: a ferramenta se serve
    try:
        tarefas = todos(con, "SELECT id, client_id, title FROM tasks WHERE project='U-RACE'")
        por = {}
        for t in tarefas:
            p = identidade.pessoa_do_titulo(t["title"])
            if p in alvo:
                por.setdefault(p, []).append(t)
        print("===== onde está hoje, e o que o resolver diz =====")
        for nome in alvo:
            ts = por.get(nome, [])
            c, m = atribuicao.resolver(con, nome)
            iguais = todos(con, "SELECT id, name, pilot_name FROM clients WHERE lower(name)=lower(?) OR lower(pilot_name)=lower(?)",
                           (nome, nome))
            print(f"\n{nome:<9} {len(ts):>3} serv | resolver -> "
                  f"{(c['id'], c['pilot_name'] or c['name']) if c else None} ({m})"
                  f" | card com esse nome exato: {[(x['id'], x['name'], x['pilot_name']) for x in iguais]}")
            donos = {}
            for t in ts:
                donos[t["client_id"]] = donos.get(t["client_id"], 0) + 1
            for cid, n in sorted(donos.items(), key=lambda kv: -kv[1]):
                cc = um(con, "SELECT name, pilot_name FROM clients WHERE id=?", (cid,)) if cid else None
                print(f"      hoje em #{cid} {(cc['pilot_name'] or cc['name']) if cc else '(sem card)'}: {n}")
        print("\n===== títulos COM separador que ficaram SEM nome =====")
        n = 0
        for t in tarefas:
            tt = t["title"]
            if identidade.pessoa_do_titulo(tt) is None and ("_" in tt or " - " in tt or "|" in tt):
                cc = um(con, "SELECT name, pilot_name FROM clients WHERE id=?", (t["client_id"],)) if t["client_id"] else None
                print(f"  {tt[:60]:<60} hoje em {(cc['pilot_name'] or cc['name']) if cc else '(sem card)'}")
                n += 1
                if n >= 70:
                    print("  …"); break
    finally:
        con.close()


if __name__ == "__main__":
    main()

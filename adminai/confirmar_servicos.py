#!/usr/bin/env python3
"""Carimba "este serviço é deste cliente, o dono confirmou". A varredura nunca mexe.

    python3 adminai/confirmar_servicos.py 15 238            # mostra o que carimbaria
    python3 adminai/confirmar_servicos.py 15 238 --aplicar

Nasceu de 22/09. O dono confirmou que os 18 serviços "Savage" e os 2 "Savege" do card
#15 são do Alexander — mesmo o card tendo sido alcançado pelo sobrenome do **Kenneth**
Savage — e que o único "Alex" do #238 é do Alex Donnell.

Sem carimbo, "está certo hoje" não dura: basta um homônimo novo entrar no cadastro para
o nome virar ambíguo e a varredura tirar o serviço de lá. O carimbo é o que faz a
decisão dele valer mais que qualquer regra automática.

Tira o carimbo com --soltar, se ele mudar de ideia.
"""
import argparse
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from command_center.db import agora, aplicar_schema, auditar, conectar, todos, um  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cards", nargs="+", type=int, help="ids dos cards cujos serviços o dono confirmou")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--soltar", action="store_true", help="tira o carimbo em vez de pôr")
    a = ap.parse_args()

    con = conectar()
    aplicar_schema(con)
    try:
        print("\n" + ("APLICANDO" if a.aplicar else "PLANO (nada foi escrito)"))
        print("=" * 72)
        total = 0
        for cid in a.cards:
            c = um(con, "SELECT id, name, pilot_name FROM clients WHERE id=?", (cid,))
            if not c:
                sys.exit(f"card #{cid} não existe")
            alvo = ("client_by='human'" if a.soltar else "COALESCE(client_by,'') <> 'human'")
            tarefas = todos(con, f"SELECT id, title FROM tasks WHERE client_id=? AND {alvo}", (cid,))
            print(f"\n#{c['id']} {c['pilot_name'] or c['name']}: "
                  f"{len(tarefas)} serviço(s) {'a soltar' if a.soltar else 'a confirmar'}")
            for t in tarefas[:12]:
                print(f"    {t['title'][:70]}")
            if len(tarefas) > 12:
                print(f"    … e mais {len(tarefas) - 12}")
            total += len(tarefas)
            if not a.aplicar or not tarefas:
                continue
            if a.soltar:
                con.execute("UPDATE tasks SET client_by=NULL, client_at=NULL WHERE client_id=? AND client_by='human'", (cid,))
            else:
                con.execute("UPDATE tasks SET client_by='human', client_at=? WHERE client_id=? "
                            "AND COALESCE(client_by,'') <> 'human'", (agora(), cid))
            auditar(con, "tasks.client_confirmed" if not a.soltar else "tasks.client_unconfirmed",
                    "owner:cli", entity_type="client", entity_id=cid,
                    detail={"servicos": len(tarefas), "reason": "dono, 22/09: confirmou de quem são"})
            con.commit()
            print("  feito.")
        if not a.aplicar:
            print(f"\n{total} serviço(s) no total. Nada foi escrito — repita com --aplicar.")
    finally:
        con.close()


if __name__ == "__main__":
    main()

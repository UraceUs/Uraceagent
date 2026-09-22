#!/usr/bin/env python3
"""Carimba "este serviço é deste cliente, o dono confirmou". A varredura nunca mexe.

    python3 adminai/confirmar_servicos.py 15 --nome Savage --nome Savege
    python3 adminai/confirmar_servicos.py 15 --nome Savage --nome Savege --aplicar
    python3 adminai/confirmar_servicos.py 238 --nome Alex --aplicar

`--nome` é o nome como aparece NO TÍTULO da tarefa, e ele é obrigatório: sem filtro,
carimbar "tudo que está neste card" é carimbar também o que está lá por engano.

A extensão da VPS pegou isso em 22/09: o dono aprovou 20 serviços do #15 (18 "Savage"
+ 2 "Savege") e a ferramenta ia carimbar **70** — incluindo
`Lucas Oil Winter Series Race | Sebring`, que é uma corrida, não uma pessoa. Carimbar
é dizer "nunca mais confira isto": carimbar errado é pior do que não carimbar.

Use `--tudo` para carimbar o card inteiro, quando for mesmo isso que o dono disse.
Tira o carimbo com `--soltar`.
"""
import argparse
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from adminai._venv import garantir_venv  # noqa: E402

garantir_venv()          # o python3 do sistema não tem as dependências (22/09)

from command_center.db import agora, aplicar_schema, auditar, conectar, todos, um  # noqa: E402
from command_center.providers import identidade  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cards", nargs="+", type=int, help="ids dos cards cujos serviços o dono confirmou")
    ap.add_argument("--nome", action="append", default=[], metavar="NOME",
                    help="nome como aparece no TÍTULO (repita para vários). Obrigatório sem --tudo")
    ap.add_argument("--tudo", action="store_true", help="o card inteiro, sem filtro (use com cuidado)")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--soltar", action="store_true", help="tira o carimbo em vez de pôr")
    a = ap.parse_args()
    if not a.nome and not a.tudo:
        sys.exit("passe --nome (o nome como está no título) ou --tudo. Carimbar sem filtro\n"
                 "carimba também o que está no card por engano — foi o que a VPS pegou em 22/09.")
    alvos = {n.strip().lower() for n in a.nome}

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
            if alvos:
                tarefas = [t for t in tarefas
                           if (identidade.pessoa_do_titulo(t["title"]) or "").lower() in alvos]
            fora = []
            if alvos:
                todas = todos(con, f"SELECT id, title FROM tasks WHERE client_id=? AND {alvo}", (cid,))
                fora = [t for t in todas if t not in tarefas]
            print(f"\n#{c['id']} {c['pilot_name'] or c['name']}: "
                  f"{len(tarefas)} serviço(s) {'a soltar' if a.soltar else 'a confirmar'}")
            for t in tarefas[:12]:
                print(f"    {t['title'][:70]}")
            if len(tarefas) > 12:
                print(f"    … e mais {len(tarefas) - 12}")
            if fora:
                print(f"    ({len(fora)} serviço(s) do card FORA do filtro — não serão tocados)")
                for t in fora[:5]:
                    print(f"       fora: {t['title'][:64]}")
            total += len(tarefas)
            if not a.aplicar or not tarefas:
                continue
            ids = [t["id"] for t in tarefas]
            marcas = ",".join("?" * len(ids))
            if a.soltar:
                con.execute(f"UPDATE tasks SET client_by=NULL, client_at=NULL WHERE id IN ({marcas})", ids)
            else:
                con.execute(f"UPDATE tasks SET client_by='human', client_at=? WHERE id IN ({marcas})",
                            (agora(), *ids))
            auditar(con, "tasks.client_confirmed" if not a.soltar else "tasks.client_unconfirmed",
                    "owner:cli", entity_type="client", entity_id=cid,
                    detail={"servicos": len(tarefas), "nomes": sorted(alvos) or "todos",
                            "reason": "dono, 22/09: confirmou de quem são"})
            con.commit()
            print("  feito.")
        if not a.aplicar:
            print(f"\n{total} serviço(s) no total. Nada foi escrito — repita com --aplicar.")
    finally:
        con.close()


if __name__ == "__main__":
    main()

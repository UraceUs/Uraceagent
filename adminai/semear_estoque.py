#!/usr/bin/env python3
"""Cria os itens de estoque a partir do que as invoices mostraram girar.

Dono, 23/09: *"leia todas as invoices criadas desde o início do ano para saber quais as
peças que mais são usadas"*. `dados/pecas-mais-usadas-2026.json` é o resultado disso —
348 invoices do QuickBooks, linha a linha, de 02/01 a 22/09/2026.

    python3 adminai/semear_estoque.py                      # mostra o que criaria
    python3 adminai/semear_estoque.py --aplicar            # cria
    python3 adminai/semear_estoque.py --min-invoices 5     # só o que girou mesmo

**Por que ordenar por INVOICES e não por quantidade:** a frequência é que diz se a peça
precisa estar na prateleira. Uma caixa de 49 adesivos vendida de uma vez não é item de
giro; um pinhão que apareceu em 31 vendas diferentes é.

**Não cria saldo.** Saldo só nasce de movimento — entrada, contagem. O que isto cria é a
ficha: o que é, de que tipo, qual o mínimo. A primeira contagem física é que diz quanto
tem.

O mínimo sugerido é **um mês de consumo** medido nessas invoices, arredondado para cima.
É ponto de partida para o dono corrigir com o que ele sabe e os números não mostram:
prazo de entrega da Comet, peça que quebra em lote, corrida grande no calendário.
"""
import argparse
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from adminai._venv import garantir_venv  # noqa: E402

garantir_venv()

from command_center.db import aplicar_schema, conectar, um  # noqa: E402
from command_center.providers import estoque  # noqa: E402

DADOS = os.path.join(RAIZ, "dados", "pecas-mais-usadas-2026.json")


def carregar(caminho=DADOS):
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def semear(con, itens, aplicar=False):
    """Idempotente pelo nome: rodar duas vezes não duplica ficha."""
    criados, ja_existiam = [], []
    for it in itens:
        ja = um(con, "SELECT id, name FROM stock_items WHERE LOWER(name)=LOWER(?)", (it["nome"],))
        if ja:
            ja_existiam.append(dict(it, id=ja["id"]))
            continue
        if aplicar:
            iid = estoque.criar_item(
                con, it["kind"], it["nome"], min_qty=it["min_sugerido"],
                unit="jogo" if it["kind"] == "pneu" else "un",
                notes=(f"Criado pelo giro das invoices (jan–set/2026): {it['qty_vendida']:g} "
                       f"em {it['invoices']} venda(s). Categoria no QuickBooks: {it['categoria']}."))
            it = dict(it, id=iid)
        criados.append(it)
    return {"criados": criados, "ja_existiam": ja_existiam}


def main():
    ap = argparse.ArgumentParser(description="Cria itens de estoque pelo giro das invoices")
    ap.add_argument("--aplicar", action="store_true", help="cria de verdade")
    ap.add_argument("--min-invoices", type=int, default=3,
                    help="só itens que apareceram em pelo menos N vendas (padrão 3)")
    ap.add_argument("--arquivo", default=DADOS)
    a = ap.parse_args()

    doc = carregar(a.arquivo)
    itens = [x for x in doc["itens"] if x["invoices"] >= a.min_invoices]
    print(f"fonte: {doc['fonte']}")
    print(f"{len(doc['itens'])} itens físicos no total · {len(itens)} com {a.min_invoices}+ vendas\n")

    con = conectar()
    aplicar_schema(con)
    try:
        r = semear(con, itens, aplicar=a.aplicar)
        if a.aplicar:
            con.commit()
        print(f"{'CRIADOS' if a.aplicar else 'CRIARIA'} ({len(r['criados'])}):")
        print(f"  {'vendas':>6} {'qtd':>6} {'mín':>4}  item")
        for x in r["criados"]:
            print(f"  {x['invoices']:>6} {x['qty_vendida']:>6.1f} {x['min_sugerido']:>4}  {x['nome'][:50]}")
        if r["ja_existiam"]:
            print(f"\njá existiam, não toquei ({len(r['ja_existiam'])}): "
                  + ", ".join(x["nome"][:28] for x in r["ja_existiam"][:8]))
        if not a.aplicar:
            print("\nNada foi criado. Para criar: --aplicar")
        else:
            print("\nFichas criadas SEM saldo: saldo só nasce de movimento.")
            print("Próximo passo é a contagem física — é ela que diz quanto tem hoje.")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)

#!/usr/bin/env python3
"""Contagem física: o que a mão contou vira o saldo.

As fichas nascem sem saldo — saldo só nasce de movimento. Esta é a ferramenta que dá o
primeiro: alguém vai na prateleira, conta, e anota.

    python3 adminai/contar_estoque.py                          # imprime a folha
    python3 adminai/contar_estoque.py --local trailer          # a folha do trailer
    python3 adminai/contar_estoque.py --contar 3=12 5=0 --aplicar

**Contar não é "corrigir o número".** É dizer que o número estava errado e guardar de
quanto era o erro. Sem isso não há como saber se o estoque está sendo furtado, perdido
ou só mal lançado — e o painel fica com um número em que ninguém acredita.

**Item que você NÃO contou fica como está.** Nunca vira zero. Contagem parcial que zera
o resto é como um estoque inteiro some numa tarde: alguém conta a prateleira dos pneus,
salva, e as correntes desaparecem. Para dizer "não tem nenhum", conte `=0` — explícito.

**Zero é uma contagem válida e importante.** `5=0` registra que a prateleira está vazia,
o que é diferente de nunca ter sido contada.
"""
import argparse
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from adminai._venv import garantir_venv  # noqa: E402

garantir_venv()

from command_center.db import aplicar_schema, conectar, todos, um  # noqa: E402
from command_center.providers import estoque  # noqa: E402


def folha(con, local_id):
    """O que há para contar naquele lugar, com o saldo que o sistema acha que tem."""
    linhas = []
    for i in todos(con, """SELECT * FROM stock_items WHERE active=1 AND tracking='quantidade'
                            ORDER BY name"""):
        atual = estoque.saldo(con, i["id"], local_id, client_id=None)
        ultima = um(con, """SELECT at FROM stock_moves WHERE item_id=? AND kind='contagem'
                             ORDER BY id DESC LIMIT 1""", (i["id"],))
        linhas.append({"id": i["id"], "nome": i["name"], "unidade": i["unit"],
                       "minimo": i["min_qty"], "sistema": atual,
                       "contado_em": (ultima["at"][:10] if ultima else None)})
    return linhas


def ler_pares(pares):
    """`3=12` → (3, 12.0). Erra claro: um dedo errado aqui vira saldo errado lá."""
    saida = []
    for p in pares:
        if "=" not in p:
            raise SystemExit(f"formato errado: {p!r} — use id=quantidade, por exemplo 3=12")
        ident, _, qty = p.partition("=")
        try:
            saida.append((int(ident.strip().lstrip("#")), float(qty.strip())))
        except ValueError:
            raise SystemExit(f"formato errado: {p!r} — id e quantidade têm de ser números")
    return saida


def main():
    ap = argparse.ArgumentParser(description="Contagem física do estoque")
    ap.add_argument("--local", default=estoque.SEDE, help="sede (padrão) ou trailer")
    ap.add_argument("--contar", nargs="+", metavar="ID=QTD", default=[],
                    help="o que a mão contou. Item fora da lista NÃO é alterado")
    ap.add_argument("--aplicar", action="store_true", help="grava a contagem")
    ap.add_argument("--quem", type=int, help="id do usuário que contou")
    ap.add_argument("--nota", help="observação (ex.: 'contagem do mês, prateleira nova')")
    a = ap.parse_args()

    con = conectar()
    aplicar_schema(con)
    try:
        loc = estoque.local(con, a.local)
        if not a.contar:
            linhas = folha(con, loc["id"])
            print(f"FOLHA DE CONTAGEM — {loc['name']}\n")
            print(f"  {'#id':>5} {'sistema':>8} {'mín':>5}  {'contado em':<11} item")
            for l in linhas:
                print(f"  {l['id']:>5} {l['sistema']:>8.6g} {(l['minimo'] or 0):>5.4g}  "
                      f"{(l['contado_em'] or '—'):<11} {l['nome'][:42]} ({l['unidade']})")
            print(f"\n{len(linhas)} item(ns). Conte e volte com:")
            print("  python3 adminai/contar_estoque.py --contar 3=12 5=0 --aplicar")
            print("Item que você não passar fica como está — nunca vira zero.")
            return 0

        pares = ler_pares(a.contar)
        print(f"CONTAGEM — {loc['name']}\n")
        print(f"  {'#id':>5} {'antes':>8} {'contado':>8} {'dif':>8}  item")
        total_dif = 0.0
        for ident, qty in pares:
            it = estoque.item(con, ident)                 # erra claro se o id não existe
            antes = estoque.saldo(con, ident, loc["id"], client_id=None)
            dif = qty - antes
            total_dif += dif
            print(f"  {ident:>5} {antes:>8.6g} {qty:>8.6g} {dif:>+8.6g}  {it['name'][:42]}")
            if a.aplicar:
                estoque.contar(con, ident, qty, onde=loc["id"], by_user_id=a.quem, notes=a.nota)
        if a.aplicar:
            con.commit()
            print(f"\nGRAVADO: {len(pares)} contagem(ns), diferença total {total_dif:+.6g}")
            falta = estoque.abaixo_do_minimo(con)
            if falta:
                print(f"\nAbaixo do mínimo depois da contagem ({len(falta)}):")
                for f in falta[:15]:
                    sku = f" · SKU {f['sku']}" if f["sku"] else ""
                    print(f"  falta {f['falta']:>6.6g} {f['unit']:<5} {f['name'][:40]}{sku}")
        else:
            print("\nNada foi gravado. Para gravar: --aplicar")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)

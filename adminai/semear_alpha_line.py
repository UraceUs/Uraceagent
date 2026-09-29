#!/usr/bin/env python3
"""Cria as fichas da fileira Alpha Line (dono, 29/09).

*"Preciso da prateleira horizontal com escrito Alpha Line… pode já colocar como exemplo
boné da URACE, camisa da URACE, moletom URACE… e os nossos macacões standard."*

Só a **ficha**: sem quantidade e sem preço. Quanto tem é o mecânico que diz, tocando no
card; o preço é o gerente que põe. Idempotente pelo nome: rodar de novo não duplica, e
ficha que alguém já editou (ou desativou) não é tocada.

    python3 adminai/semear_alpha_line.py            # mostra o que criaria
    python3 adminai/semear_alpha_line.py --aplicar  # cria
"""
import argparse
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from adminai._venv import garantir_venv  # noqa: E402
garantir_venv()

from command_center.db import aplicar_schema, conectar, um  # noqa: E402
from command_center.providers import estoque  # noqa: E402

ITENS = [
    ("Boné URACE", "Bonés"),
    ("Camisa URACE", "Camisetas"),
    ("Moletom URACE", "Moletons"),
    ("Macacão URACE (standard)", "Macacões"),
]


def semear(con, aplicar=False):
    criados, ja_existiam = [], []
    for nome, sub in ITENS:
        if um(con, "SELECT id FROM stock_items WHERE LOWER(name)=LOWER(?)", (nome,)):
            ja_existiam.append(nome)
            continue
        if aplicar:
            estoque.criar_item(con, "peca", nome, category="vestuario", subcategory=sub,
                               notes="Alpha Line — ficha criada a pedido do dono (29/09). "
                                     "Quantidade e preço: informar no painel.")
        criados.append(nome)
    return {"criados": criados, "ja_existiam": ja_existiam}


def main():
    ap = argparse.ArgumentParser(description="Cria as fichas da fileira Alpha Line")
    ap.add_argument("--aplicar", action="store_true", help="cria de verdade")
    a = ap.parse_args()
    con = conectar()
    aplicar_schema(con)
    try:
        r = semear(con, aplicar=a.aplicar)
        print(("CRIADAS: " if a.aplicar else "CRIARIA: ") + (", ".join(r["criados"]) or "nada"))
        if r["ja_existiam"]:
            print("já existiam, não toquei: " + ", ".join(r["ja_existiam"]))
    finally:
        con.close()


if __name__ == "__main__":
    main()

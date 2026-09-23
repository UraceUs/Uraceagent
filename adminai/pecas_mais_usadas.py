#!/usr/bin/env python3
"""Quais peças a URACE realmente usa — pelas invoices, não de cabeça.

Dono, 23/09: *"leia todas as invoices criadas desde o início do ano para saber quais as
peças que mais são usadas"*.

Este é o agregador. Ele recebe as linhas das invoices do QuickBooks (um TSV
`item_name<TAB>qty<TAB>amount`, uma linha por item vendido) e devolve o arquivo que
`adminai/semear_estoque.py` consome.

    python3 adminai/pecas_mais_usadas.py linhas.tsv > dados/pecas-mais-usadas-2026.json

**Por que não usar o relatório pronto do QuickBooks:** o dono mandou ler invoice por
invoice, e tinha razão. O "Sales by Product" põe **Travel Fee no topo, com 684 de
quantidade** — são milhas a $0,85, não peça. Ele também joga fora o prefixo de categoria
(`Parts:`, `Service:`), que é justamente o que separa peça de serviço.

**Três filtros, e cada um já pegou coisa errada de verdade:**

1. **Serviço arquivado como peça.** `Parts:Rebuild Motor Labor` e `Parts:SPEEDlab
   Complete Tag Rebuild Labor` estão sob "Parts" no QuickBooks e são mão de obra.
2. **Fatura anulada.** Invoice com "Voided" no memo tem linhas com quantidade 0 que só
   sujam a conta.
3. **O que não é prateleira.** Roupa sob medida, tenda de evento e kart completo saem —
   com o motivo escrito no arquivo, para o dono discordar se quiser.

Ordena por **em quantas invoices a peça apareceu**, não por quantidade: é a frequência
que diz se a peça precisa estar na prateleira. Uma caixa de 49 adesivos vendida de uma
vez não é item de giro; um pinhão em 31 vendas diferentes é.
"""
import collections
import json
import re
import sys

CATEGORIAS_FISICAS = {"Parts", "Parts IAME", "OTK Parts", "OTK Wheels", "Engine parts",
                      "Electric", "Fuel and Oil"}
FORA_DA_PRATELEIRA = {
    "Clothes and accessories": "feito sob medida por encomenda; não fica em prateleira",
    "Canotops": "estrutura de evento (tenda, parede, bandeira); compra por pedido",
    "Karts": "chassi/kart completo: é ficha individual com número de série, não quantidade",
}
E_SERVICO = re.compile(r"labor|rebuild|blue print", re.I)
E_PNEU = re.compile(r"\btires?\b", re.I)
# Item sem categoria no QuickBooks que ainda assim é coisa física.
FISICO_SEM_CATEGORIA = re.compile(
    r"Tires|Piston|Bearing|Pin\b|Bumper|Clamp|Radio|SD card|transponder|Sticker|Wheel|"
    r"Chain|sprocket|Plug|Gasket|[Aa]xle|stub|seal|belt|WD40|studs|weights")


def agregar(linhas, meses):
    """`linhas`: iterável de (item_name, qty, amount). Devolve a lista ordenada."""
    itens = collections.defaultdict(lambda: {"qty": 0.0, "valor": 0.0, "invoices": 0, "categoria": ""})
    for nome_cheio, qty, valor in linhas:
        categoria, sep, nome = nome_cheio.partition(":")
        if not sep:
            categoria, nome = "", nome_cheio
        if E_SERVICO.search(nome_cheio) or categoria in FORA_DA_PRATELEIRA:
            continue
        if categoria not in CATEGORIAS_FISICAS and not (
                categoria == "" and FISICO_SEM_CATEGORIA.search(nome_cheio)):
            continue
        d = itens[nome.strip()]
        d["qty"] += float(qty)
        d["valor"] += float(valor)
        d["invoices"] += 1
        d["categoria"] = categoria or "(sem categoria no QuickBooks)"

    saida = []
    for nome, d in itens.items():
        por_mes = d["qty"] / meses if meses else 0
        saida.append({
            "nome": nome, "categoria": d["categoria"],
            "kind": "pneu" if E_PNEU.search(nome) else "peca",
            "qty_vendida": round(d["qty"], 2), "invoices": d["invoices"],
            "valor_vendido": round(d["valor"], 2), "por_mes": round(por_mes, 2),
            # Um mês de consumo, arredondado para cima. Ponto de partida para o dono
            # corrigir com o que os números não mostram: prazo da Comet, peça que quebra
            # em lote, corrida grande no calendário.
            "min_sugerido": max(1, round(por_mes + 0.5)),
            "preco_medio": round(d["valor"] / d["qty"], 2) if d["qty"] else None,
        })
    saida.sort(key=lambda x: (-x["invoices"], -x["qty_vendida"]))
    return saida


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("uso: pecas_mais_usadas.py <linhas.tsv> [meses]", file=sys.stderr)
        return 2
    meses = float(sys.argv[2]) if len(sys.argv) > 2 else 8.7
    linhas = []
    with open(sys.argv[1], encoding="utf-8") as f:
        for linha in f:
            partes = linha.rstrip("\n").split("\t")
            if len(partes) == 3:
                linhas.append(partes)
    json.dump({"itens": agregar(linhas, meses), "fora_da_lista": FORA_DA_PRATELEIRA,
               "meses": meses}, sys.stdout, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)

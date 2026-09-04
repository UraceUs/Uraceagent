#!/usr/bin/env python3
"""Testes do markdown do painel, escritos a partir do que QUEBROU.

Cada caso aqui é um padrão real que o agente escreveu num relatório e que
o renderizador não entendeu na primeira versão. Rode antes de mexer em _md:

    python3 adminai/painel/tests/test_md.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from gerar_painel import _md  # noqa: E402

CASOS = [
    # o agente quebra a frase no meio; o par ** só fecha se juntarmos as linhas
    ("negrito atravessando a quebra de linha",
     "`delivered` = **abriu e NÃO\nassinou** · fim.",
     "<b>abriu e NÃO assinou</b>"),
    ("negrito atravessando a quebra dentro de item",
     "- **Nenhum envelope** → a waiver **nunca\n  foi enviada**.",
     "<b>nunca foi enviada</b>"),
    ("negrito dentro de célula de tabela",
     "| Quem | E-mail |\n| --- | --- |\n| Hubbard | misterhub**bb**ard@x.com |",
     "misterhub<b>bb</b>ard"),
    ("linha separadora da tabela não vira dado",
     "| a | b |\n| --- | --- |\n| 1 | 2 |",
     None),  # verificado por ausência, abaixo
    ("citação perde o >",
     "> Gerado por: Administrative AI",
     "Gerado por: Administrative AI"),
    ("asterisco escapado vira asterisco",
     "\\* item literal",
     "* item literal"),
    ("código inline",
     "olhe `~/.urace/logs/`.",
     "<code>~/.urace/logs/</code>"),
    ("wikilink perde os colchetes",
     "ver [[Waiver de responsabilidade]] hoje",
     "ver Waiver de responsabilidade hoje"),
    ("HTML do relatório é escapado, não executado",
     "<script>alert(1)</script>",
     "&lt;script&gt;"),
]


def main():
    falhas = 0
    for nome, entrada, esperado in CASOS:
        saida = _md(entrada)
        ok = (esperado in saida) if esperado else ("---" not in saida)
        print(("  ok   " if ok else " FALHA ") + nome)
        if not ok:
            falhas += 1
            print("        esperava:", esperado)
            print("        saiu    :", saida[:200])
    # nenhum caso pode deixar markdown cru para trás
    for nome, entrada, _ in CASOS:
        if "**" in _md(entrada):
            print(" FALHA  markdown cru sobrou em:", nome)
            falhas += 1
    print(f"\n{len(CASOS)} casos · {falhas} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())

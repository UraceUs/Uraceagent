#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Saúde do grafo do segundo cérebro.

O dono definiu a forma que quer ver crescer: muitos hubs, cada um com seu
punhado de notas atômicas em volta, e os hubs ligados entre si. Este
script mede se o cérebro ainda tem essa forma — e aponta exatamente o que
saiu dela.

Não altera nada. Só lê e relata.

Uso:
    python3 adminai/brain_health.py           # relatório
    python3 adminai/brain_health.py --strict  # sai com rc=1 se houver falha
"""
import os
import re
import sys
import collections

import os as _os
# o cérebro fica ao lado deste script (../brain), não em quem chamou:
# o instalador roda de ~ e antes disso dava "nada encontrado".
VAULT = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "brain")
ARQUIVO = "90_ARQUIVO"          # arquivo morto não conta na saúde
MIN_SAIDA = 2                    # toda nota liga para o hub + pelo menos 1 lateral
MEGA_PALAVRAS = 1800             # acima disso, a nota provavelmente cobre 2 assuntos
                                 # (diário é exceção: é cronológico, cresce por natureza)
HUB_MINIMO = 8                   # entradas para ser considerado hub


def carregar():
    """Devolve {nome: (caminho, texto_sem_codigo, palavras)}."""
    notas = {}
    for raiz, _, arquivos in os.walk(VAULT):
        if "__pycache__" in raiz:
            continue
        for arq in arquivos:
            if not arq.endswith(".md"):
                continue
            caminho = os.path.join(raiz, arq)
            bruto = open(caminho, encoding="utf-8").read()
            # tira bloco de código e código inline: link ali dentro é exemplo,
            # não ligação de verdade
            limpo = re.sub(r"```.*?```", "", bruto, flags=re.S)
            limpo = re.sub(r"`[^`\n]*`", "", limpo)
            notas[arq[:-3]] = (caminho, limpo, len(bruto.split()))
    return notas


def links(texto):
    """Nomes de nota citados. Trata alias e o pipe escapado de tabela."""
    saida = []
    for cru in re.findall(r"\[\[([^\]]+)\]\]", texto):
        alvo = cru.replace("\\|", "|").split("|")[0].split("#")[0].strip()
        if alvo:
            saida.append(alvo)
    return saida


def analisar(notas):
    entrada = collections.Counter()
    saida = {}
    quebrados = collections.defaultdict(set)

    for nome, (_, texto, _) in notas.items():
        alvos = {a for a in links(texto) if a != nome}
        saida[nome] = alvos
        for alvo in alvos:
            if alvo in notas:
                entrada[alvo] += 1
            else:
                quebrados[alvo].add(nome)
    return entrada, saida, quebrados


def ativa(caminho):
    return ARQUIVO not in caminho


def main():
    notas = carregar()
    if not notas:
        print(f"nada encontrado em {VAULT}/")
        return 1

    entrada, saida, quebrados = analisar(notas)
    ativas = {n: v for n, v in notas.items() if ativa(v[0])}
    total_links = sum(len(v) for v in saida.values())

    hubs = [(n, c) for n, c in entrada.most_common() if c >= HUB_MINIMO]
    orfas = sorted(n for n in ativas if entrada[n] == 0)
    poucos = sorted(n for n in ativas if len(saida[n]) < MIN_SAIDA)
    megas = sorted((w, n) for n, (c, _, w) in ativas.items()
                   if w > MEGA_PALAVRAS and "30_DIARIO" not in c)
    duplicados = [n for n in notas if list(notas).count(n) > 1]

    print("=" * 62)
    print("SAÚDE DO CÉREBRO")
    print("=" * 62)
    print(f"notas ativas ....... {len(ativas)}   (+{len(notas)-len(ativas)} no arquivo)")
    print(f"ligações ........... {total_links}")
    print(f"densidade .......... {total_links/len(ativas):.1f} por nota")
    print(f"hubs (>={HUB_MINIMO} entradas) {len(hubs)}")
    print()

    print(f"-- os hubs, do maior para o menor --")
    for nome, contagem in hubs[:15]:
        print(f"   {contagem:4}  {nome}")
    print()

    falhas = []

    if quebrados:
        falhas.append("links quebrados")
        print(f"❌ LINKS QUEBRADOS ({len(quebrados)}) — apontam para nota que não existe")
        for alvo, origens in sorted(quebrados.items()):
            print(f"   [[{alvo}]]  citado em: {', '.join(sorted(origens))}")
        print()

    if duplicados:
        falhas.append("nomes duplicados")
        print(f"❌ NOMES DUPLICADOS ({len(set(duplicados))}) — wikilink fica ambíguo")
        for nome in sorted(set(duplicados)):
            print(f"   {nome}")
        print()

    if orfas:
        falhas.append("notas órfãs")
        print(f"❌ ÓRFÃS ({len(orfas)}) — ninguém linka, viram ilha no grafo")
        for nome in orfas:
            print(f"   {nome}")
        print()

    if poucos:
        falhas.append("notas pouco ligadas")
        print(f"⚠️  POUCO LIGADAS ({len(poucos)}) — menos de {MIN_SAIDA} links de saída")
        print("   toda nota liga para o hub da área + pelo menos uma lateral")
        for nome in poucos:
            print(f"   {len(saida[nome])} link(s)  {nome}")
        print()

    if megas:
        falhas.append("notas grandes")
        print(f"⚠️  GRANDES ({len(megas)}) — acima de {MEGA_PALAVRAS} palavras")
        print("   provavelmente cobrem mais de um assunto; considerar dividir")
        for palavras, nome in sorted(megas, reverse=True):
            print(f"   {palavras:5} palavras  {nome}")
        print()

    if not falhas:
        print("✅ o grafo está na forma: hubs conectados, satélites ligados,")
        print("   nenhuma ilha, nenhum link morto.")
        print()

    print("=" * 62)
    if "--strict" in sys.argv and falhas:
        print("FALHOU:", " · ".join(falhas))
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # alguém fechou o pipe (ex.: | head). Não é erro do relatório.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)

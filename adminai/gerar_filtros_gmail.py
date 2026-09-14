#!/usr/bin/env python3
"""Gera filtros NATIVOS do Gmail a partir dos e-mails reais de cada caixa.

Pedido do dono (14/09): *"leia as tags dos dois e-mails, identifique as keywords
de cada um e coloque nativamente neles os marcadores"*. Ou seja: parar de depender
da IA para classificar o que é determinístico — quem manda o e-mail já diz onde ele
vai.

COMO FUNCIONA
  1. Para cada marcador CONFIRMADO no manual (taxonomia_gmail.py), pega uma amostra
     das mensagens que já estão nele e lê o remetente.
  2. Monta a distribuição remetente → marcadores. Um remetente só vira regra do
     marcador X se a MAIORIA das mensagens dele estiver em X (--share) e houver
     evidência suficiente (--min). Isso evita o caso Amazon, que aparece em
     "Shipping Status" e em "Finances/Shopping" ao mesmo tempo.
  3. Escreve um `mailFilters.xml` que o Gmail importa
     (Configurações → Filtros → Importar filtros) e um relatório em Markdown para
     o dono conferir ANTES de importar.

O QUE ELE NÃO FAZ, DE PROPÓSITO
  * Não escreve nada no Gmail. O escopo `gmail.modify` não cria filtro, e mesmo
    que criasse, filtro é configuração do dono: ele revisa e importa.
  * Não inventa marcador. Só usa os que ele confirmou no manual.
  * Não arquiva nada além de `wNews` — regra dele desde 28/08.
  * Não usa palavra no assunto. Remetente é evidência; palavra solta no assunto
    gera falso positivo em massa. O que não tem remetente estável vai para o
    relatório como decisão dele, não como regra chutada.

    python3 adminai/gerar_filtros_gmail.py --conta urace
    python3 adminai/gerar_filtros_gmail.py --conta support --amostra 40
"""
import argparse
import collections
import os
import re
import sys
import time
import urllib.parse
from xml.sax.saxutils import quoteattr

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "adminai", "mcp"))

import gmail_mcp  # noqa: E402
from command_center.providers.classificar import SISTEMA  # noqa: E402
from command_center.providers.taxonomia_gmail import MANUAL, OK  # noqa: E402

ARQUIVAVEL = "wNews"                 # o único marcador que sai da inbox sozinho
RX_EMAIL = re.compile(r"<([^>]+)>")
# Remetentes genéricos demais para virar regra: pegariam a caixa inteira.
DOMINIOS_PROIBIDOS = {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "icloud.com"}


def _endereco(de):
    """'Fulano <a@b.com>' -> 'a@b.com', em minúsculas."""
    m = RX_EMAIL.search(de or "")
    bruto = (m.group(1) if m else (de or "")).strip().strip("<>").lower()
    return bruto if "@" in bruto else ""


def marcadores_da_caixa(conta):
    """Abre a caixa e devolve os marcadores dela.

    São DOIS carregamentos, e esquecer o segundo custou uma rodada: `_carregar_env`
    lê o ~/.urace/adminai.env, mas quem preenche `_contas` com os tokens é
    `_carregar_contas`. Sem ele o Gmail responde "conta não configurada.
    Disponíveis: []" — que parece falta de credencial e não é."""
    gmail_mcp._carregar_env()
    gmail_mcp._carregar_contas()
    if conta not in gmail_mcp._contas:
        sys.exit(f"ERRO: a caixa {conta}@ não tem token neste servidor "
                 f"({gmail_mcp._sem_token.get(conta, '?')}).\n"
                 f"Rode: python3 adminai/google_auth.py --conta {conta}")
    return gmail_mcp._mapa_labels(conta)


def _req(conta, url, tentativas=4):
    """Como o _req do MCP, mas espera e tenta de novo quando o Gmail limita."""
    for n in range(tentativas):
        try:
            return gmail_mcp._req(conta, url)
        except Exception as e:
            texto = str(e)
            if n == tentativas - 1 or not any(c in texto for c in ("429", "403", "500", "503")):
                raise
            time.sleep(2 ** n)
    return {}


def amostrar(conta, nomes, amostra, verboso=True):
    """remetente -> Counter(marcador), lido das mensagens reais da caixa."""
    por_remetente = collections.defaultdict(collections.Counter)
    id_para_nome = {v: k for k, v in gmail_mcp._mapa_labels(conta).items()}
    vistos = set()
    for i, nome in enumerate(nomes, 1):
        q = urllib.parse.urlencode({"q": f'label:"{nome}"', "maxResults": amostra})
        try:
            r = _req(conta, f"{gmail_mcp.GMAIL}/messages?{q}")
        except Exception as e:
            print(f"  ! {nome}: {type(e).__name__}: {str(e)[:80]}", file=sys.stderr)
            continue
        msgs = r.get("messages", [])
        if verboso:
            print(f"[{i}/{len(nomes)}] {nome}: {len(msgs)} mensagens", file=sys.stderr)
        for m in msgs:
            if m["id"] in vistos:
                continue
            vistos.add(m["id"])
            try:
                d = _req(conta, f"{gmail_mcp.GMAIL}/messages/{m['id']}?format=metadata&metadataHeaders=From")
            except Exception:
                continue
            end = _endereco(gmail_mcp._cabecalho(d, "From"))
            if not end or end.split("@")[-1] in DOMINIOS_PROIBIDOS:
                continue
            # a mensagem conta para TODOS os marcadores que ela tem: é assim que
            # a ambiguidade (Amazon em dois marcadores) aparece nos números
            for lid in d.get("labelIds", []):
                alvo = id_para_nome.get(lid)
                if alvo and alvo in nomes:
                    por_remetente[end][alvo] += 1
    return por_remetente


def regras(por_remetente, share, minimo, max_marcadores=2):
    """marcador -> [(remetente, acertos, total)], só onde a evidência sustenta."""
    saida = collections.defaultdict(list)
    for end, contagem in por_remetente.items():
        total = sum(contagem.values())
        if total < minimo:
            continue
        for alvo, n in contagem.most_common(max_marcadores):
            if n / total >= share:
                saida[alvo].append((end, n, total))
    for alvo in saida:
        saida[alvo].sort(key=lambda x: -x[1])
    return saida


def xml(por_marcador, conta):
    L = ["<?xml version='1.0' encoding='UTF-8'?>",
         "<feed xmlns='http://www.w3.org/2005/Atom' xmlns:apps='http://schemas.google.com/apps/2006'>",
         f"  <title>Filtros URACE — {conta}@urace.us</title>"]
    for alvo in sorted(por_marcador):
        remetentes = " OR ".join(e for e, _n, _t in por_marcador[alvo])
        L += ["  <entry>",
              "    <category term='filter'></category>",
              "    <title>Mail Filter</title>",
              "    <content></content>",
              f"    <apps:property name='from' value={quoteattr(remetentes)}/>",
              f"    <apps:property name='label' value={quoteattr(alvo)}/>"]
        if alvo == ARQUIVAVEL:                      # regra do dono: só propaganda sai da inbox
            L.append("    <apps:property name='shouldArchive' value='true'/>")
        L.append("  </entry>")
    L.append("</feed>")
    return "\n".join(L) + "\n"


def desconhecidos(na_caixa):
    """Marcadores da caixa que não são do dono nem do Gmail.

    Tem de descontar os do sistema (INBOX, SENT, CATEGORY_*…) e o manual INTEIRO,
    não só o confirmado. Sem isso o relatório enchia de ruído e escondia o que
    importa: um marcador novo que apareceu sozinho, como os `Email Review/…` de
    agosto."""
    do_manual = {n for n, _f, _q, _t, _e in MANUAL}
    return sorted(n for n in na_caixa
                  if n not in do_manual and n.upper() not in SISTEMA and not n.startswith("CATEGORY_"))


def relatorio(por_marcador, nomes, na_caixa, conta, share, minimo):
    cobertos = set(por_marcador)
    sem = [n for n in nomes if n not in cobertos]
    fora_do_manual = desconhecidos(na_caixa)
    L = [f"# Filtros do Gmail — {conta}@urace.us", "",
         f"Gerado de mensagens reais da caixa. Um remetente vira regra quando **{int(share*100)}%** ou mais",
         f"das mensagens dele estão naquele marcador e há pelo menos **{minimo}** mensagens dele na amostra.",
         "",
         f"- marcadores com filtro: **{len(cobertos)}**",
         f"- marcadores sem remetente estável: **{len(sem)}**",
         f"- remetentes usados: **{sum(len(v) for v in por_marcador.values())}**", ""]
    if fora_do_manual:
        L += ["## ⚠️ Marcadores na caixa que NÃO estão no manual", "",
              "Não são do sistema do Gmail e não estão no manual que o dono confirmou em 11/09.",
              "A IA os ignora. Confira um por um: os seus entram no manual; os que você não",
              "reconhecer foram postos por outra coisa, como os `Email Review/…` de agosto.", ""]
        L += [f"- `{n}`" for n in fora_do_manual] + [""]
    L += ["## As regras", "", "| Marcador | Remetentes | Evidência |", "|---|---|---|"]
    for alvo in sorted(por_marcador):
        itens = por_marcador[alvo]
        ev = ", ".join(f"{n}/{t}" for _e, n, t in itens[:4])
        rem = "<br>".join(e for e, _n, _t in itens[:8])
        if len(itens) > 8:
            rem += f"<br>… mais {len(itens) - 8}"
        L.append(f"| `{alvo.replace('|', chr(92) + '|')}` | {rem} | {ev} |")
    if sem:
        L += ["", "## Sem remetente estável — decisão sua", "",
              "Estes não têm um remetente que os identifique (são conversa com pessoa, ou o",
              "remetente varia demais). Filtro por palavra no assunto erraria em massa, então",
              "eu **não** inventei regra. Continuam com a triagem da IA, que usa o manual.", ""]
        L += [f"- `{n}`" for n in sem]
    L += ["", "## Como importar", "",
          "Gmail → Ver todas as configurações → **Filtros e endereços bloqueados** →",
          "**Importar filtros** → escolher o arquivo → *Abrir arquivo* → revisar → *Criar filtros*.",
          "Marque **\"Aplicar novos filtros a conversas existentes\"** só se quiser reclassificar o",
          "histórico; sem isso vale para o que chegar daqui para frente.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conta", default="urace", choices=["urace", "support"])
    ap.add_argument("--amostra", type=int, default=30, help="mensagens por marcador")
    ap.add_argument("--share", type=float, default=0.6, help="fatia mínima do remetente no marcador")
    ap.add_argument("--min", dest="minimo", type=int, default=3, help="mensagens mínimas do remetente")
    ap.add_argument("--saida", default=os.path.expanduser("~/.urace"))
    a = ap.parse_args()

    na_caixa = list(marcadores_da_caixa(a.conta))
    nomes = [n for n, _f, _q, _t, e in MANUAL if e == OK and n in na_caixa]
    if not nomes:
        sys.exit(f"nenhum marcador do manual existe na caixa {a.conta}@ — nada a fazer.")
    print(f"caixa {a.conta}@: {len(na_caixa)} marcadores, {len(nomes)} do manual confirmado", file=sys.stderr)

    por_remetente = amostrar(a.conta, nomes, a.amostra)
    por_marcador = regras(por_remetente, a.share, a.minimo)

    os.makedirs(a.saida, exist_ok=True)
    fx = os.path.join(a.saida, f"mailFilters-{a.conta}.xml")
    fr = os.path.join(a.saida, f"filtros-{a.conta}.md")
    with open(fx, "w", encoding="utf-8") as f:
        f.write(xml(por_marcador, a.conta))
    with open(fr, "w", encoding="utf-8") as f:
        f.write(relatorio(por_marcador, nomes, na_caixa, a.conta, a.share, a.minimo))
    print(f"\nescrito: {fx}\nescrito: {fr}", file=sys.stderr)
    print(f"{len(por_marcador)} filtros, {sum(len(v) for v in por_marcador.values())} remetentes")


if __name__ == "__main__":
    main()

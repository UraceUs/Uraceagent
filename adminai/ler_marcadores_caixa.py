#!/usr/bin/env python3
"""Lê os marcadores de uma caixa e mostra o que há dentro de cada um.

É o passo zero do manual, o mesmo que foi feito na urace@ em 11/09: a IA não pode
escrever "o que vai neste marcador" sem antes olhar o que já está lá. O dono foi
explícito: *"leia marcador por marcador que existia antes, entenda o que se coloca
em cada um, me dê o manual e eu confirmo"*.

A support@ nunca passou por isso. O manual de 11/09 saiu inteiro da urace@, e por
isso a triagem daquela caixa enxerga quase nada: `Customer Service/Leads`,
`Customer Service/Service/New Order` e o resto da taxonomia de lá não existem no
manual.

Este script NÃO escreve nada — nem no Gmail, nem no banco. Ele só produz o retrato
para o manual ser escrito e, depois, confirmado pelo dono no painel.

    python3 adminai/ler_marcadores_caixa.py --conta support
    python3 adminai/ler_marcadores_caixa.py --conta support --exemplos 8
"""
import argparse
import importlib.util
import os
import sys
import urllib.parse

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "adminai", "mcp"))

import gmail_mcp  # noqa: E402

# `adminai` não é pacote (não tem __init__.py): carrega o irmão pelo caminho
_spec = importlib.util.spec_from_file_location(
    "gerar_filtros_gmail", os.path.join(RAIZ, "adminai", "gerar_filtros_gmail.py"))
_gf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gf)
_endereco, _req, marcadores_da_caixa = _gf._endereco, _gf._req, _gf.marcadores_da_caixa


def retrato(conta, exemplos, so_novos):
    mapa = marcadores_da_caixa(conta)
    from command_center.providers.taxonomia_gmail import MANUAL
    do_manual = {n for n, _f, _q, _t, _e in MANUAL}
    nomes = sorted(n for n in mapa if not n.isupper() and not n.startswith("CATEGORY_"))
    if so_novos:
        nomes = [n for n in nomes if n not in do_manual]

    L = [f"# Marcadores de {conta}@urace.us — retrato para o manual", "",
         f"{len(nomes)} marcadores" + (" que NÃO estão no manual de 11/09" if so_novos else "") + ".",
         "Nada foi escrito: isto é só leitura, para o manual ser escrito e o dono confirmar.", ""]
    for i, nome in enumerate(nomes, 1):
        print(f"[{i}/{len(nomes)}] {nome}", file=sys.stderr)
        # POR ID: `q=label:"Softwares|Apps/Docusign"` devolve zero, porque o Gmail
        # interpreta o `|` na consulta. Contagem vem de labels/{id}, que dá o número
        # real — `resultSizeEstimate` trava em 201 e engana.
        try:
            det = _req(conta, f"{gmail_mcp.GMAIL}/labels/{mapa[nome]}")
            q = urllib.parse.urlencode({"labelIds": mapa[nome], "maxResults": exemplos})
            r = _req(conta, f"{gmail_mcp.GMAIL}/messages?{q}")
        except Exception as e:
            L += [f"## `{nome}`", f"- (não deu para ler: {type(e).__name__})", ""]
            continue
        msgs = r.get("messages", [])
        L += [f"## `{nome}`",
              f"{det.get('threadsTotal', '?')} conversas · {det.get('messagesTotal', '?')} mensagens", ""]
        for m in msgs:
            try:
                d = _req(conta, f"{gmail_mcp.GMAIL}/messages/{m['id']}"
                                f"?format=metadata&metadataHeaders=From&metadataHeaders=Subject")
            except Exception:
                continue
            de = _endereco(gmail_mcp._cabecalho(d, "From")) or "?"
            assunto = (gmail_mcp._cabecalho(d, "Subject") or "(sem assunto)")[:110]
            L.append(f"- `{de}` — {assunto}")
        L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conta", default="support", choices=["urace", "support"])
    ap.add_argument("--exemplos", type=int, default=5, help="mensagens de amostra por marcador")
    ap.add_argument("--todos", action="store_true", help="inclui também os que já estão no manual")
    ap.add_argument("--saida", default=os.path.expanduser("~/.urace"))
    a = ap.parse_args()
    texto = retrato(a.conta, a.exemplos, so_novos=not a.todos)
    caminho = os.path.join(a.saida, f"marcadores-{a.conta}.md")
    os.makedirs(a.saida, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)
    print(f"escrito {caminho}", file=sys.stderr)
    print(caminho)


if __name__ == "__main__":
    main()

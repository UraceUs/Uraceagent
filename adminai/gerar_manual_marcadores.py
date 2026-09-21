#!/usr/bin/env python3
"""Gera `skills/urace-gmail/MANUAL.md` a partir do manual confirmado pelo dono.

Fonte única de verdade: `command_center/providers/taxonomia_gmail.py`.

Existem dois caminhos que classificam e-mail — a triagem do Command Center
(regra `gmail_triagem`, 07/13/21h) e o agente que lê a skill `urace-gmail`.
Antes disto os dois tinham listas próprias, e a da skill estava de 28/08:
parcial e desatualizada. Agora a skill NÃO tem tabela própria: lê este
arquivo, que é gerado daqui. `test_manual_da_skill_esta_em_dia` quebra se
alguém editar um lado sem o outro.

    python3 adminai/gerar_manual_marcadores.py            # escreve
    python3 adminai/gerar_manual_marcadores.py --conferir # só compara (CI)
"""
import argparse
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from command_center.providers.taxonomia_gmail import (  # noqa: E402
    CONFIRMADO_EM, EXEMPLOS, FORA, MANUAL, OK,
)

DESTINO = os.path.join(RAIZ, "skills", "urace-gmail", "MANUAL.md")


def _celula(texto):
    """`|` dentro de célula quebra a tabela do Markdown (ex.: `LOC | Practice`)."""
    return str(texto).replace("|", "\\|")


def _milhar(n):
    return f"{n:,}".replace(",", ".")


def _data_br(iso):
    a, m, d = iso.split("-")
    return f"{d}/{m}/{a}"


def gerar():
    confirmados = [m for m in MANUAL if m[4] == OK]
    fora = [m for m in MANUAL if m[4] == FORA]
    data = _data_br(CONFIRMADO_EM)

    L = [
        "<!-- GERADO por adminai/gerar_manual_marcadores.py — NÃO EDITE À MÃO.",
        "     A fonte é command_center/providers/taxonomia_gmail.py. -->",
        "",
        "# Manual dos marcadores do Gmail — confirmado pelo dono",
        "",
        f"O dono leu **marcador por marcador** e confirmou em **{data}**: "
        f"**{len(confirmados)} de {len(MANUAL)}**.",
        "",
        "Este é o **único** lugar de onde sai a classificação. Vale também no painel",
        "(Command Center → Gmail → Manual dos marcadores), que lê a mesma fonte.",
        "",
        "## Regras invioláveis",
        "",
        "1. **A IA não cria marcador.** O MCP recusa marcador que não existe na conta.",
        "2. **Só classifica com marcador confirmado aqui.** Marcador que aparecer na",
        "   caixa depois disto entra como `pendente` e a IA **não o enxerga** até o",
        "   dono confirmar no painel. Marcador fora desta lista NÃO EXISTE para ela.",
        "3. **Nada de apagar e nada de spam.** Arquivar, só `wNews`.",
        "4. Na dúvida, **não chutar**: deixa na inbox e pergunta.",
        "",
        "## O que chega → onde vai",
        "",
        "| Chega isto | Vai para |",
        "|---|---|",
    ]
    for chega, vai in EXEMPLOS:
        L.append(f"| {_celula(chega)} | `{_celula(vai)}` |")

    L += ["", "## Os marcadores, um a um", ""]
    familia_atual = None
    for nome, familia, o_que, threads, estado in MANUAL:
        if estado != OK:
            continue
        if familia != familia_atual:
            familia_atual = familia
            L += ["", f"### {_celula(familia)}", "", "| Marcador | O que vai aqui | Threads |", "|---|---|---|"]
        L.append(f"| `{_celula(nome)}` | {_celula(o_que)} | {_milhar(threads)} |")

    if fora:
        L += [
            "",
            "## Fora da triagem — a IA ignora",
            "",
            f"O dono deixou **{len(fora)}** marcadores de fora. Eles existem na caixa, mas",
            "**não são dele** e a IA não os lê nem os aplica. Quem os aplicou foi o conector",
            "do Gmail do claude.ai (token de 16/07, rotulagem entre 9 e 12/08) — não o",
            "Command Center. Ver `brain/40_SISTEMAS/Taxonomia do Gmail.md`.",
            "",
        ]
        for nome, _familia, _o_que, threads, _estado in fora:
            L.append(f"- `{nome}` ({_milhar(threads)} threads)")

    L += ["", f"> Fonte: `command_center/providers/taxonomia_gmail.py` · confirmado em {data}.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conferir", action="store_true", help="só compara, não escreve")
    a = ap.parse_args()
    novo = gerar()
    atual = None
    if os.path.isfile(DESTINO):
        with open(DESTINO, encoding="utf-8") as f:
            atual = f.read()
    if a.conferir:
        if atual != novo:
            sys.exit("MANUAL.md está desatualizado. Rode: python3 adminai/gerar_manual_marcadores.py")
        print("MANUAL.md em dia.")
        return
    if atual == novo:
        print("MANUAL.md já estava em dia.")
        return
    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
    with open(DESTINO, "w", encoding="utf-8") as f:
        f.write(novo)
    print(f"escrito {DESTINO} ({len(novo.splitlines())} linhas)")


if __name__ == "__main__":
    main()

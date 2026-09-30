"""Motion (issue #23): animação só em transform/opacity, durações dos tokens, e o
pedido de menos movimento é respeitado. Lê o CSS do frontend — é um lint de motion."""
import os
import re

import pytest

CSS = os.path.join(os.path.dirname(__file__), "..", "web", "src", "styles")
# O que anima sem recalcular a página (compositor) ou só repinta
PODE = {"transform", "opacity", "background-position", "filter", "box-shadow", "background", "background-color",
        "color", "border-color", "visibility", "stroke-dashoffset"}
LAYOUT = r"(width|height|top|left|right|bottom|margin[-a-z]*|padding[-a-z]*|all)"
EXCECOES = (".app.rail .side{",)     # menu recolhido abre por cima da página (ver o comentário no CSS)


def _css():
    for nome in sorted(os.listdir(CSS)):
        if nome.endswith(".css"):
            with open(os.path.join(CSS, nome), encoding="utf-8") as f:
                yield nome, f.read()


def test_keyframes_so_mexem_no_que_nao_recalcula_a_pagina():
    ruins = []
    for nome, s in _css():
        for m in re.finditer(r"@keyframes\s+([\w-]+)\s*\{((?:[^{}]*\{[^{}]*\})*)\s*\}", s):
            for prop in re.findall(r"([a-z-]+)\s*:", m.group(2)):
                if prop not in PODE:
                    ruins.append(f"{nome} @keyframes {m.group(1)}: {prop}")
    assert not ruins, "\n".join(ruins)


def test_transicao_nao_anima_layout():
    ruins = []
    for nome, s in _css():
        for linha in s.splitlines():
            if any(x in linha for x in EXCECOES):
                continue
            for m in re.finditer(r"transition\s*:\s*([^;}]+)", linha):
                for parte in m.group(1).split(","):
                    prop = parte.strip().split(" ")[0]
                    if re.fullmatch(LAYOUT, prop):
                        ruins.append(f"{nome}: transition {prop} — {linha.strip()[:90]}")
    assert not ruins, "\n".join(ruins)


def test_tokens_de_motion_existem_e_menos_movimento_desliga():
    tokens = dict(_css())["tokens.css"]
    for t in ("--dur-rapida", "--dur-media", "--dur-lenta", "--ease-saida", "--ease-entrada"):
        assert re.search(re.escape(t) + r"\s*:", tokens), t
    assert re.search(r"prefers-reduced-motion:\s*reduce\)\s*\{\s*\*,\s*\*::before,\s*\*::after\s*\{\s*animation-duration:\s*\.01ms!important;"
                     r"\s*transition-duration:\s*\.01ms!important", tokens)


@pytest.mark.parametrize("nome", ["rise", "toastin", "popin", "sheet"])
def test_animacao_de_entrada_usa_os_tokens(nome):
    usos = [m.group(0) for _, s in _css() for m in re.finditer(r"animation\s*:\s*" + nome + r"\b[^;}]*", s)]
    assert usos and all("var(--dur-" in u and "var(--ease-saida)" in u for u in usos), usos

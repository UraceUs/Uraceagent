"""A skill que a IA lê e o manual que o dono confirmou não podem divergir.

Dono, 11/09: *"eu quero garantir que essas novas diretivas de e-mail estejam
atualizadas na IA, no cérebro, em tudo que é parte do nosso projeto."*

Existiam duas listas de marcadores: a do `taxonomia_gmail.py` (confirmada
marcador por marcador) e uma tabela própria dentro de `skills/urace-gmail/SKILL.md`,
parada em 28/08. Duas listas divergem, e quem mandava era a errada. Agora a
skill não tem lista: lê `MANUAL.md`, gerado da fonte única. Estes testes
quebram se alguém reabrir esse buraco.
"""
import os
import re
import subprocess
import sys

import pytest

from command_center.providers.taxonomia_gmail import MANUAL, OK

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(RAIZ, "skills", "urace-gmail", "SKILL.md")
MD = os.path.join(RAIZ, "skills", "urace-gmail", "MANUAL.md")
GERADOR = os.path.join(RAIZ, "adminai", "gerar_manual_marcadores.py")


def _ler(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def test_manual_da_skill_esta_em_dia():
    """`MANUAL.md` é gerado de `taxonomia_gmail.py`. Editou um lado, gere o outro."""
    r = subprocess.run([sys.executable, GERADOR, "--conferir"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_manual_tem_os_confirmados_e_marca_os_de_fora():
    md = _ler(MD)
    confirmados = [n for n, _f, _q, _t, e in MANUAL if e == OK]
    fora = [n for n, _f, _q, _t, e in MANUAL if e != OK]
    assert len(confirmados) == 145
    for nome in confirmados:
        assert f"`{nome.replace('|', chr(92) + '|')}`" in md, f"faltou {nome} no MANUAL.md"
    # os de fora aparecem, mas na seção que manda ignorar
    corpo, _, rodape = md.partition("## Fora da triagem")
    for nome in fora:
        assert nome not in corpo and nome in rodape, f"{nome} precisa ficar só na seção de fora"


def test_skill_nao_tem_taxonomia_propria():
    """A skill aponta para o manual e não recria a lista."""
    s = _ler(SKILL)
    assert "MANUAL.md" in s
    assert "NUNCA criar marcador" in s
    familias = {f for _n, f, _q, _t, _e in MANUAL}
    nomes = {n: e for n, _f, _q, _t, e in MANUAL}
    for token in re.findall(r"`([^`\n]+)`", s):
        if "…" in token or "<" in token or token.endswith(".md") or token.endswith(".py"):
            continue
        if token.split("/")[0] not in familias:
            continue
        assert token in nomes, f"a skill cita `{token}`, que não está no manual do dono"
        assert nomes[token] == OK, f"a skill cita `{token}`, que o dono deixou de fora"


@pytest.mark.parametrize("caminho", [SKILL, MD])
def test_arquivos_existem_e_nao_estao_vazios(caminho):
    assert len(_ler(caminho)) > 500

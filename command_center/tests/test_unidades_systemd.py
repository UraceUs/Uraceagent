"""As unidades systemd do deploy.

Dono/extensão da VPS, 22/09: os serviços automáticos avisavam a cada recarga por causa
do `%20` no link de documentação, e o serviço de waivers morreu às 07:33 com código 1
**sem deixar mensagem nenhuma** no log. As duas coisas são da unidade, não do código.
"""
import glob
import os
import re

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UNIDADES = sorted(glob.glob(os.path.join(RAIZ, "adminai", "deploy", "**", "*.service"), recursive=True))
ONESHOT_DE_AGENTE = ("urace-waivers", "urace-asana-sync", "urace-triagem-email")


def _texto(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def test_existem_unidades():
    assert UNIDADES, "nenhuma unidade encontrada"


@pytest.mark.parametrize("caminho", UNIDADES, ids=lambda c: os.path.basename(c))
def test_porcento_sempre_escapado(caminho):
    """No systemd `%` abre especificador. `%20` num caminho vira "Unknown specifier" a
    cada recarga — o aviso que a extensão viu. Escapa-se dobrando."""
    for n, linha in enumerate(_texto(caminho).splitlines(), 1):
        for m in re.finditer(r"%(.)", linha):
            if m.group(1) == "%":
                continue
            assert not m.group(1).isdigit(), f"{os.path.basename(caminho)}:{n}: '%{m.group(1)}' precisa ser '%%{m.group(1)}'"


@pytest.mark.parametrize("nome", ONESHOT_DE_AGENTE)
def test_oneshot_de_agente_carimba_como_morreu(nome):
    """Falhar em silêncio é o pior modo de falhar: não dá para consertar o que não
    deixou rastro. Toda unidade oneshot que chama o agente grava resultado e código
    de saída no próprio log."""
    caminho = os.path.join(RAIZ, "adminai", "deploy", f"{nome}.service")
    if not os.path.exists(caminho):
        pytest.skip(f"{nome} não existe neste repositório")
    s = _texto(caminho)
    assert "ExecStopPost=" in s, f"{nome}: sem carimbo de saída"
    pós = next(l for l in s.splitlines() if l.startswith("ExecStopPost="))
    assert "$SERVICE_RESULT" in pós and "$EXIT_STATUS" in pós, f"{nome}: o carimbo não diz por que morreu"
    destino = re.search(r"(?m)^StandardOutput=append:(.+)$", s)
    assert destino and destino.group(1).strip() in pós, f"{nome}: o carimbo tem de ir para o mesmo log"


def test_o_instalador_copia_todas_as_unidades():
    """Lista escrita à mão esquece; glob não. Em 22/09 um comando copiou 3 unidades e
    deixou a 4ª (urace-brain-health) com o aviso de specifier."""
    sh = os.path.join(RAIZ, "adminai", "deploy", "instalar_unidades.sh")
    assert os.path.exists(sh), "falta o instalador das unidades"
    texto = _texto(sh)
    assert "find" in texto and "*.service" in texto, "o instalador tem de varrer, não listar"
    for caminho in UNIDADES:
        assert os.path.basename(caminho) not in texto, \
            f"{os.path.basename(caminho)} está escrito à mão no instalador — use o glob"

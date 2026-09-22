"""As ferramentas de linha de comando têm de achar o Python do Command Center.

A extensão da VPS bateu duas vezes em `No module named 'fastapi'` — a segunda já com o
`adminai/_venv.py` no lugar. A causa: o `bin/python` de um venv é um **symlink** para o
Python do sistema, e a guarda anti-laço comparava `realpath`, que resolve o symlink.
Os dois lados davam o mesmo caminho, e a troca de interpretador nunca acontecia.
"""
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from adminai import _venv  # noqa: E402


@pytest.fixture()
def venv_falso(tmp_path, monkeypatch):
    """Um venv como os de verdade: bin/python é symlink para o Python do sistema."""
    binario = tmp_path / "cc-venv" / "bin"
    binario.mkdir(parents=True)
    link = binario / "python"
    os.symlink(sys.executable, link)
    monkeypatch.setattr(_venv, "CANDIDATOS", (str(link),))
    monkeypatch.delenv(_venv.MARCA, raising=False)
    return str(link)


def test_symlink_do_venv_nao_engana_mais(venv_falso, monkeypatch):
    """O teste que teria pego o bug: `realpath` dos dois lados é o mesmo."""
    assert os.path.realpath(venv_falso) == os.path.realpath(sys.executable), "o cenário é esse"
    monkeypatch.setattr(_venv.importlib.util, "find_spec", lambda _n: None)   # falta a dependência
    assert _venv.escolher_python() == os.path.abspath(venv_falso)


def test_com_a_dependencia_presente_nao_troca_nada(venv_falso, monkeypatch):
    monkeypatch.setattr(_venv.importlib.util, "find_spec", lambda _n: object())
    assert _venv.escolher_python() is None


def test_nao_entra_em_laco(venv_falso, monkeypatch):
    """Se a troca já foi tentada e ainda falta dependência, deixa o erro aparecer."""
    monkeypatch.setattr(_venv.importlib.util, "find_spec", lambda _n: None)
    monkeypatch.setenv(_venv.MARCA, "1")
    assert _venv.escolher_python() is None


def test_sem_venv_a_vista_nao_inventa(monkeypatch, tmp_path):
    monkeypatch.setattr(_venv, "CANDIDATOS", (str(tmp_path / "nao-existe"),))
    monkeypatch.setattr(_venv.importlib.util, "find_spec", lambda _n: None)
    monkeypatch.delenv(_venv.MARCA, raising=False)
    assert _venv.escolher_python() is None


def test_toda_ferramenta_de_linha_de_comando_chama_o_bootstrap():
    """Ferramenta nova que importe command_center tem de passar por aqui."""
    import glob
    faltando = []
    for caminho in glob.glob(os.path.join(RAIZ, "adminai", "*.py")):
        with open(caminho, encoding="utf-8") as f:
            texto = f.read()
        if "from command_center" not in texto or os.path.basename(caminho).startswith("_"):
            continue
        if "garantir_venv()" not in texto:
            faltando.append(os.path.basename(caminho))
    assert not faltando, f"sem garantir_venv(): {faltando}"

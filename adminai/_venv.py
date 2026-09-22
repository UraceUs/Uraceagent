"""Garante que a ferramenta roda sob o Python do Command Center.

A extensão da VPS bateu nisto em 22/09: `python3 adminai/sincronizar.py docusign`
morreu com `No module named 'fastapi'`, porque o `python3` do sistema não tem as
dependências. Ela achou o venv sozinha e repetiu — mas quem usa a ferramenta não
deveria precisar saber disso.

Importe e chame `garantir_venv()` ANTES de importar qualquer coisa de `command_center`.
"""
import importlib.util
import os
import sys

# O venv que o serviço do Command Center usa. Em ordem de preferência.
CANDIDATOS = (
    os.environ.get("CC_PYTHON"),
    os.path.expanduser("~/.urace/cc-venv/bin/python"),
    "/home/ubuntu/.urace/cc-venv/bin/python",
)
SENTINELA = "fastapi"          # se isto importa, estamos no Python certo


def garantir_venv():
    """Se faltar dependência e houver venv, re-executa este mesmo comando nele.

    Não instala nada, não mexe em `~/.urace/`: só troca de interpretador. Sem venv à
    vista, deixa o `ImportError` falar por si — errar alto é melhor que errar quieto."""
    if importlib.util.find_spec(SENTINELA) is not None:
        return
    atual = os.path.realpath(sys.executable)
    for cand in CANDIDATOS:
        if not cand:
            continue
        cand = os.path.expanduser(cand)
        if os.path.exists(cand) and os.path.realpath(cand) != atual:
            print(f"(usando o Python do Command Center: {cand})", file=sys.stderr)
            os.execv(cand, [cand, os.path.abspath(sys.argv[0]), *sys.argv[1:]])

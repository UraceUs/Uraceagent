"""A ponte de vendas (salesagent/) tem os testes dela como scripts (`python3 test_x.py`), fora do
pytest. Os que provam o atendimento humano (14/10) — a trava da IA na saída, o caso no painel e
a volta só por ordem do painel — rodam aqui também, para o CI de cada PR pegar regressão."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPTS = ["test_handoff.py", "test_never_silent.py", "test_sdr.py", "test_human_loop.py", "test_customer_memory.py"]


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_da_ponte(script, tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CC_", "HANDOFF_", "WA_"))}
    env["URACE_DIR"] = str(tmp_path)               # cada script também cria o próprio diretório
    r = subprocess.run([sys.executable, str(RAIZ / "salesagent" / "tests" / script)], cwd=RAIZ, env=env,
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (r.stdout[-3000:] + r.stderr[-2000:])

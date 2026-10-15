"""O deploy só pula a bateria quando o CI do GitHub confirma o verde DESTE commit (#277).

Dono, 15/10: *"rode os testes ... no seu ambiente virtual, porque os testes estão demorando de 15 a 20
minutos ... comita, empurra para o GitHub e testa por lá, antes da gente jogar ali na VPS"*.

O risco de pular testes é subir código sem prova. Por isso a regra é assimétrica: só `ok` quando os três
jobs terminaram e passaram; qualquer dúvida vira "roda aqui".
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "adminai" / "deploy" / "command_center" / "ci_verde.py"
DEPLOY = RAIZ / "adminai" / "deploy" / "command_center" / "servir_command_center.sh"

_spec = importlib.util.spec_from_file_location("ci_verde", SCRIPT)
ci = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ci)


def _run(nome, status="completed", conclusao="success", inicio="2026-10-15T16:00:00Z"):
    return {"name": nome, "status": status, "conclusion": conclusao, "started_at": inicio}


VERDE = [_run("Python — ruff + pytest"), _run("Frontend — tsc + oxlint + build"),
         _run("End-to-end — Playwright no Chromium"), _run("iOS — build e TestFlight")]


def test_os_tres_jobs_verdes_pulam_a_bateria():
    assert ci.veredito({"check_runs": VERDE}) == ("ok", "")


def test_qualquer_duvida_roda_a_bateria_na_vps():
    vermelho = [*VERDE[:2], _run("End-to-end — Playwright no Chromium", conclusao="failure")]
    rodando = [*VERDE[:2], _run("End-to-end — Playwright no Chromium", status="in_progress", conclusao=None)]
    sem_e2e = VERDE[:2]
    for dados in ({"check_runs": vermelho}, {"check_runs": rodando}, {"check_runs": sem_e2e},
                  {"message": "Not Found"}, None, [], "texto"):
        ok, motivo = ci.veredito(dados)
        assert ok == "" and motivo, dados


def test_re_run_verde_vale_sobre_a_falha_antiga():
    """Um job re-rodado ganha outro check com o mesmo nome: vale o mais recente (15/10, #256 e #267)."""
    antigo = _run("End-to-end — Playwright no Chromium", conclusao="failure", inicio="2026-10-15T16:20:00Z")
    novo = _run("End-to-end — Playwright no Chromium", inicio="2026-10-15T17:13:00Z")
    assert ci.veredito({"check_runs": [*VERDE[:2], antigo, novo]}) == ("ok", "")
    assert ci.veredito({"check_runs": [*VERDE[:2], novo, antigo]}) == ("ok", "")


def test_pela_linha_de_comando_json_quebrado_nao_vira_ok():
    for entrada in ("", "{", "<html>rate limit</html>"):
        r = subprocess.run([sys.executable, str(SCRIPT)], input=entrada, capture_output=True, text=True)
        assert r.stdout.strip() != "ok", entrada
    r = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps({"check_runs": VERDE}),
                       capture_output=True, text=True)
    assert r.stdout.strip() == "ok"


def test_o_deploy_so_pula_com_ok_e_cai_na_bateria_no_resto():
    texto = DEPLOY.read_text(encoding="utf-8")
    assert "ci_verde.py" in texto and "/commits/$SHA/check-runs" in texto
    assert 'if [ "$CI" = "ok" ]; then' in texto, "só o ok exato pula"
    assert "URACE_DEPLOY_TESTES" in texto, "dá para forçar a bateria"
    senao = texto.split('if [ "$CI" = "ok" ]; then', 1)[1].split("\nfi", 1)[0].split("else", 1)[1]
    assert "-m pytest -q command_center/tests" in senao, "sem confirmação, a bateria roda na VPS"

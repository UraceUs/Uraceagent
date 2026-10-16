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


# ------------------------------------------------------------------ #286: a tag ci-verde, lida pelo git
# Deploy de 15/10: a API do GitHub respondeu 404 na VPS (o repositório é privado, a VPS não tem login) e a
# bateria rodou lá de novo. O CI agora grava `ci-verde/<sha>`; o deploy a lê com a chave do `git pull`.
WORKFLOW = RAIZ / ".github" / "workflows" / "ci.yml"


def _comando_da_tag():
    texto = DEPLOY.read_text(encoding="utf-8")
    linha = next(x for x in texto.splitlines() if "ls-remote" in x)
    return linha.strip().removeprefix("if ").split(" >/dev/null")[0]


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                   env={"GIT_AUTHOR_NAME": "Teste", "GIT_AUTHOR_EMAIL": "teste@example.com", "HOME": str(cwd),
                        "GIT_COMMITTER_NAME": "Teste", "GIT_COMMITTER_EMAIL": "teste@example.com",
                        "PATH": "/usr/bin:/bin:/usr/local/bin"})


def test_o_deploy_acha_a_tag_do_ci_pelo_git_e_so_ela_pula(tmp_path):
    remoto, repo = tmp_path / "remoto.git", tmp_path / "repo"
    _git("init", "-q", "--bare", str(remoto), cwd=tmp_path)
    _git("init", "-q", str(repo), cwd=tmp_path)
    (repo / "a.txt").write_text("x")
    _git("add", "a.txt", cwd=repo)
    _git("commit", "-q", "-m", "um", cwd=repo)
    _git("remote", "add", "origin", str(remoto), cwd=repo)
    _git("push", "-q", "origin", "HEAD:refs/heads/claude/commandcenter-vps", cwd=repo)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    cmd = _comando_da_tag()
    assert "ls-remote --exit-code origin" in cmd and '"refs/tags/ci-verde/$SHA"' in cmd

    def acha():
        return subprocess.run(["bash", "-c", cmd], env={"REPO": str(repo), "SHA": sha, "PATH": "/usr/bin:/bin:/usr/local/bin"},
                              capture_output=True).returncode == 0
    assert not acha(), "sem a tag do CI, o deploy roda a bateria"
    _git("push", "-q", "origin", f"HEAD:refs/tags/ci-verde/{'0' * 40}", cwd=repo)
    assert not acha(), "a tag de OUTRO commit não vale"
    _git("push", "-q", "origin", f"HEAD:refs/tags/ci-verde/{sha}", cwd=repo)
    assert acha(), "com a tag deste commit, pula"


def test_a_tag_vem_antes_da_api_e_a_api_so_vale_com_ok():
    texto = DEPLOY.read_text(encoding="utf-8")
    passo3 = texto.split("# --------------------------------------------------------------- 3. testes", 1)[1].split("# ----", 1)[0]
    assert passo3.index("ls-remote") < passo3.index("api.github.com"), "a tag primeiro (repositório privado)"
    assert 'if [ "$API" = "ok" ]; then CI="ok"' in passo3
    for credencial in ("Authorization", "GH_TOKEN", "GITHUB_TOKEN", "$TOKEN"):
        assert credencial not in passo3, "nenhum token na VPS"


def test_o_ci_grava_a_tag_so_com_os_tres_jobs_verdes_no_branch_da_vps():
    import yaml
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    verde = jobs["verde"]
    assert set(verde["needs"]) == {"python", "web", "e2e"}, "só depois dos três jobs"
    assert "github.event_name == 'push'" in verde["if"] and "refs/heads/claude/commandcenter-vps" in verde["if"]
    assert verde["permissions"] == {"contents": "write"}, "a permissão mínima, só neste job"
    corpo = verde["steps"][0]["run"]
    assert "refs/tags/ci-verde/${{ github.sha }}" in corpo and 'sha="${{ github.sha }}"' in corpo
    assert all("permissions" not in j for k, j in jobs.items() if k != "verde"), "os outros jobs seguem só leitura"

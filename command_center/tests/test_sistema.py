"""Atualizar o sistema pelo painel (17/09): só ADMIN; o pedido vira um arquivo que o path unit
do servidor vê; o log da última rodada é lido do arquivo; nada de parâmetro vai para o shell."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from command_center.api import auth, sistema
from command_center.api.main import app
from command_center.db import aplicar_schema, conectar, um

B = "/ops/api"
SENHA = "senha-forte-123"


@pytest.fixture(scope="module")
def cli():
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc-sys.sqlite")
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "admin@urace.us", "Admin", "ADMIN", SENHA)
    auth.criar_usuario(con, "op@urace.us", "Op", "OPERATOR", SENHA)
    con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def entra(cli, email):
    assert cli.post(B + "/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def test_atualizacao_so_admin_pedido_vira_arquivo_e_log_e_lido(cli, monkeypatch, tmp_path):
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    monkeypatch.setattr(sistema, "_systemctl", lambda *a: "enabled" if a[0] == "is-enabled" else "inactive")
    h = entra(cli, "op@urace.us")
    assert cli.get(f"{B}/system/update", headers=h).status_code == 403
    assert cli.post(f"{B}/system/update", headers=h).status_code == 403
    h = entra(cli, "admin@urace.us")
    e = cli.get(f"{B}/system/update", headers=h).json()
    assert e["instalado"] and not e["rodando"] and e["versao"]["commit"] and e["ultima"]["resultado"] is None
    r = cli.post(f"{B}/system/update", headers=h)
    assert r.status_code == 200 and (tmp_path / "deploy.request").read_text().strip().endswith("admin@urace.us")
    con = conectar()
    try:
        assert um(con, "SELECT 1 AS x FROM audit_logs WHERE event='system.update'")
    finally:
        con.close()
    # com o pedido na fila, um segundo clique é recusado; o log da última rodada mostra o resultado
    assert cli.post(f"{B}/system/update", headers=h).status_code == 409
    (tmp_path / "deploy-painel.log").write_text("lixo antigo\n=== deploy 2026-09-17T15:00:00-04:00 (pedido pelo painel) ===\n-- 1/7 venv\n185 passed\n=== fim: 0 ===\n")
    (tmp_path / "deploy.request").unlink()
    e = cli.get(f"{B}/system/update", headers=h).json()
    assert e["ultima"]["resultado"] is True and "lixo" not in e["ultima"]["log"] and e["ultima"]["inicio"].startswith("2026-09-17T15:00")
    (tmp_path / "deploy-painel.log").write_text("=== deploy 2026-09-17T16:00:00-04:00 ===\n!! o serviço não subiu\n=== fim: 1 ===\n")
    assert cli.get(f"{B}/system/update", headers=h).json()["ultima"]["resultado"] is False


def test_sem_o_path_unit_o_botao_explica(cli, monkeypatch, tmp_path):
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    monkeypatch.setattr(sistema, "_systemctl", lambda *a: "")
    h = entra(cli, "admin@urace.us")
    r = cli.post(f"{B}/system/update", headers=h)
    assert r.status_code == 503 and "terminal" in r.json()["detail"]

"""Interruptor do Chase (dono, 06/10): só ADMIN; troca só a linha SDR_MODO do bridge.env (tokens
ficam); deixa o pedido que o path unit do servidor vê; nível fora da lista é recusado."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from command_center.api import auth, sdr
from command_center.api.main import app
from command_center.db import aplicar_schema, conectar, um

B = "/ops/api"
SENHA = "senha-forte-123"


@pytest.fixture(scope="module")
def cli():
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc-sdr.sqlite")
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "admin@urace.us", "Admin", "ADMIN", SENHA)
    auth.criar_usuario(con, "gerente@urace.us", "Gerente", "MANAGER", SENHA)
    con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def entra(cli, email):
    assert cli.post(B + "/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


@pytest.fixture()
def pasta(tmp_path, monkeypatch):
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    monkeypatch.setattr(sdr, "ponte_no_ar", lambda: True)
    monkeypatch.setattr(sdr, "instalado", lambda: True)
    (tmp_path / "bridge.env").write_text("KOMMO_TOKEN=segredo-123\nSDR_MODO=observar\nHUMAN_WHATSAPP=+14075550100\n")
    os.chmod(tmp_path / "bridge.env", 0o600)
    return tmp_path


def test_so_admin_ve_e_troca(cli, pasta):
    h = entra(cli, "gerente@urace.us")
    assert cli.get(B + "/sdr", headers=h).status_code == 403
    assert cli.put(B + "/sdr", json={"nivel": "atender"}, headers=h).status_code == 403
    assert "SDR_MODO=observar" in (pasta / "bridge.env").read_text()


def test_ligar_e_desligar_o_chase_troca_so_a_linha_do_nivel(cli, pasta):
    h = entra(cli, "admin@urace.us")
    e = cli.get(B + "/sdr", headers=h).json()
    assert e["nivel"] == "observar" and not e["chase_ligado"]
    r = cli.put(B + "/sdr", json={"nivel": "atender"}, headers=h)
    assert r.status_code == 200 and r.json()["chase_ligado"] and r.json()["reiniciando"]
    env = (pasta / "bridge.env").read_text()
    assert env.splitlines() == ["KOMMO_TOKEN=segredo-123", "SDR_MODO=atender", "HUMAN_WHATSAPP=+14075550100"]
    assert oct(os.stat(pasta / "bridge.env").st_mode & 0o777) == "0o600", "o bridge.env tem token: continua 600"
    assert (pasta / "sdr.request").read_text().startswith("atender admin@urace.us")
    cli.put(B + "/sdr", json={"nivel": "organizar"}, headers=h)
    assert "SDR_MODO=organizar" in (pasta / "bridge.env").read_text()
    a = um(conectar(), "SELECT detail FROM audit_logs WHERE event='sdr.nivel' ORDER BY id DESC LIMIT 1")
    assert '"depois": "organizar"' in a["detail"] and "segredo" not in a["detail"]


def test_nivel_fora_da_lista_e_recusado_e_nada_muda(cli, pasta):
    h = entra(cli, "admin@urace.us")
    r = cli.put(B + "/sdr", json={"nivel": "atender; rm -rf /"}, headers=h)
    assert r.status_code == 400
    assert "SDR_MODO=observar" in (pasta / "bridge.env").read_text() and not (pasta / "sdr.request").exists()


def test_sem_linha_no_bridge_env_a_linha_e_acrescentada(pasta):
    (pasta / "bridge.env").write_text("KOMMO_TOKEN=x\n")
    assert sdr.nivel_gravado() == "observar"
    sdr.gravar_nivel("organizar")
    assert (pasta / "bridge.env").read_text() == "KOMMO_TOKEN=x\nSDR_MODO=organizar\n"

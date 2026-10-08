"""Cofre de logins e senhas (#162).

Dono, 08/10: "somente no acesso livre crie uma sessão de logins e senhas de onde fiquem seguras e
consigam ser armazenadas por lá".
"""
import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from command_center.api import auth
from command_center.api.main import app
from command_center.db import aplicar_schema, conectar, todos, um
from command_center.providers import cofre

SENHA = "senha-forte-123"
DONO = "eduardoffresende@gmail.com"          # acesso livre (auth.ACESSO_LIVRE)
B = "/ops/api/cofre"
SEGREDO = "W0rdPr3ss-segredo!"


@pytest.fixture(scope="module")
def cli():
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc-cofre.sqlite")
    os.environ["CC_COFRE_CHAVE"] = cofre.nova_chave()
    con = conectar(); aplicar_schema(con)
    dono = auth.criar_usuario(con, DONO, "Eduardo", "ADMIN", SENHA)
    auth.criar_usuario(con, "admin@urace.us", "Outro Admin", "ADMIN", SENHA)
    chave = auth.criar_chave(con, "teste", "ADMIN", dono, somente_leitura=False)["chave"]
    con.commit(); con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        c.chave = chave
        yield c


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def test_so_o_acesso_livre_pelo_navegador_entra(cli):
    h = entra(cli, "admin@urace.us")
    assert cli.get(B).status_code == 403                                   # ADMIN comum não
    assert cli.post(B, headers=h, json={"name": "x"}).status_code == 403
    cli.cookies.clear()
    k = {"Authorization": f"Bearer {cli.chave}"}
    assert cli.get(B, headers=k).status_code == 403                        # chave do próprio dono também não
    assert cli.get(B, headers={"X-API-Key": cli.chave}).status_code == 403
    h = entra(cli, DONO)
    assert cli.get(B, headers={"Authorization": f"Bearer {cli.chave}"}).status_code == 403   # cookie + chave: não
    r = cli.get(B)
    assert r.status_code == 200 and r.json()["ligado"] and r.json()["desbloqueado_ate"] is None
    assert r.headers["cache-control"] == "private, no-cache" or "no-store" in r.headers["cache-control"]


def test_guarda_cifrado_pede_a_senha_para_ver_e_a_auditoria_nao_leva_o_valor(cli):
    h = entra(cli, DONO)
    novo = {"name": "WordPress urace.us", "url": "https://urace.us/wp-admin", "username": "eduardo@urace.us",
            "senha": SEGREDO, "nota": "conta do Eduardo"}
    assert cli.post(B, headers=h, json=novo).status_code == 423            # trancado: confirme a senha
    assert cli.post(f"{B}/desbloquear", headers=h, json={"senha": "errada"}).status_code == 401
    assert cli.post(f"{B}/desbloquear", headers=h, json={"senha": SENHA}).status_code == 200
    it = cli.post(B, headers=h, json=novo).json()
    assert it["tem_senha"] and "senha" not in it and "secret_enc" not in it
    lista = cli.get(B).json()["itens"]
    assert [i["name"] for i in lista] == ["WordPress urace.us"] and SEGREDO not in json.dumps(lista)
    con = conectar()
    try:
        bruto = um(con, "SELECT * FROM vault_items WHERE id=?", (it["id"],))
        assert SEGREDO not in json.dumps(dict(bruto)) and bruto["secret_enc"].startswith("v1:")
        logs = json.dumps([dict(a) for a in todos(con, "SELECT * FROM audit_logs WHERE event LIKE 'vault.%'")])
        assert SEGREDO not in logs and "conta do Eduardo" not in logs
    finally:
        con.close()
    r = cli.post(f"{B}/{it['id']}/revelar", headers=h)
    assert r.status_code == 200 and r.json() == {"id": it["id"], "senha": SEGREDO, "nota": "conta do Eduardo"}
    assert r.headers["cache-control"] == "no-store"
    assert cli.post(f"{B}/travar", headers=h).status_code == 200
    assert cli.post(f"{B}/{it['id']}/revelar", headers=h).status_code == 423
    con = conectar()
    try:
        ev = [a["event"] for a in todos(con, "SELECT event FROM audit_logs WHERE event LIKE 'vault.%' ORDER BY id")]
        assert ev == ["vault.unlock_failed", "vault.unlocked", "vault.created", "vault.revealed", "vault.locked"]
    finally:
        con.close()


def test_mudar_arquivar_e_restaurar_sem_apagar(cli):
    h = entra(cli, DONO)
    cli.post(f"{B}/desbloquear", headers=h, json={"senha": SENHA})
    it = cli.post(B, headers=h, json={"name": "QuickBooks", "senha": "a1"}).json()
    cli.patch(f"{B}/{it['id']}", headers=h, json={"senha": "b2", "username": "urace@urace.us"})
    assert cli.post(f"{B}/{it['id']}/revelar", headers=h).json()["senha"] == "b2"
    assert cli.post(f"{B}/{it['id']}/arquivar", headers=h).json()["archived"] == 1
    assert "QuickBooks" not in [i["name"] for i in cli.get(B).json()["itens"]]
    assert "QuickBooks" in [i["name"] for i in cli.get(f"{B}?arquivados=true").json()["itens"]]
    assert cli.post(f"{B}/{it['id']}/restaurar", headers=h).json()["archived"] == 0


def test_sem_chave_o_cofre_fica_desligado_e_diz_por_que(cli, monkeypatch):
    h = entra(cli, DONO)
    monkeypatch.delenv("CC_COFRE_CHAVE")
    r = cli.get(B).json()
    assert r["ligado"] is False and "CC_COFRE_CHAVE" in r["motivo"]
    assert cli.post(f"{B}/desbloquear", headers=h, json={"senha": SENHA}).status_code == 503


def test_chave_trocada_nao_abre_o_que_outra_chave_guardou(monkeypatch):
    monkeypatch.setenv("CC_COFRE_CHAVE", cofre.nova_chave())
    guardado = cofre.cifrar("segredo", "senha")
    assert cofre.decifrar(guardado, "senha") == "segredo"
    with pytest.raises(cofre.ChaveErrada):
        cofre.decifrar(guardado, "nota")                                   # o campo entra como dado associado
    monkeypatch.setenv("CC_COFRE_CHAVE", cofre.nova_chave())
    with pytest.raises(cofre.ChaveErrada):
        cofre.decifrar(guardado, "senha")

"""Área do cliente (#40): conta de maior de idade, pilotos, medidas e a separação da equipe."""
import os
from datetime import date

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, todos, um  # noqa: E402
from command_center.providers import portal  # noqa: E402

P = "/ops/api/portal"
SENHA = "senha-forte-123"


def anos_atras(n, dias=0):
    h = portal.hoje()
    try:
        d = h.replace(year=h.year - n)
    except ValueError:                       # 29/02
        d = h.replace(year=h.year - n, day=28)
    return date.fromordinal(d.toordinal() + dias).isoformat()


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    c.commit(); c.close()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def csrf(cli):
    return {"X-CSRF": cli.cookies.get("cp_csrf")}


CONTA = {"name": "Maria Santos", "email": "maria@example.com", "password": "corrida-segura-9",
         "birth_date": "1985-04-12", "phone": "(407) 555-0142", "address_line1": "100 Main St", "city": "Orlando",
         "state": "fl", "zip": "32809", "accept_terms": True}


def cadastra(cli, **mais):
    r = cli.post(f"{P}/signup", json={**CONTA, **mais})
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ maioridade
def test_idade_pelo_calendario_da_florida():
    assert portal.idade(date(2008, 10, 1), em=date(2026, 9, 30)) == 17
    assert portal.idade(date(2008, 9, 30), em=date(2026, 9, 30)) == 18


def test_quem_abre_a_conta_tem_18_anos(cli):
    r = cli.post(f"{P}/signup", json={**CONTA, "birth_date": anos_atras(18, dias=1)})
    assert r.status_code == 400 and "18 or older" in r.json()["detail"], "um dia antes dos 18: não"
    assert cli.post(f"{P}/signup", json={**CONTA, "birth_date": anos_atras(18)}).status_code == 201, "no dia dos 18: sim"


def test_cadastro_valida_e_normaliza(cli):
    for ruim, msg in [({"email": "sem-arroba"}, "valid email"), ({"accept_terms": False}, "accept the terms"),
                      ({"zip": "ABC"}, "ZIP"), ({"phone": "123"}, "phone"), ({"password": "curta"}, "8 characters"),
                      ({"birth_date": "2999-01-01"}, "future")]:
        r = cli.post(f"{P}/signup", json={**CONTA, **ruim})
        assert r.status_code == 400 and msg in r.json()["detail"], (ruim, r.text)
    d = cadastra(cli, i_am_driver=True)
    assert (d["email"], d["state"], d["phone"], d["linked"]) == ("maria@example.com", "FL", "407-555-0142", False)
    assert [p["name"] for p in d["drivers"]] == ["Maria Santos"] and d["drivers"][0]["is_self"]
    assert "pw_hash" not in d and "pw_salt" not in d
    cli.cookies.clear()
    assert "already exists" in cli.post(f"{P}/signup", json={**CONTA, "email": "MARIA@example.com"}).json()["detail"]


def test_campo_desconhecido_e_recusado(cli):
    assert cli.post(f"{P}/signup", json={**CONTA, "client_id": 1}).status_code == 422, "ninguém se vincula sozinho"


# ------------------------------------------------------------------ login
def test_login_senha_errada_e_limite(cli):
    cadastra(cli); cli.cookies.clear()
    assert cli.get(f"{P}/me").status_code == 401
    r1 = cli.post(f"{P}/login", json={"email": "maria@example.com", "password": "errada-errada"})
    r2 = cli.post(f"{P}/login", json={"email": "ninguem@example.com", "password": "errada-errada"})
    assert r1.status_code == r2.status_code == 401 and r1.json() == r2.json(), "não revela quem existe"
    assert cli.post(f"{P}/login", json={"email": "Maria@Example.com", "password": CONTA["password"]}).status_code == 200
    assert cli.get(f"{P}/me").json()["name"] == "Maria Santos"
    cli.post(f"{P}/logout", headers=csrf(cli))
    assert cli.get(f"{P}/me").status_code == 401
    for _ in range(auth.MAX_FALHAS):
        cli.post(f"{P}/login", json={"email": "maria@example.com", "password": "errada-errada"})
    assert cli.post(f"{P}/login", json={"email": "maria@example.com", "password": CONTA["password"]}).status_code == 429


def test_conta_do_cliente_nao_entra_no_painel_e_a_equipe_nao_entra_na_conta(cli):
    cadastra(cli)
    for rota in ("/ops/api/clients", "/ops/api/dashboard", "/ops/api/users", "/ops/api/compras"):
        assert cli.get(rota).status_code == 401, rota
    cli.cookies.clear()
    cli.post("/ops/api/auth/login", json={"email": "ger@urace.us", "password": SENHA})
    assert cli.get(f"{P}/me").status_code == 401, "sessão da equipe não é sessão de cliente"


def test_escrita_exige_csrf(cli):
    cadastra(cli)
    assert cli.patch(f"{P}/me", json={"city": "Kissimmee"}).status_code == 403
    assert cli.patch(f"{P}/me", json={"city": "Kissimmee"}, headers=csrf(cli)).json()["city"] == "Kissimmee"


def test_limite_de_cadastros_por_conexao(cli, monkeypatch):
    from command_center.api import portal as api
    monkeypatch.setattr(api, "MAX_CADASTROS_POR_HORA", 2)
    cadastra(cli, email="a@example.com"); cli.cookies.clear()
    cadastra(cli, email="b@example.com"); cli.cookies.clear()
    assert cli.post(f"{P}/signup", json={**CONTA, "email": "c@example.com"}).status_code == 429


# ------------------------------------------------------------------ conta e pilotos
def test_responsavel_atualiza_os_proprios_dados(cli):
    cadastra(cli)
    d = cli.patch(f"{P}/me", headers=csrf(cli), json={"phone": "4075550199", "address_line1": "200 Race Way", "zip": "34741"}).json()
    assert (d["phone"], d["address_line1"], d["zip"], d["city"]) == ("407-555-0199", "200 Race Way", "34741", "Orlando")
    assert cli.patch(f"{P}/me", headers=csrf(cli), json={"birth_date": anos_atras(10)}).status_code == 400
    assert cli.patch(f"{P}/me", headers=csrf(cli), json={"email": "x@y.com"}).status_code == 422, "e-mail não muda por aqui"


def test_piloto_crianca_com_medidas(cli):
    cadastra(cli)
    d = cli.post(f"{P}/drivers", headers=csrf(cli), json={
        "name": "Lucas Santos", "birth_date": anos_atras(9),
        "measures": {"height_in": "52", "weight_lb": 61.5, "chest_in": 26, "suit_size": "130", "shoe_size": "2",
                     "desconhecida": 9, "waist_in": ""}}).json()
    p = next(x for x in d["drivers"] if x["name"] == "Lucas Santos")
    assert p["age"] == 9 and not p["is_self"]
    assert p["measures"] == {"height_in": 52.0, "weight_lb": 61.5, "chest_in": 26.0, "suit_size": "130", "shoe_size": "2"}
    assert p["measures_updated_at"]
    r = cli.post(f"{P}/drivers", headers=csrf(cli), json={"name": "Xu Li", "measures": {"height_in": 500}})
    assert r.status_code == 400 and "looks wrong" in r.json()["detail"]


def test_medida_nova_carimba_a_data(cli):
    cadastra(cli)
    pid = cli.post(f"{P}/drivers", headers=csrf(cli), json={"name": "Lucas", "measures": {"height_in": 50}}).json()["drivers"][0]["id"]
    c = conectar(); c.execute("UPDATE portal_pilots SET measures_updated_at='2026-01-01T00:00:00Z' WHERE id=?", (pid,)); c.commit(); c.close()
    p = cli.patch(f"{P}/drivers/{pid}", headers=csrf(cli), json={"notes": "canhoto"}).json()["drivers"][0]
    assert p["measures_updated_at"].startswith("2026-01-01"), "nota não é medida"
    p = cli.patch(f"{P}/drivers/{pid}", headers=csrf(cli), json={"measures": {"height_in": 53}}).json()["drivers"][0]
    assert p["measures"]["height_in"] == 53 and not p["measures_updated_at"].startswith("2026-01-01")


def test_piloto_de_outra_conta_nao_existe_para_mim(cli):
    cadastra(cli)
    pid = cli.post(f"{P}/drivers", headers=csrf(cli), json={"name": "Lucas"}).json()["drivers"][0]["id"]
    cli.cookies.clear()
    cadastra(cli, email="outra@example.com")
    assert cli.patch(f"{P}/drivers/{pid}", headers=csrf(cli), json={"name": "Hackeado"}).status_code == 404
    assert um(conectar(), "SELECT name FROM portal_pilots WHERE id=?", (pid,))["name"] == "Lucas"


def test_so_um_eu_mesmo_por_conta(cli):
    cadastra(cli, i_am_driver=True)
    r = cli.post(f"{P}/drivers", headers=csrf(cli), json={"name": "Maria de novo", "is_self": True})
    assert r.status_code == 400 and "already" in r.json()["detail"]


def test_trocar_senha_derruba_as_outras_sessoes(cli):
    cadastra(cli)
    outro = TestClient(app, base_url="https://cc.test")
    outro.post(f"{P}/login", json={"email": "maria@example.com", "password": CONTA["password"]})
    assert outro.get(f"{P}/me").status_code == 200
    assert cli.post(f"{P}/me/password", headers=csrf(cli), json={"current_password": "errada", "new_password": "nova-senha-123"}).status_code == 400
    assert cli.post(f"{P}/me/password", headers=csrf(cli), json={"current_password": CONTA["password"], "new_password": "nova-senha-123"}).status_code == 200
    assert cli.get(f"{P}/me").status_code == 200, "esta sessão continua"
    assert outro.get(f"{P}/me").status_code == 401, "a outra caiu"


def test_tudo_fica_auditado_sem_senha(cli):
    cadastra(cli)
    cli.patch(f"{P}/me", headers=csrf(cli), json={"city": "Kissimmee"})
    linhas = todos(conectar(), "SELECT event, detail FROM audit_logs WHERE event LIKE 'portal.%'")
    assert {x["event"] for x in linhas} >= {"portal.signup", "portal.account.update"}
    assert all(CONTA["password"] not in (x["detail"] or "") for x in linhas)

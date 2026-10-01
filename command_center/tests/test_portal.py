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
from command_center.tests.dados_portal import MEDIDAS, piloto  # noqa: E402

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
        "name": "Lucas Santos", "birth_date": anos_atras(9), "notes": "Started this year.",
        "measures": {"height_in": "52", "weight_lb": 61.5, "chest_in": 26, "waist_in": 24, "hips_in": 27, "suit_size": "130",
                     "shoe_size": "2", "desconhecida": 9, "inseam_in": ""}}).json()
    p = next(x for x in d["drivers"] if x["name"] == "Lucas Santos")
    assert p["age"] == 9 and not p["is_self"]
    assert p["measures"] == {"height_in": 52.0, "weight_lb": 61.5, "chest_in": 26.0, "waist_in": 24.0, "hips_in": 27.0,
                             "suit_size": "130", "shoe_size": "2"}
    assert p["measures_updated_at"] and p["measures_status"] == "ok" and p["missing"] == []
    r = cli.post(f"{P}/drivers", headers=csrf(cli), json=piloto("Xu Li", measures={**MEDIDAS, "height_in": 500}))
    assert r.status_code == 400 and "looks wrong" in r.json()["detail"]


def test_salvar_as_medidas_carimba_a_data(cli):
    """Salvar as medidas, mesmo iguais, é o cliente confirmar que estão certas (#54)."""
    cadastra(cli)
    pid = cli.post(f"{P}/drivers", headers=csrf(cli), json=piloto("Lucas Santos")).json()["drivers"][0]["id"]
    c = conectar(); c.execute("UPDATE portal_pilots SET measures_updated_at='2026-01-01T00:00:00Z' WHERE id=?", (pid,)); c.commit(); c.close()
    p = cli.patch(f"{P}/drivers/{pid}", headers=csrf(cli), json={"notes": "canhoto"}).json()["drivers"][0]
    assert p["measures_updated_at"].startswith("2026-01-01"), "nota não é medida"
    p = cli.patch(f"{P}/drivers/{pid}", headers=csrf(cli), json={"measures": MEDIDAS}).json()["drivers"][0]
    assert not p["measures_updated_at"].startswith("2026-01-01") and p["measures_status"] == "ok", "mesmas medidas, data nova"
    p = cli.patch(f"{P}/drivers/{pid}", headers=csrf(cli), json={"measures": {**MEDIDAS, "height_in": 53}}).json()["drivers"][0]
    assert p["measures"]["height_in"] == 53


def test_piloto_de_outra_conta_nao_existe_para_mim(cli):
    cadastra(cli)
    pid = cli.post(f"{P}/drivers", headers=csrf(cli), json=piloto("Lucas Santos")).json()["drivers"][0]["id"]
    cli.cookies.clear()
    cadastra(cli, email="outra@example.com")
    assert cli.patch(f"{P}/drivers/{pid}", headers=csrf(cli), json={"name": "Hackeado Silva"}).status_code == 404
    assert um(conectar(), "SELECT name FROM portal_pilots WHERE id=?", (pid,))["name"] == "Lucas Santos"


def test_so_um_eu_mesmo_por_conta(cli):
    cadastra(cli, i_am_driver=True)
    r = cli.post(f"{P}/drivers", headers=csrf(cli), json=piloto("Maria de novo", is_self=True))
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


# ------------------------------------------------------------------ #54: obrigatórios, outro país, validade das medidas
def test_responsavel_tem_os_campos_obrigatorios(cli):
    for falta, rotulo in (("phone", "phone"), ("address_line1", "street address"), ("city", "city"), ("zip", "ZIP code"),
                          ("state", "state")):
        r = cli.post(f"{P}/signup", json={**CONTA, falta: ""})
        assert r.status_code == 400 and rotulo in r.json()["detail"], (falta, r.text)
    assert cli.post(f"{P}/signup", json={**CONTA, "name": "Maria"}).json()["detail"].startswith("Enter your full name")
    cadastra(cli)
    r = cli.patch(f"{P}/me", headers=csrf(cli), json={"city": ""})
    assert r.status_code == 400 and "city" in r.json()["detail"], "o obrigatório não se apaga"


def test_cliente_de_outro_pais(cli):
    d = cadastra(cli, country="BR", phone_country="55", phone="(11) 98765-4321", state="SP", zip="01310-100", city="São Paulo")
    assert (d["country"], d["phone_country"], d["phone"], d["zip"]) == ("BR", "+55", "+55 11987654321", "01310-100")
    assert d["missing"] == []
    cli.cookies.clear()
    d = cadastra(cli, email="uk@example.com", country="GB", phone_country="+44", phone="+44 20 7946 0958", state="", zip="sw1a 1aa")
    assert d["phone"] == "+44 2079460958" and d["zip"] == "SW1A 1AA", "fora dos EUA, região é opcional"
    cli.cookies.clear()
    r = cli.post(f"{P}/signup", json={**CONTA, "email": "x@example.com", "state": "Florida"})
    assert r.status_code == 400 and "2-letter" in r.json()["detail"], "nos EUA, o estado é a sigla"
    assert cli.post(f"{P}/signup", json={**CONTA, "email": "y@example.com", "phone_country": "abc"}).status_code == 400


def test_piloto_tem_os_campos_obrigatorios_e_rede_social(cli):
    cadastra(cli)
    sem = {k: v for k, v in MEDIDAS.items() if k != "hips_in"}
    r = cli.post(f"{P}/drivers", headers=csrf(cli), json=piloto("Lucas Santos", measures=sem))
    assert r.status_code == 400 and r.json()["detail"] == "Please fill in: hips."
    r = cli.post(f"{P}/drivers", headers=csrf(cli), json=piloto("Lucas Santos", notes=""))
    assert "karting experience" in r.json()["detail"]
    r = cli.post(f"{P}/drivers", headers=csrf(cli), json=piloto("Lucas Santos", birth_date=None))
    assert "date of birth" in r.json()["detail"]
    assert "full name" in cli.post(f"{P}/drivers", headers=csrf(cli), json=piloto("Lucas")).json()["detail"]
    d = cli.post(f"{P}/drivers", headers=csrf(cli), json=piloto("Lucas Santos", social="lucas.kart")).json()["drivers"]
    assert d[0]["social"] == "@lucas.kart"
    pid = d[0]["id"]
    assert cli.patch(f"{P}/drivers/{pid}", headers=csrf(cli), json={"social": "instagram.com/lucas"}).json()["drivers"][0]["social"] \
        == "https://instagram.com/lucas"
    assert cli.patch(f"{P}/drivers/{pid}", headers=csrf(cli), json={"social": "não é perfil!!"}).status_code == 400


def test_o_proprio_responsavel_como_piloto_nasce_incompleto(cli):
    d = cadastra(cli, i_am_driver=True)
    p = d["drivers"][0]
    assert p["measures_status"] == "faltando" and {"height_in", "experience"} <= set(p["missing"])


def _envelhece(pid, dias):
    from datetime import datetime, timedelta, timezone
    t = (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    c = conectar(); c.execute("UPDATE portal_pilots SET measures_updated_at=? WHERE id=?", (t, pid)); c.commit(); c.close()


def test_medidas_avisam_com_30_dias_e_travam_com_60(cli):
    from command_center.providers import servicos_site
    from command_center.tests.test_agenda_sessoes import abre, proximo
    c = conectar(); abre(c); sid = servicos_site.criar(c, None, {"name": "Arrive and Drive", "price": 719}); c.commit(); c.close()
    cadastra(cli)
    pid = cli.post(f"{P}/drivers", headers=csrf(cli), json=piloto("Lucas Santos")).json()["drivers"][0]["id"]
    marcar = lambda d: cli.post(f"{P}/bookings", headers=csrf(cli), json={"date": proximo(d).isoformat(), "period": "manha",  # noqa: E731
                                                                         "driver_id": pid, "service_id": sid})
    _envelhece(pid, 29)
    assert cli.get(f"{P}/me").json()["drivers"][0]["measures_status"] == "ok"
    _envelhece(pid, 31)
    p = cli.get(f"{P}/me").json()["drivers"][0]
    assert (p["measures_status"], p["measures_days"]) == ("aviso", 31)
    assert marcar(2).status_code == 201, "com aviso ainda marca"
    _envelhece(pid, 61)
    assert cli.get(f"{P}/me").json()["drivers"][0]["measures_status"] == "vencida"
    r = marcar(3)
    assert r.status_code == 400 and "60 days" in r.json()["detail"]
    cli.patch(f"{P}/drivers/{pid}", headers=csrf(cli), json={"measures": MEDIDAS})
    assert marcar(3).status_code == 201, "atualizou, marca de novo"


def test_conta_incompleta_nao_marca(cli):
    from command_center.providers import servicos_site
    from command_center.tests.test_agenda_sessoes import abre, proximo
    c = conectar(); abre(c); sid = servicos_site.criar(c, None, {"name": "Arrive and Drive", "price": 719}); c.commit(); c.close()
    cadastra(cli)
    pid = cli.post(f"{P}/drivers", headers=csrf(cli), json=piloto("Lucas Santos")).json()["drivers"][0]["id"]
    c = conectar(); c.execute("UPDATE portal_accounts SET address_line1=NULL"); c.commit(); c.close()   # conta antiga, de antes da regra
    assert cli.get(f"{P}/me").json()["missing"] == ["address_line1"]
    r = cli.post(f"{P}/bookings", headers=csrf(cli), json={"date": proximo(2).isoformat(), "period": "manha", "driver_id": pid, "service_id": sid})
    assert r.status_code == 400 and "account holder" in r.json()["detail"]


def test_painel_do_cliente(cli):
    cadastra(cli)
    d = cli.get(f"{P}/dashboard").json()
    assert d["next_session"] is None and d["last_session"] is None and d["upcoming"] == 0
    assert (d["measures_warn_days"], d["measures_limit_days"]) == (30, 60)
    assert d["account"]["name"] == "Maria Santos"

"""Client ID por driver (#65). Dono, 01/10: *"um client id para cada driver"* — cada piloto da
conta tem o seu card; a sessão, o contrato e o histórico de um irmão não caem no card do outro."""
import os

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, todos, um  # noqa: E402
from command_center.providers import contrato, identidade, vinculo_site as vs  # noqa: E402

SENHA = "senha-forte-123"


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def familia(con, ligar=True):
    """Joseph Kurian, responsável, com dois drivers: Enzo (já tem card) e Lia (não tem)."""
    enzo = inserir(con, "clients", name="Joseph Kurian", pilot_name="Enzo Kurian", email="joekur001@gmail.com",
                   phone="407-555-0142", status="ACTIVE", source="asana", monthly_sessions=4, plan_type="monthly")
    conta = inserir(con, "portal_accounts", email="joekur001@gmail.com", pw_salt="x", pw_hash="x", name="Joseph Kurian",
                    birth_date="1980-01-01", phone="407-555-0142", terms_accepted_at="2026-09-30T00:00:00Z")
    p_enzo = inserir(con, "portal_pilots", account_id=conta, name="Enzo Kurian", birth_date="2014-03-02")
    p_lia = inserir(con, "portal_pilots", account_id=conta, name="Lia Kurian", birth_date="2016-05-09")
    if ligar:
        vs.vincular(con, conta, enzo, None)
    return enzo, conta, p_enzo, p_lia


def test_vincular_a_conta_da_o_card_ao_driver_dele_e_nao_ao_irmao(con):
    enzo, conta, p_enzo, p_lia = familia(con)
    assert um(con, "SELECT client_id FROM portal_pilots WHERE id=?", (p_enzo,))["client_id"] == enzo
    assert um(con, "SELECT client_id FROM portal_pilots WHERE id=?", (p_lia,))["client_id"] is None, "a Lia não herda o card do Enzo"


def test_conta_ja_vinculada_antes_herda_na_migracao(con):
    enzo, conta, p_enzo, p_lia = familia(con, ligar=False)
    con.execute("UPDATE portal_accounts SET client_id=? WHERE id=?", (enzo, conta))   # como estava antes do #65
    aplicar_schema(con)
    assert um(con, "SELECT client_id FROM portal_pilots WHERE id=?", (p_enzo,))["client_id"] == enzo
    assert um(con, "SELECT client_id FROM portal_pilots WHERE id=?", (p_lia,))["client_id"] is None
    aplicar_schema(con)                                  # idempotente
    assert um(con, "SELECT COUNT(*) AS n FROM portal_pilots WHERE client_id IS NOT NULL")["n"] == 1


def test_criar_card_do_irmao_e_cada_um_com_o_seu_client_id(con):
    enzo, conta, p_enzo, p_lia = familia(con)
    lia = vs.criar_cliente_driver(con, p_lia, None)
    c = um(con, "SELECT * FROM clients WHERE id=?", (lia,))
    assert lia != enzo and (c["name"], c["pilot_name"], c["pilot_dob"], c["email"]) == \
        ("Joseph Kurian", "Lia Kurian", "2016-05-09", "joekur001@gmail.com"), "responsável paga, a Lia é a piloto"
    with pytest.raises(vs.ErroVinculo, match="já tem card"):
        vs.criar_cliente_driver(con, p_lia, None)
    with pytest.raises(vs.ErroVinculo, match="cada driver tem o seu"):
        vs.vincular_driver(con, p_lia, enzo, None)
    assert {d["name"]: d["client_id"] for d in vs.drivers_da_conta(con, conta)} == {"Enzo Kurian": enzo, "Lia Kurian": lia}


def test_sync_nao_junta_os_irmaos_mesmo_com_o_mesmo_email(con):
    """O deduplicar une cards do mesmo e-mail/telefone/responsável. Ligados a drivers diferentes, não."""
    enzo, conta, p_enzo, p_lia = familia(con)
    lia = vs.criar_cliente_driver(con, p_lia, None)
    identidade.deduplicar(con)
    assert um(con, "SELECT id FROM clients WHERE id=?", (enzo,)) and um(con, "SELECT id FROM clients WHERE id=?", (lia,))
    assert identidade.nao_unir(con, enzo, lia)
    assert not any({p["a"]["id"], p["b"]["id"]} == {enzo, lia} for p in identidade.candidatos_duplicados(con)), \
        "irmão não aparece como duplicado"


def test_duplicado_de_verdade_continua_unindo_e_leva_o_vinculo(con):
    enzo, conta, p_enzo, _ = familia(con)
    dup = inserir(con, "clients", name="Joseph Kurian", pilot_name="Enzo Kurian", email="JOEKUR001@gmail.com", status="ACTIVE", source="asana")
    assert identidade.unir(con, dup, enzo, "teste", "mesmo e-mail") is True
    assert um(con, "SELECT client_id FROM portal_pilots WHERE id=?", (p_enzo,))["client_id"] == dup, "o driver vai junto para o card que fica"
    assert um(con, "SELECT client_id FROM portal_accounts WHERE id=?", (conta,))["client_id"] == dup


def test_sessao_do_site_conta_no_card_do_driver(con):
    enzo, conta, p_enzo, p_lia = familia(con)
    lia = vs.criar_cliente_driver(con, p_lia, None)
    inserir(con, "bookings", account_id=conta, pilot_id=p_enzo, date="2026-10-05", period="manha", status="confirmada")
    inserir(con, "bookings", account_id=conta, pilot_id=p_lia, date="2026-10-06", period="manha", status="confirmada")
    inserir(con, "bookings", account_id=conta, pilot_id=p_lia, date="2026-10-07", period="manha", status="pendente")
    assert contrato.usadas(con, enzo, "2026-10")["total"] == 1, "a sessão da Lia não gasta o contrato do Enzo"
    assert contrato.usadas(con, lia, "2026-10")["total"] == 2
    from command_center.providers import agenda_sessoes as ag
    assert {b["driver"]: b["client_id"] for b in ag.lista(con)} == {"Enzo Kurian": enzo, "Lia Kurian": lia}


def test_driver_sem_card_nao_cai_no_card_do_irmao(con):
    enzo, conta, p_enzo, p_lia = familia(con)
    inserir(con, "bookings", account_id=conta, pilot_id=p_lia, date="2026-10-06", period="manha", status="confirmada")
    assert contrato.usadas(con, enzo, "2026-10")["total"] == 0


def test_historico_do_portal_separado_por_driver(con):
    enzo, conta, p_enzo, p_lia = familia(con)
    lia = vs.criar_cliente_driver(con, p_lia, None)
    inserir(con, "tasks", client_id=enzo, title="Enzo Kurian_Urace Academy_4 stroke [1/4]", project="U-RACE", status="completed", due_on="2026-09-20")
    inserir(con, "tasks", client_id=lia, title="Lia Kurian_Urace Daily_Rental Kart [1/1]", project="U-RACE", status="open", due_on="2026-10-08")
    h = vs.historico(con, conta)
    assert [(x["date"], x["driver"]) for x in h["services"]] == [("2026-10-08", "Lia Kurian"), ("2026-09-20", "Enzo Kurian")]


def test_desvincular_o_driver_principal_passa_o_principal_ao_irmao(con):
    enzo, conta, p_enzo, p_lia = familia(con)
    lia = vs.criar_cliente_driver(con, p_lia, None)
    vs.desvincular_driver(con, p_enzo)
    assert um(con, "SELECT client_id FROM portal_accounts WHERE id=?", (conta,))["client_id"] == lia
    assert um(con, "SELECT id FROM clients WHERE id=?", (enzo,)), "desvincular não apaga card"


def test_card_mostra_de_qual_driver_ele_e(con):
    enzo, conta, p_enzo, p_lia = familia(con)
    lia = vs.criar_cliente_driver(con, p_lia, None)
    assert vs.conta_do_cliente(con, lia)["driver_id"] == p_lia
    assert vs.conta_do_cliente(con, enzo)["driver_id"] == p_enzo


@pytest.fixture()
def cli(con):
    auth.criar_usuario(con, "op@urace.us", "Operador", "OPERATOR", SENHA)
    auth.criar_usuario(con, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    con.commit()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def test_api_por_driver_com_auditoria(cli, con):
    enzo, conta, p_enzo, p_lia = familia(con); con.commit()
    h = entra(cli, "op@urace.us")
    d = {x["id"]: x for x in cli.get("/ops/api/site/contas?filtro=todas").json()["contas"]}[conta]
    assert [(x["name"], x["client_id"]) for x in d["drivers_list"]] == [("Enzo Kurian", enzo), ("Lia Kurian", None)]
    r = cli.post(f"/ops/api/site/drivers/{p_lia}/criar-cliente", headers=h)
    assert r.status_code == 201, r.text
    lia = r.json()["client_id"]
    assert cli.post(f"/ops/api/site/drivers/{p_lia}/vincular", headers=h, json={"client_id": enzo}).status_code == 400
    assert cli.post(f"/ops/api/site/drivers/{p_lia}/desvincular", headers=h).status_code == 403, "desvincular é do gerente"
    h = entra(cli, "ger@urace.us")
    assert cli.post(f"/ops/api/site/drivers/{p_lia}/desvincular", headers=h).status_code == 200
    assert cli.post(f"/ops/api/site/drivers/{p_lia}/vincular", headers=h, json={"client_id": lia}).status_code == 200
    assert cli.post("/ops/api/client-merge", headers=h, json={"keep_id": enzo, "drop_id": lia}).status_code == 409, "irmãos não se unem"
    ev = [a["event"] for a in todos(conectar(), "SELECT event FROM audit_logs")]
    assert {"portal.driver.client.create", "portal.driver.unlink", "portal.driver.link"} <= set(ev)

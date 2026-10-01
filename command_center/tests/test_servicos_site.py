"""Serviços e preços da agenda (#50): o gerente muda o preço sem código, e quem já marcou
fica com o valor do dia."""
import os

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, todos, um  # noqa: E402
from command_center.providers import agenda_sessoes as ag, servicos_site as sv  # noqa: E402
from command_center.tests.test_agenda_sessoes import abre, conta, proximo  # noqa: E402

SENHA = "senha-forte-123"


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def test_preco_aceita_o_jeito_que_a_equipe_digita():
    assert sv.preco("719") == 719.0
    assert sv.preco("$1,856.90") == 1856.9
    assert sv.preco(769.9) == 769.9
    for ruim in ("-5", "abc", "1.999", "", None, 100_001):
        with pytest.raises(sv.ErroServico):
            sv.preco(ruim)


def test_sem_servico_cadastrado_ninguem_marca(con):
    abre(con)
    c, p = conta(con)
    with pytest.raises(ag.ErroAgenda, match="type of session"):
        ag.agendar(con, c, proximo(2).isoformat(), "manha", p)
    assert sv.para_cliente(con) == [], "nada inventado"


def test_mudar_o_preco_nao_muda_quem_ja_marcou(con):
    abre(con)
    c, p = conta(con)
    sid = sv.criar(con, None, {"name": "Arrive and Drive", "price": "719"})
    b = ag.agendar(con, c, proximo(2).isoformat(), "manha", p, servico_id=sid)
    assert sv.mudar(con, None, sid, {"price": "799.90"}) == {"price": (719.0, 799.9)}
    assert um(con, "SELECT price, service_name FROM bookings WHERE id=?", (b,)) == {"price": 719.0, "service_name": "Arrive and Drive"}
    b2 = ag.agendar(con, c, proximo(3).isoformat(), "manha", p, servico_id=sid)
    assert um(con, "SELECT price FROM bookings WHERE id=?", (b2,))["price"] == 799.9
    assert ag.do_cliente(con, c)[0]["price"] in (719.0, 799.9) and ag.do_cliente(con, c)[0]["service"] == "Arrive and Drive"


def test_desativar_tira_da_area_do_cliente_sem_apagar(con):
    abre(con)
    c, p = conta(con)
    sid = sv.criar(con, None, {"name": "Kart School", "price": 1856.9})
    sv.mudar(con, None, sid, {"active": False})
    assert sv.para_cliente(con) == [] and len(sv.lista(con)) == 1
    with pytest.raises(ag.ErroAgenda, match="type of session"):
        ag.agendar(con, c, proximo(2).isoformat(), "manha", p, servico_id=sid)


def test_item_do_quickbooks_tem_de_existir_no_espelho(con):
    with pytest.raises(sv.ErroServico, match="QuickBooks"):
        sv.criar(con, None, {"name": "Coaching", "price": 369, "qbo_item_id": "999"})
    inserir(con, "qbo_items", id="45", name="Urace Daily", type="Service", price=500)
    sid = sv.criar(con, None, {"name": "Coaching", "price": 369, "qbo_item_id": "45"})
    assert [i["id"] for i in sv.itens_qbo(con)] == ["45"]
    assert um(con, "SELECT qbo_item_id FROM booking_services WHERE id=?", (sid,))["qbo_item_id"] == "45"


def test_nome_repetido_e_recusado(con):
    sv.criar(con, None, {"name": "Arrive and Drive", "price": 719})
    with pytest.raises(sv.ErroServico, match="já existe"):
        sv.criar(con, None, {"name": "arrive and drive", "price": 500})


@pytest.fixture()
def cli(con):
    auth.criar_usuario(con, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    auth.criar_usuario(con, "op@urace.us", "Operador", "OPERATOR", SENHA)
    con.commit()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def test_so_o_gerente_muda_o_preco_e_fica_auditado(cli):
    h = entra(cli, "op@urace.us")
    assert cli.post("/ops/api/site/servicos", headers=h, json={"name": "Arrive and Drive", "price": 719}).status_code == 403
    assert cli.get("/ops/api/site/servicos").status_code == 200, "a operação vê"
    h = entra(cli, "ger@urace.us")
    sid = cli.post("/ops/api/site/servicos", headers=h, json={"name": "Arrive and Drive", "price": "719.00",
                                                              "description": "One session with our kart"}).json()["id"]
    r = cli.patch(f"/ops/api/site/servicos/{sid}", headers=h, json={"price": "749"})
    assert r.status_code == 200 and r.json()["servicos"][0]["price"] == 749.0
    assert cli.patch(f"/ops/api/site/servicos/{sid}", headers=h, json={"price": "-1"}).status_code == 400
    aud = todos(conectar(), "SELECT detail FROM audit_logs WHERE event='booking.service.update'")
    assert '"antes": 719.0' in aud[0]["detail"] and '"depois": 749.0' in aud[0]["detail"]
    cli.cookies.clear()
    r = cli.post("/ops/api/portal/signup", json={"name": "Maria Santos", "email": "m@example.com", "password": "corrida-segura-9",
                                                 "birth_date": "1985-04-12", "accept_terms": True, "i_am_driver": True})
    disp = cli.get("/ops/api/portal/availability").json()
    assert disp["services"] == [{"id": sid, "name": "Arrive and Drive", "description": "One session with our kart", "price": 749.0}]
    assert "qbo_item_id" not in disp["services"][0], "o cliente não vê o item do QuickBooks"

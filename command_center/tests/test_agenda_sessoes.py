"""Agenda de sessões (#41): semana, bloqueios, capacidade, antecedência e quem decide."""
import os
from datetime import date, datetime, timedelta

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import atencao, auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, todos  # noqa: E402
from command_center.providers import agenda_sessoes as ag, servicos_site  # noqa: E402

SENHA = "senha-forte-123"
FL = ag.FUSO


def proximo(dia_semana, a_partir=3):
    """Uma data futura (>= a_partir dias) naquele dia da semana (0=segunda)."""
    d = datetime.now(FL).date() + timedelta(days=a_partir)
    while d.weekday() != dia_semana:
        d += timedelta(days=1)
    return d


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def conta(con, email="c@example.com"):
    cid = inserir(con, "portal_accounts", email=email, pw_salt="x", pw_hash="x", name="Cliente Teste", birth_date="1980-01-01",
                  terms_accepted_at="2026-09-30T00:00:00Z")
    pid = inserir(con, "portal_pilots", account_id=cid, name="Piloto Teste")
    return cid, pid


def sv(con):
    """Um serviço ativo cadastrado pela equipe (#50): sem ele, ninguém marca."""
    s = todos(con, "SELECT id FROM booking_services WHERE active=1 LIMIT 1")
    return s[0]["id"] if s else servicos_site.criar(con, None, {"name": "Arrive and Drive", "price": 719})


def abre(con, dias=range(7), periodos=("manha", "tarde"), cap=1):
    ag.mudar_semana(con, [{"weekday": d, "period": p, "open": True, "capacity": cap} for d in dias for p in periodos])


def periodo(con, d, p, visao="cliente"):
    return ag.disponibilidade(con, d, d, visao=visao)["dias"][0]["periods"][p]


# ------------------------------------------------------------------ regras
def test_nada_abre_sozinho(con):
    d = proximo(2)
    assert not periodo(con, d, "manha")["open"] and periodo(con, d, "manha", "equipe")["reason"] == "fechado"
    assert not any(x["any_open"] for x in ag.disponibilidade(con)["dias"])


def test_so_manha_so_tarde_e_dia_todo(con):
    ag.mudar_semana(con, [{"weekday": 5, "period": "manha", "open": True}, {"weekday": 6, "period": "tarde", "open": True},
                          {"weekday": 2, "period": "manha", "open": True}, {"weekday": 2, "period": "tarde", "open": True}])
    sab, dom, qua = proximo(5), proximo(6), proximo(2)
    assert periodo(con, sab, "manha")["open"] and not periodo(con, sab, "tarde")["open"] and not periodo(con, sab, "dia")["open"]
    assert not periodo(con, dom, "manha")["open"] and periodo(con, dom, "tarde")["open"]
    assert periodo(con, qua, "dia")["open"], "dia todo = manhã + tarde"


def test_bloquear_o_dia_toda_semana_e_fechar_os_dois_periodos(con):
    abre(con)
    ag.mudar_semana(con, [{"weekday": 0, "period": "manha", "open": False}, {"weekday": 0, "period": "tarde", "open": False}])
    seg = proximo(0)
    assert not ag.disponibilidade(con, seg, seg)["dias"][0]["any_open"]
    assert ag.disponibilidade(con, seg + timedelta(days=1), seg + timedelta(days=1))["dias"][0]["any_open"]


def test_bloqueio_de_data_de_intervalo_e_de_periodo(con):
    abre(con)
    d = proximo(3, a_partir=5)
    ag.bloquear(con, None, d.isoformat(), period="dia", reason="corrida em Ocala")
    ag.bloquear(con, None, (d + timedelta(days=2)).isoformat(), (d + timedelta(days=4)).isoformat(), period="dia")
    ag.bloquear(con, None, (d + timedelta(days=1)).isoformat(), period="tarde")
    disp = {x["date"]: x for x in ag.disponibilidade(con, d, d + timedelta(days=5))["dias"]}
    assert not disp[d.isoformat()]["any_open"]
    assert disp[(d + timedelta(days=1)).isoformat()]["periods"]["manha"]["open"]
    assert not disp[(d + timedelta(days=1)).isoformat()]["periods"]["tarde"]["open"]
    assert all(not disp[(d + timedelta(days=k)).isoformat()]["any_open"] for k in (2, 3, 4))
    assert disp[(d + timedelta(days=5)).isoformat()]["any_open"]
    assert periodo(con, d, "manha", "equipe")["reason"] == "bloqueado: corrida em Ocala", "a equipe vê o motivo"
    assert periodo(con, d, "manha")["reason"] == "bloqueado", "o motivo interno não vai ao cliente"


def test_desbloquear_nao_apaga(con):
    abre(con)
    d = proximo(4)
    bid = ag.bloquear(con, None, d.isoformat())
    ag.desbloquear(con, None, bid)
    assert periodo(con, d, "manha")["open"]
    assert todos(con, "SELECT active, removed_at FROM booking_blocks WHERE id=?", (bid,))[0]["active"] == 0


def test_antecedencia_e_horizonte(con, monkeypatch):
    abre(con)
    ag.mudar_config(con, None, min_notice_hours=48, horizon_days=10)
    hoje = datetime.now(FL).date()
    assert not periodo(con, hoje + timedelta(days=1), "manha")["open"], "menos de 48 h"
    assert periodo(con, hoje + timedelta(days=4), "manha")["open"]
    dias = ag.disponibilidade(con)["dias"]
    assert dias[-1]["date"] == (hoje + timedelta(days=10)).isoformat(), "horizonte de 10 dias"
    assert periodo(con, hoje + timedelta(days=1), "manha", "equipe")["open"], "a equipe vê sem o corte"


def test_config_valida_os_horarios(con):
    with pytest.raises(ag.ErroAgenda):
        ag.mudar_config(con, None, morning_end="14:00", afternoon_start="13:00")
    with pytest.raises(ag.ErroAgenda):
        ag.mudar_config(con, None, morning_start="25:00")
    assert ag.mudar_config(con, None, morning_start="08:30")["morning_start"] == "08:30"


# ------------------------------------------------------------------ agendar
def test_capacidade_e_dia_todo_ocupa_os_dois(con):
    abre(con, cap=2)
    d = proximo(2)
    c1, p1 = conta(con, "a@x.com"); c2, p2 = conta(con, "b@x.com"); c3, p3 = conta(con, "c@x.com")
    ag.agendar(con, c1, d.isoformat(), "manha", p1, servico_id=sv(con))
    assert periodo(con, d, "manha")["spots"] == 1
    ag.agendar(con, c2, d.isoformat(), "dia", p2, servico_id=sv(con))
    assert not periodo(con, d, "manha")["open"] and periodo(con, d, "tarde")["spots"] == 1
    with pytest.raises(ag.ErroAgenda, match="no longer available"):
        ag.agendar(con, c3, d.isoformat(), "manha", p3, servico_id=sv(con))
    ag.agendar(con, c3, d.isoformat(), "tarde", p3, servico_id=sv(con))
    assert periodo(con, d, "tarde", "equipe")["reason"] == "lotado"


def test_cancelada_e_recusada_liberam_a_vaga(con):
    abre(con)
    d = proximo(2)
    c1, p1 = conta(con, "a@x.com"); c2, p2 = conta(con, "b@x.com")
    b = ag.agendar(con, c1, d.isoformat(), "manha", p1, servico_id=sv(con))
    assert not periodo(con, d, "manha")["open"]
    ag.decidir(con, None, b, "recusar", "chuva")
    assert periodo(con, d, "manha")["open"]
    b2 = ag.agendar(con, c2, d.isoformat(), "manha", p2, servico_id=sv(con))
    ag.cancelar_pelo_cliente(con, c2, b2)
    assert periodo(con, d, "manha")["open"]


def test_mesmo_piloto_nao_marca_duas_vezes_no_mesmo_periodo(con):
    abre(con, cap=3)
    d = proximo(2)
    c, p = conta(con)
    ag.agendar(con, c, d.isoformat(), "manha", p, servico_id=sv(con))
    with pytest.raises(ag.ErroAgenda, match="already has"):
        ag.agendar(con, c, d.isoformat(), "dia", p, servico_id=sv(con))
    ag.agendar(con, c, d.isoformat(), "tarde", p, servico_id=sv(con))


def test_piloto_de_outra_conta_e_data_fechada(con):
    abre(con, dias=[2])
    c1, p1 = conta(con, "a@x.com"); c2, _ = conta(con, "b@x.com")
    with pytest.raises(ag.ErroAgenda, match="Driver not found"):
        ag.agendar(con, c2, proximo(2).isoformat(), "manha", p1, servico_id=sv(con))
    with pytest.raises(ag.ErroAgenda, match="no longer available"):
        ag.agendar(con, c1, proximo(3).isoformat(), "manha", p1, servico_id=sv(con))


def test_confirmacao_automatica(con):
    abre(con)
    c, p = conta(con)
    assert todos(con, "SELECT status FROM bookings WHERE id=?", (ag.agendar(con, c, proximo(2).isoformat(), "manha", p, servico_id=sv(con)),))[0]["status"] == "pendente"
    ag.mudar_config(con, None, auto_confirm=True)
    assert todos(con, "SELECT status FROM bookings WHERE id=?", (ag.agendar(con, c, proximo(3).isoformat(), "manha", p, servico_id=sv(con)),))[0]["status"] == "confirmada"


def test_decisoes_validas(con):
    abre(con)
    c, p = conta(con)
    b = ag.agendar(con, c, proximo(2).isoformat(), "manha", p, servico_id=sv(con))
    assert ag.decidir(con, None, b, "confirmar") == "confirmada"
    with pytest.raises(ag.ErroAgenda):
        ag.decidir(con, None, b, "recusar")
    assert ag.decidir(con, None, b, "cancelar") == "cancelada"


def test_atencao_mostra_pedido_do_site(con):
    abre(con)
    c, p = conta(con)
    ag.agendar(con, c, proximo(2).isoformat(), "manha", p, servico_id=sv(con))
    chaves = {i["key"]: i for i in atencao.coletar(con)}
    assert chaves["agenda-site:booking:pendentes"]["level"] == "HIGH"


# ------------------------------------------------------------------ API
@pytest.fixture()
def cli(con):
    auth.criar_usuario(con, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    auth.criar_usuario(con, "op@urace.us", "Operador", "OPERATOR", SENHA)
    con.commit()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def equipe(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def cliente(cli, email="maria@example.com"):
    cli.cookies.clear()
    r = cli.post("/ops/api/portal/signup", json={"name": "Maria Santos", "email": email, "password": "corrida-segura-9",
                                                 "birth_date": "1985-04-12", "accept_terms": True, "i_am_driver": True})
    assert r.status_code == 201, r.text
    return {"X-CSRF": cli.cookies.get("cp_csrf")}, r.json()["drivers"][0]["id"]


def test_fluxo_completo_pela_api(cli):
    h = equipe(cli, "op@urace.us")
    assert cli.put("/ops/api/site/agenda/semana", headers=h, json=[{"weekday": 2, "period": "manha", "open": True}]).status_code == 403
    h = equipe(cli, "ger@urace.us")
    regras = [{"weekday": d, "period": p, "open": True, "capacity": 1} for d in range(7) for p in ("manha", "tarde")]
    assert cli.put("/ops/api/site/agenda/semana", headers=h, json=regras).status_code == 200
    d = proximo(2)
    bid = cli.post("/ops/api/site/agenda/bloqueios", headers=h, json={"date_from": d.isoformat(), "period": "tarde", "reason": "manutenção"}).json()["id"]
    servico = cli.post("/ops/api/site/servicos", headers=h, json={"name": "Arrive and Drive", "price": "719.00"}).json()["id"]
    hc, piloto = cliente(cli)
    disp = cli.get(f"/ops/api/portal/availability?start={d}&end={d}").json()["dias"][0]["periods"]
    assert disp["manha"] == {"open": True, "spots": 1} and disp["tarde"] == {"open": False, "spots": 0}, "sem motivo interno"
    assert cli.post("/ops/api/portal/bookings", headers=hc, json={"date": d.isoformat(), "period": "tarde", "driver_id": piloto, "service_id": servico}).status_code == 400
    r = cli.post("/ops/api/portal/bookings", headers=hc, json={"date": d.isoformat(), "period": "manha", "driver_id": piloto, "notes": "primeira vez",
                                                               "service_id": servico})
    assert r.status_code == 201 and r.json()["bookings"][0]["status"] == "pendente"
    b = r.json()["id"]
    assert cli.get("/ops/api/site/agendamentos").status_code == 401, "cliente não vê a lista da equipe"
    h = equipe(cli, "op@urace.us")
    lista = cli.get("/ops/api/site/agendamentos?status=pendente").json()["agendamentos"]
    assert lista[0]["account_name"] == "Maria Santos" and lista[0]["driver"] == "Maria Santos"
    assert cli.post(f"/ops/api/site/agendamentos/{b}/confirmar", headers=h, json={"nota": "até lá"}).json()["status"] == "confirmada"
    assert cli.post(f"/ops/api/site/agenda/bloqueios/{bid}/remover", headers=h).status_code == 403, "desbloquear é do gerente"
    eventos = {x["event"] for x in todos(conectar(), "SELECT event FROM audit_logs")}
    assert {"booking.week", "booking.block", "portal.booking", "booking.confirmar"} <= eventos


def test_cliente_so_cancela_o_que_e_dele(cli):
    h = equipe(cli, "ger@urace.us")
    cli.put("/ops/api/site/agenda/semana", headers=h, json=[{"weekday": d, "period": "manha", "open": True, "capacity": 3} for d in range(7)])
    servico = cli.post("/ops/api/site/servicos", headers=h, json={"name": "Arrive and Drive", "price": 719}).json()["id"]
    hc, piloto = cliente(cli, "a@example.com")
    b = cli.post("/ops/api/portal/bookings", headers=hc, json={"date": proximo(2).isoformat(), "period": "manha", "driver_id": piloto,
                                                               "service_id": servico}).json()["id"]
    hc2, _ = cliente(cli, "b@example.com")
    assert cli.post(f"/ops/api/portal/bookings/{b}/cancel", headers=hc2).status_code == 404
    assert cli.get("/ops/api/portal/bookings").json()["bookings"] == []


def test_agendamento_extra_e_recusado(cli):
    hc, _ = cliente(cli)
    assert cli.post("/ops/api/portal/bookings", headers=hc, json={"date": "2030-01-01", "period": "manha", "status": "confirmada"}).status_code == 422
    assert date.fromisoformat(cli.get("/ops/api/portal/availability").json()["dias"][0]["date"]) >= datetime.now(FL).date()

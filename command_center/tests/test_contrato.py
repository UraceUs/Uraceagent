"""Contrato mensal (#61): o contador de sessões do mês, que zera com o mês, só para a equipe."""
import os

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, um  # noqa: E402
from command_center.providers import contrato, servicos_site as sv  # noqa: E402

SENHA = "senha-forte-123"


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def _mes(n=0):
    from datetime import date
    h = date.today()
    t = h.year * 12 + h.month - 1 + n
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def cenario(con, sessoes=4):
    cid = inserir(con, "clients", name="Paulo Kurian", pilot_name="Enzo Kurian", email="paulo@kurian.com",
                  monthly_amount=3000, monthly_sessions=sessoes, monthly_plan="Academy 4 stroke", plan_type="monthly")
    conta = inserir(con, "portal_accounts", email="paulo@kurian.com", pw_salt="x", pw_hash="x", name="Paulo Kurian",
                    birth_date="1980-01-01", terms_accepted_at="2026-09-30T00:00:00Z", client_id=cid)
    pil = inserir(con, "portal_pilots", account_id=conta, name="Enzo Kurian", client_id=cid)   # o card é do driver (#65)
    return cid, conta, pil


def sessao(con, conta, pil, dia, status="confirmada", periodo="manha"):
    return inserir(con, "bookings", account_id=conta, pilot_id=pil, date=dia, period=periodo, status=status)


def test_conta_site_e_asana_no_mes(con):
    cid, conta, pil = cenario(con)
    m = _mes()
    sessao(con, conta, pil, f"{m}-03")
    sessao(con, conta, pil, f"{m}-10", status="pendente")
    sessao(con, conta, pil, f"{m}-12", status="cancelada")                 # cancelada não conta
    sessao(con, conta, pil, f"{_mes(-1)}-20")                               # mês passado, conta no mês dele
    inserir(con, "tasks", client_id=cid, title="Enzo Kurian_Academy 4 Stroke - DOM 11", project="U-RACE", section="SUNDAY",
            status="open", due_on=f"{m}-11")
    u = contrato.usadas(con, cid, m)
    assert (len(u["site"]), len(u["asana"]), u["total"]) == (2, 1, 3)
    assert contrato.usadas(con, cid, _mes(-1))["total"] == 1


def test_acima_do_contrato(con):
    cid, conta, pil = cenario(con, sessoes=1)
    m = _mes()
    sessao(con, conta, pil, f"{m}-03")
    assert contrato.situacao_do_agendamento(con, cid, f"{m}-03") == {"usadas": 1, "sessoes_por_mes": 1, "acima": False}
    sessao(con, conta, pil, f"{m}-04")
    assert contrato.situacao_do_agendamento(con, cid, f"{m}-04")["acima"] is True


def test_sem_contrato_nao_tem_contador(con):
    cid = inserir(con, "clients", name="Avulso Silva")
    assert contrato.situacao_do_agendamento(con, cid, "2026-10-01") is None
    assert contrato.situacao_do_agendamento(con, None, "2026-10-01") is None
    assert contrato.sessoes_por_mes(con, cid) == 4, "sem número no card, o padrão da Academy"


def test_item_do_servico_aceita_texto_livre_e_so_lista_academy_e_daily_own_kart(con):
    for i, n in enumerate(["URACE Academy 4 stroke", "Urace Daily Using Own Kart", "Urace Daily Rental Kart", "Tires MG Red"]):
        inserir(con, "qbo_items", id=str(i + 1), name=n, type="Service", price=500)
    assert [i["name"] for i in sv.itens_qbo(con)] == ["URACE Academy 4 stroke", "Urace Daily Using Own Kart"]
    a = sv.criar(con, None, {"name": "Academy Session", "price": 689.23, "qbo_item": "urace academy 4 stroke"})
    assert um(con, "SELECT qbo_item_id, invoice_text FROM booking_services WHERE id=?", (a,)) == {"qbo_item_id": "1", "invoice_text": None}
    b = sv.criar(con, None, {"name": "Arrive and Drive", "price": 719, "qbo_item": "Arrive and Drive — 4-stroke"})
    assert um(con, "SELECT qbo_item_id, invoice_text FROM booking_services WHERE id=?", (b,)) == \
        {"qbo_item_id": None, "invoice_text": "Arrive and Drive — 4-stroke"}, "texto personalizado"


@pytest.fixture()
def cli(con):
    auth.criar_usuario(con, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    con.commit()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def test_card_mostra_o_contrato_do_cliente_e_a_lista_da_equipe_tambem(cli, con):
    cid, conta, pil = cenario(con, sessoes=None)
    m = _mes()
    sessao(con, conta, pil, f"{m}-05", status="pendente")
    sessao(con, conta, pil, f"{_mes(-1)}-05")
    con.commit()
    cli.post("/ops/api/auth/login", json={"email": "ger@urace.us", "password": SENHA})
    h = {"X-CSRF": cli.cookies.get("cc_csrf")}
    assert cli.get(f"/ops/api/clients/{cid}/monthly").json()["sessions_per_month"] == 4
    assert cli.patch(f"/ops/api/clients/{cid}/mensal", headers=h, json={"monthly_sessions": 0}).status_code == 400
    assert cli.patch(f"/ops/api/clients/{cid}/mensal", headers=h, json={"monthly_sessions": 2}).status_code == 200
    d = cli.get(f"/ops/api/clients/{cid}/monthly").json()
    assert d["sessions_per_month"] == 2 and d["sessions_per_month_set"] is True
    atual, passado = d["months"][0], d["months"][1]
    assert (atual["month"], atual["sessions_used"], atual["sessions_left"], atual["closed"]) == (m, 1, 1, False)
    assert atual["sessions"][0]["site"] is True, "o agendamento do site entra no contador"
    assert (passado["sessions_used"], passado["sessions_left"], passado["closed"]) == (1, 1, True), "deixou de usar 1 no mês passado"
    ag = cli.get("/ops/api/site/agendamentos").json()["agendamentos"]
    assert next(x for x in ag if x["date"].startswith(m))["contrato"] == {"usadas": 1, "sessoes_por_mes": 2, "acima": False}
    cli.cookies.clear()
    assert cli.get("/ops/api/portal/bookings").status_code == 401, "o cliente não vê nada disto"


def test_card_reconhece_a_mensalidade_pelo_item_da_linha(con):
    """#63: a invoice do Joseph Kurian de 17/09 não tem memo, só o item "Academy Monthly"."""
    from command_center.api import rotas
    cid, _, _ = cenario(con)
    m = _mes()
    iid = inserir(con, "invoices", client_id=cid, doc_number="1077", amount=2756, balance=0, status="paid",
                  issued_on=f"{m}-17", customer_ref="485", memo=None)
    inserir(con, "invoice_lines", invoice_id=iid, line_no=1, item_name="Academy Monthly", description="", amount=2756)
    d = rotas.resumo_mensalidade(con, cid)
    assert d["months"][0]["invoice"]["doc_number"] == "1077" and d["last_monthly_amount"] == 2756

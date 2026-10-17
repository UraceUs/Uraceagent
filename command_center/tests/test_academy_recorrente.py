"""Aluno recorrente da Academy (Kart School): pacote do mês, sessão extra e a cobrança dela (#314, parte 1).

Dono, 16/10: *"sempre que for um cliente desse, que é recorrente, que é mensal, quando ele for para a área do
cliente para ele poder agendar a sessão dele, ele não precisa efetuar o pagamento, a não ser que as sessões
daquele pacote dele … Se ele já tiver usado as sessões daquele pacote dele mensal, aí ele paga uma sessão
adicional. Aí a sessão é dividida pelo valor do mensal dele … ou então usa aqueles valores"*.

O que estes testes trancam: o preço da extra (configurado no card > o do plano > mensal ÷ sessões, em centavos
com arredondamento comercial); a vaga do pacote não conta extra nem Stripe e volta quando a sessão é cancelada;
os dias pedidos ocupam as vagas em ordem de data, mês a mês; o plano comprado no site só vale depois da 1ª
mensalidade paga e o plano encerrado não vale; a extra vai na invoice com o item e o valor da extra, sem
depósito; a do pacote não chama o QuickBooks; "Confirmar sozinho" não confirma a extra; a extra cancelada com a
invoice aberta aparece em Precisa de atenção. Dados fictícios."""
import os
from datetime import date, timedelta
from decimal import Decimal

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import atencao, auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import agora, aplicar_schema, conectar, inserir, um  # noqa: E402
from command_center.providers import agenda_sessoes as ag  # noqa: E402
from command_center.providers import cobranca_agenda as cob  # noqa: E402
from command_center.providers import contrato, mensalidades, servicos_site  # noqa: E402
from command_center.tests.test_agenda_sessoes import abre, conta  # noqa: E402

SENHA = "senha-forte-123"


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def _mes(n=0):
    h = ag._agora_fl().date()
    t = h.year * 12 + h.month - 1 + n
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


class Qbo:
    def __init__(self):
        self.chamadas = []

    def __call__(self, **kw):
        self.chamadas.append(kw)
        n = len(self.chamadas)
        return {"id": f"9{n}", "numero": f"URACE-20{n}", "total": round(sum(x["unitario"] for x in kw["linhas"]), 2),
                "link": f"https://qbo.test/inv/9{n}", "enviado": True, "enviado_para": kw["email"],
                "link_pagamento": f"https://connect.intuit.com/pay/9{n}"}


def aluno(con, mensal=2756.90, sessoes=4, **mais):
    """Um aluno fictício da Academy: card com contrato, conta do site e o piloto ligado ao card."""
    card = inserir(con, "clients", name="Lia Recorrente", pilot_name="Rui Recorrente", email="lia.recorrente@example.com",
                   status="ACTIVE", plan_type="monthly", monthly_plan="Academy 4 stroke", monthly_amount=mensal,
                   monthly_sessions=sessoes, **mais)
    cid, pid = conta(con, email="lia.recorrente@example.com")
    con.execute("UPDATE portal_pilots SET client_id=? WHERE id=?", (card, pid))
    return card, cid, pid


def sessao(con, cid, pid, dia, status="confirmada", **mais):
    return inserir(con, "bookings", account_id=cid, pilot_id=pid, date=dia, period="manha", status=status, **mais)


# ------------------------------------------------------------------ o preço da extra
def test_preco_da_extra_mensal_dividido_com_centavos_e_o_configurado_vence(con):
    card, _, _ = aluno(con, mensal=2756.90, sessoes=4)
    assert contrato.preco_extra(con, card) == Decimal("689.23"), "2.756,90 ÷ 4 = 689,225 → 689,23"
    con.execute("UPDATE clients SET monthly_amount=3156.90 WHERE id=?", (card,))
    assert contrato.preco_extra(con, card) == Decimal("789.23")
    con.execute("UPDATE clients SET monthly_amount=1378.45, monthly_sessions=2 WHERE id=?", (card,))
    assert contrato.preco_extra(con, card) == Decimal("689.23"), "pacote de 2: 1.378,45 ÷ 2"
    assert contrato.extra(con, card)["conta"] == "1,378.45 ÷ 2"
    con.execute("UPDATE clients SET extra_session_price=650 WHERE id=?", (card,))
    assert contrato.extra(con, card) == {"preco": Decimal("650.00"), "origem": "card", "conta": None}, "o valor do card vence"
    sem_mensal = inserir(con, "clients", name="Sem Mensal", plan_type="monthly")
    assert contrato.preco_extra(con, sem_mensal) is None


def test_preco_e_item_da_extra_do_plano_do_site_e_o_item_extra_session_do_quickbooks(con):
    inserir(con, "qbo_items", id="892", name="Academy | Extra session (beyond monthly 4)", price=689)
    inserir(con, "qbo_items", id="893", name="Tires extra set", price=300)
    plano = servicos_site.criar(con, None, {"name": "Academy 3 months", "price": 2756.90, "kind": "plan", "months": 3,
                                            "sessions_month": 4, "extra_price": "700"})
    card, cid, pid = aluno(con)
    inserir(con, "plan_orders", account_id=cid, pilot_id=pid, service_id=plano, service_name="Academy 3 months",
            price=2756.90, months=3, sessions_month=4, start_month=_mes(), status="ativa", client_id=card)
    assert contrato.extra(con, card)["origem"] == "plano" and contrato.preco_extra(con, card) == Decimal("700.00")
    assert contrato.item_extra(con, card) == "892", "sem item no card nem no plano: o 'Extra session' do QuickBooks"
    servicos_site.mudar(con, None, plano, {"extra_item": "Tires extra set"})
    assert contrato.item_extra(con, card) == "893", "o item do plano vence o do espelho"
    con.execute("UPDATE clients SET extra_item_id='892' WHERE id=?", (card,))
    assert contrato.item_extra(con, card) == "892", "o do card vence o do plano"
    with pytest.raises(servicos_site.ErroServico):
        servicos_site.mudar(con, None, plano, {"extra_item": "Item que não existe"})


# ------------------------------------------------------------------ a vaga do pacote
def test_vaga_do_pacote_nao_conta_extra_nem_stripe_e_cancelar_devolve(con):
    card, cid, pid = aluno(con, sessoes=4)
    m = _mes(1)
    a = sessao(con, cid, pid, f"{m}-02", coverage="plano")
    sessao(con, cid, pid, f"{m}-03", coverage="plano")
    sessao(con, cid, pid, f"{m}-04", charge_kind="contrato")                 # de antes do #314: conta
    sessao(con, cid, pid, f"{m}-05", coverage="extra", charge_kind="invoice")
    sessao(con, cid, pid, f"{m}-06", charge_kind="stripe")                   # paga no carrinho: não ocupa vaga
    sessao(con, cid, pid, f"{m}-07", charge_kind="invoice")                  # avulsa cobrada de antes: não ocupa
    assert contrato.usadas_do_pacote(con, card, m) == 3
    assert contrato.usadas(con, card, m)["total"] == 6, "o total de sessões do mês continua para o card"
    con.execute("UPDATE bookings SET status='cancelada' WHERE id=?", (a,))
    assert contrato.usadas_do_pacote(con, card, m) == 2, "a do pacote cancelada devolve a vaga do mês"
    assert [x["coverage"] for x in contrato.alocar(con, card, [f"{m}-20", f"{m}-21", f"{m}-22"])] == ["plano", "plano", "extra"]


def test_alocar_em_ordem_de_data_e_cada_mes_com_o_seu_pacote(con):
    card, cid, pid = aluno(con, sessoes=4)
    m, m2 = _mes(1), _mes(2)
    sessao(con, cid, pid, f"{m}-01", coverage="plano")                      # 1 já usada no mês
    pedido = [f"{m}-28", f"{m}-07", f"{m}-14", f"{m2}-04", f"{m}-21", f"{m}-10"]
    r = contrato.alocar(con, card, pedido)
    por_dia = {d: x["coverage"] for d, x in zip(pedido, r)}
    assert [por_dia[d] for d in sorted(d for d in pedido if d.startswith(m))] == ["plano", "plano", "plano", "extra", "extra"], \
        "4 no pacote, 1 usada: as 3 primeiras datas são do plano e o resto é extra"
    assert por_dia[f"{m2}-04"] == "plano", "o mês seguinte tem o próprio pacote (zera no dia 1)"
    assert {x["price"] for x in r if x["coverage"] == "extra"} == {Decimal("689.23")}
    assert {x["price"] for x in r if x["coverage"] == "plano"} == {Decimal("0.00")}


# ------------------------------------------------------------------ quem é recorrente
def test_plano_do_site_so_vale_depois_da_primeira_mensalidade_paga(con):
    card, cid, pid = aluno(con)
    plano = servicos_site.criar(con, None, {"name": "Academy 1 month", "price": 2756.90, "kind": "plan", "months": 1,
                                            "sessions_month": 4})
    oid = inserir(con, "plan_orders", account_id=cid, pilot_id=pid, service_id=plano, service_name="Academy 1 month",
                  price=2756.90, months=1, sessions_month=4, start_month=_mes(), status="pendente", client_id=card,
                  qbo_invoice_id="555")
    assert not contrato.vigente(con, card), "comprado e não pago: as sessões ainda não saem do plano"
    iid = inserir(con, "invoices", client_id=card, doc_number="URACE-0900", amount=2756.90, balance=0, status="Paid")
    con.execute("INSERT INTO entity_links (entity_type, entity_id, system, external_id) VALUES ('invoice', ?, 'quickbooks', '555')", (iid,))
    assert contrato.vigente(con, card), "paga no espelho do QuickBooks: vale, mesmo sem a waiver ainda"
    con.execute("UPDATE plan_orders SET status='ativa' WHERE id=?", (oid,))
    assert contrato.vigente(con, card)


def test_plano_encerrado_nao_vale_e_pro_driver_sem_mensal_nao_e_recorrente(con):
    card, _, _ = aluno(con)
    inserir(con, "monthly_recurring", client_id=card, amount=2756.90, item_id="1", months=6,
            start_on=f"{_mes(-7)}-01", end_on=f"{_mes(-2)}-01", status="active")
    assert not contrato.vigente(con, card, _mes()), "a recorrência acabou dois meses atrás"
    assert contrato.vigente(con, card, _mes(-2)), "no último mês cobrado ainda valia"
    inserir(con, "monthly_recurring", client_id=card, amount=2756.90, item_id="1", months=6,
            start_on=f"{_mes(-1)}-01", end_on=f"{_mes(4)}-01", status="active")
    assert contrato.vigente(con, card, _mes()), "renovou"
    pro = inserir(con, "clients", name="Piloto Pro Exemplo", pro_driver=1)
    assert not contrato.vigente(con, pro), "Pro Racing Driver sem mensal no card não é recorrente"


# ------------------------------------------------------------------ a cobrança
@pytest.fixture()
def cenario(con, monkeypatch):
    monkeypatch.setattr(mensalidades, "_cliente_qbo", lambda con, cid: "42")
    inserir(con, "qbo_items", id="11", name="Arrive and Drive 4T", price=719)
    inserir(con, "qbo_items", id="35", name="Security deposit", price=400)
    inserir(con, "qbo_items", id="892", name="Academy | Extra session (beyond monthly 4)", price=689)
    sid = servicos_site.criar(con, None, {"name": "Arrive and Drive", "price": 719, "qbo_item": "Arrive and Drive 4T",
                                          "deposit": 400})
    card, cid, pid = aluno(con, sessoes=1)
    abre(con, cap=3)
    con.commit()
    return {"sid": sid, "card": card, "conta": cid, "piloto": pid}


def marca(con, c, dia):
    bid = ag.agendar(con, c["conta"], dia.isoformat(), "manha", c["piloto"], None, c["sid"])
    cob.ao_marcar(con, bid)
    return bid


def _dois_no_mesmo_mes():
    """Duas datas futuras abertas no mesmo mês (a antecedência mínima é de 24 h)."""
    d = ag._agora_fl().date() + timedelta(days=2)
    if (d + timedelta(days=1)).month != d.month:
        d = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
    return d, d + timedelta(days=1)


def test_extra_vai_com_item_e_valor_da_extra_sem_deposito_e_a_do_pacote_nao_chama_o_quickbooks(con, cenario):
    d1, d2 = _dois_no_mesmo_mes()
    qbo = Qbo()
    b1 = marca(con, cenario, d1)
    b2 = marca(con, cenario, d2)
    x1, x2 = um(con, "SELECT * FROM bookings WHERE id=?", (b1,)), um(con, "SELECT * FROM bookings WHERE id=?", (b2,))
    assert (x1["coverage"], x1["price"], x1["list_price"]) == ("plano", 0, 719), "do pacote: nada a cobrar"
    assert (x2["coverage"], x2["price"], x2["list_price"]) == ("extra", 2756.90, 719), "pacote de 1: a 2ª é extra (mensal ÷ 1)"
    cob.aceitar(con, 1, b1, enviar_invoice=qbo, enviar_waiver=lambda *a: {"envelopeId": "e1"})
    assert not qbo.chamadas and um(con, "SELECT charge_kind FROM bookings WHERE id=?", (b1,))["charge_kind"] == "contrato"
    r = cob.aceitar(con, 1, b2, enviar_invoice=qbo, enviar_waiver=lambda *a: {"envelopeId": "e2"})
    assert r["pagamento"] == "enviada" and len(qbo.chamadas) == 1
    linhas = qbo.chamadas[0]["linhas"]
    assert [(x["item_id"], x["unitario"]) for x in linhas] == [("892", 2756.90)], "item da extra, sem a linha do depósito"
    assert linhas[0]["descricao"].startswith("Extra session (Academy 4 stroke) · ")


def test_extra_sem_item_nem_valor_fica_escrito_para_a_equipe(con, cenario):
    con.execute("UPDATE qbo_items SET active=0 WHERE id='892'")
    d1, d2 = _dois_no_mesmo_mes()
    marca(con, cenario, d1)
    b2 = marca(con, cenario, d2)
    cob.aceitar(con, 1, b2, enviar_invoice=Qbo(), enviar_waiver=lambda *a: {"envelopeId": "e"})
    assert "item da sessão extra" in um(con, "SELECT charge_error FROM bookings WHERE id=?", (b2,))["charge_error"]


def test_confirmar_sozinho_nao_confirma_a_extra_sem_cobranca(con, cenario):
    ag.mudar_config(con, None, auto_confirm=True)
    d1, d2 = _dois_no_mesmo_mes()
    b1 = marca(con, cenario, d1)
    b2 = marca(con, cenario, d2)
    x1, x2 = um(con, "SELECT * FROM bookings WHERE id=?", (b1,)), um(con, "SELECT * FROM bookings WHERE id=?", (b2,))
    assert (x1["status"], x1["charge_kind"]) == ("confirmada", "contrato"), "a do pacote confirma sozinha, sem cobrança"
    assert (x2["status"], x2["coverage"], x2["decided_at"]) == ("pendente", "extra", None), \
        "a extra espera a invoice e a waiver, mesmo com Confirmar sozinho"


def test_extra_que_nasceu_sem_preco_cobra_depois_que_a_equipe_poe_o_valor(con, cenario):
    """O card sem mensal: a 2ª sessão nasce extra sem preço. A equipe põe o "Valor da sessão extra" e o Aceitar cobra."""
    con.execute("UPDATE clients SET monthly_amount=NULL WHERE id=?", (cenario["card"],))
    d1, d2 = _dois_no_mesmo_mes()
    marca(con, cenario, d1)
    b2 = marca(con, cenario, d2)
    x2 = um(con, "SELECT coverage, price FROM bookings WHERE id=?", (b2,))
    assert (x2["coverage"], x2["price"]) == ("extra", None)
    qbo = Qbo()
    cob.aceitar(con, 1, b2, enviar_invoice=qbo, enviar_waiver=lambda *a: {"envelopeId": "e"})
    assert not qbo.chamadas and "sem valor da sessão extra" in um(con, "SELECT charge_error FROM bookings WHERE id=?", (b2,))["charge_error"]
    con.execute("UPDATE clients SET extra_session_price=650 WHERE id=?", (cenario["card"],))   # a Mensalidade do card
    r = cob.aceitar(con, 1, b2, enviar_invoice=qbo, enviar_waiver=lambda *a: {"envelopeId": "e"})
    assert r["pagamento"] == "enviada" and len(qbo.chamadas) == 1, r
    assert [(x["item_id"], x["unitario"]) for x in qbo.chamadas[0]["linhas"]] == [("892", 650.0)]
    assert um(con, "SELECT price FROM bookings WHERE id=?", (b2,))["price"] == 650.0, "o valor fica gravado na sessão"


def test_vaga_do_pacote_devolvida_vale_para_a_extra_ainda_nao_cobrada(con, cenario):
    """Pacote de 1: o dia 1 é do plano e o dia 2 extra. O cliente cancela o dia 1 antes da cobrança do dia 2: o dia 2
    passa a ser do plano, sem invoice (o cliente só paga a extra quando já usou as do pacote)."""
    d1, d2 = _dois_no_mesmo_mes()
    b1 = marca(con, cenario, d1)
    b2 = marca(con, cenario, d2)
    assert um(con, "SELECT coverage FROM bookings WHERE id=?", (b2,))["coverage"] == "extra"
    ag.cancelar_pelo_cliente(con, cenario["conta"], b1)
    qbo = Qbo()
    cob.aceitar(con, 1, b2, enviar_invoice=qbo, enviar_waiver=lambda *a: {"envelopeId": "e"})
    x2 = um(con, "SELECT coverage, price, charge_kind, qbo_invoice_id FROM bookings WHERE id=?", (b2,))
    assert not qbo.chamadas, "nenhuma invoice de extra com a vaga do pacote livre"
    assert (x2["coverage"], x2["price"], x2["charge_kind"], x2["qbo_invoice_id"]) == ("plano", 0, "contrato", None)
    assert um(con, "SELECT 1 AS x FROM audit_logs WHERE event='booking.realocada' AND entity_id=?", (str(b2),))


def test_card_da_equipe_acima_do_contrato_conta_so_o_pacote_e_as_extras(con):
    """Pacote de 4: 3 do plano e 2 pagas no Stripe no mês. Sobra 1 vaga e nada está acima do contrato; uma extra, sim."""
    from command_center.api.rotas import resumo_mensalidade
    card, cid, pid = aluno(con, sessoes=4)
    m = _mes()
    for d in ("03", "04", "05"):
        sessao(con, cid, pid, f"{m}-{d}", coverage="plano")
    for d in ("06", "07"):
        sessao(con, cid, pid, f"{m}-{d}", charge_kind="stripe")
    mes = resumo_mensalidade(con, card, meses=1)["months"][0]
    assert (mes["sessions_used"], mes["sessions_left"], mes["sessions_over"]) == (5, 1, 0), mes
    sessao(con, cid, pid, f"{m}-08", coverage="extra", charge_kind="invoice")
    mes = resumo_mensalidade(con, card, meses=1)["months"][0]
    assert (mes["sessions_left"], mes["sessions_over"]) == (1, 1), "a extra é acima do contrato; a vaga do pacote continua"


def test_extra_cancelada_com_invoice_aberta_aparece_em_precisa_de_atencao(con, cenario):
    d1, d2 = _dois_no_mesmo_mes()
    marca(con, cenario, d1)
    b2 = marca(con, cenario, d2)
    cob.aceitar(con, 1, b2, enviar_invoice=Qbo(), enviar_waiver=lambda *a: {"envelopeId": "e"})
    assert not [i for i in atencao.coletar(con) if i["key"].startswith("extra-cancelada")]
    ag.cancelar_pelo_cliente(con, cenario["conta"], b2)
    it = [i for i in atencao.coletar(con) if i["key"] == f"extra-cancelada:booking:{b2}"]
    assert it and "URACE-201" in it[0]["title"] and it[0]["client_id"] == cenario["card"]


# ------------------------------------------------------------------ o painel do gerente
@pytest.fixture()
def cli(con):
    auth.criar_usuario(con, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    con.commit()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def test_gerente_combina_o_valor_e_o_item_da_extra_na_mensalidade_do_card(cli, con):
    inserir(con, "qbo_items", id="892", name="Academy | Extra session (beyond monthly 4)", price=689)
    card, cid, pid = aluno(con)
    m = _mes()
    sessao(con, cid, pid, f"{m}-03", coverage="plano")
    sessao(con, cid, pid, f"{m}-04", coverage="extra", charge_kind="invoice")
    con.commit()
    cli.post("/ops/api/auth/login", json={"email": "ger@urace.us", "password": SENHA})
    h = {"X-CSRF": cli.cookies.get("cc_csrf")}
    d = cli.get(f"/ops/api/clients/{card}/mensal").json()
    assert d["extra"] == {"price": 689.23, "origin": "mensal", "math": "2,756.90 ÷ 4", "item_id": "892",
                          "item_name": "Academy | Extra session (beyond monthly 4)"}
    assert any(x["id"] == "892" for x in d["itens"]), "o item da extra está na lista do gerente"
    assert cli.patch(f"/ops/api/clients/{card}/mensal", headers=h, json={"extra_session_price": -1}).status_code == 400
    assert cli.patch(f"/ops/api/clients/{card}/mensal", headers=h, json={"extra_item_id": "nao-existe"}).status_code == 400
    r = cli.patch(f"/ops/api/clients/{card}/mensal", headers=h, json={"extra_session_price": 650.555, "extra_item_id": "892"})
    assert r.status_code == 200 and r.json()["extra"]["price"] == 650.56 and r.json()["extra"]["origin"] == "card"
    assert um(con, "SELECT extra_session_price, extra_item_id FROM clients WHERE id=?", (card,)) == \
        {"extra_session_price": 650.56, "extra_item_id": "892"}
    r = cli.patch(f"/ops/api/clients/{card}/mensal", headers=h, json={"extra_session_price": None})
    assert r.json()["extra"]["origin"] == "mensal", "apagar o valor volta ao mensal ÷ sessões"
    mes = cli.get(f"/ops/api/clients/{card}/monthly").json()["months"][0]
    assert (mes["month"], mes["sessions_used"], mes["sessions_left"]) == (m, 2, 3), "a extra não ocupa vaga do pacote"
    ags = cli.get("/ops/api/site/agendamentos").json()["agendamentos"]
    assert {x["coverage"]: x["contrato"]["acima"] for x in ags} == {"plano": False, "extra": True}


def test_cliente_ve_incluida_no_plano_e_nao_ve_o_contador(cli, con):
    card, cid, pid = aluno(con)
    sessao(con, cid, pid, (date.today() + timedelta(days=5)).isoformat(), coverage="plano", price=0, accepted_at=agora())
    con.commit()
    d = ag.do_cliente(con, cid)
    assert d[0]["coverage"] == "plano" and "usadas" not in d[0] and "sessoes_por_mes" not in d[0]

"""Venda automática do site (#164).

Dono, 08/10: "eu preciso que as etapas de compra sejam sempre respeitadas ... QuickBooks, manda a
invoice, já paga o security deposit, já assina o waiver ... e dali ela recebe a confirmação ... Um site
totalmente automático que venda sozinho, sem precisar de um humano."

O que estes testes trancam: desligada, nada muda (a equipe aceita); ligada, o pedido vira invoice +
depósito + waiver na hora, com card e cliente do QuickBooks garantidos; o card só liga sozinho a um card
existente com e-mail confirmado E o mesmo piloto (senão é card novo, marcado para unir); o cliente nunca
vê o link interno do QuickBooks, só o de pagamento; a confirmação chega por e-mail uma vez; a conferência
direta do pagamento respeita o intervalo."""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from command_center.api import auth
from command_center.api.main import app
from command_center.db import agora, aplicar_schema, conectar, inserir, todos, um
from command_center.providers import agenda_sessoes as ag
from command_center.providers import cobranca_agenda as cob
from command_center.providers import mensalidades, servicos_site, venda_site
from command_center.tests.dados_portal import piloto
from command_center.tests.test_agenda_sessoes import abre, conta, proximo


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


class Qbo:
    def __init__(self):
        self.chamadas = []

    def __call__(self, **kw):
        self.chamadas.append(kw)
        n = len(self.chamadas)
        return {"id": f"9{n}", "numero": f"URACE-10{n}", "total": sum(l["unitario"] for l in kw["linhas"]),
                "link": f"https://qbo.intuit.com/app/login?pagereq=invoice%3FtxnId%3D9{n}", "enviado": True,
                "enviado_para": kw["email"], "link_pagamento": f"https://connect.intuit.com/pay/9{n}"}


class Docusign:
    def __init__(self):
        self.chamadas = []

    def __call__(self, template, nome, email, servico):
        self.chamadas.append((template, nome, email))
        return {"envelopeId": f"env-{len(self.chamadas)}"}


class Emails:
    def __init__(self):
        self.enviados = []

    def __call__(self, para, assunto, texto):
        self.enviados.append((para, assunto, texto))
        return "ok"


@pytest.fixture()
def cenario(con, monkeypatch):
    qbo_clientes = {}
    monkeypatch.setattr(mensalidades, "_cliente_qbo", lambda con, card: qbo_clientes.get(card))
    inserir(con, "qbo_items", id="11", name="Arrive and Drive 4T", price=719)
    inserir(con, "qbo_items", id="35", name="Security deposit", price=400)
    sid = servicos_site.criar(con, None, {"name": "Arrive and Drive", "price": 719, "qbo_item": "Arrive and Drive 4T", "deposit": 400})
    cid, pid = conta(con)
    abre(con, cap=3)
    con.commit()
    criados = []

    def criar_qbo(nome, email=None, telefone=None):
        criados.append((nome, email))
        return {"id": "77", "nome": nome}
    return {"sid": sid, "conta": cid, "piloto": pid, "qbo_clientes": qbo_clientes, "criar_qbo": criar_qbo, "criados": criados}


def marca(con, c, dia=None):
    return ag.agendar(con, c["conta"], (dia or proximo(2)).isoformat(), "manha", c["piloto"], None, c["sid"])


def b_(con, bid):
    return um(con, "SELECT * FROM bookings WHERE id=?", (bid,))


def liga(con):
    ag.mudar_config(con, None, auto_sell=True)


def vende(con, c, bid, **kw):
    return venda_site.vender(con, bid, enviar_invoice=kw.get("qbo") or Qbo(), enviar_waiver=kw.get("ds") or Docusign(),
                             criar_qbo=c["criar_qbo"], enviar_email=kw.get("emails") or Emails())


# ------------------------------------------------------------------ desligada: nada muda
def test_desligada_o_pedido_espera_a_equipe(con, cenario):
    bid = marca(con, cenario)
    assert vende(con, cenario, bid) is None
    b = b_(con, bid)
    assert b["status"] == "pendente" and not b["accepted_at"] and not b["qbo_invoice_id"]


# ------------------------------------------------------------------ ligada: vende sozinha
def test_ligada_cria_card_e_cliente_no_quickbooks_cobra_servico_e_deposito_manda_waiver_e_avisa(con, cenario):
    liga(con)
    qbo, ds, emails = Qbo(), Docusign(), Emails()
    bid = marca(con, cenario)
    r = vende(con, cenario, bid, qbo=qbo, ds=ds, emails=emails)
    b = b_(con, bid)
    card = um(con, "SELECT client_id FROM portal_pilots WHERE id=?", (cenario["piloto"],))["client_id"]
    assert card and b["accepted_at"] and "card novo" in b["card_note"]
    assert cenario["criados"] == [("Cliente Teste", "c@example.com")], "cliente do QuickBooks criado uma vez"
    assert [(l["item_id"], l["unitario"]) for l in qbo.chamadas[0]["linhas"]] == [("11", 719.0), ("35", 400.0)]
    assert qbo.chamadas[0]["cliente_id"] == "77"
    assert ds.chamadas == [("parental", "Cliente Teste", "c@example.com")]
    assert r["pagamento"] == {"estado": "pagar", "link": "https://connect.intuit.com/pay/91", "invoice": "URACE-101",
                              "total": 1119.0, "para": "c@example.com"}
    assert r["waiver"]["estado"] == "email" and r["waiver"]["para"] == "c@example.com" and not r["confirmada"]
    # o e-mail ao cliente: o link de PAGAMENTO, nunca o da tela da equipe no QuickBooks
    (para, assunto, texto), = emails.enviados
    assert para == "c@example.com" and "https://connect.intuit.com/pay/91" in texto and "qbo.intuit.com/app" not in texto
    assert "DocuSign" in texto and "/ops/portal/sessions/" in texto
    # a área do cliente também só mostra o link de pagamento
    vista = ag.do_cliente(con, cenario["conta"])[0]
    assert vista["invoice_link"] == "https://connect.intuit.com/pay/91"
    # vender de novo não cobra de novo nem avisa de novo
    assert vende(con, cenario, bid, qbo=qbo, emails=emails) is None and len(qbo.chamadas) == 1 and len(emails.enviados) == 1


def test_card_existente_so_liga_sozinho_com_email_confirmado_e_o_mesmo_piloto(con, cenario):
    liga(con)
    antigo = inserir(con, "clients", name="Cliente Teste", email="c@example.com", pilot_name="Piloto Teste", status="ACTIVE")
    cenario["qbo_clientes"][antigo] = "42"
    # sem o e-mail confirmado: card novo, marcado como possível duplicado (ninguém vê o histórico do outro)
    bid = marca(con, cenario)
    vende(con, cenario, bid)
    novo = um(con, "SELECT client_id FROM portal_pilots WHERE id=?", (cenario["piloto"],))["client_id"]
    assert novo != antigo and "possível duplicado" in b_(con, bid)["card_note"]
    assert "POSSÍVEL DUPLICADO" in um(con, "SELECT notes FROM clients WHERE id=?", (novo,))["notes"]
    # outra conta, e-mail confirmado, mesmo e-mail e mesmo piloto do card: liga sozinha
    conta2, piloto2 = conta(con, email="d@example.com")
    antigo2 = inserir(con, "clients", name="Cliente Teste", email="D@example.com", pilot_name="Piloto Teste", status="ACTIVE")
    cenario["qbo_clientes"][antigo2] = "42"
    con.execute("UPDATE portal_accounts SET email_verified_at=? WHERE id=?", (agora(), conta2))
    bid2 = ag.agendar(con, conta2, proximo(3).isoformat(), "manha", piloto2, None, cenario["sid"])
    qbo = Qbo()
    vende(con, cenario, bid2, qbo=qbo)
    assert um(con, "SELECT client_id FROM portal_pilots WHERE id=?", (piloto2,))["client_id"] == antigo2
    assert "mesmo e-mail confirmado e mesmo piloto" in b_(con, bid2)["card_note"]
    assert qbo.chamadas[0]["cliente_id"] == "42" and cenario["criados"] == [("Cliente Teste", "c@example.com")]


def test_paga_e_assinada_confirma_e_avisa_uma_vez_com_conferencia_direta_no_intervalo(con, cenario):
    liga(con)
    bid = marca(con, cenario)
    vende(con, cenario, bid)
    card = um(con, "SELECT client_id FROM portal_pilots WHERE id=?", (cenario["piloto"],))["client_id"]
    inserir(con, "waivers", client_id=card, signer_name="Cliente Teste", signer_email="c@example.com", template="parental",
            status="completed", completed_at=agora())
    lidas, emails = [], Emails()

    def ler(inv):
        lidas.append(inv)
        return {"saldo": 1119.0, "total": 1119.0, "status": "sent", "link_pagamento": "https://connect.intuit.com/pay/91"}
    t0 = datetime.now(timezone.utc)
    assert not venda_site.conferir_pagamento(con, bid, ler=ler, enviar_email=emails, agora_dt=t0)
    assert not venda_site.conferir_pagamento(con, bid, ler=ler, enviar_email=emails, agora_dt=t0 + timedelta(seconds=20))
    assert lidas == ["91"], "no máximo uma conferência por minuto"

    def ler_pago(inv):
        return {"saldo": 0, "total": 1119.0, "status": "paid"}
    assert venda_site.conferir_pagamento(con, bid, ler=ler_pago, enviar_email=emails, agora_dt=t0 + timedelta(seconds=61))
    b = b_(con, bid)
    assert b["status"] == "confirmada" and b["paid_at"]
    assert [a for _, a, _ in emails.enviados] == ["You're confirmed: your URACE session"]
    assert venda_site.checkout(con, bid)["confirmada"]
    assert not venda_site.avisar_confirmada(con, bid, emails) and len(emails.enviados) == 1


def test_rodada_cria_o_cliente_do_quickbooks_que_faltou_e_avisa_quando_confirma(con, cenario):
    liga(con)
    bid = marca(con, cenario)

    def criar_falha(nome, email=None, telefone=None):
        raise RuntimeError("QuickBooks fora do ar")
    venda_site.vender(con, bid, enviar_invoice=Qbo(), enviar_waiver=Docusign(), criar_qbo=criar_falha, enviar_email=Emails())
    assert "fora do ar" in b_(con, bid)["charge_error"] and not b_(con, bid)["qbo_invoice_id"]
    assert venda_site.checkout(con, bid)["pagamento"]["estado"] == "equipe", "o cliente não fica olhando um 'preparando' eterno"
    qbo = Qbo()
    cob.rodar(con, enviar_invoice=qbo, enviar_waiver=Docusign(), enviar_email=Emails(), criar_qbo=cenario["criar_qbo"])
    b = b_(con, bid)
    assert b["qbo_invoice_id"] and b["pay_link"] and qbo.chamadas[0]["cliente_id"] == "77"


def test_utm_guarda_so_as_chaves_de_campanha():
    assert json.loads(venda_site.utm_limpo({"utm_source": "instagram", "utm_campaign": "outubro", "x": "y"})) == \
        {"utm_source": "instagram", "utm_campaign": "outubro"}
    assert venda_site.utm_limpo({"x": 1}) is None and venda_site.utm_limpo("lixo") is None


# ------------------------------------------------------------------ pela API
SENHA = "senha-forte-123"
P = "/ops/api/portal"


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    monkeypatch.setenv("CC_EMAIL_FAKE", str(tmp_path / "emails.jsonl"))
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    auth.criar_usuario(c, "adm@urace.us", "Admin", "ADMIN", SENHA)
    inserir(c, "qbo_items", id="11", name="Arrive and Drive 4T", price=719)
    inserir(c, "qbo_items", id="35", name="Security deposit", price=400)
    servicos_site.criar(c, None, {"name": "Arrive and Drive", "price": 719, "qbo_item": "Arrive and Drive 4T", "deposit": 400})
    abre(c, cap=3)
    c.commit(); c.close()
    qbo = Qbo()
    monkeypatch.setattr(mensalidades, "_cliente_qbo", lambda con, card: None)
    monkeypatch.setattr(venda_site, "_criar_qbo_padrao", lambda **kw: {"id": "77"})
    monkeypatch.setattr(cob, "_enviar_padrao", qbo)
    monkeypatch.setattr(cob, "_enviar_waiver_padrao", Docusign())
    monkeypatch.setattr(venda_site, "_ler_padrao", lambda inv: {"saldo": 1119.0, "total": 1119.0, "status": "sent"})
    with TestClient(app, base_url="https://cc.test") as t:
        t.qbo = qbo
        yield t


def _staff(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def _cliente(cli, email="maria@example.com"):
    cli.cookies.clear()
    r = cli.post(f"{P}/signup", json={"name": "Maria Santos", "email": email, "password": "corrida-segura-9",
                                      "birth_date": "1985-04-12", "phone": "(407) 555-0142", "address_line1": "100 Main St",
                                      "city": "Orlando", "state": "FL", "zip": "32809", "accept_terms": True})
    assert r.status_code == 201, r.text
    h = {"X-CSRF": cli.cookies.get("cp_csrf")}
    pid = cli.post(f"{P}/drivers", headers=h, json=piloto("Leo Santos")).json()["drivers"][0]["id"]
    return h, pid


def test_so_o_administrador_liga_a_venda_automatica(cli):
    h = _staff(cli, "ger@urace.us")
    assert cli.patch("/ops/api/site/agenda/config", headers=h, json={"auto_sell": True}).status_code == 403
    h = _staff(cli, "adm@urace.us")
    assert cli.patch("/ops/api/site/agenda/config", headers=h, json={"auto_sell": True}).json()["auto_sell"] == 1


def test_pelo_site_o_pedido_vira_invoice_e_o_cliente_acompanha_as_etapas(cli):
    h = _staff(cli, "adm@urace.us")
    cli.patch("/ops/api/site/agenda/config", headers=h, json={"auto_sell": True})
    h, pid = _cliente(cli)
    sid = cli.get(f"{P}/availability").json()["services"][0]["id"]
    r = cli.post(f"{P}/bookings", headers=h, json={"date": proximo(2).isoformat(), "period": "manha", "service_id": sid,
                                                   "driver_id": pid, "origin": "site", "utm": {"utm_source": "instagram"}})
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    assert r.json()["auto_sell"] is True
    c = cli.get(f"{P}/bookings/{bid}").json()
    assert c["pagamento"]["estado"] == "pagar" and c["pagamento"]["link"] == "https://connect.intuit.com/pay/91"
    assert c["waiver"]["estado"] == "email" and not c["confirmada"]
    assert cli.get(f"{P}/bookings/{bid}").headers["cache-control"] in ("private, no-store", "private, no-cache")
    con = conectar()
    try:
        b = b_(con, bid)
        assert b["origin"] == "site" and json.loads(b["utm"]) == {"utm_source": "instagram"}
    finally:
        con.close()
    emails = [json.loads(x) for x in open(os.environ["CC_EMAIL_FAKE"], encoding="utf-8")]
    assert [e["subject"] for e in emails if e["to"] == "maria@example.com"] == ["Your URACE booking: what's next"]
    # outra conta não vê o pedido
    h2, _ = _cliente(cli, "outra@example.com")
    assert cli.get(f"{P}/bookings/{bid}").status_code == 404
    assert len(todos(conectar(), "SELECT id FROM bookings")) == 1

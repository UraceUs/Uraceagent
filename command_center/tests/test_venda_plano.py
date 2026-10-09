"""Plano mensal vendido pelo site (#169).

Dono, 09/10: "Vender online já: invoice recorrente do QuickBooks criada pelo site". O que estes testes
trancam: o plano cadastrado no painel aparece na página da Academy com o botão que vende; o pedido vira
contrato no card, primeira mensalidade na hora (com link de pagamento), as outras agendadas no dia 1 (uma
por mês, nunca duas) e waiver; pago + waiver → ativo e e-mail; sem a venda automática, nada é cobrado."""
import os

import pytest
from fastapi.testclient import TestClient

from command_center.api.main import app
from command_center.db import aplicar_schema, conectar, inserir, todos, um
from command_center.providers import agenda_sessoes as ag
from command_center.providers import contrato, mensalidades, servicos_site, venda_plano
from command_center.tests.test_agenda_sessoes import conta
from command_center.tests.test_venda_site import Docusign, Emails, Qbo

os.environ["URACE_ENV"] = "/nao/existe"


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


@pytest.fixture()
def cenario(con, monkeypatch):
    qbo_clientes = {}
    monkeypatch.setattr(mensalidades, "_cliente_qbo", lambda con, card: qbo_clientes.get(card))
    inserir(con, "qbo_items", id="21", name="Academy 4 stroke", price=2688.43)
    sid = servicos_site.criar(con, None, {"name": "Academy 3 months", "price": 2688.43, "qbo_item": "Academy 4 stroke",
                                          "kind": "plan", "months": 3, "sessions_month": 4})
    cid, pid = conta(con)
    con.commit()

    def criar_qbo(nome, email=None, telefone=None):
        qid = f"Q{len(qbo_clientes) + 1}"
        return {"aplicado": True, "id": qid}
    return {"sid": sid, "cid": cid, "pid": pid, "qbo_clientes": qbo_clientes, "criar_qbo": criar_qbo}


def liga(con):
    ag.mudar_config(con, None, auto_sell=True); con.commit()


def test_plano_do_painel_aparece_na_academy_e_na_api_publica(cenario, tmp_path, monkeypatch):
    monkeypatch.delenv("CC_SITE_HOSTS", raising=False)
    with TestClient(app, base_url="https://novo.urace.us") as t:
        r = t.get("/ops/api/vitrine/planos").json()
        assert [(p["name"], p["price"], p["months"], p["sessions_month"], p["total"]) for p in r["plans"]] == \
            [("Academy 3 months", 2688.43, 3, 4, 8065.29)]
        assert "qbo" not in str(r).lower()
        html = t.get("/academy/").text
        assert f'href="/ops/portal/reserve?plan={cenario["sid"]}"' in html and "Academy 3 months" in html
        assert "$2,756.90" not in html, "com plano cadastrado, os cartões fixos do site antigo saem"
        assert t.get("/ops/api/vitrine/servicos").json()["services"] == [], "plano não é sessão avulsa"


def test_sem_plano_cadastrado_a_academy_pede_contato(con, monkeypatch):
    monkeypatch.delenv("CC_SITE_HOSTS", raising=False)
    with TestClient(app, base_url="https://novo.urace.us") as t:
        html = t.get("/academy/").text
        assert "/contact/?assunto=academy" in html and "reserve?plan=" not in html


def test_pedido_vira_contrato_primeira_mensalidade_e_as_outras_agendadas(con, cenario):
    liga(con)
    qbo, ds, em = Qbo(), Docusign(), Emails()
    oid = venda_plano.pedir(con, cenario["cid"], cenario["sid"], cenario["pid"], origin="site", utm={"utm_source": "instagram"})
    assert venda_plano.pedir(con, cenario["cid"], cenario["sid"], cenario["pid"]) == oid, "o mesmo pedido, não dois"
    c = venda_plano.vender(con, oid, enviar_invoice=qbo, enviar_waiver=ds, criar_qbo=cenario["criar_qbo"], enviar_email=em)
    o = um(con, "SELECT * FROM plan_orders WHERE id=?", (oid,))
    # 1. card com o contrato
    assert o["client_id"] and contrato.tem_contrato(con, o["client_id"])
    card = um(con, "SELECT * FROM clients WHERE id=?", (o["client_id"],))
    assert (card["plan_type"], card["monthly_plan"], card["monthly_amount"], card["monthly_item_id"], card["monthly_sessions"]) == \
        ("monthly", "Academy 3 months", 2688.43, "21", 4)
    # 2. a primeira mensalidade saiu agora, com o link de pagamento do cliente
    assert len(qbo.chamadas) == 1 and qbo.chamadas[0]["linhas"][0]["unitario"] == 2688.43
    assert "[" in qbo.chamadas[0]["memo"] and o["pay_link"].startswith("https://connect.intuit.com/pay/")
    # 3. as outras duas agendadas no dia 1; este mês já consta enviado — uma por mês
    meses = todos(con, "SELECT month, status, doc_number FROM monthly_invoices WHERE client_id=? ORDER BY month", (o["client_id"],))
    assert [m["status"] for m in meses] == ["enviada", "a_enviar", "a_enviar"] and meses[0]["doc_number"] == "URACE-101"
    assert meses[0]["month"] == o["start_month"]
    rec = um(con, "SELECT * FROM monthly_recurring WHERE id=?", (o["recurring_id"],))
    assert rec["months"] == 3 and rec["status"] == "active" and rec["client_id"] == o["client_id"]
    # 4. waiver pelo DocuSign, e-mail de boas-vindas com os passos
    assert len(ds.chamadas) == 1 and o["waiver_ref"]
    assert c["pagamento"]["estado"] == "pagar" and c["waiver"]["estado"] == "email" and c["next_months"] == [meses[1]["month"], meses[2]["month"]]
    assert len(em.enviados) == 1 and "first month" in em.enviados[0][2] and "/ops/portal/plans/" in em.enviados[0][2]
    assert "qbo.intuit.com" not in em.enviados[0][2], "o cliente nunca vê o link interno do QuickBooks"
    # rodar de novo não cobra de novo
    assert venda_plano.vender(con, oid, enviar_invoice=qbo, enviar_waiver=ds, criar_qbo=cenario["criar_qbo"], enviar_email=em) is None
    assert len(qbo.chamadas) == 1


def test_pago_e_waiver_assinada_ativa_o_plano_e_avisa(con, cenario):
    liga(con)
    qbo, ds, em = Qbo(), Docusign(), Emails()
    oid = venda_plano.pedir(con, cenario["cid"], cenario["sid"], cenario["pid"])
    venda_plano.vender(con, oid, enviar_invoice=qbo, enviar_waiver=ds, criar_qbo=cenario["criar_qbo"], enviar_email=em)
    o = um(con, "SELECT * FROM plan_orders WHERE id=?", (oid,))
    # a waiver chega assinada (espelho do DocuSign)
    con.execute("UPDATE waivers SET status='completed', completed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (o["waiver_ref"],))
    assert not venda_plano.conferir_pagamento(con, oid, ler=lambda i: {"saldo": 2688.43, "total": 2688.43}, enviar_email=em)
    assert um(con, "SELECT status FROM plan_orders WHERE id=?", (oid,))["status"] == "pendente"
    from datetime import datetime, timedelta, timezone
    depois = datetime.now(timezone.utc) + timedelta(seconds=61)
    assert venda_plano.conferir_pagamento(con, oid, ler=lambda i: {"saldo": 0, "total": 2688.43}, enviar_email=em, agora_dt=depois)
    o = um(con, "SELECT * FROM plan_orders WHERE id=?", (oid,))
    assert o["status"] == "ativa" and o["paid_at"]
    assert [a for _, a, _ in em.enviados] == ["Your Academy 3 months plan: what's next", "Your Academy 3 months plan is active"]
    c = venda_plano.checkout(con, oid)
    assert c["ativo"] and c["pagamento"]["estado"] == "pago" and c["waiver"]["estado"] == "ok"


def test_sem_venda_automatica_o_pedido_fica_para_a_equipe(con, cenario):
    qbo, ds, em = Qbo(), Docusign(), Emails()
    oid = venda_plano.pedir(con, cenario["cid"], cenario["sid"], cenario["pid"])
    assert venda_plano.vender(con, oid, enviar_invoice=qbo, enviar_waiver=ds, criar_qbo=cenario["criar_qbo"], enviar_email=em) is None
    assert not qbo.chamadas and not ds.chamadas and not em.enviados
    c = venda_plano.checkout(con, oid)
    assert not c["aceita"] and c["pagamento"]["estado"] == "preparando"


def test_pedido_exige_plano_ativo_e_piloto_da_conta(con, cenario):
    outra, outro_piloto = conta(con, email="outra@example.com")
    with pytest.raises(venda_plano.ErroPlano, match="driver"):
        venda_plano.pedir(con, cenario["cid"], cenario["sid"], outro_piloto)
    servicos_site.mudar(con, None, cenario["sid"], {"active": False})
    with pytest.raises(venda_plano.ErroPlano, match="plan"):
        venda_plano.pedir(con, cenario["cid"], cenario["sid"], cenario["pid"])


def test_api_do_cliente_cria_e_acompanha_o_plano(cenario, con, monkeypatch, tmp_path):
    liga(con)
    qbo, ds = Qbo(), Docusign()
    from command_center.providers import cobranca_agenda, venda_site
    monkeypatch.setattr(cobranca_agenda, "_enviar_padrao", qbo)
    monkeypatch.setattr(cobranca_agenda, "_enviar_waiver_padrao", ds)
    monkeypatch.setattr(venda_site, "_criar_qbo_padrao", cenario["criar_qbo"])
    monkeypatch.setattr(venda_site, "_ler_padrao", lambda i: {"saldo": 2688.43, "total": 2688.43})
    monkeypatch.setenv("CC_EMAIL_FAKE", str(tmp_path / "emails.jsonl"))
    with TestClient(app, base_url="https://my.urace.us") as t:
        r = t.post("/ops/api/portal/signup", json={"name": "Maria Santos", "email": "maria.plano@example.com", "password": "corrida-segura-9",
                                                  "birth_date": "1985-04-12", "phone": "(407) 555-0142", "address_line1": "100 Main St",
                                                  "city": "Orlando", "state": "FL", "zip": "32809", "accept_terms": True})
        assert r.status_code == 201, r.text
        csrf = {"X-CSRF": t.cookies.get("cp_csrf")}
        from command_center.tests.dados_portal import piloto
        pid = t.post("/ops/api/portal/drivers", json=piloto("Nina Plano"), headers=csrf).json()["drivers"][0]["id"]
        r = t.post("/ops/api/portal/plans", json={"service_id": cenario["sid"], "driver_id": pid, "origin": "site"}, headers=csrf)
        assert r.status_code == 201 and r.json()["auto_sell"] is True, r.text
        oid = r.json()["id"]
        c = t.get(f"/ops/api/portal/plans/{oid}")
        assert c.status_code == 200 and "private" in c.headers["cache-control"]
        assert c.json()["plan"] == "Academy 3 months" and c.json()["pagamento"]["estado"] == "pagar"
        assert c.json()["pagamento"]["link"].startswith("https://connect.intuit.com/pay/")
        assert t.get("/ops/api/portal/plans/999").status_code == 404

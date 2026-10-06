"""Cobrança e waiver da sessão marcada pelo site (#50, PR B) — decisões do dono de 06/10.

O que estes testes trancam: aceitar a vaga cria e envia a invoice (serviço + depósito quando o
serviço pede) e manda a waiver pelo DocuSign; a sessão só confirma sozinha com invoice paga e
waiver assinada; cliente com contrato não paga de novo e, com a waiver em dia, confirma ao
marcar; lembrete 3 dias e 1 dia antes, uma vez cada; nada cancela sozinho; nada é cobrado duas
vezes; toda falha fica escrita no agendamento para a equipe."""
from datetime import date, timedelta

import pytest

from command_center.db import agora, atualizar, inserir, um  # noqa: I001
from command_center.providers import cobranca_agenda as cob
from command_center.providers import mensalidades, servicos_site
from command_center.db import aplicar_schema, conectar
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
                "link": f"https://qbo.test/inv/9{n}", "enviado": True, "enviado_para": kw["email"]}


class Docusign:
    def __init__(self):
        self.chamadas = []

    def __call__(self, template, nome, email, servico):
        self.chamadas.append((template, nome, email))
        return {"envelopeId": f"env-{len(self.chamadas)}"}


@pytest.fixture()
def cenario(con, monkeypatch):
    monkeypatch.setattr(mensalidades, "_cliente_qbo", lambda con, cid: "42")
    inserir(con, "qbo_items", id="11", name="Arrive and Drive 4T", price=719)
    inserir(con, "qbo_items", id="35", name="Security deposit", price=400)
    sid = servicos_site.criar(con, None, {"name": "Arrive and Drive", "price": 719, "qbo_item": "Arrive and Drive 4T",
                                          "deposit": 400})
    card = inserir(con, "clients", name="Cliente Teste", email="c@example.com", status="ACTIVE")
    cid, pid = conta(con)
    con.execute("UPDATE portal_pilots SET client_id=? WHERE id=?", (card, pid))
    abre(con, cap=3)
    con.commit()
    return {"sid": sid, "card": card, "conta": cid, "piloto": pid}


def marca(con, c, dia=None):
    from command_center.providers import agenda_sessoes as ag
    return ag.agendar(con, c["conta"], (dia or proximo(2)).isoformat(), "manha", c["piloto"], None, c["sid"])


def b_(con, bid):
    return um(con, "SELECT * FROM bookings WHERE id=?", (bid,))


def paga(con, b):
    iid = inserir(con, "invoices", client_id=b["id"], doc_number=b["invoice_doc"], amount=b["invoice_total"], balance=0, status="Paid")
    con.execute("INSERT INTO entity_links (entity_type, entity_id, system, external_id) VALUES ('invoice', ?, 'quickbooks', ?)",
                (iid, b["qbo_invoice_id"]))


def assina(con, card):
    inserir(con, "waivers", client_id=card, signer_name="Cliente Teste", signer_email="c@example.com", template="parental",
            status="completed", completed_at=agora())


def test_aceitar_cobra_servico_e_deposito_manda_a_waiver_e_so_confirma_com_pago_e_assinada(con, cenario):
    qbo, ds = Qbo(), Docusign()
    bid = marca(con, cenario)
    r = cob.aceitar(con, 1, bid, enviar_invoice=qbo, enviar_waiver=ds)
    assert r["status"] == "pendente" and r["pagamento"] == "enviada" and r["waiver"] == "enviada"
    linhas = qbo.chamadas[0]["linhas"]
    assert [(l["item_id"], l["unitario"]) for l in linhas] == [("11", 719.0), ("35", 400.0)], "serviço + depósito"
    assert qbo.chamadas[0]["cliente_id"] == "42" and qbo.chamadas[0]["email"] == "c@example.com"
    assert ds.chamadas == [("parental", "Cliente Teste", "c@example.com")], "piloto menor: o responsável assina"
    b = b_(con, bid)
    assert b["invoice_doc"] == "URACE-101" and b["waiver_ref"]
    assert not cob.verificar(con, bid), "só a invoice enviada não confirma"
    paga(con, b)
    assert not cob.verificar(con, bid), "paga mas sem waiver assinada: ainda não"
    assina(con, cenario["card"])
    assert cob.verificar(con, bid) and b_(con, bid)["status"] == "confirmada"
    # aceitar de novo não cobra de novo
    with pytest.raises(Exception):
        cob.aceitar(con, 1, bid, enviar_invoice=qbo, enviar_waiver=ds)
    assert len(qbo.chamadas) == 1


def test_servico_sem_deposito_e_sem_item_do_quickbooks(con, cenario):
    con.execute("UPDATE booking_services SET deposit=0 WHERE id=?", (cenario["sid"],))
    qbo = Qbo()
    bid = marca(con, cenario)
    cob.aceitar(con, 1, bid, enviar_invoice=qbo, enviar_waiver=Docusign())
    assert len(qbo.chamadas[0]["linhas"]) == 1, "depósito 0 = sem depósito"
    con.execute("UPDATE booking_services SET qbo_item_id=NULL, invoice_text='Custom' WHERE id=?", (cenario["sid"],))
    bid2 = marca(con, cenario, proximo(3))
    cob.aceitar(con, 1, bid2, enviar_invoice=qbo, enviar_waiver=Docusign())
    b = b_(con, bid2)
    assert "item do QuickBooks" in b["charge_error"] and not b["qbo_invoice_id"] and len(qbo.chamadas) == 1
    # a rodada tenta de novo até 3 vezes; depois espera a equipe
    for _ in range(5):
        cob.rodar(con, enviar_invoice=qbo, enviar_waiver=Docusign(), enviar_email=lambda *a: None)
    assert b_(con, bid2)["charge_attempts"] == 3


def test_contrato_nao_paga_de_novo_e_com_waiver_em_dia_confirma_ao_marcar(con, cenario):
    con.execute("UPDATE clients SET plan_type='monthly', monthly_sessions=4 WHERE id=?", (cenario["card"],))
    qbo = Qbo()
    bid = marca(con, cenario)
    assert not cob.ao_marcar(con, bid), "sem waiver em dia, não confirma sozinha"
    r = cob.aceitar(con, 1, bid, enviar_invoice=qbo, enviar_waiver=Docusign())
    assert r["pagamento"] == "contrato" and not qbo.chamadas and r["status"] == "pendente"
    assina(con, cenario["card"])
    bid2 = marca(con, cenario, proximo(3))
    assert cob.ao_marcar(con, bid2) and b_(con, bid2)["status"] == "confirmada" and not qbo.chamadas


def test_sem_card_ou_sem_cliente_no_quickbooks_fica_escrito(con, cenario, monkeypatch):
    con.execute("UPDATE portal_pilots SET client_id=NULL WHERE id=?", (cenario["piloto"],))
    bid = marca(con, cenario)
    cob.aceitar(con, 1, bid, enviar_invoice=Qbo(), enviar_waiver=Docusign())
    assert "card" in b_(con, bid)["charge_error"]
    con.execute("UPDATE portal_pilots SET client_id=? WHERE id=?", (cenario["card"], cenario["piloto"]))
    monkeypatch.setattr(mensalidades, "_cliente_qbo", lambda con, cid: None)
    bid2 = marca(con, cenario, proximo(3))
    cob.aceitar(con, 1, bid2, enviar_invoice=Qbo(), enviar_waiver=Docusign())
    assert "não está no QuickBooks" in b_(con, bid2)["charge_error"]


def test_piloto_adulto_assina_a_propria_e_sem_email_nao_manda(con, cenario):
    con.execute("UPDATE portal_pilots SET birth_date='1990-01-01', email=NULL, is_self=0 WHERE id=?", (cenario["piloto"],))
    ds = Docusign()
    bid = marca(con, cenario)
    cob.aceitar(con, 1, bid, enviar_invoice=Qbo(), enviar_waiver=ds)
    assert not ds.chamadas and "piloto adulto sem e-mail" in b_(con, bid)["waiver_error"]
    con.execute("UPDATE portal_pilots SET email='piloto@example.com' WHERE id=?", (cenario["piloto"],))
    cob.rodar(con, enviar_invoice=Qbo(), enviar_waiver=ds, enviar_email=lambda *a: None)
    assert ds.chamadas == [("adult", "Piloto Teste", "piloto@example.com")]


def test_waiver_nativa_ligada_nao_manda_docusign(con, cenario):
    bid = marca(con, cenario)                       # a agenda cria a linha de config
    con.execute("UPDATE booking_config SET waiver_native=1 WHERE id=1")
    ds = Docusign()
    cob.aceitar(con, 1, bid, enviar_invoice=Qbo(), enviar_waiver=ds)
    assert not ds.chamadas


def test_lembrete_3_dias_e_1_dia_antes_uma_vez_cada_e_nada_cancela(con, cenario):
    hoje = date.today()
    bid = marca(con, cenario)
    atualizar(con, "bookings", bid, date=(hoje + timedelta(days=3)).isoformat())
    cob.aceitar(con, 1, bid, enviar_invoice=Qbo(), enviar_waiver=Docusign())
    mandados = []
    email = lambda para, assunto, texto: mandados.append((para, assunto, texto))  # noqa: E731
    cob.rodar(con, hoje=hoje, enviar_email=email)
    cob.rodar(con, hoje=hoje, enviar_email=email)
    assert len(mandados) == 1 and mandados[0][0] == "c@example.com"
    assert "Pay the invoice URACE-101" in mandados[0][2] and "Sign the waiver" in mandados[0][2]
    cob.rodar(con, hoje=hoje + timedelta(days=2), enviar_email=email)
    assert len(mandados) == 2 and "tomorrow" in mandados[1][2]
    cob.rodar(con, hoje=hoje + timedelta(days=5), enviar_email=email)
    assert b_(con, bid)["status"] == "pendente", "nada cancela sozinho: a equipe decide"


def test_lembrete_que_falha_fica_escrito(con, cenario):
    hoje = date.today()
    bid = marca(con, cenario)
    atualizar(con, "bookings", bid, accepted_at=agora(), date=(hoje + timedelta(days=1)).isoformat())
    def falha(*a):
        raise RuntimeError("sem token do Google para noreply@urace.us")
    cob.rodar(con, hoje=hoje, enviar_invoice=Qbo(), enviar_waiver=Docusign(), enviar_email=falha)
    b = b_(con, bid)
    assert "noreply" in b["reminder_error"] and not b["reminded_1d_at"]

"""#236: carrinho e checkout do site no Stripe (sessões da agenda + loja).

Dono, 14/10: "o sistema de carrinho e checkout ... Tudo testado, tudo funcionando. É, usando o Stripe";
"quando a pessoa selecionar o serviço, selecionar a data, já vai com aquele serviço e o preço que está lá";
"O depósito de segurança ele é cobrado em venda manual ou automática"; "Todo mundo agora precisa de conta".

O que estes testes trancam: o preço e o depósito vêm do servidor (catálogo e painel), nunca do navegador;
sessão pede conta e piloto da própria conta; um checkout só com todas as linhas e o depósito; o pago
(webhook e página de obrigado) marca a sessão uma vez só, liga ao card do piloto e abre a venda GANHO;
a vaga que sumiu antes do pagamento fica para a equipe sem perder o pagamento; expirado não marca nada.
Nada fala com o Stripe nem com o QuickBooks de verdade."""
import json

import pytest

from command_center.api import auth
from command_center.db import inserir, todos, um
from command_center.providers import agenda_sessoes as ag
from command_center.providers import carrinho, servicos_site
from command_center.tests.dados_portal import completa
from command_center.tests.test_agenda_sessoes import abre, proximo
from command_center.tests.test_stripe_loja import _assinado, _emails, _evento, _simples, amb  # noqa: F401

SENHA = "pista-molhada-7"


@pytest.fixture()
def loja(amb):  # noqa: F811
    cli, con, st, qbo, tmp = amb
    inserir(con, "qbo_items", id="11", name="Arrive and Drive 4T", price=719)
    inserir(con, "qbo_items", id="35", name="Security deposit", price=400)
    # #263: o serviço do 4-stroke já nasce da migração, ligado ao kart pela chave; aqui só se põe o
    # item do QuickBooks que este teste usa (o site cobra pelo Stripe, a invoice da equipe é à parte)
    sid = um(con, "SELECT id FROM booking_services WHERE site_kart='4-stroke'")["id"]
    servicos_site.mudar(con, None, sid, {"qbo_item": "Arrive and Drive 4T", "deposit": 400})
    abre(con, cap=1)
    con.commit()
    return cli, con, st, qbo, tmp, sid


def _entrar(cli, con, email="lia@example.com", nome="Lia Souza", piloto="Theo Souza"):
    """Conta do site pela API (o cookie fica no cliente de teste) e um piloto com o cadastro em dia."""
    r = cli.post("/ops/api/portal/signup", json={"name": nome, "email": email, "password": SENHA, "birth_date": "1980-01-01",
                                                 "accept_terms": True, "phone": "(407) 555-0142", "address_line1": "100 Main St",
                                                 "city": "Orlando", "state": "FL", "zip": "32809"})
    assert r.status_code == 201, r.text
    conta = r.json()["id"]
    pid = inserir(con, "portal_pilots", account_id=conta, name=piloto)
    completa(con, conta, pid)
    con.commit()
    return conta, pid


def _csrf(cli):
    return {"X-CSRF": cli.cookies.get("cp_csrf")}


def _sessao(sid, dia, piloto=None, turno="manha", **lixo):
    return {"tipo": "sessao", "servico": sid, "data": dia.isoformat(), "turno": turno, "piloto": piloto, **lixo}


def _checkout(cli, itens, entrega="retirada"):
    return cli.post("/ops/api/vitrine/carrinho/checkout", json={"itens": itens, "entrega": entrega}, headers=_csrf(cli))


def _pagar(cli, st, sid_stripe, eid="evt_c1", email="lia@example.com", nome="Lia Souza"):
    s = dict(st.sessoes[sid_stripe], payment_status="paid", payment_intent="pi_c1",
             customer_details={"email": email, "name": nome, "phone": "+14075550142"})
    st.sessoes[sid_stripe] = s
    corpo, cab = _assinado(_evento(s, eid=eid))
    return cli.post("/ops/api/stripe/webhook", content=corpo, headers=cab)


# ------------------------------------------------------------------ o preço é do servidor
def test_cotacao_usa_o_preco_do_painel_e_do_catalogo_e_ignora_o_do_navegador(loja):
    cli, con, st, qbo, tmp, sid = loja
    p = _simples()
    dia = proximo(5)
    r = cli.post("/ops/api/vitrine/carrinho", json={"itens": [
        _sessao(sid, dia, preco=1, price=1, unitario=1, deposito=0),
        {"tipo": "produto", "produto": p["slug"], "quantidade": 2, "preco": 0.01}]})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    d = r.json()
    sessao, prod = d["linhas"]
    assert (sessao["unitario"], sessao["deposito"], sessao["nome"]) == (719.0, 400.0, "Arrive and Drive 4-stroke")
    assert prod["unitario"] == float(p["price"]) and prod["valor"] == round(float(p["price"]) * 2, 2)
    assert d["subtotal"] == round(719 + float(p["price"]) * 2, 2) and d["deposito"] == 400
    assert d["total"] == round(d["subtotal"] + 400, 2)
    assert d["precisa_conta"] and d["account"] is None, "sessão pede a conta do site"
    # o gerente muda o preço: o carrinho mostra o novo na hora (o preço mora no painel, #50)
    servicos_site.mudar(con, None, sid, {"price": 799, "deposit": 0, "deposit_required": False})   # #317: zerar pede desmarcar
    con.commit()
    d = cli.post("/ops/api/vitrine/carrinho", json={"itens": [_sessao(sid, dia)]}).json()
    assert d["linhas"][0]["unitario"] == 799 and d["deposito"] == 0


def test_dia_fechado_lotado_ou_servico_inativo_nao_entra(loja):
    cli, con, st, qbo, tmp, sid = loja
    dia = proximo(5)
    ag.bloquear(con, None, dia.isoformat(), dia.isoformat(), "manha", "evento")
    plano = servicos_site.criar(con, None, {"name": "Academy 1 month", "price": 2756.9, "kind": "plan", "months": 1})
    con.commit()
    d = cli.post("/ops/api/vitrine/carrinho", json={"itens": [
        _sessao(sid, dia), _sessao(sid, proximo(6), turno="tarde"), _sessao(sid, proximo(6), turno="tarde"),
        _sessao(plano, proximo(6)), _sessao(sid, proximo(6), turno="noite")]}).json()
    erros = [x["erro"] for x in d["linhas"]]
    assert erros[0].startswith("This time is no longer available")
    assert erros[1] is None and erros[2].startswith("This time is no longer available"), "1 vaga: a segunda do carrinho não cabe"
    assert "no longer offered" in erros[3], "plano mensal não entra como sessão"
    assert erros[4] == "Choose morning or afternoon."
    assert not d["ok"] and d["total"] == 1119.0


def test_sessao_exige_conta_e_piloto_da_propria_conta(loja):
    cli, con, st, qbo, tmp, sid = loja
    dia = proximo(5)
    r = cli.post("/ops/api/vitrine/carrinho/checkout", json={"itens": [_sessao(sid, dia)]})
    assert r.status_code == 401 and r.json()["sign_in"]
    assert not st.chamadas, "sem conta, o Stripe nem é chamado"
    outra = inserir(con, "portal_accounts", email="outro@example.com", pw_salt="x", pw_hash="x", name="Outro Pai",
                    birth_date="1980-01-01", terms_accepted_at="2026-09-30T00:00:00Z")
    alheio = inserir(con, "portal_pilots", account_id=outra, name="Filho Alheio")
    con.commit()
    conta, pid = _entrar(cli, con)
    d = cli.post("/ops/api/vitrine/carrinho", json={"itens": [_sessao(sid, dia, alheio)]}).json()
    assert d["account"]["name"] == "Lia Souza" and [x["name"] for x in d["account"]["drivers"]] == ["Theo Souza"]
    assert d["linhas"][0]["erro"] == "Choose the driver for this session." and d["linhas"][0]["piloto"] is None
    r = _checkout(cli, [_sessao(sid, dia, alheio)])
    assert r.status_code == 400 and not st.chamadas
    r = cli.post("/ops/api/vitrine/carrinho/checkout", json={"itens": [_sessao(sid, dia, pid)]})
    assert r.status_code == 403, "logado, escrever pede o CSRF"


def test_um_checkout_com_todas_as_linhas_e_o_deposito(loja):
    cli, con, st, qbo, tmp, sid = loja
    conta, pid = _entrar(cli, con)
    p = _simples()
    dia = proximo(5)
    r = _checkout(cli, [_sessao(sid, dia, pid), {"tipo": "produto", "produto": p["slug"], "quantidade": 2}], entrega="envio")
    assert r.status_code == 200, r.text
    assert r.json()["url"].startswith("https://checkout.stripe.com/")
    (_, caminho, campos, idem), = st.chamadas
    assert caminho == "/v1/checkout/sessions" and idem.startswith("urace-carrinho-")
    linhas = [(i["price_data"]["unit_amount"], i["quantity"], i["price_data"]["product_data"]["name"]) for i in campos["line_items"]]
    assert linhas[0][:2] == (71900, 1) and "Arrive and Drive 4-stroke" in linhas[0][2] and "Theo Souza" in linhas[0][2]
    assert linhas[1][:2] == (40000, 1) and linhas[1][2].startswith("Refundable security deposit")
    assert linhas[2] == (round(float(p["price"]) * 100), 2, p["name"])
    assert campos["customer_email"] == "lia@example.com" and campos["expires_at"] > 0
    assert campos["success_url"].endswith("/cart/thanks/?session_id={CHECKOUT_SESSION_ID}")
    assert campos["shipping_address_collection"]["allowed_countries"]
    o = um(con, "SELECT * FROM store_orders")
    assert (o["kind"], o["status"], o["account_id"], o["delivery"]) == ("carrinho", "aberto", conta, "envio")
    assert o["amount"] == round(719 + 400 + float(p["price"]) * 2, 2)
    itens = carrinho.itens(con, o["id"])
    assert [(x["kind"], x["unit_price"], x["deposit"]) for x in itens] == [("sessao", 719.0, 400.0), ("produto", float(p["price"]), 0)]
    assert not todos(con, "SELECT id FROM bookings"), "a sessão só vira agendamento depois de pago"


def test_produto_sozinho_no_carrinho_pede_conta_e_vai_com_o_email_dela(loja):
    """#248 (dono, 14/10): "Para a pessoa conseguir comprar com a gente, ela tem que criar a conta dela lá no site"."""
    cli, con, st, qbo, tmp, sid = loja
    p = _simples()
    itens = [{"tipo": "produto", "produto": p["slug"]}]
    d = cli.post("/ops/api/vitrine/carrinho", json={"itens": itens}).json()
    assert d["precisa_conta"] and not d["tem_sessao"]
    r = cli.post("/ops/api/vitrine/carrinho/checkout", json={"itens": itens})
    assert r.status_code == 401 and r.json()["sign_in"] and not st.chamadas, "sem conta, o Stripe nem é chamado"
    conta, _ = _entrar(cli, con)
    r = _checkout(cli, itens)
    assert r.status_code == 200 and st.chamadas[0][2]["customer_email"] == "lia@example.com"
    assert "expires_at" not in st.chamadas[0][2], "sem sessão, o Checkout não precisa expirar em 31 min"
    assert um(con, "SELECT account_id FROM store_orders")["account_id"] == conta


# ------------------------------------------------------------------ pago
def test_pago_marca_a_sessao_liga_o_card_do_piloto_e_e_idempotente(loja):
    cli, con, st, qbo, tmp, sid = loja
    conta, pid = _entrar(cli, con)
    p = _simples()
    dia = proximo(5)
    _checkout(cli, [_sessao(sid, dia, pid), {"tipo": "produto", "produto": p["slug"]}])
    sid_stripe = next(iter(st.sessoes))
    # o gerente muda o preço DEPOIS da compra: o pedido guarda o preço do dia
    servicos_site.mudar(con, None, sid, {"price": 999})
    con.commit()
    r = _pagar(cli, st, sid_stripe)
    assert r.json()["resultado"] == "pago"
    b = um(con, "SELECT * FROM bookings")
    assert (b["status"], b["charge_kind"], b["price"], b["pilot_id"], b["account_id"]) == ("pendente", "stripe", 719.0, pid, conta)
    assert b["accepted_at"] and b["paid_at"] and b["store_order_id"]
    from command_center.providers import cobranca_agenda as cob
    assert cob.situacao(con, b)["pagamento"] == "pago", "pago no Stripe: falta só a waiver"
    card = um(con, "SELECT client_id FROM portal_pilots WHERE id=?", (pid,))["client_id"]
    assert card and um(con, "SELECT pilot_name FROM clients WHERE id=?", (card,))["pilot_name"] == "Theo Souza"
    opps = todos(con, "SELECT * FROM opportunities")
    assert len(opps) == 1 and opps[0]["stage"] == "GANHO" and opps[0]["client_id"] == card and opps[0]["source"] == "Site"
    assert opps[0]["amount"] == round(719 + 400 + float(p["price"]), 2) and "Theo Souza" in opps[0]["pilot_name"]
    o = um(con, "SELECT * FROM store_orders")
    assert o["status"] == "pago" and o["opp_id"] == opps[0]["id"] and o["attention"] is None
    # o mesmo evento de novo, outro evento da mesma sessão e a página de obrigado: nada se repete
    assert _pagar(cli, st, sid_stripe).json()["resultado"] == "duplicado"
    assert _pagar(cli, st, sid_stripe, eid="evt_c2").json()["resultado"] == "pago"
    assert cli.get(f"/cart/thanks/?session_id={sid_stripe}").status_code == 200
    assert len(todos(con, "SELECT id FROM bookings")) == 1 and len(todos(con, "SELECT id FROM opportunities")) == 1
    # e-mails: a confirmação para quem comprou e o aviso para a equipe (uma vez só)
    para = [m["to"] for m in _emails(tmp)]
    assert para.count("lia@example.com") == 1 and para.count("support@urace.us") == 1
    conf = next(m for m in _emails(tmp) if m["to"] == "lia@example.com")
    assert "Refundable security deposit: US$ 400.00" in conf["text"] and "Sign the waiver" in conf["text"]
    # QuickBooks: um Sales Receipt com o serviço, o depósito e o produto
    (recibo,) = qbo.recibos
    assert [(x["item_id"], x["unitario"]) for x in recibo["linhas"]][:2] == [("11", 719.0), ("35", 400.0)]
    assert recibo["numero"] == f"WEB-{o['id']:05d}"


def test_pagina_de_obrigado_registra_quando_o_webhook_atrasa(loja):
    cli, con, st, qbo, tmp, sid = loja
    conta, pid = _entrar(cli, con)
    _checkout(cli, [_sessao(sid, proximo(5), pid)])
    sid_stripe = next(iter(st.sessoes))
    st.sessoes[sid_stripe].update(payment_status="paid", customer_details={"email": "lia@example.com", "name": "Lia Souza"})
    r = cli.get(f"/cart/thanks/?session_id={sid_stripe}")
    assert r.status_code == 200 and "Thank you! Your order is confirmed" in r.text and "data-limpar-carrinho" in r.text
    assert 'name="robots" content="noindex' in r.text and r.headers["cache-control"] == "no-store"
    assert len(todos(con, "SELECT id FROM bookings")) == 1
    corpo, cab = _assinado(_evento(st.sessoes[sid_stripe], eid="evt_tarde"))
    assert cli.post("/ops/api/stripe/webhook", content=corpo, headers=cab).json()["resultado"] == "pago"
    assert len(todos(con, "SELECT id FROM bookings")) == 1, "o webhook atrasado não marca de novo"


def test_vaga_que_sumiu_antes_do_pagamento_fica_para_a_equipe_sem_perder_o_pagamento(loja):
    cli, con, st, qbo, tmp, sid = loja
    conta, pid = _entrar(cli, con)
    dia = proximo(5)
    _checkout(cli, [_sessao(sid, dia, pid)])
    # alguém pega a última vaga enquanto a pessoa está no Checkout
    outra = inserir(con, "portal_accounts", email="rapido@example.com", pw_salt="x", pw_hash="x", name="Rapido Silva",
                    birth_date="1980-01-01", terms_accepted_at="2026-09-30T00:00:00Z")
    p2 = inserir(con, "portal_pilots", account_id=outra, name="Rapido Jr")
    completa(con, outra, p2)
    ag.agendar(con, outra, dia.isoformat(), "manha", p2, None, sid)
    con.commit()
    assert _pagar(cli, st, next(iter(st.sessoes))).json()["resultado"] == "pago"
    o = um(con, "SELECT * FROM store_orders")
    assert o["status"] == "pago" and o["attention"] and "vaga sumiu" in o["attention"]
    (x,) = carrinho.itens(con, o["id"])
    assert x["status"] == "sem_vaga" and x["booking_id"] is None
    assert len(todos(con, "SELECT id FROM bookings WHERE account_id=?", (conta,))) == 0, "não lota a agenda por cima"
    assert um(con, "SELECT COUNT(*) AS n FROM opportunities")["n"] == 1, "a venda entra mesmo assim"
    equipe = next(m for m in _emails(tmp) if m["to"] == "support@urace.us")
    assert "SEM VAGA" in equipe["subject"] and "ATENÇÃO" in equipe["text"]
    cliente = next(m for m in _emails(tmp) if m["to"] == "lia@example.com")
    assert "Your payment is safe" in cliente["text"]


def test_expirado_ou_cancelado_nao_marca_nada(loja):
    cli, con, st, qbo, tmp, sid = loja
    conta, pid = _entrar(cli, con)
    _checkout(cli, [_sessao(sid, proximo(5), pid)])
    s = st.sessoes[next(iter(st.sessoes))]
    corpo, cab = _assinado(_evento(s, tipo="checkout.session.expired", eid="evt_exp"))
    assert cli.post("/ops/api/stripe/webhook", content=corpo, headers=cab).json()["resultado"] == "expirado"
    assert um(con, "SELECT status FROM store_orders")["status"] == "expirado"
    assert not todos(con, "SELECT id FROM bookings") and not todos(con, "SELECT id FROM opportunities")
    r = cli.get("/cart/?cancelled=1")
    assert r.status_code == 200 and "nothing was charged" in r.text


def test_dois_pilotos_duas_vendas_cada_uma_no_card_do_seu_piloto(loja):
    """Nunca pôr serviço de um cliente no card de outro: cada piloto tem o seu card e a sua venda."""
    cli, con, st, qbo, tmp, sid = loja
    conta, pid = _entrar(cli, con)
    irmao = inserir(con, "portal_pilots", account_id=conta, name="Bia Souza")
    completa(con, conta, irmao)
    ag.mudar_semana(con, [{"weekday": d, "period": p, "open": True, "capacity": 3} for d in range(7) for p in ("manha", "tarde")])
    con.commit()
    dia = proximo(5)
    assert _checkout(cli, [_sessao(sid, dia, pid), _sessao(sid, dia, irmao)]).status_code == 200
    _pagar(cli, st, next(iter(st.sessoes)))
    cards = {x["pilot_name"]: x["client_id"] for x in carrinho.itens(con, um(con, "SELECT id FROM store_orders")["id"])}
    assert cards["Theo Souza"] and cards["Bia Souza"] and cards["Theo Souza"] != cards["Bia Souza"]
    opps = {o["pilot_name"]: o["client_id"] for o in todos(con, "SELECT * FROM opportunities")}
    assert opps == cards


def test_painel_mostra_o_pedido_com_as_linhas_na_venda(loja):
    cli, con, st, qbo, tmp, sid = loja
    conta, pid = _entrar(cli, con)
    p = _simples()
    _checkout(cli, [_sessao(sid, proximo(5), pid), {"tipo": "produto", "produto": p["slug"]}])
    _pagar(cli, st, next(iter(st.sessoes)))
    opp = um(con, "SELECT id FROM opportunities")["id"]
    auth.criar_usuario(con, "closer@urace.us", "Carla Vendas", "OPERATOR", "senha-forte-123")
    con.commit()
    assert cli.post("/ops/api/auth/login", json={"email": "closer@urace.us", "password": "senha-forte-123"}).status_code == 200
    d = cli.get(f"/ops/api/sales/{opp}").json()
    ped = d["pedido"]
    assert ped["tipo"] == "carrinho" and ped["status"] == "pago" and len(ped["linhas"]) == 2
    s = ped["linhas"][0]
    assert (s["tipo"], s["unitario"], s["deposito"], s["piloto"], s["status"]) == ("sessao", 719.0, 400.0, "Theo Souza", "marcada")
    assert s["agendamento"] == um(con, "SELECT id FROM bookings")["id"]
    lista = cli.get("/ops/api/site/agendamentos").json()["agendamentos"]
    assert lista[0]["charge_kind"] == "stripe" and lista[0]["cobranca"]["pagamento"] == "pago"


def test_carrinho_e_pagina_do_site_sem_indexar(loja):
    cli, *_ = loja
    r = cli.get("/cart/")
    assert r.status_code == 200 and '<h1 id="h-cart">Your cart</h1>' in r.text
    assert 'name="robots" content="noindex' in r.text and r.headers["cache-control"] == "no-store"
    assert "/cart/" not in cli.get("/sitemap.xml").text
    assert cli.get("/checkout/", follow_redirects=False).headers["location"] == "/cart/"
    assert 'href="/cart/"' in cli.get("/").text and "carrinho.js" in cli.get("/").text
    assert json.loads(cli.get("/ops/api/vitrine/servicos").text)["cart"] is True

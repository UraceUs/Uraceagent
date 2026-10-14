"""#248: conta do site obrigatória para comprar, aviso sempre, registro no card do cliente e PT/EN.

Dono, 14/10: "Para a pessoa conseguir comprar com a gente, ela tem que criar a conta dela lá no site da
URACE. Então, o e-mail que precisa para essas coisas do Stripe já pode ser puxado de lá"; "o cliente e a
equipe precisam da confirmação de pagamento sempre e deixar isso também registrado no card do cliente no
Command Center"; "mesmo jeito do command center, switch para mudar de português para inglês"; "mostre
todas as informações do cliente ali".

Dados fictícios (@example.com, 555-01xx). Nada fala com o Stripe de verdade."""
import re

import pytest

from command_center.api import auth
from command_center.db import inserir, todos, um
from command_center.providers import pedido_site
from command_center.tests.test_agenda_sessoes import proximo
from command_center.tests.test_carrinho import _checkout, _entrar, _sessao, loja  # noqa: F401
from command_center.tests.test_stripe_loja import _assinado, _conta, _emails, _evento, _simples, amb  # noqa: F401

EMAIL = "rita.teste@example.com"


def _webhook(cli, s, tipo, eid, **extra):
    corpo, cab = _assinado(_evento(s, tipo=tipo, eid=eid, **extra))
    r = cli.post("/ops/api/stripe/webhook", content=corpo, headers=cab)
    assert r.status_code == 200, r.text
    return r.json()["resultado"]


def _pedido(con):
    return um(con, "SELECT * FROM store_orders ORDER BY id DESC LIMIT 1")


def _h1(html):
    return re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S).group(1).strip()


def _idioma(cli, lang, volta="/cart/"):
    return cli.post("/language/", data={"lang": lang, "volta": volta}, follow_redirects=False)


@pytest.fixture()
def compra(loja):  # noqa: F811
    """Conta (Rita) com um piloto e um carrinho com sessão + produto, já no Stripe."""
    cli, con, st, qbo, tmp, sid = loja
    conta, pid = _entrar(cli, con, email=EMAIL, nome="Rita Teste", piloto="Davi Teste")
    p = _simples()
    dia = proximo(5)
    return cli, con, st, qbo, tmp, sid, conta, pid, dia, p


# ------------------------------------------------------------------ a conta é obrigatória
def test_buy_now_sem_conta_manda_entrar_e_voltar_para_o_produto(amb):  # noqa: F811
    cli, con, st, qbo, tmp = amb
    p = _simples()
    r = cli.post("/ops/api/vitrine/checkout", data={"produto": p["slug"], "quantidade": "1"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/ops/portal?volta=/store/p/{p['slug']}/"
    r = cli.post("/ops/api/vitrine/checkout", json={"produto": p["slug"]}, headers={"Accept": "application/json"})
    assert r.status_code == 401 and r.json()["sign_in"] and r.json()["url"].startswith("/ops/portal?volta=/store/p/")
    assert not st.chamadas and not todos(con, "SELECT id FROM store_orders"), "sem conta, nada de pedido nem de Stripe"
    conta = _conta(cli, "Bia Teste", "bia.teste@example.com")
    r = cli.post("/ops/api/vitrine/checkout", data={"produto": p["slug"], "quantidade": "1"}, follow_redirects=False)
    assert r.headers["location"].startswith("https://checkout.stripe.com/")
    campos = st.chamadas[0][2]
    assert campos["customer_email"] == "bia.teste@example.com" and campos["locale"] == "en"
    o = _pedido(con)
    assert (o["account_id"], o["email"], o["name"], o["lang"]) == (conta, "bia.teste@example.com", "Bia Teste", "en")
    assert "Buying needs your URACE account" in cli.get(f"/store/p/{p['slug']}/").text


def test_o_email_e_o_card_vem_da_conta_e_nao_do_que_o_stripe_devolve(amb):  # noqa: F811
    """O e-mail dos avisos é o da conta; o card ligado à conta (pela equipe) recebe a venda, mesmo com outro
    nome no cartão. Nunca o card de outra pessoa que só tem o mesmo e-mail do cartão."""
    cli, con, st, qbo, tmp = amb
    p = _simples()
    conta = _conta(cli, "Caio Teste", "caio.teste@example.com")
    card = inserir(con, "clients", name="Caio Teste", email="caio.teste@example.com", status="ACTIVE")
    inserir(con, "clients", name="Outra Pessoa", email="cartao.teste@example.com", status="ACTIVE")
    con.execute("UPDATE portal_accounts SET client_id=? WHERE id=?", (card, conta))
    con.commit()
    s = st.sessoes[cli.post("/ops/api/vitrine/checkout", data={"produto": p["slug"]}, follow_redirects=False)
                   .headers["location"].rsplit("/", 1)[1]]
    s.update(payment_status="paid", customer_details={"email": "cartao.teste@example.com", "name": "Titular Do Cartao"})
    assert _webhook(cli, s, "checkout.session.completed", "evt_c1") == "pago"
    o = _pedido(con)
    assert o["email"] == "caio.teste@example.com" and o["name"] == "Caio Teste"
    opp = um(con, "SELECT * FROM opportunities")
    assert opp["client_id"] == card and opp["stage"] == "GANHO"
    assert [m["to"] for m in _emails(tmp)] == ["caio.teste@example.com", "support@urace.us"]


# ------------------------------------------------------------------ aviso sempre e registro no card
def test_cada_resultado_avisa_cliente_e_equipe_e_fica_no_card_uma_vez(compra):
    cli, con, st, qbo, tmp, sid, conta, pid, dia, p = compra
    card_piloto = inserir(con, "clients", name="Rita Teste", pilot_name="Davi Teste", email=EMAIL, status="ACTIVE")
    card_conta = inserir(con, "clients", name="Rita Teste", email=EMAIL, status="ACTIVE")
    outro = inserir(con, "clients", name="Rita Teste", pilot_name="Irmao Teste", email=EMAIL, status="ACTIVE")
    con.execute("UPDATE portal_pilots SET client_id=? WHERE id=?", (card_piloto, pid))
    con.execute("UPDATE portal_accounts SET client_id=? WHERE id=?", (card_conta, conta))
    con.commit()
    assert _checkout(cli, [_sessao(sid, dia, pid), {"tipo": "produto", "produto": p["slug"]}]).status_code == 200
    s = st.sessoes[next(reversed(st.sessoes))]
    s.update(payment_status="unpaid")
    for eid in ("evt_k1", "evt_k1", "evt_k2"):
        _webhook(cli, s, "checkout.session.completed", eid)
    for eid in ("evt_k3", "evt_k4"):
        _webhook(cli, s, "checkout.session.async_payment_failed", eid)
    o = _pedido(con)
    assert [x["result"] for x in todos(con, "SELECT result FROM store_order_notices WHERE order_id=? ORDER BY id", (o["id"],))] == \
        ["aguardando", "falhou"]
    assuntos = [m["subject"] for m in _emails(tmp)]
    assert sum("confirming your payment" in a for a in assuntos) == 1 and sum("didn't go through" in a for a in assuntos) == 1
    assert sum("PROCESSANDO" in a for a in assuntos) == 1 and sum("PAGAMENTO FALHOU" in a for a in assuntos) == 1
    evs = todos(con, "SELECT * FROM client_events ORDER BY id")
    assert sorted((e["client_id"], e["result"]) for e in evs) == sorted(
        [(card_piloto, "aguardando"), (card_conta, "aguardando"), (card_piloto, "falhou"), (card_conta, "falhou")])
    assert not [e for e in evs if e["client_id"] == outro], "nunca no card de outro cliente (o irmão)"
    do_piloto = next(e for e in evs if e["client_id"] == card_piloto and e["result"] == "falhou")
    assert "Davi Teste" in do_piloto["detail"] and p["name"] not in do_piloto["detail"], "cada card com as suas linhas"
    assert do_piloto["link"] == pedido_site.link(o) and "US$ 1,119.00" in do_piloto["detail"]
    do_produto = next(e for e in evs if e["client_id"] == card_conta and e["result"] == "falhou")
    assert p["name"] in do_produto["detail"] and "Davi Teste" not in do_produto["detail"]
    # o Client360 mostra na linha do tempo, com o link da página do pedido
    auth.criar_usuario(con, "closer@urace.us", "Carla Vendas", "OPERATOR", "senha-forte-123")
    con.commit()
    assert cli.post("/ops/api/auth/login", json={"email": "closer@urace.us", "password": "senha-forte-123"}).status_code == 200
    tl = cli.get(f"/ops/api/clients/{card_piloto}").json()["timeline"]
    pag = [x for x in tl if x["kind"] == "SITE_PAYMENT"]
    assert {x["status"] for x in pag} == {"aguardando", "falhou"}
    assert pag[0]["links"][0]["deep_link"] == pedido_site.link(o) and "pedido #" in pag[0]["title"]


def test_pago_tambem_fica_no_card_do_piloto(compra):
    cli, con, st, qbo, tmp, sid, conta, pid, dia, p = compra
    assert _checkout(cli, [_sessao(sid, dia, pid)]).status_code == 200
    s = st.sessoes[next(reversed(st.sessoes))]
    s.update(payment_status="paid")
    _webhook(cli, s, "checkout.session.completed", "evt_pg1")
    o = _pedido(con)
    card = um(con, "SELECT client_id FROM portal_pilots WHERE id=?", (pid,))["client_id"]
    (ev,) = todos(con, "SELECT * FROM client_events")
    assert (ev["client_id"], ev["result"], ev["link"]) == (card, "pago", pedido_site.link(o))
    n = um(con, "SELECT * FROM store_order_notices WHERE order_id=? AND result='pago'", (o["id"],))
    assert n["sent_at"] and n["to_email"] == EMAIL


# ------------------------------------------------------------------ os dados do cliente na página
def test_pagina_do_pedido_mostra_os_dados_do_cliente_da_conta(compra):
    cli, con, st, qbo, tmp, sid, conta, pid, dia, p = compra
    assert _checkout(cli, [_sessao(sid, dia, pid), {"tipo": "produto", "produto": p["slug"]}], entrega="envio").status_code == 200
    s = st.sessoes[next(reversed(st.sessoes))]
    s.update(payment_status="paid", shipping_details={"name": "Rita Teste", "address": {
        "line1": "200 Test Ave", "city": "Orlando", "state": "FL", "postal_code": "32801", "country": "US"}})
    _webhook(cli, s, "checkout.session.completed", "evt_d1")
    o = _pedido(con)
    r = cli.get(pedido_site.caminho(o))
    assert r.headers["cache-control"] == "no-store" and r.headers["referrer-policy"] == "no-referrer"
    assert 'name="robots" content="noindex' in r.text
    for v in ("Your details", "Rita Teste", EMAIL, "(407) 555-0142", "100 Main St", "Davi Teste", "200 Test Ave, Orlando FL 32801"):
        assert v in r.text, v


# ------------------------------------------------------------------ inglês e português
def test_chave_de_idioma_grava_a_escolha_e_so_volta_para_a_pagina(amb):  # noqa: F811
    cli, *_ = amb
    r = cli.get("/cart/")
    assert '<html lang="en">' in r.text and 'action="/language/"' in r.text and "Your cart" in r.text
    r = _idioma(cli, "pt")
    assert r.status_code == 303 and r.headers["location"] == "/cart/"
    assert "urace_lang=pt" in r.headers["set-cookie"] and "Max-Age=31536000" in r.headers["set-cookie"]
    r = cli.get("/cart/")
    assert '<html lang="pt-BR">' in r.text and _h1(r.text) == "Seu carrinho" and r.headers["cache-control"] == "no-store"
    assert 'value="pt" aria-pressed="true"' in r.text
    for ruim in ("https://evil.example.com/", "//evil.example.com/", "/ops/api/users", "/cart/\\x"):
        assert _idioma(cli, "en", ruim).headers["location"] == "/cart/", ruim
    assert _idioma(cli, "xx").headers["set-cookie"].startswith("urace_lang=en")
    assert _idioma(cli, "pt", "/store/cancelled/").headers["location"] == "/store/cancelled/"
    r = cli.get("/store/cancelled/")
    assert _h1(r.text) == "Checkout cancelado" and "Nada foi cobrado" in r.text


def test_comprou_em_portugues_a_pagina_o_stripe_e_os_emails_saem_em_portugues(compra):
    cli, con, st, qbo, tmp, sid, conta, pid, dia, p = compra
    _idioma(cli, "pt")
    d = cli.post("/ops/api/vitrine/carrinho", json={"itens": [_sessao(sid, dia, pid)]}).json()
    assert "(manhã)" in d["linhas"][0]["detalhe"] and " de " in d["linhas"][0]["detalhe"]
    assert _checkout(cli, [_sessao(sid, dia, pid), {"tipo": "produto", "produto": p["slug"]}]).status_code == 200
    campos = st.chamadas[-1][2]
    assert campos["locale"] == "pt-BR" and campos["customer_email"] == EMAIL
    o = _pedido(con)
    assert o["lang"] == "pt"
    s = st.sessoes[o["stripe_session_id"]]
    s.update(payment_status="unpaid")
    _webhook(cli, s, "checkout.session.completed", "evt_pt1")
    r = cli.get(pedido_site.caminho(o))
    assert '<html lang="pt-BR">' in r.text and _h1(r.text) == "Pagamento em confirmação" and "Não pague de novo" in r.text
    assert "Os seus dados" in r.text and "Pagamento em confirmação | URACE" in r.text
    (proc,) = [m for m in _emails(tmp) if m["to"] == EMAIL]
    assert proc["subject"].startswith("Estamos confirmando o seu pagamento") and "Página do seu pedido" in proc["text"]
    assert "(manhã)" in proc["text"]
    _webhook(cli, s, "checkout.session.async_payment_succeeded", "evt_pt2")
    conf = [m for m in _emails(tmp) if m["to"] == EMAIL and "confirmado" in m["subject"]]
    assert len(conf) == 1 and "Obrigado pelo pedido" in conf[0]["text"] and "Assine a waiver" in conf[0]["text"]
    equipe = [m for m in _emails(tmp) if m["to"] == "support@urace.us"]
    assert equipe and all("pedido #" in m["subject"] for m in equipe), "a equipe sempre em português"
    # quem abre a página em inglês vê em inglês (a chave é de quem olha)
    _idioma(cli, "en", pedido_site.caminho(o))
    assert _h1(cli.get(pedido_site.caminho(o)).text) == "Payment confirmed"


def test_mensagens_do_carrinho_em_portugues(compra):
    cli, con, st, qbo, tmp, sid, conta, pid, dia, p = compra
    _idioma(cli, "pt")
    cli.post("/ops/api/portal/logout")
    r = cli.post("/ops/api/vitrine/carrinho/checkout", json={"itens": [{"tipo": "produto", "produto": p["slug"]}]})
    assert r.status_code == 401 and r.json()["erro"] == "Entre ou crie a sua conta URACE para comprar."
    d = cli.post("/ops/api/vitrine/carrinho", json={"itens": [_sessao(sid, dia, turno="noite")]}).json()
    assert d["linhas"][0]["erro"] == "Escolha manhã ou tarde."

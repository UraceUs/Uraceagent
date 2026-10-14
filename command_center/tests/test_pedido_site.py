"""#245: uma página no site para cada resultado do pagamento no Stripe.

Dono, 14/10, sobre os 4 eventos do webhook (`checkout.session.completed`, `async_payment_succeeded`,
`async_payment_failed`, `expired`): "monte páginas para cada um no site".

O que estes testes trancam: cada evento leva ao estado certo do pedido, à página certa no link pessoal
(`/order/<token>/`, token com selo HMAC: mexido → 404) e ao e-mail certo, uma vez só; "Try again" e
"Restore cart" remontam o carrinho com as mesmas escolhas e o servidor recalcula preço e vaga; a vaga
não fica presa por um pagamento que falhou; a volta do Stripe usa a mesma página; o painel mostra o
estado e o link. Dados fictícios (@example.com, 555-01xx). Nada fala com o Stripe de verdade."""
import json
import re

import pytest

from command_center.api import auth
from command_center.db import inserir, todos, um
from command_center.providers import carrinho, pedido_site, servicos_site, stripe_loja
from command_center.tests.test_agenda_sessoes import periodo, proximo
from command_center.tests.test_carrinho import _checkout, _entrar, _sessao, loja  # noqa: F401
from command_center.tests.test_stripe_loja import _assinado, _comprar, _emails, _evento, _simples, amb  # noqa: F401

EMAIL = "maya.teste@example.com"


def _webhook(cli, s, tipo, eid, **extra):
    corpo, cab = _assinado(_evento(s, tipo=tipo, eid=eid, **extra))
    r = cli.post("/ops/api/stripe/webhook", content=corpo, headers=cab)
    assert r.status_code == 200, r.text
    return r.json()["resultado"]


def _pedido(con):
    return um(con, "SELECT * FROM store_orders ORDER BY id DESC LIMIT 1")


def _pagina(cli, o):
    r = cli.get(pedido_site.caminho(o))
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store" and r.headers["referrer-policy"] == "no-referrer"
    assert 'name="robots" content="noindex' in r.text
    assert len(re.findall(r"<h1[ >]", r.text)) == 1, "um h1 por página"
    return r


def _h1(html):
    return re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S).group(1).strip()


def _titulo(html):
    return re.search(r"<title>(.*?)</title>", html).group(1).replace("&#x27;", "'")


def _cliente(tmp, para):
    return [m for m in _emails(tmp) if m["to"] == para]


@pytest.fixture()
def pedido_sessao(loja):  # noqa: F811
    """Conta, piloto e um carrinho com uma sessão (preço 719 + depósito 400) e um produto, já no Stripe."""
    cli, con, st, qbo, tmp, sid = loja
    conta, pid = _entrar(cli, con, email=EMAIL, nome="Maya Teste", piloto="Noah Teste")
    p = _simples()
    dia = proximo(5)
    assert _checkout(cli, [_sessao(sid, dia, pid), {"tipo": "produto", "produto": p["slug"]}]).status_code == 200
    s = st.sessoes[next(reversed(st.sessoes))]
    return cli, con, st, qbo, tmp, sid, conta, pid, dia, p, s


# ------------------------------------------------------------------ o link pessoal
def test_token_com_selo_e_qualquer_outro_e_404(amb):  # noqa: F811
    cli, con, st, qbo, tmp = amb
    _comprar(cli, _simples())
    o = _pedido(con)
    tok = pedido_site.token(o)
    assert re.fullmatch(rf"{o['id']}-[A-Za-z0-9_-]{{27}}", tok)
    assert cli.get(f"/order/{tok}/").status_code == 200
    outro = inserir(con, "store_orders", product_slug="x", product_name="X", quantity=1, unit_price=1, amount=1, delivery="retirada")
    ruins = [f"{o['id']}-{'A' * 27}", f"{outro}-{tok.split('-', 1)[1]}", tok[:-1], "1", "abc", f"{o['id']}"]
    for ruim in ruins:
        r = cli.get(f"/order/{ruim}/")
        assert r.status_code == 404 and "Page not found" in r.text, ruim
        assert cli.get(f"/order/{ruim}/cart/").status_code == 404
        assert cli.post(f"/order/{ruim}/retry", data={}).status_code == 404
    assert pedido_site.achar(con, tok)["id"] == o["id"] and pedido_site.achar(con, ruins[1]) is None
    assert cli.get(f"https://ops.urace.us/order/{tok}/").status_code == 404, "o painel não serve a página do site"
    # a chave mora fora do repositório, criada na primeira vez, só legível pelo serviço
    import os
    chave = tmp / "pedidos.key"
    assert chave.exists() and oct(os.stat(chave).st_mode & 0o777) == "0o600"


# ------------------------------------------------------------------ completed + pago
def test_completed_pago_mostra_payment_confirmed_com_itens_deposito_e_proximos_passos(pedido_sessao):
    cli, con, st, qbo, tmp, sid, conta, pid, dia, p, s = pedido_sessao
    s.update(payment_status="paid", payment_intent="pi_245", customer_details={"email": EMAIL, "name": "Maya Teste"})
    assert _webhook(cli, s, "checkout.session.completed", "evt_p1") == "pago"
    o = _pedido(con)
    r = _pagina(cli, o)
    assert _h1(r.text) == "Payment confirmed" and _titulo(r.text) == "Payment confirmed | URACE"
    assert "Noah Teste" in r.text and p["name"] in r.text
    from command_center.vitrine.paginas import usd
    assert "Total paid" in r.text and usd(719 + 400 + float(p["price"])) in r.text
    assert "refundable security deposit $400" in r.text
    b = um(con, "SELECT id FROM bookings")
    assert f'/ops/portal/sessions/{b["id"]}"' in r.text and "Sign the waiver" in r.text
    assert "data-limpar-carrinho" not in r.text, "o link do e-mail não esvazia o carrinho de ninguém"
    conf = _cliente(tmp, EMAIL)
    assert len(conf) == 1 and pedido_site.link(o) in conf[0]["text"], "a confirmação leva o link da página"
    assert pedido_site.link(o) == f"https://novo.urace.us{pedido_site.caminho(o)}"


def test_volta_do_stripe_usa_a_mesma_pagina(pedido_sessao):
    cli, con, st, qbo, tmp, sid, conta, pid, dia, p, s = pedido_sessao
    s.update(payment_status="paid", customer_details={"email": EMAIL, "name": "Maya Teste"})
    r = cli.get(f"/cart/thanks/?session_id={s['id']}")
    assert _h1(r.text) == "Payment confirmed" and "data-limpar-carrinho" in r.text and r.headers["cache-control"] == "no-store"
    o = _pedido(con)
    assert f'href="{pedido_site.caminho(o)}"' in r.text, "a volta do Stripe aponta o link pessoal"
    # loja de um produto
    loc = _comprar(cli, p).headers["location"]
    s2 = st.sessoes[loc.rsplit("/", 1)[1]]
    r = cli.get(f"/store/thanks/?session_id={s2['id']}")
    assert _h1(r.text) == "Payment processing" and "confirming your payment" in r.text


# ------------------------------------------------------------------ completed + aguardando → async succeeded
def test_aguardando_depois_async_succeeded_confirma_e_manda_o_email_uma_vez(pedido_sessao):
    cli, con, st, qbo, tmp, sid, conta, pid, dia, p, s = pedido_sessao
    s.update(payment_status="unpaid", customer_details={"email": EMAIL, "name": "Maya Teste"})
    assert _webhook(cli, s, "checkout.session.completed", "evt_a1") == "aguardando"
    o = _pedido(con)
    r = _pagina(cli, o)
    assert _h1(r.text) == "Payment processing" and _titulo(r.text) == "Payment processing | URACE"
    assert "Please don't pay again" in r.text.replace("&#x27;", "'") and EMAIL in r.text
    assert "Try again" not in r.text and "Restore cart" not in r.text
    assert not _emails(tmp), "processando: nenhum e-mail ainda"
    assert not todos(con, "SELECT id FROM bookings"), "a vaga só é marcada quando o pagamento entra"
    for eid in ("evt_a2", "evt_a2", "evt_a3"):            # o mesmo evento duas vezes e outro do mesmo tipo
        _webhook(cli, s, "checkout.session.async_payment_succeeded", eid)
    o = _pedido(con)
    assert o["status"] == "pago"
    assert _h1(_pagina(cli, o).text) == "Payment confirmed"
    conf = _cliente(tmp, EMAIL)
    assert len(conf) == 1 and "confirmed" in conf[0]["subject"] and pedido_site.link(o) in conf[0]["text"]
    assert len(todos(con, "SELECT id FROM bookings")) == 1 and len(todos(con, "SELECT id FROM opportunities")) == 1


# ------------------------------------------------------------------ async failed
def test_async_failed_mostra_a_pagina_avisa_a_pessoa_e_a_equipe_uma_vez_e_nao_prende_a_vaga(pedido_sessao):
    cli, con, st, qbo, tmp, sid, conta, pid, dia, p, s = pedido_sessao
    s.update(payment_status="unpaid", customer_details={"email": EMAIL, "name": "Maya Teste", "phone": "+14075550147"})
    assert _webhook(cli, s, "checkout.session.completed", "evt_f1") == "aguardando"
    for eid in ("evt_f2", "evt_f2", "evt_f3"):
        assert _webhook(cli, s, "checkout.session.async_payment_failed", eid) in ("falhou", "duplicado")
    o = _pedido(con)
    assert (o["status"], o["outcome"], o["outcome_email"]) == ("falhou", "falhou", EMAIL) and o["outcome_notified_at"]
    r = _pagina(cli, o)
    assert _h1(r.text) == "Payment didn't go through" and _titulo(r.text) == "Payment didn't go through | URACE"
    assert "nothing was charged and no session was booked" in r.text
    assert f'action="/order/{pedido_site.token(o)}/retry"' in r.text and ">Try again<" in r.text
    cliente = _cliente(tmp, EMAIL)
    assert len(cliente) == 1 and "didn't go through" in cliente[0]["subject"]
    assert pedido_site.link(o) in cliente[0]["text"] and "nothing was charged" in cliente[0]["text"]
    equipe = _cliente(tmp, "support@urace.us")
    assert len(equipe) == 1 and "PAGAMENTO FALHOU" in equipe[0]["subject"] and pedido_site.link(o) in equipe[0]["text"]
    # a vaga não fica presa: nada marcado, o turno continua com a vaga
    assert not todos(con, "SELECT id FROM bookings") and not todos(con, "SELECT id FROM opportunities")
    assert periodo(con, dia, "manha")["spots"] == 1
    assert carrinho.cotar(con, [_sessao(sid, dia, pid)], conta)["linhas"][0]["erro"] is None
    # a rodada de 15 min não manda de novo
    con.execute("UPDATE store_orders SET updated_at='2026-01-01T00:00:00.000Z'")
    assert pedido_site.rodar(con) == {"avisos": 0} and len(_emails(tmp)) == 2


def test_aviso_que_falhou_no_envio_a_rodada_manda_depois_uma_vez(pedido_sessao, monkeypatch):
    cli, con, st, qbo, tmp, sid, conta, pid, dia, p, s = pedido_sessao
    from command_center.providers import email_envio
    original, fora = email_envio.enviar, [True]

    def talvez(*a, **k):
        if fora[0]:
            raise email_envio.ErroEnvio("Gmail fora do ar")
        return original(*a, **k)
    monkeypatch.setattr(email_envio, "enviar", talvez)
    s.update(customer_details={"email": EMAIL, "name": "Maya Teste"})
    _webhook(cli, s, "checkout.session.async_payment_failed", "evt_r1")
    o = _pedido(con)
    assert o["outcome_notified_at"] is None and "fora do ar" in o["outcome_notify_error"]
    fora[0] = False
    con.execute("UPDATE store_orders SET updated_at='2026-01-01T00:00:00.000Z'")
    assert pedido_site.rodar(con) == {"avisos": 1}
    assert pedido_site.rodar(con) == {"avisos": 0}
    assert len(_cliente(tmp, EMAIL)) == 1 and len(_cliente(tmp, "support@urace.us")) == 1


# ------------------------------------------------------------------ expired
def test_expirado_com_email_do_checkout_avisa_uma_vez_e_sem_email_nao_avisa(amb):  # noqa: F811
    cli, con, st, qbo, tmp = amb
    p = _simples()
    s = st.sessoes[_comprar(cli, p).headers["location"].rsplit("/", 1)[1]]
    for eid in ("evt_e1", "evt_e1", "evt_e2"):
        _webhook(cli, s, "checkout.session.expired", eid, customer_details={"email": "Ana.Teste@example.com"})
    o = _pedido(con)
    assert (o["status"], o["outcome"], o["outcome_email"]) == ("expirado", "expirado", "ana.teste@example.com")
    r = _pagina(cli, o)
    assert _h1(r.text) == "Checkout expired" and _titulo(r.text) == "Checkout expired | URACE"
    assert "nothing was charged" in r.text and f'href="/order/{pedido_site.token(o)}/cart/">Restore cart<' in r.text
    msgs = _emails(tmp)
    assert [m["to"] for m in msgs] == ["ana.teste@example.com"], "um aviso só, e nada para a equipe"
    assert "expired" in msgs[0]["subject"] and pedido_site.link(o) in msgs[0]["text"]
    # sem e-mail informado no Checkout: ninguém recebe nada (nem a equipe)
    s2 = st.sessoes[_comprar(cli, p).headers["location"].rsplit("/", 1)[1]]
    _webhook(cli, s2, "checkout.session.expired", "evt_e3")
    o2 = _pedido(con)
    assert o2["status"] == "expirado" and o2["outcome_email"] is None
    assert len(_emails(tmp)) == 1 and _h1(_pagina(cli, o2).text) == "Checkout expired"


def test_carrinho_com_conta_expirado_sem_email_digitado_nao_avisa(pedido_sessao):
    """O e-mail da conta vai pré-preenchido no Checkout; o aviso de expirado só sai com o e-mail que o
    Stripe devolve no evento (a pessoa chegou a informar)."""
    cli, con, st, qbo, tmp, sid, conta, pid, dia, p, s = pedido_sessao
    _webhook(cli, s, "checkout.session.expired", "evt_x1")
    o = _pedido(con)
    assert o["status"] == "expirado" and o["email"] == EMAIL and o["outcome_email"] is None and not _emails(tmp)


# ------------------------------------------------------------------ Try again / Restore cart
def test_try_again_recalcula_o_preco_e_abre_um_checkout_novo(pedido_sessao):
    cli, con, st, qbo, tmp, sid, conta, pid, dia, p, s = pedido_sessao
    s.update(customer_details={"email": EMAIL, "name": "Maya Teste"})
    _webhook(cli, s, "checkout.session.async_payment_failed", "evt_t1")
    velho = _pedido(con)
    servicos_site.mudar(con, None, sid, {"price": 799, "deposit": 300})       # o gerente muda o preço depois
    con.commit()
    n = len(st.chamadas)
    r = cli.post(f"/order/{pedido_site.token(velho)}/retry", data={"csrf": cli.cookies.get("cp_csrf")}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("https://checkout.stripe.com/c/pay/cs_test_")
    (_, _, campos, _), = st.chamadas[n:]
    precos = [(i["price_data"]["unit_amount"], i["price_data"]["product_data"]["name"][:30]) for i in campos["line_items"]]
    assert precos[0][0] == 79900 and precos[1][0] == 30000, "preço e depósito de hoje, do servidor"
    assert precos[2][0] == round(float(p["price"]) * 100)
    novo = _pedido(con)
    assert novo["id"] != velho["id"] and novo["retry_of"] == velho["id"] and novo["status"] == "aberto"
    assert um(con, "SELECT status FROM store_orders WHERE id=?", (velho["id"],))["status"] == "falhou", "o velho fica como estava"
    # pago o novo, a página do velho aponta o novo e não oferece pagar de novo
    st.sessoes[novo["stripe_session_id"]].update(payment_status="paid", customer_details={"email": EMAIL, "name": "Maya Teste"})
    _webhook(cli, st.sessoes[novo["stripe_session_id"]], "checkout.session.completed", "evt_t2")
    r = _pagina(cli, velho)
    assert f'href="{pedido_site.caminho(novo)}"' in r.text and ">Try again<" not in r.text
    assert cli.post(f"/order/{pedido_site.token(velho)}/retry", data={}, follow_redirects=False).headers["location"] == \
        pedido_site.caminho(velho)


def test_try_again_sem_a_conta_ou_sem_a_vaga_vai_para_o_carrinho_restaurado(pedido_sessao):
    cli, con, st, qbo, tmp, sid, conta, pid, dia, p, s = pedido_sessao
    _webhook(cli, s, "checkout.session.async_payment_failed", "evt_v1")
    o = _pedido(con)
    tok = pedido_site.token(o)
    n = len(st.chamadas)
    r = cli.post(f"/order/{tok}/retry", data={}, follow_redirects=False)       # sem o CSRF da conta
    assert r.status_code == 303 and r.headers["location"] == f"/order/{tok}/cart/"
    # a vaga some (alguém marcou o último lugar): o servidor confere e não abre checkout
    from command_center.providers import agenda_sessoes as ag
    outra = inserir(con, "portal_accounts", email="leo.teste@example.com", pw_salt="x", pw_hash="x", name="Leo Teste",
                    birth_date="1980-01-01", terms_accepted_at="2026-09-30T00:00:00Z")
    from command_center.tests.dados_portal import completa
    p2 = inserir(con, "portal_pilots", account_id=outra, name="Leo Junior")
    completa(con, outra, p2)
    ag.agendar(con, outra, dia.isoformat(), "manha", p2, None, sid)
    con.commit()
    r = cli.post(f"/order/{tok}/retry", data={"csrf": cli.cookies.get("cp_csrf")}, follow_redirects=False)
    assert r.headers["location"] == f"/order/{tok}/cart/" and len(st.chamadas) == n, "sem vaga, o Stripe nem é chamado"
    # o carrinho restaurado: as escolhas (nunca preço) e o servidor mostra que a vaga acabou
    r = cli.get(f"/order/{tok}/cart/")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store" and _h1(r.text) == "Your cart"
    itens = json.loads(re.search(r'data-restaurar="([^"]+)"', r.text).group(1).replace("&quot;", '"'))
    assert itens == [{"tipo": "sessao", "servico": sid, "data": dia.isoformat(), "turno": "manha", "piloto": pid},
                     {"tipo": "produto", "produto": p["slug"], "variacao": "", "quantidade": 1}]
    assert "back in your cart" in r.text
    cot = cli.post("/ops/api/vitrine/carrinho", json={"itens": itens}).json()
    assert cot["linhas"][0]["erro"].startswith("This time is no longer available")


def test_restore_cart_da_loja_de_um_produto_e_try_again_sem_conta(amb):  # noqa: F811
    cli, con, st, qbo, tmp = amb
    p = _simples()
    s = st.sessoes[_comprar(cli, p, quantidade="2", entrega="envio").headers["location"].rsplit("/", 1)[1]]
    _webhook(cli, s, "checkout.session.expired", "evt_l1")
    o = _pedido(con)
    tok = pedido_site.token(o)
    r = cli.get(f"/order/{tok}/cart/")
    assert '"produto":"' + p["slug"] + '"' in r.text.replace("&quot;", '"') and 'value="envio" checked' in r.text
    r = cli.post(f"/order/{tok}/retry", data={}, follow_redirects=False)      # produto não pede conta
    assert r.status_code == 303 and r.headers["location"].startswith("https://checkout.stripe.com/")
    campos = st.chamadas[-1][2]
    assert campos["line_items"][0]["quantity"] == 2 and campos["line_items"][0]["price_data"]["unit_amount"] == round(p["price"] * 100)
    assert "shipping_address_collection" in campos
    assert _pedido(con)["retry_of"] == o["id"]


def test_pedido_pago_nao_restaura_nem_paga_de_novo(amb):  # noqa: F811
    cli, con, st, qbo, tmp = amb
    s = st.sessoes[_comprar(cli, _simples()).headers["location"].rsplit("/", 1)[1]]
    s.update(payment_status="paid", customer_details={"email": "bia.teste@example.com", "name": "Bia Teste"})
    _webhook(cli, s, "checkout.session.completed", "evt_pp")
    o = _pedido(con)
    n = len(st.chamadas)
    for r in (cli.get(f"/order/{pedido_site.token(o)}/cart/", follow_redirects=False),
              cli.post(f"/order/{pedido_site.token(o)}/retry", data={}, follow_redirects=False)):
        assert r.status_code == 303 and r.headers["location"] == pedido_site.caminho(o)
    assert len(st.chamadas) == n


def test_pagina_confere_no_stripe_quando_o_webhook_nao_chegou(amb):  # noqa: F811
    cli, con, st, qbo, tmp = amb
    s = st.sessoes[_comprar(cli, _simples()).headers["location"].rsplit("/", 1)[1]]
    o = _pedido(con)
    s["status"] = "open"
    assert _h1(_pagina(cli, o).text) == "Checkout not finished", "checkout aberto não vira 'processando'"
    assert _pedido(con)["status"] == "aberto"
    s["status"] = "expired"
    assert _h1(_pagina(cli, o).text) == "Checkout expired"
    assert stripe_loja.status_da_sessao({"status": "expired"}) == "aguardando", "sem `conferindo`, igual a antes"


# ------------------------------------------------------------------ o painel
def test_painel_lista_os_pedidos_com_estado_e_link(pedido_sessao):
    cli, con, st, qbo, tmp, sid, conta, pid, dia, p, s = pedido_sessao
    _webhook(cli, s, "checkout.session.async_payment_failed", "evt_pn")
    falhou = _pedido(con)
    s2 = st.sessoes[_comprar(cli, p).headers["location"].rsplit("/", 1)[1]]
    s2.update(payment_status="paid", customer_details={"email": "rui.teste@example.com", "name": "Rui Teste"})
    _webhook(cli, s2, "checkout.session.completed", "evt_pn2")
    pago = _pedido(con)
    auth.criar_usuario(con, "closer@urace.us", "Carla Vendas", "OPERATOR", "senha-forte-123")
    con.commit()
    assert cli.get("/ops/api/site/pedidos").status_code == 401
    assert cli.post("/ops/api/auth/login", json={"email": "closer@urace.us", "password": "senha-forte-123"}).status_code == 200
    d = cli.get("/ops/api/site/pedidos?limit=1").json()
    assert d["total"] == 2 and len(d["pedidos"]) == 1 and d["pedidos"][0]["id"] == pago["id"]
    d = cli.get("/ops/api/site/pedidos?status=falhou").json()
    (x,) = d["pedidos"]
    assert (x["id"], x["status"], x["email"]) == (falhou["id"], "falhou", EMAIL) and x["aviso_em"]
    assert x["link"] == pedido_site.link(falhou) and x["caminho"] == pedido_site.caminho(falhou)
    assert "Noah Teste" in x["resumo"]
    venda = cli.get(f"/ops/api/sales/{pago['opp_id']}").json()
    assert venda["pedido"]["link"] == pedido_site.link(pago) and venda["pedido"]["status"] == "pago"

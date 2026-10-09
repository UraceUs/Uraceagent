"""#174: a loja paga no ato pelo Stripe Checkout. Nada aqui fala com o Stripe nem com o QuickBooks:
o Stripe é uma função falsa (`_http`) e o webhook é assinado aqui com um segredo de teste."""
import hashlib
import hmac
import json
import os
import time

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import vitrine  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir  # noqa: E402
from command_center.providers import stripe_loja  # noqa: E402
from command_center.vitrine import paginas_site  # noqa: E402

SEGREDO = "whsec_teste_123"


def _produtos():
    return paginas_site.dados("produtos.json")["produtos"]


def _simples():
    """Produto sem variação, com preço e em estoque."""
    return next(p for p in _produtos() if not p["variations"] and p["price"] and p["in_stock"])


def _com_variacao():
    return next(p for p in _produtos() if p["variations"] and p["in_stock"]
                and sum(1 for v in p["variations"] if v.get("price") and v.get("in_stock", True)) >= 2)


class StripeFalso:
    def __init__(self):
        self.chamadas, self.sessoes, self.n = [], {}, 0

    def __call__(self, metodo, caminho, campos=None, idem=None):
        self.chamadas.append((metodo, caminho, campos, idem))
        if metodo == "POST" and caminho == "/v1/checkout/sessions":
            self.n += 1
            sid = f"cs_test_{self.n:04d}"
            self.sessoes[sid] = {"id": sid, "object": "checkout.session", "url": f"https://checkout.stripe.com/c/pay/{sid}",
                                 "client_reference_id": campos["client_reference_id"], "payment_status": "unpaid",
                                 "amount_total": sum(i["price_data"]["unit_amount"] * i["quantity"] for i in campos["line_items"])}
            return self.sessoes[sid]
        if metodo == "GET" and caminho.startswith("/v1/checkout/sessions/"):
            return self.sessoes[caminho.rsplit("/", 1)[1]]
        raise AssertionError(caminho)


class QboFalso:
    def __init__(self, falhar=False):
        self.recibos, self.clientes, self.falhar = [], [], falhar

    def qbo_clientes_buscar(self, texto):
        return []

    def qbo_criar_cliente(self, nome, email=None, telefone=None):
        self.clientes.append((nome, email))
        return {"id": "77"}

    def item_loja_sistema(self, nome, preco, descricao=None):
        return {"id": "501", "nome": nome}

    def recibo_venda_sistema(self, **kw):
        if self.falhar:
            raise RuntimeError("QuickBooks fora do ar")
        self.recibos.append(kw)
        return {"id": "9001", "numero": kw["numero"], "total": 1, "link": "https://qbo/x"}


@pytest.fixture()
def amb(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    monkeypatch.setenv("CC_EMAIL_FAKE", str(tmp_path / "emails.jsonl"))
    monkeypatch.delenv("CC_SITE_HOSTS", raising=False)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_falsa")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SEGREDO)
    vitrine._envios.clear()
    st, qbo = StripeFalso(), QboFalso()
    monkeypatch.setattr(stripe_loja, "_http", st)
    monkeypatch.setattr(stripe_loja, "_qbo", lambda: qbo)
    with TestClient(app, base_url="https://novo.urace.us") as cli:
        con = conectar(); aplicar_schema(con)
        yield cli, con, st, qbo, tmp_path
        con.close()


def _assinado(evento, segredo=SEGREDO, t=None):
    corpo = json.dumps(evento).encode()
    t = str(int(t or time.time()))
    sig = hmac.new(segredo.encode(), t.encode() + b"." + corpo, hashlib.sha256).hexdigest()
    return corpo, {"Stripe-Signature": f"t={t},v1={sig}", "Content-Type": "application/json"}


def _evento(sessao, tipo="checkout.session.completed", eid="evt_1", **extra):
    return {"id": eid, "type": tipo, "data": {"object": {**sessao, **extra}}}


def _comprar(cli, p, **campos):
    dados = {"produto": p["slug"], "quantidade": "1", "entrega": "retirada", **campos}
    return cli.post("/ops/api/vitrine/checkout", data=dados, follow_redirects=False)


def _pagar(cli, st, sid, eid="evt_1", nome="Ana Lima", email="ana@exemplo.com", **extra):
    s = dict(st.sessoes[sid], payment_status="paid", payment_intent="pi_123",
             customer_details={"email": email, "name": nome, "phone": "+14075550100"}, **extra)
    st.sessoes[sid] = s
    corpo, cab = _assinado(_evento(s, eid=eid))
    return cli.post("/ops/api/stripe/webhook", content=corpo, headers=cab)


def _emails(tmp_path):
    f = tmp_path / "emails.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []


# ------------------------------------------------------------------ assinatura
def test_assinatura_confere_segredo_tempo_e_corpo():
    corpo = b'{"id":"evt_1"}'
    t = int(time.time())
    sig = hmac.new(SEGREDO.encode(), f"{t}.".encode() + corpo, hashlib.sha256).hexdigest()
    assert stripe_loja.assinatura_ok(corpo, f"t={t},v1={sig}", SEGREDO)
    assert stripe_loja.assinatura_ok(corpo, f"t={t},v1=errada,v1={sig}", SEGREDO), "o Stripe manda mais de um v1 ao trocar o segredo"
    assert not stripe_loja.assinatura_ok(corpo, f"t={t},v1={sig}", "whsec_outro")
    assert not stripe_loja.assinatura_ok(corpo + b" ", f"t={t},v1={sig}", SEGREDO), "corpo mexido não passa"
    assert not stripe_loja.assinatura_ok(corpo, f"t={t},v1={sig}", SEGREDO, agora_ts=t + 301), "evento velho reenviado não passa"
    assert not stripe_loja.assinatura_ok(corpo, "", SEGREDO) and not stripe_loja.assinatura_ok(corpo, f"t={t},v1={sig}", "")


# ------------------------------------------------------------------ a página do produto
def test_sem_chave_a_loja_continua_no_pedido_para_a_equipe(amb, monkeypatch):
    cli, *_ = amb
    monkeypatch.delenv("STRIPE_SECRET_KEY")
    p = _simples()
    html = cli.get(f"/store/p/{p['slug']}/").text
    assert "/ops/api/vitrine/checkout" not in html and "Order this" in html
    r = _comprar(cli, p)
    assert r.status_code == 303 and r.headers["location"] == f"/store/p/{p['slug']}/?checkout=erro"


def test_com_chave_o_produto_com_preco_e_estoque_tem_buy_now(amb):
    cli, *_ = amb
    p = _simples()
    r = cli.get(f"/store/p/{p['slug']}/")
    assert 'action="/ops/api/vitrine/checkout"' in r.text and ">Buy now<" in r.text
    assert f'name="produto" value="{p["slug"]}"' in r.text
    assert "Send order request" in r.text, "o pedido para a equipe continua, para quem quer perguntar antes"
    assert "form-action 'self' https://checkout.stripe.com;" in r.headers["content-security-policy"]
    assert "script-src 'self';" in r.headers["content-security-policy"], "nenhum script de fora"
    assert len(paginas_site.re.findall(r"<h1[ >]", r.text)) == 1


def test_sem_preco_ou_sem_estoque_nao_vende_online(amb):
    cli, *_ = amb
    sem_preco = next(p for p in _produtos() if not p["price"])
    fora = next(p for p in _produtos() if not p["in_stock"])
    for p in (sem_preco, fora):
        html = cli.get(f"/store/p/{p['slug']}/").text
        assert "/ops/api/vitrine/checkout" not in html, p["slug"]
        r = _comprar(cli, p)
        assert r.status_code == 303 and "checkout=erro" in r.headers["location"]
    con = amb[1]
    assert con.execute("SELECT COUNT(*) FROM store_orders").fetchone()[0] == 0


# ------------------------------------------------------------------ a sessão
def test_checkout_usa_o_preco_do_catalogo_e_manda_ao_stripe(amb):
    cli, con, st, *_ = amb
    p = _com_variacao()
    v = [x for x in p["variations"] if x.get("price") and x.get("in_stock", True)][1]
    nome_v = " / ".join(v["attrs"])
    r = _comprar(cli, p, variacao=nome_v, quantidade="3", entrega="envio", preco="0.01", amount="1")
    assert r.status_code == 303 and r.headers["location"].startswith("https://checkout.stripe.com/c/pay/cs_test_")
    _, caminho, campos, idem = st.chamadas[-1]
    item = campos["line_items"][0]
    assert item["price_data"]["unit_amount"] == round(v["price"] * 100) and item["quantity"] == 3, "o preço nunca vem do formulário"
    assert item["price_data"]["currency"] == "usd" and nome_v in item["price_data"]["product_data"]["name"]
    assert campos["success_url"] == "https://novo.urace.us/store/thanks/?session_id={CHECKOUT_SESSION_ID}"
    assert campos["cancel_url"] == f"https://novo.urace.us/store/cancelled/?p={p['slug']}"
    assert "US" in campos["shipping_address_collection"]["allowed_countries"], "envio: o Stripe pede o endereço"
    o = dict(con.execute("SELECT * FROM store_orders").fetchone())
    assert idem == f"urace-loja-{o['id']}" and campos["client_reference_id"] == str(o["id"])
    assert (o["status"], o["quantity"], o["unit_price"], o["amount"], o["delivery"]) == ("aberto", 3, v["price"], round(v["price"] * 3, 2), "envio")
    assert o["stripe_session_id"] == r.headers["location"].rsplit("/", 1)[1]


def test_retirada_nao_pede_endereco_e_quantidade_tem_limite(amb):
    cli, con, st, *_ = amb
    p = _simples()
    _comprar(cli, p, quantidade="500")
    campos = st.chamadas[-1][2]
    assert "shipping_address_collection" not in campos and campos["line_items"][0]["quantity"] == 20


def test_variacao_fora_de_estoque_ou_inexistente_nao_vende(amb):
    cli, con, st, *_ = amb
    p = _com_variacao()
    r = _comprar(cli, p, variacao="nao-existe")
    assert r.status_code == 303 and "checkout=erro" in r.headers["location"] and not st.chamadas
    r = cli.post("/ops/api/vitrine/checkout", json={"produto": p["slug"], "variacao": "nao-existe"},
                 headers={"Accept": "application/json"})
    assert r.status_code == 400 and r.json()["erro"] == "Please choose an option."


def test_stripe_fora_do_ar_volta_para_o_produto_com_aviso(amb, monkeypatch):
    cli, con, *_ = amb

    def cai(*a, **k):
        raise stripe_loja.ErroStripe("Stripe HTTP 500")
    monkeypatch.setattr(stripe_loja, "_http", cai)
    p = _simples()
    r = _comprar(cli, p)
    assert r.headers["location"] == f"/store/p/{p['slug']}/?checkout=erro"
    assert "couldn’t open the secure checkout" in cli.get(r.headers["location"]).text
    assert con.execute("SELECT status FROM store_orders").fetchone()[0] == "falhou"


# ------------------------------------------------------------------ o webhook
def test_pago_vira_venda_ganha_com_card_emails_e_recibo_no_quickbooks(amb):
    cli, con, st, qbo, tmp = amb
    p = _simples()
    sid = _comprar(cli, p).headers["location"].rsplit("/", 1)[1]
    r = _pagar(cli, st, sid)
    assert r.status_code == 200 and r.json()["resultado"] == "pago"
    o = dict(con.execute("SELECT * FROM store_orders").fetchone())
    assert o["status"] == "pago" and o["amount_paid"] == p["price"] and o["email"] == "ana@exemplo.com"
    opp = dict(con.execute("SELECT * FROM opportunities WHERE id=?", (o["opp_id"],)).fetchone())
    assert (opp["stage"], opp["source"], opp["amount"]) == ("GANHO", "Site", p["price"])
    assert opp["service"] == f"Store: {p['name']}" and "pago no Stripe" in opp["notes"]
    card = dict(con.execute("SELECT * FROM clients WHERE id=?", (opp["client_id"],)).fetchone())
    assert (card["name"], card["email"]) == ("Ana Lima", "ana@exemplo.com"), "ninguém com esse e-mail: card novo"
    para = [e["to"] for e in _emails(tmp)]
    assert para == ["ana@exemplo.com", "support@urace.us"]
    assert "Order #%d confirmed" % o["id"] in _emails(tmp)[0]["subject"]
    assert qbo.recibos and qbo.recibos[0]["numero"] == f"WEB-{o['id']:05d}" and qbo.recibos[0]["cliente_id"] == "77"
    assert qbo.recibos[0]["linhas"][0]["unitario"] == p["price"]
    o = dict(con.execute("SELECT * FROM store_orders").fetchone())
    assert o["qbo_receipt_id"] == "9001" and o["notified_at"]


def test_o_mesmo_evento_duas_vezes_nao_cria_dois_pedidos(amb):
    cli, con, st, qbo, tmp = amb
    sid = _comprar(cli, _simples()).headers["location"].rsplit("/", 1)[1]
    _pagar(cli, st, sid, eid="evt_9")
    r = _pagar(cli, st, sid, eid="evt_9")
    assert r.json()["resultado"] == "duplicado"
    r = _pagar(cli, st, sid, eid="evt_10")              # outro evento da mesma sessão (async_payment etc.)
    assert r.json()["resultado"] == "pago"
    assert con.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0] == 1
    assert len(qbo.recibos) == 1 and len(_emails(tmp)) == 2


def test_assinatura_errada_ou_sem_segredo_nao_muda_nada(amb, monkeypatch):
    cli, con, st, *_ = amb
    sid = _comprar(cli, _simples()).headers["location"].rsplit("/", 1)[1]
    corpo, cab = _assinado(_evento(dict(st.sessoes[sid], payment_status="paid")), segredo="whsec_de_outro")
    assert cli.post("/ops/api/stripe/webhook", content=corpo, headers=cab).status_code == 400
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET")
    corpo, cab = _assinado(_evento(dict(st.sessoes[sid], payment_status="paid")))
    assert cli.post("/ops/api/stripe/webhook", content=corpo, headers=cab).status_code == 503
    assert con.execute("SELECT status FROM store_orders").fetchone()[0] == "aberto"
    assert con.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0] == 0


def test_sessao_expirada_e_evento_de_outra_coisa(amb):
    cli, con, st, *_ = amb
    sid = _comprar(cli, _simples()).headers["location"].rsplit("/", 1)[1]
    corpo, cab = _assinado(_evento(st.sessoes[sid], tipo="checkout.session.expired", eid="evt_x"))
    assert cli.post("/ops/api/stripe/webhook", content=corpo, headers=cab).json()["resultado"] == "expirado"
    corpo, cab = _assinado({"id": "evt_y", "type": "charge.refunded", "data": {"object": {}}})
    assert cli.post("/ops/api/stripe/webhook", content=corpo, headers=cab).json()["resultado"] == "ignorado"
    corpo, cab = _assinado(_evento({"id": "cs_de_outro_site", "payment_status": "paid"}, eid="evt_z"))
    assert cli.post("/ops/api/stripe/webhook", content=corpo, headers=cab).json()["resultado"] == "sem pedido"
    assert con.execute("SELECT status FROM store_orders").fetchone()[0] == "expirado"


def test_pagamento_que_confirma_depois_espera_e_depois_vende(amb):
    cli, con, st, *_ = amb
    sid = _comprar(cli, _simples()).headers["location"].rsplit("/", 1)[1]
    s = dict(st.sessoes[sid], payment_status="unpaid", customer_details={"email": "b@exemplo.com", "name": "Bia"})
    corpo, cab = _assinado(_evento(s, eid="evt_a"))
    assert cli.post("/ops/api/stripe/webhook", content=corpo, headers=cab).json()["resultado"] == "aguardando"
    assert con.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0] == 0
    corpo, cab = _assinado(_evento(s, tipo="checkout.session.async_payment_succeeded", eid="evt_b"))
    assert cli.post("/ops/api/stripe/webhook", content=corpo, headers=cab).json()["resultado"] == "pago"
    assert con.execute("SELECT stage FROM opportunities").fetchone()[0] == "GANHO"


# ------------------------------------------------------------------ o card do cliente
def test_card_existente_so_liga_com_email_e_nome(amb):
    cli, con, st, *_ = amb
    ana = inserir(con, "clients", name="Ana Lima", email="ana@exemplo.com", status="ACTIVE")
    sid = _comprar(cli, _simples()).headers["location"].rsplit("/", 1)[1]
    _pagar(cli, st, sid, eid="evt_1", nome="ANA LIMA")
    opp = con.execute("SELECT stage, client_id FROM opportunities").fetchone()
    assert tuple(opp) == ("GANHO", ana)

    inserir(con, "clients", name="Carlos Souza", email="familia@exemplo.com", status="ACTIVE")
    sid = _comprar(cli, _simples()).headers["location"].rsplit("/", 1)[1]
    _pagar(cli, st, sid, eid="evt_2", nome="Marina Souza", email="familia@exemplo.com")
    opp = dict(con.execute("SELECT * FROM opportunities ORDER BY id DESC").fetchone())
    assert opp["client_id"] is None and opp["stage"] == "FECHAMENTO", "e-mail de outro card: nunca no card de outra pessoa"
    assert "vincular à mão" in opp["notes"]
    assert con.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == 2, "nem cria card duplicado"


# ------------------------------------------------------------------ a volta do Stripe
def test_pagina_de_obrigado_confere_no_stripe_quando_o_webhook_atrasa(amb):
    cli, con, st, qbo, tmp = amb
    p = _simples()
    sid = _comprar(cli, p).headers["location"].rsplit("/", 1)[1]
    st.sessoes[sid].update(payment_status="paid", customer_details={"email": "c@exemplo.com", "name": "Caio Reis"})
    r = cli.get(f"/store/thanks/?session_id={sid}")
    assert r.status_code == 200 and "Your order is confirmed" in r.text and "noindex" in r.text
    assert r.headers["cache-control"] == "no-store"
    assert con.execute("SELECT status FROM store_orders").fetchone()[0] == "pago"
    _pagar(cli, st, sid, eid="evt_tarde", nome="Caio Reis", email="c@exemplo.com")   # o webhook chega depois
    assert con.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0] == 1
    assert len(qbo.recibos) == 1 and len(_emails(tmp)) == 2


def test_obrigado_sem_pagamento_ainda_e_cancelado(amb):
    cli, con, st, *_ = amb
    p = _simples()
    sid = _comprar(cli, p).headers["location"].rsplit("/", 1)[1]
    assert "confirming your payment" in cli.get(f"/store/thanks/?session_id={sid}").text
    assert "Thank you" in cli.get("/store/thanks/?session_id=<script>").text
    r = cli.get(f"/store/cancelled/?p={p['slug']}")
    assert "Nothing was charged" in r.text and f'href="/store/p/{p["slug"]}/"' in r.text and "noindex" in r.text
    assert "/store/thanks/" not in paginas_site.caminhos() and "/store/cancelled/" not in paginas_site.caminhos()


def test_quickbooks_fora_do_ar_a_rotina_tenta_de_novo(amb, monkeypatch):
    cli, con, st, qbo, tmp = amb
    qbo.falhar = True
    sid = _comprar(cli, _simples()).headers["location"].rsplit("/", 1)[1]
    _pagar(cli, st, sid)
    o = dict(con.execute("SELECT * FROM store_orders").fetchone())
    assert o["qbo_receipt_id"] is None and "fora do ar" in o["qbo_error"]
    assert con.execute("SELECT ok FROM opp_events WHERE kind='invoice'").fetchone()[0] == 0
    qbo.falhar = False
    con.execute("UPDATE store_orders SET paid_at='2026-10-01T00:00:00.000Z'")
    assert stripe_loja.rodar(con, qbo=qbo) == {"avisados": 0, "qbo": 1}
    assert con.execute("SELECT qbo_receipt_id FROM store_orders").fetchone()[0] == "9001"
    assert stripe_loja.rodar(con, qbo=qbo) == {"avisados": 0, "qbo": 0}

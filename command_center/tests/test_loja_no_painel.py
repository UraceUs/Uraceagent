"""#298 (dono, 16/10): *"nos produtos da loja, colocar o valor de envio, o shipping, o valor de shipping … o valor
do Security Deposit … que eu consiga alterar … essas funções serão necessárias que sejam ativas permanentemente"*.
Decisões: frete = **valor fixo por produto**; no painel = **tudo do produto**.

O que estes testes trancam:
- os 70 produtos do arquivo entram no banco uma vez, sem perder nada (a loja sai igual), e o que a equipe muda
  ou esconde nunca volta na subida seguinte;
- a loja, a página do produto, o sitemap e o carrinho leem o banco: nome, preço, promoção, estoque, escondido;
- o frete fixo do produto (× quantidade) entra no Stripe como linha "Shipping" só com "Ship to me"; a retirada
  continua grátis; sem frete no painel, a equipe combina à parte como antes; o pedido, o e-mail e o painel mostram;
- o depósito de segurança do produto vira a linha dele no Stripe;
- o produto a US$ 1 com frete 0 fecha o checkout em US$ 1,00;
- o painel: só o gerente muda, tudo auditado; texto com script sai limpo; foto vira WebP sem EXIF.
"""
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from command_center.api import auth
from command_center.api.main import app
from command_center.db import aplicar_schema, um
from command_center.providers import carrinho, loja as lj
from command_center.tests.test_carrinho import _checkout, _entrar, _pagar, loja  # noqa: F401
from command_center.tests.test_stripe_loja import _emails, amb  # noqa: F401
from command_center.vitrine import paginas_site

SENHA = "pista-molhada-7"


def _arquivo():
    return paginas_site.dados("produtos.json")["produtos"]


def _um_simples(con):
    return next(p for p in lj.catalogo(con) if not p["variations"] and p["price"] and p["in_stock"])


def _item(slug, qtd=1, variacao=""):
    return {"tipo": "produto", "produto": slug, "variacao": variacao, "quantidade": qtd}


def _stripe(st):
    return next(c for m, cam, c, _i in reversed(st.chamadas) if m == "POST" and cam == "/v1/checkout/sessions")


def _linhas_stripe(st):
    return [(i["price_data"]["product_data"]["name"], i["quantity"], i["price_data"]["unit_amount"])
            for i in _stripe(st)["line_items"]]


@pytest.fixture()
def painel(loja):  # noqa: F811
    """O painel (outro endereço, o mesmo banco): um gerente e um operador."""
    cli, con, st, qbo, tmp, sid = loja
    auth.criar_usuario(con, "ger@example.com", "Gerente", "MANAGER", SENHA)
    auth.criar_usuario(con, "op@example.com", "Operador", "OPERATOR", SENHA)
    con.commit()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t, loja


def _entra(t, email):
    t.cookies.clear()
    assert t.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": t.cookies.get("cc_csrf")}


# ------------------------------------------------------------------ 1. o arquivo entra no banco uma vez
def test_os_70_produtos_entram_no_banco_sem_perder_nada(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    arquivo = _arquivo()
    banco = lj.catalogo(con)
    assert len(banco) == len(arquivo) == 70
    for a, b in zip(arquivo, banco):
        assert {k: b[k] for k in a} == {**a, "sku": a.get("sku") or ""}, a["slug"]
        assert (b["shipping_fee"], b["deposit"], b["active"]) == (None, 0.0, True), "frete a combinar, como antes"


def test_o_que_a_equipe_muda_ou_esconde_nunca_volta(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    p = _um_simples(con)
    lj.mudar(con, None, p["id"], {"name": "Renamed by the team", "shipping_fee": "25"})
    outro = lj.catalogo(con)[5]
    lj.mudar(con, None, outro["id"], {"active": False})
    con.commit()
    aplicar_schema(con)
    aplicar_schema(con)
    assert um(con, "SELECT COUNT(*) AS n FROM store_products")["n"] == 70
    assert (lj.do_painel(con, p["id"])["name"], lj.do_painel(con, p["id"])["shipping_fee"]) == ("Renamed by the team", 25.0)
    assert not lj.do_painel(con, outro["id"])["active"]


# ------------------------------------------------------------------ 2. o site lê o banco
def test_a_loja_e_o_produto_mostram_o_que_o_painel_mudou(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    p = _um_simples(con)
    lj.mudar(con, None, p["id"], {"name": "Team Gloves Pro", "regular": "120", "promo": "99.90", "shipping_fee": "15"})
    con.commit()
    loja_html = cli.get("/store/").text
    assert "Team Gloves Pro" in loja_html and "<s>$120</s> $99.90" in loja_html
    html = cli.get(f"/store/p/{p['slug']}/").text
    assert "<h1 id=\"h-prod\">Team Gloves Pro</h1>" in html and "$99.90" in html
    assert "Ship to me <span class=\"opcional\">— shipping $15 per item</span>" in html
    ld = [json.loads(x) for x in __import__("re").findall(r'<script type="application/ld\+json">(.*?)</script>', html, 16)]
    oferta = next(x for x in ld if x.get("@type") == "Product")["offers"]
    assert oferta["price"] == "99.90", "o Google vê o preço do painel"


def test_produto_escondido_sai_da_loja_do_sitemap_e_do_carrinho(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    p = _um_simples(con)
    lj.mudar(con, None, p["id"], {"active": False})
    con.commit()
    assert f"/store/p/{p['slug']}/" not in cli.get("/store/").text
    assert cli.get(f"/store/p/{p['slug']}/").status_code == 404
    assert f"/store/p/{p['slug']}/" not in cli.get("/sitemap.xml").text
    linha = carrinho.cotar(con, [_item(p["slug"])])["linhas"][0]
    assert linha["erro"] and "no longer in the store" in linha["erro"]


# ------------------------------------------------------------------ 3. o frete no Stripe
def test_frete_fixo_vezes_a_quantidade_entra_no_stripe_so_com_ship_to_me(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    p = _um_simples(con)
    lj.mudar(con, None, p["id"], {"shipping_fee": "25"})
    con.commit()
    _entrar(cli, con)
    c = carrinho.cotar(con, [_item(p["slug"], 2)], entrega="envio")
    assert (c["frete"], c["frete_envio"], c["frete_a_combinar"]) == (50.0, 50.0, False)
    assert c["total"] == round(p["price"] * 2 + 50, 2)
    r = _checkout(cli, [_item(p["slug"], 2)], entrega="envio")
    assert r.status_code == 200, r.text
    assert ("Shipping", 1, 5000) in _linhas_stripe(st)
    o = um(con, "SELECT * FROM store_orders ORDER BY id DESC LIMIT 1")
    assert (o["delivery"], o["shipping_fee"], o["amount"]) == ("envio", 50.0, round(p["price"] * 2 + 50, 2))
    x = um(con, "SELECT * FROM store_order_items WHERE order_id=?", (o["id"],))
    assert x["shipping"] == 50.0
    # retirar na pista continua grátis: nenhuma linha de frete
    r = _checkout(cli, [_item(p["slug"], 2)], entrega="retirada")
    assert r.status_code == 200, r.text
    assert not [n for n, *_ in _linhas_stripe(st) if n == "Shipping"]


def test_sem_frete_no_painel_a_equipe_combina_a_parte_como_antes(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    p = _um_simples(con)
    c = carrinho.cotar(con, [_item(p["slug"])], entrega="envio")
    assert (c["frete"], c["frete_a_combinar"]) == (0.0, True)
    _entrar(cli, con)
    assert _checkout(cli, [_item(p["slug"])], entrega="envio").status_code == 200
    assert not [n for n, *_ in _linhas_stripe(st) if n == "Shipping"]
    assert um(con, "SELECT shipping_fee FROM store_orders ORDER BY id DESC LIMIT 1")["shipping_fee"] == 0.0


def test_o_pedido_o_email_e_o_painel_mostram_o_frete_cobrado(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    p = _um_simples(con)
    lj.mudar(con, None, p["id"], {"shipping_fee": "25"})
    con.commit()
    _entrar(cli, con)
    assert _checkout(cli, [_item(p["slug"], 2)], entrega="envio").status_code == 200
    sessao = next(reversed(st.sessoes))
    assert _pagar(cli, st, sessao).status_code == 200
    o = um(con, "SELECT * FROM store_orders WHERE stripe_session_id=?", (sessao,))
    assert o["status"] == "pago"
    cliente = [m for m in _emails(tmp) if m["to"] == "lia@example.com"]
    assert cliente and "Shipping (US$ 50.00) is included in your payment" in cliente[-1]["text"]
    assert "Shipping: US$ 50.00" in cliente[-1]["text"]
    equipe = [m for m in _emails(tmp) if m["to"] == "support@urace.us"]
    assert "frete US$ 50.00 cobrado no pedido" in equipe[-1]["text"]
    from command_center.providers import pedido_site
    pagina = cli.get(pedido_site.caminho(o)).text
    assert "Includes shipping" in pagina and "$50" in pagina
    nota = um(con, "SELECT notes FROM opportunities WHERE id=?", (o["opp_id"],))["notes"]
    assert "frete US$ 50.00 cobrado" in nota
    linhas = carrinho.linhas_qbo(con, qbo, o["id"])
    assert any(x["descricao"].startswith("Shipping") and x["unitario"] == 50.0 for x in linhas), "o frete no recibo do QuickBooks"


def test_deposito_do_produto_vira_a_linha_dele_no_stripe(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    p = _um_simples(con)
    lj.mudar(con, None, p["id"], {"deposit": "100"})
    con.commit()
    _entrar(cli, con)
    assert _checkout(cli, [_item(p["slug"])]).status_code == 200
    assert (f"Refundable security deposit · {p['name']}", 1, 10000) in _linhas_stripe(st)


def test_buy_now_tambem_cobra_o_frete_do_painel(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    p = _um_simples(con)
    lj.mudar(con, None, p["id"], {"shipping_fee": "12.50"})
    con.commit()
    _entrar(cli, con)
    r = cli.post("/ops/api/vitrine/checkout", data={"produto": p["slug"], "quantidade": "2", "entrega": "envio"},
                 headers={"Accept": "application/json"})
    assert r.status_code == 200, r.text
    assert ("Shipping", 1, 2500) in _linhas_stripe(st)
    o = um(con, "SELECT * FROM store_orders ORDER BY id DESC LIMIT 1")
    assert o["shipping_fee"] == 25.0


def test_o_produto_de_um_dolar_com_frete_zero_fecha_em_um_dolar(painel):
    """Dono, 16/10: *"vou fazer uma compra com o valor de um dólar"*: o produto criado no painel."""
    t, (cli, con, st, qbo, tmp, sid) = painel
    h = _entra(t, "ger@example.com")
    r = t.post("/ops/api/site/produtos", headers=h, json={"name": "Checkout test item", "regular": "1",
                                                          "shipping_fee": "0", "categories": ["parts"]})
    assert r.status_code == 201, r.text
    slug = r.json()["produto"]["slug"]
    assert slug == "checkout-test-item"
    assert "Checkout test item" in cli.get("/store/?s=checkout+test").text
    assert "free shipping" in cli.get(f"/store/p/{slug}/").text
    _entrar(cli, con)
    assert _checkout(cli, [_item(slug)], entrega="envio").status_code == 200
    sessao = st.sessoes[next(reversed(st.sessoes))]
    assert sessao["amount_total"] == 100, "US$ 1,00 no Stripe"
    assert _linhas_stripe(st) == [("Checkout test item", 1, 100)]


# ------------------------------------------------------------------ 4. o painel
def test_so_o_gerente_muda_produto_e_fica_auditado(painel):
    t, (cli, con, st, qbo, tmp, sid) = painel
    p = _um_simples(con)
    h = _entra(t, "op@example.com")
    lista = t.get("/ops/api/site/produtos?limit=10", headers=h).json()
    assert (lista["total"], len(lista["produtos"])) == (70, 10), "paginado no servidor"
    assert t.patch(f"/ops/api/site/produtos/{p['id']}", headers=h, json={"shipping_fee": "9"}).status_code == 403
    h = _entra(t, "ger@example.com")
    r = t.patch(f"/ops/api/site/produtos/{p['id']}", headers=h, json={"shipping_fee": "9", "deposit": "50"})
    assert r.status_code == 200, r.text
    assert (r.json()["produto"]["shipping_fee"], r.json()["produto"]["deposit"]) == (9.0, 50.0)
    aud = um(con, "SELECT * FROM audit_logs WHERE event='store.product.update' ORDER BY id DESC LIMIT 1")
    assert aud and "shipping_fee" in aud["detail"]
    # vazio volta a "combinar à parte"
    r = t.patch(f"/ops/api/site/produtos/{p['id']}", headers=h, json={"shipping_fee": ""})
    assert r.json()["produto"]["shipping_fee"] is None


@pytest.mark.parametrize("campos, erro", [
    ({"regular": "50", "promo": "60"}, "promocional"),
    ({"regular": "-1"}, "preço"),
    ({"shipping_fee": "abc"}, "frete"),
    ({"images": [{"src": "https://outro-site.example.com/x.png"}]}, "foto"),
    ({"images": [{"src": "../../etc/passwd"}]}, "foto"),
    ({"categories": ["nao-existe"]}, "categoria"),
    ({"name": " "}, "nome"),
])
def test_o_painel_recusa_o_que_nao_faz_sentido(painel, campos, erro):
    t, (cli, con, st, qbo, tmp, sid) = painel
    p = _um_simples(con)
    h = _entra(t, "ger@example.com")
    r = t.patch(f"/ops/api/site/produtos/{p['id']}", headers=h, json=campos)
    assert r.status_code == 400 and erro in r.json()["detail"], r.text


def test_texto_do_produto_sai_limpo_de_script(painel):
    t, (cli, con, st, qbo, tmp, sid) = painel
    p = _um_simples(con)
    h = _entra(t, "ger@example.com")
    r = t.patch(f"/ops/api/site/produtos/{p['id']}", headers=h, json={
        "description": '<p onclick="x()">Great <strong>grip</strong><script>alert(1)</script></p><a href="javascript:alert(1)">x</a>'})
    assert r.status_code == 200, r.text
    d = r.json()["produto"]["description"]
    assert d == "<p>Great <strong>grip</strong></p>x"
    html = cli.get(f"/store/p/{p['slug']}/").text
    assert "Great <strong>grip</strong>" in html and "alert(1)" not in html


def test_variacoes_editadas_mudam_o_select_e_o_preco_do_carrinho(painel):
    t, (cli, con, st, qbo, tmp, sid) = painel
    p = _um_simples(con)
    h = _entra(t, "ger@example.com")
    r = t.patch(f"/ops/api/site/produtos/{p['id']}", headers=h, json={
        "attribute_names": ["Size"],
        "variations": [{"attrs": ["S"], "regular": "40", "promo": "30"}, {"attrs": ["M"], "regular": "45"},
                       {"attrs": ["L"], "regular": "45", "in_stock": False}]})
    assert r.status_code == 200, r.text
    q = r.json()["produto"]
    assert (q["type"], q["price"], q["price_min"], q["price_max"], q["on_sale"]) == ("variable", 30.0, 30.0, 45.0, True)
    assert q["attributes"] == [{"name": "Size", "terms": ["S", "M", "L"]}]
    html = cli.get(f"/store/p/{p['slug']}/").text
    assert "$30 – $45" in html and '<label>Size<select name="variacao">' in html
    assert carrinho.cotar(con, [_item(p["slug"], 1, "S")])["linhas"][0]["unitario"] == 30.0
    assert carrinho.cotar(con, [_item(p["slug"], 1, "L")])["linhas"][0]["erro"], "sem estoque não vende"


def test_foto_subida_vira_webp_sem_exif_e_aparece_no_site(painel):
    t, (cli, con, st, qbo, tmp, sid) = painel
    p = _um_simples(con)
    h = _entra(t, "ger@example.com")
    im = Image.new("RGB", (3000, 2000), (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "Fabricante do celular"                       # Make
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif)
    r = t.post(f"/ops/api/site/produtos/{p['id']}/fotos", headers=h, data={"alt": "Red gloves"},
               files={"arquivo": ("foto.jpg", buf.getvalue(), "image/jpeg")})
    assert r.status_code == 201, r.text
    foto = r.json()["produto"]["images"][-1]
    assert foto["src"].startswith("/store/img/") and foto["src"].endswith(".webp") and foto["alt"] == "Red gloves"
    servida = cli.get(foto["src"])
    assert servida.status_code == 200 and servida.headers["content-type"] == "image/webp"
    w = Image.open(io.BytesIO(servida.content))
    assert max(w.size) == 1600 and not w.getexif(), "≤ 1600 px e sem metadado"
    # a nova primeiro: vira a foto da loja
    fotos = [foto] + [i for i in r.json()["produto"]["images"] if i != foto]
    assert t.patch(f"/ops/api/site/produtos/{p['id']}", headers=h, json={"images": fotos}).status_code == 200
    assert f'src="{foto["src"]}"' in cli.get("/store/").text
    assert cli.get("/store/img/..%2F..%2Fcc.sqlite").status_code == 404


def test_categoria_antiga_do_woocommerce_aparece_marcada_pela_da_loja(painel):
    """O produto do WooCommerce em "apparel"/"suits" aparece na loja em Custom kart suits / Official URACE products;
    o painel mostra marcada a categoria da loja (e o filtro acha), e o "sem categoria" cai em Parts, como no site."""
    t, (cli, con, st, qbo, tmp, sid) = painel
    h = _entra(t, "op@example.com")
    assert t.get("/ops/api/site/produtos/235", headers=h).json()["produto"]["categorias_loja"] == ["official-urace-products", "custom-kart-suits"]
    assert t.get("/ops/api/site/produtos/3182", headers=h).json()["produto"]["categorias_loja"] == ["parts"]
    ids = [p["id"] for p in t.get("/ops/api/site/produtos?categoria=official-urace-products&limit=200", headers=h).json()["produtos"]]
    assert 235 in ids

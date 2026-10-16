"""#309 (dono, 16/10): *"todos os produtos que estão na loja … sejam editáveis … quantidade em estoque também, e fazer ele
no nosso estoque, na seção do site … não precisa ficar aparente essa parte … para os clientes, mas a gente seleciona o que
que é dropshipping e o que que a gente tem em estoque para poder enviar. Um marcador para isso lá, e o que tiver em estoque
a gente coloca quanto que tem em estoque."*

O que estes testes trancam:
- o marcador nasce `dropshipping` nos 70 produtos e nada muda no site; o cliente nunca vê o marcador nem a quantidade;
- em estoque com item ligado, quem diz se tem é o estoque (Galpão + Pista, só o que é da URACE): sem saldo, "Out of
  stock" na página, no cartão da loja e no JSON-LD, e a opção sem saldo fica desativada;
- ligar pede a contagem, e um item vende no site por um produto só;
- a venda paga (Buy now e carrinho) baixa o estoque uma vez só (webhook repetido + página de obrigado), `conferir()`
  continua batendo, e sem saldo o pagamento entra e vira "Resolver: sem estoque";
- a quantidade acima do que o box tem é recusada no checkout, com mensagem que não diz o número;
- o painel: só o gerente liga e muda o marcador, o operador conta; a lista é paginada no servidor.
"""
import html as html_
import json
import re

from command_center.db import inserir, todos, um
from command_center.providers import carrinho, estoque, loja as lj, painel_site, pedido_site
from command_center.providers.loja import ErroProduto
from command_center.tests.test_carrinho import _checkout, _entrar, _pagar, loja  # noqa: F401
from command_center.tests.test_loja_no_painel import _entra, _item, _um_simples, painel  # noqa: F401
from command_center.tests.test_stripe_loja import _comprar, _emails, amb  # noqa: F401
from command_center.tests.test_stripe_loja import _pagar as _pagar_buy_now

# o que o cliente lê quando pede mais do que o box tem: nunca o número
SEM_TANTO = "We don't have that many in stock right now. Please lower the quantity or send us an order request."


def _es():
    from command_center.providers import estoque_site
    return estoque_site


def _com_opcoes(con):
    return next(p for p in lj.catalogo(con) if p["in_stock"] and len(p["variations"]) >= 2
                and sum(1 for v in p["variations"] if v.get("price") and v.get("in_stock", True)) >= 2)


def _ld(html):
    return next(x for x in (json.loads(y) for y in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, 16))
                if x.get("@type") == "Product")


def _do_site(con, pid):
    return next(p for p in lj.catalogo(con) if p["id"] == pid)


def _ligar(con, p, qtd, variacao="", local="sede"):
    r = _es().ligar(con, None, p["id"], variacao, criar={"name": f"{p['name'][:40]} {variacao}".strip(), "category": "outros"},
                 contagem=qtd, local=local)
    con.commit()
    return r["item_id"]


def _sid(resp):
    return resp.headers["location"].rsplit("/", 1)[1]


# ------------------------------------------------------------------ 1. o marcador
def test_o_marcador_nasce_dropshipping_e_o_site_nao_muda(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    assert {r["fulfillment"] for r in todos(con, "SELECT fulfillment FROM store_products")} == {"dropshipping"}
    p = _um_simples(con)
    assert lj.do_painel(con, p["id"])["fulfillment"] == "dropshipping"
    assert all("fulfillment" not in x for x in lj.catalogo(con)), "o marcador nunca sai para o site"
    html = cli.get(f"/store/p/{p['slug']}/").text
    assert "Out of stock" not in html and _ld(html)["offers"]["availability"] == "https://schema.org/InStock"
    assert not carrinho.cotar(con, [_item(p["slug"], 20)])["linhas"][0]["erro"], "dropshipping não tem limite de quantidade"


def test_em_estoque_sem_saldo_fica_out_of_stock_na_pagina_no_cartao_e_no_json_ld(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    p = _um_simples(con)
    item = _ligar(con, p, 0)
    assert lj.do_painel(con, p["id"])["fulfillment"] == "estoque", "ligar marca o produto como em estoque"
    html = cli.get(f"/store/p/{p['slug']}/").text
    assert '<span class="chip-fora">Out of stock</span>' in html and "Buy now" not in html
    assert _ld(html)["offers"]["availability"] == "https://schema.org/OutOfStock"
    cartao = re.search(rf'<article class="produto-card"><a href="/store/p/{p["slug"]}/">.*?</article>', cli.get("/store/").text, 16)
    assert cartao and "<small>Out of stock</small>" in cartao.group(0)
    assert carrinho.cotar(con, [_item(p["slug"])])["linhas"][0]["erro"], "o carrinho não vende"
    # o box conta 2 no Galpão: volta a vender, sem ninguém mexer na caixa "Em estoque"
    estoque.contar(con, item, 2, onde="sede")
    con.commit()
    html = cli.get(f"/store/p/{p['slug']}/").text
    assert "Out of stock" not in html and "Buy now" in html
    assert _ld(html)["offers"]["availability"] == "https://schema.org/InStock"


def test_opcao_sem_saldo_fica_desativada(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    p = _com_opcoes(con)
    a, b = [" / ".join(v["attrs"]) for v in p["variations"][:2]]
    _ligar(con, p, 0, a)
    _ligar(con, p, 3, b)
    html = cli.get(f"/store/p/{p['slug']}/").text
    sel = re.search(r'<form class="form-pedido form-comprar".*?</form>', html, 16).group(0)
    a_, b_ = re.escape(html_.escape(a)), re.escape(html_.escape(b))
    assert re.search(rf'<option value="{a_}"[^>]* disabled>[^<]*\(out of stock\)', sel), "a opção sem saldo"
    assert not re.search(rf'<option value="{b_}"[^>]* disabled>', sel)
    assert carrinho.cotar(con, [_item(p["slug"], 1, a)])["linhas"][0]["erro"]
    assert not carrinho.cotar(con, [_item(p["slug"], 1, b)])["linhas"][0]["erro"]


def test_o_cliente_nunca_ve_o_marcador_nem_a_quantidade(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    p = _um_simples(con)
    _ligar(con, p, 7)
    for pagina in (cli.get(f"/store/p/{p['slug']}/").text, cli.get("/store/").text):
        assert not re.search(r"dropshipping|fulfillment|em estoque|in stock: 7|7 in stock", pagina, re.I)
    r = cli.post("/ops/api/vitrine/carrinho", json={"itens": [_item(p["slug"], 9)]})
    corpo = r.text
    assert "fulfillment" not in corpo and "dropshipping" not in corpo and '"estoque"' not in corpo
    erro = r.json()["linhas"][0]["erro"]
    assert erro == SEM_TANTO and "7" not in erro, "a mensagem não diz quanto tem"
    assert not cli.post("/ops/api/vitrine/carrinho", json={"itens": [_item(p["slug"], 7)]}).json()["linhas"][0]["erro"]
    # duas linhas do mesmo produto somam: 4 + 4 passa de 7
    d = cli.post("/ops/api/vitrine/carrinho", json={"itens": [_item(p["slug"], 4), _item(p["slug"], 4)]}).json()
    assert [x["erro"] for x in d["linhas"]] == [None, SEM_TANTO] and not d["ok"]


# ------------------------------------------------------------------ 2. ligar e contar
def test_ligar_pede_a_contagem_e_um_item_vende_por_um_produto_so(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    p = _um_simples(con)
    outro = next(x for x in lj.catalogo(con) if not x["variations"] and x["id"] != p["id"])
    it = estoque.criar_item(con, "peca", "Urace Kart Team Cap (e2e)", category="vestuario")
    try:
        _es().ligar(con, None, p["id"], "", item_id=it)
        raise AssertionError("ligou sem contar")
    except ErroProduto as e:
        assert "quanto tem agora" in str(e)
    assert not um(con, "SELECT 1 AS x FROM store_product_stock"), "recusado não liga"
    _es().ligar(con, None, p["id"], "", item_id=it, contagem="3", local="pista")
    assert estoque.vendavel(con, it) == 3.0
    m = um(con, "SELECT * FROM stock_moves WHERE item_id=? ORDER BY id DESC LIMIT 1", (it,))
    assert (m["kind"], m["source"], m["qty"]) == ("contagem", "site", 3.0)
    for kw, frase in (({"item_id": it, "contagem": 1}, "já vende no site"),                     # um item, um produto
                      ({"criar": {"kind": "motor"}, "contagem": 1}, "peça ou pneu"),
                      ({"criar": {"name": "Outro"}, "contagem": 1, "local": "trailer"}, "trailer")):
        try:
            _es().ligar(con, None, outro["id"], "", **kw)
            raise AssertionError(kw)
        except ErroProduto as e:
            assert frase in str(e), (kw, str(e))
    try:
        _es().ligar(con, None, p["id"], "", criar={"name": "Outro item"}, contagem=1)
        raise AssertionError("ligou duas vezes a mesma opção")
    except ErroProduto as e:
        assert "desligue antes" in str(e)


def test_peca_de_cliente_e_o_trailer_nao_contam_para_o_site(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    p = _um_simples(con)
    item = _ligar(con, p, 0)
    dono = inserir(con, "clients", name="Família Teste", email="familia.teste@example.com", status="ACTIVE", source="manual")
    estoque.entrada(con, item, qty=5, para="sede", client_id=dono, reason="guardado do cliente")
    estoque.entrada(con, item, qty=4, para="trailer")
    con.commit()
    assert not _do_site(con, p["id"])["in_stock"], "o que é do cliente e o que está no trailer não vendem no site"
    estoque.transferir(con, item, qty=1, de="trailer", para="pista")
    con.commit()
    assert _do_site(con, p["id"])["in_stock"] and lj.limites(con)[(p["slug"], "")] == 1


# ------------------------------------------------------------------ 3. a venda paga baixa o estoque
def test_buy_now_pago_baixa_o_estoque_uma_vez_so(amb):  # noqa: F811
    cli, con, st, qbo, tmp = amb
    p = _um_simples(con)
    item = _ligar(con, p, 5)
    s = _sid(_comprar(cli, p, quantidade="2"))
    assert _pagar_buy_now(cli, st, s, eid="evt_e1").json()["resultado"] == "pago"
    assert _pagar_buy_now(cli, st, s, eid="evt_e1").json()["resultado"] == "duplicado"
    assert _pagar_buy_now(cli, st, s, eid="evt_e2").json()["resultado"] == "pago"     # outro evento da mesma sessão
    assert cli.get(f"/store/thanks/?session_id={s}").status_code == 200                # e a página de obrigado
    assert estoque.vendavel(con, item) == 3.0, "saiu 2, uma vez só"
    vendas = todos(con, "SELECT * FROM stock_moves WHERE item_id=? AND kind='saida'", (item,))
    assert len(vendas) == 1 and (vendas[0]["reason"], vendas[0]["source"], vendas[0]["qty"]) == ("venda", "site", 2.0)
    o = um(con, "SELECT * FROM store_orders WHERE stripe_session_id=?", (s,))
    assert o["stock_move_id"] == vendas[0]["id"] and f"pedido #{o['id']}" in vendas[0]["notes"]
    assert o["attention"] is None and estoque.conferir(con) == [], "o razão continua batendo"


def test_carrinho_pago_baixa_o_estoque_envio_sai_primeiro_do_galpao(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    p = _um_simples(con)
    item = _ligar(con, p, 1, local="sede")
    estoque.contar(con, item, 2, onde="pista")
    con.commit()
    _entrar(cli, con)
    assert _checkout(cli, [_item(p["slug"], 2)], entrega="envio").status_code == 200
    s = next(reversed(st.sessoes))
    assert _pagar(cli, st, s).status_code == 200
    assert (estoque.vendavel(con, item, 1), estoque.vendavel(con, item, 3)) == (0.0, 1.0), "Galpão primeiro, depois a Pista"
    x = um(con, "SELECT * FROM store_order_items WHERE kind='produto' ORDER BY id")
    assert x["stock_move_id"] and x["stock_note"].startswith("baixou 2")
    assert estoque.conferir(con) == []
    # retirada: a Pista primeiro
    estoque.contar(con, item, 1, onde="sede")
    con.commit()
    assert _checkout(cli, [_item(p["slug"], 1)], entrega="retirada").status_code == 200
    _pagar(cli, st, next(reversed(st.sessoes)), eid="evt_c2")
    assert (estoque.vendavel(con, item, 1), estoque.vendavel(con, item, 3)) == (1.0, 0.0)


def test_sem_saldo_na_hora_de_pagar_o_pagamento_entra_e_vira_resolver(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    p = _um_simples(con)
    item = _ligar(con, p, 1)
    _entrar(cli, con)
    assert _checkout(cli, [_item(p["slug"], 1)]).status_code == 200
    estoque.saida(con, item, qty=1, de="sede", reason="venda", source="balcao")    # o Balcão vendeu a última antes
    con.commit()
    s = next(reversed(st.sessoes))
    assert _pagar(cli, st, s).json()["resultado"] == "pago"
    o = um(con, "SELECT * FROM store_orders WHERE stripe_session_id=?", (s,))
    assert o["status"] == "pago" and o["opp_id"], "o pagamento não cai"
    assert o["attention"] and o["attention"].startswith("sem estoque") and "pediu 1, tinha 0" in o["attention"]
    assert estoque.vendavel(con, item) == 0.0 and estoque.conferir(con) == [], "nunca negativo"
    assert pedido_site.lista(con)["pedidos"][0]["atencao"].startswith("sem estoque"), "Resolver: em Pedidos do site"
    assert painel_site.painel(con)["atencao"]["pedidos_sem_estoque"] == 1
    equipe = [m for m in _emails(tmp) if m["to"] == "support@urace.us"][-1]
    assert "SEM ESTOQUE" in equipe["subject"] and "SEM ESTOQUE" in equipe["text"]


def test_buy_now_sem_saldo_tambem_vira_resolver(amb):  # noqa: F811
    cli, con, st, qbo, tmp = amb
    p = _um_simples(con)
    item = _ligar(con, p, 2)
    s = _sid(_comprar(cli, p, quantidade="2"))
    estoque.contar(con, item, 1, onde="sede")                                      # alguém recontou: só tem 1
    con.commit()
    assert _pagar_buy_now(cli, st, s).json()["resultado"] == "pago"
    o = um(con, "SELECT * FROM store_orders WHERE stripe_session_id=?", (s,))
    assert o["status"] == "pago" and "pediu 2, tinha 1" in o["attention"] and "falta 1" in o["attention"]
    assert estoque.vendavel(con, item) == 0.0 and estoque.conferir(con) == []
    assert "SEM ESTOQUE" in [m for m in _emails(tmp) if m["to"] == "support@urace.us"][-1]["subject"]


def test_quantidade_acima_do_que_o_box_tem_e_recusada_no_checkout(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    p = _um_simples(con)
    _ligar(con, p, 2)
    _entrar(cli, con)
    r = cli.post("/ops/api/vitrine/checkout", data={"produto": p["slug"], "quantidade": "3", "entrega": "retirada"},
                 headers={"Accept": "application/json"})
    assert r.status_code == 400 and r.json()["erro"] == SEM_TANTO
    r = _checkout(cli, [_item(p["slug"], 3)])
    assert r.status_code == 400 and SEM_TANTO in r.text
    assert not st.chamadas, "o Stripe nem é chamado"
    r = cli.post("/ops/api/vitrine/checkout", data={"produto": p["slug"], "quantidade": "2", "entrega": "retirada"},
                 headers={"Accept": "application/json"})
    assert r.status_code == 200, r.text
    campos = st.chamadas[-1][2]
    assert campos["expires_at"], "a última unidade não fica presa um dia num checkout esquecido"


def test_kart_usado_com_numero_de_serie_vende_a_unidade(amb):  # noqa: F811
    cli, con, st, qbo, tmp = amb
    p = _um_simples(con)
    kart = estoque.criar_item(con, "chassi", "Kart usado (e2e)")
    estoque.entrada(con, kart, serial="SN-E2E-01", para="sede")
    _es().ligar(con, None, p["id"], "", item_id=kart)                                # série: as unidades são a contagem
    con.commit()
    assert _do_site(con, p["id"])["in_stock"]
    s = _sid(_comprar(cli, p))
    assert _pagar_buy_now(cli, st, s).json()["resultado"] == "pago"
    assert um(con, "SELECT status FROM stock_units WHERE item_id=?", (kart,))["status"] == "vendido"
    assert not _do_site(con, p["id"])["in_stock"], "a unidade única vendeu: Out of stock"


# ------------------------------------------------------------------ 4. o painel
def test_estoque_do_site_no_painel_gerente_liga_operador_conta(painel):  # noqa: F811
    t, (cli, con, st, qbo, tmp, sid) = painel
    p = _um_simples(con)
    h = _entra(t, "op@example.com")
    lista = t.get("/ops/api/site/estoque?limit=10", headers=h).json()
    assert (lista["total"], len(lista["produtos"]), lista["contagem"]["dropshipping"]) == (70, 10, 70), "paginado no servidor"
    assert [x["code"] for x in lista["locais"]] == ["sede", "pista"], "Galpão + Pista; o trailer fica fora"
    assert t.post(f"/ops/api/site/estoque/{p['id']}/ligar", headers=h, json={"criar": {}, "contagem": 1}).status_code == 403
    assert t.patch(f"/ops/api/site/produtos/{p['id']}", headers=h, json={"fulfillment": "estoque"}).status_code == 403
    hg = _entra(t, "ger@example.com")
    assert t.patch(f"/ops/api/site/produtos/{p['id']}", headers=hg, json={"fulfillment": "outro"}).status_code == 400
    assert t.patch(f"/ops/api/site/produtos/{p['id']}", headers=hg, json={"fulfillment": "estoque"}).status_code == 200
    sem = t.get("/ops/api/site/estoque?modo=sem_item", headers=hg).json()
    assert [x["id"] for x in sem["produtos"]] == [p["id"]], "em estoque sem item ligado"
    sug = t.get(f"/ops/api/site/estoque/itens?produto={p['id']}", headers=hg).json()
    assert "itens" in sug and "total" in sug
    r = t.post(f"/ops/api/site/estoque/{p['id']}/ligar", headers=hg, json={"criar": {"name": "Peça do site (e2e)"}})
    assert r.status_code == 400 and "quanto tem agora" in r.json()["detail"]
    r = t.post(f"/ops/api/site/estoque/{p['id']}/ligar", headers=hg, json={"criar": {"name": "Peça do site (e2e)"}, "contagem": "4"})
    assert r.status_code == 201, r.text
    aud = um(con, "SELECT * FROM audit_logs WHERE event='store.stock.link' ORDER BY id DESC LIMIT 1")
    assert aud and "Peça do site (e2e)" in aud["detail"]
    h = _entra(t, "op@example.com")
    r = t.post(f"/ops/api/site/estoque/{p['id']}/contar", headers=h, json={"qty": 6, "local": "pista"})
    assert r.status_code == 200 and (r.json()["antes"], r.json()["depois"]) == (0.0, 6.0), r.text
    linha = t.get("/ops/api/site/estoque?modo=estoque", headers=h).json()["produtos"][0]
    assert linha["tem"] == 10.0 and linha["opcoes"][0]["ligado"]["item"] == "Peça do site (e2e)"
    item = linha["opcoes"][0]["ligado"]["item_id"]
    ficha = t.get(f"/ops/api/estoque/{item}", headers=h).json()["item"]
    assert ficha["na_loja"] and ficha["na_loja"][0]["product_id"] == p["id"], "o Estoque do box mostra o produto do site"
    assert next(i for i in t.get("/ops/api/estoque", headers=h).json()["itens"] if i["id"] == item)["na_loja"]
    produto = t.get(f"/ops/api/site/produtos/{p['id']}", headers=h).json()["produto"]
    assert produto["estoque"]["tem"] == 10.0 and produto["estoque"]["no_site"] is True
    assert t.delete(f"/ops/api/site/estoque/{p['id']}/ligar", headers=h).status_code == 403
    hg = _entra(t, "ger@example.com")
    assert t.delete(f"/ops/api/site/estoque/{p['id']}/ligar", headers=hg).status_code == 200
    assert estoque.vendavel(con, item) == 10.0, "desligar não mexe no saldo nem apaga o item"
    assert um(con, "SELECT event FROM audit_logs WHERE event='store.stock.unlink'")

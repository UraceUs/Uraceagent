"""#309 · os achados da revisão do PR #320 (Estoque do site), um teste por achado. Cada um falha sem a correção.

Dinheiro e estoque: a opção sem item ligado com o produto desmarcado; ligar um item que já tem saldo (a tela mostrava a
soma e a pessoa digitava o total num local só); renomear a opção ligada; o saldo fracionado dividido entre locais; o
"Pagos sem estoque" que nunca zerava. Segurança e entrada: NaN na contagem, preço infinito e o carrinho anônimo que
revelava o saldo exato. Dados fictícios marcados (`@example.com`).
"""
from command_center.db import todos, transacao, um
from command_center.providers import carrinho, estoque, loja as lj, painel_site, pedido_site
from command_center.providers.loja import ErroProduto
from command_center.tests.test_carrinho import _checkout, _entrar, _pagar, loja  # noqa: F401
from command_center.tests.test_estoque_do_site import SEM_TANTO, _com_opcoes, _do_site, _es, _ligar, _sid
from command_center.tests.test_loja_no_painel import _entra, _item, _um_simples, painel  # noqa: F401
from command_center.tests.test_stripe_loja import _comprar, amb  # noqa: F401
from command_center.tests.test_stripe_loja import _pagar as _pagar_buy_now


def _nomes(p):
    return [" / ".join(v["attrs"]) for v in p["variations"]]


def _vars(p, nomes, antes=True):
    """As opções do produto como a tela manda ao salvar: os mesmos preços, os nomes novos e (com `antes`) o nome de
    quando a tela abriu."""
    out = []
    for v, nome in zip(p["variations"], nomes):
        x = {"attrs": [a.strip() for a in nome.split("/")], "regular": v["regular"], "in_stock": v.get("in_stock", True)}
        if v["price"] < v["regular"]:
            x["promo"] = v["price"]
        if antes:
            x["antes"] = " / ".join(v["attrs"])
        out.append(x)
    return out


def _ligacoes(con, pid):
    return {r["variation"]: r["item_id"] for r in todos(con, "SELECT variation, item_id FROM store_product_stock WHERE product_id=?",
                                                       (pid,))}


# ------------------------------------------------------------------ 1. a opção solta segue a caixa do produto
def test_opcao_sem_item_nao_vende_com_o_produto_desmarcado(loja):  # noqa: F811
    """Opção sem item ligado + produto com "Em estoque" desmarcado: não vende, mesmo com outra opção ligada com saldo."""
    cli, con, st, qbo, tmp, sid = loja
    p = _com_opcoes(con)
    a, b = _nomes(p)[:2]
    _ligar(con, p, 3, b)                                  # b ligada, com saldo; a sem item
    lj.mudar(con, None, p["id"], {"in_stock": False})     # a equipe desmarca "Em estoque" no produto
    con.commit()
    site = _do_site(con, p["id"])
    por_nome = {" / ".join(v["attrs"]): v for v in site["variations"]}
    assert por_nome[a]["in_stock"] is False, "a opção solta segue a caixa do produto"
    assert por_nome[b]["in_stock"] is True and site["in_stock"], "a ligada segue o estoque"
    assert carrinho.cotar(con, [_item(p["slug"], 1, a)])["linhas"][0]["erro"], "a opção solta não é comprável"
    assert not carrinho.cotar(con, [_item(p["slug"], 1, b)])["linhas"][0]["erro"]


# ------------------------------------------------------------------ 2. ligar um item que já tem saldo
def test_ligar_item_que_ja_tem_saldo_nao_pede_contagem_nem_infla(painel):  # noqa: F811
    """Galpão 5 + Pista 3: ligar sem contagem não mexe no saldo (era obrigatório, e a tela, que mostrava só a soma,
    levava a pessoa a digitar 8 no Galpão: 8 + 3 = 11). A API devolve o saldo de cada local."""
    t, (cli, con, st, qbo, tmp, sid) = painel
    p = _um_simples(con)
    it = estoque.criar_item(con, "peca", "Boné Teste Revisão (e2e)", category="vestuario")
    estoque.contar(con, it, 5, onde="sede")
    estoque.contar(con, it, 3, onde="pista")
    con.commit()
    contagens = um(con, "SELECT COUNT(*) AS n FROM stock_moves WHERE item_id=? AND kind='contagem'", (it,))["n"]
    hg = _entra(t, "ger@example.com")
    achados = t.get(f"/ops/api/site/estoque/itens?q=Bone Teste Revisao&produto={p['id']}", headers=hg).json()["itens"]
    x = next(i for i in achados if i["id"] == it)
    assert x["por_local"] == {"sede": 5.0, "pista": 3.0} and x["tem"] == 8.0 and x["contado"] is True
    r = t.post(f"/ops/api/site/estoque/{p['id']}/ligar", headers=hg, json={"item_id": it})
    assert r.status_code == 201, r.text
    assert estoque.vendavel(con, it) == 8.0, "ligar não infla o saldo"
    assert um(con, "SELECT COUNT(*) AS n FROM stock_moves WHERE item_id=? AND kind='contagem'", (it,))["n"] == contagens, \
        "sem contagem, ligar não conta"
    linha = next(x for x in t.get(f"/ops/api/site/estoque?q={p['slug']}", headers=hg).json()["produtos"] if x["id"] == p["id"])
    assert linha["opcoes"][0]["ligado"]["por_local"] == {"sede": 5.0, "pista": 3.0} and linha["tem"] == 8.0
    produto = t.get(f"/ops/api/site/produtos/{p['id']}", headers=hg).json()["produto"]
    assert produto["estoque"]["ligados"][""]["por_local"] == {"sede": 5.0, "pista": 3.0}
    # contar continua por local: 6 na Pista vira 5 + 6, nunca o total num local só
    r = t.post(f"/ops/api/site/estoque/{p['id']}/contar", headers=hg, json={"qty": 6, "local": "pista"})
    assert r.status_code == 200 and (r.json()["antes"], r.json()["depois"]) == (3.0, 6.0)
    assert estoque.vendavel(con, it) == 11.0 and estoque.conferir(con) == []


def test_ligar_item_sem_saldo_nem_contagem_ainda_pede_a_contagem(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    p = _um_simples(con)
    it = estoque.criar_item(con, "peca", "Peça Nunca Contada (e2e)", category="outros")
    try:
        _es().ligar(con, None, p["id"], "", item_id=it)
        raise AssertionError("ligou sem contar um item que nunca foi contado")
    except ErroProduto as e:
        assert "quanto tem agora" in str(e)


# ------------------------------------------------------------------ 3. renomear a opção ligada
def test_renomear_a_opcao_ligada_leva_a_ligacao_junto(painel):  # noqa: F811
    """A tela manda o nome de antes: a ligação vai para o nome novo e a opção continua vendendo só o que o box tem."""
    t, (cli, con, st, qbo, tmp, sid) = painel
    p = _com_opcoes(con)
    a, b = _nomes(p)[:2]
    item = _ligar(con, p, 2, a)
    novos = _nomes(p)
    novos[0] = a + " Plus"
    hg = _entra(t, "ger@example.com")
    r = t.patch(f"/ops/api/site/produtos/{p['id']}", headers=hg, json={"variations": _vars(p, novos)})
    assert r.status_code == 200, r.text
    assert _ligacoes(con, p["id"]) == {a + " Plus": item}, "a ligação foi junto com o nome"
    assert lj.limites(con)[(p["slug"], a + " Plus")] == 2
    assert carrinho.cotar(con, [_item(p["slug"], 3, a + " Plus")])["linhas"][0]["erro"] == SEM_TANTO, "não vende sem limite"
    aud = um(con, "SELECT detail FROM audit_logs WHERE event='store.product.update' ORDER BY id DESC LIMIT 1")
    assert "opcoes_no_estoque" in aud["detail"]


def test_renomear_sem_o_nome_de_antes_casa_pela_posicao_e_troca_de_nomes(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    p = _com_opcoes(con)
    a, b = _nomes(p)[:2]
    ia, ib = _ligar(con, p, 1, a), _ligar(con, p, 4, b)
    novos = _nomes(p)
    novos[0] = a + " X"
    with transacao(con):
        lj.mudar(con, None, p["id"], {"variations": _vars(p, novos, antes=False)})      # outro cliente da API
    assert _ligacoes(con, p["id"]) == {a + " X": ia, b: ib}
    # trocar os nomes de duas opções ligadas (a tela manda o nome de antes): cada ligação segue a sua opção
    p = lj.do_painel(con, p["id"])
    trocados = _nomes(p)
    trocados[0], trocados[1] = trocados[1], trocados[0]
    with transacao(con):
        lj.mudar(con, None, p["id"], {"variations": _vars(p, trocados)})
    assert _ligacoes(con, p["id"]) == {b: ia, a + " X": ib}


def test_renomear_sem_como_casar_e_recusado_e_nada_muda(painel):  # noqa: F811
    t, (cli, con, st, qbo, tmp, sid) = painel
    p = _com_opcoes(con)
    a, b = _nomes(p)[:2]
    _ligar(con, p, 1, a)
    _ligar(con, p, 1, b)
    antes = um(con, "SELECT variations FROM store_products WHERE id=?", (p["id"],))["variations"]
    # sem o nome de antes, duas opções ligadas somem e entram três novas: não dá para saber qual é qual
    vs = (_vars(p, [f"Novo {i}" for i in range(len(p["variations"]))], antes=False)
          + _vars(p, ["Novo extra"], antes=False))
    hg = _entra(t, "ger@example.com")
    r = t.patch(f"/ops/api/site/produtos/{p['id']}", headers=hg, json={"variations": vs})
    assert r.status_code == 400 and "ligada ao estoque" in r.json()["detail"], r.text
    assert um(con, "SELECT variations FROM store_products WHERE id=?", (p["id"],))["variations"] == antes, "nada mudou"
    assert set(_ligacoes(con, p["id"])) == {a, b}


# ------------------------------------------------------------------ 4. saldo fracionado dividido entre locais
def test_saldo_fracionado_nos_dois_locais_baixa_o_que_o_site_vendeu(amb):  # noqa: F811
    """0,5 no Galpão + 0,5 na Pista: o site vende 1 (a soma) e a baixa tira 0,5 de cada (arredondar por local tirava 0)."""
    cli, con, st, qbo, tmp = amb
    p = _um_simples(con)
    item = _ligar(con, p, "0.5", local="sede")
    estoque.contar(con, item, 0.5, onde="pista")
    con.commit()
    assert _do_site(con, p["id"])["in_stock"] and lj.limites(con)[(p["slug"], "")] == 1
    s = _sid(_comprar(cli, p))
    assert _pagar_buy_now(cli, st, s).json()["resultado"] == "pago"
    o = um(con, "SELECT * FROM store_orders WHERE stripe_session_id=?", (s,))
    assert o["attention"] is None and o["stock_note"].startswith("baixou 1"), o["stock_note"]
    assert estoque.vendavel(con, item) == 0.0, "a soma baixada bate com o vendido"
    vendas = todos(con, "SELECT qty FROM stock_moves WHERE item_id=? AND kind='saida' AND reason='venda'", (item,))
    assert sorted(v["qty"] for v in vendas) == [0.5, 0.5] and estoque.conferir(con) == []


# ------------------------------------------------------------------ 5. "Pagos sem estoque" zera com o Resolvido
def test_resolvido_tira_o_sem_estoque_do_pedido_e_do_painel(painel):  # noqa: F811
    t, (cli, con, st, qbo, tmp, sid) = painel
    p = _um_simples(con)
    item = _ligar(con, p, 1)
    _entrar(cli, con)
    assert _checkout(cli, [_item(p["slug"], 1)]).status_code == 200
    estoque.saida(con, item, qty=1, de="sede", reason="venda", source="balcao")     # o Balcão vendeu a última antes
    con.commit()
    s = next(reversed(st.sessoes))
    assert _pagar(cli, st, s).json()["resultado"] == "pago"
    o = um(con, "SELECT * FROM store_orders WHERE stripe_session_id=?", (s,))
    assert painel_site.painel(con)["atencao"]["pedidos_sem_estoque"] == 1
    linha = pedido_site.lista(con)["pedidos"][0]
    assert linha["sem_estoque"] is True and linha["atencao"].startswith("sem estoque")
    h = _entra(t, "op@example.com")                                                # o operador resolve
    r = t.post(f"/ops/api/site/pedidos/{o['id']}/estoque-resolvido", headers=h)
    assert r.status_code == 200, r.text
    assert painel_site.painel(con)["atencao"]["pedidos_sem_estoque"] == 0, "o contador zera"
    linha = pedido_site.lista(con)["pedidos"][0]
    assert linha["sem_estoque"] is False and linha["atencao"] is None, "sai do Resolver"
    x = um(con, "SELECT * FROM store_order_items WHERE order_id=? AND kind='produto'", (o["id"],))
    assert x["stock_resolved_at"] and x["stock_note"].startswith("sem estoque"), "a frase fica na linha"
    aud = um(con, "SELECT * FROM audit_logs WHERE event='store.stock.resolved' ORDER BY id DESC LIMIT 1")
    assert aud and str(aud["entity_id"]) == str(o["id"]) and "sem estoque" in aud["detail"]
    # o webhook repetido não traz o problema de volta, e resolver de novo diz que não há nada
    from command_center.providers import estoque_site
    assert estoque_site.baixar_do_pedido(con, o["id"]) == []
    assert t.post(f"/ops/api/site/pedidos/{o['id']}/estoque-resolvido", headers=h).status_code == 400


# ------------------------------------------------------------------ 6. NaN na contagem
def test_contagem_nan_e_infinita_e_recusada_com_400(painel):  # noqa: F811
    t, (cli, con, st, qbo, tmp, sid) = painel
    p = _um_simples(con)
    item = _ligar(con, p, 2)
    for v in ("nan", "NaN", "inf", "-inf"):
        try:
            _es()._qtd(v)
            raise AssertionError(v)
        except ErroProduto:
            pass
    h = _entra(t, "op@example.com")
    for v in ("nan", "inf"):
        r = t.post(f"/ops/api/site/estoque/{p['id']}/contar", headers=h, json={"qty": v})
        assert r.status_code == 400, (v, r.status_code, r.text)
        r = t.post("/ops/api/estoque/contar", headers=h, json={"item_id": item, "qty": v})   # a rota antiga do Estoque
        assert r.status_code == 400, (v, r.status_code, r.text)
    assert estoque.vendavel(con, item) == 2.0 and estoque.conferir(con) == []


# ------------------------------------------------------------------ 7. preço infinito
def test_preco_infinito_e_recusado_e_as_listas_continuam_de_pe(painel):  # noqa: F811
    t, (cli, con, st, qbo, tmp, sid) = painel
    p = _um_simples(con)
    for v in ("1e400", "inf", "nan"):
        try:
            estoque.criar_item(con, "peca", f"Peça Preço {v} (e2e)", price=v)
            raise AssertionError(v)
        except estoque.ErroEstoque as e:
            assert "número" in str(e)
    hg = _entra(t, "ger@example.com")
    r = t.post(f"/ops/api/site/estoque/{p['id']}/ligar", headers=hg,
               json={"criar": {"name": "Peça Infinita (e2e)", "price": "1e400"}, "contagem": 1})
    assert r.status_code == 400, r.text
    assert not um(con, "SELECT 1 AS x FROM stock_items WHERE name='Peça Infinita (e2e)'")
    assert t.get("/ops/api/estoque", headers=hg).status_code == 200
    assert t.get("/ops/api/site/estoque", headers=hg).status_code == 200


# ------------------------------------------------------------------ 8. o carrinho não revela o saldo
def test_carrinho_soma_as_linhas_e_responde_so_cabe_ou_nao_cabe(loja):  # noqa: F811
    """20 linhas de 1 com saldo 7: todas dizem a mesma frase (linha a linha, as 7 primeiras passavam e mostravam o
    número exato numa requisição só). Outro produto no mesmo carrinho não é afetado."""
    cli, con, st, qbo, tmp, sid = loja
    p = _um_simples(con)
    outro = next(x for x in lj.catalogo(con) if not x["variations"] and x["price"] and x["in_stock"] and x["id"] != p["id"])
    _ligar(con, p, 7)
    d = cli.post("/ops/api/vitrine/carrinho", json={"itens": [_item(p["slug"])] * 20}).json()
    erros = [x["erro"] for x in d["linhas"]]
    assert erros == [SEM_TANTO] * len(erros) and len(erros) >= 8 and not d["ok"], erros
    d = cli.post("/ops/api/vitrine/carrinho", json={"itens": [_item(p["slug"])] * 7 + [_item(outro["slug"], 3)]}).json()
    assert [x["erro"] for x in d["linhas"]] == [None] * 8 and d["ok"], "7 cabem"
    d = cli.post("/ops/api/vitrine/carrinho", json={"itens": [_item(p["slug"])] * 8 + [_item(outro["slug"], 3)]}).json()
    assert [x["erro"] for x in d["linhas"]] == [SEM_TANTO] * 8 + [None]


# ------------------------------------------------------------------ 10. dropshipping que ainda tem ligação
def test_item_preso_em_produto_dropshipping_diz_onde_esta_e_como_soltar(painel):  # noqa: F811
    """Passar a dropshipping deixa a ligação (o item continua no estoque). A lista do Ligar diz "dropshipping", a
    recusa diz para desligar lá, e a lista do Estoque do site continua mostrando a ligação (o Desligar da tela)."""
    t, (cli, con, st, qbo, tmp, sid) = painel
    p = _um_simples(con)
    outro = next(x for x in lj.catalogo(con) if not x["variations"] and x["price"] and x["id"] != p["id"])
    item = _ligar(con, p, 2)
    hg = _entra(t, "ger@example.com")
    assert t.patch(f"/ops/api/site/produtos/{p['id']}", headers=hg, json={"fulfillment": "dropshipping"}).status_code == 200
    linha = next(x for x in t.get("/ops/api/site/estoque?modo=dropshipping&limit=100", headers=hg).json()["produtos"]
                 if x["id"] == p["id"])
    assert linha["opcoes"][0]["ligado"]["item_id"] == item, "a ligação continua à vista no cartão dropshipping"
    nome = um(con, "SELECT name FROM stock_items WHERE id=?", (item,))["name"]
    achado = next(i for i in t.get(f"/ops/api/site/estoque/itens?q={nome}&produto={outro['id']}", headers=hg).json()["itens"]
                  if i["id"] == item)
    assert achado["ligado_fulfillment"] == "dropshipping" and achado["ligado_pid"] == p["id"]
    r = t.post(f"/ops/api/site/estoque/{outro['id']}/ligar", headers=hg, json={"item_id": item})
    assert r.status_code == 400 and "(dropshipping): desligue" in r.json()["detail"], r.text
    assert t.delete(f"/ops/api/site/estoque/{p['id']}/ligar", headers=hg).status_code == 200
    assert t.post(f"/ops/api/site/estoque/{outro['id']}/ligar", headers=hg, json={"item_id": item}).status_code == 201


def test_tirar_a_opcao_ligada_ou_dar_opcoes_ao_produto_ligado_e_recusado(painel):  # noqa: F811
    """A opção ligada que sai do produto, e o produto ligado inteiro que ganha opções, deixariam a ligação órfã (e o item
    preso: um item, um produto). Recusa com a frase do que fazer; desligado, salva."""
    t, (cli, con, st, qbo, tmp, sid) = painel
    p = _com_opcoes(con)
    a = _nomes(p)[0]
    _ligar(con, p, 2, a)
    hg = _entra(t, "ger@example.com")
    sem_a = _vars(p, _nomes(p))[1:]                                   # a tela tirou a opção ligada
    r = t.patch(f"/ops/api/site/produtos/{p['id']}", headers=hg, json={"variations": sem_a})
    assert r.status_code == 400 and "desligue" in r.json()["detail"] and a in r.json()["detail"], r.text
    assert _nomes(lj.do_painel(con, p["id"])) == _nomes(p), "nada mudou"
    assert t.delete(f"/ops/api/site/estoque/{p['id']}/ligar?variacao={a}", headers=hg).status_code == 200
    assert t.patch(f"/ops/api/site/produtos/{p['id']}", headers=hg, json={"variations": sem_a}).status_code == 200
    # o produto simples ligado inteiro ganha opções
    s = _um_simples(con)
    _ligar(con, s, 1)
    novas = [{"attrs": ["S"], "regular": s["regular"] or s["price"], "in_stock": True, "antes": None},
             {"attrs": ["M"], "regular": s["regular"] or s["price"], "in_stock": True, "antes": None}]
    r = t.patch(f"/ops/api/site/produtos/{s['id']}", headers=hg, json={"variations": novas, "attribute_names": ["Size"]})
    assert r.status_code == 400 and "produto inteiro" in r.json()["detail"], r.text
    assert not lj.do_painel(con, s["id"])["variations"] and _ligacoes(con, s["id"]) == {"": _ligacoes(con, s["id"])[""]}

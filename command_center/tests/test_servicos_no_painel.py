"""#297 (dono, 16/10, prioridade 1): *"aquele serviço que estão na página do Arrive and Drive em qualquer outra
página estejam e sejam possíveis de ser manipulados os que já estão lá ou se a gente quiser adicionar algum outro
lá pelo Command Center … a gente consiga alterar o valor, alterar o nome, alterar as coisas ali pelo Command
Center também"* e *"vou fazer uma compra com o valor de um dólar"*.

O que estes testes trancam, na página do Arrive and Drive:
- o cartão do kart (nome no site, linha de baixo, aviso, "o cliente traz o kart") sai do serviço do painel;
- os textos de hoje entram no painel **uma vez**, só onde o campo está vazio — nada é sobrescrito;
- um kart novo criado no painel aparece na página e vai para o carrinho com o preço e o depósito dele;
- o Lead and Follow mostra o nome e o texto do painel;
- o teste de US$ 1: preço 1 e depósito 0 fecham o checkout do Stripe em US$ 1,00, sem linha de depósito.
"""
import json
import re

import pytest

from command_center.db import aplicar_schema, um
from command_center.providers import carrinho, servicos_site as sv
from command_center.tests.test_agenda_sessoes import proximo
from command_center.tests.test_carrinho import _checkout, _entrar, _sessao, loja  # noqa: F401
from command_center.tests.test_stripe_loja import amb  # noqa: F401
from command_center.vitrine import conteudo as C


def _pagina(cli):
    r = cli.get(C.ARRIVE["caminho"])
    assert r.status_code == 200, r.text[:300]
    return r.text


def _cartao(html, chave):
    m = re.search(r'<label class="kart[^"]*"><input type="radio" name="kart" value="' + re.escape(chave) + r'".*?</label>', html, re.S)
    assert m, f"o kart {chave!r} não está na página"
    return m.group(0)


def _servico(con, chave):
    return um(con, "SELECT * FROM booking_services WHERE site_kart=?", (chave,))


def test_os_textos_de_hoje_entram_no_painel_uma_vez_e_nao_sao_sobrescritos(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    k4 = _servico(con, "4-stroke")
    assert (k4["site_title"], k4["site_subtitle"], k4["own_kart"]) == ("4-stroke", "Ages 7+", 0)
    proprio = _servico(con, "Own kart")
    assert proprio["own_kart"] == 1 and proprio["site_note"] == C.AVISO_KART_PROPRIO
    lf = um(con, "SELECT * FROM booking_services WHERE kind='addon'")
    assert lf["description"] == C.LEAD_AND_FOLLOW["texto"]
    # a equipe muda no painel; a subida seguinte não desfaz
    sv.mudar(con, None, k4["id"], {"site_title": "Rental 4T", "site_subtitle": "Ages 8+ · 30 min"})
    con.commit()
    aplicar_schema(con)
    k4 = _servico(con, "4-stroke")
    assert (k4["site_title"], k4["site_subtitle"]) == ("Rental 4T", "Ages 8+ · 30 min")


def test_o_cartao_do_kart_na_pagina_vem_do_painel(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    sv.mudar(con, None, sid, {"site_title": "Rental 4T", "site_subtitle": "Ages 8+ · 30 min",
                              "site_note": "Closed shoes, please."})
    con.commit()
    html = _pagina(cli)
    cartao = _cartao(html, "4-stroke")
    assert 'data-kart="4-stroke"' in cartao, "a chave do kart não muda: carrinho e reserva continuam casando"
    assert '<span class="kart-nome">Rental 4T</span>' in cartao
    assert '<span class="kart-idade">Ages 8+ · 30 min</span>' in cartao
    assert '<span class="kart-aviso">Closed shoes, please.</span>' in cartao
    assert 'data-titulo="Rental 4T"' in cartao, "o resumo da reserva usa o nome do painel"
    ofertas = [o["name"] for x in _ld(html) if x.get("@type") == "Service" for o in x["offers"]]
    assert "Rental 4T" in ofertas, "o Google também vê o nome do painel"
    # vazio volta ao de sempre
    sv.mudar(con, None, sid, {"site_title": "", "site_subtitle": "", "site_note": ""})
    con.commit()
    cartao = _cartao(_pagina(cli), "4-stroke")
    assert '<span class="kart-nome">4-stroke</span>' in cartao and '<span class="kart-idade">Ages 7+</span>' in cartao


def test_kart_novo_criado_no_painel_aparece_na_pagina_e_vai_ao_carrinho(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    novo = sv.criar(con, None, {"name": "Arrive and Drive Rental 2T Pro", "price": "950", "deposit": "300",
                                "site_kart": "Rental 2-stroke Pro", "site_title": "2-stroke Pro",
                                "site_subtitle": "Ages 15+ · racing kart", "kind": "session"})
    con.commit()
    cartao = _cartao(_pagina(cli), "Rental 2-stroke Pro")
    assert 'data-preco="950"' in cartao and "$950" in cartao and "2-stroke Pro" in cartao
    linha = carrinho.cotar(con, [_sessao(novo, proximo(5))])["linhas"][0]
    assert (linha["unitario"], linha["deposito"]) == (950.0, 300.0)
    # o cliente traz o kart: o cartão ganha o aviso e a marca do kart próprio
    sv.mudar(con, None, novo, {"own_kart": True, "site_note": "Ship your kart 2 days before."})
    con.commit()
    cartao = _cartao(_pagina(cli), "Rental 2-stroke Pro")
    assert 'class="kart kart-proprio"' in cartao and 'data-proprio="1"' in cartao and "Ship your kart" in cartao
    # desativado, sai da página
    sv.mudar(con, None, novo, {"active": False})
    con.commit()
    assert 'value="Rental 2-stroke Pro"' not in _pagina(cli)


@pytest.mark.parametrize("chave", ["<script>", "x", "a" * 41, "kart;drop"])
def test_chave_de_kart_novo_estranha_e_recusada(loja, chave):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    with pytest.raises(sv.ErroServico):
        sv.criar(con, None, {"name": "Kart estranho", "price": "100", "site_kart": chave})


def test_o_lead_and_follow_mostra_o_nome_e_o_texto_do_painel(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    lf = um(con, "SELECT id FROM booking_services WHERE kind='addon'")["id"]
    sv.mudar(con, None, lf, {"site_title": "Coach on track", "description": "A pro coach beside you all day."})
    con.commit()
    html = _pagina(cli)
    assert "<strong>Add Coach on track</strong> · A pro coach beside you all day." in html


def test_o_teste_de_um_dolar_fecha_o_checkout_do_stripe_em_um_dolar(loja):  # noqa: F811
    """Dono, 16/10: *"vou fazer uma compra com o valor de um dólar"*: preço 1 e depósito 0 no painel."""
    cli, con, st, qbo, tmp, sid = loja
    sv.mudar(con, None, sid, {"price": "1", "deposit": "0"})
    con.commit()
    assert "$1" in _cartao(_pagina(cli), "4-stroke")
    conta, pid = _entrar(cli, con)
    r = _checkout(cli, [_sessao(sid, proximo(5), pid)])
    assert r.status_code == 200, r.text
    sessao = st.sessoes[next(iter(st.sessoes))]
    assert sessao["amount_total"] == 100, "US$ 1,00 no Stripe"
    campos = next(c for m, cam, c, _i in st.chamadas if m == "POST" and cam == "/v1/checkout/sessions")
    nomes = [i["price_data"]["product_data"]["name"] for i in campos["line_items"]]
    assert not [n for n in nomes if "deposit" in n.lower()], ("depósito 0 não vira linha no Stripe", nomes)


def _ld(html):
    return [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


# ------------------------------------------------------------------ parte 2: os cartões das outras páginas
from command_center.providers import cartoes_site as cs  # noqa: E402


def _cartao_de(con, pagina, titulo):
    return um(con, "SELECT * FROM site_offers WHERE page=? AND title=?", (pagina, titulo))


def test_os_cartoes_de_hoje_entram_uma_vez_e_nao_sao_sobrescritos(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    contagem = {r["page"]: r["n"] for r in con.execute("SELECT page, COUNT(*) AS n FROM site_offers GROUP BY page")}
    assert contagem == {"academy": 8, "pro-team": 2, "for-beginners": 3}, contagem
    c = _cartao_de(con, "academy", "6-month contract")
    cs.mudar(con, None, c["id"], {"price": "$9,999.00", "active": False})
    con.commit()
    aplicar_schema(con)
    aplicar_schema(con)
    assert con.execute("SELECT COUNT(*) FROM site_offers").fetchone()[0] == 13, "nada é recriado"
    c = um(con, "SELECT * FROM site_offers WHERE id=?", (c["id"],))
    assert (c["price"], c["active"]) == ("$9,999.00", 0), "o que a equipe mudou fica"


def test_a_academy_mostra_os_cartoes_do_painel(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    html = cli.get("/academy/").text
    assert "$2,756" in html and "No contract" in html, "o texto de hoje, agora do painel"
    c = _cartao_de(con, "academy", "No contract")
    cs.mudar(con, None, c["id"], {"title": "Monthly, no contract", "price": "$2,500", "body": "Cancel any time."})
    outro = _cartao_de(con, "academy", "12-month contract")
    cs.mudar(con, None, outro["id"], {"active": False})
    con.commit()
    html = cli.get("/academy/").text
    assert "Monthly, no contract" in html and "$2,500" in html and "Cancel any time." in html
    assert html.count("<h3>12-month contract</h3>") == 1, "escondido: sai de um grupo, o outro grupo continua com o seu"
    ofertas = [o for x in _ld(html) if x.get("@type") == "Service" for o in x.get("offers", [])]
    assert any(o["price"] == "2500.00" for o in ofertas), "o Google vê o preço do painel"


def test_cartao_novo_aparece_e_o_preco_do_kart_e_o_do_painel_ao_vivo(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    cs.criar(con, None, {"page": "for-beginners", "title": "Sim 2 Grid", "subtitle": "Start in the simulator.",
                         "price": "{kart}", "per": "Starting at", "link": "/services/", "button": "See the sim"})
    sv.mudar(con, None, sid, {"price": "650"})              # o 4-stroke fica o kart mais barato
    con.commit()
    html = cli.get("/for-beginners/").text
    assert "Sim 2 Grid" in html and "See the sim" in html
    assert html.count("<span>Starting at</span><strong>$650</strong>") == 2, "o Arrive & Drive e o novo, com o preço do painel"
    assert "Starting at $650" in cli.get("/services/").text, "o hub também"
    assert "$650 per racing participant" in cli.get("/services/birthday-party/").text, "e o Investment dos eventos"
    assert "$719" not in cli.get("/services/birthday-party/").text


@pytest.mark.parametrize("link", ["javascript:alert(1)", "data:text/html,x", "http://site.com", "/x\"><script>"])
def test_link_do_cartao_so_do_site_ou_https(loja, link):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    with pytest.raises(cs.ErroCartao):
        cs.criar(con, None, {"page": "academy", "title": "Plano", "link": link})


def test_pagina_sem_cartao_ativo_volta_ao_texto_de_sempre(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    con.execute("UPDATE site_offers SET active=0 WHERE page='pro-team'")
    con.commit()
    html = cli.get("/pro-team/").text
    assert "Race Weekend Support" in html, "a página não fica vazia: cai no texto de conteudo_paginas"

"""#279 (dono, 15/10, Bloco 1): Lead and Follow como add-on da reserva, kart próprio como 5ª opção e a taxa
de convidado.

- *"Lead and Follow ($769) entra no carrinho como add-on na reserva do Arrive and Drive?"* → sim.
- *"sim como a 5 opção e coloque um warning que o kart precisa ser enviado com no mínimo 2 dias de
  antecedência para ser checado e feito a manutenção necessária."*
- Convidado: *"diga que varia entre 15 a 22 e é cobrado diretamente pela pista"*.
"""
import re

from command_center.db import aplicar_schema, todos, um
from command_center.providers import carrinho, servicos_site
from command_center.tests.test_agenda_sessoes import proximo
from command_center.tests.test_carrinho import _checkout, _entrar, _pagar, _sessao, loja  # noqa: F401
from command_center.tests.test_stripe_loja import amb  # noqa: F401
from command_center.vitrine import conteudo as C


def _lf(con):
    return um(con, "SELECT * FROM booking_services WHERE kind='addon' AND site_kart='Lead and Follow'")


# --------------------------------------------------------------- o add-on nasce no painel, sem ninguém cadastrar
def test_o_lead_and_follow_nasce_no_painel_com_o_preco_da_planilha_e_nao_e_sobrescrito(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    a = _lf(con)
    assert a and a["price"] == 769.0 and a["active"] == 1 and (a["deposit"] or 0) == 0
    # o gerente muda o preço: a subida seguinte não desfaz e não cria outra linha
    con.execute("UPDATE booking_services SET price=800 WHERE id=?", (a["id"],))
    aplicar_schema(con)
    aplicar_schema(con)
    assert _lf(con)["price"] == 800.0
    assert len(todos(con, "SELECT id FROM booking_services WHERE kind='addon'")) == 1
    # o add-on não vira kart: não entra na lista de sessões que a agenda usa
    assert all(s["site_kart"] != "Lead and Follow" for s in servicos_site.para_cliente(con))


def test_a_api_do_site_entrega_o_add_on_com_o_preco_do_painel(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    lf = cli.get("/ops/api/vitrine/servicos").json()["lead_follow"]
    assert lf["price"] == 769.0 and lf["name"] == "Lead and Follow"
    con.execute("UPDATE booking_services SET active=0 WHERE kind='addon'")
    con.commit()
    assert cli.get("/ops/api/vitrine/servicos").json()["lead_follow"] is None, "desativado: a caixa some"


# --------------------------------------------------------------- o carrinho
def test_sessao_com_lead_and_follow_vira_duas_linhas_e_o_preco_e_do_servidor(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    dia = proximo(5)
    c = carrinho.cotar(con, [_sessao(sid, dia, lead_follow=True, preco_lf=1)])
    sessao, lf = c["linhas"]
    assert (sessao["tipo"], lf["tipo"]) == ("sessao", "addon")
    assert lf["unitario"] == 769.0 and lf["idx"] == sessao["idx"] and lf["data"] == dia.isoformat()
    assert c["subtotal"] == 719.0 + 769.0 and c["deposito"] == 400.0
    # sem pedir, não entra; pedido só com "true" de verdade (nada de string do navegador)
    assert len(carrinho.cotar(con, [_sessao(sid, dia)])["linhas"]) == 1
    assert len(carrinho.cotar(con, [_sessao(sid, dia, lead_follow="1")])["linhas"]) == 1


def test_add_on_que_o_painel_nao_vende_mais_trava_o_checkout_com_aviso(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    con.execute("UPDATE booking_services SET active=0 WHERE kind='addon'")
    c = carrinho.cotar(con, [_sessao(sid, proximo(5), lead_follow=True)])
    assert c["linhas"][1]["erro"] and "Lead and Follow" in c["linhas"][1]["erro"]
    assert not c["ok"]


def test_pago_o_lead_and_follow_entra_na_sessao_marcada_e_no_stripe(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    conta, pid = _entrar(cli, con)
    lf_id = _lf(con)["id"]
    servicos_site.mudar(con, None, lf_id, {"qbo_item": "Arrive and Drive 4T"})   # a equipe aponta o item
    con.commit()
    r = _checkout(cli, [_sessao(sid, proximo(5), pid, lead_follow=True)])
    assert r.status_code == 200, r.text
    sid_stripe = next(iter(st.sessoes))
    campos = next(c for m, cam, c, _i in st.chamadas if m == "POST" and cam == "/v1/checkout/sessions")
    nomes = [i["price_data"]["product_data"]["name"] for i in campos["line_items"]]
    assert any(n.startswith("Lead and Follow") for n in nomes), ("o cliente vê o add-on no Stripe", nomes)
    assert st.sessoes[sid_stripe]["amount_total"] == (719 + 400 + 769) * 100
    assert _pagar(cli, st, sid_stripe).json()["resultado"] == "pago"
    b = um(con, "SELECT * FROM bookings")
    assert "Lead and Follow" in b["notes"] and "769.00" in b["notes"], "a equipe vê na sessão que o dia tem coach na pista"
    assert len(todos(con, "SELECT id FROM bookings")) == 1, "o add-on não vira uma segunda sessão"
    # a tabela das linhas só aceita produto ou sessão: o add-on vai NA linha da sessão (sem reconstruir tabela)
    (linha,) = todos(con, "SELECT * FROM store_order_items")
    assert (linha["kind"], linha["variation"], linha["product_slug"]) == ("sessao", "Lead and Follow", f"addon:{lf_id}")
    assert linha["amount"] == 719 + 400 + 769 and linha["name"].endswith("+ Lead and Follow")
    opp = um(con, "SELECT * FROM opportunities")
    assert opp["amount"] == 719 + 400 + 769 and "Lead and Follow" in opp["service"]
    # QuickBooks: o recibo tem o add-on como linha própria, com o item que a equipe apontou
    (recibo,) = qbo.recibos
    assert ("11", 769.0) in [(x["item_id"], x["unitario"]) for x in recibo["linhas"]]


# --------------------------------------------------------------- o kart próprio
def test_kart_proprio_e_a_quinta_opcao_com_o_aviso_dos_dois_dias(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    k = C.kart_da_chave("Own kart")
    assert k["preco"] == 500 and k["min"] == 4 and k.get("proprio")
    assert "at least 2 days before your session" in C.AVISO_KART_PROPRIO
    s = um(con, "SELECT * FROM booking_services WHERE site_kart='Own kart'")
    assert (s["price"], s["deposit"], s["kind"]) == (500.0, 0.0, "session"), "sem depósito: o kart é do cliente"
    html = cli.get("/services/arrive-and-drive/").text
    assert 'data-kart="Own kart" data-preco="500" data-proprio="1"' in html
    assert C.AVISO_KART_PROPRIO in html
    linha = carrinho.cotar(con, [_sessao(s["id"], proximo(5))])["linhas"][0]
    assert linha["aviso"] == C.AVISO_KART_PROPRIO, "o aviso vai junto para o carrinho"
    # o "a partir de" do site continua sendo o aluguel do kart da URACE
    assert C.preco_minimo() == 719


def test_a_pagina_oferece_o_lead_and_follow_com_o_preco_do_painel(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    html = cli.get("/services/arrive-and-drive/").text
    assert re.search(r'class="agenda-lf addon"><input type="checkbox" name="lead_follow"', html)
    assert "+$769" in html


# --------------------------------------------------------------- o convidado
def test_convidado_varia_de_15_a_22_e_e_cobrado_pela_pista(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    for caminho in ("/services/arrive-and-drive/", "/career/"):
        texto = re.sub(r"<[^>]+>", " ", cli.get(caminho).text)
        assert "Extra guests must pay $15 each" not in texto, caminho
        assert "Spectator pass any day $22" not in texto and "spectator pass any day $22" not in texto, caminho
    texto = re.sub(r"<[^>]+>", " ", cli.get("/services/arrive-and-drive/").text)
    assert "$15 to $22" in texto or "$15–22" in texto
    assert "charged directly by the track" in texto

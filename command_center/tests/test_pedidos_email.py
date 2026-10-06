"""Pedidos pelo e-mail, do jeito que eles chegam de verdade no urace@ (dono, 06/10).

"Chegou qualquer atualização com aquele mesmo número de pedido […] chegou uma fatura daquele
pedido. Ah, está pendente o pagamento […] vai chegar também, provavelmente, por link, aí tem
que abrir o link […] não ter necessidade de inserção manual."

Os formatos abaixo são os que a caixa mostrou na primeira semana (KartSport/Shopify,
ShipStation, UPS, FedEx, Alibaba, QuickBooks de fornecedor) — com números trocados.
"""
import hashlib
import json
import os
import socket

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from command_center.db import aplicar_schema, conectar, inserir, todos, um  # noqa: E402
from command_center.providers import compras, compras_email as ce, pagina  # noqa: E402


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def msg(assunto, corpo="", de="Loja <orders@loja.com>", data="Mon, 28 Sep 2026 10:00:00 -0400", snippet="", links=None,
        marcadores=None, mid=None):
    msg.n = getattr(msg, "n", 0) + 1
    return {"message_id": mid or f"p{msg.n}", "de": de, "assunto": assunto, "corpo": corpo, "snippet": snippet,
            "data": data, "marcadores": marcadores or ["INBOX"], "links": links or []}


def aplica(con, m, thread=None):
    info = ce.ler(m)
    assert info, f"deveria ser compra: {m['assunto']}"
    return ce.aplicar(con, info, "urace", thread or m["message_id"], m["message_id"])


KS = "Kartsport North America <store+22505245@t.shopifyemail.com>"
SS = "Vantage Karting Group <tracking@shipstation.com>"
UPS = "UPS <mcinfo@ups.com>"
QB = "QuickBooks <quickbooks@notification.intuit.com>"
T1 = "1ZK102480399990001"


# ------------------------------------------------------------------ o que NÃO é compra
@pytest.mark.parametrize("m", [
    msg("Reminder: Your recurring payment to  NATALIE ROMANI will occur tomorrow", "Amount $400",
        de="Bank of America <onlinebanking@ealerts.bankofamerica.com>"),
    msg("Your Refund Receipt - OYO Hotel Orlando Airport (Itinerary #72079874052335)", "", de='"Hotels.com" <hotels@eg.hotels.com>'),
    msg("Recibo de compra", "Total $310", de="Copa Airlines <noreply@css.copaair.com>"),
    msg("Receipt from FLORIDA KARTING CHAMPIONSHIP LLC #LrRn", "Total $150.00",
        de="FLORIDA KARTING CHAMPIONSHIP LLC <messenger@messaging.squareup.com>"),
    msg("Zelle® payment of $717.00 to NATALIE ROMANI has been sent", "", de="Bank <x@bankmail.com>"),
    msg("Payment received: Invoice #URACE-0017-(Joseph Kurian)", "Paid to URACE", de=QB),
    msg("Money on the way!", "Deposit ID 2448562523", de="BusinessServices@intuit.com"),
    msg("Woohoo! You got paid.", "Michael paid you", de=QB),
    msg("New payment request from Orlando Kart Center - invoice 1075", "BALANCE DUE$2700.00", de=QB),
    msg("Your payment to Uber Technologies, I... has been processed", "", de="service@paypal.com"),
    msg("Your next payment is due October 1", "Minimum payment $7400.00", de="support@square.peach.finance"),
])
def test_banco_viagem_venda_nossa_e_corrida_nao_viram_compra(m):
    assert ce.ler(m) is None


# ------------------------------------------------------------------ leitura fina
def test_css_do_email_nao_vira_numero_de_pedido_e_fedex_tem_rastreio_no_assunto(con):
    a = msg("Your shipment is on the way 538060779646", "border: 2px solid; Your shipment from WalMart.com is on the way.\n"
            "Estimated delivery date Tue, 09/29/2026", de="FedEx Delivery Manager <TrackingUpdates@fedex.com>")
    b = msg("Part of your shipment is scheduled for delivery tomorrow 877820098885",
            "order: 2px; Part of your shipment from SHENYANG SUNSHINE ADVERT CO., LTD. is scheduled for delivery tomorrow",
            de="FedEx Delivery Manager <TrackingUpdates@fedex.com>")
    ia, ib = ce.ler(a), ce.ler(b)
    assert ia["order_number"] is None and ib["order_number"] is None, "'order: 2px' é CSS"
    assert ia["tracking"] == ["538060779646"] and ia["carrier"] == "FedEx" and ia["supplier_hint"] == "Walmart"
    assert ib["supplier_hint"].startswith("SHENYANG SUNSHINE") and ib["stage"] == "previsao"
    pa, _ = aplica(con, a)
    pb, _ = aplica(con, b)
    assert pa != pb, "duas caixas de lojas diferentes não são a mesma compra"
    assert compras.compra(con, pa)["supplier"] == "Walmart"


def test_rastreio_que_so_aparece_no_resumo_do_gmail(con):
    """O corpo do aviso da UPS é CSS até o corte; o resumo do Gmail tem o código."""
    m = msg("Your UPS Package was delivered", "x" * 50, de=UPS,
            snippet="UPS Hi Italo, Your package was delivered. From KART SPORT Delivered Thursday 10/01/2026 12:10 PM "
                    f"Track Your Package › UPS Ground {T1}")
    info = ce.ler(m)
    assert info["tracking"] == [T1] and info["kind"] == "entregue" and info["supplier_hint"] == "KartSport North America"


def test_etapas_finas_pelo_assunto():
    assert ce.estagio("envio", "Your order is out for delivery") == "saiu_para_entrega"
    assert ce.estagio("envio", "UPS Update: Package Scheduled for Delivery Tomorrow") == "previsao"
    assert ce.estagio("envio", "Delivery exception: weather delay") == "atraso"
    assert ce.estagio("envio", 'Shipped: "Chain"') == "em_transito"
    assert ce.estagio("pedido", "Order #47863 in final stages of processing") == "preparando"
    assert ce.estagio("pedido", "Re: Order #47838 confirmed", '"info" <info@kartsportnorthamerica.com>') == "mensagem"
    assert ce.estagio("pedido", "Your order is waiting for payment (317394842001022128)") == "pagamento_pendente"
    assert ce.tipo("【Action Required】Your Trade Assurance Order No. 317394842001022128 is awaiting initial payment")[0] == "pedido"
    assert ce.tipo("Your initial payment has been received (317394842001022128)")[0] == "pagamento"
    assert ce.tipo("Invoice #INV-116671 — payment link enclosed")[0] == "pedido"


def test_numeros():
    assert ce.numero_do_pedido("Your order is on its way (316625486001022128)") == "316625486001022128"
    assert ce.numero_do_pedido("[No-reply]A shipment from order PM5183429 has been delivered") == "PM5183429"
    assert ce.numero_do_pedido("td { border: 2px } Order #47863 confirmed") == "47863", "'border' não é 'order'"
    assert ce.numero_da_fatura("Invoice #INV-116671 — payment link enclosed") == "INV-116671"
    assert ce.numero_da_fatura("Payment confirmation: Invoice #1678-(Courtney Concepts Karting)") == "1678"
    assert ce.numero_da_fatura("invoice 1398 has not been paid") == "1398"
    assert ce.total("BALANCE DUE$427.22 0% APR") == 427.22
    assert ce.total("Amount Paid USD 31.48") == 31.48
    assert ce.canonico("Vantage Karting Group") == ce.canonico("KART SPORT") == ce.canonico("Kartsport North America")


def test_rastreio_tirado_do_link_sem_abrir_a_pagina():
    url = ("http://trackshipment.shipstation.com/?branding_id=0010b963&carrier_code=ups&tracking_number=1ZK102480315679926"
           "&order_number=U08tODgwNTAsICMx&postal_code=32210&locale=en")
    assert ce.rastreios_do_link(url) == [("1ZK102480315679926", "UPS")]
    assert ce.rastreios_do_link("https://www.fedex.com/fedextrack/?trknbr=538060779646") == [("538060779646", "FedEx")]
    assert ce.rastreios_do_link("https://t.17track.net/en#nums=YT2639521437087837") == [("YT2639521437087837", None)]
    assert ce.rastreios_do_link("https://www.kartsportna.com/") == []


# ------------------------------------------------------------------ a mesma compra do pedido à entrega
def test_kartsport_do_pedido_a_entrega_sem_duplicar(con):
    """O caso real de 28/09–01/10: pedido no Shopify, envio pelo ShipStation (outro número),
    avisos da UPS sem número nenhum — tudo numa compra só, em ordem de chegada."""
    p, criada = aplica(con, msg("Order #47843 confirmed", "Thank you for your purchase! Order #47843\nTotal $4,234.92 USD",
                                de=KS, data="Mon, 28 Sep 2026 16:06:19 -0400"))
    assert criada
    aplica(con, msg("Re: Order #47843 confirmed", "Can you ship to Jacksonville?", de='"info" <info@kartsportnorthamerica.com>',
                    data="Tue, 29 Sep 2026 09:14:33 -0400"), "conversa")
    # o armazém avisa ANTES do Shopify contar o rastreio: nasce uma casca só com a referência SO-
    link = (f"http://trackshipment.shipstation.com/?carrier_code=ups&tracking_number={T1}&order_number=U08t")
    so, criada_so = aplica(con, msg("Your order has been shipped!", "Thank you for your order from Vantage Karting Group! "
                                    "your order (#SO-88050, #1) was shipped via UPS", de=SS, data="Tue, 29 Sep 2026 18:21:08 -0400",
                                    links=[{"texto": T1, "url": link}]))
    assert criada_so and so != p
    assert compras.compra(con, so)["reference"] == "SO-88050" and compras.compra(con, so)["order_number"] is None
    # o Shopify diz o rastreio do pedido #47843: a casca do armazém é a mesma compra
    aplica(con, msg("Order #47843 in final stages of processing", f"Order #47843 UPS tracking number: {T1}", de=KS,
                    data="Tue, 29 Sep 2026 18:25:22 -0400"))
    assert um(con, "SELECT 1 AS x FROM purchase_orders WHERE id=?", (so,)) is None, "a casca foi juntada"
    for txt, d in (("UPS Update: Package Scheduled for Delivery Tomorrow", "Wed, 30 Sep 2026 14:57:43 -0400"),
                   ("Your UPS Package was delivered", "Thu, 01 Oct 2026 12:14:37 -0400")):
        aplica(con, msg(txt, f"From KART SPORT Delivered Thursday UPS Ground {T1}", de=UPS, data=d))
    aplica(con, msg("Your order has been delivered!", "your order (#SO-88050, #1) was delivered via UPS", de=SS,
                    data="Thu, 01 Oct 2026 12:13:07 -0400", links=[{"texto": T1, "url": link}]))
    assert um(con, "SELECT COUNT(*) AS n FROM purchase_orders")["n"] == 1
    c = compras.compra(con, p)
    assert (c["supplier"], c["order_number"], c["tracking"], c["ship_status"]) == ("KartSport North America", "47843", T1, "entregue")
    assert c["reference"] == "47843" and c["email_total"] == 4234.92 and c["order_url"] == link
    etapas = [(e["kind"], e["stage"]) for e in c["eventos"]]
    assert etapas[:4] == [("pedido", None), ("pedido", "mensagem"), ("envio", "em_transito"), ("pedido", "preparando")]
    assert ("entregue", None) in etapas and len(etapas) == 7


def test_mensagem_da_loja_nao_mexe_na_entrega(con):
    p, _ = aplica(con, msg("Your order has shipped", f"Order #5531 Tracking number: {T1}", de="Comet <orders@cometkartsales.com>"))
    aplica(con, msg("Re: Your order has shipped", "Order #5531 — sorry, the order will be cancelled if you don't answer",
                    de="Rick <rick@cometkartsales.com>"))
    assert compras.compra(con, p)["ship_status"] == "enviado"


def test_duas_encomendas_na_mesma_caixa(con):
    a, _ = aplica(con, msg("Order #47838 in final stages of processing", f"Order #47838 tracking number: {T1}", de=KS))
    b, _ = aplica(con, msg("Order #47863 in final stages of processing", f"Order #47863 tracking number: {T1}", de=KS))
    assert a != b
    aplica(con, msg("Your UPS Package was delivered", f"UPS Ground {T1}", de=UPS))
    ca, cb = compras.compra(con, a), compras.compra(con, b)
    assert ca["ship_status"] == cb["ship_status"] == "entregue", "a caixa entregue entrega os dois pedidos"
    assert any(e["kind"] == "entregue" for e in cb["eventos"]) and any(e["kind"] == "entregue" for e in ca["eventos"])


# ------------------------------------------------------------------ fatura e pagamento
def test_fatura_de_fornecedor_pelo_quickbooks_pendente_e_paga(con):
    p, criada = aplica(con, msg("New payment request from Courtney Concepts Karting - invoice 1678",
                                "Your invoice is ready! BALANCE DUE$427.22 Shipped today.", de=QB))
    c = compras.compra(con, p)
    assert criada and (c["supplier"], c["invoice_number"], c["payment_status"], c["amount_due"]) == (
        "Courtney Concepts Karting", "1678", "pendente", 427.22)
    assert c["eventos"][0]["stage"] == "pagamento_pendente" and c["ship_status"] is None
    p2, _ = aplica(con, msg("Payment confirmation: Invoice #1678-(Courtney Concepts Karting)",
                            "You paid $427.22 to Courtney Concepts Karting on 09/22/2026", de=QB))
    c = compras.compra(con, p)
    assert p2 == p and c["payment_status"] == "pago" and c["paid_at"] and c["amount_due"] == 0


def test_lembrete_de_fatura_acha_a_mesma_compra(con):
    p, _ = aplica(con, msg("New payment request from Ryan Norberg LLC - invoice 1398", "BALANCE DUE$250.00", de=QB))
    p2, criada = aplica(con, msg("Invoice - Reminder: Your payment to Ryan Norberg LLC is due",
                                 "BALANCE DUE$250.00 a reminder to let you know that invoice 1398 has not been paid.", de=QB))
    assert (p2, criada) == (p, False)


def test_fatura_sem_numero_do_pedido_casa_pelo_valor_do_mesmo_fornecedor(con):
    p, _ = aplica(con, msg("Order #47838 confirmed", "Order #47838 Total $326.04 USD", de=KS))
    outra, _ = aplica(con, msg("Order #47863 confirmed", "Order #47863 Total $388.44 USD", de=KS))
    f, criada = aplica(con, msg("Invoice #INV-116671 — payment link enclosed", "Invoice #INV-116671 is ready for payment. Amount due: $326.04",
                                de="billing@vantagekarting.com"))
    assert (f, criada) == (p, False), "mesmo fornecedor (Vantage = KartSport), mesmo valor ao centavo"
    c = compras.compra(con, p)
    assert c["invoice_number"] == "INV-116671" and c["payment_status"] == "pendente"
    assert compras.compra(con, outra)["invoice_number"] is None


def test_alibaba_pendente_pago_enviado_entregue(con):
    n = "317394842001022128"
    al = "Alibaba <credit@notice.alibaba.com>"
    p, _ = aplica(con, msg(f"Your order is waiting for payment ({n})", f"Your payment for Trade Assurance order no. {n} is due.", de=al))
    assert compras.compra(con, p)["payment_status"] == "pendente"
    aplica(con, msg(f"Your initial payment has been received ({n})", f"received your initial payment for order no. {n}", de=al))
    aplica(con, msg(f"Your order is on its way ({n})", f"The supplier has shipped your products for order no. {n}", de=al))
    aplica(con, msg(f"Your order {n} has been delivered", "", de=al))
    c = compras.compra(con, p)
    assert (c["payment_status"], c["ship_status"], c["order_number"]) == ("pago", "entregue", n)
    assert um(con, "SELECT COUNT(*) AS n FROM purchase_orders")["n"] == 1


# ------------------------------------------------------------------ abrir o link
def _pagina_fake(tmp_path, monkeypatch, url, html):
    monkeypatch.setenv("CC_PAGINA_FAKE", str(tmp_path))
    (tmp_path / (hashlib.sha1(url.encode()).hexdigest() + ".html")).write_text(html, encoding="utf-8")


def test_abre_o_link_de_rastreio_e_poe_na_linha_do_tempo(con, tmp_path, monkeypatch):
    url = "https://track.lojadekart.com/orders/7781/status"
    p, _ = aplica(con, msg("Your order has shipped", "Order #7781 — track your package with the link below",
                           de="Kart Parts <orders@lojadekart.com>", links=[{"texto": "Track your package", "url": url},
                                                                           {"texto": "Unsubscribe", "url": "https://lojadekart.com/unsubscribe"}]))
    assert compras.compra(con, p)["tracking"] is None, "o e-mail só tinha o link"
    _pagina_fake(tmp_path, monkeypatch, url, "<html><style>.x{}</style><h1>Order 7781</h1><p>Status</p><p>Out for delivery</p>"
                 "<p>Carrier: UPS Tracking number: 1ZK102480399990777</p><p>Estimated delivery: Oct 8, 2026</p></html>")
    r = ce.rever_paginas(con)
    assert r == {"paginas_lidas": 1, "paginas_com_novidade": 1}
    c = compras.compra(con, p)
    assert c["tracking"] == "1ZK102480399990777" and c["expected_at"] == "2026-10-08"
    assert c["eventos"][-1]["stage"] == "saiu_para_entrega" and c["eventos"][-1]["mailbox"] == "web"
    assert ce.rever_paginas(con)["paginas_lidas"] == 0, "não abre a mesma página de novo antes de 6 h"
    um_pag = um(con, "SELECT ok, result FROM purchase_pages")
    assert um_pag["ok"] == 1 and json.loads(um_pag["result"])["stage"] == "saiu_para_entrega"
    # passadas as 6 h, a página diz entregue
    con.execute("UPDATE purchase_pages SET fetched_at='2000-01-01T00:00:00Z'")
    _pagina_fake(tmp_path, monkeypatch, url, "<p>Status</p><p>Delivered</p><p>Thursday 10/08/2026</p>")
    ce.rever_paginas(con)
    c = compras.compra(con, p)
    assert c["ship_status"] == "entregue" and c["delivered_at"]
    assert ce.rever_paginas(con)["paginas_lidas"] == 0, "entregue: não abre mais"


def test_pagina_de_loja_que_pede_login_nao_e_aberta(con, tmp_path, monkeypatch):
    monkeypatch.setenv("CC_PAGINA_FAKE", str(tmp_path))
    aplica(con, msg('Shipped: "Chain"', "Order #112-1234567-7654321", de="Amazon.com <shipment-tracking@amazon.com>",
                    links=[{"texto": "Track package", "url": "https://www.amazon.com/progress-tracker/package?orderId=112-1234567-7654321"}]))
    assert ce.rever_paginas(con)["paginas_lidas"] == 0


def test_link_util_e_endereco_proibido(monkeypatch):
    assert pagina.util("https://www.ups.com/track?tracknum=1Z", "Track")
    assert not pagina.util("https://loja.com/unsubscribe?u=1", "Track your order")
    assert not pagina.util("https://loja.com/account/login?next=/orders/1", "View order")
    assert not pagina.util("https://loja.com/blog", "Our blog")

    def resolve(host, *_a, **_k):
        ips = {"interno.loja.com": "10.0.0.5", "metadado.loja.com": "169.254.169.254", "local.loja.com": "127.0.0.1",
               "publica.loja.com": "93.184.216.34"}
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ips[host], 0))]
    monkeypatch.setattr(pagina.socket, "getaddrinfo", resolve)
    for host in ("interno", "metadado", "local"):
        with pytest.raises(pagina.ErroPagina):
            pagina._conferir(f"https://{host}.loja.com/track")
    with pytest.raises(pagina.ErroPagina):
        pagina._conferir("https://publica.loja.com:8443/track")
    with pytest.raises(pagina.ErroPagina):
        pagina._conferir("file:///etc/passwd")
    assert pagina._conferir("https://publica.loja.com/track")


def test_gmail_tira_css_e_lista_links_com_destino_real():
    import gmail_mcp
    html = ("<html><head><style>td{border:2px}</style></head><body><p>Order&nbsp;#47863</p>"
            "<a href=\"https://www.google.com/url?q=https://www.ups.com/track?tracknum%3D1ZK102480315679926&sa=D\">Track</a>"
            "<a href='mailto:x@y.com'>mail</a></body></html>")
    t = gmail_mcp._html_para_texto(html)
    assert "border" not in t and "Order #47863" in t
    assert gmail_mcp.links_do_html(html) == [{"texto": "Track", "url": "https://www.ups.com/track?tracknum=1ZK102480315679926"}]


# ------------------------------------------------------------------ varredura e refazer
def _caixa_fake(monkeypatch, caixa, consultas=None):
    def falso(sistema, ferramenta, **k):
        if ferramenta == "gmail_buscar":
            if consultas is not None:
                consultas.append(k["consulta"])
            return {"threads": [{"thread_id": t, "mensagens": len(ms)} for t, ms in caixa.items()]}
        assert k.get("com_links") is True and k.get("limite") == ce.CORPO_LIMITE
        return {"mensagens": caixa[k["thread_id"]]}
    monkeypatch.setattr(ce, "chamar", falso)


def test_aplica_em_ordem_de_chegada_entre_conversas(con, monkeypatch):
    """O "foi enviado" estava numa conversa lida antes da do "pedido confirmado": a ordem de
    chegada manda, e o pedido não vira duas compras."""
    caixa = {"envio": [msg("Order #47838 in final stages of processing", f"Order #47838 tracking number: {T1}", de=KS,
                           data="Tue, 29 Sep 2026 18:25:27 -0400")],
             "pedido": [msg("Order #47838 confirmed", "Order #47838 Total $326.04 USD", de=KS, data="Mon, 28 Sep 2026 14:33:27 -0400")],
             "ups": [msg("Your UPS Package was delivered", f"UPS Next Day Air {T1}", de=UPS, data="Wed, 30 Sep 2026 10:08:00 -0400")]}
    _caixa_fake(monkeypatch, caixa)
    r = ce.sincronizar(con, abrir_paginas=False)
    assert (r["compras_criadas"], r["compras_atualizadas"]) == (1, 2)
    c = compras.compras(con)[0]
    assert [e["kind"] for e in c["eventos"]] == ["pedido", "pedido", "entregue"] and c["ship_status"] == "entregue"


def test_janela_cobre_a_sincronia_parada(con, monkeypatch):
    inserir(con, "purchase_email_threads", thread_id="x", mailbox="urace", messages=1, decision="ignorado")
    inserir(con, "sync_logs", system="gmail_compras", started_at="2026-01-01T00:00:00Z", finished_at="2026-01-01T00:00:00Z",
            ok=1, items=0, message="")
    assert ce._dias_desde_ultima(con) == ce.MAX_JANELA_DIAS
    consultas = []
    _caixa_fake(monkeypatch, {}, consultas)
    assert ce.varrer(con, dias=365)["dias"] == 365 and "newer_than:365d" in consultas[0]


def test_refazer_guarda_backup_e_nao_toca_no_que_a_equipe_mexeu(con, tmp_path, monkeypatch):
    lixo, _ = aplica(con, msg("Your shipment is on the way 538060779646", "border: 2px", de="FedEx <TrackingUpdates@fedex.com>"))
    con.execute("UPDATE purchase_orders SET order_number='2px', reference='2px' WHERE id=?", (lixo,))
    da_equipe, _ = aplica(con, msg("Order Confirmation", "Order #7001", de="Comet <orders@cometkartsales.com>"))
    compras.adicionar_linhas(con, da_equipe, [{"description": "Corrente", "qty": 1}])
    con.commit()
    caixa = {"f1": [msg("Your shipment is on the way 538060779646", "Your shipment from WalMart.com is on the way",
                        de="FedEx <TrackingUpdates@fedex.com>", mid="real-1")]}
    _caixa_fake(monkeypatch, caixa)
    r = ce.refazer(con, dias=30, pasta=str(tmp_path))
    assert r["refeitas"] == 1 and os.path.exists(r["backup"])
    copia = json.load(open(r["backup"], encoding="utf-8"))
    assert [c["id"] for c in copia["compras"]] == [lixo] and copia["eventos"], "o que saiu está no backup"
    assert oct(os.stat(r["backup"]).st_mode & 0o777) == "0o600"
    assert um(con, "SELECT 1 AS x FROM purchase_orders WHERE id=?", (da_equipe,)), "compra com item fica"
    nova = um(con, "SELECT * FROM purchase_orders WHERE id != ?", (da_equipe,))
    assert (nova["order_number"], nova["supplier"], nova["tracking"]) == (None, "Walmart", "538060779646")
    assert {a["event"] for a in todos(con, "SELECT event FROM audit_logs")} >= {"purchase.email.rebuild"}


# ------------------------------------------------------------------ espelho no Asana (Shipping Orders)
class AsanaFalso:
    """O quadro Shipping Orders em memória, com a mesma porta do asana_mcp."""

    def __init__(self, tarefas):
        self.tarefas = {t["gid"]: t for t in tarefas}
        self.chamadas = []

    def pedidos_do_shipping(self):
        return list(self.tarefas.values())

    def espelhar_pedido(self, gid, nome, campos, campos_se_vazio, secao_gid, bloco, mexer_status=True):
        assert os.environ.get("APLICAR") == "1", "a escrita só acontece com APLICAR ligado nesta chamada"
        self.chamadas.append({"gid": gid, "nome": nome, "campos": campos, "se_vazio": campos_se_vazio, "secao": secao_gid,
                              "bloco": bloco, "mexer": mexer_status})
        if gid is None:
            gid = f"novo{len(self.tarefas) + 1}"
            self.tarefas[gid] = {"gid": gid, "name": nome, "custom_fields": [{"gid": k, "display_value": v} for k, v in campos_se_vazio.items()]}
            return {"aplicado": True, "gid": gid, "criada": True}
        return {"aplicado": True, "gid": gid, "criada": False}


def tarefa(gid, nome, pedido=None, rastreio=None, status=None):
    from command_center.providers import compras_asana as ca
    return {"gid": gid, "name": nome, "completed": False,
            "custom_fields": [{"gid": ca.CAMPO_PEDIDO, "display_value": pedido}, {"gid": ca.CAMPO_RASTREIO, "display_value": rastreio},
                              {"gid": ca.CAMPO_STATUS, "display_value": status}]}


def test_espelho_no_asana_acha_a_tarefa_do_pedido_e_nao_duplica(con, monkeypatch):
    from command_center.providers import compras_asana as ca
    falso = AsanaFalso([tarefa("t-amz", "Push button", "# ‫111-5909349-2751414", status="Order Created"),
                        tarefa("t-ks", "Kartsport North America - Order #47843", status=None),
                        tarefa("t-link", "CHAINS", "https://kartsportna.com/account/orders/685836",
                               f"https://www.ups.com/track?track=yes&trackNums={T1}", status="Pending/Review")])
    monkeypatch.setattr(ca, "modulo", lambda _s: falso)
    aplica(con, msg('Shipped: "Push button"', "Order #111-5909349-2751414", de="Amazon.com <shipment-tracking@amazon.com>"))
    aplica(con, msg("Order #47843 confirmed", "Order #47843 Total $4,234.92 USD", de=KS))
    aplica(con, msg("Your UPS Package was delivered", f"UPS Ground {T1}", de=UPS))
    aplica(con, msg("New payment request from Courtney Concepts Karting - invoice 1678", "BALANCE DUE$427.22", de=QB))
    r = ca.espelhar(con)
    assert r == {"ok": True, "criadas": 1, "atualizadas": 3, "erros": 0}
    por = {ch["gid"]: ch for ch in falso.chamadas}
    assert por["t-amz"]["campos"] == {ca.CAMPO_STATUS: ca.STATUS["Shipped"][0]} and por["t-amz"]["secao"] == ca.STATUS["Shipped"][1]
    assert por["t-ks"]["se_vazio"][ca.CAMPO_PEDIDO] == "47843" and por["t-ks"]["se_vazio"][ca.CAMPO_FORNECEDOR] == ca.FORNECEDORES["KartSport North America"]
    assert por["t-link"]["mexer"] is False, "Pending/Review é decisão de gente: o status não muda"
    nova = por[None]
    assert nova["campos"] == {ca.CAMPO_STATUS: ca.STATUS["Payment pending"][0]} and nova["se_vazio"][ca.CAMPO_PEDIDO] == "1678"
    assert nova["se_vazio"][ca.CAMPO_FORNECEDOR] == ca.OUTRO
    assert f"Rastreio UPS {T1}: https://www.ups.com/track?track=yes&trackNums={T1}" in por["t-link"]["bloco"], "o link vai na descrição"
    assert "/compras/" in nova["bloco"] and "Fatura: 1678 (pagamento pendente)" in nova["bloco"]
    assert {x["asana_gid"] for x in todos(con, "SELECT asana_gid FROM purchase_orders")} == {"t-amz", "t-ks", "t-link", "novo4"}
    falso.chamadas.clear()
    assert ca.espelhar(con) == {"ok": True, "criadas": 0, "atualizadas": 0}, "nada mudou: não escreve de novo"
    aplica(con, msg("Payment confirmation: Invoice #1678-(Courtney Concepts Karting)", "You paid $427.22", de=QB))
    ca.espelhar(con)
    assert [ch["gid"] for ch in falso.chamadas] == ["novo4"] and falso.chamadas[0]["campos"] == {ca.CAMPO_STATUS: ca.STATUS["Order Created"][0]}


def test_espelho_desligado_e_status_que_nao_volta(con, monkeypatch):
    from command_center.providers import compras_asana as ca
    monkeypatch.setenv("CC_ASANA_PEDIDOS", "0")
    assert ca.espelhar(con) == {"ok": True, "desligado": True}
    monkeypatch.delenv("CC_ASANA_PEDIDOS")
    falso = AsanaFalso([tarefa("t1", "Order #5531", "5531", status="Arrived")])
    monkeypatch.setattr(ca, "modulo", lambda _s: falso)
    aplica(con, msg("Order Confirmation", "Order #5531", de="Comet <orders@cometkartsales.com>"))
    ca.espelhar(con)
    assert falso.chamadas[0]["mexer"] is False, "Arrived no Asana não volta para Order Created"


def test_o_que_o_email_real_ensinou_sobre_links_e_datas():
    """UPS põe "Delivery Alerts" (preferências) antes do link de rastreio; a Shopify põe
    "Edit or Cancel Order" e "Reorder"; o QuickBooks, "View and pay". Nenhum desses se abre."""
    links = [{"texto": "Delivery Alerts", "url": "https://wwwapps.ups.com/ppc/ppc.html/preferencePage/mychoicePreference/deliveryalerts"},
             {"texto": "Edit or Cancel Order", "url": "https://shopify-order-edit.herokuapp.com/order-editor/kartsportna.myshopify.com/76"},
             {"texto": "View and pay", "url": "https://links.notification.intuit.com/ss/c/u001.abc"},
             {"texto": "Track Your Package", "url": "https://www.ups.com/track?loc=en_US&tracknum=1ZK102480302498548&requester=ST"}]
    assert ce._melhor_link(links) == links[3]["url"]
    assert not any(pagina.util(lk["url"], lk["texto"]) for lk in links[:3])
    assert ce.previsao("Estimated delivery date Tue, 09/29/2026") == "2026-09-29"


def test_gmail_espera_e_tenta_de_novo_quando_passa_da_cota(monkeypatch):
    """06/10 no VPS: a varredura de um ano parou com "Quota exceeded ... Units per minute per
    user". A cota volta no minuto seguinte: esperar e tentar de novo, não desistir."""
    import io
    import urllib.error
    import gmail_mcp
    esperas, chamadas = [], []

    class Resp:
        def __init__(self, corpo): self.corpo = corpo
        def read(self): return self.corpo
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def abre(req, timeout=0):
        chamadas.append(req.full_url)
        if len(chamadas) <= 2:
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(
                b'{"error":{"code":403,"message":"Quota exceeded for quota metric \'Total Query Cost\' and limit \'Units per minute per user\'"}}'))
        return Resp(b'{"id":"t1"}')
    monkeypatch.setattr(gmail_mcp, "_access_token", lambda nome: "tok")
    monkeypatch.setattr(gmail_mcp.urllib.request, "urlopen", abre)
    monkeypatch.setattr(gmail_mcp.time, "sleep", esperas.append)
    assert gmail_mcp._req("urace", "https://gmail.googleapis.com/gmail/v1/users/me/threads/t1") == {"id": "t1"}
    assert esperas == list(gmail_mcp.ESPERAS_COTA[:2]) and len(chamadas) == 3

    # 403 que não é cota (sem permissão) não fica tentando: erro na hora
    chamadas.clear(); esperas.clear()

    def negado(req, timeout=0):
        chamadas.append(1)
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(b'{"error":{"message":"Insufficient Permission"}}'))
    monkeypatch.setattr(gmail_mcp.urllib.request, "urlopen", negado)
    with pytest.raises(gmail_mcp.ErroFerramenta):
        gmail_mcp._req("urace", "https://gmail.googleapis.com/gmail/v1/users/me/threads/t1")
    assert esperas == [] and len(chamadas) == 1

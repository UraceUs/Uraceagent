"""E-mail de compra no urace@ vira compra; envio, pagamento e entrega a atualizam (dono, 30/09).

"...caso tenha somente a atualização do envio, crie também automaticamente."
"""
import os

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import atencao, auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, todos, um  # noqa: E402
from command_center.providers import compras, compras_email as ce, estoque  # noqa: E402

C = "/ops/api/compras"
SENHA = "senha-forte-123"


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def msg(assunto, corpo="", de="Amazon.com <shipment-tracking@amazon.com>", mid=None, data="Tue, 29 Sep 2026 10:00:00 -0400",
        marcadores=None):
    msg.n = getattr(msg, "n", 0) + 1
    return {"message_id": mid or f"m{msg.n}", "de": de, "assunto": assunto, "corpo": corpo, "data": data,
            "marcadores": marcadores or ["INBOX"]}


def aplica(con, m, thread="t1"):
    info = ce.ler(m)
    assert info, f"deveria ser compra: {m['assunto']}"
    return ce.aplicar(con, info, "urace", thread, m["message_id"])


# ------------------------------------------------------------------ leitura
@pytest.mark.parametrize("assunto,esperado", [
    ('Ordered: "Tillotson carburetor kit" and 1 more item', "pedido"),
    ("Your Amazon.com order #112-1234567-7654321", "pedido"),
    ("Order Confirmation", "pedido"),
    ('Shipped: "Tillotson carburetor kit"', "envio"),
    ("Your order is out for delivery", "envio"),
    ("Your package will be delivered today", "envio"),
    ("UPS Update: Package Scheduled for Delivery Tomorrow", "envio"),
    ('Delivered: "Tillotson carburetor kit"', "entregue"),
    ("Your package has been delivered", "entregue"),
    ("Receipt for your payment to Comet Kart Sales", "pagamento"),
    ("Payment confirmation for order 5531", "pagamento"),
    ("Your order has been cancelled", "cancelado"),
    ("Your refund for order 5531", "reembolso"),
    ("Seu pedido foi entregue", "entregue"),
    ("Seu pedido será entregue amanhã", "envio"),
])
def test_tipo_pelo_assunto(assunto, esperado):
    assert ce.tipo(assunto)[0] == esperado


def test_assunto_vago_decide_pelo_que_e_concreto():
    assert ce.tipo("Thanks for shopping with us", tem_rastreio=True) == ("envio", "corpo")
    assert ce.tipo("Thanks for shopping with us", tem_pedido=True) == ("pedido", "corpo")
    assert ce.tipo("Thanks for shopping with us") == (None, None), "palavra solta no corpo não basta"
    m = msg("A note from our team", "You can cancel your order anytime. Order #88123 is confirmed.", de="Comet <sales@cometkartsales.com>")
    assert ce.ler(m)["kind"] == "pedido", "rodapé com 'cancel' não vira cancelamento"


def test_extrai_numeros_rastreio_total_previsao():
    corpo = ("Order #112-1234567-7654321\nSubtotal: $40.00\nShipping: $5.00\nOrder Total: $45.99\n"
             "Arriving Friday, October 2\nTracking number: 1Z999AA10123456784 (UPS)")
    info = ce.ler(msg('Shipped: "Chain RK 219"', corpo))
    assert info["order_number"] == "112-1234567-7654321"
    assert info["tracking"] == ["1Z999AA10123456784"] and info["carrier"] == "UPS"
    assert info["amount"] == 45.99, "Subtotal não é o total"
    assert info["expected_at"] == "2026-10-02"
    assert info["items_hint"] == "Chain RK 219" and info["supplier"] == "Amazon"
    assert ce.numero_do_pedido("Order Confirmation — thanks!") is None, "'Confirmation' não é número"
    assert ce.numero_do_pedido("Order number: 5531") == "5531"
    assert ce.previsao("Estimated delivery: 10/05/2026") == "2026-10-05"
    assert ce.total("Total: $10.00 ... Total: $12.50") == 12.5, "com 'Total' solto, vale o último"


def test_fornecedor_pelo_remetente():
    assert ce.fornecedor("Comet Kart Sales <orders@cometkartsales.com>")[0] == "Comet Kart Sales"
    assert ce.fornecedor('"Orders" <no-reply@kartparts.com>')[0] == "Kartparts"
    assert ce.fornecedor("Speedy Kart Parts <no-reply@shopifyemail.com>")[0] == "Speedy Kart Parts"
    assert ce.fornecedor("UPS <mcinfo@ups.com>") == (None, "UPS")
    assert ce.fornecedor("service@paypal.com", "Receipt for your payment to Comet Kart Sales.\n")[0] == "Comet Kart Sales"


@pytest.mark.parametrize("m", [
    msg("[URACE] Order #1054 placed by John Smith", "Order #1054", de="URace Store <store@urace.us>"),
    msg("You've got a new order: #2231", "Order #2231", de="Wix <no-reply@wix.com>"),
    msg("Payment received from Enzo Kurian", "Invoice 1043 paid $500.00", de="QuickBooks <quickbooks@notification.intuit.com>"),
    msg("30% off everything — order now!", "Order #1 today", de="Kart Store <deals@kartstore.com>"),
    msg("Your order shipped", "Tracking number 1Z999AA10123456784", de="Kart <x@kart.com>", marcadores=["CATEGORY_PROMOTIONS"]),
    msg("Order #77 shipped", "", de="Shop <a@b.com>", marcadores=["URace Store/Shipped Orders"]),
    msg("Your subscription receipt", "Order #A123", de="Canva <no-reply@canva.com>"),
    msg("Receipt for your purchase", "Order #TP-4410 Amount paid: $60.00", de="Orlando Kart Center <noreply@orlandokartcenter.com>"),
    msg("Your receipt", "Order #8812", de="Receipts <no-reply@okc-mail.com>", marcadores=["Finances/Shopping/Orlando Kart Center/Track Pass"]),
])
def test_venda_nossa_cobranca_e_propaganda_nao_viram_compra(m):
    assert ce.ler(m) is None


# ------------------------------------------------------------------ compra
def test_ciclo_amazon_pedido_envio_entregue(con):
    pid, criada = aplica(con, msg('Ordered: "Tillotson carburetor kit"', "Order #112-1234567-7654321\nOrder Total: $89.90",
                                  de="Amazon.com <auto-confirm@amazon.com>"), "ta")
    assert criada
    c = compras.compra(con, pid)
    assert (c["status"], c["source"], c["ship_status"], c["supplier"]) == ("pedida", "email", "pedido", "Amazon")
    assert (c["order_number"], c["reference"], c["email_total"]) == ("112-1234567-7654321", "112-1234567-7654321", 89.9)
    assert c["linhas"] == [], "não inventa item: quem comprou confirma o que foi"

    p2, criada2 = aplica(con, msg('Shipped: "Tillotson carburetor kit"', "Order #112-1234567-7654321\nTracking number: TBA123456789012",
                                  data="Wed, 30 Sep 2026 08:00:00 -0400"), "tb")
    assert (p2, criada2) == (pid, False), "outra conversa, mesmo nº de pedido: mesma compra"
    p3, _ = aplica(con, msg('Delivered: "Tillotson carburetor kit"', "Your package was delivered. Order #112-1234567-7654321",
                            data="Thu, 01 Oct 2026 15:00:00 -0400"), "tc")
    c = compras.compra(con, pid)
    assert p3 == pid and c["ship_status"] == "entregue" and c["tracking"] == "TBA123456789012" and c["carrier"] == "Amazon"
    assert c["shipped_at"].startswith("2026-09-30") and c["delivered_at"].startswith("2026-10-01")
    assert c["status"] == "pedida", "entregue pela transportadora NÃO é recebido no estoque"
    assert [e["kind"] for e in c["eventos"]] == ["pedido", "envio", "entregue"]
    assert c["entregue_sem_entrada"] and not c["atrasada"]


def test_so_a_atualizacao_de_envio_cria_a_compra(con):
    pid, criada = aplica(con, msg("UPS Update: Your package is on the way", "Tracking Number: 1Z999AA10123456784\nScheduled delivery: Oct 3",
                                  de="UPS <mcinfo@ups.com>"))
    c = compras.compra(con, pid)
    assert criada and c["ship_status"] == "enviado" and c["carrier"] == "UPS"
    assert c["supplier"] == "Não identificado (envio UPS)" and c["expected_at"] == "2026-10-03"
    # a entrega pelo mesmo rastreio, noutra conversa, atualiza a mesma compra
    p2, _ = aplica(con, msg("UPS Update: Delivered", "Tracking Number: 1Z999AA10123456784", de="UPS <mcinfo@ups.com>"), "t9")
    assert p2 == pid and compras.compra(con, pid)["ship_status"] == "entregue"


def test_pagamento_depois_do_envio_nao_volta_o_status(con):
    pid, _ = aplica(con, msg("Your order has shipped", "Order number: 5531\nTracking number: 1Z999AA10123456784",
                             de="Comet Kart Sales <orders@cometkartsales.com>"))
    aplica(con, msg("Receipt for your payment to Comet Kart Sales", "Order number: 5531\nAmount paid: $120.00",
                    de="service@paypal.com"), "t2")
    c = compras.compra(con, pid)
    assert c["ship_status"] == "enviado" and c["paid_at"], "pago fica registrado, sem desfazer 'enviado'"
    assert c["supplier"] == "Comet Kart Sales"


def test_compra_digitada_a_mao_e_achada_pela_referencia(con):
    iid = estoque.criar_item(con, "peca", "Vela NGK")
    pid = compras.criar_compra(con, None, [{"item_id": iid, "qty": 4}], supplier="Comet Kart Sales", reference="#5531")
    p2, criada = aplica(con, msg("Order 5531 shipped", "Order #5531 Tracking number: 1Z999AA10123456784",
                                 de="Comet Kart Sales <orders@cometkartsales.com>"))
    c = compras.compra(con, pid)
    assert (p2, criada) == (pid, False)
    assert (c["status"], c["ship_status"], c["order_number"]) == ("pedida", "enviado", "5531"), "rascunho vira pedida"
    assert len(c["linhas"]) == 1


def test_mesma_mensagem_nao_conta_duas_vezes(con):
    m = msg("Your order has shipped", "Order #9001 Tracking number: 1Z999AA10123456784", de="Kart <x@kartparts.com>")
    pid, _ = aplica(con, m)
    assert ce.aplicar(con, ce.ler(m), "urace", "t1", m["message_id"]) == (None, False)
    assert len(compras.compra(con, pid)["eventos"]) == 1


def test_conversa_do_gmail_com_pedidos_diferentes_nao_junta(con):
    p1, _ = aplica(con, msg("Order Confirmation", "Order #7001", de="Comet <orders@cometkartsales.com>"), "mesma")
    p2, criada = aplica(con, msg("Order Confirmation", "Order #7002", de="Comet <orders@cometkartsales.com>"), "mesma")
    assert criada and p1 != p2
    p3, _ = aplica(con, msg("Payment confirmation", "Thanks! Payment confirmed.", de="Comet <orders@cometkartsales.com>"), "mesma")
    assert p3 == p2, "sem número, a conversa decide"


def test_cancelado_marca_o_envio_e_nao_cancela_sozinho(con):
    pid, _ = aplica(con, msg("Order Confirmation", "Order #7001", de="Comet <orders@cometkartsales.com>"))
    aplica(con, msg("Your order has been cancelled", "Order #7001", de="Comet <orders@cometkartsales.com>"), "t2")
    c = compras.compra(con, pid)
    assert c["ship_status"] == "cancelado" and c["status"] == "pedida", "quem cancela a compra é gente"


# ------------------------------------------------------------------ pedidos da equipe
def test_sku_no_email_liga_o_pedido_sozinho_e_nome_so_sugere(con):
    corrente = estoque.criar_item(con, "peca", "Rk Non Oring Chain 219", sku="RK219-106")
    vela = estoque.criar_item(con, "peca", "Vela NGK B9EG")
    r1 = compras.criar_pedido(con, None, 2, item_id=corrente)
    r2 = compras.criar_pedido(con, None, 3, item_id=vela)
    r3 = compras.criar_pedido(con, None, 1, description="Chave de roda 17mm")
    pid, _ = aplica(con, msg("Order Confirmation", "Order #7001\nRK219-106 Chain x2\nNGK B9EG Vela spark plug x3",
                             de="Comet <orders@cometkartsales.com>"))
    c = compras.compra(con, pid)
    assert [l["request_id"] for l in c["linhas"]] == [r1], "SKU casou: ligado, com a quantidade do pedido"
    assert um(con, "SELECT status FROM purchase_requests WHERE id=?", (r1,))["status"] == "comprando"
    sug = [s["id"] for s in compras.pedidos_sugeridos(con, pid)]
    assert sug == [r2], "todas as palavras do pedido no e-mail: sugestão; r3 não aparece"
    assert r3 not in sug
    # o pedido ligado passa a mostrar o envio da compra
    aplica(con, msg("Your order has shipped", "Order #7001 Tracking number: 1Z999AA10123456784",
                    de="Comet <orders@cometkartsales.com>"), "t2")
    p = next(x for x in compras.pedidos(con) if x["id"] == r1)
    assert (p["envio"], p["rastreio"], p["transportadora"]) == ("enviado", "1Z999AA10123456784", "UPS")


def test_concluir_compra_que_nao_e_de_estoque(con):
    pid, _ = aplica(con, msg("Receipt for your payment", "Order #TP-4410 Amount paid: $60.00",
                             de="Kart Tools <noreply@karttools.com>"))
    rid = compras.criar_pedido(con, None, 1, description="Passe de pista")
    compras.ligar_pedidos(con, pid, [rid])
    compras.concluir(con, pid)
    assert compras.compra(con, pid)["status"] == "recebida"
    assert um(con, "SELECT status FROM purchase_requests WHERE id=?", (rid,))["status"] == "chegou"
    assert todos(con, "SELECT * FROM stock_moves") == []
    with pytest.raises(compras.ErroCompra):
        compras.concluir(con, pid)


def test_atencao_mostra_entregue_sem_entrada(con):
    pid, _ = aplica(con, msg('Delivered: "Brake pads"', "Order #112-1234567-7654321", de="Amazon.com <x@amazon.com>"))
    chaves = {i["key"]: i for i in atencao.coletar(con)}
    assert f"compra-entregue:purchase:{pid}" in chaves
    assert "falta dar entrada" in chaves[f"compra-entregue:purchase:{pid}"]["title"]


# ------------------------------------------------------------------ sincronia
def test_sincronia_so_rele_conversa_que_mudou(con, monkeypatch):
    chamadas = []
    caixa = {"t1": [msg('Ordered: "Kit freio"', "Order #112-1111111-2222222", de="Amazon.com <a@amazon.com>")],
             "t2": [msg("Lunch on Friday?", "hey", de="Amigo <a@gmail.com>")]}

    def falso(sistema, ferramenta, **k):
        chamadas.append((ferramenta, k.get("thread_id"), k.get("consulta")))
        if ferramenta == "gmail_buscar":
            assert k["so_inbox"] is False and k["conta"] == "urace", "a caixa inteira do urace@, não só a inbox"
            return {"threads": [{"thread_id": t, "mensagens": len(ms)} for t, ms in caixa.items()]}
        return {"mensagens": caixa[k["thread_id"]]}
    monkeypatch.setattr(ce, "chamar", falso)
    r = ce.sincronizar(con)
    assert (r["compras_criadas"], r["ignoradas"], r["dias"]) == (1, 1, ce.PRIMEIRA_VEZ_DIAS)
    assert "newer_than:7d" in chamadas[0][2]
    chamadas.clear()
    r = ce.sincronizar(con)
    assert [c[0] for c in chamadas] == ["gmail_buscar"] and r["dias"] == ce.JANELA_DIAS, "nada mudou: não relê"
    caixa["t1"].append(msg('Shipped: "Kit freio"', "Order #112-1111111-2222222 Tracking number: TBA123456789012"))
    chamadas.clear()
    r = ce.sincronizar(con)
    assert [c[1] for c in chamadas if c[0] == "gmail_thread"] == ["t1"] and r["compras_atualizadas"] == 1
    assert um(con, "SELECT ship_status FROM purchase_orders")["ship_status"] == "enviado"
    assert um(con, "SELECT COUNT(*) AS n FROM purchase_orders")["n"] == 1


def test_sincronia_sem_token_nao_quebra(con, monkeypatch):
    class ErroFerramenta(Exception):
        pass

    def falso(*a, **k):
        raise ErroFerramenta("conta urace não configurada")
    monkeypatch.setattr(ce, "chamar", falso)
    assert ce.sincronizar(con)["ok"] is False


# ------------------------------------------------------------------ API
@pytest.fixture()
def cli(con, tmp_path, monkeypatch):
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    auth.criar_usuario(con, "mec@urace.us", "Mecânico", "OPERATOR", SENHA)
    auth.criar_usuario(con, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    con.commit()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def test_api_itens_pedidos_e_concluir(cli, con):
    pid, _ = aplica(con, msg("Order Confirmation", "Order #7001 Order Total: $300.00", de="Comet <orders@cometkartsales.com>"))
    rid = compras.criar_pedido(con, None, 2, description="Pneu MG amarelo")
    con.commit()
    h = entra(cli, "mec@urace.us")
    assert cli.post(f"{C}/{pid}/linhas", headers=h, json=[{"description": "Pneu", "qty": 1}]).status_code == 403
    assert cli.post(f"{C}/{pid}/concluir", headers=h).status_code == 403
    v = cli.get(f"{C}/{pid}", headers=h).json()
    assert v["email_total"] is None and v["eventos"][0]["link"].startswith("https://mail.google.com/mail/u/0/#all/")
    assert all(c["email_total"] is None for c in cli.get(C, headers=h).json()["compras"])
    h = entra(cli, "ger@urace.us")
    assert cli.get(f"{C}/{pid}", headers=h).json()["email_total"] == 300.0
    assert cli.post(f"{C}/{pid}/linhas", headers=h, json=[{"description": "Corrente", "qty": 1, "unit_cost": 40}]).status_code == 200
    assert cli.post(f"{C}/{pid}/pedidos", headers=h, json={"request_ids": [rid]}).status_code == 200
    assert len(cli.get(f"{C}/{pid}", headers=h).json()["linhas"]) == 2
    assert cli.post(f"{C}/{pid}/pedidos", headers=h, json={"request_ids": [rid]}).status_code == 400, "já está comprando"
    assert cli.get(f"{C}/resumo", headers=h).json()["entregues"] == 0
    assert cli.post(f"{C}/{pid}/concluir", headers=h).status_code == 200
    assert cli.post(f"{C}/{pid}/linhas", headers=h, json=[{"description": "X", "qty": 1}]).status_code == 400
    ev = {a["event"] for a in todos(con, "SELECT event FROM audit_logs")}
    assert {"purchase.email", "purchase.lines", "purchase.link_requests", "purchase.close"} <= ev


def test_data_da_entrega_no_fuso_da_florida():
    assert atencao._dia_fl("2026-10-01T01:30:00Z") == "2026-09-30", "21h30 EDT ainda é dia 30"
    assert atencao._dia_fl("2026-10-01T15:00:00.000Z") == "2026-10-01"

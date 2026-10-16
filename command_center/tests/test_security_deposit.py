"""#317 · Site › Security deposit: o valor cobrado no site e a devolução pelo Stripe, com o valor escolhido.

Dono, 16/10: *"uma sessão de security deposit, onde a gente consiga ter o controle para fazer o reembolso de cada
security deposit e alterar o valor do security deposit para ser cobrado no site … só clicar no botão e fazer o refund
do Security Deposit pelo Command Center. Sempre conseguindo alterar o valor que vai ser reembolsado."* E: *"eu coloquei
um serviço, fui testar lá no checkout, e o serviço … ia permitir que eu fizesse o checkout … sem o security deposit …
coloca em cada serviço … um checkbox para marcar que ele é obrigatório."*

Dados fictícios (@example.com, 555-01xx). O Stripe é o falso dos testes da loja, com as devoluções.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from command_center.api import auth
from command_center.api.main import app
from command_center.db import aplicar_schema, inserir, todos, um
from command_center.providers import cobranca_agenda, deposito_site, servicos_site
from command_center.tests.test_agenda_sessoes import proximo
from command_center.tests.test_carrinho import _checkout, _entrar, _pagar, _sessao, loja  # noqa: F401
from command_center.tests.test_stripe_loja import StripeFalso, amb  # noqa: F401

SENHA_EQUIPE = "senha-da-equipe-9"
D = "/ops/api/site/depositos"


class StripeComDevolucao(StripeFalso):
    """O Stripe falso da loja, mais `POST /v1/refunds` e a lista de devoluções de um pagamento."""
    def __init__(self, base):
        super().__init__()
        self.base, self.devolucoes, self.falhar, self.sumir = base, [], None, False
        self.chamadas, self.sessoes = base.chamadas, base.sessoes

    def __call__(self, metodo, caminho, campos=None, idem=None):
        if metodo == "POST" and caminho == "/v1/refunds":
            self.chamadas.append((metodo, caminho, campos, idem))
            if self.falhar:
                raise self.falhar
            r = {"id": f"re_test_{len(self.devolucoes) + 1:03d}", "object": "refund", "amount": campos["amount"],
                 "payment_intent": campos["payment_intent"], "status": "succeeded", "metadata": campos.get("metadata") or {}}
            self.devolucoes.append(r)
            if self.sumir:
                raise TimeoutError("a resposta se perdeu")
            return r
        if metodo == "GET" and caminho.startswith("/v1/refunds?"):
            self.chamadas.append((metodo, caminho, campos, idem))
            pi = caminho.split("payment_intent=", 1)[1].split("&", 1)[0]
            return {"object": "list", "data": [r for r in self.devolucoes if r["payment_intent"] == pi]}
        return self.base(metodo, caminho, campos, idem)


@pytest.fixture()
def dep(loja, monkeypatch):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    from command_center.providers import stripe_loja
    sd = StripeComDevolucao(st)
    monkeypatch.setattr(stripe_loja, "_http", sd)
    for email, papel in (("ger@urace.us", "MANAGER"), ("op@urace.us", "OPERATOR"), ("ver@urace.us", "VIEWER")):
        auth.criar_usuario(con, email, email.split("@")[0].title(), papel, SENHA_EQUIPE)
    # uma compra de verdade pelo carrinho: sessão com o depósito de US$ 400, paga no Stripe (o webhook)
    conta, pid = _entrar(cli, con)
    r = _checkout(cli, [_sessao(sid, proximo(5), pid)])
    assert r.status_code == 200, r.text
    assert _pagar(cli, st, next(iter(st.sessoes))).status_code == 200
    o = um(con, "SELECT * FROM store_orders WHERE kind='carrinho'")
    assert (o["status"], o["payment_intent"], o["deposit"]) == ("pago", "pi_c1", 400)
    item = um(con, "SELECT id FROM store_order_items WHERE order_id=? AND deposit>0", (o["id"],))["id"]
    with TestClient(app, base_url="https://cc.test") as painel:
        yield painel, con, sd, o["id"], item, sid


def entra(painel, email="ger@urace.us"):
    painel.cookies.clear()
    assert painel.post("/ops/api/auth/login", json={"email": email, "password": SENHA_EQUIPE}).status_code == 200
    return {"X-CSRF": painel.cookies.get("cc_csrf")}


def devolver(painel, h, oid, item, valor, nota=None):
    return painel.post(f"{D}/{oid}/reembolsar", json={"item_id": item, "valor": valor, "nota": nota}, headers=h)


def _buy_now(con, deposito=50, pi="pi_buy_1", status="pago"):
    return inserir(con, "store_orders", kind="produto", product_slug="capacete-e2e", product_name="Capacete (teste)",
                   quantity=1, unit_price=300, amount=300 + deposito, delivery="retirada", status=status, deposit=deposito,
                   payment_intent=pi, email="compra@example.com", name="Rita Teste", paid_at="2026-10-15T15:00:00.000Z")


# ------------------------------------------------------------------ a lista
def test_a_lista_mostra_cada_deposito_pago_e_o_que_segue_retido(dep):
    painel, con, sd, oid, item, sid = dep
    _buy_now(con)
    _buy_now(con, pi="pi_nao_pago", status="aberto")           # não pago: depósito nenhum retido
    h = entra(painel, "op@urace.us")
    r = painel.get(D, headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["total"] == 2 and d["soma_retido"] == 450 and d["stripe"] and d["modo_teste"]
    sessao = next(x for x in d["depositos"] if x["order_id"] == oid)
    assert (sessao["item_id"], sessao["deposito"], sessao["retido"], sessao["piloto"]) == (item, 400, 400, "Theo Souza")
    assert sessao["pode_devolver"] and sessao["devolucoes"] == []
    assert "pi_c1" not in r.text and "payment_intent" not in sessao, "o id do pagamento fica no servidor"
    assert painel.get(D, params={"q": "theo"}, headers=h).json()["total"] == 1
    assert painel.get(D, params={"q": f"#{oid}"}, headers=h).json()["total"] == 1
    assert painel.get(D, params={"estado": "devolvidos"}, headers=h).json()["total"] == 0
    assert painel.get(D, params={"estado": "x"}, headers=h).status_code == 400
    p = painel.get(D, params={"limit": 1, "offset": 1}, headers=h).json()
    assert p["total"] == 2 and len(p["depositos"]) == 1, "paginada no servidor"


def test_devolve_o_deposito_inteiro_pelo_stripe(dep):
    painel, con, sd, oid, item, sid = dep
    h = entra(painel)
    r = devolver(painel, h, oid, item, "400", "sem dano no kart")
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "feito" and r.json()["stripe"] == "re_test_001"
    (_, caminho, campos, idem), = [c for c in sd.chamadas if c[1] == "/v1/refunds"]
    assert (campos["payment_intent"], campos["amount"]) == ("pi_c1", 40000)
    assert campos["metadata"]["tipo"] == "security_deposit" and idem.startswith("urace-deposito-")
    d = painel.get(D, params={"estado": "devolvidos"}, headers=h).json()
    x, = d["depositos"]
    assert (x["retido"], x["devolvido"], x["pode_devolver"]) == (0, 400, False)
    assert x["devolucoes"][0]["nota"] == "sem dano no kart" and x["devolucoes"][0]["por"] == "Ger"
    ev = um(con, "SELECT * FROM audit_logs WHERE event='store.deposit.refund'")
    assert ev and '"valor": 400' in ev["detail"]


def test_devolve_em_partes_e_nunca_mais_que_o_retido(dep):
    painel, con, sd, oid, item, sid = dep
    h = entra(painel)
    assert devolver(painel, h, oid, item, 150).status_code == 200
    r = devolver(painel, h, oid, item, 250.01)
    assert r.status_code == 400 and "250.00" in r.json()["detail"]
    assert devolver(painel, h, oid, item, "$250.00").status_code == 200
    assert devolver(painel, h, oid, item, 1).status_code == 400, "já devolveu tudo"
    assert [c[2]["amount"] for c in sd.chamadas if c[1] == "/v1/refunds"] == [15000, 25000]
    for ruim in (0, -5, "abc", "1.234"):
        assert devolver(painel, h, oid, item, ruim).status_code == 400


def test_o_buy_now_tambem_devolve(dep):
    painel, con, sd, oid, item, sid = dep
    b = _buy_now(con)
    h = entra(painel)
    assert devolver(painel, h, b, None, 20).status_code == 200
    x = next(y for y in painel.get(D, headers=h).json()["depositos"] if y["order_id"] == b)
    assert (x["item_id"], x["retido"], x["devolvido"]) == (None, 30, 20)
    assert devolver(painel, h, b, item, 1).status_code == 400, "a linha de outro pedido não serve"


def test_stripe_recusou_fica_registrado_e_o_valor_volta_a_ficar_retido(dep):
    painel, con, sd, oid, item, sid = dep
    from command_center.providers import stripe_loja
    sd.falhar = stripe_loja.ErroStripe("Stripe HTTP 400: Charge has already been refunded.")
    h = entra(painel)
    r = devolver(painel, h, oid, item, 400)
    assert r.status_code == 502 and "already been refunded" in r.json()["detail"]
    x = painel.get(D, headers=h).json()["depositos"][0]
    assert x["retido"] == 400 and x["devolucoes"][0]["estado"] == "falhou"
    sd.falhar = None
    assert devolver(painel, h, oid, item, 400).status_code == 200


def test_resposta_perdida_reserva_o_valor_e_o_conferir_acerta(dep):
    """Dois cliques (ou a resposta que não volta) nunca devolvem duas vezes: o valor fica reservado até conferir."""
    painel, con, sd, oid, item, sid = dep
    h = entra(painel)
    sd.sumir = True
    r = devolver(painel, h, oid, item, 400)
    assert r.status_code == 504
    assert devolver(painel, h, oid, item, 400).status_code == 400, "o segundo clique não devolve de novo"
    assert len([c for c in sd.chamadas if c[1] == "/v1/refunds"]) == 1
    sd.sumir = False
    c = painel.post(f"{D}/{oid}/conferir", headers=h)
    assert c.status_code == 200 and c.json() == {"acertos": 1, "stripe_devolvido": 400}
    x = painel.get(D, params={"estado": "todos"}, headers=h).json()["depositos"][0]
    assert x["devolucoes"][0]["estado"] == "feito" and x["devolucoes"][0]["stripe"] == "re_test_001" and x["retido"] == 0


def test_pendente_que_nunca_chegou_ao_stripe_volta_a_ficar_retido(dep):
    painel, con, sd, oid, item, sid = dep
    rid = inserir(con, "store_deposit_refunds", order_id=oid, item_id=item, amount=400, status="pendente",
                  created_at=(datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z"))
    h = entra(painel)
    assert painel.get(D, headers=h).json()["depositos"][0]["retido"] == 0
    assert painel.post(f"{D}/{oid}/conferir", headers=h).json()["acertos"] == 1
    assert um(con, "SELECT status FROM store_deposit_refunds WHERE id=?", (rid,))["status"] == "falhou"
    assert painel.get(D, headers=h).json()["depositos"][0]["retido"] == 400


def test_o_conferir_mostra_o_que_foi_devolvido_direto_no_stripe(dep):
    painel, con, sd, oid, item, sid = dep
    sd.devolucoes.append({"id": "re_painel_stripe", "amount": 7190, "payment_intent": "pi_c1", "status": "succeeded", "metadata": {}})
    h = entra(painel)
    assert painel.post(f"{D}/{oid}/conferir", headers=h).json() == {"acertos": 0, "stripe_devolvido": 71.9}
    x = painel.get(D, headers=h).json()["depositos"][0]
    assert x["stripe_devolvido"] == 71.9 and x["retido"] == 400, "devolução de fora não é dada como do depósito"


def test_so_gerente_devolve_e_confere_e_sempre_com_csrf(dep):
    painel, con, sd, oid, item, sid = dep
    h = entra(painel, "op@urace.us")
    assert devolver(painel, h, oid, item, 10).status_code == 403
    assert painel.post(f"{D}/{oid}/conferir", headers=h).status_code == 403
    h = entra(painel, "ver@urace.us")
    assert painel.get(D, headers=h).status_code == 403
    entra(painel)
    assert painel.post(f"{D}/{oid}/reembolsar", json={"item_id": item, "valor": 10}).status_code == 403
    assert not [c for c in sd.chamadas if c[1] == "/v1/refunds"]


def test_sem_stripe_nao_devolve(dep, monkeypatch):
    painel, con, sd, oid, item, sid = dep
    monkeypatch.delenv("STRIPE_SECRET_KEY")
    h = entra(painel)
    assert painel.get(D, headers=h).json()["stripe"] is False
    r = devolver(painel, h, oid, item, 10)
    assert r.status_code == 400 and "Stripe" in r.json()["detail"]


# ------------------------------------------------------------------ o valor cobrado no site
def test_muda_o_valor_do_deposito_cobrado_no_site(dep):
    painel, con, sd, oid, item, sid = dep
    h = entra(painel)
    v = painel.get(f"{D}/valores", headers=h).json()
    s = next(x for x in v["servicos"] if x["id"] == sid)
    assert (s["deposit"], s["deposit_required"]) == (400, True)
    r = painel.patch(f"{D}/valor", json={"tipo": "servico", "id": sid, "valor": "1.00"}, headers=h)
    assert r.status_code == 200
    assert um(con, "SELECT deposit FROM booking_services WHERE id=?", (sid,))["deposit"] == 1
    ev = um(con, "SELECT detail FROM audit_logs WHERE event='booking.service.update' ORDER BY id DESC")
    assert '"via": "security deposit"' in ev["detail"] and '"antes": 400' in ev["detail"]
    # o carrinho já cobra o valor novo; o pedido pago continua com o valor do dia
    d = _carrinho_de(con, sid)
    assert d["deposito"] == 1
    assert um(con, "SELECT deposit FROM store_order_items WHERE id=?", (item,))["deposit"] == 400
    h2 = entra(painel, "op@urace.us")
    assert painel.patch(f"{D}/valor", json={"tipo": "servico", "id": sid, "valor": 2}, headers=h2).status_code == 403


def test_obrigatorio_nao_deixa_o_deposito_zerar(dep):
    painel, con, sd, oid, item, sid = dep
    h = entra(painel)
    r = painel.patch(f"{D}/valor", json={"tipo": "servico", "id": sid, "valor": 0}, headers=h)
    assert r.status_code == 400 and "obrigatório" in r.json()["detail"]
    assert painel.patch(f"{D}/valor", json={"tipo": "servico", "id": sid, "obrigatorio": False}, headers=h).status_code == 200
    assert painel.patch(f"{D}/valor", json={"tipo": "servico", "id": sid, "valor": 0}, headers=h).status_code == 200
    r = painel.patch(f"{D}/valor", json={"tipo": "servico", "id": sid, "obrigatorio": True}, headers=h)
    assert r.status_code == 400, "marcar obrigatório com o depósito zerado não passa"
    assert painel.patch(f"{D}/valor", json={"tipo": "servico", "id": 99999, "valor": 5}, headers=h).status_code == 404


def test_produto_com_deposito_muda_aqui_tambem(dep):
    painel, con, sd, oid, item, sid = dep
    pid = um(con, "SELECT id FROM store_products ORDER BY id LIMIT 1")["id"]
    h = entra(painel)
    assert painel.get(f"{D}/valores", headers=h).json()["produtos"] == []
    assert painel.patch(f"{D}/valor", json={"tipo": "produto", "id": pid, "valor": 25}, headers=h).status_code == 200
    assert [p["deposit"] for p in painel.get(f"{D}/valores", headers=h).json()["produtos"]] == [25]
    assert painel.patch(f"{D}/valor", json={"tipo": "kart", "id": pid, "valor": 25}, headers=h).status_code == 400


# ------------------------------------------------------------------ "obrigatório" no serviço
def test_servico_novo_com_deposito_obrigatorio_pede_o_valor(dep):
    painel, con, sd, oid, item, sid = dep
    h = entra(painel)
    novo = {"name": "Teste de checkout", "price": 10, "kind": "session", "deposit_required": True}
    r = painel.post("/ops/api/site/servicos", json=novo, headers=h)
    assert r.status_code == 400 and "obrigatório" in r.json()["detail"]
    r = painel.post("/ops/api/site/servicos", json={**novo, "deposit": "1"}, headers=h)
    assert r.status_code == 201
    s = um(con, "SELECT * FROM booking_services WHERE id=?", (r.json()["id"],))
    assert (s["deposit"], s["deposit_required"]) == (1, 1)
    sem = painel.post("/ops/api/site/servicos", json={"name": "Sem depósito", "price": 10, "kind": "session"}, headers=h).json()["id"]
    assert um(con, "SELECT deposit_required FROM booking_services WHERE id=?", (sem,))["deposit_required"] == 0
    r = painel.patch(f"/ops/api/site/servicos/{sem}", json={"deposit_required": True}, headers=h)
    assert r.status_code == 400


def _carrinho_de(con, sid):
    from command_center.providers import carrinho
    return carrinho.cotar(con, [_sessao(sid, proximo(6))])


def test_checkout_nunca_passa_sem_o_deposito_obrigatorio(dep):
    """O caso do dono: o serviço sem valor de depósito deixava pagar sem ele."""
    painel, con, sd, oid, item, sid = dep
    con.execute("UPDATE booking_services SET deposit=0, deposit_required=1 WHERE id=?", (sid,))   # mexido à mão no banco
    from command_center.providers import carrinho
    linha = carrinho._linha_sessao(con, _sessao(sid, proximo(6)), None, {}, {}, True)
    assert linha["erro"] and "can't be paid online" in linha["erro"]
    b = {"service_id": sid, "price": 719, "service_name": "Arrive and Drive 4-stroke", "date": proximo(6).isoformat(), "period": "manha"}
    with pytest.raises(cobranca_agenda.ErroCobranca, match="obrigatório"):
        cobranca_agenda.linhas_da_invoice(con, b)


def test_a_migracao_marca_obrigatorio_uma_vez_so(dep):
    painel, con, sd, oid, item, sid = dep
    assert um(con, "SELECT deposit_required FROM booking_services WHERE id=?", (sid,))["deposit_required"] == 1
    servicos_site.mudar(con, None, sid, {"deposit_required": False})
    aplicar_schema(con)
    assert um(con, "SELECT deposit_required FROM booking_services WHERE id=?", (sid,))["deposit_required"] == 0, \
        "o que o gerente desmarcou continua desmarcado depois da subida"
    plano = um(con, "SELECT deposit_required FROM booking_services WHERE kind='addon' LIMIT 1")
    assert plano is None or plano["deposit_required"] == 0


def test_os_valores_e_a_lista_nao_tem_dado_de_cartao(dep):
    painel, con, sd, oid, item, sid = dep
    h = entra(painel)
    devolver(painel, h, oid, item, 400)
    txt = painel.get(D, params={"estado": "todos"}, headers=h).text
    assert "pi_c1" not in txt and "sk_test" not in txt
    assert todos(con, "SELECT * FROM store_deposit_refunds")[0]["stripe_refund_id"] == "re_test_001"
    assert deposito_site.modo_teste()

"""Loja paga no ato pelo Stripe Checkout (#174).

Dono, 08/10: *"Stripe Checkout"* para a loja própria; 09/10: *"tbm tenho a conta da stripe"*.

O caminho de um pedido:
  1. A página do produto (preço fechado e em estoque) manda para `POST /ops/api/vitrine/checkout`.
     O preço sai do catálogo do site, nunca do formulário. Nasce um `store_orders` 'aberto' e a
     sessão do Checkout (cartão, Apple Pay, Google Pay: os meios ligados na conta do Stripe).
  2. A pessoa paga no checkout.stripe.com e volta para `/store/thanks/`.
  3. O Stripe avisa `checkout.session.completed` no webhook, com assinatura (STRIPE_WEBHOOK_SECRET).
     Cada evento entra uma vez só (`stripe_events`). Pago → o pedido vira oportunidade GANHO em
     Vendas, ligada ao card do cliente quando o e-mail e o nome batem; a pessoa recebe a
     confirmação; a equipe recebe o aviso para separar e entregar; o QuickBooks ganha o
     Sales Receipt (já pago) para o financeiro continuar lá.
  A página de obrigado também confere a sessão no Stripe: se o webhook atrasar, nada se perde, e
  o que já foi feito não se repete (cada passo olha o próprio campo no pedido).

Chaves só no VPS, em ~/.urace/adminai.env: STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET (e a
publicável, que o Checkout hospedado não precisa). Sem a secreta, a loja segue no pedido para a
equipe (#164). Nunca se loga chave, corpo de evento nem dado de cartão (o cartão nem passa aqui).
"""
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from command_center.db import agora, atualizar, auditar, inserir, todos, um

API = "https://api.stripe.com"
TOLERANCIA = 300                       # segundos entre o Stripe assinar e nós recebermos
PAISES_ENVIO = ("US", "CA", "MX", "BR", "PR")
FL = ZoneInfo("America/New_York")


class ErroStripe(Exception):
    def __init__(self, msg="", codigo=None):
        super().__init__(msg)
        self.codigo = codigo           # #317: o HTTP do Stripe (5xx = resultado indeterminado: pode ter feito)


def ligado():
    return bool(os.environ.get("STRIPE_SECRET_KEY", "").strip())


def _base():
    return os.environ.get("STRIPE_API_BASE", API).rstrip("/")     # o e2e aponta para um Stripe falso


def _achatar(d, prefixo=""):
    """{"a": {"b": [1]}} → [("a[b][0]", "1")]: o formato de formulário da API do Stripe."""
    out = []
    itens = d.items() if isinstance(d, dict) else enumerate(d)
    for k, v in itens:
        chave = f"{prefixo}[{k}]" if prefixo else str(k)
        if isinstance(v, (dict, list, tuple)):
            out += _achatar(v, chave)
        elif v is not None:
            out.append((chave, "true" if v is True else "false" if v is False else str(v)))
    return out


def _http(metodo, caminho, campos=None, idem=None):
    chave = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not chave:
        raise ErroStripe("Stripe sem chave")
    dados = urllib.parse.urlencode(_achatar(campos)).encode() if campos else None
    req = urllib.request.Request(_base() + caminho, data=dados, method=metodo)
    req.add_header("Authorization", "Bearer " + chave)
    req.add_header("Stripe-Version", "2024-06-20")
    if idem:
        req.add_header("Idempotency-Key", idem)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            msg = (json.load(e).get("error") or {}).get("message") or ""
        except Exception:                                   # noqa: BLE001
            msg = ""
        raise ErroStripe(f"Stripe HTTP {e.code}: {msg[:200]}", codigo=e.code)
    except urllib.error.URLError as e:
        raise ErroStripe(f"sem conexão com o Stripe: {e.reason}")


# ------------------------------------------------------------------ o que dá para comprar
def compravel(p, variacao=None):
    """Preço fechado e em estoque (o produto e a variação escolhida). O resto continua pedido."""
    if not p or not p.get("in_stock"):
        return False
    if p.get("variations"):
        v = variacao or next((x for x in p["variations"] if x.get("in_stock", True) and x.get("price")), None)
        return bool(v and v.get("in_stock", True) and (v.get("price") or p.get("price")))
    return bool(p.get("price"))


def _variacao(p, nome):
    return next((v for v in p.get("variations") or () if " / ".join(v["attrs"]) == nome), None)


def _fl_hoje():
    return datetime.now(FL).date().isoformat()


# ------------------------------------------------------------------ 1. a sessão do Checkout
class PrecisaConta(ValueError):
    """#248 (dono, 14/10): "Para a pessoa conseguir comprar com a gente, ela tem que criar a conta dela lá no
    site da URACE". Comprar pede a conta do site; o e-mail dela vai para o Stripe e para os avisos."""


def locale_stripe(lang):
    return "pt-BR" if lang == "pt" else "en"


def criar_sessao(con, p, variacao_nome, quantidade, entrega, origem, host, foto_url=None, http=None, conta_id=None, lang="en",
                 utm=None):
    """Grava o pedido 'aberto' e cria a sessão do Checkout. Devolve (pedido_id, url do Stripe).
    #248: só com a conta do site (`conta_id`); o e-mail da conta vai como `customer_email`."""
    http = http or _http
    conta = um(con, "SELECT * FROM portal_accounts WHERE id=? AND active=1", (conta_id,)) if conta_id else None
    if not conta:
        raise PrecisaConta("Please sign in or create your URACE account to buy.")
    v = _variacao(p, variacao_nome) if p.get("variations") else None
    if p.get("variations") and not v:
        raise ValueError("Please choose an option.")
    if not compravel(p, v):
        raise ValueError("This item can't be bought online right now. Send us an order request instead.")
    from command_center.providers import loja
    unit = float((v or {}).get("price") or p["price"])
    qtd = max(1, min(20, int(quantidade)))
    entrega = "envio" if entrega == "envio" else "retirada"
    nome = p["name"] + (f" ({variacao_nome})" if v else "")
    # #298: o frete fixo do produto (× quantidade) com "Ship to me" (None: a equipe combina à parte) e o depósito
    frete = loja.frete(p, qtd, entrega)
    deposito = round(float(p.get("deposit") or 0) * qtd, 2)
    oid = inserir(con, "store_orders", product_slug=p["slug"], product_name=p["name"], variation=variacao_nome if v else None,
                  quantity=qtd, unit_price=unit, amount=round(unit * qtd + (frete or 0) + deposito, 2), delivery=entrega,
                  origin=host, account_id=conta["id"], email=(conta["email"] or "").lower() or None, name=conta["name"],
                  phone=conta["phone"], lang="pt" if lang == "pt" else "en",
                  shipping_fee=frete if entrega == "envio" else None, deposit=deposito, utm=utm)
    produto = {"name": nome[:250]}
    if foto_url:
        produto["images"] = [foto_url]
    linhas = [{"quantity": qtd, "price_data": {"currency": "usd", "unit_amount": round(unit * 100), "product_data": produto}}]
    if deposito > 0:
        linhas.append({"quantity": 1, "price_data": {"currency": "usd", "unit_amount": round(deposito * 100),
                                                     "product_data": {"name": f"Refundable security deposit · {nome}"[:250]}}})
    if frete:
        linhas.append({"quantity": 1, "price_data": {"currency": "usd", "unit_amount": round(frete * 100),
                                                     "product_data": {"name": "Shipping"}}})
    campos = {
        "mode": "payment",
        "line_items": linhas,
        "success_url": f"{origem}/store/thanks/?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{origem}/store/cancelled/?p={p['slug']}",
        "client_reference_id": str(oid),
        "metadata": {"pedido": oid, "produto": p["slug"], "entrega": entrega, "frete": f"{frete or 0:.2f}"},
        "payment_intent_data": {"description": f"URACE Store #{oid}: {nome}"[:250], "metadata": {"pedido": oid}},
        "phone_number_collection": {"enabled": True},
        "billing_address_collection": "auto",
        "customer_email": conta["email"],
        "locale": locale_stripe(lang),
    }
    if entrega == "envio":
        campos["shipping_address_collection"] = {"allowed_countries": list(PAISES_ENVIO)}
    try:
        s = http("POST", "/v1/checkout/sessions", campos, idem=f"urace-loja-{oid}")
    except ErroStripe:
        atualizar(con, "store_orders", oid, status="falhou", updated_at=agora())
        raise
    atualizar(con, "store_orders", oid, stripe_session_id=s["id"], stripe_url=s.get("url"), updated_at=agora())
    auditar(con, "store.checkout", "site", entity_type="store_order", entity_id=oid,
            detail={"produto": p["slug"], "variacao": variacao_nome if v else None, "qtd": qtd, "valor": round(unit * qtd, 2),
                    "frete": frete, "deposito": deposito})
    return oid, s.get("url")


# ------------------------------------------------------------------ 2. o webhook
def assinatura_ok(corpo: bytes, cabecalho: str, segredo: str, agora_ts=None) -> bool:
    """Confere o `Stripe-Signature` (t=…,v1=…): HMAC-SHA256 de "t.corpo" com o segredo do endpoint,
    dentro da tolerância de 5 minutos (evento velho reenviado por terceiro não passa)."""
    if not segredo or not cabecalho:
        return False
    partes = [x.split("=", 1) for x in cabecalho.split(",") if "=" in x]
    t = next((v for k, v in partes if k.strip() == "t"), None)
    v1 = [v.strip() for k, v in partes if k.strip() == "v1"]
    if not t or not v1 or not t.isdigit():
        return False
    if abs((agora_ts or time.time()) - int(t)) > TOLERANCIA:
        return False
    esperado = hmac.new(segredo.encode(), t.encode() + b"." + corpo, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(esperado, x) for x in v1)


def _pedido_da_sessao(con, s):
    o = um(con, "SELECT * FROM store_orders WHERE stripe_session_id=?", (s.get("id"),))
    if not o and str(s.get("client_reference_id") or "").isdigit():
        o = um(con, "SELECT * FROM store_orders WHERE id=? AND stripe_session_id IS NULL", (int(s["client_reference_id"]),))
    return o


def _registrar_sessao(con, o, s, status):
    """Grava o que o Stripe disse da sessão. Nunca volta um pedido pago para trás."""
    if o["status"] == "pago":
        return o
    det = s.get("customer_details") or {}
    envio = (s.get("shipping_details") or (s.get("collected_information") or {}).get("shipping_details") or None)
    da_conta = bool(o.get("account_id") and o["email"])      # #248: a conta é a base; o Stripe só completa
    campos = dict(status=status, stripe_session_id=s.get("id") or o["stripe_session_id"],
                  payment_intent=s.get("payment_intent") if isinstance(s.get("payment_intent"), str) else o["payment_intent"],
                  email=(o["email"] if da_conta else (det.get("email") or o["email"] or "")).lower() or None,
                  name=(o["name"] if da_conta and o["name"] else det.get("name") or o["name"]),
                  phone=(o["phone"] if da_conta and o["phone"] else det.get("phone") or o["phone"]), updated_at=agora())
    if envio:
        campos["shipping"] = json.dumps(envio, ensure_ascii=False)
    if s.get("amount_total") is not None:
        campos["amount_paid"] = round(int(s["amount_total"]) / 100, 2)
    if status == "pago":
        campos["paid_at"] = agora()
    atualizar(con, "store_orders", o["id"], **campos)
    return um(con, "SELECT * FROM store_orders WHERE id=?", (o["id"],))


def status_da_sessao(s, tipo="checkout.session.completed", conferindo=False):
    """O estado do pedido para o que o Stripe disse. `conferindo`: a página leu a sessão (sem evento), e a
    sessão ainda aberta ou já vencida diz isso no `status` dela (#245)."""
    if tipo == "checkout.session.expired" or (conferindo and s.get("status") == "expired"):
        return "expirado"
    if conferindo and s.get("status") == "open":
        return "aberto"
    if tipo == "checkout.session.async_payment_failed":
        return "falhou"
    if tipo == "checkout.session.async_payment_succeeded" or s.get("payment_status") in ("paid", "no_payment_required"):
        return "pago"
    return "aguardando"                 # pago por um meio que confirma depois (o Stripe avisa de novo)


TIPOS = ("checkout.session.completed", "checkout.session.async_payment_succeeded",
         "checkout.session.async_payment_failed", "checkout.session.expired")


def receber_evento(con, evento):
    """Um evento já com a assinatura conferida. Devolve (resultado, pedido_id_pago ou None).
    O mesmo `evt_…` duas vezes não faz nada na segunda: o registro do evento e o efeito dele
    entram juntos, numa transação só."""
    import sqlite3
    tipo, s = evento.get("type"), ((evento.get("data") or {}).get("object") or {})
    con.execute("BEGIN IMMEDIATE")
    try:
        try:
            inserir(con, "stripe_events", id=str(evento["id"]), type=str(tipo or "?"))
        except sqlite3.IntegrityError:
            con.execute("ROLLBACK")
            return "duplicado", None
        res = _efeito(con, evento["id"], tipo, s)
        con.execute("COMMIT")
        return res
    except Exception:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise


def _efeito(con, eid, tipo, s):
    if tipo not in TIPOS:
        atualizar_evento(con, eid, None, "ignorado")
        return "ignorado", None
    o = _pedido_da_sessao(con, s)
    if not o:
        atualizar_evento(con, eid, None, "sem pedido")
        return "sem pedido", None
    novo = status_da_sessao(s, tipo)
    era = o["status"]
    o = _registrar_sessao(con, o, s, novo)
    atualizar_evento(con, eid, o["id"], novo)
    if novo == "pago" and era != "pago":
        ligar_e_vender(con, o["id"])
        return "pago", o["id"]
    if novo in ("aguardando", "falhou", "expirado") and o["status"] == novo:      # #245, #248: avisa sempre
        from command_center.providers import pedido_site
        pedido_site.marcar_resultado(con, o, novo)
    return novo, None


def atualizar_evento(con, eid, order_id, resultado):
    con.execute("UPDATE stripe_events SET order_id=?, result=? WHERE id=?", (order_id, resultado, str(eid)))


def conferir_sessao(con, session_id, http=None):
    """A página de obrigado pergunta ao Stripe: se o webhook ainda não chegou e a sessão está paga,
    o pedido entra agora. Devolve (pedido, pago_agora)."""
    o = um(con, "SELECT * FROM store_orders WHERE stripe_session_id=?", (session_id,))
    if not o or o["status"] == "pago" or not ligado():
        return o, False
    s = (http or _http)("GET", f"/v1/checkout/sessions/{urllib.parse.quote(session_id)}")
    novo = status_da_sessao(s, conferindo=True)
    if novo != "pago":
        o = _registrar_sessao(con, o, s, novo if o["status"] == "aberto" else o["status"])
        if o["status"] in ("aguardando", "expirado"):           # #248: o webhook avisa; se ele atrasar, fica na fila
            from command_center.providers import pedido_site
            pedido_site.marcar_resultado(con, o, o["status"])
        return o, False
    con.execute("BEGIN IMMEDIATE")           # o webhook pode chegar no mesmo instante: um só vende
    try:
        atual = um(con, "SELECT status FROM store_orders WHERE id=?", (o["id"],))
        if atual["status"] == "pago":
            con.execute("COMMIT")
            return um(con, "SELECT * FROM store_orders WHERE id=?", (o["id"],)), False
        o = _registrar_sessao(con, o, s, "pago")
        ligar_e_vender(con, o["id"])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return um(con, "SELECT * FROM store_orders WHERE id=?", (o["id"],)), True


# ------------------------------------------------------------------ 3. pago: card, Vendas
def _cliente(con, o):
    """Regra de vínculo do site (#164): o card só é o desta pessoa quando o e-mail E o nome batem.
    E-mail de um card com outro nome (um pai comprando no e-mail do filho, um e-mail da empresa)
    não liga: a equipe decide. Sem card nenhum com esse e-mail, nasce um card novo."""
    from command_center.providers import identidade
    if o.get("account_id"):                          # #248: a conta do site, já ligada pela equipe, diz o card
        c = um(con, """SELECT c.id, c.name FROM portal_accounts a JOIN clients c ON c.id=a.client_id
                        WHERE a.id=? AND c.kind<>?""", (o["account_id"], identidade.SEPARADO))
        if c:
            return c["id"], f"card da conta do site ({c['name']})"
    if not o["email"]:
        return None, "sem e-mail no Checkout: vincular à mão"
    cards = todos(con, "SELECT * FROM clients WHERE email=? AND kind<>?", (o["email"], identidade.SEPARADO))
    batem = [c for c in cards if o["name"] and (identidade.mesmo_nome(o["name"], c["name"]) or
                                                 (c.get("pilot_name") and identidade.mesmo_nome(o["name"], c["pilot_name"])))]
    if len(batem) == 1:
        return batem[0]["id"], f"e-mail e nome batem com o card {batem[0]['name']}"
    if cards:
        return None, (f"o e-mail {o['email']} é do card {cards[0]['name']}, mas o nome no pagamento é {o['name'] or '—'}: "
                      "vincular à mão")
    cid = inserir(con, "clients", name=o["name"] or o["email"], email=o["email"], phone=o["phone"], status="ACTIVE",
                  source="loja")
    return cid, "card criado (ninguém com esse e-mail)"


def descricao(o):
    return o["product_name"] + (f" ({o['variation']})" if o["variation"] else "") + (f" × {o['quantity']}" if o["quantity"] > 1 else "")


def _endereco(o):
    try:
        e = json.loads(o["shipping"] or "null") or {}
    except ValueError:
        return ""
    a = e.get("address") or {}
    linhas = [e.get("name"), a.get("line1"), a.get("line2"),
              " ".join(x for x in (a.get("city"), a.get("state"), a.get("postal_code")) if x), a.get("country")]
    return "\n".join(x for x in linhas if x)


def ligar_e_vender(con, oid):
    """Pedido pago: card do cliente e oportunidade em Vendas (GANHO com card; FECHAMENTO quando o
    vínculo fica para a equipe). Só banco local — rápido, dentro da resposta ao webhook. O e-mail e o
    QuickBooks vêm depois, em `avisar_e_registrar`."""
    o = um(con, "SELECT * FROM store_orders WHERE id=?", (oid,))
    if o["opp_id"]:
        return o["opp_id"]
    if o.get("kind") == "carrinho":                 # #236: várias linhas, sessões da agenda, um card por piloto
        from command_center.providers import carrinho
        return carrinho.pago(con, oid)
    cid, nota = _cliente(con, o)
    valor = o["amount_paid"] if o["amount_paid"] is not None else o["amount"]
    from command_center.providers import pedido_site
    entrega = ("retirada na pista (Orlando Kart Center)" if o["delivery"] == "retirada"
               else pedido_site.texto_envio_equipe(o, pedido_site.linhas(con, o)).replace("ENVIO — ", "envio — "))
    notas = (f"[Loja · pago no Stripe] {descricao(o)} — US$ {valor:,.2f}\nPedido #{o['id']} · {entrega}"
             + (f"\nEndereço:\n{_endereco(o)}" if o["delivery"] == "envio" and o["shipping"] else "")
             + f"\nCard: {nota}")
    opp = inserir(con, "opportunities", name=o["name"] or o["email"] or "Cliente da loja", email=o["email"], phone=o["phone"],
                  service=f"Store: {descricao(o)}", amount=valor, stage="GANHO" if cid else "FECHAMENTO", source="Site",
                  client_id=cid, notes=notas, campaign=o["utm"],
                  closing=json.dumps({"em": agora(), "por": "stripe", "pedido": o["id"]}, ensure_ascii=False))
    inserir(con, "opp_events", opp_id=opp, kind="note", title="Pago na loja do site (Stripe)", detail=notas[:2000],
            at=agora(), actor="site")
    atualizar(con, "store_orders", oid, client_id=cid, link_note=nota, opp_id=opp, updated_at=agora())
    auditar(con, "store.paid", "stripe", entity_type="store_order", entity_id=oid,
            detail={"valor": valor, "opp": opp, "card": cid, "vinculo": nota})
    return opp


# ------------------------------------------------------------------ 4. e-mails e QuickBooks
def _enviar(enviar, para, assunto, texto):
    from command_center.providers import email_envio
    (enviar or email_envio.enviar)(para, assunto, texto)


def avisar(con, oid, enviar=None):
    """A confirmação para quem comprou e o aviso para a equipe separar e entregar. Uma vez só."""
    o = um(con, "SELECT * FROM store_orders WHERE id=?", (oid,))
    if not o or o["status"] != "pago" or o["notified_at"]:
        return False
    if o.get("kind") == "carrinho":
        from command_center.providers import carrinho
        return carrinho.avisar(con, oid, enviar)
    from command_center.providers import pedido_site
    valor = o["amount_paid"] if o["amount_paid"] is not None else o["amount"]
    lang = pedido_site.lingua(o)                        # #248: no idioma em que a pessoa comprou
    pedido_site.registrar_no_card(con, o, "pago")       # #248: o pagamento na linha do tempo do card
    if lang == "pt":
        entrega_cli = ("Avisamos quando estiver pronto para retirar no Orlando Kart Center (10724 Cosmonaut Blvd, Box 3, "
                       "Orlando, FL 32824)." if o["delivery"] == "retirada" else
                       pedido_site.texto_envio(o, pedido_site.linhas(con, o), lang))
        assunto = f"Pedido #{o['id']} confirmado — URACE Store"
        texto = (f"{pedido_site.ola(o, lang)},\n\nObrigado pelo pedido! Recebemos o seu pagamento.\n\n{descricao(o)}\n"
                 f"Total pago: US$ {valor:,.2f}\nPedido: #{o['id']}\n\n{entrega_cli}\n\nPágina do seu pedido: {pedido_site.link(o)}\n\n"
                 f"{pedido_site.contato(lang)}\n\nURACE — the Champion's Factory")
    else:
        entrega_cli = ("We'll let you know when it's ready for pickup at the Orlando Kart Center (10724 Cosmonaut Blvd, Box 3, "
                       "Orlando, FL 32824)." if o["delivery"] == "retirada" else
                       pedido_site.texto_envio(o, pedido_site.linhas(con, o), lang))
        assunto = f"Order #{o['id']} confirmed — URACE Store"
        texto = (f"{pedido_site.ola(o, lang)},\n\nThanks for your order! We received your payment.\n\n{descricao(o)}\nTotal paid: "
                 f"US$ {valor:,.2f}\nOrder: #{o['id']}\n\n{entrega_cli}\n\nYour order page: {pedido_site.link(o)}\n\n"
                 f"Questions? Call or WhatsApp +1 (407) 250 2291.\n\nURACE — the Champion's Factory")
    try:
        if o["email"]:
            _enviar(enviar, o["email"], assunto, texto)
        _enviar(enviar, "support@urace.us", f"Loja · PAGO: {descricao(o)} — {o['name'] or o['email']}",
                f"Pedido #{o['id']} pago no Stripe: US$ {valor:,.2f}\n{descricao(o)}\n{o['name'] or ''} <{o['email'] or ''}> "
                f"{o['phone'] or ''}\nEntrega: {'retirada na pista' if o['delivery'] == 'retirada' else pedido_site.texto_envio_equipe(o, pedido_site.linhas(con, o))}\n"
                + (f"Endereço:\n{_endereco(o)}\n" if o["shipping"] else "")
                + f"Card: {o['link_note'] or '—'}\n\nSeparar e entregar. Vendas: https://ops.urace.us/ops/sales/{o['opp_id']}"
                + f"\nPágina do pedido: {pedido_site.link(o)}")
        atualizar(con, "store_orders", oid, notified_at=agora(), notify_error=None, updated_at=agora())
        pedido_site.avisado_pago(con, o, o["email"])
        return True
    except Exception as e:                              # noqa: BLE001 — o pedido já está pago e em Vendas
        atualizar(con, "store_orders", oid, notify_error=str(e)[:300], updated_at=agora())
        return False


def _qbo():
    from command_center import providers
    return providers.modulo("quickbooks")


def registrar_qbo(con, oid, qbo=None):
    """Sales Receipt no QuickBooks: o cliente (o do card, pelo e-mail; senão criado), o item do
    produto e o valor pago. Número WEB-<pedido>: rodar de novo devolve o mesmo recibo."""
    o = um(con, "SELECT * FROM store_orders WHERE id=?", (oid,))
    if not o or o["status"] != "pago" or o["qbo_receipt_id"]:
        return None
    try:
        q = qbo or _qbo()
        cliente = o["qbo_customer_id"]
        if not cliente:
            achados = [x for x in (q.qbo_clientes_buscar(o["email"]) if o["email"] else [])
                       if (x.get("email") or "") == (o["email"] or "").lower()]
            if achados:
                cliente = achados[0]["id"]
            else:
                from command_center.providers.mensalidades import _aplicando
                novo = _aplicando(q.qbo_criar_cliente, nome=o["name"] or o["email"], email=o["email"], telefone=o["phone"])
                cliente = (novo or {}).get("id")
            if not cliente:
                raise RuntimeError("o QuickBooks não devolveu o cliente")
            atualizar(con, "store_orders", oid, qbo_customer_id=str(cliente))
        valor = o["amount_paid"] if o["amount_paid"] is not None else o["amount"]
        memo = f"URACE Store #{o['id']} — pago no Stripe ({o['payment_intent'] or o['stripe_session_id']})"
        if o.get("kind") == "carrinho":             # #236: uma linha por item, e o depósito no item dele
            from command_center.providers import carrinho
            linhas = carrinho.linhas_qbo(con, q, oid)
            memo = f"URACE order #{o['id']} (site cart) — pago no Stripe ({o['payment_intent'] or o['stripe_session_id']})"
        else:
            item = q.item_loja_sistema(o["product_name"], o["unit_price"], f"URACE Store: {o['product_name']}")
            extra = [(carrinho_item_deposito(con), o["deposit"], "Refundable security deposit")] if o.get("deposit") else []
            if o.get("shipping_fee"):                       # #298: o frete fixo do produto, no item "Shipping"
                from command_center.providers import carrinho
                extra.append((carrinho.item_frete(q), o["shipping_fee"], f"Shipping: {descricao(o)}"))
            resto = round(valor - sum(v for _, v, _ in extra), 2)
            linhas = [{"item_id": item["id"], "quantidade": o["quantity"], "unitario": round(resto / o["quantity"], 2),
                       "descricao": descricao(o)}] + [{"item_id": i, "quantidade": 1, "unitario": v, "descricao": d}
                                                      for i, v, d in extra]
        r = q.recibo_venda_sistema(cliente_id=cliente, linhas=linhas, memo=memo, data=(o["paid_at"] or agora())[:10],
                                   numero=f"WEB-{o['id']:05d}", email=o["email"])
        atualizar(con, "store_orders", oid, qbo_receipt_id=str(r.get("id") or ""), qbo_receipt_doc=r.get("numero"),
                  qbo_error=None, updated_at=agora())
        for opp in _opps(con, o):
            inserir(con, "opp_events", opp_id=opp, kind="invoice", title=f"Sales Receipt {r.get('numero')} no QuickBooks",
                    detail=r.get("link"), at=agora(), actor="site", ok=1)
        return r
    except Exception as e:                              # noqa: BLE001 — pago está; o financeiro vê o erro
        atualizar(con, "store_orders", oid, qbo_error=str(e)[:300], updated_at=agora())
        for opp in _opps(con, o):
            inserir(con, "opp_events", opp_id=opp, kind="invoice", title="QuickBooks: registrar a venda à mão",
                    detail=str(e)[:300], at=agora(), actor="site", ok=0)
        return None


def carrinho_item_deposito(con):
    from command_center.providers import carrinho
    return carrinho._item_deposito(con)


def _opps(con, o):
    """As oportunidades do pedido: uma (#174), ou uma por card no carrinho (#236)."""
    ids = [x["opp_id"] for x in todos(con, "SELECT DISTINCT opp_id FROM store_order_items WHERE order_id=? AND opp_id IS NOT NULL",
                                      (o["id"],))]
    return ids or ([o["opp_id"]] if o["opp_id"] else [])


def avisar_e_registrar(oid, enviar=None, qbo=None):
    """Depois da resposta ao Stripe (tarefa em segundo plano): e-mails e QuickBooks."""
    from command_center.db import conectar
    con = conectar()
    try:
        o = um(con, "SELECT kind FROM store_orders WHERE id=?", (oid,))
        if o and o["kind"] == "carrinho":           # #236: a waiver de cada sessão, e a sessão no Asana (#67)
            from command_center.providers import agenda_asana, carrinho
            for bid in carrinho.seguir_sessoes(con, oid):
                con.commit()
                agenda_asana.levar(bid)
            con.commit()
        avisar(con, oid, enviar)
        registrar_qbo(con, oid, qbo)
    finally:
        con.close()


def rodar(con, enviar=None, qbo=None):
    """Na rotina de 15 min: pago que ainda não avisou ou não foi para o QuickBooks tenta de novo
    (QuickBooks fora do ar, e-mail que falhou). Pedido pago há menos de 2 min fica para a tarefa
    que o webhook já disparou."""
    feitos = {"avisados": 0, "qbo": 0}
    for o in todos(con, "SELECT id FROM store_orders WHERE status='pago' AND (notified_at IS NULL OR qbo_receipt_id IS NULL) "
                        "AND paid_at < strftime('%Y-%m-%dT%H:%M:%fZ','now','-2 minutes') ORDER BY id LIMIT 20"):
        feitos["avisados"] += bool(avisar(con, o["id"], enviar))
        feitos["qbo"] += bool(registrar_qbo(con, o["id"], qbo))
    return feitos

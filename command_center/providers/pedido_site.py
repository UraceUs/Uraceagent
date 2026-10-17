"""A página de cada pedido do site e o aviso de cada resultado do pagamento (#245).

Dono, 14/10, sobre os 4 eventos do webhook do Stripe (`checkout.session.completed`,
`checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`,
`checkout.session.expired`): *"monte páginas para cada um no site"*.

Cada pedido (o carrinho, #236, e a loja de um produto, #174) tem um link pessoal, `/order/<token>/`:
o token é o número do pedido com um selo HMAC (chave em `~/.urace/pedidos.key`, fora do repositório,
criada na primeira vez). Sem o selo certo, 404. A página mostra o estado que o Stripe deu:

  completed + pago        → "Payment confirmed" (itens, total, depósito, o que vem a seguir)
  completed + aguardando  → "Payment processing" (não pague de novo; e-mail quando confirmar)
  async_payment_succeeded → "Payment confirmed" e a confirmação por e-mail (a mesma do pago, uma vez só)
  async_payment_failed    → "Payment didn't go through" e o botão "Try again"
  expired                 → "Checkout expired" e o botão "Restore cart"

"Try again" e "Restore cart" remontam o carrinho com as MESMAS escolhas (produto, opção e
quantidade; serviço, dia, turno e piloto) e o servidor recalcula preço, depósito e vaga, como em
qualquer carrinho. A vaga nunca fica presa: a sessão só vira agendamento quando o pagamento entra.

#248 (dono, 14/10): "o cliente e a equipe precisam da confirmação de pagamento sempre e deixar isso
também registrado no card do cliente no Command Center". Em TODO resultado (pago, aguardando, falhou,
expirado): e-mail para o cliente (no idioma em que ele comprou, `store_orders.lang`), aviso para a
equipe e um registro na linha do tempo do card (`client_events`), um por resultado por pedido
(`store_order_notices`, tomado antes de mandar). A conta do site é obrigatória para comprar: o e-mail
dos avisos é o da conta, e a página mostra os dados do cliente da conta.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets

from command_center.db import agora, atualizar, conectar, inserir, todos, um  # noqa: F401

ESTADOS = ("pago", "aguardando", "falhou", "expirado", "aberto")
CONTATO = "Questions? Call or WhatsApp +1 (407) 250 2291."
ASSINATURA = "URACE — the Champion's Factory"


# ------------------------------------------------------------------ o link pessoal
def _pasta():
    return os.environ.get("URACE_DIR") or os.path.expanduser("~/.urace")


def _chave():
    """32 bytes aleatórios, criados na primeira vez e só legíveis pelo serviço. Nunca no repositório.
    Perdida, os links antigos deixam de abrir (a equipe manda o novo pelo painel); nada mais depende dela."""
    pasta = _pasta()
    os.makedirs(pasta, mode=0o700, exist_ok=True)
    caminho = os.path.join(pasta, "pedidos.key")
    try:
        with open(caminho, "rb") as f:
            k = f.read()
    except FileNotFoundError:
        k = secrets.token_bytes(32)
        try:
            fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:                       # outro processo criou agora: vale a dele
            with open(caminho, "rb") as f:
                k = f.read()
        else:
            with os.fdopen(fd, "wb") as f:
                f.write(k)
    if len(k) < 32:
        raise RuntimeError("chave dos links de pedido corrompida")
    return k


def _selo(o):
    msg = f"pedido-site|{o['id']}|{o['created_at']}".encode()
    return base64.urlsafe_b64encode(hmac.new(_chave(), msg, hashlib.sha256).digest()).decode().rstrip("=")[:27]


def token(o):
    return f"{o['id']}-{_selo(o)}"


def achar(con, tok):
    """O pedido deste token, ou None (token mexido, de outro pedido ou inventado)."""
    m = re.fullmatch(r"([1-9][0-9]{0,9})-([A-Za-z0-9_-]{27})", tok or "")
    if not m:
        return None
    o = um(con, "SELECT * FROM store_orders WHERE id=?", (int(m.group(1)),))
    if not o or not hmac.compare_digest(_selo(o), m.group(2)):
        return None
    return o


def caminho(o):
    return f"/order/{token(o)}/"


def _host_do_site(o):
    h = (o.get("origin") or "").strip().lower()
    if re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,252}", h):
        return h
    hosts = [x.strip().lower() for x in os.environ.get("CC_SITE_HOSTS", "novo.urace.us").split(",") if x.strip()]
    return hosts[0] if hosts else "novo.urace.us"


def link(o):
    """O endereço completo que vai no e-mail e no painel (o site em que a pessoa comprou)."""
    return f"https://{_host_do_site(o)}{caminho(o)}"


# ------------------------------------------------------------------ o que o pedido tem
def linhas(con, o):
    """As linhas do pedido: as do carrinho (#236) ou a linha única da loja (#174), no mesmo formato."""
    if o["kind"] == "carrinho":
        return todos(con, "SELECT * FROM store_order_items WHERE order_id=? ORDER BY id", (o["id"],))
    nome = o["product_name"] + (f" ({o['variation']})" if o["variation"] else "")
    return [{"id": None, "kind": "produto", "name": nome, "quantity": o["quantity"], "unit_price": o["unit_price"],
             "deposit": o.get("deposit") or 0, "amount": o["amount"], "product_slug": o["product_slug"], "variation": o["variation"],
             "shipping": o.get("shipping_fee"),          # #298: o frete do "Buy now" (None: combinado à parte)
             "service_id": None, "service_name": None, "date": None, "period": None, "pilot_id": None,
             "pilot_name": None, "status": None, "booking_id": None, "client_id": o["client_id"], "note": None}]


# ------------------------------------------------------------------ o frete (#298)
def frete(o, ls):
    """(cobrado, a combinar): o frete que entrou no pagamento e os produtos com o frete combinado à parte (o
    produto sem frete no painel, ou o pedido de antes do #298). Retirada na pista: (0, [])."""
    if o["delivery"] != "envio":
        return 0.0, []
    falta = [x["name"] for x in ls if x["kind"] == "produto" and x.get("shipping") is None]
    return float(o.get("shipping_fee") or 0), falta


def texto_envio(o, ls, lang="en"):
    """A frase do envio para o cliente (e-mail e página do pedido)."""
    cobrado, falta = frete(o, ls)
    pt = lang == "pt"
    if falta and not cobrado:
        return ("Confirmamos o valor do frete e mandamos o código de rastreio. O frete é cobrado à parte." if pt else
                "We'll confirm the shipping cost and send you the tracking number. Shipping is billed separately.")
    if falta:
        nomes = ", ".join(falta)
        return (f"O frete de {_usd(cobrado)} já entrou no pagamento. O de {nomes} confirmamos e cobramos à parte. "
                "Mandamos o código de rastreio por e-mail." if pt else
                f"Shipping of {_usd(cobrado)} is included in your payment. We'll confirm the shipping of {nomes} and bill it "
                "separately. We'll email you the tracking number.")
    if cobrado:
        return (f"O frete ({_usd(cobrado)}) já entrou no pagamento. Mandamos o código de rastreio por e-mail." if pt else
                f"Shipping ({_usd(cobrado)}) is included in your payment. We'll email you the tracking number.")
    return ("Frete grátis. Mandamos o código de rastreio por e-mail." if pt else
            "Free shipping. We'll email you the tracking number.")


def texto_envio_equipe(o, ls):
    """O que a equipe lê sobre o envio (aviso, nota da venda)."""
    cobrado, falta = frete(o, ls)
    partes = [f"frete {_usd(cobrado)} cobrado no pedido"] if cobrado else []
    if falta:
        todos_sem = not cobrado and len(falta) == sum(1 for x in ls if x["kind"] == "produto")
        partes.append("combinar o frete" if todos_sem else "combinar o frete de: " + ", ".join(falta))
    return "ENVIO — " + ("; ".join(partes) or "frete grátis")


def itens_do_carrinho(con, o):
    """As escolhas do pedido, no formato do carrinho do navegador (nunca preço: o servidor recalcula)."""
    out = []
    for x in linhas(con, o):
        if x["kind"] == "produto" and x["product_slug"]:
            out.append({"tipo": "produto", "produto": x["product_slug"], "variacao": x["variation"] or "",
                        "quantidade": x["quantity"]})
        elif x["kind"] == "sessao" and x["service_id"]:
            out.append({"tipo": "sessao", "servico": x["service_id"], "data": x["date"], "turno": x["period"],
                        "piloto": x["pilot_id"]})
    return out


def tem_sessao(con, o):
    return any(x["kind"] == "sessao" for x in linhas(con, o))


def refeito(con, o):
    """O pedido novo que saiu do "Try again"/"Restore cart" deste e já foi pago (ou está confirmando)."""
    return um(con, "SELECT * FROM store_orders WHERE retry_of=? AND status IN ('pago','aguardando') ORDER BY id DESC LIMIT 1",
              (o["id"],))


# ------------------------------------------------------------------ em inglês ou português (#248)
DIAS_PT = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
MESES_PT = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
TURNO = {"en": {"manha": "morning", "tarde": "afternoon", "dia": "full day"},
         "pt": {"manha": "manhã", "tarde": "tarde", "dia": "dia todo"}}


def lingua(o):
    return "pt" if (o.get("lang") or "") == "pt" else "en"


def quando(d, periodo, lang="en"):
    """'Sat, Oct 18, 2026 (morning)' ou 'sáb, 18 de out de 2026 (manhã)'."""
    from datetime import date
    try:
        dia = date.fromisoformat(d)
    except (TypeError, ValueError):
        return str(d or "")
    turno = TURNO["pt" if lang == "pt" else "en"].get(periodo, periodo or "")
    if lang == "pt":
        return f"{DIAS_PT[dia.weekday()]}, {dia.day} de {MESES_PT[dia.month - 1]} de {dia.year} ({turno})"
    return dia.strftime("%a, %b %d, %Y").replace(" 0", " ") + f" ({turno})"


def nome_linha(x, lang="en"):
    """O nome da linha no idioma: a sessão é refeita com o dia e o turno (o nome guardado é o do Stripe)."""
    if x["kind"] == "sessao" and x.get("service_name") and x.get("date"):
        return f"{x['service_name']} · {quando(x['date'], x['period'], lang)}" + (f" · {x['pilot_name']}" if x.get("pilot_name") else "")
    return x["name"]


def _usd(n):
    return f"US$ {n:,.2f}"


def texto_itens(ls, lang="en"):
    dep = "Refundable security deposit" if lang != "pt" else "Depósito de segurança reembolsável"
    out = []
    for x in ls:
        s = f"- {nome_linha(x, lang)}" + (f" × {x['quantity']}" if x["quantity"] > 1 else "") + f": {_usd(x['unit_price'] * x['quantity'])}"
        if x["deposit"]:
            s += f"\n  {dep}: {_usd(x['deposit'])}"
        if x.get("shipping"):                                # #298: o frete fixo da linha
            s += f"\n  {'Frete' if lang == 'pt' else 'Shipping'}: {_usd(x['shipping'])}"
        out.append(s)
    return "\n".join(out)


def contato(lang):
    return ("Dúvidas? Ligue ou mande WhatsApp para +1 (407) 250 2291." if lang == "pt" else CONTATO)


def primeiro_nome(o, lang="en"):
    return (o["name"] or "").split()[0] if o["name"] else ("olá" if lang == "pt" else "there")


def ola(o, lang):
    return f"Olá, {primeiro_nome(o, lang)}" if lang == "pt" else f"Hi {primeiro_nome(o, lang)}"


# ------------------------------------------------------------------ quem comprou (#248)
def conta(con, o):
    return um(con, "SELECT * FROM portal_accounts WHERE id=?", (o["account_id"],)) if o.get("account_id") else None


def endereco_entrega(o):
    try:
        s = json.loads(o["shipping"] or "null") or {}
    except ValueError:
        return ""
    a = s.get("address") or {}
    partes = [s.get("name"), a.get("line1"), a.get("line2"),
              " ".join(x for x in (a.get("city"), a.get("state"), a.get("postal_code")) if x), a.get("country")]
    return ", ".join(x for x in partes if x)


def cliente(con, o, ls=None):
    """Os dados do cliente para a página do pedido (dono, 14/10: "mostre todas as informações do cliente
    ali"): os da conta do site; sem conta (pedido antigo), os que o Stripe deu."""
    c = conta(con, o)
    ls = ls if ls is not None else linhas(con, o)
    end = ""
    if c:
        end = ", ".join(x for x in (c.get("address_line1"), c.get("address_line2"),
                                     " ".join(y for y in (c.get("city"), c.get("state"), c.get("zip")) if y)) if x)
    return {"nome": (c or {}).get("name") or o["name"], "email": (c or {}).get("email") or o["email"],
            "telefone": (c or {}).get("phone") or o["phone"], "endereco": end,
            "pilotos": sorted({x["pilot_name"] for x in ls if x.get("pilot_name")}),
            "entrega": o["delivery"], "endereco_entrega": endereco_entrega(o),
            "tem_produto": any(x["kind"] == "produto" for x in ls)}


# ------------------------------------------------------------------ o resultado que o Stripe deu (#245, #248)
RESULTADOS = ("pago", "aguardando", "falhou", "expirado")
NOME_EQUIPE = {"pago": "PAGO", "aguardando": "PROCESSANDO O PAGAMENTO", "falhou": "PAGAMENTO FALHOU",
               "expirado": "CHECKOUT EXPIROU"}
NOME_CARD = {"pago": "pago", "aguardando": "processando o pagamento", "falhou": "pagamento não passou",
             "expirado": "checkout expirou"}


def marcar_resultado(con, o, resultado):
    """Este pedido chegou a este resultado: o aviso fica na fila (um por resultado por pedido). Dentro da
    transação do webhook; o evento repetido nem chega aqui, e o mesmo resultado de novo não faz nada."""
    if resultado in RESULTADOS:
        con.execute("INSERT OR IGNORE INTO store_order_notices (order_id, result) VALUES (?, ?)", (o["id"], resultado))


def textos(con, o, resultado):
    """(assunto, texto) do e-mail para a pessoa, no idioma em que ela comprou. Aguardando, falhou, expirou
    (o do pago é o de `stripe_loja.avisar` / `carrinho.avisar`)."""
    lang = lingua(o)
    ls = linhas(con, o)
    sessao = any(x["kind"] == "sessao" for x in ls)
    itens = texto_itens(ls, lang)
    n = o["id"]
    if lang == "pt":
        nada = "nada foi cobrado" + (" e nenhuma sessão foi reservada" if sessao else "")
        fim = f"Página do seu pedido: {link(o)}\n\n{contato(lang)}\n\n{ASSINATURA}"
        if resultado == "aguardando":
            return (f"Estamos confirmando o seu pagamento — pedido #{n} — URACE",
                    f"{ola(o, lang)},\n\nObrigado pelo pedido #{n}. O seu meio de pagamento leva um pouco mais para confirmar "
                    f"(por exemplo, uma transferência bancária). Não pague de novo: mandamos um e-mail assim que ele for "
                    f"confirmado.\n\n{itens}\nTotal: {_usd(o['amount'])}\n\n"
                    + ("Os horários das sessões são reservados quando o pagamento for confirmado.\n\n" if sessao else "") + fim)
        if resultado == "falhou":
            return (f"O pagamento não foi concluído — pedido #{n} — URACE",
                    f"{ola(o, lang)},\n\nO pagamento do seu pedido #{n} na URACE não foi concluído, então {nada}.\n\n{itens}\n\n"
                    f"Você pode tentar de novo com os mesmos itens. Preços e disponibilidade são conferidos de novo:\n{link(o)}\n\n"
                    f"{contato(lang)}\n\n{ASSINATURA}")
        return (f"O seu checkout expirou — pedido #{n} — URACE",
                f"{ola(o, lang)},\n\nO checkout seguro do pedido #{n} na URACE fechou antes de o pagamento ser concluído, então "
                f"{nada}.\n\n{itens}\n\nOs seus itens estão guardados. Restaure o carrinho aqui (preços e disponibilidade são "
                f"conferidos de novo):\n{link(o)}\n\n{contato(lang)}\n\n{ASSINATURA}")
    nada = "nothing was charged" + (" and no session was booked" if sessao else "")
    if resultado == "aguardando":
        return (f"We're confirming your payment — order #{n} — URACE",
                f"{ola(o, lang)},\n\nThanks for your order #{n}. Your payment method takes a little longer to confirm (for "
                f"example, a bank transfer). Please don't pay again: we'll email you as soon as it's confirmed.\n\n{itens}\n"
                f"Total: {_usd(o['amount'])}\n\n"
                + ("Session times are booked when the payment clears.\n\n" if sessao else "")
                + f"Your order page: {link(o)}\n\n{CONTATO}\n\n{ASSINATURA}")
    if resultado == "falhou":
        return (f"Payment didn't go through — order #{n} — URACE",
                f"{ola(o, lang)},\n\nThe payment for your URACE order #{n} didn't go through, so {nada}.\n\n"
                f"{itens}\n\nYou can try again with the same items. Prices and availability are checked again "
                f"when you do:\n{link(o)}\n\n{CONTATO}\n\n{ASSINATURA}")
    return (f"Your checkout expired — order #{n} — URACE",
            f"{ola(o, lang)},\n\nYour secure checkout for URACE order #{n} closed before the payment was finished, "
            f"so {nada}.\n\n{itens}\n\nYour items are saved. Restore your cart here (prices and availability are "
            f"checked again):\n{link(o)}\n\n{CONTATO}\n\n{ASSINATURA}")


def _enviar(enviar, para, assunto, texto):
    from command_center.providers import email_envio
    (enviar or email_envio.enviar)(para, assunto, texto)


def texto_equipe(con, o, resultado):
    """O aviso para support@ (em português, como os outros avisos), com o link da página do pedido."""
    ls = linhas(con, o)
    cli = cliente(con, o, ls)
    o_que = {"aguardando": "o meio de pagamento confirma depois (ex.: transferência). Nada foi marcado ainda; a vaga "
                           "não está presa. O cliente recebeu o aviso de que estamos confirmando.",
             "falhou": "o pagamento que confirmava depois não passou. Nada foi cobrado e nenhuma sessão foi marcada; a "
                       "vaga continua livre. O cliente recebeu o e-mail com o botão Try again.",
             "expirado": "o checkout fechou antes do pagamento. Nada foi cobrado. O cliente recebeu o e-mail com o botão "
                         "Restore cart."}[resultado]
    if not cli["email"]:
        o_que += " ATENÇÃO: sem e-mail do cliente, ligue para ele."
    return (f"Site · {NOME_EQUIPE[resultado]}: pedido #{o['id']} — {cli['nome'] or cli['email'] or 'sem nome'}",
            f"Pedido #{o['id']}: {o_que}\n{cli['nome'] or ''} <{cli['email'] or ''}> {cli['telefone'] or ''}\n\n"
            f"{texto_itens(ls, 'pt')}\nTotal: {_usd(o['amount'])}\n\nPágina do pedido (para mandar ao cliente): {link(o)}")


def avisar_resultado(con, oid, resultado, enviar=None):
    """O aviso de um resultado que não é o pago: e-mail para o cliente (no idioma dele), aviso para a equipe
    e o registro no card. Uma vez só: o aviso é tomado antes de mandar; se o envio falha, ele é solto e a
    rodada de 15 min tenta de novo."""
    n = um(con, "SELECT * FROM store_order_notices WHERE order_id=? AND result=?", (oid, resultado))
    o = um(con, "SELECT * FROM store_orders WHERE id=?", (oid,))
    if not n or not o or n["sent_at"] or resultado == "pago":
        return False
    cur = con.execute("UPDATE store_order_notices SET claimed_at=? WHERE id=? AND sent_at IS NULL AND "
                      "(claimed_at IS NULL OR claimed_at < strftime('%Y-%m-%dT%H:%M:%fZ','now','-10 minutes'))", (agora(), n["id"]))
    con.commit()
    if cur.rowcount != 1:
        return False                                    # outra tarefa tomou este aviso agora
    registrar_no_card(con, o, resultado)
    para = cliente(con, o)["email"]
    try:
        if para:
            assunto, texto = textos(con, o, resultado)
            _enviar(enviar, para, assunto, texto)
        _enviar(enviar, "support@urace.us", *texto_equipe(con, o, resultado))
        con.execute("UPDATE store_order_notices SET sent_at=?, to_email=?, error=NULL WHERE id=?", (agora(), para, n["id"]))
        con.commit()
        return True
    except Exception as e:                              # noqa: BLE001 — a rodada de 15 min tenta de novo
        con.execute("UPDATE store_order_notices SET claimed_at=NULL, error=? WHERE id=?", (str(e)[:300], n["id"]))
        con.commit()
        return False


def avisado_pago(con, o, para):
    """O pago avisa por `stripe_loja.avisar`/`carrinho.avisar`; aqui só fica anotado (o painel mostra)."""
    con.execute("INSERT OR IGNORE INTO store_order_notices (order_id, result) VALUES (?, 'pago')", (o["id"],))
    con.execute("UPDATE store_order_notices SET sent_at=COALESCE(sent_at, ?), to_email=?, error=NULL WHERE order_id=? AND result='pago'",
                (agora(), para, o["id"]))


def avisar_resultado_bg(oid, resultado, enviar=None):
    """Depois da resposta ao Stripe (tarefa em segundo plano)."""
    con = conectar()
    try:
        avisar_resultado(con, oid, resultado, enviar)
    finally:
        con.close()


def rodar(con, enviar=None):
    """Na rotina de 15 min: aviso que não saiu (e-mail fora do ar) tenta de novo. O que chegou há menos de
    2 min fica para a tarefa que o webhook já disparou."""
    n = 0
    for x in todos(con, "SELECT order_id, result FROM store_order_notices WHERE sent_at IS NULL AND result<>'pago' "
                        "AND created_at < strftime('%Y-%m-%dT%H:%M:%fZ','now','-2 minutes') ORDER BY id LIMIT 20"):
        n += bool(avisar_resultado(con, x["order_id"], x["result"], enviar))
    return {"avisos": n}


# ------------------------------------------------------------------ o registro no card (#248)
def _cards(con, o, ls):
    """Card → as linhas dele. A sessão vai para o card do PILOTO (o da linha, ou o que o piloto da conta já
    tem); o produto, para o card da compra (o da linha/pedido, ou o card ligado à conta do site). Sem card
    certo, a linha fica de fora: nunca no card de outro cliente."""
    grupos = {}
    acc = conta(con, o)
    for x in ls:
        cid = x.get("client_id")
        if not cid and x["kind"] == "sessao" and x.get("pilot_id") and o.get("account_id"):
            p = um(con, "SELECT client_id FROM portal_pilots WHERE id=? AND account_id=?", (x["pilot_id"], o["account_id"]))
            cid = p and p["client_id"]
        if not cid and x["kind"] == "produto":
            cid = o.get("client_id") or (acc or {}).get("client_id")
        if cid and um(con, "SELECT 1 AS x FROM clients WHERE id=?", (cid,)):
            grupos.setdefault(cid, []).append(x)
    return grupos


def registrar_no_card(con, o, resultado):
    """A linha do tempo do card (Client360) ganha o resultado do pagamento: valor, o que é e o link da
    página do pedido. Um registro por card, pedido e resultado."""
    o = um(con, "SELECT * FROM store_orders WHERE id=?", (o["id"],))
    ls = linhas(con, o)
    feitos = 0
    for cid, minhas in _cards(con, o, ls).items():
        valor = round(sum((x["amount"] if x["amount"] is not None else x["unit_price"] * x["quantity"]) for x in minhas), 2)
        titulo = f"Pagamento no site: {NOME_CARD[resultado]} · pedido #{o['id']}"
        detalhe = (f"{_usd(valor)} · " + "; ".join(nome_linha(x, 'pt') + (f" × {x['quantity']}" if x["quantity"] > 1 else "")
                                                   for x in minhas))
        if len(minhas) < len(ls):
            detalhe += f" (pedido inteiro: {_usd(o['amount_paid'] if o['amount_paid'] is not None else o['amount'])})"
        cur = con.execute("INSERT OR IGNORE INTO client_events (client_id, at, kind, title, status, detail, link, order_id, result) "
                          "VALUES (?, ?, 'SITE_PAYMENT', ?, ?, ?, ?, ?, ?)",
                          (cid, agora(), titulo, resultado, detalhe[:600], link(o), o["id"], resultado))
        feitos += cur.rowcount
    return feitos


# ------------------------------------------------------------------ o painel
def _avisos(con, o):
    return {x["result"]: {"em": x["sent_at"], "para": x["to_email"], "erro": x["error"]}
            for x in todos(con, "SELECT * FROM store_order_notices WHERE order_id=?", (o["id"],))}


def para_painel(con, o):
    """O que a equipe vê de um pedido: estado, quem, o quê, e o link da página para mandar ao cliente."""
    from command_center.providers import estoque_site
    ls = linhas(con, o)
    avisos = _avisos(con, o)
    atual = avisos.get(o["status"]) or {}
    return {"sem_estoque": bool(estoque_site.pendentes(con, o)),
            "estoque": [{"linha": n, "nota": t} for n, t in estoque_site.baixas(con, o)], "id": o["id"], "tipo": o["kind"], "status": o["status"], "total": o["amount"], "pago": o["amount_paid"],
            "criado_em": o["created_at"], "pago_em": o["paid_at"], "nome": o["name"], "email": o["email"], "telefone": o["phone"],
            "resumo": "; ".join(x["name"] + (f" × {x['quantity']}" if x["quantity"] > 1 else "") for x in ls)[:300],
            "opp_id": o["opp_id"], "atencao": o["attention"], "aviso_em": atual.get("em") or (o["notified_at"] if o["status"] == "pago" else None),
            "aviso_para": atual.get("para"), "aviso_erro": atual.get("erro") or (o["notify_error"] if o["status"] == "pago" else None),
            "avisos": avisos, "refeito_de": o["retry_of"], "idioma": lingua(o), "conta": o["account_id"],
            "link": link(o), "caminho": caminho(o)}


def lista(con, status=None, limit=50, offset=0):
    onde, p = "", []
    if status in ESTADOS:
        onde, p = " WHERE status=?", [status]
    total = um(con, f"SELECT COUNT(*) AS n FROM store_orders{onde}", p)["n"]
    linhas_ = todos(con, f"SELECT * FROM store_orders{onde} ORDER BY id DESC LIMIT ? OFFSET ?",
                    p + [max(1, min(int(limit), 200)), max(0, int(offset))])
    return {"pedidos": [para_painel(con, o) for o in linhas_], "total": total}

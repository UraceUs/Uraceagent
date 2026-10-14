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

Falhou ou expirou, a pessoa fica sabendo por e-mail (expirado só se ela chegou a informar o e-mail
no Checkout), com o link da página; a equipe recebe o aviso do falhou. Um aviso por pedido, nunca
dois: `outcome_notified_at` é tomado antes de mandar.
"""
import base64
import hashlib
import hmac
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
             "deposit": 0, "amount": o["amount"], "product_slug": o["product_slug"], "variation": o["variation"],
             "service_id": None, "service_name": None, "date": None, "period": None, "pilot_id": None,
             "pilot_name": None, "status": None, "booking_id": None, "client_id": o["client_id"], "note": None}]


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


# ------------------------------------------------------------------ o resultado que o webhook trouxe
def marcar_resultado(con, o, s, novo):
    """Falhou ou expirou: guarda para quem vai o aviso. Dentro da transação do webhook (o evento repetido
    nem chega aqui). Falhou: o e-mail do Checkout ou o da conta. Expirou: só o que a pessoa informou no
    Checkout (`customer_details.email`); sem ele, ninguém recebe nada."""
    if o["outcome"] or o["outcome_notified_at"]:
        return
    det = (s.get("customer_details") or {}).get("email") or ""
    para = det.strip().lower() or None
    if novo == "falhou":
        para = para or (o["email"] or None)
    atualizar(con, "store_orders", o["id"], outcome=novo, outcome_email=para, updated_at=agora())


def _primeiro(o):
    return (o["name"] or "").split()[0] if o["name"] else "there"


def _usd(n):
    return f"US$ {n:,.2f}"


def _texto_itens(ls):
    out = []
    for x in ls:
        s = f"- {x['name']}" + (f" × {x['quantity']}" if x["quantity"] > 1 else "") + f": {_usd(x['unit_price'] * x['quantity'])}"
        if x["deposit"]:
            s += f"\n  Refundable security deposit: {_usd(x['deposit'])}"
        out.append(s)
    return "\n".join(out)


def _enviar(enviar, para, assunto, texto):
    from command_center.providers import email_envio
    (enviar or email_envio.enviar)(para, assunto, texto)


def textos(con, o):
    """(assunto, texto) do e-mail para a pessoa, conforme o resultado. Usado no envio e no teste."""
    ls = linhas(con, o)
    sessao = any(x["kind"] == "sessao" for x in ls)
    nada = "nothing was charged" + (" and no session was booked" if sessao else "")
    if o["outcome"] == "falhou":
        return (f"Payment didn't go through — order #{o['id']} — URACE",
                f"Hi {_primeiro(o)},\n\nThe payment for your URACE order #{o['id']} didn't go through, so {nada}.\n\n"
                f"{_texto_itens(ls)}\n\nYou can try again with the same items. Prices and availability are checked again "
                f"when you do:\n{link(o)}\n\n{CONTATO}\n\n{ASSINATURA}")
    return (f"Your checkout expired — order #{o['id']} — URACE",
            f"Hi {_primeiro(o)},\n\nYour secure checkout for URACE order #{o['id']} closed before the payment was finished, "
            f"so {nada}.\n\n{_texto_itens(ls)}\n\nYour items are saved. Restore your cart here (prices and availability are "
            f"checked again):\n{link(o)}\n\n{CONTATO}\n\n{ASSINATURA}")


def avisar_resultado(con, oid, enviar=None):
    """O aviso do falhou (pessoa + equipe) ou do expirou (só a pessoa, e só com e-mail). Uma vez só: o pedido
    é tomado (`outcome_notified_at`) antes de mandar; se o envio falha, ele é solto e a rodada tenta de novo."""
    o = um(con, "SELECT * FROM store_orders WHERE id=?", (oid,))
    if not o or not o["outcome"] or o["outcome_notified_at"]:
        return False
    if o["status"] == "pago" or (o["outcome"] == "expirado" and not o["outcome_email"]):
        atualizar(con, "store_orders", oid, outcome_notified_at=agora(), updated_at=agora())
        con.commit()
        return False
    cur = con.execute("UPDATE store_orders SET outcome_notified_at=? WHERE id=? AND outcome_notified_at IS NULL",
                      (agora(), oid))
    con.commit()
    if cur.rowcount != 1:
        return False                                    # outra tarefa tomou este aviso agora
    try:
        if o["outcome_email"]:
            assunto, texto = textos(con, o)
            _enviar(enviar, o["outcome_email"], assunto, texto)
        if o["outcome"] == "falhou":
            ls = linhas(con, o)
            _enviar(enviar, "support@urace.us",
                    f"Site · PAGAMENTO FALHOU: pedido #{o['id']} — {o['name'] or o['email'] or 'sem nome'}",
                    f"O pagamento do pedido #{o['id']} falhou no Stripe (meio de pagamento que confirma depois). Nada foi "
                    f"cobrado e nenhuma sessão foi marcada; a vaga continua livre.\n{o['name'] or ''} <{o['email'] or ''}> "
                    f"{o['phone'] or ''}\n\n{_texto_itens(ls)}\nTotal: {_usd(o['amount'])}\n\n"
                    + ("O cliente recebeu o e-mail com o botão Try again.\n" if o["outcome_email"]
                       else "O cliente NÃO recebeu e-mail (o Stripe não passou e-mail): ligue para ele.\n")
                    + f"Página do pedido (para mandar ao cliente): {link(o)}")
        atualizar(con, "store_orders", oid, outcome_notify_error=None, updated_at=agora())
        con.commit()
        return True
    except Exception as e:                              # noqa: BLE001 — a rodada de 15 min tenta de novo
        atualizar(con, "store_orders", oid, outcome_notified_at=None, outcome_notify_error=str(e)[:300], updated_at=agora())
        con.commit()
        return False


def avisar_resultado_bg(oid, enviar=None):
    """Depois da resposta ao Stripe (tarefa em segundo plano)."""
    con = conectar()
    try:
        avisar_resultado(con, oid, enviar)
    finally:
        con.close()


def rodar(con, enviar=None):
    """Na rotina de 15 min: aviso de falhou/expirou que não saiu (e-mail fora do ar) tenta de novo. O que
    chegou há menos de 2 min fica para a tarefa que o webhook já disparou."""
    n = 0
    for o in todos(con, "SELECT id FROM store_orders WHERE outcome IS NOT NULL AND outcome_notified_at IS NULL "
                        "AND updated_at < strftime('%Y-%m-%dT%H:%M:%fZ','now','-2 minutes') ORDER BY id LIMIT 20"):
        n += bool(avisar_resultado(con, o["id"], enviar))
    return {"avisos": n}


# ------------------------------------------------------------------ o painel
def para_painel(con, o):
    """O que a equipe vê de um pedido: estado, quem, o quê, e o link da página para mandar ao cliente."""
    ls = linhas(con, o)
    return {"id": o["id"], "tipo": o["kind"], "status": o["status"], "total": o["amount"], "pago": o["amount_paid"],
            "criado_em": o["created_at"], "pago_em": o["paid_at"], "nome": o["name"], "email": o["email"], "telefone": o["phone"],
            "resumo": "; ".join(x["name"] + (f" × {x['quantity']}" if x["quantity"] > 1 else "") for x in ls)[:300],
            "opp_id": o["opp_id"], "atencao": o["attention"], "aviso_em": o["outcome_notified_at"],
            "aviso_para": o["outcome_email"], "aviso_erro": o["outcome_notify_error"], "refeito_de": o["retry_of"],
            "link": link(o), "caminho": caminho(o)}


def lista(con, status=None, limit=50, offset=0):
    onde, p = "", []
    if status in ESTADOS:
        onde, p = " WHERE status=?", [status]
    total = um(con, f"SELECT COUNT(*) AS n FROM store_orders{onde}", p)["n"]
    linhas_ = todos(con, f"SELECT * FROM store_orders{onde} ORDER BY id DESC LIMIT ? OFFSET ?",
                    p + [max(1, min(int(limit), 200)), max(0, int(offset))])
    return {"pedidos": [para_painel(con, o) for o in linhas_], "total": total}

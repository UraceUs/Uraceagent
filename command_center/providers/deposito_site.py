"""#317 · Site › Security deposit: o depósito de segurança cobrado no site, devolvido pelo Stripe com o valor escolhido.

Dono, 16/10: *"uma sessão de security deposit, onde a gente consiga ter o controle para fazer o reembolso de cada
security deposit e alterar o valor do security deposit para ser cobrado no site … coloca lá no Stripe … para a gente
só clicar no botão e fazer o refund do Security Deposit pelo Command Center. Sempre conseguindo alterar o valor que
vai ser reembolsado."*

Cada DEPÓSITO é uma linha cobrada no Stripe: no carrinho, cada sessão com depósito (`store_order_items.deposit`); no
"Buy now" de um produto, o pedido inteiro (`store_orders.deposit`, sem linha). Só pedido **pago** tem depósito retido.

Devolver:
  * o valor é escolhido na hora (parcial vale, e mais de uma devolução no mesmo depósito), nunca mais que o que
    ainda está retido;
  * a devolução nasce `pendente` numa transação `BEGIN IMMEDIATE` ANTES de chamar o Stripe: dois cliques (ou duas
    pessoas) ao mesmo tempo não devolvem duas vezes, porque o segundo já vê o valor reservado;
  * o Stripe recebe uma chave de idempotência por devolução (`urace-deposito-<id>`): repetir o pedido nunca devolve
    de novo;
  * se a resposta do Stripe se perder no caminho, a linha fica `pendente` (o valor continua reservado) e o
    "Conferir no Stripe" acerta pela marca `urace_reembolso` que vai na devolução.

O QuickBooks não muda sozinho: o recibo da venda continua lá, e a devolução se registra como sempre se registrou.
"""
import os
import urllib.parse
from datetime import datetime, timedelta, timezone

from command_center.db import agora, atualizar, auditar, inserir, todos, um
from command_center.providers import loja, servicos_site as sv, stripe_loja

ESTADOS = ("retidos", "devolvidos", "todos")
# uma devolução `pendente` mais velha que isto, sem par no Stripe, é dada como não feita no "Conferir"
PENDENTE_ESQUECIDA = timedelta(minutes=10)


class ErroDeposito(ValueError):
    pass


def _cents(v):
    return int(round(float(v or 0) * 100))


def _dolar(c):
    return round(c / 100, 2)


# ------------------------------------------------------------------ a lista
_DEPOSITOS = """
WITH dep AS (
  SELECT o.id AS order_id, i.id AS item_id, i.deposit AS deposito, i.name AS descricao, i.kind AS tipo,
         i.date AS data, i.period AS turno, i.pilot_name AS piloto, COALESCE(i.client_id, o.client_id) AS client_id,
         o.name AS nome, o.email AS email, o.paid_at AS pago_em, o.payment_intent AS payment_intent,
         o.stripe_refunded AS stripe_devolvido
    FROM store_orders o JOIN store_order_items i ON i.order_id = o.id
   WHERE o.status = 'pago' AND o.kind = 'carrinho' AND i.deposit > 0
  UNION ALL
  SELECT o.id, NULL, o.deposit, o.product_name || COALESCE(' · ' || o.variation, ''), 'produto',
         NULL, NULL, NULL, o.client_id, o.name, o.email, o.paid_at, o.payment_intent, o.stripe_refunded
    FROM store_orders o
   WHERE o.status = 'pago' AND o.kind <> 'carrinho' AND COALESCE(o.deposit, 0) > 0
), dev AS (
  SELECT order_id, item_id,
         SUM(CASE WHEN status = 'feito' THEN amount ELSE 0 END) AS devolvido,
         SUM(CASE WHEN status = 'pendente' THEN amount ELSE 0 END) AS reservado
    FROM store_deposit_refunds GROUP BY order_id, item_id
)
SELECT dep.*, COALESCE(dev.devolvido, 0) AS devolvido, COALESCE(dev.reservado, 0) AS reservado,
       ROUND(dep.deposito - COALESCE(dev.devolvido, 0) - COALESCE(dev.reservado, 0), 2) AS retido
  FROM dep LEFT JOIN dev ON dev.order_id = dep.order_id AND dev.item_id IS dep.item_id
"""


def _filtro(estado, q):
    onde, p = [], []
    if estado == "retidos":                  # com devolução pendente também: falta conferir no Stripe
        onde.append("(retido > 0 OR reservado > 0)")
    elif estado == "devolvidos":
        onde.append("(retido <= 0 AND reservado <= 0)")
    q = (q or "").strip().lstrip("#")
    if q:
        if q.isascii() and q.isdigit() and len(q) <= 18:
            onde.append("order_id = ?")
            p.append(int(q))
        else:
            like = f"%{q.lower()}%"
            onde.append("(LOWER(COALESCE(nome,'')) LIKE ? OR LOWER(COALESCE(email,'')) LIKE ? OR LOWER(COALESCE(piloto,'')) LIKE ?)")
            p += [like, like, like]
    return (" WHERE " + " AND ".join(onde)) if onde else "", p


def lista(con, estado="retidos", q="", limit=30, offset=0):
    """Os depósitos cobrados no site, do mais novo ao mais velho, paginados; com os totais do filtro."""
    if estado not in ESTADOS:
        raise ErroDeposito("filtro inválido: retidos, devolvidos ou todos")
    onde, p = _filtro(estado, q)
    base = f"SELECT * FROM ({_DEPOSITOS}){onde}"
    soma = um(con, f"SELECT COUNT(*) AS n, COALESCE(SUM(retido), 0) AS retido, COALESCE(SUM(devolvido), 0) AS devolvido FROM ({base})", p)
    linhas = todos(con, f"{base} ORDER BY pago_em DESC, order_id DESC, item_id LIMIT ? OFFSET ?", p + [limit, offset])
    chaves = [(x["order_id"], x["item_id"]) for x in linhas]
    devs = {}
    if chaves:
        ids = sorted({o for o, _ in chaves})
        for d in todos(con, f"""SELECT r.*, u.name AS por FROM store_deposit_refunds r LEFT JOIN users u ON u.id = r.by_user_id
                                 WHERE r.order_id IN ({",".join("?" * len(ids))}) ORDER BY r.id""", ids):
            devs.setdefault((d["order_id"], d["item_id"]), []).append(
                {"id": d["id"], "valor": d["amount"], "estado": d["status"], "stripe": d["stripe_refund_id"],
                 "stripe_estado": d["stripe_status"], "nota": d["note"], "erro": d["error"], "por": d["por"],
                 "em": d["done_at"] or d["created_at"]})
    itens = [{**x, "retido": max(0.0, x["retido"]), "pode_devolver": bool(x["payment_intent"]) and x["retido"] > 0,
              "devolucoes": devs.get((x["order_id"], x["item_id"]), [])} for x in linhas]
    for x in itens:
        x.pop("payment_intent", None)              # o id do pagamento fica no servidor
    return {"depositos": itens, "total": soma["n"], "soma_retido": round(soma["retido"], 2),
            "soma_devolvido": round(soma["devolvido"], 2), "stripe": stripe_loja.ligado()}


def _deposito(con, oid, item_id):
    """A linha do depósito (pago), com o que já saiu e o que está reservado."""
    sql = f"SELECT * FROM ({_DEPOSITOS}) WHERE order_id = ? AND item_id IS ?"
    return um(con, sql, (oid, item_id))


# ------------------------------------------------------------------ devolver
def _valor(v):
    try:
        n = sv.preco(v)
    except sv.ErroServico:
        raise ErroDeposito("valor inválido: use números, como 400 ou 150.50")
    if n <= 0:
        raise ErroDeposito("o valor a devolver tem de ser maior que zero")
    return n


def reembolsar(con, por, oid, item_id, valor, nota=None, ip=None, http=None):
    """Devolve `valor` do depósito pelo Stripe. Devolve a devolução gravada (feita ou com o erro do Stripe)."""
    if not stripe_loja.ligado() and http is None:
        raise ErroDeposito("o Stripe não está ligado neste servidor")
    v = _valor(valor)
    nota = (nota or "").strip()[:300] or None
    con.execute("BEGIN IMMEDIATE")
    try:
        d = _deposito(con, oid, item_id)
        if not d:
            raise ErroDeposito("depósito não encontrado (o pedido precisa estar pago e ter depósito)")
        if not d["payment_intent"]:
            raise ErroDeposito("este pagamento não tem o id do Stripe: devolva pelo painel do Stripe")
        if _cents(v) > _cents(d["retido"]):
            raise ErroDeposito(f"o máximo que ainda dá para devolver é US$ {max(0, d['retido']):,.2f}")
        rid = inserir(con, "store_deposit_refunds", order_id=oid, item_id=item_id, amount=v, status="pendente",
                      note=nota, by_user_id=por)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    campos = {"payment_intent": d["payment_intent"], "amount": _cents(v), "reason": "requested_by_customer",
              "metadata": {"urace_reembolso": rid, "pedido": oid, "linha": item_id or "", "tipo": "security_deposit"}}
    try:
        r = (http or stripe_loja._http)("POST", "/v1/refunds", campos, idem=f"urace-deposito-{rid}")
    except Exception as e:                                  # noqa: BLE001
        if isinstance(e, stripe_loja.ErroStripe) and not (getattr(e, "codigo", None) or 0) >= 500:
            # o Stripe disse não (4xx) ou nem chegou lá (sem conexão): nada foi devolvido, o valor volta a ficar retido
            atualizar(con, "store_deposit_refunds", rid, status="falhou", error=str(e)[:300], done_at=agora())
            auditar(con, "store.deposit.refund_fail", f"user:{por}", user_id=por, entity_type="store_order", entity_id=oid,
                    detail={"linha": item_id, "valor": v, "nota": nota, "erro": str(e)[:200]}, ip=ip)
            return {"id": rid, "estado": "falhou", "erro": str(e)[:300]}
        # a resposta se perdeu (tempo esgotado no meio) ou o Stripe deu 5xx (resultado indeterminado): ele pode ter
        # devolvido. O valor segue reservado e o "Conferir no Stripe" acerta pela marca; um clique novo não devolve de novo
        auditar(con, "store.deposit.refund_unknown", f"user:{por}", user_id=por, entity_type="store_order", entity_id=oid,
                detail={"linha": item_id, "valor": v, "nota": nota, "erro": str(e)[:200] or type(e).__name__}, ip=ip)
        return {"id": rid, "estado": "pendente",
                "erro": "a resposta do Stripe não chegou. Toque em \"Conferir no Stripe\" daqui a pouco."}
    estado = "falhou" if r.get("status") in ("failed", "canceled") else "feito"
    atualizar(con, "store_deposit_refunds", rid, status=estado, stripe_refund_id=r.get("id"),
              stripe_status=r.get("status"), done_at=agora(),
              error=(r.get("failure_reason") or "o Stripe recusou") if estado == "falhou" else None)
    auditar(con, "store.deposit.refund", f"user:{por}", user_id=por, entity_type="store_order", entity_id=oid,
            detail={"linha": item_id, "valor": v, "nota": nota, "stripe": r.get("id"), "estado": r.get("status")}, ip=ip)
    return {"id": rid, "estado": estado, "stripe": r.get("id"), "stripe_estado": r.get("status")}


def conferir(con, por, oid, ip=None, http=None, agora_dt=None):
    """Lê as devoluções do pagamento no Stripe: acerta as do painel (pela marca) e guarda quanto o pagamento já
    teve devolvido no total — inclusive o que foi devolvido direto no painel do Stripe."""
    o = um(con, "SELECT id, payment_intent, status FROM store_orders WHERE id = ?", (oid,))
    if not o or o["status"] != "pago":
        raise ErroDeposito("pedido não encontrado ou não pago")
    if not o["payment_intent"]:
        raise ErroDeposito("este pagamento não tem o id do Stripe")
    r = (http or stripe_loja._http)("GET", f"/v1/refunds?payment_intent={urllib.parse.quote(o['payment_intent'])}&limit=100")
    lista_s = r.get("data") or []
    nossos = {str(x["id"]): x for x in todos(con, "SELECT * FROM store_deposit_refunds WHERE order_id = ?", (oid,))}
    vistos, acertos = set(), 0
    for s in lista_s:
        marca = str((s.get("metadata") or {}).get("urace_reembolso") or "")
        linha = nossos.get(marca)
        if not linha:
            continue
        vistos.add(marca)
        estado = "falhou" if s.get("status") in ("failed", "canceled") else "feito"
        if (linha["status"], linha["stripe_refund_id"], linha["stripe_status"]) != (estado, s.get("id"), s.get("status")):
            atualizar(con, "store_deposit_refunds", linha["id"], status=estado, stripe_refund_id=s.get("id"),
                      stripe_status=s.get("status"), done_at=linha["done_at"] or agora(),
                      error=(s.get("failure_reason") or "o Stripe recusou") if estado == "falhou" else None)
            acertos += 1
    limite = ((agora_dt or datetime.now(timezone.utc)) - PENDENTE_ESQUECIDA).strftime("%Y-%m-%dT%H:%M:%S")
    for k, linha in nossos.items():
        if linha["status"] == "pendente" and k not in vistos and linha["created_at"][:19] < limite:
            atualizar(con, "store_deposit_refunds", linha["id"], status="falhou", done_at=agora(),
                      error="não chegou ao Stripe: o valor voltou a ficar retido")
            acertos += 1
    total = _dolar(sum(int(s.get("amount") or 0) for s in lista_s if s.get("status") not in ("failed", "canceled")))
    con.execute("UPDATE store_orders SET stripe_refunded = ? WHERE id = ?", (total, oid))
    auditar(con, "store.deposit.check", f"user:{por}", user_id=por, entity_type="store_order", entity_id=oid,
            detail={"acertos": acertos, "stripe_devolvido": total}, ip=ip)
    return {"acertos": acertos, "stripe_devolvido": total}


# ------------------------------------------------------------------ o valor cobrado no site
def valores(con):
    """O depósito que o site cobra hoje: por sessão (cada serviço) e por produto (os que têm)."""
    servicos = todos(con, """SELECT id, name, deposit, deposit_required, active, kind FROM booking_services
                              WHERE COALESCE(kind, 'session') = 'session' ORDER BY active DESC, sort, id""")
    produtos = todos(con, """SELECT id, name, slug, deposit, active FROM store_products
                              WHERE COALESCE(deposit, 0) > 0 ORDER BY active DESC, sort, id""")
    return {"servicos": [{**s, "deposit": s["deposit"] or 0.0, "deposit_required": bool(s["deposit_required"]),
                          "active": bool(s["active"])} for s in servicos],
            "produtos": [{**p, "deposit": p["deposit"] or 0.0, "active": bool(p["active"])} for p in produtos]}


def mudar_valor(con, por, tipo, ident, valor=None, obrigatorio=None):
    """Muda o depósito cobrado nas PRÓXIMAS compras (o pedido já pago fica com o valor do dia) e, no serviço, a
    caixa "obrigatório". Devolve (evento, {campo: (antes, depois)}) para a auditoria."""
    if tipo == "servico":
        d = {**({"deposit": valor} if valor is not None else {}),
             **({"deposit_required": bool(obrigatorio)} if obrigatorio is not None else {})}
        if not d:
            raise ErroDeposito("nada para mudar")
        try:
            return "booking.service.update", sv.mudar(con, por, ident, d)
        except sv.ErroServico as e:
            raise ErroDeposito(str(e))
    if tipo == "produto":
        if valor is None:
            raise ErroDeposito("nada para mudar")
        try:
            return "store.product.update", loja.mudar(con, por, ident, {"deposit": valor})
        except loja.ErroProduto as e:
            raise ErroDeposito(str(e))
    raise ErroDeposito("tipo inválido: servico ou produto")


def modo_teste():
    """A chave do Stripe é a de teste? A tela avisa: devolução em modo teste não devolve dinheiro de verdade."""
    return os.environ.get("STRIPE_SECRET_KEY", "").strip().startswith(("sk_test_", "rk_test_"))

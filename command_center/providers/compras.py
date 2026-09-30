"""Pedidos internos e compras — o que a URACE compra para si (módulo 3 do roadmap).

Dono, 30/09: *"siga com a tela de pedidos e compras"*. O fluxo real de hoje (quem pede,
por onde, quem aprova) ainda não foi contado; este é o mínimo que cobre o dia a dia e que
dá para ajustar depois sem perder dado:

- **Pedido** é de quem precisa: o mecânico pede a peça (do estoque ou uma coisa qualquer),
  quanto, para quando, se é urgente e para o kart de quem. Estados: aberto → comprando →
  chegou → entregue (ou cancelado).
- **Compra** é de quem gasta: o gerente junta pedidos e o que está abaixo do mínimo numa
  compra do fornecedor, com custo. Estados: rascunho → pedida → parcial/recebida (ou
  cancelada, se nada chegou).
- **Receber dá entrada no estoque sozinho**, atualiza o custo da peça (e o preço final,
  quando a ficha tem margem) e avisa o pedido que chegou. Ninguém redigita o que chegou —
  redigitar é onde o estoque começa a não bater.

Peça comprada para o kart de um cliente entra como estoque DA URACE: quando o mecânico usar
("usada no kart de"), ela vira cobrança do cliente pelo caminho que já existe (29/09).
"""
from datetime import date

from command_center.db import agora, inserir, todos, um
from command_center.providers import estoque, prateleiras

ErroCompra = estoque.ErroEstoque


def _texto(v):
    return (v or "").strip() or None


# --------------------------------------------------------------------- pedidos
def criar_pedido(con, por, qty, item_id=None, description=None, unit=None, client_id=None,
                 needed_by=None, urgent=False, notes=None):
    it = estoque.item(con, item_id) if item_id else None
    desc = _texto(description) or (it["name"] if it else None)
    if not desc:
        raise ErroCompra("diga o que precisa (escolha a peça ou escreva o que é)")
    qty = float(qty or 0)
    if qty <= 0:
        raise ErroCompra("quantidade tem de ser maior que zero")
    if client_id and not um(con, "SELECT 1 AS x FROM clients WHERE id=?", (client_id,)):
        raise ErroCompra(f"cliente #{client_id} não existe")
    if needed_by:
        try:
            date.fromisoformat(needed_by[:10])
        except ValueError:
            raise ErroCompra("data inválida (use AAAA-MM-DD)")
    return inserir(con, "purchase_requests", item_id=it["id"] if it else None, description=desc[:200], qty=qty,
                   unit=_texto(unit) or (it["unit"] if it else "un"), client_id=client_id,
                   needed_by=(needed_by or None) and needed_by[:10], urgent=1 if urgent else 0,
                   notes=_texto(notes), requested_by=por)


def pedidos(con, status=None):
    sql = """SELECT r.*, u.name AS pedido_por, COALESCE(c.pilot_name, c.name) AS cliente, i.name AS item
               FROM purchase_requests r LEFT JOIN users u ON u.id=r.requested_by
               LEFT JOIN clients c ON c.id=r.client_id LEFT JOIN stock_items i ON i.id=r.item_id"""
    p = ()
    if status:
        sql += " WHERE r.status=?"; p = (status,)
    return [dict(x) for x in todos(con, sql + " ORDER BY r.urgent DESC, COALESCE(r.needed_by,'9999') , r.id", p)]


def mudar_pedido(con, rid, novo):
    r = um(con, "SELECT * FROM purchase_requests WHERE id=?", (rid,))
    if not r:
        raise ErroCompra("pedido não existe")
    permitido = {"cancelado": ("aberto",), "entregue": ("chegou",), "aberto": ("cancelado",)}
    if r["status"] not in permitido.get(novo, ()):
        raise ErroCompra(f"pedido {r['status']} não pode virar {novo}")
    con.execute("UPDATE purchase_requests SET status=?, updated_at=? WHERE id=?", (novo, agora(), rid))
    return r


# --------------------------------------------------------------------- compras
def criar_compra(con, por, linhas, supplier=None, reference=None, expected_at=None, notes=None, pedir=False):
    """`linhas`: [{item_id?, description?, qty, unit_cost?, request_id?}]. Pedido que entra
    numa compra sai de "aberto" — e não pode entrar em duas."""
    if not linhas:
        raise ErroCompra("a compra precisa de pelo menos um item")
    pid = inserir(con, "purchase_orders", supplier=_texto(supplier) or "Comet Kart Sales", reference=_texto(reference),
                  expected_at=(expected_at or None) and expected_at[:10], notes=_texto(notes), created_by=por,
                  status="pedida" if pedir else "rascunho", ordered_at=agora() if pedir else None)
    for l in linhas:
        req = None
        if l.get("request_id"):
            req = um(con, "SELECT * FROM purchase_requests WHERE id=?", (l["request_id"],))
            if not req:
                raise ErroCompra(f"pedido #{l['request_id']} não existe")
            if req["status"] != "aberto":
                raise ErroCompra(f"o pedido #{req['id']} ({req['description']}) já está {req['status']}")
        item_id = l.get("item_id") or (req["item_id"] if req else None)
        it = estoque.item(con, item_id) if item_id else None
        desc = _texto(l.get("description")) or (req["description"] if req else None) or (it["name"] if it else None)
        if not desc:
            raise ErroCompra("cada item da compra precisa de nome")
        qty = float(l.get("qty") or (req["qty"] if req else 0))
        if qty <= 0:
            raise ErroCompra(f"quantidade de {desc} tem de ser maior que zero")
        custo = l.get("unit_cost")
        if custo is not None and float(custo) < 0:
            raise ErroCompra("custo não pode ser negativo")
        inserir(con, "purchase_lines", purchase_id=pid, item_id=it["id"] if it else None, description=desc[:200],
                qty=qty, unit_cost=None if custo in (None, "") else round(float(custo), 2),
                request_id=req["id"] if req else None)
        if req:
            con.execute("UPDATE purchase_requests SET status='comprando', purchase_id=?, updated_at=? WHERE id=?",
                        (pid, agora(), req["id"]))
    return pid


def compra(con, pid):
    c = um(con, """SELECT p.*, u.name AS criada_por FROM purchase_orders p LEFT JOIN users u ON u.id=p.created_by
                    WHERE p.id=?""", (pid,))
    if not c:
        raise ErroCompra("compra não existe")
    linhas = [dict(l) for l in todos(con, """SELECT l.*, i.name AS item, i.unit, r.requested_by, u.name AS pedido_por,
                                                     COALESCE(cl.pilot_name, cl.name) AS cliente
                                                FROM purchase_lines l LEFT JOIN stock_items i ON i.id=l.item_id
                                                LEFT JOIN purchase_requests r ON r.id=l.request_id
                                                LEFT JOIN users u ON u.id=r.requested_by
                                                LEFT JOIN clients cl ON cl.id=r.client_id
                                               WHERE l.purchase_id=? ORDER BY l.id""", (pid,))]
    total = sum((l["unit_cost"] or 0) * l["qty"] for l in linhas)
    return {**c, "linhas": linhas, "total": round(total, 2),
            "sem_custo": sum(1 for l in linhas if l["unit_cost"] is None),
            "atrasada": atrasada(c)}


def atrasada(c):
    return bool(c["status"] in ("pedida", "parcial") and c["expected_at"] and c["expected_at"] < date.today().isoformat())


def compras(con, status=None):
    sql = "SELECT id FROM purchase_orders"
    p = ()
    if status:
        sql += " WHERE status=?"; p = (status,)
    return [compra(con, x["id"]) for x in todos(con, sql + " ORDER BY id DESC LIMIT 200", p)]


def marcar_pedida(con, pid, reference=None, expected_at=None):
    c = um(con, "SELECT * FROM purchase_orders WHERE id=?", (pid,))
    if not c:
        raise ErroCompra("compra não existe")
    if c["status"] != "rascunho":
        raise ErroCompra(f"a compra já está {c['status']}")
    con.execute("UPDATE purchase_orders SET status='pedida', ordered_at=?, reference=COALESCE(?, reference), "
                "expected_at=COALESCE(?, expected_at), updated_at=? WHERE id=?",
                (agora(), _texto(reference), (expected_at or None) and expected_at[:10], agora(), pid))


def cancelar_compra(con, pid):
    c = um(con, "SELECT * FROM purchase_orders WHERE id=?", (pid,))
    if not c:
        raise ErroCompra("compra não existe")
    if um(con, "SELECT 1 AS x FROM purchase_lines WHERE purchase_id=? AND qty_received>0", (pid,)):
        raise ErroCompra("já chegou parte desta compra: não dá para cancelar (o estoque já recebeu)")
    if c["status"] == "cancelada":
        return
    con.execute("UPDATE purchase_orders SET status='cancelada', updated_at=? WHERE id=?", (agora(), pid))
    # os pedidos voltam para a fila: ninguém fica esperando uma compra que não existe
    con.execute("UPDATE purchase_requests SET status='aberto', purchase_id=NULL, updated_at=? WHERE purchase_id=? AND status='comprando'",
                (agora(), pid))


def receber(con, pid, recebidos, por=None, local=estoque.SEDE):
    """`recebidos`: [{line_id, qty, criar_item?}]. Cada quantidade vira ENTRADA no estoque
    (motivo "compra", com o número da compra). Chegou mais do que foi pedido: recusado —
    é erro de digitação ou é outra compra."""
    c = um(con, "SELECT * FROM purchase_orders WHERE id=?", (pid,))
    if not c:
        raise ErroCompra("compra não existe")
    if c["status"] in ("cancelada", "recebida"):
        raise ErroCompra(f"a compra já está {c['status']}")
    if not recebidos:
        raise ErroCompra("diga quanto chegou de pelo menos um item")
    entradas = []
    for r in recebidos:
        l = um(con, "SELECT * FROM purchase_lines WHERE id=? AND purchase_id=?", (r.get("line_id"), pid))
        if not l:
            raise ErroCompra("esse item não é desta compra")
        qty = float(r.get("qty") or 0)
        if qty <= 0:
            continue
        falta = round(l["qty"] - l["qty_received"], 4)
        if qty > falta + 1e-9:
            raise ErroCompra(f"{l['description']}: chegaram {qty:g}, mas faltavam {falta:g}")
        item_id = l["item_id"]
        if not item_id and r.get("criar_item"):
            item_id = estoque.criar_item(con, "peca", l["description"],
                                         category=prateleiras.sugerir("peca", l["description"]),
                                         notes=f"Criada no recebimento da compra #{pid}.")
            con.execute("UPDATE purchase_lines SET item_id=? WHERE id=?", (item_id, l["id"]))
        if item_id:
            estoque.entrada(con, item_id, qty=qty, para=local, reason="compra", by_user_id=por,
                            notes=f"compra #{pid}" + (f" · {c['reference']}" if c["reference"] else ""))
            if l["unit_cost"] is not None:
                it = estoque.item(con, item_id)
                # custo novo: com margem, o preço final acompanha; sem margem, o preço fica como está
                estoque.atualizar_item(con, item_id, cost=l["unit_cost"],
                                       **({} if it["markup"] else {"price": it["price"]}))
        con.execute("UPDATE purchase_lines SET qty_received=qty_received+? WHERE id=?", (qty, l["id"]))
        if l["request_id"] and qty >= falta - 1e-9:
            con.execute("UPDATE purchase_requests SET status='chegou', updated_at=? WHERE id=? AND status='comprando'",
                        (agora(), l["request_id"]))
        entradas.append({"line_id": l["id"], "item_id": item_id, "qty": qty, "estoque": bool(item_id)})
    if not entradas:
        raise ErroCompra("nenhuma quantidade informada")
    pendente = um(con, "SELECT COUNT(*) AS n FROM purchase_lines WHERE purchase_id=? AND qty_received < qty - 1e-9", (pid,))["n"]
    novo = "recebida" if not pendente else "parcial"
    con.execute("UPDATE purchase_orders SET status=?, ordered_at=COALESCE(ordered_at, ?), updated_at=? WHERE id=?",
                (novo, agora(), agora(), pid))
    return {"status": novo, "entradas": entradas}

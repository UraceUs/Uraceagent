"""Serviços da agenda e os preços deles (#50).

Dono, 01/10: *"deixe o campo dos preços para ter a possibilidade de ser facilmente
alterados"*. Quem muda o preço é o gerente, numa tela do site interno, sem código:
- o **preço vive no banco**, não no código nem no WordPress;
- o **agendamento guarda o serviço e o valor do dia em que foi marcado**: mudar o preço
  depois não muda a cobrança de quem já marcou;
- **desativar não apaga**: o serviço some da área do cliente, e o histórico continua;
- cada serviço aponta para um **item do QuickBooks**, que é o que vai na linha da invoice.

Nada é inventado: sem serviço cadastrado pela equipe, o cliente não consegue marcar
(NO FAKE DATA).
"""
import re

from command_center.db import agora, atualizar, inserir, todos, um

MAX_PRECO = 100_000


class ErroServico(ValueError):
    pass


def preco(v):
    """'719', '719.9', '$1,856.90' → 719.0 / 719.9 / 1856.9. Nada de negativo nem absurdo."""
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        t = re.sub(r"[\s$]", "", str(v or "")).replace(",", "")
        if not re.fullmatch(r"\d+(\.\d{1,2})?", t):
            raise ErroServico("preço inválido: use números, como 719 ou 719.90")
        n = float(t)
    if not 0 <= n <= MAX_PRECO:
        raise ErroServico(f"preço fora do limite (0 a {MAX_PRECO:,})")
    return round(n, 2)


def _texto(v, n):
    v = re.sub(r"\s+", " ", (v or "").strip())
    return v[:n] or None


def lista(con, ativos=False):
    sql = ("SELECT s.*, q.name AS qbo_item_name FROM booking_services s LEFT JOIN qbo_items q ON q.id=s.qbo_item_id"
           + (" WHERE s.active=1" if ativos else "") + " ORDER BY s.active DESC, s.sort, s.name")
    return [dict(s) for s in todos(con, sql)]


def para_cliente(con):
    """O que a área do cliente mostra para marcar sessão: nome, descrição e preço. Nada do QuickBooks."""
    return [{"id": s["id"], "name": s["name"], "description": s["description"], "price": s["price"],
             "deposit": s["deposit"] or 0} for s in lista(con, True) if (s["kind"] or "session") == "session"]


def planos_para_cliente(con):
    """#169: os planos mensais que o site vende (Academy, Boost): preço por mês, meses, sessões por mês."""
    return [{"id": s["id"], "name": s["name"], "description": s["description"], "price": s["price"],
             "months": s["months"] or 1, "sessions_month": s["sessions_month"] or 0,
             "total": round(s["price"] * (s["months"] or 1), 2)}
            for s in lista(con, True) if s["kind"] == "plan"]


def plano(con, sid):
    s = um(con, "SELECT * FROM booking_services WHERE id=? AND active=1 AND kind='plan'", (sid,)) if sid else None
    if not s:
        raise ErroServico("Choose a plan.")
    return s


def itens_qbo(con):
    """Itens do QuickBooks (espelho local) que a equipe pode escolher. Dono, 01/10: *"por
    enquanto deixe só os academies e o race daily using own kart"*."""
    return [dict(i) for i in todos(con, """SELECT id, name, full_name, price FROM qbo_items
                                            WHERE active=1 AND COALESCE(type,'Service')='Service'
                                              AND (LOWER(COALESCE(full_name, name)) LIKE '%academy%'
                                                   OR (LOWER(COALESCE(full_name, name)) LIKE '%daily%'
                                                       AND LOWER(COALESCE(full_name, name)) LIKE '%own kart%'))
                                            ORDER BY name""")]


def _dados(con, d, parcial):
    s = {}
    if not parcial or "name" in d:
        nome = _texto(d.get("name"), 80)
        if not nome or len(nome) < 3:
            raise ErroServico("dê um nome ao serviço (o cliente lê, em inglês)")
        s["name"] = nome
    if not parcial or "price" in d:
        s["price"] = preco(d.get("price"))
    if "description" in d:
        s["description"] = _texto(d.get("description"), 300)
    if "qbo_item" in d:
        # dono, 01/10: "que seja possível que seja um texto personalizado". O que bate com
        # o nome de um item vira o item; o resto é o texto da linha da invoice.
        t = re.sub(r"\s+", " ", (d["qbo_item"] or "").strip())[:120]
        item = um(con, """SELECT id FROM qbo_items WHERE active=1
                           AND (LOWER(name)=LOWER(?) OR LOWER(COALESCE(full_name,''))=LOWER(?))""", (t, t)) if t else None
        s["qbo_item_id"] = item["id"] if item else None
        s["invoice_text"] = None if item else (t or None)
    if "qbo_item_id" in d and "qbo_item" not in d:
        item = (str(d["qbo_item_id"]).strip() if d["qbo_item_id"] is not None else "") or None
        if item and not um(con, "SELECT 1 AS x FROM qbo_items WHERE id=?", (item,)):
            raise ErroServico("item do QuickBooks não encontrado (sincronize o QuickBooks e tente de novo)")
        s["qbo_item_id"] = item
    if "deposit" in d:
        # #50: depósito por sessão (Arrive and Drive: US$ 400); vazio ou 0 = sem depósito
        s["deposit"] = preco(d["deposit"]) if d["deposit"] not in (None, "", 0, "0") else 0.0
    if "kind" in d and d["kind"] is not None:
        if d["kind"] not in ("session", "plan"):
            raise ErroServico("tipo inválido: session (sessão avulsa) ou plan (plano mensal)")
        s["kind"] = d["kind"]
    if "months" in d:
        m = int(d["months"]) if d["months"] not in (None, "") else None
        if m is not None and not 1 <= m <= 36:
            raise ErroServico("meses do plano: de 1 a 36")
        s["months"] = m
    if "sessions_month" in d:
        n = int(d["sessions_month"]) if d["sessions_month"] not in (None, "") else None
        if n is not None and not 0 <= n <= 31:
            raise ErroServico("sessões por mês: de 0 a 31")
        s["sessions_month"] = n
    if "active" in d and d["active"] is not None:
        s["active"] = 1 if d["active"] else 0
    if "sort" in d and d["sort"] is not None:
        s["sort"] = int(d["sort"])
    return s


def criar(con, por, d):
    s = _dados(con, d, parcial=False)
    if s.get("kind") == "plan" and not s.get("months"):
        s["months"] = 1
    if um(con, "SELECT 1 AS x FROM booking_services WHERE lower(name)=lower(?) AND active=1", (s["name"],)):
        raise ErroServico("já existe um serviço ativo com esse nome")
    return inserir(con, "booking_services", **s, updated_by=por, updated_at=agora())


def mudar(con, por, sid, d):
    """Devolve {campo: (antes, depois)} — vai para a auditoria."""
    atual = um(con, "SELECT * FROM booking_services WHERE id=?", (sid,))
    if not atual:
        raise ErroServico("serviço não existe")
    s = _dados(con, d, parcial=True)
    mud = {k: (atual[k], v) for k, v in s.items() if atual[k] != v}
    if mud:
        atualizar(con, "booking_services", sid, **{k: v for k, (_, v) in mud.items()}, updated_by=por, updated_at=agora())
    return mud


def do_agendamento(con, sid):
    """O serviço escolhido pelo cliente: tem de existir e estar ativo."""
    s = um(con, "SELECT * FROM booking_services WHERE id=? AND active=1", (sid,)) if sid else None
    if not s:
        raise ErroServico("Choose the type of session.")
    return s

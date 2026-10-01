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
    sql = "SELECT * FROM booking_services" + (" WHERE active=1" if ativos else "") + " ORDER BY active DESC, sort, name"
    return [dict(s) for s in todos(con, sql)]


def para_cliente(con):
    """O que a área do cliente mostra: nome, descrição e preço. Nada do QuickBooks."""
    return [{"id": s["id"], "name": s["name"], "description": s["description"], "price": s["price"]} for s in lista(con, True)]


def itens_qbo(con):
    """Itens de serviço do QuickBooks (espelho local), para a equipe escolher."""
    return [dict(i) for i in todos(con, """SELECT id, name, full_name, price FROM qbo_items
                                            WHERE active=1 AND COALESCE(type,'Service')='Service' ORDER BY name""")]


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
    if "qbo_item_id" in d:
        item = (str(d["qbo_item_id"]).strip() if d["qbo_item_id"] is not None else "") or None
        if item and not um(con, "SELECT 1 AS x FROM qbo_items WHERE id=?", (item,)):
            raise ErroServico("item do QuickBooks não encontrado (sincronize o QuickBooks e tente de novo)")
        s["qbo_item_id"] = item
    if "active" in d and d["active"] is not None:
        s["active"] = 1 if d["active"] else 0
    if "sort" in d and d["sort"] is not None:
        s["sort"] = int(d["sort"])
    return s


def criar(con, por, d):
    s = _dados(con, d, parcial=False)
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

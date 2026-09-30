"""Pedidos internos e compras — as rotas. As regras moram em `providers/compras.py`.

**Quem pode o quê:**
- **pedir** é OPERATOR: quem está no box é quem sabe o que falta;
- **receber** é OPERATOR: quem abre a caixa conta o que chegou, e isso já vira estoque;
- **criar a compra, marcar pedida, cancelar** é MANAGER: é dinheiro saindo;
- **custo** só aparece para gerente, como no estoque.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import auditar, get_db, transacao, um
from command_center.providers import compras, estoque

r = APIRouter(prefix="/ops/api/compras", tags=["compras"])


def _gerente(u):
    return bool(u.get("free")) or auth.pode(u.get("role"), "MANAGER")


def _aud(con, request, u, evento, eid, detalhe, tipo="purchase_order"):
    auditar(con, evento, f"user:{u['id']}", user_id=u["id"], entity_type=tipo, entity_id=eid, detail=detalhe,
            ip=(request.client.host if request and request.client else None))


def _sem_custo(c, u):
    if _gerente(u):
        return c
    c = dict(c, total=None)
    c["linhas"] = [dict(l, unit_cost=None) for l in c["linhas"]]
    return c


# --------------------------------------------------------------------- pedidos
@r.get("/pedidos")
def listar_pedidos(status: str | None = None, limit: int | None = None, offset: int = 0,
                   con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    lim = None if limit is None else max(1, min(limit, 500))
    return {"pedidos": compras.pedidos(con, status or None, lim, offset),
            "total": compras.total_pedidos(con, status or None)}


class PedidoIn(BaseModel):
    item_id: int | None = None
    description: str | None = None
    qty: float
    unit: str | None = None
    client_id: int | None = None
    needed_by: str | None = None
    urgent: bool = False
    notes: str | None = None


@r.post("/pedidos", status_code=201)
def pedir(dados: PedidoIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    try:
        rid = compras.criar_pedido(con, u["id"], **dados.model_dump())
    except compras.ErroCompra as e:
        raise HTTPException(400, str(e))
    _aud(con, request, u, "purchase.request", rid, dados.model_dump(), "purchase_request")
    con.commit()
    return {"id": rid}


@r.post("/pedidos/{rid}/cancelar")
def cancelar_pedido(rid: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """Quem pediu cancela o próprio pedido; o gerente cancela qualquer um."""
    p = um(con, "SELECT requested_by FROM purchase_requests WHERE id=?", (rid,))
    if not p:
        raise HTTPException(404, "Pedido não encontrado.")
    if p["requested_by"] != u["id"] and not _gerente(u):
        raise HTTPException(403, "Só quem pediu (ou o gerente) cancela.")
    try:
        compras.mudar_pedido(con, rid, "cancelado")
    except compras.ErroCompra as e:
        raise HTTPException(400, str(e))
    _aud(con, request, u, "purchase.request.cancel", rid, {}, "purchase_request")
    con.commit()
    return {"ok": True}


@r.post("/pedidos/{rid}/entregue")
def entregar_pedido(rid: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    try:
        compras.mudar_pedido(con, rid, "entregue")
    except compras.ErroCompra as e:
        raise HTTPException(400, str(e))
    _aud(con, request, u, "purchase.request.delivered", rid, {}, "purchase_request")
    con.commit()
    return {"ok": True}


# --------------------------------------------------------------------- resumo
@r.get("/resumo")
def resumo(con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    abertos = compras.pedidos(con, "aberto")
    caminho = [c for c in compras.compras(con) if c["status"] in ("pedida", "parcial")]
    return {"pedidos_abertos": len(abertos), "urgentes": sum(1 for p in abertos if p["urgent"]),
            "rascunhos": len(compras.compras(con, "rascunho")), "a_caminho": len(caminho),
            "atrasadas": sum(1 for c in caminho if c["atrasada"]),
            "entregues": sum(1 for c in caminho if c["entregue_sem_entrada"]),
            "repor": [x for x in estoque.abaixo_do_minimo(con) if x["id"] not in {n["id"] for n in estoque.nunca_contados(con)}]}


# --------------------------------------------------------------------- compras
@r.get("")
def listar(status: str | None = None, limit: int = 200, offset: int = 0,
           con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    lista = [_sem_custo(c, u) for c in compras.compras(con, status or None, max(1, min(limit, 500)), offset)]
    if not _gerente(u):
        lista = [dict(c, email_total=None) for c in lista]
    return {"compras": lista, "gerente": _gerente(u), "total": compras.total_compras(con, status or None)}


@r.get("/{pid}")
def ver(pid: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    try:
        c = _sem_custo(compras.compra(con, pid), u)
    except compras.ErroCompra as e:
        raise HTTPException(404, str(e))
    for e in c["eventos"]:           # o e-mail no Gmail do urace@ (conta 0, como na caixa de entrada)
        e["link"] = f"https://mail.google.com/mail/u/0/#all/{e['thread_id']}" if e.get("thread_id") else None
    if c["status"] in ("rascunho", "pedida", "parcial"):
        c["pedidos_sugeridos"] = compras.pedidos_sugeridos(con, pid)
    if not _gerente(u):
        c["email_total"] = None
    return c


class LinhaIn(BaseModel):
    item_id: int | None = None
    description: str | None = None
    qty: float | None = None
    unit_cost: float | None = None
    request_id: int | None = None


class CompraIn(BaseModel):
    supplier: str | None = None
    reference: str | None = None
    expected_at: str | None = None
    notes: str | None = None
    pedir: bool = False
    linhas: list[LinhaIn]


@r.post("", status_code=201)
def criar(dados: CompraIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    try:
        with transacao(con):
            pid = compras.criar_compra(con, u["id"], [l.model_dump() for l in dados.linhas], supplier=dados.supplier,
                                       reference=dados.reference, expected_at=dados.expected_at, notes=dados.notes,
                                       pedir=dados.pedir)
            _aud(con, request, u, "purchase.create", pid, {"linhas": len(dados.linhas), "pedida": dados.pedir,
                                                           "fornecedor": dados.supplier})
    except compras.ErroCompra as e:
        raise HTTPException(400, str(e))
    return {"id": pid}


class PedidaIn(BaseModel):
    reference: str | None = None
    expected_at: str | None = None


@r.post("/{pid}/pedida")
def pedida(pid: int, dados: PedidaIn, request: Request, con: sqlite3.Connection = Depends(get_db),
           u=Depends(auth.exige("MANAGER"))):
    try:
        compras.marcar_pedida(con, pid, dados.reference, dados.expected_at)
    except compras.ErroCompra as e:
        raise HTTPException(400, str(e))
    _aud(con, request, u, "purchase.ordered", pid, dados.model_dump())
    con.commit()
    return {"ok": True}


@r.post("/{pid}/cancelar")
def cancelar(pid: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    try:
        with transacao(con):
            compras.cancelar_compra(con, pid)
            _aud(con, request, u, "purchase.cancel", pid, {})
    except compras.ErroCompra as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@r.post("/{pid}/linhas")
def adicionar(pid: int, dados: list[LinhaIn], request: Request, con: sqlite3.Connection = Depends(get_db),
              u=Depends(auth.exige("MANAGER"))):
    """Itens numa compra que já existe (a que nasceu de um e-mail vem sem itens)."""
    try:
        with transacao(con):
            ids = compras.adicionar_linhas(con, pid, [l.model_dump() for l in dados])
            _aud(con, request, u, "purchase.lines", pid, {"linhas": len(ids)})
    except compras.ErroCompra as e:
        raise HTTPException(400, str(e))
    return {"ids": ids}


class LigarIn(BaseModel):
    request_ids: list[int]


@r.post("/{pid}/pedidos")
def ligar(pid: int, dados: LigarIn, request: Request, con: sqlite3.Connection = Depends(get_db),
          u=Depends(auth.exige("MANAGER"))):
    """Os pedidos da equipe entram nesta compra: quem pediu passa a ver o envio."""
    try:
        with transacao(con):
            ids = compras.ligar_pedidos(con, pid, dados.request_ids)
            _aud(con, request, u, "purchase.link_requests", pid, {"pedidos": dados.request_ids})
    except compras.ErroCompra as e:
        raise HTTPException(400, str(e))
    return {"ids": ids}


@r.post("/{pid}/concluir")
def concluir(pid: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    """Fecha sem dar entrada no estoque: serviço, passe de pista, ferramenta que já foi para o uso."""
    try:
        with transacao(con):
            compras.concluir(con, pid)
            _aud(con, request, u, "purchase.close", pid, {})
    except compras.ErroCompra as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


class RecebidoIn(BaseModel):
    line_id: int
    qty: float
    criar_item: bool = False


class ReceberIn(BaseModel):
    local: str = estoque.SEDE
    itens: list[RecebidoIn]


@r.post("/{pid}/receber")
def receber(pid: int, dados: ReceberIn, request: Request, con: sqlite3.Connection = Depends(get_db),
            u=Depends(auth.exige("OPERATOR"))):
    """Tudo ou nada: se uma linha não serve, nada entra no estoque."""
    try:
        with transacao(con):
            res = compras.receber(con, pid, [i.model_dump() for i in dados.itens], por=u["id"], local=dados.local)
            _aud(con, request, u, "purchase.receive", pid, {"local": dados.local, **res})
    except compras.ErroCompra as e:
        raise HTTPException(400, str(e))
    return res

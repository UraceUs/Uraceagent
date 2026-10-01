"""Site público, visto de dentro (#41, #42): a agenda de sessões e, depois, as contas de
clientes. Quem abre e fecha a agenda é o gerente; confirmar e recusar pedido é da operação."""
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import auditar, get_db, transacao
from command_center.providers import agenda_sessoes as ag, servicos_site as sv, vinculo_site as vs

r = APIRouter(prefix="/ops/api/site", tags=["site"])


def _aud(con, request, u, evento, eid, detalhe):
    auditar(con, evento, f"user:{u['id']}", user_id=u["id"], entity_type="booking", entity_id=eid, detail=detalhe,
            ip=auth._ip(request))


def _d(v):
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        raise HTTPException(400, "data inválida (AAAA-MM-DD)")


@r.get("/agenda")
def ver_agenda(de: str | None = None, ate: str | None = None, con: sqlite3.Connection = Depends(get_db),
               u=Depends(auth.exige("OPERATOR"))):
    """Visão da equipe: o mês inteiro, com o porquê de cada período fechado e a ocupação."""
    try:
        disp = ag.disponibilidade(con, _d(de), _d(ate), visao="equipe")
    except ag.ErroAgenda as e:
        raise HTTPException(400, str(e))
    return {**disp, "semana": ag.semana(con), "bloqueios": ag.bloqueios(con), "config_completa": ag.config(con)}


class ConfigIn(BaseModel):
    morning_start: str | None = None
    morning_end: str | None = None
    afternoon_start: str | None = None
    afternoon_end: str | None = None
    auto_confirm: bool | None = None
    horizon_days: int | None = None
    min_notice_hours: int | None = None


@r.patch("/agenda/config")
def mudar_config(dados: ConfigIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    try:
        cfg = ag.mudar_config(con, u["id"], **dados.model_dump(exclude_unset=True))
    except ag.ErroAgenda as e:
        raise HTTPException(400, str(e))
    _aud(con, request, u, "booking.config", None, dados.model_dump(exclude_unset=True))
    con.commit()
    return cfg


class RegraIn(BaseModel):
    weekday: int
    period: str
    open: bool
    capacity: int = 1


@r.put("/agenda/semana")
def mudar_semana(regras: list[RegraIn], request: Request, con: sqlite3.Connection = Depends(get_db),
                 u=Depends(auth.exige("MANAGER"))):
    try:
        with transacao(con):
            s = ag.mudar_semana(con, [x.model_dump() for x in regras])
            _aud(con, request, u, "booking.week", None, {"regras": [x.model_dump() for x in regras]})
    except ag.ErroAgenda as e:
        raise HTTPException(400, str(e))
    return s


class BloqueioIn(BaseModel):
    date_from: str
    date_to: str | None = None
    period: str = "dia"
    reason: str | None = None


@r.post("/agenda/bloqueios", status_code=201)
def bloquear(dados: BloqueioIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    try:
        bid = ag.bloquear(con, u["id"], **dados.model_dump())
    except ag.ErroAgenda as e:
        raise HTTPException(400, str(e))
    _aud(con, request, u, "booking.block", bid, dados.model_dump())
    con.commit()
    return {"id": bid}


@r.post("/agenda/bloqueios/{bid}/remover")
def desbloquear(bid: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    try:
        ag.desbloquear(con, u["id"], bid)
    except ag.ErroAgenda as e:
        raise HTTPException(404, str(e))
    _aud(con, request, u, "booking.unblock", bid, {})
    con.commit()
    return {"ok": True}


@r.get("/agendamentos")
def agendamentos(status: str | None = None, de: str | None = None, ate: str | None = None,
                 con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    return {"agendamentos": ag.lista(con, status or None, de, ate)}


class DecisaoIn(BaseModel):
    nota: str | None = None


@r.post("/agendamentos/{bid}/{decisao}")
def decidir(bid: int, decisao: str, dados: DecisaoIn, request: Request, con: sqlite3.Connection = Depends(get_db),
            u=Depends(auth.exige("OPERATOR"))):
    if decisao not in ("confirmar", "recusar", "cancelar"):
        raise HTTPException(404, "decisão desconhecida")
    try:
        novo = ag.decidir(con, u["id"], bid, decisao, dados.nota)
    except ag.ErroAgenda as e:
        raise HTTPException(400, str(e))
    _aud(con, request, u, f"booking.{decisao}", bid, {"nota": dados.nota})
    con.commit()
    return {"status": novo}


# ------------------------------------------------------------------ serviços e preços (#50)
@r.get("/servicos")
def servicos(con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    return {"servicos": sv.lista(con), "itens_qbo": sv.itens_qbo(con)}


class ServicoIn(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | str | None = None
    qbo_item_id: str | None = None
    active: bool | None = None
    sort: int | None = None


@r.post("/servicos", status_code=201)
def criar_servico(dados: ServicoIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                  u=Depends(auth.exige("MANAGER"))):
    try:
        sid = sv.criar(con, u["id"], dados.model_dump(exclude_unset=True))
    except sv.ErroServico as e:
        raise HTTPException(400, str(e))
    auditar(con, "booking.service.create", f"user:{u['id']}", user_id=u["id"], entity_type="booking_service", entity_id=sid,
            detail=dados.model_dump(exclude_unset=True), ip=auth._ip(request))
    con.commit()
    return {"id": sid, "servicos": sv.lista(con)}


@r.patch("/servicos/{sid}")
def mudar_servico(sid: int, dados: ServicoIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                  u=Depends(auth.exige("MANAGER"))):
    """Mudar o preço vale para os próximos agendamentos; quem já marcou fica com o valor do dia."""
    try:
        mud = sv.mudar(con, u["id"], sid, dados.model_dump(exclude_unset=True))
    except sv.ErroServico as e:
        raise HTTPException(404 if "não existe" in str(e) else 400, str(e))
    if mud:
        auditar(con, "booking.service.update", f"user:{u['id']}", user_id=u["id"], entity_type="booking_service",
                entity_id=sid, detail={k: {"antes": a, "depois": d} for k, (a, d) in mud.items()}, ip=auth._ip(request))
    con.commit()
    return {"servicos": sv.lista(con)}


# ------------------------------------------------------------------ contas do site (#42)
@r.get("/contas")
def contas(filtro: str = "sem_vinculo", con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    if filtro not in ("sem_vinculo", "vinculadas", "todas"):
        raise HTTPException(400, "filtro inválido")
    return {"contas": vs.contas(con, filtro)}


class VincularIn(BaseModel):
    client_id: int


@r.post("/contas/{conta_id}/vincular")
def vincular(conta_id: int, dados: VincularIn, request: Request, con: sqlite3.Connection = Depends(get_db),
             u=Depends(auth.exige("OPERATOR"))):
    """Uma pessoa confirma: é o vínculo que abre para o cliente o histórico daquele card."""
    try:
        res = vs.vincular(con, conta_id, dados.client_id, u["id"])
    except vs.ErroVinculo as e:
        raise HTTPException(400, str(e))
    auditar(con, "portal.link", f"user:{u['id']}", user_id=u["id"], entity_type="portal_account", entity_id=conta_id,
            detail=res, ip=auth._ip(request))
    con.commit()
    return {"ok": True}


@r.post("/contas/{conta_id}/desvincular")
def desvincular(conta_id: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    try:
        res = vs.desvincular(con, conta_id)
    except vs.ErroVinculo as e:
        raise HTTPException(404, str(e))
    auditar(con, "portal.unlink", f"user:{u['id']}", user_id=u["id"], entity_type="portal_account", entity_id=conta_id,
            detail=res, ip=auth._ip(request))
    con.commit()
    return {"ok": True}


@r.get("/contas/do-cliente/{client_id}")
def do_cliente(client_id: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    return {"conta": vs.conta_do_cliente(con, client_id)}

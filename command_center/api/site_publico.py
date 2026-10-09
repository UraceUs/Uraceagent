"""Site público, visto de dentro (#41, #42): a agenda de sessões e, depois, as contas de
clientes. Quem abre e fecha a agenda é o gerente; confirmar e recusar pedido é da operação."""
import sqlite3
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import auditar, get_db, todos, transacao
from command_center.providers import agenda_asana, agenda_sessoes as ag, contrato, servicos_site as sv, vinculo_site as vs

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
    corridas = []
    if disp["dias"]:
        de_, ate_ = disp["dias"][0]["date"], disp["dias"][-1]["date"]
        corridas = todos(con, """SELECT id, name, series, track, city, date_start, COALESCE(date_end, date_start) AS date_end
                                   FROM races WHERE active=1 AND date_start IS NOT NULL AND date_start<=?
                                    AND COALESCE(date_end, date_start)>=? ORDER BY date_start""", (ate_, de_))
    return {**disp, "semana": ag.semana(con), "bloqueios": ag.bloqueios(con), "config_completa": ag.config(con),
            "corridas": corridas}


class ConfigIn(BaseModel):
    morning_start: str | None = None
    morning_end: str | None = None
    afternoon_start: str | None = None
    afternoon_end: str | None = None
    auto_confirm: bool | None = None
    auto_sell: bool | None = None          # #164: venda automática (só ADMIN ou o acesso livre liga ou desliga)
    horizon_days: int | None = None
    min_notice_hours: int | None = None


@r.patch("/agenda/config")
def mudar_config(dados: ConfigIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    if dados.auto_sell is not None and not (u.get("free") or u["role"] == "ADMIN"):
        raise HTTPException(403, "Só o administrador liga ou desliga a venda automática.")
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
    date_from: str | None = None
    date_to: str | None = None
    period: str = "dia"
    reason: str | None = None
    weekday: int | None = None             # recorrente: 0 = segunda


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
    lista = ag.lista(con, status or None, de, ate)
    from command_center.providers import cobranca_agenda
    for a in lista:                          # contrato mensal: só a equipe vê (#61)
        a["contrato"] = contrato.situacao_do_agendamento(con, a["client_id"], a["date"])
        a["cobranca"] = cobranca_agenda.situacao(con, a) if a.get("accepted_at") else None
    return {"agendamentos": lista}


class DecisaoIn(BaseModel):
    nota: str | None = None


@r.post("/agendamentos/{bid}/{decisao}")
def decidir(bid: int, decisao: str, dados: DecisaoIn, request: Request, tarefas: BackgroundTasks,
            con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    if decisao not in ("aceitar", "confirmar", "recusar", "cancelar"):
        raise HTTPException(404, "decisão desconhecida")
    if decisao == "confirmar" and not (u.get("free") or auth.pode(u["role"], "MANAGER")):
        # #50: confirmar sem esperar pagamento e waiver é decisão do gerente; a equipe aceita a vaga
        raise HTTPException(403, "Confirmar sem esperar pagamento e waiver é do gerente. Use Aceitar.")
    try:
        if decisao == "aceitar":
            from command_center.providers import cobranca_agenda
            res = cobranca_agenda.aceitar(con, u["id"], bid)
            novo = res["status"]
        else:
            novo = ag.decidir(con, u["id"], bid, decisao, dados.nota)
            res = None
    except ag.ErroAgenda as e:
        raise HTTPException(400, str(e))
    _aud(con, request, u, f"booking.{decisao}", bid, {"nota": dados.nota, **({"cobranca": res} if res else {})})
    con.commit()
    tarefas.add_task(agenda_asana.levar, bid)      # #67: a situação nova vai para a tarefa do Asana
    return {"status": novo, "cobranca": res}


# ------------------------------------------------------------------ serviços e preços (#50)
@r.get("/servicos")
def servicos(con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    return {"servicos": sv.lista(con), "itens_qbo": sv.itens_qbo(con)}


class ServicoIn(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | str | None = None
    qbo_item_id: str | None = None
    qbo_item: str | None = None             # texto livre: o nome de um item, ou o texto da linha (#61)
    deposit: float | str | None = None      # #50: depósito por sessão; vazio ou 0 = sem depósito
    kind: str | None = None                 # #169: session (avulsa) | plan (mensal: price é por mês)
    months: int | str | None = None         # #169: meses do compromisso do plano
    sessions_month: int | str | None = None # #169: sessões por mês que o plano dá (vira o contrato do card)
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


@r.post("/contas/{conta_id}/criar-cliente", status_code=201)
def criar_cliente(conta_id: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """Cliente novo, que não existe no site interno: o card nasce com os dados da conta e já
    fica vinculado (#52). Se já existe alguém com o mesmo e-mail ou telefone, recusa."""
    try:
        with transacao(con):
            cid = vs.criar_cliente(con, conta_id, u["id"])
            auditar(con, "portal.client.create", f"user:{u['id']}", user_id=u["id"], entity_type="portal_account",
                    entity_id=conta_id, detail={"client_id": cid}, ip=auth._ip(request))
    except vs.ErroVinculo as e:
        raise HTTPException(400, str(e))
    return {"client_id": cid}


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


# ------------------------------------------------------------------ um card por driver (#65)
@r.post("/drivers/{pilot_id}/vincular")
def vincular_driver(pilot_id: int, dados: VincularIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                    u=Depends(auth.exige("OPERATOR"))):
    """Cada driver tem o seu card (Client ID). Uma pessoa confirma qual."""
    try:
        res = vs.vincular_driver(con, pilot_id, dados.client_id, u["id"])
    except vs.ErroVinculo as e:
        raise HTTPException(400, str(e))
    auditar(con, "portal.driver.link", f"user:{u['id']}", user_id=u["id"], entity_type="portal_pilot", entity_id=pilot_id,
            detail=res, ip=auth._ip(request))
    con.commit()
    return {"ok": True}


@r.post("/drivers/{pilot_id}/criar-cliente", status_code=201)
def criar_cliente_driver(pilot_id: int, request: Request, con: sqlite3.Connection = Depends(get_db),
                         u=Depends(auth.exige("OPERATOR"))):
    """Card novo para o driver: o responsável e o contato da conta, o piloto é o driver."""
    try:
        with transacao(con):
            cid = vs.criar_cliente_driver(con, pilot_id, u["id"])
            auditar(con, "portal.driver.client.create", f"user:{u['id']}", user_id=u["id"], entity_type="portal_pilot",
                    entity_id=pilot_id, detail={"client_id": cid}, ip=auth._ip(request))
    except vs.ErroVinculo as e:
        raise HTTPException(400, str(e))
    return {"client_id": cid}


@r.post("/drivers/{pilot_id}/desvincular")
def desvincular_driver(pilot_id: int, request: Request, con: sqlite3.Connection = Depends(get_db),
                       u=Depends(auth.exige("MANAGER"))):
    try:
        res = vs.desvincular_driver(con, pilot_id)
    except vs.ErroVinculo as e:
        raise HTTPException(404, str(e))
    auditar(con, "portal.driver.unlink", f"user:{u['id']}", user_id=u["id"], entity_type="portal_pilot", entity_id=pilot_id,
            detail=res, ip=auth._ip(request))
    con.commit()
    return {"ok": True}


@r.get("/contas/do-cliente/{client_id}")
def do_cliente(client_id: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    return {"conta": vs.conta_do_cliente(con, client_id)}


# ------------------------------------------------------------------ waiver assinada aqui (#85)
class WaiverNativaIn(BaseModel):
    ligada: bool


@r.get("/waiver-nativa")
def waiver_nativa(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                  con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    """Ligada ou não, os dois modelos importados (nome, hash, quando) e as assinadas aqui (paginadas)."""
    from command_center.providers import waiver_nativa as wn
    return {"ligada": wn.ligada(con), "modelos": wn.modelos(con), "assinadas": wn.listar(con, limit, offset)}


@r.post("/waiver-nativa/importar")
def waiver_nativa_importar(request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("ADMIN"))):
    """LÊ os dois modelos no DocuSign (nome + PDF) e guarda aqui. Não muda nada no DocuSign."""
    from command_center.providers import NaoConectado
    from command_center.providers import waiver_nativa as wn
    try:
        feitos = wn.importar_do_docusign(con, u["id"])
    except NaoConectado as e:
        raise HTTPException(503, f"DocuSign não conectado: {e}")
    except ValueError as e:
        raise HTTPException(409, str(e))
    _aud(con, request, u, "waiver_nativa.importar", None, {"modelos": feitos})
    con.commit()
    return {"modelos": wn.modelos(con)}


@r.post("/waiver-nativa/ligar")
def waiver_nativa_ligar(dados: WaiverNativaIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                        u=Depends(auth.exige("ADMIN"))):
    """Liga ou desliga a assinatura na área do cliente. Desligar não apaga nada já assinado."""
    from command_center.providers import waiver_nativa as wn
    try:
        ligada = wn.ligar(con, dados.ligada, u["id"])
    except ValueError as e:
        raise HTTPException(409, str(e))
    _aud(con, request, u, "waiver_nativa.ligar", None, {"ligada": ligada})
    con.commit()
    return {"ligada": ligada, "modelos": wn.modelos(con)}

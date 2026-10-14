"""Atendimento humano — as rotas (missão de 14/10). A lógica mora em providers/atendimento.py.

    POST /ops/api/atendimento/casos              escalate_to_human (IA pela chave de API, ou pessoa)
    GET  /ops/api/atendimento/casos              fila: pendentes, em atendimento, atrasados, sem
                                                 responsável, resolvidos (paginada)
    GET  /ops/api/atendimento/casos/{id}         o caso, a linha do tempo e os avisos
    POST /ops/api/atendimento/casos/{id}/assumir | transferir | encerrar | devolver | responder
    GET  /ops/api/atendimento/conversa/{lead}    o estado da conversa e se a IA pode responder
    GET  /ops/api/atendimento/saude              fila de avisos, ponte devendo confirmação

Quem pode o quê:
  * abrir caso: OPERATOR+ (pessoa ou chave de API que não seja só-leitura — é o caminho da IA);
  * assumir, transferir, encerrar, devolver, responder: só PESSOA (chave de API recebe 403), e
    encerrar/devolver/transferir só quem atende ou um gerente;
  * ler: qualquer pessoa logada.
"""
import sqlite3
import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from command_center.api import auth
from command_center.db import get_db
from command_center.providers import atendimento as at

r = APIRouter(prefix="/ops/api/atendimento", tags=["atendimento"])

# Uma IA em laço não pode encher a equipe de avisos. Teto de abertura por credencial; quem passa
# recebe 429 e a ponte guarda o pedido para tentar de novo (nada se perde).
LIMITE_POR_MIN = 30
_janela = defaultdict(deque)
_trava = threading.Lock()


def _limitar(u):
    chave = u.get("via") or f"user:{u['id']}"
    agora_s = time.monotonic()
    with _trava:
        fila = _janela[chave]
        while fila and agora_s - fila[0] > 60:
            fila.popleft()
        if len(fila) >= LIMITE_POR_MIN:
            raise HTTPException(429, "Muitos escalonamentos em um minuto. Tente de novo em instantes.")
        fila.append(agora_s)


def _rid(request):
    return getattr(request.state, "request_id", None) or request.headers.get("x-request-id")


def _http(e):
    return HTTPException(getattr(e, "codigo", 400), str(e))


class CasoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: str | int
    reason: str
    priority: str | None = "normal"
    summary: str | None = None
    customer_name: str | None = None
    requested_action: str | None = None
    category: str | None = None
    channel: str | None = None
    idempotency_key: str | None = None
    origin: str | None = None          # ia | regra | humano (padrão: ia para chave, humano para pessoa)
    assume: bool = False               # a pessoa que abre já assume (abertura manual pelo painel)


@r.post("/casos", status_code=201)
def abrir(dados: CasoIn, request: Request, idempotency_key: str | None = Header(default=None),
          u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    _limitar(u)
    por_chave = str(u.get("via") or "").startswith("key:")
    origem = dados.origin or ("ia" if por_chave else "humano")
    if dados.assume and por_chave:
        raise HTTPException(403, "Chave de API não assume atendimento: só uma pessoa.")
    try:
        res = at.abrir_caso(con, conversation_id=dados.conversation_id, reason=dados.reason,
                            priority=dados.priority, summary=dados.summary, customer_name=dados.customer_name,
                            requested_action=dados.requested_action, category=dados.category, canal=dados.channel,
                            chave=dados.idempotency_key or idempotency_key, origem=origem, u=u,
                            correlacao=_rid(request), assumir=dados.assume)
    except at.ErroAtendimento as e:
        raise _http(e)
    return res


@r.get("/casos")
def lista(filtro: str = "abertos", limit: int = 50, offset: int = 0, lead: int | None = None,
          u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    try:
        return at.listar(con, filtro, limit, offset, kommo_lead_id=lead)
    except at.ErroAtendimento as e:
        raise _http(e)


@r.get("/casos/{cid}")
def ver(cid: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    try:
        d = at.detalhe(con, cid)
    except at.ErroAtendimento as e:
        raise _http(e)
    d["pode"] = _o_que_pode(d, u)
    return d


def _o_que_pode(c, u):
    pessoa = not str(u.get("via") or "").startswith("key:")
    opera = pessoa and (u.get("free") or auth.pode(u.get("role"), "OPERATOR")) and not u.get("somente_leitura")
    dono = c.get("responsavel_id") == u.get("id") or u.get("free") or auth.pode(u.get("role"), "MANAGER")
    return {"assumir": bool(opera and c["estado"] == "HUMAN_PENDING"),
            "transferir": bool(opera and dono and c["estado"] == "HUMAN_ACTIVE"),
            "encerrar": bool(opera and dono and c["estado"] == "HUMAN_ACTIVE" and not c.get("ponte_pendente")),
            "devolver": bool(opera and dono and c["estado"] == "HUMAN_ACTIVE" and not c.get("ponte_pendente")),
            "responder": bool(opera and dono and c["estado"] == "HUMAN_ACTIVE" and c.get("crm_lead_id"))}


@r.post("/casos/{cid}/assumir")
def assumir(cid: int, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    try:
        return at._publico(con, at.assumir_caso(con, cid, u, correlacao=_rid(request)))
    except at.ErroAtendimento as e:
        raise _http(e)


class TransferirIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    para_user_id: int


@r.post("/casos/{cid}/transferir")
def transferir(cid: int, dados: TransferirIn, request: Request, u=Depends(auth.exige("OPERATOR")),
               con: sqlite3.Connection = Depends(get_db)):
    try:
        return at._publico(con, at.transferir_caso(con, cid, u, dados.para_user_id, correlacao=_rid(request)))
    except at.ErroAtendimento as e:
        raise _http(e)


class TextoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    texto: str


def _fechamento(con, cid, u, request, fn, texto):
    try:
        c, erro = fn(con, cid, u, texto, correlacao=_rid(request))
    except at.ErroAtendimento as e:
        raise _http(e)
    d = at._publico(con, c)
    if erro:
        # 202: pedido aceito, ainda não feito. A conversa continua com a pessoa (e a IA travada)
        # até a ponte confirmar; o laço tenta de novo sozinho.
        d["aviso"] = (f"A ponte não confirmou ({erro}). A conversa continua com você e a IA segue travada; "
                      "o sistema tenta de novo a cada meio minuto.")
    return d


@r.post("/casos/{cid}/encerrar")
def encerrar(cid: int, dados: TextoIn, request: Request, u=Depends(auth.exige("OPERATOR")),
             con: sqlite3.Connection = Depends(get_db)):
    return _fechamento(con, cid, u, request, at.encerrar_caso, dados.texto)


@r.post("/casos/{cid}/devolver")
def devolver(cid: int, dados: TextoIn, request: Request, u=Depends(auth.exige("OPERATOR")),
             con: sqlite3.Connection = Depends(get_db)):
    return _fechamento(con, cid, u, request, at.devolver_caso, dados.texto)


@r.post("/casos/{cid}/responder")
def responder(cid: int, dados: TextoIn, request: Request, u=Depends(auth.exige("OPERATOR")),
              con: sqlite3.Connection = Depends(get_db)):
    """A resposta da pessoa ao cliente, pelo canal oficial: o mesmo circuito do chat do Kommo no
    painel (fila → continuação do Salesbot → WhatsApp/Instagram), com recibo e nota de reserva.
    Sai como mensagem humana: a ponte nunca a lê como mensagem do cliente (ver docs)."""
    from command_center.api import crm
    try:
        at._pessoa(u)
        c = at.caso(con, cid)
    except at.ErroAtendimento as e:
        raise _http(e)
    if c["estado"] != "HUMAN_ACTIVE":
        raise HTTPException(409, "Assuma o caso antes de responder.")
    if c["responsavel_id"] != u["id"] and not (u.get("free") or auth.pode(u.get("role"), "MANAGER")):
        raise HTTPException(403, "Quem responde é quem está atendendo (ou um gerente).")
    if not c["crm_lead_id"]:
        raise HTTPException(409, "Este lead ainda não está no espelho do Kommo do painel: responda pelo Kommo "
                                 "(link no caso).")
    res = crm.responder(c["crm_lead_id"], crm.TextoIn(text=dados.texto), request, u, con)
    ator, nome = at._ator(u)
    at._evento(con, cid, "resposta_humana", ator, nome, detalhe={"msg": res.get("msg_id"), "como": res.get("como")},
               correlacao=_rid(request))
    return res


@r.get("/conversa/{lead}")
def conversa(lead: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    try:
        lead = at.lead_da_conversa(lead)
    except at.ErroAtendimento as e:
        raise _http(e)
    aberto = at.caso_aberto(con, lead)
    return {"conversa": f"kommo:{lead}", "estado": at.estado_conversa(con, lead),
            "caso_aberto": aberto["id"] if aberto else None,
            "ia_travada": at.ia_travada(lead), "ia_pode_responder": not at.ia_travada(lead)}


@r.get("/saude")
def saude(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    return at.saude(con)


@r.get("/pessoas")
def pessoas(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Para quem transferir: quem atende cliente (operador ou acima, ativo, sem cargo de box)."""
    from command_center.db import todos
    return {"pessoas": todos(con, "SELECT id, name, role FROM users WHERE active=1 AND role IN ('ADMIN','MANAGER','OPERATOR') "
                                  "AND (cargo IS NULL OR cargo='') ORDER BY name")}

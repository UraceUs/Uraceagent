"""Vendas: o fluxo do closer (dono, 17/09) — aprovado no canvas antes de entrar aqui.

Closer aqui é a PESSOA que vende, não um papel do sistema: quem vende é OPERATOR e a
área de vendas é uma tela do operador (correção do dono, 17/09).

Oportunidade NÃO é cliente: vive em `opportunities`, com linha do tempo própria
(`opp_events`), e só vira card de cliente no Ganho. O closer liga por fora e registra
tudo aqui: ligação, retorno, anotação, etapa. Quando fecha, UMA tela dispara a lista:
card do cliente, cliente e invoice no QuickBooks, waiver no DocuSign, tarefa no Asana,
Kommo em "Closed won" e as tarefas personalizadas que ele escrever.

Travas: cada passo é gravado com resultado; falha de um não derruba os outros. Valor fora
da tabela de preços não bloqueia o fechamento — a invoice fica pendente até o gerente ou o
dono conferir o valor e liberar (#204, dono, 14/10: "precisa confirmar o valor da invoice").
O preço da tabela vem do catálogo, nunca do valor da venda; o depósito de segurança entra na
invoice quando o serviço pede, como na venda automática. Nada de e-mail livre: o Gmail do painel é só
leitura, então "e-mail" só existe como waiver/invoice (que o próprio sistema envia) ou
como tarefa personalizada.
"""
import json
import os
import sqlite3

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import agora, atualizar, auditar, get_db, inserir, todos, transacao, um
from command_center.providers import NaoConectado, chamar, modulo

r = APIRouter(prefix="/ops/api/sales", tags=["sales"])

ETAPAS = ("NOVO", "CONVERSA", "PROPOSTA", "FECHAMENTO", "GANHO", "PERDIDO")
ETAPA_PT = {"NOVO": "Novo", "CONVERSA": "Em conversa", "PROPOSTA": "Proposta",
            "FECHAMENTO": "Fechamento", "GANHO": "Ganho", "PERDIDO": "Perdido"}
RESULTADOS = {"fechou": "Atendeu · fechou", "pensar": "Atendeu · vai pensar", "nao_atendeu": "Não atendeu",
              "sem_interesse": "Sem interesse", "remarcou": "Remarcou"}
PASSOS = ("cliente", "qbo", "waiver", "asana", "kommo")
PASSO_PT = {"cliente": "Card do cliente", "qbo": "Cliente e invoice no QuickBooks",
            "waiver": "Waiver no DocuSign", "asana": "Tarefa no Asana", "kommo": "Kommo: Closed won"}
# o ícone da linha do tempo vem do `kind`: cada passo fala a mesma língua do resto do painel
PASSO_KIND = {"cliente": "client", "qbo": "invoice", "waiver": "waiver", "asana": "asana", "kommo": "kommo"}


# --------------------------------------------------------------- base
def _ev(con, opp_id, kind, title, detail=None, actor=None, ok=None, at=None):
    return inserir(con, "opp_events", opp_id=opp_id, kind=kind, title=title,
                   detail=json.dumps(detail, ensure_ascii=False) if isinstance(detail, (dict, list)) else detail,
                   at=at or agora(), actor=actor, ok=ok)


def _opp(con, oid, u=None):
    o = um(con, """SELECT o.*, u.name AS closer_name, c.name AS client_name, c.pilot_name AS client_pilot
                   FROM opportunities o LEFT JOIN users u ON u.id=o.closer_user_id
                   LEFT JOIN clients c ON c.id=o.client_id WHERE o.id=?""", (oid,))
    if not o:
        raise HTTPException(404, "Oportunidade não encontrada.")
    o["closing"] = json.loads(o["closing"] or "null")
    o["campaign"] = json.loads(o["campaign"] or "null")       # #260: de onde o contato do site veio
    return o


def _limpa(v):
    return (v or "").strip() or None


def _fuso():
    from command_center.api.agenda import FUSO
    return FUSO


def hoje_local():
    """Data de hoje na Florida — "tudo no sistema roda no fuso EDT" (dono, 17/09)."""
    from datetime import datetime
    return datetime.now(_fuso()).date().isoformat()


def quando_pt(iso):
    """"2026-09-19T14:00:00Z" → "19/09 10:00" (hora da Florida), para o texto do evento."""
    from datetime import datetime, timezone
    if not iso:
        return "—"
    t = str(iso).replace("Z", "+00:00")
    if len(t) == 10:                     # só a data: não invento hora
        return t[8:10] + "/" + t[5:7]
    try:
        d = datetime.fromisoformat(t)
    except ValueError:
        return str(iso)[:16].replace("T", " ")
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(_fuso()).strftime("%d/%m %H:%M")


def fim_do_dia_local():
    """Fim do dia da Florida, em UTC — para comparar com o que está gravado."""
    from datetime import datetime, time, timezone
    fim = datetime.combine(datetime.now(_fuso()).date(), time(23, 59, 59), tzinfo=_fuso())
    return fim.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dia_local(iso):
    """Data (na Florida) de um instante gravado em UTC."""
    from datetime import datetime, timezone
    if not iso:
        return None
    t = str(iso).replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(t)
    except ValueError:
        return str(iso)[:10]
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(_fuso()).date().isoformat()


def _google(tarefas: BackgroundTasks, oid):
    """#220: o retorno vai para o Google Calendar do closer conectado — depois da resposta, sem
    atrasar a tela; falhou, o laço automático tenta de novo."""
    from command_center.providers import google_agenda
    tarefas.add_task(google_agenda.sincronizar_em_segundo_plano, oid)


def _aplicando(sistema, fn, *a, **kw):
    """Clique humano: APLICAR ligado só nesta thread e nesta chamada (mesmo padrão do CRM)."""
    try:
        m = modulo(sistema)
    except NaoConectado:
        raise
    ctx = getattr(m, "_ctx", None)
    if ctx is None:
        anterior = os.environ.get("APLICAR")
        os.environ["APLICAR"] = "1"
        try:
            return fn(*a, **kw)
        finally:
            if anterior is None:
                os.environ.pop("APLICAR", None)
            else:
                os.environ["APLICAR"] = anterior
    ctx.aplicar = True
    try:
        return fn(*a, **kw)
    finally:
        ctx.aplicar = None


# --------------------------------------------------------------- leitura
@r.get("/board")
def board(minhas: bool = False, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """O quadro: uma coluna por etapa, na ordem do fluxo. `minhas=1` filtra as suas."""
    so_minhas = minhas
    where, args = "", []
    if so_minhas:
        where, args = "WHERE (o.closer_user_id=? OR o.closer_user_id IS NULL)", [u["id"]]
    ops = todos(con, f"""SELECT o.*, u.name AS closer_name,
                                (SELECT COUNT(*) FROM opp_events e WHERE e.opp_id=o.id AND e.kind='call') AS calls
                         FROM opportunities o LEFT JOIN users u ON u.id=o.closer_user_id {where}
                         ORDER BY COALESCE(o.next_at, o.updated_at) ASC""", tuple(args))
    for o in ops:
        o["closing"] = json.loads(o["closing"] or "null")
    hoje = hoje_local()
    colunas = []
    for e in ETAPAS:
        na = [o for o in ops if o["stage"] == e]
        if e in ("GANHO", "PERDIDO"):                        # fechadas: só as recentes
            na = [o for o in na if (o["updated_at"] or "") >= _dias_atras(7)][:20]
        colunas.append({"etapa": e, "nome": ETAPA_PT[e], "total": len(na),
                        "valor": round(sum(o["amount"] or 0 for o in na), 2), "oportunidades": na})
    abertas = [o for o in ops if o["stage"] not in ("GANHO", "PERDIDO")]
    return {"colunas": colunas, "abertas": len(abertas),
            "retornos_hoje": sum(1 for o in abertas if dia_local(o["next_at"]) == hoje),
            "atrasados": sum(1 for o in abertas if o["next_at"] and o["next_at"] < agora()),
            "so_minhas": so_minhas}


def _dias_atras(n):
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%SZ")


@r.get("/agenda")
def agenda(dias: int = 7, minhas: bool = False, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Agenda de vendas: retornos marcados, atrasado primeiro. `minhas=1` mostra só os seus."""
    where, args = "WHERE o.next_at IS NOT NULL AND o.stage NOT IN ('GANHO','PERDIDO')", []
    if minhas:
        where += " AND (o.closer_user_id=? OR o.closer_user_id IS NULL)"
        args.append(u["id"])
    ops = todos(con, f"""SELECT o.id, o.name, o.pilot_name, o.service, o.amount, o.stage, o.source,
                                o.next_at, o.next_what, o.phone, o.email, u.name AS closer_name
                         FROM opportunities o LEFT JOIN users u ON u.id=o.closer_user_id
                         {where} ORDER BY o.next_at ASC LIMIT 200""", tuple(args))
    agora_ = agora()
    for o in ops:
        o["atrasado"] = bool(o["next_at"] and o["next_at"] < agora_)
    feitas = todos(con, """SELECT e.at, e.title, o.name FROM opp_events e JOIN opportunities o ON o.id=e.opp_id
                           WHERE e.kind='call' AND e.at >= ? ORDER BY e.at DESC LIMIT 50""", (_dias_atras(2),))
    hoje = hoje_local()
    feitas = [f for f in feitas if dia_local(f["at"]) == hoje]
    return {"retornos": ops, "ligacoes_hoje": feitas, "dias": dias}


@r.get("/catalogo")
def catalogo_rota(q: str | None = None, limit: int = 300, offset: int = 0, u=Depends(auth.usuario_atual),
                  con: sqlite3.Connection = Depends(get_db)):
    """Os itens do catálogo do QuickBooks para a tela de fechar: o preço da tabela vem daqui (#204)."""
    itens, total = catalogo(con, q, limit, offset)
    return {"itens": itens, "total": total, "limit": limit, "offset": offset}


@r.get("/{oid}")
def detalhe(oid: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    o = _opp(con, oid, u)
    ref = item_da_tabela(con, o["service"], o.get("qbo_item_id"))
    card = _achar_card(con, o) if o["stage"] != "GANHO" else None
    evs = todos(con, "SELECT * FROM opp_events WHERE opp_id=? ORDER BY at DESC, id DESC LIMIT 200", (oid,))
    for e in evs:
        if e["detail"] and e["detail"].startswith(("{", "[")):
            try:
                e["detail"] = json.loads(e["detail"])
            except ValueError:
                pass
    from command_center.providers import carrinho        # #236: o pedido do site com as linhas
    na_tabela = _confere_preco(o["amount"], ref["preco"] if ref else None)[0]
    return {"oportunidade": o, "eventos": evs, "pedido": carrinho.do_painel(con, oid),
            # #204: o preço da tabela (do catálogo) e o card em que o fechamento cairia — se for de
            # outro piloto, a tela pergunta se é irmão
            "tabela": ref, "pode_liberar": gerente(u),
            # #310: enviada | esperando | livre — só depois de fechar (antes, não há invoice a liberar)
            "invoice": estado_da_invoice(o, na_tabela) if _fechada(o["closing"]) else None,
            # #310 (A1): invoice criada no QuickBooks cujo envio falhou — sai de novo só pelo Reenviar (a mesma)
            "nao_enviadas": nao_enviadas(o["closing"]),
            "card": card and {"id": card["id"], "name": card["name"], "pilot_name": card["pilot_name"],
                              "outro_piloto": _outro_piloto(card, o)},
            "etapas": [{"codigo": k, "nome": v} for k, v in ETAPA_PT.items()],
            "resultados": [{"codigo": k, "nome": v} for k, v in RESULTADOS.items()]}


# --------------------------------------------------------------- escrita
class OppIn(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    pilot_name: str | None = None
    pilot_age: int | None = None
    service: str | None = None
    service_date: str | None = None
    service_time: str | None = None
    amount: float | None = None
    source: str | None = None
    notes: str | None = None
    next_at: str | None = None
    next_what: str | None = None
    crm_lead_id: int | None = None
    stage: str | None = None
    client_id: int | None = None          # #158: vincular ao cliente já na criação


def _campos(d: OppIn):
    campos = {k: v for k, v in d.model_dump().items() if v is not None}
    for k in ("name", "email", "phone", "pilot_name", "service", "notes", "next_what", "source"):
        if k in campos:
            campos[k] = _limpa(str(campos[k]))
    if campos.get("email"):
        campos["email"] = campos["email"].lower()
    if campos.get("stage") and campos["stage"] not in ETAPAS:
        raise HTTPException(400, f"Etapa inválida. Use: {', '.join(ETAPAS)}")
    return campos


@r.post("", status_code=201)
def criar(dados: OppIn, request: Request, tarefas: BackgroundTasks, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """Nova oportunidade: o closer cria durante a ligação, em segundos."""
    campos = _campos(dados)
    if not campos.get("name"):
        raise HTTPException(400, "Nome é obrigatório.")
    ja = None
    if campos.get("client_id"):            # vinculado no formulário (#158): o fechamento cai neste card
        ja = um(con, "SELECT id, name FROM clients WHERE id=?", (campos["client_id"],))
        if not ja:
            raise HTTPException(400, "Cliente não existe.")
    elif campos.get("email"):
        ja = um(con, "SELECT id, name FROM clients WHERE email=?", (campos["email"],))
    oid = inserir(con, "opportunities", closer_user_id=u["id"], updated_at=agora(), **campos)
    _ev(con, oid, "stage", f"Oportunidade criada em {ETAPA_PT[campos.get('stage', 'NOVO')]}",
        {"origem": campos.get("source"), "ja_e_cliente": ja["name"] if ja else None}, f"user:{u['id']}", 1)
    auditar(con, "sales.create", f"user:{u['id']}", user_id=u["id"], entity_type="opportunity", entity_id=oid,
            detail={"nome": campos.get("name"), "origem": campos.get("source")}, ip=auth._ip(request))
    con.commit()
    if campos.get("next_at"):
        _google(tarefas, oid)
    return {"id": oid, "ja_e_cliente": ja and {"id": ja["id"], "nome": ja["name"]}}


@r.patch("/{oid}")
def editar(oid: int, dados: OppIn, request: Request, tarefas: BackgroundTasks, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    o = _opp(con, oid, u)
    campos = _campos(dados)
    if campos.get("client_id") and not um(con, "SELECT id FROM clients WHERE id=?", (campos["client_id"],)):
        raise HTTPException(400, "Cliente não existe.")
    atualizar(con, "opportunities", oid, updated_at=agora(), **campos)
    mudou = {k: v for k, v in campos.items() if str(o.get(k) or "") != str(v or "")}
    if mudou:
        _ev(con, oid, "note", "Ficha editada", mudou, f"user:{u['id']}")
    auditar(con, "sales.update", f"user:{u['id']}", user_id=u["id"], entity_type="opportunity", entity_id=oid,
            detail=mudou, ip=auth._ip(request))
    con.commit()
    if "next_at" in mudou or "next_what" in mudou or "name" in mudou or "service" in mudou:
        _google(tarefas, oid)
    return {"ok": True, "mudou": sorted(mudou)}


class LigacaoIn(BaseModel):
    resultado: str
    minutos: int | None = None
    texto: str | None = None
    proximo_em: str | None = None
    proximo_que: str | None = None
    etapa: str | None = None


@r.post("/{oid}/call")
def ligacao(oid: int, dados: LigacaoIn, request: Request, tarefas: BackgroundTasks, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """Registrar a ligação (ditada ou digitada): resultado, o que foi dito e o próximo passo."""
    o = _opp(con, oid, u)
    if dados.resultado not in RESULTADOS:
        raise HTTPException(400, f"Resultado inválido. Use: {', '.join(RESULTADOS)}")
    titulo = RESULTADOS[dados.resultado] + (f" · {dados.minutos} min" if dados.minutos else "")
    _ev(con, oid, "call", titulo, _limpa(dados.texto), f"user:{u['id']}", 1 if dados.resultado != "nao_atendeu" else 0)
    campos = {"updated_at": agora()}
    if dados.proximo_em:
        campos.update(next_at=dados.proximo_em, next_what=_limpa(dados.proximo_que) or "retorno")
        _ev(con, oid, "next", f"Retorno marcado: {quando_pt(dados.proximo_em)}", _limpa(dados.proximo_que), f"user:{u['id']}")
    elif dados.resultado in ("fechou", "sem_interesse"):
        campos.update(next_at=None, next_what=None)
    etapa = dados.etapa or ("FECHAMENTO" if dados.resultado == "fechou" else
                            "CONVERSA" if o["stage"] == "NOVO" and dados.resultado != "sem_interesse" else None)
    if etapa and etapa in ETAPAS and etapa != o["stage"]:
        campos["stage"] = etapa
        _ev(con, oid, "stage", f"{ETAPA_PT[o['stage']]} → {ETAPA_PT[etapa]}", None, f"user:{u['id']}")
    atualizar(con, "opportunities", oid, **campos)
    auditar(con, "sales.call", f"user:{u['id']}", user_id=u["id"], entity_type="opportunity", entity_id=oid,
            detail={"resultado": dados.resultado, "etapa": campos.get("stage")}, ip=auth._ip(request))
    con.commit()
    _google(tarefas, oid)
    return {"ok": True, "etapa": campos.get("stage", o["stage"]), "next_at": campos.get("next_at", o["next_at"])}


class RetornoIn(BaseModel):
    quando: str
    o_que: str | None = None


@r.post("/{oid}/next")
def retorno(oid: int, dados: RetornoIn, tarefas: BackgroundTasks, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    _opp(con, oid, u)
    atualizar(con, "opportunities", oid, next_at=dados.quando, next_what=_limpa(dados.o_que) or "retorno", updated_at=agora())
    _ev(con, oid, "next", f"Retorno marcado: {quando_pt(dados.quando)}", _limpa(dados.o_que), f"user:{u['id']}")
    con.commit()
    _google(tarefas, oid)
    return {"ok": True}


class TextoIn(BaseModel):
    texto: str


@r.post("/{oid}/note")
def anotar(oid: int, dados: TextoIn, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    o = _opp(con, oid, u)
    t = _limpa(dados.texto)
    if not t:
        raise HTTPException(400, "Anotação vazia.")
    _ev(con, oid, "note", "Anotação", t, f"user:{u['id']}")
    atualizar(con, "opportunities", oid, notes=((o["notes"] + "\n") if o["notes"] else "") + t, updated_at=agora())
    con.commit()
    return {"ok": True}


class EtapaIn(BaseModel):
    etapa: str
    motivo: str | None = None


@r.post("/{oid}/stage")
def mover(oid: int, dados: EtapaIn, request: Request, tarefas: BackgroundTasks, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    o = _opp(con, oid, u)
    if dados.etapa not in ETAPAS:
        raise HTTPException(400, f"Etapa inválida. Use: {', '.join(ETAPAS)}")
    if dados.etapa == "GANHO" and not o["client_id"]:
        raise HTTPException(409, "Ganho é o resultado do Fechar venda: use a tela de fechamento para criar o cliente e disparar o resto.")
    campos = {"stage": dados.etapa, "updated_at": agora()}
    if dados.etapa == "PERDIDO":
        if not _limpa(dados.motivo):
            raise HTTPException(400, "Perdido exige motivo.")
        campos.update(lost_reason=_limpa(dados.motivo), next_at=None, next_what=None)
    _ev(con, oid, "stage", f"{ETAPA_PT[o['stage']]} → {ETAPA_PT[dados.etapa]}", _limpa(dados.motivo), f"user:{u['id']}")
    atualizar(con, "opportunities", oid, **campos)
    auditar(con, "sales.stage", f"user:{u['id']}", user_id=u["id"], entity_type="opportunity", entity_id=oid,
            detail={"de": o["stage"], "para": dados.etapa, "motivo": _limpa(dados.motivo)}, ip=auth._ip(request))
    con.commit()
    _google(tarefas, oid)
    return {"ok": True}


TOQUE_DUPLO_S = 60     # o segundo toque no mesmo lead dentro deste tempo não cria outra


@r.post("/from-lead/{lead_id}", status_code=201)
def do_chat(lead_id: int, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """"Passar para vendas": o lead do chat do Kommo vira oportunidade no painel de vendas.

    Dono, 06/10: "eu continuo ali no chat, mas quando eu clico ele registra no painel de vendas
    aquele lead como uma oportunidade. Caso não tenha, ele cria. Se já tiver aquele mesmo lead,
    ele só aponta uma nova oportunidade." Cada toque é uma oportunidade (o cliente que volta é
    negócio novo), ligada ao mesmo lead; só o toque duplo sem querer (o mesmo lead agora há
    pouco) devolve a que acabou de nascer."""
    from datetime import datetime, timedelta, timezone
    l = um(con, "SELECT * FROM crm_leads WHERE id=?", (lead_id,))
    if not l:
        raise HTTPException(404, "Lead não encontrado.")
    anteriores = todos(con, "SELECT id, stage, created_at FROM opportunities WHERE crm_lead_id=? ORDER BY id DESC", (lead_id,))
    corte = (datetime.now(timezone.utc) - timedelta(seconds=TOQUE_DUPLO_S)).strftime("%Y-%m-%dT%H:%M:%S")
    if anteriores and anteriores[0]["created_at"] >= corte:
        return {"id": anteriores[0]["id"], "reaproveitada": True, "nova": False, "do_lead": len(anteriores)}
    oid = inserir(con, "opportunities", name=l["contact_name"] or l["name"] or f"Lead {l['external_id']}",
                  email=(l["contact_email"] or None), phone=l["contact_phone"], source=l["source"] or "Kommo",
                  crm_lead_id=lead_id, closer_user_id=u["id"], updated_at=agora())
    if anteriores:
        _ev(con, oid, "stage", f"Nova oportunidade do mesmo lead do Kommo (já tinha {len(anteriores)})",
            {"lead": l["external_id"], "canal": l["source"], "anteriores": [a["id"] for a in anteriores]}, f"user:{u['id']}", 1)
    else:
        _ev(con, oid, "stage", "Veio do chat do Kommo", {"lead": l["external_id"], "canal": l["source"]}, f"user:{u['id']}", 1)
    auditar(con, "sales.from_lead", f"user:{u['id']}", user_id=u["id"], entity_type="opportunity", entity_id=oid,
            detail={"lead": lead_id, "anteriores": [a["id"] for a in anteriores]})
    con.commit()
    return {"id": oid, "reaproveitada": False, "nova": True, "do_lead": len(anteriores) + 1}


# --------------------------------------------------------------- fechamento
class ExtraIn(BaseModel):
    titulo: str
    onde: str = "painel"          # painel | asana
    quando: str | None = None     # AAAA-MM-DD
    notas: str | None = None


class FecharIn(BaseModel):
    service: str | None = None
    service_date: str | None = None
    service_time: str | None = None
    amount: float | None = None
    pilot_name: str | None = None
    pilot_age: int | None = None
    email: str | None = None
    phone: str | None = None
    nota_cliente: str | None = None
    preco_tabela: float | None = None     # não decide nada (#204): o preço da tabela vem do catálogo
    item_id: str | None = None            # #204: o item do catálogo do QuickBooks escolhido na tela
    irmao: bool = False                   # #204: o card que já existe é do irmão: criar o card deste piloto
    passos: dict[str, bool] = {}
    extras: list[ExtraIn] = []
    confirmar: bool = False               # #310 (R4): o gerente conferiu no QuickBooks que a tentativa anterior não mandou


def gerente(u):
    """Gerente, administrador ou a conta de acesso livre: quem confere o valor da invoice."""
    return bool(u and (u.get("free") or auth.pode(u.get("role"), "MANAGER")))


def item_da_tabela(con, servico=None, item_id=None):
    """O preço da tabela vem do CATÁLOGO, nunca do valor da venda (#204, dono, 14/10: *"precisa
    confirmar o valor da invoice"*). Catálogo = os itens do QuickBooks (`qbo_items`, que a Rate
    Card atualiza toda semana) e os serviços do site (`booking_services`, o que a venda
    automática cobra, com o depósito). `item_id` é o item escolhido na tela; sem ele, o nome do
    serviço tem que ser o do item (ou o do serviço do site). Devolve
    {item_id, nome, preco, deposito, fonte} ou None."""
    nome = (servico or "").strip().lower()
    q = s = None
    if item_id:
        q = um(con, "SELECT id, name, price FROM qbo_items WHERE id=? AND active=1", (str(item_id),))
        if not q:
            return None
    elif nome:
        q = um(con, """SELECT id, name, price FROM qbo_items WHERE active=1
                        AND (LOWER(name)=? OR LOWER(COALESCE(full_name,''))=?) ORDER BY id LIMIT 1""", (nome, nome))
        if not q:
            s = um(con, "SELECT * FROM booking_services WHERE active=1 AND LOWER(name)=? ORDER BY id LIMIT 1", (nome,))
            if s and s["qbo_item_id"]:
                q = um(con, "SELECT id, name, price FROM qbo_items WHERE id=? AND active=1", (s["qbo_item_id"],))
    if not q and not s:
        return None
    if q and not s:                         # o depósito é o do serviço do site com este item (venda automática)
        s = um(con, """SELECT * FROM booking_services WHERE active=1 AND qbo_item_id=?
                         AND COALESCE(kind,'session')='session' ORDER BY (COALESCE(deposit,0)>0) DESC, id LIMIT 1""", (q["id"],))
    # a tabela é o item do QuickBooks (a Rate Card); serviço do site sem item, o preço dele
    if q and q["price"] is not None:
        preco, fonte = q["price"], "quickbooks"
    else:
        preco, fonte = (s["price"] if s else None), "site"
    return {"item_id": q["id"] if q else None, "nome": q["name"] if q else s["name"],
            "preco": float(preco) if preco is not None else None,
            "deposito": float(s["deposit"] or 0) if s else 0.0, "fonte": fonte}


def catalogo(con, busca=None, limite=300, offset=0):
    """Os itens que a tela de fechar oferece: serviço do QuickBooks (o depósito fica fora: ele entra
    sozinho). Paginado: (itens, total)."""
    args, filtro = [], ""
    if busca:
        filtro = " AND LOWER(COALESCE(full_name, name)) LIKE ?"
        args.append(f"%{busca.strip().lower()}%")
    onde = f"""FROM qbo_items WHERE active=1 AND COALESCE(type,'Service')='Service'
               AND LOWER(name) NOT LIKE '%security deposit%'{filtro}"""
    total = um(con, f"SELECT COUNT(*) AS n {onde}", tuple(args))["n"]
    itens = todos(con, f"SELECT id, name, price {onde} ORDER BY name LIMIT ? OFFSET ?",
                  (*args, max(1, min(int(limite), 500)), max(0, int(offset))))
    for i in itens:
        ref = item_da_tabela(con, None, i["id"])
        i["deposito"] = ref["deposito"] if ref else 0.0
    return itens, total


def _confere_preco(valor, preco_tabela):
    """Invoice fora da tabela de preços é do gerente/dono (política 17/09, reafirmada em 14/10).
    Sem preço de tabela no catálogo não há como saber se está na tabela: também espera quem
    confere o valor (#204)."""
    if valor is None:
        return False, "sem valor"
    if preco_tabela is None:
        return None, "sem preço de tabela no catálogo para este serviço"
    if abs(float(valor) - float(preco_tabela)) < 0.01:
        return True, "valor da tabela"
    return False, f"valor ${float(valor):g} difere da tabela (${float(preco_tabela):g})"


def situacao_do_preco(con, o, item_id=None):
    """(ref, preco_tabela, na_tabela, por_que) da oportunidade agora."""
    ref = item_da_tabela(con, o["service"], item_id or o.get("qbo_item_id"))
    preco = ref["preco"] if ref else None
    na_tabela, por_que = _confere_preco(o["amount"], preco)
    return ref, preco, na_tabela, por_que


def _valor_liberado(o):
    """O valor da venda é o que foi aprovado (no fechamento por gerente ou no Liberar invoice)?"""
    f = o.get("closing") or {}
    v = f.get("valor_aprovado")
    return v is not None and o["amount"] is not None and abs(float(v) - float(o["amount"])) < 0.01


def _aprovado_pelo_gerente(f):
    """O valor desta venda foi aprovado por quem confere (o gerente ou o dono fechou fora da tabela, ou
    liberou), e não só por estar na tabela do item de então."""
    return bool(f) and bool(f.get("liberada") or (f.get("aprovado") and f.get("na_tabela") is not True))


def _passo_qbo(f):
    """A linha "Cliente e invoice no QuickBooks" do fechamento (ou None)."""
    return next((p for p in (f or {}).get("passos") or [] if p.get("passo") == "qbo"), None)


def _espera_aprovacao(f):
    """O fechamento deixou a invoice esperando quem confere o valor? `invoice_pendente` (desde 14/10)
    ou só o `pendente` no passo do QuickBooks (o formato de antes, #310)."""
    q = _passo_qbo(f)
    return bool(f) and bool(f.get("invoice_pendente") or (q and q.get("pendente") and q.get("ok") is not True))


def _fechada(f):
    """A venda já fechou? O fechamento de verdade tem a data (`em`) ou os passos; o pedido pago no site
    também conta. Só a marca de quem está fechando agora (`cobrando`) não é fechamento (#310)."""
    return bool(f) and bool(f.get("em") or f.get("passos") or f.get("por") == "stripe")


def pago_no_site(f):
    """A venda nasceu do pedido pago no site, pelo Stripe (`stripe_loja`, `carrinho`): o cliente já pagou,
    e nada sai pelo QuickBooks para ela (#310, R1)."""
    return bool(f) and f.get("por") == "stripe"


def estado_da_invoice(o, na_tabela):
    """A invoice do serviço desta venda (#310, dono, 14/10: invoice fora da tabela só sai com o gerente
    ou o dono; nunca cobrar duas vezes):

    - "enviada": o passo do QuickBooks saiu (no fechamento, no botão do passo, no Liberar ou pela IA),
      ou o pedido foi pago no site (Stripe) — o cliente já pagou;
    - "esperando": fora da tabela (ou sem preço de tabela) e ninguém conferiu o valor — inclusive a
      invoice desligada pelo closer e o fechamento de antes de 14/10. Só o gerente ou o dono libera;
    - "livre": pode sair pelo botão do passo.

    A invoice só do depósito fica em `deposito_cobrado`, não aqui."""
    f = o.get("closing") or {}
    if pago_no_site(f):
        return "enviada"
    q = _passo_qbo(f)
    if q and q.get("ok") is True:
        return "enviada"
    if _espera_aprovacao(f) or (na_tabela is not True and not _valor_liberado(o)):
        return "esperando"
    return "livre"


def _numero(f):
    q = _passo_qbo(f) or {}
    n = q.get("numero") or q.get("invoice")
    return f" #{n}" if n else ""


def ja_saiu(f):
    """A frase do 409 quando a cobrança desta venda já saiu: não cobramos duas vezes."""
    if pago_no_site(f):
        pedido = f" #{f['pedido']}" if f.get("pedido") else ""
        return f"O pedido{pedido} desta venda foi pago no site (Stripe): não cobramos duas vezes."
    if (_passo_qbo(f) or {}).get("enviado") is False:
        return (f"A invoice{_numero(f)} desta venda já foi criada no QuickBooks e o envio falhou: reenvie a mesma "
                "(Reenviar). Não criamos outra.")
    return f"A invoice{_numero(f)} desta venda já saiu: não cobramos duas vezes."


def _detalhe_qbo(res, feito):
    """O texto da linha do QuickBooks: o que saiu, ou a invoice criada cujo envio falhou (#310, A1)."""
    if isinstance(res, dict) and res.get("enviado") is False:
        n = res.get("numero") or res.get("invoice")
        return f"invoice nº {n} criada; o envio falhou ({(res.get('erro_envio') or res.get('aviso') or '')[:120]}): reenviar"
    return feito


def nao_enviadas(f):
    """As invoices desta venda criadas no QuickBooks e não enviadas (o envio falhou): saem de novo só pelo
    Reenviar, que manda a MESMA (#310, A1). [{invoice, numero, o_que}]"""
    out = []
    q = _passo_qbo(f)
    if q and q.get("ok") is True and q.get("enviado") is False and q.get("invoice"):
        out.append({"invoice": str(q["invoice"]), "numero": q.get("numero") or q["invoice"], "o_que": "invoice"})
    d = (f or {}).get("deposito_nao_enviado")
    if isinstance(d, dict) and d.get("invoice"):
        out.append({"invoice": str(d["invoice"]), "numero": d.get("numero") or d["invoice"], "o_que": "deposito"})
    return out


# --------------------------------------------------------------- a trava da cobrança (#310)
# Toda saída que cobra (fechar, Liberar, o passo, a IA, o depósito) marca `closing.cobrando` com
# compare-and-set antes de falar com o QuickBooks; quem chega com a marca viva para. O QuickBooks
# responde em segundos (o tempo máximo de uma chamada é 90 s): a marca mais velha que isto é de um
# pedido que caiu no meio. Ela não some sozinha (R4): a invoice pode ter saído. O mesmo vale, na hora,
# para a chamada que não respondeu (A1, a marca `incerta`). Só o gerente ou o dono resolve, depois de
# conferir no QuickBooks: "Não saiu: mandar" (`confirmar`) ou "Saiu: registrar o número".
COBRANDO_MAX_S = 600
O_QUE_PT = {"liberar": "liberando a invoice", "reenvio": "mandando a invoice", "ia": "mandando a invoice pela IA",
            "deposito": "cobrando o depósito", "fechar": "fechando a venda"}
# o desfecho de cada tentativa na auditoria: todos levam o `tentativa` do "enviando"
DESFECHOS = ("sales.invoice.release", "sales.invoice.resend", "sales.invoice", "sales.deposit", "sales.close",
             "sales.invoice.failed", "sales.invoice.confirmed", "sales.invoice.registered")
SEM_DESFECHO = "tentativa_sem_desfecho"
# o que uma tentativa cobrava: a requestid da pendente só se reaproveita para a MESMA cobrança
CONTEUDO = ("valor", "deposito", "item", "so_deposito")


class Travado(Exception):
    """A cobrança desta venda não pode começar agora. `motivo` diz à tela que decisão pedir."""

    def __init__(self, mensagem, motivo=None, status=409):
        super().__init__(mensagem)
        self.motivo, self.status = motivo, status

    def http(self):
        return HTTPException(self.status, {"motivo": self.motivo, "mensagem": str(self)} if self.motivo else str(self))


def nada_saiu(e):
    """O erro prova que nada foi criado no QuickBooks? `NaoConectado`, o erro de antes da chamada e a
    recusa do QuickBooks (HTTP 4xx, menos 408 e 429) provam. Tempo esgotado, conexão caída, 5xx, 408 e
    429 não: a invoice pode ter sido criada (#310, A1)."""
    return isinstance(e, NaoConectado) or bool(getattr(e, "nada_saiu", False))


def _marca(f):
    m = (f or {}).get("cobrando")
    return m if isinstance(m, dict) else None


def _idade_s(iso):
    from datetime import datetime, timezone
    try:
        desde = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if desde.tzinfo is None:
        desde = desde.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - desde).total_seconds()


def cobrando_agora(f):
    """Quem está cobrando esta venda neste instante ({por, em, acao, tentativa}), ou None. A marca
    `incerta` (a chamada acabou sem resposta) não está cobrando: está sem desfecho."""
    m = _marca(f)
    idade = _idade_s(m.get("em")) if m and not m.get("incerta") else None
    return m if m and idade is not None and idade < COBRANDO_MAX_S else None


def ocupado(m):
    return (f"{m.get('por') or 'Alguém'} está {O_QUE_PT.get(m.get('acao'), 'cobrando esta venda')} agora "
            f"({quando_pt(m.get('em'))}): espere um instante e recarregue.")


def _envio_da_tentativa(con, oid, tok):
    a = um(con, """SELECT detail, at FROM audit_logs WHERE event='sales.invoice.sending' AND entity_type='opportunity'
                    AND entity_id=? AND detail LIKE ? ORDER BY id DESC LIMIT 1""", (str(oid), f'%"tentativa": "{tok}"%'))
    return (json.loads(a["detail"] or "{}"), a["at"]) if a else ({}, None)


def _sem_desfecho(con, oid, f):
    """A tentativa de cobrar que não terminou (R4, A1): a marca vencida ou `incerta` no fechamento, ou o
    último "enviando" da auditoria sem desfecho. Devolve {por, em, acao, tentativa, requestid, erro,
    valor, deposito, item, so_deposito} ou None."""
    m = _marca(f)
    if m and not cobrando_agora(f):
        d, _at = _envio_da_tentativa(con, oid, m.get("tentativa"))
        return {**{k: d.get(k) for k in ("requestid", *CONTEUDO)}, **m,
                "erro": (m.get("incerta") or {}).get("erro") if isinstance(m.get("incerta"), dict) else None}
    a = um(con, """SELECT detail, at FROM audit_logs WHERE event='sales.invoice.sending' AND entity_type='opportunity'
                    AND entity_id=? ORDER BY id DESC LIMIT 1""", (str(oid),))
    d = json.loads((a or {}).get("detail") or "{}")
    tok = d.get("tentativa")
    if not tok or (m and m.get("tentativa") == tok):
        return None
    marcas = ",".join("?" * len(DESFECHOS))
    if um(con, f"""SELECT 1 AS x FROM audit_logs WHERE entity_type='opportunity' AND entity_id=? AND event IN ({marcas})
                    AND detail LIKE ? LIMIT 1""", (str(oid), *DESFECHOS, f'%"tentativa": "{tok}"%')):
        return None
    return {**{k: d.get(k) for k in ("requestid", *CONTEUDO)},
            "por": d.get("por"), "em": d.get("em") or a["at"], "acao": d.get("acao"), "tentativa": tok}


def texto_sem_desfecho(m):
    quando = quando_pt(m.get("em"))
    dia, _, hora = quando.partition(" ")
    erro = f" (o QuickBooks não respondeu: {m['erro'][:120]})" if m.get("erro") else ""
    return (f"A tentativa de {m.get('por') or 'alguém'} às {hora or dia}{(' de ' + dia) if hora else ''} "
            f"({O_QUE_PT.get(m.get('acao'), 'cobrando esta venda')}) não terminou: confira no QuickBooks se a invoice "
            f"saiu{erro}. O gerente ou o dono resolve: se não saiu, manda de novo; se saiu, registra o número.")


def travar(con, oid, cru, quem, acao, confirmar=False, pode_confirmar=False, ator="system", user_id=None):
    """Põe a marca `cobrando` no fechamento com compare-and-set: só troca o `closing` que este pedido
    leu (`cru`). Quem chega com a marca viva, ou com o fechamento mudado no meio, para (o clique duplo,
    duas abas, a IA no meio do botão). A tentativa anterior sem desfecho (R4) só passa com
    `confirmar`, e só o gerente ou o dono confirma: a confirmação encerra a tentativa antiga na
    auditoria (`sales.invoice.confirmed`), junto com a marca nova (A2). Devolve a marca."""
    import uuid
    f = json.loads(cru or "null") or {}
    if (m := cobrando_agora(f)):
        raise Travado(ocupado(m))
    pend = _sem_desfecho(con, oid, f)
    if pend and not confirmar:
        raise Travado(texto_sem_desfecho(pend), SEM_DESFECHO)
    if pend and not pode_confirmar:
        raise Travado("Só o gerente ou o dono confirma que a tentativa anterior não mandou a invoice.", SEM_DESFECHO, 403)
    marca = {"por": quem, "em": agora(), "acao": acao, "tentativa": uuid.uuid4().hex[:16]}
    if pend:                              # a requestid da pendente vai junto (A1: o QuickBooks não cria a segunda)
        marca.update(confirmou=pend["tentativa"], pendente={k: pend.get(k) for k in ("requestid", *CONTEUDO)})
    novo = json.dumps(dict(f, cobrando=marca), ensure_ascii=False)
    with transacao(con, imediata=True):
        if con.execute("UPDATE opportunities SET closing=? WHERE id=? AND closing IS ?", (novo, oid, cru)).rowcount != 1:
            raise Travado("Esta venda mudou agora mesmo (outro clique, outra aba ou a IA?): recarregue e confira.")
        if pend:
            auditar(con, "sales.invoice.confirmed", ator, user_id=user_id, entity_type="opportunity", entity_id=oid,
                    detail={"tentativa": pend["tentativa"], "acao": pend.get("acao"), "por": quem,
                            "nova": marca["tentativa"], "nova_acao": acao})
    return marca


def ler_closing(con, oid):
    """O `closing` cru (o texto do banco, que o compare-and-set compara) e o lido."""
    cru = (um(con, "SELECT closing FROM opportunities WHERE id=?", (oid,)) or {}).get("closing")
    return cru, json.loads(cru or "null")


def gravar_fechamento(con, oid, muda, **campos):
    """R3: a escrita final do fechamento relê o `closing` (dentro de `transacao(con, imediata=True)`),
    aplica só a mudança deste pedido e grava. Regravar o que se leu no começo apagava o que outro
    pedido gravou no meio (o "liberada" de um Liberar, o depósito cobrado)."""
    f = ler_closing(con, oid)[1] or {}
    muda(f)
    atualizar(con, "opportunities", oid, closing=json.dumps(f, ensure_ascii=False) if f else None,
              updated_at=agora(), **campos)
    return f


def _tira_marca(f, marca):
    """Tira a marca deste pedido (e só a dele: a de quem confirmou por cima fica)."""
    if (_marca(f) or {}).get("tentativa") == marca["tentativa"]:
        f.pop("cobrando", None)


def _deixa_incerta(f, marca, erro):
    """A chamada acabou sem resposta: a marca deste pedido fica, como `incerta` (A1)."""
    m = _marca(f)
    if m and m.get("tentativa") == marca["tentativa"]:
        m["incerta"] = {"em": agora(), "erro": str(erro)[:200]}


def destravar(con, oid, marca, erro=None, actor="system", user_id=None):
    """Nada saiu: tira a marca e, se o pedido chegou a falar com o QuickBooks, grava o desfecho da
    tentativa (`sales.invoice.failed`). O botão volta a funcionar."""
    with transacao(con, imediata=True):
        gravar_fechamento(con, oid, lambda f: _tira_marca(f, marca))
        if erro is not None:
            auditar(con, "sales.invoice.failed", actor, user_id=user_id, entity_type="opportunity", entity_id=oid,
                    detail={"tentativa": marca["tentativa"], "acao": marca["acao"], "erro": str(erro)[:300]})


def sem_resposta(con, oid, marca, erro):
    """A chamada ao QuickBooks acabou sem prova de que nada saiu (A1): a marca fica, `incerta`, e o
    próximo pedido cai na tentativa sem desfecho (só o gerente resolve)."""
    with transacao(con, imediata=True):
        gravar_fechamento(con, oid, lambda f: _deixa_incerta(f, marca, erro))


def soltar(con, oid, marca, falou):
    """O fim de uma chamada que deu errado: nada saiu, a marca sai; sem resposta, ela fica `incerta`."""
    if not falou["qbo"]:
        destravar(con, oid, marca)
    elif falou.get("erro"):
        sem_resposta(con, oid, marca, falou["erro"])


def enviando(con, oid, marca, actor, user_id=None, **detalhe):
    """R4: antes de chamar o QuickBooks, o "enviando" vai para a auditoria em autocommit. Se a gravação
    do desfecho cair depois de a invoice sair, sobra o rastro: o próximo pedido para e pergunta."""
    auditar(con, "sales.invoice.sending", actor, user_id=user_id, entity_type="opportunity", entity_id=oid,
            detail={"tentativa": marca["tentativa"], "acao": marca["acao"], "por": marca["por"], "em": marca["em"],
                    **detalhe})


def _mesma_cobranca(a, b):
    def igual(x, y):
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and not isinstance(x, bool):
            return abs(float(x) - float(y)) < 0.01
        return (x or None) == (y or None)
    return all(igual(a.get(k), b.get(k)) for k in CONTEUDO)


def requestid_de(marca, detalhe):
    """A `requestid` do POST /invoice (A1): a da tentativa pendente que o gerente confirmou, quando é a
    MESMA cobrança (se ela tinha criado, o QuickBooks devolve a mesma invoice em vez de criar a
    segunda); senão, uma nova, derivada desta tentativa."""
    pend = marca.get("pendente") or {}
    if pend.get("requestid") and _mesma_cobranca(pend, detalhe):
        return pend["requestid"]
    return f"urace-{marca['tentativa']}"


def ja_cobrado(f):
    """O que este fechamento já cobrou (ou está cobrando agora). Fechar de novo cobraria outra vez
    (#310): a lista refaria a invoice, o depósito, o card, a waiver, o Asana e o Kommo."""
    if not f:
        return None
    if pago_no_site(f):
        return "o pedido já foi pago no site (Stripe)"
    if (_passo_qbo(f) or {}).get("ok") is True:
        return f"a invoice{_numero(f)} já saiu"
    if f.get("liberada"):
        return "a invoice já foi liberada"
    if (m := cobrando_agora(f)):
        return f"{m.get('por') or 'alguém'} está {O_QUE_PT.get(m.get('acao'), 'cobrando esta venda')} agora"
    if f.get("deposito_cobrado"):
        return "o depósito já foi cobrado"
    return None


def _passo(saida, nome, ok, detalhe, extra=None):
    saida.append({"passo": nome, "nome": PASSO_PT.get(nome, nome), "ok": ok, "detalhe": detalhe, **(extra or {})})
    return saida[-1]


def _achar_card(con, o):
    """O card em que o fechamento cai: o vinculado no formulário (#158) ou o do mesmo e-mail ou
    telefone. Irmãos (#204) dividem o contato: entre eles, o do piloto desta venda."""
    from command_center.providers import identidade
    if o.get("client_id"):
        return um(con, "SELECT * FROM clients WHERE id=?", (o["client_id"],))
    cs = todos(con, "SELECT * FROM clients WHERE email=? ORDER BY id", (o["email"],)) if o["email"] else []
    if not cs and o["phone"]:
        d = identidade.so_digitos(o["phone"])
        if d:
            cs = [c for c in todos(con, "SELECT * FROM clients WHERE phone IS NOT NULL ORDER BY id")
                  if identidade.so_digitos(c["phone"]) == d]
    return identidade._do_piloto(cs, o["pilot_name"] or o["name"]) if cs else None


def _outro_piloto(card, o):
    """O card que existe é de OUTRO piloto (o irmão)? Só com os dois pilotos escritos e o primeiro
    nome diferente — nome parecido não decide sozinho."""
    from command_center.providers import identidade
    if not card or not card.get("pilot_name") or not o.get("pilot_name"):
        return False
    a, b = identidade.normaliza(card["pilot_name"]), identidade.normaliza(o["pilot_name"])
    return bool(a and b and a[0] != b[0])


def _cliente_do_fechamento(con, o, nota, irmao=False):
    """Card do cliente: o vinculado no formulário (#158), o que existe (mesmo e-mail ou telefone) ou
    um novo. Nunca duplica. #204: com `irmao`, o card que existe é do irmão e o deste piloto nasce
    ao lado (mesmo responsável, e-mail e telefone); sem `irmao`, o serviço de um piloto não cai no
    card de outro — o passo para e diz o que fazer."""
    from command_center.providers import identidade
    achado = _achar_card(con, o)
    if achado and irmao:
        cid, novo = identidade.criar_irmao(con, achado["id"], o["pilot_name"], notas=nota, status="ACTIVE", source="venda")
        return cid, (f"card de irmão criado (irmão de {achado['pilot_name'] or achado['name']})" if novo
                     else f"ligado ao card do irmão que já existia (família de {achado['pilot_name'] or achado['name']})")
    if achado and _outro_piloto(achado, o):
        raise identidade.ErroIrmao(f"o card com este contato é do piloto {achado['pilot_name']}, e esta venda é de "
                                   f"{o['pilot_name']}: marque \"É irmão\" para criar o card dele, ou vincule ao card certo")
    campos = dict(name=o["name"], email=o["email"], phone=o["phone"],
                  pilot_name=o["pilot_name"] if (o["pilot_name"] or "") != (o["name"] or "") else None,
                  status="ACTIVE", source="venda")
    if achado:
        novos = {k: v for k, v in campos.items() if v and not achado.get(k)}
        if nota:
            novos["notes"] = ((achado.get("notes") or "") + "\n" + nota).strip()
        if novos:
            atualizar(con, "clients", achado["id"], updated_at=agora(), **novos)
        return achado["id"], f"ligado ao card que já existia: {achado['name']}"
    cid = inserir(con, "clients", notes=nota, **campos)
    return cid, "card criado"


class NadaSaiu(RuntimeError):
    """O erro de antes da invoice (cliente, item, simulação): nada foi criado no QuickBooks (#310)."""
    nada_saiu = True


def _qbo(con, o, aprovado, ref=None, deposito=0.0, so_deposito=False, requestid=None):
    """Cliente no QuickBooks (se não existe) e invoice criada + enviada: o serviço pelo item do
    catálogo e, quando o serviço pede, o depósito na mesma linha "Security deposit" da venda
    automática (#204). Sem aprovação, a invoice fica pendente: nada vai ao QuickBooks.

    #310 (A1): o erro de antes da invoice leva `nada_saiu`; a invoice criada cujo envio falhou volta
    com `enviado: False` (quem chamou grava, e o Reenviar manda a mesma); `requestid` vai ao QuickBooks."""
    if not aprovado:
        return {"cliente_qbo": None, "invoice": None, "pendente": True}
    nome, email = o["name"], o["email"]
    try:
        busca = chamar("quickbooks", "qbo_clientes_buscar", termo=email or nome, maximo=5) or []
        cliente = (busca[0] if busca else None)
        if not cliente:
            novo = _aplicando("quickbooks", chamar, "quickbooks", "qbo_criar_cliente", nome=nome, email=email, telefone=o["phone"])
            cliente = {"id": (novo or {}).get("id") or (novo or {}).get("cliente_id"), "nome": nome}
        cid = str(cliente.get("id") or cliente.get("cliente_id") or "")
        if not cid:
            raise NadaSaiu("QuickBooks não devolveu o id do cliente")
        from command_center.api import acoes
        from command_center.providers import cobranca_agenda
        linhas = []
        if not so_deposito:
            if not ref or not ref.get("item_id"):
                raise NadaSaiu("o serviço não tem item no catálogo do QuickBooks: escolha o item na tela de fechar")
            linhas.append({"item_id": ref["item_id"], "quantidade": 1, "unitario": float(o["amount"] or 0),
                           "descricao": o["service"] or ref["nome"]})
        if deposito and deposito > 0:
            linhas.append(cobranca_agenda.linha_deposito(con, deposito))
        if not linhas:
            raise NadaSaiu("nada a cobrar")
        memo = acoes.memo_invoice(produto=o["service"], piloto=o["pilot_name"], data_servico=o["service_date"])
    except NaoConectado:
        raise
    except Exception as e:                                       # antes da invoice: nada foi criado
        if not isinstance(e, NadaSaiu):
            e.nada_saiu = True
        raise
    inv = _aplicando("quickbooks", chamar, "quickbooks", "qbo_criar_e_enviar_invoice", cliente_id=cid,
                     linhas=linhas, vence_em=o["service_date"], memo=memo, email=email, nota_privada=memo,
                     requestid=requestid)
    if isinstance(inv, dict) and inv.get("aplicado") is False:
        raise NadaSaiu("o QuickBooks não criou a invoice (simulação)")
    inv = inv or {}
    res = {"cliente_qbo": cid, "invoice": inv.get("id") or inv.get("numero"), "numero": inv.get("numero"), "pendente": False,
           "total": inv.get("total"), "deposito": float(deposito or 0), "enviado": inv.get("enviado") is not False}
    if not res["enviado"]:
        res["erro_envio"] = (inv.get("erro_envio") or inv.get("aviso") or "o envio falhou")[:300]
    return res


def resumo_do_fechamento(por, o, ref, na_tabela, por_que, aprovado, deposito, saida):
    """O que fica gravado em `closing`: o passo a passo e a situação da cobrança (#204)."""
    q = next((p for p in saida if p["passo"] == "qbo"), None)
    saiu = bool(q and q["ok"] is True and q.get("invoice"))
    return {"em": agora(), "por": por, "na_tabela": na_tabela, "aprovado": aprovado, "motivo_preco": por_que,
            "valor": o["amount"], "preco_tabela": ref["preco"] if ref else None,
            "item": {"id": ref["item_id"], "nome": ref["nome"]} if ref and ref.get("item_id") else None,
            "valor_aprovado": o["amount"] if aprovado else None,
            "invoice_pendente": bool(q and q.get("pendente")),
            "deposito": deposito, "deposito_cobrado": (q.get("invoice") if saiu and deposito else None),
            "passos": saida}


def _waiver(con, o):
    menor = (o["pilot_age"] is not None and int(o["pilot_age"]) < 18)
    modelo = os.environ.get("DOCUSIGN_TEMPLATE_PARENTAL", "6dbf2094-39da-4c21-95dd-feda7ac28022") if menor \
        else os.environ.get("DOCUSIGN_TEMPLATE_ADULT", "c51aede4-bba5-40df-9f14-24c340e2bd3e")
    email = (o["email"] or "").lower()
    if "@" not in email:
        raise RuntimeError("sem e-mail do responsável")
    if email.endswith("@urace.us"):
        raise RuntimeError("e-mail do domínio da URACE não é de cliente")
    res = modulo("docusign").enviar_waiver_humano(modelo, o["name"], email, o["service"] or "")
    env = (res or {}).get("envelopeId")
    wid = inserir(con, "waivers", client_id=o["client_id"], signer_name=o["name"], signer_email=email,
                  template=("parental" if menor else "adult"), status="sent", sent_at=agora(),
                  link_reason="enviada no fechamento da venda", link_by="human", synced_at=agora())
    from command_center.api import rastro        # dono, 21/09: fica registrado na tarefa, com a hora
    rastro.waiver_enviada(con, o["client_id"], o["name"], email,
                          modelo=("parental" if menor else "adult"))
    return {"envelope": env, "waiver_id": wid, "modelo": "parental" if menor else "adult"}


def _asana(con, o):
    from adminai.mcp import asana_mcp
    piloto = o["pilot_name"] or o["name"]
    quando = (o["service_date"] or "")[:10]
    hora = f" {o['service_time']}" if o["service_time"] else ""
    titulo = f"{piloto}_{o['service'] or 'Serviço'}{(' - ' + quando) if quando else ''}{hora}"
    notas = f"Fechado pela venda (oportunidade #{o['id']}). Responsável: {o['name']}"
    if o["email"]:
        notas += f" · {o['email']}"
    if o["phone"]:
        notas += f" · {o['phone']}"
    if o["amount"]:
        notas += f" · valor ${o['amount']:g}"
    res = _aplicando("asana", chamar, "asana", "asana_criar_tarefa", projeto_gid=asana_mcp.PROJETO_URACE,
                     nome=titulo, notas=notas, vence_em=quando or None)
    return {"tarefa": (res or {}).get("gid") or (res or {}).get("id"), "titulo": titulo}


def _kommo_ganho(con, o):
    if not o["crm_lead_id"]:
        return {"nota": "esta oportunidade não veio do chat: nada a mover no Kommo"}
    l = um(con, "SELECT * FROM crm_leads WHERE id=?", (o["crm_lead_id"],))
    if not l:
        return {"nota": "lead do chat não está mais no espelho"}
    funis = chamar("kommo", "kommo_funis") or []
    etapa = None
    for f in funis:
        if str(f.get("id")) != str(l["pipeline_id"] or ""):
            continue
        for e in f.get("etapas") or []:
            if "won" in (e.get("nome") or "").lower() or "ganho" in (e.get("nome") or "").lower():
                etapa = e
                break
    if not etapa:
        return {"nota": "não achei a etapa 'Closed won' neste funil do Kommo"}
    _aplicando("kommo", modulo("kommo").mover_etapa_humano, l["external_id"], etapa["id"], l["pipeline_id"])
    atualizar(con, "crm_leads", l["id"], stage_id=str(etapa["id"]), stage_name=etapa.get("nome"), synced_at=agora())
    return {"etapa": etapa.get("nome")}


def _extra(con, o, e: ExtraIn, user_id):
    if e.onde == "asana":
        from adminai.mcp import asana_mcp
        res = _aplicando("asana", chamar, "asana", "asana_criar_tarefa", projeto_gid=asana_mcp.PROJETO_URACE,
                         nome=e.titulo, notas=(e.notas or f"Tarefa do fechamento da venda (oportunidade #{o['id']})"),
                         vence_em=(e.quando or None))
        return {"onde": "asana", "tarefa": (res or {}).get("gid") or (res or {}).get("id")}
    quando = e.quando
    if quando and len(quando) == 10:
        quando += "T12:00:00Z"
    if quando and not o["next_at"]:
        atualizar(con, "opportunities", o["id"], next_at=quando, next_what=e.titulo)
    return {"onde": "painel", "quando": quando}


@r.post("/{oid}/close")
def fechar(oid: int, dados: FecharIn, request: Request, tarefas: BackgroundTasks, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """Fechar venda: uma tela, um botão. Cada passo ligado roda aqui e o resultado fica gravado.
    Falha de um passo não impede os outros; a tela mostra o que faltou, com o botão manual.

    #204 (dono, 14/10): o preço da tabela vem do catálogo (o que a tela manda em `preco_tabela`
    não decide nada); fora da tabela, ou sem preço de tabela, a invoice só sai com o gerente ou o
    dono. O depósito entra na mesma invoice quando o serviço pede, como na venda automática.

    #310: fechar de novo não cobra de novo, e dois fechamentos ao mesmo tempo (duas abas, a IA)
    não mandam duas invoices: este marca "fechando a venda" (`closing.cobrando`) antes dos passos."""
    o = _opp(con, oid, u)
    cru, f0 = ler_closing(con, oid)
    if (m := cobrando_agora(f0)):
        raise HTTPException(409, ocupado(m))
    if (cobrado := ja_cobrado(f0)):                            # #310: fechar de novo cobraria outra vez
        raise HTTPException(409, f"Venda já fechada e {cobrado}: fechar de novo cobraria outra vez. "
                                 "Use os botões de cada passo no acompanhamento.")
    try:
        marca = travar(con, oid, cru, u["name"], "fechar", dados.confirmar, gerente(u), f"user:{u['id']}", u["id"])
    except Travado as e:
        raise e.http()
    falou = {"qbo": False}            # o QuickBooks pode ter mandado a invoice: a marca só sai com o desfecho
    try:
        return _fechar(oid, dados, request, tarefas, u, con, o, marca, falou)
    except BaseException:
        soltar(con, oid, marca, falou)
        raise


def _fechar(oid, dados, request, tarefas, u, con, o, marca, falou):
    campos = {k: v for k, v in dados.model_dump(exclude={"passos", "extras", "nota_cliente", "preco_tabela", "item_id",
                                                         "irmao", "confirmar"}).items()
              if v is not None}
    if campos:
        for k in ("service", "email", "phone", "pilot_name"):
            if k in campos:
                campos[k] = _limpa(str(campos[k]))
        atualizar(con, "opportunities", oid, updated_at=agora(), **campos)
        o = _opp(con, oid, u)
    if not o["service"] or o["amount"] is None:
        raise HTTPException(400, "Para fechar, diga o serviço e o valor.")
    ref, _preco, na_tabela, por_que = situacao_do_preco(con, o, dados.item_id)
    if dados.item_id and not ref:
        raise HTTPException(400, "Este item não está no catálogo do QuickBooks (ou está inativo).")
    if ref and ref["item_id"] and ref["item_id"] != o.get("qbo_item_id"):
        atualizar(con, "opportunities", oid, qbo_item_id=ref["item_id"])
        o["qbo_item_id"] = ref["item_id"]
    aprovado = na_tabela is True or gerente(u)
    deposito = ref["deposito"] if ref else 0.0
    quer = {p: bool(dados.passos.get(p, True)) for p in PASSOS}
    saida = []
    ator = f"user:{u['id']}"

    def passo_qbo():
        if not aprovado:
            return _qbo(con, o, False)
        return com_rastro(con, oid, marca, ator, u["id"], falou, lambda rid: _qbo(con, o, True, ref, deposito, requestid=rid),
                          valor=o["amount"], deposito=deposito, item=ref and ref["item_id"])

    if quer["cliente"]:
        try:
            cid, det = _cliente_do_fechamento(con, o, _limpa(dados.nota_cliente), dados.irmao)
            atualizar(con, "opportunities", oid, client_id=cid)
            o["client_id"] = cid
            _passo(saida, "cliente", True, det, {"client_id": cid})
        except Exception as e:                                   # noqa: BLE001
            _passo(saida, "cliente", False, str(e)[:240])

    for nome, fn in (("qbo", passo_qbo), ("waiver", lambda: _waiver(con, o)),
                     ("asana", lambda: _asana(con, o)), ("kommo", lambda: _kommo_ganho(con, o))):
        if not quer[nome]:
            _passo(saida, nome, None, "desligado pelo closer")
            continue
        try:
            res = fn()
            if nome == "qbo" and res.get("pendente"):
                _passo(saida, nome, None, f"invoice esperando o gerente conferir o valor: {por_que}", res)
            else:
                _passo(saida, nome, True, _detalhe_qbo(res, "feito"), res if isinstance(res, dict) else None)
        except NaoConectado as e:
            _passo(saida, nome, False, f"não conectado: {str(e)[:160]}")
        except Exception as e:                                   # noqa: BLE001
            _passo(saida, nome, False, SEM_RESPOSTA.format(str(e)[:160]) if nome == "qbo" and falou.get("erro")
                   else str(e)[:240])

    for e in dados.extras[:10]:
        try:
            res = _extra(con, o, e, u["id"])
            _passo(saida, f"extra:{e.titulo[:40]}", True, f"tarefa em {res['onde']}", res)  # nome = o que o closer escreveu
        except Exception as ex:                                  # noqa: BLE001
            _passo(saida, f"extra:{e.titulo[:40]}", False, str(ex)[:200])

    fechado = resumo_do_fechamento(u["name"], o, ref, na_tabela, por_que, aprovado, deposito, saida)
    etapa = "GANHO" if o["client_id"] else "FECHAMENTO"
    incerta = falou.get("erro")           # A1: o QuickBooks não respondeu: a marca fica, sem desfecho
    with transacao(con, imediata=True):     # R3: o fechamento entra inteiro, com a linha do tempo e a auditoria
        gravar_fechamento(con, oid, lambda f: _troca_tudo(f, fechado, marca, incerta), stage=etapa,
                          next_at=None if etapa == "GANHO" else o["next_at"])
        for p in saida:
            _ev(con, oid, PASSO_KIND.get(p["passo"], "task"), f"{p['nome']}: {p['detalhe']}",
                p.get("client_id") and {"client_id": p["client_id"]} or None,
                ator, 1 if p["ok"] else (0 if p["ok"] is False else None))
        _ev(con, oid, "stage", f"Venda fechada · {ETAPA_PT[etapa]}", {"valor": o["amount"], "servico": o["service"]}, ator, 1)
        auditar(con, "sales.close", ator, user_id=u["id"], entity_type="opportunity", entity_id=oid,
                detail={"valor": o["amount"], "servico": o["service"], "preco_tabela": fechado["preco_tabela"],
                        "na_tabela": na_tabela, "aprovado": aprovado, "deposito": deposito,
                        "passos": {p["passo"]: p["ok"] for p in saida}, "confirmou": marca.get("confirmou"),
                        # sem resposta do QuickBooks, a tentativa fica sem desfecho (o gerente resolve)
                        **({"tentativa_sem_resposta": marca["tentativa"]} if incerta else {"tentativa": marca["tentativa"]})},
                ip=auth._ip(request))
    _google(tarefas, oid)
    return {"ok": True, "etapa": etapa, "fechamento": fechado, "client_id": o["client_id"]}


SEM_RESPOSTA = ("o QuickBooks não respondeu ({}): a invoice pode ter saído. Confira no QuickBooks antes de tentar "
                "de novo (o gerente resolve: não saiu, manda; saiu, registra o número)")


def com_rastro(con, oid, marca, ator, user_id, falou, chamada, **detalhe):
    """A chamada que cobra, com o rastro do R4: o "enviando" na auditoria antes (com a `requestid` que
    vai ao QuickBooks) e, se ela falha, o desfecho. Só o erro que prova que nada saiu
    (`nada_saiu`) grava `sales.invoice.failed` e desliga `falou["qbo"]`; sem resposta (A1), fica
    `falou["erro"]`, sem desfecho: a marca não pode sair."""
    rid = requestid_de(marca, detalhe)
    enviando(con, oid, marca, ator, user_id, requestid=rid, **detalhe)
    falou["qbo"] = True
    try:
        return chamada(rid)
    except Exception as e:
        if nada_saiu(e):
            falou["qbo"] = False
            auditar(con, "sales.invoice.failed", ator, user_id=user_id, entity_type="opportunity", entity_id=oid,
                    detail={"tentativa": marca["tentativa"], "acao": marca["acao"], "erro": str(e)[:300]})
        else:
            falou["erro"] = f"{type(e).__name__}: {str(e)[:200]}"
            auditar(con, "sales.invoice.uncertain", ator, user_id=user_id, entity_type="opportunity", entity_id=oid,
                    detail={"tentativa_sem_resposta": marca["tentativa"], "acao": marca["acao"], "erro": falou["erro"]})
        raise


def _troca_tudo(f, fechado, marca, incerta=None):
    """O fechamento novo no lugar do que estava, sem a marca deste pedido (a de quem confirmou por cima
    fica). Sem resposta do QuickBooks (A1), a marca deste pedido fica, `incerta`."""
    minha = _marca(f) if (_marca(f) or {}).get("tentativa") == marca["tentativa"] else None
    outra = _marca(f) if not minha else None
    f.clear()
    f.update(fechado)
    if outra:
        f["cobrando"] = outra
    elif incerta:
        f["cobrando"] = dict(minha or marca, incerta={"em": agora(), "erro": str(incerta)[:200]})


def _troca_passo(fechado, passo, item):
    fechado["passos"] = [p for p in fechado.get("passos", []) if p.get("passo") != passo] + [item]


def _http_da_chamada(e, falou=None):
    """O erro de uma chamada que cobra, para a tela: nada saiu, ou não se sabe (A1)."""
    if isinstance(e, HTTPException):
        return e
    if isinstance(e, NaoConectado):
        return HTTPException(503, f"não conectado: {e}")
    if falou and falou.get("erro"):
        texto = SEM_RESPOSTA.format(str(e)[:160])
        return HTTPException(502, texto[0].upper() + texto[1:] + ".")
    return HTTPException(502, str(e)[:300])


@r.post("/{oid}/step/{passo}")
def refazer(oid: int, passo: str, request: Request, irmao: bool = False, item_id: str | None = None,
            confirmar: bool = False, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """Botão manual de um passo (reenviar waiver, mandar a invoice, criar a tarefa…).

    #204: a invoice que espera o gerente NÃO sai por aqui — antes, este botão mandava com
    `aprovado=True` e passava por cima da aprovação. Só sai o valor da tabela ou o já liberado.
    #310: a invoice que já saiu (ou que o cliente pagou no site) também não sai de novo, e o envio
    por aqui fica na auditoria. Nenhum passo roda antes de fechar (R7: criava um fechamento e a venda
    não fechava mais). A invoice marca `cobrando` antes de falar com o QuickBooks (R2: dois cliques,
    a IA ou o Liberar no meio), e a gravação final relê o fechamento (R3). `item_id` é o item do
    catálogo escolhido na tela quando o serviço não tem (R6); `confirmar` é o do R4 (só o gerente)."""
    o = _opp(con, oid, u)
    if passo not in PASSOS:
        raise HTTPException(400, f"Passo inválido. Use: {', '.join(PASSOS)}")
    cru, fechado = ler_closing(con, oid)
    if (m := cobrando_agora(fechado)) and m.get("acao") == "fechar":
        raise HTTPException(409, ocupado(m))
    if not _fechada(fechado):
        raise HTTPException(409, "Feche a venda antes: os passos saem no fechamento (feitos antes, o fechamento faria de novo).")
    o["closing"] = fechado
    ator, marca, deposito = f"user:{u['id']}", None, 0.0
    if passo == "qbo":
        if not o["service"] or o["amount"] is None:
            raise HTTPException(400, "Para a invoice, a ficha precisa do serviço e do valor.")
        ref, _preco, na_tabela, por_que = situacao_do_preco(con, o, item_id)
        if item_id and not ref:
            raise HTTPException(400, "Este item não está no catálogo do QuickBooks (ou está inativo).")
        estado = estado_da_invoice(o, na_tabela)
        if estado == "livre" and item_id and na_tabela is not True and not _aprovado_pelo_gerente(fechado):
            estado = "esperando"          # R6: o item escolhido agora tem outro preço: o valor aprovado no fechamento era o de outra tabela
        if estado == "enviada":
            raise HTTPException(409, f"{ja_saiu(fechado)} Para corrigir a invoice, fale com a gerência.")
        if estado == "esperando":
            motivo = por_que if na_tabela is not True else (fechado.get("motivo_preco") or por_que)
            raise HTTPException(409, f"A invoice espera o gerente conferir o valor ({motivo}). "
                                     "O gerente ou o dono usa Liberar invoice.")
        deposito = 0.0 if fechado.get("deposito_cobrado") else (ref["deposito"] if ref else 0.0)
        try:
            marca = travar(con, oid, cru, u["name"], "reenvio", confirmar, gerente(u), ator, u["id"])
        except Travado as e:
            raise e.http()
        falou = {"qbo": False}
        try:
            if ref and ref["item_id"] and ref["item_id"] != o.get("qbo_item_id"):     # R6: o item escolhido fica na venda
                atualizar(con, "opportunities", oid, qbo_item_id=ref["item_id"])
                o["qbo_item_id"] = ref["item_id"]
            res = com_rastro(con, oid, marca, ator, u["id"], falou,
                             lambda rid: _qbo(con, o, True, ref, deposito, requestid=rid),
                             valor=o["amount"], deposito=deposito, item=ref and ref["item_id"])
        except BaseException as e:
            soltar(con, oid, marca, falou)
            if not isinstance(e, Exception):
                raise
            raise _http_da_chamada(e, falou)
    else:
        try:
            if passo == "cliente":
                cid, det = _cliente_do_fechamento(con, o, None, irmao)
                atualizar(con, "opportunities", oid, client_id=cid)
                res = {"client_id": cid, "detalhe": det}
            elif passo == "waiver":
                res = _waiver(con, o)
            elif passo == "asana":
                res = _asana(con, o)
            else:
                res = _kommo_ganho(con, o)
        except ValueError as e:                                  # trava de dado (irmão, card de outro piloto)
            raise HTTPException(409, str(e)[:300])
        except Exception as e:                                   # noqa: BLE001
            raise _http_da_chamada(e)
    item = {"passo": passo, "nome": PASSO_PT[passo], "ok": True,
            "detalhe": _detalhe_qbo(res, "refeito à mão") if passo == "qbo" else "refeito à mão",
            **(res if isinstance(res, dict) else {})}

    def muda(f):                          # R3: só a mudança deste passo, no fechamento relido
        _troca_passo(f, passo, item)
        if passo == "qbo":
            f.update(invoice_pendente=False, deposito=deposito or f.get("deposito"))
            if deposito:
                f["deposito_cobrado"] = res.get("invoice") or True
            _tira_marca(f, marca)
    with transacao(con, imediata=True):   # o que saiu, a linha do tempo e a auditoria entram juntos
        gravar_fechamento(con, oid, muda)
        _ev(con, oid, PASSO_KIND[passo], f"{PASSO_PT[passo]}: refeito à mão", res, ator, 1)
        if passo == "qbo":                # #310: o reenvio fica na auditoria, como o Liberar
            auditar(con, "sales.invoice.resend", ator, user_id=u["id"], entity_type="opportunity",
                    entity_id=oid, detail={"valor": o["amount"], "na_tabela": na_tabela, "item": ref and ref["item_id"],
                                           "deposito": deposito, "invoice": res.get("invoice"), "enviado": res.get("enviado"),
                                           "tentativa": marca["tentativa"], "confirmou": marca.get("confirmou")},
                    ip=auth._ip(request))
    return {"ok": True, "passo": passo, "resultado": res}


class LiberarIn(BaseModel):
    valor: float                          # o valor que o gerente conferiu na tela (tem que ser o da venda)
    item_id: str | None = None            # o item do catálogo, quando a venda ainda não tem
    confirmar: bool = False               # #310 (R4): conferiu no QuickBooks que a tentativa anterior não mandou


@r.post("/{oid}/invoice/liberar")
def liberar_invoice(oid: int, dados: LiberarIn, request: Request, u=Depends(auth.exige("MANAGER")),
                    con: sqlite3.Connection = Depends(get_db)):
    """Liberar invoice (#204, dono, 14/10: *"precisa confirmar o valor da invoice"*). A invoice fora
    da tabela (ou sem preço de tabela) só sai quando o gerente ou o dono confere o valor contra o
    preço da tabela. Manda o valor conferido: se a venda mudou de valor no meio, não libera.

    #310: libera também a invoice desligada pelo closer fora da tabela e a do fechamento de antes
    de 14/10 (que só tinha `pendente` no passo); a que já saiu (ou foi paga no site) não sai de novo;
    e nada cobra junto (dois cliques, a IA, o passo, o depósito): o primeiro marca `cobrando` antes de
    falar com o QuickBooks. Com o item escolhido na janela, libera também a venda cujo serviço não
    tinha item (R6)."""
    o = _opp(con, oid, u)
    cru, f = ler_closing(con, oid)
    o["closing"] = f
    if not _fechada(f):
        raise HTTPException(409, "Esta venda não tem invoice esperando aprovação.")
    _r, _p, na_tabela_da_venda, _pq = situacao_do_preco(con, o)
    estado = estado_da_invoice(o, na_tabela_da_venda)
    de_onde = ((_passo_qbo(f) or {}).get("detalhe") or "")[:120] or None    # pendente, antigo, desligada ou falhou
    if estado == "enviada":
        raise HTTPException(409, ja_saiu(f))
    if estado != "esperando" and not dados.item_id:
        raise HTTPException(409, "Esta venda não tem invoice esperando aprovação.")
    if o["amount"] is None or abs(float(dados.valor) - float(o["amount"])) >= 0.01:
        raise HTTPException(409, f"O valor da venda agora é ${float(o['amount'] or 0):g}: confira de novo antes de liberar.")
    ref, preco, na_tabela, por_que = situacao_do_preco(con, o, dados.item_id)
    if dados.item_id and not ref:
        raise HTTPException(400, "Este item não está no catálogo do QuickBooks (ou está inativo).")
    ator, falou = f"user:{u['id']}", {"qbo": False}
    try:                                  # o clique duplo, a IA, o passo: só um troca o `closing` que leu
        marca = travar(con, oid, cru, u["name"], "liberar", dados.confirmar, True, ator, u["id"])
    except Travado as e:
        raise e.http()
    deposito = 0.0 if f.get("deposito_cobrado") else (ref["deposito"] if ref else 0.0)
    try:
        if ref and ref["item_id"] and ref["item_id"] != o.get("qbo_item_id"):
            atualizar(con, "opportunities", oid, qbo_item_id=ref["item_id"])
            o["qbo_item_id"] = ref["item_id"]
        res = com_rastro(con, oid, marca, ator, u["id"], falou, lambda rid: _qbo(con, o, True, ref, deposito, requestid=rid),
                         valor=o["amount"], deposito=deposito, item=ref and ref["item_id"])
    except BaseException as e:
        soltar(con, oid, marca, falou)    # nada saiu: a marca sai; sem resposta, fica (o gerente resolve)
        if not isinstance(e, Exception):
            raise
        raise _http_da_chamada(e, falou)
    liberada = {"por": u["name"], "em": agora(), "valor": o["amount"], "preco_tabela": preco, "motivo_preco": por_que}
    passo = {"passo": "qbo", "nome": PASSO_PT["qbo"], "ok": True,
             "detalhe": _detalhe_qbo(res, f"liberada por {u['name']} (valor ${float(o['amount']):g}; {por_que})"), **res}

    def muda(g):                          # R3: só o que o Liberar muda, no fechamento relido
        g.update(aprovado=True, valor_aprovado=o["amount"], invoice_pendente=False, liberada=liberada,
                 preco_tabela=preco, deposito=deposito or g.get("deposito"))
        if deposito:
            g["deposito_cobrado"] = res.get("invoice") or True
        _troca_passo(g, "qbo", passo)
        _tira_marca(g, marca)
    tabela = f"${preco:g}" if preco is not None else "sem preço de tabela"
    with transacao(con, imediata=True):   # a invoice que saiu, a linha do tempo e a auditoria entram juntas
        f = gravar_fechamento(con, oid, muda)
        _ev(con, oid, "invoice", f"Invoice liberada por {u['name']}: ${float(o['amount']):g} (tabela: {tabela})", res, ator, 1)
        auditar(con, "sales.invoice.release", ator, user_id=u["id"], entity_type="opportunity", entity_id=oid,
                detail={"valor": o["amount"], "preco_tabela": preco, "na_tabela": na_tabela, "item": ref and ref["item_id"],
                        "deposito": deposito, "invoice": res.get("invoice"), "de": de_onde,
                        "tentativa": marca["tentativa"], "confirmou": marca.get("confirmou")}, ip=auth._ip(request))
    return {"ok": True, "resultado": res, "fechamento": f}


@r.post("/{oid}/deposit")
def cobrar_deposito(oid: int, request: Request, confirmar: bool = False, u=Depends(auth.exige("OPERATOR")),
                    con: sqlite3.Connection = Depends(get_db)):
    """Cobrar só o depósito (#204, dono, 14/10: *"o depósito de segurança é cobrado em venda manual
    ou automática"*). Para quando ele faltou: venda fechada antes, ou com a invoice desligada. Uma
    invoice só com a linha "Security deposit", no valor que o catálogo pede para o serviço — o
    mesmo da venda automática. Não cobra duas vezes: nem o que já saiu, nem junto com o Liberar, o
    passo ou a IA (#310: marca `cobrando` antes do QuickBooks e relê o fechamento no fim)."""
    o = _opp(con, oid, u)
    cru, f = ler_closing(con, oid)
    if not _fechada(f):
        raise HTTPException(409, "Feche a venda antes: o depósito vai junto com a invoice do fechamento.")
    if pago_no_site(f):
        raise HTTPException(409, ja_saiu(f))
    if f.get("deposito_cobrado"):
        raise HTTPException(409, "O depósito desta venda já foi cobrado.")
    if _espera_aprovacao(f):                                 # #310: também o fechamento de antes de 14/10
        raise HTTPException(409, "A invoice desta venda espera o gerente conferir o valor; o depósito vai junto quando ela for liberada.")
    ref = item_da_tabela(con, o["service"], o.get("qbo_item_id"))
    deposito = ref["deposito"] if ref else 0.0
    if not deposito:
        raise HTTPException(400, "O serviço desta venda não pede depósito no catálogo (Site › Serviços e preços).")
    ator, falou = f"user:{u['id']}", {"qbo": False}
    try:
        marca = travar(con, oid, cru, u["name"], "deposito", confirmar, gerente(u), ator, u["id"])
    except Travado as e:
        raise e.http()
    try:
        res = com_rastro(con, oid, marca, ator, u["id"], falou,
                         lambda rid: _qbo(con, o, True, ref, deposito, so_deposito=True, requestid=rid),
                         deposito=deposito, so_deposito=True)
    except BaseException as e:
        soltar(con, oid, marca, falou)
        if not isinstance(e, Exception):
            raise
        raise _http_da_chamada(e, falou)

    def muda(g):
        g.update(deposito=deposito, deposito_cobrado=res.get("invoice") or True)
        if res.get("enviado") is False:  # A1: criada, o envio falhou: o Reenviar manda a mesma
            g["deposito_nao_enviado"] = {"invoice": res.get("invoice"), "numero": res.get("numero"),
                                         "erro": res.get("erro_envio")}
        _tira_marca(g, marca)
    with transacao(con, imediata=True):
        gravar_fechamento(con, oid, muda)
        _ev(con, oid, "invoice", f"Depósito cobrado: ${deposito:g}" + (
            "" if res.get("enviado") is not False else f" (invoice nº {res.get('numero') or res.get('invoice')} criada; o envio falhou: reenviar)"),
            res, ator, 1)
        auditar(con, "sales.deposit", ator, user_id=u["id"], entity_type="opportunity", entity_id=oid,
                detail={"deposito": deposito, "invoice": res.get("invoice"), "tentativa": marca["tentativa"],
                        "confirmou": marca.get("confirmou")}, ip=auth._ip(request))
    return {"ok": True, "deposito": deposito, "resultado": res}


class ReenviarIn(BaseModel):
    invoice: str | None = None            # qual das não enviadas (o id no QuickBooks); sem ele, a primeira


@r.post("/{oid}/invoice/reenviar")
def reenviar_invoice(oid: int, request: Request, dados: ReenviarIn | None = None, u=Depends(auth.exige("OPERATOR")),
                     con: sqlite3.Connection = Depends(get_db)):
    """Reenviar a invoice criada cujo envio falhou (#310, A1): manda a MESMA invoice pelo QuickBooks, como o
    lembrete (`qbo_enviar_invoice`). Nunca cria outra: só aceita a invoice que esta venda gravou como
    criada e não enviada."""
    o = _opp(con, oid, u)
    _cru, f = ler_closing(con, oid)
    alvos = [a for a in nao_enviadas(f) if not (dados and dados.invoice) or a["invoice"] == str(dados.invoice)]
    if not alvos:
        raise HTTPException(409, "Esta venda não tem invoice criada e não enviada: nada a reenviar.")
    a = alvos[0]
    try:
        res = _aplicando("quickbooks", chamar, "quickbooks", "qbo_enviar_invoice", id=a["invoice"], email=o["email"] or None)
    except NaoConectado as e:
        raise HTTPException(503, f"não conectado: {e}")
    except Exception as e:                                       # noqa: BLE001
        raise HTTPException(502, f"O reenvio falhou ({str(e)[:200]}): a invoice nº {a['numero']} continua criada e não "
                                 "enviada. Tente de novo (é a mesma invoice).")
    if isinstance(res, dict) and res.get("aplicado") is False:
        raise HTTPException(502, "O QuickBooks não reenviou (simulação).")
    para = (res or {}).get("enviado_para") or o["email"]

    def muda(g):
        if a["o_que"] == "deposito":
            g.pop("deposito_nao_enviado", None)
            return
        q = _passo_qbo(g)
        if q and str(q.get("invoice")) == a["invoice"]:
            q.update(enviado=True, enviado_para=para, detalhe=f"invoice nº {a['numero']} reenviada por {u['name']} (a mesma)")
            q.pop("erro_envio", None)
    with transacao(con, imediata=True):
        f = gravar_fechamento(con, oid, muda)
        _ev(con, oid, "invoice", f"Invoice nº {a['numero']} reenviada por {u['name']} (a mesma, para {para})",
            {"invoice": a["invoice"], "numero": a["numero"], "para": para}, f"user:{u['id']}", 1)
        auditar(con, "sales.invoice.send", f"user:{u['id']}", user_id=u["id"], entity_type="opportunity", entity_id=oid,
                detail={"invoice": a["invoice"], "numero": a["numero"], "o_que": a["o_que"], "para": para},
                ip=auth._ip(request))
    return {"ok": True, "invoice": a["invoice"], "numero": a["numero"], "enviado_para": para, "fechamento": f}


class RegistrarIn(BaseModel):
    numero: str                           # o Invoice no. que o gerente conferiu no QuickBooks
    aceitar_diferenca: bool = False       # o total da invoice não bate com a tentativa: registrar mesmo assim


AVISO_SEM_GRAVAR = "o fechamento caiu antes de gravar: confira se este passo saiu antes de tentar de novo"


def _esperado(pend, o):
    """O total que a tentativa pendente mandava (o serviço e o depósito, ou só o depósito)."""
    dep = float(pend.get("deposito") or 0)
    if pend.get("so_deposito") or pend.get("acao") == "deposito":
        return dep or None
    valor = pend.get("valor") if pend.get("valor") is not None else o["amount"]
    return None if valor is None else round(float(valor) + dep, 2)


@r.post("/{oid}/invoice/registrar")
def registrar_invoice(oid: int, dados: RegistrarIn, request: Request, u=Depends(auth.exige("MANAGER")),
                      con: sqlite3.Connection = Depends(get_db)):
    """A invoice saiu (#310, A2). A tentativa sem desfecho mandou mesmo a invoice (o gerente conferiu no
    QuickBooks): o gerente ou o dono informa o número, o painel confere no QuickBooks (só leitura) que
    ela existe e é do mesmo cliente, e grava o passo do QuickBooks como feito, com o desfecho
    `sales.invoice.registered`. A marca sai e nada é cobrado de novo. Sem o QuickBooks ligado, não
    registra: sem conferir, não."""
    o = _opp(con, oid, u)
    numero = (dados.numero or "").strip().lstrip("#").strip()
    if not numero:
        raise HTTPException(400, "Diga o número da invoice no QuickBooks (Invoice no.).")
    cru, f = ler_closing(con, oid)
    if (m := cobrando_agora(f)):
        raise HTTPException(409, ocupado(m))
    pend = _sem_desfecho(con, oid, f or {})
    if not pend:
        raise HTTPException(409, "Esta venda não tem tentativa sem desfecho: não há o que registrar. A invoice que saiu "
                                 "aparece no passo do QuickBooks.")
    try:                                  # só leitura: a invoice e o cliente desta venda no QuickBooks
        inv = chamar("quickbooks", "invoice_por_numero", numero=numero)
        clientes = (chamar("quickbooks", "qbo_clientes_buscar", termo=o["email"] or o["name"], maximo=5) or []) if inv else []
    except NaoConectado:
        raise HTTPException(503, "Ligue o QuickBooks para conferir (Integrações): sem conferir a invoice, nada é registrado.")
    except Exception as e:                                       # noqa: BLE001
        raise HTTPException(502, f"Não consegui conferir no QuickBooks ({str(e)[:200]}): nada foi registrado.")
    if not inv:
        raise HTTPException(409, f"A invoice nº {numero} não existe no QuickBooks: confira o número.")
    ids = {str(c.get("id") or c.get("cliente_id")) for c in clientes if c.get("id") or c.get("cliente_id")}
    if str(inv.get("cliente_id")) not in ids:
        raise HTTPException(409, f"A invoice nº {numero} é de outro cliente no QuickBooks ({inv.get('cliente') or inv.get('cliente_id')}), "
                                 "não do desta venda: confira o número.")
    total, esperado = inv.get("total"), _esperado(pend, o)
    diferente = esperado is not None and total is not None and abs(float(total) - esperado) >= 0.01
    if diferente and not dados.aceitar_diferenca:
        raise HTTPException(409, {"motivo": "valor_diferente",
                                  "mensagem": f"A invoice nº {numero} é de ${float(total):g}, e a tentativa cobrava ${esperado:g}: "
                                              "confira no QuickBooks. Registrar mesmo assim?"})
    so_dep = bool(pend.get("so_deposito") or pend.get("acao") == "deposito")
    fechada_antes = _fechada(f)
    etapa = None if fechada_antes else ("GANHO" if o["client_id"] else "FECHAMENTO")

    def muda(g):
        if not _fechada(g):               # o fechamento caiu antes de gravar: o que ficou sem rastro, a conferir
            saida = []
            _passo(saida, "cliente", True if o["client_id"] else False,
                   "card ligado" if o["client_id"] else AVISO_SEM_GRAVAR, {"client_id": o["client_id"]} if o["client_id"] else None)
            for p in ("waiver", "asana", "kommo"):
                _passo(saida, p, False, AVISO_SEM_GRAVAR)
            g.update(em=agora(), por=u["name"], valor=o["amount"], passos=saida, registrada=True)
        if so_dep:
            g.update(deposito=pend.get("deposito") or g.get("deposito"), deposito_cobrado=inv.get("id") or numero)
        else:
            espera = _espera_aprovacao(g) or not _valor_liberado(dict(o, closing=g))
            _troca_passo(g, "qbo", {"passo": "qbo", "nome": PASSO_PT["qbo"], "ok": True, "registrada": True,
                                    "detalhe": f"registrada por {u['name']}: a invoice nº {numero} saiu (conferida no QuickBooks)",
                                    "invoice": inv.get("id") or numero, "numero": numero, "total": total,
                                    "cliente_qbo": inv.get("cliente_id"), "pendente": False})
            g.update(invoice_pendente=False)
            if espera:                    # quem registra é o gerente ou o dono: o valor da invoice fica conferido
                g.update(aprovado=True, valor_aprovado=o["amount"],
                         liberada={"por": u["name"], "em": agora(), "valor": o["amount"], "registrada": numero})
            if float(pend.get("deposito") or 0) > 0 and not g.get("deposito_cobrado"):
                g["deposito_cobrado"] = inv.get("id") or numero
        g.pop("cobrando", None)
    with transacao(con, imediata=True):
        if _sem_desfecho(con, oid, ler_closing(con, oid)[1] or {}) != pend:
            raise HTTPException(409, "Esta venda mudou agora mesmo: recarregue e confira.")
        campos = {"stage": etapa, **({"next_at": None} if etapa == "GANHO" else {})} if etapa else {}
        f = gravar_fechamento(con, oid, muda, **campos)
        _ev(con, oid, "invoice", f"Invoice nº {numero} registrada por {u['name']}: saiu na tentativa de {pend.get('por') or 'alguém'} "
                                 f"(conferida no QuickBooks)", {"invoice": inv.get("id"), "numero": numero, "total": total},
            f"user:{u['id']}", 1)
        auditar(con, "sales.invoice.registered", f"user:{u['id']}", user_id=u["id"], entity_type="opportunity", entity_id=oid,
                detail={"tentativa": pend["tentativa"], "acao": pend.get("acao"), "invoice": inv.get("id"), "numero": numero,
                        "total": total, "esperado": esperado, "diferente": diferente, "cliente_qbo": inv.get("cliente_id")},
                ip=auth._ip(request))
    aviso = (f"A invoice nº {numero} é de ${float(total):g}, e a tentativa cobrava ${esperado:g}." if diferente else None)
    return {"ok": True, "fechamento": f, "aviso": aviso}

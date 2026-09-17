"""Vendas: o fluxo do closer (dono, 17/09) — aprovado no canvas antes de entrar aqui.

Oportunidade NÃO é cliente: vive em `opportunities`, com linha do tempo própria
(`opp_events`), e só vira card de cliente no Ganho. O closer liga por fora e registra
tudo aqui: ligação, retorno, anotação, etapa. Quando fecha, UMA tela dispara a lista:
card do cliente, cliente e invoice no QuickBooks, waiver no DocuSign, tarefa no Asana,
Kommo em "Closed won" e as tarefas personalizadas que ele escrever.

Travas: cada passo é gravado com resultado; falha de um não derruba os outros. Valor fora
da tabela de preços não bloqueia o fechamento — a invoice fica pendente de aprovação do
dono (mesma regra das políticas da IA). Nada de e-mail livre: o Gmail do painel é só
leitura, então "e-mail" só existe como waiver/invoice (que o próprio sistema envia) ou
como tarefa personalizada.
"""
import json
import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import agora, atualizar, auditar, get_db, inserir, todos, um
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
    if u and u["role"] == "CLOSER" and o["closer_user_id"] not in (None, u["id"]):
        raise HTTPException(403, "Esta oportunidade é de outro closer.")
    o["closing"] = json.loads(o["closing"] or "null")
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
    """O quadro: uma coluna por etapa, na ordem do fluxo. Closer vê as dele por padrão."""
    so_minhas = minhas or u["role"] == "CLOSER"
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
def agenda(dias: int = 7, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Agenda de vendas: retornos marcados, atrasado primeiro. Só os do closer, quando é closer."""
    where, args = "WHERE o.next_at IS NOT NULL AND o.stage NOT IN ('GANHO','PERDIDO')", []
    if u["role"] == "CLOSER":
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


@r.get("/{oid}")
def detalhe(oid: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    o = _opp(con, oid, u)
    evs = todos(con, "SELECT * FROM opp_events WHERE opp_id=? ORDER BY at DESC, id DESC LIMIT 200", (oid,))
    for e in evs:
        if e["detail"] and e["detail"].startswith(("{", "[")):
            try:
                e["detail"] = json.loads(e["detail"])
            except ValueError:
                pass
    return {"oportunidade": o, "eventos": evs, "etapas": [{"codigo": k, "nome": v} for k, v in ETAPA_PT.items()],
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
def criar(dados: OppIn, request: Request, u=Depends(auth.exige("CLOSER")), con: sqlite3.Connection = Depends(get_db)):
    """Nova oportunidade: o closer cria durante a ligação, em segundos."""
    campos = _campos(dados)
    if not campos.get("name"):
        raise HTTPException(400, "Nome é obrigatório.")
    ja = None
    if campos.get("email"):
        ja = um(con, "SELECT id, name FROM clients WHERE email=?", (campos["email"],))
    oid = inserir(con, "opportunities", closer_user_id=u["id"], updated_at=agora(), **campos)
    _ev(con, oid, "stage", f"Oportunidade criada em {ETAPA_PT[campos.get('stage', 'NOVO')]}",
        {"origem": campos.get("source"), "ja_e_cliente": ja["name"] if ja else None}, f"user:{u['id']}", 1)
    auditar(con, "sales.create", f"user:{u['id']}", user_id=u["id"], entity_type="opportunity", entity_id=oid,
            detail={"nome": campos.get("name"), "origem": campos.get("source")}, ip=auth._ip(request))
    con.commit()
    return {"id": oid, "ja_e_cliente": ja and {"id": ja["id"], "nome": ja["name"]}}


@r.patch("/{oid}")
def editar(oid: int, dados: OppIn, request: Request, u=Depends(auth.exige("CLOSER")), con: sqlite3.Connection = Depends(get_db)):
    o = _opp(con, oid, u)
    campos = _campos(dados)
    atualizar(con, "opportunities", oid, updated_at=agora(), **campos)
    mudou = {k: v for k, v in campos.items() if str(o.get(k) or "") != str(v or "")}
    if mudou:
        _ev(con, oid, "note", "Ficha editada", mudou, f"user:{u['id']}")
    auditar(con, "sales.update", f"user:{u['id']}", user_id=u["id"], entity_type="opportunity", entity_id=oid,
            detail=mudou, ip=auth._ip(request))
    con.commit()
    return {"ok": True, "mudou": sorted(mudou)}


class LigacaoIn(BaseModel):
    resultado: str
    minutos: int | None = None
    texto: str | None = None
    proximo_em: str | None = None
    proximo_que: str | None = None
    etapa: str | None = None


@r.post("/{oid}/call")
def ligacao(oid: int, dados: LigacaoIn, request: Request, u=Depends(auth.exige("CLOSER")), con: sqlite3.Connection = Depends(get_db)):
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
    return {"ok": True, "etapa": campos.get("stage", o["stage"]), "next_at": campos.get("next_at", o["next_at"])}


class RetornoIn(BaseModel):
    quando: str
    o_que: str | None = None


@r.post("/{oid}/next")
def retorno(oid: int, dados: RetornoIn, u=Depends(auth.exige("CLOSER")), con: sqlite3.Connection = Depends(get_db)):
    _opp(con, oid, u)
    atualizar(con, "opportunities", oid, next_at=dados.quando, next_what=_limpa(dados.o_que) or "retorno", updated_at=agora())
    _ev(con, oid, "next", f"Retorno marcado: {quando_pt(dados.quando)}", _limpa(dados.o_que), f"user:{u['id']}")
    con.commit()
    return {"ok": True}


class TextoIn(BaseModel):
    texto: str


@r.post("/{oid}/note")
def anotar(oid: int, dados: TextoIn, u=Depends(auth.exige("CLOSER")), con: sqlite3.Connection = Depends(get_db)):
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
def mover(oid: int, dados: EtapaIn, request: Request, u=Depends(auth.exige("CLOSER")), con: sqlite3.Connection = Depends(get_db)):
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
    return {"ok": True}


@r.post("/from-lead/{lead_id}", status_code=201)
def do_chat(lead_id: int, u=Depends(auth.exige("CLOSER")), con: sqlite3.Connection = Depends(get_db)):
    """"Passar para o closer": o lead do chat do Kommo vira oportunidade, com o que já se sabe."""
    l = um(con, "SELECT * FROM crm_leads WHERE id=?", (lead_id,))
    if not l:
        raise HTTPException(404, "Lead não encontrado.")
    ja = um(con, "SELECT id FROM opportunities WHERE crm_lead_id=?", (lead_id,))
    if ja:
        return {"id": ja["id"], "reaproveitada": True}
    oid = inserir(con, "opportunities", name=l["contact_name"] or l["name"] or f"Lead {l['external_id']}",
                  email=(l["contact_email"] or None), phone=l["contact_phone"], source=l["source"] or "Kommo",
                  crm_lead_id=lead_id, closer_user_id=u["id"], updated_at=agora())
    _ev(con, oid, "stage", "Veio do chat do Kommo", {"lead": l["external_id"], "canal": l["source"]}, f"user:{u['id']}", 1)
    con.commit()
    return {"id": oid, "reaproveitada": False}


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
    preco_tabela: float | None = None
    passos: dict[str, bool] = {}
    extras: list[ExtraIn] = []


def _confere_preco(servico, valor, preco_tabela):
    """Invoice fora da tabela de preços é do dono (política 17/09). A tela manda o preço da
    tabela (rate card) quando o serviço tem um; sem referência, não invento: sai como
    "sem referência" e a invoice segue com o closer respondendo pelo valor."""
    if valor is None:
        return False, "sem valor"
    if preco_tabela is None:
        return None, "sem preço de tabela para este serviço"
    if abs(float(valor) - float(preco_tabela)) < 0.01:
        return True, "valor da tabela"
    return False, f"valor ${valor:g} difere da tabela (${float(preco_tabela):g})"


def _passo(saida, nome, ok, detalhe, extra=None):
    saida.append({"passo": nome, "nome": PASSO_PT.get(nome, nome), "ok": ok, "detalhe": detalhe, **(extra or {})})
    return saida[-1]


def _cliente_do_fechamento(con, o, nota):
    """Card do cliente: liga ao que existe (mesmo e-mail) ou cria. Nunca duplica."""
    achado = None
    if o["email"]:
        achado = um(con, "SELECT * FROM clients WHERE email=?", (o["email"],))
    if not achado and o["phone"]:
        from command_center.providers import identidade
        d = identidade.so_digitos(o["phone"])
        if d:
            for c in todos(con, "SELECT * FROM clients WHERE phone IS NOT NULL"):
                if identidade.so_digitos(c["phone"]) == d:
                    achado = c
                    break
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


def _qbo(con, o, aprovado):
    """Cliente no QuickBooks (se não existe) e invoice criada + enviada. Fora da tabela: fica pendente."""
    nome, email = o["name"], o["email"]
    busca = chamar("quickbooks", "qbo_clientes_buscar", termo=email or nome, maximo=5) or []
    cliente = (busca[0] if busca else None)
    if not cliente:
        novo = _aplicando("quickbooks", chamar, "quickbooks", "qbo_criar_cliente", nome=nome, email=email, telefone=o["phone"])
        cliente = {"id": (novo or {}).get("id") or (novo or {}).get("cliente_id"), "nome": nome}
    cid = str(cliente.get("id") or cliente.get("cliente_id") or "")
    if not cid:
        raise RuntimeError("QuickBooks não devolveu o id do cliente")
    if not aprovado:
        return {"cliente_qbo": cid, "invoice": None, "pendente": True}
    from command_center.api import acoes
    memo = acoes.memo_invoice(produto=o["service"], piloto=o["pilot_name"], data_servico=o["service_date"])
    linhas = [{"descricao": o["service"] or "Serviço URACE", "valor": float(o["amount"] or 0)}]
    inv = _aplicando("quickbooks", chamar, "quickbooks", "qbo_criar_e_enviar_invoice", cliente_id=cid,
                     linhas=linhas, vence_em=o["service_date"], memo=memo, email=email, nota_privada=memo)
    return {"cliente_qbo": cid, "invoice": (inv or {}).get("id") or (inv or {}).get("numero"), "pendente": False}


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
def fechar(oid: int, dados: FecharIn, request: Request, u=Depends(auth.exige("CLOSER")), con: sqlite3.Connection = Depends(get_db)):
    """Fechar venda: uma tela, um botão. Cada passo ligado roda aqui e o resultado fica gravado.
    Falha de um passo não impede os outros; a tela mostra o que faltou, com o botão manual."""
    o = _opp(con, oid, u)
    campos = {k: v for k, v in dados.model_dump(exclude={"passos", "extras", "nota_cliente", "preco_tabela"}).items() if v is not None}
    if campos:
        for k in ("service", "email", "phone", "pilot_name"):
            if k in campos:
                campos[k] = _limpa(str(campos[k]))
        atualizar(con, "opportunities", oid, updated_at=agora(), **campos)
        o = _opp(con, oid, u)
    if not o["service"] or o["amount"] is None:
        raise HTTPException(400, "Para fechar, diga o serviço e o valor.")
    quer = {p: bool(dados.passos.get(p, True)) for p in PASSOS}
    na_tabela, por_que = _confere_preco(o["service"], o["amount"], dados.preco_tabela)
    aprovado = na_tabela is not False or u["role"] in ("ADMIN", "MANAGER")
    saida = []

    if quer["cliente"]:
        try:
            cid, det = _cliente_do_fechamento(con, o, _limpa(dados.nota_cliente))
            atualizar(con, "opportunities", oid, client_id=cid)
            o["client_id"] = cid
            _passo(saida, "cliente", True, det, {"client_id": cid})
        except Exception as e:                                   # noqa: BLE001
            _passo(saida, "cliente", False, f"{type(e).__name__}: {str(e)[:200]}")

    for nome, fn in (("qbo", lambda: _qbo(con, o, aprovado)), ("waiver", lambda: _waiver(con, o)),
                     ("asana", lambda: _asana(con, o)), ("kommo", lambda: _kommo_ganho(con, o))):
        if not quer[nome]:
            _passo(saida, nome, None, "desligado pelo closer")
            continue
        try:
            res = fn()
            if nome == "qbo" and res.get("pendente"):
                _passo(saida, nome, None, f"invoice esperando aprovação do dono: {por_que}", res)
            else:
                _passo(saida, nome, True, "feito", res if isinstance(res, dict) else None)
        except NaoConectado as e:
            _passo(saida, nome, False, f"não conectado: {str(e)[:160]}")
        except Exception as e:                                   # noqa: BLE001
            _passo(saida, nome, False, str(e)[:240])

    for e in dados.extras[:10]:
        try:
            res = _extra(con, o, e, u["id"])
            _passo(saida, f"extra:{e.titulo[:40]}", True, f"tarefa em {res['onde']}", res)  # nome = o que o closer escreveu
        except Exception as ex:                                  # noqa: BLE001
            _passo(saida, f"extra:{e.titulo[:40]}", False, str(ex)[:200])

    fechado = {"em": agora(), "por": u["name"], "na_tabela": na_tabela, "aprovado": aprovado,
               "motivo_preco": por_que, "passos": saida}
    etapa = "GANHO" if o["client_id"] else "FECHAMENTO"
    atualizar(con, "opportunities", oid, stage=etapa, closing=json.dumps(fechado, ensure_ascii=False),
              next_at=None if etapa == "GANHO" else o["next_at"], updated_at=agora())
    for p in saida:
        _ev(con, oid, PASSO_KIND.get(p["passo"], "task"), f"{p['nome']}: {p['detalhe']}",
            p.get("client_id") and {"client_id": p["client_id"]} or None,
            f"user:{u['id']}", 1 if p["ok"] else (0 if p["ok"] is False else None))
    _ev(con, oid, "stage", f"Venda fechada · {ETAPA_PT[etapa]}", {"valor": o["amount"], "servico": o["service"]}, f"user:{u['id']}", 1)
    auditar(con, "sales.close", f"user:{u['id']}", user_id=u["id"], entity_type="opportunity", entity_id=oid,
            detail={"valor": o["amount"], "servico": o["service"], "passos": {p["passo"]: p["ok"] for p in saida}},
            ip=auth._ip(request))
    con.commit()
    return {"ok": True, "etapa": etapa, "fechamento": fechado, "client_id": o["client_id"]}


@r.post("/{oid}/step/{passo}")
def refazer(oid: int, passo: str, u=Depends(auth.exige("CLOSER")), con: sqlite3.Connection = Depends(get_db)):
    """Botão manual de um passo (reenviar waiver, mandar a invoice, criar a tarefa…)."""
    o = _opp(con, oid, u)
    if passo not in PASSOS:
        raise HTTPException(400, f"Passo inválido. Use: {', '.join(PASSOS)}")
    try:
        if passo == "cliente":
            cid, det = _cliente_do_fechamento(con, o, None)
            atualizar(con, "opportunities", oid, client_id=cid)
            res, ok = {"client_id": cid, "detalhe": det}, True
        elif passo == "qbo":
            res, ok = _qbo(con, o, True), True
        elif passo == "waiver":
            res, ok = _waiver(con, o), True
        elif passo == "asana":
            res, ok = _asana(con, o), True
        else:
            res, ok = _kommo_ganho(con, o), True
    except NaoConectado as e:
        raise HTTPException(503, f"não conectado: {e}")
    except Exception as e:                                       # noqa: BLE001
        raise HTTPException(502, str(e)[:300])
    _ev(con, oid, PASSO_KIND[passo], f"{PASSO_PT[passo]}: refeito à mão", res, f"user:{u['id']}", 1 if ok else 0)
    fechado = o["closing"] or {"passos": []}
    fechado["passos"] = [p for p in fechado.get("passos", []) if p.get("passo") != passo] + \
                        [{"passo": passo, "nome": PASSO_PT[passo], "ok": True, "detalhe": "refeito à mão", **(res if isinstance(res, dict) else {})}]
    atualizar(con, "opportunities", oid, closing=json.dumps(fechado, ensure_ascii=False), updated_at=agora())
    con.commit()
    return {"ok": True, "passo": passo, "resultado": res}

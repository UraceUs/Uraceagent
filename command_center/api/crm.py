"""CRM (Kommo) dentro do Command Center.

Pedido do dono (09/09, retomado em 10/09): uma aba do Kommo no painel com
o funil, a conversa, a resposta, o estágio, as tags, o contato e a origem
do lead — sem abrir o Kommo.

Como funciona:
  * LER vem do espelho (crm_leads/crm_messages), que a sincronia enche.
    Ao abrir um lead, o painel busca a conversa ao vivo e guarda o que for
    novo — assim a tela é rápida e o conteúdo é o de agora.
  * ESCREVER (mover de etapa, marcar tag, anotar, responder) chama as
    PORTAS HUMANAS do MCP com APLICAR liberado só naquela chamada: quem
    autoriza é o clique de uma pessoa, e tudo fica na auditoria.
  * RESPONDER sai pelo Salesbot da conta e aparece como mensagem do bot
    (limite conhecido do Kommo). Sem KOMMO_BOT_ID a resposta é recusada
    com explicação; a nota interna continua funcionando.
  * O webhook do Kommo entra por /crm/webhook com segredo compartilhado —
    é assim que a mensagem que chega no Instagram/Facebook/WhatsApp
    aparece aqui sem esperar a próxima sincronia.

Nada apaga lead, contato, nota ou tag: essa porta não existe.
"""
import hmac
import json
import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import agora, atualizar, auditar, get_db, inserir, todos, um
from command_center.providers import NaoConectado, chamar, modulo

r = APIRouter(prefix="/ops/api/crm")
SISTEMA = "kommo"


def _aplicando(fn, *a, **kw):
    """Ato humano: APLICAR=1 só nesta chamada (igual ao motor da IA)."""
    anterior = os.environ.get("APLICAR")
    os.environ["APLICAR"] = "1"
    try:
        return fn(*a, **kw)
    finally:
        if anterior is None:
            os.environ.pop("APLICAR", None)
        else:
            os.environ["APLICAR"] = anterior


def _erro(e):
    if isinstance(e, NaoConectado):
        return HTTPException(503, f"Kommo não conectado: {e}")
    return HTTPException(502, str(e)[:300])


def _lead(con, lid):
    l = um(con, """SELECT c.*, cl.name AS client_name, cl.pilot_name AS client_pilot
                   FROM crm_leads c LEFT JOIN clients cl ON cl.id=c.client_id WHERE c.id=?""", (lid,))
    if not l:
        raise HTTPException(404, "Lead not found.")
    l["tags"] = json.loads(l["tags"] or "[]")
    return l


# ------------------------------------------------------------- leitura
@r.get("/board")
def board(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """O funil como o dono vê no Kommo: colunas na ordem, leads em cada uma."""
    leads = todos(con, """SELECT c.*, cl.name AS client_name, cl.pilot_name AS client_pilot
                          FROM crm_leads c LEFT JOIN clients cl ON cl.id=c.client_id
                          ORDER BY COALESCE(c.stage_order, 0), COALESCE(c.updated_at_src, c.synced_at) DESC""")
    for l in leads:
        l["tags"] = json.loads(l["tags"] or "[]")
    funis, indice = [], {}
    for l in leads:
        fid = l["pipeline_id"] or "—"
        f = indice.get(fid)
        if not f:
            f = {"id": fid, "nome": l["pipeline_name"] or "Funil", "etapas": [], "_et": {}}
            indice[fid] = f
            funis.append(f)
        eid = l["stage_id"] or "—"
        e = f["_et"].get(eid)
        if not e:
            e = {"id": eid, "nome": l["stage_name"] or "Etapa", "ordem": l["stage_order"] or 0, "leads": []}
            f["_et"][eid] = e
            f["etapas"].append(e)
        e["leads"].append(l)
    for f in funis:
        f["etapas"].sort(key=lambda e: e["ordem"] or 0)
        f.pop("_et")
    integ = um(con, "SELECT status, last_success_at, last_error FROM integrations WHERE system='kommo'") or {}
    return {"funis": funis, "total": len(leads),
            "pendentes": sum(1 for l in leads if l["needs_reply"]),
            "integracao": integ}


@r.get("/stages")
def stages(u=Depends(auth.usuario_atual)):
    """Etapas de verdade, direto do Kommo (para o seletor de mover)."""
    try:
        return chamar(SISTEMA, "kommo_funis")
    except Exception as e:
        raise _erro(e)


@r.get("/leads/{lid}")
def lead(lid: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Lead do espelho + conversa. Busca a conversa ao vivo e guarda o que for novo."""
    l = _lead(con, lid)
    aviso = None
    try:
        msgs = chamar(SISTEMA, "kommo_conversa", lead_id=l["external_id"], maximo=100)
        from command_center.providers.sync import guardar_conversa
        novas, ultima = guardar_conversa(con, lid, msgs)
        if ultima:
            atualizar(con, "crm_leads", lid, last_message_at=ultima)
        con.commit()
    except NaoConectado as e:
        aviso = f"Kommo não conectado: {e}. Mostrando o que já estava guardado."
    except Exception as e:
        aviso = f"Não deu para ler a conversa agora: {str(e)[:200]}"
    mensagens = todos(con, "SELECT * FROM crm_messages WHERE lead_id=? ORDER BY at, id", (lid,))
    return {"lead": l, "mensagens": mensagens, "aviso": aviso,
            "responder_habilitado": bool(os.environ.get("KOMMO_BOT_ID"))}


# ------------------------------------------------------------- escrita
class EtapaIn(BaseModel):
    stage_id: str
    pipeline_id: str | None = None


@r.post("/leads/{lid}/stage")
def mover(lid: int, dados: EtapaIn, request: Request, u=Depends(auth.exige("OPERATOR")),
          con: sqlite3.Connection = Depends(get_db)):
    l = _lead(con, lid)
    try:
        res = _aplicando(modulo(SISTEMA).mover_etapa_humano, l["external_id"], dados.stage_id,
                         dados.pipeline_id or l["pipeline_id"])
    except Exception as e:
        raise _erro(e)
    atualizar(con, "crm_leads", lid, stage_id=str(dados.stage_id), stage_name=res.get("etapa") or l["stage_name"],
              pipeline_id=dados.pipeline_id or l["pipeline_id"], synced_at=agora())
    auditar(con, "crm.stage", f"user:{u['id']}", user_id=u["id"], entity_type="crm_lead", entity_id=lid,
            detail={"de": l["stage_name"], "para": res.get("etapa") or dados.stage_id}, ip=auth._ip(request))
    con.commit()
    return {"ok": True, **res}


class TagsIn(BaseModel):
    tags: list[str]


@r.post("/leads/{lid}/tags")
def tags(lid: int, dados: TagsIn, request: Request, u=Depends(auth.exige("OPERATOR")),
         con: sqlite3.Connection = Depends(get_db)):
    l = _lead(con, lid)
    try:
        res = _aplicando(modulo(SISTEMA).marcar_tag_humano, l["external_id"], dados.tags)
    except Exception as e:
        raise _erro(e)
    atualizar(con, "crm_leads", lid, tags=json.dumps(res.get("tags") or l["tags"], ensure_ascii=False), synced_at=agora())
    auditar(con, "crm.tags", f"user:{u['id']}", user_id=u["id"], entity_type="crm_lead", entity_id=lid,
            detail={"novas": res.get("novas")}, ip=auth._ip(request))
    con.commit()
    return {"ok": True, **res}


class TextoIn(BaseModel):
    text: str


@r.post("/leads/{lid}/note")
def nota(lid: int, dados: TextoIn, request: Request, u=Depends(auth.exige("OPERATOR")),
         con: sqlite3.Connection = Depends(get_db)):
    """Anotação interna: fica no Kommo e aqui. Não vai para o cliente."""
    l = _lead(con, lid)
    try:
        res = _aplicando(modulo(SISTEMA).nota_humana, l["external_id"], dados.text)
    except Exception as e:
        raise _erro(e)
    inserir(con, "crm_messages", lead_id=lid, external_id=res.get("nota_id"), direction="nota",
            author=u["name"], text=dados.text[:8000], at=agora(), source="painel")
    auditar(con, "crm.note", f"user:{u['id']}", user_id=u["id"], entity_type="crm_lead", entity_id=lid,
            detail={"chars": len(dados.text)}, ip=auth._ip(request))
    con.commit()
    return {"ok": True, **res}


@r.post("/leads/{lid}/reply")
def responder(lid: int, dados: TextoIn, request: Request, u=Depends(auth.exige("OPERATOR")),
              con: sqlite3.Connection = Depends(get_db)):
    """Responde ao lead no canal dele. Ato humano: nunca a IA sozinha."""
    l = _lead(con, lid)
    try:
        res = _aplicando(modulo(SISTEMA).responder_humano, l["external_id"], dados.text)
    except Exception as e:
        raise _erro(e)
    inserir(con, "crm_messages", lead_id=lid, external_id=None, direction="saida",
            author=u["name"], text=dados.text[:8000], at=agora(), source="painel")
    atualizar(con, "crm_leads", lid, needs_reply=0, synced_at=agora())
    auditar(con, "crm.reply", f"user:{u['id']}", user_id=u["id"], entity_type="crm_lead", entity_id=lid,
            detail={"chars": len(dados.text), "bot": res.get("bot_id")}, ip=auth._ip(request))
    con.commit()
    return {"ok": True, **res}


class VinculoIn(BaseModel):
    client_id: int | None = None


@r.post("/leads/{lid}/link")
def vincular(lid: int, dados: VinculoIn, request: Request, u=Depends(auth.exige("OPERATOR")),
             con: sqlite3.Connection = Depends(get_db)):
    """Liga (ou desliga) o lead ao card do cliente, à mão."""
    l = _lead(con, lid)
    if dados.client_id and not um(con, "SELECT 1 AS x FROM clients WHERE id=?", (dados.client_id,)):
        raise HTTPException(404, "Client not found.")
    atualizar(con, "crm_leads", lid, client_id=dados.client_id, synced_at=agora())
    auditar(con, "crm.link", f"user:{u['id']}", user_id=u["id"], entity_type="crm_lead", entity_id=lid,
            detail={"de": l["client_id"], "para": dados.client_id}, ip=auth._ip(request))
    con.commit()
    return {"ok": True, "client_id": dados.client_id}


@r.post("/sync")
def sincronizar(u=Depends(auth.exige("MANAGER")), con: sqlite3.Connection = Depends(get_db)):
    from command_center.providers.sync import sync_kommo
    res = sync_kommo(con)
    con.commit()
    return res


# ------------------------------------------------------------- webhook
@r.post("/webhook")
async def webhook(request: Request, con: sqlite3.Connection = Depends(get_db)):
    """Mensagem que chega no Kommo (Salesbot/webhook) entra aqui na hora.

    Sem cookie de sessão: quem prova a origem é o segredo compartilhado
    (KOMMO_WEBHOOK_SECRET), comparado em tempo constante. Sem segredo
    configurado, a porta fica fechada — não se aceita post anônimo."""
    segredo = os.environ.get("KOMMO_WEBHOOK_SECRET", "")
    enviado = request.headers.get("x-urace-secret") or request.query_params.get("secret") or ""
    if not segredo or not hmac.compare_digest(segredo, enviado):
        raise HTTPException(403, "Forbidden.")
    try:
        corpo = await request.json()
    except Exception:
        corpo = dict(await request.form())
    ext = str(corpo.get("lead_id") or corpo.get("entity_id") or "").strip()
    texto = (corpo.get("text") or corpo.get("message") or "").strip()
    if not ext:
        raise HTTPException(400, "sem lead_id")
    l = um(con, "SELECT id FROM crm_leads WHERE external_id=?", (ext,))
    if not l:                                   # lead que ainda não veio na sincronia: cria o mínimo
        lid = inserir(con, "crm_leads", external_id=ext, name=corpo.get("name") or f"Lead {ext}",
                      source=corpo.get("source"), synced_at=agora())
    else:
        lid = l["id"]
    if texto:
        inserir(con, "crm_messages", lead_id=lid, external_id=str(corpo.get("message_id") or "") or None,
                direction="entrada", author=corpo.get("author") or corpo.get("name") or "cliente",
                text=texto[:8000], at=agora(), source="webhook")
        atualizar(con, "crm_leads", lid, last_message_at=agora(), needs_reply=1)
    auditar(con, "crm.webhook", "kommo", entity_type="crm_lead", entity_id=lid,
            detail={"chars": len(texto), "origem": corpo.get("source")})
    con.commit()
    return {"ok": True, "lead_id": lid}

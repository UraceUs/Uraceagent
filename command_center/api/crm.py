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
  * O CHAT usa o circuito do Salesbot provado em 24/08: o bloco do widget
    manda cada mensagem recebida para /crm/hook (?key=KOMMO_HOOK_KEY) e o
    bot fica esperando; a RESPOSTA humana entra numa fila e sai pela
    continuação (return_url) com o texto de quem escreveu — na hora, se o
    bot ainda espera; senão o painel dispara o bot (bots/run) e ele volta ao
    hook para buscar a fila. Sem entrega em PRAZO_FILA_S, vira nota no lead
    e fica marcada como não entregue. Aparece como mensagem do bot: limite
    do Kommo, dito na tela.
  * /crm/webhook (JSON + segredo) continua existindo para automações
    externas; o caminho real do chat é o hook.

Nada apaga lead, contato, nota ou tag: essa porta não existe.
"""
import hmac
import json
import os
import sqlite3

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import agora, atualizar, auditar, get_db, inserir, todos, um
from command_center.providers import NaoConectado, chamar, modulo

r = APIRouter(prefix="/ops/api/crm")
SISTEMA = "kommo"


def _aplicando(fn, *a, **kw):
    """Ato humano: APLICAR ligado só NESTA thread e só nesta chamada. Não mexe no
    ambiente do processo — uma tarefa de fundo do hook rodando ao mesmo tempo que uma
    ação da IA não pode virar a simulação dela em escrita real (nem o contrário)."""
    k = modulo(SISTEMA)
    ctx = getattr(k, "_ctx", None)
    if ctx is None:                                   # módulo falso nos testes: cai no ambiente
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
        novas, _ = guardar_conversa(con, lid, msgs)
        if novas:
            from command_center.providers.sync import recalcular_conversa
            recalcular_conversa(con, lid)
        con.commit()
    except NaoConectado as e:
        aviso = f"Kommo não conectado: {e}. Mostrando o que já estava guardado."
    except Exception as e:
        aviso = f"Não deu para ler a conversa agora: {str(e)[:200]}"
    varrer_fila(con); con.commit()
    mensagens = todos(con, "SELECT * FROM crm_messages WHERE lead_id=? ORDER BY at, id", (lid,))
    l = _lead(con, lid)
    return {"lead": l, "mensagens": mensagens, "aviso": aviso,
            "responder_habilitado": bool(os.environ.get("KOMMO_BOT_ID")) or _return_fresco(l),
            "chat_ligado": bool(_chave_hook()) and bool(os.environ.get("KOMMO_BOT_ID"))}


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


JANELA_RETURN_S = 50          # o bot espera >= 58 s (provado 24/08); usamos com folga
PRAZO_FILA_S = 150            # sem entrega até aqui, a mensagem vira nota no Kommo e fica marcada


def _reivindicar_fila(con, lead_id):
    """Marca as mensagens na fila como 'sending' de forma atômica e devolve-as em ordem.
    Duas entregas concorrentes (resposta na hora + tarefa de fundo do hook) não levam a
    mesma mensagem: só quem mudou o status leva."""
    fila = todos(con, """SELECT id, text FROM crm_messages WHERE lead_id=? AND direction='saida' AND status='queued'
                         ORDER BY id""", (lead_id,))
    minhas = []
    for m in fila:
        cur = con.execute("UPDATE crm_messages SET status='sending' WHERE id=? AND status='queued'", (m["id"],))
        if cur.rowcount == 1:
            minhas.append(m)
    con.commit()
    return minhas


def _entregar(con, lead, mensagens):
    """Entrega as mensagens reivindicadas numa continuação só (o bot só espera uma).
    Devolve (ok, detalhe). Falha devolve as mensagens para a fila com o motivo."""
    texto = "\n\n".join(m["text"] for m in mensagens if m.get("text"))
    ok, det = modulo(SISTEMA).continuar_bot_humano(lead["return_url"], texto)
    if ok:
        for m in mensagens:
            atualizar(con, "crm_messages", m["id"], status="sent", error=None)
        atualizar(con, "crm_leads", lead["id"], return_url=None, return_token=None, return_at=None,
                  needs_reply=0, synced_at=agora())
    else:
        for m in mensagens:
            atualizar(con, "crm_messages", m["id"], status="queued", error=det[:300])
        if "404" in det or "não estava mais esperando" in det or "fora do domínio" in det:
            atualizar(con, "crm_leads", lead["id"], return_url=None, return_token=None, return_at=None)
    con.commit()
    return ok, det


def _return_fresco(lead):
    if not lead.get("return_url") or not lead.get("return_at"):
        return False
    from datetime import datetime, timezone
    try:
        idade = (datetime.now(timezone.utc) - datetime.fromisoformat(lead["return_at"].replace("Z", "+00:00"))).total_seconds()
    except ValueError:
        return False
    return idade < JANELA_RETURN_S


def varrer_fila(con):
    """Mensagem na fila há mais de PRAZO_FILA_S sem o bot abrir o canal: não fica em
    silêncio. Vira nota no lead ("enviar manualmente") e fica marcada como falha."""
    from datetime import datetime, timedelta, timezone
    limite = (datetime.now(timezone.utc) - timedelta(seconds=PRAZO_FILA_S)).strftime("%Y-%m-%dT%H:%M:%S")
    velhas = todos(con, """SELECT m.*, l.external_id AS lead_ext FROM crm_messages m JOIN crm_leads l ON l.id=m.lead_id
                           WHERE m.direction='saida' AND m.status IN ('queued','sending') AND m.at < ?""", (limite,))
    for m in velhas:
        motivo = "o bot não abriu o chat a tempo (Salesbot ligado? gatilho na etapa? KOMMO_BOT_ID?)"
        try:
            _aplicando(modulo(SISTEMA).nota_humana, m["lead_ext"],
                       f"[Command Center — NÃO chegou ao cliente, enviar manualmente]\n{m['text']}")
            motivo += " — texto gravado como nota no lead"
        except Exception as e:
            motivo += f" — e a nota também falhou: {str(e)[:120]}"
        atualizar(con, "crm_messages", m["id"], status="failed", error=motivo[:300])
        auditar(con, "crm.reply.failed", "system", entity_type="crm_lead", entity_id=m["lead_id"], detail={"msg": m["id"]})
    return len(velhas)


@r.post("/leads/{lid}/reply")
def responder(lid: int, dados: TextoIn, request: Request, u=Depends(auth.exige("OPERATOR")),
              con: sqlite3.Connection = Depends(get_db)):
    """Responde ao lead no canal em que ele falou. Ato humano: nunca a IA sozinha.

    Caminho: a mensagem entra na fila; se o Salesbot ainda está esperando (o lead
    acabou de falar), sai na hora pela continuação; senão o painel dispara o bot
    (bots/run), que chama o hook sem mensagem e recebe a fila. Se em PRAZO_FILA_S
    o bot não abrir o chat, a varredura marca como falha e grava nota no Kommo."""
    texto = (dados.text or "").strip()
    if not texto:
        raise HTTPException(400, "Resposta vazia.")
    l = _lead(con, lid)
    mid = inserir(con, "crm_messages", lead_id=lid, external_id=None, direction="saida", status="queued",
                  author=u["name"], text=texto[:8000], at=agora(), source="painel")
    auditar(con, "crm.reply", f"user:{u['id']}", user_id=u["id"], entity_type="crm_lead", entity_id=lid,
            detail={"chars": len(texto), "msg": mid}, ip=auth._ip(request))
    con.commit()
    como, det = "fila", None
    if _return_fresco(l):
        minhas = _reivindicar_fila(con, lid)          # a fila inteira, em ordem — inclui a de agora
        if minhas:
            ok, det = _aplicando(_entregar, con, l, minhas)
            como = "entregue" if ok else "fila"
    if como == "fila" and um(con, "SELECT 1 AS x FROM crm_messages WHERE id=? AND status='queued'", (mid,)):
        try:
            _aplicando(modulo(SISTEMA).abrir_canal_humano, l["external_id"])
            como = "bot disparado"
        except Exception as e:
            atualizar(con, "crm_messages", mid, status="failed", error=str(e)[:300])
            con.commit()
            raise _erro(e)
    con.commit()
    return {"ok": True, "msg_id": mid, "como": como, "detalhe": det,
            "aviso": ("Enviada no chat do lead." if como == "entregue" else
                      "Na fila: o bot do Kommo vai abrir o chat e entregar em segundos. Se em 2-3 min não sair, "
                      "vira nota no lead e fica marcada aqui como não entregue.")}


class VinculoIn(BaseModel):
    client_id: int | None = None


@r.post("/leads/{lid}/link")
def vincular(lid: int, dados: VinculoIn, request: Request, u=Depends(auth.exige("OPERATOR")),
             con: sqlite3.Connection = Depends(get_db)):
    """Liga (ou desliga) o lead ao card do cliente, à mão."""
    l = _lead(con, lid)
    if dados.client_id and not um(con, "SELECT 1 AS x FROM clients WHERE id=?", (dados.client_id,)):
        raise HTTPException(404, "Client not found.")
    atualizar(con, "crm_leads", lid, client_id=dados.client_id, link_by="human", synced_at=agora())
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


# ------------------------------------------------------------- hook do Salesbot (o chat)
def _chave_hook():
    """KOMMO_HOOK_KEY vem do ~/.urace/kommo.env (EnvironmentFile do serviço); se o
    serviço subiu sem ele, o módulo do MCP carrega o arquivo ao ser importado."""
    if not os.environ.get("KOMMO_HOOK_KEY"):
        try:
            modulo(SISTEMA)
        except Exception:
            pass
    return os.environ.get("KOMMO_HOOK_KEY", "")


def _enriquecer_lead(lid, external_id):
    """Lead que chegou pelo hook antes da sincronia: lê no Kommo funil, etapa, origem e contato."""
    from command_center.db import conectar
    con = conectar()
    try:
        d = chamar(SISTEMA, "kommo_lead", lead_id=external_id)
        c = d.get("contato") or {}
        atualizar(con, "crm_leads", lid, name=d.get("nome"), pipeline_id=d.get("funil_id"), pipeline_name=d.get("funil"),
                  stage_id=d.get("etapa_id"), stage_name=d.get("etapa"), stage_order=d.get("ordem"), price=d.get("valor"),
                  source=d.get("origem"), tags=json.dumps(d.get("tags") or [], ensure_ascii=False), link=d.get("link"),
                  contact_name=c.get("nome"), contact_email=c.get("email"), contact_phone=c.get("telefone"),
                  created_at_src=d.get("criado_em"), updated_at_src=d.get("atualizado_em"), synced_at=agora())
        if c.get("email") or c.get("telefone") or c.get("nome"):
            from command_center.providers.sync import _acha_cliente
            cli = _acha_cliente(con, email=(c.get("email") or "").lower() or None, nome=c.get("nome"), telefone=c.get("telefone"))
            if cli:
                atualizar(con, "crm_leads", lid, client_id=cli["id"])
        con.commit()
    except Exception:
        pass
    finally:
        con.close()


def _entregar_fila(lid):
    """Em segundo plano, logo depois do ACK: o bot está esperando, entrega o que há na fila."""
    from command_center.db import conectar
    con = conectar()
    try:
        l = um(con, "SELECT * FROM crm_leads WHERE id=?", (lid,))
        if l and l["return_url"]:
            minhas = _reivindicar_fila(con, lid)
            if minhas:
                _aplicando(_entregar, con, l, minhas)
    finally:
        con.close()


@r.post("/hook")
async def hook(request: Request, background: BackgroundTasks, key: str | None = None,
               con: sqlite3.Connection = Depends(get_db)):
    """O Salesbot do Kommo bate aqui a cada mensagem recebida (bloco do widget,
    widget_request, form-encoded) e quando o painel o dispara para entregar uma
    resposta. ACK em menos de 2 s; o resto é em segundo plano.

    Autenticação: ?key= igual a KOMMO_HOOK_KEY (o widget não manda header). Se
    KOMMO_BOT_SECRET existir, o JWT descartável do bot também é conferido."""
    chave = _chave_hook()
    if not chave or not hmac.compare_digest(chave, key or ""):
        auditar(con, "crm.hook.recusado", "kommo", detail={"motivo": "sem chave configurada" if not chave else "chave não bate",
                                                         "ip": request.headers.get("x-forwarded-for") or (request.client.host if request.client else None)})
        con.commit()
        raise HTTPException(403, "Forbidden.")
    bruto = await request.body()
    try:
        k = modulo(SISTEMA)
    except NaoConectado as ex:
        raise HTTPException(503, f"Kommo não conectado: {ex}")
    payload = k.parse_corpo_hook(bruto)
    tok = payload.get("token") or (payload.get("data") or {}).get("token") if isinstance(payload.get("data"), dict) else payload.get("token")
    if tok and not k.verificar_token_bot(tok):
        raise HTTPException(401, "invalid bot token")
    e = k.extrair_entrada(payload)
    if not e["lead_id"]:
        auditar(con, "crm.hook.ignorado", "kommo", detail={"motivo": "sem lead_id", "amostra": bruto[:200].decode("utf-8", "replace")})
        con.commit()
        return {"ok": True, "ignorado": "sem lead_id"}
    l = um(con, "SELECT * FROM crm_leads WHERE external_id=?", (e["lead_id"],))
    novo = l is None
    if novo:
        lid = inserir(con, "crm_leads", external_id=e["lead_id"], name=e["nome"] or f"Lead {e['lead_id']}",
                      contact_name=e["nome"], contact_phone=e["telefone"], synced_at=agora())
    else:
        lid = l["id"]
        if e["nome"] and not l["contact_name"]:
            atualizar(con, "crm_leads", lid, contact_name=e["nome"], contact_phone=e["telefone"] or l["contact_phone"])
    campos = dict(last_hook_at=agora())
    if e["return_url"]:
        campos.update(return_url=e["return_url"], return_token=e["token"], return_at=agora())
    if e["texto"]:
        import hashlib
        ext = "hook:" + hashlib.sha1(f"{e['lead_id']}|{e['texto']}|{agora()[:16]}".encode()).hexdigest()[:16]
        if not um(con, "SELECT 1 AS x FROM crm_messages WHERE lead_id=? AND external_id=?", (lid, ext)):
            inserir(con, "crm_messages", lead_id=lid, external_id=ext, direction="entrada",
                    author=e["nome"] or "cliente", text=e["texto"][:8000], at=agora(), source="hook")
        campos.update(last_message_at=agora(), needs_reply=1)
    atualizar(con, "crm_leads", lid, **campos)
    auditar(con, "crm.hook", "kommo", entity_type="crm_lead", entity_id=lid,
            detail={"mensagem": bool(e["texto"]), "return_url": bool(e["return_url"]), "novo": novo})
    con.commit()
    if novo:
        background.add_task(_enriquecer_lead, lid, e["lead_id"])
    if e["return_url"]:
        background.add_task(_entregar_fila, lid)
    return {"ok": True}


@r.get("/inbox")
def inbox(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """As conversas, como uma caixa de entrada: quem falou por último primeiro,
    quem espera resposta no topo."""
    varrer_fila(con); con.commit()
    leads = todos(con, """SELECT c.*, cl.name AS client_name, cl.pilot_name AS client_pilot,
                                 (SELECT text FROM crm_messages m WHERE m.lead_id=c.id AND m.direction IN ('entrada','saida')
                                  AND m.text IS NOT NULL ORDER BY m.at DESC, m.id DESC LIMIT 1) AS snippet,
                                 (SELECT COUNT(*) FROM crm_messages m WHERE m.lead_id=c.id AND m.direction IN ('entrada','saida')) AS msgs,
                                 (SELECT COUNT(*) FROM crm_messages m WHERE m.lead_id=c.id AND m.status='failed') AS falhas
                          FROM crm_leads c LEFT JOIN clients cl ON cl.id=c.client_id
                          WHERE c.last_message_at IS NOT NULL OR c.last_hook_at IS NOT NULL
                             OR EXISTS (SELECT 1 FROM crm_messages m WHERE m.lead_id=c.id AND m.direction IN ('entrada','saida'))
                          ORDER BY c.needs_reply DESC, COALESCE(c.last_message_at, c.updated_at_src, c.synced_at) DESC
                          LIMIT 300""")
    for l in leads:
        l["tags"] = json.loads(l["tags"] or "[]")
    return {"conversas": leads, "pendentes": sum(1 for l in leads if l["needs_reply"])}


@r.get("/setup")
def setup(request: Request, u=Depends(auth.exige("ADMIN")), con: sqlite3.Connection = Depends(get_db)):
    """O que falta para o chat funcionar, e a URL exata para colar no bloco do bot."""
    host = os.environ.get("CC_PUBLIC_HOST") or request.headers.get("x-forwarded-host") or request.headers.get("host") or "urace-bridge.duckdns.org"
    chave = _chave_hook()
    ultimo = um(con, "SELECT at AS created_at FROM audit_logs WHERE event='crm.hook' ORDER BY id DESC LIMIT 1")
    hoje = um(con, "SELECT COUNT(*) AS n FROM audit_logs WHERE event='crm.hook' AND at >= ?", (agora()[:10],))
    return {"hook_url": (f"https://{host}/ops/api/crm/hook?key={chave}" if chave else None),
            "hook_key": bool(chave), "bot_id": os.environ.get("KOMMO_BOT_ID") or None,
            "bot_secret": bool(os.environ.get("KOMMO_BOT_SECRET")), "token": bool(os.environ.get("KOMMO_TOKEN")),
            "ultimo_hook": ultimo["created_at"] if ultimo else None, "hooks_hoje": hoje["n"] if hoje else 0,
            "fila": um(con, "SELECT COUNT(*) AS n FROM crm_messages WHERE status='queued'")["n"],
            "falhas": um(con, "SELECT COUNT(*) AS n FROM crm_messages WHERE status='failed'")["n"]}


@r.get("/diagnostico")
def diagnostico(u=Depends(auth.exige("ADMIN"))):
    """Só ADMIN: o que o Kommo devolve cru em /events (tipos e forma), para acertar a
    leitura do chat sem adivinhar. Não traz texto de mensagem."""
    try:
        return modulo(SISTEMA).eventos_brutos_humano(maximo=20, desde_dias=30)
    except Exception as e:
        raise _erro(e)


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

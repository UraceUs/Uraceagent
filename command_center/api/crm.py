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


def _permanente(e):
    """Erro que insistir não conserta: bot não configurado, Kommo não conectado.

    A fila insiste sozinha com falha passageira (rede, 5xx) — mas insistir com "sem
    KOMMO_BOT_ID" seria enganar quem escreveu: aquilo nunca vai sair. "RECUSADO:" é a
    marca que os MCP usam para dizer "não é problema de tentar de novo"."""
    return isinstance(e, NaoConectado) or "RECUSADO:" in str(e)


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
            "chat_ligado": bool(_chave_hook()) and bool(os.environ.get("KOMMO_BOT_ID")),
            # esta conta devolve as nossas mensagens? só então "sem recibo" quer dizer algo
            "recibo_ativo": confirmacao_confiavel(con)}


@r.get("/leads/{lid}/detail")
def detalhe(lid: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Tudo que o Kommo mostra do lead (17/09): contatos com todos os campos, perfis (Instagram,
    Facebook, WhatsApp…), responsável, funil, tags, datas, estado da conversa e histórico.
    Lê ao vivo e guarda o retrato; sem Kommo, devolve o último retrato guardado."""
    l = _lead(con, lid)
    aviso, ao_vivo, d = None, False, None
    try:
        d = chamar(SISTEMA, "kommo_lead_completo", lead_id=l["external_id"])
        ao_vivo = True
        atualizar(con, "crm_leads", lid, detail=json.dumps(d, ensure_ascii=False), detail_at=agora())
        _absorver_detalhe(con, l, d)
        con.commit()
    except NaoConectado as e:
        aviso = f"Kommo não conectado: {e}."
    except Exception as e:
        aviso = f"Não deu para ler o lead no Kommo agora: {str(e)[:200]}."
    if d is None:
        if l.get("detail"):
            try:
                d = json.loads(l["detail"])
                aviso = (aviso or "") + " Mostrando o último retrato guardado."
            except ValueError:
                d = None
        if d is None:
            raise HTTPException(503, aviso or "Sem retrato do lead.")
    l = _lead(con, lid)
    d["perfis"] = _perfis_do_painel(l) + [p for p in (d.get("perfis") or []) if not any(q["rede"] == p["rede"] for q in _perfis_do_painel(l))]
    return {"detalhe": d, "ao_vivo": ao_vivo, "em": l.get("detail_at"), "aviso": aviso}


REDES = {"instagram": ("Instagram", "https://www.instagram.com/{}/"), "facebook": ("Facebook", "{}"), "tiktok": ("TikTok", "https://www.tiktok.com/@{}"),
         "whatsapp": ("WhatsApp", "https://wa.me/{}"), "site": ("Site", "{}")}


def _perfis_do_painel(l):
    """Perfis que uma pessoa informou no painel (o Kommo não expõe o @ pela API)."""
    try:
        p = json.loads(l.get("profiles") or "{}") or {}
    except ValueError:
        p = {}
    saida = []
    for rede, (nome, molde) in REDES.items():
        v = str(p.get(rede) or "").strip()
        if not v:
            continue
        if v.startswith("http"):
            url, rotulo = v, v.replace("https://", "").replace("http://", "").rstrip("/")
        elif rede == "whatsapp":
            import re as _re
            d = _re.sub(r"\D", "", v); url, rotulo = molde.format(d), v
        elif rede in ("facebook", "site"):
            url, rotulo = "https://" + v.lstrip("@"), v.lstrip("@")
        else:
            h = v.lstrip("@"); url, rotulo = molde.format(h), "@" + h
        saida.append({"rede": nome, "rotulo": rotulo, "url": url, "informado": True})
    return saida


class PerfisIn(BaseModel):
    instagram: str | None = None
    facebook: str | None = None
    tiktok: str | None = None
    whatsapp: str | None = None
    site: str | None = None


@r.post("/leads/{lid}/profiles")
def perfis(lid: int, dados: PerfisIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """Informar o @/link do perfil do lead (uma vez; fica no painel). Vazio apaga."""
    l = _lead(con, lid)
    try:
        atual = json.loads(l.get("profiles") or "{}") or {}
    except ValueError:
        atual = {}
    for k, v in dados.model_dump().items():
        if v is None:
            continue
        v = v.strip()
        if v:
            atual[k] = v[:200]
        else:
            atual.pop(k, None)
    atualizar(con, "crm_leads", lid, profiles=json.dumps(atual, ensure_ascii=False))
    auditar(con, "crm.profiles", f"user:{u['id']}", user_id=u["id"], entity_type="crm_lead", entity_id=lid, detail={"redes": sorted(atual)}, ip=auth._ip(request))
    con.commit()
    return {"ok": True, "profiles": atual, "perfis": _perfis_do_painel({"profiles": json.dumps(atual)})}



def _absorver_detalhe(con, l, d):
    """O que o retrato traz de melhor entra no espelho: contato, origem, responsável, e cada mensagem
    do histórico (só hora e canal) vira marca na conversa, sem repetir."""
    from command_center.providers.sync import recalcular_conversa
    lead = d.get("lead") or {}
    c = (d.get("contatos") or [{}])[0]
    campos = {}
    if c.get("nome") and not l.get("contact_name"):
        campos["contact_name"] = c["nome"]
    if c.get("email") and not l.get("contact_email"):
        campos["contact_email"] = c["email"]
    if c.get("telefone") and not l.get("contact_phone"):
        campos["contact_phone"] = c["telefone"]
    canal = (d.get("conversa") or {}).get("canal")
    if canal and (not l.get("source") or l["source"] != canal):
        campos["source"] = canal
    if lead.get("responsavel"):
        campos["responsible"] = lead["responsavel"]
    if lead.get("tags") is not None:
        campos["tags"] = json.dumps(lead.get("tags") or [], ensure_ascii=False)
    for k in (("funil_id", "pipeline_id"), ("funil", "pipeline_name"), ("etapa_id", "stage_id"), ("etapa", "stage_name"), ("ordem", "stage_order"), ("valor", "price")):
        if lead.get(k[0]) is not None:
            campos[k[1]] = lead[k[0]]
    if campos:
        atualizar(con, "crm_leads", l["id"], **campos)
    novas = 0
    for ev in d.get("eventos") or []:
        if not ev.get("mensagem"):
            continue
        ext = "ev:" + ev["id"]
        if um(con, "SELECT 1 AS x FROM crm_messages WHERE lead_id=? AND external_id=?", (l["id"], ext)):
            continue
        if tem_texto_perto(con, l["id"], ev["direcao"], ev.get("em")):
            continue
        inserir(con, "crm_messages", lead_id=l["id"], external_id=ext, direction=ev["direcao"], author=None, text=None,
                at=ev.get("em") or agora(), source=ev.get("canal") or "kommo-evento")
        novas += 1
    if novas:
        recalcular_conversa(con, l["id"])


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
PRAZO_FILA_S = 900            # 15 min insistindo antes de desistir (era 150 s: uma tentativa e adeus)
ESPERA_TENTATIVA_S = 60       # entre uma cutucada no bot e a seguinte
CONFIRMA_PRAZO_S = 600        # entregue e sem eco do Kommo depois disto: suspeita, não certeza


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
        motivo = (f"o bot não abriu o chat em {PRAZO_FILA_S // 60} min, depois de "
                  f"{m['tentativas'] or 0} tentativa(s) (Salesbot ligado? gatilho na etapa? KOMMO_BOT_ID?)")
        try:
            _aplicando(modulo(SISTEMA).nota_humana, m["lead_ext"],
                       f"[Command Center — NÃO chegou ao cliente, enviar manualmente]\n{m['text']}")
            motivo += " — texto gravado como nota no lead"
        except Exception as e:
            motivo += f" — e a nota também falhou: {str(e)[:120]}"
        atualizar(con, "crm_messages", m["id"], status="failed", error=motivo[:300])
        auditar(con, "crm.reply.failed", "system", entity_type="crm_lead", entity_id=m["lead_id"], detail={"msg": m["id"]})
    return len(velhas)


def empurrar_fila(con):
    """Insiste com o que está na fila. Roda sozinho a cada meio minuto (laço `cc-chat`).

    Antes, o painel tentava UMA vez: se o Salesbot não abrisse o chat naquele instante, a
    mensagem apodrecia na fila até alguém abrir a conversa na tela — e virava nota interna,
    que o cliente nunca vê. Agora cada lead com fila é cutucado de novo a cada minuto, até
    PRAZO_FILA_S. Quem desiste é a varredura, e só depois de insistir.

    Devolve o que aconteceu, para o laço registrar."""
    from datetime import datetime, timedelta, timezone
    agora_dt = datetime.now(timezone.utc)
    corte = (agora_dt - timedelta(seconds=ESPERA_TENTATIVA_S)).strftime("%Y-%m-%dT%H:%M:%S")
    leads = todos(con, """SELECT l.*, MIN(m.at) AS primeira, COUNT(m.id) AS n,
                                 MAX(COALESCE(m.ultima_tentativa,'')) AS ultima
                          FROM crm_messages m JOIN crm_leads l ON l.id = m.lead_id
                          WHERE m.direction='saida' AND m.status='queued'
                          GROUP BY l.id""")
    entregues, cutucados, falhas = 0, 0, []
    for l in leads:
        lead = dict(l)
        if _return_fresco(lead):                       # o bot ainda espera: entrega agora
            minhas = _reivindicar_fila(con, lead["id"])
            if minhas:
                ok, det = _aplicando(_entregar, con, lead, minhas)
                entregues += len(minhas) if ok else 0
                if not ok:
                    falhas.append({"lead": lead["id"], "erro": det[:120]})
                continue
        if lead["ultima"] and lead["ultima"] > corte:   # já cutucado há menos de um minuto
            continue
        con.execute("""UPDATE crm_messages SET tentativas = COALESCE(tentativas,0) + 1, ultima_tentativa = ?
                       WHERE lead_id=? AND direction='saida' AND status='queued'""", (agora(), lead["id"]))
        con.commit()
        try:
            _aplicando(modulo(SISTEMA).abrir_canal_humano, lead["external_id"])
            cutucados += 1
        except Exception as e:                          # noqa: BLE001
            falhas.append({"lead": lead["id"], "erro": str(e)[:120]})
    return {"entregues": entregues, "cutucados": cutucados, "falhas": falhas}


def confirmar_entrega(con, lead_id, texto, em):
    """O Kommo devolveu uma mensagem NOSSA: é o recibo. Carimba a resposta do painel que
    tem o mesmo texto por perto e ainda estava sem confirmação.

    Este é o único sinal de que a mensagem apareceu de verdade no chat do cliente — a
    continuação do Salesbot responder "202" só diz que o Kommo aceitou o pedido."""
    alvo = um(con, """SELECT id FROM crm_messages WHERE lead_id=? AND direction='saida' AND confirmado_em IS NULL
                      AND text=? AND ABS(strftime('%s', at) - strftime('%s', ?)) <= 900
                      ORDER BY at DESC LIMIT 1""", (lead_id, (texto or "")[:8000], em))
    if not alvo:
        return False
    atualizar(con, "crm_messages", alvo["id"], confirmado_em=em, status="sent", error=None)
    return True


def confirmacao_confiavel(con, dias=7):
    """A conta devolve as nossas mensagens? Se nunca devolveu, falta de recibo não quer
    dizer nada — e o painel não vai acusar o que não consegue ver (lição de 21/09)."""
    r = um(con, """SELECT COUNT(*) AS n FROM crm_messages WHERE confirmado_em IS NOT NULL
                   AND confirmado_em >= strftime('%Y-%m-%dT%H:%M:%S', 'now', ?)""", (f"-{int(dias)} days",))
    return bool(r and r["n"])


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
        except Exception as e:                            # noqa: BLE001
            # Falhar aqui NÃO é desistir: a mensagem fica na fila e o laço `cc-chat` insiste
            # sozinho a cada meio minuto. Marcar como falha na primeira tentativa foi o que
            # fez resposta boa morrer por uma piscada de rede (21/09). Só o erro permanente
            # (bot desligado) volta na cara de quem escreveu — porque aí insistir é mentira.
            if _permanente(e):
                atualizar(con, "crm_messages", mid, status="failed", error=str(e)[:300])
                con.commit()
                raise _erro(e)
            atualizar(con, "crm_messages", mid, error=str(e)[:300], tentativas=1, ultima_tentativa=agora())
            det = str(e)[:200]
    con.commit()
    return {"ok": True, "msg_id": mid, "como": como, "detalhe": det,
            "aviso": ("Enviada no chat do lead." if como == "entregue" else
                      f"Na fila: o painel insiste com o bot do Kommo a cada meio minuto. Se em "
                      f"{PRAZO_FILA_S // 60} min não sair, vira nota no lead e acende o aviso aqui.")}


class ReenviarIn(BaseModel):
    texto: str | None = None


@r.post("/leads/{lid}/messages/{mid}/resend")
def reenviar(lid: int, mid: int, dados: ReenviarIn, request: Request, u=Depends(auth.exige("OPERATOR")),
             con: sqlite3.Connection = Depends(get_db)):
    """Tentar de novo uma resposta que não chegou ao cliente.

    Existe porque em 21/09 o dono respondeu pelo painel e **algumas mensagens não saíram**:
    o estado ficava certo na tela ("não entregue"), mas não havia como reenviar sem copiar
    o texto na mão. A mensagem antiga é marcada como substituída — o histórico não some."""
    l = _lead(con, lid)
    m = um(con, "SELECT * FROM crm_messages WHERE id=? AND lead_id=?", (mid, lid))
    if not m:
        raise HTTPException(404, "mensagem não encontrada nesta conversa")
    if m["direction"] != "saida":
        raise HTTPException(400, "só dá para reenviar resposta sua")
    if m["status"] == "sent":
        raise HTTPException(409, "essa já foi entregue")
    texto = (dados.texto or m["text"] or "").strip()
    if not texto:
        raise HTTPException(400, "sem texto para reenviar")
    atualizar(con, "crm_messages", mid, status="failed",
              error=f"substituída pelo reenvio de {u['name']} em {agora()[:16].replace('T', ' ')}")
    novo = inserir(con, "crm_messages", lead_id=lid, external_id=None, direction="saida", status="queued",
                   author=u["name"], text=texto[:8000], at=agora(), source="painel")
    auditar(con, "crm.reply.resend", f"user:{u['id']}", user_id=u["id"], entity_type="crm_lead", entity_id=lid,
            detail={"de": mid, "para": novo}, ip=auth._ip(request))
    con.commit()
    como, det = "fila", None
    if _return_fresco(l):
        minhas = _reivindicar_fila(con, lid)
        if minhas:
            ok, det = _aplicando(_entregar, con, l, minhas)
            como = "entregue" if ok else "fila"
    if como == "fila":
        try:
            _aplicando(modulo(SISTEMA).abrir_canal_humano, l["external_id"])
            como = "bot disparado"
        except Exception as e:                            # noqa: BLE001
            if _permanente(e):
                atualizar(con, "crm_messages", novo, status="failed", error=str(e)[:300])
                con.commit()
                raise _erro(e)
            atualizar(con, "crm_messages", novo, error=str(e)[:300], tentativas=1, ultima_tentativa=agora())
            det = str(e)[:200]                            # fica na fila; o laço `cc-chat` insiste
    con.commit()
    return {"ok": True, "msg_id": novo, "como": como, "detalhe": det}


@r.get("/leads/{lid}/avatar")
def avatar(lid: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Foto do perfil que o Kommo manda no webhook. A URL (amojo.kommo.com) não é pública: o servidor
    busca com o token da conta e guarda em cache (~/.urace/avatars). Sem foto → 404 (o painel mostra iniciais)."""
    import hashlib
    import urllib.request
    from fastapi.responses import Response
    from command_center.api.sistema import _dir
    l = _lead(con, lid)
    url = l.get("contact_avatar")
    if not url or not str(url).startswith("https://"):
        raise HTTPException(404, "sem foto")
    pasta = _dir() / "avatars"
    pasta.mkdir(parents=True, exist_ok=True)
    chave = hashlib.sha1(url.encode()).hexdigest()[:20]
    for ext, mt in (("jpg", "image/jpeg"), ("png", "image/png"), ("webp", "image/webp")):
        f = pasta / f"{lid}-{chave}.{ext}"
        if f.exists():
            return Response(f.read_bytes(), media_type=mt, headers={"Cache-Control": "private, max-age=86400"})
    token = os.environ.get("KOMMO_TOKEN") or ""
    if not token:
        try:
            modulo(SISTEMA); token = os.environ.get("KOMMO_TOKEN") or ""
        except Exception:
            token = ""
    dados, mt = None, None
    for headers in ({"Authorization": f"Bearer {token}", "User-Agent": "urace-command-center"}, {"User-Agent": "urace-command-center"}):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                ct = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                corpo = resp.read(3_000_000)
                if ct.startswith("image/") and corpo:
                    dados, mt = corpo, ct
                    break
        except Exception:
            continue
    if not dados:
        raise HTTPException(404, "foto indisponível")
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(mt, "jpg")
    (pasta / f"{lid}-{chave}.{ext}").write_bytes(dados)
    return Response(dados, media_type=mt, headers={"Cache-Control": "private, max-age=86400"})


class EstrelaIn(BaseModel):
    starred: bool = True


@r.post("/leads/{lid}/star")
def estrela_lead(lid: int, dados: EstrelaIn, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Favoritar a conversa (estrela na lista). Marca do painel; não vai para o Kommo."""
    _lead(con, lid)
    atualizar(con, "crm_leads", lid, starred=1 if dados.starred else 0)
    con.commit()
    return {"ok": True, "starred": bool(dados.starred)}


@r.post("/messages/{mid}/star")
def estrela_mensagem(mid: int, dados: EstrelaIn, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Favoritar uma mensagem dentro da conversa."""
    if not um(con, "SELECT 1 AS x FROM crm_messages WHERE id=?", (mid,)):
        raise HTTPException(404, "Message not found.")
    atualizar(con, "crm_messages", mid, starred=1 if dados.starred else 0)
    con.commit()
    return {"ok": True, "starred": bool(dados.starred)}


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
        if not um(con, "SELECT 1 AS x FROM crm_messages WHERE lead_id=? AND external_id=?", (lid, ext)) \
                and not _entrada_gemea(con, lid, e["texto"], agora()):
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
    """As conversas, como uma caixa de entrada: a mensagem mais recente sempre no topo
    (pedido do dono, 17/09); quem espera resposta é marcado, não reordenado."""
    varrer_fila(con); con.commit()
    leads = todos(con, """SELECT c.*, cl.name AS client_name, cl.pilot_name AS client_pilot,
                                 (SELECT text FROM crm_messages m WHERE m.lead_id=c.id AND m.direction IN ('entrada','saida')
                                  AND m.text IS NOT NULL ORDER BY m.at DESC, m.id DESC LIMIT 1) AS snippet,
                                 (SELECT COUNT(*) FROM crm_messages m WHERE m.lead_id=c.id AND m.direction IN ('entrada','saida')) AS msgs,
                                 (SELECT COUNT(*) FROM crm_messages m WHERE m.lead_id=c.id AND m.status='failed') AS falhas
                          FROM crm_leads c LEFT JOIN clients cl ON cl.id=c.client_id
                          WHERE c.last_message_at IS NOT NULL OR c.last_hook_at IS NOT NULL
                             OR EXISTS (SELECT 1 FROM crm_messages m WHERE m.lead_id=c.id AND m.direction IN ('entrada','saida'))
                          ORDER BY COALESCE((SELECT MAX(m.at) FROM crm_messages m WHERE m.lead_id=c.id AND m.direction IN ('entrada','saida')),
                                            c.last_message_at, c.updated_at_src, c.synced_at) DESC
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
    ultimo_wh = um(con, "SELECT at AS created_at FROM audit_logs WHERE event='crm.webhook' ORDER BY id DESC LIMIT 1")
    return {"hook_url": (f"https://{host}/ops/api/crm/hook?key={chave}" if chave else None),
            "webhook_url": (f"https://{host}/ops/api/crm/webhook?key={chave}" if chave else None),
            "ultimo_webhook": ultimo_wh["created_at"] if ultimo_wh else None,
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
def _lista_php(v):
    """`message[add][0][...]` vem como dict com chaves '0','1'… (form PHP) ou como lista (JSON)."""
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]
    if isinstance(v, dict):
        return [x for _, x in sorted(v.items(), key=lambda kv: str(kv[0])) if isinstance(x, dict)]
    return []


def _mensagens_do_webhook_kommo(corpo):
    """Webhook de conta do Kommo ("Incoming message received"): message[add][i] com id, chat_id, talk_id,
    contact_id, text, created_at, element_type (2 = lead), entity_type, entity_id, type (incoming/outgoing),
    author{name}, origin. Devolve uma lista normalizada; vazia se não for esse formato."""
    saida = []
    m = corpo.get("message") if isinstance(corpo, dict) else None
    if not isinstance(m, dict):
        return saida
    for chave in ("add", "update"):
        for it in _lista_php(m.get(chave)):
            texto = it.get("text")
            if texto is None and isinstance(it.get("message"), dict):
                it = it["message"]; texto = it.get("text")
            tipo = str(it.get("type") or "incoming").lower()
            et = str(it.get("entity_type") or "").lower()
            el = str(it.get("element_type") or "")
            lead = None
            if et in ("lead", "leads") or el == "2":
                lead = it.get("entity_id") or it.get("element_id")
            autor = it.get("author") if isinstance(it.get("author"), dict) else {}
            saida.append({"id": str(it.get("id") or ""), "lead_id": str(lead) if lead else None,
                          "contato_id": str(it.get("contact_id") or "") or None, "talk_id": str(it.get("talk_id") or "") or None,
                          "texto": (str(texto).strip() if texto is not None else ""), "direcao": "saida" if tipo.startswith("out") else "entrada",
                          "autor": autor.get("name"), "avatar": autor.get("avatar_url") if str(autor.get("type") or "") != "internal" else None,
                          "origem": it.get("origin"), "criado_em": it.get("created_at"),
                          "anexo": it.get("attachment") or it.get("media") or None})
    return saida


def _quando_kommo(v):
    try:
        from adminai.mcp.kommo_mcp import _quando
        return _quando(int(v)) if v not in (None, "") else None
    except Exception:
        return None


def tem_texto_perto(con, lead_id, direcao, em, janela=180):
    """Já há mensagem COM texto desta direção a ≤ janela s? Então a marca (evento sem texto) é a mesma mensagem."""
    if not em:
        return False
    r = um(con, """SELECT 1 AS x FROM crm_messages WHERE lead_id=? AND direction=? AND text IS NOT NULL
                   AND ABS(strftime('%s', at) - strftime('%s', ?)) <= ? LIMIT 1""", (lead_id, direcao, em, janela))
    return bool(r)


JANELA_GEMEA_S = 300          # a mesma mensagem pelos dois caminhos chega em segundos


def _entrada_gemea(con, lead_id, texto, em, janela=JANELA_GEMEA_S):
    """A mensagem do lead chega DUAS vezes: pelo webhook da conta (com o id do Kommo, o canal e
    o autor) e pelo hook do bot (só o texto). Em 21/09 o dono viu a conversa duplicada e achou
    que estava faltando mensagem. Vale a do webhook; a do hook só entra se a outra não veio.

    O casamento é por texto e tempo porque os dois caminhos dão ids diferentes para a mesma
    mensagem. A janela é curta (5 min) de propósito: cliente que repete a mesma frase depois
    disso continua aparecendo duas vezes, como deve."""
    return bool(um(con, """SELECT 1 AS x FROM crm_messages WHERE lead_id=? AND direction='entrada' AND text=?
                           AND ABS(strftime('%s', at) - strftime('%s', ?)) <= ? LIMIT 1""",
                   (lead_id, (texto or "")[:8000], em, janela)))


@r.post("/webhook")
async def webhook(request: Request, background: BackgroundTasks, con: sqlite3.Connection = Depends(get_db)):
    """Mensagem que chega no Kommo entra aqui na hora, com TEXTO.

    Dois formatos: (a) o webhook de conta do Kommo ("Incoming message received", Settings →
    Integrations → Webhooks), form-encoded, message[add][0][text]…; (b) o simples
    {lead_id, text, message_id, author} de um bot/webhook próprio.
    Sem cookie de sessão: quem prova a origem é o segredo na URL (?key= igual ao do hook,
    ou ?secret= / X-Urace-Secret = KOMMO_WEBHOOK_SECRET), comparado em tempo constante."""
    segredo = os.environ.get("KOMMO_WEBHOOK_SECRET", "")
    chave = _chave_hook()
    enviado = request.headers.get("x-urace-secret") or request.query_params.get("secret") or request.query_params.get("key") or ""
    ok = (segredo and hmac.compare_digest(segredo, enviado)) or (chave and hmac.compare_digest(chave, enviado))
    if not ok:
        raise HTTPException(403, "Forbidden.")
    bruto = await request.body()
    try:
        corpo = json.loads(bruto) if bruto else {}
        if not isinstance(corpo, dict):
            corpo = {}
    except ValueError:
        from adminai.mcp.kommo_mcp import parse_corpo_hook
        corpo = parse_corpo_hook(bruto)
    conta = (corpo.get("account") or {}) if isinstance(corpo.get("account"), dict) else {}
    dominio = os.environ.get("KOMMO_DOMAIN", "").replace("https://", "").strip("/").lower()
    if conta.get("subdomain") and dominio and not dominio.startswith(str(conta["subdomain"]).lower()):
        raise HTTPException(403, "Conta do Kommo diferente.")

    if isinstance(corpo.get("message"), dict):               # amostra crua da última mensagem, para diagnóstico (17/09)
        try:
            from command_center.api.sistema import _dir
            (_dir() / "kommo-webhook-ultimo.json").write_text(json.dumps({k: v for k, v in corpo.items() if k != "account"}, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass
    msgs = _mensagens_do_webhook_kommo(corpo)
    if not msgs:                                              # formato simples
        ext = str(corpo.get("lead_id") or corpo.get("entity_id") or "").strip()
        if not ext:
            # Webhook marcado como "All": leads/contacts/notes/talks… Nunca devolve erro (o Kommo
            # desliga o webhook depois de falhas seguidas). Lead que mudou é relido em segundo plano.
            tocados = []
            for chave in ("add", "update", "status", "responsible", "restore"):
                for it in _lista_php((corpo.get("leads") or {}).get(chave) if isinstance(corpo.get("leads"), dict) else None):
                    if it.get("id"):
                        tocados.append(str(it["id"]))
            for ext2 in tocados[:20]:
                l2 = um(con, "SELECT id FROM crm_leads WHERE external_id=?", (ext2,))
                if l2:
                    background.add_task(_enriquecer_lead, l2["id"], ext2)
            return {"ok": True, "ignorado": [k for k in corpo.keys() if k != "account"], "leads_relidos": len(tocados)}
        msgs = [{"id": str(corpo.get("message_id") or ""), "lead_id": ext, "contato_id": None, "talk_id": None,
                 "texto": str(corpo.get("text") or corpo.get("message") or "").strip(), "direcao": "entrada",
                 "autor": corpo.get("author") or corpo.get("name"), "origem": corpo.get("source"), "criado_em": None, "anexo": None,
                 "_nome": corpo.get("name"), "_simples": True}]
    from adminai.mcp.kommo_mcp import canal_da_origem
    guardadas, confirmadas, leads = 0, 0, set()
    for m in msgs:
        ext = m["lead_id"]
        if not ext and m["contato_id"]:                       # mensagem só com contato: acha o lead
            try:
                ext = modulo(SISTEMA)._lead_do_contato(m["contato_id"])
            except Exception:
                ext = None
        if not ext:
            continue
        canal = canal_da_origem(m["origem"]) or (m["origem"] if m["origem"] and len(str(m["origem"])) < 40 else None)
        l = um(con, "SELECT * FROM crm_leads WHERE external_id=?", (ext,))
        novo = False
        if not l:
            lid = inserir(con, "crm_leads", external_id=ext, name=m.get("_nome") or m["autor"] or f"Lead {ext}", contact_name=m["autor"],
                          contact_avatar=m.get("avatar"), source=canal, link=f"https://{dominio or 'urace.kommo.com'}/leads/detail/{ext}", synced_at=agora())
            novo = True
        else:
            lid = l["id"]
            campos = {}
            if canal and not l["source"]:
                campos["source"] = canal
            if m["autor"] and not l["contact_name"] and m["direcao"] == "entrada":
                campos["contact_name"] = m["autor"]
            if m.get("avatar") and m["direcao"] == "entrada" and m["avatar"] != l.get("contact_avatar"):
                campos["contact_avatar"] = m["avatar"]
            if campos:
                atualizar(con, "crm_leads", lid, **campos)
        leads.add(lid)
        texto = m["texto"] or ("" if not m["anexo"] else "[anexo]")
        if not texto:
            continue
        em = _quando_kommo(m["criado_em"]) or agora()
        ext_msg = (m["id"] if m.get("_simples") and m["id"] else None) or (f"msg:{m['id']}" if m["id"] else f"msg:{lid}:{em}")
        if um(con, "SELECT 1 AS x FROM crm_messages WHERE lead_id=? AND external_id=?", (lid, ext_msg)):
            continue
        # Resposta nossa que o Kommo devolve como "outgoing". Não é lixo: é o RECIBO da mensagem
        # que o painel mandou. Carimba a original em vez de largar a informação no chão (21/09).
        if m["direcao"] == "saida" and um(con, """SELECT 1 AS x FROM crm_messages WHERE lead_id=? AND direction='saida' AND text=?
                                                  AND ABS(strftime('%s', at) - strftime('%s', ?)) <= 900 LIMIT 1""", (lid, texto[:8000], em)):
            if confirmar_entrega(con, lid, texto, em):
                confirmadas += 1
            continue
        # o hook do bot pode já ter posto a MESMA mensagem (só texto): vale esta, com id e canal
        if m["direcao"] == "entrada":
            con.execute("""DELETE FROM crm_messages WHERE lead_id=? AND direction='entrada' AND external_id LIKE 'hook:%'
                           AND text=? AND ABS(strftime('%s', at) - strftime('%s', ?)) <= ?""",
                        (lid, texto[:8000], em, JANELA_GEMEA_S))
        # a sincronia pode já ter posto a marca (evento sem texto) desta mesma mensagem: some com a marca
        con.execute("""DELETE FROM crm_messages WHERE lead_id=? AND direction=? AND text IS NULL AND external_id LIKE 'ev:%'
                       AND ABS(strftime('%s', at) - strftime('%s', ?)) <= 180""", (lid, m["direcao"], em))
        inserir(con, "crm_messages", lead_id=lid, external_id=ext_msg, direction=m["direcao"],
                author=(m["autor"] or ("cliente" if m["direcao"] == "entrada" else "nós")), text=texto[:8000], at=em,
                source=canal or "webhook", status=("sent" if m["direcao"] == "saida" else None))
        guardadas += 1
        if m["direcao"] == "entrada":
            atualizar(con, "crm_leads", lid, last_message_at=em, needs_reply=1)
        else:
            from command_center.providers.sync import recalcular_conversa
            recalcular_conversa(con, lid)
        if novo:
            background.add_task(_enriquecer_lead, lid, ext)
    for lid in leads:
        auditar(con, "crm.webhook", "kommo", entity_type="crm_lead", entity_id=lid,
                detail={"mensagens": guardadas, "confirmadas": confirmadas,
                        "formato": "kommo" if corpo.get("message") else "simples"})
    con.commit()
    return {"ok": True, "leads": sorted(leads), "mensagens": guardadas, "confirmadas": confirmadas}

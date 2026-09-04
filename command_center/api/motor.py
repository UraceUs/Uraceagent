"""Motor de eventos e aprendizado.

- Cada mudança detectada pela sincronia vira um ai_event (tarefa criada,
  e-mail de cliente recebido, waiver devolvida/assinada).
- Uma regra ligada em automation_rules transforma o evento num comando
  para o agente, com o contexto do item e o que o dono já ensinou
  (ai_learnings). O agente responde e PROPÕE ações; política decide se
  executa, pede confirmação ou espera aprovação humana.
- O balão "Instruir a IA" em cada item de atenção vira comando + memória.
- Ação aprovada executa aqui, pelo módulo do MCP, com APLICAR liberado só
  nesta chamada: aprovação humana é a autorização.
"""
import json
import os
import threading

from command_center.api import ia
from command_center.db import agora, atualizar, auditar, conectar, inserir, todos, um

MAX_APRENDIZADOS = 25


# ------------------------------------------------------------ memória
def aprendizados(con, client_id=None, entity_type=None):
    escopos = ["global"]
    if client_id:
        escopos.append(f"client:{client_id}")
    if entity_type:
        escopos.append(f"entity:{entity_type}")
    marks = ",".join("?" * len(escopos))
    rows = todos(con, f"SELECT scope, text FROM ai_learnings WHERE active=1 AND scope IN ({marks}) ORDER BY id DESC LIMIT ?",
                 (*escopos, MAX_APRENDIZADOS))
    if not rows:
        return ""
    linhas = [f"- ({r['scope']}) {r['text']}" for r in reversed(rows)]
    return "\n\nO QUE O DONO JÁ ENSINOU (obedeça; em conflito com o cérebro, isto prevalece):\n" + "\n".join(linhas)


def aprender(con, texto, user_id, client_id=None, entity_type=None, source_key=None):
    escopo = f"client:{client_id}" if client_id else (f"entity:{entity_type}" if entity_type else "global")
    lid = inserir(con, "ai_learnings", scope=escopo, text=texto.strip()[:1000], source_key=source_key, created_by=user_id)
    auditar(con, "ai.learn", f"user:{user_id}", user_id=user_id, entity_type="ai_learning", entity_id=lid,
            detail={"scope": escopo, "text": texto[:200]})
    return lid


# ------------------------------------------------------------ contexto
def _contexto_cliente(con, client_id):
    if not client_id:
        return ""
    c = um(con, "SELECT * FROM clients WHERE id=?", (client_id,))
    if not c:
        return ""
    ws = todos(con, "SELECT status, template, signer_email, completed_at, expires_at FROM waivers WHERE client_id=? AND hidden=0 ORDER BY sent_at DESC LIMIT 3", (client_id,))
    ts = todos(con, "SELECT title, section, due_on, status FROM tasks WHERE client_id=? ORDER BY due_on DESC LIMIT 5", (client_id,))
    return ("\nCLIENTE: " + json.dumps({k: c[k] for k in ("id", "name", "pilot_name", "pilot_dob", "email", "phone", "vip", "status") if k in c.keys()}, ensure_ascii=False)
            + "\nWAIVERS NO ESPELHO: " + json.dumps(ws, ensure_ascii=False)
            + "\nSERVIÇOS NO ESPELHO: " + json.dumps(ts, ensure_ascii=False))


def _prompt_evento(con, ev):
    regra = {"task.created": "Um serviço NOVO entrou no quadro. Verifique a waiver do piloto (docusign_waivers_de pelo e-mail do responsável; menor = parental) e, se faltar, PROPONHA o envio. "
                             "Verifique o que falta para a invoice (produto/valor): se souber pelo Rate Card e pela tarefa, proponha a invoice com o valor; se não souber, diga exatamente o que falta. "
                             "Comente na tarefa do Asana o que preparou.",
             "email.received": "Chegou e-mail de um cliente conhecido. Leia a thread (gmail_thread), diga o que ele quer, classifique com o marcador certo e, se precisar de resposta, PROPONHA um rascunho (gmail_rascunho). Nunca envie.",
             "waiver.bounced": "A waiver deste cliente voltou (e-mail devolvido). Procure o e-mail correto na tarefa do Asana e nas caixas do Gmail; PROPONHA a correção e o reenvio, ou diga que não achou.",
             "waiver.completed": "A waiver deste cliente foi assinada. Comente na tarefa do Asana correspondente que a waiver chegou (asana_comentar).",
             }.get(ev["kind"], "Avalie o evento e proponha o que fazer.")
    return (f"EVENTO AUTOMÁTICO: {ev['kind']} — {ev['summary']}\n{regra}"
            + _contexto_cliente(con, ev["client_id"]) + aprendizados(con, ev["client_id"], ev["entity_type"]))


# ------------------------------------------------------------ eventos
def regra_ligada(con, kind):
    r = um(con, "SELECT enabled FROM automation_rules WHERE json_extract(trigger, '$.event') = ?", (kind,))
    return bool(r and r["enabled"])


def registrar_evento(con, kind, entity_type, entity_id, client_id, summary):
    """Idempotente por (kind, tipo, id)."""
    con.execute("""INSERT OR IGNORE INTO ai_events (kind, entity_type, entity_id, client_id, summary)
                   VALUES (?,?,?,?,?)""", (kind, entity_type, entity_id, client_id, summary[:300]))


def processar_eventos(con, user_id, limite=10):
    """Transforma eventos NEW em comandos para o agente (um por evento), respeitando as regras."""
    disparados = 0
    for ev in todos(con, "SELECT * FROM ai_events WHERE status='NEW' ORDER BY id LIMIT ?", (limite,)):
        if not regra_ligada(con, ev["kind"]):
            atualizar(con, "ai_events", ev["id"], status="SKIPPED", handled_at=agora(), note="regra desligada")
            continue
        texto = _prompt_evento(con, ev)
        session_key = f"agent:{ia.AGENTE}:evento-{ev['kind']}-{ev['id']}"
        cid = inserir(con, "ai_commands", user_id=user_id, text=texto, session_key=session_key)
        wid = inserir(con, "ai_workflows", command_id=cid, client_id=ev["client_id"], kind=ev["kind"], summary=ev["summary"])
        atualizar(con, "ai_events", ev["id"], status="RUNNING", command_id=cid, handled_at=agora())
        auditar(con, "ai.event", "system", user_id=user_id, entity_type="ai_event", entity_id=ev["id"],
                detail={"kind": ev["kind"], "command_id": cid, "workflow_id": wid})
        threading.Thread(target=_executa_evento, args=(ev["id"], cid, wid, texto, session_key, user_id), daemon=True).start()
        disparados += 1
    return disparados


def _executa_evento(event_id, command_id, workflow_id, texto, session_key, user_id):
    ia._executa(command_id, texto, session_key, user_id)
    con = conectar()
    try:
        c = um(con, "SELECT status FROM ai_commands WHERE id=?", (command_id,))
        ok = c and c["status"] == "DONE"
        atualizar(con, "ai_events", event_id, status="DONE" if ok else "FAILED", handled_at=agora())
        atualizar(con, "ai_workflows", workflow_id, status="DONE" if ok else "FAILED", finished_at=agora())
        con.execute("UPDATE ai_actions SET workflow_id=? WHERE command_id=?", (workflow_id, command_id))
    finally:
        con.close()


# ------------------------------------------------------------ instrução pelo balão
def instruir(con, user_id, key, texto, item, lembrar):
    """Comando com o contexto do item de atenção; opcionalmente vira memória."""
    client_id = item.get("client_id")
    entity = item.get("entity") or {}
    if lembrar:
        aprender(con, texto, user_id, client_id=client_id, entity_type=entity.get("type"), source_key=key)
    prompt = (f"INSTRUÇÃO DO DONO sobre o item de atenção \"{item.get('title')}\" ({item.get('why', '')}):\n{texto.strip()}\n"
              "Cumpra a instrução: consulte o que precisar e PROPONHA as ações (waiver, invoice, comentário, rascunho) com os dados exatos."
              + _contexto_cliente(con, client_id) + aprendizados(con, client_id, entity.get("type")))
    session_key = f"agent:{ia.AGENTE}:atencao-{user_id}-{agora()[:10]}"
    cid = inserir(con, "ai_commands", user_id=user_id, text=prompt, session_key=session_key)
    if client_id:
        wid = inserir(con, "ai_workflows", command_id=cid, client_id=client_id, kind="instrucao", summary=item.get("title"))
    else:
        wid = None
    auditar(con, "ai.instruct", f"user:{user_id}", user_id=user_id, entity_type="attention", entity_id=key,
            detail={"text": texto[:300], "remember": bool(lembrar), "command_id": cid})
    threading.Thread(target=_executa_instrucao, args=(cid, wid, prompt, session_key, user_id), daemon=True).start()
    return cid


def _executa_instrucao(command_id, workflow_id, texto, session_key, user_id):
    ia._executa(command_id, texto, session_key, user_id)
    if workflow_id:
        con = conectar()
        try:
            c = um(con, "SELECT status FROM ai_commands WHERE id=?", (command_id,))
            atualizar(con, "ai_workflows", workflow_id, status="DONE" if c and c["status"] == "DONE" else "FAILED", finished_at=agora())
            con.execute("UPDATE ai_actions SET workflow_id=? WHERE command_id=?", (workflow_id, command_id))
        finally:
            con.close()


# ------------------------------------------------------------ execução de ação aprovada
def executar_acao(aid, user_id):
    """Roda uma ação APPROVED pelo módulo do MCP (sem passar pelo agente).
    Precisa de args estruturados no payload; sem eles, devolve o que falta."""
    from command_center.providers import NaoConectado, chamar
    con = conectar()
    try:
        a = um(con, "SELECT * FROM ai_actions WHERE id=?", (aid,))
        if not a or a["status"] != "APPROVED":
            return
        payload = json.loads(a["payload"] or "{}")
        args = payload.get("args")
        atualizar(con, "ai_actions", aid, status="RUNNING")
        if not isinstance(args, dict) or not args:
            atualizar(con, "ai_actions", aid, status="FAILED", finished_at=agora(),
                      result="Sem argumentos estruturados: a IA descreveu a ação mas não deu os campos exatos. Peça no AI Command: 'refaça a ACAO com os argumentos em JSON'.")
            return
        sistema = a["system"] or a["action"].split("_")[0]
        if sistema in ("qbo", "quickbooks"):
            atualizar(con, "ai_actions", aid, status="FAILED", finished_at=agora(), result="QuickBooks em stand-by (P-11): nada foi enviado.")
            return
        if sistema == "google":
            sistema = "gmail"
        anterior = os.environ.get("APLICAR")
        os.environ["APLICAR"] = "1"                 # aprovação humana = autorização, só nesta chamada
        try:
            res = chamar(sistema, a["action"], **args)
        finally:
            if anterior is None:
                os.environ.pop("APLICAR", None)
            else:
                os.environ["APLICAR"] = anterior
        atualizar(con, "ai_actions", aid, status="DONE", finished_at=agora(), result=json.dumps(res, ensure_ascii=False)[:2000])
        auditar(con, "action.executed", f"user:{user_id}", user_id=user_id, entity_type="ai_action", entity_id=aid,
                detail={"action": a["action"], "args": {k: (str(v)[:80]) for k, v in args.items()}})
    except NaoConectado as e:
        atualizar(con, "ai_actions", aid, status="FAILED", finished_at=agora(), result=f"não conectado: {e}")
    except Exception as e:
        atualizar(con, "ai_actions", aid, status="FAILED", finished_at=agora(), result=f"{type(e).__name__}: {str(e)[:500]}")
        auditar(con, "action.failed", f"user:{user_id}", user_id=user_id, entity_type="ai_action", entity_id=aid, detail={"erro": str(e)[:300]})
    finally:
        con.close()

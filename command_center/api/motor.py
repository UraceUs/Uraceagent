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
import re
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
    saida = ""
    if rows:
        linhas = [f"- ({r['scope']}) {r['text']}" for r in reversed(rows)]
        saida += "\n\nO QUE O DONO JÁ ENSINOU (obedeça; em conflito com o cérebro, isto prevalece):\n" + "\n".join(linhas)
    return saida + fontes_de_contexto(con)


def fontes_de_contexto(con):
    """Planilhas e arquivos cadastrados em Integrações: a IA sabe que existem e como ler cada um."""
    fontes = todos(con, "SELECT * FROM context_sources WHERE active=1 ORDER BY kind, id")
    if not fontes:
        return ""
    linhas = []
    for f in fontes:
        if f["kind"] == "sheet":
            linhas.append(f"- PLANILHA '{f['title']}': {f['description'] or ''} → sheets_ler(conta='urace', planilha_id='{f['sheet_id']}', intervalo='{f['sheet_range'] or 'A1:Z200'}')")
        elif f["kind"] == "file":
            nome = os.path.basename(f["text_path"] or f["path"] or "")
            linhas.append(f"- ARQUIVO '{f['title']}': {f['description'] or ''} → read /workspace/contexto/{nome}")
        else:
            linhas.append(f"- LINK '{f['title']}': {f['description'] or ''} → {f['url']}")
    return "\n\nFONTES DE CONTEXTO cadastradas pelo dono (consulte quando o assunto pedir):\n" + "\n".join(linhas)


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


def cliente_citado(con, texto):
    """Cliente cujo nome (piloto ou responsável, 2+ palavras) aparece no texto do dono."""
    from command_center.providers.identidade import normaliza
    t = " " + " ".join(normaliza(texto or "")) + " "
    melhor, tam = None, 0
    for c in todos(con, "SELECT id, name, pilot_name FROM clients"):
        for n in (c["pilot_name"], c["name"]):
            toks = normaliza(n or "")
            if len(toks) >= 2 and (" " + " ".join(toks) + " ") in t and len(toks) > tam:
                melhor, tam = c["id"], len(toks)
    return melhor


def contexto_do_comando(con, texto, user_id=None):
    """Tudo que o painel já sabe sobre o piloto citado: histórico, última invoice (com o id do
    cliente no QBO), waiver e o catálogo de itens. Entra no comando para a IA agir de uma vez.
    Sem nome na mensagem ("pode continuar com a invoice"), vale o último piloto da conversa do dia."""
    cid = cliente_citado(con, texto)
    if not cid and user_id:
        for c in todos(con, "SELECT text FROM ai_commands WHERE user_id=? AND created_at >= date('now') AND text NOT LIKE 'EVENTO AUTOMÁTICO%' ORDER BY id DESC LIMIT 8", (user_id,)):
            cid = cliente_citado(con, c["text"])
            if cid:
                break
    if not cid:
        return ""
    c = um(con, "SELECT * FROM clients WHERE id=?", (cid,))
    ts = todos(con, "SELECT title, section, due_on, status FROM tasks WHERE client_id=? ORDER BY due_on DESC LIMIT 5", (cid,))
    inv = um(con, "SELECT doc_number, amount, memo, issued_on, customer_ref, customer_email FROM invoices WHERE client_id=? ORDER BY issued_on DESC LIMIT 1", (cid,))
    ws = todos(con, "SELECT status, template, signer_name, signer_email, completed_at, expires_at FROM waivers WHERE client_id=? AND hidden=0 ORDER BY sent_at DESC LIMIT 3", (cid,))
    from datetime import date, timedelta
    corte = (date.today() - timedelta(days=365)).isoformat()
    assinada = next((w for w in ws if w["status"] == "completed" and (w["completed_at"] or "")[:10] >= corte), None)
    idade = None
    if c.get("pilot_dob"):
        try:
            d = date.fromisoformat(c["pilot_dob"][:10]); h = date.today()
            idade = h.year - d.year - ((h.month, h.day) < (d.month, d.day))
        except ValueError:
            pass
    itens = todos(con, "SELECT id, name, price FROM qbo_items WHERE active=1 ORDER BY name LIMIT 60")
    linhas = ["\n\nCONTEXTO DO PAINEL sobre " + (c["pilot_name"] or c["name"]) + " (use estes dados; não pergunte o que já está aqui):",
              "- Piloto: " + json.dumps({"nome": c["pilot_name"] or c["name"], "nascimento": c.get("pilot_dob"), "idade": idade,
                                         "menor": (idade is not None and idade < 18), "tipo": c.get("plan_type"), "vip": bool(c.get("vip"))}, ensure_ascii=False),
              "- Responsável (quem paga e assina): " + json.dumps({"nome": c["name"], "email": c.get("email"), "email_alt": c.get("email_alt"), "telefone": c.get("phone")}, ensure_ascii=False),
              "- Últimos serviços: " + json.dumps(ts, ensure_ascii=False),
              "- Última invoice no QuickBooks: " + (json.dumps({"numero": inv["doc_number"], "valor": inv["amount"], "memo": inv["memo"], "emitida_em": inv["issued_on"],
                                                                 "cliente_id_qbo": inv["customer_ref"], "email_cobranca": inv["customer_email"]}, ensure_ascii=False) if inv else "nenhuma no espelho"),
              "- Waiver: " + (f"ASSINADA em {assinada['completed_at'][:10]} por {assinada['signer_name']} ({assinada['template']}) — vale um ano, NÃO peça de novo" if assinada
                              else ("nenhuma assinada nos últimos 12 meses" + (f"; última: {ws[0]['status']} ({ws[0]['template']})" if ws else ""))),
              ]
    if inv and inv["customer_ref"]:
        linhas.append(f"- Para invoice: cliente_id={inv['customer_ref']} (id do responsável no QBO), email={inv['customer_email'] or c.get('email')}")
    if itens:
        linhas.append("- Itens do QuickBooks (item_id: nome, preço de lista; o preço válido é o da Rate Card): " +
                      "; ".join(f"{i['id']}: {i['name']}" + (f" (${i['price']:.0f})" if i.get("price") else "") for i in itens))
    return "\n".join(linhas)


def _prompt_evento(con, ev):
    regra = {"task.created": "Um serviço NOVO entrou no quadro. Verifique a waiver do piloto (docusign_waivers_de pelo e-mail do responsável; menor = parental) e, se faltar, PROPONHA o envio. "
                             "Verifique o que falta para a invoice (produto/valor): se souber pelo Rate Card e pela tarefa, proponha a invoice com o valor; se não souber, diga exatamente o que falta. "
                             "Comente na tarefa do Asana o que preparou.",
             "email.received": "Chegou e-mail de um cliente conhecido. Leia a thread (gmail_thread), diga o que ele quer, classifique com o marcador certo e, se precisar de resposta, PROPONHA um rascunho (gmail_rascunho). Nunca envie.",
             "waiver.bounced": "A waiver deste cliente voltou (e-mail devolvido). Procure o e-mail correto na tarefa do Asana e nas caixas do Gmail; PROPONHA a correção e o reenvio, ou diga que não achou.",
             "waiver.completed": "A waiver deste cliente foi assinada. Comente na tarefa do Asana correspondente que a waiver chegou (asana_comentar).",
             "billing.monthly": "É dia 1: monte a invoice MENSAL deste cliente conforme o plano (campo monthly_plan e monthly_note do cliente) "
                                "e os preços da aba Academy da Rate Card (mensal sem contrato; extra = mensal ÷ 4; +$250/sessão fora do OKC). "
                                "Ache o cliente no QuickBooks (qbo_clientes_buscar pelo e-mail do responsável) e o item no catálogo (qbo_itens_buscar). "
                                "Declare UMA ação: ACAO: qbo_criar_e_enviar_invoice | <cliente> | mensalidade <mês> | {json com cliente_id, linhas[item_id, quantidade, unitario, descricao], vence_em, memo, email}. "
                                "Não invente valor: se algo faltar, diga o que falta e não proponha a ação.",
             "task.overdue": "A tarefa está numa coluna de dia que já passou e continua aberta. Leia a tarefa (asana_tarefa) e os comentários. "
                             "Se o serviço aconteceu (subtarefas feitas, comentário de conclusão, ou simplesmente a data passou sem cancelamento), "
                             "declare ACAO: asana_mover_para_finished | <gid> | mover para Finished Services | {\"gid\":\"<gid>\"} — essa ação é SAFE e executa sozinha. "
                             "Se houver sinal de que NÃO aconteceu (cancelado, remarcado), diga isso claramente e não mova.",
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


def processar_eventos(con, user_id, limite=3):
    """Transforma eventos NEW em comandos para o agente (um por evento), respeitando as regras."""
    disparados = 0
    for ev in todos(con, "SELECT * FROM ai_events WHERE status='NEW' ORDER BY id LIMIT ?", (limite,)):
        if not regra_ligada(con, ev["kind"]):
            atualizar(con, "ai_events", ev["id"], status="SKIPPED", handled_at=agora(), note="regra desligada")
            continue
        texto = _prompt_evento(con, ev)
        # UMA sessão por dia para todos os eventos: cada chave nova sobe outro sandbox (09/09: 6 containers)
        session_key = f"agent:{ia.AGENTE}:eventos-{agora()[:10]}"
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
def _tarefa_da_invoice(con, acao_row, args):
    """gid da tarefa do Asana a que a invoice pertence: a tarefa criada no mesmo comando,
    ou a tarefa do cliente com a mesma data de vencimento."""
    if acao_row.get("command_id"):
        for x in todos(con, "SELECT result FROM ai_actions WHERE command_id=? AND action IN ('asana_criar_do_modelo','asana_criar_tarefa') AND status='DONE'", (acao_row["command_id"],)):
            try:
                gid = (json.loads(x["result"] or "{}")).get("gid")
            except ValueError:
                gid = None
            if gid:
                return gid
    email = (args.get("email") or "").lower()
    data = args.get("vence_em")
    c = um(con, "SELECT id FROM clients WHERE LOWER(email)=? OR LOWER(email_alt)=?", (email, email)) if email else None
    if c and data:
        t = um(con, """SELECT l.external_id FROM tasks t JOIN entity_links l ON l.entity_type='task' AND l.entity_id=t.id AND l.system='asana'
                       WHERE t.client_id=? AND t.due_on=? ORDER BY t.id DESC LIMIT 1""", (c["id"], data))
        if t:
            return t["external_id"]
    return None


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
        from command_center.api import acoes as _ac
        acao = _ac.nome_canonico(a["action"])
        acao, args = _ac.converter(acao, args)
        args, sobrando = _ac.ajustar_aos_parametros(acao, args)
        if sobrando:
            auditar(con, "action.args_ajustados", "system", entity_type="ai_action", entity_id=aid, detail={"acao": acao, "descartados": sobrando})
        sistema = acao.split("_")[0]
        if acao == "asana_mover_para_finished":       # açúcar SAFE: só para a coluna Finished Services
            from command_center.providers.sync import SECAO_FINISHED
            acao, args = "asana_mover_para_secao", {"gid": args.get("gid"), "secao_gid": SECAO_FINISHED}
        sistema = acao.split("_")[0]
        if sistema == "qbo":
            sistema = "quickbooks"
        if sistema == "google":
            sistema = "gmail"
        anterior = os.environ.get("APLICAR")
        os.environ["APLICAR"] = "1"                 # aprovação humana = autorização, só nesta chamada
        try:
            res = chamar(sistema, acao, **args)
        finally:
            if anterior is None:
                os.environ.pop("APLICAR", None)
            else:
                os.environ["APLICAR"] = anterior
        atualizar(con, "ai_actions", aid, status="DONE", finished_at=agora(), result=json.dumps(res, ensure_ascii=False)[:2000])
        auditar(con, "action.executed", f"user:{user_id}", user_id=user_id, entity_type="ai_action", entity_id=aid,
                detail={"action": a["action"], "args": {k: (str(v)[:80]) for k, v in args.items()}})
        if acao in ("qbo_criar_e_enviar_invoice", "qbo_criar_invoice") and isinstance(res, dict) and res.get("link"):
            try:                                              # o link da invoice volta para a linha 'Invoice link:' da tarefa
                gid = _tarefa_da_invoice(con, a, args)
                if gid:
                    from command_center.providers import modulo
                    texto_inv = " ".join(str(x) for x in [args.get("memo")] + [l.get("descricao") for l in (args.get("linhas") or []) if isinstance(l, dict)] if x).lower()
                    deposito = bool(re.search(r"deposit|dep[oó]sito|cau[çc][ãa]o", texto_inv))
                    modulo("asana").preencher_invoice_na_tarefa(gid, res["link"], res.get("total"), deposito=deposito)
                    auditar(con, "asana.invoice_link", "system", entity_type="ai_action", entity_id=aid, detail={"gid": gid, "link": res["link"], "campo": "Security deposit" if deposito else "Invoice link"})
            except Exception as e:
                auditar(con, "asana.invoice_link.failed", "system", entity_type="ai_action", entity_id=aid, detail={"erro": str(e)[:200]})
    except NaoConectado as e:
        atualizar(con, "ai_actions", aid, status="FAILED", finished_at=agora(), result=f"não conectado: {e}")
    except Exception as e:
        atualizar(con, "ai_actions", aid, status="FAILED", finished_at=agora(), result=f"{type(e).__name__}: {str(e)[:500]}")
        auditar(con, "action.failed", f"user:{user_id}", user_id=user_id, entity_type="ai_action", entity_id=aid, detail={"erro": str(e)[:300]})
        try:                                              # caiu durante o uso da IA: re-sonda só esse sistema
            from command_center.api import agenda
            agenda.sondar_apos_falha(con, sistema, str(e))
        except Exception:
            pass
    finally:
        con.close()


def executar_safe(con, command_id, user_id):
    """Ações SAFE com argumentos executam sozinhas, logo depois de propostas.
    É a autocorreção: o que não precisa de humano não espera humano."""
    ids = [a["id"] for a in todos(con, "SELECT id, payload FROM ai_actions WHERE command_id=? AND policy='SAFE' AND status='PROPOSED'", (command_id,))
           if isinstance((json.loads(a["payload"] or "{}")).get("args"), dict)]
    for aid in ids:
        atualizar(con, "ai_actions", aid, status="APPROVED")
        auditar(con, "action.auto", "system", user_id=user_id, entity_type="ai_action", entity_id=aid, detail={"policy": "SAFE"})
    for aid in ids:
        executar_acao(aid, user_id)
    return len(ids)


def eventos_do_dia_1(con, hoje=None):
    """No dia 1 do mês, um evento billing.monthly por cliente com plano mensal (uma vez por mês)."""
    from datetime import date
    hoje = hoje or date.today()
    if hoje.day != 1:
        return 0
    mes = hoje.strftime("%Y-%m")
    n = 0
    for c in todos(con, "SELECT id, name, pilot_name, monthly_plan FROM clients WHERE monthly_plan IS NOT NULL AND monthly_plan<>'' AND status IN ('ACTIVE','NEW','PENDING')"):
        if um(con, "SELECT 1 FROM ai_events WHERE kind='billing.monthly' AND entity_type='client' AND entity_id=? AND summary LIKE ?", (c["id"], f"mensalidade {mes}%")):
            continue
        # a chave única é (kind, tipo, id): para permitir um por mês, o id do evento leva o mês no summary e o entity_id é o cliente
        con.execute("DELETE FROM ai_events WHERE kind='billing.monthly' AND entity_type='client' AND entity_id=? AND status IN ('DONE','FAILED','SKIPPED')", (c["id"],))
        registrar_evento(con, "billing.monthly", "client", c["id"], c["id"], f"mensalidade {mes}: {c['pilot_name'] or c['name']} — plano {c['monthly_plan']}")
        n += 1
    return n

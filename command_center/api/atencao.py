"""NEEDS ATTENTION — o que exige humano, com prioridade contextual.

Não é "o mais velho primeiro". Cada regra pesa contexto: dinheiro, prazo
do serviço, dependência (waiver bloqueia pista), VIP, e-mail devolvido.
Regras vêm do cérebro (PARAMETROS: waiver 2 dias antes; delivered ≠
assinado; autoresponded = bounce; VIP dispensa waiver).

Cada item devolve: level, title, why, entity (tipo/id), link, action.
"""
import json
from datetime import date, datetime, timedelta

from command_center.db import todos, um

NIVEIS = ("CRITICAL", "HIGH", "MEDIUM", "LOW")


def _dias_ate(iso):
    if not iso:
        return None
    try:
        return (date.fromisoformat(iso[:10]) - date.today()).days
    except ValueError:
        return None


def _link(con, tipo, id_):
    r = um(con, "SELECT deep_link FROM entity_links WHERE entity_type=? AND entity_id=? AND deep_link IS NOT NULL LIMIT 1", (tipo, id_))
    return r["deep_link"] if r else None


def coletar(con, incluir_ocultos=False):
    """Itens ativos; com incluir_ocultos=True devolve também os ocultos, marcados."""
    itens = _coletar(con)
    ocultos = {r["key"]: r for r in todos(con, """SELECT d.*, u.name AS dismissed_by_name FROM attention_dismissals d
                                                  LEFT JOIN users u ON u.id = d.dismissed_by""")}
    saida = []
    for it in itens:
        d = ocultos.get(it["key"])
        if d and not incluir_ocultos:
            continue
        it["dismissed"] = {"by": d["dismissed_by_name"], "at": d["dismissed_at"], "reason": d["reason"]} if d else None
        saida.append(it)
    return saida


def _chave(regra, tipo, id_):
    return f"{regra}:{tipo}:{id_}"


def _usd(v):
    return "—" if v is None else f"${float(v):,.2f}"


def _dbr(iso):
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso and len(iso) >= 10 else "—"


def _fatos_tarefa(t):
    """Nome, data, coluna, piloto/responsável, produto e categoria, subtarefas — tudo que identifica a tarefa."""
    from command_center.api.acoes import _partes_do_nome
    piloto, produto, categoria = _partes_do_nome(t.get("title"))
    f = [("Tarefa", t.get("title") or "—"), ("Data", _dbr(t.get("due_on"))), ("Coluna", t.get("section") or "—")]
    if t.get("cliente") or t.get("pilot_name"):
        f.append(("Piloto", t.get("pilot_name") or piloto or "—"))
        f.append(("Responsável", t.get("cliente") or "—"))
    if produto:
        f.append(("Serviço", produto + (f" / {categoria}" if categoria else "")))
    if t.get("subtasks_total"):
        f.append(("Subtarefas", f"{t.get('subtasks_done') or 0}/{t['subtasks_total']}"))
    if t.get("email"):
        f.append(("E-mail", t["email"]))
    return f


def _fatos_waiver(w):
    return [("Assina", w.get("signer_name") or "—"), ("E-mail", w.get("signer_email") or "—"), ("Modelo", w.get("template") or "—"),
            ("Enviada", _dbr(w.get("sent_at"))), ("Expira", _dbr(w.get("expires_at"))), ("Cliente", w.get("cliente") or "sem vínculo")]


def _coletar(con):
    itens = []
    hoje = date.today()

    # ---- 1. serviço próximo sem waiver (a regra que mais custa)
    for t in todos(con, """SELECT t.*, c.name AS cliente, c.email, c.vip, c.pilot_name
                           FROM tasks t LEFT JOIN clients c ON c.id = t.client_id
                           WHERE t.status='open' AND t.due_on IS NOT NULL AND t.project='U-RACE'"""):
        dias = _dias_ate(t["due_on"])
        if dias is None or dias < 0 or dias > 7:
            continue
        if t["vip"]:
            continue                                   # VIP dispensa waiver (04/09)
        w = um(con, """SELECT status, expires_at FROM waivers WHERE client_id=? AND status='completed'
                       AND completed_at >= ? ORDER BY completed_at DESC LIMIT 1""",
               (t["client_id"], (hoje - timedelta(days=365)).isoformat())) if t["client_id"] else None
        if w:
            continue
        aberto = um(con, "SELECT status FROM waivers WHERE client_id=? AND status IN ('sent','delivered') LIMIT 1",
                    (t["client_id"],)) if t["client_id"] else None
        if dias <= 1:
            nivel = "CRITICAL"
        elif dias <= 2:
            nivel = "HIGH"
        else:
            nivel = "MEDIUM"
        quem = t["cliente"] or t["pilot_name"] or t["title"]
        itens.append(dict(
            key=_chave("waiver-servico", "task", t["id"]),
            level=nivel,
            title=f"{quem}: serviço em {dias} dia(s) sem waiver assinada" if dias else f"{quem}: serviço HOJE sem waiver assinada",
            why=("Envelope aberto (" + aberto["status"] + ", não assinado)." if aberto else "Nenhum envelope enviado.")
                + " Regra: waiver assinada 2 dias antes do serviço.",
            entity={"type": "task", "id": t["id"]}, client_id=t["client_id"],
            link=_link(con, "task", t["id"]),
            action="Enviar waiver" if not aberto else "Cobrar assinatura",
            facts=_fatos_tarefa(t) + [("Waiver", aberto["status"] if aberto else "nenhuma enviada")],
        ))

    # ---- 2. e-mail devolvido (envelope que nunca vai ser assinado)
    for w in todos(con, "SELECT w.*, c.name AS cliente FROM waivers w LEFT JOIN clients c ON c.id=w.client_id WHERE w.status='autoresponded'"):
        itens.append(dict(key=_chave("waiver-devolveu", "waiver", w["id"]), level="HIGH", title=f"Waiver de {w['signer_name'] or w['cliente']} devolveu (e-mail inválido)",
                          why=f"{w['signer_email']}: o servidor de e-mail recusou. Ninguém vai assinar esse envelope.",
                          entity={"type": "waiver", "id": w["id"]}, client_id=w["client_id"],
                          link=_link(con, "waiver", w["id"]), action="Corrigir e-mail e reenviar", facts=_fatos_waiver(w)))

    # ---- 3. waiver perto de expirar, com serviço no quadro
    for w in todos(con, """SELECT w.*, c.name AS cliente FROM waivers w LEFT JOIN clients c ON c.id=w.client_id
                           WHERE w.status IN ('sent','delivered') AND w.expires_at IS NOT NULL"""):
        dias = _dias_ate(w["expires_at"])
        if dias is None or dias > 21:
            continue
        tem_servico = um(con, "SELECT 1 FROM tasks WHERE client_id=? AND status='open'", (w["client_id"],)) if w["client_id"] else None
        itens.append(dict(key=_chave("waiver-expira", "waiver", w["id"]), level="MEDIUM" if tem_servico else "LOW",
                          title=f"Waiver de {w['signer_name'] or w['cliente']} expira em {dias} dia(s)",
                          why=("Há serviço agendado para este cliente. " if tem_servico else "Sem serviço agendado. ")
                              + ("Aberta e não assinada." if w["status"] == "delivered" else "Enviada, nunca aberta."),
                          entity={"type": "waiver", "id": w["id"]}, client_id=w["client_id"],
                          link=_link(con, "waiver", w["id"]), action="Decidir: cobrar ou deixar expirar", facts=_fatos_waiver(w)))

    # ---- 4. tarefa vencida ainda aberta — só depois que a IA tentou (evento task.overdue DONE/FAILED)
    for t in todos(con, """SELECT t.*, c.name AS cliente, c.pilot_name, c.email, ev.status AS ev_status, cmd.output AS ia_out, cmd.error AS ia_err
                           FROM tasks t LEFT JOIN clients c ON c.id=t.client_id
                           LEFT JOIN ai_events ev ON ev.kind='task.overdue' AND ev.entity_type='task' AND ev.entity_id=t.id
                           LEFT JOIN ai_commands cmd ON cmd.id=ev.command_id
                           WHERE t.status='open' AND t.due_on < ? AND t.project='U-RACE' AND LOWER(COALESCE(t.section,'')) NOT IN ('races','finished services')""",
                   (hoje.isoformat(),)):
        if t["ev_status"] in ("NEW", "RUNNING"):
            continue                                   # a IA está cuidando; não incomoda o humano
        dias = -(_dias_ate(t["due_on"]) or 0)
        if t["ev_status"] is None and dias <= 1:
            continue                                   # ainda vai virar evento na próxima sincronia
        resumo_ia = ((t["ia_out"] or t["ia_err"] or "").strip().split("\n")[0][:160])
        itens.append(dict(key=_chave("tarefa-vencida", "task", t["id"]), level="LOW" if t["ev_status"] == "DONE" else "MEDIUM",
                          title=f"{t['title'][:70]} · venceu em {_dbr(t['due_on'])} ({dias} dia(s)) e continua aberta",
                          why=("A IA tentou e disse: " + resumo_ia) if resumo_ia else "Serviço concluído deve ir para Finished Services; ainda está na coluna do dia.",
                          entity={"type": "task", "id": t["id"]}, client_id=t["client_id"],
                          link=_link(con, "task", t["id"]), action="Mover ou concluir", facts=_fatos_tarefa(t)))

    # ---- 4b. invoice vencida há mais de 30 dias (regra do dono: cobrança por lote, mas não some)
    for i in todos(con, """SELECT i.*, c.name AS cliente, c.pilot_name FROM invoices i LEFT JOIN clients c ON c.id=i.client_id
                           WHERE i.status='overdue' AND i.due_on < ? ORDER BY i.due_on""",
                   ((hoje - timedelta(days=30)).isoformat(),)):
        dias = -(_dias_ate(i["due_on"]) or 0)
        quem = i["cliente"] or i.get("customer_email") or "cliente não identificado"
        servico = (i.get("memo") or "").strip() or "serviço não descrito na invoice"
        itens.append(dict(key=_chave("invoice-vencida", "invoice", i["id"]), level="MEDIUM" if dias < 90 else "HIGH",
                          title=f"Invoice {i['doc_number'] or ''} · {quem} · {_usd(i['balance'] if i.get('balance') is not None else i['amount'])} em aberto · venceu em {_dbr(i['due_on'])} ({dias} dias)",
                          why=f"{servico}. Emitida em {_dbr(i.get('issued_on'))}. Saldo em aberto não é inadimplência (pode haver parcelamento); a cobrança é por lote (D-2026-08-31).",
                          entity={"type": "invoice", "id": i["id"]}, client_id=i["client_id"],
                          link=_link(con, "invoice", i["id"]), action="Cobrar no lote",
                          facts=[("Cliente", quem), ("Piloto", i.get("pilot_name") or "—"), ("Serviço", servico), ("Valor", _usd(i["amount"])),
                                 ("Em aberto", _usd(i["balance"])), ("Emitida", _dbr(i.get("issued_on"))), ("Venceu", _dbr(i.get("due_on"))),
                                 ("E-mail de cobrança", i.get("customer_email") or "—")]))

    # ---- 5. integrações com erro
    for i in todos(con, "SELECT * FROM integrations WHERE status IN ('ERROR','DEGRADED')"):
        itens.append(dict(key=_chave("integracao", "integration", i["system"]), level="HIGH" if i["status"] == "ERROR" else "MEDIUM",
                          title=f"Integração {i['system']}: {i['status']}",
                          why=(i["last_error"] or "")[:200], entity={"type": "integration", "id": i["system"]},
                          client_id=None, link=None, action="Ver integrações",
                          facts=[("Sistema", i["system"]), ("Último sucesso", (i.get("last_success_at") or "—")[:16].replace("T", " ")), ("Última tentativa", (i.get("last_attempt_at") or "—")[:16].replace("T", " ")), ("Erros seguidos", str(i.get("error_count") or 0))]))

    # ---- 6. ações da IA esperando aprovação / falhas
    pend = todos(con, "SELECT id, action, payload, created_at FROM ai_actions WHERE status='PROPOSED' AND policy='REQUIRES_APPROVAL' ORDER BY id DESC LIMIT 10")
    if pend:
        from command_center.api.acoes import ACOES_INVOICE
        detalhes = []
        for a in pend:
            try:
                pl = json.loads(a["payload"] or "{}")
            except ValueError:
                pl = {}
            args = pl.get("args") if isinstance(pl.get("args"), dict) else {}
            alvo = pl.get("alvo") or "—"
            if a["action"] in ACOES_INVOICE:
                total = sum((l.get("quantidade") or 1) * (l.get("unitario") or 0) for l in args.get("linhas") or [] if isinstance(l, dict))
                desc = next((l.get("descricao") for l in args.get("linhas") or [] if isinstance(l, dict) and l.get("descricao")), None)
                detalhes.append(("Invoice", f"{alvo} · {_usd(total)}" + (f" · {desc}" if desc else "") + (f" · serviço {_dbr(args.get('data_servico'))}" if args.get("data_servico") else "")))
            elif a["action"] == "docusign_enviar_waiver":
                detalhes.append(("Waiver", f"{args.get('nome') or alvo} <{args.get('email') or '—'}>"))
            else:
                detalhes.append((a["action"], alvo))
        itens.append(dict(key=_chave("aprovacoes", "approvals", "pendentes"), level="HIGH",
                          title=(f"{detalhes[0][0]} esperando sua aprovação: {detalhes[0][1]}" if len(pend) == 1
                                 else f"{len(pend)} ações da IA esperando sua aprovação"),
                          why="Nada executa sem aprovação humana. Aprovar uma invoice cria E envia ao cliente.",
                          entity={"type": "approvals", "id": None}, client_id=None, link=None, action="Revisar",
                          facts=[(k, v) for k, v in detalhes[:6]]))
    # falha da IA só vira item se a ÚLTIMA execução falhou (se ela se recuperou depois, não incomoda)
    ult = um(con, "SELECT status, error FROM ai_commands WHERE status IN ('DONE','FAILED') ORDER BY finished_at DESC LIMIT 1")
    if ult and ult["status"] == "FAILED":
        n = um(con, "SELECT COUNT(*) AS n FROM ai_commands WHERE status='FAILED' AND created_at > ?",
               ((datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),))
        itens.append(dict(key=_chave("ia-falhas", "ai", "24h"), level="MEDIUM", title=f"A IA falhou {n['n']} vez(es) nas últimas 24h e ainda não se recuperou",
                          why=(ult["error"] or "sem detalhe")[:200], entity={"type": "ai", "id": None},
                          client_id=None, link=None, action="Ver AI Command"))

    # ---- 7. e-mails de cliente conhecido: só na inbox, recentes, não nossos, não notificação
    from command_center.providers import classificar
    corte = (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%S")
    for e in todos(con, """SELECT e.*, c.name AS cliente FROM emails e JOIN clients c ON c.id=e.client_id
                           WHERE e.handled=0 AND (COALESCE(e.is_inbox,1)=1 OR COALESCE(e.needs_human,0)=1) AND COALESCE(e.last_at,'') >= ?
                           ORDER BY e.last_at DESC LIMIT 20""", (corte,)):
        if classificar.auto_tratar(e, e.get("suggested_label")):
            continue
        nivel = "HIGH" if (e.get("priority") in ("CRITICAL", "HIGH")) else "MEDIUM"
        itens.append(dict(key=_chave("email-cliente", "email", e["id"]), level=nivel, title=f"{e['cliente']} escreveu: {(e['subject'] or '')[:60]}",
                          why=(f"A IA moveu para '{e.get('suggested_label')}' ({e.get('triage_reason') or 'pede resposta'}), mas é uma pessoa que responde." if e.get("needs_human") and not e.get("is_inbox")
                               else f"Na inbox {e['mailbox']}@ há {max(0, (datetime.utcnow() - datetime.fromisoformat(e['last_at'][:19])).days) if e.get('last_at') else '?'} dia(s), sem resposta. Intenção: {e.get('intent') or 'não classificada'}."),
                          entity={"type": "email", "id": e["id"]}, client_id=e["client_id"],
                          link=_link(con, "email", e["id"]), action="Responder",
                          facts=[("De", e.get("sender") or "—"), ("Assunto", e.get("subject") or "—"), ("Caixa", f"{e['mailbox']}@urace.us"),
                                 ("Quando", (e.get("last_at") or "—")[:16].replace("T", " ")), ("Cliente", e["cliente"]), ("Trecho", (e.get("snippet") or "")[:140] or "—")]))

    ordem = {n: i for i, n in enumerate(NIVEIS)}
    itens.sort(key=lambda x: ordem[x["level"]])
    return itens

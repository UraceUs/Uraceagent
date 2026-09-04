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


def coletar(con):
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
            level=nivel,
            title=f"{quem}: serviço em {dias} dia(s) sem waiver assinada" if dias else f"{quem}: serviço HOJE sem waiver assinada",
            why=("Envelope aberto (" + aberto["status"] + ", não assinado)." if aberto else "Nenhum envelope enviado.")
                + " Regra: waiver assinada 2 dias antes do serviço.",
            entity={"type": "task", "id": t["id"]}, client_id=t["client_id"],
            link=_link(con, "task", t["id"]),
            action="Enviar waiver" if not aberto else "Cobrar assinatura",
        ))

    # ---- 2. e-mail devolvido (envelope que nunca vai ser assinado)
    for w in todos(con, "SELECT w.*, c.name AS cliente FROM waivers w LEFT JOIN clients c ON c.id=w.client_id WHERE w.status='autoresponded'"):
        itens.append(dict(level="HIGH", title=f"Waiver de {w['signer_name'] or w['cliente']} devolveu (e-mail inválido)",
                          why=f"{w['signer_email']}: o servidor de e-mail recusou. Ninguém vai assinar esse envelope.",
                          entity={"type": "waiver", "id": w["id"]}, client_id=w["client_id"],
                          link=_link(con, "waiver", w["id"]), action="Corrigir e-mail e reenviar"))

    # ---- 3. waiver perto de expirar, com serviço no quadro
    for w in todos(con, """SELECT w.*, c.name AS cliente FROM waivers w LEFT JOIN clients c ON c.id=w.client_id
                           WHERE w.status IN ('sent','delivered') AND w.expires_at IS NOT NULL"""):
        dias = _dias_ate(w["expires_at"])
        if dias is None or dias > 21:
            continue
        tem_servico = um(con, "SELECT 1 FROM tasks WHERE client_id=? AND status='open'", (w["client_id"],)) if w["client_id"] else None
        itens.append(dict(level="MEDIUM" if tem_servico else "LOW",
                          title=f"Waiver de {w['signer_name'] or w['cliente']} expira em {dias} dia(s)",
                          why=("Há serviço agendado para este cliente. " if tem_servico else "Sem serviço agendado. ")
                              + ("Aberta e não assinada." if w["status"] == "delivered" else "Enviada, nunca aberta."),
                          entity={"type": "waiver", "id": w["id"]}, client_id=w["client_id"],
                          link=_link(con, "waiver", w["id"]), action="Decidir: cobrar ou deixar expirar"))

    # ---- 4. tarefa vencida ainda aberta
    for t in todos(con, "SELECT t.*, c.name AS cliente FROM tasks t LEFT JOIN clients c ON c.id=t.client_id WHERE t.status='open' AND t.due_on < ?",
                   (hoje.isoformat(),)):
        dias = -(_dias_ate(t["due_on"]) or 0)
        itens.append(dict(level="MEDIUM" if dias <= 3 else "LOW",
                          title=f"Tarefa vencida há {dias} dia(s): {t['title'][:60]}",
                          why="Serviço concluído deve ir para Finished Services; ainda está na coluna do dia.",
                          entity={"type": "task", "id": t["id"]}, client_id=t["client_id"],
                          link=_link(con, "task", t["id"]), action="Mover ou concluir"))

    # ---- 5. integrações com erro
    for i in todos(con, "SELECT * FROM integrations WHERE status IN ('ERROR','DEGRADED')"):
        itens.append(dict(level="HIGH" if i["status"] == "ERROR" else "MEDIUM",
                          title=f"Integração {i['system']}: {i['status']}",
                          why=(i["last_error"] or "")[:200], entity={"type": "integration", "id": i["system"]},
                          client_id=None, link=None, action="Ver integrações"))

    # ---- 6. ações da IA esperando aprovação / falhas
    n = um(con, "SELECT COUNT(*) AS n FROM ai_actions WHERE status='PROPOSED' AND policy='REQUIRES_APPROVAL'")
    if n and n["n"]:
        itens.append(dict(level="HIGH", title=f"{n['n']} ação(ões) da IA esperando sua aprovação",
                          why="Nada executa sem aprovação humana.", entity={"type": "approvals", "id": None},
                          client_id=None, link=None, action="Revisar"))
    n = um(con, "SELECT COUNT(*) AS n FROM ai_commands WHERE status='FAILED' AND created_at > ?",
           ((datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S"),))
    if n and n["n"]:
        itens.append(dict(level="HIGH", title=f"{n['n']} comando(s) da IA falharam nas últimas 48h",
                          why="Ver o erro no histórico do AI Command.", entity={"type": "ai", "id": None},
                          client_id=None, link=None, action="Ver AI Activity"))

    # ---- 7. e-mails não tratados de cliente conhecido
    for e in todos(con, """SELECT e.*, c.name AS cliente FROM emails e JOIN clients c ON c.id=e.client_id
                           WHERE e.handled=0 ORDER BY e.last_at DESC LIMIT 20"""):
        itens.append(dict(level="HIGH", title=f"{e['cliente']} escreveu: {(e['subject'] or '')[:60]}",
                          why=f"Cliente conhecido na caixa {e['mailbox']}@ sem tratamento.",
                          entity={"type": "email", "id": e["id"]}, client_id=e["client_id"],
                          link=_link(con, "email", e["id"]), action="Responder"))

    ordem = {n: i for i, n in enumerate(NIVEIS)}
    itens.sort(key=lambda x: ordem[x["level"]])
    return itens

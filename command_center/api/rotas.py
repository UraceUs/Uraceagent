"""Rotas de dados da Fase 1: dashboard, atenção, clientes, busca,
integrações, políticas. Toda rota exige sessão; escrita exige papel.
"""
import json
import sqlite3
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from command_center.api import atencao, auth
from command_center.db import auditar, get_db, todos, um
from command_center.providers import SISTEMAS, recarregar, saude
from command_center.providers import sync as sy

BASE = "/ops/api"
r = APIRouter(prefix=BASE)


def _links(con, tipo, id_):
    return todos(con, "SELECT system, external_id, deep_link FROM entity_links WHERE entity_type=? AND entity_id=?", (tipo, id_))


# ------------------------------------------------------- integrações
@r.get("/integrations")
def integrations(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    return todos(con, "SELECT * FROM integrations ORDER BY system")


@r.post("/integrations/check")
def integrations_check(request: Request, u=Depends(auth.exige("OPERATOR")),
                       con: sqlite3.Connection = Depends(get_db)):
    """Sonda cada sistema com UMA chamada real e grava o estado."""
    recarregar()
    saida = {}
    for s in SISTEMAS:
        st, det = saude(s)
        con.execute("UPDATE integrations SET status=?, last_attempt_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
                    "last_success_at=CASE WHEN ? IN ('CONNECTED','DEGRADED') THEN strftime('%Y-%m-%dT%H:%M:%fZ','now') ELSE last_success_at END, "
                    "last_error=CASE WHEN ? IN ('ERROR','DISCONNECTED') THEN ? ELSE NULL END, detail=? WHERE system=?",
                    (st, st, st, json.dumps(det, ensure_ascii=False)[:500], json.dumps(det, ensure_ascii=False), s))
        saida[s] = {"status": st, "detail": det}
    auditar(con, "integrations.check", f"user:{u['id']}", user_id=u["id"], ip=auth._ip(request))
    return saida


@r.post("/sync")
def sync(request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """Atualiza os espelhos a partir das fontes reais. Só leitura nos sistemas."""
    res = sy.sync_tudo(con)
    auditar(con, "sync.run", f"user:{u['id']}", user_id=u["id"], detail=res, ip=auth._ip(request))
    return res


# --------------------------------------------------------- dashboard
@r.get("/dashboard")
def dashboard(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    hoje = date.today().isoformat()
    n = lambda sql, p=(): (um(con, sql, p) or {}).get("n", 0)
    fin = auth.pode(u["role"], "MANAGER")   # financeiro: MANAGER+
    inv_abertas = todos(con, "SELECT amount, balance, due_on FROM invoices WHERE status IN ('sent','overdue')") if fin else []
    atencao_itens = atencao.coletar(con)
    return {
        "active_clients": n("SELECT COUNT(*) AS n FROM clients WHERE status='ACTIVE'"),
        "tasks_due_today": n("SELECT COUNT(*) AS n FROM tasks WHERE status='open' AND due_on=?", (hoje,)),
        "overdue_tasks": n("SELECT COUNT(*) AS n FROM tasks WHERE status='open' AND due_on<?", (hoje,)),
        "upcoming_7d": n("SELECT COUNT(*) AS n FROM tasks WHERE status='open' AND due_on BETWEEN ? AND ?",
                         (hoje, (date.today() + timedelta(days=7)).isoformat())),
        "waivers_open": n("SELECT COUNT(*) AS n FROM waivers WHERE status IN ('sent','delivered')"),
        "waivers_bounced": n("SELECT COUNT(*) AS n FROM waivers WHERE status='autoresponded'"),
        "emails_attention": n("SELECT COUNT(*) AS n FROM emails WHERE handled=0 AND client_id IS NOT NULL"),
        "ai_actions_today": n("SELECT COUNT(*) AS n FROM ai_actions WHERE created_at >= ?", (hoje,)),
        "ai_pending_approval": n("SELECT COUNT(*) AS n FROM ai_actions WHERE status='PROPOSED' AND policy='REQUIRES_APPROVAL'"),
        "open_invoices": (None if not fin else {
            "count": len(inv_abertas), "total": round(sum(i["balance"] or 0 for i in inv_abertas), 2),
            "overdue": sum(1 for i in inv_abertas if (i["due_on"] or "9999") < hoje),
            "connected": (um(con, "SELECT status FROM integrations WHERE system='quickbooks'") or {}).get("status") == "CONNECTED"}),
        "integrations": todos(con, "SELECT system, status, last_success_at FROM integrations ORDER BY system"),
        "needs_attention": atencao_itens[:12],
        "needs_attention_total": len(atencao_itens),
        "last_sync": todos(con, "SELECT system, MAX(finished_at) AS at, ok, message FROM sync_logs GROUP BY system"),
    }


@r.get("/needs-attention")
def needs_attention(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    return atencao.coletar(con)


# ----------------------------------------------------------- clientes
@r.get("/clients")
def clients(status: str = None, q: str = None, vip: bool = None,
            u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    where, p = ["1=1"], []
    if status:
        where.append("c.status=?"); p.append(status.upper())
    if vip is not None:
        where.append("c.vip=?"); p.append(1 if vip else 0)
    if q:
        where.append("(c.name LIKE ? OR c.pilot_name LIKE ? OR c.email LIKE ?)"); p += [f"%{q}%"] * 3
    rows = todos(con, f"""
        SELECT c.*, s.label AS stage,
          (SELECT COUNT(*) FROM tasks t WHERE t.client_id=c.id AND t.status='open') AS open_tasks,
          (SELECT MIN(due_on) FROM tasks t WHERE t.client_id=c.id AND t.status='open' AND due_on>=date('now')) AS next_service,
          (SELECT status FROM waivers w WHERE w.client_id=c.id ORDER BY sent_at DESC LIMIT 1) AS waiver_status,
          (SELECT COUNT(*) FROM emails e WHERE e.client_id=c.id AND e.handled=0) AS emails_open,
          (SELECT MAX(synced_at) FROM tasks t WHERE t.client_id=c.id) AS last_activity
        FROM clients c LEFT JOIN client_stages s ON s.code=c.stage_code
        WHERE {' AND '.join(where)} ORDER BY next_service IS NULL, next_service, c.name""", p)
    return rows


@r.get("/clients/{cid}")
def client_360(cid: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    c = um(con, "SELECT * FROM clients WHERE id=?", (cid,))
    if not c:
        raise HTTPException(404, "Client not found.")
    fin = auth.pode(u["role"], "MANAGER")
    tarefas = todos(con, "SELECT * FROM tasks WHERE client_id=? ORDER BY due_on DESC", (cid,))
    for t in tarefas:
        t["links"] = _links(con, "task", t["id"])
    waivers = todos(con, "SELECT * FROM waivers WHERE client_id=? ORDER BY sent_at DESC", (cid,))
    for w in waivers:
        w["links"] = _links(con, "waiver", w["id"])
    emails = todos(con, "SELECT * FROM emails WHERE client_id=? ORDER BY last_at DESC LIMIT 50", (cid,))
    for e in emails:
        e["links"] = _links(con, "email", e["id"])
    invoices = todos(con, "SELECT * FROM invoices WHERE client_id=? ORDER BY issued_on DESC", (cid,)) if fin else None
    acoes = todos(con, "SELECT a.* FROM ai_actions a JOIN ai_workflows w ON w.id=a.workflow_id WHERE w.client_id=? ORDER BY a.created_at DESC LIMIT 50", (cid,))
    # timeline: tudo junto, em ordem
    tl = []
    for t in tarefas:
        tl.append({"at": t["due_on"], "kind": "SERVICE", "title": t["title"], "status": t["status"], "entity": {"type": "task", "id": t["id"]}})
    for w in waivers:
        tl.append({"at": (w["sent_at"] or "")[:10], "kind": "WAIVER_SENT", "title": f"Waiver {w['template']} → {w['signer_name']}", "status": w["status"], "entity": {"type": "waiver", "id": w["id"]}})
        if w["completed_at"]:
            tl.append({"at": w["completed_at"][:10], "kind": "WAIVER_SIGNED", "title": f"Waiver assinada por {w['signer_name']}", "status": "completed", "entity": {"type": "waiver", "id": w["id"]}})
    for e in emails:
        tl.append({"at": (e["last_at"] or "")[:10], "kind": "EMAIL", "title": e["subject"], "status": "handled" if e["handled"] else "open", "entity": {"type": "email", "id": e["id"]}})
    for a in acoes:
        tl.append({"at": a["created_at"][:10], "kind": "AI_ACTION", "title": a["action"], "status": a["status"], "entity": {"type": "ai_action", "id": a["id"]}})
    tl.sort(key=lambda x: x["at"] or "", reverse=True)
    return {"client": c, "links": _links(con, "client", cid), "tasks": tarefas, "waivers": waivers,
            "emails": emails, "invoices": invoices, "ai_actions": acoes, "timeline": tl,
            "stages": todos(con, "SELECT code, label FROM client_stages ORDER BY ord")}


class ClienteIn(BaseModel):
    status: str = None
    stage_code: str = None
    notes: str = None
    vip: bool = None


@r.patch("/clients/{cid}")
def client_patch(cid: int, dados: ClienteIn, request: Request, u=Depends(auth.exige("OPERATOR")),
                 con: sqlite3.Connection = Depends(get_db)):
    if not um(con, "SELECT id FROM clients WHERE id=?", (cid,)):
        raise HTTPException(404, "Client not found.")
    campos = {k: v for k, v in dados.model_dump().items() if v is not None}
    if "vip" in campos:
        if not auth.pode(u["role"], "MANAGER"):
            raise HTTPException(403, "Only managers can change VIP.")
        campos["vip"] = 1 if campos["vip"] else 0
    if not campos:
        return {"ok": True}
    sets = ", ".join(f"{k}=?" for k in campos)
    con.execute(f"UPDATE clients SET {sets}, updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (*campos.values(), cid))
    auditar(con, "client.update", f"user:{u['id']}", user_id=u["id"], entity_type="client", entity_id=cid,
            detail=campos, ip=auth._ip(request))
    return {"ok": True}


# -------------------------------------------------------------- busca
@r.get("/search")
def search(q: str, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    q = (q or "").strip()
    if len(q) < 2:
        return {"clients": [], "tasks": [], "waivers": [], "emails": [], "commands": []}
    like = f"%{q}%"
    out = {
        "clients": todos(con, "SELECT id, name, pilot_name, email, status, vip FROM clients WHERE name LIKE ? OR pilot_name LIKE ? OR email LIKE ? LIMIT 8", (like,) * 3),
        "tasks": todos(con, "SELECT id, title, due_on, section, status, client_id FROM tasks WHERE title LIKE ? LIMIT 8", (like,)),
        "waivers": todos(con, "SELECT id, signer_name, signer_email, status, expires_at, client_id FROM waivers WHERE signer_name LIKE ? OR signer_email LIKE ? LIMIT 8", (like, like)),
        "emails": todos(con, "SELECT id, subject, sender, mailbox, last_at, client_id FROM emails WHERE subject LIKE ? OR sender LIKE ? LIMIT 8", (like, like)),
        "commands": todos(con, "SELECT id, text, status, created_at FROM ai_commands WHERE text LIKE ? AND user_id=? ORDER BY id DESC LIMIT 5", (like, u["id"])),
    }
    return out


# ------------------------------------------------------------- listas
@r.get("/tasks")
def tasks(status: str = "open", u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    rows = todos(con, "SELECT t.*, c.name AS client_name FROM tasks t LEFT JOIN clients c ON c.id=t.client_id WHERE t.status=? ORDER BY t.due_on", (status,))
    for t in rows:
        t["links"] = _links(con, "task", t["id"])
    return rows


@r.get("/waivers")
def waivers(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    rows = todos(con, "SELECT w.*, c.name AS client_name FROM waivers w LEFT JOIN clients c ON c.id=w.client_id ORDER BY CASE w.status WHEN 'autoresponded' THEN 0 WHEN 'delivered' THEN 1 WHEN 'sent' THEN 2 ELSE 3 END, w.expires_at")
    for w in rows:
        w["links"] = _links(con, "waiver", w["id"])
    return rows


@r.get("/emails")
def emails(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    rows = todos(con, "SELECT e.*, c.name AS client_name FROM emails e LEFT JOIN clients c ON c.id=e.client_id ORDER BY e.last_at DESC LIMIT 200")
    for e in rows:
        e["links"] = _links(con, "email", e["id"])
    return rows


# ---------------------------------------------------------- políticas
@r.get("/policies")
def policies(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    return todos(con, "SELECT * FROM action_policies ORDER BY policy, action")


class PoliticaIn(BaseModel):
    policy: str
    note: str = None


@r.put("/policies/{action}")
def policy_put(action: str, dados: PoliticaIn, request: Request, u=Depends(auth.exige("ADMIN")),
               con: sqlite3.Connection = Depends(get_db)):
    if dados.policy not in ("SAFE", "REQUIRES_CONFIRMATION", "REQUIRES_APPROVAL", "BLOCKED"):
        raise HTTPException(400, "Invalid policy.")
    atual = um(con, "SELECT * FROM action_policies WHERE action=?", (action,))
    if not atual:
        raise HTTPException(404, "Unknown action.")
    if atual["policy"] == "BLOCKED" and action.startswith("apagar"):
        raise HTTPException(403, "Deleting is blocked by design and cannot be enabled here.")
    con.execute("UPDATE action_policies SET policy=?, note=COALESCE(?, note), updated_by=?, updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE action=?",
                (dados.policy, dados.note, u["id"], action))
    auditar(con, "policy.update", f"user:{u['id']}", user_id=u["id"], entity_type="policy", entity_id=action,
            detail={"from": atual["policy"], "to": dados.policy}, ip=auth._ip(request))
    return {"ok": True}

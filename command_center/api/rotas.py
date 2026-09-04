"""Rotas de dados da Fase 1: dashboard, atenção, clientes, busca,
integrações, políticas. Toda rota exige sessão; escrita exige papel.
"""
import json
import re
import sqlite3
import threading
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from command_center.api import atencao, auth
from command_center.db import agora, auditar, conectar, get_db, todos, um
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


_SYNC = {"running": False, "started_at": None, "finished_at": None, "result": None, "by": None}
_SYNC_LOCK = threading.Lock()


def _sync_thread(user_id, ip):
    con = conectar()
    try:
        res = sy.sync_tudo(con)
        auditar(con, "sync.run", f"user:{user_id}", user_id=user_id, detail=res, ip=ip)
        _SYNC["result"] = res
    except Exception as e:                        # nunca deixa a flag presa em "running"
        _SYNC["result"] = {"ok": False, "motivo": f"{type(e).__name__}: {str(e)[:300]}"}
    finally:
        _SYNC["running"] = False
        _SYNC["finished_at"] = agora()
        con.close()


@r.post("/sync", status_code=202)
def sync(request: Request, wait: bool = False, u=Depends(auth.exige("OPERATOR")),
         con: sqlite3.Connection = Depends(get_db)):
    """Atualiza os espelhos a partir das fontes reais. Só leitura nos sistemas.

    Roda em segundo plano (o histórico do Asana pode levar minutos); o
    estado sai em GET /sync. wait=1 espera terminar (testes e scripts).
    """
    if wait:
        res = sy.sync_tudo(con)
        auditar(con, "sync.run", f"user:{u['id']}", user_id=u["id"], detail=res, ip=auth._ip(request))
        return res
    with _SYNC_LOCK:
        if _SYNC["running"]:
            return {"started": False, "running": True, "started_at": _SYNC["started_at"]}
        _SYNC.update(running=True, started_at=agora(), finished_at=None, result=None, by=u["id"])
    threading.Thread(target=_sync_thread, args=(u["id"], auth._ip(request)), daemon=True).start()
    return {"started": True, "running": True, "started_at": _SYNC["started_at"]}


@r.get("/sync")
def sync_status(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    return {**_SYNC, "logs": todos(con, "SELECT * FROM sync_logs ORDER BY id DESC LIMIT 12")}


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
def needs_attention(hidden: bool = False, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    return atencao.coletar(con, incluir_ocultos=hidden)


class OcultarIn(BaseModel):
    key: str
    reason: str = None
    level: str = None
    title: str = None


@r.post("/needs-attention/dismiss")
def attention_dismiss(dados: OcultarIn, request: Request, u=Depends(auth.exige("OPERATOR")),
                      con: sqlite3.Connection = Depends(get_db)):
    """Esconde um aviso. Não toca na tarefa, no envelope nem no e-mail de origem."""
    if not dados.key or ":" not in dados.key or len(dados.key) > 200:
        raise HTTPException(400, "Invalid key.")
    con.execute("""INSERT INTO attention_dismissals (key, level, title, reason, dismissed_by)
                   VALUES (?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET reason=excluded.reason,
                   dismissed_by=excluded.dismissed_by, dismissed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
                (dados.key, dados.level, (dados.title or "")[:200], (dados.reason or "")[:500] or None, u["id"]))
    auditar(con, "attention.dismiss", f"user:{u['id']}", user_id=u["id"], entity_type="attention", entity_id=dados.key,
            detail={"title": dados.title, "reason": dados.reason}, ip=auth._ip(request))
    return {"ok": True}


class RestaurarIn(BaseModel):
    key: str


@r.post("/needs-attention/restore")
def attention_restore(dados: RestaurarIn, request: Request, u=Depends(auth.exige("OPERATOR")),
                      con: sqlite3.Connection = Depends(get_db)):
    n = con.execute("DELETE FROM attention_dismissals WHERE key=?", (dados.key,)).rowcount
    if not n:
        raise HTTPException(404, "Nothing hidden with that key.")
    auditar(con, "attention.restore", f"user:{u['id']}", user_id=u["id"], entity_type="attention", entity_id=dados.key,
            ip=auth._ip(request))
    return {"ok": True}


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
          (SELECT COUNT(*) FROM tasks t WHERE t.client_id=c.id AND t.status='completed') AS done_tasks,
          (SELECT MAX(due_on) FROM tasks t WHERE t.client_id=c.id AND t.status='completed') AS last_service,
          (SELECT MIN(due_on) FROM tasks t WHERE t.client_id=c.id AND t.status='open' AND due_on>=date('now')) AS next_service,
          (SELECT status FROM waivers w WHERE w.client_id=c.id ORDER BY sent_at DESC LIMIT 1) AS waiver_status,
          (SELECT COUNT(*) FROM emails e WHERE e.client_id=c.id AND e.handled=0) AS emails_open,
          (SELECT MAX(synced_at) FROM tasks t WHERE t.client_id=c.id) AS last_activity
        FROM clients c LEFT JOIN client_stages s ON s.code=c.stage_code
        WHERE {' AND '.join(where)} ORDER BY MAX(COALESCE(next_service, ''), COALESCE(last_service, '')) DESC, COALESCE(c.pilot_name, c.name)""", p)
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
    if "status" in campos:
        campos["status_locked"] = 1                      # mudança à mão não é desfeita pela sincronia
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
def tasks(status: str = "open", project: str = None, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """status=open|completed|all. Espelho do quadro inteiro (menos Matt tasks)."""
    where, p = [], []
    if status != "all":
        where.append("t.status=?"); p.append(status)
    if project:
        where.append("t.project=?"); p.append(project)
    sql = "SELECT t.*, c.name AS client_name FROM tasks t LEFT JOIN clients c ON c.id=t.client_id"
    if where:
        sql += " WHERE " + " AND ".join(where)
    rows = todos(con, sql + " ORDER BY t.due_on IS NULL, t.due_on, t.title", p)
    for t in rows:
        t["links"] = _links(con, "task", t["id"])
    return rows


@r.get("/waivers")
def waivers(hidden: bool = False, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    rows = todos(con, "SELECT w.*, c.name AS client_name, c.pilot_name AS client_pilot FROM waivers w LEFT JOIN clients c ON c.id=w.client_id WHERE w.hidden=? ORDER BY CASE w.status WHEN 'autoresponded' THEN 0 WHEN 'delivered' THEN 1 WHEN 'sent' THEN 2 ELSE 3 END, w.sent_at DESC", (1 if hidden else 0,))
    for w in rows:
        w["links"] = _links(con, "waiver", w["id"])
    return rows


@r.get("/emails")
def emails(mailbox: str = None, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    sql = "SELECT e.*, c.name AS client_name FROM emails e LEFT JOIN clients c ON c.id=e.client_id"
    p = []
    if mailbox:
        sql += " WHERE e.mailbox=?"; p.append(mailbox)
    rows = todos(con, sql + " ORDER BY e.last_at DESC LIMIT 300", p)
    for e in rows:
        e["links"] = _links(con, "email", e["id"])
    return rows


class EmailIn(BaseModel):
    handled: bool


@r.patch("/emails/{eid}")
def email_patch(eid: int, dados: EmailIn, request: Request, u=Depends(auth.exige("OPERATOR")),
                con: sqlite3.Connection = Depends(get_db)):
    """Marca tratado/não tratado no espelho. Não mexe no Gmail."""
    if not um(con, "SELECT id FROM emails WHERE id=?", (eid,)):
        raise HTTPException(404, "Email not found.")
    con.execute("UPDATE emails SET handled=? WHERE id=?", (1 if dados.handled else 0, eid))
    auditar(con, "email.handled", f"user:{u['id']}", user_id=u["id"], entity_type="email", entity_id=eid,
            detail={"handled": dados.handled}, ip=auth._ip(request))
    return {"ok": True}


@r.get("/docusign/templates")
def docusign_templates(u=Depends(auth.usuario_atual)):
    """Modelos da conta DocuSign, ao vivo. Sem credencial devolve connected=false, nunca 500."""
    from command_center.providers import NaoConectado, chamar
    try:
        return {"connected": True, "templates": chamar("docusign", "docusign_templates")}
    except NaoConectado as e:
        return {"connected": False, "reason": str(e), "templates": []}
    except Exception as e:
        return {"connected": False, "reason": f"{type(e).__name__}: {str(e)[:200]}", "templates": []}


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


# ================================================================ Gmail
# Caixa de entrada por dentro: marcadores, corpo da thread ao vivo, mover
# (clique humano: aplica o marcador E tira da inbox), classificar com a IA.
from command_center.providers import NaoConectado, modulo, chamar  # noqa: E402
from command_center.providers import classificar  # noqa: E402


def _thread_id(con, eid):
    l = um(con, "SELECT external_id FROM entity_links WHERE entity_type='email' AND entity_id=? AND system='gmail'", (eid,))
    return l["external_id"] if l else None


@r.get("/gmail/labels")
def gmail_labels(mailbox: str = "urace", u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Marcadores reais da caixa + quantas threads da inbox espelhada têm cada um."""
    contagem = {}
    for e in todos(con, "SELECT labels, suggested_label FROM emails WHERE mailbox=? AND is_inbox=1", (mailbox,)):
        for l in json.loads(e["labels"] or "[]"):
            contagem[l] = contagem.get(l, 0) + 1
    try:
        nomes = chamar("gmail", "gmail_marcadores", conta=mailbox)
        return {"connected": True, "labels": [{"name": m["nome"], "id": m["id"], "type": m.get("tipo"), "inbox_count": contagem.get(m["nome"], 0)} for m in nomes]}
    except NaoConectado as e:
        return {"connected": False, "reason": str(e), "labels": [{"name": k, "id": None, "type": "user", "inbox_count": v} for k, v in sorted(contagem.items())]}
    except Exception as e:
        return {"connected": False, "reason": f"{type(e).__name__}: {str(e)[:200]}", "labels": []}


@r.get("/emails/{eid}/thread")
def email_thread(eid: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Corpo da thread, ao vivo do Gmail (não fica no banco)."""
    e = um(con, "SELECT * FROM emails WHERE id=?", (eid,))
    if not e:
        raise HTTPException(404, "Email not found.")
    tid = _thread_id(con, eid)
    if not tid:
        return {"connected": False, "reason": "thread sem vínculo com o Gmail", "messages": []}
    try:
        t = chamar("gmail", "gmail_thread", conta=e["mailbox"], thread_id=tid)
        return {"connected": True, "thread_id": tid, "messages": t.get("mensagens", [])}
    except NaoConectado as ex:
        return {"connected": False, "reason": str(ex), "messages": []}
    except Exception as ex:
        raise HTTPException(502, f"Gmail: {str(ex)[:300]}")


class MoverIn(BaseModel):
    label: str


@r.post("/emails/{eid}/move")
def email_move(eid: int, dados: MoverIn, request: Request, u=Depends(auth.exige("OPERATOR")),
               con: sqlite3.Connection = Depends(get_db)):
    """Clique humano: aplica o marcador e tira da caixa de entrada (decisão do dono, 04/09)."""
    e = um(con, "SELECT * FROM emails WHERE id=?", (eid,))
    if not e:
        raise HTTPException(404, "Email not found.")
    label = (dados.label or "").strip()
    if not label or label.upper() in ("INBOX", "TRASH", "SPAM", "UNREAD", "STARRED"):
        raise HTTPException(400, "Escolha um marcador de destino.")
    tid = _thread_id(con, eid)
    if not tid:
        raise HTTPException(409, "Thread sem vínculo com o Gmail.")
    try:
        res = modulo("gmail").mover_humano(e["mailbox"], tid, label)
    except NaoConectado as ex:
        raise HTTPException(503, f"Gmail não conectado: {ex}")
    except Exception as ex:
        raise HTTPException(502, str(ex)[:300])
    labels = [l for l in json.loads(e["labels"] or "[]") if l != "INBOX"]
    if label not in labels:
        labels.append(label)
    con.execute("UPDATE emails SET labels=?, is_inbox=0, handled=1, synced_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                (json.dumps(labels, ensure_ascii=False), eid))
    auditar(con, "email.move", f"user:{u['id']}", user_id=u["id"], entity_type="email", entity_id=eid,
            detail={"label": label, "thread": tid, "mailbox": e["mailbox"]}, ip=auth._ip(request))
    return {"ok": True, **res}


_CLASSIF = {"running": False, "started_at": None, "finished_at": None, "result": None}


def _classificar_thread(user_id, mailbox, ids):
    from command_center.api import ia
    con = conectar()
    try:
        saida = {"classificados": 0, "sem_marcador": 0, "erro": None}
        where = "mailbox=? AND is_inbox=1" + (" AND id IN (%s)" % ",".join("?" * len(ids)) if ids else " AND suggested_label IS NULL")
        emails = todos(con, f"SELECT * FROM emails WHERE {where}", (mailbox, *ids))
        if not emails:
            _CLASSIF["result"] = saida; return
        nomes = [m["nome"] for m in chamar("gmail", "gmail_marcadores", conta=mailbox)]
        nomes = [n for n in nomes if n.upper() not in classificar.SISTEMA and not n.startswith("CATEGORY_")]
        for i in range(0, len(emails), 25):
            lote = emails[i:i + 25]
            ok, texto, erro = ia.RUNNER(classificar.prompt_ia(lote, nomes, mailbox), f"agent:{ia.AGENTE}:classificar-{mailbox}")
            if not ok:
                saida["erro"] = erro; break
            res = classificar.parse_ia(texto, nomes)
            for e in lote:
                lab, motivo = res.get(e["id"], (None, "sem resposta da IA"))
                atualizar(con, "emails", e["id"], suggested_label=lab, suggested_reason=motivo, suggested_by="ia", suggested_at=agora())
                saida["classificados" if lab else "sem_marcador"] += 1
        auditar(con, "gmail.classify", f"user:{user_id}", user_id=user_id, detail={"mailbox": mailbox, **saida})
        _CLASSIF["result"] = saida
    except Exception as e:
        _CLASSIF["result"] = {"erro": f"{type(e).__name__}: {str(e)[:300]}"}
    finally:
        _CLASSIF["running"] = False; _CLASSIF["finished_at"] = agora(); con.close()


class ClassificarIn(BaseModel):
    mailbox: str = "urace"
    ids: list[int] = []


@r.post("/gmail/classify", status_code=202)
def gmail_classify(dados: ClassificarIn, u=Depends(auth.exige("OPERATOR"))):
    """Manda as threads sem sugestão (ou as escolhidas) para o agente classificar. Só sugere; mover é clique."""
    if _CLASSIF["running"]:
        return {"started": False, "running": True}
    _CLASSIF.update(running=True, started_at=agora(), finished_at=None, result=None)
    threading.Thread(target=_classificar_thread, args=(u["id"], dados.mailbox, dados.ids[:200]), daemon=True).start()
    return {"started": True, "running": True}


@r.get("/gmail/classify")
def gmail_classify_status(u=Depends(auth.usuario_atual)):
    return _CLASSIF


# ============================================================= DocuSign
def _envelope_id(con, wid):
    l = um(con, "SELECT external_id FROM entity_links WHERE entity_type='waiver' AND entity_id=? AND system='docusign'", (wid,))
    return l["external_id"] if l else None


@r.get("/waivers/{wid}/download")
def waiver_download(wid: int, request: Request, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """PDF assinado (documento + certificado), ao vivo do DocuSign."""
    from fastapi.responses import Response
    w = um(con, "SELECT * FROM waivers WHERE id=?", (wid,))
    if not w:
        raise HTTPException(404, "Waiver not found.")
    env = _envelope_id(con, wid)
    if not env:
        raise HTTPException(409, "Envelope sem vínculo com o DocuSign.")
    try:
        pdf = modulo("docusign").baixar_documento_humano(env)
    except NaoConectado as ex:
        raise HTTPException(503, f"DocuSign não conectado: {ex}")
    except Exception as ex:
        raise HTTPException(502, str(ex)[:300])
    auditar(con, "waiver.download", f"user:{u['id']}", user_id=u["id"], entity_type="waiver", entity_id=wid,
            detail={"envelope": env}, ip=auth._ip(request))
    nome = re.sub(r"[^A-Za-z0-9._-]+", "_", f"waiver-{w['signer_name'] or w['signer_email'] or wid}")[:80]
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nome}.pdf"', "Cache-Control": "no-store"})


class LixeiraIn(BaseModel):
    reason: str = None


@r.post("/waivers/{wid}/trash")
def waiver_trash(wid: int, dados: LixeiraIn, request: Request, u=Depends(auth.exige("OPERATOR")),
                 con: sqlite3.Connection = Depends(get_db)):
    """Lixeira: some do painel (restaurável) e, se o envelope está em aberto, é ANULADO no DocuSign.
    Envelope assinado é registro legal: só some do painel."""
    w = um(con, "SELECT * FROM waivers WHERE id=?", (wid,))
    if not w:
        raise HTTPException(404, "Waiver not found.")
    env = _envelope_id(con, wid)
    anulado = None
    if env and w["status"] in ("sent", "delivered", "autoresponded"):
        try:
            anulado = modulo("docusign").anular_humano(env, dados.reason or f"Anulado no Command Center por {u['name']}")
        except NaoConectado as ex:
            raise HTTPException(503, f"DocuSign não conectado: {ex}")
        except Exception as ex:
            raise HTTPException(502, str(ex)[:300])
    con.execute("UPDATE waivers SET hidden=1, status=CASE WHEN ? THEN 'voided' ELSE status END, synced_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                (1 if anulado and anulado.get("aplicado") else 0, wid))
    auditar(con, "waiver.trash", f"user:{u['id']}", user_id=u["id"], entity_type="waiver", entity_id=wid,
            detail={"envelope": env, "reason": dados.reason, "voided": bool(anulado and anulado.get("aplicado")), "status_antes": w["status"]}, ip=auth._ip(request))
    return {"ok": True, "hidden": True, "voided": bool(anulado and anulado.get("aplicado")),
            "note": "Assinada fica no DocuSign (registro legal); só saiu do painel." if w["status"] == "completed" else None}


@r.post("/waivers/{wid}/restore")
def waiver_restore(wid: int, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    if not um(con, "SELECT id FROM waivers WHERE id=? AND hidden=1", (wid,)):
        raise HTTPException(404, "Nothing hidden with that id.")
    con.execute("UPDATE waivers SET hidden=0 WHERE id=?", (wid,))
    auditar(con, "waiver.restore", f"user:{u['id']}", user_id=u["id"], entity_type="waiver", entity_id=wid, ip=auth._ip(request))
    return {"ok": True}


class ReenviarIn(BaseModel):
    email: str = None
    name: str = None


@r.post("/waivers/{wid}/resend")
def waiver_resend(wid: int, dados: ReenviarIn, request: Request, u=Depends(auth.exige("OPERATOR")),
                  con: sqlite3.Connection = Depends(get_db)):
    """Reenvia a notificação; com e-mail novo, corrige o signatário antes (e-mail devolvido)."""
    w = um(con, "SELECT * FROM waivers WHERE id=?", (wid,))
    if not w:
        raise HTTPException(404, "Waiver not found.")
    novo = (dados.email or "").strip().lower() or None
    if novo and ("@" not in novo or "." not in novo.split("@")[-1]):
        raise HTTPException(400, "E-mail inválido.")
    env = _envelope_id(con, wid)
    if not env:
        raise HTTPException(409, "Envelope sem vínculo com o DocuSign.")
    try:
        res = modulo("docusign").reenviar_humano(env, novo, dados.name)
    except NaoConectado as ex:
        raise HTTPException(503, f"DocuSign não conectado: {ex}")
    except Exception as ex:
        raise HTTPException(502, str(ex)[:300])
    if novo:
        con.execute("UPDATE waivers SET signer_email=?, status='sent', synced_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (novo, wid))
    auditar(con, "waiver.resend", f"user:{u['id']}", user_id=u["id"], entity_type="waiver", entity_id=wid,
            detail={"envelope": env, "new_email": novo}, ip=auth._ip(request))
    return {"ok": True, **res}


class VinculoIn(BaseModel):
    client_id: int = None   # null = desvincular


@r.post("/waivers/{wid}/link")
def waiver_link(wid: int, dados: VinculoIn, request: Request, u=Depends(auth.exige("OPERATOR")),
                con: sqlite3.Connection = Depends(get_db)):
    """Vínculo manual waiver ↔ cliente. A sincronia não sobrescreve vínculo humano."""
    if not um(con, "SELECT id FROM waivers WHERE id=?", (wid,)):
        raise HTTPException(404, "Waiver not found.")
    if dados.client_id is not None and not um(con, "SELECT id FROM clients WHERE id=?", (dados.client_id,)):
        raise HTTPException(404, "Client not found.")
    con.execute("UPDATE waivers SET client_id=?, link_by='human', link_reason=? WHERE id=?",
                (dados.client_id, f"vinculado à mão por {u['name']}" if dados.client_id else "desvinculado à mão", wid))
    auditar(con, "waiver.link", f"user:{u['id']}", user_id=u["id"], entity_type="waiver", entity_id=wid,
            detail={"client_id": dados.client_id}, ip=auth._ip(request))
    return {"ok": True}



# ============================================================ Clientes: duplicados, união, varredura
from command_center.providers import identidade  # noqa: E402


@r.get("/client-duplicates")
def clients_duplicates(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Pares que parecem a mesma pessoa. Decisão humana; a IA pode opinar."""
    return {"pairs": identidade.candidatos_duplicados(con),
            "merged": todos(con, "SELECT * FROM client_merges ORDER BY id DESC LIMIT 50")}


class UnirIn(BaseModel):
    keep_id: int
    drop_id: int
    reason: str = None


@r.post("/client-merge")
def clients_merge(dados: UnirIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    if dados.keep_id == dados.drop_id:
        raise HTTPException(400, "Same client.")
    if not um(con, "SELECT id FROM clients WHERE id=?", (dados.keep_id,)) or not um(con, "SELECT id FROM clients WHERE id=?", (dados.drop_id,)):
        raise HTTPException(404, "Client not found.")
    identidade.unir(con, dados.keep_id, dados.drop_id, f"user:{u['id']}", dados.reason or "unido à mão")
    auditar(con, "client.merge", f"user:{u['id']}", user_id=u["id"], entity_type="client", entity_id=dados.keep_id,
            detail={"drop_id": dados.drop_id, "reason": dados.reason}, ip=auth._ip(request))
    return {"ok": True}


_DUP_IA = {"running": False, "result": None, "finished_at": None}


def _duplicados_ia_thread(user_id):
    from command_center.api import ia
    con = conectar()
    try:
        pares = identidade.candidatos_duplicados(con)
        if not pares:
            _DUP_IA["result"] = {"pareceres": {}}; return
        linhas = [f"- par {i}: A=#{p['a']['id']} '{p['a']['pilot_name'] or p['a']['name']}' (resp. {p['a']['name']}, {p['a']['email'] or 'sem e-mail'}, {p['a']['phone'] or 'sem tel'}) × "
                  f"B=#{p['b']['id']} '{p['b']['pilot_name'] or p['b']['name']}' (resp. {p['b']['name']}, {p['b']['email'] or 'sem e-mail'}, {p['b']['phone'] or 'sem tel'})" for i, p in enumerate(pares)]
        prompt = ("TAREFA: para cada par abaixo, diga se é a MESMA pessoa/cliente da URACE. Consulte o Asana (asana_buscar / asana_tarefa) "
                  "para comparar descrição, e-mail, telefone e histórico das tarefas de cada nome antes de responder. Não altere nada em sistema nenhum. "
                  "RESPONDA APENAS JSON: {\"pares\":[{\"par\":<int>,\"mesma_pessoa\":true|false|null,\"confianca\":\"alta|media|baixa\",\"motivo\":\"<até 20 palavras>\"}]}\n" + "\n".join(linhas))
        ok, texto, erro = ia.RUNNER(prompt, f"agent:{ia.AGENTE}:duplicados")
        if not ok:
            _DUP_IA["result"] = {"erro": erro}; return
        m = re.search(r"\{.*\}", texto or "", re.S)
        dados = json.loads(m.group(0)) if m else {}
        pareceres = {}
        for it in dados.get("pares", []):
            try:
                i = int(it.get("par"))
            except (TypeError, ValueError):
                continue
            if 0 <= i < len(pares):
                pareceres[f"{pares[i]['a']['id']}-{pares[i]['b']['id']}"] = {"mesma_pessoa": it.get("mesma_pessoa"), "confianca": it.get("confianca"), "motivo": (it.get("motivo") or "")[:200]}
        auditar(con, "client.duplicates_ai", f"user:{user_id}", user_id=user_id, detail={"pares": len(pares), "pareceres": len(pareceres)})
        _DUP_IA["result"] = {"pareceres": pareceres}
    except Exception as e:
        _DUP_IA["result"] = {"erro": f"{type(e).__name__}: {str(e)[:300]}"}
    finally:
        _DUP_IA["running"] = False; _DUP_IA["finished_at"] = agora(); con.close()


@r.post("/client-duplicates/ai", status_code=202)
def clients_duplicates_ai(u=Depends(auth.exige("OPERATOR"))):
    if _DUP_IA["running"]:
        return {"started": False, "running": True}
    _DUP_IA.update(running=True, result=None, finished_at=None)
    threading.Thread(target=_duplicados_ia_thread, args=(u["id"],), daemon=True).start()
    return {"started": True, "running": True}


@r.get("/client-duplicates/ai")
def clients_duplicates_ai_status(u=Depends(auth.usuario_atual)):
    return _DUP_IA


def _varrer_cliente(con, c):
    """Gmail (as duas caixas, fora da inbox também) e DocuSign para UM cliente. Só leitura + espelho."""
    saida = {"gmail": 0, "docusign": 0, "avisos": []}
    email = (c["email"] or "").lower()
    nomes = [n for n in (c["pilot_name"], c["name"]) if n]
    for conta in ("urace", "support"):
        consultas = []
        if email:
            consultas.append(f"from:{email} OR to:{email}")
        if conta == "support" and nomes:                        # acessos do DocuSign chegam no support@
            consultas.append(" OR ".join(f'"{n}"' for n in nomes[:2]))
        for q in consultas:
            try:
                r = chamar("gmail", "gmail_buscar", conta=conta, consulta=q, so_inbox=False, maximo=50)
            except NaoConectado as e:
                saida["avisos"].append(f"gmail: {e}"); break
            except Exception as e:
                if "não configurada" in str(e):
                    break
                saida["avisos"].append(f"gmail {conta}: {str(e)[:120]}"); break
            for t in r.get("threads", []):
                eid = um(con, "SELECT entity_id FROM entity_links WHERE system='gmail' AND external_id=? AND entity_type='email'", (t["thread_id"],))
                marcadores = t.get("marcadores") or []
                campos = dict(client_id=c["id"], mailbox=conta, subject=t.get("assunto"), sender=(t.get("de") or "")[:200],
                              last_at=sy._data_iso(t.get("data")), snippet=(t.get("snippet") or "")[:300], messages=t.get("mensagens"),
                              is_inbox=1 if "INBOX" in marcadores else 0, labels=json.dumps(marcadores, ensure_ascii=False), synced_at=agora())
                if eid:
                    con.execute("UPDATE emails SET client_id=COALESCE(client_id, ?), synced_at=? WHERE id=?", (c["id"], agora(), eid["entity_id"]))
                else:
                    from command_center.db import inserir
                    nid = inserir(con, "emails", **campos)
                    con.execute("INSERT OR IGNORE INTO entity_links (entity_type, entity_id, system, external_id, deep_link) VALUES ('email',?,?,?,?)",
                                (nid, "gmail", t["thread_id"], f"https://mail.google.com/mail/u/{0 if conta == 'urace' else 1}/#all/{t['thread_id']}"))
                saida["gmail"] += 1
    if email:
        try:
            r = chamar("docusign", "docusign_waivers_de", email=email)
            for grupo in ("waiver_valida", "em_aberto", "historico"):
                for e in r.get(grupo) or []:
                    w = um(con, "SELECT w.id, w.client_id, w.link_by FROM waivers w JOIN entity_links l ON l.entity_type='waiver' AND l.entity_id=w.id WHERE l.system='docusign' AND l.external_id=?", (e["envelopeId"],))
                    if w and not w["client_id"]:
                        con.execute("UPDATE waivers SET client_id=?, link_by='sync', link_reason=? WHERE id=?", (c["id"], f"varredura: e-mail {email}", w["id"]))
                        saida["docusign"] += 1
        except NaoConectado as e:
            saida["avisos"].append(f"docusign: {e}")
        except Exception as e:
            saida["avisos"].append(f"docusign: {str(e)[:120]}")
    con.execute("UPDATE clients SET scanned_at=? WHERE id=?", (agora(), c["id"]))
    return saida


@r.post("/clients/{cid}/scan")
def client_scan(cid: int, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """Varre Gmail e DocuSign atrás deste cliente e liga o que achar ao card."""
    c = um(con, "SELECT * FROM clients WHERE id=?", (cid,))
    if not c:
        raise HTTPException(404, "Client not found.")
    res = _varrer_cliente(con, c)
    auditar(con, "client.scan", f"user:{u['id']}", user_id=u["id"], entity_type="client", entity_id=cid, detail=res, ip=auth._ip(request))
    return res


_SCAN = {"running": False, "done": 0, "total": 0, "result": None, "finished_at": None}


def _scan_all_thread(user_id):
    con = conectar()
    try:
        cs = todos(con, "SELECT * FROM clients WHERE status='ACTIVE' ORDER BY last_service_at DESC")
        _SCAN.update(total=len(cs), done=0)
        tot = {"gmail": 0, "docusign": 0}
        for c in cs:
            r = _varrer_cliente(con, c)
            tot["gmail"] += r["gmail"]; tot["docusign"] += r["docusign"]
            _SCAN["done"] += 1
            if any(a.startswith(("gmail:", "docusign:")) and "não conectado" in a.lower() for a in r["avisos"]):
                break
        auditar(con, "client.scan_all", f"user:{user_id}", user_id=user_id, detail=tot)
        _SCAN["result"] = tot
    except Exception as e:
        _SCAN["result"] = {"erro": f"{type(e).__name__}: {str(e)[:300]}"}
    finally:
        _SCAN["running"] = False; _SCAN["finished_at"] = agora(); con.close()


@r.post("/client-scan-all", status_code=202)
def clients_scan_all(u=Depends(auth.exige("OPERATOR"))):
    if _SCAN["running"]:
        return {"started": False, **_SCAN}
    _SCAN.update(running=True, done=0, total=0, result=None, finished_at=None)
    threading.Thread(target=_scan_all_thread, args=(u["id"],), daemon=True).start()
    return {"started": True, **_SCAN}


@r.get("/client-scan-all")
def clients_scan_all_status(u=Depends(auth.usuario_atual)):
    return _SCAN


# ================================================================ Asana: detalhe ao vivo
@r.get("/tasks/{tid}/detail")
def task_detail(tid: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Descrição, campos, subtarefas, anexos e comentários — ao vivo do Asana. Só leitura."""
    t = um(con, "SELECT * FROM tasks WHERE id=?", (tid,))
    if not t:
        raise HTTPException(404, "Task not found.")
    l = um(con, "SELECT external_id FROM entity_links WHERE entity_type='task' AND entity_id=? AND system='asana'", (tid,))
    if not l:
        return {"connected": False, "reason": "tarefa sem vínculo com o Asana"}
    gid = l["external_id"]
    try:
        full = chamar("asana", "asana_tarefa", gid=gid)
        saida = {"connected": True, "gid": gid, "task": full}
        for chave, ferramenta in (("comments", "asana_comentarios"), ("attachments", "asana_anexos")):
            try:
                saida[chave] = chamar("asana", ferramenta, gid=gid)
            except Exception as e:
                saida[chave] = []; saida[chave + "_error"] = str(e)[:200]
        return saida
    except NaoConectado as e:
        return {"connected": False, "reason": str(e)}
    except Exception as e:
        raise HTTPException(502, f"Asana: {str(e)[:300]}")

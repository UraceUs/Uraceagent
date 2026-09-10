"""Rotas de dados da Fase 1: dashboard, atenção, clientes, busca,
integrações, políticas. Toda rota exige sessão; escrita exige papel.
"""
import json
import os
import re
import sqlite3
import threading
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from command_center.api import atencao, auth
from command_center.db import agora, auditar, conectar, get_db, inserir, todos, um
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
    """Sonda cada sistema com UMA chamada real e grava o estado. A rotina
    automática só roda de manhã e à noite (agenda.py, decisão do dono 09/09)."""
    from command_center.api import agenda
    saida = agenda.sondar(con, por=f"user:{u['id']}")
    auditar(con, "integrations.check", f"user:{u['id']}", user_id=u["id"], ip=auth._ip(request))
    return saida


_SYNC = {"running": False, "started_at": None, "finished_at": None, "result": None, "by": None, "stage": None, "stage_started_at": None}
_SYNC_LOCK = threading.Lock()


def _sync_thread(user_id, ip):
    from command_center.api import motor
    con = conectar()
    try:
        res = {}
        # uma etapa por sistema, com o nome visível em GET /sync (a tela mostra "sincronizando: asana")
        for nome, fn in (("cerebro", sy.sync_cerebro), ("asana", sy.sync_asana), ("docusign", sy.sync_docusign),
                         ("gmail", sy.sync_gmail), ("quickbooks", sy.sync_qbo)):
            _SYNC["stage"] = nome; _SYNC["stage_started_at"] = agora()
            try:
                res[nome] = fn(con)
            except Exception as e:                    # um sistema com erro não derruba os outros
                res[nome] = {"ok": False, "motivo": f"{type(e).__name__}: {str(e)[:300]}"}
            if isinstance(res[nome], dict) and res[nome].get("ok") is False and nome != "cerebro":
                try:                                  # caiu no meio do uso: aí sim re-sonda (só ele)
                    from command_center.api import agenda
                    agenda.sondar_apos_falha(con, nome, str(res[nome].get("motivo") or ""))
                except Exception:
                    pass
        _SYNC["stage"] = "eventos"
        auditar(con, "sync.run", f"user:{user_id}", user_id=user_id, detail=res, ip=ip)
        res["eventos_disparados"] = motor.processar_eventos(con, user_id)
        _SYNC["result"] = res
    except Exception as e:                        # nunca deixa a flag presa em "running"
        _SYNC["result"] = {"ok": False, "motivo": f"{type(e).__name__}: {str(e)[:300]}"}
    finally:
        _SYNC["running"] = False
        _SYNC["finished_at"] = agora()
        _SYNC["stage"] = None
        con.close()


@r.post("/sync", status_code=202)
def sync(request: Request, wait: bool = False, u=Depends(auth.exige("OPERATOR")),
         con: sqlite3.Connection = Depends(get_db)):
    """Atualiza os espelhos a partir das fontes reais. Só leitura nos sistemas.

    Roda em segundo plano (o histórico do Asana pode levar minutos); o
    estado sai em GET /sync. wait=1 espera terminar (testes e scripts).
    """
    if wait:
        from command_center.api import motor
        res = sy.sync_tudo(con)
        auditar(con, "sync.run", f"user:{u['id']}", user_id=u["id"], detail=res, ip=auth._ip(request))
        res["eventos_disparados"] = motor.processar_eventos(con, u["id"])
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
    reason: str | None = None
    level: str | None = None
    title: str | None = None


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
def clients(status: str | None = None, q: str | None = None, vip: bool | None = None, pro: bool | None = None,
            u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    where, p = ["1=1"], []
    if status:
        where.append("c.status=?"); p.append(status.upper())
    if vip is not None:
        where.append("c.vip=?"); p.append(1 if vip else 0)
    if pro is not None:
        where.append("c.pro_driver=?"); p.append(1 if pro else 0)
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
    # cada item da linha do tempo leva o SEU link (Asana da tarefa, DocuSign do envelope, Gmail da thread, QBO da invoice)
    def _usd(v):
        return "?" if v is None else f"${v:,.2f}"

    def _dbr(d):
        return f"{d[8:10]}/{d[5:7]}/{d[:4]}" if d and len(d) >= 10 else (d or "")
    tl = []
    for t in tarefas:
        tl.append({"at": t["due_on"], "kind": "SERVICE", "title": t["title"], "status": t["status"], "entity": {"type": "task", "id": t["id"]},
                   "detail": f"{t['section'] or ''}" + (f" · subtarefas {t['subtasks_done'] or 0}/{t['subtasks_total']}" if t.get("subtasks_total") else ""), "links": t["links"]})
    for w in waivers:
        tl.append({"at": (w["sent_at"] or "")[:10], "kind": "WAIVER_SENT", "title": f"Waiver {w['template']} → {w['signer_name']}", "status": w["status"], "entity": {"type": "waiver", "id": w["id"]},
                   "detail": w.get("signer_email"), "links": w["links"]})
        if w["completed_at"]:
            tl.append({"at": w["completed_at"][:10], "kind": "WAIVER_SIGNED", "title": f"Waiver assinada por {w['signer_name']}", "status": "completed", "entity": {"type": "waiver", "id": w["id"]},
                       "detail": f"vale até {_dbr(w['expires_at'])}" if w.get("expires_at") else None, "links": w["links"]})
    for e in emails:
        tl.append({"at": (e["last_at"] or "")[:10], "kind": "EMAIL", "title": e["subject"], "status": "handled" if e["handled"] else "open", "entity": {"type": "email", "id": e["id"]},
                   "detail": f"{e['mailbox']}@ · {e.get('sender') or ''}", "links": e["links"]})
    for a in acoes:
        tl.append({"at": a["created_at"][:10], "kind": "AI_ACTION", "title": a["action"], "status": a["status"], "entity": {"type": "ai_action", "id": a["id"]},
                   "detail": (a.get("reason") or "")[:120], "links": []})
    for i in (invoices or []):
        tl.append({"at": i["issued_on"] or (i["due_on"] or ""), "kind": "INVOICE", "title": f"Invoice {i['doc_number'] or ''} · {_usd(i['amount'])}", "status": i["status"] or "?",
                   "entity": {"type": "invoice", "id": i["id"]}, "detail": (f"saldo {_usd(i['balance'])}" if i.get("balance") else "paga") + (f" · vence {_dbr(i['due_on'])}" if i.get("due_on") else "") + (f" · {i['memo']}" if i.get("memo") else ""), "links": _links(con, "invoice", i["id"])})
    tl.sort(key=lambda x: x["at"] or "", reverse=True)
    ultimo = next((t for t in tarefas if t["status"] == "completed" and t["due_on"]), None)
    return {"client": c, "links": _links(con, "client", cid), "tasks": tarefas, "waivers": waivers,
            "emails": emails, "invoices": invoices, "ai_actions": acoes, "timeline": tl, "last_service": ultimo,
            "open_balance": (sum((i["balance"] or 0) for i in invoices) if invoices else None),
            "stages": todos(con, "SELECT code, label FROM client_stages ORDER BY ord")}


class ClienteIn(BaseModel):
    status: str | None = None
    stage_code: str | None = None
    notes: str | None = None
    vip: bool | None = None
    monthly_plan: str | None = None
    monthly_note: str | None = None


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
def tasks(status: str = "open", project: str | None = None, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
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
def emails(mailbox: str | None = None, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
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
    con.execute("UPDATE emails SET handled=?, handled_by=?, handled_reason=NULL WHERE id=?", (1 if dados.handled else 0, f"user:{u['id']}" if dados.handled else None, eid))
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
    note: str | None = None


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
        return {"connected": False, "reason": str(e), "labels": [{"name": k, "id": None, "type": "user", "inbox_count": v} for k, v in sorted(contagem.items())
                                                                 if k.upper() not in classificar.SISTEMA and not k.startswith("CATEGORY_")]}
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


@r.get("/emails/{eid}/html/{message_id}")
def email_html(eid: int, message_id: str, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """A mensagem como o Gmail mostra (HTML + imagens inline), limpa e com CSP
    própria, para o iframe com sandbox do painel. Sem HTML, cai para o texto."""
    from fastapi.responses import HTMLResponse
    from command_center.api import html_seguro
    e = um(con, "SELECT * FROM emails WHERE id=?", (eid,))
    if not e or not re.fullmatch(r"[A-Za-z0-9_-]{4,40}", message_id or ""):
        raise HTTPException(404, "Email not found.")
    try:
        r_ = modulo("gmail").mensagem_html(e["mailbox"], message_id)
    except NaoConectado as ex:
        raise HTTPException(503, f"Gmail não conectado: {ex}")
    except Exception as ex:
        raise HTTPException(502, f"Gmail: {str(ex)[:300]}")
    html = r_.get("html") or ("<pre style='white-space:pre-wrap'>%s</pre>" % (r_.get("texto") or "").replace("&", "&amp;").replace("<", "&lt;"))
    resp = HTMLResponse(html_seguro.pagina(html, r_.get("assunto") or e["subject"] or ""))
    resp.headers["Content-Security-Policy"] = html_seguro.CSP
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    return resp


class RotularIn(BaseModel):
    add: list[str] = []


@r.post("/emails/{eid}/labels")
def email_labels(eid: int, dados: RotularIn, request: Request, u=Depends(auth.exige("OPERATOR")),
                 con: sqlite3.Connection = Depends(get_db)):
    """Clique humano: ADICIONA marcadores (não tira da inbox). Mover é o clique no marcador."""
    e = um(con, "SELECT * FROM emails WHERE id=?", (eid,))
    if not e:
        raise HTTPException(404, "Email not found.")
    add = [l.strip() for l in dados.add if l and l.strip() and l.strip().upper() not in ("INBOX", "TRASH", "SPAM", "UNREAD", "STARRED")]
    if not add:
        raise HTTPException(400, "Escolha um marcador.")
    tid = _thread_id(con, eid)
    if not tid:
        raise HTTPException(409, "Thread sem vínculo com o Gmail.")
    try:
        res = modulo("gmail").rotular_humano(e["mailbox"], tid, add)
    except NaoConectado as ex:
        raise HTTPException(503, f"Gmail não conectado: {ex}")
    except Exception as ex:
        raise HTTPException(502, str(ex)[:300])
    labels = json.loads(e["labels"] or "[]")
    for l in add:
        if l not in labels:
            labels.append(l)
    con.execute("UPDATE emails SET labels=?, synced_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (json.dumps(labels, ensure_ascii=False), eid))
    auditar(con, "email.label", f"user:{u['id']}", user_id=u["id"], entity_type="email", entity_id=eid,
            detail={"add": add, "thread": tid, "mailbox": e["mailbox"]}, ip=auth._ip(request))
    return {"ok": True, "labels": labels, **res}


_TRIAGEM = {"running": False, "started_at": None, "finished_at": None, "result": None}


def _triagem_thread(user_id, mailboxes):
    from command_center.api import agenda, ia, motor
    from command_center.providers import triagem
    con = conectar()
    try:
        with ia._PARALELO:
            _TRIAGEM["result"] = triagem.rodar(con, ia.RUNNER, f"agent:{ia.AGENTE}:triagem-{date.today().isoformat()}",
                                               mailboxes=mailboxes, aprendizados=motor.aprendizados(con), por=f"user:{user_id}")
        _ = agenda   # a rotina automática usa o mesmo caminho
    except Exception as e:
        _TRIAGEM["result"] = {"erros": [f"{type(e).__name__}: {str(e)[:300]}"]}
    finally:
        _TRIAGEM["running"] = False; _TRIAGEM["finished_at"] = agora(); con.close()


class TriagemIn(BaseModel):
    mailbox: str | None = None


@r.post("/gmail/triage", status_code=202)
def gmail_triage(dados: TriagemIn, request: Request, u=Depends(auth.exige("OPERATOR"))):
    """Triagem agora (a automática roda 07:00, 13:00 e 21:00): a IA lê cada thread,
    aplica os marcadores e move para o principal. Só ficam na inbox as que ela não decidiu."""
    if _TRIAGEM["running"]:
        return {"started": False, "running": True}
    from command_center.providers import triagem
    caixas = tuple([dados.mailbox]) if dados.mailbox in triagem.CAIXAS else triagem.CAIXAS
    _TRIAGEM.update(running=True, started_at=agora(), finished_at=None, result=None)
    threading.Thread(target=_triagem_thread, args=(u["id"], caixas), daemon=True).start()
    return {"started": True, "running": True}


@r.get("/gmail/triage")
def gmail_triage_status(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    regra = um(con, "SELECT enabled, schedule, last_run_at, last_result FROM automation_rules WHERE name='gmail_triagem'")
    return {**_TRIAGEM, "rule": regra}


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
    con.execute("UPDATE emails SET labels=?, is_inbox=0, handled=1, handled_by=?, handled_reason=?, synced_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                (json.dumps(labels, ensure_ascii=False), f"user:{u['id']}", f"movido para {label}", eid))
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
    """PDF assinado (documento + certificado). Baixa do DocuSign na primeira vez e guarda
    em ~/.urace/waivers: depois o card do cliente abre o arquivo guardado, e é o mesmo
    arquivo que vai anexado na tarefa do Asana."""
    from fastapi.responses import Response
    from command_center.api import motor
    w = um(con, "SELECT * FROM waivers WHERE id=?", (wid,))
    if not w:
        raise HTTPException(404, "Waiver not found.")
    env = _envelope_id(con, wid)
    if not env:
        raise HTTPException(409, "Envelope sem vínculo com o DocuSign.")
    try:
        try:
            with open(motor.pdf_da_waiver(con, w), "rb") as f:
                pdf = f.read()
        except OSError:                                  # sem lugar para guardar: pega ao vivo
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
    reason: str | None = None


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
    email: str | None = None
    name: str | None = None


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
    client_id: int | None = None   # null = desvincular


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


_FULL = {"running": False, "started_at": None, "finished_at": None, "stage": None, "done": 0, "total": None, "result": None, "by": None}


def _full_thread(user_id):
    con = conectar()
    try:
        def prog(d):
            _FULL.update(d)
        res = sy.sync_asana_completo(con, prog)
        con.commit()
        _FULL["result"] = res
        auditar(con, "sync.full", f"user:{user_id}", user_id=user_id, detail=res)
    except Exception as e:
        _FULL["result"] = {"ok": False, "motivo": f"{type(e).__name__}: {str(e)[:300]}"}
    finally:
        _FULL["running"] = False; _FULL["finished_at"] = agora()
        with _SYNC_LOCK:
            _SYNC["running"] = False
        con.close()


@r.post("/sync/full", status_code=202)
def sync_full(u=Depends(auth.exige("MANAGER"))):
    """Puxa o histórico COMPLETO do quadro U-RACE (todas as colunas, concluídas incluídas,
    sem teto) e liga cada serviço à pessoa certa. Segura a sincronia normal enquanto roda."""
    with _SYNC_LOCK:
        if _FULL["running"] or _SYNC["running"]:
            return {"started": False, **_FULL, "sync_running": _SYNC["running"]}
        _SYNC.update(running=True, started_at=agora(), finished_at=None, result=None, by=u["id"], stage="histórico completo do Asana")
    _FULL.update(running=True, started_at=agora(), finished_at=None, stage="listando", done=0, total=None, result=None, by=u["id"])
    threading.Thread(target=_full_thread, args=(u["id"],), daemon=True).start()
    return {"started": True, **_FULL}


@r.get("/sync/full")
def sync_full_status(u=Depends(auth.usuario_atual)):
    return _FULL


@r.get("/clients/{cid}/duplicates")
def client_duplicates_of(cid: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Quem parece ser a mesma pessoa que este cliente (para o botão 'Unir com…')."""
    if not um(con, "SELECT id FROM clients WHERE id=?", (cid,)):
        raise HTTPException(404, "Client not found.")
    pares = identidade.candidatos_duplicados(con, para=cid)
    return [dict(**(p["b"] if p["a"]["id"] == cid else p["a"]), why=p["why"]) for p in pares]


@r.get("/client-duplicates")
def clients_duplicates(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Pares que parecem a mesma pessoa. Decisão humana; a IA pode opinar."""
    return {"pairs": identidade.candidatos_duplicados(con),
            "merged": todos(con, "SELECT * FROM client_merges ORDER BY id DESC LIMIT 50")}


class UnirIn(BaseModel):
    keep_id: int
    drop_id: int
    reason: str | None = None


@r.post("/client-merge")
def clients_merge(dados: UnirIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    if dados.keep_id == dados.drop_id:
        raise HTTPException(400, "Same client.")
    if not um(con, "SELECT id FROM clients WHERE id=?", (dados.keep_id,)) or not um(con, "SELECT id FROM clients WHERE id=?", (dados.drop_id,)):
        raise HTTPException(404, "Client not found.")
    antes = {t: um(con, f"SELECT COUNT(*) AS n FROM {t} WHERE client_id=?", (dados.drop_id,))["n"] for t in ("tasks", "waivers", "emails", "invoices")}
    identidade.unir(con, dados.keep_id, dados.drop_id, f"user:{u['id']}", dados.reason or "unido à mão")
    identidade.recalcular_status(con)
    auditar(con, "client.merge", f"user:{u['id']}", user_id=u["id"], entity_type="client", entity_id=dados.keep_id,
            detail={"drop_id": dados.drop_id, "reason": dados.reason, "moved": antes}, ip=auth._ip(request))
    return {"ok": True, "moved": antes}


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
                na_inbox = "INBOX" in marcadores
                campos = dict(client_id=c["id"], mailbox=conta, subject=t.get("assunto"), sender=(t.get("de") or "")[:200],
                              last_at=sy._data_iso(t.get("data")), snippet=(t.get("snippet") or "")[:300], messages=t.get("mensagens"),
                              is_inbox=1 if na_inbox else 0, labels=json.dumps(marcadores, ensure_ascii=False), synced_at=agora(),
                              # histórico fora da inbox é contexto do cliente, não trabalho pendente
                              handled=0 if na_inbox else 1, handled_by=None if na_inbox else "auto",
                              handled_reason=None if na_inbox else "histórico trazido pela varredura (fora da inbox)")
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
    saida["contratos"] = _contratos_do_docusign(con, c)
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



# ============================================================ IA que age: instrução, memória, eventos, regras
from command_center.api import motor  # noqa: E402


class InstruirIn(BaseModel):
    key: str
    text: str
    remember: bool = True
    title: str | None = None
    why: str | None = None
    client_id: int | None = None
    entity_type: str | None = None
    entity_id: str | None = None


@r.post("/needs-attention/instruct", status_code=202)
def attention_instruct(dados: InstruirIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """Balão do item: manda a instrução para o agente com o contexto do item; com remember, vira memória."""
    texto = (dados.text or "").strip()
    if not texto or len(texto) > 4000:
        raise HTTPException(400, "Escreva a instrução (até 4000 caracteres).")
    item = {"title": dados.title, "why": dados.why, "client_id": dados.client_id,
            "entity": {"type": dados.entity_type, "id": dados.entity_id}}
    cid = motor.instruir(con, u["id"], dados.key, texto, item, dados.remember)
    return {"command_id": cid, "remembered": bool(dados.remember)}


@r.get("/ai/learnings")
def learnings(all: bool = False, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    sql = "SELECT l.*, us.name AS created_by_name FROM ai_learnings l LEFT JOIN users us ON us.id=l.created_by"
    if not all:
        sql += " WHERE l.active=1"
    return todos(con, sql + " ORDER BY l.id DESC LIMIT 300")


class AprenderIn(BaseModel):
    text: str
    client_id: int | None = None
    entity_type: str | None = None


@r.post("/ai/learnings", status_code=201)
def learning_create(dados: AprenderIn, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    if not (dados.text or "").strip():
        raise HTTPException(400, "Texto vazio.")
    return {"id": motor.aprender(con, dados.text, u["id"], dados.client_id, dados.entity_type)}


@r.post("/ai/learnings/{lid}/toggle")
def learning_toggle(lid: int, request: Request, u=Depends(auth.exige("MANAGER")), con: sqlite3.Connection = Depends(get_db)):
    l = um(con, "SELECT * FROM ai_learnings WHERE id=?", (lid,))
    if not l:
        raise HTTPException(404, "Not found.")
    con.execute("UPDATE ai_learnings SET active=? WHERE id=?", (0 if l["active"] else 1, lid))
    auditar(con, "ai.learning.toggle", f"user:{u['id']}", user_id=u["id"], entity_type="ai_learning", entity_id=lid, detail={"active": not l["active"]}, ip=auth._ip(request))
    return {"ok": True, "active": not l["active"]}


@r.get("/ai/events")
def ai_events(limit: int = 100, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    return todos(con, """SELECT e.*, c.name AS client_name, c.pilot_name, cmd.status AS command_status,
                                (SELECT COUNT(*) FROM ai_actions a WHERE a.command_id=e.command_id) AS actions
                         FROM ai_events e LEFT JOIN clients c ON c.id=e.client_id LEFT JOIN ai_commands cmd ON cmd.id=e.command_id
                         ORDER BY e.id DESC LIMIT ?""", (max(1, min(limit, 500)),))


@r.post("/ai/events/process", status_code=202)
def ai_events_process(u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    return {"disparados": motor.processar_eventos(con, u["id"])}


@r.get("/automation/rules")
def automation_rules(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    return todos(con, "SELECT * FROM automation_rules ORDER BY id")


class RegraIn(BaseModel):
    enabled: bool


@r.put("/automation/rules/{name}")
def automation_rule_put(name: str, dados: RegraIn, request: Request, u=Depends(auth.exige("ADMIN")), con: sqlite3.Connection = Depends(get_db)):
    if not um(con, "SELECT id FROM automation_rules WHERE name=?", (name,)):
        raise HTTPException(404, "Unknown rule.")
    con.execute("UPDATE automation_rules SET enabled=? WHERE name=?", (1 if dados.enabled else 0, name))
    auditar(con, "automation.rule", f"user:{u['id']}", user_id=u["id"], entity_type="automation_rule", entity_id=name, detail={"enabled": dados.enabled}, ip=auth._ip(request))
    return {"ok": True}



# ============================================================ QuickBooks (financeiro: MANAGER+)
@r.get("/invoices")
def invoices(status: str = None, u=Depends(auth.exige("MANAGER")), con: sqlite3.Connection = Depends(get_db)):
    sql = "SELECT i.*, c.name AS client_name, c.pilot_name FROM invoices i LEFT JOIN clients c ON c.id=i.client_id"
    p = []
    if status:
        sql += " WHERE i.status=?"; p.append(status)
    rows = todos(con, sql + " ORDER BY CASE i.status WHEN 'overdue' THEN 0 WHEN 'open' THEN 1 WHEN 'sent' THEN 1 ELSE 2 END, i.due_on DESC LIMIT 500", p)
    for i in rows:
        i["links"] = _links(con, "invoice", i["id"])
    return rows


@r.get("/qbo/summary")
def qbo_summary(u=Depends(auth.exige("MANAGER")), con: sqlite3.Connection = Depends(get_db)):
    from datetime import date as _d
    hoje = _d.today().isoformat()
    n = lambda sql, p=(): (um(con, sql, p) or {})
    aberto = n("SELECT COUNT(*) AS c, COALESCE(SUM(balance),0) AS t FROM invoices WHERE status IN ('open','sent','overdue')")
    vencido = n("SELECT COUNT(*) AS c, COALESCE(SUM(balance),0) AS t FROM invoices WHERE status='overdue'")
    pagas30 = n("SELECT COUNT(*) AS c, COALESCE(SUM(amount),0) AS t FROM invoices WHERE status='paid' AND issued_on >= date(?, '-30 days')", (hoje,))
    integ = um(con, "SELECT status, detail, last_success_at FROM integrations WHERE system='quickbooks'")
    return {"connected": bool(integ and integ["status"] == "CONNECTED"), "integration": integ,
            "open": {"count": aberto["c"], "total": round(aberto["t"], 2)}, "overdue": {"count": vencido["c"], "total": round(vencido["t"], 2)},
            "paid_30d": {"count": pagas30["c"], "total": round(pagas30["t"], 2)},
            "top_debtors": todos(con, """SELECT c.id, c.name, c.pilot_name, SUM(i.balance) AS balance, COUNT(*) AS n FROM invoices i JOIN clients c ON c.id=i.client_id
                                         WHERE i.status IN ('open','sent','overdue') GROUP BY c.id ORDER BY balance DESC LIMIT 8""")}



# ============================================================ Criação manual pelo painel (portas humanas)
from command_center.providers.sync import PROJETO_URACE, SECOES_DIAS, _upsert_cliente, _liga, ASANA_LINK  # noqa: E402

MODELO_SESSAO = os.environ.get("ASANA_MODELO_SESSAO", "1208702559561159")
RATE_CARD_ID = "160efDlmavKKGbtGfJKCTOV_3Q9JEO3Lc6xA1mEMMNyo"


class ClienteNovoIn(BaseModel):
    name: str
    pilot_name: str | None = None
    pilot_dob: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    notes: str | None = None
    vip: bool = False


@r.post("/clients", status_code=201)
def client_create(dados: ClienteNovoIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """Cliente criado à mão no painel. Se já existir (e-mail, telefone, nome), devolve o existente em vez de duplicar."""
    nome = (dados.name or "").strip()
    if len(nome) < 2:
        raise HTTPException(400, "Nome do responsável é obrigatório.")
    email = (dados.email or "").strip().lower() or None
    if email and "@" not in email:
        raise HTTPException(400, "E-mail inválido.")
    cid, novo = _upsert_cliente(con, nome, email, (dados.phone or "").strip() or None, (dados.pilot_name or "").strip() or None,
                                (dados.pilot_dob or "").strip() or None, True if dados.vip else None, source="manual")
    if dados.company or dados.notes:
        con.execute("UPDATE clients SET company=COALESCE(?, company), notes=COALESCE(?, notes) WHERE id=?", (dados.company, dados.notes, cid))
    if novo:
        con.execute("UPDATE clients SET status='NEW' WHERE id=?", (cid,))
    auditar(con, "client.create" if novo else "client.match", f"user:{u['id']}", user_id=u["id"], entity_type="client", entity_id=cid,
            detail={"name": nome, "email": email, "novo": novo}, ip=auth._ip(request))
    return {"id": cid, "created": novo}


CATEGORIAS = ("Using Own Kart", "Baby Kart", "4 stroke", "2 stroke", "Adult Shifter", "F4")
PRODUTOS = {
    "Urace Daily": "treino avulso (Practice / Professional Coaching); preço na aba Academy da Rate Card",
    "Lead and Follow": "coach na pista junto com o piloto (2T); fechado com antecedência = $769 por piloto; aba Academy",
    "Academy": "mensal, 4 sessões [1/4 … 4/4]; preço na aba Academy",
    "Corrida": "Race Support / Trackside Support; preço na aba Racing team",
    "Arrive and Drive": "kart da URACE; aba Academy",
    "Summer Camp": "camp; aba Academy",
    "Test Drive": "primeira experiência; aba Academy",
}


def nome_tarefa(piloto, produto, categoria, n, total):
    """'Renato Frota Pionti_Urace Daily_2T [1/1]' — o padrão que o quadro e a IA leem."""
    base = f"{piloto.strip()}_{produto.strip()}" + (f"_{categoria.strip()}" if categoria else "")
    return f"{base} [{max(1, int(n or 1))}/{max(1, int(total or 1))}]"


class TarefaNovaIn(BaseModel):
    client_id: int | None = None
    pilot_name: str
    responsible: str | None = None
    email: str | None = None
    phone: str | None = None
    dob: str | None = None
    height: str | None = None
    weight: str | None = None
    waist: str | None = None
    experience: str | None = None
    product: str                         # Urace Daily | Academy | Corrida | Arrive and Drive | Summer Camp | Test Drive
    category: str | None = None          # 2T, 4T, Baby Kart, F4, X30, KA100
    package_n: int = 1                   # Academy: sessão 1..4 do mês
    package_total: int = 1               # Academy: 4
    days: int = 1                        # compatibilidade
    due_on: str                          # AAAA-MM-DD
    section_gid: str | None = None       # coluna do dia; se vazio, deduz do due_on
    extra_notes: str | None = None


def _secao_do_dia(due_on):
    from datetime import date as _d
    nomes = {1: "TUESDAY", 2: "WEDNESDAY", 3: "THURSDAY", 4: "FRIDAY", 5: "SATURDAY", 6: "SUNDAY"}
    wd = _d.fromisoformat(due_on).weekday()
    nome = nomes.get(wd)
    for gid, n in SECOES_DIAS.items():
        if n == nome:
            return gid, n
    return None, None


@r.post("/tasks", status_code=201)
def task_create(dados: TarefaNovaIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """Botão 'Nova tarefa': instancia o modelo oficial no Asana, na coluna do dia, e espelha aqui."""
    from datetime import date as _d
    try:
        _d.fromisoformat(dados.due_on)
    except ValueError:
        raise HTTPException(400, "Data inválida (AAAA-MM-DD).")
    faltam = [k for k, v in (("piloto", dados.pilot_name), ("e-mail", dados.email), ("telefone", dados.phone)) if not (v or "").strip()]
    if faltam:
        raise HTTPException(400, "Obrigatório: " + ", ".join(faltam) + ".")
    if "@" not in (dados.email or ""):
        raise HTTPException(400, "E-mail inválido.")
    if dados.category and dados.category not in CATEGORIAS:
        raise HTTPException(400, f"Categoria deve ser uma de: {', '.join(CATEGORIAS)}.")
    sec_gid, sec_nome = (dados.section_gid, SECOES_DIAS.get(dados.section_gid)) if dados.section_gid else _secao_do_dia(dados.due_on)
    if not sec_gid:
        raise HTTPException(400, "A data cai numa segunda-feira: o quadro não tem coluna. Escolha outra data ou a coluna.")
    piloto = dados.pilot_name.strip()
    resp = (dados.responsible or piloto).strip()
    if dados.product not in PRODUTOS:
        raise HTTPException(400, f"Produto deve ser um de: {', '.join(PRODUTOS)}.")
    n, total = (dados.package_n, dados.package_total) if dados.product == "Academy" else (1, max(1, int(dados.days or 1)))
    nome = nome_tarefa(piloto, dados.product, dados.category, n, total)
    idade = None
    if dados.dob:
        try:
            b = _d.fromisoformat(dados.dob); h = _d.today()
            idade = h.year - b.year - ((h.month, h.day) < (b.month, b.day))
        except ValueError:
            raise HTTPException(400, "Data de nascimento inválida (AAAA-MM-DD).")
    if idade is not None and idade < 18 and not (dados.responsible or "").strip():
        raise HTTPException(400, "Piloto menor de idade: o responsável é obrigatório (é quem assina a waiver e paga).")
    if idade is None and not (dados.responsible or "").strip():
        raise HTTPException(400, "Informe a data de nascimento do piloto ou o responsável.")
    from command_center.api import acoes as _ac
    notas = _ac.notas_servico(piloto, resp, dados.email, dados.phone, dados.dob, dados.due_on, dados.product, dados.category, None,
                              dados.height, dados.weight, dados.waist, dados.experience, dados.extra_notes, por=u["name"])
    campos = {} if dados.product in ("Corrida",) else {"Race": "Practice Bushnell" if re.search(r"bushnell", (dados.extra_notes or "") + (dados.category or ""), re.I) else _ac.RACE_PADRAO}
    try:
        res = modulo("asana").criar_do_modelo_humano(MODELO_SESSAO, nome, sec_gid, notas, dados.due_on, campos)
    except NaoConectado as ex:
        raise HTTPException(503, f"Asana não conectado: {ex}")
    except Exception as ex:
        raise HTTPException(502, str(ex)[:300])
    cid = dados.client_id
    if not cid:
        cid, _ = _upsert_cliente(con, resp, (dados.email or "").lower() or None, dados.phone, piloto if piloto != resp else None, dados.dob, source="manual")
    tid = inserir(con, "tasks", client_id=cid, title=res.get("nome") or nome, project="U-RACE", section=sec_nome, section_gid=sec_gid,
                  status="open", due_on=dados.due_on, synced_at=agora())
    _liga(con, "task", tid, "asana", res["gid"], res.get("link") or ASANA_LINK.format(proj=PROJETO_URACE, gid=res["gid"]))
    _liga(con, "client", cid, "asana", res["gid"], res.get("link"))
    auditar(con, "task.create", f"user:{u['id']}", user_id=u["id"], entity_type="task", entity_id=tid,
            detail={"gid": res["gid"], "nome": nome, "secao": sec_nome, "client_id": cid}, ip=auth._ip(request))
    from command_center.api import motor
    motor.registrar_evento(con, "task.created", "task", tid, cid, f"{nome} em {sec_nome} ({dados.due_on}) — criada pelo painel")
    return {"id": tid, "client_id": cid, "gid": res["gid"], "link": res.get("link"), "section": sec_nome}


class WaiverEnviarIn(BaseModel):
    template: str                        # parental | adult
    signer_name: str
    signer_email: str
    service: str | None = None
    client_id: int | None = None


@r.post("/waivers/send", status_code=201)
def waiver_send(dados: WaiverEnviarIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """Botão 'Enviar waiver': clique humano; as travas de duplicidade do DocuSign continuam valendo."""
    templates = {"parental": os.environ.get("DOCUSIGN_TEMPLATE_PARENTAL", "6dbf2094-39da-4c21-95dd-feda7ac28022"),
                 "adult": os.environ.get("DOCUSIGN_TEMPLATE_ADULT", "c51aede4-bba5-40df-9f14-24c340e2bd3e")}
    if dados.template not in templates:
        raise HTTPException(400, "Modelo deve ser parental ou adult.")
    email = dados.signer_email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "E-mail inválido.")
    if email.endswith("@urace.us"):
        raise HTTPException(400, "E-mail do domínio da URACE não é de cliente. Confira o e-mail do responsável.")
    try:
        res = modulo("docusign").enviar_waiver_humano(templates[dados.template], dados.signer_name.strip(), email, dados.service or "")
    except NaoConectado as ex:
        raise HTTPException(503, f"DocuSign não conectado: {ex}")
    except Exception as ex:
        raise HTTPException(409 if "RECUSADO" in str(ex) or "NÃO ENVIAR" in str(ex) else 502, str(ex)[:300])
    env = res.get("envelopeId") if isinstance(res, dict) else None
    cid = dados.client_id or (_acha := None)
    if not cid:
        c = um(con, "SELECT id FROM clients WHERE email=?", (email,))
        cid = c["id"] if c else None
    wid = inserir(con, "waivers", client_id=cid, signer_name=dados.signer_name.strip(), signer_email=email, template=dados.template,
                  status="sent", sent_at=agora(), link_reason="enviada pelo painel", link_by="human" if cid else None, synced_at=agora())
    if env:
        _liga(con, "waiver", wid, "docusign", env, f"https://apps.docusign.com/send/documents/details/{env}")
    auditar(con, "waiver.send", f"user:{u['id']}", user_id=u["id"], entity_type="waiver", entity_id=wid,
            detail={"envelope": env, "template": dados.template, "email": email}, ip=auth._ip(request))
    return {"id": wid, "envelope": env, "result": res}


@r.get("/rate-card/check")
def rate_card_check(u=Depends(auth.usuario_atual)):
    """A IA precisa ler a planilha de preços. Prova: lê as primeiras células ao vivo."""
    try:
        r = chamar("gmail", "sheets_ler", conta="urace", planilha_id=RATE_CARD_ID, intervalo="A1:D6")
        return {"ok": True, "linhas": r.get("linhas", [])[:6], "id": RATE_CARD_ID}
    except NaoConectado as e:
        return {"ok": False, "reason": str(e), "id": RATE_CARD_ID}
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {str(e)[:200]}", "id": RATE_CARD_ID}



# ============================================================ Fontes de contexto da IA (Integrações → Planilhas / Arquivos)
from fastapi import File, Form, UploadFile  # noqa: E402

CONTEXT_DIR = os.path.join(os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "context")
EXT_OK = {".pdf", ".txt", ".md", ".csv", ".json", ".docx", ".xlsx", ".png", ".jpg", ".jpeg"}
MAX_BYTES = 25 * 1024 * 1024


def _workspace_contexto():
    agente = os.environ.get("OPENCLAW_AGENT", "urace-admin")
    return os.path.expanduser(f"~/.openclaw/workspace/{agente}/contexto")


def _sheet_id(url):
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]{20,})", url or "")
    return m.group(1) if m else ((url or "").strip() if re.fullmatch(r"[A-Za-z0-9_-]{20,}", (url or "").strip()) else None)


def _slug(nome):
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", nome.strip()).strip("-.")[:80] or "arquivo"
    return base


def _extrair_texto(caminho, mime):
    """PDF → texto (pypdf, se instalado). txt/md/csv/json → o próprio arquivo. Outros: sem texto."""
    ext = os.path.splitext(caminho)[1].lower()
    if ext in (".txt", ".md", ".csv", ".json"):
        return caminho
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            partes = []
            for pg in PdfReader(caminho).pages[:200]:
                partes.append(pg.extract_text() or "")
            txt = "\n\n".join(partes).strip()
            if txt:
                alvo = caminho + ".txt"
                with open(alvo, "w", encoding="utf-8") as f:
                    f.write(txt)
                return alvo
        except Exception:
            return None
    return None


def _publicar_no_workspace(src):
    """Copia o arquivo (e o texto extraído) para o workspace do agente: é lá que ele lê."""
    import shutil
    try:
        dst_dir = _workspace_contexto()
        os.makedirs(dst_dir, exist_ok=True)
        for pth in (src["path"], src["text_path"]):
            if pth and os.path.isfile(pth):
                shutil.copy2(pth, os.path.join(dst_dir, os.path.basename(pth)))
        return True
    except Exception:
        return False


@r.get("/context")
def context_list(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    rows = todos(con, "SELECT c.*, us.name AS added_by_name FROM context_sources c LEFT JOIN users us ON us.id=c.added_by ORDER BY c.kind, c.id")
    for c in rows:
        c["workspace_name"] = os.path.basename(c["text_path"] or c["path"] or "") if c["kind"] == "file" else None
    return rows


class PlanilhaIn(BaseModel):
    title: str
    url: str
    description: str | None = None
    sheet_range: str | None = None


@r.post("/context/sheet", status_code=201)
def context_sheet(dados: PlanilhaIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    sid = _sheet_id(dados.url)
    if not sid:
        raise HTTPException(400, "Cole o link da planilha do Google (docs.google.com/spreadsheets/d/…).")
    if not (dados.title or "").strip():
        raise HTTPException(400, "Dê um título.")
    if um(con, "SELECT id FROM context_sources WHERE sheet_id=?", (sid,)):
        raise HTTPException(409, "Essa planilha já está cadastrada.")
    cid = inserir(con, "context_sources", kind="sheet", title=dados.title.strip()[:120], description=(dados.description or "").strip()[:500] or None,
                  url=f"https://docs.google.com/spreadsheets/d/{sid}", sheet_id=sid, sheet_range=(dados.sheet_range or "").strip()[:60] or None, added_by=u["id"])
    auditar(con, "context.add", f"user:{u['id']}", user_id=u["id"], entity_type="context", entity_id=cid, detail={"kind": "sheet", "title": dados.title}, ip=auth._ip(request))
    return {"id": cid, **_checar(con, cid)}


class LinkIn(BaseModel):
    title: str
    url: str
    description: str | None = None


@r.post("/context/link", status_code=201)
def context_link(dados: LinkIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    if not (dados.url or "").startswith("http"):
        raise HTTPException(400, "Link inválido.")
    cid = inserir(con, "context_sources", kind="link", title=dados.title.strip()[:120], description=(dados.description or "").strip()[:500] or None,
                  url=dados.url.strip()[:500], added_by=u["id"])
    auditar(con, "context.add", f"user:{u['id']}", user_id=u["id"], entity_type="context", entity_id=cid, detail={"kind": "link", "title": dados.title}, ip=auth._ip(request))
    return {"id": cid}


@r.post("/context/file", status_code=201)
async def context_file(request: Request, file: UploadFile = File(...), title: str = Form(""), description: str = Form(""),
                       u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in EXT_OK:
        raise HTTPException(400, f"Tipo não aceito ({ext or 'sem extensão'}). Aceitos: {', '.join(sorted(EXT_OK))}.")
    dados = await file.read()
    if not dados:
        raise HTTPException(400, "Arquivo vazio.")
    if len(dados) > MAX_BYTES:
        raise HTTPException(413, "Arquivo maior que 25 MB.")
    os.makedirs(CONTEXT_DIR, exist_ok=True)
    nome = _slug(os.path.splitext(file.filename or "arquivo")[0]) + ext
    caminho = os.path.join(CONTEXT_DIR, nome)
    n = 1
    while os.path.exists(caminho):
        n += 1; caminho = os.path.join(CONTEXT_DIR, f"{_slug(os.path.splitext(file.filename or 'arquivo')[0])}-{n}{ext}")
    with open(caminho, "wb") as f:
        f.write(dados)
    os.chmod(caminho, 0o600)
    texto = _extrair_texto(caminho, file.content_type)
    cid = inserir(con, "context_sources", kind="file", title=(title or file.filename or nome).strip()[:120], description=(description or "").strip()[:500] or None,
                  path=caminho, text_path=texto, mime=file.content_type, size=len(dados), added_by=u["id"])
    ok = _publicar_no_workspace({"path": caminho, "text_path": texto})
    con.execute("UPDATE context_sources SET last_check_at=?, last_check_ok=?, last_check_msg=? WHERE id=?",
                (agora(), 1 if ok else 0, ("no workspace do agente" + ("" if texto else "; sem texto extraído — a IA só vê o nome")) if ok else "não consegui copiar para o workspace do agente", cid))
    auditar(con, "context.add", f"user:{u['id']}", user_id=u["id"], entity_type="context", entity_id=cid,
            detail={"kind": "file", "nome": os.path.basename(caminho), "bytes": len(dados), "texto": bool(texto)}, ip=auth._ip(request))
    return {"id": cid, "name": os.path.basename(caminho), "text": bool(texto), "workspace": ok}


def _checar(con, cid):
    c = um(con, "SELECT * FROM context_sources WHERE id=?", (cid,))
    ok, msg = False, ""
    try:
        if c["kind"] == "sheet":
            r = chamar("gmail", "sheets_ler", conta="urace", planilha_id=c["sheet_id"], intervalo=(c["sheet_range"] or "A1:D5").split("!")[-1] if False else (c["sheet_range"] or "A1:D5"))
            linhas = r.get("linhas", [])
            ok, msg = True, f"{len(linhas)} linha(s) lidas; primeira: {(linhas[0] if linhas else [])[:4]}"
        elif c["kind"] == "file":
            ok = _publicar_no_workspace(c)
            msg = "no workspace do agente" if ok else "não consegui copiar para o workspace do agente"
        else:
            ok, msg = True, "link registrado (a IA recebe o endereço)"
    except NaoConectado as e:
        msg = f"não conectado: {e}"
    except Exception as e:
        msg = f"{type(e).__name__}: {str(e)[:200]}"
    con.execute("UPDATE context_sources SET last_check_at=?, last_check_ok=?, last_check_msg=? WHERE id=?", (agora(), 1 if ok else 0, msg[:300], cid))
    return {"ok": ok, "msg": msg}


@r.post("/context/{cid}/check")
def context_check(cid: int, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    if not um(con, "SELECT id FROM context_sources WHERE id=?", (cid,)):
        raise HTTPException(404, "Not found.")
    return _checar(con, cid)


@r.post("/context/{cid}/toggle")
def context_toggle(cid: int, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    c = um(con, "SELECT * FROM context_sources WHERE id=?", (cid,))
    if not c:
        raise HTTPException(404, "Not found.")
    con.execute("UPDATE context_sources SET active=? WHERE id=?", (0 if c["active"] else 1, cid))
    auditar(con, "context.toggle", f"user:{u['id']}", user_id=u["id"], entity_type="context", entity_id=cid, detail={"active": not c["active"]}, ip=auth._ip(request))
    return {"ok": True, "active": not c["active"]}


@r.get("/context/{cid}/download")
def context_download(cid: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    from fastapi.responses import FileResponse
    c = um(con, "SELECT * FROM context_sources WHERE id=? AND kind='file'", (cid,))
    if not c or not c["path"] or not os.path.isfile(c["path"]):
        raise HTTPException(404, "Arquivo não encontrado.")
    return FileResponse(c["path"], filename=os.path.basename(c["path"]), headers={"Cache-Control": "no-store"})


# ============================================================ Pro Racing Drivers, mensalidade, contrato, equipamento, corridas (09/09)
MESES_EN = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"), 1)}
SESSOES_MES = 4
CONTRACT_DIR = os.path.join(os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "contracts")
IMAGE_DIR = os.path.join(os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "images")


def mes_da_invoice(inv):
    """'Urace Academy Training Program + Tuner [August, 2026]' → '2026-08'; senão o mês de emissão."""
    m = re.search(r"\[\s*([A-Za-z]+)[,\s]+(\d{4})\s*\]", inv.get("memo") or "")
    if m and m.group(1).lower() in MESES_EN:
        return f"{m.group(2)}-{MESES_EN[m.group(1).lower()]:02d}"
    return (inv.get("issued_on") or "")[:7] or None


def resumo_mensalidade(con, cid, meses=4):
    """Por mês: invoice da mensalidade (memo Academy), sessões usadas (tarefas de treino), restantes, e se falta invoice."""
    from datetime import date as _d
    hoje = _d.today()
    invs = todos(con, "SELECT * FROM invoices WHERE client_id=? ORDER BY issued_on DESC", (cid,))
    por_mes = {}
    for i in invs:
        if re.search(r"academy|monthly|training program|mensal", (i.get("memo") or "") + " " + (i.get("doc_number") or ""), re.I):
            por_mes.setdefault(mes_da_invoice(i), i)
    saida = []
    for k in range(meses):
        y, mo = hoje.year, hoje.month - k
        while mo <= 0:
            mo += 12; y -= 1
        mes = f"{y}-{mo:02d}"
        usadas = todos(con, """SELECT title, due_on, status FROM tasks WHERE client_id=? AND due_on LIKE ? AND project='U-RACE'
                               AND LOWER(COALESCE(section,'')) NOT IN ('races','finished services') OR (client_id=? AND due_on LIKE ? AND status='completed' AND LOWER(COALESCE(section,''))='finished services')""",
                       (cid, mes + "%", cid, mes + "%"))
        inv = por_mes.get(mes)
        saida.append({"month": mes, "invoice": ({"id": inv["id"], "doc_number": inv["doc_number"], "amount": inv["amount"], "balance": inv["balance"], "status": inv["status"], "memo": inv["memo"]} if inv else None),
                      "sessions_used": len(usadas), "sessions_left": max(0, SESSOES_MES - len(usadas)), "sessions": usadas,
                      "needs_invoice": inv is None and (k == 0 or len(usadas) > 0)})
    ultimo = next((i for i in invs if re.search(r"academy|monthly|training program|mensal", (i.get("memo") or ""), re.I)), None)
    return {"months": saida, "last_monthly_amount": ultimo["amount"] if ultimo else None, "last_monthly_memo": ultimo["memo"] if ultimo else None,
            "sessions_per_month": SESSOES_MES}


@r.get("/clients/{cid}/monthly")
def client_monthly(cid: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    if not um(con, "SELECT id FROM clients WHERE id=?", (cid,)):
        raise HTTPException(404, "Client not found.")
    r_ = resumo_mensalidade(con, cid)
    if not auth.pode(u["role"], "MANAGER"):                          # financeiro só para gerente+
        for m in r_["months"]:
            if m["invoice"]:
                m["invoice"] = {k: v for k, v in m["invoice"].items() if k not in ("amount", "balance")}
        r_["last_monthly_amount"] = None
    r_["contracts"] = todos(con, "SELECT c.*, us.name AS added_by_name FROM contracts c LEFT JOIN users us ON us.id=c.added_by WHERE c.client_id=? ORDER BY c.id DESC", (cid,))
    return r_


class EquipIn(BaseModel):
    plan_type: str | None = None          # monthly | daily
    pro_driver: bool | None = None
    chassis_id: int | None = None
    engine_id: int | None = None
    equipment_notes: str | None = None


@r.patch("/clients/{cid}/profile")
def client_profile(cid: int, dados: EquipIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    if not um(con, "SELECT id FROM clients WHERE id=?", (cid,)):
        raise HTTPException(404, "Client not found.")
    campos = {}
    if dados.plan_type is not None:
        if dados.plan_type not in ("monthly", "daily", ""):
            raise HTTPException(400, "plan_type: monthly ou daily.")
        campos["plan_type"] = dados.plan_type or None
    if dados.pro_driver is not None:
        if not auth.pode(u["role"], "MANAGER"):
            raise HTTPException(403, "Só gerente marca Pro Racing Driver.")
        campos["pro_driver"] = 1 if dados.pro_driver else 0
    for k in ("chassis_id", "engine_id", "equipment_notes"):
        v = getattr(dados, k)
        if v is not None:
            campos[k] = v or None
    if not campos:
        return {"ok": True}
    sets = ", ".join(f"{k}=?" for k in campos)
    con.execute(f"UPDATE clients SET {sets}, updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (*campos.values(), cid))
    auditar(con, "client.profile", f"user:{u['id']}", user_id=u["id"], entity_type="client", entity_id=cid, detail=campos, ip=auth._ip(request))
    return {"ok": True}


@r.get("/clients/{cid}/equipment")
def client_equipment(cid: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    c = um(con, "SELECT chassis_id, engine_id, equipment_notes FROM clients WHERE id=?", (cid,))
    if not c:
        raise HTTPException(404, "Client not found.")
    ch = um(con, "SELECT * FROM catalog_chassis WHERE id=?", (c["chassis_id"],)) if c["chassis_id"] else None
    en = um(con, "SELECT * FROM catalog_engines WHERE id=?", (c["engine_id"],)) if c["engine_id"] else None
    parts = todos(con, "SELECT * FROM catalog_parts WHERE engine_id=? AND active=1 ORDER BY name", (c["engine_id"],)) if c["engine_id"] else []
    return {"chassis": ch, "engine": en, "parts": parts, "notes": c["equipment_notes"]}


# ---- contrato da Academy: upload ou achado no DocuSign
@r.post("/clients/{cid}/contract", status_code=201)
async def contract_upload(cid: int, request: Request, file: UploadFile = File(...), title: str = Form(""),
                          u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    if not um(con, "SELECT id FROM clients WHERE id=?", (cid,)):
        raise HTTPException(404, "Client not found.")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".pdf", ".png", ".jpg", ".jpeg"):
        raise HTTPException(400, "Contrato em PDF (ou imagem).")
    dados = await file.read()
    if not dados or len(dados) > MAX_BYTES:
        raise HTTPException(400, "Arquivo vazio ou maior que 25 MB.")
    os.makedirs(CONTRACT_DIR, exist_ok=True)
    caminho = os.path.join(CONTRACT_DIR, f"cliente-{cid}-{_slug(os.path.splitext(file.filename or 'contrato')[0])}{ext}")
    with open(caminho, "wb") as f:
        f.write(dados)
    os.chmod(caminho, 0o600)
    kid = inserir(con, "contracts", client_id=cid, kind="academy", source="upload", file_path=caminho, title=(title or file.filename or "Contrato")[:120], added_by=u["id"], status="completed")
    con.execute("UPDATE clients SET plan_type=COALESCE(plan_type,'monthly') WHERE id=?", (cid,))
    auditar(con, "contract.upload", f"user:{u['id']}", user_id=u["id"], entity_type="contract", entity_id=kid, detail={"client_id": cid, "nome": os.path.basename(caminho)}, ip=auth._ip(request))
    return {"id": kid}


@r.get("/contracts/{kid}/download")
def contract_download(kid: int, request: Request, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    from fastapi.responses import FileResponse, Response
    k = um(con, "SELECT * FROM contracts WHERE id=?", (kid,))
    if not k:
        raise HTTPException(404, "Not found.")
    if k["file_path"] and os.path.isfile(k["file_path"]):
        return FileResponse(k["file_path"], filename=os.path.basename(k["file_path"]), headers={"Cache-Control": "no-store"})
    if k["envelope_id"]:
        try:
            pdf = modulo("docusign").baixar_documento_humano(k["envelope_id"])
        except NaoConectado as ex:
            raise HTTPException(503, f"DocuSign não conectado: {ex}")
        except Exception as ex:
            raise HTTPException(502, str(ex)[:300])
        auditar(con, "contract.download", f"user:{u['id']}", user_id=u["id"], entity_type="contract", entity_id=kid, ip=auth._ip(request))
        return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="contrato-{kid}.pdf"', "Cache-Control": "no-store"})
    raise HTTPException(404, "Contrato sem arquivo nem envelope.")


def _contratos_do_docusign(con, c):
    """Envelopes do cliente cujo assunto fala de Academy/contract viram contratos (fonte DocuSign)."""
    email = (c["email"] or "").lower()
    if not email:
        return 0
    n = 0
    try:
        r = chamar("docusign", "docusign_waivers_de", email=email)
    except Exception:
        return 0
    for grupo in ("waiver_valida", "em_aberto", "historico"):
        for e in r.get(grupo) or []:
            assunto = (e.get("assunto") or "").lower()
            if not re.search(r"academy|contract|contrato|program", assunto) or re.search(r"waiver", assunto):
                continue
            if um(con, "SELECT 1 FROM contracts WHERE envelope_id=?", (e["envelopeId"],)):
                continue
            inserir(con, "contracts", client_id=c["id"], kind="academy", source="docusign", envelope_id=e["envelopeId"], status=e.get("status"),
                    signed_at=e.get("concluido_em"), title=e.get("assunto"))
            if e.get("status") == "completed":
                con.execute("UPDATE clients SET plan_type=COALESCE(plan_type,'monthly') WHERE id=?", (c["id"],))
            n += 1
    return n


# ---- catálogo de equipamento (editável)
@r.get("/catalog")
def catalog(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    return {"chassis": todos(con, "SELECT * FROM catalog_chassis ORDER BY active DESC, brand, model"),
            "engines": todos(con, "SELECT * FROM catalog_engines ORDER BY active DESC, brand, model"),
            "parts": todos(con, "SELECT p.*, e.brand AS engine_brand, e.model AS engine_model FROM catalog_parts p LEFT JOIN catalog_engines e ON e.id=p.engine_id ORDER BY p.engine_id, p.name")}


class ChassisIn(BaseModel):
    brand: str | None = None
    model: str | None = None
    size: str | None = None
    tire_front: str | None = None
    tire_rear: str | None = None
    notes: str | None = None
    active: bool | None = None


class EngineIn(BaseModel):
    brand: str | None = None
    model: str | None = None
    stroke: str | None = None
    category: str | None = None
    notes: str | None = None
    active: bool | None = None


class PartIn(BaseModel):
    engine_id: int | None = None
    name: str | None = None
    part_number: str | None = None
    price: float | None = None
    notes: str | None = None
    active: bool | None = None


_TABELAS = {"chassis": ("catalog_chassis", ChassisIn), "engines": ("catalog_engines", EngineIn), "parts": ("catalog_parts", PartIn)}


def _catalogo_upsert(con, kind, dados, cid, u, request):
    tabela, _ = _TABELAS[kind]
    campos = {k: (1 if v else 0) if k == "active" else v for k, v in dados.model_dump().items() if v is not None}
    if cid is None:
        if kind == "chassis" and not campos.get("brand"):
            raise HTTPException(400, "Marca é obrigatória.")
        if kind == "engines" and not (campos.get("brand") and campos.get("model")):
            raise HTTPException(400, "Marca e modelo são obrigatórios.")
        if kind == "parts" and not (campos.get("name") and campos.get("engine_id")):
            raise HTTPException(400, "Nome e motor são obrigatórios.")
        cid = inserir(con, tabela, **campos)
    else:
        if not um(con, f"SELECT id FROM {tabela} WHERE id=?", (cid,)):
            raise HTTPException(404, "Not found.")
        if campos:
            con.execute(f"UPDATE {tabela} SET " + ", ".join(f"{k}=?" for k in campos) + " WHERE id=?", (*campos.values(), cid))
    auditar(con, "catalog.save", f"user:{u['id']}", user_id=u["id"], entity_type=tabela, entity_id=cid, detail=campos, ip=auth._ip(request))
    return {"id": cid}


@r.post("/catalog/chassis", status_code=201)
def chassis_create(dados: ChassisIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    return _catalogo_upsert(con, "chassis", dados, None, u, request)


@r.patch("/catalog/chassis/{cid}")
def chassis_patch(cid: int, dados: ChassisIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    return _catalogo_upsert(con, "chassis", dados, cid, u, request)


@r.post("/catalog/engines", status_code=201)
def engine_create(dados: EngineIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    return _catalogo_upsert(con, "engines", dados, None, u, request)


@r.patch("/catalog/engines/{cid}")
def engine_patch(cid: int, dados: EngineIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    return _catalogo_upsert(con, "engines", dados, cid, u, request)


@r.post("/catalog/parts", status_code=201)
def part_create(dados: PartIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    return _catalogo_upsert(con, "parts", dados, None, u, request)


@r.patch("/catalog/parts/{cid}")
def part_patch(cid: int, dados: PartIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    return _catalogo_upsert(con, "parts", dados, cid, u, request)


@r.post("/catalog/{kind}/{cid}/image")
async def catalog_image(kind: str, cid: int, request: Request, file: UploadFile = File(...), u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    if kind not in ("chassis", "engines"):
        raise HTTPException(404, "Not found.")
    tabela = _TABELAS[kind][0]
    if not um(con, f"SELECT id FROM {tabela} WHERE id=?", (cid,)):
        raise HTTPException(404, "Not found.")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(400, "Imagem em PNG, JPG ou WEBP.")
    dados = await file.read()
    if not dados or len(dados) > 5 * 1024 * 1024:
        raise HTTPException(400, "Imagem vazia ou maior que 5 MB.")
    os.makedirs(IMAGE_DIR, exist_ok=True)
    caminho = os.path.join(IMAGE_DIR, f"{kind}-{cid}{ext}")
    with open(caminho, "wb") as f:
        f.write(dados)
    con.execute(f"UPDATE {tabela} SET image_path=? WHERE id=?", (caminho, cid))
    auditar(con, "catalog.image", f"user:{u['id']}", user_id=u["id"], entity_type=tabela, entity_id=cid, ip=auth._ip(request))
    return {"ok": True}


@r.get("/catalog/{kind}/{cid}/image")
def catalog_image_get(kind: str, cid: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    from fastapi.responses import FileResponse
    if kind not in ("chassis", "engines"):
        raise HTTPException(404, "Not found.")
    c = um(con, f"SELECT image_path FROM {_TABELAS[kind][0]} WHERE id=?", (cid,))
    if not c or not c["image_path"] or not os.path.isfile(c["image_path"]):
        raise HTTPException(404, "Sem imagem.")
    return FileResponse(c["image_path"], headers={"Cache-Control": "private, max-age=3600"})


# ---- corridas e convites
def _corrida_out(con, rc):
    rc["invited"] = todos(con, """SELECT i.*, c.name, c.pilot_name, cmd.status AS estimate_status FROM race_invites i JOIN clients c ON c.id=i.client_id
                                  LEFT JOIN ai_commands cmd ON cmd.id=i.estimate_cmd WHERE i.race_id=? ORDER BY i.id""", (rc["id"],))
    rc["task"] = None
    if rc.get("task_id"):
        t = um(con, "SELECT id, title, status, due_on, section, subtasks_total, subtasks_done, assignee, synced_at FROM tasks WHERE id=?", (rc["task_id"],))
        if t:
            t["links"] = _links(con, "task", t["id"])
            rc["task"] = t
    return rc


@r.get("/races")
def races(all: bool = False, client_id: int | None = None, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Calendário de corridas: a coluna RACES do Asana (uma por tarefa) mais as manuais."""
    where, p = ["1=1"], []
    if not all:
        where.append("r.active=1")
    if client_id:
        where.append("r.id IN (SELECT race_id FROM race_invites WHERE client_id=?)"); p.append(client_id)
    rows = todos(con, f"SELECT r.*, (SELECT COUNT(*) FROM race_invites i WHERE i.race_id=r.id) AS invites FROM races r WHERE {' AND '.join(where)} ORDER BY COALESCE(r.date_start,'9999')", p)
    return [_corrida_out(con, rc) for rc in rows]


def _comenta_na_corrida(con, rid, texto):
    """Espelha no Asana o convite/confirmação (comentário na tarefa da corrida). Sem Asana, segue em silêncio."""
    r = um(con, "SELECT task_id FROM races WHERE id=?", (rid,))
    if not r or not r["task_id"]:
        return None
    l = um(con, "SELECT external_id FROM entity_links WHERE entity_type='task' AND entity_id=? AND system='asana'", (r["task_id"],))
    if not l:
        return None
    try:
        return modulo("asana").comentar_humano(l["external_id"], texto)
    except Exception as e:
        return {"erro": f"{type(e).__name__}: {str(e)[:200]}"}


class RaceIn(BaseModel):
    name: str | None = None
    series: str | None = None
    track: str | None = None
    city: str | None = None
    date_start: str | None = None
    date_end: str | None = None
    notes: str | None = None
    active: bool | None = None
    local_only: bool | None = None


@r.post("/races", status_code=201)
def race_create(dados: RaceIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """Nova corrida = tarefa criada do modelo oficial "New Race [Race + City/Track]" na coluna
    RACES do Asana (vem com as subtarefas do modelo). Sem Asana: 503, a não ser que
    `local_only` (só no painel)."""
    if not (dados.name or "").strip():
        raise HTTPException(400, "Nome da corrida é obrigatório.")
    campos = {k: v for k, v in dados.model_dump().items() if v is not None and k not in ("active", "local_only")}
    task_id = None
    if not dados.local_only:
        try:
            m = modulo("asana")
            secoes = chamar("asana", "asana_secoes", projeto_gid=PROJETO_URACE)
            races_gid = next((x["gid"] for x in secoes if x["nome"].strip().upper() == "RACES"), None)
            if not races_gid:
                raise HTTPException(409, "Coluna RACES não encontrada no quadro U-RACE.")
            local = " / ".join(x for x in (dados.city, dados.track) if x)
            nome = f"{dados.name.strip()}" + (f" [{local}]" if local else "")
            notas = "\n".join(x for x in ((f"Série: {dados.series}" if dados.series else ""), (f"Pista: {dados.track}" if dados.track else ""),
                                          (f"Cidade: {dados.city}" if dados.city else ""), (f"Fim: {dados.date_end}" if dados.date_end else ""), dados.notes or "") if x)
            novo = m.criar_do_modelo_humano(m.MODELO_CORRIDA, nome, secao_gid=races_gid, notas=notas or None, vence_em=dados.date_start)
            gid = novo.get("gid") or (novo.get("tarefa") or {}).get("gid")
            if gid:
                task_id, _ = sy._grava_tarefa(con, gid, dict(client_id=None, title=nome, project="U-RACE", section="RACES", section_gid=races_gid,
                                                             status="open", due_on=dados.date_start, subtasks_total=novo.get("subtarefas"), subtasks_done=0, synced_at=agora()))
            campos["name"] = nome
        except HTTPException:
            raise
        except NaoConectado as e:
            raise HTTPException(503, f"Asana não conectado: {e}. Marque 'só no painel' para criar sem o Asana.")
        except Exception as e:
            raise HTTPException(502, f"Asana: {str(e)[:300]}")
    rid = inserir(con, "races", source="asana" if task_id else "manual", task_id=task_id, **campos)
    auditar(con, "race.create", f"user:{u['id']}", user_id=u["id"], entity_type="race", entity_id=rid, detail={**campos, "task_id": task_id}, ip=auth._ip(request))
    return {"id": rid, "task_id": task_id}


@r.patch("/races/{rid}")
def race_patch(rid: int, dados: RaceIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    if not um(con, "SELECT id FROM races WHERE id=?", (rid,)):
        raise HTTPException(404, "Not found.")
    campos = {k: (1 if v else 0) if k == "active" else v for k, v in dados.model_dump().items() if v is not None}
    if campos:
        con.execute("UPDATE races SET " + ", ".join(f"{k}=?" for k in campos) + " WHERE id=?", (*campos.values(), rid))
    auditar(con, "race.update", f"user:{u['id']}", user_id=u["id"], entity_type="race", entity_id=rid, detail=campos, ip=auth._ip(request))
    return {"ok": True}


class ConviteIn(BaseModel):
    client_id: int


@r.post("/races/{rid}/invite", status_code=201)
def race_invite(rid: int, dados: ConviteIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    if not um(con, "SELECT id FROM races WHERE id=?", (rid,)):
        raise HTTPException(404, "Race not found.")
    c = um(con, "SELECT id, pro_driver FROM clients WHERE id=?", (dados.client_id,))
    if not c:
        raise HTTPException(404, "Client not found.")
    if um(con, "SELECT 1 FROM race_invites WHERE race_id=? AND client_id=?", (rid, dados.client_id)):
        raise HTTPException(409, "Já convidado.")
    iid = inserir(con, "race_invites", race_id=rid, client_id=dados.client_id, invited_by=u["id"])
    piloto = um(con, "SELECT COALESCE(pilot_name, name) AS p FROM clients WHERE id=?", (dados.client_id,))["p"]
    _comenta_na_corrida(con, rid, f"[Command Center] Convidado: {piloto} — aguardando confirmação.")
    auditar(con, "race.invite", f"user:{u['id']}", user_id=u["id"], entity_type="race", entity_id=rid, detail={"client_id": dados.client_id}, ip=auth._ip(request))
    return {"id": iid}


class ConviteStatusIn(BaseModel):
    status: str


@r.patch("/invites/{iid}")
def invite_status(iid: int, dados: ConviteStatusIn, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    if dados.status not in ("invited", "confirmed", "declined", "done"):
        raise HTTPException(400, "status inválido.")
    if not um(con, "SELECT id FROM race_invites WHERE id=?", (iid,)):
        raise HTTPException(404, "Not found.")
    con.execute("UPDATE race_invites SET status=? WHERE id=?", (dados.status, iid))
    i = um(con, "SELECT i.race_id, COALESCE(c.pilot_name, c.name) AS p FROM race_invites i JOIN clients c ON c.id=i.client_id WHERE i.id=?", (iid,))
    rotulo = {"confirmed": "CONFIRMADO", "declined": "não vai", "done": "correu", "invited": "convidado, aguardando confirmação"}.get(dados.status, dados.status)
    _comenta_na_corrida(con, i["race_id"], f"[Command Center] {i['p']}: {rotulo}.")
    auditar(con, "race.invite.status", f"user:{u['id']}", user_id=u["id"], entity_type="race_invite", entity_id=iid, detail={"status": dados.status}, ip=auth._ip(request))
    return {"ok": True}


def _estimativa_thread(iid, cid_cmd, texto, session_key, user_id):
    from command_center.api import ia
    ia._executa(cid_cmd, texto, session_key, user_id)
    con = conectar()
    try:
        c = um(con, "SELECT status, output, error FROM ai_commands WHERE id=?", (cid_cmd,))
        con.execute("UPDATE race_invites SET estimate_text=? WHERE id=?", ((c["output"] if c and c["status"] == "DONE" else f"falhou: {c['error'] if c else '?'}")[:4000], iid))
    finally:
        con.close()


@r.post("/invites/{iid}/estimate", status_code=202)
def invite_estimate(iid: int, request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """Prévia de custo da corrida para este piloto: a IA lê a aba Racing team da Rate Card e o equipamento. Não cria nada no QuickBooks."""
    from command_center.api import ia, motor
    i = um(con, "SELECT i.*, r.name AS race, r.series, r.track, r.city, r.date_start, r.date_end, r.notes AS race_notes FROM race_invites i JOIN races r ON r.id=i.race_id WHERE i.id=?", (iid,))
    if not i:
        raise HTTPException(404, "Not found.")
    c = um(con, "SELECT * FROM clients WHERE id=?", (i["client_id"],))
    eq = client_equipment(i["client_id"], u, con)
    prompt = (f"PRÉVIA DE CUSTO (não crie nada no QuickBooks, não envie nada): quanto custaria para o piloto {c['pilot_name'] or c['name']} "
              f"(responsável {c['name']}, plano {c['plan_type'] or '?'}/{c['monthly_plan'] or 'sem mensal'}) correr em '{i['race']}' "
              f"({i['series'] or ''} {i['track'] or ''} {i['city'] or ''} {i['date_start'] or ''}–{i['date_end'] or ''}). "
              f"Equipamento: chassi {json.dumps(eq['chassis'], ensure_ascii=False) if eq['chassis'] else 'não informado'}; motor {json.dumps(eq['engine'], ensure_ascii=False) if eq['engine'] else 'não informado'}. "
              "Use a aba 'Racing team' da Rate Card (sheets_ler) e, se a corrida for fora do Orlando Kart Center, some hotel/comida/transporte conforme a planilha. "
              "Responda com uma tabela curta: item, quantidade, unitário, total; e o total geral. Diga o que assumiu. ACAO: nenhuma."
              + motor.aprendizados(con, c["id"]))
    session_key = f"agent:{ia.AGENTE}:estimativa-{iid}"
    cmd = inserir(con, "ai_commands", user_id=u["id"], text=prompt, session_key=session_key)
    con.execute("UPDATE race_invites SET estimate_cmd=?, estimate_text=NULL WHERE id=?", (cmd, iid))
    auditar(con, "race.estimate", f"user:{u['id']}", user_id=u["id"], entity_type="race_invite", entity_id=iid, detail={"command_id": cmd}, ip=auth._ip(request))
    threading.Thread(target=_estimativa_thread, args=(iid, cmd, prompt, session_key, u["id"]), daemon=True).start()
    return {"command_id": cmd}

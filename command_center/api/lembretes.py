"""Lembretes recorrentes de invoice em aberto (dono, 16/09).

Pedido: *"um botão nos clientes para mandar reminders — diário, semanal ou um período
personalizado de dias — com o toggle de ligar e desligar; tanto no perfil do cliente
quanto no QuickBooks, onde eu seleciono as invoices que quero nesses reminders."*

Como funciona:
- Um lembrete por invoice (`invoice_reminders`). Cadência: `daily` (1 dia), `weekly`
  (7 dias) ou `custom` (N dias). Ligado/desligado.
- A rotina `lembrete_invoice` roda uma vez por dia (agenda, 09:00 de Orlando) e manda o
  lembrete de cada invoice cujo `next_on` já chegou e que **ainda tem saldo**. Depois
  marca o próximo dia. Invoice paga desliga o lembrete sozinha.
- O envio é o `qbo_enviar_invoice` do QuickBooks (reenvia a invoice por e-mail para o
  BillEmail). Sem APLICAR=1 é simulação, e fica registrado como simulação.
- Quem liga o lembrete é um MANAGER, na tela: essa é a aprovação humana — por isso a
  rotina não passa pela IA nem pela fila de aprovações. O envio "agora" também é botão.
"""
from datetime import date, datetime, timedelta

from command_center.db import agora, auditar, inserir, todos, um

CADENCIAS = {"daily": 1, "weekly": 7, "custom": None}
ABERTAS = ("open", "sent", "overdue")


def dias_da_cadencia(cadence, every_days):
    if cadence not in CADENCIAS:
        raise ValueError("cadência: daily, weekly ou custom")
    if cadence == "custom":
        n = int(every_days or 0)
        if not (1 <= n <= 90):
            raise ValueError("período personalizado: entre 1 e 90 dias")
        return n
    return CADENCIAS[cadence]


def hoje_local():
    from command_center.api.agenda import FUSO
    return datetime.now(FUSO).date()


def configurar(con, user_id, invoice_ids, cadence, every_days=None, enabled=True):
    """Cria ou atualiza o lembrete de cada invoice. Devolve os lembretes resultantes."""
    n = dias_da_cadencia(cadence, every_days)
    hoje = hoje_local().isoformat()
    saida = []
    for iid in invoice_ids:
        inv = um(con, "SELECT id, client_id, status, balance, doc_number FROM invoices WHERE id=?", (iid,))
        if not inv:
            continue
        atual = um(con, "SELECT * FROM invoice_reminders WHERE invoice_id=?", (iid,))
        campos = dict(cadence=cadence, every_days=n, enabled=1 if enabled else 0, updated_at=agora(), updated_by=user_id)
        if atual:
            # religar um lembrete que já mandou mantém o ritmo a partir de hoje
            if enabled and not atual["enabled"]:
                campos["next_on"] = hoje
            con.execute("UPDATE invoice_reminders SET cadence=:cadence, every_days=:every_days, enabled=:enabled, updated_at=:updated_at, updated_by=:updated_by"
                        + (", next_on=:next_on" if "next_on" in campos else "") + " WHERE id=:id", {**campos, "id": atual["id"]})
            rid = atual["id"]
        else:
            rid = inserir(con, "invoice_reminders", invoice_id=iid, client_id=inv["client_id"], next_on=hoje, created_by=user_id, **campos)
        auditar(con, "invoice.reminder.configured", f"user:{user_id}", user_id=user_id, entity_type="invoice", entity_id=iid,
                detail={"doc_number": inv["doc_number"], "cadence": cadence, "every_days": n, "enabled": bool(enabled)})
        saida.append(um(con, "SELECT * FROM invoice_reminders WHERE id=?", (rid,)))
    return saida


def alternar(con, user_id, rid, enabled=None, cadence=None, every_days=None):
    r = um(con, "SELECT * FROM invoice_reminders WHERE id=?", (rid,))
    if not r:
        return None
    novo_cad = cadence or r["cadence"]
    n = dias_da_cadencia(novo_cad, every_days if every_days is not None else r["every_days"])
    en = r["enabled"] if enabled is None else (1 if enabled else 0)
    next_on = r["next_on"]
    if en and not r["enabled"]:
        next_on = hoje_local().isoformat()
    con.execute("UPDATE invoice_reminders SET enabled=?, cadence=?, every_days=?, next_on=?, updated_at=?, updated_by=? WHERE id=?",
                (en, novo_cad, n, next_on, agora(), user_id, rid))
    auditar(con, "invoice.reminder.toggled", f"user:{user_id}", user_id=user_id, entity_type="invoice", entity_id=r["invoice_id"],
            detail={"enabled": bool(en), "cadence": novo_cad, "every_days": n})
    return um(con, "SELECT * FROM invoice_reminders WHERE id=?", (rid,))


def _qbo_id(con, invoice_id):
    l = um(con, "SELECT external_id FROM entity_links WHERE entity_type='invoice' AND entity_id=? AND system IN ('quickbooks','qbo')", (invoice_id,))
    return l["external_id"] if l else None


def enviar(con, r, por="agenda"):
    """Manda UM lembrete (reenvio da invoice pelo QuickBooks). Devolve o resultado, sem levantar.
    A chamada ao provider é `chamar`, para o teste poder trocar."""
    from command_center.providers import NaoConectado, chamar
    inv = um(con, "SELECT * FROM invoices WHERE id=?", (r["invoice_id"],))
    if not inv:
        return {"ok": False, "motivo": "invoice não está mais no espelho"}
    if inv["status"] not in ABERTAS or not (inv["balance"] or 0) > 0:
        con.execute("UPDATE invoice_reminders SET enabled=0, note='invoice paga — lembrete desligado sozinho', updated_at=? WHERE id=?", (agora(), r["id"]))
        auditar(con, "invoice.reminder.stopped", "system", entity_type="invoice", entity_id=inv["id"], detail={"doc_number": inv["doc_number"], "motivo": "paga"})
        return {"ok": False, "motivo": "invoice já paga; lembrete desligado"}
    ext = _qbo_id(con, inv["id"])
    if not ext:
        return {"ok": False, "motivo": "invoice sem vínculo com o QuickBooks"}
    try:
        res = chamar("quickbooks", "qbo_enviar_invoice", id=ext)
    except NaoConectado as e:
        return {"ok": False, "motivo": f"QuickBooks não conectado: {e}"}
    except Exception as e:
        return {"ok": False, "motivo": f"{type(e).__name__}: {str(e)[:200]}"}
    aplicado = bool(res.get("aplicado"))
    proximo = (hoje_local() + timedelta(days=int(r["every_days"] or 1))).isoformat()
    con.execute("UPDATE invoice_reminders SET last_sent_at=?, sent_count=COALESCE(sent_count,0)+1, next_on=?, note=?, updated_at=? WHERE id=?",
                (agora(), proximo, None if aplicado else "último envio foi simulação (APLICAR=0)", agora(), r["id"]))
    auditar(con, "invoice.reminder.sent" if aplicado else "invoice.reminder.simulated", f"user:{por}" if isinstance(por, int) else por,
            user_id=por if isinstance(por, int) else None, entity_type="invoice", entity_id=inv["id"],
            detail={"doc_number": inv["doc_number"], "balance": inv["balance"], "para": res.get("enviado_para") or inv["customer_email"], "proximo": proximo, "res": {k: v for k, v in res.items() if k != "link"}})
    return {"ok": True, "aplicado": aplicado, "proximo": proximo, "para": res.get("enviado_para"), "doc_number": inv["doc_number"]}


def devidos(con, hoje=None):
    hoje = (hoje or hoje_local()).isoformat()
    return todos(con, "SELECT r.* FROM invoice_reminders r JOIN invoices i ON i.id=r.invoice_id WHERE r.enabled=1 AND r.next_on<=? ORDER BY r.id", (hoje,))


def rodar(con, hoje=None):
    """A rotina do dia: manda o que está devido. Chamada pela agenda (09:00)."""
    enviados, parados, falhas = [], [], []
    for r in devidos(con, hoje):
        res = enviar(con, r, por="agenda")
        (enviados if res.get("ok") else parados if "paga" in (res.get("motivo") or "") else falhas).append({"invoice_id": r["invoice_id"], **res})
    con.commit()
    return {"enviados": len(enviados), "parados": len(parados), "falhas": len(falhas), "detalhe": (enviados + parados + falhas)[:20]}


def listar(con, client_id=None):
    sql = """SELECT r.*, i.doc_number, i.balance, i.amount, i.status AS invoice_status, i.due_on, c.name AS client_name, c.pilot_name
             FROM invoice_reminders r JOIN invoices i ON i.id=r.invoice_id LEFT JOIN clients c ON c.id=i.client_id"""
    p = ()
    if client_id:
        sql += " WHERE r.client_id=?"; p = (client_id,)
    return todos(con, sql + " ORDER BY r.enabled DESC, r.next_on", p)


CAMPOS_NA_INVOICE = """(SELECT r.id FROM invoice_reminders r WHERE r.invoice_id=i.id) AS reminder_id,
          (SELECT r.enabled FROM invoice_reminders r WHERE r.invoice_id=i.id) AS reminder_enabled,
          (SELECT r.cadence FROM invoice_reminders r WHERE r.invoice_id=i.id) AS reminder_cadence,
          (SELECT r.every_days FROM invoice_reminders r WHERE r.invoice_id=i.id) AS reminder_every_days,
          (SELECT r.next_on FROM invoice_reminders r WHERE r.invoice_id=i.id) AS reminder_next_on,
          (SELECT r.last_sent_at FROM invoice_reminders r WHERE r.invoice_id=i.id) AS reminder_last_sent_at,
          (SELECT r.sent_count FROM invoice_reminders r WHERE r.invoice_id=i.id) AS reminder_sent_count,
          (SELECT r.note FROM invoice_reminders r WHERE r.invoice_id=i.id) AS reminder_note"""

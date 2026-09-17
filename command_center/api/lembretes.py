"""Lembretes recorrentes de invoice em aberto (dono, 16/09).

Pedido: *"um botão nos clientes para mandar reminders — diário, semanal ou um período
personalizado de dias — com o toggle de ligar e desligar; tanto no perfil do cliente
quanto no QuickBooks, onde eu seleciono as invoices que quero nesses reminders."*

Como funciona:
- Um lembrete por invoice (`invoice_reminders`). Cadência: `daily` (1 dia), `weekly`
  (7 dias) ou `custom` (N dias). Ligado/desligado.
- A rotina `lembrete_invoice` roda uma vez por dia (agenda, 09:00 de Orlando): desliga os
  lembretes de invoice paga e entrega à IA a lista do que está devido. **O disparo é da
  IA** (dono, 17/09): ela propõe `qbo_lembrete_invoice` (SAFE), o executor confere que o
  lembrete está ligado, e o painel marca o próximo dia. Invoice paga desliga sozinha.
- O envio é o reenvio da invoice pelo QuickBooks, para o BillEmail. Sem APLICAR=1 é
  simulação, e fica registrado como simulação.
- Quem liga o lembrete é um MANAGER, na tela: essa é a aprovação humana — por isso a
  ação da IA é SAFE e não passa pela fila de aprovações. "Enviar agora" é botão humano.
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


def lembrete_do_qbo(con, qbo_id):
    """O lembrete da invoice que tem esse id no QuickBooks (para a trava do executor)."""
    l = um(con, "SELECT entity_id FROM entity_links WHERE entity_type='invoice' AND external_id=? AND system IN ('quickbooks','qbo')", (str(qbo_id),))
    return um(con, "SELECT * FROM invoice_reminders WHERE invoice_id=?", (l["entity_id"],)) if l else None


def registrar_envio(con, qbo_id, res, por="ia"):
    """Depois que a IA disparou `qbo_lembrete_invoice`: marca o próximo dia, conta, audita."""
    r = lembrete_do_qbo(con, qbo_id)
    if not r:
        return None
    inv = um(con, "SELECT * FROM invoices WHERE id=?", (r["invoice_id"],))
    aplicado = bool(res.get("aplicado"))
    proximo = (hoje_local() + timedelta(days=int(r["every_days"] or 1))).isoformat()
    con.execute("UPDATE invoice_reminders SET last_sent_at=?, sent_count=COALESCE(sent_count,0)+1, next_on=?, note=?, updated_at=? WHERE id=?",
                (agora(), proximo, None if aplicado else "último envio foi simulação (APLICAR=0)", agora(), r["id"]))
    auditar(con, "invoice.reminder.sent" if aplicado else "invoice.reminder.simulated", por, entity_type="invoice", entity_id=r["invoice_id"],
            detail={"doc_number": inv["doc_number"] if inv else None, "para": res.get("enviado_para"), "proximo": proximo, "por": por})
    return proximo


def rodar(con, hoje=None):
    """A rotina do dia (agenda, 09:00). Dono, 17/09: *"a escolha de quais lembretes são meus;
    o disparo é da IA."* Então o painel não envia: fecha os lembretes pagos, e entrega à IA a
    lista do que está devido, com o id de cada invoice no QuickBooks. A IA dispara com
    `qbo_lembrete_invoice` (SAFE), o executor confere que o lembrete está ligado e o painel
    marca o próximo dia. Se a IA não rodar hoje, `next_on` fica no passado e amanhã volta."""
    devidas, parados = [], []
    for r in devidos(con, hoje):
        inv = um(con, "SELECT * FROM invoices WHERE id=?", (r["invoice_id"],))
        if not inv or inv["status"] not in ABERTAS or not (inv["balance"] or 0) > 0:
            con.execute("UPDATE invoice_reminders SET enabled=0, note='invoice paga — lembrete desligado sozinho', updated_at=? WHERE id=?", (agora(), r["id"]))
            auditar(con, "invoice.reminder.stopped", "system", entity_type="invoice", entity_id=r["invoice_id"], detail={"doc_number": inv["doc_number"] if inv else None, "motivo": "paga"})
            parados.append(r["invoice_id"]); continue
        ext = _qbo_id(con, inv["id"])
        if not ext:
            continue
        devidas.append({"invoice_id": inv["id"], "qbo_id": ext, "doc_number": inv["doc_number"], "saldo": inv["balance"], "vence": inv["due_on"],
                        "cadencia": r["cadence"], "dias": r["every_days"], "cliente": (um(con, "SELECT name, pilot_name, email FROM clients WHERE id=?", (inv["client_id"],)) or {}) if inv["client_id"] else {}})
    con.commit()
    if not devidas:
        return {"devidos": 0, "parados": len(parados), "command_id": None}
    from command_center.api import ia
    admin = um(con, "SELECT id FROM users WHERE role='ADMIN' AND active=1 ORDER BY id LIMIT 1")
    if not admin:
        return {"devidos": len(devidas), "parados": len(parados), "command_id": None, "motivo": "sem usuário ADMIN para assinar o comando"}
    linhas = "\n".join(f"- invoice {d['doc_number']} (id no QuickBooks: {d['qbo_id']}) · saldo ${d['saldo']} · vence {d['vence']} · cliente {d['cliente'].get('name') or '?'}"
                        f"{(' (piloto ' + d['cliente']['pilot_name'] + ')') if d['cliente'].get('pilot_name') else ''} · cadência {d['cadencia']} ({d['dias']} dias)" for d in devidas)
    texto = ("EVENTO AUTOMÁTICO: lembretes de invoice devidos hoje. O gerente ligou o lembrete destas invoices em aberto; "
             "o disparo é seu. Para CADA uma, proponha `ACAO: qbo_lembrete_invoice | <doc_number> | lembrete | {\"id\":\"<id no QuickBooks>\"}` — "
             "é SAFE e executa sozinha; o painel confere que o lembrete está ligado e marca o próximo dia. Não crie invoice, não mude valor, "
             "não mande e-mail por outro caminho. Se o cliente tiver tarefa aberta no Asana, um comentário curto ([IA ADM] lembrete de invoice enviado) ajuda.\n" + linhas)
    session_key = f"agent:{ia.AGENTE}:lembretes-{hoje_local().isoformat()}"
    cid = inserir(con, "ai_commands", user_id=admin["id"], text=texto, session_key=session_key)
    auditar(con, "invoice.reminder.handoff", "system", entity_type="ai_command", entity_id=cid, detail={"devidos": [d["doc_number"] for d in devidas]})
    con.commit()
    import threading
    threading.Thread(target=ia._executa, args=(cid, texto, session_key, admin["id"]), daemon=True).start()
    return {"devidos": len(devidas), "parados": len(parados), "command_id": cid}


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

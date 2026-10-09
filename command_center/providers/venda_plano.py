"""Plano mensal vendido pelo site (#169): Academy e Boost, sem a equipe no meio.

Dono, 09/10: *"Vender online já: invoice recorrente do QuickBooks criada pelo site"*. O que acontece
quando o cliente escolhe o plano, entra na conta, diz quem é o piloto e clica em pagar:

1. o card do piloto é garantido (a mesma regra da sessão avulsa, `venda_site.garantir_card`);
2. o card ganha o **contrato**: `plan_type='monthly'`, valor, item do QuickBooks e sessões por mês —
   é o que faz as sessões marcadas depois contarem no plano, sem cobrar de novo (decisão de 06/10);
3. a **primeira mensalidade** sai na hora pelo QuickBooks, com o link de pagamento do cliente;
4. as **outras** ficam agendadas no dia 1 às 01:00 (`monthly_invoices`, como a tela Mensalidade do
   painel, #63): uma por mês, nunca duas;
5. a waiver sai pelo DocuSign (ou é assinada na área do cliente, com a nativa ligada);
6. pago + waiver → o plano fica **ativo** e o cliente recebe o e-mail.

Tudo aparece no painel: card do cliente (contrato e Mensalidade) e auditoria. Nada é cobrado
sem a venda automática ligada (Site › Disponibilidade).
"""
import json
from datetime import date, datetime, timedelta, timezone

from command_center.db import agora, atualizar, auditar, inserir, todos, um
from command_center.providers import cobranca_agenda as cob
from command_center.providers import mensalidades, servicos_site
from command_center.providers import venda_site as vsite

CONFERIR_A_CADA_S = 60


class ErroPlano(ValueError):
    """Mensagem em inglês: é o que o cliente lê."""


def _mes_atual():
    return mensalidades.agora_fl().date().replace(day=1)


def pedir(con, conta_id, service_id, pilot_id, origin=None, utm=None):
    """O pedido do cliente: plano ativo, piloto da própria conta. Devolve o id."""
    try:
        s = servicos_site.plano(con, service_id)
    except servicos_site.ErroServico as e:
        raise ErroPlano(str(e))
    p = um(con, "SELECT * FROM portal_pilots WHERE id=? AND account_id=? AND active=1", (pilot_id, conta_id)) if pilot_id else None
    if not p:
        raise ErroPlano("Choose the driver of this plan.")
    if not p["birth_date"]:
        raise ErroPlano("Add the driver's date of birth first.")
    aberto = um(con, """SELECT id FROM plan_orders WHERE account_id=? AND pilot_id=? AND status='pendente'
                         AND created_at > ?""", (conta_id, pilot_id, (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")))
    if aberto:
        return aberto["id"]                       # o mesmo pedido de ontem continua valendo: nada de duas invoices
    oid = inserir(con, "plan_orders", account_id=conta_id, pilot_id=pilot_id, service_id=s["id"], service_name=s["name"],
                  price=float(s["price"]), months=int(s["months"] or 1), sessions_month=s["sessions_month"],
                  start_month=_mes_atual().strftime("%Y-%m"), origin="site" if origin == "site" else "portal",
                  utm=vsite.utm_limpo(utm))
    auditar(con, "plan.order", "system", entity_type="plan_order", entity_id=oid,
            detail={"account": conta_id, "pilot": pilot_id, "service": s["id"], "months": s["months"]})
    return oid


# ------------------------------------------------------------------ a venda
def _contrato_no_card(con, o, s):
    """O card passa a ter o plano: é o que `contrato.tem_contrato` lê."""
    atualizar(con, "clients", o["client_id"], plan_type="monthly", monthly_plan=s["name"], monthly_amount=float(o["price"]),
              monthly_item_id=s["qbo_item_id"], monthly_sessions=o["sessions_month"] or None)


def _descricao(o, piloto, mes):
    a, m = [int(x) for x in mes.split("-")]
    return f"{o['service_name']} — {piloto} [{mensalidades.MESES_EN[m - 1]}, {a}]"


def _primeira_mensalidade(con, o, s, qbo, email, piloto, enviar):
    """A invoice deste mês, agora, com o link de pagamento; e a linha dela em monthly_invoices."""
    mes = o["start_month"]
    ja = mensalidades.invoice_do_mes(con, o["client_id"], mes)
    if ja:
        raise cob.ErroCobranca(f"este mês já tem mensalidade no QuickBooks ({ja['doc_number']})")
    res = enviar(cliente_id=qbo, linhas=[{"item_id": s["qbo_item_id"], "quantidade": 1, "unitario": float(o["price"]),
                                          "descricao": _descricao(o, piloto, mes)}],
                 vence_em=date.today().isoformat(), memo=_descricao(o, piloto, mes), email=email)
    if not res or res.get("aplicado") is False:
        raise cob.ErroCobranca("o QuickBooks não criou a invoice (simulação)")
    atualizar(con, "plan_orders", o["id"], qbo_invoice_id=str(res.get("id") or ""), invoice_doc=res.get("numero"),
              invoice_total=res.get("total"), invoice_link=res.get("link"), pay_link=res.get("link_pagamento"),
              invoice_sent_to=res.get("enviado_para"), charge_error=None, updated_at=agora())
    return res


def _agendar_resto(con, o, s, email, piloto, res):
    """monthly_recurring + uma linha por mês: a deste mês já enviada, as outras no dia 1 às 01:00."""
    inicio = date.fromisoformat(o["start_month"] + "-01")
    fim = mensalidades.soma_mes(inicio, o["months"] - 1)
    rid = inserir(con, "monthly_recurring", client_id=o["client_id"], qbo_id=None, name=f"{o['service_name']} {piloto} {o['start_month']}",
                  amount=float(o["price"]), item_id=s["qbo_item_id"], months=o["months"], start_on=inicio.isoformat(),
                  end_on=fim.isoformat(), email=email, status="active",
                  result=json.dumps({"modo": "site", "primeira": res.get("numero"), "envio": f"dia 1 às {mensalidades.HORA_ENVIO}"}))
    inserir(con, "monthly_invoices", recurring_id=rid, client_id=o["client_id"], month=o["start_month"], amount=float(o["price"]),
            item_id=s["qbo_item_id"], description=_descricao(o, piloto, o["start_month"]), email=email,
            send_at=f"{inicio.isoformat()} {mensalidades.HORA_ENVIO}", status="enviada", qbo_id=str(res.get("id") or ""),
            doc_number=res.get("numero"), sent_at=agora(), note="primeira mensalidade: vendida pelo site")
    if o["months"] > 1:
        mensalidades.agendar(con, None, o["client_id"], rid, mensalidades.soma_mes(inicio, 1), o["months"] - 1,
                             float(o["price"]), s["qbo_item_id"], f"{o['service_name']} — {piloto}", email)
    atualizar(con, "plan_orders", o["id"], recurring_id=rid, updated_at=agora())
    return rid


def vender(con, oid, por=None, enviar_invoice=None, enviar_waiver=None, criar_qbo=None, enviar_email=None):
    """O pedido vira cobrança e contrato na hora (venda automática ligada). Devolve as etapas."""
    o = um(con, "SELECT * FROM plan_orders WHERE id=?", (oid,))
    if not o or not vsite.ligada(con) or o["status"] != "pendente" or o["qbo_invoice_id"]:
        return None
    s = um(con, "SELECT * FROM booking_services WHERE id=?", (o["service_id"],))
    a = um(con, "SELECT * FROM portal_accounts WHERE id=?", (o["account_id"],))
    p = um(con, "SELECT * FROM portal_pilots WHERE id=?", (o["pilot_id"],))
    piloto = p["name"] if p else a["name"]
    try:
        if not o["client_id"]:
            card, nota = vsite.garantir_card(con, o, por)
            atualizar(con, "plan_orders", oid, client_id=card, card_note=(nota or "")[:300] or None, updated_at=agora())
            o = um(con, "SELECT * FROM plan_orders WHERE id=?", (oid,))
            auditar(con, "plan.card", "system", entity_type="plan_order", entity_id=oid, detail={"client_id": card, "nota": nota})
        if not s["qbo_item_id"]:
            raise cob.ErroCobranca("o plano não tem item do QuickBooks: escolha o item em Site público › Serviços")
        try:
            qbo = mensalidades._cliente_qbo(con, o["client_id"])
        except Exception as e:                                     # noqa: BLE001 — QuickBooks fora do ar
            raise cob.ErroCobranca(f"QuickBooks indisponível: {getattr(e, 'detail', e)}")
        if not qbo:
            qbo = vsite.criador_de_cliente_qbo(con, {"account_id": o["account_id"], "id": oid}, criar_qbo)(o["client_id"])
        _contrato_no_card(con, o, s)
        res = _primeira_mensalidade(con, o, s, qbo, a["email"], piloto, enviar_invoice or cob._enviar_padrao)
        _agendar_resto(con, o, s, a["email"], piloto, res)
        auditar(con, "plan.invoice", "system", entity_type="plan_order", entity_id=oid,
                detail={"invoice": res.get("numero"), "total": res.get("total"), "client_id": o["client_id"], "meses": o["months"]})
    except Exception as e:                                         # noqa: BLE001 — fica escrito; a equipe vê no card
        atualizar(con, "plan_orders", oid, charge_error=str(e)[:300], updated_at=agora())
    o = um(con, "SELECT * FROM plan_orders WHERE id=?", (oid,))
    cob.pedir_waiver(con, _como_sessao(o), enviar_waiver, tabela="plan_orders", card=o["client_id"],
                     motivo=f"site: plano #{oid} ({o['service_name']})")
    auditar(con, "plan.auto_sell", "system", entity_type="plan_order", entity_id=oid)
    verificar(con, oid)
    avisar_recebido(con, oid, enviar_email)
    return checkout(con, oid)


def _como_sessao(o):
    """O que `cobranca_agenda` espera de um agendamento: o plano vale a partir de hoje."""
    d = dict(o)
    d["date"] = date.today().isoformat()
    return d


def waiver_ok(con, o):
    return cob.waiver_em_dia(con, _como_sessao(o), o["client_id"] or 0)


def verificar(con, oid):
    """Primeira mensalidade paga + waiver em dia → plano ativo, sozinho."""
    o = um(con, "SELECT * FROM plan_orders WHERE id=?", (oid,))
    if not o or o["status"] != "pendente" or not o["paid_at"] or not waiver_ok(con, o):
        return False
    atualizar(con, "plan_orders", oid, status="ativa", updated_at=agora())
    auditar(con, "plan.active", "system", entity_type="plan_order", entity_id=oid, detail={"invoice": o["invoice_doc"]})
    return True


def conferir_pagamento(con, oid, ler=None, enviar_email=None, agora_dt=None):
    """Quem está na tela não espera o espelho: confere a invoice no QuickBooks, 1 vez por minuto."""
    o = um(con, "SELECT * FROM plan_orders WHERE id=?", (oid,))
    if not o or not o["qbo_invoice_id"] or o["paid_at"] or o["status"] != "pendente":
        return False
    agora_dt = agora_dt or datetime.now(timezone.utc)
    if o["pay_checked_at"]:
        try:
            if agora_dt - datetime.fromisoformat(o["pay_checked_at"].replace("Z", "+00:00")) < timedelta(seconds=CONFERIR_A_CADA_S):
                return False
        except ValueError:
            pass
    mud = {"pay_checked_at": agora_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")}
    try:
        r = (ler or vsite._ler_padrao)(o["qbo_invoice_id"]) or {}
    except Exception:                                               # noqa: BLE001 — sem QuickBooks agora
        r = {}
    if r.get("link_pagamento") and not o["pay_link"]:
        mud["pay_link"] = r["link_pagamento"]
    pago = (r.get("saldo") is not None and float(r["saldo"]) <= 0 and float(r.get("total") or 0) > 0) or r.get("status") == "paid"
    if pago:
        mud["paid_at"] = agora()
    atualizar(con, "plan_orders", oid, **mud)
    if pago:
        auditar(con, "plan.paid", "system", entity_type="plan_order", entity_id=oid, detail={"invoice": o["invoice_doc"]})
        if verificar(con, oid):
            avisar_ativo(con, oid, enviar_email)
    return pago


# ------------------------------------------------------------------ o que o cliente vê
def checkout(con, oid):
    o = um(con, """SELECT o.*, p.name AS driver, p.birth_date, p.is_self, p.email AS driver_email, a.email AS account_email
                     FROM plan_orders o JOIN portal_accounts a ON a.id=o.account_id LEFT JOIN portal_pilots p ON p.id=o.pilot_id
                    WHERE o.id=?""", (oid,))
    from command_center.providers import waiver_nativa
    nativa = waiver_nativa.ligada(con)
    w_ok = waiver_ok(con, o)
    w = "ok" if w_ok else ("erro" if o["waiver_error"] else ("enviada" if o["waiver_ref"] else "pendente"))
    waiver = {"estado": "ok" if w == "ok" else ("assinar_aqui" if nativa else ("email" if w == "enviada" else
                                                                                 "equipe" if w == "erro" else "preparando")),
              "link": f"/portal/drivers/{o['pilot_id']}/waiver" if nativa and w != "ok" and o["pilot_id"] else None}
    if waiver["estado"] == "email":
        menor = o["birth_date"] and cob._idade(date.fromisoformat(o["birth_date"]), date.today()) < cob.MAIORIDADE
        waiver["para"] = o["account_email"] if (menor or o["is_self"]) else (o["driver_email"] or o["account_email"])
    pg = "pago" if o["paid_at"] else ("enviada" if o["qbo_invoice_id"] else ("erro" if o["charge_error"] else "pendente"))
    pagamento = {"estado": {"pago": "pago", "enviada": "pagar", "erro": "equipe"}.get(pg, "preparando"),
                 "link": o["pay_link"] if pg == "enviada" else None, "invoice": o["invoice_doc"],
                 "total": o["invoice_total"], "para": o["invoice_sent_to"]}
    proximos = [m["month"] for m in todos(con, """SELECT month FROM monthly_invoices WHERE recurring_id=? AND status='a_enviar'
                                                   ORDER BY month""", (o["recurring_id"],))] if o["recurring_id"] else []
    return {"id": o["id"], "status": o["status"], "plan": o["service_name"], "price": o["price"], "months": o["months"],
            "sessions_month": o["sessions_month"], "total": round(o["price"] * o["months"], 2), "driver": o["driver"],
            "start_month": o["start_month"], "next_months": proximos, "aceita": bool(o["qbo_invoice_id"] or o["charge_error"]),
            "pagamento": pagamento, "waiver": waiver, "ativo": o["status"] == "ativa"}


# ------------------------------------------------------------------ e-mails ao cliente
def _link(oid):
    from command_center import enderecos
    return f"https://{enderecos.CLIENTE}/ops/portal/plans/{oid}"


def _mes(m):
    a, n = [int(x) for x in m.split("-")]
    return f"{mensalidades.MESES_EN[n - 1]} {a}"


def avisar_recebido(con, oid, enviar_email=None):
    o = um(con, "SELECT * FROM plan_orders WHERE id=?", (oid,))
    if not o or o["notified_received_at"] or not vsite.ligada(con):
        return False
    c = checkout(con, oid)
    a = um(con, "SELECT name, email FROM portal_accounts WHERE id=?", (o["account_id"],))
    passos = []
    if c["pagamento"]["estado"] == "pagar":
        passos.append(f"1. Pay the first month{' (invoice ' + c['pagamento']['invoice'] + ')' if c['pagamento']['invoice'] else ''}: "
                      f"{c['pagamento']['link'] or 'it is in your email from QuickBooks'}")
    elif c["pagamento"]["estado"] == "preparando":
        passos.append("1. Pay the first month: the invoice is on its way to your email from QuickBooks.")
    if c["waiver"]["estado"] == "assinar_aqui":
        passos.append(f"{len(passos) + 1}. Sign the waiver in your URACE account: {_link(oid)}")
    elif c["waiver"]["estado"] in ("email", "preparando"):
        passos.append(f"{len(passos) + 1}. Sign the waiver: it is in your email from DocuSign"
                      f"{' (sent to ' + c['waiver']['para'] + ')' if c['waiver'].get('para') else ''}.")
    proximos = (f"The next months ({', '.join(_mes(m) for m in c['next_months'])}) are invoiced on the 1st of each month, "
                f"${o['price']:,.2f} each.\n\n") if c["next_months"] else ""
    texto = (f"Hi {a['name'].split(' ')[0]},\n\nWelcome to {o['service_name']}! Here is your plan:\n\n"
             f"{o['service_name']} · {o['months']} month{'s' if o['months'] > 1 else ''} · ${o['price']:,.2f} per month"
             f"{' · ' + c['driver'] if c['driver'] else ''}\n\n"
             + ("To start:\n" + "\n".join(passos) + "\n\nIt activates by itself as soon as both are done.\n\n" if passos else "")
             + proximos
             + f"Then book your sessions any time in your URACE account: {_link(oid)}\n\n"
             "Questions? Reply to this email or write to support@urace.us.\n\nURACE.US · Orlando, FL")
    try:
        vsite._enviar(enviar_email, a["email"], f"Your {o['service_name']} plan: what's next", texto)
        atualizar(con, "plan_orders", oid, notified_received_at=agora())
        return True
    except Exception as e:                                         # noqa: BLE001
        atualizar(con, "plan_orders", oid, notify_error=f"e-mail de recebimento: {e}"[:300])
        return False


def avisar_ativo(con, oid, enviar_email=None):
    o = um(con, "SELECT * FROM plan_orders WHERE id=?", (oid,))
    if not o or o["status"] != "ativa" or o["notified_confirmed_at"] or not vsite.ligada(con):
        return False
    a = um(con, "SELECT name, email FROM portal_accounts WHERE id=?", (o["account_id"],))
    texto = (f"Hi {a['name'].split(' ')[0]},\n\nYour {o['service_name']} plan is active. "
             f"{'Book up to ' + str(o['sessions_month']) + ' sessions a month' if o['sessions_month'] else 'Book your sessions'} "
             f"in your URACE account: {_link(oid)}\n\nYour URACE QR is in your account: show it at the shop.\n\nURACE.US · Orlando, FL")
    try:
        vsite._enviar(enviar_email, a["email"], f"Your {o['service_name']} plan is active", texto)
        atualizar(con, "plan_orders", oid, notified_confirmed_at=agora())
        return True
    except Exception as e:                                         # noqa: BLE001
        atualizar(con, "plan_orders", oid, notify_error=f"e-mail de ativação: {e}"[:300])
        return False

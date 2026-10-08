"""Venda automática do site (#164).

Dono, 08/10: *"eu preciso que as etapas de compra sejam sempre respeitadas ... ou ela loga ou ela cria
a conta dela ... daí ela vai para a etapa de compra: QuickBooks, manda a invoice, já paga o security
deposit, já assina o waiver por ali mesmo, e dali ela recebe a confirmação ... Um site totalmente
automático que venda sozinho, sem precisar de um humano."*

Com a **venda automática** ligada (Site público › Agenda; nasce desligada), o pedido feito pelo cliente
não espera a equipe "Aceitar": na mesma hora

1. **o card do piloto** existe (ou é ligado ao card que já é dele, ou é criado);
2. **o cliente no QuickBooks** existe (é achado pelo e-mail, ou criado);
3. a regra do #50 roda igual (`cobranca_agenda.aceitar`): invoice do serviço + depósito, e a waiver;
4. o cliente recebe um e-mail com o que falta, e a tela mostra as etapas até "confirmada".

As etapas não se pulam: sem conta não há pedido; sem pagamento e waiver a sessão não confirma (#50).

**Card (a regra "nunca pôr serviço de um cliente no card de outro" continua):** ligar sozinho a um card
que já existe só acontece com duas provas juntas: o **e-mail confirmado** da conta é o e-mail do card E o
**nome do piloto** é o do card. Qualquer outra semelhança vira **card novo** marcado "possível
duplicado" para a equipe conferir e unir (nada do histórico de outra pessoa aparece para o cliente).
"""
import json
from datetime import datetime, timedelta, timezone

from command_center.db import agora, atualizar, auditar, inserir, todos, um
from command_center.providers import agenda_sessoes as ag
from command_center.providers import cobranca_agenda as cob
from command_center.providers import identidade
from command_center.providers import vinculo_site as vs

CONFERIR_A_CADA_S = 60          # conferência direta do pagamento no QuickBooks, no máximo 1 por minuto


def ligada(con):
    return bool(ag.config(con).get("auto_sell"))


# ------------------------------------------------------------------ card do piloto
def _nome(x):
    return identidade.normaliza(x or "")


def garantir_card(con, b, por=None):
    """(client_id, nota). O card do piloto do pedido: o que ele já tem, o que é comprovadamente dele, ou novo."""
    p = um(con, "SELECT * FROM portal_pilots WHERE id=?", (b["pilot_id"],)) if b["pilot_id"] else None
    if not p:
        raise cob.ErroCobranca("o pedido não tem piloto")
    if p["client_id"]:
        return p["client_id"], None
    a = um(con, "SELECT * FROM portal_accounts WHERE id=?", (b["account_id"],))
    if a["email_verified_at"] and a["email"]:
        ocupados = vs._ocupados(con, a["id"])
        cands = [c for c in todos(con, """SELECT * FROM clients WHERE LOWER(email)=LOWER(?) OR LOWER(COALESCE(email_alt,''))=LOWER(?)""",
                                  (a["email"], a["email"]))
                 if c["id"] not in ocupados and _nome(c["pilot_name"] or c["name"]) == _nome(p["name"])
                 and not um(con, "SELECT 1 AS x FROM portal_pilots WHERE client_id=? AND id<>?", (c["id"], p["id"]))]
        if len(cands) == 1:
            vs.vincular_driver(con, p["id"], cands[0]["id"], por)
            return cands[0]["id"], f"ligado ao card {cands[0]['id']}: mesmo e-mail confirmado e mesmo piloto"
    try:
        return vs.criar_cliente_driver(con, p["id"], por), "card novo criado pela venda do site"
    except vs.ErroVinculo as e:
        # parecido com um card que já existe, sem prova suficiente para ligar: a venda não espera a
        # equipe; o card é novo e fica marcado para conferir e unir (ninguém vê o histórico de outro)
        cid = inserir(con, "clients", name=a["name"], email=a["email"], phone=a["phone"], pilot_name=p["name"],
                      pilot_dob=p["birth_date"], status="NEW", source="site",
                      notes=f"Criado pela venda do site (conta #{a['id']}, driver {p['name']}). POSSÍVEL DUPLICADO: {e}. Confira e una.")
        vs.vincular_driver(con, p["id"], cid, por)
        return cid, f"card novo {cid}, possível duplicado: {e}"


# ------------------------------------------------------------------ cliente no QuickBooks
def _criar_qbo_padrao(nome, email=None, telefone=None):
    from command_center import providers
    from command_center.providers.mensalidades import _aplicando
    return _aplicando(providers.modulo("quickbooks").qbo_criar_cliente, nome=nome, email=email, telefone=telefone)


def criador_de_cliente_qbo(con, b, criar=None):
    """A função que `cobranca_agenda.cobrar` chama quando o card ainda não tem cliente no QuickBooks."""
    def _criar(card):
        a = um(con, "SELECT name, email, phone FROM portal_accounts WHERE id=?", (b["account_id"],))
        res = (criar or _criar_qbo_padrao)(nome=a["name"], email=a["email"], telefone=a["phone"])
        if not res or res.get("aplicado") is False or not res.get("id"):
            raise cob.ErroCobranca("o QuickBooks não criou o cliente (simulação)")
        auditar(con, "booking.qbo_customer", "system", entity_type="booking", entity_id=b["id"],
                detail={"client_id": card, "qbo": res.get("id")})
        return str(res["id"])
    return _criar


# ------------------------------------------------------------------ a venda
def vender(con, bid, por=None, enviar_invoice=None, enviar_waiver=None, criar_qbo=None, enviar_email=None):
    """O pedido do cliente vira cobrança na hora (venda automática ligada). Devolve as etapas."""
    b = um(con, "SELECT * FROM bookings WHERE id=?", (bid,))
    if not b or not ligada(con) or b["status"] != "pendente" or b["accepted_at"]:
        return None
    try:
        card, nota = garantir_card(con, b, por)
        if nota:
            atualizar(con, "bookings", bid, card_note=nota[:300], updated_at=agora())
            auditar(con, "booking.card", "system", entity_type="booking", entity_id=bid, detail={"client_id": card, "nota": nota})
    except (vs.ErroVinculo, cob.ErroCobranca) as e:
        atualizar(con, "bookings", bid, card_note=f"erro: {e}"[:300], updated_at=agora())
    cob.aceitar(con, por, bid, enviar_invoice, enviar_waiver,
                criar_cliente=criador_de_cliente_qbo(con, b, criar_qbo))
    auditar(con, "booking.auto_sell", "system", entity_type="booking", entity_id=bid)
    avisar_recebida(con, bid, enviar_email)
    return checkout(con, bid)


# ------------------------------------------------------------------ pagamento (conferência direta)
def _ler_padrao(inv_id):
    from command_center import providers
    return providers.modulo("quickbooks").qbo_invoice_do_cliente(id=inv_id)


def conferir_pagamento(con, bid, ler=None, enviar_email=None, agora_dt=None):
    """Quem está na tela de acompanhamento não espera os 15 min do espelho: confere a invoice
    direto no QuickBooks (só leitura), no máximo uma vez por minuto."""
    b = um(con, "SELECT * FROM bookings WHERE id=?", (bid,))
    if not b or not b["qbo_invoice_id"] or b["paid_at"] or b["status"] != "pendente":
        return False
    agora_dt = agora_dt or datetime.now(timezone.utc)
    if b["pay_checked_at"]:
        try:
            ultima = datetime.fromisoformat(b["pay_checked_at"].replace("Z", "+00:00"))
            if agora_dt - ultima < timedelta(seconds=CONFERIR_A_CADA_S):
                return False
        except ValueError:
            pass
    mud = {"pay_checked_at": agora_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")}
    try:
        r = (ler or _ler_padrao)(b["qbo_invoice_id"]) or {}
    except Exception:                                               # noqa: BLE001 — sem QuickBooks agora: o espelho resolve
        r = {}
    if r.get("link_pagamento") and not b["pay_link"]:
        mud["pay_link"] = r["link_pagamento"]
    pago = (r.get("saldo") is not None and float(r["saldo"]) <= 0 and float(r.get("total") or 0) > 0) or r.get("status") == "paid"
    if pago:
        mud["paid_at"] = agora()
    atualizar(con, "bookings", bid, **mud)
    if pago:
        auditar(con, "booking.paid", "system", entity_type="booking", entity_id=bid, detail={"invoice": b["invoice_doc"]})
        if cob.verificar(con, bid):
            avisar_confirmada(con, bid, enviar_email)
    return pago


# ------------------------------------------------------------------ o que o cliente vê
def checkout(con, bid):
    """As etapas do pedido, na linguagem do cliente (nada de erro interno na tela dele)."""
    b = um(con, """SELECT b.*, p.name AS driver, p.birth_date, p.is_self, p.email AS driver_email, a.email AS account_email
                     FROM bookings b JOIN portal_accounts a ON a.id=b.account_id LEFT JOIN portal_pilots p ON p.id=b.pilot_id
                    WHERE b.id=?""", (bid,))
    s = cob.situacao(con, b)
    from command_center.providers import waiver_nativa
    nativa = waiver_nativa.ligada(con)
    w = s["waiver"]
    waiver = {"estado": "ok" if w == "ok" else ("assinar_aqui" if nativa else ("email" if w == "enviada" else "preparando")),
              "link": f"/portal/drivers/{b['pilot_id']}/waiver" if nativa and w != "ok" and b["pilot_id"] else None}
    if waiver["estado"] == "email":
        menor = b["birth_date"] and cob._idade(datetime.fromisoformat(b["birth_date"]).date(),
                                                datetime.fromisoformat(b["date"]).date()) < cob.MAIORIDADE
        waiver["para"] = b["account_email"] if (menor or b["is_self"]) else (b["driver_email"] or b["account_email"])
    pg = s["pagamento"]
    pagamento = {"estado": {"pago": "pago", "contrato": "contrato", "enviada": "pagar"}.get(pg, "preparando"),
                 "link": b["pay_link"] if pg == "enviada" else None, "invoice": b["invoice_doc"],
                 "total": b["invoice_total"], "para": b["invoice_sent_to"]}
    return {"id": b["id"], "status": b["status"], "date": b["date"], "period": b["period"], "service": b["service_name"],
            "price": b["price"], "driver": b["driver"], "aceita": s["aceita"], "pagamento": pagamento, "waiver": waiver,
            "confirmada": b["status"] == "confirmada"}


# ------------------------------------------------------------------ e-mails ao cliente
def _per(b):
    return {"manha": "morning", "tarde": "afternoon", "dia": "full day"}.get(b["period"], b["period"])


def _link_conta(bid):
    from command_center import enderecos
    return f"https://{enderecos.CLIENTE}/ops/portal/sessions/{bid}"


def _enviar(enviar_email, para, assunto, texto):
    if enviar_email is None:
        from command_center.providers import email_envio
        enviar_email = email_envio.enviar
    return enviar_email(para, assunto, texto)


def avisar_recebida(con, bid, enviar_email=None):
    b = um(con, "SELECT * FROM bookings WHERE id=?", (bid,))
    if not b or b["notified_received_at"] or not ligada(con):
        return False
    c = checkout(con, bid)
    a = um(con, "SELECT name, email FROM portal_accounts WHERE id=?", (b["account_id"],))
    passos = []
    if c["pagamento"]["estado"] == "pagar":
        passos.append(f"1. Pay the invoice{' ' + c['pagamento']['invoice'] if c['pagamento']['invoice'] else ''} "
                      f"(session + refundable security deposit): {c['pagamento']['link'] or 'it is in your email from QuickBooks'}")
    elif c["pagamento"]["estado"] == "preparando":
        passos.append("1. Pay the invoice: it is on its way to your email from QuickBooks.")
    if c["waiver"]["estado"] == "assinar_aqui":
        passos.append(f"{len(passos) + 1}. Sign the waiver in your URACE account: {_link_conta(bid)}")
    elif c["waiver"]["estado"] in ("email", "preparando"):
        passos.append(f"{len(passos) + 1}. Sign the waiver: it is in your email from DocuSign"
                      f"{' (sent to ' + c['waiver']['para'] + ')' if c['waiver'].get('para') else ''}.")
    texto = (f"Hi {a['name'].split(' ')[0]},\n\nThanks for booking with URACE! We are holding your spot:\n\n"
             f"{b['service_name'] or 'Session'} · {b['date'][5:7]}/{b['date'][8:10]}/{b['date'][:4]} ({_per(b)})\n\n"
             + ("To confirm it:\n" + "\n".join(passos) + "\n\nIt confirms by itself as soon as both are done.\n\n" if passos else "")
             + f"Follow your booking any time in your URACE account: {_link_conta(bid)}\n\n"
             "Questions? Reply to this email or write to support@urace.us.\n\nURACE.US · Orlando, FL")
    try:
        _enviar(enviar_email, a["email"], "Your URACE booking: what's next", texto)
        atualizar(con, "bookings", bid, notified_received_at=agora())
        return True
    except Exception as e:                                         # noqa: BLE001 — fica escrito para a equipe
        atualizar(con, "bookings", bid, reminder_error=f"e-mail de recebimento: {e}"[:300])
        return False


def avisar_confirmada(con, bid, enviar_email=None):
    b = um(con, "SELECT * FROM bookings WHERE id=?", (bid,))
    if not b or b["status"] != "confirmada" or b["notified_confirmed_at"] or not ligada(con):
        return False
    a = um(con, "SELECT name, email FROM portal_accounts WHERE id=?", (b["account_id"],))
    texto = (f"Hi {a['name'].split(' ')[0]},\n\nYou're confirmed! See you at the track:\n\n"
             f"{b['service_name'] or 'Session'} · {b['date'][5:7]}/{b['date'][8:10]}/{b['date'][:4]} ({_per(b)})\n\n"
             "Your URACE QR is in your account: show it at the shop.\n"
             f"Your booking: {_link_conta(bid)}\n\nURACE.US · Orlando, FL")
    try:
        _enviar(enviar_email, a["email"], "You're confirmed: your URACE session", texto)
        atualizar(con, "bookings", bid, notified_confirmed_at=agora())
        return True
    except Exception as e:                                         # noqa: BLE001
        atualizar(con, "bookings", bid, reminder_error=f"e-mail de confirmação: {e}"[:300])
        return False


def utm_limpo(utm):
    """Só as chaves de campanha, curtas: de onde veio a venda, para o marketing."""
    if not isinstance(utm, dict):
        return None
    ok = {k: str(v)[:120] for k, v in utm.items()
          if k in ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid", "ref") and v}
    return json.dumps(ok, ensure_ascii=False) if ok else None

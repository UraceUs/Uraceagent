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
import re
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
        mesmas = [bid]
        if b["group_id"]:
            # #314: a invoice das extras do pedido é uma só — paga, vale para todas as sessões dela
            mesmas += [x["id"] for x in todos(con, """SELECT id FROM bookings WHERE group_id=? AND qbo_invoice_id=? AND id<>?
                                                       AND paid_at IS NULL""", (b["group_id"], b["qbo_invoice_id"], bid))]
            for x in mesmas[1:]:
                atualizar(con, "bookings", x, paid_at=mud["paid_at"], pay_checked_at=mud["pay_checked_at"])
        for x in mesmas:
            if cob.verificar(con, x):
                avisar_confirmada(con, x, enviar_email)
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
    waiver = {"estado": "ok" if w == "ok" else ("assinar_aqui" if nativa else ("email" if w == "enviada" else
                                                                                 "equipe" if w == "erro" else "preparando")),
              "link": f"/portal/drivers/{b['pilot_id']}/waiver" if nativa and w != "ok" and b["pilot_id"] else None}
    if waiver["estado"] == "email":
        menor = b["birth_date"] and cob._idade(datetime.fromisoformat(b["birth_date"]).date(),
                                                datetime.fromisoformat(b["date"]).date()) < cob.MAIORIDADE
        waiver["para"] = b["account_email"] if (menor or b["is_self"]) else (b["driver_email"] or b["account_email"])
    pg = s["pagamento"]
    # "erro" (sem item, QuickBooks fora…): a equipe resolve; o cliente não fica olhando um "preparando" eterno
    pagamento = {"estado": {"pago": "pago", "contrato": "contrato", "enviada": "pagar", "erro": "equipe"}.get(pg, "preparando"),
                 "link": b["pay_link"] if pg == "enviada" else None, "invoice": b["invoice_doc"],
                 "total": b["invoice_total"], "para": b["invoice_sent_to"]}
    return {"id": b["id"], "status": b["status"], "date": b["date"], "period": b["period"], "service": b["service_name"],
            "price": b["price"], "driver": b["driver"], "aceita": s["aceita"], "pagamento": pagamento, "waiver": waiver,
            "confirmada": b["status"] == "confirmada", "coverage": b["coverage"]}


# ------------------------------------------------------------------ e-mails ao cliente
def _per(b):
    return {"manha": "morning", "tarde": "afternoon", "dia": "full day"}.get(b["period"], b["period"])


def _link_conta(bid):
    from command_center import enderecos
    return f"https://{enderecos.CLIENTE}/ops/portal/sessions/{bid}"


def _link_grupo(gid):
    from command_center import enderecos
    return f"https://{enderecos.CLIENTE}/ops/portal/sessions/group/{gid}"


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
        o_que = "extra session" if c.get("coverage") == "extra" else "session + refundable security deposit"
        passos.append(f"1. Pay the invoice{' ' + c['pagamento']['invoice'] if c['pagamento']['invoice'] else ''} "
                      f"({o_que}): {c['pagamento']['link'] or 'it is in your email from QuickBooks'}")
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
    juntas, link = [b], _link_conta(bid)
    if b["group_id"]:
        # #314: o pedido de vários dias recebe UM e-mail, quando todas as sessões dele confirmaram
        juntas = todos(con, "SELECT * FROM bookings WHERE group_id=? AND status IN ('pendente','confirmada') ORDER BY date, id",
                       (b["group_id"],))
        if any(x["status"] != "confirmada" for x in juntas) or any(x["notified_confirmed_at"] for x in juntas):
            return False
        link = _link_grupo(b["group_id"])
    linhas = "\n".join(f"{x['service_name'] or 'Session'} · {x['date'][5:7]}/{x['date'][8:10]}/{x['date'][:4]} ({_per(x)})"
                       for x in juntas)
    texto = (f"Hi {a['name'].split(' ')[0]},\n\nYou're confirmed! See you at the track:\n\n{linhas}\n\n"
             "Your URACE QR is in your account: show it at the shop.\n"
             f"Your booking: {link}\n\nURACE.US · Orlando, FL")
    try:
        _enviar(enviar_email, a["email"], "You're confirmed: your URACE session" + ("s" if len(juntas) > 1 else ""), texto)
        for x in juntas:
            atualizar(con, "bookings", x["id"], notified_confirmed_at=agora())
        return True
    except Exception as e:                                         # noqa: BLE001
        atualizar(con, "bookings", bid, reminder_error=f"e-mail de confirmação: {e}"[:300])
        return False


# ------------------------------------------------------------------ pedido de vários dias (#314)
def _do_grupo(con, gid):
    return todos(con, """SELECT b.*, p.name AS driver FROM bookings b LEFT JOIN portal_pilots p ON p.id=b.pilot_id
                          WHERE b.group_id=? ORDER BY b.date, b.id""", (gid,))


def vender_grupo(con, gid, por=None, enviar_invoice=None, enviar_waiver=None, criar_qbo=None, enviar_email=None):
    """O pedido de vários dias vira cobrança na hora (venda automática ligada): o card uma vez, as extras numa
    invoice só, uma waiver, um e-mail. Devolve as etapas."""
    bs = [b for b in _do_grupo(con, gid) if b["status"] == "pendente" and not b["accepted_at"]]
    if not bs or not ligada(con):
        return None
    b = bs[0]
    try:
        card, nota = garantir_card(con, b, por)
        if nota:
            for x in bs:
                atualizar(con, "bookings", x["id"], card_note=nota[:300], updated_at=agora())
            auditar(con, "booking.card", "system", entity_type="booking", entity_id=b["id"], detail={"client_id": card, "nota": nota})
    except (vs.ErroVinculo, cob.ErroCobranca) as e:
        for x in bs:
            atualizar(con, "bookings", x["id"], card_note=f"erro: {e}"[:300], updated_at=agora())
    cob.aceitar(con, por, b["id"], enviar_invoice, enviar_waiver, criar_cliente=criador_de_cliente_qbo(con, b, criar_qbo))
    for x in bs:
        auditar(con, "booking.auto_sell", "system", entity_type="booking", entity_id=x["id"], detail={"grupo": gid})
    avisar_recebido_grupo(con, gid, enviar_email)
    return checkout_grupo(con, gid)


def conferir_pagamento_grupo(con, gid, ler=None, enviar_email=None, agora_dt=None):
    """Uma leitura no QuickBooks por invoice do pedido (a das extras), no máximo uma vez por minuto."""
    pago = False
    vistas = set()
    for b in _do_grupo(con, gid):
        if b["qbo_invoice_id"] and b["qbo_invoice_id"] not in vistas and not b["paid_at"] and b["status"] == "pendente":
            vistas.add(b["qbo_invoice_id"])
            pago = conferir_pagamento(con, b["id"], ler, enviar_email, agora_dt) or pago
    return pago


def checkout_grupo(con, gid):
    """As etapas do pedido de vários dias, na linguagem do cliente: cada dia com "Included in your plan" ou
    "Extra session · $X", a invoice das extras (uma só) e a waiver. Nada do contador do pacote."""
    from command_center.providers.agenda_lote import rotulo
    bs = _do_grupo(con, gid)
    ativas = [b for b in bs if b["status"] in ag.ATIVAS]
    extras = [b for b in ativas if b["coverage"] == "extra"]
    base = checkout(con, (ativas or bs)[0]["id"])
    if extras:
        pagamento = checkout(con, next((b for b in extras if b["qbo_invoice_id"]), extras[0])["id"])["pagamento"]
    else:
        pagamento = {"estado": "contrato", "link": None, "invoice": None, "total": None, "para": None}
    return {"id": gid, "service": bs[0]["service_name"], "driver": bs[0]["driver"],
            "status": "cancelada" if not ativas else ("confirmada" if all(b["status"] == "confirmada" for b in ativas) else "pendente"),
            "sessions": [{"id": b["id"], "date": b["date"], "period": b["period"], "status": b["status"], "coverage": b["coverage"],
                          "price": b["price"], "label": rotulo(b["coverage"], b["price"]) if b["coverage"] else None} for b in bs],
            "included": sum(1 for b in ativas if b["coverage"] == "plano"), "extras": len(extras),
            "extras_total": round(sum(b["price"] or 0 for b in extras), 2),
            "aceita": any(b["accepted_at"] for b in ativas), "confirmada": bool(ativas) and all(b["status"] == "confirmada" for b in ativas),
            "pagamento": pagamento, "waiver": base["waiver"]}


def avisar_recebido_grupo(con, gid, enviar_email=None):
    """Um e-mail para o pedido inteiro: os dias, o que é do plano e o que é extra, e o que falta."""
    g = um(con, "SELECT * FROM booking_groups WHERE id=?", (gid,))
    if not g or g["notified_received_at"] or not ligada(con):
        return False
    c = checkout_grupo(con, gid)
    a = um(con, "SELECT name, email FROM portal_accounts WHERE id=?", (g["account_id"],))
    dias = "\n".join(f"- {x['date'][5:7]}/{x['date'][8:10]}/{x['date'][:4]} ({_per(x)}) · {x['label'] or ''}"
                     for x in c["sessions"] if x["status"] in ag.ATIVAS)
    passos = []
    if c["pagamento"]["estado"] == "pagar":
        passos.append(f"1. Pay the invoice{' ' + c['pagamento']['invoice'] if c['pagamento']['invoice'] else ''} "
                      f"(extra sessions): {c['pagamento']['link'] or 'it is in your email from QuickBooks'}")
    elif c["pagamento"]["estado"] == "preparando":
        passos.append("1. Pay the invoice of the extra sessions: it is on its way to your email from QuickBooks.")
    if c["waiver"]["estado"] == "assinar_aqui":
        passos.append(f"{len(passos) + 1}. Sign the waiver in your URACE account: {_link_grupo(gid)}")
    elif c["waiver"]["estado"] in ("email", "preparando"):
        passos.append(f"{len(passos) + 1}. Sign the waiver: it is in your email from DocuSign"
                      f"{' (sent to ' + c['waiver']['para'] + ')' if c['waiver'].get('para') else ''}.")
    texto = (f"Hi {a['name'].split(' ')[0]},\n\nThanks for booking with URACE! We are holding your sessions:\n\n"
             f"{c['service'] or 'Session'}{' · ' + c['driver'] if c['driver'] else ''}\n{dias}\n\n"
             + ("To confirm them:\n" + "\n".join(passos) + "\n\nThey confirm by themselves as soon as it is done.\n\n" if passos else "")
             + f"Follow your booking any time in your URACE account: {_link_grupo(gid)}\n\n"
             "Questions? Reply to this email or write to support@urace.us.\n\nURACE.US · Orlando, FL")
    try:
        _enviar(enviar_email, a["email"], "Your URACE booking: what's next", texto)
        atualizar(con, "booking_groups", gid, notified_received_at=agora())
        for x in c["sessions"]:
            atualizar(con, "bookings", x["id"], notified_received_at=agora())
        return True
    except Exception as e:                                         # noqa: BLE001 — fica escrito para a equipe
        for x in c["sessions"]:
            atualizar(con, "bookings", x["id"], reminder_error=f"e-mail de recebimento: {e}"[:300])
        return False


# De onde a pessoa veio. #260 (15/10) acrescentou o que o site antigo mandava e o novo não: os
# cookies do pixel do Meta (`fbp`, `fbc`) e os ids de campanha e de conjunto de anúncios.
CAMPANHA = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "gclid", "fbclid", "fbp", "fbc", "campaign_id", "adset_id", "ref")
CAMPANHA_MAX = 200


def utm_limpo(utm):
    """Só as chaves de campanha, curtas e sem HTML: de onde veio a venda, para o marketing.

    Nada da pessoa entra aqui — nem nome, nem e-mail, nem telefone."""
    if not isinstance(utm, dict):
        return None
    ok = {}
    for k in CAMPANHA:
        v = utm.get(k)
        if v is None or isinstance(v, (dict, list, tuple, bool)):
            continue
        v = re.sub(r"\s+", " ", str(v).replace("<", " ").replace(">", " ")).strip()[:CAMPANHA_MAX]
        if v:
            ok[k] = v
    return json.dumps(ok, ensure_ascii=False) if ok else None

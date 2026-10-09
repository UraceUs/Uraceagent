"""Cobrança e waiver da sessão marcada pelo site (#50, PR B).

Dono, 05/10: *"A sessão do cliente só será confirmada após o pagamento e assinatura da waiver"*.
Decisões de 06/10 (painel de decisões):
- **Quando a equipe aceita a vaga**, a invoice do QuickBooks é criada e enviada sozinha: o preço do
  serviço gravado no agendamento + o **depósito** (US$ 400) quando o serviço pede (Arrive and Drive:
  o contrato da Academy, §2.3, diz que o depósito é devolvido em até 5 dias úteis se não houver
  incidente — por isso vale por sessão).
- **A waiver sai sozinha pelo DocuSign** na mesma hora, se o piloto não tem uma válida, com as
  4 travas do DocuSign (já assinada há menos de 1 ano, envelope aberto, idade e nome/e-mail
  conferidos). Com a waiver nativa ligada, quem assina é o cliente, na área do cliente.
- **Cliente com contrato** (Academy) não paga de novo: conta como sessão do contrato. Se a waiver
  já está em dia, a sessão confirma sozinha assim que é marcada (dentro do limite do mês).
- **Lembrete 3 dias e 1 dia antes**, por e-mail, dizendo o que falta. **Nada cancela sozinho**: sem
  pagamento ou waiver, a equipe decide (pode confirmar mesmo assim, recusar ou cancelar).

O agendamento aceito continua `pendente` (segura a vaga) com `accepted_at` preenchido, e vira
`confirmada` sozinho quando a invoice está paga (o espelho do QuickBooks sincroniza a cada 15 min)
e a waiver está assinada. Toda falha (sem card, sem cliente no QuickBooks, serviço sem item) fica
escrita no agendamento para a equipe ver e resolver — a rodada seguinte tenta de novo.
"""
from datetime import date, timedelta

from command_center.db import agora, atualizar, auditar, inserir, um
from command_center.providers import agenda_sessoes as ag
from command_center.providers import contrato

TENTATIVAS = 3
LEMBRETES = (3, 1)                    # dias antes da sessão
MAIORIDADE = 18


class ErroCobranca(ValueError):
    pass


# ------------------------------------------------------------------ leitura
def card_do_agendamento(con, b):
    """O card (clients.id) do piloto, ou o da conta quando o piloto ainda não tem card."""
    r = um(con, f"""SELECT {contrato.CARD_DO_AGENDAMENTO} AS cid FROM bookings b
                     JOIN portal_accounts a ON a.id=b.account_id LEFT JOIN portal_pilots p ON p.id=b.pilot_id
                    WHERE b.id=?""", (b["id"],))
    return r["cid"] if r else None


def _idade(nasc, em):
    return em.year - nasc.year - ((em.month, em.day) < (nasc.month, nasc.day))


def waiver_em_dia(con, b, card=None):
    """A waiver vale no dia da sessão: a nativa do piloto, ou uma do DocuSign no card dele."""
    if b["pilot_id"]:
        from command_center.providers import waiver_nativa
        w = waiver_nativa.vigente(con, b["pilot_id"])
        if w and (w["expires_at"] or "") >= b["date"]:
            return True
    card = card if card is not None else card_do_agendamento(con, b)
    if not card:
        return False
    limite = (date.fromisoformat(b["date"]) - timedelta(days=365)).isoformat()
    return bool(um(con, """SELECT 1 AS x FROM waivers WHERE client_id=? AND status='completed'
                              AND COALESCE(source,'')<>'urace' AND COALESCE(hidden,0)=0
                              AND COALESCE(internal,0)=0 AND substr(completed_at,1,10) >= ?""", (card, limite)))


def invoice_paga(con, b):
    """A invoice desta sessão já aparece paga no espelho do QuickBooks?"""
    if not b["qbo_invoice_id"]:
        return False
    if "paid_at" in b.keys() and b["paid_at"]:           # #164: conferido direto no QuickBooks
        return True
    i = um(con, """SELECT i.balance, i.status FROM invoices i JOIN entity_links l
                     ON l.entity_type='invoice' AND l.entity_id=i.id AND l.system IN ('quickbooks','qbo')
                  WHERE l.external_id=?""", (str(b["qbo_invoice_id"]),))
    return bool(i and ((i["balance"] is not None and i["balance"] <= 0) or (i["status"] or "").lower() == "paid"))


def situacao(con, b):
    """O que falta para a sessão aceita confirmar — para a equipe e para o cliente."""
    b = dict(b)
    pago = b["charge_kind"] == "contrato" or invoice_paga(con, b)
    waiver = waiver_em_dia(con, b)
    return {"aceita": bool(b["accepted_at"]), "pagamento": "contrato" if b["charge_kind"] == "contrato" else
            ("pago" if pago else ("enviada" if b["qbo_invoice_id"] else ("erro" if b["charge_error"] else "pendente"))),
            "waiver": "ok" if waiver else ("erro" if b["waiver_error"] else ("enviada" if b["waiver_ref"] else "pendente")),
            "pronta": bool(b["accepted_at"]) and pago and waiver}


# ------------------------------------------------------------------ invoice
def _sessao(b):
    per = {"manha": "morning", "tarde": "afternoon", "dia": "full day"}.get(b["period"], b["period"])
    return f"{b['service_name'] or 'Session'} · {date.fromisoformat(b['date']).strftime('%m/%d/%Y')} ({per})"


def linhas_da_invoice(con, b):
    """O preço do serviço gravado no agendamento + o depósito, quando o serviço pede."""
    s = um(con, "SELECT * FROM booking_services WHERE id=?", (b["service_id"],)) if b["service_id"] else None
    if not s or not s["qbo_item_id"]:
        raise ErroCobranca("o serviço não tem item do QuickBooks: escolha o item em Site público › Serviços")
    if b["price"] is None:
        raise ErroCobranca("o agendamento não tem preço")
    linhas = [{"item_id": s["qbo_item_id"], "quantidade": 1, "unitario": float(b["price"]), "descricao": _sessao(b)}]
    dep = s["deposit"] or 0
    if dep > 0:
        item = um(con, """SELECT id FROM qbo_items WHERE active=1
                           AND (LOWER(name) LIKE '%security deposit%' OR LOWER(COALESCE(full_name,'')) LIKE '%security deposit%')
                         ORDER BY id LIMIT 1""")
        if not item:
            raise ErroCobranca("não achei o item \"Security deposit\" no QuickBooks (sincronize o QuickBooks)")
        linhas.append({"item_id": item["id"], "quantidade": 1, "unitario": float(dep),
                       "descricao": "Refundable security deposit: returned within 5 business days after the session if there is no incident."})
    return linhas


def _enviar_padrao(**kw):
    from command_center import providers
    from command_center.providers.mensalidades import _aplicando
    return _aplicando(providers.modulo("quickbooks").qbo_criar_e_enviar_invoice, **kw)


def cobrar(con, b, enviar=None, criar_cliente=None):
    """Cria e envia a invoice da sessão. Não cobra duas vezes; contrato não cobra. `criar_cliente`
    (venda automática, #164) cria o cliente no QuickBooks quando o card ainda não tem."""
    b = dict(b)
    if b["charge_kind"] or b["qbo_invoice_id"]:
        return b["charge_kind"]
    card = card_do_agendamento(con, b)
    if card and contrato.tem_contrato(con, card):
        sit = contrato.situacao_do_agendamento(con, card, b["date"])
        if not (sit and sit.get("acima")):
            atualizar(con, "bookings", b["id"], charge_kind="contrato", charge_error=None, updated_at=agora())
            return "contrato"
    try:
        if not card:
            raise ErroCobranca("a conta do site ainda não está ligada a um card (Client ID)")
        from command_center.providers.mensalidades import _cliente_qbo
        try:
            qbo = _cliente_qbo(con, card)
        except Exception as e:                                     # noqa: BLE001 — QuickBooks fora do ar
            raise ErroCobranca(f"QuickBooks indisponível: {getattr(e, 'detail', e)}")
        if not qbo and criar_cliente:
            qbo = criar_cliente(card)
        if not qbo:
            raise ErroCobranca("o cliente não está no QuickBooks (crie o cliente lá ou ligue o card)")
        conta = um(con, "SELECT email FROM portal_accounts WHERE id=?", (b["account_id"],))
        res = (enviar or _enviar_padrao)(cliente_id=qbo, linhas=linhas_da_invoice(con, b), vence_em=b["date"],
                                         memo=f"URACE session: {_sessao(b)}.", email=conta["email"] if conta else None)
        if not res or res.get("aplicado") is False:
            raise ErroCobranca("o QuickBooks não criou a invoice (simulação)")
        atualizar(con, "bookings", b["id"], charge_kind="invoice", qbo_invoice_id=str(res.get("id") or ""),
                  invoice_doc=res.get("numero"), invoice_total=res.get("total"), invoice_link=res.get("link"),
                  pay_link=res.get("link_pagamento"),
                  invoice_sent_to=res.get("enviado_para"), charge_error=None if res.get("enviado", True) else
                  (res.get("aviso") or "criada, mas não enviada"), charge_attempts=(b["charge_attempts"] or 0) + 1,
                  updated_at=agora())
        auditar(con, "booking.invoice", "system", entity_type="booking", entity_id=b["id"],
                detail={"invoice": res.get("numero"), "total": res.get("total"), "client_id": card})
        return "invoice"
    except Exception as e:                                         # noqa: BLE001 — fica escrito, tenta de novo
        atualizar(con, "bookings", b["id"], charge_error=str(e)[:300], charge_attempts=(b["charge_attempts"] or 0) + 1,
                  updated_at=agora())
        return None


# ------------------------------------------------------------------ waiver
def _enviar_waiver_padrao(template, nome, email, servico):
    from command_center.providers import modulo
    modelos = {"parental": "6dbf2094-39da-4c21-95dd-feda7ac28022", "adult": "c51aede4-bba5-40df-9f14-24c340e2bd3e"}
    import os
    modelos["parental"] = os.environ.get("DOCUSIGN_TEMPLATE_PARENTAL", modelos["parental"])
    modelos["adult"] = os.environ.get("DOCUSIGN_TEMPLATE_ADULT", modelos["adult"])
    return modulo("docusign").enviar_waiver_humano(modelos[template], nome, email, servico)


def pedir_waiver(con, b, enviar=None, tabela="bookings", card=None, motivo=None):
    """Sem waiver válida, manda a do DocuSign (as 4 travas valem lá). Com a nativa ligada, não manda:
    o cliente assina na área do cliente. `tabela`/`card`/`motivo`: o plano mensal (#169) usa o mesmo."""
    b = dict(b)
    if b["waiver_ref"] or waiver_em_dia(con, b, card):
        return "ok"
    from command_center.providers import waiver_nativa
    if waiver_nativa.ligada(con):
        return "nativa"
    p = um(con, "SELECT * FROM portal_pilots WHERE id=?", (b["pilot_id"],)) if b["pilot_id"] else None
    a = um(con, "SELECT * FROM portal_accounts WHERE id=?", (b["account_id"],))
    try:
        if not p or not p["birth_date"]:
            raise ErroCobranca("o piloto não tem data de nascimento")
        menor = _idade(date.fromisoformat(p["birth_date"]), date.fromisoformat(b["date"])) < MAIORIDADE
        if menor or p["is_self"]:
            nome, email = a["name"], a["email"]
        else:
            nome, email = p["name"], (p["email"] or "").strip()
            if not email:
                raise ErroCobranca("piloto adulto sem e-mail: ele assina a própria waiver (cadastre o e-mail dele)")
        template = "parental" if menor else "adult"
        res = (enviar or _enviar_waiver_padrao)(template, nome, email.lower(), b["service_name"] or "")
        env = res.get("envelopeId") if isinstance(res, dict) else None
        card = card if card is not None else card_do_agendamento(con, b)
        wid = inserir(con, "waivers", client_id=card, signer_name=nome, signer_email=email.lower(), template=template,
                      status="sent", sent_at=agora(), link_reason=motivo or f"agenda: sessão #{b['id']} aceita",
                      link_by="system" if card else None, minor_name=p["name"] if menor else None, synced_at=agora())
        if env:
            con.execute("""INSERT OR IGNORE INTO entity_links (entity_type, entity_id, system, external_id, deep_link)
                           VALUES ('waiver', ?, 'docusign', ?, ?)""",
                        (wid, env, f"https://apps.docusign.com/send/documents/details/{env}"))
        atualizar(con, tabela, b["id"], waiver_ref=wid, waiver_error=None, updated_at=agora())
        auditar(con, "booking.waiver" if tabela == "bookings" else "plan.waiver", "system",
                entity_type="booking" if tabela == "bookings" else "plan_order", entity_id=b["id"],
                detail={"waiver": wid, "envelope": env, "template": template, "email": email.lower()})
        return "enviada"
    except Exception as e:                                         # noqa: BLE001 — trava do DocuSign ou dado faltando
        atualizar(con, tabela, b["id"], waiver_error=str(e)[:300], updated_at=agora())
        return None


# ------------------------------------------------------------------ fluxo
def verificar(con, bid):
    """Aceita + paga (ou contrato) + waiver em dia → confirmada, sozinha."""
    b = um(con, "SELECT * FROM bookings WHERE id=?", (bid,))
    if not b or b["status"] != "pendente" or not b["accepted_at"]:
        return False
    if not situacao(con, b)["pronta"]:
        return False
    atualizar(con, "bookings", bid, status="confirmada", decided_at=agora(), updated_at=agora(),
              decision_note=b["decision_note"] or ("Session of your plan: confirmed." if b["charge_kind"] == "contrato"
                                                   else "Paid and waiver signed: confirmed."))
    auditar(con, "booking.confirmed.auto", "system", entity_type="booking", entity_id=bid,
            detail={"pagamento": b["charge_kind"], "invoice": b["invoice_doc"]})
    return True


def aceitar(con, por, bid, enviar_invoice=None, enviar_waiver=None, criar_cliente=None):
    """A equipe aceita a vaga: cobra (ou conta no contrato), pede a waiver e confirma se já pode."""
    b = um(con, "SELECT * FROM bookings WHERE id=?", (bid,))
    if not b:
        raise ag.ErroAgenda("agendamento não existe")
    if b["status"] != "pendente":
        raise ag.ErroAgenda(f"o agendamento está {b['status']}")
    if not b["accepted_at"]:
        atualizar(con, "bookings", bid, accepted_at=agora(), accepted_by=por, updated_at=agora())
    b = um(con, "SELECT * FROM bookings WHERE id=?", (bid,))
    cobrar(con, b, enviar_invoice, criar_cliente)
    b = um(con, "SELECT * FROM bookings WHERE id=?", (bid,))
    pedir_waiver(con, b, enviar_waiver)
    verificar(con, bid)
    b = um(con, "SELECT * FROM bookings WHERE id=?", (bid,))
    return {"status": b["status"], **situacao(con, b), "charge_error": b["charge_error"], "waiver_error": b["waiver_error"]}


def ao_marcar(con, bid):
    """Contrato + waiver em dia (dono, 06/10): a sessão confirma sozinha assim que é marcada,
    desde que esteja dentro do limite do mês."""
    b = um(con, "SELECT * FROM bookings WHERE id=?", (bid,))
    if not b or b["status"] != "pendente":
        return False
    card = card_do_agendamento(con, b)
    if not card or not contrato.tem_contrato(con, card):
        return False
    sit = contrato.situacao_do_agendamento(con, card, b["date"])
    if (sit and sit.get("acima")) or not waiver_em_dia(con, b, card):
        return False
    atualizar(con, "bookings", bid, accepted_at=agora(), charge_kind="contrato", updated_at=agora())
    return verificar(con, bid)


def _texto_lembrete(b, s, dias):
    quando = "in 3 days" if dias == 3 else "tomorrow"
    falta = []
    if s["pagamento"] not in ("pago", "contrato"):
        falta.append(f"- Pay the invoice{' ' + b['invoice_doc'] if b['invoice_doc'] else ''}"
                     f"{': ' + b['invoice_link'] if b['invoice_link'] else ' (it is in your email from QuickBooks)'}")
    if s["waiver"] != "ok":
        falta.append("- Sign the waiver (it is in your email from DocuSign, or in your URACE account)")
    return (f"Hi,\n\nYour URACE session is {quando}: {_sessao(b)}.\n\n"
            "To confirm it, we still need:\n" + "\n".join(falta) +
            "\n\nIf you have questions, reply to support@urace.us.\n\nURACE.US · Orlando, FL")


def rodar(con, hoje=None, enviar_invoice=None, enviar_waiver=None, enviar_email=None, criar_qbo=None):
    """Laço do autosync: tenta de novo o que falhou, confirma o que ficou pronto e lembra o cliente
    3 dias e 1 dia antes. Nada cancela sozinho. Com a venda automática (#164), também cria o cliente
    no QuickBooks que faltou e avisa o cliente quando a sessão confirma."""
    from command_center.providers import venda_site
    auto = venda_site.ligada(con)
    hoje = hoje or ag._agora_fl().date()
    feito = {"confirmadas": 0, "cobradas": 0, "waivers": 0, "lembretes": 0}
    for b in con.execute("""SELECT * FROM bookings WHERE status='pendente' AND accepted_at IS NOT NULL
                              AND date >= ? ORDER BY date, id""", (hoje.isoformat(),)).fetchall():
        criar = venda_site.criador_de_cliente_qbo(con, b, criar_qbo) if auto else None
        if not b["charge_kind"] and (b["charge_attempts"] or 0) < TENTATIVAS and cobrar(con, b, enviar_invoice, criar):
            feito["cobradas"] += 1
        b = um(con, "SELECT * FROM bookings WHERE id=?", (b["id"],))
        if not b["waiver_ref"] and pedir_waiver(con, b, enviar_waiver) == "enviada":
            feito["waivers"] += 1
        if verificar(con, b["id"]):
            feito["confirmadas"] += 1
            if auto:
                venda_site.avisar_confirmada(con, b["id"], enviar_email)
            continue
        b = um(con, "SELECT * FROM bookings WHERE id=?", (b["id"],))
        dias = (date.fromisoformat(b["date"]) - hoje).days
        campo = {3: "reminded_3d_at", 1: "reminded_1d_at"}.get(dias)
        if campo and not b[campo]:
            a = um(con, "SELECT email FROM portal_accounts WHERE id=?", (b["account_id"],))
            try:
                if enviar_email is None:
                    from command_center.providers import email_envio
                    enviar_email = email_envio.enviar
                enviar_email(a["email"], f"Your URACE session {'in 3 days' if dias == 3 else 'is tomorrow'}: what is missing",
                             _texto_lembrete(b, situacao(con, b), dias))
                atualizar(con, "bookings", b["id"], **{campo: agora()}, reminder_error=None, updated_at=agora())
                feito["lembretes"] += 1
            except Exception as e:                                 # noqa: BLE001 — fica escrito para a equipe
                atualizar(con, "bookings", b["id"], reminder_error=str(e)[:300], updated_at=agora())
    return feito

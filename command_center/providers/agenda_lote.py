"""Vários dias num pedido do aluno recorrente (#314, parte 2).

Dono, 16/10: *"para esses clientes, é interessante eles terem a oportunidade de marcar mais de um dia,
multi-seleção de dias. Então, se ele quiser marcar para quartas, toda quarta. Ou quartas e sábado dessa
semana, ou então sábado e domingo da outra, ele consegue marcar isso tudo em um book."*

- **Cotar** (`cotar`): os dias escolhidos, um a um, como o servidor os vê — aberto ou não (a agenda do
  cliente: horizonte e antecedência valem), conflito com outra sessão do piloto, e se cabe no pacote do mês
  ("Included in your plan") ou é extra ("Extra session · $X"). Nada é gravado. O `hash` resume a cotação.
- **Marcar** (`marcar`): o pedido inteiro numa transação — ou entram todos os dias, ou nenhum. Se a cotação
  mudou desde que o cliente viu (outra pessoa pegou a vaga, o preço mudou), o pedido volta para ele revisar.
- No máximo 12 dias por pedido. Só para quem tem plano mensal vigente: o cliente avulso marca um dia por vez.
- O contador do pacote (usadas/total) não sai daqui: o cliente vê só o rótulo de cada dia (dono, 01/10).

Mensagens em inglês: é o que o cliente lê.
"""
import hashlib
import json
from datetime import date

from command_center.db import atualizar, inserir, todos, um
from command_center.providers import agenda_sessoes as ag
from command_center.providers import contrato, servicos_site

MAX_DIAS = 12
PERIODOS = ("manha", "tarde", "dia")
MOTIVOS = {"invalido": "Choose a valid date and time.",
           "fechado": "This time is not available. Pick another one.",
           "repetido": "This day and time is twice in your booking.",
           "fora_do_plano": "Your monthly plan does not cover this date. Use \"Book as a regular session\" on this day."}
MUDOU = "Your booking changed since you reviewed it (a spot or a price). Please review it and book again."


class ErroLote(ValueError):
    """Mensagem em inglês: é o que o cliente lê."""


class CotacaoMudou(ErroLote):
    """A vaga ou o preço mudou entre a cotação e o pedido: o cliente revisa antes (409)."""


def rotulo(cobertura, preco):
    """O que o cliente lê em cada dia — e só isto (dono, 01/10: o contador fica com a equipe)."""
    if cobertura == "plano":
        return "Included in your plan"
    return "Extra session" + (f" · ${preco:,.2f}" if preco is not None else "")


def _piloto(con, conta_id, piloto_id):
    p = um(con, "SELECT * FROM portal_pilots WHERE id=? AND account_id=? AND active=1", (piloto_id, conta_id)) if piloto_id else None
    if not p:
        raise ErroLote("Choose the driver for these sessions.")
    return p


def plano_do_piloto(con, conta_id, piloto_id):
    """O piloto é aluno recorrente? E o nome do plano e o preço da extra — nunca o contador."""
    p = _piloto(con, conta_id, piloto_id)
    card = p["client_id"]
    rec = contrato.vigente(con, card)
    c = um(con, "SELECT monthly_plan FROM clients WHERE id=?", (card,)) if rec else None
    e = contrato.preco_extra(con, card) if rec else None
    return {"driver_id": p["id"], "recurring": rec, "plan": (c or {}).get("monthly_plan") or ("Monthly plan" if rec else None),
            "extra_price": float(e) if e is not None else None}


def _sobrepoe(a, b):
    return a == b or "dia" in (a, b)


def cotar(con, conta_id, piloto_id, servico_id, slots):
    """Cada dia pedido → {date, period, ok, reason, message, coverage, price, label}; e os totais."""
    if not isinstance(slots, list) or not slots:
        raise ErroLote("Choose at least one day.")
    if len(slots) > MAX_DIAS:
        raise ErroLote(f"Up to {MAX_DIAS} days per booking. Book the rest in another one.")
    try:
        servico = servicos_site.do_agendamento(con, servico_id)
    except servicos_site.ErroServico as e:
        raise ErroLote(str(e))
    p = _piloto(con, conta_id, piloto_id)
    card = p["client_id"]
    if not contrato.vigente(con, card):
        raise ErroLote("Booking several days at once is for students with a monthly plan. Book one session at a time.")
    from command_center.providers import portal                      # import aqui: portal não depende da agenda
    falta = portal.pode_marcar(con, conta_id, piloto_id)
    if falta:
        raise ErroLote(falta)
    linhas = []
    for s in slots:
        d, per = str((s or {}).get("date") or "")[:10], str((s or {}).get("period") or "")
        try:
            dia = date.fromisoformat(d)
        except ValueError:
            dia = None
        linhas.append({"date": d, "period": per, "_dia": dia if per in PERIODOS else None})
    validos = [x["_dia"] for x in linhas if x["_dia"]]
    disp = {x["date"]: x for x in ag.disponibilidade(con, min(validos), max(validos))["dias"]} if validos else {}
    ja = todos(con, """SELECT date, period FROM bookings WHERE account_id=? AND COALESCE(pilot_id,0)=? AND date BETWEEN ? AND ?
                        AND status IN ('pendente','confirmada')""",
               (conta_id, piloto_id, min(validos).isoformat(), max(validos).isoformat())) if validos else []
    vistos = []
    for x in linhas:
        motivo = None
        if not x["_dia"]:
            motivo = "invalido"
        elif any(y["date"] == x["date"] and _sobrepoe(y["period"], x["period"]) for y in ja):
            motivo = "ja_tem"
        elif not (disp.get(x["date"]) or {}).get("periods", {}).get(x["period"], {}).get("open"):
            motivo = "fechado"
        elif any(d == x["date"] and _sobrepoe(per, x["period"]) for d, per in vistos):
            motivo = "repetido"
        if not motivo:
            vistos.append((x["date"], x["period"]))
        x["reason"] = motivo
    bons = [x for x in linhas if not x["reason"]]
    for x, a in zip(bons, contrato.alocar(con, card, [x["date"] for x in bons])):
        if not a["coverage"]:
            x["reason"] = "fora_do_plano"
        else:
            x["coverage"], x["price"] = a["coverage"], (float(a["price"]) if a["price"] is not None else None)
    saida = []
    for x in linhas:
        ok = not x["reason"]
        msg = None if ok else (f"{p['name']} already has a session at this time." if x["reason"] == "ja_tem" else MOTIVOS[x["reason"]])
        saida.append({"date": x["date"], "period": x["period"], "ok": ok, "reason": x["reason"], "message": msg,
                      "coverage": x.get("coverage") if ok else None, "price": x.get("price") if ok else None,
                      "label": rotulo(x.get("coverage"), x.get("price")) if ok else None})
    extras = [x for x in saida if x["coverage"] == "extra"]
    total = sum((contrato.centavos(x["price"]) for x in extras if x["price"] is not None), contrato.ZERO)
    resumo = [[x["date"], x["period"], x["ok"], x["coverage"], x["price"]] for x in saida]
    h = hashlib.sha256(json.dumps([servico["id"], piloto_id, resumo]).encode()).hexdigest()[:16]
    return {"slots": saida, "included": sum(1 for x in saida if x["coverage"] == "plano"), "extras": len(extras),
            "extras_total": float(total), "extra_price_missing": any(x["price"] is None for x in extras),
            "service": servico["name"], "hash": h}


def marcar(con, conta_id, piloto_id, servico_id, slots, cotacao, notas=None, origem=None, utm=None):
    """O pedido inteiro: chame dentro de `transacao` (ou entra tudo, ou nada). Devolve (grupo, [ids])."""
    from command_center.providers import cobranca_agenda as cob
    c = cotar(con, conta_id, piloto_id, servico_id, slots)
    ruim = next((x for x in c["slots"] if not x["ok"]), None)
    if ruim:
        quando = date.fromisoformat(ruim["date"]).strftime("%a, %b %d").replace(" 0", " ") if ruim["reason"] != "invalido" else ""
        raise ErroLote(f"{quando + ': ' if quando else ''}{ruim['message']}")
    if not cotacao or cotacao != c["hash"]:
        raise CotacaoMudou(MUDOU)
    gid = inserir(con, "booking_groups", account_id=conta_id, pilot_id=piloto_id, service_id=servico_id,
                  origin="site" if origem == "site" else "portal", utm=utm)
    ids = []
    for x in sorted(c["slots"], key=lambda y: (y["date"], y["period"])):
        try:
            bid = ag.agendar(con, conta_id, x["date"], x["period"], piloto_id, notas, servico_id)
        except ag.ErroAgenda as e:
            raise ErroLote(f"{date.fromisoformat(x['date']).strftime('%a, %b %d').replace(' 0', ' ')}: {e}")
        atualizar(con, "bookings", bid, group_id=gid, origin="site" if origem == "site" else "portal", utm=utm)
        ids.append(bid)
    cob.alocar_grupo(con, ids)
    for bid in ids:
        cob.ao_marcar(con, bid)
    return gid, ids


def conferir(con, conta_id, piloto_id, servico_id, slots, cotacao):
    """O pedido de um dia do aluno recorrente (a Reserva do site): a cotação que o cliente viu ("Included in your
    plan" ou "Extra session · $X") ainda vale? Chame dentro da `transacao`, antes de marcar. Mudou (a última vaga
    do mês foi ocupada, o preço mudou, o plano acabou): CotacaoMudou (409), e o cliente revisa antes."""
    try:
        c = cotar(con, conta_id, piloto_id, servico_id, slots)
    except ErroLote:
        raise CotacaoMudou(MUDOU)
    if c["hash"] != cotacao:
        raise CotacaoMudou(MUDOU)
    return c

"""Carrinho e checkout do site (#236).

Dono, 14/10: *"O site novo, eu ainda preciso montar o sistema de carrinho e checkout ... Tudo testado,
tudo funcionando. É, usando o Stripe."* Sobre a agenda (#50): *"quando a pessoa selecionar o serviço,
selecionar a data, já vai com aquele serviço e o preço que está lá para aquela data"*; *"O depósito de
segurança ele é cobrado em venda manual ou automática"*; *"Todo mundo agora precisa de conta no site"*.

O carrinho mora no navegador (só o que a pessoa escolheu: produto, variação e quantidade; serviço, dia,
turno e piloto). **Tudo o que custa dinheiro é recalculado aqui**, do catálogo da loja e do painel:
preço, depósito e vaga. Nada do formulário vira valor.

O caminho:
  1. `cotar`: a página do carrinho mostra as linhas como o servidor as vê (preço, depósito, vaga, piloto).
  2. `criar_checkout`: a sessão da agenda exige a conta do site (e o piloto da conta, com o cadastro em
     dia); o produto segue sem conta, como na loja (#174). Nasce um `store_orders` (kind='carrinho') com
     as linhas em `store_order_items` (preço do dia) e UMA sessão do Stripe Checkout com todas as linhas,
     mais a linha do depósito de segurança de cada sessão que tem depósito.
  3. Pago (webhook ou página de obrigado, pelo mesmo `stripe_loja.receber_evento`/`conferir_sessao`,
     idempotentes): `pago` confere a vaga de novo e marca cada sessão (`bookings` já aceita e paga: falta
     só a waiver); se a vaga sumiu entre o checkout e o pagamento, a linha fica "sem vaga" para a equipe
     remarcar ou devolver, e o pagamento não se perde. Cada card ganha a sua oportunidade GANHO em Vendas
     (a sessão vai para o card do PILOTO; nunca para o card de outro cliente). `avisar` manda a
     confirmação e o aviso à equipe; `registrar_qbo` põe o Sales Receipt no QuickBooks.
"""
import json
import time
from datetime import date

from command_center.db import agora, atualizar, auditar, inserir, todos, um
from command_center.providers import agenda_sessoes as ag
from command_center.vitrine import dica

MAX_ITENS = 20
MAX_QTD = 20
PERIODOS = {"manha": "morning", "tarde": "afternoon", "dia": "full day"}
EXPIRA_S = 31 * 60          # com sessão no carrinho, o Checkout vale 31 min (o mínimo do Stripe é 30)
DEPOSITO_TXT = "Refundable security deposit. " + dica.DEPOSITO_INFO   # #282: o mesmo texto do ⓘ do site


class ErroCarrinho(ValueError):
    pass


class PrecisaConta(ErroCarrinho):
    """A sessão da agenda pede a conta do site (dono, 14/10: "Todo mundo agora precisa de conta no site")."""


def _usd(n):
    return f"US$ {n:,.2f}"


def _produtos(con):
    """#298: os produtos à venda vêm do banco (o painel edita); banco sem produto nenhum cai no arquivo de antes."""
    from command_center.providers import loja
    return loja.do_site(con)


def quando(d, periodo):
    try:
        dia = date.fromisoformat(d).strftime("%a, %b %d, %Y").replace(" 0", " ")
    except (TypeError, ValueError):
        dia = str(d)
    return f"{dia} ({PERIODOS.get(periodo, periodo)})"


def _int(v, padrao=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return padrao


# ------------------------------------------------------------------ 1. o que o carrinho custa
def _linha_produto(produtos, it, entrega=None, limites=None, uso=None):
    """#298: o frete fixo do produto (× quantidade) só com "Ship to me"; `frete_envio` é quanto seria (o carrinho
    mostra na opção de entrega) e None quando a equipe combina à parte. O depósito do produto vale por unidade.
    #309: o produto em estoque não passa do que o box tem (somando as linhas do mesmo produto e opção); a mensagem
    não diz o número."""
    from command_center.providers import loja
    from command_center.providers.stripe_loja import _variacao, compravel
    p = produtos.get(str(it.get("produto") or ""))
    qtd = max(1, min(MAX_QTD, _int(it.get("quantidade"), 1)))
    if not p:
        return {"tipo": "produto", "nome": "Product not found", "quantidade": qtd, "unitario": 0, "deposito": 0,
                "frete": 0, "frete_envio": 0, "erro": "This product is no longer in the store. Remove it from the cart."}
    nome_var = str(it.get("variacao") or "")
    v = _variacao(p, nome_var) if p.get("variations") else None
    envio = loja.frete(p, qtd, "envio")
    linha = {"tipo": "produto", "produto": p["slug"], "variacao": nome_var if v else None, "quantidade": qtd,
             "nome": p["name"] + (f" ({nome_var})" if v else ""), "detalhe": None,
             "deposito": round(float(p.get("deposit") or 0) * qtd, 2), "frete_envio": envio,
             "frete": (envio or 0) if entrega == "envio" else 0,
             "link": f"/store/p/{p['slug']}/", "foto": p["images"][0]["src"] if p.get("images") else None}
    if p.get("variations") and not v:
        return {**linha, "unitario": 0, "erro": "Please choose an option on the product page."}
    if not compravel(p, v):
        return {**linha, "unitario": 0, "erro": "This item can't be bought online right now. Send us an order request instead."}
    chave = (p["slug"], nome_var if v else "")
    limite = (limites or {}).get(chave)
    if limite is not None and uso is not None:
        if uso.get(chave, 0) + qtd > limite:
            from command_center.providers.stripe_loja import SEM_TANTO
            return {**linha, "unitario": float((v or {}).get("price") or p["price"]), "erro": SEM_TANTO}
        uso[chave] = uso.get(chave, 0) + qtd
    return {**linha, "unitario": float((v or {}).get("price") or p["price"]), "erro": None}


def _linha_sessao(con, it, conta_id, uso, pilotos, para_pagar):
    """Serviço, dia, turno e piloto. O preço e o depósito são os do painel hoje (#50)."""
    sid, d, per = _int(it.get("servico")), str(it.get("data") or ""), str(it.get("turno") or "")
    s = um(con, "SELECT * FROM booking_services WHERE id=? AND active=1 AND COALESCE(kind,'session')='session'", (sid,)) if sid else None
    base = {"tipo": "sessao", "servico": sid, "data": d, "turno": per, "quantidade": 1, "piloto": _int(it.get("piloto")),
            "piloto_nome": None, "link": "/services/arrive-and-drive/#reservar"}
    if not s:
        return {**base, "nome": "Session", "detalhe": None, "unitario": 0, "deposito": 0,
                "erro": "This session is no longer offered. Remove it and pick another one."}
    linha = {**base, "nome": s["name"], "detalhe": quando(d, per), "unitario": float(s["price"]),
             "deposito": float(s["deposit"] or 0), "erro": None}
    if s["deposit_required"] and not linha["deposito"] > 0:
        # #317: o depósito é obrigatório neste serviço e o valor sumiu (banco mexido à mão): não cobra sem ele
        return {**linha, "erro": "This session can't be paid online right now. Please contact us to book it."}
    from command_center.providers.servicos_site import cartao_do_site
    cartao = cartao_do_site(dict(s)) if s["site_kart"] else {}
    if cartao.get("aviso"):
        linha["aviso"] = cartao["aviso"]                  # #279: o kart próprio chega à pista 2 dias antes; #297: do painel
    try:
        dia = date.fromisoformat(d)
    except ValueError:
        return {**linha, "detalhe": None, "erro": "Choose a valid date."}
    if per not in PERIODOS:
        return {**linha, "erro": "Choose morning or afternoon."}
    dias = ag.disponibilidade(con, dia, dia)["dias"]           # visão do cliente: horizonte e antecedência valem
    vagas = dias[0]["periods"][per] if dias else {"open": False, "spots": 0}
    turnos = ag.PERIODOS if per == "dia" else (per,)
    ja_no_carrinho = max(uso.get((d, t), 0) for t in turnos)
    if not vagas["open"] or vagas["spots"] - ja_no_carrinho <= 0:
        return {**linha, "erro": "This time is no longer available. Please pick another one."}
    for t in turnos:
        uso[(d, t)] = uso.get((d, t), 0) + 1
    pid = linha["piloto"]
    if not conta_id:
        return linha                                              # sem conta ainda: o piloto vem depois do login
    if not pid:
        return {**linha, "erro": "Choose the driver for this session." if para_pagar else None, "falta_piloto": True}
    p = pilotos.get(pid)
    if not p:
        return {**linha, "piloto": None, "erro": "Choose the driver for this session.", "falta_piloto": True}
    linha["piloto_nome"] = p["name"]
    from command_center.providers import portal
    # #305 (dono, 16/10): paga antes e completa o piloto depois, "com lembretes pelo email ate completar as
    # informações". O responsável completo continua exigido (o carrinho pede os dados dele); o piloto sem medidas
    # (ou com as medidas vencidas) não trava mais a compra: a linha avisa e o e-mail lembra até completar.
    conta = um(con, "SELECT * FROM portal_accounts WHERE id=?", (conta_id,))
    if conta and portal.faltando_conta(conta):
        return {**linha, "erro": "Please complete the account holder details (Account) before booking."}
    st = next((x["measures_status"] for x in portal.pilotos(con, conta_id) if x["id"] == pid), None)
    if st == "vencida":
        linha["aviso_piloto"] = (f"{p['name']}'s measurements are over 60 days old. After payment, we'll email you a link to "
                                 "review them.")
    elif st == "faltando":
        linha["aviso_piloto"] = (f"After payment, we'll email you a link to add {p['name']}'s measurements and karting "
                                 "experience. We'll remind you until it's done.")
    if um(con, """SELECT 1 AS x FROM bookings WHERE account_id=? AND date=? AND status IN ('pendente','confirmada')
                   AND COALESCE(pilot_id,0)=? AND (period=? OR period='dia' OR ?='dia')""", (conta_id, d, pid, per, per)):
        return {**linha, "erro": f"{p['name']} already has a session at this time."}
    chave = ("piloto", pid, d)
    if any(uso.get((*chave, t)) for t in turnos):
        return {**linha, "erro": f"{p['name']} is already in this cart at this time."}
    for t in turnos:
        uso[(*chave, t)] = 1
    return linha


def _linha_lead_follow(con, sessao):
    """#279 (dono, 15/10): o Lead and Follow é um add-on do dia de treino, $769 (preço do painel, #50). Vira uma
    linha própria — o cliente vê o que paga, o Stripe também — presa à sessão: mesmo dia, turno e piloto, e o
    mesmo `idx` (tirar a linha só desliga o add-on). Sessão com problema: o problema é dela, não do add-on."""
    from command_center.providers import servicos_site
    a = servicos_site.addon_do_site(con)
    base = {"tipo": "addon", "idx": sessao["idx"], "quantidade": 1, "deposito": 0, "data": sessao.get("data"),
            "turno": sessao.get("turno"), "piloto": sessao.get("piloto"), "piloto_nome": sessao.get("piloto_nome"),
            "detalhe": sessao.get("detalhe"), "link": "/services/arrive-and-drive/#reservar"}
    if not a:
        return {**base, "servico": None, "nome": "Lead and Follow", "unitario": 0, "valor": 0,
                "erro": "Lead and Follow is not open for online booking right now. Remove it to continue, or talk to us."}
    return {**base, "servico": a["id"], "nome": a["name"], "unitario": float(a["price"]), "valor": round(float(a["price"]), 2),
            "erro": None}


def _limites(con):
    """#309: o que o box tem de cada produto em estoque (só o servidor usa; nunca vai para o navegador)."""
    from command_center.providers import loja
    return loja.limites(con)


def cotar(con, itens, conta_id=None, para_pagar=False, entrega=None):
    """As linhas do carrinho como o servidor as vê. `itens` vem do navegador: só escolhas, nunca valor.
    #298: `entrega` ("envio" | "retirada") põe o frete dos produtos no total."""
    if not isinstance(itens, list):
        itens = []
    produtos = _produtos(con)
    pilotos = {p["id"]: p for p in todos(con, "SELECT id, name FROM portal_pilots WHERE account_id=? AND active=1",
                                         (conta_id,))} if conta_id else {}
    uso, linhas, no_estoque = {}, [], {}
    limites = _limites(con) if any(isinstance(x, dict) and x.get("tipo") == "produto" for x in itens[:MAX_ITENS]) else {}
    for i, it in enumerate(itens[:MAX_ITENS]):
        if not isinstance(it, dict):
            continue
        tipo = it.get("tipo")
        if tipo == "produto":
            linha = _linha_produto(produtos, it, entrega, limites, no_estoque)
        elif tipo == "sessao":
            linha = _linha_sessao(con, it, conta_id, uso, pilotos, para_pagar)
        else:
            continue
        linha["idx"] = i
        linha["valor"] = round(linha["unitario"] * linha["quantidade"], 2)
        linhas.append(linha)
        if tipo == "sessao" and it.get("lead_follow") is True:
            linhas.append(_linha_lead_follow(con, linha))
    validas = [x for x in linhas if not x["erro"]]
    subtotal = round(sum(x["valor"] for x in validas), 2)
    deposito = round(sum(x["deposito"] for x in validas), 2)
    tem_sessao = any(x["tipo"] == "sessao" for x in linhas)
    tem_produto = any(x["tipo"] == "produto" for x in linhas)
    prods = [x for x in validas if x["tipo"] == "produto"]
    envio = entrega == "envio" and tem_produto
    frete = round(sum(x["frete"] for x in prods), 2) if envio else 0.0
    return {"linhas": linhas, "subtotal": subtotal, "deposito": deposito, "frete": frete,
            "total": round(subtotal + deposito + frete, 2), "entrega": "envio" if envio else "retirada",
            # o que o "Ship to me" custaria, e se algum produto tem o frete combinado à parte
            "frete_envio": round(sum(x["frete_envio"] or 0 for x in prods), 2),
            "frete_a_combinar": any(x["frete_envio"] is None for x in prods),
            "tem_sessao": tem_sessao, "tem_produto": tem_produto,
            "precisa_conta": bool(linhas) and not conta_id,          # #248: toda compra pede a conta do site
            "ok": bool(linhas) and not any(x["erro"] or x.get("falta_piloto") for x in linhas),
            "demais": len(itens) > MAX_ITENS}


# ------------------------------------------------------------------ 2. o checkout
def _nome_stripe(x):
    if x["tipo"] in ("sessao", "addon"):
        return f"{x['nome']} · {x['detalhe']}" + (f" · {x['piloto_nome']}" if x.get("piloto_nome") else "")
    return x["nome"]


def criar_checkout(con, itens, entrega, conta_id, origem, host, http=None, lang="en", utm=None):
    """Grava o pedido 'aberto' com as linhas e cria UMA sessão do Checkout. Devolve (pedido_id, url).
    #248: só com a conta do site (o e-mail dela vai ao Stripe e aos avisos); `lang` é o idioma da pessoa."""
    from command_center.providers import stripe_loja
    c = cotar(con, itens, conta_id, para_pagar=True, entrega=entrega)
    if not c["linhas"]:
        raise ErroCarrinho("Your cart is empty.")
    if c["demais"]:
        raise ErroCarrinho(f"Up to {MAX_ITENS} items per order.")
    if c["precisa_conta"]:
        raise PrecisaConta("Please sign in or create your URACE account to buy.")
    erro = next((x["erro"] for x in c["linhas"] if x["erro"]), None)
    if erro:
        raise ErroCarrinho(erro)
    conta = um(con, "SELECT * FROM portal_accounts WHERE id=?", (conta_id,)) if conta_id else None
    entrega = c["entrega"]
    n = sum(x["quantidade"] for x in c["linhas"])
    resumo = (c["linhas"][0]["nome"] + (f" + {len(c['linhas']) - 1} more" if len(c["linhas"]) > 1 else ""))[:200]
    oid = inserir(con, "store_orders", kind="carrinho", product_slug="carrinho", product_name=resumo, quantity=n,
                  unit_price=c["total"], amount=c["total"], delivery=entrega, origin=host, account_id=conta_id,
                  shipping_fee=c["frete"] if entrega == "envio" else None, deposit=c["deposito"],
                  email=((conta["email"] or "").lower() or None if conta else None), name=(conta["name"] if conta else None),
                  phone=(conta["phone"] if conta else None), lang="pt" if lang == "pt" else "en", utm=utm)
    # #279: o Lead and Follow vai NA linha da sessão que ele acompanha — `variation` com o nome do add-on,
    # `product_slug` "addon:<id do serviço>" e o valor somado no `amount`. A tabela só aceita produto ou sessão,
    # e mudar isso seria reconstruir uma tabela de produção (regra do dono: não sem autorização). No Stripe e no
    # recibo do QuickBooks ele continua sendo uma linha própria.
    addons = {x["idx"]: x for x in c["linhas"] if x["tipo"] == "addon"}
    for x in c["linhas"]:
        if x["tipo"] == "addon":
            continue
        a = addons.get(x["idx"]) if x["tipo"] == "sessao" else None
        inserir(con, "store_order_items", order_id=oid, kind=x["tipo"],
                name=(_nome_stripe(x) + (f" + {a['nome']}" if a else ""))[:250], quantity=x["quantidade"],
                unit_price=x["unitario"], deposit=x["deposito"],
                shipping=(x["frete_envio"] if entrega == "envio" else None) if x["tipo"] == "produto" else None,
                amount=round(x["valor"] + x["deposito"] + (x.get("frete") or 0) + (a["valor"] if a else 0), 2),
                product_slug=(f"addon:{a['servico']}" if a else x.get("produto")),
                variation=(a["nome"] if a else x.get("variacao")), service_id=x.get("servico"),
                service_name=x["nome"] if x["tipo"] in ("sessao", "addon") else None,
                date=x.get("data") if x["tipo"] in ("sessao", "addon") else None,
                period=x.get("turno") if x["tipo"] in ("sessao", "addon") else None, pilot_id=x.get("piloto"), pilot_name=x.get("piloto_nome"))
    linhas_stripe = []
    for x in c["linhas"]:
        produto = {"name": _nome_stripe(x)[:250]}
        if x.get("foto") and not origem.startswith("http://"):
            from command_center.vitrine import paginas
            produto["images"] = [origem + paginas.foto_url(x["foto"])]
        linhas_stripe.append({"quantity": x["quantidade"], "price_data": {"currency": "usd", "unit_amount": round(x["unitario"] * 100),
                                                                          "product_data": produto}})
        if x["deposito"] > 0:
            if x["tipo"] == "produto":                       # #298: o depósito do produto, por unidade
                dep = {"name": f"Refundable security deposit · {x['nome']}"[:250]}
            else:
                dep = {"name": f"Refundable security deposit · {x['nome']} · {x['detalhe']}"[:250], "description": DEPOSITO_TXT}
            linhas_stripe.append({"quantity": 1, "price_data": {"currency": "usd", "unit_amount": round(x["deposito"] * 100),
                                                                "product_data": dep}})
    if c["frete"] > 0:                                       # #298: o frete fixo dos produtos, numa linha própria
        linhas_stripe.append({"quantity": 1, "price_data": {"currency": "usd", "unit_amount": round(c["frete"] * 100),
                                                            "product_data": {"name": "Shipping"}}})
    campos = {
        "mode": "payment",
        "line_items": linhas_stripe,
        "success_url": f"{origem}/cart/thanks/?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{origem}/cart/?cancelled=1",
        "client_reference_id": str(oid),
        "metadata": {"pedido": oid, "tipo": "carrinho", "entrega": entrega, "conta": conta_id or "", "frete": f"{c['frete']:.2f}"},
        "payment_intent_data": {"description": f"URACE order #{oid}: {resumo}"[:250], "metadata": {"pedido": oid}},
        "phone_number_collection": {"enabled": True},
        "billing_address_collection": "auto",
    }
    if conta:
        campos["customer_email"] = conta["email"]
    campos["locale"] = stripe_loja.locale_stripe(lang)
    limites = _limites(con)
    estoque_limitado = any(x["tipo"] == "produto" and (x.get("produto"), x.get("variacao") or "") in limites for x in c["linhas"])
    if c["tem_sessao"] or estoque_limitado:
        # a vaga (e, #309, a última unidade do estoque) não fica presa por um dia num checkout esquecido
        campos["expires_at"] = int(time.time()) + EXPIRA_S
    if entrega == "envio":
        campos["shipping_address_collection"] = {"allowed_countries": list(stripe_loja.PAISES_ENVIO)}
    try:
        s = (http or stripe_loja._http)("POST", "/v1/checkout/sessions", campos, idem=f"urace-carrinho-{oid}")
    except stripe_loja.ErroStripe:
        atualizar(con, "store_orders", oid, status="falhou", updated_at=agora())
        raise
    atualizar(con, "store_orders", oid, stripe_session_id=s["id"], stripe_url=s.get("url"), updated_at=agora())
    auditar(con, "store.cart.checkout", f"portal:{conta_id}" if conta_id else "site", entity_type="store_order", entity_id=oid,
            detail={"linhas": len(c["linhas"]), "sessoes": sum(1 for x in c["linhas"] if x["tipo"] == "sessao"),
                    "valor": c["subtotal"], "deposito": c["deposito"], "frete": c["frete"]})
    return oid, s.get("url")


# ------------------------------------------------------------------ 3. pago: sessões, cards, Vendas
def itens(con, oid):
    return todos(con, "SELECT * FROM store_order_items WHERE order_id=? ORDER BY id", (oid,))


def _vaga(con, x, conta_id):
    """A vaga ainda existe? Agora vale a regra da equipe (capacidade e bloqueio): a pessoa já pagou dentro
    do prazo do Checkout, a antecedência mínima não derruba a compra."""
    dia = date.fromisoformat(x["date"])
    d = ag.disponibilidade(con, dia, dia, visao="equipe")["dias"]
    if not d or not d[0]["periods"][x["period"]]["open"]:
        return False
    return not um(con, """SELECT 1 AS x FROM bookings WHERE account_id=? AND date=? AND status IN ('pendente','confirmada')
                           AND COALESCE(pilot_id,0)=COALESCE(?,0) AND (period=? OR period='dia' OR ?='dia')""",
                  (conta_id, x["date"], x["pilot_id"], x["period"], x["period"]))


def _marcar(con, o, x):
    """A sessão paga vira agendamento já aceito e pago (falta a waiver para confirmar sozinha, #50)."""
    from command_center.providers import cobranca_agenda as cob
    from command_center.providers import venda_site
    from command_center.providers import vinculo_site as vs
    if x["booking_id"] or x["status"]:
        return x["client_id"]
    if not o["account_id"] or not x["pilot_id"] or not _vaga(con, x, o["account_id"]):
        nota = ("a vaga sumiu entre o checkout e o pagamento: remarcar com o cliente ou devolver o valor"
                if o["account_id"] and x["pilot_id"] else "sessão sem conta ou piloto: marcar à mão")
        con.execute("UPDATE store_order_items SET status='sem_vaga', note=? WHERE id=?", (nota, x["id"]))
        return None
    bid = inserir(con, "bookings", account_id=o["account_id"], pilot_id=x["pilot_id"], date=x["date"], period=x["period"],
                  status="pendente", service_id=x["service_id"], service_name=x["service_name"], price=x["unit_price"],
                  notes=f"Paid online: URACE order #{o['id']}" + (f" · + {x['variation']} (add-on, {_usd(_valor_addon(x))}, paid)"
                                                                    if _tem_addon(x) else ""),
                  origin="site", accepted_at=agora(), charge_kind="stripe",
                  paid_at=agora(), invoice_total=x["amount"], store_order_id=o["id"], utm=o["utm"],
                  pilot_pending=1 if _piloto_pendente(con, x["pilot_id"]) else 0)   # #305: lembrar até completar
    b = um(con, "SELECT * FROM bookings WHERE id=?", (bid,))
    try:
        card, nota = venda_site.garantir_card(con, b)
    except (vs.ErroVinculo, cob.ErroCobranca) as e:
        card, nota = None, f"erro: {e}"
    if nota:
        atualizar(con, "bookings", bid, card_note=nota[:300], updated_at=agora())
    con.execute("UPDATE store_order_items SET status='marcada', booking_id=?, client_id=? WHERE id=?", (bid, card, x["id"]))
    auditar(con, "booking.paid.cart", "stripe", entity_type="booking", entity_id=bid,
            detail={"pedido": o["id"], "card": card, "valor": x["amount"]})
    return card


def _piloto_pendente(con, pid):
    from command_center.providers import conta_site
    return conta_site.piloto_pendente(con, pid)


def _tem_addon(x):
    """#279: a linha da sessão leva um add-on (Lead and Follow) pago junto."""
    return x["kind"] == "sessao" and str(x["product_slug"] or "").startswith("addon:")


def _valor_addon(x):
    return round(float(x["amount"]) - float(x["unit_price"]) * x["quantity"] - float(x["deposit"] or 0)
                 - float(x.get("shipping") or 0), 2)


def _texto_linha(x):
    v = _usd(x["unit_price"] * x["quantity"]) + (f" + {x['variation']} {_usd(_valor_addon(x))}" if _tem_addon(x) else "")
    s = f"- {x['name']}" + (f" × {x['quantity']}" if x["quantity"] > 1 else "") + f": {v}"
    if x["deposit"]:
        s += f" + depósito {_usd(x['deposit'])}"
    if x.get("shipping"):
        s += f" + frete {_usd(x['shipping'])}"           # #298
    if x["status"] == "sem_vaga":
        s += f"\n  ⚠ SEM VAGA: {x['note']}"
    elif (x.get("stock_note") or "").startswith("sem estoque"):      # #309: a equipe resolve (o pagamento ficou)
        s += f"\n  ⚠ SEM ESTOQUE: {x['stock_note']}"
    elif x["booking_id"]:
        s += f" (agendamento #{x['booking_id']})"
    return s


def pago(con, oid):
    """Pedido do carrinho pago: marca as sessões, liga os cards e abre uma oportunidade GANHO por card.
    Só banco local (rápido, dentro da resposta ao webhook). Rodar de novo não refaz nada."""
    from command_center.providers import stripe_loja
    o = um(con, "SELECT * FROM store_orders WHERE id=?", (oid,))
    if o["opp_id"]:
        return o["opp_id"]
    grupos = {}                                              # card → linhas (None: a equipe vincula)
    for x in itens(con, oid):
        if x["kind"] == "sessao":
            card = _marcar(con, o, x)
            grupos.setdefault(card, []).append(x["id"])
    from command_center.providers import estoque_site
    sem_estoque = estoque_site.baixar_do_pedido(con, oid)    # #309: o produto em estoque sai do estoque, uma vez só
    produtos = [x["id"] for x in itens(con, oid) if x["kind"] == "produto"]
    nota_produto = None
    if produtos:
        cid, nota_produto = stripe_loja._cliente(con, o)
        grupos.setdefault(cid, []).extend(produtos)
    linhas = {x["id"]: x for x in itens(con, oid)}
    sem_vaga = [x for x in linhas.values() if x["status"] == "sem_vaga"]
    from command_center.providers import pedido_site
    entrega = ("retirada na pista (Orlando Kart Center)" if o["delivery"] == "retirada"
               else pedido_site.texto_envio_equipe(o, list(linhas.values())).replace("ENVIO — ", "envio: "))
    conta = um(con, "SELECT name, email, phone FROM portal_accounts WHERE id=?", (o["account_id"],)) if o["account_id"] else None
    quem = (conta or {}).get("name") or o["name"] or o["email"] or "Cliente do site"     # o responsável da conta, não o nome do cartão
    primeira = None
    for card, ids in sorted(grupos.items(), key=lambda g: (g[0] is None, g[0] or 0)):
        ls = [linhas[i] for i in ids]
        valor = round(sum(x["amount"] for x in ls), 2)
        sessoes = [x for x in ls if x["kind"] == "sessao"]
        pilotos = sorted({x["pilot_name"] for x in sessoes if x["pilot_name"]})
        notas = (f"[Site · carrinho pago no Stripe] Pedido #{oid} — {_usd(valor)}\n" + "\n".join(_texto_linha(x) for x in ls)
                 + (f"\nEntrega: {entrega}" if any(x["kind"] == "produto" for x in ls) else "")
                 + (f"\nEndereço:\n{stripe_loja._endereco(o)}" if o["delivery"] == "envio" and o["shipping"] else "")
                 + ("\nCard: " + (f"card {card}" if card else "vincular à mão")
                    + (f" ({nota_produto})" if nota_produto and any(x["kind"] == "produto" for x in ls) else "")))
        servico = "Site: " + "; ".join(x["name"] for x in ls)
        opp = inserir(con, "opportunities", name=quem, email=(conta or {}).get("email") or o["email"],
                      phone=(conta or {}).get("phone") or o["phone"],
                      pilot_name=", ".join(pilotos) or None, service=servico[:300],
                      service_date=sessoes[0]["date"] if sessoes else None, amount=valor,
                      stage="GANHO" if card else "FECHAMENTO", source="Site", client_id=card, notes=notas, campaign=o["utm"],
                      closing=json.dumps({"em": agora(), "por": "stripe", "pedido": oid}, ensure_ascii=False))
        inserir(con, "opp_events", opp_id=opp, kind="note", title="Pago no carrinho do site (Stripe)", detail=notas[:2000],
                at=agora(), actor="site")
        con.execute(f"UPDATE store_order_items SET opp_id=? WHERE id IN ({','.join('?' * len(ids))})", (opp, *ids))
        if card:
            con.execute(f"UPDATE store_order_items SET client_id=? WHERE client_id IS NULL AND id IN ({','.join('?' * len(ids))})",
                        (card, *ids))
        primeira = primeira or (opp, card)
    atencao = ("; ".join([f"{x['name']}: {x['note']}" for x in sem_vaga] + sem_estoque))[:500] or None
    nota = "; ".join(filter(None, [f"{len([g for g in grupos if g])} card(s) ligado(s)" if any(grupos) else None,
                                   "vincular à mão" if None in grupos else None, nota_produto]))
    atualizar(con, "store_orders", oid, client_id=primeira[1], opp_id=primeira[0], link_note=nota[:300] or None,
              attention=atencao, updated_at=agora())
    auditar(con, "store.paid", "stripe", entity_type="store_order", entity_id=oid,
            detail={"carrinho": True, "opps": len(grupos), "sem_vaga": len(sem_vaga), "valor": o["amount_paid"] or o["amount"],
                    **({"sem_estoque": len(sem_estoque)} if sem_estoque else {})})
    return primeira[0]


# ------------------------------------------------------------------ 4. depois de pago (fora da resposta)
def seguir_sessoes(con, oid, enviar_waiver=None):
    """A waiver de cada sessão marcada (a nativa fica para o cliente assinar na conta) e a confirmação
    sozinha quando a waiver já está em dia. É o mesmo que a rodada de 15 min faz; aqui sai na hora."""
    from command_center.providers import cobranca_agenda as cob
    feitas = []
    for x in itens(con, oid):
        if not x["booking_id"]:
            continue
        b = um(con, "SELECT * FROM bookings WHERE id=?", (x["booking_id"],))
        if b and b["status"] == "pendente":
            if not b["waiver_ref"]:
                cob.pedir_waiver(con, b, enviar_waiver)
            cob.verificar(con, b["id"])
            feitas.append(b["id"])
    return feitas


def _link_sessao(bid):
    from command_center import enderecos
    return f"https://{enderecos.CLIENTE}/ops/portal/sessions/{bid}"


def avisar(con, oid, enviar=None):
    """A confirmação para quem comprou e o aviso para a equipe. Uma vez só."""
    from command_center.providers import pedido_site, stripe_loja
    o = um(con, "SELECT * FROM store_orders WHERE id=?", (oid,))
    if not o or o["status"] != "pago" or o["notified_at"]:
        return False
    ls = itens(con, oid)
    valor = o["amount_paid"] if o["amount_paid"] is not None else o["amount"]
    lang = pedido_site.lingua(o)                        # #248: no idioma em que a pessoa comprou
    pedido_site.registrar_no_card(con, o, "pago")       # #248: o pagamento na linha do tempo de cada card
    pt = lang == "pt"
    cli = []
    for x in ls:
        linha = (f"- {pedido_site.nome_linha(x, lang)}" + (f" × {x['quantity']}" if x["quantity"] > 1 else "")
                 + f": {_usd(x['unit_price'] * x['quantity'])}")
        if x["deposit"]:
            linha += f"\n  {'Depósito de segurança reembolsável' if pt else 'Refundable security deposit'}: {_usd(x['deposit'])}"
        if x.get("shipping"):                              # #298: o frete fixo do produto
            linha += f"\n  {'Frete' if pt else 'Shipping'}: {_usd(x['shipping'])}"
        if x["kind"] == "sessao" and x["booking_id"]:
            linha += (f"\n  Reservada. Assine a waiver na sua conta URACE para confirmar: {_link_sessao(x['booking_id'])}" if pt else
                      f"\n  Booked. Sign the waiver in your URACE account to confirm it: {_link_sessao(x['booking_id'])}")
        elif x["kind"] == "sessao":
            linha += ("\n  Este horário foi ocupado logo antes do seu pagamento. A nossa equipe vai ligar para escolher outro horário "
                      "(ou devolver o valor). O seu pagamento está seguro." if pt else
                      "\n  This time was taken just before your payment. Our team will call you to pick another time (or refund it). "
                      "Your payment is safe.")
        cli.append(linha)
    tem_produto = any(x["kind"] == "produto" for x in ls)
    if pt:
        entrega = ("" if not tem_produto else
                   "\nItens da loja: avisamos quando estiverem prontos para retirar no Orlando Kart Center (10724 Cosmonaut Blvd, "
                   "Box 3, Orlando, FL 32824).\n" if o["delivery"] == "retirada" else
                   f"\nItens da loja: {pedido_site.texto_envio(o, ls, lang)}\n")
        deposito = ("\nDepósito de segurança: " + dica.DEPOSITO_INFO_PT + "\n"
                    if any(x["deposit"] for x in ls) else "")
        assunto = f"Pedido #{o['id']} confirmado — URACE"
        texto = (f"{pedido_site.ola(o, lang)},\n\nObrigado pelo pedido! Recebemos o seu pagamento.\n\n" + "\n".join(cli)
                 + f"\n\nTotal pago: {_usd(valor)}\nPedido: #{o['id']}\n{entrega}{deposito}\n"
                 f"Página do seu pedido: {pedido_site.link(o)}\n\n{pedido_site.contato(lang)}\n\nURACE — the Champion's Factory")
    else:
        entrega = ("" if not tem_produto else
                   "\nStore items: we'll let you know when they're ready for pickup at the Orlando Kart Center (10724 Cosmonaut Blvd, Box 3, "
                   "Orlando, FL 32824).\n" if o["delivery"] == "retirada" else
                   f"\nStore items: {pedido_site.texto_envio(o, ls, lang)}\n")
        deposito = ("\nSecurity deposit: " + dica.DEPOSITO_INFO + "\n"
                    if any(x["deposit"] for x in ls) else "")
        assunto = f"Order #{o['id']} confirmed — URACE"
        texto = (f"{pedido_site.ola(o, lang)},\n\nThanks for your order! We received your payment.\n\n" + "\n".join(cli)
                 + f"\n\nTotal paid: {_usd(valor)}\nOrder: #{o['id']}\n{entrega}{deposito}\n"
                 f"Your order page: {pedido_site.link(o)}\n\n"
                 "Questions? Call or WhatsApp +1 (407) 250 2291.\n\nURACE — the Champion's Factory")
    try:
        if o["email"]:
            stripe_loja._enviar(enviar, o["email"], assunto, texto)
        equipe = (f"Pedido #{o['id']} pago no Stripe: {_usd(valor)}\n{o['name'] or ''} <{o['email'] or ''}> {o['phone'] or ''}\n\n"
                  + "\n".join(_texto_linha(x) for x in ls)
                  + (f"\n\nEntrega: {'retirada na pista' if o['delivery'] == 'retirada' else pedido_site.texto_envio_equipe(o, ls)}" if tem_produto else "")
                  + (f"\nEndereço:\n{stripe_loja._endereco(o)}" if o["shipping"] else "")
                  + (f"\n\nATENÇÃO: {o['attention']}" if o["attention"] else "")
                  + "\n\nVendas: " + ", ".join(sorted({f"https://ops.urace.us/ops/sales/{x['opp_id']}" for x in ls if x["opp_id"]}))
                  + f"\nPágina do pedido: {pedido_site.link(o)}")
        aviso = ("".join([" · SEM VAGA" if any(x["status"] == "sem_vaga" for x in ls) else "",       # #309: e sem estoque
                          " · SEM ESTOQUE" if any((x.get("stock_note") or "").startswith("sem estoque") for x in ls) else ""])
                 if o["attention"] else "")
        stripe_loja._enviar(enviar, "support@urace.us",
                            f"Site · PAGO{aviso}: pedido #{o['id']} — {o['name'] or o['email']}", equipe)
        atualizar(con, "store_orders", oid, notified_at=agora(), notify_error=None, updated_at=agora())
        pedido_site.avisado_pago(con, o, o["email"])
        return True
    except Exception as e:                              # noqa: BLE001 — o pedido já está pago e em Vendas
        atualizar(con, "store_orders", oid, notify_error=str(e)[:300], updated_at=agora())
        return False


def _item_deposito(con):
    i = um(con, """SELECT id FROM qbo_items WHERE active=1
                    AND (LOWER(name) LIKE '%security deposit%' OR LOWER(COALESCE(full_name,'')) LIKE '%security deposit%')
                  ORDER BY id LIMIT 1""")
    if not i:
        raise RuntimeError('não achei o item "Security deposit" no QuickBooks (sincronize o QuickBooks)')
    return i["id"]


def linhas_qbo(con, q, oid):
    """As linhas do Sales Receipt: o produto (o item da loja), o serviço (o item do QuickBooks do serviço) e
    o depósito (o item "Security deposit", como a invoice da agenda faz)."""
    saida = []
    for x in itens(con, oid):
        if x["kind"] == "produto":
            fim = f" ({x['variation']})" if x["variation"] else ""
            nome = x["name"][:-len(fim)] if fim and x["name"].endswith(fim) else x["name"]     # o item é o do produto (#174)
            item = q.item_loja_sistema(nome, x["unit_price"], f"URACE Store: {nome}")["id"]
        else:
            s = um(con, "SELECT qbo_item_id FROM booking_services WHERE id=?", (x["service_id"],))
            if not s or not s["qbo_item_id"]:
                raise RuntimeError(f"o serviço {x['service_name']} não tem item do QuickBooks (Site › Serviços e preços)")
            item = s["qbo_item_id"]
        saida.append({"item_id": item, "quantidade": x["quantity"], "unitario": x["unit_price"], "descricao": x["name"]})
        if _tem_addon(x):                                    # #279: o Lead and Follow pago junto com a sessão
            sid_addon = int(str(x["product_slug"]).split(":", 1)[1])
            a = um(con, "SELECT name, qbo_item_id FROM booking_services WHERE id=?", (sid_addon,))
            if not a or not a["qbo_item_id"]:
                raise RuntimeError(f"o add-on {x['variation']} não tem item do QuickBooks (Site › Serviços e preços)")
            saida.append({"item_id": a["qbo_item_id"], "quantidade": 1, "unitario": _valor_addon(x), "descricao": a["name"]})
        if x["deposit"]:
            saida.append({"item_id": _item_deposito(con), "quantidade": 1, "unitario": x["deposit"],
                          "descricao": DEPOSITO_TXT if x["kind"] == "sessao" else "Refundable security deposit"})
        if x.get("shipping"):                                # #298: o frete fixo do produto, no item "Shipping"
            saida.append({"item_id": item_frete(q), "quantidade": 1, "unitario": x["shipping"], "descricao": f"Shipping: {x['name']}"})
    return saida


def item_frete(q):
    return q.item_loja_sistema("Shipping", 0, "URACE Store: shipping")["id"]


# ------------------------------------------------------------------ 5. o painel
def do_painel(con, opp_id):
    """O pedido do site ligado a esta oportunidade, com as linhas (Vendas mostra no detalhe da venda).
    Carrinho (#236): todas as linhas do pedido, marcando as desta venda. Loja (#174): uma linha."""
    from command_center.providers import pedido_site
    o = um(con, """SELECT * FROM store_orders WHERE opp_id=?
                    OR id IN (SELECT order_id FROM store_order_items WHERE opp_id=?) ORDER BY id DESC LIMIT 1""",
           (opp_id, opp_id))
    if not o:
        return None
    if o["kind"] == "carrinho":
        ls = [{"id": x["id"], "tipo": x["kind"], "nome": x["name"], "quantidade": x["quantity"], "unitario": x["unit_price"],
               "deposito": x["deposit"], "valor": x["amount"], "data": x["date"], "turno": x["period"], "piloto": x["pilot_name"],
               "status": x["status"], "agendamento": x["booking_id"], "card": x["client_id"], "nota": x["note"],
               "desta_venda": x["opp_id"] == opp_id} for x in itens(con, o["id"])]
    else:
        ls = [{"id": None, "tipo": "produto", "nome": o["product_name"] + (f" ({o['variation']})" if o["variation"] else ""),
               "quantidade": o["quantity"], "unitario": o["unit_price"], "deposito": 0, "valor": o["amount"], "data": None,
               "turno": None, "piloto": None, "status": None, "agendamento": None, "card": o["client_id"], "nota": None,
               "desta_venda": True}]
    return {"id": o["id"], "tipo": o["kind"], "status": o["status"], "total": o["amount"], "pago": o["amount_paid"],
            "pago_em": o["paid_at"], "entrega": o["delivery"], "recibo_qbo": o["qbo_receipt_doc"], "erro_qbo": o["qbo_error"],
            "atencao": o["attention"], "linhas": ls, "link": pedido_site.link(o)}       # #245: a página do pedido

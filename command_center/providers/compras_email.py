"""E-mail de compra que chega no urace@ vira compra no painel — e cada atualização a move.

Dono, 30/09: *"faça com que todo email relacionado a compra que chegar no urace@urace se
torne um item de compra, e toda atualização de shipping / envio, confirmação de pagamento,
confirmação de delivered atualize essa tarefa; caso tenha somente a atualização do envio,
crie também automaticamente"*.

Como funciona, em cada ciclo da sincronia (15 min):

1. Busca no urace@ (a caixa inteira, não só a inbox: o filtro do Gmail arquiva
   "Finances/Shopping" e "Shipping Status") as conversas dos últimos dias com cara de compra.
2. Relê só a conversa que ganhou mensagem nova (`purchase_email_threads`).
3. Cada mensagem é classificada em **pedido · pagamento · envio · entregue · cancelado ·
   reembolso**, e dela sai o nº do pedido, o rastreio, a transportadora, o total e a
   previsão de chegada — quando a loja escreveu.
4. Acha a compra pelo nº do pedido (ou pela referência digitada à mão) e, se não achar,
   pelo rastreio. Não achou: **cria** a compra (origem e-mail), mesmo que o primeiro
   e-mail seja só o "foi enviado".
5. Cada mensagem vira um evento na linha do tempo da compra (uma vez só: message_id único).

O que NÃO faz, de propósito:
- **Não dá entrada no estoque.** "Delivered" é a transportadora dizendo que deixou a caixa;
  quem abre e conta é gente. A compra entregue sem entrada aparece em "Precisa de atenção".
- **Não inventa item.** O e-mail diz que houve pedido; o que exatamente foi, com quantidade
  e custo, quem comprou confirma (ou liga os pedidos da equipe, que já têm quantidade).
- **Não confunde venda com compra.** Pedido da nossa loja, pagamento de invoice nossa e
  propaganda ficam de fora (ver `_ignorar`).
- **Não escreve no Gmail.** Só lê.
"""
import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parseaddr

from command_center.db import agora, atualizar, auditar, inserir, todos, um
from command_center.providers import NaoConectado, chamar, compras, estoque

CAIXA = "urace"
JANELA_DIAS = 2            # cada ciclo olha os últimos 2 dias (o ciclo é de 15 min: sobra folga)
PRIMEIRA_VEZ_DIAS = 7      # na primeira passada, uma semana para trás
MAX_THREADS = 400

CONSULTA = ("-in:sent -in:drafts -category:promotions -category:social newer_than:{dias}d "
            "{label:finances-shopping label:finances-shopping-amazon label:shipping-status label:canotops "
            "label:fornecedores-pendente label:fornecedores-recebido "
            "subject:order subject:ordered subject:shipped subject:shipping subject:shipment subject:delivered "
            "subject:delivery subject:tracking subject:\"on its way\" subject:\"on the way\" subject:receipt "
            "subject:payment subject:pedido subject:purchase subject:package subject:envio subject:entrega "
            "subject:rastreio subject:compra}")

ORDEM = {"pedido": 1, "pagamento": 2, "envio": 3, "entregue": 4}            # tipo do e-mail
STATUS = {"pedido": "pedido", "pagamento": "pago", "envio": "enviado", "entregue": "entregue"}
PESO = {"pedido": 1, "pago": 2, "enviado": 3, "entregue": 4}                 # andamento da compra

# ------------------------------------------------------------------ classificação
# A ordem importa: "Delivered: your order #123" é entrega, não pedido.
_TIPOS = [
    # "will be delivered today" / "delivered by Friday" é previsão, não entrega
    ("entregue", r"(\b(?<!be )(?<!being )delivered\b(?!\s+(by|on|tomorrow|today|between|to you))|\bfoi entregue\b|(?<!será )(?<!sera )(?<!ser )\bentregue\b(?!\s+at[eé])|"
                 r"\bdelivery complete\b)"),
    ("cancelado", r"\b(cancel+ed|cancel+ation|cancelad[oa])\b"),
    ("reembolso", r"\b(refund(ed)?|reembolso|estorno)\b"),
    ("envio", r"\b(shipped|has shipped|shipping (confirmation|update|notification)|shipment|on (its|the) way|out for delivery|"
              r"in transit|dispatched|tracking (number|info|update)|label created|arriving|will be delivered|to be delivered|scheduled (for )?delivery|delivery (today|tomorrow)|ser[aá] entregue|enviad[oa]|a caminho|saiu para entrega|rastreio)\b"),
    ("pagamento", r"\b(payment (confirmation|confirmed|received|successful|complete[d]?|processed)|payment to|receipt|"
                  r"paid|pagamento (confirmado|aprovado|recebido)|recibo|invoice paid)\b"),
    ("pedido", r"\b(order (confirmation|confirmed|received|placed|summary|details)|your order|thanks? (you )?for your (order|purchase)|"
               r"purchase (confirmation|order)|ordered|order #|pedido (confirmado|recebido|realizado|feito)|compra (confirmada|realizada))\b"),
]
_TIPOS = [(k, re.compile(p, re.I)) for k, p in _TIPOS]

# Venda nossa, cobrança de cliente, assinatura e propaganda: não é compra de peça/insumo.
_NAO_E_COMPRA = re.compile(
    r"(placed by|new order|you'?ve got a new order|you have a new order|nova venda|new sale|"
    r"received a payment|payment received from|you received|you've received|payout|"
    r"invoice from urace|from urace\.?us|subscription|renewal|your plan|free trial|membership|"
    r"\d+\s?% off|sale ends|deal of|coupon|promo code|webinar|newsletter)", re.I)
_REMETENTES_FORA = ("urace.us", "intuit.com", "quickbooks", "docusign", "kommo", "simplybook", "asana.com",
                    "dialpad", "google.com", "anthropic.com")
_MARCADORES_FORA = ("URace Store/", "Customer Service/", "CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "SENT", "DRAFT", "SPAM", "TRASH")


# Dono, 30/09: recibo do Orlando Kart Center (passe de pista) NÃO vira compra.
_LOJAS_FORA = ("orlandokartcenter", "orlando kart center")


def _ignorar(msg):
    """Motivo para não ser compra, ou None."""
    de = (msg.get("de") or "").lower()
    email = parseaddr(msg.get("de") or "")[1].lower()
    marcas = " ".join(str(m).lower() for m in (msg.get("marcadores") or []))
    if any(x in de or x in email.replace(".", "").replace("-", "") or x in marcas for x in _LOJAS_FORA):
        return "Orlando Kart Center (dono: passe de pista não é compra)"
    if any(email.endswith(d) or d in email.split("@")[-1] for d in _REMETENTES_FORA):
        return "remetente fora (nosso ou de sistema)"
    marc = msg.get("marcadores") or []
    if any(str(m).startswith(p) or str(m) == p for m in marc for p in _MARCADORES_FORA):
        return "marcador fora (venda nossa, atendimento ou propaganda)"
    if _NAO_E_COMPRA.search(msg.get("assunto") or "") or "urace store" in de:
        return "assunto de venda, assinatura ou propaganda"
    return None


def tipo(assunto, tem_rastreio=False, tem_pedido=False):
    """Pelo ASSUNTO. O corpo de e-mail de loja fala de tudo ("cancel anytime", "track your
    package", "delivered"), então quando o assunto não diz, só o que é concreto decide:
    tem rastreio → envio; tem nº de pedido → pedido; nada disso → não é compra."""
    for k, rx in _TIPOS:
        if rx.search(assunto or ""):
            return k, "assunto"
    if tem_rastreio:
        return "envio", "corpo"
    if tem_pedido:
        return "pedido", "corpo"
    return None, None


# ------------------------------------------------------------------ extração
_AMAZON = re.compile(r"\b\d{3}-\d{7}-\d{7}\b")
_NUM_PEDIDO = re.compile(r"(?:order|pedido|purchase order|p\.o\.)\s*(?:number|no\.?|nº|n°|num\.?|id)?\s*[:#]?\s*#?\s*"
                         r"([A-Z0-9][A-Z0-9-]{2,24})", re.I)
_UPS = re.compile(r"\b1Z[0-9A-Z]{16}\b")
_TBA = re.compile(r"\bTBA\d{12}\b")
_USPS = re.compile(r"\b(9[2-5]\d{18,20})\b")
_RASTREIO = re.compile(r"(?:tracking|rastreio|rastreamento)\s*(?:number|no\.?|#|id|code|c[oó]digo)?\s*[:#]?\s*([A-Z0-9]{8,34})\b", re.I)
_TOTAL = re.compile(r"(?:order total|grand total|total charged|amount paid|payment amount|amount charged|total pago|total)"
                    r"\s*(?:\(usd\))?\s*[:\-]?\s*(?:US\s?|USD\s?)?\$\s?([\d,]+(?:\.\d{2})?)", re.I)
_MESES = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_PREVISAO = re.compile(r"(?:arriving|arrives|estimated delivery|expected delivery|delivery date|delivered by|scheduled delivery|"
                       r"entrega prevista|previs[aã]o de entrega)\s*(?:date)?\s*[:\-]?\s*(?:on\s+|by\s+)?(?:[a-z]+day,?\s+)?"
                       r"(?:(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:,?\s+(\d{4}))?"
                       r"|(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?)", re.I)
_CITACAO = re.compile(r"[\"“]([^\"”]{3,160})[\"”]")


def _tem_digito(s):
    return any(c.isdigit() for c in s or "")


def numero_do_pedido(texto):
    m = _AMAZON.search(texto or "")
    if m:
        return m.group(0)
    for m in _NUM_PEDIDO.finditer(texto or ""):
        n = m.group(1).strip("-")
        if _tem_digito(n) and not re.fullmatch(r"\d{1,2}", n):
            return n
    return None


def rastreios(texto):
    """[(número, transportadora)] — sem repetir."""
    t = texto or ""
    achados = []
    for m in _UPS.finditer(t):
        achados.append((m.group(0), "UPS"))
    for m in _TBA.finditer(t):
        achados.append((m.group(0), "Amazon"))
    if re.search(r"\busps\b", t, re.I):
        achados += [(m.group(1), "USPS") for m in _USPS.finditer(t)]
    for m in _RASTREIO.finditer(t):
        n = m.group(1)
        if _tem_digito(n) and len(re.sub(r"\D", "", n)) >= 6:
            achados.append((n, transportadora(n, t)))
    vistos, saida = set(), []
    for n, c in achados:
        if n.upper() not in vistos:
            vistos.add(n.upper()); saida.append((n, c))
    return saida


def transportadora(numero, texto=""):
    if numero.upper().startswith("1Z"):
        return "UPS"
    if numero.upper().startswith("TBA"):
        return "Amazon"
    for nome, rx in (("FedEx", r"\bfed\s?ex\b"), ("USPS", r"\busps\b"), ("DHL", r"\bdhl\b"), ("UPS", r"\bups\b"),
                     ("OnTrac", r"\bontrac\b")):
        if re.search(rx, texto or "", re.I):
            return nome
    return None


def total(texto):
    """O total do pedido. "Subtotal" não conta; entre os rótulos fortes (order total, grand
    total, amount paid…) vale o primeiro; só com "Total" solto, vale o último."""
    fortes, soltos = [], []
    for m in _TOTAL.finditer(texto or ""):
        rot = m.group(0).lower()
        antes = (texto[max(0, m.start() - 3):m.start()] or "").lower()
        if antes.endswith("sub"):
            continue
        try:
            v = round(float(m.group(1).replace(",", "")), 2)
        except ValueError:
            continue
        (soltos if re.match(r"total\b", rot) else fortes).append(v)
    return fortes[0] if fortes else (soltos[-1] if soltos else None)


def previsao(texto, ref=None):
    """Previsão de chegada que a loja/transportadora escreveu (formato dos EUA)."""
    m = _PREVISAO.search(texto or "")
    if not m:
        return None
    ref = ref or date.today()
    try:
        if m.group(1):
            mes, dia, ano = _MESES[m.group(1).lower()[:3]], int(m.group(2)), int(m.group(3) or ref.year)
        else:
            mes, dia = int(m.group(4)), int(m.group(5))
            ano = int(m.group(6)) if m.group(6) else ref.year
            ano = ano + 2000 if ano < 100 else ano
        d = date(ano, mes, dia)
    except (ValueError, KeyError):
        return None
    if not m.group(3) and not (m.group(6)) and d < ref - timedelta(days=60):
        d = date(d.year + 1, d.month, d.day)          # "Arriving Jan 3" escrito em dezembro
    return d.isoformat()


_GENERICOS = re.compile(r"\b(no-?reply|do-?not-?reply|orders?|shipping|shipment|notifications?|notify|customer service|"
                        r"support|sales|team|info|store|auto-?confirm|confirm(ation)?|updates?|mailer|billing|receipts?)\b", re.I)
_CONHECIDOS = {"amazon": "Amazon", "cometkartsales": "Comet Kart Sales", "ebay": "eBay", "alibaba": "Alibaba",
               "harborfreight": "Harbor Freight", "homedepot": "The Home Depot", "lowes": "Lowe's", "walmart": "Walmart",
               "paypal": None, "shopify": None, "shop": None}
_TRANSPORTADORAS = {"ups": "UPS", "fedex": "FedEx", "usps": "USPS", "dhl": "DHL", "ontrac": "OnTrac"}


def _base_do_dominio(email):
    partes = (email.split("@")[-1] or "").lower().split(".")
    partes = [p for p in partes if p]
    if len(partes) >= 3 and partes[-2] in ("co", "com") and len(partes[-1]) == 2:
        return partes[-3]
    return partes[-2] if len(partes) >= 2 else (partes[0] if partes else "")


def fornecedor(de, texto=""):
    """(fornecedor, é_transportadora). O nome de exibição vale mais que o domínio, menos
    quando é genérico ("Orders", "no-reply")."""
    nome, email = parseaddr(de or "")
    base = _base_do_dominio(email)
    if base in _TRANSPORTADORAS:
        return None, _TRANSPORTADORAS[base]
    if base in _CONHECIDOS and _CONHECIDOS[base]:
        return _CONHECIDOS[base], None
    if base == "paypal":                                   # "Receipt for your payment to Comet Kart Sales"
        m = re.search(r"payment to\s+([A-Z][\w&'. -]{2,40}?)(?:\s*[\n.,]|$)", texto or "")
        return (m.group(1).strip() if m else "PayPal"), None
    limpo = re.sub(r"\s+", " ", _GENERICOS.sub(" ", (nome or "").replace('"', ""))).strip(" -|·@")
    if len(limpo) >= 3:
        return limpo[:60], None
    return (base.capitalize() if base else "Fornecedor não identificado"), None


def _norm(s):
    return estoque._norm(s).upper()


def ler(msg):
    """O que uma mensagem diz, sem tocar no banco. None quando não é compra."""
    assunto = msg.get("assunto") or ""
    corpo = msg.get("corpo") or msg.get("snippet") or ""
    texto = f"{assunto}\n{corpo}"
    if _ignorar(msg):
        return None
    pedido = numero_do_pedido(texto)
    track = rastreios(texto)
    k, _onde = tipo(assunto, bool(track), bool(pedido))
    if not k:
        return None
    forn, transp = fornecedor(msg.get("de"), texto)
    em = _data(msg.get("data"))
    citado = _CITACAO.search(assunto)
    return {"kind": k, "order_number": pedido, "tracking": [t for t, _ in track],
            "carrier": transp or next((c for _, c in track if c), None), "supplier": forn,
            "amount": total(corpo), "expected_at": previsao(texto, _dia(em)),
            "items_hint": citado.group(1).strip() if citado else None,
            "at": em, "subject": assunto[:300], "sender": (msg.get("de") or "")[:200],
            "excerpt": re.sub(r"\s+", " ", corpo)[:1500]}


def _data(rfc):
    from command_center.providers.sync import _data_rfc
    return _data_rfc(rfc) if rfc else agora()


def _dia(iso):
    try:
        return date.fromisoformat((iso or "")[:10])
    except ValueError:
        return None


# ------------------------------------------------------------------ ligar à compra
def achar_compra(con, info):
    """Pelo nº do pedido (ou referência digitada) primeiro; depois por rastreio."""
    abertas = todos(con, """SELECT id, order_number, reference, tracking FROM purchase_orders
                             WHERE created_at >= ? ORDER BY id DESC LIMIT 1000""",
                    ((datetime.now(timezone.utc) - timedelta(days=240)).strftime("%Y-%m-%d"),))
    if info.get("order_number"):
        alvo = _norm(info["order_number"])
        for c in abertas:
            if alvo and alvo in {_norm(c["order_number"]), _norm(c["reference"])}:
                return c["id"]
    for t in info.get("tracking") or []:
        alvo = _norm(t)
        for c in abertas:
            meus = {_norm(x) for x in (c["tracking"] or "").split()} | {_norm(c["reference"])}
            if alvo in meus:
                return c["id"]
    return None


def aplicar(con, info, mailbox, thread_id, message_id):
    """Grava a mensagem na compra certa (criando, se preciso). Devolve (purchase_id, criada)."""
    if message_id and um(con, "SELECT 1 AS x FROM purchase_events WHERE message_id=?", (message_id,)):
        return None, False
    pid = achar_compra(con, info)
    if not pid:
        # pela conversa: a mesma thread é a mesma compra — menos quando os números dizem que
        # não (o Gmail junta "Order confirmation" de pedidos diferentes da mesma loja)
        ja = um(con, """SELECT e.purchase_id, o.order_number FROM purchase_events e JOIN purchase_orders o ON o.id=e.purchase_id
                         WHERE e.thread_id=? ORDER BY e.id DESC LIMIT 1""", (thread_id,))
        if ja and not (info["order_number"] and ja["order_number"] and _norm(ja["order_number"]) != _norm(info["order_number"])):
            pid = ja["purchase_id"]
    criada = False
    if not pid:
        forn = info["supplier"] or (f"Não identificado (envio {info['carrier']})" if info["carrier"] else "Não identificado")
        pid = inserir(con, "purchase_orders", supplier=forn[:80], status="pedida", source="email",
                      order_number=info["order_number"], reference=info["order_number"],
                      ordered_at=info["at"], items_hint=info["items_hint"],
                      notes=f"Criada pelo e-mail “{info['subject'][:120]}”.")
        criada = True
    c = um(con, "SELECT * FROM purchase_orders WHERE id=?", (pid,))
    mud = {}
    if info["order_number"] and not c["order_number"]:
        mud["order_number"] = info["order_number"]
        if not c["reference"]:
            mud["reference"] = info["order_number"]
    if info["tracking"]:
        atuais = (c["tracking"] or "").split()
        novos = [t for t in info["tracking"] if _norm(t) not in {_norm(x) for x in atuais}]
        if novos:
            mud["tracking"] = " ".join(atuais + novos)[:400]
    if info["carrier"] and not c["carrier"]:
        mud["carrier"] = info["carrier"]
    if info["items_hint"] and not c["items_hint"]:
        mud["items_hint"] = info["items_hint"][:200]
    if info["amount"] is not None and info["kind"] in ("pedido", "pagamento") and c["email_total"] is None:
        mud["email_total"] = info["amount"]
    if info["expected_at"] and info["kind"] in ("pedido", "pagamento", "envio"):
        mud["expected_at"] = info["expected_at"]
    if c["supplier"].startswith("Não identificado") and info["supplier"]:
        mud["supplier"] = info["supplier"][:80]
    k = info["kind"]
    if k in ORDEM:
        if ORDEM[k] > PESO.get(c["ship_status"] or "", 0) and c["ship_status"] != "cancelado":
            mud["ship_status"] = STATUS[k]
        campo = {"pagamento": "paid_at", "envio": "shipped_at", "entregue": "delivered_at"}.get(k)
        if campo and not c[campo]:
            mud[campo] = info["at"]
        if c["status"] == "rascunho":                     # a loja confirmou: foi pedida
            mud["status"] = "pedida"
            mud["ordered_at"] = c["ordered_at"] or info["at"]
    elif k == "cancelado" and c["ship_status"] != "entregue":
        mud["ship_status"] = "cancelado"                  # quem cancela a compra no painel é gente
    if mud:
        atualizar(con, "purchase_orders", pid, **mud, updated_at=agora())
    inserir(con, "purchase_events", purchase_id=pid, kind=k, at=info["at"], mailbox=mailbox, thread_id=thread_id,
            message_id=message_id, subject=info["subject"], sender=info["sender"], order_number=info["order_number"],
            tracking=" ".join(info["tracking"]) or None, carrier=info["carrier"], amount=info["amount"],
            excerpt=info["excerpt"])
    _ligar_por_sku(con, pid)
    auditar(con, "purchase.email", "system", entity_type="purchase_order", entity_id=pid,
            detail={"tipo": k, "criada": criada, "pedido": info["order_number"], "rastreio": info["tracking"],
                    "assunto": info["subject"][:120]})
    return pid, criada


def _ligar_por_sku(con, pid):
    """Único vínculo automático com os pedidos da equipe: o SKU da peça pedida aparece no
    e-mail da loja. Nome parecido fica como SUGESTÃO na ficha — "chain" casa com muita coisa."""
    c = um(con, "SELECT status FROM purchase_orders WHERE id=?", (pid,))
    if c["status"] not in ("rascunho", "pedida", "parcial"):
        return []
    ids = [s["id"] for s in compras.pedidos_sugeridos(con, pid) if s["por_sku"]]
    if ids:
        compras.ligar_pedidos(con, pid, ids)
        auditar(con, "purchase.email.link", "system", entity_type="purchase_order", entity_id=pid,
                detail={"pedidos": ids, "por": "sku"})
    return ids


# ------------------------------------------------------------------ sincronia
def sincronizar(con, dias=None):
    """Um ciclo: busca, relê o que mudou, aplica. Nunca escreve no Gmail."""
    from command_center.providers.sync import _marca
    inicio = agora()
    if dias is None:
        dias = JANELA_DIAS if um(con, "SELECT 1 AS x FROM purchase_email_threads LIMIT 1") else PRIMEIRA_VEZ_DIAS
    try:
        threads, pagina = [], None
        while len(threads) < MAX_THREADS:
            r = chamar("gmail", "gmail_buscar", conta=CAIXA, consulta=CONSULTA.replace("{dias}", str(dias)),
                       so_inbox=False, maximo=100, pagina=pagina)
            threads.extend(r.get("threads", []))
            pagina = r.get("proxima_pagina")
            if not pagina:
                break
        criadas = atualizadas = ignoradas = 0
        for t in threads:
            visto = um(con, "SELECT messages FROM purchase_email_threads WHERE thread_id=?", (t["thread_id"],))
            if visto and visto["messages"] >= (t.get("mensagens") or 0):
                continue
            th = chamar("gmail", "gmail_thread", conta=CAIXA, thread_id=t["thread_id"])
            decisao = None
            for m in th.get("mensagens", []):
                info = ler(m)
                if not info:
                    continue
                pid, criada = aplicar(con, info, CAIXA, t["thread_id"], m.get("message_id"))
                if pid:
                    decisao = "compra"
                    criadas += criada; atualizadas += (not criada)
            if not decisao:
                ignoradas += 1
                decisao = "ignorado"
            con.execute("""INSERT INTO purchase_email_threads (thread_id, mailbox, messages, decision, seen_at)
                           VALUES (?,?,?,?,?) ON CONFLICT(thread_id) DO UPDATE SET messages=excluded.messages,
                           decision=CASE WHEN purchase_email_threads.decision='compra' THEN 'compra' ELSE excluded.decision END,
                           seen_at=excluded.seen_at""",
                        (t["thread_id"], CAIXA, len(th.get("mensagens", [])) or (t.get("mensagens") or 0), decisao, agora()))
            con.commit()
        res = {"ok": True, "conversas": len(threads), "compras_criadas": criadas, "compras_atualizadas": atualizadas,
               "ignoradas": ignoradas, "dias": dias}
        _marca(con, "gmail_compras", True, criadas + atualizadas,
               f"{criadas} compra(s) nova(s), {atualizadas} atualização(ões), {ignoradas} conversa(s) que não eram compra", inicio)
        return res
    except NaoConectado as e:
        _marca(con, "gmail_compras", False, 0, f"não conectado: {e}", inicio, desconectado=True)
        return {"ok": False, "motivo": "not connected"}
    except Exception as e:
        if type(e).__name__ == "ErroFerramenta" and "não configurada" in str(e):
            _marca(con, "gmail_compras", False, 0, "caixa urace@ sem token", inicio, desconectado=True)
            return {"ok": False, "motivo": "caixa urace@ sem token"}
        _marca(con, "gmail_compras", False, 0, f"{type(e).__name__}: {str(e)[:300]}", inicio)
        return {"ok": False, "motivo": str(e)[:300]}

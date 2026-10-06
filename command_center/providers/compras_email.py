"""E-mail de compra que chega no urace@ vira compra no painel — e cada atualização a move.

Dono, 30/09: *"faça com que todo email relacionado a compra que chegar no urace@urace se
torne um item de compra, e toda atualização de shipping / envio, confirmação de pagamento,
confirmação de delivered atualize essa tarefa; caso tenha somente a atualização do envio,
crie também automaticamente"*.

Dono, 06/10: *"chegou uma fatura daquele pedido. Ah, está pendente o pagamento. Pedido tal,
número tal […] provavelmente chegue por link, aí tem que abrir o link […] a intenção é não
ter necessidade de inserção manual"* e *"já roda uma verificação completa no e-mail"*.

Como funciona, em cada ciclo da sincronia (15 min):

1. Busca no urace@ (a caixa inteira, não só a inbox: o filtro do Gmail arquiva
   "Finances/Shopping" e "Shipping Status") as conversas com cara de compra, desde a última
   passada que deu certo (no mínimo 2 dias).
2. Relê só a conversa que ganhou mensagem nova (`purchase_email_threads`) e aplica as
   mensagens NA ORDEM EM QUE CHEGARAM, de todas as conversas juntas: o "pedido confirmado"
   vem antes do "foi enviado", mesmo quando estão em conversas diferentes.
3. Cada mensagem é classificada em **pedido · pagamento · envio · entregue · cancelado ·
   reembolso**, com a etapa fina quando o assunto diz: pagamento pendente, preparando,
   etiqueta criada, em trânsito, previsão de entrega, saiu para entrega, atraso, mensagem
   da loja. Dela sai o nº do pedido, o nº da fatura, o rastreio, a transportadora, o total,
   o valor devido, a previsão de chegada e os links de rastreio/pedido.
4. Acha a compra pelo nº do pedido (ou pela referência digitada à mão), pela fatura, pelo
   rastreio e, para a fatura que não cita o pedido, pelo mesmo fornecedor com o mesmo valor
   ao centavo. Não achou: **cria** a compra (origem e-mail).
5. Cada mensagem vira um evento na linha do tempo da compra (uma vez só: message_id único).
6. No fim do ciclo, abre a página de rastreio/pedido que veio no e-mail (`pagina.py`) das
   compras que ainda não chegaram, e o que a página diz entra na linha do tempo.

Fatura de fornecedor pelo QuickBooks ("New payment request from Courtney Concepts Karting -
invoice 1678", "Payment confirmation: Invoice #1678-(…)") é compra a pagar e entra; o resto
do QuickBooks (pagamento que NÓS recebemos, depósito, "you got paid") continua fora.

O que NÃO faz, de propósito:
- **Não dá entrada no estoque.** "Delivered" é a transportadora dizendo que deixou a caixa;
  quem abre e conta é gente. A compra entregue sem entrada aparece em "Precisa de atenção".
- **Não inventa item.** O e-mail diz que houve pedido; o que exatamente foi, com quantidade
  e custo, quem comprou confirma (ou liga os pedidos da equipe, que já têm quantidade).
- **Não confunde venda com compra.** Pedido da nossa loja, pagamento de invoice nossa,
  banco, viagem, assinatura e propaganda ficam de fora (ver `_ignorar`).
- **Não escreve no Gmail.** Só lê.
"""
import hashlib
import json
import os
import re
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from email.utils import parseaddr

from command_center.db import agora, atualizar, auditar, inserir, todos, um
from command_center.providers import NaoConectado, chamar, compras, estoque, pagina

CAIXA = "urace"
JANELA_DIAS = 2            # mínimo de cada ciclo (o ciclo é de 15 min: sobra folga)
PRIMEIRA_VEZ_DIAS = 7      # na primeira passada, uma semana para trás
MAX_JANELA_DIAS = 30       # sincronia parada há mais tempo que isso: rodar a varredura
VARREDURA_DIAS = 400       # "verificação completa": um ano e pouco de caixa
MAX_THREADS = 400
MAX_THREADS_VARREDURA = 4000
CORPO_LIMITE = 12000       # caracteres do corpo lidos por mensagem
JANELA_ACHAR_DIAS = 420    # compra mais velha que isso não recebe evento novo

CONSULTA = ("-in:sent -in:drafts -category:promotions -category:social newer_than:{dias}d "
            "{label:finances-shopping label:finances-shopping-amazon label:shipping-status label:canotops "
            "label:fornecedores-pendente label:fornecedores-recebido "
            "subject:order subject:ordered subject:shipped subject:shipping subject:shipment subject:delivered "
            "subject:delivery subject:tracking subject:\"on its way\" subject:\"on the way\" subject:receipt "
            "subject:payment subject:pedido subject:purchase subject:package subject:envio subject:entrega "
            "subject:rastreio subject:compra subject:invoice subject:fatura subject:waybill subject:\"payment request\"}")

ORDEM = {"pedido": 1, "pagamento": 2, "envio": 3, "entregue": 4}            # tipo do e-mail
STATUS = {"pedido": "pedido", "pagamento": "pago", "envio": "enviado", "entregue": "entregue"}
PESO = {"pedido": 1, "pago": 2, "enviado": 3, "entregue": 4}                 # andamento da compra

# ------------------------------------------------------------------ classificação
# A ordem importa: "Delivered: your order #123" é entrega, não pedido; "Your order is waiting
# for payment" é pagamento PENDENTE, não pedido nem pagamento.
_PENDENTE = re.compile(
    r"\b(waiting for payment|await(?:ing)? (?:\w+ )?payment|payment (?:is )?(?:due|pending|required|overdue)|is due\b|"
    r"payment request|finish your payment|ready for payment|payment link|balance due|unpaid|past due|overdue|"
    r"invoice (?:reminder|due)|pagamento pendente|aguardando pagamento|fatura)\b", re.I)
_TIPOS = [
    # "will be delivered today" / "delivered by Friday" é previsão, não entrega
    ("entregue", r"(\b(?<!be )(?<!being )delivered\b(?!\s+(by|on|tomorrow|today|between|to you))|\bfoi entregue\b|(?<!será )(?<!sera )(?<!ser )\bentregue\b(?!\s+at[eé])|"
                 r"\bdelivery complete\b)"),
    ("cancelado", r"\b(cancel+ed|cancel+ation|cancelad[oa])\b"),
    ("reembolso", r"\b(refund(ed)?|reembolso|estorno)\b"),
    ("pendente", _PENDENTE.pattern),
    ("envio", r"\b(shipped|has shipped|shipping (confirmation|update|notification)|shipment|on (its|the) way|out for delivery|"
              r"in transit|dispatched|tracking (number|info|update)|label created|arriving|will be delivered|to be delivered|scheduled (for )?delivery|delivery (today|tomorrow)|ser[aá] entregue|enviad[oa]|a caminho|saiu para entrega|rastreio)\b"),
    ("pagamento", r"\b(payment (confirmation|confirmed|received|successful|complete[d]?|processed|receipt)|payment has been (received|processed|confirmed)|"
                  r"payment to|receipt|you paid|paid|pagamento (confirmado|aprovado|recebido)|recibo|invoice paid)\b"),
    ("pedido", r"\b(order (confirmation|confirmed|received|placed|summary|details)|your order|thanks? (you )?for your (order|purchase)|"
               r"purchase (confirmation|order)|ordered|order #|pedido (confirmado|recebido|realizado|feito)|compra (confirmada|realizada))\b"),
]
_TIPOS = [(k, re.compile(p, re.I)) for k, p in _TIPOS]

_ESTAGIO_ENVIO = [
    ("saiu_para_entrega", re.compile(r"\b(out for delivery|saiu para entrega)\b", re.I)),
    ("atraso", re.compile(r"\b(delay(ed)?|exception|delivery attempt(ed)?|unable to deliver|missed delivery|held at|on hold|atrasad[oa])\b", re.I)),
    ("previsao", re.compile(r"\b(scheduled (for )?delivery|arriving|delivery (today|tomorrow)|will be delivered|to be delivered|"
                            r"estimated delivery|ser[aá] entregue)\b", re.I)),
    ("etiqueta", re.compile(r"\b(label created|shipping label|label (has been )?printed)\b", re.I)),
]
_PREPARANDO = re.compile(r"\b(final stages|processing|being prepared|preparing|ready to ship|em separa[cç][aã]o)\b", re.I)

# Venda nossa, cobrança de cliente, banco, viagem, assinatura e propaganda: não é compra.
_NAO_E_COMPRA = re.compile(
    r"(placed by|new order|you'?ve got a new order|you have a new order|nova venda|new sale|"
    r"received a payment|payment received from|you received|you've received|payout|you got paid|paid you|money on the way|"
    r"invoice from urace|from urace\.?us|subscription|renewal|your plan|free trial|membership|"
    r"zelle|recurring payment|autopay|auto-pay|line of credit|vehicle payment|statement is (ready|available)|"
    r"itinerary|reservation|boarding pass|\bflight\b|check-in|\bhotel\b|\buber\b|\blyft\b|"
    r"championship|registration|entry fee|"
    r"\d+\s?% off|sale ends|deal of|coupon|promo code|webinar|newsletter)", re.I)
_REMETENTES_FORA = ("urace.us", "intuit.com", "quickbooks", "docusign", "kommo", "simplybook", "asana.com",
                    "dialpad", "google.com", "anthropic.com")
# 06/10 — o que a primeira semana no ar mostrou que entrava sem ser compra (banco, viagem, SaaS)
_DOMINIOS_FORA = ("bankofamerica.com", "ally.com", "chase.com", "peach.finance", "americanexpress.com", "aexp.com",
                  "capitalone.com", "wellsfargo.com", "discover.com", "hotels.com", "expedia.com", "booking.com",
                  "airbnb.com", "copaair.com", "aa.com", "delta.com", "united.com", "jetblue.com", "southwest.com",
                  "spirit.com", "flyfrontier.com", "uber.com", "lyft.com", "openai.com", "heroku.com")
_MARCADORES_FORA = ("URace Store/", "Customer Service/", "CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "SENT", "DRAFT", "SPAM", "TRASH")

# Dono, 30/09: recibo do Orlando Kart Center (passe de pista) NÃO vira compra.
_LOJAS_FORA = ("orlandokartcenter", "orlando kart center")

# Fatura de fornecedor que chega pelo QuickBooks dele (conta a PAGAR — urace-gmail, 28/08)
_QB_PEDE = re.compile(r"payment request from\s+(.+?)\s*-\s*invoice\s*#?\s*([A-Z0-9][\w-]*)?\s*$", re.I)
_QB_DEVE = re.compile(r"(?:your payment to|finish your payment to)\s+(.+?)(?:\s+is due\b.*)?\s*$", re.I)
_QB_PAGO = re.compile(r"payment confirmation:\s*invoice\s*#?\s*([\w-]+?)-\((.+)\)\s*$", re.I)


def _email_de(msg):
    return parseaddr(msg.get("de") or "")[1].lower()


def _dominio(email):
    return (email.split("@")[-1] or "").lower()


def _do_quickbooks(msg):
    e = _email_de(msg)
    return "intuit.com" in _dominio(e) or "quickbooks" in e


def conta_a_pagar(msg):
    """Fatura de fornecedor pelo QuickBooks: {supplier, invoice_number, kind, stage} ou None."""
    if not _do_quickbooks(msg):
        return None
    a = re.sub(r"\s+", " ", msg.get("assunto") or "").strip()
    m = _QB_PAGO.search(a)
    if m:
        return {"supplier": m.group(2).strip(), "invoice_number": m.group(1), "kind": "pagamento", "stage": None}
    m = _QB_PEDE.search(a)
    if m:
        return {"supplier": m.group(1).strip(), "invoice_number": m.group(2), "kind": "pedido", "stage": "pagamento_pendente"}
    m = _QB_DEVE.search(a)
    if m:
        return {"supplier": m.group(1).strip(), "invoice_number": None, "kind": "pedido", "stage": "pagamento_pendente"}
    return None


def _ignorar(msg, conta=None):
    """Motivo para não ser compra, ou None."""
    de = (msg.get("de") or "").lower()
    email = _email_de(msg)
    marcas = " ".join(str(m).lower() for m in (msg.get("marcadores") or []))
    assunto = (msg.get("assunto") or "").lower()
    if any(x in de or x in email.replace(".", "").replace("-", "") or x in marcas or x in assunto.replace("-", " ")
           for x in _LOJAS_FORA):
        return "Orlando Kart Center (dono: passe de pista não é compra)"
    dom = _dominio(email)
    if any(dom == d or dom.endswith("." + d) for d in _DOMINIOS_FORA):
        return "banco, viagem ou assinatura"
    if not conta and any(email.endswith(d) or d in dom for d in _REMETENTES_FORA):
        return "remetente fora (nosso ou de sistema)"
    marc = msg.get("marcadores") or []
    if any(str(m).startswith(p) or str(m) == p for m in marc for p in _MARCADORES_FORA):
        return "marcador fora (venda nossa, atendimento ou propaganda)"
    if _NAO_E_COMPRA.search(msg.get("assunto") or "") or "urace store" in de:
        return "assunto de venda, banco, viagem, assinatura ou propaganda"
    return None


def tipo(assunto, tem_rastreio=False, tem_pedido=False):
    """Pelo ASSUNTO. O corpo de e-mail de loja fala de tudo ("cancel anytime", "track your
    package", "delivered"), então quando o assunto não diz, só o que é concreto decide:
    tem rastreio → envio; tem nº de pedido → pedido; nada disso → não é compra.
    "pendente" é pedido com a etapa pagamento_pendente (`estagio`)."""
    for k, rx in _TIPOS:
        if rx.search(assunto or ""):
            return ("pedido" if k == "pendente" else k), "assunto"
    if tem_rastreio:
        return "envio", "corpo"
    if tem_pedido:
        return "pedido", "corpo"
    return None, None


def estagio(kind, assunto, de=""):
    """A etapa fina, quando o assunto diz. None = só o tipo."""
    a = assunto or ""
    if kind == "pedido":
        if _PENDENTE.search(a):
            return "pagamento_pendente"
        if re.match(r"\s*(re|res|fwd?|enc)\s*:", a, re.I) and not re.search(r"no-?reply|do-?not-?reply|notification|mailer", de or "", re.I):
            return "mensagem"
        if _PREPARANDO.search(a):
            return "preparando"
        return None
    if kind == "envio":
        for nome, rx in _ESTAGIO_ENVIO:
            if rx.search(a):
                return nome
        return "em_transito"
    return None


# ------------------------------------------------------------------ extração
_AMAZON = re.compile(r"\b\d{3}-\d{7}-\d{7}\b")
_NUM_PEDIDO = re.compile(r"(?<![a-z])(?:order|pedido|purchase order|p\.o\.)\s*(?:number|no\.?|nº|n°|num\.?|id)?\s*[:#(]?\s*\(?\s*#?\s*"
                         r"([A-Z0-9][A-Z0-9-]{2,24})", re.I)
_NUM_ENTRE_PARENTESES = re.compile(r"\((\d{10,20})\)")          # Alibaba: "Your order is on its way (316625486001022128)"
_NUM_FATURA = re.compile(r"(?<![a-z])invoice\s*(?:number|no\.?|#)?\s*:?\s*#?\s*([A-Z]{0,5}-?\d[A-Z0-9-]*?)(?=-\(|[\s,.;:)!]|$)", re.I)
_UPS = re.compile(r"\b1Z[0-9A-Z]{16}\b")
_TBA = re.compile(r"\bTBA\d{12}\b")
_USPS = re.compile(r"\b(9[2-5]\d{18,20})\b")
_FEDEX = re.compile(r"\b(\d{12}|\d{15})\b")
_RASTREIO = re.compile(r"(?:tracking|rastreio|rastreamento|waybill|air waybill|awb)\s*(?:number|no\.?|#|id|code|c[oó]digo)?\s*[:#]?\s*([A-Z0-9]{8,34})\b", re.I)
_TOTAL = re.compile(r"(?:order total|grand total|total charged|amount paid|payment amount|amount charged|balance due|amount due|"
                    r"invoice amount|you paid|total pago|total)"
                    r"\s*(?:\(usd\))?\s*[:\-]?\s*(?:USD\s?\$?|US\$|\$)\s?([\d,]+(?:\.\d{2})?)", re.I)
_MESES = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_PREVISAO = re.compile(r"(?:arriving|arrives|estimated delivery|expected delivery|delivery date|delivered by|scheduled delivery|"
                       r"entrega prevista|previs[aã]o de entrega)\s*(?:date)?\s*[:\-]?\s*(?:on\s+|by\s+)?(?:(?:[a-z]+day|mon|tues?|wed|thu|thurs?|fri|sat|sun)\.?,?\s+)?"
                       r"(?:(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:,?\s+(\d{4}))?"
                       r"|(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?)", re.I)
_CITACAO = re.compile(r"[\"“]([^\"”]{3,160})[\"”]")
# remetente da caixa num e-mail de transportadora: "Your shipment from WalMart.com is on the way",
# "Your package was delivered. From KART SPORT Delivered Thursday"
_DE_QUEM = re.compile(r"(?:shipment|package|parcel|order)s? from\s+([A-Z0-9][\w&.,'’ -]{1,60}?)(?=\s+(?:is|has|was|will|are)\b|\s*\n|\s*$)"
                      r"|\bFrom\s+([A-Z][A-Z0-9&.' -]{2,40}?)\s+(?:Delivered|Scheduled|Estimated|Arriving|Shipped|Ship|Track)\b")
_CSS = re.compile(r"\d+(px|em|pt|rem|%)", re.I)


def _tem_digito(s):
    return any(c.isdigit() for c in s or "")


def numero_do_pedido(texto):
    m = _AMAZON.search(texto or "")
    if m:
        return m.group(0)
    for m in _NUM_PEDIDO.finditer(texto or ""):
        n = m.group(1).strip("-")
        if _tem_digito(n) and not re.fullmatch(r"\d{1,2}", n) and not _CSS.fullmatch(n):
            return n
    m = _NUM_ENTRE_PARENTESES.search((texto or "").split("\n", 1)[0])
    return m.group(1) if m else None


def numero_da_fatura(texto):
    for m in _NUM_FATURA.finditer(texto or ""):
        n = m.group(1).strip("-")
        if _tem_digito(n) and not _CSS.fullmatch(n):
            return n
    return None


def rastreios(texto, de=""):
    """[(número, transportadora)] — sem repetir."""
    t = texto or ""
    achados = []
    for m in _UPS.finditer(t):
        achados.append((m.group(0), "UPS"))
    for m in _TBA.finditer(t):
        achados.append((m.group(0), "Amazon"))
    if re.search(r"\busps\b", t, re.I):
        achados += [(m.group(1), "USPS") for m in _USPS.finditer(t)]
    if "fedex" in (de or "").lower():
        # FedEx põe o número no assunto ("Your shipment is on the way 538060779646")
        achados += [(m.group(1), "FedEx") for m in _FEDEX.finditer(t.split("\n", 1)[0])]
    for m in _RASTREIO.finditer(t):
        n = m.group(1)
        if _tem_digito(n) and len(re.sub(r"\D", "", n)) >= 6:
            achados.append((n, transportadora(n, t + " " + (de or ""))))
    vistos, saida = set(), []
    for n, c in achados:
        if n.upper() not in vistos:
            vistos.add(n.upper()); saida.append((n, c))
    return saida


# parâmetros de URL que carregam o código de rastreio (UPS, FedEx, USPS, DHL, ShipStation, 17track…)
_PARAMS_RASTREIO = ("tracking_number", "trackingnumber", "tracking_numbers", "tracknum", "tracknums", "trknbr",
                    "tracknumbers", "tlabels", "qtc_tlabels1", "tracking-id", "trackingid", "inquirynumber1", "nums", "awb")
_HOST_TRANSP = {"ups.com": "UPS", "fedex.com": "FedEx", "usps.com": "USPS", "dhl.com": "DHL", "ontrac.com": "OnTrac"}


def rastreios_do_link(url):
    """[(número, transportadora)] tirados da própria URL de rastreio — sem abrir a página."""
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return []
    q = {k.lower(): v for k, v in urllib.parse.parse_qs(u.query).items()}
    q.update({k.lower(): v for k, v in urllib.parse.parse_qs(u.fragment).items()})
    host = (u.hostname or "").lower()
    transp = next((n for h, n in _HOST_TRANSP.items() if host == h or host.endswith("." + h)), None)
    cc = (q.get("carrier_code") or q.get("carrier") or [""])[0].lower()
    transp = transp or next((n for h, n in _HOST_TRANSP.items() if cc.startswith(h.split(".")[0])), None)
    saida = []
    for chave in _PARAMS_RASTREIO:
        for v in q.get(chave, []):
            for n in re.split(r"[,\s]+", v):
                n = n.strip().upper()
                if 8 <= len(n) <= 34 and re.fullmatch(r"[A-Z0-9]+", n) and _tem_digito(n):
                    saida.append((n, transp or transportadora(n)))
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
               "paypal": None, "shopify": None, "shop": None, "shipstation": None, "vantagekarting": "KartSport North America",
               "kartsportnorthamerica": "KartSport North America", "kartsportna": "KartSport North America"}
_TRANSPORTADORAS = {"ups": "UPS", "fedex": "FedEx", "usps": "USPS", "dhl": "DHL", "ontrac": "OnTrac"}
# o mesmo fornecedor com nomes diferentes em cada sistema (loja, armazém, transportadora)
_APELIDOS = [(re.compile(r"kart\s?sport|vantage karting", re.I), "KartSport North America"),
             (re.compile(r"comet kart", re.I), "Comet Kart Sales"),
             (re.compile(r"wal-?mart", re.I), "Walmart"),
             (re.compile(r"^amazon", re.I), "Amazon")]


def canonico(nome):
    """Nome único do fornecedor ("KART SPORT", "Vantage Karting Group" → "KartSport North America")."""
    n = (nome or "").strip()
    for rx, certo in _APELIDOS:
        if rx.search(n):
            return certo
    return n


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
        return (canonico(m.group(1).strip()) if m else "PayPal"), None
    limpo = re.sub(r"\s+", " ", _GENERICOS.sub(" ", (nome or "").replace('"', ""))).strip(" -|·@")
    if len(limpo) >= 3:
        return canonico(limpo[:60]), None
    return (base.capitalize() if base else "Fornecedor não identificado"), None


def quem_mandou(texto):
    """Quem despachou, quando o e-mail é da transportadora ("shipment from WalMart.com")."""
    m = _DE_QUEM.search(texto or "")
    if not m:
        return None
    n = (m.group(1) or m.group(2) or "").strip(" .,")
    return canonico(n) if len(n) >= 3 else None


def _norm(s):
    return estoque._norm(s).upper()


# links que valem guardar: rastreio primeiro, depois a página do pedido
_HOSTS_RASTREIO = ("ups.com", "fedex.com", "usps.com", "dhl.com", "ontrac.com", "trackshipment.shipstation.com", "17track.net",
                   "aftership.com", "parcelpanel", "narvar.com", "route.com", "track.", "tracking.")
# precisam de login: o link é guardado, mas a página não é aberta
_NAO_ABRE = ("amazon.", "ebay.", "alibaba.", "walmart.", "etsy.")


def _melhor_link(links):
    """O link para guardar (rastreio > pedido > outro útil)."""
    uteis = [lk for lk in links or [] if pagina.util(lk.get("url", ""), lk.get("texto", ""))]
    for lk in uteis:                                       # o link que carrega o próprio código
        if rastreios_do_link(lk["url"]):
            return lk["url"]
    for lk in uteis:
        host = (urllib.parse.urlsplit(lk["url"]).hostname or "").lower()
        if any(h in host for h in _HOSTS_RASTREIO) and re.search(r"track", lk["url"] + " " + lk.get("texto", ""), re.I):
            return lk["url"]
    for lk in uteis:
        if re.search(r"order|pedido|invoice|logistic", lk["url"] + " " + lk.get("texto", ""), re.I):
            return lk["url"]
    return uteis[0]["url"] if uteis else None


def ler(msg):
    """O que uma mensagem diz, sem tocar no banco. None quando não é compra."""
    assunto = msg.get("assunto") or ""
    corpo = msg.get("corpo") or ""
    snippet = msg.get("snippet") or ""
    texto = f"{assunto}\n{snippet}\n{corpo}"
    de = msg.get("de") or ""
    conta = conta_a_pagar(msg)
    if _ignorar(msg, conta):
        return None
    if _do_quickbooks(msg) and not conta:
        return None
    links = msg.get("links") or []
    track = rastreios(texto, de)
    for lk in links:
        track += [x for x in rastreios_do_link(lk.get("url", "")) if x[0].upper() not in {t.upper() for t, _ in track}]
    pedido = None if conta else numero_do_pedido(texto)
    ref_armazem = None
    if "shipstation" in _dominio(_email_de(msg)):
        # "your order (#SO-88050, #1)" é o nº do ARMAZÉM (ShipStation da KartSport), não o da loja
        # (#47843): vira referência, para a compra da loja absorver este aviso pelo rastreio.
        ref_armazem, pedido = pedido, None
    fatura = (conta or {}).get("invoice_number") or numero_da_fatura(assunto) or (numero_da_fatura(texto) if conta else None)
    if conta:
        k, stage = conta["kind"], conta["stage"]
    else:
        k, _onde = tipo(assunto, bool(track), bool(pedido or fatura))
        if not k:
            return None
        stage = estagio(k, assunto, de)
    forn, transp = fornecedor(de, texto)
    if conta:
        forn = canonico(conta["supplier"])
    hint = quem_mandou(texto) if transp or "shipstation" in de.lower() else None
    em = _data(msg.get("data"))
    citado = _CITACAO.search(assunto)
    valor = total(f"{snippet}\n{corpo}")
    return {"kind": k, "stage": stage, "order_number": pedido, "invoice_number": fatura, "ship_ref": ref_armazem,
            "tracking": [t for t, _ in track],
            "carrier": transp or next((c for _, c in track if c), None), "supplier": forn, "supplier_hint": hint,
            "amount": valor, "expected_at": previsao(texto, _dia(em)),
            "items_hint": citado.group(1).strip() if citado else None,
            "url": _melhor_link(links),
            "at": em, "subject": assunto[:300], "sender": de[:200],
            "excerpt": re.sub(r"\s+", " ", f"{snippet} {corpo}")[:1500]}


def _data(rfc):
    from command_center.providers.sync import _data_rfc
    return _data_rfc(rfc) if rfc else agora()


def _dia(iso):
    try:
        return date.fromisoformat((iso or "")[:10])
    except ValueError:
        return None


# ------------------------------------------------------------------ ligar à compra
def _abertas(con):
    return todos(con, """SELECT id, supplier, order_number, reference, tracking, invoice_number, email_total, amount_due,
                                status, created_at
                           FROM purchase_orders WHERE created_at >= ? AND status != 'cancelada' ORDER BY id DESC LIMIT 3000""",
                 ((datetime.now(timezone.utc) - timedelta(days=JANELA_ACHAR_DIAS)).strftime("%Y-%m-%d"),))


def _rastreios_da(c):
    return {_norm(x) for x in (c["tracking"] or "").split()} | {_norm(c["reference"])} - {""}


def achar_compras(con, info):
    """Ids das compras desta mensagem, a principal primeiro.

    1. nº do pedido (ou referência digitada); 2. nº da fatura; 3. rastreio — que pode ser de
    mais de uma compra (duas encomendas na mesma caixa); 4. fatura sem nº de pedido: mesmo
    fornecedor, mesmo valor ao centavo, compra sem fatura ainda."""
    abertas = _abertas(con)
    if info.get("order_number"):
        alvo = _norm(info["order_number"])
        for c in abertas:
            if alvo and alvo in {_norm(c["order_number"]), _norm(c["reference"])}:
                return [c["id"]]
    if info.get("invoice_number"):
        alvo = _norm(info["invoice_number"])
        for c in abertas:
            if alvo and alvo == _norm(c["invoice_number"]):
                return [c["id"]]
    if info.get("ship_ref"):
        alvo = _norm(info["ship_ref"])
        for c in abertas:
            if alvo and alvo == _norm(c["reference"]):
                return [c["id"]]
    achadas = []
    for t in info.get("tracking") or []:
        alvo = _norm(t)
        for c in abertas:
            if alvo in _rastreios_da(c) and c["id"] not in achadas:
                # rastreio de outra compra com OUTRO nº de pedido: é a mesma caixa, não o mesmo pedido
                if info.get("order_number") and c["order_number"] and _norm(c["order_number"]) != _norm(info["order_number"]):
                    continue
                achadas.append(c["id"])
    if achadas:
        return achadas
    if info.get("invoice_number") and info.get("amount") is not None and info.get("supplier"):
        forn = canonico(info["supplier"])
        for c in abertas:
            if (not c["invoice_number"] and canonico(c["supplier"]) == forn and c["email_total"] is not None
                    and abs(c["email_total"] - info["amount"]) < 0.005):
                return [c["id"]]
    return []


def achar_compra(con, info):
    ids = achar_compras(con, info)
    return ids[0] if ids else None


def _mesmo_fornecedor(a, b):
    a, b = canonico(a or ""), canonico(b or "")
    return a == b or a.startswith("Não identificado") or b.startswith("Não identificado")


def aplicar(con, info, mailbox, thread_id, message_id, pid=None):
    """Grava a mensagem na compra certa (criando, se preciso). Devolve (purchase_id, criada)."""
    if message_id and um(con, "SELECT 1 AS x FROM purchase_events WHERE message_id=?", (message_id,)):
        return None, False
    irmas = []
    if not pid:
        ids = achar_compras(con, info)
        pid, irmas = (ids[0], ids[1:]) if ids else (None, [])
    if not pid and thread_id:
        # pela conversa: a mesma thread é a mesma compra — menos quando os números dizem que
        # não (o Gmail junta "Order confirmation" de pedidos diferentes da mesma loja)
        ja = um(con, """SELECT e.purchase_id, o.order_number, o.supplier FROM purchase_events e JOIN purchase_orders o ON o.id=e.purchase_id
                         WHERE e.thread_id=? AND o.status != 'cancelada' ORDER BY e.id DESC LIMIT 1""", (thread_id,))
        if ja and not (info["order_number"] and ja["order_number"] and _norm(ja["order_number"]) != _norm(info["order_number"])) \
                and _mesmo_fornecedor(ja["supplier"], info["supplier"] or info.get("supplier_hint")):
            pid = ja["purchase_id"]
    criada = False
    if not pid:
        forn = info["supplier"] or info.get("supplier_hint") or (
            f"Não identificado (envio {info['carrier']})" if info["carrier"] else "Não identificado")
        ref = info["order_number"] or info.get("invoice_number") or info.get("ship_ref")
        pid = inserir(con, "purchase_orders", supplier=forn[:80], status="pedida", source="email",
                      order_number=info["order_number"], reference=ref,
                      ordered_at=info["at"], items_hint=info["items_hint"],
                      notes=f"Criada pelo e-mail “{info['subject'][:120]}”.")
        criada = True
    _atualizar_compra(con, pid, info)
    for outra in irmas:                                    # a mesma caixa leva mais de um pedido
        _atualizar_compra(con, outra, info, so_envio=True)
    inserir(con, "purchase_events", purchase_id=pid, kind=info["kind"], stage=info.get("stage"), at=info["at"], mailbox=mailbox,
            thread_id=thread_id, message_id=message_id, subject=info["subject"], sender=info["sender"],
            order_number=info["order_number"], invoice_number=info.get("invoice_number"),
            tracking=" ".join(info["tracking"]) or None, carrier=info["carrier"], amount=info["amount"],
            url=info.get("url"), excerpt=info["excerpt"])
    if info["order_number"] and info["tracking"]:
        _juntar_orfas(con, pid, info)
    _ligar_por_sku(con, pid)
    auditar(con, "purchase.email", "system", entity_type="purchase_order", entity_id=pid,
            detail={"tipo": info["kind"], "etapa": info.get("stage"), "criada": criada, "pedido": info["order_number"],
                    "fatura": info.get("invoice_number"), "rastreio": info["tracking"], "assunto": info["subject"][:120],
                    **({"mesma_caixa": irmas} if irmas else {})})
    return pid, criada


def _atualizar_compra(con, pid, info, so_envio=False):
    c = um(con, "SELECT * FROM purchase_orders WHERE id=?", (pid,))
    mud = {}
    k, stage = info["kind"], info.get("stage")
    if not so_envio:
        if info["order_number"] and not c["order_number"]:
            mud["order_number"] = info["order_number"]
            if not c["reference"] or c["reference"] == c["invoice_number"]:
                mud["reference"] = info["order_number"]
        if info.get("invoice_number") and not c["invoice_number"]:
            mud["invoice_number"] = info["invoice_number"]
            if not c["reference"] and not mud.get("reference"):
                mud["reference"] = info["invoice_number"]
        if info["items_hint"] and not c["items_hint"]:
            mud["items_hint"] = info["items_hint"][:200]
        if info["amount"] is not None and k in ("pedido", "pagamento") and c["email_total"] is None and stage != "pagamento_pendente":
            mud["email_total"] = info["amount"]
        sup = info["supplier"] or info.get("supplier_hint")
        if c["supplier"].startswith("Não identificado") and sup:
            mud["supplier"] = sup[:80]
        if info.get("url") and not c["order_url"]:
            mud["order_url"] = info["url"][:1500]
        if stage == "pagamento_pendente":
            mud["payment_status"] = "pendente"
            if info["amount"] is not None:
                mud["amount_due"] = info["amount"]
        elif k == "pagamento":
            mud["payment_status"] = "pago"
            mud["amount_due"] = None if c["amount_due"] is None else 0
    if info["tracking"]:
        atuais = (c["tracking"] or "").split()
        novos = [t for t in info["tracking"] if _norm(t) not in {_norm(x) for x in atuais}]
        if novos and not so_envio:
            mud["tracking"] = " ".join(atuais + novos)[:400]
    if info["carrier"] and not c["carrier"]:
        mud["carrier"] = info["carrier"]
    if info["expected_at"] and k in ("pedido", "pagamento", "envio"):
        mud["expected_at"] = info["expected_at"]
    if stage == "mensagem" or stage == "pagamento_pendente":
        pass                                              # conversa da loja e fatura não mudam a entrega
    elif k in ORDEM and not (so_envio and k in ("pedido", "pagamento")):
        if ORDEM[k] > PESO.get(c["ship_status"] or "", 0) and c["ship_status"] != "cancelado":
            mud["ship_status"] = STATUS[k]
        campo = {"pagamento": "paid_at", "envio": "shipped_at", "entregue": "delivered_at"}.get(k)
        if campo and not c[campo]:
            mud[campo] = info["at"]
    elif k == "cancelado" and c["ship_status"] != "entregue" and not so_envio:
        mud["ship_status"] = "cancelado"                  # quem cancela a compra no painel é gente
    if c["status"] == "rascunho" and k in ORDEM and not so_envio:   # a loja confirmou: foi pedida
        mud["status"] = "pedida"
        mud["ordered_at"] = c["ordered_at"] or info["at"]
    if mud:
        atualizar(con, "purchase_orders", pid, **mud, updated_at=agora())


def _juntar_orfas(con, pid, info):
    """O e-mail da loja trouxe nº do pedido E rastreio: a compra que nasceu só do aviso da
    transportadora (ou do armazém, sem o nº da loja) com esse rastreio é esta mesma compra.
    Os eventos dela passam para cá e a casca vazia sai — só se ninguém mexeu nela."""
    c = um(con, "SELECT * FROM purchase_orders WHERE id=?", (pid,))
    alvos = {_norm(t) for t in info["tracking"]}
    for o in todos(con, """SELECT * FROM purchase_orders WHERE id != ? AND source='email' AND order_number IS NULL
                            AND status IN ('pedida','rascunho') AND tracking IS NOT NULL""", (pid,)):
        if not (alvos & {_norm(x) for x in (o["tracking"] or "").split()}):
            continue
        if not _mesmo_fornecedor(o["supplier"], c["supplier"]) or _mexida_por_gente(con, o["id"]):
            continue
        con.execute("UPDATE purchase_events SET purchase_id=? WHERE purchase_id=?", (pid, o["id"]))
        mud = {}
        for campo in ("paid_at", "shipped_at", "delivered_at", "expected_at", "carrier", "order_url", "asana_gid"):
            if o[campo] and not c[campo]:
                mud[campo] = o[campo]
        if PESO.get(o["ship_status"] or "", 0) > PESO.get(c["ship_status"] or "", 0) and c["ship_status"] != "cancelado":
            mud["ship_status"] = o["ship_status"]
        juntos = (c["tracking"] or "").split() + [t for t in (o["tracking"] or "").split()
                                                  if _norm(t) not in {_norm(x) for x in (c["tracking"] or "").split()}]
        mud["tracking"] = " ".join(juntos)[:400]
        if o["reference"] and not c["reference"]:
            mud["reference"] = o["reference"]
        atualizar(con, "purchase_orders", pid, **mud, updated_at=agora())
        c = um(con, "SELECT * FROM purchase_orders WHERE id=?", (pid,))
        con.execute("DELETE FROM purchase_pages WHERE purchase_id=?", (o["id"],))
        con.execute("DELETE FROM purchase_orders WHERE id=?", (o["id"],))
        auditar(con, "purchase.email.merge", "system", entity_type="purchase_order", entity_id=pid,
                detail={"juntou": o["id"], "rastreio": sorted(alvos), "fornecedor": o["supplier"]})


def _mexida_por_gente(con, pid):
    """Alguém da equipe já mexeu nesta compra (itens, pedidos ligados, receber, cancelar)?"""
    if um(con, "SELECT 1 AS x FROM purchase_lines WHERE purchase_id=? LIMIT 1", (pid,)):
        return True
    if um(con, "SELECT 1 AS x FROM purchase_requests WHERE purchase_id=? LIMIT 1", (pid,)):
        return True
    return bool(um(con, """SELECT 1 AS x FROM audit_logs WHERE entity_type='purchase_order' AND entity_id=?
                            AND actor LIKE 'user:%' LIMIT 1""", (str(pid),)))


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


# ------------------------------------------------------------------ página do link
PAGINA_POR_CICLO = 15
PAGINA_DE_NOVO_HORAS = 6
_SITUACOES = [   # o que a página de rastreio diz, do mais forte para o mais fraco
    ("entregue", None, re.compile(r"(^|\n)\s*delivered\b|\b(has been|was) delivered\b|\bdelivered on\b|\bentregue\b", re.I)),
    ("envio", "saiu_para_entrega", re.compile(r"\bout for delivery\b|\bsaiu para entrega\b", re.I)),
    ("envio", "atraso", re.compile(r"\b(delivery exception|delayed|exception|delivery attempted|unable to deliver)\b", re.I)),
    ("envio", "em_transito", re.compile(r"\b(in transit|on the way|on its way|departed|arrived at|picked up|em tr[aâ]nsito)\b", re.I)),
    ("envio", "etiqueta", re.compile(r"\b(label created|shipping label created|order processed: ready for)\b", re.I)),
]


def situacao_da_pagina(texto):
    for kind, stage, rx in _SITUACOES:
        if rx.search(texto or ""):
            return kind, stage
    return None, None


def rever_paginas(con, limite=PAGINA_POR_CICLO):
    """Abre o link de rastreio/pedido das compras que ainda não chegaram e põe na linha do
    tempo o que a página diz. Uma página por compra, no máximo a cada 6 h."""
    corte = (datetime.now(timezone.utc) - timedelta(hours=PAGINA_DE_NOVO_HORAS)).strftime("%Y-%m-%dT%H:%M:%S")
    desde = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%d")
    cand = todos(con, """SELECT e.url, e.purchase_id, MAX(e.id) AS ult FROM purchase_events e
                           JOIN purchase_orders o ON o.id=e.purchase_id
                          WHERE e.url IS NOT NULL AND e.url NOT LIKE 'pagina:%' AND o.status IN ('pedida','parcial','rascunho')
                            AND COALESCE(o.ship_status,'') NOT IN ('entregue','cancelado') AND o.created_at >= ?
                          GROUP BY e.url, e.purchase_id ORDER BY ult DESC LIMIT 200""", (desde,))
    lidas = mudou = 0
    for c in cand:
        if lidas >= limite:
            break
        url = c["url"]
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        if any(h in host for h in _NAO_ABRE):
            continue
        h = hashlib.sha1(url.encode()).hexdigest()
        ja = um(con, "SELECT fetched_at FROM purchase_pages WHERE url_hash=?", (h,))
        if ja and ja["fetched_at"] > corte:
            continue
        lidas += 1
        try:
            p = pagina.abrir(url)
            erro = None
        except pagina.ErroPagina as e:
            p, erro = None, str(e)[:300]
        res = None
        if p:
            kind, stage = situacao_da_pagina(p["texto"])
            track = rastreios(p["texto"]) + rastreios_do_link(p["url"])
            res = {"kind": kind, "stage": stage, "tracking": [t for t, _ in track],
                   "carrier": next((x for _, x in track if x), None), "expected_at": previsao(p["texto"])}
            if kind or res["tracking"]:
                info = {"kind": kind or "envio", "stage": stage or ("em_transito" if not kind else None), "order_number": None,
                        "invoice_number": None, "ship_ref": None, "tracking": res["tracking"], "carrier": res["carrier"], "supplier": None,
                        "supplier_hint": None, "amount": None, "expected_at": res["expected_at"], "items_hint": None,
                        "url": url, "at": agora(), "subject": f"Página de rastreio: {_ROTULO.get(stage or kind, kind or 'rastreio')}",
                        "sender": host[:200], "excerpt": p["texto"][:1500]}
                chave = f"pagina:{h[:16]}:{info['kind']}:{info['stage'] or ''}:{','.join(sorted(res['tracking']))}"
                pid, _ = aplicar(con, info, "web", None, chave, pid=c["purchase_id"])
                mudou += bool(pid)
        con.execute("""INSERT INTO purchase_pages (url_hash, url, purchase_id, fetched_at, ok, result, error) VALUES (?,?,?,?,?,?,?)
                       ON CONFLICT(url_hash) DO UPDATE SET fetched_at=excluded.fetched_at, ok=excluded.ok,
                       result=excluded.result, error=excluded.error""",
                    (h, url[:1500], c["purchase_id"], agora(), 1 if p else 0, json.dumps(res) if res else None, erro))
        con.commit()
    return {"paginas_lidas": lidas, "paginas_com_novidade": mudou}


_ROTULO = {"entregue": "entregue", "saiu_para_entrega": "saiu para entrega", "atraso": "atraso", "em_transito": "em trânsito",
           "etiqueta": "etiqueta criada", "envio": "em trânsito"}


# ------------------------------------------------------------------ sincronia
def _dias_desde_ultima(con):
    """Janela do ciclo: desde a última passada que deu certo (2 dias no mínimo)."""
    if not um(con, "SELECT 1 AS x FROM purchase_email_threads LIMIT 1"):
        return PRIMEIRA_VEZ_DIAS
    u = um(con, "SELECT MAX(finished_at) AS f FROM sync_logs WHERE system='gmail_compras' AND ok=1")
    if not u or not u["f"]:
        return JANELA_DIAS
    try:
        ult = datetime.fromisoformat(u["f"].replace("Z", "+00:00"))
    except ValueError:
        return JANELA_DIAS
    dias = (datetime.now(timezone.utc) - ult).days + 2
    return max(JANELA_DIAS, min(dias, MAX_JANELA_DIAS))


def sincronizar(con, dias=None, forcar=False, abrir_paginas=True):
    """Um ciclo: busca, relê o que mudou, aplica em ordem de chegada, abre os links. Nunca
    escreve no Gmail. `forcar` relê toda conversa achada (a varredura completa)."""
    from command_center.providers.sync import _marca
    inicio = agora()
    if dias is None:
        dias = _dias_desde_ultima(con)
    teto = MAX_THREADS_VARREDURA if forcar or dias > MAX_JANELA_DIAS else MAX_THREADS
    try:
        threads, pagina_tok = [], None
        while len(threads) < teto:
            r = chamar("gmail", "gmail_buscar", conta=CAIXA, consulta=CONSULTA.replace("{dias}", str(dias)),
                       so_inbox=False, maximo=100, pagina=pagina_tok)
            threads.extend(r.get("threads", []))
            pagina_tok = r.get("proxima_pagina")
            if not pagina_tok:
                break
        lidas, fila = [], []
        for t in threads:
            visto = um(con, "SELECT messages FROM purchase_email_threads WHERE thread_id=?", (t["thread_id"],))
            if visto and visto["messages"] >= (t.get("mensagens") or 0) and not forcar:
                continue
            th = _thread(t["thread_id"])
            lidas.append((t, th))
            for m in th.get("mensagens", []):
                fila.append((_data(m.get("data")) or "", t["thread_id"], m))
        fila.sort(key=lambda x: x[0])                      # a ordem em que os e-mails chegaram
        criadas = atualizadas = 0
        compra_por_thread = set()
        for _quando, tid, m in fila:
            info = ler(m)
            if not info:
                continue
            pid, criada = aplicar(con, info, CAIXA, tid, m.get("message_id"))
            if pid:
                compra_por_thread.add(tid)
                criadas += criada; atualizadas += (not criada)
            elif um(con, "SELECT 1 AS x FROM purchase_events WHERE message_id=?", (m.get("message_id"),)):
                compra_por_thread.add(tid)
        ignoradas = 0
        for t, th in lidas:
            decisao = "compra" if t["thread_id"] in compra_por_thread else "ignorado"
            ignoradas += decisao == "ignorado"
            con.execute("""INSERT INTO purchase_email_threads (thread_id, mailbox, messages, decision, seen_at)
                           VALUES (?,?,?,?,?) ON CONFLICT(thread_id) DO UPDATE SET messages=excluded.messages,
                           decision=CASE WHEN purchase_email_threads.decision='compra' THEN 'compra' ELSE excluded.decision END,
                           seen_at=excluded.seen_at""",
                        (t["thread_id"], CAIXA, len(th.get("mensagens", [])) or (t.get("mensagens") or 0), decisao, agora()))
        con.commit()
        pag = rever_paginas(con) if abrir_paginas else {"paginas_lidas": 0, "paginas_com_novidade": 0}
        res = {"ok": True, "conversas": len(threads), "compras_criadas": criadas, "compras_atualizadas": atualizadas,
               "ignoradas": ignoradas, "dias": dias, **pag}
        _marca(con, "gmail_compras", True, criadas + atualizadas,
               f"{criadas} compra(s) nova(s), {atualizadas} atualização(ões), {ignoradas} conversa(s) que não eram compra, "
               f"{pag['paginas_lidas']} página(s) de rastreio lida(s)", inicio)
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


def _thread(thread_id):
    try:
        return chamar("gmail", "gmail_thread", conta=CAIXA, thread_id=thread_id, limite=CORPO_LIMITE, com_links=True)
    except TypeError:                                     # provider antigo, sem os parâmetros novos
        return chamar("gmail", "gmail_thread", conta=CAIXA, thread_id=thread_id)


# ------------------------------------------------------------------ varredura completa
def varrer(con, dias=None):
    """"Já roda uma verificação completa no e-mail" (dono, 06/10): relê a caixa de um ano
    para trás. Mensagem já aplicada não conta de novo (message_id único)."""
    dias = int(dias or os.environ.get("COMPRAS_DIAS") or VARREDURA_DIAS)
    return sincronizar(con, dias=dias, forcar=True)


def refazer(con, dias=None, pasta=None):
    """Refaz do zero as compras que o e-mail criou e ninguém tocou, com as regras de hoje.

    A primeira semana no ar (30/09–06/10) juntou caixas de lojas diferentes pelo "2px" do CSS,
    criou compra de banco e de hotel e deixou aviso da UPS sem rastreio. Essas compras são só
    leitura do Gmail: dá para apagar e ler de novo. Antes, TUDO vai para um backup JSON em
    ~/.urace/backups/. Compra com item, pedido ligado, recebimento ou qualquer mão humana
    (audit_logs com usuário) fica como está e só recebe os eventos novos."""
    pasta = pasta or os.path.join(os.environ.get("URACE_DIR") or os.path.expanduser("~/.urace"), "backups")
    os.makedirs(pasta, exist_ok=True)
    alvo = [c["id"] for c in todos(con, "SELECT id FROM purchase_orders WHERE source='email' AND status IN ('pedida','rascunho')")
            if not _mexida_por_gente(con, c["id"])]
    copia = {"quando": agora(), "compras": [dict(r) for r in todos(con, f"SELECT * FROM purchase_orders WHERE id IN ({','.join('?' * len(alvo))})", alvo)] if alvo else [],
             "eventos": [dict(r) for r in todos(con, f"SELECT * FROM purchase_events WHERE purchase_id IN ({','.join('?' * len(alvo))})", alvo)] if alvo else [],
             "conversas": [dict(r) for r in todos(con, "SELECT * FROM purchase_email_threads")]}
    arq = os.path.join(pasta, f"compras-email-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    with open(arq, "w", encoding="utf-8") as f:
        json.dump(copia, f, ensure_ascii=False, indent=1)
    os.chmod(arq, 0o600)
    if alvo:
        marcas = ",".join("?" * len(alvo))
        con.execute(f"DELETE FROM purchase_events WHERE purchase_id IN ({marcas})", alvo)
        con.execute(f"DELETE FROM purchase_pages WHERE purchase_id IN ({marcas})", alvo)
        con.execute(f"DELETE FROM purchase_orders WHERE id IN ({marcas})", alvo)
    con.execute("DELETE FROM purchase_email_threads")
    auditar(con, "purchase.email.rebuild", "system", entity_type="purchase_order", entity_id=None,
            detail={"refeitas": len(alvo), "backup": arq})
    con.commit()
    r = varrer(con, dias)
    return {**r, "refeitas": len(alvo), "backup": arq}

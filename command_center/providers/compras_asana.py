"""A compra do painel espelhada no quadro Shipping Orders do Asana (dono, 06/10).

"Esse projeto lá do Asana vai estar um pouco desatualizado com pedidos mais antigos. Mas vale
de eles estarem lá também." A tela de Compras do Command Center é a fonte; o Asana recebe uma
cópia de cada compra que veio do e-mail, sem precisar de ninguém:

- **acha a tarefa que já existe** pelo nº do pedido, pela fatura ou pelo rastreio (no campo,
  no nome ou dentro do link que alguém colou) — nunca cria a segunda tarefa do mesmo pedido;
- **campo preenchido à mão não é sobrescrito**: só os vazios recebem valor (P-08: código no
  campo, link na descrição — decisão do dono de 06/10);
- **o status anda para a frente** (Payment pending → Order Created → Shipped → Arrived) e a
  tarefa vai para o quadro do status. Cancelled, Refunded e Pending/Review são decisão de
  gente: o Command Center não tira a tarefa de lá;
- tarefa **concluída** é pedido fechado: não se mexe;
- a descrição ganha um bloco "Command Center" com o link de rastreio, a página do pedido, a
  previsão, a fatura e a última atualização — o resto da descrição fica como está.

Liga/desliga: `CC_ASANA_PEDIDOS=0` desliga. Só compras com movimento nos últimos
`CC_ASANA_PEDIDOS_DIAS` (60) dias vão para o Asana: a varredura de um ano não enche o quadro
de pedido antigo já entregue.
"""
import os
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

from command_center.db import agora, atualizar, auditar, todos, um
from command_center.providers import NaoConectado, modulo
from command_center.providers.compras_email import canonico, rastreios_do_link
from command_center.providers.mensalidades import _aplicando

CAMPO_FORNECEDOR = "1215973949234112"
CAMPO_PEDIDO = "1215973949234125"
CAMPO_RASTREIO = "1215973949234127"
CAMPO_CRIADO = "1215973949234129"
CAMPO_STATUS = "1215973949424917"
# opção do status -> (gid da opção, gid da seção). Mesmo mapa de adminai/asana_status_sync.py.
STATUS = {"Order Created": ("1215973949424918", "1215973949234108"),
          "Shipped": ("1215973949424919", "1215973949234109"),
          "Arrived": ("1215973949424920", "1215973949234110"),
          "Pending/Review": ("1215973949424921", "1215973949234111"),
          "Payment pending": ("1215973949424959", "1217953854755118"),
          "Refunded": ("1216770934507250", "1217953805649184"),
          "Cancelled": ("1217677231456961", "1216267652449391")}
ORDEM = {"Payment pending": 0, "Order Created": 1, "Shipped": 2, "Arrived": 3}
DE_GENTE = {"Cancelled", "Refunded", "Pending/Review"}
FORNECEDORES = {"KartSport North America": "1215973949234114", "Comet Kart Sales": "1217594555399879",
                "eBay": "1215973949234113", "Amazon": "1215973949234115", "Aim": "1215973949424850",
                "Alphaline": "1215973949234116", "Cannotops": "1215973949234117", "Etsy": "1216267652449388"}
OUTRO = "1215973949234118"
PAINEL = os.environ.get("CC_URL_PUBLICA", "https://urace.us/ops")
LIMITE_POR_CICLO = 40

_ROTULO = {"pagamento_pendente": "pagamento pendente", "preparando": "preparando", "mensagem": "mensagem da loja",
           "etiqueta": "etiqueta criada", "em_transito": "em trânsito", "previsao": "previsão de entrega",
           "saiu_para_entrega": "saiu para entrega", "atraso": "atraso na entrega",
           "pedido": "pedido feito", "pagamento": "pago", "envio": "enviado", "entregue": "entregue",
           "cancelado": "cancelado na loja", "reembolso": "reembolso"}


def _n(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def chaves_da_tarefa(t):
    """Números de pedido e rastreio que uma tarefa do quadro carrega — no campo (às vezes um
    link: "orderId=111-…"), no nome ("Order #47843") ou no link de rastreio colado."""
    campos = {cf["gid"]: cf.get("display_value") or "" for cf in t.get("custom_fields", []) or []}
    textos = [campos.get(CAMPO_PEDIDO, ""), campos.get(CAMPO_RASTREIO, ""), t.get("name") or ""]
    chaves = set()
    for tx in textos:
        for m in re.finditer(r"\b\d{3}-\d{7}-\d{7}\b|\b\d{2}-\d{5}-\d{5}\b|#\s*([A-Z0-9-]{4,})|\b(1Z[0-9A-Z]{16})\b|\b(\d{10,22})\b", tx, re.I):
            chaves.add(_n(m.group(1) or m.group(2) or m.group(3) or m.group(0)))
        if tx.startswith("http"):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(tx).query)
            for k in ("orderId", "orderid", "purchaseOrderId", "id"):
                chaves.update(_n(v) for v in q.get(k, []))
            chaves.update(_n(n) for n, _ in rastreios_do_link(tx))
    so_campo = _n(campos.get(CAMPO_PEDIDO, ""))
    if so_campo and not campos.get(CAMPO_PEDIDO, "").startswith("http"):
        chaves.add(so_campo)
    return {c for c in chaves if len(c) >= 4}


def chaves_da_compra(c):
    ks = {_n(c["order_number"]), _n(c["invoice_number"])}
    ks.update(_n(t) for t in (c["tracking"] or "").split())
    return {k for k in ks if len(k) >= 4}


def status_da_compra(con, c):
    if c["ship_status"] == "cancelado":
        return "Cancelled"
    if um(con, "SELECT 1 AS x FROM purchase_events WHERE purchase_id=? AND kind='reembolso' LIMIT 1", (c["id"],)):
        return "Refunded"
    if c["ship_status"] == "entregue":
        return "Arrived"
    if c["ship_status"] == "enviado":
        return "Shipped"
    if c["payment_status"] == "pendente":
        return "Payment pending"
    return "Order Created"


def link_de_rastreio(numero, transp=None):
    u, t = numero.upper(), (transp or "").lower()
    if u.startswith("1Z") or t == "ups":
        return f"https://www.ups.com/track?track=yes&trackNums={numero}"
    if t == "fedex":
        return f"https://www.fedex.com/fedextrack/?trknbr={numero}"
    if t == "usps":
        return f"https://tools.usps.com/go/TrackConfirmAction?tLabels={numero}"
    if t == "dhl":
        return f"https://www.dhl.com/us-en/home/tracking/tracking-express.html?tracking-id={numero}"
    return None


def _quando_fl(iso):
    from zoneinfo import ZoneInfo
    try:
        d = datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except ValueError:
        return iso or ""
    return d.astimezone(ZoneInfo("America/New_York")).strftime("%m/%d/%Y %H:%M")


def bloco(con, c):
    """O texto do Command Center na descrição da tarefa (links aqui; códigos nos campos)."""
    linhas = [f"Fornecedor: {c['supplier']}"]
    if c["order_number"]:
        linhas.append(f"Pedido: {c['order_number']}")
    if c["invoice_number"]:
        pg = {"pendente": "pagamento pendente", "pago": "paga"}.get(c["payment_status"] or "", "")
        linhas.append(f"Fatura: {c['invoice_number']}" + (f" ({pg})" if pg else ""))
    for t in (c["tracking"] or "").split():
        url = link_de_rastreio(t, c["carrier"])
        linhas.append(f"Rastreio {c['carrier'] or ''} {t}".replace("  ", " ") + (f": {url}" if url else ""))
    if c["order_url"]:
        linhas.append(f"Página do pedido: {c['order_url']}")
    if c["expected_at"]:
        linhas.append(f"Previsão de entrega: {c['expected_at'][5:7]}/{c['expected_at'][8:10]}/{c['expected_at'][:4]}")
    ult = um(con, """SELECT kind, stage, at, subject FROM purchase_events WHERE purchase_id=?
                      ORDER BY COALESCE(at, created_at) DESC, id DESC LIMIT 1""", (c["id"],))
    if ult:
        linhas.append(f"Última atualização: {_ROTULO.get(ult['stage'] or ult['kind'], ult['kind'])} — "
                      f"{_quando_fl(ult['at'])} (Flórida) — “{(ult['subject'] or '')[:100]}”")
    linhas.append(f"Command Center: {PAINEL}/compras/{c['id']}")
    return "\n".join(linhas)


def _nome(c):
    if c["items_hint"]:
        return f"{c['items_hint']} — {c['supplier']}"
    num = c["order_number"] or c["invoice_number"] or c["reference"]
    return f"{c['supplier']} - Order #{num}" if num else f"{c['supplier']} — compra #{c['id']}"


def espelhar(con, limite=LIMITE_POR_CICLO):
    """Leva ao Shipping Orders as compras do e-mail que mudaram desde a última vez."""
    if os.environ.get("CC_ASANA_PEDIDOS", "1") == "0":
        return {"ok": True, "desligado": True}
    dias = int(os.environ.get("CC_ASANA_PEDIDOS_DIAS") or 60)
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y-%m-%d")
    fila = todos(con, """SELECT * FROM purchase_orders WHERE source='email' AND status != 'cancelada'
                           AND COALESCE(ordered_at, created_at) >= ?
                           AND (asana_synced_at IS NULL OR updated_at >= asana_synced_at)
                         ORDER BY id LIMIT ?""", (desde, limite))
    if not fila:
        return {"ok": True, "criadas": 0, "atualizadas": 0}
    try:
        m = modulo("asana")
        tarefas = m.pedidos_do_shipping()
    except NaoConectado as e:
        return {"ok": False, "motivo": f"Asana não conectado: {e}"}
    except Exception as e:                               # noqa: BLE001 — Asana fora do ar não para a sincronia
        return {"ok": False, "motivo": f"{type(e).__name__}: {str(e)[:200]}"}
    por_chave, por_gid = {}, {}
    for t in tarefas:
        por_gid[t["gid"]] = t
        for k in chaves_da_tarefa(t):
            por_chave.setdefault(k, t)
    criadas = atualizadas = erros = 0
    for c in fila:
        t = por_gid.get(c["asana_gid"]) if c["asana_gid"] else None
        if not t:
            t = next((por_chave[k] for k in chaves_da_compra(c) if k in por_chave), None)
        st = status_da_compra(con, c)
        atual = None
        if t:
            atual = next((cf.get("display_value") for cf in t.get("custom_fields", []) or [] if cf["gid"] == CAMPO_STATUS), None)
        mexer = not (atual in DE_GENTE or (atual in ORDEM and st in ORDEM and ORDEM[st] < ORDEM[atual]))
        rastreio = (c["tracking"] or "").split()
        se_vazio = {CAMPO_FORNECEDOR: FORNECEDORES.get(canonico(c["supplier"]), OUTRO)}
        if c["order_number"] or c["invoice_number"]:
            se_vazio[CAMPO_PEDIDO] = c["order_number"] or c["invoice_number"]
        if rastreio:
            se_vazio[CAMPO_RASTREIO] = " ".join(rastreio)
        data = (c["ordered_at"] or c["created_at"] or "")[:10]
        if data:
            se_vazio[CAMPO_CRIADO] = {"date": data}
        try:
            r = _aplicando(m.espelhar_pedido, gid=t["gid"] if t else None, nome=_nome(c), campos={CAMPO_STATUS: STATUS[st][0]},
                           campos_se_vazio=se_vazio, secao_gid=STATUS[st][1], bloco=bloco(con, c), mexer_status=mexer)
        except Exception as e:                           # noqa: BLE001 — erro fica na compra, o ciclo segue
            erros += 1
            atualizar(con, "purchase_orders", c["id"], asana_error=f"{type(e).__name__}: {str(e)[:300]}")
            con.commit()
            continue
        gid = r.get("gid") or (t["gid"] if t else None)
        if r.get("criada"):
            criadas += 1
            nova = {"gid": gid, "name": _nome(c), "custom_fields": []}
            por_gid[gid] = nova
            for k in chaves_da_compra(c):
                por_chave.setdefault(k, nova)
        elif r.get("aplicado"):
            atualizadas += 1
        con.execute("UPDATE purchase_orders SET asana_gid=?, asana_synced_at=?, asana_error=NULL WHERE id=?",
                    (gid, agora(), c["id"]))
        if r.get("aplicado"):
            auditar(con, "purchase.asana", "system", entity_type="purchase_order", entity_id=c["id"],
                    detail={"tarefa": gid, "criada": bool(r.get("criada")), "status": st if mexer else None})
        con.commit()
    return {"ok": erros == 0, "criadas": criadas, "atualizadas": atualizadas, "erros": erros}

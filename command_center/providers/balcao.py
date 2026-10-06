"""BALCÃO — o leitor de QR e de código de barras (#87).

Dono, 05/10: *"o mecânico vai ler o QR Code do cliente e vai ler o código de barras da
peça. E aí já vai subir para aquele cliente, no card daquele cliente, uma invoice aberta
de partes com aquela peça"*. E as decisões do mesmo dia:

- **A invoice nasce no QuickBooks na hora**, na primeira peça cobrada, e cada peça
  seguinte vira linha nela. **Uma por cliente por dia** (fuso da Flórida), com o memo
  "Parts invoice — parts used | piloto | Service date". **Não é enviada sozinha**: alguém
  aperta "Enviar" no fim do dia ou no dia seguinte.
- **O mecânico lança**, e cada peça lida já salva.
- **Código novo cria o item no QuickBooks**, dentro da categoria (Parts, Engine parts…).
- **Peça do cliente** (o jogo de pneus que ele comprou e não usou) é lida em outro modo,
  GUARDAR, que põe no estoque dele e não cobra. Cobrar uma peça que o cliente tem guardada
  pede confirmação: a diferença tem de ser evidente para não misturar.

A ordem é sempre: **o painel grava primeiro** (estoque, cobrança, a lista da tela) e só
depois o QuickBooks recebe a invoice inteira de novo. Se o QuickBooks falhar, nada se perde:
fica o erro na invoice e o botão de tentar de novo.

O QR do cliente leva um **código aleatório** do card, não o id: ninguém chega ao card de
outro trocando um número. Lido pela câmera de um celular qualquer, ele abre o card no painel,
e o painel pede login.
"""
import io
import re
import secrets
import sqlite3

from command_center import enderecos
from command_center.db import agora, atualizar, inserir, todos, um
from command_center.providers import estoque, portal

MODOS = ("cobrar", "guardar", "usar_do_cliente")
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"        # sem 0/O e 1/I: dá para ler em voz alta
RX_QR = re.compile(r"/C/([A-Z2-9]{10})(?:[/?#]|$)")
MEMO = "Parts invoice — parts used"


class ErroBalcao(ValueError):
    """Regra do balcão violada. A mensagem é para a tela."""


class Confirmar(ErroBalcao):
    """Precisa de uma decisão de quem está lendo antes de seguir. `motivo` diz qual."""

    def __init__(self, motivo, mensagem):
        super().__init__(mensagem)
        self.motivo = motivo


def hoje():
    return portal.hoje().isoformat()


# ------------------------------------------------------------------ QR do cliente
def codigo_do_cliente(con, client_id):
    """O código do QR deste card (nasce na primeira vez que alguém pede)."""
    c = um(con, "SELECT id, scan_code FROM clients WHERE id=?", (client_id,))
    if not c:
        raise LookupError("cliente não existe")
    if c["scan_code"]:
        return c["scan_code"]
    for _ in range(8):
        cod = "".join(secrets.choice(ALFABETO) for _ in range(10))
        try:
            con.execute("UPDATE clients SET scan_code=? WHERE id=? AND scan_code IS NULL", (cod, client_id))
            break
        except sqlite3.IntegrityError:
            continue
    return um(con, "SELECT scan_code FROM clients WHERE id=?", (client_id,))["scan_code"]


def url_do_cliente(codigo):
    return f"{enderecos.principal()}/ops/c/{codigo}"


def qr_svg(con, client_id):
    import segno
    b = io.BytesIO()
    segno.make(url_do_cliente(codigo_do_cliente(con, client_id)), error="m").save(
        b, kind="svg", scale=8, border=2, dark="#000", light="#fff", xmldecl=False)
    return b.getvalue()


def cliente_pelo_codigo(con, codigo):
    return um(con, "SELECT * FROM clients WHERE scan_code=?", ((codigo or "").strip().upper(),))


def resumo_cliente(c):
    return {"id": c["id"], "nome": c["pilot_name"] or c["name"], "responsavel": c["name"],
            "pilot_name": c["pilot_name"], "email": c["email"]}


# ------------------------------------------------------------------ código de barras da peça
def _codigo(v):
    v = re.sub(r"\s+", "", v or "")
    if not 3 <= len(v) <= 64:
        raise ErroBalcao("código inválido: leia de novo")
    if RX_QR.search(v.upper()):
        raise ErroBalcao("este é o QR de um cliente, não de uma peça")
    return v


def item_publico(con, it, client_id=None):
    codigos = [r["code"] for r in todos(con, "SELECT code FROM stock_barcodes WHERE item_id=? ORDER BY created_at", (it["id"],))]
    out = {"id": it["id"], "name": it["name"], "kind": it["kind"], "unit": it["unit"], "price": it["price"],
           "category": it["category"], "sku": it["sku"], "tracking": it["tracking"],
           "qbo_item_id": it["qbo_item_id"], "qbo_item_name": it["qbo_item_name"], "codigos": codigos,
           "nosso": estoque.saldo(con, it["id"], client_id=None)}
    if client_id:
        out["do_cliente"] = estoque.saldo(con, it["id"], client_id=client_id)
    return out


def ler(con, texto, client_id=None):
    """O que o leitor mandou: o QR de um cliente, uma peça conhecida ou um código novo."""
    t = (texto or "").strip()
    m = RX_QR.search(t.upper())
    if m:
        c = cliente_pelo_codigo(con, m.group(1))
        if not c:
            raise ErroBalcao("QR de cliente não reconhecido")
        return {"tipo": "cliente", "cliente": resumo_cliente(c)}
    cod = _codigo(t)
    b = um(con, "SELECT b.item_id FROM stock_barcodes b JOIN stock_items i ON i.id=b.item_id "
                "WHERE b.code=? AND i.active=1", (cod,))
    if not b:                       # peça excluída lê como código novo: dá para cadastrar de novo
        return {"tipo": "desconhecido", "codigo": cod}
    return {"tipo": "peca", "codigo": cod, "item": item_publico(con, estoque.item(con, b["item_id"]), client_id)}


def cadastrar_codigo(con, codigo, item_id, por=None, origem="fabricante"):
    cod = _codigo(codigo)
    it = estoque.item(con, item_id)
    ja = um(con, "SELECT b.item_id, i.name, i.active FROM stock_barcodes b JOIN stock_items i ON i.id=b.item_id WHERE b.code=?", (cod,))
    if ja and not ja["active"]:     # era de uma peça excluída: o código passa para a peça nova
        con.execute("UPDATE stock_barcodes SET item_id=?, origin=?, created_by=? WHERE code=?", (it["id"], origem, por, cod))
        return cod
    if ja:
        if ja["item_id"] == it["id"]:
            return cod
        raise ErroBalcao(f"o código {cod} já é de {ja['name']}")
    inserir(con, "stock_barcodes", code=cod, item_id=it["id"], origin=origem, created_by=por)
    return cod


def codigo_urace(con, item_id, por=None):
    """A etiqueta da URACE, para peça sem código na embalagem: URC + o número do item."""
    it = estoque.item(con, item_id)
    ja = um(con, "SELECT code FROM stock_barcodes WHERE item_id=? AND origin='urace'", (it["id"],))
    if ja:
        return ja["code"]
    return cadastrar_codigo(con, f"URC{it['id']:06d}", it["id"], por, origem="urace")


def etiqueta_pdf(con, item_id):
    """Etiqueta 62 × 29 mm (rolo das térmicas comuns): código de barras Code 128 + nome."""
    from reportlab.graphics.barcode import code128
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    it = estoque.item(con, item_id)
    cod = codigo_urace(con, item_id)
    b = io.BytesIO()
    larg, alt = 62 * mm, 29 * mm
    cv = canvas.Canvas(b, pagesize=(larg, alt))
    cv.setTitle(f"Etiqueta {cod}")
    barra = code128.Code128(cod, barHeight=13 * mm, barWidth=0.33 * mm, humanReadable=True)
    barra.drawOn(cv, max(2 * mm, (larg - barra.width) / 2), 9 * mm)
    cv.setFont("Helvetica-Bold", 7)
    cv.drawCentredString(larg / 2, 3 * mm, it["name"][:48])
    cv.showPage()
    cv.save()
    return b.getvalue()


# ------------------------------------------------------------------ item no QuickBooks
def _qbo():
    from command_center.providers import modulo
    return modulo("quickbooks")


def ligar_item_qbo(con, item_id, qbo_item_id=None, categoria_id=None):
    """Liga a peça a um item do catálogo do QuickBooks: um que já existe, ou cria agora
    dentro da categoria. É o que deixa a peça entrar na invoice."""
    it = estoque.item(con, item_id)
    if qbo_item_id:
        q = um(con, "SELECT id, name, full_name FROM qbo_items WHERE id=?", (str(qbo_item_id),))
        if not q:
            raise ErroBalcao("item do QuickBooks não encontrado: sincronize o QuickBooks e tente de novo")
        atualizar(con, "stock_items", it["id"], qbo_item_id=q["id"], qbo_item_name=q["full_name"] or q["name"])
        return estoque.item(con, item_id)
    if it["price"] is None:
        raise ErroBalcao(f"{it['name']} ainda não tem preço final: defina o preço antes de criar no QuickBooks")
    r = _qbo().criar_item_peca_sistema(nome=it["name"], preco=it["price"], categoria_id=categoria_id,
                                       sku=it["sku"] or it["part_number"], descricao=it["name"])
    if not r.get("id"):
        raise ErroBalcao("o QuickBooks não devolveu o item criado")
    con.execute("""INSERT INTO qbo_items (id, name, full_name, price, type, active, synced_at) VALUES (?,?,?,?,?,1,?)
                   ON CONFLICT(id) DO UPDATE SET name=excluded.name, full_name=excluded.full_name, price=excluded.price""",
                (str(r["id"]), r.get("nome") or it["name"], r.get("nome_completo"), r.get("preco"), r.get("tipo"), agora()))
    atualizar(con, "stock_items", it["id"], qbo_item_id=str(r["id"]), qbo_item_name=r.get("nome_completo") or r.get("nome"))
    return estoque.item(con, item_id)


def cliente_qbo(con, client_id):
    from command_center.api.mensal import _cliente_qbo
    from fastapi import HTTPException
    c = um(con, "SELECT * FROM clients WHERE id=?", (client_id,))
    try:
        return _cliente_qbo(con, c)[0] if c else None
    except HTTPException:
        raise ErroBalcao("QuickBooks não está conectado: não dá para cobrar agora (guardar no estoque do cliente funciona)")


# ------------------------------------------------------------------ lançar
def _invoice_do_dia(con, client_id, data, por):
    p = um(con, "SELECT * FROM parts_invoices WHERE client_id=? AND service_date=? AND status='aberta' ORDER BY id DESC LIMIT 1",
           (client_id, data))
    if p:
        return p
    return um(con, "SELECT * FROM parts_invoices WHERE id=?",
              (inserir(con, "parts_invoices", client_id=client_id, service_date=data, created_by=por),))


def _ultimo_movimento(con, item_id):
    return um(con, "SELECT MAX(id) AS id FROM stock_moves WHERE item_id=?", (item_id,))["id"]


def lancar(con, client_id, item_id, modo, qty=1, local=estoque.SEDE, por=None, codigo=None, confirmado=False):
    """Uma leitura. Devolve a linha de `counter_scans`. Não fala com o QuickBooks: quem chama
    grava (commit) e depois chama `sincronizar_qbo` com a invoice da linha."""
    if modo not in MODOS:
        raise ErroBalcao("modo inválido")
    c = um(con, "SELECT * FROM clients WHERE id=?", (client_id,))
    if not c:
        raise LookupError("cliente não existe")
    it = estoque.item(con, item_id)
    if it["tracking"] == "serie":
        raise ErroBalcao(f"{it['name']} tem número de série: lance pela tela de Estoque")
    qty = float(qty or 1)
    loc = estoque.local(con, local)
    charge_id = pinv_id = None
    if modo == "cobrar":
        if not confirmado and estoque.saldo(con, it["id"], client_id=client_id) > 0:
            raise Confirmar("tem_do_cliente", f"{c['pilot_name'] or c['name']} tem {it['name']} guardado com a gente. "
                                              "Usar a dele (sem cobrar) ou cobrar uma nova?")
        if it["price"] is None:
            raise ErroBalcao(f"{it['name']} não tem preço final: chame o gerente para definir")
        if not it["qbo_item_id"]:
            raise Confirmar("precisa_item_qbo", f"{it['name']} ainda não tem item no QuickBooks: o gerente escolhe a categoria e cria")
        if not cliente_qbo(con, client_id):
            raise ErroBalcao("este card não está ligado a um cliente do QuickBooks (sem invoice e sem e-mail que bata). "
                             "Ligue no card antes de cobrar")
        estoque.saida(con, it["id"], qty=qty, de=loc, client_id=None, para_cliente_id=client_id, reason="venda",
                      by_user_id=por, source="balcao", notes="balcão")
        move = _ultimo_movimento(con, it["id"])
        pinv_id = _invoice_do_dia(con, client_id, hoje(), por)["id"]
        charge_id = estoque.registrar_cobranca(con, it["id"], client_id, qty, move_id=move, by_user_id=por, notes="balcão")
        atualizar(con, "stock_charges", charge_id, parts_invoice_id=pinv_id)
    elif modo == "guardar":
        estoque.entrada(con, it["id"], qty=qty, para=loc, client_id=client_id, reason="guardado do cliente",
                        by_user_id=por, source="balcao", notes="balcão")
        move = _ultimo_movimento(con, it["id"])
    else:
        estoque.saida(con, it["id"], qty=qty, de=loc, client_id=client_id, para_cliente_id=client_id,
                      reason="uso em serviço", by_user_id=por, source="balcao", notes="balcão: peça do cliente")
        move = _ultimo_movimento(con, it["id"])
    sid = inserir(con, "counter_scans", client_id=client_id, item_id=it["id"], code=codigo, mode=modo, qty=qty,
                  location_id=loc["id"], move_id=move, charge_id=charge_id, parts_invoice_id=pinv_id, by_user_id=por)
    return um(con, "SELECT * FROM counter_scans WHERE id=?", (sid,))


def desfazer(con, scan_id, por=None):
    """Desfaz uma leitura: devolve ao estoque de onde saiu e tira a linha da invoice.
    Invoice já enviada não muda por aqui — o ajuste é no QuickBooks."""
    s = um(con, "SELECT * FROM counter_scans WHERE id=?", (scan_id,))
    if not s:
        raise LookupError("leitura não existe")
    if s["undone_at"]:
        raise ErroBalcao("esta leitura já foi desfeita")
    if s["mode"] == "cobrar":
        p = um(con, "SELECT status FROM parts_invoices WHERE id=?", (s["parts_invoice_id"],))
        if p and p["status"] != "aberta":
            raise ErroBalcao("a invoice desta peça já foi enviada: ajuste pelo QuickBooks")
        estoque.entrada(con, s["item_id"], qty=s["qty"], para=s["location_id"], client_id=None,
                        reason="estorno do balcão", by_user_id=por, source="balcao")
        atualizar(con, "stock_charges", s["charge_id"], status="waived", notes="desfeito no balcão",
                  resolved_by=por, resolved_at=agora())
    elif s["mode"] == "guardar":
        estoque.saida(con, s["item_id"], qty=s["qty"], de=s["location_id"], client_id=s["client_id"],
                      para_cliente_id=s["client_id"], reason="estorno do balcão", by_user_id=por, source="balcao")
    else:
        estoque.entrada(con, s["item_id"], qty=s["qty"], para=s["location_id"], client_id=s["client_id"],
                        reason="estorno do balcão", by_user_id=por, source="balcao")
    atualizar(con, "counter_scans", s["id"], undone_at=agora(), undone_by=por)
    return um(con, "SELECT * FROM counter_scans WHERE id=?", (s["id"],))


# ------------------------------------------------------------------ invoice de peças ↔ QuickBooks
def linhas(con, pinv_id):
    return todos(con, """SELECT ch.id, ch.qty, ch.unit_price, i.name, i.sku, i.qbo_item_id
                           FROM stock_charges ch JOIN stock_items i ON i.id=ch.item_id
                          WHERE ch.parts_invoice_id=? AND ch.status!='waived' ORDER BY ch.id""", (pinv_id,))


def memo(con, p):
    from command_center.api.acoes import memo_invoice
    c = um(con, "SELECT name, pilot_name FROM clients WHERE id=?", (p["client_id"],))
    return memo_invoice(produto=MEMO, piloto=(c["pilot_name"] or c["name"]) if c else None, data_servico=p["service_date"])


def sincronizar_qbo(con, pinv_id):
    """Leva a invoice inteira ao QuickBooks (cria na primeira vez). Erro fica guardado na
    invoice, para a tela mostrar e o botão tentar de novo — a leitura já está salva."""
    from command_center.providers import NaoConectado
    p = um(con, "SELECT * FROM parts_invoices WHERE id=?", (pinv_id,))
    if not p or p["status"] != "aberta":
        return p
    ls = linhas(con, p["id"])
    if not ls and not p["qbo_invoice_id"]:
        atualizar(con, "parts_invoices", p["id"], total=0, qbo_error=None)
        return um(con, "SELECT * FROM parts_invoices WHERE id=?", (p["id"],))
    corpo = [{"item_id": l["qbo_item_id"], "quantidade": l["qty"], "unitario": l["unit_price"],
              "descricao": l["name"] + (f" · {l['sku']}" if l["sku"] else "")} for l in ls]
    try:
        cliente = cliente_qbo(con, p["client_id"])
        if not cliente:
            raise ErroBalcao("este card não está ligado a um cliente do QuickBooks")
        r = _qbo().invoice_pecas_sistema(cliente_id=cliente, linhas=corpo, memo=memo(con, p), data=p["service_date"],
                                         invoice_id=p["qbo_invoice_id"])
    except NaoConectado:
        atualizar(con, "parts_invoices", p["id"], qbo_error="QuickBooks não está conectado")
        return um(con, "SELECT * FROM parts_invoices WHERE id=?", (p["id"],))
    except Exception as e:                                       # noqa: BLE001 — vai para a tela
        atualizar(con, "parts_invoices", p["id"], qbo_error=str(e)[:400])
        return um(con, "SELECT * FROM parts_invoices WHERE id=?", (p["id"],))
    total = round(sum(float(l["qty"]) * float(l["unit_price"]) for l in ls), 2)
    atualizar(con, "parts_invoices", p["id"], qbo_invoice_id=str(r.get("id") or p["qbo_invoice_id"]),
              doc_number=r.get("numero") or p["doc_number"], total=total, qbo_error=None, qbo_synced_at=agora(),
              status="anulada" if r.get("anulada") else "aberta")
    if ls:
        con.execute(f"UPDATE stock_charges SET status='invoiced' WHERE id IN ({','.join('?' * len(ls))})",
                    tuple(l["id"] for l in ls))
    return um(con, "SELECT * FROM parts_invoices WHERE id=?", (p["id"],))


def enviar(con, pinv_id, por=None):
    p = um(con, "SELECT * FROM parts_invoices WHERE id=?", (pinv_id,))
    if not p:
        raise LookupError("invoice de peças não existe")
    if p["status"] != "aberta":
        raise ErroBalcao(f"esta invoice já está {p['status']}")
    if not p["qbo_invoice_id"] or p["qbo_error"]:
        raise ErroBalcao("a invoice ainda não está no QuickBooks: toque em 'Tentar de novo' antes de enviar")
    r = _qbo().enviar_invoice_sistema(p["qbo_invoice_id"])
    atualizar(con, "parts_invoices", p["id"], status="enviada", sent_by=por, sent_at=agora(), sent_to=r.get("enviado_para"))
    return um(con, "SELECT * FROM parts_invoices WHERE id=?", (p["id"],))


# ------------------------------------------------------------------ o que a tela mostra
def invoice_publica(con, p):
    c = um(con, "SELECT id, name, pilot_name FROM clients WHERE id=?", (p["client_id"],))
    return {**dict(p), "cliente": (c["pilot_name"] or c["name"]) if c else None,
            "linhas": [dict(l, total=round(float(l["qty"]) * float(l["unit_price"]), 2)) for l in linhas(con, p["id"])]}


def do_cliente(con, client_id, data=None):
    """Tudo o que a tela do balcão mostra depois de ler o QR."""
    c = um(con, "SELECT * FROM clients WHERE id=?", (client_id,))
    if not c:
        raise LookupError("cliente não existe")
    data = data or hoje()
    leituras = todos(con, """SELECT s.*, i.name, i.unit, u.name AS por FROM counter_scans s
                               JOIN stock_items i ON i.id=s.item_id LEFT JOIN users u ON u.id=s.by_user_id
                              WHERE s.client_id=? AND substr(s.at,1,10)>=? ORDER BY s.id DESC LIMIT 50""",
                     (client_id, data[:8] + "01"))
    invs = todos(con, "SELECT * FROM parts_invoices WHERE client_id=? AND (status='aberta' OR service_date=?) ORDER BY id DESC",
                 (client_id, data))
    return {"cliente": resumo_cliente(c), "data": data, "qr": url_do_cliente(codigo_do_cliente(con, client_id)),
            "invoices": [invoice_publica(con, p) for p in invs],
            "leituras": [dict(x) for x in leituras], "guardado": estoque.do_cliente(con, client_id)["pecas"]}


def a_enviar(con, limit=50, offset=0):
    """As invoices de peças abertas, para alguém apertar "Enviar"."""
    total = um(con, "SELECT COUNT(*) AS n FROM parts_invoices WHERE status='aberta' AND total>0")["n"]
    itens = todos(con, "SELECT * FROM parts_invoices WHERE status='aberta' AND total>0 ORDER BY service_date, id LIMIT ? OFFSET ?",
                  (limit, offset))
    return {"itens": [invoice_publica(con, p) for p in itens], "total": total, "limit": limit, "offset": offset}

"""Balcão (#87): a tela do leitor de QR e de código de barras.

As regras moram em `providers/balcao.py`; aqui fica quem pode o quê:

- **ler, lançar (cobrar / guardar / usar a peça do cliente), desfazer, cadastrar código e
  imprimir etiqueta** é OPERATOR: é o mecânico com o leitor na mão (dono, 05/10: *"o mecânico
  vai lançar as peças e assim que ele lançar a peça já salva a invoice"*).
- **criar o item no QuickBooks e enviar a invoice** é MANAGER: um mexe no catálogo da
  contabilidade, o outro manda cobrança para o cliente.

Cada lançamento grava primeiro aqui (commit) e depois leva a invoice ao QuickBooks. Se o
QuickBooks falhar, a leitura fica salva e a tela mostra o erro com "Tentar de novo".
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import auditar, get_db, um
from command_center.providers import balcao as b, estoque

r = APIRouter(prefix="/ops/api/balcao", tags=["balcao"])


def _aud(con, request, u, evento, tipo, eid, detalhe):
    auditar(con, evento, f"user:{u['id']}", user_id=u["id"], entity_type=tipo, entity_id=eid, detail=detalhe,
            ip=auth._ip(request))


def _erro(e):
    if isinstance(e, b.Confirmar):
        return HTTPException(409, {"motivo": e.motivo, "mensagem": str(e)})
    return HTTPException(400, str(e))


def _gerente(u):
    return bool(u.get("free")) or auth.pode(u.get("role"), "MANAGER")


@r.get("/ler")
def ler(codigo: str, client_id: int | None = None, con: sqlite3.Connection = Depends(get_db),
        u=Depends(auth.exige("OPERATOR"))):
    """O que o leitor mandou: QR de cliente, peça conhecida ou código novo."""
    try:
        return b.ler(con, codigo, client_id)
    except (b.ErroBalcao, estoque.ErroEstoque) as e:
        raise _erro(e)


@r.get("/cliente/{client_id}")
def cliente(client_id: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    try:
        out = {**b.do_cliente(con, client_id), "gerente": _gerente(u)}
    except LookupError:
        raise HTTPException(404, "Cliente não encontrado.")
    con.commit()                                     # o código do QR nasce na primeira vez
    return out


@r.get("/cliente/{client_id}/qr.svg")
def qr(client_id: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    try:
        svg = b.qr_svg(con, client_id)
    except LookupError:
        raise HTTPException(404, "Cliente não encontrado.")
    con.commit()
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "private, no-store"})


@r.get("/c/{codigo}")
def pelo_qr(codigo: str, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """O QR lido pela câmera de um celular qualquer abre /ops/c/<código>: a tela pergunta aqui de quem é."""
    c = b.cliente_pelo_codigo(con, codigo)
    if not c:
        raise HTTPException(404, "QR de cliente não reconhecido.")
    return b.resumo_cliente(c)


class LancarIn(BaseModel):
    client_id: int
    item_id: int
    modo: str
    qty: float = 1
    local: str = estoque.SEDE
    codigo: str | None = None
    confirmado: bool = False


def _sincronizar(con, pinv_id):
    if pinv_id:
        b.sincronizar_qbo(con, pinv_id)
        con.commit()


@r.post("/lancar", status_code=201)
def lancar(dados: LancarIn, request: Request, con: sqlite3.Connection = Depends(get_db),
           u=Depends(auth.exige("OPERATOR"))):
    try:
        s = b.lancar(con, dados.client_id, dados.item_id, dados.modo, dados.qty, dados.local, u["id"],
                     dados.codigo, dados.confirmado)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except (b.ErroBalcao, estoque.ErroEstoque) as e:
        con.rollback()
        raise _erro(e)
    _aud(con, request, u, f"balcao.{dados.modo}", "client", dados.client_id,
         {"item": dados.item_id, "qty": dados.qty, "leitura": s["id"], "invoice_pecas": s["parts_invoice_id"]})
    con.commit()
    _sincronizar(con, s["parts_invoice_id"])
    return {"leitura": dict(s), **b.do_cliente(con, dados.client_id)}


@r.post("/leituras/{scan_id}/desfazer")
def desfazer(scan_id: int, request: Request, con: sqlite3.Connection = Depends(get_db),
             u=Depends(auth.exige("OPERATOR"))):
    try:
        s = b.desfazer(con, scan_id, u["id"])
    except LookupError:
        raise HTTPException(404, "Leitura não encontrada.")
    except (b.ErroBalcao, estoque.ErroEstoque) as e:
        con.rollback()
        raise _erro(e)
    _aud(con, request, u, "balcao.desfazer", "client", s["client_id"], {"leitura": scan_id, "modo": s["mode"]})
    con.commit()
    _sincronizar(con, s["parts_invoice_id"])
    return b.do_cliente(con, s["client_id"])


class CodigoIn(BaseModel):
    codigo: str
    item_id: int | None = None
    # peça nova, cadastrada na hora em que o código aparece (o mecânico pode: dono, 23/09)
    nome: str | None = None
    kind: str = "peca"
    category: str | None = None
    # gerente: preço final e o item no QuickBooks, criado na hora (dono, 05/10)
    price: float | None = None
    qbo_item_id: str | None = None
    qbo_categoria_id: str | None = None


@r.post("/codigos", status_code=201)
def cadastrar(dados: CodigoIn, request: Request, con: sqlite3.Connection = Depends(get_db),
              u=Depends(auth.exige("OPERATOR"))):
    gerente = _gerente(u)
    if (dados.price is not None or dados.qbo_item_id or dados.qbo_categoria_id) and not gerente:
        raise HTTPException(403, "Preço e item do QuickBooks são do gerente.")
    try:
        item_id = dados.item_id
        if not item_id:
            item_id = estoque.criar_item(con, dados.kind, dados.nome or "", category=dados.category, price=dados.price)
        elif dados.price is not None:
            estoque.atualizar_item(con, item_id, price=dados.price)
        cod = b.cadastrar_codigo(con, dados.codigo, item_id, u["id"])
    except (b.ErroBalcao, estoque.ErroEstoque) as e:
        con.rollback()
        raise _erro(e)
    _aud(con, request, u, "balcao.codigo", "stock_item", item_id, {"codigo": cod, "novo": not dados.item_id})
    con.commit()
    aviso = None
    if gerente and (dados.qbo_item_id or dados.qbo_categoria_id):
        try:
            b.ligar_item_qbo(con, item_id, dados.qbo_item_id, dados.qbo_categoria_id)
            _aud(con, request, u, "balcao.item_qbo", "stock_item", item_id,
                 {"qbo_item": dados.qbo_item_id, "categoria": dados.qbo_categoria_id})
            con.commit()
        except Exception as e:                       # noqa: BLE001 — o código já está salvo
            con.rollback()
            aviso = f"Código salvo, mas o item do QuickBooks não foi criado: {str(e)[:300]}"
    return {"codigo": cod, "item": b.item_publico(con, estoque.item(con, item_id)), "aviso": aviso}


class ItemQboIn(BaseModel):
    qbo_item_id: str | None = None
    categoria_id: str | None = None
    price: float | None = None


@r.post("/itens/{item_id}/quickbooks")
def item_qbo(item_id: int, dados: ItemQboIn, request: Request, con: sqlite3.Connection = Depends(get_db),
             u=Depends(auth.exige("MANAGER"))):
    from command_center.providers import NaoConectado
    try:
        if dados.price is not None:
            estoque.atualizar_item(con, item_id, price=dados.price)
        it = b.ligar_item_qbo(con, item_id, dados.qbo_item_id, dados.categoria_id)
    except NaoConectado:
        con.rollback()
        raise HTTPException(503, "QuickBooks não está conectado.")
    except (b.ErroBalcao, estoque.ErroEstoque) as e:
        con.rollback()
        raise _erro(e)
    except Exception as e:                           # noqa: BLE001 — recusa do QuickBooks
        con.rollback()
        raise HTTPException(502, f"QuickBooks: {str(e)[:300]}")
    _aud(con, request, u, "balcao.item_qbo", "stock_item", item_id, {"qbo_item": it["qbo_item_id"]})
    con.commit()
    return {"item": b.item_publico(con, it)}


@r.get("/categorias")
def categorias(con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    """As categorias do QuickBooks e os itens de peça que já existem lá (do espelho)."""
    from command_center.providers import NaoConectado
    try:
        cats, conectado = b._qbo().categorias_sistema(), True
    except NaoConectado:                             # a tela avisa e o item fica para depois
        cats, conectado = [], False
    itens = [dict(x) for x in con.execute("SELECT id, name, full_name, price FROM qbo_items WHERE active=1 "
                                          "AND COALESCE(type,'')!='Category' ORDER BY full_name").fetchall()]
    return {"categorias": cats, "itens": itens, "conectado": conectado}


@r.post("/itens/{item_id}/codigo-urace", status_code=201)
def codigo_urace(item_id: int, request: Request, con: sqlite3.Connection = Depends(get_db),
                 u=Depends(auth.exige("OPERATOR"))):
    try:
        cod = b.codigo_urace(con, item_id, u["id"])
    except (b.ErroBalcao, estoque.ErroEstoque) as e:
        raise _erro(e)
    con.commit()
    return {"codigo": cod}


@r.get("/itens/{item_id}/etiqueta.pdf")
def etiqueta(item_id: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    try:
        pdf = b.etiqueta_pdf(con, item_id)
    except estoque.ErroEstoque as e:
        raise _erro(e)
    con.commit()
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="etiqueta-{item_id}.pdf"', "Cache-Control": "no-store"})


@r.get("/invoices")
def invoices(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
             con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """Invoices de peças abertas: o que falta enviar."""
    return {**b.a_enviar(con, limit, offset), "gerente": _gerente(u)}


@r.post("/invoices/{pinv_id}/sincronizar")
def sincronizar(pinv_id: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    p = b.sincronizar_qbo(con, pinv_id)
    if not p:
        raise HTTPException(404, "Invoice de peças não encontrada.")
    con.commit()
    return b.invoice_publica(con, p)


@r.post("/invoices/{pinv_id}/conferir-pagamento")
def conferir_pagamento(pinv_id: int, request: Request, con: sqlite3.Connection = Depends(get_db),
                       u=Depends(auth.exige("OPERATOR"))):
    """Depois de passar o cartão no GoPayment: confere no QuickBooks se a invoice ficou paga."""
    from command_center.providers import NaoConectado
    if not b.cartao_ligado():
        raise HTTPException(404, "Cartão no balcão desligado (CC_BALCAO_CARTAO=0).")
    try:
        r = b.conferir_pagamento(con, pinv_id, u["id"])
    except LookupError:
        raise HTTPException(404, "Invoice de peças não encontrada.")
    except b.ErroBalcao as e:
        raise HTTPException(400, str(e))
    except NaoConectado:
        raise HTTPException(503, "QuickBooks não está conectado.")
    con.commit()
    return {**r, "invoice": b.invoice_publica(con, um(con, "SELECT * FROM parts_invoices WHERE id=?", (pinv_id,)))}


@r.post("/invoices/{pinv_id}/enviar")
def enviar(pinv_id: int, request: Request, con: sqlite3.Connection = Depends(get_db),
           u=Depends(auth.exige("MANAGER"))):
    from command_center.providers import NaoConectado
    try:
        p = b.enviar(con, pinv_id, u["id"])
    except LookupError:
        raise HTTPException(404, "Invoice de peças não encontrada.")
    except NaoConectado:
        raise HTTPException(503, "QuickBooks não está conectado.")
    except b.ErroBalcao as e:
        raise _erro(e)
    except Exception as e:                           # noqa: BLE001 — recusa do QuickBooks
        raise HTTPException(502, f"QuickBooks: {str(e)[:300]}")
    _aud(con, request, u, "balcao.enviar", "client", p["client_id"],
         {"invoice_pecas": p["id"], "qbo": p["qbo_invoice_id"], "para": p["sent_to"]})
    con.commit()
    return b.invoice_publica(con, um(con, "SELECT * FROM parts_invoices WHERE id=?", (p["id"],)))

"""Estoque — o que existe, onde está e de quem é.

A tela de Logística fala com estas rotas. As regras todas moram em
`providers/estoque.py`; aqui só há o que é da web: quem pode fazer o quê, e traduzir
`ErroEstoque` em 400 com a mensagem que o painel mostra para gente.

**Quem pode o quê**, e o porquê de cada nível:

- **ver** é OPERATOR: o mecânico no box precisa saber se tem pastilha antes de prometer.
- **contar, dar entrada, transferir** é OPERATOR: é o trabalho dele, e contagem errada
  aparece na conferência.
- **cadastrar peça nova, com foto** é OPERATOR — **decisão do dono, 23/09**: *"o acesso
  de mecânico consiga, ao clicar em estoque, ter um botão de adicionar; aí ele consegue
  colocar foto, descrição, nome e quantidade do item que temos"*. Eu tinha posto isso em
  MANAGER por conta própria e estava errado: quem está na prateleira é quem sabe o que
  há nela, e obrigar a pedir para o gerente é o jeito certo de o cadastro nunca acontecer.
- **vender e ajustar** é MANAGER: ajuste sem dono vira estoque que não bate, e venda
  mexe em dinheiro.
- **assinalar peça para um cliente** é OPERATOR (29/09): é quem separa na prateleira.
  **Devolver para a URACE** é MANAGER: transforma o que era dos outros em vendável.
- **valor de compra, margem e preço final** são MANAGER, e custo e margem nem aparecem
  para o mecânico: ele vê o preço que vai para o cliente, não quanto a casa ganha.

A quantidade informada no cadastro entra como **contagem física**, não como compra: o
mecânico está dizendo "tem isto aqui agora", e é exatamente o que contagem quer dizer.
"""
import os
import sqlite3

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import auditar, get_db, todos, transacao, um
from command_center.providers import estoque, prateleiras

r = APIRouter(prefix="/ops/api/estoque", tags=["estoque"])


def _erro(e):
    """`ErroEstoque` é regra de negócio, não defeito: 400 com a frase pronta para a tela."""
    return HTTPException(400, str(e))


class ContarIn(BaseModel):
    item_id: int
    qty: float
    local: str = estoque.SEDE
    nota: str | None = None
    client_id: int | None = None      # contando a peça de um cliente guardada com a gente


class MoverIn(BaseModel):
    item_id: int
    qty: float | None = None
    unit_id: int | None = None
    local: str = estoque.SEDE
    para: str | None = None
    client_id: int | None = None
    para_cliente_id: int | None = None
    serial: str | None = None
    motivo: str | None = None
    nota: str | None = None


def _gerente(u):
    return bool(u.get("free")) or auth.pode(u.get("role"), "MANAGER")


def _vitrine(i, u):
    """Os campos da prateleira e do preço. **Custo e margem só para gerente**: o mecânico
    vê o preço que vai para o cliente, não quanto a URACE ganha em cima."""
    cat, sugerida = prateleiras.prateleira_de(i)
    out = dict(category=cat, prateleira_sugerida=sugerida, subcategory=i["subcategory"],
               size=i["size"], price=i["price"])
    if _gerente(u):
        out.update(cost=i["cost"], markup=i["markup"])
    return out


def _donos(con):
    """{item_id: [{client_id, cliente, qty}]} — peça de cliente guardada com a gente."""
    out = {}
    for l in todos(con, """SELECT l.item_id, l.client_id, COALESCE(c.pilot_name, c.name) AS cliente,
                                  SUM(l.qty) AS qty
                             FROM stock_levels l JOIN clients c ON c.id = l.client_id
                            WHERE l.qty > 0 GROUP BY l.item_id, l.client_id"""):
        out.setdefault(l["item_id"], []).append(dict(l))
    marcas = ",".join("?" * len(estoque.EM_CASA))
    for l in todos(con, f"""SELECT un.item_id, un.client_id, COALESCE(c.pilot_name, c.name) AS cliente,
                                   COUNT(*) AS qty
                              FROM stock_units un JOIN clients c ON c.id = un.client_id
                             WHERE un.status IN ({marcas}) GROUP BY un.item_id, un.client_id""",
                   estoque.EM_CASA):
        out.setdefault(l["item_id"], []).append(dict(l))
    return out


@r.get("")
def rota_lista(local: str | None = None, con: sqlite3.Connection = Depends(get_db),
               u=Depends(auth.exige("OPERATOR"))):
    """A prateleira: cada item com saldo total, o que é nosso e o que é de cliente."""
    loc = estoque.local(con, local)["id"] if local else None
    mov = estoque.ultimos_movimentos(con)
    donos = _donos(con)
    itens = []
    for i in todos(con, "SELECT * FROM stock_items WHERE active=1 ORDER BY kind, name"):
        total = estoque.saldo(con, i["id"], loc)
        nosso = estoque.saldo(con, i["id"], loc, client_id=None)
        itens.append(dict(
            id=i["id"], name=i["name"], kind=i["kind"], tracking=i["tracking"],
            unit=i["unit"], min_qty=i["min_qty"], sku=i["sku"], supplier_url=i["supplier_url"],
            notes=i["notes"], tem_foto=bool(i["image_path"]),
            total=total, nosso=nosso, de_clientes=round(total - nosso, 4),
            abaixo=bool(i["min_qty"] and nosso < float(i["min_qty"])),
            contado=i["id"] in mov, ultima_contagem=(mov.get(i["id"]) or {}).get("contagem"),
            clientes=donos.get(i["id"], []), **_vitrine(i, u)))
    return {"itens": itens,
            "prateleiras": prateleiras.PRATELEIRAS,
            "gerente": _gerente(u),
            "a_contar": [x["id"] for x in estoque.nunca_contados(con)],
            "locais": [dict(l) for l in todos(con, "SELECT * FROM stock_locations WHERE active=1")],
            "repor": estoque.abaixo_do_minimo(con),
            "divergencias": estoque.conferir(con)}


@r.get("/{item_id}")
def rota_item(item_id: int, con: sqlite3.Connection = Depends(get_db),
              u=Depends(auth.exige("OPERATOR"))):
    """Uma ficha com seu histórico — o razão é o que explica o saldo de hoje."""
    try:
        it = estoque.item(con, item_id)
    except estoque.ErroEstoque as e:
        raise HTTPException(404, str(e))
    movimentos = todos(con, """SELECT m.*, u.name AS quem, lo.name AS de_nome, ld.name AS para_nome
                                 FROM stock_moves m
                                 LEFT JOIN users u ON u.id = m.by_user_id
                                 LEFT JOIN stock_locations lo ON lo.id = m.from_location_id
                                 LEFT JOIN stock_locations ld ON ld.id = m.to_location_id
                                WHERE m.item_id=? ORDER BY m.id DESC LIMIT 100""", (item_id,))
    saldos = todos(con, """SELECT l.*, lo.name AS local, lo.code AS local_code, COALESCE(c.pilot_name, c.name) AS cliente
                             FROM stock_levels l
                             JOIN stock_locations lo ON lo.id = l.location_id
                             LEFT JOIN clients c ON c.id = l.client_id
                            WHERE l.item_id=? AND l.qty <> 0""", (item_id,))
    unidades = todos(con, """SELECT un.*, lo.name AS local, lo.code AS local_code, COALESCE(c.pilot_name, c.name) AS cliente
                               FROM stock_units un
                               LEFT JOIN stock_locations lo ON lo.id = un.location_id
                               LEFT JOIN clients c ON c.id = un.client_id
                              WHERE un.item_id=? ORDER BY un.serial""", (item_id,))
    ficha = dict(it)
    for k in ("cost", "markup"):
        if not _gerente(u):
            ficha.pop(k, None)
    ficha.update(_vitrine(it, u))
    return {"item": ficha, "saldos": [dict(x) for x in saldos],
            "unidades": [dict(x) for x in unidades],
            "movimentos": [dict(x) for x in movimentos],
            "total": estoque.saldo(con, item_id), "nosso": estoque.vendavel(con, item_id)}


def _auditar(con, request, u, evento, item_id, detalhe):
    auditar(con, evento, f"user:{u['id']}", user_id=u["id"], entity_type="stock_item",
            entity_id=item_id, detail=detalhe,
            ip=(request.client.host if request and request.client else None))


@r.post("/contar")
def rota_contar(dados: ContarIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                u=Depends(auth.exige("OPERATOR"))):
    """Contagem física. **Só mexe no item contado** — o que não veio no pedido fica como
    está, porque contagem parcial que zera o resto some com o estoque inteiro."""
    try:
        res = estoque.contar(con, dados.item_id, dados.qty, onde=dados.local, client_id=dados.client_id,
                             by_user_id=u["id"], notes=dados.nota)
    except estoque.ErroEstoque as e:
        raise _erro(e)
    _auditar(con, request, u, "stock.count", dados.item_id,
             {"qty": dados.qty, "local": dados.local, "client_id": dados.client_id, **res})
    con.commit()
    return res


class ContagemIn(BaseModel):
    local: str = estoque.SEDE
    itens: list[ContarIn]


@r.post("/contagem")
def rota_contagem(dados: ContagemIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                  u=Depends(auth.exige("OPERATOR"))):
    """A contagem da prateleira inteira, de uma vez — é o que tira o estoque do zero.

    **Tudo ou nada**: se uma linha não serve (quantidade negativa, item com número de série,
    item que não existe), nenhuma é gravada e a resposta diz qual. Meia contagem gravada
    deixaria o mecânico sem saber o que precisa refazer. Item que **não veio** na lista fica
    como está — em branco é "não contei", não "zero"."""
    if not dados.itens:
        raise HTTPException(400, "Nenhuma quantidade informada.")
    vistos = set()
    for linha in dados.itens:
        if linha.item_id in vistos:
            raise HTTPException(400, "O mesmo item apareceu duas vezes na contagem.")
        vistos.add(linha.item_id)
    resultado = []
    # A conexão é autocommit: sem BEGIN explícito, cada contar() já estaria gravado quando
    # a linha ruim aparecesse, e o "tudo ou nada" seria só promessa.
    try:
        with transacao(con):
            for linha in dados.itens:
                it = estoque.item(con, linha.item_id)
                res = estoque.contar(con, linha.item_id, linha.qty, onde=dados.local,
                                     by_user_id=u["id"], notes=linha.nota or "contagem da prateleira")
                resultado.append({"item_id": linha.item_id, "name": it["name"], **res})
            for x in resultado:
                _auditar(con, request, u, "stock.count", x["item_id"],
                         {"qty": x["depois"], "local": dados.local, "antes": x["antes"],
                          "diferenca": x["diferenca"], "lote": True})
    except estoque.ErroEstoque as e:
        raise _erro(e)
    return {"contados": len(resultado), "local": dados.local,
            "com_diferenca": [x for x in resultado if x["diferenca"]], "itens": resultado}


@r.get("/item/{item_id}/sku-sugestoes")
def rota_sugestoes_sku(item_id: int, con: sqlite3.Connection = Depends(get_db),
                       u=Depends(auth.exige("OPERATOR"))):
    """Produtos do catálogo da Comet que parecem esta peça. A escolha é de gente."""
    from command_center.providers import fornecedor
    try:
        it = estoque.item(con, item_id)
    except estoque.ErroEstoque as e:
        raise HTTPException(404, str(e))
    tem_catalogo = bool(um(con, "SELECT 1 AS x FROM supplier_products WHERE supplier=? LIMIT 1",
                           (it["supplier"] or fornecedor.PADRAO,)))
    return {"item": {"id": it["id"], "name": it["name"], "sku": it["sku"], "supplier_url": it["supplier_url"]},
            "tem_catalogo": tem_catalogo,
            "sugestoes": fornecedor.sugerir_sku(con, it["name"], it["supplier"] or fornecedor.PADRAO)}


class SkuIn(BaseModel):
    sku: str


@r.post("/item/{item_id}/sku")
def rota_ligar_sku(item_id: int, dados: SkuIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                   u=Depends(auth.exige("MANAGER"))):
    """Liga a peça a um produto do catálogo (SKU + link). É **gerente**: o SKU decide o que
    o módulo de compras vai pedir, e casar errado é comprar a peça errada. O nome que a
    equipe deu ao item não muda — é a língua da casa."""
    from command_center.providers import fornecedor
    try:
        it = estoque.item(con, item_id)
    except estoque.ErroEstoque as e:
        raise HTTPException(404, str(e))
    sup = it["supplier"] or fornecedor.PADRAO
    p = um(con, "SELECT sku, name, url FROM supplier_products WHERE supplier=? AND sku=? AND gone_at IS NULL",
           (sup, dados.sku.strip()))
    if not p:
        raise HTTPException(400, "Esse SKU não está no catálogo do fornecedor.")
    antes = {"sku": it["sku"], "supplier_url": it["supplier_url"]}
    con.execute("UPDATE stock_items SET sku=?, supplier_url=? WHERE id=?", (p["sku"], p["url"], item_id))
    _auditar(con, request, u, "stock.item.sku", item_id,
             {"antes": antes, "sku": p["sku"], "produto": p["name"], "url": p["url"]})
    con.commit()
    return {"ok": True, "sku": p["sku"], "supplier_url": p["url"], "produto": p["name"]}


@r.post("/entrada")
def rota_entrada(dados: MoverIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                 u=Depends(auth.exige("OPERATOR"))):
    try:
        res = estoque.entrada(con, dados.item_id, qty=dados.qty, serial=dados.serial,
                              para=dados.local, client_id=dados.client_id,
                              reason=dados.motivo, by_user_id=u["id"], notes=dados.nota)
    except estoque.ErroEstoque as e:
        raise _erro(e)
    _auditar(con, request, u, "stock.in", dados.item_id, {**dados.model_dump(), **res})
    con.commit()
    return res


@r.post("/saida")
def rota_saida(dados: MoverIn, request: Request, con: sqlite3.Connection = Depends(get_db),
               u=Depends(auth.exige("OPERATOR"))):
    """Uso em serviço é do mecânico; **venda é do gerente**, porque mexe em dinheiro."""
    if (dados.motivo or "") == "venda" and not auth.pode(u.get("role"), "MANAGER"):
        raise HTTPException(403, "Venda de peça é do gerente. Para uso em serviço, deixe o motivo.")
    try:
        res = estoque.saida(con, dados.item_id, qty=dados.qty, unit_id=dados.unit_id,
                            de=dados.local, client_id=dados.client_id,
                            para_cliente_id=dados.para_cliente_id,
                            reason=dados.motivo or "uso em serviço",
                            by_user_id=u["id"], notes=dados.nota)
    except estoque.ErroEstoque as e:
        raise _erro(e)
    _auditar(con, request, u, "stock.out", dados.item_id, {**dados.model_dump(), **res})
    con.commit()
    return res


@r.post("/transferir")
def rota_transferir(dados: MoverIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                    u=Depends(auth.exige("OPERATOR"))):
    try:
        res = estoque.transferir(con, dados.item_id, qty=dados.qty, unit_id=dados.unit_id,
                                 de=dados.local, para=dados.para or estoque.TRAILER,
                                 client_id=dados.client_id, by_user_id=u["id"], notes=dados.nota)
    except estoque.ErroEstoque as e:
        raise _erro(e)
    _auditar(con, request, u, "stock.move", dados.item_id, {**dados.model_dump(), **res})
    con.commit()
    return res


@r.post("/ajustar")
def rota_ajustar(dados: MoverIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                 u=Depends(auth.exige("MANAGER"))):
    """Ajuste é de gerente e **exige motivo** — ajuste sem motivo é como um estoque
    deixa de bater sem ninguém perceber."""
    try:
        res = estoque.ajustar(con, dados.item_id, dados.qty or 0, onde=dados.local,
                              client_id=dados.client_id, reason=dados.motivo,
                              by_user_id=u["id"], notes=dados.nota)
    except estoque.ErroEstoque as e:
        raise _erro(e)
    _auditar(con, request, u, "stock.adjust", dados.item_id, {**dados.model_dump(), **res})
    con.commit()
    return res


TIPOS_IMAGEM = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
IMAGEM_MAX = 6 * 1024 * 1024        # foto de celular moderno passa fácil de 4 MB


def _pasta_fotos():
    caminho = os.path.join(os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "estoque")
    os.makedirs(caminho, exist_ok=True)
    return caminho


@r.post("/item")
async def rota_criar_item(request: Request, con: sqlite3.Connection = Depends(get_db),
                          u=Depends(auth.exige("OPERATOR")),
                          name: str = Form(...), kind: str | None = Form(None),
                          unit: str | None = Form(None), notes: str | None = Form(None),
                          sku: str | None = Form(None), min_qty: float | None = Form(None),
                          qty: float | None = Form(None), local: str = Form(estoque.SEDE),
                          category: str | None = Form(None), subcategory: str | None = Form(None),
                          size: str | None = Form(None), cost: str | None = Form(None),
                          markup: str | None = Form(None), price: str | None = Form(None),
                          client_id: int | None = Form(None), serial: str | None = Form(None),
                          foto: UploadFile | None = File(None)):
    """O botão "Adicionar" do mecânico: nome, descrição, quantidade e foto.

    A **quantidade entra como contagem**, não como compra: ele está dizendo "tem isto
    aqui agora". Chamar isso de entrada seria inventar uma compra que não houve, e o
    razão ficaria contando uma história falsa.

    Se a foto falhar, a peça **continua cadastrada**: perder o cadastro inteiro porque a
    imagem não subiu seria trocar o que importa pelo enfeite.
    """
    if any((v or "").strip() for v in (cost, markup, price)) and not _gerente(u):
        raise HTTPException(403, "Valor de compra, margem e preço final são do gerente. "
                                 "Cadastre a peça sem eles; o gerente completa depois.")
    prat = prateleiras.POR_CODIGO.get(category or "")
    kind = kind or (prat["kind"] if prat else "peca")
    unit = unit or (prat["unit"] if prat else "un")
    seriais = [x.strip() for x in (serial or "").replace(",", "\n").splitlines() if x.strip()]
    contado, unidades = None, []
    # Tudo numa transação: peça cadastrada pela metade (ficha sem a quantidade, ou com
    # dois dos três números de série) é pior do que peça nenhuma — ninguém percebe.
    try:
        with transacao(con):
            iid = estoque.criar_item(con, kind, name, sku=sku or None, unit=unit,
                                     min_qty=min_qty, notes=notes, category=category,
                                     subcategory=subcategory, size=size, cost=cost,
                                     markup=markup, price=price)
            if qty is not None:
                contado = estoque.contar(con, iid, qty, onde=local, client_id=client_id,
                                         by_user_id=u["id"], notes="quantidade informada no cadastro")
            for sn in seriais:
                unidades.append(estoque.entrada(con, iid, serial=sn, para=local, client_id=client_id,
                                                reason="cadastro (já estava com a gente)",
                                                by_user_id=u["id"]))
    except estoque.ErroEstoque as e:
        raise _erro(e)

    aviso = None
    if foto is not None and getattr(foto, "filename", None):
        ext = TIPOS_IMAGEM.get((foto.content_type or "").lower())
        if not ext:
            aviso = "A peça foi cadastrada, mas a foto não: use PNG, JPG ou WEBP."
        else:
            dados_foto = await foto.read(IMAGEM_MAX + 1)
            if len(dados_foto) > IMAGEM_MAX:
                aviso = "A peça foi cadastrada, mas a foto é grande demais (máximo 6 MB)."
            else:
                nome_arq = f"item-{iid}{ext}"
                with open(os.path.join(_pasta_fotos(), nome_arq), "wb") as f:
                    f.write(dados_foto)
                con.execute("UPDATE stock_items SET image_path=? WHERE id=?", (nome_arq, iid))

    _auditar(con, request, u, "stock.item.create", iid,
             {"name": name, "kind": kind, "qty": qty, "category": category, "client_id": client_id,
              "seriais": seriais, "com_preco": price is not None or cost is not None,
              "com_foto": bool(aviso is None and foto and getattr(foto, "filename", None))})
    con.commit()
    return {"id": iid, "contado": contado, "unidades": unidades, "aviso": aviso}


class EditarIn(BaseModel):
    model_config = {"extra": "forbid"}
    name: str | None = None
    notes: str | None = None
    unit: str | None = None
    min_qty: float | None = None
    category: str | None = None
    subcategory: str | None = None
    size: str | None = None
    cost: float | None = None
    markup: str | None = None
    price: float | None = None


@r.patch("/item/{item_id}")
def rota_editar(item_id: int, dados: EditarIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                u=Depends(auth.exige("OPERATOR"))):
    """Editar a ficha: nome, descrição, prateleira, medida — do mecânico. Valor de compra,
    margem e preço final — do gerente. Só o que veio no pedido muda."""
    campos = dados.model_dump(exclude_unset=True)
    if set(campos) & set(estoque.DE_PRECO) and not _gerente(u):
        raise HTTPException(403, "Valor de compra, margem e preço final são do gerente.")
    try:
        estoque.item(con, item_id)
    except estoque.ErroEstoque as e:
        raise HTTPException(404, str(e))
    try:
        mudou = estoque.atualizar_item(con, item_id, **campos)
    except estoque.ErroEstoque as e:
        raise _erro(e)
    if mudou:
        _auditar(con, request, u, "stock.item.edit", item_id,
                 {k: {"antes": a, "depois": d} for k, (a, d) in mudou.items()})
    con.commit()
    it = estoque.item(con, item_id)
    return {"ok": True, "mudou": sorted(mudou), **_vitrine(it, u)}


class DonoIn(BaseModel):
    item_id: int
    client_id: int
    qty: float | None = None
    unit_id: int | None = None
    local: str = estoque.SEDE
    nota: str | None = None


@r.post("/assinalar")
def rota_assinalar(dados: DonoIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                   u=Depends(auth.exige("OPERATOR"))):
    """Assinalar peça da URACE para um cliente — o pneu dele guardado com a gente.
    É do mecânico: é ele quem separa na prateleira, e o histórico diz quem fez."""
    try:
        with transacao(con):
            res = estoque.trocar_dono(con, dados.item_id, para_cliente_id=dados.client_id, qty=dados.qty,
                                      unit_id=dados.unit_id, onde=dados.local, by_user_id=u["id"],
                                      notes=dados.nota)
            _auditar(con, request, u, "stock.assign", dados.item_id, {**dados.model_dump(), **res})
    except estoque.ErroEstoque as e:
        raise _erro(e)
    return res


@r.post("/devolver")
def rota_devolver(dados: DonoIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                  u=Depends(auth.exige("MANAGER"))):
    """A peça do cliente volta a ser da URACE (assinalada por engano, ou ele vendeu para
    nós). É do **gerente**: transforma o que era dos outros em algo que a casa pode vender."""
    try:
        with transacao(con):
            res = estoque.trocar_dono(con, dados.item_id, de_cliente_id=dados.client_id, qty=dados.qty,
                                      unit_id=dados.unit_id, onde=dados.local, by_user_id=u["id"],
                                      notes=dados.nota)
            _auditar(con, request, u, "stock.unassign", dados.item_id, {**dados.model_dump(), **res})
    except estoque.ErroEstoque as e:
        raise _erro(e)
    return res


@r.post("/item/{item_id}/foto")
async def rota_foto(item_id: int, request: Request, foto: UploadFile = File(...),
                    con: sqlite3.Connection = Depends(get_db),
                    u=Depends(auth.exige("OPERATOR"))):
    """Trocar a foto de uma peça já cadastrada."""
    try:
        estoque.item(con, item_id)
    except estoque.ErroEstoque as e:
        raise HTTPException(404, str(e))
    ext = TIPOS_IMAGEM.get((foto.content_type or "").lower())
    if not ext:
        raise HTTPException(400, "Use PNG, JPG ou WEBP.")
    dados = await foto.read(IMAGEM_MAX + 1)
    if len(dados) > IMAGEM_MAX:
        raise HTTPException(400, "Foto grande demais (máximo 6 MB).")
    nome = f"item-{item_id}{ext}"
    with open(os.path.join(_pasta_fotos(), nome), "wb") as f:
        f.write(dados)
    con.execute("UPDATE stock_items SET image_path=? WHERE id=?", (nome, item_id))
    _auditar(con, request, u, "stock.item.photo", item_id, {"arquivo": nome})
    con.commit()
    return {"ok": True}


@r.get("/item/{item_id}/foto")
def rota_ver_foto(item_id: int, con: sqlite3.Connection = Depends(get_db),
                  u=Depends(auth.exige("OPERATOR"))):
    """A foto sai pelo servidor, com sessão — nunca por link público adivinhável."""
    it = um(con, "SELECT image_path FROM stock_items WHERE id=?", (item_id,))
    if not it or not it["image_path"]:
        raise HTTPException(404)
    caminho = os.path.join(_pasta_fotos(), os.path.basename(it["image_path"]))
    if not os.path.isfile(caminho):
        raise HTTPException(404)
    from fastapi.responses import FileResponse
    return FileResponse(caminho, headers={"Cache-Control": "private, max-age=300"})


@r.get("/cliente/{client_id}")
def rota_do_cliente(client_id: int, con: sqlite3.Connection = Depends(get_db),
                    u=Depends(auth.exige("OPERATOR"))):
    """O que é do cliente e está com a gente — para aparecer no card dele."""
    return estoque.do_cliente(con, client_id)

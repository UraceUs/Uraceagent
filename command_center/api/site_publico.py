"""Site público, visto de dentro (#41, #42): a agenda de sessões e, depois, as contas de
clientes. Quem abre e fecha a agenda é o gerente; confirmar e recusar pedido é da operação."""
import sqlite3
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Path, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field

from command_center.api import auth
from command_center.db import auditar, get_db, todos, transacao
from command_center.providers import agenda_asana, agenda_sessoes as ag, cartoes_site as cs, contrato, loja, servicos_site as sv, vinculo_site as vs

r = APIRouter(prefix="/ops/api/site", tags=["site"])


def _aud(con, request, u, evento, eid, detalhe):
    auditar(con, evento, f"user:{u['id']}", user_id=u["id"], entity_type="booking", entity_id=eid, detail=detalhe,
            ip=auth._ip(request))


def _d(v):
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        raise HTTPException(400, "data inválida (AAAA-MM-DD)")


@r.get("/agenda")
def ver_agenda(de: str | None = None, ate: str | None = None, con: sqlite3.Connection = Depends(get_db),
               u=Depends(auth.exige("OPERATOR"))):
    """Visão da equipe: o mês inteiro, com o porquê de cada período fechado e a ocupação."""
    try:
        disp = ag.disponibilidade(con, _d(de), _d(ate), visao="equipe")
    except ag.ErroAgenda as e:
        raise HTTPException(400, str(e))
    corridas = []
    if disp["dias"]:
        de_, ate_ = disp["dias"][0]["date"], disp["dias"][-1]["date"]
        corridas = todos(con, """SELECT id, name, series, track, city, date_start, COALESCE(date_end, date_start) AS date_end
                                   FROM races WHERE active=1 AND date_start IS NOT NULL AND date_start<=?
                                    AND COALESCE(date_end, date_start)>=? ORDER BY date_start""", (ate_, de_))
    return {**disp, "semana": ag.semana(con), "bloqueios": ag.bloqueios(con), "config_completa": ag.config(con),
            "corridas": corridas}


class ConfigIn(BaseModel):
    morning_start: str | None = None
    morning_end: str | None = None
    afternoon_start: str | None = None
    afternoon_end: str | None = None
    auto_confirm: bool | None = None
    auto_sell: bool | None = None          # #164: venda automática (só ADMIN ou o acesso livre liga ou desliga)
    horizon_days: int | None = None
    min_notice_hours: int | None = None


@r.patch("/agenda/config")
def mudar_config(dados: ConfigIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    if dados.auto_sell is not None and not (u.get("free") or u["role"] == "ADMIN"):
        raise HTTPException(403, "Só o administrador liga ou desliga a venda automática.")
    try:
        cfg = ag.mudar_config(con, u["id"], **dados.model_dump(exclude_unset=True))
    except ag.ErroAgenda as e:
        raise HTTPException(400, str(e))
    _aud(con, request, u, "booking.config", None, dados.model_dump(exclude_unset=True))
    con.commit()
    return cfg


class RegraIn(BaseModel):
    weekday: int
    period: str
    open: bool
    capacity: int = 1


@r.put("/agenda/semana")
def mudar_semana(regras: list[RegraIn], request: Request, con: sqlite3.Connection = Depends(get_db),
                 u=Depends(auth.exige("MANAGER"))):
    try:
        with transacao(con):
            s = ag.mudar_semana(con, [x.model_dump() for x in regras])
            _aud(con, request, u, "booking.week", None, {"regras": [x.model_dump() for x in regras]})
    except ag.ErroAgenda as e:
        raise HTTPException(400, str(e))
    return s


class BloqueioIn(BaseModel):
    date_from: str | None = None
    date_to: str | None = None
    period: str = "dia"
    reason: str | None = None
    weekday: int | None = None             # recorrente: 0 = segunda


@r.post("/agenda/bloqueios", status_code=201)
def bloquear(dados: BloqueioIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    try:
        bid = ag.bloquear(con, u["id"], **dados.model_dump())
    except ag.ErroAgenda as e:
        raise HTTPException(400, str(e))
    _aud(con, request, u, "booking.block", bid, dados.model_dump())
    con.commit()
    return {"id": bid}


@r.post("/agenda/bloqueios/{bid}/remover")
def desbloquear(bid: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    try:
        ag.desbloquear(con, u["id"], bid)
    except ag.ErroAgenda as e:
        raise HTTPException(404, str(e))
    _aud(con, request, u, "booking.unblock", bid, {})
    con.commit()
    return {"ok": True}


@r.get("/agendamentos")
def agendamentos(status: str | None = None, de: str | None = None, ate: str | None = None,
                 con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    lista = ag.lista(con, status or None, de, ate)
    from command_center.providers import cobranca_agenda
    for a in lista:                          # contrato mensal: só a equipe vê (#61)
        a["contrato"] = contrato.situacao_do_agendamento(con, a["client_id"], a["date"], a)
        a["cobranca"] = cobranca_agenda.situacao(con, a) if a.get("accepted_at") else None
    return {"agendamentos": lista}


class DecisaoIn(BaseModel):
    nota: str | None = None


@r.post("/agendamentos/{bid}/{decisao}")
def decidir(bid: int, decisao: str, dados: DecisaoIn, request: Request, tarefas: BackgroundTasks,
            con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    if decisao not in ("aceitar", "confirmar", "recusar", "cancelar"):
        raise HTTPException(404, "decisão desconhecida")
    if decisao == "confirmar" and not (u.get("free") or auth.pode(u["role"], "MANAGER")):
        # #50: confirmar sem esperar pagamento e waiver é decisão do gerente; a equipe aceita a vaga
        raise HTTPException(403, "Confirmar sem esperar pagamento e waiver é do gerente. Use Aceitar.")
    try:
        if decisao == "aceitar":
            from command_center.providers import cobranca_agenda
            res = cobranca_agenda.aceitar(con, u["id"], bid)
            novo = res["status"]
        else:
            novo = ag.decidir(con, u["id"], bid, decisao, dados.nota)
            res = None
    except ag.ErroAgenda as e:
        raise HTTPException(400, str(e))
    _aud(con, request, u, f"booking.{decisao}", bid, {"nota": dados.nota, **({"cobranca": res} if res else {})})
    con.commit()
    tarefas.add_task(agenda_asana.levar, bid)      # #67: a situação nova vai para a tarefa do Asana
    return {"status": novo, "cobranca": res}


# ------------------------------------------------------------------ serviços e preços (#50)
@r.get("/servicos")
def servicos(con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    return {"servicos": sv.lista(con), "itens_qbo": sv.itens_qbo(con)}


class ServicoIn(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | str | None = None
    qbo_item_id: str | None = None
    qbo_item: str | None = None             # texto livre: o nome de um item, ou o texto da linha (#61)
    deposit: float | str | None = None      # #50: depósito por sessão; vazio ou 0 = sem depósito
    deposit_required: bool | None = None    # #317: marcado, a sessão nunca sai sem o depósito
    site_kart: str | None = None            # #263: o kart do site que este serviço vende (chave de conteudo.KARTS); #297: ou um kart novo
    site_title: str | None = None           # #297: o cartão do kart no site — nome, linha de baixo, aviso, kart próprio
    site_subtitle: str | None = None
    site_note: str | None = None
    own_kart: bool | None = None
    kind: str | None = None                 # #169: session (avulsa) | plan (mensal: price é por mês)
    months: int | str | None = None         # #169: meses do compromisso do plano
    sessions_month: int | str | None = None # #169: sessões por mês que o plano dá (vira o contrato do card)
    extra_price: float | str | None = None  # #314: o valor da sessão extra do plano (vazio: mensal ÷ sessões)
    extra_item: str | None = None           # #314: o item do QuickBooks da sessão extra do plano (pelo nome)
    active: bool | None = None
    sort: int | None = None


@r.post("/servicos", status_code=201)
def criar_servico(dados: ServicoIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                  u=Depends(auth.exige("MANAGER"))):
    try:
        sid = sv.criar(con, u["id"], dados.model_dump(exclude_unset=True))
    except sv.ErroServico as e:
        raise HTTPException(400, str(e))
    auditar(con, "booking.service.create", f"user:{u['id']}", user_id=u["id"], entity_type="booking_service", entity_id=sid,
            detail=dados.model_dump(exclude_unset=True), ip=auth._ip(request))
    con.commit()
    return {"id": sid, "servicos": sv.lista(con)}


@r.patch("/servicos/{sid}")
def mudar_servico(sid: int, dados: ServicoIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                  u=Depends(auth.exige("MANAGER"))):
    """Mudar o preço vale para os próximos agendamentos; quem já marcou fica com o valor do dia."""
    try:
        mud = sv.mudar(con, u["id"], sid, dados.model_dump(exclude_unset=True))
    except sv.ErroServico as e:
        raise HTTPException(404 if "não existe" in str(e) else 400, str(e))
    if mud:
        auditar(con, "booking.service.update", f"user:{u['id']}", user_id=u["id"], entity_type="booking_service",
                entity_id=sid, detail={k: {"antes": a, "depois": d} for k, (a, d) in mud.items()}, ip=auth._ip(request))
    con.commit()
    return {"servicos": sv.lista(con)}


# ------------------------------------------------------------------ cartões das páginas (#297, parte 2)
@r.get("/cartoes")
def cartoes(con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """Os cartões de preço das páginas do site (Academy, Pro Team, For Beginners), na ordem de cada página."""
    return {"cartoes": cs.lista(con), "paginas": cs.PAGINAS, "preco_kart": cs.preco_kart(con)}


class CartaoIn(BaseModel):
    page: str | None = None
    grp: str | None = None
    title: str | None = None
    subtitle: str | None = None
    body: str | None = None
    price: str | None = None                # texto do cartão; {kart}, {academy}, {boost} viram o valor do painel
    per: str | None = None
    link: str | None = None
    button: str | None = None
    active: bool | None = None
    sort: int | None = None


@r.post("/cartoes", status_code=201)
def criar_cartao(dados: CartaoIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                 u=Depends(auth.exige("MANAGER"))):
    try:
        cid = cs.criar(con, u["id"], dados.model_dump(exclude_unset=True))
    except cs.ErroCartao as e:
        raise HTTPException(400, str(e))
    auditar(con, "site.card.create", f"user:{u['id']}", user_id=u["id"], entity_type="site_offer", entity_id=cid,
            detail=dados.model_dump(exclude_unset=True), ip=auth._ip(request))
    con.commit()
    return {"id": cid, "cartoes": cs.lista(con)}


@r.patch("/cartoes/{cid}")
def mudar_cartao(cid: int, dados: CartaoIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                 u=Depends(auth.exige("MANAGER"))):
    """Esconder não apaga: o cartão sai da página e continua no painel para voltar."""
    try:
        mud = cs.mudar(con, u["id"], cid, dados.model_dump(exclude_unset=True))
    except cs.ErroCartao as e:
        raise HTTPException(404 if "não existe" in str(e) else 400, str(e))
    if mud:
        auditar(con, "site.card.update", f"user:{u['id']}", user_id=u["id"], entity_type="site_offer", entity_id=cid,
                detail={k: {"antes": a, "depois": d} for k, (a, d) in mud.items()}, ip=auth._ip(request))
    con.commit()
    return {"cartoes": cs.lista(con)}


# ------------------------------------------------------------------ produtos da loja (#298)
@r.get("/produtos")
def produtos(q: str = "", categoria: str | None = None, estado: str | None = None,
             limit: int = Query(30, ge=1, le=200), offset: int = Query(0, ge=0),
             con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """Os produtos da loja (do banco), paginados no servidor: busca, categoria, ativos ou escondidos."""
    ativos = {"ativos": True, "escondidos": False}.get(estado or "")
    return {**loja.lista(con, q, categoria, ativos, limit, offset), "categorias": loja.categorias()}


@r.get("/produtos/{pid}")
def produto(pid: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    p = loja.do_painel(con, pid)
    if not p:
        raise HTTPException(404, "produto não existe")
    return {"produto": {**p, "categorias_loja": loja.categorias_da_loja(p)}, "categorias": loja.categorias()}


class VariacaoIn(BaseModel):
    attrs: list[str] = []
    regular: float | str | None = None      # o preço cheio da opção
    promo: float | str | None = None        # o promocional (vazio: sem promoção)
    in_stock: bool = True
    # #309 (revisão): o nome que a opção tinha quando a tela abriu (null na opção nova). Renomear a opção ligada ao
    # estoque leva a ligação junto; sem isto, a opção renomeada venderia sem limite.
    antes: str | None = Field(None, max_length=400)


class FotoIn(BaseModel):
    src: str
    alt: str | None = None


class ProdutoIn(BaseModel):
    name: str | None = None
    slug: str | None = None                 # só na criação: o endereço /store/p/<slug>/ não muda depois
    regular: float | str | None = None      # "Preço"
    promo: float | str | None = None        # "Preço promocional" (vazio: sem promoção)
    short: str | None = None
    description: str | None = None
    images: list[FotoIn] | None = None      # a ordem: a primeira é a da loja
    categories: list[str] | None = None
    attribute_names: list[str] | None = None
    variations: list[VariacaoIn] | None = None
    in_stock: bool | None = None
    sku: str | None = None
    shipping_fee: float | str | None = None  # frete fixo por unidade com "Ship to me"; vazio = combinar à parte
    deposit: float | str | None = None       # depósito de segurança por unidade; vazio ou 0 = sem
    fulfillment: str | None = None           # #309: dropshipping | estoque (interno: o cliente nunca vê)
    active: bool | None = None
    sort: int | None = None


def _produto_in(dados):
    return dados.model_dump(exclude_unset=True)


@r.post("/produtos", status_code=201)
def criar_produto(dados: ProdutoIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                  u=Depends(auth.exige("MANAGER"))):
    try:
        pid = loja.criar(con, u["id"], _produto_in(dados))
    except loja.ErroProduto as e:
        raise HTTPException(400, str(e))
    auditar(con, "store.product.create", f"user:{u['id']}", user_id=u["id"], entity_type="store_product", entity_id=pid,
            detail={k: v for k, v in _produto_in(dados).items() if k not in ("short", "description")}, ip=auth._ip(request))
    con.commit()
    return {"id": pid, "produto": loja.do_painel(con, pid)}


@r.patch("/produtos/{pid}")
def mudar_produto(pid: int, dados: ProdutoIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                  u=Depends(auth.exige("MANAGER"))):
    """Mudar o preço ou o frete vale para as próximas compras; o pedido já feito fica com o valor do dia.
    Esconder não apaga: o produto sai da loja e continua aqui para voltar."""
    d = _produto_in(dados)
    d.pop("slug", None)
    try:
        with transacao(con):        # #309: o produto e a ligação da opção renomeada com o estoque, juntos ou nenhum
            mud = loja.mudar(con, u["id"], pid, d)
            if mud:
                auditar(con, "store.product.update", f"user:{u['id']}", user_id=u["id"], entity_type="store_product",
                        entity_id=pid, detail={k: {"antes": a, "depois": v} for k, (a, v) in mud.items()}, ip=auth._ip(request))
    except loja.ErroProduto as e:
        raise HTTPException(404 if "não existe" in str(e) else 400, str(e))
    return {"produto": loja.do_painel(con, pid)}


FOTO_MAX = 12 * 1024 * 1024


@r.post("/produtos/{pid}/fotos", status_code=201)
async def subir_foto(pid: int, request: Request, arquivo: UploadFile = File(...), alt: str = Form(""),
                     con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    """Foto do celular ou do computador: vira WebP de até 1600 px, sem EXIF (sem a posição GPS), e entra no fim."""
    dados = await arquivo.read(FOTO_MAX + 1)
    if not dados or len(dados) > FOTO_MAX:
        raise HTTPException(400, "foto vazia ou maior que 12 MB")
    try:
        fotos = loja.guardar_foto(con, u["id"], pid, dados, alt)
    except loja.ErroProduto as e:
        raise HTTPException(404 if "não existe" in str(e) else 400, str(e))
    auditar(con, "store.product.photo", f"user:{u['id']}", user_id=u["id"], entity_type="store_product", entity_id=pid,
            detail={"fotos": len(fotos)}, ip=auth._ip(request))
    con.commit()
    return {"produto": loja.do_painel(con, pid)}


# ------------------------------------------------------------------ estoque do site (#309)
@r.get("/estoque")
def estoque_do_site(q: str = Query("", max_length=80), modo: str = "todos", limit: int = Query(20, ge=1, le=100),
                    offset: int = Query(0, ge=0), con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """Cada produto da loja com o marcador (dropshipping ou em estoque), o item do estoque ligado a ele (ou a cada
    opção) e quanto tem no Galpão + Pista. Paginado no servidor; os filtros contam cada grupo."""
    from command_center.providers import estoque_site
    try:
        return estoque_site.lista(con, q, modo, limit, offset)
    except loja.ErroProduto as e:
        raise HTTPException(400, str(e))


@r.get("/estoque/itens")
def estoque_itens(q: str = Query("", max_length=80), produto: int | None = Query(None, ge=1, le=2**63 - 1),
                  limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0),
                  con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """Os itens do estoque interno para ligar: a busca pelo nome; sem busca, os parecidos com o nome do produto."""
    from command_center.providers import estoque_site
    return estoque_site.itens(con, q, produto, limit, offset)


class NovoItemIn(BaseModel):
    name: str | None = Field(None, max_length=120)
    kind: str | None = None                 # peca | pneu (quantidade; vazio: pela prateleira); kart e motor entram pelo Estoque
    category: str | None = Field(None, max_length=40)
    size: str | None = Field(None, max_length=60)
    price: float | str | None = None        # o preço final do Balcão (o da loja fica no produto)


class LigarIn(BaseModel):
    variacao: str = Field("", max_length=200)
    item_id: int | None = Field(None, ge=1, le=2**63 - 1)
    criar: NovoItemIn | None = None
    contagem: float | str | None = None     # quanto tem agora (obrigatório no item de quantidade)
    local: str | None = None                # sede (Galpão) | pista


def _aud_estoque(con, request, u, evento, pid, detalhe):
    auditar(con, evento, f"user:{u['id']}", user_id=u["id"], entity_type="store_product", entity_id=pid, detail=detalhe,
            ip=auth._ip(request))


@r.post("/estoque/{pid}/ligar", status_code=201)
def ligar_estoque(dados: LigarIn, request: Request, pid: int = Path(..., ge=1, le=2**63 - 1),
                  con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    """Liga o produto (ou a opção) a um item do estoque, que já existe ou nasce do produto, com a contagem de agora.
    O produto passa a "em estoque": o site vende pelo saldo, e a venda paga sai do estoque."""
    from command_center.providers import estoque_site
    try:
        with transacao(con):
            res = estoque_site.ligar(con, u["id"], pid, dados.variacao, dados.item_id,
                                     dados.criar.model_dump() if dados.criar else None, dados.contagem, dados.local)
            _aud_estoque(con, request, u, "store.stock.link", pid, res)
    except loja.ErroProduto as e:
        raise HTTPException(404 if "não existe" in str(e) else 400, str(e))
    return {"ok": True, **res}


@r.delete("/estoque/{pid}/ligar")
def desligar_estoque(request: Request, pid: int = Path(..., ge=1, le=2**63 - 1), variacao: str = Query("", max_length=200),
                     con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    """Tira a ligação. O item continua no estoque com o saldo e o histórico; a venda deixa de baixar dele."""
    from command_center.providers import estoque_site
    try:
        with transacao(con):
            res = estoque_site.desligar(con, u["id"], pid, variacao)
            _aud_estoque(con, request, u, "store.stock.unlink", pid, res)
    except loja.ErroProduto as e:
        raise HTTPException(404 if "não existe" in str(e) else 400, str(e))
    return {"ok": True, **res}


class ContarSiteIn(BaseModel):
    variacao: str = Field("", max_length=200)
    qty: float | str
    local: str | None = None
    nota: str | None = Field(None, max_length=300)


@r.post("/estoque/{pid}/contar")
def contar_estoque(dados: ContarSiteIn, request: Request, pid: int = Path(..., ge=1, le=2**63 - 1),
                   con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """A contagem do item ligado (a mesma regra do Estoque: contar é do operador, e a diferença fica no razão)."""
    from command_center.providers import estoque_site
    try:
        with transacao(con):
            res = estoque_site.contar(con, u["id"], pid, dados.variacao, dados.qty, dados.local, dados.nota)
            _aud_estoque(con, request, u, "store.stock.count", pid, res)
    except loja.ErroProduto as e:
        raise HTTPException(404 if "não existe" in str(e) else 400, str(e))
    return {"ok": True, **res}


# ------------------------------------------------------------------ contas do site (#42)
@r.get("/contas")
def contas(filtro: str = "sem_vinculo", con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    if filtro not in ("sem_vinculo", "vinculadas", "todas"):
        raise HTTPException(400, "filtro inválido")
    return {"contas": vs.contas(con, filtro)}


class VincularIn(BaseModel):
    client_id: int


@r.post("/contas/{conta_id}/vincular")
def vincular(conta_id: int, dados: VincularIn, request: Request, con: sqlite3.Connection = Depends(get_db),
             u=Depends(auth.exige("OPERATOR"))):
    """Uma pessoa confirma: é o vínculo que abre para o cliente o histórico daquele card."""
    try:
        res = vs.vincular(con, conta_id, dados.client_id, u["id"])
    except vs.ErroVinculo as e:
        raise HTTPException(400, str(e))
    auditar(con, "portal.link", f"user:{u['id']}", user_id=u["id"], entity_type="portal_account", entity_id=conta_id,
            detail=res, ip=auth._ip(request))
    con.commit()
    return {"ok": True}


@r.post("/contas/{conta_id}/criar-cliente", status_code=201)
def criar_cliente(conta_id: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """Cliente novo, que não existe no site interno: o card nasce com os dados da conta e já
    fica vinculado (#52). Se já existe alguém com o mesmo e-mail ou telefone, recusa."""
    try:
        with transacao(con):
            cid = vs.criar_cliente(con, conta_id, u["id"])
            auditar(con, "portal.client.create", f"user:{u['id']}", user_id=u["id"], entity_type="portal_account",
                    entity_id=conta_id, detail={"client_id": cid}, ip=auth._ip(request))
    except vs.ErroVinculo as e:
        raise HTTPException(400, str(e))
    return {"client_id": cid}


@r.post("/contas/{conta_id}/desvincular")
def desvincular(conta_id: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    try:
        res = vs.desvincular(con, conta_id)
    except vs.ErroVinculo as e:
        raise HTTPException(404, str(e))
    auditar(con, "portal.unlink", f"user:{u['id']}", user_id=u["id"], entity_type="portal_account", entity_id=conta_id,
            detail=res, ip=auth._ip(request))
    con.commit()
    return {"ok": True}


# ------------------------------------------------------------------ um card por driver (#65)
@r.post("/drivers/{pilot_id}/vincular")
def vincular_driver(pilot_id: int, dados: VincularIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                    u=Depends(auth.exige("OPERATOR"))):
    """Cada driver tem o seu card (Client ID). Uma pessoa confirma qual."""
    try:
        res = vs.vincular_driver(con, pilot_id, dados.client_id, u["id"])
    except vs.ErroVinculo as e:
        raise HTTPException(400, str(e))
    auditar(con, "portal.driver.link", f"user:{u['id']}", user_id=u["id"], entity_type="portal_pilot", entity_id=pilot_id,
            detail=res, ip=auth._ip(request))
    con.commit()
    return {"ok": True}


@r.post("/drivers/{pilot_id}/criar-cliente", status_code=201)
def criar_cliente_driver(pilot_id: int, request: Request, con: sqlite3.Connection = Depends(get_db),
                         u=Depends(auth.exige("OPERATOR"))):
    """Card novo para o driver: o responsável e o contato da conta, o piloto é o driver."""
    try:
        with transacao(con):
            cid = vs.criar_cliente_driver(con, pilot_id, u["id"])
            auditar(con, "portal.driver.client.create", f"user:{u['id']}", user_id=u["id"], entity_type="portal_pilot",
                    entity_id=pilot_id, detail={"client_id": cid}, ip=auth._ip(request))
    except vs.ErroVinculo as e:
        raise HTTPException(400, str(e))
    return {"client_id": cid}


@r.post("/drivers/{pilot_id}/desvincular")
def desvincular_driver(pilot_id: int, request: Request, con: sqlite3.Connection = Depends(get_db),
                       u=Depends(auth.exige("MANAGER"))):
    try:
        res = vs.desvincular_driver(con, pilot_id)
    except vs.ErroVinculo as e:
        raise HTTPException(404, str(e))
    auditar(con, "portal.driver.unlink", f"user:{u['id']}", user_id=u["id"], entity_type="portal_pilot", entity_id=pilot_id,
            detail=res, ip=auth._ip(request))
    con.commit()
    return {"ok": True}


@r.get("/contas/do-cliente/{client_id}")
def do_cliente(client_id: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    return {"conta": vs.conta_do_cliente(con, client_id)}


# ------------------------------------------------------------------ pedidos do site (#236, #245)
@r.get("/pedidos")
def pedidos(status: str | None = None, limit: int = Query(30, ge=1, le=200), offset: int = Query(0, ge=0),
            con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """Os pedidos do carrinho e da loja em todo estado (pago, processando, falhou, expirou, no checkout),
    paginados, cada um com o link da página do pedido para a equipe mandar ao cliente."""
    from command_center.providers import pedido_site
    return pedido_site.lista(con, status, limit, offset)


@r.post("/pedidos/{oid}/estoque-resolvido")
def estoque_resolvido(request: Request, oid: int = Path(..., ge=1, le=2**63 - 1), con: sqlite3.Connection = Depends(get_db),
                      u=Depends(auth.exige("OPERATOR"))):
    """#309 (revisão): o "Resolver: sem estoque" do pedido pago foi resolvido (a equipe separou o que tinha, combinou
    com o cliente ou devolveu pelo Stripe). Sai do "Resolver" do pedido e do "Pagos sem estoque" do Painel do site; a
    frase fica na linha e na auditoria."""
    from command_center.providers import estoque_site
    try:
        with transacao(con):
            res = estoque_site.resolver(con, oid, u["id"])
            auditar(con, "store.stock.resolved", f"user:{u['id']}", user_id=u["id"], entity_type="store_order", entity_id=oid,
                    detail=res, ip=auth._ip(request))
    except loja.ErroProduto as e:
        raise HTTPException(404 if "não existe" in str(e) else 400, str(e))
    return {"ok": True, **res}


# ------------------------------------------------------------------ security deposit (#317)
@r.get("/depositos")
def depositos(estado: str = "retidos", q: str = Query("", max_length=120), limit: int = Query(30, ge=1, le=200), offset: int = Query(0, ge=0),
              con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """Cada depósito de segurança cobrado no site (pedido pago), com o que já foi devolvido e o que segue retido."""
    from command_center.providers import deposito_site as dep
    try:
        return {**dep.lista(con, estado, q, limit, offset), "modo_teste": dep.modo_teste()}
    except dep.ErroDeposito as e:
        raise HTTPException(400, str(e))


@r.get("/depositos/valores")
def depositos_valores(con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    from command_center.providers import deposito_site as dep
    return dep.valores(con)


class ReembolsoIn(BaseModel):
    item_id: int | None = Field(None, ge=1, le=2**63 - 1)   # a linha do carrinho; vazio = o depósito do pedido ("Buy now")
    valor: float | str
    nota: str | None = Field(None, max_length=1000)


@r.post("/depositos/{oid}/reembolsar")
def reembolsar_deposito(dados: ReembolsoIn, request: Request, oid: int = Path(..., ge=1, le=2**63 - 1),
                        con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    """Devolve o valor escolhido do depósito pelo Stripe. Parcial vale; nunca mais que o que segue retido."""
    from command_center.providers import deposito_site as dep
    try:
        res = dep.reembolsar(con, u["id"], oid, dados.item_id, dados.valor, dados.nota, ip=auth._ip(request))
    except dep.ErroDeposito as e:
        raise HTTPException(400, str(e))
    if res["estado"] == "falhou":
        raise HTTPException(502, f"O Stripe não devolveu: {res['erro']}")
    if res["estado"] == "pendente":
        raise HTTPException(504, f"Não deu para confirmar: {res['erro']}")
    return res


@r.post("/depositos/{oid}/conferir")
def conferir_deposito(request: Request, oid: int = Path(..., ge=1, le=2**63 - 1), con: sqlite3.Connection = Depends(get_db),
                      u=Depends(auth.exige("MANAGER"))):
    """Lê no Stripe as devoluções deste pagamento (as do painel e as feitas direto no Stripe)."""
    from command_center.providers import deposito_site as dep, stripe_loja
    try:
        return dep.conferir(con, u["id"], oid, ip=auth._ip(request))
    except dep.ErroDeposito as e:
        raise HTTPException(400, str(e))
    except stripe_loja.ErroStripe as e:
        raise HTTPException(502, str(e))


class ValorDepositoIn(BaseModel):
    tipo: str                               # servico | produto
    id: int = Field(..., ge=1, le=2**63 - 1)
    valor: float | str | None = None
    obrigatorio: bool | None = None         # só serviço


@r.patch("/depositos/valor")
def mudar_valor_deposito(dados: ValorDepositoIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                         u=Depends(auth.exige("MANAGER"))):
    """O depósito que o site cobra nas próximas compras (por serviço e por produto) e a caixa "obrigatório"."""
    from command_center.providers import deposito_site as dep
    try:
        evento, mud = dep.mudar_valor(con, u["id"], dados.tipo, dados.id, dados.valor, dados.obrigatorio)
    except dep.ErroDeposito as e:
        raise HTTPException(404 if "não existe" in str(e) else 400, str(e))
    if mud:
        auditar(con, evento, f"user:{u['id']}", user_id=u["id"],
                entity_type="booking_service" if dados.tipo == "servico" else "store_product", entity_id=dados.id,
                detail={**{k: {"antes": a, "depois": v} for k, (a, v) in mud.items()}, "via": "security deposit"},
                ip=auth._ip(request))
    con.commit()
    return dep.valores(con)


# ------------------------------------------------------------------ o painel do site (#306)
@r.get("/painel")
def painel(dias: int = Query(30), con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """As métricas do site no período (7, 30 ou 90 dias, no fuso da Flórida), com o período anterior para comparar."""
    from command_center.providers import painel_site
    return painel_site.painel(con, dias)


# ------------------------------------------------------------------ waiver assinada aqui (#85)
class WaiverNativaIn(BaseModel):
    ligada: bool


@r.get("/waiver-nativa")
def waiver_nativa(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                  con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    """Ligada ou não, os dois modelos importados (nome, hash, quando, versão), as assinadas aqui (paginadas) e
    a conferência do aviso §744.301(3) no parental atual (#116)."""
    from command_center.providers import waiver_nativa as wn
    return {"ligada": wn.ligada(con), "modelos": wn.modelos(con), "assinadas": wn.listar(con, limit, offset),
            "aviso_744": wn.aviso(con)}


@r.get("/waiver-nativa/versoes")
def waiver_nativa_versoes(kind: str | None = Query(None, pattern="^(adult|parental)$"), limit: int = Query(25, ge=1, le=200),
                          offset: int = Query(0, ge=0), con: sqlite3.Connection = Depends(get_db),
                          u=Depends(auth.exige("MANAGER"))):
    """#116: toda versão de modelo que já valeu (nunca se apaga), das mais novas para as mais velhas, paginadas,
    com quantas assinaturas cada uma tem e a conferência do aviso feita na importação."""
    from command_center.providers import waiver_nativa as wn
    return wn.versoes(con, kind, limit, offset)


@r.get("/waiver-nativa/versoes/{vid}/pdf")
def waiver_nativa_versao_pdf(vid: int = Path(..., ge=1, le=2**63 - 1), con: sqlite3.Connection = Depends(get_db),
                             u=Depends(auth.exige("MANAGER"))):
    """O PDF de uma versão, como foi importado. Se o arquivo no disco não bate mais com o hash da versão, 409."""
    import hashlib
    from command_center.providers import waiver_nativa as wn
    v = wn.versao(con, vid)
    if not v:
        raise HTTPException(404, "versão não encontrada")
    try:
        with open(v["pdf_path"], "rb") as f:
            pdf = f.read()
    except OSError:
        raise HTTPException(404, "o PDF desta versão não está no servidor")
    if hashlib.sha256(pdf).hexdigest() != v["sha256"]:
        raise HTTPException(409, "o PDF desta versão no servidor não bate com o hash gravado: importe o modelo de novo")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="URACE-waiver-{v["kind"]}-v{v["number"]}.pdf"',
                             "Cache-Control": "private, no-store", "X-Content-SHA256": v["sha256"]})


@r.post("/waiver-nativa/importar")
def waiver_nativa_importar(request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("ADMIN"))):
    """LÊ os dois modelos no DocuSign (nome + PDF) e guarda aqui. Não muda nada no DocuSign."""
    from command_center.providers import NaoConectado
    from command_center.providers import waiver_nativa as wn
    try:
        feitos = wn.importar_do_docusign(con, u["id"])
    except NaoConectado as e:
        raise HTTPException(503, f"DocuSign não conectado: {e}")
    except ValueError as e:
        raise HTTPException(409, str(e))
    _aud(con, request, u, "waiver_nativa.importar", None, {"modelos": feitos})
    con.commit()
    return {"modelos": wn.modelos(con)}


@r.post("/waiver-nativa/ligar")
def waiver_nativa_ligar(dados: WaiverNativaIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                        u=Depends(auth.exige("ADMIN"))):
    """Liga ou desliga a assinatura na área do cliente. Desligar não apaga nada já assinado."""
    from command_center.providers import waiver_nativa as wn
    try:
        ligada = wn.ligar(con, dados.ligada, u["id"])
    except ValueError as e:
        raise HTTPException(409, str(e))
    _aud(con, request, u, "waiver_nativa.ligar", None, {"ligada": ligada})
    con.commit()
    return {"ligada": ligada, "modelos": wn.modelos(con)}

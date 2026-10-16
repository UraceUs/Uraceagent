"""Site público, visto de dentro (#41, #42): a agenda de sessões e, depois, as contas de
clientes. Quem abre e fecha a agenda é o gerente; confirmar e recusar pedido é da operação."""
import sqlite3
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

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
        a["contrato"] = contrato.situacao_do_agendamento(con, a["client_id"], a["date"])
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
    site_kart: str | None = None            # #263: o kart do site que este serviço vende (chave de conteudo.KARTS); #297: ou um kart novo
    site_title: str | None = None           # #297: o cartão do kart no site — nome, linha de baixo, aviso, kart próprio
    site_subtitle: str | None = None
    site_note: str | None = None
    own_kart: bool | None = None
    kind: str | None = None                 # #169: session (avulsa) | plan (mensal: price é por mês)
    months: int | str | None = None         # #169: meses do compromisso do plano
    sessions_month: int | str | None = None # #169: sessões por mês que o plano dá (vira o contrato do card)
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
        mud = loja.mudar(con, u["id"], pid, d)
    except loja.ErroProduto as e:
        raise HTTPException(404 if "não existe" in str(e) else 400, str(e))
    if mud:
        auditar(con, "store.product.update", f"user:{u['id']}", user_id=u["id"], entity_type="store_product", entity_id=pid,
                detail={k: {"antes": a, "depois": v} for k, (a, v) in mud.items()}, ip=auth._ip(request))
    con.commit()
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
    """Ligada ou não, os dois modelos importados (nome, hash, quando) e as assinadas aqui (paginadas)."""
    from command_center.providers import waiver_nativa as wn
    return {"ligada": wn.ligada(con), "modelos": wn.modelos(con), "assinadas": wn.listar(con, limit, offset)}


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

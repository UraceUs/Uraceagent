"""Área do cliente (#40) — as rotas. Hoje em `/ops/portal` (site interno, para testar);
depois vai para o site público.

**Separada da equipe, de propósito:**
- tabela própria (`portal_accounts`), sessão própria (`portal_sessions`) e cookie próprio
  (`cp_session`). A dependência da equipe (`auth.usuario_atual`) só lê `cc_session`: um
  cliente logado não alcança nenhuma rota do painel, e vice-versa;
- CSRF por cookie duplo (`cp_csrf` legível + cabeçalho `X-CSRF`) em tudo que escreve;
- limite de tentativas de login (por IP e por e-mail) e de cadastro (por IP), e a mesma
  mensagem para "e-mail não existe" e "senha errada";
- a senha é scrypt com sal (a mesma função da equipe).

Mensagens em inglês: é o que o cliente lê (o site público é en-US).
"""
import hmac
import os
import secrets
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from command_center.api import auth
from command_center.db import agora, atualizar, auditar, get_db, inserir, transacao, um
from command_center.providers import agenda_asana, agenda_sessoes as ag, portal, servicos_site, vinculo_site

r = APIRouter(prefix="/ops/api/portal", tags=["portal"])

COOKIE = "cp_session"
COOKIE_CSRF = "cp_csrf"
DIAS = 30
MAX_CADASTROS_POR_HORA = 10
# #305: toda conta nova manda um e-mail com a marca da URACE; um teto geral por hora para ele não virar canal de spam
# espalhado por muitas conexões (um dia normal tem poucas contas novas)
MAX_CADASTROS_GLOBAL_HORA = 100


def _chave_cadastro(ip):
    """A chave do limite por conexão. IPv6: o bloco /64 (uma casa recebe um /64 inteiro)."""
    import ipaddress
    try:
        a = ipaddress.ip_address(ip)
        if a.version == 6:
            ip = f"{ipaddress.ip_network(f'{ip}/64', strict=False).network_address}/64"
    except ValueError:
        pass
    return f"portal-signup:{ip}"


def limite_de_cadastro(con, ip):
    """A mensagem quando passou do limite (por conexão ou o geral), ou None."""
    desde = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    if um(con, "SELECT COUNT(*) AS n FROM login_attempts WHERE key=? AND at>?", (_chave_cadastro(ip), desde))["n"] >= MAX_CADASTROS_POR_HORA:
        return "Too many sign-ups from this connection. Try again later."
    if um(con, "SELECT COUNT(*) AS n FROM login_attempts WHERE key LIKE 'portal-signup:%' AND at>?", (desde,))["n"] >= MAX_CADASTROS_GLOBAL_HORA:
        return "Too many sign-ups right now. Please try again in a few minutes."
    return None


def contar_cadastro(con, ip):
    inserir(con, "login_attempts", key=_chave_cadastro(ip), ok=1)
MSG_LOGIN = "Invalid email or password."


def _erro(e):
    return HTTPException(400, str(e))


def _token_hash(t):
    return auth._hash_token(t)


def _abrir(con, request, response, conta_id):
    token = secrets.token_urlsafe(32)
    expira = (datetime.now(timezone.utc) + timedelta(days=DIAS)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    con.execute("INSERT INTO portal_sessions (id, account_id, expires_at, ip, user_agent) VALUES (?,?,?,?,?)",
                (_token_hash(token), conta_id, expira, auth._ip(request), (request.headers.get("user-agent") or "")[:200]))
    seguro = auth._seguro(request)
    for nome, valor, http in ((COOKIE, token, True), (COOKIE_CSRF, secrets.token_urlsafe(24), False)):
        response.set_cookie(nome, valor, max_age=DIAS * 86400, httponly=http, secure=seguro, samesite="lax", path="/")
    atualizar(con, "portal_accounts", conta_id, last_login_at=agora())


def conta_do_cookie(request, con):
    """A conta do cliente logado neste navegador, ou None (#236: o carrinho do site funciona sem conta
    para produto e pede a conta só para a sessão da agenda)."""
    token = request.cookies.get(COOKIE)
    s = um(con, """SELECT s.account_id, s.expires_at FROM portal_sessions s JOIN portal_accounts a ON a.id=s.account_id
                    WHERE s.id=? AND s.revoked_at IS NULL AND a.active=1""", (_token_hash(token),)) if token else None
    return s["account_id"] if s and s["expires_at"] > agora() else None


def csrf_ok(request):
    c, h = request.cookies.get(COOKIE_CSRF, ""), request.headers.get("x-csrf", "")
    return bool(c) and hmac.compare_digest(c, h)


def cliente_atual(request: Request, con: sqlite3.Connection = Depends(get_db)):
    """Dependência: a conta do cliente logado. Escrita exige o CSRF."""
    conta = conta_do_cookie(request, con)
    if not conta:
        raise HTTPException(401, "Please sign in.")
    if request.method not in ("GET", "HEAD", "OPTIONS") and not csrf_ok(request):
        raise HTTPException(403, "Security check failed. Reload the page and try again.")
    return conta


def _aud(con, request, evento, conta_id, detalhe=None):
    auditar(con, evento, f"portal:{conta_id}", entity_type="portal_account", entity_id=conta_id,
            detail=detalhe or {}, ip=auth._ip(request))


# ------------------------------------------------------------------ cadastro e login
class CadastroIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    email: str
    password: str
    birth_date: str
    phone_country: str | None = None
    phone: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    country: str | None = None
    accept_terms: bool = False
    i_am_driver: bool = False


@r.post("/signup", status_code=201)
def cadastro(dados: CadastroIn, request: Request, response: Response, background: BackgroundTasks,
             con: sqlite3.Connection = Depends(get_db)):
    ip = auth._ip(request)
    passou = limite_de_cadastro(con, ip)
    if passou:
        raise HTTPException(429, passou)
    if not auth.senha_aceitavel(dados.password) or len(dados.password) < 8:
        raise HTTPException(400, "Use a password with at least 8 characters.")
    contar_cadastro(con, ip)
    sal, h = auth.hash_senha(dados.password)
    try:
        cid = portal.criar_conta(con, dados.model_dump(exclude={"password"}), sal, h)
    except portal.ErroPortal as e:
        con.commit()                              # a tentativa conta para o limite
        raise _erro(e)
    _abrir(con, request, response, cid)
    _aud(con, request, "portal.signup", cid, {"piloto_proprio": dados.i_am_driver})
    con.commit()
    # #305 (dono, 16/10): toda conta nova recebe o e-mail de boas-vindas com a identidade da URACE (a senha vai nele:
    # decisão do dono). A senha só existe nesta requisição: vai para o e-mail e some, nunca é guardada nem logada.
    from command_center.providers import conta_site
    from command_center.vitrine import idioma
    background.add_task(conta_site.boas_vindas_bg, cid, dados.password, idioma.de_request(request))
    return portal.conta(con, cid)


class LoginIn(BaseModel):
    email: str
    password: str


@r.post("/login")
def entrar(dados: LoginIn, request: Request, response: Response, con: sqlite3.Connection = Depends(get_db)):
    email = (dados.email or "").strip().lower()
    ip = auth._ip(request)
    chaves = (f"portal-ip:{ip}", f"portal-email:{email}")
    if any(auth._falhas_recentes(con, k) >= auth.MAX_FALHAS for k in chaves):
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")
    c = um(con, "SELECT id, pw_salt, pw_hash, active FROM portal_accounts WHERE email=?", (email,))
    ok = bool(c and c["active"] and auth.confere_senha(dados.password or "", c["pw_salt"], c["pw_hash"]))
    if not c:
        auth._scrypt(dados.password or "", b"0" * 16)      # mesmo custo: o tempo não revela quem existe
    for k in chaves:
        auth._registra_tentativa(con, k, ok)
    if not ok:
        con.commit()
        time.sleep(0.4)
        raise HTTPException(401, MSG_LOGIN)
    _abrir(con, request, response, c["id"])
    _aud(con, request, "portal.login", c["id"])
    con.commit()
    return portal.conta(con, c["id"])


@r.post("/logout")
def sair(request: Request, response: Response, con: sqlite3.Connection = Depends(get_db)):
    token = request.cookies.get(COOKIE)
    if token:
        con.execute("UPDATE portal_sessions SET revoked_at=? WHERE id=? AND revoked_at IS NULL", (agora(), _token_hash(token)))
        con.commit()
    for c in (COOKIE, COOKIE_CSRF):
        response.delete_cookie(c, path="/")
    return {"ok": True}


# ------------------------------------------------------------------ conta
@r.get("/me")
def eu(cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    return portal.conta(con, cid)


class ContaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    birth_date: str | None = None
    phone_country: str | None = None
    phone: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    country: str | None = None


@r.patch("/me")
def editar_conta(dados: ContaIn, request: Request, cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    try:
        mudou = portal.atualizar_conta(con, cid, dados.model_dump(exclude_unset=True))
    except portal.ErroPortal as e:
        raise _erro(e)
    _aud(con, request, "portal.account.update", cid, {"campos": mudou})
    con.commit()
    return portal.conta(con, cid)


class SenhaIn(BaseModel):
    current_password: str
    new_password: str


@r.post("/me/password")
def trocar_senha(dados: SenhaIn, request: Request, response: Response, cid=Depends(cliente_atual),
                 con: sqlite3.Connection = Depends(get_db)):
    c = um(con, "SELECT pw_salt, pw_hash FROM portal_accounts WHERE id=?", (cid,))
    if not auth.confere_senha(dados.current_password or "", c["pw_salt"], c["pw_hash"]):
        raise HTTPException(400, "Your current password is not right.")
    if not auth.senha_aceitavel(dados.new_password) or len(dados.new_password) < 8:
        raise HTTPException(400, "Use a password with at least 8 characters.")
    sal, h = auth.hash_senha(dados.new_password)
    atualizar(con, "portal_accounts", cid, pw_salt=sal, pw_hash=h, updated_at=agora())
    # as outras sessões caem; esta continua (nova)
    con.execute("UPDATE portal_sessions SET revoked_at=? WHERE account_id=? AND revoked_at IS NULL", (agora(), cid))
    _abrir(con, request, response, cid)
    _aud(con, request, "portal.password", cid)
    con.commit()
    return {"ok": True}


# ------------------------------------------------------------------ esqueci minha senha (#168)
RESET_MIN = 30
MAX_PEDIDOS_RESET_IP, MAX_PEDIDOS_RESET_EMAIL = 5, 3          # por hora
HOSTS_NOSSOS = {"urace.us", "www.urace.us", "my.urace.us", "ops.urace.us", "novo.urace.us"}
MSG_RESET_OK = "If that email has an account with us, we just sent a link to choose a new password. Check your inbox and spam."


class EsqueciIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str


class RedefinirIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str
    password: str


def _base_do_link(request):
    """Onde o link de redefinição aponta: o endereço que a pessoa está usando, desde que seja nosso
    (um cabeçalho Host inventado não vira link no e-mail). Fora da lista, my.urace.us."""
    cheio = (request.headers.get("host") or "").strip().lower()
    host = cheio.split(":")[0]
    nossos = HOSTS_NOSSOS | {h.strip().lower() for h in os.environ.get("CC_SITE_HOSTS", "").split(",") if h.strip()}
    if host in nossos or host in {"127.0.0.1", "localhost"}:
        # sem TLS na frente (desenvolvimento e testes), o endereço é o que veio, com a porta
        return f"https://{host}" if auth._seguro(request) else f"{request.url.scheme}://{cheio}"
    return "https://my.urace.us"


def _pedidos_na_hora(con, chave):
    desde = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    return um(con, "SELECT COUNT(*) AS n FROM login_attempts WHERE key=? AND at>?", (chave, desde))["n"]


@r.post("/password/forgot")
def esqueci_senha(dados: EsqueciIn, request: Request, con: sqlite3.Connection = Depends(get_db)):
    """Manda o link de redefinição. A resposta é a mesma existindo ou não a conta: a tela não
    revela quais e-mails estão cadastrados. Limite por IP e por e-mail."""
    from command_center.providers import email_envio
    email = (dados.email or "").strip().lower()
    ip = auth._ip(request)
    if _pedidos_na_hora(con, f"portal-reset-ip:{ip}") >= MAX_PEDIDOS_RESET_IP or \
            _pedidos_na_hora(con, f"portal-reset-email:{email}") >= MAX_PEDIDOS_RESET_EMAIL:
        raise HTTPException(429, "Too many requests. Try again in an hour.")
    inserir(con, "login_attempts", key=f"portal-reset-ip:{ip}", ok=1)
    inserir(con, "login_attempts", key=f"portal-reset-email:{email}", ok=1)
    c = um(con, "SELECT id, name FROM portal_accounts WHERE email=? AND active=1", (email,))
    if c:
        token = secrets.token_urlsafe(32)
        criado = datetime.now(timezone.utc)
        inserir(con, "portal_resets", account_id=c["id"], token_hash=_token_hash(token), ip=ip,
                created_at=criado.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                expires_at=(criado + timedelta(minutes=RESET_MIN)).strftime("%Y-%m-%dT%H:%M:%S.000Z"))
        link = f"{_base_do_link(request)}/ops/portal/reset?token={token}"
        texto = (f"Hi {c['name'].split()[0]},\n\nSomeone asked to reset the password of your URACE account. "
                 f"If it was you, open this link and choose a new password:\n\n{link}\n\n"
                 f"The link works once and expires in {RESET_MIN} minutes. If you did not ask for it, ignore this email: "
                 "your password stays the same.\n\nURACE.US · Orlando, FL")
        # #305: com a identidade da URACE, como o das boas-vindas
        from command_center.providers import email_marca
        html = email_marca.html(f"Hi {c['name'].split()[0]}!", [
            "Someone asked to reset the password of your URACE account. If it was you, choose a new password:"],
            botao=("Choose a new password", link),
            depois=[f"The link works once and expires in {RESET_MIN} minutes.",
                    "If you did not ask for it, ignore this email: your password stays the same."])
        try:
            email_envio.enviar(email, "Reset your URACE password", texto, html=html)
        except email_envio.ErroEnvio:
            con.rollback()
            raise HTTPException(503, "We could not send the email right now. Try again in a few minutes.")
        _aud(con, request, "portal.password.reset.sent", c["id"])
    con.commit()
    return {"ok": True, "message": MSG_RESET_OK}


@r.post("/password/reset")
def redefinir_senha(dados: RedefinirIn, request: Request, response: Response, con: sqlite3.Connection = Depends(get_db)):
    """Troca a senha pelo link (uso único, 30 min), derruba as outras sessões e entra."""
    h = _token_hash((dados.token or "").strip())
    t = um(con, "SELECT id, account_id, expires_at, used_at FROM portal_resets WHERE token_hash=?", (h,))
    agora_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    if not t or t["used_at"] or t["expires_at"] < agora_iso:
        raise HTTPException(400, "This link has expired or was already used. Ask for a new one.")
    if not auth.senha_aceitavel(dados.password) or len(dados.password) < 8:
        raise HTTPException(400, "Use a password with at least 8 characters.")
    cid = t["account_id"]
    sal, ph = auth.hash_senha(dados.password)
    atualizar(con, "portal_accounts", cid, pw_salt=sal, pw_hash=ph, updated_at=agora())
    con.execute("UPDATE portal_resets SET used_at=? WHERE account_id=? AND used_at IS NULL", (agora_iso, cid))
    con.execute("UPDATE portal_sessions SET revoked_at=? WHERE account_id=? AND revoked_at IS NULL", (agora(), cid))
    _abrir(con, request, response, cid)
    _aud(con, request, "portal.password.reset", cid)
    con.commit()
    return portal.conta(con, cid)


# ------------------------------------------------------------------ pilotos
class PilotoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    birth_date: str | None = None
    email: str | None = None
    phone: str | None = None
    notes: str | None = None
    social: str | None = None
    measures: dict | None = None
    is_self: bool = False


@r.post("/drivers", status_code=201)
def novo_piloto(dados: PilotoIn, request: Request, cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    try:
        pid = portal.criar_piloto(con, cid, dados.model_dump(exclude_unset=True) | {"name": dados.name})
    except portal.ErroPortal as e:
        raise _erro(e)
    _aud(con, request, "portal.driver.create", cid, {"piloto": pid})
    con.commit()
    return portal.conta(con, cid)


@r.patch("/drivers/{pid}")
def editar_piloto(pid: int, dados: PilotoIn, request: Request, cid=Depends(cliente_atual),
                  con: sqlite3.Connection = Depends(get_db)):
    d = dados.model_dump(exclude_unset=True)
    d.pop("is_self", None)
    try:
        mudou = portal.atualizar_piloto(con, cid, pid, d)
    except portal.ErroPortal as e:
        raise HTTPException(404 if "not found" in str(e) else 400, str(e))
    _aud(con, request, "portal.driver.update", cid, {"piloto": pid, "campos": mudou})
    con.commit()
    return portal.conta(con, cid)


# ------------------------------------------------------------------ agenda (#41)
@r.get("/availability")
def disponibilidade(request: Request, start: str | None = None, end: str | None = None, cid=Depends(cliente_atual),
                    con: sqlite3.Connection = Depends(get_db)):
    """O que o cliente pode marcar: só aberto/fechado e vagas, sem o motivo interno."""
    try:
        d = ag.disponibilidade(con, date.fromisoformat(start) if start else None, date.fromisoformat(end) if end else None)
    except (ValueError, ag.ErroAgenda):
        raise HTTPException(400, "Choose a valid date range.")
    for dia in d["dias"]:
        for p in ("manha", "tarde"):
            dia["periods"][p] = {"open": dia["periods"][p]["open"], "spots": dia["periods"][p]["spots"]}
    return {**d, "services": servicos_site.para_cliente(con), "auto_sell": bool(ag.config(con).get("auto_sell")),
            "cart": carrinho_ligado(request)}


@r.get("/bookings")
def meus_agendamentos(limit: int | None = None, offset: int = 0, cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    """As sessões da conta, das mais novas para as mais velhas. #314: o aluno recorrente marca muitas — com `limit`,
    uma página e o `total` (sem `limit`, as 100 de sempre)."""
    if limit is None:
        return {"bookings": ag.do_cliente(con, cid)}
    limit, offset = max(1, min(int(limit), 100)), max(0, int(offset))
    return {"bookings": ag.do_cliente(con, cid, limit, offset), "total": ag.total_do_cliente(con, cid), "limit": limit, "offset": offset}


class AgendarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: str
    period: str
    service_id: int | None = None
    driver_id: int | None = None
    notes: str | None = None
    origin: str | None = None                # #164: "site" quando veio do site novo
    utm: dict | None = None                  # #164: utm_source, utm_campaign… (para o marketing)
    quote: str | None = None                 # #314: o hash da cotação que o aluno recorrente viu (409 se mudou)


def _vender(bid):
    """Venda automática (#164) fora da resposta: o QuickBooks e o DocuSign levam alguns segundos, e a
    tela de acompanhamento mostra cada etapa chegando."""
    from command_center.db import conectar
    from command_center.providers import venda_site
    con = conectar()
    try:
        venda_site.vender(con, bid)
        con.commit()
    finally:
        con.close()


@r.post("/bookings", status_code=201)
def agendar(dados: AgendarIn, request: Request, tarefas: BackgroundTasks, cid=Depends(cliente_atual),
            con: sqlite3.Connection = Depends(get_db)):
    from command_center.providers import agenda_lote
    try:
        with transacao(con):                  # duas pessoas na última vaga: só uma leva
            if dados.quote is not None:
                # #314: o aluno recorrente viu "Included in your plan" ou "Extra session · $X": se mudou, revisa antes
                agenda_lote.conferir(con, cid, dados.driver_id, dados.service_id,
                                     [{"date": dados.date, "period": dados.period}], dados.quote)
            bid = ag.agendar(con, cid, dados.date, dados.period, dados.driver_id, dados.notes, dados.service_id)
            from command_center.providers import cobranca_agenda, venda_site
            atualizar(con, "bookings", bid, origin="site" if dados.origin == "site" else "portal",
                      utm=venda_site.utm_limpo(dados.utm))
            cobranca_agenda.ao_marcar(con, bid)      # contrato + waiver em dia: confirma sozinha (dono, 06/10)
            _aud(con, request, "portal.booking", cid, {"agendamento": bid, "data": dados.date, "periodo": dados.period,
                                                        "servico": dados.service_id})
    except agenda_lote.CotacaoMudou as e:
        raise HTTPException(409, str(e))
    except ag.ErroAgenda as e:
        raise HTTPException(400, str(e))
    tarefas.add_task(agenda_asana.levar, bid)      # #67: todo agendamento vira tarefa no Asana
    from command_center.providers import venda_site
    if venda_site.ligada(con):
        tarefas.add_task(_vender, bid)
    return {"id": bid, "bookings": ag.do_cliente(con, cid), "auto_sell": venda_site.ligada(con)}


# ------------------------------------------------------------------ vários dias num pedido (#314)
def carrinho_ligado(request):
    """#236/#314: neste endereço a sessão pode ir para o carrinho do site (Stripe): é o site novo e o Stripe está ligado."""
    from command_center.api.vitrine import e_do_site
    from command_center.providers import stripe_loja
    return e_do_site(request) and stripe_loja.ligado()


@r.get("/plan")
def meu_plano(request: Request, response: Response, driver_id: int | None = None, cid=Depends(cliente_atual),
              con: sqlite3.Connection = Depends(get_db)):
    """Por piloto: é aluno recorrente (plano mensal vigente)? O nome do plano, o preço da extra e como paga: o
    recorrente pelo plano (QuickBooks); o cliente novo no carrinho do site (Stripe) quando ele está ligado, senão
    pela invoice (dono, 16/10). O contador do pacote não sai daqui (dono, 01/10: o cliente não vê)."""
    from command_center.providers import agenda_lote
    ids = [p["id"] for p in portal.pilotos(con, cid) if driver_id is None or p["id"] == driver_id]
    if driver_id is not None and not ids:
        raise HTTPException(404, "Driver not found.")
    carrinho = carrinho_ligado(request)
    pilotos = [agenda_lote.plano_do_piloto(con, cid, i) for i in ids]
    for p in pilotos:
        p["payment"] = "plano" if p["recurring"] else ("stripe" if carrinho else "invoice")
    response.headers["Cache-Control"] = "private, no-store"
    return {"drivers": pilotos, "cart": carrinho}


class DiaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: str
    period: str


class LoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_id: int
    driver_id: int
    slots: list[DiaIn]
    quote: str | None = None                 # o hash da cotação que o cliente viu
    notes: str | None = None
    origin: str | None = None
    utm: dict | None = None


@r.post("/bookings/quote")
def cotar_lote(dados: LoteIn, response: Response, cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    """Cada dia: aberto ou não, e "Included in your plan" ou "Extra session · $X". Nada é gravado."""
    from command_center.providers import agenda_lote
    try:
        q = agenda_lote.cotar(con, cid, dados.driver_id, dados.service_id, [x.model_dump() for x in dados.slots])
    except agenda_lote.ErroLote as e:
        raise HTTPException(400, str(e))
    response.headers["Cache-Control"] = "private, no-store"
    return q


def _vender_grupo(gid):
    from command_center.db import conectar
    from command_center.providers import venda_site
    con = conectar()
    try:
        venda_site.vender_grupo(con, gid)
        con.commit()
    finally:
        con.close()


@r.post("/bookings/batch", status_code=201)
def marcar_lote(dados: LoteIn, request: Request, tarefas: BackgroundTasks, cid=Depends(cliente_atual),
                con: sqlite3.Connection = Depends(get_db)):
    """O pedido de vários dias: ou entram todos, ou nenhum. A cotação mudou desde que o cliente viu: 409."""
    from command_center.providers import agenda_lote, venda_site
    try:
        with transacao(con):
            gid, ids = agenda_lote.marcar(con, cid, dados.driver_id, dados.service_id, [x.model_dump() for x in dados.slots],
                                          dados.quote, dados.notes, dados.origin, venda_site.utm_limpo(dados.utm))
            _aud(con, request, "portal.booking.batch", cid, {"grupo": gid, "agendamentos": ids, "servico": dados.service_id,
                                                              "datas": sorted(f"{x.date} {x.period}" for x in dados.slots)})
    except agenda_lote.CotacaoMudou as e:
        raise HTTPException(409, str(e))
    except (agenda_lote.ErroLote, ag.ErroAgenda) as e:
        raise HTTPException(400, str(e))
    for bid in ids:
        tarefas.add_task(agenda_asana.levar, bid)            # #67: cada sessão vira tarefa no Asana
    if venda_site.ligada(con):
        tarefas.add_task(_vender_grupo, gid)
    return {"group_id": gid, "ids": ids, "auto_sell": venda_site.ligada(con)}


@r.get("/bookings/group/{gid}")
def acompanhar_lote(gid: int, response: Response, cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    """As etapas do pedido de vários dias: os dias, a invoice das extras (uma só), a waiver, confirmado."""
    from command_center.providers import venda_site
    if not um(con, "SELECT 1 AS x FROM booking_groups WHERE id=? AND account_id=?", (gid, cid)):
        raise HTTPException(404, "Booking not found.")
    venda_site.conferir_pagamento_grupo(con, gid)
    con.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return venda_site.checkout_grupo(con, gid)


# ------------------------------------------------------------------ plano mensal (#169)
class PlanoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_id: int
    driver_id: int
    origin: str | None = None
    utm: dict | None = None


def _vender_plano(oid):
    from command_center.db import conectar
    from command_center.providers import venda_plano
    con = conectar()
    try:
        venda_plano.vender(con, oid)
        con.commit()
    finally:
        con.close()


@r.post("/plans", status_code=201)
def assinar_plano(dados: PlanoIn, request: Request, tarefas: BackgroundTasks, cid=Depends(cliente_atual),
                  con: sqlite3.Connection = Depends(get_db)):
    """O cliente escolhe o plano (Academy, Boost) e o piloto; com a venda automática ligada, a primeira
    mensalidade sai na hora e as outras ficam agendadas no dia 1."""
    from command_center.providers import venda_plano, venda_site
    try:
        oid = venda_plano.pedir(con, cid, dados.service_id, dados.driver_id, dados.origin, dados.utm)
    except venda_plano.ErroPlano as e:
        raise HTTPException(400, str(e))
    _aud(con, request, "portal.plan", cid, {"plano": oid, "servico": dados.service_id, "piloto": dados.driver_id})
    con.commit()
    if venda_site.ligada(con):
        tarefas.add_task(_vender_plano, oid)
    return {"id": oid, "auto_sell": venda_site.ligada(con)}


@r.get("/plans/{oid}")
def acompanhar_plano(oid: int, response: Response, cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    from command_center.providers import venda_plano
    if not um(con, "SELECT 1 AS x FROM plan_orders WHERE id=? AND account_id=?", (oid, cid)):
        raise HTTPException(404, "Plan not found.")
    venda_plano.conferir_pagamento(con, oid)
    con.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return venda_plano.checkout(con, oid)


@r.get("/bookings/{bid}")
def acompanhar(bid: int, response: Response, cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    """As etapas de um pedido (#164): reservado → pagar → waiver → confirmado. Confere o pagamento
    direto no QuickBooks no máximo 1 vez por minuto."""
    from command_center.providers import venda_site
    if not um(con, "SELECT 1 AS x FROM bookings WHERE id=? AND account_id=?", (bid, cid)):
        raise HTTPException(404, "Booking not found.")
    venda_site.conferir_pagamento(con, bid)
    con.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return venda_site.checkout(con, bid)


@r.post("/bookings/{bid}/cancel")
def cancelar(bid: int, request: Request, tarefas: BackgroundTasks, cid=Depends(cliente_atual),
             con: sqlite3.Connection = Depends(get_db)):
    try:
        ag.cancelar_pelo_cliente(con, cid, bid)
    except ag.ErroAgenda as e:
        raise HTTPException(404 if "not found" in str(e) else 400, str(e))
    _aud(con, request, "portal.booking.cancel", cid, {"agendamento": bid})
    con.commit()
    tarefas.add_task(agenda_asana.levar, bid)
    return {"bookings": ag.do_cliente(con, cid)}


# ------------------------------------------------------------------ painel do cliente (#54)
@r.get("/dashboard")
def painel(cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    """O resumo da conta: o que falta, os pilotos (última sessão e medidas) e as sessões."""
    c = portal.conta(con, cid)
    sessoes = ag.do_cliente(con, cid)
    hoje = portal.hoje().isoformat()
    proximas = sorted((s for s in sessoes if s["status"] in ("pendente", "confirmada") and s["date"] >= hoje),
                      key=lambda s: s["date"])
    feitas = [s for s in sessoes if s["status"] == "confirmada" and s["date"] < hoje]
    hist = vinculo_site.historico(con, cid)
    ultimo = max([s["date"] for s in feitas] + [x["date"] for x in hist["services"] if x["status"] == "done"], default=None)
    return {"account": c, "next_session": proximas[0] if proximas else None, "upcoming": len(proximas),
            "last_session": ultimo, "days_since_last_session": (portal.hoje() - date.fromisoformat(ultimo)).days
            if ultimo else None, "linked": hist["linked"],
            "measures_warn_days": portal.MEDIDAS_AVISO_DIAS, "measures_limit_days": portal.MEDIDAS_LIMITE_DIAS}


# ------------------------------------------------------------------ histórico (#42)
@r.get("/history")
def historico(cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    """Só depois que a equipe liga a conta ao cliente do site interno."""
    return vinculo_site.historico(con, cid)


# ------------------------------------------------------------------ waiver assinada aqui (#85)
class WaiverIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    typed_name: str
    signature: str                   # data:image/png;base64,... (desenhada no quadro)
    read_and_agree: bool = False
    consent_esign: bool = False
    english_understood: bool = False     # #119: caixa de idioma
    relationship: str | None = None          # parental (#105): mother | father (tutor e outros: no balcão)
    guardian_declaration: bool = False
    document_read_at: str | None = None       # #107: quando a tela viu todas as páginas do PDF (ISO, UTC)
    document_read_mode: str | None = None     # pdf_viewer | pdf_opened_and_text (o navegador não desenhou o PDF)
    sign_code: str | None = None              # #108: o código que chegou no e-mail da conta
    review_id: int | None = Field(None, ge=1, le=2**63 - 1)   # #112: a revisão que este clique final confirma
    name_mismatch_confirmed: bool = False     # #112: o nome digitado é outro e quem assina confirmou


class CodigoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str


def _emitir(con, request, cid, finalidade):
    from command_center.providers import codigos, email_envio
    c = um(con, "SELECT email FROM portal_accounts WHERE id=?", (cid,))
    try:
        r = codigos.emitir(con, cid, finalidade, c["email"], email_envio.enviar)
    except codigos.ErroCodigo as e:
        raise HTTPException(429, str(e))
    except email_envio.ErroEnvio:
        raise HTTPException(503, "We could not send the email right now. Try again in a few minutes.")
    _aud(con, request, "portal.code.sent", cid, {"finalidade": finalidade})
    if finalidade == "waiver_sign":                 # #111: na trilha da waiver
        from command_center.providers import trilha_waiver as tw
        tw.registrar(con, "code_sent", "account", ip=auth._ip(request), user_agent=request.headers.get("user-agent"),
                     detail={"sent_to": r.get("sent_to")}, account_id=cid)
    con.commit()
    return r


@r.post("/email/verify/send")
def email_codigo(request: Request, cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    """#108: manda o código que confirma o e-mail da conta."""
    if um(con, "SELECT email_verified_at FROM portal_accounts WHERE id=?", (cid,))["email_verified_at"]:
        return {"verified": True}
    return _emitir(con, request, cid, "email_verify")


@r.post("/email/verify")
def email_confirmar(dados: CodigoIn, request: Request, cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    from command_center.providers import codigos
    try:
        codigos.conferir(con, cid, "email_verify", dados.code)
    except codigos.ErroCodigo as e:
        raise HTTPException(400, str(e))
    con.execute("UPDATE portal_accounts SET email_verified_at=? WHERE id=?", (agora(), cid))
    _aud(con, request, "portal.email.verified", cid)
    con.commit()
    return {"verified": True}


@r.post("/waivers/code")
def waiver_codigo(request: Request, cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    """#108: o código de uma vez, na hora de assinar a waiver."""
    from command_center.providers import waiver_nativa as wn
    if not wn.ligada(con):
        raise HTTPException(404, "Waiver not available.")
    if not um(con, "SELECT email_verified_at FROM portal_accounts WHERE id=?", (cid,))["email_verified_at"]:
        raise HTTPException(400, "Confirm your email first.")
    return _emitir(con, request, cid, "waiver_sign")


@r.get("/waivers")
def waivers(cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    """Por piloto: qual waiver vale (menor → parental; maior → adult) e se já está assinada."""
    from command_center.providers import waiver_nativa as wn
    return wn.situacao(con, cid)


@r.get("/waivers/model/{kind}")
def waiver_modelo(kind: str, cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    """O texto do documento para ler antes de assinar (o PDF original está em …/pdf)."""
    from command_center.providers import waiver_nativa as wn
    m = wn.modelo(con, kind) if wn.ligada(con) else None
    if not m:
        raise HTTPException(404, "Waiver not available.")
    return {"kind": kind, "name": m["name"], "pages": m["pages"], "text": m["text"] or "",
            "declaration": wn.DECLARACAO if kind == "parental" else None}


@r.get("/waivers/model/{kind}/pdf")
def waiver_modelo_pdf(kind: str, request: Request, driver: int | None = Query(None, ge=1, le=2**63 - 1),
                      cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    from command_center.providers import waiver_nativa as wn
    m = wn.modelo(con, kind) if wn.ligada(con) else None
    if not m:
        raise HTTPException(404, "Waiver not available.")
    with open(m["pdf_path"], "rb") as f:
        pdf = f.read()
    # #107: a prova de que o documento chegou a quem assina — o assinar exige este registro
    _aud(con, request, "portal.waiver.document_view", cid, {"kind": kind, "sha256": m["sha256"]})
    from command_center.providers import trilha_waiver as tw          # #111: e o passo na trilha
    # revisão #329: a tela diz de qual piloto é a aba (`?driver=`); só vale piloto desta conta
    piloto = driver if driver and any(x["id"] == driver for x in portal.pilotos(con, cid)) else None
    tw.entregou_o_pdf(con, "account", ip=auth._ip(request), user_agent=request.headers.get("user-agent"),
                      detail={"sha256": m["sha256"]}, account_id=cid, pilot_id=piloto, kind=kind,
                      template_version_id=m.get("version_id"))
    con.commit()
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="URACE-waiver-{kind}.pdf"', "Cache-Control": "no-store"})


@r.post("/drivers/{pid}/waiver/review", status_code=201)
def revisar_waiver(pid: int, dados: WaiverIn, request: Request, cid=Depends(cliente_atual),
                   con: sqlite3.Connection = Depends(get_db)):
    """#112, passo 1: confere tudo menos o código e devolve o resumo que a tela mostra antes do clique final."""
    from command_center.providers import revisao_waiver as rv, waiver_nativa as wn
    try:
        return wn.revisar(con, cid, pid, dados.model_dump(), ip=auth._ip(request), aparelho=request.headers.get("user-agent"))
    except LookupError:
        raise HTTPException(404, "Driver not found.")
    except wn.ErroWaiver as e:
        raise HTTPException(400, str(e))
    except rv.Demais as e:
        raise HTTPException(429, str(e))


@r.post("/drivers/{pid}/waiver", status_code=201)
def assinar_waiver(pid: int, dados: WaiverIn, request: Request, cid=Depends(cliente_atual),
                   con: sqlite3.Connection = Depends(get_db)):
    from command_center.providers import waiver_nativa as wn
    try:
        w = wn.assinar(con, cid, pid, dados.model_dump(), ip=auth._ip(request), aparelho=request.headers.get("user-agent"))
    except LookupError:
        raise HTTPException(404, "Driver not found.")
    except wn.ErroWaiver as e:
        raise HTTPException(400, str(e))
    _aud(con, request, "portal.waiver.sign", cid, {"piloto": pid, "waiver": w["id"], "modelo": w["template"],
                                                   "sha256": w["doc_sha256"]})
    con.commit()
    return {"waiver_id": w["id"], "signed_at": w["completed_at"], "valid_until": w["expires_at"], **wn.situacao(con, cid)}


class EventoTelaIn(BaseModel):
    """#111: o que só a tela sabe. Lista fechada no servidor (trilha_waiver.DA_TELA)."""
    model_config = ConfigDict(extra="forbid")
    event: str = Field(..., max_length=40)
    mode: str | None = Field(None, max_length=40)          # all_pages_viewed: pdf_viewer | pdf_opened_and_text
    pages: int | None = Field(None, ge=1, le=500)


@r.post("/drivers/{pid}/waiver/events", status_code=201)
def waiver_evento(pid: int, dados: EventoTelaIn, request: Request, cid=Depends(cliente_atual),
                  con: sqlite3.Connection = Depends(get_db)):
    """#111: abriu a tela de assinar e leu todas as páginas, relatados pela tela, com hora do servidor, IP e aparelho."""
    from command_center.providers import trilha_waiver as tw, waiver_nativa as wn
    if not wn.ligada(con):
        raise HTTPException(404, "Waiver not available.")
    p = next((x for x in portal.pilotos(con, cid) if x["id"] == pid), None)
    if not p:
        raise HTTPException(404, "Driver not found.")
    try:
        tipo = wn.tipo_para(p)
    except wn.ErroWaiver as e:
        raise HTTPException(400, str(e))
    detalhe = None
    if dados.event == "all_pages_viewed":
        if dados.mode not in wn.MODOS_LEITURA:
            raise HTTPException(400, "Unknown reading mode.")
        detalhe = {"mode": dados.mode, "pages": dados.pages}
    m = wn.modelo(con, tipo)
    try:
        e = tw.da_tela(con, dados.event, "account", ip=auth._ip(request), user_agent=request.headers.get("user-agent"),
                       detail=detalhe, account_id=cid, pilot_id=pid, client_id=p.get("client_id"), kind=tipo,
                       template_version_id=m.get("version_id") if m else None)
    except ValueError:
        raise HTTPException(400, "Unknown event.")
    except tw.Demais as ex:
        raise HTTPException(429, str(ex))
    return {"ok": True, "id": e["id"]}


@r.get("/waivers/{wid}/pdf")
def waiver_assinada_pdf(wid: int, request: Request, cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    """O PDF assinado (documento + página de assinatura e certificado), só da própria conta."""
    from command_center.providers import trilha_waiver as tw, waiver_nativa as wn
    w = wn.da_conta(con, cid, wid)
    if not w or not w["pdf_path"] or not os.path.isfile(w["pdf_path"]):
        raise HTTPException(404, "Waiver not found.")
    tw.registrar(con, "downloaded", "account", ip=auth._ip(request), user_agent=request.headers.get("user-agent"),
                 detail={"by": "signer"}, account_id=cid, waiver_id=wid, pilot_id=w["pilot_id"], client_id=w["client_id"],
                 kind=w["template"])
    with open(w["pdf_path"], "rb") as f:
        return Response(content=f.read(), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="URACE-waiver-{wid}.pdf"', "Cache-Control": "no-store"})


# ------------------------------------------------------------------ convite da waiver por e-mail (#135)
# Sem conta e sem login: o link (segredo + selo) é quem autentica, e o código no e-mail confirma
# a caixa na hora de assinar. O card, o piloto e o modelo vêm do convite; nada aqui escolhe card.
class ConviteAssinarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")      # um client_id ou driver_id no corpo é recusado (422)
    typed_name: str
    signature: str
    read_and_agree: bool = False
    consent_esign: bool = False
    english_understood: bool = False
    relationship: str | None = None
    guardian_declaration: bool = False
    document_read_at: str | None = None
    document_read_mode: str | None = None
    sign_code: str | None = None
    review_id: int | None = Field(None, ge=1, le=2**63 - 1)   # #112
    name_mismatch_confirmed: bool = False


def _convite_recusado(con, request, e):
    """410 para link usado, trocado, vencido ou de card que mudou; 404 para o que não é link nosso.
    A tentativa num convite conhecido vai para a auditoria do card (o link em si nunca)."""
    if e.convite:
        auditar(con, "waiver.invite.refused", f"invite:{e.convite['id']}", entity_type="client",
                entity_id=e.convite["client_id"], detail={"invite": e.convite["id"], "estado": e.estado}, ip=auth._ip(request))
    return HTTPException(404 if e.estado == "invalid" else 410, str(e), headers={"X-Invite-State": e.estado})


@r.get("/invite/{token}")
def convite(token: str, request: Request, response: Response, con: sqlite3.Connection = Depends(get_db)):
    from command_center.providers import convite_waiver as cw
    try:
        d = cw.ver(con, token, ip=auth._ip(request), aparelho=request.headers.get("user-agent"))
    except cw.LinkInvalido as e:
        raise _convite_recusado(con, request, e)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    return d


@r.get("/invite/{token}/pdf")
def convite_pdf(token: str, request: Request, con: sqlite3.Connection = Depends(get_db)):
    from command_center.providers import convite_waiver as cw
    try:
        pdf = cw.pdf_do_modelo(con, token, ip=auth._ip(request), aparelho=request.headers.get("user-agent"))
    except cw.LinkInvalido as e:
        raise _convite_recusado(con, request, e)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="URACE-waiver.pdf"', "Cache-Control": "no-store"})


@r.post("/invite/{token}/code")
def convite_codigo(token: str, request: Request, con: sqlite3.Connection = Depends(get_db)):
    from command_center.providers import codigos, convite_waiver as cw, email_envio
    try:
        return cw.emitir_codigo(con, token, ip=auth._ip(request), aparelho=request.headers.get("user-agent"))
    except cw.LinkInvalido as e:
        raise _convite_recusado(con, request, e)
    except codigos.ErroCodigo as e:
        raise HTTPException(429, str(e))
    except email_envio.ErroEnvio:
        raise HTTPException(503, "We could not send the email right now. Try again in a few minutes.")


@r.post("/invite/{token}/events", status_code=201)
def convite_evento(token: str, dados: EventoTelaIn, request: Request, con: sqlite3.Connection = Depends(get_db)):
    """#111: o que só a tela do convite sabe (leu todas as páginas), com lista fechada e limite de chamadas."""
    from command_center.providers import convite_waiver as cw, trilha_waiver as tw
    try:
        e = cw.evento_da_tela(con, token, dados.event, dados.mode, dados.pages, ip=auth._ip(request),
                              aparelho=request.headers.get("user-agent"))
    except cw.LinkInvalido as ex:
        raise _convite_recusado(con, request, ex)
    except tw.Demais as ex:
        raise HTTPException(429, str(ex))
    except ValueError:
        raise HTTPException(400, "Unknown event.")
    return {"ok": True, "id": e["id"]}


@r.post("/invite/{token}/review", status_code=201)
def convite_revisar(token: str, dados: ConviteAssinarIn, request: Request, con: sqlite3.Connection = Depends(get_db)):
    """#112, passo 1 pelo convite: confere tudo menos o código e devolve o resumo."""
    from command_center.providers import convite_waiver as cw, revisao_waiver as rv, waiver_nativa as wn
    try:
        return cw.revisar(con, token, dados.model_dump(), ip=auth._ip(request), aparelho=request.headers.get("user-agent"))
    except cw.LinkInvalido as e:
        raise _convite_recusado(con, request, e)
    except wn.ErroWaiver as e:
        raise HTTPException(400, str(e))
    except rv.Demais as e:
        raise HTTPException(429, str(e))


@r.post("/invite/{token}/sign", status_code=201)
def convite_assinar(token: str, dados: ConviteAssinarIn, request: Request, con: sqlite3.Connection = Depends(get_db)):
    from command_center.providers import convite_waiver as cw, waiver_nativa as wn
    try:
        w, _inv = cw.assinar(con, token, dados.model_dump(), ip=auth._ip(request), aparelho=request.headers.get("user-agent"))
    except cw.LinkInvalido as e:
        raise _convite_recusado(con, request, e)
    except wn.ErroWaiver as e:
        raise HTTPException(400, str(e))
    return {"signed_at": w["completed_at"], "valid_until": w["expires_at"], "driver": w["minor_name"] or _inv["driver_name"]}


@r.get("/invite/{token}/signed.pdf")
def convite_pdf_assinado(token: str, request: Request, con: sqlite3.Connection = Depends(get_db)):
    """A cópia de quem assinou, pelo mesmo link, até a validade do convite."""
    from command_center.providers import convite_waiver as cw
    w = cw.pdf_assinado(con, token, ip=auth._ip(request), aparelho=request.headers.get("user-agent"))
    if not w:
        raise HTTPException(404, "Signed waiver not available from this link.")
    with open(w["pdf_path"], "rb") as f:
        return Response(content=f.read(), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="URACE-waiver-{w["id"]}.pdf"', "Cache-Control": "no-store"})


# ------------------------------------------------------------------ QR do balcão (#87)
@r.get("/drivers/{pid}/qr.svg")
def qr_do_piloto(pid: int, cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    """O QR que o cliente mostra no balcão. Só do piloto desta conta, e só depois que a equipe
    ligou o piloto ao card dele (antes disso não há card para a peça entrar)."""
    from command_center.providers import balcao
    p = next((x for x in portal.pilotos(con, cid) if x["id"] == pid), None)
    if not p or not p.get("client_id"):
        raise HTTPException(404, "QR not available yet.")
    svg = balcao.qr_svg(con, p["client_id"])
    con.commit()
    return Response(content=svg, media_type="image/svg+xml", headers={"Cache-Control": "private, no-store"})

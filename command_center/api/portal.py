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
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from command_center.api import auth
from command_center.db import agora, atualizar, auditar, get_db, inserir, transacao, um
from command_center.providers import agenda_sessoes as ag, portal

r = APIRouter(prefix="/ops/api/portal", tags=["portal"])

COOKIE = "cp_session"
COOKIE_CSRF = "cp_csrf"
DIAS = 30
MAX_CADASTROS_POR_HORA = 10
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


def cliente_atual(request: Request, con: sqlite3.Connection = Depends(get_db)):
    """Dependência: a conta do cliente logado. Escrita exige o CSRF."""
    token = request.cookies.get(COOKIE)
    s = um(con, """SELECT s.account_id, s.expires_at FROM portal_sessions s JOIN portal_accounts a ON a.id=s.account_id
                    WHERE s.id=? AND s.revoked_at IS NULL AND a.active=1""", (_token_hash(token),)) if token else None
    if not s or s["expires_at"] <= agora():
        raise HTTPException(401, "Please sign in.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        c, h = request.cookies.get(COOKIE_CSRF, ""), request.headers.get("x-csrf", "")
        if not c or not hmac.compare_digest(c, h):
            raise HTTPException(403, "Security check failed. Reload the page and try again.")
    return s["account_id"]


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
    phone: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    accept_terms: bool = False
    i_am_driver: bool = False


@r.post("/signup", status_code=201)
def cadastro(dados: CadastroIn, request: Request, response: Response, con: sqlite3.Connection = Depends(get_db)):
    ip = auth._ip(request)
    desde = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    if um(con, "SELECT COUNT(*) AS n FROM login_attempts WHERE key=? AND at>?", (f"portal-signup:{ip}", desde))["n"] >= MAX_CADASTROS_POR_HORA:
        raise HTTPException(429, "Too many sign-ups from this connection. Try again later.")
    if not auth.senha_aceitavel(dados.password) or len(dados.password) < 8:
        raise HTTPException(400, "Use a password with at least 8 characters.")
    inserir(con, "login_attempts", key=f"portal-signup:{ip}", ok=1)
    sal, h = auth.hash_senha(dados.password)
    try:
        cid = portal.criar_conta(con, dados.model_dump(exclude={"password"}), sal, h)
    except portal.ErroPortal as e:
        con.commit()                              # a tentativa conta para o limite
        raise _erro(e)
    _abrir(con, request, response, cid)
    _aud(con, request, "portal.signup", cid, {"piloto_proprio": dados.i_am_driver})
    con.commit()
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
    phone: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None


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


# ------------------------------------------------------------------ pilotos
class PilotoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    birth_date: str | None = None
    email: str | None = None
    phone: str | None = None
    notes: str | None = None
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
def disponibilidade(start: str | None = None, end: str | None = None, cid=Depends(cliente_atual),
                    con: sqlite3.Connection = Depends(get_db)):
    """O que o cliente pode marcar: só aberto/fechado e vagas, sem o motivo interno."""
    from datetime import date
    try:
        d = ag.disponibilidade(con, date.fromisoformat(start) if start else None, date.fromisoformat(end) if end else None)
    except (ValueError, ag.ErroAgenda):
        raise HTTPException(400, "Choose a valid date range.")
    for dia in d["dias"]:
        for p in ("manha", "tarde"):
            dia["periods"][p] = {"open": dia["periods"][p]["open"], "spots": dia["periods"][p]["spots"]}
    return d


@r.get("/bookings")
def meus_agendamentos(cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    return {"bookings": ag.do_cliente(con, cid)}


class AgendarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: str
    period: str
    driver_id: int | None = None
    notes: str | None = None


@r.post("/bookings", status_code=201)
def agendar(dados: AgendarIn, request: Request, cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    try:
        with transacao(con):                  # duas pessoas na última vaga: só uma leva
            bid = ag.agendar(con, cid, dados.date, dados.period, dados.driver_id, dados.notes)
            _aud(con, request, "portal.booking", cid, {"agendamento": bid, "data": dados.date, "periodo": dados.period})
    except ag.ErroAgenda as e:
        raise HTTPException(400, str(e))
    return {"id": bid, "bookings": ag.do_cliente(con, cid)}


@r.post("/bookings/{bid}/cancel")
def cancelar(bid: int, request: Request, cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    try:
        ag.cancelar_pelo_cliente(con, cid, bid)
    except ag.ErroAgenda as e:
        raise HTTPException(404 if "not found" in str(e) else 400, str(e))
    _aud(con, request, "portal.booking.cancel", cid, {"agendamento": bid})
    con.commit()
    return {"bookings": ag.do_cliente(con, cid)}

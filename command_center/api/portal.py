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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from command_center.api import auth
from command_center.db import agora, atualizar, auditar, get_db, inserir, transacao, um
from command_center.providers import agenda_asana, agenda_sessoes as ag, portal, servicos_site, vinculo_site

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
def disponibilidade(start: str | None = None, end: str | None = None, cid=Depends(cliente_atual),
                    con: sqlite3.Connection = Depends(get_db)):
    """O que o cliente pode marcar: só aberto/fechado e vagas, sem o motivo interno."""
    try:
        d = ag.disponibilidade(con, date.fromisoformat(start) if start else None, date.fromisoformat(end) if end else None)
    except (ValueError, ag.ErroAgenda):
        raise HTTPException(400, "Choose a valid date range.")
    for dia in d["dias"]:
        for p in ("manha", "tarde"):
            dia["periods"][p] = {"open": dia["periods"][p]["open"], "spots": dia["periods"][p]["spots"]}
    return {**d, "services": servicos_site.para_cliente(con), "auto_sell": bool(ag.config(con).get("auto_sell"))}


@r.get("/bookings")
def meus_agendamentos(cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    return {"bookings": ag.do_cliente(con, cid)}


class AgendarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: str
    period: str
    service_id: int | None = None
    driver_id: int | None = None
    notes: str | None = None
    origin: str | None = None                # #164: "site" quando veio do site novo
    utm: dict | None = None                  # #164: utm_source, utm_campaign… (para o marketing)


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
    try:
        with transacao(con):                  # duas pessoas na última vaga: só uma leva
            bid = ag.agendar(con, cid, dados.date, dados.period, dados.driver_id, dados.notes, dados.service_id)
            from command_center.providers import cobranca_agenda, venda_site
            atualizar(con, "bookings", bid, origin="site" if dados.origin == "site" else "portal",
                      utm=venda_site.utm_limpo(dados.utm))
            cobranca_agenda.ao_marcar(con, bid)      # contrato + waiver em dia: confirma sozinha (dono, 06/10)
            _aud(con, request, "portal.booking", cid, {"agendamento": bid, "data": dados.date, "periodo": dados.period,
                                                        "servico": dados.service_id})
    except ag.ErroAgenda as e:
        raise HTTPException(400, str(e))
    tarefas.add_task(agenda_asana.levar, bid)      # #67: todo agendamento vira tarefa no Asana
    from command_center.providers import venda_site
    if venda_site.ligada(con):
        tarefas.add_task(_vender, bid)
    return {"id": bid, "bookings": ag.do_cliente(con, cid), "auto_sell": venda_site.ligada(con)}


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
def waiver_modelo_pdf(kind: str, request: Request, cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    from command_center.providers import waiver_nativa as wn
    m = wn.modelo(con, kind) if wn.ligada(con) else None
    if not m:
        raise HTTPException(404, "Waiver not available.")
    with open(m["pdf_path"], "rb") as f:
        pdf = f.read()
    # #107: a prova de que o documento chegou a quem assina — o assinar exige este registro
    _aud(con, request, "portal.waiver.document_view", cid, {"kind": kind, "sha256": m["sha256"]})
    con.commit()
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="URACE-waiver-{kind}.pdf"', "Cache-Control": "no-store"})


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


@r.get("/waivers/{wid}/pdf")
def waiver_assinada_pdf(wid: int, cid=Depends(cliente_atual), con: sqlite3.Connection = Depends(get_db)):
    """O PDF assinado (documento + página de assinatura e certificado), só da própria conta."""
    from command_center.providers import waiver_nativa as wn
    w = wn.da_conta(con, cid, wid)
    if not w or not w["pdf_path"] or not os.path.isfile(w["pdf_path"]):
        raise HTTPException(404, "Waiver not found.")
    with open(w["pdf_path"], "rb") as f:
        return Response(content=f.read(), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="URACE-waiver-{wid}.pdf"', "Cache-Control": "no-store"})


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

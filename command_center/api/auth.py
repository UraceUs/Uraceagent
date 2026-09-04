"""Autenticação, sessão, RBAC e auditoria do Command Center.

Decisões (ADR §2):
  * senha em scrypt com sal por usuário; nunca a senha, nunca reversível.
  * sessão = token aleatório no cookie; no banco fica só o SHA-256 dele.
    Revogar é marcar `revoked_at` — vale na hora, sem esperar expirar.
  * cookie HttpOnly + Secure + SameSite=Strict. Mutações exigem o header
    `X-CSRF` igual ao cookie `cc_csrf` (double-submit) — o SameSite já
    barra o caso comum; o header barra o resto.
  * rate limit por IP e por e-mail, com a mesma mensagem para tudo:
    "Invalid email or password." Nunca dizer se o e-mail existe.
  * RBAC checado AQUI, por rota. O frontend só esconde botão.
  * tudo que importa vai para audit_logs (login, falha, logout, revogação,
    mudança de usuário/papel).
"""
import base64
import hashlib
import hmac
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response, status

from command_center.db import agora, atualizar, auditar, get_db, inserir, todos, um

SESSAO_HORAS = 12
LEMBRAR_DIAS = 30
MAX_FALHAS = 5            # por chave (ip ou e-mail) na janela
JANELA_MIN = 15
COOKIE_SESSAO = "cc_session"
COOKIE_CSRF = "cc_csrf"
PAPEIS = ("ADMIN", "MANAGER", "OPERATOR", "VIEWER")
NIVEL = {p: i for i, p in enumerate(reversed(PAPEIS))}   # ADMIN=3 … VIEWER=0
MSG_CREDENCIAL = "Invalid email or password."


# ------------------------------------------------------------- senha
def _scrypt(senha, sal):
    return hashlib.scrypt(senha.encode(), salt=sal, n=2 ** 15, r=8, p=1,
                          dklen=32, maxmem=64 * 1024 * 1024)


def hash_senha(senha):
    sal = secrets.token_bytes(16)
    return base64.b64encode(sal).decode(), base64.b64encode(_scrypt(senha, sal)).decode()


def confere_senha(senha, sal_b64, hash_b64):
    return hmac.compare_digest(_scrypt(senha, base64.b64decode(sal_b64)),
                               base64.b64decode(hash_b64))


# Mínimo de 5 por decisão do dono (04/09/2026). O que segura a porta é o
# bloqueio de tentativas (5 erros em 15 min por IP e por e-mail) — não
# afrouxe os dois ao mesmo tempo.
SENHA_MIN = 5


def senha_aceitavel(s):
    return isinstance(s, str) and SENHA_MIN <= len(s) <= 200


# ----------------------------------------------------------- usuários
def criar_usuario(con, email, name, role, senha, por_user_id=None, ip=None):
    if role not in PAPEIS:
        raise ValueError("papel inválido")
    if not senha_aceitavel(senha):
        raise ValueError(f"senha: mínimo {SENHA_MIN} caracteres")
    sal, h = hash_senha(senha)
    uid = inserir(con, "users", email=email.strip().lower(), name=name.strip(),
                  role=role, pw_salt=sal, pw_hash=h)
    auditar(con, "user.create", f"user:{por_user_id}" if por_user_id else "system",
            user_id=por_user_id, entity_type="user", entity_id=uid,
            detail={"email": email.strip().lower(), "role": role}, ip=ip)
    return uid


def trocar_senha(con, user_id, senha, por_user_id, ip=None):
    if not senha_aceitavel(senha):
        raise ValueError(f"senha: mínimo {SENHA_MIN} caracteres")
    sal, h = hash_senha(senha)
    atualizar(con, "users", user_id, pw_salt=sal, pw_hash=h)
    # senha nova derruba toda sessão aberta daquele usuário
    con.execute("UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (agora(), user_id))
    auditar(con, "user.password_change", f"user:{por_user_id}", user_id=por_user_id,
            entity_type="user", entity_id=user_id, ip=ip)


# ---------------------------------------------------------- rate limit
def _falhas_recentes(con, chave):
    desde = (datetime.now(timezone.utc) - timedelta(minutes=JANELA_MIN)).strftime("%Y-%m-%dT%H:%M:%S")
    r = um(con, "SELECT COUNT(*) AS n FROM login_attempts WHERE key = ? AND ok = 0 AND at > ?",
           (chave, desde))
    return r["n"] if r else 0


def _registra_tentativa(con, chave, ok):
    inserir(con, "login_attempts", key=chave, ok=1 if ok else 0)


# --------------------------------------------------------------- sessão
def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def abrir_sessao(con, user_id, lembrar, ip, user_agent):
    token = secrets.token_urlsafe(32)
    horas = LEMBRAR_DIAS * 24 if lembrar else SESSAO_HORAS
    expira = (datetime.now(timezone.utc) + timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    con.execute("INSERT INTO sessions (id, user_id, expires_at, ip, user_agent) VALUES (?,?,?,?,?)",
                (_hash_token(token), user_id, expira, ip, (user_agent or "")[:200]))
    return token, horas * 3600


def sessao_valida(con, token):
    if not token:
        return None
    s = um(con, """SELECT s.id, s.user_id, s.expires_at, u.email, u.name, u.role, u.active
                   FROM sessions s JOIN users u ON u.id = s.user_id
                   WHERE s.id = ? AND s.revoked_at IS NULL""", (_hash_token(token),))
    if not s or not s["active"]:
        return None
    if s["expires_at"] <= agora():
        return None
    return s


def revogar_sessao(con, token):
    con.execute("UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (agora(), _hash_token(token)))


def revogar_todas(con, user_id):
    con.execute("UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (agora(), user_id))


def _ip(request):
    xff = request.headers.get("x-forwarded-for", "")
    return (xff.split(",")[0].strip() if xff else request.client.host if request.client else "?")


def _seguro(request):
    """Cookie Secure só quando de fato há TLS na frente (Caddy) — em
    desenvolvimento local, http://127.0.0.1 não entregaria o cookie."""
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def login(con, request, response, email, senha, lembrar=False):
    email = (email or "").strip().lower()
    ip = _ip(request)
    chave_ip, chave_email = f"ip:{ip}", f"email:{email}"
    if _falhas_recentes(con, chave_ip) >= MAX_FALHAS or _falhas_recentes(con, chave_email) >= MAX_FALHAS:
        auditar(con, "auth.rate_limited", "system", detail={"email": email}, ip=ip)
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")

    u = um(con, "SELECT * FROM users WHERE email = ?", (email,))
    ok = bool(u and u["active"] and confere_senha(senha or "", u["pw_salt"], u["pw_hash"]))
    if not u:
        # custo parecido com uma checagem real, para não revelar existência pelo tempo
        _scrypt(senha or "", b"0" * 16)
    _registra_tentativa(con, chave_ip, ok)
    _registra_tentativa(con, chave_email, ok)
    if not ok:
        auditar(con, "auth.fail", "system", detail={"email": email,
                "reason": "inactive" if (u and not u["active"]) else "credentials"}, ip=ip)
        time.sleep(0.4)
        raise HTTPException(401, MSG_CREDENCIAL)

    token, max_age = abrir_sessao(con, u["id"], lembrar, ip, request.headers.get("user-agent"))
    csrf = secrets.token_urlsafe(24)
    atualizar(con, "users", u["id"], last_login_at=agora())
    auditar(con, "auth.login", f"user:{u['id']}", user_id=u["id"], ip=ip,
            detail={"remember": bool(lembrar)})
    seguro = _seguro(request)
    response.set_cookie(COOKIE_SESSAO, token, max_age=max_age, httponly=True,
                        secure=seguro, samesite="strict", path="/")
    response.set_cookie(COOKIE_CSRF, csrf, max_age=max_age, httponly=False,
                        secure=seguro, samesite="strict", path="/")
    return {"id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"]}


def logout(con, request, response):
    token = request.cookies.get(COOKIE_SESSAO)
    s = sessao_valida(con, token)
    if token:
        revogar_sessao(con, token)
    if s:
        auditar(con, "auth.logout", f"user:{s['user_id']}", user_id=s["user_id"], ip=_ip(request))
    for c in (COOKIE_SESSAO, COOKIE_CSRF):
        response.delete_cookie(c, path="/")


# ------------------------------------------------------------ guardas
def usuario_atual(request: Request, con: sqlite3.Connection = Depends(get_db)):
    s = sessao_valida(con, request.cookies.get(COOKIE_SESSAO))
    if not s:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf_cookie = request.cookies.get(COOKIE_CSRF, "")
        csrf_header = request.headers.get("x-csrf", "")
        if not csrf_cookie or not hmac.compare_digest(csrf_cookie, csrf_header):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF check failed.")
    return {"id": s["user_id"], "email": s["email"], "name": s["name"], "role": s["role"]}


def exige(papel_minimo):
    """Dependência: o usuário precisa ter pelo menos este papel."""
    if papel_minimo not in PAPEIS:
        raise ValueError(papel_minimo)

    def _guarda(u=Depends(usuario_atual)):
        if NIVEL[u["role"]] < NIVEL[papel_minimo]:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "You don't have permission to do this.")
        return u
    return _guarda


def pode(role, papel_minimo):
    return NIVEL.get(role, -1) >= NIVEL[papel_minimo]

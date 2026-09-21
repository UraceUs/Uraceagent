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
import os
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
# 17/09, correção do dono: "vendas e operador devem ser a mesma coisa, com os acessos de
# operador". Existiu um papel CLOSER por algumas horas; quem vende é OPERATOR, e a área de
# vendas é uma tela do operador como qualquer outra. Banco antigo com role='CLOSER' é
# convertido em OPERATOR na migração.
NIVEL = {"ADMIN": 3, "MANAGER": 2, "OPERATOR": 1, "VIEWER": 0}
MSG_CREDENCIAL = "Invalid email or password."

# Acesso livre (dono, 17/09): "ele opera em todas as áreas, então não precisa
# nem de nomenclatura de cargo — ele tem acesso livre e irrestrito". Na prática
# a conta é ADMIN; a diferença é que o painel não mostra cargo nenhum e ninguém
# rebaixa a conta por engano. A lista pode crescer por CC_ACESSO_LIVRE
# (e-mails separados por vírgula) sem mexer no código.
ACESSO_LIVRE = tuple(
    e.strip().lower() for e in os.environ.get(
        "CC_ACESSO_LIVRE", "eduardoffresende@gmail.com").split(",") if e.strip()
)


def livre(email):
    """A conta tem acesso livre e irrestrito (sem cargo)?"""
    return (email or "").strip().lower() in ACESSO_LIVRE


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
    return {"id": u["id"], "email": u["email"], "name": u["name"],
            "role": u["role"], "free": livre(u["email"])}


def logout(con, request, response):
    token = request.cookies.get(COOKIE_SESSAO)
    s = sessao_valida(con, token)
    if token:
        revogar_sessao(con, token)
    if s:
        auditar(con, "auth.logout", f"user:{s['user_id']}", user_id=s["user_id"], ip=_ip(request))
    for c in (COOKIE_SESSAO, COOKIE_CSRF):
        response.delete_cookie(c, path="/")


# ------------------------------------------------------------ chave de API
# Dono, 21/09: "preciso montar uma chave api desse command center". Outro sistema
# (n8n, script, integração) precisa falar com o painel sem navegador — e sem afrouxar
# nada do que já protege a porta.
#
# Formato:  urk_<id>_<segredo>   ·  id público (vai no log), segredo de 32 bytes.
# No banco fica só o HASH do segredo (scrypt, como senha). Quem perde a chave cria
# outra; ninguém — nem o ADMIN, nem eu — consegue ler a chave depois de criada.
#
# Três travas que valem mais que o resto:
#   1. a chave age como uma PESSOA e o papel dela nunca passa do papel dessa pessoa;
#   2. chave nenhuma herda "acesso livre": conta sem cargo não vira chave sem limite;
#   3. quem entra por chave não recebe cookie e não passa por CSRF (não há cookie para
#      um site de terceiro abusar) — mas também não ganha sessão nem troca senha.
#
# E uma quarta, que veio do uso real (21/09: a chave é para um agente de IA fora do
# painel, com acesso ao financeiro): **papel e permissão de escrever são coisas
# separadas**. `read_only` deixa a chave ver tudo o que o papel dela alcança e não mexer
# em nada — porque "ver o financeiro" e "mandar mensagem para cliente" não deveriam vir
# no mesmo pacote. O padrão é só leitura; escrever é a exceção, marcada na mão.
PREFIXO_CHAVE = "urk"


def gerar_chave():
    """Devolve (id_publico, segredo, chave_inteira). A chave inteira só existe aqui."""
    ident = secrets.token_hex(5)
    segredo = secrets.token_urlsafe(32)
    return ident, segredo, f"{PREFIXO_CHAVE}_{ident}_{segredo}"


def criar_chave(con, nome, papel, user_id, por_user_id=None, dias=None, nota=None, somente_leitura=True):
    """Cria e devolve a chave inteira UMA vez. Depois disto, só o hash existe."""
    if papel not in PAPEIS:
        raise ValueError(f"papel inválido: use um de {', '.join(PAPEIS)}")
    dono = um(con, "SELECT id, email, role, active FROM users WHERE id = ?", (user_id,))
    if not dono or not dono["active"]:
        raise ValueError("a chave precisa de uma pessoa ativa para agir como ela")
    teto = "ADMIN" if livre(dono["email"]) else dono["role"]
    if NIVEL[papel] > NIVEL[teto]:
        raise ValueError(f"a chave não pode ter mais acesso que {dono['email']} ({teto})")
    ident, segredo, inteira = gerar_chave()
    sal, h = hash_senha(segredo)
    expira = ((datetime.now(timezone.utc) + timedelta(days=int(dias))).strftime("%Y-%m-%dT%H:%M:%SZ")
              if dias else None)
    con.execute("""INSERT INTO api_keys (id, name, salt, hash, role, user_id, created_by, expires_at, note, read_only)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (ident, (nome or "sem nome")[:80], sal, h, papel, user_id, por_user_id, expira, (nota or None),
                 1 if somente_leitura else 0))
    auditar(con, "apikey.create", f"user:{por_user_id}" if por_user_id else "system", user_id=por_user_id,
            entity_type="api_key", entity_id=None,
            detail={"chave": ident, "nome": nome, "papel": papel, "como": dono["email"], "expira": expira,
                    "so_leitura": bool(somente_leitura)})
    con.commit()
    return {"id": ident, "chave": inteira, "role": papel, "expires_at": expira,
            "read_only": bool(somente_leitura)}


def revogar_chave(con, ident, por_user_id=None):
    k = um(con, "SELECT id, name FROM api_keys WHERE id = ? AND revoked_at IS NULL", (ident,))
    if not k:
        return False
    con.execute("UPDATE api_keys SET revoked_at = ? WHERE id = ?", (agora(), ident))
    auditar(con, "apikey.revoke", f"user:{por_user_id}" if por_user_id else "system", user_id=por_user_id,
            entity_type="api_key", entity_id=None, detail={"chave": ident, "nome": k["name"]})
    con.commit()
    return True


def _chave_do_pedido(request):
    """`Authorization: Bearer urk_...` ou `X-API-Key: urk_...`."""
    bruto = request.headers.get("x-api-key") or ""
    if not bruto:
        cabecalho = request.headers.get("authorization") or ""
        if cabecalho[:7].lower() == "bearer ":
            bruto = cabecalho[7:]
    bruto = bruto.strip()
    if not bruto.startswith(PREFIXO_CHAVE + "_"):
        return None, None
    partes = bruto.split("_", 2)
    return (partes[1], partes[2]) if len(partes) == 3 and partes[1] and partes[2] else (None, None)


def chave_valida(con, request, tocar=True):
    """Confere a chave do pedido. Devolve o usuário efetivo ou None.

    Papel efetivo = o menor entre o papel da chave e o papel de quem ela representa: se a
    pessoa foi rebaixada depois, a chave desce junto, sem ninguém lembrar de revogar."""
    ident, segredo = _chave_do_pedido(request)
    if not ident:
        return None
    k = um(con, """SELECT k.*, u.email, u.name, u.role AS papel_pessoa, u.active
                   FROM api_keys k JOIN users u ON u.id = k.user_id
                   WHERE k.id = ? AND k.revoked_at IS NULL""", (ident,))
    if not k or not k["active"]:
        return None
    if k["expires_at"] and k["expires_at"] <= agora():
        return None
    if not confere_senha(segredo, k["salt"], k["hash"]):
        return None
    teto = "ADMIN" if livre(k["email"]) else k["papel_pessoa"]
    papel = k["role"] if NIVEL[k["role"]] <= NIVEL[teto] else teto
    if tocar:
        # uma escrita por minuto, no máximo: saber que a chave está viva não vale
        # um UPDATE a cada GET de uma integração que consulta de dez em dez segundos
        con.execute("""UPDATE api_keys SET uses = uses + 1, last_used_at = ?, last_ip = ?
                       WHERE id = ? AND (last_used_at IS NULL OR last_used_at < ?)""",
                    (agora(), _ip(request), ident,
                     (datetime.now(timezone.utc) - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")))
        con.commit()
    # `free` fica FALSO de propósito: acesso livre é da pessoa no navegador, não da chave.
    return {"id": k["user_id"], "email": k["email"], "name": f"{k['name']} (chave)",
            "role": papel, "free": False, "via": f"key:{ident}",
            "somente_leitura": bool(k["read_only"])}


# ------------------------------------------------------------ guardas
def usuario_atual(request: Request, con: sqlite3.Connection = Depends(get_db)):
    porchave = chave_valida(con, request)
    if porchave:
        if porchave["somente_leitura"] and request.method not in ("GET", "HEAD", "OPTIONS"):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "Esta chave é só de leitura: ela consulta o painel e não muda nada. "
                                "Para deixá-la agir, crie outra chave sem 'só leitura'.")
        return porchave                       # sem cookie, sem CSRF: não há cookie para abusar
    s = sessao_valida(con, request.cookies.get(COOKIE_SESSAO))
    if not s:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf_cookie = request.cookies.get(COOKIE_CSRF, "")
        csrf_header = request.headers.get("x-csrf", "")
        if not csrf_cookie or not hmac.compare_digest(csrf_cookie, csrf_header):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF check failed.")
    return {"id": s["user_id"], "email": s["email"], "name": s["name"],
            "role": s["role"], "free": livre(s["email"])}


def exige(papel_minimo):
    """Dependência: o usuário precisa ter pelo menos este papel."""
    if papel_minimo not in PAPEIS:
        raise ValueError(papel_minimo)

    def _guarda(u=Depends(usuario_atual)):
        if u.get("free"):
            return u
        if NIVEL[u["role"]] < NIVEL[papel_minimo]:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "You don't have permission to do this.")
        return u
    return _guarda


def pode(role, papel_minimo):
    return NIVEL.get(role, -1) >= NIVEL[papel_minimo]

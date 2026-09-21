"""URACE Command Center — API.

    uvicorn command_center.api.main:app --host 127.0.0.1 --port 8790

Serve também o frontend compilado (command_center/web/dist) em /ops.
O Caddy põe TLS e encaminha /ops* para cá.
"""
import os
import sqlite3

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from command_center.api import auth, dialpad, ia, rotas
from command_center.db import auditar, aplicar_schema, conectar, get_db, todos, um

BASE = "/ops"
AQUI = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.normpath(os.path.join(AQUI, "..", "web", "dist"))

from contextlib import asynccontextmanager


def _limpar_sandboxes():
    """Para os sandboxes ociosos do agente. Cada sessão do OpenClaw sobe um
    container que fica de pé por horas (09/09: 6 containers, VPS de 1,9 GB).
    Só mexe quando nenhum `openclaw agent` está rodando — aí todos estão ociosos."""
    import subprocess
    agente = os.environ.get("OPENCLAW_AGENT", "urace-admin")
    try:
        if subprocess.run(["pgrep", "-f", "openclaw agent"], capture_output=True, timeout=10).returncode == 0:
            return 0
        ids = subprocess.run(["docker", "ps", "-q", "--filter", f"name=openclaw-sbx-agent-{agente}"],
                             capture_output=True, text=True, timeout=20).stdout.split()
        if ids:
            subprocess.run(["docker", "stop", *ids], capture_output=True, timeout=120)
        return len(ids)
    except Exception:
        return 0


def _autosync():
    """A cada N minutos: espelha as fontes e acorda a IA para o que mudou.
    É o que faz "a IA agir a cada alteração" sem ninguém clicar."""
    import threading
    import time
    from command_center.api import motor
    from command_center.db import agora, um
    minutos = int(os.environ.get("CC_AUTOSYNC_MIN", "15"))
    time.sleep(20)                                        # deixa o serviço subir
    while True:
        from command_center.api import rotas
        con = conectar()
        try:
            admin = um(con, "SELECT id FROM users WHERE role='ADMIN' AND active=1 ORDER BY id LIMIT 1")
            with rotas._SYNC_LOCK:
                pode = admin is not None and not rotas._SYNC["running"]
                if pode:
                    rotas._SYNC.update(running=True, started_at=agora(), finished_at=None, result=None, by=admin["id"])
            if pode:
                motor.eventos_do_dia_1(con)                # mensalidades: uma por cliente com plano, no dia 1
                rotas._sync_thread(admin["id"], None)      # mesma rotina do botão, mesma trava
                auditar(con, "sync.auto", "system", detail=rotas._SYNC.get("result"))
            parados = _limpar_sandboxes()
            if parados:
                auditar(con, "sandbox.cleanup", "system", detail={"parados": parados})
            from command_center.api import agenda   # rotinas por horário: triagem do Gmail, sondagem manhã/noite
            agenda.rodar(con)
        except Exception as e:                            # nunca derruba o laço
            try:
                auditar(con, "sync.auto.failed", "system", detail={"erro": f"{type(e).__name__}: {str(e)[:300]}"})
            except Exception:
                pass
        finally:
            con.close()
        time.sleep(minutos * 60)


def _laco_do_chat():
    """A resposta no chat não pode depender de alguém abrir a tela.

    Até 21/09 a entrega tinha UMA chance: se o Salesbot não abrisse o canal naquele
    instante, a mensagem ficava parada até alguém abrir a conversa no painel — e o
    dono descobria dias depois. Este laço insiste a cada meio minuto e desiste só
    quando o prazo acaba, gravando nota no lead e acendendo o aviso.

    Meio minuto é de propósito: a janela de continuação do bot é de menos de um
    minuto, e perder essa janela é perder a entrega instantânea."""
    import time
    from command_center.db import auditar, conectar
    time.sleep(25)
    segundos = int(os.environ.get("CC_CHAT_SEG", "30"))
    while True:
        con = conectar()
        try:
            from command_center.db import agora as _agora
            from command_center.api import crm
            r = crm.empurrar_fila(con)
            desistiu = crm.varrer_fila(con)
            con.commit()
            crm.BATIDA.update(em=_agora(), ciclos=crm.BATIDA["ciclos"] + 1,
                              ultimo=({**r, "desistiu": desistiu} if (r["entregues"] or desistiu or r["falhas"])
                                      else crm.BATIDA["ultimo"]))
            if r["entregues"] or desistiu or r["falhas"]:
                auditar(con, "crm.fila", "system", detail={**r, "desistiu": desistiu})
                con.commit()
        except Exception as e:                            # nunca derruba o laço
            try:
                auditar(con, "crm.fila.failed", "system", detail={"erro": f"{type(e).__name__}: {str(e)[:300]}"})
                con.commit()
            except Exception:
                pass
        finally:
            con.close()
        time.sleep(segundos)


@asynccontextmanager
async def _ciclo(app):
    con = conectar()
    try:
        aplicar_schema(con)
    finally:
        con.close()
    if os.environ.get("CC_AUTOSYNC", "1") == "1":
        import threading
        threading.Thread(target=_autosync, daemon=True, name="cc-autosync").start()
        threading.Thread(target=_laco_do_chat, daemon=True, name="cc-chat").start()
    yield


app = FastAPI(title="URACE Command Center", docs_url=None, redoc_url=None,
              openapi_url=None, lifespan=_ciclo)


@app.middleware("http")
async def _cabecalhos(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = resp.headers.get("Cache-Control", "no-store")
    if "Content-Security-Policy" in resp.headers:      # rota com política própria (corpo de e-mail em iframe)
        return resp
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' "
        "https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
        "connect-src 'self'; frame-ancestors 'none'")
    return resp


app.include_router(rotas.r)
app.include_router(ia.r)
from command_center.api import qbo  # noqa: E402
app.include_router(qbo.r)
from command_center.api import crm  # noqa: E402
app.include_router(crm.r)
from command_center.api import sistema  # noqa: E402
app.include_router(sistema.r)
from command_center.api import vendas  # noqa: E402
app.include_router(vendas.r)
app.include_router(dialpad.r)
from command_center.api import precos  # noqa: E402
app.include_router(precos.r)


# ------------------------------------------------------------- saúde
@app.get(BASE + "/health")
def health():
    return {"ok": True}


@app.get(BASE + "/ready")
def ready(con: sqlite3.Connection = Depends(get_db)):
    con.execute("SELECT 1")
    return {"ok": True, "db": True}


# -------------------------------------------------------------- auth
class LoginIn(BaseModel):
    email: str
    password: str
    remember: bool = False


@app.post(BASE + "/api/auth/login")
def api_login(dados: LoginIn, request: Request, response: Response,
              con: sqlite3.Connection = Depends(get_db)):
    return auth.login(con, request, response, dados.email, dados.password, dados.remember)


@app.post(BASE + "/api/auth/logout")
def api_logout(request: Request, response: Response, con: sqlite3.Connection = Depends(get_db)):
    auth.logout(con, request, response)
    return {"ok": True}


@app.get(BASE + "/api/auth/me")
def api_me(u=Depends(auth.usuario_atual)):
    return u


class SenhaIn(BaseModel):
    current_password: str
    new_password: str


@app.post(BASE + "/api/auth/password")
def api_senha(dados: SenhaIn, request: Request, response: Response,
              u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    reg = um(con, "SELECT pw_salt, pw_hash FROM users WHERE id = ?", (u["id"],))
    if not auth.confere_senha(dados.current_password, reg["pw_salt"], reg["pw_hash"]):
        raise HTTPException(401, auth.MSG_CREDENCIAL)
    try:
        auth.trocar_senha(con, u["id"], dados.new_password, u["id"], auth._ip(request))
    except ValueError as e:
        raise HTTPException(400, str(e))
    auth.logout(con, request, response)
    return {"ok": True, "message": "Password changed. Sign in again."}


# --------------------------------------------------------- usuários (ADMIN)
class UsuarioIn(BaseModel):
    email: str
    name: str
    role: str
    password: str


@app.get(BASE + "/api/users")
def api_users(u=Depends(auth.exige("ADMIN")), con: sqlite3.Connection = Depends(get_db)):
    lista = todos(con, "SELECT id, email, name, role, active, created_at, last_login_at FROM users ORDER BY id")
    # `free` marca a conta de acesso livre (sem cargo) — o painel não mostra papel nela
    for r in lista:
        r["free"] = auth.livre(r["email"])
    return lista


@app.post(BASE + "/api/users", status_code=201)
def api_users_create(dados: UsuarioIn, request: Request, u=Depends(auth.exige("ADMIN")),
                     con: sqlite3.Connection = Depends(get_db)):
    try:
        uid = auth.criar_usuario(con, dados.email, dados.name, dados.role, dados.password,
                                 por_user_id=u["id"], ip=auth._ip(request))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "A user with this email already exists.")
    return {"id": uid}


class AtivoIn(BaseModel):
    active: bool


@app.post(BASE + "/api/users/{uid}/active")
def api_users_active(uid: int, dados: AtivoIn, request: Request, u=Depends(auth.exige("ADMIN")),
                     con: sqlite3.Connection = Depends(get_db)):
    if uid == u["id"] and not dados.active:
        raise HTTPException(400, "You can't deactivate yourself.")
    if not um(con, "SELECT id FROM users WHERE id = ?", (uid,)):
        raise HTTPException(404, "User not found.")
    con.execute("UPDATE users SET active = ? WHERE id = ?", (1 if dados.active else 0, uid))
    if not dados.active:
        auth.revogar_todas(con, uid)
    from command_center.db import auditar
    auditar(con, "user.active", f"user:{u['id']}", user_id=u["id"], entity_type="user",
            entity_id=uid, detail={"active": dados.active}, ip=auth._ip(request))
    return {"ok": True}


class PapelIn(BaseModel):
    role: str


@app.post(BASE + "/api/users/{uid}/role")
def api_users_role(uid: int, dados: PapelIn, request: Request, u=Depends(auth.exige("ADMIN")),
                   con: sqlite3.Connection = Depends(get_db)):
    """Administrador muda o nível de acesso de OUTRA pessoa. Não muda o próprio e não
    deixa a conta sem administrador ativo. A pessoa é derrubada das sessões para
    entrar já com o papel novo."""
    if dados.role not in auth.PAPEIS:
        raise HTTPException(400, f"Papel inválido. Use um de: {', '.join(auth.PAPEIS)}.")
    if uid == u["id"]:
        raise HTTPException(400, "Você não muda o próprio papel; peça a outro administrador.")
    alvo = um(con, "SELECT id, email, role, active FROM users WHERE id = ?", (uid,))
    if not alvo:
        raise HTTPException(404, "User not found.")
    if auth.livre(alvo["email"]):
        raise HTTPException(400, "Esta conta tem acesso livre e irrestrito; não tem cargo para mudar.")
    if alvo["role"] == "ADMIN" and dados.role != "ADMIN":
        n = um(con, "SELECT COUNT(*) AS n FROM users WHERE role='ADMIN' AND active=1 AND id<>?", (uid,))
        if not n or n["n"] == 0:
            raise HTTPException(409, "Esse é o único administrador ativo; promova outro antes.")
    if alvo["role"] == dados.role:
        return {"ok": True, "role": dados.role}
    con.execute("UPDATE users SET role = ? WHERE id = ?", (dados.role, uid))
    auth.revogar_todas(con, uid)
    from command_center.db import auditar as _aud
    _aud(con, "user.role", f"user:{u['id']}", user_id=u["id"], entity_type="user", entity_id=uid,
         detail={"from": alvo["role"], "to": dados.role}, ip=auth._ip(request))
    return {"ok": True, "role": dados.role}


class SenhaDeOutroIn(BaseModel):
    password: str


@app.post(BASE + "/api/users/{uid}/password")
def api_users_password(uid: int, dados: SenhaDeOutroIn, request: Request, u=Depends(auth.exige("ADMIN")),
                       con: sqlite3.Connection = Depends(get_db)):
    """Administrador define a senha de alguém que perdeu a sua (dono, 21/09).

    Não pede a senha antiga — quem esqueceu não a tem. O que protege é ser ADMIN, ficar na
    auditoria com quem fez, e derrubar toda sessão aberta daquela pessoa: se alguém entrou
    na conta dela, sai na hora. A senha nova não volta em resposta nenhuma; quem define a
    combina com a pessoa por fora."""
    alvo = um(con, "SELECT id, email, name FROM users WHERE id = ?", (uid,))
    if not alvo:
        raise HTTPException(404, "User not found.")
    try:
        auth.trocar_senha(con, uid, dados.password, por_user_id=u["id"], ip=auth._ip(request))
    except ValueError as e:
        raise HTTPException(400, str(e))
    con.commit()
    return {"ok": True, "email": alvo["email"],
            "aviso": ("Senha definida. As sessões abertas desta pessoa foram derrubadas; "
                      "ela entra de novo com a senha nova.")}


# ------------------------------------------------------- chaves de API (ADMIN)
class ChaveIn(BaseModel):
    name: str
    role: str = "VIEWER"
    user_id: int | None = None        # a pessoa que a chave representa (padrão: quem criou)
    days: int | None = None           # validade; sem isto, não expira
    note: str | None = None
    read_only: bool = True            # padrão: consulta o painel e não muda nada


@app.get(BASE + "/api/keys")
def api_keys_list(u=Depends(auth.exige("ADMIN")), con: sqlite3.Connection = Depends(get_db)):
    """As chaves que existem — nunca a chave em si, que só existiu no momento da criação."""
    return todos(con, """SELECT k.id, k.name, k.role, k.created_at, k.expires_at, k.last_used_at,
                                k.last_ip, k.uses, k.revoked_at, k.note, k.read_only,
                                u.email AS como, u.name AS como_nome, u.role AS papel_pessoa,
                                c.email AS criada_por
                         FROM api_keys k JOIN users u ON u.id = k.user_id
                         LEFT JOIN users c ON c.id = k.created_by
                         ORDER BY k.revoked_at IS NOT NULL, k.created_at DESC""")


@app.post(BASE + "/api/keys", status_code=201)
def api_keys_create(dados: ChaveIn, request: Request, u=Depends(auth.exige("ADMIN")),
                    con: sqlite3.Connection = Depends(get_db)):
    """Cria a chave e devolve o valor UMA vez. Não há como vê-lo de novo — nem por aqui,
    nem no banco: o que fica guardado é o hash. Perdeu, cria outra e revoga a antiga."""
    try:
        nova = auth.criar_chave(con, dados.name, (dados.role or "").upper(),
                                dados.user_id or u["id"], por_user_id=u["id"],
                                dias=dados.days, nota=dados.note, somente_leitura=dados.read_only)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {**nova, "aviso": ("Guarde agora: esta é a única vez que a chave aparece. "
                              + ("Ela consulta o painel e não muda nada."
                                 if nova["read_only"] else
                                 "ATENÇÃO: esta chave ESCREVE — o que ela fizer acontece de verdade, "
                                 "sem passar por aprovação."))}


@app.post(BASE + "/api/keys/{ident}/revoke")
def api_keys_revoke(ident: str, request: Request, u=Depends(auth.exige("ADMIN")),
                    con: sqlite3.Connection = Depends(get_db)):
    """Desliga a chave na hora. Quem estiver usando recebe 401 no pedido seguinte."""
    if not auth.revogar_chave(con, ident, por_user_id=u["id"]):
        raise HTTPException(404, "Chave não encontrada (ou já revogada).")
    return {"ok": True}


# ------------------------------------------------------------- audit
@app.get(BASE + "/api/audit")
def api_audit(limit: int = 100, u=Depends(auth.exige("MANAGER")),
              con: sqlite3.Connection = Depends(get_db)):
    limit = max(1, min(limit, 500))
    return todos(con, "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,))


# ---------------------------------------------------------- frontend
if os.path.isdir(os.path.join(DIST, "assets")):
    app.mount(BASE + "/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")


@app.get(BASE)
@app.get(BASE + "/")
@app.get(BASE + "/{caminho:path}")
def spa(caminho: str = ""):
    """Tudo que não é /api nem /assets devolve o index do SPA — menos os arquivos soltos do
    build (o que o Vite copia de `web/public`: a foto do login, favicon). Sem isso o `<img>`
    do login recebia o index e achava que a foto não existia (17/09)."""
    if caminho.startswith("api/") or caminho.startswith("assets/"):
        raise HTTPException(404)
    if caminho and "\\" not in caminho:
        alvo = os.path.normpath(os.path.join(DIST, caminho))
        if (alvo.startswith(DIST + os.sep) and os.path.isfile(alvo)
                and os.path.basename(alvo) != "index.html"):
            return FileResponse(alvo, headers={"Cache-Control": "public, max-age=3600"})
    index = os.path.join(DIST, "index.html")
    if not os.path.isfile(index):
        return JSONResponse({"error": "frontend not built",
                             "hint": "cd command_center/web && npm ci && npm run build"}, 503)
    return FileResponse(index, headers={"Cache-Control": "no-store"})

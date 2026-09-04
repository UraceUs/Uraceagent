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

from command_center.api import auth, rotas
from command_center.db import aplicar_schema, conectar, get_db, todos, um

BASE = "/ops"
AQUI = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.normpath(os.path.join(AQUI, "..", "web", "dist"))

from contextlib import asynccontextmanager


@asynccontextmanager
async def _ciclo(app):
    con = conectar()
    try:
        aplicar_schema(con)
    finally:
        con.close()
    yield


app = FastAPI(title="URACE Command Center", docs_url=None, redoc_url=None,
              openapi_url=None, lifespan=_ciclo)


@app.middleware("http")
async def _cabecalhos(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = resp.headers.get("Cache-Control", "no-store")
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' "
        "https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
        "connect-src 'self'; frame-ancestors 'none'")
    return resp


app.include_router(rotas.r)


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
    return todos(con, "SELECT id, email, name, role, active, created_at, last_login_at FROM users ORDER BY id")


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
    """Tudo que não é /api nem /assets devolve o index do SPA."""
    if caminho.startswith("api/") or caminho.startswith("assets/"):
        raise HTTPException(404)
    index = os.path.join(DIST, "index.html")
    if not os.path.isfile(index):
        return JSONResponse({"error": "frontend not built",
                             "hint": "cd command_center/web && npm ci && npm run build"}, 503)
    return FileResponse(index, headers={"Cache-Control": "no-store"})

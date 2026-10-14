"""Conectar o próprio Google Calendar (#220) — as rotas. O resto mora em `providers/google_agenda.py`.

- **Quem conecta é a pessoa, no navegador** (cookie de sessão): chave de API, conector MCP e a IA
  não começam nem desfazem conexão. Mecânico e coach não chegam aqui (a trava do cargo fecha).
- **A volta do Google não depende do cookie de sessão** (ele é `SameSite=Strict` e não vem num
  redirecionamento que começa em accounts.google.com). Quem diz de quem é a conexão é o `state`
  assinado, de uso único, que nasceu com a sessão; e um cookie `Lax` de 10 minutos prova que é o
  MESMO navegador que pediu.
- Auditoria de conectar, desconectar e falha na volta, com a conta Google e nunca o token.
"""
import logging
import sqlite3
from datetime import date, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from command_center.api import auth
from command_center.db import auditar, get_db
from command_center.providers import google_agenda as g

r = APIRouter(prefix="/ops/api/google", tags=["google"])
COOKIE_NONCE = "cc_gstate"
VOLTA = "/ops/sales/agenda"
MAX_DIAS = 62


class _SemCodigoNoLog(logging.Filter):
    """O log de acesso do uvicorn grava a URL inteira; a volta do Google traz `code` e `state`."""

    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(g.mascarar(a) for a in record.args)
        return True


_log = logging.getLogger("uvicorn.access")
if not any(isinstance(f, _SemCodigoNoLog) for f in _log.filters):
    _log.addFilter(_SemCodigoNoLog())


def pelo_navegador(request: Request, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """Conectar e desconectar só com a sessão do navegador da própria pessoa."""
    if request.headers.get("authorization") or request.headers.get("x-api-key"):
        raise HTTPException(403, "Conectar o Google Calendar é pela própria pessoa, no navegador.")
    s = auth.sessao_valida(con, request.cookies.get(auth.COOKIE_SESSAO))
    if not s or s["user_id"] != u["id"]:
        raise HTTPException(403, "Conectar o Google Calendar é pela própria pessoa, no navegador.")
    return u


def _estado(con, uid):
    ok, motivo = g.configurado()
    c = g.conexao(con, uid)
    return {"configurado": ok, "motivo": motivo,
            "conectado": bool(c and c["status"] == "ativo"), "expirado": bool(c and c["status"] == "expirado"),
            "email": c and c["google_email"], "conectado_em": c and c["connected_at"],
            "sincronizado_em": c and c["last_sync_at"], "erro": c and c["last_error"],
            "redirect_uri": g.redirect_uri() if ok else None}


@r.get("/status")
def status(response: Response, u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return _estado(con, u["id"])


@r.post("/connect")
def conectar(request: Request, response: Response, u=Depends(pelo_navegador), con: sqlite3.Connection = Depends(get_db)):
    """Devolve o endereço do Google; a tela leva a pessoa até lá."""
    ok, motivo = g.configurado()
    if not ok:
        raise HTTPException(503, motivo)
    url, nonce = g.iniciar(con, u["id"])
    response.set_cookie(COOKIE_NONCE, nonce, max_age=g.ESTADO_VALE_MIN * 60, httponly=True,
                        secure=auth._seguro(request), samesite="lax", path="/ops/api/google/callback")
    response.headers["Cache-Control"] = "no-store"
    return {"url": url}


def _volta(resultado, motivo=None):
    q = {"google": resultado}
    if motivo:
        q["motivo"] = motivo
    resp = RedirectResponse(f"{VOLTA}?{urlencode(q)}", status_code=303)
    resp.delete_cookie(COOKIE_NONCE, path="/ops/api/google/callback")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@r.get("/callback")
def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
             con: sqlite3.Connection = Depends(get_db)):
    """A volta do Google. Sem sessão de propósito (ver o topo): o `state` diz quem é."""
    ip = auth._ip(request)
    try:
        uid, verificador = g.consumir_estado(con, state, request.cookies.get(COOKIE_NONCE))
    except (g.EstadoInvalido, g.cofre.CofreDesligado, g.cofre.ChaveErrada) as e:
        auditar(con, "google.connect.refused", "system", detail={"motivo": str(e)[:120]}, ip=ip)
        return _volta("erro", "estado")
    if error:
        auditar(con, "google.connect.denied", f"user:{uid}", user_id=uid, entity_type="user", entity_id=uid,
                detail={"erro": error[:40]}, ip=ip)
        return _volta("erro", "negado" if error == "access_denied" else "google")
    if not code:
        return _volta("erro", "google")
    try:
        email = g.trocar_codigo(con, uid, code, verificador)
    except (g.GoogleErro, g.NaoConfigurado) as e:
        auditar(con, "google.connect.failed", f"user:{uid}", user_id=uid, entity_type="user", entity_id=uid,
                detail={"erro": str(e)[:160]}, ip=ip)
        return _volta("erro", "escopo" if "permissão de agenda" in str(e) else "google")
    auditar(con, "google.connect", f"user:{uid}", user_id=uid, entity_type="user", entity_id=uid,
            detail={"conta": email}, ip=ip)
    try:                                                   # os retornos que já existem vão já
        g.sincronizar_usuario(con, uid)
    except Exception:                                      # noqa: BLE001 — o laço tenta de novo
        pass
    return _volta("ok")


@r.post("/disconnect")
def desconectar(request: Request, u=Depends(pelo_navegador), con: sqlite3.Connection = Depends(get_db)):
    c = g.conexao(con, u["id"])
    tinha, revogou = g.desconectar(con, u["id"])
    if tinha:
        auditar(con, "google.disconnect", f"user:{u['id']}", user_id=u["id"], entity_type="user", entity_id=u["id"],
                detail={"conta": c and c["google_email"], "revogado_no_google": revogou}, ip=auth._ip(request))
    return {"ok": True, "tinha": tinha, "revogado": revogou}


@r.post("/sync")
def sincronizar(u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """Acerta agora os retornos da pessoa no Google dela (o laço automático faz o mesmo sozinho)."""
    if not g.conexao(con, u["id"]) or g.conexao(con, u["id"])["status"] != "ativo":
        raise HTTPException(409, "Conecte o seu Google Calendar primeiro.")
    try:
        conta, erro = g.sincronizar_usuario(con, u["id"])
    except (g.NaoConfigurado, g.ConexaoExpirada) as e:
        raise HTTPException(409, str(e))
    return {"ok": not erro, "feito": conta, "erro": erro}


def _dia(v, padrao):
    if not v:
        return padrao
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        raise HTTPException(400, "Data inválida: use AAAA-MM-DD.")


@r.get("/events")
def eventos(response: Response, de: str | None = None, ate: str | None = None,
            u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """Os eventos do Google da PRÓPRIA pessoa no período (só leitura). Ninguém vê a agenda de outro."""
    from command_center.api.vendas import hoje_local
    response.headers["Cache-Control"] = "no-store"
    hoje = date.fromisoformat(hoje_local())
    d0 = _dia(de, hoje)
    d1 = _dia(ate, d0 + timedelta(days=7))
    if d1 < d0 or (d1 - d0).days > MAX_DIAS:
        raise HTTPException(400, f"Período inválido (até {MAX_DIAS} dias).")
    c = g.conexao(con, u["id"])
    if not c or c["status"] != "ativo":
        return {"conectado": False, "eventos": [], "de": d0.isoformat(), "ate": d1.isoformat()}
    try:
        evs = g.eventos(con, u["id"], d0, d1)
    except g.ConexaoExpirada as e:
        return {"conectado": False, "erro": str(e), "eventos": [], "de": d0.isoformat(), "ate": d1.isoformat()}
    except (g.GoogleErro, g.NaoConfigurado) as e:
        return {"conectado": True, "erro": str(e), "eventos": [], "de": d0.isoformat(), "ate": d1.isoformat()}
    return {"conectado": True, "eventos": evs or [], "de": d0.isoformat(), "ate": d1.isoformat()}

"""Consentimento OAuth do QuickBooks feito pelo próprio Command Center.

Por quê aqui: a Intuit exige redirect URI em HTTPS para chaves de
produção, e o único HTTPS nosso é https://urace-bridge.duckdns.org. O
callback chega sem cookie de sessão (SameSite=Strict não atravessa o
redirect vindo de intuit.com), então a prova de quem iniciou é o `state`
gerado em /connect, guardado com o usuário e validade de 10 minutos.
O token vai para ~/.urace/qbo-token.json (600); nada entra no banco.
"""
import os
import secrets
import time
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from command_center.api import auth
from command_center.db import auditar, get_db

r = APIRouter(prefix="/ops/api/qbo")
AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
SCOPE = "com.intuit.quickbooks.accounting"
_estados = {}                       # state -> (user_id, expira)


def _redirect_uri(request: Request):
    host = os.environ.get("CC_PUBLIC_HOST") or request.headers.get("x-forwarded-host") or request.headers.get("host")
    return f"https://{host}/ops/api/qbo/callback"


def _client_id():
    from command_center.providers import modulo
    try:
        modulo("quickbooks")                       # carrega o env do MCP (sem token ele falha; pegamos só o env)
    except Exception:
        pass
    cid = os.environ.get("QBO_CLIENT_ID")
    if not cid:
        # o módulo saiu antes de exportar: lê o env direto
        env = os.path.expanduser(os.environ.get("URACE_ENV", "~/.urace/adminai.env"))
        if os.path.exists(env):
            for l in open(env, encoding="utf-8"):
                if l.startswith("QBO_CLIENT_ID="):
                    cid = l.split("=", 1)[1].strip().strip('"')
                if l.startswith("QBO_CLIENT_SECRET=") and not os.environ.get("QBO_CLIENT_SECRET"):
                    os.environ["QBO_CLIENT_SECRET"] = l.split("=", 1)[1].strip().strip('"')
                if l.startswith("QBO_REALM_ID=") and not os.environ.get("QBO_REALM_ID"):
                    os.environ["QBO_REALM_ID"] = l.split("=", 1)[1].strip().strip('"')
            if cid:
                os.environ["QBO_CLIENT_ID"] = cid
    return cid


@r.get("/connect")
def connect(request: Request, u=Depends(auth.exige("ADMIN")), con=Depends(get_db)):
    """Manda o administrador para a tela de consentimento da Intuit."""
    cid = _client_id()
    if not cid or not os.environ.get("QBO_CLIENT_SECRET"):
        raise HTTPException(409, "QBO_CLIENT_ID e QBO_CLIENT_SECRET ainda não estão em ~/.urace/adminai.env. Veja docs/adminai/quickbooks-conexao.md.")
    state = secrets.token_urlsafe(24)
    _estados[state] = (u["id"], time.time() + 600)
    for k in [k for k, v in _estados.items() if v[1] < time.time()]:
        _estados.pop(k, None)
    q = urllib.parse.urlencode({"client_id": cid, "response_type": "code", "scope": SCOPE,
                                "redirect_uri": _redirect_uri(request), "state": state})
    auditar(con, "qbo.connect.start", f"user:{u['id']}", user_id=u["id"], ip=auth._ip(request))
    return RedirectResponse(f"{AUTH_URL}?{q}", status_code=302)


@r.get("/callback")
def callback(request: Request, code: str = None, state: str = None, realmId: str = None, error: str = None,
             con=Depends(get_db)):
    """Volta da Intuit. Sem sessão: a prova é o state."""
    if error:
        return RedirectResponse(f"/ops/quickbooks?erro={urllib.parse.quote(error)}", status_code=302)
    dono = _estados.pop(state or "", None)
    if not dono or dono[1] < time.time():
        raise HTTPException(400, "Consentimento expirado ou não iniciado por aqui. Volte ao painel e clique em Conectar de novo.")
    if not code or not realmId:
        raise HTTPException(400, "A Intuit não devolveu code/realmId.")
    _client_id()
    import importlib
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "adminai", "mcp"))
    q = importlib.import_module("quickbooks_mcp")
    try:
        tok = q.trocar_codigo(code, _redirect_uri(request))
    except Exception as e:
        raise HTTPException(502, f"A Intuit recusou a troca do código: {str(e)[:300]}")
    q.gravar_token({"access_token": tok["access_token"], "refresh_token": tok["refresh_token"], "expires_in": tok.get("expires_in"),
                    "realm_id": realmId, "obtido_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "por_user_id": dono[0]})
    con.execute("UPDATE integrations SET status='CONNECTED', last_success_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'), last_error=NULL, detail=? WHERE system='quickbooks'",
                ('{"realm_id": "%s", "consentimento": "Command Center"}' % realmId,))
    auditar(con, "qbo.connect.done", f"user:{dono[0]}", user_id=dono[0], entity_type="integration", entity_id="quickbooks",
            detail={"realm_id": realmId}, ip=auth._ip(request))
    from command_center.providers import recarregar
    recarregar()
    return RedirectResponse("/ops/quickbooks?connected=1", status_code=302)

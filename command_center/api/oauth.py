"""O painel como serviço de login OAuth — para o conector do claude.ai entrar.

Dono, 24/09: o conector personalizado recusou chave fixa e falhou com *"não foi possível
registrar no serviço de login"*. Ele tenta **registro dinâmico de cliente** (RFC 7591)
contra um servidor de autorização que não existia. Este módulo é esse servidor.

**O que ele NÃO muda:** o que o conector alcança depois de entrar continua sendo só o
`/ops/mcp`, que só tem ferramentas de leitura e abre o banco em `mode=ro`. O login não
amplia nada; ele só substitui a chave no cabeçalho por um fluxo que o cliente entende.

**Quem autoriza é gente, no navegador.** O `/authorize` exige sessão do painel: se não
houver, manda para a tela de login e volta. Não existe caminho em que um programa se
autorize sozinho.

Decisões que vale registrar, porque cada uma fecha um buraco conhecido:

- **PKCE obrigatório** (S256). Sem ele, um código interceptado na volta do navegador vira
  token. Com ele, o código só serve para quem guardou o verificador.
- **`redirect_uri` conferido contra lista fechada**, byte a byte. É a porta por onde o
  código sai; aceitar parecido é entregar o código a outro destino.
- **Código de uso único.** Reuso é sinal de interceptação: a segunda tentativa falha e o
  token já emitido é revogado, porque nesse ponto não dá para saber quem é o legítimo.
- **Nada em claro.** Código e token viram hash antes de tocar o banco, como a senha e a
  chave de API já faziam.
"""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from command_center.api import auth
from command_center.db import agora, auditar, get_db, inserir, todos, um

r = APIRouter(prefix="/ops/oauth", tags=["oauth"])

CODIGO_VALE_MIN = 5          # tempo de vida do código de autorização
TOKEN_VALE_HORAS = 12
REFRESH_VALE_DIAS = 30
ESCOPO = "mcp:read"          # o único que existe: ler o painel pelo MCP


def emissor():
    """A identidade pública deste servidor. Tem de bater com o que o cliente descobriu."""
    return os.environ.get("CC_PUBLIC_URL", "https://urace-bridge.duckdns.org").rstrip("/")


def _hash(valor):
    return hashlib.sha256(valor.encode()).hexdigest()


def _agora_mais(**kw):
    return (datetime.now(timezone.utc) + timedelta(**kw)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def metadados_servidor():
    """RFC 8414. É o que o cliente lê para saber onde bater."""
    base = emissor()
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/ops/oauth/authorize",
        "token_endpoint": f"{base}/ops/oauth/token",
        "registration_endpoint": f"{base}/ops/oauth/register",
        "revocation_endpoint": f"{base}/ops/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
        "scopes_supported": [ESCOPO],
        "service_documentation": f"{base}/ops/",
    }


def metadados_recurso():
    """RFC 9728: quem protege o quê, e qual servidor de login vale para isso."""
    base = emissor()
    return {"resource": f"{base}/ops/mcp", "authorization_servers": [base],
            "scopes_supported": [ESCOPO],
            "bearer_methods_supported": ["header"]}


# ------------------------------------------------------- registro dinâmico (RFC 7591)
@r.post("/register")
def registrar(dados: dict, request: Request, con: sqlite3.Connection = Depends(get_db)):
    """O cliente se apresenta e recebe um `client_id`. **Sem sessão**, de propósito: é o
    que a especificação pede, e registrar-se ainda não dá acesso a nada — só o
    `/authorize`, com gente logada aprovando, é que dá."""
    uris = dados.get("redirect_uris") or []
    if not isinstance(uris, list) or not uris:
        raise HTTPException(400, "redirect_uris é obrigatório")
    for u in uris:
        if not isinstance(u, str) or not u.startswith(("https://", "http://localhost", "http://127.0.0.1")):
            # http só em localhost: em qualquer outro lugar o código voltaria em claro.
            raise HTTPException(400, f"redirect_uri precisa ser https (ou localhost): {u}")
    nome = (dados.get("client_name") or "cliente sem nome")[:120]
    cid = "ucc_" + secrets.token_urlsafe(18)
    metodo = dados.get("token_endpoint_auth_method") or "none"
    if metodo not in ("none", "client_secret_post", "client_secret_basic"):
        metodo = "client_secret_post"
    publico = metodo == "none"
    segredo = None if publico else secrets.token_urlsafe(32)
    sal = None if publico else secrets.token_hex(16)
    inserir(con, "oauth_clients", client_id=cid, name=nome,
            secret_hash=None if publico else _hash(sal + segredo),
            secret_salt=sal, redirect_uris=json.dumps(uris),
            created_ip=(request.client.host if request.client else None))
    auditar(con, "oauth.client.register", "system", entity_type="oauth_client", entity_id=cid,
            detail={"nome": nome, "redirect_uris": uris, "publico": publico},
            ip=(request.client.host if request.client else None))
    con.commit()
    saida = {"client_id": cid, "client_name": nome, "redirect_uris": uris,
             "token_endpoint_auth_method": metodo,
             "grant_types": ["authorization_code", "refresh_token"],
             "response_types": ["code"], "client_id_issued_at": int(datetime.now().timestamp())}
    if segredo:
        saida["client_secret"] = segredo        # única vez que ele existe em claro
    return JSONResponse(saida, status_code=201)


# ------------------------------------------------------------------ autorização
def _cliente(con, client_id):
    c = um(con, "SELECT * FROM oauth_clients WHERE client_id=? AND revoked_at IS NULL", (client_id,))
    if not c:
        raise HTTPException(400, "cliente desconhecido ou revogado")
    return c


def _confere_redirect(cliente, uri):
    """Comparação exata contra a lista fechada. `startswith` aqui já foi a porta de
    entrada de ataque em serviços de verdade: `https://meusite.com` casaria com
    `https://meusite.com.invasor.net`."""
    permitidos = json.loads(cliente["redirect_uris"])
    if uri not in permitidos:
        raise HTTPException(400, "redirect_uri não está registrado para este cliente")
    return uri


PAGINA = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Autorizar acesso — URACE</title><style>
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;
background:#0d0f12;color:#e8eaed;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
.c{{max-width:440px;padding:32px;background:#16191e;border:1px solid #262a31;border-radius:16px}}
h1{{font-size:19px;margin:0 0 4px}}.m{{color:#9aa0a6;font-size:13.5px}}
ul{{margin:18px 0;padding-left:18px}}li{{margin:5px 0;color:#c9ccd1;font-size:14px}}
.w{{background:#1d1a12;border:1px solid #3d3319;color:#e0c068;padding:10px 12px;
border-radius:10px;font-size:13px;margin:16px 0}}
form{{display:flex;gap:10px;margin-top:22px}}button{{flex:1;padding:11px;border-radius:10px;
border:1px solid #2d3139;font-size:14px;cursor:pointer;font-family:inherit}}
.no{{background:transparent;color:#c9ccd1}}.ok{{background:#e8eaed;color:#0d0f12;font-weight:600;border-color:#e8eaed}}
</style></head><body><div class="c">
<h1>{nome} quer acessar o Command Center</h1>
<p class="m">Entrando como <b>{usuario}</b>.</p>
<ul>
<li>Ler clientes, serviços, invoices, waivers e corridas</li>
<li>Ler o estoque e o que precisa de atenção</li>
<li>Ler o rastro de auditoria</li>
</ul>
<div class="w">Somente leitura. Este acesso <b>não</b> altera dado nenhum, não fala com
cliente e não mexe em dinheiro — nem se pedirem.</div>
<p class="m">Você pode revogar quando quiser, no painel.</p>
<form method="post" action="/ops/oauth/authorize">
{campos}
<input type="hidden" name="csrf" value="{csrf}">
<button class="no" name="decisao" value="nao" type="submit">Cancelar</button>
<button class="ok" name="decisao" value="sim" type="submit">Autorizar</button>
</form></div></body></html>"""


def _campos_ocultos(p):
    def esc(v):
        return (str(v or "").replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))
    return "\n".join(f'<input type="hidden" name="{k}" value="{esc(v)}">' for k, v in p.items())


@r.get("/authorize")
def autorizar(request: Request, con: sqlite3.Connection = Depends(get_db)):
    """Mostra a tela de consentimento. **Exige gente logada no painel**: sem sessão,
    manda para o login e volta para cá depois."""
    p = dict(request.query_params)
    cliente = _cliente(con, p.get("client_id", ""))
    redirect_uri = _confere_redirect(cliente, p.get("redirect_uri", ""))
    if p.get("response_type") != "code":
        return _volta_com_erro(redirect_uri, p, "unsupported_response_type")
    if not p.get("code_challenge") or p.get("code_challenge_method") != "S256":
        # Sem PKCE o código interceptado na volta vira token. Não é opcional aqui.
        return _volta_com_erro(redirect_uri, p, "invalid_request",
                               "PKCE com S256 é obrigatório neste servidor")

    try:
        u = auth.usuario_atual(request, con)
    except HTTPException:
        destino = "/ops/login?" + urlencode({"next": f"/ops/oauth/authorize?{urlencode(p)}"})
        return RedirectResponse(destino, status_code=303)

    return HTMLResponse(PAGINA.format(
        nome=cliente["name"], usuario=u.get("email") or u.get("name") or "você",
        campos=_campos_ocultos(p),
        csrf=(request.cookies.get(auth.COOKIE_CSRF) or "")))


def _volta_com_erro(redirect_uri, p, erro, descricao=None):
    """Erro do cliente volta PARA o cliente, como a especificação manda — assim ele
    mostra algo útil em vez de uma página branca."""
    q = {"error": erro}
    if descricao:
        q["error_description"] = descricao
    if p.get("state"):
        q["state"] = p["state"]
    return RedirectResponse(f"{redirect_uri}?{urlencode(q)}", status_code=303)


@r.post("/authorize")
def decidir(request: Request, con: sqlite3.Connection = Depends(get_db),
            decisao: str = Form(...), client_id: str = Form(...),
            redirect_uri: str = Form(...), code_challenge: str = Form(...),
            state: str = Form(None), scope: str = Form(None), csrf: str = Form(""),
            response_type: str = Form("code"), code_challenge_method: str = Form("S256")):
    """A decisão da pessoa. Só aqui nasce um código.

    O CSRF vem em **campo do formulário**, não no cabeçalho: este POST sai de um
    `<form>` de navegador, que não manda cabeçalho próprio. É o mesmo token de duas
    submissões do resto do painel — conferido aqui à mão em vez de a rota ser isentada,
    porque isenção vira buraco e conferência não.
    """
    cliente = _cliente(con, client_id)
    _confere_redirect(cliente, redirect_uri)
    sessao = auth.sessao_valida(con, request.cookies.get(auth.COOKIE_SESSAO))
    if not sessao:
        raise HTTPException(401, "sua sessão expirou; entre de novo e repita a autorização")
    esperado = request.cookies.get(auth.COOKIE_CSRF) or ""
    if not esperado or not hmac.compare_digest(csrf or "", esperado):
        raise HTTPException(403, "pedido sem a marca de segurança do formulário")
    # `sessao_valida` devolve a linha da SESSÃO: ali `id` é o id da sessão, e quem manda
    # é `user_id`. Confundir os dois gravava o id errado no código de autorização — a
    # chave estrangeira pegou na hora, e é para isso que ela existe.
    u = {"id": sessao["user_id"], "email": sessao["email"], "name": sessao["name"],
         "role": sessao["role"]}

    if decisao != "sim":
        return _volta_com_erro(redirect_uri, {"state": state}, "access_denied",
                               "a pessoa não autorizou")

    codigo = secrets.token_urlsafe(32)
    inserir(con, "oauth_codes", code_hash=_hash(codigo), client_id=client_id,
            user_id=u["id"], redirect_uri=redirect_uri, code_challenge=code_challenge,
            scope=scope or ESCOPO, expires_at=_agora_mais(minutes=CODIGO_VALE_MIN))
    auditar(con, "oauth.authorize", f"user:{u['id']}", user_id=u["id"],
            entity_type="oauth_client", entity_id=client_id,
            detail={"cliente": cliente["name"], "escopo": scope or ESCOPO})
    con.commit()
    q = {"code": codigo}
    if state:
        q["state"] = state
    return RedirectResponse(f"{redirect_uri}?{urlencode(q)}", status_code=303)


# ------------------------------------------------------------------ token
def _confere_pkce(verificador, desafio):
    esperado = hashlib.sha256((verificador or "").encode()).digest()
    import base64
    calculado = base64.urlsafe_b64encode(esperado).decode().rstrip("=")
    return hmac.compare_digest(calculado, desafio or "")


def _emitir(con, client_id, user_id, escopo):
    acesso = secrets.token_urlsafe(32)
    refresh = secrets.token_urlsafe(32)
    inserir(con, "oauth_tokens", token_hash=_hash(acesso), kind="access", client_id=client_id,
            user_id=user_id, scope=escopo, expires_at=_agora_mais(hours=TOKEN_VALE_HORAS))
    inserir(con, "oauth_tokens", token_hash=_hash(refresh), kind="refresh", client_id=client_id,
            user_id=user_id, scope=escopo, expires_at=_agora_mais(days=REFRESH_VALE_DIAS))
    return {"access_token": acesso, "token_type": "Bearer",
            "expires_in": TOKEN_VALE_HORAS * 3600, "refresh_token": refresh, "scope": escopo}


def _credencial_basic(request):
    """`Authorization: Basic base64(client_id:client_secret)` — o jeito padrão (RFC 6749
    §2.3.1) de um cliente confidencial se identificar no /token. Cada parte vem
    codificada como formulário antes do base64, por isso o `unquote_plus`."""
    import base64
    from urllib.parse import unquote_plus
    cab = request.headers.get("authorization") or ""
    if not cab.lower().startswith("basic "):
        return None
    try:
        cid, _, seg = base64.b64decode(cab[6:].strip()).decode().partition(":")
    except (ValueError, UnicodeDecodeError):
        return None
    return unquote_plus(cid), unquote_plus(seg)


def _erro_oauth(codigo, descricao, http=400):
    return JSONResponse({"error": codigo, "error_description": descricao}, status_code=http)


@r.post("/token")
def token(request: Request, con: sqlite3.Connection = Depends(get_db),
          grant_type: str = Form(...), code: str = Form(None), redirect_uri: str = Form(None),
          client_id: str = Form(None), code_verifier: str = Form(None),
          refresh_token: str = Form(None), client_secret: str = Form(None)):
    basico = _credencial_basic(request)
    if basico:
        if client_id and client_id != basico[0]:
            return _erro_oauth("invalid_client", "client_id do cabeçalho e do formulário não batem", 401)
        client_id, client_secret = basico[0], client_secret or basico[1]
    if grant_type == "refresh_token":
        return _renovar(con, refresh_token, client_id)
    if grant_type != "authorization_code":
        return _erro_oauth("unsupported_grant_type", f"não sei fazer {grant_type}")

    linha = um(con, "SELECT * FROM oauth_codes WHERE code_hash=?", (_hash(code or ""),))
    if not linha:
        return _erro_oauth("invalid_grant", "código desconhecido")

    if linha["used_at"]:
        # Código usado duas vezes é sinal de interceptação. Neste ponto não há como saber
        # quem é o legítimo, então **os dois perdem**: tudo que saiu daquele código morre.
        con.execute("UPDATE oauth_tokens SET revoked_at=? WHERE client_id=? AND user_id=? "
                    "AND revoked_at IS NULL", (agora(), linha["client_id"], linha["user_id"]))
        auditar(con, "oauth.code.reuse", "system", user_id=linha["user_id"],
                entity_type="oauth_client", entity_id=linha["client_id"],
                detail={"acao": "todos os tokens desse cliente foram revogados"})
        con.commit()
        return _erro_oauth("invalid_grant", "código já usado; o acesso foi revogado por segurança")

    if linha["expires_at"] < agora():
        return _erro_oauth("invalid_grant", "código expirado")
    if client_id and client_id != linha["client_id"]:
        return _erro_oauth("invalid_grant", "código não é deste cliente")
    if redirect_uri and redirect_uri != linha["redirect_uri"]:
        return _erro_oauth("invalid_grant", "redirect_uri diferente do usado na autorização")

    cliente = um(con, "SELECT * FROM oauth_clients WHERE client_id=?", (linha["client_id"],))
    if cliente and cliente["secret_hash"]:
        if not client_secret or not hmac.compare_digest(
                _hash((cliente["secret_salt"] or "") + client_secret), cliente["secret_hash"]):
            return _erro_oauth("invalid_client", "segredo do cliente não confere", 401)
    if not _confere_pkce(code_verifier, linha["code_challenge"]):
        return _erro_oauth("invalid_grant", "code_verifier não confere com o desafio")

    con.execute("UPDATE oauth_codes SET used_at=? WHERE code_hash=?", (agora(), linha["code_hash"]))
    saida = _emitir(con, linha["client_id"], linha["user_id"], linha["scope"] or ESCOPO)
    auditar(con, "oauth.token", f"user:{linha['user_id']}", user_id=linha["user_id"],
            entity_type="oauth_client", entity_id=linha["client_id"], detail={"escopo": linha["scope"]})
    con.commit()
    return JSONResponse(saida)


def _renovar(con, refresh, client_id):
    linha = um(con, "SELECT * FROM oauth_tokens WHERE token_hash=? AND kind='refresh'",
               (_hash(refresh or ""),))
    if not linha or linha["revoked_at"] or (linha["expires_at"] or "") < agora():
        return _erro_oauth("invalid_grant", "refresh token inválido ou expirado")
    if client_id and client_id != linha["client_id"]:
        return _erro_oauth("invalid_grant", "refresh token não é deste cliente")
    # Rotação: o refresh usado morre e sai outro. Assim um refresh roubado só vale até o
    # dono legítimo renovar — e a renovação dele denuncia o roubo.
    con.execute("UPDATE oauth_tokens SET revoked_at=? WHERE token_hash=?",
                (agora(), linha["token_hash"]))
    saida = _emitir(con, linha["client_id"], linha["user_id"], linha["scope"] or ESCOPO)
    con.commit()
    return JSONResponse(saida)


@r.post("/revoke")
def revogar(con: sqlite3.Connection = Depends(get_db), token: str = Form(...)):
    """RFC 7009. Sempre responde 200, mesmo para token que não existe: dizer "esse não é
    meu" seria um oráculo para descobrir tokens válidos."""
    con.execute("UPDATE oauth_tokens SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
                (agora(), _hash(token)))
    con.commit()
    return JSONResponse({"ok": True})


def usuario_do_token(con, valor):
    """Valida um Bearer de OAuth. Devolve o usuário como as outras portas devolvem, para
    o resto do painel não precisar saber por onde ele entrou."""
    linha = um(con, """SELECT t.*, u.email, u.name, u.role, u.active
                         FROM oauth_tokens t JOIN users u ON u.id = t.user_id
                        WHERE t.token_hash=? AND t.kind='access'""", (_hash(valor or ""),))
    if not linha or linha["revoked_at"] or not linha["active"]:
        return None
    if (linha["expires_at"] or "") < agora():
        return None
    con.execute("UPDATE oauth_tokens SET uses=uses+1, last_used_at=? WHERE token_hash=?",
                (agora(), linha["token_hash"]))
    return {"id": linha["user_id"], "email": linha["email"], "name": linha["name"],
            "role": linha["role"], "via": "oauth", "client_id": linha["client_id"],
            # O token OAuth existe para o MCP, que só lê. Marcar aqui mantém a trava de
            # escrita valendo mesmo se um dia alguém apontar este token para outra rota.
            "somente_leitura": True}

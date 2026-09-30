"""Cache das APIs (issue #20): ETag nos GET e paginação no backend.

**ETag.** As telas se atualizam sozinhas (a cada 15–60 s) e quase sempre nada mudou. Todo
GET 200 da API sai com `ETag` (hash do corpo) e `Cache-Control: private, no-cache`: o
navegador guarda, pergunta de novo com `If-None-Match` e, se nada mudou, recebe **304 sem
corpo**. O dado continua sempre conferido com o servidor (no-cache = revalidar sempre; com a
sessão caída a resposta é 401 e o guardado não aparece), e `private` impede cache
compartilhado (proxy, CDN).

É um middleware ASGI puro, registrado por dentro de todos: vê o corpo inteiro, antes do gzip.

**Paginação.** `paginar()` aplica `LIMIT/OFFSET` no SQL e devolve o total no cabeçalho
`X-Total-Count`. Sem `limit`, a rota se comporta como antes (compatível com as telas).
"""
import hashlib

from command_center.db import todos, um

MAX_POR_PAGINA = 500


def _etag(corpo):
    return 'W/"' + hashlib.sha1(corpo).hexdigest()[:20] + '"'


def _bate(if_none_match, etag):
    if not if_none_match:
        return False
    if if_none_match.strip() == "*":
        return True
    fortes = {t.strip().removeprefix("W/") for t in if_none_match.split(",")}
    return etag.removeprefix("W/") in fortes


class ETagAPI:
    def __init__(self, app, prefixo="/ops/api/"):
        self.app, self.prefixo = app, prefixo

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "GET" or not scope["path"].startswith(self.prefixo):
            return await self.app(scope, receive, send)
        inm = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"if-none-match"), None)
        inicio, partes = None, []

        async def envia(msg):
            nonlocal inicio
            if msg["type"] == "http.response.start":
                inicio = msg
                return
            if msg["type"] != "http.response.body":
                return await send(msg)
            partes.append(msg.get("body", b""))
            if msg.get("more_body"):
                return
            corpo = b"".join(partes)
            if inicio["status"] != 200:
                await send(inicio)
                return await send({"type": "http.response.body", "body": corpo})
            etag = _etag(corpo)
            cab = [(k, v) for k, v in inicio["headers"] if k.lower() not in (b"etag", b"cache-control")]
            cab += [(b"etag", etag.encode()), (b"cache-control", b"private, no-cache")]
            if _bate(inm, etag):
                cab = [(k, v) for k, v in cab if k.lower() not in (b"content-length", b"content-type")]
                await send({"type": "http.response.start", "status": 304, "headers": cab})
                return await send({"type": "http.response.body", "body": b""})
            await send({**inicio, "headers": cab})
            await send({"type": "http.response.body", "body": corpo})

        await self.app(scope, receive, envia)


def paginar(con, sql, params, response, limit=None, offset=0, padrao=None):
    """`sql` já com WHERE e ORDER BY, sem LIMIT. Com `limit`: uma página e o total em
    `X-Total-Count`. Sem `limit`: `padrao` (o teto que a rota sempre teve) ou tudo."""
    params = list(params or [])
    if limit is None:
        return todos(con, sql + (f" LIMIT {int(padrao)}" if padrao else ""), params)
    total = um(con, f"SELECT COUNT(*) AS n FROM ({sql})", params)["n"]
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    lim = max(1, min(int(limit), MAX_POR_PAGINA))
    return todos(con, sql + " LIMIT ? OFFSET ?", params + [lim, max(0, int(offset or 0))])

"""MCP que OPERA o painel, pelo papel de quem está usando (#73).

Dono, 02/10: *"eu preciso que toda, todas as funcionalidades sejam operáveis pela API, não só
como visualização, mas como operação mesmo... os nossos vendedores... usam o Claude nas
máquinas deles... de acordo com o nível de hierarquia ali do operador ou gerente"*.

**Não existe um caminho paralelo.** A ferramenta `urace_api` chama a MESMA rota que o botão do
painel chama, dentro do processo, com a credencial de quem está no Claude. Por isso valem, sem
nada escrito de novo aqui:

- a checagem de papel de cada rota (`auth.exige`): o operador não faz o que é do gerente;
- a validação e as travas de cada rota (cobrar duas vezes, card de outro cliente, "nunca");
- a auditoria com o nome da pessoa;
- a trava de leitura: token sem o escopo de operar continua só lendo.

O que vai para o cliente ou mexe em dinheiro pede `confirmar: true`: a primeira chamada
devolve o que vai acontecer, e só a segunda faz. O resto do painel (login, chaves, área do
cliente) fica fora, porque não é operação de equipe.
"""
import asyncio
import inspect
import json
import re
import sys

from fastapi import APIRouter
from fastapi.routing import APIRoute

from command_center.api import auth
from command_center.db import auditar, conectar

PREFIXO = "/ops/api/"
# fora do MCP: credenciais e sessões (login, senha, chaves) e a área do cliente (outra porta)
FORA = re.compile(r"^/ops/api/(auth|portal)(/|$)")
METODOS = ("GET", "POST", "PATCH", "PUT", "DELETE")
# o que manda algo para fora (cliente, QuickBooks, DocuSign, e-mail, Kommo, Asana) ou cobra
PEDE_CONFIRMACAO = re.compile(
    r"invoice|waiver|docusign|qbo|quickbooks|gmail|email|enviar|send|lembrete|reminder|kommo|whatsapp|"
    r"recorrencia|mensal|fechar|close|step/|cobr|pagamento|payment|asana|tasks|agendamentos/", re.I)


def _papel_da_rota(dep):
    """O papel mínimo que `auth.exige(...)` pede nesta rota (procura nas dependências)."""
    for d in dep.dependencies:
        fn = d.call
        if getattr(fn, "__name__", "") == "_guarda" and "exige" in getattr(fn, "__qualname__", ""):
            return inspect.getclosurevars(fn).nonlocals.get("papel_minimo")
        achado = _papel_da_rota(d)
        if achado:
            return achado
    return None


def _usa_login(dep):
    return any(getattr(d.call, "__name__", "") == "usuario_atual" or _usa_login(d) for d in dep.dependencies)


_CATALOGO = None


def catalogo():
    """[(método, caminho, papel, descrição, campos)] de toda rota de equipe do painel."""
    global _CATALOGO
    if _CATALOGO is not None:
        return _CATALOGO
    from command_center.api.main import app
    spec = app.openapi()
    saida = []
    vistos = set()
    for nome, mod in list(sys.modules.items()):
        if not nome.startswith("command_center.api."):
            continue
        r = getattr(mod, "r", None)
        if not isinstance(r, APIRouter):
            continue
        for rota in r.routes:
            if not isinstance(rota, APIRoute) or not rota.path.startswith(PREFIXO) or FORA.match(rota.path):
                continue
            papel = _papel_da_rota(rota.dependant) or ("VIEWER" if _usa_login(rota.dependant) else None)
            if not papel:
                continue                        # rota pública ou de outra porta: não é operação de equipe
            for metodo in sorted(rota.methods & set(METODOS)):
                if (metodo, rota.path) in vistos:
                    continue
                vistos.add((metodo, rota.path))
                op = (spec.get("paths", {}).get(rota.path) or {}).get(metodo.lower()) or {}
                desc = (inspect.getdoc(rota.endpoint) or op.get("summary") or rota.name or "").strip()
                saida.append({"metodo": metodo, "caminho": rota.path, "papel": papel,
                              "descricao": desc.split("\n\n")[0][:400],
                              "campos": _campos(spec, op), "confirma": metodo != "GET" and bool(PEDE_CONFIRMACAO.search(rota.path))})
    saida.sort(key=lambda x: (x["caminho"], x["metodo"]))
    _CATALOGO = saida
    return saida


def _campos(spec, op):
    """Parâmetros (consulta) e corpo JSON, resumidos para o modelo saber o que mandar."""
    out = {}
    for p in op.get("parameters") or []:
        if p.get("in") == "query":
            out[p["name"]] = (p.get("schema") or {}).get("type", "string") + (" (obrigatório)" if p.get("required") else "")
    corpo = (((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
    ref = corpo.get("$ref", "")
    if ref.startswith("#/components/schemas/"):
        corpo = spec.get("components", {}).get("schemas", {}).get(ref.rsplit("/", 1)[1], {})
    obrig = set(corpo.get("required") or [])
    for k, v in (corpo.get("properties") or {}).items():
        tipo = v.get("type") or "/".join(x.get("type", "?") for x in v.get("anyOf", []) if x.get("type") != "null") or "valor"
        out[f"corpo.{k}"] = tipo + (" (obrigatório)" if k in obrig else "")
    return out


def _caminho_casa(modelo, caminho):
    return re.fullmatch(re.sub(r"\\\{[^}]+\\\}", r"[^/]+", re.escape(modelo)), caminho) is not None


def _operacao(metodo, caminho):
    return next((o for o in catalogo() if o["metodo"] == metodo and _caminho_casa(o["caminho"], caminho)), None)


def pode(quem, papel):
    return quem.get("free") or auth.pode(quem.get("role"), papel)


def operacoes(quem, busca=None, limite=60):
    """O que ESTA pessoa pode fazer pelo MCP: só as rotas que o papel dela alcança, e só
    leitura se o acesso dela é de leitura."""
    so_ler = bool(quem.get("somente_leitura"))
    itens = [o for o in catalogo() if pode(quem, o["papel"]) and (not so_ler or o["metodo"] == "GET")]
    if busca:
        termos = [t for t in re.split(r"\s+", busca.lower()) if t]
        itens = [o for o in itens if all(t in f"{o['caminho']} {o['descricao']}".lower() for t in termos)]
    limite = max(1, min(int(limite or 60), 300))
    return {"papel": quem.get("role"), "opera": not so_ler, "total": len(itens), "operacoes": itens[:limite],
            "como_usar": "chame urace_api com metodo e caminho (troque {id} pelo número); corpo é JSON. "
                         "O que tem confirma=true precisa de confirmar=true — antes disso só mostra o que vai fazer."}


def chamar(quem, ctx, metodo, caminho, corpo=None, consulta=None, confirmar=False):
    """Chama a rota do painel por dentro, como a pessoa. Devolve {status, resposta}."""
    metodo = str(metodo or "").upper()
    if metodo not in METODOS:
        raise ValueError(f"método inválido: use um de {', '.join(METODOS)}")
    caminho = "/" + str(caminho or "").lstrip("/")
    if not caminho.startswith(PREFIXO):
        caminho = PREFIXO + caminho.lstrip("/").removeprefix("ops/api/")
    if ".." in caminho or "?" in caminho or "#" in caminho:
        raise ValueError("caminho inválido: passe a consulta em 'consulta', não na URL")
    if FORA.match(caminho):
        raise ValueError("login, chaves e área do cliente não são operados pelo MCP")
    op = _operacao(metodo, caminho)
    if not op:
        raise ValueError(f"{metodo} {caminho} não existe no painel (veja urace_operacoes)")
    if metodo != "GET" and quem.get("somente_leitura"):
        raise ValueError("este acesso é só de leitura. Para operar, conecte de novo e marque "
                         "'Também operar o painel como você' na tela de autorização.")
    if not pode(quem, op["papel"]):
        raise ValueError(f"isto é do papel {op['papel']} ou acima; você é {quem.get('role')}")
    if op["confirma"] and not confirmar:
        return {"precisa_confirmar": True, "vai_fazer": {"metodo": metodo, "caminho": caminho, "corpo": corpo,
                                                          "consulta": consulta},
                "descricao": op["descricao"],
                "aviso": "isto vai para fora (cliente, QuickBooks, DocuSign, e-mail ou Asana) ou cobra. "
                         "Mostre à pessoa o que vai acontecer e chame de novo com confirmar=true."}
    status, resposta = _requisicao(ctx, metodo, caminho, corpo, consulta)
    if metodo != "GET":
        con = conectar()
        try:
            auditar(con, "mcp.call", f"user:{quem.get('id')}", user_id=quem.get("id"), entity_type="mcp",
                    detail={"metodo": metodo, "caminho": caminho, "status": status, "via": quem.get("via"),
                            "cliente_oauth": quem.get("client_id"), "confirmado": bool(confirmar)})
            con.commit()
        finally:
            con.close()
    return {"status": status, "ok": 200 <= status < 300, "resposta": resposta}


def _requisicao(ctx, metodo, caminho, corpo, consulta):
    """A requisição de verdade, para o próprio app (ASGI), com a credencial de quem chamou.
    Roda num laço de eventos próprio: quem chama já está fora do laço do servidor."""
    import httpx
    from command_center.api.main import app

    async def _vai():
        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transporte, base_url=ctx["base_url"]) as c:
            return await c.request(metodo, caminho, params=consulta or None,
                                   json=corpo if corpo is not None and metodo != "GET" else None,
                                   headers=ctx["cabecalhos"], timeout=120)
    r = asyncio.run(_vai())
    try:
        resposta = r.json()
    except (ValueError, json.JSONDecodeError):
        resposta = r.text[:4000]
    return r.status_code, resposta

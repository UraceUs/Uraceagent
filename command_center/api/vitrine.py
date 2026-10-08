"""Rotas do site novo (#148, #164): todas as páginas em novo.urace.us, a agenda pública e os
formulários de contato e de pedido da loja.

As páginas só respondem nos endereços do site (`CC_SITE_HOSTS`, por padrão `novo.urace.us`).
Em ops.urace.us e my.urace.us, `/` continua do jeito que era (o Caddy manda para o painel ou
para a área do cliente) e um caminho do site devolve 404 — o painel não vira vitrine.

Os endereços do urace.us de hoje (WordPress) viram 301 para o endereço novo
(`paginas_site.redirecionamentos()`): nada que o Google indexou cai no 404.

A agenda pública (`/ops/api/vitrine/agenda`) é a mesma da área do cliente, sem login e com
menos: só dia, turno, aberto ou não e vagas. Nunca o motivo de um dia fechado, nem quem marcou.

Contato e pedido da loja (#164) entram no funil de Vendas do Command Center como oportunidade
(origem "Site") e avisam a equipe por e-mail — tudo conectado por ali, como o dono pediu.
"""
import json
import os
import re
import sqlite3
import threading
import time
from functools import lru_cache
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from command_center.db import agora, get_db, inserir
from command_center.providers import agenda_sessoes as ag
from command_center.vitrine import paginas
from command_center.vitrine import paginas_site as ps

r = APIRouter(tags=["vitrine"])

# Política própria do site: nada de fora (fontes e fotos são nossas), nenhum script inline.
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; font-src 'self'; script-src 'self'; "
       "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")

# Páginas fixas: caminho → função(host). As dinâmicas (blog, loja, contato) estão em `_dinamica`.
PAGINAS = {
    "/": paginas.home,
    "/services/arrive-and-drive/": paginas.arrive_and_drive,
    "/services/": ps.hub,
    "/academy/": ps.academy,
    "/pro-team/": ps.pro_team,
    "/for-beginners/": ps.beginners,
    "/career/": ps.career,
    "/about/": ps.about,
    "/accessibility/": ps.accessibility,
    "/blog/": ps.blog,
    "/store/": ps.store,
}
for _s in ps.S.SERVICOS:
    PAGINAS[_s["caminho"]] = (lambda d: (lambda host: ps.servico(host, d)))(_s)


def hosts():
    return {h.strip().lower() for h in os.environ.get("CC_SITE_HOSTS", "novo.urace.us").split(",") if h.strip()}


def host_de(request):
    return (request.headers.get("host") or "").split(":")[0].strip().lower()


def e_do_site(request):
    return host_de(request) in hosts()


def _html(conteudo, status=200):
    return HTMLResponse(conteudo, status_code=status, headers={
        "Content-Security-Policy": CSP,
        "X-Frame-Options": "DENY",
        # página pública, igual para todo mundo: pode ficar 5 min no navegador
        "Cache-Control": "public, max-age=300",
    })


@lru_cache(maxsize=1)
def redirecionamentos():
    return ps.redirecionamentos()


def _slug(s):
    return s if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,120}", s or "") else None


def _dinamica(host, caminho, q):
    """Blog, loja e contato: o caminho carrega o slug. None quando não existe."""
    m = re.fullmatch(r"/blog/category/([^/]+)/", caminho)
    if m:
        return ps.blog(host, _slug(m.group(1)))
    m = re.fullmatch(r"/blog/([^/]+)/", caminho)
    if m:
        return ps.post(host, _slug(m.group(1)))
    m = re.fullmatch(r"/store/p/([^/]+)/", caminho)
    if m:
        return ps.product(host, _slug(m.group(1)), enviado=q.get("sent") == "1")
    m = re.fullmatch(r"/store/([^/]+)/", caminho)
    if m:
        return ps.store(host, _slug(m.group(1)))
    if caminho == "/contact/":
        assunto = q.get("assunto") if q.get("assunto") in dict(ps.P.CONTACT["assuntos"]) else None
        return ps.contact(host, assunto, (q.get("produto") or "")[:120] or None, enviado=q.get("sent") == "1")
    return None


def existe(caminho, host="novo.urace.us"):
    return caminho in PAGINAS or _dinamica(host, caminho, {}) is not None


def pagina(request: Request, caminho: str):
    """O que o site responde em `caminho` (sempre começando com /)."""
    if not e_do_site(request):
        raise HTTPException(404)
    host = host_de(request)
    q = dict(request.query_params)
    if caminho in PAGINAS:
        return _html(PAGINAS[caminho](host))
    html = _dinamica(host, caminho, q)
    if html:
        return _html(html)
    # endereço do urace.us de hoje → o novo (301, sem perder o que o Google indexou)
    novo = redirecionamentos().get(caminho) or redirecionamentos().get(caminho + "/")
    if novo:
        return RedirectResponse(novo, status_code=301)
    # o mesmo endereço sem a barra final (como o WordPress fazia): 301 para o certo
    if not caminho.endswith("/") and existe(caminho + "/", host):
        return RedirectResponse(caminho + "/" + (f"?{request.url.query}" if request.url.query else ""), status_code=301)
    return _html(paginas.nao_achou(host), status=404)


@r.get("/", include_in_schema=False)
def inicio(request: Request):
    return pagina(request, "/")


@r.get("/services/arrive-and-drive/", include_in_schema=False)
@r.get("/services/arrive-and-drive", include_in_schema=False)
def arrive_and_drive(request: Request):
    return pagina(request, request.url.path)


@r.get("/ops/api/vitrine/agenda")
def agenda_publica(con: sqlite3.Connection = Depends(get_db)):
    """Os dias que o cliente pode pedir, do jeito que a área do cliente mostra — sem login.

    Só aberto/fechado e vagas por turno; o horário de cada turno vem da configuração."""
    d = ag.disponibilidade(con)            # visão do cliente: horizonte e antecedência já aplicados
    dias = [{"date": x["date"],
             "manha": {"open": x["periods"]["manha"]["open"], "spots": x["periods"]["manha"]["spots"]},
             "tarde": {"open": x["periods"]["tarde"]["open"], "spots": x["periods"]["tarde"]["spots"]}}
            for x in d["dias"]]
    cfg = d["config"]
    return {"config": {k: cfg[k] for k in ("morning_start", "morning_end", "afternoon_start", "afternoon_end")},
            "dias": dias}


@r.get("/ops/api/vitrine/servicos")
def servicos_publicos(con: sqlite3.Connection = Depends(get_db)):
    """#164: o que o site vende, para a reserva montar o resumo antes do login: nome, preço e o
    depósito reembolsável. Nada do QuickBooks."""
    from command_center.providers import servicos_site
    return {"services": servicos_site.para_cliente(con), "auto_sell": bool(ag.config(con).get("auto_sell"))}


# ------------------------------------------------------------------ contato e pedido (#164)
_JANELA, _MAXIMO = 600, 8                   # por IP: 8 envios a cada 10 min
_envios: dict[str, list[float]] = {}
_tranca = threading.Lock()


def _ip(request):
    return (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "") or "?").split(",")[0].strip()


def _estourou(ip):
    with _tranca:
        t = time.time()
        fila = [x for x in _envios.get(ip, ()) if t - x < _JANELA]
        if len(fila) >= _MAXIMO:
            _envios[ip] = fila
            return True
        fila.append(t)
        _envios[ip] = fila
        return False


async def _campos(request):
    """O formulário vem como JSON (contato.js) ou urlencoded (sem JavaScript). Só texto, aparado."""
    corpo = await request.body()
    tipo = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if tipo == "application/json":
        try:
            dados = json.loads(corpo or b"{}")
        except ValueError:
            raise HTTPException(400, "JSON inválido")
        if not isinstance(dados, dict):
            raise HTTPException(400, "JSON inválido")
    else:
        dados = {k: v[0] for k, v in parse_qs(corpo.decode("utf-8", "replace"), keep_blank_values=True).items()}
    return {k: str(v or "").strip()[:2000] for k, v in dados.items() if isinstance(v, (str, int, float))}


def _responde(request, ok, volta, erro=None):
    """fetch recebe JSON; o formulário sem JavaScript volta para a página com `?sent=1`."""
    quer_json = "application/json" in (request.headers.get("accept") or "") or \
        (request.headers.get("content-type") or "").startswith("application/json")
    if quer_json:
        return JSONResponse({"ok": ok, **({"erro": erro} if erro else {})}, status_code=200 if ok else 400,
                            headers={"Cache-Control": "no-store"})
    if not ok:
        raise HTTPException(400, erro)
    return RedirectResponse(volta, status_code=303)


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validar(c):
    if c.get("site"):
        return "robo"                      # honeypot preenchido: um robô. Diz "ok" e descarta.
    if len(c.get("nome", "")) < 2:
        return "Please tell us your name."
    if not EMAIL_RE.match(c.get("email", "")):
        return "Please check your email address."
    return None


def _avisar_equipe(assunto, texto):
    from command_center.providers import email_envio
    try:
        email_envio.enviar("support@urace.us", assunto, texto)
    except Exception:                                   # noqa: BLE001 — já está no funil; o e-mail é aviso
        pass


def _confirmar_pessoa(para, assunto, texto):
    from command_center.providers import email_envio
    try:
        email_envio.enviar(para, assunto, texto)
    except Exception:                                   # noqa: BLE001
        pass


def _oportunidade(con, c, servico, valor, notas, origem="Site"):
    oid = inserir(con, "opportunities", name=c["nome"], email=c["email"].lower(), phone=c.get("telefone") or None,
                  service=servico, amount=valor, stage="NOVO", source=origem, notes=notas)
    inserir(con, "opp_events", opp_id=oid, kind="note", title="Chegou pelo site", detail=notas[:2000], at=agora(), actor="site")
    con.commit()
    return oid


@r.post("/ops/api/vitrine/contato", include_in_schema=False)
async def contato(request: Request, con: sqlite3.Connection = Depends(get_db)):
    """O formulário de /contact/: vira oportunidade em Vendas (origem Site) e avisa support@."""
    if not e_do_site(request):
        raise HTTPException(404)
    c = await _campos(request)
    erro = _validar(c)
    if erro == "robo":
        return _responde(request, True, "/contact/?sent=1")
    if erro:
        return _responde(request, False, "/contact/", erro)
    if _estourou(_ip(request)):
        return _responde(request, False, "/contact/", "Too many messages in a row. Please try again in a few minutes.")
    if len(c.get("mensagem", "")) < 2:
        return _responde(request, False, "/contact/", "Please write a message.")
    assuntos = dict(ps.P.CONTACT["assuntos"])
    assunto = assuntos.get(c.get("assunto"), "Something else")
    notas = f"[{assunto}] {c['mensagem']}"
    oid = _oportunidade(con, c, assunto, None, notas)
    _avisar_equipe(f"Site · contato: {assunto} — {c['nome']}",
                   f"{c['nome']} <{c['email']}> {c.get('telefone') or ''}\nAssunto: {assunto}\n\n{c['mensagem']}\n\n"
                   f"Vendas: https://ops.urace.us/ops/sales/{oid}")
    _confirmar_pessoa(c["email"], "We got your message — URACE",
                      f"Hi {c['nome'].split()[0]},\n\nThanks for reaching out to URACE. We received your message about "
                      f"{assunto} and will reply shortly, usually within one business day.\n\nIn a hurry? Call or WhatsApp "
                      f"+1 (407) 250 2291.\n\nURACE — the Champion's Factory\nOrlando Kart Center, 10724 Cosmonaut Blvd, Box 3, Orlando, FL 32824")
    return _responde(request, True, "/contact/?sent=1")


@r.post("/ops/api/vitrine/pedido", include_in_schema=False)
async def pedido(request: Request, con: sqlite3.Connection = Depends(get_db)):
    """O pedido da loja: produto, variação e quantidade viram oportunidade com o valor estimado;
    a equipe confirma estoque e frete e manda a invoice do QuickBooks. Nada é cobrado aqui."""
    if not e_do_site(request):
        raise HTTPException(404)
    c = await _campos(request)
    produtos = {p["slug"]: p for p in ps.dados("produtos.json")["produtos"]}
    p = produtos.get(c.get("produto") or "")
    volta = f"/store/p/{p['slug']}/" if p else "/store/"
    erro = _validar(c)
    if erro == "robo":
        return _responde(request, True, volta + "?sent=1")
    if not p:
        return _responde(request, False, volta, "Product not found.")
    if erro:
        return _responde(request, False, volta, erro)
    if _estourou(_ip(request)):
        return _responde(request, False, volta, "Too many requests in a row. Please try again in a few minutes.")
    try:
        qtd = max(1, min(20, int(c.get("quantidade") or 1)))
    except ValueError:
        qtd = 1
    variacao = next((v for v in p["variations"] if " / ".join(v["attrs"]) == c.get("variacao")), None)
    unit = (variacao or {}).get("price") or p["price"] or None
    valor = round(unit * qtd, 2) if unit else None
    desc = p["name"] + (f" ({' / '.join(variacao['attrs'])})" if variacao else "") + (f" × {qtd}" if qtd > 1 else "")
    notas = f"[Loja] {desc}" + (f" — {paginas.usd(valor)}" if valor else " — preço a confirmar") + \
        (f"\n{c['mensagem']}" if c.get("mensagem") else "")
    oid = _oportunidade(con, c, f"Store: {desc}", valor, notas)
    _avisar_equipe(f"Site · pedido da loja: {desc} — {c['nome']}",
                   f"{c['nome']} <{c['email']}> {c.get('telefone') or ''}\n{desc}\nValor estimado: {paginas.usd(valor) if valor else 'a confirmar'}\n"
                   f"{c.get('mensagem') or ''}\n\nVendas: https://ops.urace.us/ops/sales/{oid}")
    _confirmar_pessoa(c["email"], "We got your order request — URACE Store",
                      f"Hi {c['nome'].split()[0]},\n\nThanks for your order request: {desc}"
                      f"{' — ' + paginas.usd(valor) if valor else ''}.\n\nOur team will confirm availability, shipping and the total, "
                      f"and send you an invoice to pay online. Nothing has been charged.\n\nQuestions? Call or WhatsApp +1 (407) 250 2291.\n\n"
                      f"URACE — the Champion's Factory")
    return _responde(request, True, volta + "?sent=1")


def robots(request):
    """robots.txt do site: enquanto é prévia, ninguém indexa; depois, só o painel fica de fora."""
    if paginas.preview():
        return "User-agent: *\nDisallow: /\n"
    return (f"User-agent: *\nDisallow: /ops/\nAllow: /\n\nSitemap: https://{host_de(request)}/sitemap.xml\n")


def sitemap(request):
    host = host_de(request)
    urls = "".join(f"  <url><loc>https://{host}{c}</loc></url>\n" for c in ps.caminhos())
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "</urlset>\n")

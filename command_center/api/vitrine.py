"""Rotas do site novo (#148): as páginas em novo.urace.us e a agenda pública.

As páginas só respondem nos endereços do site (`CC_SITE_HOSTS`, por padrão `novo.urace.us`).
Em ops.urace.us e my.urace.us, `/` continua do jeito que era (o Caddy manda para o painel ou
para a área do cliente) e um caminho do site devolve 404 — o painel não vira vitrine.

A agenda pública (`/ops/api/vitrine/agenda`) é a mesma da área do cliente, sem login e com
menos: só dia, turno, aberto ou não e vagas. Nunca o motivo de um dia fechado, nem quem marcou.
"""
import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from command_center.db import get_db
from command_center.providers import agenda_sessoes as ag
from command_center.vitrine import paginas

r = APIRouter(tags=["vitrine"])

# Política própria do site: nada de fora (fontes e fotos são nossas), nenhum script inline.
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; font-src 'self'; script-src 'self'; "
       "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")

PAGINAS = {
    "/": paginas.home,
    "/services/arrive-and-drive/": paginas.arrive_and_drive,
}


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


def pagina(request: Request, caminho: str):
    """O que o site responde em `caminho` (sempre começando com /)."""
    if not e_do_site(request):
        raise HTTPException(404)
    host = host_de(request)
    if caminho in PAGINAS:
        return _html(PAGINAS[caminho](host))
    # o mesmo endereço sem a barra final (como o WordPress fazia): 301 para o certo
    if not caminho.endswith("/") and caminho + "/" in PAGINAS:
        return RedirectResponse(caminho + "/", status_code=301)
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


def robots(request):
    """robots.txt do site: enquanto é prévia, ninguém indexa; depois, só o painel fica de fora."""
    if paginas.preview():
        return "User-agent: *\nDisallow: /\n"
    return (f"User-agent: *\nDisallow: /ops/\nAllow: /\n\nSitemap: https://{host_de(request)}/sitemap.xml\n")


def sitemap(request):
    host = host_de(request)
    urls = "".join(f"  <url><loc>https://{host}{c}</loc></url>\n" for c in PAGINAS)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "</urlset>\n")

"""O que o mundo de fora (Google, Bing) pode ver deste servidor (issue #25).

O Command Center é um painel com login: fica FORA dos buscadores (`noindex` no HTML e
bloqueado aqui). Públicas são só as páginas legais (/legal/, exigidas pela Intuit para o
app do QuickBooks) — essas entram no sitemap, com canonical e schema markup no próprio HTML.

O domínio do sitemap vem da requisição, mas só se for um dos nossos: um `Host` inventado
não vira link no sitemap (injeção de cabeçalho).
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response

r = APIRouter(tags=["publico"])

LEGAL = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "adminai", "deploy", "legal"))
PAGINAS = ("privacy", "eula")


def _host(request):
    """#79: o nome por onde a pessoa entrou, se for nosso; senão, ops.urace.us."""
    from command_center import enderecos
    return enderecos.host_da_requisicao(request)


@r.get("/robots.txt", response_class=PlainTextResponse)
def robots(request: Request):
    from command_center.api import vitrine
    if vitrine.e_do_site(request):           # #148: o site novo tem o próprio
        return vitrine.robots(request)
    return ("User-agent: *\n"
            "Disallow: /ops/\n"
            "Disallow: /kommo/\n"
            "Disallow: /human/\n"
            "Disallow: /health\n"
            "Allow: /legal/\n"
            f"\nSitemap: https://{_host(request)}/sitemap.xml\n")


@r.get("/sitemap.xml")
def sitemap(request: Request):
    from command_center.api import vitrine
    if vitrine.e_do_site(request):
        return Response(vitrine.sitemap(request), media_type="application/xml",
                        headers={"Cache-Control": "public, max-age=86400"})
    host = _host(request)
    urls = []
    for p in PAGINAS:
        caminho = os.path.join(LEGAL, f"{p}.html")
        quando = datetime.fromtimestamp(os.path.getmtime(caminho), timezone.utc).strftime("%Y-%m-%d") \
            if os.path.exists(caminho) else None
        urls.append(f"  <url><loc>https://{host}/legal/{p}.html</loc>"
                    + (f"<lastmod>{quando}</lastmod>" if quando else "") + "<changefreq>yearly</changefreq></url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n")
    return Response(xml, media_type="application/xml", headers={"Cache-Control": "public, max-age=86400"})

"""O que o mundo de fora (Google, Bing) pode ver deste servidor (issue #25).

O Command Center é um painel com login: fica FORA dos buscadores (`noindex` no HTML e
bloqueado aqui). Públicas são só as páginas legais (/legal/, exigidas pela Intuit para o
app do QuickBooks) — essas entram no sitemap, com canonical e schema markup no próprio HTML.

O domínio do sitemap vem da requisição, mas só se for um dos nossos: um `Host` inventado
não vira link no sitemap (injeção de cabeçalho).
"""
import os
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response

r = APIRouter(tags=["publico"])

LEGAL = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "adminai", "deploy", "legal"))
PAGINAS = ("privacy", "eula")
PADRAO = "urace-bridge.duckdns.org"


def _dominios():
    nossos = {PADRAO}
    for v in (os.environ.get("CC_PUBLIC_URL"), os.environ.get("CC_PUBLIC_HOST")):
        if v:
            nossos.add(urlsplit(v if "://" in v else "https://" + v).hostname or v)
    nossos.update(d.strip() for d in os.environ.get("CC_DOMINIOS_EXTRAS", "").split() if d.strip())
    return nossos


def _host(request):
    h = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(":")[0].lower()
    return h if h in _dominios() else PADRAO


@r.get("/robots.txt", response_class=PlainTextResponse)
def robots(request: Request):
    return ("User-agent: *\n"
            "Disallow: /ops/\n"
            "Disallow: /kommo/\n"
            "Disallow: /human/\n"
            "Disallow: /health\n"
            "Allow: /legal/\n"
            f"\nSitemap: https://{_host(request)}/sitemap.xml\n")


@r.get("/sitemap.xml")
def sitemap(request: Request):
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

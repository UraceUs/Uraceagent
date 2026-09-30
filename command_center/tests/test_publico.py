"""Páginas públicas (issue #25): robots.txt, sitemap.xml, canonical, meta e schema markup."""
import json
import os
import re
import xml.etree.ElementTree as ET

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api.main import app  # noqa: E402

LEGAL = os.path.join(os.path.dirname(__file__), "..", "..", "adminai", "deploy", "legal")
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    with TestClient(app, base_url="https://urace-bridge.duckdns.org") as t:
        yield t


def test_robots_tira_o_painel_e_deixa_as_paginas_legais(cli):
    r = cli.get("/robots.txt")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "Disallow: /ops/" in r.text and "Allow: /legal/" in r.text
    assert "Sitemap: https://urace-bridge.duckdns.org/sitemap.xml" in r.text


def test_sitemap_e_xml_valido_com_as_paginas_publicas(cli):
    r = cli.get("/sitemap.xml")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    locs = [e.text for e in ET.fromstring(r.content).findall("s:url/s:loc", NS)]
    assert locs == ["https://urace-bridge.duckdns.org/legal/privacy.html", "https://urace-bridge.duckdns.org/legal/eula.html"]
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", e.text) for e in ET.fromstring(r.content).findall("s:url/s:lastmod", NS))
    assert "/ops" not in r.text, "o painel nunca vai para o sitemap"


def test_host_inventado_nao_vira_link(cli, monkeypatch):
    assert "evil.example" not in cli.get("/sitemap.xml", headers={"Host": "evil.example"}).text
    monkeypatch.setenv("CC_DOMINIOS_EXTRAS", "ops.urace.us")
    assert "https://ops.urace.us/legal/eula.html" in cli.get("/sitemap.xml", headers={"Host": "ops.urace.us"}).text


@pytest.mark.parametrize("nome", ["privacy", "eula"])
def test_pagina_legal_com_seo_completo(nome):
    html = open(os.path.join(LEGAL, f"{nome}.html"), encoding="utf-8").read()
    assert len(re.findall(r"<h1[\s>]", html)) == 1, "um h1 só"
    niveis = [int(n) for n in re.findall(r"<h([1-6])[\s>]", html)]
    assert all(b <= a + 1 for a, b in zip(niveis, niveis[1:])), "sem pular nível de cabeçalho"
    url = f"https://urace-bridge.duckdns.org/legal/{nome}.html"
    assert f'<link rel="canonical" href="{url}">' in html
    desc = re.search(r'<meta name="description" content="([^"]+)">', html).group(1)
    assert 70 <= len(desc) <= 200, "descrição do tamanho que o Google mostra"
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.+?)</script>', html, re.S).group(1))
    assert ld["@type"] == "WebPage" and ld["url"] == url and ld["publisher"]["name"] == "URACE.US INC"
    end = ld["publisher"]["address"]
    assert end["streetAddress"] in html and end["postalCode"] in html, "schema só com dado que está na página (NO FAKE DATA)"


def test_titulos_unicos():
    titulos = [re.search(r"<title>(.+?)</title>", open(os.path.join(LEGAL, f"{n}.html"), encoding="utf-8").read()).group(1)
               for n in ("privacy", "eula")]
    assert len(set(titulos)) == 2


def test_painel_continua_fora_dos_buscadores():
    idx = open(os.path.join(os.path.dirname(__file__), "..", "web", "index.html"), encoding="utf-8").read()
    assert '<meta name="robots" content="noindex, nofollow" />' in idx

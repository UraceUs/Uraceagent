"""Site novo da URACE em novo.urace.us (#148): páginas montadas no servidor, só no endereço do
site, com SEO completo, as fotos e os preços do urace.us de hoje, e a agenda pública."""
import json
import os
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir  # noqa: E402
from command_center.providers import agenda_sessoes as ag  # noqa: E402
from command_center.vitrine import conteudo, paginas_site  # noqa: E402

SITE = "https://novo.urace.us"
PAGINAS = tuple(paginas_site.caminhos())           # o site inteiro (#164): 100+ páginas


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    monkeypatch.delenv("CC_SITE_HOSTS", raising=False)
    monkeypatch.delenv("CC_SITE_PREVIEW", raising=False)
    with TestClient(app, base_url=SITE) as t:
        yield t


class _Leitor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.attrs, self.ld, self._em_ld, self.h = [], [], [], False, []
        self._h = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append(tag)
        self.attrs.append((tag, a))
        if tag == "script" and a.get("type") == "application/ld+json":
            self._em_ld = True
        if re.fullmatch(r"h[1-6]", tag):
            self._h = [tag, ""]

    def handle_endtag(self, tag):
        if tag == "script":
            self._em_ld = False
        if self._h and tag == self._h[0]:
            self.h.append(tuple(self._h))
            self._h = None

    def handle_data(self, data):
        if self._em_ld:
            self.ld.append(json.loads(data))
        if self._h:
            self._h[1] += data


def _le(html):
    p = _Leitor()
    p.feed(html)
    return p


@pytest.mark.parametrize("caminho", PAGINAS)
def test_pagina_do_site_com_seo_completo(cli, caminho):
    r = cli.get(caminho)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    p = _le(r.text)
    assert [n for n, _ in p.h].count("h1") == 1, "um h1 por página"
    niveis = [int(n[1]) for n, _ in p.h if n != "h1"]
    assert niveis and niveis[0] == 2, "depois do h1 vem h2"
    assert all(b - a <= 1 for a, b in zip([1] + niveis, niveis)), "sem pular nível de título"
    metas = {a.get("name") or a.get("property"): a.get("content") for t, a in p.attrs if t == "meta"}
    assert metas["description"] and len(metas["description"]) >= 80
    assert metas["robots"] == "noindex, nofollow", "prévia: fora do Google até a troca"
    canon = [a["href"] for t, a in p.attrs if t == "link" and a.get("rel") == "canonical"]
    assert canon == [SITE + caminho]
    assert any("LocalBusiness" in str(x.get("@type")) for x in p.ld), "schema do negócio"
    # política própria e sem nada de fora: fontes e fotos são nossas
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert not re.search(r"(src|href)=\"https?://(?!novo\.urace\.us)[^\"]+\.(css|js|woff2?)", r.text)
    assert "style=" not in r.text, "sem estilo inline (a política não deixa)"


def test_titulos_e_descricoes_unicos(cli):
    vistos = {cli.get(c).text.split("<title>")[1].split("</title>")[0] for c in PAGINAS}
    assert len(vistos) == len(PAGINAS)


def test_nenhum_link_volta_ao_wordpress_e_nenhum_link_interno_quebra(cli):
    """#164: o site inteiro mora aqui. O menu não aponta para urace.us, e todo link interno de
    toda página abre (200) ou é um 301 que leva a uma página que abre."""
    internos, externos_antigos = set(), set()
    for c in PAGINAS:
        html = cli.get(c).text
        for h in re.findall(r'href="([^"#]+)', html):
            if h.startswith("https://urace.us"):
                externos_antigos.add((c, h))
            elif h.startswith("/") and not h.startswith(("/ops/", "/_s/", "/legal/")):
                internos.add(h.split("?")[0])
    assert not externos_antigos
    quebrados = []
    for h in sorted(internos):
        r = cli.get(h, follow_redirects=False)
        if r.status_code == 301:
            r = cli.get(r.headers["location"], follow_redirects=False)
        if r.status_code != 200:
            quebrados.append((h, r.status_code))
    assert not quebrados


@pytest.mark.parametrize("antigo, novo", [
    ("/kart-training-packages/", "/academy/"),
    ("/professional-kart-team-racing-team/", "/pro-team/"),
    ("/the-driver-factory/", "/career/"),
    ("/shop/", "/store/"),
    ("/product-category/engines/", "/store/engines/"),
    ("/book-online/", "/ops/portal/reserve"),
    ("/corporate-events", "/services/corporate-events/"),
])
def test_endereco_do_urace_us_de_hoje_redireciona_para_o_novo(cli, antigo, novo):
    r = cli.get(antigo, follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == novo


def test_loja_e_blog_vieram_inteiros(cli):
    d = paginas_site.dados("produtos.json")
    assert len(d["produtos"]) >= 60 and sum(1 for p in d["produtos"] if p["images"]) >= 0.8 * len(d["produtos"])
    r = cli.get("/store/")
    assert r.status_code == 200 and r.text.count("produto-card") == len(d["produtos"])
    um = d["produtos"][0]
    r = cli.get(f"/store/p/{um['slug']}/")
    assert um["name"] in r.text and 'action="/ops/api/vitrine/pedido"' in r.text
    assert [x for x in _le(r.text).ld if x.get("@type") == "Product"][0]["offers"]["priceCurrency"] == "USD"
    assert cli.get(f"/product/{um['slug']}/", follow_redirects=False).headers["location"] == f"/store/p/{um['slug']}/"
    posts = paginas_site.dados("posts.json")["posts"]
    assert len(posts) >= 7
    r = cli.get(f"/blog/{posts[0]['slug']}/")
    assert posts[0]["title"] in r.text and "{IMG:" not in r.text
    assert [x for x in _le(r.text).ld if x.get("@type") == "BlogPosting"]
    assert cli.get("/blog/nao-existe/").status_code == 404 and cli.get("/store/p/nao-existe/").status_code == 404


def test_contato_do_site_vira_oportunidade_em_vendas_e_avisa_a_equipe(cli, tmp_path, monkeypatch):
    """#164: tudo conectado pelo Command Center — o formulário entra no funil de Vendas (origem Site)."""
    caixa = tmp_path / "emails.jsonl"
    monkeypatch.setenv("CC_EMAIL_FAKE", str(caixa))
    r = cli.get("/contact/?assunto=academy&produto=3%20months")
    assert '<option value="academy" selected>' in r.text and "About: 3 months" in r.text
    r = cli.post("/ops/api/vitrine/contato", json={"nome": "Ana Lima", "email": "ana@exemplo.com", "telefone": "407 555 0101",
                                                  "assunto": "academy", "mensagem": "My son is 9, when can he start?"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    con = conectar(); aplicar_schema(con)
    o = con.execute("SELECT name, email, service, stage, source, notes FROM opportunities").fetchall()
    assert [tuple(x) for x in o] == [("Ana Lima", "ana@exemplo.com", "URACE Academy", "NOVO", "Site", "[URACE Academy] My son is 9, when can he start?")]
    emails = [json.loads(x) for x in caixa.read_text(encoding="utf-8").splitlines()]
    assert [m["to"] for m in emails] == ["support@urace.us", "ana@exemplo.com"]
    assert "ops.urace.us/ops/sales/" in emails[0]["text"] and "Ana" in emails[1]["text"]
    # sem JavaScript: o formulário volta para a página com o aviso
    r = cli.post("/ops/api/vitrine/contato", data={"nome": "Bia", "email": "bia@exemplo.com", "mensagem": "Hi"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/contact/?sent=1"
    assert "aviso-ok" in cli.get("/contact/?sent=1").text
    # robô (honeypot preenchido) e dado ruim não entram no funil
    assert cli.post("/ops/api/vitrine/contato", json={"nome": "x", "email": "r@r.com", "mensagem": "spam", "site": "http://spam"}).json()["ok"]
    assert cli.post("/ops/api/vitrine/contato", json={"nome": "Caio", "email": "sem-arroba", "mensagem": "oi"}).status_code == 400
    assert con.execute("SELECT count(*) FROM opportunities").fetchone()[0] == 2
    # e no painel o site não existe
    with TestClient(app, base_url="https://ops.urace.us") as t:
        assert t.post("/ops/api/vitrine/contato", json={"nome": "Z", "email": "z@z.com", "mensagem": "z"}).status_code == 404


def test_pedido_da_loja_vira_oportunidade_com_o_valor(cli, tmp_path, monkeypatch):
    monkeypatch.setenv("CC_EMAIL_FAKE", str(tmp_path / "emails.jsonl"))
    d = paginas_site.dados("produtos.json")
    p = next(x for x in d["produtos"] if x["variations"] and x["variations"][0].get("price"))
    v = p["variations"][0]
    r = cli.post("/ops/api/vitrine/pedido", json={"produto": p["slug"], "variacao": " / ".join(v["attrs"]), "quantidade": "2",
                                                 "nome": "Dan Reis", "email": "dan@exemplo.com", "mensagem": "Ship to Tampa"})
    assert r.json() == {"ok": True}
    con = conectar(); aplicar_schema(con)
    o = con.execute("SELECT service, amount, notes FROM opportunities").fetchone()
    assert o["service"] == f"Store: {p['name']} ({' / '.join(v['attrs'])}) × 2"
    assert o["amount"] == round(v["price"] * 2, 2) and "Ship to Tampa" in o["notes"]
    assert cli.post("/ops/api/vitrine/pedido", json={"produto": "nao-existe", "nome": "Dan", "email": "d@d.com"}).status_code == 400


def test_arrive_and_drive_mostra_os_precos_de_hoje_e_leva_para_a_agenda(cli):
    r = cli.get("/services/arrive-and-drive/")
    for k in conteudo.KARTS:
        assert f'value="{k["nome"]}" data-preco="{k["preco"]}"' in r.text
    assert {k["preco"] for k in conteudo.KARTS} == {719, 819, 899}, "os preços do urace.us em 07/10"
    assert "Your Own Kart" not in r.text, "não aparece no site público de hoje"
    assert 'href="/ops/portal/reserve"' in r.text, "sem JavaScript, o botão leva para a reserva (#164)"
    assert 'data-api="/ops/api/vitrine/agenda"' in r.text
    ofertas = [x for x in _le(r.text).ld if x.get("@type") == "Service"][0]["offers"]
    assert sorted(float(o["price"]) for o in ofertas) == [719.0, 719.0, 819.0, 899.0]
    assert "Box 3" in r.text and "Box 5" not in r.text, "endereço da decisão de 01/10"


def test_sem_barra_final_redireciona(cli):
    r = cli.get("/services/arrive-and-drive", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/services/arrive-and-drive/"
    r = cli.get("/blog", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/blog/"


def test_pagina_que_nao_existe_e_404_do_site(cli):
    r = cli.get("/about-us-que-nao-existe/")
    assert r.status_code == 404 and "Page not found" in r.text and "<h1>" in r.text


def test_painel_e_area_do_cliente_continuam_iguais(cli):
    """Nos endereços do painel o site não existe: / e os caminhos do site dão 404 como antes."""
    for host in ("https://ops.urace.us", "https://my.urace.us", "https://urace-bridge.duckdns.org"):
        with TestClient(app, base_url=host) as t:
            assert t.get("/").status_code == 404
            assert t.get("/services/arrive-and-drive/").status_code == 404
            assert "Disallow: /ops/" in t.get("/robots.txt").text
    # e no endereço do site, o painel e a área do cliente seguem no mesmo lugar
    assert cli.get("/ops/api/portal/me").status_code == 401
    assert cli.get("/ops/api/dashboard").status_code == 401


def test_robots_e_sitemap_do_site(cli, monkeypatch):
    assert cli.get("/robots.txt").text == "User-agent: *\nDisallow: /\n"
    monkeypatch.setenv("CC_SITE_PREVIEW", "0")
    assert "Sitemap: https://novo.urace.us/sitemap.xml" in cli.get("/robots.txt").text
    assert 'name="robots"' not in cli.get("/").text, "depois da troca, o Google pode indexar"
    locs = [u.text for u in ET.fromstring(cli.get("/sitemap.xml").content).iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert locs == [SITE + c for c in PAGINAS]


def test_arquivos_do_site_com_cache_e_tipo_certo(cli):
    css = cli.get("/_s/site.css")
    assert css.status_code == 200 and "max-age=604800" in css.headers["cache-control"]
    assert cli.get("/_s/fonts/archivo-expanded.woff2").headers["content-type"] == "font/woff2"
    foto = cli.get("/_s/img/home-hero.webp")
    assert foto.headers["content-type"] == "image/webp"
    assert b"Exif" not in foto.content[:4096], "foto sem EXIF"
    assert cli.get("/_s/../api/main.py").status_code == 404


def test_fotos_do_site_comprimidas():
    pasta = os.path.join(os.path.dirname(conteudo.__file__), "static", "img")
    from PIL import Image
    for nome in os.listdir(pasta):
        if nome.endswith(".webp"):
            with Image.open(os.path.join(pasta, nome)) as im:
                assert max(im.size) <= 1600, nome
                assert "exif" not in im.info, nome
            assert os.path.getsize(os.path.join(pasta, nome)) < 200_000, nome


def test_agenda_publica_so_mostra_aberto_e_vagas(cli):
    con = conectar(); aplicar_schema(con)
    ag.mudar_semana(con, [{"weekday": d, "period": p, "open": d != 0, "capacity": 3}
                          for d in range(7) for p in ("manha", "tarde")])
    ag.bloquear(con, None, date_from="2099-01-01", date_to="2099-01-02", reason="viagem do Italo para a Itália")
    con.commit()
    r = cli.get("/ops/api/vitrine/agenda")
    assert r.status_code == 200
    d = r.json()
    assert set(d) == {"config", "dias"} and set(d["config"]) == {"morning_start", "morning_end", "afternoon_start", "afternoon_end"}
    assert d["dias"] and all(set(x) == {"date", "manha", "tarde"} for x in d["dias"])
    assert all(set(x["manha"]) == {"open", "spots"} for x in d["dias"])
    assert any(x["manha"]["open"] for x in d["dias"]), "dias de terça a domingo abertos"
    assert "Itália" not in r.text and "reason" not in r.text, "o motivo interno nunca sai"
    # ETag como toda GET da API: nada mudou → 304
    assert cli.get("/ops/api/vitrine/agenda", headers={"If-None-Match": r.headers["etag"]}).status_code == 304


def test_agenda_publica_desconta_quem_ja_marcou(cli):
    con = conectar(); aplicar_schema(con)
    ag.mudar_semana(con, [{"weekday": d, "period": p, "open": True, "capacity": 2} for d in range(7) for p in ("manha", "tarde")])
    con.commit()
    dia = [x for x in cli.get("/ops/api/vitrine/agenda").json()["dias"] if x["tarde"]["open"]][3]
    conta = inserir(con, "portal_accounts", name="Cliente Teste", email="t@exemplo.com", pw_salt="x", pw_hash="x",
                    birth_date="1990-01-01", terms_accepted_at="2026-10-07T00:00:00Z")
    inserir(con, "bookings", account_id=conta, date=dia["date"], period="tarde", status="pendente")
    con.commit()
    depois = {x["date"]: x for x in cli.get("/ops/api/vitrine/agenda").json()["dias"]}[dia["date"]]
    assert depois["tarde"]["spots"] == dia["tarde"]["spots"] - 1
    assert "Cliente Teste" not in cli.get("/ops/api/vitrine/agenda").text

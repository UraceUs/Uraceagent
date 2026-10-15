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
    ("/services/kart-school/", "/academy/"),                       # #254: virou a URACE Academy
    ("/services/professional-coaching/", "/services/arrive-and-drive/"),   # #254: virou o Arrive and Drive
    ("/professional-kart-team-racing-team/", "/pro-team/"),
    ("/the-driver-factory/", "/career/"),
    ("/shop/", "/store/"),
    ("/product-category/engines/", "/store/engines/"),
    ("/book-online/", "/services/arrive-and-drive/"),      # #252: página indexada vai para página pública
    ("/corporate-events", "/services/corporate-events/"),
])
def test_endereco_do_urace_us_de_hoje_redireciona_para_o_novo(cli, antigo, novo):
    r = cli.get(antigo, follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == novo


def test_loja_e_blog_vieram_inteiros(cli):
    d = paginas_site.dados("produtos.json")
    assert len(d["produtos"]) >= 60 and sum(1 for p in d["produtos"] if p["images"]) >= 0.8 * len(d["produtos"])
    r = cli.get("/store/")
    assert r.status_code == 200 and r.text.count("produto-card") == paginas_site.LOJA_POR_PAGINA
    inteiro = sum(cli.get(c).text.count("produto-card") for c in ["/store/"] + paginas_site.paginas_da_loja()
                  if c.startswith("/store/page/") or c == "/store/")
    assert inteiro == len(d["produtos"]), "as páginas da loja juntas mostram o catálogo inteiro"
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


def test_arrive_and_drive_mostra_os_precos_de_hoje_e_leva_para_o_carrinho(cli):
    """#263: cada kart da página carrega a chave (`data-kart`) com que o site acha o serviço do painel,
    e o preço é o do painel — que a migração semeou com os preços da Rate Card. #262: um botão só, o do
    carrinho; o "Continue to booking" (invoice do QuickBooks) saiu do site público."""
    r = cli.get("/services/arrive-and-drive/")
    for k in conteudo.KARTS:
        assert f'value="{k["nome"]}" data-kart="{k["nome"]}" data-preco="{k["preco"]:g}"' in r.text
    assert {k["preco"] for k in conteudo.KARTS} == {719, 819, 899}, "os preços do urace.us em 07/10"
    assert "Your Own Kart" not in r.text, "não aparece no site público de hoje"
    assert 'href="/ops/portal/reserve"' not in r.text, "#262: o site público não oferece mais esse caminho"
    assert "Continue to booking" not in r.text, "#262: um caminho só, o do carrinho"
    assert 'class="btn btn-cheio agenda-carrinho"' in r.text and 'data-carrinho="/cart/"' in r.text
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


# ------------------------------------------------------------------ #207: o texto do urace.us de hoje
def test_texto_do_urace_us_de_hoje_no_menu_na_home_e_no_blog(cli):
    """Dono, 13/10: "vou pegar o copy que tá no site atual e jogar naquele outro site". Os rótulos do
    menu e do rodapé, a home e o título dos artigos são os do urace.us de 13/10, nos caminhos novos."""
    r = cli.get("/")
    menu = r.text.split('<nav class="menu"')[1].split("</nav>")[0]
    for rot, href in (("About URACE", "/about/"), ("Our Services", "/services/"), ("Plan Your Career", "/career/"),
                      ("Racing Team", "/pro-team/"), ("Contact us", "/contact/")):
        assert f'href="{href}">{rot}</a>' in menu
    assert "<h1>The Champions Factory</h1>" in r.text
    assert "The ladder ends on our grid" in r.text and "Our Contents" in r.text
    assert "© 2026 URACE | All rights reserved" in r.text and ">Navigation<" in r.text
    assert "invoice #" not in r.text, "o depoimento sai sem o pagamento do cliente"
    titulo = cli.get("/blog/upgrading-your-kart-chassis-when-and-why/").text.split("<title>")[1].split("</title>")[0]
    assert titulo == "Upgrading Your Kart Chassis: When It Is Worth It | URACE"


def test_decisoes_do_dono_continuam_valendo_em_todo_o_site(cli):
    """O texto novo não traz de volta o que o dono já decidiu: Box 3, remarcação com 24 h e o nome URACE."""
    for c in PAGINAS:
        if c.startswith("/store/"):
            continue                                   # nome e descrição do produto são os da loja
        texto = re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", cli.get(c).text, flags=re.S))
        assert "Box 5" not in texto and not re.search(r"\b48 ?h", texto), c
        assert not re.search(r"\bU(race|Race|Rrace)\b", texto), c


def test_preco_de_servico_vem_do_sistema_e_nao_do_texto(cli):
    """Regra 2 da #207: o preço do Arrive and Drive sai de KARTS; os planos, do painel. O que o sistema
    não tem não vira número escrito na página."""
    minimo = f"${min(k['preco'] for k in conteudo.KARTS):,}"
    for c in ("/", "/services/", "/for-beginners/", "/services/birthday-party/"):
        assert minimo in cli.get(c).text, c
    for c in ("/services/", "/for-beginners/", "/career/", "/pro-team/"):
        html = cli.get(c).text
        for valor in ("$2,619.06", "$2,756.90", "$5,000", "$5K", "$3K", "$1,200", "$60 "):
            assert valor not in html, (c, valor)
    # com os planos no painel, o Pro Team mostra o preço deles
    from command_center.providers import servicos_site
    con = conectar(); aplicar_schema(con)
    servicos_site.criar(con, None, {"name": "Academy 1 month", "price": 2756.9, "kind": "plan", "months": 1, "sessions_month": 4})
    servicos_site.criar(con, None, {"name": "URACE Boost", "price": 5000, "kind": "plan", "months": 1, "sessions_month": 8})
    con.commit()
    html = cli.get("/pro-team/").text
    assert "<strong>$2,756.90</strong>" in html and "<strong>$5,000</strong>" in html


# ------------------------------------------------------------------ #254: os dois programas que se fundiram
ANTIGOS_254 = (("/services/kart-school/", "/academy/"), ("/services/professional-coaching/", "/services/arrive-and-drive/"))


def test_programas_fundidos_em_arrive_and_drive_e_urace_academy(cli):
    """Dono, 15/10 (#254): "o kart school se tornou Urace academy, e o professional coaching se tornou o
    arrive and drive". Os dois cartões e as duas páginas somem, o texto que fazia sentido fica em quem
    herdou, o endereço antigo redireciona e nada no site aponta para ele."""
    hub = cli.get("/services/").text
    nomes = re.findall(r'<span class="servico-txt"><strong>([^<]+)</strong>', hub)
    assert nomes[:2] == ["Arrive and Drive", "URACE Academy"]
    assert "Kart School" not in nomes and "Professional Coaching" not in nomes
    assert "video breakdown and benchmark comparison" in hub, "o cartão do coaching entrou no Arrive and Drive"
    assert "Become a racing driver" in hub, "o cartão da Kart School entrou na URACE Academy"
    # as páginas antigas não existem mais: fora do site, fora do sitemap, e 301 para quem herdou
    locs = {u.text for u in ET.fromstring(cli.get("/sitemap.xml").content).iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")}
    for antigo, novo in ANTIGOS_254:
        assert antigo not in PAGINAS and SITE + antigo not in locs
        r = cli.get(antigo, follow_redirects=False)
        assert r.status_code == 301 and r.headers["location"] == novo
    # o texto aproveitado está na página que herdou
    academy = cli.get("/academy/").text
    for trecho in ("Mentorship by winning drivers", "closed toe shoes", "How to join the URACE Academy",
                   "comprehensive racing education", "practical training, theory, real karts"):
        assert trecho in academy, trecho
    arrive = cli.get("/services/arrive-and-drive/").text
    for trecho in ("Professional coaching, data and video analysis", "Lead and Follow", "Technique and mindset training",
                   "Theory and mechanics simplified", "Drivers who already race"):
        assert trecho in arrive, trecho
    # nenhuma página do site (nem o nome do programa, nem o link) fica falando dos dois
    for c in PAGINAS:
        html = cli.get(c).text
        assert not re.search(r"\bKart School\b|\bProfessional Coaching\b", html), c
        for antigo, _ in ANTIGOS_254:
            assert f'href="{antigo}"' not in html and f'"https://novo.urace.us{antigo}"' not in html, (c, antigo)


def test_precos_do_site_batem_com_a_rate_card(cli):
    """#254, dono 15/10: "os preços são os da tabela de all rates and cards" — `brain/40_SISTEMAS/Rate Card.md`,
    seção "Tabelas ditadas pelo dono em 09/09": diária por kart, Lead and Follow fechado com antecedência e
    mensal sem contrato. Preço que não está na tabela não aparece inventado na página."""
    assert [(k["nome"], k["preco"]) for k in conteudo.KARTS] == [
        ("Baby Kart", 719), ("4-stroke", 719), ("2-stroke", 819), ("Adult Shifter", 899)], "diária tudo incluso"
    arrive = cli.get("/services/arrive-and-drive/").text
    for valor in ("$719", "$819", "$899", "$769", "$3,460.50"):
        assert valor in arrive, valor
    # o last-minute do Lead and Follow só o operador fecha na pista: não vai para o site
    assert "$395" not in arrive and "$245" not in arrive
    from command_center.vitrine import conteudo_paginas
    assert conteudo_paginas.ACADEMY["planos"][0][3] == "$2,756.90", "mensal sem contrato (4 stroke / Baby Kart)"
    assert "$2,756.90" in cli.get("/academy/").text


def _enderecos_do_urace_us():
    arq = os.path.join(os.path.dirname(__file__), "enderecos_urace_us.txt")
    with open(arq, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def test_nenhum_endereco_do_urace_us_cai_no_404(cli):
    """#252: no dia da troca, todo endereço que o urace.us de hoje publica (sitemaps do Yoast e
    links internos) tem de abrir no site novo — página ou 301 que leva a uma página que abre.
    As famílias do WooCommerce (subcategoria, etiqueta, página 2, produto que saiu do catálogo e
    as telas da conta do WordPress) não têm par no novo e caem na loja ou no portal."""
    quebrados = []
    for antigo in _enderecos_do_urace_us():
        r = cli.get(antigo, follow_redirects=False)
        if r.status_code in (301, 302, 303):
            destino = r.headers["location"]
            if destino.startswith("/ops/"):             # a área do cliente é o SPA, servido fora do teste
                continue
            r = cli.get(destino, follow_redirects=False)
            if r.status_code in (301, 302, 303):        # no máximo um salto a mais
                r = cli.get(r.headers["location"], follow_redirects=False)
            if r.status_code != 200:
                quebrados.append((antigo, destino, r.status_code))
        elif r.status_code != 200:
            quebrados.append((antigo, "-", r.status_code))
    assert not quebrados, quebrados


@pytest.mark.parametrize("antigo, novo", [
    ("/birthday-party/", "/services/birthday-party/"),                      # menu do urace.us de hoje
    ("/group-events-social-gatherings/", "/services/group-events/"),
    ("/product-category/karts-parts/chassis/", "/store/chassis/"),          # subcategoria do WooCommerce
    ("/product-category/karts-parts/chassis/tony-kart-otk/brakes/", "/store/"),
    ("/product-category/apparel-gear/apparel/suits/", "/store/custom-kart-suits/"),
    ("/product-category/used/", "/store/"),
    ("/product-tag/jecko/", "/store/"),
    ("/product/kart-que-saiu-do-catalogo/", "/store/"),                     # produto fora do catálogo
    ("/store/page/9/", "/store/"),                                          # #261: página que não existe
    ("/store/page/1/", "/store/"),                                          # #261: a página 1 é a própria loja
    ("/blog/page/2/", "/blog/"),                                            # o blog não pagina: vai para a primeira
    # #261: a loja pagina de verdade, então a página 2 do WooCommerce leva à página 2 da loja
    ("/shop/page/2/", "/store/page/2/"),
    ("/product-category/karts-parts/page/2/", "/store/parts/page/2/"),
    ("/my-account/lost-password/", "/ops/portal"),
    ("/sitemap_index.xml", "/sitemap.xml"),
    ("/product-sitemap.xml", "/sitemap.xml"),
])
def test_familia_de_endereco_do_wordpress_redireciona(cli, antigo, novo):
    r = cli.get(antigo, follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == novo


def test_pagina_do_produto_sem_codigo_do_tema_no_texto(cli):
    """#252: a descrição vinda do WooCommerce traz CSS e JavaScript do tema soltos (no urace.us eles
    ficam dentro de <style>/<script>). Como texto, viravam lixo na página do produto e estouravam a
    largura no celular. Nenhuma página do site mostra código."""
    sujas = []
    for p in paginas_site.dados("produtos.json")["produtos"]:
        texto = _texto_visivel(cli.get(f"/store/p/{p['slug']}/").text)
        if paginas_site.CODIGO.search(texto):
            sujas.append(p["slug"])
    assert not sujas, sujas


def _texto_visivel(html):
    corpo = html.split("<main", 1)[1]
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", corpo))


def test_meta_description_do_produto_nao_corta_palavra(cli):
    """#252: antes o resumo era cortado seco em 120 caracteres e o Google mostrava "add it w.".
    Agora o corte é no fim de frase ou de palavra, e a nota de rodapé de preço não vira o resumo."""
    for p in paginas_site.dados("produtos.json")["produtos"]:
        html = cli.get(f"/store/p/{p['slug']}/").text
        desc = re.search(r'<meta name="description" content="(.*?)">', html).group(1)
        assert 80 <= len(desc) <= 175, (p["slug"], len(desc), desc)
        assert not desc.startswith("*"), (p["slug"], desc)
        assert desc.endswith((".", "!", "?", "…")), (p["slug"], desc)
        if desc.endswith("…"):                          # cortou: a última palavra está inteira
            assert len(desc.rstrip("…").split()[-1]) > 2, (p["slug"], desc)
    desc = re.search(r'<meta name="description" content="(.*?)">',
                     cli.get("/store/p/arrive-and-drive/").text).group(1)
    assert desc.startswith("Arrive and Drive is designed for all ages")


def test_pagina_do_404_fica_fora_do_google_e_tem_saida(cli, monkeypatch):
    """#252: a página do 404 não é para o Google, e não termina em beco sem saída."""
    monkeypatch.setenv("CC_SITE_PREVIEW", "0")
    r = cli.get("/nao-existe-mesmo/")
    assert r.status_code == 404
    assert 'name="robots" content="noindex, nofollow"' in r.text
    for destino in ("/services/arrive-and-drive/", "/store/", "/services/", "/contact/"):
        assert f'href="{destino}"' in r.text
    assert "new site" not in r.text, "depois da troca não existe mais um 'site novo'"


def test_schema_do_negocio_nao_perde_o_seo_local_do_urace_us(cli):
    """#252: o LocalBusiness do urace.us de hoje (Yoast) tem mapa, coordenadas, faixa de preço,
    cidades atendidas e os perfis de Yelp, TripAdvisor e Google Maps. A troca de domínio não pode
    perder nada disso, e a home ainda diz quem é a URACE (Organization) e qual é o site (WebSite)."""
    p = _le(cli.get("/").text)
    negocio = next(x for x in p.ld if "LocalBusiness" in str(x.get("@type")))
    assert negocio["geo"]["latitude"] and negocio["geo"]["longitude"]
    assert negocio["hasMap"].startswith("https://www.google.com/maps/")
    assert negocio["priceRange"] and negocio["currenciesAccepted"] == "USD"
    assert [c["name"] for c in negocio["areaServed"]] == ["Orlando", "Kissimmee", "Winter Garden", "Florida"]
    assert any("yelp.com" in u for u in negocio["sameAs"]) and any("tripadvisor." in u for u in negocio["sameAs"])
    assert negocio["address"]["streetAddress"].endswith("Box 3")
    tipos = {str(x.get("@type")) for x in p.ld}
    assert "Organization" in tipos and "WebSite" in tipos
    # e em toda página o negócio continua completo (é o schema que o Google lê em qualquer entrada)
    for c in ("/services/arrive-and-drive/", "/store/", "/contact/"):
        n = next(x for x in _le(cli.get(c).text).ld if "LocalBusiness" in str(x.get("@type")))
        assert n["geo"] and n["hasMap"] and n["areaServed"], c


# ------------------------------------------------- loja: busca, filtro, ordem e página (#261)
def _nomes_na_grade(html):
    """Os produtos que a página da loja mostra, na ordem em que aparecem."""
    return [re.sub(r"<[^>]+>", "", n) for n in re.findall(r'<span class="produto-txt"><strong>(.*?)</strong>', html)]


def test_busca_da_loja_e_do_servidor_e_funciona_sem_javascript(cli):
    """#261 (dono, 15/10: *"Busca e filtro na loja… Eu faço — confirma?"* → *"sim"*): a loja acha
    produto por texto, e quem acha é o servidor — a página já chega com o resultado. O formulário é
    um `form method="get"` de verdade, então sem JavaScript continua funcionando."""
    r = cli.get("/store/")
    assert '<form class="loja-busca" method="get" action="/store/" role="search">' in r.text
    for campo in ('name="s"', 'name="min_price"', 'name="max_price"', 'name="orderby"'):
        assert campo in r.text, campo
    # nenhum script da loja: a página é montada no servidor (o carrinho.js é o de todo o site)
    assert re.findall(r'<script src="/_s/([a-z]+\.js)', r.text) == ["carrinho.js"]
    # o código do produto (SKU) acha um só, e o nome acha o produto certo em primeiro lugar
    assert _nomes_na_grade(cli.get("/store/?s=MXCKIT").text) == ["OTK Magnesium Wheels Set MXC - 130mm, 210mm"]
    assert _nomes_na_grade(cli.get("/store/?s=mxc").text)[0] == "OTK Magnesium Wheels Set MXC - 130mm, 210mm"
    # busca dentro da categoria também
    assert all("wheel" in n.lower() or "magnesium" in n.lower()
               for n in _nomes_na_grade(cli.get("/store/parts/?s=magnesium+wheel+set").text))
    # nada encontrado: a página não é um beco sem saída
    vazio = cli.get("/store/?s=zzzznaoexistenada")
    assert vazio.status_code == 200 and not _nomes_na_grade(vazio.text)
    assert "Nothing matched that" in vazio.text and 'href="/store/"' in vazio.text
    # página de resultado fica fora do Google e aponta o canônico para a loja
    assert 'name="robots" content="noindex, nofollow"' in vazio.text
    assert f'<link rel="canonical" href="{SITE}/store/">' in vazio.text


def test_filtro_de_preco_e_ordenacao_da_loja(cli):
    """#261: o filtro de preço (`min_price`/`max_price`) e a ordenação são resolvidos no servidor,
    com os mesmos nomes que o urace.us publica hoje."""
    faixa = paginas_site.catalogo(min_price=800, max_price=900, limit=50)
    assert faixa["total"] and all(paginas_site._faixa(p)[1] >= 800 and paginas_site._faixa(p)[0] <= 900
                                  for p in faixa["produtos"])
    assert faixa["total"] < paginas_site.catalogo(limit=1)["total"], "o filtro tira produto"
    nomes = _nomes_na_grade(cli.get("/store/?min_price=800&max_price=900").text)
    assert nomes and len(nomes) == faixa["total"]
    assert "OTK Magnesium Wheels Set MXC - 130mm, 210mm" in nomes, "$838.95 está entre 800 e 900"
    baratos = [paginas_site._faixa(p)[0] for p in paginas_site.catalogo(orderby="price", limit=50)["produtos"]]
    assert baratos == sorted(baratos)
    caros = [paginas_site._faixa(p)[1] for p in paginas_site.catalogo(orderby="price-desc", limit=50)["produtos"]]
    assert caros == sorted(caros, reverse=True)
    # o formulário volta marcado com o que a pessoa pediu (sem JavaScript, é o HTML que lembra)
    html = cli.get("/store/?min_price=800&max_price=900&orderby=price-desc").text
    assert 'name="min_price" value="800"' in html and 'name="max_price" value="900"' in html
    assert '<option value="price-desc" selected>' in html


def test_loja_paginada_no_backend(cli, monkeypatch):
    """#261: lista que cresce é paginada no backend (`limit`/`offset` + `total`, como manda o
    CLAUDE.md), e a página vem no caminho (`/store/page/2/`), não num parâmetro."""
    tudo = paginas_site.dados("produtos.json")["produtos"]
    c = paginas_site.catalogo(limit=24, offset=24)
    assert c["total"] == len(tudo) and c["limit"] == 24 and c["offset"] == 24 and len(c["produtos"]) <= 24
    assert c["paginas"] == -(-len(tudo) // 24)
    r = cli.get("/store/")
    assert f"of {len(tudo)} products" in r.text, "a página diz o total que veio do servidor"
    assert '<a class="chip-link" rel="next" href="/store/page/2/">Next</a>' in r.text
    vistos = []
    for caminho in ["/store/"] + [f"/store/page/{n}/" for n in range(2, c["paginas"] + 1)]:
        pg = cli.get(caminho)
        assert pg.status_code == 200, caminho
        vistos += _nomes_na_grade(pg.text)
    assert len(vistos) == len(tudo) and len(set(vistos)) == len(set(p["name"] for p in tudo))
    # a página 2 é indexável, com canônico próprio e título diferente da primeira
    monkeypatch.setenv("CC_SITE_PREVIEW", "0")
    p2 = cli.get("/store/page/2/")
    assert f'<link rel="canonical" href="{SITE}/store/page/2/">' in p2.text
    assert 'name="robots"' not in p2.text, "a página 2 entra no Google (é por ela que ele acha o resto)"
    assert "Page 2" in p2.text.split("</title>")[0]
    assert 'name="robots" content="noindex, nofollow"' in cli.get("/store/?s=wheels").text
    # e entra no sitemap, senão o Google não chega nos produtos depois da primeira página
    assert "/store/page/2/" in paginas_site.caminhos()
    # página que não existe não é 404: volta para a loja
    assert cli.get("/store/page/7/", follow_redirects=False).headers["location"] == "/store/"


@pytest.mark.parametrize("antigo, esperado", [
    ("/store/?s=wheels", 200),
    ("/store/?min_price=100&max_price=900", 200),
    ("/store/?orderby=price", 200),
    ("/store/?orderby=popularity", 200),           # o Woo ordena por venda; a cópia não traz venda
    ("/store/?orderby=rating", 200),
    ("/store/page/2/", 200),
    ("/store/parts/?s=wheel&orderby=price-desc", 200),
    ("/shop/?s=wheels", 301),
    ("/shop/page/2/", 301),
    ("/?s=mxc", 301),                              # a busca do WordPress (`/?s=`) é a busca da loja
    ("/product-category/engines/?orderby=price", 301),
])
def test_endereco_da_loja_do_urace_us_de_hoje_continua_abrindo(cli, antigo, esperado):
    """#261: `?s=`, `min_price`, `max_price`, a ordenação do Woo e `page/N` são endereços que o
    urace.us publica hoje. Todos continuam abrindo, e o 301 leva a busca e o filtro com ele."""
    r = cli.get(antigo, follow_redirects=False)
    assert r.status_code == esperado, (antigo, r.status_code)
    if esperado == 301:
        destino = r.headers["location"]
        if "?" in antigo:
            assert antigo.split("?", 1)[1] in destino or "s=mxc" in destino, destino
        r = cli.get(destino, follow_redirects=False)
        assert r.status_code == 200, (destino, r.status_code)


MXC = "otk-magnesium-wheels-set-mxc-130mm-210mm"


def test_jogo_de_rodas_otk_mxc_entrou_no_catalogo(cli):
    """#261 (dono, 15/10: *"o jogo de rodas OTK MXC está no sitemap de hoje e não está no catálogo
    novo. Entra?"* → *"sim"*): o produto abre, aparece na busca, cai na categoria certa, entra no
    sitemap e o endereço do urace.us de hoje leva até ele. Nome, preço, descrição e foto vieram da
    página que o urace.us publica (lida em 15/10): $838.95, SKU MXCKIT."""
    p = next(x for x in paginas_site.dados("produtos.json")["produtos"] if x["slug"] == MXC)
    assert (p["name"], p["price"], p["sku"], p["in_stock"]) == (
        "OTK Magnesium Wheels Set MXC - 130mm, 210mm", 838.95, "MXCKIT", True)
    r = cli.get(f"/store/p/{MXC}/")
    assert r.status_code == 200 and "$838.95" in r.text
    oferta = [x for x in _le(r.text).ld if x.get("@type") == "Product"][0]["offers"]
    assert oferta["price"] == "838.95" and oferta["availability"].endswith("InStock")
    # a foto é nossa, em WebP comprimido
    assert p["images"][0]["src"].endswith(".webp")
    assert os.path.exists(os.path.join(os.path.dirname(conteudo.__file__), "static", "img", p["images"][0]["src"]))
    # a descrição não traz CSS/JS do tema e não corta no meio da palavra
    texto = _texto_visivel(r.text)
    assert not paginas_site.CODIGO.search(texto)
    assert "Includes Beadlocks and Valve Stems" in texto
    desc = re.search(r'<meta name="description" content="(.*?)">', r.text).group(1)
    assert 80 <= len(desc) <= 175 and desc.endswith((".", "!", "?", "…"))
    # busca, categoria e sitemap
    assert MXC in cli.get("/store/?s=MXCKIT").text
    assert paginas_site._categoria(p)["slug"] == "parts", "a página do urace.us não dá categoria: cai em Parts"
    assert MXC in cli.get("/store/parts/?s=mxc").text
    assert f"/store/p/{MXC}/" in paginas_site.caminhos()
    assert cli.get(f"/product/{MXC}/", follow_redirects=False).headers["location"] == f"/store/p/{MXC}/"

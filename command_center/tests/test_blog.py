"""#172 (dono, 16/10: *"editor do blog, pode seguir"*): Site › Blog no painel.

Pedido na issue: artigos em rascunho ou publicados; título, categoria, resumo, capa (WebP ≤ 1600 px, sem EXIF) e texto
com títulos, listas, links e imagens, com prévia no visual do site; os artigos passam para o banco **sem mudar o
endereço** `/blog/<slug>/`; publicar e despublicar mudam na hora o sitemap e o JSON-LD; o OPERATOR escreve e só o
ADMIN (ou a conta de acesso livre) publica; tudo na auditoria.

O que estes testes trancam:
- os 7 artigos do WordPress entram no banco uma vez, com o HTML como está, e cada página sai **igual** à do arquivo;
- a tabela do post 451 continua inteira (na importação e no salvar do editor); a loja continua sem tabela;
- rascunho dá 404 e fica fora do blog e do sitemap; publicar põe na lista, na categoria, no sitemap e no JSON-LD
  (com `dateModified`); despublicar dá 404 (e um dos 7 só sai com confirmação: o Google tem o endereço);
- OPERATOR publicando recebe 403; ADMIN e acesso livre publicam;
- `<script>`, `onerror` e `javascript:` somem; o endereço trava na primeira publicação; endereços reservados;
- a capa sai WebP sem EXIF, com o tamanho de verdade; versões e voltar; a lista é paginada com o total;
- sem banco, o site volta ao arquivo.

Revisão do PR #322 (cada teste falha sem a correção):
- publicar só põe no ar o rascunho que o administrador viu (`visto`); mudou depois → 409, nada vai ao ar;
- o Enter do Chrome e o texto colado (`<div>`) viram parágrafos, não texto grudado;
- os 7 do WordPress guardam a versão original (e o banco que importou sem ela ganha uma, uma vez só);
- texto patológico limpa em tempo linear, e muito acima do limite dá 400; `href="/"` fica; `/\\` não passa;
- id, offset e meia letra de UTF-16 absurdos dão 4xx, nunca 500; a home sem artigo no ar não desenha a faixa do blog;
- foto com pixels demais (100 MP de cor lisa, poucos KB) dá 400 antes de decodificar.
"""
import io
import json
import re
import sqlite3
import struct
import time
import xml.etree.ElementTree as ET
import zlib

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from command_center.api import auth
from command_center.api.main import app
from command_center.db import aplicar_schema, conectar, todos, um
from command_center.providers import blog, imagem
from command_center.vitrine import conteudo, html_seguro, paginas_site

SENHA = "pista-molhada-7"
B = "/ops/api/site/blog"
ARQUIVO = paginas_site.dados("posts.json")["posts"]
P451 = next(p for p in ARQUIVO if p["id"] == 451)
OP, GER, ADM, LIVRE = "op@example.com", "ger@example.com", "adm@example.com", "livre@example.com"
DESC = "How to read the racing line of a kart track in Orlando: braking point, apex and exit, explained by a coach."
TEXTO = "<h2>The line</h2><p>Brake in a straight line, turn in late and look at the exit of the corner.</p>"


@pytest.fixture()
def amb(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    monkeypatch.delenv("CC_SITE_HOSTS", raising=False)
    monkeypatch.delenv("CC_SITE_PREVIEW", raising=False)
    monkeypatch.setattr(auth, "ACESSO_LIVRE", (LIVRE,))       # a conta de acesso livre do teste (fictícia)
    con = conectar()
    aplicar_schema(con)
    for email, nome, papel in ((OP, "Operador", "OPERATOR"), (GER, "Gerente", "MANAGER"), (ADM, "Admin", "ADMIN"),
                               (LIVRE, "Livre", "OPERATOR")):
        auth.criar_usuario(con, email, nome, papel, SENHA)
    with TestClient(app, base_url="https://cc.test") as painel, TestClient(app, base_url="https://novo.urace.us") as site:
        yield painel, site, con
    con.close()


def _entra(t, email):
    t.cookies.clear()
    assert t.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": t.cookies.get("cc_csrf")}


def _novo(painel, h, titulo="How to Read a Kart Track", categoria="training-racing", **kw):
    r = painel.post(B, headers=h, json={"title": titulo, "category": categoria, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _pronto(painel, h, pid, **kw):
    r = painel.patch(f"{B}/{pid}", headers=h, json={"description": DESC, "excerpt": "Braking point, apex and exit.",
                                                    "html": TEXTO, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _visto(painel, h, pid):
    """O que a tela do artigo tem na mão ao clicar Publicar: o `updated_at` do rascunho que ela abriu."""
    return painel.get(f"{B}/{pid}", headers=h).json()["post"]["updated_at"]


def _publica(painel, pid, email=ADM):
    h = _entra(painel, email)
    return painel.post(f"{B}/{pid}/publicar", headers=h, json={"visto": _visto(painel, h, pid)})


def _ld(html, tipo):
    blocos = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
    return [b for b in blocos if b.get("@type") == tipo]


def _locs(site):
    return {u.text for u in ET.fromstring(site.get("/sitemap.xml").content).iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")}


def _foto_com_exif(largura=2400, altura=1200):
    im = Image.new("RGB", (largura, altura), (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "CameraMaker"
    exif[0x8825] = {1: "N", 2: (28.0, 25.0, 0.0)}             # GPS: a posição de onde a foto foi tirada
    b = io.BytesIO()
    im.save(b, "JPEG", exif=exif.tobytes())
    assert b"Exif" in b.getvalue()[:200]
    return b.getvalue()


# ------------------------------------------------------------------ a importação dos 7
def test_os_7_do_wordpress_entram_uma_vez_com_o_html_como_esta(amb):
    painel, site, con = amb
    rs = todos(con, "SELECT * FROM blog_posts ORDER BY id")
    assert sorted(r["id"] for r in rs) == sorted(p["id"] for p in ARQUIVO) and len(rs) == 7
    for r in rs:
        p = next(x for x in ARQUIVO if x["id"] == r["id"])
        d = json.loads(r["draft"])
        assert r["published"] == r["draft"] and r["origin"] == "wordpress" and r["slug"] == p["slug"]
        assert r["first_published_at"] == p["date"] and d["html"] == p["html"] and d["title"] == p["title"]
        assert d["image_w"] and d["image_h"], "a capa leva o tamanho de verdade"
    # o que a equipe muda nunca volta na subida seguinte, e nada entra duas vezes
    con.execute("UPDATE blog_posts SET published=NULL WHERE id=451")
    aplicar_schema(con)
    aplicar_schema(con)
    assert um(con, "SELECT COUNT(*) AS n FROM blog_posts")["n"] == 7
    assert um(con, "SELECT published FROM blog_posts WHERE id=451")["published"] is None


def test_cada_pagina_do_blog_com_o_banco_sai_igual_a_do_arquivo(amb, monkeypatch):
    """O endereço e o HTML não mudam no dia da troca: cada um dos 7, o /blog/, as categorias, a home e o sitemap."""
    painel, site, con = amb
    # a página lê mesmo o banco (senão a comparação abaixo não provaria nada): o publicado muda, a página muda
    antes = um(con, "SELECT published FROM blog_posts WHERE id=444")["published"]
    con.execute("UPDATE blog_posts SET published=? WHERE id=444", (antes.replace(ARQUIVO[-1]["title"], "Lido do banco"),))
    assert "<h1>Lido do banco</h1>" in site.get(f"/blog/{ARQUIVO[-1]['slug']}/").text
    con.execute("UPDATE blog_posts SET published=? WHERE id=444", (antes,))
    caminhos = [f"/blog/{p['slug']}/" for p in ARQUIVO] + ["/blog/", "/"] + \
        [f"/blog/category/{c['slug']}/" for c in blog.categorias()] + ["/sitemap.xml"]
    com_banco = {c: site.get(c) for c in caminhos}
    assert all(r.status_code == 200 for r in com_banco.values())
    monkeypatch.setattr(blog, "publicados", lambda con: None)   # o mesmo caminho da página, lendo o arquivo
    for c in caminhos:
        assert site.get(c).text == com_banco[c].text, c


# ------------------------------------------------------------------ a tabela do post 451
def test_a_tabela_do_post_451_continua_inteira_e_a_loja_continua_igual(amb):
    painel, site, con = amb
    tabela = re.search(r"<figure><table>.*?</table></figure>", P451["html"], re.S).group(0)
    assert tabela in site.get(f"/blog/{P451['slug']}/").text, "importado sem limpar: a tabela sai inteira"
    # o editor do painel manda o texto de volta: a tabela passa pela limpeza do blog sem perder nada
    h = _entra(painel, OP)
    r = painel.patch(f"{B}/451", headers=h, json={"html": P451["html"]})
    assert r.status_code == 200, r.text
    salvo = r.json()["post"]["draft"]["html"]
    assert "<figure><table><thead><tr><th>Category</th><th>Age</th><th>Per day</th></tr></thead><tbody>" in salvo
    assert salvo.count("<td>") == 15 and salvo.count("<tr>") == 6 and "</tbody></table></figure>" in salvo
    assert "<table>" not in html_seguro.limpar(P451["html"]), "a loja e o editor do site continuam sem tabela"
    assert html_seguro.limpar('<table onclick="x()"><tr><td style="color:red">1</td></tr></table>', extra=html_seguro.BLOG) \
        == "<table><tr><td>1</td></tr></table>", "a tabela passa sem atributo"


# ------------------------------------------------------------------ rascunho, publicar, despublicar
def test_rascunho_da_404_fica_fora_do_blog_e_do_sitemap_e_tem_previa(amb):
    painel, site, con = amb
    h = _entra(painel, OP)
    p = _novo(painel, h)["post"]
    _pronto(painel, h, p["id"])
    url = f"/blog/{p['slug']}/"
    assert p["slug"] == "how-to-read-a-kart-track" and p["estado"] == "rascunho"
    assert site.get(url).status_code == 404
    assert url not in site.get("/blog/").text and url not in site.get("/blog/category/training-racing/").text
    assert f"https://novo.urace.us{url}" not in _locs(site)
    prev = painel.get(f"{B}/{p['id']}/previa", headers=h)
    assert prev.status_code == 200 and "<h1>How to Read a Kart Track</h1>" in prev.text
    assert 'content="noindex, nofollow"' in prev.text and "frame-ancestors 'self'" in prev.headers["content-security-policy"]
    assert "public" not in prev.headers["cache-control"], "a prévia não fica em cache"


def test_publicar_poe_na_lista_na_categoria_no_sitemap_e_no_json_ld(amb):
    painel, site, con = amb
    h = _entra(painel, OP)
    pid = _novo(painel, h)["id"]
    _pronto(painel, h, pid)
    r = _publica(painel, pid)
    assert r.status_code == 200, r.text
    assert r.json()["post"]["estado"] == "no_ar"
    url = "/blog/how-to-read-a-kart-track/"
    pg = site.get(url)
    assert pg.status_code == 200 and pg.headers["cache-control"] == "public, max-age=300"
    assert "<h1>How to Read a Kart Track</h1>" in pg.text and "<h2>The line</h2>" in pg.text
    ld = _ld(pg.text, "BlogPosting")[0]
    assert ld["datePublished"] == ld["dateModified"] == blog.hoje() and ld["description"] == DESC
    lista = site.get("/blog/").text
    assert lista.index(f'href="{url}"') < lista.index(f'href="/blog/{ARQUIVO[0]["slug"]}/"'), "o mais novo primeiro"
    assert f"https://novo.urace.us{url}" in [x["url"] for x in _ld(lista, "Blog")[0]["blogPost"]]
    assert f'href="{url}"' in site.get("/blog/category/training-racing/").text
    assert f'href="{url}"' not in site.get("/blog/category/racing-gear/").text
    assert f"https://novo.urace.us{url}" in _locs(site)
    # um dos 7, mudado e publicado de novo: a data de publicação fica a do WordPress, a da mudança é a de hoje
    assert painel.patch(f"{B}/451", headers=_entra(painel, OP), json={"title": "Getting Started in Kart Racing (2027 edition)"}).status_code == 200
    assert painel.get(f"{B}/451", headers=h).json()["post"]["estado"] == "mudou"
    assert "(2027 edition)" not in site.get(f"/blog/{P451['slug']}/").text, "o site não vê o rascunho"
    assert _publica(painel, 451).status_code == 200
    ld = _ld(site.get(f"/blog/{P451['slug']}/").text, "BlogPosting")[0]
    assert ld["headline"].endswith("(2027 edition)") and ld["datePublished"] == "2024-12-26" and ld["dateModified"] == blog.hoje()


def test_despublicar_da_404_e_um_dos_7_pede_confirmacao(amb):
    painel, site, con = amb
    h = _entra(painel, OP)
    pid = _novo(painel, h)["id"]
    _pronto(painel, h, pid)
    assert _publica(painel, pid).status_code == 200
    adm = _entra(painel, ADM)
    assert painel.post(f"{B}/{pid}/despublicar", headers=adm).status_code == 200, "artigo novo: sem pergunta"
    assert painel.post(f"{B}/{pid}/despublicar", headers=adm).status_code == 400, "já está fora do ar"
    assert site.get("/blog/how-to-read-a-kart-track/").status_code == 404
    assert "https://novo.urace.us/blog/how-to-read-a-kart-track/" not in _locs(site)
    # o 451 está no Google: sem confirmar, não sai do ar
    r = painel.post(f"{B}/451/despublicar", headers=adm)
    assert r.status_code == 409 and "Google" in r.json()["detail"]
    assert site.get(f"/blog/{P451['slug']}/").status_code == 200
    r = painel.post(f"{B}/451/despublicar", headers=adm, json={"confirmar": True})
    assert r.status_code == 200 and r.json()["post"]["estado"] == "rascunho"
    assert site.get(f"/blog/{P451['slug']}/").status_code == 404
    # o 451 era o único de Getting Started: a categoria sai do sitemap e do menu de categorias, o endereço fica
    locs = _locs(site)
    assert f"https://novo.urace.us/blog/{P451['slug']}/" not in locs
    assert "https://novo.urace.us/blog/category/getting-started/" not in locs
    assert 'href="/blog/category/getting-started/"' not in site.get("/blog/").text
    cat = site.get("/blog/category/getting-started/")
    assert cat.status_code == 200 and "No articles here yet" in cat.text


def test_so_o_admin_ou_o_acesso_livre_publica_e_despublica(amb):
    painel, site, con = amb
    h = _entra(painel, OP)
    pid = _novo(painel, h)["id"]
    _pronto(painel, h, pid)
    for email in (OP, GER):
        assert _publica(painel, pid, email).status_code == 403, email
        assert painel.post(f"{B}/451/despublicar", headers=_entra(painel, email), json={"confirmar": True}).status_code == 403
    assert site.get("/blog/how-to-read-a-kart-track/").status_code == 404
    assert _publica(painel, pid, ADM).status_code == 200
    assert painel.post(f"{B}/{pid}/despublicar", headers=_entra(painel, LIVRE)).status_code == 200, "acesso livre passa"
    assert _publica(painel, pid, LIVRE).status_code == 200
    # o leitor não entra no blog do painel
    auth.criar_usuario(con, "leitor@example.com", "Leitor", "VIEWER", SENHA)
    assert painel.get(B, headers=_entra(painel, "leitor@example.com")).status_code == 403


def test_publicar_confere_o_que_falta(amb):
    painel, site, con = amb
    h = _entra(painel, OP)
    pid = _novo(painel, h)["id"]
    r = _publica(painel, pid)
    assert r.status_code == 400 and "descrição para o Google" in r.json()["detail"] and "texto do artigo" in r.json()["detail"]
    h = _entra(painel, OP)
    assert painel.patch(f"{B}/{pid}", headers=h, json={"description": "x" * 156}).status_code == 400
    assert painel.patch(f"{B}/{pid}", headers=h, json={"title": "ab"}).status_code == 400
    assert painel.patch(f"{B}/{pid}", headers=h, json={"category": "uncategorized"}).status_code == 400


# ------------------------------------------------------------------ texto seguro e endereço
def test_script_onerror_e_javascript_somem_do_texto(amb):
    painel, site, con = amb
    h = _entra(painel, OP)
    pid = _novo(painel, h, titulo="<script>alert(1)</script> Kart tips")["id"]
    sujo = ('<p onclick="x()">Hi <b>there</b><script>alert(1)</script></p><img src="/_f/0123456789abcdef.webp" onerror="alert(2)">'
            '<a href="javascript:alert(3)">click</a><table><tr><td onmouseover="alert(4)">1</td></tr></table>'
            '<p>Long enough text for the article body.</p>')
    salvo = _pronto(painel, h, pid, html=sujo)["post"]["draft"]["html"]
    for ruim in ("script", "onerror", "onclick", "onmouseover", "javascript:", "alert("):
        assert ruim not in salvo, ruim
    assert '<img src="/_f/0123456789abcdef.webp" alt="" loading="lazy">' in salvo and "<table><tr><td>1</td></tr></table>" in salvo
    assert _publica(painel, pid).status_code == 200
    slug = um(con, "SELECT slug FROM blog_posts WHERE id=?", (pid,))["slug"]
    pg = site.get(f"/blog/{slug}/").text
    assert "<h1>&lt;script&gt;alert(1)&lt;/script&gt; Kart tips</h1>" in pg, "título é texto, nunca HTML"
    assert "<script>alert(1)</script>" not in pg, "nem no JSON-LD (lá o </ vira <\\/)"
    assert _ld(pg, "BlogPosting")[0]["headline"] == "<script>alert(1)</script> Kart tips"


def test_o_endereco_trava_na_primeira_publicacao(amb):
    painel, site, con = amb
    h = _entra(painel, OP)
    pid = _novo(painel, h)["id"]
    _pronto(painel, h, pid)
    for ruim in ("category", "page", "img", "Com Espaço", "a/b", P451["slug"]):
        assert painel.patch(f"{B}/{pid}", headers=h, json={"slug": ruim}).status_code == 400, ruim
    r = painel.patch(f"{B}/{pid}", headers=h, json={"slug": "reading-a-kart-track"})
    assert r.status_code == 200 and r.json()["post"]["endereco"] == "/blog/reading-a-kart-track/"
    assert _novo(painel, h)["post"]["slug"] == "how-to-read-a-kart-track", "o endereço que vagou pode ser de outro"
    assert _novo(painel, h)["post"]["slug"] == "how-to-read-a-kart-track-2", "repetido ganha -2"
    assert _publica(painel, pid).status_code == 200
    h = _entra(painel, OP)
    r = painel.patch(f"{B}/{pid}", headers=h, json={"slug": "outro-endereco"})
    assert r.status_code == 400 and "não muda depois de publicado" in r.json()["detail"]
    painel.post(f"{B}/{pid}/despublicar", headers=_entra(painel, ADM))
    assert painel.patch(f"{B}/{pid}", headers=_entra(painel, OP), json={"slug": "outro-endereco"}).status_code == 400, \
        "despublicar não destrava: o Google guardou o endereço"
    assert painel.patch(f"{B}/451", headers=_entra(painel, OP), json={"slug": "novo-endereco"}).status_code == 400


# ------------------------------------------------------------------ capa e fotos
def test_capa_sai_webp_sem_exif_com_o_tamanho_de_verdade(amb):
    painel, site, con = amb
    h = _entra(painel, OP)
    pid = _novo(painel, h)["id"]
    _pronto(painel, h, pid)
    r = painel.post(f"{B}/{pid}/capa", headers=h, files={"arquivo": ("pista.jpg", _foto_com_exif(), "image/jpeg")})
    assert r.status_code == 200, r.text
    d = r.json()["post"]["draft"]
    assert re.fullmatch(r"/_f/[0-9a-f]{16}\.webp", d["image"]) and (d["image_w"], d["image_h"]) == (1600, 800)
    foto = site.get(d["image"])
    assert foto.headers["content-type"] == "image/webp" and b"Exif" not in foto.content and b"CameraMaker" not in foto.content
    assert Image.open(io.BytesIO(foto.content)).size == (1600, 800)
    r = _publica(painel, pid)
    assert r.status_code == 400 and "descrição da capa" in r.json()["detail"], "foto subida precisa de descrição"
    assert painel.patch(f"{B}/{pid}", headers=_entra(painel, OP), json={"image_alt": "A red kart at the apex"}).status_code == 200
    assert _publica(painel, pid).status_code == 200
    pg = site.get("/blog/how-to-read-a-kart-track/").text
    assert f'<img class="post-capa" src="{d["image"]}" alt="A red kart at the apex" width="1600" height="800">' in pg
    assert _ld(pg, "BlogPosting")[0]["image"] == f"https://novo.urace.us{d['image']}"
    assert f'<img src="{d["image"]}" alt="" width="1600" height="800" loading="lazy">' in site.get("/blog/").text
    # a foto do meio do texto: o mesmo WebP, devolvido para o editor pôr no lugar do cursor
    h = _entra(painel, OP)
    r = painel.post(f"{B}/{pid}/imagens", headers=h, files={"arquivo": ("x.jpg", _foto_com_exif(800, 600), "image/jpeg")})
    assert r.status_code == 201 and r.json()["largura"] == 800 and r.json()["src"].startswith("/_f/")
    assert painel.post(f"{B}/{pid}/capa", headers=h, files={"arquivo": ("x.txt", b"nao e foto", "text/plain")}).status_code == 400


# ------------------------------------------------------------------ versões, lista e auditoria
def test_versoes_e_voltar_trazem_a_antiga_para_o_rascunho(amb):
    painel, site, con = amb
    h = _entra(painel, OP)
    pid = _novo(painel, h)["id"]
    _pronto(painel, h, pid)
    assert _publica(painel, pid).status_code == 200
    h = _entra(painel, OP)
    painel.patch(f"{B}/{pid}", headers=h, json={"title": "How to Read a Kart Track, Second Take"})
    assert _publica(painel, pid).status_code == 200
    h = _entra(painel, OP)
    vs = painel.get(f"{B}/{pid}/versoes", headers=h).json()["versoes"]
    assert [v["title"] for v in vs] == ["How to Read a Kart Track, Second Take", "How to Read a Kart Track"]
    assert vs[0]["por"] == "Admin"
    r = painel.post(f"{B}/{pid}/versoes/{vs[1]['id']}/voltar", headers=h)
    assert r.status_code == 200 and r.json()["post"]["draft"]["title"] == "How to Read a Kart Track"
    assert r.json()["post"]["estado"] == "mudou"
    assert "Second Take" in site.get("/blog/how-to-read-a-kart-track/").text, "o site só muda ao publicar de novo"
    assert painel.post(f"{B}/{pid}/versoes/999999/voltar", headers=h).status_code == 404


def test_lista_paginada_com_total_busca_estado_e_categoria(amb):
    painel, site, con = amb
    h = _entra(painel, OP)
    novo = _novo(painel, h)["post"]
    r = painel.get(f"{B}?limit=3&offset=0", headers=h).json()
    assert r["total"] == 8 and len(r["posts"]) == 3 and r["posts"][0]["id"] == novo["id"], "o rascunho novo em cima"
    assert "html" not in r["posts"][0]["draft"], "a lista não leva o texto dos artigos"
    assert [c["slug"] for c in r["categorias"]] == ["getting-started", "kart-setup", "racing-gear", "training-racing"]
    assert painel.get(f"{B}?limit=3&offset=6", headers=h).json()["posts"][-1]["id"] == 444
    assert [p["id"] for p in painel.get(f"{B}?estado=rascunho", headers=h).json()["posts"]] == [novo["id"]]
    assert painel.get(f"{B}?estado=no_ar", headers=h).json()["total"] == 7
    assert {p["id"] for p in painel.get(f"{B}?categoria=kart-setup", headers=h).json()["posts"]} == {449, 455}
    assert [p["id"] for p in painel.get(f"{B}?q=disney", headers=h).json()["posts"]] == [2216]
    assert painel.get(f"{B}?estado=qualquer", headers=h).status_code == 400
    assert painel.get(f"{B}/999999", headers=h).status_code == 404


def test_a_auditoria_grava_cada_passo(amb):
    painel, site, con = amb
    h = _entra(painel, OP)
    pid = _novo(painel, h)["id"]
    _pronto(painel, h, pid)
    painel.post(f"{B}/{pid}/capa", headers=h, data={"alt": "Kart"}, files={"arquivo": ("p.jpg", _foto_com_exif(400, 300), "image/jpeg")})
    _publica(painel, pid)
    vid = painel.get(f"{B}/{pid}/versoes", headers=_entra(painel, OP)).json()["versoes"][0]["id"]
    painel.post(f"{B}/{pid}/versoes/{vid}/voltar", headers=_entra(painel, OP))
    painel.post(f"{B}/{pid}/despublicar", headers=_entra(painel, ADM))
    ev = todos(con, "SELECT event, user_id, entity_type, detail FROM audit_logs WHERE entity_type='blog_post' AND entity_id=? ORDER BY id",
               (str(pid),))
    assert [e["event"] for e in ev] == ["blog.post.create", "blog.post.update", "blog.post.photo", "blog.post.publish",
                                        "blog.post.restore", "blog.post.unpublish"]
    assert all(e["user_id"] for e in ev)
    assert "Brake in a straight line" not in json.dumps([e["detail"] for e in ev]), "o texto do artigo não vai para a auditoria"


# ------------------------------------------------------------------ sem banco
def test_sem_banco_o_site_volta_ao_arquivo(amb, monkeypatch):
    painel, site, con = amb
    h = _entra(painel, OP)
    pid = _novo(painel, h)["id"]
    _pronto(painel, h, pid)
    assert _publica(painel, pid).status_code == 200
    assert painel.post(f"{B}/451/despublicar", headers=_entra(painel, ADM), json={"confirmar": True}).status_code == 200
    assert site.get(f"/blog/{P451['slug']}/").status_code == 404 and site.get("/blog/how-to-read-a-kart-track/").status_code == 200

    def fora(*a, **k):
        raise sqlite3.OperationalError("banco fora")
    monkeypatch.setattr("command_center.db.conectar", fora)
    assert site.get(f"/blog/{P451['slug']}/").status_code == 200, "o arquivo de antes"
    assert site.get("/blog/how-to-read-a-kart-track/").status_code == 404
    assert site.get("/blog/").text.count('class="post-card"') == len(ARQUIVO)


# ------------------------------------------------------------------ revisão do PR #322
def test_publicar_poe_no_ar_so_o_rascunho_que_o_admin_viu(amb, monkeypatch):
    """O admin abre o artigo e a prévia; o operador salva outro texto; o admin clica Publicar: 409, nada vai ao ar."""
    painel, site, con = amb
    h = _entra(painel, OP)
    pid = _novo(painel, h)["id"]
    _pronto(painel, h, pid)
    adm = _entra(painel, ADM)
    visto = _visto(painel, adm, pid)
    assert painel.post(f"{B}/{pid}/publicar", headers=adm).status_code == 422, "sem `visto` ninguém publica às cegas"
    assert painel.post(f"{B}/{pid}/publicar", headers=adm, json={}).status_code == 422
    h = _entra(painel, OP)
    assert painel.patch(f"{B}/{pid}", headers=h, json={"title": "Totally Different Title",
                                                       "html": "<p>Text the admin never saw.</p>"}).status_code == 200
    adm = _entra(painel, ADM)
    r = painel.post(f"{B}/{pid}/publicar", headers=adm, json={"visto": visto})
    assert r.status_code == 409 and "mudou depois que você abriu" in r.json()["detail"], r.text
    assert um(con, "SELECT published FROM blog_posts WHERE id=?", (pid,))["published"] is None
    assert site.get("/blog/how-to-read-a-kart-track/").status_code == 404
    assert painel.get(f"{B}/{pid}/versoes", headers=adm).json()["versoes"] == []
    # a tela recarrega (visto novo) e o admin publica o que agora viu
    r = painel.post(f"{B}/{pid}/publicar", headers=adm, json={"visto": _visto(painel, adm, pid)})
    assert r.status_code == 200, r.text
    assert "Text the admin never saw." in site.get("/blog/how-to-read-a-kart-track/").text
    # um dos 7 (nunca mudou: `updated_at` nulo) também: o operador mexe depois que o admin abriu → 409
    assert _visto(painel, adm, 451) is None
    assert painel.patch(f"{B}/451", headers=_entra(painel, OP), json={"title": "Getting Started, Changed Later"}).status_code == 200
    assert painel.post(f"{B}/451/publicar", headers=_entra(painel, ADM), json={"visto": None}).status_code == 409
    assert "Changed Later" not in site.get(f"/blog/{P451['slug']}/").text
    # a conferência é a própria escrita: o rascunho que muda entre a leitura e o UPDATE também não vai ao ar
    adm = _entra(painel, ADM)
    pid2 = _novo(painel, _entra(painel, OP), titulo="Second Kart Article")["id"]
    _pronto(painel, _entra(painel, OP), pid2)
    visto = _visto(painel, adm, pid2)
    real = blog.problemas

    def no_meio(c):
        con.execute("UPDATE blog_posts SET draft=? WHERE id=?", (blog._js({**c, "html": "<p>Sneaked in.</p>"}), pid2))
        return real(c)
    monkeypatch.setattr(blog, "problemas", no_meio)
    with pytest.raises(blog.RascunhoMudou):
        blog.publicar(con, 1, pid2, visto)
    assert um(con, "SELECT published FROM blog_posts WHERE id=?", (pid2,))["published"] is None


def test_enter_e_texto_colado_em_div_viram_paragrafos(amb):
    """O Enter do Chrome cria <div>; o texto colado de uma página vem em <div>. Antes a div sumia e grudava tudo."""
    painel, site, con = amb
    h = _entra(painel, OP)
    pid = _novo(painel, h)["id"]
    enter = "<p>First paragraph.</p><div>Second paragraph.</div><div>Third one.</div>"
    r = painel.patch(f"{B}/{pid}", headers=h, json={"html": enter})
    assert r.json()["post"]["draft"]["html"] == "<p>First paragraph.</p><p>Second paragraph.</p><p>Third one.</p>"
    colado = ('<div class="x" style="color:red" onclick="alert(1)">Paragraph one.</div>'
              '<div><div>Nested one.</div><div>Nested two.</div></div><div>Intro<ul><li>item</li></ul></div>')
    salvo = painel.patch(f"{B}/{pid}", headers=h, json={"html": colado}).json()["post"]["draft"]["html"]
    assert salvo == "<p>Paragraph one.</p><p>Nested one.</p><p>Nested two.</p><p>Intro</p><ul><li>item</li></ul>", salvo
    # a loja e o editor do site usam o mesmo editor: o Enter lá também vira parágrafo
    assert html_seguro.limpar("Uma<div>Duas</div>") == "Uma<p>Duas</p>"


def test_a_versao_original_dos_7_fica_guardada_e_volta(amb):
    painel, site, con = amb
    original = P451["html"]
    for p in ARQUIVO:
        vs = todos(con, "SELECT * FROM blog_post_versions WHERE post_id=?", (p["id"],))
        assert len(vs) == 1 and vs[0]["published_by"] is None and vs[0]["published_at"] == p["date"], p["id"]
        assert json.loads(vs[0]["content"])["html"] == p["html"]
    h = _entra(painel, OP)
    assert painel.patch(f"{B}/451", headers=h, json={"html": "<p>New text that replaces the old one.</p>"}).status_code == 200
    assert _publica(painel, 451).status_code == 200
    vs = painel.get(f"{B}/451/versoes", headers=_entra(painel, OP)).json()["versoes"]
    assert len(vs) == 2 and not vs[0]["original"] and vs[0]["por"] == "Admin", "a mais nova em cima"
    assert vs[1]["original"] and vs[1]["por"] is None and vs[1]["published_at"] == P451["date"]
    r = painel.post(f"{B}/451/versoes/{vs[1]['id']}/voltar", headers=_entra(painel, OP))
    assert r.status_code == 200 and r.json()["post"]["draft"]["html"] == original, "o texto do WordPress volta"
    # a subida seguinte não duplica
    aplicar_schema(con)
    assert um(con, "SELECT COUNT(*) AS n FROM blog_post_versions WHERE published_by IS NULL")["n"] == 7
    # o banco que importou antes desta correção (sem a versão original) ganha a que falta, uma vez só
    con.execute("DELETE FROM blog_post_versions WHERE published_by IS NULL")
    aplicar_schema(con)
    aplicar_schema(con)
    assert um(con, "SELECT COUNT(*) AS n FROM blog_post_versions WHERE published_by IS NULL")["n"] == 7
    assert um(con, "SELECT COUNT(*) AS n FROM blog_post_versions WHERE post_id=451")["n"] == 2, "a do painel fica"
    assert json.loads(um(con, "SELECT content FROM blog_post_versions WHERE post_id=451 AND published_by IS NULL")["content"])["html"] == original


def test_texto_patologico_limpa_rapido_e_acima_do_limite_da_400(amb):
    painel, site, con = amb
    n = 40_000                                         # 280 KB: antes, ~20 s (a lista de tags abertas era varrida)
    t = time.monotonic()
    html_seguro.limpar("<b>" * n + "</u>" * n, extra=html_seguro.BLOG)
    assert time.monotonic() - t < 2
    h = _entra(painel, OP)
    pid = _novo(painel, h)["id"]
    n = (2 * blog.HTML_MAX) // 7                       # dentro do que ainda passa pela limpeza
    t = time.monotonic()
    r = painel.patch(f"{B}/{pid}", headers=h, json={"html": "<b>" * n + "</u>" * n})
    assert r.status_code == 400 and "longo demais" in r.json()["detail"] and time.monotonic() - t < 2
    t = time.monotonic()
    r = painel.patch(f"{B}/{pid}", headers=h, json={"html": "<p>" + "x" * (2 * blog.HTML_MAX) + "</p>"})
    assert r.status_code == 400 and "longo demais" in r.json()["detail"] and time.monotonic() - t < 2


def test_link_para_a_home_fica_e_barra_invertida_nao_passa(amb):
    painel, site, con = amb
    h = _entra(painel, OP)
    pid = _novo(painel, h)["id"]
    salvo = painel.patch(f"{B}/{pid}", headers=h, json={"html": '<p>Back to the <a href="/">home page</a>.</p>'}).json()["post"]["draft"]["html"]
    assert salvo == '<p>Back to the <a href="/">home page</a>.</p>'
    # o post 447 do WordPress tem um link para a home: o primeiro salvar no editor não pode tirar
    p447 = next(p for p in ARQUIVO if p["id"] == 447)
    assert 'href="/"' in p447["html"]
    assert 'href="/"' in painel.patch(f"{B}/447", headers=h, json={"html": p447["html"]}).json()["post"]["draft"]["html"]
    # /\evil.example: o Chromium lê como //evil.example (outro site, sem o rel="noopener")
    for sujo in ('<a href="/\\evil.example/x">bad</a>', '<img src="/\\evil.example/x.png" alt="x">',
                 '<a href="//evil.example/x">bad</a>', '<img src="//evil.example/x.png" alt="x">'):
        salvo = painel.patch(f"{B}/{pid}", headers=h, json={"html": sujo + "<p>ok</p>"}).json()["post"]["draft"]["html"]
        assert "evil.example" not in salvo, (sujo, salvo)


def test_entrada_absurda_da_4xx_nunca_500(amb):
    painel, site, con = amb
    h = _entra(painel, OP)
    grande = "99999999999999999999"                    # maior que o inteiro do SQLite (2**63-1)
    for metodo, url, kw in (("get", f"{B}/{grande}", {}), ("get", f"{B}/{grande}/versoes", {}), ("get", f"{B}/{grande}/previa", {}),
                            ("patch", f"{B}/{grande}", {"json": {"title": "Abc def"}}),
                            ("post", f"{B}/451/versoes/{grande}/voltar", {}), ("post", f"{B}/{grande}/versoes/1/voltar", {}),
                            ("post", f"{B}/{grande}/capa", {"files": {"arquivo": ("a.jpg", b"x", "image/jpeg")}}),
                            ("post", f"{B}/{grande}/imagens", {"files": {"arquivo": ("a.jpg", b"x", "image/jpeg")}}),
                            ("get", f"{B}?offset={grande}", {}), ("get", f"{B}?offset=-1", {}), ("get", f"{B}/0", {})):
        r = getattr(painel, metodo)(url, headers=h, **kw)
        assert r.status_code == 422, (metodo, url, r.status_code)
    adm = _entra(painel, ADM)
    for url, corpo in ((f"{B}/{grande}/publicar", {"visto": None}), (f"{B}/{grande}/despublicar", {"confirmar": True})):
        assert painel.post(url, headers=adm, json=corpo).status_code == 422, url
    assert painel.get(f"{B}/{2**63 - 1}", headers=adm).status_code == 404, "o maior id que cabe: não existe"
    # meia letra de UTF-16 sozinha (o JSON aceita "\\ud800"; o banco não grava): sai do texto
    h = _entra(painel, OP)
    hj = {**h, "content-type": "application/json"}
    r = painel.post(B, headers=hj, content=b'{"title": "Kart \\udfff tips", "category": "training-racing"}')
    assert r.status_code == 201 and r.json()["post"]["draft"]["title"] == "Kart tips", r.text
    pid = r.json()["id"]
    r = painel.patch(f"{B}/{pid}", headers=hj, content=b'{"title": "Kart \\ud800 line", "excerpt": "a\\ud800b", "html": "<p>x \\ud800y</p>"}')
    assert r.status_code == 200, r.text
    d = r.json()["post"]["draft"]
    assert (d["title"], d["excerpt"], d["html"]) == ("Kart line", "ab", "<p>x y</p>")
    assert um(con, "SELECT detail FROM audit_logs WHERE event='blog.post.create' AND entity_id=?", (str(pid),))["detail"]


def test_home_sem_artigo_no_ar_nao_mostra_a_faixa_do_blog(amb):
    painel, site, con = amb
    titulo, sub = conteudo.HOME["blog_titulo"], conteudo.HOME["blog_sub"]
    home = site.get("/").text
    assert 'id="h-blog"' in home and titulo in home and home.count('class="post-card"') == 3
    adm = _entra(painel, ADM)
    for p in ARQUIVO:
        assert painel.post(f"{B}/{p['id']}/despublicar", headers=adm, json={"confirmar": True}).status_code == 200
    home = site.get("/").text
    assert 'id="h-blog"' not in home and sub not in home and 'class="posts-grade"' not in home
    assert home.count("<h1") == 1 and 'id="h-duvidas"' in home, "o resto da home fica"


def _png_liso(largura, altura):
    """Um PNG válido de cor lisa (1 bit por pixel): 100 MP cabem em ~15 KB, e decodificar pede centenas de MB."""
    def bloco(tipo, dados):
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)
    linha, z = b"\x00" * (1 + (largura + 7) // 8), zlib.compressobj(9)
    idat = b"".join(z.compress(linha) for _ in range(altura)) + z.flush()
    return (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", largura, altura, 1, 0, 0, 0, 0))
            + bloco(b"IDAT", idat) + bloco(b"IEND", b""))


def test_foto_com_pixels_demais_da_400_antes_de_decodificar(amb):
    painel, site, con = amb
    h = _entra(painel, OP)
    pid = _novo(painel, h)["id"]
    bomba = _png_liso(10_000, 10_000)                  # 100 MP: o Pillow só avisava (recusa acima de 120 MP)
    assert len(bomba) < 100_000
    for rota in ("capa", "imagens"):
        r = painel.post(f"{B}/{pid}/{rota}", headers=h, files={"arquivo": ("liso.png", bomba, "image/png")})
        assert r.status_code == 400 and r.json()["detail"] == imagem.GRANDE_DEMAIS, (rota, r.status_code, r.text[:200])
    # a foto de 48–50 MP de um celular continua passando na conferência (o cabeçalho; nada decodificado aqui)
    assert imagem.abrir(_png_liso(8_000, 6_250)).size == (8_000, 6_250)


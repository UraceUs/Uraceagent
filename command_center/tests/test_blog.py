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
"""
import io
import json
import re
import sqlite3
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from command_center.api import auth
from command_center.api.main import app
from command_center.db import aplicar_schema, conectar, todos, um
from command_center.providers import blog
from command_center.vitrine import html_seguro, paginas_site

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


def _publica(painel, pid, email=ADM):
    return painel.post(f"{B}/{pid}/publicar", headers=_entra(painel, email))


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

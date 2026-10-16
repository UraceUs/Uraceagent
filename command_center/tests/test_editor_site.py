"""#300 (dono, 16/10): *"no Command Center separe o site público uma seção para o site público aí no site público a
gente tenha é, como alterar o design, layout, puxando e arrastando e soltando de uma forma bem simples e conseguir
editar por lá como se fosse realmente um WordPress"*. Decisão: **livre, tipo Elementor**.

O que estes testes trancam:
- o modelo guarda só o que é do modelo (nada de HTML solto, script, link estranho, foto de fora);
- página nova: rascunho fora do ar; publicar confere as regras do site (um h1, sem pular nível, foto com descrição,
  título e descrição); publicada, sai no endereço dela, no sitemap, com canonical e JSON-LD;
- página que já existe: as faixas dela viram seções originais que se movem e se escondem; sem mexer, sai igual;
  "Voltar ao original" devolve a página do código;
- cada publicação guarda uma versão; voltar uma versão traz ela para o rascunho;
- karts, produtos e cartões vêm do banco; ver é do operador, mudar e publicar é do gerente.
"""
import io
import json
import re

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from command_center.api import auth
from command_center.api.main import app
from command_center.db import aplicar_schema, conectar, um
from command_center.providers import servicos_site
from command_center.vitrine import editor as ed

SENHA = "pista-molhada-7"


@pytest.fixture()
def amb(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    monkeypatch.delenv("CC_SITE_HOSTS", raising=False)
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "ger@example.com", "Gerente", "MANAGER", SENHA)
    auth.criar_usuario(con, "op@example.com", "Operador", "OPERATOR", SENHA)
    con.commit()
    with TestClient(app, base_url="https://cc.test") as painel, TestClient(app, base_url="https://novo.urace.us") as site:
        yield painel, site, con
    con.close()


def _entra(t, email="ger@example.com"):
    t.cookies.clear()
    assert t.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": t.cookies.get("cc_csrf")}


def _nova(painel, h, **kw):
    r = painel.post("/ops/api/site/editor/paginas", headers=h, json={"title": "Summer Kart Camp 2027", "path": "/summer-camp/", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _salvar(painel, h, pid, **kw):
    return painel.patch(f"/ops/api/site/editor/paginas/{pid}", headers=h, json=kw)


def _secao(*widgets, fundo="clara", colunas=1):
    cols = [list(widgets)] + [[] for _ in range(colunas - 1)]
    return {"id": ed.novo_id(), "tipo": "secao", "fundo": fundo, "espaco": "m", "colunas": colunas, "itens": cols}


H1 = {"id": "h1a", "tipo": "titulo", "texto": "Summer Kart Camp", "nivel": 1}
DESC = "Five days of kart racing camp in Orlando for drivers 7 and up, with coaches, karts and gear included."


# ------------------------------------------------------------------ o modelo
@pytest.mark.parametrize("conteudo, erro", [
    ({"itens": [{"tipo": "html", "html": "<script>x</script>"}]}, "inválido"),
    ({"itens": [_secao({"tipo": "botao", "texto": "Go", "link": "javascript:alert(1)"})]}, "link"),
    ({"itens": [_secao({"tipo": "imagem", "src": "https://outro.example.com/x.png", "alt": "x"})]}, "foto"),
    ({"itens": [_secao({"tipo": "widget-novo"})]}, "desconhecido"),
    ({"itens": [{"tipo": "original", "indice": 0}]}, "original"),
])
def test_o_modelo_recusa_o_que_nao_e_dele(conteudo, erro):
    with pytest.raises(ed.ErroEditor, match=erro):
        ed.limpar(conteudo)


def test_texto_sai_limpo_e_nada_vira_html_solto():
    c = ed.limpar({"itens": [_secao({"tipo": "texto", "html": '<p onclick="x()">Hi <b>there</b><script>alert(1)</script></p>'},
                                    {"tipo": "titulo", "texto": "<img src=x onerror=alert(1)>", "nivel": 2})]})
    html = ed.corpo(c)
    assert "<p>Hi <b>there</b></p>" in html and "alert" not in html.replace("&lt;img src=x onerror=alert(1)&gt;", "")
    assert "&lt;img src=x onerror=alert(1)&gt;" in html, "título é texto, nunca HTML"


# ------------------------------------------------------------------ página nova
def test_pagina_nova_fica_fora_do_ar_ate_publicar_e_publicar_confere_as_regras(amb):
    painel, site, con = amb
    h = _entra(painel)
    p = _nova(painel, h)["pagina"]
    assert site.get("/summer-camp/").status_code == 404, "rascunho não sai no site"
    # sem descrição e com dois h1: não publica, e diz por quê
    _salvar(painel, h, p["id"], conteudo={"itens": [_secao(H1, {"tipo": "titulo", "texto": "Again", "nivel": 1})]})
    r = painel.post(f"/ops/api/site/editor/paginas/{p['id']}/publicar", headers=h)
    assert r.status_code == 400 and "um título nível 1" in r.json()["detail"] and "descrição" in r.json()["detail"]
    # título que pula de nível também não
    _salvar(painel, h, p["id"], description=DESC, conteudo={"itens": [_secao(H1, {"tipo": "titulo", "texto": "Deep", "nivel": 3})]})
    assert "pula de nível" in painel.post(f"/ops/api/site/editor/paginas/{p['id']}/publicar", headers=h).json()["detail"]
    _salvar(painel, h, p["id"], conteudo={"itens": [
        _secao(H1, {"tipo": "texto", "html": "<p>Learn from <strong>pro coaches</strong>.</p>"}, fundo="escura"),
        _secao({"tipo": "titulo", "texto": "What you get", "nivel": 2}, {"tipo": "lista", "itens": ["Karts", "Coaching"]},
               {"tipo": "botao", "texto": "Book the camp", "link": "/contact/?assunto=camp"}, colunas=2)]})
    r = painel.post(f"/ops/api/site/editor/paginas/{p['id']}/publicar", headers=h)
    assert r.status_code == 200, r.text
    html = site.get("/summer-camp/").text
    assert html.count("<h1") == 1 and "Summer Kart Camp" in html and "<strong>pro coaches</strong>" in html
    assert '<link rel="canonical" href="https://novo.urace.us/summer-camp/">' in html
    assert "<title>Summer Kart Camp 2027</title>" in html and DESC in html
    assert 'class="faixa escura ed-secao' in html and "ed-grade ed-c2" in html
    assert "application/ld+json" in html, "o JSON-LD do negócio"
    assert "/summer-camp/" in site.get("/sitemap.xml").text


def test_o_rascunho_muda_e_o_site_so_muda_quando_publica_de_novo(amb):
    painel, site, con = amb
    h = _entra(painel)
    pid = _nova(painel, h)["pagina"]["id"]
    _salvar(painel, h, pid, description=DESC, conteudo={"itens": [_secao(H1)]})
    painel.post(f"/ops/api/site/editor/paginas/{pid}/publicar", headers=h)
    r = _salvar(painel, h, pid, conteudo={"itens": [_secao({**H1, "texto": "Winter Kart Camp"})]})
    assert r.json()["pagina"]["estado"] == "mudou"
    assert "Summer Kart Camp" in site.get("/summer-camp/").text and "Winter Kart Camp" not in site.get("/summer-camp/").text
    prev = painel.get(f"/ops/api/site/editor/paginas/{pid}/previa", headers=h)
    assert prev.status_code == 200 and "Winter Kart Camp" in prev.text, "a pré-visualização mostra o rascunho"
    assert prev.headers["x-frame-options"] == "SAMEORIGIN" and "frame-ancestors 'self'" in prev.headers["content-security-policy"]
    assert 'name="robots" content="noindex' in prev.text
    painel.post(f"/ops/api/site/editor/paginas/{pid}/publicar", headers=h)
    assert "Winter Kart Camp" in site.get("/summer-camp/").text


def test_versoes_guardam_cada_publicacao_e_voltam_para_o_rascunho(amb):
    painel, site, con = amb
    h = _entra(painel)
    pid = _nova(painel, h)["pagina"]["id"]
    for nome in ("Version One Camp", "Version Two Camp"):
        _salvar(painel, h, pid, description=DESC, conteudo={"itens": [_secao({**H1, "texto": nome})]})
        assert painel.post(f"/ops/api/site/editor/paginas/{pid}/publicar", headers=h).status_code == 200
    vs = painel.get(f"/ops/api/site/editor/paginas/{pid}/versoes", headers=h).json()["versoes"]
    assert len(vs) == 2
    r = painel.post(f"/ops/api/site/editor/paginas/{pid}/versoes/{vs[-1]['id']}/voltar", headers=h)
    assert "Version One Camp" in json.dumps(r.json()["pagina"]["draft"])
    assert "Version Two Camp" in site.get("/summer-camp/").text, "voltar só mexe no rascunho"
    painel.post(f"/ops/api/site/editor/paginas/{pid}/publicar", headers=h)
    assert "Version One Camp" in site.get("/summer-camp/").text


@pytest.mark.parametrize("caminho", ["/store/x/", "/ops/x/", "/", "/academy/", "/legal/x/"])
def test_endereco_do_sistema_ou_de_pagina_que_existe_nao_vira_pagina_nova(amb, caminho):
    painel, site, con = amb
    h = _entra(painel)
    r = painel.post("/ops/api/site/editor/paginas", headers=h, json={"title": "Some page title", "path": caminho})
    assert r.status_code == 400, r.text


# ------------------------------------------------------------------ página que já existe
def test_pagina_existente_vira_faixas_que_se_movem_e_voltar_ao_original(amb):
    painel, site, con = amb
    h = _entra(painel)
    antes = site.get("/about/").text
    r = painel.post("/ops/api/site/editor/paginas", headers=h, json={"base": "/about/"})
    assert r.status_code == 201, r.text
    p = r.json()
    itens = p["pagina"]["draft"]["itens"]
    assert itens and all(x["tipo"] == "original" for x in itens) and len(p["originais"]) == len(itens)
    pid = p["pagina"]["id"]
    # publicar sem mexer: o mesmo conteúdo
    assert painel.post(f"/ops/api/site/editor/paginas/{pid}/publicar", headers=h).status_code == 200
    depois = site.get("/about/").text
    corpo = lambda x: re.search(r'<main id="conteudo">(.*)</main>', x, re.S).group(1)  # noqa: E731
    assert re.sub(r"\s+", "", corpo(depois)) == re.sub(r"\s+", "", corpo(antes)), "sem mexer, sai igual"
    # esconde a última faixa, põe uma seção nova antes da primeira e move a segunda para o fim
    novo = [_secao({"tipo": "titulo", "texto": "Meet the team in person", "nivel": 2},
                   {"tipo": "botao", "texto": "Visit us", "link": "/contact/"}, fundo="cinza")]
    orig = [dict(x) for x in itens]
    orig[-1]["oculto"] = True
    ordem = [orig[0], *novo, *orig[2:], orig[1]]
    r = _salvar(painel, h, pid, conteudo={"itens": ordem})
    assert r.status_code == 200, r.text
    assert painel.post(f"/ops/api/site/editor/paginas/{pid}/publicar", headers=h).status_code == 200, "o h1 é o da faixa original"
    html = site.get("/about/").text
    assert "Meet the team in person" in html and "ed-cinza" in html and html.count("<h1") == 1
    # voltar ao original
    assert painel.post(f"/ops/api/site/editor/paginas/{pid}/despublicar", headers=h).status_code == 200
    assert re.sub(r"\s+", "", corpo(site.get("/about/").text)) == re.sub(r"\s+", "", corpo(antes))
    assert um(con, "SELECT COUNT(*) AS n FROM site_page_versions WHERE page_id=?", (pid,))["n"] == 2, "as versões ficam"


# ------------------------------------------------------------------ o que vem do banco
def test_karts_e_cartoes_vem_do_painel(amb):
    painel, site, con = amb
    h = _entra(painel)
    sid = um(con, "SELECT id FROM booking_services WHERE site_kart='4-stroke'")["id"]
    servicos_site.mudar(con, None, sid, {"price": "655", "site_title": "Rental 4T"})
    con.commit()
    pid = _nova(painel, h)["pagina"]["id"]
    titulo = {"tipo": "titulo", "texto": "Pick your kart", "nivel": 2}       # os cartões têm h3: o h2 vem antes
    _salvar(painel, h, pid, description=DESC, conteudo={"itens": [_secao(H1, titulo, {"tipo": "karts"}, {"tipo": "cartoes", "pagina": "academy"})]})
    assert painel.post(f"/ops/api/site/editor/paginas/{pid}/publicar", headers=h).status_code == 200
    html = site.get("/summer-camp/").text
    assert "Rental 4T" in html and "$655" in html, "o kart e o preço do painel"
    assert "12-month contract" in html, "os cartões da Academy do painel"


# ------------------------------------------------------------------ fotos e permissões
def test_foto_do_editor_vira_webp_sem_exif_e_exige_descricao(amb):
    painel, site, con = amb
    h = _entra(painel)
    buf = io.BytesIO()
    ex = Image.Exif(); ex[0x010F] = "Fabricante"
    Image.new("RGB", (2400, 1600), (10, 120, 200)).save(buf, "JPEG", exif=ex)
    r = painel.post("/ops/api/site/editor/fotos", headers=h, files={"arquivo": ("f.jpg", buf.getvalue(), "image/jpeg")})
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["src"].startswith("/_f/") and max(f["largura"], f["altura"]) == 1600
    img = site.get(f["src"])
    assert img.status_code == 200 and not Image.open(io.BytesIO(img.content)).getexif()
    pid = _nova(painel, h)["pagina"]["id"]
    w = {"tipo": "imagem", "src": f["src"], "alt": "", "largura": f["largura"], "altura": f["altura"]}
    _salvar(painel, h, pid, description=DESC, conteudo={"itens": [_secao(H1, w)]})
    assert "sem descrição" in painel.post(f"/ops/api/site/editor/paginas/{pid}/publicar", headers=h).json()["detail"]
    _salvar(painel, h, pid, conteudo={"itens": [_secao(H1, {**w, "alt": "Drivers on the track at sunset"})]})
    assert painel.post(f"/ops/api/site/editor/paginas/{pid}/publicar", headers=h).status_code == 200
    assert f'src="{f["src"]}" alt="Drivers on the track at sunset"' in site.get("/summer-camp/").text


def test_operador_ve_e_so_o_gerente_muda_e_publica(amb):
    painel, site, con = amb
    h = _entra(painel)
    pid = _nova(painel, h)["pagina"]["id"]
    h = _entra(painel, "op@example.com")
    assert painel.get("/ops/api/site/editor/paginas", headers=h).status_code == 200
    assert painel.get(f"/ops/api/site/editor/paginas/{pid}/previa", headers=h).status_code == 200
    assert _salvar(painel, h, pid, title="Changed by operator").status_code == 403
    assert painel.post(f"/ops/api/site/editor/paginas/{pid}/publicar", headers=h).status_code == 403
    assert um(con, "SELECT COUNT(*) AS n FROM audit_logs WHERE event='site.page.create'")["n"] == 1


# ------------------------------------------------------------------ #315: o editor como o Canva
# Dono, 16/10: *"ele abre uma mini visualização de como é o site público. E dali a pessoa consegue, por ali, clicar no
# que ela precisa editar. Ela edita, ela puxa, ela arrasta, ela solta … É como se fosse um Canva."*
def _previa(painel, h, pid, editar=True):
    return painel.get(f"/ops/api/site/editor/paginas/{pid}/previa" + ("?editar=1" if editar else ""), headers=h)


def test_a_previa_de_edicao_marca_cada_peca_e_o_site_continua_igual(amb, monkeypatch):
    """A prévia de edição tem os `data-ed-*` (seção, coluna, elemento, faixa original) e o CSS do editor, sem medição;
    o site e a prévia de sempre não levam nada disso."""
    painel, site, con = amb
    monkeypatch.setenv("SITE_GTM_ID", "GTM-59CCNDC")          # com a medição ligada no site
    h = _entra(painel)
    pid = _nova(painel, h)["pagina"]["id"]
    sec = _secao(H1, {"id": "bt1", "tipo": "botao", "texto": "Book the camp", "link": "/contact/"},
                 {"id": "li1", "tipo": "lista", "itens": []}, colunas=2)
    _salvar(painel, h, pid, description=DESC, conteudo={"itens": [sec]})
    ed_html = _previa(painel, h, pid).text
    assert f'data-ed-s="{sec["id"]}"' in ed_html and f'data-ed-col="{sec["id"]}:0"' in ed_html
    assert f'data-ed-col="{sec["id"]}:1"' in ed_html, "a coluna vazia também é um lugar para soltar"
    assert '<h1 data-ed-w="h1a" data-ed-tipo="titulo" class="ed-t' in ed_html
    assert 'data-ed-w="bt1" data-ed-tipo="botao"' in ed_html
    assert 'class="lista ed-lista ed-vazio"' in ed_html, "a lista vazia continua clicável para escrever"
    assert "/_s/editor-previa.css?v=" in ed_html
    assert "medicao.js" not in ed_html and "GTM-59CCNDC" not in ed_html, "quem edita não é visita"
    assert 'name="robots" content="noindex' in ed_html
    assert painel.get("/_s/editor-previa.css").status_code == 200
    # a prévia de sempre e o site: nada do editor
    assert painel.post(f"/ops/api/site/editor/paginas/{pid}/publicar", headers=h).status_code == 200
    for html in (_previa(painel, h, pid, editar=False).text, site.get("/summer-camp/").text):
        assert "data-ed-" not in html and "editor-previa.css" not in html and "ed-vazio" not in html
    assert "GTM-59CCNDC" in site.get("/summer-camp/").text, "o site continua medindo"


def test_a_previa_de_edicao_de_pagina_que_existe_marca_as_faixas_e_mostra_a_escondida_apagada(amb):
    painel, site, con = amb
    h = _entra(painel)
    p = painel.post("/ops/api/site/editor/paginas", headers=h, json={"base": "/about/"}).json()
    itens = [dict(x) for x in p["pagina"]["draft"]["itens"]]
    itens[1]["oculto"] = True
    _salvar(painel, h, p["pagina"]["id"], conteudo={"itens": itens})
    html = _previa(painel, h, p["pagina"]["id"]).text
    assert '<section data-ed-s="o0" data-ed-o="0"' in html
    assert '<section data-ed-s="o1" data-ed-o="1" data-ed-oculto=""' in html, "a escondida aparece apagada na prévia"
    publica = re.search(r'<main id="conteudo">(.*)</main>', _previa(painel, h, p["pagina"]["id"], editar=False).text, re.S).group(1)
    assert publica.count("<section") == html.count("<section") - 1, "fora da edição, a escondida some"


def test_a_previa_continua_sem_script_nem_estilo_inline(amb):
    """A prévia roda na origem do painel, com a sessão do gerente: a política dela é a do site (nada inline)."""
    painel, site, con = amb
    h = _entra(painel)
    pid = _nova(painel, h)["pagina"]["id"]
    pol = _previa(painel, h, pid).headers["content-security-policy"]
    diretivas = dict(x.strip().split(" ", 1) for x in pol.split(";"))
    assert diretivas["script-src"] == "'self'" and diretivas["style-src"] == "'self'"
    assert "unsafe" not in pol and diretivas["frame-ancestors"] == "'self'"


def test_salvar_com_a_revisao_velha_recusa_em_vez_de_apagar_o_que_o_outro_fez(amb):
    painel, site, con = amb
    h = _entra(painel)
    p = _nova(painel, h)["pagina"]
    rev = p["rev"]
    r = _salvar(painel, h, p["id"], rev=rev, conteudo={"itens": [_secao({**H1, "texto": "Gerente A"})]})
    assert r.status_code == 200 and r.json()["pagina"]["rev"] == rev + 1
    r = _salvar(painel, h, p["id"], rev=rev, conteudo={"itens": [_secao({**H1, "texto": "Gerente B"})]})
    assert r.status_code == 409 and r.json()["detail"]["motivo"] == "rev"
    assert "Gerente A" in json.dumps(painel.get(f"/ops/api/site/editor/paginas/{p['id']}", headers=h).json()["pagina"]["draft"])
    # publicar também confere: só vai para o ar o rascunho que a tela mostra
    _salvar(painel, h, p["id"], description=DESC)
    r = painel.post(f"/ops/api/site/editor/paginas/{p['id']}/publicar", headers=h, json={"rev": rev + 1})
    assert r.status_code == 409 and site.get("/summer-camp/").status_code == 404
    r = painel.post(f"/ops/api/site/editor/paginas/{p['id']}/publicar", headers=h, json={"rev": rev + 2})
    assert r.status_code == 200, r.text


def test_titulo_vazio_salva_no_rascunho_e_trava_a_publicacao(amb):
    painel, site, con = amb
    h = _entra(painel)
    pid = _nova(painel, h)["pagina"]["id"]
    r = _salvar(painel, h, pid, description=DESC, conteudo={"itens": [_secao(H1, {"id": "t2", "tipo": "titulo", "texto": "", "nivel": 2},
                                                                                {"id": "b2", "tipo": "botao", "texto": "Go", "link": ""})]})
    assert r.status_code == 200, r.text
    assert any("título(s) vazio(s)" in x for x in r.json()["problemas"])
    assert any("sem texto ou sem link" in x for x in r.json()["problemas"])
    r = painel.post(f"/ops/api/site/editor/paginas/{pid}/publicar", headers=h)
    assert r.status_code == 400 and "vazio" in r.json()["detail"]


def test_link_que_nao_passa_fica_o_de_antes_e_volta_o_motivo(amb):
    painel, site, con = amb
    h = _entra(painel)
    pid = _nova(painel, h)["pagina"]["id"]
    bt = {"id": "bt9", "tipo": "botao", "texto": "Book", "link": "/contact/"}
    _salvar(painel, h, pid, conteudo={"itens": [_secao(H1, bt)]})
    for ruim in ("javascript:alert(1)", "/con tato"):
        r = _salvar(painel, h, pid, conteudo={"itens": [_secao({**H1, "texto": "Other text kept"}, {**bt, "link": ruim})]})
        assert r.status_code == 200, "o resto da página salva"
        assert "link" in r.json()["erros"]["bt9"]
        d = json.dumps(r.json()["pagina"]["draft"])
        assert '"link": "/contact/"' in d and "javascript" not in d and "Other text kept" in d


def test_desenhar_devolve_so_as_secoes_novas_marcadas(amb):
    painel, site, con = amb
    h = _entra(painel)
    p = painel.post("/ops/api/site/editor/paginas", headers=h, json={"base": "/about/"}).json()
    nova = _secao({"id": "tt1", "tipo": "titulo", "texto": "Meet the team", "nivel": 2})
    itens = [*p["pagina"]["draft"]["itens"], nova]
    r = _salvar(painel, h, p["pagina"]["id"], conteudo={"itens": itens}, desenhar=True).json()
    assert [s["id"] for s in r["secoes"]] == [nova["id"]], "as faixas originais não vão de novo"
    assert 'data-ed-w="tt1"' in r["secoes"][0]["html"] and r["secoes"][0]["html"].startswith("<section")
    assert "secoes" not in _salvar(painel, h, p["pagina"]["id"], conteudo={"itens": itens}).json()


def test_texto_vindo_da_previa_sai_limpo():
    """O texto editado na prévia chega como HTML do contenteditable: script e evento somem, <div> vira parágrafo,
    e o título é sempre texto."""
    c = ed.limpar({"itens": [_secao(
        {"id": "x1", "tipo": "texto", "html": '<div>One <b>bold</b></div><div><img src=x onerror="alert(1)">Two</div><script>alert(2)</script>'},
        {"id": "x2", "tipo": "titulo", "texto": "Hello<br>World<div>x</div>", "nivel": 2},
        {"id": "x3", "tipo": "lista", "itens": ["<b>Karts</b>", ""]})]}, rascunho=True)
    html = ed.corpo(c)
    assert "<p>One <b>bold</b></p><p>Two</p>" in html, html
    assert "onerror" not in html and "alert" not in html and "<script" not in html
    assert "Hello&lt;br&gt;World&lt;div&gt;x&lt;/div&gt;" in html and "<br>" not in html
    assert "<li>&lt;b&gt;Karts&lt;/b&gt;</li>" in html

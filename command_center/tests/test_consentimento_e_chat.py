"""#171 e #170 (dono, 15/10, Bloco 1): banner de consentimento para o Analytics e o pixel ("Sim, banner
simples") e o chat do Kommo em todas as páginas públicas.

- O Google e o Meta **só** carregam depois do "Accept". "Decline" guarda a recusa e nada de fora carrega.
- Sem `noscript` do GTM e do pixel: quem está sem JavaScript não tem como aceitar.
- O chat do Kommo é atendimento, não medição: carrega com a configuração, sem depender do banner — mas
  nunca no painel, no carrinho ou na página do pedido (mostram dado de pessoa).
- id e hash do Kommo moram no ambiente (o repositório é público), como os ids da medição.
O teste do navegador roda a página de verdade no Chromium, servida pelo TestClient, e conta as
requisições que saem para o Google e para o Kommo."""
import os

import pytest

from command_center.tests.test_medicao import GTM, SITE, _bloco, cli  # noqa: F401

KID = "1000001"                     # fictício, no formato do widget
KHASH = "0" * 64                    # fictício, no formato do widget


def _com_chat(monkeypatch):
    monkeypatch.setenv("SITE_KOMMO_ID", KID)
    monkeypatch.setenv("SITE_KOMMO_HASH", KHASH)


def test_o_chat_do_kommo_vem_do_ambiente_e_abre_so_os_hosts_dele(cli, monkeypatch):  # noqa: F811
    _com_chat(monkeypatch)
    r = cli.get("/")
    d = _bloco(r.text)
    assert d["kommo"] == {"id": KID, "hash": KHASH} and d["gtm"] == "", "chat sem medição também carrega"
    pol = r.headers["content-security-policy"]
    for h in ("script-src 'self' https://gso.kommo.com https://forms.kommo.com https://piper.amocrm.com",
              "wss://lc-en.kommo.com", "frame-src https://gso.kommo.com https://forms.kommo.com https://piper.amocrm.com"):
        assert h in pol, h
    # #284: o widget põe estilo inline (sem isso o balão aparece sem forma no ar); script inline, nunca
    diretivas = {d.split()[0]: d.split()[1:] for d in pol.split("; ")}
    assert "'unsafe-inline'" in diretivas["style-src"]
    assert "'unsafe-inline'" not in diretivas["script-src"] and "'unsafe-eval'" not in pol
    # o painel e o carrinho nunca levam script de fora
    assert "kommo" not in cli.get("/ops/").headers.get("content-security-policy", "")
    carrinho = cli.get("/cart/")
    assert _bloco(carrinho.text) is None and "kommo" not in carrinho.headers.get("content-security-policy", "")


def test_id_ou_hash_fora_do_formato_nao_carrega_o_chat(cli, monkeypatch):  # noqa: F811
    monkeypatch.setenv("SITE_KOMMO_ID", KID)
    monkeypatch.setenv("SITE_KOMMO_HASH", "<script>")
    assert _bloco(cli.get("/").text) is None


def test_o_script_so_carrega_o_google_e_o_meta_depois_do_accept():
    js = open(os.path.join(os.path.dirname(__file__), "..", "vitrine", "static", "medicao.js"), encoding="utf-8").read()
    fora = js.split("function carregarDeFora()", 1)[0]
    assert "googletagmanager.com/gtm.js" not in fora and "pixelBase(cfg.pixel)" not in fora, \
        "nada do Google ou do Meta antes do consentimento"
    assert "if (escolha === 'sim') carregarDeFora()" in js


# ------------------------------------------------------------------ no navegador, de verdade
NAVEGADOR = pytest.mark.skipif(os.environ.get("CC_E2E") != "1", reason="navegador: rode com CC_E2E=1")


def _abrir(contexto, cli):  # noqa: F811
    """Uma página do Chromium em que o site é o TestClient e o resto do mundo é contado e barrado."""
    saidas = {"google": 0, "meta": 0, "kommo": 0}

    def rota(route):
        u = route.request.url
        if u.startswith(SITE):
            r = cli.get(u[len(SITE):] or "/")
            route.fulfill(status=r.status_code, body=r.content,
                          headers={k: v for k, v in r.headers.items() if k.lower() not in ("content-length", "content-encoding")})
            return
        if "googletagmanager" in u or "google-analytics" in u:
            saidas["google"] += 1
        elif "facebook" in u:
            saidas["meta"] += 1
        elif "kommo" in u or "amocrm" in u:
            saidas["kommo"] += 1
        route.abort()

    contexto.route("**/*", rota)
    return contexto.new_page(), saidas


@NAVEGADOR
def test_no_navegador_o_banner_segura_o_google_ate_o_accept_e_o_decline_vale(cli, monkeypatch):  # noqa: F811
    from playwright.sync_api import sync_playwright
    monkeypatch.setenv("SITE_GTM_ID", GTM)
    _com_chat(monkeypatch)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("PW_CHROMIUM") or None)
        # 1 · primeira visita: banner, chat carregando, e NADA do Google
        ctx = b.new_context(viewport={"width": 390, "height": 844})
        pg, saidas = _abrir(ctx, cli)
        pg.goto(SITE + "/")
        pg.locator(".consentimento").wait_for()
        pg.wait_for_timeout(800)
        assert saidas["google"] == 0, "o Google não pode carregar antes do Accept"
        assert saidas["kommo"] >= 1, "o chat é atendimento: carrega sem depender do banner"
        botoes = pg.locator(".consentimento button")
        assert [botoes.nth(i).inner_text() for i in range(botoes.count())] == ["Decline", "Accept"]
        assert all(botoes.nth(i).bounding_box()["height"] >= 40 for i in range(botoes.count())), "alvo de toque"
        # 2 · Accept: o Google carrega na hora, e a próxima página já vem sem banner
        pg.get_by_role("button", name="Accept").click()
        pg.wait_for_timeout(500)
        assert saidas["google"] >= 1
        pg.goto(SITE + "/services/")
        pg.wait_for_timeout(500)
        assert pg.locator(".consentimento").count() == 0
        ctx.close()
        # 3 · outra pessoa: Decline, e nada do Google nem agora nem na próxima página
        ctx = b.new_context(viewport={"width": 390, "height": 844})
        pg, saidas = _abrir(ctx, cli)
        pg.goto(SITE + "/")
        pg.get_by_role("button", name="Decline").click()
        pg.goto(SITE + "/store/")
        pg.wait_for_timeout(800)
        assert saidas["google"] == 0 and pg.locator(".consentimento").count() == 0
        # "Cookie settings" no rodapé pergunta de novo
        pg.get_by_role("button", name="Cookie settings").click()
        pg.locator(".consentimento").wait_for()
        # nada rola para o lado com o banner aberto
        assert pg.evaluate("document.documentElement.scrollWidth") <= 390
        b.close()


# #284: um widget fictício que faz o que o do Kommo faz no ar — põe um <style> e um style="" no HTML
# dele e um balão fixo embaixo à direita. Antes, o navegador recusava o estilo (CSP) e o balão ficava
# sem forma; e, com forma, ele cobria o banner de cookies.
WIDGET = """(function () {
  var st = document.createElement('style')
  st.textContent = '.amo-button-holder{padding:7px}' +
    '.amo-button{width:60px;height:60px;border-radius:50%;background:rgb(26, 92, 255)}'
  document.head.appendChild(st)
  var d = document.createElement('div')
  d.className = 'amo-button-holder amo-horisontal'
  // #293: como o widget real no ar (16/10) — a posição vem inline, solta a 90 px das bordas
  d.setAttribute('style', 'position: fixed; z-index: 61; right: 90px; bottom: 90px;')
  d.innerHTML = '<div id="amobutton" class="amo-button" style="box-shadow:0 2px 8px #0003"></div>'
  document.body.appendChild(d)
})()"""


@NAVEGADOR
@pytest.mark.parametrize("largura", [360, 1280])
def test_no_navegador_o_balao_do_chat_tem_estilo_e_nao_cobre_o_banner(cli, monkeypatch, largura):  # noqa: F811
    from playwright.sync_api import sync_playwright
    monkeypatch.setenv("SITE_GTM_ID", GTM)
    _com_chat(monkeypatch)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("PW_CHROMIUM") or None)
        ctx = b.new_context(viewport={"width": largura, "height": 800})

        def rota(route):
            u = route.request.url
            if u.startswith(SITE):
                r = cli.get(u[len(SITE):] or "/")
                route.fulfill(status=r.status_code, body=r.content,
                              headers={k: v for k, v in r.headers.items() if k.lower() not in ("content-length", "content-encoding")})
            elif u.startswith("https://gso.kommo.com/js/button.js"):
                route.fulfill(status=200, body=WIDGET, headers={"content-type": "application/javascript"})
            else:
                route.abort()
        ctx.route("**/*", rota)
        pg = ctx.new_page()
        pg.add_init_script("window.__csp = []; document.addEventListener('securitypolicyviolation',"
                           " e => window.__csp.push(e.violatedDirective + ' ' + (e.blockedURI || 'inline')))")
        pg.goto(SITE + "/")
        banner = pg.locator(".consentimento")
        banner.wait_for()
        balao = pg.locator(".amo-button")
        balao.wait_for()
        pg.wait_for_timeout(400)                                    # a transição do balão
        assert [v for v in pg.evaluate("window.__csp") if v.startswith("style-src")] == [], "estilo do widget recusado"
        assert pg.evaluate("getComputedStyle(document.querySelector('.amo-button')).boxShadow") != "none", "style=\"\" recusado"
        assert balao.bounding_box()["width"] == 60, "o <style> do widget não valeu"
        bb, bn = balao.bounding_box(), banner.bounding_box()
        assert bb["y"] + bb["height"] <= bn["y"] + 1, f"o balão cobre o banner: {bb} × {bn}"
        assert pg.evaluate("window.__csp.filter(v => v.startsWith('script-src') && v.endsWith('inline'))") == []
        # fechado o banner, o balão volta para o canto — #293 (dono, 16/10): "bem no canto inferior direito",
        # não onde o Kommo põe (90 px das bordas)
        pg.get_by_role("button", name="Accept").click()
        pg.wait_for_timeout(400)
        bb = balao.bounding_box()
        assert largura - (bb["x"] + bb["width"]) <= 24, f"longe da borda direita: {bb}"
        assert 800 - (bb["y"] + bb["height"]) <= 24, f"longe da borda de baixo: {bb}"
        assert bb["x"] + bb["width"] <= largura and bb["y"] + bb["height"] <= 800, "o balão inteiro na tela"
        b.close()

"""End-to-end no navegador de verdade (issue #16): servidor real, banco semeado e Chromium.

Roda só com CC_E2E=1 — precisa do frontend construído (`npm run build` em
command_center/web) e do Playwright para Python. No CI é um job próprio; localmente:

    (cd command_center/web && npm run build)
    CC_E2E=1 python3 -m pytest -q command_center/tests/e2e

Chromium fora do lugar padrão: PW_CHROMIUM=/opt/pw-browsers/chromium.
Nada aqui fala com Asana, Gmail, QuickBooks ou Kommo: o banco é descartável e o
servidor sobe sem sincronia (CC_AUTOSYNC=0) e sem credencial (URACE_ENV inexistente).
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("CC_E2E") != "1", reason="end-to-end: rode com CC_E2E=1")

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DIST = os.path.join(RAIZ, "command_center", "web", "dist", "index.html")
SENHA = "senha-de-teste-123"

# Toda tela do menu. Rota com :id usa o 1 que a semente cria.
ROTAS = ["/", "/attention", "/clients", "/clients/1", "/races", "/gmail", "/gmail/manual", "/asana", "/docusign",
         "/quickbooks", "/crm/chat", "/crm/funil", "/sales", "/sales/agenda", "/ai", "/ai/capabilities", "/approvals",
         "/integrations", "/automation", "/activity", "/users", "/audit", "/policies", "/account", "/estoque",
         "/pedidos", "/compras", "/planejamento", "/equipe"]


def _porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    if not os.path.exists(DIST):
        pytest.fail("frontend não construído: rode `npm run build` em command_center/web")
    pasta = tmp_path_factory.mktemp("e2e")
    env = dict(os.environ, CC_DB_PATH=str(pasta / "e2e.sqlite"), URACE_DIR=str(pasta), URACE_ENV="/nao/existe",
               CC_AUTOSYNC="0", PYTHONPATH=RAIZ)
    subprocess.run([sys.executable, os.path.join(RAIZ, "command_center", "tests", "e2e", "semear.py")],
                   env=env, check=True, cwd=RAIZ, capture_output=True)
    porta = _porta_livre()
    log = open(pasta / "uvicorn.log", "w")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "command_center.api.main:app", "--port", str(porta)],
                            env=env, cwd=RAIZ, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{porta}/ops"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/login", timeout=1)
            break
        except OSError:
            time.sleep(0.2)
    else:
        proc.terminate()
        pytest.fail("servidor não subiu: " + open(pasta / "uvicorn.log").read()[-2000:])
    yield base
    proc.terminate()
    proc.wait(timeout=10)
    log.close()


@pytest.fixture(scope="module")
def navegador():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("PW_CHROMIUM") or None)
        yield b
        b.close()


def entrar(navegador, base, email="eduardo@urace.us", largura=1280, altura=900):
    """Página logada, com os erros de JavaScript e as respostas 5xx da API anotados nela."""
    pg = navegador.new_page(viewport={"width": largura, "height": altura})
    pg.erros_js, pg.erros_api = [], []
    pg.on("pageerror", lambda e: pg.erros_js.append(str(e)))
    pg.on("response", lambda r: pg.erros_api.append(f"{r.status} {r.url}") if "/api/" in r.url and r.status >= 500 else None)
    pg.goto(base + "/login")
    pg.fill("#email", email)
    pg.fill("#pw", SENHA)
    pg.keyboard.press("Enter")
    pg.wait_for_url(lambda u: "/login" not in u, timeout=10000)
    return pg


def abrir(pg, base, rota):
    pg.goto(base + rota)
    pg.wait_for_load_state("networkidle")


def test_login_errado_nao_entra(servidor, navegador):
    pg = navegador.new_page()
    pg.goto(servidor + "/login")
    pg.fill("#email", "eduardo@urace.us")
    pg.fill("#pw", "senha-errada-000")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(800)
    assert "/login" in pg.url
    pg.close()


def test_toda_tela_abre_sem_erro(servidor, navegador):
    pg = entrar(navegador, servidor)
    problemas = []
    for rota in ROTAS:
        pg.erros_js.clear(); pg.erros_api.clear()
        abrir(pg, servidor, rota)
        if "/login" in pg.url:
            problemas.append(f"{rota}: mandou para o login")
        if pg.erros_js or pg.erros_api:
            problemas.append(f"{rota}: {pg.erros_js[:2]} {pg.erros_api[:2]}")
    pg.close()
    assert not problemas, "\n".join(problemas)


def test_operador_nao_ve_tela_de_gerente(servidor, navegador):
    pg = entrar(navegador, servidor, "op@urace.us")
    r = pg.request.get(servidor + "/api/users")
    assert r.status in (401, 403)
    pg.close()


def _cabecalhos(pg):
    """[(nível, texto)] na ordem do documento, só o que está visível."""
    return pg.evaluate("""() => [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')]
        .filter(h => h.offsetParent !== null || getComputedStyle(h).position === 'fixed')
        .map(h => [Number(h.tagName[1]), h.textContent.trim().slice(0, 40)])""")


def test_um_h1_por_tela_e_sem_pular_nivel(servidor, navegador):
    """Issue #18: exatamente um h1; e nenhum cabeçalho desce mais de um nível de uma vez (h1 → h3)."""
    pg = entrar(navegador, servidor)
    problemas = []
    for rota in ["/login-deslogado"] + ROTAS + ["/nao-existe"]:
        if rota == "/login-deslogado":
            p2 = navegador.new_page(); p2.goto(servidor + "/login"); p2.wait_for_load_state("networkidle")
            cab, alvo = _cabecalhos(p2), "/login"
            p2.close()
        else:
            abrir(pg, servidor, rota)
            cab, alvo = _cabecalhos(pg), rota
        h1 = [t for n, t in cab if n == 1]
        if len(h1) != 1:
            problemas.append(f"{alvo}: {len(h1)} h1 {h1}")
        anterior = 0
        for n, t in cab:
            if n > anterior + 1:
                problemas.append(f"{alvo}: pulou de h{anterior} para h{n} ({t!r})")
                break
            anterior = n
    pg.close()
    assert not problemas, "\n".join(problemas)


def test_titulo_da_aba_por_tela(servidor, navegador):
    pg = entrar(navegador, servidor)
    titulos = {}
    for rota in ["/compras", "/estoque", "/clients", "/attention"]:
        abrir(pg, servidor, rota)
        titulos[rota] = pg.title()
    pg.close()
    assert all(t.endswith("· URACE Command Center") for t in titulos.values()), titulos
    assert len(set(titulos.values())) == len(titulos), f"cada tela com o seu título: {titulos}"
    assert titulos["/compras"].startswith("Compras")


_VAZA = """() => {
  const W = document.documentElement.clientWidth
  const rola = document.documentElement.scrollWidth > W + 1 || document.body.scrollWidth > W + 1
  const recortado = el => { for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
    const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden' || o === 'clip') return true } return false }
  const culpados = []
  document.querySelectorAll('body *').forEach(el => {
    const b = el.getBoundingClientRect()
    if (b.width < 8 || b.height < 4 || getComputedStyle(el).position === 'fixed') return
    if (b.right > W + 1 && !recortado(el)) culpados.push(`${el.tagName.toLowerCase()}.${String(el.className || '').split(' ').slice(0, 2).join('.')} (${Math.round(b.right)}px)`)
  })
  return { rola, culpados: culpados.slice(0, 4) }
}"""


@pytest.mark.parametrize("largura", [360, 390])
def test_nenhuma_tela_rola_para_o_lado_no_celular(servidor, navegador, largura):
    """Issue #22: em 360 e 390 px, nenhuma tela empurra a página para o lado."""
    pg = entrar(navegador, servidor, largura=largura, altura=800)
    problemas = []
    for rota in ROTAS:
        abrir(pg, servidor, rota)
        r = pg.evaluate(_VAZA)
        if r["rola"] or r["culpados"]:
            problemas.append(f"{rota}: {'rola; ' if r['rola'] else ''}{', '.join(r['culpados'])}")
    pg.close()
    assert not problemas, "\n".join(problemas)


_PEQUENOS = """() => {
  const out = []
  document.querySelectorAll('.btn, .iconbtn, .mic, .tabs button').forEach(el => {
    const b = el.getBoundingClientRect()
    if (b.width < 2 || b.height < 2 || getComputedStyle(el).visibility === 'hidden') return
    if (b.bottom < 0 || b.top > innerHeight * 3) return
    // offsetHeight é o tamanho de layout: a animação de entrada (scale .985) não conta
    if (el.offsetHeight < 40) out.push(`${el.tagName.toLowerCase()}.${String(el.className).split(' ').slice(0, 3).join('.')}=${el.offsetHeight}px "${(el.textContent || '').trim().slice(0, 20)}"`)
  })
  return out.slice(0, 5)
}"""


def test_botoes_com_alvo_de_toque_de_40px_no_celular(servidor, navegador):
    """Issue #22: botão, ícone e aba com pelo menos 40 px de altura em 390 px."""
    pg = entrar(navegador, servidor, largura=390, altura=800)
    problemas = []
    for rota in ROTAS:
        abrir(pg, servidor, rota)
        r = pg.evaluate(_PEQUENOS)
        if r:
            problemas.append(f"{rota}: {', '.join(r)}")
    pg.close()
    assert not problemas, "\n".join(problemas)


@pytest.mark.parametrize("antigo,novo", [("/compras?c=7", "/compras/7"), ("/crm/chat?lead=3", "/crm/chat/3"),
                                         ("/equipe?c=2", "/equipe/2")])
def test_endereco_antigo_redireciona_para_o_caminho(servidor, navegador, antigo, novo):
    """Issue #24: item abre pelo caminho; o link antigo (salvo, notificação, atenção) ainda funciona."""
    pg = entrar(navegador, servidor)
    abrir(pg, servidor, antigo)
    assert pg.url.endswith("/ops" + novo), pg.url
    pg.close()


def test_abrir_e_fechar_a_compra_muda_o_endereco(servidor, navegador):
    # a semente não cria compra: cria uma pelo próprio painel (gerente)
    pg = entrar(navegador, servidor)
    r = pg.request.post(servidor + "/api/compras", data={"pedir": True, "linhas": [{"description": "Corrente 106", "qty": 2}]},
                        headers={"X-CSRF": next(c["value"] for c in pg.context.cookies() if c["name"] == "cc_csrf")})
    assert r.ok, r.text()
    pid = r.json()["id"]
    abrir(pg, servidor, "/compras")
    pg.get_by_text(f"#{pid} · Comet Kart Sales").click()
    pg.wait_for_url(f"**/ops/compras/{pid}")
    pg.get_by_role("heading", name=f"Compra #{pid} · Comet Kart Sales").wait_for(timeout=8000)
    pg.get_by_role("button", name="Fechar", exact=True).click()
    pg.wait_for_url("**/ops/compras")
    pg.close()

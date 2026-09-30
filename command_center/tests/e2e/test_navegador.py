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

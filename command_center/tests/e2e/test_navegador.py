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
import re
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

EMAILS = None


def codigo_do_email(para):
    """O código de 6 dígitos do último e-mail que o servidor "mandou" para `para` (#108)."""
    import json
    linhas = [json.loads(x) for x in open(EMAILS, encoding="utf-8").read().splitlines()]
    return re.search(r"\b(\d{6})\b", [x for x in linhas if x["to"] == para][-1]["text"]).group(1)


# Toda tela do menu. Rota com :id usa o 1 que a semente cria.
ROTAS = ["/", "/cofre", "/attention", "/clients", "/clients/1", "/races", "/gmail", "/gmail/manual", "/asana", "/docusign",
         "/quickbooks", "/crm/chat", "/crm/funil", "/sales", "/sales/agenda", "/ai", "/ai/capabilities", "/approvals",
         "/integrations", "/automation", "/activity", "/users", "/audit", "/policies", "/account", "/estoque",
         "/pedidos", "/compras", "/planejamento", "/equipe", "/site", "/site/disponibilidade", "/site/servicos",
         "/site/waiver", "/balcao", "/biblioteca", "/biblioteca/historicos", "/meu-dia", "/checklists",
         "/suits", "/suits/leads", "/suits/fornecedores", "/suits/ponte", "/suits/modelo"]


def _porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    if not os.path.exists(DIST):
        pytest.fail("frontend não construído: rode `npm run build` em command_center/web")
    pasta = tmp_path_factory.mktemp("e2e")
    global EMAILS
    EMAILS = str(pasta / "emails.jsonl")                 # #108: o e-mail do código vai para cá, nada sai da máquina
    env = dict(os.environ, CC_DB_PATH=str(pasta / "e2e.sqlite"), URACE_DIR=str(pasta), URACE_ENV="/nao/existe",
               CC_AUTOSYNC="0", PYTHONPATH=RAIZ, CC_EMAIL_FAKE=EMAILS,
               CC_SITE_HOSTS="127.0.0.1",              # #148: o site novo responde no endereço do teste
               CC_ACESSO_LIVRE="livre@urace.us",       # #162: a conta do cofre
               CC_COFRE_CHAVE="dGVzdGUtZTJlLWNoYXZlLWRvLWNvZnJlLTMyYnl0ZXM")  # 32 bytes de teste
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


@pytest.mark.parametrize("largura", [360, 1280])
def test_compra_do_email_mostra_a_linha_do_tempo(servidor, navegador, largura):
    """Dono, 06/10: "no painel de pedidos mostre todas as informações daquele pedido: se está em
    rota, se já foi entregue, se teve alguma atualização". A semente traz a compra da KartSport
    do pedido à saída para entrega e uma fatura pendente."""
    pg = entrar(navegador, servidor, largura=largura, altura=800)
    abrir(pg, servidor, "/compras")
    pg.get_by_text("fatura(s) a pagar").wait_for(timeout=8000)
    pg.get_by_text("KartSport North America", exact=False).first.click()
    pg.get_by_role("heading", name="Linha do tempo").wait_for(timeout=8000)
    corpo = pg.locator(".modal").inner_text()
    for esperado in ("saiu para entrega", "previsão de entrega", "preparando", "Última atualização", "1ZK102480300000001"):
        assert esperado in corpo, esperado
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    pg.get_by_role("button", name="Fechar", exact=True).click()
    pg.get_by_text("Courtney Concepts Karting", exact=False).first.click()
    pg.locator(".modal").get_by_text("pagamento pendente", exact=False).first.wait_for(timeout=8000)
    assert "fatura 9999" in pg.locator(".modal").inner_text()
    assert not pg.erros_js and not pg.erros_api, (pg.erros_js, pg.erros_api)
    pg.close()


def test_passar_para_vendas_registra_e_fica_no_chat(servidor, navegador):
    """Dono, 06/10: "eu continuo ali no chat do Kommo, mas quando eu clico ele registra no painel
    de vendas aquele lead como uma oportunidade" — sem abrir a página de vendas."""
    pg = entrar(navegador, servidor)
    lid = pg.request.get(servidor + "/api/crm/inbox").json()["conversas"][0]["id"]
    abrir(pg, servidor, f"/crm/chat/{lid}")
    pg.get_by_role("button", name=re.compile("Passar para vendas")).first.click()
    pg.get_by_text("Registrado no painel de vendas como oportunidade.").wait_for(timeout=8000)
    assert f"/crm/chat/{lid}" in pg.url, pg.url
    assert pg.get_by_role("button", name=re.compile(r"Em vendas \(1\)")).count() >= 1
    # sem credencial do Kommo no e2e, o detalhe ao vivo do lead responde 503 de propósito; vendas não pode falhar
    assert not pg.erros_js and not [e for e in pg.erros_api if "/api/sales" in e], (pg.erros_js, pg.erros_api)
    pg.close()


# ------------------------------------------------------------------ área do cliente (#40, #54)
ROTAS_PORTAL = ["/portal", "/portal/signup"]
ROTAS_PORTAL_DENTRO = ["/portal/dashboard", "/portal/book", "/portal/sessions", "/portal/drivers", "/portal/history", "/portal/account"]
CONTATO = {"phone": "(407) 555-0101", "address_line1": "100 Main St", "city": "Orlando", "state": "FL", "zip": "32809"}
PILOTO_OK = {"birth_date": "2014-05-01", "notes": "Two seasons in Mini kart.",
             "measures": {"height_in": 60, "weight_lb": 110, "chest_in": 30, "waist_in": 26, "hips_in": 30}}


def cliente_pela_api(pg, servidor, nome, email, piloto=None, ip=None):
    """Cria a conta (e um piloto completo) pela API, na sessão do navegador da página. `ip` faz o
    cadastro vir de outra conexão (o limite é de 10 cadastros por hora por conexão)."""
    r = pg.request.post(servidor + "/api/portal/signup", data={"name": nome, "email": email, "password": "pista-molhada-7",
                                                              "birth_date": "1980-01-01", "accept_terms": True, **CONTATO},
                        headers={"X-Forwarded-For": ip} if ip else None)
    assert r.ok, r.text()
    if piloto:
        csrf = next(c["value"] for c in pg.context.cookies() if c["name"] == "cp_csrf")
        r = pg.request.post(servidor + "/api/portal/drivers", data={"name": piloto, **PILOTO_OK}, headers={"X-CSRF": csrf})
        assert r.ok, r.text()


def test_cliente_cria_a_conta_poe_o_piloto_com_medidas_e_volta_a_entrar(servidor, navegador):
    pg = navegador.new_page(viewport={"width": 390, "height": 844})
    pg.erros_js = []
    pg.on("pageerror", lambda e: pg.erros_js.append(str(e)))
    pg.goto(servidor + "/portal")
    pg.locator(".login .pista").wait_for()                      # o login do cliente tem o desenho do login da equipe
    pg.get_by_role("link", name="Create an account").click()
    pg.get_by_label("Full name").fill("Ana Driver")
    pg.get_by_label("Date of birth").fill("1988-03-02")
    pg.get_by_label("Email").fill("ana.e2e@example.com")
    pg.get_by_label("Password").fill("pista-molhada-7")
    pg.get_by_label("Phone").fill("407 555 0101")
    pg.get_by_label("Street address").fill("100 Main St")
    pg.get_by_label("City").fill("Orlando")
    pg.get_by_role("textbox", name="State").fill("FL")
    pg.get_by_label("ZIP").fill("32809")
    pg.get_by_label("I accept the").check()
    pg.get_by_role("button", name="Create account").click()
    pg.wait_for_url("**/ops/portal/dashboard")
    pg.get_by_role("heading", name="Dashboard", level=1).wait_for()
    pg.get_by_role("link", name="Drivers", exact=True).click()
    pg.get_by_role("heading", name="Drivers", level=1).wait_for()
    # sem piloto ainda: o formulário já vem aberto, e as medidas são obrigatórias
    pg.get_by_label("Driver's full name").fill("Bia Driver")
    pg.get_by_label("Date of birth").fill("2015-06-01")
    pg.get_by_role("button", name="Save driver").click()
    assert "Please fill in" in pg.get_by_role("alert").inner_text()
    for rot, v in (("Height (in)", "50"), ("Weight (lb)", "70"), ("Chest (in)", "26"), ("Waist (in)", "24")):          # quadril é opcional
        pg.get_by_label(rot).fill(v)
    pg.get_by_label("Karting experience").fill("First year, Baby kart.")
    pg.get_by_text("More sizes").click()
    pg.get_by_label("Suit size").fill("130")
    pg.get_by_role("button", name="Save driver").click()
    pg.get_by_role("heading", name="Bia Driver", level=2).wait_for()
    assert pg.get_by_text("Suit size").is_visible() and pg.get_by_text("Measurements up to date").is_visible()
    assert pg.title() == "Drivers · URACE"
    pg.get_by_role("button", name="Sign out").click()
    pg.wait_for_url("**/ops/portal")
    pg.get_by_label("Email").fill("ana.e2e@example.com")
    pg.get_by_label("Password", exact=True).fill("pista-molhada-7")
    pg.get_by_role("button", name="Sign in").click()
    pg.get_by_role("heading", name="Bia Driver", level=3).wait_for()      # no dashboard
    assert not pg.erros_js, pg.erros_js
    # conta de cliente não abre o painel
    assert pg.request.get(servidor + "/api/clients").status == 401
    pg.close()


def test_qr_do_cliente_a_vista_na_area_do_cliente_e_no_card(servidor, navegador):
    """#165, dono 08/10: "o cliente sempre ali na conta dele tem o QR Code dele, não está aparecendo lá.
    Mesmo o QR Code do card do cliente lá no Command Center"."""
    cli = navegador.new_page(viewport={"width": 360, "height": 800})
    cli.erros_js = []
    cli.on("pageerror", lambda e: cli.erros_js.append(str(e)))
    cliente_pela_api(cli, servidor, "Rita QR", "rita.qr.e2e@example.com", piloto="Leo QR", ip="10.9.9.9")
    abrir(cli, servidor, "/portal/dashboard")
    cli.get_by_text("Leo QR's URACE QR appears here as soon as our team connects").wait_for()   # sem card: diz o porquê
    pid = cli.request.get(servidor + "/api/portal/me").json()["drivers"][0]["id"]
    adm = entrar(navegador, servidor)
    csrf = next(c["value"] for c in adm.context.cookies() if c["name"] == "cc_csrf")
    r = adm.request.post(servidor + f"/api/site/drivers/{pid}/criar-cliente", headers={"X-CSRF": csrf})
    assert r.ok, r.text()
    cid = r.json()["client_id"]
    abrir(cli, servidor, "/portal/dashboard")
    qr = cli.get_by_role("img", name="URACE QR of Leo QR")
    qr.wait_for()                                                            # aberto no painel, sem clicar em nada
    cli.wait_for_function("() => { const i = document.querySelector('.portal-qr img'); return i && i.complete && i.naturalWidth > 0 }")
    r = cli.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    assert not cli.erros_js, cli.erros_js
    abrir(adm, servidor, f"/clients/{cid}")
    adm.get_by_role("button", name="QR do balcão").click()
    dlg = adm.get_by_role("dialog", name="QR do balcão de Leo QR")
    dlg.get_by_role("img", name="QR do balcão de Leo QR").wait_for()
    adm.wait_for_function("() => { const i = document.querySelector('.qr-modal img'); return i && i.complete && i.naturalWidth > 0 }")
    assert dlg.get_by_role("link", name="Abrir no balcão").get_attribute("href").endswith(f"/balcao/{cid}")
    assert not adm.erros_js and not adm.erros_api, (adm.erros_js, adm.erros_api)
    cli.close(); adm.close()


def test_menor_de_idade_nao_abre_a_conta(servidor, navegador):
    pg = navegador.new_page()
    pg.goto(servidor + "/portal/signup")
    pg.get_by_label("Full name").fill("Teen Driver")
    pg.get_by_label("Date of birth").fill("2012-05-05")
    pg.get_by_label("Email").fill("teen.e2e@example.com")
    pg.get_by_label("Password").fill("pista-molhada-7")
    pg.get_by_label("I accept the").check()
    pg.get_by_role("button", name="Create account").click()
    pg.get_by_role("alert").wait_for()
    assert "18 or older" in pg.get_by_role("alert").inner_text() and "/portal/signup" in pg.url
    pg.close()


@pytest.mark.parametrize("largura", [360, 390])
def test_area_do_cliente_um_h1_e_sem_rolagem_lateral(servidor, navegador, largura):
    pg = navegador.new_page(viewport={"width": largura, "height": 800})
    problemas = []
    for rota in ROTAS_PORTAL:
        pg.goto(servidor + rota); pg.wait_for_load_state("networkidle")
        h1 = [t for n, t in _cabecalhos(pg) if n == 1]
        if len(h1) != 1:
            problemas.append(f"{rota}: {len(h1)} h1")
        r = pg.evaluate(_VAZA)
        if r["rola"] or r["culpados"]:
            problemas.append(f"{rota}: rola {r['culpados']}")
    pg.close()
    assert not problemas, "\n".join(problemas)


@pytest.mark.parametrize("largura", [360, 390])
def test_area_do_cliente_por_dentro_um_h1_e_sem_rolagem_lateral(servidor, navegador, largura):
    pg = navegador.new_page(viewport={"width": largura, "height": 800})
    cliente_pela_api(pg, servidor, "Dora Dentro", f"dora{largura}.e2e@example.com", piloto="Duda Dentro")
    problemas = []
    for rota in ROTAS_PORTAL_DENTRO:
        pg.goto(servidor + rota); pg.wait_for_load_state("networkidle")
        h1 = [t for n, t in _cabecalhos(pg) if n == 1]
        if len(h1) != 1:
            problemas.append(f"{rota}: {len(h1)} h1")
        r = pg.evaluate(_VAZA)
        if r["rola"] or r["culpados"]:
            problemas.append(f"{rota}: rola {r['culpados']}")
    pg.close()
    assert not problemas, "\n".join(problemas)



# ------------------------------------------------------------------ agenda (#41)
def test_gerente_abre_a_agenda_cliente_marca_e_equipe_confirma(servidor, navegador):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    # 1. gerente abre sábado de manhã pela tela
    g = entrar(navegador, servidor)
    abrir(g, servidor, "/site/disponibilidade")
    g.get_by_label("Sáb Manhã aberto").check()
    g.get_by_role("button", name="Salvar a semana").click()
    g.get_by_text("Semana salva").wait_for()
    # 1b. gerente cadastra o serviço e o preço pela tela (#50): sem serviço, ninguém marca
    abrir(g, servidor, "/site/servicos")
    g.get_by_text("o cliente não consegue marcar", exact=False).wait_for()
    g.get_by_label("Nome", exact=True).fill("Arrive and Drive")
    g.get_by_label("Preço (US$)").fill("719")
    g.get_by_role("button", name="Criar").click()
    g.get_by_text("Serviço criado").wait_for()
    # 2. cliente cria a conta pela API e marca pela tela
    c = navegador.new_page(viewport={"width": 390, "height": 844})
    cliente_pela_api(c, servidor, "Cleo Agenda", "cleo.e2e@example.com", piloto="Caio Agenda")
    c.goto(servidor + "/portal/book")
    sab = datetime.now(ZoneInfo("America/New_York")).date() + timedelta(days=3)
    while sab.weekday() != 5:
        sab += timedelta(days=1)
    rotulo = sab.strftime("%A, %B ") + str(sab.day)
    c.locator(".portal-cal-d.aberto").first.wait_for()          # o calendário carregou
    for _ in range(3):                              # o sábado pode estar no mês seguinte
        if c.get_by_role("gridcell", name=f"{rotulo}, available").count():
            break
        c.get_by_role("button", name="Next month").click()
    c.get_by_role("gridcell", name=f"{rotulo}, available").click()
    c.get_by_role("button", name="Morning").click()
    c.get_by_text("per driver").wait_for()                        # o preço aparece antes de marcar
    assert "$719.00" in c.locator(".portal-servicos").inner_text()
    c.get_by_role("button", name="Request session").click()
    c.get_by_text("Request sent!").wait_for()
    c.get_by_role("link", name="My sessions").first.click()
    c.get_by_text("Waiting for confirmation").wait_for()
    # 3. equipe vê em "Precisa de atenção" e confirma na agenda
    abrir(g, servidor, "/attention")
    g.get_by_text("sessão(ões) pedida(s) pelo site").first.wait_for()
    abrir(g, servidor, "/site")
    g.get_by_text("Cleo Agenda").first.wait_for()
    # #50 (dono, 06/10): a equipe ACEITA — cobra e pede a waiver; aqui não há QuickBooks nem card,
    # então fica escrito o que falta, e o gerente pode confirmar mesmo assim
    g.get_by_role("button", name="Aceitar").first.click()
    g.get_by_text("Aceita, mas falta resolver").wait_for()
    g.get_by_text("aceita · esperando pagamento e waiver").first.wait_for()
    c.reload()
    c.get_by_text("Accepted: waiting for payment and waiver").wait_for()
    g.get_by_role("button", name="Confirmar mesmo assim").first.click()
    g.get_by_text("Sessão confirmada.").wait_for()
    c.reload()
    c.get_by_text("Confirmed").wait_for()
    # #81: no Dashboard, a próxima sessão é escrita como em "My sessions" (com o horário) e
    # não vira cartão dentro do cartão — nem no visual 3D, que é o padrão
    c.goto(servidor + "/portal/dashboard")
    kpi = c.locator(".portal-kpi").first
    kpi.get_by_text("Confirmed").wait_for()
    assert kpi.locator(".card").count() == 0, "cartão dentro do cartão"
    assert "Morning · " in kpi.inner_text() and "AM" in kpi.inner_text(), kpi.inner_text()
    g.close(); c.close()


# ------------------------------------------------------------------ vínculo (#42)
def test_equipe_vincula_pela_sugestao_e_o_cliente_ve_o_historico(servidor, navegador):
    c = navegador.new_page(viewport={"width": 390, "height": 844})
    cliente_pela_api(c, servidor, "Carla Mendes", "carla@example.com")
    c.goto(servidor + "/portal/history")
    c.get_by_text("once our team connects your account").wait_for()
    g = entrar(navegador, servidor)
    abrir(g, servidor, "/site/contas")
    cartao = g.locator(".card", has_text="carla@example.com").first
    cartao.get_by_text("mesmo e-mail").wait_for()
    cartao.get_by_role("button", name="Vincular a este").click()
    g.get_by_role("button", name="Vincular", exact=True).click()
    g.get_by_text("Vinculado.").wait_for()
    c.reload()
    c.get_by_role("heading", name="Service history").wait_for()
    c.locator(".tbl .tr").first.wait_for()
    assert c.locator(".tbl .tr").count() >= 1, "o histórico do card aparece"
    g.close(); c.close()


# ------------------------------------------------------------------ telas do site interno (#52)
def test_bloqueio_recorrente_calendario_do_mes_e_criar_cliente_pela_conta(servidor, navegador):
    g = entrar(navegador, servidor)
    abrir(g, servidor, "/site/disponibilidade")
    g.get_by_role("heading", name="Calendário do mês").wait_for()
    assert g.locator(".site-cal-d").count() >= 28 and g.locator(".site-cal-d.fds").count() >= 8, "o mês inteiro, com fim de semana"
    g.get_by_role("radio", name="Toda semana").click()
    g.get_by_role("combobox", name="Dia da semana").select_option(label="toda segunda")
    g.get_by_label("Motivo").fill("sem aula")
    g.get_by_role("button", name="Bloquear").click()
    g.get_by_text("Bloqueado.").wait_for()
    g.get_by_text("recorrente").first.wait_for()
    assert "toda segunda" in g.locator(".tbl").inner_text()
    # conta de quem não está na base: cria o card e já vincula
    c = navegador.new_page(viewport={"width": 390, "height": 844})
    cliente_pela_api(c, servidor, "Eduardo Fillipe Resende", "eduardo.novo@example.com", piloto="Lucas Fillipe Resende")
    abrir(g, servidor, "/site/contas")
    cartao = g.locator(".card", has_text="eduardo.novo@example.com").first
    cartao.get_by_role("button", name="Criar cliente").click()
    g.get_by_role("button", name="Criar cliente", exact=True).last.click()
    g.get_by_text("Cliente criado e vinculado.").wait_for()
    g.close(); c.close()


def test_cinco_toques_no_u_abrem_o_login_da_equipe_e_ha_volta(servidor, navegador):
    """#74 (dono, 02/10): no app, a primeira tela é a do cliente; o Command Center fica
    escondido no "U". Quatro toques não fazem nada; o quinto abre o login da equipe."""
    pg = navegador.new_page(viewport={"width": 390, "height": 844})
    pg.goto(servidor + "/portal")
    u = pg.locator(".portal-login .mark-u")
    u.wait_for()
    for _ in range(4):
        u.click()
    assert "/portal" in pg.url, "quatro toques: continua no login do cliente"
    u.click()
    pg.wait_for_url("**/ops/login")
    pg.get_by_text("Acesso restrito").wait_for()
    pg.get_by_role("link", name="Área do cliente").click()
    pg.wait_for_url("**/ops/portal**")
    pg.close()


def test_equipe_ve_como_conectar_o_claude(servidor, navegador):
    """#77: o cartão está na tela Equipe, com o endereço do conector e o passo a passo."""
    pg = entrar(navegador, servidor)
    pg.goto(servidor + "/equipe")
    pg.get_by_role("heading", name="Conectar o Claude").wait_for()
    pg.get_by_role("button", name="Como conectar").click()
    pg.get_by_text("/ops/mcp").first.wait_for()
    pg.get_by_text("claude mcp add --transport http urace").wait_for()
    pg.close()


@pytest.mark.parametrize("largura", [360, 390])
def test_area_do_cliente_escreve_tudo_do_mesmo_jeito(servidor, navegador, largura):
    """#81 (dono, 04/10: "veja as formatações que estão fora de padrão e padronize"): nome
    comprido não quebra palavra por palavra, "Last session" igual nas duas telas, rede social
    com rótulo e todos os botões com a mesma letra."""
    pg = navegador.new_page(viewport={"width": largura, "height": 844})
    cliente_pela_api(pg, servidor, "Paula Padrao", f"paula{largura}.e2e@example.com")
    csrf = next(c["value"] for c in pg.context.cookies() if c["name"] == "cp_csrf")
    r = pg.request.post(servidor + "/api/portal/drivers", headers={"X-CSRF": csrf},
                        data={"name": "Gabriela Fernanda Albuquerque Montenegro", "social": "@gabi_kart", **PILOTO_OK})
    assert r.ok, r.text()
    pg.goto(servidor + "/portal/drivers"); pg.wait_for_load_state("networkidle")
    nome = pg.locator(".portal-piloto h2").first
    altura_linha = float(nome.evaluate("e => parseFloat(getComputedStyle(e).lineHeight) || 24"))
    assert nome.bounding_box()["height"] <= altura_linha * 2.2, "o nome quebrou palavra por palavra"
    cartao = pg.locator(".portal-piloto").first.inner_text()
    assert "Last session: none yet" in cartao and "Social: @gabi_kart" in cartao and "Client ID:" in cartao, cartao
    assert "last session none" not in cartao
    tamanhos = set(pg.eval_on_selector_all(".portal .btn", "els => els.map(e => getComputedStyle(e).fontSize)"))
    assert len(tamanhos) == 1, f"botões com letras diferentes: {tamanhos}"
    pg.goto(servidor + "/portal/dashboard"); pg.wait_for_load_state("networkidle")
    assert "Last session: none yet" in pg.locator(".portal-piloto").first.inner_text()
    assert pg.get_by_text("None yet", exact=True).count() == 1, "o cartão Last session diz o mesmo"
    tamanhos = set(pg.eval_on_selector_all(".portal .btn", "els => els.map(e => getComputedStyle(e).fontSize)"))
    assert len(tamanhos) == 1, f"botões com letras diferentes: {tamanhos}"
    pg.close()


def test_integracoes_mostra_o_dialpad_sem_a_chave(servidor, navegador):
    """#83 (dono, 05/10): ligou o Dialpad e o passo de conferir dizia "Integrações → Dialpad",
    que não existia. O cartão mostra se está ligado e o último evento; a chave do webhook nunca."""
    pg = entrar(navegador, servidor)
    abrir(pg, servidor, "/integrations")
    cartao = pg.locator(".card", has=pg.get_by_role("heading", name="Dialpad", exact=True))
    cartao.wait_for()
    texto = cartao.inner_text()
    assert "falta configurar" in texto and "DIALPAD_API_KEY" in texto, texto
    assert "key=" not in texto
    pg.close()


# ------------------------------------------------------------------ waiver nativa (#85)
def test_waiver_nativa_admin_liga_o_responsavel_assina_no_celular_e_a_equipe_ve(servidor, navegador):
    # 1. nasce desligada; o ADMIN liga pela tela (os modelos a semente já "importou")
    a = entrar(navegador, servidor, "italo@urace.us")
    abrir(a, servidor, "/site/waiver")
    a.get_by_text("desligada", exact=True).wait_for()
    a.get_by_role("button", name="Ligar", exact=True).click()
    a.get_by_role("dialog").get_by_role("button", name="Ligar", exact=True).click()
    a.get_by_text("Ligada: o cliente já vê").wait_for()
    # 2. o responsável de um piloto menor assina pelo celular
    c = navegador.new_page(viewport={"width": 360, "height": 800})
    c.erros_js = []
    c.on("pageerror", lambda e: c.erros_js.append(str(e)))
    cliente_pela_api(c, servidor, "Rita Waiver", "rita.e2e@example.com", piloto="Rafa Waiver")
    c.goto(servidor + "/portal/dashboard")
    c.get_by_role("link", name="Sign it online").click()
    c.get_by_role("heading", name="Sign the waiver", level=1).wait_for()
    # #107: o PDF de verdade, desenhado na tela; as caixas só se liberam depois de ler tudo
    tela = c.locator(".pdf-folha canvas").first
    tela.wait_for()
    assert c.get_by_label("I have read this waiver").is_disabled()
    c.wait_for_function("""() => { const t = document.querySelector('.pdf-folha canvas');
        if (!t) return false; const d = t.getContext('2d').getImageData(0, 0, t.width, t.height).data;
        for (let i = 0; i < d.length; i += 4) if (d[i] < 128) return true; return false }""")   # tinta: não é página em branco
    c.locator(".pdf-folha canvas").nth(2).wait_for()
    c.get_by_text(re.compile(r"Scroll through every page to continue: \d of 3 read")).wait_for()
    assert c.get_by_role("button", name="Sign the waiver").is_disabled()
    c.locator(".pdf-caixa").evaluate("e => e.scrollTo(0, e.scrollHeight)")      # pular direto para o fim não conta a do meio
    assert not c.get_by_text("All 3 pages read.").is_visible()
    c.locator(".pdf-caixa").evaluate("""async e => { for (let y = 0; y <= e.scrollHeight; y += 120) {
        e.scrollTo(0, y); await new Promise(ok => setTimeout(ok, 60)) } }""")   # rolar como gente, página por página
    c.get_by_text("All 3 pages read.").wait_for()
    assert c.get_by_label("I have read this waiver").is_enabled()
    c.get_by_text("Text version (for screen readers)").click()
    c.get_by_label("Waiver text").get_by_text("E2E TEST DOCUMENT").wait_for()   # o texto do modelo, para leitor de tela
    assert len([t for n, t in _cabecalhos(c) if n == 1]) == 1
    r = c.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    # #108: o e-mail da conta é confirmado por código (uma vez) e a assinatura pede um código novo
    assert c.get_by_role("button", name="Sign the waiver").is_disabled()
    c.get_by_role("button", name="Send the code to my email").click()
    c.get_by_label("Code sent to").wait_for()
    c.get_by_label("Code sent to").fill(codigo_do_email("rita.e2e@example.com"))
    c.get_by_role("button", name="Confirm email").click()
    c.get_by_role("button", name="Send me the signing code").click()
    c.get_by_label("Signing code sent to").wait_for()
    c.get_by_label("Signing code sent to").fill(codigo_do_email("rita.e2e@example.com"))
    c.get_by_role("button", name="Sign the waiver").click()
    assert "Check both boxes" in c.get_by_role("alert").inner_text()
    # #105: pelo menor, só pai ou mãe — "Other" explica e não deixa assinar
    c.get_by_label("Other (grandparent").check()
    c.get_by_text("Only a parent (mother or father) can sign").wait_for()
    assert c.get_by_role("button", name="Sign the waiver").is_disabled()
    c.get_by_label("Mother").check()
    c.get_by_label("I am the parent (natural guardian) of Rafa Waiver").check()
    c.get_by_label("I read and understand English").check()          # #119
    c.get_by_label("I have read this waiver").check()
    c.get_by_label("I agree to sign electronically").check()
    c.get_by_label("Your full name").fill("Rita Waiver")
    quadro = c.locator("canvas.portal-assinatura").bounding_box()
    c.mouse.move(quadro["x"] + 20, quadro["y"] + 110)
    c.mouse.down()
    for i in range(1, 13):
        c.mouse.move(quadro["x"] + 20 + i * 22, quadro["y"] + 110 - (i % 4) * 18, steps=2)
    c.mouse.up()
    c.get_by_role("button", name="Sign the waiver").click()
    c.get_by_text("Signed. The waiver for Rafa Waiver is valid until").wait_for()
    pdf = c.request.get(servidor.replace("/ops", "") + c.get_by_role("link", name="Download the signed PDF").get_attribute("href"))
    assert pdf.ok and pdf.body().startswith(b"%PDF")
    c.get_by_role("button", name="Back to Drivers").click()
    c.get_by_text("Waiver: signed").wait_for()
    # 2b. #104: um piloto ADULTO que não é a Rita assina a própria waiver — a Rita não assina por ele
    csrf = next(k["value"] for k in c.context.cookies() if k["name"] == "cp_csrf")
    r = c.request.post(servidor + "/api/portal/drivers", data={"name": "Beto Adulto", **PILOTO_OK, "birth_date": "1990-02-02"},
                       headers={"X-CSRF": csrf})
    assert r.ok, r.text()
    c.goto(servidor + "/portal/dashboard")
    c.get_by_text("Beto Adulto is an adult and signs their own waiver").wait_for()
    assert c.get_by_role("link", name="Sign it online").count() == 0
    assert not c.erros_js, c.erros_js
    # 3. a equipe vê a assinada na aba Waiver
    abrir(a, servidor, "/site/waiver")
    a.get_by_text("Rafa Waiver").wait_for()
    assert "parental · por Rita Waiver" in a.locator(".tr", has_text="Rafa Waiver").inner_text()
    a.close(); c.close()


# ------------------------------------------------------------------ balcão (#87)
def test_balcao_le_o_cliente_cobra_guarda_e_pergunta_antes_de_cobrar_peca_dele(servidor, navegador):
    pg = entrar(navegador, servidor, largura=360, altura=800)
    david = pg.request.get(servidor + "/api/clients?q=Pera").json()[0]["id"]
    # o QR do card, como o leitor o "digita"
    qr = pg.request.get(servidor + f"/api/balcao/cliente/{david}").json()["qr"]
    abrir(pg, servidor, "/balcao")
    assert len([t for n, t in _cabecalhos(pg) if n == 1]) == 1
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    campo = pg.get_by_label("Leia o QR do cliente")
    campo.fill(qr); campo.press("Enter")
    pg.wait_for_url(f"**/ops/balcao/{david}")
    pg.get_by_role("heading", name="David Pera", level=2).wait_for()
    # COBRAR: a peça entra na invoice de peças de hoje. Sem QuickBooks no e2e, a tela diz isso.
    campo = pg.get_by_label("Leia a peça (ou outro cliente)")
    campo.fill("7890000000017"); campo.press("Enter")
    pg.get_by_text("Front bumper (e2e): cobrada.").wait_for()
    pg.get_by_text("QuickBooks: QuickBooks não está conectado").wait_for()
    assert pg.get_by_role("button", name="Tentar de novo").count() == 1
    # GUARDAR: outra cor, outro aviso, vai para o estoque dele
    pg.get_by_role("radio", name="GUARDAR").click()
    pg.get_by_text("Modo GUARDAR: a peça vai para o estoque do cliente e NÃO é cobrada.").wait_for()
    campo.fill("7890000000017"); campo.press("Enter")
    pg.get_by_text("Front bumper (e2e): guardada para o cliente.").wait_for()
    pg.get_by_text("Guardado deste cliente com a gente").wait_for()
    # COBRAR uma peça que ele tem guardada pergunta antes
    pg.get_by_role("radio", name="COBRAR").click()
    campo.fill("7890000000017"); campo.press("Enter")
    pg.get_by_role("heading", name="Esta peça é do cliente?").wait_for()
    pg.get_by_role("button", name="Usar a dele (sem cobrar)").click()
    pg.get_by_text("Front bumper (e2e): usada do estoque do cliente.").wait_for()
    # código que ninguém conhece abre o cadastro
    campo.fill("1234509876"); campo.press("Enter")
    pg.get_by_role("heading", name="Código novo").wait_for()
    pg.get_by_role("button", name="Cancelar").click()
    # desfazer a primeira leitura (a cobrada)
    pg.get_by_role("button", name="Desfazer").last.click()
    pg.get_by_text("Desfeito.").wait_for()
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    assert not pg.erros_js and not pg.erros_api, (pg.erros_js, pg.erros_api)
    pg.close()


# ------------------------------------------------------------------ biblioteca (#88)
@pytest.mark.parametrize("largura", [360, 1280])
def test_biblioteca_do_gerente_com_os_historicos(servidor, navegador, largura):
    pg = entrar(navegador, servidor, largura=largura, altura=800)
    abrir(pg, servidor, "/biblioteca/historicos")
    assert len([t for n, t in _cabecalhos(pg) if n == 1]) == 1
    pg.get_by_text("Histórico de serviço — David Pera").wait_for()
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    pdf = pg.request.get(servidor + "/" + pg.get_by_role("link", name="PDF").first.get_attribute("href").split("/ops/", 1)[1])
    assert pdf.ok and pdf.body().startswith(b"%PDF")
    assert not pg.erros_js and not pg.erros_api, (pg.erros_js, pg.erros_api)
    pg.close()


def test_operador_nao_entra_na_biblioteca(servidor, navegador):
    pg = entrar(navegador, servidor, "op@urace.us")
    abrir(pg, servidor, "/biblioteca")
    pg.get_by_text("Esta área não é do seu acesso").wait_for()
    assert pg.get_by_role("link", name="Biblioteca").count() == 0, "nem aparece no menu"
    pg.close()


# ------------------------------------------------------------------ mecânico e checklists (#92)
def _png_pequeno(caminho):
    from PIL import Image
    Image.new("RGB", (60, 40), (40, 120, 200)).save(caminho, "PNG")
    return caminho


def test_meu_dia_do_mecanico_cabe_em_390(servidor, navegador):
    pg = entrar(navegador, servidor, "luis@urace.us", largura=390, altura=800)
    pg.get_by_role("heading", name="Meu dia", level=1).wait_for()
    pg.get_by_text("David Pera_Urace Daily_Arrive and Drive").wait_for()
    assert len([t for n, t in _cabecalhos(pg) if n == 1]) == 1
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    pg.close()


def test_mecanico_abre_no_meu_dia_preenche_o_checklist_com_foto(servidor, navegador, tmp_path):
    largura = 360
    pg = entrar(navegador, servidor, "luis@urace.us", largura=largura, altura=800)
    pg.get_by_role("heading", name="Meu dia", level=1).wait_for()
    assert len([t for n, t in _cabecalhos(pg) if n == 1]) == 1
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    servico = pg.locator(".card", has_text="David Pera_Urace Daily_Arrive and Drive")
    servico.get_by_role("button", name="Kart Checklist").click()
    pg.get_by_text("Kart Checklist · David Pera").wait_for()
    pg.get_by_role("checkbox", name="Check engine oil (change if needed)").check()
    pg.get_by_role("checkbox", name="Check chain tension (+/- 25mm)").check()
    pg.locator("input[aria-label='Subir foto: Check chain tension (+/- 25mm)']").set_input_files(_png_pequeno(tmp_path / f"f{largura}.png"))
    pg.get_by_text("Foto salva.").wait_for()
    pg.locator("img.ck-foto").first.wait_for()       # o aviso pode chegar antes do quadro redesenhar a foto (CI, 06/10)
    assert pg.locator("img.ck-foto").count() == 1
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    pg.get_by_role("button", name="Concluir checklist").click()
    pg.get_by_role("heading", name="Meu dia", level=1).wait_for()
    pg.locator(".card", has_text="David Pera_Urace Daily_Arrive and Drive").get_by_text("completo").wait_for()
    assert not pg.erros_js and not pg.erros_api, (pg.erros_js, pg.erros_api)
    pg.close()


@pytest.mark.parametrize("largura", [360, 390])
def test_mecanico_ve_a_semana_e_o_mes_no_celular_e_toca_no_dia(servidor, navegador, largura):
    """Dono, 06/10: no celular do mecânico, "uma visão do calendário mensal… continua tendo a
    visualização do dia… e também da semana". Tocar num dia abre o dia."""
    pg = entrar(navegador, servidor, "luis@urace.us", largura=largura, altura=800)
    pg.get_by_role("heading", name="Meu dia", level=1).wait_for()
    pg.get_by_role("button", name="Semana", exact=True).click()
    hoje = pg.locator(".md-semana-d.hoje")
    hoje.get_by_text("David Pera").first.wait_for()
    assert pg.locator(".md-semana-d").count() == 7
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    pg.get_by_role("button", name="Mês", exact=True).click()
    celula = pg.locator(".md-cal-d.hoje")
    celula.wait_for()
    assert "marcado" in celula.get_attribute("aria-label")
    caixa = celula.bounding_box()
    assert caixa["height"] >= 40, caixa
    assert len([t for n, t in _cabecalhos(pg) if n == 1]) == 1
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    pg.get_by_role("button", name="Próximo mês").click()
    pg.get_by_role("button", name="Mês anterior").click()
    pg.locator(".md-cal-d.hoje").click()                       # tocar no dia abre o dia, com os checklists
    pg.locator(".card.card-b", has_text="David Pera_Urace Daily_Arrive and Drive").get_by_role("button", name="Kart Checklist").wait_for()
    assert pg.get_by_role("button", name="Dia", exact=True).get_attribute("aria-pressed") == "true"
    assert not pg.erros_js and not pg.erros_api, (pg.erros_js, pg.erros_api)
    pg.close()


def test_mecanico_cadastra_peca_nova_no_balcao_com_foto_e_ela_aparece_no_estoque(servidor, navegador, tmp_path):
    """Dono, 06/10: ao adicionar a peça, o mecânico tira a foto na hora ou escolhe da galeria,
    e a foto aparece no estoque no lugar da caixinha."""
    pg = entrar(navegador, servidor, "luis@urace.us", largura=360, altura=800)
    pg.get_by_role("heading", name="Meu dia", level=1).wait_for()
    abrir(pg, servidor, "/balcao")
    campo = pg.get_by_label("Leia o QR do cliente")
    campo.fill("5550001112223"); campo.press("Enter")
    pg.get_by_role("heading", name="Código novo").wait_for()
    # dois caminhos: câmera na hora (capture) e galeria (sem capture, senão o Android esconde a galeria)
    assert pg.get_by_role("button", name="Tirar foto").is_visible() and pg.get_by_role("button", name="Escolher da galeria").is_visible()
    assert pg.locator("input[aria-label='Tirar foto da peça']").get_attribute("capture") == "environment"
    assert pg.locator("input[aria-label='Escolher foto da galeria']").get_attribute("capture") is None
    pg.get_by_label("Nome da peça nova").fill("Rear bumper (e2e foto)")
    pg.locator("input[aria-label='Escolher foto da galeria']").set_input_files(_png_pequeno(tmp_path / "peca.png"))
    pg.locator(".foto-peca img").wait_for()
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    pg.get_by_role("button", name="Salvar código").click()
    pg.get_by_text("Código e foto cadastrados.").wait_for()
    abrir(pg, servidor, "/estoque")
    card = pg.locator(".pcard", has_text="Rear bumper (e2e foto)")
    card.locator(".ph img").wait_for()
    assert card.locator(".ph img").evaluate("i => i.complete && i.naturalWidth > 0")
    # o "Adicionar peça" do estoque tem os mesmos dois caminhos
    pg.get_by_role("button", name="Adicionar peça").first.click()
    pg.get_by_role("heading", name="Adicionar peça").wait_for()
    assert pg.get_by_role("button", name="Escolher da galeria").is_visible()
    assert not pg.erros_js and not pg.erros_api, (pg.erros_js, pg.erros_api)
    pg.close()


def _video_do_qr(texto, caminho):
    """Um .y4m de 2 s com o QR parado no meio: a "câmera" falsa do Chromium mostra isto."""
    import io
    import segno
    from PIL import Image
    buf = io.BytesIO(); segno.make(texto, error="m").save(buf, kind="png", scale=8, border=4)
    qr = Image.open(buf).convert("RGB")
    quadro = Image.new("RGB", (640, 480), (255, 255, 255))
    qr.thumbnail((440, 440)); quadro.paste(qr, ((640 - qr.width) // 2, (480 - qr.height) // 2))
    y, u, v = quadro.convert("YCbCr").split()
    u, v = u.resize((320, 240)), v.resize((320, 240))
    with open(caminho, "wb") as f:
        f.write(b"YUV4MPEG2 W640 H480 F10:1 Ip A1:1 C420jpeg\n")
        for _ in range(20):
            f.write(b"FRAME\n" + y.tobytes() + u.tobytes() + v.tobytes())
    return caminho


def test_mecanico_exclui_peca_pela_lixeira_com_confirmacao(servidor, navegador):
    """Dono, 06/10: "um íconezinho de lixeira… dá só um pop-up de confirmação: deseja realmente
    excluir essa peça? E aí, só o sim ou não"."""
    pg = entrar(navegador, servidor, "luis@urace.us", largura=360, altura=800)
    csrf = next(c["value"] for c in pg.context.cookies() if c["name"] == "cc_csrf")
    r = pg.request.post(servidor + "/api/estoque/item", headers={"X-CSRF": csrf},
                        multipart={"name": "Peça de exemplo (e2e lixeira)", "category": "outros", "qty": "1"})
    assert r.ok, r.text()
    abrir(pg, servidor, "/estoque")
    card = pg.locator(".pcard-w", has_text="Peça de exemplo (e2e lixeira)")
    lixo = card.get_by_role("button", name="Excluir Peça de exemplo (e2e lixeira)")
    caixa = lixo.bounding_box()
    assert caixa["width"] >= 40 and caixa["height"] >= 40, caixa
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    lixo.click()
    pg.get_by_text("Deseja realmente excluir esta peça?").wait_for()
    pg.get_by_role("button", name="Não", exact=True).click()                   # não: nada muda
    assert card.count() == 1
    lixo.click()
    pg.get_by_role("button", name="Sim, excluir").click()
    pg.get_by_text("Peça de exemplo (e2e lixeira) excluída.").wait_for()
    card.wait_for(state="detached")
    assert not pg.erros_js and not pg.erros_api, (pg.erros_js, pg.erros_api)
    pg.close()


def test_mecanico_le_o_qr_do_cliente_pela_camera_e_abre_o_cliente(servidor, navegador, tmp_path):
    """Dono, 06/10: "quando colocar ler QR code, abrir a câmera para poder ler esse QR code" e já puxar
    o cliente. O Chromium de Linux não tem BarcodeDetector — é o mesmo caminho do iPhone (ZXing)."""
    adm = entrar(navegador, servidor)
    david = adm.request.get(servidor + "/api/clients?q=Pera").json()[0]["id"]
    qr = adm.request.get(servidor + f"/api/balcao/cliente/{david}").json()["qr"]
    adm.close()
    video = _video_do_qr(qr, tmp_path / "qr.y4m")
    b = navegador.browser_type.launch(executable_path=os.environ.get("PW_CHROMIUM") or None, args=[
        "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", f"--use-file-for-fake-video-capture={video}"])
    try:
        pg = entrar(b, servidor, "luis@urace.us", largura=390, altura=844)
        pg.get_by_role("heading", name="Meu dia", level=1).wait_for()
        abrir(pg, servidor, "/balcao")
        assert pg.evaluate("() => 'BarcodeDetector' in window") is False      # sem o leitor nativo, como no iPhone
        console = []
        pg.on("console", lambda m: console.append(f"{m.type}: {m.text}"[:300]))
        pg.get_by_role("button", name="Ler com a câmera").click()
        pg.get_by_role("heading", name="Apontar para o código").wait_for()
        try:
            pg.wait_for_url(f"**/ops/balcao/{david}", timeout=15000)
        except Exception:                      # diga o que a tela mostrava: o CI não guarda print
            raise AssertionError(f"a câmera não leu o QR em 15 s. url={pg.url}\ntela={pg.inner_text('body')[:1500]}\n"
                                 f"console={console[-15:]}\njs={pg.erros_js}\napi={pg.erros_api}")
        pg.get_by_role("heading", name="David Pera", level=2).wait_for()
        assert pg.get_by_role("heading", name="Apontar para o código").count() == 0   # a câmera fechou sozinha
        assert not pg.erros_js and not pg.erros_api, (pg.erros_js, pg.erros_api)
    finally:
        b.close()


def test_mecanico_so_ve_o_que_e_do_box(servidor, navegador):
    pg = entrar(navegador, servidor, "luis@urace.us")
    pg.get_by_role("heading", name="Meu dia", level=1).wait_for()
    menu = pg.get_by_role("navigation", name="Principal")
    for ve in ("Balcão", "Checklists", "Estoque", "Clientes", "Equipe"):
        assert menu.get_by_role("link", name=ve).count() == 1, ve
    for nao in ("Oportunidades", "Chat do Kommo", "QuickBooks", "Biblioteca", "AI Command", "Site público"):
        assert menu.get_by_role("link", name=nao).count() == 0, nao
    for rota in ("/sales", "/quickbooks", "/biblioteca", "/attention"):
        abrir(pg, servidor, rota)
        pg.get_by_text("Esta área não é do seu acesso").wait_for()
    abrir(pg, servidor, "/clients/1")
    assert pg.get_by_role("button", name="Editar").count() == 0, "o mecânico vê o card, não edita"
    assert pg.get_by_role("button", name="Invoices 🔒").count() == 0 and pg.get_by_role("button", name="Mensalidade e contrato").count() == 0
    assert not pg.erros_js and not [e for e in pg.erros_api if "/api/" in e], (pg.erros_js, pg.erros_api)
    pg.close()


def test_gerente_edita_o_modelo_do_checklist(servidor, navegador):
    pg = entrar(navegador, servidor)
    abrir(pg, servidor, "/checklists")
    card = pg.locator(".card.card-b", has=pg.get_by_role("heading", name="Mechanic Checklist", exact=True))
    card.get_by_role("button", name="Editar").click()
    card.get_by_label("Foto obrigatória no checklist").check()
    card.get_by_label("Novo item").fill("Check fire extinguisher")
    card.get_by_role("button", name="Adicionar").click()
    card.get_by_text("3 itens").wait_for()
    assert card.get_by_label("Foto obrigatória no checklist").is_checked()
    pg.close()


# ------------------------------------------------------------------ site novo (#148)
@pytest.mark.parametrize("largura", [360, 390])
def test_site_novo_um_h1_e_sem_rolagem_lateral(servidor, navegador, largura):
    site = servidor.removesuffix("/ops")
    pg = navegador.new_page(viewport={"width": largura, "height": 800})
    erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    problemas = []
    for rota in ("/", "/services/arrive-and-drive/"):
        pg.goto(site + rota); pg.wait_for_load_state("networkidle")
        h1 = [t for n, t in _cabecalhos(pg) if n == 1]
        if len(h1) != 1:
            problemas.append(f"{rota}: {len(h1)} h1")
        r = pg.evaluate(_VAZA)
        if r["rola"] or r["culpados"]:
            problemas.append(f"{rota}: rola {r['culpados']}")
        menor = pg.evaluate("""() => [...document.querySelectorAll('main a, main button, main label.kart, header a, header summary')]
            .filter(e => e.offsetParent !== null).map(e => [e.getBoundingClientRect().height, (e.innerText || e.getAttribute('aria-label') || '').trim().slice(0, 30)])
            .filter(([h]) => h < 40)""")
        if menor:
            problemas.append(f"{rota}: alvo de toque < 40 px {menor[:3]}")
    pg.close()
    assert not problemas, "\n".join(problemas)
    assert not erros, erros


def test_site_novo_escolhe_kart_dia_e_turno_e_a_area_do_cliente_abre_ja_marcada(servidor, navegador):
    """O visitante escolhe no site; entra na conta; a agenda da área do cliente abre com o kart,
    o dia e o turno escolhidos, e o pedido vai para a equipe como qualquer outro."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    site = servidor.removesuffix("/ops")
    g = entrar(navegador, servidor)
    abrir(g, servidor, "/site/disponibilidade")
    sabado = g.get_by_label("Sáb Manhã aberto")
    if not sabado.is_checked():                     # outro teste pode já ter aberto o sábado
        sabado.check()
        g.get_by_role("button", name="Salvar a semana").click()
        g.get_by_text("Semana salva").wait_for()
    abrir(g, servidor, "/site/servicos")
    g.get_by_label("Nome", exact=True).fill("Arrive and Drive 2-stroke")
    g.get_by_placeholder("719.00").fill("819")          # o campo do serviço novo (o de outro teste já existe)
    g.get_by_role("button", name="Criar").click()
    g.get_by_text("Serviço criado").wait_for()
    g.close()
    aux = navegador.new_page()
    cliente_pela_api(aux, servidor, "Sara Site", "sara.site.e2e@example.com", piloto="Sami Site", ip="10.1.48.1")
    aux.close()

    v = navegador.new_page(viewport={"width": 390, "height": 844})
    erros = []
    v.on("pageerror", lambda e: erros.append(str(e)))
    v.goto(site + "/services/arrive-and-drive/")
    v.locator("label.kart", has_text="2-stroke").click()
    # o primeiro dia aberto (só o sábado de manhã abre; o primeiro pode já ter lotado no outro teste)
    dia = v.locator(".agenda-dia.aberto").first
    dia.wait_for()                                                  # a agenda pública carregou
    rotulo = dia.get_attribute("aria-label").removesuffix(", available")
    hoje = datetime.now(ZoneInfo("America/New_York")).date()
    sab = next(d for d in (hoje + timedelta(days=n) for n in range(120)) if d.strftime("%A, %B ") + str(d.day) == rotulo)
    dia.click()
    v.get_by_role("button", name=re.compile("^Morning")).click()
    assert v.locator(".agenda-preco").inner_text() == "$819"
    v.get_by_role("link", name="Request this session").click()
    # sem conta aberta neste navegador: entra, e volta para a agenda com a escolha
    v.locator("#p-email").fill("sara.site.e2e@example.com")
    v.locator("#p-pw").fill("pista-molhada-7")
    v.get_by_role("button", name="Sign in").click()
    v.wait_for_url(re.compile(r"/ops/portal/book\?date=" + sab.isoformat()))
    v.get_by_role("heading", name="Book a session").wait_for()
    assert v.locator(".portal-cal-d.on").inner_text() == str(sab.day)
    assert v.get_by_role("button", name=re.compile("^Morning")).get_attribute("aria-pressed") == "true"
    assert v.get_by_role("radio", name=re.compile("Arrive and Drive 2-stroke")).is_checked(), "o kart escolheu o serviço"
    assert v.locator("textarea").input_value() == "Kart: 2-stroke"
    v.get_by_role("button", name="Request session").click()
    v.get_by_text("Request sent!").wait_for()
    v.close()
    assert not erros, erros


# ------------------------------------------------------------- Suits · Alpha Line (#153)
@pytest.mark.parametrize("largura", [360, 1280])
def test_suits_registra_o_pedido_anota_com_print_muda_a_etapa_e_grava_medida(servidor, navegador, tmp_path, largura):
    """Dono, 08/10: "registrar novo pedido ... Sempre dê a oportunidade ali de eu adicionar uma nota, às vezes um
    screenshot para IA poder entender, já avançar com aquilo ali no status que estiver"."""
    pg = entrar(navegador, servidor, largura=largura, altura=900)
    abrir(pg, servidor, "/suits")
    pg.get_by_role("heading", name="Suits · Alpha Line", level=1).wait_for()
    pg.get_by_role("button", name="Registrar novo pedido").click()
    dlg = pg.get_by_role("dialog", name="Registrar novo pedido")
    dlg.get_by_label("Cliente", exact=True).fill(f"Ryan Casner {largura}")
    dlg.get_by_label("E-mail", exact=True).fill("ryan@example.com")
    dlg.get_by_role("button", name="Registrar", exact=True).click()
    pg.get_by_role("heading", name=f"Ryan Casner {largura}", level=1).wait_for()
    assert re.search(r"/suits/\d+$", pg.url), pg.url
    pg.get_by_label("Nota", exact=True).fill("Cliente mandou as medidas no print")
    pg.locator(".suit-arquivo input[type=file]").set_input_files(_png_pequeno(tmp_path / f"print{largura}.png"))
    pg.get_by_label("Etapa", exact=True).select_option("awaiting_measurements")
    pg.get_by_label("Pedir à IA para seguir daqui").uncheck()
    pg.get_by_role("button", name="Salvar nota").click()
    pg.get_by_text("Nota salva.").wait_for()
    foto = pg.locator(".suit-tempo img.suit-img").first
    foto.wait_for(state="attached")                  # loading="lazy": só ganha tamanho quando aparece na tela
    foto.scroll_into_view_if_needed()
    pg.wait_for_function("() => { const i = document.querySelector('.suit-tempo img.suit-img'); return i && i.complete && i.naturalWidth > 0 }")
    pg.locator(".suit-etapas li.atual", has_text="Awaiting Measurements").wait_for()
    pg.get_by_role("button", name="Preencher").click()
    pg.get_by_label("1 – Head circumference").fill("59")
    pg.get_by_role("button", name="Salvar medidas").click()
    pg.locator(".suit-med", has_text="Head circumference").get_by_text("59 cm / 1'11\"").wait_for()
    assert "1 – Head circumference — 59 cm / 1'11\"" in pg.locator(".suit-pre").first.inner_text()   # já no e-mail ao fornecedor
    assert len([t for n, t in _cabecalhos(pg) if n == 1]) == 1
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    abrir(pg, servidor, "/suits")
    pg.get_by_role("link", name=re.compile(f"Ryan Casner {largura}")).wait_for()
    assert not pg.erros_js and not pg.erros_api, (pg.erros_js, pg.erros_api)
    pg.close()


def test_suits_novo_pedido_vincula_ao_cliente_e_puxa_o_cadastro(servidor, navegador):
    """#158, dono 08/10: "Todo lugar que a gente for fazer inserção manual, sempre coloque um para vincular
    com o cliente ... para poder vincular e puxar as informações pré-definidas ali daquele cliente"."""
    pg = entrar(navegador, servidor, largura=390, altura=900)
    abrir(pg, servidor, "/suits")
    pg.get_by_role("button", name="Registrar novo pedido").click()
    dlg = pg.get_by_role("dialog", name="Registrar novo pedido")
    dlg.get_by_label("Vincular ao cliente (puxa os dados do cadastro)").fill("Carla Mend")
    dlg.locator(".lpick-menu .opt", has_text="Théo Mendes").click()
    dlg.get_by_text("Puxado do cadastro").wait_for()
    assert dlg.get_by_label("Cliente", exact=True).input_value() == "Carla Mendes"
    assert dlg.get_by_label("E-mail", exact=True).input_value() == "carla@example.com"
    assert dlg.get_by_label("Piloto (se não for o cliente)").input_value() == "Théo Mendes"
    dlg.get_by_role("button", name="Registrar", exact=True).click()
    pg.get_by_role("heading", name="Carla Mendes", level=1).wait_for()
    pg.get_by_role("link", name=re.compile("Théo Mendes")).wait_for()          # o card do cliente, no pedido
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    assert not pg.erros_js and not pg.erros_api, (pg.erros_js, pg.erros_api)
    pg.close()


def test_cofre_abre_com_a_senha_guarda_e_mostra_so_para_o_acesso_livre(servidor, navegador):
    """#162, dono 08/10: "somente no acesso livre crie uma sessão de logins e senhas de onde fiquem
    seguras e consigam ser armazenadas por lá"."""
    pg = entrar(navegador, servidor, email="livre@urace.us", largura=360, altura=800)
    abrir(pg, servidor, "/cofre")
    pg.get_by_role("heading", name="Cofre", level=1).wait_for()
    assert pg.get_by_role("button", name="Novo login").count() == 0          # trancado: só depois da senha
    pg.get_by_label("Confirme a sua senha de login para abrir").fill(SENHA)
    pg.get_by_role("button", name="Abrir o cofre").click()
    pg.get_by_role("button", name="Novo login").click()
    dlg = pg.get_by_role("dialog", name="Novo login")
    dlg.get_by_label("Serviço").fill("WordPress urace.us")
    dlg.get_by_label("Usuário ou e-mail").fill("eduardo@urace.us")
    dlg.get_by_label("Senha", exact=True).fill("segredo-de-teste-9")
    dlg.get_by_role("button", name="Guardar").click()
    pg.get_by_role("heading", name="WordPress urace.us", level=3).wait_for()
    assert pg.get_by_text("segredo-de-teste-9").count() == 0                 # a senha não aparece sozinha
    pg.get_by_role("button", name="Ver senha").click()
    pg.get_by_text("segredo-de-teste-9").wait_for()
    assert len([t for n, t in _cabecalhos(pg) if n == 1]) == 1
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    pg.get_by_role("button", name="Trancar agora").click()
    pg.get_by_role("button", name="Abrir o cofre").wait_for()
    assert pg.get_by_text("segredo-de-teste-9").count() == 0
    assert not pg.erros_js and not pg.erros_api, (pg.erros_js, pg.erros_api)
    pg.close()
    pg = entrar(navegador, servidor, largura=390, altura=800)                # MANAGER comum: porta fechada
    abrir(pg, servidor, "/cofre")
    pg.get_by_text("O cofre é só da conta de acesso livre.").wait_for()
    assert pg.get_by_role("link", name="Cofre").count() == 0
    pg.close()


def test_suits_ponte_comeca_em_simulacao_e_guarda_o_designer(servidor, navegador):
    pg = entrar(navegador, servidor, largura=390, altura=900)
    abrir(pg, servidor, "/suits/ponte")
    pg.get_by_text("Em simulação:").wait_for()
    pg.get_by_label("E-mail do designer").fill("designer@example.com")
    pg.get_by_role("button", name="Salvar", exact=True).click()
    pg.get_by_text("Ponte salva.").wait_for()
    abrir(pg, servidor, "/suits/ponte")
    assert pg.get_by_label("E-mail do designer").input_value() == "designer@example.com"
    assert not pg.get_by_label("Envio automático (sem aprovação)").is_checked()
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    pg.close()


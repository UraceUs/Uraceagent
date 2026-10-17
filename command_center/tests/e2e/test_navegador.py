"""End-to-end no navegador de verdade (issue #16): servidor real, banco semeado e Chromium.

Roda só com CC_E2E=1 — precisa do frontend construído (`npm run build` em
command_center/web) e do Playwright para Python. No CI é um job próprio; localmente:

    (cd command_center/web && npm run build)
    CC_E2E=1 python3 -m pytest -q command_center/tests/e2e

Chromium fora do lugar padrão: PW_CHROMIUM=/opt/pw-browsers/chromium.
Nada aqui fala com Asana, Gmail, QuickBooks ou Kommo: o banco é descartável e o
servidor sobe sem sincronia (CC_AUTOSYNC=0) e sem credencial (URACE_ENV inexistente).
"""
import json
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
         "/pedidos", "/compras", "/planejamento", "/equipe", "/site", "/site/agendamentos", "/site/disponibilidade", "/site/servicos", "/site/cartoes",
         "/site/produtos", "/site/produtos/235", "/site/estoque", "/site/editor", "/site/editor/1", "/site/blog", "/site/blog/451",
         "/site/waiver", "/site/pedidos", "/site/deposito", "/balcao", "/biblioteca", "/biblioteca/historicos", "/meu-dia", "/checklists",
         "/suits", "/suits/leads", "/suits/fornecedores", "/suits/ponte", "/suits/modelo", "/como-usar",
         "/como-usar/geral", "/como-usar/vendas", "/como-usar/mecanicos"]


class _StripeFalso:
    """#174: um Stripe de mentira no próprio teste (nada sai da máquina). Cria a sessão, mostra uma
    "página do Checkout" e, no Pay, volta para o success_url como o de verdade."""
    def __init__(self):
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from urllib.parse import parse_qsl
        sessoes = self.sessoes = {}
        devolucoes = self.devolucoes = []                  # #317: as devoluções do security deposit
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, d):
                b = json.dumps(d).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

            def do_POST(self):
                campos = dict(parse_qsl(self.rfile.read(int(self.headers["Content-Length"])).decode()))
                if self.path == "/v1/refunds":
                    r = {"id": f"re_e2e{len(devolucoes) + 1:03d}", "object": "refund", "amount": int(campos["amount"]),
                         "payment_intent": campos["payment_intent"], "status": "succeeded",
                         "metadata": {k[9:-1]: v for k, v in campos.items() if k.startswith("metadata[")}}
                    devolucoes.append(r)
                    return self._json(r)
                sid = f"cs_test_e2e{len(sessoes) + 1:03d}"
                n = 0                                  # #236: o carrinho manda várias linhas (e a do depósito)
                while f"line_items[{n}][quantity]" in campos:
                    n += 1
                sessoes[sid] = {"id": sid, "url": f"{fake.origem}/pay/{sid}", "payment_status": "unpaid",
                                "client_reference_id": campos["client_reference_id"],
                                "nome": campos["line_items[0][price_data][product_data][name]"],
                                "linhas": [campos[f"line_items[{i}][price_data][product_data][name]"] for i in range(n)],
                                "amount_total": sum(int(campos[f"line_items[{i}][price_data][unit_amount]"]) * int(campos[f"line_items[{i}][quantity]"])
                                                    for i in range(n)),
                                "customer_email": campos.get("customer_email"),
                                "success_url": campos["success_url"], "cancel_url": campos["cancel_url"]}
                self._json(sessoes[sid])

            def do_GET(self):
                if self.path.startswith("/v1/refunds?"):
                    pi = parse_qsl(self.path.split("?", 1)[1]).__iter__()
                    pi = dict(pi).get("payment_intent")
                    return self._json({"object": "list", "data": [r for r in devolucoes if r["payment_intent"] == pi]})
                partes = self.path.strip("/").split("/")
                if partes[:3] == ["v1", "checkout", "sessions"]:
                    return self._json(sessoes[partes[3]])
                # o navegador pede /favicon.ico e afins: 404 em vez de estourar no log do teste
                if len(partes) < 2 or partes[1] not in sessoes:
                    self.send_response(404); self.send_header("Content-Length", "0")
                    return self.end_headers()
                s = sessoes[partes[1]]
                if len(partes) == 3:                   # /pay/<sid>/ok: pagou
                    s.update(payment_status="paid", payment_intent="pi_e2e",
                             customer_details={"email": s["customer_email"] or "lia.loja.e2e@example.com", "name": "Lia Loja", "phone": None})
                    self.send_response(303)
                    self.send_header("Location", s["success_url"].replace("{CHECKOUT_SESSION_ID}", s["id"]))
                    return self.end_headers()
                b = (f"<!doctype html><title>Stripe Checkout (test)</title><h1>{s['nome']}</h1>"
                     + "".join(f"<p class='linha'>{x}</p>" for x in s["linhas"])
                     + f"<p>Total US$ {s['amount_total'] / 100:.2f}</p><a href='/pay/{s['id']}/ok'>Pay</a>").encode()
                self.send_response(200); self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.origem = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()


STRIPE = None
WHSEC_E2E = "whsec_e2e_teste_245"                       # #245: o segredo do webhook, só deste teste


def webhook_stripe(site, sessao, tipo, eid, **extra):
    """#245: o evento do Stripe assinado como o de verdade, direto no webhook do servidor do teste."""
    import hashlib
    import hmac
    import json
    corpo = json.dumps({"id": eid, "type": tipo, "data": {"object": {**sessao, **extra}}}).encode()
    t = str(int(time.time()))
    sig = hmac.new(WHSEC_E2E.encode(), t.encode() + b"." + corpo, hashlib.sha256).hexdigest()
    req = urllib.request.Request(site + "/ops/api/stripe/webhook", data=corpo, method="POST",
                                 headers={"Stripe-Signature": f"t={t},v1={sig}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)["resultado"]
GOOGLE = None
GOOGLE_CRED = None
BANCO = None


def _porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    if not os.path.exists(DIST):
        pytest.fail("frontend não construído: rode `npm run build` em command_center/web")
    pasta = tmp_path_factory.mktemp("e2e")
    global EMAILS, STRIPE, GOOGLE, GOOGLE_CRED, BANCO
    EMAILS = str(pasta / "emails.jsonl")                 # #108: o e-mail do código vai para cá, nada sai da máquina
    BANCO = str(pasta / "e2e.sqlite")                    # #317: o teste do depósito põe um pedido pago direto no banco
    STRIPE = _StripeFalso()                              # #174: o Checkout é o falso, local
    from command_center.tests.google_falso import GoogleFalso
    GOOGLE = GoogleFalso()                               # #220: o login e o Calendar do Google são os falsos, locais
    GOOGLE_CRED = str(pasta / "google-web-credentials.json")   # começa SEM o arquivo: botão desligado
    porta = _porta_livre()
    env = dict(os.environ, CC_DB_PATH=str(pasta / "e2e.sqlite"), URACE_DIR=str(pasta), URACE_ENV="/nao/existe",
               CC_AUTOSYNC="0", PYTHONPATH=RAIZ, CC_EMAIL_FAKE=EMAILS,
               CC_SITE_HOSTS="127.0.0.1",              # #148: o site novo responde no endereço do teste
               CC_ACESSO_LIVRE="livre@urace.us",       # #162: a conta do cofre
               CC_BALCAO_HOSTS="localhost",           # #180: localhost faz o papel de parts.urace.us
               CC_BALCAO_URL=f"http://localhost:{porta}",   # #311: o botão do balcão leva para lá, já logado
               STRIPE_SECRET_KEY="sk_test_e2e", STRIPE_WEBHOOK_SECRET=WHSEC_E2E, STRIPE_API_BASE=STRIPE.origem, STRIPE_CHECKOUT_ORIGEM=STRIPE.origem,
               CC_COFRE_CHAVE="dGVzdGUtZTJlLWNoYXZlLWRvLWNvZnJlLTMyYnl0ZXM",  # 32 bytes de teste
               CC_GOOGLE_BASE=GOOGLE.origem, CC_GOOGLE_WEB_CREDENTIALS=GOOGLE_CRED,
               CC_GOOGLE_REDIRECT_URI=f"http://127.0.0.1:{porta}/ops/api/google/callback")
    subprocess.run([sys.executable, os.path.join(RAIZ, "command_center", "tests", "e2e", "semear.py")],
                   env=env, check=True, cwd=RAIZ, capture_output=True)
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
    STRIPE.srv.shutdown()
    GOOGLE.parar()


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
ROTAS_PORTAL = ["/portal", "/portal/signup", "/portal/reserve"]
ROTAS_PORTAL_DENTRO = ["/portal/dashboard", "/portal/book", "/portal/sessions", "/portal/drivers", "/portal/history", "/portal/account"]
CONTATO = {"phone": "(407) 555-0101", "address_line1": "100 Main St", "city": "Orlando", "state": "FL", "zip": "32809"}
PILOTO_OK = {"birth_date": "2014-05-01", "notes": "Two seasons in Mini kart.",
             "measures": {"height_in": 60, "weight_lb": 110, "chest_in": 30, "waist_in": 26, "hips_in": 30}}


def cliente_pela_api(pg, servidor, nome, email, piloto=None, ip=None, telefone=None):
    """Cria a conta (e um piloto completo) pela API, na sessão do navegador da página. `ip` faz o
    cadastro vir de outra conexão (o limite é de 10 cadastros por hora por conexão). `telefone`
    próprio quando o teste cria o card: o mesmo telefone em dois cards de contas diferentes trava."""
    r = pg.request.post(servidor + "/api/portal/signup", data={"name": nome, "email": email, "password": "pista-molhada-7",
                                                              "birth_date": "1980-01-01", "accept_terms": True,
                                                              **CONTATO, **({"phone": telefone} if telefone else {})},
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
    cliente_pela_api(cli, servidor, "Rita QR", "rita.qr.e2e@example.com", piloto="Leo QR", ip="10.9.9.9", telefone="(407) 555-0165")
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
    # 1b. #263: os quatro serviços do site nascem da migração, com os preços da Rate Card — ninguém
    # cadastra nada à mão. A tela de Serviços e preços é onde o gerente muda o preço (#50).
    abrir(g, servidor, "/site/servicos")
    g.get_by_role("heading", name="Serviços", exact=False).first.wait_for()
    do_painel = g.request.get(servidor + "/api/site/servicos").json()["servicos"]
    do_4t = [x for x in do_painel if x["site_kart"] == "4-stroke" and x["active"]]
    assert len(do_4t) == 1 and do_4t[0]["price"] == 719, do_painel
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
    # #253/#263: com vários serviços no painel e sem kart vindo do site, a pessoa escolhe — e só aí
    # o preço do escolhido aparece, antes de marcar
    c.get_by_role("radio", name=re.compile("Arrive and Drive 4-stroke")).check()
    c.get_by_text("per driver").wait_for()
    assert "$719.00" in c.locator(".portal-servicos").inner_text()
    # #314 (dono, 16/10): cliente novo no site com o Stripe ligado paga no carrinho — o botão é "Add to cart"
    assert c.get_by_role("button", name="Request session").count() == 0
    c.get_by_role("button", name="Add to cart").click()
    c.wait_for_url(re.compile(r"/cart/"))
    c.locator(".carrinho-linha").first.wait_for()
    # o Aceitar da equipe é o caminho da invoice (Stripe desligado, ou pedido que a equipe recebe): entra pela API
    csrf_c = {"X-CSRF": next(x["value"] for x in c.context.cookies() if x["name"] == "cp_csrf")}
    pid = c.request.get(servidor + "/api/portal/me").json()["drivers"][0]["id"]
    assert c.request.post(servidor + "/api/portal/bookings", headers=csrf_c,
                          data={"date": sab.isoformat(), "period": "manha", "service_id": do_4t[0]["id"], "driver_id": pid}).ok
    c.goto(servidor + "/portal/sessions")
    c.get_by_text("Waiting for confirmation").wait_for()
    # 3. equipe vê em "Precisa de atenção" e confirma na agenda
    abrir(g, servidor, "/attention")
    g.get_by_text("sessão(ões) pedida(s) pelo site").first.wait_for()
    abrir(g, servidor, "/site/agendamentos")
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


# ------------------------------------------------------------------ aluno recorrente: vários dias num pedido (#314)
# alvo de toque: altura E largura (a 360 px o dia do calendário tinha 38 px de largura)
_TOQUE_VARIOS = """() => [...document.querySelectorAll('.portal-varios-dia .btn, .portal-varios-atalhos .btn, .portal-cal-d.aberto')]
  .filter(el => el.offsetHeight < 40 || el.offsetWidth < 40)
  .map(el => `${el.className}=${el.offsetWidth}x${el.offsetHeight}px "${(el.textContent || '').trim().slice(0, 16)}"`).slice(0, 5)"""


def _aluno_recorrente(navegador, servidor, g, csrf, largura, quem="rita", ip=None, telefone=None):
    """Conta e piloto pela API do cliente; o card e a mensalidade (1 sessão por mês, extra de $689.23) pela equipe.
    O card fica em `c.card`."""
    c = navegador.new_page(viewport={"width": largura, "height": 844})
    c.erros_js = []
    c.on("pageerror", lambda e: c.erros_js.append(str(e)))
    cliente_pela_api(c, servidor, "Rita Recorrente", f"{quem}{largura}.e2e@example.com", piloto=f"Rafa Recorrente {quem} {largura}",
                     ip=ip or f"10.1.31.{largura % 250}", telefone=telefone or f"(407) 555-01{largura % 100:02d}")
    pid = c.request.get(servidor + "/api/portal/me").json()["drivers"][0]["id"]
    r = g.request.post(servidor + f"/api/site/drivers/{pid}/criar-cliente", headers=csrf)
    assert r.ok, r.text()
    card = r.json()["client_id"]
    r = g.request.patch(servidor + f"/api/clients/{card}/mensal", headers=csrf,
                        data={"monthly_amount": 2756.90, "monthly_sessions": 1, "extra_session_price": 689.23})
    assert r.ok, r.text()
    c.card = card
    return c


@pytest.mark.parametrize("largura", [360, 390])
def test_aluno_recorrente_marca_toda_quarta_num_pedido_so_no_celular(servidor, navegador, largura):
    """#314, dono 16/10: "se ele quiser marcar para quartas, toda quarta … ele consegue marcar isso tudo em um book".
    Cada dia diz só "Included in your plan" ou "Extra session · $689.23"; o resumo soma; um h1, nada rola para o lado,
    alvo de toque de 40 px."""
    g = entrar(navegador, servidor)
    csrf = {"X-CSRF": next(x["value"] for x in g.context.cookies() if x["name"] == "cc_csrf")}
    abrir_quarta = [{"weekday": 2, "period": p, "open": True, "capacity": 3} for p in ("manha", "tarde")]
    assert g.request.put(servidor + "/api/site/agenda/semana", headers=csrf, data=abrir_quarta).ok
    try:
        c = _aluno_recorrente(navegador, servidor, g, csrf, largura)
        c.goto(servidor + "/portal/book")
        c.get_by_role("heading", name="Book sessions", level=1).wait_for()
        assert c.get_by_text("2756").count() == 0, "o cliente não vê conta nem contador do pacote"
        c.get_by_role("radio", name=re.compile("Arrive and Drive 4-stroke")).check()
        c.get_by_role("button", name="Every Wed").click()
        dias = c.locator(".portal-varios-dia")
        dias.first.wait_for()
        n = dias.count()
        assert n >= 2, "as quartas abertas das próximas 4 semanas"
        c.get_by_text("Included in your plan").first.wait_for()
        c.get_by_text("Extra session · $689.23").first.wait_for()
        soma = c.locator(".reserva-total .soma")
        soma.wait_for()
        assert re.search(r"\d+ included · \d+ extras? ", soma.inner_text().replace("\n", " ")), soma.inner_text()
        texto = c.locator("main").inner_text() if c.locator("main").count() else c.inner_text("body")
        assert " of 1" not in texto and "used" not in texto.lower(), "o contador (usadas/total) não vai para o cliente"
        assert len([t for nv, t in _cabecalhos(c) if nv == 1]) == 1
        r = c.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        assert not c.evaluate(_TOQUE_VARIOS), c.evaluate(_TOQUE_VARIOS)
        # tirar um dia tira da lista e o resumo acompanha
        c.get_by_role("button", name=re.compile("^Remove ")).first.click()
        c.wait_for_function(f"() => document.querySelectorAll('.portal-varios-dia').length === {n - 1}")
        if largura == 390:
            c.get_by_role("button", name=re.compile(r"^Book \d+ session")).click()
            c.wait_for_url(re.compile(r"/ops/portal/sessions/group/\d+$"))
            c.get_by_role("heading", name="Almost there", level=1).wait_for()
            c.get_by_text("Request received").wait_for()             # venda automática desligada: a equipe aceita
            assert c.locator(".portal-varios-dia").count() == n - 1
            r = c.evaluate(_VAZA)
            assert not r["rola"] and not r["culpados"], r
            abrir(g, servidor, "/site/agendamentos")
            g.get_by_text(re.compile("pedido de vários dias #")).first.wait_for()
            g.get_by_text(re.compile(r"extra \$689\.23")).first.wait_for()
        else:
            # #314: o aluno recorrente não vê o carrinho (Stripe) na reserva do site: ele marca pelo plano
            c.goto(servidor + "/portal/reserve")
            c.get_by_role("heading", name="Book your session", level=1).wait_for()
            c.get_by_text("Academy student: sessions in your monthly plan are included").wait_for()
            assert c.get_by_role("button", name="Add to cart").count() == 0
            # decisões 1 e 2: nada de preço cheio, depósito ou total para o aluno — ele vê o rótulo de cada dia
            c.get_by_role("radio", name=re.compile("Arrive and Drive 4-stroke")).check()
            c.get_by_text("you see which one it is before booking").wait_for()
            passo1 = c.locator("section[aria-labelledby=r1]")
            assert passo1.locator(".reserva-total").count() == 0, "sem o total com depósito no passo 1"
            assert "$719" not in passo1.inner_text() and "Security deposit" not in passo1.inner_text(), passo1.inner_text()
        assert not c.erros_js, c.erros_js
        c.close()
    finally:
        g.request.put(servidor + "/api/site/agenda/semana", headers=csrf,
                      data=[{**x, "open": False} for x in abrir_quarta])
        g.close()


def test_aluno_no_ultimo_mes_do_plano_marca_o_mes_seguinte_como_sessao_avulsa(servidor, navegador):
    """#314: a recorrência termina neste mês (o último mês de um contrato, ou o plano de 1 mês do site). O mês seguinte
    aparece na agenda, mas o plano não cobre: o dia diz isso e tem "Book as a regular session", que leva ao fluxo de um
    dia e ao carrinho (Stripe ligado aqui). Também: sem o tipo de sessão, a tela diz o que falta; o atalho de fim de
    semana sem dia aberto avisa; a 360 px, nada rola para o lado e o toque tem 40 px."""
    import sqlite3
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    g = entrar(navegador, servidor)
    csrf = {"X-CSRF": next(x["value"] for x in g.context.cookies() if x["name"] == "cc_csrf")}
    abrir_quarta = [{"weekday": 2, "period": p, "open": True, "capacity": 3} for p in ("manha", "tarde")]
    assert g.request.put(servidor + "/api/site/agenda/semana", headers=csrf, data=abrir_quarta).ok
    try:
        c = _aluno_recorrente(navegador, servidor, g, csrf, 360, quem="ultimo", ip="10.1.32.7", telefone="(407) 555-0177")
        hoje = datetime.now(ZoneInfo("America/New_York")).date()
        este_mes = hoje.replace(day=1)
        con = sqlite3.connect(BANCO)
        con.execute("""INSERT INTO monthly_recurring (client_id, amount, item_id, months, start_on, end_on, status)
                       VALUES (?, 2756.90, '1', 6, ?, ?, 'active')""",
                    (c.card, (este_mes - timedelta(days=150)).replace(day=1).isoformat(), este_mes.isoformat()))
        con.commit()
        con.close()
        prox = (este_mes + timedelta(days=32)).replace(day=1)
        quarta = prox + timedelta(days=(2 - prox.weekday()) % 7)            # a 1ª quarta do mês seguinte (até 37 dias)
        c.goto(servidor + "/portal/book")
        c.get_by_role("heading", name="Book sessions", level=1).wait_for()
        assert c.locator(".portal-cal[role=group] [role=gridcell]").count() == 0, "o calendário é um grupo de botões"
        # o atalho do fim de semana sem dia aberto diz por que nada entrou (o sábado pode ter sido aberto por outro teste)
        abertos = {d["date"] for d in c.request.get(servidor + "/api/portal/availability").json()["dias"] if d["any_open"]}
        sab = hoje + timedelta(days=5 - hoje.weekday())
        if not {sab.isoformat(), (sab + timedelta(days=1)).isoformat()} & abertos:
            c.get_by_role("button", name="This weekend").click()
            c.get_by_text("No open days that weekend.").wait_for()
        rotulo = f"{quarta.strftime('%A, %B ')}{quarta.day}"
        for _ in range(3):
            if c.get_by_role("button", name=f"{rotulo}, available").count():
                break
            c.get_by_role("button", name="Next month").click()
        c.get_by_role("button", name=f"{rotulo}, available").click()
        assert c.get_by_role("button", name=f"{rotulo}, selected").get_attribute("aria-pressed") == "true"
        c.get_by_text("Pick the session type above to see what is included.").wait_for()
        c.get_by_role("radio", name=re.compile("Arrive and Drive 4-stroke")).check()
        c.get_by_text("Your monthly plan does not cover this date").wait_for()
        assert c.get_by_role("button", name=re.compile(r"^Book \d+ session")).is_disabled()
        r = c.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        assert not c.evaluate(_TOQUE_VARIOS), c.evaluate(_TOQUE_VARIOS)
        c.get_by_role("button", name="Book as a regular session").click()
        c.get_by_role("heading", name="Book a session", level=1).wait_for()
        c.get_by_text("Regular session: your monthly plan does not cover this date").wait_for()
        assert c.get_by_role("button", name="Morning").get_attribute("aria-pressed") == "true", "o dia e o turno vêm escolhidos"
        assert len([t for nv, t in _cabecalhos(c) if nv == 1]) == 1
        r = c.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        c.get_by_role("button", name="Add to cart").click()
        c.wait_for_url(re.compile(r"/cart/"))
        c.locator(".carrinho-linha").first.wait_for()
        c.wait_for_load_state("networkidle")
        assert "monthly plan" not in c.locator(".carrinho-linha").first.inner_text(), "o carrinho aceita o dia que o plano não cobre"
        assert not c.erros_js, c.erros_js
        c.close()
    finally:
        g.request.put(servidor + "/api/site/agenda/semana", headers=csrf,
                      data=[{**x, "open": False} for x in abrir_quarta])
        g.close()


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
    cliente_pela_api(c, servidor, "Eduardo Fillipe Resende", "eduardo.novo@example.com", piloto="Tomas Fillipe Resende")
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
    c.locator("canvas.portal-assinatura").scroll_into_view_if_needed()      # fora do menu fixo de baixo (celular)
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


# ------------------------------------------------------------------ convite da waiver por e-mail (#135)
def test_convite_da_waiver_sai_do_card_e_o_adulto_assina_pelo_link_sem_conta(servidor, navegador):
    """Dono, 14/10: "o e-mail que tiver no card vai receber isso". A equipe vê para quem vai, confirma
    e manda; o piloto adulto abre o link do e-mail (falso: nada sai da máquina), sem conta, e assina."""
    import json
    a = entrar(navegador, servidor, "italo@urace.us", largura=390, altura=844)
    csrf = {"X-CSRF": next(k["value"] for k in a.context.cookies() if k["name"] == "cc_csrf")}
    estava = a.request.get(servidor + "/api/site/waiver-nativa").json()["ligada"]
    assert a.request.post(servidor + "/api/site/waiver-nativa/ligar", data={"ligada": True}, headers=csrf).ok
    cid = a.request.post(servidor + "/api/clients", data={"name": "Gabi Convite", "pilot_dob": "1995-06-15",
                                                          "email": "gabi.convite.e2e@example.com"}, headers=csrf).json()["id"]
    sem = a.request.post(servidor + "/api/clients", data={"name": "Davi Sem Email", "pilot_dob": "1994-01-20"}, headers=csrf).json()["id"]
    # sem e-mail no card: o botão fica desligado e explica
    abrir(a, servidor, f"/clients/{sem}")
    a.get_by_role("button", name=re.compile(r"^Waivers \(")).click()
    assert a.get_by_role("button", name="Enviar convite da waiver por e-mail").is_disabled()
    a.get_by_text("O card não tem e-mail").wait_for()
    # com e-mail: mostra para quem vai, pede confirmação e manda
    abrir(a, servidor, f"/clients/{cid}")
    a.get_by_role("button", name="✉ Convite por e-mail").click()
    a.get_by_text("Vai para").wait_for()
    a.get_by_role("button", name="Enviar convite da waiver por e-mail").click()
    dlg = a.get_by_role("dialog")
    dlg.get_by_text("gabi.convite.e2e@example.com").wait_for()
    assert "assina a própria waiver (adult)" in dlg.inner_text()
    dlg.get_by_role("button", name="Enviar", exact=True).click()
    a.locator(".convite-waiver .chip", has_text="enviado").wait_for()
    assert len([t for n, t in _cabecalhos(a) if n == 1]) == 1
    r = a.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    # o e-mail (falso) leva o link pessoal; o cliente abre no celular, sem conta
    msg = [json.loads(x) for x in open(EMAILS, encoding="utf-8").read().splitlines() if "gabi.convite.e2e" in x][-1]
    assert msg["subject"] == "Sign your URACE waiver"
    link = re.search(r"https://my\.urace\.us/ops(/portal/invite/\S+)", msg["text"]).group(1)
    c = navegador.new_page(viewport={"width": 360, "height": 800})
    c.erros_js = []
    c.on("pageerror", lambda e: c.erros_js.append(str(e)))
    c.goto(servidor + link)
    c.get_by_role("heading", name="Sign the waiver", level=1).wait_for()
    c.get_by_text("You sign for yourself, Gabi Convite").wait_for()
    c.locator(".pdf-folha canvas").nth(2).wait_for()
    assert c.get_by_label("I have read this waiver").is_disabled()
    c.locator(".pdf-caixa").evaluate("""async e => { for (let y = 0; y <= e.scrollHeight; y += 120) {
        e.scrollTo(0, y); await new Promise(ok => setTimeout(ok, 60)) } }""")
    c.get_by_text("All 3 pages read.").wait_for()
    assert len([t for n, t in _cabecalhos(c) if n == 1]) == 1
    r = c.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    c.get_by_label("I read and understand English").check()
    c.get_by_label("I have read this waiver").check()
    c.get_by_label("I agree to sign electronically").check()
    c.get_by_label("Your full name").fill("Gabi Convite")
    c.locator("canvas.portal-assinatura").scroll_into_view_if_needed()
    quadro = c.locator("canvas.portal-assinatura").bounding_box()
    c.mouse.move(quadro["x"] + 20, quadro["y"] + 110)
    c.mouse.down()
    for i in range(1, 13):
        c.mouse.move(quadro["x"] + 20 + i * 22, quadro["y"] + 110 - (i % 4) * 18, steps=2)
    c.mouse.up()
    assert c.get_by_role("button", name="Sign the waiver").is_disabled(), "sem o código do e-mail não assina"
    c.get_by_role("button", name="Send me the signing code").click()
    c.get_by_label("Signing code sent to").wait_for()
    c.get_by_label("Signing code sent to").fill(codigo_do_email("gabi.convite.e2e@example.com"))
    c.get_by_role("button", name="Sign the waiver").click()
    c.get_by_text("Signed. The waiver for Gabi Convite is valid until").wait_for()
    pdf = c.request.get(servidor.replace("/ops", "") + c.get_by_role("link", name="Download the signed PDF").get_attribute("href"))
    assert pdf.ok and pdf.body().startswith(b"%PDF")
    # o link não vale duas vezes
    c.goto(servidor + link)
    c.get_by_text("This link was already used").wait_for()
    assert not c.erros_js, c.erros_js
    # no card: o convite assinado e a waiver junto com as outras
    abrir(a, servidor, f"/clients/{cid}")
    a.get_by_role("button", name=re.compile(r"^Waivers \(1\)")).click()
    a.locator(".convite-waiver .chip", has_text="assinado").wait_for()
    assert "área do cliente" in a.locator("table.tbl tr", has_text="gabi.convite.e2e@example.com").inner_text()
    if not estava:
        a.request.post(servidor + "/api/site/waiver-nativa/ligar", data={"ligada": False}, headers=csrf)
    a.close(); c.close()


# ------------------------------------------------------------------ balcão (#87)
def test_balcao_le_o_cliente_cobra_guarda_e_pergunta_antes_de_cobrar_peca_dele(servidor, navegador):
    pg = entrar(navegador, servidor, largura=360, altura=800)
    david = pg.request.get(servidor + "/api/clients?q=Pedalo").json()[0]["id"]
    # o QR do card, como o leitor o "digita"
    qr = pg.request.get(servidor + f"/api/balcao/cliente/{david}").json()["qr"]
    abrir(pg, servidor, "/balcao")
    assert len([t for n, t in _cabecalhos(pg) if n == 1]) == 1
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    campo = pg.get_by_label("Leia o QR do cliente")
    campo.fill(qr); campo.press("Enter")
    pg.wait_for_url(f"**/ops/balcao/{david}")
    pg.get_by_role("heading", name="David Pedalo", level=2).wait_for()
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
    pg.get_by_text("Histórico de serviço — David Pedalo").wait_for()
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
    pg.get_by_text("David Pedalo_Urace Daily_Arrive and Drive").wait_for()
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
    servico = pg.locator(".card", has_text="David Pedalo_Urace Daily_Arrive and Drive")
    servico.get_by_role("button", name="Kart Checklist").click()
    pg.get_by_text("Kart Checklist · David Pedalo").wait_for()
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
    pg.locator(".card", has_text="David Pedalo_Urace Daily_Arrive and Drive").get_by_text("completo").wait_for()
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
    hoje.get_by_text("David Pedalo").first.wait_for()
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
    pg.locator(".card.card-b", has_text="David Pedalo_Urace Daily_Arrive and Drive").get_by_role("button", name="Kart Checklist").wait_for()
    assert pg.get_by_role("button", name="Dia", exact=True).get_attribute("aria-pressed") == "true"
    assert not pg.erros_js and not pg.erros_api, (pg.erros_js, pg.erros_api)
    pg.close()


def test_calendario_em_cards_a_corrida_traz_um_card_por_cliente(servidor, navegador):
    """#233 (dono, 14/10): no mês, "separado ali os cards … corrida é um card de serviço geral com
    cards de serviços de cada cliente … um treino é um card de serviço daquele cliente"."""
    pg = entrar(navegador, servidor, "luis@urace.us", largura=1280, altura=900)
    pg.get_by_role("heading", name="Meu dia", level=1).wait_for()
    pg.get_by_role("button", name="Mês", exact=True).click()
    pg.locator(".md-cal-d.hoje .md-card.servico", has_text="David Pedalo").wait_for()   # o treino: card do cliente
    corrida = pg.locator(".md-cal-d .md-card.corrida", has_text="ROK")
    if not corrida.count():                                    # a corrida é daqui a 9 dias: pode cair no mês seguinte
        pg.get_by_role("button", name="Próximo mês").click()
    corrida.first.wait_for()
    assert corrida.first.locator(".md-card-sub .md-card.servico", has_text="Bryan Sapata").count() == 1
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    pg.get_by_role("button", name="Semana", exact=True).click()
    pg.locator(".md-semana-d.hoje .md-card.servico", has_text="David Pedalo").wait_for()
    corrida = pg.locator(".md-semana-d .md-card.corrida", has_text="ROK")
    for _ in range(2):
        if corrida.count():
            break
        pg.get_by_role("button", name="Próximo semana").click()
        pg.wait_for_timeout(400)
    corrida.first.locator(".md-card-sub .md-card.servico", has_text="Bryan Sapata").wait_for()
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
    david = adm.request.get(servidor + "/api/clients?q=Pedalo").json()[0]["id"]
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
        pg.get_by_role("heading", name="David Pedalo", level=2).wait_for()
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
    for nao in ("Oportunidades", "Chat do Kommo", "QuickBooks", "Biblioteca", "AI Command", "Painel do site", "Pedidos do site"):
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
    from command_center.vitrine import paginas_site
    post = paginas_site.dados("posts.json")["posts"][0]["slug"]
    produto = next(p for p in paginas_site.dados("produtos.json")["produtos"] if p["images"] and p["variations"])["slug"]
    for rota in ("/", "/services/arrive-and-drive/", "/services/", "/services/birthday-party/", "/academy/", "/pro-team/",
                 "/career/", "/about/", "/contact/", "/blog/", f"/blog/{post}/", "/store/", f"/store/p/{produto}/",
                 # #261: a loja com busca, filtro de preço e paginação — o formulário não pode estourar a largura
                 "/store/?s=magnesium+wheel&min_price=300&max_price=900&orderby=price", "/store/page/2/",
                 "/store/?s=zzzznaoexistenada", "/store/parts/",
                 # #252: o Arrive and Drive é o mais vendido e a descrição dele vem do WooCommerce com
                 # CSS do tema no meio do texto, que estourava a largura; o carrinho fecha o caminho
                 "/store/p/arrive-and-drive/", "/cart/"):
        pg.goto(site + rota); pg.wait_for_load_state("networkidle")
        h1 = [t for n, t in _cabecalhos(pg) if n == 1]
        if len(h1) != 1:
            problemas.append(f"{rota}: {len(h1)} h1")
        r = pg.evaluate(_VAZA)
        if r["rola"] or r["culpados"]:
            problemas.append(f"{rota}: rola {r['culpados']}")
        menor = pg.evaluate("""() => [...document.querySelectorAll('main a, main button, main label.kart, header a, header summary')]
            .filter(e => e.offsetParent !== null && !e.closest('p, li, dd, address, .post-corpo'))   // link no meio do texto não é botão
            .map(e => [e.getBoundingClientRect().height, (e.innerText || e.getAttribute('aria-label') || '').trim().slice(0, 30)])
            .filter(([h]) => h < 40)""")
        if menor:
            problemas.append(f"{rota}: alvo de toque < 40 px {menor[:3]}")
    pg.close()
    assert not problemas, "\n".join(problemas)
    assert not erros, erros


@pytest.mark.parametrize("largura", [390, 1280])
def test_site_programas_fundidos_no_celular_e_no_computador(servidor, navegador, largura):
    """#254 (dono, 15/10): na página de programas ficam o Arrive and Drive e a URACE Academy — o Kart
    School e o Professional Coaching somem dos cartões, o texto deles está em quem herdou, e o
    endereço antigo abre a página nova. No celular (390) e no computador (1280)."""
    site = servidor.removesuffix("/ops")
    pg = navegador.new_page(viewport={"width": largura, "height": 900})
    erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    problemas = []

    pg.goto(site + "/services/"); pg.wait_for_load_state("networkidle")
    cartoes = pg.locator(".servicos-grade .servico-card")
    nomes = [cartoes.nth(i).locator("strong").inner_text() for i in range(cartoes.count())]
    if nomes[:2] != ["Arrive and Drive", "URACE Academy"] or "Kart School" in nomes or "Professional Coaching" in nomes:
        problemas.append(f"cartões: {nomes}")

    # o endereço antigo leva à página que herdou, com o texto aproveitado
    for antigo, fim, trecho in (("/services/kart-school/", "/academy/", "Mentorship by winning drivers"),
                                ("/services/professional-coaching/", "/services/arrive-and-drive/", "Lead and Follow")):
        pg.goto(site + antigo); pg.wait_for_load_state("networkidle")
        if not pg.url.endswith(fim):
            problemas.append(f"{antigo}: foi para {pg.url}")
        if pg.get_by_text(trecho).count() < 1:
            problemas.append(f"{fim}: falta “{trecho}”")

    for rota in ("/services/", "/academy/", "/services/arrive-and-drive/"):
        pg.goto(site + rota); pg.wait_for_load_state("networkidle")
        h1 = [t for n, t in _cabecalhos(pg) if n == 1]
        if len(h1) != 1:
            problemas.append(f"{rota}: {len(h1)} h1")
        r = pg.evaluate(_VAZA)
        if r["rola"] or r["culpados"]:
            problemas.append(f"{rota}: rola {r['culpados']}")
    pg.close()
    assert not problemas, "\n".join(problemas)
    assert not erros, erros


@pytest.mark.parametrize("largura", [360, 390])
def test_site_novo_404_com_saida_no_celular(servidor, navegador, largura):
    """#252: quem cai num endereço que não existe vê quatro portas de saída, com alvo de toque de
    verdade, e a página não rola para o lado em 360 nem em 390 px."""
    site = servidor.removesuffix("/ops")
    pg = navegador.new_page(viewport={"width": largura, "height": 800})
    pg.goto(site + "/este-endereco-nao-existe/")
    pg.wait_for_load_state("networkidle")
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    alvos = pg.evaluate("""() => [...document.querySelectorAll('main .hero-acoes a')]
        .map(a => [a.getAttribute('href'), Math.round(a.getBoundingClientRect().height)])""")
    assert [h for h, _ in alvos] == ["/services/arrive-and-drive/", "/store/", "/services/", "/contact/"]
    assert all(altura >= 40 for _, altura in alvos), alvos
    assert len(pg.query_selector_all("h1")) == 1
    pg.close()


def test_esqueci_a_senha_no_celular_do_link_do_email_ate_entrar(servidor, navegador):
    """#168: quem esqueceu a senha pede o link na tela de entrar, abre o link do e-mail, escolhe a
    senha nova e já entra na conta — tudo no celular."""
    import json
    aux = navegador.new_page()
    cliente_pela_api(aux, servidor, "Olga Esqueci", "olga.esqueci.e2e@example.com", ip="10.1.68.1")
    aux.close()
    v = navegador.new_page(viewport={"width": 390, "height": 844}, extra_http_headers={"X-Forwarded-For": "10.1.68.2"})
    erros = []
    v.on("pageerror", lambda e: erros.append(str(e)))
    v.goto(servidor + "/portal")
    v.get_by_role("link", name="Forgot your password?").click()
    v.get_by_role("heading", name="Forgot your password?").wait_for()
    v.get_by_label("Email").fill("olga.esqueci.e2e@example.com")
    v.get_by_role("button", name="Send me the link").click()
    v.get_by_text("we just sent a link").wait_for()
    assert not v.evaluate(_VAZA)["rola"]
    linhas = [json.loads(x) for x in open(EMAILS, encoding="utf-8").read().splitlines()]
    texto = [x for x in linhas if x["to"] == "olga.esqueci.e2e@example.com"][-1]["text"]
    link = re.search(r"https?://\S+/ops/portal/reset\?token=[\w-]+", texto).group(0)
    assert link.startswith(servidor.removesuffix("/ops")), "o link aponta para o endereço que a pessoa usou"
    v.goto(link)
    v.get_by_role("heading", name="Choose a new password").wait_for()
    v.get_by_label("New password", exact=True).fill("pista-seca-2026")
    v.get_by_label("Repeat the new password").fill("pista-seca-2026")
    v.get_by_role("button", name="Save and sign in").click()
    v.wait_for_url(re.compile(r"/portal/dashboard"))             # entrou na conta
    assert v.get_by_text("Olga Esqueci").count() >= 1
    v.close()
    assert not erros, erros


def test_plano_da_academy_vendido_pelo_site_no_celular(servidor, navegador):
    """#169, dono 09/10: "Vender online já". O plano cadastrado no painel aparece na Academy com o botão
    que vende; o cliente entra, escolhe o piloto e vai para o acompanhamento (primeira mensalidade + waiver)."""
    site = servidor.removesuffix("/ops")
    adm = entrar(navegador, servidor, email="italo@urace.us")
    csrf = {"X-CSRF": next(c["value"] for c in adm.context.cookies() if c["name"] == "cc_csrf")}
    assert adm.request.patch(servidor + "/api/site/agenda/config", data={"auto_sell": True}, headers=csrf).ok
    if not adm.request.get(servidor + "/api/vitrine/planos").json()["plans"]:
        assert adm.request.post(servidor + "/api/site/servicos", data={"name": "Academy 3 months e2e", "price": 2688.43, "kind": "plan",
                                                                        "months": 3, "sessions_month": 4}, headers=csrf).ok
    # o painel mostra o plano com os campos dele
    abrir(adm, servidor, "/site/servicos")
    adm.get_by_text("plano de 3 meses, 4 sessões/mês").first.wait_for()
    try:
        _plano_no_celular(navegador, servidor, site)
    finally:
        # a venda automática volta a desligada: os testes seguintes do site esperam o pedido para a equipe
        adm.request.patch(servidor + "/api/site/agenda/config", data={"auto_sell": False}, headers=csrf)
        adm.close()


def _plano_no_celular(navegador, servidor, site):
    aux = navegador.new_page()
    cliente_pela_api(aux, servidor, "Paula Plano", "paula.plano.e2e@example.com", piloto="Pedro Plano", ip="10.1.69.1")
    aux.close()
    v = navegador.new_page(viewport={"width": 390, "height": 844}, extra_http_headers={"X-Forwarded-For": "10.1.69.2"})
    erros = []
    v.on("pageerror", lambda e: erros.append(str(e)))
    v.goto(site + "/academy/")
    assert v.get_by_text("Academy 3 months e2e").count() >= 1 and not v.evaluate(_VAZA)["rola"]
    v.get_by_role("link", name="Choose").first.click()
    v.get_by_role("heading", name="Join the plan", level=1).wait_for()
    v.get_by_text("First month, invoiced today").wait_for()
    v.get_by_role("button", name="Continue", exact=True).click()
    v.get_by_role("tab", name="I have an account").click()
    v.get_by_label("Email").fill("paula.plano.e2e@example.com")
    v.get_by_label("Password").fill("pista-molhada-7")
    v.get_by_role("button", name="Sign in and continue").click()
    v.get_by_text("Signed in as").wait_for()
    v.get_by_role("radio", name=re.compile("Pedro Plano")).wait_for()
    assert v.get_by_role("radio", name=re.compile("Pedro Plano")).is_checked(), "um piloto só: já vem escolhido"
    assert len([x for n, x in _cabecalhos(v) if n == 1]) == 1
    r = v.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    v.get_by_label("I agree to the").check()
    v.get_by_role("button", name=re.compile("^Join and pay")).click()
    v.wait_for_url(re.compile(r"/ops/portal/plans/\d+$"))
    v.get_by_role("heading", name="Almost there", level=1).wait_for()
    v.get_by_text("Plan chosen").wait_for()
    assert v.get_by_text(re.compile("Pay the first month|Paid")).count() >= 1
    assert v.get_by_text("Sign the waiver").count() == 1
    v.close()
    assert not erros, erros


def test_site_novo_contato_e_pedido_da_loja_chegam_em_vendas(servidor, navegador):
    """#164: o formulário do site (e o pedido da loja) vira oportunidade em Vendas, origem Site."""
    from command_center.vitrine import paginas_site
    site = servidor.removesuffix("/ops")
    v = navegador.new_page(viewport={"width": 390, "height": 844})
    erros = []
    v.on("pageerror", lambda e: erros.append(str(e)))
    v.goto(site + "/contact/?assunto=event")
    v.get_by_label("Your name").fill("Eva Evento")
    v.get_by_label("Email").fill("eva.evento.e2e@example.com")
    v.get_by_label("Message").fill("Birthday for 8 kids in November.")
    v.get_by_role("button", name="Send").click()
    v.get_by_text("Thank you! We got your message").wait_for()
    produto = next(p for p in paginas_site.dados("produtos.json")["produtos"] if p["images"] and p["variations"] and p["variations"][0].get("price"))
    v.goto(site + f"/store/p/{produto['slug']}/")
    v.get_by_text("Send an order request").click()          # #174: com o Stripe ligado, o pedido fica no "perguntar antes"
    v.get_by_label("Your name").fill("Eva Evento")
    v.get_by_label("Email").fill("eva.evento.e2e@example.com")
    v.get_by_role("button", name="Send order request").click()
    v.get_by_text("Thank you! We got your order request").wait_for()
    v.close()
    assert not erros, erros
    g = entrar(navegador, servidor)
    abrir(g, servidor, "/sales")
    g.get_by_text("Eva Evento").first.wait_for()
    assert g.get_by_text("Eva Evento").count() >= 2, "contato e pedido, os dois no funil"
    g.close()


def test_loja_compra_no_stripe_checkout_e_o_pedido_entra_pago_em_vendas(servidor, navegador):
    """#174: Buy now → página do Checkout (o Stripe falso) → Pay → obrigado com o pedido confirmado,
    e a venda GANHO em Vendas. No celular, nada rola para o lado."""
    from command_center.vitrine import paginas_site
    site = servidor.removesuffix("/ops")
    produto = next(p for p in paginas_site.dados("produtos.json")["produtos"]
                   if not p["variations"] and p["price"] and p["in_stock"] and p["images"])
    v = navegador.new_page(viewport={"width": 360, "height": 780})
    erros = []
    v.on("pageerror", lambda e: erros.append(str(e)))
    cliente_pela_api(v, servidor, "Lia Loja", "lia.loja.e2e@example.com", ip="10.1.74.1")   # #248: comprar pede a conta
    v.goto(site + f"/store/p/{produto['slug']}/")
    assert v.evaluate("document.documentElement.scrollWidth") <= 360
    v.get_by_label("Ship to me").check()
    v.get_by_label("Pick up at the track").check()
    v.get_by_role("button", name="Buy now").click()
    v.wait_for_url(STRIPE.origem + "/pay/**")
    assert v.title() == "Stripe Checkout (test)"
    assert f"US$ {produto['price']:.2f}" in v.content()
    v.get_by_role("link", name="Pay").click()
    v.get_by_role("heading", name="Payment confirmed", level=1).wait_for()   # #245: a página do pedido
    assert "/store/thanks/?session_id=cs_test_e2e" in v.url
    v.close()
    assert not erros, erros
    g = entrar(navegador, servidor)
    abrir(g, servidor, "/sales")
    g.get_by_text("Lia Loja").first.wait_for()
    # #310 (R1): a venda paga no site não mostra o Liberar (que cobrava de novo quem já pagou)
    vendas = [o for c in g.request.get(servidor + "/api/sales/board").json()["colunas"] for o in c["oportunidades"]]
    oid = next(o["id"] for o in vendas if o["name"] == "Lia Loja")
    abrir(g, servidor, f"/sales/{oid}")
    g.get_by_text("Pago no site (Stripe).").wait_for()
    assert g.get_by_role("button", name="Liberar invoice").count() == 0
    assert g.get_by_role("button", name="Cobrar só o depósito").count() == 0
    assert g.request.get(servidor + f"/api/sales/{oid}").json()["invoice"] == "enviada"
    assert not g.erros_js, g.erros_js
    g.close()


def test_o_botao_do_balcao_abre_o_parts_ja_logado(servidor, navegador):
    """#311 (dono, 16/10): o botão vermelho "tem que direcionar a pessoa para o … parts.urace.us, já
    logada com o mesmo login". O mecânico entra no painel (127.0.0.1), toca no botão e cai no balcão
    do celular (localhost faz o papel do parts) sem passar pelo login, com o nome dele à vista."""
    balcao = servidor.replace("127.0.0.1", "localhost")
    pg = entrar(navegador, servidor, email="luis@urace.us", largura=360, altura=740)
    abrir(pg, servidor, "/balcao")
    botao = pg.get_by_role("button", name="Abrir o balcão do celular")
    caixa = botao.bounding_box()
    assert caixa and caixa["height"] >= 40
    paginas = []
    pg.on("framenavigated", lambda f: paginas.append(f.url) if f == pg.main_frame else None)
    botao.click()
    pg.wait_for_url(balcao + "/**")
    pg.get_by_role("heading", name="Leia a peça").wait_for()
    assert not any("/login" in u for u in paginas), paginas
    assert "passe" not in pg.url, "o passe nunca aparece no endereço"
    assert pg.get_by_role("button", name="Sair da conta de Luis Barros").is_visible()
    assert pg.evaluate("document.documentElement.scrollWidth") <= 360
    assert pg.evaluate("fetch('/ops/api/clients').then(r => r.status)") == 403
    eu = pg.evaluate("fetch('/ops/api/auth/me').then(r => r.json())")
    assert (eu["email"], eu["so_balcao"]) == ("luis@urace.us", True)
    # voltar com o mesmo passe não entra de novo: o formulário reenviado cai no login, com o aviso
    pg.close()
    assert not pg.erros_js, pg.erros_js


def _espera_no_banco(con, sql, args, valor, tempo=10):
    """O botão desliga enquanto salva: ler o banco logo depois do clique corre com o PATCH (o CI pegou)."""
    fim = time.time() + tempo
    while time.time() < fim:
        if con.execute(sql, args).fetchone()[0] == valor:
            return True
        time.sleep(0.1)
    return False


def test_security_deposit_devolve_parte_pelo_stripe_e_muda_o_valor_cobrado(servidor, navegador):
    """#317 (dono, 16/10): "fazer o reembolso de cada security deposit e alterar o valor do security deposit para ser
    cobrado no site … só clicar no botão e fazer o refund … Sempre conseguindo alterar o valor que vai ser
    reembolsado." Um pedido pago no site com o depósito de US$ 400; o gerente, no celular, devolve US$ 150 pelo Stripe
    (o falso) e muda o depósito que o site cobra."""
    import sqlite3
    con = sqlite3.connect(BANCO)
    sid, preco = con.execute("SELECT id, price FROM booking_services WHERE site_kart='4-stroke'").fetchone()
    oid = con.execute("""INSERT INTO store_orders (kind, product_slug, product_name, quantity, unit_price, amount, delivery,
                           status, payment_intent, deposit, email, name, paid_at)
                         VALUES ('carrinho','carrinho','Arrive and Drive 4-stroke',1,?,?, 'retirada','pago','pi_e2e_dep',400,
                                 'dora.deposito.e2e@example.com','Dora Deposito','2026-10-15T15:00:00.000Z')""",
                      (preco + 400, preco + 400)).lastrowid
    con.execute("""INSERT INTO store_order_items (order_id, kind, name, quantity, unit_price, deposit, amount, service_id,
                     service_name, date, period, pilot_name)
                   VALUES (?, 'sessao', 'Arrive and Drive 4-stroke · Theo', 1, ?, 400, ?, ?, 'Arrive and Drive 4-stroke',
                           '2026-10-18', 'manha', 'Theo Deposito')""", (oid, preco, preco + 400, sid))
    con.commit()
    pg = entrar(navegador, servidor, largura=390, altura=844)
    abrir(pg, servidor, "/site/deposito")
    pg.get_by_role("heading", name="Security deposit", level=1).wait_for()
    cartao = pg.locator("article.cd", has_text="Dora Deposito")
    cartao.wait_for()
    assert "$400.00" in cartao.inner_text() and "Theo Deposito" in cartao.inner_text()
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    botao = cartao.get_by_role("button", name="Devolver pelo Stripe")
    assert botao.bounding_box()["height"] >= 40
    cartao.get_by_label("Valor a devolver (US$)").fill("150")
    cartao.get_by_label("Motivo (opcional)").fill("sem dano, menos a taxa da pista")
    botao.click()
    pg.get_by_role("dialog").get_by_role("button", name="Devolver").click()
    pg.get_by_text("Devolvido $150.00 pelo Stripe.").wait_for()
    cartao.get_by_text("Devolvido em parte").wait_for()
    assert "$250.00" in cartao.inner_text()
    assert [(d["amount"], d["payment_intent"]) for d in STRIPE.devolucoes] == [(15000, "pi_e2e_dep")]
    # mais do que o que segue retido não sai, nem chega ao Stripe
    cartao.get_by_label("Valor a devolver (US$)").fill("300")
    cartao.get_by_role("button", name="Devolver pelo Stripe").click()
    pg.get_by_text("O máximo que ainda dá para devolver é $250.00.").wait_for()
    assert len(STRIPE.devolucoes) == 1
    cartao.get_by_role("button", name="Conferir no Stripe").click()
    pg.get_by_text("Conferido: tudo igual ao Stripe.").wait_for()
    # o valor que o site cobra: US$ 1 para testar o checkout, e volta aos 400
    campo = pg.get_by_label("Depósito de Arrive and Drive 4-stroke (US$)")
    campo.fill("1")
    linha = pg.locator("li.dep-valor", has=campo)
    linha.get_by_role("button", name="Salvar").click()
    pg.get_by_text("Salvo. Vale para as próximas compras.").first.wait_for()
    assert _espera_no_banco(con, "SELECT deposit FROM booking_services WHERE id=?", (sid,), 1)
    assert linha.get_by_role("checkbox", name="Obrigatório").is_checked()
    campo.fill("400")
    linha.get_by_role("button", name="Salvar").click()
    assert _espera_no_banco(con, "SELECT deposit FROM booking_services WHERE id=?", (sid,), 400)
    # a caixa "Obrigatório" leva junto o valor digitado e ainda não salvo (revisão do #317)
    obr = linha.get_by_role("checkbox", name="Obrigatório")
    obr.click()                                   # a caixa salva na hora; o estado volta do servidor
    linha.locator("input[type=checkbox]:not(:checked):not([disabled])").wait_for()
    assert _espera_no_banco(con, "SELECT deposit_required FROM booking_services WHERE id=?", (sid,), 0)
    campo.fill("2")
    obr.click()
    linha.locator("input[type=checkbox]:checked:not([disabled])").wait_for()
    assert _espera_no_banco(con, "SELECT deposit * 10 + deposit_required FROM booking_services WHERE id=?", (sid,), 21)
    campo.fill("400")
    linha.get_by_role("button", name="Salvar").click()
    assert _espera_no_banco(con, "SELECT deposit FROM booking_services WHERE id=?", (sid,), 400)
    pg.set_viewport_size({"width": 360, "height": 740})
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    # o texto dos botões do cartão cabe neles (revisão: "Devolver pelo Stripe" passava da pílula a 360 px)
    assert pg.evaluate("""() => [...document.querySelectorAll('.cd-acoes .btn')].every(b => b.scrollWidth <= b.clientWidth + 1)""")
    con.close()
    pg.close()
    assert not pg.erros_js and not pg.erros_api, (pg.erros_js, pg.erros_api)


def test_servico_novo_ja_nasce_com_o_security_deposit_obrigatorio(servidor, navegador):
    """#317 (dono, 16/10): "eu coloquei um serviço, fui testar lá no checkout, e o serviço … ia permitir que eu fizesse
    o checkout … sem o security deposit … coloca em cada serviço … um checkbox para marcar que ele é obrigatório"."""
    pg = entrar(navegador, servidor, largura=390, altura=844)
    abrir(pg, servidor, "/site/servicos")
    novo = pg.locator("section", has=pg.get_by_role("heading", name="Novo serviço"))
    novo.wait_for()
    obr = novo.get_by_role("checkbox", name="Security deposit obrigatório")
    assert obr.is_checked(), "a sessão nova nasce com o depósito obrigatório"
    novo.get_by_label("Nome").fill("Teste de checkout e2e")
    novo.get_by_label("Preço (US$)").fill("10")
    criar = novo.get_by_role("button", name="Criar")
    assert criar.is_disabled(), "sem o valor do depósito, não cria"
    novo.get_by_label("Depósito por sessão (US$)").fill("1")
    criar.click()
    pg.get_by_text("Serviço criado: o cliente já vê.").wait_for()
    s = next(x for x in pg.request.get(servidor + "/api/site/servicos").json()["servicos"] if x["name"] == "Teste de checkout e2e")
    assert (s["deposit"], s["deposit_required"]) == (1, 1)
    r = pg.request.patch(servidor + f"/api/site/servicos/{s['id']}", data={"active": False},
                         headers={"X-CSRF": next(c["value"] for c in pg.context.cookies() if c["name"] == "cc_csrf")})
    assert r.ok, "desativa para não aparecer nos outros testes"
    pg.close()
    assert not pg.erros_js, pg.erros_js


def test_balcao_do_celular_peca_depois_piloto_e_o_gerente_confirma(servidor, navegador):
    """#180: em parts.urace.us (aqui, localhost) o mecânico entra e só existe o balcão. Lê a peça
    (o código digitado faz o papel da câmera), toca no piloto do dia e pronto; o gerente confirma
    na Revisão do painel. Uma mão: nada rola para o lado em 360 px, botões grandes."""
    balcao = servidor.replace("127.0.0.1", "localhost")
    v = navegador.new_page(viewport={"width": 360, "height": 740})
    erros = []
    v.on("pageerror", lambda e: erros.append(str(e)))
    v.goto(balcao + "/login")
    v.fill("#email", "luis@urace.us")
    v.fill("#pw", SENHA)
    v.keyboard.press("Enter")
    v.get_by_role("heading", name="Leia a peça").wait_for()
    assert v.evaluate("document.documentElement.scrollWidth") <= 360
    v.get_by_role("button", name="Código apagado? Digitar").click()
    v.get_by_label("Código da peça").fill("7890000000017")
    v.get_by_role("button", name="Ler", exact=True).click()
    v.get_by_role("heading", name="Front bumper (e2e)").wait_for()
    piloto = v.locator(".br-piloto", has_text="David Pedalo").first
    caixa = piloto.bounding_box()
    assert caixa and caixa["height"] >= 48, "alvo grande para o polegar"
    piloto.click()
    # #206 (dono, 13/10: "Escaneou, selecionou o cliente, já finaliza"): vai direto para a OS do David
    v.get_by_text("Peça adicionada").wait_for()
    v.get_by_text("Já está na invoice de David Pedalo", exact=False).wait_for()
    # #215 (dono, 13/10): "o nome do cliente fica como a maior coisa ali, e o nome da peça quase não
    # dá para ver" — a peça lida é o maior texto do painel, maior que o nome do cliente
    tam = v.evaluate("""() => [document.querySelector('.br-add-peca'), document.querySelector('.br-sessao-nome')]
        .map(e => parseFloat(getComputedStyle(e).fontSize))""")
    assert tam[0] > tam[1] * 1.4, tam
    assert v.get_by_role("heading", name="Front bumper (e2e)").count() == 1
    v.get_by_role("button", name="Encerrar").click()
    v.get_by_role("heading", name="Operação encerrada").wait_for()
    v.get_by_role("button", name="Próximo piloto").click()
    # nesse endereço, outra tela não abre e a API das outras seções responde 403
    v.goto(balcao + "/clients")
    v.get_by_role("heading", name="Leia a peça").wait_for()
    r = v.evaluate("fetch('/ops/api/clients').then(r => r.status)")
    assert r == 403
    v.close()
    assert not erros, erros

    # o gerente não confirma nada: a peça já está nas leituras do David, no balcão do painel
    g = entrar(navegador, servidor)
    ids = g.evaluate("fetch('/ops/api/clients?q=David%20Pedalo').then(r => r.json())")
    lista = ids["itens"] if isinstance(ids, dict) else ids
    cid = next(c["id"] for c in lista if (c.get("pilot_name") or "") == "David Pedalo")
    abrir(g, servidor, f"/balcao/{cid}")
    g.locator(".tbl .tr", has_text="Front bumper (e2e)").first.wait_for()
    assert not g.erros_js, g.erros_js
    g.close()


def test_balcao_finalizado_desfazer_no_celular_contar_o_estoque_e_abrir_cliente(servidor, navegador):
    """#206 (dono, 13/10: "finalizar o balcão de peças urgentemente"): a própria leitura pendente se
    desfaz a qualquer hora; a contagem rápida tira o estoque do zero; o cliente abre pelo nome."""
    balcao = servidor.replace("127.0.0.1", "localhost")
    v = navegador.new_page(viewport={"width": 360, "height": 740})
    v.goto(balcao + "/login")
    v.fill("#email", "luis@urace.us")
    v.fill("#pw", SENHA)
    v.keyboard.press("Enter")
    v.get_by_role("heading", name="Leia a peça").wait_for()
    v.get_by_role("button", name="Código apagado? Digitar").click()
    v.get_by_label("Código da peça").fill("7890000000017")
    v.get_by_role("button", name="Ler", exact=True).click()
    v.get_by_role("heading", name="Front bumper (e2e)").wait_for()
    v.locator(".br-piloto", has_text="David Pedalo").first.click()
    v.get_by_text("Peça adicionada").wait_for()
    # a operação fica aberta: a próxima peça já vai para o mesmo piloto, sem tocar de novo
    v.get_by_role("button", name="Código apagado? Digitar").click()
    v.get_by_label("Código da peça").fill("7890000000017")
    v.get_by_role("button", name="Ler", exact=True).click()
    v.get_by_role("heading", name="Nesta operação · 2").wait_for()
    assert v.evaluate("document.documentElement.scrollWidth") <= 360
    v.wait_for_timeout(6500)                                    # a confirmação da peça NÃO some (#215)
    v.get_by_text("Peça adicionada").wait_for()
    lista = v.locator(".br-op-l")
    antes = lista.get_by_role("listitem").count()
    botao = lista.get_by_role("button", name="Desfazer Front bumper (e2e)").first
    assert botao.bounding_box()["height"] >= 40
    botao.click()
    v.wait_for_function(f"() => document.querySelectorAll('.br-op-l li').length < {antes}")
    assert v.evaluate("document.documentElement.scrollWidth") <= 360
    v.get_by_role("button", name="Encerrar").click()
    v.get_by_role("heading", name="Operação encerrada").wait_for()
    v.close()

    g = entrar(navegador, servidor, largura=360, altura=900)
    abrir(g, servidor, "/balcao")
    g.get_by_role("heading", name="Contar o estoque").wait_for()
    g.get_by_role("button", name="Começar a contar").click()
    g.get_by_label("Leia a peça").fill("7890000000017")
    g.get_by_label("Leia a peça").press("Enter")
    g.get_by_text("Front bumper (e2e)", exact=True).first.wait_for()
    g.get_by_label("Quanto tem aqui agora").fill("4")
    g.get_by_role("button", name="Gravar contagem").click()
    g.get_by_text("Front bumper (e2e): 4 contado(s).").wait_for()
    r = g.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    g.get_by_role("button", name="Terminar").click()
    g.get_by_role("heading", name="Abrir um cliente").wait_for()
    assert len([t for n, t in _cabecalhos(g) if n == 1]) == 1
    assert not g.erros_js and not g.erros_api, (g.erros_js, g.erros_api)
    g.close()


def test_site_novo_escolhe_kart_dia_e_turno_e_a_area_do_cliente_abre_ja_marcada(servidor, navegador):
    """O visitante escolhe no site; entra na conta; a agenda da área do cliente abre com o kart,
    o dia e o turno escolhidos, e o cliente novo paga no carrinho do site (#314: Stripe ligado).

    #262: o site público já não oferece o "Continue to booking" — o caminho dele é o carrinho. A
    reserva da área do cliente (#164) continua existindo e é a daqui para frente, aberta pelo mesmo
    endereço com kart, dia e turno. #263: o serviço do 2-stroke vem da migração, com o preço do
    painel; ninguém cadastra nada à mão."""
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
    # #263: os quatro serviços do site vêm da migração, ligados ao kart pela chave "Kart do site"
    do_painel = g.request.get(servidor + "/api/site/servicos").json()["servicos"]
    do_2t = [x for x in do_painel if x["site_kart"] == "2-stroke" and x["active"]]
    assert len(do_2t) == 1 and do_2t[0]["price"] == 819, do_painel
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
    assert v.locator(".agenda-preco").inner_text() == "$819", "o preço é o do painel (#50)"
    assert v.locator(".agenda-carrinho").inner_text().strip().startswith("Add to cart"), "#262: um botão só"
    assert not v.locator(".agenda-ir").count(), '#262: o "Continue to booking" saiu do site público'
    # #164: a reserva da área do cliente abre na mesma identidade do site, com a escolha do site
    v.goto(f"{servidor}/portal/reserve?kart=2-stroke&date={sab.isoformat()}&period=manha")
    v.get_by_role("heading", name="Book your session", level=1).wait_for()
    assert v.get_by_role("radio", name=re.compile("Arrive and Drive 2-stroke")).is_checked(), "o kart escolheu o serviço"
    assert v.get_by_role("button", name=re.compile("^Morning")).get_attribute("aria-pressed") == "true"
    v.get_by_role("button", name="Continue", exact=True).click()
    v.get_by_role("tab", name="I have an account").click()
    v.get_by_label("Email").fill("sara.site.e2e@example.com")
    v.get_by_label("Password").fill("pista-molhada-7")
    v.get_by_role("button", name="Sign in and continue").click()
    v.get_by_text("Signed in as").wait_for()
    assert v.get_by_role("radio", name=re.compile("Sami Site")).is_checked(), "um piloto só: já vem escolhido"
    assert v.locator("textarea").input_value() == "Kart: 2-stroke"
    v.get_by_label("I agree to the").check()
    # #314 (dono, 16/10): cliente novo, Stripe ligado — paga no carrinho do site, com o piloto já escolhido
    assert v.get_by_role("button", name="Request this session").count() == 0
    v.get_by_role("button", name=re.compile(r"^Add to cart · \$")).click()
    v.wait_for_url(re.compile(r"/cart/"))
    v.locator(".carrinho-linha").first.wait_for()
    assert "2-stroke" in v.locator(".carrinho-linhas").inner_text()
    v.close()
    assert not erros, erros


def test_reserva_do_site_cliente_novo_cria_a_conta_poe_o_piloto_e_vai_para_o_pagamento(servidor, navegador):
    """#164, dono 08/10: "a pessoa vai marcar o horário, o dia e o valor ... ou ela loga ou ela cria a conta
    dela ... daí ela vai para a etapa de compra ... Um site totalmente automático que venda sozinho"."""
    site = servidor.removesuffix("/ops")
    adm = entrar(navegador, servidor, email="italo@urace.us")
    csrf = {"X-CSRF": next(c["value"] for c in adm.context.cookies() if c["name"] == "cc_csrf")}
    assert adm.request.patch(servidor + "/api/site/agenda/config", data={"auto_sell": True}, headers=csrf).ok
    # #263: os serviços do site vêm da migração; aqui só se garante que há algum ativo (outro teste
    # pode ter desligado e religado) — nada é cadastrado à mão
    assert adm.request.get(servidor + "/api/vitrine/servicos").json()["services"], "a migração semeia os 4 karts (#263)"
    abrir(adm, servidor, "/site/disponibilidade")
    sabado = adm.get_by_label("Sáb Manhã aberto")
    if not sabado.is_checked():
        sabado.check()
        adm.get_by_role("button", name="Salvar a semana").click()
        adm.get_by_text("Semana salva").wait_for()
    try:
        # IP próprio: o cadastro tem limite por IP/hora, e os outros testes já criaram contas pelo 127.0.0.1
        v = navegador.new_page(viewport={"width": 360, "height": 800}, extra_http_headers={"X-Forwarded-For": "10.1.64.1"})
        erros = []
        v.on("pageerror", lambda e: erros.append(str(e)))
        v.goto(site + "/services/arrive-and-drive/?utm_source=instagram&utm_campaign=outubro")
        dia = v.locator(".agenda-dia.aberto").first
        dia.wait_for()
        rotulo = dia.get_attribute("aria-label").removesuffix(", available")
        dia.click()
        v.get_by_role("button", name=re.compile("^Morning")).click()
        # #262: um botão só, e ele leva ao carrinho levando a campanha de onde a pessoa veio
        assert not v.locator(".agenda-ir").count(), 'o "Continue to booking" saiu'
        assert v.locator(".agenda-carrinho").inner_text().strip().startswith("Add to cart")
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        hoje = datetime.now(ZoneInfo("America/New_York")).date()
        sab = next(d for d in (hoje + timedelta(days=n) for n in range(120))
                   if d.strftime("%A, %B ") + str(d.day) == rotulo)
        # a reserva da área do cliente (#164) continua sendo o caminho desta prova
        v.goto(f"{servidor}/portal/reserve?kart=4-stroke&date={sab.isoformat()}&period=manha"
               "&utm_source=instagram&utm_campaign=outubro")
        v.get_by_role("heading", name="Book your session", level=1).wait_for()
        # #263: o kart do site escolhe o serviço pela chave, sem a pessoa marcar nada
        assert v.get_by_role("radio", name=re.compile("Arrive and Drive 4-stroke")).is_checked()
        v.get_by_role("button", name="Continue", exact=True).click()
        # 2 · conta nova sem sair da reserva
        v.get_by_label("Full name").fill("Nina Nova")
        v.get_by_label("Date of birth").fill("1984-02-10")
        v.get_by_label("Email").fill("nina.nova.e2e@example.com")
        v.get_by_label("Password").fill("pista-molhada-7")
        v.get_by_label("Phone").fill("407 555 0188")
        v.get_by_label("Street address").fill("200 Lake St")
        v.get_by_label("City").fill("Orlando")
        v.get_by_role("textbox", name="State").fill("FL")
        v.get_by_label("ZIP").fill("32824")
        v.get_by_label("I accept the").check()
        v.get_by_role("button", name="Create account and continue").click()
        v.get_by_text("Signed in as").wait_for()
        # 3 · o piloto (sem nenhum ainda: o formulário já vem aberto)
        v.get_by_label("Driver's full name").fill("Theo Nova")
        v.get_by_label("Date of birth").fill("2013-07-01")
        for rot, val in (("Height (in)", "56"), ("Weight (lb)", "85"), ("Chest (in)", "28"), ("Waist (in)", "25")):
            v.get_by_label(rot).fill(val)
        v.get_by_label("Karting experience").fill("First time")
        v.get_by_role("button", name="Save driver").click()
        v.get_by_role("radio", name=re.compile("Theo Nova")).wait_for()
        assert v.get_by_role("radio", name=re.compile("Theo Nova")).is_checked()
        # 4 · revisar e pagar
        assert len([t for n, t in _cabecalhos(v) if n == 1]) == 1
        r = v.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        v.get_by_label("I agree to the").check()
        # #314 (dono, 16/10): "cliente novo, que não for do Kart School, ele vai pagar pelo Stripe" — com o Stripe
        # ligado, o pagamento é o do carrinho (sem ele, a invoice do QuickBooks continua: test_venda_site)
        assert v.get_by_role("button", name=re.compile("^Book and pay")).count() == 0
        v.get_by_role("button", name=re.compile(r"^Add to cart · \$")).click()
        v.wait_for_url(re.compile(r"/cart/"))
        v.locator(".carrinho-linha").first.wait_for()
        assert "4-stroke" in v.locator(".carrinho-linhas").inner_text()
        r = v.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        assert not erros, erros
        v.close()
    finally:
        adm.request.patch(servidor + "/api/site/agenda/config", data={"auto_sell": False}, headers=csrf)
        adm.close()


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
    dlg.get_by_label("Cliente", exact=True).fill(f"Ryan Capner {largura}")
    dlg.get_by_label("E-mail", exact=True).fill("ryan@example.com")
    dlg.get_by_role("button", name="Registrar", exact=True).click()
    pg.get_by_role("heading", name=f"Ryan Capner {largura}", level=1).wait_for()
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
    # já no e-mail ao fornecedor (a prévia é recalculada logo depois da lista das medidas: esperar por ela)
    pg.locator(".suit-pre").first.get_by_text("1 – Head circumference — 59 cm / 1'11\"").wait_for()
    assert len([t for n, t in _cabecalhos(pg) if n == 1]) == 1
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    abrir(pg, servidor, "/suits")
    pg.get_by_role("link", name=re.compile(f"Ryan Capner {largura}")).wait_for()
    assert not pg.erros_js and not pg.erros_api, (pg.erros_js, pg.erros_api)
    pg.close()


@pytest.mark.parametrize("largura", [360, 1280])
def test_suits_descarta_o_que_nao_e_pedido_e_restaura(servidor, navegador, largura):
    """#195 (dono, 13/10): "nenhum desse aí foi e-mail de suit … cessa isso, limpa esses daí"."""
    pg = entrar(navegador, servidor, largura=largura, altura=900)
    abrir(pg, servidor, "/suits")
    pg.get_by_role("button", name="Registrar novo pedido").click()
    dlg = pg.get_by_role("dialog", name="Registrar novo pedido")
    dlg.get_by_label("Cliente", exact=True).fill(f"OpenAI {largura}")
    dlg.get_by_role("button", name="Registrar", exact=True).click()
    pg.get_by_role("heading", name=f"OpenAI {largura}", level=1).wait_for()
    # #198: a chave "IA neste pedido" — desliga, some o "Pedir à IA" da nota, liga de novo
    chave = pg.get_by_role("switch", name=re.compile("IA neste pedido"))
    assert chave.get_attribute("aria-checked") == "true" and pg.get_by_label("Pedir à IA para seguir daqui").count() == 1
    chave.click()
    pg.get_by_text("IA desligada neste pedido: o que chegar por e-mail fica para a equipe.").wait_for()
    pg.wait_for_function("() => document.querySelector('[role=switch]').getAttribute('aria-checked') === 'false'")
    assert pg.get_by_label("Pedir à IA para seguir daqui").count() == 0
    assert chave.bounding_box()["height"] >= 40
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    chave.click()
    pg.wait_for_function("() => document.querySelector('[role=switch]').getAttribute('aria-checked') === 'true'")
    pg.get_by_role("button", name="Não é pedido de suit").click()
    dlg = pg.get_by_role("dialog", name=re.compile("Descartar o pedido"))
    dlg.get_by_label("Por quê (opcional)").fill("fatura da OpenAI")
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    dlg.get_by_role("button", name="Descartar", exact=True).click()
    pg.get_by_text(re.compile("Descartado em")).wait_for()
    pg.get_by_text("fatura da OpenAI").first.wait_for()
    abrir(pg, servidor, "/suits")
    pg.get_by_role("heading", name="Em andamento", level=2).wait_for()
    pg.wait_for_load_state("networkidle")
    assert pg.get_by_role("link", name=re.compile(f"OpenAI {largura}")).count() == 0, "saiu de Em andamento"
    pg.get_by_role("button", name="Descartados").click()
    pg.get_by_role("link", name=re.compile(f"OpenAI {largura}")).click()
    pg.get_by_role("button", name="Restaurar o pedido").click()
    pg.get_by_role("button", name="Não é pedido de suit").wait_for()
    assert len([t for n, t in _cabecalhos(pg) if n == 1]) == 1
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
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


# ------------------------------------------------------------- idioma (#177)
@pytest.mark.parametrize("largura", [390, 1280])
def test_bandeiras_trocam_o_command_center_para_ingles_e_de_volta(servidor, navegador, largura):
    """Dono, 09/10: "o command center inteiro com versão português e inglês, com um switch com a bandeira
    americana e a bandeira brasileira no topo de cada página"."""
    pg = entrar(navegador, servidor, largura=largura, altura=844)
    erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    try:
        pg.get_by_role("button", name="English").click()
        pg.wait_for_function("() => document.documentElement.lang === 'en'")
        assert pg.get_by_role("button", name="English").get_attribute("aria-pressed") == "true"
        for rota, h1 in (("/", "Today"), ("/clients", "Clients"), ("/estoque", "Inventory"), ("/attention", "Needs attention")):
            abrir(pg, servidor, rota)
            pg.get_by_role("heading", level=1, name=h1).wait_for()
            r = pg.evaluate(_VAZA)
            assert not r["rola"], (rota, r)
        assert pg.title().startswith("Needs attention")
        # a escolha fica: outra aba, mesma língua
        abrir(pg, servidor, "/clients")
        pg.get_by_role("heading", level=1, name="Clients").wait_for()
    finally:
        pg.get_by_role("button", name="Português").click()
        pg.wait_for_function("() => document.documentElement.lang === 'pt-BR'")
    pg.get_by_role("heading", level=1, name="Clientes").wait_for()
    pg.close()
    assert not erros, erros


def test_bandeiras_tambem_no_login(servidor, navegador):
    pg = navegador.new_page(viewport={"width": 360, "height": 740})
    pg.goto(servidor + "/login")
    pg.get_by_role("button", name="English").click()
    pg.get_by_role("button", name="Sign in").wait_for()
    assert not pg.evaluate(_VAZA)["rola"]
    pg.get_by_role("button", name="Português").click()
    pg.get_by_role("button", name="Entrar").wait_for()
    pg.close()



def test_balcao_mostra_os_pilotos_do_dia_sem_ler_e_peca_sem_cliente_pergunta_de_quem_e(servidor, navegador):
    """#212 (dono, 13/10: "não tá aparecendo nenhum cliente nos dias que tiveram clientes" e
    "quando eu ler, aparecer qual o piloto que tem ali no dia"). No celular, os pilotos do dia
    aparecem antes de qualquer leitura; no painel, peça lida sem cliente pergunta de quem é."""
    balcao = servidor.replace("127.0.0.1", "localhost")
    v = navegador.new_page(viewport={"width": 360, "height": 740})
    v.goto(balcao + "/login")
    v.fill("#email", "luis@urace.us")
    v.fill("#pw", SENHA)
    v.keyboard.press("Enter")
    v.get_by_role("heading", name="Leia a peça").wait_for()
    v.get_by_role("heading", name="Pilotos de", exact=False).wait_for()
    piloto = v.locator(".br-antes .br-piloto", has_text="David Pedalo").first
    piloto.wait_for()
    assert piloto.bounding_box()["height"] >= 48
    piloto.click()
    v.get_by_text("Peças de").wait_for()
    v.get_by_role("button", name="Encerrar").click()
    assert v.evaluate("document.documentElement.scrollWidth") <= 360
    v.close()

    g = entrar(navegador, servidor, largura=360, altura=900)
    abrir(g, servidor, "/balcao")
    g.locator(".br-piloto", has_text="David Pedalo").first.wait_for()      # pilotos de hoje, sem ler nada
    campo = g.get_by_label("Leia o QR do cliente")
    campo.fill("7890000000017"); campo.press("Enter")
    g.get_by_role("heading", name="De quem é?").wait_for()
    g.get_by_role("dialog").locator(".br-piloto", has_text="David Pedalo").first.click()
    g.get_by_text("Front bumper (e2e) → David Pedalo: cobrada.").wait_for()
    g.get_by_role("heading", name="David Pedalo", level=2).wait_for()
    g.locator(".tbl .tr", has_text="Front bumper (e2e)").first.wait_for()
    r = g.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    assert len([t for n, t in _cabecalhos(g) if n == 1]) == 1
    assert not g.erros_js, g.erros_js
    g.close()


def test_menu_lateral_por_areas_cada_tela_num_lugar_so(servidor, navegador):
    """#217 (dono, 13/10: "tá tudo muito bagunçado … SDR junto ali com suite … vamos separar por
    áreas"). As áreas na ordem combinada, cada tela na sua área e nenhum link repetido."""
    g = entrar(navegador, servidor)
    abrir(g, servidor, "/")
    g.locator("nav.nav .grp").first.wait_for()
    grupos = g.evaluate("[...document.querySelectorAll('nav.nav .grp')].map(e => e.textContent.trim())")
    assert grupos == ["Hoje", "Comercial", "Site", "Logística", "Pedidos e compras", "IA e inserções manuais", "Equipe",
                      "Administrativo"], grupos
    area = g.evaluate("""() => { let grp = ''; const m = {}
        for (const el of document.querySelector('nav.nav').children) {
          if (el.classList.contains('grp')) grp = el.textContent.trim()
          else if (el.tagName === 'A') { const l = (el.querySelector('.lbl') || el).textContent.trim(); (m[l] = m[l] || []).push(grp) }
        }
        return m }""")
    # #306: o site ganhou a seção dele, com uma subseção por painel
    esperado = {"Calendário": "Hoje", "Robô SDR": "Comercial", "Clientes": "Comercial", "Painel do site": "Site",
                "Pedidos do site": "Site", "Agendamentos": "Site", "Editor do site": "Site", "Contas de clientes": "Site",
                "Estoque do site": "Site",                                                    # #309
                "Balcão": "Logística", "Checklists": "Logística", "Suits · Alpha Line": "Pedidos e compras",
                "Pedidos": "Pedidos e compras", "Manual dos marcadores": "IA e inserções manuais",
                "QuickBooks": "Administrativo", "Asana": "Administrativo"}
    for tela, grp in esperado.items():
        assert area.get(tela) == [grp], (tela, area.get(tela))
    hrefs = g.evaluate("[...document.querySelectorAll('nav.nav a')].map(a => a.getAttribute('href'))")
    assert len(hrefs) == len(set(hrefs)), sorted(h for h in hrefs if hrefs.count(h) > 1)
    abrir(g, servidor, "/site")
    g.get_by_role("heading", name="Painel do site", level=1).wait_for()
    abrir(g, servidor, "/site/agendamentos")
    g.get_by_role("heading", name="Agendamentos", level=1).wait_for()
def test_calendario_gerente_exclui_servico_e_ele_fica_no_historico_do_card(servidor, navegador):
    """#219 (dono, 13/10): "somente o acesso livre e o gerente tenham a possibilidade de excluir uma
    tarefa … ela exclui, deixa de ser mostrada, mas lá no histórico de serviço ela continua"."""
    m = entrar(navegador, servidor, "luis@urace.us", largura=390, altura=844)
    abrir(m, servidor, "/meu-dia")
    m.get_by_role("button", name="Próximo dia").click()
    m.get_by_role("heading", name="Renato Faixa Pistoni", level=3).wait_for()
    assert m.get_by_role("button", name="Excluir", exact=False).count() == 0, "o mecânico não exclui"
    m.close()

    g = entrar(navegador, servidor, largura=390, altura=844)
    abrir(g, servidor, "/meu-dia")
    g.get_by_role("button", name="Próximo dia").click()
    g.get_by_role("heading", name="Renato Faixa Pistoni", level=3).wait_for()
    g.get_by_role("button", name="Excluir o serviço Renato Faixa Pistoni_Professional Coaching_2T [1/1]").click()
    g.get_by_role("heading", name="Excluir serviço?").wait_for()
    g.get_by_label("Motivo (opcional)").fill("teste e2e")
    g.get_by_role("dialog").get_by_role("button", name="Excluir").click()
    g.get_by_text("Serviço excluído. Ele continua no histórico do card.").wait_for()
    g.get_by_role("heading", name="Renato Faixa Pistoni", level=3).wait_for(state="detached")
    r = g.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    cid = g.evaluate("fetch('/ops/api/clients?q=Pistoni').then(r => r.json())")
    cid = (cid["itens"] if isinstance(cid, dict) else cid)[0]["id"]
    abrir(g, servidor, f"/clients/{cid}")
    g.get_by_role("button", name="Serviços", exact=False).first.click()
    linha = g.locator("tr.tr-excluido", has_text="Professional Coaching")
    linha.wait_for()
    assert "teste e2e" in linha.inner_text() and "excluído" in linha.inner_text()
    linha.get_by_role("button", name="Restaurar").click()
    g.get_by_text("Serviço restaurado.").wait_for()
    # o aviso aparece antes de a tabela ser redesenhada: esperar a linha sair, em vez de contar na hora
    # (contar na hora deixava este teste falhar de vez em quando)
    linha.first.wait_for(state="detached")
    assert g.locator("tr.tr-excluido", has_text="Professional Coaching").count() == 0
    assert not g.erros_js, g.erros_js
    g.close()


def test_como_usar_le_os_guias_navega_entre_eles_e_baixa_o_md_para_a_ia(servidor, navegador):
    """#223 (dono, 13/10): "uma seção chamada como usar … o guia de como usar a plataforma … MD para
    IA também, uma parte onde a pessoa consegue baixar o MD"."""
    g = entrar(navegador, servidor, largura=390, altura=844)
    abrir(g, servidor, "/como-usar")
    g.get_by_role("heading", name="Como usar", level=1).wait_for()
    g.get_by_role("heading", name="MD para a sua IA").wait_for()
    with g.expect_download() as baixa:
        g.get_by_role("link", name="Baixar o MD para a IA").click()
    assert baixa.value.suggested_filename == "urace-command-center-para-ia.md"
    g.get_by_role("link", name="Guia geral").click()
    g.wait_for_url("**/ops/como-usar/geral")
    g.locator("article.guia h3", has_text="Mapa das telas").first.wait_for()
    assert len([t for n, t in _cabecalhos(g) if n == 1]) == 1
    r = g.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    g.locator("article.guia a[href='/ops/como-usar/vendas']").first.click()
    g.wait_for_url("**/ops/como-usar/vendas")
    g.get_by_role("heading", name="Playbook de vendas do Command Center", level=2).wait_for()
    assert not g.erros_js and not g.erros_api, (g.erros_js, g.erros_api)
    g.close()


def test_liberar_invoice_so_o_gerente_conferindo_o_valor_e_a_tabela(servidor, navegador):
    """#204 (dono, 14/10: "precisa confirmar o valor da invoice"): a invoice fora da tabela fica
    esperando; o operador vê o aviso mas não libera, e o gerente libera vendo o valor e o preço
    da tabela (que vem do catálogo, não do valor da venda). #310: a invoice que o closer desligou
    no fechamento fora da tabela também tem o Liberar, no aviso e no acompanhamento, no celular."""
    op = entrar(navegador, servidor, "op@urace.us")
    csrf = {"X-CSRF": next(c["value"] for c in op.context.cookies() if c["name"] == "cc_csrf")}
    r = op.request.post(servidor + "/api/sales", headers=csrf,
                        data={"name": "Marina Lopes", "email": "marina.e2e@example.com", "service": "Urace Daily", "amount": 420})
    oid = r.json()["id"]
    r = op.request.post(servidor + f"/api/sales/{oid}/close", headers=csrf, data={
        "preco_tabela": 420, "passos": {"cliente": False, "qbo": True, "waiver": False, "asana": False, "kommo": False}})
    f = r.json()["fechamento"]
    assert f["invoice_pendente"] is True and f["preco_tabela"] == 500, f
    # o operador vê por que parou, mas não tem o botão nem a rota
    abrir(op, servidor, f"/sales/{oid}")
    op.get_by_text("Invoice esperando o gerente conferir o valor.").wait_for()
    op.get_by_text("Só o gerente ou o dono libera.").wait_for()
    assert op.get_by_role("button", name="Liberar invoice").count() == 0
    assert op.request.post(servidor + f"/api/sales/{oid}/invoice/liberar", headers=csrf, data={"valor": 420}).status == 403
    assert op.request.post(servidor + f"/api/sales/{oid}/step/qbo", headers=csrf).status == 409
    # #310: fechada fora da tabela com a invoice desligada pelo closer (antes, ninguém conseguia mandar)
    r = op.request.post(servidor + "/api/sales", headers=csrf,
                        data={"name": "Otávio Desligado", "email": "otavio.e2e@example.com", "service": "Urace Daily", "amount": 430})
    oid2 = r.json()["id"]
    r = op.request.post(servidor + f"/api/sales/{oid2}/close", headers=csrf, data={
        "passos": {"cliente": False, "qbo": False, "waiver": False, "asana": False, "kommo": False}})
    assert r.json()["fechamento"]["invoice_pendente"] is False, r.json()
    assert op.request.post(servidor + f"/api/sales/{oid2}/step/qbo", headers=csrf).status == 409
    # #310 (R5): na tabela, com a invoice desligada no fechamento (estado "livre"): o passo manda
    r = op.request.post(servidor + "/api/sales", headers=csrf,
                        data={"name": "Paulo Tabela", "email": "paulo.e2e@example.com", "service": "Urace Daily", "amount": 500})
    oid3 = r.json()["id"]
    r = op.request.post(servidor + f"/api/sales/{oid3}/close", headers=csrf, data={
        "passos": {"cliente": False, "qbo": False, "waiver": False, "asana": False, "kommo": False}})
    assert op.request.get(servidor + f"/api/sales/{oid3}").json()["invoice"] == "livre"
    op.close()

    g = entrar(navegador, servidor, largura=360, altura=800)          # gerente, no celular
    abrir(g, servidor, f"/sales/{oid}")
    g.get_by_role("button", name="Liberar invoice").first.click()
    modal = g.locator(".modal", has=g.get_by_role("heading", name="Liberar invoice", level=3))
    modal.wait_for()
    texto = modal.inner_text()
    assert "Valor da venda" in texto and "Preço da tabela (catálogo)" in texto, texto
    assert re.search(r"\$\s?420", texto) and re.search(r"\$\s?500", texto), texto
    r = g.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    # sem QuickBooks no e2e, a liberação chega ao servidor e volta "não conectado": nada sai, nada muda
    modal.get_by_role("button", name=re.compile(r"Liberar invoice de")).click()
    g.get_by_text(re.compile("não conectado")).first.wait_for(timeout=8000)
    d = g.request.get(servidor + f"/api/sales/{oid}").json()
    assert d["oportunidade"]["closing"]["invoice_pendente"] is True and d["pode_liberar"] is True

    # #310: a desligada pelo closer — o aviso e o botão na ficha, e o Liberar na linha do acompanhamento
    abrir(g, servidor, f"/sales/{oid2}")
    g.get_by_text("Invoice desligada no fechamento, com valor fora da tabela.").wait_for()
    # alvo de toque: a altura do layout (a janela abre com uma escala curta, que a caixa medida pegaria)
    assert g.get_by_role("button", name="Liberar invoice", exact=True).first.evaluate("b => b.offsetHeight") >= 40
    g.get_by_role("button", name="Fechar venda", exact=True).click()
    acomp = g.locator(".modal", has=g.get_by_role("heading", name="Acompanhamento do fechamento"))
    acomp.wait_for()
    linha = acomp.get_by_role("button", name="Liberar invoice", exact=True)
    assert linha.evaluate("b => b.offsetHeight") >= 40, "alvo de toque"
    linha.click()
    modal = g.locator(".modal", has=g.get_by_role("heading", name="Liberar invoice", level=3))
    modal.wait_for()
    assert re.search(r"\$\s?430", modal.inner_text()) and re.search(r"\$\s?500", modal.inner_text()), modal.inner_text()
    r = g.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    modal.get_by_role("button", name=re.compile(r"Liberar invoice de")).click()
    g.get_by_text(re.compile("não conectado")).first.wait_for(timeout=8000)
    d = g.request.get(servidor + f"/api/sales/{oid2}").json()
    assert d["invoice"] == "esperando" and "cobrando" not in d["oportunidade"]["closing"], "nada saiu: a marca do clique sai"

    # #310 (R5): a desligada na tabela tinha só um "—" na linha da invoice; agora tem o botão do passo
    abrir(g, servidor, f"/sales/{oid3}")
    g.get_by_role("button", name="Fechar venda", exact=True).click()
    acomp = g.locator(".modal", has=g.get_by_role("heading", name="Acompanhamento do fechamento"))
    acomp.wait_for()
    mandar = acomp.get_by_role("button", name="mandar a invoice", exact=True)
    assert mandar.evaluate("b => b.offsetHeight") >= 40, "alvo de toque"
    r = g.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    mandar.click()
    # a invoice foi desligada pelo closer: mandar pergunta antes (2ª revisão), como "Cobrar só o depósito"
    pergunta = g.locator(".modal.ask", has=g.get_by_role("heading", name="Mandar a invoice?"))
    pergunta.wait_for()
    assert re.search(r"\$\s?500", pergunta.inner_text()), pergunta.inner_text()
    pergunta.get_by_role("button", name="Mandar a invoice", exact=True).click()
    g.get_by_text(re.compile("não conectado")).first.wait_for(timeout=8000)
    d = g.request.get(servidor + f"/api/sales/{oid3}").json()
    assert d["invoice"] == "livre" and "cobrando" not in d["oportunidade"]["closing"], "nada saiu: a marca sai"
    assert not g.erros_js, g.erros_js
    g.close()


@pytest.mark.parametrize("largura", [360, 390])
def test_venda_tentativa_sem_desfecho_mandar_ou_registrar_no_celular(servidor, navegador, largura):
    """#310, 2ª revisão (A2): a tentativa que não terminou oferece ao gerente "Não saiu: mandar" e "Saiu:
    registrar o número"; o registro confere no QuickBooks (sem ele ligado, nada é registrado). Quem vende
    só vê o aviso. A invoice criada cujo envio falhou tem o Reenviar (A1). E a venda paga no site. Tudo
    em 360 e 390 px, sem rolar para o lado e com o toque de 40 px."""
    import sqlite3
    g = entrar(navegador, servidor, largura=largura, altura=800)
    csrf = {"X-CSRF": next(c["value"] for c in g.context.cookies() if c["name"] == "cc_csrf")}
    r = g.request.post(servidor + "/api/sales", headers=csrf,
                       data={"name": f"Rita Revisao {largura}", "email": f"rita{largura}.e2e@example.com",
                             "service": "Urace Daily", "amount": 500})
    oid = r.json()["id"]
    r = g.request.post(servidor + f"/api/sales/{oid}/close", headers=csrf, data={
        "passos": {"cliente": False, "qbo": False, "waiver": False, "asana": False, "kommo": False}})
    assert r.status == 200, r.text()
    con = sqlite3.connect(BANCO, timeout=10, isolation_level=None)
    # a tentativa de antes ficou sem desfecho: o "enviando" na auditoria, nada depois
    con.execute("INSERT INTO audit_logs (event, actor, entity_type, entity_id, detail) VALUES (?,?,?,?,?)",
                ("sales.invoice.sending", "user:1", "opportunity", str(oid), json.dumps(
                    {"tentativa": f"t{largura}x", "acao": "reenvio", "por": "Gina Exemplo", "em": "2026-10-16T14:05:00.000Z",
                     "valor": 500, "deposito": 0, "item": "32"})))
    stripe = con.execute("""INSERT INTO opportunities (name, email, service, amount, stage, source, closing)
                            VALUES (?,?,?,?,?,?,?)""", (f"Sara Stripe {largura}", f"sara{largura}.e2e@example.com",
                                                        "Store: Camiseta Exemplo", 45, "FECHAMENTO", "Site",
                                                        json.dumps({"em": "2026-10-16T15:00:00.000Z", "por": "stripe", "pedido": 9}))).lastrowid
    passo = {"passo": "qbo", "nome": "Cliente e invoice no QuickBooks", "ok": True, "enviado": False, "invoice": "7001",
             "numero": f"N{largura}", "detalhe": f"invoice nº N{largura} criada; o envio falhou (HTTP 500): reenviar"}
    criada = con.execute("""INSERT INTO opportunities (name, email, service, amount, stage, source, closing)
                            VALUES (?,?,?,?,?,?,?)""", (f"Nina Envio {largura}", f"nina{largura}.e2e@example.com", "Urace Daily",
                                                        500, "FECHAMENTO", "Ligação",
                                                        json.dumps({"em": "2026-10-16T15:00:00.000Z", "por": "Carla Exemplo",
                                                                    "passos": [passo]}))).lastrowid
    con.close()

    abrir(g, servidor, f"/sales/{oid}")
    g.get_by_role("button", name="Fechar venda", exact=True).click()
    acomp = g.locator(".modal", has=g.get_by_role("heading", name="Acompanhamento do fechamento"))
    acomp.wait_for()
    acomp.get_by_role("button", name="mandar a invoice", exact=True).click()
    g.locator(".modal.ask").get_by_role("button", name="Mandar a invoice", exact=True).click()
    dlg = g.locator(".modal.ask", has=g.get_by_role("heading", name="A tentativa anterior não terminou"))
    dlg.wait_for(timeout=8000)
    assert re.search("não terminou: confira no QuickBooks", dlg.inner_text()), dlg.inner_text()
    dlg.get_by_role("button", name="Não saiu: mandar").wait_for()
    g.wait_for_timeout(400)
    r = g.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    assert not g.evaluate(_PEQUENOS), g.evaluate(_PEQUENOS)
    dlg.get_by_role("button", name="Saiu: registrar o número").click()
    reg = g.locator(".modal.ask", has=g.get_by_role("heading", name="Registrar a invoice que saiu"))
    reg.wait_for()
    reg.get_by_label("Número da invoice no QuickBooks (Invoice no.)").fill("1001")
    r = g.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    assert not g.evaluate(_PEQUENOS), g.evaluate(_PEQUENOS)
    reg.get_by_role("button", name="Registrar a invoice").click()
    # sem o QuickBooks no e2e, o servidor não confere: nada é registrado
    g.get_by_text(re.compile("Ligue o QuickBooks para conferir")).first.wait_for(timeout=8000)
    d = g.request.get(servidor + f"/api/sales/{oid}").json()
    assert d["invoice"] == "livre" and not [p for p in d["oportunidade"]["closing"]["passos"] if p.get("registrada")]
    g.keyboard.press("Escape")

    # A1: a invoice criada cujo envio falhou: o aviso e o Reenviar (a mesma invoice)
    abrir(g, servidor, f"/sales/{criada}")
    g.get_by_text(f"Invoice nº N{largura} criada, o envio falhou.").wait_for()
    reenviar = g.get_by_role("button", name="Reenviar", exact=True)
    assert reenviar.evaluate("b => b.offsetHeight") >= 40
    assert g.get_by_role("button", name="Liberar invoice").count() == 0
    r = g.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    reenviar.click()
    g.get_by_text(re.compile("não conectado")).first.wait_for(timeout=8000)
    assert g.request.get(servidor + f"/api/sales/{criada}").json()["nao_enviadas"][0]["invoice"] == "7001"

    # a venda paga no site
    abrir(g, servidor, f"/sales/{stripe}")
    g.get_by_text("Pago no site (Stripe).").wait_for()
    r = g.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    assert not g.evaluate(_PEQUENOS), g.evaluate(_PEQUENOS)
    assert not g.erros_js, g.erros_js
    g.close()

    # quem vende: o aviso do servidor, sem a escolha do gerente
    op = entrar(navegador, servidor, "op@urace.us", largura=largura, altura=800)
    abrir(op, servidor, f"/sales/{oid}")
    op.get_by_role("button", name="Fechar venda", exact=True).click()
    acomp = op.locator(".modal", has=op.get_by_role("heading", name="Acompanhamento do fechamento"))
    acomp.wait_for()
    acomp.get_by_role("button", name="mandar a invoice", exact=True).click()
    op.locator(".modal.ask").get_by_role("button", name="Mandar a invoice", exact=True).click()
    op.get_by_text(re.compile("não terminou: confira no QuickBooks")).first.wait_for(timeout=8000)
    assert op.get_by_role("button", name="Não saiu: mandar").count() == 0
    assert op.get_by_role("button", name="Saiu: registrar o número").count() == 0
    r = op.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    assert not op.erros_js, op.erros_js
    op.close()


def test_card_de_irmao_com_vincular_ao_cliente(servidor, navegador):
    """#204 (dono, 14/10: "sim, é para criar um card de um irmão"): o Novo cliente com o mesmo
    e-mail abriria o card do irmão; o card de irmão nasce do card escolhido em "Vincular ao
    cliente", com o mesmo responsável e contato, e cada piloto fica com o seu."""
    pg = entrar(navegador, servidor, "op@urace.us", largura=390, altura=844)
    abrir(pg, servidor, "/clients")
    pg.get_by_role("button", name=re.compile(r"Novo cliente")).first.click()
    pg.get_by_role("button", name=re.compile("É irmão de um cliente")).click()
    pg.get_by_role("heading", name="Card de irmão", level=3).wait_for()
    pg.get_by_label("Irmão de — vincular ao cliente").fill("David")
    pg.locator(".lpick-menu .opt", has_text="David Pedalo").first.click()
    pg.get_by_text(re.compile("vem do card de David Pedalo")).wait_for()
    r = pg.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    pg.get_by_label("Piloto (o irmão) *").fill("Sofia Pedalo")
    pg.get_by_role("button", name="Criar card do irmão").click()
    pg.get_by_text("Card do irmão criado.").wait_for()
    pg.get_by_role("heading", name="Sofia Pedalo").first.wait_for()
    pg.get_by_role("link", name="David Pedalo").first.wait_for()          # o irmão, marcado no card
    david = pg.request.get(servidor + "/api/clients?q=David%20Pedalo").json()[0]
    sofia = [c for c in pg.request.get(servidor + "/api/clients?q=Sofia").json() if c["pilot_name"] == "Sofia Pedalo"][0]
    assert sofia["id"] != david["id"] and sofia["email"] == david["email"] and sofia["phone"] == david["phone"]
    card = pg.request.get(servidor + f"/api/clients/{sofia['id']}").json()
    assert card["client"]["sibling_of"] == david["id"] and [i["id"] for i in card["irmaos"]] == [david["id"]]
    assert card["tasks"] == [], "o serviço do David não vai para o card da Sofia"
    assert not pg.erros_js and not pg.erros_api, (pg.erros_js, pg.erros_api)


# ------------------------------------------------------------- carrinho e checkout no Stripe (#236)
def test_carrinho_sessao_e_produto_um_checkout_no_stripe_e_o_pedido_no_painel(servidor, navegador):
    """#236, dono 14/10: "o sistema de carrinho e checkout ... Tudo testado, tudo funcionando. É, usando o
    Stripe". Sessão da agenda (com o preço e o depósito do painel) + produto da loja no mesmo carrinho;
    conta e piloto; um checkout só no Stripe (o falso); volta paga; o pedido e a sessão aparecem no painel.
    No celular (390 e 360 px), nada rola para o lado e os botões têm 40 px."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from command_center.vitrine import paginas_site
    site = servidor.removesuffix("/ops")
    adm = entrar(navegador, servidor, email="italo@urace.us")
    csrf = {"X-CSRF": next(c["value"] for c in adm.context.cookies() if c["name"] == "cc_csrf")}
    # #263: o serviço do Baby Kart vem da migração (nome, preço e depósito); aqui só se garante que
    # está ativo e com o depósito que este teste confere
    do_painel = adm.request.get(servidor + "/api/site/servicos").json()["servicos"]
    baby = next(x for x in do_painel if x["site_kart"] == "Baby Kart")
    r = adm.request.patch(servidor + f"/api/site/servicos/{baby['id']}",
                          data={"price": 719, "deposit": 400, "active": True}, headers=csrf)
    assert r.ok, r.text()
    # domingo à tarde, 5 vagas, só para este teste (os outros usam o sábado de manhã)
    assert adm.request.put(servidor + "/api/site/agenda/semana", data=[{"weekday": 6, "period": "tarde", "open": True, "capacity": 5}],
                           headers=csrf).ok
    produto = next(p for p in paginas_site.dados("produtos.json")["produtos"]
                   if not p["variations"] and p["price"] and p["in_stock"] and p["images"])
    hoje = datetime.now(ZoneInfo("America/New_York")).date()
    domingo = next(d for d in (hoje + timedelta(days=n) for n in range(3, 12)) if d.weekday() == 6)
    rotulo = domingo.strftime("%A, %B ") + str(domingo.day) + ", available"
    try:
        v = navegador.new_page(viewport={"width": 390, "height": 844}, extra_http_headers={"X-Forwarded-For": "10.2.36.1"})
        erros = []
        v.on("pageerror", lambda e: erros.append(str(e)))
        cliente_pela_api(v, servidor, "Carla Carrinho", "carla.carrinho.e2e@example.com", piloto="Caio Carrinho", ip="10.2.36.1")
        # 1 · a sessão: kart, dia, turno → o preço do painel e o botão do carrinho
        v.goto(site + "/services/arrive-and-drive/")
        v.locator("label.kart", has_text="Baby Kart").click()
        v.locator(".agenda-dia.aberto").first.wait_for()
        for _ in range(3):
            if v.get_by_role("button", name=rotulo).count():
                break
            v.get_by_role("button", name="Next month").click()
        v.get_by_role("button", name=rotulo).click()
        v.get_by_role("button", name=re.compile("^Afternoon")).click()
        assert v.locator(".agenda-preco").inner_text() == "$719"
        assert not v.locator(".agenda-ir").count(), '#262: um botão só, sem o "Continue to booking"'
        v.get_by_role("button", name=re.compile("^Add to cart")).click()
        v.wait_for_url(re.compile(r"/cart/"))          # #262: o único caminho leva ao carrinho
        # 2 · o produto da loja
        v.goto(site + f"/store/p/{produto['slug']}/")
        v.get_by_role("button", name="Add to cart").click()
        v.get_by_text("Added to your cart.").wait_for()
        assert v.locator("[data-carrinho-n]").inner_text() == "2", "o contador do topo"
        # 3 · o carrinho: o preço vem do servidor, o piloto da conta já vem escolhido
        v.locator("a.carrinho-topo").click()
        v.wait_for_url("**/cart/")
        v.get_by_role("heading", name="Your cart", level=1).wait_for()
        assert v.title() == "Your cart | URACE" and v.locator('meta[name="robots"]').get_attribute("content").startswith("noindex")
        total = 719 + 400 + produto["price"]
        pagar = v.get_by_role("button", name=re.compile(r"^Checkout · \$" + re.escape(f"{total:,.2f}")))
        pagar.wait_for()
        assert v.get_by_text("Refundable security deposit: $400.00").count() == 1
        assert v.locator(".carrinho-linhas").get_by_label("Driver").input_value() != ""
        assert v.get_by_text("Signed in as").count() == 1
        for largura in (390, 360):
            v.set_viewport_size({"width": largura, "height": 800})
            assert len([t for n, t in _cabecalhos(v) if n == 1]) == 1
            r = v.evaluate(_VAZA)
            assert not r["rola"] and not r["culpados"], (largura, r)
            menor = v.evaluate("""() => [...document.querySelectorAll('.carrinho button, .carrinho select, .carrinho input:not([type=radio]), .carrinho label.opcao, header a, header summary')]
                .filter(e => e.offsetParent !== null).map(e => [e.getBoundingClientRect().height, (e.innerText || e.getAttribute('aria-label') || '').trim().slice(0, 30)])
                .filter(([h]) => h < 40)""")
            assert not menor, (largura, menor)
        # 4 · um checkout só no Stripe (o falso), com a linha do depósito
        pagar.click()
        v.wait_for_url(STRIPE.origem + "/pay/**")
        assert f"US$ {total:.2f}" in v.content()
        assert v.locator(".linha", has_text="Refundable security deposit").count() == 1
        assert v.locator(".linha", has_text="Caio Carrinho").count() == 1
        v.get_by_role("link", name="Pay").click()
        v.get_by_role("heading", name="Payment confirmed", level=1).wait_for()   # #245: a página do pedido
        assert "/cart/thanks/?session_id=cs_test_e2e" in v.url
        assert v.get_by_text("Booked.").count() == 1
        assert v.evaluate("JSON.parse(localStorage.getItem('urace.carrinho') || '{}').itens.length") == 0, "o carrinho virou pedido"
        r = v.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        v.close()
        assert not erros, erros
        # 5 · o painel: a venda GANHO com o pedido e as linhas, e a sessão paga na agenda
        abrir(adm, servidor, "/sales")
        adm.get_by_text("Carla Carrinho").first.click()
        adm.get_by_role("heading", name=re.compile(r"^Pedido do site #\d+")).wait_for()
        assert adm.get_by_text("Caio Carrinho").count() >= 1 and adm.get_by_text(produto["name"]).count() >= 1
        abrir(adm, servidor, "/site/agendamentos")
        adm.get_by_text(re.compile(r"pago no site · pedido #\d+")).first.wait_for()
        assert not adm.erros_js, adm.erros_js
    finally:
        adm.request.put(servidor + "/api/site/agenda/semana", data=[{"weekday": 6, "period": "tarde", "open": False, "capacity": 5}],
                        headers=csrf)
        adm.close()


@pytest.mark.parametrize("largura", [1280, 390])
def test_agenda_de_vendas_conecta_o_google_calendar_e_mostra_os_compromissos(servidor, navegador, largura):
    """#220: sem o cliente OAuth na VPS, o botão fica desligado e diz por quê. Com ele, a pessoa entra
    no "Google" (o falso, local), volta conectada, o retorno vira evento lá e o compromisso dela
    aparece na Agenda de vendas, sem rolar para o lado no celular."""
    from datetime import datetime, timedelta, timezone
    from command_center.tests.google_falso import credenciais_json
    pg = entrar(navegador, servidor, largura=largura, altura=900)
    abrir(pg, servidor, "/sales/agenda")
    botao = pg.get_by_role("button", name="Conectar ao Google Calendar")
    assert botao.is_disabled()
    assert pg.get_by_text("O gerente ainda não configurou o acesso ao Google", exact=False).count() >= 1

    amanha = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    GOOGLE.evento_alheio(f"Reunião e2e {largura}", f"{amanha}T13:00:00-04:00", f"{amanha}T14:00:00-04:00")
    csrf = next(c["value"] for c in pg.context.cookies() if c["name"] == "cc_csrf")
    r = pg.request.post(servidor + "/api/sales", headers={"X-CSRF": csrf},
                        data={"name": f"Retorno Google e2e {largura}", "next_at": f"{amanha}T15:00:00Z"})
    assert r.status == 201
    open(GOOGLE_CRED, "w").write(credenciais_json())
    try:
        abrir(pg, servidor, "/sales/agenda")
        pg.get_by_role("button", name="Conectar ao Google Calendar").click()
        pg.wait_for_url(lambda u: u.startswith(GOOGLE.origem), timeout=10000)
        pg.click("#permitir")                                # a "tela de consentimento" do Google
        pg.wait_for_url(lambda u: "/ops/sales/agenda" in u and "google=" not in u, timeout=10000)
        pg.wait_for_load_state("networkidle")
        assert pg.get_by_text("Conectado como vendedor.teste@example.com").count() == 1
        pg.get_by_text(f"Reunião e2e {largura}").wait_for(timeout=10000)
        assert any(f"Retorno Google e2e {largura}" in e["summary"] for e in GOOGLE.nossos().values())
        assert not pg.locator("main").get_by_text("URACE · retorno", exact=False).count()   # o nosso evento não volta duplicado
        r = pg.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        assert not pg.erros_js and not pg.erros_api

        pg.get_by_role("button", name="Desconectar").click()
        pg.get_by_role("dialog").get_by_role("button", name="Desconectar").click()
        pg.get_by_role("button", name="Conectar ao Google Calendar").wait_for(timeout=10000)
        assert pg.get_by_text(f"Reunião e2e {largura}").count() == 0
    finally:
        os.remove(GOOGLE_CRED)
    pg.close()


# ------------------------------------------------------------- uma página para cada resultado do Stripe (#245)
def test_cada_resultado_do_pagamento_tem_a_sua_pagina_no_celular(servidor, navegador):
    """#245, dono 14/10: "monte páginas para cada um no site" (os 4 eventos do webhook do Stripe). #248: comprar
    pede a conta do site ("Buy now" sem conta → entrar → volta ao produto), a chave EN/PT ("mesmo jeito do command
    center") e o aviso sempre. No celular: processando → (chave PT) não passou (e-mail com o link; "Tentar de novo"
    abre um checkout novo) → expirou ("Restaurar o carrinho") → pago. Cada página com um h1, nada rola para o lado
    em 390 e 360 px e os botões têm 40 px. O painel mostra o pedido com o estado e o link."""
    import json

    from command_center.vitrine import paginas_site
    site = servidor.removesuffix("/ops")
    produto = next(p for p in paginas_site.dados("produtos.json")["produtos"]
                   if not p["variations"] and p["price"] and p["in_stock"] and p["images"])
    quem = {"email": "ivo.teste.e2e@example.com", "name": "Ivo Teste", "phone": "+14075550148"}
    conta = navegador.new_page()                         # a conta já existe; a pessoa só entra
    cliente_pela_api(conta, servidor, quem["name"], quem["email"], ip="10.2.48.1")
    conta.close()
    v = navegador.new_page(viewport={"width": 390, "height": 844}, extra_http_headers={"X-Forwarded-For": "10.2.45.1"})
    erros = []
    v.on("pageerror", lambda e: erros.append(str(e)))

    def confere(h1):
        v.get_by_role("heading", name=h1, level=1).wait_for()
        assert v.locator('meta[name="robots"]').get_attribute("content").startswith("noindex")
        for largura in (390, 360):
            v.set_viewport_size({"width": largura, "height": 800})
            assert len([t for n, t in _cabecalhos(v) if n == 1]) == 1
            r = v.evaluate(_VAZA)
            assert not r["rola"] and not r["culpados"], (h1, largura, r)
            menor = v.evaluate("""() => [...document.querySelectorAll('main .btn, main button, .pedido-pagina a')]
                .filter(e => e.offsetParent !== null).map(e => [e.getBoundingClientRect().height, e.innerText.trim().slice(0, 30)])
                .filter(([h]) => h < 40)""")
            assert not menor, (h1, largura, menor)
        v.set_viewport_size({"width": 390, "height": 844})

    def sessao_do_stripe():
        v.wait_for_url(STRIPE.origem + "/pay/**")
        return STRIPE.sessoes[v.url.rstrip("/").rsplit("/", 1)[1]]

    def emails_para(trecho):
        for _ in range(50):
            achados = [json.loads(x) for x in open(EMAILS, encoding="utf-8").read().splitlines()]
            achados = [x for x in achados if x["to"] == quem["email"] and trecho in x["subject"]]
            if achados:
                return achados
            time.sleep(0.1)
        return []

    # 0 · #248: "Buy now" sem conta → entrar → volta para o produto
    v.goto(site + f"/store/p/{produto['slug']}/")
    v.get_by_role("button", name="Buy now").click()
    v.wait_for_url(re.compile(r".*/ops/portal\?volta=/store/p/.*"))
    v.fill("#p-email", quem["email"])
    v.fill("#p-pw", "pista-molhada-7")
    v.get_by_role("button", name="Sign in").click()
    v.wait_for_url(re.compile(rf".*/store/p/{re.escape(produto['slug'])}/$"))
    # 1 · Buy now → o Checkout (o falso), com o e-mail da conta → confirma depois: "Payment processing"
    v.get_by_role("button", name="Buy now").click()
    s1 = sessao_do_stripe()
    assert s1["customer_email"] == quem["email"], "o e-mail da conta vai para o Stripe"
    assert webhook_stripe(site, s1, "checkout.session.completed", "evt_e2e_245a", customer_details=quem) == "aguardando"
    v.goto(site + f"/store/thanks/?session_id={s1['id']}")
    confere("Payment processing")
    v.get_by_role("link", name=re.compile(r"^order #\d+$")).click()
    v.wait_for_url(re.compile(r".*/order/\d+-[A-Za-z0-9_-]{27}/$"))
    pagina = v.url.removeprefix(site)
    confere("Payment processing")
    assert v.title() == "Payment processing | URACE" and v.get_by_text("Your details").count() == 1
    assert emails_para("confirming your payment"), "#248: e-mail já no processando"
    # 1b · a chave EN/PT: a mesma página em português (e a escolha fica)
    v.get_by_role("button", name="Português").click()
    confere("Pagamento em confirmação")
    assert v.evaluate("document.documentElement.lang") == "pt-BR" and v.url.endswith(pagina)
    # 2 · async_payment_failed: "O pagamento não foi concluído", o e-mail com o link e "Tentar de novo" → checkout novo
    assert webhook_stripe(site, s1, "checkout.session.async_payment_failed", "evt_e2e_245b", customer_details=quem) == "falhou"
    v.reload()
    confere("O pagamento não foi concluído")
    assert v.get_by_text("nada foi cobrado", exact=False).count() >= 1
    avisos = emails_para("didn't go through")              # o pedido foi feito em inglês: o e-mail sai em inglês
    assert len(avisos) == 1 and pagina in avisos[0]["text"]
    v.get_by_role("button", name="Tentar de novo").click()
    s2 = sessao_do_stripe()
    assert f"US$ {produto['price']:.2f}" in v.content(), "o preço do catálogo, recalculado"
    # 3 · o checkout novo expira: "O checkout expirou" (e o e-mail em português) e "Restaurar o carrinho"
    assert webhook_stripe(site, s2, "checkout.session.expired", "evt_e2e_245c") == "expirado"
    v.goto(site + f"/cart/thanks/?session_id={s2['id']}")
    confere("O checkout expirou")
    assert emails_para("O seu checkout expirou"), "o pedido novo foi feito em português"
    v.get_by_role("link", name="Restaurar o carrinho").click()
    v.wait_for_url("**/cart/")
    v.get_by_role("heading", name="Seu carrinho", level=1).wait_for()
    pagar = v.get_by_role("button", name=re.compile(r"^Pagar · \$"))
    pagar.wait_for()
    assert v.evaluate("JSON.parse(localStorage.getItem('urace.carrinho') || '{}').itens.length") == 1
    assert v.get_by_text("Conectado como").count() == 1
    r = v.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    # 4 · paga: "Pagamento confirmado"; de volta ao inglês, "Payment confirmed"
    pagar.click()
    sessao_do_stripe()
    v.get_by_role("link", name="Pay").click()
    confere("Pagamento confirmado")
    v.get_by_role("button", name="English").click()
    confere("Payment confirmed")
    # 5 · token mexido: 404
    assert v.request.get(site + pagina[:-6] + "AAAAA/").status == 404
    v.close()
    assert not erros, erros
    # 6 · o painel: o pedido com o estado e o link da página, no celular também
    adm = entrar(navegador, servidor, email="italo@urace.us", largura=390, altura=844)
    abrir(adm, servidor, "/site/pedidos")
    adm.get_by_role("button", name="Não passou").click()
    adm.get_by_text("pagamento não passou").first.wait_for()
    assert adm.locator(f'a[href$="{pagina}"]').count() == 1
    r = adm.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    assert not adm.erros_js and not adm.erros_api, (adm.erros_js, adm.erros_api)
    adm.close()


# ------------------------------------------------- o kart escolhido no site e o que falta escolher (#253)
def _csrf(pg):
    return {"X-CSRF": next(c["value"] for c in pg.context.cookies() if c["name"] == "cc_csrf")}


def _servicos_do_painel(adm, servidor):
    return adm.request.get(servidor + "/api/site/servicos").json()["servicos"]


def _ativar(adm, servidor, sid, ativo):
    r = adm.request.patch(servidor + f"/api/site/servicos/{sid}", data={"active": ativo}, headers=_csrf(adm))
    assert r.ok, r.text()


def _criar_servico(adm, servidor, nome, preco, kart=None):
    """#263: `kart` é a chave do kart do site (o campo "Kart do site" do painel); sem ela, o serviço
    não é de kart nenhum e o site não o oferece."""
    corpo = {"name": nome, "price": preco}
    if kart:
        corpo["site_kart"] = kart
    r = adm.request.post(servidor + "/api/site/servicos", data=corpo, headers=_csrf(adm))
    assert r.ok, r.text()
    return r.json()["id"]


def _desligar_os_servicos(adm, servidor):
    """Desliga todos os serviços de sessão ativos e devolve os ids, para religar no fim."""
    antes = [s["id"] for s in _servicos_do_painel(adm, servidor)
             if s["active"] and (s["kind"] or "session") == "session"]
    for sid in antes:
        _ativar(adm, servidor, sid, False)
    return antes


def _proximo(dia_semana):
    """O próximo dia dessa semana (terça=1, quarta=2) com folga, no fuso da Flórida."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    hoje = datetime.now(ZoneInfo("America/New_York")).date()
    return next(d for d in (hoje + timedelta(days=n) for n in range(3, 12)) if d.weekday() == dia_semana)


def _clicar_dia(v, data):
    """Clica nesse dia no calendário público, virando o mês quantas vezes precisar."""
    rotulo = data.strftime("%A, %B ") + str(data.day) + ", available"
    v.locator(".agenda-dia.aberto").first.wait_for()
    for _ in range(4):
        if v.get_by_role("button", name=rotulo).count():
            break
        v.get_by_role("button", name="Next month").click()
    v.get_by_role("button", name=rotulo).click()


@pytest.mark.parametrize("largura", [390, 1280])
def test_agenda_do_site_diz_o_que_falta_e_avisa_quando_nao_da_para_reservar(servidor, navegador, largura):
    """#253, dono 15/10 (serviço "teste" desativado no painel e a reserva travada no ar): o botão diz o
    que falta de verdade — dia escolhido e turno faltando é "Pick a time to continue", não "Pick a day";
    um turno só aberto já vem escolhido; o turno do dia anterior não fica marcado onde não abre; e sem
    serviço do painel a página avisa com o contato em vez de oferecer um botão que não leva a nada.

    #262: é um botão só, o do carrinho. #263: o serviço é do kart pela chave "Kart do site", e o kart
    sem serviço ativo **sai da página** em vez de ficar oferecendo o que não dá para comprar."""
    site = servidor.removesuffix("/ops")
    adm = entrar(navegador, servidor, email="italo@urace.us")
    csrf = _csrf(adm)
    terca, quarta = _proximo(1), _proximo(2)
    antes = _desligar_os_servicos(adm, servidor)
    meus = [_criar_servico(adm, servidor, f"Adult Shifter Arrive and Drive {largura}", 899, kart="Adult Shifter")]
    # terça: manhã e tarde; quarta: só manhã (o turno único)
    assert adm.request.put(servidor + "/api/site/agenda/semana", headers=csrf,
                           data=[{"weekday": 1, "period": "manha", "open": True, "capacity": 5},
                                 {"weekday": 1, "period": "tarde", "open": True, "capacity": 5},
                                 {"weekday": 2, "period": "manha", "open": True, "capacity": 5},
                                 {"weekday": 2, "period": "tarde", "open": False, "capacity": 5}]).ok
    try:
        v = navegador.new_page(viewport={"width": largura, "height": 844})
        erros = []
        v.on("pageerror", lambda e: erros.append(str(e)))
        v.goto(site + "/services/arrive-and-drive/")
        # #263: só o Adult Shifter tem serviço ativo, então é o único kart na página
        v.locator("label.kart").first.wait_for()
        assert v.locator("label.kart:not([hidden])").count() == 1, "um serviço ativo, um kart na página"
        assert "Adult Shifter" in v.locator("label.kart").first.inner_text()
        botao = v.locator(".agenda-carrinho")
        assert not v.locator(".agenda-ir").count(), '#262: o "Continue to booking" saiu'
        # 1 · dia escolhido, turno faltando: o botão fala do turno (antes dizia "Pick a day")
        _clicar_dia(v, terca)
        assert botao.inner_text().strip() == "Pick a time to continue", botao.inner_text()
        assert botao.get_attribute("aria-disabled") == "true" and botao.is_disabled()
        assert v.locator(".agenda-turnos.falta").count() == 1, "os turnos ficam em destaque"
        assert "Morning or Afternoon" in v.locator(".agenda-aviso").inner_text()
        # 2 · com o turno, o botão é o do carrinho, com o preço e o depósito do painel
        v.get_by_role("button", name=re.compile("^Afternoon")).click()
        assert botao.inner_text().strip().startswith("Add to cart"), botao.inner_text()
        assert botao.get_attribute("aria-disabled") is None and not botao.is_disabled()
        assert "$899" in botao.inner_text(), "o preço é o do painel (#50)"
        assert not v.locator(".agenda-turnos.falta").count()
        # 3 · dia com um turno só: já vem escolhido, e a tarde do dia anterior não fica marcada
        _clicar_dia(v, quarta)
        manha = v.get_by_role("button", name=re.compile("^Morning"))
        tarde = v.get_by_role("button", name=re.compile("^Afternoon"))
        assert manha.get_attribute("aria-pressed") == "true", "um turno só aberto: escolhido sozinho"
        assert tarde.get_attribute("aria-pressed") == "false" and tarde.is_disabled()
        assert botao.inner_text().strip().startswith("Add to cart")
        # 4 · o painel tem serviço, mas nenhum é de kart do site: nenhum kart na página, e o aviso
        _ativar(adm, servidor, meus[0], False)
        meus.append(_criar_servico(adm, servidor, f"URACE test product 253 {largura}", 500))
        v.reload()
        aviso = v.locator(".agenda-indisponivel")
        aviso.first.wait_for()
        assert not v.locator('input[name="kart"]').count(), "#263: kart sem serviço não fica na página"
        assert "Online booking is closed right now" in aviso.first.inner_text()
        assert aviso.first.get_by_role("link", name=re.compile("support@urace.us")).count() == 1
        assert v.locator(".agenda-carrinho").is_hidden() or v.locator(".agenda-carrinho").is_disabled()
        # 5 · painel sem serviço nenhum: nada de botão morto, e a reserva do site diz a verdade
        _ativar(adm, servidor, meus[1], False)
        v.reload()
        aviso.first.wait_for()
        assert "Online booking is closed right now" in aviso.first.inner_text()
        r = v.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        v.goto(f"{servidor}/portal/reserve?kart=2-stroke&date={terca.isoformat()}&period=manha")
        v.get_by_role("heading", name="Book your session", level=1).wait_for()
        v.get_by_text("Online booking is closed right now").wait_for()
        assert not v.get_by_role("radio").count(), "nenhum serviço, nenhum escolhido"
        assert len([t for n, t in _cabecalhos(v) if n == 1]) == 1
        r = v.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        assert not erros, erros
        v.close()
    finally:
        for sid in meus:
            _ativar(adm, servidor, sid, False)
        for sid in antes:
            _ativar(adm, servidor, sid, True)
        adm.request.put(servidor + "/api/site/agenda/semana", headers=csrf,
                        data=[{"weekday": 1, "period": "manha", "open": False, "capacity": 5},
                              {"weekday": 1, "period": "tarde", "open": False, "capacity": 5},
                              {"weekday": 2, "period": "manha", "open": False, "capacity": 5}])
        adm.close()


def test_reserva_do_site_so_pre_seleciona_o_servico_do_kart_escolhido(servidor, navegador):
    """#253, dono 15/10 (print com "teste · teste de produto $500.00" já escolhido): com um serviço só
    no painel, a reserva escolhia esse serviço mesmo sem relação com o kart clicado no site. Agora: o
    kart sem serviço no painel não escolhe nada e a tela avisa, com o contato; o kart com serviço
    continua vindo escolhido. No celular (390 px), nada rola para o lado.

    #263: o que faz o serviço ser "do kart" é a chave "Kart do site", não o nome — um serviço chamado
    "Arrive and Drive 2-stroke" **sem** a chave não é escolhido, e um com a chave é, qualquer que seja
    o nome dele."""
    adm = entrar(navegador, servidor, email="italo@urace.us")
    csrf = _csrf(adm)
    terca = _proximo(1)
    antes = _desligar_os_servicos(adm, servidor)
    # um serviço só, que não é de nenhum kart do site: era ele que vinha escolhido (o defeito de #253)
    meus = [_criar_servico(adm, servidor, "URACE test product 253 reserva", 500)]
    assert adm.request.put(servidor + "/api/site/agenda/semana", headers=csrf,
                           data=[{"weekday": 1, "period": "manha", "open": True, "capacity": 5}]).ok
    try:
        v = navegador.new_page(viewport={"width": 390, "height": 844})
        erros = []
        v.on("pageerror", lambda e: erros.append(str(e)))
        v.goto(f"{servidor}/portal/reserve?kart=2-stroke&date={terca.isoformat()}&period=manha")
        v.get_by_role("heading", name="Book your session", level=1).wait_for()
        radio = v.get_by_role("radio", name=re.compile("URACE test product 253 reserva"))
        radio.wait_for()
        assert not radio.is_checked(), "o serviço que não é do kart nunca vem escolhido"
        # #263: nem o que tem o nome do kart no nome, se não tem a chave
        sem_chave = _criar_servico(adm, servidor, "Arrive and Drive 2-stroke sem chave", 819)
        meus.append(sem_chave)
        v.reload()
        pelo_nome = v.get_by_role("radio", name=re.compile("Arrive and Drive 2-stroke sem chave"))
        pelo_nome.wait_for()
        assert not pelo_nome.is_checked(), "o nome do kart no nome do serviço não escolhe nada (#263)"
        v.get_by_text("From the site:").wait_for()                     # a tela mostra o kart que veio do site
        assert v.get_by_text(re.compile("is not open for online booking right now")).count() == 1
        assert v.get_by_role("link", name="support@urace.us").count() >= 1
        assert v.get_by_role("button", name="Continue", exact=True).is_disabled()
        assert len([t for n, t in _cabecalhos(v) if n == 1]) == 1
        r = v.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        # o serviço com a chave do kart: aí sim já vem escolhido, e sem aviso — mesmo com um nome
        # que não fala de kart nenhum
        meus.append(_criar_servico(adm, servidor, "Sessão do 2T 253", 819, kart="2-stroke"))
        v.goto(f"{servidor}/portal/reserve?kart=2-stroke&date={terca.isoformat()}&period=manha")
        do_kart = v.get_by_role("radio", name=re.compile("Sessão do 2T 253"))
        do_kart.wait_for()
        assert do_kart.is_checked(), "o kart do site escolhe o serviço com a chave dele (#263)"
        assert not v.get_by_role("radio", name=re.compile("URACE test product 253 reserva")).is_checked()
        assert not v.get_by_role("radio", name=re.compile("Arrive and Drive 2-stroke sem chave")).is_checked()
        assert not v.get_by_text(re.compile("is not open for online booking right now")).count()
        assert v.get_by_role("button", name="Continue", exact=True).is_enabled()
        r = v.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        assert not erros, erros
        v.close()
    finally:
        for sid in meus:
            _ativar(adm, servidor, sid, False)
        for sid in antes:
            _ativar(adm, servidor, sid, True)
        adm.request.put(servidor + "/api/site/agenda/semana", headers=csrf,
                        data=[{"weekday": 1, "period": "manha", "open": False, "capacity": 5}])
        adm.close()


def test_stripe_falso_responde_404_em_caminho_desconhecido():
    """O navegador pede /favicon.ico ao Stripe falso. Antes isso estourava IndexError dentro do
    servidor de teste e sujava o log da prova (visto no pacote da VPS em 15/10, #268)."""
    import urllib.error

    fake = _StripeFalso()
    try:
        for caminho in ("/favicon.ico", "/", "/pay/nao-existe"):
            with pytest.raises(urllib.error.HTTPError) as erro:
                urllib.request.urlopen(fake.origem + caminho, timeout=5)
            assert erro.value.code == 404, caminho
    finally:
        fake.srv.shutdown()


@pytest.mark.parametrize("largura", [360, 1280])
def test_o_i_do_deposito_abre_no_toque_e_no_mouse(servidor, navegador, largura):
    """#282 (dono, 15/10): "ali no security deposit coloque um ícone de info que ao clicar com o dedo no
    celular ou passar o mouse em cima diga que o valor é reembolsável 5 dias após desde que não tenha
    nenhum dano ao kart; danos acima do valor do depósito podem ser cobrados adicionalmente".

    Na reserva e no carrinho (linha e resumo): o toque abre e o segundo toque fecha; no computador, o
    mouse em cima mostra. O texto fica inteiro na tela e nada rola para o lado."""
    site = servidor.removesuffix("/ops")
    adm = entrar(navegador, servidor, email="italo@urace.us")
    csrf = _csrf(adm)
    terca = _proximo(1)
    antes = _desligar_os_servicos(adm, servidor)
    sid = _criar_servico(adm, servidor, f"4-stroke Arrive and Drive 282 {largura}", 719, kart="4-stroke")
    assert adm.request.patch(servidor + f"/api/site/servicos/{sid}", headers=csrf, data={"deposit": 400}).ok
    assert adm.request.put(servidor + "/api/site/agenda/semana", headers=csrf,
                           data=[{"weekday": 1, "period": "manha", "open": True, "capacity": 5}]).ok
    toque = largura < 600
    try:
        ctx = navegador.new_context(viewport={"width": largura, "height": 844}, has_touch=toque, is_mobile=toque)
        v = ctx.new_page()
        erros = []
        v.on("pageerror", lambda e: erros.append(str(e)))
        v.goto(site + "/services/arrive-and-drive/")
        _clicar_dia(v, terca)
        v.get_by_role("button", name=re.compile("^Morning")).click()
        dep = v.locator(".agenda-deposito")
        dep.wait_for()
        r = v.evaluate(_VAZA)                       # fechado, o texto escondido não empurra a página
        assert not r["rola"] and not r["culpados"], r
        assert "$400" in dep.inner_text() and "refundable security deposit" in dep.inner_text()

        def confere(caixa, foto):
            botao, texto = caixa.locator(".dica-botao"), caixa.locator(".dica-texto")
            assert botao.get_attribute("aria-label") == "About the security deposit"
            b = botao.bounding_box()
            assert b["width"] >= 40 and b["height"] >= 40, "alvo de toque ≥ 40 px"
            assert not texto.is_visible()
            if toque:
                botao.tap()
            else:
                botao.hover()
            texto.wait_for(state="visible")
            assert "5 business days after your session" in texto.inner_text()
            assert "Damage above the deposit amount may be charged additionally" in texto.inner_text()
            t = texto.bounding_box()
            assert t["x"] >= 0 and t["x"] + t["width"] <= largura, f"o texto sai da tela: {t}"
            if os.environ.get("CC_FOTOS"):                         # a prova com fotos (#253)
                v.wait_for_timeout(300)                                # o fim da animação
                v.screenshot(path=os.path.join(os.environ["CC_FOTOS"], f"282-{foto}-{largura}.png"))
            if toque:
                assert botao.get_attribute("aria-expanded") == "true"
                botao.tap()                                          # o segundo toque fecha
                texto.wait_for(state="hidden")
                assert botao.get_attribute("aria-expanded") == "false"
            else:
                v.mouse.move(0, 0)
                texto.wait_for(state="hidden")

        confere(dep.locator(".dica"), "reserva")
        r = v.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        # no carrinho: a linha da sessão e o resumo
        v.locator(".agenda-carrinho").click()
        v.wait_for_url(re.compile(r"/cart/"))
        v.locator(".carrinho-linha .dica").first.wait_for()
        r = v.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        confere(v.locator(".carrinho-linha .dica").first, "carrinho-linha")
        confere(v.locator(".carrinho-total .dica").first, "carrinho-resumo")
        r = v.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        assert not erros, erros
        v.evaluate("localStorage.removeItem('urace.carrinho')")
        ctx.close()
    finally:
        _ativar(adm, servidor, sid, False)
        for s in antes:
            _ativar(adm, servidor, s, True)
        adm.request.put(servidor + "/api/site/agenda/semana", headers=csrf,
                        data=[{"weekday": 1, "period": "manha", "open": False, "capacity": 5}])
        adm.close()

def test_criar_a_conta_vindo_do_carrinho_vai_ao_carrinho_uma_vez_so(servidor, navegador):
    """#288 (CI do #283, 15/10: "A conta criada volta para o carrinho: FALHOU — net::ERR_ABORTED"). Depois
    do cadastro, a área mandava o navegador ao /cart/ e, no mesmo instante, se redesenhava conectada; com o
    `?volta=cart` ainda no endereço, ela guardava a volta de novo e mandava ao /cart/ uma SEGUNDA vez — a
    segunda ida abortava a primeira. Agora a área só navega: uma ida ao carrinho, já conectado."""
    # um visitante com o próprio IP (o Caddy repassa no X-Forwarded-For): a suíte inteira já criou contas
    # do 127.0.0.1 e o limite de cadastros por hora (MAX_CADASTROS_POR_HORA) é por IP
    ctx = navegador.new_context(viewport={"width": 1280, "height": 900},
                                extra_http_headers={"X-Forwarded-For": "203.0.113.88"})
    v = ctx.new_page()
    erros, idas = [], []
    v.on("pageerror", lambda e: erros.append(str(e)))
    v.on("request", lambda r: idas.append(r.url) if r.resource_type == "document" and r.url.endswith("/cart/") else None)

    def carrinho_lento(route):        # como numa máquina lenta: uma 2ª ida chega antes de a 1ª abrir
        time.sleep(0.8)
        route.continue_()
    v.route("**/cart/", carrinho_lento)
    v.goto(servidor + "/portal/signup?volta=cart")              # o "Create account" do carrinho leva aqui
    v.get_by_role("heading", name="Create your account", level=1).wait_for()
    v.get_by_label("Full name").fill("Teste Volta Carrinho")
    v.get_by_label("Date of birth").fill("1990-05-05")
    v.get_by_label("Email").fill("teste.volta.288@example.com")
    v.get_by_label("Password").fill("pista-molhada-7")
    v.get_by_label("Phone").fill("4075550142")
    v.get_by_label("Street address").fill("10724 Cosmonaut Blvd")
    v.get_by_label("City").fill("Orlando")
    v.get_by_role("textbox", name="State").fill("FL")
    v.get_by_label("ZIP").fill("32824")
    v.get_by_label("I accept the").check()
    v.get_by_role("button", name="Create account").click()
    v.wait_for_url("**/cart/", timeout=30000)
    v.get_by_role("heading", name="Your cart", level=1).wait_for()
    v.wait_for_timeout(500)                                      # uma segunda ida chegaria aqui
    me = v.request.get(servidor + "/api/portal/me")                   # a conta abriu a sessão
    assert me.ok and me.json()["email"] == "teste.volta.288@example.com", me.text()
    assert len(idas) == 1, f"o cadastro mandou ao carrinho {len(idas)} vezes: {idas}"
    assert not erros, erros
    ctx.close()


def test_sem_conta_os_dados_no_carrinho_viram_a_conta_e_o_checkout_abre(servidor, navegador):
    """#305 (dono, 16/10): *"ao invés de ter o botão de seguir e create account … ela vai ter que preencher as
    informações dela … Quando for para o checkout, já cria a conta dela … a pessoa recebe o um e-mail com a nossa
    identidade"*. No celular, sem conta: os dados, o piloto só com o nome, a senha confirmada e os termos no próprio
    carrinho; o checkout cria a conta, abre o Stripe (o falso), volta paga e logada; as boas-vindas chegam."""
    site = servidor.removesuffix("/ops")
    adm = entrar(navegador, servidor, email="italo@urace.us")
    csrf = _csrf(adm)
    sid = _criar_servico(adm, servidor, "4-stroke Arrive and Drive 305", 719, kart="4-stroke")
    # quinta de manhã, só para este teste
    assert adm.request.put(servidor + "/api/site/agenda/semana", headers=csrf,
                           data=[{"weekday": 3, "period": "manha", "open": True, "capacity": 5}]).ok
    quinta = _proximo(3)
    ctx = navegador.new_context(viewport={"width": 390, "height": 844}, extra_http_headers={"X-Forwarded-For": "203.0.113.105"})
    try:
        v = ctx.new_page()
        erros = []
        v.on("pageerror", lambda e: erros.append(str(e)))
        v.goto(site + "/cart/")
        v.evaluate("(i) => localStorage.setItem('urace.carrinho', JSON.stringify({v: 1, itens: i}))",
                   [{"tipo": "sessao", "servico": sid, "data": quinta.isoformat(), "turno": "manha"}])
        v.reload()
        v.get_by_role("heading", name="Your details", level=3).wait_for()
        assert not v.get_by_role("link", name="Create account").count(), 'o "Create account" saiu do carrinho'
        assert v.get_by_role("link", name="Already have an account? Sign in").count() == 1
        form = v.locator(".carrinho-cadastro")
        assert form.get_by_role("group", name="Who's driving?").is_visible(), "o carrinho tem sessão: quem pilota"
        for nome, valor in (("name", "Rita Rapida"), ("birth_date", "1985-03-03"), ("email", "rita.rapida.305@example.com"),
                            ("phone", "407 555 0177"), ("address_line1", "200 Lake St"), ("city", "Orlando"),
                            ("state", "FL"), ("zip", "32824"), ("password", "pista-molhada-7"), ("password2", "pista-molhada-8")):
            form.locator(f'[name="{nome}"]').fill(valor)
        form.get_by_text("Someone else (my child, a friend)").click()
        form.get_by_label("Driver's full name").fill("Rui Rapido")
        pagar = v.get_by_role("button", name=re.compile(r"^Checkout · \$"))
        pagar.click()
        v.get_by_text("The passwords don't match.").wait_for()
        form.locator('[name="password2"]').fill("pista-molhada-7")
        pagar.click()
        v.get_by_text("Accept the terms and the privacy policy to continue.").wait_for()
        form.get_by_label("I accept the").check()
        for largura in (390, 360):
            v.set_viewport_size({"width": largura, "height": 800})
            assert len([t for n, t in _cabecalhos(v) if n == 1]) == 1
            r = v.evaluate(_VAZA)
            assert not r["rola"] and not r["culpados"], (largura, r)
            menor = v.evaluate("""() => [...document.querySelectorAll('.carrinho button, .carrinho select, .carrinho input:not([type=radio]):not([type=checkbox]), .carrinho label.opcao')]
                .filter(e => e.offsetParent !== null).map(e => [e.getBoundingClientRect().height, (e.name || e.innerText || '').trim().slice(0, 30)])
                .filter(([h]) => h < 40)""")
            assert not menor, (largura, menor)
        pagar.click()
        v.wait_for_url(STRIPE.origem + "/pay/**")
        assert v.locator(".linha", has_text="Rui Rapido").count() == 1, "o piloto que ela escreveu vai para a sessão"
        v.get_by_role("link", name="Pay").click()
        v.get_by_role("heading", name="Payment confirmed", level=1).wait_for()
        me = v.request.get(servidor + "/api/portal/me")
        assert me.ok and me.json()["email"] == "rita.rapida.305@example.com", "volta do Stripe já logada"
        assert [d["name"] for d in me.json()["drivers"]] == ["Rui Rapido"]
        import json
        boas = [json.loads(x) for x in open(EMAILS, encoding="utf-8").read().splitlines() if "rita.rapida.305" in x]
        bv = [m for m in boas if m["subject"] == "Welcome to URACE: your account is ready"]
        assert len(bv) == 1 and "Password: pista-molhada-7" in bv[0]["text"] and "/ops/portal" in bv[0]["text"]
        r = v.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        assert not erros, erros
    finally:
        ctx.close()
        adm.request.put(servidor + "/api/site/agenda/semana", headers=csrf,
                        data=[{"weekday": 3, "period": "manha", "open": False, "capacity": 5}])
        _ativar(adm, servidor, sid, False)
        adm.close()


def test_sem_conta_duas_sessoes_cada_uma_com_o_seu_piloto(servidor, navegador):
    """#305, revisão (regra do dono: nunca pôr serviço de um cliente no card de outro). Duas sessões no carrinho sem
    conta: o carrinho pede o piloto de cada uma, e cada nome vai para a sua linha no Stripe."""
    site = servidor.removesuffix("/ops")
    adm = entrar(navegador, servidor, email="italo@urace.us")
    csrf = _csrf(adm)
    sid = _criar_servico(adm, servidor, "4-stroke Arrive and Drive 305b", 719, kart="4-stroke")
    assert adm.request.put(servidor + "/api/site/agenda/semana", headers=csrf,
                           data=[{"weekday": 3, "period": "manha", "open": True, "capacity": 5},
                                 {"weekday": 3, "period": "tarde", "open": True, "capacity": 5}]).ok
    quinta = _proximo(3)
    ctx = navegador.new_context(viewport={"width": 390, "height": 844}, extra_http_headers={"X-Forwarded-For": "203.0.113.106"})
    try:
        v = ctx.new_page()
        v.goto(site + "/cart/")
        v.evaluate("(i) => localStorage.setItem('urace.carrinho', JSON.stringify({v: 1, itens: i}))",
                   [{"tipo": "sessao", "servico": sid, "data": quinta.isoformat(), "turno": t} for t in ("manha", "tarde")])
        v.reload()
        form = v.locator(".carrinho-cadastro")
        campos = form.locator(".cad-varios-campos input")
        campos.nth(1).wait_for()
        assert campos.count() == 2 and not form.locator(".cad-um").is_visible(), "duas sessões: um nome por sessão"
        for nome, valor in (("name", "Rosa Dupla"), ("birth_date", "1983-04-04"), ("email", "rosa.dupla.305@example.com"),
                            ("phone", "407 555 0178"), ("address_line1", "300 Lake St"), ("city", "Orlando"), ("state", "FL"),
                            ("zip", "32824"), ("password", "pista-molhada-7"), ("password2", "pista-molhada-7")):
            form.locator(f'[name="{nome}"]').fill(valor)
        form.get_by_label("I accept the").check()
        campos.nth(0).fill("Caio Duplo")
        pagar = v.get_by_role("button", name=re.compile(r"^Checkout · \$"))
        pagar.click()
        v.get_by_text(re.compile("^Fill in: Driver for")).wait_for()
        campos.nth(1).fill("Clara Dupla")
        r = v.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        pagar.click()
        v.wait_for_url(STRIPE.origem + "/pay/**")
        assert v.locator(".linha", has_text="Caio Duplo").count() == 1 and v.locator(".linha", has_text="Clara Dupla").count() == 1
    finally:
        ctx.close()
        adm.request.put(servidor + "/api/site/agenda/semana", headers=csrf,
                        data=[{"weekday": 3, "period": "manha", "open": False, "capacity": 5},
                              {"weekday": 3, "period": "tarde", "open": False, "capacity": 5}])
        _ativar(adm, servidor, sid, False)
        adm.close()
def test_o_painel_do_site_mostra_as_visitas_e_as_subsecoes(servidor, navegador):
    """#306 (dono, 16/10): *"uma sessão dedicada exclusiva somente para o site … uma seção com subseções de cada
    painel de lá … E aí também do site um dashboard com as métricas dele"*. Uma pessoa (navegador de verdade, não robô)
    abre duas páginas do site; no celular, o menu tem a seção Site e o Painel do site mostra as visitas e as páginas,
    sem rolar para o lado, com cada subseção a um toque."""
    site = servidor.removesuffix("/ops")
    ctx = navegador.new_context(viewport={"width": 390, "height": 844}, user_agent=(
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"))
    v = ctx.new_page()
    v.goto(site + "/for-beginners/?utm_source=e2e306")
    v.goto(site + "/about/")
    ctx.close()
    g = entrar(navegador, servidor, largura=390, altura=844)
    try:
        abrir(g, servidor, "/site")
        g.get_by_role("heading", name="Painel do site", level=1).wait_for()
        assert g.title().startswith("Painel do site")
        g.get_by_text("Recebido pelo site").wait_for()
        assert g.get_by_role("heading", name="Páginas mais vistas", level=2).count() == 1
        assert g.get_by_text("/for-beginners/").count() >= 1 and g.get_by_text("/about/").count() >= 1
        assert g.get_by_text("e2e306").count() >= 1, "a entrada pela campanha"
        g.get_by_role("button", name="Últimos 7 dias").click()
        assert g.get_by_role("button", name="Últimos 7 dias").get_attribute("aria-pressed") == "true"
        for largura in (390, 360):
            g.set_viewport_size({"width": largura, "height": 800})
            r = g.evaluate(_VAZA)
            assert not r["rola"] and not r["culpados"], (largura, r)
            assert len([t for n, t in _cabecalhos(g) if n == 1]) == 1
        abas = g.get_by_role("navigation", name="Subseções do site")
        assert abas.get_by_role("link").count() >= 9
        abas.get_by_role("link", name="Pedidos do site").click()
        g.get_by_role("heading", name="Pedidos do site", level=1).wait_for()
        assert not g.erros_js and not g.erros_api, (g.erros_js, g.erros_api)
    finally:
        g.close()


def test_o_gerente_muda_o_nome_do_kart_no_painel_e_o_site_mostra(servidor, navegador):
    """#297 (dono, 16/10): *"os serviços que estão lá em cada página, a gente consiga alterar o valor, alterar o
    nome, alterar as coisas ali pelo Command Center"*. No celular: Site público › Serviços e preços, o cartão do
    4-stroke ganha outro nome e outra linha de baixo, e a página do Arrive and Drive mostra na hora."""
    site = servidor.removesuffix("/ops")
    g = entrar(navegador, servidor, largura=390, altura=844)
    csrf = _csrf(g)
    do_4t = next(x for x in g.request.get(servidor + "/api/site/servicos").json()["servicos"]
                 if x["site_kart"] == "4-stroke" and x["active"])
    try:
        abrir(g, servidor, "/site/servicos")
        nomes = g.get_by_label("Nome no site")
        nomes.first.wait_for()
        i = next(i for i in range(nomes.count()) if nomes.nth(i).input_value() == "4-stroke")
        cartao = nomes.nth(i).locator("xpath=ancestor::div[contains(@class, 'card-b')][1]")
        nomes.nth(i).fill("Rental 4T e2e")
        cartao.get_by_label("Linha de baixo no site").fill("Ages 8+ · e2e")
        assert cartao.get_by_label("O cliente traz o próprio kart").bounding_box()["height"] >= 16
        cartao.get_by_role("button", name="Salvar").click()
        g.get_by_text("Salvo. Vale para os próximos agendamentos.").wait_for()
        r = g.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        v = navegador.new_page(viewport={"width": 390, "height": 844})
        v.goto(site + "/services/arrive-and-drive/")
        kart = v.locator('label.kart:has(input[value="4-stroke"])')
        kart.wait_for()
        assert "Rental 4T e2e" in kart.inner_text() and "Ages 8+ · e2e" in kart.inner_text()
        v.close()
    finally:
        g.request.patch(servidor + f"/api/site/servicos/{do_4t['id']}", headers=csrf,
                        data={"site_title": do_4t["site_title"], "site_subtitle": do_4t["site_subtitle"]})
        g.close()


def test_o_gerente_muda_um_cartao_da_pagina_e_o_site_mostra(servidor, navegador):
    """#297, parte 2: Site público › Cartões das páginas, no celular. O cartão do For Beginners muda de título e de
    botão, e a página mostra; o preço {kart} é o do painel."""
    site = servidor.removesuffix("/ops")
    g = entrar(navegador, servidor, largura=390, altura=844)
    csrf = _csrf(g)
    d = g.request.get(servidor + "/api/site/cartoes").json()
    alvo = next(c for c in d["cartoes"] if c["page"] == "for-beginners" and c["title"] == "Racing Team")
    try:
        abrir(g, servidor, "/site/cartoes")
        g.get_by_role("heading", name="For Beginners", exact=False).first.wait_for()
        cartao = g.locator(f'[data-cartao="{alvo["id"]}"]')
        cartao.get_by_label("Título", exact=True).fill("Racing Team e2e")
        cartao.get_by_label("Texto do botão").fill("Join the team")
        cartao.get_by_role("button", name="Salvar").click()
        g.get_by_text("Salvo: a página do site já mostra.").wait_for()
        r = g.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        v = navegador.new_page(viewport={"width": 390, "height": 844})
        v.goto(site + "/for-beginners/")
        v.get_by_role("heading", name="Racing Team e2e", level=3).wait_for()
        assert v.get_by_role("link", name="Join the team").count() == 1
        assert f"${d['preco_kart']:g}" in v.locator(".planos").inner_text().replace(",", ""), "o {kart} é o preço do painel"
        v.close()
    finally:
        g.request.patch(servidor + f"/api/site/cartoes/{alvo['id']}", headers=csrf,
                        data={"title": alvo["title"], "button": alvo["button"]})
        g.close()


def test_o_gerente_poe_o_frete_do_produto_e_o_carrinho_cobra(servidor, navegador):
    """#298: Site público › Produtos da loja, no celular. O gerente abre um produto pelo endereço dele, põe o frete
    fixo e salva; a página do produto diz o frete, e o carrinho com "Ship to me" soma o frete × quantidade."""
    site = servidor.removesuffix("/ops")
    g = entrar(navegador, servidor, largura=390, altura=844)
    csrf = _csrf(g)
    lista = g.request.get(servidor + "/api/site/produtos?limit=200&estado=ativos").json()["produtos"]
    alvo = next(p for p in lista if not p["variations"] and p["price"] and p["in_stock"])
    try:
        abrir(g, servidor, "/site/produtos")
        g.get_by_label("Buscar").fill(alvo["name"][:20])
        g.get_by_role("link", name=alvo["name"], exact=True).first.click()
        g.wait_for_url(f"**/site/produtos/{alvo['id']}")
        g.get_by_role("heading", name=alvo["name"], level=2).wait_for()
        g.get_by_label("Frete por unidade (US$)").fill("18")
        g.get_by_role("button", name="Salvar", exact=True).click()
        g.get_by_text("Salvo: a loja do site já mostra.").wait_for()
        r = g.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        v = navegador.new_page(viewport={"width": 390, "height": 844})
        v.goto(site + f"/store/p/{alvo['slug']}/")
        v.get_by_text("shipping $18 per item").first.wait_for()
        v.locator('form.form-comprar input[name="quantidade"]').fill("2")
        v.get_by_role("button", name="Add to cart").click()
        v.goto(site + "/cart/")
        v.locator(".carrinho-linha").first.wait_for()
        v.get_by_text("Ship to me").click()
        v.locator(".carrinho-total dt", has_text="Shipping").wait_for()
        assert "$36.00" in v.locator(".carrinho-total").inner_text(), "frete × quantidade"
        assert "shipping $36.00" in v.locator(".carrinho-frete-txt").inner_text()
        r = v.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        v.close()
    finally:
        g.request.patch(servidor + f"/api/site/produtos/{alvo['id']}", headers=csrf, data={"shipping_fee": ""})
        g.close()


# ------------------------------------------------------------------ #315: o editor do site como o Canva
# Dono, 16/10: *"o editor do site ele abre uma mini visualização de como é o site público. E dali a pessoa consegue, por
# ali, clicar no que ela precisa editar. Ela edita, ela puxa, ela arrasta, ela solta, ela insere alguma coisa com o
# mouse … sem precisar de preencher cards para aquilo ali. … É como se fosse um Canva."*
_DESC_E2E = "Five days of kart racing camp in Orlando for drivers 7 and up, with coaches and karts."


def _lona(pg):
    """A prévia onde se trabalha (o iframe do editor)."""
    return pg.frame_locator("iframe.ed-iframe")


def _pagina_do_editor(pg, servidor, csrf, titulo, caminho, itens=None, **kw):
    r = pg.request.post(servidor + "/api/site/editor/paginas", headers=csrf, data={"title": titulo, "path": caminho})
    assert r.ok, r.text()
    p = r.json()["pagina"]
    if itens is not None or kw:
        r = pg.request.patch(servidor + f"/api/site/editor/paginas/{p['id']}", headers=csrf,
                             data={**({"conteudo": {"itens": itens}} if itens is not None else {}), **kw})
        assert r.ok, r.text()
    return p["id"]


def _rascunho(pg, servidor, pid):
    return pg.request.get(servidor + f"/api/site/editor/paginas/{pid}").json()["pagina"]["draft"]


def _ids(lona, col):
    return lona.locator(f'[data-ed-col="{col}"] > [data-ed-w]').evaluate_all("ns => ns.map(n => n.getAttribute('data-ed-w'))")


def _salvo(pg):
    pg.locator(".ed-salvo", has_text="salvo").wait_for()
    pg.wait_for_function("() => document.querySelector('.ed-salvo')?.textContent.trim() === 'salvo'")


def test_editor_canva_clica_no_titulo_escreve_no_lugar_desfaz_refaz_e_publica(servidor, navegador):
    """#315, computador: a página nova abre na prévia; clicar no título seleciona (a barra aparece em cima dele),
    clicar de novo escreve no lugar; Ctrl+Z volta, Ctrl+Shift+Z refaz; a descrição vai na aba Página; publica e o
    site mostra. Sem nenhum formulário de elemento."""
    site = servidor.removesuffix("/ops")
    g = entrar(navegador, servidor, largura=1280, altura=900)
    csrf = _csrf(g)
    pid = None
    try:
        abrir(g, servidor, "/site/editor")
        g.get_by_label("Título da aba").fill("Summer Kart Camp e2e")
        g.get_by_label("Endereço").fill("/summer-camp-e2e/")
        g.get_by_role("button", name="Criar e abrir").click()
        g.wait_for_url("**/site/editor/*")
        pid = int(g.url.rstrip("/").rsplit("/", 1)[1])
        lona = _lona(g)
        titulo = lona.locator('[data-ed-tipo="titulo"]').first
        titulo.wait_for()
        sem_formulario = "nenhum formulário de elemento na tela (só a aba Página tem campos)"
        assert g.locator(".ed .fld, .ed-fora .fld").count() == 0, sem_formulario
        titulo.click()
        barra = g.locator(".ed-barra")
        barra.get_by_text("Título", exact=True).wait_for()
        assert "ed-sel" in titulo.get_attribute("class")
        assert g.locator(".ed .fld, .ed-fora .fld").count() == 0, sem_formulario + ": selecionado"
        # o nome do botão começa pelo que ele mostra (quem fala com o computador diz "H1")
        assert barra.get_by_role("button", name="H1: o título da página (um só)").get_attribute("aria-pressed") == "true"
        titulo.click()                                           # de novo: escreve no lugar
        g.wait_for_function("() => document.querySelector('iframe.ed-iframe').contentDocument.querySelector('[contenteditable]')")
        assert g.locator(".ed .fld, .ed-fora .fld").count() == 0, sem_formulario + ": em edição"
        g.keyboard.press("Control+a")
        g.keyboard.type("Summer Kart Camp Canva")
        _salvo(g)
        assert "Summer Kart Camp Canva" in str(_rascunho(g, servidor, pid))
        g.keyboard.press("Control+z")
        g.wait_for_function("() => document.querySelector('iframe.ed-iframe').contentDocument.querySelector('h1').textContent.trim() === 'Summer Kart Camp e2e'")
        g.keyboard.press("Control+Shift+z")
        g.wait_for_function("() => document.querySelector('iframe.ed-iframe').contentDocument.querySelector('h1').textContent.trim() === 'Summer Kart Camp Canva'")
        _salvo(g)
        assert "Summer Kart Camp Canva" in str(_rascunho(g, servidor, pid))
        g.locator(".ed-lado").get_by_role("button", name="Camadas", exact=True).click()
        g.locator(".ed-camadas").wait_for()
        assert g.locator(".ed .fld, .ed-fora .fld").count() == 0, sem_formulario + ": nas Camadas"
        # a descrição da página (o que o Google mostra) fica na aba Página; enquanto falta, Publicar fica parado
        publicar = g.get_by_role("button", name="Publicar", exact=True)
        assert publicar.is_disabled()
        g.locator(".ed-lado").get_by_role("button", name=re.compile("^Página")).click()
        g.get_by_label("Descrição").fill(_DESC_E2E)
        _salvo(g)
        publicar.wait_for(state="visible")
        g.wait_for_function("() => ![...document.querySelectorAll('.ed-topo .btn.primary')].some(b => b.disabled)")
        publicar.click()
        g.get_by_text("Publicado: o site já mostra.").wait_for()
        assert [n for n, _ in _cabecalhos(g)].count(1) == 1, "um h1 na tela do editor"
        assert not g.erros_js and not g.erros_api, (g.erros_js, g.erros_api)
        v = navegador.new_page(viewport={"width": 390, "height": 844})
        v.goto(site + "/summer-camp-e2e/")
        v.get_by_role("heading", name="Summer Kart Camp Canva", level=1).wait_for()
        assert v.locator("[data-ed-w], [contenteditable]").count() == 0, "o site não leva nada do editor"
        for largura in (390, 360):                               # a página que o editor fez não rola para o lado
            v.set_viewport_size({"width": largura, "height": 800})
            r = v.evaluate(_VAZA)
            assert not r["rola"] and not r["culpados"], (largura, r)
        v.close()
    finally:
        if pid:
            g.request.post(servidor + f"/api/site/editor/paginas/{pid}/despublicar", headers=csrf)
        g.close()


def test_editor_canva_nao_publica_o_rascunho_velho_quando_o_salvar_falha(servidor, navegador):
    """#315: o bug do Publicar. Se o salvar falha (aqui, outra pessoa salvou antes), a tela avisa, para de salvar e o
    Publicar fica parado: nunca põe no ar um rascunho diferente do que a tela mostra."""
    g = entrar(navegador, servidor, largura=1280, altura=900)
    csrf = _csrf(g)
    pid = _pagina_do_editor(g, servidor, csrf, "Conflict Kart Camp e2e", "/conflict-camp-e2e/", description=_DESC_E2E)
    abrir(g, servidor, f"/site/editor/{pid}")
    lona = _lona(g)
    titulo = lona.locator('[data-ed-tipo="titulo"]').first
    titulo.wait_for()
    g.wait_for_function("() => ![...document.querySelectorAll('.ed-topo .btn.primary')].some(b => b.disabled)")
    # outra pessoa salva a página agora
    p = g.request.get(servidor + f"/api/site/editor/paginas/{pid}").json()["pagina"]
    assert g.request.patch(servidor + f"/api/site/editor/paginas/{pid}", headers=csrf, data={"title": "Other manager title", "rev": p["rev"]}).ok
    titulo.dblclick()
    g.keyboard.press("Control+a")
    g.keyboard.type("Mine, not saved")
    g.get_by_text("Outra pessoa (ou outra aba) salvou esta página").wait_for()
    assert g.get_by_role("button", name="Publicar", exact=True).is_disabled()
    assert "Mine, not saved" not in str(_rascunho(g, servidor, pid))
    g.close()


def test_editor_canva_arrasta_da_coluna_1_para_a_2_e_da_paleta_para_a_previa(servidor, navegador):
    """#315, computador: o mouse atravessa a prévia. Arrastar um texto da coluna 1 para a 2, e uma peça da paleta
    (Botão) para logo depois do título. A linha azul mostra onde cai; o rascunho guarda."""
    g = entrar(navegador, servidor, largura=1280, altura=900)
    csrf = _csrf(g)
    sec = {"id": "c1e2e", "tipo": "secao", "fundo": "clara", "espaco": "m", "colunas": 2, "itens": [
        [{"id": "h1e2e", "tipo": "titulo", "texto": "Drag Kart Camp", "nivel": 1}, {"id": "tx1e2e", "tipo": "texto", "html": "<p>Left column text.</p>"}],
        [{"id": "tx2e2e", "tipo": "texto", "html": "<p>Right column text.</p>"}]]}
    pid = _pagina_do_editor(g, servidor, csrf, "Drag Kart Camp e2e", "/drag-camp-e2e/", [sec])
    abrir(g, servidor, f"/site/editor/{pid}")
    g.get_by_role("button", name="Computador").click()
    lona = _lona(g)
    lona.locator('[data-ed-w="tx2e2e"]').wait_for()
    g.wait_for_timeout(300)                                   # a prévia terminou de se ajustar à largura
    a = lona.locator('[data-ed-w="tx1e2e"]').bounding_box()
    b = lona.locator('[data-ed-w="tx2e2e"]').bounding_box()
    g.mouse.move(a["x"] + 10, a["y"] + a["height"] / 2)
    g.mouse.down()
    g.mouse.move(a["x"] + 30, a["y"] + a["height"] / 2, steps=4)
    g.mouse.move(b["x"] + 20, b["y"] + b["height"] - 1, steps=12)
    assert lona.locator(".ed-solta-depois").count() == 1, "a linha mostra onde cai"
    g.mouse.up()
    g.wait_for_function("() => document.querySelector('iframe.ed-iframe').contentDocument.querySelector('[data-ed-col=\"c1e2e:1\"] [data-ed-w=\"tx1e2e\"]')")
    _salvo(g)
    d = _rascunho(g, servidor, pid)["itens"][0]["itens"]
    assert [w["id"] for w in d[0]] == ["h1e2e"] and [w["id"] for w in d[1]] == ["tx2e2e", "tx1e2e"], d
    # da paleta para logo depois do título
    pal = g.locator(".ed-peca", has_text="Botão").bounding_box()
    h1 = lona.locator('[data-ed-w="h1e2e"]').bounding_box()
    g.mouse.move(pal["x"] + 20, pal["y"] + pal["height"] / 2)
    g.mouse.down()
    g.mouse.move(pal["x"] + 60, pal["y"] + 30, steps=4)
    g.mouse.move(h1["x"] + 40, h1["y"] + h1["height"] - 3, steps=15)
    g.locator(".ed-fantasma", has_text="Botão").wait_for()
    g.mouse.up()
    g.wait_for_function("() => document.querySelector('iframe.ed-iframe').contentDocument.querySelectorAll('[data-ed-col=\"c1e2e:0\"] > [data-ed-w]').length === 2")
    assert lona.locator('[data-ed-col="c1e2e:0"] > [data-ed-w]').evaluate_all("ns => ns.map(n => n.getAttribute('data-ed-tipo'))") == ["titulo", "botao"]
    _salvo(g)
    assert [w["tipo"] for w in _rascunho(g, servidor, pid)["itens"][0]["itens"][0]] == ["titulo", "botao"]
    assert not g.erros_js and not g.erros_api, (g.erros_js, g.erros_api)
    g.close()


def test_editor_canva_no_celular_toca_para_selecionar_e_insere_tocando_no_lugar(servidor, navegador):
    """#315, celular (390, toque de verdade): tocar seleciona e a barra fica embaixo; + Inserir abre a folha, tocar na
    peça e depois tocar na página põe ali; tocar e segurar arrasta. Nada rola para o lado e todo botão tem 40 px."""
    ctx = navegador.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    g = ctx.new_page()
    g.goto(servidor + "/login")
    g.fill("#email", "eduardo@urace.us")
    g.fill("#pw", SENHA)
    g.keyboard.press("Enter")
    g.wait_for_url(lambda u: "/login" not in u, timeout=10000)
    csrf = _csrf(g)
    sec = {"id": "m1e2e", "tipo": "secao", "fundo": "escura", "espaco": "g", "colunas": 1, "itens": [[
        {"id": "mh1e2e", "tipo": "titulo", "texto": "Phone Kart Camp", "nivel": 1},
        {"id": "mtxe2e", "tipo": "texto", "html": "<p>Short words.</p>"}]]}
    pid = _pagina_do_editor(g, servidor, csrf, "Phone Kart Camp e2e", "/phone-camp-e2e/", [sec])
    abrir(g, servidor, f"/site/editor/{pid}")
    lona = _lona(g)
    lona.locator('[data-ed-w="mh1e2e"]').tap()
    doca = g.locator(".ed-doca .ed-barra")
    doca.get_by_text("Título", exact=True).wait_for()
    caixa = doca.bounding_box()
    assert caixa["y"] + caixa["height"] <= 844 and caixa["y"] > 844 / 2, f"a barra fica embaixo: {caixa}"
    r = g.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    assert not g.evaluate(_PEQUENOS), g.evaluate(_PEQUENOS)
    pequenas = g.locator(".ed-doca .ed-amostra").evaluate_all("ns => ns.filter(n => n.offsetHeight < 40).length")
    assert pequenas == 0, "as amostras de cor também têm 40 px no celular"
    assert not _estreitos(g, ".ed-doca .btn, .ed-topo .btn"), "o botão de um símbolo (P M G, ↑ ↓, ↶ ↷) também tem 40 px de largura"
    doca.get_by_role("button", name="Fechar a seleção").tap()
    g.locator(".ed-doca").get_by_role("button", name="Inserir").tap()
    g.locator(".ed-folha").get_by_role("button", name="Lista", exact=True).tap()
    g.locator(".ed-tocar", has_text="Lista").wait_for()
    t = lona.locator('[data-ed-w="mh1e2e"]').bounding_box()
    g.touchscreen.tap(t["x"] + 30, t["y"] + t["height"] - 4)           # na metade de baixo do título: logo depois dele
    g.wait_for_function("() => document.querySelector('iframe.ed-iframe').contentDocument.querySelectorAll('[data-ed-col=\"m1e2e:0\"] > [data-ed-w]').length === 3")
    assert lona.locator('[data-ed-col="m1e2e:0"] > [data-ed-w]').evaluate_all("ns => ns.map(n => n.getAttribute('data-ed-tipo'))") == ["titulo", "lista", "texto"]
    _salvo(g)
    assert [w["tipo"] for w in _rascunho(g, servidor, pid)["itens"][0]["itens"][0]] == ["titulo", "lista", "texto"]
    # tocar e segurar: o dedo arrasta a peça (o texto vai para antes da lista), sem rolar a página
    g.evaluate("document.querySelector('.ed-lona').scrollIntoView({ block: 'start' })")   # a prévia inteira à vista, longe da barra de baixo
    a = lona.locator('[data-ed-w="mtxe2e"]').bounding_box()
    b = lona.locator('[data-ed-tipo="lista"]').bounding_box()
    cdp = ctx.new_cdp_session(g)
    x0, y0 = a["x"] + 20, a["y"] + a["height"] / 2
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x0, "y": y0}]})
    g.wait_for_timeout(500)                                              # o toque longo (350 ms)
    for k in range(1, 11):
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x0, "y": y0 + (b["y"] + 2 - y0) * k / 10}]})
        g.wait_for_timeout(30)
    assert lona.locator(".ed-arrastando").count() == 1
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    g.wait_for_function("() => [...document.querySelector('iframe.ed-iframe').contentDocument.querySelectorAll('[data-ed-col=\"m1e2e:0\"] > [data-ed-w]')].map(n => n.getAttribute('data-ed-tipo')).join() === 'titulo,texto,lista'")
    _salvo(g)
    assert [w["tipo"] for w in _rascunho(g, servidor, pid)["itens"][0]["itens"][0]] == ["titulo", "texto", "lista"]
    r = g.evaluate(_VAZA)
    assert not r["rola"] and not r["culpados"], r
    # a folha Camadas: leva o foco, todo botão com 40 px (também em 360), Esc fecha e o foco volta para quem abriu
    g.locator(".ed-doca").get_by_role("button", name="Fechar a seleção").tap()
    g.locator(".ed-doca").get_by_role("button", name="Camadas").tap()
    g.locator(".ed-folha .ed-camadas").wait_for()
    assert g.evaluate("() => !!document.activeElement?.closest('.ed-folha')"), "a folha leva o foco"
    for largura in (390, 360):
        g.set_viewport_size({"width": largura, "height": 800})
        assert not _estreitos(g, ".ed-folha .btn"), (largura, _estreitos(g, ".ed-folha .btn"))
        r = g.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], (largura, r)
    g.keyboard.press("Escape")
    g.locator(".ed-folha").wait_for(state="detached")
    assert g.evaluate("() => document.activeElement?.textContent.trim()") == "Camadas", "o foco volta para quem abriu"
    ctx.close()


def test_editor_canva_so_com_o_teclado(servidor, navegador):
    """#315: tudo sem mouse. Nas Camadas, Enter escolhe; Alt+↑ sobe o elemento (e o leitor de tela ouve onde foi);
    Ctrl+Z volta; Delete apaga; ↓ vai para o próximo e Enter escreve nele."""
    g = entrar(navegador, servidor, largura=1280, altura=900)
    csrf = _csrf(g)
    sec = {"id": "k1e2e", "tipo": "secao", "fundo": "clara", "espaco": "m", "colunas": 1, "itens": [[
        {"id": "kh1e2e", "tipo": "titulo", "texto": "Keyboard Kart Camp", "nivel": 1},
        {"id": "ktxe2e", "tipo": "texto", "html": "<p>Some words.</p>"},
        {"id": "kbte2e", "tipo": "botao", "texto": "Book", "link": "/contact/"}]]}
    pid = _pagina_do_editor(g, servidor, csrf, "Keyboard Kart Camp e2e", "/keyboard-camp-e2e/", [sec])
    abrir(g, servidor, f"/site/editor/{pid}")
    lona = _lona(g)
    lona.locator('[data-ed-w="kbte2e"]').wait_for()
    aba = g.locator(".ed-lado").get_by_role("button", name="Camadas", exact=True)
    aba.focus()
    g.keyboard.press("Enter")
    item = g.locator(".ed-camadas .ed-camada-nome", has_text="Texto")
    item.focus()
    g.keyboard.press("Enter")
    assert "ed-sel" in lona.locator('[data-ed-w="ktxe2e"]').get_attribute("class")
    g.keyboard.press("Alt+ArrowUp")
    g.wait_for_function("() => [...document.querySelector('iframe.ed-iframe').contentDocument.querySelectorAll('[data-ed-col=\"k1e2e:0\"] > [data-ed-w]')].map(n => n.getAttribute('data-ed-w')).join() === 'ktxe2e,kh1e2e,kbte2e'")
    assert "movido para seção 1, posição 1" in g.locator(".ed [aria-live]").inner_text()
    g.keyboard.press("Control+z")
    g.wait_for_function("() => [...document.querySelector('iframe.ed-iframe').contentDocument.querySelectorAll('[data-ed-col=\"k1e2e:0\"] > [data-ed-w]')].map(n => n.getAttribute('data-ed-w')).join() === 'kh1e2e,ktxe2e,kbte2e'")
    g.keyboard.press("Delete")
    g.wait_for_function("() => !document.querySelector('iframe.ed-iframe').contentDocument.querySelector('[data-ed-w=\"ktxe2e\"]')")
    g.keyboard.press("Control+z")
    lona.locator('[data-ed-w="ktxe2e"]').wait_for()
    g.locator(".ed-camadas .ed-camada-nome", has_text="Texto").focus()
    g.keyboard.press("Enter")
    g.keyboard.press("ArrowDown")
    assert "ed-sel" in lona.locator('[data-ed-w="kbte2e"]').get_attribute("class")
    # o foco anda para a linha da peça nova no quadro seguinte: o Enter antes disso cairia na linha do Texto
    g.wait_for_function("() => document.activeElement?.getAttribute('data-camada') === 'kbte2e'")
    g.keyboard.press("Enter")
    g.wait_for_function("() => document.querySelector('iframe.ed-iframe').contentDocument.querySelector('[data-ed-w=\"kbte2e\"] a[contenteditable]')")
    g.keyboard.type(" now")
    g.keyboard.press("Escape")
    _salvo(g)
    ws = _rascunho(g, servidor, pid)["itens"][0]["itens"][0]
    assert [w["id"] for w in ws] == ["kh1e2e", "ktxe2e", "kbte2e"] and ws[2]["texto"] == "Book now", ws
    assert not g.erros_js and not g.erros_api, (g.erros_js, g.erros_api)
    g.close()


def _n_ws(col):
    """JS: quantos elementos a coluna `col` da prévia tem agora."""
    return f"() => document.querySelector('iframe.ed-iframe').contentDocument.querySelectorAll('[data-ed-col=\"{col}\"] > [data-ed-w]').length"


def _estreitos(pg, sel):
    """Os botões de `sel` com menos de 40 px de largura (o alvo de toque do CLAUDE.md)."""
    return pg.locator(sel).evaluate_all("ns => ns.filter(n => n.offsetWidth > 1 && n.offsetWidth < 40)"
                                        ".map(n => (n.getAttribute('aria-label') || n.textContent.trim()) + '=' + n.offsetWidth)")


def test_editor_canva_voltar_versao_limpa_os_erros_e_recusa_com_a_revisao_velha(servidor, navegador):
    """#315 (revisão): "Voltar a esta versão" tira os erros do rascunho de antes (o Publicar não fica preso num erro
    velho) e vai com a revisão da tela: se outra pessoa salvou depois, recusa e para, sem apagar o que ela fez."""
    g = entrar(navegador, servidor, largura=1280, altura=900)
    csrf = _csrf(g)
    pid = _pagina_do_editor(g, servidor, csrf, "Restore Kart Camp e2e", "/restore-camp-e2e/", description=_DESC_E2E)
    assert g.request.post(servidor + f"/api/site/editor/paginas/{pid}/publicar", headers=csrf).ok
    try:
        abrir(g, servidor, f"/site/editor/{pid}")
        _lona(g).locator('[data-ed-tipo="titulo"]').first.wait_for()
        g.locator(".ed-lado").get_by_role("button", name=re.compile("^Página")).click()
        g.get_by_label("Título da aba").fill("Restore Kart Camp " + "x" * 80)      # mais de 90 letras: o rascunho recusa
        _salvo(g)
        problemas = g.locator(".ed-problemas")
        problemas.get_by_text("título da aba: até 90 caracteres").wait_for()
        publicar = g.get_by_role("button", name="Publicar", exact=True)
        assert publicar.is_disabled()
        g.get_by_role("button", name="Ver as versões").click()
        g.get_by_role("button", name="Voltar a esta versão").first.click()
        g.get_by_text("A versão voltou para o rascunho").wait_for()
        assert g.get_by_label("Título da aba").input_value() == "Restore Kart Camp e2e"
        problemas.wait_for(state="detached")
        g.wait_for_function("() => ![...document.querySelectorAll('.ed-topo .btn.primary')].some(b => b.disabled)")
        # outra pessoa salva agora: a volta desta tela (que ficou para trás) recusa
        p = g.request.get(servidor + f"/api/site/editor/paginas/{pid}").json()["pagina"]
        assert g.request.patch(servidor + f"/api/site/editor/paginas/{pid}", headers=csrf,
                               data={"title": "Other manager restore title", "rev": p["rev"]}).ok
        g.get_by_role("button", name="Voltar a esta versão").first.click()
        g.locator(".ed-aviso").get_by_text("Outra pessoa (ou outra aba) salvou esta página").wait_for()
        assert g.request.get(servidor + f"/api/site/editor/paginas/{pid}").json()["pagina"]["title"] == "Other manager restore title"
        assert publicar.is_disabled()
        assert not g.erros_js and not g.erros_api, (g.erros_js, g.erros_api)
    finally:
        g.request.post(servidor + f"/api/site/editor/paginas/{pid}/despublicar", headers=csrf)
        g.close()


def test_editor_canva_endereco_recusado_trava_o_publicar(servidor, navegador):
    """#315 (revisão): o bug do Publicar pelo caminho de verdade. O endereço que não passa fica o de antes no rascunho e
    volta como erro; enquanto houver erro, o Publicar fica parado (senão poria no ar o endereço velho)."""
    site = servidor.removesuffix("/ops")
    g = entrar(navegador, servidor, largura=1280, altura=900)
    csrf = _csrf(g)
    pid = _pagina_do_editor(g, servidor, csrf, "Address Kart Camp e2e", "/address-camp-e2e/")
    try:
        abrir(g, servidor, f"/site/editor/{pid}")
        _lona(g).locator('[data-ed-tipo="titulo"]').first.wait_for()
        g.locator(".ed-lado").get_by_role("button", name=re.compile("^Página")).click()
        g.get_by_label("Descrição").fill(_DESC_E2E)
        g.get_by_label("Endereço").fill("/summer camp/")
        _salvo(g)
        g.locator(".ed-problemas").get_by_text("endereço: use letras").wait_for()
        publicar = g.get_by_role("button", name="Publicar", exact=True)
        assert publicar.is_disabled(), "com o endereço recusado, o Publicar poria no ar o endereço de antes"
        g.get_by_label("Endereço").fill("/address-camp-x-e2e/")
        _salvo(g)
        g.wait_for_function("() => ![...document.querySelectorAll('.ed-topo .btn.primary')].some(b => b.disabled)")
        publicar.click()
        g.get_by_text("Publicado: o site já mostra.").wait_for()
        assert g.request.get(site + "/address-camp-x-e2e/").status == 200
        assert g.request.get(site + "/address-camp-e2e/").status == 404
        assert not g.erros_js and not g.erros_api, (g.erros_js, g.erros_api)
    finally:
        g.request.post(servidor + f"/api/site/editor/paginas/{pid}/despublicar", headers=csrf)
        g.close()


def test_editor_canva_teclado_na_barra_nas_camadas_e_nos_avisos(servidor, navegador):
    """#315, só com o teclado (revisão): as abas são botões e as setas nelas não mexem na página; ↑/↓ das Camadas
    desligados quando não fazem nada; mudar de coluna nas Camadas deixa o foco na peça; a barra vem antes da prévia no
    Tab e as setas nela não andam pela página; Duplicar na barra devolve o foco à barra nova; o leitor de tela ouve o
    segundo aviso igual, e ↓ diz o que é cada peça."""
    g = entrar(navegador, servidor, largura=1280, altura=900)
    csrf = _csrf(g)
    itens = [{"id": "q1e2e", "tipo": "secao", "fundo": "clara", "espaco": "m", "colunas": 2, "itens": [
        [{"id": "qh1e2e", "tipo": "titulo", "texto": "Keys Kart Camp", "nivel": 1}, {"id": "qf1e2e", "tipo": "texto", "html": "<p>First words.</p>"}],
        [{"id": "qr1e2e", "tipo": "texto", "html": "<p>Right words.</p>"}]]},
        {"id": "q2e2e", "tipo": "secao", "fundo": "clara", "espaco": "m", "colunas": 1, "itens": [
            [{"id": "qs2e2e", "tipo": "texto", "html": "<p>Second words.</p>"}]]}]
    pid = _pagina_do_editor(g, servidor, csrf, "Keys Kart Camp e2e", "/keys-camp-e2e/", itens)
    abrir(g, servidor, f"/site/editor/{pid}")
    lona = _lona(g)
    lona.locator('[data-ed-w="qs2e2e"]').wait_for()
    foco = lambda: g.evaluate("() => { const a = document.activeElement; return { label: a?.getAttribute('aria-label') || '', "
                              "camada: a?.getAttribute('data-camada') || '', barra: !!a?.closest('.ed-barra'), body: a === document.body } }")
    aviso = lambda: g.locator(".ed > [aria-live]").evaluate("n => n.textContent")
    # as abas: botões com aria-pressed (sem role=tab pela metade); ↓ nelas não seleciona nada na página
    assert g.locator('.ed-abas [role="tab"], .ed-abas[role="tablist"]').count() == 0
    aba = g.locator(".ed-lado").get_by_role("button", name="Camadas", exact=True)
    aba.focus()
    g.keyboard.press("Enter")
    assert aba.get_attribute("aria-pressed") == "true"
    g.keyboard.press("ArrowDown")
    assert lona.locator(".ed-sel").count() == 0, "↓ na aba não mexe na seleção da página"
    # ↑/↓ das Camadas desligados quando não fazem nada (a mesma regra da barra)
    linha = lambda wid: g.locator(f'.ed-camada:has([data-camada="{wid}"])')
    assert linha("qr1e2e").get_by_role("button", name="Subir Texto").is_disabled(), "o 1º da coluna 2 da 1ª seção não sobe"
    assert linha("qs2e2e").get_by_role("button", name="Descer Texto").is_disabled(), "o último da página não desce"
    assert not linha("qf1e2e").get_by_role("button", name="Subir Texto").is_disabled()
    # mudar de coluna pelas Camadas (a linha é outra agora): o foco fica na peça
    g.locator('.ed-camadas [data-camada="qf1e2e"]').focus()
    g.keyboard.press("Enter")
    assert "ed-sel" in lona.locator('[data-ed-w="qf1e2e"]').get_attribute("class")
    g.keyboard.press("Alt+ArrowRight")
    g.wait_for_function("() => document.querySelector('iframe.ed-iframe').contentDocument.querySelector('[data-ed-col=\"q1e2e:1\"] [data-ed-w=\"qf1e2e\"]')")
    g.wait_for_function("() => document.activeElement?.getAttribute('data-camada') === 'qf1e2e'", timeout=5000)
    linha("qf1e2e").get_by_role("button", name="Texto para a coluna da esquerda").focus()
    g.keyboard.press("Enter")
    g.wait_for_function("() => document.querySelector('iframe.ed-iframe').contentDocument.querySelector('[data-ed-col=\"q1e2e:0\"] [data-ed-w=\"qf1e2e\"]')")
    g.wait_for_function("() => document.activeElement?.getAttribute('data-camada') === 'qf1e2e'", timeout=5000)
    # a barra vem antes da prévia: o Tab chega nela sem passar pelos links da página
    barra = g.locator(".ed-barra")
    barra.get_by_text("Texto", exact=True).wait_for()
    assert barra.evaluate("b => !!(b.compareDocumentPosition(document.querySelector('iframe.ed-iframe')) & Node.DOCUMENT_POSITION_FOLLOWING)")
    for _ in range(30):
        g.keyboard.press("Tab")
        if foco()["barra"]:
            break
    assert foco()["barra"], "o Tab chega na barra antes de entrar na prévia"
    # as setas na barra não andam pela página (a barra remontaria e o foco cairia no body)
    barra.get_by_role("button", name="Tamanho: Grande").focus()
    g.keyboard.press("ArrowDown")
    assert "ed-sel" in lona.locator('[data-ed-w="qf1e2e"]').get_attribute("class") and foco()["label"] == "Tamanho: Grande", foco()
    # Duplicar na barra: a peça nova fica escolhida e o foco vai para o mesmo botão na barra dela
    barra.get_by_role("button", name="Duplicar").focus()
    g.keyboard.press("Enter")
    g.wait_for_function(_n_ws("q1e2e:0") + " === 3")
    g.wait_for_function("() => document.activeElement?.closest('.ed-barra') && document.activeElement.getAttribute('aria-label') === 'Duplicar'", timeout=5000)
    # o mesmo aviso duas vezes seguidas muda o texto da região (senão o leitor de tela fica mudo)
    primeiro = aviso()
    g.keyboard.press("Control+d")
    g.wait_for_function(_n_ws("q1e2e:0") + " === 4")
    segundo = aviso()
    assert "Duplicado" in primeiro and "Duplicado" in segundo and primeiro != segundo, (primeiro, segundo)
    g.keyboard.press("Control+z")
    g.wait_for_function(_n_ws("q1e2e:0") + " === 3")
    um = aviso()
    g.keyboard.press("Control+z")
    g.wait_for_function(_n_ws("q1e2e:0") + " === 2")
    dois = aviso()
    assert "Desfeito" in um and "Desfeito" in dois and um != dois, (um, dois)
    # ↓ diz o que é e onde está: dois Textos seguidos não soam iguais
    g.locator('.ed-camadas [data-camada="qh1e2e"]').focus()
    g.keyboard.press("Enter")
    g.keyboard.press("ArrowDown")
    g.wait_for_function("() => document.querySelector('.ed > [aria-live]').textContent.includes('First words')", timeout=5000)
    a1 = aviso()
    g.keyboard.press("ArrowDown")
    g.wait_for_function("() => document.querySelector('.ed > [aria-live]').textContent.includes('Right words')", timeout=5000)
    a2 = aviso()
    assert "coluna 1" in a1 and "coluna 2" in a2, (a1, a2)
    assert not g.erros_js and not g.erros_api, (g.erros_js, g.erros_api)
    g.close()


def test_editor_canva_tela_estreita_so_com_o_teclado(servidor, navegador):
    """#315, até 900 px sem ponteiro (revisão): a folha leva o foco, prende o Tab, fecha com Esc e devolve o foco a quem
    abriu; a peça escolhida na folha Inserir entra pelo botão "Pôr no fim da página" (Enter), sem tocar na prévia."""
    g = entrar(navegador, servidor, largura=800, altura=900)
    csrf = _csrf(g)
    sec = {"id": "n1e2e", "tipo": "secao", "fundo": "clara", "espaco": "m", "colunas": 1, "itens": [[
        {"id": "nh1e2e", "tipo": "titulo", "texto": "Narrow Kart Camp", "nivel": 1},
        {"id": "ntxe2e", "tipo": "texto", "html": "<p>Narrow words.</p>"}]]}
    pid = _pagina_do_editor(g, servidor, csrf, "Narrow Kart Camp e2e", "/narrow-camp-e2e/", [sec])
    abrir(g, servidor, f"/site/editor/{pid}")
    _lona(g).locator('[data-ed-w="ntxe2e"]').wait_for()
    na_folha = "() => !!document.activeElement?.closest('.ed-folha')"
    texto_do_foco = "() => document.activeElement?.textContent.trim()"
    inserir = g.locator(".ed-doca").get_by_role("button", name="Inserir")
    inserir.focus()
    g.keyboard.press("Enter")
    g.locator(".ed-folha").wait_for()
    assert g.evaluate(na_folha), "a folha leva o foco"
    g.keyboard.press("Shift+Tab")
    assert g.evaluate(na_folha), "o Tab fica dentro da folha"
    g.keyboard.press("Tab")
    assert g.evaluate(na_folha)
    g.keyboard.press("Escape")
    g.locator(".ed-folha").wait_for(state="detached")
    assert g.evaluate(texto_do_foco) == "Inserir", "o foco volta para quem abriu a folha"
    g.keyboard.press("Enter")
    g.locator(".ed-folha").get_by_role("button", name="Título", exact=True).focus()
    g.keyboard.press("Enter")
    g.locator(".ed-tocar").wait_for()
    assert g.evaluate(texto_do_foco) == "Pôr no fim da página", "o foco vai para o botão que põe sem tocar"
    g.keyboard.press("Enter")
    g.wait_for_function(_n_ws("n1e2e:0") + " === 3")
    assert g.locator(".ed-tocar").count() == 0
    assert not g.evaluate("() => document.activeElement === document.body"), "o foco não cai no body"
    _salvo(g)
    assert [w["tipo"] for w in _rascunho(g, servidor, pid)["itens"][0]["itens"][0]] == ["titulo", "texto", "titulo"]
    assert not g.erros_js and not g.erros_api, (g.erros_js, g.erros_api)
    g.close()


def test_editor_canva_mais_pergunta_com_o_texto_em_edicao_fica(servidor, navegador):
    """#315 (revisão): "+ Pergunta" na barra com a pergunta em edição. A pergunta nova aparece na prévia e fica no
    rascunho; escrever de novo não volta a lista ao que era."""
    g = entrar(navegador, servidor, largura=1280, altura=900)
    csrf = _csrf(g)
    sec = {"id": "f1e2e", "tipo": "secao", "fundo": "clara", "espaco": "m", "colunas": 1, "itens": [[
        {"id": "fh1e2e", "tipo": "titulo", "texto": "FAQ Kart Camp", "nivel": 1},
        {"id": "fqe2e", "tipo": "faq", "itens": [{"pergunta": "How old?", "resposta": "Seven and up."}]}]]}
    pid = _pagina_do_editor(g, servidor, csrf, "FAQ Kart Camp e2e", "/faq-camp-e2e/", [sec])
    abrir(g, servidor, f"/site/editor/{pid}")
    faq = _lona(g).locator('[data-ed-w="fqe2e"]')
    em_edicao = "() => document.querySelector('iframe.ed-iframe').contentDocument.querySelector('[data-ed-w=\"fqe2e\"] summary[contenteditable]')"
    faq.locator("summary").first.dblclick()
    g.wait_for_function(em_edicao)
    g.locator(".ed-barra").get_by_role("button", name="+ Pergunta").click()
    g.wait_for_function("() => document.querySelector('iframe.ed-iframe').contentDocument.querySelectorAll('[data-ed-w=\"fqe2e\"] details').length === 2",
                        timeout=8000)
    _salvo(g)
    faq.locator("summary").first.dblclick()
    g.wait_for_function(em_edicao)
    g.keyboard.press("End")
    g.keyboard.type("!")
    _salvo(g)
    w = next(x for x in _rascunho(g, servidor, pid)["itens"][0]["itens"][0] if x["tipo"] == "faq")
    assert len(w["itens"]) == 2 and w["itens"][0]["pergunta"] == "How old?!", w
    assert not g.erros_js and not g.erros_api, (g.erros_js, g.erros_api)
    g.close()


def test_editor_canva_escrever_num_texto_antigo_guarda_a_foto_e_os_links(servidor, navegador):
    """#315 (revisão): o texto que já existia (do editor antigo) tem foto e links que o servidor aceita (http, caminho
    com +). Escrever nele na prévia não apaga nenhum deles."""
    g = entrar(navegador, servidor, largura=1280, altura=900)
    csrf = _csrf(g)
    html = ('<p>See <a href="http://example.com/map">the map</a> and <a href="/blog/a+b/">the post</a>.</p>'
            '<p><img src="https://example.com/track.webp" alt="Track"></p>')
    sec = {"id": "l1e2e", "tipo": "secao", "fundo": "clara", "espaco": "m", "colunas": 1, "itens": [[
        {"id": "lh1e2e", "tipo": "titulo", "texto": "Links Kart Camp", "nivel": 1}, {"id": "ltxe2e", "tipo": "texto", "html": html}]]}
    pid = _pagina_do_editor(g, servidor, csrf, "Links Kart Camp e2e", "/links-camp-e2e/", [sec])
    abrir(g, servidor, f"/site/editor/{pid}")
    tx = _lona(g).locator('[data-ed-w="ltxe2e"]')
    tx.locator("p").first.dblclick()
    g.wait_for_function("() => document.querySelector('iframe.ed-iframe').contentDocument.querySelector('[data-ed-w=\"ltxe2e\"][contenteditable]')")
    g.keyboard.press("Control+End")
    g.keyboard.type(" Go.")
    _salvo(g)
    h = next(x for x in _rascunho(g, servidor, pid)["itens"][0]["itens"][0] if x["id"] == "ltxe2e")["html"]
    assert "Go." in h, h
    assert 'href="http://example.com/map"' in h and 'href="/blog/a+b/"' in h, h
    assert 'src="https://example.com/track.webp"' in h and 'alt="Track"' in h, h
    assert not g.erros_js and not g.erros_api, (g.erros_js, g.erros_api)
    g.close()


def test_editor_canva_foto_solta_na_previa_abre_a_descricao(servidor, navegador):
    """#315 (revisão): uma foto do computador solta na prévia entra como imagem nova e a barra dela já abre o balão da
    descrição (o aviso pede para escrever a descrição)."""
    import base64
    import io

    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 30, 30)).save(b, "PNG")
    png = base64.b64encode(b.getvalue()).decode()
    g = entrar(navegador, servidor, largura=1280, altura=900)
    csrf = _csrf(g)
    sec = {"id": "p1e2e", "tipo": "secao", "fundo": "clara", "espaco": "m", "colunas": 1, "itens": [[
        {"id": "ph1e2e", "tipo": "titulo", "texto": "Photo Kart Camp", "nivel": 1},
        {"id": "ptxe2e", "tipo": "texto", "html": "<p>Photo words.</p>"}]]}
    pid = _pagina_do_editor(g, servidor, csrf, "Photo Kart Camp e2e", "/photo-camp-e2e/", [sec])
    abrir(g, servidor, f"/site/editor/{pid}")
    _lona(g).locator('[data-ed-w="ptxe2e"]').wait_for()
    previa = next(f for f in g.frames if "/previa" in f.url)
    previa.evaluate("""png => {
      const r = document.querySelector('[data-ed-w="ptxe2e"]').getBoundingClientRect()
      const x = r.left + 20, y = r.bottom - 3
      const dt = new DataTransfer()
      dt.items.add(new File([Uint8Array.from(atob(png), c => c.charCodeAt(0))], 'kart.png', { type: 'image/png' }))
      const alvo = document.elementFromPoint(x, y)
      for (const tipo of ['dragenter', 'dragover', 'drop'])
        alvo.dispatchEvent(new DragEvent(tipo, { dataTransfer: dt, clientX: x, clientY: y, bubbles: true, cancelable: true }))
    }""", png)
    pop = g.locator(".ed-barra .ed-pop")
    pop.wait_for(timeout=8000)
    pop.locator("input").fill("A red kart on a test photo")
    _salvo(g)
    ws = _rascunho(g, servidor, pid)["itens"][0]["itens"][0]
    assert [w["tipo"] for w in ws] == ["titulo", "texto", "imagem"], ws
    assert ws[2]["src"].startswith("/_f/") and ws[2]["alt"] == "A red kart on a test photo", ws[2]
    assert not g.erros_js and not g.erros_api, (g.erros_js, g.erros_api)
    g.close()


def _confirmar_marcador(g, rotulo):
    """#309 (revisão): mudar o marcador muda o que o site vende, e o painel pergunta antes."""
    g.get_by_role("dialog", name=re.compile("^Passar ")).get_by_role("button", name=rotulo, exact=True).click()


@pytest.mark.parametrize("largura", [360, 390])
def test_o_gerente_marca_em_estoque_liga_conta_e_a_venda_deixa_out_of_stock(servidor, navegador, largura):
    """#309 (dono, 16/10): "a gente seleciona o que que é dropshipping e o que que a gente tem em estoque … e o que tiver
    em estoque a gente coloca quanto que tem". No celular, em Site › Estoque do site, o gerente passa um produto a "em
    estoque", cria o item a partir do produto e conta 1; o cliente compra pelo Buy now (o Stripe falso) e o produto vira
    "Out of stock" no site, sem o cliente ver o marcador. O painel mostra o saldo 0, sem rolar para o lado."""
    site = servidor.removesuffix("/ops")
    g = entrar(navegador, servidor, largura=largura, altura=844)
    csrf = _csrf(g)
    lista = g.request.get(servidor + "/api/site/produtos?limit=200&estado=ativos").json()["produtos"]
    candidatos = [p for p in lista if not p["variations"] and p["price"] and p["in_stock"] and p["fulfillment"] == "dropshipping"]
    alvo = candidatos[5 if largura == 360 else 6]          # longe dos que os outros testes usam
    try:
        abrir(g, servidor, "/site/estoque")
        g.get_by_role("heading", name="Estoque do site", level=1).wait_for()
        assert g.title().startswith("Estoque do site")
        g.get_by_label("Buscar produto").fill(alvo["name"][:24])
        g.get_by_role("button", name="Buscar", exact=True).click()
        cartao = g.locator("article.cd", has=g.get_by_role("heading", name=alvo["name"], level=3))
        cartao.wait_for()
        assert cartao.locator(".cd-pill").inner_text().strip().lower() == "dropshipping"
        cartao.get_by_role("button", name="Passar a em estoque").click()
        _confirmar_marcador(g, "Passar a em estoque")
        g.get_by_text("Marcado como em estoque.", exact=False).wait_for()
        cartao.get_by_text("falta ligar ao estoque").wait_for()
        cartao.get_by_role("button", name=re.compile("^Ligar ")).click()
        painel = g.get_by_role("dialog")
        painel.get_by_role("heading", name=re.compile("^Ligar ao estoque"), level=3).wait_for()
        painel.get_by_role("button", name="Criar item", exact=True).click()
        painel.get_by_label("Quanto tem no Galpão agora").fill("1")
        r = g.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], ("painel", r)
        painel.get_by_role("button", name="Ligar e contar").click()
        g.get_by_text("Ligado: o site já vende pelo estoque.").wait_for()
        cartao.locator(".cd-grande", has_text="1").wait_for()
        r = g.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        assert len([t for n, t in _cabecalhos(g) if n == 1]) == 1
        assert g.evaluate("[...document.querySelectorAll('.cd .btn')].every(b => b.offsetHeight >= 40)"), "toque de 40 px"
        # o cliente compra a única unidade
        ctx = navegador.new_context(viewport={"width": largura, "height": 780})
        v = ctx.new_page()
        cliente_pela_api(v, servidor, "Rui Estoque", f"rui.estoque.{largura}.e2e@example.com", ip=f"10.3.9.{largura % 250}")
        v.goto(site + f"/store/p/{alvo['slug']}/")
        html = v.content()
        assert "dropshipping" not in html.lower() and "Out of stock" not in html, "o cliente não vê o marcador"
        v.get_by_role("button", name="Buy now").click()
        v.wait_for_url(STRIPE.origem + "/pay/**")
        v.get_by_role("link", name="Pay").click()
        v.get_by_role("heading", name="Payment confirmed", level=1).wait_for()
        ctx.close()
        ctx = navegador.new_context(viewport={"width": largura, "height": 780})          # sem o cache da página de antes
        v = ctx.new_page()
        v.goto(site + f"/store/p/{alvo['slug']}/")
        v.get_by_text("Out of stock").first.wait_for()
        assert v.get_by_role("button", name="Buy now").count() == 0
        ctx.close()
        abrir(g, servidor, "/site/estoque")
        g.get_by_role("button", name=re.compile("^Sem saldo")).click()
        cartao = g.locator("article.cd", has=g.get_by_role("heading", name=alvo["name"], level=3))
        cartao.locator(".cd-grande", has_text="0").wait_for()
        r = g.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        # Pedidos do site diz o que saiu do estoque, para a equipe separar (revisão do PR #320)
        abrir(g, servidor, "/site/pedidos")
        pedido = g.locator(".card", has_text=f"rui.estoque.{largura}.e2e@example.com").first
        pedido.get_by_text("baixou 1 do estoque", exact=False).wait_for()
        r = g.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        assert not g.erros_js and not g.erros_api, (g.erros_js, g.erros_api)
    finally:
        g.request.delete(servidor + f"/api/site/estoque/{alvo['id']}/ligar", headers=csrf)
        g.request.patch(servidor + f"/api/site/produtos/{alvo['id']}", headers=csrf, data={"fulfillment": "dropshipping"})
        g.close()


def _produtos_para_estoque(g, servidor):
    """Os produtos simples, com preço, à venda e em dropshipping (o padrão): o que os testes do Estoque do site usam."""
    lista = g.request.get(servidor + "/api/site/produtos?limit=200&estado=ativos").json()["produtos"]
    return [p for p in lista if not p["variations"] and p["price"] and p["in_stock"] and p["fulfillment"] == "dropshipping"]


def _sem_o(candidatos, p):
    return [x for x in candidatos if x["id"] != p["id"]]


def test_estoque_do_site_mostra_cada_local_liga_sem_inflar_e_o_dropshipping_desliga(servidor, navegador):
    """Revisão do PR #320, no celular de 360×640: a lista de itens do painel Ligar não encolhe (era 10 px); o item que já
    tem Galpão 5 + Pista 3 liga sem contar (o saldo fica 8, não 11), a tela mostra "Galpão 5 · Pista 3" e o campo vem
    com o saldo de cada local; o produto passado a dropshipping ainda mostra a ligação e o Desligar (o item ficava
    preso), e a lista do Ligar diz "ligado a X (dropshipping)". Nada rola para o lado."""
    g = entrar(navegador, servidor, largura=360, altura=640)
    csrf = _csrf(g)
    candidatos = _produtos_para_estoque(g, servidor)
    alvo, outro = candidatos[7], candidatos[8]
    itens = []
    for n in range(1, 9):                      # oito itens parecidos: a lista passa da altura do painel
        r = g.request.post(servidor + "/api/estoque/item", headers=csrf,
                           form={"name": f"Peça Revisão Ligar E2E {n}", "kind": "peca", "category": "outros"})
        assert r.ok, r.text()
        itens.append(r.json()["id"])
    item = itens[0]
    for qtd, local in ((5, "sede"), (3, "pista")):
        assert g.request.post(servidor + "/api/estoque/contar", headers=csrf, data={"item_id": item, "qty": qtd, "local": local}).ok
    for p in (alvo, outro):
        assert g.request.patch(servidor + f"/api/site/produtos/{p['id']}", headers=csrf, data={"fulfillment": "estoque"}).ok
    try:
        abrir(g, servidor, "/site/estoque")
        g.get_by_label("Buscar produto").fill(alvo["name"][:24])
        g.get_by_role("button", name="Buscar", exact=True).click()
        cartao = g.locator("article.cd", has=g.get_by_role("heading", name=alvo["name"], level=3))
        cartao.get_by_role("button", name=re.compile("^Ligar ")).click()
        painel = g.get_by_role("dialog")
        painel.get_by_label("Buscar no estoque").fill("Revisao Ligar E2E")
        painel.get_by_role("button", name="Buscar", exact=True).click()
        painel.locator(".es-itens li").nth(7).wait_for()
        altura = g.evaluate("document.querySelector('.es-itens').getBoundingClientRect().height")
        assert altura >= 150, f"a lista do Ligar encolheu para {altura:.0f} px"
        painel.locator("label.es-item", has_text="Peça Revisão Ligar E2E 1").first.click()
        painel.locator("label.es-item", has_text="Peça Revisão Ligar E2E 1").first.get_by_text("Galpão 5 · Pista 3").wait_for()
        campo = painel.get_by_label("Quanto tem no Galpão agora")
        assert campo.input_value() == "5", "o campo vem com o saldo do Galpão, não com a soma"
        painel.get_by_role("combobox", name=re.compile("^Onde")).select_option("pista")
        assert painel.get_by_label("Quanto tem na Pista agora").input_value() == "3"
        r = g.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], ("painel Ligar", r)
        painel.get_by_role("button", name="Ligar", exact=True).click()
        g.get_by_text("Ligado: o site já vende pelo estoque.").wait_for()
        assert g.request.get(servidor + f"/api/estoque/{item}").json()["nosso"] == 8.0, "ligar não infla o saldo"
        cartao.get_by_text("Galpão 5 · Pista 3").wait_for()
        cartao.get_by_role("button", name=re.compile("^Contar ")).click()
        painel = g.get_by_role("dialog")
        assert painel.get_by_label("Quanto tem no Galpão agora").input_value() == "5"
        painel.get_by_role("combobox", name=re.compile("^Onde")).select_option("pista")
        painel.get_by_label("Quanto tem na Pista agora").fill("4")
        painel.get_by_role("button", name="Salvar a contagem").click()
        g.get_by_text("Contado: 3 → 4.").wait_for()
        cartao.get_by_text("Galpão 5 · Pista 4").wait_for()
        assert g.request.get(servidor + f"/api/estoque/{item}").json()["nosso"] == 9.0
        r = g.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        assert g.evaluate("[...document.querySelectorAll('.cd .btn')].every(b => b.offsetHeight >= 40)"), "toque de 40 px"
        # dropshipping com a ligação: o cartão mostra o item e o Desligar; o Ligar de outro produto diz onde ele está
        cartao.get_by_role("button", name="Passar a dropshipping").click()
        _confirmar_marcador(g, "Passar a dropshipping")
        cartao.locator(".cd-pill", has_text="Dropshipping").wait_for()
        cartao.get_by_text("Peça Revisão Ligar E2E 1", exact=False).wait_for()
        g.get_by_label("Buscar produto").fill(outro["name"][:24])
        g.get_by_role("button", name="Buscar", exact=True).click()
        cartao2 = g.locator("article.cd", has=g.get_by_role("heading", name=outro["name"], level=3))
        cartao2.get_by_role("button", name=re.compile("^Ligar ")).click()
        painel = g.get_by_role("dialog")
        painel.get_by_label("Buscar no estoque").fill("Revisao Ligar E2E 1")
        painel.get_by_role("button", name="Buscar", exact=True).click()
        painel.get_by_text(f"ligado a {alvo['name']} (dropshipping)").wait_for()
        painel.get_by_role("button", name="Cancelar").click()
        g.get_by_label("Buscar produto").fill(alvo["name"][:24])
        g.get_by_role("button", name="Buscar", exact=True).click()
        cartao.get_by_role("button", name=re.compile("^Desligar ")).click()
        g.get_by_role("dialog", name=re.compile("^Desligar")).get_by_role("button", name="Desligar", exact=True).click()
        g.get_by_text("Desligado.").wait_for()
        cartao.get_by_role("button", name=re.compile("^Desligar ")).wait_for(state="detached")
        r = g.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        assert not g.erros_js and not g.erros_api, (g.erros_js, g.erros_api)
    finally:
        for p in (alvo, outro):
            g.request.delete(servidor + f"/api/site/estoque/{p['id']}/ligar", headers=csrf)
            g.request.patch(servidor + f"/api/site/produtos/{p['id']}", headers=csrf, data={"fulfillment": "dropshipping"})
        g.close()


def test_estoque_do_site_a_pagina_nao_volta_a_toa_e_abre_filtrado_pelo_produto(servidor, navegador):
    """Revisão do PR #320: numa página com um cartão só, ligar (o cartão continua no filtro) não volta uma página: só
    volta quando a página fica vazia. E "Ligar em Estoque do site" (no produto) abre /site/estoque/<endereço> já
    filtrado no produto."""
    g = entrar(navegador, servidor, largura=390, altura=844)
    csrf = _csrf(g)
    candidatos = _produtos_para_estoque(g, servidor)
    alvo = candidatos[9]
    marcados = []

    def marcar(p):
        assert g.request.patch(servidor + f"/api/site/produtos/{p['id']}", headers=csrf, data={"fulfillment": "estoque"}).ok
        marcados.append(p)
    try:
        # 21 "em estoque": a segunda página tem um cartão só
        ja = g.request.get(servidor + "/api/site/estoque?modo=estoque&limit=1").json()["total"]
        for p in _sem_o(candidatos, alvo)[10:10 + 21 - ja]:
            marcar(p)
        abrir(g, servidor, "/site/estoque")
        g.get_by_role("button", name=re.compile("^Em estoque · 21$")).click()
        g.get_by_text("1–20 de 21").wait_for()
        g.get_by_role("button", name="Próximas").click()
        g.get_by_text("21–21 de 21").wait_for()
        cartao = g.locator("article.cd")
        cartao.nth(1).wait_for(state="detached")             # a página 2 chegou: um cartão só
        assert cartao.count() == 1
        nome = cartao.locator("h3").inner_text()
        cartao.get_by_role("button", name=re.compile("^Ligar ")).click()
        painel = g.get_by_role("dialog")
        painel.get_by_role("button", name="Criar item", exact=True).click()
        painel.get_by_label(re.compile("^Quanto tem")).fill("1")
        painel.get_by_role("button", name="Ligar e contar").click()
        g.get_by_text("Ligado: o site já vende pelo estoque.").wait_for()
        g.locator("article.cd", has=g.get_by_role("heading", name=nome, level=3)).locator(".cd-grande", has_text="1").wait_for()
        assert g.get_by_text("21–21 de 21").is_visible(), "o cartão continua no filtro: a página fica"
        # passar a dropshipping tira o cartão do filtro: a página vazia volta para a anterior
        g.get_by_role("button", name="Passar a dropshipping").click()
        _confirmar_marcador(g, "Passar a dropshipping")
        g.get_by_role("button", name=re.compile("^Em estoque · 20$")).wait_for()
        g.locator("article.cd").nth(19).wait_for()
        assert g.locator("article.cd").count() == 20 and g.get_by_role("button", name="Próximas").count() == 0
        r = g.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        # o link do produto abre o Estoque do site já filtrado nele, no endereço limpo
        marcar(alvo)
        abrir(g, servidor, f"/site/produtos/{alvo['id']}")
        g.get_by_role("link", name="Ligar em Estoque do site").click()
        g.wait_for_url(f"**/site/estoque/{alvo['slug']}")
        assert g.get_by_label("Buscar produto").input_value() == alvo["slug"]
        g.locator("article.cd", has=g.get_by_role("heading", name=alvo["name"], level=3)).wait_for()
        assert g.title().startswith("Estoque do site")
        assert not g.erros_js and not g.erros_api, (g.erros_js, g.erros_api)
    finally:
        for p in marcados:
            g.request.delete(servidor + f"/api/site/estoque/{p['id']}/ligar", headers=csrf)
            g.request.patch(servidor + f"/api/site/produtos/{p['id']}", headers=csrf, data={"fulfillment": "dropshipping"})
        g.close()


def test_pago_sem_estoque_o_operador_marca_resolvido_e_o_painel_zera(servidor, navegador):
    """Revisão do PR #320: o pedido pago sem estoque (alguém contou 0 enquanto o cliente pagava) mostra "Resolver: sem
    estoque" e o botão Resolvido em Pedidos do site; resolvido, sai do pedido e o "Pagos sem estoque" do Painel do site
    volta a zero."""
    site = servidor.removesuffix("/ops")
    g = entrar(navegador, servidor, largura=360, altura=780)
    csrf = _csrf(g)
    alvo = _produtos_para_estoque(g, servidor)[11]
    try:
        assert g.request.post(servidor + f"/api/site/estoque/{alvo['id']}/ligar", headers=csrf,
                              data={"criar": {"name": "Peça Resolver E2E"}, "contagem": 1}).ok
        ctx = navegador.new_context(viewport={"width": 360, "height": 780})
        v = ctx.new_page()
        cliente_pela_api(v, servidor, "Rita Resolve", "rita.resolve.e2e@example.com", ip="10.3.9.77")
        v.goto(site + f"/store/p/{alvo['slug']}/")
        v.get_by_role("button", name="Buy now").click()
        v.wait_for_url(STRIPE.origem + "/pay/**")
        assert g.request.post(servidor + f"/api/site/estoque/{alvo['id']}/contar", headers=csrf, data={"qty": 0}).ok
        v.get_by_role("link", name="Pay").click()
        v.get_by_role("heading", name="Payment confirmed", level=1).wait_for()
        ctx.close()
        assert g.request.get(servidor + "/api/site/painel").json()["atencao"]["pedidos_sem_estoque"] == 1
        abrir(g, servidor, "/site/pedidos")
        conta = "rita.resolve.e2e@example.com"
        pedido = g.locator(".card", has_text=conta).filter(has_text="Resolver:").first
        pedido.get_by_text("sem estoque", exact=False).first.wait_for()
        r = g.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        pedido.get_by_role("button", name=re.compile("^Resolvido")).click()
        g.get_by_role("dialog", name=re.compile("^O sem estoque")).get_by_role("button", name="Resolvido", exact=True).click()
        g.get_by_text("Resolvido: saiu do Painel do site.").wait_for()
        g.locator(".card", has_text=conta).first.get_by_role("button", name=re.compile("^Resolvido")).wait_for(state="detached")
        assert g.locator(".card", has_text=conta).filter(has_text="Resolver:").count() == 0
        assert g.request.get(servidor + "/api/site/painel").json()["atencao"]["pedidos_sem_estoque"] == 0
        assert not g.erros_js and not g.erros_api, (g.erros_js, g.erros_api)
    finally:
        g.request.delete(servidor + f"/api/site/estoque/{alvo['id']}/ligar", headers=csrf)
        g.request.patch(servidor + f"/api/site/produtos/{alvo['id']}", headers=csrf, data={"fulfillment": "dropshipping"})
        g.close()


def test_estoque_do_site_confirma_o_marcador_pagina_os_itens_e_solta_o_item_na_busca_nova(servidor, navegador):
    """Workflow da revisão do PR #320: mudar o marcador pede confirmação (Cancelar não muda nada); a lista do Ligar
    passa de 12 itens com Anteriores/Próximas; e a busca nova solta o item escolhido, que antes era ligado sem estar na
    tela."""
    g = entrar(navegador, servidor, largura=390, altura=844)
    csrf = _csrf(g)
    alvo = _produtos_para_estoque(g, servidor)[12]
    for n in range(1, 15):
        assert g.request.post(servidor + "/api/estoque/item", headers=csrf,
                              form={"name": f"Peça Paginada E2E {n:02d}", "kind": "peca", "category": "outros"}).ok
    try:
        abrir(g, servidor, f"/site/estoque/{alvo['slug']}")
        cartao = g.locator("article.cd", has=g.get_by_role("heading", name=alvo["name"], level=3))
        cartao.get_by_role("button", name="Passar a em estoque").click()
        dlg = g.get_by_role("dialog", name=re.compile("^Passar "))
        dlg.get_by_text("Galpão + Pista", exact=False).wait_for()
        dlg.get_by_role("button", name="Cancelar").click()
        assert cartao.locator(".cd-pill").inner_text().strip().lower() == "dropshipping", "Cancelar não muda o marcador"
        cartao.get_by_role("button", name="Passar a em estoque").click()
        _confirmar_marcador(g, "Passar a em estoque")
        g.get_by_text("Marcado como em estoque.", exact=False).wait_for()
        cartao.get_by_role("button", name=re.compile("^Ligar ")).click()
        painel = g.get_by_role("dialog")
        painel.get_by_label("Buscar no estoque").fill("Paginada E2E")
        painel.get_by_role("button", name="Buscar", exact=True).click()
        painel.get_by_text("1–12 de 14 itens").wait_for()
        painel.get_by_role("button", name="Próximas").click()
        painel.get_by_text("13–14 de 14 itens").wait_for()
        painel.locator("label.es-item", has_text="Peça Paginada E2E 14").wait_for()
        painel.get_by_role("button", name="Anteriores").click()
        painel.locator("label.es-item", has_text="Peça Paginada E2E 01").click()
        painel.get_by_label("Buscar no estoque").fill("Zzz Inexistente E2E")
        painel.get_by_role("button", name="Buscar", exact=True).click()
        painel.get_by_text("Nenhum item com esse nome", exact=False).wait_for()
        painel.get_by_label(re.compile("^Quanto tem")).fill("1")
        painel.get_by_role("button", name="Ligar e contar").click()
        g.get_by_text("Escolha o item do estoque.").wait_for()
        ligado = g.request.get(servidor + f"/api/site/produtos/{alvo['id']}").json()["produto"]["estoque"]["ligados"]
        assert not ligado, "a busca nova soltou o item: nada foi ligado sem estar na tela"
        r = g.evaluate(_VAZA)
        assert not r["rola"] and not r["culpados"], r
        assert not g.erros_js and not g.erros_api, (g.erros_js, g.erros_api)
    finally:
        g.request.delete(servidor + f"/api/site/estoque/{alvo['id']}/ligar", headers=csrf)
        g.request.patch(servidor + f"/api/site/produtos/{alvo['id']}", headers=csrf, data={"fulfillment": "dropshipping"})
        g.close()


# ------------------------------------------------------------------ blog do site (#172)
_ALVOS_DO_SITE = """() => [...document.querySelectorAll('main a, main button, main label.kart, header a, header summary')]
    .filter(e => e.offsetParent !== null && !e.closest('p, li, dd, address, .post-corpo'))   // link no meio do texto não é botão
    .map(e => [e.getBoundingClientRect().height, (e.innerText || e.getAttribute('aria-label') || '').trim().slice(0, 30)])
    .filter(([h]) => h < 40)"""


def test_blog_o_operador_escreve_o_admin_publica_e_o_artigo_cabe_no_celular(servidor, navegador, tmp_path):
    """#172 (dono, 16/10: "editor do blog, pode seguir"): Site › Blog no celular. O operador cria o artigo pelo "Novo
    artigo" (em cima), escreve, sobe a capa e salva o rascunho, mas não publica; o administrador publica, e o artigo sai
    em /blog/<slug>/ com um h1, sem rolar para o lado e com alvo de toque de 40 px em 360 e 390 px."""
    from PIL import Image
    site = servidor.removesuffix("/ops")
    url = "/blog/kart-racing-line-for-beginners-e2e/"
    op = entrar(navegador, servidor, "op@urace.us", largura=390, altura=844)
    adm, pid = None, None
    try:
        abrir(op, servidor, "/site/blog")
        op.get_by_role("heading", name="Blog", level=1).wait_for()
        titulos = [t for n, t in _cabecalhos(op) if n == 2]
        assert titulos.index("Novo artigo") < next(i for i, t in enumerate(titulos) if t.startswith("Artigos")), \
            "a inserção fica em cima (dono)"
        novo = op.locator("section.card", has=op.get_by_role("heading", name="Novo artigo"))
        novo.get_by_label("Título do artigo").fill("Kart Racing Line for Beginners e2e")
        novo.get_by_label("Categoria do artigo").select_option("training-racing")
        novo.get_by_role("button", name="Criar e abrir").click()
        op.wait_for_url(re.compile(r".*/site/blog/\d+$"))
        pid = int(op.url.rstrip("/").rsplit("/", 1)[1])
        op.get_by_label("Resumo").fill("Braking point, apex and exit: the racing line for your first day on track.")
        op.get_by_label("Descrição para o Google").fill("How to drive the racing line in a kart in Orlando: braking point, apex and exit, "
                                                     "explained by a URACE coach.")
        op.get_by_role("textbox", name="Texto do artigo").fill("Brake in a straight line, turn in late and look at the exit.")
        foto = tmp_path / "capa.png"
        Image.new("RGB", (2000, 1000), (200, 30, 30)).save(foto)
        op.get_by_label("Subir a capa").set_input_files(str(foto))
        op.get_by_text("Capa salva no rascunho").wait_for()
        op.get_by_label("Descrição da capa").fill("A red kart at the apex")
        op.get_by_role("button", name="Salvar rascunho").click()
        op.get_by_text("Rascunho salvo.").wait_for()
        assert op.get_by_role("button", name="Publicar", exact=True).count() == 0, "o operador não publica"
        assert op.get_by_text("Só o administrador publica").count() == 1
        assert op.request.post(servidor + f"/api/site/blog/{pid}/publicar", headers=_csrf(op)).status == 403
        assert op.request.get(site + url).status == 404, "rascunho fora do site"
        op.locator('iframe[title="Prévia do artigo"]').wait_for()
        for largura in (390, 360):
            op.set_viewport_size({"width": largura, "height": 800})
            r = op.evaluate(_VAZA)
            assert not r["rola"] and not r["culpados"], (largura, r)
        assert not op.erros_js and not op.erros_api, (op.erros_js, op.erros_api)

        adm = entrar(navegador, servidor, "italo@urace.us", largura=390, altura=844)
        abrir(adm, servidor, f"/site/blog/{pid}")
        adm.get_by_role("button", name="Publicar", exact=True).click()
        adm.get_by_text("Publicado: o blog e o mapa do site já mostram.").wait_for()
        assert f"<loc>https://127.0.0.1{url}</loc>" in adm.request.get(site + "/sitemap.xml").text(), "no mapa do site na hora"
        for largura in (360, 390):
            v = navegador.new_page(viewport={"width": largura, "height": 800})
            erros = []
            v.on("pageerror", lambda e: erros.append(str(e)))
            v.goto(site + url)
            v.wait_for_load_state("networkidle")
            assert [t for n, t in _cabecalhos(v) if n == 1] == ["Kart Racing Line for Beginners e2e"], largura
            r = v.evaluate(_VAZA)
            assert not r["rola"] and not r["culpados"], (largura, r)
            assert not v.evaluate(_ALVOS_DO_SITE), (largura, v.evaluate(_ALVOS_DO_SITE))
            assert v.locator("img.post-capa").get_attribute("alt") == "A red kart at the apex"
            assert not erros, erros
            v.close()
        assert not adm.erros_js and not adm.erros_api, (adm.erros_js, adm.erros_api)
    finally:
        if pid and adm:
            adm.request.post(servidor + f"/api/site/blog/{pid}/despublicar", headers=_csrf(adm), data={"confirmar": True})
        op.close()
        if adm:
            adm.close()


def _artigo_novo(op, servidor, titulo):
    """Um rascunho criado pela tela "Novo artigo"; devolve o id (a tela já abre nele)."""
    abrir(op, servidor, "/site/blog")
    novo = op.locator("section.card", has=op.get_by_role("heading", name="Novo artigo"))
    novo.get_by_label("Título do artigo").fill(titulo)
    novo.get_by_role("button", name="Criar e abrir").click()
    op.wait_for_url(re.compile(r".*/site/blog/\d+$"))
    return int(op.url.rstrip("/").rsplit("/", 1)[1])


def test_blog_enter_texto_colado_e_link_para_a_home_ficam_no_editor(servidor, navegador):
    """Revisão do #172: o Enter do Chrome criava <div> e o texto colado de uma página vem em <div>; o servidor jogava a
    div fora e os parágrafos grudavam ao salvar. E o link para a home ("/") era recusado na tela e no servidor."""
    op = entrar(navegador, servidor, "op@urace.us", largura=390, altura=844)
    op.context.grant_permissions(["clipboard-read", "clipboard-write"])
    try:
        pid = _artigo_novo(op, servidor, "Enter and Paste Test e2e")
        caixa = op.get_by_role("textbox", name="Texto do artigo")
        caixa.click()
        op.keyboard.type("First paragraph of the article.")
        op.keyboard.press("Enter")
        op.keyboard.type("Second paragraph of the article.")
        op.keyboard.press("Enter")
        op.keyboard.type("Third one.")
        op.keyboard.press("Enter")
        colado = ('<div>Paragraph one from a web page.</div><div>Paragraph two from a web page.</div>'
                  '<img src="x" onerror="window.__xss=1"><a href="javascript:window.__xss=2">bad</a>')
        op.evaluate("""async (h) => { await navigator.clipboard.write([new ClipboardItem({
            'text/html': new Blob([h], {type: 'text/html'}), 'text/plain': new Blob(['x'], {type: 'text/plain'})})]) }""", colado)
        op.keyboard.press("Control+V")
        op.get_by_role("button", name="Link", exact=True).click()
        pergunta = op.get_by_role("dialog", name="Link")
        pergunta.locator("input").fill("/")
        pergunta.get_by_role("button", name="Pôr o link").click()
        assert op.get_by_text("Use um endereço que comece com").count() == 0, "a tela aceita / (a home)"
        op.get_by_role("button", name="Salvar rascunho").click()
        op.get_by_text("Rascunho salvo.").wait_for()
        salvo = op.request.get(servidor + f"/api/site/blog/{pid}").json()["post"]["draft"]["html"]
        for par in ("First paragraph of the article.", "Second paragraph of the article.", "Third one.",
                    "Paragraph one from a web page.", "Paragraph two from a web page."):
            assert f"<p>{par}</p>" in salvo, (par, salvo)
        assert 'href="/"' in salvo, salvo
        assert "javascript" not in salvo and "onerror" not in salvo and op.evaluate("window.__xss") is None
        assert not op.erros_js and not op.erros_api, (op.erros_js, op.erros_api)
    finally:
        op.close()


def test_blog_o_admin_so_publica_o_que_viu(servidor, navegador):
    """Revisão do #172: o admin abre o artigo e a prévia, o operador salva outro texto, o admin clica Publicar. Antes ia
    ao ar o que ele nunca viu; agora a tela recebe 409, recarrega o artigo e avisa, e só o segundo clique publica."""
    site = servidor.removesuffix("/ops")
    url = "/blog/review-before-publishing-e2e/"
    op = entrar(navegador, servidor, "op@urace.us", largura=390, altura=844)
    adm, pid = None, None
    try:
        pid = _artigo_novo(op, servidor, "Review Before Publishing e2e")
        r = op.request.patch(servidor + f"/api/site/blog/{pid}", headers=_csrf(op), data={
            "description": "What the admin reviews before a kart article goes live on the URACE site, step by step.",
            "html": "<p>The text the admin reviewed.</p>"})
        assert r.ok, r.text()
        adm = entrar(navegador, servidor, "italo@urace.us", largura=390, altura=844)
        abrir(adm, servidor, f"/site/blog/{pid}")
        adm.get_by_role("textbox", name="Texto do artigo").get_by_text("The text the admin reviewed.").wait_for()
        r = op.request.patch(servidor + f"/api/site/blog/{pid}", headers=_csrf(op), data={
            "title": "Changed After the Admin Opened e2e", "html": "<p>A text the admin never saw.</p>"})
        assert r.ok, r.text()
        adm.get_by_role("button", name="Publicar", exact=True).click()
        adm.get_by_text("O rascunho mudou depois que você abriu o artigo.").wait_for()
        assert adm.request.get(site + url).status == 404, "nada foi ao ar"
        adm.get_by_role("heading", name="Changed After the Admin Opened e2e", level=2).wait_for()
        adm.get_by_role("textbox", name="Texto do artigo").get_by_text("A text the admin never saw.").wait_for()
        adm.get_by_role("button", name="Publicar", exact=True).click()
        adm.get_by_text("Publicado: o blog e o mapa do site já mostram.").wait_for()
        pg = adm.request.get(site + url)
        assert pg.status == 200 and "A text the admin never saw." in pg.text()
        assert not adm.erros_js and not adm.erros_api, (adm.erros_js, adm.erros_api)
    finally:
        if pid and adm:
            adm.request.post(servidor + f"/api/site/blog/{pid}/despublicar", headers=_csrf(adm), data={"confirmar": True})
        op.close()
        if adm:
            adm.close()

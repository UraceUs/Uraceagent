"""Abrir o link do e-mail como uma pessoa abriria, e ler o que a página diz (dono, 06/10).

"vai chegar também, provavelmente, por link, aí tem que abrir o link. Então, a triagem faz
isso, ela abre o link, coleta essas informações como se fosse um usuário."

O que este módulo faz, e só isso:
- um GET na página de rastreio ou de pedido que veio num e-mail de compra, com cara de
  navegador, sem cookie, sem login, sem preencher formulário nem clicar em nada;
- devolve o TEXTO visível da página, para o mesmo leitor do e-mail tirar dali o rastreio,
  a transportadora, a situação ("Delivered", "Out for delivery") e a previsão.

Cuidados (link de e-mail é coisa que vem de fora):
- só http/https, porta padrão, e o endereço tem de resolver para IP PÚBLICO — nunca
  localhost, rede interna ou metadado da nuvem (SSRF). Vale também para cada redirecionamento;
- no máximo 3 redirecionamentos, 2 MB e 15 s por página;
- link de descadastro, de login, de política, de ajuda e de "escreva uma avaliação" nunca
  é aberto (`util()`).

Página que só existe depois do JavaScript (UPS, FedEx, Amazon) volta quase vazia ou pede
login: aí o leitor fica com o que o próprio e-mail disse. Se o servidor tiver o Chromium
do Playwright (`CC_NAVEGADOR=1`), a página é desenhada nele antes de ser lida.

Em teste nada sai da máquina: `CC_PAGINA_FAKE=<pasta>` lê `<sha1 da url>.html` dessa pasta.
"""
import hashlib
import html as _html
import ipaddress
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

MAX_BYTES = 2_000_000
TIMEOUT = 15
MAX_REDIRECTS = 3
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0 Safari/537.36")

# o que interessa num e-mail de compra: rastrear, ver o pedido, ver a fatura
_INTERESSA = re.compile(r"(track|rastre|shipment|logistic|order|pedido|delivery|package|invoice|status)", re.I)
# o que nunca se abre: sair da lista, entrar na conta, avaliar, ajuda, política
_NUNCA = re.compile(r"(unsubscribe|optout|opt-out|preference|privacy|terms|policy|help|support|contact|"
                    r"cancel|reorder|order-edit|order-editor|edit|return|approve|accept|confirm-receipt|confirm_receipt|"
                    r"\bpay\b|/pay|payment|checkout|cart|"
                    r"review|feedback|survey|sign[-_]?in|login|log-in|password|account/settings|"
                    r"facebook|instagram|twitter|youtube|tiktok|linkedin|pinterest|apps\.apple|play\.google|"
                    r"mailto:|tel:|\.(png|jpe?g|gif|svg|webp)(\?|$))", re.I)


class ErroPagina(RuntimeError):
    """A página não foi lida (bloqueada, fora do ar, endereço proibido). Texto sem segredo."""


def util(url, texto=""):
    """O link merece ser aberto? Rastreio/pedido sim; descadastro, login, rede social, não."""
    alvo = f"{url} {texto}"
    return bool(_INTERESSA.search(alvo)) and not _NUNCA.search(url)


def _ip_publico(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ErroPagina(f"endereço não resolve: {host} ({e})")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise ErroPagina(f"endereço não público recusado: {host}")
    return True


def _conferir(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ErroPagina("só http/https")
    if u.port not in (None, 80, 443):
        raise ErroPagina("porta fora do padrão recusada")
    if u.username or u.password:
        raise ErroPagina("link com usuário/senha recusado")
    _ip_publico(u.hostname)
    return u


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def texto_da_pagina(html):
    t = re.sub(r"(?is)<(style|script|noscript|head|svg)\b.*?</\1\s*>", " ", html or "")
    t = re.sub(r"(?i)<\s*(br|/p|/div|/tr|/li|/h\d|/td)\b[^>]*>", "\n", t)
    t = _html.unescape(re.sub(r"<[^>]+>", " ", t))
    t = re.sub(r"[ \t ]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t).strip()


def _fake(url):
    pasta = os.environ.get("CC_PAGINA_FAKE")
    arq = os.path.join(pasta, hashlib.sha1(url.encode()).hexdigest() + ".html")
    if not os.path.exists(arq):
        raise ErroPagina("página não existe (teste)")
    with open(arq, encoding="utf-8") as f:
        return {"url": url, "status": 200, "texto": texto_da_pagina(f.read())}


def _navegador(url):
    """Chromium do Playwright, se o servidor tiver (CC_NAVEGADOR=1). Sem ele, None."""
    if os.environ.get("CC_NAVEGADOR") != "1":
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    caminho = os.environ.get("CC_NAVEGADOR_CHROMIUM") or None
    with sync_playwright() as p:
        nav = p.chromium.launch(executable_path=caminho, headless=True)
        try:
            ctx = nav.new_context(user_agent=UA, java_script_enabled=True, accept_downloads=False)
            pg = ctx.new_page()
            # cada pedido da página passa pela mesma regra de IP público
            pg.route("**/*", lambda rota: rota.abort() if not _rota_ok(rota.request.url) else rota.continue_())
            pg.goto(url, timeout=TIMEOUT * 1000, wait_until="networkidle")
            return texto_da_pagina(pg.content())
        finally:
            nav.close()


def _rota_ok(url):
    try:
        _conferir(url)
        return True
    except ErroPagina:
        return False


def abrir(url):
    """{url (final), status, texto}. Levanta ErroPagina quando não deu para ler."""
    if os.environ.get("CC_PAGINA_FAKE"):
        return _fake(url)
    abridor = urllib.request.build_opener(_SemRedirecionar)
    atual = url
    for _ in range(MAX_REDIRECTS + 1):
        _conferir(atual)
        req = urllib.request.Request(atual, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml",
                                                     "Accept-Language": "en-US,en;q=0.9"})
        try:
            with abridor.open(req, timeout=TIMEOUT) as r:
                corpo = r.read(MAX_BYTES + 1)
                status = r.status
                tipo = r.headers.get("Content-Type", "")
                charset = r.headers.get_content_charset() or "utf-8"
            break
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                atual = urllib.parse.urljoin(atual, e.headers["Location"])
                continue
            raise ErroPagina(f"HTTP {e.code}")
        except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
            raise ErroPagina(f"sem conexão: {getattr(e, 'reason', e)}")
    else:
        raise ErroPagina("redirecionamentos demais")
    if len(corpo) > MAX_BYTES:
        raise ErroPagina("página grande demais")
    if "html" not in tipo and "text" not in tipo:
        raise ErroPagina(f"não é página ({tipo or 'sem tipo'})")
    texto = texto_da_pagina(corpo.decode(charset, errors="replace"))
    if len(texto) < 200:                       # casca vazia de JavaScript: tenta o navegador
        try:
            desenhado = _navegador(atual)
        except Exception:                       # noqa: BLE001 — navegador é melhoria, não requisito
            desenhado = None
        if desenhado:
            texto = desenhado
    return {"url": atual, "status": status, "texto": texto}

"""Rotas do site novo (#148, #164): todas as páginas em novo.urace.us, a agenda pública e os
formulários de contato e de pedido da loja.

As páginas só respondem nos endereços do site (`CC_SITE_HOSTS`, por padrão `novo.urace.us`).
Em ops.urace.us e my.urace.us, `/` continua do jeito que era (o Caddy manda para o painel ou
para a área do cliente) e um caminho do site devolve 404 — o painel não vira vitrine.

Os endereços do urace.us de hoje (WordPress) viram 301 para o endereço novo
(`paginas_site.destino()`): nada que o Google indexou cai no 404.

A agenda pública (`/ops/api/vitrine/agenda`) é a mesma da área do cliente, sem login e com
menos: só dia, turno, aberto ou não e vagas. Nunca o motivo de um dia fechado, nem quem marcou.

Contato e pedido da loja (#164) entram no funil de Vendas do Command Center como oportunidade
(origem "Site") e avisam a equipe por e-mail — tudo conectado por ali, como o dono pediu.
"""
import hmac
import json
import os
import re
import sqlite3
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from command_center.db import agora, auditar, get_db, inserir, transacao, um
from command_center.providers import agenda_sessoes as ag
from command_center.vitrine import conteudo as C, idioma, medicao, paginas
from command_center.vitrine import paginas_site as ps

r = APIRouter(tags=["vitrine"])

# Política própria do site: nada de fora (fontes e fotos são nossas), nenhum script inline.
# #174: o formulário de comprar termina num 303 para o checkout.stripe.com, e o Chrome confere o
# form-action também no redirecionamento — só esse endereço de fora entra, e só aí. (O e2e troca
# pelo Stripe falso dele em STRIPE_CHECKOUT_ORIGEM.)
# #260: a medição abre o mínimo — os hosts do Google Tag Manager e do Meta — e só na resposta que
# levou a medição no HTML (`medindo`). Sem id no ambiente, a política é exatamente a de antes.
def csp(medindo=False):
    checkout = os.environ.get("STRIPE_CHECKOUT_ORIGEM", "https://checkout.stripe.com")
    d = {"default-src": ["'self'"], "img-src": ["'self'", "data:"], "style-src": ["'self'"],
         "font-src": ["'self'"], "script-src": ["'self'"], "connect-src": ["'self'"],
         "base-uri": ["'none'"], "form-action": ["'self'", checkout], "frame-ancestors": ["'none'"]}
    if medindo:
        for diretiva, hosts in medicao.csp_hosts().items():
            d.setdefault(diretiva, []).extend(h for h in hosts if h not in d.get(diretiva, ()))
    return "; ".join(f"{k} {' '.join(v)}" for k, v in d.items())

# Páginas fixas: caminho → função(host). As dinâmicas (blog, loja, contato) estão em `_dinamica`.
PAGINAS = {
    "/": paginas.home,
    "/services/arrive-and-drive/": paginas.arrive_and_drive,
    "/services/": ps.hub,
    "/academy/": ps.academy,
    "/pro-team/": ps.pro_team,
    "/for-beginners/": ps.beginners,
    "/career/": ps.career,
    "/about/": ps.about,
    "/accessibility/": ps.accessibility,
    "/blog/": ps.blog,
    "/store/": ps.store,
}
for _s in ps.S.SERVICOS:
    PAGINAS[_s["caminho"]] = (lambda d: (lambda host: ps.servico(host, d)))(_s)


def hosts():
    return {h.strip().lower() for h in os.environ.get("CC_SITE_HOSTS", "novo.urace.us").split(",") if h.strip()}


def host_de(request):
    return (request.headers.get("host") or "").split(":")[0].strip().lower()


def e_do_site(request):
    return host_de(request) in hosts()


def _html(conteudo, status=200):
    # #260: a política abre os hosts da medição só quando a página realmente levou o bloco dela —
    # assim a permissão nunca é maior do que o HTML usa, sem passar o caminho por oito chamadas
    return HTMLResponse(conteudo, status_code=status, headers={
        "Content-Security-Policy": csp(medindo=medicao.MARCA in conteudo),
        "X-Frame-Options": "DENY",
        # página pública, igual para todo mundo: pode ficar 5 min no navegador
        "Cache-Control": "public, max-age=300",
    })


def _slug(s):
    return s if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,120}", s or "") else None


def _dinamica(host, caminho, q):
    """Blog, loja e contato: o caminho carrega o slug. None quando não existe."""
    m = re.fullmatch(r"/blog/category/([^/]+)/", caminho)
    if m:
        return ps.blog(host, _slug(m.group(1)))
    m = re.fullmatch(r"/blog/([^/]+)/", caminho)
    if m:
        return ps.post(host, _slug(m.group(1)))
    m = re.fullmatch(r"/store/p/([^/]+)/", caminho)
    if m:
        from command_center.providers import stripe_loja
        return ps.product(host, _slug(m.group(1)), enviado=q.get("sent") == "1", stripe=stripe_loja.ligado(),
                          erro_checkout=q.get("checkout") == "erro")
    m = re.fullmatch(r"/store/(?:([^/]+)/)?page/(\d+)/", caminho)
    if m:                                               # #261: a página da loja é caminho, não parâmetro
        cat = _slug(m.group(1)) if m.group(1) else None
        if m.group(1) and not cat:
            return None
        n = int(m.group(2)) if len(m.group(2)) <= 4 else 0
        return ps.store(host, cat, q, pagina=n) if n > 1 else None   # page/1/ é a própria /store/ (301)
    m = re.fullmatch(r"/store/([^/]+)/", caminho)
    if m:
        return ps.store(host, _slug(m.group(1)), q)
    if caminho == "/contact/":
        assunto = q.get("assunto") if q.get("assunto") in dict(ps.P.CONTACT["assuntos"]) else None
        return ps.contact(host, assunto, (q.get("produto") or "")[:120] or None, enviado=q.get("sent") == "1")
    return None


@r.get("/ops/api/vitrine/planos")
def planos_publicos(con: sqlite3.Connection = Depends(get_db)):
    """#169: os planos mensais que o site vende (preço por mês, meses, sessões por mês)."""
    from command_center.providers import servicos_site
    return {"plans": servicos_site.planos_para_cliente(con), "auto_sell": bool(ag.config(con).get("auto_sell"))}


def _planos():
    """Os planos cadastrados no painel, para a página da Academy (sem plano, a página pede contato)."""
    from command_center.db import conectar
    from command_center.providers import servicos_site
    try:
        con = conectar()
        try:
            return servicos_site.planos_para_cliente(con)
        finally:
            con.close()
    except Exception:                                   # noqa: BLE001 — banco fora: a página sai sem os planos
        return []


def _servicos_do_site():
    """#263: os serviços de sessão ativos do painel, para a página do Arrive and Drive sair com o
    kart que o site vende de verdade e o preço do painel (#50). `None` = o painel não respondeu: a
    página sai com os quatro karts de `KARTS` e o `agenda.js` corrige quando a lista chegar."""
    from command_center.db import conectar
    from command_center.providers import servicos_site
    try:
        con = conectar()
        try:
            return servicos_site.para_cliente(con, cartao=True)      # #297: com o cartão do kart do painel
        finally:
            con.close()
    except Exception:                                   # noqa: BLE001 — banco fora: a página não mente, só não filtra
        return None


def _lead_follow_do_site():
    """#279: o add-on do dia de treino que o painel vende (None: banco fora, ou não vende)."""
    from command_center.db import conectar
    from command_center.providers import servicos_site
    try:
        con = conectar()
        try:
            return servicos_site.addon_do_site(con)
        finally:
            con.close()
    except Exception:                                   # noqa: BLE001 — banco fora: a caixa só não aparece
        return None


def _do_banco(ler):
    """#297: lê do banco o que a página mostra; banco fora devolve None e a página cai no texto de sempre."""
    from command_center.db import conectar
    try:
        con = conectar()
        try:
            return ler(con)
        finally:
            con.close()
    except Exception:                                   # noqa: BLE001 — banco fora: a página não quebra
        return None


def _cartoes(pagina):
    from command_center.providers import cartoes_site
    return _do_banco(lambda con: cartoes_site.da_pagina(con, pagina))


def existe(caminho, host="novo.urace.us"):
    if caminho in PAGINAS or caminho == "/cart/" or _dinamica(host, caminho, {}) is not None:
        return True
    from command_center.providers import editor_site                 # #300: as páginas novas do editor
    return caminho in (_do_banco(editor_site.caminhos_novos) or [])


class _UmaVez:
    """#298: lê do banco só se a página pedir, e uma vez por requisição (a home não abre o catálogo da loja)."""
    def __init__(self, ler):
        self.ler, self.lido, self.valor = ler, False, None

    def __call__(self):
        if not self.lido:
            self.valor, self.lido = _do_banco(self.ler), True
        return self.valor


def _com_o_painel(fazer):
    """O que o painel decide na página: #297, o "a partir de" (o menor preço de kart do painel, ao vivo); #298, os
    produtos da loja (do banco; sem banco, o arquivo de antes)."""
    from command_center.providers import cartoes_site, loja
    marca = paginas.PRECO_KART.set(_do_banco(cartoes_site.preco_kart))
    marca_loja = ps.PRODUTOS.set(_UmaVez(loja.catalogo))
    try:
        return fazer()
    finally:
        ps.PRODUTOS.reset(marca_loja)
        paginas.PRECO_KART.reset(marca)


def pagina(request: Request, caminho: str):
    """O que o site responde em `caminho` (sempre começando com /)."""
    if not e_do_site(request):
        raise HTTPException(404)
    host = host_de(request)
    q = dict(request.query_params)
    resp = _com_o_painel(lambda: _pagina(request, caminho, host, q))
    _contar_visita(request, caminho, q, resp)
    return resp


def _contar_visita(request, caminho, q, resp):
    """#306: +1 nas visitas da página (e na entrada, quando a pessoa chegou de fora). A conta fica na memória; de 30 em
    30 s vai para o banco, depois da resposta (ninguém espera o banco para ver a página)."""
    from starlette.background import BackgroundTask

    from command_center.providers import painel_site
    if not painel_site.conta(request, request.method, resp.status_code):
        return
    if caminho == "/cart/" and q.get("cancelled"):     # a volta do Stripe não é abrir o carrinho de novo
        return
    fonte = painel_site.fonte_da_entrada(request.headers.get("referer"), q.get("utm_source"), hosts(),
                                         request.headers.get("sec-fetch-site"))
    if painel_site.anotar(caminho, fonte, ip=_ip(request)) and resp.background is None:
        resp.background = BackgroundTask(painel_site.descarregar)


# #300: as páginas do site que o editor abre (as fixas; a loja e o blog são listas que mudam com a busca)
EDITAVEIS = tuple(c for c in PAGINAS if c not in ("/store/", "/blog/"))


def html_da_pagina(caminho, host):
    """O HTML da página do código (o que o site mostra sem o editor), ou None quando não é página fixa."""
    if caminho == C.ARRIVE["caminho"]:                  # #263: o kart que está na página é o que o painel vende
        return paginas.arrive_and_drive(host, servicos=_servicos_do_site(), lead_follow=_lead_follow_do_site())
    if caminho == "/academy/":                          # #297: os cartões do painel (sem plano à venda pelo site)
        return ps.academy(host, planos=_planos(), cartoes=_cartoes("academy"))
    if caminho == "/pro-team/":                         # #207: o preço da Academy e do Boost é o do painel
        return ps.pro_team(host, planos=_planos(), cartoes=_cartoes("pro-team"))
    if caminho == "/for-beginners/":
        return ps.beginners(host, cartoes=_cartoes("for-beginners"))
    if caminho in PAGINAS and caminho != "/store/":
        return PAGINAS[caminho](host)
    return None


def _do_editor(caminho, host):
    """#300: a página que o editor publicou neste endereço (nova, ou a reescrita de uma que já existe)."""
    from command_center.api import editor_site as api_editor
    from command_center.providers import editor_site
    pub = _do_banco(lambda con: editor_site.publicada(con, caminho))
    return api_editor.desenhar(pub, host) if pub else None


def _pagina(request, caminho, host, q):
    if not (caminho == "/" and (q.get("s") or "").strip()):
        feita = _do_editor(caminho, host)
        if feita:
            return _html(feita)
    if caminho in (C.ARRIVE["caminho"], "/academy/", "/pro-team/", "/for-beginners/"):
        return _html(html_da_pagina(caminho, host))
    if caminho == "/cart/":                             # #236: o carrinho (noindex, sem cache: é de cada pessoa)
        from command_center.providers import stripe_loja
        return _sem_cache(ps.carrinho(host, cancelado=q.get("cancelled") == "1", stripe=stripe_loja.ligado(),
                                      lang=idioma.de_request(request)))
    if caminho == "/" and (q.get("s") or "").strip():   # #261: a busca do WordPress (`/?s=`) é a da loja
        return RedirectResponse(f"/store/?{urlencode({'s': q['s'].strip()[:80]})}", status_code=301)
    if caminho == "/store/":                            # #261: busca, filtro de preço e ordem vêm do endereço
        return _html(ps.store(host, None, q))
    if caminho in PAGINAS:
        return _html(PAGINAS[caminho](host))
    html = _dinamica(host, caminho, q)
    if html:
        return _html(html)
    # endereço do urace.us de hoje → o novo (301, sem perder o que o Google indexou)
    novo = ps.destino(caminho)
    if novo and novo != caminho:
        # #261: o endereço antigo leva a busca, o filtro e a ordem com ele (`?s=`, `min_price`…)
        if request.url.query and "?" not in novo:
            novo = f"{novo}?{request.url.query}"
        return RedirectResponse(novo, status_code=301)
    # o mesmo endereço sem a barra final (como o WordPress fazia): 301 para o certo
    if not caminho.endswith("/") and existe(caminho + "/", host):
        return RedirectResponse(caminho + "/" + (f"?{request.url.query}" if request.url.query else ""), status_code=301)
    return _html(paginas.nao_achou(host), status=404)


@r.get("/", include_in_schema=False)
def inicio(request: Request):
    return pagina(request, "/")


@r.get("/services/arrive-and-drive/", include_in_schema=False)
@r.get("/services/arrive-and-drive", include_in_schema=False)
def arrive_and_drive(request: Request):
    return pagina(request, request.url.path)


@r.get("/ops/api/vitrine/agenda")
def agenda_publica(con: sqlite3.Connection = Depends(get_db)):
    """Os dias que o cliente pode pedir, do jeito que a área do cliente mostra — sem login.

    Só aberto/fechado e vagas por turno; o horário de cada turno vem da configuração."""
    d = ag.disponibilidade(con)            # visão do cliente: horizonte e antecedência já aplicados
    dias = [{"date": x["date"],
             "manha": {"open": x["periods"]["manha"]["open"], "spots": x["periods"]["manha"]["spots"]},
             "tarde": {"open": x["periods"]["tarde"]["open"], "spots": x["periods"]["tarde"]["spots"]}}
            for x in d["dias"]]
    cfg = d["config"]
    return {"config": {k: cfg[k] for k in ("morning_start", "morning_end", "afternoon_start", "afternoon_end")},
            "dias": dias}


@r.get("/ops/api/vitrine/servicos")
def servicos_publicos(request: Request, con: sqlite3.Connection = Depends(get_db)):
    """#164: o que o site vende, para a reserva montar o resumo antes do login: nome, preço e o
    depósito reembolsável. Nada do QuickBooks. `cart` (#236): neste endereço dá para pôr no carrinho
    (o carrinho é do site novo e paga no Stripe)."""
    from command_center.providers import servicos_site, stripe_loja
    return {"services": servicos_site.para_cliente(con), "auto_sell": bool(ag.config(con).get("auto_sell")),
            "lead_follow": servicos_site.addon_do_site(con),           # #279: o add-on do dia de treino
            "cart": e_do_site(request) and stripe_loja.ligado()}


# ------------------------------------------------------------------ contato e pedido (#164)
_JANELA, _MAXIMO = 600, 8                   # por IP: 8 envios a cada 10 min
_envios: dict[str, list[float]] = {}
_tranca = threading.Lock()


def _ip(request):
    return (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "") or "?").split(",")[0].strip()


def _estourou(ip):
    with _tranca:
        t = time.time()
        fila = [x for x in _envios.get(ip, ()) if t - x < _JANELA]
        if len(fila) >= _MAXIMO:
            _envios[ip] = fila
            return True
        fila.append(t)
        _envios[ip] = fila
        return False


async def _campos(request):
    """O formulário vem como JSON (contato.js) ou urlencoded (sem JavaScript). Só texto, aparado."""
    corpo = await request.body()
    tipo = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if tipo == "application/json":
        try:
            dados = json.loads(corpo or b"{}")
        except ValueError:
            raise HTTPException(400, "JSON inválido")
        if not isinstance(dados, dict):
            raise HTTPException(400, "JSON inválido")
    else:
        dados = {k: v[0] for k, v in parse_qs(corpo.decode("utf-8", "replace"), keep_blank_values=True).items()}
    return {k: str(v or "").strip()[:2000] for k, v in dados.items() if isinstance(v, (str, int, float))}


def _responde(request, ok, volta, erro=None):
    """fetch recebe JSON; o formulário sem JavaScript volta para a página com `?sent=1`."""
    quer_json = "application/json" in (request.headers.get("accept") or "") or \
        (request.headers.get("content-type") or "").startswith("application/json")
    if quer_json:
        return JSONResponse({"ok": ok, **({"erro": erro} if erro else {})}, status_code=200 if ok else 400,
                            headers={"Cache-Control": "no-store"})
    if not ok:
        raise HTTPException(400, erro)
    return RedirectResponse(volta, status_code=303)


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validar(c):
    if c.get("site"):
        return "robo"                      # honeypot preenchido: um robô. Diz "ok" e descarta.
    if len(c.get("nome", "")) < 2:
        return "Please tell us your name."
    if not EMAIL_RE.match(c.get("email", "")):
        return "Please check your email address."
    return None


def _avisar_equipe(assunto, texto):
    from command_center.providers import email_envio
    try:
        email_envio.enviar("support@urace.us", assunto, texto)
    except Exception:                                   # noqa: BLE001 — já está no funil; o e-mail é aviso
        pass


def _confirmar_pessoa(para, assunto, texto):
    from command_center.providers import email_envio
    try:
        email_envio.enviar(para, assunto, texto)
    except Exception:                                   # noqa: BLE001
        pass


def _campanha(c):
    """#260: de onde o contato veio (utm_*, gclid, fbclid, fbp, fbc, campaign_id, adset_id).

    O `campanha.js` põe os campos escondidos no formulário — com JavaScript e sem ele. Vendas vê
    isso no card da oportunidade. Só campanha: nada da pessoa entra aqui."""
    from command_center.providers import venda_site
    return venda_site.utm_limpo({k: c.get(k) for k in venda_site.CAMPANHA})


def _oportunidade(con, c, servico, valor, notas, origem="Site"):
    oid = inserir(con, "opportunities", name=c["nome"], email=c["email"].lower(), phone=c.get("telefone") or None,
                  service=servico, amount=valor, stage="NOVO", source=origem, notes=notas,
                  campaign=_campanha(c))
    inserir(con, "opp_events", opp_id=oid, kind="note", title="Chegou pelo site", detail=notas[:2000], at=agora(), actor="site")
    con.commit()
    return oid


@r.post("/ops/api/vitrine/contato", include_in_schema=False)
async def contato(request: Request, con: sqlite3.Connection = Depends(get_db)):
    """O formulário de /contact/: vira oportunidade em Vendas (origem Site) e avisa support@."""
    if not e_do_site(request):
        raise HTTPException(404)
    c = await _campos(request)
    erro = _validar(c)
    if erro == "robo":
        return _responde(request, True, "/contact/?sent=1")
    if erro:
        return _responde(request, False, "/contact/", erro)
    if _estourou(_ip(request)):
        return _responde(request, False, "/contact/", "Too many messages in a row. Please try again in a few minutes.")
    if len(c.get("mensagem", "")) < 2:
        return _responde(request, False, "/contact/", "Please write a message.")
    assuntos = dict(ps.P.CONTACT["assuntos"])
    assunto = assuntos.get(c.get("assunto"), "Something else")
    notas = f"[{assunto}] {c['mensagem']}"
    oid = _oportunidade(con, c, assunto, None, notas)
    _avisar_equipe(f"Site · contato: {assunto} — {c['nome']}",
                   f"{c['nome']} <{c['email']}> {c.get('telefone') or ''}\nAssunto: {assunto}\n\n{c['mensagem']}\n\n"
                   f"Vendas: https://ops.urace.us/ops/sales/{oid}")
    _confirmar_pessoa(c["email"], "We got your message — URACE",
                      f"Hi {c['nome'].split()[0]},\n\nThanks for reaching out to URACE. We received your message about "
                      f"{assunto} and will reply shortly, usually within one business day.\n\nIn a hurry? Call or WhatsApp "
                      f"+1 (407) 250 2291.\n\nURACE — the Champion's Factory\nOrlando Kart Center, 10724 Cosmonaut Blvd, Box 3, Orlando, FL 32824")
    return _responde(request, True, "/contact/?sent=1")


@r.post("/ops/api/vitrine/pedido", include_in_schema=False)
async def pedido(request: Request, con: sqlite3.Connection = Depends(get_db)):
    """O pedido da loja: produto, variação e quantidade viram oportunidade com o valor estimado;
    a equipe confirma estoque e frete e manda a invoice do QuickBooks. Nada é cobrado aqui."""
    if not e_do_site(request):
        raise HTTPException(404)
    c = await _campos(request)
    from command_center.providers import loja
    p = loja.do_site(con).get(c.get("produto") or "")          # #298: o catálogo do painel
    volta = f"/store/p/{p['slug']}/" if p else "/store/"
    erro = _validar(c)
    if erro == "robo":
        return _responde(request, True, volta + "?sent=1")
    if not p:
        return _responde(request, False, volta, "Product not found.")
    if erro:
        return _responde(request, False, volta, erro)
    if _estourou(_ip(request)):
        return _responde(request, False, volta, "Too many requests in a row. Please try again in a few minutes.")
    try:
        qtd = max(1, min(20, int(c.get("quantidade") or 1)))
    except ValueError:
        qtd = 1
    variacao = next((v for v in p["variations"] if " / ".join(v["attrs"]) == c.get("variacao")), None)
    unit = (variacao or {}).get("price") or p["price"] or None
    valor = round(unit * qtd, 2) if unit else None
    desc = p["name"] + (f" ({' / '.join(variacao['attrs'])})" if variacao else "") + (f" × {qtd}" if qtd > 1 else "")
    notas = f"[Loja] {desc}" + (f" — {paginas.usd(valor)}" if valor else " — preço a confirmar") + \
        (f"\n{c['mensagem']}" if c.get("mensagem") else "")
    oid = _oportunidade(con, c, f"Store: {desc}", valor, notas)
    _avisar_equipe(f"Site · pedido da loja: {desc} — {c['nome']}",
                   f"{c['nome']} <{c['email']}> {c.get('telefone') or ''}\n{desc}\nValor estimado: {paginas.usd(valor) if valor else 'a confirmar'}\n"
                   f"{c.get('mensagem') or ''}\n\nVendas: https://ops.urace.us/ops/sales/{oid}")
    _confirmar_pessoa(c["email"], "We got your order request — URACE Store",
                      f"Hi {c['nome'].split()[0]},\n\nThanks for your order request: {desc}"
                      f"{' — ' + paginas.usd(valor) if valor else ''}.\n\nOur team will confirm availability, shipping and the total, "
                      f"and send you an invoice to pay online. Nothing has been charged.\n\nQuestions? Call or WhatsApp +1 (407) 250 2291.\n\n"
                      f"URACE — the Champion's Factory")
    return _responde(request, True, volta + "?sent=1")


# ------------------------------------------------------------------ loja paga no Stripe (#174)
def _origem(request):
    """https://<endereço do site> para a volta do Stripe (no teste local, http com a porta)."""
    h = (request.headers.get("host") or "").strip().lower()
    local = host_de(request) in ("127.0.0.1", "localhost")
    return ("http://" if local else "https://") + h


@r.post("/ops/api/vitrine/checkout", include_in_schema=False)
async def checkout(request: Request, con: sqlite3.Connection = Depends(get_db)):
    """O botão "Buy now": confere produto, variação e preço no catálogo e manda ao Stripe Checkout."""
    from command_center.providers import stripe_loja
    if not e_do_site(request):
        raise HTTPException(404)
    c = await _campos(request)
    from command_center.providers import loja
    p = loja.do_site(con).get(c.get("produto") or "")          # #298: o catálogo do painel
    volta = f"/store/p/{p['slug']}/" if p else "/store/"
    quer_json = "application/json" in (request.headers.get("accept") or "")

    def erro(msg):
        if quer_json:
            return JSONResponse({"ok": False, "erro": msg}, status_code=400, headers={"Cache-Control": "no-store"})
        return RedirectResponse(volta + "?checkout=erro", status_code=303)

    if c.get("site"):
        return RedirectResponse(volta, status_code=303)            # honeypot: um robô
    if not p:
        return erro("Product not found.")
    if not stripe_loja.ligado():
        return erro("Online payment isn't available right now. Please send us an order request.")
    if _estourou(_ip(request)):
        return erro("Too many requests in a row. Please try again in a few minutes.")
    from command_center.api import portal as api_portal
    conta = api_portal.conta_do_cookie(request, con)
    if not conta:                                  # #248: comprar pede a conta do site; entra (ou cria) e volta
        destino = f"{paginas.PORTAL}?volta={volta}"
        if quer_json:
            return JSONResponse({"ok": False, "erro": "Please sign in or create your URACE account to buy.", "sign_in": True,
                                 "url": destino}, status_code=401, headers={"Cache-Control": "no-store"})
        return RedirectResponse(destino, status_code=303)
    try:
        qtd = int(c.get("quantidade") or 1)
    except ValueError:
        qtd = 1
    foto = None
    if p["images"] and not _origem(request).startswith("http://"):
        foto = _origem(request) + paginas.foto_url(p["images"][0]["src"])
    try:
        _, url = stripe_loja.criar_sessao(con, p, c.get("variacao") or "", qtd, c.get("entrega"), _origem(request),
                                          host_de(request), foto_url=foto, conta_id=conta, lang=idioma.de_request(request))
    except ValueError as e:
        return erro(str(e))
    except stripe_loja.ErroStripe as e:
        import logging
        logging.getLogger("urace.loja").warning("checkout do Stripe falhou: %s", str(e)[:200])
        return erro("We couldn’t open the secure checkout just now. Please try again in a minute.")
    if quer_json:
        return JSONResponse({"ok": True, "url": url}, headers={"Cache-Control": "no-store"})
    return RedirectResponse(url, status_code=303)


@r.post("/ops/api/stripe/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, background: BackgroundTasks, con: sqlite3.Connection = Depends(get_db)):
    """O Stripe avisa aqui (qualquer endereço do servidor). Sem assinatura válida: 400 e nada muda.
    A resposta sai logo; os e-mails e o QuickBooks vêm depois, em segundo plano."""
    from command_center.providers import stripe_loja
    corpo = await request.body()
    segredo = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not segredo:
        raise HTTPException(503, "webhook do Stripe sem segredo configurado")
    if not stripe_loja.assinatura_ok(corpo, request.headers.get("stripe-signature") or "", segredo):
        raise HTTPException(400, "assinatura inválida")
    try:
        evento = json.loads(corpo)
    except ValueError:
        raise HTTPException(400, "JSON inválido")
    if not isinstance(evento, dict) or not evento.get("id"):
        raise HTTPException(400, "evento sem id")
    resultado, pago = stripe_loja.receber_evento(con, evento)
    if pago:
        background.add_task(stripe_loja.avisar_e_registrar, pago)
    elif resultado in ("aguardando", "falhou", "expirado"):     # #245, #248: todo resultado avisa, uma vez só
        from command_center.db import um
        from command_center.providers import pedido_site
        ev = um(con, "SELECT order_id FROM stripe_events WHERE id=?", (str(evento["id"]),))
        if ev and ev["order_id"]:
            background.add_task(pedido_site.avisar_resultado_bg, ev["order_id"], resultado)
    return JSONResponse({"recebido": True, "resultado": resultado}, headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------ carrinho (#236)
def _json(dados, status=200):
    return JSONResponse(dados, status_code=status, headers={"Cache-Control": "no-store"})


async def _corpo_json(request):
    try:
        d = json.loads(await request.body() or b"{}")
    except ValueError:
        raise HTTPException(400, "JSON inválido")
    if not isinstance(d, dict):
        raise HTTPException(400, "JSON inválido")
    return d


def _conta_resumo(con, conta_id):
    """O que o carrinho precisa da conta: quem está logado e os pilotos (com o que falta em cada um). #305: piloto
    incompleto não trava mais a compra (completa depois, com lembrete por e-mail): `pending` diz o que falta."""
    from command_center.providers import portal
    c = portal.conta(con, conta_id)
    falta = {"faltando": "profile to complete after payment", "vencida": "measurements to update after payment"}
    return {"name": c["name"], "email": c["email"], "missing": c["missing"],
            "drivers": [{"id": p["id"], "name": p["name"], "blocked": None, "pending": falta.get(p["measures_status"])}
                        for p in c["drivers"]]}


# #305 (dono, 16/10): "a pessoa, para ela conseguir … seguir para o checkout, ela vai ter que preencher as
# informações dela … Quando for para o checkout, já cria a conta dela no Erase automaticamente". Os mesmos campos e
# as mesmas regras do cadastro (`portal.criar_conta`), mais a senha confirmada e o nome do piloto da sessão.
CAMPOS_CONTA = ("name", "email", "birth_date", "phone_country", "phone", "address_line1", "address_line2", "city", "state",
                "zip", "country", "accept_terms")


def _texto_ou_nada(v):
    """O que veio do navegador como texto (número vira texto; lista, objeto e booleano não valem)."""
    if isinstance(v, str):
        return v
    return str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


class ErroConta(ValueError):
    def __init__(self, msg, status=400, entrar=False):
        super().__init__(msg)
        self.status, self.entrar = status, entrar


def _conta_do_carrinho(con, request, nova, itens, entrega=None):
    """Cria a conta (e o piloto, quando o carrinho tem sessão) com o que a pessoa preencheu no carrinho e põe o piloto
    nas sessões. Devolve (conta, senha). A senha fica só na memória desta requisição (vai para o e-mail de
    boas-vindas, decisão do dono) e é guardada só como hash.

    O banco grava cada comando na hora (autocommit): o carrinho é conferido ANTES (vaga, serviço, produto), para a
    conta não nascer de um carrinho que não fecha, e a conta e o piloto entram numa transação só."""
    from command_center.api import auth, portal as api_portal
    from command_center.providers import carrinho, portal
    if not isinstance(nova, dict):
        raise ErroConta("Fill in your details to continue.")
    nova = {**nova, **{k: _texto_ou_nada(nova.get(k)) for k in (*CAMPOS_CONTA, "password", "password2") if k != "accept_terms"}}
    c = carrinho.cotar(con, itens, None, para_pagar=True, entrega=entrega)
    if not c["linhas"]:
        raise ErroConta("Your cart is empty.")
    if c["demais"]:
        raise ErroConta(f"Up to {carrinho.MAX_ITENS} items per order.")
    erro = next((x["erro"] for x in c["linhas"] if x["erro"]), None)
    if erro:
        raise ErroConta(erro)
    # quem pilota: com uma sessão, "eu" ou o nome de outra pessoa; com duas ou mais, um nome por sessão (o serviço de um
    # filho nunca vai para o card do outro, regra do dono). Mesmo piloto em duas sessões no mesmo horário não fecha depois.
    itens = itens if isinstance(itens, list) else []
    sessoes = [(i, it) for i, it in enumerate(itens) if isinstance(it, dict) and it.get("tipo") == "sessao"]
    piloto = nova.get("piloto") if isinstance(nova.get("piloto"), dict) else {}
    titular = _chave_nome(nova.get("name"))
    nomes = None
    if len(sessoes) > 1 and isinstance(piloto.get("por_sessao"), list):
        nomes = {x["idx"]: " ".join((_texto_ou_nada(x.get("nome")) or "").split()) for x in piloto["por_sessao"]
                 if isinstance(x, dict) and isinstance(x.get("idx"), int) and not isinstance(x.get("idx"), bool)}
        if any(not nomes.get(i) for i, _ in sessoes):
            raise ErroConta("Write the driver's full name for each session.")
    quem = {i: _chave_nome(nomes[i]) if nomes else "um" for i, _ in sessoes}
    ocupado = set()
    for x in c["linhas"]:
        if x["tipo"] != "sessao":
            continue
        turnos = ag.PERIODOS if x["turno"] == "dia" else (x["turno"],)
        k = quem.get(x["idx"], "um")
        if any((k, x["data"], t) in ocupado for t in turnos):
            raise ErroConta("The same driver has two sessions at the same time in this cart. Change the time or the driver."
                            if nomes else
                            "Two sessions in this cart are at the same time, and a new account books one driver. Remove one, "
                            "check out, then book the other driver from your URACE area.")
        ocupado.update((k, x["data"], t) for t in turnos)
    senha, senha2 = str(nova.get("password") or ""), str(nova.get("password2") or "")
    if len(senha) < 8 or not auth.senha_aceitavel(senha):
        raise ErroConta("Use a password with at least 8 characters.")
    if senha != senha2:
        raise ErroConta("The passwords don't match.")
    ip = auth._ip(request)
    passou = api_portal.limite_de_cadastro(con, ip)
    if passou:
        raise ErroConta(passou, 429)
    api_portal.contar_cadastro(con, ip)
    con.commit()                                       # a tentativa conta para o limite, mesmo se o resto voltar atrás
    dados = {k: nova.get(k) for k in CAMPOS_CONTA}
    dados["accept_terms"] = nova.get("accept_terms") is True          # "false" (texto) não é aceite
    dados["i_am_driver"] = bool(sessoes) and (any(k == titular for k in quem.values()) if nomes else bool(piloto.get("eu")))
    sal, h = auth.hash_senha(senha)
    try:
        with transacao(con):                           # conta sem piloto (ou piloto sem conta) não fica pela metade
            cid = portal.criar_conta(con, dados, sal, h)
            eu = um(con, "SELECT id FROM portal_pilots WHERE account_id=? AND is_self=1", (cid,)) if dados["i_am_driver"] else None
            criados = {}
            for i, it in sessoes:
                if nomes:
                    k = quem[i]
                    if k == titular:
                        pid = eu["id"]
                    elif k in criados:
                        pid = criados[k]
                    else:
                        # o dono, 16/10: o carrinho pede só o nome do piloto; as medidas vêm depois, com lembrete por e-mail
                        pid = criados[k] = portal.criar_piloto(con, cid, {"name": nomes[i]}, completo=False)
                elif piloto.get("eu"):
                    pid = eu["id"]
                else:
                    pid = criados.get("um") or portal.criar_piloto(con, cid, {"name": _texto_ou_nada(piloto.get("nome"))}, completo=False)
                    criados["um"] = pid
                it["piloto"] = pid
    except portal.ErroPortal as e:
        raise ErroConta(str(e), entrar="already exists" in str(e))
    auditar(con, "portal.signup", f"portal:{cid}", entity_type="portal_account", entity_id=cid,
            detail={"origem": "carrinho", "piloto": bool(sessoes)}, ip=ip)
    return cid, senha


def _chave_nome(v):
    """O nome para comparar (o mesmo piloto escrito com outra caixa ou com espaço a mais é o mesmo)."""
    return " ".join(str(v or "").split()).casefold()


@r.post("/ops/api/vitrine/carrinho", include_in_schema=False)
async def carrinho_cotar(request: Request, con: sqlite3.Connection = Depends(get_db)):
    """As linhas do carrinho como o servidor as vê: preço do catálogo e do painel, depósito, vaga e piloto.
    Só lê. Com a conta do site aberta neste navegador, também diz quem é e quais pilotos tem."""
    from command_center.api import portal as api_portal
    from command_center.providers import carrinho, stripe_loja
    if not e_do_site(request):
        raise HTTPException(404)
    d = await _corpo_json(request)
    conta = api_portal.conta_do_cookie(request, con)
    entrega = "envio" if d.get("entrega") == "envio" else "retirada"       # #298: o frete entra com "Ship to me"
    cot = _no_idioma(carrinho.cotar(con, d.get("itens"), conta, entrega=entrega), idioma.de_request(request))
    return _json({**cot, "account": _conta_resumo(con, conta) if conta else None, "stripe": stripe_loja.ligado()})


def _no_idioma(cot, lang):
    """#248: as linhas como o servidor vê, no idioma da pessoa (o dia da sessão e as mensagens)."""
    from command_center.providers import pedido_site
    if lang != "pt":
        return cot
    for x in cot["linhas"]:
        x["nome"] = idioma.traduzir(x["nome"], lang)
        x["erro"] = idioma.traduzir(x["erro"], lang)
        if x.get("aviso_piloto"):                       # #305: completar o piloto depois do pagamento
            x["aviso_piloto"] = idioma.traduzir(x["aviso_piloto"], lang)
        if x["tipo"] == "sessao" and x.get("detalhe"):
            x["detalhe"] = pedido_site.quando(x["data"], x["turno"], lang)
    return cot


@r.post("/ops/api/vitrine/carrinho/checkout", include_in_schema=False)
async def carrinho_checkout(request: Request, background: BackgroundTasks, con: sqlite3.Connection = Depends(get_db)):
    """Um checkout só no Stripe com o carrinho inteiro. Toda compra pede a conta do site (#248): logado, a conta dele
    (e o CSRF dela); #305, sem conta, os dados que a pessoa preencheu no carrinho viram a conta aqui mesmo."""
    from command_center.api import portal as api_portal
    from command_center.providers import carrinho, conta_site, stripe_loja
    if not e_do_site(request):
        raise HTTPException(404)
    d = await _corpo_json(request)
    lang = idioma.de_request(request)
    if not stripe_loja.ligado():
        return _json({"ok": False, "erro": idioma.traduzir("Online payment isn't available right now. Please call or WhatsApp us.", lang)}, 400)
    conta = api_portal.conta_do_cookie(request, con)
    if conta and not api_portal.csrf_ok(request):
        return _json({"ok": False, "erro": idioma.traduzir("Security check failed. Reload the page and try again.", lang)}, 403)
    if _estourou(_ip(request)):
        return _json({"ok": False, "erro": idioma.traduzir("Too many requests in a row. Please try again in a few minutes.", lang)}, 429)
    itens, senha, nova = d.get("itens"), None, False
    if not conta and d.get("conta") is not None:
        # criar conta pede JSON de verdade (o tipo exato: `text/plain;x=application/json` passaria sem o navegador
        # perguntar antes) e, quando o navegador diz de onde veio, o próprio site
        if (request.headers.get("content-type") or "").split(";")[0].strip().lower() != "application/json":
            return _json({"ok": False, "erro": "JSON only"}, 415)
        origem = request.headers.get("origin")
        if origem is not None and (urlsplit(origem).hostname or "").lower() not in hosts():
            return _json({"ok": False, "erro": idioma.traduzir("Security check failed. Reload the page and try again.", lang)}, 403)
        try:
            conta, senha = _conta_do_carrinho(con, request, d["conta"], itens, d.get("entrega"))
            nova = True
        except ErroConta as e:
            return _json({"ok": False, "erro": idioma.traduzir(str(e), lang), "sign_in": e.entrar}, e.status)
    try:
        oid, url = carrinho.criar_checkout(con, itens, d.get("entrega"), conta, _origem(request), host_de(request),
                                           lang=lang)
        resp = _json({"ok": True, "url": url, "order": oid})
    except carrinho.PrecisaConta as e:
        con.rollback()
        resp = _json({"ok": False, "erro": idioma.traduzir(str(e), lang), "sign_in": True}, 401)
    except carrinho.ErroCarrinho as e:
        con.rollback()
        resp = _json({"ok": False, "erro": idioma.traduzir(str(e), lang)}, 400)
    except stripe_loja.ErroStripe as e:
        import logging
        logging.getLogger("urace.loja").warning("checkout do carrinho falhou: %s", str(e)[:200])
        # o pedido fica 'falhou' (a equipe vê a tentativa)
        resp = _json({"ok": False, "erro": idioma.traduzir("We couldn’t open the secure checkout just now. Please try again in a minute.", lang)}, 502)
    except Exception:
        if not nova:
            raise
        # o inesperado depois de a conta nascer: ela fica, abre a sessão e recebe as boas-vindas (a senha só existe agora)
        import logging
        logging.getLogger("urace.loja").exception("checkout do carrinho com conta nova falhou")
        resp = _json({"ok": False, "erro": idioma.traduzir("Something went wrong. Please try again.", lang)}, 500)
    if nova:
        # #305: a conta nova já sai logada neste navegador (volta do Stripe para a página do pedido e para a área
        # dela) e recebe as boas-vindas com a identidade da URACE: login, senha, número de cliente e o link. Se o
        # checkout não abriu (Stripe fora do ar, a vaga sumiu no mesmo segundo), a conta fica e ela tenta de novo logada.
        api_portal._abrir(con, request, resp, conta)
        background.add_task(conta_site.boas_vindas_bg, conta, senha, lang)
    con.commit()
    return resp


def _sem_cache(html, status=200):
    resp = _html(html, status=status)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ------------------------------------------------------------------ a página de cada pedido (#245)
def _conferir(con, o, background):
    """Pedido ainda sem resultado final: pergunta ao Stripe (se o webhook atrasar, nada se perde)."""
    from command_center.providers import stripe_loja
    if not o or o["status"] not in ("aberto", "aguardando") or not o["stripe_session_id"] or not stripe_loja.ligado():
        return o
    try:
        novo, agora_pago = stripe_loja.conferir_sessao(con, o["stripe_session_id"])
    except stripe_loja.ErroStripe:
        return o
    if agora_pago:
        background.add_task(stripe_loja.avisar_e_registrar, novo["id"])
    elif novo and novo["status"] in ("aguardando", "expirado"):    # #248: se o webhook atrasar, o aviso sai daqui
        from command_center.providers import pedido_site
        background.add_task(pedido_site.avisar_resultado_bg, novo["id"], novo["status"])
    return novo or o


def _pagina_pedido(request, con, o, caminho, limpar=False, erro=None, status=200):
    """O mesmo desenho em `/order/<token>/` e na volta do Stripe. Sem cache e sem Referer: o link é pessoal."""
    from command_center.api import portal as api_portal
    from command_center.providers import pedido_site
    ref = pedido_site.refeito(con, o)
    ls = pedido_site.linhas(con, o)
    volta = caminho + (f"?{request.url.query}" if request.url.query and caminho.endswith("/thanks/") else "")
    html = ps.pedido_pagina(host_de(request), o, ls=ls, caminho=caminho, token=pedido_site.token(o),
                            limpar=limpar, refeito=(ref["id"], pedido_site.caminho(ref)) if ref else None, erro=erro,
                            csrf=request.cookies.get(api_portal.COOKIE_CSRF, ""), lang=idioma.de_request(request),
                            volta=volta, cli=pedido_site.cliente(con, o, ls))
    resp = _sem_cache(html, status)
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


def _volta_do_stripe(request, background, con):
    from command_center.db import um
    sid = (request.query_params.get("session_id") or "")[:200]
    if not re.fullmatch(r"cs_[A-Za-z0-9_]+", sid):
        return None
    o = um(con, "SELECT * FROM store_orders WHERE stripe_session_id=?", (sid,))
    return _conferir(con, o, background)


@r.get("/cart/thanks/", include_in_schema=False)
def carrinho_obrigado(request: Request, background: BackgroundTasks, con: sqlite3.Connection = Depends(get_db)):
    """A volta do Stripe: confere a sessão e mostra a página do pedido (#245), com o estado dele."""
    if not e_do_site(request):
        raise HTTPException(404)
    o = _volta_do_stripe(request, background, con)
    if not o:
        return _sem_cache(ps.carrinho_obrigado(host_de(request), None, lang=idioma.de_request(request), volta=_volta_aqui(request)))
    return _pagina_pedido(request, con, o, "/cart/thanks/", limpar=o["status"] in ("pago", "aguardando"))


@r.get("/store/thanks/", include_in_schema=False)
def loja_obrigado(request: Request, background: BackgroundTasks, con: sqlite3.Connection = Depends(get_db)):
    if not e_do_site(request):
        raise HTTPException(404)
    o = _volta_do_stripe(request, background, con)
    if not o:
        return _sem_cache(ps.obrigado(host_de(request), None, lang=idioma.de_request(request), volta=_volta_aqui(request)))
    return _pagina_pedido(request, con, o, "/store/thanks/")


def _pedido_do_token(request, con, token):
    from command_center.providers import pedido_site
    if not e_do_site(request):
        raise HTTPException(404)
    return pedido_site.achar(con, token)


def _nao_achou(request):
    resp = _sem_cache(paginas.nao_achou(host_de(request)), status=404)
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@r.get("/order/{token}/", include_in_schema=False)
def pedido_pagina(token: str, request: Request, background: BackgroundTasks, con: sqlite3.Connection = Depends(get_db)):
    """O link pessoal do pedido: pago, confirmando, falhou, expirou ou ainda no checkout."""
    o = _pedido_do_token(request, con, token)
    if not o:
        return _nao_achou(request)
    o = _conferir(con, o, background)
    from command_center.providers import pedido_site
    return _pagina_pedido(request, con, o, pedido_site.caminho(o))


@r.get("/order/{token}/cart/", include_in_schema=False)
def pedido_restaurar(token: str, request: Request, con: sqlite3.Connection = Depends(get_db)):
    """"Restore cart": o carrinho com as escolhas do pedido (o carrinho.js junta ao deste navegador e o
    servidor recalcula preço e vaga). Pedido pago não restaura: volta para a página dele."""
    from command_center.providers import pedido_site, stripe_loja
    o = _pedido_do_token(request, con, token)
    if not o:
        return _nao_achou(request)
    if o["status"] in ("pago", "aguardando"):
        return RedirectResponse(pedido_site.caminho(o), status_code=303)
    resp = _sem_cache(ps.carrinho(host_de(request), stripe=stripe_loja.ligado(), lang=idioma.de_request(request),
                                  restaurar=(o["id"], pedido_site.itens_do_carrinho(con, o), o["delivery"])))
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@r.post("/order/{token}/retry", include_in_schema=False)
async def pedido_de_novo(token: str, request: Request, con: sqlite3.Connection = Depends(get_db)):
    """"Try again": um checkout novo com as mesmas escolhas, preço e vaga recalculados (`carrinho.cotar`).
    Sessão pede a conta do pedido aberta neste navegador (e o CSRF dela, no formulário); faltando a conta,
    ou se algo mudou (vaga, estoque, preço que já não fecha), vai para o carrinho restaurado, que mostra o
    porquê. O pedido velho fica como está (falhou/expirou): nada foi cobrado nele."""
    from command_center.api import portal as api_portal
    from command_center.providers import carrinho, pedido_site, stripe_loja
    o = _pedido_do_token(request, con, token)
    if not o:
        return _nao_achou(request)
    volta = pedido_site.caminho(o)
    if o["status"] in ("pago", "aguardando") or pedido_site.refeito(con, o):
        return RedirectResponse(volta, status_code=303)
    restaurar = RedirectResponse(volta + "cart/", status_code=303)
    if not stripe_loja.ligado():
        return restaurar
    if _estourou(_ip(request)):
        return _pagina_pedido(request, con, o, volta, erro="Too many requests in a row. Please try again in a few minutes.",
                              status=429)
    c = await _campos(request)
    conta = api_portal.conta_do_cookie(request, con)
    csrf = request.cookies.get(api_portal.COOKIE_CSRF, "")
    if conta and not (csrf and hmac.compare_digest(csrf, c.get("csrf", ""))):
        conta = None                                    # sem o CSRF da conta, segue como visitante
    itens = pedido_site.itens_do_carrinho(con, o)
    if not itens or not conta or (o["account_id"] and conta != o["account_id"]):
        return restaurar                                # #248: comprar pede a conta (a do pedido); o carrinho pede o login
    try:
        novo, url = carrinho.criar_checkout(con, itens, o["delivery"], conta, _origem(request), host_de(request),
                                            lang=idioma.de_request(request))
    except carrinho.ErroCarrinho:
        return restaurar
    except stripe_loja.ErroStripe as e:
        import logging
        logging.getLogger("urace.loja").warning("checkout de novo falhou: %s", str(e)[:200])
        return _pagina_pedido(request, con, o, volta, erro="We couldn’t open the secure checkout just now. Please try again in a minute.",
                              status=502)
    from command_center.db import atualizar, auditar
    atualizar(con, "store_orders", novo, retry_of=o["id"])
    auditar(con, "store.retry", f"portal:{conta}" if conta else "site", entity_type="store_order", entity_id=novo,
            detail={"de": o["id"], "estado_antes": o["status"]})
    con.commit()
    return RedirectResponse(url, status_code=303)


@r.get("/_f/{nome}", include_in_schema=False)
def foto_do_editor(nome: str):
    """#300: a foto que a equipe subiu no editor do site (WebP sem EXIF). Pública; o nome é o hash do arquivo."""
    from fastapi.responses import FileResponse

    from command_center.providers import editor_site
    caminho = editor_site.arquivo_da_foto(nome)
    if not caminho:
        raise HTTPException(404)
    return FileResponse(caminho, media_type="image/webp", headers={"Cache-Control": "public, max-age=31536000, immutable"})


@r.get("/store/img/{nome}", include_in_schema=False)
def foto_da_loja(nome: str, request: Request):
    """#298: a foto que a equipe subiu no painel (WebP sem EXIF). Pública como as do site (e o painel mostra a
    mesma); o nome leva o hash do arquivo, então o navegador guarda por um ano."""
    from fastapi.responses import FileResponse

    from command_center.providers import loja
    caminho = loja.arquivo_da_foto(nome)
    if not caminho:
        raise HTTPException(404)
    return FileResponse(caminho, media_type="image/webp", headers={"Cache-Control": "public, max-age=31536000, immutable"})


@r.get("/store/cancelled/", include_in_schema=False)
def loja_cancelado(request: Request):
    if not e_do_site(request):
        raise HTTPException(404)
    return _sem_cache(ps.cancelado(host_de(request), _slug(request.query_params.get("p") or ""), lang=idioma.de_request(request),
                                   volta=_volta_aqui(request)))


def _volta_aqui(request):
    return request.url.path + (f"?{request.url.query}" if request.url.query else "")


@r.post("/language/", include_in_schema=False)
async def trocar_idioma(request: Request):
    """#248: a chave EN/PT das páginas da compra. Grava a escolha (um ano) e volta para a mesma página."""
    if not e_do_site(request):
        raise HTTPException(404)
    c = await _campos(request)
    volta = c.get("volta") or "/cart/"
    if not idioma.volta_ok(volta):
        volta = "/cart/"
    resp = RedirectResponse(volta, status_code=303)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.set_cookie(idioma.COOKIE, idioma.norma(c.get("lang")), max_age=idioma.UM_ANO, path="/", samesite="lax",
                    secure=request.url.scheme == "https", httponly=True)
    return resp


def robots(request):
    """robots.txt do site: enquanto é prévia, ninguém indexa; depois, só o painel fica de fora."""
    if paginas.preview():
        return "User-agent: *\nDisallow: /\n"
    return (f"User-agent: *\nDisallow: /ops/\nAllow: /\n\nSitemap: https://{host_de(request)}/sitemap.xml\n")


def sitemap(request):
    host = host_de(request)
    from command_center.providers import editor_site
    novas = [c for c in (_do_banco(editor_site.caminhos_novos) or []) if c not in PAGINAS]   # #300: as do editor
    urls = "".join(f"  <url><loc>https://{host}{c}</loc></url>\n" for c in [*_com_o_painel(ps.caminhos), *novas])
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "</urlset>\n")

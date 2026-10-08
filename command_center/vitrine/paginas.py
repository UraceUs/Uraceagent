"""O HTML do site novo (#148), montado no servidor.

Cada página sai pronta: o Google lê sem JavaScript, o celular desenha rápido, e o único
script (`agenda.js`) só acende a agenda na página do serviço. Sem ele, o botão de reservar
continua levando para a agenda da área do cliente.

Regras da casa (CLAUDE.md) que este arquivo segue: um `h1` por página e seções em `h2`;
título e descrição por página; `canonical`; schema (JSON-LD); fotos com `loading="lazy"`
fora do topo; enquanto o site é prévia (`CC_SITE_PREVIEW`), `noindex`.
"""
import hashlib
import json
import os
from html import escape

from command_center.vitrine import conteudo as C

STATIC = os.path.join(os.path.dirname(__file__), "static")
PORTAL = "/ops/portal"


def e(v):
    return escape(str(v), quote=True)


def _versao(nome):
    """Hash do arquivo no endereço (`site.css?v=…`): o navegador guarda por um ano e o deploy
    seguinte troca o nome sozinho."""
    try:
        with open(os.path.join(STATIC, nome), "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()[:10]
    except OSError:
        return "0"


def estatico(nome):
    return f"/_s/{nome}?v={_versao(nome)}"


def preview():
    return os.environ.get("CC_SITE_PREVIEW", "1") != "0"


def usd(n):
    return f"${n:,.0f}" if float(n).is_integer() else f"${n:,.2f}"


# ------------------------------------------------------------------ peças comuns
def _negocio(host):
    """Schema do negócio (o mesmo LocalBusiness que o Yoast publica hoje no urace.us)."""
    end = C.SITE["endereco"]
    return {
        "@context": "https://schema.org", "@type": ["SportsActivityLocation", "LocalBusiness"],
        "@id": f"https://{host}/#business", "name": C.SITE["nome"], "url": f"https://{host}/",
        "telephone": C.SITE["telefone_e164"], "email": C.SITE["emails"][0],
        "image": f"https://{host}{estatico('img/home-hero.webp')}",
        "address": {"@type": "PostalAddress", "streetAddress": end["rua"], "addressLocality": end["cidade"],
                    "addressRegion": end["estado"], "postalCode": end["cep"], "addressCountry": end["pais"]},
        "openingHoursSpecification": [{"@type": "OpeningHoursSpecification",
                                       "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                                                     "Saturday", "Sunday"], "opens": "08:00", "closes": "20:00"}],
        "sameAs": list(C.SITE["redes"].values()),
    }


def _ld(dados):
    # `</` dentro do JSON fecharia a tag <script>: escapa a barra
    return '<script type="application/ld+json">' + json.dumps(dados, ensure_ascii=False).replace("</", "<\\/") + "</script>"


def _link(rot, href, atual):
    marca = ' aria-current="page"' if href == atual else ""
    return f'<a href="{e(href)}"{marca}>{e(rot)}</a>'


def _cabecalho(atual):
    itens = "".join(f"<li>{_link(r, h, atual)}</li>" for r, h in C.MENU)
    return f"""<header class="topo">
  <a class="pular" href="#conteudo">Skip to content</a>
  <div class="topo-in">
    <a class="logo" href="/" aria-label="URACE home"><img src="{estatico('img/logo.svg')}" alt="URACE" width="120" height="20"></a>
    <nav class="menu" aria-label="Main">
      <ul>{itens}</ul>
    </nav>
    <details class="menu-cel">
      <summary aria-label="Open menu"><span></span><span></span><span></span></summary>
      <nav aria-label="Main (mobile)"><ul>{itens}<li><a href="{PORTAL}">My account</a></li></ul></nav>
    </details>
    <a class="conta" href="{PORTAL}">My account</a>
    <a class="btn btn-sm" href="/services/arrive-and-drive/#reservar">Book now</a>
  </div>
</header>"""


def _rodape():
    end = C.SITE["endereco"]
    redes = "".join(f'<li><a href="{e(u)}" rel="noopener">{e(n)}</a></li>' for n, u in C.SITE["redes"].items())
    nav = "".join(f'<li><a href="{e(h)}">{e(r)}</a></li>' for r, h in C.MENU)
    emails = "".join(f'<a href="mailto:{e(m)}">{e(m)}</a>' for m in C.SITE["emails"])
    return f"""<footer class="rodape">
  <div class="rodape-in">
    <div class="rodape-marca">
      <img src="{estatico('img/logo-footer.svg')}" alt="URACE" width="120" height="20" loading="lazy">
      <p>{e(C.SITE['slogan'])}</p>
      <address>{e(end['rua'])}, {e(end['cidade'])}, {e(end['estado'])} {e(end['cep'])}<br>{e(end['onde'].capitalize())}</address>
      <p><a href="tel:{e(C.SITE['telefone_e164'])}">{e(C.SITE['telefone'])}</a></p>
      <p class="emails">{emails}</p>
      <p class="muted">{e(C.SITE['horario'])}</p>
    </div>
    <nav aria-label="Footer"><h2 class="rodape-h">Navigation</h2><ul>{nav}</ul></nav>
    <div><h2 class="rodape-h">Socials</h2><ul>{redes}</ul></div>
  </div>
  <p class="rodape-fim">© 2026 URACE · <a href="/legal/privacy.html">Privacy policy</a></p>
</footer>"""


def layout(*, host, caminho, titulo, descricao, corpo, schemas=(), scripts=(), foto=None):
    canon = f"https://{host}{caminho}"
    robots = '<meta name="robots" content="noindex, nofollow">' if preview() else ""
    og_img = (f'<meta property="og:image" content="https://{host}{estatico("img/" + foto)}">'
              f'<meta name="twitter:image" content="https://{host}{estatico("img/" + foto)}">') if foto else ""
    js = "".join(f'<script src="{estatico(s)}" defer></script>' for s in scripts)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{e(titulo)}</title>
<meta name="description" content="{e(descricao)}">
{robots}
<link rel="canonical" href="{e(canon)}">
<meta property="og:type" content="website"><meta property="og:title" content="{e(titulo)}">
<meta property="og:description" content="{e(descricao)}"><meta property="og:url" content="{e(canon)}">{og_img}
<meta property="og:site_name" content="URACE"><meta property="og:locale" content="en_US">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{e(titulo)}">
<meta name="twitter:description" content="{e(descricao)}">
<meta name="theme-color" content="#0b0b0f">
<link rel="icon" type="image/png" href="{estatico('img/favicon.png')}">
<link rel="preload" href="/_s/fonts/archivo-expanded.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{estatico('site.css')}">
{''.join(_ld(s) for s in schemas)}
{js}
</head>
<body>
{_cabecalho(caminho)}
<main id="conteudo">
{corpo}
</main>
{_rodape()}
</body>
</html>"""


def _lista(itens, classe="checks"):
    return f'<ul class="{classe}">' + "".join(f"<li>{e(i)}</li>" for i in itens) + "</ul>"


# ------------------------------------------------------------------ páginas
def home(host):
    h = C.HOME
    numeros = "".join(f'<div class="numero"><strong>{e(n)}</strong><span>{e(t)}</span></div>' for n, t in h["numeros"])
    campeoes = "".join(f'<figure><img src="{estatico("img/" + f)}" alt="" width="480" height="631" loading="lazy">'
                       f'<figcaption>{e(n)}</figcaption></figure>'
                       for f, n in zip(h["fotos_campeoes"], h["campeoes"]))
    servicos = "".join(
        f'<article class="card-servico"><h3>{e(s["nome"])}</h3><p>{e(s["texto"])}</p>'
        + (f'<p class="preco">{e(s["preco"])}</p>' if s.get("preco") else "")
        + f'<a class="seta" href="{e(s["link"])}">See {e(s["nome"])}</a></article>'
        for s in h["servicos"])
    depo = "".join(f'<blockquote><p>{e(t)}</p><footer>{e(n)}{(" · " + e(c)) if c else ""}</footer></blockquote>'
                   for n, c, t in h["depoimentos"])
    corpo = f"""
<section class="hero hero-home">
  <div class="hero-in">
    <h1>{e(h['h1'])}</h1>
    <p class="hero-sub">{e(h['sub'])}</p>
    <div class="hero-acoes"><a class="btn" href="/services/arrive-and-drive/#reservar">Book your race session</a>
      <a class="btn btn-linha" href="{e(C.SITE['whatsapp'])}" rel="noopener">Talk to us</a></div>
  </div>
</section>
<section class="faixa escura" aria-labelledby="h-numeros">
  <h2 id="h-numeros" class="sr">URACE in numbers</h2>
  <div class="numeros">{numeros}</div>
</section>
<section class="faixa clara" aria-labelledby="h-servicos">
  <div class="largura">
    <h2 id="h-servicos">Services</h2>
    <div class="servicos">{servicos}</div>
  </div>
</section>
<section class="faixa escura" aria-labelledby="h-campeoes">
  <div class="largura">
    <h2 id="h-campeoes">We build <em>Champions</em></h2>
    <p class="lede">Urace, built to win!</p>
    <div class="campeoes">{campeoes}</div>
  </div>
</section>
<section class="faixa clara" aria-labelledby="h-treino">
  <div class="largura duas">
    <div><h2 id="h-treino">Kart Driver Training</h2></div>
    <div class="texto">{''.join(f'<p>{e(p)}</p>' for p in h['treino'])}
      <a class="seta" href="{e(C.ANTIGO + '/kart-training-packages/')}">See the Academy</a></div>
  </div>
</section>
<section class="faixa escura" aria-labelledby="h-depo">
  <div class="largura">
    <h2 id="h-depo">Built by Urace</h2>
    <p class="lede">Testimonials from parents and drivers</p>
    <div class="depoimentos">{depo}</div>
  </div>
</section>
<section class="faixa clara" aria-labelledby="h-sobre">
  <div class="largura duas">
    <img src="{estatico('img/sobre.webp')}" alt="Italo Silveira at the track" width="573" height="490" loading="lazy">
    <div class="texto"><h2 id="h-sobre">About</h2><p>{e(h['sobre'])}</p></div>
  </div>
</section>
<section class="faixa vermelha" aria-labelledby="h-duvidas">
  <div class="largura centro">
    <h2 id="h-duvidas">Do you still have questions?</h2>
    <p>Contact our team to get all the information about our products and services.</p>
    <a class="btn btn-branco" href="{e(C.SITE['whatsapp'])}" rel="noopener">Talk to us on WhatsApp</a>
  </div>
</section>"""
    return layout(host=host, caminho="/", titulo=h["titulo"], descricao=h["descricao"], corpo=corpo,
                  schemas=(_negocio(host),), foto=h["foto"])


def arrive_and_drive(host):
    a = C.ARRIVE
    karts = "".join(
        f'<label class="kart"><input type="radio" name="kart" value="{e(k["nome"])}" data-preco="{k["preco"]}"'
        f'{" checked" if i == 1 else ""}><span class="kart-nome">{e(k["nome"])}</span>'
        f'<span class="kart-idade">{e(k["idade"])}</span><span class="kart-preco">{usd(k["preco"])}</span></label>'
        for i, k in enumerate(C.KARTS))
    faq = "".join(f'<details><summary>{e(t)}</summary>{"".join(f"<p>{e(p)}</p>" for p in ps)}</details>'
                  for t, ps in a["faq"])
    depo = "".join(f'<blockquote><p>{e(t)}</p><footer>{e(n)}</footer></blockquote>' for n, t in a["depoimentos"])
    passos = "".join(f"<li>{e(p)}</li>" for p in a["passos"])
    oferta = {
        "@context": "https://schema.org", "@type": "Service", "name": "Kart Arrive and Drive in Orlando",
        "serviceType": "Kart racing experience", "description": a["descricao"],
        "provider": {"@id": f"https://{host}/#business"}, "areaServed": "Orlando, FL",
        "offers": [{"@type": "Offer", "name": k["nome"], "price": f"{k['preco']:.2f}", "priceCurrency": "USD",
                    "availability": "https://schema.org/InStock", "url": f"https://{host}{a['caminho']}"} for k in C.KARTS],
        # #164: o botão de reservar, para o Google entender que dá para reservar online
        "potentialAction": {"@type": "ReserveAction", "target": {"@type": "EntryPoint",
                            "urlTemplate": f"https://{host}{PORTAL}/reserve", "actionPlatform": ["http://schema.org/DesktopWebPlatform",
                                                                                                    "http://schema.org/MobileWebPlatform"]},
                            "result": {"@type": "Reservation", "name": "Kart Arrive and Drive session"}},
    }
    perguntas = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": t, "acceptedAnswer": {"@type": "Answer", "text": " ".join(ps)}} for t, ps in a["faq"]]}
    trilha = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": f"https://{host}/"},
        {"@type": "ListItem", "position": 2, "name": "Arrive and Drive", "item": f"https://{host}{a['caminho']}"}]}
    corpo = f"""
<section class="hero hero-servico hero-arrive">
  <div class="hero-in">
    <p class="eyebrow">{e(a['eyebrow'])}</p>
    <h1>{e(a['h1'])}</h1>
    <p class="hero-sub">{e(a['sub'])}</p>
    <div class="hero-acoes"><a class="btn" href="#reservar">Book my experience</a>
      <span class="hero-preco">From {usd(C.preco_minimo())} per driver</span></div>
  </div>
</section>

<section class="faixa clara reserva-faixa" aria-labelledby="h-reservar" id="reservar">
  <div class="largura reserva-grade">
    <div class="reserva-info">
      <h2 id="h-reservar">Book your session</h2>
      <fieldset class="karts"><legend>1 · Choose your kart</legend>{karts}</fieldset>
      <div class="inclui">
        <div><h3>We provide</h3>{_lista(a['fornece'])}</div>
        <div><h3>You bring</h3>{_lista(a['trazer'])}</div>
      </div>
    </div>
    <div class="agenda" data-api="/ops/api/vitrine/agenda" data-portal="{PORTAL}/reserve">
      <h3>2 · Pick a day</h3>
      <div class="agenda-mes" hidden>
        <button type="button" class="agenda-nav" data-ir="-1" aria-label="Previous month">‹</button>
        <strong class="agenda-titulo" aria-live="polite"></strong>
        <button type="button" class="agenda-nav" data-ir="1" aria-label="Next month">›</button>
      </div>
      <div class="agenda-grade" role="group" aria-label="Available days"></div>
      <div class="agenda-turnos" role="group" aria-label="Morning or afternoon" hidden></div>
      <p class="agenda-aviso" role="status">Loading the open days…</p>
      <div class="agenda-total"><span class="agenda-resumo">4-stroke · per driver</span><strong class="agenda-preco">{usd(C.KARTS[1]['preco'])}</strong></div>
      <a class="btn btn-cheio agenda-ir" href="{PORTAL}/reserve">Continue to booking</a>
      <p class="agenda-nota">Next: sign in or create your account and choose the driver. Then you get the invoice (session + refundable security deposit) to pay online and the waiver to sign. Your spot is confirmed as soon as both are done. Track fees are paid to the Orlando Kart Center.</p>
    </div>
  </div>
</section>

<section class="faixa escura" aria-labelledby="h-esperar">
  <div class="largura duas">
    <div><h2 id="h-esperar">What to expect from your Arrive and Drive</h2></div>
    {_lista(a['esperar'])}
  </div>
</section>

<section class="faixa clara" aria-labelledby="h-porque">
  <div class="largura">
    <h2 id="h-porque">Why URACE</h2>
    <ul class="porque">{''.join(f'<li>{e(p)}</li>' for p in a['porque'])}</ul>
  </div>
</section>

<section class="faixa clara" aria-labelledby="h-quem">
  <div class="largura duas">
    <img src="{estatico('img/' + a['foto_equipe'])}" alt="URACE drivers and karts at the Orlando Kart Center" width="598" height="517" loading="lazy">
    <div class="texto"><h2 id="h-quem">Who can join the Arrive and Drive in Orlando?</h2>{_lista(a['quem'])}
      <a class="btn" href="#reservar">Book my experience</a></div>
  </div>
</section>

<section class="faixa escura" aria-labelledby="h-como">
  <div class="largura">
    <h2 id="h-como">How it works</h2>
    <ol class="passos">{passos}</ol>
  </div>
</section>

<section class="faixa clara" aria-labelledby="h-faq">
  <div class="largura estreita">
    <h2 id="h-faq">Frequently Asked Questions</h2>
    <div class="faq">{faq}</div>
  </div>
</section>

<section class="faixa escura" aria-labelledby="h-local">
  <div class="largura duas">
    <div><h2 id="h-local">Location</h2>
      <address>{e(C.SITE['endereco']['rua'])}, {e(C.SITE['endereco']['cidade'])}, Florida — {e(C.SITE['endereco']['onde'])}.</address></div>
    <div class="depoimentos">{depo}</div>
  </div>
</section>

<section class="faixa vermelha" aria-labelledby="h-fecho">
  <div class="largura centro">
    <h2 id="h-fecho">{e(a['fecho'])}</h2>
    <div class="hero-acoes centro"><a class="btn btn-branco" href="#reservar">Book my experience</a>
      <a class="btn btn-linha-branca" href="{e(C.SITE['whatsapp'])}" rel="noopener">Need more details? Let’s chat</a></div>
  </div>
</section>"""
    return layout(host=host, caminho=a["caminho"], titulo=a["titulo"], descricao=a["descricao"], corpo=corpo,
                  schemas=(_negocio(host), oferta, perguntas, trilha), scripts=("agenda.js",), foto=a["foto"])


def nao_achou(host):
    corpo = """
<section class="faixa clara"><div class="largura estreita centro">
  <h1>Page not found</h1>
  <p>This page doesn't exist on the new site yet.</p>
  <div class="hero-acoes centro"><a class="btn" href="/">Go to the home page</a></div>
</div></section>"""
    return layout(host=host, caminho="/404", titulo="Page not found | URACE", descricao="This page was not found.",
                  corpo=corpo)

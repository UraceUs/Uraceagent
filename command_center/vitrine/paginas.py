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
from command_center.vitrine import medicao

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
        # #252: o mesmo que o urace.us de hoje publica — o SEO local não pode cair na troca
        "alternateName": C.SITE["outro_nome"], "description": C.SITE["descricao_negocio"],
        "priceRange": C.SITE["faixa_preco"], "currenciesAccepted": C.SITE["moeda"],
        "geo": {"@type": "GeoCoordinates", "latitude": C.SITE["geo"][0], "longitude": C.SITE["geo"][1]},
        "hasMap": C.SITE["mapa"],
        "areaServed": [{"@type": t, "name": n} for t, n in C.SITE["atende"]],
        "sameAs": [*C.SITE["redes"].values(), *C.SITE["perfis"]],
    }


def _marca(host):
    """#252: quem é a URACE e qual é o site. O urace.us de hoje publica os dois (Yoast); sem eles, o
    Google perde o logo, as redes e o nome do site na troca de domínio."""
    return ({"@context": "https://schema.org", "@type": "Organization", "@id": f"https://{host}/#organization",
             "name": C.SITE["nome"], "url": f"https://{host}/",
             "logo": {"@type": "ImageObject", "url": f"https://{host}{estatico('img/favicon.png')}"},
             "sameAs": [*C.SITE["redes"].values(), *C.SITE["perfis"]]},
            {"@context": "https://schema.org", "@type": "WebSite", "@id": f"https://{host}/#website",
             "url": f"https://{host}/", "name": C.SITE["nome"], "inLanguage": "en-US",
             "publisher": {"@id": f"https://{host}/#organization"}})


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
    <a class="carrinho-topo" href="/cart/" aria-label="Cart"><svg aria-hidden="true" viewBox="0 0 24 24" width="22" height="22"><path d="M3 4h2l2.4 10.2a1 1 0 0 0 1 .8h8.9a1 1 0 0 0 1-.8L20 8H6.2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="9" cy="19" r="1.6" fill="currentColor"/><circle cx="17" cy="19" r="1.6" fill="currentColor"/></svg><span class="carrinho-n" data-carrinho-n hidden></span></a>
    <a class="btn btn-sm" href="/services/arrive-and-drive/#reservar">Book now</a>
  </div>
</header>"""


def _rodape():
    end = C.SITE["endereco"]
    redes = "".join(f'<li><a href="{e(u)}" rel="noopener">{e(n)}</a></li>' for n, u in C.SITE["redes"].items())
    nav = "".join(f'<li><a href="{e(h)}">{e(r)}</a></li>' for r, h in C.RODAPE)
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
  <p class="rodape-fim">© 2026 URACE | All rights reserved · <a href="/legal/privacy.html">Privacy policy</a></p>
</footer>"""


def layout(*, host, caminho, titulo, descricao, corpo, schemas=(), scripts=(), foto=None, indexar=True, lang="en",
           medicao_eventos=()):
    """`medicao_eventos` (#260): o que esta página já sabe para o `dataLayer` (hoje, o `purchase`
    do pedido pago). Sem `SITE_GTM_ID`/`SITE_META_PIXEL_ID` no ambiente, nada de medição sai."""
    canon = f"https://{host}{caminho}"
    robots = '<meta name="robots" content="noindex, nofollow">' if preview() or not indexar else ""
    og_img = (f'<meta property="og:image" content="https://{host}{estatico("img/" + foto)}">'
              f'<meta name="twitter:image" content="https://{host}{estatico("img/" + foto)}">') if foto else ""
    # #236: carrinho.js em toda página (o contador do topo); vem antes, a agenda e a loja usam o que ele expõe
    # #260: medicao.js primeiro (o dataLayer existe antes de todo mundo) e só quando há id no ambiente;
    # campanha.js em toda página, sempre: ele é nosso e não fala com ninguém de fora
    med = medicao.cabeca(caminho, medicao_eventos)
    js = "".join(f'<script src="{estatico(s)}" defer></script>'
                 for s in ((medicao.SCRIPT,) if med else ()) + ("campanha.js", "carrinho.js", *scripts))
    return f"""<!doctype html>
<html lang="{"pt-BR" if lang == "pt" else "en"}">
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
{med}
{js}
</head>
<body>
{medicao.noscript(caminho)}
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
    from command_center.vitrine.paginas_site import _post_card, dados     # paginas_site importa este módulo
    h = C.HOME
    numeros = "".join(f'<div class="numero"><strong>{e(n)}</strong><span>{e(t)}</span></div>' for n, t in h["numeros"])
    campeoes = "".join(f'<figure><img src="{estatico("img/" + f)}" alt="" width="480" height="631" loading="lazy">'
                       f'<figcaption>{e(n)}{f"<br><small>{e(d)}</small>" if d else ""}</figcaption></figure>'
                       for f, (n, d) in zip(h["fotos_campeoes"], h["campeoes"]))
    # o preço do Arrive and Drive é o de KARTS, o mesmo que a página e a reserva mostram
    servicos = "".join(
        f'<article class="card-servico"><h3>{e(s["nome"])}</h3><p>{e(s["texto"])}</p>'
        + (f'<p class="preco">Starting at {usd(C.preco_minimo())}</p>' if s.get("preco_kart") else "")
        + f'<a class="seta" href="{e(s["link"])}">See {e(s["nome"])}</a></article>'
        for s in h["servicos"])
    depo = "".join(f'<blockquote><p>{e(t)}</p><footer>{e(n)}{(" · " + e(c)) if c else ""}</footer></blockquote>'
                   for n, c, t in h["depoimentos"])
    eventos = " · ".join(f'<a href="{e(href)}">{e(r)}</a>' for r, href in h["eventos_links"])
    posts = "".join(_post_card(p) for p in dados("posts.json")["posts"][:3])
    corpo = f"""
<section class="hero hero-home">
  <div class="hero-in">
    <h1>{e(h['h1'])}</h1>
    <p class="hero-sub">{e(h['sub'])}</p>
    <div class="hero-acoes"><a class="btn" href="/services/arrive-and-drive/#reservar">Book your race session</a>
      <a class="btn btn-linha" href="{e(C.SITE['whatsapp'])}" rel="noopener">Talk to us</a></div>
  </div>
</section>
<section class="faixa clara" aria-labelledby="h-metodo">
  <div class="largura duas">
    <div class="texto"><h2 id="h-metodo">{e(h['metodo'][0])}</h2><p>{e(h['metodo'][1])}</p></div>
    <div class="texto"><h2>{e(h['eventos'][0])}</h2><p>{e(h['eventos'][1])}</p><p>{eventos}</p></div>
  </div>
</section>
<section class="faixa escura" aria-labelledby="h-numeros">
  <div class="largura">
    <h2 id="h-numeros">{e(h['escada'][0])}</h2>
    <p class="lede">{e(h['escada'][1])}</p>
  </div>
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
    <p class="lede">URACE, built to win!</p>
    <div class="campeoes">{campeoes}</div>
  </div>
</section>
<section class="faixa clara" aria-labelledby="h-treino">
  <div class="largura duas">
    <div><h2 id="h-treino">Kart Driver Training</h2></div>
    <div class="texto">{''.join(f'<p>{e(p)}</p>' for p in h['treino'])}
      <a class="seta" href="/academy/">See the Academy</a></div>
  </div>
</section>
<section class="faixa escura" aria-labelledby="h-depo">
  <div class="largura">
    <h2 id="h-depo">{e(h['depoimentos_titulo'])}</h2>
    <p class="lede">{e(h['depoimentos_sub'])}</p>
    <div class="depoimentos">{depo}</div>
  </div>
</section>
<section class="faixa clara" aria-labelledby="h-sobre">
  <div class="largura duas">
    <img src="{estatico('img/sobre.webp')}" alt="Italo Silveira at the track" width="573" height="490" loading="lazy">
    <div class="texto"><h2 id="h-sobre">About</h2><p>{e(h['sobre'])}</p></div>
  </div>
</section>
<section class="faixa escura" aria-labelledby="h-blog">
  <div class="largura">
    <h2 id="h-blog">{e(h['blog_titulo'])}</h2>
    <p class="lede">{e(h['blog_sub'])}</p>
    <div class="posts-grade">{posts}</div>
  </div>
</section>
<section class="faixa vermelha" aria-labelledby="h-duvidas">
  <div class="largura centro">
    <h2 id="h-duvidas">{e(h['fecho'][0])}</h2>
    <p>{e(h['fecho'][1])}</p>
    <a class="btn btn-branco" href="{e(C.SITE['whatsapp'])}" rel="noopener">Talk to us on WhatsApp</a>
  </div>
</section>"""
    return layout(host=host, caminho="/", titulo=h["titulo"], descricao=h["descricao"], corpo=corpo,
                  schemas=(_negocio(host), *_marca(host)), foto=h["foto"])


def _karts_do_painel(servicos):
    """#263: o kart do site e o serviço do painel que o vende, casados pela chave (`site_kart`).

    `servicos=None` é "o painel não respondeu" (banco fora): a página sai com os quatro karts e os
    preços de `KARTS`, e o `agenda.js` corrige quando a lista chegar. Com a lista na mão, fica na
    página só o kart que tem **um** serviço ativo — o kart que não dá para comprar sai, em vez de
    ficar na tela oferecendo o que não existe (dono, 15/10, #263). Dois serviços com a mesma chave
    são ambíguos: ninguém escolhe no lugar da pessoa, então esse kart também sai.
    """
    if servicos is None:
        return [(k, None) for k in C.KARTS]
    por_chave = {}
    for sv in servicos:
        chave = " ".join(str(sv.get("site_kart") or "").split()).lower()
        if chave:
            por_chave.setdefault(chave, []).append(sv)
    return [(k, por_chave[k["nome"].lower()][0]) for k in C.KARTS
            if len(por_chave.get(k["nome"].lower(), ())) == 1]


# #262 (dono, 15/10): *"sim um caminho somente levando para o carrinho; de lá do carrinho para seguir
# com a compra requer criar a conta e seguir, lembre-se que o único método de pagamento do site será o
# Stripe"*. O texto antigo prometia a invoice do QuickBooks — caminho que o site público não oferece
# mais (a equipe continua faturando por lá). Este conta o caminho que existe: carrinho → conta →
# Stripe → waiver.
NOTA_RESERVA = ("Next: the session goes to your cart. Sign in or create your URACE account, then pay with Stripe — "
                "card, Apple Pay or Google Pay. Your spot is confirmed once the payment goes through and the driver's "
                "waiver is signed in your account. The security deposit is refundable. Track fees are paid to the "
                "Orlando Kart Center.")


PROPRIO = ' data-proprio="1"'


def arrive_and_drive(host, servicos=None, lead_follow=None):
    a = C.ARRIVE
    # #50/#263: o preço que a página mostra é o do painel; `KARTS` só vale enquanto o painel não falou
    pares = _karts_do_painel(servicos)
    precos = [(sv["price"] if sv else k["preco"]) for k, sv in pares]
    # o 4-stroke já vem marcado quando está na página (é o que os termos recomendam para quem começa);
    # saiu da página, marca o primeiro que sobrou — a página nunca fica sem kart escolhido
    nomes = [k["nome"] for k, _sv in pares]
    marcado = "4-stroke" if "4-stroke" in nomes else (nomes[0] if nomes else None)
    # #279: o kart próprio traz o aviso no próprio cartão (sempre à vista) e repete perto do botão quando escolhido
    karts = "".join(
        f'<label class="kart{" kart-proprio" if k.get("proprio") else ""}"><input type="radio" name="kart" value="{e(k["nome"])}"'
        f' data-kart="{e(k["nome"])}" data-preco="{preco:g}"{PROPRIO if k.get("proprio") else ""}'
        f'{" checked" if k["nome"] == marcado else ""}><span class="kart-nome">{e(k["nome"])}</span>'
        f'<span class="kart-idade">{e(k["idade"])}</span><span class="kart-preco">{usd(preco)}</span>'
        + (f'<span class="kart-aviso">{e(k["aviso"])}</span>' if k.get("aviso") else "") + '</label>'
        for (k, _sv), preco in zip(pares, precos, strict=True))
    # #279: o Lead and Follow só aparece quando o painel vende (preço do painel, #50)
    lf = lead_follow
    caixa_lf = (f'<label class="agenda-lf addon"><input type="checkbox" name="lead_follow" value="1">'
                f'<span class="addon-txt"><strong>Add Lead and Follow</strong> · {e(C.LEAD_AND_FOLLOW["texto"])}</span>'
                f'<span class="addon-preco">+{usd(lf["price"])}</span></label>') if lf and pares else \
        '<label class="agenda-lf addon" hidden><input type="checkbox" name="lead_follow" value="1"><span class="addon-txt">' \
        f'<strong>Add Lead and Follow</strong> · {e(C.LEAD_AND_FOLLOW["texto"])}</span><span class="addon-preco"></span></label>'
    aviso_proprio = next((k["aviso"] for k, _sv in pares if k.get("aviso")), C.AVISO_KART_PROPRIO)
    if not pares:
        karts = ('<p class="agenda-indisponivel"><span>Online booking is closed right now. Talk to us and we book '
                 f'your session for you:</span> <a href="{e(C.SITE["whatsapp"])}" rel="noopener">WhatsApp '
                 f'{e(C.SITE["telefone"])}</a> <a href="mailto:{e(C.SITE["emails"][0])}">{e(C.SITE["emails"][0])}</a></p>')
    faq = "".join(f'<details><summary>{e(t)}</summary>{"".join(f"<p>{e(p)}</p>" for p in ps)}</details>'
                  for t, ps in a["faq"])
    depo = "".join(f'<blockquote><p>{e(t)}</p><footer>{e(n)}</footer></blockquote>' for n, t in a["depoimentos"])
    passos = "".join(f"<li>{e(p)}</li>" for p in a["passos"])
    oferta = {
        "@context": "https://schema.org", "@type": "Service", "name": "Kart Arrive and Drive in Orlando",
        "serviceType": "Kart racing experience", "description": a["descricao"],
        "provider": {"@id": f"https://{host}/#business"}, "areaServed": "Orlando, FL",
        # #263: oferta só do kart que o site vende de verdade, com o preço do painel (#50)
        "offers": [{"@type": "Offer", "name": k["nome"], "price": f"{preco:.2f}", "priceCurrency": "USD",
                    "availability": "https://schema.org/InStock", "url": f"https://{host}{a['caminho']}"}
                   for (k, _sv), preco in zip(pares, precos, strict=True)],
        # #164/#262: reservar começa nesta página (kart, dia e turno) e termina no carrinho
        "potentialAction": {"@type": "ReserveAction", "target": {"@type": "EntryPoint",
                            "urlTemplate": f"https://{host}{a['caminho']}#reservar", "actionPlatform": ["http://schema.org/DesktopWebPlatform",
                                                                                                           "http://schema.org/MobileWebPlatform"]},
                            "result": {"@type": "Reservation", "name": "Kart Arrive and Drive session"}},
    }
    if not pares:                            # nada à venda agora: o Google não recebe oferta nem ação
        oferta.pop("offers")
        oferta.pop("potentialAction")
    perguntas = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": t, "acceptedAnswer": {"@type": "Answer", "text": " ".join(ps)}} for t, ps in a["faq"]]}
    trilha = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": f"https://{host}/"},
        {"@type": "ListItem", "position": 2, "name": "Arrive and Drive", "item": f"https://{host}{a['caminho']}"}]}
    # "From $X per driver" só existe quando há kart à venda; o preço é o do painel (#50)
    desde = f'<span class="hero-preco">From {usd(min(precos))} per driver</span>' if precos else ""
    resumo = marcado or ""
    preco_marcado = next((p for (k, _sv), p in zip(pares, precos, strict=True) if k["nome"] == marcado), None)
    sem_venda = "" if pares else " hidden"      # nada à venda: o total e o botão não ficam na tela vazios
    corpo = f"""
<section class="hero hero-servico hero-arrive">
  <div class="hero-in">
    <p class="eyebrow">{e(a['eyebrow'])}</p>
    <h1>{e(a['h1'])}</h1>
    <p class="hero-sub">{e(a['sub'])}</p>
    <div class="hero-acoes"><a class="btn" href="#reservar">Book my experience</a>
      {desde}</div>
  </div>
</section>

<section class="faixa clara reserva-faixa" aria-labelledby="h-reservar" id="reservar">
  <div class="largura reserva-grade">
    <div class="reserva-info">
      <h2 id="h-reservar">Book your session</h2>
      <fieldset class="karts"><legend>1 · Choose your kart</legend>{karts}</fieldset>
      <div class="inclui">
        <div><h3>What URACE Provides</h3>{_lista(a['fornece'])}</div>
        <div><h3>What YOU Need to Bring</h3>{_lista(a['trazer'])}</div>
      </div>
    </div>
    <div class="agenda" data-api="/ops/api/vitrine/agenda" data-carrinho="/cart/" data-servicos="/ops/api/vitrine/servicos">
      <h3>2 · Pick a day</h3>
      <div class="agenda-mes" hidden>
        <button type="button" class="agenda-nav" data-ir="-1" aria-label="Previous month">‹</button>
        <strong class="agenda-titulo" aria-live="polite"></strong>
        <button type="button" class="agenda-nav" data-ir="1" aria-label="Next month">›</button>
      </div>
      <div class="agenda-grade" role="group" aria-label="Available days"></div>
      <div class="agenda-turnos" role="group" aria-label="Morning or afternoon" hidden></div>
      <p class="agenda-aviso" role="status">Loading the open days…</p>
      <!-- #253: o kart (ou o site inteiro) sem serviço no painel: um aviso honesto com o contato, no lugar de um botão morto -->
      <p class="agenda-indisponivel" role="status" hidden><span class="agenda-indisponivel-txt"></span>
        <a href="{e(C.SITE['whatsapp'])}" rel="noopener">WhatsApp {e(C.SITE['telefone'])}</a>
        <a href="mailto:{e(C.SITE['emails'][0])}">{e(C.SITE['emails'][0])}</a></p>
      {caixa_lf}
      <p class="agenda-aviso-kart" role="note"{"" if marcado and C.kart_da_chave(marcado).get("proprio") else " hidden"}>{e(aviso_proprio)}</p>
      <div class="agenda-total"{sem_venda}><span class="agenda-resumo">{e(resumo)} · per driver</span><strong class="agenda-preco">{usd(preco_marcado) if preco_marcado is not None else ''}</strong></div>
      <!-- #262 (dono, 15/10): "um caminho somente levando para o carrinho". Um botão só: ele diz o que
           falta escolher e, com tudo escolhido, põe a sessão no carrinho e leva para lá. -->
      <button type="button" class="btn btn-cheio agenda-carrinho" aria-disabled="true" disabled{sem_venda}>Pick a day to continue</button>
      <p class="carrinho-ok" role="status" aria-live="polite"></p>
      <noscript><p class="agenda-indisponivel"><span>Booking online needs JavaScript. Turn it on, or talk to us and
        we book your session for you:</span> <a href="{e(C.SITE['whatsapp'])}" rel="noopener">WhatsApp {e(C.SITE['telefone'])}</a>
        <a href="mailto:{e(C.SITE['emails'][0])}">{e(C.SITE['emails'][0])}</a></p></noscript>
      <p class="agenda-nota">{e(NOTA_RESERVA)}</p>
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
    <p>{e(a['porque_fecho'])}</p>
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
    <h2 id="h-como">How It Works</h2>
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
    <p class="fecho-sub">{e(a['fecho_sub'])}</p>
    <div class="hero-acoes centro"><a class="btn btn-branco" href="#reservar">Book my experience</a>
      <a class="btn btn-linha-branca" href="{e(C.SITE['whatsapp'])}" rel="noopener">Need more details before booking? Let’s chat.</a></div>
  </div>
</section>"""
    return layout(host=host, caminho=a["caminho"], titulo=a["titulo"], descricao=a["descricao"], corpo=corpo,
                  schemas=(_negocio(host), oferta, perguntas, trilha), scripts=("agenda.js",), foto=a["foto"])


def nao_achou(host):
    """#252: a página do 404 fica fora do Google (`indexar=False`) e sempre com saída: o que a
    pessoa veio buscar está em uma destas quatro portas, não só na home."""
    corpo = """
<section class="faixa clara"><div class="largura estreita centro">
  <h1>Page not found</h1>
  <p>This address doesn't exist. Here is where to go next:</p>
  <div class="hero-acoes centro"><a class="btn" href="/services/arrive-and-drive/">Book a session</a><a class="btn btn-linha" href="/store/">Store</a><a class="btn btn-linha" href="/services/">Our services</a><a class="btn btn-linha" href="/contact/">Contact us</a></div>
  <p class="small muted">Looking for something you saw before? Call or WhatsApp +1 (407) 250 2291, or <a href="/contact/">send us a message</a>.</p>
</div></section>"""
    return layout(host=host, caminho="/404", titulo="Page not found | URACE",
                  descricao="This address doesn't exist on the URACE site. Find your way to booking a kart session, the store, our services or the team.",
                  corpo=corpo, indexar=False)

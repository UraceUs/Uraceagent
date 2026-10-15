"""As páginas do site novo além da home e do Arrive and Drive (#164): serviços, Academy, Pro Team,
For Beginners, Career, About, Contact, Accessibility, blog e loja. Todas usam o `layout()` de
`paginas.py` (cabeçalho, rodapé, metadados, JSON-LD) e o mesmo CSS.

O conteúdo mora em `conteudo_servicos.py`, `conteudo_paginas.py` e em `dados/*.json` (loja e blog,
copiados do urace.us). Aqui só se desenha.
"""
import json
import os
import re
from functools import lru_cache
from html import escape as e
from urllib.parse import quote, urlencode

from command_center.vitrine import conteudo as C
from command_center.vitrine import conteudo_paginas as P
from command_center.vitrine import conteudo_servicos as S
from command_center.vitrine import idioma
from command_center.vitrine.paginas import PORTAL, _lista, _negocio, estatico, layout, usd

DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")


@lru_cache(maxsize=None)
def dados(nome):
    with open(os.path.join(DADOS, nome), encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ pedaços
def _ps(textos, classe=""):
    cl = f' class="{classe}"' if classe else ""
    return "".join(f"<p{cl}>{e(t)}</p>" for t in textos)


def _faq(itens, ident="faq"):
    """Perguntas em <details>: título e parágrafos (ou lista, quando o item é uma lista de frases curtas)."""
    out = []
    for titulo, corpo in itens:
        if isinstance(corpo, str):
            corpo = (corpo,)
        if all(len(x) < 140 for x in corpo) and len(corpo) > 2:
            miolo = _lista(corpo, "lista")
        else:
            miolo = _ps(corpo)
        out.append(f"<details><summary>{e(titulo)}</summary><div class=\"faq-corpo\">{miolo}</div></details>")
    return f'<div class="faq" id="{ident}">' + "".join(out) + "</div>"


def _faq_ld(itens):
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": t, "acceptedAnswer": {"@type": "Answer", "text": " ".join((c,) if isinstance(c, str) else c)}}
        for t, c in itens]}


def _trilha(host, *passos):
    itens = [{"@type": "ListItem", "position": 1, "name": "Home", "item": f"https://{host}/"}]
    for i, (nome, caminho) in enumerate(passos, 2):
        itens.append({"@type": "ListItem", "position": i, "name": nome, "item": f"https://{host}{caminho}"})
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": itens}


def _passos(titulo, passos, intro=None):
    return f"""<section class="faixa clara" aria-labelledby="h-passos"><div class="largura">
  <h2 id="h-passos">{e(titulo)}</h2>{f'<p>{e(intro)}</p>' if intro else ''}
  <ol class="passos">{"".join(f"<li>{e(p)}</li>" for p in passos)}</ol>
</div></section>"""


def _depoimentos(itens, titulo="What Our Clients Say", sub=None):
    """Depoimentos: (nome, texto) ou (nome, cargo, texto)."""
    if not itens:
        return ""
    def um(d):
        n, *c, t = d
        quem = e(n) + (f" · {e(c[0])}" if c and c[0] else "")
        return f'<blockquote><p>{e(t)}</p><footer>{quem}</footer></blockquote>'
    return f"""<section class="faixa escura" aria-labelledby="h-depo"><div class="largura">
  <h2 id="h-depo">{e(titulo)}</h2>{f'<p class="lede">{e(sub)}</p>' if sub else ''}
  <div class="depoimentos">{"".join(um(d) for d in itens)}</div>
</div></section>"""


def _local():
    end = C.SITE["endereco"]
    return f"""<section class="faixa clara" aria-labelledby="h-local"><div class="largura duas">
  <div><h2 id="h-local">Location</h2><address>{e(end['rua'])}, {e(end['cidade'])}, Florida {e(end['cep'])} — {e(end['onde'])}.</address>
    <p><a href="tel:{e(C.SITE['telefone_e164'])}">{e(C.SITE['telefone'])}</a> · <a href="mailto:{e(C.SITE['emails'][0])}">{e(C.SITE['emails'][0])}</a></p>
    <p class="muted">{e(C.SITE['horario'])}</p></div>
  <div><h2>Opening hours</h2><p>{e(S.HORARIO[0])}</p></div>
</div></section>"""


def _fecho(titulo, sub, cta, cor="vermelha"):
    rot, href = cta
    return f"""<section class="faixa {cor}" aria-labelledby="h-fecho"><div class="largura centro">
  <h2 id="h-fecho">{e(titulo)}</h2>{f'<p class="fecho-sub">{e(sub)}</p>' if sub else ''}
  <div class="hero-acoes centro"><a class="btn {'btn-branco' if cor == 'vermelha' else ''}" href="{e(href)}">{e(rot)}</a>
    <a class="btn btn-linha-branca" href="{e(C.SITE['whatsapp'])}" rel="noopener">Need more details before booking? Let’s chat.</a></div>
</div></section>"""


def _hero_foto(nome):
    """A foto do hero como <img> (a política do site não deixa estilo inline)."""
    return f'<img class="hero-foto" src="{estatico("img/" + nome)}" alt="" width="1600" height="900" fetchpriority="high">' if nome else ""


def _hero(d, classe="hero-servico"):
    rot, href = d["cta"]
    foto = _hero_foto(d.get("foto"))
    return f"""<section class="hero {classe}">{foto}
  <div class="hero-in">
    {f'<p class="eyebrow">{e(d["eyebrow"])}</p>' if d.get("eyebrow") else ''}
    <h1>{e(d['h1'])}</h1>
    {f'<p class="hero-sub">{e(d["sub"])}</p>' if d.get("sub") else ''}
    <div class="hero-acoes"><a class="btn" href="{e(href)}">{e(rot)}</a></div>
  </div>
</section>"""


def _colunas(titulo, itens, ident):
    return f"""<section class="faixa clara" aria-labelledby="{ident}"><div class="largura">
  <h2 id="{ident}">{e(titulo)}</h2>
  <div class="cartoes">{"".join(f"<article class='cartao'><h3>{e(t)}</h3><p>{e(p)}</p></article>" for t, p in itens)}</div>
</div></section>"""


# ------------------------------------------------------------------ serviços
def servico(host, d):
    partes = [_hero(d)]
    if d.get("intro"):
        partes.append(f"""<section class="faixa clara" aria-labelledby="h-intro"><div class="largura estreita">
  <h2 id="h-intro">{e(d['intro_titulo'])}</h2>{_ps(d['intro'])}</div></section>""")
    if d.get("beneficios"):
        partes.append(f"""<section class="faixa clara" aria-labelledby="h-benef"><div class="largura">
  <h2 id="h-benef">{e(d['beneficios_titulo'])}</h2><p class="muted">{e(d['beneficios_intro'])}</p>
  <div class="cartoes">{"".join(f"<article class='cartao'><h3>{e(t)}</h3><p>{e(p)}</p></article>" for t, p in d['beneficios'])}</div>
</div></section>""")
    if d.get("fornece") or d.get("espera"):
        partes.append(f"""<section class="faixa escura" aria-labelledby="h-inclui"><div class="largura">
  <h2 id="h-inclui">{e(d.get('fornece_titulo') or 'What to expect')}</h2>{f"<p>{e(d['fornece_intro'])}</p>" if d.get('fornece_intro') else ''}
  <div class="inclui">
    {f"<div><h3>What to expect</h3>{_lista(d['espera'])}</div>" if d.get('espera') else ''}
    {f"<div><h3>{e(d.get('fornece_rotulo') or 'What URACE Provides')}</h3>{_lista(d['fornece'])}</div>" if d.get('fornece') else ''}
    {f"<div><h3>What YOU Need to Bring</h3>{_lista(d['trazer'])}</div>" if d.get('trazer') else ''}
  </div>
</div></section>""")
    if d.get("formatos"):
        acc = []
        for t, intro, itens in d["formatos"]:
            if intro or itens:
                acc.append(f"<details><summary>{e(t)}</summary><div class='faq-corpo'>{f'<p>{e(intro)}</p>' if intro else ''}{_lista(itens) if itens else ''}</div></details>")
            else:                       # o site atual mostra só o título (sem texto embaixo)
                acc.append(f"<p class='formato'>{e(t)}</p>")
        partes.append(f"""<section class="faixa clara" aria-labelledby="h-formatos"><div class="largura duas">
  <div><h2 id="h-formatos">{e(d['formatos_titulo'])}</h2><p>{e(d['formatos_intro'])}</p></div>
  <div class="faq">{"".join(acc)}</div>
</div></section>""")
    if d.get("porque"):
        partes.append(f"""<section class="faixa vermelha" aria-labelledby="h-porque"><div class="largura">
  <p class="eyebrow">Why URACE</p><h2 id="h-porque">{e(d['porque_titulo'])}</h2>
  {f"<p>{e(d['porque_intro'])}</p>" if d.get('porque_intro') else ''}{_lista(d['porque'], 'checks claras')}
  {f"<p>{e(d['porque_fecho'])}</p>" if d.get('porque_fecho') else ''}
</div></section>""")
    if d.get("dias"):
        cards = "".join(f"""<article class="dia"><img src="{estatico('img/' + f)}" alt="" width="640" height="420" loading="lazy"><h3>{e(t)}</h3><p>{e(p)}</p></article>"""
                        for t, p, f in d["dias"])
        partes.append(f"""<section class="faixa clara" aria-labelledby="h-dias"><div class="largura">
  <h2 id="h-dias">{e(d['dias_titulo'])}</h2>{f"<p>{e(d['dias_intro'])}</p>" if d.get('dias_intro') else ''}<div class="dias">{cards}</div></div></section>""")
    if d.get("para_quem"):
        partes.append(f"""<section class="faixa clara" aria-labelledby="h-quem"><div class="largura duas">
  <div><h2 id="h-quem">{e(d.get('para_quem_titulo') or 'Who is this for?')}</h2>{f"<p>{e(d['para_quem_intro'])}</p>" if d.get('para_quem_intro') else ''}</div>
  <div>{_lista(d['para_quem'])}{f"<p>{e(d['para_quem_fecho'])}</p>" if d.get('para_quem_fecho') else ''}</div>
</div></section>""")
    if d.get("curriculo"):
        partes.append(f"""<section class="faixa escura" aria-labelledby="h-curr"><div class="largura duas">
  <div><h2 id="h-curr">Curriculum Highlights</h2>
    <dl class="curriculo">{"".join(f"<div><dt>{e(t)}</dt><dd>{e(p)}</dd></div>" for t, p in d['curriculo'])}</dl></div>
  <div><h2>Program Objectives</h2><ol class="passos">{"".join(f"<li>{e(o)}</li>" for o in d['objetivos'])}</ol></div>
</div></section>""")
    if d.get("logistica"):
        partes.append(f"""<section class="faixa clara" aria-labelledby="h-log"><div class="largura duas">
  <div><h2 id="h-log">{e(d['logistica_titulo'])}</h2>{_lista(d['logistica'])}</div>
  <div><h2>{e(d['extras_titulo'])}</h2>{_lista(d['extras'], 'lista')}</div>
</div></section>""")
    if d.get("passos"):
        partes.append(_passos(d["passos_titulo"], d["passos"], d.get("passos_intro")))
    if d.get("investimento"):          # o preço por piloto é o do Arrive and Drive (KARTS), não texto fixo
        partes.append(f"""<section class="faixa vermelha" aria-labelledby="h-inv"><div class="largura centro">
  <h2 id="h-inv">Investment</h2><p class="preco-grande">{e(d['investimento'].format(preco=usd(C.preco_minimo())))}</p></div></section>""")
    partes.append(f"""<section class="faixa clara" aria-labelledby="h-faq"><div class="largura estreita">
  <h2 id="h-faq">Frequently Asked Questions</h2>{_faq(d['faq'])}</div></section>""")
    partes.append(_local())
    partes.append(_depoimentos(d.get("depoimentos")))
    partes.append(_fecho(d["fecho"], d.get("fecho_sub"), d["fecho_cta"]))
    oferta = {"@context": "https://schema.org", "@type": "Service", "name": d["h1"], "serviceType": "Kart racing program",
              "description": d["descricao"], "provider": {"@id": f"https://{host}/#business"}, "areaServed": "Orlando, FL",
              "url": f"https://{host}{d['caminho']}"}
    return layout(host=host, caminho=d["caminho"], titulo=d["titulo"], descricao=d["descricao"], corpo="".join(partes),
                  schemas=(_negocio(host), oferta, _faq_ld(d["faq"]), _trilha(host, ("Services", "/services/"), (d["h1"], d["caminho"]))),
                  foto=d.get("foto"))


def hub(host):
    d = S.HUB
    # preço só onde o sistema tem o valor: "kart" é o menor preço do Arrive and Drive (KARTS)
    def preco(pr):
        return f"<em>Starting at {usd(C.preco_minimo())}</em>" if pr == "kart" else ""
    cards = "".join(f"""<a class="servico-card" href="{e(h)}"><img src="{estatico('img/' + f)}" alt="" width="640" height="400" loading="lazy">
  <span class="servico-txt"><strong>{e(t)}</strong><span>{e(p)}</span>{preco(pr)}</span></a>""" for t, p, pr, h, f in d["cartoes"])
    corpo = f"""<section class="hero hero-servico hero-hub"><div class="hero-in">
  <p class="eyebrow">{e(d['eyebrow'])}</p><h1>{e(d['h1'])}</h1><p class="hero-sub">{e(d['sub'])}</p>
  <div class="hero-acoes"><a class="btn" href="{PORTAL}/reserve">Book online</a><a class="btn btn-linha" href="/contact/">Talk to us</a></div>
</div></section>
<section class="faixa clara" aria-labelledby="h-lista"><div class="largura">
  <h2 id="h-lista">Every URACE program</h2><div class="servicos-grade">{cards}</div>
</div></section>
<section class="faixa escura" aria-labelledby="h-sim" id="sim2grid"><div class="largura duas">
  <div><p class="eyebrow">{e(d['sim_abertura'])}</p><h2 id="h-sim">{e(d['sim_titulo'])}</h2>{_ps(d['sim'])}{_faq(d['sim_faq'], 'faq-sim')}</div>
  <div class="fotos-duas">{"".join(f'<img src="{estatico("img/" + f)}" alt="URACE Sim 2 Grid" width="640" height="420" loading="lazy">' for f in d['sim_fotos'])}</div>
</div></section>
{_fecho(d['fecho'], d['fecho_sub'], ('Tell us about the driver', '/contact/'))}"""
    lista = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": t, "url": f"https://{host}{h}"} for i, (t, _, _, h, _) in enumerate(d["cartoes"], 1)]}
    return layout(host=host, caminho=d["caminho"], titulo=d["titulo"], descricao=d["descricao"], corpo=corpo,
                  schemas=(_negocio(host), lista, _trilha(host, ("Services", "/services/"))), foto="arrive-and-drive-hero.webp")


# ------------------------------------------------------------------ institucionais
def _planos(planos, assunto="academy"):
    """Os planos (Academy, Pro Team). Mensalidade ainda não se vende sozinha pelo site (invoice
    recorrente do QuickBooks): o botão abre o contato com o plano já escrito."""
    cards = []
    for nome, sub, texto, preco, por, *resto in planos:
        href = resto[0] if resto else f"/contact/?assunto={assunto}&produto={quote(nome)}"
        valor = f'<p class="plano-preco"><strong>{e(preco)}</strong><span>{e(por)}</span></p>' if preco else ""
        cards.append(f"""<article class="plano"><h3>{e(nome)}</h3><p class="plano-sub">{e(sub)}</p><p>{e(texto)}</p>
  {valor}<a class="btn btn-sm" href="{e(href)}">Choose</a></article>""")
    return f'<div class="planos">{"".join(cards)}</div>'


def _planos_do_painel(planos):
    """#169: os planos cadastrados em Site › Serviços (tipo plano), com o botão que vende. Boost é o
    de um mês com "boost" no nome; os outros são o compromisso (1, 3, 6 meses…)."""
    def card(p):
        meses = p["months"]
        sub = f"{p['sessions_month']} sessions a month" if p.get("sessions_month") else "Monthly plan"
        total = f" Total of {usd(p['total'])} over {meses} months." if meses > 1 else ""
        return f"""<article class="plano"><h3>{e(p['name'])}</h3><p class="plano-sub">{e(sub)} · {meses} month{'s' if meses > 1 else ''}</p>
  <p>{e(p['description'] or '')}{e(total)}</p>
  <p class="plano-preco"><strong>{usd(p['price'])}</strong><span>per month</span></p><a class="btn btn-sm" href="{PORTAL}/reserve?plan={p['id']}">Choose</a></article>"""
    boost = [p for p in planos if p["months"] == 1 and "boost" in p["name"].lower()]
    compromisso = [p for p in planos if p not in boost]
    html = f'<div class="planos">{"".join(card(p) for p in compromisso)}</div>' if compromisso else ""
    if boost:
        html += f'<h3 class="mt">URACE Boost</h3><div class="planos">{"".join(card(p) for p in boost)}</div>'
    return html


def academy(host, planos=None):
    d = P.ACADEMY
    etapas = "".join(f"""<article class="etapa-card"><img src="{estatico('img/' + f)}" alt="" width="64" height="64" loading="lazy"><h3>{e(t)}</h3><p>{e(p)}</p></article>""" for t, p, f in d["etapas"])
    corpo = f"""{_hero(d)}
<section class="faixa clara" aria-labelledby="h-mais"><div class="largura duas">
  <div><h2 id="h-mais">{e(d['mais_titulo'])}</h2>{_ps(d['mais'])}</div>
  <img src="{estatico('img/' + d['foto'])}" alt="URACE Academy coaching" width="800" height="600" loading="lazy" class="foto-redonda">
</div></section>
<section class="faixa escura" aria-labelledby="h-planos"><div class="largura">
  <h2 id="h-planos">{e(d['planos_titulo'])}</h2><p class="muted">{e(d['planos_sub'])}</p>{_planos_do_painel(planos) if planos else _planos(d['planos']) + '<h3 class="mt">URACE Boost</h3>' + _planos((d['boost'],))}
</div></section>
<section class="faixa clara" aria-labelledby="h-quem"><div class="largura duas">
  <div><h2 id="h-quem">{e(d['para_quem_titulo'])}</h2>{_lista(d['para_quem'])}</div>
  <div><h2>{e(d['inclui_titulo'])}</h2>{_lista(d['inclui'])}</div>
</div></section>
<section class="faixa escura" aria-labelledby="h-curr"><div class="largura duas">
  <div><h2 id="h-curr">Curriculum Highlights</h2><dl class="curriculo">{"".join(f"<div><dt>{e(t)}</dt><dd>{e(p)}</dd></div>" for t, p in d['curriculo'])}</dl></div>
  <div><h2>Program Objectives</h2><ol class="passos">{"".join(f"<li>{e(o)}</li>" for o in d['objetivos'])}</ol></div>
</div></section>
<section class="faixa clara" aria-labelledby="h-carreira"><div class="largura estreita">
  <h2 id="h-carreira">{e(d['carreira_titulo'])}</h2><p>{e(d['carreira_intro'])}</p>{_lista(d['carreira'])}
  <p class="muted">{e(d['carreira_extras_intro'])}</p>{_lista(d['carreira_extras'], 'lista')}
</div></section>
<section class="faixa vermelha" aria-labelledby="h-caminho"><div class="largura">
  <h2 id="h-caminho">{e(d['caminho_titulo'])}</h2>{_ps(d['caminho_texto'])}
  <div class="etapas-grade">{etapas}</div>
</div></section>
<section class="faixa clara" aria-labelledby="h-faq"><div class="largura estreita"><h2 id="h-faq">Good to know</h2>{_faq(d['faq'])}</div></section>
{_fecho(d['fecho'], d['fecho_sub'], d['fecho_cta'], 'escura')}"""
    oferta = {"@context": "https://schema.org", "@type": "Service", "name": "URACE Academy", "serviceType": "Monthly kart driver training",
              "description": d["descricao"], "provider": {"@id": f"https://{host}/#business"}, "areaServed": "Orlando, FL",
              "offers": [{"@type": "Offer", "name": f"Academy — {n}", "price": pr.replace("$", "").replace(",", ""), "priceCurrency": "USD",
                          "url": f"https://{host}{d['caminho']}"} for n, _, _, pr, _ in d["planos"]]}
    return layout(host=host, caminho=d["caminho"], titulo=d["titulo"], descricao=d["descricao"], corpo=corpo,
                  schemas=(_negocio(host), oferta, _faq_ld(d["faq"]), _trilha(host, ("Academy", d["caminho"]))), foto=d["foto"])


def _preco_plano(planos, qual):
    """O preço por mês do plano do painel: "boost" (o de um mês com boost no nome) ou "academy" (o
    mensal de um mês, ou o de menos meses). Sem plano cadastrado, sem preço."""
    boost = [p for p in planos or () if p["months"] == 1 and "boost" in p["name"].lower()]
    if qual == "boost":
        return usd(boost[0]["price"]) if boost else ""
    outros = sorted((p for p in planos or () if p not in boost), key=lambda p: p["months"])
    return usd(outros[0]["price"]) if outros else ""


def pro_team(host, planos=None):
    d = P.PRO_TEAM
    opcoes = [(n, s, t, _preco_plano(planos, pr) if pr in ("academy", "boost") else pr, por, h)
              for n, s, t, pr, por, h in d["opcoes"]]
    suporte = "".join(f"<article class='cartao'><h3>{e(t)}</h3>{f'<p>{e(p)}</p>' if p else ''}</article>" for t, p in d['suporte'])
    corpo = f"""{_hero(d)}
<section class="faixa clara" aria-labelledby="h-metodo"><div class="largura estreita"><h2 id="h-metodo">{e(d['suporte_titulo'])}</h2><p>{e(d['metodo'])}</p>
  <div class="cartoes">{suporte}</div></div></section>
<section class="faixa clara" aria-labelledby="h-mais"><div class="largura estreita"><h2 id="h-mais">{e(d['mais_titulo'])}</h2>{_ps(d['mais'])}</div></section>
<section class="faixa escura" aria-labelledby="h-opcoes"><div class="largura"><h2 id="h-opcoes">{e(d['opcoes_titulo'])}</h2><p class="muted">{e(d['opcoes_sub'])}</p>{_planos(opcoes, 'team')}</div></section>
<section class="faixa clara" aria-labelledby="h-cal"><div class="largura duas">
  <div><h2 id="h-cal">{e(d['calendario_titulo'])}</h2><p>{e(d['calendario_sub'])}</p></div>
  <dl class="calendario">{"".join(f"<div><dt>{e(q)}</dt><dd>{e(n)}</dd></div>" for q, n in d['calendario'])}</dl>
</div></section>
{_fecho(d['fecho'], d['fecho_sub'], d['fecho_cta'])}"""
    equipe = {"@context": "https://schema.org", "@type": "SportsTeam", "name": "URACE Racing Team", "sport": "Kart racing",
              "memberOf": {"@id": f"https://{host}/#business"}, "url": f"https://{host}{d['caminho']}"}
    return layout(host=host, caminho=d["caminho"], titulo=d["titulo"], descricao=d["descricao"], corpo=corpo,
                  schemas=(_negocio(host), equipe, _trilha(host, ("Racing Team", d["caminho"]))), foto=d["foto"])


def beginners(host):
    d = P.BEGINNERS
    def preco(pr):            # "kart": o menor preço do Arrive and Drive (KARTS); os outros não têm preço no sistema
        return f'<p class="plano-preco"><span>Starting at</span><strong>{usd(C.preco_minimo())}</strong></p>' if pr == "kart" else ""
    cards = "".join(f"""<article class="plano"><h3>{e(n)}</h3><p class="plano-sub">{e(s)}</p><p>{e(t)}</p>{preco(pr)}<a class="btn btn-sm" href="{e(h)}">{e(b)}</a></article>"""
                    for n, s, t, pr, h, b in d["proximo"])
    corpo = f"""{_hero(d)}
<section class="faixa clara" aria-labelledby="h-primeira"><div class="largura estreita"><h2 id="h-primeira">{e(d['primeira_titulo'])}</h2>{_ps(d['primeira'])}</div></section>
<section class="faixa escura" aria-labelledby="h-contato"><div class="largura estreita"><h2 id="h-contato">{e(d['contato_titulo'])}</h2>{_ps(d['contato'])}
  <p><a class="btn" href="/services/arrive-and-drive/">{e(d['contato_cta'])}</a></p></div></section>
<section class="faixa clara" aria-labelledby="h-proximo"><div class="largura"><h2 id="h-proximo">{e(d['proximo_titulo'])}</h2><div class="planos">{cards}</div></div></section>
<section class="faixa clara" aria-labelledby="h-faq"><div class="largura estreita"><h2 id="h-faq">Questions beginners ask</h2>{_faq(d['faq'])}</div></section>
{_fecho(d['fecho'], d['fecho_sub'], d['fecho_cta'])}"""
    return layout(host=host, caminho=d["caminho"], titulo=d["titulo"], descricao=d["descricao"], corpo=corpo,
                  schemas=(_negocio(host), _faq_ld(d["faq"]), _trilha(host, ("For Beginners", d["caminho"]))), foto=d["foto"])


def career(host):
    d = P.CAREER
    degraus = "".join(f"""<li><a href="{e(h)}"><strong>{e(t)}</strong><span>{e(p)}</span></a></li>""" for t, p, h in d["degraus"])
    fotos = "".join(f'<figure><img src="{estatico("img/" + f)}" alt="{e(a)}" width="480" height="600" loading="lazy"><figcaption>{e(a)}</figcaption></figure>' for f, a in d["fotos"])
    corpo = f"""{_hero(d)}
<section class="faixa clara" aria-labelledby="h-degraus"><div class="largura"><h2 id="h-degraus">{e(d['degraus_titulo'])}</h2><p>{e(d['degraus_intro'])}</p><ol class="degraus">{degraus}</ol>
  {_ps(d['aviso'], 'muted small')}</div></section>
<section class="faixa escura" aria-labelledby="h-pessoa"><div class="largura duas"><div><h2 id="h-pessoa">{e(d['pessoa_titulo'])}</h2>{_ps(d['pessoa'])}</div><div class="campeoes">{fotos}</div></div></section>
<section class="faixa clara" aria-labelledby="h-prof"><div class="largura estreita"><h2 id="h-prof">{e(d['profissional_titulo'])}</h2>{_ps(d['profissional'])}{_lista(f"{t}: {p}" for t, p in d['profissional_itens'])}</div></section>
<section class="faixa escura" aria-labelledby="h-eventos"><div class="largura estreita"><h2 id="h-eventos">{e(d['eventos_titulo'])}</h2>{_ps(d['eventos'])}{_faq(d['eventos_faq'], 'faq-eventos')}
  <p class="hero-acoes"><a class="btn" href="/services/group-events/">Group Events &amp; Social Gatherings</a> <a class="btn" href="/services/corporate-events/">Corporate Events</a> <a class="btn" href="/services/birthday-party/">Birthday Party</a></p></div></section>
<section class="faixa clara" aria-labelledby="h-faq"><div class="largura estreita"><h2 id="h-faq">{e(d['perguntas_titulo'])}</h2><p class="muted">{e(d['perguntas_sub'])}</p>{_faq(d['faq'])}</div></section>
{_fecho(d['fecho'], d['fecho_sub'], d['fecho_cta'])}"""
    return layout(host=host, caminho=d["caminho"], titulo=d["titulo"], descricao=d["descricao"], corpo=corpo,
                  schemas=(_negocio(host), _faq_ld(d["faq"]), _trilha(host, ("Career", d["caminho"]))), foto=d["foto"])


def about(host):
    d = P.ABOUT
    corpo = f"""<section class="hero hero-servico">{_hero_foto(d['foto'])}<div class="hero-in">
  <p class="eyebrow">{e(d['eyebrow'])}</p><h1>{e(d['h1'])}</h1></div></section>
<section class="faixa clara" aria-labelledby="h-hist"><div class="largura estreita"><h2 id="h-hist">{e(d['historia_titulo'])}</h2>{_ps(d['historia'])}{_lista(d['historia_itens'], 'lista')}<p>{e(d['historia_fecho'])}</p></div></section>
<section class="faixa escura" aria-labelledby="h-met"><div class="largura duas"><div><h2 id="h-met">{e(d['metodo_titulo'])}</h2><p>{e(d['metodo_intro'])}</p>{_lista(d['metodo'])}<p>{e(d['metodo_fecho'])}</p></div>
  <div><h2>{e(d['diferente_titulo'])}</h2>{_ps(d['diferente'])}{_lista(d['diferente_itens'], 'lista')}<p>{e(d['diferente_fecho'])}</p></div></div></section>
<section class="faixa clara" aria-labelledby="h-equipe"><div class="largura duas"><div><h2 id="h-equipe">{e(d['equipe_titulo'])}</h2>{_ps(d['equipe'])}{_lista(d['equipe_itens'], 'lista')}{_ps(d['equipe_fecho'])}</div>
  <div><h2>Vision</h2><p>{e(d['visao'])}</p><h2>Mission</h2>{_ps(d['missao'])}</div></div></section>
<section class="faixa vermelha" aria-labelledby="h-sup"><div class="largura duas"><div><h2 id="h-sup">{e(d['suporte_titulo'])}</h2>{_ps(d['suporte'])}</div>
  <div><h2>{e(d['seguranca_titulo'])}</h2><p>{e(d['seguranca_intro'])}</p>{_lista(d['seguranca'], 'checks claras')}<p>{e(d['seguranca_fecho'])}</p></div></div></section>
{_depoimentos(C.DEPOIMENTOS, d['depoimentos_titulo'], d['depoimentos_sub'])}
{_fecho(d['fecho'], d['fecho_sub'], d['fecho_cta'], 'escura')}"""
    return layout(host=host, caminho=d["caminho"], titulo=d["titulo"], descricao=d["descricao"], corpo=corpo,
                  schemas=(_negocio(host), _trilha(host, ("About", d["caminho"]))), foto=d["foto"])


ENVIADO = ('<p class="aviso-ok" role="status">Thank you! We got your message and will reply shortly — usually within '
           'one business day. In a hurry? Chat with us on WhatsApp.</p>')


def contact(host, assunto=None, produto=None, enviado=False):
    d = P.CONTACT
    end = C.SITE["endereco"]
    opcoes = "".join(f'<option value="{e(v)}"{" selected" if v == assunto else ""}>{e(r)}</option>' for v, r in d["assuntos"])
    corpo = f"""<section class="faixa clara" aria-labelledby="h-contato"><div class="largura duas">
  <div><p class="eyebrow">{e(d['eyebrow'])}</p><h1 id="h-contato">{e(d['h1'])}</h1><p class="hero-sub-escura">{e(d['sub'])}</p>{ENVIADO if enviado else ''}
    <form class="form-contato" method="post" action="/ops/api/vitrine/contato" data-contato>
      <label>Your name<input name="nome" required autocomplete="name" maxlength="120"></label>
      <label>Email<input name="email" type="email" required autocomplete="email" maxlength="160"></label>
      <label>Phone <span class="opcional">(optional)</span><input name="telefone" type="tel" autocomplete="tel" maxlength="40"></label>
      <label>What is it about?<select name="assunto">{opcoes}</select></label>
      <label>Message<textarea name="mensagem" required maxlength="2000" rows="5">{e(('About: ' + produto) if produto else '')}</textarea></label>
      <label class="escondido" aria-hidden="true">Leave this empty<input name="site" tabindex="-1" autocomplete="off"></label>
      <p class="small muted">By sending this form, you agree to be contacted by the URACE team about your inquiry.</p>
      <button class="btn" type="submit">Send</button>
      <p class="form-estado" role="status" aria-live="polite"></p>
    </form></div>
  <div class="contato-lado">
    <h2>{e(d['local_titulo'])}</h2>
    <address>{e(end['rua'])}, {e(end['cidade'])}, Florida {e(end['cep'])}<br>{e(end['onde'].capitalize())}.</address>
    <p><a href="tel:{e(C.SITE['telefone_e164'])}">{e(C.SITE['telefone'])}</a><br><a href="mailto:{e(C.SITE['emails'][0])}">{e(C.SITE['emails'][0])}</a></p>
    <p class="muted">{e(C.SITE['horario'])}</p>
    <p><a class="btn btn-sm" href="{e(C.SITE['whatsapp'])}" rel="noopener">Chat on WhatsApp</a></p>
    <p><a href="https://maps.google.com/?q={e(end['rua'].replace(' ', '+'))},+{e(end['cidade'])},+{e(end['estado'])}+{e(end['cep'])}" rel="noopener">Open in Google Maps</a></p>
  </div>
</div></section>"""
    return layout(host=host, caminho=d["caminho"], titulo=d["titulo"], descricao=d["descricao"], corpo=corpo,
                  schemas=(_negocio(host), _trilha(host, ("Contact", d["caminho"]))), scripts=("contato.js",))


def accessibility(host):
    d = P.ACCESSIBILITY
    corpo = f"""<section class="faixa clara"><div class="largura estreita texto">
  <h1>{e(d['h1'])}</h1>{_ps(d['texto'])}
  <h2>{e(d['conformidade_titulo'])}</h2>{_ps(d['conformidade'])}
  <h2>{e(d['feedback_titulo'])}</h2><p>{e(d['feedback'])}</p>
  <ul><li>Phone: <a href="tel:{e(C.SITE['telefone_e164'])}">{e(C.SITE['telefone'])}</a></li><li>E-mail: <a href="mailto:{e(C.SITE['emails'][1])}">{e(C.SITE['emails'][1])}</a></li></ul>
  <h2>{e(d['data_titulo'])}</h2><p>{e(d['data'])}</p>
</div></section>"""
    return layout(host=host, caminho=d["caminho"], titulo=d["titulo"], descricao=d["descricao"], corpo=corpo, schemas=(_negocio(host),))


# ------------------------------------------------------------------ blog
def _post_card(p):
    foto = f'<img src="{estatico("img/" + p["image"])}" alt="" width="640" height="400" loading="lazy">' if p.get("image") else ""
    cats = ", ".join(c["name"] for c in p["categories"])
    return f"""<article class="post-card"><a href="/blog/{e(p['slug'])}/">{foto}<span class="post-txt"><small>{e(cats)} · {e(_data(p['date']))}</small><strong>{e(p['title'])}</strong><span>{e(_corta(p['excerpt'], 180))}</span></span></a></article>"""


def _corta(t, n):
    """Corta no espaço, não no meio da palavra."""
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def _data(iso):
    from datetime import date
    return date.fromisoformat(iso).strftime("%B %-d, %Y")


BLOG_SUB = "Top tier nationally recognized kart team providing race-wide support, driver training."     # urace.us/blog/


def blog(host, categoria=None):
    d = dados("posts.json")
    posts = d["posts"]
    cat = next((c for c in d["categorias"] if c["slug"] == categoria), None) if categoria else None
    if categoria and not cat:
        return None
    if cat:
        posts = [p for p in posts if any(c["slug"] == cat["slug"] for c in p["categories"])]
    caminho = f"/blog/category/{cat['slug']}/" if cat else "/blog/"
    titulo = f"{cat['name']} - URACE Blog" if cat else "Kart Racing Blog - How to Race Karts | URACE"
    descricao = _desc(cat["description"] if cat and cat["description"] else "How to get into karting, go faster, overtake and become a racing driver.",
                      "Practical guides from the URACE coaching team in Orlando.")
    cats = "".join(f'<a class="chip-link{" on" if cat and c["slug"] == cat["slug"] else ""}" href="/blog/category/{e(c["slug"])}/">{e(c["name"])}</a>'
                   for c in d["categorias"] if c["slug"] != "uncategorized")
    corpo = f"""<section class="faixa clara" aria-labelledby="h-blog"><div class="largura">
  <p class="eyebrow">Blog</p><h1 id="h-blog">{e(cat['name']) if cat else 'Take advantage of our materials'}</h1>
  <p class="hero-sub-escura">{e(descricao if cat else BLOG_SUB)}</p>
  <nav class="chips" aria-label="Categories"><a class="chip-link{'' if cat else ' on'}" href="/blog/">All</a>{cats}</nav>
  <div class="posts-grade">{"".join(_post_card(p) for p in posts)}</div>
</div></section>"""
    lista = {"@context": "https://schema.org", "@type": "Blog", "name": "URACE Blog", "url": f"https://{host}/blog/",
             "blogPost": [{"@type": "BlogPosting", "headline": p["title"], "datePublished": p["date"], "url": f"https://{host}/blog/{p['slug']}/"} for p in posts]}
    return layout(host=host, caminho=caminho, titulo=titulo, descricao=descricao, corpo=corpo,
                  schemas=(_negocio(host), lista, _trilha(host, ("Blog", "/blog/"))), foto=posts[0]["image"] if posts and posts[0].get("image") else None)


def post(host, slug):
    d = dados("posts.json")
    p = next((x for x in d["posts"] if x["slug"] == slug), None)
    if not p:
        return None
    html = _niveis(p["html"].replace("{IMG:", "/_s/img/").replace("}", ""), "h2")      # as imagens já são as nossas (WebP)
    foto = f'<img class="post-capa" src="{estatico("img/" + p["image"])}" alt="" width="1200" height="675">' if p.get("image") else ""
    outros = [x for x in d["posts"] if x["slug"] != slug][:3]
    corpo = f"""<article class="faixa clara"><div class="largura estreita texto">
  <p class="eyebrow">{e(', '.join(c['name'] for c in p['categories']))} · {e(_data(p['date']))}</p>
  <h1>{e(p['title'])}</h1>{foto}
  <div class="post-corpo">{html}</div>
  <p class="mt"><a class="btn" href="{PORTAL}/reserve">Book a session</a> <a class="btn btn-linha-escura" href="/blog/">All articles</a></p>
</div></article>
<section class="faixa escura" aria-labelledby="h-mais"><div class="largura"><h2 id="h-mais">Keep reading</h2><div class="posts-grade">{"".join(_post_card(x) for x in outros)}</div></div></section>"""
    artigo = {"@context": "https://schema.org", "@type": "BlogPosting", "headline": p["title"], "description": p["description"],
              "datePublished": p["date"], "author": {"@type": "Organization", "name": "URACE"},
              "publisher": {"@id": f"https://{host}/#business"}, "mainEntityOfPage": f"https://{host}/blog/{p['slug']}/",
              **({"image": f"https://{host}{estatico('img/' + p['image'])}"} if p.get("image") else {})}
    return layout(host=host, caminho=f"/blog/{p['slug']}/", titulo=p.get("seo_title") or f"{p['title']} | URACE", descricao=_desc(p["description"], "From the URACE blog, Orlando."), corpo=corpo,
                  schemas=(_negocio(host), artigo, _trilha(host, ("Blog", "/blog/"), (p["title"], f"/blog/{p['slug']}/"))), foto=p.get("image"))


# ------------------------------------------------------------------ loja
CATEGORIAS_LOJA = (("chassis", "Chassis"), ("competition-karts", "Competition karts"), ("engines", "Engines"), ("parts", "Parts"),
                   ("tires", "Tires"), ("custom-kart-suits", "Custom kart suits"), ("official-urace-products", "Official URACE products"),
                   ("kart-driver-training", "Programs"))


ALIAS_LOJA = {"apparel": "official-urace-products", "suits": "custom-kart-suits", "apparel-gear": "official-urace-products",
              "classes-programs": "kart-driver-training", "karts-parts": "parts"}


def _categoria(p):
    """A categoria do produto que tem página na loja (as do WooCommerce sem página caem na equivalente)."""
    nomes = dict(CATEGORIAS_LOJA)
    for c in p["categories"]:
        slug = ALIAS_LOJA.get(c["slug"], c["slug"])
        if slug in nomes:
            return {"slug": slug, "name": nomes[slug]}
    return {"slug": "parts", "name": nomes["parts"]}


# #252: a descrição de um produto do WooCommerce pode trazer CSS e JavaScript do tema soltos no
# meio do texto (o urace.us põe isso dentro de <style>/<script>; na cópia, as tags ficaram de fora).
# Como texto, isso aparece como lixo na página e estoura a largura no celular: aqui some.
CODIGO = re.compile(r"[\w.#\[\]:*-]+\s*\{[^{}]*:[^{}]*\}|@media\s*\(|@keyframes\b|\bfunction\s*\(|"
                    r"\bdocument\.(querySelector|getElementBy|addEventListener)|\.(addEventListener|innerHTML)\s*[=(]")


def _sem_codigo(html):
    """Tira os pedaços de CSS/JS que vieram como texto, parágrafo por parágrafo."""
    def um(m):
        return "" if CODIGO.search(_texto(m.group(0))) else m.group(0)
    html = re.sub(r"<p\b[^>]*>.*?</p>", um, html, flags=re.S | re.I)
    return re.sub(r"(?m)^(?!<)[^<\n]*$", lambda m: "" if CODIGO.search(m.group(0)) else m.group(0), html)


def _niveis(html, topo):
    """Títulos do texto copiado (h2–h6) viram um nível só, abaixo do título da seção."""
    return re.sub(r"<(/?)h[2-6]>", lambda m: f"<{m.group(1)}{topo}>", _sem_codigo(html))


def _preco(p):
    if p["price"] == 0 and not p["price_min"]:
        return "Ask for price"
    if p["price_min"] and p["price_max"] and p["price_max"] != p["price_min"]:
        return f"{usd(p['price_min'])} – {usd(p['price_max'])}"
    return usd(p["price"]) if p["price"] else "Ask for price"


def _produto_card(p):
    img = p["images"][0] if p["images"] else None
    foto = f'<img src="{estatico("img/" + img["src"])}" alt="{e(img["alt"])}" width="400" height="400" loading="lazy">' if img else '<span class="sem-foto" aria-hidden="true">URACE</span>'
    promo = f'<s>{usd(p["regular"])}</s> ' if p["on_sale"] and p["regular"] > p["price"] else ""
    return f"""<article class="produto-card"><a href="/store/p/{e(p['slug'])}/">{foto}<span class="produto-txt"><strong>{e(p['name'])}</strong><em>{promo}{e(_preco(p))}</em>{'' if p['in_stock'] else '<small>Out of stock</small>'}</span></a></article>"""


LAZY = ' loading="lazy"'
LOJA_SUB = "From kart suits to full chassis, shop URACE's official store and get race-ready gear delivered to you."

# #261 (dono, 15/10: *"Busca e filtro na loja… Eu faço — confirma?"* → *"sim"*): a loja do urace.us
# de hoje acha produto por texto (`?s=`), filtra por preço (`min_price`/`max_price`), ordena
# (`?orderby=`) e pagina (`page/N`). A loja do site novo faz o mesmo e faz tudo no servidor: a
# página sai pronta, o navegador não baixa o catálogo nem filtra nada, e sem JavaScript continua
# funcionando (o formulário é um `form method="get"` de verdade).
LOJA_POR_PAGINA = 24

# A ordenação do WooCommerce, com os nomes que o urace.us publica hoje. `popularity` e `rating`
# precisariam de venda e de nota, que a cópia do catálogo não traz: em vez de inventar número,
# o endereço abre na ordem do catálogo (e eles não entram no menu de ordenar).
ORDENS_WOO = {"menu_order": "menu_order", "relevance": "relevance", "price": "price",
              "price-desc": "price-desc", "date": "date", "popularity": "menu_order", "rating": "menu_order"}
ORDENAR = (("menu_order", "Default"), ("price", "Price: low to high"),
           ("price-desc", "Price: high to low"), ("date", "Newest"))


def _faixa(p):
    """O preço do produto como faixa: o variável tem mínimo e máximo, o simples tem um só."""
    lo, hi = p["price_min"] or p["price"], p["price_max"] or p["price"]
    return (lo, hi) if hi >= lo else (hi, lo)


def _numero(v):
    """Um preço que veio do endereço (`min_price=120`), ou None quando não é número."""
    try:
        n = float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    return n if 0 <= n <= 1_000_000 else None


def _pontos(p, termos):
    """Quanto o produto casa com a busca: o nome vale mais que o código, que a categoria, que o
    texto. Toda palavra tem de aparecer em algum lugar — 0 é não achou."""
    onde = ((p["name"].lower(), 8), ((p.get("sku") or "").lower(), 5),
            (" ".join(c["name"] for c in p["categories"]).lower(), 3),
            (_texto(f'{p["short"]} {p["description"]}').lower(), 1))
    total = 0
    for t in termos:
        peso = max((w for texto, w in onde if t in texto), default=0)
        if not peso:
            return 0
        total += peso
    return total


def catalogo(categoria=None, termo="", min_price=None, max_price=None, orderby="menu_order",
             limit=LOJA_POR_PAGINA, offset=0):
    """Os produtos da loja resolvidos no servidor: categoria, busca por texto, faixa de preço e
    ordenação, com `limit`/`offset` e o `total` (o padrão de lista do CLAUDE.md)."""
    produtos = dados("produtos.json")["produtos"]
    if categoria:
        produtos = [p for p in produtos if _categoria(p)["slug"] == categoria]
    termos = [t for t in re.split(r"[\s,]+", (termo or "").lower().strip()) if t][:8]
    if termos:                                          # mais pontos primeiro, empate pela ordem do catálogo
        casados = [(_pontos(p, termos), -i, p) for i, p in enumerate(produtos)]
        produtos = [p for pontos, _, p in sorted((c for c in casados if c[0]), reverse=True)]
    if min_price is not None:
        produtos = [p for p in produtos if _faixa(p)[1] >= min_price]
    if max_price is not None:
        produtos = [p for p in produtos if _faixa(p)[0] <= max_price]
    if orderby == "price":
        produtos = sorted(produtos, key=lambda p: _faixa(p)[0])
    elif orderby == "price-desc":
        produtos = sorted(produtos, key=lambda p: _faixa(p)[1], reverse=True)
    elif orderby == "date":                             # a cópia não traz data; no WooCommerce o id cresce com o tempo
        produtos = sorted(produtos, key=lambda p: p["id"], reverse=True)
    total = len(produtos)
    return {"produtos": produtos[offset:offset + limit], "total": total, "limit": limit, "offset": offset,
            "paginas": max(1, -(-total // limit))}


def filtro_loja(q):
    """O que a pessoa pediu no endereço, com os nomes que o WooCommerce do urace.us publica hoje
    (`s`, `min_price`, `max_price`, `orderby`): assim o endereço de hoje continua abrindo."""
    q = q or {}
    termo = re.sub(r"\s+", " ", (q.get("s") or "").strip())[:80]
    ordem = ORDENS_WOO.get((q.get("orderby") or "").strip().lower())
    if ordem == "relevance" and not termo:
        ordem = None
    return {"termo": termo, "min_price": _numero(q.get("min_price")), "max_price": _numero(q.get("max_price")),
            "orderby": ordem or ("relevance" if termo else "menu_order")}


def _ordem_padrao(f):
    return "relevance" if f["termo"] else "menu_order"


def _filtrando(f):
    """Alguém pediu busca, faixa de preço ou outra ordem? (Aí a página fica fora do Google.)"""
    return (bool(f["termo"]) or f["min_price"] is not None or f["max_price"] is not None
            or f["orderby"] != _ordem_padrao(f))


def _num(v):
    return f"{v:g}" if isinstance(v, float) else v


def _query_loja(f):
    """A busca, o filtro e a ordem como query, para os links de página e de categoria."""
    itens = [(k, _num(v)) for k, v in (("s", f["termo"]), ("min_price", f["min_price"]),
                                       ("max_price", f["max_price"]),
                                       ("orderby", f["orderby"] if f["orderby"] != _ordem_padrao(f) else ""))
             if v not in (None, "")]
    return urlencode(itens)


def _link_loja(caminho, f):
    qs = _query_loja(f)
    return f"{caminho}?{qs}" if qs else caminho


def _loja_busca(base, f):
    """O formulário de busca e filtro: um `form method="get"`, que funciona sem JavaScript."""
    opcoes = ((("relevance", "Best match"),) + ORDENAR) if f["termo"] else ORDENAR
    ordens = "".join(f'<option value="{s}"{" selected" if f["orderby"] == s else ""}>{e(n)}</option>'
                     for s, n in opcoes)
    limpar = f'<a class="chip-link" href="{e(base)}">Clear search and filters</a>' if _filtrando(f) else ""
    return f"""<form class="loja-busca" method="get" action="{e(base)}" role="search">
    <label class="loja-q" for="loja-s">What are you looking for?
      <input id="loja-s" type="search" name="s" value="{e(f['termo'])}" maxlength="80" autocomplete="off"
             placeholder="Product, part number or brand"></label>
    <label for="loja-min">Min price (USD)
      <input id="loja-min" type="number" name="min_price" value="{e(_num(f['min_price']) or '')}" min="0" max="1000000" step="1" inputmode="decimal"></label>
    <label for="loja-max">Max price (USD)
      <input id="loja-max" type="number" name="max_price" value="{e(_num(f['max_price']) or '')}" min="0" max="1000000" step="1" inputmode="decimal"></label>
    <label for="loja-ordem">Sort by<select id="loja-ordem" name="orderby">{ordens}</select></label>
    <button class="btn" type="submit">Search the store</button>
    {limpar}
  </form>"""


def _paginacao(base, f, pagina, paginas):
    """As páginas da loja no caminho (`/store/page/2/`), não num parâmetro."""
    if paginas <= 1:
        return ""
    href = lambda n: _link_loja(base if n == 1 else f"{base}page/{n}/", f)  # noqa: E731
    partes = []
    if pagina > 1:
        partes.append(f'<a class="chip-link" rel="prev" href="{e(href(pagina - 1))}">Previous</a>')
    anterior = 0
    for n in sorted({1, paginas, *range(max(1, pagina - 2), min(paginas, pagina + 2) + 1)}):
        if n > anterior + 1:
            partes.append('<span class="chip-vazio" aria-hidden="true">…</span>')
        atual = ' aria-current="page"' if n == pagina else ""
        partes.append(f'<a class="chip-link{" on" if n == pagina else ""}" href="{e(href(n))}"'
                      f' aria-label="Page {n}"{atual}>{n}</a>')
        anterior = n
    if pagina < paginas:
        partes.append(f'<a class="chip-link" rel="next" href="{e(href(pagina + 1))}">Next</a>')
    return f'<nav class="chips paginacao" aria-label="Store pages">{"".join(partes)}</nav>'


def _conta_loja(c, f):
    """"Showing 1–24 of 70 products": o `total` do servidor, dito na página."""
    if not c["total"]:
        return ""
    faixa = (f"{c['offset'] + 1}–{c['offset'] + len(c['produtos'])} of {c['total']}"
             if c["paginas"] > 1 else f"all {c['total']}")
    if f["termo"]:
        return f'<p class="muted loja-conta">Showing {faixa} {"match" if c["total"] == 1 else "matches"} for “{e(f["termo"])}”.</p>'
    return f'<p class="muted loja-conta">Showing {faixa} {"product" if c["total"] == 1 else "products"}.</p>'


NADA_NA_LOJA = ("Nothing matched that. Try fewer words or a wider price range — or ask the team, and we find "
                "the part for you and send you the link.")


def store(host, categoria=None, q=None, pagina=1):
    """A loja e as categorias, com busca, filtro de preço, ordenação e paginação do servidor (#261).
    `pagina` vem do caminho (`/store/page/2/`); fora da faixa devolve None (a rota manda o 301)."""
    nomes = dict(CATEGORIAS_LOJA)
    if categoria and categoria not in nomes:
        return None
    base = f"/store/{categoria}/" if categoria else "/store/"
    f = filtro_loja(q)
    c = catalogo(categoria, f["termo"], f["min_price"], f["max_price"], f["orderby"],
                 limit=LOJA_POR_PAGINA, offset=(pagina - 1) * LOJA_POR_PAGINA)
    if pagina < 1 or (pagina > 1 and pagina > c["paginas"]):
        return None
    filtrando = _filtrando(f)
    caminho = base if filtrando or pagina == 1 else f"{base}page/{pagina}/"
    nome_cat = nomes[categoria] if categoria else None
    sub = (f"{nome_cat} from the URACE race shop at the Orlando Kart Center, chosen and fitted by racers."
           if nome_cat else LOJA_SUB)
    if f["termo"]:
        titulo = f"Search: {f['termo']} | URACE Store"
        descricao = (f"{c['total']} {'product' if c['total'] == 1 else 'products'} matching “{f['termo']}” in the "
                     "URACE race shop at the Orlando Kart Center: chassis, engines, tires, suits and parts.")
    elif nome_cat:
        titulo = f"{nome_cat} - URACE Store" if pagina == 1 else f"{nome_cat} - Page {pagina} | URACE Store"
        descricao = sub
    else:
        titulo = ("Kart Parts Store - Chassis, Engines & Tires | URACE" if pagina == 1 else
                  f"Kart Parts Store - Page {pagina} | URACE")
        descricao = ("Racing kart parts in Orlando: chassis, engines, tires, apparel and accessories. Everything you "
                     "need to race faster, from the URACE race shop.")
    if pagina > 1 and not f["termo"]:
        descricao = f"{descricao} Page {pagina} of {c['paginas']}."
    chips = "".join(f'<a class="chip-link{" on" if s == categoria else ""}"'
                    f' href="{e(_link_loja(f"/store/{s}/", f))}">{e(n)}</a>' for s, n in CATEGORIAS_LOJA)
    grade = ("".join(_produto_card(p) for p in c["produtos"]) if c["produtos"]
             else f'<p class="loja-vazia">{e(NADA_NA_LOJA)}</p>')
    corpo = f"""<section class="faixa clara" aria-labelledby="h-loja"><div class="largura">
  <p class="eyebrow">Store</p><h1 id="h-loja">{e(nome_cat) if nome_cat else 'Everything you need to race faster'}</h1>
  <p class="hero-sub-escura">{e(sub)}</p>
  {_loja_busca(base, f)}
  <nav class="chips" aria-label="Categories"><a class="chip-link{'' if categoria else ' on'}" href="{e(_link_loja('/store/', f))}">All</a>{chips}</nav>
  {_conta_loja(c, f)}
  <div class="produtos-grade">{grade}</div>
  {_paginacao(base, f, pagina, c["paginas"])}
</div></section>
<section class="faixa escura" aria-labelledby="h-garantia"><div class="largura">
  <h2 id="h-garantia">Backed by racers, built for racers</h2>
  <div class="cartoes">
    <article class="cartao"><h3>Fast shipping</h3><p>Orders processed and shipped within 24 business hours.</p></article>
    <article class="cartao"><h3>Official gear</h3><p>Authentic parts and equipment from the best kart brands.</p></article>
    <article class="cartao"><h3>Expert support</h3><p>Our team knows karting from the inside. We help you choose the right product.</p></article>
    <article class="cartao"><h3>Secure checkout</h3><p>Your data and payment are protected on every purchase.</p></article>
  </div>
</div></section>
{_fecho('Not sure what you need?', 'Our team can help you choose the right parts, suit, or chassis for your level and category.', ('Ask the team', '/contact/?assunto=store'))}"""
    lista = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [
        {"@type": "ListItem", "position": c["offset"] + i, "url": f"https://{host}/store/p/{p['slug']}/", "name": p["name"]}
        for i, p in enumerate(c["produtos"], 1)]}
    return layout(host=host, caminho=caminho, titulo=titulo, descricao=descricao, corpo=corpo,
                  indexar=not filtrando,
                  schemas=(_negocio(host), lista, _trilha(host, ("Store", "/store/"))))


@lru_cache(maxsize=1)
def paginas_da_loja():
    """As páginas 2 em diante da loja e de cada categoria, para o sitemap: sem elas o Google não
    chega nos produtos que ficam depois da primeira página. (Guardado: o catálogo é um arquivo, e
    `_familia` pergunta isto em todo endereço antigo que chega.)"""
    out = []
    for cat in (None, *[s for s, _ in CATEGORIAS_LOJA]):
        base = f"/store/{cat}/" if cat else "/store/"
        out += [f"{base}page/{i}/" for i in range(2, catalogo(cat)["paginas"] + 1)]
    return out


def _form_comprar(p):
    """#174: preço fechado e em estoque → paga na hora no Stripe Checkout (sem JavaScript: POST e 303)."""
    opcoes = ""
    if p["variations"]:
        rows = []
        for v in p["variations"]:
            nome = " / ".join(v["attrs"])
            ok = v.get("in_stock", True) and (v.get("price") or p["price"])
            rows.append(f"<option value=\"{e(nome)}\"{'' if ok else ' disabled'}>{e(nome)}"
                        f"{' — ' + usd(v.get('price') or p['price']) if ok else ' (out of stock)'}</option>")
        rotulo = p["attributes"][0]["name"] if p["attributes"] else "Option"
        opcoes = f'<label>{e(rotulo)}<select name="variacao">{"".join(rows)}</select></label>'
    return f"""<form class="form-pedido form-comprar" method="post" action="/ops/api/vitrine/checkout">
      <input type="hidden" name="produto" value="{e(p['slug'])}">
      {opcoes}
      <label>Quantity<input name="quantidade" type="number" min="1" max="20" value="1" inputmode="numeric"></label>
      <fieldset class="entrega"><legend>Delivery</legend>
        <label class="opcao"><input type="radio" name="entrega" value="retirada" checked> <span>Pick up at the track <span class="opcional">— Orlando Kart Center, free</span></span></label>
        <label class="opcao"><input type="radio" name="entrega" value="envio"> <span>Ship to me <span class="opcional">— we confirm and bill shipping separately</span></span></label>
      </fieldset>
      <label class="escondido" aria-hidden="true">Leave this empty<input name="site" tabindex="-1" autocomplete="off"></label>
      <div class="comprar-acoes">
        <button class="btn" type="submit">Buy now</button>
        <button class="btn btn-linha-escura" type="button" data-por-no-carrinho hidden>Add to cart</button>
      </div>
      <p class="carrinho-ok" role="status" aria-live="polite"></p>
      <p class="small muted">Secure checkout by Stripe: card, Apple Pay or Google Pay. Buying needs your URACE account: you sign in (or create it) first and come right back. The confirmation arrives by email.</p>
    </form>"""


ERRO_CHECKOUT = ('<p class="aviso-erro" role="alert">We couldn’t open the secure checkout just now. Please try again, '
                 'or send us an order request below.</p>')


def product(host, slug, enviado=False, stripe=False, erro_checkout=False):
    d = dados("produtos.json")
    p = next((x for x in d["produtos"] if x["slug"] == slug), None)
    if not p:
        return None
    fotos = "".join(f'<img src="{estatico("img/" + i["src"])}" alt="{e(i["alt"])}" width="800" height="800"{LAZY if n else ""}>' for n, i in enumerate(p["images"][:4]))
    opcoes = ""
    for a in p["attributes"]:
        rows = []
        for v in p["variations"]:
            nome = " / ".join(v["attrs"])
            rows.append(f"<option value=\"{e(nome)}\">{e(nome)}{' — ' + usd(v['price']) if v.get('price') else ''}{'' if v.get('in_stock', True) else ' (out of stock)'}</option>")
        if rows:
            opcoes = f'<label>{e(a["name"])}<select name="variacao">{"".join(rows)}</select></label>'
            break
    promo = f'<s>{usd(p["regular"])}</s> ' if p["on_sale"] and p["regular"] > p["price"] else ""
    cat = _categoria(p)
    from command_center.providers.stripe_loja import compravel
    comprar = stripe and compravel(p)
    corpo = f"""<section class="faixa clara" aria-labelledby="h-prod"><div class="largura produto">
  <div class="produto-fotos">{fotos or '<span class="sem-foto" aria-hidden="true">URACE</span>'}</div>
  <div class="produto-info">
    <p class="eyebrow"><a href="/store/{e(cat['slug'])}/">{e(cat['name'])}</a></p>
    <h1 id="h-prod">{e(p['name'])}</h1>
    <p class="produto-preco">{promo}<strong>{e(_preco(p))}</strong>{'' if p['in_stock'] else ' <span class="chip-fora">Out of stock</span>'}</p>
    {f'<div class="produto-short">{_niveis(p["short"], "p")}</div>' if p['short'] else ''}
    {ENVIADO.replace('your message', 'your order request') if enviado else ''}
    {ERRO_CHECKOUT if erro_checkout else ''}
    {_form_comprar(p) if comprar else ''}
    {'<details class="pedido-alt"' + (' open' if enviado else '') + '><summary>Questions, sizes or a custom order? Send an order request</summary>' if comprar else ''}
    <form class="form-pedido" method="post" action="/ops/api/vitrine/pedido" data-pedido data-produto="{e(p['slug'])}">
      {opcoes}
      <label>Quantity<input name="quantidade" type="number" min="1" max="20" value="1" inputmode="numeric"></label>
      <label>Your name<input name="nome" required autocomplete="name" maxlength="120"></label>
      <label>Email<input name="email" type="email" required autocomplete="email" maxlength="160"></label>
      <label>Phone <span class="opcional">(optional)</span><input name="telefone" type="tel" autocomplete="tel" maxlength="40"></label>
      <label>Notes <span class="opcional">(size, shipping address, questions)</span><textarea name="mensagem" maxlength="1000" rows="3"></textarea></label>
      <label class="escondido" aria-hidden="true">Leave this empty<input name="site" tabindex="-1" autocomplete="off"></label>
      <button class="btn{' btn-linha-escura' if comprar else ''}" type="submit">{'Send order request' if comprar else 'Order this' if p['in_stock'] else 'Ask about availability'}</button>
      <p class="small muted">We confirm availability, shipping and the total, and send you the invoice to pay online. Nothing is charged now.</p>
      <p class="form-estado" role="status" aria-live="polite"></p>
    </form>
    {'</details>' if comprar else ''}
  </div>
</div></section>
{f'<section class="faixa escura" aria-labelledby="h-desc"><div class="largura estreita texto"><h2 id="h-desc">About this product</h2>{_niveis(p["description"], "h3")}</div></section>' if p['description'] else ''}"""
    ld = {"@context": "https://schema.org", "@type": "Product", "name": p["name"], "sku": p.get("sku") or str(p["id"]),
          "url": f"https://{host}/store/p/{p['slug']}/", "brand": {"@type": "Brand", "name": "URACE"},
          **({"image": [f"https://{host}{estatico('img/' + i['src'])}" for i in p["images"][:4]]} if p["images"] else {}),
          "offers": {"@type": "Offer" if not (p["price_min"] and p["price_max"] and p["price_max"] != p["price_min"]) else "AggregateOffer",
                     "priceCurrency": "USD", "url": f"https://{host}/store/p/{p['slug']}/",
                     "availability": "https://schema.org/InStock" if p["in_stock"] else "https://schema.org/OutOfStock",
                     **({"lowPrice": f"{p['price_min']:.2f}", "highPrice": f"{p['price_max']:.2f}"} if (p["price_min"] and p["price_max"] and p["price_max"] != p["price_min"]) else {"price": f"{p['price']:.2f}"})}}
    desc = _desc(_resumo_produto(p), "From the URACE race shop at the Orlando Kart Center: parts, suits and gear chosen by racers.")
    return layout(host=host, caminho=f"/store/p/{p['slug']}/", titulo=f"{p['name']} | URACE Store", descricao=desc, corpo=corpo,
                  schemas=(_negocio(host), ld, _trilha(host, ("Store", "/store/"), (cat["name"], f"/store/{cat['slug']}/"), (p["name"], f"/store/p/{p['slug']}/"))),
                  scripts=("contato.js",), foto=p["images"][0]["src"] if p["images"] else None)


def _obrigado_generico(host, caminho, lang, volta_loja):
    T = lambda en, pt: idioma.t(lang, en, pt)  # noqa: E731
    botao = (f'<a class="btn" href="/store/">{T("Back to the store", "Voltar para a loja")}</a>' if volta_loja
             else f'<a class="btn" href="/">{T("Back to the home page", "Voltar para o início")}</a>')
    corpo = f"""<section class="faixa clara" aria-labelledby="h-ok"><div class="largura estreita texto pedido-pagina">
  {idioma.chave(lang, caminho)}
  <h1 id="h-ok">{T("Thank you", "Obrigado")}</h1>
  <p>{T("If you just paid, the confirmation is on its way to your email. Questions? Call or WhatsApp +1 (407) 250 2291.",
        "Se você acabou de pagar, a confirmação está a caminho do seu e-mail. Dúvidas? Ligue ou mande WhatsApp para +1 (407) 250 2291.")}</p>
  <p class="hero-acoes">{botao}</p>
</div></section>"""
    if volta_loja:
        titulo = T("Order confirmation | URACE Store", "Confirmação do pedido | URACE Store")
        desc = T("Your URACE Store order: payment confirmation and what happens next — pickup at the Orlando Kart Center or shipping.",
                 "O seu pedido na URACE Store: a confirmação do pagamento e o que vem a seguir — retirada no Orlando Kart Center ou envio.")
    else:
        titulo = T("Order confirmation | URACE", "Confirmação do pedido | URACE")
        desc = T("Your URACE order: payment confirmation for your race sessions and store items, and what happens next.",
                 "O seu pedido na URACE: a confirmação do pagamento das sessões e dos itens da loja, e o que vem a seguir.")
    return layout(host=host, caminho=caminho.split("?")[0], titulo=titulo, descricao=desc, corpo=corpo, indexar=False,
                  lang=lang)


def obrigado(host, pedido=None, lang="en", volta="/store/thanks/", **kw):
    """#174: a volta do Stripe Checkout da loja. Com o pedido, é a página do pedido (#245) com o estado
    dele; sem, um obrigado genérico. Fora do sitemap e do Google (noindex). #248: em inglês ou português."""
    if pedido:
        return pedido_pagina(host, pedido, caminho="/store/thanks/", lang=lang, volta=volta, **kw)
    return _obrigado_generico(host, volta, lang, volta_loja=True)


def cancelado(host, slug=None, lang="en", volta="/store/cancelled/"):
    T = lambda en, pt: idioma.t(lang, en, pt)  # noqa: E731
    d = dados("produtos.json")
    p = next((x for x in d["produtos"] if x["slug"] == slug), None) if slug else None
    volta_btn = (f'<a class="btn" href="/store/p/{e(p["slug"])}/">{T("Back to", "Voltar para")} {e(p["name"])}</a>' if p
                 else f'<a class="btn" href="/store/">{T("Back to the store", "Voltar para a loja")}</a>')
    corpo = f"""<section class="faixa clara" aria-labelledby="h-cancel"><div class="largura estreita texto pedido-pagina">
  {idioma.chave(lang, volta)}
  <h1 id="h-cancel">{T("Checkout cancelled", "Checkout cancelado")}</h1>
  <p>{T("Nothing was charged. You can try again whenever you like, or ask us anything first.",
        "Nada foi cobrado. Você pode tentar de novo quando quiser, ou tirar uma dúvida com a gente antes.")}</p>
  <p class="hero-acoes">{volta_btn} <a class="btn btn-linha-escura" href="/contact/?assunto=store">{T("Ask a question", "Tirar uma dúvida")}</a></p>
</div></section>"""
    return layout(host=host, caminho="/store/cancelled/", titulo=T("Checkout cancelled | URACE Store", "Checkout cancelado | URACE Store"),
                  descricao=T("Your URACE Store checkout was cancelled and nothing was charged. Go back to the product or ask our team a question.",
                              "O seu checkout na URACE Store foi cancelado e nada foi cobrado. Volte ao produto ou tire uma dúvida com a equipe."),
                  corpo=corpo, indexar=False, lang=lang)


# ------------------------------------------------------------------ carrinho (#236)
PERIODO_EN = {"manha": "Morning", "tarde": "Afternoon", "dia": "Full day"}


def carrinho(host, cancelado=False, stripe=True, restaurar=None, lang="en"):
    """A página do carrinho. As linhas vêm do navegador e o servidor recalcula (carrinho.js chama
    /ops/api/vitrine/carrinho). Fora do Google e do sitemap: é de cada pessoa.
    `restaurar` (#245): (pedido, itens, entrega) do "Restore cart"/"Try again" de um pedido que não foi
    pago. Os itens vão num atributo (só as escolhas, nunca preço) e o carrinho.js junta ao carrinho.
    #248: em inglês ou português (o carrinho.js lê o `lang` da página)."""
    T = lambda en, pt: idioma.t(lang, en, pt)  # noqa: E731
    aviso = (f'<p class="aviso-erro" role="alert">{T("Checkout cancelled: nothing was charged. Your cart is still here.", "Checkout cancelado: nada foi cobrado. O seu carrinho continua aqui.")}</p>'
             if cancelado else "")
    dados_rest, envio = "", False
    if restaurar:
        oid, itens_rest, entrega_rest = restaurar
        dados_rest = f' data-restaurar="{e(json.dumps(itens_rest, separators=(",", ":")))}"'
        envio = entrega_rest == "envio"
        aviso = ('<p class="aviso-ok" role="status">'
                 + T(f"We put the items of order #{int(oid)} back in your cart. Prices and availability are checked again before you pay.",
                     f"Os itens do pedido #{int(oid)} voltaram para o seu carrinho. Preços e disponibilidade são conferidos de novo antes de pagar.")
                 + "</p>")
    fora = ('' if stripe else '<p class="aviso-erro" role="alert">'
            + T("Online payment isn't available right now. Please call or WhatsApp us at +1 (407) 250 2291.",
                "O pagamento online não está disponível agora. Ligue ou mande WhatsApp para +1 (407) 250 2291.") + '</p>')
    corpo = f"""<section class="faixa clara" aria-labelledby="h-cart"><div class="largura carrinho-pagina">
  {idioma.chave(lang, "/cart/")}
  <h1 id="h-cart">{T("Your cart", "Seu carrinho")}</h1>
  {aviso}{fora}
  <div class="carrinho" data-api="/ops/api/vitrine/carrinho" data-portal="{PORTAL}"{dados_rest}>
    <p class="carrinho-estado" role="status" aria-live="polite">{T("Loading your cart…", "Carregando o seu carrinho…")}</p>
    <div class="carrinho-grade" hidden>
      <section class="carrinho-itens" aria-labelledby="h-itens">
        <h2 id="h-itens">{T("Items", "Itens")}</h2>
        <ul class="carrinho-linhas"></ul>
      </section>
      <section class="carrinho-resumo" aria-labelledby="h-resumo">
        <h2 id="h-resumo">{T("Order summary", "Resumo do pedido")}</h2>
        <div class="carrinho-conta" hidden></div>
        <fieldset class="entrega carrinho-entrega" hidden><legend>{T("Delivery for store items", "Entrega dos itens da loja")}</legend>
          <label class="opcao"><input type="radio" name="entrega" value="retirada"{'' if envio else ' checked'}> <span>{T("Pick up at the track", "Retirar na pista")} <span class="opcional">— Orlando Kart Center, {T("free", "grátis")}</span></span></label>
          <label class="opcao"><input type="radio" name="entrega" value="envio"{' checked' if envio else ''}> <span>{T("Ship to me", "Enviar para mim")} <span class="opcional">— {T("we confirm and bill shipping separately", "confirmamos e cobramos o frete à parte")}</span></span></label>
        </fieldset>
        <dl class="carrinho-total"></dl>
        <p class="carrinho-erro aviso-erro" role="alert" hidden></p>
        <button class="btn btn-cheio carrinho-pagar" type="button" disabled>{T("Checkout", "Pagar")}</button>
        <p class="small muted">{T("Secure checkout by Stripe: card, Apple Pay or Google Pay. Your URACE account is needed to buy. Prices and spots are checked again when you pay. The security deposit of a session is refundable: returned within 5 business days after the session if there is no incident.",
                                  "Pagamento seguro pelo Stripe: cartão, Apple Pay ou Google Pay. Para comprar, é preciso a sua conta URACE. Preços e vagas são conferidos de novo na hora de pagar. O depósito de segurança da sessão é reembolsável: volta em até 5 dias úteis depois da sessão, se não houver incidente.")}</p>
      </section>
    </div>
    <div class="carrinho-vazio" hidden>
      <p>{T("Your cart is empty.", "O seu carrinho está vazio.")}</p>
      <p class="hero-acoes"><a class="btn" href="/services/arrive-and-drive/#reservar">{T("Book a session", "Reservar uma sessão")}</a>
        <a class="btn btn-linha-escura" href="/store/">{T("Shop the store", "Ver a loja")}</a></p>
    </div>
  </div>
  <noscript><p class="aviso-erro">{T("The cart needs JavaScript.", "O carrinho precisa de JavaScript.")} <a href="{PORTAL}/reserve">{T("Book a session", "Reservar uma sessão")}</a>
    · <a href="/store/">{T("Store", "Loja")}</a></p></noscript>
</div></section>"""
    return layout(host=host, caminho="/cart/", titulo=T("Your cart | URACE", "Seu carrinho | URACE"),
                  descricao=T("Your URACE cart: race sessions and store items in one secure Stripe checkout, with prices checked by our system.",
                              "O seu carrinho na URACE: sessões e itens da loja num só pagamento seguro pelo Stripe, com os preços conferidos pelo sistema."),
                  corpo=corpo, indexar=False, lang=lang)


def carrinho_obrigado(host, pedido, itens=None, lang="en", volta="/cart/thanks/", **kw):
    """A volta do Stripe para o carrinho (noindex). Com o pedido, é a página do pedido (#245)."""
    if pedido:
        return pedido_pagina(host, pedido, caminho="/cart/thanks/", lang=lang, volta=volta, **kw)
    return _obrigado_generico(host, volta, lang, volta_loja=False)


# ------------------------------------------------------------------ a página do pedido (#245, #248)
# Um estado para cada resultado do Stripe: (h1, título da aba, meta description), em inglês e português.
ESTADO_PEDIDO = {
    "en": {
        "pago": ("Payment confirmed", "Payment confirmed | URACE",
                 "Your URACE order is paid and confirmed: the items, the total, the refundable deposit and what happens next."),
        "aguardando": ("Payment processing", "Payment processing | URACE",
                       "Your payment for this URACE order is still being confirmed. No need to pay again: we email you as soon as it clears."),
        "falhou": ("Payment didn't go through", "Payment didn't go through | URACE",
                   "The payment for this URACE order didn't go through and nothing was charged. Try again with the same items."),
        "expirado": ("Checkout expired", "Checkout expired | URACE",
                     "Your URACE checkout expired before the payment was finished and nothing was charged. Restore your cart in one tap."),
        "aberto": ("Checkout not finished", "Checkout not finished | URACE",
                   "We haven't received a payment for this URACE order yet and nothing was charged. Restore your cart to finish it."),
    },
    "pt": {
        "pago": ("Pagamento confirmado", "Pagamento confirmado | URACE",
                 "O seu pedido na URACE está pago e confirmado: os itens, o total, o depósito reembolsável e o que vem a seguir."),
        "aguardando": ("Pagamento em confirmação", "Pagamento em confirmação | URACE",
                       "O pagamento deste pedido na URACE ainda está sendo confirmado. Não pague de novo: mandamos e-mail assim que confirmar."),
        "falhou": ("O pagamento não foi concluído", "O pagamento não foi concluído | URACE",
                   "O pagamento deste pedido na URACE não foi concluído e nada foi cobrado. Tente de novo com os mesmos itens."),
        "expirado": ("O checkout expirou", "O checkout expirou | URACE",
                     "O seu checkout na URACE expirou antes do pagamento e nada foi cobrado. Restaure o carrinho com um toque."),
        "aberto": ("Checkout não concluído", "Checkout não concluído | URACE",
                   "Ainda não recebemos o pagamento deste pedido na URACE e nada foi cobrado. Restaure o carrinho para concluir."),
    },
}


def _pedido_linhas(ls, pago, lang):
    from command_center.providers import pedido_site
    T = lambda en, pt: idioma.t(lang, en, pt)  # noqa: E731
    out = []
    for x in ls:
        dep = (f'<span class="muted">+ {T("refundable security deposit", "depósito de segurança reembolsável")} {usd(x["deposit"])}</span>'
               if x["deposit"] else "")
        det = ""
        if pago and x["kind"] == "sessao" and x["booking_id"]:
            det = (f'<span class="pedido-passo">{T("Booked. Sign the waiver in your URACE account to confirm it.", "Reservada. Assine a waiver na sua conta URACE para confirmar.")} '
                   f'<a class="btn btn-sm" href="{PORTAL}/sessions/{x["booking_id"]}">{T("Sign the waiver", "Assinar a waiver")}</a></span>')
        elif pago and x["kind"] == "sessao":
            det = ('<span class="carrinho-sem-vaga">'
                   + T("This time was taken just before your payment. Our team will call you to pick another time (or refund it). Your payment is safe.",
                       "Este horário foi ocupado logo antes do seu pagamento. A nossa equipe vai ligar para escolher outro horário (ou devolver o valor). O seu pagamento está seguro.")
                   + "</span>")
        qtd = f' × {x["quantity"]}' if x["quantity"] > 1 else ""
        out.append(f'<li><b>{e(pedido_site.nome_linha(x, lang))}{qtd}</b><span>{usd(x["unit_price"] * x["quantity"])}</span>{dep}{det}</li>')
    return f'<ul class="carrinho-recibo">{"".join(out)}</ul>'


def _pedido_cliente(cli, lang):
    """#248 (dono, 14/10): "mostre todas as informações do cliente ali" — os dados da conta do site."""
    T = lambda en, pt: idioma.t(lang, en, pt)  # noqa: E731
    linhas = [(T("Name", "Nome"), cli["nome"]), ("E-mail", cli["email"]), (T("Phone", "Telefone"), cli["telefone"]),
              (T("Address", "Endereço"), cli["endereco"])]
    if cli["pilotos"]:
        linhas.append((T("Drivers", "Pilotos") if len(cli["pilotos"]) > 1 else T("Driver", "Piloto"), ", ".join(cli["pilotos"])))
    if cli["tem_produto"]:
        entrega = (T("Pick up at the Orlando Kart Center (10724 Cosmonaut Blvd, Box 3, Orlando, FL 32824)",
                     "Retirada no Orlando Kart Center (10724 Cosmonaut Blvd, Box 3, Orlando, FL 32824)") if cli["entrega"] == "retirada"
                   else T("Ship to", "Enviar para") + ": " + (cli["endereco_entrega"] or T("the address you give in the checkout", "o endereço informado no checkout")))
        linhas.append((T("Delivery", "Entrega"), entrega))
    itens = "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in linhas if v)
    return f'<h2 id="h-cliente">{T("Your details", "Os seus dados")}</h2><dl class="pedido-cliente">{itens}</dl>'


def pedido_pagina(host, o, *, ls, caminho, token, limpar=False, refeito=None, erro=None, csrf="", lang="en", volta=None,
                  cli=None):
    """A página de situação do pedido: `/order/<token>/` (o link pessoal) e a volta do Stripe
    (`/cart/thanks/`, `/store/thanks/`), com o mesmo desenho. `ls`: as linhas (`pedido_site.linhas`).
    `limpar`: a volta do Stripe com o pedido pago ou confirmando esvazia o carrinho deste navegador.
    `cli` (#248): os dados do cliente (`pedido_site.cliente`). Em inglês ou português (a chave no topo).
    Fora do Google (noindex); a rota manda `no-store`."""
    T = lambda en, pt: idioma.t(lang, en, pt)  # noqa: E731
    st = o["status"] if o["status"] in ESTADO_PEDIDO["en"] else "aberto"
    h1, titulo, desc = ESTADO_PEDIDO["pt" if lang == "pt" else "en"][st]
    sessao = any(x["kind"] == "sessao" for x in ls)
    produto = any(x["kind"] == "produto" for x in ls)
    deposito = sum(x["deposit"] or 0 for x in ls)
    valor = o["amount_paid"] if o["amount_paid"] is not None else o["amount"]
    nada = T("nothing was charged" + (" and no session was booked" if sessao else ""),
             "nada foi cobrado" + (" e nenhuma sessão foi reservada" if sessao else ""))
    para = e((cli or {}).get("email") or o["email"] or T("your email", "o seu e-mail"))
    voltar = (f'<a class="btn btn-linha-escura" href="{PORTAL}/sessions">{T("My sessions", "Minhas sessões")}</a>' if sessao and st == "pago"
              else f'<a class="btn btn-linha-escura" href="/store/">{T("Back to the store", "Voltar para a loja")}</a>' if not sessao
              else f'<a class="btn btn-linha-escura" href="/">{T("Home", "Início")}</a>')
    contato = f'<a class="btn btn-linha-escura" href="/contact/">{T("Contact us", "Fale com a gente")}</a>'
    aviso_erro = (f'<p class="aviso-erro" role="alert">{e(idioma.traduzir(erro, lang))}</p>' if erro else "")
    novo = ('<p class="aviso-ok" role="status">' + T("You placed this order again in a new checkout:", "Você refez este pedido num checkout novo:")
            + f' <a href="{e(refeito[1])}">{T("see order", "ver o pedido")} #{refeito[0]}</a>.</p>' if refeito else "")
    total = (f'<dl class="carrinho-total pedido-total"><dt class="soma">{T("Total paid", "Total pago") if st == "pago" else T("Order total", "Total do pedido")}</dt>'
             f'<dd class="soma">{usd(valor)}</dd>'
             + (f'<dt>{T("Includes the refundable security deposit", "Inclui o depósito de segurança reembolsável")}</dt><dd>{usd(deposito)}</dd>' if deposito else "")
             + "</dl>")
    itens = f'<h2 id="h-itens">{T("Your order", "O seu pedido")}</h2>{_pedido_linhas(ls, st == "pago", lang)}{total}'
    dados = _pedido_cliente(cli, lang) if cli else ""
    if st == "pago":
        passos = []
        if produto:
            passos.append(T("Store items: we'll email you when they're ready for pickup at the Orlando Kart Center.",
                            "Itens da loja: avisamos por e-mail quando estiverem prontos para retirar no Orlando Kart Center.")
                          if o["delivery"] == "retirada" else
                          T("Store items: we'll confirm the shipping cost and email you the tracking number. Shipping is billed separately.",
                            "Itens da loja: confirmamos o valor do frete e mandamos o código de rastreio por e-mail. O frete é cobrado à parte."))
        if sessao:
            passos.append(T("Each session is confirmed once the driver's waiver is signed in your URACE account.",
                            "Cada sessão é confirmada quando a waiver do piloto estiver assinada na sua conta URACE."))
        if deposito:
            passos.append(T("The security deposit is returned within 5 business days after the session if there is no incident.",
                            "O depósito de segurança é devolvido em até 5 dias úteis depois da sessão, se não houver incidente."))
        passos.append(T(f"A confirmation is on its way to {para}.", f"A confirmação está a caminho de {para}."))
        corpo_estado = (f'<p class="aviso-ok" role="status">{T("Thank you! Your order is confirmed. Payment received:", "Obrigado! O seu pedido está confirmado. Pagamento recebido:")} '
                        f'<strong>{usd(valor)}</strong>.</p>{itens}{dados}'
                        f'<h2 id="h-passos">{T("What happens next", "O que vem a seguir")}</h2><ul class="pedido-passos">'
                        + "".join(f"<li>{x}</li>" for x in passos) + f'</ul><p class="hero-acoes">{voltar}</p>')
    elif st == "aguardando":
        corpo_estado = ('<p class="aviso-info" role="status">'
                        + T(f"We're confirming your payment. Some payment methods, like a bank transfer, take a few days to clear. "
                            f"<strong>Please don't pay again</strong>: we'll email {para} as soon as it's confirmed.",
                            f"Estamos confirmando o seu pagamento. Alguns meios de pagamento, como a transferência bancária, levam alguns "
                            f"dias para confirmar. <strong>Não pague de novo</strong>: mandamos um e-mail para {para} assim que confirmar.")
                        + "</p>"
                        + ("<p>" + T("Session times are booked when the payment clears. If a time fills up before that, our team will call you to pick another one (or refund it).",
                                     "Os horários das sessões são reservados quando o pagamento confirmar. Se um horário lotar antes disso, a nossa equipe liga para escolher outro (ou devolver o valor).")
                           + "</p>" if sessao else "")
                        + f'{itens}{dados}<p class="hero-acoes">{voltar} {contato}</p>')
    elif st == "falhou":
        botao = ("" if refeito else
                 f'<form class="hero-acoes pedido-refazer" method="post" action="/order/{e(token)}/retry">'
                 f'<input type="hidden" name="csrf" value="{e(csrf)}">'
                 f'<button class="btn" type="submit">{T("Try again", "Tentar de novo")}</button> {contato}</form>')
        falta = T("The payment wasn't completed, so", "O pagamento não foi concluído, então")
        corpo_estado = (f'<p class="aviso-erro" role="alert">{falta} {nada}.</p>'
                        f'<p>{T("You can try again with the same items, with the same or another payment method. Prices and availability are checked again.", "Você pode tentar de novo com os mesmos itens, com o mesmo ou outro meio de pagamento. Preços e disponibilidade são conferidos de novo.")}</p>'
                        f'{botao}{itens}{dados}')
    else:                                               # expirado ou aberto: restaurar o carrinho
        motivo = (T("The secure checkout closed before the payment was finished", "O checkout seguro fechou antes de o pagamento ser concluído")
                  if st == "expirado" else
                  T("We haven't received a payment for this order yet", "Ainda não recebemos o pagamento deste pedido"))
        botao = ("" if refeito else
                 f'<p class="hero-acoes"><a class="btn" href="/order/{e(token)}/cart/">{T("Restore cart", "Restaurar o carrinho")}</a> {contato}</p>')
        corpo_estado = (f'<p class="aviso-erro" role="status">{motivo}, {T("so", "então")} {nada}.</p>'
                        f'<p>{T("Your items are saved. Restore your cart to pick up where you left off: prices and availability are checked again.", "Os seus itens estão guardados. Restaure o carrinho para continuar de onde parou: preços e disponibilidade são conferidos de novo.")}</p>'
                        f'{botao}{itens}{dados}')
    meu_link = ("" if caminho.startswith("/order/") else
                f'<p class="small muted">{T("Your order page, to check it any time:", "A página do seu pedido, para conferir quando quiser:")} '
                f'<a href="/order/{e(token)}/">{T("order", "pedido")} #{o["id"]}</a></p>')
    marca = " data-limpar-carrinho" if limpar else ""
    corpo = f"""<section class="faixa clara" aria-labelledby="h-ok"><div class="largura estreita texto pedido-pagina pedido-{st}"{marca}>
  {idioma.chave(lang, volta or caminho)}
  <p class="eyebrow">{T("Order", "Pedido")} #{o['id']}</p>
  <h1 id="h-ok">{h1}</h1>
  {aviso_erro}{novo}{corpo_estado}
  {meu_link}
</div></section>"""
    return layout(host=host, caminho=caminho, titulo=titulo, descricao=desc, corpo=corpo, indexar=False, lang=lang)


def _desc(texto, complemento):
    """meta description com pelo menos 80 caracteres: um texto curto ganha o complemento."""
    texto = texto.strip()
    if not texto.endswith(("…", "!", "?")):
        texto = texto.rstrip(".") + "."
    return texto if len(texto) >= 80 else f"{texto} {complemento}"


def _corte(texto, limite=155):
    """#252: corta sem partir palavra. Prefere o fim de uma frase; senão, a última palavra inteira
    e reticências. Antes o corte era seco em 120 e saía "add it w." no Google."""
    texto = texto.strip()
    if len(texto) <= limite:
        return texto
    pedaco = texto[:limite + 1]
    frase = max(pedaco.rfind(". "), pedaco.rfind("! "), pedaco.rfind("? "))
    if frase >= 80:
        return pedaco[:frase + 1].strip()
    return pedaco[:pedaco.rfind(" ")].rstrip(" ,;:·—-") + "…"


def _resumo_produto(p):
    """O texto da meta description de um produto: o resumo da loja, mas não quando ele é só a nota
    de rodapé de preço (começa com *) — aí vale o primeiro parágrafo da descrição, e por fim o nome."""
    for bruto in (p["short"], p["description"]):
        for pedaco in re.split(r"(?i)</p>|<br\s*/?>|\n", bruto or ""):
            t = re.sub(r"\s+([.,;:!?])", r"\1", _texto(pedaco))
            if len(t) >= 40 and not t.startswith("*") and not CODIGO.search(t):
                return _corte(t)
    return p["name"]


def _texto(h):
    from html import unescape
    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))).strip()


# ------------------------------------------------------------------ o mapa do site
def caminhos():
    """Todas as páginas do site, para o sitemap e o teste de "um h1 por página"."""
    d = dados("posts.json"); pr = dados("produtos.json")
    out = ["/", "/services/", C.ARRIVE["caminho"]] + [s["caminho"] for s in S.SERVICOS] + [p["caminho"] for p in P.PAGINAS]
    out += ["/blog/"] + [f"/blog/category/{c['slug']}/" for c in d["categorias"] if c["slug"] != "uncategorized" and c.get("count", 1)]
    out += [f"/blog/{p['slug']}/" for p in d["posts"]]
    out += ["/store/"] + [f"/store/{s}/" for s, _ in CATEGORIAS_LOJA] + [f"/store/p/{p['slug']}/" for p in pr["produtos"]]
    out += paginas_da_loja()                            # #261: /store/page/2/ e a página 2 de cada categoria
    return out


@lru_cache(maxsize=1)
def redirecionamentos():
    """Endereço antigo do urace.us → endereço novo (301). Nada do site antigo cai no 404."""
    # #236: /cart/ é o carrinho do site novo; o /checkout/ do WordPress cai nele
    # #252: /book-online/ é página indexada do urace.us (o Yoast publica no sitemap), então vai para
    # a página pública que faz o mesmo (agenda, preços e o botão de reservar) e não para dentro do portal
    r = {"/shop/": "/store/", "/book-online/": C.ARRIVE["caminho"], "/my-account/": PORTAL, "/checkout/": "/cart/"}
    for d in list(S.SERVICOS) + list(P.PAGINAS):
        for antigo in d.get("antigos", ()):
            r[antigo] = d["caminho"]
    pr = dados("produtos.json")
    for p in pr["produtos"]:
        r[f"/product/{p['slug']}/"] = f"/store/p/{p['slug']}/"
    for s, _ in CATEGORIAS_LOJA:
        r[f"/product-category/{s}/"] = f"/store/{s}/"
    for antigo, novo in ALIAS_LOJA.items():
        r[f"/product-category/{antigo}/"] = f"/store/{novo}/"
    r["/product-category/apparel/suits/"] = "/store/custom-kart-suits/"
    for c in ("/lp1-cancelada/", "/lp2-cancelada/", "/lp3-cancelada/", "/lp4-cancelada/", "/typ/", "/the-driver-factory-thank-you-page/"):
        r[c] = "/career/"
    for c in ("/affiliate-account/", "/affiliate-registration/", "/affiliate-reset-password/"):
        r[c] = PORTAL
    r["/product/go-kart-driving-experience/"] = C.ARRIVE["caminho"]
    for p in dados("posts.json")["posts"]:
        r[f"/{p['slug']}/"] = f"/blog/{p['slug']}/"
    for c in dados("posts.json")["categorias"]:
        r[f"/category/{c['slug']}/"] = f"/blog/category/{c['slug']}/"
    for s in ("sitemap_index", "post-sitemap", "page-sitemap", "product-sitemap",
              "category-sitemap", "product_cat-sitemap", "product_tag-sitemap"):
        r[f"/{s}.xml"] = "/sitemap.xml"                 # o Google volta a achar o mapa do site
    return r


# As famílias de endereço do WooCommerce que não têm par no site novo: subcategoria de produto,
# etiqueta, página 2 em diante, produto que saiu do catálogo e as telas da conta do WordPress.
# Sem isto, 110 endereços do urace.us de hoje cairiam no 404 no dia da troca (#252).
def _familia(caminho):
    m = re.fullmatch(r"(/.*?/)page/(\d+)/", caminho)     # /shop/page/2/, /blog/page/2/, /product-category/x/page/2/
    if m:
        base = destino(m.group(1)) or (m.group(1) if m.group(1) in caminhos() else None)
        # #261: a loja do site novo pagina de verdade, então a página N do WooCommerce vai para a
        # página N da loja quando ela existe; o blog (e a loja sem aquela página) vai para a primeira
        return (f"{base}page/{m.group(2)}/" if base and f"{base}page/{m.group(2)}/" in caminhos() else base)
    m = re.fullmatch(r"/product-category/(.+)/", caminho)
    if m:                                               # a subcategoria cai na categoria da loja, ou na loja
        fim = m.group(1).rstrip("/").split("/")[-1]
        cat = ALIAS_LOJA.get(fim, fim)
        return f"/store/{cat}/" if cat in dict(CATEGORIAS_LOJA) else "/store/"
    if re.fullmatch(r"/product-tag/[^/]+/", caminho):    # etiqueta de produto: a loja não tem página de etiqueta
        return "/store/"
    if re.fullmatch(r"/product/[^/]+/", caminho):        # produto que já não está no catálogo
        return "/store/"
    if re.fullmatch(r"/my-account/.+", caminho):         # lost-password, orders, downloads, edit-address…
        return PORTAL
    return None


def destino(caminho):
    """O endereço novo de um endereço do urace.us de hoje (301), ou None. Primeiro o mapa exato,
    depois as famílias do WooCommerce."""
    r = redirecionamentos()
    return r.get(caminho) or r.get(caminho + "/") or _familia(caminho) or _familia(caminho + "/")

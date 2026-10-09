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
from urllib.parse import quote

from command_center.vitrine import conteudo as C
from command_center.vitrine import conteudo_paginas as P
from command_center.vitrine import conteudo_servicos as S
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


def _passos(titulo, passos):
    return f"""<section class="faixa clara" aria-labelledby="h-passos"><div class="largura">
  <h2 id="h-passos">{e(titulo)}</h2>
  <ol class="passos">{"".join(f"<li>{e(p)}</li>" for p in passos)}</ol>
</div></section>"""


def _depoimentos(itens):
    if not itens:
        return ""
    return f"""<section class="faixa escura" aria-labelledby="h-depo"><div class="largura">
  <h2 id="h-depo">What our clients say</h2>
  <div class="depoimentos">{"".join(f'<blockquote><p>{e(t)}</p><footer>{e(n)}</footer></blockquote>' for n, t in itens)}</div>
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
    <a class="btn btn-linha-branca" href="{e(C.SITE['whatsapp'])}" rel="noopener">Need more details? Let's chat</a></div>
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
  <h2 id="h-inclui">{e(d.get('fornece_titulo') or 'What to expect')}</h2>
  <div class="inclui">
    {f"<div><h3>What to expect</h3>{_lista(d['espera'])}</div>" if d.get('espera') else ''}
    {f"<div><h3>We provide</h3>{_lista(d['fornece'])}</div>" if d.get('fornece') else ''}
    {f"<div><h3>You bring</h3>{_lista(d['trazer'])}</div>" if d.get('trazer') else ''}
  </div>
</div></section>""")
    if d.get("formatos"):
        acc = []
        for t, intro, itens in d["formatos"]:
            acc.append(f"<details><summary>{e(t)}</summary><div class='faq-corpo'><p>{e(intro)}</p>{_lista(itens) if itens else ''}</div></details>")
        partes.append(f"""<section class="faixa clara" aria-labelledby="h-formatos"><div class="largura duas">
  <div><h2 id="h-formatos">{e(d['formatos_titulo'])}</h2><p>{e(d['formatos_intro'])}</p></div>
  <div class="faq">{"".join(acc)}</div>
</div></section>""")
    if d.get("porque"):
        partes.append(f"""<section class="faixa vermelha" aria-labelledby="h-porque"><div class="largura">
  <p class="eyebrow">Why URACE</p><h2 id="h-porque">{e(d['porque_titulo'])}</h2>
  {f"<p>{e(d['porque_intro'])}</p>" if d.get('porque_intro') else ''}{_lista(d['porque'], 'checks claras')}
</div></section>""")
    if d.get("dias"):
        cards = "".join(f"""<article class="dia"><img src="{estatico('img/' + f)}" alt="" width="640" height="420" loading="lazy"><h3>{e(t)}</h3><p>{e(p)}</p></article>"""
                        for t, p, f in d["dias"])
        partes.append(f"""<section class="faixa clara" aria-labelledby="h-dias"><div class="largura">
  <h2 id="h-dias">{e(d['dias_titulo'])}</h2><div class="dias">{cards}</div></div></section>""")
    if d.get("para_quem"):
        partes.append(f"""<section class="faixa clara" aria-labelledby="h-quem"><div class="largura duas">
  <div><h2 id="h-quem">{e(d.get('para_quem_titulo') or 'Who is this for?')}</h2>{f"<p>{e(d['para_quem_intro'])}</p>" if d.get('para_quem_intro') else ''}</div>
  {_lista(d['para_quem'])}
</div></section>""")
    if d.get("curriculo"):
        partes.append(f"""<section class="faixa escura" aria-labelledby="h-curr"><div class="largura duas">
  <div><h2 id="h-curr">Curriculum highlights</h2>
    <dl class="curriculo">{"".join(f"<div><dt>{e(t)}</dt><dd>{e(p)}</dd></div>" for t, p in d['curriculo'])}</dl></div>
  <div><h2>Program objectives</h2><ol class="passos">{"".join(f"<li>{e(o)}</li>" for o in d['objetivos'])}</ol></div>
</div></section>""")
    if d.get("logistica"):
        partes.append(f"""<section class="faixa clara" aria-labelledby="h-log"><div class="largura duas">
  <div><h2 id="h-log">{e(d['logistica_titulo'])}</h2>{_lista(d['logistica'])}</div>
  <div><h2>{e(d['extras_titulo'])}</h2>{_lista(d['extras'], 'lista')}</div>
</div></section>""")
    if d.get("passos"):
        partes.append(_passos(d["passos_titulo"], d["passos"]))
    if d.get("investimento"):
        partes.append(f"""<section class="faixa vermelha" aria-labelledby="h-inv"><div class="largura centro">
  <h2 id="h-inv">Investment</h2><p class="preco-grande">{e(d['investimento'])}</p></div></section>""")
    partes.append(f"""<section class="faixa clara" aria-labelledby="h-faq"><div class="largura estreita">
  <h2 id="h-faq">Frequently asked questions</h2>{_faq(d['faq'])}</div></section>""")
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
    cards = "".join(f"""<a class="servico-card" href="{e(h)}"><img src="{estatico('img/' + f)}" alt="" width="640" height="400" loading="lazy">
  <span class="servico-txt"><strong>{e(t)}</strong><span>{e(p)}</span><em>{e(pr)}</em></span></a>""" for t, p, pr, h, f in d["cartoes"])
    corpo = f"""<section class="hero hero-servico hero-hub"><div class="hero-in">
  <p class="eyebrow">Services · Orlando, FL</p><h1>{e(d['h1'])}</h1><p class="hero-sub">{e(d['sub'])}</p>
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
        cards.append(f"""<article class="plano"><h3>{e(nome)}</h3><p class="plano-sub">{e(sub)}</p><p>{e(texto)}</p>
  <p class="plano-preco"><strong>{e(preco)}</strong><span>{e(por)}</span></p><a class="btn btn-sm" href="{e(href)}">Choose</a></article>""")
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
  <div><h2 id="h-curr">Curriculum highlights</h2><dl class="curriculo">{"".join(f"<div><dt>{e(t)}</dt><dd>{e(p)}</dd></div>" for t, p in d['curriculo'])}</dl></div>
  <div><h2>Program objectives</h2><ol class="passos">{"".join(f"<li>{e(o)}</li>" for o in d['objetivos'])}</ol></div>
</div></section>
<section class="faixa clara" aria-labelledby="h-carreira"><div class="largura estreita">
  <h2 id="h-carreira">{e(d['carreira_titulo'])}</h2><p>{e(d['carreira_intro'])}</p>{_lista(d['carreira'])}
  <p class="muted">Available as paid add-ons, negotiated separately once a driver is ready for them:</p>{_lista(d['carreira_extras'], 'lista')}
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


def pro_team(host):
    d = P.PRO_TEAM
    corpo = f"""{_hero(d)}
<section class="faixa clara" aria-labelledby="h-metodo"><div class="largura estreita"><h2 id="h-metodo">{e(d['suporte_titulo'])}</h2><p>{e(d['metodo'])}</p>
  <div class="cartoes">{"".join(f"<article class='cartao'><h3>{e(t)}</h3><p>{e(p)}</p></article>" for t, p in d['suporte'])}</div></div></section>
<section class="faixa escura" aria-labelledby="h-opcoes"><div class="largura"><h2 id="h-opcoes">{e(d['opcoes_titulo'])}</h2><p class="muted">{e(d['opcoes_sub'])}</p>{_planos(d['opcoes'], 'team')}</div></section>
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
    cards = "".join(f"""<article class="plano"><h3>{e(n)}</h3><p class="plano-sub">{e(s)}</p><p>{e(t)}</p><p class="plano-preco"><strong>{e(pr)}</strong></p><a class="btn btn-sm" href="{e(h)}">See more</a></article>"""
                    for n, s, t, pr, h in d["proximo"])
    corpo = f"""{_hero(d)}
<section class="faixa clara" aria-labelledby="h-primeira"><div class="largura estreita"><h2 id="h-primeira">{e(d['primeira_titulo'])}</h2>{_ps(d['primeira'])}</div></section>
<section class="faixa escura" aria-labelledby="h-contato"><div class="largura estreita"><h2 id="h-contato">{e(d['contato_titulo'])}</h2>{_ps(d['contato'])}
  <p><a class="btn" href="/services/arrive-and-drive/">Book my first day</a></p></div></section>
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
<section class="faixa clara" aria-labelledby="h-degraus"><div class="largura"><h2 id="h-degraus">{e(d['degraus_titulo'])}</h2><ol class="degraus">{degraus}</ol>
  <p class="muted small">{e(d['aviso'])}</p></div></section>
<section class="faixa escura" aria-labelledby="h-pessoa"><div class="largura duas"><div><h2 id="h-pessoa">{e(d['pessoa_titulo'])}</h2>{_ps(d['pessoa'])}</div><div class="campeoes">{fotos}</div></div></section>
<section class="faixa clara" aria-labelledby="h-prof"><div class="largura estreita"><h2 id="h-prof">{e(d['profissional_titulo'])}</h2>{_ps(d['profissional'])}{_lista(d['profissional_itens'])}</div></section>
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
<section class="faixa clara" aria-labelledby="h-equipe"><div class="largura duas"><div><h2 id="h-equipe">{e(d['equipe_titulo'])}</h2>{_ps(d['equipe'])}{_lista(d['equipe_itens'], 'lista')}<p>{e(d['equipe_fecho'])}</p></div>
  <div><h2>Vision</h2><p>{e(d['visao'])}</p><h2>Mission</h2>{_ps(d['missao'])}</div></div></section>
<section class="faixa vermelha" aria-labelledby="h-sup"><div class="largura duas"><div><h2 id="h-sup">{e(d['suporte_titulo'])}</h2>{_ps(d['suporte'])}</div>
  <div><h2>{e(d['seguranca_titulo'])}</h2><p>{e(d['seguranca_intro'])}</p>{_lista(d['seguranca'], 'checks claras')}<p>{e(d['seguranca_fecho'])}</p></div></div></section>
{_depoimentos(C.ARRIVE['depoimentos'])}
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
  <ul><li>Phone: <a href="tel:{e(C.SITE['telefone_e164'])}">{e(C.SITE['telefone'])}</a></li><li>Email: <a href="mailto:{e(C.SITE['emails'][1])}">{e(C.SITE['emails'][1])}</a></li></ul>
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
  <p class="hero-sub-escura">{e(descricao)}</p>
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
    return layout(host=host, caminho=f"/blog/{p['slug']}/", titulo=f"{p['title']} | URACE", descricao=_desc(p["description"], "From the URACE blog, Orlando."), corpo=corpo,
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


def _niveis(html, topo):
    """Títulos do texto copiado (h2–h6) viram um nível só, abaixo do título da seção."""
    return re.sub(r"<(/?)h[2-6]>", lambda m: f"<{m.group(1)}{topo}>", html)


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


def store(host, categoria=None):
    d = dados("produtos.json")
    produtos = d["produtos"]
    nomes = dict(CATEGORIAS_LOJA)
    if categoria and categoria not in nomes:
        return None
    if categoria:
        produtos = [p for p in produtos if _categoria(p)["slug"] == categoria]
    caminho = f"/store/{categoria}/" if categoria else "/store/"
    titulo = f"{nomes[categoria]} - URACE Store" if categoria else "Kart Parts Store - Chassis, Engines & Tires | URACE"
    descricao = (f"{nomes[categoria]} from the URACE race shop at the Orlando Kart Center, chosen and fitted by racers." if categoria else
                 "Racing kart parts in Orlando: chassis, engines, tires, apparel and accessories. Everything you need to race faster, from the URACE race shop.")
    chips = "".join(f'<a class="chip-link{" on" if s == categoria else ""}" href="/store/{s}/">{e(n)}</a>' for s, n in CATEGORIAS_LOJA)
    corpo = f"""<section class="faixa clara" aria-labelledby="h-loja"><div class="largura">
  <p class="eyebrow">Store</p><h1 id="h-loja">{e(nomes[categoria]) if categoria else 'Everything you need to race faster'}</h1>
  <p class="hero-sub-escura">{e(LOJA_SUB) if not categoria else e(descricao)}</p>
  <nav class="chips" aria-label="Categories"><a class="chip-link{'' if categoria else ' on'}" href="/store/">All</a>{chips}</nav>
  <div class="produtos-grade">{"".join(_produto_card(p) for p in produtos)}</div>
</div></section>
<section class="faixa escura" aria-labelledby="h-garantia"><div class="largura">
  <h2 id="h-garantia">Backed by racers, built for racers</h2>
  <div class="cartoes">
    <article class="cartao"><h3>Official gear</h3><p>Authentic parts and equipment from the best kart brands.</p></article>
    <article class="cartao"><h3>Expert support</h3><p>Our team knows karting from the inside. We help you choose the right product.</p></article>
    <article class="cartao"><h3>Fitted at the track</h3><p>Parts can be installed by the URACE mechanic at the Orlando Kart Center.</p></article>
    <article class="cartao"><h3>Fast answer</h3><p>Order online and the team confirms availability and shipping within one business day.</p></article>
  </div>
</div></section>
{_fecho('Not sure what you need?', 'Our team can help you choose the right parts, suit, or chassis for your level and category.', ('Ask the team', '/contact/?assunto=store'))}"""
    lista = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [
        {"@type": "ListItem", "position": i, "url": f"https://{host}/store/p/{p['slug']}/", "name": p["name"]} for i, p in enumerate(produtos[:50], 1)]}
    return layout(host=host, caminho=caminho, titulo=titulo, descricao=descricao, corpo=corpo,
                  schemas=(_negocio(host), lista, _trilha(host, ("Store", "/store/"))))


def product(host, slug, enviado=False):
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
    corpo = f"""<section class="faixa clara" aria-labelledby="h-prod"><div class="largura produto">
  <div class="produto-fotos">{fotos or '<span class="sem-foto" aria-hidden="true">URACE</span>'}</div>
  <div class="produto-info">
    <p class="eyebrow"><a href="/store/{e(cat['slug'])}/">{e(cat['name'])}</a></p>
    <h1 id="h-prod">{e(p['name'])}</h1>
    <p class="produto-preco">{promo}<strong>{e(_preco(p))}</strong>{'' if p['in_stock'] else ' <span class="chip-fora">Out of stock</span>'}</p>
    {f'<div class="produto-short">{_niveis(p["short"], "p")}</div>' if p['short'] else ''}
    {ENVIADO.replace('your message', 'your order request') if enviado else ''}
    <form class="form-pedido" method="post" action="/ops/api/vitrine/pedido" data-pedido data-produto="{e(p['slug'])}">
      {opcoes}
      <label>Quantity<input name="quantidade" type="number" min="1" max="20" value="1" inputmode="numeric"></label>
      <label>Your name<input name="nome" required autocomplete="name" maxlength="120"></label>
      <label>Email<input name="email" type="email" required autocomplete="email" maxlength="160"></label>
      <label>Phone <span class="opcional">(optional)</span><input name="telefone" type="tel" autocomplete="tel" maxlength="40"></label>
      <label>Notes <span class="opcional">(size, shipping address, questions)</span><textarea name="mensagem" maxlength="1000" rows="3"></textarea></label>
      <label class="escondido" aria-hidden="true">Leave this empty<input name="site" tabindex="-1" autocomplete="off"></label>
      <button class="btn" type="submit">{'Order this' if p['in_stock'] else 'Ask about availability'}</button>
      <p class="small muted">We confirm availability, shipping and the total, and send you the invoice to pay online. Nothing is charged now.</p>
      <p class="form-estado" role="status" aria-live="polite"></p>
    </form>
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
    desc = _desc((p["short"] and _texto(p["short"])[:120]) or p["name"], "From the URACE race shop at the Orlando Kart Center: parts, suits and gear chosen by racers.")
    return layout(host=host, caminho=f"/store/p/{p['slug']}/", titulo=f"{p['name']} | URACE Store", descricao=desc, corpo=corpo,
                  schemas=(_negocio(host), ld, _trilha(host, ("Store", "/store/"), (cat["name"], f"/store/{cat['slug']}/"), (p["name"], f"/store/p/{p['slug']}/"))),
                  scripts=("contato.js",), foto=p["images"][0]["src"] if p["images"] else None)


def _desc(texto, complemento):
    """meta description com pelo menos 80 caracteres: um texto curto ganha o complemento."""
    texto = texto.strip().rstrip(".") + "."
    return texto if len(texto) >= 80 else f"{texto} {complemento}"


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
    return out


def redirecionamentos():
    """Endereço antigo do urace.us → endereço novo (301). Nada do site antigo cai no 404."""
    r = {"/shop/": "/store/", "/book-online/": PORTAL + "/reserve", "/my-account/": PORTAL, "/cart/": "/store/", "/checkout/": "/store/"}
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
    return r

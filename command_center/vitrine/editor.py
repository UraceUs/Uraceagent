"""O editor visual do site público (#300): o modelo da página, a validação e o desenho.

Dono, 16/10: *"no Command Center separe o site público uma seção para o site público aí no site público a gente
tenha é, como alterar o design, layout, puxando e arrastando e soltando de uma forma bem simples e conseguir editar
por lá como se fosse realmente um WordPress"*. Decisão: **livre, tipo Elementor**.

A página é uma lista de itens, de cima para baixo:
- **seção** (`secao`): fundo, espaçamento e 1 a 3 colunas; cada coluna tem os seus elementos;
- **seção original** (`original`): numa página que já existe no site, cada faixa dela vira um item que se move ou
  se esconde, e continua viva (o preço do painel, a agenda, a loja). Entre elas entram as seções novas.

Elementos: título (h1/h2/h3), texto (negrito, itálico, lista), imagem (WebP do painel), botão, lista, espaço, os
karts do Arrive and Drive, produtos da loja, os cartões de uma página e perguntas frequentes. Karts, produtos e
cartões vêm do banco (#297, #298), nunca de texto colado.

Cor, tamanho e espaçamento são escolhas da paleta do site (classes, sem estilo solto: a política do site não deixa
estilo inline, e a paleta garante o contraste). Na publicação, `problemas()` confere o que o editor gerou: um h1,
título sem pular nível, foto com descrição, título e descrição da página.
"""
import json
import re
import secrets
from html import escape as e
from html.parser import HTMLParser

from command_center.vitrine import html_seguro

FUNDOS = {"clara": "clara", "escura": "escura", "marca": "vermelha", "cinza": "ed-cinza"}
ESPACOS = ("p", "m", "g")
TAMANHOS = ("p", "m", "g")
CORES = ("padrao", "marca", "suave")
ALINHAR = ("esq", "centro")
FORMAS = ("larga", "media", "quadrada")
PAGINAS_CARTOES = ("academy", "pro-team", "for-beginners")
WIDGETS = ("titulo", "texto", "imagem", "botao", "lista", "espaco", "karts", "produtos", "cartoes", "faq")
MAX_ITENS = 60
MAX_POR_COLUNA = 30
CAMINHO = re.compile(r"/(?:[a-z0-9]+(?:-[a-z0-9]+)*/)+")
# o que não pode virar página nova: o painel, os arquivos, a loja, o blog, o carrinho, o pedido, as páginas legais
RESERVADOS = ("/ops/", "/_s/", "/_f/", "/store/", "/blog/", "/cart/", "/order/", "/legal/", "/contact/", "/sitemap", "/robots")


class ErroEditor(ValueError):
    pass


def novo_id():
    return secrets.token_hex(4)


def _txt(v, n, campo, obrigatorio=False):
    t = re.sub(r"\s+", " ", str(v or "")).strip()
    if obrigatorio and not t:
        raise ErroEditor(f"{campo}: escreva o texto")
    if len(t) > n:
        raise ErroEditor(f"{campo}: até {n} caracteres")
    return t


def _escolha(v, opcoes, padrao):
    return v if v in opcoes else padrao


def link_ok(v):
    """Só caminho do próprio site ou https (nada de javascript:, data:)."""
    t = (v or "").strip()
    if re.fullmatch(r"/[A-Za-z0-9/_\-.?=&%#]*", t) or re.fullmatch(r"https://[^\s\"'<>]+", t) \
            or re.fullmatch(r"(tel:\+?[0-9 ()-]{6,20}|mailto:[^\s\"'<>@]+@[^\s\"'<>]+)", t):
        return t[:300]
    raise ErroEditor("link: use um caminho do site (ex.: /contact/), https://, tel: ou mailto:")


def foto_ok(src):
    """A foto tem de ser do site: subida no editor (/_f/…), da loja (/store/img/…) ou das fotos do site."""
    s = str(src or "")
    if re.fullmatch(r"/_f/[0-9a-f]{16}\.webp", s) or re.fullmatch(r"/store/img/[0-9]+-[0-9a-f]{16}\.webp", s):
        return s
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,150}\.(webp|jpg|jpeg|png|svg)", s) and ".." not in s:
        return s
    raise ErroEditor("imagem: suba a foto pelo editor")


# ------------------------------------------------------------------ validação
def _widget(w):
    if not isinstance(w, dict) or w.get("tipo") not in WIDGETS:
        raise ErroEditor("elemento desconhecido")
    t = w["tipo"]
    out = {"id": re.sub(r"[^a-z0-9]", "", str(w.get("id") or ""))[:12] or novo_id(), "tipo": t}
    if t in ("titulo", "texto", "botao"):
        out["alinhar"] = _escolha(w.get("alinhar"), ALINHAR, "esq")
    if t in ("titulo", "texto"):
        out["tamanho"] = _escolha(w.get("tamanho"), TAMANHOS, "m")
        out["cor"] = _escolha(w.get("cor"), CORES, "padrao")
    if t == "titulo":
        out["texto"] = _txt(w.get("texto"), 160, "título", True)
        out["nivel"] = w.get("nivel") if w.get("nivel") in (1, 2, 3) else 2
    elif t == "texto":
        h = html_seguro.limpar(w.get("html"))
        if len(h) > html_seguro.MAX:
            raise ErroEditor("texto longo demais")
        out["html"] = h
    elif t == "imagem":
        out["src"] = foto_ok(w.get("src"))
        out["alt"] = _txt(w.get("alt"), 200, "descrição da foto")
        out["forma"] = _escolha(w.get("forma"), FORMAS, "larga")
        out["largura"] = max(1, min(4000, int(w.get("largura") or 1600)))
        out["altura"] = max(1, min(4000, int(w.get("altura") or 900)))
        out["legenda"] = _txt(w.get("legenda"), 200, "legenda")
    elif t == "botao":
        out["texto"] = _txt(w.get("texto"), 60, "botão", True)
        out["link"] = link_ok(w.get("link"))
        out["estilo"] = _escolha(w.get("estilo"), ("cheio", "linha"), "cheio")
    elif t == "lista":
        itens = [_txt(x, 200, "item da lista") for x in (w.get("itens") or [])][:30]
        out["itens"] = [x for x in itens if x]
    elif t == "espaco":
        out["tamanho"] = _escolha(w.get("tamanho"), TAMANHOS, "m")
    elif t == "produtos":
        out["categoria"] = re.sub(r"[^a-z0-9-]", "", str(w.get("categoria") or ""))[:40]
        out["quantos"] = max(3, min(12, int(w.get("quantos") or 6)))
    elif t == "cartoes":
        out["pagina"] = _escolha(w.get("pagina"), PAGINAS_CARTOES, "academy")
    elif t == "faq":
        itens = []
        for x in (w.get("itens") or [])[:20]:
            q, a = _txt((x or {}).get("pergunta"), 200, "pergunta"), _txt((x or {}).get("resposta"), 1200, "resposta")
            if q and a:
                itens.append({"pergunta": q, "resposta": a})
        out["itens"] = itens
    return out


def limpar(conteudo, com_originais=False, n_originais=0):
    """O que veio do painel → o modelo guardado. Recusa o que não é do modelo; nunca guarda HTML solto."""
    itens = (conteudo or {}).get("itens") if isinstance(conteudo, dict) else None
    if not isinstance(itens, list):
        raise ErroEditor("página sem itens")
    if len(itens) > MAX_ITENS:
        raise ErroEditor(f"até {MAX_ITENS} seções por página")
    out, vistos = [], set()
    for it in itens:
        if not isinstance(it, dict):
            raise ErroEditor("item inválido")
        if it.get("tipo") == "original":
            if not com_originais:
                raise ErroEditor("seção original só existe numa página que já está no site")
            i = int(it.get("indice", -1))
            if not 0 <= i < n_originais or i in vistos:
                raise ErroEditor("seção original inválida")
            vistos.add(i)
            out.append({"id": f"o{i}", "tipo": "original", "indice": i, "oculto": bool(it.get("oculto"))})
            continue
        if it.get("tipo") != "secao":
            raise ErroEditor("item inválido")
        n = it.get("colunas") if it.get("colunas") in (1, 2, 3) else 1
        cols = list(it.get("itens") or [])[:n]
        cols += [[] for _ in range(n - len(cols))]
        colunas = []
        for c in cols:
            if not isinstance(c, list) or len(c) > MAX_POR_COLUNA:
                raise ErroEditor(f"até {MAX_POR_COLUNA} elementos por coluna")
            colunas.append([_widget(w) for w in c])
        out.append({"id": re.sub(r"[^a-z0-9]", "", str(it.get("id") or ""))[:12] or novo_id(), "tipo": "secao",
                    "fundo": _escolha(it.get("fundo"), FUNDOS, "clara"), "espaco": _escolha(it.get("espaco"), ESPACOS, "m"),
                    "colunas": n, "itens": colunas})
    return {"itens": out}


def slug(t):
    import unicodedata
    s = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60] or "page"


def caminho_novo(v):
    c = "/" + "/".join(p for p in str(v or "").strip().lower().split("/") if p) + "/"
    if not CAMINHO.fullmatch(c) or len(c) > 120:
        raise ErroEditor("endereço: use letras, números e hífen, como /summer-camp/")
    if c == "/" or any(c.startswith(r) for r in RESERVADOS):
        raise ErroEditor(f"o endereço {c} é do sistema; escolha outro")
    return c


# ------------------------------------------------------------------ as seções que a página já tem
class _Secoes(HTMLParser):
    """Separa o `<main>` de uma página do site nas faixas de cima (`<section>` de primeiro nível)."""
    def __init__(self, html):
        super().__init__(convert_charrefs=False)
        self.html, self.pos, self.nivel, self.inicio, self.secoes = html, 0, 0, None, []
        self._linhas = [0]
        for linha in html.splitlines(keepends=True):
            self._linhas.append(self._linhas[-1] + len(linha))

    def _onde(self):
        ln, col = self.getpos()
        return self._linhas[ln - 1] + col

    def handle_starttag(self, tag, attrs):
        if tag == "section":
            if self.nivel == 0:
                self.inicio = self._onde()
            self.nivel += 1

    def handle_endtag(self, tag):
        if tag == "section" and self.nivel:
            self.nivel -= 1
            if self.nivel == 0 and self.inicio is not None:
                fim = self.html.index(">", self._onde()) + 1
                self.secoes.append(self.html[self.inicio:fim])
                self.inicio = None


def extrair(html):
    """Do HTML de uma página do site: as faixas (seções), o título, a descrição, o JSON-LD e os scripts dela."""
    m = re.search(r'<main id="conteudo">(.*)</main>', html, re.S)
    p = _Secoes(m.group(1) if m else "")
    p.feed(m.group(1) if m else "")
    titulo = re.search(r"<title>(.*?)</title>", html, re.S)
    desc = re.search(r'<meta name="description" content="(.*?)">', html, re.S)
    from html import unescape
    lds = []
    for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            lds.append(json.loads(x))
        except ValueError:
            pass
    padrao = {"campanha.js", "carrinho.js", "medicao.js"}
    scripts = [s for s in re.findall(r'<script src="/_s/([a-z0-9_-]+\.js)\?v=', html) if s not in padrao]
    return {"secoes": p.secoes, "titulo": unescape(titulo.group(1)) if titulo else "",
            "descricao": unescape(desc.group(1)) if desc else "", "ld": lds, "scripts": list(dict.fromkeys(scripts))}


def de_uma_pagina(n):
    """O conteúdo inicial de uma página que já existe: as faixas dela, na ordem, como seções originais."""
    return {"itens": [{"id": f"o{i}", "tipo": "original", "indice": i, "oculto": False} for i in range(n)]}


def pagina_nova(titulo):
    """O começo de uma página nova: uma faixa escura com o h1 e um botão."""
    return {"itens": [{"id": novo_id(), "tipo": "secao", "fundo": "escura", "espaco": "g", "colunas": 1, "itens": [[
        {"id": novo_id(), "tipo": "titulo", "texto": titulo or "New page", "nivel": 1, "tamanho": "g", "cor": "padrao",
         "alinhar": "esq"},
        {"id": novo_id(), "tipo": "botao", "texto": "Book now", "link": "/services/arrive-and-drive/#reservar",
         "estilo": "cheio", "alinhar": "esq"}]]}]}


# ------------------------------------------------------------------ o desenho
def _classes(w):
    return " ".join(x for x in (f"ed-tam-{w.get('tamanho', 'm')}", f"ed-cor-{w.get('cor', 'padrao')}",
                                f"ed-al-{w.get('alinhar', 'esq')}") if x)


def _w(w, dados, primeira_foto):
    from command_center.vitrine import paginas_site as ps
    from command_center.vitrine.paginas import foto_url, usd
    t = w["tipo"]
    if t == "titulo":
        n = w["nivel"]
        return f'<h{n} class="ed-t {_classes(w)}">{e(w["texto"])}</h{n}>'
    if t == "texto":
        return f'<div class="texto ed-tx {_classes(w)}">{w["html"]}</div>' if w["html"] else ""
    if t == "imagem":
        lazy = "" if primeira_foto[0] else ' loading="lazy"'
        primeira_foto[0] = False
        leg = f"<figcaption>{e(w['legenda'])}</figcaption>" if w.get("legenda") else ""
        return (f'<figure class="ed-img ed-img-{w["forma"]}"><img src="{e(foto_url(w["src"]))}" alt="{e(w["alt"])}" '
                f'width="{w["largura"]}" height="{w["altura"]}" decoding="async"{lazy}>{leg}</figure>')
    if t == "botao":
        cl = "btn" + (" btn-linha-escura" if w["estilo"] == "linha" else "")
        return f'<p class="hero-acoes ed-al-{w["alinhar"]}"><a class="{cl}" href="{e(w["link"])}">{e(w["texto"])}</a></p>'
    if t == "lista":
        return f'<ul class="lista ed-lista">{"".join(f"<li>{e(x)}</li>" for x in w["itens"])}</ul>' if w["itens"] else ""
    if t == "espaco":
        return f'<div class="ed-espaco ed-espaco-{w["tamanho"]}" aria-hidden="true"></div>'
    if t == "karts":
        ks = dados.get("karts") or []
        if not ks:
            return ""
        cards = "".join(
            f'<article class="plano"><h3>{e(k["titulo"])}</h3><p class="plano-sub">{e(k.get("linha") or "")}</p>'
            f'<p class="plano-preco"><strong>{usd(k["price"])}</strong><span>per session</span></p>'
            f'<a class="btn btn-sm" href="/services/arrive-and-drive/#reservar">Book {e(k["titulo"])}</a></article>' for k in ks)
        return f'<div class="planos">{cards}</div>'
    if t == "produtos":
        ps_ = [p for p in ps.produtos() if not w["categoria"] or ps._categoria(p)["slug"] == w["categoria"]]
        ps_ = [p for p in ps_ if p.get("in_stock")][:w["quantos"]]
        return f'<div class="produtos-grade">{"".join(ps._produto_card(p) for p in ps_)}</div>' if ps_ else ""
    if t == "cartoes":
        cs = (dados.get("cartoes") or {}).get(w["pagina"]) or []
        return ps._grupos_dos_cartoes(cs, dados.get("planos")) if cs else ""
    if t == "faq":
        return ps._faq([(x["pergunta"], (x["resposta"],)) for x in w["itens"]], ident=f"faq-{w['id']}") if w["itens"] else ""
    return ""


def corpo(conteudo, dados=None, originais=()):
    """O HTML do `<main>`: as seções novas e as originais (as que não estão escondidas), na ordem do editor."""
    dados = dados or {}
    partes, primeira = [], [True]
    for it in conteudo["itens"]:
        if it["tipo"] == "original":
            if not it.get("oculto") and it["indice"] < len(originais):
                partes.append(originais[it["indice"]])
            continue
        cols = "".join(f'<div class="ed-col">{"".join(_w(w, dados, primeira) for w in c)}</div>' for c in it["itens"])
        partes.append(f'<section class="faixa {FUNDOS[it["fundo"]]} ed-secao ed-esp-{it["espaco"]}" id="s-{e(it["id"])}">'
                      f'<div class="largura"><div class="ed-grade ed-c{it["colunas"]}">{cols}</div></div></section>')
    return "\n".join(partes)


def ld_extra(conteudo):
    """O JSON-LD que os elementos pedem: as perguntas frequentes viram FAQPage."""
    from command_center.vitrine import paginas_site as ps
    faq = [(x["pergunta"], (x["resposta"],)) for it in conteudo["itens"] if it["tipo"] == "secao"
           for c in it["itens"] for w in c if w["tipo"] == "faq" for x in w["itens"]]
    return [ps._faq_ld(faq)] if faq else []


# ------------------------------------------------------------------ as regras do site
def problemas(conteudo, html_corpo, titulo, descricao):
    """O que impede publicar: as regras do site (CLAUDE.md) conferidas no HTML que o editor gerou."""
    out = []
    if not 10 <= len(titulo or "") <= 70:
        out.append("título da aba: de 10 a 70 caracteres (o Google mostra até uns 60)")
    if not 50 <= len(descricao or "") <= 170:
        out.append("descrição: de 50 a 170 caracteres (é o texto do Google embaixo do título)")
    niveis = [int(n) for n in re.findall(r"<h([1-6])\b", html_corpo)]
    h1 = niveis.count(1)
    if h1 != 1:
        out.append(f"a página precisa de exatamente um título nível 1 (h1); tem {h1}")
    anterior = 0
    for n in niveis:
        if n > anterior + 1:
            out.append(f"um título pula de nível (de h{anterior} para h{n}): use o nível {anterior + 1} antes")
            break
        anterior = n
    sem = sum(1 for it in conteudo["itens"] if it["tipo"] == "secao" for c in it["itens"] for w in c
              if w["tipo"] == "imagem" and not w.get("alt"))
    if sem:
        out.append(f"{sem} foto(s) sem descrição: quem não vê a foto (e o Google) lê a descrição")
    if not re.sub(r"<[^>]+>|\s", "", html_corpo):
        out.append("a página está vazia")
    return out

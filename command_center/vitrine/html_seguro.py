"""O texto do produto que a equipe escreve no painel vira HTML seguro para o site (#298).

A descrição e o resumo dos produtos são HTML (vieram do WooCommerce assim). No painel, a equipe muda esse texto
num editor simples (negrito, itálico, lista, subtítulo). Antes de gravar, só as tags que os 70 produtos de hoje
usam passam: p, br, strong/b, em/i, u, ul/ol/li, h2–h4, a (http(s), caminho do site, mailto, tel) e img
(https ou caminho do site). Atributo de evento, style, script, iframe e companhia não passam: o resto vira texto.

#172: o blog pede mais (`limpar(html, extra=BLOG)`): tabela, figura e citação, sem atributo nenhum. O post 451 do
WordPress tem `<figure><table>…`; sem isto, a tabela vira texto solto no primeiro salvar. Só o blog passa `extra`:
a loja e o editor do site continuam com as tags de sempre.

Revisão do #172: `<div>` vira `<p>` (o Enter do Chrome e o texto colado de uma página chegam em `<div>`; antes a div
sumia e os parágrafos grudavam), `href="/"` (a home) passa, `/\\` não passa (o Chromium lê `/\\host` como `//host`), e
as tags abertas se contam num Counter: um texto com milhares de tags abertas não leva segundos (era quadrático).
"""
import re
from collections import Counter
from html import escape
from html.parser import HTMLParser

TAGS = {"p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "h2", "h3", "h4", "a", "img"}
BLOG = frozenset({"table", "thead", "tbody", "tr", "th", "td", "figure", "figcaption", "blockquote"})
VAZIAS = {"br", "img"}
VIRA_P = {"div"}                 # o bloco que o Chrome cria no Enter e que vem no texto colado: entra como parágrafo
# bloco não cabe dentro de parágrafo: abrir um fecha o <p> aberto (como o navegador faz). Sem isto, a <div> que
# embrulha uma lista ou outras divs (texto colado de uma página) viraria <p><ul>… ou <p><p>…
BLOCOS = {"p", "ul", "ol", "li", "h2", "h3", "h4", "table", "figure", "blockquote"}
SOMEM_COM_CONTEUDO = {"script", "style", "iframe", "object", "embed", "template", "svg", "math", "noscript", "head", "title"}
MAX = 20_000


# sem espaço, aspas, <, > nem barra invertida: o Chromium lê "/\evil.example" como "//evil.example" (outro site)
_CHAR = r"[^\s\"'<>\\]"


def _url_ok(v, img=False):
    v = (v or "").strip()
    if v.startswith("//"):
        return False
    if img:
        return bool(re.fullmatch(rf"(https://|/){_CHAR}+", v))
    return bool(re.fullmatch(rf"(https?://|mailto:|tel:){_CHAR}+|/{_CHAR}*", v))   # "/" sozinho é a home


class _Limpa(HTMLParser):
    def __init__(self, tags=TAGS):
        super().__init__(convert_charrefs=True)
        self.out, self.abertas, self.fora, self.tags = [], [], 0, tags
        self.n = Counter()                       # quantas de cada tag estão abertas: `tag in self.abertas` sem varrer

    def _abre(self, tag):
        self.abertas.append(tag)
        self.n[tag] += 1

    def _fecha(self):
        t = self.abertas.pop()
        self.n[t] -= 1
        if t == "p" and self.out and self.out[-1] == "<p>":   # parágrafo vazio (a div que só embrulhava): some
            self.out.pop()
        else:
            self.out.append(f"</{t}>")
        return t

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in VIRA_P:                        # sem os atributos da div: o parágrafo nasce limpo
            tag, attrs = "p", []
        if tag in SOMEM_COM_CONTEUDO:
            self.fora += 1
            return
        if self.fora or tag not in self.tags:
            return
        a = dict((k.lower(), v) for k, v in attrs)
        if tag == "a":
            href = a.get("href")
            if not _url_ok(href):                 # link estranho (javascript:, data:…): fica só o texto
                return
            ext = href.strip().startswith("http")
            self.out.append(f'<a href="{escape(href.strip(), quote=True)}"'
                            + (' rel="noopener" target="_blank"' if ext else "") + ">")
            self._abre(tag)
            return
        if tag == "img":
            src = a.get("src")
            if _url_ok(src, img=True):
                self.out.append(f'<img src="{escape(src.strip(), quote=True)}" alt="{escape(a.get("alt") or "", quote=True)}" loading="lazy">')
            return
        if tag == "br":
            self.out.append("<br>")
            return
        if tag in BLOCOS and self.n["p"]:        # <p>a<ul>: o parágrafo fecha antes da lista
            while self._fecha() != "p":
                pass
        if tag == "li" and self.abertas and self.abertas[-1] == tag:      # <li>a<li>b: o primeiro fecha
            self._fecha()
        self.out.append(f"<{tag}>")
        self._abre(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        t = "p" if tag.lower() in VIRA_P else tag.lower()
        if t not in VAZIAS and t in self.tags and not self.fora and self.abertas and self.abertas[-1] == t:
            self.handle_endtag(t)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in VIRA_P:
            tag = "p"
        if tag in SOMEM_COM_CONTEUDO:
            self.fora = max(0, self.fora - 1)
            return
        if self.fora or tag not in self.tags or tag in VAZIAS or not self.n[tag]:
            return
        while self.abertas:                      # fecha o que ficou aberto dentro dela
            if self._fecha() == tag:
                break

    def handle_data(self, data):
        if not self.fora:
            self.out.append(escape(data, quote=False))


def limpar(html, extra=()):
    """HTML qualquer → só as tags seguras, tudo fechado. Vazio (ou só espaço e <br>) → ''. Quem grava confere o
    tamanho (`MAX`): cortar aqui partiria uma tag ao meio. `extra` (#172, só o blog): mais tags, sem atributo."""
    p = _Limpa(TAGS | set(extra) - SOMEM_COM_CONTEUDO)
    p.feed(str(html or ""))
    p.close()
    while p.abertas:
        p._fecha()
    saida = "".join(p.out).strip()
    if not re.sub(r"<br>|<p>|</p>|&nbsp;|\s", "", saida):
        return ""
    return saida

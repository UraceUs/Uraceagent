"""O texto do produto que a equipe escreve no painel vira HTML seguro para o site (#298).

A descrição e o resumo dos produtos são HTML (vieram do WooCommerce assim). No painel, a equipe muda esse texto
num editor simples (negrito, itálico, lista, subtítulo). Antes de gravar, só as tags que os 70 produtos de hoje
usam passam: p, br, strong/b, em/i, u, ul/ol/li, h2–h4, a (http(s), caminho do site, mailto, tel) e img
(https ou caminho do site). Atributo de evento, style, script, iframe e companhia não passam: o resto vira texto.
"""
import re
from html import escape
from html.parser import HTMLParser

TAGS = {"p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "h2", "h3", "h4", "a", "img"}
VAZIAS = {"br", "img"}
SOMEM_COM_CONTEUDO = {"script", "style", "iframe", "object", "embed", "template", "svg", "math", "noscript", "head", "title"}
MAX = 20_000


def _url_ok(v, img=False):
    v = (v or "").strip()
    if img:
        return bool(re.fullmatch(r"(https://|/)[^\s\"'<>]+", v)) and not v.startswith("//")
    return bool(re.fullmatch(r"(https?://|/|mailto:|tel:)[^\s\"'<>]+", v)) and not v.startswith("//")


class _Limpa(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.abertas, self.fora = [], [], 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in SOMEM_COM_CONTEUDO:
            self.fora += 1
            return
        if self.fora or tag not in TAGS:
            return
        a = dict((k.lower(), v) for k, v in attrs)
        if tag == "a":
            href = a.get("href")
            if not _url_ok(href):                 # link estranho (javascript:, data:…): fica só o texto
                return
            ext = href.strip().startswith("http")
            self.out.append(f'<a href="{escape(href.strip(), quote=True)}"'
                            + (' rel="noopener" target="_blank"' if ext else "") + ">")
            self.abertas.append(tag)
            return
        if tag == "img":
            src = a.get("src")
            if _url_ok(src, img=True):
                self.out.append(f'<img src="{escape(src.strip(), quote=True)}" alt="{escape(a.get("alt") or "", quote=True)}" loading="lazy">')
            return
        if tag == "br":
            self.out.append("<br>")
            return
        if tag in ("li", "p") and self.abertas and self.abertas[-1] == tag:      # <li>a<li>b: o primeiro fecha
            self.out.append(f"</{self.abertas.pop()}>")
        self.out.append(f"<{tag}>")
        self.abertas.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VAZIAS and tag.lower() in TAGS and not self.fora and self.abertas and self.abertas[-1] == tag.lower():
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in SOMEM_COM_CONTEUDO:
            self.fora = max(0, self.fora - 1)
            return
        if self.fora or tag not in TAGS or tag in VAZIAS or tag not in self.abertas:
            return
        while self.abertas:                      # fecha o que ficou aberto dentro dela
            t = self.abertas.pop()
            self.out.append(f"</{t}>")
            if t == tag:
                break

    def handle_data(self, data):
        if not self.fora:
            self.out.append(escape(data, quote=False))


def limpar(html):
    """HTML qualquer → só as tags seguras, tudo fechado. Vazio (ou só espaço e <br>) → ''. Quem grava confere o
    tamanho (`MAX`): cortar aqui partiria uma tag ao meio."""
    p = _Limpa()
    p.feed(str(html or ""))
    p.close()
    while p.abertas:
        p.out.append(f"</{p.abertas.pop()}>")
    saida = "".join(p.out).strip()
    if not re.sub(r"<br>|<p>|</p>|&nbsp;|\s", "", saida):
        return ""
    return saida

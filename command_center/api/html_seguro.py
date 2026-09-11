"""Corpo HTML de e-mail para exibir "como no Gmail", sem executar nada.

Camadas (todas): 1) esta limpeza tira script, iframe, object, form, link,
meta, handlers on* e URLs javascript:; 2) a página vai com CSP própria sem
script; 3) o painel a mostra num iframe com sandbox (sem script, sem
navegação do topo). Imagens remotas (https) e inline (data:) carregam —
é o que o dono pediu: "quero ver o e-mail como vejo no Gmail".
"""
import re

_TAGS_FORA = ("script", "iframe", "object", "embed", "form", "applet", "frame", "frameset", "noscript", "template")
_RX_BLOCOS = re.compile(r"<(%s)\b[^>]*>.*?</\1\s*>" % "|".join(_TAGS_FORA), re.I | re.S)
_RX_SOLTAS = re.compile(r"<\s*/?\s*(%s|meta|link|base|input|button|select|textarea)\b[^>]*>" % "|".join(_TAGS_FORA), re.I)
_RX_ON = re.compile(r"""\s+on[a-z]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""", re.I)
_RX_JS = re.compile(r"""(href|src|action|xlink:href|formaction|background)\s*=\s*(["']?)\s*(javascript|vbscript|data:text/html)[^"'\s>]*""", re.I)
_RX_STYLE_URL = re.compile(r"url\s*\(\s*['\"]?\s*(javascript|vbscript)[^)]*\)", re.I)
_RX_EXPR = re.compile(r"expression\s*\(", re.I)

CSP = ("default-src 'none'; img-src https: http: data: cid:; style-src 'unsafe-inline'; "
       "font-src https: data:; media-src https: data:; form-action 'none'; base-uri 'none'; "
       "frame-ancestors 'self'")


def limpar(html):
    h = html or ""
    h = _RX_BLOCOS.sub("", h)
    h = _RX_SOLTAS.sub("", h)
    h = _RX_ON.sub("", h)
    h = _RX_JS.sub(r'\1=\2#', h)
    h = _RX_STYLE_URL.sub("url()", h)
    h = _RX_EXPR.sub("expression_(", h)
    return h


def pagina(html, titulo=""):
    """Documento completo para o iframe: fonte do sistema, links abrem fora."""
    corpo = limpar(html)
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            f"<meta http-equiv='Content-Security-Policy' content=\"{CSP}\">"
            "<meta name='referrer' content='no-referrer'><base target='_blank'>"
            f"<title>{re.sub(r'[<>&]', '', titulo or '')}</title>"
            "<style>body{margin:12px;font:14px/1.45 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1b1b1f;background:#fff;word-break:break-word}"
            "img{max-width:100%;height:auto}table{max-width:100%}blockquote{border-left:3px solid #ddd;margin:8px 0;padding-left:10px;color:#555}</style>"
            f"</head><body>{corpo}</body></html>")

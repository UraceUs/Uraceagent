"""As páginas do editor visual do site (#300): rascunho, publicação e histórico.

- **Rascunho** é o que o painel salva enquanto a equipe mexe (sozinho, a cada mudança). Ninguém de fora vê.
- **Publicar** confere as regras do site (`vitrine/editor.problemas`) e põe o rascunho no ar; cada publicação vira
  uma **versão**, e "Voltar a esta versão" traz uma antiga para o rascunho (nada se apaga).
- Página **nova** ganha o endereço dela (ex.: `/summer-camp/`). Página que **já existe** no site começa com as faixas
  dela como seções originais; publicada, o editor serve aquele endereço. **Voltar ao original** tira a publicação:
  o site volta à página do código, e o rascunho e as versões ficam.
- **Revisão** (#315): cada rascunho salvo soma 1 em `rev`. O painel manda o `rev` que tem; se outra pessoa salvou
  antes, o salvar e o publicar recusam (`Conflito`, 409) em vez de um apagar o que o outro fez, e o Publicar só põe no
  ar o rascunho que a tela está mostrando.
"""
import hashlib
import json
import os

from command_center.db import agora, atualizar, inserir, todos, um
from command_center.vitrine import editor as ed

ErroEditor = ed.ErroEditor


class Conflito(ErroEditor):
    """#315: o rascunho mudou desde que esta tela o leu (outra pessoa salvou, ou outra aba)."""


CONFLITO = "outra pessoa (ou outra aba) salvou esta página agora há pouco: recarregue para ver o que ela fez"


def _conferir_rev(p, rev):
    if rev is not None and int(rev) != int(p.get("rev") or 0):
        raise Conflito(CONFLITO)


def _json(v):
    try:
        return json.loads(v) if v else None
    except ValueError:
        return None


def _pagina(r):
    p = dict(r)
    p["draft"] = _json(p["draft"]) or {"itens": []}
    p["published"] = _json(p["published"])
    mudou = (p["published"] is None or p["published"] != p["draft"] or p["pub_title"] != p["title"]
             or p["pub_description"] != p["description"])
    p["estado"] = "rascunho" if p["published"] is None else ("mudou" if mudou else "publicada")
    return p


def lista(con):
    return [_pagina(r) for r in todos(con, "SELECT * FROM site_pages ORDER BY (published IS NULL), path")]


def uma(con, pid):
    r = um(con, "SELECT * FROM site_pages WHERE id=?", (pid,))
    if not r:
        raise ErroEditor("página não existe")
    return _pagina(r)


def publicada(con, caminho):
    """A página do editor que está no ar neste endereço, ou None."""
    r = um(con, "SELECT * FROM site_pages WHERE path=? AND published IS NOT NULL", (caminho,))
    if not r:
        return None
    p = _pagina(r)
    return {"id": p["id"], "path": p["path"], "base": p["base"], "conteudo": p["published"],
            "title": p["pub_title"], "description": p["pub_description"] or ""}


def caminhos_novos(con):
    """As páginas novas que estão no ar (para o sitemap)."""
    return [r["path"] for r in todos(con, "SELECT path FROM site_pages WHERE base IS NULL AND published IS NOT NULL ORDER BY path")]


def criar_nova(con, por, titulo, caminho, existe):
    t = ed._txt(titulo, 70, "título da aba", True)
    c = ed.caminho_novo(caminho or "/" + ed.slug(t) + "/")
    if existe(c) or um(con, "SELECT 1 AS x FROM site_pages WHERE path=?", (c,)):
        raise ErroEditor(f"o endereço {c} já tem uma página: escolha outro")
    return inserir(con, "site_pages", path=c, base=None, title=t, description="",
                   draft=json.dumps(ed.pagina_nova(t), ensure_ascii=False), updated_by=por, updated_at=agora())


def criar_de_existente(con, por, caminho, extraido):
    """A página do site como ponto de partida: as faixas dela viram seções originais, o título e a descrição dela."""
    if um(con, "SELECT 1 AS x FROM site_pages WHERE path=?", (caminho,)):
        raise ErroEditor("essa página já está no editor: abra a que existe")
    if not extraido["secoes"]:
        raise ErroEditor("não deu para abrir essa página no editor")
    return inserir(con, "site_pages", path=caminho, base=caminho, title=extraido["titulo"][:70] or caminho,
                   description=extraido["descricao"][:170],
                   draft=json.dumps(ed.de_uma_pagina(len(extraido["secoes"])), ensure_ascii=False),
                   updated_by=por, updated_at=agora())


def salvar(con, por, pid, d, n_originais=0, existe=None, rev=None, erros=None):
    """O rascunho: o modelo validado, o título e a descrição. O endereço de página nova muda só antes de publicar.

    #315: o rascunho é tolerante (`ed.limpar(..., rascunho=True)`): o que não passa fica como estava e o motivo vai para
    `erros` ({id do elemento: motivo}). `rev` é a revisão que o painel tem (None: não confere)."""
    p = uma(con, pid)
    _conferir_rev(p, rev)
    c = {}
    if "conteudo" in d:
        c["draft"] = json.dumps(ed.limpar(d["conteudo"], com_originais=bool(p["base"]), n_originais=n_originais,
                                          rascunho=True, anterior=p["draft"], erros=erros), ensure_ascii=False)
    def pagina(nome, fazer):     # #315: no painel (com `erros`), o dado da página que não passa fica como estava
        try:
            v = fazer()
        except ErroEditor as e:
            if erros is None:
                raise
            erros["pagina"] = str(e)
            return
        if v is not None:
            c[nome] = v

    def endereco():
        if d["path"] == p["path"]:
            return None
        if p["base"] or p["published"] is not None:
            raise ErroEditor("o endereço não muda depois de publicada (o Google e quem salvou o link perderiam a página)")
        novo = ed.caminho_novo(d["path"])
        if (existe and existe(novo)) or um(con, "SELECT 1 AS x FROM site_pages WHERE path=? AND id<>?", (novo, pid)):
            raise ErroEditor(f"o endereço {novo} já tem uma página: escolha outro")
        return novo

    if "title" in d:
        pagina("title", lambda: ed._txt(d["title"], 90, "título da aba"))
    if "description" in d:
        pagina("description", lambda: ed._txt(d["description"], 200, "descrição"))
    if "path" in d:
        pagina("path", endereco)
    if c:      # troca e confere numa operação só: duas gravações com a mesma revisão não passam as duas
        sets = ", ".join(f"{k} = ?" for k in c)
        cur = con.execute(f"UPDATE site_pages SET {sets}, rev = rev + 1, updated_by = ?, updated_at = ? WHERE id = ? AND rev = ?",
                          (*c.values(), por, agora(), pid, int(p.get("rev") or 0)))
        if cur.rowcount == 0:
            raise Conflito(CONFLITO)
    return uma(con, pid)


def publicar(con, por, pid, conferir, rev=None):
    """`conferir(pagina)` devolve os problemas do rascunho (as regras do site). Sem problema: no ar e uma versão nova.
    `rev` (#315): a revisão que a tela mostra; se o rascunho mudou depois, recusa (`Conflito`)."""
    p = uma(con, pid)
    _conferir_rev(p, rev)
    probs = conferir(p)
    if probs:
        return probs
    quando = agora()
    conteudo = json.dumps(p["draft"], ensure_ascii=False)
    atualizar(con, "site_pages", pid, published=conteudo, pub_title=p["title"], pub_description=p["description"],
              published_at=quando, published_by=por, updated_at=quando)
    inserir(con, "site_page_versions", page_id=pid, content=conteudo, title=p["title"], description=p["description"],
            published_by=por, published_at=quando)
    return []


def despublicar(con, por, pid):
    """Tira do ar (a página do código volta, ou o endereço novo some). Rascunho e versões ficam."""
    uma(con, pid)
    atualizar(con, "site_pages", pid, published=None, pub_title=None, pub_description=None, updated_by=por, updated_at=agora())
    return uma(con, pid)


def versoes(con, pid):
    return [dict(r) for r in todos(con, """SELECT v.id, v.title, v.published_at, u.name AS por FROM site_page_versions v
                                            LEFT JOIN users u ON u.id=v.published_by WHERE v.page_id=? ORDER BY v.id DESC""", (pid,))]


def voltar(con, por, pid, vid):
    v = um(con, "SELECT * FROM site_page_versions WHERE id=? AND page_id=?", (vid, pid))
    if not v:
        raise ErroEditor("versão não existe")
    atualizar(con, "site_pages", pid, draft=v["content"], title=v["title"], description=v["description"],
              rev=int(uma(con, pid).get("rev") or 0) + 1, updated_by=por, updated_at=agora())
    return uma(con, pid)


# ------------------------------------------------------------------ fotos
def pasta_fotos():
    p = os.path.join(os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "site-fotos")
    os.makedirs(p, mode=0o700, exist_ok=True)
    return p


def guardar_foto(dados):
    """Foto do celular ou do computador → WebP ≤ 1600 px, sem EXIF. O nome é o hash: a mesma foto não duplica."""
    import io

    from PIL import Image

    from command_center.providers import imagem
    try:
        webp, ext = imagem.comprimir(dados)
    except imagem.ImagemInvalida as e:
        raise ErroEditor(str(e))
    nome = hashlib.sha256(webp).hexdigest()[:16] + ext
    caminho = os.path.join(pasta_fotos(), nome)
    if not os.path.exists(caminho):
        with open(caminho, "wb") as f:
            f.write(webp)
        os.chmod(caminho, 0o644)
    largura, altura = Image.open(io.BytesIO(webp)).size
    return {"src": f"/_f/{nome}", "largura": largura, "altura": altura}


def arquivo_da_foto(nome):
    import re
    if not re.fullmatch(r"[0-9a-f]{16}\.webp", nome or ""):
        return None
    c = os.path.join(pasta_fotos(), nome)
    return c if os.path.isfile(c) else None

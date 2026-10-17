"""O editor visual do site no painel (#300): Site público › Editor.

Dono, 16/10: *"como alterar o design, layout, puxando e arrastando e soltando de uma forma bem simples e conseguir
editar por lá como se fosse realmente um WordPress"*. Decisão: **livre, tipo Elementor**.

Ver e pré-visualizar é do operador; criar, mudar, publicar e voltar versão é do gerente, tudo auditado. A
pré-visualização é a página do site de verdade, desenhada do rascunho, num iframe do próprio painel (fora do Google).

#315 (dono, 16/10: *"ele abre uma mini visualização de como é o site público. E dali a pessoa consegue, por ali, clicar
no que ela precisa editar … É como se fosse um Canva"*): a prévia é a área de trabalho.
- `previa?editar=1` desenha com os `data-ed-*` e o `editor-previa.css`, sem medição; a política continua a do site
  (sem script nem estilo inline), só deixando o próprio painel pôr a prévia num iframe.
- O `PATCH` manda o `rev` que a tela tem (409 se outra pessoa salvou antes) e, com `desenhar`, recebe o HTML das seções
  novas para trocar só o que mudou, sem recarregar a prévia. O rascunho é tolerante e devolve os `erros` por elemento.
"""
import re
import sqlite3
from html import unescape

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import auditar, get_db
from command_center.providers import editor_site as es
from command_center.vitrine import editor as ed

r = APIRouter(prefix="/ops/api/site/editor", tags=["site"])
FOTO_MAX = 12 * 1024 * 1024


# ------------------------------------------------------------------ o desenho (site e pré-visualização)
def _dados():
    """O que os elementos do banco mostram: os karts do Arrive and Drive, os cartões das páginas e os planos."""
    from command_center.api import vitrine
    from command_center.providers import cartoes_site, servicos_site
    from command_center.vitrine import paginas

    def ler(con):
        # #312 (revisão): os mesmos karts que a página do Arrive and Drive mostra — o kart com dois serviços ativos sai
        ks = [sv for _k, sv in paginas._karts_do_painel(servicos_site.para_cliente(con, cartao=True)) if sv]
        return {"karts": sorted(ks, key=lambda k: (k.get("sort") or 0, k["price"])),
                "cartoes": {pg: cartoes_site.da_pagina(con, pg) or [] for pg in ed.PAGINAS_CARTOES},
                "planos": servicos_site.planos_para_cliente(con)}
    return vitrine._do_banco(ler) or {}


def _original(caminho, host):
    from command_center.api import vitrine
    html = vitrine.html_da_pagina(caminho, host)
    return ed.extrair(html) if html else {"secoes": [], "titulo": "", "descricao": "", "ld": [], "scripts": []}


def _orig(p, host):
    """A página do código que esta reescreve (desenhada uma vez por requisição), ou None numa página nova."""
    return _original(p["base"], host) if p.get("base") else None


def desenhar(pagina, host, conteudo=None, titulo=None, descricao=None, indexar=True, marcar=False, orig=False):
    """A página inteira (o `layout` do site): as seções do editor, as originais da página e o JSON-LD.
    `marcar` (#315): a prévia de edição do painel."""
    from command_center.vitrine.paginas import _negocio, layout
    conteudo = conteudo or pagina["conteudo"]
    if orig is False:
        orig = _orig(pagina, host)
    corpo = ed.corpo(conteudo, _dados(), orig["secoes"] if orig else (), marcar=marcar)
    schemas = list(orig["ld"]) if orig else [_negocio(host)]
    schemas += ed.ld_extra(conteudo)
    return layout(host=host, caminho=pagina["path"], titulo=titulo or pagina["title"], descricao=descricao or pagina["description"],
                  corpo=corpo, schemas=schemas, scripts=tuple(orig["scripts"]) if orig else (), indexar=indexar,
                  editando=marcar)


def _host(request):
    from command_center.api import vitrine
    return sorted(vitrine.hosts())[0] if vitrine.hosts() else "novo.urace.us"


def _saida(p, host, orig=False, dados=None):
    """O que o painel recebe: a página, os problemas que impedem publicar e o resumo das seções originais."""
    if orig is False:
        orig = _orig(p, host)
    resumo = []
    for s in (orig["secoes"] if orig else []):
        t = re.search(r"<h[1-3][^>]*>(.*?)</h[1-3]>", s, re.S)
        resumo.append(unescape(re.sub(r"<[^>]+>", "", t.group(1))).strip()[:80] if t else "")
    dados = _dados() if dados is None else dados
    html = ed.corpo(p["draft"], dados, orig["secoes"] if orig else ())
    return {"pagina": p, "problemas": ed.problemas(p["draft"], html, p["title"], p["description"]), "originais": resumo,
            "previa": f"/ops/api/site/editor/paginas/{p['id']}/previa"}


def _aud(con, request, u, evento, pid, detalhe=None):
    auditar(con, evento, f"user:{u['id']}", user_id=u["id"], entity_type="site_page", entity_id=pid, detail=detalhe,
            ip=auth._ip(request))


# ------------------------------------------------------------------ as rotas
@r.get("/paginas")
def paginas(request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """As páginas do editor e as do site que ainda podem ser abertas nele."""
    from command_center.api import vitrine
    ja = {p["path"] for p in es.lista(con)}
    host = _host(request)
    existentes = []
    for c in vitrine.EDITAVEIS:
        if c in ja:
            continue
        html = vitrine.html_da_pagina(c, host)
        existentes.append({"caminho": c, "titulo": ed.extrair(html)["titulo"] if html else c})
    return {"paginas": [{k: p[k] for k in ("id", "path", "base", "title", "estado", "published_at", "updated_at")}
                        for p in es.lista(con)], "existentes": existentes}


class NovaIn(BaseModel):
    title: str | None = None
    path: str | None = None
    base: str | None = None          # o caminho de uma página do site para abrir no editor


@r.post("/paginas", status_code=201)
def criar(dados: NovaIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    from command_center.api import vitrine
    host = _host(request)
    try:
        if dados.base:
            if dados.base not in vitrine.EDITAVEIS:
                raise ed.ErroEditor("essa página não abre no editor")
            pid = es.criar_de_existente(con, u["id"], dados.base, _original(dados.base, host))
        else:
            pid = es.criar_nova(con, u["id"], dados.title, dados.path, lambda c: vitrine.existe(c, host))
    except ed.ErroEditor as e:
        raise HTTPException(400, str(e))
    _aud(con, request, u, "site.page.create", pid, dados.model_dump(exclude_unset=True))
    con.commit()
    return _saida(es.uma(con, pid), host)


@r.get("/paginas/{pid}")
def pagina(pid: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    try:
        return _saida(es.uma(con, pid), _host(request))
    except ed.ErroEditor as e:
        raise HTTPException(404, str(e))


class SalvarIn(BaseModel):
    conteudo: dict | None = None
    title: str | None = None
    description: str | None = None
    path: str | None = None
    rev: int | None = None           # #315: a revisão que a tela tem (409 se outra pessoa salvou antes)
    desenhar: bool = False           # #315: devolve o HTML das seções novas para a prévia trocar só o que mudou


def _conflito(e):
    return HTTPException(409, {"motivo": "rev", "mensagem": str(e)})


@r.patch("/paginas/{pid}")
def salvar(pid: int, dados: SalvarIn, request: Request, con: sqlite3.Connection = Depends(get_db),
           u=Depends(auth.exige("MANAGER"))):
    """O rascunho (o painel salva sozinho a cada mudança). Ninguém de fora vê até publicar."""
    from command_center.api import vitrine
    host = _host(request)
    erros = {}
    try:
        p = es.uma(con, pid)
        orig = _orig(p, host)
        p = es.salvar(con, u["id"], pid, dados.model_dump(exclude_unset=True, exclude={"rev", "desenhar"}),
                      len(orig["secoes"]) if orig else 0, existe=lambda c: vitrine.existe(c, host), rev=dados.rev, erros=erros)
    except es.Conflito as e:
        raise _conflito(e)
    except ed.ErroEditor as e:
        raise HTTPException(404 if "não existe" in str(e) else 400, str(e))
    con.commit()
    d = _dados()
    out = _saida(p, host, orig, d)
    out["erros"] = erros
    if dados.desenhar:      # só as seções novas: as originais não mudam por dentro (movem e escondem na própria prévia)
        out["secoes"] = [{"id": i, "html": h} for i, h in vitrine._com_o_painel(
            lambda: ed.partes(p["draft"], d, orig["secoes"] if orig else (), marcar=True)) if not i.startswith("o")]
    return out


class PublicarIn(BaseModel):
    rev: int | None = None           # #315: publica só se o rascunho for o que a tela mostra


@r.post("/paginas/{pid}/publicar")
def publicar(pid: int, request: Request, dados: PublicarIn | None = None, con: sqlite3.Connection = Depends(get_db),
             u=Depends(auth.exige("MANAGER"))):
    host = _host(request)
    try:
        probs = es.publicar(con, u["id"], pid, lambda p: _saida(p, host)["problemas"], rev=dados.rev if dados else None)
    except es.Conflito as e:
        raise _conflito(e)
    except ed.ErroEditor as e:
        raise HTTPException(404, str(e))
    if probs:
        raise HTTPException(400, "Antes de publicar: " + "; ".join(probs))
    _aud(con, request, u, "site.page.publish", pid)
    con.commit()
    return _saida(es.uma(con, pid), host)


@r.post("/paginas/{pid}/despublicar")
def despublicar(pid: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    """Tira do ar. Numa página que já existia, o site volta à página do código; o rascunho e as versões ficam."""
    try:
        p = es.despublicar(con, u["id"], pid)
    except ed.ErroEditor as e:
        raise HTTPException(404, str(e))
    _aud(con, request, u, "site.page.unpublish", pid)
    con.commit()
    return _saida(p, _host(request))


@r.get("/paginas/{pid}/versoes")
def versoes(pid: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    return {"versoes": es.versoes(con, pid)}


class VoltarIn(BaseModel):
    rev: int | None = None           # #315: a revisão que a tela tem (409 se outra pessoa salvou depois)


@r.post("/paginas/{pid}/versoes/{vid}/voltar")
def voltar(pid: int, vid: int, request: Request, dados: VoltarIn | None = None, con: sqlite3.Connection = Depends(get_db),
           u=Depends(auth.exige("MANAGER"))):
    """A versão antiga volta para o rascunho (confira na pré-visualização e publique)."""
    try:
        p = es.voltar(con, u["id"], pid, vid, rev=dados.rev if dados else None)
    except es.Conflito as e:         # antes do ErroEditor: o Conflito é um ErroEditor e viraria 404
        raise _conflito(e)
    except ed.ErroEditor as e:
        raise HTTPException(404, str(e))
    _aud(con, request, u, "site.page.restore", pid, {"versao": vid})
    con.commit()
    out = _saida(p, _host(request))
    out["erros"] = {}                # a versão foi publicada: nada dela está recusado
    return out


@r.get("/paginas/{pid}/previa", include_in_schema=False)
def previa(pid: int, request: Request, editar: int = 0, con: sqlite3.Connection = Depends(get_db),
           u=Depends(auth.exige("OPERATOR"))):
    """O rascunho desenhado como o site mostra, para o iframe do editor. Fora do Google e sem cache.
    `editar=1` (#315): com os marcadores de edição e o CSS do editor, sem medição."""
    from command_center.api import vitrine
    try:
        p = es.uma(con, pid)
    except ed.ErroEditor as e:
        raise HTTPException(404, str(e))
    host = _host(request)
    html = vitrine._com_o_painel(lambda: desenhar({**p, "conteudo": p["draft"]}, host, indexar=False, marcar=bool(editar)))
    return HTMLResponse(html, headers={
        "Content-Security-Policy": vitrine.csp().replace("frame-ancestors 'none'", "frame-ancestors 'self'"),
        "X-Frame-Options": "SAMEORIGIN", "Cache-Control": "no-store"})


@r.post("/fotos", status_code=201)
async def foto(request: Request, arquivo: UploadFile = File(...), con: sqlite3.Connection = Depends(get_db),
               u=Depends(auth.exige("MANAGER"))):
    """Foto do celular ou do computador: WebP de até 1600 px, sem EXIF (sem a posição GPS)."""
    dados = await arquivo.read(FOTO_MAX + 1)
    if not dados or len(dados) > FOTO_MAX:
        raise HTTPException(400, "foto vazia ou maior que 12 MB")
    try:
        f = es.guardar_foto(dados)
    except ed.ErroEditor as e:
        raise HTTPException(400, str(e))
    auditar(con, "site.page.photo", f"user:{u['id']}", user_id=u["id"], entity_type="site_photo", entity_id=f["src"],
            ip=auth._ip(request))
    con.commit()
    return f

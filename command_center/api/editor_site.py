"""O editor visual do site no painel (#300): Site público › Editor.

Dono, 16/10: *"como alterar o design, layout, puxando e arrastando e soltando de uma forma bem simples e conseguir
editar por lá como se fosse realmente um WordPress"*. Decisão: **livre, tipo Elementor**.

Ver e pré-visualizar é do operador; criar, mudar, publicar e voltar versão é do gerente, tudo auditado. A
pré-visualização é a página do site de verdade, desenhada do rascunho, num iframe do próprio painel (fora do Google).
"""
import sqlite3

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

    def ler(con):
        ks = [k for k in servicos_site.para_cliente(con, cartao=True) if k.get("site_kart")]
        return {"karts": sorted(ks, key=lambda k: (k.get("sort") or 0, k["price"])),
                "cartoes": {pg: cartoes_site.da_pagina(con, pg) or [] for pg in ed.PAGINAS_CARTOES},
                "planos": servicos_site.planos_para_cliente(con)}
    return vitrine._do_banco(ler) or {}


def _original(caminho, host):
    from command_center.api import vitrine
    html = vitrine.html_da_pagina(caminho, host)
    return ed.extrair(html) if html else {"secoes": [], "titulo": "", "descricao": "", "ld": [], "scripts": []}


def desenhar(pagina, host, conteudo=None, titulo=None, descricao=None, indexar=True):
    """A página inteira (o `layout` do site): as seções do editor, as originais da página e o JSON-LD."""
    from command_center.vitrine.paginas import _negocio, layout
    conteudo = conteudo or pagina["conteudo"]
    orig = _original(pagina["base"], host) if pagina.get("base") else None
    corpo = ed.corpo(conteudo, _dados(), orig["secoes"] if orig else ())
    schemas = list(orig["ld"]) if orig else [_negocio(host)]
    schemas += ed.ld_extra(conteudo)
    return layout(host=host, caminho=pagina["path"], titulo=titulo or pagina["title"], descricao=descricao or pagina["description"],
                  corpo=corpo, schemas=schemas, scripts=tuple(orig["scripts"]) if orig else (), indexar=indexar)


def _host(request):
    from command_center.api import vitrine
    return sorted(vitrine.hosts())[0] if vitrine.hosts() else "novo.urace.us"


def _n_originais(p, host):
    return len(_original(p["base"], host)["secoes"]) if p["base"] else 0


def _problemas(p, host):
    orig = _original(p["base"], host) if p["base"] else None
    html = ed.corpo(p["draft"], _dados(), orig["secoes"] if orig else ())
    return ed.problemas(p["draft"], html, p["title"], p["description"])


def _saida(p, host):
    """O que o painel recebe: a página, os problemas que impedem publicar e o resumo das seções originais."""
    orig = _original(p["base"], host) if p["base"] else None
    resumo = []
    for s in (orig["secoes"] if orig else []):
        import re
        from html import unescape
        t = re.search(r"<h[1-3][^>]*>(.*?)</h[1-3]>", s, re.S)
        resumo.append(unescape(re.sub(r"<[^>]+>", "", t.group(1))).strip()[:80] if t else "")
    html = ed.corpo(p["draft"], _dados(), orig["secoes"] if orig else ())
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


@r.patch("/paginas/{pid}")
def salvar(pid: int, dados: SalvarIn, request: Request, con: sqlite3.Connection = Depends(get_db),
           u=Depends(auth.exige("MANAGER"))):
    """O rascunho (o painel salva sozinho a cada mudança). Ninguém de fora vê até publicar."""
    from command_center.api import vitrine
    host = _host(request)
    try:
        p = es.uma(con, pid)
        p = es.salvar(con, u["id"], pid, dados.model_dump(exclude_unset=True), _n_originais(p, host),
                      existe=lambda c: vitrine.existe(c, host))
    except ed.ErroEditor as e:
        raise HTTPException(404 if "não existe" in str(e) else 400, str(e))
    con.commit()
    return _saida(p, host)


@r.post("/paginas/{pid}/publicar")
def publicar(pid: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    host = _host(request)
    try:
        probs = es.publicar(con, u["id"], pid, lambda p: _problemas(p, host))
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


@r.post("/paginas/{pid}/versoes/{vid}/voltar")
def voltar(pid: int, vid: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    """A versão antiga volta para o rascunho (confira na pré-visualização e publique)."""
    try:
        p = es.voltar(con, u["id"], pid, vid)
    except ed.ErroEditor as e:
        raise HTTPException(404, str(e))
    _aud(con, request, u, "site.page.restore", pid, {"versao": vid})
    con.commit()
    return _saida(p, _host(request))


@r.get("/paginas/{pid}/previa", include_in_schema=False)
def previa(pid: int, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """O rascunho desenhado como o site mostra, para o iframe do editor. Fora do Google e sem cache."""
    from command_center.api import vitrine
    try:
        p = es.uma(con, pid)
    except ed.ErroEditor as e:
        raise HTTPException(404, str(e))
    host = _host(request)
    html = vitrine._com_o_painel(lambda: desenhar({**p, "conteudo": p["draft"]}, host, indexar=False))
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

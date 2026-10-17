"""O blog do site no painel (#172): Site › Blog.

Pedido na issue: artigos em rascunho ou publicados, com título, categoria, resumo, capa (WebP ≤ 1600 px, sem EXIF) e
texto com títulos, listas, links e imagens, mais uma prévia com o visual do site. O OPERATOR escreve o rascunho e
**só o ADMIN** (ou a conta de acesso livre) publica e despublica. Tudo vai para a auditoria (`blog.post.*`).
Dono, 16/10: *"editor do blog, pode seguir"*.

Despublicar um dos 7 artigos do WordPress derruba um endereço que o Google já indexou (404): a rota só tira do ar
com `confirmar` (a tela pergunta antes, com esse aviso).

Revisão do #172: publicar leva `visto` (o `updated_at` do rascunho que o administrador abriu); se o operador salvou
outro texto depois, 409 e nada vai ao ar. Id e offset absurdos (maiores que o inteiro do SQLite) dão 422, não 500.
"""
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import auditar, get_db
from command_center.providers import blog

r = APIRouter(prefix="/ops/api/site/blog", tags=["site"])
FOTO_MAX = 12 * 1024 * 1024
INT_MAX = 2**63 - 1                     # o maior inteiro do SQLite: acima disso o id estourava (OverflowError, 500)
Id = Annotated[int, Path(ge=1, le=INT_MAX)]


def _aud(con, request, u, evento, pid, detalhe=None):
    auditar(con, evento, f"user:{u['id']}", user_id=u["id"], entity_type="blog_post", entity_id=pid, detail=detalhe,
            ip=auth._ip(request))


def _erro(e):
    if isinstance(e, blog.RascunhoMudou):
        return HTTPException(409, str(e))
    return HTTPException(404 if "não existe" in str(e) else 400, str(e))


def _saida(con, pid):
    """O artigo, o que falta para publicar e o endereço da prévia."""
    p = blog.um_post(con, pid)
    return {"post": p, "problemas": blog.problemas(p["draft"]), "previa": f"/ops/api/site/blog/{pid}/previa",
            "categorias": blog.categorias()}


def _host():
    from command_center.api import vitrine
    return sorted(vitrine.hosts())[0] if vitrine.hosts() else "novo.urace.us"


# ------------------------------------------------------------------ ler
@r.get("")
def lista(q: str = "", estado: str | None = None, categoria: str | None = None,
          limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0, le=INT_MAX),
          con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """Os artigos (rascunho, no ar, mudado depois de publicar), paginados no servidor, com o total."""
    if estado and estado not in blog.ESTADOS:
        raise HTTPException(400, "estado: rascunho, no_ar ou mudou")
    return {**blog.lista(con, q, estado, categoria, limit, offset), "categorias": blog.categorias()}


@r.get("/{pid}")
def um(pid: Id, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    try:
        return _saida(con, pid)
    except blog.ErroBlog as e:
        raise _erro(e)


# ------------------------------------------------------------------ escrever (OPERATOR)
class NovoIn(BaseModel):
    title: str
    category: str
    slug: str | None = None


@r.post("", status_code=201)
def criar(dados: NovoIn, request: Request, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """Um rascunho novo: fora do ar até o administrador publicar."""
    try:
        pid = blog.criar(con, u["id"], dados.title, dados.category, dados.slug)
    except blog.ErroBlog as e:
        raise _erro(e)
    out = _saida(con, pid)                            # na auditoria, o título como ficou gravado (já limpo)
    _aud(con, request, u, "blog.post.create", pid, {"title": out["post"]["draft"]["title"], "category": out["post"]["category"]})
    return {"id": pid, **out}


class RascunhoIn(BaseModel):
    title: str | None = None
    seo_title: str | None = None
    excerpt: str | None = None
    description: str | None = None
    category: str | None = None
    image: str | None = None             # só "" (tirar a capa); a capa nova sobe por /capa
    image_alt: str | None = None
    html: str | None = None
    slug: str | None = None              # só antes da primeira publicação


@r.patch("/{pid}")
def salvar(pid: Id, dados: RascunhoIn, request: Request, con: sqlite3.Connection = Depends(get_db),
           u=Depends(auth.exige("OPERATOR"))):
    """Muda o rascunho. O site só vê depois que o administrador publicar."""
    d = dados.model_dump(exclude_unset=True)
    try:
        mudou = blog.salvar_rascunho(con, u["id"], pid, d)
    except blog.ErroBlog as e:
        raise _erro(e)
    if mudou:                                         # só os nomes dos campos: o texto do artigo não vai para o log
        _aud(con, request, u, "blog.post.update", pid, {"campos": mudou})
    return _saida(con, pid)


async def _foto(arquivo):
    dados = await arquivo.read(FOTO_MAX + 1)
    if not dados or len(dados) > FOTO_MAX:
        raise HTTPException(400, "foto vazia ou maior que 12 MB")
    try:
        return blog.guardar_imagem(dados)
    except blog.ErroBlog as e:
        raise HTTPException(400, str(e))


@r.post("/{pid}/capa")
async def capa(pid: Id, request: Request, arquivo: UploadFile = File(...), alt: str = Form(""),
               con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """A capa do artigo: WebP de até 1600 px, sem EXIF (sem a posição GPS), com o tamanho de verdade."""
    try:
        blog.linha(con, pid)
        f = await _foto(arquivo)
        blog.por_capa(con, u["id"], pid, f, alt)
    except blog.ErroBlog as e:
        raise _erro(e)
    _aud(con, request, u, "blog.post.photo", pid, {"capa": f["src"]})
    return _saida(con, pid)


@r.post("/{pid}/imagens", status_code=201)
async def imagem(pid: Id, request: Request, arquivo: UploadFile = File(...),
                 con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """Uma foto para o meio do texto: devolve o endereço (o editor põe no lugar do cursor)."""
    try:
        blog.linha(con, pid)
    except blog.ErroBlog as e:
        raise _erro(e)
    f = await _foto(arquivo)
    _aud(con, request, u, "blog.post.photo", pid, {"imagem": f["src"]})
    return f


@r.get("/{pid}/versoes")
def versoes(pid: Id, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    try:
        return {"versoes": blog.versoes(con, pid)}
    except blog.ErroBlog as e:
        raise _erro(e)


@r.post("/{pid}/versoes/{vid}/voltar")
def voltar(pid: Id, vid: Id, request: Request, con: sqlite3.Connection = Depends(get_db),
           u=Depends(auth.exige("OPERATOR"))):
    """A versão antiga volta para o rascunho (o site não muda até publicar de novo)."""
    try:
        blog.voltar(con, u["id"], pid, vid)
    except blog.ErroBlog as e:
        raise _erro(e)
    _aud(con, request, u, "blog.post.restore", pid, {"versao": vid})
    return _saida(con, pid)


# ------------------------------------------------------------------ publicar (ADMIN ou acesso livre)
class PublicarIn(BaseModel):
    visto: str | None                    # obrigatório: o `updated_at` do artigo que a tela abriu (null nos 7 importados)


@r.post("/{pid}/publicar")
def publicar(pid: Id, dados: PublicarIn, request: Request, con: sqlite3.Connection = Depends(get_db),
             u=Depends(auth.exige("ADMIN"))):
    """Põe o rascunho no ar: o blog, a categoria, o sitemap e o JSON-LD mudam na hora (o navegador de quem já abriu
    guarda a página até 5 min, e o sitemap até 24 h). Só o rascunho que o administrador viu: mudou depois → 409."""
    try:
        probs = blog.publicar(con, u["id"], pid, dados.visto)
    except blog.ErroBlog as e:
        raise _erro(e)
    if probs:
        raise HTTPException(400, "Antes de publicar, falta: " + "; ".join(probs))
    p = blog.um_post(con, pid)
    _aud(con, request, u, "blog.post.publish", pid, {"slug": p["slug"]})
    return _saida(con, pid)


class DespublicarIn(BaseModel):
    confirmar: bool = False


@r.post("/{pid}/despublicar")
def despublicar(pid: Id, request: Request, dados: DespublicarIn | None = None, con: sqlite3.Connection = Depends(get_db),
                u=Depends(auth.exige("ADMIN"))):
    """Tira do ar (o endereço vira 404). Um dos 7 do WordPress só sai com `confirmar`: o Google já tem o endereço."""
    try:
        p = blog.um_post(con, pid)
        if p["no_google"] and p["published"] is not None and not (dados and dados.confirmar):
            raise HTTPException(409, f"/blog/{p['slug']}/ já está no Google: tirar do ar faz o endereço dar 404. "
                                     "Confirme para tirar mesmo assim.")
        blog.despublicar(con, u["id"], pid)
    except blog.ErroBlog as e:
        raise _erro(e)
    _aud(con, request, u, "blog.post.unpublish", pid, {"slug": p["slug"], "no_google": p["no_google"]})
    return _saida(con, pid)


# ------------------------------------------------------------------ a prévia
@r.get("/{pid}/previa", include_in_schema=False)
def previa(pid: Id, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("OPERATOR"))):
    """O rascunho desenhado como o site mostra, para o iframe do painel. Fora do Google (noindex) e sem cache."""
    from command_center.api import vitrine
    from command_center.vitrine import paginas_site as ps
    try:
        linha = blog.linha(con, pid)
    except blog.ErroBlog as e:
        raise _erro(e)
    p = blog.para_o_site(linha, blog.um_post(con, pid)["draft"])
    html = vitrine._com_o_painel(lambda: ps.artigo(_host(), p, indexar=False))
    return HTMLResponse(html, headers={
        "Content-Security-Policy": vitrine.csp().replace("frame-ancestors 'none'", "frame-ancestors 'self'"),
        "X-Frame-Options": "SAMEORIGIN", "Cache-Control": "no-store"})

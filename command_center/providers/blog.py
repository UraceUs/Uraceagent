"""Os artigos do blog no banco, escritos no painel (#172): Site › Blog.

Pedido na issue: o OPERATOR escreve o rascunho e só o ADMIN (ou a conta de acesso livre) publica; publicar e
despublicar mudam na hora o blog, o sitemap e o JSON-LD; os artigos passam para o banco **sem mudar o endereço**
`/blog/<slug>/`. Dono, 16/10: *"editor do blog, pode seguir"*.

- Cada artigo é uma linha de `blog_posts`. Os 7 do WordPress entram uma vez (`importar`), com o id de lá e o HTML
  **como está** (sem passar pela limpeza: a tabela do post 451 continua inteira). Só roda com a tabela vazia, então o
  que a equipe muda ou tira do ar nunca volta na subida seguinte.
- **Rascunho** (`draft`) é o que o painel salva; o site lê só o **publicado** (`published`). Publicar copia o rascunho
  para o ar e guarda uma **versão**; "Voltar a esta versão" traz uma antiga para o rascunho (nada se apaga).
- O **endereço** (slug) trava na primeira publicação e não destrava ao despublicar: o Google já guardou.
- `publicados` devolve os artigos no **mesmo formato** do `posts.json` (o site continua desenhando igual).
- Revisão do #172: **publicar** só vai se o rascunho for o que o administrador viu (`visto` = o `updated_at` que a
  tela abriu; mudou no meio → `RascunhoMudou`, 409); a importação guarda a **versão original** de cada um dos 7; letra
  solta de UTF-16 (`\ud800`) sai do texto, e um texto muito acima do limite nem passa pela limpeza.
"""
import json
import re
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from command_center.db import agora, atualizar, inserir, todos, transacao, um
from command_center.vitrine import html_seguro

FL = ZoneInfo("America/New_York")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
SLUG_MAX = 100
# /blog/category/…, /blog/page/2/ e /blog/img/ são caminhos do blog, não artigos
RESERVADOS = ("category", "page", "img")
TITULO = (3, 120)
RESUMO_MAX = 400            # o texto do cartão; os 7 do WordPress têm até 366 letras
DESCRICAO = (50, 155)       # a do Google: até 155 aparece inteira
SEO_MAX = 70
ALT_MAX = 200
HTML_MAX = 60_000
CAMPOS = ("title", "seo_title", "excerpt", "description", "category", "image", "image_alt", "image_w", "image_h", "html")
ESTADOS = ("rascunho", "no_ar", "mudou")


class ErroBlog(ValueError):
    pass


class RascunhoMudou(ErroBlog):
    """O rascunho mudou depois que o administrador abriu o artigo: publicar poria no ar o que ele não viu."""


# ------------------------------------------------------------------ categorias e datas
def categorias(todas=False):
    """As categorias do blog: as 5 de `posts.json`, fixas (a issue não pede editar). `uncategorized` não se escolhe."""
    from command_center.vitrine.paginas_site import dados
    return [{"slug": c["slug"], "name": c["name"], "description": c.get("description") or ""}
            for c in dados("posts.json")["categorias"] if todas or c["slug"] != "uncategorized"]


def _categoria(slug):
    return next((c for c in categorias(todas=True) if c["slug"] == slug),
                {"slug": slug, "name": slug.replace("-", " ").title(), "description": ""})


def dia(v):
    """A data (AAAA-MM-DD, no fuso da Flórida) de um horário do banco; a "date" do WordPress já vem assim."""
    if not v:
        return None
    if len(v) == 10:
        return v
    try:
        quando = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return v[:10]
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    return quando.astimezone(FL).date().isoformat()


def hoje():
    return datetime.now(FL).date().isoformat()


# ------------------------------------------------------------------ leitura
def _js(d):
    """O JSON do conteúdo sempre do mesmo jeito: rascunho e publicado se comparam como texto."""
    return json.dumps({k: d.get(k) for k in CAMPOS}, ensure_ascii=False, sort_keys=True)


def _de(v):
    try:
        d = json.loads(v) if v else None
    except ValueError:
        return None
    return {k: d.get(k) for k in CAMPOS} if isinstance(d, dict) else None


def estado(r):
    if r["published"] is None:
        return "rascunho"
    return "no_ar" if r["published"] == r["draft"] else "mudou"


def para_o_site(r, c):
    """Uma linha do banco e um conteúdo (o publicado, ou o rascunho na prévia) no formato do `posts.json`."""
    return {"id": r["id"], "slug": r["slug"], "title": c.get("title") or "", "seo_title": c.get("seo_title") or "",
            "date": dia(r["first_published_at"]) or hoje(),
            "modified": dia(r["published_at"]) or dia(r["first_published_at"]) or hoje(),
            "excerpt": c.get("excerpt") or c.get("description") or "", "description": c.get("description") or "",
            "categories": [_categoria(c.get("category") or r["category"])], "image": c.get("image") or "",
            "image_alt": c.get("image_alt") or "", "image_w": c.get("image_w"), "image_h": c.get("image_h"),
            "html": c.get("html") or ""}


def publicados(con):
    """Os artigos no ar, do mais novo para o mais velho. None quando a tabela nunca recebeu artigo (o site cai no
    arquivo de antes); lista vazia quando a equipe tirou todos do ar."""
    if not um(con, "SELECT 1 AS x FROM blog_posts LIMIT 1"):
        return None
    rs = todos(con, """SELECT * FROM blog_posts WHERE published IS NOT NULL
                        ORDER BY first_published_at DESC, id DESC""")
    return [para_o_site(r, _de(r["published"]) or {}) for r in rs]


def _painel(r, leve=False):
    """O que o painel recebe de um artigo. Na lista (`leve`), sem o texto: o cartão não precisa dele."""
    draft, pub = _de(r["draft"]) or {}, _de(r["published"])
    if leve:
        draft = {k: v for k, v in draft.items() if k != "html"}
        pub = {k: v for k, v in pub.items() if k != "html"} if pub else None
    return {"id": r["id"], "slug": r["slug"], "category": r["category"], "origin": r["origin"], "estado": estado(r),
            "draft": draft, "published": pub,
            "first_published_at": r["first_published_at"], "published_at": r["published_at"] or r["first_published_at"],
            "publicado_por": r.get("publicado_por"), "updated_at": r["updated_at"], "mudado_por": r.get("mudado_por"),
            "created_at": r["created_at"], "endereco": f"/blog/{r['slug']}/",
            "endereco_travado": r["first_published_at"] is not None,
            # um dos 7 do WordPress: o endereço já está no Google (despublicar pede confirmação)
            "no_google": r["origin"] == "wordpress"}


_COM_NOMES = """SELECT b.*, p.name AS publicado_por, m.name AS mudado_por FROM blog_posts b
                LEFT JOIN users p ON p.id = b.published_by LEFT JOIN users m ON m.id = b.updated_by"""


def linha(con, pid):
    r = um(con, _COM_NOMES + " WHERE b.id=?", (pid,))
    if not r:
        raise ErroBlog("artigo não existe")
    return r


def um_post(con, pid):
    return _painel(linha(con, pid))


def lista(con, termo="", estado_=None, categoria=None, limit=20, offset=0):
    """O que o painel lista: busca por título ou endereço, estado e categoria. Paginado no servidor, com o total.
    Os rascunhos que nunca foram ao ar vêm primeiro; depois, do mais novo para o mais velho."""
    onde, args = [], []
    t = re.sub(r"\s+", " ", (termo or "").strip())[:80].lower()
    if t:
        onde.append("(LOWER(json_extract(b.draft, '$.title')) LIKE ? OR b.slug LIKE ?)")
        args += [f"%{t}%"] * 2
    if estado_ == "rascunho":
        onde.append("b.published IS NULL")
    elif estado_ == "no_ar":
        onde.append("b.published IS NOT NULL")
    elif estado_ == "mudou":
        onde.append("b.published IS NOT NULL AND b.published <> b.draft")
    if categoria:
        onde.append("b.category = ?")
        args.append(categoria)
    w = (" WHERE " + " AND ".join(onde)) if onde else ""
    total = um(con, f"SELECT COUNT(*) AS n FROM blog_posts b{w}", tuple(args))["n"]
    limit, offset = max(1, min(int(limit), 100)), max(0, int(offset))
    rs = todos(con, f"""{_COM_NOMES}{w}
                        ORDER BY (b.first_published_at IS NOT NULL), COALESCE(b.first_published_at, b.created_at) DESC, b.id DESC
                        LIMIT ? OFFSET ?""", (*args, limit, offset))
    return {"posts": [_painel(r, leve=True) for r in rs], "total": total, "limit": limit, "offset": offset}


# ------------------------------------------------------------------ validação
_SURROGATE = re.compile(r"[\ud800-\udfff]")


def _sem_surrogate(v):
    """O JSON aceita "\\ud800" (meia letra de UTF-16, sozinha); o banco não grava isso (UnicodeEncodeError, 500)."""
    return _SURROGATE.sub("", str(v or ""))


def _linha_de_texto(v):
    return re.sub(r"\s+", " ", _sem_surrogate(v)).strip()


def _texto(v, campo, minimo=0, maximo=None):
    t = _linha_de_texto(v)
    if minimo and len(t) < minimo:
        raise ErroBlog(f"{campo}: pelo menos {minimo} letras")
    if maximo and len(t) > maximo:
        raise ErroBlog(f"{campo}: até {maximo} letras (tem {len(t)})")
    return t


def _cat(v):
    v = str(v or "").strip()
    if v not in {c["slug"] for c in categorias()}:
        raise ErroBlog("categoria: escolha uma da lista")
    return v


def slug_de(titulo):
    """O endereço que sai do título: minúsculas, sem acento, palavras com hífen."""
    t = unicodedata.normalize("NFKD", str(titulo or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    if len(t) > 80:
        t = t[:80].rsplit("-", 1)[0]
    return t or "artigo"


def _slug(v):
    s = str(v or "").strip().strip("/").lower()
    s = s.removeprefix("blog/")
    if not SLUG.fullmatch(s) or len(s) > SLUG_MAX:
        raise ErroBlog(f"endereço: letras minúsculas, números e hífen, até {SLUG_MAX} (ex.: how-to-start-karting)")
    if s in RESERVADOS:
        raise ErroBlog(f"o endereço /blog/{s}/ é do sistema; escolha outro")
    return s


def _livre(con, s, pid=None):
    if um(con, "SELECT 1 AS x FROM blog_posts WHERE slug=? AND id IS NOT ?", (s, pid)):
        raise ErroBlog(f"o endereço /blog/{s}/ já é de outro artigo: escolha outro")
    return s


def limpar_html(v):
    v = _sem_surrogate(v)
    if len(v) > 2 * HTML_MAX:                 # nem limpa: muito acima do limite, e limpar texto enorme custa tempo
        raise ErroBlog(f"texto: longo demais (até {HTML_MAX:,} caracteres)")
    h = html_seguro.limpar(v, extra=html_seguro.BLOG)
    if len(h) > HTML_MAX:
        raise ErroBlog(f"texto: longo demais (até {HTML_MAX:,} caracteres)")
    return h


def problemas(c):
    """O que impede publicar (o que o Google e quem lê precisam)."""
    out = []
    if len(_linha_de_texto(c.get("title"))) < TITULO[0]:
        out.append("o título")
    d = len(_linha_de_texto(c.get("description")))
    if not DESCRICAO[0] <= d <= DESCRICAO[1]:
        out.append(f"a descrição para o Google, de {DESCRICAO[0]} a {DESCRICAO[1]} letras (tem {d})")
    if not _linha_de_texto(re.sub(r"<[^>]+>", " ", c.get("html") or "")):
        out.append("o texto do artigo")
    if c.get("category") not in {x["slug"] for x in categorias()}:
        out.append("a categoria")
    if str(c.get("image") or "").startswith("/_f/") and not _linha_de_texto(c.get("image_alt")):
        out.append("a descrição da capa (quem não vê a foto ouve esse texto)")
    return out


# ------------------------------------------------------------------ escrita
def _vazio(titulo, categoria):
    return {"title": titulo, "seo_title": "", "excerpt": "", "description": "", "category": categoria, "image": "",
            "image_alt": "", "image_w": None, "image_h": None, "html": ""}


def criar(con, por, titulo, categoria, slug=None):
    """Um rascunho novo (fora do ar). O endereço sai do título quando não vem; repetido ganha -2, -3…"""
    t = _texto(titulo, "título", *TITULO)
    cat = _cat(categoria)
    if slug:
        s = _livre(con, _slug(slug))
    else:
        base = slug_de(t)
        base = _slug(f"{base}-post" if base in RESERVADOS else base)
        s, n = base, 1
        while um(con, "SELECT 1 AS x FROM blog_posts WHERE slug=?", (s,)):
            n += 1
            s = f"{base[:SLUG_MAX - 4]}-{n}"
    return inserir(con, "blog_posts", slug=s, category=cat, draft=_js(_vazio(t, cat)), origin="painel",
                   updated_by=por, updated_at=agora())


def salvar_rascunho(con, por, pid, d):
    """Muda só o rascunho (o site não vê até publicar). Devolve os nomes dos campos que mudaram (para a auditoria)."""
    r = linha(con, pid)
    c = _de(r["draft"]) or {}
    novo = dict(c)
    if "title" in d:
        novo["title"] = _texto(d["title"], "título", *TITULO)
    if "seo_title" in d:
        novo["seo_title"] = _texto(d["seo_title"], "título para o Google", 0, SEO_MAX)
    if "excerpt" in d:
        novo["excerpt"] = _texto(d["excerpt"], "resumo", 0, RESUMO_MAX)
    if "description" in d:
        novo["description"] = _texto(d["description"], "descrição para o Google", 0, DESCRICAO[1])
    if "category" in d:
        novo["category"] = _cat(d["category"])
    if "image_alt" in d:
        novo["image_alt"] = _texto(d["image_alt"], "descrição da capa", 0, ALT_MAX)
    if "image" in d:                                  # pelo PATCH só se tira a capa; foto nova sobe por /capa
        if d["image"]:
            raise ErroBlog("a capa nova sobe pelo botão da capa")
        novo.update(image="", image_alt="", image_w=None, image_h=None)
    if "html" in d:
        novo["html"] = limpar_html(d["html"])
    campos = {}
    mudou = [k for k in CAMPOS if novo.get(k) != c.get(k)]
    if mudou:
        campos.update(draft=_js(novo), category=novo["category"])
    if "slug" in d and d["slug"] is not None:
        s = _slug(d["slug"])
        if s != r["slug"]:
            if r["first_published_at"]:
                raise ErroBlog("o endereço não muda depois de publicado (o Google e quem salvou o link perderiam o artigo)")
            campos["slug"] = _livre(con, s, pid)
            mudou.append("slug")
    if campos:
        atualizar(con, "blog_posts", pid, **campos, updated_by=por, updated_at=agora())
    return mudou


def por_capa(con, por, pid, foto, alt=""):
    """A capa que a equipe subiu (`foto`: o que `guardar_imagem` devolve) vai para o rascunho, com a descrição."""
    r = linha(con, pid)
    c = _de(r["draft"]) or {}
    c.update(image=foto["src"], image_w=foto["largura"], image_h=foto["altura"],
             image_alt=_texto(alt, "descrição da capa", 0, ALT_MAX) or c.get("image_alt") or "")
    atualizar(con, "blog_posts", pid, draft=_js(c), updated_by=por, updated_at=agora())


MUDOU = "o rascunho mudou depois que você abriu o artigo: confira o texto e a prévia de novo antes de publicar"


def publicar(con, por, pid, visto):
    """Põe o rascunho no ar e guarda uma versão. Devolve o que falta (lista vazia: publicou).

    `visto` é o `updated_at` do rascunho que o administrador abriu (None nos 7 importados, que nunca mudaram). Se o
    operador salvou outro texto depois, `RascunhoMudou`: nada vai ao ar sem ser visto. A conferência é a própria
    escrita (UPDATE … WHERE o rascunho é o mesmo): duas abas ao mesmo tempo também não passam."""
    r = linha(con, pid)
    if (r["updated_at"] or "") != (visto or ""):
        raise RascunhoMudou(MUDOU)
    c = _de(r["draft"]) or {}
    probs = problemas(c)
    if probs:
        return probs
    quando = agora()
    conteudo = _js(c)
    with transacao(con):
        cur = con.execute("""UPDATE blog_posts SET published=?, published_at=?, published_by=?, first_published_at=?,
                                    updated_at=? WHERE id=? AND draft=? AND COALESCE(updated_at, '')=?""",
                          (conteudo, quando, por, r["first_published_at"] or quando, quando, pid, r["draft"],
                           r["updated_at"] or ""))
        if cur.rowcount != 1:
            raise RascunhoMudou(MUDOU)
        inserir(con, "blog_post_versions", post_id=pid, content=conteudo, published_by=por, published_at=quando)
    return []


def despublicar(con, por, pid):
    """Tira do ar: o endereço vira 404 e sai do blog e do sitemap. O rascunho, o endereço e as versões ficam."""
    if linha(con, pid)["published"] is None:
        raise ErroBlog("o artigo não está no ar")
    atualizar(con, "blog_posts", pid, published=None, updated_by=por, updated_at=agora())


def versoes(con, pid):
    """As versões publicadas, da mais nova para a mais velha. A original de um dos 7 (`original`) tem a data do
    WordPress (AAAA-MM-DD) e ninguém do painel como autor."""
    linha(con, pid)
    rs = todos(con, """SELECT v.id, v.content, v.published_at, v.published_by, u.name AS por FROM blog_post_versions v
                        LEFT JOIN users u ON u.id = v.published_by WHERE v.post_id=?
                        ORDER BY v.published_at DESC, v.id DESC""", (pid,))
    return [{"id": v["id"], "published_at": v["published_at"], "por": v["por"], "original": v["published_by"] is None,
             "title": (_de(v["content"]) or {}).get("title") or ""} for v in rs]


def voltar(con, por, pid, vid):
    """A versão antiga volta para o rascunho (confira na prévia e publique). O endereço não muda."""
    linha(con, pid)
    v = um(con, "SELECT content FROM blog_post_versions WHERE id=? AND post_id=?", (vid, pid))
    if not v:
        raise ErroBlog("versão não existe")
    c = _de(v["content"]) or {}
    atualizar(con, "blog_posts", pid, draft=_js(c), category=c.get("category") or linha(con, pid)["category"],
              updated_by=por, updated_at=agora())


# ------------------------------------------------------------------ fotos
def guardar_imagem(dados):
    """Foto do celular ou do computador → WebP ≤ 1600 px, sem EXIF, servida em /_f/<hash>.webp (a mesma pasta e o
    mesmo endereço do editor do site). Devolve {src, largura, altura}."""
    from command_center.providers import editor_site
    try:
        return editor_site.guardar_foto(dados)
    except editor_site.ErroEditor as e:
        raise ErroBlog(str(e))


# ------------------------------------------------------------------ a importação dos 7 do WordPress
def _ler_arquivo(caminho):
    """Os artigos de `posts.json` no formato do banco: (id, slug, categoria, conteúdo json, data do WordPress)."""
    try:
        with open(caminho, encoding="utf-8") as f:
            artigos = json.load(f)["posts"]
    except (OSError, ValueError, KeyError):
        return []
    from command_center.vitrine.paginas import tamanho_estatico
    out = []
    for p in artigos:
        cat = (p.get("categories") or [{"slug": "uncategorized"}])[0]["slug"]
        w, h = tamanho_estatico(p["image"]) if p.get("image") else (None, None)
        c = _js({"title": p["title"], "seo_title": p.get("seo_title") or "", "excerpt": p.get("excerpt") or "",
                 "description": p.get("description") or "", "category": cat, "image": p.get("image") or "",
                 "image_alt": "", "image_w": w, "image_h": h, "html": p.get("html") or ""})
        out.append((p["id"], p["slug"], cat, c, p["date"]))
    return out


_SEM_ORIGINAL = """SELECT b.id FROM blog_posts b WHERE b.origin='wordpress' AND NOT EXISTS
                   (SELECT 1 FROM blog_post_versions v WHERE v.post_id=b.id AND v.published_by IS NULL)"""


def importar(con, caminho):
    """Os artigos de `posts.json` entram **uma vez**, como estão: o id do WordPress, a data como `datePublished`, o
    HTML cru (sem limpar) e a capa de static/img com o tamanho de verdade. Rascunho = publicado: nada muda no site.

    Cada um ganha também a **versão original** (a data do WordPress, sem autor do painel): a primeira publicação
    daqui troca o rascunho e o publicado, e sem ela o texto do site antigo não voltava mais. Num banco que já
    importou sem essa versão, ela entra na subida seguinte, uma vez só (o que a equipe mudou não é tocado)."""
    if um(con, "SELECT 1 AS x FROM blog_posts LIMIT 1"):
        faltam = {r["id"] for r in todos(con, _SEM_ORIGINAL)}
        if not faltam:
            return 0
        artigos = [a for a in _ler_arquivo(caminho) if a[0] in faltam]
        with transacao(con):
            con.executemany("INSERT INTO blog_post_versions (post_id, content, published_by, published_at) VALUES (?,?,NULL,?)",
                            [(pid, c, data) for pid, _s, _cat, c, data in artigos])
        return 0
    artigos = _ler_arquivo(caminho)
    if not artigos:
        return 0
    with transacao(con):
        con.executemany("""INSERT OR IGNORE INTO blog_posts (id, slug, category, draft, published, first_published_at, origin)
                           VALUES (?,?,?,?,?,?, 'wordpress')""", [(pid, s, cat, c, c, data) for pid, s, cat, c, data in artigos])
        con.executemany("INSERT INTO blog_post_versions (post_id, content, published_by, published_at) VALUES (?,?,NULL,?)",
                        [(pid, c, data) for pid, _s, _cat, c, data in artigos])
    return len(artigos)

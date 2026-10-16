"""Os cartões de preço das páginas do site, editados no painel (#297, parte 2).

Dono, 16/10: *"aquele serviço que estão na página do Arrive and Drive em qualquer outra página estejam e sejam
possíveis de ser manipulados os que já estão lá ou se a gente quiser adicionar algum outro lá pelo Command Center
… a gente consiga alterar o valor, alterar o nome, alterar as coisas ali"*.

- Cada cartão é uma linha de `site_offers`: página, grupo, título, subtítulo, texto, preço, "por", link e botão.
- Os cartões de hoje (planilha da Academy, opções do Pro Team, próximos passos do For Beginners) entram **uma
  vez**, pela `seed_key`; esconder não apaga, e o que a equipe mudou nunca é sobrescrito.
- O preço é texto (o que o cartão mostra: "$2,756", "Let’s talk"). Três marcas viram valor do painel, ao vivo:
  `{kart}` (o menor preço de kart do Arrive and Drive), `{academy}` e `{boost}` (o plano do painel).
- Página sem cartão ativo no banco (ou banco fora) cai no texto de sempre de `vitrine/conteudo_paginas.py`.
"""
import re

from command_center.db import agora, atualizar, inserir, todos, um

PAGINAS = {"academy": "/academy/", "pro-team": "/pro-team/", "for-beginners": "/for-beginners/"}
CAMPOS = {"grp": 80, "title": 80, "subtitle": 120, "body": 600, "price": 40, "per": 40, "button": 40}
MARCAS = ("{kart}", "{academy}", "{boost}")


class ErroCartao(ValueError):
    pass


def _texto(v, n):
    v = re.sub(r"\s+", " ", (v or "").strip())
    return v[:n] or None


def lista(con, pagina=None, ativos=False):
    onde, args = [], []
    if pagina:
        onde.append("page=?"); args.append(pagina)
    if ativos:
        onde.append("active=1")
    sql = "SELECT * FROM site_offers" + (" WHERE " + " AND ".join(onde) if onde else "") + " ORDER BY page, sort, id"
    return [dict(r) for r in todos(con, sql, tuple(args))]


def da_pagina(con, pagina):
    """Os cartões ativos da página, na ordem do painel; None quando a página não tem nenhum (cai no texto de sempre)."""
    cs = lista(con, pagina, ativos=True)
    return cs or None


def _link(v):
    t = (v or "").strip()
    if not t:
        return None
    # só endereço do próprio site (caminho) ou https: nada de javascript:, data: etc.
    if not (re.fullmatch(r"/[A-Za-z0-9/_\-.?=&%#]*", t) or re.fullmatch(r"https://[^\s\"'<>]+", t)):
        raise ErroCartao("link: use um caminho do site (ex.: /contact/) ou um endereço https://")
    return t[:300]


def _dados(d, parcial):
    c = {}
    if not parcial or "page" in d:
        if d.get("page") not in PAGINAS:
            raise ErroCartao("página: " + ", ".join(PAGINAS))
        c["page"] = d["page"]
    if not parcial or "title" in d:
        t = _texto(d.get("title"), CAMPOS["title"])
        if not t or len(t) < 2:
            raise ErroCartao("dê um título ao cartão (o cliente lê, em inglês)")
        c["title"] = t
    for k, n in CAMPOS.items():
        if k != "title" and k in d:
            c[k] = _texto(d.get(k), n)
    if "link" in d:
        c["link"] = _link(d.get("link"))
    if "active" in d and d["active"] is not None:
        c["active"] = 1 if d["active"] else 0
    if "sort" in d and d["sort"] is not None:
        c["sort"] = int(d["sort"])
    return c


def criar(con, por, d):
    c = _dados(d, parcial=False)
    if "sort" not in c:
        ult = um(con, "SELECT COALESCE(MAX(sort), 0) AS s FROM site_offers WHERE page=?", (c["page"],))
        c["sort"] = (ult["s"] or 0) + 10
    return inserir(con, "site_offers", **c, updated_by=por, updated_at=agora())


def mudar(con, por, cid, d):
    """Devolve {campo: (antes, depois)} — vai para a auditoria."""
    atual = um(con, "SELECT * FROM site_offers WHERE id=?", (cid,))
    if not atual:
        raise ErroCartao("cartão não existe")
    c = _dados(d, parcial=True)
    mud = {k: (atual[k], v) for k, v in c.items() if atual[k] != v}
    if mud:
        atualizar(con, "site_offers", cid, **{k: v for k, (_, v) in mud.items()}, updated_by=por, updated_at=agora())
    return mud


def preco_kart(con):
    """O "a partir de" do site: o menor preço de kart que o painel vende (o kart próprio não entra, senão o site
    anunciaria o preço de quem traz o kart). Sem kart à venda, o de `conteudo.KARTS`."""
    from command_center.providers import servicos_site
    from command_center.vitrine import conteudo as C
    precos = [s["price"] for s in servicos_site.para_cliente(con, cartao=True) if s["site_kart"] and not s["proprio"]]
    return min(precos) if precos else C.preco_minimo()


def com_marcas(texto, valores):
    """`{kart}`, `{academy}` e `{boost}` no preço viram o valor do painel (vazio quando o painel não tem)."""
    t = texto or ""
    for m in MARCAS:
        if m in t:
            t = t.replace(m, valores.get(m.strip("{}")) or "")
    return t

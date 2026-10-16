"""Os produtos da loja no banco, editados no painel (#298).

Dono, 16/10: *"nos produtos da loja, colocar o valor de envio, o shipping, o valor de shipping … que eu consiga
alterar … essas funções serão necessárias que sejam ativas permanentemente"*. Decisões: frete = **valor fixo por
produto**; no painel = **tudo do produto**.

- Cada produto é uma linha de `store_products`. Os 70 do WooCommerce entram uma vez (`db._importar_produtos`).
- `catalogo` devolve os produtos no **mesmo formato** do `produtos.json` de antes (o site, o carrinho e o Stripe
  continuam lendo igual), mais `shipping_fee` e `deposit`.
- **Frete**: valor fixo por unidade, cobrado com "Ship to me". Vazio (None) = como antes, a equipe combina e
  cobra à parte; 0 = frete grátis.
- **Depósito de segurança**: por unidade, reembolsável (o mesmo do serviço da agenda); 0 = sem depósito.
- Preço: "Preço" é o cheio (`regular`); "Preço promocional" (opcional) é o que se cobra (`price`). Com variações,
  cada uma tem o seu, e a faixa (`price_min`/`price_max`) sai delas.
- Esconder não apaga: o produto sai da loja, do carrinho e do sitemap, e o histórico dos pedidos continua.
- **Como vendemos** (#309, dono, 16/10: *"a gente seleciona o que que é dropshipping e o que que a gente tem em estoque
  … não precisa ficar aparente essa parte … para os clientes"*): `fulfillment` é `dropshipping` (o padrão: o fornecedor
  envia, vale a caixa "Em estoque") ou `estoque` (o box envia). Em estoque, o produto (ou cada opção) liga a um item do
  estoque interno (`store_product_stock`) e **quem diz se tem é o estoque**: um saldo só, o do Balcão, da contagem e de
  Compras, contado no Galpão e na Pista (o trailer de corrida fica fora). O site recebe só o "Out of stock" derivado:
  o marcador e a quantidade nunca saem de `catalogo` (o que o site, o carrinho e o Stripe leem).
"""
import hashlib
import json
import os
import re

from command_center.db import agora, atualizar, inserir, todos, um
from command_center.vitrine import html_seguro

MAX_PRECO = 100_000
MAX_FOTOS = 8
MAX_VARIACOES = 60
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
CAMPOS_JSON = ("images", "categories", "tags", "attributes", "variations")
FULFILLMENT = ("dropshipping", "estoque")          # #309: como vendemos (interno; o cliente nunca vê)
LOCAIS_DO_SITE = ("sede", "pista")                 # #309: Galpão + Pista (OKC) contam para o site; o trailer não
INTERNOS = ("fulfillment",)                        # #309: o que o painel lê e a saída pública tira


class ErroProduto(ValueError):
    pass


def pasta_fotos():
    """As fotos que a equipe sobe no painel: WebP ≤ 1600 px, sem EXIF, em ~/.urace/loja (fora do repositório)."""
    p = os.path.join(os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "loja")
    os.makedirs(p, mode=0o700, exist_ok=True)
    return p


# ------------------------------------------------------------------ leitura
def _produto(r):
    """A linha do banco no formato do `produtos.json` (o que o site desenha), mais o que é do painel."""
    p = dict(r)
    for k in CAMPOS_JSON:
        try:
            p[k] = json.loads(p[k] or "[]")
        except ValueError:
            p[k] = []
    return {"id": p["id"], "slug": p["slug"], "name": p["name"], "type": p["kind"], "price": p["price"] or 0.0,
            "regular": p["regular"] or 0.0, "on_sale": bool(p["on_sale"]), "price_min": p["price_min"],
            "price_max": p["price_max"], "short": p["short"] or "", "description": p["description"] or "",
            "images": p["images"], "categories": p["categories"], "tags": p["tags"], "attributes": p["attributes"],
            "variations": p["variations"], "in_stock": bool(p["in_stock"]), "sku": p["sku"] or "",
            "shipping_fee": p["shipping_fee"], "deposit": p["deposit"] or 0.0, "active": bool(p["active"]),
            "sort": p["sort"], "origin": p["origin"], "updated_at": p["updated_at"],
            "fulfillment": p.get("fulfillment") or "dropshipping"}


# ------------------------------------------------------------------ #309: o estoque do site
def opcoes(p):
    """Os nomes das opções do produto, como o pedido grava (`" / ".join(attrs)`); [""] = produto sem opção."""
    return [" / ".join(v["attrs"]) for v in p.get("variations") or ()] or [""]


def _sql_ligados(onde=""):
    marcas = ",".join("?" * len(LOCAIS_DO_SITE))
    return (f"""SELECT s.product_id, s.variation, s.item_id, s.created_at, i.name AS item_name, i.kind, i.tracking, i.unit,
                       i.active AS item_active, i.price AS item_price, p.slug, p.fulfillment, p.active AS product_active,
                       CASE WHEN i.active=0 THEN 0
                            WHEN i.tracking='serie' THEN
                              (SELECT COUNT(*) FROM stock_units u JOIN stock_locations lo ON lo.id=u.location_id
                                WHERE u.item_id=i.id AND u.client_id IS NULL AND u.status='disponivel' AND lo.code IN ({marcas}))
                            ELSE (SELECT COALESCE(SUM(l.qty), 0) FROM stock_levels l JOIN stock_locations lo ON lo.id=l.location_id
                                   WHERE l.item_id=i.id AND l.client_id IS NULL AND lo.code IN ({marcas})) END AS tem,
                       (SELECT MAX(m.at) FROM stock_moves m WHERE m.item_id=i.id AND m.kind='contagem') AS contado_em
                  FROM store_product_stock s JOIN stock_items i ON i.id=s.item_id JOIN store_products p ON p.id=s.product_id
                  {onde} ORDER BY s.product_id, s.variation"""), (*LOCAIS_DO_SITE, *LOCAIS_DO_SITE)


def ligados(con, pids=None):
    """{product_id: {opção: ligação}}: o item do estoque de cada produto/opção e quanto **da URACE** tem agora no Galpão
    e na Pista (peça de cliente nunca conta; item de série conta as unidades disponíveis). Uma consulta só."""
    onde, args = "", ()
    if pids is not None:
        pids = [int(x) for x in pids]
        if not pids:
            return {}
        onde = f"WHERE s.product_id IN ({','.join('?' * len(pids))})"
        args = tuple(pids)
    sql, locais = _sql_ligados(onde)
    out = {}
    for r in todos(con, sql, (*locais, *args)):
        r["tem"] = float(r["tem"] or 0)
        out.setdefault(r["product_id"], {})[r["variation"]] = r
    return out


def no_site(p, ls):
    """O que o site mostra (#309). Em estoque com item ligado, **quem diz se tem é o estoque**: sem uma unidade inteira, é
    "Out of stock" (o produto, ou a opção, que fica desativada). Sem item ligado, e no dropshipping, vale a caixa "Em
    estoque" do painel, como antes."""
    if p.get("fulfillment") != "estoque" or not ls:
        return p
    if not p["variations"]:
        l = ls.get("")
        return {**p, "in_stock": l["tem"] >= 1} if l else p
    vs, ligada_tem, solta_tem = [], False, False
    for v in p["variations"]:
        l = ls.get(" / ".join(v["attrs"]))
        if l:
            v = {**v, "in_stock": l["tem"] >= 1}
            ligada_tem = ligada_tem or v["in_stock"]
        else:
            solta_tem = solta_tem or bool(v.get("in_stock", True))
        vs.append(v)
    if not any(" / ".join(v["attrs"]) in ls for v in p["variations"]):
        return p
    return {**p, "variations": vs, "in_stock": ligada_tem or (bool(p["in_stock"]) and solta_tem)}


def publico(p):
    """A saída para o site, o carrinho e o Stripe: sem o marcador interno (o cliente nunca vê)."""
    return {k: v for k, v in p.items() if k not in INTERNOS}


def limites(con):
    """(endereço, opção) → quantas unidades inteiras o site pode vender agora: só produto em estoque com item ligado (o
    resto não tem limite). O carrinho e o "Buy now" conferem a quantidade aqui; o número nunca vai para o cliente."""
    sql, locais = _sql_ligados("WHERE p.fulfillment='estoque' AND p.active=1")
    return {(r["slug"], r["variation"]): int(float(r["tem"] or 0) + 1e-9) for r in todos(con, sql, locais)}


def catalogo(con):
    """Os produtos à venda (ativos), na ordem da loja. None quando a tabela nunca recebeu produto (o site cai no
    arquivo de antes); lista vazia quando a equipe escondeu todos. #309: o "Em estoque" já vem do estoque (no produto
    em estoque com item ligado) e o marcador interno fica de fora."""
    if not um(con, "SELECT 1 AS x FROM store_products LIMIT 1"):
        return None
    ls = ligados(con)
    return [publico(no_site(_produto(r), ls.get(r["id"])))
            for r in todos(con, "SELECT * FROM store_products WHERE active=1 ORDER BY sort, id")]


def do_site(con):
    """slug → produto à venda: o carrinho, o "Buy now" e o pedido. Tabela vazia (nunca importou): o arquivo de antes."""
    cat = catalogo(con)
    if cat is None:
        from command_center.vitrine.paginas_site import dados
        cat = dados("produtos.json")["produtos"]
    return {p["slug"]: p for p in cat}


def _ligacao(l):
    """A ligação como o painel mostra: o item, quanto tem (Galpão + Pista, da URACE) e a última contagem."""
    return {"variation": l["variation"], "item_id": l["item_id"], "item": l["item_name"], "kind": l["kind"],
            "tracking": l["tracking"], "unit": l["unit"], "tem": l["tem"], "ativo": bool(l["item_active"]),
            "preco_balcao": l["item_price"], "contado_em": l["contado_em"]}


def com_estoque(p, ls):
    """O produto do painel com o estoque dele (#309): cada ligação, o que o site mostra agora e a soma do que tem."""
    ls = ls or {}
    site = no_site(p, ls)
    return {**p, "estoque": {
        "ligados": {k: _ligacao(l) for k, l in ls.items()},
        "no_site": bool(site["in_stock"]),
        "opcoes_no_site": [bool(v.get("in_stock", True)) for v in site["variations"]],
        "tem": round(sum(l["tem"] for k, l in ls.items() if k in opcoes(p)), 4) if ls else None}}


def do_painel(con, pid):
    r = um(con, "SELECT * FROM store_products WHERE id=?", (pid,))
    if not r:
        return None
    return com_estoque(_produto(r), ligados(con, [r["id"]]).get(r["id"]))


def categorias_da_loja(p):
    """As categorias da loja em que o produto aparece (as do WooCommerce sem página caem na equivalente; sem
    nenhuma, o site põe em Parts): o que o painel mostra marcado."""
    from command_center.vitrine.paginas_site import ALIAS_LOJA, CATEGORIAS_LOJA
    nomes = dict(CATEGORIAS_LOJA)
    slugs = list(dict.fromkeys(ALIAS_LOJA.get(c["slug"], c["slug"]) for c in p["categories"]))
    return [s for s in slugs if s in nomes] or ["parts"]


def lista(con, termo="", categoria=None, ativos=None, limit=50, offset=0):
    """O que o painel lista: busca por nome, SKU ou endereço; categoria; ativos/escondidos. Paginado no servidor."""
    onde, args = [], []
    t = re.sub(r"\s+", " ", (termo or "").strip())[:80]
    if t:
        onde.append("(LOWER(name) LIKE ? OR LOWER(COALESCE(sku,'')) LIKE ? OR slug LIKE ?)")
        args += [f"%{t.lower()}%"] * 3
    if categoria:                                         # a categoria da loja e as do WooCommerce que caem nela
        from command_center.vitrine.paginas_site import ALIAS_LOJA
        slugs = [categoria] + [k for k, v in ALIAS_LOJA.items() if v == categoria]
        onde.append("(" + " OR ".join("categories LIKE ?" for _ in slugs) + ")")
        args += [f'%"slug": "{s}"%' for s in slugs]
    if ativos is not None:
        onde.append("active=?")
        args.append(1 if ativos else 0)
    w = (" WHERE " + " AND ".join(onde)) if onde else ""
    total = um(con, f"SELECT COUNT(*) AS n FROM store_products{w}", tuple(args))["n"]
    limit, offset = max(1, min(int(limit), 200)), max(0, int(offset))
    rs = todos(con, f"SELECT * FROM store_products{w} ORDER BY active DESC, sort, id LIMIT ? OFFSET ?", (*args, limit, offset))
    ls = ligados(con, [r["id"] for r in rs])
    return {"produtos": [com_estoque(_produto(r), ls.get(r["id"])) for r in rs], "total": total, "limit": limit, "offset": offset}


def categorias():
    """As categorias que têm página na loja (as que o painel oferece)."""
    from command_center.vitrine.paginas_site import CATEGORIAS_LOJA
    return [{"slug": s, "name": n} for s, n in CATEGORIAS_LOJA]


# ------------------------------------------------------------------ validação
def _texto(v, n):
    return re.sub(r"\s+", " ", str(v or "").strip())[:n] or None


def valor(v, campo, vazio=None):
    """'719' · '719.9' · '$1,856.90' → float. Vazio → `vazio` (None no frete: combinar à parte)."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return vazio
    if isinstance(v, bool):
        raise ErroProduto(f"{campo}: use números, como 25 ou 25.90")
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        t = re.sub(r"[\s$]", "", str(v)).replace(",", "")
        if not re.fullmatch(r"\d+(\.\d{1,2})?", t):
            raise ErroProduto(f"{campo}: use números, como 25 ou 25.90")
        n = float(t)
    if not 0 <= n <= MAX_PRECO:
        raise ErroProduto(f"{campo}: de 0 a {MAX_PRECO:,}")
    return round(n, 2)


def _html(v, campo):
    h = html_seguro.limpar(v)
    if len(h) > html_seguro.MAX:
        raise ErroProduto(f"{campo}: texto longo demais (até {html_seguro.MAX:,} caracteres)")
    return h


def slug_de(nome):
    import unicodedata
    t = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:80]


def _foto_ok(src):
    """Só foto que o site tem: as copiadas do WooCommerce (static/img) ou as que a equipe subiu (/store/img/…)."""
    from command_center.vitrine.paginas import STATIC
    if re.fullmatch(r"/store/img/[a-z0-9-]+\.webp", src or ""):
        return os.path.isfile(os.path.join(pasta_fotos(), src.rsplit("/", 1)[1]))
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,150}\.(webp|jpg|jpeg|png)", src or "") and ".." not in src:
        return os.path.isfile(os.path.join(STATIC, "img", src))
    return False


def _fotos(v):
    if not isinstance(v, list):
        raise ErroProduto("fotos: lista inválida")
    out = []
    for i in v[:MAX_FOTOS]:
        src = str((i or {}).get("src") or "")
        if not _foto_ok(src):
            raise ErroProduto("foto que o site não tem: suba a foto pelo painel")
        out.append({"src": src, "alt": _texto((i or {}).get("alt"), 160) or ""})
    return out


def _variacoes(v, atual):
    """[{attrs: ["Size"], price, promo, in_stock}] → o formato do site. O id da variação do WooCommerce fica."""
    if not isinstance(v, list):
        raise ErroProduto("variações: lista inválida")
    if len(v) > MAX_VARIACOES:
        raise ErroProduto(f"até {MAX_VARIACOES} variações")
    ids = {" / ".join(x.get("attrs") or []): x.get("id") for x in atual or []}
    out, vistas = [], set()
    for x in v:
        x = x or {}
        attrs = [a for a in (_texto(a, 60) for a in (x.get("attrs") or [])) if a]
        if not attrs:
            raise ErroProduto("cada variação precisa do nome da opção (ex.: M, Blue / 2)")
        nome = " / ".join(attrs)
        if nome.lower() in vistas:
            raise ErroProduto(f"variação repetida: {nome}")
        vistas.add(nome.lower())
        cheio = valor(x.get("regular", x.get("price")), f"preço de {nome}", vazio=0.0)
        promo = valor(x.get("promo"), f"preço promocional de {nome}") if "promo" in x else None
        if promo is not None and promo > cheio:
            raise ErroProduto(f"{nome}: o preço promocional é maior que o preço")
        cobra = promo if promo is not None else cheio
        out.append({"id": ids.get(nome), "attrs": attrs, "price": cobra, "regular": cheio,
                    "in_stock": bool(x.get("in_stock", True))})
    return out


def _derivar(vs, price, regular, nomes):
    """O que sai dos outros campos: tipo, faixa de preço, promoção e as escolhas do select. Igual ao que o
    WooCommerce publicava: com variações, o preço do produto é o menor delas."""
    if not vs:
        return {"kind": "simple", "price": price, "regular": regular, "price_min": None, "price_max": None,
                "on_sale": 1 if regular and price < regular else 0, "attributes": []}
    cobrados = [v["price"] for v in vs if v.get("price")]
    termos = []
    for v in vs:
        for i, a in enumerate(v["attrs"]):
            while len(termos) <= i:
                termos.append([])
            if a not in termos[i]:
                termos[i].append(a)
    lo = min(cobrados) if cobrados else 0.0
    return {"kind": "variable", "price": lo, "regular": min((v["regular"] for v in vs if v.get("regular")), default=lo),
            "price_min": lo if cobrados else None, "price_max": max(cobrados) if cobrados else None,
            "on_sale": 1 if any(v.get("regular") and v["price"] < v["regular"] for v in vs) else 0,
            "attributes": [{"name": (nomes[i] if i < len(nomes) and nomes[i] else "Option"), "terms": t}
                           for i, t in enumerate(termos)]}


def _dados(con, d, atual=None):
    parcial = atual is not None
    a = atual or {}
    c = {}
    if not parcial or "name" in d:
        nome = _texto(d.get("name"), 120)
        if not nome or len(nome) < 2:
            raise ErroProduto("dê um nome ao produto (o cliente lê, em inglês)")
        c["name"] = nome
    if not parcial:
        slug = slug_de(d.get("slug") or c["name"])
        if not slug or not SLUG.fullmatch(slug):
            raise ErroProduto("endereço inválido: use letras, números e hífen")
        if um(con, "SELECT 1 AS x FROM store_products WHERE slug=?", (slug,)):
            raise ErroProduto(f"já existe um produto no endereço /store/p/{slug}/")
        c["slug"] = slug
    if "short" in d:
        c["short"] = _html(d.get("short"), "resumo")
    if "description" in d:
        c["description"] = _html(d.get("description"), "descrição")
    if "images" in d:
        c["images"] = _fotos(d.get("images"))
    if "categories" in d:
        nomes = {x["slug"]: x["name"] for x in categorias()}
        cats = [s for s in (d.get("categories") or []) if s in nomes]
        if not cats:
            raise ErroProduto("escolha ao menos uma categoria da loja")
        c["categories"] = [{"slug": s, "name": nomes[s]} for s in dict.fromkeys(cats)]
    elif not parcial:
        c["categories"] = [{"slug": "parts", "name": "Parts"}]
    if "in_stock" in d and d["in_stock"] is not None:
        c["in_stock"] = 1 if d["in_stock"] else 0
    if "fulfillment" in d and d["fulfillment"] is not None:       # #309: interno, o cliente nunca vê
        if d["fulfillment"] not in FULFILLMENT:
            raise ErroProduto("como vendemos: dropshipping ou em estoque")
        c["fulfillment"] = d["fulfillment"]
    if "sku" in d:
        c["sku"] = _texto(d.get("sku"), 60)
    if "shipping_fee" in d:
        c["shipping_fee"] = valor(d.get("shipping_fee"), "frete")
    if "deposit" in d:
        c["deposit"] = valor(d.get("deposit"), "depósito", vazio=0.0)
    if "active" in d and d["active"] is not None:
        c["active"] = 1 if d["active"] else 0
    if "sort" in d and d["sort"] is not None:
        c["sort"] = int(d["sort"])
    # o preço: "Preço" (cheio) e "Preço promocional" (o que se cobra, opcional); com variações, o de cada uma
    if parcial and not ({"regular", "promo", "variations", "attribute_names"} & set(d)):
        return c
    cheio = valor(d["regular"], "preço", vazio=0.0) if "regular" in d else a.get("regular", 0.0)
    if "promo" in d:
        promo = valor(d.get("promo"), "preço promocional")
    else:
        promo = a["price"] if parcial and a.get("price", 0) < a.get("regular", 0) else None
    if promo is not None and promo > cheio:
        raise ErroProduto("o preço promocional é maior que o preço")
    vs = _variacoes(d["variations"], a.get("variations")) if "variations" in d else (a.get("variations") or [])
    if "attribute_names" in d:
        nomes = [_texto(n, 60) or "Option" for n in (d.get("attribute_names") or [])][:5]
    else:
        nomes = [x["name"] for x in a.get("attributes") or []]
    if "variations" in d:
        c["variations"] = vs
    c.update(_derivar(vs, promo if promo is not None else cheio, cheio, nomes))
    if not vs and parcial and "attribute_names" not in d and "variations" not in d:
        c.pop("attributes")                               # produto simples: as escolhas de antes ficam como estão
    return c


def _gravavel(c):
    return {k: (json.dumps(v, ensure_ascii=False) if k in CAMPOS_JSON else v) for k, v in c.items()}


def criar(con, por, d):
    c = _dados(con, d)
    c.setdefault("in_stock", 1)
    if "sort" not in c:
        ult = um(con, "SELECT COALESCE(MAX(sort), 0) AS s FROM store_products")
        c["sort"] = (ult["s"] or 0) + 10
    return inserir(con, "store_products", **_gravavel(c), origin="painel", updated_by=por, updated_at=agora())


def _comparavel(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (list, dict)) else v


def mudar(con, por, pid, d):
    """Devolve {campo: (antes, depois)} — vai para a auditoria (texto longo entra só como 'mudou')."""
    atual = do_painel(con, pid)
    if not atual:
        raise ErroProduto("produto não existe")
    bruto = dict(um(con, "SELECT * FROM store_products WHERE id=?", (pid,)))
    c = _gravavel(_dados(con, d, atual={**atual, "kind": bruto["kind"]}))
    mud = {k: (bruto[k], v) for k, v in c.items() if _comparavel(bruto[k]) != _comparavel(v) and str(bruto[k]) != str(v)}
    if mud:
        atualizar(con, "store_products", pid, **{k: v for k, (_, v) in mud.items()}, updated_by=por, updated_at=agora())
    return {k: (("…", "mudou") if k in ("short", "description", *CAMPOS_JSON) else ab) for k, ab in mud.items()}


# ------------------------------------------------------------------ fotos
def guardar_foto(con, por, pid, dados, alt=""):
    """Foto do celular ou do computador → WebP ≤ 1600 px, sem EXIF, e entra no fim das fotos do produto."""
    from command_center.providers import imagem
    p = do_painel(con, pid)
    if not p:
        raise ErroProduto("produto não existe")
    if len(p["images"]) >= MAX_FOTOS:
        raise ErroProduto(f"até {MAX_FOTOS} fotos por produto")
    try:
        webp, ext = imagem.comprimir(dados)
    except imagem.ImagemInvalida as e:
        raise ErroProduto(str(e))
    nome = f"{int(pid)}-{hashlib.sha256(webp).hexdigest()[:16]}{ext}"
    caminho = os.path.join(pasta_fotos(), nome)
    with open(caminho, "wb") as f:
        f.write(webp)
    os.chmod(caminho, 0o644)
    fotos = p["images"] + [{"src": f"/store/img/{nome}", "alt": _texto(alt, 160) or p["name"]}]
    atualizar(con, "store_products", pid, images=json.dumps(fotos, ensure_ascii=False), updated_by=por, updated_at=agora())
    return fotos


def arquivo_da_foto(nome):
    """O arquivo de uma foto subida no painel (para a rota pública /store/img/<nome>), ou None."""
    if not re.fullmatch(r"[0-9]+-[0-9a-f]{16}\.webp", nome or ""):
        return None
    caminho = os.path.join(pasta_fotos(), nome)
    return caminho if os.path.isfile(caminho) else None


# ------------------------------------------------------------------ frete e depósito
def frete(p, quantidade, entrega):
    """O frete de uma linha: o fixo do produto × quantidade com "Ship to me". None = combinar à parte."""
    if entrega != "envio":
        return 0.0
    fee = (p or {}).get("shipping_fee")
    return None if fee is None else round(float(fee) * int(quantidade), 2)

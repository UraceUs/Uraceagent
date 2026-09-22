"""Catálogo do fornecedor — ler o que dá para comprar, sem raspar HTML quando não precisa.

O dono pediu (22/09) um raspador do `cometkartsales.com`, para usar os SKUs deles como
referência de compra. Raspar HTML é a **pior** das opções disponíveis, e este módulo só
chega nela por último:

1. **JSON da própria loja.** Shopify publica `/products.json`; BigCommerce e outras têm
   endpoints parecidos. Vem com SKU limpo, paginado, e é servido de propósito.
2. **JSON-LD dentro da página.** Praticamente toda loja publica `schema.org/Product` num
   `<script type="application/ld+json">` — é o que o Google lê. Estruturado e estável.
3. **HTML na unha.** Só se os dois acima não existirem. Quebra quando mudam o layout, e
   é por isso que fica em último lugar.

O núcleo aqui **não toca a rede**: recebe bytes e devolve produtos. Isso é o que permite
testar o entendimento do catálogo sem bater no site de ninguém. Quem busca é
`adminai/importar_comet.py`, que respeita `robots.txt`, se identifica e vai devagar.

Nada aqui apaga: produto que sumiu do catálogo é marcado com `gone_at`, porque o
histórico de compra continua apontando para ele.
"""
import json
import re
from html.parser import HTMLParser

from command_center.db import agora, inserir, todos, um

PADRAO = "comet"


def _texto(v):
    return None if v is None else str(v).strip() or None


def _preco(v):
    """'$129.95' · '129.95' · 12995 (centavos, Shopify às vezes) → float."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"\d[\d.,]*", str(v))
    if not m:
        return None
    n = m.group(0)
    # 1.234,56 (vírgula decimal) vs 1,234.56 (ponto decimal): manda o ÚLTIMO separador.
    ult_v, ult_p = n.rfind(","), n.rfind(".")
    if ult_v > ult_p:
        n = n.replace(".", "").replace(",", ".")
    else:
        n = n.replace(",", "")
    try:
        return float(n)
    except ValueError:
        return None


# ------------------------------------------------------------------ 1. JSON da loja
def do_shopify(dados, base=""):
    """`/products.json` do Shopify: um produto pode ter várias variantes, e **o SKU mora
    na variante**, não no produto. Tratar produto como unidade perderia tamanho e cor."""
    if isinstance(dados, (bytes, str)):
        dados = json.loads(dados)
    saida = []
    for p in dados.get("products", []) or []:
        handle = p.get("handle") or ""
        url = f"{base.rstrip('/')}/products/{handle}" if base and handle else None
        imagens = p.get("images") or []
        img = (imagens[0] or {}).get("src") if imagens else None
        variantes = p.get("variants") or []
        for v in variantes:
            sku = _texto(v.get("sku"))
            if not sku:
                continue          # sem SKU não serve de referência de compra
            nome = _texto(p.get("title")) or ""
            titulo_v = _texto(v.get("title"))
            if titulo_v and titulo_v.lower() not in ("default title", "default"):
                nome = f"{nome} — {titulo_v}"
            saida.append({
                "sku": sku, "name": nome, "url": url,
                "price": _preco(v.get("price")),
                "brand": _texto(p.get("vendor")),
                "category": _texto(p.get("product_type")),
                "available": 1 if v.get("available") else 0,
                "image_url": img,
                "raw": json.dumps({"product": p.get("id"), "variant": v}, ensure_ascii=False)[:20000],
            })
    return saida


# ------------------------------------------------------------------ 2. JSON-LD
class _Scripts(HTMLParser):
    """Só os `<script type="application/ld+json">`. Regex em HTML erra com `>` dentro de
    atributo; o parser da biblioteca padrão não."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocos, self._pegando = [], False

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "script":
            tipo = dict(attrs).get("type", "") or ""
            self._pegando = "ld+json" in tipo.lower()

    def handle_endtag(self, tag):
        if tag.lower() == "script":
            self._pegando = False

    def handle_data(self, data):
        if self._pegando and data.strip():
            self.blocos.append(data.strip())


def _achatar(no):
    """JSON-LD vem em árvore, lista, ou `@graph`. Devolve todo dicionário lá dentro."""
    if isinstance(no, list):
        for x in no:
            yield from _achatar(x)
    elif isinstance(no, dict):
        yield no
        for chave in ("@graph", "itemListElement", "hasVariant"):
            if chave in no:
                yield from _achatar(no[chave])


def do_jsonld(html, url=None):
    """`schema.org/Product` dentro da página — o que o Google lê."""
    p = _Scripts()
    try:
        p.feed(html.decode("utf-8", "replace") if isinstance(html, bytes) else html)
    except Exception:
        return []
    saida = []
    for bloco in p.blocos:
        try:
            dados = json.loads(bloco)
        except (ValueError, TypeError):
            continue
        for no in _achatar(dados):
            tipos = no.get("@type") or ""
            tipos = [tipos] if isinstance(tipos, str) else list(tipos)
            if not any(str(t).lower() == "product" for t in tipos):
                continue
            ofertas = no.get("offers") or {}
            ofertas = ofertas[0] if isinstance(ofertas, list) and ofertas else ofertas
            ofertas = ofertas if isinstance(ofertas, dict) else {}
            sku = _texto(no.get("sku")) or _texto(no.get("mpn")) or _texto(ofertas.get("sku"))
            nome = _texto(no.get("name"))
            if not sku or not nome:
                continue
            marca = no.get("brand")
            marca = _texto(marca.get("name")) if isinstance(marca, dict) else _texto(marca)
            img = no.get("image")
            img = img[0] if isinstance(img, list) and img else img
            disp = str(ofertas.get("availability") or "").lower()
            saida.append({
                "sku": sku, "name": nome,
                "url": _texto(no.get("url")) or _texto(ofertas.get("url")) or url,
                "price": _preco(ofertas.get("price")),
                "currency": _texto(ofertas.get("priceCurrency")) or "USD",
                "brand": marca,
                "category": _texto(no.get("category")),
                "available": None if not disp else (0 if "outofstock" in disp.replace(" ", "") else 1),
                "image_url": _texto(img) if isinstance(img, str) else None,
                "raw": json.dumps(no, ensure_ascii=False)[:20000],
            })
    return saida


# ------------------------------------------------------------------ sitemap
def urls_do_sitemap(xml, filtro=None):
    """`<loc>` de sitemap e de índice de sitemaps. `filtro` corta o que não é produto."""
    txt = xml.decode("utf-8", "replace") if isinstance(xml, bytes) else xml
    achados = [u.strip() for u in re.findall(r"<loc>\s*(.*?)\s*</loc>", txt, re.I | re.S)]
    if filtro:
        achados = [u for u in achados if filtro in u]
    vistos, saida = set(), []
    for u in achados:                      # sitemap grande repete; ordem importa para retomar
        if u not in vistos:
            vistos.add(u)
            saida.append(u)
    return saida


# ------------------------------------------------------------------ gravar
def salvar(con, produtos, supplier=PADRAO, marcar_sumidos=False):
    """Grava o catálogo. **Nunca apaga.**

    `marcar_sumidos` só vale quando a varredura foi COMPLETA: marcar com base numa
    varredura parcial diria que sumiu metade do catálogo. Por isso o padrão é não marcar,
    e quem varre inteiro pede explicitamente.
    """
    novos = atualizados = 0
    vistos = set()
    for p in produtos:
        sku = _texto(p.get("sku"))
        nome = _texto(p.get("name"))
        if not sku or not nome:
            continue
        vistos.add(sku)
        ja = um(con, "SELECT * FROM supplier_products WHERE supplier=? AND sku=?", (supplier, sku))
        campos = {"name": nome, "url": p.get("url"), "price": p.get("price"),
                  "currency": p.get("currency") or "USD", "brand": p.get("brand"),
                  "category": p.get("category"), "available": p.get("available"),
                  "image_url": p.get("image_url"), "raw": p.get("raw"),
                  "last_seen_at": agora(), "gone_at": None}
        if ja:
            # Campo que não veio nesta passada não apaga o que já se sabia.
            campos = {k: v for k, v in campos.items()
                      if v is not None or k in ("gone_at", "last_seen_at")}
            sets = ", ".join(f"{k}=?" for k in campos)
            con.execute(f"UPDATE supplier_products SET {sets} WHERE id=?",
                        (*campos.values(), ja["id"]))
            atualizados += 1
        else:
            inserir(con, "supplier_products", supplier=supplier, sku=sku, **campos)
            novos += 1
    sumidos = 0
    if marcar_sumidos and vistos:
        marcas = ",".join("?" * len(vistos))
        cur = con.execute(
            f"UPDATE supplier_products SET gone_at=? WHERE supplier=? AND gone_at IS NULL "
            f"AND sku NOT IN ({marcas})", (agora(), supplier, *vistos))
        sumidos = cur.rowcount or 0
    return {"novos": novos, "atualizados": atualizados, "sumidos": sumidos,
            "vistos": len(vistos)}


def ligar_no_estoque(con, supplier=PADRAO):
    """Preenche nome e link do fornecedor nos itens de estoque que têm SKU dele.

    Só completa o que está vazio: o nome que a equipe deu ao item no painel é o nome
    que a equipe usa, e sobrescrever isso com o nome de catálogo seria trocar a língua
    da casa pela do fornecedor.
    """
    ligados = 0
    for i in todos(con, "SELECT * FROM stock_items WHERE sku IS NOT NULL AND supplier=?", (supplier,)):
        p = um(con, "SELECT * FROM supplier_products WHERE supplier=? AND sku=?", (supplier, i["sku"]))
        if not p:
            continue
        if not i["supplier_url"] and p["url"]:
            con.execute("UPDATE stock_items SET supplier_url=? WHERE id=?", (p["url"], i["id"]))
            ligados += 1
    return ligados


def sem_cadastro(con, supplier=PADRAO):
    """SKU que o estoque usa e o catálogo não conhece — erro de digitação ou peça que
    saiu de linha. Vale olhar antes de o módulo de compras tentar pedir."""
    return todos(con, """SELECT i.id, i.name, i.sku FROM stock_items i
                          WHERE i.sku IS NOT NULL AND i.supplier=? AND i.active=1
                            AND NOT EXISTS (SELECT 1 FROM supplier_products p
                                             WHERE p.supplier=i.supplier AND p.sku=i.sku)""",
                 (supplier,))

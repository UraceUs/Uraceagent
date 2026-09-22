"""Ler o catálogo do fornecedor sem bater no site de ninguém.

O núcleo recebe bytes e devolve produtos — é isso que permite provar que entendemos o
formato sem fazer uma requisição sequer. O que toca a rede (`adminai/importar_comet.py`)
é só educação: robots.txt, pausa, cache.
"""
import json
import os
import tempfile

import pytest

from command_center.db import aplicar_schema, conectar, inserir, todos, um
from command_center.providers import estoque, fornecedor


@pytest.fixture()
def con():
    antes = os.environ.get("CC_DB_PATH")
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="cc-forn-"), "cc.sqlite")
    c = conectar(); aplicar_schema(c)
    try:
        yield c
    finally:
        c.close()
        if antes is None:
            os.environ.pop("CC_DB_PATH", None)
        else:
            os.environ["CC_DB_PATH"] = antes


SHOPIFY = {"products": [
    {"id": 1, "title": "MG Yellow Tire", "handle": "mg-yellow", "vendor": "MG",
     "product_type": "Tires", "images": [{"src": "https://x/img.jpg"}],
     "variants": [
         {"id": 11, "sku": "MG-YEL-F", "title": "Front", "price": "129.95", "available": True},
         {"id": 12, "sku": "MG-YEL-R", "title": "Rear", "price": "149.95", "available": False}]},
    {"id": 2, "title": "KA100 Piston", "handle": "ka100-piston", "vendor": "IAME",
     "product_type": "Engine Parts",
     "variants": [{"id": 21, "sku": "IAME-KA-PIS", "title": "Default Title",
                   "price": "89.00", "available": True}]},
    {"id": 3, "title": "Sem SKU", "handle": "x", "variants": [{"id": 31, "sku": "", "price": "1"}]},
]}


def test_o_sku_mora_na_variante_nao_no_produto():
    """Um produto com duas variantes são DOIS SKU. Tratar produto como unidade perderia
    tamanho e cor — e a compra pediria a peça errada."""
    p = fornecedor.do_shopify(SHOPIFY, base="https://cometkartsales.com")
    assert [x["sku"] for x in p] == ["MG-YEL-F", "MG-YEL-R", "IAME-KA-PIS"]
    assert p[0]["name"] == "MG Yellow Tire — Front"
    assert p[0]["price"] == 129.95 and p[0]["available"] == 1
    assert p[1]["available"] == 0


def test_variante_unica_nao_ganha_o_sufixo_inutil():
    """"Default Title" é ruído do Shopify, não o nome da variante."""
    p = fornecedor.do_shopify(SHOPIFY)
    assert [x for x in p if x["sku"] == "IAME-KA-PIS"][0]["name"] == "KA100 Piston"


def test_produto_sem_sku_nao_entra():
    """Sem SKU não serve de referência de compra, que é a única função deste catálogo."""
    assert all(x["sku"] for x in fornecedor.do_shopify(SHOPIFY))


def test_o_link_do_produto_sai_montado():
    p = fornecedor.do_shopify(SHOPIFY, base="https://cometkartsales.com/")
    assert p[0]["url"] == "https://cometkartsales.com/products/mg-yellow"


JSONLD = """<!doctype html><html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
 {"@type":"BreadcrumbList","itemListElement":[]},
 {"@type":"Product","sku":"CKS-4412","name":"Tillotson Carb Kit",
  "brand":{"@name":"x","name":"Tillotson"},"category":"Carburetor",
  "image":["https://x/1.jpg"],
  "offers":{"@type":"Offer","price":"64.99","priceCurrency":"USD",
            "availability":"https://schema.org/InStock",
            "url":"https://cometkartsales.com/p/cks-4412"}}]}
</script>
<script type="application/json">{"nao":"sou ld+json"}</script>
</head><body><p>preço na página: $999 (não é para ler daqui)</p></body></html>"""


def test_jsonld_e_lido_de_dentro_do_grafo():
    """JSON-LD vem em árvore, lista ou @graph. Product pode estar em qualquer nível."""
    p = fornecedor.do_jsonld(JSONLD)
    assert len(p) == 1
    assert p[0]["sku"] == "CKS-4412" and p[0]["name"] == "Tillotson Carb Kit"
    assert p[0]["price"] == 64.99 and p[0]["brand"] == "Tillotson"
    assert p[0]["available"] == 1 and p[0]["currency"] == "USD"


def test_jsonld_ignora_script_que_nao_e_ld_json():
    assert len(fornecedor.do_jsonld(JSONLD)) == 1, "não lê o application/json comum"


def test_fora_de_estoque_e_lido_como_tal():
    html = JSONLD.replace("InStock", "OutOfStock")
    assert fornecedor.do_jsonld(html)[0]["available"] == 0


def test_html_quebrado_nao_derruba_a_importacao():
    """Uma página ruim no meio de milhares não pode parar a varredura."""
    assert fornecedor.do_jsonld("<html><script type='application/ld+json'>{ isto não é json")== []
    assert fornecedor.do_jsonld("") == []


@pytest.mark.parametrize("bruto,esperado", [
    ("$129.95", 129.95), ("129,95", 129.95), ("$1,234.56", 1234.56),
    ("1.234,56", 1234.56), ("R$ 2.756,90", 2756.90), (89, 89.0), ("", None), (None, None),
    ("grátis", None),
])
def test_preco_le_as_duas_notacoes(bruto, esperado):
    """A Rate Card já ensinou isto apanhando: manda o ÚLTIMO separador."""
    assert fornecedor._preco(bruto) == esperado


SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>https://cometkartsales.com/products/a</loc></url>
<url><loc>https://cometkartsales.com/products/b</loc></url>
<url><loc>https://cometkartsales.com/products/a</loc></url>
<url><loc>https://cometkartsales.com/pages/sobre</loc></url></urlset>"""


def test_sitemap_nao_repete_url():
    assert fornecedor.urls_do_sitemap(SITEMAP).count("https://cometkartsales.com/products/a") == 1


def test_sitemap_filtra_o_que_nao_e_produto():
    u = fornecedor.urls_do_sitemap(SITEMAP, filtro="/products/")
    assert len(u) == 2 and all("/products/" in x for x in u)


# --------------------------------------------------------------- gravar sem apagar
def test_salvar_cria_e_atualiza_pelo_sku(con):
    fornecedor.salvar(con, fornecedor.do_shopify(SHOPIFY))
    assert um(con, "SELECT COUNT(*) n FROM supplier_products")["n"] == 3
    mudado = json.loads(json.dumps(SHOPIFY))
    mudado["products"][0]["variants"][0]["price"] = "139.95"
    r = fornecedor.salvar(con, fornecedor.do_shopify(mudado))
    assert (r["novos"], r["atualizados"]) == (0, 3)
    assert um(con, "SELECT price FROM supplier_products WHERE sku='MG-YEL-F'")["price"] == 139.95


def test_o_que_sumiu_do_catalogo_e_marcado_nunca_apagado(con):
    """O histórico de compra continua apontando para a peça que saiu de linha."""
    fornecedor.salvar(con, fornecedor.do_shopify(SHOPIFY))
    so_um = {"products": [SHOPIFY["products"][1]]}
    r = fornecedor.salvar(con, fornecedor.do_shopify(so_um), marcar_sumidos=True)
    assert r["sumidos"] == 2
    assert um(con, "SELECT COUNT(*) n FROM supplier_products")["n"] == 3, "nada foi apagado"
    assert um(con, "SELECT gone_at FROM supplier_products WHERE sku='MG-YEL-F'")["gone_at"]
    assert um(con, "SELECT gone_at FROM supplier_products WHERE sku='IAME-KA-PIS'")["gone_at"] is None


def test_varredura_parcial_nao_marca_ninguem_como_sumido(con):
    """A trava que importa: marcar com base numa varredura parcial diria que sumiu
    metade do catálogo. Por isso o padrão é NÃO marcar."""
    fornecedor.salvar(con, fornecedor.do_shopify(SHOPIFY))
    r = fornecedor.salvar(con, fornecedor.do_shopify({"products": [SHOPIFY["products"][1]]}))
    assert r["sumidos"] == 0
    assert um(con, "SELECT COUNT(*) n FROM supplier_products WHERE gone_at IS NOT NULL")["n"] == 0


def test_produto_que_voltou_deixa_de_estar_sumido(con):
    fornecedor.salvar(con, fornecedor.do_shopify(SHOPIFY))
    fornecedor.salvar(con, fornecedor.do_shopify({"products": [SHOPIFY["products"][1]]}),
                      marcar_sumidos=True)
    fornecedor.salvar(con, fornecedor.do_shopify(SHOPIFY))
    assert um(con, "SELECT gone_at FROM supplier_products WHERE sku='MG-YEL-F'")["gone_at"] is None


def test_campo_que_nao_veio_nao_apaga_o_que_ja_se_sabia(con):
    """Uma passada pelo JSON-LD sem categoria não pode zerar a categoria que o
    products.json já tinha trazido."""
    fornecedor.salvar(con, fornecedor.do_shopify(SHOPIFY))
    fornecedor.salvar(con, [{"sku": "MG-YEL-F", "name": "MG Yellow Tire — Front"}])
    assert um(con, "SELECT category FROM supplier_products WHERE sku='MG-YEL-F'")["category"] == "Tires"


# --------------------------------------------------------- a ponte com o estoque
def test_o_catalogo_completa_o_link_do_item_de_estoque(con):
    fornecedor.salvar(con, fornecedor.do_shopify(SHOPIFY, base="https://cometkartsales.com"))
    i = estoque.criar_item(con, "pneu", "Pneu dianteiro MG", sku="MG-YEL-F", unit="un")
    r = fornecedor.ligar_no_estoque(con)
    assert (r["casados"], r["links"], r["sem_par"]) == (1, 1, 0)
    assert um(con, "SELECT supplier_url FROM stock_items WHERE id=?", (i,))["supplier_url"] \
        == "https://cometkartsales.com/products/mg-yellow"


def test_casado_e_link_sao_coisas_diferentes(con):
    """"0 ligados" parecia defeito quando o SKU casava mas o catálogo não trazia URL.
    Casar é o que importa; o link é consequência."""
    fornecedor.salvar(con, [{"sku": "SEM-URL", "name": "Peça sem link no catálogo"}])
    estoque.criar_item(con, "peca", "Peça nossa", sku="SEM-URL")
    r = fornecedor.ligar_no_estoque(con)
    assert (r["casados"], r["links"]) == (1, 0)


def test_sku_que_nao_acha_par_e_contado_a_parte(con):
    fornecedor.salvar(con, fornecedor.do_shopify(SHOPIFY))
    estoque.criar_item(con, "peca", "SKU errado", sku="NAO-EXISTE")
    estoque.criar_item(con, "peca", "SKU certo", sku="IAME-KA-PIS")
    r = fornecedor.ligar_no_estoque(con)
    assert (r["casados"], r["sem_par"]) == (1, 1)


def test_o_nome_que_a_equipe_deu_ao_item_nao_e_sobrescrito(con):
    """Trocar o nome da casa pelo do catálogo seria trocar a língua da equipe pela do
    fornecedor. O mecânico procura "pneu dianteiro", não "MG Yellow Tire — Front"."""
    fornecedor.salvar(con, fornecedor.do_shopify(SHOPIFY, base="https://cometkartsales.com"))
    i = estoque.criar_item(con, "pneu", "Pneu dianteiro MG", sku="MG-YEL-F")
    fornecedor.ligar_no_estoque(con)
    assert um(con, "SELECT name FROM stock_items WHERE id=?", (i,))["name"] == "Pneu dianteiro MG"


def test_sku_que_o_estoque_usa_e_o_catalogo_nao_conhece_e_apontado(con):
    """Erro de digitação ou peça fora de linha — vale ver antes de a compra tentar pedir."""
    fornecedor.salvar(con, fornecedor.do_shopify(SHOPIFY))
    estoque.criar_item(con, "peca", "Peça com SKU errado", sku="MG-YEL-FF")
    estoque.criar_item(con, "peca", "Peça certa", sku="IAME-KA-PIS")
    assert [o["sku"] for o in fornecedor.sem_cadastro(con)] == ["MG-YEL-FF"]


def test_a_lista_de_reposicao_encontra_o_link_depois_da_importacao(con):
    """O caminho inteiro, ponta a ponta: catálogo importado → item ligado → falta pouco
    → o comprador recebe SKU e link. É esta a ponte para o módulo de compras."""
    fornecedor.salvar(con, fornecedor.do_shopify(SHOPIFY, base="https://cometkartsales.com"))
    i = estoque.criar_item(con, "pneu", "Pneu dianteiro MG", sku="MG-YEL-F", min_qty=8)
    estoque.entrada(con, i, qty=2)
    fornecedor.ligar_no_estoque(con)
    falta = estoque.abaixo_do_minimo(con)
    assert len(falta) == 1 and falta[0]["falta"] == 6
    assert falta[0]["sku"] == "MG-YEL-F"
    assert falta[0]["supplier_url"].endswith("/products/mg-yellow")

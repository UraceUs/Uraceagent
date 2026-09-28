"""Estoque, fase 2 — a primeira contagem da prateleira e o SKU ligado por gente.

Dono, 25/09: os 16 itens semeados das invoices apareciam como falta, todos com zero. O zero
era "ninguém contou", não "acabou". Daqui saem três regras:

- ficha **nunca contada** é um pedido de contagem, não de compra;
- a contagem da prateleira inteira é **tudo ou nada**, e o que ficou em branco fica como está;
- o SKU do fornecedor só é ligado por **gerente** e só se existir no catálogo.
"""
import os
import tempfile

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import atencao, auth, mcp_http  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, todos, um  # noqa: E402
from command_center.providers import estoque, fornecedor  # noqa: E402

B = "/ops/api/estoque"
SENHA = "senha-forte-123"


# ------------------------------------------------------------------ provider, banco novo
@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def test_ficha_sem_movimento_e_nunca_contada(con):
    a = estoque.criar_item(con, "peca", "Rear sprocket", min_qty=8)
    b = estoque.criar_item(con, "peca", "Rk Non Oring Chain", min_qty=6)
    assert [i["id"] for i in estoque.nunca_contados(con)] == [a, b]
    estoque.contar(con, a, 0)
    assert [i["id"] for i in estoque.nunca_contados(con)] == [b], "contar zero é contar"
    mov = estoque.ultimos_movimentos(con)
    assert mov[a]["contagem"] and b not in mov


def test_entrada_tambem_da_historia_mas_nao_e_contagem(con):
    a = estoque.criar_item(con, "peca", "Vela NGK", min_qty=2)
    estoque.entrada(con, a, qty=4)
    assert estoque.nunca_contados(con) == []
    assert estoque.ultimos_movimentos(con)[a]["contagem"] is None


def test_item_de_serie_e_inativo_nao_entram_na_folha(con):
    estoque.criar_item(con, "motor", "Motor IAME", tracking="serie")
    x = estoque.criar_item(con, "peca", "Peça aposentada")
    con.execute("UPDATE stock_items SET active=0 WHERE id=?", (x,))
    assert estoque.nunca_contados(con) == []


def test_atencao_pede_contagem_e_nao_manda_comprar_o_que_ninguem_contou(con):
    a = estoque.criar_item(con, "peca", "Rear sprocket", min_qty=8)
    b = estoque.criar_item(con, "peca", "Rk Non Oring Chain", min_qty=6)
    chaves = {i["key"]: i for i in atencao.coletar(con)}
    assert "estoque-contar:stock:primeira" in chaves
    assert "estoque-repor:stock:minimo" not in chaves, "zero de quem ninguém contou não é falta"
    estoque.contar(con, a, 3)                       # contado e abaixo do mínimo (8)
    chaves = {i["key"]: i for i in atencao.coletar(con)}
    assert chaves["estoque-repor:stock:minimo"]["title"].startswith("Repor Rear sprocket: faltam 5")
    assert "Rk Non Oring Chain" in chaves["estoque-contar:stock:primeira"]["facts"][0][1]
    estoque.contar(con, b, 10)
    estoque.contar(con, a, 9)
    chaves = {i["key"] for i in atencao.coletar(con)}
    assert not {k for k in chaves if k.startswith("estoque-")}


def test_conector_avisa_que_nunca_contado_nao_e_falta(con):
    a = estoque.criar_item(con, "peca", "Rear sprocket", min_qty=8)
    estoque.criar_item(con, "peca", "Rk Non Oring Chain", min_qty=6)
    estoque.contar(con, a, 3)
    r = mcp_http._f_estoque(con)
    assert {i["name"]: i["contado"] for i in r["itens"]} == {"Rear sprocket": True, "Rk Non Oring Chain": False}
    assert r["nunca_contados"] == ["Rk Non Oring Chain"] and "ninguém contou" in r["aviso"]
    assert mcp_http._f_resumo(con)["itens_nunca_contados"] == 1


# ------------------------------------------------------------------ sugestão de SKU
CATALOGO = [
    {"sku": "RK-219-108", "name": "RK 219 Non O-Ring Chain 108 Links", "brand": "RK", "url": "https://c/rk108", "price": 38.0},
    {"sku": "RK-219-106", "name": "RK 219 Non O-Ring Chain 106 Links", "brand": "RK", "url": "https://c/rk106", "price": 37.0},
    {"sku": "SPR-80", "name": "Rear Sprocket 80T", "brand": "Otk", "url": "https://c/spr80", "price": 26.0},
    {"sku": "OLD-108", "name": "Chain 108 discontinued", "brand": "X", "url": "https://c/old", "price": 1.0},
]


def _catalogo(con):
    fornecedor.salvar(con, CATALOGO)
    con.execute("UPDATE supplier_products SET gone_at='2026-09-01' WHERE sku='OLD-108'")


def test_numero_da_peca_pesa_mais_que_palavra(con):
    _catalogo(con)
    s = fornecedor.sugerir_sku(con, "Rk Non Oring Chain 108")
    assert s[0]["sku"] == "RK-219-108", "o 108 é o que separa uma corrente da outra"
    assert s[0]["score"] > s[1]["score"]


def test_produto_fora_do_catalogo_nao_e_sugerido(con):
    _catalogo(con)
    assert "OLD-108" not in {x["sku"] for x in fornecedor.sugerir_sku(con, "Chain 108")}


def test_sem_palavra_util_nao_sugere_nada(con):
    _catalogo(con)
    assert fornecedor.sugerir_sku(con, "kit de") == []
    assert fornecedor.sugerir_sku(con, "Pastilha Tonykart") == []


# ------------------------------------------------------------------ API
@pytest.fixture(scope="module")
def cli():
    pasta = tempfile.mkdtemp()
    os.environ["CC_DB_PATH"] = os.path.join(pasta, "cc.sqlite")
    os.environ["URACE_DIR"] = pasta
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "mec@urace.us", "Mecânico", "OPERATOR", SENHA)
    auth.criar_usuario(c, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    auth.criar_usuario(c, "olho@urace.us", "Visitante", "VIEWER", SENHA)
    _catalogo(c)
    c.close()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def _db():
    return conectar()


def _item(nome, **kw):
    c = _db()
    try:
        return estoque.criar_item(c, kw.pop("kind", "peca"), nome, **kw)
    finally:
        c.close()


def _saldo(iid, onde=None):
    c = _db()
    try:
        return estoque.saldo(c, iid, estoque.local(c, onde)["id"] if onde else None)
    finally:
        c.close()


def test_mecanico_conta_a_prateleira_e_o_em_branco_fica_como_esta(cli):
    a, b, c = _item("Pinhão 10T"), _item("Pinhão 11T"), _item("Pinhão 12T")
    h = entra(cli, "mec@urace.us")
    antes = cli.get(B, headers=h).json()
    assert {a, b, c} <= set(antes["a_contar"])
    r = cli.post(f"{B}/contagem", headers=h, json={"local": "sede", "itens": [
        {"item_id": a, "qty": 4}, {"item_id": b, "qty": 0}]})
    assert r.status_code == 200, r.text
    assert r.json()["contados"] == 2 and [x["item_id"] for x in r.json()["com_diferenca"]] == [a]
    assert _saldo(a) == 4 and _saldo(b) == 0
    depois = cli.get(B, headers=h).json()
    assert a not in depois["a_contar"] and b not in depois["a_contar"] and c in depois["a_contar"]
    linha = {i["id"]: i for i in depois["itens"]}
    assert linha[a]["contado"] and linha[a]["ultima_contagem"] and not linha[c]["contado"]
    aud = todos(_db(), "SELECT * FROM audit_logs WHERE event='stock.count' AND entity_id=?", (str(a),))
    assert len(aud) == 1 and '"lote": true' in aud[0]["detail"]


def test_contagem_com_uma_linha_ruim_nao_grava_nenhuma(cli):
    """Meia contagem gravada deixa o mecânico sem saber o que refazer."""
    a, motor = _item("Corrente 106"), _item("Motor X30", kind="motor", tracking="serie")
    h = entra(cli, "mec@urace.us")
    ruins = [{"item_id": motor, "qty": 1},            # número de série: confere-se unidade a unidade
             {"item_id": a + 10_000, "qty": 1},       # não existe
             {"item_id": _item("Arruela"), "qty": -1}]  # negativo
    for ruim in ruins:
        r = cli.post(f"{B}/contagem", headers=h, json={"itens": [{"item_id": a, "qty": 7}, ruim]})
        assert r.status_code == 400, r.text
        assert _saldo(a) == 0
    assert um(_db(), "SELECT COUNT(*) n FROM stock_moves WHERE item_id=?", (a,))["n"] == 0
    assert um(_db(), "SELECT COUNT(*) n FROM audit_logs WHERE event='stock.count' AND entity_id=?", (str(a),))["n"] == 0


def test_contagem_recusa_item_repetido_e_lista_vazia(cli):
    a = _item("Bucha")
    h = entra(cli, "mec@urace.us")
    assert cli.post(f"{B}/contagem", headers=h, json={"itens": [{"item_id": a, "qty": 1}, {"item_id": a, "qty": 2}]}).status_code == 400
    assert cli.post(f"{B}/contagem", headers=h, json={"itens": []}).status_code == 400
    assert _saldo(a) == 0


def test_contagem_no_trailer_nao_mexe_na_sede(cli):
    a = _item("Parafuso do para-choque")
    h = entra(cli, "mec@urace.us")
    assert cli.post(f"{B}/contagem", headers=h, json={"local": "trailer", "itens": [{"item_id": a, "qty": 5}]}).status_code == 200
    assert _saldo(a, "trailer") == 5 and _saldo(a, "sede") == 0


def test_visitante_nao_conta(cli):
    a = _item("Vela de ignição")
    h = entra(cli, "olho@urace.us")
    assert cli.post(f"{B}/contagem", headers=h, json={"itens": [{"item_id": a, "qty": 1}]}).status_code == 403
    assert _saldo(a) == 0


def test_mecanico_ve_sugestoes_mas_so_gerente_liga_o_sku(cli):
    a = _item("Rk Non Oring Chain 108")
    h = entra(cli, "mec@urace.us")
    s = cli.get(f"{B}/item/{a}/sku-sugestoes", headers=h).json()
    assert s["tem_catalogo"] and s["sugestoes"][0]["sku"] == "RK-219-108"
    assert cli.post(f"{B}/item/{a}/sku", headers=h, json={"sku": "RK-219-108"}).status_code == 403
    h = entra(cli, "ger@urace.us")
    r = cli.post(f"{B}/item/{a}/sku", headers=h, json={"sku": " RK-219-108 "})
    assert r.status_code == 200, r.text
    it = um(_db(), "SELECT * FROM stock_items WHERE id=?", (a,))
    assert it["sku"] == "RK-219-108" and it["supplier_url"] == "https://c/rk108"
    assert it["name"] == "Rk Non Oring Chain 108", "o nome da casa não muda"
    aud = um(_db(), "SELECT * FROM audit_logs WHERE event='stock.item.sku' AND entity_id=?", (str(a),))
    assert aud and "RK-219-108" in aud["detail"]


def test_sku_inventado_ou_fora_do_catalogo_e_recusado(cli):
    a = _item("Chain 108 velha")
    h = entra(cli, "ger@urace.us")
    for sku in ("NAO-EXISTE", "OLD-108"):
        assert cli.post(f"{B}/item/{a}/sku", headers=h, json={"sku": sku}).status_code == 400
    assert um(_db(), "SELECT sku FROM stock_items WHERE id=?", (a,))["sku"] is None
    assert cli.get(f"{B}/item/999999/sku-sugestoes", headers=h).status_code == 404

"""#187: etiqueta QR de prateleira para cada produto do QuickBooks e as duplicatas do catálogo.

Dono, 12/10: *"se tiver duplicata, identifica … normalmente tem produtos que são para chassis
diferentes … esses são produtos diferentes"* e *"monta uma arte com o QR Code e o nome da peça
em inglês … só de colocar a câmera em cima, já lê … e já vai somando ali na parte do balcão"*.
"""
import os
import sys

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, um  # noqa: E402
from command_center.providers import balcao, balcao_rapido, etiquetas  # noqa: E402
from command_center.tests.test_balcao import SENHA, QboFalso, entra  # noqa: E402

B = "/ops/api/balcao"
ITENS = [("615", "IAME Fiberglass Reed Petal", "Engine parts:IAME Fiberglass Reed Petal", 21.89, "NonInventory"),
         ("96", "IAME Mini Swift Clutch Cover", "Engine parts:IAME Mini Swift Clutch Cover", 57.56, "NonInventory"),
         ("1010000111", "IAME Mini Swift Clutch Cover", "IAME Mini Swift Clutch Cover", 0.0, "NonInventory"),
         ("107", "OTK Clamp for  32mm Torsion Bar", "OTK Parts:OTK Clamp for  32mm Torsion Bar", 27.5, "NonInventory"),
         ("108", "OTK Clamp for 30mm Torsion Bar", "OTK Parts:OTK Clamp for 30mm Torsion Bar", 30.79, "NonInventory"),
         ("501", "Brake pad Parolin Micro/Mini", "Parts:Brake pad Parolin Micro/Mini", 39.9, "NonInventory"),
         ("505", "Compkart brake pad", "Parts:Compkart brake pad", 48.99, "NonInventory"),
         ("1010000172", "Parts", "Parts", None, "Category"),
         ("844", "Corporate Event | 1 session", "Corporate Event | 1 session", 390.0, "Service"),
         ("9001", "Rotax Engine Junior Max Evo", "Rental:Rotax Engine Junior Max Evo", 3395.0, "NonInventory")]


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    c = conectar(); aplicar_schema(c)
    for i in ITENS:
        c.execute("INSERT INTO qbo_items (id, name, full_name, price, type, active) VALUES (?,?,?,?,?,1)", i)
    yield c
    c.close()


# ------------------------------------------------------------------ o catálogo e as duplicatas
def test_so_produto_fisico_vira_etiqueta(con):
    ids = [p["id"] for p in etiquetas.produtos(con)]
    assert "1010000172" not in ids and "844" not in ids, "categoria e serviço ficam fora"
    assert "9001" not in ids, "aluguel não vai para a prateleira"
    assert set(ids) == {"615", "96", "1010000111", "107", "108", "501", "505"}
    p = next(p for p in etiquetas.produtos(con) if p["id"] == "615")
    assert (p["codigo"], p["categoria"], p["name"]) == ("URQ615", "Engine parts", "IAME Fiberglass Reed Petal")
    assert [p["id"] for p in etiquetas.produtos(con, ["OTK Parts"])] == ["107", "108"]
    assert {c["nome"]: c["itens"] for c in etiquetas.categorias(con)} == {"Engine parts": 2, "OTK Parts": 2, "Parts": 2, "": 1}


def test_duplicata_e_o_mesmo_produto_e_chassi_ou_medida_diferente_nao_e(con):
    grupos = etiquetas.duplicatas(etiquetas.produtos(con))
    assert [sorted(p["id"] for p in g["itens"]) for g in grupos] == [["1010000111", "96"]]
    assert grupos[0]["motivo"] == "mesmo nome"
    nomes = ["10ft Half Wall", "10ft Half Walls", "OTK Clamp for 30mm Torsion Bar", "OTK Flat Torsion Bar Clamp 30mm",
             "Front sprocket Z11", "Mini Rok front sprocket Z11", "Front sprocket Z12", "Chassis parolin opportunity 2024",
             "Parolin opportunity 2023", "Bumper saver kit", "OTK Bumper Saver kit", "Bumper Saver Senzo"]
    g = etiquetas.duplicatas([{"id": str(i), "name": n} for i, n in enumerate(nomes)])
    juntos = sorted(sorted(p["name"] for p in x["itens"]) for x in g)
    assert juntos == [["10ft Half Wall", "10ft Half Walls"], ["OTK Clamp for 30mm Torsion Bar", "OTK Flat Torsion Bar Clamp 30mm"]]


# ------------------------------------------------------------------ o balcão lê o QR
def test_qr_da_prateleira_liga_a_peca_ao_quickbooks_na_primeira_leitura(con):
    r = balcao.ler(con, "URQ615")
    assert r["tipo"] == "peca" and r["item"]["name"] == "IAME Fiberglass Reed Petal"
    assert (r["item"]["qbo_item_id"], r["item"]["price"]) == ("615", 21.89)
    assert r["item"]["codigos"] == ["URQ615"]
    de_novo = balcao.ler(con, "urq615 ".upper())
    assert de_novo["item"]["id"] == r["item"]["id"], "a segunda leitura é a mesma peça"
    assert um(con, "SELECT COUNT(*) AS n FROM stock_items WHERE qbo_item_id='615'")["n"] == 1


def test_qr_usa_o_item_de_estoque_que_ja_existe(con):
    from command_center.providers import estoque
    iid = estoque.criar_item(con, "peca", "Reed petal (fiberglass)", price=25)
    con.execute("UPDATE stock_items SET qbo_item_id='615' WHERE id=?", (iid,))
    assert balcao.ler(con, "URQ615")["item"]["id"] == iid


def test_qr_de_item_que_nao_existe_e_codigo_novo(con):
    assert balcao.ler(con, "URQ999999")["tipo"] == "desconhecido"
    assert um(con, "SELECT COUNT(*) AS n FROM stock_items WHERE qbo_item_id='999999'")["n"] == 0


def test_celular_registra_pela_etiqueta(con):
    p = balcao_rapido.registrar(con, "URQ108", "2026-10-12")
    assert p["peca"] == "OTK Clamp for 30mm Torsion Bar" and p["item_id"]


# ------------------------------------------------------------------ a arte
def test_pdf_folha_e_uma_por_pagina(con):
    itens = etiquetas.produtos(con)
    folha = etiquetas.pdf(itens, "folha")
    uma = etiquetas.pdf(itens, "uma")
    assert folha.startswith(b"%PDF") and uma.startswith(b"%PDF")
    assert folha.count(b"/Type /Page\n") + folha.count(b"/Type /Page ") >= 1
    assert uma.count(b"/Type /Page") - uma.count(b"/Type /Pages") == len(itens)
    with pytest.raises(etiquetas.ErroEtiqueta):
        etiquetas.pdf([], "folha")
    with pytest.raises(etiquetas.ErroEtiqueta):
        etiquetas.pdf(itens, "a4")


# ------------------------------------------------------------------ o catálogo inteiro (era cortado em 300)
def test_qbo_itens_pagina_o_catalogo_inteiro(monkeypatch):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "adminai", "mcp"))
    import quickbooks_mcp as q
    pedidos = []

    def _query(sql):
        pedidos.append(sql)
        inicio = int(sql.split("startposition ")[1].split()[0])
        lote = int(sql.split("maxresults ")[1])
        total = 2350
        fim = min(total, inicio - 1 + lote)
        return {"Item": [{"Id": str(n), "Name": f"Item {n}", "Active": True} for n in range(inicio, fim + 1)]}
    monkeypatch.setattr(q, "_query", _query)
    todos_ = q.qbo_itens(maximo=5000)
    assert len(todos_) == 2350 and len(pedidos) == 3
    assert len(q.qbo_itens()) == 300, "o padrão continua 300 para quem não pede mais"


# ------------------------------------------------------------------ a tela
@pytest.fixture()
def cli(con, monkeypatch):
    qbo = QboFalso()
    import command_center.providers as prov
    monkeypatch.setattr(prov, "modulo", lambda nome: qbo if nome == "quickbooks" else None)
    mec = auth.criar_usuario(con, "mec@urace.us", "Mecânico", "OPERATOR", SENHA)
    con.execute("UPDATE users SET cargo='MECANICO' WHERE id=?", (mec,))
    auth.criar_usuario(con, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    inserir(con, "clients", name="Leo", status="ACTIVE")
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def test_gerente_ve_as_duplicatas_e_baixa_o_pdf(cli):
    entra(cli, "ger@urace.us")
    r = cli.get(f"{B}/etiquetas").json()
    assert r["total"] == 7 and len(r["duplicatas"]) == 1
    assert cli.get(f"{B}/etiquetas", params={"categorias": "OTK Parts|Parts"}).json()["total"] == 4
    pdf = cli.get(f"{B}/etiquetas.pdf", params={"formato": "uma", "categorias": "OTK Parts"})
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")
    assert cli.get(f"{B}/etiquetas.pdf", params={"categorias": "Nada"}).status_code == 400


def test_mecanico_le_a_etiqueta_mas_nao_imprime(cli):
    entra(cli, "mec@urace.us")
    assert cli.get(f"{B}/etiquetas").status_code == 403
    r = cli.get(f"{B}/ler", params={"codigo": "URQ501"}).json()
    assert r["tipo"] == "peca" and r["item"]["name"] == "Brake pad Parolin Micro/Mini"

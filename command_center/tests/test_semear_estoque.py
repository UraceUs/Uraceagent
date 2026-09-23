"""Semear o estoque pelo que as invoices mostraram girar.

Dono, 23/09: *"leia todas as invoices criadas desde o início do ano para saber quais as
peças que mais são usadas"*. O gabarito destes testes é o arquivo gerado daquela leitura,
`dados/pecas-mais-usadas-2026.json` — 348 invoices reais do QuickBooks.
"""
import importlib
import json
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from command_center.db import aplicar_schema, conectar, todos, um  # noqa: E402
from command_center.providers import estoque  # noqa: E402

semear_estoque = importlib.import_module("adminai.semear_estoque")


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


ITENS = [
    {"nome": "Rear sprocket", "kind": "peca", "categoria": "Parts", "qty_vendida": 63.0,
     "invoices": 31, "min_sugerido": 8},
    {"nome": "MG SH2 Red Tires Jr/Sr", "kind": "pneu", "categoria": "Parts", "qty_vendida": 31.0,
     "invoices": 16, "min_sugerido": 4},
    {"nome": "Peça de uma venda só", "kind": "peca", "categoria": "Parts", "qty_vendida": 1.0,
     "invoices": 1, "min_sugerido": 1},
]


def test_cria_ficha_com_minimo_e_procedencia(con):
    r = semear_estoque.semear(con, ITENS, aplicar=True)
    assert len(r["criados"]) == 3
    i = um(con, "SELECT * FROM stock_items WHERE name='Rear sprocket'")
    assert i["min_qty"] == 8 and i["kind"] == "peca" and i["tracking"] == "quantidade"
    assert "31 venda(s)" in i["notes"], "de onde veio o número tem de ficar escrito"


def test_pneu_vira_tipo_pneu_com_unidade_jogo(con):
    semear_estoque.semear(con, ITENS, aplicar=True)
    i = um(con, "SELECT * FROM stock_items WHERE name LIKE 'MG SH2%'")
    assert i["kind"] == "pneu" and i["unit"] == "jogo"


def test_nao_cria_saldo(con):
    """Ficha não é saldo. Quanto tem hoje quem diz é a contagem física."""
    semear_estoque.semear(con, ITENS, aplicar=True)
    assert todos(con, "SELECT * FROM stock_levels") == []
    assert todos(con, "SELECT * FROM stock_moves") == []
    i = um(con, "SELECT id FROM stock_items WHERE name='Rear sprocket'")
    assert estoque.saldo(con, i["id"]) == 0


def test_rodar_duas_vezes_nao_duplica(con):
    semear_estoque.semear(con, ITENS, aplicar=True)
    r = semear_estoque.semear(con, ITENS, aplicar=True)
    assert r["criados"] == [] and len(r["ja_existiam"]) == 3
    assert um(con, "SELECT COUNT(*) n FROM stock_items")["n"] == 3


def test_sem_aplicar_nao_escreve(con):
    r = semear_estoque.semear(con, ITENS, aplicar=False)
    assert len(r["criados"]) == 3
    assert um(con, "SELECT COUNT(*) n FROM stock_items")["n"] == 0


def test_a_ficha_nova_ja_aparece_na_lista_de_reposicao(con):
    """O ciclo fecha: ficha com mínimo e sem saldo é, por definição, o que falta comprar."""
    semear_estoque.semear(con, ITENS, aplicar=True)
    falta = {f["name"]: f["falta"] for f in estoque.abaixo_do_minimo(con)}
    assert falta["Rear sprocket"] == 8.0
    i = um(con, "SELECT id FROM stock_items WHERE name='Rear sprocket'")
    estoque.entrada(con, i["id"], qty=10)          # contagem/entrada resolve
    assert "Rear sprocket" not in {f["name"] for f in estoque.abaixo_do_minimo(con)}


# ------------------------------------------- o arquivo de verdade, gerado das invoices
def test_o_gabarito_do_dono_esta_no_repositorio():
    doc = semear_estoque.carregar()
    assert "348 invoices" in doc["fonte"] and "2026-09-22" in doc["fonte"]
    assert len(doc["itens"]) > 100


def test_o_arquivo_esta_ordenado_por_frequencia_nao_por_quantidade():
    """A frequência diz se a peça precisa estar na prateleira; a quantidade não.
    Uma caixa de 49 adesivos vendida de uma vez não é item de giro."""
    itens = semear_estoque.carregar()["itens"]
    assert [x["invoices"] for x in itens] == sorted((x["invoices"] for x in itens), reverse=True)
    assert itens[0]["nome"] == "Rear sprocket" and itens[0]["invoices"] == 31


def test_servico_mal_arquivado_como_peca_ficou_de_fora():
    """"Parts:Rebuild Motor Labor" e "Parts:SPEEDlab Complete Tag Rebuild Labor" estão
    sob "Parts" no QuickBooks, mas são mão de obra. Não entram em prateleira."""
    nomes = " | ".join(x["nome"].lower() for x in semear_estoque.carregar()["itens"])
    assert "labor" not in nomes and "rebuild" not in nomes


def test_taxa_de_viagem_nao_virou_peca():
    """O relatório pronto do QuickBooks põe "Travel Fee" no topo com 684 de quantidade —
    é quilometragem a $0,85. Foi por isso que o dono mandou ler invoice por invoice."""
    nomes = {x["nome"] for x in semear_estoque.carregar()["itens"]}
    for fora in ("Travel Fee", "Hotel", "Food", "Services", "Storage fee", "Driver Pass"):
        assert fora not in nomes, fora


def test_o_que_ficou_de_fora_tem_motivo_escrito():
    """Roupa sob medida e tenda de evento não são prateleira — e o porquê fica no arquivo,
    para o dono discordar se quiser."""
    doc = semear_estoque.carregar()
    assert set(doc["fora_da_lista"]) >= {"Clothes and accessories", "Canotops", "Karts"}
    assert all(v.strip() for v in doc["fora_da_lista"].values())


def test_todo_item_tem_minimo_de_pelo_menos_um():
    assert all(x["min_sugerido"] >= 1 for x in semear_estoque.carregar()["itens"])


# ---------------------------------------- o agregador: os três filtros que já pegaram erro
pecas_mais_usadas = importlib.import_module("adminai.pecas_mais_usadas")


def test_servico_arquivado_como_peca_nao_entra():
    """"Parts:Rebuild Motor Labor" está sob "Parts" no QuickBooks e é mão de obra."""
    r = pecas_mais_usadas.agregar([
        ("Parts:Rebuild Motor Labor", "1", "1350"),
        ("Parts:SPEEDlab Complete Tag Rebuild Labor", "1", "1499"),
        ("Parts:Rear sprocket", "2", "53"),
    ], meses=9)
    assert [x["nome"] for x in r] == ["Rear sprocket"]


def test_taxa_de_viagem_e_hotel_nao_sao_peca():
    """O "Sales by Product" do QuickBooks põe Travel Fee no topo com 684 — são milhas."""
    r = pecas_mais_usadas.agregar([
        ("Travel Fee", "684", "1635.35"), ("Hotel", "1", "362"),
        ("Service:Professional Coaching", "3", "2400"), ("Parts:Tie rod", "1", "24"),
    ], meses=9)
    assert [x["nome"] for x in r] == ["Tie rod"]


def test_peca_sem_categoria_no_quickbooks_ainda_e_encontrada():
    """"Levanto KRT Tires Junior/Senior" não tem prefixo e é o 9º item mais vendido."""
    r = pecas_mais_usadas.agregar([("Levanto KRT Tires Junior/Senior", "2", "520")], meses=9)
    assert r[0]["nome"] == "Levanto KRT Tires Junior/Senior" and r[0]["kind"] == "pneu"


def test_ordena_por_frequencia_e_nao_por_quantidade():
    """Uma caixa de 49 adesivos numa venda só não é item de giro; um pinhão em 3 vendas é."""
    linhas = [("Parts:Number Sticker", "49", "139")] + [("Parts:Rear sprocket", "1", "26")] * 3
    r = pecas_mais_usadas.agregar(linhas, meses=9)
    assert [x["nome"] for x in r] == ["Rear sprocket", "Number Sticker"]
    assert r[0]["invoices"] == 3 and r[1]["qty_vendida"] == 49


def test_minimo_sai_do_consumo_mensal_e_nunca_e_zero():
    r = pecas_mais_usadas.agregar([("Parts:Rear sprocket", "63", "1637")], meses=8.7)
    assert r[0]["por_mes"] == 7.24 and r[0]["min_sugerido"] == 8
    r2 = pecas_mais_usadas.agregar([("Parts:Coisa rara", "1", "10")], meses=8.7)
    assert r2[0]["min_sugerido"] == 1, "item raro ainda precisa de pelo menos 1"


def test_o_que_nao_e_prateleira_fica_de_fora_com_motivo():
    r = pecas_mais_usadas.agregar([
        ("Clothes and accessories:Custom Kart Suit", "30", "13290"),
        ("Canotops:10ft Half Wall", "7", "1043"),
        ("Karts:Chassi novo", "1", "5000"),
        ("Parts:Rear sprocket", "1", "26"),
    ], meses=9)
    assert [x["nome"] for x in r] == ["Rear sprocket"]
    assert set(pecas_mais_usadas.FORA_DA_PRATELEIRA) == {"Clothes and accessories", "Canotops", "Karts"}
    assert all(m.strip() for m in pecas_mais_usadas.FORA_DA_PRATELEIRA.values())


def test_preco_medio_sai_do_que_foi_de_fato_cobrado():
    r = pecas_mais_usadas.agregar([("Parts:Rk Non Oring Chain", "2", "112.78")], meses=9)
    assert r[0]["preco_medio"] == 56.39

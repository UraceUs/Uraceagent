"""Contagem física — o movimento que tira o estoque do zero.

A regra que mais importa aqui: **item que ninguém contou fica como está.** Contagem
parcial que zera o resto é como um estoque inteiro some numa tarde — alguém conta a
prateleira dos pneus, salva, e as correntes desaparecem.
"""
import importlib
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from command_center.db import aplicar_schema, conectar, todos, um  # noqa: E402
from command_center.providers import estoque  # noqa: E402

contar_estoque = importlib.import_module("adminai.contar_estoque")


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


@pytest.fixture()
def itens(con):
    a = estoque.criar_item(con, "peca", "Rear sprocket", min_qty=8)
    b = estoque.criar_item(con, "peca", "Rk Non Oring Chain", min_qty=6)
    con.commit()
    return a, b


def test_a_folha_mostra_o_que_ha_para_contar(con, itens):
    sede = estoque.local(con, "sede")["id"]
    f = contar_estoque.folha(con, sede)
    assert [l["nome"] for l in f] == ["Rear sprocket", "Rk Non Oring Chain"]
    assert all(l["sistema"] == 0 and l["contado_em"] is None for l in f), "nasce sem saldo"


def test_contar_um_nao_zera_o_outro(con, itens):
    """O defeito que esta ferramenta existe para não ter: contagem parcial não apaga
    o que não foi contado."""
    a, b = itens
    estoque.entrada(con, a, qty=10)
    estoque.entrada(con, b, qty=4)
    con.commit()
    estoque.contar(con, a, 7)
    con.commit()
    assert estoque.saldo(con, a) == 7
    assert estoque.saldo(con, b) == 4, "a corrente não foi contada e não pode sumir"


def test_zero_contado_e_diferente_de_nunca_contado(con, itens):
    """"Não tem nenhum" é informação; "ninguém olhou" é ausência dela."""
    a, _ = itens
    sede = estoque.local(con, "sede")["id"]
    assert contar_estoque.folha(con, sede)[0]["contado_em"] is None
    estoque.contar(con, a, 0)
    con.commit()
    linha = [l for l in contar_estoque.folha(con, sede) if l["id"] == a][0]
    assert linha["sistema"] == 0 and linha["contado_em"] is not None


def test_a_diferenca_da_contagem_fica_registrada(con, itens):
    """Contar não é corrigir o número: é guardar de quanto era o erro."""
    a, _ = itens
    estoque.entrada(con, a, qty=10)
    con.commit()
    r = estoque.contar(con, a, 7, notes="contagem do mês")
    con.commit()
    assert r["diferenca"] == -3
    m = um(con, "SELECT * FROM stock_moves WHERE kind='contagem'")
    assert m["qty_before"] == 10 and m["qty_after"] == 7 and m["notes"] == "contagem do mês"


def test_contagem_no_trailer_nao_mexe_na_sede(con, itens):
    a, _ = itens
    estoque.entrada(con, a, qty=10, para="sede")
    con.commit()
    estoque.contar(con, a, 2, onde="trailer")
    con.commit()
    assert estoque.saldo(con, a, estoque.local(con, "sede")["id"]) == 10
    assert estoque.saldo(con, a, estoque.local(con, "trailer")["id"]) == 2
    assert estoque.saldo(con, a) == 12


def test_a_contagem_tira_o_item_da_lista_de_falta(con, itens):
    """O ciclo fechando: ficha zerada aparece como falta; contada, some da lista."""
    a, b = itens
    assert len(estoque.abaixo_do_minimo(con)) == 2
    estoque.contar(con, a, 10)      # mínimo é 8
    con.commit()
    assert [f["id"] for f in estoque.abaixo_do_minimo(con)] == [b]


def test_o_razao_e_o_saldo_continuam_batendo_depois_de_contar(con, itens):
    a, b = itens
    estoque.entrada(con, a, qty=10)
    estoque.contar(con, a, 7)
    estoque.saida(con, a, qty=2)
    estoque.contar(con, b, 3)
    con.commit()
    assert estoque.conferir(con) == []
    assert estoque.saldo(con, a) == 5 and estoque.saldo(con, b) == 3


# --------------------------------------------------------------- a leitura dos pares
@pytest.mark.parametrize("texto,esperado", [
    ("3=12", (3, 12.0)), ("#3=12", (3, 12.0)), (" 3 = 12 ", (3, 12.0)), ("3=0", (3, 0.0)),
    ("3=2.5", (3, 2.5)),
])
def test_le_o_par_id_quantidade(texto, esperado):
    assert contar_estoque.ler_pares([texto]) == [esperado]


@pytest.mark.parametrize("ruim", ["3", "3=abc", "x=1", "=5", "3=1=2"])
def test_par_mal_escrito_para_tudo(ruim):
    """Um dedo errado aqui vira saldo errado lá. Melhor recusar do que adivinhar."""
    with pytest.raises(SystemExit):
        contar_estoque.ler_pares([ruim])


def test_contar_item_que_nao_existe_erra_claro(con):
    with pytest.raises(estoque.ErroEstoque) as e:
        estoque.contar(con, 999, 5)
    assert "não existe" in str(e.value)

"""Estoque: o que existe, onde está e de quem é.

Estes testes travam três decisões do dono (22/09) e uma regra que vem dos cards:

- chassi e motor têm ficha individual; pneu e peça são quantidade;
- sede e trailer são dois locais, e transferir não cria nem consome nada;
- o SKU da Comet é **referência de compra**, não identidade;
- **peça de um cliente nunca sai para outro** — a mesma regra de "nunca colocar serviço
  de outro cliente em card de outro cliente", aplicada ao que é físico.
"""
import os
import tempfile

import pytest

from command_center.db import aplicar_schema, conectar, inserir, todos, um
from command_center.providers import estoque
from command_center.providers.estoque import ErroEstoque


@pytest.fixture()
def con():
    antes = os.environ.get("CC_DB_PATH")
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="cc-estoq-"), "cc.sqlite")
    c = conectar(); aplicar_schema(c)
    try:
        yield c
    finally:
        c.close()
        if antes is None:
            os.environ.pop("CC_DB_PATH", None)
        else:
            os.environ["CC_DB_PATH"] = antes


def _cliente(con, nome):
    return inserir(con, "clients", source="manual", status="ACTIVE", name=nome)


def _pneu(con, **kw):
    kw.setdefault("name", "Pneu MG Yellow (jogo)")
    kw.setdefault("sku", "MG-YEL-SET")
    return estoque.criar_item(con, "pneu", unit="jogo", **kw)


def _motor(con):
    return estoque.criar_item(con, "motor", "IAME KA100")


# ------------------------------------------------------------ os dois comportamentos
def test_chassi_e_motor_nascem_com_ficha_individual(con):
    """Decisão do dono: "chassi e motor: ficha individual com número de série"."""
    m = _motor(con)
    assert um(con, "SELECT tracking FROM stock_items WHERE id=?", (m,))["tracking"] == "serie"
    estoque.entrada(con, m, serial="KA-9931")
    u = um(con, "SELECT * FROM stock_units WHERE item_id=?", (m,))
    assert u["serial"] == "KA-9931" and u["status"] == "disponivel"
    assert estoque.saldo(con, m) == 1


def test_motor_sem_numero_de_serie_nao_entra(con):
    """Ficha individual sem série é uma ficha que não identifica nada."""
    m = _motor(con)
    with pytest.raises(ErroEstoque) as e:
        estoque.entrada(con, m, qty=3)
    assert "número de série" in str(e.value)


def test_o_mesmo_serial_nao_entra_duas_vezes(con):
    m = _motor(con)
    estoque.entrada(con, m, serial="KA-9931")
    with pytest.raises(ErroEstoque) as e:
        estoque.entrada(con, m, serial="KA-9931")
    assert "já está cadastrado" in str(e.value)


def test_pneu_e_peca_sao_quantidade(con):
    p = _pneu(con)
    assert um(con, "SELECT tracking FROM stock_items WHERE id=?", (p,))["tracking"] == "quantidade"
    estoque.entrada(con, p, qty=10)
    estoque.saida(con, p, qty=3, reason="uso em serviço")
    assert estoque.saldo(con, p) == 7


def test_pneu_sem_quantidade_nao_entra(con):
    with pytest.raises(ErroEstoque) as e:
        estoque.entrada(con, _pneu(con), serial="nada")
    assert "informe quanto" in str(e.value)


def test_nao_deixa_o_saldo_ficar_negativo(con):
    """Saldo negativo é sempre erro de lançamento. Engolir isso é perder a contagem."""
    p = _pneu(con)
    estoque.entrada(con, p, qty=2)
    with pytest.raises(ErroEstoque) as e:
        estoque.saida(con, p, qty=5)
    assert "tem 2" in str(e.value)
    assert estoque.saldo(con, p) == 2, "a recusa não deixa rastro no saldo"


def test_quantidade_negativa_na_entrada_e_recusada(con):
    """Entrada com número negativo é saída escrita errado — e some do razão como saída."""
    with pytest.raises(ErroEstoque) as e:
        estoque.entrada(con, _pneu(con), qty=-5)
    assert "maior que zero" in str(e.value)


# ------------------------------------------------- a peça do cliente que está com a gente
def test_peca_de_um_cliente_nunca_sai_para_outro(con):
    """A regra dos cards, aplicada ao físico. Vale para quantidade…"""
    hank, savage = _cliente(con, "Hank Lai"), _cliente(con, "Alexander Savage")
    p = _pneu(con)
    estoque.entrada(con, p, qty=4, client_id=hank)
    with pytest.raises(ErroEstoque) as e:
        estoque.saida(con, p, qty=1, client_id=hank, para_cliente_id=savage, reason="venda")
    assert "Hank Lai" in str(e.value) and "outro cliente" in str(e.value)
    assert estoque.saldo(con, p, client_id=hank) == 4


def test_motor_do_cliente_tambem_nao_sai_para_outro(con):
    """…e para ficha individual, que é onde o prejuízo seria maior."""
    hank, savage = _cliente(con, "Hank Lai"), _cliente(con, "Alexander Savage")
    m = _motor(con)
    u = estoque.entrada(con, m, serial="KA-77", client_id=hank)["unit_id"]
    with pytest.raises(ErroEstoque):
        estoque.saida(con, m, unit_id=u, para_cliente_id=savage, reason="venda")
    assert um(con, "SELECT status FROM stock_units WHERE id=?", (u,))["status"] == "disponivel"


def test_peca_do_cliente_nao_e_nossa_para_vender(con):
    """Venda sem dizer para quem, de peça que é de alguém, é venda do que não é nosso."""
    hank = _cliente(con, "Hank Lai")
    p = _pneu(con)
    estoque.entrada(con, p, qty=4, client_id=hank)
    with pytest.raises(ErroEstoque) as e:
        estoque.saida(con, p, qty=1, client_id=hank, reason="venda")
    assert "não é nosso para vender" in str(e.value)


def test_devolver_para_o_proprio_dono_pode(con):
    """A trava é contra desviar, não contra devolver."""
    hank = _cliente(con, "Hank Lai")
    p = _pneu(con)
    estoque.entrada(con, p, qty=4, client_id=hank)
    estoque.saida(con, p, qty=4, client_id=hank, para_cliente_id=hank, reason="devolução")
    assert estoque.saldo(con, p, client_id=hank) == 0


def test_o_estoque_do_cliente_nao_se_mistura_com_o_nosso(con):
    """Mesmo item, dois donos, dois saldos. Sem isso o painel venderia o que é dos outros."""
    hank = _cliente(con, "Hank Lai")
    p = _pneu(con)
    estoque.entrada(con, p, qty=10)                 # nossos
    estoque.entrada(con, p, qty=4, client_id=hank)  # dele
    assert estoque.saldo(con, p) == 14, "o total da casa"
    assert estoque.saldo(con, p, client_id=None) == 10, "o que é nosso"
    assert estoque.saldo(con, p, client_id=hank) == 4


def test_o_que_e_do_cliente_aparece_para_o_card_dele(con):
    hank = _cliente(con, "Hank Lai")
    m, p = _motor(con), _pneu(con)
    estoque.entrada(con, m, serial="KA-77", client_id=hank)
    estoque.entrada(con, p, qty=4, client_id=hank)
    estoque.entrada(con, p, qty=10)                 # nosso: não pode aparecer no card dele
    d = estoque.do_cliente(con, hank)
    assert [u["serial"] for u in d["unidades"]] == ["KA-77"]
    assert [x["qty"] for x in d["pecas"]] == [4]


# --------------------------------------------------------------- sede e trailer
def test_transferir_nao_cria_nem_consome(con):
    """O total da casa não muda: o kart foi para a corrida, não sumiu."""
    p = _pneu(con)
    estoque.entrada(con, p, qty=10, para="sede")
    estoque.transferir(con, p, qty=4, de="sede", para="trailer")
    assert estoque.saldo(con, p, estoque.local(con, "sede")["id"]) == 6
    assert estoque.saldo(con, p, estoque.local(con, "trailer")["id"]) == 4
    assert estoque.saldo(con, p) == 10


def test_transferir_motor_muda_de_local_sem_virar_outra_unidade(con):
    m = _motor(con)
    u = estoque.entrada(con, m, serial="KA-77")["unit_id"]
    estoque.transferir(con, m, unit_id=u, de="sede", para="trailer")
    assert um(con, "SELECT location_id FROM stock_units WHERE id=?", (u,))["location_id"] == \
        estoque.local(con, "trailer")["id"]
    assert um(con, "SELECT COUNT(*) n FROM stock_units WHERE item_id=?", (m,))["n"] == 1


def test_nao_transfere_o_que_nao_esta_no_local_de_origem(con):
    """O trailer não empresta o que está na sede."""
    p = _pneu(con)
    estoque.entrada(con, p, qty=10, para="sede")
    with pytest.raises(ErroEstoque):
        estoque.transferir(con, p, qty=1, de="trailer", para="sede")
    assert estoque.saldo(con, p) == 10


def test_local_que_nao_existe_erra_claro(con):
    with pytest.raises(ErroEstoque) as e:
        estoque.entrada(con, _pneu(con), qty=1, para="garagem-do-vizinho")
    assert "local de estoque desconhecido" in str(e.value)


def test_vendavel_nunca_inclui_a_peca_do_cliente(con):
    """O defeito que este teste tranca: `client_id=None` queria dizer "não filtre" E "o
    que é nosso". O PDV perguntaria quanto pode vender e receberia o que é dos outros."""
    hank = _cliente(con, "Hank Lai")
    p = _pneu(con)
    estoque.entrada(con, p, qty=10)
    estoque.entrada(con, p, qty=4, client_id=hank)
    assert estoque.vendavel(con, p) == 10
    assert estoque.saldo(con, p) == 14, "TODOS continua sendo o total físico da casa"


def test_vendavel_de_motor_tambem_exclui_o_do_cliente(con):
    hank = _cliente(con, "Hank Lai")
    m = _motor(con)
    estoque.entrada(con, m, serial="KA-1")
    estoque.entrada(con, m, serial="KA-2", client_id=hank)
    assert estoque.vendavel(con, m) == 1 and estoque.saldo(con, m) == 2


# --------------------------------------------------------------- contagem e conferência
def test_contagem_vira_o_saldo_e_guarda_a_diferenca(con):
    """Contagem não é "corrigir o número": é dizer que estava errado e guardar de quanto."""
    p = _pneu(con)
    estoque.entrada(con, p, qty=10)
    r = estoque.contar(con, p, 8, by_user_id=None)
    assert (r["antes"], r["depois"], r["diferenca"]) == (10, 8, -2)
    assert estoque.saldo(con, p) == 8
    m = um(con, "SELECT * FROM stock_moves WHERE kind='contagem'")
    assert m["qty_before"] == 10 and m["qty_after"] == 8


def test_o_saldo_bate_com_o_razao_depois_de_uma_vida_inteira(con):
    """A conferência é o que impede o número de virar opinião."""
    hank = _cliente(con, "Hank Lai")
    p = _pneu(con)
    estoque.entrada(con, p, qty=10)
    estoque.entrada(con, p, qty=4, client_id=hank)
    estoque.transferir(con, p, qty=3, de="sede", para="trailer")
    estoque.saida(con, p, qty=2, reason="uso em serviço")
    estoque.ajustar(con, p, -1, reason="quebra")
    estoque.contar(con, p, 5, onde="sede")
    estoque.saida(con, p, qty=1, de="trailer", reason="uso em serviço")
    assert estoque.conferir(con) == [], "razão e saldo têm de contar a mesma história"
    assert estoque.saldo(con, p) == 5 + 2 + 4


def test_a_conferencia_acusa_quem_mexeu_no_saldo_por_fora(con):
    """Se alguém editar a tabela de saldo na mão, a conferência tem de gritar."""
    p = _pneu(con)
    estoque.entrada(con, p, qty=10)
    con.execute("UPDATE stock_levels SET qty=99 WHERE item_id=?", (p,))
    d = estoque.conferir(con)
    assert len(d) == 1 and d[0]["saldo"] == 99 and d[0]["razao"] == 10


def test_conferir_nao_conserta_sozinho(con):
    """Consertar em silêncio esconderia o defeito que produziu a diferença."""
    p = _pneu(con)
    estoque.entrada(con, p, qty=10)
    con.execute("UPDATE stock_levels SET qty=99 WHERE item_id=?", (p,))
    estoque.conferir(con)
    assert estoque.saldo(con, p) == 99, "só aponta"


def test_contagem_nao_vale_para_ficha_individual(con):
    """Contar motor é conferir série por série, não digitar um total."""
    m = _motor(con)
    estoque.entrada(con, m, serial="KA-77")
    with pytest.raises(ErroEstoque) as e:
        estoque.contar(con, m, 1)
    assert "ficha individual" in str(e.value)


def test_ajuste_sem_motivo_e_recusado(con):
    """Ajuste sem motivo é como um estoque deixa de bater sem ninguém perceber."""
    p = _pneu(con)
    estoque.entrada(con, p, qty=10)
    with pytest.raises(ErroEstoque) as e:
        estoque.ajustar(con, p, -1, reason="  ")
    assert "precisa de motivo" in str(e.value)


def test_todo_movimento_fica_no_razao(con):
    p = _pneu(con)
    estoque.entrada(con, p, qty=10)
    estoque.transferir(con, p, qty=3, de="sede", para="trailer")
    estoque.saida(con, p, qty=2, reason="venda", para_cliente_id=_cliente(con, "X"))
    estoque.ajustar(con, p, -1, reason="quebra")
    estoque.contar(con, p, 4, onde="sede")
    assert [m["kind"] for m in todos(con, "SELECT kind FROM stock_moves ORDER BY id")] == \
        ["entrada", "transferencia", "saida", "ajuste", "contagem"]


# ------------------------------------------------- reposição: a ponte para as compras
def test_abaixo_do_minimo_traz_o_sku_para_o_modulo_de_compras(con):
    """O SKU da Comet é referência de compra (dono, 22/09): a lista de reposição já sai
    com o que o comprador precisa para pedir."""
    p = _pneu(con, min_qty=6, supplier_url="https://cometkartsales.com/produto/mg-yel")
    estoque.entrada(con, p, qty=4)
    falta = estoque.abaixo_do_minimo(con)
    assert len(falta) == 1
    assert falta[0]["sku"] == "MG-YEL-SET" and falta[0]["falta"] == 2
    assert falta[0]["supplier_url"].startswith("https://cometkartsales.com")


def test_a_peca_do_cliente_nao_entra_na_lista_de_compra(con):
    """Peça de cliente não é nossa para repor — o painel não manda comprar dos outros."""
    hank = _cliente(con, "Hank Lai")
    p = _pneu(con, min_qty=6)
    estoque.entrada(con, p, qty=10, client_id=hank)
    assert [f["id"] for f in estoque.abaixo_do_minimo(con)] == [p], \
        "o estoque dele não tapa o buraco do nosso"
    estoque.entrada(con, p, qty=6)
    assert estoque.abaixo_do_minimo(con) == []


def test_item_sem_minimo_nao_vira_alarme(con):
    """Sem mínimo definido não há o que avisar — nem com o estoque zerado."""
    p = _pneu(con)                       # criado sem min_qty
    estoque.entrada(con, p, qty=2)
    estoque.saida(con, p, qty=2)
    assert estoque.saldo(con, p) == 0 and estoque.abaixo_do_minimo(con) == []


def test_minimo_nao_vale_para_ficha_individual(con):
    with pytest.raises(ErroEstoque) as e:
        estoque.criar_item(con, "motor", "IAME X30", min_qty=2)
    assert "não vale para item com número de série" in str(e.value)


# --------------------------------------------------------------------- o SKU
def test_sku_repetido_no_mesmo_fornecedor_e_o_mesmo_item_cadastrado_duas_vezes(con):
    """Se passar, a compra pediria em dobro."""
    _pneu(con)
    with pytest.raises(ErroEstoque) as e:
        estoque.criar_item(con, "pneu", "Outro nome para o mesmo pneu", sku="MG-YEL-SET")
    assert "já é do item" in str(e.value)


def test_item_pode_existir_sem_sku(con):
    """SKU é referência de compra, não identidade: peça avulsa e usado existem sem ele."""
    i = estoque.criar_item(con, "peca", "Corrente usada que veio no kart do Hank")
    assert um(con, "SELECT sku FROM stock_items WHERE id=?", (i,))["sku"] is None

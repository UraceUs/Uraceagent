"""Estoque em prateleiras, preço para o cliente e peça assinalada para cliente.

Dono, 29/09: *"a visualização que eu quero no estoque é por cards, em fileiras horizontais
de categorias"*; a peça tem *"o valor que a gente compra, … a porcentagem ou valor fixo que
a gente vai colocar em cima, … o valor final que vai entrar na invoice"*; e dá para
*"assinalar aqueles dois sets de pneus para o cliente"*, pelo estoque ou pelo card dele.
"""
import os
import tempfile

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth, motor  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, todos, um  # noqa: E402
from command_center.providers import estoque, prateleiras  # noqa: E402

B = "/ops/api/estoque"
SENHA = "senha-forte-123"


# ------------------------------------------------------------------ margem e preço final
@pytest.mark.parametrize("margem,esperado", [
    ("15%", 115.0), ("15 %", 115.0), ("20", 120.0), ("$20", 120.0), ("+20", 120.0),
    ("15% + 10", 125.0), ("12,5%", 112.5), ("", None), (None, None),
])
def test_margem_livre_vira_preco_final(margem, esperado):
    assert prateleiras.preco_final(100, margem) == esperado


def test_sem_valor_de_compra_nao_ha_conta():
    assert prateleiras.preco_final(None, "15%") is None


@pytest.mark.parametrize("ruim", ["quinze", "15%%", "-10", "10 dólares"])
def test_margem_que_nao_se_entende_e_recusada(ruim):
    """Melhor recusar do que adivinhar: margem mal lida é preço errado na invoice."""
    with pytest.raises(prateleiras.MargemInvalida):
        prateleiras.ler_margem(ruim)


# ------------------------------------------------------------------ prateleira sugerida
@pytest.mark.parametrize("kind,nome,prat", [
    ("pneu", "MG SH2 Red Tires Jr/Sr", "pneus"), ("motor", "IAME X30", "motores"),
    ("chassi", "Tony Kart 401T", "chassis"), ("peca", "Rk Non Oring Chain", "hardware"),
    ("peca", "Rear sprocket", "hardware"), ("peca", "Tonykart brake pads", "hardware"),
    ("peca", "Spark Plug", "pecas-motor"), ("peca", "Fuel mix", "fluidos"),
    ("peca", "Custom Kart Suit", "vestuario"), ("peca", "Number Sticker", "outros"),
    ("peca", "Coisa sem pista nenhuma", "outros"),
])
def test_peca_antiga_ganha_prateleira_pelo_nome(kind, nome, prat):
    assert prateleiras.sugerir(kind, nome) == prat


def test_vestuario_e_a_ultima_fileira():
    assert prateleiras.PRATELEIRAS[-1]["code"] == "vestuario"
    assert prateleiras.PRATELEIRAS[0]["code"] == "pneus"


def test_vocabulario_da_apostila_esta_nas_sugestoes():
    """Marca e medida do pneu, família do motor: a língua que a equipe já usa."""
    p, m = prateleiras.POR_CODIGO["pneus"], prateleiras.POR_CODIGO["motores"]
    assert {"MG", "Evinco", "LeVanto", "Leconte"} <= set(p["subcategorias"])
    assert {"4.60-5", "7.10-5", "6.00-5", "4.20-5"} <= set(p["medidas"])
    assert {"IAME", "Vortex ROK", "Rotax", "OKN", "Tillotson", "Briggs L206"} <= set(m["subcategorias"])


# ------------------------------------------------------------------ provider
@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def _cliente(con, nome):
    return inserir(con, "clients", name=nome, status="ACTIVE", source="manual")


def test_ficha_nasce_com_prateleira_e_preco_calculado(con):
    iid = estoque.criar_item(con, "pneu", "MG SH2 Red", category="pneus", subcategory="MG", size="7.10-5",
                             cost=200, markup="15%")
    it = estoque.item(con, iid)
    assert (it["category"], it["subcategory"], it["size"], it["cost"], it["markup"], it["price"]) == \
           ("pneus", "MG", "7.10-5", 200.0, "15%", 230.0)


def test_preco_final_digitado_vale_como_esta(con):
    iid = estoque.criar_item(con, "peca", "Corrente", cost=40, markup="15%", price=49.9)
    assert estoque.item(con, iid)["price"] == 49.9


def test_prateleira_ou_margem_invalida_nao_cria_nada(con):
    with pytest.raises(estoque.ErroEstoque):
        estoque.criar_item(con, "peca", "X", category="gaveta")
    with pytest.raises(estoque.ErroEstoque):
        estoque.criar_item(con, "peca", "X", cost=10, markup="muito")
    assert um(con, "SELECT COUNT(*) n FROM stock_items")["n"] == 0


def test_mudar_margem_refaz_o_preco_e_nao_mexe_no_tipo(con):
    iid = estoque.criar_item(con, "peca", "Vela", category="pecas-motor", cost=10, markup="20%")
    mudou = estoque.atualizar_item(con, iid, markup="50%", category="hardware")
    it = estoque.item(con, iid)
    assert it["price"] == 15.0 and it["category"] == "hardware" and it["kind"] == "peca"
    assert mudou["price"] == (12.0, 15.0)
    estoque.atualizar_item(con, iid, price=19.99)
    assert estoque.item(con, iid)["price"] == 19.99 and estoque.item(con, iid)["markup"] == "50%"
    with pytest.raises(estoque.ErroEstoque):
        estoque.atualizar_item(con, iid, kind="motor")


def test_assinalar_para_cliente_e_devolver(con):
    """Os dois sets de pneu do Brian: continuam na prateleira, passam a ser dele."""
    brian = _cliente(con, "Brian Santiago")
    iid = estoque.criar_item(con, "pneu", "MG SH2 Red", category="pneus")
    estoque.contar(con, iid, 5)
    r = estoque.trocar_dono(con, iid, para_cliente_id=brian, qty=2)
    assert r["cliente"] == "Brian Santiago"
    assert estoque.vendavel(con, iid) == 3 and estoque.saldo(con, iid, client_id=brian) == 2
    assert estoque.saldo(con, iid) == 5, "nada saiu da prateleira"
    assert estoque.conferir(con) == [], "o razão continua refazendo o saldo"
    assert estoque.do_cliente(con, brian)["pecas"][0]["qty"] == 2
    estoque.trocar_dono(con, iid, de_cliente_id=brian, qty=2)
    assert estoque.vendavel(con, iid) == 5 and estoque.conferir(con) == []


def test_nao_assinala_mais_do_que_a_urace_tem(con):
    brian = _cliente(con, "Brian Santiago")
    iid = estoque.criar_item(con, "pneu", "Evinco", category="pneus")
    estoque.contar(con, iid, 1)
    with pytest.raises(estoque.ErroEstoque):
        estoque.trocar_dono(con, iid, para_cliente_id=brian, qty=2)


def test_de_um_cliente_para_outro_nao(con):
    """A trava de sempre: peça de um cliente não vai para outro sem voltar pela URACE."""
    a, b = _cliente(con, "Brian Santiago"), _cliente(con, "Hank Lai")
    iid = estoque.criar_item(con, "pneu", "LeVanto", category="pneus")
    estoque.contar(con, iid, 2, client_id=a)
    with pytest.raises(estoque.ErroEstoque):
        estoque.trocar_dono(con, iid, de_cliente_id=a, para_cliente_id=b, qty=1)
    with pytest.raises(estoque.ErroEstoque):
        estoque.trocar_dono(con, iid, qty=1)
    assert estoque.saldo(con, iid, client_id=a) == 2


def test_motor_assinalado_pela_unidade(con):
    brian, hank = _cliente(con, "Brian Santiago"), _cliente(con, "Hank Lai")
    iid = estoque.criar_item(con, "motor", "IAME X30", category="motores")
    u = estoque.entrada(con, iid, serial="X30-1")["unit_id"]
    estoque.trocar_dono(con, iid, para_cliente_id=brian, unit_id=u)
    assert um(con, "SELECT client_id FROM stock_units WHERE id=?", (u,))["client_id"] == brian
    with pytest.raises(estoque.ErroEstoque):
        estoque.trocar_dono(con, iid, para_cliente_id=hank, unit_id=u)
    assert estoque.vendavel(con, iid) == 0


def test_tabela_de_precos_reconhece_a_peca_da_invoice(con):
    estoque.criar_item(con, "peca", "Rk Non Oring Chain", category="hardware", cost=40, markup="15%")
    assert estoque.preco_de_tabela(con, ["RK non o-ring chain"], 46.0)["name"] == "Rk Non Oring Chain", "O-Ring = Oring"
    assert estoque.preco_de_tabela(con, ["Rk Non Oring Chain 108 links"], 46.0)["name"] == "Rk Non Oring Chain"
    assert estoque.preco_de_tabela(con, ["Rk Non Oring Chain"], 50.0) is None, "preço diferente não bate"
    assert estoque.preco_de_tabela(con, ["Spark Plug"], 46.0) is None


def test_ai_command_recebe_o_preco_final_do_estoque(con):
    estoque.criar_item(con, "pneu", "MG SH2 Red", category="pneus", subcategory="MG", size="7.10-5",
                       unit="jogo", cost=200, markup="15%")
    estoque.criar_item(con, "peca", "Sem preço ainda", category="outros")
    ctx = motor.contexto_de_precos(con, "monta a invoice do Brian com 1 jogo de pneu")
    assert "PREÇO FINAL DAS PEÇAS DO ESTOQUE" in ctx
    assert "MG SH2 Red (MG · 7.10-5): $230.00 por jogo" in ctx
    assert "Sem preço ainda" not in ctx, "sem preço preenchido, nada é inventado"


# ------------------------------------------------------------------ API
@pytest.fixture(scope="module")
def cli():
    pasta = tempfile.mkdtemp()
    os.environ["CC_DB_PATH"] = os.path.join(pasta, "cc.sqlite")
    os.environ["URACE_DIR"] = pasta
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "mec@urace.us", "Mecânico", "OPERATOR", SENHA)
    auth.criar_usuario(c, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    inserir(c, "clients", name="Brian Santiago", status="ACTIVE", source="manual")
    c.close()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def _db():
    return conectar()


def _brian():
    return um(_db(), "SELECT id FROM clients WHERE name='Brian Santiago'")["id"]


def _itens(cli, h):
    return {i["name"]: i for i in cli.get(B, headers=h).json()["itens"]}


def test_mecanico_adiciona_pneu_na_prateleira_de_pneus(cli):
    h = entra(cli, "mec@urace.us")
    r = cli.post(f"{B}/item", headers=h, data={"name": "MG SH2 Red", "category": "pneus", "subcategory": "MG",
                                                "size": "7.10-5", "qty": "4"})
    assert r.status_code == 200, r.text
    it = estoque.item(_db(), r.json()["id"])
    assert it["kind"] == "pneu" and it["unit"] == "jogo" and it["category"] == "pneus"
    linha = _itens(cli, h)["MG SH2 Red"]
    assert linha["nosso"] == 4 and linha["category"] == "pneus" and not linha["prateleira_sugerida"]


def test_mecanico_adiciona_peca_que_e_do_cliente(cli):
    h = entra(cli, "mec@urace.us")
    r = cli.post(f"{B}/item", headers=h, data={"name": "Evinco Blue", "category": "pneus", "qty": "2",
                                                "client_id": str(_brian())})
    assert r.status_code == 200, r.text
    linha = _itens(cli, h)["Evinco Blue"]
    assert linha["nosso"] == 0 and linha["de_clientes"] == 2
    assert linha["clientes"] == [{"item_id": r.json()["id"], "client_id": _brian(), "cliente": "Brian Santiago", "qty": 2.0}]


def test_mecanico_nao_ve_nem_poe_custo_e_margem(cli):
    h = entra(cli, "ger@urace.us")
    r = cli.post(f"{B}/item", headers=h, data={"name": "Pastilha Tonykart", "category": "hardware", "qty": "3",
                                                "cost": "30", "markup": "15% + 5"})
    assert r.status_code == 200, r.text
    ger = _itens(cli, h)["Pastilha Tonykart"]
    assert (ger["cost"], ger["markup"], ger["price"]) == (30.0, "15% + 5", 39.5)
    h = entra(cli, "mec@urace.us")
    mec = _itens(cli, h)["Pastilha Tonykart"]
    assert mec["price"] == 39.5, "o preço para o cliente ele vê"
    assert "cost" not in mec and "markup" not in mec
    assert "cost" not in cli.get(f"{B}/{ger['id']}", headers=h).json()["item"]
    antes = um(_db(), "SELECT COUNT(*) n FROM stock_items")["n"]
    r = cli.post(f"{B}/item", headers=h, data={"name": "Com preço", "cost": "10"})
    assert r.status_code == 403
    assert um(_db(), "SELECT COUNT(*) n FROM stock_items")["n"] == antes
    assert cli.patch(f"{B}/item/{ger['id']}", headers=h, json={"price": 1}).status_code == 403
    assert estoque.item(_db(), ger["id"])["price"] == 39.5


def test_motor_com_numeros_de_serie_e_tudo_ou_nada(cli):
    h = entra(cli, "mec@urace.us")
    r = cli.post(f"{B}/item", headers=h, data={"name": "IAME KA100", "category": "motores", "serial": "KA-1\nKA-2"})
    assert r.status_code == 200, r.text
    assert len(r.json()["unidades"]) == 2 and _itens(cli, h)["IAME KA100"]["nosso"] == 2
    antes = um(_db(), "SELECT COUNT(*) n FROM stock_items")["n"]
    r = cli.post(f"{B}/item", headers=h, data={"name": "IAME X30", "category": "motores", "serial": "X-1, X-1"})
    assert r.status_code == 400
    assert um(_db(), "SELECT COUNT(*) n FROM stock_items")["n"] == antes, "ficha pela metade não fica"


def test_editar_ficha_e_margem_do_gerente(cli):
    h = entra(cli, "mec@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "Rear sprocket 80T"}).json()["id"]
    assert _itens(cli, h)["Rear sprocket 80T"]["category"] == "hardware"
    assert _itens(cli, h)["Rear sprocket 80T"]["prateleira_sugerida"]
    r = cli.patch(f"{B}/item/{iid}", headers=h, json={"category": "hardware", "subcategory": "Coroa / pinhão", "size": "80T"})
    assert r.status_code == 200, r.text
    assert not _itens(cli, h)["Rear sprocket 80T"]["prateleira_sugerida"]
    h = entra(cli, "ger@urace.us")
    assert cli.patch(f"{B}/item/{iid}", headers=h, json={"cost": 20, "markup": "30%"}).json()["price"] == 26.0
    assert cli.patch(f"{B}/item/{iid}", headers=h, json={"markup": "10"}).json()["price"] == 30.0
    assert cli.patch(f"{B}/item/{iid}", headers=h, json={"markup": "caro"}).status_code == 400
    assert cli.patch(f"{B}/item/{iid}", headers=h, json={"kind": "motor"}).status_code == 422
    aud = todos(_db(), "SELECT detail FROM audit_logs WHERE event='stock.item.edit' AND entity_id=?", (str(iid),))
    assert any('"price"' in a["detail"] for a in aud)


def test_assinalar_e_do_mecanico_devolver_e_do_gerente(cli):
    h = entra(cli, "mec@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "MG SM2 Yellow", "category": "pneus", "qty": "5"}).json()["id"]
    r = cli.post(f"{B}/assinalar", headers=h, json={"item_id": iid, "client_id": _brian(), "qty": 2})
    assert r.status_code == 200, r.text
    dele = cli.get(f"{B}/cliente/{_brian()}", headers=h).json()
    assert any(p["name"] == "MG SM2 Yellow" and p["qty"] == 2 and p["local_code"] == "sede" for p in dele["pecas"])
    assert cli.post(f"{B}/assinalar", headers=h, json={"item_id": iid, "client_id": _brian(), "qty": 10}).status_code == 400
    assert cli.post(f"{B}/devolver", headers=h, json={"item_id": iid, "client_id": _brian(), "qty": 2}).status_code == 403
    h = entra(cli, "ger@urace.us")
    assert cli.post(f"{B}/devolver", headers=h, json={"item_id": iid, "client_id": _brian(), "qty": 2}).status_code == 200
    assert _itens(cli, h)["MG SM2 Yellow"]["nosso"] == 5
    ev = [a["event"] for a in todos(_db(), "SELECT event FROM audit_logs WHERE entity_id=? ORDER BY id", (str(iid),))]
    assert "stock.assign" in ev and "stock.unassign" in ev
    assert cli.get(B, headers=h).json()["divergencias"] == []


# ------------------------------------------------------------------ 29/09, segunda rodada
def test_locais_sao_galpao_trailer_e_pista(con):
    """Dono: "galpão, trailer de corrida e pista (OKC)". O código 'sede' fica — é o que o
    razão guarda —, só o nome muda."""
    locs = {l["code"]: l["name"] for l in todos(con, "SELECT code, name FROM stock_locations")}
    assert locs == {"sede": "Galpão", "trailer": "Trailer de corrida", "pista": "Pista (OKC)"}
    iid = estoque.criar_item(con, "pneu", "MG SW2", category="pneus")
    estoque.contar(con, iid, 2, onde="pista")
    assert estoque.saldo(con, iid, estoque.local(con, "pista")["id"]) == 2


def test_banco_antigo_ganha_o_nome_novo_mas_nome_trocado_a_mao_fica(con):
    con.execute("UPDATE stock_locations SET name='Sede' WHERE code='sede'")
    aplicar_schema(con)
    assert estoque.local(con, "sede")["name"] == "Galpão"
    con.execute("UPDATE stock_locations SET name='Oficina do Italo' WHERE code='sede'")
    aplicar_schema(con)
    assert estoque.local(con, "sede")["name"] == "Oficina do Italo"


def test_alpha_line_e_o_nome_da_ultima_fileira():
    assert prateleiras.PRATELEIRAS[-1]["nome"] == "Alpha Line"
    assert "Macacões" in prateleiras.PRATELEIRAS[-1]["subcategorias"]
    assert prateleiras.sugerir("peca", "Macacão URACE (standard)") == "vestuario"


def test_fichas_da_alpha_line_sem_quantidade_nem_preco_e_sem_duplicar(con):
    import importlib
    semear = importlib.import_module("adminai.semear_alpha_line")
    assert semear.semear(con, aplicar=False)["criados"] and um(con, "SELECT COUNT(*) n FROM stock_items")["n"] == 0
    r = semear.semear(con, aplicar=True)
    assert r["criados"] == ["Boné URACE", "Camisa URACE", "Moletom URACE", "Macacão URACE (standard)"]
    linhas = todos(con, "SELECT * FROM stock_items")
    assert all(l["category"] == "vestuario" and l["price"] is None for l in linhas)
    assert todos(con, "SELECT * FROM stock_moves") == [], "quanto tem é o mecânico que diz"
    assert semear.semear(con, aplicar=True)["criados"] == []
    assert um(con, "SELECT COUNT(*) n FROM stock_items")["n"] == 4


def test_registrar_ja_dizendo_que_e_do_cliente(cli):
    """Dono: 'quando tiver registrando, já precisa ter um campo para colocar que é de algum
    cliente' — contagem e chegada com dono, sem passo extra."""
    h = entra(cli, "mec@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "LeVanto KRT", "category": "pneus"}).json()["id"]
    r = cli.post(f"{B}/contar", headers=h, json={"item_id": iid, "qty": 2, "local": "pista", "client_id": _brian()})
    assert r.status_code == 200, r.text
    r = cli.post(f"{B}/entrada", headers=h, json={"item_id": iid, "qty": 1, "client_id": _brian(), "motivo": "recebido do cliente"})
    assert r.status_code == 200, r.text
    linha = _itens(cli, h)["LeVanto KRT"]
    assert linha["nosso"] == 0 and linha["clientes"][0]["qty"] == 3
    assert cli.get(B, headers=h).json()["divergencias"] == []


# ------------------------------------------------------------------ lixeira (dono, 06/10)
def test_mecanico_exclui_peca_e_ela_sai_da_prateleira_sem_apagar_o_historico(cli):
    """Dono, 06/10: "dá a permissão para mecânico, gerente, acesso livre… excluir aquela peça
    ali das prateleiras". Sai da prateleira; movimentos e auditoria ficam."""
    h = entra(cli, "mec@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "Peça de exemplo", "category": "outros", "qty": "3"}).json()["id"]
    assert "Peça de exemplo" in _itens(cli, h)
    r = cli.delete(f"{B}/item/{iid}", headers=h)
    assert r.status_code == 200, r.text
    assert "Peça de exemplo" not in _itens(cli, h)
    assert estoque.item(_db(), iid)["active"] == 0, "a ficha fica, desligada"
    assert um(_db(), "SELECT COUNT(*) n FROM stock_moves WHERE item_id=?", (iid,))["n"] >= 1
    ev = [a["event"] for a in todos(_db(), "SELECT event FROM audit_logs WHERE entity_id=? ORDER BY id", (str(iid),))]
    assert "stock.item.remove" in ev
    assert cli.delete(f"{B}/item/{iid}", headers=h).status_code == 400, "excluir de novo diz que já foi"
    assert cli.delete(f"{B}/item/999999", headers=h).status_code == 404
    h = entra(cli, "ger@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "Outra de exemplo"}).json()["id"]
    assert cli.delete(f"{B}/item/{iid}", headers=h).status_code == 200


def test_peca_de_cliente_guardada_nao_se_exclui(cli):
    h = entra(cli, "mec@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "Pneu do Brian", "category": "pneus", "qty": "2",
                                                  "client_id": str(_brian())}).json()["id"]
    r = cli.delete(f"{B}/item/{iid}", headers=h)
    assert r.status_code == 400 and "cliente" in r.json()["detail"]
    assert "Pneu do Brian" in _itens(cli, h)


def test_codigo_de_peca_excluida_vira_codigo_novo_no_balcao(cli):
    from command_center.providers import balcao
    h = entra(cli, "mec@urace.us")
    velha = cli.post(f"{B}/item", headers=h, data={"name": "Vela antiga"}).json()["id"]
    c = _db()
    balcao.cadastrar_codigo(c, "7891234567895", velha); c.commit()
    assert balcao.ler(c, "7891234567895")["tipo"] == "peca"
    assert cli.delete(f"{B}/item/{velha}", headers=h).status_code == 200
    c = _db()
    assert balcao.ler(c, "7891234567895")["tipo"] == "desconhecido"
    nova = cli.post(f"{B}/item", headers=h, data={"name": "Vela nova"}).json()["id"]
    balcao.cadastrar_codigo(c, "7891234567895", nova); c.commit()
    assert balcao.ler(c, "7891234567895")["item"]["id"] == nova

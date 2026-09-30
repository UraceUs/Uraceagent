"""Pedidos internos e compras (dono, 30/09: "siga com a tela de pedidos e compras").

Pedido é de quem precisa; compra é de quem gasta; receber dá entrada no estoque sozinho.
"""
import os
import tempfile
from datetime import date, timedelta

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import atencao, auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, todos, um  # noqa: E402
from command_center.providers import compras, estoque  # noqa: E402

C = "/ops/api/compras"
SENHA = "senha-forte-123"


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def test_ciclo_completo_pedido_compra_recebimento(con):
    corrente = estoque.criar_item(con, "peca", "Rk Non Oring Chain", category="hardware", cost=40, markup="25%")
    rid = compras.criar_pedido(con, None, 3, item_id=corrente, urgent=True)
    pid = compras.criar_compra(con, None, [{"request_id": rid, "unit_cost": 44}], pedir=True)
    assert um(con, "SELECT status FROM purchase_requests WHERE id=?", (rid,))["status"] == "comprando"
    linha = compras.compra(con, pid)["linhas"][0]
    assert (linha["qty"], linha["description"], compras.compra(con, pid)["total"]) == (3, "Rk Non Oring Chain", 132.0)
    r = compras.receber(con, pid, [{"line_id": linha["id"], "qty": 2}])
    assert r["status"] == "parcial" and estoque.vendavel(con, corrente) == 2
    assert um(con, "SELECT status FROM purchase_requests WHERE id=?", (rid,))["status"] == "comprando", "ainda falta 1"
    r = compras.receber(con, pid, [{"line_id": linha["id"], "qty": 1}])
    assert r["status"] == "recebida" and estoque.vendavel(con, corrente) == 3
    assert um(con, "SELECT status FROM purchase_requests WHERE id=?", (rid,))["status"] == "chegou"
    it = estoque.item(con, corrente)
    assert it["cost"] == 44 and it["price"] == 55.0, "custo novo; com margem, o preço acompanha"
    mov = todos(con, "SELECT reason, notes FROM stock_moves WHERE item_id=? AND kind='entrada'", (corrente,))
    assert all(m["reason"] == "compra" and f"compra #{pid}" in m["notes"] for m in mov)
    assert estoque.conferir(con) == []


def test_sem_margem_o_preco_final_fica(con):
    iid = estoque.criar_item(con, "peca", "Vela", category="pecas-motor", price=12)
    pid = compras.criar_compra(con, None, [{"item_id": iid, "qty": 5, "unit_cost": 6}])
    compras.receber(con, pid, [{"line_id": compras.compra(con, pid)["linhas"][0]["id"], "qty": 5}])
    it = estoque.item(con, iid)
    assert (it["cost"], it["price"]) == (6, 12)


def test_chegou_mais_que_o_pedido_e_recusado(con):
    iid = estoque.criar_item(con, "peca", "Pinhão")
    pid = compras.criar_compra(con, None, [{"item_id": iid, "qty": 2}])
    with pytest.raises(compras.ErroCompra):
        compras.receber(con, pid, [{"line_id": compras.compra(con, pid)["linhas"][0]["id"], "qty": 3}])


def test_item_livre_pode_virar_ficha_no_recebimento(con):
    pid = compras.criar_compra(con, None, [{"description": "Fita de freio azul", "qty": 4}])
    l = compras.compra(con, pid)["linhas"][0]
    compras.receber(con, pid, [{"line_id": l["id"], "qty": 4, "criar_item": True}])
    it = um(con, "SELECT * FROM stock_items WHERE name='Fita de freio azul'")
    assert it and estoque.saldo(con, it["id"]) == 4 and it["category"] == "hardware"


def test_item_livre_sem_ficha_nao_mexe_no_estoque(con):
    pid = compras.criar_compra(con, None, [{"description": "Chave de roda", "qty": 1}])
    l = compras.compra(con, pid)["linhas"][0]
    assert compras.receber(con, pid, [{"line_id": l["id"], "qty": 1}])["entradas"][0]["estoque"] is False
    assert todos(con, "SELECT * FROM stock_moves") == []


def test_pedido_nao_entra_em_duas_compras(con):
    rid = compras.criar_pedido(con, None, 1, description="Luva P")
    compras.criar_compra(con, None, [{"request_id": rid}])
    with pytest.raises(compras.ErroCompra):
        compras.criar_compra(con, None, [{"request_id": rid}])


def test_cancelar_compra_devolve_os_pedidos_para_a_fila(con):
    rid = compras.criar_pedido(con, None, 1, description="Luva M")
    pid = compras.criar_compra(con, None, [{"request_id": rid}])
    compras.cancelar_compra(con, pid)
    assert um(con, "SELECT status, purchase_id FROM purchase_requests WHERE id=?", (rid,)) == {"status": "aberto", "purchase_id": None}


def test_compra_com_algo_recebido_nao_cancela(con):
    iid = estoque.criar_item(con, "peca", "Eixo")
    pid = compras.criar_compra(con, None, [{"item_id": iid, "qty": 2}])
    compras.receber(con, pid, [{"line_id": compras.compra(con, pid)["linhas"][0]["id"], "qty": 1}])
    with pytest.raises(compras.ErroCompra):
        compras.cancelar_compra(con, pid)


def test_pedido_precisa_dizer_o_que_e_e_quanto(con):
    with pytest.raises(compras.ErroCompra):
        compras.criar_pedido(con, None, 1)
    with pytest.raises(compras.ErroCompra):
        compras.criar_pedido(con, None, 0, description="algo")


def test_atencao_pedido_urgente_e_compra_atrasada(con):
    compras.criar_pedido(con, None, 2, description="Pastilha", urgent=True)
    pid = compras.criar_compra(con, None, [{"description": "Pneus", "qty": 4}], pedir=True,
                               expected_at=(date.today() - timedelta(days=2)).isoformat())
    chaves = {i["key"]: i for i in atencao.coletar(con)}
    assert chaves["pedido-urgente:purchase:abertos"]["level"] == "HIGH"
    assert f"compra-atrasada:purchase:{pid}" in chaves
    assert compras.compra(con, pid)["atrasada"]


# ------------------------------------------------------------------ API
@pytest.fixture(scope="module")
def cli():
    pasta = tempfile.mkdtemp()
    os.environ["CC_DB_PATH"] = os.path.join(pasta, "cc.sqlite")
    os.environ["URACE_DIR"] = pasta
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "mec@urace.us", "Mecânico", "OPERATOR", SENHA)
    auth.criar_usuario(c, "mec2@urace.us", "Outro Mecânico", "OPERATOR", SENHA)
    auth.criar_usuario(c, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    inserir(c, "clients", name="Enzo Kurian", status="ACTIVE", source="manual")
    c.close()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def test_mecanico_pede_gerente_compra_mecanico_recebe(cli):
    h = entra(cli, "ger@urace.us")
    iid = cli.post("/ops/api/estoque/item", headers=h, data={"name": "Tonykart brake pads", "category": "hardware"}).json()["id"]
    h = entra(cli, "mec@urace.us")
    enzo = um(conectar(), "SELECT id FROM clients")["id"]
    r = cli.post(f"{C}/pedidos", headers=h, json={"item_id": iid, "qty": 2, "client_id": enzo, "urgent": True,
                                                  "needed_by": "2026-10-05"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert cli.post(C, headers=h, json={"linhas": [{"request_id": rid}]}).status_code == 403, "comprar é do gerente"
    h = entra(cli, "ger@urace.us")
    pid = cli.post(C, headers=h, json={"pedir": True, "reference": "COMET-991", "linhas": [{"request_id": rid, "unit_cost": 30}]}).json()["id"]
    h = entra(cli, "mec@urace.us")
    c = cli.get(f"{C}/{pid}", headers=h).json()
    assert c["linhas"][0]["unit_cost"] is None and c["total"] is None, "custo é do gerente"
    assert c["linhas"][0]["cliente"] == "Enzo Kurian"
    r = cli.post(f"{C}/{pid}/receber", headers=h, json={"itens": [{"line_id": c["linhas"][0]["id"], "qty": 2}]})
    assert r.status_code == 200 and r.json()["status"] == "recebida", r.text
    assert estoque.vendavel(conectar(), iid) == 2
    assert cli.post(f"{C}/pedidos/{rid}/entregue", headers=h).status_code == 200
    ev = {a["event"] for a in todos(conectar(), "SELECT event FROM audit_logs")}
    assert {"purchase.request", "purchase.create", "purchase.receive", "purchase.request.delivered"} <= ev


def test_recebimento_com_linha_ruim_nao_grava_nada(cli):
    h = entra(cli, "ger@urace.us")
    iid = cli.post("/ops/api/estoque/item", headers=h, data={"name": "Corrente 106", "category": "hardware"}).json()["id"]
    pid = cli.post(C, headers=h, json={"linhas": [{"item_id": iid, "qty": 2}, {"description": "Adesivo", "qty": 1}]}).json()["id"]
    ls = cli.get(f"{C}/{pid}", headers=h).json()["linhas"]
    r = cli.post(f"{C}/{pid}/receber", headers=h, json={"itens": [{"line_id": ls[0]["id"], "qty": 2}, {"line_id": ls[1]["id"], "qty": 5}]})
    assert r.status_code == 400
    assert estoque.saldo(conectar(), iid) == 0, "tudo ou nada"


def test_so_quem_pediu_ou_o_gerente_cancela(cli):
    h = entra(cli, "mec@urace.us")
    rid = cli.post(f"{C}/pedidos", headers=h, json={"description": "Graxa", "qty": 1}).json()["id"]
    h2 = entra(cli, "mec2@urace.us")
    assert cli.post(f"{C}/pedidos/{rid}/cancelar", headers=h2).status_code == 403
    h = entra(cli, "mec@urace.us")
    assert cli.post(f"{C}/pedidos/{rid}/cancelar", headers=h).status_code == 200


def test_resumo(cli):
    h = entra(cli, "mec@urace.us")
    cli.post(f"{C}/pedidos", headers=h, json={"description": "Pneu chuva", "qty": 1, "urgent": True})
    d = cli.get(f"{C}/resumo", headers=h).json()
    assert d["pedidos_abertos"] >= 1 and d["urgentes"] >= 1 and "repor" in d

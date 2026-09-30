"""Peça do estoque usada no kart do cliente → cobrança dele.

Dono, 29/09: o preço final da peça "vai ser o valor que vai entrar na invoice daquele cliente
que pedir aquela peça, que usar aquela peça". Cada peça DA URACE que sai para um cliente fica
a cobrar, com o preço congelado; a invoice que chega do QuickBooks dá baixa sozinha.
"""
import os
import tempfile

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import atencao, auth, motor  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, todos, um  # noqa: E402
from command_center.providers import estoque, sync  # noqa: E402

B = "/ops/api/estoque"
SENHA = "senha-forte-123"


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def _base(con, preco=45.0):
    enzo = inserir(con, "clients", name="Enzo Kurian", status="ACTIVE", source="manual")
    iid = estoque.criar_item(con, "peca", "Rk Non Oring Chain", category="hardware", price=preco)
    estoque.contar(con, iid, 5)
    return enzo, iid


def _invoice(con, cid, linhas):
    inv = inserir(con, "invoices", client_id=cid, doc_number="2201", amount=100, balance=100, status="open", issued_on="2026-10-01")
    for n, (nome, desc, qtd, unit) in enumerate(linhas):
        inserir(con, "invoice_lines", invoice_id=inv, line_no=n, item_name=nome, description=desc, qty=qtd, unit_price=unit, amount=qtd * unit)
    return inv


def test_preco_da_cobranca_fica_congelado(con):
    enzo, iid = _base(con)
    ch = estoque.registrar_cobranca(con, iid, enzo, 1)
    estoque.atualizar_item(con, iid, price=60)
    assert estoque.cobrancas(con, enzo)[0]["unit_price"] == 45.0, "mudar o preço depois não muda o que já foi usado"


def test_invoice_do_quickbooks_da_baixa_pelo_nome_e_preco(con):
    enzo, iid = _base(con)
    a = estoque.registrar_cobranca(con, iid, enzo, 1)
    b = estoque.registrar_cobranca(con, iid, enzo, 1)
    inv = _invoice(con, enzo, [("Parts:Rk Non Oring Chain", "Chain 108 - Enzo", 1, 45.0)])
    assert estoque.conciliar_cobrancas(con, inv) == [a], "uma linha de 1 unidade dá baixa em uma cobrança só"
    assert [c["id"] for c in estoque.cobrancas(con, enzo)] == [b]


def test_nome_igual_com_preco_diferente_nao_baixa(con):
    enzo, iid = _base(con)
    estoque.registrar_cobranca(con, iid, enzo, 1)
    inv = _invoice(con, enzo, [("Rk Non Oring Chain", None, 1, 50.0)])
    assert estoque.conciliar_cobrancas(con, inv) == []


def test_invoice_de_outro_cliente_nao_baixa(con):
    enzo, iid = _base(con)
    outro = inserir(con, "clients", name="Hank Lai", status="ACTIVE", source="manual")
    estoque.registrar_cobranca(con, iid, enzo, 1)
    assert estoque.conciliar_cobrancas(con, _invoice(con, outro, [("Rk Non Oring Chain", None, 1, 45.0)])) == []


def test_sincronia_do_quickbooks_concilia(con, monkeypatch):
    enzo, iid = _base(con)
    con.execute("UPDATE clients SET email='joe@x.com' WHERE id=?", (enzo,))
    estoque.registrar_cobranca(con, iid, enzo, 2)
    fatura = {"id": "9", "numero": "2301", "total": 90, "saldo": 90, "status": "open", "email": "joe@x.com",
              "cliente": "Enzo Kurian", "linhas": [{"item_id": "71", "item": "Rk Non Oring Chain", "descricao": "x", "qtd": 2, "unitario": 45.0, "total": 90}]}
    monkeypatch.setattr(sync, "chamar", lambda *a, **k: {"invoices": [fatura]} if a[1] == "qbo_invoices" else [])
    assert sync.sync_qbo(con)["ok"]
    assert estoque.cobrancas(con, enzo) == [] and estoque.cobrancas(con, enzo, "invoiced")[0]["doc_number"] == "2301"


def test_ia_recebe_as_pecas_a_cobrar(con):
    enzo, iid = _base(con)
    estoque.registrar_cobranca(con, iid, enzo, 1)
    sem = estoque.criar_item(con, "peca", "Spark Plug", category="pecas-motor")
    estoque.registrar_cobranca(con, sem, enzo, 2)
    ctx = motor.contexto_do_comando(con, "monta a invoice do Enzo Kurian")
    assert "PEÇAS DO ESTOQUE USADAS E AINDA NÃO COBRADAS" in ctx
    assert "1× Rk Non Oring Chain a $45.00" in ctx and "2× Spark Plug (SEM PREÇO" in ctx
    assert "PEÇAS DO ESTOQUE" in motor._contexto_cliente(con, enzo), "o dia 1 também vê"


def test_atencao_lembra_de_cobrar(con):
    enzo, iid = _base(con)
    estoque.registrar_cobranca(con, iid, enzo, 2)
    it = {i["key"]: i for i in atencao.coletar(con)}[f"estoque-cobrar:client:{enzo}"]
    assert "Enzo Kurian" in it["title"] and it["facts"][0][1] == "$90.00"


# ------------------------------------------------------------------ API
@pytest.fixture(scope="module")
def cli():
    pasta = tempfile.mkdtemp()
    os.environ["CC_DB_PATH"] = os.path.join(pasta, "cc.sqlite")
    os.environ["URACE_DIR"] = pasta
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "mec@urace.us", "Mecânico", "OPERATOR", SENHA)
    auth.criar_usuario(c, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    inserir(c, "clients", name="Enzo Kurian", status="ACTIVE", source="manual")
    c.close()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def _enzo():
    return um(conectar(), "SELECT id FROM clients WHERE name='Enzo Kurian'")["id"]


def test_usei_no_kart_do_cliente_vira_cobranca(cli):
    h = entra(cli, "ger@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "Tonykart brake pads", "category": "hardware", "qty": "4", "price": "38"}).json()["id"]
    h = entra(cli, "mec@urace.us")
    r = cli.post(f"{B}/saida", headers=h, json={"item_id": iid, "qty": 2, "para_cliente_id": _enzo(), "motivo": "uso em serviço"})
    assert r.status_code == 200 and r.json()["cobranca_id"], r.text
    c = cli.get(f"{B}/cobrancas", headers=h, params={"client_id": _enzo()}).json()
    assert c["total"] == 76.0 and c["itens"][0]["name"] == "Tonykart brake pads"
    assert estoque.saldo(conectar(), iid) == 2


def test_peca_do_proprio_cliente_nao_se_cobra(cli):
    h = entra(cli, "mec@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "MG SH2 do Enzo", "category": "pneus", "qty": "2", "client_id": str(_enzo())}).json()["id"]
    r = cli.post(f"{B}/saida", headers=h, json={"item_id": iid, "qty": 1, "client_id": _enzo(), "para_cliente_id": _enzo()})
    assert r.status_code == 200 and "cobranca_id" not in r.json()


def test_uso_sem_cliente_nao_gera_cobranca(cli):
    h = entra(cli, "mec@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "Graxa", "category": "fluidos", "qty": "3"}).json()["id"]
    antes = um(conectar(), "SELECT COUNT(*) n FROM stock_charges")["n"]
    assert cli.post(f"{B}/saida", headers=h, json={"item_id": iid, "qty": 1}).status_code == 200
    assert um(conectar(), "SELECT COUNT(*) n FROM stock_charges")["n"] == antes


def test_saida_recusada_nao_deixa_cobranca_orfa(cli):
    h = entra(cli, "mec@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "Pinhão raro", "category": "hardware", "qty": "1"}).json()["id"]
    antes = um(conectar(), "SELECT COUNT(*) n FROM stock_charges")["n"]
    assert cli.post(f"{B}/saida", headers=h, json={"item_id": iid, "qty": 5, "para_cliente_id": _enzo()}).status_code == 400
    assert um(conectar(), "SELECT COUNT(*) n FROM stock_charges")["n"] == antes


def test_gerente_resolve_o_que_a_conciliacao_nao_resolveu(cli):
    h = entra(cli, "mec@urace.us")
    iid = cli.post(f"{B}/item", headers=h, data={"name": "Vela sem preço", "category": "pecas-motor", "qty": "3"}).json()["id"]
    ch = cli.post(f"{B}/saida", headers=h, json={"item_id": iid, "qty": 1, "para_cliente_id": _enzo()}).json()["cobranca_id"]
    assert cli.post(f"{B}/cobrancas/{ch}", headers=h, json={"acao": "nao_cobrar"}).status_code == 403
    h = entra(cli, "ger@urace.us")
    assert cli.post(f"{B}/cobrancas/{ch}", headers=h, json={"acao": "preco", "unit_price": 12}).json()["unit_price"] == 12
    assert cli.post(f"{B}/cobrancas/{ch}", headers=h, json={"acao": "nao_cobrar", "nota": "garantia"}).json()["status"] == "waived"
    assert cli.post(f"{B}/cobrancas/{ch}", headers=h, json={"acao": "cobrada"}).status_code == 409
    assert cli.post(f"{B}/cobrancas/{ch}", headers=h, json={"acao": "reabrir"}).json()["status"] == "pending"
    assert any(a["event"] == "stock.charge" for a in todos(conectar(), "SELECT event FROM audit_logs"))

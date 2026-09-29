"""Card do cliente, 29/09: valor da mensalidade + recorrência no QuickBooks, e serviços
que se movem para o cliente certo e mudam de nome (no Asana também).

Dono, no card do Enzo Kurian: *"o valor seja um campo alterável… pode ser um deal
diferente… deixasse como invoice recorrente no QuickBooks, padrão seis meses"*; e *"esse
Levi Grezik não é desse cliente… vincular ao cliente correto… alterar o nome… e selecionar
quais outros eu quero deixar com esse mesmo nome"*.
"""
import json
import os
import sys
import tempfile
from datetime import date

import pytest

os.environ["URACE_ENV"] = "/nao/existe"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "adminai", "mcp"))

from fastapi.testclient import TestClient  # noqa: E402

from command_center import providers  # noqa: E402
from command_center.api import auth, motor  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, todos, um  # noqa: E402
from command_center.providers import sync  # noqa: E402

SENHA = "senha-forte-123"


# ------------------------------------------------------------------ sincronia respeita o carimbo
@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def _cliente(con, nome, **kw):
    return inserir(con, "clients", name=nome, status="ACTIVE", source="manual", **kw)


def test_servico_confirmado_a_mao_nao_volta_para_o_card_errado(con):
    """O defeito que o botão "Mover" precisava que não existisse: a sincronia relia a tarefa
    aberta e decidia o cliente de novo pela descrição."""
    enzo, levi = _cliente(con, "Enzo Kurian"), _cliente(con, "Levi Grezik")
    tid, _ = sync._grava_tarefa(con, "G1", dict(client_id=enzo, title="Levi Grezik_Arrive and Drive", project="U-RACE"))
    con.execute("UPDATE tasks SET client_id=?, client_by='human' WHERE id=?", (levi, tid))
    sync._grava_tarefa(con, "G1", dict(client_id=enzo, title="Levi Grezik_Arrive and Drive — DOM 27/09", project="U-RACE"))
    t = um(con, "SELECT * FROM tasks WHERE id=?", (tid,))
    assert t["client_id"] == levi, "a escolha da pessoa fica"
    assert t["title"].endswith("DOM 27/09"), "o resto continua sincronizando"


def test_sem_carimbo_a_sincronia_segue_decidindo(con):
    a, b = _cliente(con, "A Um"), _cliente(con, "B Dois")
    tid, _ = sync._grava_tarefa(con, "G2", dict(client_id=a, title="x", project="U-RACE"))
    sync._grava_tarefa(con, "G2", dict(client_id=b, title="x", project="U-RACE"))
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (tid,))["client_id"] == b


# ------------------------------------------------------------------ dia 1 e contexto da IA
def test_dia_1_nao_cobra_duas_vezes_quem_tem_recorrencia(con):
    enzo = _cliente(con, "Enzo Kurian", monthly_plan="Academy 4 stroke", monthly_amount=450)
    outro = _cliente(con, "Hank Lai", monthly_plan="Academy 2 stroke")
    inserir(con, "monthly_recurring", client_id=enzo, amount=450, item_id="7", months=6,
            start_on="2026-10-01", end_on="2027-03-01", status="active")
    assert motor.eventos_do_dia_1(con, date(2026, 10, 1)) == 1
    ev = [e["client_id"] for e in todos(con, "SELECT client_id FROM ai_events WHERE kind='billing.monthly'")]
    assert ev == [outro]


def test_recorrencia_simulada_ou_encerrada_nao_segura_o_dia_1(con):
    enzo = _cliente(con, "Enzo Kurian", monthly_plan="Academy 4 stroke")
    inserir(con, "monthly_recurring", client_id=enzo, amount=450, item_id="7", months=6,
            start_on="2026-10-01", end_on="2027-03-01", status="simulated")
    assert motor.eventos_do_dia_1(con, date(2026, 10, 1)) == 1


def test_ia_recebe_o_valor_combinado(con):
    enzo = _cliente(con, "Enzo Kurian", monthly_plan="Academy 4 stroke", monthly_amount=399, monthly_item_id="7")
    ctx = motor._contexto_cliente(con, enzo)
    dados = json.loads(ctx.split("CLIENTE: ")[1].split("\n")[0])
    assert dados["monthly_amount"] == 399 and dados["monthly_item_id"] == "7" and dados["monthly_plan"] == "Academy 4 stroke"


# ------------------------------------------------------------------ conector do QuickBooks
@pytest.fixture
def qb(monkeypatch, tmp_path):
    import quickbooks_mcp as q
    monkeypatch.setenv("QBO_CLIENT_ID", "cid"); monkeypatch.setenv("QBO_CLIENT_SECRET", "sec"); monkeypatch.setenv("QBO_REALM_ID", "1")
    monkeypatch.setenv("QBO_TOKEN_JSON", str(tmp_path / "t.json"))
    q.gravar_token({"refresh_token": "r", "realm_id": "1"})
    enviados = []

    def _req(caminho, metodo="GET", corpo=None, params=None):
        enviados.append((caminho, metodo, corpo))
        return {"RecurringTransaction": {"Invoice": {"Id": "77", "TotalAmt": 450, "RecurringInfo": {"Name": "m"}}}}
    monkeypatch.setattr(q, "_req", _req)
    return q, enviados


LINHA = [{"item_id": "7", "quantidade": 1, "unitario": 450, "descricao": "Academy 4 stroke — Enzo"}]


def test_recorrencia_no_quickbooks_seis_meses_no_dia_1(qb, monkeypatch):
    q, enviados = qb
    monkeypatch.setenv("APLICAR", "1")
    r = q.qbo_criar_recorrencia("485", LINHA, 6, "2026-10-01", nome="Mensalidade Enzo", email="joe@x.com")
    assert r["aplicado"] and r["id"] == "77" and r["fim"] == "2027-03-01"
    caminho, metodo, corpo = enviados[-1]
    assert (caminho, metodo) == ("/recurringtransaction", "POST")
    inv = corpo["Invoice"]
    sched = inv["RecurringInfo"]["ScheduleInfo"]
    assert inv["RecurringInfo"]["RecurType"] == "Automated" and inv["EmailStatus"] == "NeedToSend"
    assert (sched["IntervalType"], sched["DayOfMonth"], sched["StartDate"], sched["MaxOccurrences"]) == ("Monthly", 1, "2026-10-01", 6)
    assert inv["Line"][0]["SalesItemLineDetail"]["UnitPrice"] == 450 and inv["BillEmail"]["Address"] == "joe@x.com"


def test_recorrencia_doze_meses_vira_o_ano(qb, monkeypatch):
    q, _ = qb
    monkeypatch.setenv("APLICAR", "1")
    assert q.qbo_criar_recorrencia("485", LINHA, 12, "2026-11-01")["fim"] == "2027-10-01"


def test_recorrencia_sem_aplicar_e_simulacao(qb, monkeypatch):
    q, enviados = qb
    monkeypatch.setenv("APLICAR", "0")
    r = q.qbo_criar_recorrencia("485", LINHA, 6, "2026-10-01")
    assert not r["aplicado"] and enviados == []


@pytest.mark.parametrize("meses,inicio", [(0, "2026-10-01"), (37, "2026-10-01"), (6, "2026-10-15"), (6, "amanhã")])
def test_recorrencia_recusa_o_que_nao_faz_sentido(qb, monkeypatch, meses, inicio):
    q, _ = qb
    monkeypatch.setenv("APLICAR", "1")
    with pytest.raises(Exception):
        q.qbo_criar_recorrencia("485", LINHA, meses, inicio)


def test_o_servidor_stdio_registra_o_lembrete_e_a_recorrencia():
    """O `if __name__` ficava no meio do arquivo e o lembrete nunca existia no stdio."""
    import quickbooks_mcp as q
    fonte = open(q.__file__, encoding="utf-8").read()
    assert fonte.rstrip().endswith("srv.rodar()")
    assert fonte.index('if __name__ == "__main__"') > fonte.index("def qbo_lembrete_invoice")


# ------------------------------------------------------------------ API
@pytest.fixture(scope="module")
def cli():
    pasta = tempfile.mkdtemp()
    os.environ["CC_DB_PATH"] = os.path.join(pasta, "cc.sqlite")
    os.environ["URACE_DIR"] = pasta
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "op@urace.us", "Op", "OPERATOR", SENHA)
    auth.criar_usuario(c, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    enzo = inserir(c, "clients", name="Enzo Kurian", pilot_name="Enzo", email="joekur001@gmail.com", status="ACTIVE",
                   source="manual", monthly_plan="Academy 4 stroke")
    inserir(c, "clients", name="Levi Grezik", status="ACTIVE", source="manual")
    inserir(c, "qbo_items", id="7", name="Academy 4 stroke", price=500, active=1)
    inserir(c, "invoices", client_id=enzo, doc_number="2001", amount=500, balance=0, status="paid",
            issued_on="2026-09-01", customer_ref="485", memo="Academy")
    c.close()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def _id(nome):
    return um(conectar(), "SELECT id FROM clients WHERE name=?", (nome,))["id"]


def test_valor_mensal_e_do_gerente(cli):
    enzo = _id("Enzo Kurian")
    h = entra(cli, "op@urace.us")
    assert cli.get(f"/ops/api/clients/{enzo}/mensal", headers=h).status_code == 403
    assert cli.patch(f"/ops/api/clients/{enzo}/mensal", headers=h, json={"monthly_amount": 1}).status_code == 403
    h = entra(cli, "ger@urace.us")
    assert cli.patch(f"/ops/api/clients/{enzo}/mensal", headers=h, json={"monthly_item_id": "999"}).status_code == 400
    r = cli.patch(f"/ops/api/clients/{enzo}/mensal", headers=h, json={"monthly_amount": 450, "monthly_item_id": "7"})
    assert r.status_code == 200, r.text
    d = cli.get(f"/ops/api/clients/{enzo}/mensal", headers=h).json()
    assert d["monthly_amount"] == 450 and d["item"]["name"] == "Academy 4 stroke" and d["padrao_meses"] == 6
    assert any(a["event"] == "client.monthly.deal" for a in todos(conectar(), "SELECT event FROM audit_logs"))


def test_recorrencia_pelo_painel_e_sem_cobrar_duas_vezes(cli, monkeypatch):
    enzo = _id("Enzo Kurian")
    chamadas = []

    def falso(sistema, ferramenta, **a):
        chamadas.append((sistema, ferramenta, a))
        return {"aplicado": True, "id": "77", "inicio": a["inicio"]}
    monkeypatch.setattr(providers, "chamar", falso)
    h = entra(cli, "ger@urace.us")
    cli.patch(f"/ops/api/clients/{enzo}/mensal", headers=h, json={"monthly_amount": 450, "monthly_item_id": "7"})
    inicio = f"{date.today().year + 1}-01-01"
    r = cli.post(f"/ops/api/clients/{enzo}/mensal/recorrencia", headers=h, json={"meses": 6, "inicio": inicio})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active" and r.json()["fim"] == f"{date.today().year + 1}-06-01"
    _, ferramenta, a = chamadas[-1]
    assert ferramenta == "qbo_criar_recorrencia" and a["cliente_id"] == "485", "cliente do QBO pela última invoice"
    assert a["linhas"][0]["unitario"] == 450 and a["email"] == "joekur001@gmail.com"
    r = cli.post(f"/ops/api/clients/{enzo}/mensal/recorrencia", headers=h, json={"meses": 12, "inicio": inicio})
    assert r.status_code == 409, "cobrar duas vezes, não"
    rec = um(conectar(), "SELECT * FROM monthly_recurring WHERE client_id=?", (enzo,))
    assert rec["status"] == "active" and rec["qbo_id"] == "77" and rec["months"] == 6


def test_recorrencia_simulada_fica_registrada_como_simulacao(cli, monkeypatch):
    levi = _id("Levi Grezik")
    con = conectar(); con.execute("UPDATE clients SET monthly_amount=300, monthly_item_id='7', email='levi@x.com' WHERE id=?", (levi,)); con.close()

    def falso(sistema, ferramenta, **a):
        if ferramenta == "qbo_clientes_buscar":
            return [{"id": "900", "email": "levi@x.com"}]
        return {"aplicado": False, "teria_feito": "criar recorrência"}
    monkeypatch.setattr(providers, "chamar", falso)
    h = entra(cli, "ger@urace.us")
    r = cli.post(f"/ops/api/clients/{levi}/mensal/recorrencia", headers=h, json={"meses": 3})
    assert r.status_code == 200 and r.json()["status"] == "simulated", r.text
    assert um(conectar(), "SELECT status FROM monthly_recurring WHERE client_id=?", (levi,))["status"] == "simulated"


def test_recorrencia_sem_valor_combinado_e_recusada(cli):
    novo = inserir(c := conectar(), "clients", name="Sem Deal", status="ACTIVE", source="manual"); c.close()
    h = entra(cli, "ger@urace.us")
    assert cli.post(f"/ops/api/clients/{novo}/mensal/recorrencia", headers=h, json={}).status_code == 400


def _tarefa(cid, titulo, gid):
    c = conectar()
    tid = inserir(c, "tasks", client_id=cid, title=titulo, project="U-RACE", status="open")
    if gid:
        inserir(c, "entity_links", entity_type="task", entity_id=tid, system="asana", external_id=gid)
    c.close()
    return tid


def test_mover_servico_e_do_gerente_e_fica_carimbado(cli):
    enzo, levi = _id("Enzo Kurian"), _id("Levi Grezik")
    tid = _tarefa(enzo, "Levi Grezik_Arrive and Drive", "G10")
    h = entra(cli, "op@urace.us")
    assert cli.post(f"/ops/api/tasks/{tid}/cliente", headers=h, json={"client_id": levi}).status_code == 403
    h = entra(cli, "ger@urace.us")
    r = cli.post(f"/ops/api/tasks/{tid}/cliente", headers=h, json={"client_id": levi})
    assert r.status_code == 200, r.text
    t = um(conectar(), "SELECT * FROM tasks WHERE id=?", (tid,))
    assert t["client_id"] == levi and t["client_by"] == "human"


def test_renomear_no_asana_e_em_varios(cli, monkeypatch):
    enzo = _id("Enzo Kurian")
    a, b, c = _tarefa(enzo, "Enzo Kurian_Academy [4 Stroke] SESSAO EXTRA", "G20"), \
        _tarefa(enzo, "Enzo Kurian [4 strokes 09/05/26]", "G21"), _tarefa(enzo, "criada no painel", None)
    pedidos = []

    def falso(sistema, ferramenta, **k):
        pedidos.append((ferramenta, k["gid"], k["nome"]))
        return {"aplicado": True}
    monkeypatch.setattr(providers, "chamar", falso)
    h = entra(cli, "op@urace.us")
    r = cli.post("/ops/api/tasks/renomear", headers=h, json={"task_ids": [a, b, c], "nome": "Enzo Kurian_Academy Monthly [4 Stroke]"})
    assert r.status_code == 200, r.text
    assert len(r.json()["renomeados"]) == 3 and r.json()["falhas"] == []
    assert {p[1] for p in pedidos} == {"G20", "G21"} and all(p[0] == "asana_renomear" for p in pedidos)
    for tid in (a, b, c):
        t = um(conectar(), "SELECT * FROM tasks WHERE id=?", (tid,))
        assert t["title"] == "Enzo Kurian_Academy Monthly [4 Stroke]" and t["client_by"] == "human"


def test_asana_em_simulacao_nao_muda_o_nome_aqui(cli, monkeypatch):
    """Nome trocado só no painel voltaria ao antigo na próxima sincronia: melhor não trocar."""
    enzo = _id("Enzo Kurian")
    tid = _tarefa(enzo, "nome velho", "G30")
    monkeypatch.setattr(providers, "chamar", lambda *a, **k: {"aplicado": False, "modo": "SIMULAÇÃO (APLICAR=0)"})
    h = entra(cli, "op@urace.us")
    r = cli.post("/ops/api/tasks/renomear", headers=h, json={"task_ids": [tid], "nome": "nome novo"})
    assert r.status_code == 502 and "simulação" in r.json()["detail"]
    assert um(conectar(), "SELECT title FROM tasks WHERE id=?", (tid,))["title"] == "nome velho"


def test_asana_renomear_respeita_simulacao_e_protecao(monkeypatch):
    import asana_mcp as a
    monkeypatch.setattr(a, "_ler_tarefa", lambda gid, campos=None: {"gid": gid, "name": "velho", "memberships": []})
    escritas = []
    monkeypatch.setattr(a, "_req", lambda caminho, metodo="GET", corpo=None, **k: escritas.append((caminho, metodo, corpo)) or {"data": {}})
    monkeypatch.setenv("APLICAR", "0")
    assert not a.asana_renomear("1", "novo")["aplicado"] and escritas == []
    monkeypatch.setenv("APLICAR", "1")
    assert a.asana_renomear("1", "novo")["aplicado"]
    assert ("/tasks/1", "PUT", {"name": "novo"}) in escritas
    monkeypatch.setattr(a, "_ler_tarefa", lambda gid, campos=None: {"gid": gid, "name": "x",
                                                                    "memberships": [{"project": {"gid": a.PROJETO_ADM}}]})
    with pytest.raises(a.ErroFerramenta):
        a.asana_renomear("2", "novo")

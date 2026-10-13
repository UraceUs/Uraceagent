"""#219: excluir serviço do Calendário — só gerente e acesso livre; some, mas fica no histórico.

Dono, 13/10: *"somente o acesso livre e o gerente tenham a possibilidade de excluir uma tarefa
facilmente. Ela exclui, deixa de ser mostrada, mas lá no histórico de serviço ela continua sendo
armazenada como uma tarefa excluída, com todo o histórico de logs para auditoria."*
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from command_center.api import auth, motor
from command_center.api.main import app
from command_center.db import aplicar_schema, conectar, inserir, todos, um
from command_center.providers import balcao_rapido, checklists, sync

SENHA = "senha-forte-123"
DIA = "2026-10-20"


@pytest.fixture(scope="module")
def cli():
    pasta = tempfile.mkdtemp()
    os.environ["CC_DB_PATH"] = os.path.join(pasta, "cc.sqlite")
    os.environ["URACE_DIR"] = pasta
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "op@urace.us", "Op", "OPERATOR", SENHA)
    auth.criar_usuario(c, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    c.close()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def _servico(gid, nome="Max Westerberg"):
    con = conectar()
    cid = inserir(con, "clients", name=nome, pilot_name=nome, status="ACTIVE", source="manual")
    tid, _ = sync._grava_tarefa(con, gid, dict(client_id=cid, title=f"{nome}_Arrive and Drive [1/1]", project="U-RACE",
                                                section="TUESDAY", status="open", due_on=DIA))
    con.commit(); con.close()
    return tid, cid


def test_so_gerente_exclui_e_o_mecanico_nem_ve_o_botao(cli):
    tid, _ = _servico("X1")
    h = entra(cli, "op@urace.us")
    assert cli.get(f"/ops/api/meu-dia?data={DIA}").json()["gerente"] is False
    assert cli.post(f"/ops/api/tasks/{tid}/excluir", headers=h, json={}).status_code == 403
    h = entra(cli, "ger@urace.us")
    assert cli.get(f"/ops/api/meu-dia?data={DIA}").json()["gerente"] is True
    assert cli.post(f"/ops/api/tasks/{tid}/excluir", headers=h, json={"motivo": "teste do dono"}).status_code == 200
    assert cli.post(f"/ops/api/tasks/{tid}/excluir", headers=h, json={}).status_code == 409


def test_excluido_some_do_calendario_do_balcao_e_dos_contadores_mas_fica_no_card(cli):
    tid, cid = _servico("X2", "Lia Souza")
    con = conectar()
    assert any(s["id"] == tid for s in checklists.meu_dia(con, DIA)["servicos"])
    con.close()
    h = entra(cli, "ger@urace.us")
    cli.post(f"/ops/api/tasks/{tid}/excluir", headers=h, json={"motivo": "duplicado"})
    con = conectar()
    assert not any(s["id"] == tid for s in checklists.meu_dia(con, DIA)["servicos"]), "some do dia"
    assert not any(s["id"] == tid for s in checklists.periodo(con, DIA, DIA)["dias"][DIA]["servicos"]), "e da semana/mês"
    assert not any(p["client_id"] == cid for p in balcao_rapido.pilotos_do_dia(con, DIA)), "e do balcão"
    con.close()
    card = cli.get(f"/ops/api/clients/{cid}").json()
    t = next(x for x in card["tasks"] if x["id"] == tid)
    assert t["deleted_at"] and t["deleted_by_name"] == "Gerente" and t["deleted_reason"] == "duplicado", "fica no histórico"
    assert cli.get("/ops/api/clients").status_code == 200
    ev = todos(conectar(), "SELECT detail FROM audit_logs WHERE event='task.deleted' AND entity_id=?", (tid,))
    assert ev and "duplicado" in ev[0]["detail"]


def test_a_sincronia_do_asana_nao_desfaz_a_exclusao(cli):
    tid, cid = _servico("X3", "Ana Lima")
    h = entra(cli, "ger@urace.us")
    cli.post(f"/ops/api/tasks/{tid}/excluir", headers=h, json={})
    con = conectar()
    sync._grava_tarefa(con, "X3", dict(client_id=cid, title="Ana Lima_Arrive and Drive [1/1] — TER", project="U-RACE",
                                       section="TUESDAY", status="open", due_on=DIA))
    con.commit()
    t = um(con, "SELECT * FROM tasks WHERE id=?", (tid,))
    assert t["deleted_at"] and t["title"].endswith("TER"), "a marca fica; o resto continua espelhando"


def test_a_ia_nao_age_em_servico_excluido(cli):
    tid, cid = _servico("X4", "Rui Costa")
    h = entra(cli, "ger@urace.us")
    cli.post(f"/ops/api/tasks/{tid}/excluir", headers=h, json={})
    con = conectar()
    inserir(con, "ai_events", kind="task.overdue", entity_type="task", entity_id=tid, client_id=cid,
            summary="ainda aberta", status="NEW")
    con.commit()
    motor.processar_eventos(con, 1)
    ev = um(con, "SELECT status, note FROM ai_events WHERE entity_id=? AND kind='task.overdue'", (tid,))
    assert ev["status"] == "SKIPPED" and "excluído" in ev["note"]


def test_restaurar_volta_para_o_calendario(cli):
    tid, _ = _servico("X5", "Bia Reis")
    h = entra(cli, "ger@urace.us")
    cli.post(f"/ops/api/tasks/{tid}/excluir", headers=h, json={})
    assert cli.post(f"/ops/api/tasks/{tid}/restaurar", headers=h).status_code == 200
    con = conectar()
    assert any(s["id"] == tid for s in checklists.meu_dia(con, DIA)["servicos"])
    assert um(con, "SELECT 1 AS x FROM audit_logs WHERE event='task.restored' AND entity_id=?", (tid,))

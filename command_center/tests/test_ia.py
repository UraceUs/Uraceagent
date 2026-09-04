"""AI Command com runner falso: fila, execução em thread, extração de
ações propostas com a política vigente, aprovação/rejeição auditadas,
BLOCKED nunca aprovável, e isolamento por usuário."""
import os
import tempfile
import time

import pytest

from fastapi.testclient import TestClient

from command_center.api import auth, ia
from command_center.api.main import app
from command_center.db import aplicar_schema, conectar, todos

B = "/ops/api/ai"
SENHA = "senha-forte-123"

SAIDA_SIMULADA = """Varredura feita. Renato Frota Pionti, serviço amanhã, menor (14), sem waiver.
Não enviei nada — o ambiente está em simulação. Em produção eu teria enviado a waiver
parental para o responsável e comentado na tarefa.

{"aplicado": false, "modo": "SIMULAÇÃO (APLICAR=0)", "teria_feito": "rascunho (urace) para rafael@spmesportes.com.br: 'Waiver do Renato'"}

ACAO: docusign_enviar_waiver | Rafael Pionti <rafael@spmesportes.com.br> | waiver parental, serviço 05/09
ACAO: asana_comentar | 1218104997373079 | [IA ADM] waiver pendente, responsável avisado
"""


def runner_falso(texto, session_key):
    if "falhe" in texto:
        return False, "", "erro simulado do agente"
    return True, SAIDA_SIMULADA, None


@pytest.fixture(scope="module")
def cli():
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc-ia.sqlite")
    ia.RUNNER = runner_falso
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "admin@urace.us", "Admin", "ADMIN", SENHA)
    auth.criar_usuario(con, "op@urace.us", "Op", "OPERATOR", SENHA)
    auth.criar_usuario(con, "viewer@urace.us", "Viewer", "VIEWER", SENHA)
    con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def espera(cli, cid, timeout=5):
    fim = time.time() + timeout
    while time.time() < fim:
        c = cli.get(f"{B}/commands/{cid}").json()
        if c["status"] in ("DONE", "FAILED"):
            return c
        time.sleep(0.05)
    raise AssertionError("comando não terminou")


def test_viewer_nao_comanda(cli):
    h = entra(cli, "viewer@urace.us")
    assert cli.post(B + "/commands", headers=h, json={"text": "oi"}).status_code == 403
    assert cli.get(B + "/suggestions").status_code == 200        # mas vê as sugestões


def test_comando_roda_e_propoe_acoes_com_politica(cli):
    h = entra(cli, "op@urace.us")
    r = cli.post(B + "/commands", headers=h, json={"text": "rode a varredura de waivers"})
    assert r.status_code == 202
    c = espera(cli, r.json()["id"])
    assert c["status"] == "DONE" and "Renato" in c["output"]
    pol = {a["action"]: a for a in c["actions"]}
    assert pol["docusign_enviar_waiver"]["policy"] == "REQUIRES_APPROVAL"
    assert pol["docusign_enviar_waiver"]["status"] == "PROPOSED"
    assert pol["asana_comentar"]["policy"] == "SAFE"
    assert pol["gmail_rascunho"]["policy"] == "SAFE"
    con = conectar()
    assert todos(con, "SELECT * FROM approvals WHERE action_id=?", (pol["docusign_enviar_waiver"]["id"],))
    con.close()


def test_aprovacao_exige_manager_e_e_auditada(cli):
    entra(cli, "op@urace.us")
    acao = [a for a in cli.get(B + "/actions?status=PROPOSED").json() if a["policy"] == "REQUIRES_APPROVAL"][0]
    h = {"X-CSRF": cli.cookies.get("cc_csrf")}
    assert cli.post(f"{B}/actions/{acao['id']}/approve", headers=h, json={}).status_code == 403   # OPERATOR não aprova
    h = entra(cli, "admin@urace.us")
    r = cli.post(f"{B}/actions/{acao['id']}/approve", headers=h, json={"comment": "ok, manda"})
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"
    assert cli.post(f"{B}/actions/{acao['id']}/approve", headers=h, json={}).status_code == 409   # já decidida
    ev = [e["event"] for e in cli.get(B + "/activity").json()]
    assert "action.approved" in ev and "ai.command.done" in ev and "ai.command" in ev


def test_operador_pode_rejeitar(cli):
    h = entra(cli, "op@urace.us")
    acao = [a for a in cli.get(B + "/actions?status=PROPOSED").json()][0]
    r = cli.post(f"{B}/actions/{acao['id']}/reject", headers=h, json={"comment": "não é o caso"})
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"


def test_bloqueada_nunca_aprova(cli):
    con = conectar()
    from command_center.db import inserir
    aid = inserir(con, "ai_actions", action="gmail_enviar", system="gmail", policy="BLOCKED", status="BLOCKED",
                  payload="{}", reason="teste")
    con.close()
    h = entra(cli, "admin@urace.us")
    assert cli.post(f"{B}/actions/{aid}/approve", headers=h, json={}).status_code == 403


def test_falha_do_agente_fica_registrada(cli):
    h = entra(cli, "op@urace.us")
    cid = cli.post(B + "/commands", headers=h, json={"text": "falhe de propósito"}).json()["id"]
    c = espera(cli, cid)
    assert c["status"] == "FAILED" and "erro simulado" in c["error"]


def test_historico_e_por_usuario_salvo_para_manager(cli):
    entra(cli, "viewer@urace.us")
    assert cli.get(B + "/commands").json() == []                  # viewer não comandou nada
    entra(cli, "admin@urace.us")
    assert len(cli.get(B + "/commands").json()) >= 2              # manager+ vê todos

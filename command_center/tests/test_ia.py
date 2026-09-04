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


R = "/ops/api"


# ------------------------------------------------ IA que age (04/09): eventos, balão, memória, execução
def test_acao_com_json_e_execucao_aprovada(cli):
    from command_center.api import ia, motor
    from command_center.db import conectar
    h = entra(cli, "admin@urace.us")
    ia.RUNNER = lambda texto, sk: (True, "Feito.\nACAO: asana_comentar | 123 | avisar | {\"gid\":\"123\",\"texto\":\"waiver chegou\"}\nACAO: docusign_enviar_waiver | x@y.com | parental", None)
    r = cli.post(B + "/commands", headers=h, json={"text": "teste de protocolo"})
    cid = r.json()["id"]
    import time
    for _ in range(50):
        c = cli.get(B + f"/commands/{cid}").json()
        if c["status"] in ("DONE", "FAILED"):
            break
        time.sleep(0.1)
    acts = {a["action"]: a for a in c["actions"]}
    import json
    assert json.loads(acts["asana_comentar"]["payload"])["args"] == {"gid": "123", "texto": "waiver chegou"}
    assert json.loads(acts["docusign_enviar_waiver"]["payload"])["args"] is None
    assert acts["docusign_enviar_waiver"]["policy"] == "REQUIRES_APPROVAL"
    # aprovar a que não tem args: executa e falha com explicação (nunca 500, nunca "some")
    aid = acts["docusign_enviar_waiver"]["id"]
    r = cli.post(B + f"/actions/{aid}/approve", headers=h, json={})
    assert r.status_code == 200 and "executando" in r.json()["note"]
    for _ in range(50):
        a = [x for x in cli.get(B + "/actions").json() if x["id"] == aid][0]
        if a["status"] in ("DONE", "FAILED"):
            break
        time.sleep(0.1)
    assert a["status"] == "FAILED" and "argumentos" in a["result"]
    # a com args mas política SAFE/confirmação: aprovar executa via provider (sem Asana -> FAILED "não conectado")
    aid2 = acts["asana_comentar"]["id"]
    cli.post(B + f"/actions/{aid2}/approve", headers=h, json={})
    for _ in range(50):
        a2 = [x for x in cli.get(B + "/actions").json() if x["id"] == aid2][0]
        if a2["status"] in ("DONE", "FAILED"):
            break
        time.sleep(0.1)
    assert a2["status"] == "FAILED" and "conectado" in (a2["result"] or "").lower()
    con = conectar(); assert motor.aprendizados(con) == ""; con.close()


def test_balao_instrui_e_aprende(cli):
    from command_center.api import ia
    h = entra(cli, "admin@urace.us")
    ia.RUNNER = lambda texto, sk: (True, ("ENSINADO" if "custa $350" in texto else "SEM MEMORIA") + "\nACAO: nenhuma", None)
    r = cli.post(R + "/needs-attention/instruct", headers=h, json={"key": "waiver-servico:task:1", "text": "Practice OKC custa $350; envie a invoice e a waiver", "remember": True, "title": "X sem waiver", "why": "regra", "client_id": None, "entity_type": "task", "entity_id": "1"})
    assert r.status_code == 202 and r.json()["remembered"]
    ls = cli.get(B + "/learnings").json()
    assert ls and ls[0]["scope"] == "entity:task" and "custa $350" in ls[0]["text"]
    # a memória entra no próximo comando do mesmo escopo (entity:task) — e no global só o global
    cid = cli.post(R + "/needs-attention/instruct", headers=h, json={"key": "k2", "text": "ok", "remember": False, "title": "Y", "entity_type": "task"}).json()["command_id"]
    import time
    for _ in range(50):
        c = cli.get(B + f"/commands/{cid}").json()
        if c["status"] in ("DONE", "FAILED"):
            break
        time.sleep(0.1)
    assert c["status"] == "DONE" and c["output"].startswith("ENSINADO")
    assert cli.post(R + "/needs-attention/instruct", headers=entra(cli, "viewer@urace.us"), json={"key": "k", "text": "x"}).status_code == 403
    h = entra(cli, "admin@urace.us")
    assert cli.post(B + f"/learnings/{ls[0]['id']}/toggle", headers=h).json()["active"] is False


def test_eventos_viram_comandos_conforme_regra(cli):
    from command_center.api import ia, motor
    from command_center.db import conectar, inserir
    h = entra(cli, "admin@urace.us")
    ia.RUNNER = lambda texto, sk: (True, "EVENTO OK\nACAO: nenhuma", None)
    con = conectar()
    cid = inserir(con, "clients", name="Evento Teste", email="ev@example.com", status="ACTIVE", source="asana")
    tid = inserir(con, "tasks", client_id=cid, title="Evento Teste_Kart", project="U-RACE", section="SATURDAY", status="open", due_on="2026-09-12")
    motor.registrar_evento(con, "task.created", "task", tid, cid, "Evento Teste_Kart em SATURDAY")
    motor.registrar_evento(con, "task.created", "task", tid, cid, "duplicado ignorado")
    assert con.execute("SELECT COUNT(*) FROM ai_events WHERE entity_id=?", (tid,)).fetchone()[0] == 1
    # regra desligada -> SKIPPED; ligada -> comando
    assert cli.put(R + "/automation/rules/novo_servico", headers=h, json={"enabled": False}).status_code == 200
    assert motor.processar_eventos(con, 1) == 0
    ev = cli.get(B + "/events").json()[0]
    assert ev["status"] == "SKIPPED"
    cli.put(R + "/automation/rules/novo_servico", headers=h, json={"enabled": True})
    con.execute("UPDATE ai_events SET status='NEW' WHERE id=?", (ev["id"],))
    assert motor.processar_eventos(con, 1) == 1
    import time
    for _ in range(50):
        ev = cli.get(B + "/events").json()[0]
        if ev["status"] in ("DONE", "FAILED"):
            break
        time.sleep(0.1)
    assert ev["status"] == "DONE" and ev["command_id"] and ev["command_status"] == "DONE"
    assert cli.put(R + "/automation/rules/nao_existe", headers=h, json={"enabled": True}).status_code == 404
    assert cli.put(R + "/automation/rules/novo_servico", headers=entra(cli, "viewer@urace.us"), json={"enabled": False}).status_code == 403
    con.close()

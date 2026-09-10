"""AI Command com runner falso: fila, execução em thread, extração de
ações propostas com a política vigente, aprovação/rejeição auditadas,
BLOCKED nunca aprovável, e isolamento por usuário."""
import json
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
    con = conectar(); assert "Racing team" in motor.aprendizados(con) and "custa $350" not in motor.aprendizados(con); con.close()


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


def test_safe_executa_sozinho_e_finished(cli):
    from command_center.api import ia
    import json, time
    h = entra(cli, "admin@urace.us")
    ia.RUNNER = lambda texto, sk: (True, 'ok\nACAO: asana_mover_para_finished | 999 | mover | {"gid":"999"}\nACAO: asana_mover_para_secao | 999 | mover | {"gid":"999","secao_gid":"1"}', None)
    cid = cli.post(B + "/commands", headers=h, json={"text": "vencida"}).json()["id"]
    for _ in range(80):
        c = cli.get(B + f"/commands/{cid}").json()
        if c["status"] in ("DONE", "FAILED") and all(a["status"] not in ("APPROVED", "RUNNING") for a in c["actions"]):
            break
        time.sleep(0.1)
    acts = {a["action"]: a for a in c["actions"]}
    # SAFE com args: executou sozinha (sem Asana aqui -> FAILED "não conectado", mas passou pelo motor, não ficou PROPOSED)
    assert acts["asana_mover_para_finished"]["policy"] == "SAFE" and acts["asana_mover_para_finished"]["status"] == "FAILED"
    assert "conectado" in (acts["asana_mover_para_finished"]["result"] or "").lower()
    # REQUIRES_CONFIRMATION continua esperando gente
    assert acts["asana_mover_para_secao"]["status"] == "PROPOSED"


def test_openclaw_descoberta_e_mensagem():
    from command_center.api import ia
    import os
    antes = os.environ.pop("OPENCLAW_BIN", None)
    try:
        assert ia._acha_openclaw()                                   # nunca vazio
        os.environ["OPENCLAW_BIN"] = "/x/y/openclaw"
        assert ia._acha_openclaw() == "/x/y/openclaw"
        ok, _, erro = ia.runner_openclaw("ping", "s")
        assert not ok and "OPENCLAW_BIN" in erro and "/x/y/openclaw" in erro
    finally:
        os.environ.pop("OPENCLAW_BIN", None)
        if antes:
            os.environ["OPENCLAW_BIN"] = antes


# ------------------------------------------ 10/09: invoice com valor certo, sem repetir o decidido
def test_normaliza_invoice_aliases_item_por_nome_e_valor_do_texto():
    from command_center.api import acoes
    buscar = lambda nome: [{"id": "31", "nome": "Arrive and Drive daily"}] if "arrive" in nome.lower() else []
    args, prob = acoes.normalizar_invoice({"cliente": "77", "itens": [{"item": "Arrive and Drive daily", "valor": "$500", "qty": 1, "desc": "David Pera 13/09"}], "due": "2026-09-13"}, "", buscar)
    assert prob == [] and args["cliente_id"] == "77" and args["data_servico"] == "2026-09-13" and args["vence_em"] == "2026-09-11"   # vence 2 dias antes do serviço
    assert args["linhas"][0] == {"item_id": "31", "quantidade": 1, "unitario": 500.0, "descricao": "David Pera 13/09"}
    # valor zerado + UM valor no texto da IA → o texto manda
    args, prob = acoes.normalizar_invoice({"cliente_id": 77, "linhas": [{"item_id": "31", "unitario": 0, "descricao": "x"}]}, "Invoice de $500 no nome do Nicolas.", buscar)
    assert prob == [] and args["linhas"][0]["unitario"] == 500.0 and args["linhas"][0]["_valor_do_texto"] is True
    # dois valores no texto: não adivinha → problema; item não achado → problema
    args, prob = acoes.normalizar_invoice({"cliente_id": "77", "linhas": [{"item": "Coisa inexistente", "unitario": 0}]}, "Pode ser $500 ou $719.", buscar)
    assert any("Coisa inexistente" in p for p in prob) and any("zerado" in p for p in prob)
    assert acoes.valores_no_texto("Total: $1,250.00 e $500") == [1250.0, 500.0]
    assert acoes.assinatura("asana_criar_tarefa", {"nome": "David Pera_Urace Daily [1/1]", "vence_em": "2026-09-13"}) == "asana_criar_tarefa|david pera_urace daily [1/1]|2026-09-13"


_TAREFA = 'ACAO: asana_atualizar_tarefa | David Pera | serviço domingo | {"projeto_gid":"1205450093098920","secao_gid":"1205141832260879","nome":"David Pera_Urace Daily_Using Own Kart [1/1]","vence_em":"2026-09-13"}'
_INVOICE_OK = 'ACAO: qbo_criar_e_enviar_invoice | Nicolas Pera | invoice $500 | {"cliente_id":"77","linhas":[{"item_id":"31","quantidade":1,"unitario":500,"descricao":"Using Own Kart - David Pera - 2026-09-13"}],"vence_em":"2026-09-13"}'


def test_nao_repete_acao_feita_e_substitui_pendente(cli):
    h = entra(cli, "admin@urace.us")
    ia.RUNNER = lambda texto, sk: (True, "Vou criar a tarefa e a invoice de $500.\n" + _TAREFA + "\n" + _INVOICE_OK, None)
    c1 = espera(cli, cli.post(f"{B}/commands", headers=h, json={"text": "David Pera domingo, mesmo esquema"}).json()["id"])
    a1 = {a["action"]: a for a in c1["actions"]}
    assert a1["asana_atualizar_tarefa"]["status"] == "PROPOSED" and a1["qbo_criar_e_enviar_invoice"]["status"] == "PROPOSED"
    # o dono muda algo e manda de novo: as pendentes antigas são substituídas, não duplicadas
    c2 = espera(cli, cli.post(f"{B}/commands", headers=h, json={"text": "waiver vale um ano, mesmo valor"}).json()["id"])
    assert "AÇÕES JÁ PROPOSTAS HOJE" in c2["prompt"] and "#%d" % a1["asana_atualizar_tarefa"]["id"] in c2["prompt"] and c2["text"] == "waiver vale um ano, mesmo valor"
    a2 = {a["action"]: a for a in c2["actions"]}
    assert all(a["status"] == "PROPOSED" for a in a2.values())
    velha = cli.get(f"{B}/commands/{c1['id']}").json()["actions"]
    assert all(a["status"] == "REJECTED" and "substituída" in (a["result"] or "") for a in velha)
    assert "substitui a proposta" in c2["output"]
    # a tarefa foi aprovada e executada: não volta a ser proposta
    con = conectar(); con.execute("UPDATE ai_actions SET status='DONE' WHERE id=?", (a2["asana_atualizar_tarefa"]["id"],)); con.commit(); con.close()
    c3 = espera(cli, cli.post(f"{B}/commands", headers=h, json={"text": "e aí?"}).json()["id"])
    acoes3 = [a["action"] for a in c3["actions"]]
    assert "asana_atualizar_tarefa" not in acoes3 and "qbo_criar_e_enviar_invoice" in acoes3
    assert "já aprovada/feita em #%d" % a2["asana_atualizar_tarefa"]["id"] in c3["output"]
    assert "FEITA" in c3["prompt"]


def test_invoice_zerada_ganha_uma_correcao_da_ia(cli, monkeypatch):
    h = entra(cli, "admin@urace.us")
    chamadas = []

    def runner(texto, sk):
        chamadas.append(texto)
        if "[Command Center] A ação qbo_criar_e_enviar_invoice" in texto:
            return True, 'ACAO: qbo_criar_e_enviar_invoice | Nicolas Pera | invoice $500 | {"cliente_id":"77","linhas":[{"item_id":"31","quantidade":1,"unitario":500,"descricao":"corrigida"}],"vence_em":"2026-09-20"}', None
        return True, ('Mesmo esquema: pode ser $500 ou $719, depende.\n'
                      'ACAO: qbo_criar_e_enviar_invoice | Nicolas Pera | invoice | {"cliente_id":"77","itens":[{"item":"Arrive and Drive daily - David","valor":0}],"vence_em":"2026-09-20"}'), None
    ia.RUNNER = runner
    monkeypatch.setattr(ia, "_buscar_item_qbo", lambda nome: [])
    c = espera(cli, cli.post(f"{B}/commands", headers=h, json={"text": "invoice do David pro dia 20"}).json()["id"], timeout=8)
    assert len(chamadas) == 2 and "valor unitário zerado" in chamadas[1]
    acs = c["actions"]
    boa = [a for a in acs if a["status"] == "PROPOSED"]; ruim = [a for a in acs if a["status"] == "REJECTED"]
    assert len(boa) == 1 and len(ruim) == 1 and "correção" in ruim[0]["result"]
    import json as _j
    p = _j.loads(boa[0]["payload"])
    assert p["args"]["linhas"][0]["unitario"] == 500 and not p.get("problemas") and "unitario" in c["output"]
    ia.RUNNER = runner_falso


def test_nome_com_prefixo_do_mcp_e_tarefa_pelo_modelo(cli):
    """'asana__asana_criar_tarefa' (como o OpenClaw expõe) vira asana_criar_tarefa; em coluna de dia,
    vira asana_criar_do_modelo com o modelo oficial — e executa (SAFE) em vez de cair em 'Confirmar' e falhar."""
    from command_center.api import acoes
    assert acoes.nome_canonico("asana__asana_criar_tarefa") == "asana_criar_tarefa"
    assert acoes.nome_canonico("qbo__qbo_criar_e_enviar_invoice") == "qbo_criar_e_enviar_invoice"
    assert acoes.nome_canonico("google__gmail_rascunho") == "gmail_rascunho"
    n, a = acoes.converter("asana_criar_tarefa", {"projeto_gid": "1205450093098920", "secao_gid": "1205141832260879", "nome": "David Pera_Urace Daily [1/1]", "notas": "x", "vence_em": "2026-09-13"})
    assert n == "asana_criar_do_modelo" and a == {"modelo_gid": acoes.MODELO_SESSAO, "nome": "David Pera_Urace Daily [1/1]", "secao_gid": "1205141832260879", "notas": "x", "vence_em": "2026-09-13", "campos": {"Race": "Practice OKC"}}
    assert acoes.converter("asana_criar_tarefa", {"secao_gid": "outra", "nome": "x"})[0] == "asana_criar_tarefa"
    h = entra(cli, "admin@urace.us")
    ia.RUNNER = lambda texto, sk: (True, 'Criando.\nACAO: asana__asana_criar_tarefa | David Pera | tarefa | {"projeto_gid":"1205450093098920","secao_gid":"1205141832260879","nome":"David Pera_Urace Daily_Using Own Kart [1/1]","vence_em":"2026-09-13"}', None)
    c = espera(cli, cli.post(f"{B}/commands", headers=h, json={"text": "David Pera domingo"}).json()["id"])
    a = c["actions"][0]
    assert a["action"] == "asana_criar_do_modelo" and a["policy"] == "SAFE"
    import json as _j
    assert _j.loads(a["payload"])["args"]["modelo_gid"] == acoes.MODELO_SESSAO
    assert a["status"] in ("FAILED", "DONE") and (a["status"] == "DONE" or "não conectado" in (a["result"] or ""))   # sem Asana no teste: tentou de verdade
    ia.RUNNER = runner_falso


def test_contexto_do_piloto_citado_e_invoice_resolvida_sem_perguntar(cli, monkeypatch):
    """'Filho do Nicolas Pera - David Pera... mesmo esquema' → o comando leva histórico, id do cliente no QBO,
    waiver válida e itens; consulta proposta como ação é descartada; invoice com placeholders é resolvida pelo espelho."""
    from command_center.api import acoes, motor
    from command_center.db import conectar, inserir
    con = conectar()
    try:
        cid = inserir(con, "clients", name="Nicolas Pera", email="peranicolas2106@gmail.com", phone="305-906-2542", pilot_name="David Pera", pilot_dob="2014-05-02", vip=0, status="ACTIVE", source="asana")
        inserir(con, "tasks", client_id=cid, title="David Pera_Urace Daily_Using Own Kart [1/1]", project="U-RACE", section="Finished Services", status="completed", due_on="2026-08-23")
        inserir(con, "invoices", client_id=cid, doc_number="1031", amount=500, balance=0, status="paid", issued_on="2026-08-20", memo="Using Own Kart - David Pera", customer_email="peranicolas2106@gmail.com", customer_ref="696")
        inserir(con, "waivers", client_id=cid, signer_name="Nicolas Pera", signer_email="peranicolas2106@gmail.com", template="parental", status="completed", sent_at="2026-08-15", completed_at="2026-08-16", expires_at="2027-08-16")
        con.execute("INSERT OR REPLACE INTO qbo_items (id, name, full_name, price, type, active) VALUES ('31','Arrive and Drive daily','Arrive and Drive daily',500,'Service',1), ('32','Race Support','Race Support',1200,'Service',1)")
        con.commit()
        assert motor.cliente_citado(con, "Filho do Nicolas Pera - David Pera. Coloca na agenda pro Domingo esta semana.") == cid
        ctx = motor.contexto_do_comando(con, "David Pera domingo, mesmo esquema")
        assert "cliente_id=696" in ctx and "ASSINADA em 2026-08-16" in ctx and "31: Arrive and Drive daily" in ctx and '"idade": 12' in ctx and "Using Own Kart" in ctx
        assert motor.contexto_do_comando(con, "quem tem invoice vencida?") == ""
        # invoice com placeholders → cliente pelo espelho (última invoice), item pelo catálogo, valor do texto
        args, prob = acoes.normalizar_invoice({"cliente_id": "<id de qbo_clientes_buscar>", "linhas": [{"item_id": "<id de qbo_itens_buscar>", "quantidade": 1, "unitario": 0, "descricao": "Arrive and Drive daily - Using Own Kart - David Pera - 2026-09-13"}], "vence_em": "2026-09-13"},
                                             "Invoice de $500 no nome do Nicolas.", None, None, con, "Nicolas Pera")
        assert prob == [] and args["cliente_id"] == "696" and args["linhas"][0]["item_id"] == "31" and args["linhas"][0]["unitario"] == 500.0 and args["email"] == "peranicolas2106@gmail.com"
    finally:
        con.close()
    assert acoes.eh_consulta("qbo_itens_buscar") and acoes.eh_consulta("asana_tarefa") and not acoes.eh_consulta("qbo_criar_e_enviar_invoice") and not acoes.eh_consulta("asana_criar_do_modelo")
    h = entra(cli, "admin@urace.us")
    ia.RUNNER = lambda texto, sk: (True, ('Vou montar a invoice de $500.\n'
                                          'ACAO: qbo_clientes_buscar | Nicolas Pera | achar o cliente | {"texto":"peranicolas2106@gmail.com"}\n'
                                          'ACAO: qbo_criar_e_enviar_invoice | Nicolas Pera | invoice | {"cliente_id":"<id>","linhas":[{"item_id":"<id>","quantidade":1,"unitario":500,"descricao":"Arrive and Drive daily - David Pera - 2026-09-13"}],"vence_em":"2026-09-13"}'), None)
    c = espera(cli, cli.post(f"{B}/commands", headers=h, json={"text": "Filho do Nicolas Pera - David Pera. Domingo, mesmo esquema."}).json()["id"])
    assert "CONTEXTO DO PAINEL sobre David Pera" in c["prompt"] and "cliente_id=696" in c["prompt"]
    vivas = [a for a in c["actions"] if a["status"] == "PROPOSED"]
    assert [a["action"] for a in vivas] == ["qbo_criar_e_enviar_invoice"] and all(a["action"] != "qbo_clientes_buscar" for a in c["actions"])
    import json as _j
    p = _j.loads(vivas[0]["payload"])
    assert not p.get("problemas") and p["args"]["cliente_id"] == "696" and p["args"]["linhas"][0]["item_id"] == "31"
    assert cli.get(f"{B}/actions/{vivas[0]['id']}").json()["status"] == "PROPOSED"
    ia.RUNNER = runner_falso


def test_tarefa_com_descricao_padrao_race_okc_e_link_da_invoice_de_volta(cli, monkeypatch):
    from command_center.api import acoes, motor
    from command_center.db import conectar, inserir, um
    con = conectar()
    try:
        cid = um(con, "SELECT id FROM clients WHERE pilot_name='David Pera'")["id"]
        n, a = acoes.converter("asana_criar_tarefa", {"projeto_gid": "1205450093098920", "secao_gid": "1205141832260879", "nome": "David Pera_Urace Daily_Using Own Kart [1/1]",
                                                     "notas": "Driver's name: David Pera\nInvoice link:   Price: $500", "vence_em": "2026-09-13"}, con, "David Pera domingo mesmo esquema")
        assert n == "asana_criar_do_modelo" and a["campos"] == {"Race": "Practice OKC"}
        notas = a["notas"]
        assert "Service Dates for this Month: 09/13/2026" in notas and "Date of Birth: 05/02/2014" in notas and "Age: 12  (menor: waiver parental)" in notas
        assert "Responsible Name: Nicolas Pera" in notas and "Email: peranicolas2106@gmail.com" in notas and "Product: Urace Daily / Using Own Kart" in notas
        assert "Invoice link: (a IA preenche quando a invoice sair)\nPrice: $500.00\n\nSecurity deposit: —\nPrice: —" in notas and "Height: —\nWeight: —\nWaist: —" in notas
        n2, a2 = acoes.converter("asana_criar_do_modelo", {"modelo_gid": "x", "nome": "David Pera_Urace Daily_2T [1/1]", "secao_gid": "1205141832260879"}, con, "treino em Bushnell")
        assert a2["campos"] == {"Race": "Practice Bushnell"}
        assert "campos" not in acoes.converter("asana_criar_do_modelo", {"modelo_gid": "x", "nome": "ROK Cup Round 5 [Orlando]", "secao_gid": "s"}, None, "")[1]
        # invoice executada → link volta para a tarefa criada no mesmo comando
        cmd = inserir(con, "ai_commands", user_id=1, text="x", session_key="s", status="DONE")
        inserir(con, "ai_actions", command_id=cmd, action="asana_criar_do_modelo", system="asana", policy="SAFE", status="DONE", payload="{}", result='{"aplicado": true, "gid": "999001"}')
        aid = inserir(con, "ai_actions", command_id=cmd, action="qbo_criar_e_enviar_invoice", system="qbo", policy="REQUIRES_APPROVAL", status="APPROVED",
                      payload=json.dumps({"args": {"cliente_id": "696", "linhas": [{"item_id": "31", "quantidade": 1, "unitario": 500, "descricao": "x"}], "vence_em": "2026-09-13", "email": "peranicolas2106@gmail.com"}}))
        con.commit()
        assert motor._tarefa_da_invoice(con, {"command_id": cmd}, {"email": "peranicolas2106@gmail.com", "vence_em": "2026-09-13"}) == "999001"
    finally:
        con.close()
    preenchidos = []

    class Qbo:
        pass
    monkeypatch.setattr(motor, "chamar", lambda sistema, acao, **a: {"id": "1042", "link": "https://qbo.intuit.com/app/invoice?txnId=1042", "total": 500.0, "enviado": True}, raising=False)
    import command_center.providers as prov

    class As:
        def preencher_invoice_na_tarefa(self, gid, link, valor=None, deposito=False): preenchidos.append((gid, link, valor, deposito)); return {"aplicado": True}
    monkeypatch.setattr(prov, "modulo", lambda s: As())
    monkeypatch.setattr(prov, "chamar", lambda sistema, acao, **a: {"id": "1042", "link": "https://qbo.intuit.com/app/invoice?txnId=1042", "total": 500.0, "enviado": True})
    motor.executar_acao(aid, 1)
    con = conectar()
    try:
        assert um(con, "SELECT status FROM ai_actions WHERE id=?", (aid,))["status"] == "DONE"
        assert um(con, "SELECT 1 AS x FROM audit_logs WHERE event='asana.invoice_link'") is not None
    finally:
        con.close()
    assert preenchidos == [("999001", "https://qbo.intuit.com/app/invoice?txnId=1042", 500.0, False)]
    # security deposit: mesmo procedimento, na linha 'Security deposit:'
    con = conectar()
    try:
        aid2 = inserir(con, "ai_actions", command_id=cmd, action="qbo_criar_e_enviar_invoice", system="qbo", policy="REQUIRES_APPROVAL", status="APPROVED",
                       payload=json.dumps({"args": {"cliente_id": "696", "linhas": [{"item_id": "40", "quantidade": 1, "unitario": 400, "descricao": "Security deposit - David Pera"}], "vence_em": "2026-09-13"}}))
        con.commit()
    finally:
        con.close()
    motor.executar_acao(aid2, 1)
    assert preenchidos[-1] == ("999001", "https://qbo.intuit.com/app/invoice?txnId=1042", 500.0, True)


def test_consulta_executada_na_hora_e_item_criado_quando_nao_existe(cli, monkeypatch):
    """Busca listada pelo agente é executada pelo painel e volta como resultado na mesma conversa;
    produto que não existe no QBO é criado com o valor (só o envio da invoice fica para o dono)."""
    from command_center.api import acoes
    from command_center.db import conectar, um
    import command_center.providers as prov
    criados, buscas = [], []

    class Qbo:
        def qbo_itens_buscar(self, termos=None, texto=None): buscas.append(termos or texto); return [{"termo": texto or termos, "found": False, "itens": []}]
        def criar_item_sistema(self, nome, preco=0, descricao=None): criados.append((nome, preco)); return {"id": "77", "nome": nome}
    monkeypatch.setattr(prov, "modulo", lambda s: Qbo())
    chamadas = []

    def runner(texto, sk):
        chamadas.append(texto)
        if "Executei as consultas" in texto:
            assert "qbo_itens_buscar" in texto and '"found": false' in texto
            return True, ('Item não existe: crio e monto a invoice de $500.\n'
                          'ACAO: qbo_criar_e_enviar_invoice | Nicolas Pera | invoice | {"cliente_id":"696","linhas":[{"item":"Urace Daily","quantidade":1,"unitario":500,"descricao":"Urace Daily - Using Own Kart - David Pera - 2026-09-20"}],"vence_em":"2026-09-20"}'), None
        return True, ('Vou procurar o item.\nACAO: qbo_itens_buscar | Urace Daily | achar o item | {"texto":"Urace Daily"}'), None
    ia.RUNNER = runner
    h = entra(cli, "admin@urace.us")
    c = espera(cli, cli.post(f"{B}/commands", headers=h, json={"text": "David Pera dia 20, Urace Daily, invoice de $500"}).json()["id"], timeout=8)
    assert len(chamadas) == 2 and buscas == ["Urace Daily"]
    acs = [a for a in c["actions"] if a["status"] == "PROPOSED"]
    assert [a["action"] for a in acs] == ["qbo_criar_e_enviar_invoice"]
    p = json.loads(acs[0]["payload"])
    assert not p.get("problemas") and p["args"]["linhas"][0]["item_id"] == "77" and criados == [("Urace Daily", 500.0)]
    assert "criado no QuickBooks (id 77" in c["output"]
    con = conectar()
    try:
        assert um(con, "SELECT name FROM qbo_items WHERE id='77'")["name"] == "Urace Daily"
    finally:
        con.close()
    assert acoes._nome_de_produto("Arrive and Drive daily - David Pera - 2026-09-13") == "Arrive and Drive daily"
    assert acoes._nome_de_produto("Coisa qualquer", None) is None
    ia.RUNNER = runner_falso


def test_uma_conversa_por_usuario_e_automatica_separada(cli):
    from command_center.db import conectar, inserir
    con = conectar()
    try:
        op = con.execute("SELECT id FROM users WHERE email='op@urace.us'").fetchone()[0]
        inserir(con, "ai_commands", user_id=op, text="pergunta do operador", session_key="s", status="DONE", output="resposta")
        inserir(con, "ai_commands", user_id=1, text="EVENTO AUTOMÁTICO: task.overdue — x", session_key="s", status="DONE", output="movi")
        con.commit()
    finally:
        con.close()
    # operador: só a própria conversa; sem a automática; sem ver a do admin
    h = entra(cli, "op@urace.us")
    t = cli.get(f"{B}/threads").json()
    assert [x["id"] for x in t["threads"]] == [op] and t["auto"] is None
    mine = cli.get(f"{B}/thread").json()
    assert all(c["user_id"] == op for c in mine["commands"]) and any(c["text"] == "pergunta do operador" for c in mine["commands"])
    assert not any(c["text"].startswith("EVENTO") for c in mine["commands"])
    assert all(c["user_id"] == op for c in cli.get(f"{B}/thread?user_id=1").json()["commands"])     # não escala para outro usuário
    assert cli.get(f"{B}/thread?kind=auto").status_code == 403
    # admin: vê todas, a do operador e a automática; ordem cronológica com ações embutidas
    h = entra(cli, "admin@urace.us")
    t = cli.get(f"{B}/threads").json()
    assert op in [x["id"] for x in t["threads"]] and t["auto"]["n"] >= 1
    do_op = cli.get(f"{B}/thread?user_id={op}").json()["commands"]
    assert all(c["user_id"] == op for c in do_op) and "pergunta do operador" in [c["text"] for c in do_op]
    auto = cli.get(f"{B}/thread?kind=auto").json()["commands"]
    assert auto and all(c["text"].startswith(("EVENTO AUTOMÁTICO", "TAREFA:")) for c in auto)
    minha = cli.get(f"{B}/thread?limit=2").json()
    assert len(minha["commands"]) == 2 and minha["has_more"] and minha["commands"][0]["id"] < minha["commands"][1]["id"] and "actions" in minha["commands"][0]
    antes = cli.get(f"{B}/thread?limit=2&before={minha['commands'][0]['id']}").json()["commands"]
    assert all(c["id"] < minha["commands"][0]["id"] for c in antes)


def test_continuar_sem_citar_o_piloto_usa_o_ultimo_da_conversa(cli):
    """"pode continuar com a invoice" → o contexto do painel vem do último piloto citado hoje nesta conversa."""
    from command_center.api import motor
    from command_center.db import conectar
    h = entra(cli, "admin@urace.us")
    ia.RUNNER = lambda texto, sk: (True, "Ok.\nACAO: nenhuma", None)
    espera(cli, cli.post(f"{B}/commands", headers=h, json={"text": "David Pera domingo que vem, mesmo esquema"}).json()["id"])
    c = espera(cli, cli.post(f"{B}/commands", headers=h, json={"text": "pode continuar com a montagem da invoice"}).json()["id"])
    assert "CONTEXTO DO PAINEL sobre David Pera" in c["prompt"] and c["text"] == "pode continuar com a montagem da invoice"
    con = conectar()
    try:
        assert motor.contexto_do_comando(con, "e aí?", user_id=None) == ""
    finally:
        con.close()
    ia.RUNNER = runner_falso


def test_completar_proposta_incompleta_pelo_painel(cli, monkeypatch):
    """Proposta antiga 'sem item': o botão Completar acha/cria o item e resolve o cliente sem nova rodada da IA."""
    from command_center.db import conectar, inserir
    import command_center.providers as prov
    con = conectar()
    try:
        cmd = inserir(con, "ai_commands", user_id=1, text="x", session_key="s", status="DONE", output="Invoice de $500.")
        aid = inserir(con, "ai_actions", command_id=cmd, action="qbo_criar_e_enviar_invoice", system="qbo", policy="REQUIRES_APPROVAL", status="PROPOSED",
                      payload=json.dumps({"alvo": "Nicolas Pera", "args": {"cliente_id": "696", "email": "peranicolas2106@gmail.com", "vence_em": "2026-09-13",
                                                                             "linhas": [{"item_id": "", "quantidade": 1, "unitario": 500, "descricao": "Urace Daily - Using Own Kart - David Pera - 2026-09-13"}]},
                                          "problemas": ["linha sem item do QuickBooks"]}), reason="incompleta: linha sem item do QuickBooks")
        inserir(con, "approvals", action_id=aid); con.commit()
    finally:
        con.close()
    criados = []

    class Qbo:
        def criar_item_sistema(self, nome, preco=0, descricao=None): criados.append((nome, preco)); return {"id": "88", "nome": nome}
        def qbo_itens_buscar(self, termos=None, texto=None): return [{"found": False, "itens": []}]
    monkeypatch.setattr(prov, "modulo", lambda s: Qbo())
    h = entra(cli, "admin@urace.us")
    r = cli.post(f"{B}/actions/{aid}/complete", headers=h)
    assert r.status_code == 200 and r.json()["ok"]
    a = cli.get(f"{B}/actions/{aid}").json()
    p = json.loads(a["payload"])
    # o item vem do catálogo espelhado (se já existir) ou é criado na hora (id 88)
    assert p["args"]["linhas"][0]["item_id"] and (criados == [] or p["args"]["linhas"][0]["item_id"] == "88")
    assert not p.get("problemas") and a["reason"].startswith("completada pelo painel")
    assert cli.post(f"{B}/actions/{aid}/complete", headers=entra(cli, "viewer@urace.us")).status_code == 403


def test_invoice_vence_2_dias_antes_e_memo_com_data_do_servico(cli):
    from command_center.api import acoes
    from command_center.db import conectar, inserir, um
    con = conectar()
    try:
        cid = um(con, "SELECT id FROM clients WHERE pilot_name='David Pera'")["id"]
        inserir(con, "tasks", client_id=cid, title="David Pera_Urace Daily_Using Own Kart [1/1]", project="U-RACE", section="SUNDAY", status="open", due_on="2026-09-13")
        con.commit()
        # o agente manda o dia do serviço como vencimento: o painel entende (bate com a tarefa) e corrige
        args, prob = acoes.normalizar_invoice({"cliente_id": "696", "email": "peranicolas2106@gmail.com", "vence_em": "2026-09-13",
                                               "linhas": [{"item_id": "31", "quantidade": 1, "unitario": 500, "descricao": "Urace Daily - Using Own Kart - David Pera - 2026-09-13"}]},
                                              "", None, None, con, "Nicolas Pera")
        assert prob == [] and args["data_servico"] == "2026-09-13" and args["vence_em"] == "2026-09-11"
        assert args["memo"] == "Urace Daily | Using Own Kart | David Pera | Service date: 09/13/2026" and args["nota_privada"] == args["memo"]
        # com data_servico explícita e memo sem data: memo ganha a data; vencimento = -2
        args, _ = acoes.normalizar_invoice({"cliente_id": "696", "data_servico": "09/20/2026", "memo": "Academy daily | Using Own Kart",
                                            "linhas": [{"item_id": "31", "unitario": 500, "descricao": "Urace Daily - Using Own Kart - David Pera"}]}, "", None, None, con, "Nicolas Pera")
        assert args["vence_em"] == "2026-09-18" and "Service date: 09/20/2026" in args["memo"] and args["nota_privada"] == args["memo"]
        assert acoes.memo_invoice("Urace Daily", "2 stroke", "Théo", "2026-10-03") == "Urace Daily | 2 stroke | Théo | Service date: 10/03/2026"
    finally:
        con.close()

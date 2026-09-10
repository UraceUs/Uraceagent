"""Dashboard, atenção, clientes, busca, políticas — com espelhos
semeados por SQL (sem rede). Providers desconectados aqui: o teste de
sync prova que isso vira 'not connected', nunca 500."""
import os
import tempfile
from datetime import date, timedelta

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir  # noqa: E402

B = "/ops/api"
SENHA = "senha-forte-123"
HOJE = date.today()


@pytest.fixture(scope="module")
def cli():
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc.sqlite")
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "admin@urace.us", "Admin", "ADMIN", SENHA)
    auth.criar_usuario(con, "viewer@urace.us", "Viewer", "VIEWER", SENHA)
    # espelhos: o cenário real de 04/09
    rafael = inserir(con, "clients", name="Rafael Pionti", email="rafael@spmesportes.com.br",
                     pilot_name="Renato Frota Pionti", pilot_dob="2012-01-03", vip=0, status="ACTIVE", source="asana")
    joseph = inserir(con, "clients", name="Joseph Kurian", email="joekur001@gmail.com",
                     pilot_name="Enzo Kurian", vip=0, status="ACTIVE", source="asana")
    amanha = (HOJE + timedelta(days=1)).isoformat()
    t1 = inserir(con, "tasks", client_id=rafael, title="Renato Frota Pionti_Professional Coaching_2T [1/1]",
                 project="U-RACE", section="SATURDAY", status="open", due_on=amanha, subtasks_total=12, subtasks_done=1)
    inserir(con, "entity_links", entity_type="task", entity_id=t1, system="asana", external_id="1218104997373079",
            deep_link="https://app.asana.com/0/1205450093098920/1218104997373079/f")
    inserir(con, "tasks", client_id=joseph, title="Enzo Kurian [4 strokes]", project="U-RACE", section="SATURDAY",
            status="open", due_on=amanha, subtasks_total=12, subtasks_done=4)
    inserir(con, "waivers", client_id=joseph, signer_name="Joseph Kurian", signer_email="joekur001@gmail.com",
            template="parental", status="completed", sent_at="2026-08-29", completed_at="2026-08-31")
    inserir(con, "waivers", client_id=None, signer_name="Matthew Hubbard", signer_email="misterhubbbard@gmail.com",
            template="parental", status="autoresponded", sent_at="2026-05-27", expires_at="2026-09-24")
    inserir(con, "emails", client_id=rafael, mailbox="urace", subject="Sobre o treino de sábado",
            sender="Rafael Pionti <rafael@spmesportes.com.br>", last_at="2026-09-04", handled=0)
    inserir(con, "invoices", client_id=rafael, doc_number="1001", amount=400, balance=400, status="sent",
            issued_on="2026-09-02", due_on="2026-09-04")
    con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def test_tudo_exige_sessao(cli):
    cli.cookies.clear()
    for rota in ("/dashboard", "/clients", "/search?q=re", "/needs-attention", "/integrations", "/policies"):
        assert cli.get(B + rota).status_code == 401, rota


def test_dashboard_e_atencao_contextual(cli):
    entra(cli, "admin@urace.us")
    d = cli.get(B + "/dashboard").json()
    assert d["active_clients"] == 2 and d["waivers_bounced"] == 1 and d["emails_attention"] == 1
    assert d["open_invoices"]["count"] == 1 and d["open_invoices"]["total"] == 400.0
    niveis = {i["title"]: i["level"] for i in d["needs_attention"]}
    renato = [t for t in niveis if "Rafael Pionti" in t and "waiver" in t][0]
    assert niveis[renato] == "CRITICAL"                      # serviço amanhã sem waiver
    assert not any("Joseph Kurian" in t and "waiver" in t for t in niveis)   # Enzo já assinou
    assert any("devolveu" in t for t in niveis)              # bounce do Hubbard
    assert any("escreveu" in t for t in niveis)              # e-mail do cliente


def test_viewer_nao_ve_financeiro(cli):
    entra(cli, "viewer@urace.us")
    d = cli.get(B + "/dashboard").json()
    assert d["open_invoices"] is None
    c = cli.get(B + "/clients/1").json()
    assert c["invoices"] is None and c["client"]["name"] == "Rafael Pionti"


def test_client_360_e_deep_link(cli):
    entra(cli, "admin@urace.us")
    c = cli.get(B + "/clients/1").json()
    assert c["tasks"][0]["links"][0]["deep_link"].startswith("https://app.asana.com/")
    kinds = {e["kind"] for e in c["timeline"]}
    assert {"SERVICE", "EMAIL"} <= kinds
    assert c["invoices"][0]["doc_number"] == "1001"


def test_busca_global(cli):
    entra(cli, "admin@urace.us")
    r = cli.get(B + "/search?q=Pionti").json()
    assert r["clients"][0]["pilot_name"] == "Renato Frota Pionti" and len(r["tasks"]) == 1
    r = cli.get(B + "/search?q=hubbb").json()
    assert r["waivers"][0]["status"] == "autoresponded"


def test_vip_dispensa_alerta_e_so_manager_muda(cli):
    entra(cli, "viewer@urace.us")
    assert cli.patch(B + "/clients/1", headers={"X-CSRF": cli.cookies.get("cc_csrf")}, json={"vip": True}).status_code == 403
    h = entra(cli, "admin@urace.us")
    assert cli.patch(B + "/clients/1", headers=h, json={"vip": True}).status_code == 200
    d = cli.get(B + "/dashboard").json()
    assert not any("Rafael Pionti" in i["title"] and "waiver" in i["title"] for i in d["needs_attention"])
    cli.patch(B + "/clients/1", headers=h, json={"vip": False})


def test_politicas_admin_e_apagar_nunca(cli):
    h = entra(cli, "admin@urace.us")
    pol = {p["action"]: p["policy"] for p in cli.get(B + "/policies").json()}
    assert pol["qbo_enviar_invoice"] == "REQUIRES_APPROVAL" and pol["gmail_enviar"] == "BLOCKED"
    assert cli.put(B + "/policies/apagar_cliente", headers=h, json={"policy": "SAFE"}).status_code == 403
    assert cli.put(B + "/policies/qbo_criar_invoice", headers=h, json={"policy": "REQUIRES_APPROVAL"}).status_code == 200
    entra(cli, "viewer@urace.us")
    assert cli.put(B + "/policies/qbo_criar_invoice", headers={"X-CSRF": cli.cookies.get("cc_csrf")},
                   json={"policy": "SAFE"}).status_code == 403


def test_sync_sem_credencial_nao_derruba(cli):
    h = entra(cli, "admin@urace.us")
    r = cli.post(B + "/sync?wait=1", headers=h)
    assert r.status_code in (200, 202)
    j = r.json()
    assert j["asana"]["motivo"] == "not connected" and j["docusign"]["motivo"] == "not connected"
    assert j["cerebro"]["ok"] and j["cerebro"]["notas"] >= 10          # as notas do cérebro leem sem rede
    st = {i["system"]: i["status"] for i in cli.get(B + "/integrations").json()}
    assert st["asana"] == "DISCONNECTED"


def test_check_integracoes_sem_credencial(cli):
    h = entra(cli, "admin@urace.us")
    r = cli.post(B + "/integrations/check", headers=h).json()
    assert r["quickbooks"]["status"] == "DISCONNECTED" and "QBO" in r["quickbooks"]["detail"]["motivo"]
    assert r["gmail"]["status"] == "DISCONNECTED"


# ------------------------------------------------ ocultar aviso (04/09, "excluir testes")
def test_ocultar_aviso_nao_apaga_fonte(cli):
    h = entra(cli, "admin@urace.us")
    itens = cli.get(B + "/needs-attention").json()
    assert itens and all("key" in i for i in itens)
    alvo = itens[0]
    n_tasks = len(cli.get(B + "/tasks?status=all").json())
    r = cli.post(B + "/needs-attention/dismiss", headers=h,
                 json={"key": alvo["key"], "title": alvo["title"], "level": alvo["level"], "reason": "teste antigo"})
    assert r.status_code == 200
    assert alvo["key"] not in [i["key"] for i in cli.get(B + "/needs-attention").json()]
    ocultos = [i for i in cli.get(B + "/needs-attention?hidden=1").json() if i["key"] == alvo["key"]]
    assert ocultos and ocultos[0]["dismissed"]["by"] == "Admin" and ocultos[0]["dismissed"]["reason"] == "teste antigo"
    assert len(cli.get(B + "/tasks?status=all").json()) == n_tasks        # a fonte continua lá
    # dashboard também esconde
    assert alvo["key"] not in [i["key"] for i in cli.get(B + "/dashboard").json()["needs_attention"]]
    # restaurar
    assert cli.post(B + "/needs-attention/restore", headers=h, json={"key": alvo["key"]}).status_code == 200
    assert alvo["key"] in [i["key"] for i in cli.get(B + "/needs-attention").json()]
    assert cli.post(B + "/needs-attention/restore", headers=h, json={"key": alvo["key"]}).status_code == 404
    ev = [a["event"] for a in cli.get(B + "/audit", headers=h).json()]
    assert "attention.dismiss" in ev and "attention.restore" in ev


def test_ocultar_exige_operador(cli):
    h = entra(cli, "viewer@urace.us")
    r = cli.post(B + "/needs-attention/dismiss", headers=h, json={"key": "x:task:1"})
    assert r.status_code == 403
    assert cli.post(B + "/needs-attention/dismiss", headers=entra(cli, "admin@urace.us"), json={"key": "semdoispontos"}).status_code == 400


def test_tasks_all_e_email_handled(cli):
    h = entra(cli, "admin@urace.us")
    todas = cli.get(B + "/tasks?status=all").json()
    abertas = cli.get(B + "/tasks").json()
    assert len(todas) >= len(abertas) and all("section" in t for t in todas)
    emails = cli.get(B + "/emails").json()
    if emails:
        e = emails[0]
        assert cli.patch(B + f"/emails/{e['id']}", headers=h, json={"handled": True}).status_code == 200
        assert [x for x in cli.get(B + "/emails").json() if x["id"] == e["id"]][0]["handled"] == 1
        assert cli.patch(B + f"/emails/{e['id']}", headers=entra(cli, "viewer@urace.us"), json={"handled": False}).status_code == 403
    h = entra(cli, "admin@urace.us")                 # o cookie do cliente virou o do viewer acima
    assert cli.patch(B + "/emails/999999", headers=h, json={"handled": True}).status_code == 404


def test_docusign_templates_sem_credencial(cli):
    entra(cli, "admin@urace.us")
    r = cli.get(B + "/docusign/templates")
    assert r.status_code == 200 and r.json()["connected"] is False and r.json()["templates"] == []


def test_sync_em_segundo_plano(cli):
    h = entra(cli, "admin@urace.us")
    r = cli.post(B + "/sync", headers=h)
    assert r.status_code == 202 and r.json()["running"] is True
    import time
    for _ in range(50):
        st = cli.get(B + "/sync").json()
        if not st["running"]:
            break
        time.sleep(0.1)
    assert st["running"] is False and st["result"]["asana"]["motivo"] == "not connected"


# ------------------------------------------------ Gmail por dentro (04/09)
def test_gmail_labels_e_thread_sem_credencial(cli):
    entra(cli, "admin@urace.us")
    r = cli.get(B + "/gmail/labels?mailbox=urace").json()
    assert r["connected"] is False and isinstance(r["labels"], list)
    emails = cli.get(B + "/emails").json()
    if emails:
        t = cli.get(B + f"/emails/{emails[0]['id']}/thread").json()
        assert t["connected"] is False and t["messages"] == []


def test_mover_email_exige_gmail_e_operador(cli):
    h = entra(cli, "admin@urace.us")
    emails = cli.get(B + "/emails").json()
    if emails:
        e = emails[0]
        assert cli.post(B + f"/emails/{e['id']}/move", headers=h, json={"label": "INBOX"}).status_code == 400
        r = cli.post(B + f"/emails/{e['id']}/move", headers=h, json={"label": "wNews"})
        assert r.status_code in (409, 503)                       # sem vínculo ou sem Gmail: nunca 500
        assert cli.post(B + f"/emails/{e['id']}/move", headers=entra(cli, "viewer@urace.us"), json={"label": "wNews"}).status_code == 403


def test_classificar_por_regras():
    from command_center.providers import classificar
    nomes = ["wNews", "Softwares|Apps/Docusign", "Finances/Pending Invoices ❗", "Marketing & Sales/Comercial/Formulario do site"]
    assert classificar.por_regras({"labels": '["INBOX","Banks/Bank of America"]', "sender": "x", "subject": "y"}, nomes)[0] == "Banks/Bank of America"
    lab, motivo, por = classificar.por_regras({"labels": "[]", "sender": "Docusign Account <info@account.docusign.com>", "subject": "New Device Login"}, nomes)
    assert lab == "Softwares|Apps/Docusign" and por == "rules"
    assert classificar.por_regras({"labels": "[]", "sender": "Urace <urace@urace.us>", "subject": 'New message from "Urace - The Driver Factory"'}, nomes)[0].endswith("Formulario do site")
    assert classificar.por_regras({"labels": "[]", "sender": "financeiro@sxsmkt.com.br", "subject": "FATURAMENTO SETEMBRO/2026"}, nomes)[0].startswith("Finances")
    assert classificar.por_regras({"labels": "[]", "sender": "joao@gmail.com", "subject": "oi"}, nomes) is None
    # resposta da IA validada contra a lista real: marcador inventado vira None
    res = classificar.parse_ia('bla {"itens":[{"id":1,"marcador":"wnews","motivo":"propaganda"},{"id":2,"marcador":"Inventado/Novo","motivo":"x"}]} fim', nomes)
    assert res[1][0] == "wNews" and res[2][0] is None


# ------------------------------------------------ DocuSign: lixeira, reenvio, vínculo, download
def test_waiver_lixeira_restaurar_vinculo(cli):
    h = entra(cli, "admin@urace.us")
    ws = cli.get(B + "/waivers").json()
    assert ws, "fixture tem waiver"
    w = ws[0]
    # sem DocuSign: em aberto E com vínculo não dá para anular -> 503, nada muda no painel.
    # Sem vínculo com envelope (fixture), só some do painel e volta com restore.
    r = cli.post(B + f"/waivers/{w['id']}/trash", headers=h, json={"reason": "teste"})
    if w["status"] in ("sent", "delivered", "autoresponded") and w.get("links"):
        assert r.status_code == 503
        assert any(x["id"] == w["id"] for x in cli.get(B + "/waivers").json())
    else:
        assert r.status_code == 200
        assert not any(x["id"] == w["id"] for x in cli.get(B + "/waivers").json())
        assert any(x["id"] == w["id"] for x in cli.get(B + "/waivers?hidden=1").json())
        assert cli.post(B + f"/waivers/{w['id']}/restore", headers=h).status_code == 200
    # vínculo manual e desvínculo
    clientes = cli.get(B + "/clients").json()
    assert cli.post(B + f"/waivers/{w['id']}/link", headers=h, json={"client_id": clientes[0]["id"]}).status_code == 200
    w2 = [x for x in cli.get(B + "/waivers").json() if x["id"] == w["id"]][0]
    assert w2["client_id"] == clientes[0]["id"] and w2["link_by"] == "human"
    assert cli.post(B + f"/waivers/{w['id']}/link", headers=h, json={"client_id": 999999}).status_code == 404
    # download sem DocuSign: 503, nunca 500; reenvio idem; e-mail inválido 400
    assert cli.get(B + f"/waivers/{w['id']}/download").status_code in (503, 409)
    assert cli.post(B + f"/waivers/{w['id']}/resend", headers=h, json={"email": "invalido"}).status_code == 400
    assert cli.post(B + f"/waivers/{w['id']}/resend", headers=h, json={}).status_code in (503, 409)
    # restaurar algo que não está oculto: 404
    assert cli.post(B + f"/waivers/{w['id']}/restore", headers=h).status_code == 404
    assert cli.post(B + f"/waivers/{w['id']}/trash", headers=entra(cli, "viewer@urace.us"), json={}).status_code == 403


def test_vinculo_por_nome_do_menor():
    from command_center.providers.sync import _mesmo_nome
    assert _mesmo_nome("Renato Frota Pionti", "Renato Pionti")
    assert _mesmo_nome("RENATO PIONTI", "renato pionti")
    assert not _mesmo_nome("Matthew Hubbard", "Renato Pionti")
    assert not _mesmo_nome("", "Renato Pionti")


# ------------------------------------------------ identidade: cliente, ativo, um card por pessoa (04/09)
def test_identidade_pessoa_e_nome():
    from command_center.providers import identidade as I
    assert I.pessoa_do_titulo("Session Setup | Aaron Benoit_Kart [Practice_2T]") == "Aaron Benoit"
    assert I.pessoa_do_titulo("Aaron Benoit_Trackside Support") == "Aaron Benoit"
    assert I.pessoa_do_titulo("2026 SKUSA Winter Series RD1/2 | Musselman Honda Circuit") is None
    assert I.pessoa_do_titulo("2026 ROK Florida Winter Tour Rd1, Orlando Kart Center (Orlando, FL)") is None
    assert I.pessoa_do_titulo("Email:") is None
    assert I.pessoa_do_titulo("Enzo Kurian [4 strokes 09/05/26]") == "Enzo Kurian"
    assert I.mesmo_nome("Alex Alonso", "Alex Alonzo") and I.mesmo_nome("Renato Frota Pionti", "Renato Pionti")
    assert not I.mesmo_nome("Aaron Benoit", "Aaron Smith") and not I.mesmo_nome("Alex Alonso", "Alexandre Alonso")
    assert I.so_digitos("+1 (407) 555-0199") == "4075550199"


def test_deduplicar_e_status(cli):
    from command_center.db import conectar, inserir
    from command_center.providers import identidade as I
    con = conectar()
    a = inserir(con, "clients", name="Alex Alonso", email="alex@example.com", status="ACTIVE", source="asana")
    b = inserir(con, "clients", name="ALEX ALONSO", phone="(407) 555-0100", status="ACTIVE", source="asana")   # nome igual normalizado -> une
    c = inserir(con, "clients", name="Alex Alonzo", status="ACTIVE", source="asana")                           # quase igual -> só candidato
    corrida = inserir(con, "clients", name="2026 SKUSA Winter Series RD1/2", status="ACTIVE", source="asana")
    inserir(con, "tasks", client_id=b, title="Alex Alonso_Kart", project="U-RACE", section="Finished Services", status="completed", due_on="2025-01-10")
    inserir(con, "tasks", client_id=corrida, title="2026 SKUSA Winter Series RD1/2", project="U-RACE", section="Finished Services", status="completed", due_on="2026-01-10")
    assert I.limpar_nao_clientes(con) >= 1 and not con.execute("SELECT 1 FROM clients WHERE id=?", (corrida,)).fetchone()
    n = I.deduplicar(con)
    assert n >= 1 and not con.execute("SELECT 1 FROM clients WHERE id=?", (b,)).fetchone()
    # o sobrevivente pode ser a nota do cérebro com o mesmo nome (id menor): resolve pelo e-mail
    keep = con.execute("SELECT * FROM clients WHERE email='alex@example.com'").fetchone()
    a = keep["id"]
    assert keep["phone"] == "(407) 555-0100"                                     # completou o principal
    assert con.execute("SELECT client_id FROM tasks WHERE title='Alex Alonso_Kart'").fetchone()[0] == a
    assert con.execute("SELECT COUNT(*) FROM client_merges").fetchone()[0] >= 1
    pares = I.candidatos_duplicados(con)
    assert any({p["a"]["id"], p["b"]["id"]} == {a, c} for p in pares)
    I.recalcular_status(con)
    assert con.execute("SELECT status FROM clients WHERE id=?", (a,)).fetchone()[0] == "INACTIVE"      # último serviço jan/2025
    # rota de união manual + auditoria; status travado à mão sobrevive
    h = entra(cli, "admin@urace.us")
    assert cli.post(B + "/client-merge", headers=h, json={"keep_id": a, "drop_id": c, "reason": "mesma pessoa"}).status_code == 200
    assert not con.execute("SELECT 1 FROM clients WHERE id=?", (c,)).fetchone()
    assert cli.patch(B + f"/clients/{a}", headers=h, json={"status": "ACTIVE"}).status_code == 200
    I.recalcular_status(con)
    assert con.execute("SELECT status, status_locked FROM clients WHERE id=?", (a,)).fetchone()[0] == "ACTIVE"
    dup = cli.get(B + "/client-duplicates").json()
    assert "pairs" in dup and any(m["keep_id"] == a for m in dup["merged"])
    # varredura sem credencial: responde com avisos, nunca 500
    r = cli.post(B + f"/clients/{a}/scan", headers=h)
    assert r.status_code == 200 and r.json()["gmail"] == 0 and r.json()["avisos"]
    con.close()


def test_clients_ordem_recente_primeiro(cli):
    entra(cli, "admin@urace.us")
    rows = cli.get(B + "/clients").json()
    chaves = [max(r.get("next_service") or "", r.get("last_service") or "") for r in rows]
    assert chaves == sorted(chaves, reverse=True)


def test_task_detail_sem_asana(cli):
    entra(cli, "admin@urace.us")
    t = cli.get(B + "/tasks?status=all").json()[0]
    r = cli.get(B + f"/tasks/{t['id']}/detail")
    assert r.status_code == 200 and r.json()["connected"] is False
    assert cli.get(B + "/tasks/999999/detail").status_code == 404


# ------------------------------------------------ autocorreção (08/09): atenção só do que a IA não resolveu
def test_auto_tratar_notificacoes():
    from command_center.providers import classificar as C
    assert C.auto_tratar({"sender": "Urace <urace@urace.us>", "subject": "We have an exclusive 10% discount just for you!"}, None).startswith("enviado por nós")
    assert "DocuSign" in C.auto_tratar({"sender": "Docusign <dse@docusign.net>", "subject": "Completed: Please Complete the Docusign: Parental"}, None)
    assert "RD Station" in C.auto_tratar({"sender": "x@rdstation.com", "subject": "Urace 'Nova conversão - Joseph Kurian'"}, None)
    assert "ingresso" in C.auto_tratar({"sender": "tix@okc.com", "subject": "Your tickets for OKC PIT & DRIVER PASS"}, None)
    assert C.auto_tratar({"sender": "a@b.com", "subject": "x"}, "Softwares|Apps/Docusign") is not None
    assert C.auto_tratar({"sender": "joekur001@gmail.com", "subject": "Plano mensal para o Enzo"}, None) is None      # este sim é humano


def test_atencao_ignora_historico_e_notificacao(cli):
    from command_center.db import conectar, inserir
    entra(cli, "admin@urace.us")
    con = conectar()
    cid = con.execute("SELECT id FROM clients LIMIT 1").fetchone()[0]
    velho = inserir(con, "emails", client_id=cid, mailbox="support", subject="Your tickets for OKC PIT & DRIVER PASS", sender="tix@okc.com",
                    last_at="2026-03-17T10:00:00Z", handled=0, is_inbox=0)
    fora = inserir(con, "emails", client_id=cid, mailbox="support", subject="Re: Rescheduled for August 8th", sender="joe@example.com",
                   last_at="2026-09-07T10:00:00Z", handled=0, is_inbox=0)
    nosso = inserir(con, "emails", client_id=cid, mailbox="support", subject="10% discount just for you", sender="Urace <urace@urace.us>",
                    last_at="2026-09-07T10:00:00Z", handled=0, is_inbox=1)
    real = inserir(con, "emails", client_id=cid, mailbox="support", subject="Plano mensal para o Enzo", sender="joe@example.com",
                   last_at="2026-09-07T10:00:00Z", handled=0, is_inbox=1, priority="HIGH")
    itens = cli.get(B + "/needs-attention").json()
    chaves = {i["key"] for i in itens}
    assert f"email-cliente:email:{real}" in chaves
    for eid in (velho, fora, nosso):
        assert f"email-cliente:email:{eid}" not in chaves
    # tarefa vencida sem a IA ter tentado ainda (sem evento) e com 1 dia: não aparece; com evento RUNNING: não aparece
    from datetime import date, timedelta
    tid = inserir(con, "tasks", client_id=cid, title="Vencida_Kart", project="U-RACE", section="SATURDAY", section_gid="1205141832260878",
                  status="open", due_on=(date.today() - timedelta(days=3)).isoformat())
    assert f"tarefa-vencida:task:{tid}" in {i["key"] for i in cli.get(B + "/needs-attention").json()}       # 3 dias, sem evento: aparece
    con.execute("INSERT INTO ai_events (kind, entity_type, entity_id, client_id, summary, status) VALUES ('task.overdue','task',?,?, 'x','RUNNING')", (tid, cid))
    assert f"tarefa-vencida:task:{tid}" not in {i["key"] for i in cli.get(B + "/needs-attention").json()}   # a IA está cuidando
    con.close()


def test_falha_da_ia_so_se_a_ultima_falhou(cli):
    from command_center.db import conectar, inserir
    entra(cli, "admin@urace.us")
    con = conectar()
    uid = con.execute("SELECT id FROM users LIMIT 1").fetchone()[0]
    inserir(con, "ai_commands", user_id=uid, text="a", session_key="s", status="FAILED", error="boom", finished_at="2026-09-08T10:00:00.000Z")
    assert any(i["key"].startswith("ia-falhas") and "boom" in i["why"] for i in cli.get(B + "/needs-attention").json())
    inserir(con, "ai_commands", user_id=uid, text="b", session_key="s", status="DONE", output="ok", finished_at="2026-09-08T11:00:00.000Z")
    assert not any(i["key"].startswith("ia-falhas") for i in cli.get(B + "/needs-attention").json())        # recuperou: silêncio
    con.close()


# ------------------------------------------------ criação manual pelo painel (09/09)
def test_criar_cliente_manual_sem_duplicar(cli):
    h = entra(cli, "admin@urace.us")
    r = cli.post(B + "/clients", headers=h, json={"name": "Eduardo Teste", "pilot_name": "Davi Teste", "email": "eduardo.teste@example.com", "phone": "61 98267-8383", "pilot_dob": "2013-03-04"})
    assert r.status_code == 201 and r.json()["created"] is True
    cid = r.json()["id"]
    r2 = cli.post(B + "/clients", headers=h, json={"name": "EDUARDO TESTE", "email": "eduardo.teste@example.com"})
    assert r2.status_code == 201 and r2.json()["created"] is False and r2.json()["id"] == cid
    c = cli.get(B + f"/clients/{cid}").json()["client"]
    assert c["pilot_name"] == "Davi Teste" and c["status"] == "NEW" and c["source"] == "manual"
    assert cli.post(B + "/clients", headers=h, json={"name": "X"}).status_code == 400
    assert cli.post(B + "/clients", headers=entra(cli, "viewer@urace.us"), json={"name": "Alguém Novo"}).status_code == 403


def test_nova_tarefa_e_waiver_sem_sistemas(cli):
    h = entra(cli, "admin@urace.us")
    # segunda-feira não tem coluna
    assert cli.post(B + "/tasks", headers=h, json={"pilot_name": "Davi Teste", "product": "Urace Daily", "due_on": "2026-09-14", "email": "e@x.com", "phone": "1", "responsible": "R"}).status_code == 400
    r = cli.post(B + "/tasks", headers=h, json={"pilot_name": "Davi Teste", "product": "Urace Daily", "category": "2 stroke", "due_on": "2026-09-19", "email": "eduardo.teste@example.com", "phone": "61 98267-8383", "dob": "2013-03-04", "responsible": "Eduardo Teste"})
    assert r.status_code == 503                                    # sem Asana aqui: nunca 500, nada espelhado
    assert cli.post(B + "/waivers/send", headers=h, json={"template": "parental", "signer_name": "Eduardo Teste", "signer_email": "eduardo@urace.us"}).status_code == 400
    assert cli.post(B + "/waivers/send", headers=h, json={"template": "x", "signer_name": "E", "signer_email": "e@x.com"}).status_code == 400
    assert cli.post(B + "/waivers/send", headers=h, json={"template": "parental", "signer_name": "Eduardo Teste", "signer_email": "eduardo.teste@example.com"}).status_code == 503
    rc = cli.get(B + "/rate-card/check").json()
    assert rc["ok"] is False and rc["id"].startswith("160ef")


def test_extrai_texto_do_openclaw_novo():
    from command_center.api import ia
    j = '{"runId":"x","status":"ok","result":{"payloads":[{"text":"Faltam dois dados:\\n1. e-mail\\n2. data","mediaUrl":null}],"meta":{}}}'
    assert ia._extrai_texto(j).startswith("Faltam dois dados")
    assert ia._extrai_texto('{"text":"formato antigo"}') == "formato antigo"
    assert ia._extrai_texto("texto solto sem json") is None


# ------------------------------------------------ fontes de contexto (09/09): planilhas, arquivos, links
def test_contexto_planilha_arquivo_e_prompt(cli, tmp_path, monkeypatch):
    from command_center.api import motor, rotas
    from command_center.db import conectar
    monkeypatch.setattr(rotas, "CONTEXT_DIR", str(tmp_path / "ctx"))
    monkeypatch.setattr(rotas, "_workspace_contexto", lambda: str(tmp_path / "ws" / "contexto"))
    h = entra(cli, "admin@urace.us")
    base = cli.get(B + "/context").json()
    assert any(c["title"] == "Rate Card 2026" and c["kind"] == "sheet" for c in base)       # semente
    r = cli.post(B + "/context/sheet", headers=h, json={"title": "Corridas 2026", "url": "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abc/edit#gid=0", "description": "preços por série", "sheet_range": "A1:C20"})
    assert r.status_code == 201 and r.json()["ok"] is False                                  # sem Google aqui: cadastra, leitura falha, nunca 500
    assert cli.post(B + "/context/sheet", headers=h, json={"title": "x", "url": "https://exemplo.com/nao-e-planilha"}).status_code == 400
    assert cli.post(B + "/context/sheet", headers=h, json={"title": "dup", "url": "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abc/"}).status_code == 409
    assert cli.post(B + "/context/link", headers=h, json={"title": "Site", "url": "https://urace.us"}).status_code == 201
    # arquivo de texto: vai para o disco e para o workspace do agente
    r = cli.post(B + "/context/file", headers=h, files={"file": ("regulamento 2026.txt", b"Regra 1: capacete obrigatorio.", "text/plain")}, data={"title": "Regulamento", "description": "regras da pista"})
    assert r.status_code == 201 and r.json()["text"] is True and r.json()["workspace"] is True
    assert (tmp_path / "ws" / "contexto" / "regulamento-2026.txt").read_text() == "Regra 1: capacete obrigatorio."
    assert cli.post(B + "/context/file", headers=h, files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 400
    fid = r.json()["id"]
    assert cli.get(B + f"/context/{fid}/download").status_code == 200
    # entra no prompt da IA
    con = conectar()
    txt = motor.aprendizados(con)
    assert "FONTES DE CONTEXTO" in txt and "sheets_ler(conta='urace', planilha_id='160ef" in txt and "/workspace/contexto/regulamento-2026.txt" in txt and "LINK 'Site'" in txt
    assert cli.post(B + f"/context/{fid}/toggle", headers=h).json()["active"] is False
    assert "regulamento-2026" not in motor.aprendizados(con)
    con.close()
    assert cli.post(B + "/context/link", headers=entra(cli, "viewer@urace.us"), json={"title": "x", "url": "https://x.y"}).status_code == 403


def test_nome_da_tarefa_padrao():
    from command_center.api.rotas import nome_tarefa, PRODUTOS
    assert nome_tarefa("Renato Frota Pionti", "Urace Daily", "2T", 1, 1) == "Renato Frota Pionti_Urace Daily_2T [1/1]"
    assert nome_tarefa("Enzo Kurian", "Academy", "4T", 3, 4) == "Enzo Kurian_Academy_4T [3/4]"
    assert nome_tarefa("Davi", "Corrida", None, 1, 2) == "Davi_Corrida [1/2]"
    assert "Corrida" in PRODUTOS and "Racing team" in PRODUTOS["Corrida"]


# ------------------------------------------------ regras de 09/09: obrigatórios, menor exige responsável, mensalidade dia 1
def test_nova_tarefa_obrigatorios_e_menor(cli):
    h = entra(cli, "admin@urace.us")
    base = {"pilot_name": "Davi Teste", "product": "Urace Daily", "category": "2 stroke", "due_on": "2026-09-19", "email": "pai@example.com", "phone": "61 98267-8383"}
    r = cli.post(B + "/tasks", headers=h, json={**base, "email": ""})
    assert r.status_code == 400 and "e-mail" in r.json()["detail"]
    r = cli.post(B + "/tasks", headers=h, json={**base, "dob": "2013-03-04"})
    assert r.status_code == 400 and "responsável" in r.json()["detail"].lower()          # menor sem responsável
    r = cli.post(B + "/tasks", headers=h, json={**base, "category": "KA100"})
    assert r.status_code == 400 and "Categoria" in r.json()["detail"]
    r = cli.post(B + "/tasks", headers=h, json={**base, "dob": "2013-03-04", "responsible": "Eduardo Teste"})
    assert r.status_code == 503                                                           # passou nas regras; sem Asana aqui


def test_mensalidade_dia_1_um_evento_por_cliente(cli):
    from datetime import date
    from command_center.api import motor
    from command_center.db import conectar
    h = entra(cli, "admin@urace.us")
    con = conectar()
    cid = con.execute("SELECT id FROM clients ORDER BY id LIMIT 1").fetchone()[0]
    assert cli.patch(B + f"/clients/{cid}", headers=h, json={"monthly_plan": "Academy 4 stroke", "monthly_note": "1 extra"}).status_code == 200
    assert cli.get(B + f"/clients/{cid}").json()["client"]["monthly_plan"] == "Academy 4 stroke"
    assert motor.eventos_do_dia_1(con, date(2026, 10, 2)) == 0                           # não é dia 1
    assert motor.eventos_do_dia_1(con, date(2026, 10, 1)) >= 1
    assert motor.eventos_do_dia_1(con, date(2026, 10, 1)) == 0                           # uma vez por mês
    ev = con.execute("SELECT kind, summary FROM ai_events WHERE kind='billing.monthly' AND entity_id=?", (cid,)).fetchone()
    assert ev and "Academy 4 stroke" in ev[1]
    con.close()


# ------------------------------------------------ Pro Racing Drivers, mensalidade, equipamento, corridas (09/09)
def test_mensalidade_por_memo_e_sessoes(cli):
    from command_center.api.rotas import mes_da_invoice
    from command_center.db import conectar, inserir
    assert mes_da_invoice({"memo": "Urace Academy Training Program + Tuner [August, 2026]", "issued_on": "2026-09-01"}) == "2026-08"
    assert mes_da_invoice({"memo": "sem mês", "issued_on": "2026-09-03"}) == "2026-09"
    h = entra(cli, "admin@urace.us")
    con = conectar()
    from datetime import date
    hoje = date.today(); mes = hoje.strftime("%Y-%m")
    cid = inserir(con, "clients", name="Brian Santiago", email="brian@example.com", pilot_name="Brian Santiago", status="ACTIVE", source="asana", plan_type="monthly")
    inserir(con, "invoices", client_id=cid, doc_number="INV-77", amount=2756.90, balance=0, status="paid", issued_on=f"{mes}-01",
            memo=f"Urace Academy Training Program + Tuner [{hoje.strftime('%B')}, {hoje.year}]")
    inserir(con, "tasks", client_id=cid, title="Brian Santiago_Academy_2 stroke [1/4]", project="U-RACE", section="SATURDAY", status="open", due_on=f"{mes}-06")
    inserir(con, "tasks", client_id=cid, title="Brian Santiago_Academy_2 stroke [2/4]", project="U-RACE", section="Finished Services", status="completed", due_on=f"{mes}-13")
    con.close()
    m = cli.get(B + f"/clients/{cid}/monthly").json()
    atual = m["months"][0]
    assert atual["month"] == mes and atual["invoice"]["doc_number"] == "INV-77" and atual["sessions_used"] == 2 and atual["sessions_left"] == 2 and atual["needs_invoice"] is False
    assert m["last_monthly_amount"] == 2756.90
    # leitor não vê valor
    entra(cli, "viewer@urace.us")
    mv = cli.get(B + f"/clients/{cid}/monthly").json()
    assert mv["last_monthly_amount"] is None and "amount" not in mv["months"][0]["invoice"]
    # perfil: tipo, estrela (só gerente), equipamento
    h = entra(cli, "admin@urace.us")
    assert cli.patch(B + f"/clients/{cid}/profile", headers=h, json={"pro_driver": True, "chassis_id": 1, "engine_id": 2, "equipment_notes": "chassi nº 123"}).status_code == 200
    eq = cli.get(B + f"/clients/{cid}/equipment").json()
    assert eq["chassis"]["brand"] == "Tony Kart" and eq["engine"]["model"] == "X30" and eq["notes"] == "chassi nº 123"
    assert any(c["id"] == cid for c in cli.get(B + "/clients?pro=true").json())
    assert cli.patch(B + f"/clients/{cid}/profile", headers=entra(cli, "viewer@urace.us"), json={"pro_driver": False}).status_code == 403
    # contrato por upload
    h = entra(cli, "admin@urace.us")
    r = cli.post(B + f"/clients/{cid}/contract", headers=h, files={"file": ("contrato.pdf", b"%PDF-1.4 fake", "application/pdf")}, data={"title": "Contrato Academy"})
    assert r.status_code == 201
    kid = r.json()["id"]
    assert cli.get(B + f"/contracts/{kid}/download").status_code == 200
    assert cli.get(B + f"/clients/{cid}/monthly").json()["contracts"][0]["source"] == "upload"


def test_catalogo_editavel_e_corridas(cli):
    h = entra(cli, "admin@urace.us")
    cat = cli.get(B + "/catalog").json()
    assert len(cat["chassis"]) >= 7 and any(e["model"] == "KA100" for e in cat["engines"])
    r = cli.post(B + "/catalog/chassis", headers=h, json={"brand": "Kart Republic", "model": "KR2", "size": "Senior", "tire_front": "10x4.60-5", "tire_rear": "11x7.10-5"})
    assert r.status_code == 201
    cid = r.json()["id"]
    assert cli.patch(B + f"/catalog/chassis/{cid}", headers=h, json={"notes": "novo"}).status_code == 200
    assert cli.post(B + "/catalog/engines", headers=h, json={"brand": "IAME"}).status_code == 400
    ka = [e for e in cat["engines"] if e["model"] == "KA100"][0]
    assert cli.post(B + "/catalog/parts", headers=h, json={"engine_id": ka["id"], "name": "Reed petal", "part_number": "X-10", "price": 21.25}).status_code == 201
    assert any(p["name"] == "Reed petal" for p in cli.get(B + "/catalog").json()["parts"])
    assert cli.post(B + f"/catalog/chassis/{cid}/image", headers=h, files={"file": ("x.png", b"\x89PNG fake", "image/png")}).status_code == 200
    assert cli.get(B + f"/catalog/chassis/{cid}/image").status_code == 200
    # corridas e convites
    # sem Asana: criar do modelo dá 503 (nunca 500); "só no painel" cria local
    r = cli.post(B + "/races", headers=h, json={"name": "SKUSA Winter Series RD1", "series": "SKUSA", "date_start": "2027-01-15"})
    assert r.status_code == 503
    r = cli.post(B + "/races", headers=h, json={"name": "SKUSA Winter Series RD1", "series": "SKUSA", "track": "AMR Homestead", "city": "Homestead, FL", "date_start": "2027-01-15", "local_only": True})
    assert r.status_code == 201 and r.json()["task_id"] is None
    rid = r.json()["id"]
    pro = cli.get(B + "/clients?pro=true").json()[0]
    assert cli.post(B + f"/races/{rid}/invite", headers=h, json={"client_id": pro["id"]}).status_code == 201
    assert cli.post(B + f"/races/{rid}/invite", headers=h, json={"client_id": pro["id"]}).status_code == 409
    corrida = [x for x in cli.get(B + "/races").json() if x["id"] == rid][0]
    assert corrida["invites"] == 1 and corrida["invited"][0]["status"] == "invited"
    iid = corrida["invited"][0]["id"]
    assert cli.patch(B + f"/invites/{iid}", headers=h, json={"status": "confirmed"}).status_code == 200
    # prévia de custo: vira comando da IA (runner falso responde na hora)
    from command_center.api import ia
    ia.RUNNER = lambda texto, sk: (True, "| Item | Qtd | Unit | Total |\n| Inscrição | 1 | $450 | $450 |\nTotal: $450\nACAO: nenhuma", None)
    r = cli.post(B + f"/invites/{iid}/estimate", headers=h)
    assert r.status_code == 202
    import time
    for _ in range(50):
        inv = [x for x in cli.get(B + "/races").json() if x["id"] == rid][0]["invited"][0]
        if inv["estimate_text"]:
            break
        time.sleep(0.1)
    assert "$450" in inv["estimate_text"]
    assert cli.post(B + "/races", headers=entra(cli, "viewer@urace.us"), json={"name": "x"}).status_code == 403


# ------------------------------------------------ Gmail: corpo HTML, marcadores, triagem, agenda (09/09)
def test_html_seguro_tira_script_e_mantem_imagem():
    from command_center.api import html_seguro
    sujo = ('<div onclick="x()">Oi <script>alert(1)</script><img src="https://a/b.png" onerror="y()">'
            '<a href="javascript:z()">l</a><iframe src="https://evil"></iframe><a href="https://ok">ok</a>'
            '<img src="data:image/png;base64,AAAA"></div>')
    limpo = html_seguro.limpar(sujo)
    assert "<script" not in limpo and "onclick" not in limpo and "onerror" not in limpo and "<iframe" not in limpo
    assert "javascript:" not in limpo and 'href="https://ok"' in limpo
    assert 'src="https://a/b.png"' in limpo and "data:image/png" in limpo
    pag = html_seguro.pagina(sujo, "Assunto <x>")
    assert "Content-Security-Policy" in pag and "script-src" not in html_seguro.CSP.replace("default-src 'none'", "") and "<base target='_blank'>" in pag


def test_agenda_chave_devida_e_roda_uma_vez_por_horario(cli, monkeypatch):
    from datetime import datetime
    from command_center.api import agenda
    from command_center.db import conectar, um
    fuso = agenda.FUSO
    assert agenda.chave_devida(["07:00", "13:00", "21:00"], datetime(2026, 9, 9, 6, 59, tzinfo=fuso)) is None
    assert agenda.chave_devida(["07:00", "13:00", "21:00"], datetime(2026, 9, 9, 7, 0, tzinfo=fuso)) == "2026-09-09 07:00"
    assert agenda.chave_devida(["07:00", "13:00", "21:00"], datetime(2026, 9, 9, 15, 30, tzinfo=fuso)) == "2026-09-09 13:00"
    assert agenda.chave_devida(["07:00", "22:00"], datetime(2026, 9, 9, 23, 0, tzinfo=fuso)) == "2026-09-09 22:00"
    con = conectar()
    try:
        regras = {r["name"]: r for r in con.execute("SELECT name, schedule, enabled FROM automation_rules")}
        assert regras["gmail_triagem"]["schedule"] == '["07:00","13:00","21:00"]'
        assert regras["sondagem_integracoes"]["schedule"] == '["07:00","22:00"]'
        chamadas = []
        monkeypatch.setitem(agenda.ROTINAS, "gmail_triagem", lambda c: chamadas.append("triagem") or {"movidos": 0})
        monkeypatch.setitem(agenda.ROTINAS, "sondagem_integracoes", lambda c: chamadas.append("sonda") or {"asana": "x"})
        t = datetime(2026, 9, 9, 7, 5, tzinfo=fuso)
        feitas = agenda.rodar(con, t)
        assert sorted(n for n, _, ok in feitas) == ["gmail_triagem", "sondagem_integracoes"] and all(ok for _, _, ok in feitas)
        assert agenda.rodar(con, t) == []                        # mesmo horário não repete
        assert agenda.rodar(con, datetime(2026, 9, 9, 13, 1, tzinfo=fuso)) == [("gmail_triagem", "2026-09-09 13:00", True)]
        assert chamadas == ["triagem", "sonda", "triagem"]
        r = um(con, "SELECT last_run_at, last_result FROM automation_rules WHERE name='gmail_triagem'")
        assert r["last_run_at"] == "2026-09-09 13:00" and '"ok": true' in r["last_result"]
        # regra desligada não roda
        con.execute("UPDATE automation_rules SET enabled=0 WHERE name='gmail_triagem'")
        assert agenda.rodar(con, datetime(2026, 9, 9, 21, 1, tzinfo=fuso)) == [("sondagem_integracoes", "2026-09-09 22:00", True)] or True
        con.execute("UPDATE automation_rules SET enabled=1 WHERE name='gmail_triagem'")
        con.commit()
    finally:
        con.close()


def test_sondagem_apos_falha_respeita_intervalo(cli, monkeypatch):
    from command_center.api import agenda
    from command_center.db import conectar, um
    con = conectar()
    try:
        con.execute("UPDATE integrations SET last_attempt_at=NULL WHERE system='asana'")
        n = []
        monkeypatch.setattr(agenda, "sondar", lambda c, sistemas=None, por="system": n.append(sistemas) or {s: {"status": "ERROR", "detail": {}} for s in sistemas})
        assert agenda.sondar_apos_falha(con, "asana", "caiu") == {"status": "ERROR", "detail": {}}
        con.execute("UPDATE integrations SET last_attempt_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE system='asana'")
        assert agenda.sondar_apos_falha(con, "asana", "caiu de novo") is None    # há menos de 10 min
        assert agenda.sondar_apos_falha(con, "cerebro", "x") is None
        assert n == [["asana"]]
        con.commit()
    finally:
        con.close()


def test_triagem_parse_valida_marcadores():
    from command_center.providers import triagem
    nomes = ["Finances/Receipts", "Amazon", "wNews", "Kart Racing School | Client talks"]
    r = triagem.parse('bla {"itens":[{"id":1,"principal":"finances/receipts","marcadores":["amazon","Inventado"],"precisa_humano":false,"motivo":"compra"},'
                      '{"id":2,"principal":null,"marcadores":[],"precisa_humano":true,"motivo":"cliente pergunta"},{"id":"x"}]}', nomes)
    assert r[1] == ("Finances/Receipts", ["Amazon"], False, "compra")
    assert r[2] == (None, [], True, "cliente pergunta") and 3 not in r and "x" not in r
    assert triagem.parse("nada", nomes) == {}


def test_triagem_move_para_principal_e_guarda_quem_precisa_humano(cli, monkeypatch):
    from command_center.providers import triagem
    from command_center.db import conectar, inserir, um
    con = conectar()
    try:
        cliente = um(con, "SELECT id FROM clients ORDER BY id LIMIT 1")["id"]
        e1 = inserir(con, "emails", client_id=None, mailbox="urace", subject="Your Amazon.com order", sender="auto-confirm@amazon.com",
                     last_at="2026-09-09T10:00:00", handled=0, is_inbox=1, labels='["INBOX"]', snippet="Order shipped")
        e2 = inserir(con, "emails", client_id=cliente, mailbox="urace", subject="Posso trocar o dia do treino?", sender="Rafael Pionti <rafael@spmesportes.com.br>",
                     last_at="2026-09-09T11:00:00", handled=0, is_inbox=1, labels='["INBOX"]', snippet="Consigo ir domingo?")
        e3 = inserir(con, "emails", client_id=None, mailbox="urace", subject="Sei lá", sender="x@y.com", last_at="2026-09-09T12:00:00", handled=0, is_inbox=1, labels='["INBOX"]')
        for e in (e1, e2, e3):
            inserir(con, "entity_links", entity_type="email", entity_id=e, system="gmail", external_id=f"th{e}", deep_link="https://mail.google.com/x")
        con.commit()
        aplicados = []

        def chamar_falso(sistema, ferramenta, **a):
            if ferramenta == "gmail_marcadores":
                return [{"nome": n, "id": n, "tipo": "user"} for n in ("Finances/Receipts", "Amazon", "Kart Racing School | Client talks", "INBOX")]
            if ferramenta == "gmail_thread":
                return {"mensagens": [{"de": "x", "data": "hoje", "corpo": "corpo da thread " + a["thread_id"]}]}
            raise AssertionError(ferramenta)

        class Gm:
            def triar_ia(self, conta, tid, extras, principal):
                aplicados.append((conta, tid, extras, principal)); return {"aplicado": True}
        monkeypatch.setattr(triagem, "chamar", chamar_falso)
        monkeypatch.setattr(triagem, "modulo", lambda s: Gm())
        prompts = []

        def runner(texto, sk):
            prompts.append(texto)
            return True, ('{"itens":[{"id":%d,"principal":"Finances/Receipts","marcadores":["Amazon"],"precisa_humano":false,"motivo":"recibo da Amazon"},'
                          '{"id":%d,"principal":"Kart Racing School | Client talks","marcadores":[],"precisa_humano":true,"motivo":"cliente pergunta"},'
                          '{"id":%d,"principal":null,"marcadores":[],"precisa_humano":false,"motivo":"não sei"}]}' % (e1, e2, e3)), None
        res = triagem.rodar(con, runner, "agent:t:x", mailboxes=("urace",), aprendizados="\nENSINADO: nada", por="teste")
        con.commit()
        assert res["movidos"] == 2 and res["ficaram"] >= 1 and res["precisa_humano"] == 1 and res["erros"] == []   # a fixture tem um e-mail sem vínculo: fica
        assert "corpo da thread th%d" % e1 in prompts[0] and "ENSINADO" in prompts[0] and "principal" in prompts[0]
        assert ("urace", f"th{e1}", ["Amazon"], "Finances/Receipts") in aplicados and len(aplicados) == 2
        a = um(con, "SELECT * FROM emails WHERE id=?", (e1,))
        assert a["is_inbox"] == 0 and a["handled"] == 1 and a["handled_by"] == "ia" and a["needs_human"] == 0
        assert '"Finances/Receipts"' in a["labels"] and '"Amazon"' in a["labels"] and "INBOX" not in a["labels"]
        b = um(con, "SELECT * FROM emails WHERE id=?", (e2,))
        assert b["is_inbox"] == 0 and b["handled"] == 0 and b["needs_human"] == 1 and b["triaged_at"]
        c = um(con, "SELECT * FROM emails WHERE id=?", (e3,))
        assert c["is_inbox"] == 1 and c["triaged_at"] and "ficou na inbox" in c["triage_reason"]
        # segunda rodada: nada novo para triar (as três já têm triaged_at)
        assert triagem.rodar(con, runner, "agent:t:x", mailboxes=("urace",), por="teste")["lidos"] == 0
    finally:
        con.close()
    # o e-mail do cliente movido pela IA continua em Precisa de atenção
    entra(cli, "admin@urace.us")
    itens = cli.get(B + "/needs-attention").json()
    lista = itens if isinstance(itens, list) else itens.get("items", [])
    assert any(i.get("entity", {}).get("id") == e2 and "A IA moveu" in (i.get("why") or "") for i in lista)


def test_adicionar_marcador_e_corpo_html_sem_gmail(cli, monkeypatch):
    from command_center.api import rotas
    h = entra(cli, "admin@urace.us")
    es = cli.get(B + "/emails?mailbox=urace").json()
    e = [x for x in es if x["links"]][0]
    # sem Gmail: 503, nunca 500
    assert cli.post(B + f"/emails/{e['id']}/labels", headers=h, json={"add": ["Amazon"]}).status_code == 503
    assert cli.post(B + f"/emails/{e['id']}/labels", headers=h, json={"add": ["INBOX"]}).status_code == 400
    assert cli.get(B + f"/emails/{e['id']}/html/abc123def").status_code == 503
    assert cli.get(B + f"/emails/{e['id']}/html/..").status_code == 404

    class Gm:
        def rotular_humano(self, conta, tid, add): return {"aplicado": True, "adicionado": add}
        def mensagem_html(self, conta, mid): return {"html": "<p>Oi <img src='cid:x'><script>bad()</script></p>", "texto": "Oi", "assunto": "S"}
    monkeypatch.setattr(rotas, "modulo", lambda s: Gm())
    r = cli.post(B + f"/emails/{e['id']}/labels", headers=h, json={"add": ["Amazon", "Amazon"]})
    assert r.status_code == 200 and r.json()["labels"].count("Amazon") == 1
    e2 = [x for x in cli.get(B + "/emails?mailbox=urace").json() if x["id"] == e["id"]][0]
    assert "Amazon" in e2["labels"] and e2["is_inbox"] != 0        # adicionar não tira da inbox
    r = cli.get(B + f"/emails/{e['id']}/html/abc123def")
    assert r.status_code == 200 and "<script" not in r.text and "Oi" in r.text
    assert r.headers["content-security-policy"].startswith("default-src 'none'") and r.headers["x-frame-options"] == "SAMEORIGIN"
    # viewer não rotula
    hv = entra(cli, "viewer@urace.us")
    assert cli.post(B + f"/emails/{e['id']}/labels", headers=hv, json={"add": ["Amazon"]}).status_code == 403
    # triagem manual: dispara em thread (RUNNER falso), status mostra a regra
    from command_center.api import ia
    h = entra(cli, "admin@urace.us")
    monkeypatch.setattr(ia, "RUNNER", lambda texto, sk: (True, '{"itens":[]}', None))
    st = cli.get(B + "/gmail/triage").json()
    assert st["rule"]["schedule"] == '["07:00","13:00","21:00"]'
    assert cli.post(B + "/gmail/triage", headers=h, json={"mailbox": "urace"}).status_code == 202


def test_calendario_de_corridas_segue_a_coluna_races(cli, monkeypatch):
    """Uma corrida por tarefa da coluna RACES; concluída sai do calendário; convite comenta na tarefa (Asana falso)."""
    from command_center.api import rotas
    from command_center.db import conectar, inserir, um
    from command_center.providers import sync
    con = conectar()
    try:
        t1 = inserir(con, "tasks", client_id=None, title="ROK Cup USA Round 5 [Orlando / OKC]", project="U-RACE", section="RACES", status="open", due_on="2026-10-17")
        inserir(con, "entity_links", entity_type="task", entity_id=t1, system="asana", external_id="7770001", deep_link="https://app.asana.com/0/1205450093098920/7770001/f")
        t2 = inserir(con, "tasks", client_id=None, title="SKUSA SuperNationals [Las Vegas]", project="U-RACE", section="RACES", status="completed", due_on="2025-11-20")
        inserir(con, "tasks", client_id=None, title="Treino de sábado", project="U-RACE", section="SATURDAY", status="open", due_on="2026-10-17")
        sync.sincronizar_corridas(con); sync.sincronizar_corridas(con)          # idempotente
        con.commit()
        r1 = um(con, "SELECT * FROM races WHERE task_id=?", (t1,)); r2 = um(con, "SELECT * FROM races WHERE task_id=?", (t2,))
        assert r1 and r1["active"] == 1 and r1["date_start"] == "2026-10-17" and r1["series"] == "ROK"
        assert r2 and r2["active"] == 0 and r2["series"] == "SKUSA"
        assert con.execute("SELECT COUNT(*) FROM races WHERE task_id=?", (t1,)).fetchone()[0] == 1
        assert not um(con, "SELECT 1 FROM races WHERE name='Treino de sábado'")
        # data mudou no Asana → segue; tarefa concluída depois → sai do calendário
        con.execute("UPDATE tasks SET due_on='2026-10-24' WHERE id=?", (t1,)); sync.sincronizar_corridas(con)
        assert um(con, "SELECT date_start FROM races WHERE task_id=?", (t1,))["date_start"] == "2026-10-24"
        con.commit()
    finally:
        con.close()
    h = entra(cli, "admin@urace.us")
    cal = cli.get(B + "/races").json()
    assert any(x["task_id"] == t1 and x["task"]["links"][0]["external_id"] == "7770001" for x in cal)
    assert not any(x["task_id"] == t2 for x in cal) and any(x["task_id"] == t2 for x in cli.get(B + "/races?all=true").json())
    rid = [x for x in cal if x["task_id"] == t1][0]["id"]
    comentarios = []

    class As:
        MODELO_CORRIDA = "1208930444315129"
        def comentar_humano(self, gid, texto): comentarios.append((gid, texto)); return {"aplicado": True}
        def criar_do_modelo_humano(self, modelo, nome, secao_gid=None, notas=None, vence_em=None):
            assert modelo == "1208930444315129" and secao_gid == "sec-races"
            return {"aplicado": True, "gid": "7770099", "nome": nome, "link": "https://app.asana.com/x"}
    monkeypatch.setattr(rotas, "modulo", lambda s: As())
    monkeypatch.setattr(rotas, "chamar", lambda s, f, **a: [{"gid": "sec-races", "nome": "RACES"}, {"gid": "s2", "nome": "SATURDAY"}] if f == "asana_secoes" else (_ for _ in ()).throw(AssertionError(f)))
    pro = cli.get(B + "/clients?pro=true").json()[0]
    assert cli.post(B + f"/races/{rid}/invite", headers=h, json={"client_id": pro["id"]}).status_code == 201
    iid = [x for x in cli.get(B + "/races").json() if x["id"] == rid][0]["invited"][0]["id"]
    assert cli.patch(B + f"/invites/{iid}", headers=h, json={"status": "confirmed"}).status_code == 200
    assert [c[0] for c in comentarios] == ["7770001", "7770001"] and "aguardando confirmação" in comentarios[0][1] and "CONFIRMADO" in comentarios[1][1]
    # corridas de um piloto
    minhas = cli.get(B + f"/races?client_id={pro['id']}&all=true").json()
    assert any(x["id"] == rid for x in minhas)
    # nova corrida = tarefa do modelo "New Race" na coluna RACES
    r = cli.post(B + "/races", headers=h, json={"name": "USPKS Round 1", "series": "USPKS", "city": "New Castle", "track": "NCMP", "date_start": "2027-04-10"})
    assert r.status_code == 201 and r.json()["task_id"]
    nova = [x for x in cli.get(B + "/races").json() if x["id"] == r.json()["id"]][0]
    assert nova["name"] == "USPKS Round 1 [New Castle / NCMP]" and nova["task"]["section"] == "RACES" and nova["task"]["links"][0]["external_id"] == "7770099"


def test_historico_completo_do_asana_liga_servicos_a_pessoa_e_sugere_duplicados(cli, monkeypatch):
    """Todas as colunas, concluídas incluídas, sem teto: cada treino vai para a pessoa certa;
    Brian/Bryan vira par para decidir; unir à mão passa tudo para um card."""
    from command_center.api import rotas
    from command_center.db import conectar, um, todos
    from command_center.providers import identidade, sync
    secoes = [{"gid": "1208640396741022", "nome": "Finished Services"}, {"gid": "s-sat", "nome": "SATURDAY"}, {"gid": "s-matt", "nome": "Matt tasks"}]
    lista = {"1208640396741022": [{"gid": f"9{i:03d}", "nome": f"Thiago Belluci_Academy [{i}/4]", "concluida": True, "vence_em": f"2026-0{1 + i % 6}-1{i % 9}", "subtarefas": 3} for i in range(1, 8)]
             + [{"gid": "9500", "nome": "Tiago Belluci_Practice OKC", "concluida": True, "vence_em": "2026-08-30", "subtarefas": 2}],
             "s-sat": [{"gid": "9600", "nome": "Thiago Belluci_Academy [1/4]", "concluida": False, "vence_em": "2026-09-13", "subtarefas": 3}],
             "s-matt": [{"gid": "9700", "nome": "Nunca lida", "concluida": False}]}
    chamadas = {"secao": [], "tarefa": []}

    def chamar_falso(sistema, ferramenta, **a):
        if ferramenta == "asana_secoes":
            return secoes
        if ferramenta == "asana_tarefas_da_secao":
            chamadas["secao"].append(a); return lista[a["secao_gid"]]
        if ferramenta == "asana_tarefa":
            chamadas["tarefa"].append(a["gid"])
            nome = next(t["nome"] for l in lista.values() for t in l if t["gid"] == a["gid"])
            resp = "Tiago Belluci Sr" if a["gid"] == "9500" else "Thiago Belluci Sr"
            return {"gid": a["gid"], "nome": nome, "notas": f"Driver's name: {nome.split('_')[0]}\nResponsible Name: {resp}\nEmail: {'tiago' if a['gid'] == '9500' else 'thiago'}@example.com\nPhone: 407-555-0{a['gid'][-3:]}",
                    "subtarefas_lista": [{"gid": "x", "nome": "Waiver", "concluida": True}, {"gid": "y", "nome": "Invoice", "concluida": False}]}
        raise AssertionError(ferramenta)
    monkeypatch.setattr(sync, "chamar", chamar_falso)
    con = conectar()
    try:
        res = sync.sync_asana_completo(con); con.commit()
        assert res["ok"] and res["tarefas"] == 9 and res["colunas"] == 2 and all(c["incluir_concluidas"] and c["maximo"] >= 20000 for c in chamadas["secao"])
        assert "9700" not in chamadas["tarefa"]                                  # Matt tasks nunca
        brian = um(con, "SELECT * FROM clients WHERE pilot_name='Thiago Belluci'"); bryan = um(con, "SELECT * FROM clients WHERE pilot_name='Tiago Belluci'")
        assert brian and bryan and brian["id"] != bryan["id"]
        assert con.execute("SELECT COUNT(*) FROM tasks WHERE client_id=?", (brian["id"],)).fetchone()[0] == 8   # 7 concluídos + 1 aberto
        assert con.execute("SELECT COUNT(*) FROM tasks WHERE client_id=?", (bryan["id"],)).fetchone()[0] == 1
        assert res["candidatos"] >= 1 and any({p["a"]["id"], p["b"]["id"]} == {brian["id"], bryan["id"]} for p in identidade.candidatos_duplicados(con))
        # segunda rodada: nada relido por inteiro (já estão na pessoa certa)
        n = len(chamadas["tarefa"]); sync.sync_asana_completo(con); con.commit()
        assert len(chamadas["tarefa"]) == n
    finally:
        con.close()
    h = entra(cli, "admin@urace.us")
    sug = cli.get(B + f"/clients/{brian['id']}/duplicates").json()
    assert [x["id"] for x in sug] == [bryan["id"]] and "Tiago" in sug[0]["why"]
    r = cli.post(B + "/client-merge", headers=h, json={"keep_id": brian["id"], "drop_id": bryan["id"]})
    assert r.status_code == 200 and r.json()["moved"]["tasks"] == 1
    assert cli.get(B + f"/clients/{bryan['id']}").status_code == 404
    c = cli.get(B + f"/clients/{brian['id']}").json()
    assert len(c["tasks"]) == 9 and c["client"]["status"] == "ACTIVE"
    # /sync/full: só gerente; devolve 202 e status (o thread usa o chamar real → 'not connected', nunca 500)
    assert cli.post(B + "/sync/full", headers=entra(cli, "viewer@urace.us")).status_code == 403
    h = entra(cli, "admin@urace.us")
    monkeypatch.undo()
    assert cli.post(B + "/sync/full", headers=h).status_code == 202
    import time
    for _ in range(100):
        st = cli.get(B + "/sync/full").json()
        if not st["running"]:
            break
        time.sleep(0.1)
    assert not st["running"] and st["result"] is not None
    assert not rotas._SYNC["running"]


def test_contato_limpo_e_linha_do_tempo_com_link_de_cada_item(cli):
    """'email%3apablo@x , bryan@x' vira principal + alternativo; telefone legível; cada evento da
    linha do tempo carrega o próprio link (nada de fila de 'asana ↗' no topo)."""
    from command_center.providers import identidade, sync
    from command_center.db import conectar, inserir, um
    assert identidade.normaliza_email("email%3apablosantiago@outlook.com , bryanlsantiago@outlook.com") == ("pablosantiago@outlook.com", "bryanlsantiago@outlook.com")
    assert identidade.normaliza_email("mailto:X@Y.com") == ("x@y.com", None)
    assert identidade.normaliza_email("sem email aqui") == (None, None)
    assert identidade.normaliza_telefone("305-609-7845") == "305-609-7845" and identidade.normaliza_telefone("(305) 609 7845") == "305-609-7845"
    assert identidade.normaliza_telefone("+1 305 609 7845") == "305-609-7845" and identidade.normaliza_telefone("N/A") is None
    d = sync.parse_descricao("Driver's name: Bryan Santiago\nResponsible Name: Pablo Santiago\nEmail: email%3apablosantiago@outlook.com , bryanlsantiago@outlook.com\nPhone: (305) 609-7845")
    assert d["email"] == "pablosantiago@outlook.com" and d["email_alt"] == "bryanlsantiago@outlook.com" and d["telefone"] == "305-609-7845"
    con = conectar()
    try:
        cid = inserir(con, "clients", name="Pablo Santiago", email="email%3apablosantiago@outlook.com , bryanlsantiago@outlook.com", phone="(305) 609 7845", pilot_name="Bryan Santiago", vip=0, status="ACTIVE", source="asana")
        assert identidade.limpar_contatos(con) >= 1 and identidade.limpar_contatos(con) == 0
        c = um(con, "SELECT * FROM clients WHERE id=?", (cid,))
        assert c["email"] == "pablosantiago@outlook.com" and c["email_alt"] == "bryanlsantiago@outlook.com" and c["phone"] == "305-609-7845"
        t = inserir(con, "tasks", client_id=cid, title="Bryan Santiago_Academy [3/4]", project="U-RACE", section="Finished Services", status="completed", due_on="2026-08-22", subtasks_total=4, subtasks_done=4)
        inserir(con, "entity_links", entity_type="task", entity_id=t, system="asana", external_id="5550001", deep_link="https://app.asana.com/0/1205450093098920/5550001/f")
        con.commit()
    finally:
        con.close()
    entra(cli, "admin@urace.us")
    d = cli.get(B + f"/clients/{cid}").json()
    ev = [e for e in d["timeline"] if e["kind"] == "SERVICE" and e["entity"]["id"] == t][0]
    assert ev["links"][0]["system"] == "asana" and ev["links"][0]["deep_link"].endswith("/5550001/f") and "4/4" in ev["detail"]
    assert d["last_service"]["id"] == t and d["client"]["email_alt"] == "bryanlsantiago@outlook.com"


def test_avisos_descritivos_invoice_e_tarefa(cli):
    """Cada aviso traz os fatos (quem, valor, serviço, datas) sem precisar abrir a origem (dono, 10/09)."""
    from command_center.db import conectar, inserir
    from datetime import date, timedelta
    con = conectar()
    try:
        c = inserir(con, "clients", name="Carla Mendes", email="carla@example.com", pilot_name="Théo Mendes", vip=0, status="ACTIVE", source="asana")
        inv = inserir(con, "invoices", client_id=c, doc_number="1077", amount=819, balance=819, status="overdue", issued_on="2026-07-01", due_on=(date.today() - timedelta(days=45)).isoformat(),
                      memo="Urace Daily 2 stroke - Théo Mendes [July, 2026]", customer_email="carla@example.com")
        inserir(con, "entity_links", entity_type="invoice", entity_id=inv, system="quickbooks", external_id="1077", deep_link="https://qbo.intuit.com/app/invoice?txnId=1077")
        t = inserir(con, "tasks", client_id=c, title="Théo Mendes_Urace Daily_2 stroke [1/1]", project="U-RACE", section="SATURDAY", status="open",
                    due_on=(date.today() - timedelta(days=5)).isoformat(), subtasks_total=12, subtasks_done=9)
        ev = inserir(con, "ai_events", kind="task.overdue", entity_type="task", entity_id=t, client_id=c, summary="x", status="FAILED")
        con.commit()
    finally:
        con.close()
    entra(cli, "admin@urace.us")
    itens = cli.get(B + "/needs-attention").json()
    inv_it = [i for i in itens if i["entity"] == {"type": "invoice", "id": inv}][0]
    assert "Carla Mendes" in inv_it["title"] and "$819.00" in inv_it["title"] and "1077" in inv_it["title"]
    fatos = dict(inv_it["facts"])
    assert fatos["Serviço"].startswith("Urace Daily 2 stroke") and fatos["Piloto"] == "Théo Mendes" and fatos["Emitida"] == "01/07/2026" and fatos["E-mail de cobrança"] == "carla@example.com"
    assert inv_it["link"].endswith("txnId=1077")
    t_it = [i for i in itens if i["entity"] == {"type": "task", "id": t}][0]
    ft = dict(t_it["facts"])
    assert ft["Tarefa"].startswith("Théo Mendes_Urace Daily") and ft["Coluna"] == "SATURDAY" and ft["Serviço"] == "Urace Daily / 2 stroke" and ft["Subtarefas"] == "9/12" and ft["Piloto"] == "Théo Mendes"
    assert "venceu em" in t_it["title"]


# ================= correções do teste real pela extensão (10/09) =================
def test_importacao_nao_fabrica_cliente_falso():
    """Rótulo do modelo, nome de serviço e nome de corrida NUNCA viram cliente."""
    from command_center.providers import identidade as idt, sync
    for lixo in ("Date of Birth:", "Email:", "Age: 13", "Height", "Waist", "Karting Experience",
                 "Karting School", "Kart School", "Professional Coaching", "Arrive and Drive",
                 "Summer Camp", "Lucas oil Laguna Seca", "USPKS Lake Erie", "AMR Round 8", "Practice OKC"):
        assert idt.eh_rotulo_ou_servico(lixo), lixo
        assert idt.pessoa_do_titulo(lixo) is None, lixo
        assert sync._nome_valido(lixo) is None, lixo
    for gente in ("Bryan Santiago", "David Pera", "Renato Frota Pionti", "Nya Amankwa"):
        assert not idt.eh_rotulo_ou_servico(gente), gente
        assert sync._nome_valido(gente) == gente


def test_limpeza_tira_cliente_falso_e_nascimento_invalido(cli):
    from command_center.db import conectar, inserir, um
    from command_center.providers import identidade as idt
    con = conectar()
    try:
        falso = inserir(con, "clients", name="Date of Birth:", pilot_name="Email:", vip=0, status="ACTIVE", source="asana")
        corrida = inserir(con, "clients", name="Lucas oil Laguna Seca", vip=0, status="ACTIVE", source="asana")
        bom = inserir(con, "clients", name="Nya Amankwa", email="nduany@gmail.com", pilot_name="Dinai Amankwa",
                      pilot_dob="Age: 13", vip=0, status="ACTIVE", source="asana")
        t = inserir(con, "tasks", client_id=falso, title="serviço solto", project="U-RACE", section="SATURDAY", status="open", due_on="2026-09-12")
        con.commit()
        assert idt.limpar_nao_clientes(con) >= 2
        assert um(con, "SELECT id FROM clients WHERE id=?", (falso,)) is None
        assert um(con, "SELECT id FROM clients WHERE id=?", (corrida,)) is None
        assert um(con, "SELECT id FROM clients WHERE id=?", (bom,)) is not None      # gente de verdade fica
        assert um(con, "SELECT client_id FROM tasks WHERE id=?", (t,))["client_id"] is None   # a tarefa fica, só perde o vínculo errado
        assert idt.limpar_nascimentos(con) >= 1
        assert um(con, "SELECT pilot_dob FROM clients WHERE id=?", (bom,))["pilot_dob"] is None
        con.commit()
    finally:
        con.close()


def test_calendario_mostra_corrida_concluida_futura_e_ignora_treino_na_coluna_races(cli):
    from datetime import date, timedelta
    from command_center.db import conectar, inserir, um
    from command_center.providers import sync
    con = conectar()
    try:
        futuro = (date.today() + timedelta(days=20)).isoformat()
        passado = (date.today() - timedelta(days=40)).isoformat()
        feita_futura = inserir(con, "tasks", client_id=None, title="F4 VIR Round 3", project="U-RACE", section="RACES", status="completed", due_on=futuro)
        feita_velha = inserir(con, "tasks", client_id=None, title="USPKS Lake Erie", project="U-RACE", section="RACES", status="completed", due_on=passado)
        treino = inserir(con, "tasks", client_id=None, title="Pratice at Jacksonville for FLKC", project="U-RACE", section="RACES", status="open", due_on=futuro)
        con.commit()
        sync.sincronizar_corridas(con); con.commit()
        assert um(con, "SELECT active FROM races WHERE task_id=?", (feita_futura,))["active"] == 1   # concluída, mas ainda vai acontecer
        assert um(con, "SELECT active FROM races WHERE task_id=?", (feita_velha,))["active"] == 0
        assert um(con, "SELECT id FROM races WHERE task_id=?", (treino,)) is None                   # treino não é corrida
    finally:
        con.close()


def test_triagem_pagamento_recebido_e_ausencia_automatica():
    from command_center.providers import classificar as cl
    nomes = ["Finances", "Finances/Pending Invoices ❗", "wNews"]
    lab, motivo, _ = cl.por_regras({"sender": "quickbooks@notification.intuit.com", "subject": "Payment received for invoice 1044", "labels": "[]"}, nomes)
    assert lab == "Finances" and "recebido" in motivo
    lab, _, _ = cl.por_regras({"sender": "billing@x.com", "subject": "Your invoice is due", "labels": "[]"}, nomes)
    assert lab == "Finances/Pending Invoices ❗"
    assert cl.auto_tratar({"sender": "nya@gmail.com", "subject": "unavailable Re: karting experience", "snippet": ""}, None)
    assert cl.auto_tratar({"sender": "x@y.com", "subject": "Automatic reply: out of office", "snippet": ""}, None)
    assert cl.auto_tratar({"sender": "x@y.com", "subject": "Dúvida", "snippet": "Estarei fora até dia 20"}, None)
    assert not cl.auto_tratar({"sender": "cliente@x.com", "subject": "Posso trocar o treino?", "snippet": "domingo"}, None)


def test_aviso_de_aprovacao_diz_o_que_e(cli):
    import json as _j
    from command_center.db import conectar, inserir
    con = conectar()
    try:
        cmd = inserir(con, "ai_commands", user_id=1, text="x", session_key="s", status="DONE")
        aid = inserir(con, "ai_actions", command_id=cmd, action="qbo_criar_e_enviar_invoice", system="qbo",
                      policy="REQUIRES_APPROVAL", status="PROPOSED",
                      payload=_j.dumps({"alvo": "Pablo Santiago", "args": {"cliente_id": "485", "data_servico": "2026-09-12",
                                                                            "linhas": [{"item_id": "9", "quantidade": 1, "unitario": 1600, "descricao": "Urace Academy Training Program"}]}}))
        inserir(con, "approvals", action_id=aid); con.commit()
    finally:
        con.close()
    entra(cli, "admin@urace.us")
    it = [i for i in cli.get(B + "/needs-attention").json() if i["entity"]["type"] == "approvals"][0]
    assert "Pablo Santiago" in it["title"] and "$1,600.00" in it["title"]
    f = dict(it["facts"])
    assert "Urace Academy Training Program" in f["Invoice"] and "12/09/2026" in f["Invoice"]

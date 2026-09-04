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
    assert r["quickbooks"]["status"] == "DISCONNECTED" and "P-11" in r["quickbooks"]["detail"]["nota"]
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

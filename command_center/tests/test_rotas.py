"""Dashboard, atenção, clientes, busca, políticas — com espelhos
semeados por SQL (sem rede). Providers desconectados aqui: o teste de
sync prova que isso vira 'not connected', nunca 500."""
import os
import tempfile
from datetime import date, timedelta

import pytest

os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc-rotas.sqlite")
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
    r = cli.post(B + "/sync", headers=h)
    assert r.status_code == 200
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

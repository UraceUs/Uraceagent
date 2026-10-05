"""Cargos Mecânico e Coach + checklists nativos (#92).

Dono, 05/10: o mecânico "tem acesso aos processos que ele está envolvido" (acesso aprovado
como proposto); coach com o mesmo acesso por enquanto; checklists da planilha Master Checklist,
nativos, editáveis de gerente para cima; foto opcional em todo item e obrigatória onde o gerente
marcar.
"""
import io
import os
from datetime import date, timedelta

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, um  # noqa: E402
from command_center.providers import checklists as ck  # noqa: E402

SENHA = "senha-forte-123"
HOJE = "2026-10-05"
C = "/ops/api/checklists"

# A grade como a API do Sheets devolve a aba "Master Operations" (célula mesclada só na primeira coluna)
GRADE = [
    [],
    ["", "kart Racing Team - Master Operations"],
    ["", "Practice Day / Kart School", "", "", "", "", "Technical Inspection", "", "Race Event", "", "", "", "", "", "Vehicle Maintenance"],
    ["", "The day before Checklist", "Mechanic Checklist", "Coach Checklist", "Lounge/VIP Area checklist", "", "Kart Checklist", "",
     "Checklist ( ADM )", "Preparation Before travel", "Wednesday:", "Mechanic checklist (RACE)", "Coach checklist", "", "Quarterly Team Checklist"],
    ["", "1. Check weather forecast", "At arrival morning tasks: 7:00 - 7:30 am", "At arrival morning tasks: 7:00 - 7:30 am",
     "1. Fill the fridge with water", "", "Engine:", "", "1. Confirm drivers (1 month prior)", "Kart equipment",
     "1. Position the trailer in the pit spot", "1. Do the kart checklist", "1. Track walk with drivers Thursday 7am", "", "1. Change the van's oil"],
    ["", "2. Prepare rain tires and wheels", "1. Open the garage", "1. Open the VIP Lounge", "2. Fill the coffee machine with water", "",
     "1. Check engine oil (change if needed)", "", "2. Pre-race invoice", "1. Racing engines", "2. Unload the trailer",
     "2. Check bottom of front bumper for holes", "2. Check all MyChron batteries", "", "2. Check the van's brake fluid"],
    ["", "", "2. Turn on the AC to 75°F", "", "", "", "2. Check engine mount tightness", "", "", "", "Tent assembly"],
    ["", "", "", "", "", "", "Chassis:", "", "", "", "1. Assemble tent"],
    ["", "", "", "", "", "", "1. Front bumper clamp tightness"],
]


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    monkeypatch.setattr(ck, "hoje", lambda: HOJE)
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "admin@urace.us", "Admin", "ADMIN", SENHA)
    auth.criar_usuario(con, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    mec = auth.criar_usuario(con, "luis@urace.us", "Luis", "OPERATOR", SENHA)
    coach = auth.criar_usuario(con, "hernan@urace.us", "Hernan", "VIEWER", SENHA)
    leo = inserir(con, "clients", name="Maria Santos", pilot_name="Leo Santos", email="familia@example.com", status="ACTIVE", source="manual")
    inserir(con, "emails", client_id=leo, mailbox="urace", subject="assunto privado", last_at=(date.today() - timedelta(days=4)).isoformat() + "T10:00:00Z")
    inserir(con, "invoices", client_id=leo, doc_number="1031", amount=500, balance=0, status="paid", issued_on="2026-09-01")
    tarefa = inserir(con, "tasks", client_id=leo, title="Leo Santos_Urace Daily_Arrive and Drive [1/1]", status="open",
                     due_on=HOJE, section="SUNDAY")
    corrida = inserir(con, "races", name="ROK Cup Florida", date_start=HOJE, date_end="2026-10-06", source="manual")
    inserir(con, "race_invites", race_id=corrida, client_id=leo, status="confirmed")
    ck.importar(con, GRADE)
    con.commit(); con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        c.ids = {"mec": mec, "coach": coach, "leo": leo, "tarefa": tarefa, "corrida": corrida}
        yield c


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def da_cargo(cli, uid, cargo):
    h = entra(cli, "admin@urace.us")
    r = cli.post(f"/ops/api/users/{uid}/cargo", json={"cargo": cargo}, headers=h)
    assert r.status_code == 200, r.text


# ------------------------------------------------------------------ cargo
def test_o_login_ja_diz_o_cargo(cli):
    """Sem isto, o celular do mecânico abre o painel geral até recarregar a página."""
    da_cargo(cli, cli.ids["mec"], "MECANICO")
    cli.cookies.clear()
    r = cli.post("/ops/api/auth/login", json={"email": "luis@urace.us", "password": SENHA})
    assert r.json()["cargo"] == "MECANICO"


def test_cargo_vira_operator_e_so_alcanca_o_que_e_do_box(cli):
    da_cargo(cli, cli.ids["coach"], "COACH")
    assert dict(um(conectar(), "SELECT role, cargo FROM users WHERE id=?", (cli.ids["coach"],))) == {"role": "OPERATOR", "cargo": "COACH"}, \
        "o coach era VIEWER: o cargo leva a OPERATOR, que é o que deixa preencher"
    da_cargo(cli, cli.ids["mec"], "MECANICO")
    entra(cli, "luis@urace.us")
    assert cli.get("/ops/api/auth/me").json()["cargo"] == "MECANICO"
    for ok in ("/ops/api/meu-dia", "/ops/api/clients", f"/ops/api/clients/{cli.ids['leo']}", "/ops/api/estoque",
               "/ops/api/balcao/invoices", f"{C}/modelos"):
        assert cli.get(ok).status_code == 200, ok
    for nao in ("/ops/api/dashboard", "/ops/api/needs-attention", "/ops/api/crm/inbox", "/ops/api/biblioteca",
                f"/ops/api/clients/{cli.ids['leo']}/monthly", "/ops/api/races", "/ops/api/site/agendamentos",
                "/ops/api/invoices", "/ops/api/users", "/ops/api/sales/board"):
        assert cli.get(nao).status_code == 403, nao
    card = cli.get(f"/ops/api/clients/{cli.ids['leo']}").json()
    assert card["emails"] == [] and card["invoices"] is None and card["ai_actions"] == [], "o card sem e-mail, IA e valores"
    assert not any(t["kind"] in ("EMAIL", "INVOICE") for t in card["timeline"])


def test_mudar_o_papel_tira_o_cargo(cli):
    da_cargo(cli, cli.ids["mec"], "MECANICO")
    h = entra(cli, "admin@urace.us")
    assert cli.post(f"/ops/api/users/{cli.ids['mec']}/role", json={"role": "MANAGER"}, headers=h).status_code == 200
    assert um(conectar(), "SELECT cargo FROM users WHERE id=?", (cli.ids["mec"],))["cargo"] is None
    assert cli.post(f"/ops/api/users/{cli.ids['mec']}/cargo", json={"cargo": "PILOTO"}, headers=h).status_code == 400


# ------------------------------------------------------------------ planilha
def test_importa_a_planilha_como_esta_com_grupos_e_secoes():
    cks = {c["name"]: c for c in ck.interpretar(GRADE)}
    assert cks["Mechanic Checklist"]["section"] == "Practice Day / Kart School"
    assert cks["Mechanic Checklist"]["itens"][0] == {"grupo": "At arrival morning tasks: 7:00 - 7:30 am", "text": "Open the garage"}
    assert [i["grupo"] for i in cks["Kart Checklist"]["itens"]] == ["Engine:", "Engine:", "Chassis:"]
    assert cks["Coach checklist"]["section"] == "Race Event" and cks["Coach Checklist"]["section"] == "Practice Day / Kart School"
    assert cks["Wednesday:"]["itens"][-1] == {"grupo": "Tent assembly", "text": "Assemble tent"}


def test_reimportar_nao_desfaz_o_que_o_gerente_editou(cli):
    con = conectar()
    t = um(con, "SELECT id FROM checklist_templates WHERE name='Mechanic Checklist'")
    con.execute("UPDATE checklist_templates SET quando='avulso' WHERE id=?", (t["id"],)); con.commit()
    r = ck.importar(con, GRADE)
    assert r["novos"] == [] and "Mechanic Checklist" in r["ja_existiam"]
    assert um(con, "SELECT quando FROM checklist_templates WHERE id=?", (t["id"],))["quando"] == "avulso"


# ------------------------------------------------------------------ meu dia e preencher
def test_meu_dia_mostra_os_checklists_do_cargo(cli):
    da_cargo(cli, cli.ids["mec"], "MECANICO")
    da_cargo(cli, cli.ids["coach"], "COACH")
    entra(cli, "luis@urace.us")
    d = cli.get("/ops/api/meu-dia").json()
    assert [s["cliente"] for s in d["servicos"]] == ["Leo Santos"]
    assert {c["nome"] for c in d["do_dia"]} == {"The day before Checklist", "Mechanic Checklist"}, "nada do coach para o mecânico"
    assert [c["nome"] for c in d["servicos"][0]["checklists"]] == ["Kart Checklist"]
    corrida = d["corridas"][0]
    assert {c["nome"] for c in corrida["checklists"]} == {"Preparation Before travel", "Wednesday:", "Mechanic checklist (RACE)"}
    assert corrida["pilotos"][0]["piloto"] == "Leo Santos" and corrida["pilotos"][0]["checklists"][0]["nome"] == "Kart Checklist"
    assert "Checklist ( ADM )" not in {c["nome"] for c in corrida["checklists"]}
    entra(cli, "hernan@urace.us")
    assert {c["nome"] for c in cli.get("/ops/api/meu-dia").json()["do_dia"]} == {"Coach Checklist", "Lounge/VIP Area checklist"}


def _png():
    from PIL import Image
    b = io.BytesIO(); Image.new("RGB", (40, 30), (200, 10, 10)).save(b, "PNG")
    return b.getvalue()


def test_mecanico_preenche_com_foto_e_so_conclui_completo(cli):
    da_cargo(cli, cli.ids["mec"], "MECANICO")
    hg = entra(cli, "ger@urace.us")
    kart = cli.get(f"{C}/modelos").json()["modelos"]
    kart = next(t for t in kart if t["name"] == "Kart Checklist")
    # gerente torna a foto obrigatória no item do para-choque
    para = next(i for i in kart["itens"] if "bumper" in i["text"])
    assert cli.patch(f"{C}/itens/{para['id']}", json={"photo_required": True}, headers=hg).status_code == 200
    h = entra(cli, "luis@urace.us")
    assert cli.patch(f"{C}/itens/{para['id']}", json={"photo_required": False}, headers=h).status_code == 403, "modelo é do gerente"
    r = cli.post(f"{C}/runs", json={"template_id": kart["id"], "ctx": {"tipo": "task", "task_id": cli.ids["tarefa"]}}, headers=h)
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["cliente"] == "Leo Santos" and run["total"] == 3
    assert cli.post(f"{C}/runs", json={"template_id": kart["id"], "ctx": {"tipo": "task", "task_id": cli.ids["tarefa"]}},
                    headers=h).json()["id"] == run["id"], "o mesmo serviço abre o mesmo checklist"
    for it in run["itens"]:
        cli.post(f"{C}/runs/{run['id']}/itens/{it['id']}", json={"done": True}, headers=h)
    r = cli.post(f"{C}/runs/{run['id']}/concluir", headers=h)
    assert r.status_code == 400 and "foto: Front bumper" in r.json()["detail"]
    item = next(i for i in run["itens"] if i["photo_required"])
    r = cli.post(f"{C}/runs/{run['id']}/itens/{item['id']}/foto", files={"arquivo": ("x.png", _png(), "image/png")}, headers=h)
    assert r.status_code == 201
    fid = next(i for i in r.json()["itens"] if i["id"] == item["id"])["fotos"][0]
    f = cli.get(f"{C}/fotos/{fid}")
    assert f.status_code == 200 and f.content[:4] == b"RIFF", "WebP, sem EXIF"
    r = cli.post(f"{C}/runs/{run['id']}/concluir", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "completo"
    assert cli.post(f"{C}/runs/{run['id']}/itens/{item['id']}", json={"done": False}, headers=h).status_code == 400, "concluído não muda"


def test_checklist_inteiro_com_foto_obrigatoria_e_a_copia_nao_muda(cli):
    hg = entra(cli, "ger@urace.us")
    mod = next(t for t in cli.get(f"{C}/modelos").json()["modelos"] if t["name"] == "Mechanic Checklist")
    antigo = cli.post(f"{C}/runs", json={"template_id": mod["id"], "ctx": {"tipo": "dia"}}, headers=hg).json()
    cli.patch(f"{C}/modelos/{mod['id']}", json={"photo_required": True}, headers=hg)
    cli.post(f"{C}/modelos/{mod['id']}/itens", json={"text": "Check fire extinguisher"}, headers=hg)
    assert cli.get(f"{C}/runs/{antigo['id']}").json()["total"] == 2, "o que já começou fica como estava"
    novo = cli.post(f"{C}/runs", json={"template_id": mod["id"], "ctx": {"tipo": "dia", "data": "2026-10-06"}}, headers=hg).json()
    assert novo["total"] == 3
    for it in novo["itens"]:
        cli.post(f"{C}/runs/{novo['id']}/itens/{it['id']}", json={"done": True}, headers=hg)
    r = cli.post(f"{C}/runs/{novo['id']}/concluir", headers=hg)
    assert r.status_code == 400 and "pelo menos uma" in r.json()["detail"]


def test_mecanico_nao_abre_checklist_do_coach(cli):
    da_cargo(cli, cli.ids["mec"], "MECANICO")
    h = entra(cli, "luis@urace.us")
    coach = next(t for t in cli.get(f"{C}/modelos").json()["modelos"] if t["cargo"] == "COACH")
    assert cli.post(f"{C}/runs", json={"template_id": coach["id"], "ctx": {"tipo": "dia"}}, headers=h).status_code == 403


def test_incompleto_de_ontem_vai_para_precisa_de_atencao(cli):
    con = conectar()
    t = um(con, "SELECT id FROM checklist_templates WHERE name='Mechanic Checklist'")
    ck.abrir(con, t["id"], {"tipo": "dia", "data": (date.fromisoformat(HOJE) - timedelta(days=1)).isoformat()})
    con.commit()
    entra(cli, "ger@urace.us")
    a = [x for x in cli.get("/ops/api/needs-attention").json() if x["entity"]["type"] == "checklist_run"]
    assert a and a[0]["title"] == "1 checklist(s) incompleto(s)"

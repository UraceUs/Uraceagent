"""Conta do site ↔ cliente interno (#42): o sistema sugere, a equipe confirma, e só então o
cliente vê o histórico — nunca o serviço de outra pessoa."""
import os
import zlib

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import atencao, auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, todos, um  # noqa: E402
from command_center.providers import vinculo_site as vs  # noqa: E402
from command_center.tests.dados_portal import ENDERECO, MEDIDAS, piloto as dados_piloto  # noqa: E402

SENHA = "senha-forte-123"


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "op@urace.us", "Operador", "OPERATOR", SENHA)
    auth.criar_usuario(c, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    enzo = inserir(c, "clients", name="Paulo Kurian", pilot_name="Enzo Kurian", email="paulo@kurian.com", phone="407-555-0142", status="ACTIVE", source="asana")
    outro = inserir(c, "clients", name="Rita Gomes", pilot_name="Leo Gomes", email="rita@gomes.com", phone="321-555-0100", status="ACTIVE", source="asana")
    inserir(c, "tasks", client_id=enzo, title="Enzo Kurian_Urace Daily_Using Own Kart [1/1]", project="U-RACE", section="SATURDAY",
            status="completed", due_on="2026-09-12", fields='{"nota": "nota interna: pagar com desconto"}')
    inserir(c, "tasks", client_id=enzo, title="Enzo Kurian_Urace Academy_2 stroke [2/4]", project="U-RACE", section="SUNDAY", status="open", due_on="2026-10-04")
    inserir(c, "tasks", client_id=outro, title="Leo Gomes_Urace Daily_Rental Kart [1/1]", project="U-RACE", section="FRIDAY", status="completed", due_on="2026-09-10")
    c.commit(); c.close()
    with TestClient(app, base_url="https://cc.test") as t:
        t.ids = {"enzo": enzo, "outro": outro}
        yield t


def cliente(cli, email, nome="Paulo Kurian", tel=None, piloto=None):
    cli.cookies.clear()
    r = cli.post("/ops/api/portal/signup", json={"name": nome, "email": email, "password": "corrida-segura-9", "birth_date": "1980-01-01",
                                                 **ENDERECO, "phone": tel or f"(689) 555-{zlib.crc32(email.encode()) % 10000:04d}",
                                                 "accept_terms": True})
    assert r.status_code == 201, r.text
    h = {"X-CSRF": cli.cookies.get("cp_csrf")}
    if piloto:
        assert cli.post("/ops/api/portal/drivers", headers=h, json=dados_piloto(piloto)).status_code == 201
    return h, r.json()["id"]


def equipe(cli, email="op@urace.us"):
    cli.cookies.clear()
    cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA})
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def test_sugere_por_email_telefone_e_nome_do_piloto(cli):
    _, a1 = cliente(cli, "paulo@kurian.com", nome="P. Kurian")
    _, a2 = cliente(cli, "outro@mail.com", nome="Alguém Silva", tel="(321) 555-0100")
    _, a3 = cliente(cli, "terceiro@mail.com", nome="Pai Qualquer", piloto="Enzo Kurian")
    _, a4 = cliente(cli, "ninguem@mail.com", nome="Zé Ninguém")
    equipe(cli)
    contas = {c["id"]: c for c in cli.get("/ops/api/site/contas").json()["contas"]}
    assert contas[a1]["sugestao"]["client_id"] == cli.ids["enzo"] and contas[a1]["sugestao"]["motivo"] == "mesmo e-mail"
    assert contas[a2]["sugestao"]["client_id"] == cli.ids["outro"] and contas[a2]["sugestao"]["motivo"] == "mesmo telefone"
    assert contas[a3]["sugestao"]["client_id"] == cli.ids["enzo"] and "piloto" in contas[a3]["sugestao"]["motivo"]
    assert contas[a4]["sugestao"] is None
    c = conectar()
    assert um(c, "SELECT client_id FROM portal_accounts WHERE id=?", (a1,))["client_id"] is None, "sugestão não é vínculo"


def test_cliente_novo_no_painel_vira_sugestao_sozinho(cli):
    _, a = cliente(cli, "nova@mail.com", nome="Carla Nova", piloto="Nina Nova")
    equipe(cli)
    assert cli.get("/ops/api/site/contas").json()["contas"][0]["sugestao"] is None
    c = conectar(); novo = inserir(c, "clients", name="Carla Nova", pilot_name="Nina Nova", status="NEW", source="asana"); c.commit(); c.close()
    assert cli.get("/ops/api/site/contas").json()["contas"][0]["sugestao"]["client_id"] == novo


def test_historico_so_depois_do_vinculo_e_sem_nota_interna(cli):
    hc, a = cliente(cli, "paulo@kurian.com")
    assert cli.get("/ops/api/portal/history").json() == {"linked": False, "services": []}
    h = equipe(cli)
    assert cli.post(f"/ops/api/site/contas/{a}/vincular", headers=h, json={"client_id": cli.ids["enzo"]}).status_code == 200
    cli.cookies.clear()
    cli.post("/ops/api/portal/login", json={"email": "paulo@kurian.com", "password": "corrida-segura-9"})
    hist = cli.get("/ops/api/portal/history").json()
    assert hist["linked"] and hist["services"] == [
        {"date": "2026-10-04", "service": "Urace Academy · 2 stroke", "status": "scheduled"},
        {"date": "2026-09-12", "service": "Urace Daily · Using Own Kart", "status": "done"}]
    assert "nota interna" not in str(hist) and "Rental" not in str(hist), "nada de nota, nada de outro cliente"
    assert cli.get("/ops/api/portal/me").json()["linked"] is True


def test_um_cliente_so_uma_conta_e_card_separado_nao(cli):
    _, a1 = cliente(cli, "a@mail.com")
    _, a2 = cliente(cli, "b@mail.com")
    h = equipe(cli)
    assert cli.post(f"/ops/api/site/contas/{a1}/vincular", headers=h, json={"client_id": cli.ids["enzo"]}).status_code == 200
    r = cli.post(f"/ops/api/site/contas/{a2}/vincular", headers=h, json={"client_id": cli.ids["enzo"]})
    assert r.status_code == 400 and "a@mail.com" in r.json()["detail"]
    c = conectar(); sep = inserir(c, "clients", name="Corrida X", kind="separado", status="ACTIVE", source="asana"); c.commit(); c.close()
    assert cli.post(f"/ops/api/site/contas/{a2}/vincular", headers=h, json={"client_id": sep}).status_code == 400
    contas = {x["id"]: x for x in cli.get("/ops/api/site/contas?filtro=todas").json()["contas"]}
    assert contas[a2]["sugestao"] is None or contas[a2]["sugestao"]["client_id"] != cli.ids["enzo"], "cliente ocupado não é sugerido"


def test_cliente_nao_se_vincula_e_desvincular_e_do_gerente(cli):
    hc, a = cliente(cli, "paulo@kurian.com")
    assert cli.post(f"/ops/api/site/contas/{a}/vincular", headers=hc, json={"client_id": cli.ids["enzo"]}).status_code == 401
    h = equipe(cli)
    cli.post(f"/ops/api/site/contas/{a}/vincular", headers=h, json={"client_id": cli.ids["enzo"]})
    assert cli.post(f"/ops/api/site/contas/{a}/desvincular", headers=h).status_code == 403
    h = equipe(cli, "ger@urace.us")
    assert cli.post(f"/ops/api/site/contas/{a}/desvincular", headers=h).status_code == 200
    ev = [x["event"] for x in todos(conectar(), "SELECT event FROM audit_logs WHERE event LIKE 'portal.%link'")]
    assert ev == ["portal.link", "portal.unlink"]


def test_card_do_cliente_mostra_conta_pilotos_e_medidas(cli):
    hc, a = cliente(cli, "paulo@kurian.com")
    cli.post("/ops/api/portal/drivers", headers=hc, json=dados_piloto("Enzo Kurian", measures={**MEDIDAS, "height_in": 55, "suit_size": "140"}))
    h = equipe(cli)
    assert cli.get(f"/ops/api/site/contas/do-cliente/{cli.ids['enzo']}").json()["conta"] is None
    cli.post(f"/ops/api/site/contas/{a}/vincular", headers=h, json={"client_id": cli.ids["enzo"]})
    conta = cli.get(f"/ops/api/site/contas/do-cliente/{cli.ids['enzo']}").json()["conta"]
    assert conta["email"] == "paulo@kurian.com" and conta["drivers"][0]["measures"]["height_in"] == 55.0 and conta["drivers"][0]["measures"]["suit_size"] == "140"
    assert "pw_hash" not in conta


def test_atencao_conta_sem_vinculo(cli):
    cliente(cli, "solta@mail.com", nome="Conta Solta")
    chaves = {i["key"]: i for i in atencao.coletar(conectar())}
    assert "conta-site:portal_account:sem_vinculo" in chaves


def test_servico_do_titulo():
    assert vs._servico("David Pera_Urace Daily_Using Own Kart [1/1]") == "Urace Daily · Using Own Kart"
    assert vs._servico("Só um nome") == "Session"

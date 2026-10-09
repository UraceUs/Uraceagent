"""#180: o balcão no celular, com uma mão — peça primeiro, piloto do dia depois, revisão do gerente.

Dono, 09/10: *"escaneou a peça, identificou ali … já abre um pop-up para selecionar os pilotos
que estão no dia … quando ele clicar no cliente, já registra aquela peça"*; *"já sobe … no
balcão, no Command Center, só que na seção de revisão"*; e *"ponto urace.us … login, senha e
pronto … sem ter o risco de abrir outras seções"*.
"""
import os

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, um  # noqa: E402
from command_center.providers import balcao, balcao_rapido, estoque  # noqa: E402
from command_center.tests.test_balcao import SENHA, QboFalso, entra  # noqa: E402

B = "/ops/api/balcao"
HOJE = "2026-10-09"
AMANHA = "2026-10-10"


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    monkeypatch.delenv("CC_BALCAO_HOSTS", raising=False)
    qbo = QboFalso()
    import command_center.providers as prov
    monkeypatch.setattr(prov, "modulo", lambda nome: qbo if nome == "quickbooks" else None)
    monkeypatch.setattr(balcao, "hoje", lambda: HOJE)
    con = conectar(); aplicar_schema(con)
    mec = auth.criar_usuario(con, "mec@urace.us", "Mecânico", "OPERATOR", SENHA)
    con.execute("UPDATE users SET cargo='MECANICO' WHERE email='mec@urace.us'")
    auth.criar_usuario(con, "mec2@urace.us", "Outro mecânico", "OPERATOR", SENHA)
    auth.criar_usuario(con, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    leo = inserir(con, "clients", name="Maria Santos", pilot_name="Leo Santos", email="familia@example.com", status="ACTIVE")
    inserir(con, "invoices", client_id=leo, doc_number="URACE-0001", amount=10, balance=0, status="paid",
            issued_on="2026-09-01", customer_ref="qbo-cust-7")
    ana = inserir(con, "clients", name="Ana Lima", status="ACTIVE")
    conta = inserir(con, "portal_accounts", email="familia@example.com", pw_salt="x", pw_hash="x", name="Maria Santos",
                    birth_date="1980-01-01", terms_accepted_at="2026-09-30T00:00:00Z", client_id=leo)
    p_leo = inserir(con, "portal_pilots", account_id=conta, name="Leo Santos", client_id=leo)
    p_novo = inserir(con, "portal_pilots", account_id=conta, name="Bia Santos")        # ainda sem card
    inserir(con, "bookings", account_id=conta, pilot_id=p_leo, date=AMANHA, period="manha", status="confirmada")
    inserir(con, "bookings", account_id=conta, pilot_id=p_novo, date=AMANHA, period="tarde", status="pendente")
    inserir(con, "bookings", account_id=conta, pilot_id=p_leo, date=HOJE, period="manha", status="cancelada")
    corrida = inserir(con, "races", name="Orlando Cup", date_start=AMANHA, date_end=AMANHA, active=1)
    inserir(con, "race_invites", race_id=corrida, client_id=leo, status="confirmed")
    inserir(con, "race_invites", race_id=corrida, client_id=ana, status="invited")
    para = estoque.criar_item(con, "peca", "Front bumper Tony Kart", category="hardware", price=89.5)
    estoque.entrada(con, para, qty=5)
    con.execute("UPDATE stock_items SET qbo_item_id='qi-1', qbo_item_name='Parts:Front bumper' WHERE id=?", (para,))
    balcao.cadastrar_codigo(con, "7891234567895", para)
    con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        c.qbo, c.leo, c.ana, c.p_leo, c.p_novo, c.para, c.mec = qbo, leo, ana, p_leo, p_novo, para, mec
        yield c


def _con():
    return conectar()


# ------------------------------------------------------------------ os pilotos do dia
def test_pilotos_do_dia_saem_das_sessoes_corridas_e_servicos(cli):
    con = _con()
    inserir(con, "tasks", title="Revisão do motor", client_id=cli.ana, due_on=AMANHA)
    ps = balcao_rapido.pilotos_do_dia(con, AMANHA)
    nomes = {p["nome"]: p for p in ps}
    assert set(nomes) == {"Leo Santos", "Bia Santos", "Ana Lima"}
    assert nomes["Leo Santos"]["client_id"] == cli.leo and set(nomes["Leo Santos"]["origens"]) == {"sessão", "corrida"}, "um botão só"
    assert nomes["Bia Santos"]["client_id"] is None and nomes["Bia Santos"]["pilot_id"] == cli.p_novo
    assert set(nomes["Ana Lima"]["origens"]) == {"corrida", "serviço"}
    assert balcao_rapido.pilotos_do_dia(con, HOJE) == [], "sessão cancelada não entra"
    assert "email" not in str(ps) and "price" not in str(ps), "sem contato nem valor"


# ------------------------------------------------------------------ o celular: peça → piloto
def test_ler_a_peca_e_tocar_no_piloto_registra_pendente_sem_cobrar(cli):
    h = entra(cli)
    r = cli.get(f"{B}/ler", params={"codigo": "7891234567895"})
    assert r.json()["tipo"] == "peca" and r.json()["item"]["name"] == "Front bumper Tony Kart"
    r = cli.post(f"{B}/rapido", json={"codigo": " 7891234567895 ", "data": AMANHA, "client_id": cli.leo}, headers=h)
    assert r.status_code == 201
    p = r.json()
    assert (p["status"], p["item_id"], p["client_id"], p["pilot_name"], p["service_date"], p["peca"]) == \
        ("pendente", cli.para, cli.leo, "Leo Santos", AMANHA, "Front bumper Tony Kart")
    con = _con()
    assert con.execute("SELECT COUNT(*) FROM counter_scans").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM stock_charges").fetchone()[0] == 0
    assert estoque.saldo(con, cli.para) == 5, "o estoque só muda quando o gerente confirma"
    assert not cli.qbo.chamadas, "nada vai ao QuickBooks pelo celular"
    tela = cli.get(f"{B}/rapido", params={"data": AMANHA}).json()
    assert [m["id"] for m in tela["minhas"]] == [p["id"]]
    assert next(x for x in tela["pilotos"] if x["client_id"] == cli.leo)["pecas"] == 1


def test_codigo_desconhecido_tambem_entra_e_qr_de_cliente_nao(cli):
    h = entra(cli)
    r = cli.post(f"{B}/rapido", json={"codigo": "NOVO-123", "data": AMANHA, "pilot_id": cli.p_novo}, headers=h)
    assert r.status_code == 201 and r.json()["item_id"] is None and r.json()["pilot_name"] == "Bia Santos"
    con = _con()
    cod = balcao.codigo_do_cliente(con, cli.leo)
    r = cli.post(f"{B}/rapido", json={"codigo": f"https://ops.urace.us/ops/c/{cod}", "client_id": cli.leo}, headers=h)
    assert r.status_code == 400 and "QR de um cliente" in r.json()["detail"]


def test_sem_piloto_fica_para_decidir_e_piloto_de_outro_card_e_recusado(cli):
    h = entra(cli)
    r = cli.post(f"{B}/rapido", json={"codigo": "7891234567895", "data": AMANHA}, headers=h)
    assert r.status_code == 201 and r.json()["client_id"] is None
    r = cli.post(f"{B}/rapido", json={"codigo": "7891234567895", "client_id": cli.ana, "pilot_id": cli.p_leo}, headers=h)
    assert r.status_code == 400 and "não batem" in r.json()["detail"]


def test_desfazer_so_a_propria_leitura_pendente(cli):
    h = entra(cli)
    pid = cli.post(f"{B}/rapido", json={"codigo": "7891234567895", "client_id": cli.leo}, headers=h).json()["id"]
    h2 = entra(cli, "mec2@urace.us")
    assert cli.post(f"{B}/rapido/{pid}/desfazer", headers=h2).status_code == 400
    h = entra(cli)
    assert cli.post(f"{B}/rapido/{pid}/desfazer", headers=h).status_code == 200
    assert _con().execute("SELECT COUNT(*) FROM counter_pending").fetchone()[0] == 0


# ------------------------------------------------------------------ a revisão do gerente
def test_o_mecanico_nao_ve_a_revisao(cli):
    entra(cli)
    assert cli.get(f"{B}/revisao").status_code == 403
    entra(cli, "ger@urace.us")
    assert cli.get(f"{B}/revisao").status_code == 200


def test_confirmar_cobra_na_invoice_do_dia_da_leitura(cli):
    h = entra(cli)
    pid = cli.post(f"{B}/rapido", json={"codigo": "7891234567895", "data": AMANHA, "client_id": cli.leo}, headers=h).json()["id"]
    h = entra(cli, "ger@urace.us")
    rev = cli.get(f"{B}/revisao").json()
    assert rev["total"] == 1 and rev["itens"][0]["por"] == "Mecânico" and rev["itens"][0]["item"]["price"] == 89.5
    r = cli.post(f"{B}/revisao/{pid}/confirmar", json={"modo": "cobrar"}, headers=h)
    assert r.status_code == 200 and r.json()["total"] == 0
    con = _con()
    p = um(con, "SELECT * FROM counter_pending WHERE id=?", (pid,))
    s = um(con, "SELECT * FROM counter_scans WHERE id=?", (p["scan_id"],))
    inv = um(con, "SELECT * FROM parts_invoices WHERE id=?", (s["parts_invoice_id"],))
    assert (p["status"], p["mode"], s["mode"], inv["service_date"]) == ("confirmada", "cobrar", "cobrar", AMANHA)
    assert estoque.saldo(con, cli.para) == 4
    assert cli.qbo.chamadas[-1][0] == "invoice" and cli.qbo.chamadas[-1][1]["data"] == AMANHA
    assert cli.post(f"{B}/revisao/{pid}/confirmar", json={"modo": "cobrar"}, headers=h).status_code == 400


def test_codigo_novo_so_confirma_depois_de_dizer_que_peca_e(cli):
    h = entra(cli)
    pid = cli.post(f"{B}/rapido", json={"codigo": "NOVO-777", "client_id": cli.leo}, headers=h).json()["id"]
    h = entra(cli, "ger@urace.us")
    r = cli.post(f"{B}/revisao/{pid}/confirmar", json={"modo": "guardar"}, headers=h)
    assert r.status_code == 400 and "código novo" in r.json()["detail"]
    con = _con()
    balcao.cadastrar_codigo(con, "NOVO-777", cli.para)
    r = cli.post(f"{B}/revisao/{pid}/confirmar", json={"modo": "guardar"}, headers=h)
    assert r.status_code == 200
    assert estoque.saldo(con, cli.para, client_id=cli.leo) == 1, "guardado no estoque do cliente, sem cobrar"


def test_piloto_sem_card_pede_o_cliente_na_revisao(cli):
    h = entra(cli)
    pid = cli.post(f"{B}/rapido", json={"codigo": "7891234567895", "pilot_id": cli.p_novo}, headers=h).json()["id"]
    h = entra(cli, "ger@urace.us")
    r = cli.post(f"{B}/revisao/{pid}/confirmar", json={"modo": "cobrar"}, headers=h)
    assert r.status_code == 400 and "escolha o cliente" in r.json()["detail"]
    r = cli.post(f"{B}/revisao/{pid}/confirmar", json={"modo": "cobrar", "client_id": cli.leo}, headers=h)
    assert r.status_code == 200


def test_peca_que_o_cliente_tem_guardada_pede_decisao_e_nada_muda(cli):
    con = _con()
    estoque.entrada(con, cli.para, qty=1, client_id=cli.leo, reason="guardado do cliente")
    h = entra(cli)
    pid = cli.post(f"{B}/rapido", json={"codigo": "7891234567895", "client_id": cli.leo}, headers=h).json()["id"]
    h = entra(cli, "ger@urace.us")
    r = cli.post(f"{B}/revisao/{pid}/confirmar", json={"modo": "cobrar"}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["motivo"] == "tem_do_cliente"
    assert um(con, "SELECT status FROM counter_pending WHERE id=?", (pid,))["status"] == "pendente"
    assert cli.post(f"{B}/revisao/{pid}/confirmar", json={"modo": "usar_do_cliente"}, headers=h).status_code == 200
    assert estoque.saldo(con, cli.para, client_id=cli.leo) == 0


def test_descartar(cli):
    h = entra(cli)
    pid = cli.post(f"{B}/rapido", json={"codigo": "7891234567895", "client_id": cli.leo}, headers=h).json()["id"]
    h = entra(cli, "ger@urace.us")
    assert cli.post(f"{B}/revisao/{pid}/descartar", json={"nota": "lida duas vezes"}, headers=h).json()["total"] == 0
    p = um(_con(), "SELECT * FROM counter_pending WHERE id=?", (pid,))
    assert (p["status"], p["review_note"]) == ("descartada", "lida duas vezes")


# ------------------------------------------------------------------ balcao.urace.us: só o balcão
def test_no_endereco_do_balcao_so_o_balcao_responde(cli):
    with TestClient(app, base_url="https://balcao.urace.us") as bc:
        r = bc.post("/ops/api/auth/login", json={"email": "ger@urace.us", "password": SENHA})
        assert r.status_code == 200 and r.json()["so_balcao"] is True
        h = {"X-CSRF": bc.cookies.get("cc_csrf")}
        assert bc.get("/ops/api/auth/me").json()["so_balcao"] is True
        assert bc.get(f"{B}/rapido").status_code == 200
        assert bc.get(f"{B}/ler", params={"codigo": "7891234567895"}).status_code == 200
        assert bc.post(f"{B}/rapido", json={"codigo": "7891234567895", "client_id": cli.leo}, headers=h).status_code == 201
        for caminho in ("/ops/api/clients", f"{B}/revisao", f"{B}/invoices", "/ops/api/estoque", "/ops/api/users"):
            assert bc.get(caminho).status_code == 403, f"{caminho}: nem o gerente abre outra seção aqui"
        assert bc.post(f"{B}/lancar", json={"client_id": cli.leo, "item_id": cli.para, "modo": "cobrar"},
                       headers=h).status_code == 403
        assert bc.get("/ops/mcp").status_code == 404
    entra(cli, "ger@urace.us")
    assert cli.get("/ops/api/auth/me").json()["so_balcao"] is False
    assert cli.get(f"{B}/revisao").status_code == 200, "no painel, o gerente revisa"

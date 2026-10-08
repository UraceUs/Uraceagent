"""Suits / Alpha Line (#153): pedidos de macacão, etapas com nota e imagem, medidas, e-mail ao
fornecedor pelo modelo, leads, fornecedores e a importação do projeto SUITS do Asana.

Dono, 08/10: "na aba de suítes ... registrar novo pedido ... Sempre dê a oportunidade ali de eu
adicionar uma nota, às vezes um screenshot para IA poder entender, já avançar com aquilo ali no
status que estiver" e "tem um padrão de envio. Salva esse padrão como template".
"""
import io
import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from command_center.api import agente_sdk, auth, ia
from command_center.api.main import app
from command_center.db import aplicar_schema, conectar, um
from command_center.providers import suits

SENHA = "senha-forte-123"
B = "/ops/api/suits"


# ------------------------------------------------------------------ medidas
def test_medidas_nas_duas_unidades():
    m = suits.normalizar_medidas({"head": "59", "forehead_neck": 42, "weight": "70", "foot": "42 EUR / 9 US"})
    assert m["head"] == {"v": 59.0, "u": "cm"} and m["foot"] == {"t": "42 EUR / 9 US"}
    assert suits.texto_medida("head", m["head"]) == "59 cm / 1'11\""
    assert suits.texto_medida("forehead_neck", m["forehead_neck"]) == "42 cm / 1'4.5\""
    assert suits.texto_medida("weight", m["weight"]) == "70 kg / 154.3 lb"
    pol = suits.normalizar_medidas({"wrist": "6.5", "weight": "150"}, "in", "lb")
    assert suits.texto_medida("wrist", pol["wrist"]) == "16.5 cm / 6.5\""
    assert suits.texto_medida("weight", pol["weight"]) == "68 kg / 150 lb"
    assert suits.normalizar_medidas({"head": ""}) == {}                     # vazio não vira zero
    for ruim in ({"orelha": 3}, {"head": "abc"}, {"head": -1}):
        with pytest.raises(suits.Invalido):
            suits.normalizar_medidas(ruim)


def test_bloco_de_medidas_na_ordem_do_fornecedor_e_6bis_so_quando_tem():
    m = suits.normalizar_medidas({"head": 59})
    b = suits.bloco_medidas(m).splitlines()
    assert b[0] == "1 – Head circumference — 59 cm / 1'11\"" and b[1].startswith("2 – Distance from forehead to neck — (missing)")
    assert not any(x.startswith("6bis") for x in b) and b[-1].startswith("29 – Foot size")
    assert any(x.startswith("6bis – Bust") for x in suits.bloco_medidas(suits.normalizar_medidas({"bust": 90})).splitlines())
    assert len(suits.faltando(m)) == 28


# ------------------------------------------------------------------ a API
@pytest.fixture(scope="module")
def cli():
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc-suits.sqlite")
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "admin@urace.us", "Admin Urace", "ADMIN", SENHA)
    auth.criar_usuario(con, "op@urace.us", "Lara Carvalho", "OPERATOR", SENHA)
    auth.criar_usuario(con, "viewer@urace.us", "Viewer", "VIEWER", SENHA)
    con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def _png():
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (2400, 1200), (217, 22, 23)).save(b, "PNG")
    return b.getvalue()


def test_registrar_avancar_anotar_com_imagem_e_pedir_a_ia(cli, monkeypatch):
    h = entra(cli, "op@urace.us")
    r = cli.post(B, headers=h, json={"customer_name": "Ryan Casner", "customer_email": "ryan@example.com", "language": "en",
                                     "driver_name": "Ryan Casner", "design": {"cores": "black / red, Pantone 1355 PC"},
                                     "medidas": {"valores": {"head": 59}, "unidade": "cm"}})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["status"] == "standby" and p["title"] == "Ryan Casner" and p["medidas_texto"]["head"] == "59 cm / 1'11\""
    assert p["notas"][0]["kind"] == "etapa"
    pid = p["id"]
    lista = cli.get(B + "?limit=10")
    assert lista.status_code == 200 and lista.headers["X-Total-Count"] == "1" and lista.json()[0]["id"] == pid
    # nota com screenshot, mudando a etapa e pedindo à IA para seguir
    chamadas = []
    monkeypatch.setattr(ia, "_executa", lambda *a: chamadas.append(a))
    r = cli.post(f"{B}/{pid}/notas", headers=h, data={"texto": "Cliente mandou as medidas no print", "status": "awaiting_measurements",
                                                      "pedir_ia": "true"},
                 files={"imagem": ("medidas.png", _png(), "image/png")})
    assert r.status_code == 201, r.text
    nota = r.json()
    assert nota["command_id"]
    p = cli.get(f"{B}/{pid}").json()
    assert p["status"] == "awaiting_measurements"
    n = [x for x in p["notas"] if x["kind"] == "nota"][0]
    assert n["tem_imagem"] and n["command_id"] == nota["command_id"] and n["status"] == "awaiting_measurements"
    img = cli.get(f"{B}/notas/{n['id']}/imagem")
    assert img.status_code == 200 and img.headers["content-type"] == "image/webp"
    from PIL import Image
    assert max(Image.open(io.BytesIO(img.content)).size) <= 1600          # comprimida
    con = conectar()
    c = um(con, "SELECT prompt FROM ai_commands WHERE id=?", (nota["command_id"],))
    con.close()
    assert "SUITS — pedido de macacão" in c["prompt"] and ".webp" in c["prompt"] and "idioma do cliente" in c["prompt"]
    assert chamadas and chamadas[0][0] == nota["command_id"]
    # entregue fecha o pedido; a linha do tempo guarda a troca
    r = cli.patch(f"{B}/{pid}", headers=h, json={"status": "delivered"})
    assert r.status_code == 200 and r.json()["closed"] == 1
    assert any(x["kind"] == "etapa" and "Delivered" in (x["text"] or "") for x in r.json()["notas"])
    assert cli.get(B + "?estado=abertos&limit=10").headers["X-Total-Count"] == "0"
    assert cli.post(f"{B}/{pid}/notas", headers=h, data={"status": "voando"}).status_code == 400


def test_medidas_parciais_e_apagar_uma(cli):
    h = entra(cli, "op@urace.us")
    pid = cli.post(B, headers=h, json={"customer_name": "Tyron Brouta"}).json()["id"]
    cli.patch(f"{B}/{pid}", headers=h, json={"medidas": {"valores": {"head": 59, "neck": 36}}})
    cli.patch(f"{B}/{pid}", headers=h, json={"medidas": {"valores": {"chest": 38}, "unidade": "in"}})
    p = cli.patch(f"{B}/{pid}", headers=h, json={"medidas": {"valores": {"neck": ""}}}).json()
    assert set(p["measurements"]) == {"head", "chest"} and p["medidas_texto"]["chest"] == "96.5 cm / 3'2\""
    assert cli.patch(f"{B}/{pid}", headers=h, json={"medidas": {"valores": {"head": "x"}}}).status_code == 400


def test_email_do_fornecedor_pelo_modelo(cli):
    h = entra(cli, "admin@urace.us")
    f = cli.post(f"{B}/fornecedores", headers=h, json={"name": "Usman", "contact": "Usman", "email": "speedinds@example.com",
                                                        "is_current": True}).json()
    pid = cli.post(B, headers=h, json={"customer_name": "Frankie Iadevaia", "quantity": 2,
                                       "design": {"cores": "Pantone 1355 PC"}}).json()["id"]
    e = cli.get(f"{B}/{pid}/email-fornecedor").json()
    assert e["para"] == "speedinds@example.com" and e["assunto"] == "SUIT - Frankie Iadevaia"
    assert e["corpo"].startswith("Hi Usman,\n\nWe have a new order:\n\n1 – Head circumference — (missing)")
    assert "Colors: Pantone 1355 PC" in e["corpo"] and "Quantity: 2 suits" in e["corpo"] and "Admin Urace\nUrace" in e["corpo"]
    assert e["faltam"] == ["29 medida(s)"]
    assert cli.post(f"{B}/{pid}/email-fornecedor/rascunho", headers=h).status_code == 400    # incompleto não vai
    # o modelo é editável (gerente) e precisa das medidas
    assert cli.put(f"{B}/modelo", headers=h, json={"subject": "x", "body": "sem medidas"}).status_code == 400
    m = cli.put(f"{B}/modelo", headers=h, json={"subject": "NEW SUIT - {piloto}", "body": "Hello {fornecedor}\n{medidas}"}).json()
    assert m["subject"] == "NEW SUIT - {piloto}"
    assert cli.get(f"{B}/{pid}/email-fornecedor").json()["assunto"] == "NEW SUIT - Frankie Iadevaia"
    h2 = entra(cli, "op@urace.us")
    assert cli.put(f"{B}/modelo", headers=h2, json={"subject": "a", "body": "{medidas}"}).status_code == 403
    assert cli.patch(f"{B}/fornecedores/{f['id']}", headers=h2, json={"price": "$1"}).status_code == 403


def test_rascunho_ao_fornecedor_no_gmail_com_tudo_preenchido(cli, monkeypatch):
    from command_center import providers
    h = entra(cli, "admin@urace.us")
    fid = cli.post(f"{B}/fornecedores", headers=h, json={"name": "Usman B", "email": "u@example.com"}).json()["id"]
    todas = {m[0]: 50 for m in suits.MEDIDAS if m[3] == "comp"} | {"weight": 70, "foot": "42 EUR"}
    pid = cli.post(B, headers=h, json={"customer_name": "Completo", "supplier_id": fid,
                                       "medidas": {"valores": todas}}).json()["id"]
    feitos = []
    monkeypatch.setattr(providers, "chamar", lambda s, f, **kw: feitos.append((s, f, kw, os.environ.get("APLICAR"))) or {"draft_id": "d1"})
    r = cli.post(f"{B}/{pid}/email-fornecedor/rascunho", headers=h)
    assert r.status_code == 200 and r.json()["draft_id"] == "d1"
    assert feitos[0][:2] == ("gmail", "gmail_rascunho") and feitos[0][2]["para"] == "u@example.com" and feitos[0][3] == "1"
    assert os.environ.get("APLICAR") is None                               # volta ao que era
    assert any(n["kind"] == "email" for n in cli.get(f"{B}/{pid}").json()["notas"])


def test_lead_vira_pedido(cli):
    h = entra(cli, "op@urace.us")
    lid = cli.post(f"{B}/leads", headers=h, json={"name": "Nathan", "email": "n@example.com", "notes": "Same suit as Chris Murray"}).json()["id"]
    p = cli.post(f"{B}/leads/{lid}/pedido", headers=h).json()
    assert p["customer_name"] == "Nathan" and any("Chris Murray" in (n["text"] or "") for n in p["notas"])
    lead = [x for x in cli.get(f"{B}/leads?estado=convertido").json() if x["id"] == lid][0]
    assert lead["status"] == "convertido" and lead["order_id"] == p["id"]
    assert cli.post(f"{B}/leads/{lid}/pedido", headers=h).json()["id"] == p["id"]     # não duplica


def test_fornecedor_atual_e_um_so(cli):
    h = entra(cli, "admin@urace.us")
    a = cli.post(f"{B}/fornecedores", headers=h, json={"name": "A", "is_current": True}).json()
    b = cli.post(f"{B}/fornecedores", headers=h, json={"name": "B", "is_current": True}).json()
    atuais = [f["id"] for f in cli.get(f"{B}/fornecedores").json() if f["is_current"]]
    assert atuais == [b["id"]] and a["id"] not in atuais


def test_quem_so_le_nao_entra(cli):
    entra(cli, "viewer@urace.us")
    assert cli.get(B).status_code == 403


# ------------------------------------------------------------ importar do Asana
TAREFAS = [
    {"gid": "1", "name": "Mikey Colins [não está pago]", "completed": False, "due_on": None, "notes": "",
     "memberships": [{"section": {"name": "Standby"}}],
     "custom_fields": [{"name": "Status", "display_value": "Standby"}, {"name": "Order Date", "display_value": "2026-05-04T00:00:00.000Z"}]},
    {"gid": "2", "name": "Alex Kalimnios", "completed": False, "due_on": "2026-07-24", "notes": "medidas no e-mail",
     "memberships": [{"section": {"name": "Order"}}],
     "custom_fields": [{"name": "Status", "display_value": "Awaiting Measurements"}, {"name": "Fornecedor", "display_value": "Usman"}]},
    {"gid": "3", "name": "Michael Fuller", "completed": True, "due_on": "2026-03-03", "notes": "",
     "memberships": [{"section": {"name": "Seção sem título"}}],
     "custom_fields": [{"name": "Status", "display_value": "In Transit"}, {"name": "Fornecedor", "display_value": "Usman"}]},
    {"gid": "4", "name": "T-shirt Urace", "completed": False, "due_on": None, "notes": "",
     "memberships": [{"section": {"name": "Order"}}], "custom_fields": [{"name": "Status", "display_value": "In Production"}]},
    {"gid": "5", "name": "Nathan", "completed": False, "notes": "tnlloyd19@example.com\nSame suit as Chris Murray",
     "memberships": [{"section": {"name": "SUIT LEADS"}}], "custom_fields": []},
    {"gid": "6", "name": "Suit Derek", "completed": False, "notes": "",
     "memberships": [{"section": {"name": "SUIT LEADS"}}], "custom_fields": [{"name": "Status", "display_value": "Canceled"}]},
    {"gid": "7", "name": "PALACE RACE WEAR", "completed": False,
     "notes": "Contato: Shamas Din\nE-mail: info@palace.example\nTelefone: +92 300\nTem FIA: Sim\nStatus: Talking\n"
              "Valor por macacão: $210 – $260\nFrete por macacão: —\nComentários: SFI 3.2A/5 Nomex",
     "memberships": [{"section": {"name": "Seleção de fornecedores"}}], "custom_fields": []},
    {"gid": "8", "name": "Links", "notes": "https://docs.google.com/x", "memberships": [{"section": {"name": "Seleção de fornecedores"}}]},
    {"gid": "9", "name": "Conferir pagamento do cliente", "memberships": [{"section": {"name": "Checklist para o pedido de macacão"}}]},
    {"gid": "10", "name": "📋 MODELO — New Order: <nome do cliente>", "memberships": [{"section": {"name": "Checklist para o pedido de macacão"}}]},
    {"gid": "11", "name": "Follow up on \"WHEEL DEAL SPORTS\"", "memberships": [{"section": {"name": "Fornecedores"}}]},
]


def test_importar_do_asana_sem_duplicar(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "imp.sqlite"))
    con = conectar(); aplicar_schema(con)
    r = suits.importar(con, TAREFAS)
    assert r == {"pedidos": 4, "leads": 2, "fornecedores": 1, "ja_tinha": 0, "ignoradas": 4}
    p = {x["asana_gid"]: dict(x) for x in con.execute("SELECT * FROM suit_orders").fetchall()}
    assert (p["1"]["status"], p["1"]["closed"], p["1"]["order_date"]) == ("standby", 0, "2026-05-04")
    assert p["2"]["status"] == "awaiting_measurements" and p["2"]["asana_notes"] == "medidas no e-mail"
    assert (p["3"]["status"], p["3"]["closed"]) == ("in_transit", 1)          # concluída no Asana: histórico, sem inventar "entregue"
    assert p["4"]["product"] == "T-shirt"
    usman = um(con, "SELECT id FROM suit_suppliers WHERE name='Usman'")["id"]
    assert p["2"]["supplier_id"] == usman == p["3"]["supplier_id"]
    leads = {x["asana_gid"]: dict(x) for x in con.execute("SELECT * FROM suit_leads").fetchall()}
    assert leads["5"]["email"] == "tnlloyd19@example.com" and leads["5"]["status"] == "aberto" and leads["6"]["status"] == "perdido"
    f = dict(um(con, "SELECT * FROM suit_suppliers WHERE asana_gid='7'"))
    assert (f["contact"], f["email"], f["has_fia"], f["price"], f["shipping"]) == ("Shamas Din", "info@palace.example", 1, "$210 – $260", None)
    # de novo: nada duplica, e o que a equipe mudou aqui fica
    con.execute("UPDATE suit_orders SET status='design_pending' WHERE asana_gid='1'")
    r2 = suits.importar(con, TAREFAS)
    assert r2["pedidos"] == r2["leads"] == r2["fornecedores"] == 0 and r2["ja_tinha"] == 7
    assert um(con, "SELECT status FROM suit_orders WHERE asana_gid='1'")["status"] == "design_pending"
    con.close()


def test_importar_pela_api(cli, monkeypatch):
    from command_center import providers

    class Asana:
        @staticmethod
        def tarefas_do_suits():
            return TAREFAS[:2]
    monkeypatch.setattr(providers, "modulo", lambda s: Asana())
    h = entra(cli, "op@urace.us")
    assert cli.post(f"{B}/importar", headers=h).status_code == 403       # importar é do gerente
    h = entra(cli, "admin@urace.us")
    r = cli.post(f"{B}/importar", headers=h)
    assert r.status_code == 200 and r.json()["pedidos"] == 2


# ------------------------------------------------------------------- a IA
def test_ia_registra_e_avanca_pelas_ferramentas_dos_suits(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "ia.sqlite"))
    con = conectar(); aplicar_schema(con)
    from command_center.api import suits as api_suits
    f = {nome: fn for nome, _, _, _, fn in api_suits.ferramentas_ia()}
    pid = f["suits_criar_pedido"](con, None, customer_name="Enzo", language="pt", medidas={"valores": {"head": 55}})["id"]
    f["suits_atualizar_pedido"](con, None, pid, status="awaiting_measurements", design={"cores": "azul"})
    f["suits_anotar"](con, None, pid, "Pedi o formulário de medidas ao cliente, em português.")
    p = f["suits_pedido"](con, None, pid)
    assert p["source"] == "ia" and p["status"] == "awaiting_measurements" and p["design"] == {"cores": "azul"}
    assert p["email_fornecedor"]["assunto"] == "SUIT - Enzo" and [n["kind"] for n in p["notas"]][-1] == "ia"
    assert f["suits_pedidos"](con, None, busca="enzo")[0]["id"] == pid
    for nome in ("suits_pedidos", "suits_pedido", "suits_leads", "suits_fornecedores"):
        assert agente_sdk.classificar(con, nome) == "ler"
    for nome in ("suits_criar_pedido", "suits_atualizar_pedido", "suits_anotar"):
        assert agente_sdk.classificar(con, nome) == "fazer"                # interno: faz direto e fica registrado
    assert json.loads(um(con, "SELECT measurements FROM suit_orders WHERE id=?", (pid,))["measurements"])["head"]["v"] == 55
    con.close()

"""Balcão com leitor (#87): QR do cliente + código de barras da peça → invoice de peças.

Dono, 05/10: *"o mecânico vai ler o QR Code do cliente e vai ler o código de barras da
peça. E aí já vai subir para aquele cliente, no card daquele cliente, uma invoice aberta de
partes com aquela peça"*. E: nasce no QuickBooks na hora; uma por dia; não é enviada
sozinha; código novo cria o item no QuickBooks com a categoria; peça do cliente vai para o
estoque dele e não cobra — e a diferença tem de ser evidente.

O QuickBooks aqui é falso e anota cada chamada: o teste prova o que seria escrito lá.
"""
import os
import re
from datetime import date

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, um  # noqa: E402
from command_center.providers import balcao, estoque  # noqa: E402

B = "/ops/api/balcao"
SENHA = "senha-forte-123"
HOJE = "2026-10-05"


class QboFalso:
    def __init__(self):
        self.chamadas, self.falhar, self.n = [], None, 0

    def _anota(self, _fn, **kw):
        self.chamadas.append((_fn, kw))
        if self.falhar:
            raise RuntimeError(self.falhar)

    def categorias_sistema(self):
        return [{"id": "c1", "nome": "Parts"}, {"id": "c2", "nome": "Engine parts"}]

    def criar_item_peca_sistema(self, **kw):
        self._anota("criar_item", **kw)
        return {"id": "it-9", "nome": kw["nome"], "nome_completo": f"Parts:{kw['nome']}", "preco": kw["preco"], "tipo": "Service"}

    def invoice_pecas_sistema(self, **kw):
        self._anota("invoice", **kw)
        if kw.get("invoice_id"):
            return {"id": kw["invoice_id"], "numero": "URACE-0101", "anulada": not kw["linhas"]}
        self.n += 1
        return {"id": f"inv-{self.n}", "numero": f"URACE-010{self.n}"}

    def enviar_invoice_sistema(self, invoice_id):
        self._anota("enviar", invoice_id=invoice_id)
        return {"id": invoice_id, "enviado_para": "familia@example.com"}


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    qbo = QboFalso()
    import command_center.providers as prov
    monkeypatch.setattr(prov, "modulo", lambda nome: qbo if nome == "quickbooks" else None)
    monkeypatch.setattr(balcao, "hoje", lambda: HOJE)
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "mec@urace.us", "Mecânico", "OPERATOR", SENHA)
    auth.criar_usuario(con, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    auth.criar_usuario(con, "olho@urace.us", "Visitante", "VIEWER", SENHA)
    leo = inserir(con, "clients", name="Maria Santos", pilot_name="Leo Santos", email="familia@example.com",
                  status="ACTIVE", source="manual")
    # o card já é cliente no QuickBooks: tem invoice anterior com o id dele lá
    inserir(con, "invoices", client_id=leo, doc_number="URACE-0001", amount=10, balance=0, status="paid",
            issued_on="2026-09-01", customer_ref="qbo-cust-7")
    sem_qbo = inserir(con, "clients", name="Sem Quickbooks", status="ACTIVE", source="manual")
    para = estoque.criar_item(con, "peca", "Front bumper Tony Kart", category="hardware", price=89.5)
    estoque.entrada(con, para, qty=5)
    pneu = estoque.criar_item(con, "pneu", "MG Yellow set")      # sem preço final ainda
    con.commit(); con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        c.qbo, c.leo, c.sem_qbo, c.para, c.pneu = qbo, leo, sem_qbo, para, pneu
        yield c


def entra(cli, email="mec@urace.us"):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def prepara_peca(cli, item, codigo="7891234567895"):
    """Gerente cadastra o código da embalagem e cria o item no QuickBooks, na categoria."""
    h = entra(cli, "ger@urace.us")
    r = cli.post(f"{B}/codigos", json={"codigo": codigo, "item_id": item, "qbo_categoria_id": "c1"}, headers=h)
    assert r.status_code == 201 and r.json()["aviso"] is None, r.text
    return codigo


def lanca(cli, h, item, modo="cobrar", **mais):
    return cli.post(f"{B}/lancar", json={"client_id": cli.leo, "item_id": item, "modo": modo, **mais}, headers=h)


# ------------------------------------------------------------------ QR do cliente
def test_cada_card_tem_um_qr_opaco_e_o_leitor_reconhece(cli):
    h = entra(cli)
    svg = cli.get(f"{B}/cliente/{cli.leo}/qr.svg")
    assert svg.status_code == 200 and svg.content.startswith(b"<svg")
    cod = um(conectar(), "SELECT scan_code FROM clients WHERE id=?", (cli.leo,))["scan_code"]
    assert re.fullmatch(r"[A-Z2-9]{10}", cod) and str(cli.leo) not in cod, "código aleatório, nunca o id"
    assert cli.get(f"{B}/cliente/{cli.leo}/qr.svg").status_code == 200
    assert um(conectar(), "SELECT scan_code FROM clients WHERE id=?", (cli.leo,))["scan_code"] == cod, "o QR não muda"
    r = cli.get(f"{B}/ler", params={"codigo": f"https://ops.urace.us/ops/c/{cod}"}, headers=h).json()
    assert r["tipo"] == "cliente" and r["cliente"]["nome"] == "Leo Santos"
    assert cli.get(f"{B}/ler", params={"codigo": "https://ops.urace.us/ops/c/AAAAAAAAAA"}).status_code == 400
    entra(cli, "olho@urace.us")
    assert cli.get(f"{B}/cliente/{cli.leo}/qr.svg").status_code == 403, "visitante não opera o balcão"


# ------------------------------------------------------------------ código da peça
def test_codigo_novo_cadastra_peca_e_o_gerente_cria_o_item_no_quickbooks(cli):
    h = entra(cli)
    assert cli.get(f"{B}/ler", params={"codigo": "0001112223334"}, headers=h).json()["tipo"] == "desconhecido"
    r = cli.post(f"{B}/codigos", json={"codigo": "0001112223334", "nome": "Chain 219 Regina", "category": "hardware"}, headers=h)
    assert r.status_code == 201, r.text
    novo = r.json()["item"]["id"]
    assert cli.get(f"{B}/ler", params={"codigo": "0001112223334"}, headers=h).json()["item"]["name"] == "Chain 219 Regina"
    assert cli.post(f"{B}/codigos", json={"codigo": "999888777", "item_id": novo, "price": 45}, headers=h).status_code == 403, \
        "preço é do gerente"
    assert cli.post(f"{B}/codigos", json={"codigo": "0001112223334", "item_id": cli.para}, headers=h).status_code == 400, \
        "um código, uma peça"
    hg = entra(cli, "ger@urace.us")
    r = cli.post(f"{B}/codigos", json={"codigo": "999888777", "item_id": novo, "price": 45, "qbo_categoria_id": "c1"}, headers=hg)
    assert r.status_code == 201 and r.json()["item"]["qbo_item_name"] == "Parts:Chain 219 Regina", r.text
    nome, kw = cli.qbo.chamadas[-1]
    assert nome == "criar_item" and kw["categoria_id"] == "c1" and kw["preco"] == 45


def test_etiqueta_urace_para_peca_sem_codigo(cli):
    h = entra(cli)
    assert cli.post(f"{B}/itens/{cli.pneu}/codigo-urace", headers=h).json()["codigo"] == f"URC{cli.pneu:06d}"
    pdf = cli.get(f"{B}/itens/{cli.pneu}/etiqueta.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert cli.get(f"{B}/ler", params={"codigo": f"URC{cli.pneu:06d}"}, headers=h).json()["item"]["id"] == cli.pneu


# ------------------------------------------------------------------ cobrar
def test_a_invoice_nasce_no_quickbooks_na_primeira_peca_e_cresce_a_cada_leitura(cli):
    cod = prepara_peca(cli, cli.para)
    h = entra(cli)
    r = lanca(cli, h, cli.para, codigo=cod)
    assert r.status_code == 201, r.text
    nome, kw = cli.qbo.chamadas[-1]
    assert nome == "invoice" and kw["invoice_id"] is None and kw["cliente_id"] == "qbo-cust-7" and kw["data"] == HOJE
    assert kw["memo"] == "Parts invoice — parts used | Leo Santos | Service date: 10/05/2026"
    assert kw["linhas"] == [{"item_id": "it-9", "quantidade": 1.0, "unitario": 89.5, "descricao": "Front bumper Tony Kart"}]
    inv = r.json()["invoices"][0]
    assert inv["status"] == "aberta" and inv["qbo_invoice_id"] == "inv-1" and inv["total"] == 89.5 and not inv["qbo_error"]
    # a segunda peça vai para a MESMA invoice, que é reescrita inteira
    r = lanca(cli, h, cli.para, qty=2)
    nome, kw = cli.qbo.chamadas[-1]
    assert kw["invoice_id"] == "inv-1" and [x["quantidade"] for x in kw["linhas"]] == [1.0, 2.0]
    assert r.json()["invoices"][0]["total"] == 268.5
    assert estoque.saldo(conectar(), cli.para, client_id=None) == 2, "saiu do estoque da URACE"
    assert not any(n == "enviar" for n, _ in cli.qbo.chamadas), "não é enviada sozinha"


def test_outro_dia_e_outra_invoice(cli, monkeypatch):
    prepara_peca(cli, cli.para)
    h = entra(cli)
    lanca(cli, h, cli.para)
    monkeypatch.setattr(balcao, "hoje", lambda: "2026-10-06")
    lanca(cli, h, cli.para)
    criadas = [kw for n, kw in cli.qbo.chamadas if n == "invoice" and not kw["invoice_id"]]
    assert [kw["data"] for kw in criadas] == [HOJE, "2026-10-06"]
    assert "Service date: 10/06/2026" in criadas[1]["memo"]


def test_sem_preco_sem_item_ou_sem_cliente_no_quickbooks_nao_cobra(cli):
    h = entra(cli)
    r = lanca(cli, h, cli.pneu)
    assert r.status_code == 400 and "preço final" in r.json()["detail"]
    r = lanca(cli, h, cli.para)
    assert r.status_code == 409 and r.json()["detail"]["motivo"] == "precisa_item_qbo"
    prepara_peca(cli, cli.para)
    h = entra(cli)
    r = cli.post(f"{B}/lancar", json={"client_id": cli.sem_qbo, "item_id": cli.para, "modo": "cobrar"}, headers=h)
    assert r.status_code == 400 and "QuickBooks" in r.json()["detail"]
    assert estoque.saldo(conectar(), cli.para, client_id=None) == 5, "recusado não mexe no estoque"


def test_peca_sem_saldo_da_urace_nao_cobra(cli):
    prepara_peca(cli, cli.para)
    h = entra(cli)
    r = lanca(cli, h, cli.para, qty=9)
    assert r.status_code == 400 and "tem 5" in r.json()["detail"]
    assert not um(conectar(), "SELECT 1 AS x FROM parts_invoices"), "nada pela metade"


# ------------------------------------------------------------------ guardar × cobrar
def test_peca_do_cliente_vai_para_o_estoque_dele_e_cobrar_pede_confirmacao(cli):
    prepara_peca(cli, cli.para)
    h = entra(cli)
    assert lanca(cli, h, cli.para, modo="guardar", qty=2).status_code == 201
    con = conectar()
    assert estoque.saldo(con, cli.para, client_id=cli.leo) == 2
    assert not [n for n, _ in cli.qbo.chamadas if n == "invoice"], "guardar não cobra"
    r = lanca(cli, h, cli.para)
    assert r.status_code == 409 and r.json()["detail"]["motivo"] == "tem_do_cliente"
    assert "guardado" in r.json()["detail"]["mensagem"]
    assert lanca(cli, h, cli.para, modo="usar_do_cliente").status_code == 201
    assert estoque.saldo(conectar(), cli.para, client_id=cli.leo) == 1
    assert not [n for n, _ in cli.qbo.chamadas if n == "invoice"], "usar a peça dele não cobra"
    assert lanca(cli, h, cli.para, confirmado=True).status_code == 201, "cobrar uma nova, confirmado"


# ------------------------------------------------------------------ desfazer, falha e envio
def test_desfazer_devolve_ao_estoque_e_tira_da_invoice(cli):
    prepara_peca(cli, cli.para)
    h = entra(cli)
    s1 = lanca(cli, h, cli.para).json()["leitura"]["id"]
    s2 = lanca(cli, h, cli.para).json()["leitura"]["id"]
    r = cli.post(f"{B}/leituras/{s2}/desfazer", headers=h)
    assert r.status_code == 200 and r.json()["invoices"][0]["total"] == 89.5
    assert len(cli.qbo.chamadas[-1][1]["linhas"]) == 1
    assert cli.post(f"{B}/leituras/{s2}/desfazer", headers=h).status_code == 400, "não desfaz duas vezes"
    cli.post(f"{B}/leituras/{s1}/desfazer", headers=h)
    assert cli.qbo.chamadas[-1][1]["linhas"] == [], "sem linha: a invoice é anulada no QuickBooks"
    assert um(conectar(), "SELECT status FROM parts_invoices")["status"] == "anulada"
    assert estoque.saldo(conectar(), cli.para, client_id=None) == 5


def test_quickbooks_fora_do_ar_nao_perde_a_leitura(cli):
    prepara_peca(cli, cli.para)
    h = entra(cli)
    cli.qbo.falhar = "HTTP 503 em POST /invoice"
    r = lanca(cli, h, cli.para)
    assert r.status_code == 201
    inv = r.json()["invoices"][0]
    assert "503" in inv["qbo_error"] and not inv["qbo_invoice_id"]
    assert estoque.saldo(conectar(), cli.para, client_id=None) == 4, "a leitura ficou salva"
    hg = entra(cli, "ger@urace.us")
    assert cli.post(f"{B}/invoices/{inv['id']}/enviar", headers=hg).status_code == 400, "não envia o que não subiu"
    cli.qbo.falhar = None
    r = cli.post(f"{B}/invoices/{inv['id']}/sincronizar", headers=hg)
    assert r.json()["qbo_invoice_id"] == "inv-1" and not r.json()["qbo_error"]


def test_so_o_gerente_envia_e_depois_de_enviada_a_peca_vai_para_outra(cli):
    prepara_peca(cli, cli.para)
    h = entra(cli)
    s = lanca(cli, h, cli.para).json()
    pid = s["invoices"][0]["id"]
    assert cli.get(f"{B}/invoices", headers=h).json()["total"] == 1
    assert cli.post(f"{B}/invoices/{pid}/enviar", headers=h).status_code == 403
    hg = entra(cli, "ger@urace.us")
    r = cli.post(f"{B}/invoices/{pid}/enviar", headers=hg)
    assert r.status_code == 200 and r.json()["status"] == "enviada" and r.json()["sent_to"] == "familia@example.com"
    assert cli.qbo.chamadas[-1] == ("enviar", {"invoice_id": "inv-1"})
    h = entra(cli)
    assert cli.post(f"{B}/leituras/{s['leitura']['id']}/desfazer", headers=h).status_code == 400
    r = lanca(cli, h, cli.para)
    assert [i["qbo_invoice_id"] for i in r.json()["invoices"] if i["status"] == "aberta"] == ["inv-2"]
    assert date.fromisoformat(HOJE)


# ------------------------------------------------------------------ o que vai para o QuickBooks de verdade
@pytest.fixture
def qb(monkeypatch, tmp_path):
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "adminai", "mcp"))
    import quickbooks_mcp as q
    monkeypatch.setenv("QBO_REALM_ID", "1")
    monkeypatch.setenv("QBO_TOKEN_JSON", str(tmp_path / "t.json"))
    q.gravar_token({"refresh_token": "r", "realm_id": "1"})
    feito, respostas = [], {}

    def _req(caminho, metodo="GET", corpo=None, params=None):
        feito.append((caminho, metodo, corpo, params))
        return respostas.get((caminho, metodo), {"Invoice": {"Id": "55", "DocNumber": "URACE-0200", "TotalAmt": 10}})
    monkeypatch.setattr(q, "_req", _req)
    monkeypatch.setattr(q, "_conta_receita", lambda: {"value": "79", "name": "Sales"})
    monkeypatch.setattr(q, "_proximo_doc_number", lambda: "URACE-0200")
    return q, feito, respostas


LINHA_QBO = [{"item_id": "it-9", "quantidade": 2, "unitario": 89.5, "descricao": "Front bumper Tony Kart"}]


def test_invoice_nova_tem_data_numero_memo_e_nao_e_enviada(qb):
    q, feito, _ = qb
    q.invoice_pecas_sistema(cliente_id="7", linhas=LINHA_QBO, memo="Parts invoice — parts used", data="2026-10-05")
    caminho, metodo, corpo, _ = feito[-1]
    assert (caminho, metodo) == ("/invoice", "POST")
    assert corpo["TxnDate"] == corpo["DueDate"] == "2026-10-05" and corpo["DocNumber"] == "URACE-0200"
    assert corpo["Line"][0]["Amount"] == 179.0 and corpo["Line"][0]["SalesItemLineDetail"]["UnitPrice"] == 89.5
    assert corpo["CustomerMemo"]["value"] == corpo["PrivateNote"] == "Parts invoice — parts used"
    assert not any("/send" in c for c, *_ in feito), "criar não envia"


def test_invoice_existente_e_reescrita_inteira_e_enviada_nao_muda(qb):
    q, feito, respostas = qb
    respostas[("/invoice/55", "GET")] = {"Invoice": {"Id": "55", "SyncToken": "3", "DocNumber": "URACE-0200"}}
    q.invoice_pecas_sistema(cliente_id="7", linhas=LINHA_QBO, memo="m", data="2026-10-05", invoice_id="55")
    corpo = feito[-1][2]
    assert corpo["Id"] == "55" and corpo["SyncToken"] == "3" and corpo["sparse"] is True and len(corpo["Line"]) == 1
    q.invoice_pecas_sistema(cliente_id="7", linhas=[], memo="m", data="2026-10-05", invoice_id="55")
    assert feito[-1][3] == {"operation": "void"}, "sem linha: void, nunca delete"
    respostas[("/invoice/55", "GET")] = {"Invoice": {"Id": "55", "SyncToken": "4", "DocNumber": "URACE-0200", "EmailStatus": "EmailSent"}}
    with pytest.raises(Exception, match="já foi enviada"):
        q.invoice_pecas_sistema(cliente_id="7", linhas=LINHA_QBO, memo="m", data="2026-10-05", invoice_id="55")


def test_item_da_peca_entra_na_categoria_e_nao_duplica(qb):
    q, feito, respostas = qb
    respostas[("/query", "GET")] = {"QueryResponse": {}}
    respostas[("/item", "POST")] = {"Item": {"Id": "90", "Name": "Front bumper", "FullyQualifiedName": "Parts:Front bumper"}}
    r = q.criar_item_peca_sistema(nome="Front bumper", preco=89.5, categoria_id="c1", sku="TK-1")
    corpo = feito[-1][2]
    assert corpo["SubItem"] is True and corpo["ParentRef"] == {"value": "c1"} and corpo["Sku"] == "TK-1"
    assert corpo["UnitPrice"] == 89.5 and r["nome_completo"] == "Parts:Front bumper"
    respostas[("/query", "GET")] = {"QueryResponse": {"Item": [{"Id": "90", "Name": "Front bumper", "ParentRef": {"value": "c1"}}]}}
    n = len(feito)
    assert q.criar_item_peca_sistema(nome="Front bumper", preco=89.5, categoria_id="c1")["id"] == "90"
    assert [c for c, m, *_ in feito[n:] if m == "POST"] == [], "já existe na categoria: não cria outro"
    with pytest.raises(Exception, match="':'"):
        q.criar_item_peca_sistema(nome="Parts:Front", preco=1)


def test_o_cliente_ve_o_qr_do_proprio_piloto_so_depois_de_ligado_ao_card(cli):
    from command_center.tests.dados_portal import piloto
    cli.cookies.clear()
    conta = {"name": "Maria Santos", "email": "maria@example.com", "password": "corrida-segura-9", "birth_date": "1985-04-12",
             "phone": "(407) 555-0142", "address_line1": "100 Main St", "city": "Orlando", "state": "FL", "zip": "32809",
             "accept_terms": True}
    assert cli.post("/ops/api/portal/signup", json=conta).status_code == 201
    hc = {"X-CSRF": cli.cookies.get("cp_csrf")}
    r = cli.post("/ops/api/portal/drivers", json=piloto("Leo Santos", birth_date="2014-05-01"), headers=hc)
    pid = next(d["id"] for d in r.json()["drivers"] if d["name"] == "Leo Santos")
    assert cli.get(f"/ops/api/portal/drivers/{pid}/qr.svg").status_code == 404, "sem card ainda, sem QR"
    con = conectar(); con.execute("UPDATE portal_pilots SET client_id=? WHERE id=?", (cli.leo, pid)); con.commit()
    r = cli.get(f"/ops/api/portal/drivers/{pid}/qr.svg")
    assert r.status_code == 200 and r.content.startswith(b"<svg")
    assert cli.get(f"/ops/api/portal/drivers/{pid + 99}/qr.svg").status_code == 404


def test_invoice_aberta_aparece_em_precisa_de_atencao_ate_ser_enviada(cli):
    prepara_peca(cli, cli.para)
    h = entra(cli)
    pid = lanca(cli, h, cli.para).json()["invoices"][0]["id"]
    hg = entra(cli, "ger@urace.us")

    def pendencia():
        return [a for a in cli.get("/ops/api/needs-attention").json() if a["entity"]["type"] == "parts_invoice"]
    a = pendencia()
    assert a and a[0]["title"] == "1 invoice(s) de peças para enviar" and "Leo Santos" in a[0]["facts"][0][0]
    cli.post(f"{B}/invoices/{pid}/enviar", headers=hg)
    assert not pendencia()

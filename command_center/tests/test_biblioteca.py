"""Biblioteca (#88): os documentos de cada cliente juntos, e o espelho no Drive.

Dono, 05/10: todas as invoices (o PDF que o QuickBooks imprime), os recibos de pagamento do
QuickBooks, contratos, waivers e histórico de serviço; atualizada todo dia por rotina, sem IA;
gerente para cima; no Drive, pasta "Command Center" por cliente, compartilhada com o Eduardo.

O que estes testes trancam: o documento só entra no card certo (na dúvida, "Sem cliente");
só se baixa de novo o que mudou; uma origem fora do ar não derruba as outras; o Drive recebe
a estrutura combinada e o arquivo que muda é SUBSTITUÍDO (nada é apagado).
"""
import os

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, todos, um  # noqa: E402
from command_center.providers import NaoConectado, biblioteca as bib  # noqa: E402

SENHA = "senha-forte-123"
PDF = b"%PDF-1.4 teste"


class QboFalso:
    def __init__(self):
        self.pdfs, self.desde = [], []
        self.docs = {"invoice": [
            {"id": "100", "numero": "1031", "data": "2026-09-01", "total": 500, "saldo": 0, "cliente_id": "c1",
             "atualizado_em": "2026-09-02T10:00:00Z", "versao": "0", "email_status": "EmailSent"},
            {"id": "200", "numero": "0901", "data": "2024-03-10", "total": 300, "saldo": 300, "cliente_id": "c1",
             "atualizado_em": "2024-03-10T10:00:00Z", "versao": "0"},
            {"id": "300", "numero": "1077", "data": "2026-07-01", "total": 819, "saldo": 819, "cliente_id": "c9",
             "atualizado_em": "2026-07-01T10:00:00Z", "versao": "1"}],
            "payment": [{"id": "P1", "numero": "ZELLE-77", "data": "2026-09-03", "total": 500, "cliente_id": "c1",
                         "atualizado_em": "2026-09-03T10:00:00Z", "versao": "0", "invoices": ["100"], "metodo": "Zelle"}]}

    def documentos_sistema(self, tipo, desde=None):
        self.desde.append((tipo, desde))
        return [dict(d) for d in self.docs[tipo]]

    def pdf_sistema(self, tipo, id):
        self.pdfs.append((tipo, id))
        if tipo == "payment":
            raise RuntimeError("HTTP 400 ao baixar o PDF de payment")
        return PDF + id.encode()


class DriveFalso:
    def __init__(self):
        self.pastas, self.arquivos, self.compartilhado, self.n = {}, {}, [], 0

    def token(self):
        return "tok"

    def pasta(self, tok, nome, pai=None):
        chave = (pai, nome)
        if chave not in self.pastas:
            self.n += 1
            self.pastas[chave] = f"p{self.n}"
        return self.pastas[chave]

    def enviar(self, tok, nome, dados, pai, file_id=None):
        if file_id:
            assert file_id in self.arquivos, "substitui o mesmo arquivo"
            self.arquivos[file_id].update(nome=nome, dados=dados, versoes=self.arquivos[file_id]["versoes"] + 1)
            return file_id
        self.n += 1
        fid = f"f{self.n}"
        self.arquivos[fid] = {"nome": nome, "dados": dados, "pai": pai, "versoes": 1}
        return fid

    def compartilhar(self, tok, fid, email, papel="reader"):
        self.compartilhado.append((fid, email, papel))

    def caminho(self, pai):
        nomes = {v: k for k, v in self.pastas.items()}
        partes = []
        while pai:
            p, nome = nomes[pai]
            partes.insert(0, nome)
            pai = p
        return "/".join(partes)


@pytest.fixture()
def amb(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    auth.criar_usuario(con, "op@urace.us", "Operador", "OPERATOR", SENHA)
    a = inserir(con, "clients", name="Nicolas Pera", pilot_name="David Pera", status="ACTIVE", source="manual")
    b = inserir(con, "clients", name="Carla Mendes", pilot_name="Théo Mendes", status="ACTIVE", source="manual")
    c = inserir(con, "clients", name="Carla Mendes", pilot_name="Lia Mendes", status="ACTIVE", source="manual")
    i = inserir(con, "invoices", client_id=a, doc_number="1031", amount=500, balance=0, status="paid", issued_on="2026-09-01", customer_ref="c1")
    inserir(con, "entity_links", entity_type="invoice", entity_id=i, system="quickbooks", external_id="100")
    # família: o mesmo cliente do QuickBooks em dois cards (dois pilotos)
    inserir(con, "invoices", client_id=b, doc_number="1050", amount=1, balance=0, status="paid", issued_on="2026-08-01", customer_ref="c9")
    inserir(con, "invoices", client_id=c, doc_number="1051", amount=1, balance=0, status="paid", issued_on="2026-08-02", customer_ref="c9")
    w = tmp_path / "waiver.pdf"; w.write_bytes(b"%PDF waiver")
    inserir(con, "waivers", client_id=a, signer_name="Nicolas Pera", status="completed", completed_at="2026-08-30T12:00:00Z", pdf_path=str(w))
    k = tmp_path / "contrato.pdf"; k.write_bytes(b"%PDF contrato")
    inserir(con, "contracts", client_id=a, source="upload", status="completed", file_path=str(k), title="Academy 12 meses", signed_at="2026-08-01")
    inserir(con, "tasks", client_id=a, title="David Pera_Urace Daily_Using Own Kart [1/1]", status="completed", due_on="2026-09-01")
    con.commit()
    yield con, {"a": a, "b": b, "c": c}
    con.close()


def test_cada_documento_no_card_certo_e_na_duvida_sem_cliente(amb):
    con, ids = amb
    r = bib.rodada(con, qbo=QboFalso(), drive=DriveFalso(), log=lambda *_: None)
    assert r["qbo"]["invoice"] == 3 and r["qbo"]["recibo"] == 1
    doc = {(d["kind"], d["ref"]): d for d in todos(con, "SELECT * FROM library_docs")}
    assert doc[("invoice", "100")]["client_id"] == ids["a"], "a invoice já ligada pela sincronia"
    assert doc[("invoice", "200")]["client_id"] == ids["a"], "invoice antiga: cliente do QuickBooks com um card só"
    assert doc[("invoice", "300")]["client_id"] is None, "família com dois cards: não chuta"
    assert doc[("recibo", "P1")]["client_id"] == ids["a"], "o recibo segue a invoice que ele pagou"
    assert doc[("invoice", "100")]["status"] == "paga"
    for kind in ("waiver", "contrato", "historico"):
        assert any(k == kind for k, _ in doc), kind
    assert open(doc[("invoice", "100")]["file_path"], "rb").read() == PDF + b"100", "o PDF do próprio QuickBooks"


def test_recibo_sem_pdf_do_quickbooks_vira_comprovante_com_os_dados_dele(amb):
    con, _ = amb
    bib.rodada(con, qbo=QboFalso(), usar_drive=False, log=lambda *_: None)
    from pypdf import PdfReader
    d = um(con, "SELECT * FROM library_docs WHERE kind='recibo'")
    texto = PdfReader(d["file_path"]).pages[0].extract_text()
    assert "Payment receipt" in texto and "500.00" in texto and "Zelle" in texto and "QuickBooks payment record" in texto


def test_so_baixa_de_novo_o_que_mudou_e_o_drive_substitui_o_mesmo_arquivo(amb):
    con, _ = amb
    qbo, drive = QboFalso(), DriveFalso()
    bib.rodada(con, qbo=qbo, drive=drive, log=lambda *_: None)
    antes = len(qbo.pdfs)
    bib.rodada(con, qbo=qbo, drive=drive, log=lambda *_: None)
    assert len(qbo.pdfs) == antes, "nada mudou: nenhum PDF baixado de novo"
    assert qbo.desde[-1][1], "a segunda rodada pede só o que mudou desde a primeira"
    qbo.docs["invoice"][0].update(atualizado_em="2026-10-05T10:00:00Z", versao="1")
    bib.rodada(con, qbo=qbo, drive=drive, log=lambda *_: None)
    assert qbo.pdfs[-1] == ("invoice", "100")
    fid = um(con, "SELECT drive_file_id FROM library_docs WHERE kind='invoice' AND ref='100'")["drive_file_id"]
    assert drive.arquivos[fid]["versoes"] == 1, "mesmo PDF (bytes iguais): não sobe de novo"


def test_drive_por_cliente_e_compartilhado_com_o_eduardo(amb):
    con, ids = amb
    drive = DriveFalso()
    bib.rodada(con, qbo=QboFalso(), drive=drive, log=lambda *_: None)
    caminhos = {drive.caminho(a["pai"]) + "/" + a["nome"] for a in drive.arquivos.values()}
    assert f"Command Center/Clientes/David Pera #{ids['a']}/Invoices/2026-09-01 Invoice 1031.pdf" in caminhos
    assert any(c.startswith("Command Center/Clientes/Sem cliente/Invoices/") for c in caminhos)
    assert any("/Waivers/" in c for c in caminhos) and any("/Recibos/" in c for c in caminhos)
    assert any("/Histórico de serviço/" in c for c in caminhos) and any("/Contratos/" in c for c in caminhos)
    clientes = drive.pastas[(drive.pastas[(None, "Command Center")], "Clientes")]
    assert drive.compartilhado == [(clientes, "eduardo@urace.us", "reader")], \
        "só Clientes: o backup do banco, na raiz, continua privado"
    bib.rodada(con, qbo=QboFalso(), drive=drive, log=lambda *_: None)
    assert len(drive.compartilhado) == 1, "compartilha uma vez só"


def test_quickbooks_fora_do_ar_nao_derruba_o_resto(amb):
    con, _ = amb

    class Fora:
        def documentos_sistema(self, *a, **k):
            raise NaoConectado("quickbooks")
    r = bib.rodada(con, qbo=Fora(), drive=DriveFalso(), log=lambda *_: None)
    assert "não conectado" in r["qbo"]["erro"]
    assert r["documentos"]["waiver"] == 1 and r["drive"]["drive"] >= 3


# ------------------------------------------------------------------ a tela
def test_biblioteca_e_de_gerente_para_cima(amb, monkeypatch):
    con, ids = amb
    bib.rodada(con, qbo=QboFalso(), usar_drive=False, log=lambda *_: None)
    with TestClient(app, base_url="https://cc.test") as cli:
        assert cli.post("/ops/api/auth/login", json={"email": "op@urace.us", "password": SENHA}).status_code == 200
        assert cli.get("/ops/api/biblioteca").status_code == 403, "operador não entra na Biblioteca"
        cli.cookies.clear()
        assert cli.post("/ops/api/auth/login", json={"email": "ger@urace.us", "password": SENHA}).status_code == 200
        r = cli.get("/ops/api/biblioteca", params={"tipo": "invoice", "limit": 2}).json()
        assert r["total"] == 3 and len(r["itens"]) == 2
        assert cli.get("/ops/api/biblioteca", params={"tipo": "invoice", "client_id": ids["a"]}).json()["total"] == 2
        assert cli.get("/ops/api/biblioteca", params={"q": "1077"}).json()["itens"][0]["cliente"] is None
        did = r["itens"][0]["id"]
        p = cli.get(f"/ops/api/biblioteca/{did}/pdf")
        assert p.status_code == 200 and p.content.startswith(b"%PDF")
        res = cli.get("/ops/api/biblioteca/resumo").json()
        assert res["contagem"]["invoice"] == 3 and res["sem_cliente"] == 1
        assert cli.get("/ops/api/biblioteca", params={"tipo": "xyz"}).status_code == 400


def test_todas_as_invoices_paginadas_e_so_o_que_mudou(monkeypatch, tmp_path):
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "adminai", "mcp"))
    import quickbooks_mcp as q
    feitas = []

    def _query(sql):
        feitas.append(sql)
        n = 1000 if "startposition 1 " in sql else 3
        return {"Invoice": [{"Id": str(i), "DocNumber": str(i), "MetaData": {"LastUpdatedTime": "2026-10-01T00:00:00Z"},
                             "CustomerRef": {"value": "7"}} for i in range(n)]}
    monkeypatch.setattr(q, "_query", _query)
    docs = q.documentos_sistema("invoice")
    assert len(docs) == 1003 and "startposition 1001" in feitas[1], "passa de 1000: busca a próxima página"
    assert "where" not in feitas[0].lower(), "primeira vez: todas, sem limite de data"
    q.documentos_sistema("invoice", desde="2026-10-05T03:40:00Z")
    assert "MetaData.LastUpdatedTime >= '2026-10-05T03:40:00Z'" in feitas[-1]
    assert docs[0]["atualizado_em"] == "2026-10-01T00:00:00Z" and docs[0]["cliente_id"] == "7"

"""QuickBooks: MCP próprio com HTTP falso, consentimento pelo painel, espelho de invoices."""
import json
import os
import sys
import tempfile

import pytest

os.environ["URACE_ENV"] = "/nao/existe"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "adminai", "mcp"))

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar  # noqa: E402

B = "/ops/api"
SENHA = "senha-forte-123"


@pytest.fixture(scope="module")
def cli():
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc-qbo.sqlite")
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "admin@urace.us", "Admin", "ADMIN", SENHA)
    auth.criar_usuario(con, "op@urace.us", "Op", "OPERATOR", SENHA)
    con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def entra(cli, email):
    r = cli.post(B + "/auth/login", json={"email": email, "password": SENHA})
    assert r.status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


@pytest.fixture
def qbo(monkeypatch, tmp_path):
    import quickbooks_mcp as q
    monkeypatch.setenv("QBO_CLIENT_ID", "cid"); monkeypatch.setenv("QBO_CLIENT_SECRET", "sec"); monkeypatch.setenv("QBO_REALM_ID", "9341453113046421")
    monkeypatch.setenv("QBO_TOKEN_JSON", str(tmp_path / "qbo-token.json"))
    q.gravar_token({"refresh_token": "r1", "realm_id": "9341453113046421"})
    chamadas = []
    respostas = {}

    def _token_post(campos):
        chamadas.append(("token", campos))
        return {"access_token": "a1", "refresh_token": "r2", "expires_in": 3600}

    def _req(caminho, metodo="GET", corpo=None, params=None):
        chamadas.append((metodo, caminho, corpo, params))
        for k, v in respostas.items():
            if k in caminho or (params and k in (params.get("query") or "")):
                return v
        return {}
    monkeypatch.setattr(q, "_token_post", _token_post)
    monkeypatch.setattr(q, "_req", _req)
    q._cache.update(access=None, expira=0)
    return q, chamadas, respostas


def test_refresh_rotaciona_e_persiste(qbo):
    q, chamadas, _ = qbo
    q._access_token()
    assert json.load(open(q._token_path()))["refresh_token"] == "r2"          # rotacionou e gravou
    assert oct(os.stat(q._token_path()).st_mode)[-3:] == "600"


def test_invoices_status_e_deeplink(qbo):
    q, _, respostas = qbo
    from datetime import date, timedelta
    ontem = (date.today() - timedelta(days=1)).isoformat(); amanha = (date.today() + timedelta(days=1)).isoformat()
    respostas["Invoice"] = {"QueryResponse": {"Invoice": [
        {"Id": "101", "DocNumber": "6YZRN1QWN647NQ", "CustomerRef": {"value": "7", "name": "Alex Alonzo"}, "TotalAmt": 350.0, "Balance": 350.0, "DueDate": ontem, "TxnDate": "2026-08-01",
         "BillEmail": {"Address": "alex@example.com"}, "Line": [{"DetailType": "SalesItemLineDetail", "Amount": 350.0, "SalesItemLineDetail": {"ItemRef": {"name": "Summer Camp"}, "Qty": 1, "UnitPrice": 350.0}}]},
        {"Id": "102", "DocNumber": "X", "CustomerRef": {"value": "8", "name": "Outro"}, "TotalAmt": 100.0, "Balance": 0, "DueDate": amanha, "TxnDate": "2026-08-02"},
        {"Id": "103", "DocNumber": "Y", "CustomerRef": {"value": "9", "name": "Terceiro"}, "TotalAmt": 100.0, "Balance": 100.0, "DueDate": amanha, "TxnDate": "2026-08-03", "EmailStatus": "EmailSent"}]}}
    r = q.qbo_invoices(status="all")
    st = {i["numero"]: i["status"] for i in r["invoices"]}
    assert st == {"6YZRN1QWN647NQ": "overdue", "X": "paid", "Y": "sent"}
    assert r["invoices"][0]["link"] == "https://qbo.intuit.com/app/login?pagereq=invoice%3FtxnId%3D101&deeplinkcompanyid=9341453113046421"
    assert [i["numero"] for i in q.qbo_invoices(status="overdue")["invoices"]] == ["6YZRN1QWN647NQ"]


def test_regras_de_escrita(qbo):
    q, chamadas, respostas = qbo
    from mcp_stdio import ErroFerramenta
    with pytest.raises(ErroFerramenta):
        q.qbo_criar_item("Parts IAME:X", 10)                                  # dois-pontos
    with pytest.raises(ErroFerramenta):
        q.qbo_criar_invoice("7", [{"unitario": 10}])                          # linha sem item
    os.environ["APLICAR"] = "0"
    r = q.qbo_criar_invoice("7", [{"item_id": "1", "quantidade": 2, "unitario": 21.25}])
    assert r["aplicado"] is False and "42.50" in r["teria_feito"]           # unitário × quantidade
    respostas["/invoice/5"] = {"Invoice": {"Id": "5", "DocNumber": "N5", "TotalAmt": 10, "BillEmail": {"Address": "x@y.com"}}}
    r = q.qbo_enviar_invoice("5")
    assert r["aplicado"] is False and "x@y.com" in r["teria_feito"]          # APLICAR=0 nunca envia
    os.environ.pop("APLICAR", None)


def test_connect_exige_admin_e_chaves(cli, monkeypatch):
    h = entra(cli, "op@urace.us")
    assert cli.get(B + "/qbo/connect", headers=h, follow_redirects=False).status_code == 403
    entra(cli, "admin@urace.us")
    monkeypatch.delenv("QBO_CLIENT_ID", raising=False); monkeypatch.delenv("QBO_CLIENT_SECRET", raising=False)
    assert cli.get(B + "/qbo/connect", follow_redirects=False).status_code == 409
    monkeypatch.setenv("QBO_CLIENT_ID", "cid"); monkeypatch.setenv("QBO_CLIENT_SECRET", "sec")
    r = cli.get(B + "/qbo/connect", follow_redirects=False)
    assert r.status_code == 302 and "appcenter.intuit.com" in r.headers["location"] and "state=" in r.headers["location"]
    assert "redirect_uri=https%3A%2F%2Fcc.test%2Fops%2Fapi%2Fqbo%2Fcallback" in r.headers["location"]
    # callback sem state válido: 400; com state válido troca o código e grava o token
    assert cli.get(B + "/qbo/callback?code=x&state=nada&realmId=1", follow_redirects=False).status_code == 400
    state = r.headers["location"].split("state=")[1].split("&")[0]
    import quickbooks_mcp as q
    tmp = tempfile.mkdtemp(); monkeypatch.setenv("QBO_TOKEN_JSON", os.path.join(tmp, "t.json"))
    monkeypatch.setattr(q, "_token_post", lambda campos: {"access_token": "a", "refresh_token": "r", "expires_in": 3600})
    r2 = cli.get(B + f"/qbo/callback?code=abc&state={state}&realmId=9341453113046421", follow_redirects=False)
    assert r2.status_code == 302 and r2.headers["location"].endswith("/ops/quickbooks?connected=1")
    assert json.load(open(os.path.join(tmp, "t.json")))["realm_id"] == "9341453113046421"
    assert [i for i in cli.get(B + "/integrations").json() if i["system"] == "quickbooks"][0]["status"] == "CONNECTED"
    assert cli.get(B + f"/qbo/callback?code=abc&state={state}&realmId=1", follow_redirects=False).status_code == 400   # state não reusa


def test_invoices_e_summary_sao_financeiro(cli):
    entra(cli, "op@urace.us")
    assert cli.get(B + "/invoices").status_code == 403 and cli.get(B + "/qbo/summary").status_code == 403
    entra(cli, "admin@urace.us")
    s = cli.get(B + "/qbo/summary").json()
    assert "open" in s and "overdue" in s and isinstance(s["top_debtors"], list)
    assert cli.get(B + "/invoices").status_code == 200


def test_invoice_sempre_com_numero(monkeypatch):
    """Conta com numeração personalizada: a API não numera; o painel manda o próximo número."""
    import importlib, sys
    sys.path.insert(0, "adminai/mcp")
    qb = importlib.import_module("quickbooks_mcp")
    monkeypatch.setattr(qb, "_query", lambda sql: {"Invoice": [{"DocNumber": "1041"}, {"DocNumber": "1039"}, {"DocNumber": "ABC"}, {"DocNumber": None}]} if "DocNumber" in sql else {})
    assert qb._proximo_doc_number() == "1042"
    monkeypatch.setattr(qb, "_query", lambda sql: {"Invoice": [{"DocNumber": "INV-0099"}]})
    assert qb._proximo_doc_number() == "INV-0100"
    monkeypatch.setattr(qb, "_query", lambda sql: {"Invoice": []})
    assert qb._proximo_doc_number().endswith("01") and len(qb._proximo_doc_number()) == 10
    enviados = []
    monkeypatch.setattr(qb, "_query", lambda sql: {"Invoice": [{"DocNumber": "1041"}]})
    monkeypatch.setattr(qb, "_aplicar", lambda: True)
    monkeypatch.setattr(qb, "_realm", lambda: "9341453113046421")
    monkeypatch.setattr(qb, "_req", lambda caminho, metodo="GET", corpo=None, params=None: (enviados.append((caminho, corpo)) or {"Invoice": {"Id": "9", "DocNumber": corpo["DocNumber"], "TotalAmt": 500, "Balance": 500, "Line": []}}))
    r = qb.qbo_criar_invoice("696", [{"item_id": "31", "quantidade": 1, "unitario": 500, "descricao": "x"}], vence_em="2026-09-11", memo="m")
    assert enviados[0][1]["DocNumber"] == "1042" and enviados[0][1]["PrivateNote"] == "m" and r["numero"] == "1042"

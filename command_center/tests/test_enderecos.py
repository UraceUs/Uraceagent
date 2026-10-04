"""Todos os endereços em urace.us (#79).

Dono, 04/10: *"somente as urls dos paineis de logins ficaram com a url nova preciso que todas
tenham a url urace.us"*. O que o painel mostra e manda colar nos outros sistemas é
`ops.urace.us`; o duckdns antigo continua respondendo, cada um com o próprio nome, para nada
cair enquanto Kommo, Dialpad, Intuit e os conectores já ligados não são trocados."""
import os
import tempfile

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar  # noqa: E402

SENHA = "senha-forte-123"


@pytest.fixture(scope="module")
def cli():
    pasta = tempfile.mkdtemp()
    os.environ["CC_DB_PATH"] = os.path.join(pasta, "cc.sqlite")
    os.environ["URACE_DIR"] = pasta
    os.environ.pop("CC_PUBLIC_URL", None)
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "dono@urace.us", "Italo", "ADMIN", SENHA)
    con.commit(); con.close()
    with TestClient(app, base_url="https://urace-bridge.duckdns.org", follow_redirects=False) as c:
        yield c


def entra(cli, host):
    cli.cookies.clear()
    r = cli.post("/ops/api/auth/login", json={"email": "dono@urace.us", "password": SENHA}, headers={"Host": host})
    assert r.status_code == 200, r.text


def test_o_login_do_mcp_nasce_em_urace_us(cli):
    m = cli.get("/.well-known/oauth-authorization-server", headers={"Host": "ops.urace.us"}).json()
    assert m["issuer"] == "https://ops.urace.us"
    assert m["token_endpoint"] == "https://ops.urace.us/ops/oauth/token"
    rec = cli.get("/.well-known/oauth-protected-resource", headers={"Host": "ops.urace.us"}).json()
    assert rec == {**rec, "resource": "https://ops.urace.us/ops/mcp", "authorization_servers": ["https://ops.urace.us"]}


def test_quem_ja_esta_ligado_no_antigo_continua_com_o_antigo(cli):
    """O emissor tem de ser o endereço de onde o cliente leu os metadados (RFC 8414)."""
    m = cli.get("/.well-known/oauth-authorization-server", headers={"Host": "urace-bridge.duckdns.org"}).json()
    assert m["issuer"] == "https://urace-bridge.duckdns.org"
    r = cli.post("/ops/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                 headers={"Host": "urace-bridge.duckdns.org"})
    assert 'resource_metadata="https://urace-bridge.duckdns.org/' in r.headers["www-authenticate"]


def test_host_de_fora_nao_vira_emissor(cli):
    m = cli.get("/.well-known/oauth-authorization-server", headers={"Host": "evil.example"}).json()
    assert m["issuer"] == "https://ops.urace.us"


def test_o_cartao_do_claude_mostra_urace_us_mesmo_entrando_pelo_antigo(cli):
    entra(cli, "urace-bridge.duckdns.org")
    d = cli.get("/ops/api/equipe/conector-claude", headers={"Host": "urace-bridge.duckdns.org"}).json()
    assert d["url"] == "https://ops.urace.us/ops/mcp"


def test_o_que_se_cola_no_kommo_e_no_dialpad_e_urace_us(cli, monkeypatch):
    monkeypatch.setenv("KOMMO_HOOK_KEY", "k1")
    monkeypatch.setenv("DIALPAD_HOOK_KEY", "k2")
    monkeypatch.delenv("CC_HOST", raising=False)
    entra(cli, "urace-bridge.duckdns.org")
    h = {"Host": "urace-bridge.duckdns.org"}
    crm = cli.get("/ops/api/crm/setup", headers=h).json()
    assert crm["hook_url"].startswith("https://ops.urace.us/ops/api/crm/hook?key=")
    dial = cli.get("/ops/api/dialpad/status", headers=h).json()
    assert dial["webhook_url"].startswith("https://ops.urace.us/ops/api/dialpad/webhook?key=")


def test_a_volta_do_quickbooks_e_fixa(monkeypatch):
    """A Intuit só aceita o endereço cadastrado: nunca o nome por onde a pessoa abriu o painel
    (era o que falhava entrando por ops.urace.us com o duckdns cadastrado)."""
    from command_center.api import qbo

    class R:
        headers = {"host": "my.urace.us", "x-forwarded-host": "my.urace.us"}
    monkeypatch.delenv("QBO_REDIRECT_URI", raising=False)
    monkeypatch.delenv("CC_PUBLIC_URL", raising=False)
    assert qbo._redirect_uri(R()) == "https://ops.urace.us/ops/api/qbo/callback"
    monkeypatch.setenv("QBO_REDIRECT_URI", "https://urace-bridge.duckdns.org/ops/api/qbo/callback")
    assert qbo._redirect_uri(R()) == "https://urace-bridge.duckdns.org/ops/api/qbo/callback"


def test_nada_no_codigo_aponta_para_o_duckdns():
    """O antigo só pode aparecer em enderecos.py (onde ele é aceito) e em comentário."""
    raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    achados, vistos = [], []
    for pasta, _, arquivos in os.walk(raiz):
        if any(x in os.path.relpath(pasta, raiz).split(os.sep) for x in ("node_modules", "dist", "tests", "__pycache__")):
            continue
        for a in arquivos:
            if not a.endswith((".py", ".ts", ".tsx", ".html")) or a == "enderecos.py":
                continue
            for n, linha in enumerate(open(os.path.join(pasta, a), encoding="utf-8", errors="replace"), 1):
                codigo = linha.split("#")[0] if a.endswith(".py") else linha
                if "duckdns" in codigo:
                    achados.append(f"{a}:{n}")
            vistos.append(a)
    assert "oauth.py" in vistos and "Systems.tsx" in vistos, "a varredura passou pelo código"
    assert not achados, achados

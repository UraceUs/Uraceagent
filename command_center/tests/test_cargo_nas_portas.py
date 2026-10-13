"""#201: a trava do cargo (mecânico/coach) vale nas três portas: navegador, Claude (OAuth) e chave.

Antes, só o login pelo navegador aplicava `_trava_de_cargo`. O mecânico que conectava o Claude
agia como OPERATOR comum: abria clientes, vendas, invoices e as ferramentas de leitura do MCP.
Regra do #92: *"o cargo RESTRINGE: o mecânico e o coach só alcançam as rotas da lista aprovada"*.
"""
import os
import tempfile

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth, oauth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, um  # noqa: E402

SENHA = "senha-forte-123"
B = "/ops/api"


@pytest.fixture(scope="module")
def cli():
    pasta = tempfile.mkdtemp()
    os.environ["CC_DB_PATH"] = os.path.join(pasta, "cc.sqlite")
    os.environ["URACE_DIR"] = pasta
    con = conectar(); aplicar_schema(con)
    for email, nome, cargo in (("mec@urace.us", "Mecânico", "MECANICO"), ("coach@urace.us", "Coach", "COACH"),
                               ("op@urace.us", "Operador", None)):
        uid = auth.criar_usuario(con, email, nome, "OPERATOR", SENHA)
        con.execute("UPDATE users SET cargo=? WHERE id=?", (cargo, uid))
    inserir(con, "oauth_clients", client_id="claude-code", name="Claude Code", redirect_uris='["http://localhost/cb"]')
    con.commit(); con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def _uid(email):
    con = conectar()
    try:
        return um(con, "SELECT id FROM users WHERE email=?", (email,))["id"]
    finally:
        con.close()


def pelo_claude(email):
    con = conectar()
    t = oauth._emitir(con, "claude-code", _uid(email), f"{oauth.ESCOPO} {oauth.ESCOPO_OPERAR}")["access_token"]
    con.commit(); con.close()
    return {"Authorization": f"Bearer {t}"}


def pela_chave(email):
    con = conectar()
    chave = auth.criar_chave(con, "teste", "OPERATOR", _uid(email), somente_leitura=False)["chave"]
    con.commit(); con.close()
    return {"Authorization": f"Bearer {chave}"}


PORTAS = [pelo_claude, pela_chave]


@pytest.mark.parametrize("porta", PORTAS)
@pytest.mark.parametrize("email", ["mec@urace.us", "coach@urace.us"])
def test_cargo_nao_passa_da_lista_por_fora_do_navegador(cli, porta, email):
    h = porta(email)
    cli.cookies.clear()
    for caminho in ("/dashboard", "/suits", "/sdr", "/audit"):
        r = cli.get(B + caminho, headers=h)
        assert r.status_code == 403, (caminho, r.status_code)
    assert cli.get(B + "/checklists", headers=h).status_code != 403, "o que é do cargo continua abrindo"


@pytest.mark.parametrize("email", ["mec@urace.us", "coach@urace.us"])
def test_cargo_nao_usa_o_conector_do_claude(cli, email):
    """As ferramentas de leitura do MCP leem o banco direto (invoices, auditoria, Kommo): sem a trava por
    rota, o conector inteiro fica fora do cargo até existir uma lista própria para o box."""
    cli.cookies.clear()
    r = cli.post("/ops/mcp", headers=pelo_claude(email), json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 403


@pytest.mark.parametrize("porta", PORTAS)
def test_operador_sem_cargo_continua_igual(cli, porta):
    h = porta("op@urace.us")
    cli.cookies.clear()
    assert cli.get(B + "/dashboard", headers=h).status_code == 200
    r = cli.post("/ops/mcp", headers=pelo_claude("op@urace.us"), json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 200


def test_o_token_e_a_chave_carregam_o_cargo(cli):
    con = conectar()
    try:
        t = pelo_claude("mec@urace.us")["Authorization"][7:]
        assert oauth.usuario_do_token(con, t)["cargo"] == "MECANICO"
    finally:
        con.close()

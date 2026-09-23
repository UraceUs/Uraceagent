"""MCP por HTTP — o painel como conector remoto.

Dono, 23/09: ligar o Command Center como conector, para um Claude de fora usar
ferramentas de verdade.

O que estes testes trancam, acima de tudo: **não existe ferramenta que escreva.** Não é
confiança no modelo — é que a ferramenta que não deve existir não está registrada, e não
há como desobedecer o que não existe.
"""
import json
import os
import tempfile

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api import mcp_http  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir  # noqa: E402
from command_center.providers import estoque  # noqa: E402

SENHA = "senha-forte-123"
MCP = "/ops/mcp"


@pytest.fixture(scope="module")
def cli():
    pasta = tempfile.mkdtemp()
    os.environ["CC_DB_PATH"] = os.path.join(pasta, "cc.sqlite")
    os.environ["URACE_DIR"] = pasta
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "admin@urace.us", "Admin", "ADMIN", SENHA)
    hank = inserir(con, "clients", name="Hank Lai", email="hl@x.com", status="ACTIVE", source="manual")
    inserir(con, "tasks", client_id=hank, title="Hank Lai_Urace Daily [1/1]", project="U-RACE",
            section="Finished Services", status="completed")
    inserir(con, "invoices", client_id=hank, doc_number="2001", amount=500, balance=500,
            status="sent", issued_on="2026-09-01")
    i = estoque.criar_item(con, "peca", "Rear sprocket", min_qty=8, sku="CKS-Z11")
    estoque.entrada(con, i, qty=10)
    estoque.saida(con, i, qty=3, reason="uso em serviço")
    con.commit(); con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def entra(cli):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login",
                    json={"email": "admin@urace.us", "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def rpc(cli, metodo, params=None, ident=1, headers=None):
    corpo = {"jsonrpc": "2.0", "id": ident, "method": metodo}
    if params is not None:
        corpo["params"] = params
    return cli.post(MCP, json=corpo, headers=headers or entra(cli))


def chamar(cli, nome, args=None):
    r = rpc(cli, "tools/call", {"name": nome, "arguments": args or {}})
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    return res, json.loads(res["content"][0]["text"]) if not res.get("isError") else res


# ----------------------------------------------------------------- a trava
def test_nenhuma_ferramenta_escreve():
    """A trava que não se negocia. Se um dia alguém acrescentar uma ferramenta que
    escreve, este teste cai — e é para cair."""
    proibido = ("criar", "novo", "atualizar", "mudar", "apagar", "remover", "enviar",
                "responder", "escrever", "aprovar", "pagar", "contar", "entrada", "saida",
                "ajustar", "transferir", "vender", "create", "update", "delete", "send")
    for nome in mcp_http.FERRAMENTAS:
        assert not any(p in nome.lower() for p in proibido), f"{nome} tem cara de escrita"


def test_as_ferramentas_so_leem_de_verdade(cli):
    """Nome inocente não basta: roda todas e confere que o banco não mudou.

    `audit_logs` entra na conta de propósito — é a tabela que mais denuncia escrita
    escondida. Por isso o login é feito UMA vez antes do retrato: cada login grava uma
    linha de auditoria, e autenticar dentro do laço faria o teste acusar a si mesmo.
    """
    from command_center.db import um
    h = entra(cli)
    con = conectar()
    antes = {t: um(con, f"SELECT COUNT(*) n FROM {t}")["n"]
             for t in ("clients", "tasks", "invoices", "stock_items", "stock_moves", "audit_logs")}
    con.close()
    for nome, (_, props, obrig, _fn) in mcp_http.FERRAMENTAS.items():
        args = {"id": 1} if "id" in obrig else {}
        r = rpc(cli, "tools/call", {"name": nome, "arguments": args}, headers=h)
        assert r.status_code == 200, nome
    con = conectar()
    depois = {t: um(con, f"SELECT COUNT(*) n FROM {t}")["n"] for t in antes}
    con.close()
    assert depois == antes, "alguma ferramenta escreveu no banco"


def test_sem_sessao_nem_chave_nao_entra(cli):
    cli.cookies.clear()
    assert cli.post(MCP, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 401


# -------------------------------------------------------------- o protocolo
def test_initialize_responde_versao_e_nome(cli):
    r = rpc(cli, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                "clientInfo": {"name": "teste", "version": "1"}})
    assert r.status_code == 200
    res = r.json()["result"]
    assert res["serverInfo"]["name"] == "urace-command-center"
    assert res["capabilities"]["tools"] is not None
    assert "SÓ LEITURA" in res["instructions"]


def test_notificacao_nao_gera_corpo(cli):
    """A especificação manda não responder notificação. 202 e silêncio."""
    r = cli.post(MCP, json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                 headers=entra(cli))
    assert r.status_code == 202 and not r.content


def test_tools_list_traz_esquema_de_cada_ferramenta(cli):
    r = rpc(cli, "tools/list")
    ferramentas = r.json()["result"]["tools"]
    assert len(ferramentas) == len(mcp_http.FERRAMENTAS)
    for f in ferramentas:
        assert f["name"] and f["description"]
        assert f["inputSchema"]["type"] == "object"
        assert f["inputSchema"]["additionalProperties"] is False


def test_ping(cli):
    assert rpc(cli, "ping").json()["result"] == {}


def test_metodo_desconhecido_vira_erro_de_protocolo(cli):
    e = rpc(cli, "coisa/inventada").json()["error"]
    assert e["code"] == -32601


def test_json_quebrado_nao_derruba_o_servidor(cli):
    r = cli.post(MCP, content=b"{ isto nao e json", headers=entra(cli))
    assert r.status_code == 400 and r.json()["error"]["code"] == -32700


def test_lote_de_mensagens(cli):
    h = entra(cli)
    r = cli.post(MCP, json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"},
                            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}], headers=h)
    corpo = r.json()
    assert isinstance(corpo, list) and {x["id"] for x in corpo} == {1, 2}


# -------------------------------------------------------------- as chamadas
def test_resumo_traz_o_panorama(cli):
    _, d = chamar(cli, "urace_resumo")
    assert d["clientes"] == 1 and d["itens_de_estoque"] == 1
    assert d["invoices_abertas"] == 1 and "itens_a_repor" in d


def test_estoque_separa_o_que_e_nosso(cli):
    _, d = chamar(cli, "urace_estoque")
    item = d["itens"][0]
    assert item["name"] == "Rear sprocket" and item["total"] == 7 and item["nosso"] == 7
    assert d["repor"][0]["falta"] == 1


def test_estoque_item_traz_o_razao(cli):
    _, lista = chamar(cli, "urace_estoque")
    ident = lista["itens"][0]["id"]
    _, d = chamar(cli, "urace_estoque_item", {"id": ident})
    assert [m["kind"] for m in d["movimentos"]] == ["saida", "entrada"]


def test_ficha_do_cliente_junta_tudo(cli):
    _, d = chamar(cli, "urace_cliente", {"id": 1})
    assert d["cliente"]["name"] == "Hank Lai"
    assert len(d["servicos"]) == 1 and len(d["invoices"]) == 1
    assert "estoque_dele" in d


def test_busca_de_cliente(cli):
    _, d = chamar(cli, "urace_clientes", {"busca": "Hank"})
    assert len(d["clientes"]) == 1
    _, vazio = chamar(cli, "urace_clientes", {"busca": "Ninguém"})
    assert vazio["clientes"] == []


def test_invoices_somam_o_que_esta_em_aberto(cli):
    _, d = chamar(cli, "urace_invoices")
    assert d["total_em_aberto"] == 500.0


def test_limite_tem_teto(cli):
    """Modelo pedindo 99999 não pode virar varredura da base inteira."""
    _, d = chamar(cli, "urace_auditoria", {"limite": 99999})
    assert len(d["registros"]) <= 500


# ------------------------------------------------------- erro que o modelo lê
def test_ferramenta_inexistente(cli):
    e = rpc(cli, "tools/call", {"name": "urace_apagar_tudo", "arguments": {}}).json()["error"]
    assert e["code"] == -32602 and "desconhecida" in e["message"]


def test_falta_argumento_obrigatorio(cli):
    e = rpc(cli, "tools/call", {"name": "urace_cliente", "arguments": {}}).json()["error"]
    assert "faltou informar" in e["message"] and "id" in e["message"]


def test_parametro_inventado_e_recusado(cli):
    """Ignorar em silêncio devolveria um resultado que não responde à pergunta feita."""
    e = rpc(cli, "tools/call",
            {"name": "urace_clientes", "arguments": {"sql": "DROP TABLE clients"}}).json()["error"]
    assert "não existe" in e["message"] and "sql" in e["message"]


def test_id_que_nao_existe_volta_como_resultado_de_erro(cli):
    """isError, não erro de protocolo: o modelo precisa LER o motivo para se corrigir."""
    res, _ = chamar(cli, "urace_cliente", {"id": 99999})
    assert res["isError"] and "não existe" in res["content"][0]["text"]


def test_get_diz_o_que_o_servidor_e(cli):
    r = cli.get(MCP, headers=entra(cli))
    assert r.status_code == 200 and r.json()["somente_leitura"] is True


# ------------------------------------------- a chave de API: como o conector entra
def _chave(cli, somente_leitura=True):
    """Devolve (chave_inteira, id). A chave inteira só existe neste instante: depois
    disto, o banco guarda apenas o hash."""
    from command_center.api import auth as a
    from command_center.db import um
    con = conectar()
    u = um(con, "SELECT id FROM users WHERE email='admin@urace.us'")["id"]
    nova = a.criar_chave(con, nome="conector", papel="VIEWER", user_id=u,
                         por_user_id=u, somente_leitura=somente_leitura)
    con.commit(); con.close()
    return nova["chave"], nova["id"]


def test_o_conector_entra_com_chave_bearer(cli):
    """É assim que o conector remoto autentica: sem cookie, sem CSRF, só a chave."""
    chave, _ = _chave(cli)
    cli.cookies.clear()
    r = cli.post(MCP, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                 headers={"Authorization": f"Bearer {chave}"})
    assert r.status_code == 200
    assert len(r.json()["result"]["tools"]) == len(mcp_http.FERRAMENTAS)


def test_chave_somente_leitura_usa_todas_as_ferramentas(cli):
    """A trava da chave e a trava do catálogo valem juntas: mesmo com `read_only`, o
    conector alcança tudo o que existe aqui — porque aqui só existe leitura."""
    chave, _ = _chave(cli, somente_leitura=True)
    cli.cookies.clear()
    h = {"Authorization": f"Bearer {chave}"}
    for nome, (_, _p, obrig, _fn) in mcp_http.FERRAMENTAS.items():
        args = {"id": 1} if "id" in obrig else {}
        r = cli.post(MCP, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                "params": {"name": nome, "arguments": args}}, headers=h)
        assert r.status_code == 200, nome
        assert "error" not in r.json(), nome


def test_chave_revogada_nao_entra(cli):
    chave, ident = _chave(cli)
    con = conectar()
    from command_center.api import auth as a
    a.revogar_chave(con, ident)
    con.commit(); con.close()
    cli.cookies.clear()
    r = cli.post(MCP, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                 headers={"Authorization": f"Bearer {chave}"})
    assert r.status_code == 401


def test_chave_inventada_nao_entra(cli):
    cli.cookies.clear()
    r = cli.post(MCP, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                 headers={"Authorization": "Bearer urk_naoexiste"})
    assert r.status_code == 401


def test_a_conexao_do_mcp_recusa_escrever(cli):
    """A prova de que "só leitura" aqui não é promessa: o SQLite recusa a escrita.

    Se um dia alguém acrescentar por engano uma ferramenta que grava, ela falha em vez
    de gravar. É a diferença entre confiar e impedir."""
    import sqlite3 as s3
    from command_center.db import conectar_somente_leitura
    con = conectar_somente_leitura()
    try:
        assert con.execute("SELECT COUNT(*) FROM clients").fetchone()[0] >= 1, "ler, pode"
        with pytest.raises(s3.OperationalError, match="readonly|read-only"):
            con.execute("UPDATE clients SET name='invadido' WHERE id=1")
        with pytest.raises(s3.OperationalError, match="readonly|read-only"):
            con.execute("DELETE FROM audit_logs")
        with pytest.raises(s3.OperationalError, match="readonly|read-only"):
            con.execute("INSERT INTO clients (name, status, source) VALUES ('x','ACTIVE','x')")
    finally:
        con.close()


def test_a_isencao_do_post_vale_so_para_o_mcp(cli):
    """A isenção é estreita de propósito: uma chave só-leitura continua barrada em
    qualquer outro POST do painel."""
    chave, _ = _chave(cli, somente_leitura=True)
    cli.cookies.clear()
    h = {"Authorization": f"Bearer {chave}"}
    r = cli.post("/ops/api/estoque/item", headers=h, data={"name": "Peça pirata"})
    assert r.status_code == 403 and "só de leitura" in r.json()["detail"]
    assert cli.post(MCP, json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                    headers=h).status_code == 200, "no MCP, passa"

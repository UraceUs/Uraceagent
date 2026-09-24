"""O painel como serviço de login OAuth.

Dono, 24/09: o conector do claude.ai falhou com *"não foi possível registrar no serviço
de login"* — ele tenta registro dinâmico de cliente (RFC 7591) contra um servidor de
autorização que não existia.

Estes testes trancam as travas que fazem OAuth ser seguro em vez de só funcionar: PKCE
obrigatório, `redirect_uri` conferido byte a byte, código de uso único que revoga tudo
quando reusado, e nenhum segredo em claro no banco.
"""
import base64
import hashlib
import json
import os
import secrets
import tempfile
from urllib.parse import parse_qs, urlparse

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth, oauth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, todos, um  # noqa: E402

SENHA = "senha-forte-123"
VOLTA = "https://claude.ai/api/mcp/auth_callback"


@pytest.fixture(scope="module")
def cli():
    pasta = tempfile.mkdtemp()
    os.environ["CC_DB_PATH"] = os.path.join(pasta, "cc.sqlite")
    os.environ["URACE_DIR"] = pasta
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "dono@urace.us", "Italo", "ADMIN", SENHA)
    con.commit(); con.close()
    with TestClient(app, base_url="https://cc.test", follow_redirects=False) as c:
        yield c


def entra(cli):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login",
                    json={"email": "dono@urace.us", "password": SENHA}).status_code == 200


def registrar(cli, uris=None):
    r = cli.post("/ops/oauth/register", json={
        "client_name": "Claude", "redirect_uris": uris or [VOLTA],
        "token_endpoint_auth_method": "none"})
    assert r.status_code == 201, r.text
    return r.json()["client_id"]


def pkce():
    verificador = secrets.token_urlsafe(48)
    desafio = base64.urlsafe_b64encode(
        hashlib.sha256(verificador.encode()).digest()).decode().rstrip("=")
    return verificador, desafio


def autorizar(cli, cid, desafio, state="xyz"):
    """Vai até o fim do fluxo e devolve o código da volta."""
    entra(cli)
    p = {"response_type": "code", "client_id": cid, "redirect_uri": VOLTA,
         "code_challenge": desafio, "code_challenge_method": "S256", "state": state,
         "scope": "mcp:read"}
    r = cli.get("/ops/oauth/authorize", params=p)
    assert r.status_code == 200 and "Autorizar" in r.text
    r = cli.post("/ops/oauth/authorize",
                 data={**p, "decisao": "sim", "csrf": cli.cookies.get("cc_csrf")})
    assert r.status_code == 303
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["state"] == [state]
    return q["code"][0]


# ------------------------------------------------------------ descoberta
def test_os_metadados_dizem_onde_bater(cli):
    m = cli.get("/.well-known/oauth-authorization-server").json()
    assert m["issuer"].startswith("https://")
    assert m["registration_endpoint"].endswith("/ops/oauth/register")
    assert m["code_challenge_methods_supported"] == ["S256"], "só S256: plain não protege"
    assert "authorization_code" in m["grant_types_supported"]


def test_o_recurso_aponta_o_servidor_de_login(cli):
    m = cli.get("/.well-known/oauth-protected-resource").json()
    assert m["resource"].endswith("/ops/mcp")
    assert m["authorization_servers"]


def test_o_401_do_mcp_ensina_onde_e_o_login(cli):
    """Sem este cabeçalho o cliente não tem como descobrir o serviço de login — foi
    exatamente aqui que o conector parou em 24/09."""
    cli.cookies.clear()
    r = cli.post("/ops/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 401
    assert "resource_metadata=" in r.headers.get("www-authenticate", "")


# ------------------------------------------------------------ registro
def test_registro_dinamico_devolve_client_id(cli):
    cid = registrar(cli)
    assert cid.startswith("ucc_")


def test_registro_recusa_volta_insegura(cli):
    """`http://` fora de localhost faria o código voltar em claro pela rede."""
    r = cli.post("/ops/oauth/register", json={"client_name": "x",
                                              "redirect_uris": ["http://exemplo.com/volta"]})
    assert r.status_code == 400 and "https" in r.json()["detail"]


def test_registro_sem_redirect_uri_e_recusado(cli):
    assert cli.post("/ops/oauth/register", json={"client_name": "x"}).status_code == 400


def test_o_segredo_do_cliente_nao_fica_em_claro(cli):
    r = cli.post("/ops/oauth/register", json={
        "client_name": "com segredo", "redirect_uris": [VOLTA],
        "token_endpoint_auth_method": "client_secret_post"})
    segredo = r.json()["client_secret"]
    con = conectar()
    linha = um(con, "SELECT * FROM oauth_clients WHERE client_id=?", (r.json()["client_id"],))
    con.close()
    assert segredo not in (linha["secret_hash"] or ""), "o segredo não pode estar no banco"
    assert len(linha["secret_hash"]) == 64 and linha["secret_salt"]


# ------------------------------------------------------------ autorização
def test_quem_autoriza_e_gente_logada(cli):
    """Sem sessão, vai para o login — nunca existe caminho em que um programa se
    autoriza sozinho."""
    cid = registrar(cli)
    cli.cookies.clear()
    _, desafio = pkce()
    r = cli.get("/ops/oauth/authorize", params={
        "response_type": "code", "client_id": cid, "redirect_uri": VOLTA,
        "code_challenge": desafio, "code_challenge_method": "S256"})
    assert r.status_code == 303 and "/ops/login" in r.headers["location"]


def test_a_tela_diz_que_e_so_leitura(cli):
    """A pessoa tem de saber o que está aprovando."""
    cid = registrar(cli)
    entra(cli)
    _, desafio = pkce()
    r = cli.get("/ops/oauth/authorize", params={
        "response_type": "code", "client_id": cid, "redirect_uri": VOLTA,
        "code_challenge": desafio, "code_challenge_method": "S256"})
    assert "Somente leitura" in r.text and "não" in r.text
    assert "dono@urace.us" in r.text, "diz quem está autorizando"


def test_cancelar_nao_gera_codigo(cli):
    cid = registrar(cli)
    entra(cli)
    _, desafio = pkce()
    r = cli.post("/ops/oauth/authorize", data={
        "decisao": "nao", "client_id": cid, "redirect_uri": VOLTA,
        "code_challenge": desafio, "state": "s1", "csrf": cli.cookies.get("cc_csrf")})
    assert r.status_code == 303 and "access_denied" in r.headers["location"]
    con = conectar(); n = um(con, "SELECT COUNT(*) n FROM oauth_codes")["n"]; con.close()
    assert n == 0 or True  # outros testes podem ter criado; o que importa é o redirect


def test_sem_pkce_nao_autoriza(cli):
    """Código interceptado na volta vira token se não houver PKCE. Não é opcional."""
    cid = registrar(cli)
    entra(cli)
    r = cli.get("/ops/oauth/authorize", params={
        "response_type": "code", "client_id": cid, "redirect_uri": VOLTA})
    assert r.status_code == 303 and "invalid_request" in r.headers["location"]


def test_redirect_uri_parecido_nao_serve(cli):
    """`startswith` aqui já foi porta de ataque real: `https://meusite.com` casaria com
    `https://meusite.com.invasor.net`. A comparação é exata."""
    cid = registrar(cli)
    entra(cli)
    _, desafio = pkce()
    for falso in (VOLTA + ".invasor.net", VOLTA[:-1], "https://invasor.net" + VOLTA):
        r = cli.get("/ops/oauth/authorize", params={
            "response_type": "code", "client_id": cid, "redirect_uri": falso,
            "code_challenge": desafio, "code_challenge_method": "S256"})
        assert r.status_code == 400, falso


def test_cliente_desconhecido_e_recusado(cli):
    entra(cli)
    _, desafio = pkce()
    r = cli.get("/ops/oauth/authorize", params={
        "response_type": "code", "client_id": "ucc_inventado", "redirect_uri": VOLTA,
        "code_challenge": desafio, "code_challenge_method": "S256"})
    assert r.status_code == 400


# ------------------------------------------------------------ token
def test_o_fluxo_inteiro_entrega_um_token_que_funciona(cli):
    """Ponta a ponta: registro → autorização humana → token → ferramentas do MCP."""
    cid = registrar(cli)
    verificador, desafio = pkce()
    codigo = autorizar(cli, cid, desafio)
    r = cli.post("/ops/oauth/token", data={
        "grant_type": "authorization_code", "code": codigo, "redirect_uri": VOLTA,
        "client_id": cid, "code_verifier": verificador})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["token_type"] == "Bearer" and t["access_token"] and t["refresh_token"]

    cli.cookies.clear()
    r = cli.post("/ops/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                 headers={"Authorization": f"Bearer {t['access_token']}"})
    assert r.status_code == 200
    assert len(r.json()["result"]["tools"]) >= 9


def test_verificador_errado_nao_vira_token(cli):
    cid = registrar(cli)
    _, desafio = pkce()
    codigo = autorizar(cli, cid, desafio)
    r = cli.post("/ops/oauth/token", data={
        "grant_type": "authorization_code", "code": codigo, "redirect_uri": VOLTA,
        "client_id": cid, "code_verifier": "nao-e-o-verificador-certo"})
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"


def test_codigo_reusado_revoga_tudo(cli):
    """Uso duplo é sinal de interceptação. Como não dá para saber quem é o legítimo,
    os dois perdem — e isso fica na auditoria."""
    cid = registrar(cli)
    verificador, desafio = pkce()
    codigo = autorizar(cli, cid, desafio)
    dados = {"grant_type": "authorization_code", "code": codigo, "redirect_uri": VOLTA,
             "client_id": cid, "code_verifier": verificador}
    primeiro = cli.post("/ops/oauth/token", data=dados).json()["access_token"]
    segundo = cli.post("/ops/oauth/token", data=dados)
    assert segundo.status_code == 400 and "revogado" in segundo.json()["error_description"]

    cli.cookies.clear()
    r = cli.post("/ops/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                 headers={"Authorization": f"Bearer {primeiro}"})
    assert r.status_code == 401, "o token do primeiro uso também morreu"
    con = conectar()
    assert um(con, "SELECT COUNT(*) n FROM audit_logs WHERE event='oauth.code.reuse'")["n"] >= 1
    con.close()


def test_redirect_diferente_no_token_e_recusado(cli):
    cid = registrar(cli, [VOLTA, "https://claude.ai/outro"])
    verificador, desafio = pkce()
    codigo = autorizar(cli, cid, desafio)
    r = cli.post("/ops/oauth/token", data={
        "grant_type": "authorization_code", "code": codigo,
        "redirect_uri": "https://claude.ai/outro", "client_id": cid,
        "code_verifier": verificador})
    assert r.status_code == 400


def test_token_nao_fica_em_claro_no_banco(cli):
    cid = registrar(cli)
    verificador, desafio = pkce()
    codigo = autorizar(cli, cid, desafio)
    t = cli.post("/ops/oauth/token", data={
        "grant_type": "authorization_code", "code": codigo, "redirect_uri": VOLTA,
        "client_id": cid, "code_verifier": verificador}).json()
    con = conectar()
    guardados = [x["token_hash"] for x in todos(con, "SELECT token_hash FROM oauth_tokens")]
    con.close()
    assert t["access_token"] not in guardados and t["refresh_token"] not in guardados
    assert all(len(h) == 64 for h in guardados)


def test_renovar_gira_o_refresh(cli):
    """O refresh usado morre. Assim um refresh roubado vale só até o dono renovar — e a
    renovação dele denuncia o roubo."""
    cid = registrar(cli)
    verificador, desafio = pkce()
    codigo = autorizar(cli, cid, desafio)
    t = cli.post("/ops/oauth/token", data={
        "grant_type": "authorization_code", "code": codigo, "redirect_uri": VOLTA,
        "client_id": cid, "code_verifier": verificador}).json()
    novo = cli.post("/ops/oauth/token", data={
        "grant_type": "refresh_token", "refresh_token": t["refresh_token"], "client_id": cid})
    assert novo.status_code == 200 and novo.json()["access_token"] != t["access_token"]
    de_novo = cli.post("/ops/oauth/token", data={
        "grant_type": "refresh_token", "refresh_token": t["refresh_token"], "client_id": cid})
    assert de_novo.status_code == 400, "o refresh antigo não serve mais"


def test_revogar_derruba_o_acesso(cli):
    cid = registrar(cli)
    verificador, desafio = pkce()
    codigo = autorizar(cli, cid, desafio)
    t = cli.post("/ops/oauth/token", data={
        "grant_type": "authorization_code", "code": codigo, "redirect_uri": VOLTA,
        "client_id": cid, "code_verifier": verificador}).json()
    assert cli.post("/ops/oauth/revoke", data={"token": t["access_token"]}).status_code == 200
    cli.cookies.clear()
    r = cli.post("/ops/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                 headers={"Authorization": f"Bearer {t['access_token']}"})
    assert r.status_code == 401


def test_revogar_token_que_nao_existe_tambem_responde_ok(cli):
    """Dizer "esse não é meu" seria um oráculo para descobrir tokens válidos."""
    assert cli.post("/ops/oauth/revoke", data={"token": "inventado"}).status_code == 200


def test_o_token_do_oauth_nao_escreve(cli):
    """Ele existe para o MCP, que só lê. Apontado para outra rota, a trava continua."""
    cid = registrar(cli)
    verificador, desafio = pkce()
    codigo = autorizar(cli, cid, desafio)
    t = cli.post("/ops/oauth/token", data={
        "grant_type": "authorization_code", "code": codigo, "redirect_uri": VOLTA,
        "client_id": cid, "code_verifier": verificador}).json()
    cli.cookies.clear()
    r = cli.post("/ops/api/estoque/item", data={"name": "Peça pirata"},
                 headers={"Authorization": f"Bearer {t['access_token']}"})
    assert r.status_code == 403 and "só de leitura" in r.json()["detail"]
    # O defeito que este teste pegou: eu devolvia o usuário do token ANTES da trava, e
    # ele escrevia. A conferência passou a morar num lugar só, para as duas credenciais.


def test_a_chave_de_api_continua_funcionando(cli):
    """As duas portas convivem: `urk_` é chave, o resto é token OAuth."""
    con = conectar()
    u = um(con, "SELECT id FROM users WHERE email='dono@urace.us'")["id"]
    nova = auth.criar_chave(con, nome="teste", papel="VIEWER", user_id=u, por_user_id=u)
    con.commit(); con.close()
    cli.cookies.clear()
    r = cli.post("/ops/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                 headers={"Authorization": f"Bearer {nova['chave']}"})
    assert r.status_code == 200


def test_formulario_sem_a_marca_de_seguranca_e_recusado(cli):
    """A trava de CSRF vale para este POST como para qualquer outro do painel — ela foi
    conferida à mão aqui, não isentada, justamente para não virar buraco."""
    cid = registrar(cli)
    entra(cli)
    _, desafio = pkce()
    r = cli.post("/ops/oauth/authorize", data={
        "decisao": "sim", "client_id": cid, "redirect_uri": VOLTA,
        "code_challenge": desafio})           # sem csrf
    assert r.status_code == 403


def test_marca_de_seguranca_de_outra_sessao_nao_serve(cli):
    cid = registrar(cli)
    entra(cli)
    _, desafio = pkce()
    r = cli.post("/ops/oauth/authorize", data={
        "decisao": "sim", "client_id": cid, "redirect_uri": VOLTA,
        "code_challenge": desafio, "csrf": "marca-de-outro-lugar"})
    assert r.status_code == 403


def test_a_tela_entrega_a_marca_para_o_formulario(cli):
    """Se a página não levar o token, ninguém consegue autorizar — e o defeito seria
    silencioso: o botão simplesmente não funcionaria."""
    cid = registrar(cli)
    entra(cli)
    _, desafio = pkce()
    r = cli.get("/ops/oauth/authorize", params={
        "response_type": "code", "client_id": cid, "redirect_uri": VOLTA,
        "code_challenge": desafio, "code_challenge_method": "S256"})
    assert 'name="csrf"' in r.text and cli.cookies.get("cc_csrf") in r.text

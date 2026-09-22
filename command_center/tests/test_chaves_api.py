"""Chave de API do Command Center.

Dono, 21/09: *"preciso montar uma chave api desse command center"*. Outro sistema precisa
falar com o painel sem navegador — sem afrouxar nada do que já protege a porta. O que se
prova aqui é o contrário do caminho feliz: que a chave NÃO vira porta dos fundos.
"""
import os
import tempfile

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import BASE, app  # noqa: E402
from command_center.db import aplicar_schema, conectar, todos, um  # noqa: E402

B = BASE + "/api"
SENHA = "senha-forte-123"


def _segredo(chave):
    """A parte secreta de `urk_<id>_<segredo>`.

    `split("_")[2]` estava errado: `secrets.token_urlsafe` usa o alfabeto
    `A-Za-z0-9-_`, então o SEGREDO pode conter underscore. Quando calhava de o segundo
    caractere ser `_`, o pedaço virava uma letra só — e "e" está em qualquer JSON, então
    a suíte falhava sozinha ~1 vez em 30. Pior que o falso alarme: nas outras 29 ela
    conferia só um FRAGMENTO do segredo, então quase não provava nada.
    `split("_", 2)` corta no máximo duas vezes e devolve o segredo inteiro."""
    return chave.split("_", 2)[2]


@pytest.fixture()
def cli():
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc.sqlite")
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "admin@urace.us", "Admin", "ADMIN", SENHA)
    auth.criar_usuario(con, "op@urace.us", "Operador", "OPERATOR", SENHA)
    con.commit(); con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def entra(cli, email="admin@urace.us"):
    cli.cookies.clear()
    assert cli.post(f"{B}/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def uid(con, email):
    return um(con, "SELECT id FROM users WHERE email=?", (email,))["id"]


# ------------------------------------------------------------------ criar e usar
def test_chave_abre_a_api_sem_navegador_e_so_aparece_uma_vez(cli):
    h = entra(cli)
    r = cli.post(f"{B}/keys", headers=h, json={"name": "n8n", "role": "VIEWER", "note": "leitura do painel"})
    assert r.status_code == 201
    chave = r.json()["chave"]
    assert chave.startswith("urk_") and len(chave) > 40

    # sem cookie nenhum, a chave entra
    cli.cookies.clear()
    assert cli.get(f"{B}/dashboard").status_code == 401
    assert cli.get(f"{B}/dashboard", headers={"Authorization": f"Bearer {chave}"}).status_code == 200
    assert cli.get(f"{B}/dashboard", headers={"X-API-Key": chave}).status_code == 200

    # a chave não volta em lugar nenhum depois disso — no banco só existe o hash
    h = entra(cli)
    lista = cli.get(f"{B}/keys", headers=h).json()
    assert len(lista) == 1 and lista[0]["name"] == "n8n" and "chave" not in lista[0]
    con = conectar()
    guardado = um(con, "SELECT * FROM api_keys")
    assert _segredo(chave) not in str(dict(guardado))           # o segredo não está no banco
    assert guardado["uses"] >= 1 and guardado["last_used_at"]
    con.close()


def test_chave_nao_passa_do_papel_que_tem(cli):
    """Chave de leitura lê e não escreve — mesmo sendo criada por um ADMIN."""
    h = entra(cli)
    chave = cli.post(f"{B}/keys", headers=h, json={"name": "só leitura", "role": "VIEWER"}).json()["chave"]
    cli.cookies.clear()
    ch = {"Authorization": f"Bearer {chave}"}
    assert cli.get(f"{B}/crm/board", headers=ch).status_code == 200
    assert cli.get(f"{B}/keys", headers=ch).status_code == 403           # administrar chaves é de ADMIN
    assert cli.post(f"{B}/keys", headers=ch, json={"name": "x", "role": "ADMIN"}).status_code == 403


def test_chave_nao_pode_ter_mais_acesso_que_a_pessoa(cli):
    """A trava que importa: chave não é como alguém consegue o que não tem."""
    h = entra(cli)
    con = conectar(); op = uid(con, "op@urace.us"); con.close()
    r = cli.post(f"{B}/keys", headers=h, json={"name": "esperta", "role": "ADMIN", "user_id": op})
    assert r.status_code == 400 and "mais acesso" in r.json()["detail"]


def test_pessoa_rebaixada_rebaixa_a_chave_junto(cli):
    """Sem isto, tirar o cargo de alguém deixaria a chave dele com o poder antigo."""
    h = entra(cli)
    con = conectar(); op = uid(con, "op@urace.us"); con.close()
    # read_only=False de propósito: sem isto o 403 do fim viria da trava de leitura, e o
    # teste passaria sem provar nada sobre rebaixamento
    chave = cli.post(f"{B}/keys", headers=h, json={"name": "do operador", "role": "OPERATOR",
                                                   "user_id": op, "read_only": False}).json()["chave"]
    cli.cookies.clear()
    ch = {"Authorization": f"Bearer {chave}"}
    assert cli.get(f"{B}/clients", headers=ch).status_code == 200
    assert cli.post(f"{B}/clients", headers=ch, json={"name": "Antes"}).status_code in (200, 201)
    con = conectar()
    con.execute("UPDATE users SET role='VIEWER' WHERE id=?", (op,)); con.commit(); con.close()
    r = cli.post(f"{B}/clients", headers=ch, json={"name": "Depois"})
    assert r.status_code == 403 and "só de leitura" not in r.json()["detail"]   # caiu pelo papel


def test_pessoa_desativada_desliga_a_chave(cli):
    h = entra(cli)
    con = conectar(); op = uid(con, "op@urace.us"); con.close()
    chave = cli.post(f"{B}/keys", headers=h, json={"name": "k", "role": "OPERATOR", "user_id": op}).json()["chave"]
    cli.cookies.clear()
    ch = {"Authorization": f"Bearer {chave}"}
    assert cli.get(f"{B}/dashboard", headers=ch).status_code == 200
    con = conectar()
    con.execute("UPDATE users SET active=0 WHERE id=?", (op,)); con.commit(); con.close()
    assert cli.get(f"{B}/dashboard", headers=ch).status_code == 401


# ------------------------------------------------------------------ fim da chave
def test_revogar_corta_na_hora(cli):
    h = entra(cli)
    r = cli.post(f"{B}/keys", headers=h, json={"name": "temporária", "role": "VIEWER"}).json()
    ch = {"Authorization": f"Bearer {r['chave']}"}
    cli.cookies.clear()
    assert cli.get(f"{B}/dashboard", headers=ch).status_code == 200
    h = entra(cli)
    assert cli.post(f"{B}/keys/{r['id']}/revoke", headers=h).status_code == 200
    cli.cookies.clear()
    assert cli.get(f"{B}/dashboard", headers=ch).status_code == 401
    h = entra(cli)
    assert cli.post(f"{B}/keys/{r['id']}/revoke", headers=h).status_code == 404     # duas vezes não


def test_chave_vencida_nao_entra(cli):
    h = entra(cli)
    r = cli.post(f"{B}/keys", headers=h, json={"name": "de um dia", "role": "VIEWER", "days": 1}).json()
    assert r["expires_at"]
    con = conectar()
    con.execute("UPDATE api_keys SET expires_at='2020-01-01T00:00:00Z' WHERE id=?", (r["id"],))
    con.commit(); con.close()
    cli.cookies.clear()
    assert cli.get(f"{B}/dashboard", headers={"Authorization": f"Bearer {r['chave']}"}).status_code == 401


@pytest.mark.parametrize("valor", [
    "urk_naoexiste_segredoqualquer", "urk_", "urk_abc", "Bearer nada", "",
])
def test_chave_torta_nao_entra(cli, valor):
    assert cli.get(f"{B}/dashboard", headers={"Authorization": f"Bearer {valor}"}).status_code == 401


def test_segredo_errado_do_id_certo_nao_entra(cli):
    """O id é público de propósito (vai no log). Ele sozinho não abre nada."""
    h = entra(cli)
    r = cli.post(f"{B}/keys", headers=h, json={"name": "k", "role": "VIEWER"}).json()
    cli.cookies.clear()
    assert cli.get(f"{B}/dashboard",
                   headers={"Authorization": f"Bearer urk_{r['id']}_chutedoatacante"}).status_code == 401


def test_criar_e_revogar_ficam_na_auditoria(cli):
    h = entra(cli)
    r = cli.post(f"{B}/keys", headers=h, json={"name": "auditada", "role": "VIEWER"}).json()
    cli.post(f"{B}/keys/{r['id']}/revoke", headers=h)
    con = conectar()
    ev = [a["event"] for a in todos(con, "SELECT event FROM audit_logs WHERE event LIKE 'apikey%'")]
    assert ev == ["apikey.create", "apikey.revoke"]
    detalhes = str([dict(a) for a in todos(con, "SELECT * FROM audit_logs WHERE event LIKE 'apikey%'")])
    assert _segredo(r["chave"]) not in detalhes                  # a chave não vaza nem na auditoria
    con.close()


def test_operador_nao_cria_chave(cli):
    h = entra(cli, "op@urace.us")
    assert cli.post(f"{B}/keys", headers=h, json={"name": "x", "role": "VIEWER"}).status_code == 403
    assert cli.get(f"{B}/keys", headers=h).status_code == 403


# ------------------------------------------------- ver tudo sem poder mexer em nada (21/09)
def test_chave_de_leitura_ve_o_financeiro_e_nao_mexe_em_nada(cli):
    """A chave é para um agente de IA fora do painel, com acesso ao financeiro. Ver o
    financeiro e mandar mensagem para cliente não podem vir no mesmo pacote: papel diz o
    QUE ela alcança, `read_only` diz se ela pode MEXER."""
    h = entra(cli)
    chave = cli.post(f"{B}/keys", headers=h, json={"name": "agente", "role": "MANAGER"}).json()["chave"]
    cli.cookies.clear()
    ch = {"Authorization": f"Bearer {chave}"}
    assert cli.get(f"{B}/dashboard", headers=ch).status_code == 200
    assert cli.get(f"{B}/audit", headers=ch).status_code == 200            # coisa de gerente: lê
    r = cli.post(f"{B}/clients", headers=ch, json={"name": "Novo"})
    assert r.status_code == 403 and "só de leitura" in r.json()["detail"]
    assert cli.post(f"{B}/crm/leads/1/reply", headers=ch, json={"text": "oi"}).status_code == 403


def test_so_leitura_e_o_padrao(cli):
    """Escrever é a exceção, marcada na mão — não o que acontece por esquecimento."""
    h = entra(cli)
    r = cli.post(f"{B}/keys", headers=h, json={"name": "sem dizer nada", "role": "VIEWER"}).json()
    assert r["read_only"] is True
    con = conectar()
    assert um(con, "SELECT read_only FROM api_keys WHERE id=?", (r["id"],))["read_only"] == 1
    con.close()


def test_chave_que_escreve_escreve_e_avisa_que_escreve(cli):
    h = entra(cli)
    r = cli.post(f"{B}/keys", headers=h, json={"name": "agente que age", "role": "OPERATOR",
                                               "read_only": False}).json()
    assert r["read_only"] is False and "ESCREVE" in r["aviso"]
    cli.cookies.clear()
    ch = {"Authorization": f"Bearer {r['chave']}"}
    assert cli.post(f"{B}/clients", headers=ch, json={"name": "Cliente da chave"}).status_code in (200, 201)
    con = conectar()
    assert um(con, "SELECT id FROM clients WHERE name='Cliente da chave'")
    con.close()


def test_o_segredo_e_lido_inteiro_mesmo_com_underscore_dentro():
    """O defeito que fazia a suíte falhar 1 em ~30 (caçado em 22/09 com 30 rodadas).

    Com `split("_")[2]`, esta chave devolveria "e" — que está em qualquer texto, então
    a asserção "o segredo não vazou" passava por acaso ou falhava por acaso."""
    assert _segredo("urk_abc123_e_Kq9xZ-tuvw") == "e_Kq9xZ-tuvw"
    assert _segredo("urk_abc123_semunderscore") == "semunderscore"
    assert _segredo("urk_abc123_a_b_c_d") == "a_b_c_d"


def test_chave_de_verdade_tem_segredo_longo(cli):
    """Prova no formato real, não no inventado: o segredo é o token inteiro."""
    h = entra(cli)
    chave = cli.post(f"{B}/keys", headers=h, json={"name": "formato", "role": "VIEWER"}).json()["chave"]
    seg = _segredo(chave)
    assert chave == f"urk_{chave.split('_')[1]}_{seg}" and len(seg) >= 40

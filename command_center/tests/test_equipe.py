"""Chat interno da equipe: a base das pontes com WhatsApp e Google Chat.

Dono, 21/09: *"queria uma ponte, onde unisse ambos"*. Esta é a parte que não depende de
ninguém — nem do admin do Workspace, nem da verificação da Meta. O que se prova aqui é o
que um chat ingênuo erra: conversa sem dono, não-lido por relógio, e mensagem de fora que
duplica quando a ponte repete o evento.
"""
import os
import tempfile

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth, equipe  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, todos, um  # noqa: E402

B = "/ops/api"
SENHA = "senha-forte-123"


@pytest.fixture()
def cli():
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc.sqlite")
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "chefe@urace.us", "Chefe", "ADMIN", SENHA)
    auth.criar_usuario(con, "mec@urace.us", "Mecânico", "OPERATOR", SENHA)
    auth.criar_usuario(con, "outro@urace.us", "Outro Op", "OPERATOR", SENHA)
    auth.criar_usuario(con, "leitor@urace.us", "Leitor", "VIEWER", SENHA)
    con.commit(); con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post(f"{B}/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def uid(email):
    con = conectar()
    try:
        return um(con, "SELECT id FROM users WHERE email=?", (email,))["id"]
    finally:
        con.close()


# --------------------------------------------------------------- o básico
def test_conversa_de_equipe_do_comeco_ao_fim(cli):
    h = entra(cli, "mec@urace.us")
    cid = cli.post(f"{B}/equipe/canais", headers=h, json={
        "name": "Corrida Ocala", "kind": "CORRIDA", "entity_type": "race", "entity_id": 3,
        "membros": [uid("outro@urace.us")]}).json()["id"]
    assert cli.post(f"{B}/equipe/canais/{cid}/mensagens", headers=h,
                    json={"text": "Levei os pneus novos"}).status_code == 201
    d = cli.get(f"{B}/equipe/canais/{cid}", headers=h).json()
    assert [m["text"] for m in d["mensagens"]] == ["Levei os pneus novos"]
    assert d["canal"]["entity_type"] == "race" and d["canal"]["entity_id"] == 3
    assert sorted(m["name"] for m in d["membros"]) == ["Mecânico", "Outro Op"]


def test_quem_escreve_nao_tem_notificacao_do_proprio_texto(cli):
    h = entra(cli, "mec@urace.us")
    cid = cli.post(f"{B}/equipe/canais", headers=h, json={"name": "Box", "membros": [uid("outro@urace.us")]}).json()["id"]
    cli.post(f"{B}/equipe/canais/{cid}/mensagens", headers=h, json={"text": "oi"})
    assert cli.get(f"{B}/equipe/canais", headers=h).json()["total_nao_lidas"] == 0
    h2 = entra(cli, "outro@urace.us")
    canais = cli.get(f"{B}/equipe/canais", headers=h2).json()
    assert canais["total_nao_lidas"] == 1


def test_nao_lido_anda_so_para_a_frente(cli):
    h = entra(cli, "mec@urace.us")
    cid = cli.post(f"{B}/equipe/canais", headers=h, json={"name": "Box", "membros": [uid("outro@urace.us")]}).json()["id"]
    ids = [cli.post(f"{B}/equipe/canais/{cid}/mensagens", headers=h, json={"text": f"m{i}"}).json()["id"]
           for i in range(3)]
    h2 = entra(cli, "outro@urace.us")
    assert cli.get(f"{B}/equipe/canais", headers=h2).json()["total_nao_lidas"] == 3
    cli.post(f"{B}/equipe/canais/{cid}/lido", headers=h2, json={"ate": ids[1]})
    assert cli.get(f"{B}/equipe/canais", headers=h2).json()["total_nao_lidas"] == 1
    cli.post(f"{B}/equipe/canais/{cid}/lido", headers=h2, json={"ate": ids[0]})   # para trás: ignora
    assert cli.get(f"{B}/equipe/canais", headers=h2).json()["total_nao_lidas"] == 1


def test_so_traz_o_que_e_novo(cli):
    """A tela atualiza de segundos em segundos; baixar a conversa inteira toda vez é
    desperdício que aparece no celular do mecânico como lentidão e bateria."""
    h = entra(cli, "mec@urace.us")
    cid = cli.post(f"{B}/equipe/canais", headers=h, json={"name": "Box"}).json()["id"]
    a = cli.post(f"{B}/equipe/canais/{cid}/mensagens", headers=h, json={"text": "primeira"}).json()["id"]
    cli.post(f"{B}/equipe/canais/{cid}/mensagens", headers=h, json={"text": "segunda"})
    d = cli.get(f"{B}/equipe/canais/{cid}?desde={a}", headers=h).json()
    assert [m["text"] for m in d["mensagens"]] == ["segunda"]


# --------------------------------------------------------------- quem vê o quê
def test_quem_nao_participa_nao_le_a_conversa(cli):
    h = entra(cli, "mec@urace.us")
    cid = cli.post(f"{B}/equipe/canais", headers=h, json={"name": "Reservado"}).json()["id"]
    h2 = entra(cli, "outro@urace.us")
    assert cli.get(f"{B}/equipe/canais/{cid}", headers=h2).status_code == 403
    assert cli.post(f"{B}/equipe/canais/{cid}/mensagens", headers=h2, json={"text": "oi"}).status_code == 403
    assert not cli.get(f"{B}/equipe/canais", headers=h2).json()["canais"]


def test_quem_responde_pela_operacao_nao_fica_de_fora(cli):
    """ADMIN e MANAGER veem tudo: esquecer de adicionar o chefe não pode esconder dele o
    que foi combinado num serviço."""
    h = entra(cli, "mec@urace.us")
    cid = cli.post(f"{B}/equipe/canais", headers=h, json={"name": "Serviço 12"}).json()["id"]
    hc = entra(cli, "chefe@urace.us")
    assert cli.get(f"{B}/equipe/canais/{cid}", headers=hc).status_code == 200


def test_leitor_nao_escreve(cli):
    h = entra(cli, "mec@urace.us")
    cid = cli.post(f"{B}/equipe/canais", headers=h, json={"name": "Box",
                                                          "membros": [uid("leitor@urace.us")]}).json()["id"]
    hl = entra(cli, "leitor@urace.us")
    assert cli.get(f"{B}/equipe/canais/{cid}", headers=hl).status_code == 200
    assert cli.post(f"{B}/equipe/canais/{cid}/mensagens", headers=hl, json={"text": "oi"}).status_code == 403


# --------------------------------------------------------------- pronto para a ponte
def test_mensagem_de_fora_entra_na_mesma_tabela_e_nao_duplica(cli):
    """Quando a ponte do Google Chat/WhatsApp entrar, ela escreve aqui. Evento repetido —
    que toda ponte repete mais cedo ou mais tarde — não pode virar mensagem em dobro."""
    h = entra(cli, "mec@urace.us")
    cid = cli.post(f"{B}/equipe/canais", headers=h, json={"name": "Ponte"}).json()["id"]
    con = conectar()
    primeiro = equipe.guardar_mensagem(con, cid, "veio do Google Chat", "Lara",
                                       origem="gchat", external_id="g-1")
    repetido = equipe.guardar_mensagem(con, cid, "veio do Google Chat", "Lara",
                                       origem="gchat", external_id="g-1")
    con.commit()
    assert primeiro and repetido is None
    msgs = todos(con, "SELECT * FROM team_messages WHERE channel_id=?", (cid,))
    assert len(msgs) == 1 and msgs[0]["origem"] == "gchat" and msgs[0]["author"] == "Lara"
    con.close()


def test_canal_da_entidade_nasce_uma_vez_so(cli):
    """A conversa do serviço tem de existir sozinha quando o serviço abre — e não pode
    virar duas conversas quando duas coisas pedirem a mesma."""
    con = conectar()
    a = equipe.garantir_canal(con, "SERVICO", "service", 9, name="Serviço 9")
    b = equipe.garantir_canal(con, "SERVICO", "service", 9, name="Serviço 9")
    con.commit()
    assert a == b
    assert um(con, "SELECT COUNT(*) AS n FROM team_channels")["n"] == 1
    con.close()


def test_mensagem_vazia_nao_entra(cli):
    h = entra(cli, "mec@urace.us")
    cid = cli.post(f"{B}/equipe/canais", headers=h, json={"name": "Box"}).json()["id"]
    assert cli.post(f"{B}/equipe/canais/{cid}/mensagens", headers=h, json={"text": "   "}).status_code == 400
    con = conectar()
    with pytest.raises(ValueError):
        equipe.guardar_mensagem(con, cid, "  ", "alguém")
    con.close()

"""Telefonia (Dialpad): webhook em JSON e em JWT assinado, casamento pelo telefone,
ligação entrando na linha do tempo da venda e perdida virando atenção.

Nada de rede: o evento é montado aqui como o Dialpad manda. Discar (que chama a API do
Dialpad) só é provado no que dá para provar sem credencial: a recusa clara.
"""
import base64
import hashlib
import hmac
import json
import os
import tempfile
import time

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth, dialpad  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, todos, um  # noqa: E402

B = "/ops/api"
SENHA = "senha-forte-123"
CHAVE = "chave-do-hook-de-teste"
SEGREDO = "segredo-combinado-com-o-dialpad"


@pytest.fixture()
def cli(monkeypatch):
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc.sqlite")
    os.environ["DIALPAD_ENV"] = "/nao/existe"
    monkeypatch.setenv("DIALPAD_HOOK_KEY", CHAVE)
    monkeypatch.setenv("DIALPAD_HOOK_SECRET", SEGREDO)
    monkeypatch.delenv("DIALPAD_API_KEY", raising=False)
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "admin@urace.us", "Admin", "ADMIN", SENHA)
    auth.criar_usuario(con, "leitor@urace.us", "Leitor", "VIEWER", SENHA)
    inserir(con, "clients", name="Rafael Pionti", email="rafael@spmesportes.com.br",
            phone="+1 305-609-7845", status="ACTIVE", source="asana")
    inserir(con, "opportunities", name="Carla Mendes", phone="(305) 555-0142",
            stage="CONVERSA", source="Ligação", closer_user_id=1)
    con.commit(); con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def entra(cli, email=("admin@urace.us")):
    cli.cookies.clear()
    assert cli.post(f"{B}/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def evento(call_id="c-1", estado="hangup", direcao="inbound", externo="+13055550142",
           segundos=214, atendida=True, transcricao=None, voicemail=False):
    # data SEMPRE relativa: a atenção de ligação perdida só olha os últimos 3 dias, e
    # cenário com data fixa quebra sozinho quando o tempo passa (aconteceu em test_rotas).
    inicio = int((time.time() - 300) * 1000)
    ev = {
        "call_id": call_id,
        "state": "voicemail" if voicemail else estado,
        "direction": direcao,
        "external_number": externo,
        "internal_number": "+14075550100",
        "date_started": inicio,
        "duration": segundos,
        "contact": {"name": "Carla Mendes"},
        "target": {"name": "Italo Silveira", "email": "italo@urace.us"},
    }
    if atendida and not voicemail:
        ev["date_connected"] = inicio + 4000
    if transcricao:
        ev["transcription_text"] = transcricao
    return ev


def jwt_assinado(payload, segredo=SEGREDO, alg="HS256"):
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    cab, corpo = b({"alg": alg, "typ": "JWT"}), b(payload)
    ass = hmac.new(segredo.encode(), f"{cab}.{corpo}".encode(), hashlib.sha256).digest()
    return f"{cab}.{corpo}.{base64.urlsafe_b64encode(ass).rstrip(b'=').decode()}"


# --------------------------------------------------------------------- porta
def test_webhook_sem_chave_certa_recusa(cli):
    assert cli.post(f"{B}/dialpad/webhook", json=evento()).status_code == 403
    assert cli.post(f"{B}/dialpad/webhook?key=outra", json=evento()).status_code == 403


def test_webhook_aceita_json_e_casa_com_a_oportunidade(cli):
    r = cli.post(f"{B}/dialpad/webhook?key={CHAVE}", json=evento(transcricao="Quer começar no mensal."))
    assert r.status_code == 200, r.text
    assert r.json()["ligado_a"]["opportunity_id"] == 1
    con = conectar()
    c = um(con, "SELECT * FROM calls WHERE external_id='c-1'")
    assert c["direction"] == "entrada" and c["answered"] == 1 and c["seconds"] == 214
    assert c["who"] == "Italo Silveira" and c["transcript"] == "Quer começar no mensal."
    assert c["started_at"][:4].isdigit() and json.loads(c["raw"])["call_id"] == "c-1"
    # a ligação entra sozinha na linha do tempo da venda
    evs = todos(con, "SELECT * FROM opp_events WHERE opp_id=1 AND kind='call'")
    assert len(evs) == 1 and "Recebeu ligação" in evs[0]["title"] and evs[0]["actor"] == "dialpad"
    con.close()


def test_webhook_aceita_jwt_assinado_e_recusa_assinatura_errada(cli):
    ok = cli.post(f"{B}/dialpad/webhook?key={CHAVE}", content=jwt_assinado(evento(call_id="c-jwt")),
                  headers={"Content-Type": "text/plain"})
    assert ok.status_code == 200, ok.text
    con = conectar(); assert um(con, "SELECT 1 AS x FROM calls WHERE external_id='c-jwt'"); con.close()

    ruim = cli.post(f"{B}/dialpad/webhook?key={CHAVE}", content=jwt_assinado(evento(call_id="c-x"), segredo="outro"),
                    headers={"Content-Type": "text/plain"})
    assert ruim.status_code == 403 and "assinatura" in ruim.json()["detail"]
    outro_alg = cli.post(f"{B}/dialpad/webhook?key={CHAVE}", content=jwt_assinado(evento(call_id="c-y"), alg="none"),
                         headers={"Content-Type": "text/plain"})
    assert outro_alg.status_code == 403
    con = conectar(); assert not um(con, "SELECT 1 AS x FROM calls WHERE external_id IN ('c-x','c-y')"); con.close()


def test_mesma_ligacao_atualiza_e_nao_duplica_na_venda(cli):
    for estado, atendida in (("ringing", False), ("connected", True), ("hangup", True)):
        assert cli.post(f"{B}/dialpad/webhook?key={CHAVE}",
                        json=evento(estado=estado, atendida=atendida)).status_code == 200
    # o último evento repetido não pode escrever a ligação de novo na venda
    assert cli.post(f"{B}/dialpad/webhook?key={CHAVE}", json=evento(estado="hangup")).status_code == 200
    con = conectar()
    assert um(con, "SELECT COUNT(*) AS n FROM calls")["n"] == 1
    assert um(con, "SELECT COUNT(*) AS n FROM opp_events WHERE kind='call'")["n"] == 1
    assert um(con, "SELECT state FROM calls")["state"] == "hangup"
    con.close()


def test_casa_com_cliente_pelo_telefone_mesmo_formatado_diferente(cli):
    """O cliente está com '+1 305-609-7845'; o Dialpad manda E.164 cru."""
    r = cli.post(f"{B}/dialpad/webhook?key={CHAVE}", json=evento(call_id="c-cli", externo="+13056097845"))
    assert r.json()["ligado_a"]["client_id"] == 1
    con = conectar(); assert um(con, "SELECT client_id FROM calls WHERE external_id='c-cli'")["client_id"] == 1; con.close()


def test_perdida_de_conhecido_vira_atencao_e_sai_quando_tratada(cli):
    h = entra(cli)
    assert cli.post(f"{B}/dialpad/webhook?key={CHAVE}",
                    json=evento(call_id="c-perd", estado="missed", atendida=False)).status_code == 200
    itens = cli.get(f"{B}/needs-attention").json()
    perdida = [i for i in itens if i["entity"]["type"] == "call"]
    assert len(perdida) == 1 and perdida[0]["level"] == "HIGH" and "ligou e ninguém atendeu" in perdida[0]["title"]

    cid = perdida[0]["entity"]["id"]
    assert cli.post(f"{B}/dialpad/calls/{cid}/handled", json={"handled": True}, headers=h).status_code == 200
    assert not [i for i in cli.get(f"{B}/needs-attention").json() if i["entity"]["type"] == "call"]


def test_leitura_nao_trata_e_nao_disca(cli):
    h = entra(cli, "leitor@urace.us")
    assert cli.post(f"{B}/dialpad/webhook?key={CHAVE}", json=evento(call_id="c-v", estado="missed", atendida=False)).status_code == 200
    cid = um(conectar(), "SELECT id FROM calls WHERE external_id='c-v'")["id"]
    assert cli.post(f"{B}/dialpad/calls/{cid}/handled", json={"handled": True}, headers=h).status_code == 403
    assert cli.post(f"{B}/dialpad/call", json={"numero": "+13055550142"}, headers=h).status_code == 403


def test_discar_sem_credencial_diz_o_que_falta(cli):
    h = entra(cli)
    r = cli.post(f"{B}/dialpad/call", json={"numero": "+13055550142"}, headers=h)
    assert r.status_code == 409 and "DIALPAD_API_KEY" in r.json()["detail"]


def test_status_nao_inventa_conexao(cli):
    entra(cli)
    s = cli.get(f"{B}/dialpad/status").json()
    assert s["connected"] is False and "DIALPAD_API_KEY" in s["falta"]
    assert s["webhook_url"].endswith(f"?key={CHAVE}") and s["assinado"] is True


def test_politica_de_discar_e_confirmacao_obrigatoria(cli):
    con = conectar()
    p = um(con, "SELECT policy FROM action_policies WHERE action='dialpad_ligar'")
    assert p and p["policy"] == "REQUIRES_CONFIRMATION"
    con.close()

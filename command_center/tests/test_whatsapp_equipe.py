"""Ponte do chat da equipe com o WhatsApp (dono, 30/09).

O painel manda para o time interno pelo WhatsApp — sem aprovação, só para quem está
cadastrado — e a resposta volta para a mesma conversa. API oficial da Meta, número próprio
(nunca o do Kommo), e simulação até liberar.
"""
import hashlib
import hmac
import json
import os
import tempfile
import time

import pytest

os.environ["URACE_ENV"] = "/nao/existe"
os.environ["WA_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, todos, um  # noqa: E402
from command_center.providers import whatsapp as wa  # noqa: E402

SENHA = "senha-forte-123"
SEGREDO = "segredo-do-app-de-teste"
W = "/ops/api/whatsapp"


@pytest.fixture(autouse=True)
def sem_whatsapp_de_verdade(monkeypatch):
    for k in ("WA_TOKEN", "WA_PHONE_NUMBER_ID", "WA_APLICAR", "WA_TEMPLATE", "WA_VERIFY_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("WA_APP_SECRET", SEGREDO)
    monkeypatch.setattr(wa, "_post", lambda corpo: pytest.fail("nada pode sair sem liberar"))


def _liberar(monkeypatch, enviados):
    monkeypatch.setenv("WA_TOKEN", "t"); monkeypatch.setenv("WA_PHONE_NUMBER_ID", "123"); monkeypatch.setenv("WA_APLICAR", "1")

    def post(corpo):
        enviados.append(corpo)
        return {"messages": [{"id": f"wamid.{len(enviados)}"}]}
    monkeypatch.setattr(wa, "_post", post)


# ------------------------------------------------------------------ provider
@pytest.mark.parametrize("entrada,saida", [("+1 (407) 555-1234", "14075551234"), ("4075551234", "14075551234"),
                                           ("+55 11 91234-5678", "5511912345678")])
def test_telefone_vira_digitos_com_ddi(entrada, saida):
    assert wa.normaliza_fone(entrada) == saida


def test_assinatura_do_webhook():
    corpo = b'{"x":1}'
    boa = "sha256=" + hmac.new(SEGREDO.encode(), corpo, hashlib.sha256).hexdigest()
    assert wa.assinatura_ok(corpo, boa)
    assert not wa.assinatura_ok(corpo, "sha256=" + "0" * 64)
    assert not wa.assinatura_ok(corpo, None)


def test_sem_segredo_nenhum_webhook_passa(monkeypatch):
    monkeypatch.delenv("WA_APP_SECRET", raising=False)
    corpo = b"{}"
    assert not wa.assinatura_ok(corpo, "sha256=" + hmac.new(b"", corpo, hashlib.sha256).hexdigest())


def test_sem_liberar_e_simulacao():
    assert wa.enviar_texto("4075551234", "oi")["simulado"]


# ------------------------------------------------------------------ API
@pytest.fixture(scope="module")
def cli():
    pasta = tempfile.mkdtemp()
    os.environ["CC_DB_PATH"] = os.path.join(pasta, "cc.sqlite")
    os.environ["URACE_DIR"] = pasta
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "op@urace.us", "Operador Silva", "OPERATOR", SENHA)
    auth.criar_usuario(c, "ger@urace.us", "Italo Silveira", "MANAGER", SENHA)
    c.close()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def _novo(cli, nome, fone, funcao="mecânico"):
    h = entra(cli, "ger@urace.us")
    r = cli.post(f"{W}/contatos", headers=h, json={"name": nome, "funcao": funcao, "phone": fone})
    assert r.status_code == 201, r.text
    return r.json()


def _assinado(cli, dados):
    corpo = json.dumps(dados).encode()
    sig = "sha256=" + hmac.new(SEGREDO.encode(), corpo, hashlib.sha256).hexdigest()
    return cli.post(f"{W}/webhook", content=corpo, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})


def _entrada(fone, texto, wamid, ts=None):
    return {"entry": [{"changes": [{"value": {"messages": [
        {"from": fone, "id": wamid, "timestamp": str(ts or int(time.time())), "type": "text", "text": {"body": texto}}]}}]}]}


def _status(wamid, st):
    return {"entry": [{"changes": [{"value": {"statuses": [{"id": wamid, "status": st}]}}]}]}


def _escreve(cli, cid, texto):
    h = entra(cli, "ger@urace.us")
    r = cli.post(f"/ops/api/equipe/canais/{cid}/mensagens", headers=h, json={"text": texto})
    assert r.status_code == 201, r.text
    return um(conectar(), "SELECT * FROM team_messages WHERE id=?", (r.json()["id"],))


def test_cadastro_e_do_gerente(cli):
    h = entra(cli, "op@urace.us")
    assert cli.post(f"{W}/contatos", headers=h, json={"name": "X", "phone": "4075550000"}).status_code == 403
    c = _novo(cli, "Eduardo", "+1 407 555 0101")
    canal = um(conectar(), "SELECT * FROM team_channels WHERE id=?", (c["channel_id"],))
    assert canal["bridge"] == "whatsapp" and canal["bridge_id"] == "14075550101"
    h = entra(cli, "ger@urace.us")
    assert cli.post(f"{W}/contatos", headers=h, json={"name": "Dup", "phone": "407-555-0101"}).status_code == 409
    assert cli.post(f"{W}/contatos", headers=h, json={"name": "Ruim", "phone": "123"}).status_code == 400


def test_sem_numero_configurado_a_mensagem_fica_como_simulacao(cli):
    c = _novo(cli, "Coach Rafa", "4075550102", "coach")
    m = _escreve(cli, c["channel_id"], "Treino amanhã às 9h")
    assert m["wa_status"] == "simulado" and "simulação" in m["wa_error"]


def test_dentro_da_janela_sai_como_texto_assinado_com_o_nome(cli, monkeypatch):
    c = _novo(cli, "Mec Joao", "4075550103")
    assert _assinado(cli, _entrada("14075550103", "oi, chegou a peça?", "wamid.in1")).status_code == 200
    enviados = []
    _liberar(monkeypatch, enviados)
    m = _escreve(cli, c["channel_id"], "Chegou sim, está na prateleira A")
    assert m["wa_status"] == "enviado" and m["external_id"] == "wamid.1"
    assert enviados[0]["type"] == "text" and enviados[0]["to"] == "14075550103"
    assert enviados[0]["text"]["body"] == "*Italo:* Chegou sim, está na prateleira A", "sai como uma pessoa"


def test_fora_da_janela_sem_template_nao_finge_que_enviou(cli, monkeypatch):
    c = _novo(cli, "Adm Carla", "4075550104", "administrativo")
    _liberar(monkeypatch, [])
    m = _escreve(cli, c["channel_id"], "Pode fechar o caixa?")
    assert m["wa_status"] == "fora_da_janela" and "24 h" in m["wa_error"]


def test_fora_da_janela_com_template_aprovado(cli, monkeypatch):
    c = _novo(cli, "Mec Pedro", "4075550105")
    enviados = []
    _liberar(monkeypatch, enviados)
    monkeypatch.setenv("WA_TEMPLATE", "aviso_equipe")
    m = _escreve(cli, c["channel_id"], "Kart 12 sai às 15h")
    assert m["wa_status"] == "enviado"
    t = enviados[0]["template"]
    assert t["name"] == "aviso_equipe" and t["language"]["code"] == "pt_BR"
    assert [p["text"] for p in t["components"][0]["parameters"]] == ["Italo", "Kart 12 sai às 15h"]


def test_resposta_volta_para_a_conversa_sem_duplicar(cli):
    c = _novo(cli, "Mec Lucas", "4075550106")
    for _ in range(2):                                  # a Meta reentrega: não pode duplicar
        assert _assinado(cli, _entrada("14075550106", "feito, kart pronto", "wamid.lucas1")).json()["ok"]
    msgs = todos(conectar(), "SELECT * FROM team_messages WHERE channel_id=?", (c["channel_id"],))
    assert [(m["author"], m["text"], m["origem"]) for m in msgs] == [("Mec Lucas", "feito, kart pronto", "whatsapp")]
    ct = um(conectar(), "SELECT last_inbound_at FROM team_contacts WHERE phone='14075550106'")
    assert ct["last_inbound_at"], "a janela de 24 h abriu"


def test_numero_desconhecido_nao_vira_conversa(cli):
    antes = um(conectar(), "SELECT COUNT(*) n FROM team_messages")["n"]
    assert _assinado(cli, _entrada("15550009999", "sou um estranho", "wamid.x")).json()["mensagens"] == 0
    assert um(conectar(), "SELECT COUNT(*) n FROM team_messages")["n"] == antes
    assert um(conectar(), "SELECT 1 AS x FROM audit_logs WHERE event='whatsapp.desconhecido'")


def test_webhook_sem_assinatura_certa_e_recusado(cli):
    r = cli.post(f"{W}/webhook", content=json.dumps(_entrada("14075550106", "falso", "wamid.f")).encode(),
                 headers={"X-Hub-Signature-256": "sha256=" + "0" * 64})
    assert r.status_code == 403


def test_status_so_anda_para_frente(cli, monkeypatch):
    c = _novo(cli, "Mec Ana", "4075550107")
    _assinado(cli, _entrada("14075550107", "oi", "wamid.ana1"))
    _liberar(monkeypatch, [])
    m = _escreve(cli, c["channel_id"], "tudo certo?")
    for st in ("delivered", "read", "delivered"):
        _assinado(cli, _status(m["external_id"], st))
    assert um(conectar(), "SELECT wa_status FROM team_messages WHERE id=?", (m["id"],))["wa_status"] == "lido"


def test_verificacao_do_webhook_pela_meta(cli, monkeypatch):
    assert cli.get(f"{W}/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "42"}).status_code == 403
    monkeypatch.setenv("WA_VERIFY_TOKEN", "combinado")
    r = cli.get(f"{W}/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "combinado", "hub.challenge": "42"})
    assert r.status_code == 200 and r.text == "42"


def test_contato_desativado_nao_recebe(cli, monkeypatch):
    c = _novo(cli, "Ex Mec", "4075550108")
    h = entra(cli, "ger@urace.us")
    ctid = um(conectar(), "SELECT id FROM team_contacts WHERE phone='14075550108'")["id"]
    assert cli.patch(f"{W}/contatos/{ctid}", headers=h, json={"active": False}).status_code == 200
    assert um(conectar(), "SELECT archived_at FROM team_channels WHERE id=?", (c["channel_id"],))["archived_at"]
    _liberar(monkeypatch, [])
    m = _escreve(cli, c["channel_id"], "ainda está aí?")
    assert m["wa_status"] == "falhou"


def test_lista_mostra_a_janela(cli):
    h = entra(cli, "op@urace.us")
    d = cli.get(f"{W}/contatos", headers=h).json()
    por = {c["name"]: c for c in d["contatos"]}
    assert por["Mec Lucas"]["janela_aberta"] and not por["Adm Carla"]["janela_aberta"]
    assert d["configurado"] is False and "WA_TOKEN" not in json.dumps(d)

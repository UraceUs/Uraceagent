"""O chat do Kommo que para de receber — e ninguém percebe.

Sintoma do dono em 21/09: *"tava respondendo pelo dashboard usando o chat e algumas msgs
não foram e outras não chegaram"*. A metade que "não chegou" é esta: o Kommo desliga o
webhook depois de falhas seguidas, o painel continua bonito e mudo, e quem escreveu fica
sem resposta. Banco próprio porque o aviso olha o último webhook do banco inteiro.
"""
import os
import tempfile

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import agora, aplicar_schema, auditar, conectar, inserir  # noqa: E402

B = "/ops/api"
SENHA = "senha-forte-123"


@pytest.fixture()
def cli():
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc.sqlite")
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "admin@urace.us", "Admin", "ADMIN", SENHA)
    inserir(con, "crm_leads", external_id="e1", name="Maria Souza", contact_name="Maria",
            last_message_at=agora(), needs_reply=1)
    con.commit(); con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        assert c.post(B + "/auth/login", json={"email": "admin@urace.us", "password": SENHA}).status_code == 200
        yield c


def _mudo(cli):
    return [i for i in cli.get(B + "/needs-attention").json() if "parou de receber" in i["title"]]


def test_avisa_quando_o_kommo_para_de_mandar_aviso(cli):
    item = _mudo(cli)
    assert item and item[0]["level"] == "CRITICAL"
    assert "sem resposta" in item[0]["why"]
    assert any("Kommo → Settings → Webhooks" in f[1] for f in item[0]["facts"])


def test_com_webhook_recente_o_painel_fica_quieto(cli):
    con = conectar()
    auditar(con, "crm.webhook", "kommo", detail={"msgs": 1})
    con.commit(); con.close()
    assert not _mudo(cli)


def test_sem_conversa_nenhuma_nao_ha_o_que_avisar(cli):
    con = conectar()
    con.execute("UPDATE crm_leads SET last_message_at = NULL")
    con.commit(); con.close()
    assert not _mudo(cli)

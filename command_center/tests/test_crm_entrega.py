"""Garantir a entrega: a fila insiste sozinha e o Kommo dá o recibo.

Dono, 21/09: *"eu não quero esperar que não vá, preciso corrigir e garantir que todas
cheguem e sejam enviadas tb"*. Então o que se prova aqui:

1. falha passageira NÃO mata a mensagem — ela fica na fila e o laço insiste;
2. erro permanente (bot desligado) volta na cara de quem escreveu, porque insistir seria mentira;
3. o eco do Kommo vira RECIBO na mensagem original, em vez de ser descartado;
4. quem não tem recibo depois do prazo acende aviso — mas só se esta conta der recibo.

Banco próprio: a fila é estado do módulo inteiro.
"""
import os
import tempfile

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import atencao, auth, crm  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import agora, aplicar_schema, conectar, inserir, todos, um  # noqa: E402

B = "/ops/api"
SENHA = "senha-forte-123"


class BotFalso:
    """O Salesbot: pode estar fora do ar, pode recusar de vez, pode atender."""

    def __init__(self):
        self.runs, self.entregas = [], []
        self.fora_do_ar = False
        self.recusa_de_vez = False

    def abrir_canal_humano(self, lead_id, bot_id=None):
        if self.recusa_de_vez:
            raise RuntimeError("RECUSADO: sem KOMMO_BOT_ID no ~/.urace/kommo.env")
        if self.fora_do_ar:
            raise RuntimeError("HTTP 502 do Kommo")
        self.runs.append(str(lead_id))
        return {"aplicado": True, "lead_id": str(lead_id)}

    def continuar_bot_humano(self, return_url, texto):
        self.entregas.append((return_url, texto))
        return True, "202"

    def nota_humana(self, lead_id, texto):
        return {"aplicado": True, "nota_id": "n1"}


@pytest.fixture()
def cli(monkeypatch):
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc.sqlite")
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "op@urace.us", "Op", "OPERATOR", SENHA)
    inserir(con, "crm_leads", external_id="8001", name="Charles", source="Instagram", synced_at=agora())
    con.commit(); con.close()
    bot = BotFalso()
    monkeypatch.setattr(crm, "modulo", lambda s: bot)
    with TestClient(app, base_url="https://cc.test") as c:
        c.bot = bot
        yield c


def entra(cli):
    cli.cookies.clear()
    assert cli.post(f"{B}/auth/login", json={"email": "op@urace.us", "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def lead_id(con):
    return um(con, "SELECT id FROM crm_leads WHERE external_id='8001'")["id"]


# ------------------------------------------------------------------ a fila insiste
def test_kommo_fora_do_ar_nao_mata_a_mensagem(cli):
    """O que matava resposta boa: uma piscada de rede na primeira tentativa."""
    cli.bot.fora_do_ar = True
    h = entra(cli)
    con = conectar(); lid = lead_id(con)
    r = cli.post(f"{B}/crm/leads/{lid}/reply", headers=h, json={"text": "Hey Charles"})
    assert r.status_code == 200 and r.json()["como"] == "fila"
    m = um(con, "SELECT * FROM crm_messages WHERE lead_id=? AND direction='saida'", (lid,))
    assert m["status"] == "queued" and m["tentativas"] == 1 and "502" in m["error"]

    # o laço passa de novo, o Kommo voltou: a mensagem sai
    cli.bot.fora_do_ar = False
    con.execute("UPDATE crm_messages SET ultima_tentativa='2020-01-01T00:00:00Z' WHERE id=?", (m["id"],))
    con.commit()
    assert crm.empurrar_fila(con)["cutucados"] == 1 and cli.bot.runs == ["8001"]
    assert um(con, "SELECT tentativas FROM crm_messages WHERE id=?", (m["id"],))["tentativas"] == 2
    con.close()


def test_nao_cutuca_o_bot_a_cada_segundo(cli):
    """Insistir não é martelar: uma cutucada por minuto, por lead."""
    cli.bot.fora_do_ar = True
    h = entra(cli)
    con = conectar(); lid = lead_id(con)
    cli.post(f"{B}/crm/leads/{lid}/reply", headers=h, json={"text": "oi"})
    cli.bot.fora_do_ar = False
    assert crm.empurrar_fila(con)["cutucados"] == 0        # acabou de tentar
    assert cli.bot.runs == []
    con.close()


def test_bot_desligado_volta_na_cara_de_quem_escreveu(cli):
    """Insistir com "sem KOMMO_BOT_ID" seria enganar: aquilo nunca vai sair."""
    cli.bot.recusa_de_vez = True
    h = entra(cli)
    con = conectar(); lid = lead_id(con)
    r = cli.post(f"{B}/crm/leads/{lid}/reply", headers=h, json={"text": "oi"})
    assert r.status_code == 502 and "KOMMO_BOT_ID" in r.json()["detail"]
    assert um(con, "SELECT status FROM crm_messages WHERE lead_id=?", (lid,))["status"] == "failed"
    con.close()


def test_desiste_so_depois_do_prazo_e_grava_nota_no_lead(cli):
    h = entra(cli)
    con = conectar(); lid = lead_id(con)
    cli.bot.fora_do_ar = True
    cli.post(f"{B}/crm/leads/{lid}/reply", headers=h, json={"text": "some?"})
    assert crm.varrer_fila(con) == 0                       # ainda dentro do prazo: não desiste
    con.execute("UPDATE crm_messages SET at='2020-01-01T00:00:00' WHERE lead_id=?", (lid,))
    con.commit()
    assert crm.varrer_fila(con) == 1
    m = um(con, "SELECT * FROM crm_messages WHERE lead_id=?", (lid,))
    assert m["status"] == "failed" and "tentativa" in m["error"] and "nota no lead" in m["error"]
    con.close()


# ------------------------------------------------------------------ o recibo
def test_eco_do_kommo_vira_recibo_da_mensagem(cli):
    """Antes o eco era descartado. Ele é a única prova de que a mensagem apareceu no chat."""
    con = conectar(); lid = lead_id(con)
    mid = inserir(con, "crm_messages", lead_id=lid, direction="saida", status="sent",
                  author="Italo", text="Hey Charles", at=agora(), source="painel")
    con.commit()
    assert crm.confirmar_entrega(con, lid, "Hey Charles", agora()) is True
    con.commit()
    m = um(con, "SELECT * FROM crm_messages WHERE id=?", (mid,))
    assert m["confirmado_em"] and m["status"] == "sent"
    # o mesmo eco de novo não reescreve nada (já tem recibo)
    assert crm.confirmar_entrega(con, lid, "Hey Charles", agora()) is False
    con.close()


def test_recibo_de_texto_que_o_painel_nao_mandou_nao_carimba_nada(cli):
    con = conectar(); lid = lead_id(con)
    inserir(con, "crm_messages", lead_id=lid, direction="saida", status="sent",
            author="Italo", text="uma coisa", at=agora(), source="painel")
    con.commit()
    assert crm.confirmar_entrega(con, lid, "outra coisa bem diferente", agora()) is False
    con.close()


def test_so_cobra_recibo_de_conta_que_da_recibo(cli):
    """A trava da conferência, aplicada aqui: não acusar onde não se enxerga."""
    from datetime import datetime, timedelta, timezone
    con = conectar(); lid = lead_id(con)
    # passou do prazo de recibo (10 min), mas ainda dentro da janela que o painel olha
    meia_hora = (datetime.now(timezone.utc) - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    inserir(con, "crm_messages", lead_id=lid, direction="saida", status="sent",
            author="Italo", text="sem recibo", at=meia_hora, source="painel")
    con.commit()
    assert crm.confirmacao_confiavel(con) is False
    assert not [i for i in atencao._coletar(con) if i["key"].startswith("crm-sem-recibo")]

    # agora a conta passa a dar recibo: a mensagem sem confirmação vira aviso
    inserir(con, "crm_messages", lead_id=lid, direction="saida", status="sent", author="Italo",
            text="com recibo", at=agora(), source="painel", confirmado_em=agora())
    con.commit()
    assert crm.confirmacao_confiavel(con) is True
    avisos = [i for i in atencao._coletar(con) if i["key"].startswith("crm-sem-recibo")]
    assert avisos and "Charles" in avisos[0]["title"]
    con.close()

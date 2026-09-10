"""CRM (Kommo) no Command Center: funil espelhado, conversa, resposta humana e webhook.

Nada aqui toca no Kommo de verdade: o módulo do MCP é falso e conta o que foi
chamado — inclusive se APLICAR estava ligado (porta humana) na hora.
"""
import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from command_center.api import auth, crm
from command_center.api.main import app
from command_center.db import aplicar_schema, conectar, inserir, todos, um

B = "/ops/api"
SENHA = "senha-forte-123"


@pytest.fixture(scope="module")
def cli():
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc-crm.sqlite")
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "admin@urace.us", "Admin", "ADMIN", SENHA)
    auth.criar_usuario(con, "op@urace.us", "Op", "OPERATOR", SENHA)
    auth.criar_usuario(con, "leitor@urace.us", "Leitor", "VIEWER", SENHA)
    con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def entra(cli, email):
    assert cli.post(B + "/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


LEADS = [{
    "id": "5001", "nome": "Maria Souza — aula experimental", "valor": 500.0,
    "funil_id": "9903543", "funil": "Sales funnel", "etapa_id": "76050835", "etapa": "Leads de entrada", "ordem": 1,
    "tags": ["instagram"], "responsavel_id": "77", "origem": "Instagram", "campos": {},
    "criado_em": "2026-09-08T12:00:00Z", "atualizado_em": "2026-09-09T15:00:00Z",
    "contato": {"id": "9", "nome": "Maria Souza", "email": "maria@exemplo.com", "telefone": "+1 407 555 0101"},
    "link": "https://urace.kommo.com/leads/detail/5001",
}]
FUNIS = [{"id": "9903543", "nome": "Sales funnel", "principal": True, "etapas": [
    {"id": "76050835", "nome": "Leads de entrada", "ordem": 1},
    {"id": "105276412", "nome": "First Contact", "ordem": 2}]}]
CONVERSA = [{"id": "n1", "tipo": "chat_message", "direcao": "entrada", "quem": "Maria",
             "texto": "Oi! Quanto custa a aula experimental?", "em": "2026-09-09T15:00:00Z"}]


class KommoFalso:
    """Portas humanas do MCP. Guarda o APLICAR de cada chamada: escrita só com 1."""

    def __init__(self):
        self.feito = []

    def mover_etapa_humano(self, lead_id, etapa_id, funil_id=None):
        self.feito.append(("mover", lead_id, etapa_id, os.environ.get("APLICAR")))
        return {"aplicado": True, "lead_id": lead_id, "etapa_id": etapa_id, "etapa": "First Contact"}

    def marcar_tag_humano(self, lead_id, tags):
        self.feito.append(("tag", lead_id, tuple(tags), os.environ.get("APLICAR")))
        return {"aplicado": True, "tags": ["instagram"] + list(tags), "novas": list(tags)}

    def nota_humana(self, lead_id, texto):
        self.feito.append(("nota", lead_id, texto, os.environ.get("APLICAR")))
        return {"aplicado": True, "nota_id": "n99"}

    def responder_humano(self, lead_id, texto, bot_id=None):
        self.feito.append(("responder", lead_id, texto, os.environ.get("APLICAR")))
        return {"aplicado": True, "bot_id": "162247", "aviso": "sai como mensagem do bot"}


@pytest.fixture
def kommo(monkeypatch):
    k = KommoFalso()
    monkeypatch.setattr(crm, "modulo", lambda s: k)
    monkeypatch.setattr(crm, "chamar", lambda s, f, **a: {"kommo_conversa": CONVERSA, "kommo_funis": FUNIS}[f])
    monkeypatch.setenv("KOMMO_BOT_ID", "162247")
    return k


def test_sync_espelha_o_funil_e_liga_ao_card_do_cliente(cli, monkeypatch):
    from command_center.providers import sync
    con = conectar()
    try:
        cid = inserir(con, "clients", name="Maria Souza", pilot_name="Pedro Souza", status="NEW", email="maria@exemplo.com")
        con.commit()
        monkeypatch.setattr(sync, "chamar", lambda s, f, **a: {"kommo_funis": FUNIS, "kommo_leads": LEADS,
                                                              "kommo_conversa": CONVERSA}[f])
        r = sync.sync_kommo(con)
        assert r["ok"] and r["leads"] == 1 and r["ligados"] == 1
        l = um(con, "SELECT * FROM crm_leads WHERE external_id='5001'")
        assert l["client_id"] == cid and l["stage_name"] == "Leads de entrada" and l["source"] == "Instagram"
        assert json.loads(l["tags"]) == ["instagram"] and l["contact_phone"] == "+1 407 555 0101"
        assert l["needs_reply"] == 1 and l["last_message_at"] == "2026-09-09T15:00:00Z"   # cliente falou por último
        assert um(con, "SELECT COUNT(*) AS n FROM crm_messages WHERE lead_id=?", (l["id"],))["n"] == 1
        sync.sync_kommo(con)                                    # de novo: não duplica lead nem mensagem
        assert um(con, "SELECT COUNT(*) AS n FROM crm_leads")["n"] == 1
        assert um(con, "SELECT COUNT(*) AS n FROM crm_messages")["n"] == 1
        assert um(con, "SELECT status FROM integrations WHERE system='kommo'")["status"] == "CONNECTED"
    finally:
        con.close()


def test_board_mostra_o_funil_em_colunas(cli, kommo):
    h = entra(cli, "admin@urace.us")
    b = cli.get(f"{B}/crm/board", headers=h).json()
    assert b["total"] == 1 and b["pendentes"] == 1
    f = b["funis"][0]
    assert f["nome"] == "Sales funnel" and f["etapas"][0]["nome"] == "Leads de entrada"
    l = f["etapas"][0]["leads"][0]
    assert l["source"] == "Instagram" and l["tags"] == ["instagram"] and l["client_pilot"] == "Pedro Souza"
    assert l["link"].endswith("/leads/detail/5001")             # o link fica no item, não numa fila no topo


def test_abrir_o_lead_traz_a_conversa_e_guarda_o_que_for_novo(cli, kommo):
    h = entra(cli, "admin@urace.us")
    con = conectar()
    try:
        lid = um(con, "SELECT id FROM crm_leads WHERE external_id='5001'")["id"]
    finally:
        con.close()
    d = cli.get(f"{B}/crm/leads/{lid}", headers=h).json()
    assert d["lead"]["contact_email"] == "maria@exemplo.com" and d["responder_habilitado"] is True
    assert [m["text"] for m in d["mensagens"]] == ["Oi! Quanto custa a aula experimental?"]
    assert d["aviso"] is None
    assert len(cli.get(f"{B}/crm/leads/{lid}", headers=h).json()["mensagens"]) == 1   # não repete


def test_mover_tag_nota_e_resposta_sao_atos_humanos_com_aplicar(cli, kommo):
    h = entra(cli, "op@urace.us")
    con = conectar()
    try:
        lid = um(con, "SELECT id FROM crm_leads WHERE external_id='5001'")["id"]
    finally:
        con.close()
    assert cli.post(f"{B}/crm/leads/{lid}/stage", headers=h, json={"stage_id": "105276412"}).status_code == 200
    assert cli.post(f"{B}/crm/leads/{lid}/tags", headers=h, json={"tags": ["quente"]}).status_code == 200
    assert cli.post(f"{B}/crm/leads/{lid}/note", headers=h, json={"text": "ligou, pediu domingo"}).status_code == 200
    r = cli.post(f"{B}/crm/leads/{lid}/reply", headers=h, json={"text": "Oi Maria! A experimental sai $500."})
    assert r.status_code == 200 and "bot" in r.json()["aviso"]
    assert [x[0] for x in kommo.feito] == ["mover", "tag", "nota", "responder"]
    assert all(x[-1] == "1" for x in kommo.feito)               # APLICAR ligado só na chamada
    assert os.environ.get("APLICAR") is None                    # e devolvido depois
    con = conectar()
    try:
        l = um(con, "SELECT * FROM crm_leads WHERE id=?", (lid,))
        assert l["stage_id"] == "105276412" and l["stage_name"] == "First Contact"
        assert "quente" in json.loads(l["tags"]) and l["needs_reply"] == 0
        msgs = todos(con, "SELECT direction, text FROM crm_messages WHERE lead_id=? ORDER BY id", (lid,))
        assert [m["direction"] for m in msgs] == ["entrada", "nota", "saida"]
        eventos = {a["event"] for a in todos(con, "SELECT event FROM audit_logs")}
        assert {"crm.stage", "crm.tags", "crm.note", "crm.reply"} <= eventos
    finally:
        con.close()


def test_sem_salesbot_a_resposta_e_recusada_com_explicacao(cli, monkeypatch):
    """Melhor não responder do que fingir que respondeu."""
    from mcp_stdio import ErroFerramenta

    class SemBot:
        def responder_humano(self, lead_id, texto, bot_id=None):
            raise ErroFerramenta("RECUSADO: sem KOMMO_BOT_ID não dá para entregar a mensagem no chat do Kommo.")
    monkeypatch.setattr(crm, "modulo", lambda s: SemBot())
    h = entra(cli, "op@urace.us")
    con = conectar()
    try:
        lid = um(con, "SELECT id FROM crm_leads WHERE external_id='5001'")["id"]
    finally:
        con.close()
    r = cli.post(f"{B}/crm/leads/{lid}/reply", headers=h, json={"text": "oi"})
    assert r.status_code == 502 and "KOMMO_BOT_ID" in r.json()["detail"]


def test_leitor_nao_escreve_no_crm(cli, kommo):
    h = entra(cli, "leitor@urace.us")
    con = conectar()
    try:
        lid = um(con, "SELECT id FROM crm_leads WHERE external_id='5001'")["id"]
    finally:
        con.close()
    assert cli.get(f"{B}/crm/board", headers=h).status_code == 200
    for caminho, corpo in (("stage", {"stage_id": "1"}), ("tags", {"tags": ["x"]}),
                           ("note", {"text": "x"}), ("reply", {"text": "x"})):
        assert cli.post(f"{B}/crm/leads/{lid}/{caminho}", headers=h, json=corpo).status_code == 403


def test_webhook_so_com_segredo_e_marca_que_espera_resposta(cli, monkeypatch):
    monkeypatch.setenv("KOMMO_WEBHOOK_SECRET", "segredo-de-teste")
    corpo = {"lead_id": "5001", "text": "Consegue domingo?", "message_id": "m2", "author": "Maria"}
    assert cli.post(f"{B}/crm/webhook", json=corpo).status_code == 403
    assert cli.post(f"{B}/crm/webhook", json=corpo, headers={"X-Urace-Secret": "errado"}).status_code == 403
    r = cli.post(f"{B}/crm/webhook", json=corpo, headers={"X-Urace-Secret": "segredo-de-teste"})
    assert r.status_code == 200
    con = conectar()
    try:
        l = um(con, "SELECT * FROM crm_leads WHERE external_id='5001'")
        assert l["needs_reply"] == 1
        assert um(con, "SELECT text FROM crm_messages WHERE external_id='m2'")["text"] == "Consegue domingo?"
        # lead que ainda não veio na sincronia entra pelo webhook, sem inventar cliente
        cli.post(f"{B}/crm/webhook", json={"lead_id": "9999", "text": "oi", "source": "WhatsApp"},
                 headers={"X-Urace-Secret": "segredo-de-teste"})
        novo = um(con, "SELECT * FROM crm_leads WHERE external_id='9999'")
        assert novo["client_id"] is None and novo["source"] == "WhatsApp"
    finally:
        con.close()


def test_sem_credencial_o_crm_nao_derruba_a_tela(cli, monkeypatch):
    from command_center.providers import NaoConectado, sync
    monkeypatch.setattr(sync, "chamar", lambda *a, **k: (_ for _ in ()).throw(NaoConectado("sem KOMMO_TOKEN")))
    con = conectar()
    try:
        assert sync.sync_kommo(con)["ok"] is False
        assert um(con, "SELECT status FROM integrations WHERE system='kommo'")["status"] == "DISCONNECTED"
    finally:
        con.close()
    monkeypatch.setattr(crm, "chamar", lambda *a, **k: (_ for _ in ()).throw(NaoConectado("sem KOMMO_TOKEN")))
    h = entra(cli, "admin@urace.us")
    con = conectar()
    try:
        lid = um(con, "SELECT id FROM crm_leads WHERE external_id='5001'")["id"]
    finally:
        con.close()
    d = cli.get(f"{B}/crm/leads/{lid}", headers=h).json()
    assert "não conectado" in (d["aviso"] or "") and len(d["mensagens"]) >= 1    # mostra o que já tinha
    assert cli.get(f"{B}/crm/stages", headers=h).status_code == 503


def test_resposta_pelo_salesbot_diz_a_verdade_sobre_quem_escolhe_o_texto(monkeypatch):
    """O bot manda o que ELE está configurado para mandar. Com KOMMO_CAMPO_RESPOSTA o
    painel grava o texto no campo que o bot envia; sem o campo, avisa em vez de deixar
    o dono achar que o cliente leu o que ele escreveu."""
    import kommo_mcp as k
    chamadas = []
    monkeypatch.setattr(k, "_req", lambda c, m="GET", corpo=None, params=None: chamadas.append((m, c, corpo)) or {})
    monkeypatch.setenv("KOMMO_DOMAIN", "urace.kommo.com")
    monkeypatch.setenv("KOMMO_TOKEN", "t")
    monkeypatch.setenv("KOMMO_BOT_ID", "162247")
    monkeypatch.delenv("KOMMO_CAMPO_RESPOSTA", raising=False)
    monkeypatch.setenv("APLICAR", "1")
    r = k.responder_humano("5001", "A experimental sai $500.")
    assert r["aplicado"] and "ROTEIRO DO BOT" in r["aviso"] and r["campo"] is None
    assert [c[1] for c in chamadas] == ["/leads/5001/notes", "/bots/162247/run"]
    chamadas.clear()
    monkeypatch.setenv("KOMMO_CAMPO_RESPOSTA", "998877")
    r = k.responder_humano("5001", "A experimental sai $500.")
    assert r["campo"] == "998877" and "ROTEIRO" not in r["aviso"]
    assert chamadas[0][1] == "/leads/5001" and chamadas[0][2]["custom_fields_values"][0]["field_id"] == 998877
    assert chamadas[0][2]["custom_fields_values"][0]["values"][0]["value"] == "A experimental sai $500."
    # sem bot: recusa, e nada é chamado
    chamadas.clear()
    monkeypatch.delenv("KOMMO_BOT_ID")
    with pytest.raises(Exception) as e:
        k.responder_humano("5001", "oi")
    assert "KOMMO_BOT_ID" in str(e.value) and chamadas == []


def test_escrita_no_kommo_e_simulacao_sem_aplicar(monkeypatch):
    """APLICAR=0 (padrão) não escreve nada no CRM: só diz o que teria feito."""
    import kommo_mcp as k
    chamadas = []
    monkeypatch.setattr(k, "_req", lambda c, m="GET", corpo=None, params=None: chamadas.append((m, c)) or {})
    monkeypatch.setattr(k, "_nome_etapa", lambda f, e: ("Sales funnel", "First Contact", 2))
    monkeypatch.setenv("KOMMO_DOMAIN", "urace.kommo.com")
    monkeypatch.setenv("KOMMO_TOKEN", "t")
    monkeypatch.setenv("KOMMO_BOT_ID", "162247")
    monkeypatch.delenv("APLICAR", raising=False)
    assert k.mover_etapa_humano("5001", "105276412", "9903543")["aplicado"] is False
    assert k.nota_humana("5001", "teste")["aplicado"] is False
    assert k.responder_humano("5001", "teste")["aplicado"] is False
    assert chamadas == []
    assert not hasattr(k, "apagar_lead") and not hasattr(k, "apagar_humano")   # não existe porta de apagar

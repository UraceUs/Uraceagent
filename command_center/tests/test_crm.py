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

    def abrir_canal_humano(self, lead_id, bot_id=None):
        self.feito.append(("abrir", lead_id, None, os.environ.get("APLICAR")))
        return {"aplicado": True, "bot_id": "162247"}


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
    assert r.status_code == 200 and r.json()["como"] == "bot disparado" and "fila" in r.json()["aviso"]
    assert [x[0] for x in kommo.feito] == ["mover", "tag", "nota", "abrir"]
    assert all(x[-1] == "1" for x in kommo.feito)               # APLICAR ligado só na chamada
    assert os.environ.get("APLICAR") is None                    # e devolvido depois
    con = conectar()
    try:
        l = um(con, "SELECT * FROM crm_leads WHERE id=?", (lid,))
        assert l["stage_id"] == "105276412" and l["stage_name"] == "First Contact"
        assert "quente" in json.loads(l["tags"])
        msgs = todos(con, "SELECT direction, text, status FROM crm_messages WHERE lead_id=? ORDER BY id", (lid,))
        assert [m["direction"] for m in msgs] == ["entrada", "nota", "saida"] and msgs[-1]["status"] == "queued"
        con.execute("DELETE FROM crm_messages WHERE lead_id=? AND status='queued'", (lid,)); con.commit()   # limpa para os testes do chat
        eventos = {a["event"] for a in todos(con, "SELECT event FROM audit_logs")}
        assert {"crm.stage", "crm.tags", "crm.note", "crm.reply"} <= eventos
    finally:
        con.close()


def test_sem_salesbot_a_resposta_e_recusada_com_explicacao(cli, monkeypatch):
    """Melhor não responder do que fingir que respondeu."""
    from mcp_stdio import ErroFerramenta

    class SemBot:
        def abrir_canal_humano(self, lead_id, bot_id=None):
            raise ErroFerramenta("RECUSADO: sem KOMMO_BOT_ID não dá para reabrir o chat do lead.")
    monkeypatch.setattr(crm, "modulo", lambda s: SemBot())
    h = entra(cli, "op@urace.us")
    con = conectar()
    try:
        lid = um(con, "SELECT id FROM crm_leads WHERE external_id='5001'")["id"]
    finally:
        con.close()
    r = cli.post(f"{B}/crm/leads/{lid}/reply", headers=h, json={"text": "oi"})
    assert r.status_code == 502 and "KOMMO_BOT_ID" in r.json()["detail"]
    con = conectar()
    try:                                                    # a mensagem fica marcada como falha, não some
        assert um(con, "SELECT status FROM crm_messages WHERE lead_id=? AND text='oi'", (lid,))["status"] == "failed"
        con.execute("DELETE FROM crm_messages WHERE lead_id=? AND text='oi'", (lid,)); con.commit()
    finally:
        con.close()


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


def test_portas_do_circuito_do_salesbot(monkeypatch):
    """Continuação só em HTTPS e só com APLICAR; reabrir o canal exige KOMMO_BOT_ID."""
    import kommo_mcp as k
    chamadas = []
    monkeypatch.setattr(k, "_req", lambda c, m="GET", corpo=None, params=None: chamadas.append((m, c, corpo)) or {})
    monkeypatch.setenv("KOMMO_DOMAIN", "urace.kommo.com"); monkeypatch.setenv("KOMMO_TOKEN", "t")
    monkeypatch.delenv("APLICAR", raising=False)
    ok, det = k.continuar_bot_humano("https://urace.kommo.com/api/v4/salesbot/1/continue/a", "oi")
    assert ok is False and "SIMULAÇÃO" in det
    assert k.continuar_bot_humano("http://inseguro/x", "oi")[1] == "return_url fora do padrão"
    assert k.continuar_bot_humano("https://x", "")[1] == "sem texto ou sem return_url"
    monkeypatch.delenv("KOMMO_BOT_ID", raising=False)
    with pytest.raises(Exception) as e:
        k.abrir_canal_humano("5001")
    assert "KOMMO_BOT_ID" in str(e.value) and chamadas == []
    monkeypatch.setenv("KOMMO_BOT_ID", "162247"); monkeypatch.setenv("APLICAR", "1")
    assert k.abrir_canal_humano("5001")["aplicado"] and chamadas[-1][1] == "/bots/162247/run" and chamadas[-1][2]["entity_type"] == "leads"


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


# ------------------------------------------------------------- o chat (hook, fila, entrega)
HOOK = ("data%5Bmessage%5D=Consegue+domingo%3F&data%5Blead_id%5D=5001&data%5Bcontact_name%5D=Maria+Souza"
        "&data%5Bcontact_phone%5D=%2B1+407+555+0101&return_url=https%3A%2F%2Furace.kommo.com%2Fapi%2Fv4%2Fsalesbot%2F162247%2Fcontinue%2Fabc")


class KommoChat:
    """Portas do circuito do Salesbot: continuação e bots/run, sem rede."""

    def __init__(self):
        self.entregas, self.runs, self.notas = [], [], []
        self.falhar_continue = False
    parse_corpo_hook = staticmethod(lambda b: __import__("kommo_mcp").parse_corpo_hook(b))
    extrair_entrada = staticmethod(lambda p: __import__("kommo_mcp").extrair_entrada(p))
    verificar_token_bot = staticmethod(lambda t: __import__("kommo_mcp").verificar_token_bot(t))

    def continuar_bot_humano(self, return_url, texto):
        self.entregas.append((return_url, texto, os.environ.get("APLICAR")))
        return (False, "o bot já não estava esperando (404)") if self.falhar_continue else (True, "202")

    def abrir_canal_humano(self, lead_id, bot_id=None):
        self.runs.append((lead_id, os.environ.get("APLICAR")))
        return {"aplicado": True, "lead_id": lead_id, "bot_id": "999"}

    def nota_humana(self, lead_id, texto):
        self.notas.append((lead_id, texto)); return {"aplicado": True, "nota_id": "n1"}


@pytest.fixture
def chat(monkeypatch):
    k = KommoChat()
    monkeypatch.setattr(crm, "modulo", lambda s: k)
    monkeypatch.setattr(crm, "chamar", lambda s, f, **a: {"kommo_conversa": [], "kommo_funis": FUNIS,
                                                          "kommo_lead": LEADS[0]}[f])
    monkeypatch.setenv("KOMMO_HOOK_KEY", "chave-do-hook")
    monkeypatch.setenv("KOMMO_BOT_ID", "999")
    monkeypatch.delenv("KOMMO_BOT_SECRET", raising=False)
    return k


def _lid(ext="5001"):
    con = conectar()
    try:
        return um(con, "SELECT id FROM crm_leads WHERE external_id=?", (ext,))["id"]
    finally:
        con.close()


def test_hook_do_salesbot_guarda_a_mensagem_e_so_com_a_chave(cli, chat):
    assert cli.post(f"{B}/crm/hook", content=HOOK, headers={"Content-Type": "application/x-www-form-urlencoded"}).status_code == 403
    assert cli.post(f"{B}/crm/hook?key=errada", content=HOOK, headers={"Content-Type": "application/x-www-form-urlencoded"}).status_code == 403
    r = cli.post(f"{B}/crm/hook?key=chave-do-hook", content=HOOK, headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200 and r.json()["ok"]
    con = conectar()
    try:
        l = um(con, "SELECT * FROM crm_leads WHERE external_id='5001'")
        assert l["needs_reply"] == 1 and l["return_url"].endswith("/continue/abc") and l["return_at"] and l["last_hook_at"]
        m = um(con, "SELECT * FROM crm_messages WHERE lead_id=? AND source='hook'", (l["id"],))
        assert m["direction"] == "entrada" and m["text"] == "Consegue domingo?" and m["author"] == "Maria Souza"
        # o mesmo POST de novo no mesmo minuto não duplica
        cli.post(f"{B}/crm/hook?key=chave-do-hook", content=HOOK, headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert um(con, "SELECT COUNT(*) AS n FROM crm_messages WHERE lead_id=? AND source='hook'", (l["id"],))["n"] == 1
    finally:
        con.close()
    assert chat.entregas == []                    # nada na fila: o bot fica esperando, sem inventar resposta


def test_resposta_sai_na_hora_se_o_bot_ainda_espera(cli, chat):
    h = entra(cli, "op@urace.us")
    lid = _lid()
    r = cli.post(f"{B}/crm/leads/{lid}/reply", headers=h, json={"text": "Domingo às 9h, pode ser?"})
    assert r.status_code == 200 and r.json()["como"] == "entregue"
    assert chat.entregas[-1][0].endswith("/continue/abc") and chat.entregas[-1][1] == "Domingo às 9h, pode ser?" and chat.entregas[-1][2] == "1"
    assert chat.runs == []                        # não precisou disparar o bot
    con = conectar()
    try:
        m = um(con, "SELECT status FROM crm_messages WHERE lead_id=? AND direction='saida' ORDER BY id DESC LIMIT 1", (lid,))
        assert m["status"] == "sent"
        l = um(con, "SELECT return_url, needs_reply FROM crm_leads WHERE id=?", (lid,))
        assert l["return_url"] is None and l["needs_reply"] == 0     # continuação gasta, conversa respondida
    finally:
        con.close()


def test_resposta_horas_depois_dispara_o_bot_e_o_hook_entrega_a_fila(cli, chat):
    h = entra(cli, "op@urace.us")
    lid = _lid()
    r = cli.post(f"{B}/crm/leads/{lid}/reply", headers=h, json={"text": "Confirmado para domingo!"})
    assert r.status_code == 200 and r.json()["como"] == "bot disparado" and chat.runs == [("5001", "1")]
    con = conectar()
    try:
        assert um(con, "SELECT status FROM crm_messages WHERE lead_id=? AND direction='saida' ORDER BY id DESC LIMIT 1", (lid,))["status"] == "queued"
    finally:
        con.close()
    # o bot abre o canal: chama o hook SEM mensagem, com return_url novo → a fila sai
    sem_msg = "data%5Blead_id%5D=5001&data%5Bmessage%5D=%7B%7Bmessage_text%7D%7D&return_url=https%3A%2F%2Furace.kommo.com%2Fapi%2Fv4%2Fsalesbot%2F999%2Fcontinue%2Fxyz"
    assert cli.post(f"{B}/crm/hook?key=chave-do-hook", content=sem_msg, headers={"Content-Type": "application/x-www-form-urlencoded"}).status_code == 200
    assert chat.entregas[-1][0].endswith("/continue/xyz") and chat.entregas[-1][1] == "Confirmado para domingo!"
    con = conectar()
    try:
        assert um(con, "SELECT status FROM crm_messages WHERE lead_id=? AND direction='saida' ORDER BY id DESC LIMIT 1", (lid,))["status"] == "sent"
        assert um(con, "SELECT COUNT(*) AS n FROM crm_messages WHERE lead_id=? AND direction='entrada' AND text LIKE '%message_text%'", (lid,))["n"] == 0   # placeholder não vira mensagem
    finally:
        con.close()


def test_fila_parada_vira_nota_e_fica_marcada(cli, chat):
    h = entra(cli, "op@urace.us")
    lid = _lid()
    cli.post(f"{B}/crm/leads/{lid}/reply", headers=h, json={"text": "Essa vai ficar parada"})
    con = conectar()
    try:
        con.execute("UPDATE crm_messages SET at='2026-01-01T00:00:00Z' WHERE lead_id=? AND status='queued'", (lid,)); con.commit()
        assert crm.varrer_fila(con) == 1
        m = um(con, "SELECT status, error FROM crm_messages WHERE lead_id=? AND text='Essa vai ficar parada'", (lid,))
        assert m["status"] == "failed" and "nota" in m["error"]
        assert chat.notas[-1][0] == "5001" and "enviar manualmente" in chat.notas[-1][1]
    finally:
        con.close()
    d = cli.get(f"{B}/crm/leads/{lid}", headers=h).json()
    assert any(m["status"] == "failed" for m in d["mensagens"])


def test_inbox_e_setup(cli, chat):
    h = entra(cli, "admin@urace.us")
    ib = cli.get(f"{B}/crm/inbox", headers=h).json()
    c = next(c for c in ib["conversas"] if c["external_id"] == "5001")
    assert c["snippet"] and c["source"] == "Instagram" and ib["conversas"][0]["needs_reply"] == 1   # quem espera no topo
    s = cli.get(f"{B}/crm/setup", headers=h).json()
    assert s["hook_url"].endswith("/ops/api/crm/hook?key=chave-do-hook") and s["bot_id"] == "999" and s["hooks_hoje"] >= 1
    assert cli.get(f"{B}/crm/setup", headers=entra(cli, "op@urace.us")).status_code == 403


def test_hook_com_assinatura_do_bot(cli, chat, monkeypatch):
    import base64, hmac, hashlib
    monkeypatch.setenv("KOMMO_BOT_SECRET", "segredo")
    h64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
    cab, corpo = h64(b'{"alg":"HS512"}'), h64(b'{"exp":9999999999}')
    bom = f"{cab}.{corpo}." + h64(hmac.new(b"segredo", f"{cab}.{corpo}".encode(), hashlib.sha512).digest())
    ruim = f"{cab}.{corpo}.AAAA"
    base = "data%5Blead_id%5D=5001&data%5Bmessage%5D=oi"
    assert cli.post(f"{B}/crm/hook?key=chave-do-hook", content=base + "&token=" + ruim, headers={"Content-Type": "application/x-www-form-urlencoded"}).status_code == 401
    assert cli.post(f"{B}/crm/hook?key=chave-do-hook", content=base + "&token=" + bom, headers={"Content-Type": "application/x-www-form-urlencoded"}).status_code == 200


def test_eventos_de_chat_viram_conversas_com_canal(cli, monkeypatch):
    """O texto antigo a API não entrega; o movimento (quem, canal, quando) entra e a
    conversa aparece na caixa de entrada com a origem certa e 'espera resposta'."""
    from command_center.providers import sync
    import kommo_mcp as k
    eventos_brutos = {"_embedded": {"events": [
        {"id": "e1", "type": "outgoing_chat_message", "entity_id": 7001, "entity_type": "lead", "created_at": 1789000000,
         "value_after": [{"message": {"id": "m1", "origin": "com.amocrm.amocrmwa", "talk_id": 55}}]},
        {"id": "e2", "type": "incoming_chat_message", "entity_id": 7001, "entity_type": "lead", "created_at": 1789000600,
         "value_after": [{"message": {"id": "m2", "origin": "com.amocrm.amocrmwa", "talk_id": 55}}]},
    ]}}
    monkeypatch.setenv("KOMMO_DOMAIN", "urace.kommo.com"); monkeypatch.setenv("KOMMO_TOKEN", "t")
    pedidos = []
    def _lista_falsa(params, maximo):
        pedidos.append(params)
        # a conta ignora o filtro de tipo em silêncio: só "sem tipo" traz algo (é o caso real de 10/09)
        return eventos_brutos["_embedded"]["events"] + [{"id": "e0", "type": "lead_status_changed", "entity_type": "lead", "entity_id": 7001}] \
            if "filter[type]" not in " ".join(params) else []
    monkeypatch.setattr(k, "_lista_eventos", _lista_falsa)
    evs = k.kommo_chats()
    assert [e["direcao"] for e in evs] == ["saida", "entrada"] and evs[0]["canal"] == "WhatsApp"
    assert len(pedidos) == 4 and k._ultimo_modo["modo"] == "sem tipo"          # tentou os formatos e caiu no cru
    monkeypatch.setattr(k, "_lista_eventos", lambda params, maximo: eventos_brutos["_embedded"]["events"])
    assert len(k.kommo_chats()) == 2 and k._ultimo_modo["modo"] == "tipo[]"   # quando o filtro funciona, para no primeiro
    monkeypatch.setattr(sync, "chamar", lambda s, f, **a: {"kommo_chats": evs, "kommo_lead": {"id": "7001", "nome": "João Kart", "contato": {"nome": "João", "telefone": "+1 321 555 0102"}}}[f])
    con = conectar()
    try:
        r = sync.sincronizar_chats_kommo(con)
        assert r["conversas"] == 1 and r["conversas_novas"] == 1
        l = um(con, "SELECT * FROM crm_leads WHERE external_id='7001'")
        assert l["source"] == "WhatsApp" and l["needs_reply"] == 1 and l["name"] == "João Kart" and l["link"].endswith("/leads/detail/7001")
        ms = todos(con, "SELECT direction, text, source FROM crm_messages WHERE lead_id=? ORDER BY at", (l["id"],))
        assert [m["direction"] for m in ms] == ["saida", "entrada"] and all(m["text"] is None for m in ms) and ms[0]["source"] == "WhatsApp"
        sync.sincronizar_chats_kommo(con)          # de novo: não duplica
        assert um(con, "SELECT COUNT(*) AS n FROM crm_messages WHERE lead_id=?", (l["id"],))["n"] == 2
    finally:
        con.close()


def test_conversa_como_talk_vira_registro_de_chat(monkeypatch):
    """Caso real de 10/09: a conta não emite incoming_chat_message; o chat aparece como
    evento em entidade 'talk' (conversation_answered). O talk diz lead e canal."""
    import kommo_mcp as k
    k._talks.clear()
    monkeypatch.setenv("KOMMO_DOMAIN", "urace.kommo.com"); monkeypatch.setenv("KOMMO_TOKEN", "t")
    chamadas = []
    def _req(c, m="GET", corpo=None, params=None):
        chamadas.append(c)
        if c == "/talks/8967":
            return {"talk_id": 8967, "contact_id": 6549506, "entity_id": 23899732, "entity_type": "lead",
                    "origin": "com.amocrm.amocrmwa", "is_read": True, "created_at": 1789000000, "updated_at": 1789100000}
        return {}
    monkeypatch.setattr(k, "_req", _req)
    ev = {"id": "e9", "type": "conversation_answered", "entity_type": "talk", "entity_id": 8967, "created_at": 1789100000, "value_after": []}
    r = k._evento_chat(ev)
    assert r["lead_id"] == "23899732" and r["canal"] == "WhatsApp" and r["direcao"] == "saida" and r["talk_id"] == "8967"
    k._evento_chat(dict(ev, id="e10"))
    assert chamadas.count("/talks/8967") == 1                      # cache: um talk, uma chamada
    assert k._evento_chat({"type": "incoming_mail", "entity_type": "contact", "entity_id": 1}) is None


def test_filtro_recusado_passa_ao_proximo_e_contatos_vem_em_lote(monkeypatch):
    import kommo_mcp as k
    from mcp_stdio import ErroFerramenta
    monkeypatch.setenv("KOMMO_DOMAIN", "urace.kommo.com"); monkeypatch.setenv("KOMMO_TOKEN", "t")
    tentativas = []
    def _lista_falsa(params, maximo):
        tentativas.append(" ".join(params))
        if "filter[type]" in tentativas[-1]:
            raise ErroFerramenta('Kommo GET /events → 400: {"errors":{"key":"type"}}')
        return [{"id": "e1", "type": "incoming_chat_message", "entity_type": "lead", "entity_id": 1, "created_at": 1789000000,
                 "value_after": [{"message": {"origin": "instagram"}}]}]
    monkeypatch.setattr(k, "_lista_eventos", _lista_falsa)
    evs = k.kommo_chats()
    assert len(evs) == 1 and k._ultimo_modo["modo"] == "sem tipo" and len(tentativas) == 4
    # contatos em lote: 3 leads com contato só por id → UMA chamada /contacts
    k._contatos.clear()
    chamadas = []
    def _req(c, m="GET", corpo=None, params=None):
        chamadas.append((c, params))
        if c == "/leads":
            return {"_embedded": {"leads": [{"id": i, "name": f"L{i}", "pipeline_id": 1, "status_id": 2,
                                             "_embedded": {"contacts": [{"id": 100 + i}]}} for i in (1, 2, 3)]}}
        if c == "/contacts":
            return {"_embedded": {"contacts": [{"id": 100 + i, "name": f"C{i}", "custom_fields_values": []} for i in (1, 2, 3)]}}
        return {}
    monkeypatch.setattr(k, "_req", _req)
    monkeypatch.setattr(k, "_nome_etapa", lambda f, e: ("Sales funnel", "First Contact", 2))
    leads = k.kommo_leads(maximo=10)
    assert [l["contato"]["nome"] for l in leads] == ["C1", "C2", "C3"]
    assert [c for c, _ in chamadas].count("/contacts") == 1 and not any(c.startswith("/contacts/") for c, _ in chamadas)

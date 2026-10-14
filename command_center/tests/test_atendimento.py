"""Atendimento humano (missão de 14/10): escalonamento da IA, aviso à equipe, pessoa assume,
responde, devolve. Os testes seguem as letras da missão (A–K) e nenhum fala com sistema real:
push, WhatsApp, Kommo e a ponte são trocados por dublês que registram o que receberiam.
"""
import hashlib
import hmac
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

os.environ["WA_ENV"] = "/nao/existe"
os.environ["HANDOFF_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth, crm, push, sdr  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, todos, um  # noqa: E402
from command_center.providers import atendimento as at  # noqa: E402
from command_center.providers import whatsapp as wa  # noqa: E402

B = "/ops/api/atendimento"
SENHA = "senha-forte-123"
SEGREDO = "segredo-do-app-de-teste"


@pytest.fixture(scope="module")
def ambiente():
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc-atendimento.sqlite")
    con = conectar(); aplicar_schema(con)
    ids = {}
    for email, nome, papel in [("admin@urace.us", "Admin", "ADMIN"), ("gerente@urace.us", "Gerente", "MANAGER"),
                               ("ana@urace.us", "Ana", "OPERATOR"), ("bia@urace.us", "Bia", "OPERATOR"),
                               ("leitor@urace.us", "Leitor", "VIEWER")]:
        auth.criar_usuario(con, email, nome, papel, SENHA)
        ids[email] = um(con, "SELECT id FROM users WHERE email=?", (email,))["id"]
    chave_ia = auth.criar_chave(con, "ponte de vendas", "OPERATOR", ids["admin@urace.us"], somente_leitura=False)["chave"]
    chave_leitura = auth.criar_chave(con, "leitura", "OPERATOR", ids["admin@urace.us"])["chave"]
    inserir(con, "crm_leads", external_id="31764961", name="Lead Teste", contact_name="Maria Teste", source="WhatsApp")
    con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield {"cli": c, "ids": ids, "ia": {"X-API-Key": chave_ia}, "leitura": {"X-API-Key": chave_leitura}}


@pytest.fixture(autouse=True)
def isolado(monkeypatch, ambiente):
    """Cada teste começa sem caso aberto, sem pausa e com os dublês no lugar."""
    for k in ("WA_TOKEN", "WA_PHONE_NUMBER_ID", "WA_APLICAR", "WA_TEMPLATE_HANDOFF", "HANDOFF_PONTE_URL",
              "HANDOFF_PONTE_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("WA_APP_SECRET", SEGREDO)
    monkeypatch.setattr(wa, "_post", lambda corpo: pytest.fail("WhatsApp não pode sair sem liberar"))
    avisados = []
    monkeypatch.setattr(push, "avisar", lambda con, ids, t, c, url="/ops/": (avisados.extend(ids) or
                                                                             {"enviados": len(ids), "aparelhos": len(ids)}))
    con = conectar()
    con.execute("UPDATE handoff_casos SET estado='RESOLVED', fechado_em='2000-01-01T00:00:00.000Z' "
                "WHERE estado IN ('HUMAN_PENDING','HUMAN_ACTIVE')")
    con.execute("UPDATE handoff_casos SET ponte_pendente=NULL")
    con.close()
    sdr.gravar_pausas({})
    from command_center.api import atendimento as rota
    rota._janela.clear()                               # o teto por minuto vale por teste
    ambiente["avisados"] = avisados
    yield


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def escalar(amb, lead="31764961", **extra):
    amb["cli"].cookies.clear()
    corpo = {"conversation_id": f"kommo:{lead}", "reason": "Cliente pediu para falar com uma pessoa",
             "priority": "high", "summary": "Quer remarcar a Academy e pediu um humano.",
             "customer_name": "Maria Teste", "requested_action": "Ligar e remarcar", **extra}
    return amb["cli"].post(B + "/casos", json=corpo, headers=amb["ia"])


# ------------------------------------------------------------------ A: escalonamento básico
def test_A_escalonamento_cria_caso_com_motivo_e_trava_a_ia(ambiente):
    r = escalar(ambiente)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["resultado"] == "caso_criado" and d["estado"] == "HUMAN_PENDING"
    assert d["motivo"] == "pedido_explicito" and d["prioridade"] == "alta"
    assert d["ia_bloqueada"] is True
    assert sdr.ler_pausas()["31764961"]["handoff"] == d["caso_id"]
    con = conectar()
    c = um(con, "SELECT * FROM handoff_casos WHERE id=?", (d["caso_id"],))
    assert c["motivo_texto"] == "Cliente pediu para falar com uma pessoa"
    assert c["crm_lead_id"] and c["conversa_conferida"] == 1 and c["canal"] == "WhatsApp"
    assert [e["tipo"] for e in todos(con, "SELECT tipo FROM handoff_eventos WHERE caso_id=? ORDER BY id", (c["id"],))][:2] \
        == ["criado", "ia_travada"]
    assert um(con, "SELECT 1 AS x FROM audit_logs WHERE event='handoff.criado' AND entity_id=?", (str(c["id"]),))
    con.close()


@pytest.mark.parametrize("cid", ["", "abc", "kommo:", "kommo:-4", "0", "kommo:12ab"])
def test_A_conversa_invalida_recusada(ambiente, cid):
    r = escalar(ambiente, conversation_id=cid)
    assert r.status_code == 400


def test_A_motivo_obrigatorio_e_prioridade_validada(ambiente):
    assert escalar(ambiente, reason="  ").status_code == 400
    assert escalar(ambiente, priority="altissima").status_code == 400


@pytest.mark.parametrize("texto,categoria", [("asked for a refund of the deposit", "pagamento"),
                                             ("complaint about the coach", "reclamacao"),
                                             ("wants a discount on the academy", "excecao_comercial"),
                                             ("talked about a lawyer", "seguranca"),
                                             ("algo que ninguém previu", "outro")])
def test_A_categoria_pelo_texto_quando_nao_vem(texto, categoria):
    assert at.motivo_de(None, texto) == categoria
    assert at.motivo_de("refund", "x") == "pagamento"


# ------------------------------------------------------------------ B: notificação
def test_B_aviso_tem_os_dados_e_so_conta_o_que_saiu_de_verdade(ambiente):
    d = escalar(ambiente).json()
    assert d["humano_notificado"] is True and d["notificacao"] == "enviada"
    assert set(ambiente["avisados"]) == {ambiente["ids"][e] for e in
                                         ("admin@urace.us", "gerente@urace.us", "ana@urace.us", "bia@urace.us")}
    con = conectar()
    msg = um(con, "SELECT text, origem FROM team_messages WHERE origem='atendimento' ORDER BY id DESC LIMIT 1")
    for trecho in ("[URACE IA · ATENDIMENTO HUMANO]", "Prioridade: ALTA", "Cliente: Maria Teste", "kommo:31764961",
                   "Motivo: o cliente pediu uma pessoa", "Resumo: Quer remarcar", "Ação pedida: Ligar e remarcar",
                   f"/ops/atendimento/{d['caso_id']}", "Status: HUMAN_PENDING"):
        assert trecho in msg["text"], trecho
    assert "+1" not in msg["text"]                       # telefone do cliente não vai no aviso
    con.close()


def test_B_sem_aparelho_e_sem_whatsapp_nao_diz_que_avisou(ambiente, monkeypatch):
    monkeypatch.setattr(push, "avisar", lambda *a, **k: {"enviados": 0, "aparelhos": 0})
    d = escalar(ambiente).json()
    assert d["resultado"] == "caso_criado"
    assert d["humano_notificado"] is False and d["notificacao"] == "falhou"
    assert "Não diga ao cliente que alguém já foi avisado" in d["instrucao_para_ia"]


def _contato(amb, nome="Lucas", fone="+1 407 555 0101", recebe=True, ultima=None):
    con = conectar()
    cid = inserir(con, "team_channels", name=f"{nome} · WhatsApp", kind="EQUIPE", bridge="whatsapp",
                  bridge_id=wa.normaliza_fone(fone))
    ct = inserir(con, "team_contacts", name=nome, phone=wa.normaliza_fone(fone), channel_id=cid,
                 recebe_handoff=1 if recebe else 0, last_inbound_at=ultima)
    con.close()
    return ct


def test_B_whatsapp_oficial_dentro_da_janela_e_template_fora(ambiente, monkeypatch):
    from command_center.db import agora
    dentro = _contato(ambiente, "Lucas", "+1 407 555 0101", ultima=agora())
    fora = _contato(ambiente, "Italo", "+1 407 555 0102", ultima="2020-01-01T00:00:00.000Z")
    enviados = []
    monkeypatch.setenv("WA_TOKEN", "t"); monkeypatch.setenv("WA_PHONE_NUMBER_ID", "1"); monkeypatch.setenv("WA_APLICAR", "1")
    monkeypatch.setattr(wa, "_post", lambda corpo: (enviados.append(corpo) or {"messages": [{"id": f"wamid.{len(enviados)}"}]}))
    d = escalar(ambiente, lead="555001").json()
    con = conectar()
    linhas = {n["destino"]: n for n in todos(con, "SELECT * FROM handoff_notificacoes WHERE caso_id=? AND canal='whatsapp'",
                                              (d["caso_id"],))}
    assert linhas[f"contato:{dentro}"]["status"] == "enviado"
    assert linhas[f"contato:{fora}"]["status"] == "bloqueado"           # fora da janela e sem template
    assert "template" in linhas[f"contato:{fora}"]["erro"]
    assert enviados[0]["type"] == "text" and "ATENDIMENTO HUMANO" in enviados[0]["text"]["body"]
    # com o template aprovado, o próximo caso sai para os dois
    monkeypatch.setenv("WA_TEMPLATE_HANDOFF", "urace_handoff_alert")
    d2 = escalar(ambiente, lead="555002").json()
    tipos = [e["type"] for e in enviados[1:]]
    assert sorted(tipos) == ["template", "text"]
    tpl = next(e for e in enviados[1:] if e["type"] == "template")["template"]
    assert tpl["name"] == "urace_handoff_alert" and len(tpl["components"][0]["parameters"]) == 4
    # recibo da Meta chega pelo webhook e anda o status do aviso
    wamid = um(con, "SELECT external_id FROM handoff_notificacoes WHERE caso_id=? AND canal='whatsapp' AND status='enviado' "
                    "LIMIT 1", (d2["caso_id"],))["external_id"]
    corpo = json.dumps({"entry": [{"changes": [{"value": {"statuses": [{"id": wamid, "status": "read"}]}}]}]}).encode()
    sig = "sha256=" + hmac.new(SEGREDO.encode(), corpo, hashlib.sha256).hexdigest()
    assert ambiente["cli"].post("/ops/api/whatsapp/webhook", content=corpo,
                                headers={"x-hub-signature-256": sig}).status_code == 200
    assert um(con, "SELECT status FROM handoff_notificacoes WHERE external_id=?", (wamid,))["status"] == "lido"
    con.execute("UPDATE team_contacts SET active=0")
    con.close()


def test_B_whatsapp_sem_configurar_fica_simulado_e_nao_conta(ambiente):
    _contato(ambiente, "Eduardo", "+1 407 555 0199")
    d = escalar(ambiente, lead="555003").json()
    assert d["avisos"]["whatsapp"] == {"simulado": 1}
    con = conectar(); con.execute("UPDATE team_contacts SET active=0"); con.close()


# ------------------------------------------------------------------ C: atendimento humano
def test_C_pessoa_assume_e_responde_pelo_canal_oficial(ambiente, monkeypatch):
    d = escalar(ambiente).json()
    h = entra(ambiente["cli"], "ana@urace.us")
    r = ambiente["cli"].post(f"{B}/casos/{d['caso_id']}/assumir", headers=h)
    assert r.status_code == 200 and r.json()["estado"] == "HUMAN_ACTIVE"
    assert r.json()["responsavel_nome"] == "Ana"
    chamadas = []
    monkeypatch.setattr(crm, "responder", lambda lid, dados, req, u, con: (chamadas.append((lid, dados.text, u["name"]))
                                                                            or {"ok": True, "msg_id": 7, "como": "entregue"}))
    r = ambiente["cli"].post(f"{B}/casos/{d['caso_id']}/responder", json={"texto": "Oi Maria, aqui é a Ana."}, headers=h)
    assert r.status_code == 200, r.text
    con = conectar()
    lid = um(con, "SELECT id FROM crm_leads WHERE external_id='31764961'")["id"]
    assert chamadas == [(lid, "Oi Maria, aqui é a Ana.", "Ana")]
    assert um(con, "SELECT 1 AS x FROM handoff_eventos WHERE caso_id=? AND tipo='resposta_humana'", (d["caso_id"],))
    con.close()


def test_C_dois_cliques_em_assumir_so_um_vence(ambiente):
    d = escalar(ambiente).json()
    con = conectar()
    a = {"id": ambiente["ids"]["ana@urace.us"], "name": "Ana", "role": "OPERATOR"}
    b = {"id": ambiente["ids"]["bia@urace.us"], "name": "Bia", "role": "OPERATOR"}
    at.assumir_caso(con, d["caso_id"], a)
    with pytest.raises(at.ErroAtendimento) as e:
        at.assumir_caso(con, d["caso_id"], b)
    assert e.value.codigo == 409
    assert at.caso(con, d["caso_id"])["responsavel_id"] == a["id"]
    con.close()


def test_C_transferir_para_outra_pessoa(ambiente):
    d = escalar(ambiente).json()
    h = entra(ambiente["cli"], "ana@urace.us")
    ambiente["cli"].post(f"{B}/casos/{d['caso_id']}/assumir", headers=h)
    r = ambiente["cli"].post(f"{B}/casos/{d['caso_id']}/transferir", json={"para_user_id": ambiente["ids"]["bia@urace.us"]},
                             headers=h)
    assert r.status_code == 200 and r.json()["responsavel_nome"] == "Bia"
    assert ambiente["avisados"][-1] == ambiente["ids"]["bia@urace.us"]   # quem recebe é avisada
    # agora a Ana não encerra mais (não é dela), a Bia encerra
    assert ambiente["cli"].post(f"{B}/casos/{d['caso_id']}/encerrar", json={"texto": "x"}, headers=h).status_code == 403


# ------------------------------------------------------------------ D: bloqueio da IA
def test_D_ia_travada_em_pendente_e_em_atendimento(ambiente):
    d = escalar(ambiente).json()
    cli = ambiente["cli"]
    h = entra(cli, "ana@urace.us")
    assert cli.get(f"{B}/conversa/31764961").json()["ia_pode_responder"] is False
    cli.post(f"{B}/casos/{d['caso_id']}/assumir", headers=h)
    e = cli.get(f"{B}/conversa/31764961").json()
    assert e["estado"] == "HUMAN_ACTIVE" and e["ia_pode_responder"] is False
    assert "31764961" in sdr.ler_pausas()


def test_D_pausa_manual_nao_solta_conversa_em_atendimento(ambiente):
    d = escalar(ambiente).json()
    h = entra(ambiente["cli"], "ana@urace.us")
    r = ambiente["cli"].put("/ops/api/sdr/pausas/31764961", json={"pausada": False}, headers=h)
    assert r.status_code == 409 and f"#{d['caso_id']}" in r.json()["detail"]
    assert sdr.ler_pausas()["31764961"]["handoff"] == d["caso_id"]


def test_D_pausa_manual_anterior_sobrevive_ao_caso(ambiente, monkeypatch):
    h = entra(ambiente["cli"], "ana@urace.us")
    assert ambiente["cli"].put("/ops/api/sdr/pausas/31764961", json={"pausada": True, "motivo": "cliente VIP"},
                               headers=h).status_code == 200
    d = escalar(ambiente).json()
    h = entra(ambiente["cli"], "ana@urace.us")
    ambiente["cli"].post(f"{B}/casos/{d['caso_id']}/assumir", headers=h)
    ambiente["cli"].post(f"{B}/casos/{d['caso_id']}/encerrar", json={"texto": "Resolvido por telefone."}, headers=h)
    entrada = sdr.ler_pausas()["31764961"]
    assert "handoff" not in entrada and entrada["manual"] is True and entrada["motivo"] == "cliente VIP"


# ------------------------------------------------------------------ E: devolução do controle
class _Ponte(BaseHTTPRequestHandler):
    recebidos, responder_ok = [], True

    def do_POST(self):                                  # noqa: N802
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Ponte.recebidos.append((self.path, self.headers.get("X-Handoff-Token"), corpo))
        status = 200 if _Ponte.responder_ok else 503
        self.send_response(status); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"ok": _Ponte.responder_ok}).encode())

    def log_message(self, *a):
        pass


@pytest.fixture()
def ponte(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), _Ponte)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _Ponte.recebidos.clear(); _Ponte.responder_ok = True
    monkeypatch.setenv("HANDOFF_PONTE_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setenv("HANDOFF_PONTE_TOKEN", "token-da-ponte")
    yield _Ponte
    srv.shutdown()


def test_E_devolver_avisa_a_ponte_com_contexto_e_so_entao_solta(ambiente, ponte):
    d = escalar(ambiente).json()
    cli = ambiente["cli"]
    h = entra(cli, "ana@urace.us")
    cli.post(f"{B}/casos/{d['caso_id']}/assumir", headers=h)
    assert cli.post(f"{B}/casos/{d['caso_id']}/devolver", json={"texto": " "}, headers=h).status_code == 400
    r = cli.post(f"{B}/casos/{d['caso_id']}/devolver",
                 json={"texto": "Remarcada para sábado 10h; pode seguir com o check-in."}, headers=h)
    assert r.status_code == 200 and r.json()["estado"] == "RETURNED_TO_AI"
    caminho, token, corpo = ponte.recebidos[-1]
    assert caminho == "/handoff/estado" and token == "token-da-ponte"
    assert corpo["estado"] == "RETURNED_TO_AI" and corpo["lead_id"] == 31764961
    assert corpo["nota"].startswith("Remarcada para sábado") and corpo["autor"] == "Ana"
    assert "31764961" not in sdr.ler_pausas()
    assert cli.get(f"{B}/conversa/31764961").json() == {"conversa": "kommo:31764961", "estado": "AI_ACTIVE",
                                                       "caso_aberto": None, "ia_travada": False,
                                                       "ia_pode_responder": True}


def test_E_so_caso_assumido_pode_ser_devolvido(ambiente):
    d = escalar(ambiente).json()
    h = entra(ambiente["cli"], "gerente@urace.us")
    r = ambiente["cli"].post(f"{B}/casos/{d['caso_id']}/devolver", json={"texto": "volta"}, headers=h)
    assert r.status_code == 409


def test_E_resolvido_e_nova_mensagem_abre_novo_ciclo(ambiente, ponte):
    d = escalar(ambiente).json()
    h = entra(ambiente["cli"], "ana@urace.us")
    ambiente["cli"].post(f"{B}/casos/{d['caso_id']}/assumir", headers=h)
    r = ambiente["cli"].post(f"{B}/casos/{d['caso_id']}/encerrar", json={"texto": "Reembolso feito."}, headers=h)
    assert r.json()["estado"] == "RESOLVED" and ponte.recebidos[-1][2]["estado"] == "RESOLVED"
    assert "31764961" not in sdr.ler_pausas()
    d2 = escalar(ambiente).json()
    assert d2["resultado"] == "caso_criado" and d2["caso_id"] != d["caso_id"]


# ------------------------------------------------------------------ F: reinicialização
def test_F_reinicio_nao_destrava_conversa_humana(ambiente):
    d = escalar(ambiente).json()
    # o processo cai e alguém (ou um deploy) apaga o arquivo de pausas
    sdr.gravar_pausas({})
    con = conectar()                                   # conexão nova = processo novo
    mudou = at.reconciliar_pausas(con)
    con.close()
    assert 31764961 in mudou["travadas"]
    assert sdr.ler_pausas()["31764961"]["handoff"] == d["caso_id"]
    # e o painel inteiro reiniciado continua sabendo
    with TestClient(app, base_url="https://cc.test") as novo:
        entra(novo, "ana@urace.us")
        assert novo.get(f"{B}/conversa/31764961").json()["ia_pode_responder"] is False


def test_F_trava_de_caso_fechado_e_removida_pela_reconciliacao(ambiente):
    sdr.gravar_pausas({"777": {"handoff": 999999, "por": "atendimento humano #999999"},
                       "888": {"por": "Lucas", "manual": True}})
    con = conectar(); at.reconciliar_pausas(con); con.close()
    p = sdr.ler_pausas()
    assert "777" not in p and "888" in p                # a manual nunca é tocada


# ------------------------------------------------------------------ G: eventos duplicados
def test_G_reprocessar_o_mesmo_escalonamento_nao_duplica(ambiente):
    d1 = escalar(ambiente, idempotency_key="ponte:31764961:1700000000").json()
    antes = len(ambiente["avisados"])
    d2 = escalar(ambiente, idempotency_key="ponte:31764961:1700000000").json()
    d3 = escalar(ambiente, idempotency_key="ponte:31764961:1700000999", priority="urgent").json()
    assert d1["resultado"] == "caso_criado"
    assert d2["resultado"] == d3["resultado"] == "caso_existente"
    assert d1["caso_id"] == d2["caso_id"] == d3["caso_id"]
    assert len(ambiente["avisados"]) == antes           # nenhum aviso novo
    con = conectar()
    assert um(con, "SELECT COUNT(*) AS n FROM handoff_casos WHERE kommo_lead_id=31764961 AND estado='HUMAN_PENDING'")["n"] == 1
    assert at.caso(con, d1["caso_id"])["prioridade"] == "urgente"   # prioridade só sobe
    n = um(con, "SELECT COUNT(*) AS n FROM handoff_notificacoes WHERE caso_id=?", (d1["caso_id"],))["n"]
    at.enfileirar_avisos(con, at.caso(con, d1["caso_id"]), "abertura")   # reenfileirar não duplica
    assert um(con, "SELECT COUNT(*) AS n FROM handoff_notificacoes WHERE caso_id=?", (d1["caso_id"],))["n"] == n
    con.close()


def test_G_banco_recusa_dois_casos_abertos_na_mesma_conversa(ambiente):
    escalar(ambiente)
    con = conectar()
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        inserir(con, "handoff_casos", conversa="kommo:31764961", kommo_lead_id=31764961, motivo="outro")
    con.close()


# ------------------------------------------------------------------ H: indisponibilidade
def test_H_ponte_fora_do_ar_mantem_com_humano_e_recupera(ambiente, ponte):
    d = escalar(ambiente).json()
    cli = ambiente["cli"]
    h = entra(cli, "ana@urace.us")
    cli.post(f"{B}/casos/{d['caso_id']}/assumir", headers=h)
    ponte.responder_ok = False
    r = cli.post(f"{B}/casos/{d['caso_id']}/devolver", json={"texto": "Pode seguir."}, headers=h)
    assert r.status_code == 200 and r.json()["estado"] == "HUMAN_ACTIVE"
    assert "A ponte não confirmou" in r.json()["aviso"]
    assert "31764961" in sdr.ler_pausas()              # IA continua travada
    ponte.responder_ok = True
    con = conectar()
    assert at.sincronizar_pendentes(con) == [d["caso_id"]]
    c = at.caso(con, d["caso_id"])
    assert c["estado"] == "RETURNED_TO_AI" and c["ponte_pendente"] is None
    assert "31764961" not in sdr.ler_pausas()
    con.close()


def test_H_aviso_que_falha_volta_para_a_fila_e_sai_depois(ambiente, monkeypatch):
    falhas = {"n": 0}

    def instavel(con, ids, t, c, url="/ops/"):
        raise ConnectionError("push fora do ar")
    monkeypatch.setattr(push, "avisar", instavel)
    d = escalar(ambiente).json()
    assert d["notificacao"] == "pendente" and d["humano_notificado"] is False
    con = conectar()
    p = um(con, "SELECT * FROM handoff_notificacoes WHERE caso_id=? AND canal='push' LIMIT 1", (d["caso_id"],))
    assert p["status"] == "pendente" and p["tentativas"] == 1 and "push fora do ar" in p["erro"]
    # antes da espera passar, nada é tentado de novo
    assert at.processar_fila(con, caso_id=d["caso_id"])["enviados"] == 0
    con.execute("UPDATE handoff_notificacoes SET proxima_em='2000-01-01T00:00:00.000Z' WHERE caso_id=?", (d["caso_id"],))
    monkeypatch.setattr(push, "avisar", lambda *a, **k: (falhas.update(n=falhas["n"] + 1) or {"enviados": 1, "aparelhos": 1}))
    at.processar_fila(con, caso_id=d["caso_id"])
    assert at.resumo_avisos(con, d["caso_id"])["humano_notificado"] is True
    con.close()


def test_H_aviso_desiste_depois_do_teto(ambiente, monkeypatch):
    monkeypatch.setattr(push, "avisar", lambda *a, **k: (_ for _ in ()).throw(OSError("rede")))
    d = escalar(ambiente).json()
    con = conectar()
    for _ in range(at.TENTATIVAS_MAX):
        con.execute("UPDATE handoff_notificacoes SET proxima_em='2000-01-01T00:00:00.000Z' WHERE status='pendente'")
        at.processar_fila(con, caso_id=d["caso_id"])
    st = {r["status"] for r in todos(con, "SELECT status FROM handoff_notificacoes WHERE caso_id=? AND canal='push'",
                                     (d["caso_id"],))}
    assert st == {"desistiu"}
    assert at.caso(con, d["caso_id"])["estado"] == "HUMAN_PENDING"   # o caso continua registrado
    con.close()


def test_H_caso_atrasado_realerta_com_teto(ambiente):
    from datetime import datetime, timezone
    d = escalar(ambiente).json()
    con = conectar()
    con.execute("UPDATE handoff_casos SET prazo_em='2000-01-01T00:00:00.000Z' WHERE id=?", (d["caso_id"],))
    assert ambiente["cli"].get(f"{B}/casos?filtro=atrasados", headers=entra(ambiente["cli"], "ana@urace.us")).json()["total"] == 1
    terca_10h = datetime(2026, 10, 13, 14, 0, tzinfo=timezone.utc)
    feitos = 0
    for i in range(at.TETO_REALERTAS + 3):
        con.execute("UPDATE handoff_casos SET ultimo_realerta=NULL WHERE id=?", (d["caso_id"],))
        feitos += len(at.varrer_atrasos(con, quando=terca_10h))
    assert feitos == at.TETO_REALERTAS
    con.close()


# ------------------------------------------------------------------ I: sem ciclo de mensagens
def test_I_aviso_no_chat_da_equipe_nao_volta_para_o_whatsapp(ambiente, monkeypatch):
    """O aviso entra no chat da equipe com origem 'atendimento'; a ponte do WhatsApp só leva o
    que nasceu no painel ('painel'), então ele nunca é reenviado nem reprocessado."""
    from command_center.api import whatsapp as api_wa
    escalar(ambiente)
    con = conectar()
    m = um(con, "SELECT id FROM team_messages WHERE origem='atendimento' ORDER BY id DESC LIMIT 1")
    con.close()
    monkeypatch.setenv("WA_TOKEN", "t"); monkeypatch.setenv("WA_PHONE_NUMBER_ID", "1"); monkeypatch.setenv("WA_APLICAR", "1")
    api_wa.encaminhar(m["id"])                          # _post continua com pytest.fail: nada sai


# ------------------------------------------------------------------ J: isolamento entre clientes
def test_J_uma_conversa_nao_mexe_na_outra(ambiente, ponte):
    a = escalar(ambiente, lead="600001").json()
    b = escalar(ambiente, lead="600002", reason="reclamação do serviço").json()
    assert a["caso_id"] != b["caso_id"] and b["motivo"] == "reclamacao"
    h = entra(ambiente["cli"], "ana@urace.us")
    ambiente["cli"].post(f"{B}/casos/{a['caso_id']}/assumir", headers=h)
    ambiente["cli"].post(f"{B}/casos/{a['caso_id']}/devolver", json={"texto": "ok"}, headers=h)
    p = sdr.ler_pausas()
    assert "600001" not in p and p["600002"]["handoff"] == b["caso_id"]
    con = conectar()
    assert at.estado_conversa(con, 600001) == "AI_ACTIVE" and at.estado_conversa(con, 600002) == "HUMAN_PENDING"
    det = at.detalhe(con, b["caso_id"])
    assert all(e["tipo"] != "devolvido_ia" for e in det["eventos"])
    con.close()


# ------------------------------------------------------------------ K: autorização
def test_K_chave_de_api_abre_mas_nao_decide(ambiente):
    d = escalar(ambiente).json()
    cli = ambiente["cli"]; cli.cookies.clear()
    for acao, corpo in [("assumir", None), ("encerrar", {"texto": "x"}), ("devolver", {"texto": "x"})]:
        r = cli.post(f"{B}/casos/{d['caso_id']}/{acao}", json=corpo, headers=ambiente["ia"])
        assert r.status_code == 403, (acao, r.text)
    r = cli.post(B + "/casos", json={"conversation_id": 1, "reason": "x", "assume": True}, headers=ambiente["ia"])
    assert r.status_code == 403


def test_K_chave_so_leitura_e_leitor_nao_abrem(ambiente):
    cli = ambiente["cli"]; cli.cookies.clear()
    assert cli.post(B + "/casos", json={"conversation_id": 1, "reason": "x"}, headers=ambiente["leitura"]).status_code == 403
    h = entra(cli, "leitor@urace.us")
    assert cli.post(B + "/casos", json={"conversation_id": 1, "reason": "x"}, headers=h).status_code == 403
    d = escalar(ambiente).json()
    h = entra(cli, "leitor@urace.us")
    assert cli.post(f"{B}/casos/{d['caso_id']}/assumir", headers=h).status_code == 403
    assert cli.get(f"{B}/casos/{d['caso_id']}", headers=h).json()["pode"]["assumir"] is False


def test_K_so_quem_atende_ou_gerente_encerra(ambiente, ponte):
    d = escalar(ambiente).json()
    cli = ambiente["cli"]
    h = entra(cli, "ana@urace.us")
    cli.post(f"{B}/casos/{d['caso_id']}/assumir", headers=h)
    h = entra(cli, "bia@urace.us")
    assert cli.post(f"{B}/casos/{d['caso_id']}/encerrar", json={"texto": "x"}, headers=h).status_code == 403
    assert cli.post(f"{B}/casos/{d['caso_id']}/responder", json={"texto": "x"}, headers=h).status_code == 403
    h = entra(cli, "gerente@urace.us")
    assert cli.post(f"{B}/casos/{d['caso_id']}/encerrar", json={"texto": "Gerente encerrou."}, headers=h).status_code == 200


def test_K_sem_login_nada(ambiente):
    cli = ambiente["cli"]; cli.cookies.clear()
    assert cli.get(B + "/casos").status_code == 401
    assert cli.post(B + "/casos", json={"conversation_id": 1, "reason": "x"}).status_code == 401


def test_K_teto_de_abertura_por_credencial(ambiente, monkeypatch):
    from command_center.api import atendimento as rota
    monkeypatch.setattr(rota, "LIMITE_POR_MIN", 2)
    rota._janela.clear()
    codigos = [escalar(ambiente, lead=str(700000 + i)).status_code for i in range(3)]
    assert codigos == [201, 201, 429]
    rota._janela.clear()


# ------------------------------------------------------------------ fila e retenção
def test_fila_mostra_pendentes_sem_responsavel_e_resolvidos(ambiente, ponte):
    a = escalar(ambiente, lead="800001", priority="low").json()
    b = escalar(ambiente, lead="800002", priority="urgent").json()
    cli = ambiente["cli"]
    h = entra(cli, "ana@urace.us")
    lista = cli.get(f"{B}/casos?filtro=pendentes", headers=h).json()
    ids = [c["id"] for c in lista["itens"]]
    assert ids.index(b["caso_id"]) < ids.index(a["caso_id"])        # urgente primeiro
    assert lista["contagem"]["sem_responsavel"] >= 2
    cli.post(f"{B}/casos/{a['caso_id']}/assumir", headers=h)
    cli.post(f"{B}/casos/{a['caso_id']}/encerrar", json={"texto": "feito"}, headers=h)
    res = cli.get(f"{B}/casos?filtro=resolvidos&limit=5", headers=h).json()
    assert res["itens"][0]["id"] == a["caso_id"] and res["itens"][0]["resultado"] == "feito"
    assert cli.get(f"{B}/casos?filtro=qualquer", headers=h).status_code == 400
    det = cli.get(f"{B}/casos/{a['caso_id']}", headers=h).json()
    assert [e["tipo"] for e in det["eventos"]][:3] == ["criado", "ia_travada", "assumido"]


def test_eventos_sao_append_only(ambiente):
    d = escalar(ambiente).json()
    con = conectar()
    import sqlite3
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE handoff_eventos SET tipo='x' WHERE caso_id=?", (d["caso_id"],))
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM handoff_eventos WHERE caso_id=?", (d["caso_id"],))
    con.close()


def test_retencao_apaga_texto_de_caso_antigo(ambiente, ponte):
    d = escalar(ambiente).json()
    h = entra(ambiente["cli"], "ana@urace.us")
    ambiente["cli"].post(f"{B}/casos/{d['caso_id']}/assumir", headers=h)
    ambiente["cli"].post(f"{B}/casos/{d['caso_id']}/encerrar", json={"texto": "feito"}, headers=h)
    con = conectar()
    con.execute("UPDATE handoff_casos SET fechado_em='2020-01-01T00:00:00.000Z' WHERE id=?", (d["caso_id"],))
    assert at.limpar_retencao(con, dias=365) >= 1
    c = at.caso(con, d["caso_id"])
    assert c["resumo"] is None and c["cliente_nome"] is None and c["estado"] == "RESOLVED"
    con.close()


# ------------------------------------------------------------------ cliente escreveu de novo
def test_cliente_escreve_e_quem_atende_e_avisado_uma_vez(ambiente):
    d = escalar(ambiente).json()
    h = entra(ambiente["cli"], "ana@urace.us")
    ambiente["cli"].post(f"{B}/casos/{d['caso_id']}/assumir", headers=h)
    con = conectar()
    ambiente["avisados"].clear()
    assert at.cliente_escreveu(con, 31764961) == d["caso_id"]
    assert at.cliente_escreveu(con, "31764961") == d["caso_id"]       # 2ª mensagem seguida: sem aviso novo
    assert ambiente["avisados"] == [ambiente["ids"]["ana@urace.us"]]
    assert at.cliente_escreveu(con, 99999999) is None                  # conversa sem caso: nada
    con.close()


def test_hook_do_kommo_avisa_o_atendimento(ambiente, monkeypatch):
    """O cliente escreve no WhatsApp → Kommo → /crm/hook: quem atende recebe o push."""
    d = escalar(ambiente).json()
    h = entra(ambiente["cli"], "ana@urace.us")
    ambiente["cli"].post(f"{B}/casos/{d['caso_id']}/assumir", headers=h)
    ambiente["avisados"].clear()
    vistos = []
    monkeypatch.setattr(at, "cliente_escreveu", lambda con, lead: vistos.append(str(lead)))
    monkeypatch.setattr(crm, "_chave_hook", lambda: "chave-hook")

    class _K:
        def parse_corpo_hook(self, b):
            return {}

        def verificar_token_bot(self, t):
            return True

        def extrair_entrada(self, p):
            return {"lead_id": "31764961", "texto": "Oi, alguém aí?", "nome": "Maria", "telefone": None,
                    "return_url": None, "token": None}
    monkeypatch.setattr(crm, "modulo", lambda s: _K())
    ambiente["cli"].cookies.clear()
    r = ambiente["cli"].post("/ops/api/crm/hook?key=chave-hook", content=b"x")
    assert r.status_code == 200 and vistos == ["31764961"]

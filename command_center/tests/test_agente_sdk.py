"""AI Command no Claude Agent SDK (#152): o portão, o limite, a sessão e o e-mail no Haiku.

Dono, 08/10: "eu não quero mais esse vai e vem ... Gostei desse limite de pedido ... o modelo pode
ser o Opus 5.5 para praticamente tudo. O Haiku fica ali no e-mail. Quando o Haiku tiver
dificuldade, ele aciona o Opus no e-mail também. Mas os dois sempre ligados ao nosso cérebro."

Nada aqui fala com a Anthropic: o cliente do SDK é trocado por um falso.
"""
import json
import os
from types import SimpleNamespace

import pytest

from command_center.api import agente_sdk, ia
from command_center.db import aplicar_schema, conectar, inserir, todos, um


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def _comando(con):
    uid = con.execute("INSERT INTO users (email, name, role, pw_salt, pw_hash) VALUES ('a@urace.us','A','ADMIN','x','x')").lastrowid
    return uid, inserir(con, "ai_commands", user_id=uid, text="t", session_key="s")


# ------------------------------------------------------------------ o portão
def test_classifica_ler_fazer_aprovar_e_bloqueada(con):
    c = agente_sdk.classificar
    for nome in ("qbo_invoices", "qbo_historico_precos", "qbo_clientes_buscar", "asana_tarefa", "gmail_thread",
                 "urace_cliente", "kommo_lead", "docusign_templates"):
        assert c(con, nome) == "ler", nome
    for nome in ("asana_comentar", "asana_criar_tarefa", "asana_mover_para_secao", "asana_concluir", "qbo_criar_invoice",
                 "qbo_criar_estimate", "qbo_criar_cliente", "qbo_criar_item", "gmail_rascunho", "gmail_rotular"):
        assert c(con, nome) == "fazer", nome
    for nome in ("docusign_enviar_waiver", "docusign_reenviar_waiver"):    # política SAFE do dono (21/09; 08/10, #160)
        assert c(con, nome) == "fazer", nome
    for nome in ("qbo_enviar_invoice", "qbo_criar_e_enviar_invoice", "qbo_lembrete_invoice", "docusign_send_reminder", "docusign_anular_envelope",
                 "docusign_substituir_documento_modelo", "qbo_criar_recorrencia", "painel_unir_clientes",
                 "asana_apagar_tarefa", "qbo_atualizar_preco"):
        assert c(con, nome) == "aprovar", nome
    for nome in ("docusign_void", "qbo_apagar", "apagar_cliente"):
        assert c(con, nome) == "bloqueada", nome


def test_envio_vira_um_aprovar_e_nao_roda(con):
    _, cid = _comando(con)
    p = agente_sdk.Portao(cid)
    args = {"id": "77", "email": "cliente@example.com"}
    motivo = p.decidir("mcp__quickbooks__qbo_enviar_invoice", args)
    assert motivo and "aprovação #" in motivo
    a = um(con, "SELECT * FROM ai_actions WHERE command_id=?", (cid,))
    assert (a["action"], a["policy"], a["status"]) == ("qbo_enviar_invoice", "REQUIRES_APPROVAL", "PROPOSED")
    assert json.loads(a["payload"])["args"] == args            # quem aprovar executa exatamente isto
    assert um(con, "SELECT 1 AS x FROM approvals WHERE action_id=? AND decided_at IS NULL", (a["id"],))
    # pedir de novo não duplica o cartão
    assert "esperando aprovação" in p.decidir("mcp__quickbooks__qbo_enviar_invoice", args)
    assert len(todos(con, "SELECT id FROM ai_actions WHERE command_id=?", (cid,))) == 1


def test_bloqueada_nao_roda_nem_vira_cartao(con):
    _, cid = _comando(con)
    motivo = agente_sdk.Portao(cid).decidir("mcp__docusign__docusign_void", {"envelope_id": "x"})
    assert motivo and "bloqueada" in motivo
    assert not todos(con, "SELECT id FROM ai_actions")


def test_interno_e_leitura_rodam_e_o_interno_fica_registrado(con):
    _, cid = _comando(con)
    p = agente_sdk.Portao(cid)
    assert p.decidir("mcp__asana__asana_comentar", {"gid": "1", "texto": "oi"}) is None
    assert p.decidir("mcp__quickbooks__qbo_invoices", {"cliente_id": "9"}) is None
    p.registrar("mcp__asana__asana_comentar", {"gid": "1", "texto": "oi"}, {"aplicado": True})
    p.registrar("mcp__quickbooks__qbo_invoices", {"cliente_id": "9"}, [{"id": "1"}])
    feitas = todos(con, "SELECT action, policy, status FROM ai_actions WHERE command_id=?", (cid,))
    assert [dict(f) for f in feitas] == [{"action": "asana_comentar", "policy": "SAFE", "status": "DONE"}]


def test_le_so_o_cerebro_as_skills_e_o_contexto(con):
    p = agente_sdk.Portao(None, ferramentas=False)
    assert p.decidir("Read", {"file_path": os.path.join(agente_sdk.CEREBRO, "URACE.md")}) is None
    assert p.decidir("Read", {"file_path": "10_PROCESSOS/Pedido de macacão.md"}) is None      # relativo ao cérebro
    assert p.decidir("Grep", {"pattern": "Usman", "path": agente_sdk.SKILLS}) is None
    assert p.decidir("Read", {"file_path": "/etc/passwd"})
    assert p.decidir("Read", {"file_path": "../command_center/api/auth.py"})
    assert p.decidir("Glob", {"pattern": "../**/*.env"})
    assert p.decidir("Glob", {"pattern": "/root/**"})
    # sem comando, nada de ferramenta que escreve; e o que não é liberado não roda
    assert p.decidir("mcp__asana__asana_comentar", {})
    assert p.decidir("Bash", {"command": "ls"})


# --------------------------------------------------------------- a execução
class ClienteFalso:
    """O ClaudeSDKClient de mentira: devolve as mensagens que o teste mandar."""
    chamadas = []

    def __init__(self, mensagens, falha_com_retomar=False):
        self.mensagens, self.falha = mensagens, falha_com_retomar

    def __call__(self, opcoes):
        ClienteFalso.chamadas.append(opcoes)
        if self.falha and opcoes.resume:
            raise RuntimeError("No conversation found with session ID")
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def query(self, prompt):
        self.prompt = prompt

    async def receive_response(self):
        for m in self.mensagens:
            yield m


def _texto(t):
    return type("AssistantMessage", (), {"content": [type("TextBlock", (), {"text": t})()]})()


def _fim(subtipo="success", result="feito", erro=False, custo=0.12, sessao="sess-1", errors=None):
    return type("ResultMessage", (), {"subtype": subtipo, "result": result, "is_error": erro, "total_cost_usd": custo,
                                      "session_id": sessao, "errors": errors})()


@pytest.fixture()
def falso(monkeypatch):
    ClienteFalso.chamadas = []

    def usar(mensagens, **kw):
        f = ClienteFalso(mensagens, **kw)
        monkeypatch.setattr(agente_sdk, "_fabrica_cliente", f)
        return f
    monkeypatch.setattr(agente_sdk, "servidores_mcp", lambda: {})
    return usar


def test_resposta_e_sessao_guardada_e_retomada(con, falso):
    falso([_texto("lendo…"), _fim(result="Comentei na tarefa do Renato.")])
    r = agente_sdk.rodar("comente", "agent:x:web-1-2026-10-08", command_id=None, ferramentas=False)
    assert (r.ok, r.texto, r.sessao) == (True, "Comentei na tarefa do Renato.", "sess-1")
    o = ClienteFalso.chamadas[-1]
    assert o.model == "claude-opus-5-5" and o.max_budget_usd == 2.0 and o.permission_mode == "dontAsk"
    assert o.setting_sources == [] and "Bash" in o.disallowed_tools and o.resume is None
    falso([_fim(sessao="sess-2")])
    agente_sdk.rodar("de novo", "agent:x:web-1-2026-10-08", ferramentas=False)
    assert ClienteFalso.chamadas[-1].resume == "sess-1"             # a mesma conversa do dia
    assert um(con, "SELECT sdk_session FROM ai_sdk_sessions")["sdk_session"] == "sess-2"


def test_sessao_que_sumiu_comeca_outra(con, falso):
    agente_sdk._guardar_sessao("k", "velha")
    falso([_fim(result="ok")], falha_com_retomar=True)
    r = agente_sdk.rodar("x", "k", ferramentas=False)
    assert r.ok and [o.resume for o in ClienteFalso.chamadas] == ["velha", None]


def test_limite_de_dois_dolares_devolve_o_que_fez_e_avisa(con, falso):
    falso([_texto("Criei a tarefa e a invoice."), _fim(subtipo="error_max_budget_usd", result=None)])
    r = agente_sdk.rodar("x", None, ferramentas=False)
    assert r.ok and r.texto.startswith("Criei a tarefa e a invoice.") and "limite de US$ 2" in r.texto
    assert "0.12" not in r.texto                                         # o custo não vai para a tela


def test_erro_do_agente_vira_falha(con, falso):
    falso([_fim(subtipo="error_during_execution", result=None, erro=True, errors=["credit balance is too low"])])
    r = agente_sdk.rodar("x", None, ferramentas=False)
    assert not r.ok and "credit balance" in r.erro
    assert "sem crédito" in ia.motivo_amigavel(r.erro)


def test_ai_command_no_sdk_resolve_de_uma_vez(con, monkeypatch):
    uid, cid = _comando(con)
    pedidos = []
    con.execute("UPDATE action_policies SET policy='REQUIRES_APPROVAL' WHERE action='docusign_enviar_waiver'")  # o clique

    def rodar(prompt, session_key, command_id=None, **kw):
        pedidos.append(prompt)
        agente_sdk.Portao(command_id).decidir("mcp__docusign__docusign_enviar_waiver", {"email": "pai@example.com"})
        return agente_sdk.Resultado(True, "Waiver pronta para enviar: falta o seu aprovar.", subtipo="success", custo=0.3)
    monkeypatch.setattr(ia, "RUNNER", ia.runner_padrao)
    monkeypatch.setattr(ia, "motor_da_ia", lambda: "sdk")
    monkeypatch.setattr(agente_sdk, "rodar", rodar)
    ia._executa(cid, "envie a waiver", "agent:x:web", uid, prompt="envie a waiver\n\nCONTEXTO")
    c = um(con, "SELECT status, output FROM ai_commands WHERE id=?", (cid,))
    assert (c["status"], c["output"]) == ("DONE", "Waiver pronta para enviar: falta o seu aprovar.")
    assert len(pedidos) == 1 and "ACAO:" not in pedidos[0]               # sem protocolo de texto, sem rodadas
    a = um(con, "SELECT action, status, policy FROM ai_actions WHERE command_id=?", (cid,))
    assert (a["action"], a["status"], a["policy"]) == ("docusign_enviar_waiver", "PROPOSED", "REQUIRES_APPROVAL")
    d = json.loads(um(con, "SELECT detail FROM audit_logs WHERE event='ai.command.done'")["detail"])
    assert d["motor"] == "sdk" and d["aprovar"] == 1 and "custo" not in json.dumps(d)


# ------------------------------------------------------------------- e-mail
def test_dificuldade_do_haiku():
    assert agente_sdk.dificuldade("não sei")
    assert agente_sdk.dificuldade('{"itens": [{"id": 1, "principal": null}]}')
    assert agente_sdk.dificuldade('{"itens": [{"id": 1, "marcador": null}]}')
    assert not agente_sdk.dificuldade('{"itens": [{"id": 1, "principal": "Finances/Receipts"}]}')
    assert not agente_sdk.dificuldade('{"itens": []}')


def test_email_no_haiku_e_escala_para_o_opus_quando_ele_tem_dificuldade(monkeypatch):
    chamadas = []

    def rodar(texto, sk, modelo=None, sistema=None, **kw):
        chamadas.append(modelo)
        if modelo == agente_sdk.MODELO_EMAIL:
            return agente_sdk.Resultado(True, haiku)
        return agente_sdk.Resultado(True, '{"itens": [{"id": 1, "principal": "Clientes"}]}')
    monkeypatch.setattr(agente_sdk, "rodar", rodar)
    haiku = '{"itens": [{"id": 1, "principal": "Finances/Receipts"}]}'
    assert agente_sdk.runner_email("triagem", "k") == (True, haiku, None) and chamadas == ["claude-haiku-5-5"]
    chamadas.clear()
    haiku = '{"itens": [{"id": 1, "principal": null}]}'
    ok, texto, _ = agente_sdk.runner_email("triagem", "k")
    assert ok and '"Clientes"' in texto and chamadas == ["claude-haiku-5-5", "claude-opus-5-5"]


def test_os_dois_leem_o_cerebro():
    assert agente_sdk.CEREBRO in agente_sdk.instrucoes() and agente_sdk.CEREBRO in agente_sdk.instrucoes_email()
    assert "America/New_York" in agente_sdk.instrucoes() and "NO FAKE DATA" in agente_sdk.instrucoes()


def test_qual_motor(monkeypatch):
    monkeypatch.setenv("CC_IA_MOTOR", "openclaw")
    assert ia.motor_da_ia() == "openclaw"
    monkeypatch.setenv("CC_IA_MOTOR", "auto")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ia.motor_da_ia() == "openclaw"                          # sem chave, o de antes
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-teste")
    assert ia.motor_da_ia() == "sdk"


def test_email_com_runner_trocado_usa_o_runner(monkeypatch):
    """Quem troca o RUNNER (testes, diagnóstico) continua mandando também no e-mail."""
    monkeypatch.setattr(ia, "RUNNER", lambda t, k: (True, "do runner", None))
    monkeypatch.setattr(ia, "motor_da_ia", lambda: "sdk")
    assert ia.runner_email("x", "k") == (True, "do runner", None)


def test_ferramentas_do_painel_so_leem(monkeypatch):
    import claude_agent_sdk
    criadas = {}
    monkeypatch.setattr(claude_agent_sdk, "create_sdk_mcp_server",
                        lambda nome, versao, tools: criadas.update(nome=nome, tools=[t.name for t in tools]) or {"name": nome})
    agente_sdk.ferramentas_do_painel()
    assert criadas["nome"] == "painel" and "urace_cliente" in criadas["tools"] and "urace_precos_cobrados" in criadas["tools"]
    assert "urace_api" not in criadas["tools"] and "urace_operacoes" not in criadas["tools"]     # operar pede uma pessoa


def test_resultado_sem_fim_e_falha():
    r = agente_sdk._resultado(["x"], None, None, 2)
    assert not r.ok
    assert agente_sdk._resultado([], SimpleNamespace(subtype="error_max_turns", is_error=True, result=None,
                                                     total_cost_usd=1, errors=None), "s", 2).ok


def test_waiver_sai_sozinha_enquanto_a_politica_do_dono_for_safe(con):
    """#160, dono 08/10: "Voltar ao automático já" (a waiver, como na revisão de 21/09)."""
    for nome in ("docusign_enviar_waiver", "docusign_reenviar_waiver", "venda_enviar_waiver"):
        con.execute("INSERT OR REPLACE INTO action_policies (action, policy) VALUES (?, 'SAFE')", (nome,))
        assert agente_sdk.classificar(con, nome) == "fazer", nome
        con.execute("UPDATE action_policies SET policy='REQUIRES_APPROVAL' WHERE action=?", (nome,))
        assert agente_sdk.classificar(con, nome) == "aprovar", nome          # apertou no painel: o clique volta
    con.execute("INSERT OR REPLACE INTO action_policies (action, policy) VALUES ('qbo_enviar_invoice', 'SAFE')")
    assert agente_sdk.classificar(con, "qbo_enviar_invoice") == "aprovar"   # só a waiver; invoice continua no clique

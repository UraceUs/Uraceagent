"""#185: com informação faltando, a IA cria com o que tem e cobra o resto, em rodadas.

Dono, 12/10: *"ao invés de bloquear e não fazer a tarefa, ela coloca a tarefa com as informações
que tem … avisar o usuário que foi criado, mas que precisa colocar as demais informações, e vai
dando rodada de aviso até o usuário completar essas informações faltantes"*.

Nada aqui fala com a Anthropic.
"""
import os
from types import SimpleNamespace

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center import ensaio_ia  # noqa: E402
from command_center.api import agente_sdk, atencao, auth, ia  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, um  # noqa: E402
from command_center.providers import pendencias  # noqa: E402
from command_center.tests.test_balcao import SENHA, entra  # noqa: E402

P = "/ops/api/ai/pendencias"


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    c = conectar(); aplicar_schema(c)
    c.execute("INSERT INTO users (email, name, role, pw_salt, pw_hash) VALUES ('op@urace.us','Op','OPERATOR','x','x')")
    yield c
    c.close()


def _uid(con, email="op@urace.us"):
    return um(con, "SELECT id FROM users WHERE email=?", (email,))["id"]


# ------------------------------------------------------------------ o registro
def test_registra_com_o_que_falta_e_nao_duplica(con):
    uid = _uid(con)
    p = pendencias.registrar(con, "Tarefa: aula do Rafael", ["horário", "e-mail do responsável"], user_id=uid,
                             contato="sem cadastro; pedir a quem indicou")
    assert p["status"] == "aberta" and p["faltando"] == ["horário", "e-mail do responsável"]
    again = pendencias.registrar(con, "Tarefa: aula do Rafael", ["horário"], user_id=uid)
    assert again["id"] == p["id"] and again["faltando"] == ["horário"]
    assert pendencias.abertas(con, uid)["total"] == 1


def test_sem_titulo_ou_sem_o_que_falta_e_erro(con):
    with pytest.raises(pendencias.ErroPendencia):
        pendencias.registrar(con, "", ["horário"])
    with pytest.raises(pendencias.ErroPendencia):
        pendencias.registrar(con, "Tarefa X", [])


def test_campo_do_card_fecha_sozinho_quando_preenchido(con):
    uid = _uid(con)
    cid = inserir(con, "clients", name="Maria Santos", pilot_name="Leo", status="ACTIVE")
    p = pendencias.registrar(con, "Cliente: Maria Santos", [], user_id=uid, client_id=cid, campos=["email", "phone"])
    assert p["status"] == "aberta" and p["faltando"] == ["e-mail", "telefone"]
    con.execute("UPDATE clients SET email='maria@example.com' WHERE id=?", (cid,))
    assert pendencias.conferir(con, p["id"]) is False                       # o telefone ainda falta
    assert pendencias.publica(um(con, "SELECT * FROM ai_pendencias WHERE id=?", (p["id"],)))["faltando"] == ["telefone"]
    con.execute("UPDATE clients SET phone='+1 407 555 0100' WHERE id=?", (cid,))
    assert pendencias.conferir(con, p["id"]) is True
    assert um(con, "SELECT status, resolved_by FROM ai_pendencias WHERE id=?", (p["id"],)) == \
        {"status": "resolvida", "resolved_by": "sistema"}


def test_campo_ja_preenchido_nao_vira_pendencia(con):
    cid = inserir(con, "clients", name="Ana", email="ana@example.com", status="ACTIVE")
    p = pendencias.registrar(con, "Cliente: Ana", [], user_id=_uid(con), client_id=cid, campos=["email"])
    assert p["status"] == "resolvida"


def test_sem_card_o_campo_vira_texto(con):
    p = pendencias.registrar(con, "Tarefa: aula", [], user_id=_uid(con), campos=["phone"])
    assert p["faltando"] == ["telefone"] and p["campos"] == []


def test_cliente_de_outro_id_nao_existe_e_recusado(con):
    with pytest.raises(pendencias.ErroPendencia):
        pendencias.registrar(con, "Tarefa", ["horário"], client_id=999)


# ------------------------------------------------------------------ as rodadas
def test_rodada_avisa_cada_pessoa_e_conta(con):
    uid = _uid(con)
    pendencias.registrar(con, "Tarefa: aula do Rafael", ["horário"], user_id=uid)
    pendencias.registrar(con, "Pedido: macacão do Leo", ["medidas"], user_id=uid)
    avisos = []
    r = pendencias.rodada(con, avisar=lambda c, ids, t, corpo, url: avisos.append((ids, t, corpo, url)))
    assert r == {"ok": True, "pessoas": 1, "abertas": 2}
    assert avisos == [([uid], "Faltam completar 2 registros", "Tarefa: aula do Rafael: falta horário · e mais 1", "/ops/ai")]
    assert {x["rodadas"] for x in pendencias.abertas(con, uid)["itens"]} == {1}
    pendencias.rodada(con, avisar=lambda *a: None)
    assert {x["rodadas"] for x in pendencias.abertas(con, uid)["itens"]} == {2}


def test_resolvida_nao_e_mais_avisada(con):
    uid = _uid(con)
    p = pendencias.registrar(con, "Tarefa: aula", ["horário"], user_id=uid)
    pendencias.resolver(con, p["id"], "ia", "horário 10h")
    avisos = []
    pendencias.rodada(con, avisar=lambda *a: avisos.append(a))
    assert avisos == []


def test_rotina_esta_na_agenda(con):
    from command_center.api import agenda
    assert "pendencias_aviso" in agenda.ROTINAS
    assert um(con, "SELECT schedule FROM automation_rules WHERE name='pendencias_aviso'")["schedule"] == '["09:00","16:00"]'


# ------------------------------------------------------------------ o prompt e a instrução
def test_comando_novo_leva_as_pendencias_de_quem_pede(con):
    uid = _uid(con)
    pendencias.registrar(con, "Tarefa: aula do Rafael", ["horário"], user_id=uid, contato="(407) 555-0100 no Kommo")
    prompt = ia.montar_prompt(con, "o horário do Rafael é 10h", uid)
    assert "PENDÊNCIAS ABERTAS" in prompt and "aula do Rafael: falta horário" in prompt and "pendencia_resolver" in prompt
    assert "PENDÊNCIAS ABERTAS" not in ia.montar_prompt(con, "oi", None)


def test_instrucao_manda_criar_com_o_que_tem():
    txt = agente_sdk.instrucoes()
    assert "Nunca trave por falta de informação" in txt and "pendencia_registrar" in txt
    assert "Só pergunte o que realmente impede agir, numa lista curta, e pare." not in txt
    assert "NO FAKE DATA" in txt


def test_ferramentas_das_pendencias_sao_trabalho_interno(con):
    assert agente_sdk.classificar(con, "pendencia_registrar") == "fazer"
    assert agente_sdk.classificar(con, "pendencia_resolver") == "fazer"
    assert agente_sdk.classificar(con, "pendencias_abertas") == "ler"
    nomes = [f[0] for f in pendencias.ferramentas_ia()]
    assert nomes == ["pendencia_registrar", "pendencia_resolver", "pendencias_abertas"]
    registrar = pendencias.ferramentas_ia()[0][4]
    p = registrar(con, _uid(con), None, titulo="Tarefa: aula", faltando=["horário"])
    assert p["user_id"] == _uid(con)


def test_atencao_mostra_as_pendencias(con):
    pendencias.registrar(con, "Tarefa: aula do Rafael", ["horário"], user_id=_uid(con))
    itens = [i for i in atencao.coletar(con) if i["entity"]["type"] == "ai_pendencia"]
    assert len(itens) == 1 and "informação faltando" in itens[0]["title"]


# ------------------------------------------------------------------ a tela
@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "op@urace.us", "Op", "OPERATOR", SENHA)
    auth.criar_usuario(c, "op2@urace.us", "Op2", "OPERATOR", SENHA)
    auth.criar_usuario(c, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    pendencias.registrar(c, "Tarefa: aula do Rafael", ["horário"], user_id=_uid(c))
    c.commit(); c.close()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def test_tela_lista_as_minhas_e_completei_fecha(cli):
    h = entra(cli, "op@urace.us")
    r = cli.get(P).json()
    assert r["total"] == 1 and r["itens"][0]["faltando"] == ["horário"]
    entra(cli, "op2@urace.us")
    assert cli.get(P).json()["total"] == 0                                   # cada um vê as suas
    h2 = {"X-CSRF": cli.cookies.get("cc_csrf")}
    assert cli.post(f"{P}/{r['itens'][0]['id']}/resolver", json={}, headers=h2).status_code == 404
    entra(cli, "ger@urace.us")
    assert cli.get(P + "?todas=1").json()["total"] == 1
    h = entra(cli, "op@urace.us")
    x = cli.post(f"{P}/{r['itens'][0]['id']}/resolver", json={"resolucao": "10h"}, headers=h).json()
    assert x["status"] == "resolvida" and x["resolucao"] == "10h"
    assert cli.get(P).json()["total"] == 0


# ------------------------------------------------------------------ o ensaio do VPS
def test_ensaio_nao_grava_e_guarda_o_que_tentou(con):
    p = agente_sdk.Portao(None, True, None, ensaio=True)
    motivo = p.decidir("mcp__asana__asana_criar_tarefa", {"nome": "Aula Rafael"})
    assert motivo and "MODO ENSAIO" in motivo
    assert p.decidir("mcp__quickbooks__qbo_enviar_invoice", {"id": "1"}).startswith("MODO ENSAIO")
    assert p.decidir("mcp__pendencias__pendencia_registrar", {"titulo": "x", "faltando": ["y"]}).startswith("MODO ENSAIO")
    assert p.decidir("mcp__quickbooks__qbo_invoices", {}) is None             # leitura roda de verdade
    assert [t["ferramenta"] for t in p.tentou] == ["asana_criar_tarefa", "qbo_enviar_invoice", "pendencia_registrar"]
    assert um(con, "SELECT COUNT(*) AS n FROM ai_actions")["n"] == 0 and um(con, "SELECT COUNT(*) AS n FROM approvals")["n"] == 0
    p.registrar("mcp__quickbooks__qbo_invoices", {}, [{"email": "real@example.com"}])
    assert "real@example.com" in p.lido[0]


def _res(texto="Criei a tarefa. Falta: horário.", ok=True):
    return SimpleNamespace(ok=ok, texto=texto, erro=None)


def test_avaliar_aprova_quem_cria_anota_e_avisa():
    tentou = [{"ferramenta": "asana_criar_tarefa", "tipo": "fazer", "args": {"nome": "Aula Rafael", "email": "rafa@example.com"}},
              {"ferramenta": "pendencia_registrar", "tipo": "fazer", "args": {"titulo": "Aula", "faltando": ["horário"]}}]
    out = ensaio_ia.avaliar({"pedido": "aula pro Rafael"}, _res(), tentou, ['{"email": "rafa@example.com"}'])
    assert all(ok for ok, _ in out), out


def test_avaliar_reprova_quem_trava_inventa_ou_pede_o_que_ja_tem():
    out = dict((f, ok) for ok, f in ensaio_ia.avaliar({"pedido": "aula"}, _res("Qual o horário?"), [], []))
    assert out["não criou nada (travou por falta de informação)"] is False
    assert out["não anotou o que falta (pendencia_registrar)"] is False
    assert out["a resposta não diz o que falta"] is False
    tentou = [{"ferramenta": "qbo_criar_cliente", "tipo": "fazer", "args": {"email": "inventado@example.com", "fone": "(407) 555-0199"}},
              {"ferramenta": "pendencia_registrar", "tipo": "fazer", "args": {"titulo": "x", "campos": ["email"]}}]
    out = ensaio_ia.avaliar({"pedido": "cliente Leo", "nao_pode_faltar": ["email"]}, _res(), tentou, ["nada"])
    frases = [f for ok, f in out if not ok]
    assert any("INVENTOU" in f and "inventado@example.com" in f and "555-0199" in f for f in frases)
    assert "pediu o email, que já estava no cadastro" in frases


def test_ensaio_monta_os_cenarios_com_cliente_real_sem_gravar(con):
    inserir(con, "clients", name="Maria Santos", pilot_name="Leo Santos", email="familia@example.com", status="ACTIVE")
    con.commit()
    nomes = [c["pedido"] for c in ensaio_ia.cenarios(con)]
    assert len(nomes) == 3 and "Leo Santos" in nomes[1]

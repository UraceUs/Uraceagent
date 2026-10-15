"""Robô SDR (dono, 12/10): "uma sessão robô SDR onde ele consiga ligar e desligar, passar o que
precisa ser feito pelo robô, reportar alguma coisa, gerir o robô".

Instruções (MANAGER+), relatos (qualquer um), o arquivo que a ponte lê, o texto para o agente
do Kommo e a auditoria da ponte lida só em leitura."""
import json
import os
import sqlite3
import tempfile
import time

import pytest
from fastapi.testclient import TestClient

from command_center.api import auth, sdr
from command_center.api.main import app
from command_center.db import aplicar_schema, conectar, um

B = "/ops/api"
SENHA = "senha-forte-123"


@pytest.fixture(scope="module")
def cli():
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc-sdr-painel.sqlite")
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "admin@urace.us", "Admin", "ADMIN", SENHA)
    auth.criar_usuario(con, "gerente@urace.us", "Gerente", "MANAGER", SENHA)
    auth.criar_usuario(con, "op@urace.us", "Operador", "OPERATOR", SENHA)
    con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post(B + "/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


@pytest.fixture(scope="module")
def pasta(tmp_path_factory):
    p = tmp_path_factory.mktemp("urace")
    os.environ["URACE_DIR"] = str(p)
    (p / "bridge.env").write_text("KOMMO_TOKEN=segredo-123\nSDR_MODO=observar\n")
    sdr.ponte_no_ar = lambda: True
    sdr.instalado = lambda: True
    return p


# ------------------------------------------------------------------ instruções
def test_operador_le_mas_nao_escreve_instrucao(cli, pasta):
    h = entra(cli, "op@urace.us")
    assert cli.get(B + "/sdr/instrucoes").status_code == 200
    assert cli.post(B + "/sdr/instrucoes", json={"categoria": "tom", "texto": "curto"}, headers=h).status_code == 403
    assert not (pasta / "sdr_instrucoes.md").exists()


def test_gerente_escreve_e_o_arquivo_da_ponte_nasce(cli, pasta):
    h = entra(cli, "gerente@urace.us")
    r = cli.post(B + "/sdr/instrucoes", json={"categoria": "tom", "texto": "Responda curto,  em português."}, headers=h)
    assert r.status_code == 201
    i = r.json()
    assert (i["status"], i["quem"], i["aviso_preco"], i["em_vigor"]) == ("ativa", "Gerente", False, 1)
    assert (pasta / "sdr_instrucoes.md").read_text() == "- [tom] Responda curto, em português.\n"
    r = cli.post(B + "/sdr/instrucoes", json={"categoria": "preco", "texto": "A aula custa $500 e o preço inclui o kart"}, headers=h)
    assert r.status_code == 201 and r.json()["aviso_preco"] is True, "aceita, mas avisa que preço vem da tabela"
    assert (pasta / "sdr_instrucoes.md").read_text().splitlines() == [
        "- [preço e condições] A aula custa $500 e o preço inclui o kart", "- [tom] Responda curto, em português."]
    lista = cli.get(B + "/sdr/instrucoes").json()
    assert [x["categoria"] for x in lista["itens"]] == ["preco", "tom"] and lista["aviso_preco"].startswith("Preço vem da tabela")
    a = um(conectar(), "SELECT detail FROM audit_logs WHERE event='sdr.instrucao' ORDER BY id DESC LIMIT 1")
    assert '"criada"' in a["detail"]


def test_categoria_e_tamanho_sao_validados(cli, pasta):
    h = entra(cli, "gerente@urace.us")
    assert cli.post(B + "/sdr/instrucoes", json={"categoria": "xyz", "texto": "a"}, headers=h).status_code == 400
    assert cli.post(B + "/sdr/instrucoes", json={"categoria": "tom", "texto": "x" * 1001}, headers=h).status_code == 400
    assert cli.post(B + "/sdr/instrucoes", json={"categoria": "tom", "texto": "  "}, headers=h).status_code == 400


def test_aplicada_continua_no_arquivo_e_arquivada_sai(cli, pasta):
    h = entra(cli, "gerente@urace.us")
    tom = next(x for x in cli.get(B + "/sdr/instrucoes").json()["itens"] if x["categoria"] == "tom")
    r = cli.patch(f"{B}/sdr/instrucoes/{tom['id']}", json={"status": "aplicada"}, headers=h)
    assert r.status_code == 200 and r.json()["applied_at"] and r.json()["aplicada_por"] == "Gerente"
    assert "- [tom]" in (pasta / "sdr_instrucoes.md").read_text(), "aplicada no Kommo ainda vale para a ponte"
    r = cli.patch(f"{B}/sdr/instrucoes/{tom['id']}", json={"status": "arquivada"}, headers=h)
    assert r.status_code == 200 and r.json()["archived_at"]
    assert "- [tom]" not in (pasta / "sdr_instrucoes.md").read_text()
    assert [x["id"] for x in cli.get(B + "/sdr/instrucoes", params={"status": "arquivada"}).json()["itens"]] == [tom["id"]]
    assert cli.patch(f"{B}/sdr/instrucoes/{tom['id']}", json={"status": "nada"}, headers=h).status_code == 400
    assert cli.patch(f"{B}/sdr/instrucoes/9999", json={"status": "arquivada"}, headers=h).status_code == 404
    entra(cli, "op@urace.us")
    h2 = {"X-CSRF": cli.cookies.get("cc_csrf")}
    assert cli.patch(f"{B}/sdr/instrucoes/{tom['id']}", json={"status": "ativa"}, headers=h2).status_code == 403


def test_texto_para_o_kommo_quebra_em_linhas_de_300(cli, pasta):
    h = entra(cli, "gerente@urace.us")
    longo = " ".join(f"palavra{n}" for n in range(80))                  # ~720 caracteres
    cli.post(B + "/sdr/instrucoes", json={"categoria": "nunca", "texto": longo}, headers=h)
    r = cli.get(B + "/sdr/instrucoes/texto-kommo").json()
    linhas = r["texto"].splitlines()
    assert r["limite_por_linha"] == 300 and all(len(x) <= 300 for x in linhas)
    assert linhas[0].startswith("[nunca dizer] palavra0") and r["linhas"] == len(linhas) >= 4
    assert any(x.startswith("[preço e condições]") for x in linhas)
    assert not any("[tom]" in x for x in linhas), "arquivada não vai para o Kommo"


# ------------------------------------------------------------------ relatos
def test_qualquer_um_relata_e_so_gerente_resolve(cli, pasta):
    h = entra(cli, "op@urace.us")
    r = cli.post(B + "/sdr/relatos", json={"tipo": "preco_errado", "texto": "disse 400 para a aula", "lead_ref": " 5001 "}, headers=h)
    assert r.status_code == 201
    x = r.json()
    assert (x["status"], x["quem"], x["lead_ref"], x["tipo"]) == ("aberto", "Operador", "5001", "preco_errado")
    assert cli.post(B + "/sdr/relatos", json={"tipo": "qualquer", "texto": "x"}, headers=h).status_code == 400
    assert cli.patch(f"{B}/sdr/relatos/{x['id']}", json={"status": "resolvido"}, headers=h).status_code == 403
    assert cli.get(B + "/dashboard").json()["sdr_relatos_abertos"] == 1, "o menu acende"
    h = entra(cli, "gerente@urace.us")
    r = cli.patch(f"{B}/sdr/relatos/{x['id']}", json={"status": "resolvido"}, headers=h)
    assert r.status_code == 200 and r.json()["resolved_at"] and r.json()["resolvido_por"] == "Gerente"
    assert cli.get(B + "/dashboard").json()["sdr_relatos_abertos"] == 0
    assert cli.get(B + "/sdr/relatos").json()["abertos"] == 0
    assert cli.get(B + "/sdr/relatos", params={"status": "resolvido"}).json()["itens"][0]["id"] == x["id"]
    a = um(conectar(), "SELECT detail FROM audit_logs WHERE event='sdr.relato' ORDER BY id DESC LIMIT 1")
    assert '"resolvido"' in a["detail"]


# ------------------------------------------------------------------ auditoria da ponte e painel
def _ponte_db(pasta, linhas):
    con = sqlite3.connect(pasta / "salesbridge.db")
    con.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, lead_id INTEGER, kind TEXT NOT NULL, detail TEXT)")
    con.executemany("INSERT INTO audit (ts, lead_id, kind, detail) VALUES (?,?,?,?)", linhas)
    con.commit(); con.close()


def test_sem_banco_da_ponte_e_ponte_sem_auditoria(cli, pasta):
    entra(cli, "op@urace.us")
    assert cli.get(B + "/sdr/auditoria").json() == {"itens": [], "motivo": "ponte sem auditoria"}
    p = cli.get(B + "/sdr/painel").json()
    assert p["ponte_sem_auditoria"] and p["decisoes_24h"] is None and p["ultima_decisao"] is None
    assert (p["nivel"], p["pode_trocar"], p["pode_instruir"]) == ("observar", False, False)
    assert p["horario_humano"]["texto"] == "seg–sex 8h–18h (Orlando)" and p["instrucoes_em_vigor"] == 2


def test_auditoria_le_a_ponte_so_em_leitura_e_filtra(cli, pasta):
    agora = int(time.time())
    _ponte_db(pasta, [
        (agora - 60, 5001, "sdr", json.dumps({"modo": "observar", "lead_id": 5001, "acao": "organizar", "motivo": "LEAD_NOVO",
                                              "moveu": "Qualificação", "tags": ["academy"], "nota": True, "tarefa": False})),
        (agora - 30, 5002, "sdr", json.dumps({"modo": "observar", "acao": "marcar_nao_e_lead", "motivo": "SPAM", "tags": ["não é lead"]})),
        (agora - 3 * 86400, 5001, "sdr", json.dumps({"ignorado": "SEM_NOME"})),
        (agora - 10, 5001, "inbound", "oi"),
    ])
    entra(cli, "op@urace.us")
    r = cli.get(B + "/sdr/auditoria").json()
    assert [x["lead_id"] for x in r["itens"]] == [5002, 5001, 5001] and r["acoes"] == ["ignorado", "marcar_nao_e_lead", "organizar"]
    x = r["itens"][1]
    assert (x["acao"], x["motivo"], x["nivel"], x["fez"]) == ("organizar", "LEAD_NOVO", "observar", "etapa → Qualificação · tags: academy · nota")
    assert x["quando"].endswith("-04:00") or x["quando"].endswith("-05:00"), "hora em Orlando"
    assert [x["lead_id"] for x in cli.get(B + "/sdr/auditoria", params={"lead": "5002"}).json()["itens"]] == [5002]
    assert [x["acao"] for x in cli.get(B + "/sdr/auditoria", params={"acao": "ignorado"}).json()["itens"]] == ["ignorado"]
    assert len(cli.get(B + "/sdr/auditoria", params={"n": 1}).json()["itens"]) == 1
    p = cli.get(B + "/sdr/painel").json()
    assert p["decisoes_24h"] == 2 and p["ultima_decisao"].startswith(time.strftime("%Y-")) and not p["ponte_sem_auditoria"]
    assert oct(os.stat(pasta / "salesbridge.db").st_mode & 0o777) != "", "o painel não mexe no banco da ponte"
    con = sqlite3.connect(pasta / "salesbridge.db")
    assert con.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == 4
    con.close()


def test_filtro_por_lead_e_contagem_nao_ficam_presos_as_linhas_mais_recentes(cli, pasta):
    """Os filtros são no SQL: um lead antigo, atrás de 300 decisões de outro, continua sendo achado,
    e a contagem das 24 h conta tudo, não só um lote."""
    agora = int(time.time())
    _ponte_db(pasta, [(agora - 20000, 7007, "sdr", json.dumps({"acao": "organizar", "motivo": "ANTIGO"}))]
              + [(agora - 100 + i // 10, 5001, "sdr", json.dumps({"acao": "organizar", "motivo": f"N{i}"})) for i in range(300)])
    entra(cli, "op@urace.us")
    r = cli.get(B + "/sdr/auditoria", params={"lead": "7007"}).json()
    assert [x["motivo"] for x in r["itens"]] == ["ANTIGO"]
    assert len(cli.get(B + "/sdr/auditoria", params={"n": 200}).json()["itens"]) == 200
    assert cli.get(B + "/sdr/painel").json()["decisoes_24h"] == 303


def test_admin_troca_o_nivel_e_o_painel_mostra(cli, pasta):
    h = entra(cli, "admin@urace.us")
    assert cli.get(B + "/sdr/painel").json()["pode_trocar"] is True
    assert cli.put(B + "/sdr", json={"nivel": "organizar"}, headers=h).status_code == 200
    assert cli.get(B + "/sdr/painel").json()["nivel"] == "organizar"
    assert "KOMMO_TOKEN=segredo-123" in (pasta / "bridge.env").read_text(), "o token continua"
    cli.put(B + "/sdr", json={"nivel": "observar"}, headers=h)


# ------------------------------------------------------------------ IA pausada por conversa (13/10)
def test_quem_atende_pausa_e_reativa_a_ia_numa_conversa(cli, pasta):
    """Dono, 13/10: desativar pelo Command Center as respostas da IA numa conversa específica.
    O arquivo ~/.urace/sdr_pausas.json é o que a ponte lê a cada mensagem."""
    arq = pasta / "sdr_pausas.json"
    arq.unlink(missing_ok=True)
    con = conectar()
    if not um(con, "SELECT id FROM users WHERE email='ver@urace.us'"):
        auth.criar_usuario(con, "ver@urace.us", "Só vê", "VIEWER", SENHA)
        con.commit()
    con.close()
    h = entra(cli, "ver@urace.us")
    assert cli.put(B + "/sdr/pausas/31764961", json={"pausada": True}, headers=h).status_code == 403
    assert not arq.exists()

    h = entra(cli, "op@urace.us")
    assert cli.get(B + "/sdr/pausas").json() == {"itens": []}
    r = cli.put(B + "/sdr/pausas/31764961", json={"pausada": True, "motivo": "  Lucas assumiu   a conversa "}, headers=h)
    assert r.status_code == 200 and r.json() == {"lead_id": 31764961, "pausada": True, "total": 1}
    d = json.loads(arq.read_text(encoding="utf-8"))
    assert d["31764961"]["por"] == "Operador" and d["31764961"]["motivo"] == "Lucas assumiu a conversa"
    assert d["31764961"]["em"].endswith(("-04:00", "-05:00")), "hora em Orlando"
    assert oct(arq.stat().st_mode & 0o777) == "0o644", "a ponte (outro usuário de serviço) precisa ler"
    cli.put(B + "/sdr/pausas/34233393", json={"pausada": True}, headers=h)
    itens = cli.get(B + "/sdr/pausas").json()["itens"]
    assert {i["lead_id"] for i in itens} == {31764961, 34233393}
    assert cli.get(B + "/sdr/painel").json()["conversas_pausadas"] == 2

    assert cli.put(B + "/sdr/pausas/31764961", json={"pausada": False}, headers=h).json()["total"] == 1
    assert "31764961" not in json.loads(arq.read_text(encoding="utf-8"))
    assert cli.put(B + "/sdr/pausas/0", json={"pausada": True}, headers=h).status_code == 400
    assert cli.put(B + "/sdr/pausas/5", json={"pausada": True, "x": 1}, headers=h).status_code == 422
    a = um(conectar(), "SELECT detail, entity_id FROM audit_logs WHERE event='sdr.pausa' ORDER BY id DESC LIMIT 1")
    assert '"pausada": false' in a["detail"] and str(a["entity_id"]) == "31764961", "a reativação fica no histórico"

    arq.write_text("{ quebrado", encoding="utf-8")
    assert cli.get(B + "/sdr/pausas").json() == {"itens": []}, "arquivo ilegível não derruba o painel"
    arq.unlink()


# ------------------------------------------------------------------ testar o robô (14/10)
def test_testar_o_robo_pelo_painel_sem_kommo(cli, pasta, monkeypatch):
    """Conversa de treino: o painel repassa à ponte com a chave do bridge.env, devolve os balões
    e o que a ponte faria, e registra na auditoria sem a chave."""
    (pasta / "bridge.env").write_text("SDR_MODO=atender\nAGENT_API_KEY=chave-secreta-xyz\n", encoding="utf-8")
    pedidos = []

    class _Resp:
        def __init__(self, corpo):
            self.corpo = corpo

        def read(self):
            return json.dumps(self.corpo).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(req, timeout=0):
        pedidos.append((req.full_url, req.headers.get("X-api-key"), json.loads(req.data)))
        return _Resp({"ok": True, "mensagens": ["Oi! Aqui é o Chase, da URACE.", "É pra você ou pra outra pessoa?"],
                      "rota": "responder", "motivo": None, "diretivas": [], "cortes": [], "nota": ""})

    monkeypatch.setattr(sdr.urllib.request, "urlopen", _urlopen)
    con = conectar()
    if not um(con, "SELECT id FROM users WHERE email='ver@urace.us'"):
        auth.criar_usuario(con, "ver@urace.us", "Só vê", "VIEWER", SENHA)
        con.commit()
    con.close()
    h = entra(cli, "ver@urace.us")
    assert cli.post(B + "/sdr/teste", json={"sessao": "cc-abc123", "texto": "oi"}, headers=h).status_code == 403

    h = entra(cli, "op@urace.us")
    r = cli.post(B + "/sdr/teste", json={"sessao": "cc-abc123", "texto": "  Oi,   quanto custa? "}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["mensagens"] == ["Oi! Aqui é o Chase, da URACE.", "É pra você ou pra outra pessoa?"]
    url, chave, corpo = pedidos[-1]
    assert url.endswith("/tools/playground") and chave == "chave-secreta-xyz"
    assert corpo == {"sessao": "cc-abc123", "texto": "Oi, quanto custa?", "nome": ""}
    a = um(conectar(), "SELECT detail FROM audit_logs WHERE event='sdr.teste' ORDER BY id DESC LIMIT 1")
    assert "quanto custa" in a["detail"] and "chave-secreta" not in a["detail"], "a chave nunca vai pra auditoria"
    assert cli.post(B + "/sdr/teste", json={"sessao": "../x", "texto": "oi"}, headers=h).status_code == 400
    assert cli.post(B + "/sdr/teste", json={"sessao": "cc-abc123", "texto": "  "}, headers=h).status_code == 400

    (pasta / "bridge.env").write_text("SDR_MODO=atender\n", encoding="utf-8")
    assert cli.post(B + "/sdr/teste", json={"sessao": "cc-abc123", "texto": "oi"}, headers=h).status_code == 503


def test_testar_o_robo_tem_limite_por_minuto(cli, pasta, monkeypatch):
    """Cada teste é uma chamada ao modelo: 12 por minuto por pessoa, depois espera."""
    (pasta / "bridge.env").write_text("SDR_MODO=atender\nAGENT_API_KEY=chave-secreta-xyz\n", encoding="utf-8")

    class _Resp:
        def read(self):
            return b'{"ok": true, "mensagens": ["Oi!"], "rota": "responder", "diretivas": [], "cortes": [], "nota": ""}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(sdr.urllib.request, "urlopen", lambda req, timeout=0: _Resp())
    sdr._teste_recente.clear()
    h = entra(cli, "op@urace.us")
    codigos = [cli.post(B + "/sdr/teste", json={"sessao": "cc-limite01", "texto": f"oi {i}"}, headers=h).status_code
               for i in range(sdr.TESTE_POR_MINUTO + 2)]
    assert codigos[:sdr.TESTE_POR_MINUTO] == [200] * sdr.TESTE_POR_MINUTO
    assert codigos[sdr.TESTE_POR_MINUTO:] == [429, 429]
    # passado um minuto, libera de novo
    agora = time.time()
    assert sdr._teste_liberado(1, agora + 120) is True
    sdr._teste_recente.clear()

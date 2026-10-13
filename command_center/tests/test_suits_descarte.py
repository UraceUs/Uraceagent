"""#195: pedido que não é de macacão sai das listas e da ponte, e o e-mail só vira candidato quando fala de suit.

Dono, 13/10: *"do Frank pra cima, nenhum desse aí foi e-mail de suit … Vai estar claro na mensagem,
no corpo ou no título do e-mail que vai ser um pedido de suit … Então, cessa isso, limpa esses daí."*
Os pedidos #153 a #163 do VPS foram abertos pela ponte antiga só pelo marcador Suits, com o remetente
(noreply da OpenAI, cobrança do Stripe, o próprio eduardo@urace.us) no lugar do cliente.
"""
import pytest
from fastapi.testclient import TestClient

from command_center import manage
from command_center.api import auth
from command_center.api import suits as api_suits
from command_center.api.main import app
from command_center.db import aplicar_schema, conectar, todos, um
from command_center.providers import suits, suits_ponte as sp
from command_center.tests.test_suits_ponte import SENHA, Gmail, _executor


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "descarte.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path / "urace"))
    monkeypatch.setenv("CC_EMAIL_FAKE", str(tmp_path / "enviados.jsonl"))
    c = conectar(); aplicar_schema(c)
    c.execute("INSERT INTO users (email, name, role, pw_salt, pw_hash) VALUES ('a@urace.us','Admin','ADMIN','x','x')")
    yield c
    c.close()


def _lixo(con, titulo, email, thread):
    """Como a ponte antiga deixou: o remetente no lugar do cliente e a conversa ligada."""
    return con.execute("INSERT INTO suit_orders (title, customer_name, customer_email, gmail_thread_cliente, source) "
                       "VALUES (?,?,?,?, 'email')", (titulo, titulo, email, thread)).lastrowid


OPENAI = {"message_id": "o2", "de": "OpenAI <noreply@tm.openai.com>", "assunto": "Your OpenAI Ads invoice",
          "corpo": "Invoice INV-0CG1 is available."}


# ------------------------------------------------------------------ a ponte para de ler
def test_robo_e_a_equipe_nunca_sao_o_cliente_de_um_pedido(con):
    """Antes do descarte já não pode: e-mail novo da OpenAI virava 'o cliente respondeu' no pedido OpenAI."""
    _lixo(con, "OpenAI", "noreply@tm.openai.com", "t-openai-velha")
    _lixo(con, "Eduardo Resende", "eduardo@urace.us", "t-edu-velha")
    gm, chamadas = Gmail(), []
    gm.threads = {"t-openai-nova": [OPENAI],
                  "t-edu-nova": [{"message_id": "e1", "de": "Eduardo <eduardo@urace.us>", "assunto": "horário de sábado", "corpo": "ok"}]}
    gm.buscas = {"noreply@tm.openai.com": ["t-openai-nova"], "eduardo@urace.us": ["t-edu-nova"]}
    r = sp.rodar(con, gm, _executor(chamadas))
    assert r["eventos"] == 0 and chamadas == []
    assert um(con, "SELECT COUNT(*) AS n FROM suit_notes")["n"] == 0


def test_pedido_descartado_nao_recebe_mais_nada_da_ponte(con):
    pid = _lixo(con, "Points Insider", "hello@pointsinsider.example", "t-points")
    gm, chamadas = Gmail(), []
    gm.threads = {"t-points": [{"message_id": "p1", "de": "Points Insider <hello@pointsinsider.example>", "assunto": "Deals this week",
                                "corpo": "Fly business for less"}],
                  "t-points-2": [{"message_id": "p2", "de": "Points Insider <hello@pointsinsider.example>", "assunto": "More deals",
                                  "corpo": "Fly first for less"}]}
    gm.buscas = {"label:Suits": ["t-points"], "hello@pointsinsider.example": ["t-points-2"]}
    assert suits.descartar(con, pid, "newsletter de milhas") is True
    assert suits.descartar(con, pid) is False, "descartar de novo não repete nada"
    r = sp.rodar(con, gm, _executor(chamadas))
    assert r["eventos"] == 0 and chamadas == []
    notas = [n["text"] for n in todos(con, "SELECT text FROM suit_notes WHERE order_id=?", (pid,))]
    assert len(notas) == 1 and notas[0].startswith("Descartado: newsletter de milhas")
    p = um(con, "SELECT closed, status, discard_reason FROM suit_orders WHERE id=?", (pid,))
    assert (p["closed"], p["status"], p["discard_reason"]) == (1, "standby", "newsletter de milhas")
    assert um(con, "SELECT gmail_thread_cliente FROM suit_orders WHERE id=?", (pid,))["gmail_thread_cliente"] == "t-points", \
        "nada é apagado: a conversa continua registrada (e pulada)"


def test_descartado_nao_manda_email_nem_simula(con):
    pid = _lixo(con, "Stripe", "support@stripe.example", "t-stripe")
    suits.descartar(con, pid)
    with pytest.raises(sp.Recusado):
        sp.enviar(con, pid, "cliente", "Hi", "Thanks for your order")
    with pytest.raises(sp.Recusado):
        sp.simular_pedido(con, pid, Gmail(), _executor([]))


def test_descartar_fecha_o_aviso_de_precisa_humano(con):
    pid = _lixo(con, "RaceSelect", "info@raceselect.example", "t-rs")
    sp.precisa_humano(con, pid, "pediu reembolso?")
    suits.descartar(con, pid)
    assert um(con, "SELECT status FROM ai_events WHERE kind='suit.humano' AND entity_id=?", (pid,))["status"] == "SKIPPED"


def test_restaurar_volta_para_a_lista(con):
    pid = _lixo(con, "Alexa Lloret", "alexa@example.com", "t-alexa")
    suits.descartar(con, pid)
    assert suits.restaurar(con, pid) is True and suits.restaurar(con, pid) is False
    p = um(con, "SELECT closed, discarded_at FROM suit_orders WHERE id=?", (pid,))
    assert (p["closed"], p["discarded_at"]) == (0, None)


# ------------------------------------------------------------------ só e-mail que fala de suit
def test_marcador_sem_falar_de_macacao_nem_chega_a_ia(con):
    gm, chamadas = Gmail(), []
    gm.threads = {
        "t-carlos": [{"message_id": "c1", "de": "Daneyza Cabrera <daneyza@example.com>", "assunto": "Re: Carlos David Garcia",
                      "corpo": "Confirmo o horário de sábado, 10/10."}],
        "t-stripe": [{"message_id": "s1", "de": "Stripe <receipts@stripe.example>", "assunto": "Your receipt from URACE suits store",
                      "corpo": "Receipt #1234 for a race suit"}],
        "t-ryan": [{"message_id": "r1", "de": "Ryan <ryan@example.com>", "assunto": "Custom race suit", "corpo": "How much?"}],
        "t-joao": [{"message_id": "j1", "de": "João <joao@example.com>", "assunto": "Orçamento",
                    "corpo": "Quero fazer um macacão para o meu filho"}],
        "t-ana": [{"message_id": "a1", "de": "Ana <ana@example.es>", "assunto": "Consulta", "corpo": "Necesito un mono de karting"}]}
    gm.buscas = {"label:Suits": list(gm.threads)}
    r = sp.rodar(con, gm, _executor(chamadas))
    assert sorted(x["thread_id"] for x in r["nao_sao_de_suit"]) == ["t-carlos", "t-stripe"], "sem suit no texto, ou robô"
    assert len(chamadas) == 3 and {c["texto"].split(": ")[-1] for c in chamadas} == {"marcador"}
    assert um(con, "SELECT papel FROM suit_email_seen WHERE message_id='c1'")["papel"] == "nao_suit"
    assert sp.rodar(con, gm, _executor(chamadas))["nao_sao_de_suit"] == [], "lido uma vez e esquecido"
    assert todos(con, "SELECT id FROM suit_orders") == []


def test_o_que_fala_de_suit_e_o_que_e_robo():
    assert sp.fala_de_suit([{"assunto": "Race Suit order", "corpo": ""}])
    assert sp.fala_de_suit([{"assunto": "", "corpo": "Preciso de dois macacões"}])
    assert sp.fala_de_suit([{"assunto": "Combinaison sur mesure", "corpo": ""}])
    assert not sp.fala_de_suit([{"assunto": "Hotel suite upgrade", "corpo": "is this suitable? lawsuit"}])
    assert not sp.fala_de_suit([{"assunto": "OpenAI Ads Invoice", "corpo": "Invoice available"}])
    assert sp.robo("noreply@tm.openai.com") and sp.robo("no-reply@x.com") and sp.robo("receipts+abc@stripe.com")
    assert sp.robo("billing@anthropic.com") and sp.robo("newsletter@raceselect.com")
    assert not sp.robo("ryan@example.com") and not sp.robo("info@raceteam.com") and not sp.robo("")


# ------------------------------------------------------------------ a IA
def _ferramentas():
    return {f[0]: f[4] for f in api_suits.ferramentas_ia()}


def test_a_ia_nao_ve_nem_mexe_no_descartado_e_nao_cria_com_robo(con):
    f = _ferramentas()
    bom = _lixo(con, "Frank Rossi", "frank@example.com", "t-frank")
    ruim = _lixo(con, "Anthropic", "billing@anthropic.example", "t-ant")
    suits.descartar(con, ruim)
    assert [p["id"] for p in f["suits_pedidos"](con, 1, estado="todos")] == [bom]
    assert "erro" in f["suits_atualizar_pedido"](con, 1, ruim, driver_name="X")
    assert "erro" in f["suits_anotar"](con, 1, ruim, "oi")
    with pytest.raises(suits.Invalido):
        f["suits_criar_pedido"](con, 1, title="OpenAI", customer_email="noreply@tm.openai.com")
    with pytest.raises(suits.Invalido):
        f["suits_criar_pedido"](con, 1, title="Eduardo", customer_email="eduardo@urace.us")
    assert f["suits_criar_pedido"](con, 1, title="Paula", customer_email="paula@example.com")["id"]


# ------------------------------------------------------------------ a tela
def test_api_descartar_some_das_listas_e_restaura(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "api.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path / "urace"))
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "op@urace.us", "Op", "OPERATOR", SENHA)
    frank = _lixo(c, "Frank Rossi", "frank@example.com", "t-frank")
    ant = _lixo(c, "Anthropic", "billing@anthropic.example", "t-ant")
    c.close()
    with TestClient(app, base_url="https://cc.test") as cli:
        assert cli.post("/ops/api/auth/login", json={"email": "op@urace.us", "password": SENHA}).status_code == 200
        h = {"X-CSRF": cli.cookies.get("cc_csrf")}
        ids = lambda estado: [p["id"] for p in cli.get("/ops/api/suits", params={"estado": estado}).json()]  # noqa: E731
        r = cli.post(f"/ops/api/suits/{ant}/descartar", headers=h, json={"motivo": "cobrança da Anthropic"})
        assert r.status_code == 200 and r.json()["discard_reason"] == "cobrança da Anthropic"
        assert ids("abertos") == [frank] and ids("fechados") == [] and ids("descartados") == [ant]
        assert ids("todos") == [frank]
        res = cli.get("/ops/api/suits/resumo").json()
        assert (res["abertos"], res["fechados"], res["descartados"]) == (1, 0, 1)
        assert cli.post("/ops/api/suits/999/descartar", headers=h, json={}).status_code == 404
        assert cli.post(f"/ops/api/suits/{ant}/ponte/simular", headers=h).status_code == 409
        assert cli.post(f"/ops/api/suits/{ant}/restaurar", headers=h).json()["discarded_at"] is None
        assert sorted(ids("abertos")) == sorted([frank, ant])
        c = conectar()
        ev = [a["event"] for a in todos(c, "SELECT event FROM audit_logs WHERE entity_id=? AND entity_type='suit_order' ORDER BY id", (ant,))]
        c.close()
        assert ev == ["suit.discarded", "suit.restored"]


# ------------------------------------------------------------------ o comando do VPS
def test_comando_descarta_os_numeros_e_lista_suspeitos_sem_mexer(con, monkeypatch, capsys):
    lixo = [_lixo(con, n, e, t) for n, e, t in (("OpenAI", "noreply@tm.openai.com", "t-o"), ("Eduardo Resende", "eduardo@urace.us", "t-e"))]
    frank = con.execute("INSERT INTO suit_orders (title, customer_email, gmail_thread_cliente, source) "
                        "VALUES ('Frank', 'frank@example.com', 't-f', 'ia')").lastrowid
    talvez = _lixo(con, "Max", "max@3second.example", "t-m")
    gm = Gmail()
    gm.threads = {"t-f": [{"message_id": "f", "de": "frank@example.com", "assunto": "Kart suit", "corpo": "size?"}],
                  "t-m": [{"message_id": "m", "de": "max@3second.example", "assunto": "Video production", "corpo": "Our rates"}],
                  "t-o": [OPENAI], "t-e": []}
    import command_center.providers as prov
    monkeypatch.setattr(prov, "modulo", lambda nome: gm if nome == "gmail" else None)
    assert manage.main(["manage", "suits-suspeitos"]) == 0
    saida = capsys.readouterr().out
    assert f"#{talvez}" in saida and "a conversa não fala de macacão" in saida and f"#{frank} " not in saida
    assert "o cliente é um e-mail da URACE" in saida and "o cliente é um remetente automático" in saida
    assert um(con, "SELECT COUNT(*) AS n FROM suit_orders WHERE discarded_at IS NOT NULL")["n"] == 0, "suspeitos só lê"
    assert manage.main(["manage", "suits-descartar", *map(str, lixo), "999", "--motivo", "dono, 13/10: não é suit"]) == 0
    saida = capsys.readouterr().out
    assert saida.count("descartado") == 2 and "#999: não existe" in saida
    assert [p["id"] for p in todos(con, "SELECT id FROM suit_orders WHERE discarded_at IS NOT NULL ORDER BY id")] == lixo
    assert um(con, "SELECT discard_reason FROM suit_orders WHERE id=?", (lixo[0],))["discard_reason"] == "dono, 13/10: não é suit"
    assert manage.main(["manage", "suits-restaurar", str(lixo[1])]) == 0
    assert um(con, "SELECT discarded_at FROM suit_orders WHERE id=?", (lixo[1],))["discarded_at"] is None

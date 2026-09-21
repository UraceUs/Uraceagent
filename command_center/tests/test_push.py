"""Notificação no celular (Web Push).

Dono, 21/09: o chat interno só substitui o WhatsApp se tocar no celular. Sem rede: a
`pywebpush` é um dublê. O que se prova é o que costuma quebrar em push e ninguém descobre:
assinatura duplicada avisando três vezes, assinatura morta entupindo a tabela, e o texto
da conversa vazando para o servidor da Apple/Google.
"""
import json
import os
import sys
import tempfile
import types

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth, push  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, todos, um  # noqa: E402

B = "/ops/api"
SENHA = "senha-forte-123"


class WebPushFalso:
    """Dublê da biblioteca: guarda o que sairia e pode fingir cada erro que importa."""

    def __init__(self):
        self.enviados = []
        self.erro_em = {}          # endpoint -> código HTTP

    def instalar(self, monkeypatch):
        # a chave VAPID de verdade é testada no seu próprio teste; aqui ela é constante,
        # para o resto não depender de a `cryptography` estar sã nesta máquina
        monkeypatch.setattr(push, "chaves", lambda criar=True: {"publica": "chave-de-teste", "pem": "PEM"})

        class Excecao(Exception):
            def __init__(self, msg, codigo=None):
                super().__init__(msg)
                self.response = types.SimpleNamespace(status_code=codigo) if codigo else None

        def webpush(subscription_info, data, vapid_private_key, vapid_claims, timeout=None):
            ponta = subscription_info["endpoint"]
            if ponta in self.erro_em:
                raise Excecao("recusado", self.erro_em[ponta])
            self.enviados.append((ponta, json.loads(data)))

        modulo = types.ModuleType("pywebpush")
        modulo.webpush = webpush
        modulo.WebPushException = Excecao
        monkeypatch.setitem(sys.modules, "pywebpush", modulo)
        return self


@pytest.fixture()
def cli(monkeypatch, tmp_path):
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc.sqlite")
    monkeypatch.setenv("URACE_DIR", str(tmp_path))       # a chave VAPID nasce aqui, não no ~ de verdade
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "chefe@urace.us", "Chefe", "ADMIN", SENHA)
    auth.criar_usuario(con, "mec@urace.us", "Mecânico Pedro", "OPERATOR", SENHA)
    auth.criar_usuario(con, "outro@urace.us", "Outro Op", "OPERATOR", SENHA)
    con.commit(); con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def entra(cli, email="mec@urace.us"):
    cli.cookies.clear()
    assert cli.post(f"{B}/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def assina(cli, h, ponta="https://push.exemplo/aparelho-1"):
    return cli.post(f"{B}/push/assinar", headers=h,
                    json={"endpoint": ponta, "p256dh": "chave-publica", "auth": "segredo"})


def uid(email):
    con = conectar()
    try:
        return um(con, "SELECT id FROM users WHERE email=?", (email,))["id"]
    finally:
        con.close()


# --------------------------------------------------------------- chave VAPID
def test_a_chave_nasce_uma_vez_e_fica_fora_do_repositorio(cli, monkeypatch, tmp_path):
    try:                                                # máquina sem cryptography sã: o que
        push.chaves()                                   # importa é o painel não quebrar, e
    except BaseException:                               # isso o teste abaixo prova
        pytest.skip("cryptography indisponível nesta máquina (panic do pyo3)")
    falso = WebPushFalso()
    import types as _t
    monkeypatch.setitem(sys.modules, "pywebpush", _t.SimpleNamespace(
        webpush=lambda **k: None, WebPushException=Exception))
    assert falso
    h = entra(cli)
    a = cli.get(f"{B}/push/chave", headers=h).json()
    b = cli.get(f"{B}/push/chave", headers=h).json()
    assert a["ativo"] and a["chave"] == b["chave"]       # trocar a chave desassinaria todo mundo
    arquivo = tmp_path / "vapid.json"
    assert arquivo.exists()
    guardado = json.loads(arquivo.read_text())
    assert "BEGIN PRIVATE KEY" in guardado["pem"]        # a parte secreta fica só no arquivo
    assert guardado["pem"] not in json.dumps(a)          # e não sai pela API
    assert oct(arquivo.stat().st_mode)[-3:] == "600"


def test_servidor_sem_push_diz_em_vez_de_quebrar(cli, monkeypatch):
    """Máquina sem a biblioteca — ou com a `cryptography` quebrada, que dá panic e não
    ImportError — tem de responder "não está pronto", nunca derrubar a requisição."""
    monkeypatch.setattr(push, "chaves", lambda criar=True: (_ for _ in ()).throw(RuntimeError("panic")))
    h = entra(cli)
    r = cli.get(f"{B}/push/chave", headers=h)
    assert r.status_code == 200 and r.json()["ativo"] is False
    assert cli.post(f"{B}/push/teste", headers=h).status_code == 503
    con = conectar()
    assert push.avisar(con, [1], "oi", "corpo")["enviados"] == 0      # e o envio não explode
    con.close()


# --------------------------------------------------------------- assinaturas
def test_mesmo_aparelho_nao_avisa_tres_vezes(cli, monkeypatch):
    """Recarregar a página reassina. Se cada uma virasse uma linha, a pessoa receberia o
    mesmo aviso várias vezes — e desligaria a notificação no dia seguinte."""
    WebPushFalso().instalar(monkeypatch)
    h = entra(cli)
    assert assina(cli, h).status_code == 201
    assert assina(cli, h).status_code == 201
    con = conectar()
    assert um(con, "SELECT COUNT(*) AS n FROM push_subscriptions")["n"] == 1
    con.close()


def test_celular_e_tablet_sao_dois_aparelhos(cli, monkeypatch):
    WebPushFalso().instalar(monkeypatch)
    h = entra(cli)
    assina(cli, h, "https://push.exemplo/celular")
    assina(cli, h, "https://push.exemplo/tablet")
    assert len(cli.get(f"{B}/push/estado", headers=h).json()["aparelhos"]) == 2
    # desligar num não desliga no outro
    cli.post(f"{B}/push/cancelar", headers=h, json={"endpoint": "https://push.exemplo/tablet"})
    assert len(cli.get(f"{B}/push/estado", headers=h).json()["aparelhos"]) == 1


def test_ninguem_cancela_a_assinatura_de_outro(cli, monkeypatch):
    WebPushFalso().instalar(monkeypatch)
    h = entra(cli, "mec@urace.us")
    assina(cli, h, "https://push.exemplo/do-mecanico")
    h2 = entra(cli, "outro@urace.us")
    cli.post(f"{B}/push/cancelar", headers=h2, json={"endpoint": "https://push.exemplo/do-mecanico"})
    con = conectar()
    assert um(con, "SELECT COUNT(*) AS n FROM push_subscriptions")["n"] == 1
    con.close()


def test_endpoint_que_nao_e_https_nao_entra(cli, monkeypatch):
    WebPushFalso().instalar(monkeypatch)
    h = entra(cli)
    assert cli.post(f"{B}/push/assinar", headers=h,
                    json={"endpoint": "http://sem-tls/x", "p256dh": "a", "auth": "b"}).status_code == 400


# --------------------------------------------------------------- envio
def test_aparelho_que_sumiu_e_apagado_na_hora(cli, monkeypatch):
    """410 do navegador = pessoa desinstalou ou trocou de aparelho. Guardar isso entope a
    tabela e deixa todo envio mais lento, para todo mundo."""
    falso = WebPushFalso().instalar(monkeypatch)
    h = entra(cli)
    assina(cli, h, "https://push.exemplo/vivo")
    assina(cli, h, "https://push.exemplo/morto")
    falso.erro_em["https://push.exemplo/morto"] = 410
    con = conectar()
    r = push.avisar(con, [uid("mec@urace.us")], "oi", "corpo")
    assert r == {"enviados": 1, "limpas": 1, "aparelhos": 2}
    assert [x["endpoint"] for x in todos(con, "SELECT endpoint FROM push_subscriptions")] == \
        ["https://push.exemplo/vivo"]
    con.close()


def test_falha_passageira_nao_apaga_o_aparelho(cli, monkeypatch):
    """500 do servidor de push é problema deles, não da pessoa. Apagar na primeira falha
    faria a equipe perder a notificação por uma instabilidade de dez minutos."""
    falso = WebPushFalso().instalar(monkeypatch)
    h = entra(cli)
    assina(cli, h, "https://push.exemplo/instavel")
    falso.erro_em["https://push.exemplo/instavel"] = 500
    con = conectar()
    push.avisar(con, [uid("mec@urace.us")], "oi", "corpo")
    assert um(con, "SELECT falhas FROM push_subscriptions")["falhas"] == 1
    for _ in range(push.LIMITE_FALHAS):                 # insistindo muito, aí sim some
        push.avisar(con, [uid("mec@urace.us")], "oi", "corpo")
    assert um(con, "SELECT COUNT(*) AS n FROM push_subscriptions")["n"] == 0
    con.close()


@pytest.mark.parametrize("estrago", ["sem biblioteca", "panic do pyo3", "erro comum"])
def test_avisar_nunca_derruba_quem_chamou(cli, monkeypatch, estrago):
    """A mensagem já foi salva quando o aviso sai. Notificação que explode não pode
    transformar uma mensagem entregue em erro na tela de quem escreveu.

    O caso do panic existe porque em 21/09 ele passou direto: PanicException do pyo3 herda
    de BaseException, e o `except Exception` não pegava."""
    class Panic(BaseException):
        pass
    if estrago == "sem biblioteca":
        monkeypatch.setitem(sys.modules, "pywebpush", None)
    elif estrago == "panic do pyo3":
        monkeypatch.setattr(push, "chaves", lambda criar=True: (_ for _ in ()).throw(Panic("boom")))
    else:
        monkeypatch.setattr(push, "chaves", lambda criar=True: (_ for _ in ()).throw(RuntimeError("boom")))
    con = conectar()
    assert push.avisar(con, [1], "oi", "corpo")["enviados"] == 0
    con.close()


# --------------------------------------------------------------- privacidade
def test_o_aviso_nao_leva_o_texto_da_conversa(cli, monkeypatch):
    """O aviso passa pelo servidor da Apple/Google. Conversa da equipe não tem por que
    passar por lá: vai quem escreveu, onde, e o link."""
    falso = WebPushFalso().instalar(monkeypatch)
    h = entra(cli, "mec@urace.us")
    assina(cli, h, "https://push.exemplo/x")
    hc = entra(cli, "chefe@urace.us")
    cid = cli.post(f"{B}/equipe/canais", headers=hc,
                   json={"name": "Corrida Ocala", "membros": [uid("mec@urace.us")]}).json()["id"]
    segredo = "o cliente pagou 4.500 adiantado"
    assert cli.post(f"{B}/equipe/canais/{cid}/mensagens", headers=hc,
                    json={"text": segredo}).status_code == 201
    assert falso.enviados, "o mecânico devia ter sido avisado"
    ponta, carga = falso.enviados[-1]
    assert segredo not in json.dumps(carga)
    assert carga["titulo"].startswith("Chefe em Corrida Ocala") and carga["url"] == f"/ops/equipe?c={cid}"


def test_quem_escreveu_nao_recebe_o_proprio_aviso(cli, monkeypatch):
    falso = WebPushFalso().instalar(monkeypatch)
    h = entra(cli, "mec@urace.us")
    assina(cli, h, "https://push.exemplo/meu")
    cid = cli.post(f"{B}/equipe/canais", headers=h, json={"name": "Box"}).json()["id"]
    cli.post(f"{B}/equipe/canais/{cid}/mensagens", headers=h, json={"text": "oi"})
    assert falso.enviados == []

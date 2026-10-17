"""O IP real atrás do Caddy (#120, lacuna A-6 da waiver).

O IP vai para a trilha da waiver, para o login (limite de tentativas) e para a auditoria. Antes
valia o PRIMEIRO X-Forwarded-For, que é justamente o que o cliente escreve. Agora só um proxy
nosso (127.0.0.1, ::1 ou CC_PROXIES_CONFIAVEIS) pode falar pelo cabeçalho, e vale o último salto
que não é proxy nosso. Os IPs daqui são de documentação (RFC 5737); 6.6.6.6 é o forjado."""
import json
import os
import re

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from command_center.api import auth
from command_center.api.main import app
from command_center.db import aplicar_schema, conectar, todos, um

RAIZ = os.path.join(os.path.dirname(__file__), "..", "..")
SENHA = "senha-forte-123"
FORJADO = "6.6.6.6"
REAL = "203.0.113.5"


def _pedido(par, *xff):
    """Um Request como o uvicorn entrega: `par` é quem conectou; cada `xff` é uma linha do cabeçalho."""
    return Request({"type": "http", "method": "GET", "path": "/", "query_string": b"",
                    "client": (par, 50000) if par else None,
                    "headers": [(b"x-forwarded-for", v.encode()) for v in xff]})


# ------------------------------------------------------------------ a regra
def test_o_primeiro_valor_e_do_cliente_e_nao_vale():
    """O Caddy acrescenta o IP de quem conectou no fim; o começo da lista é o que o cliente mandou."""
    assert auth._ip(_pedido("127.0.0.1", f"{FORJADO}, {REAL}")) == REAL
    assert auth._ip(_pedido("::1", f"{FORJADO}, {REAL}")) == REAL
    assert auth._ip(_pedido("127.0.0.1", FORJADO, REAL)) == REAL, "duas linhas do cabeçalho contam como uma lista"


def test_quem_conecta_direto_nao_fala_pelo_cabecalho():
    assert auth._ip(_pedido("198.51.100.7", FORJADO)) == "198.51.100.7"
    assert auth._ip(_pedido("198.51.100.7", f"{FORJADO}, 127.0.0.1")) == "198.51.100.7"
    assert auth._ip(_pedido("198.51.100.7")) == "198.51.100.7"


def test_do_proxy_local_com_um_so_valor_e_o_valor():
    assert auth._ip(_pedido("127.0.0.1", REAL)) == REAL
    assert auth._ip(_pedido("127.0.0.1", "[2001:db8::5]:443")) == "2001:db8::5"
    assert auth._ip(_pedido("::ffff:127.0.0.1", REAL)) == REAL, "127.0.0.1 escrito como IPv6"
    assert auth._ip(_pedido("127.0.0.1")) == "127.0.0.1", "sem cabeçalho: é a própria máquina"


def test_lixo_no_ultimo_salto_nao_vira_ip():
    assert auth._ip(_pedido("127.0.0.1", "' OR 1=1 --")) == "127.0.0.1"
    assert auth._ip(_pedido("127.0.0.1", f"{FORJADO}, unknown")) == "127.0.0.1"


def test_outros_proxies_so_pela_variavel(monkeypatch):
    """Um balanceador na frente do Caddy: só conta se estiver em CC_PROXIES_CONFIAVEIS."""
    pedido = _pedido("10.0.0.2", f"{FORJADO}, {REAL}, 10.0.0.3")
    assert auth._ip(pedido) == "10.0.0.2", "sem a variável, 10.0.0.2 é um cliente como outro"
    monkeypatch.setenv("CC_PROXIES_CONFIAVEIS", "10.0.0.0/8, nao-e-ip")
    assert auth._ip(pedido) == REAL, "pula os dois saltos de confiança e para no primeiro de fora"


def test_sem_cliente_na_conexao():
    assert auth._ip(_pedido(None, FORJADO)) == "?"


def test_a_vitrine_usa_o_mesmo_ip():
    """O limite de envios do site (contato, pedido) era por IP forjável."""
    from command_center.api import vitrine
    assert vitrine._ip(_pedido("198.51.100.7", FORJADO)) == "198.51.100.7"
    assert vitrine._ip(_pedido("127.0.0.1", f"{FORJADO}, {REAL}")) == REAL


def test_ninguem_mais_le_o_cabecalho_ou_o_par_por_conta_propria():
    """Uma regra só: nenhuma rota lê o X-Forwarded-For nem o `request.client` fora de auth._ip."""
    achados = []
    base = os.path.join(RAIZ, "command_center")
    for pasta, subs, arquivos in os.walk(base):
        subs[:] = [s for s in subs if s not in ("tests", "web", "node_modules", "__pycache__")]
        for a in arquivos:
            if not a.endswith(".py"):
                continue
            p = os.path.join(pasta, a)
            if p.endswith(os.path.join("api", "auth.py")):
                continue
            for n, linha in enumerate(open(p, encoding="utf-8"), 1):
                if re.search(r"x-forwarded-for|request\.client\b", linha, re.I):
                    achados.append(f"{os.path.relpath(p, RAIZ)}:{n}")
    assert not achados, "use auth._ip(request): " + ", ".join(achados)


# ------------------------------------------------------------------ o serviço no VPS
def test_o_servico_so_escuta_na_maquina_e_so_confia_no_caddy():
    """Se o uvicorn escutasse fora de 127.0.0.1, ou confiasse em qualquer um ('*'), o cabeçalho
    voltaria a ser de quem quisesse."""
    s = open(os.path.join(RAIZ, "adminai", "deploy", "command_center", "urace-command-center.service"), encoding="utf-8").read()
    linha = next(x for x in s.splitlines() if x.startswith("ExecStart="))
    assert "--host 127.0.0.1 " in linha
    assert "--proxy-headers" in linha and "--forwarded-allow-ips 127.0.0.1'" in linha
    assert "0.0.0.0" not in linha and "*" not in linha


# ------------------------------------------------------------------ pela API, como no VPS
@pytest.fixture()
def banco(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "admin@urace.us", "Admin", "ADMIN", SENHA)
    c.commit(); c.close()


def _tentativas():
    con = conectar()
    try:
        return [x["key"] for x in todos(con, "SELECT key FROM login_attempts WHERE key LIKE 'ip:%' ORDER BY id")]
    finally:
        con.close()


def _login_errado(t):
    r = t.post("/ops/api/auth/login", json={"email": "ninguem@example.com", "password": "errada-errada"},
               headers={"X-Forwarded-For": f"{FORJADO}, {REAL}"})
    assert r.status_code == 401


def test_login_atras_do_uvicorn_com_proxy_headers(banco):
    """O VPS: Caddy → uvicorn --proxy-headers --forwarded-allow-ips 127.0.0.1 → app."""
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    with TestClient(ProxyHeadersMiddleware(app, trusted_hosts="127.0.0.1"), base_url="https://cc.test",
                    client=("127.0.0.1", 41000)) as t:
        _login_errado(t)
    assert _tentativas() == [f"ip:{REAL}"]


def test_login_sem_o_uvicorn_reescrever(banco):
    """Mesmo se o serviço subir sem --proxy-headers, a regra é a mesma."""
    with TestClient(app, base_url="https://cc.test", client=("127.0.0.1", 41000)) as t:
        _login_errado(t)
    assert _tentativas() == [f"ip:{REAL}"]


def test_forjar_o_cabecalho_nao_dribla_o_limite_de_tentativas(banco):
    """Quem trocava o X-Forwarded-For a cada tentativa nunca chegava ao limite do IP."""
    with TestClient(app, base_url="https://cc.test", client=("198.51.100.7", 41000)) as t:
        for i in range(auth.MAX_FALHAS):
            r = t.post("/ops/api/auth/login", json={"email": f"ninguem{i}@example.com", "password": "errada-errada"},
                       headers={"X-Forwarded-For": f"6.6.6.{i}"})
            assert r.status_code == 401
        r = t.post("/ops/api/auth/login", json={"email": "outro@example.com", "password": "errada-errada"},
                   headers={"X-Forwarded-For": "6.6.6.99"})
        assert r.status_code == 429
    assert set(_tentativas()) == {"ip:198.51.100.7"}


def test_a_trilha_da_waiver_grava_o_ip_real(tmp_path, monkeypatch):
    """O que a issue pede: o IP da trilha da waiver nativa não é o que o cliente escreveu."""
    from command_center.tests import test_waiver_nativa as tw
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    monkeypatch.setenv("CC_WAIVERS_DIR", str(tmp_path / "waivers"))
    monkeypatch.setenv("CC_EMAIL_FAKE", str(tmp_path / "emails.jsonl"))
    import command_center.providers as prov
    monkeypatch.setattr(prov, "modulo", lambda nome: tw.DocusignFalso() if nome == "docusign" else None)
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "admin@urace.us", "Admin", "ADMIN", SENHA)
    c.commit(); c.close()
    with TestClient(app, base_url="https://cc.test", client=("127.0.0.1", 41000),
                    headers={"X-Forwarded-For": f"{FORJADO}, {REAL}"}) as t:
        tw.liga(t)
        hc, (pid,) = tw.cliente(t)
        r = tw.assina(t, hc, pid)
        assert r.status_code == 201, r.text
        wid = r.json()["waiver_id"]
    con = conectar()
    trilha = json.loads(um(con, "SELECT audit FROM waivers WHERE id=?", (wid,))["audit"])
    con.close()
    assert trilha["ip"] == REAL
    assert trilha.get("session_login_ip") in (None, REAL)
    assert FORJADO not in json.dumps(trilha)

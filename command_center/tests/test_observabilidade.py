"""Observabilidade (issue #17): request id, log estruturado, métricas por rota, erros e Web Vitals do navegador."""
import json
import logging
import os

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth, observabilidade as ob  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar  # noqa: E402

SENHA = "senha-forte-123"


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    auth.criar_usuario(c, "op@urace.us", "Operador", "OPERATOR", SENHA)
    c.commit(); c.close()
    ob.zerar()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


class Captura(logging.Handler):
    def __init__(self):
        super().__init__(); self.linhas = []

    def emit(self, rec):
        self.linhas.append(rec.getMessage())


@pytest.fixture()
def logs():
    h = Captura(); ob.log.addHandler(h)
    yield h.linhas
    ob.log.removeHandler(h)


def test_toda_resposta_tem_request_id_e_respeita_o_que_veio(cli):
    r = cli.get("/ops/api/dashboard")
    assert len(r.headers["x-request-id"]) == 16
    assert cli.get("/ops/api/dashboard", headers={"X-Request-ID": "caddy-abc12345"}).headers["x-request-id"] == "caddy-abc12345"
    ruim = cli.get("/ops/api/dashboard", headers={"X-Request-ID": "<script>"}).headers["x-request-id"]
    assert ruim != "<script>" and len(ruim) == 16, "id estranho não é repetido de volta"


def test_log_estruturado_sem_dado_sensivel(cli, logs):
    h = entra(cli, "ger@urace.us")
    cli.get("/ops/api/clients?busca=enzo@cliente.com", headers=h)
    linhas = [json.loads(x) for x in logs if x.startswith("{")]
    ln = next(x for x in linhas if x["rota"] == "/ops/api/clients")
    assert set(ln) >= {"id", "metodo", "rota", "status", "ms", "usuario"} and ln["usuario"] is not None
    tudo = "\n".join(logs)
    assert "enzo@cliente.com" not in tudo, "query string (busca de cliente) não vai para o log"
    assert "cc_session" not in tudo and SENHA not in tudo


def test_metricas_por_rota_so_para_gerente(cli):
    h = entra(cli, "op@urace.us")
    assert cli.get("/ops/api/system/metricas", headers=h).status_code == 403
    h = entra(cli, "ger@urace.us")
    for _ in range(3):
        cli.get("/ops/api/dashboard", headers=h)
    m = cli.get("/ops/api/system/metricas", headers=h).json()
    d = next(x for x in m["rotas"] if x["rota"] == "GET /ops/api/dashboard")
    assert d["n"] >= 3 and d["p95_ms"] is not None and d["erros_5xx"] == 0
    assert any(x["rota"] == "POST /ops/api/auth/login" for x in m["rotas"]), "rota pelo modelo, não pela URL"


def test_5xx_e_contado_e_logado_como_aviso(cli, logs):
    def quebra():
        raise RuntimeError("falhou de propósito")
    if not any(getattr(rt, "path", "") == "/ops/api/_teste_500" for rt in app.routes):
        app.add_api_route("/ops/api/_teste_500", quebra, methods=["POST"])
    c = TestClient(app, base_url="https://cc.test", raise_server_exceptions=False)
    assert c.post("/ops/api/_teste_500").status_code == 500
    rota = next(x for x in ob.metricas()["rotas"] if x["rota"] == "POST /ops/api/_teste_500")
    assert rota["erros_5xx"] == 1
    ln = [json.loads(x) for x in logs if '"_teste_500"' in x or "_teste_500" in x]
    assert ln and ln[-1]["status"] == 500


def test_navegador_manda_vital_e_erro(cli):
    corpo = {"itens": [{"tipo": "vital", "nome": "LCP", "valor": 1830.5, "rota": "/ops/clients/42"},
                       {"tipo": "vital", "nome": "CLS", "valor": 0.031, "rota": "/ops/clients/42"},
                       {"tipo": "vital", "nome": "XYZ", "valor": 1, "rota": "/ops/"},
                       {"tipo": "erro", "mensagem": "TypeError: x is undefined", "rota": "/ops/compras", "pilha": "a" * 2000}]}
    assert cli.post("/ops/api/system/cliente", content=json.dumps(corpo)).status_code == 204, "sem login: pode ser erro na tela de login"
    m = ob.metricas()
    lcp = next(v for v in m["vitais"] if v["metrica"] == "LCP")
    assert lcp["rota"] == "/ops/clients/:id" and lcp["p75"] == 1830.5, "id vira :id"
    assert not any(v["metrica"] == "XYZ" for v in m["vitais"])
    assert m["erros_js"][0]["mensagem"].startswith("TypeError") and len(m["erros_js"][0]["pilha"]) == 800


def test_navegador_com_limite(cli):
    assert cli.post("/ops/api/system/cliente", content=b"x" * 5000).status_code == 413
    assert cli.post("/ops/api/system/cliente", content=b"nao-json").status_code == 400
    for _ in range(ob.LIMITE_POR_MIN):
        cli.post("/ops/api/system/cliente", content=b"{}")
    assert cli.post("/ops/api/system/cliente", content=b"{}").status_code == 429

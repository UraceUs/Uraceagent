"""Cache das APIs (issue #20): ETag/304 nos GET e paginação no backend."""
import os

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.cache_api import _bate  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, auditar, conectar, inserir  # noqa: E402
from command_center.providers import compras  # noqa: E402

SENHA = "senha-forte-123"


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    for i in range(7):
        inserir(c, "clients", name=f"Piloto {i}", status="ACTIVE", source="manual")
    for i in range(12):
        auditar(c, "teste.evento" if i % 2 else "outro.evento", "system", detail={"n": i, "marca": "agulha" if i == 5 else "palha"})
    for i in range(5):
        compras.criar_pedido(c, None, 1, description=f"Peça {i}")
    c.commit(); c.close()
    with TestClient(app, base_url="https://cc.test") as t:
        t.post("/ops/api/auth/login", json={"email": "ger@urace.us", "password": SENHA})
        yield t


def test_get_da_api_tem_etag_e_304_quando_nada_mudou(cli):
    r = cli.get("/ops/api/clients")
    et = r.headers["etag"]
    assert et.startswith('W/"') and r.headers["cache-control"] == "private, no-cache"
    r2 = cli.get("/ops/api/clients", headers={"If-None-Match": et})
    assert r2.status_code == 304 and r2.content == b""
    assert r2.headers["etag"] == et and "x-request-id" in r2.headers
    c = conectar(); inserir(c, "clients", name="Piloto novo", status="ACTIVE", source="manual"); c.commit(); c.close()
    r3 = cli.get("/ops/api/clients", headers={"If-None-Match": et})
    assert r3.status_code == 200 and r3.headers["etag"] != et, "mudou: corpo novo"


def test_erro_e_escrita_nao_ganham_etag(cli):
    cli.cookies.clear()
    r = cli.get("/ops/api/clients")
    assert r.status_code == 401 and "etag" not in r.headers
    assert "etag" not in cli.post("/ops/api/auth/login", json={"email": "x@y.z", "password": "errada-123"}).headers


def test_if_none_match_com_lista_e_asterisco():
    et = 'W/"abc"'
    assert _bate('"zzz", W/"abc"', et) and _bate('"abc"', et) and _bate("*", et)
    assert not _bate('"zzz"', et) and not _bate(None, et)


def test_paginacao_clientes_com_total(cli):
    r = cli.get("/ops/api/clients?limit=3&offset=0")
    assert len(r.json()) == 3 and r.headers["x-total-count"] == "7"
    ids = [c["id"] for c in r.json()] + [c["id"] for c in cli.get("/ops/api/clients?limit=3&offset=3").json()] \
        + [c["id"] for c in cli.get("/ops/api/clients?limit=3&offset=6").json()]
    assert len(ids) == 7 and len(set(ids)) == 7, "sem repetir nem pular entre páginas"
    assert len(cli.get("/ops/api/clients").json()) == 7 and "x-total-count" not in cli.get("/ops/api/clients").headers, \
        "sem limit: igual a antes"
    assert len(cli.get("/ops/api/clients?limit=99999").json()) == 7


def test_auditoria_busca_no_servidor_e_pagina(cli):
    r = cli.get("/ops/api/audit?limit=5")
    assert len(r.json()) == 5 and int(r.headers["x-total-count"]) >= 12
    achados = cli.get("/ops/api/audit?q=agulha&limit=50").json()
    assert len(achados) == 1 and "agulha" in achados[0]["detail"]
    pag2 = cli.get("/ops/api/audit?limit=5&offset=5").json()
    assert {x["id"] for x in pag2}.isdisjoint({x["id"] for x in r.json()})


def test_pedidos_e_compras_com_total(cli):
    d = cli.get("/ops/api/compras/pedidos?limit=2").json()
    assert len(d["pedidos"]) == 2 and d["total"] == 5
    assert cli.get("/ops/api/compras?limit=10").json()["total"] == 0

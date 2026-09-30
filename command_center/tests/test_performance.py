"""Performance (issue #19): arquivo do build com cache imutável e resposta grande comprimida."""
import os

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth, main  # noqa: E402
from command_center.db import aplicar_schema, conectar  # noqa: E402

SENHA = "senha-forte-123"


def test_arquivo_com_hash_e_imutavel_e_o_resto_nao():
    assert main.cache_de("/ops/assets/index-Co7pDqj7.js") == "public, max-age=31536000, immutable"
    assert main.cache_de("/ops/") is None and main.cache_de("/ops/api/dashboard") is None
    assert main.cache_de("/ops/assetsx/a.js") is None


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "adm@urace.us", "Admin", "ADMIN", SENHA)
    c.commit(); c.close()
    with TestClient(main.app, base_url="https://cc.test") as t:
        yield t


def test_resposta_grande_vai_comprimida_e_pequena_nao(cli):
    cli.post("/ops/api/auth/login", json={"email": "adm@urace.us", "password": SENHA})
    grande = cli.get("/ops/api/policies", headers={"Accept-Encoding": "gzip"})
    assert grande.status_code == 200 and len(grande.content) > 1024
    assert grande.headers.get("content-encoding") == "gzip"
    assert grande.headers["cache-control"] == "private, no-cache", "dado da API: só no navegador, sempre revalidado (#20)"
    cli.cookies.clear()
    pequena = cli.get("/ops/api/dashboard", headers={"Accept-Encoding": "gzip"})
    assert pequena.status_code == 401 and pequena.headers.get("content-encoding") is None, "menos de 1 KB não compensa"

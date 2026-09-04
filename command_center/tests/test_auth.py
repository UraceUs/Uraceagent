"""Auth, sessão, RBAC, CSRF, rate limit e auditoria — testados pela API.

    CC_DB_PATH=/tmp/x.sqlite python3 -m pytest command_center/tests -q
"""
import os
import sqlite3
import tempfile

import pytest

os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc-test.sqlite")

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import BASE, app  # noqa: E402
from command_center.db import aplicar_schema, conectar, todos  # noqa: E402

SENHA = "senha-forte-123"


@pytest.fixture(scope="module")
def cli():
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "admin@urace.us", "Admin", "ADMIN", SENHA)
    auth.criar_usuario(con, "viewer@urace.us", "Viewer", "VIEWER", SENHA)
    con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def entra(cli, email, senha=SENHA, remember=False):
    cli.cookies.clear()
    r = cli.post(BASE + "/api/auth/login", json={"email": email, "password": senha, "remember": remember})
    return r


def csrf(cli):
    return {"X-CSRF": cli.cookies.get("cc_csrf", "")}


def test_health_publico(cli):
    assert cli.get(BASE + "/health").json() == {"ok": True}
    assert cli.get(BASE + "/ready").json()["db"] is True


def test_sem_sessao_401(cli):
    cli.cookies.clear()
    assert cli.get(BASE + "/api/auth/me").status_code == 401


def test_login_errado_nao_revela_email(cli):
    a = entra(cli, "naoexiste@urace.us", "qualquer")
    b = entra(cli, "admin@urace.us", "errada-errada")
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"] == "Invalid email or password."


def test_login_certo_e_cookies(cli):
    r = entra(cli, "admin@urace.us")
    assert r.status_code == 200 and r.json()["role"] == "ADMIN"
    sc = r.headers.get_list("set-cookie")
    sess = [c for c in sc if c.startswith("cc_session=")][0]
    assert "HttpOnly" in sess and "Secure" in sess and "SameSite=strict" in sess.lower().replace("samesite=strict", "SameSite=strict")
    assert cli.get(BASE + "/api/auth/me").json()["email"] == "admin@urace.us"


def test_csrf_obrigatorio_em_mutacao(cli):
    entra(cli, "admin@urace.us")
    sem = cli.post(BASE + "/api/users", json={"email": "x@urace.us", "name": "X", "role": "VIEWER", "password": SENHA})
    assert sem.status_code == 403
    com = cli.post(BASE + "/api/users", headers=csrf(cli),
                   json={"email": "x@urace.us", "name": "X", "role": "VIEWER", "password": SENHA})
    assert com.status_code == 201


def test_rbac_no_backend(cli):
    entra(cli, "viewer@urace.us")
    assert cli.get(BASE + "/api/users").status_code == 403          # ADMIN only
    assert cli.get(BASE + "/api/audit").status_code == 403          # MANAGER+
    entra(cli, "admin@urace.us")
    assert cli.get(BASE + "/api/users").status_code == 200


def test_logout_revoga_de_verdade(cli):
    entra(cli, "admin@urace.us")
    tok = cli.cookies.get("cc_session")
    assert cli.post(BASE + "/api/auth/logout", headers=csrf(cli)).status_code == 200
    # reapresentar o MESMO token depois do logout tem que falhar (revogação no banco)
    cli.cookies.set("cc_session", tok)
    assert cli.get(BASE + "/api/auth/me").status_code == 401


def test_desativar_usuario_derruba_sessao(cli):
    entra(cli, "admin@urace.us"); h = csrf(cli)
    uid = [u for u in cli.get(BASE + "/api/users").json() if u["email"] == "x@urace.us"][0]["id"]
    admin_cookies = dict(cli.cookies)
    entra(cli, "x@urace.us")
    assert cli.get(BASE + "/api/auth/me").status_code == 200
    x_cookies = dict(cli.cookies)
    cli.cookies.clear(); [cli.cookies.set(k, v) for k, v in admin_cookies.items()]
    assert cli.post(BASE + f"/api/users/{uid}/active", headers=h, json={"active": False}).status_code == 200
    cli.cookies.clear(); [cli.cookies.set(k, v) for k, v in x_cookies.items()]
    assert cli.get(BASE + "/api/auth/me").status_code == 401
    assert entra(cli, "x@urace.us").status_code == 401             # inativo não entra


def test_rate_limit(cli):
    for _ in range(5):
        entra(cli, "viewer@urace.us", "errada")
    r = entra(cli, "viewer@urace.us", SENHA)                        # senha CERTA, mas bloqueado
    assert r.status_code == 429


def test_auditoria_registrou(cli):
    con = conectar()
    eventos = {r["event"] for r in todos(con, "SELECT event FROM audit_logs")}
    con.close()
    for e in ("user.create", "auth.login", "auth.fail", "auth.logout", "user.active", "auth.rate_limited"):
        assert e in eventos, e


def test_audit_append_only():
    con = conectar()
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM audit_logs")
    con.close()

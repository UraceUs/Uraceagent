"""#311: o botão "Abrir o balcão do celular" leva ao parts.urace.us já logado, com o mesmo login.

Dono, 16/10: *"Aquele botão tem que direcionar a pessoa para o … parts.urace.us, já logada com o mesmo
login que ela estava logada no … Command Center."* O painel dá um passe de uso único (30 s), que vai num
POST de formulário e vira uma sessão própria do parts.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, um  # noqa: E402

SENHA = "senha-forte-123"
PAINEL = "https://cc.test"
PARTS = "https://parts.urace.us"
ENTRAR = "/ops/api/auth/passe/entrar"


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    monkeypatch.delenv("CC_BALCAO_HOSTS", raising=False)
    monkeypatch.delenv("CC_BALCAO_URL", raising=False)
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "mec@urace.us", "Mecânico Teste", "OPERATOR", SENHA)
    con.execute("UPDATE users SET cargo='MECANICO' WHERE email='mec@urace.us'")
    auth.criar_usuario(con, "ger@urace.us", "Gerente Teste", "MANAGER", SENHA)
    auth.criar_usuario(con, "ver@urace.us", "Só olha", "VIEWER", SENHA)
    con.close()
    with TestClient(app, base_url=PAINEL, follow_redirects=False) as c:
        yield c


def _con():
    return conectar()


def entra(c, email="mec@urace.us", lembrar=False):
    c.cookies.clear()
    r = c.post("/ops/api/auth/login", json={"email": email, "password": SENHA, "remember": lembrar})
    assert r.status_code == 200
    return {"X-CSRF": c.cookies.get("cc_csrf")}


def pede(c, h):
    r = c.post("/ops/api/auth/passe", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def troca(passe, origem=PAINEL, base=PARTS, cookies=None):
    """Quem chega no parts: o navegador manda o formulário com o Origin do painel."""
    with TestClient(app, base_url=base, follow_redirects=False) as bc:
        if cookies:
            for k, v in cookies.items():
                bc.cookies.set(k, v)
        cab = {"Origin": origem} if origem is not None else {}
        r = bc.post(ENTRAR, data={"passe": passe}, headers=cab)
        me = bc.get("/ops/api/auth/me")
        return r, me, dict(bc.cookies)


# --------------------------------------------------------------------- o caminho de sempre
def test_o_painel_da_um_passe_e_o_parts_abre_ja_logado(cli):
    h = entra(cli)
    p = pede(cli, h)
    assert p["acao"] == "https://parts.urace.us/ops/api/auth/passe/entrar"
    vence = datetime.strptime(p["vence_em"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    assert vence - datetime.now(timezone.utc) <= timedelta(seconds=31)
    linha = um(_con(), "SELECT * FROM auth_passes")
    assert linha["token_hash"] != p["passe"] and p["passe"] not in str(dict(linha)), "no banco só o hash"
    assert (linha["de_host"], linha["para_host"]) == ("cc.test", "parts.urace.us")

    r, me, cookies = troca(p["passe"])
    assert r.status_code == 303 and r.headers["location"] == "/ops/"
    assert me.status_code == 200
    eu = me.json()
    assert (eu["email"], eu["role"], eu["cargo"], eu["so_balcao"]) == ("mec@urace.us", "OPERATOR", "MECANICO", True)
    galletas = r.headers.get_list("set-cookie")
    sessao = next(g for g in galletas if g.startswith("cc_session="))
    assert "HttpOnly" in sessao and "samesite=strict" in sessao.lower() and "Domain" not in sessao
    assert any(g.startswith("cc_csrf=") for g in galletas)


def test_o_gerente_tambem_entra_com_o_papel_dele(cli):
    h = entra(cli, "ger@urace.us")
    _, me, _ = troca(pede(cli, h)["passe"])
    assert (me.json()["email"], me.json()["role"], me.json()["cargo"]) == ("ger@urace.us", "MANAGER", None)


def test_a_sessao_do_parts_vence_junto_com_a_do_painel(cli):
    h = entra(cli, lembrar=True)
    troca(pede(cli, h)["passe"])
    con = _con()
    filha = um(con, "SELECT * FROM sessions WHERE parent_id IS NOT NULL")
    mae = um(con, "SELECT * FROM sessions WHERE id = ?", (filha["parent_id"],))
    assert filha["expires_at"][:19] == mae["expires_at"][:19], "nunca mais longa que a do painel"
    assert um(con, "SELECT sessao_filha FROM auth_passes")["sessao_filha"] == filha["id"]


def test_sair_do_painel_tira_o_balcao_do_celular(cli):
    h = entra(cli)
    passe = pede(cli, h)["passe"]
    with TestClient(app, base_url=PARTS, follow_redirects=False) as bc:
        bc.post(ENTRAR, data={"passe": passe}, headers={"Origin": PAINEL})
        assert bc.get("/ops/api/auth/me").status_code == 200
        cli.post("/ops/api/auth/logout", headers=h)
        assert bc.get("/ops/api/auth/me").status_code == 401


def test_quem_estava_logado_no_celular_sai_quando_outro_entra(cli):
    h = entra(cli, "ger@urace.us")
    with TestClient(app, base_url=PARTS, follow_redirects=False) as bc:
        assert bc.post("/ops/api/auth/login", json={"email": "mec@urace.us", "password": SENHA}).status_code == 200
        velho = bc.cookies.get("cc_session")
        bc.post(ENTRAR, data={"passe": pede(cli, h)["passe"]}, headers={"Origin": PAINEL})
        assert bc.get("/ops/api/auth/me").json()["email"] == "ger@urace.us"
    assert auth.sessao_valida(_con(), velho) is None


# --------------------------------------------------------------------- o que não pode
def test_o_passe_vale_uma_vez_e_o_segundo_uso_derruba_a_sessao(cli):
    h = entra(cli)
    passe = pede(cli, h)["passe"]
    _, me1, cookies = troca(passe)
    assert me1.status_code == 200
    r2, me2, _ = troca(passe)
    assert r2.headers["location"] == "/ops/login?passe=vencido" and me2.status_code == 401
    assert auth.sessao_valida(_con(), cookies["cc_session"]) is None, "quem copiou o passe derruba os dois"
    eventos = [x["event"] for x in _con().execute("SELECT event FROM audit_logs").fetchall()]
    assert "auth.passe.reuse" in eventos


def test_passe_vencido_nao_entra(cli):
    h = entra(cli)
    passe = pede(cli, h)["passe"]
    ontem = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    _con().execute("UPDATE auth_passes SET expires_at = ?", (ontem,))
    r, me, _ = troca(passe)
    assert r.headers["location"] == "/ops/login?passe=vencido" and me.status_code == 401


@pytest.mark.parametrize("origem", [None, "null", "https://outro-site.example.com", "https://parts.urace.us"])
def test_so_entra_vindo_do_painel_que_deu_o_passe(cli, origem):
    """Sem isto, um colega mandaria o celular de outro entrar na conta dele (login CSRF)."""
    h = entra(cli)
    r, me, _ = troca(pede(cli, h)["passe"], origem=origem)
    assert r.headers["location"] == "/ops/login?passe=vencido" and me.status_code == 401


def test_o_passe_so_vira_sessao_no_host_do_balcao(cli):
    h = entra(cli)
    passe = pede(cli, h)["passe"]
    r = cli.post(ENTRAR, data={"passe": passe}, headers={"Origin": PAINEL})
    assert r.headers["location"] == "/ops/login?passe=vencido"


def test_no_parts_nao_se_pede_passe(cli):
    with TestClient(app, base_url=PARTS) as bc:
        assert bc.post("/ops/api/auth/login", json={"email": "ger@urace.us", "password": SENHA}).status_code == 200
        assert bc.post("/ops/api/auth/passe", headers={"X-CSRF": bc.cookies.get("cc_csrf")}).status_code == 403


def test_passe_desconhecido_ou_torto_nao_entra(cli):
    for lixo in ("", "x", "a" * 40, "a" * 5000):
        r, me, _ = troca(lixo)
        assert r.headers["location"] == "/ops/login?passe=vencido" and me.status_code == 401


def test_sessao_do_painel_que_caiu_antes_da_troca_nao_entra(cli):
    h = entra(cli)
    passe = pede(cli, h)["passe"]
    cli.post("/ops/api/auth/logout", headers=h)
    assert troca(passe)[1].status_code == 401


def test_pessoa_desativada_antes_da_troca_nao_entra(cli):
    h = entra(cli)
    passe = pede(cli, h)["passe"]
    _con().execute("UPDATE users SET active = 0 WHERE email = 'mec@urace.us'")
    assert troca(passe)[1].status_code == 401


def test_chave_de_api_nao_vira_sessao_de_navegador(cli):
    con = _con()
    uid = um(con, "SELECT id FROM users WHERE email = 'ger@urace.us'")["id"]
    chave = auth.criar_chave(con, "integração", "MANAGER", uid, somente_leitura=False)["chave"]
    cli.cookies.clear()
    r = cli.post("/ops/api/auth/passe", headers={"Authorization": f"Bearer {chave}"})
    assert r.status_code == 403
    assert um(_con(), "SELECT COUNT(*) AS n FROM auth_passes")["n"] == 0


def test_viewer_e_sem_login_nao_pedem_passe(cli):
    h = entra(cli, "ver@urace.us")
    assert cli.post("/ops/api/auth/passe", headers=h).status_code == 403
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/passe").status_code == 401
    h = entra(cli)
    assert cli.post("/ops/api/auth/passe").status_code == 403, "sem o X-CSRF, nada"


def test_cinco_erros_travam_as_tentativas(cli):
    for _ in range(auth.MAX_FALHAS):
        troca("b" * 43)
    h = entra(cli)
    r, me, _ = troca(pede(cli, h)["passe"])
    assert me.status_code == 401, "travado: nem o passe certo entra por 15 minutos"
    assert "limite" in str([x["detail"] for x in _con().execute("SELECT detail FROM audit_logs").fetchall()])


def test_a_auditoria_nunca_guarda_o_passe(cli):
    h = entra(cli)
    passe = pede(cli, h)["passe"]
    troca(passe)
    troca(passe)
    tudo = " ".join(str(dict(x)) for x in _con().execute("SELECT * FROM audit_logs").fetchall())
    assert passe not in tudo
    eventos = {x["event"] for x in _con().execute("SELECT event FROM audit_logs").fetchall()}
    assert {"auth.passe.create", "auth.passe.use", "auth.passe.reuse"} <= eventos


# --------------------------------------------------------------------- configuração
def test_sem_balcao_configurado_o_botao_abre_aqui_mesmo(cli, monkeypatch):
    h = entra(cli)
    monkeypatch.setenv("CC_BALCAO_URL", "https://outro.example.com")      # não é host do balcão
    assert pede(cli, h) == {"acao": None}
    monkeypatch.setenv("CC_BALCAO_HOSTS", "parts.urace.us,balcao.test")
    monkeypatch.setenv("CC_BALCAO_URL", "http://balcao.test")              # sem TLS fora da máquina local
    assert pede(cli, h) == {"acao": None}
    monkeypatch.setenv("CC_BALCAO_URL", "https://balcao.test")
    assert pede(cli, h)["acao"] == "https://balcao.test/ops/api/auth/passe/entrar"


def test_a_csp_do_painel_deixa_o_formulario_ir_ao_balcao(cli):
    csp = cli.get("/ops/health").headers["content-security-policy"]
    assert "form-action" not in csp or "parts.urace.us" in csp

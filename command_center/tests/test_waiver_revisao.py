"""Revisar e confirmar antes do clique final (#112; lacunas C-2, C-4 e A-5; Fla. Stat. §668.50(10)).

O que estes testes trancam: não há como assinar sem passar pela revisão (pela conta e pelo convite); a revisão vale
uma vez, por 30 min, só para a mesma conta e piloto (ou o mesmo convite) e com o mesmo conteúdo; o nome digitado
diferente do da conta (sem acento, sem maiúsculas, sem espaço repetido) pede confirmação e os dois nomes ficam na
trilha; a trilha e o certificado têm as duas horas e a frase de efeito legal mostrada ao lado do botão; e a tabela
das revisões só aceita marcar `used_at`, uma vez. Os dados são fictícios (`@example.com`)."""
import json
import sqlite3
from datetime import datetime, timezone

import pytest

from command_center import db
from command_center.db import aplicar_schema, conectar, todos, um
from command_center.providers import revisao_waiver as rv
from command_center.tests.test_waiver_nativa import (CONTA, P, _assinatura, certificado, cli, cliente, confirma_email,  # noqa: F401
                                                     equipe, liga, ultimo_codigo)

API = "/ops/api"


def _corpo(**mais):
    return {"typed_name": "Maria Santos", "signature": _assinatura(), "read_and_agree": True, "consent_esign": True,
            "english_understood": True, "relationship": "mother", "guardian_declaration": True,
            "document_read_at": datetime.now(timezone.utc).isoformat(), "document_read_mode": "pdf_viewer", **mais}


def _pronto(cli, nome="Leo Santos", nasc="2014-05-01", conta=CONTA):  # noqa: F811
    """A conta com um piloto, o PDF entregue e o e-mail confirmado: falta só revisar e assinar."""
    hc, (pid,) = cliente(cli, conta=conta, pilotos=((nome, nasc),))
    assert cli.get(f"{P}/waivers/model/parental/pdf?driver={pid}").status_code == 200
    assert cli.get(f"{P}/waivers/model/adult/pdf?driver={pid}").status_code == 200
    confirma_email(cli, hc)
    return hc, pid


def _codigo(cli, hc, email="maria@example.com"):  # noqa: F811
    c = conectar(); c.execute("UPDATE portal_codes SET created_at='2000-01-01T00:00:00Z'"); c.commit(); c.close()
    assert cli.post(f"{P}/waivers/code", headers=hc).status_code == 200
    return ultimo_codigo(email)


def _revisa(cli, hc, pid, corpo):  # noqa: F811
    return cli.post(f"{P}/drivers/{pid}/waiver/review", json=corpo, headers=hc)


def _assina(cli, hc, pid, corpo, **mais):  # noqa: F811
    return cli.post(f"{P}/drivers/{pid}/waiver", json={**corpo, **mais}, headers=hc)


def _waivers():
    return um(conectar(), "SELECT COUNT(*) AS n FROM waivers WHERE source='urace'")["n"]


# ------------------------------------------------------------------ não há como assinar sem revisar
def test_sem_revisao_nao_assina_e_o_codigo_continua_valendo(cli):  # noqa: F811
    liga(cli)
    hc, pid = _pronto(cli)
    corpo = _corpo()
    cod = _codigo(cli, hc)
    r = _assina(cli, hc, pid, corpo, sign_code=cod)
    assert r.status_code == 400 and "Review the summary before signing" in r.json()["detail"], r.text
    assert _assina(cli, hc, pid, corpo, sign_code=cod, review_id=999999).status_code == 400, "revisão que não existe"
    assert _waivers() == 0
    rid = _revisa(cli, hc, pid, corpo).json()["review_id"]
    r = _assina(cli, hc, pid, corpo, sign_code=cod, review_id=rid)
    assert r.status_code == 201, "a revisão vem antes do código: a recusa não gastou o código"


def test_a_revisao_confere_tudo_menos_o_codigo_e_devolve_o_resumo(cli):  # noqa: F811
    liga(cli)
    hc, pid = _pronto(cli)
    r = _revisa(cli, hc, pid, _corpo(read_and_agree=False))
    assert r.status_code == 400 and "Check both boxes" in r.json()["detail"]
    r = _revisa(cli, hc, pid, _corpo(relationship="other"))
    assert r.status_code == 400 and "Only a parent" in r.json()["detail"]
    r = _revisa(cli, hc, pid, _corpo(document_read_at=None))
    assert r.status_code == 400 and "Read the whole document" in r.json()["detail"]
    r = _revisa(cli, hc, pid, _corpo())                    # sem código nenhum: a revisão não pede
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["document"] == "Parental consent Waiver liability" and s["driver"] == "Leo Santos" and s["kind"] == "parental"
    assert s["signing_as"] == "Parent (natural guardian)" and s["relationship"] == "Mother"
    assert s["guardian_declaration"].startswith("I am the parent (natural guardian) of Leo Santos")
    assert s["typed_name"] == "Maria Santos" and s["name_on_file"] == "Maria Santos" and s["name_matches"] is True
    assert s["valid_until"] and s["valid_until_reason"] == "one year"
    assert s["button"] == "I agree — sign the waiver" and "same legal effect as a handwritten signature" in s["legal_effect"]
    assert s["signature_sha256"] and len(s["signature_sha256"]) == 64
    assert _waivers() == 0, "revisar não assina"
    ev = um(conectar(), "SELECT * FROM waiver_events WHERE event='reviewed'")
    d = json.loads(ev["detail"])
    assert ev["pilot_id"] == pid and ev["ip"] and ev["user_agent"] and d["review_id"] == s["review_id"]
    assert d["typed_name"] == "Maria Santos" and d["name_on_file"] == "Maria Santos" and d["name_matches"] is True


def test_a_revisao_vale_uma_vez(cli):  # noqa: F811
    liga(cli)
    hc, pid = _pronto(cli)
    corpo = _corpo()
    rid = _revisa(cli, hc, pid, corpo).json()["review_id"]
    r = _assina(cli, hc, pid, corpo, sign_code=_codigo(cli, hc), review_id=rid)
    assert r.status_code == 201, r.text
    wid = r.json()["waiver_id"]
    assert um(conectar(), "SELECT used_at FROM waiver_reviews WHERE id=?", (rid,))["used_at"]
    assert cli.post(f"{API}/waivers/{wid}/void", json={"reason": "assinada no teste para anular"},
                    headers=equipe(cli, "ger@urace.us")).status_code == 200
    cli.cookies.clear()
    assert cli.post(f"{P}/login", json={"email": CONTA["email"], "password": CONTA["password"]}).status_code == 200
    hc = {"X-CSRF": cli.cookies.get("cp_csrf")}
    r = _assina(cli, hc, pid, corpo, sign_code=_codigo(cli, hc), review_id=rid)
    assert r.status_code == 400 and "already used" in r.json()["detail"], r.text
    assert _waivers() == 1


def _outra_assinatura():
    import base64
    import io
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (300, 100), (255, 255, 255, 0))
    ImageDraw.Draw(im).line([(10, 80), (290, 10)], fill=(0, 0, 0, 255), width=6)
    b = io.BytesIO(); im.save(b, "PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def test_conteudo_mudado_depois_da_revisao_nao_assina(cli):  # noqa: F811
    liga(cli)
    hc, pid = _pronto(cli)
    corpo = _corpo()
    rid = _revisa(cli, hc, pid, corpo).json()["review_id"]
    cod = _codigo(cli, hc)
    for mudou in ({"typed_name": "Maria Souza"}, {"relationship": "father"}, {"signature": _outra_assinatura()},
                  {"document_read_mode": "pdf_opened_and_text"}):
        r = _assina(cli, hc, pid, {**corpo, **mudou}, sign_code=cod, review_id=rid)
        assert r.status_code == 400 and "changed after the review" in r.json()["detail"], (list(mudou), r.text)
    assert _waivers() == 0
    assert _assina(cli, hc, pid, corpo, sign_code=cod, review_id=rid).status_code == 201, "o mesmo conteúdo assina"


def test_revisao_vencida_nao_assina(cli, monkeypatch):  # noqa: F811
    liga(cli)
    hc, pid = _pronto(cli)
    corpo = _corpo()
    monkeypatch.setattr(rv, "VALIDADE_MIN", -1)
    rid = _revisa(cli, hc, pid, corpo).json()["review_id"]
    r = _assina(cli, hc, pid, corpo, sign_code=_codigo(cli, hc), review_id=rid)
    assert r.status_code == 400 and "review expired" in r.json()["detail"], r.text
    assert _waivers() == 0


def test_revisao_de_outro_piloto_ou_de_outra_conta_nao_vale(cli):  # noqa: F811
    liga(cli)
    hc, (a, b) = cliente(cli, pilotos=(("Leo Santos", "2014-05-01"), ("Ana Santos", "2016-03-03")))
    for pid in (a, b):
        assert cli.get(f"{P}/waivers/model/parental/pdf?driver={pid}").status_code == 200
    confirma_email(cli, hc)
    corpo = _corpo()
    rid_a = _revisa(cli, hc, a, corpo).json()["review_id"]
    r = _assina(cli, hc, b, corpo, sign_code=_codigo(cli, hc), review_id=rid_a)
    assert r.status_code == 400 and "Review the summary" in r.json()["detail"], "a revisão de Leo não assina pela Ana"
    outra = {**CONTA, "email": "outra@example.com", "name": "Maria Santos"}
    hc2, pid2 = _pronto(cli, conta=outra)
    r = _assina(cli, hc2, pid2, corpo, sign_code=_codigo(cli, hc2, "outra@example.com"), review_id=rid_a)
    assert r.status_code == 400 and "Review the summary" in r.json()["detail"], "nem por outra conta"
    assert _waivers() == 0


def test_revisoes_demais_na_hora_viram_429(cli, monkeypatch):  # noqa: F811
    liga(cli)
    hc, pid = _pronto(cli)
    monkeypatch.setattr(rv, "POR_HORA", 3)
    assert [_revisa(cli, hc, pid, _corpo()).status_code for _ in range(4)] == [201, 201, 201, 429]


# ------------------------------------------------------------------ o nome digitado (A-5)
def test_nome_sem_acento_sem_maiusculas_e_sem_espaco_repetido_e_o_mesmo():
    assert rv.mesmo_nome("José  da SILVA", "jose da silva")
    assert rv.mesmo_nome(" Ana   Lúcia ", "ANA LUCIA")
    assert not rv.mesmo_nome("Maria Souza", "Maria Santos")
    assert not rv.mesmo_nome("", "")


def test_nome_diferente_pede_confirmacao_e_os_dois_ficam_na_trilha(cli):  # noqa: F811
    liga(cli)
    hc, pid = _pronto(cli)
    corpo = _corpo(typed_name="Mary Santos")
    s = _revisa(cli, hc, pid, corpo).json()
    assert s["name_matches"] is False and s["name_on_file"] == "Maria Santos" and s["typed_name"] == "Mary Santos"
    cod = _codigo(cli, hc)
    r = _assina(cli, hc, pid, corpo, sign_code=cod, review_id=s["review_id"])
    assert r.status_code == 400, r.text
    assert "Mary Santos" in r.json()["detail"] and "Maria Santos" in r.json()["detail"] and "Confirm" in r.json()["detail"]
    r = _assina(cli, hc, pid, corpo, sign_code=cod, review_id=s["review_id"], name_mismatch_confirmed=True)
    assert r.status_code == 201, r.text
    con = conectar()
    w = um(con, "SELECT * FROM waivers WHERE id=?", (r.json()["waiver_id"],))
    t = json.loads(w["audit"])
    assert t["typed_name"] == "Mary Santos" and t["signer_name"] == "Maria Santos"
    assert t["review"]["typed_name"] == "Mary Santos" and t["review"]["name_on_file"] == "Maria Santos"
    assert t["review"]["name_matches"] is False and t["review"]["name_mismatch_confirmed"] is True
    sig = json.loads(um(con, "SELECT detail FROM waiver_events WHERE event='signed' AND waiver_id=?", (w["id"],))["detail"])
    assert sig["typed_name"] == "Mary Santos" and sig["name_on_file"] == "Maria Santos" and sig["name_mismatch_confirmed"] is True
    cert = certificado(w["pdf_path"])
    assert "Name on file: Maria Santos" in cert and "Typed name: Mary Santos" in cert and "confirmed signing with the typed name" in cert


def test_nome_igual_nao_pede_confirmacao_e_o_certificado_nao_fala_em_diferenca(cli):  # noqa: F811
    liga(cli)
    hc, pid = _pronto(cli)
    corpo = _corpo(typed_name="maria   SANTOS")
    s = _revisa(cli, hc, pid, corpo).json()
    assert s["name_matches"] is True
    r = _assina(cli, hc, pid, corpo, sign_code=_codigo(cli, hc), review_id=s["review_id"])
    assert r.status_code == 201, r.text
    w = um(conectar(), "SELECT * FROM waivers WHERE id=?", (r.json()["waiver_id"],))
    assert json.loads(w["audit"])["review"]["name_mismatch_confirmed"] is False
    assert "Name on file" not in certificado(w["pdf_path"])


# ------------------------------------------------------------------ as duas horas e a frase de efeito legal
def test_a_trilha_e_o_certificado_tem_as_duas_horas_e_a_frase_do_botao(cli):  # noqa: F811
    liga(cli)
    hc, pid = _pronto(cli)
    corpo = _corpo()
    rid = _revisa(cli, hc, pid, corpo).json()["review_id"]
    r = _assina(cli, hc, pid, corpo, sign_code=_codigo(cli, hc), review_id=rid)
    assert r.status_code == 201, r.text
    con = conectar()
    w = um(con, "SELECT * FROM waivers WHERE id=?", (r.json()["waiver_id"],))
    t = json.loads(w["audit"])
    rev = um(con, "SELECT * FROM waiver_reviews WHERE id=?", (rid,))
    assert t["reviewed_at_utc"] == rev["created_at"] and t["confirmed_at_utc"] == t["signed_at_utc"]
    assert t["reviewed_at_utc"][:19] <= t["confirmed_at_utc"][:19]
    assert t["review"]["legal_effect_statement"] == rv.EFEITO_LEGAL and t["review"]["final_button"] == "I agree — sign the waiver"
    evs = {e["event"]: e for e in todos(con, "SELECT * FROM waiver_events")}
    sig = json.loads(evs["signed"]["detail"])
    assert sig["review_id"] == rid and sig["reviewed_at"] == rev["created_at"] and sig["confirmed_at"] == t["signed_at_utc"]
    assert evs["reviewed"]["at"] <= evs["signed"]["at"]
    covers = sig["covers"]
    assert evs["reviewed"]["id"] in covers, "a revisão entra nos passos que a assinatura cobre (e no certificado)"
    cert = certificado(w["pdf_path"])
    assert "Reviewed the summary:" in cert and "Confirmed and signed:" in cert
    assert "Signer reviewed the summary" in cert
    assert "same legal effect as a handwritten signature" in cert


# ------------------------------------------------------------------ pelo convite
def test_pelo_convite_nao_assina_sem_revisar_e_a_revisao_e_do_convite(cli):  # noqa: F811
    from command_center.tests import test_convite_waiver as tc
    liga(cli)
    h = equipe(cli)
    a = tc.card(name="Bruno Adulto", email="bruno@example.com", pilot_name=None, pilot_dob="1990-02-02")
    b = tc.card(name="Lia Adulta", email="lia@example.com", pilot_name=None, pilot_dob="1991-03-03")
    assert tc.manda(cli, h, a, "bruno@example.com").status_code == 201
    assert tc.manda(cli, h, b, "lia@example.com").status_code == 201
    ta, tb = tc.token_do_email("bruno@example.com"), tc.token_do_email("lia@example.com")
    cli.cookies.clear()
    for t in (ta, tb):
        assert cli.get(f"{P}/invite/{t}/pdf").status_code == 200
    corpo = _corpo(typed_name="Bruno Adulto", relationship=None, guardian_declaration=False)
    assert cli.post(f"{P}/invite/{ta}/code").status_code == 200
    cod = tc.codigo_do_email("bruno@example.com")
    r = cli.post(f"{P}/invite/{ta}/sign", json={**corpo, "sign_code": cod})
    assert r.status_code == 400 and "Review the summary" in r.json()["detail"], r.text
    s = cli.post(f"{P}/invite/{tb}/review", json={**corpo, "typed_name": "Lia Adulta"}).json()
    r = cli.post(f"{P}/invite/{ta}/sign", json={**corpo, "sign_code": cod, "review_id": s["review_id"]})
    assert r.status_code == 400 and "Review the summary" in r.json()["detail"], "a revisão de outro convite não vale"
    s = cli.post(f"{P}/invite/{ta}/review", json=corpo)
    assert s.status_code == 201, s.text
    s = s.json()
    assert s["signing_as"].startswith("Participant") and s["name_on_file"] == "Bruno Adulto" and s["name_matches"] is True
    r = cli.post(f"{P}/invite/{ta}/sign", json={**corpo, "sign_code": cod, "review_id": s["review_id"]})
    assert r.status_code == 201, r.text
    w = um(conectar(), "SELECT * FROM waivers WHERE client_id=? AND source='urace'", (a,))
    t = json.loads(w["audit"])
    assert t["review"]["review_id"] == s["review_id"] and t["reviewed_at_utc"] and t["confirmed_at_utc"] == t["signed_at_utc"]
    assert cli.post(f"{P}/invite/{ta}/review", json=corpo).status_code == 410, "o link usado não revisa de novo"


def test_pelo_convite_o_nome_diferente_do_convite_pede_confirmacao(cli):  # noqa: F811
    from command_center.tests import test_convite_waiver as tc
    liga(cli)
    cid = tc.card(name="Bruno Adulto", email="bruno@example.com", pilot_name=None, pilot_dob="1990-02-02")
    assert tc.manda(cli, equipe(cli), cid, "bruno@example.com").status_code == 201
    token = tc.token_do_email("bruno@example.com")
    cli.cookies.clear()
    assert cli.get(f"{P}/invite/{token}/pdf").status_code == 200
    corpo = _corpo(typed_name="Bruno Adultinho", relationship=None, guardian_declaration=False)
    s = cli.post(f"{P}/invite/{token}/review", json=corpo).json()
    assert s["name_matches"] is False and s["name_on_file"] == "Bruno Adulto"
    assert cli.post(f"{P}/invite/{token}/code").status_code == 200
    cod = tc.codigo_do_email("bruno@example.com")
    r = cli.post(f"{P}/invite/{token}/sign", json={**corpo, "sign_code": cod, "review_id": s["review_id"]})
    assert r.status_code == 400 and "different from the name on file" in r.json()["detail"]
    r = cli.post(f"{P}/invite/{token}/sign", json={**corpo, "sign_code": cod, "review_id": s["review_id"],
                                                  "name_mismatch_confirmed": True})
    assert r.status_code == 201, r.text


# ------------------------------------------------------------------ a tabela das revisões
@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def _revisao(con):
    return rv.criar(con, "account", dict(account_id=1, pilot_id=2, kind="adult"), "t" * 64, "c" * 64, "Ana Teste", "Ana Teste",
                    None, ip="203.0.113.5", user_agent="Test/1.0")["id"]


def test_toda_coluna_da_revisao_esta_na_trava(con):
    colunas = {r[1] for r in con.execute("PRAGMA table_info(waiver_reviews)")}
    assert colunas == set(db.REVISAO_TRAVADAS) | {"used_at"}, colunas ^ (set(db.REVISAO_TRAVADAS) | {"used_at"})


@pytest.mark.parametrize("coluna,valor", [("typed_name", "Outro Nome"), ("content_sha256", "d" * 64), ("pilot_id", 9),
                                          ("expires_at", "2999-01-01T00:00:00.000Z"), ("name_matches", 0)])
def test_a_revisao_nao_muda(con, coluna, valor):
    rid = _revisao(con)
    with pytest.raises(sqlite3.IntegrityError, match="only used_at"):
        con.execute(f"UPDATE waiver_reviews SET {coluna}=? WHERE id=?", (valor, rid))


def test_a_revisao_so_se_marca_usada_uma_vez_e_nunca_sai(con):
    rid = _revisao(con)
    rv.marcar_usada(con, rid)
    with pytest.raises(sqlite3.IntegrityError, match="only used_at"):
        con.execute("UPDATE waiver_reviews SET used_at='2026-01-01T00:00:00.000Z' WHERE id=?", (rid,))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        con.execute("DELETE FROM waiver_reviews WHERE id=?", (rid,))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT OR REPLACE INTO waiver_reviews (id, created_at, expires_at, flow, kind, template_sha256, "
                    "content_sha256, typed_name, name_matches) VALUES (?, 'x', 'x', 'account', 'adult', 't', 'c', 'n', 1)", (rid,))
    assert um(con, "SELECT COUNT(*) AS n FROM waiver_reviews")["n"] == 1


def test_a_trava_da_revisao_entra_a_cada_subida(con):
    con.execute("DROP TRIGGER waiver_reviews_so_usar")
    aplicar_schema(con)
    assert um(con, "SELECT 1 AS x FROM sqlite_master WHERE type='trigger' AND name='waiver_reviews_so_usar'")

"""Trilha de eventos da waiver nativa, append-only e encadeada (#111, lacuna C-3).

O que estes testes trancam: uma assinatura completa, pela conta e pelo convite, gera a sequência inteira, na
ordem (convite enviado, abriu a tela, recebeu o PDF, leu todas as páginas, revisou o resumo (#112), código enviado,
código confirmado, assinou), cada passo com hora, IP e aparelho; o certificado do PDF lista esses passos com a hora na
Flórida e em UTC e muda de página em vez de cortar; UPDATE e DELETE nos eventos levantam erro; refazer a cadeia
de hashes acha a linha mexida; a tela só registra o que está na lista fechada, com limite; e o que vem depois
de assinar (PDF baixado, anulada) fica na trilha, fora do PDF selado."""
import io
import json
import re
import sqlite3
from datetime import datetime, timezone

import pytest

from command_center import db
from command_center.db import aplicar_schema, conectar, todos, um
from command_center.providers import waiver_nativa as wn
from command_center.tests.test_waiver_nativa import (CONTA, P, PARENTAL, S, _assinatura, cli, cliente, confirma_email,  # noqa: F401
                                                     equipe, liga, ultimo_codigo)

API = "/ops/api"
ANTES = ["screen_opened", "pdf_delivered", "all_pages_viewed", "reviewed", "code_sent", "code_verified"]
REVISOU = "Signer reviewed the summary (driver, signer, relationship, typed name, signature) before the final click"


def _corpo(**mais):
    return {"typed_name": "Maria Santos", "signature": _assinatura(), "read_and_agree": True, "consent_esign": True,
            "english_understood": True, "relationship": "mother", "guardian_declaration": True,
            "document_read_at": datetime.now(timezone.utc).isoformat(), "document_read_mode": "pdf_viewer", **mais}


def revisa(cli, url, corpo, h=None):  # noqa: F811
    """#112: o passo 1 (a revisão); devolve o `review_id`."""
    r = cli.post(url, json=corpo, headers=h or {})
    assert r.status_code == 201, r.text
    return r.json()["review_id"]


def assina_como_a_tela(cli, hc, pid, kind="parental", email="maria@example.com"):  # noqa: F811
    """A ordem da tela de verdade: abre a tela, recebe o PDF, lê tudo, confirma o e-mail, revisa o resumo (#112), pede o
    código e assina."""
    assert cli.post(f"{P}/drivers/{pid}/waiver/events", json={"event": "screen_opened"}, headers=hc).status_code == 201
    assert cli.get(f"{P}/waivers/model/{kind}/pdf?driver={pid}").status_code == 200
    r = cli.post(f"{P}/drivers/{pid}/waiver/events", json={"event": "all_pages_viewed", "mode": "pdf_viewer", "pages": 1}, headers=hc)
    assert r.status_code == 201, r.text
    confirma_email(cli, hc)
    corpo = _corpo()
    rid = revisa(cli, f"{P}/drivers/{pid}/waiver/review", corpo, hc)
    cli.post(f"{P}/waivers/code", headers=hc)
    r = cli.post(f"{P}/drivers/{pid}/waiver", json={**corpo, "sign_code": ultimo_codigo(email), "review_id": rid}, headers=hc)
    assert r.status_code == 201, r.text
    return r.json()["waiver_id"]


def _texto_do_certificado(caminho, paginas_do_modelo=1):
    from pypdf import PdfReader
    return " ".join(" ".join((p.extract_text() or "").split()) for p in PdfReader(caminho).pages[paginas_do_modelo:])


# ------------------------------------------------------------------ a sequência inteira
def test_assinatura_pela_conta_gera_a_sequencia_inteira_na_ordem(cli):  # noqa: F811
    liga(cli)
    hc, (pid,) = cliente(cli)
    wid = assina_como_a_tela(cli, hc, pid)
    con = conectar()
    s = um(con, "SELECT * FROM waiver_events WHERE event='signed' AND waiver_id=?", (wid,))
    cobre = json.loads(s["detail"])["covers"]
    evs = todos(con, f"SELECT * FROM waiver_events WHERE id IN ({','.join('?' * len(cobre))}) ORDER BY id", tuple(cobre))
    assert [e["event"] for e in evs] == ANTES, [e["event"] for e in evs]
    assert all(e["account_id"] and e["flow"] == "account" and e["ip"] and e["user_agent"] for e in evs + [s])
    assert {e["source"] for e in evs if e["event"] in ("screen_opened", "all_pages_viewed")} == {"client"}
    assert {e["source"] for e in evs if e["event"] not in ("screen_opened", "all_pages_viewed")} == {"server"}
    assert s["signature_id"] and s["pilot_id"] == pid and s["kind"] == "parental" and s["id"] > max(cobre)
    assert json.loads(s["detail"])["document_sha256"] == um(con, "SELECT doc_sha256 FROM waivers WHERE id=?", (wid,))["doc_sha256"]
    # a mesma lista vai para a trilha da waiver (imutável) e para o certificado do PDF
    w = um(con, "SELECT * FROM waivers WHERE id=?", (wid,))
    t = json.loads(w["audit"])
    assert [e["event"] for e in t["events"]] == ANTES and t["events_chain_hash"] == evs[-1]["hash"]
    cert = _texto_do_certificado(w["pdf_path"])
    assert "Event history (Florida time, America/New_York, and UTC)" in cert
    for rotulo in ("Signing page opened", "Document (PDF) delivered to the signer", "Every page of the document shown on screen",
                   "One-time code emailed to the signer", "One-time code confirmed", REVISOU):
        assert rotulo in cert, rotulo
    assert "reported by the signer's browser" in cert and "recorded by URACE's server" in cert
    historia = cert.split("Event history", 1)[1]
    horas = re.findall(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d (EDT|EST) \(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ UTC\)", historia)
    assert len(horas) == len(ANTES) + 1, historia               # os seis passos e a própria assinatura
    assert evs[-1]["hash"] in cert.replace(" ", "")


def test_assinatura_pelo_convite_gera_a_sequencia_inteira_na_ordem(cli):  # noqa: F811
    from command_center.providers import trilha_waiver as tw
    from command_center.tests import test_convite_waiver as tc
    liga(cli)
    cid = tc.card(name="Bruno Adulto", email="bruno@example.com", pilot_name=None, pilot_dob="1990-02-02")
    h = equipe(cli)
    assert tc.manda(cli, h, cid, "bruno@example.com").status_code == 201
    token = tc.token_do_email("bruno@example.com")
    cli.cookies.clear()
    assert cli.get(f"{P}/invite/{token}").status_code == 200
    assert cli.get(f"{P}/invite/{token}/pdf").status_code == 200
    r = cli.post(f"{P}/invite/{token}/events", json={"event": "all_pages_viewed", "mode": "pdf_viewer"})
    assert r.status_code == 201, r.text
    corpo = _corpo(typed_name="Bruno Adulto", relationship=None, guardian_declaration=False)
    rid = revisa(cli, f"{P}/invite/{token}/review", corpo)
    assert cli.post(f"{P}/invite/{token}/code").status_code == 200
    r = cli.post(f"{P}/invite/{token}/sign", json={**corpo, "sign_code": tc.codigo_do_email("bruno@example.com"), "review_id": rid})
    assert r.status_code == 201, r.text
    con = conectar()
    w = um(con, "SELECT * FROM waivers WHERE client_id=? AND source='urace'", (cid,))
    evs = [e for e in tw.da_waiver(con, w["id"])]
    assert [e["event"] for e in evs] == ["invite_sent", "screen_opened", "pdf_delivered", "all_pages_viewed", "reviewed",
                                         "code_sent", "code_verified", "signed"], [e["event"] for e in evs]
    assert all(e["invite_id"] and e["flow"] == "invite" and e["client_id"] == cid for e in evs)
    assert all(e["ip"] for e in evs) and all(e["user_agent"] for e in evs if e["event"] != "invite_sent")
    assert evs[0]["detail"]["to"] == "b••••@example.com", "o e-mail vai mascarado na trilha"
    cert = _texto_do_certificado(w["pdf_path"])
    assert "Invitation link emailed to the signer" in cert and "Signing page opened" in cert
    # o PDF do convite baixado depois de assinar vai para a trilha, fora do PDF selado
    assert cli.get(f"{P}/invite/{token}/signed.pdf").status_code == 200
    depois = [e for e in tw.da_waiver(con, w["id"]) if e["phase"] == "after"]
    assert [e["event"] for e in depois] == ["downloaded"] and depois[0]["detail"] == {"by": "signer"}


def test_irmaos_cada_assinatura_cobre_so_os_passos_dela(cli):  # noqa: F811
    liga(cli)
    hc, (a, b) = cliente(cli, pilotos=(("Leo Santos", "2014-05-01"), ("Ana Santos", "2016-03-03")))
    wa = assina_como_a_tela(cli, hc, a)
    um_minuto_atras = "2000-01-01T00:00:00Z"
    c = conectar(); c.execute("UPDATE portal_codes SET created_at=?", (um_minuto_atras,)); c.commit(); c.close()
    wb = assina_como_a_tela(cli, hc, b)
    con = conectar()
    ca = json.loads(um(con, "SELECT detail FROM waiver_events WHERE event='signed' AND waiver_id=?", (wa,))["detail"])["covers"]
    cb = json.loads(um(con, "SELECT detail FROM waiver_events WHERE event='signed' AND waiver_id=?", (wb,))["detail"])["covers"]
    assert not set(ca) & set(cb) and min(cb) > max(ca)
    assert {e["pilot_id"] for e in todos(con, f"SELECT pilot_id FROM waiver_events WHERE id IN ({','.join('?' * len(cb))})",
                                         tuple(cb))} <= {b, None}


# ------------------------------------------------------------------ append-only e a cadeia
@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def _alguns(con, n=4):
    from command_center.providers import trilha_waiver as tw
    return [tw.registrar(con, "screen_opened", "account", source="client", ip="203.0.113.5", user_agent="Test/1.0",
                         account_id=1, pilot_id=2, kind="adult")["id"] for _ in range(n)]


def test_update_e_delete_nos_eventos_levantam_erro(con):
    eid = _alguns(con, 1)[0]
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute("UPDATE waiver_events SET ip='198.51.100.9' WHERE id=?", (eid,))
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute("DELETE FROM waiver_events WHERE id=?", (eid,))
    assert "waiver_events_no_update" in db._travas_da_waiver() and "waiver_events_no_delete" in db._travas_da_waiver()
    con.execute("DROP TRIGGER waiver_events_no_delete")
    aplicar_schema(con)                                   # a trava volta na subida
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute("DELETE FROM waiver_events WHERE id=?", (eid,))


def test_a_cadeia_de_hashes_acha_a_linha_mexida(con):
    from command_center.providers import trilha_waiver as tw
    ids = _alguns(con, 5)
    v = tw.verificar(con)
    assert v["ok"] and v["total"] == 5
    ponta = um(con, "SELECT * FROM waiver_events ORDER BY id DESC LIMIT 1")
    assert ponta["prev_hash"] == um(con, "SELECT hash FROM waiver_events WHERE id=?", (ids[-2],))["hash"]
    # no teste, tirando a trava para conseguir mexer
    con.execute("DROP TRIGGER waiver_events_no_update")
    con.execute("UPDATE waiver_events SET ip='198.51.100.9' WHERE id=?", (ids[2],))
    v = tw.verificar(con)
    assert not v["ok"] and v["first_bad_id"] == ids[2]
    aplicar_schema(con)


def test_a_cadeia_acha_a_linha_tirada_do_meio(con):
    from command_center.providers import trilha_waiver as tw
    ids = _alguns(con, 4)
    con.execute("DROP TRIGGER waiver_events_no_delete")
    con.execute("DELETE FROM waiver_events WHERE id=?", (ids[1],))
    v = tw.verificar(con)
    assert not v["ok"] and v["first_bad_id"] == ids[2]


def test_so_eventos_da_lista_fechada(con):
    from command_center.providers import trilha_waiver as tw
    with pytest.raises(ValueError):
        tw.registrar(con, "inventado", "account", account_id=1)
    with pytest.raises(ValueError):
        tw.registrar(con, "signed", "outro", account_id=1)
    with pytest.raises(ValueError):
        tw.da_tela(con, "signed", "account", account_id=1)
    assert not todos(con, "SELECT 1 FROM waiver_events")


# ------------------------------------------------------------------ o que vem da tela
def test_a_tela_so_registra_a_lista_fechada_com_limite(cli, monkeypatch):  # noqa: F811
    liga(cli)
    _, (pid_outro,) = cliente(cli, conta={**CONTA, "email": "outra@example.com"})
    hc, (pid,) = cliente(cli)
    ev = f"{P}/drivers/{pid}/waiver/events"
    assert cli.post(ev, json={"event": "signed"}, headers=hc).status_code == 400, "assinar só o servidor registra"
    assert cli.post(ev, json={"event": "all_pages_viewed", "mode": "pulei"}, headers=hc).status_code == 400
    assert cli.post(ev, json={"event": "screen_opened", "waiver_id": 1}, headers=hc).status_code == 422
    assert cli.post(f"{P}/drivers/{pid_outro}/waiver/events", json={"event": "screen_opened"}, headers=hc).status_code == 404
    from command_center.providers import trilha_waiver as tw
    monkeypatch.setattr(tw, "TELA_POR_HORA", 3)
    assert [cli.post(ev, json={"event": "screen_opened"}, headers=hc).status_code for _ in range(4)] == [201, 201, 201, 429]
    h = equipe(cli)
    assert cli.post(f"{S}/waiver-nativa/ligar", json={"ligada": False}, headers=h).status_code == 200
    cli.cookies.clear()
    assert cli.post(f"{P}/login", json={"email": CONTA["email"], "password": CONTA["password"]}).status_code == 200
    hc = {"X-CSRF": cli.cookies.get("cp_csrf")}
    assert cli.post(ev, json={"event": "screen_opened"}, headers=hc).status_code == 404, "desligada, a tela não registra"
    assert cli.post(f"{P}/invite/inventado.x/events", json={"event": "all_pages_viewed", "mode": "pdf_viewer"}).status_code == 404


def test_recarregar_o_link_do_convite_em_loop_nao_enche_a_trilha(cli, monkeypatch):  # noqa: F811
    from command_center.providers import trilha_waiver as tw
    from command_center.tests import test_convite_waiver as tc
    liga(cli)
    cid = tc.card(name="Bruno Adulto", email="bruno@example.com", pilot_name=None, pilot_dob="1990-02-02")
    assert tc.manda(cli, equipe(cli), cid, "bruno@example.com").status_code == 201
    token = tc.token_do_email("bruno@example.com")
    monkeypatch.setattr(tw, "TELA_POR_HORA", 3)
    cli.cookies.clear()
    assert all(cli.get(f"{P}/invite/{token}").status_code == 200 for _ in range(5)), "a página continua abrindo"
    assert um(conectar(), "SELECT COUNT(*) AS n FROM waiver_events WHERE event='screen_opened'")["n"] == 3


# ------------------------------------------------------------------ depois de assinar e o painel
def test_depois_de_assinar_baixar_e_anular_ficam_na_trilha_e_o_painel_mostra(cli):  # noqa: F811
    from command_center.api import auth
    from command_center.tests.test_waiver_nativa import SENHA
    liga(cli)
    hc, (pid,) = cliente(cli)
    wid = assina_como_a_tela(cli, hc, pid)
    pdf_antes = open(um(conectar(), "SELECT pdf_path FROM waivers WHERE id=?", (wid,))["pdf_path"], "rb").read()
    assert cli.get(f"{P}/waivers/{wid}/pdf").status_code == 200
    h = equipe(cli, "ger@urace.us")
    assert cli.get(f"{API}/waivers/{wid}/download").status_code == 200
    assert cli.post(f"{API}/waivers/{wid}/void", json={"reason": "assinada pelo responsável errado"}, headers=h).status_code == 200
    r = cli.get(f"{S}/waiver-nativa/{wid}/eventos")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["cadeia"]["ok"] and d["cadeia"]["total"] == len(todos(conectar(), "SELECT id FROM waiver_events"))
    fases = [(e["phase"], e["event"]) for e in d["eventos"]]
    assert fases == [("before", x) for x in ANTES] + [("signed", "signed"), ("after", "downloaded"), ("after", "downloaded"),
                                                      ("after", "voided")], fases
    depois = [e for e in d["eventos"] if e["phase"] == "after"]
    assert [e["flow"] for e in depois] == ["account", "staff", "staff"] and depois[2]["detail"]["reason"] == "assinada pelo responsável errado"
    assert open(um(conectar(), "SELECT pdf_path FROM waivers WHERE id=?", (wid,))["pdf_path"], "rb").read() == pdf_antes, \
        "o que vem depois não toca o PDF selado"
    assert cli.get(f"{S}/waiver-nativa/999999/eventos").status_code == 404
    c = conectar(); auth.criar_usuario(c, "op@urace.us", "Operador", "OPERATOR", SENHA); c.commit(); c.close()
    equipe(cli, "op@urace.us")
    assert cli.get(f"{S}/waiver-nativa/{wid}/eventos").status_code == 403


# ------------------------------------------------------------------ o certificado não corta
def test_com_30_eventos_o_certificado_muda_de_pagina_em_vez_de_cortar(tmp_path):
    from command_center.providers import trilha_waiver as tw
    from pypdf import PdfReader
    from command_center.providers import portal
    linhas = [{"id": i, "event": ev, "source": "client" if ev in tw.DA_TELA else "server", "ip": "203.0.113.5",
               "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
               "hash": f"{i:064x}", "at": f"2026-01-15T14:{i:02d}:00.000Z"}
              for i, ev in enumerate((ANTES * 5)[:30], start=1)]
    t = {"signature_id": "00000000-0000-4000-8000-000000000000", "template": "parental", "template_name": "Parental (teste)",
         "template_sha256": "a" * 64, "template_pages": 1, "signer_name": "Test Parent", "account_email": "parent@example.com",
         "driver_name": "Test Kid", "driver_birth_date": "2014-05-01", "signer_relationship": "Mother",
         "guardian_declaration": wn.DECLARACAO.format(minor="Test Kid"), "typed_name": "Test Parent",
         "signed_at_utc": "2026-01-15T15:00:00Z", "signed_at_local": "2026-01-15 10:00:00 EST", "valid_until": "2027-01-15",
         "ip": "203.0.113.5", "user_agent": "Test/1.0", "authentication": "test", "signature_png_sha256": "b" * 64,
         "events": tw.para_o_certificado(linhas, portal.FUSO), "events_chain_hash": "c" * 64}
    import base64
    png = base64.b64decode(_assinatura().split(",", 1)[1])
    pdf = wn._pdf_assinado(PARENTAL, t, png)
    paginas = PdfReader(io.BytesIO(pdf)).pages
    assert len(paginas) >= 3, "o modelo (1) e o certificado em mais de uma página"
    texto = " ".join(" ".join((p.extract_text() or "").split()) for p in paginas[1:])
    historia = texto.split("Event history", 1)[1]                      # os 30 e a própria assinatura
    assert len(re.findall(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d EST \(2026-01-15T\d\d:\d\d:00Z UTC\)", historia)) == 31
    assert "(continued)" in texto and texto.rstrip().endswith("has not been altered.")
    for p in paginas[1:]:                                 # nada abaixo da margem do pé
        ys = []
        p.extract_text(visitor_text=lambda txt, cm, tm, f, s: ys.append(tm[5] * cm[3] + cm[5]) if txt.strip() else None)
        assert ys and min(ys) >= wn.MARGEM_PE - 1, min(ys)



# ------------------------------------------------------------------ revisão do PR #329
def _sign(cli, hc, pid, email="maria@example.com", **mais):  # noqa: F811
    corpo = _corpo(**mais)
    rid = revisa(cli, f"{P}/drivers/{pid}/waiver/review", corpo, hc)
    c = conectar(); c.execute("UPDATE portal_codes SET created_at='2000-01-01T00:00:00Z'"); c.commit(); c.close()
    cli.post(f"{P}/waivers/code", headers=hc)
    return cli.post(f"{P}/drivers/{pid}/waiver", json={**corpo, "sign_code": ultimo_codigo(email), "review_id": rid}, headers=hc)


def test_recarregar_o_convite_em_loop_nao_enche_a_trilha_nem_o_certificado(cli):  # noqa: F811
    """200 recargas da tela do convite (o link e o PDF do visor) geravam 234 eventos e 15 páginas de certificado."""
    from pypdf import PdfReader
    from command_center.tests import test_convite_waiver as tc
    liga(cli)
    cid = tc.card(name="Bruno Adulto", email="bruno@example.com", pilot_name=None, pilot_dob="1990-02-02")
    assert tc.manda(cli, equipe(cli), cid, "bruno@example.com").status_code == 201
    token = tc.token_do_email("bruno@example.com")
    cli.cookies.clear()
    for _ in range(200):
        assert cli.get(f"{P}/invite/{token}").status_code == 200
        assert cli.get(f"{P}/invite/{token}/pdf").status_code == 200, "o PDF continua saindo"
    con = conectar()
    n = {r["event"]: r["n"] for r in todos(con, "SELECT event, COUNT(*) AS n FROM waiver_events GROUP BY event")}
    assert n["screen_opened"] == 30 and n["pdf_delivered"] == 30, n
    assert um(con, "SELECT COUNT(*) AS n FROM audit_logs WHERE event='waiver.invite.document_view'")["n"] == 200, \
        "a entrega do #107 continua toda no audit_logs"
    corpo = _corpo(typed_name="Bruno Adulto", relationship=None, guardian_declaration=False)
    rid = revisa(cli, f"{P}/invite/{token}/review", corpo)
    assert cli.post(f"{P}/invite/{token}/code").status_code == 200
    r = cli.post(f"{P}/invite/{token}/sign", json={**corpo, "sign_code": tc.codigo_do_email("bruno@example.com"), "review_id": rid})
    assert r.status_code == 201, r.text
    w = um(con, "SELECT * FROM waivers WHERE client_id=? AND source='urace'", (cid,))
    t = json.loads(w["audit"])
    assert [(e["event"], e["count"]) for e in t["events"]] == [("invite_sent", 1), ("screen_opened", 30), ("pdf_delivered", 30),
                                                            ("reviewed", 1), ("code_sent", 1), ("code_verified", 1)], t["events"]
    assert len(PdfReader(w["pdf_path"]).pages) <= 3, "o modelo e o certificado em no máximo duas páginas"
    cert = " ".join(" ".join((p.extract_text() or "").split()) for p in PdfReader(w["pdf_path"]).pages[1:])
    assert re.search(r"\(\S+ UTC\) to \d{4}-\d\d-\d\d \d\d:\d\d:\d\d E[DS]T \(\S+ UTC\) · Signing page opened ×30", cert), cert


def test_o_pdf_da_conta_em_loop_tem_teto_por_conta_e_modelo(cli):  # noqa: F811
    liga(cli)
    hc, (pid,) = cliente(cli)
    for _ in range(100):
        assert cli.get(f"{P}/waivers/model/parental/pdf?driver={pid}").status_code == 200
    assert cli.get(f"{P}/waivers/model/adult/pdf").status_code == 200, "o outro modelo tem o seu teto"
    con = conectar()
    assert um(con, "SELECT COUNT(*) AS n FROM waiver_events WHERE event='pdf_delivered' AND kind='parental'")["n"] == 30
    assert um(con, "SELECT COUNT(*) AS n FROM waiver_events WHERE event='pdf_delivered' AND kind='adult'")["n"] == 1
    wid = assina_como_a_tela(cli, hc, pid)
    t = json.loads(um(con, "SELECT audit FROM waivers WHERE id=?", (wid,))["audit"])
    assert [e["count"] for e in t["events"] if e["event"] == "pdf_delivered"] == [30]


def test_abrir_a_tela_muitas_vezes_nao_tira_o_leu_todas_as_paginas(cli):  # noqa: F811
    """O teto era um só para os dois eventos da tela, por conta: 30 aberturas tiravam a leitura do certificado."""
    liga(cli)
    hc, (pid, irmao) = cliente(cli, pilotos=(("Leo Santos", "2014-05-01"), ("Ana Santos", "2016-03-03")))
    ev = f"{P}/drivers/{pid}/waiver/events"
    assert [cli.post(ev, json={"event": "screen_opened"}, headers=hc).status_code for _ in range(31)][-2:] == [201, 429]
    assert cli.post(f"{P}/drivers/{irmao}/waiver/events", json={"event": "screen_opened"}, headers=hc).status_code == 201, \
        "o teto é por piloto"
    assert cli.get(f"{P}/waivers/model/parental/pdf?driver={pid}").status_code == 200
    assert cli.post(ev, json={"event": "all_pages_viewed", "mode": "pdf_viewer"}, headers=hc).status_code == 201
    confirma_email(cli, hc)
    r = _sign(cli, hc, pid)
    assert r.status_code == 201, r.text
    t = json.loads(um(conectar(), "SELECT audit FROM waivers WHERE id=?", (r.json()["waiver_id"],))["audit"])
    assert "all_pages_viewed" in [e["event"] for e in t["events"]]


def test_irmaos_em_duas_abas_cada_certificado_tem_os_passos_do_seu_piloto(cli):  # noqa: F811
    """A mãe abre e lê A e B (duas abas), assina A e depois B: o certificado de cada um tem os passos daquele piloto."""
    liga(cli)
    hc, (a, b) = cliente(cli, pilotos=(("Leo Santos", "2014-05-01"), ("Ana Santos", "2016-03-03")))
    for pid in (a, b):
        assert cli.post(f"{P}/drivers/{pid}/waiver/events", json={"event": "screen_opened"}, headers=hc).status_code == 201
        assert cli.get(f"{P}/waivers/model/parental/pdf?driver={pid}").status_code == 200
        assert cli.post(f"{P}/drivers/{pid}/waiver/events", json={"event": "all_pages_viewed", "mode": "pdf_viewer"},
                        headers=hc).status_code == 201
    confirma_email(cli, hc)
    wa = _sign(cli, hc, a).json()["waiver_id"]
    wb = _sign(cli, hc, b).json()["waiver_id"]
    con = conectar()
    for wid, pid in ((wa, a), (wb, b)):
        cob = json.loads(um(con, "SELECT detail FROM waiver_events WHERE event='signed' AND waiver_id=?", (wid,))["detail"])["covers"]
        evs = todos(con, f"SELECT * FROM waiver_events WHERE id IN ({','.join('?' * len(cob))}) ORDER BY id", tuple(cob))
        assert [e["event"] for e in evs] == ANTES, (pid, [e["event"] for e in evs])
        assert {e["pilot_id"] for e in evs if e["event"] in ("screen_opened", "pdf_delivered", "all_pages_viewed",
                                                              "code_verified", "reviewed")} == {pid}
        assert [e["pilot_id"] for e in evs if e["event"] == "code_sent"] == [None]
    o_outro = um(con, "SELECT pilot_id FROM waiver_events WHERE event='pdf_delivered' AND pilot_id=?", (b,))
    assert o_outro and o_outro["pilot_id"] == b, "o PDF da aba de B fica com o piloto B"


def test_pdf_com_piloto_de_outra_conta_fica_sem_piloto(cli):  # noqa: F811
    liga(cli)
    _, (outro,) = cliente(cli, conta={**CONTA, "email": "outra@example.com"})
    cliente(cli)
    assert cli.get(f"{P}/waivers/model/parental/pdf?driver={outro}").status_code == 200
    assert um(conectar(), "SELECT pilot_id FROM waiver_events WHERE event='pdf_delivered' ORDER BY id DESC LIMIT 1")["pilot_id"] is None


@pytest.mark.parametrize("pelo", ["conta", "convite"])
def test_nome_digitado_com_surrogate_solto_nao_vira_500(cli, pelo):  # noqa: F811
    """`\\ud800` solto no JSON dava UnicodeEncodeError (500). Agora sai do nome e a assinatura segue."""
    from command_center.tests import test_convite_waiver as tc
    liga(cli)
    if pelo == "conta":
        hc, (pid,) = cliente(cli)
        assert cli.get(f"{P}/waivers/model/parental/pdf?driver={pid}").status_code == 200
        confirma_email(cli, hc)
        corpo, url, h, nome = _corpo(), f"{P}/drivers/{pid}/waiver", hc, "Maria Santos"
        codigo = lambda: (cli.post(f"{P}/waivers/code", headers=hc), ultimo_codigo("maria@example.com"))[1]  # noqa: E731
    else:
        cid = tc.card(name="Bruno Adulto", email="bruno@example.com", pilot_name=None, pilot_dob="1990-02-02")
        assert tc.manda(cli, equipe(cli), cid, "bruno@example.com").status_code == 201
        token = tc.token_do_email("bruno@example.com")
        cli.cookies.clear()
        assert cli.get(f"{P}/invite/{token}/pdf").status_code == 200
        corpo = _corpo(typed_name="Bruno Adulto", relationship=None, guardian_declaration=False)
        url, h, nome = f"{P}/invite/{token}/sign", {}, "Bruno Adulto"
        codigo = lambda: (cli.post(f"{P}/invite/{token}/code"), tc.codigo_do_email("bruno@example.com"))[1]  # noqa: E731
    sujo = f'"{nome.split()[0]} \\ud800 {nome.split()[1]}"'
    revisao = url.replace("/sign", "/review") if url.endswith("/sign") else url + "/review"
    r = cli.post(revisao, content=json.dumps(corpo).replace(f'"{nome}"', sujo), headers={**h, "Content-Type": "application/json"})
    assert r.status_code == 201, r.text                    # #112: a revisão também não vira 500
    assert r.json()["name_matches"] is True, "o surrogate sai do nome antes de comparar"
    corpo = {**corpo, "review_id": r.json()["review_id"], "sign_code": codigo()}
    r = cli.post(url, content=json.dumps(corpo).replace(f'"{nome}"', sujo), headers={**h, "Content-Type": "application/json"})
    assert r.status_code == 201, r.text
    t = json.loads(um(conectar(), "SELECT audit FROM waivers WHERE source='urace' ORDER BY id DESC LIMIT 1")["audit"])
    assert t["typed_name"] == nome
    from command_center.providers import trilha_waiver as tw
    assert tw.verificar(conectar())["ok"]


def test_motivo_da_anulacao_com_surrogate_nao_vira_500(cli):  # noqa: F811
    liga(cli)
    hc, (pid,) = cliente(cli)
    wid = assina_como_a_tela(cli, hc, pid)
    h = equipe(cli, "ger@urace.us")
    bruto = json.dumps({"reason": "assinada por engano no teste"}).replace("engano", "engano \\udfff")
    r = cli.post(f"{API}/waivers/{wid}/void", content=bruto, headers={**h, "Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    assert r.json()["reason"] == "assinada por engano no teste"


def test_insert_or_replace_nao_passa_pela_trava_dos_eventos(con):
    from command_center.providers import trilha_waiver as tw
    e = tw.registrar(con, "screen_opened", "account", account_id=1)
    campos = {k: e[k] for k in ("id", "at", "flow", "event", "source", "hash")}
    sql = f"({', '.join(campos)}) VALUES ({', '.join('?' * len(campos))})"
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute(f"INSERT OR REPLACE INTO waiver_events {sql}", (*list(campos.values())[:-1], "x" * 64))
    con.execute(f"INSERT OR IGNORE INTO waiver_events {sql}", tuple(campos.values()))
    assert tw.verificar(con)["ok"] and um(con, "SELECT COUNT(*) AS n FROM waiver_events")["n"] == 1

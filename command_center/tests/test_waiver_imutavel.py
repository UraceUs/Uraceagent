"""Waiver assinada no próprio sistema: registro imutável e fora da lixeira (#109, lacunas D-1 e D-3).

Dono, 06/10: *"nunca apagar"*. O que estes testes trancam: a linha da waiver nativa assinada não muda
(UPDATE dos campos de prova e DELETE levantam erro no próprio SQLite); ficam livres só o vínculo com o
card e a lixeira do painel; a lixeira, pela rota e pela IA, recusa a nativa assinada; a trilha inteira
vai também para o `audit_logs`; o PDF final fica só leitura; o gerente anula com motivo numa tabela
própria (append-only) e a anulada deixa de valer, mas continua no card, na lista e no backup de verdade."""
import json
import os
import sqlite3

import pytest

from command_center.api import auth
from command_center import db
from command_center.db import aplicar_schema, conectar, inserir, todos, um
from command_center.providers import waiver_nativa as wn
from command_center.tests.test_waiver_nativa import P, SENHA, assina, cli, cliente, equipe, liga  # noqa: F401 (fixture)

API = "/ops/api"


def nativa(con, **campos):
    """Uma waiver nativa assinada, gravada direto (o INSERT é livre: o que a trava segura é a linha depois)."""
    base = dict(signer_name="Maria Santos", signer_email="maria@example.com", template="adult", status="completed",
                sent_at="2026-10-01T12:00:00.000Z", completed_at="2026-10-01T12:00:00.000Z", expires_at="2027-10-01",
                source="urace", doc_sha256="a" * 64, audit=json.dumps({"ip": "203.0.113.5"}), pdf_path="/nao/existe.pdf")
    return inserir(con, "waivers", **{**base, **campos})


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def assinada(cli, nome="Leo Santos", nasc="2014-05-01"):  # noqa: F811
    """Liga, cria a conta com um piloto e assina pela área do cliente. Devolve (waiver_id, client_id, pid, hc)."""
    liga(cli)
    hc, (pid,) = cliente(cli, pilotos=((nome, nasc),))
    r = assina(cli, hc, pid)
    assert r.status_code == 201, r.text
    wid = r.json()["waiver_id"]
    con = conectar()
    cid = inserir(con, "clients", name="Maria Santos", email="maria@example.com", pilot_name=nome, status="ACTIVE", source="manual")
    con.execute("UPDATE waivers SET client_id=?, link_by='human', link_reason='teste' WHERE id=?", (cid, wid))
    con.commit(); con.close()
    return wid, cid, pid, hc


# ------------------------------------------------------------------ a trava no banco
def test_toda_coluna_da_waiver_e_livre_ou_travada(con):
    """Coluna nova em `waivers` tem de ser classificada: nasce sem trava só se alguém decidir isso."""
    colunas = {r[1] for r in con.execute("PRAGMA table_info(waivers)")}
    assert not set(db.WAIVER_LIVRES) & set(db.WAIVER_TRAVADAS)
    assert colunas == set(db.WAIVER_LIVRES) | set(db.WAIVER_TRAVADAS)
    assert set(db.WAIVER_LIVRES) == {"client_id", "hidden", "link_by", "link_reason"}


@pytest.mark.parametrize("coluna,valor", [("doc_sha256", "b" * 64), ("audit", "{}"), ("pdf_path", "/outro.pdf"),
                                          ("status", "voided"), ("expires_at", "2030-01-01"), ("signer_email", "x@example.com"),
                                          ("completed_at", "2026-01-01T00:00:00Z"), ("source", None), ("id", 99999)])
def test_update_de_prova_na_nativa_e_recusado(con, coluna, valor):
    wid = nativa(con)
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        con.execute(f"UPDATE waivers SET {coluna}=? WHERE id=?", (valor, wid))
    w = um(con, "SELECT * FROM waivers WHERE id=?", (wid,))
    assert w["doc_sha256"] == "a" * 64 and w["status"] == "completed" and w["source"] == "urace"


def test_delete_da_nativa_e_recusado(con):
    wid = nativa(con)
    with pytest.raises(sqlite3.DatabaseError, match="never deleted"):
        con.execute("DELETE FROM waivers WHERE id=?", (wid,))
    assert um(con, "SELECT id FROM waivers WHERE id=?", (wid,))


def test_o_vinculo_com_o_card_e_a_lixeira_continuam_livres(con):
    wid = nativa(con)
    cid = inserir(con, "clients", name="Maria Santos", status="ACTIVE", source="manual")
    con.execute("UPDATE waivers SET client_id=?, link_by='human', link_reason='à mão' WHERE id=?", (cid, wid))
    con.execute("UPDATE waivers SET hidden=1 WHERE id=?", (wid,))
    con.execute("UPDATE waivers SET hidden=0 WHERE id=?", (wid,))
    con.execute("UPDATE waivers SET doc_sha256=doc_sha256, audit=audit WHERE id=?", (wid,))   # escrever o mesmo valor não é mudar
    assert um(con, "SELECT client_id FROM waivers WHERE id=?", (wid,))["client_id"] == cid


def test_unir_dois_cards_leva_a_waiver_nativa_junto(con):
    from command_center.providers import identidade
    a = inserir(con, "clients", name="Maria Santos", email="maria@example.com", pilot_name="Leo Santos", status="ACTIVE", source="manual")
    b = inserir(con, "clients", name="Maria Santos", email="maria@example.com", pilot_name="Leo Santos", status="ACTIVE", source="manual")
    wid = nativa(con, client_id=b)
    identidade.unir(con, a, b, "teste", "mesmo e-mail")
    assert um(con, "SELECT client_id FROM waivers WHERE id=?", (wid,))["client_id"] == a


def test_a_do_docusign_continua_como_era(con):
    """O espelho do DocuSign é reescrito pela sincronia; a trava é só da nativa."""
    wid = nativa(con, source=None, status="sent")
    con.execute("UPDATE waivers SET status='completed', signer_email='y@example.com', pdf_path='/p.pdf' WHERE id=?", (wid,))
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        con.execute("UPDATE waivers SET source='urace' WHERE id=?", (wid,))      # nem vira nativa por UPDATE
    con.execute("DELETE FROM waivers WHERE id=?", (wid,))


def test_a_trava_entra_a_cada_subida_e_se_atualiza(con):
    """Banco da VPS: cria se falta, troca a de texto velho, e subir de novo não mexe."""
    con.execute("DROP TRIGGER waivers_nativa_imutavel")
    con.execute("""CREATE TRIGGER waivers_nativa_imutavel BEFORE UPDATE ON waivers WHEN OLD.source IS 'urace' AND NEW.audit IS NOT OLD.audit
                   BEGIN SELECT RAISE(ABORT, 'velha'); END""")
    aplicar_schema(con)
    aplicar_schema(con)
    for nome, sql in db._travas_da_waiver().items():
        assert con.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (nome,)).fetchone()[0] == sql
    wid = nativa(con)
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        con.execute("UPDATE waivers SET doc_sha256='c' WHERE id=?", (wid,))


def test_a_anulacao_tambem_e_append_only(con):
    wid = nativa(con)
    inserir(con, "waiver_voids", waiver_id=wid, user_id=1, by_name="Gerente", reason="assinada por engano")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute("UPDATE waiver_voids SET reason='outro' WHERE waiver_id=?", (wid,))
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute("DELETE FROM waiver_voids WHERE waiver_id=?", (wid,))
    with pytest.raises(sqlite3.IntegrityError):
        inserir(con, "waiver_voids", waiver_id=wid, user_id=1, by_name="Gerente", reason="de novo, uma só")


# ------------------------------------------------------------------ assinar
def test_a_trilha_inteira_vai_para_o_audit_logs_e_o_pdf_fica_so_leitura(cli):  # noqa: F811
    wid, *_ = assinada(cli)
    con = conectar()
    w = um(con, "SELECT * FROM waivers WHERE id=?", (wid,))
    a = um(con, "SELECT * FROM audit_logs WHERE event='waiver.signed.trail' AND entity_id=?", (str(wid),))
    assert a and json.loads(a["detail"]) == json.loads(w["audit"])
    assert a["actor"].startswith("portal:") and a["ip"] == json.loads(w["audit"])["ip"]
    assert os.stat(w["pdf_path"]).st_mode & 0o777 == 0o400


def test_a_trilha_do_convite_tambem_vai_para_o_audit_logs(cli):  # noqa: F811
    from command_center.tests import test_convite_waiver as tc
    liga(cli)
    cid = tc.card(name="Bruno Adulto", email="bruno@example.com", pilot_name=None, pilot_dob="1990-02-02")
    h = equipe(cli)
    assert tc.manda(cli, h, cid, "bruno@example.com").status_code == 201
    assert tc.assina(cli, tc.token_do_email("bruno@example.com")).status_code == 201
    con = conectar()
    w = um(con, "SELECT * FROM waivers WHERE client_id=? AND source='urace'", (cid,))
    a = um(con, "SELECT * FROM audit_logs WHERE event='waiver.signed.trail' AND entity_id=?", (str(w["id"]),))
    assert json.loads(a["detail"]) == json.loads(w["audit"]) and a["actor"].startswith("invite:")


# ------------------------------------------------------------------ lixeira
def test_a_lixeira_pela_ia_nao_oculta_a_nativa_assinada(cli):  # noqa: F811
    """O furo: a ação da IA gravava hidden=1, `vigente` deixava de ver e o cliente assinava outra."""
    from command_center.api import acoes_painel
    wid, _cid, pid, _hc = assinada(cli)
    con = conectar()
    r = acoes_painel.painel_waiver_lixeira(con, None, wid, "teste")
    assert r["aplicado"] is False and "registro legal" in r["motivo"]
    assert um(con, "SELECT hidden FROM waivers WHERE id=?", (wid,))["hidden"] == 0
    assert wn.vigente(con, pid)["id"] == wid
    assert not todos(con, "SELECT 1 FROM audit_logs WHERE event='waiver.trash' AND entity_id=?", (str(wid),))


def test_a_lixeira_do_docusign_assinada_diz_que_fica_no_docusign(cli):  # noqa: F811
    from command_center.api import acoes_painel
    con = conectar()
    wid = nativa(con, source=None)
    r = acoes_painel.painel_waiver_lixeira(con, None, wid, "teste")
    assert r["aplicado"] is True and "DocuSign" in r["nota"]


# ------------------------------------------------------------------ anular
def test_o_gerente_anula_com_motivo_e_ela_deixa_de_valer_sem_mudar(cli):  # noqa: F811
    wid, cid, pid, hc = assinada(cli)
    con = conectar()
    antes = um(con, "SELECT * FROM waivers WHERE id=?", (wid,))
    con.close()
    h = equipe(cli, "ger@urace.us")
    assert cli.post(f"{API}/waivers/{wid}/void", json={"reason": "curto"}, headers=h).status_code == 400
    r = cli.post(f"{API}/waivers/{wid}/void", json={"reason": "assinada pelo responsável errado"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["voided_by"] == "Gerente" and r.json()["reason"] == "assinada pelo responsável errado"
    assert cli.post(f"{API}/waivers/{wid}/void", json={"reason": "assinada pelo responsável errado"}, headers=h).status_code == 409
    con = conectar()
    assert um(con, "SELECT * FROM waivers WHERE id=?", (wid,)) == antes, "a linha da waiver não muda"
    assert wn.vigente(con, pid) is None
    aud = um(con, "SELECT * FROM audit_logs WHERE event='waiver.void' AND entity_id=?", (str(wid),))
    assert json.loads(aud["detail"])["reason"] == "assinada pelo responsável errado" and aud["user_id"]
    from command_center.api import motor
    assert motor.waiver_do_cliente(con, cid) is None
    # no card: continua lá, marcada, com a anulação na linha do tempo; na lista, aparece como anulada
    c360 = cli.get(f"{API}/clients/{cid}").json()
    w = next(x for x in c360["waivers"] if x["id"] == wid)
    assert w["status"] == "completed" and w["voided_by"] == "Gerente" and w["void_reason"] == "assinada pelo responsável errado"
    assert any(t["kind"] == "WAIVER_VOIDED" and t["detail"] == "assinada pelo responsável errado" for t in c360["timeline"])
    assert next(x for x in cli.get(f"{API}/clients?q=Maria").json() if x["id"] == cid)["waiver_status"] == "voided"
    lista = cli.get(f"{API}/site/waiver-nativa").json()["assinadas"]["itens"]
    assert next(x for x in lista if x["id"] == wid)["void_reason"] == "assinada pelo responsável errado"
    assert next(x for x in cli.get(f"{API}/waivers").json() if x["id"] == wid)["voided_by"] == "Gerente", "a tela DocuSign também mostra"
    # o cliente vê o piloto sem waiver e pode assinar outra
    cli.cookies.clear()
    from command_center.tests.test_waiver_nativa import CONTA
    assert cli.post(f"{P}/login", json={"email": CONTA["email"], "password": CONTA["password"]}).status_code == 200
    hc = {"X-CSRF": cli.cookies.get("cp_csrf")}
    assert cli.get(f"{P}/waivers").json()["drivers"][0]["status"] == "none"
    con.execute("UPDATE portal_codes SET created_at='2000-01-01T00:00:00Z'")      # o código da 1ª assinatura foi há mais de 1 min
    con.commit()
    r = assina(cli, hc, pid)
    assert r.status_code == 201, r.text
    assert r.json()["waiver_id"] != wid


def test_so_gerente_anula_e_so_a_nativa_assinada(cli):  # noqa: F811
    wid, *_ = assinada(cli)
    con = conectar()
    auth.criar_usuario(con, "op@urace.us", "Operador", "OPERATOR", SENHA)
    docusign = nativa(con, source=None)
    con.commit(); con.close()
    h = equipe(cli, "op@urace.us")
    assert cli.post(f"{API}/waivers/{wid}/void", json={"reason": "assinada por engano no teste"}, headers=h).status_code == 403
    h = equipe(cli, "ger@urace.us")
    r = cli.post(f"{API}/waivers/{docusign}/void", json={"reason": "assinada por engano no teste"}, headers=h)
    assert r.status_code == 409 and "DocuSign" in r.json()["detail"]
    assert cli.post(f"{API}/waivers/999999/void", json={"reason": "assinada por engano no teste"}, headers=h).status_code == 404


# ------------------------------------------------------------------ backup (Biblioteca)
def test_o_backup_de_verdade_leva_a_anulada_e_a_oculta(cli):  # noqa: F811
    """Roda a Biblioteca: a anulada vai com "(anulada)" no título; a oculta (DocuSign, lixeira) vai também."""
    from command_center.providers import biblioteca
    wid, _cid, _pid, _hc = assinada(cli)
    h = equipe(cli, "ger@urace.us")
    assert cli.post(f"{API}/waivers/{wid}/void", json={"reason": "assinada pelo responsável errado"}, headers=h).status_code == 200
    con = conectar()
    pdf = os.path.join(os.path.dirname(um(con, "SELECT pdf_path FROM waivers WHERE id=?", (wid,))["pdf_path"]), "docusign.pdf")
    open(pdf, "wb").write(b"%PDF-1.4 docusign")
    oculta = nativa(con, source=None, hidden=1, pdf_path=pdf, signer_name="Pai Oculto")
    con.commit()
    r = biblioteca.sincronizar_contratos_e_waivers(con, log=lambda *_: None)
    assert r["erros"] == 0
    docs = {d["ref"]: d for d in todos(con, "SELECT * FROM library_docs WHERE kind='waiver'")}
    assert docs[str(wid)]["title"].endswith("(anulada)") and docs[str(wid)]["status"] == "anulada na área do cliente"
    assert docs[str(wid)]["sha256"] == um(con, "SELECT doc_sha256 FROM waivers WHERE id=?", (wid,))["doc_sha256"]
    assert docs[str(oculta)]["file_path"] == pdf


def test_o_backup_nao_sobe_o_pdf_da_nativa_que_mudou_no_disco(cli):  # noqa: F811
    from command_center.providers import biblioteca
    wid, *_ = assinada(cli)
    con = conectar()
    w = um(con, "SELECT * FROM waivers WHERE id=?", (wid,))
    biblioteca.sincronizar_contratos_e_waivers(con, log=lambda *_: None)
    os.chmod(w["pdf_path"], 0o600)
    open(w["pdf_path"], "ab").write(b"% adulterado")

    class Drive:
        enviados = []
        def token(self): return "t"
        def pasta(self, tok, nome, pai=None): return f"p-{nome}"
        def compartilhar(self, *a): pass
        def enviar(self, tok, nome, dados, pasta, file_id=None):
            self.enviados.append(nome); return "f1"

    r = biblioteca.sincronizar_contratos_e_waivers(con, log=lambda *_: None)
    d = um(con, "SELECT * FROM library_docs WHERE kind='waiver' AND ref=?", (str(wid),))
    assert r["erros"] == 1 and "não bate com o hash" in d["error"] and d["sha256"] == w["doc_sha256"]
    assert um(con, "SELECT 1 AS x FROM audit_logs WHERE event='biblioteca.waiver.hash_divergente' AND entity_id=?", (str(wid),))
    drive = Drive()
    biblioteca.espelhar_no_drive(con, drive=drive, log=lambda *_: None)
    assert drive.enviados == [], "o arquivo adulterado não sobrescreve a cópia do Drive"
    assert "mudou depois de conferido" in um(con, "SELECT drive_error FROM library_docs WHERE id=?", (d["id"],))["drive_error"]

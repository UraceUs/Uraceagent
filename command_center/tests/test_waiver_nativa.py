"""Waiver assinada no próprio sistema, sem DocuSign (#85).

Dono, 05/10: *"conseguimos replicar a plataforma do docusign nativa na vps?"* — por custo.
O que estes testes trancam: o texto legal é o PDF do DocuSign, byte a byte; nasce desligada;
só o responsável logado assina, pelos pilotos da própria conta; menor → parental, maior →
adult; consentimentos e assinatura de verdade são obrigatórios; o PDF final é o original +
página de assinatura, com o hash guardado; e ela entra na mesma tabela das do DocuSign."""
import base64
import hashlib
import io
import json
import os
from datetime import timedelta

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, um  # noqa: E402
from command_center.providers import portal, waiver_nativa as wn  # noqa: E402
from command_center.tests.dados_portal import piloto  # noqa: E402

P = "/ops/api/portal"
S = "/ops/api/site"
SENHA = "senha-forte-123"
CONTA = {"name": "Maria Santos", "email": "maria@example.com", "password": "corrida-segura-9",
         "birth_date": "1985-04-12", "phone": "(407) 555-0142", "address_line1": "100 Main St", "city": "Orlando",
         "state": "FL", "zip": "32809", "accept_terms": True}


def _pdf(texto):
    """Um PDF de uma página com `texto` — o papel do PDF do modelo no DocuSign."""
    from reportlab.pdfgen import canvas
    b = io.BytesIO()
    c = canvas.Canvas(b)
    c.drawString(72, 720, texto)
    c.showPage(); c.save()
    return b.getvalue()


ADULT = _pdf("ADULT RELEASE AND WAIVER OF LIABILITY - test document")
PARENTAL = _pdf("PARENTAL CONSENT, RELEASE AND WAIVER OF LIABILITY - test document")


def _assinatura(tinta=True):
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (300, 100), (255, 255, 255, 0))
    if tinta:
        d = ImageDraw.Draw(im)
        for i in range(5):
            d.line([(20, 60 + i), (280, 30 + i)], fill=(0, 0, 0, 255), width=3)
    b = io.BytesIO(); im.save(b, "PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


class DocusignFalso:
    """Só LEITURA de modelo: se algo tentar escrever no DocuSign, o teste quebra."""
    def modelo_humano(self, tid):
        return {"nome": {wn.MODELOS["adult"]: "Adult Waiver of Liability",
                         wn.MODELOS["parental"]: "Parental consent Waiver liability"}[tid],
                "documentos": [{"documentId": "1", "nome": "waiver.pdf", "paginas": "1"}]}

    def baixar_documento_do_modelo_humano(self, tid, did):
        return ADULT if tid == wn.MODELOS["adult"] else PARENTAL

    def __getattr__(self, nome):
        raise AssertionError(f"tocou no DocuSign além de ler o modelo: {nome}")


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    monkeypatch.setenv("CC_WAIVERS_DIR", str(tmp_path / "waivers"))
    monkeypatch.setenv("CC_EMAIL_FAKE", str(tmp_path / "emails.jsonl"))      # #108: nenhum e-mail sai daqui
    import command_center.providers as prov
    monkeypatch.setattr(prov, "modulo", lambda nome: DocusignFalso() if nome == "docusign" else None)
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "admin@urace.us", "Admin", "ADMIN", SENHA)
    auth.criar_usuario(c, "ger@urace.us", "Gerente", "MANAGER", SENHA)
    c.commit(); c.close()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def equipe(cli, email="admin@urace.us"):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def cliente(cli, conta=CONTA, pilotos=(("Leo Santos", "2014-05-01"),)):
    cli.cookies.clear()
    assert cli.post(f"{P}/signup", json=conta).status_code == 201
    h = {"X-CSRF": cli.cookies.get("cp_csrf")}
    ids = []
    for nome, nasc in pilotos:
        r = cli.post(f"{P}/drivers", json=piloto(nome, birth_date=nasc), headers=h)
        assert r.status_code == 201, r.text
        ids.append(next(d["id"] for d in r.json()["drivers"] if d["name"] == nome))
    return h, ids


def liga(cli):
    h = equipe(cli)
    assert cli.post(f"{S}/waiver-nativa/importar", headers=h).status_code == 200
    r = cli.post(f"{S}/waiver-nativa/ligar", json={"ligada": True}, headers=h)
    assert r.status_code == 200 and r.json()["ligada"] is True


def ultimo_codigo(email):
    """O código do último e-mail mandado para `email` (o arquivo do CC_EMAIL_FAKE)."""
    import re
    linhas = [json.loads(x) for x in open(os.environ["CC_EMAIL_FAKE"], encoding="utf-8").read().splitlines()]
    return re.search(r"\b(\d{6})\b", [x for x in linhas if x["to"] == email][-1]["text"]).group(1)


def confirma_email(cli, h):
    s = cli.get(f"{P}/waivers").json()
    if not s["email_verified"]:
        assert cli.post(f"{P}/email/verify/send", headers=h).status_code == 200
        r = cli.post(f"{P}/email/verify", json={"code": ultimo_codigo(s["email"])}, headers=h)
        assert r.status_code == 200, r.text
    return s["email"]


def assina(cli, h, pid, ler=True, codigo=True, **mais):
    """Como a tela: baixa o PDF do modelo (#107: o servidor registra a entrega), lê tudo, confirma o
    e-mail e pede o código de assinar (#108), e assina."""
    if ler:
        for k in ("adult", "parental"):
            cli.get(f"{P}/waivers/model/{k}/pdf")
    if codigo and "sign_code" not in mais:
        email = confirma_email(cli, h)
        cli.post(f"{P}/waivers/code", headers=h)          # pode ser 429 (pediu há menos de 1 min): vale o último
        mais["sign_code"] = ultimo_codigo(email)
    from datetime import datetime, timezone
    corpo = {"typed_name": "Maria Santos", "signature": _assinatura(), "read_and_agree": True, "consent_esign": True,
             "english_understood": True,
             "relationship": "mother", "guardian_declaration": True,
             "document_read_at": datetime.now(timezone.utc).isoformat(), "document_read_mode": "pdf_viewer", **mais}
    return cli.post(f"{P}/drivers/{pid}/waiver", json=corpo, headers=h)


# ------------------------------------------------------------------ ligar
def test_nasce_desligada_e_so_liga_com_os_dois_modelos(cli):
    h = equipe(cli)
    assert cli.get(f"{S}/waiver-nativa").json()["ligada"] is False
    r = cli.post(f"{S}/waiver-nativa/ligar", json={"ligada": True}, headers=h)
    assert r.status_code == 409 and "importe" in r.json()["detail"]
    hc, (pid,) = cliente(cli)
    r = assina(cli, hc, pid)
    assert r.status_code == 400 and "not available" in r.json()["detail"]


def test_importa_os_modelos_do_docusign_byte_a_byte_e_so_o_admin(cli):
    h = equipe(cli, "ger@urace.us")
    assert cli.post(f"{S}/waiver-nativa/importar", headers=h).status_code == 403, "gerente não importa"
    assert cli.post(f"{S}/waiver-nativa/ligar", json={"ligada": True}, headers=h).status_code == 403
    h = equipe(cli)
    ms = {m["kind"]: m for m in cli.post(f"{S}/waiver-nativa/importar", headers=h).json()["modelos"]}
    assert ms["adult"]["sha256"] == hashlib.sha256(ADULT).hexdigest()
    assert ms["parental"]["sha256"] == hashlib.sha256(PARENTAL).hexdigest()
    assert ms["adult"]["name"] == "Adult Waiver of Liability"


# ------------------------------------------------------------------ assinar
def test_menor_assina_a_parental_e_vira_waiver_igual_as_do_docusign(cli):
    liga(cli)
    hc, (pid,) = cliente(cli)
    s = cli.get(f"{P}/waivers").json()
    assert s["enabled"] is True and s["drivers"][0]["kind"] == "parental" and s["drivers"][0]["status"] == "none"
    assert s["drivers"][0]["own_signature_required"] is False, "pelo menor quem assina é o responsável"
    assert "PARENTAL CONSENT" in cli.get(f"{P}/waivers/model/parental").json()["text"]
    r = assina(cli, hc, pid)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["drivers"][0]["status"] == "signed"
    con = conectar()
    w = um(con, "SELECT * FROM waivers WHERE id=?", (d["waiver_id"],))
    assert w["source"] == "urace" and w["template"] == "parental" and w["status"] == "completed"
    assert w["minor_name"] == "Leo Santos" and w["signer_name"] == "Maria Santos" and w["signer_email"] == "maria@example.com"
    assert w["expires_at"] == (portal.hoje() + timedelta(days=365)).isoformat(), "vale 1 ano"
    assert um(con, "SELECT 1 AS x FROM entity_links WHERE entity_type='waiver' AND entity_id=? AND system='urace'", (w["id"],))
    # o PDF final: o original intacto + a página de assinatura, com o hash guardado
    from pypdf import PdfReader
    pdf = open(w["pdf_path"], "rb").read()
    assert hashlib.sha256(pdf).hexdigest() == w["doc_sha256"]
    paginas = PdfReader(io.BytesIO(pdf)).pages
    assert len(paginas) == 2
    assert "PARENTAL CONSENT" in paginas[0].extract_text()
    ultima = paginas[-1].extract_text()
    for trecho in ("Electronic signature and certificate", "Maria Santos", "Leo Santos", hashlib.sha256(PARENTAL).hexdigest()[:16]):
        assert trecho in ultima, trecho
    trilha = json.loads(w["audit"])
    assert trilha["consent_esign"] and trilha["read_and_agree"] and trilha["ip"] and trilha["template_sha256"]
    # #105: quem assina pelo menor diz o parentesco e declara a autoridade — na trilha e no certificado
    assert trilha["signer_relationship"] == "Mother"
    assert trilha["guardian_declaration"] == "I am the parent (natural guardian) of Leo Santos and I have the authority to sign this waiver for them."
    assert "Relationship to the minor: Mother" in ultima and "natural guardian" in ultima
    # o cliente baixa o próprio
    r = cli.get(f"{P}/waivers/{w['id']}/pdf")
    assert r.status_code == 200 and r.content == pdf


def test_maior_assina_a_adult_por_si_mesmo(cli):
    liga(cli)
    hc, _ = cliente(cli, conta={**CONTA, "i_am_driver": True}, pilotos=())
    pid = next(d["id"] for d in cli.get(f"{P}/me").json()["drivers"] if d["is_self"])
    r = assina(cli, hc, pid)
    assert r.status_code == 201, r.text
    assert um(conectar(), "SELECT template FROM waivers WHERE id=?", (r.json()["waiver_id"],))["template"] == "adult"


def test_titular_nao_assina_a_adult_de_outro_adulto(cli):
    """#104: um adulto só renuncia aos próprios direitos (Sanislo, Fla. 2015). O titular da conta
    não assina a waiver adult de um piloto adulto que não é ele: o servidor recusa e a tela explica."""
    liga(cli)
    hc, (pid,) = cliente(cli, pilotos=(("Pedro Santos", "1990-02-02"),))
    s = cli.get(f"{P}/waivers").json()["drivers"][0]
    assert s["kind"] == "adult" and s["own_signature_required"] is True
    r = assina(cli, hc, pid)
    assert r.status_code == 400 and "must sign their own waiver" in r.json()["detail"], r.text
    assert not um(conectar(), "SELECT 1 AS x FROM waivers WHERE source='urace'")


@pytest.mark.parametrize("mais,trecho", [
    ({"read_and_agree": False}, "Check both boxes"),
    ({"consent_esign": False}, "Check both boxes"),
    ({"signature": _assinatura(tinta=False)}, "Draw your signature"),
    ({"signature": "data:image/png;base64,AAAA"}, "Draw your signature"),
    ({"typed_name": "Maria"}, "full name"),
])
def test_sem_consentimento_ou_sem_assinatura_nao_assina(cli, mais, trecho):
    liga(cli)
    hc, (pid,) = cliente(cli)
    r = assina(cli, hc, pid, **mais)
    assert r.status_code == 400 and trecho in r.json()["detail"], r.text
    assert not um(conectar(), "SELECT 1 AS x FROM waivers WHERE source='urace'")


@pytest.mark.parametrize("mais,trecho", [
    ({"relationship": None}, "only a parent can sign"),
    ({"relationship": "other"}, "Only a parent (mother or father)"),
    ({"relationship": "legal_guardian"}, "in person at the track"),
    ({"relationship": "grandmother"}, "only a parent can sign"),
    ({"guardian_declaration": False}, "have the authority to sign"),
])
def test_pelo_menor_so_pai_ou_mae_com_a_declaracao(cli, mais, trecho):
    """#105: Fla. Stat. §744.301(3) só deixa o natural guardian renunciar pelo menor (Kirton v. Fields, 2008)."""
    liga(cli)
    hc, (pid,) = cliente(cli)
    assert "natural guardian" in cli.get(f"{P}/waivers/model/parental").json()["declaration"]
    r = assina(cli, hc, pid, **mais)
    assert r.status_code == 400 and trecho in r.json()["detail"], r.text
    assert not um(conectar(), "SELECT 1 AS x FROM waivers WHERE source='urace'")


def test_nao_assina_pelo_piloto_de_outra_conta_nem_duas_vezes(cli):
    liga(cli)
    _, (pid_outro,) = cliente(cli, conta={**CONTA, "email": "outra@example.com"})
    hc, (pid,) = cliente(cli)
    assert assina(cli, hc, pid_outro).status_code == 404
    assert assina(cli, hc, pid).status_code == 201
    r = assina(cli, hc, pid)
    assert r.status_code == 400 and "still valid" in r.json()["detail"]


def test_o_cliente_so_baixa_a_propria(cli):
    liga(cli)
    hc, (pid,) = cliente(cli)
    wid = assina(cli, hc, pid).json()["waiver_id"]
    cliente(cli, conta={**CONTA, "email": "outra@example.com"})
    assert cli.get(f"{P}/waivers/{wid}/pdf").status_code == 404


def test_a_equipe_baixa_pelo_card_e_o_modelo_alterado_nao_assina(cli):
    liga(cli)
    hc, (pid,) = cliente(cli)
    wid = assina(cli, hc, pid).json()["waiver_id"]
    equipe(cli, "ger@urace.us")
    r = cli.get(f"/ops/api/waivers/{wid}/download")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    # alguém trocou o PDF do modelo no disco: o hash não bate e ninguém assina sobre ele
    m = um(conectar(), "SELECT pdf_path FROM waiver_templates WHERE kind='parental'")
    open(m["pdf_path"], "wb").write(_pdf("TEXTO TROCADO"))
    hc2, (pid2,) = cliente(cli, conta={**CONTA, "email": "nova@example.com"})
    r = assina(cli, hc2, pid2)
    assert r.status_code == 400 and "could not be verified" in r.json()["detail"]


def test_a_lista_das_assinadas_e_paginada(cli):
    liga(cli)
    for i in range(3):
        hc, (pid,) = cliente(cli, conta={**CONTA, "email": f"conta{i}@example.com"})
        assert assina(cli, hc, pid).status_code == 201
    equipe(cli, "ger@urace.us")
    r = cli.get(f"{S}/waiver-nativa?limit=2&offset=0").json()["assinadas"]
    assert r["total"] == 3 and len(r["itens"]) == 2 and r["itens"][0]["minor_name"] == "Leo Santos"
    assert len(cli.get(f"{S}/waiver-nativa?limit=2&offset=2").json()["assinadas"]["itens"]) == 1


# ------------------------------------------------------------------ #106: a parental vence na véspera dos 18
def _faz_18_daqui(dias):
    """A data de nascimento de quem faz 18 daqui a `dias` dias (no fuso da Flórida)."""
    d18 = portal.hoje() + timedelta(days=dias)
    return d18.replace(year=d18.year - 18, day=min(d18.day, 28) if d18.month == 2 else d18.day).isoformat()


def test_parental_vence_na_vespera_dos_18_e_nao_em_um_ano(cli):
    liga(cli)
    hc, (pid,) = cliente(cli, pilotos=(("Teen Santos", _faz_18_daqui(90)),))
    r = assina(cli, hc, pid)
    assert r.status_code == 201, r.text
    w = um(conectar(), "SELECT * FROM waivers WHERE id=?", (r.json()["waiver_id"],))
    assert w["expires_at"] == (portal.hoje() + timedelta(days=89)).isoformat(), "véspera dos 18, não 1 ano"
    assert json.loads(w["audit"])["valid_until_reason"] == "the day before the minor turns 18"
    from pypdf import PdfReader
    assert "the day before the minor turns 18" in " ".join(PdfReader(w["pdf_path"]).pages[-1].extract_text().split())


def test_menor_longe_dos_18_continua_com_um_ano(cli):
    liga(cli)
    hc, (pid,) = cliente(cli)
    w = um(conectar(), "SELECT * FROM waivers WHERE id=?", (assina(cli, hc, pid).json()["waiver_id"],))
    assert w["expires_at"] == (portal.hoje() + timedelta(days=365)).isoformat()
    assert json.loads(w["audit"])["valid_until_reason"] == "one year"


def test_avisa_quem_faz_18_nos_proximos_30_dias(cli):
    liga(cli)
    # dono, 06/10: o aviso vem 7 dias antes (era 30)
    cliente(cli, pilotos=(("Perto Santos", _faz_18_daqui(5)), ("Longe Santos", _faz_18_daqui(20))))
    s = {d["driver"]: d for d in cli.get(f"{P}/waivers").json()["drivers"]}
    assert s["Perto Santos"]["turns_18_on"] == (portal.hoje() + timedelta(days=5)).isoformat()
    assert s["Longe Santos"]["turns_18_on"] is None


def test_parental_antiga_deixa_de_valer_quando_o_piloto_faz_18(cli, monkeypatch):
    """Uma parental gravada com validade além dos 18 (antes desta regra) não vale mais depois do aniversário:
    o piloto passa a precisar da adult, assinada por ele."""
    liga(cli)
    hc, (pid,) = cliente(cli, pilotos=(("Teen Santos", _faz_18_daqui(100)),))
    wid = assina(cli, hc, pid).json()["waiver_id"]
    con = conectar()
    con.execute("UPDATE waivers SET expires_at=? WHERE id=?", ((portal.hoje() + timedelta(days=365)).isoformat(), wid))
    con.commit()
    depois = portal.hoje() + timedelta(days=101)
    monkeypatch.setattr(portal, "hoje", lambda: depois)
    d = cli.get(f"{P}/waivers").json()["drivers"][0]
    assert d["kind"] == "adult" and d["status"] == "none"


def test_quem_nasceu_em_29_de_fevereiro_faz_18_em_1_de_marco_como_na_idade():
    from datetime import date
    assert wn.dia_dos_18(date(2008, 2, 29)) == date(2026, 3, 1)
    assert portal.idade(date(2008, 2, 29), date(2026, 2, 28)) == 17 and portal.idade(date(2008, 2, 29), date(2026, 3, 1)) == 18
    assert wn.validade("parental", date(2008, 2, 29), date(2025, 6, 1)) == date(2026, 2, 28)
    assert wn.validade("adult", date(1990, 1, 1), date(2025, 6, 1)) == date(2026, 6, 1)


# ------------------------------------------------------------------ #107: o documento inteiro passa pela tela
def test_sem_abrir_o_pdf_nao_assina(cli):
    liga(cli)
    hc, (pid,) = cliente(cli)
    r = assina(cli, hc, pid, ler=False)
    assert r.status_code == 400 and "Open and read the whole document" in r.json()["detail"], r.text
    assert not um(conectar(), "SELECT 1 AS x FROM waivers WHERE source='urace'")


@pytest.mark.parametrize("mais", [
    {"document_read_at": None},
    {"document_read_at": "ontem"},
    {"document_read_at": "2026-10-06T10:00:00"},                      # sem fuso: não dá para saber quando foi
    {"document_read_at": "2001-01-01T00:00:00Z"},                     # velha demais
    {"document_read_mode": "pulei"},
])
def test_sem_a_leitura_completa_nao_assina(cli, mais):
    liga(cli)
    hc, (pid,) = cliente(cli)
    r = assina(cli, hc, pid, **mais)
    assert r.status_code == 400 and "Read the whole document" in r.json()["detail"], r.text


def test_a_leitura_fica_na_trilha_e_no_certificado(cli):
    liga(cli)
    hc, (pid,) = cliente(cli)
    w = um(conectar(), "SELECT * FROM waivers WHERE id=?", (assina(cli, hc, pid).json()["waiver_id"],))
    t = json.loads(w["audit"])
    assert t["document_delivered_at"] and t["document_all_pages_viewed_at"] and t["reading_mode"] == "pdf_viewer"
    assert t["reading_requirement"] == "every page of the PDF shown on screen before the boxes unlock"
    ev = um(conectar(), "SELECT detail FROM audit_logs WHERE event='portal.waiver.document_view' ORDER BY id DESC LIMIT 1")
    assert json.loads(ev["detail"])["kind"] in ("adult", "parental")
    from pypdf import PdfReader
    texto = " ".join(PdfReader(w["pdf_path"]).pages[-1].extract_text().split())
    assert "Document delivered to the signer" in texto and "Whole document read" in texto


# ------------------------------------------------------------------ #108: e-mail confirmado e código na hora
def test_sem_email_confirmado_nao_assina(cli):
    liga(cli)
    hc, (pid,) = cliente(cli)
    r = assina(cli, hc, pid, codigo=False)
    assert r.status_code == 400 and "Confirm your email" in r.json()["detail"], r.text
    assert cli.post(f"{P}/waivers/code", headers=hc).status_code == 400, "sem e-mail confirmado não manda código"


def test_codigo_errado_vencido_ou_repetido_nao_assina(cli, monkeypatch):
    from command_center.providers import codigos
    liga(cli)
    hc, (pid,) = cliente(cli)
    email = confirma_email(cli, hc)
    assert cli.post(f"{P}/waivers/code", headers=hc).json()["sent_to"] == "m••••@example.com"
    certo = ultimo_codigo(email)
    errado = "000000" if certo != "000000" else "111111"
    r = assina(cli, hc, pid, sign_code=errado)
    assert r.status_code == 400 and "not right" in r.json()["detail"]
    for _ in range(4):
        assina(cli, hc, pid, sign_code=errado)
    r = assina(cli, hc, pid, sign_code=certo)
    assert r.status_code == 400 and "Too many wrong tries" in r.json()["detail"], "5 erros queimam o código"
    # pedir de novo em menos de 1 minuto: não manda
    assert cli.post(f"{P}/waivers/code", headers=hc).status_code == 429
    # depois do minuto, um código novo; vencido (15 min) não vale
    real = codigos._agora
    monkeypatch.setattr(codigos, "_agora", lambda: real() + timedelta(minutes=2))
    assert cli.post(f"{P}/waivers/code", headers=hc).status_code == 200
    novo = ultimo_codigo(email)
    monkeypatch.setattr(codigos, "_agora", lambda: real() + timedelta(minutes=20))
    r = assina(cli, hc, pid, sign_code=novo)
    assert r.status_code == 400 and "expired" in r.json()["detail"]
    assert not um(conectar(), "SELECT 1 AS x FROM waivers WHERE source='urace'")


def test_codigo_vale_uma_vez_e_nunca_fica_guardado(cli):
    liga(cli)
    hc, (pid,) = cliente(cli)
    r = assina(cli, hc, pid)
    assert r.status_code == 201, r.text
    con = conectar()
    linhas = [dict(x) for x in con.execute("SELECT * FROM portal_codes").fetchall()]
    codigos_mandados = [ultimo_codigo("maria@example.com")]
    assert all(c not in json.dumps(linhas) for c in codigos_mandados), "o código não fica guardado, só o hash"
    assert all(x["used_at"] for x in linhas), "cada código vale uma vez"
    w = um(con, "SELECT * FROM waivers WHERE id=?", (r.json()["waiver_id"],))
    t = json.loads(w["audit"])
    assert t["email_verified_at"] and t["otp_sent_at"] and t["otp_verified_at"] and t["otp_sent_to"] == "maria@example.com"
    assert t["session_login_at"] and "one-time code sent to maria@example.com" in t["authentication"]
    from pypdf import PdfReader
    texto = " ".join(PdfReader(w["pdf_path"]).pages[-1].extract_text().split())
    assert "one-time code sent to maria@example.com" in texto


def test_o_email_sai_da_caixa_certa_e_o_falso_nao_sai_da_maquina(tmp_path, monkeypatch):
    from command_center.providers import email_envio
    monkeypatch.setenv("CC_EMAIL_FAKE", str(tmp_path / "e.jsonl"))
    monkeypatch.delenv("CC_EMAIL_REMETENTE", raising=False)
    email_envio.enviar("a@example.com", "Assunto", "Texto")
    monkeypatch.setenv("CC_EMAIL_REMETENTE", "support")
    email_envio.enviar("a@example.com", "Assunto", "Texto")
    monkeypatch.setenv("CC_EMAIL_REMETENTE", "urace")
    email_envio.enviar("a@example.com", "Assunto", "Texto")
    monkeypatch.setenv("CC_EMAIL_REMETENTE", "qualquer")
    email_envio.enviar("a@example.com", "Assunto", "Texto")
    de = [json.loads(x)["from"] for x in open(tmp_path / "e.jsonl").read().splitlines()]
    assert de == ["noreply@urace.us", "support@urace.us", "urace@urace.us", "noreply@urace.us"], "padrão: noreply@ (dono, 06/10)"


# ------------------------------------------------------------------ decisões do dono, 06/10
def test_sem_a_caixa_de_ingles_nao_assina_e_com_ela_vai_para_a_trilha(cli):
    """#119: sem tradução por enquanto; quem assina confirma que lê inglês (ou mandou traduzir)."""
    liga(cli)
    hc, (pid,) = cliente(cli)
    r = assina(cli, hc, pid, english_understood=False)
    assert r.status_code == 400 and "understand English" in r.json()["detail"], r.text
    w = um(conectar(), "SELECT * FROM waivers WHERE id=?", (assina(cli, hc, pid).json()["waiver_id"],))
    t = json.loads(w["audit"])
    assert t["language_ack"] == wn.IDIOMA and "Orange County" in t["governing_law"]
    from pypdf import PdfReader
    assert "I read and understand English" in " ".join(PdfReader(w["pdf_path"]).pages[-1].extract_text().split())


def test_waiver_assinada_no_sistema_nao_vai_para_a_lixeira(cli):
    """#118 (dono: nunca apagar): a assinada aqui é o registro legal — não há cópia no DocuSign."""
    liga(cli)
    hc, (pid,) = cliente(cli)
    wid = assina(cli, hc, pid).json()["waiver_id"]
    h = equipe(cli)
    r = cli.post(f"/ops/api/waivers/{wid}/trash", headers=h, json={"reason": "teste"})
    assert r.status_code == 409 and "registro legal" in r.json()["detail"]
    assert um(conectar(), "SELECT hidden FROM waivers WHERE id=?", (wid,))["hidden"] == 0


def test_o_backup_da_biblioteca_leva_tambem_a_waiver_oculta():
    """#118: ocultar no painel não tira do backup."""
    import inspect
    from command_center.providers import biblioteca
    fonte = inspect.getsource(biblioteca)
    assert "WHERE status='completed'\")" in fonte and "status='completed' AND COALESCE(hidden,0)=0" not in fonte

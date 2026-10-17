"""Convite da waiver por e-mail (#135).

Dono, 14/10: *"vai ser por e-mail para o adulto ou para o responsável assinar aquela waiver. Tanto
para adulto quanto para responsável, o e-mail que tiver no card vai receber isso."*

O que estes testes trancam: o convite vai para o e-mail do card; piloto com 18+ assina a própria
(adult), menor é o responsável (parental, pai ou mãe); o link é de uso único, vence, é assinado e
preso a um card (token inventado, adulterado, usado, trocado, vencido ou de card que mudou é
recusado; nenhum campo da tela escolhe o card); a assinatura vira waiver do card como as outras;
cada passo vai para a auditoria; sem e-mail o envio não sai; pela IA, só com aprovação."""
import json
import os
import re
from datetime import datetime, timedelta, timezone

from command_center.db import conectar, inserir, todos, um
from command_center.providers import convite_waiver as cw
from command_center.tests.test_waiver_nativa import P, _assinatura, cli, equipe, liga, revisa_e_assina  # noqa: F401 (fixture)

API = "/ops/api"


def card(**campos):
    con = conectar()
    try:
        base = {"name": "Maria Santos", "email": "maria@example.com", "pilot_name": "Leo Santos", "pilot_dob": "2014-05-01",
                "status": "ACTIVE", "source": "manual"}
        return inserir(con, "clients", **{**base, **campos})
    finally:
        con.close()


def emails():
    arq = os.environ["CC_EMAIL_FAKE"]
    return [json.loads(x) for x in open(arq, encoding="utf-8").read().splitlines()] if os.path.exists(arq) else []


def token_do_email(para):
    ult = [e for e in emails() if e["to"] == para and "/ops/portal/invite/" in e["text"]][-1]
    return re.search(r"/ops/portal/invite/([A-Za-z0-9_.-]+)", ult["text"]).group(1)


def codigo_do_email(para):
    ult = [e for e in emails() if e["to"] == para and "code" in e["subject"].lower()][-1]
    return re.search(r"\b(\d{6})\b", ult["text"]).group(1)


def manda(cli, h, cid, email):  # noqa: F811
    return cli.post(f"{API}/clients/{cid}/waiver-invite", json={"email": email}, headers=h)


def assina(cli, token, codigo=True, **mais):  # noqa: F811
    """Como a tela do convite: abre, baixa o PDF (a entrega fica registrada), pede o código e assina."""
    cli.cookies.clear()                                  # o cliente não tem conta nem sessão
    assert cli.get(f"{P}/invite/{token}").status_code == 200
    assert cli.get(f"{P}/invite/{token}/pdf").status_code == 200
    if codigo and "sign_code" not in mais:
        assert cli.post(f"{P}/invite/{token}/code").status_code in (200, 429)   # 429: pediu há menos de 1 min, vale o último
        inv = cw.achar(conectar(), token)
        mais["sign_code"] = codigo_do_email(inv["email"])
    corpo = {"typed_name": "Leo Santos Junior", "signature": _assinatura(), "read_and_agree": True, "consent_esign": True,
             "english_understood": True, "document_read_at": datetime.now(timezone.utc).isoformat(),
             "document_read_mode": "pdf_viewer", **mais}
    return revisa_e_assina(cli, f"{P}/invite/{token}/sign", f"{P}/invite/{token}/review", corpo)


def eventos(cid):
    return [a["event"] for a in todos(conectar(), "SELECT event FROM audit_logs WHERE entity_type='client' AND entity_id=? ORDER BY id",
                                      (str(cid),))]


# ------------------------------------------------------------------ adulto × menor
def test_adulto_recebe_no_email_do_card_e_assina_a_propria_sem_conta(cli):  # noqa: F811
    liga(cli)
    cid = card(name="Bruno Adulto", email="Bruno@Example.com", pilot_name=None, pilot_dob="1990-02-02")
    h = equipe(cli)
    d = cli.get(f"{API}/clients/{cid}/waiver-invite").json()["destino"]
    assert d["can_send"] and d["kind"] == "adult" and d["signer_name"] == "Bruno Adulto" and d["email"] == "bruno@example.com"
    r = manda(cli, h, cid, "bruno@example.com")
    assert r.status_code == 201, r.text
    assert r.json()["convite"]["status"] == "sent" and r.json()["convite"]["created_by_name"] == "Admin"
    e = [x for x in emails() if x["to"] == "bruno@example.com"][-1]
    assert e["subject"] == "Sign your URACE waiver" and e["from"] == "noreply@urace.us"
    assert "Only you can sign it" in e["text"] and "expires in 72 hours" in e["text"]
    assert "https://my.urace.us/ops/portal/invite/" in e["text"]
    token = token_do_email("bruno@example.com")
    v = cli.get(f"{P}/invite/{token}").json()
    assert v["kind"] == "adult" and v["signer_name"] == "Bruno Adulto" and v["email"] == "b••••@example.com"
    assert v["model"]["declaration"] is None and "ADULT RELEASE" in v["model"]["text"]
    r = assina(cli, token)
    assert r.status_code == 201, r.text
    con = conectar()
    w = um(con, "SELECT * FROM waivers WHERE client_id=? AND source='urace'", (cid,))
    assert w and w["template"] == "adult" and w["status"] == "completed" and w["signer_email"] == "bruno@example.com"
    assert w["signer_name"] == "Bruno Adulto" and w["minor_name"] is None and w["link_by"] == "human"
    trilha = json.loads(w["audit"])
    assert trilha["invitation_sent_to"] == "bruno@example.com" and trilha["otp_verified_at"]
    assert "invitation link emailed by URACE to bruno@example.com" in trilha["authentication"]
    assert "one-time code sent to bruno@example.com" in trilha["authentication"]
    # a waiver aparece no card como as outras
    equipe(cli)
    c360 = cli.get(f"{API}/clients/{cid}").json()
    assert [x["id"] for x in c360["waivers"]] == [w["id"]]
    assert cli.get(f"{API}/clients/{cid}/waiver-invite").json()["convites"][0]["status"] == "signed"
    # a cópia de quem assinou, pelo mesmo link
    pdf = cli.get(f"{P}/invite/{token}/signed.pdf")
    assert pdf.status_code == 200 and pdf.content == open(w["pdf_path"], "rb").read()
    from command_center.tests.test_waiver_nativa import certificado
    assert "Email: bruno@example.com" in certificado(w["pdf_path"])


def test_menor_o_convite_vai_para_o_responsavel_que_assina_como_pai_ou_mae(cli):  # noqa: F811
    liga(cli)
    cid = card()
    h = equipe(cli)
    d = cli.get(f"{API}/clients/{cid}/waiver-invite").json()["destino"]
    assert d["kind"] == "parental" and d["signer_name"] == "Maria Santos" and d["driver_name"] == "Leo Santos"
    assert manda(cli, h, cid, "maria@example.com").status_code == 201
    e = [x for x in emails() if x["to"] == "maria@example.com"][-1]
    assert e["subject"] == "Sign the URACE waiver for Leo Santos" and "Hi Maria" in e["text"]
    token = token_do_email("maria@example.com")
    assert cli.get(f"{P}/invite/{token}").json()["model"]["declaration"]
    r = assina(cli, token, typed_name="Maria Santos")
    assert r.status_code == 400 and "relationship" in r.json()["detail"], "pelo menor, o parentesco é obrigatório"
    r = assina(cli, token, typed_name="Maria Santos", relationship="other", guardian_declaration=True,
               sign_code=codigo_do_email("maria@example.com"))
    assert r.status_code == 400 and "Only a parent" in r.json()["detail"]
    r = assina(cli, token, typed_name="Maria Santos", relationship="mother", guardian_declaration=True)
    assert r.status_code == 201, r.text
    w = um(conectar(), "SELECT * FROM waivers WHERE client_id=? AND source='urace'", (cid,))
    assert w["template"] == "parental" and w["minor_name"] == "Leo Santos" and w["signer_name"] == "Maria Santos"
    trilha = json.loads(w["audit"])
    assert trilha["signer_relationship"] == "Mother" and "natural guardian" in trilha["guardian_declaration"]


# ------------------------------------------------------------------ o link
def test_link_inventado_adulterado_usado_trocado_e_vencido_sao_recusados(cli, monkeypatch):  # noqa: F811
    liga(cli)
    cid = card(name="Ana Adulta", email="ana@example.com", pilot_name=None, pilot_dob="1988-01-01")
    h = equipe(cli)
    assert manda(cli, h, cid, "ana@example.com").status_code == 201
    primeiro = token_do_email("ana@example.com")
    cli.cookies.clear()
    assert cli.get(f"{P}/invite/inventado.qualquer").status_code == 404
    segredo, selo = primeiro.split(".")
    assert cli.get(f"{P}/invite/{segredo}.{'A' * len(selo)}").status_code == 404, "selo adulterado"
    assert cli.get(f"{P}/invite/{segredo}").status_code == 404, "sem o selo"
    # reenviar: o link anterior fica substituído
    con = conectar()
    con.execute("UPDATE waiver_invites SET created_at='2000-01-01T00:00:00.000Z'")      # passa o minuto entre envios
    h = equipe(cli)
    assert manda(cli, h, cid, "ana@example.com").status_code == 201
    segundo = token_do_email("ana@example.com")
    assert segundo != primeiro
    cli.cookies.clear()
    r = cli.get(f"{P}/invite/{primeiro}")
    assert r.status_code == 410 and "replaced" in r.json()["detail"]
    # vencido: 72 h depois
    real = cw._agora
    monkeypatch.setattr(cw, "_agora", lambda: real() + timedelta(hours=cw.VALIDADE_HORAS, minutes=1))
    r = cli.get(f"{P}/invite/{segundo}")
    assert r.status_code == 410 and "expired" in r.json()["detail"]
    monkeypatch.setattr(cw, "_agora", real)
    # usado: uma vez só
    assert assina(cli, segundo).status_code == 201
    r = cli.get(f"{P}/invite/{segundo}")
    assert r.status_code == 410 and "already used" in r.json()["detail"]
    r = cli.post(f"{P}/invite/{segundo}/sign", json={"typed_name": "Ana Adulta", "signature": _assinatura()})
    assert r.status_code == 410
    assert um(conectar(), "SELECT COUNT(*) AS n FROM waivers WHERE client_id=?", (cid,))["n"] == 1
    # estados no painel e auditoria das recusas (o link nunca vai para o log)
    equipe(cli)
    st = [c["status"] for c in cli.get(f"{API}/clients/{cid}/waiver-invite").json()["convites"]]
    assert st == ["signed", "replaced"]
    ev = eventos(cid)
    assert ev.count("waiver.invite.sent") == 2 and "waiver.invite.refused" in ev and "waiver.invite.signed" in ev
    assert ev.index("waiver.invite.opened") < ev.index("waiver.invite.code_sent") < ev.index("waiver.invite.signed")
    tudo = json.dumps(todos(conectar(), "SELECT * FROM audit_logs"))
    assert segredo not in tudo and segundo.split(".")[0] not in tudo


def test_codigo_errado_ou_sem_ler_o_documento_nao_assina(cli):  # noqa: F811
    liga(cli)
    cid = card(name="Rui Adulto", email="rui@example.com", pilot_name=None, pilot_dob="1980-03-03")
    assert manda(cli, equipe(cli), cid, "rui@example.com").status_code == 201
    token = token_do_email("rui@example.com")
    cli.cookies.clear()
    cli.get(f"{P}/invite/{token}")
    r = cli.post(f"{P}/invite/{token}/sign", json={"typed_name": "Rui Adulto", "signature": _assinatura(), "read_and_agree": True,
                                                   "consent_esign": True, "english_understood": True,
                                                   "document_read_at": datetime.now(timezone.utc).isoformat()})
    assert r.status_code == 400 and "Open and read the whole document" in r.json()["detail"]
    r = assina(cli, token, sign_code="000000")
    assert r.status_code == 400 and ("Ask for the signing code" in r.json()["detail"])
    cli.post(f"{P}/invite/{token}/code")
    r = cli.post(f"{P}/invite/{token}/code")
    assert r.status_code == 429, "um código por minuto"
    errado = "111111" if codigo_do_email("rui@example.com") != "111111" else "222222"
    r = assina(cli, token, codigo=False, sign_code=errado)
    assert r.status_code == 400 and "not right" in r.json()["detail"]
    assert um(conectar(), "SELECT used_at FROM waiver_invites")["used_at"] is None, "erro não gasta o link"


# ------------------------------------------------------------------ card errado
def test_nunca_assina_por_outro_card(cli):  # noqa: F811
    liga(cli)
    a = card(name="Lia Adulta", email="lia@example.com", pilot_name=None, pilot_dob="1991-01-01")
    b = card(name="Outro Cliente", email="outro@example.com", pilot_name=None, pilot_dob="1992-02-02")
    h = equipe(cli)
    assert manda(cli, h, a, "lia@example.com").status_code == 201
    token = token_do_email("lia@example.com")
    # a tela não escolhe card nem piloto: campo a mais é recusado
    cli.cookies.clear()
    r = cli.post(f"{P}/invite/{token}/sign", json={"typed_name": "Lia Adulta", "signature": _assinatura(), "client_id": b})
    assert r.status_code == 422
    # o convite levado a outro card (banco mexido) perde o selo
    con = conectar()
    con.execute("UPDATE waiver_invites SET client_id=? WHERE client_id=?", (b, a))
    assert cli.get(f"{P}/invite/{token}").status_code == 404
    con.execute("UPDATE waiver_invites SET client_id=? WHERE client_id=?", (a, b))
    assert cli.get(f"{P}/invite/{token}").status_code == 200
    # o card mudou de e-mail depois do envio: o link para de valer
    con.execute("UPDATE clients SET email='novo@example.com' WHERE id=?", (a,))
    r = cli.get(f"{P}/invite/{token}")
    assert r.status_code == 410 and "details on file changed" in r.json()["detail"]
    assert um(con, "SELECT COUNT(*) AS n FROM waivers")["n"] == 0
    # e assinado pelo link certo, a waiver só entra no card do convite
    con.execute("UPDATE clients SET email='lia@example.com' WHERE id=?", (a,))
    assert assina(cli, token).status_code == 201
    assert [w["client_id"] for w in todos(con, "SELECT client_id FROM waivers")] == [a]


def test_confirmacao_com_email_diferente_do_card_nao_manda(cli):  # noqa: F811
    liga(cli)
    cid = card()
    r = manda(cli, equipe(cli), cid, "outra@example.com")
    assert r.status_code == 409 and "mudou" in r.json()["detail"]
    assert not emails()


def test_unir_cards_leva_o_convite_e_o_link_morre(cli):  # noqa: F811
    from command_center.providers import identidade
    liga(cli)
    a = card(name="Teo Adulto", email="teo@example.com", pilot_name=None, pilot_dob="1990-01-01")
    b = card(name="Teo Adulto", email="teo@example.com", pilot_name=None, pilot_dob="1990-01-01")
    assert manda(cli, equipe(cli), b, "teo@example.com").status_code == 201
    token = token_do_email("teo@example.com")
    con = conectar()
    assert identidade.unir(con, a, b, "teste", "mesmo e-mail")
    assert um(con, "SELECT client_id FROM waiver_invites")["client_id"] == a, "o histórico vai junto"
    cli.cookies.clear()
    assert cli.get(f"{P}/invite/{token}").status_code == 404


# ------------------------------------------------------------------ sem e-mail, sem nascimento, desligada
def test_sem_email_ou_sem_nascimento_o_convite_nao_sai_e_explica(cli):  # noqa: F811
    h = equipe(cli)
    cid = card(email=None)
    d = cli.get(f"{API}/clients/{cid}/waiver-invite").json()["destino"]
    assert d["can_send"] is False and "desligada" in d["reason"], "assinatura nativa desligada vem primeiro"
    liga(cli)
    h = equipe(cli)
    d = cli.get(f"{API}/clients/{cid}/waiver-invite").json()["destino"]
    assert d["can_send"] is False and "não tem e-mail" in d["reason"]
    r = manda(cli, h, cid, "")
    assert r.status_code == 409 and "não tem e-mail" in r.json()["detail"]
    sem_nasc = card(pilot_dob=None)
    assert "data de nascimento" in cli.get(f"{API}/clients/{sem_nasc}/waiver-invite").json()["destino"]["reason"]
    menor_sem_resp = card(name="Leo Santos", pilot_name=None)
    assert "responsável" in cli.get(f"{API}/clients/{menor_sem_resp}/waiver-invite").json()["destino"]["reason"]
    da_urace = card(email="vendas@urace.us")
    assert "da URACE" in cli.get(f"{API}/clients/{da_urace}/waiver-invite").json()["destino"]["reason"]
    assert not emails()
    assert cli.get(f"{API}/clients/999999/waiver-invite").status_code == 404


def test_so_operador_manda_e_dois_cliques_seguidos_mandam_um(cli):  # noqa: F811
    from command_center.api import auth
    liga(cli)
    con = conectar()
    auth.criar_usuario(con, "leitor@urace.us", "Leitor", "VIEWER", "senha-forte-123")
    cid = card()
    h = equipe(cli, "leitor@urace.us")
    assert manda(cli, h, cid, "maria@example.com").status_code == 403
    h = equipe(cli)
    assert manda(cli, h, cid, "maria@example.com").status_code == 201
    r = manda(cli, h, cid, "maria@example.com")
    assert r.status_code == 429
    assert len([e for e in emails() if e["to"] == "maria@example.com"]) == 1


def test_email_que_nao_sai_nao_deixa_convite_valendo(cli, monkeypatch):  # noqa: F811
    from command_center.providers import email_envio
    liga(cli)
    cid = card()

    def falha(*a):
        raise email_envio.ErroEnvio("sem token")
    monkeypatch.setattr(email_envio, "enviar", falha)
    r = manda(cli, equipe(cli), cid, "maria@example.com")
    assert r.status_code == 503
    assert [c["status"] for c in cw.listar(conectar(), cid)] == ["failed"]
    assert "waiver.invite.send_failed" in eventos(cid)


# ------------------------------------------------------------------ IA: só com aprovação
def test_pela_ia_o_convite_espera_aprovacao(cli):  # noqa: F811
    from command_center.api import acoes_painel, ia
    liga(cli)
    cid = card()
    con = conectar()
    assert ia._politica(con, "painel_waiver_convite") == "REQUIRES_APPROVAL"
    assert "painel_waiver_convite" in {a["name"] for a in acoes_painel.descrever_todas()}
    # o que roda depois do aprovar (motor.executar_acao → acoes_painel)
    r = acoes_painel.executar(con, 1, "painel_waiver_convite", {"client_id": cid})
    assert r["aplicado"] and r["para"] == "maria@example.com" and r["modelo"] == "parental"
    inv = um(con, "SELECT created_by, user_id FROM waiver_invites WHERE client_id=?", (cid,))
    assert inv["created_by"] == "ia" and inv["user_id"] == 1
    sem = card(email=None)
    assert acoes_painel.executar(con, 1, "painel_waiver_convite", {"client_id": sem})["aplicado"] is False


def test_o_link_nao_vai_para_as_metricas_do_navegador():
    from command_center.api import observabilidade
    t = "a" * 43 + "." + "B" * 32
    assert observabilidade._rota_do_cliente(f"/ops/portal/invite/{t}") == "/ops/portal/invite/:token"
    assert observabilidade._rota_do_cliente("/ops/clients/12") == "/ops/clients/:id"

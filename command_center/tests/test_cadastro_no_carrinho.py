"""#305: os dados do comprador no próprio carrinho viram a conta no checkout, com as boas-vindas por e-mail.

Dono, 16/10: *"ao invés de ter o botão de seguir e create account … ela vai ter que preencher as informações dela …
Quando for para o checkout, já cria a conta dela … toda vez que criar a conta, a pessoa recebe o um e-mail com a
nossa identidade … o login dela, a senha … o cliente ID dela, link para ela poder acessar a área dela"*. Decisões dele:
a senha vai no e-mail; o cliente ID é o número do card; o piloto entra só com o nome e completa depois, "com lembretes
pelo email ate completar as informações".

O que estes testes trancam: sem conta, o checkout cria a conta (e o piloto) com o que a pessoa preencheu, já sai
logado e manda as boas-vindas com login, senha e o link; a senha nunca fica no banco; erro (senha, e-mail que já tem
conta, limite, carrinho com problema) não cria conta nem chama o Stripe; logado continua igual; o piloto incompleto
não trava a compra e recebe lembrete a cada 24 h até completar (no máximo 7); o card nasce no pagamento e o número
de cliente vai por e-mail. Nada fala com o Stripe, o Gmail nem o QuickBooks de verdade."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from command_center.db import todos, um
from command_center.providers import agenda_sessoes as ag
from command_center.tests.dados_portal import completa
from command_center.tests.test_agenda_sessoes import proximo
from command_center.tests.test_carrinho import SENHA, _checkout, _entrar, _pagar, _sessao, loja  # noqa: F401
from command_center.tests.test_stripe_loja import _simples, amb  # noqa: F401

URL = "/ops/api/vitrine/carrinho/checkout"


@pytest.fixture()
def lj(loja):  # noqa: F811 — a loja do test_carrinho (Stripe, QuickBooks e Gmail falsos)
    return loja


def _rodar(con):
    from command_center.providers import conta_site
    return conta_site.rodar(con)


def _dados(**mudar):
    d = {"name": "Lia Souza", "email": "lia@example.com", "birth_date": "1980-01-01", "phone_country": "+1",
         "phone": "(407) 555-0142", "address_line1": "100 Main St", "address_line2": "", "city": "Orlando", "state": "FL",
         "zip": "32809", "country": "US", "accept_terms": True, "password": SENHA, "password2": SENHA,
         "piloto": {"eu": False, "nome": "Theo Souza"}}
    d.update(mudar)
    return d


def _novo(cli, itens, conta=None, **cab):
    return cli.post(URL, json={"itens": itens, "entrega": "retirada", "conta": conta or _dados()}, headers=cab)


def _todos_emails(tmp):
    f = tmp / "emails.jsonl"
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


def _boas_vindas(tmp, para="lia@example.com"):
    return [m for m in _todos_emails(tmp) if m["to"] == para and m["subject"].startswith(("Welcome to URACE", "Bem-vindo"))]


def _banco_tem(tmp, texto):
    """O texto aparece em algum arquivo do banco (o principal ou o WAL)?"""
    return any(texto.encode() in f.read_bytes() for f in tmp.glob("cc.sqlite*"))


# ------------------------------------------------------------------ sem conta: o carrinho cria
def test_sem_conta_os_dados_do_carrinho_viram_a_conta_e_o_checkout_abre(lj):
    cli, con, st, qbo, tmp, sid = lj
    dia = proximo(5)
    d = cli.post("/ops/api/vitrine/carrinho", json={"itens": [_sessao(sid, dia)]}).json()
    assert d["precisa_conta"] and d["tem_sessao"] and d["ok"], "sem conta, o carrinho pede os dados (não trava)"
    r = _novo(cli, [_sessao(sid, dia)])
    assert r.status_code == 200, r.text
    assert r.json()["url"].startswith("https://checkout.stripe.com/")
    c = um(con, "SELECT * FROM portal_accounts WHERE email='lia@example.com'")
    assert c and (c["name"], c["city"], c["phone"]) == ("Lia Souza", "Orlando", "407-555-0142")
    assert c["terms_accepted_at"] and c["welcome_sent_at"] and c["welcome_lang"] == "en"
    (p,) = todos(con, "SELECT * FROM portal_pilots WHERE account_id=?", (c["id"],))
    assert (p["name"], p["is_self"], p["measures"]) == ("Theo Souza", 0, None), "o piloto entra só com o nome"
    # o pedido é da conta nova e o piloto dela está na sessão; o Stripe recebe o e-mail dela
    o = um(con, "SELECT * FROM store_orders")
    assert o["account_id"] == c["id"]
    assert um(con, "SELECT pilot_id FROM store_order_items WHERE order_id=? AND kind='sessao'", (o["id"],))["pilot_id"] == p["id"]
    assert st.chamadas[0][2]["customer_email"] == "lia@example.com"
    # já sai logada neste navegador (volta do Stripe para a página do pedido e para a área dela)
    assert cli.cookies.get("cp_session") and cli.cookies.get("cp_csrf")
    assert cli.get("/ops/api/portal/me").json()["email"] == "lia@example.com"
    # a senha nunca fica no banco: só o hash
    assert c["pw_hash"] and c["pw_hash"] != SENHA and not _banco_tem(tmp, SENHA)
    aud = um(con, "SELECT * FROM audit_logs WHERE event='portal.signup'")
    assert aud and json.loads(aud["detail"]) == {"origem": "carrinho", "piloto": True}


def test_as_boas_vindas_tem_a_marca_o_login_a_senha_e_o_link_da_area(lj):
    cli, con, st, qbo, tmp, sid = lj
    assert _novo(cli, [_sessao(sid, proximo(5))]).status_code == 200
    (m,) = _boas_vindas(tmp)
    assert m["subject"] == "Welcome to URACE: your account is ready"
    assert "Login: lia@example.com" in m["text"] and f"Password: {SENHA}" in m["text"]
    assert "Customer ID: arrives by email as soon as your card is ready" in m["text"], "o card só nasce no pagamento"
    assert "https://my.urace.us/ops/portal" in m["text"] and "https://my.urace.us/ops/portal/forgot" in m["text"]
    h = m["html"]
    assert ">U</span>" in h and ">RACE</span>" in h and "the Champion's Factory" in h and "#d91617" in h, "a marca"
    assert 'href="https://my.urace.us/ops/portal"' in h and SENHA in h and "lia@example.com" in h
    assert "10724 Cosmonaut Blvd" in h, "o rodapé com o endereço do site"


def test_eu_sou_o_piloto_usa_o_proprio_responsavel(lj):
    cli, con, st, qbo, tmp, sid = lj
    r = _novo(cli, [_sessao(sid, proximo(5))], _dados(piloto={"eu": True}))
    assert r.status_code == 200, r.text
    c = um(con, "SELECT id FROM portal_accounts")
    (p,) = todos(con, "SELECT * FROM portal_pilots WHERE account_id=?", (c["id"],))
    assert (p["name"], p["is_self"], p["birth_date"]) == ("Lia Souza", 1, "1980-01-01")
    assert um(con, "SELECT pilot_id FROM store_order_items WHERE kind='sessao'")["pilot_id"] == p["id"]


def test_so_produto_cria_a_conta_sem_piloto(lj):
    cli, con, st, qbo, tmp, sid = lj
    p = _simples()
    r = _novo(cli, [{"tipo": "produto", "produto": p["slug"]}], _dados(piloto={"eu": True}))
    assert r.status_code == 200, r.text
    c = um(con, "SELECT id FROM portal_accounts")
    assert not todos(con, "SELECT id FROM portal_pilots"), "sem sessão, ninguém vira piloto"
    assert um(con, "SELECT account_id FROM store_orders")["account_id"] == c["id"]
    assert len(_boas_vindas(tmp)) == 1


# ------------------------------------------------------------------ erros não criam conta
def test_senha_curta_ou_diferente_campo_faltando_e_termos_nao_criam_conta(lj):
    cli, con, st, qbo, tmp, sid = lj
    itens = [_sessao(sid, proximo(5))]
    casos = [
        (_dados(password="curta", password2="curta"), "at least 8 characters"),
        (_dados(password2="outra-senha-9"), "don't match"),
        (_dados(birth_date=""), "Date of birth"),
        (_dados(accept_terms=False), "accept the terms"),
        (_dados(email="sem-arroba"), "email"),
        (_dados(birth_date="2015-01-01"), "18 or older"),
        (_dados(piloto={"eu": False, "nome": ""}), "name"),
    ]
    for conta, trecho in casos:
        r = _novo(cli, itens, conta)
        assert r.status_code == 400, (trecho, r.text)
        assert trecho.lower() in r.json()["erro"].lower() and not r.json()["sign_in"], (trecho, r.json())
    assert not todos(con, "SELECT id FROM portal_accounts") and not todos(con, "SELECT id FROM portal_pilots")
    assert not st.chamadas and not _todos_emails(tmp) and not cli.cookies.get("cp_session")
    r = _novo(cli, itens, "não é um objeto")
    assert r.status_code == 400 and not todos(con, "SELECT id FROM portal_accounts")


def test_email_que_ja_tem_conta_pede_para_entrar_e_nao_mexe_na_conta(lj):
    cli, con, st, qbo, tmp, sid = lj
    conta, _ = _entrar(cli, con)
    cli.post("/ops/api/portal/logout")
    antes = dict(um(con, "SELECT * FROM portal_accounts WHERE id=?", (conta,)))
    r = _novo(cli, [_sessao(sid, proximo(5))], _dados(email="LIA@example.com", name="Outra Pessoa"))
    assert r.status_code == 400 and r.json()["sign_in"] is True and "already exists" in r.json()["erro"]
    assert dict(um(con, "SELECT * FROM portal_accounts WHERE id=?", (conta,))) == antes
    assert len(todos(con, "SELECT id FROM portal_accounts")) == 1 and not st.chamadas
    assert not cli.cookies.get("cp_session"), "não entra na conta dos outros"


def test_limite_de_cadastros_por_conexao(lj):
    cli, con, st, qbo, tmp, sid = lj
    from command_center.api import portal as api_portal
    from command_center.db import inserir
    for _ in range(api_portal.MAX_CADASTROS_POR_HORA):
        inserir(con, "login_attempts", key="portal-signup:testclient", ok=1)
    con.commit()
    r = _novo(cli, [_sessao(sid, proximo(5))])
    assert r.status_code == 429 and not todos(con, "SELECT id FROM portal_accounts") and not st.chamadas


def test_criar_conta_pede_json_de_verdade(lj):
    """Um formulário de outro site não manda JSON sem o navegador perguntar antes (CORS): sem JSON, nada."""
    cli, con, st, qbo, tmp, sid = lj
    corpo = json.dumps({"itens": [_sessao(sid, proximo(5))], "conta": _dados()})
    r = cli.post(URL, content=corpo, headers={"Content-Type": "text/plain"})
    assert r.status_code == 415 and not todos(con, "SELECT id FROM portal_accounts")


def test_carrinho_com_problema_volta_a_conta_atras(lj):
    """A vaga sumiu antes do checkout: a pessoa vê o erro e o formulário continua preenchido; nada de conta pela metade."""
    cli, con, st, qbo, tmp, sid = lj
    dia = proximo(5)
    ag.bloquear(con, None, dia.isoformat(), dia.isoformat(), "manha", "evento")
    con.commit()
    r = _novo(cli, [_sessao(sid, dia)])
    assert r.status_code == 400 and "no longer available" in r.json()["erro"]
    assert not todos(con, "SELECT id FROM portal_accounts") and not todos(con, "SELECT id FROM portal_pilots")
    assert not _todos_emails(tmp) and not cli.cookies.get("cp_session") and not st.chamadas


def test_stripe_fora_do_ar_a_conta_fica_e_a_pessoa_tenta_de_novo_logada(lj, monkeypatch):
    cli, con, st, qbo, tmp, sid = lj
    from command_center.providers import stripe_loja

    def cai(*a, **k):
        raise stripe_loja.ErroStripe("Stripe HTTP 500")
    monkeypatch.setattr(stripe_loja, "_http", cai)
    r = _novo(cli, [_sessao(sid, proximo(5))])
    assert r.status_code == 502
    assert um(con, "SELECT id FROM portal_accounts WHERE email='lia@example.com'")
    assert cli.cookies.get("cp_session") and len(_boas_vindas(tmp)) == 1
    monkeypatch.setattr(stripe_loja, "_http", st)
    pid = um(con, "SELECT id FROM portal_pilots")["id"]
    r = _checkout(cli, [_sessao(sid, proximo(5), pid)])
    assert r.status_code == 200, r.text
    assert len(todos(con, "SELECT id FROM portal_accounts")) == 1 and len(_boas_vindas(tmp)) == 1


def test_em_portugues(lj):
    cli, con, st, qbo, tmp, sid = lj
    cli.cookies.set("urace_lang", "pt")
    r = _novo(cli, [_sessao(sid, proximo(5))], _dados(password2="outra-senha-9"))
    assert r.json()["erro"] == "As senhas não são iguais."
    r = _novo(cli, [_sessao(sid, proximo(5))], _dados(name=""))
    assert r.status_code == 400 and r.json()["erro"] == "Digite o seu nome completo (nome e sobrenome).", r.json()
    assert _novo(cli, [_sessao(sid, proximo(5))]).status_code == 200
    (m,) = _boas_vindas(tmp)
    assert m["subject"] == "Bem-vindo à URACE: a sua conta está pronta"
    assert f"Senha: {SENHA}" in m["text"] and "Número de cliente: chega por e-mail" in m["text"]
    assert '<html lang="pt-BR">' in m["html"]
    assert um(con, "SELECT welcome_lang FROM portal_accounts")["welcome_lang"] == "pt"


# ------------------------------------------------------------------ logado continua igual
def test_logado_usa_a_conta_dele_e_ignora_os_dados_do_formulario(lj):
    cli, con, st, qbo, tmp, sid = lj
    conta, pid = _entrar(cli, con)
    antes = len(_todos_emails(tmp))
    r = cli.post(URL, json={"itens": [_sessao(sid, proximo(5), pid)], "conta": _dados(email="outra@example.com")},
                 headers={"X-CSRF": cli.cookies.get("cp_csrf")})
    assert r.status_code == 200, r.text
    assert len(todos(con, "SELECT id FROM portal_accounts")) == 1
    assert um(con, "SELECT account_id FROM store_orders")["account_id"] == conta
    assert len(_todos_emails(tmp)) == antes, "logado, nenhuma conta nova e nenhum e-mail de boas-vindas"


def test_piloto_incompleto_nao_trava_e_a_linha_avisa(lj):
    cli, con, st, qbo, tmp, sid = lj
    conta, pid = _entrar(cli, con)
    from command_center.db import inserir
    novo = inserir(con, "portal_pilots", account_id=conta, name="Bia Souza")
    con.commit()
    d = cli.post("/ops/api/vitrine/carrinho", json={"itens": [_sessao(sid, proximo(5), novo)]}).json()
    (linha,) = d["linhas"]
    assert linha["erro"] is None and "Bia Souza's measurements" in linha["aviso_piloto"] and d["ok"]
    drivers = {x["name"]: x for x in d["account"]["drivers"]}
    assert drivers["Bia Souza"]["pending"] and drivers["Bia Souza"]["blocked"] is None
    assert drivers["Theo Souza"]["pending"] is None
    # o responsável incompleto continua travando (o carrinho pede os dados dele)
    con.execute("UPDATE portal_accounts SET address_line1=NULL WHERE id=?", (conta,))
    con.commit()
    d = cli.post("/ops/api/vitrine/carrinho", json={"itens": [_sessao(sid, proximo(5), novo)]}).json()
    assert "account holder" in d["linhas"][0]["erro"] and not d["ok"]


# ------------------------------------------------------------------ depois do pagamento
def test_pago_o_card_nasce_o_numero_vai_por_email_e_o_lembrete_repete_ate_completar(lj):
    cli, con, st, qbo, tmp, sid = lj
    dia = proximo(5)
    assert _novo(cli, [_sessao(sid, dia)]).status_code == 200
    conta = um(con, "SELECT id FROM portal_accounts")["id"]
    pid = um(con, "SELECT id FROM portal_pilots")["id"]
    assert _pagar(cli, st, next(iter(st.sessoes))).json()["resultado"] == "pago"
    b = um(con, "SELECT * FROM bookings")
    assert b["pilot_id"] == pid and b["pilot_pending"] == 1, "pagou com o piloto incompleto: lembrar"
    card = um(con, "SELECT client_id FROM portal_pilots WHERE id=?", (pid,))["client_id"]
    assert card
    # 1º ciclo: o número de cliente (uma vez) e o primeiro lembrete
    assert _rodar(con) == {"numeros": 1, "lembretes": 1}
    con.commit()
    num = [m for m in _todos_emails(tmp) if m["subject"] == f"Your URACE customer ID: {card}"]
    assert len(num) == 1 and f"Customer ID: {card}" in num[0]["text"] and "Theo Souza" in num[0]["text"]
    lemb = [m for m in _todos_emails(tmp) if m["subject"].startswith("Almost there")]
    assert len(lemb) == 1 and "Theo Souza" in lemb[0]["subject"] and "height" in lemb[0]["text"]
    assert "https://my.urace.us/ops/portal/drivers" in lemb[0]["text"]
    assert dia.strftime("%b") in lemb[0]["subject"], "a data como a pessoa lê, não 2026-10-20"
    # antes de 24 h, nada de novo
    assert _rodar(con) == {"numeros": 0, "lembretes": 0}
    # 24 h depois, outro lembrete
    ontem = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    con.execute("UPDATE portal_pilots SET remind_at=? WHERE id=?", (ontem, pid))
    assert _rodar(con)["lembretes"] == 1
    assert um(con, "SELECT remind_n FROM portal_pilots WHERE id=?", (pid,))["remind_n"] == 2
    # no máximo 7
    con.execute("UPDATE portal_pilots SET remind_at=?, remind_n=7 WHERE id=?", (ontem, pid))
    assert _rodar(con)["lembretes"] == 0
    # completou: para de lembrar e a sessão sai da lista
    con.execute("UPDATE portal_pilots SET remind_at=?, remind_n=1 WHERE id=?", (ontem, pid))
    con.execute("UPDATE portal_pilots SET birth_date='2012-05-05' WHERE id=?", (pid,))
    completa(con, conta, pid)
    assert _rodar(con)["lembretes"] == 0
    assert um(con, "SELECT pilot_pending FROM bookings")["pilot_pending"] == 0


def test_sessao_que_passou_ou_cancelada_nao_lembra(lj):
    cli, con, st, qbo, tmp, sid = lj
    assert _novo(cli, [_sessao(sid, proximo(5))]).status_code == 200
    assert _pagar(cli, st, next(iter(st.sessoes))).json()["resultado"] == "pago"
    _rodar(con)
    con.execute("UPDATE portal_pilots SET remind_at=NULL, remind_n=0")
    con.execute("UPDATE bookings SET status='cancelada'")
    assert _rodar(con)["lembretes"] == 0
    con.execute("UPDATE bookings SET status='pendente', date='2020-01-06'")
    assert _rodar(con)["lembretes"] == 0


def test_conta_antiga_nao_recebe_numero_de_surpresa(lj):
    """Só quem recebeu as boas-vindas (contas do #305 em diante) recebe o e-mail do número de cliente."""
    cli, con, st, qbo, tmp, sid = lj
    conta, pid = _entrar(cli, con)
    con.execute("UPDATE portal_accounts SET welcome_sent_at=NULL WHERE id=?", (conta,))
    con.execute("UPDATE portal_pilots SET client_id=(SELECT MIN(id) FROM clients) WHERE id=?", (pid,))
    con.commit()
    antes = len(_todos_emails(tmp))
    assert _rodar(con)["numeros"] == 0 and len(_todos_emails(tmp)) == antes


# ------------------------------------------------------------------ cadastro pela área do cliente e senha
def test_cadastro_pela_area_do_cliente_tambem_recebe_as_boas_vindas(lj):
    cli, con, st, qbo, tmp, sid = lj
    _entrar(cli, con)
    (m,) = _boas_vindas(tmp)
    assert f"Password: {SENHA}" in m["text"] and m["html"].startswith("<!doctype html>")
    assert um(con, "SELECT welcome_sent_at FROM portal_accounts")["welcome_sent_at"]


def test_gmail_fora_do_ar_a_conta_fica_e_a_equipe_ve_o_erro(lj, monkeypatch):
    cli, con, st, qbo, tmp, sid = lj
    from command_center.providers import email_envio

    def falha(*a, **k):
        raise email_envio.ErroEnvio("Gmail fora do ar")
    monkeypatch.setattr(email_envio, "enviar", falha)
    assert _novo(cli, [_sessao(sid, proximo(5))]).status_code == 200
    c = um(con, "SELECT * FROM portal_accounts")
    assert c and c["welcome_sent_at"] is None and "Gmail fora do ar" in c["welcome_error"]


def test_nome_com_html_sai_escapado_no_email():
    from command_center.providers import conta_site
    conta = {"name": "Lia <b>Souza</b>", "email": "lia@example.com"}
    assunto, texto, h = conta_site.texto_boas_vindas(conta, "senha<script>", [], "en")
    assert "<b>" not in h and "<script>" not in h and "senha&lt;script&gt;" in h


def test_esqueci_a_senha_sai_com_a_identidade_da_urace(lj):
    cli, con, st, qbo, tmp, sid = lj
    _entrar(cli, con)
    cli.post("/ops/api/portal/logout")
    assert cli.post("/ops/api/portal/password/forgot", json={"email": "lia@example.com"}).status_code == 200
    (m,) = [x for x in _todos_emails(tmp) if x["subject"] == "Reset your URACE password"]
    assert "/ops/portal/reset" in m["text"] and "Choose a new password" in m["html"] and "#d91617" in m["html"]


# ------------------------------------------------------------------ a página do carrinho
def test_o_carrinho_tem_o_formulario_dos_dados_com_senha_confirmada_e_os_termos(lj):
    cli, con, st, qbo, tmp, sid = lj
    h = cli.get("/cart/").text
    assert 'class="form-pedido carrinho-cadastro" method="post" hidden' in h
    for nome in ("name", "birth_date", "email", "phone_country", "phone", "address_line1", "city", "state", "zip",
                 "country", "piloto_eu", "piloto_nome", "accept_terms"):
        assert f'name="{nome}"' in h, nome
    assert h.count('autocomplete="new-password"') == 2 and 'href="/legal/privacy.html"' in h
    assert h.count("<h1") == 1 and 'data-ddi="+55"' in h
    assert "Create account" not in h

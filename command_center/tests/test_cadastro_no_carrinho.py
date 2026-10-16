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


def test_criar_conta_de_outro_site_nao_passa(lj):
    """Revisão do #305: `text/plain;x=application/json` não faz o navegador perguntar antes (CORS) e passava pela
    conferência por pedaço do texto; e o navegador que diz que veio de outro site não cria conta."""
    cli, con, st, qbo, tmp, sid = lj
    corpo = json.dumps({"itens": [_sessao(sid, proximo(5))], "conta": _dados()})
    r = cli.post(URL, content=corpo, headers={"Content-Type": "text/plain;a=application/json"})
    assert r.status_code == 415
    r = cli.post(URL, content=corpo, headers={"Content-Type": "application/json", "Origin": "https://outro-site.example.com"})
    assert r.status_code == 403
    assert not todos(con, "SELECT id FROM portal_accounts") and not _todos_emails(tmp) and not st.chamadas
    r = cli.post(URL, content=corpo, headers={"Content-Type": "application/json; charset=utf-8", "Origin": "https://novo.urace.us"})
    assert r.status_code == 200, r.text


def test_duas_sessoes_cada_uma_com_o_seu_piloto(lj):
    """Revisão do #305 (regra do dono: nunca pôr serviço de um cliente no card de outro): com duas sessões ou mais, o
    carrinho pede o nome do piloto de cada uma; o mesmo nome é o mesmo piloto, o nome do titular é ele mesmo."""
    cli, con, st, qbo, tmp, sid = lj
    from command_center.tests.test_agenda_sessoes import abre
    abre(con, cap=3)
    con.commit()
    dia, outro = proximo(5), proximo(6)
    itens = [_sessao(sid, dia), _sessao(sid, dia), _sessao(sid, outro), _sessao(sid, outro, turno="tarde")]
    por = [{"idx": 0, "nome": "Theo Souza"}, {"idx": 1, "nome": "Bia  Souza"}, {"idx": 2, "nome": "theo souza"},
           {"idx": 3, "nome": "Lia Souza"}]
    r = _novo(cli, itens, _dados(piloto={"por_sessao": por}))
    assert r.status_code == 200, r.text
    conta = um(con, "SELECT id FROM portal_accounts")["id"]
    pilotos = {p["name"]: p for p in todos(con, "SELECT * FROM portal_pilots WHERE account_id=?", (conta,))}
    assert set(pilotos) == {"Theo Souza", "Bia Souza", "Lia Souza"} and pilotos["Lia Souza"]["is_self"] == 1
    linhas = [x["pilot_id"] for x in todos(con, "SELECT pilot_id FROM store_order_items WHERE kind='sessao' ORDER BY id")]
    assert linhas == [pilotos["Theo Souza"]["id"], pilotos["Bia Souza"]["id"], pilotos["Theo Souza"]["id"], pilotos["Lia Souza"]["id"]]


def test_piloto_por_sessao_pede_todos_os_nomes_e_o_mesmo_piloto_nao_fica_em_dois_lugares(lj):
    cli, con, st, qbo, tmp, sid = lj
    from command_center.tests.test_agenda_sessoes import abre
    abre(con, cap=3)
    con.commit()
    dia = proximo(5)
    itens = [_sessao(sid, dia), _sessao(sid, dia)]
    r = _novo(cli, itens, _dados(piloto={"por_sessao": [{"idx": 0, "nome": "Theo Souza"}]}))
    assert r.status_code == 400 and "each session" in r.json()["erro"]
    r = _novo(cli, itens, _dados(piloto={"por_sessao": [{"idx": 0, "nome": "Theo Souza"}, {"idx": 1, "nome": "THEO SOUZA"}]}))
    assert r.status_code == 400 and "same driver" in r.json()["erro"]
    assert not todos(con, "SELECT id FROM portal_accounts")


def test_duas_sessoes_no_mesmo_horario_nao_criam_conta(lj):
    """Revisão do #305: a conta nova leva um piloto; duas sessões no mesmo turno (ou o dia inteiro e um turno) não
    fechariam depois, então a conta nem nasce."""
    cli, con, st, qbo, tmp, sid = lj
    from command_center.tests.test_agenda_sessoes import abre
    abre(con, cap=3)
    con.commit()
    dia = proximo(5)
    for itens in ([_sessao(sid, dia), _sessao(sid, dia)], [_sessao(sid, dia, turno="dia"), _sessao(sid, dia, turno="tarde")]):
        r = _novo(cli, itens)
        assert r.status_code == 400 and "same time" in r.json()["erro"], r.text
    assert not todos(con, "SELECT id FROM portal_accounts") and not _todos_emails(tmp) and not cli.cookies.get("cp_session")
    r = _novo(cli, [_sessao(sid, dia), _sessao(sid, dia, turno="tarde")])
    assert r.status_code == 200, "manhã e tarde do mesmo dia, um piloto: fecha"


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
    assert _rodar(con) == {"boas_vindas": 0, "numeros": 1, "lembretes": 1}
    con.commit()
    num = [m for m in _todos_emails(tmp) if m["subject"] == f"Your URACE customer ID: {card}"]
    assert len(num) == 1 and f"Customer ID: {card}" in num[0]["text"] and "Theo Souza" in num[0]["text"]
    lemb = [m for m in _todos_emails(tmp) if m["subject"].startswith("Almost there")]
    assert len(lemb) == 1 and "Theo Souza" in lemb[0]["subject"] and "height" in lemb[0]["text"]
    assert "https://my.urace.us/ops/portal/drivers" in lemb[0]["text"]
    assert dia.strftime("%b") in lemb[0]["subject"], "a data como a pessoa lê, não 2026-10-20"
    # antes de 24 h, nada de novo
    assert _rodar(con) == {"boas_vindas": 0, "numeros": 0, "lembretes": 0}
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
    r = um(con, "SELECT remind_n, remind_at FROM portal_pilots WHERE id=?", (pid,))
    assert (r["remind_n"], r["remind_at"]) == (0, None), "completou: a contagem volta a zero para a próxima vez"


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
    from command_center.db import inserir
    conta, pid = _entrar(cli, con)
    card = inserir(con, "clients", name="Theo Souza")
    con.execute("UPDATE portal_accounts SET welcome_sent_at=NULL WHERE id=?", (conta,))
    con.execute("UPDATE portal_pilots SET client_id=? WHERE id=?", (card, pid))
    con.commit()
    antes = len(_todos_emails(tmp))
    assert _rodar(con)["numeros"] == 0 and len(_todos_emails(tmp)) == antes


def test_card_trocado_depois_do_email_manda_o_numero_certo(lj):
    """Revisão do #305: a equipe une o card duplicado (ou religa o piloto): o número que foi antes não vale mais."""
    cli, con, st, qbo, tmp, sid = lj
    from command_center.db import inserir
    assert _novo(cli, [_sessao(sid, proximo(5))]).status_code == 200
    assert _pagar(cli, st, next(iter(st.sessoes))).json()["resultado"] == "pago"
    _rodar(con)
    pid = um(con, "SELECT id FROM portal_pilots")["id"]
    certo = inserir(con, "clients", name="Theo Souza")
    con.execute("UPDATE portal_pilots SET client_id=? WHERE id=?", (certo, pid))
    assert _rodar(con)["numeros"] == 1
    (m,) = [x for x in _todos_emails(tmp) if x["subject"] == f"Your URACE customer ID: {certo}"]
    assert "changed: this is the right one" in m["text"]
    assert _rodar(con)["numeros"] == 0


def test_quem_comprou_so_produto_recebe_o_numero_quando_a_conta_ganha_o_card(lj):
    """Revisão do #305: sem piloto, o card é o da própria conta (a equipe liga em Contas de clientes)."""
    cli, con, st, qbo, tmp, sid = lj
    from command_center.db import inserir
    p = _simples()
    assert _novo(cli, [{"tipo": "produto", "produto": p["slug"]}], _dados(piloto={"eu": True})).status_code == 200
    assert _rodar(con)["numeros"] == 0, "ainda sem card"
    card = inserir(con, "clients", name="Lia Souza")
    con.execute("UPDATE portal_accounts SET client_id=?", (card,))
    assert _rodar(con)["numeros"] == 1
    (m,) = [x for x in _todos_emails(tmp) if x["subject"] == f"Your URACE customer ID: {card}"]
    assert f"Customer ID: {card}" in m["text"] and m["to"] == "lia@example.com"
    assert _rodar(con)["numeros"] == 0, "uma vez só"


# ------------------------------------------------------------------ cadastro pela área do cliente e senha
def test_cadastro_pela_area_do_cliente_tambem_recebe_as_boas_vindas(lj):
    cli, con, st, qbo, tmp, sid = lj
    _entrar(cli, con)
    (m,) = _boas_vindas(tmp)
    assert f"Password: {SENHA}" in m["text"] and m["html"].startswith("<!doctype html>")
    assert um(con, "SELECT welcome_sent_at FROM portal_accounts")["welcome_sent_at"]


def test_gmail_fora_do_ar_a_conta_fica_e_as_boas_vindas_saem_depois_sem_a_senha(lj, monkeypatch):
    cli, con, st, qbo, tmp, sid = lj
    from command_center.providers import conta_site, email_envio
    enviar, tentativas = email_envio.enviar, []

    def falha(*a, **k):
        tentativas.append(1)
        raise email_envio.ErroEnvio("Gmail fora do ar")
    monkeypatch.setattr(conta_site, "ESPERAS", (0, 0))
    monkeypatch.setattr(email_envio, "enviar", falha)
    assert _novo(cli, [_sessao(sid, proximo(5))]).status_code == 200
    c = um(con, "SELECT * FROM portal_accounts")
    assert c and c["welcome_sent_at"] is None and "Gmail fora do ar" in c["welcome_error"] and c["welcome_lang"] == "en"
    assert len(tentativas) == 3, "a senha só existe na hora: tenta de novo antes de desistir"
    # o Gmail voltou: no laço, as boas-vindas saem sem a senha (uma vez por hora, no máximo)
    monkeypatch.setattr(email_envio, "enviar", enviar)
    assert _rodar(con)["boas_vindas"] == 0, "acabou de falhar: espera uma hora"
    con.execute("UPDATE portal_accounts SET updated_at='2020-01-01T00:00:00.000Z'")
    assert _rodar(con)["boas_vindas"] == 1
    (m,) = _boas_vindas(tmp)
    assert "Password: the one you chose when you signed up" in m["text"] and SENHA not in m["text"]
    assert "/ops/portal/forgot" in m["text"] and not _banco_tem(tmp, SENHA)
    c = um(con, "SELECT * FROM portal_accounts")
    assert c["welcome_sent_at"] and c["welcome_error"] is None
    assert _rodar(con)["boas_vindas"] == 0, "uma vez só"


def test_quem_nao_criou_a_conta_sabe_o_que_fazer(lj):
    cli, con, st, qbo, tmp, sid = lj
    assert _novo(cli, [_sessao(sid, proximo(5))]).status_code == 200
    (m,) = _boas_vindas(tmp)
    assert ("Didn't create this account? Choose a new password at https://my.urace.us/ops/portal/forgot (that signs out every "
            "other device) and reply to this email or call +1 (407) 250 2291.") in m["text"]


def test_titulo_do_email_nao_vira_link():
    """Revisão do #305: o primeiro nome que parece endereço não vira o "Hi …!" do e-mail com a marca da URACE."""
    from command_center.providers import conta_site
    for nome in ("evil.example/login Souza", "www.golpe.example Souza", "lia@example.com Souza", "http://x Souza"):
        assunto, texto, h = conta_site.texto_boas_vindas({"name": nome, "email": "lia@example.com"}, "pista-molhada-7", [], "en")
        assert texto.startswith("Hi,\n") and "<title>Hi!</title>" in h, nome
    assert conta_site.texto_boas_vindas({"name": "Ana Lee", "email": "a@example.com"}, "x" * 8, [], "en")[1].startswith("Hi Ana,")


def test_limite_geral_de_cadastros_e_o_bloco_ipv6(lj):
    cli, con, st, qbo, tmp, sid = lj
    from command_center.api import portal as api_portal
    from command_center.db import inserir
    assert api_portal._chave_cadastro("2001:db8:1:2:aaaa::1") == api_portal._chave_cadastro("2001:db8:1:2:bbbb::9") == "portal-signup:2001:db8:1:2::/64"
    assert api_portal._chave_cadastro("203.0.113.5") == "portal-signup:203.0.113.5"
    for i in range(api_portal.MAX_CADASTROS_GLOBAL_HORA):
        inserir(con, "login_attempts", key=f"portal-signup:198.51.100.{i % 250}", ok=1)
    con.commit()
    r = _novo(cli, [_sessao(sid, proximo(5))])
    assert r.status_code == 429 and "right now" in r.json()["erro"] and not todos(con, "SELECT id FROM portal_accounts")


def test_dados_que_nao_sao_texto_nao_derrubam_nem_valem_como_aceite(lj):
    cli, con, st, qbo, tmp, sid = lj
    itens = [_sessao(sid, proximo(5))]
    r = _novo(cli, itens, _dados(accept_terms="false"))
    assert r.status_code == 400 and "accept the terms" in r.json()["erro"]
    for ruim in ({"name": ["Lia", "Souza"]}, {"email": {"x": 1}}, {"password": ["x" * 9], "password2": ["x" * 9]},
                 {"piloto": {"eu": False, "nome": ["x"]}}):
        r = _novo(cli, itens, _dados(**ruim))
        assert r.status_code == 400, (ruim, r.text)
    assert not todos(con, "SELECT id FROM portal_accounts")


def test_aviso_do_piloto_em_portugues(lj):
    cli, con, st, qbo, tmp, sid = lj
    conta, pid = _entrar(cli, con)
    from command_center.db import inserir
    novo = inserir(con, "portal_pilots", account_id=conta, name="Bia Souza")
    con.commit()
    cli.cookies.set("urace_lang", "pt")
    d = cli.post("/ops/api/vitrine/carrinho", json={"itens": [_sessao(sid, proximo(5), novo)]}).json()
    assert d["linhas"][0]["aviso_piloto"].startswith("Depois do pagamento, mandamos por e-mail o link para pôr as medidas e a experiência de Bia Souza")


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
    # revisão do #305: os termos abrem em outra aba (o formulário não se perde); nos EUA, estado e ZIP obrigatórios
    assert 'href="/legal/eula.html" target="_blank" rel="noopener"' in h
    assert 'name="state" autocomplete="address-level1" maxlength="30" placeholder="FL" required' in h
    assert h.count('class="sr cad-us"') == 2 and 'class="cad-varios" hidden' in h and "cad-varios-campos" in h
    cli.cookies.set("urace_lang", "pt")
    pt = cli.get("/cart/").text
    assert "(obrigatório)" in pt and "(required)" not in pt and "Os seus dados" in pt

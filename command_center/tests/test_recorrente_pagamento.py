"""Stripe para o cliente novo, QuickBooks para o aluno recorrente (#314, parte 3).

Dono, 16/10: *"Quando for agendamento direto pelo site de cliente novo, que não for do Kart School, ele vai pagar
pelo Stripe. Quando for cliente do Kart School, que são os nossos clientes prós … esses clientes pagam pelo
QuickBooks."* Academy e Kart School são a mesma coisa.

O que estes testes trancam: o carrinho (Stripe) nunca cobra a sessão de um piloto com plano mensal vigente — a
linha dá erro e manda marcar na área do cliente, e o checkout não abre sessão no Stripe; o piloto sem plano segue
no carrinho como antes; a área do cliente diz, por piloto, como paga: do plano, no Stripe (site novo com o Stripe
ligado) ou pela invoice (Stripe desligado). Dados fictícios."""
from command_center.db import inserir, um
from command_center.tests.test_agenda_sessoes import proximo
from command_center.tests.test_carrinho import _checkout, _entrar, _sessao, loja  # noqa: F401
from command_center.tests.test_stripe_loja import amb  # noqa: F401


def _recorrente(con, pid):
    card = inserir(con, "clients", name="Lia Souza", pilot_name="Theo Souza", email="lia@example.com", status="ACTIVE",
                   plan_type="monthly", monthly_plan="Academy 4 stroke", monthly_amount=2756.90, monthly_sessions=4)
    con.execute("UPDATE portal_pilots SET client_id=? WHERE id=?", (card, pid))
    con.commit()
    return card


def test_carrinho_nao_cobra_no_stripe_a_sessao_do_aluno_recorrente(loja):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    conta, pid = _entrar(cli, con)
    dia = proximo(5)
    r = cli.post("/ops/api/vitrine/carrinho", json={"itens": [_sessao(sid, dia, piloto=pid)]}).json()
    assert not r["linhas"][0]["erro"], "sem plano: o carrinho vende como antes"
    _recorrente(con, pid)
    r = cli.post("/ops/api/vitrine/carrinho", json={"itens": [_sessao(sid, dia, piloto=pid)]}).json()
    linha = r["linhas"][0]
    assert linha["recorrente"] is True and "monthly plan" in linha["erro"] and "in your account" in linha["erro"]
    res = _checkout(cli, [_sessao(sid, dia, piloto=pid)])
    assert res.status_code == 400 and not st.chamadas, "o Stripe nunca cobra a sessão do aluno recorrente"
    assert not um(con, "SELECT COUNT(*) AS n FROM bookings")["n"]
    # o plano acabou (a recorrência terminou há muito): o cliente volta a pagar a sessão no Stripe como qualquer um
    card = um(con, "SELECT client_id FROM portal_pilots WHERE id=?", (pid,))["client_id"]
    inserir(con, "monthly_recurring", client_id=card, amount=2756.90, item_id="1", months=1,
            start_on="2025-01-01", end_on="2025-01-01", status="active")
    con.commit()
    r = cli.post("/ops/api/vitrine/carrinho", json={"itens": [_sessao(sid, dia, piloto=pid)]}).json()
    assert not r["linhas"][0]["erro"] and not r["linhas"][0].get("recorrente")


def test_area_do_cliente_diz_como_cada_piloto_paga(loja, monkeypatch):  # noqa: F811
    cli, con, st, qbo, tmp, sid = loja
    conta, pid = _entrar(cli, con)
    outro = inserir(con, "portal_pilots", account_id=conta, name="Bia Souza")
    con.commit()
    _recorrente(con, pid)
    r = cli.get("/ops/api/portal/plan").json()
    por = {x["driver_id"]: x for x in r["drivers"]}
    assert r["cart"] is True, "site novo com o Stripe ligado"
    assert por[pid]["payment"] == "plano" and por[pid]["recurring"] is True
    assert por[outro]["payment"] == "stripe" and por[outro]["recurring"] is False
    assert cli.get("/ops/api/portal/availability").json()["cart"] is True
    monkeypatch.delenv("STRIPE_SECRET_KEY")
    r = cli.get("/ops/api/portal/plan").json()
    assert r["cart"] is False and {x["driver_id"]: x["payment"] for x in r["drivers"]} == {pid: "plano", outro: "invoice"}, \
        "Stripe desligado: a invoice continua como hoje"
    assert cli.get(f"/ops/api/portal/plan?driver_id={outro + 99}").status_code == 404

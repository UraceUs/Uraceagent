"""Vários dias num pedido do aluno recorrente (#314, parte 2).

Dono, 16/10: *"é interessante eles terem a oportunidade de marcar mais de um dia, multi-seleção de dias. Então,
se ele quiser marcar para quartas, toda quarta. Ou quartas e sábado dessa semana, ou então sábado e domingo da
outra, ele consegue marcar isso tudo em um book."*

O que estes testes trancam: a cotação traz de cada dia o rótulo e o preço do servidor ("Included in your plan" /
"Extra session · $X") e não grava nada; o pedido é tudo ou nada; as extras do pedido saem numa invoice só (uma
chamada com N linhas) e a waiver sai uma vez; o pedido recusa piloto de outra conta, conflito de horário, mais de
12 dias, cliente sem plano e falta de CSRF; cotação vencida dá 409; nada do contador do pacote vai para o
cliente; a lista de sessões do cliente é paginada. Dados fictícios."""
import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api.main import app  # noqa: E402
from command_center.db import agora, aplicar_schema, conectar, inserir, todos, um  # noqa: E402
from command_center.providers import agenda_sessoes as ag  # noqa: E402
from command_center.providers import mensalidades, servicos_site, venda_site  # noqa: E402
from command_center.tests.dados_portal import ENDERECO, piloto  # noqa: E402
from command_center.tests.test_agenda_sessoes import abre, proximo  # noqa: E402

P = "/ops/api/portal"
CONTA = {"name": "Vera Lote", "email": "vera.lote@example.com", "password": "corrida-segura-9", "birth_date": "1984-03-03",
         "accept_terms": True, **ENDERECO}


@pytest.fixture()
def amb(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path))
    c = conectar(); aplicar_schema(c)
    inserir(c, "qbo_items", id="11", name="Arrive and Drive 4T", price=719)
    inserir(c, "qbo_items", id="892", name="Academy | Extra session (beyond monthly 4)", price=689)
    sid = servicos_site.criar(c, None, {"name": "Academy session", "price": 719, "qbo_item": "Arrive and Drive 4T", "deposit": 400})
    abre(c, cap=1)
    c.commit(); c.close()
    with TestClient(app, base_url="https://cc.test") as t:
        assert t.post(f"{P}/signup", json=CONTA).status_code == 201
        h = {"X-CSRF": t.cookies.get("cp_csrf")}
        conta = t.post(f"{P}/drivers", headers=h, json=piloto("Davi Lote")).json()
        pid = conta["drivers"][0]["id"]
        c = conectar()
        card = inserir(c, "clients", name="Vera Lote", pilot_name="Davi Lote", email="vera.lote@example.com", status="ACTIVE",
                       plan_type="monthly", monthly_plan="Academy 4 stroke", monthly_amount=1378.45, monthly_sessions=2)
        c.execute("UPDATE portal_pilots SET client_id=? WHERE id=?", (card, pid))
        c.commit()
        yield {"cli": t, "h": h, "con": c, "sid": sid, "pid": pid, "card": card, "conta": conta["id"]}
        c.close()


def quartas(n, a_partir=3):
    """n quartas-feiras seguidas, a partir de daqui a `a_partir` dias (dentro do horizonte de 60 dias)."""
    d = proximo(2, a_partir)
    return [(d + timedelta(days=7 * i)).isoformat() for i in range(n)]


def corpo(a, dias, **mais):
    return {"service_id": a["sid"], "driver_id": a["pid"], "slots": [{"date": d, "period": "manha"} for d in dias], **mais}


def cota(a, dias):
    r = a["cli"].post(f"{P}/bookings/quote", headers=a["h"], json=corpo(a, dias))
    assert r.status_code == 200, r.text
    return r.json()


def test_cotacao_traz_rotulo_e_preco_do_servidor_e_nao_grava_nada(amb):
    dias = quartas(4)
    q = cota(amb, dias)
    meses = {}
    for x in sorted(q["slots"], key=lambda y: y["date"]):
        meses.setdefault(x["date"][:7], []).append(x)
    esperado = [("Included in your plan" if i < 2 else "Extra session · $689.23") for m in meses.values() for i in range(len(m))]
    assert [x["label"] for m in meses.values() for x in m] == esperado, "2 do pacote por mês; o resto é extra (1.378,45 ÷ 2)"
    assert q["included"] + q["extras"] == 4 and q["extras_total"] == round(689.23 * q["extras"], 2)
    assert all(x["ok"] for x in q["slots"]) and len(q["hash"]) == 16
    texto = str(q)
    assert "usadas" not in texto and "sessoes_por_mes" not in texto and "used" not in texto, "o contador não vai para o cliente"
    assert not um(amb["con"], "SELECT COUNT(*) AS n FROM bookings")["n"], "cotar não grava"
    r = amb["cli"].get(f"{P}/plan").json()["drivers"][0]
    assert r == {"driver_id": amb["pid"], "recurring": True, "plan": "Academy 4 stroke", "extra_price": 689.23}


def test_pedido_de_varios_dias_entra_inteiro_com_uma_invoice_e_uma_waiver(amb, monkeypatch):
    con, cli = amb["con"], amb["cli"]
    dias = quartas(5)
    q = cota(amb, dias)
    r = cli.post(f"{P}/bookings/batch", headers=amb["h"], json=corpo(amb, dias, quote=q["hash"], notes="Rain tires"))
    assert r.status_code == 201, r.text
    gid, ids = r.json()["group_id"], r.json()["ids"]
    bs = todos(con, "SELECT * FROM bookings WHERE group_id=? ORDER BY date", (gid,))
    assert [b["id"] for b in bs] == ids and len(bs) == 5 and {b["notes"] for b in bs} == {"Rain tires"}
    assert [b["coverage"] for b in bs] == [x["coverage"] for x in sorted(q["slots"], key=lambda y: y["date"])]
    auditoria = um(con, "SELECT detail FROM audit_logs WHERE event='portal.booking.batch'")["detail"]
    assert str(gid) in auditoria and "Rain tires" not in auditoria, "a auditoria leva ids e datas, nunca o corpo"
    # a venda do pedido: as extras numa invoice só, com uma linha por sessão extra, e uma waiver para o pedido
    monkeypatch.setattr(mensalidades, "_cliente_qbo", lambda con, cid: "42")
    ag.mudar_config(con, None, auto_sell=True)
    chamadas, waivers, emails = [], [], []

    def qbo(**kw):
        chamadas.append(kw)
        return {"id": "501", "numero": "URACE-0501", "total": round(sum(x["unitario"] for x in kw["linhas"]), 2),
                "link": "https://qbo.test/inv/501", "link_pagamento": "https://connect.intuit.com/pay/501", "enviado": True,
                "enviado_para": kw["email"]}
    c = venda_site.vender_grupo(con, gid, enviar_invoice=qbo, enviar_waiver=lambda *a: waivers.append(a) or {"envelopeId": "e1"},
                                enviar_email=lambda *a: emails.append(a))
    extras = [b for b in bs if b["coverage"] == "extra"]
    assert len(chamadas) == 1 and len(chamadas[0]["linhas"]) == len(extras) >= 1, "uma invoice com as extras do pedido"
    assert {x["item_id"] for x in chamadas[0]["linhas"]} == {"892"} and {x["unitario"] for x in chamadas[0]["linhas"]} == {689.23}
    assert len(waivers) == 1, "uma waiver para o pedido inteiro"
    assert len(emails) == 1 and "Extra session · $689.23" in emails[0][2] and "Included in your plan" in emails[0][2]
    depois = todos(con, "SELECT * FROM bookings WHERE group_id=? ORDER BY date", (gid,))
    assert {b["qbo_invoice_id"] for b in depois if b["coverage"] == "extra"} == {"501"}
    assert {b["charge_kind"] for b in depois if b["coverage"] == "plano"} == {"contrato"}
    assert len({b["waiver_ref"] for b in depois}) == 1 and depois[0]["waiver_ref"]
    assert c["pagamento"]["estado"] == "pagar" and c["pagamento"]["invoice"] == "URACE-0501"
    # a página do pedido, do próprio cliente; a paga da invoice vale para todas as extras
    con.commit()
    g = cli.get(f"{P}/bookings/group/{gid}").json()
    assert [x["label"] for x in g["sessions"]] == [("Included in your plan" if b["coverage"] == "plano" else "Extra session · $689.23")
                                                   for b in depois]
    depois_de_1_min = datetime.now(timezone.utc) + timedelta(minutes=2)      # a página já conferiu agora há pouco
    assert venda_site.conferir_pagamento_grupo(con, gid, ler=lambda i: {"saldo": 0, "total": 689.23}, agora_dt=depois_de_1_min)
    assert all(b["paid_at"] for b in todos(con, "SELECT * FROM bookings WHERE group_id=? AND coverage='extra'", (gid,)))
    # o laço de cobrança não cria outra invoice para as outras extras do pedido
    from command_center.providers import cobranca_agenda as cob
    cob.rodar(con, enviar_invoice=qbo, enviar_waiver=lambda *a: waivers.append(a), enviar_email=lambda *a: None)
    assert len(chamadas) == 1 and len(waivers) == 1


def test_pedido_e_tudo_ou_nada(amb):
    con, cli = amb["con"], amb["cli"]
    dias = quartas(3)
    q = cota(amb, dias)
    # outra pessoa pega a última vaga do 2º dia depois da cotação
    outra = inserir(con, "portal_accounts", email="outra.lote@example.com", pw_salt="x", pw_hash="x", name="Outra Pessoa",
                    birth_date="1980-01-01", terms_accepted_at=agora())
    inserir(con, "bookings", account_id=outra, date=dias[1], period="manha", status="confirmada")
    con.commit()
    r = cli.post(f"{P}/bookings/batch", headers=amb["h"], json=corpo(amb, dias, quote=q["hash"]))
    assert r.status_code == 400 and "not available" in r.json()["detail"]
    assert um(con, "SELECT COUNT(*) AS n FROM bookings WHERE account_id=?", (amb["conta"],))["n"] == 0, "nenhum dia entrou"
    assert um(con, "SELECT COUNT(*) AS n FROM booking_groups")["n"] == 0


def test_cotacao_vencida_da_409(amb):
    con, cli = amb["con"], amb["cli"]
    dias = quartas(5)                                   # 5 quartas: em até 2 meses de 2 no pacote, sempre há extra
    q = cota(amb, dias)
    assert q["extras"] >= 1
    con.execute("UPDATE clients SET extra_session_price=700 WHERE id=?", (amb["card"],))     # o preço da extra mudou
    con.commit()
    r = cli.post(f"{P}/bookings/batch", headers=amb["h"], json=corpo(amb, dias, quote=q["hash"]))
    assert r.status_code == 409 and "review" in r.json()["detail"]
    r = cli.post(f"{P}/bookings/batch", headers=amb["h"], json=corpo(amb, dias, quote="velha"))
    assert r.status_code == 409
    assert not um(con, "SELECT COUNT(*) AS n FROM bookings")["n"]


def test_recusas_outra_conta_conflito_mais_de_12_sem_plano_e_sem_csrf(amb):
    con, cli = amb["con"], amb["cli"]
    dias = quartas(2)
    outra = inserir(con, "portal_accounts", email="alheia.lote@example.com", pw_salt="x", pw_hash="x", name="Conta Alheia",
                    birth_date="1980-01-01", terms_accepted_at=agora())
    card2 = inserir(con, "clients", name="Conta Alheia", plan_type="monthly", monthly_amount=2756.90)
    alheio = inserir(con, "portal_pilots", account_id=outra, name="Piloto Alheio", client_id=card2)
    con.commit()
    r = cli.post(f"{P}/bookings/quote", headers=amb["h"], json={**corpo(amb, dias), "driver_id": alheio})
    assert r.status_code == 400 and "driver" in r.json()["detail"].lower()
    assert cli.post(f"{P}/bookings/batch", json=corpo(amb, dias, quote="x")).status_code == 403, "sem CSRF"
    muitos = [(proximo(0, 3) + timedelta(days=i)).isoformat() for i in range(13)]
    assert cli.post(f"{P}/bookings/quote", headers=amb["h"], json=corpo(amb, muitos)).status_code == 400
    # conflito: o piloto já tem sessão num dos dias
    inserir(con, "bookings", account_id=amb["conta"], pilot_id=amb["pid"], date=dias[0], period="dia", status="pendente")
    con.commit()
    q = cota(amb, dias)
    assert [x["ok"] for x in q["slots"]] == [False, True] and "already has a session" in q["slots"][0]["message"]
    r = cli.post(f"{P}/bookings/batch", headers=amb["h"], json=corpo(amb, dias, quote=q["hash"]))
    assert r.status_code == 400 and "already has a session" in r.json()["detail"]
    # o mesmo dia duas vezes no pedido
    q = cota(amb, [dias[1], dias[1]])
    assert [x["reason"] for x in q["slots"]] == [None, "repetido"]
    # sem plano mensal: um dia por vez
    con.execute("UPDATE clients SET plan_type=NULL, monthly_amount=NULL, monthly_sessions=NULL WHERE id=?", (amb["card"],))
    con.commit()
    r = cli.post(f"{P}/bookings/quote", headers=amb["h"], json=corpo(amb, dias))
    assert r.status_code == 400 and "monthly plan" in r.json()["detail"]
    assert cli.get(f"{P}/plan").json()["drivers"][0]["recurring"] is False


def test_lista_de_sessoes_do_cliente_e_paginada(amb):
    con, cli = amb["con"], amb["cli"]
    base = proximo(0, 3)
    for i in range(7):
        inserir(con, "bookings", account_id=amb["conta"], pilot_id=amb["pid"], date=(base + timedelta(days=i)).isoformat(),
                period="manha", status="cancelada")
    con.commit()
    r = cli.get(f"{P}/bookings?limit=3&offset=3").json()
    assert (r["total"], len(r["bookings"]), r["offset"]) == (7, 3, 3)
    assert [b["date"] for b in r["bookings"]] == [(base + timedelta(days=i)).isoformat() for i in (3, 2, 1)]
    assert len(cli.get(f"{P}/bookings").json()["bookings"]) == 7, "sem limit, como antes"


def test_invoice_das_extras_que_falhou_e_tentada_uma_vez_por_rodada(amb, monkeypatch):
    """O laço tenta de novo a invoice do pedido (até 3 vezes), não uma vez por dia extra do pedido."""
    from command_center.providers import cobranca_agenda as cob
    con, cli = amb["con"], amb["cli"]
    con.execute("UPDATE clients SET monthly_sessions=1 WHERE id=?", (amb["card"],))    # 1 por mês: 5 quartas, 3+ extras
    con.commit()
    dias = quartas(5)
    q = cota(amb, dias)
    assert q["extras"] >= 3
    gid = cli.post(f"{P}/bookings/batch", headers=amb["h"], json=corpo(amb, dias, quote=q["hash"])).json()["group_id"]
    monkeypatch.setattr(mensalidades, "_cliente_qbo", lambda con, cid: "42")
    tentativas = []

    def falha(**kw):
        tentativas.append(len(kw["linhas"]))
        raise RuntimeError("QuickBooks fora do ar")
    primeiro = todos(con, "SELECT id FROM bookings WHERE group_id=? ORDER BY date", (gid,))[0]["id"]
    cob.aceitar(con, 1, primeiro, enviar_invoice=falha, enviar_waiver=lambda *a: {"envelopeId": "e"})
    assert tentativas == [q["extras"]], "uma invoice com todas as extras"
    cob.rodar(con, enviar_invoice=falha, enviar_waiver=lambda *a: {"envelopeId": "e"}, enviar_email=lambda *a: None)
    assert len(tentativas) == 2, "uma tentativa por rodada para o pedido"
    extras = todos(con, "SELECT charge_error, charge_attempts FROM bookings WHERE group_id=? AND coverage='extra'", (gid,))
    assert {x["charge_attempts"] for x in extras} == {2} and all("fora do ar" in x["charge_error"] for x in extras)

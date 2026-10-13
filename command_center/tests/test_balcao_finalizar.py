"""#206: finalizar o balcão de peças.

Dono, 13/10: *"a gente tem que voltar e finalizar o balcão de peças urgentemente"*. O que
estes testes trancam: a revisão diz de onde a peça saiu, a peça de invoice paga não se desfaz,
a invoice paga no cartão não é enviada por e-mail, e a leitura pendente aparece em "Precisa de
atenção".
"""
from command_center.api import atencao
from command_center.db import conectar, um
from command_center.providers import estoque
from command_center.tests.test_balcao import entra
from command_center.tests.test_balcao_rapido import AMANHA, B, HOJE, cli  # noqa: F401 — a fixture


def _pendente(cli, data=HOJE):  # noqa: F811
    h = entra(cli)
    # "decidir depois": a leitura que fica para a revisão (com cliente, ela vai direto para a OS)
    return cli.post(f"{B}/rapido", json={"codigo": "7891234567895", "data": data}, headers=h).json()["id"]


# ------------------------------------------------------------------ a revisão diz de onde saiu
def test_revisao_confirma_tirando_do_local_escolhido(cli):  # noqa: F811
    con = conectar()
    estoque.transferir(con, cli.para, 2, de=estoque.SEDE, para="trailer")       # 3 no galpão, 2 no trailer
    con.close()
    pid = _pendente(cli)
    h = entra(cli, "ger@urace.us")
    item = cli.get(f"{B}/revisao").json()["itens"][0]["item"]
    assert item["nosso"] == 5, "a revisão mostra quanto a URACE tem"
    r = cli.post(f"{B}/revisao/{pid}/confirmar", json={"modo": "cobrar", "local": "trailer", "client_id": cli.leo}, headers=h)
    assert r.status_code == 200, r.text
    con = conectar()
    trailer = estoque.local(con, "trailer")["id"]
    sede = estoque.local(con, estoque.SEDE)["id"]
    assert estoque.saldo(con, cli.para, trailer, client_id=None) == 1 and estoque.saldo(con, cli.para, sede, client_id=None) == 3


def test_revisao_sem_saldo_no_local_e_recusada_e_a_leitura_continua_pendente(cli):  # noqa: F811
    pid = _pendente(cli)
    h = entra(cli, "ger@urace.us")
    r = cli.post(f"{B}/revisao/{pid}/confirmar", json={"modo": "cobrar", "local": "pista", "client_id": cli.leo}, headers=h)
    assert r.status_code == 400
    assert um(conectar(), "SELECT status FROM counter_pending WHERE id=?", (pid,))["status"] == "pendente"


# ------------------------------------------------------------------ invoice paga não se mexe
def _paga(cli):  # noqa: F811
    pid = _pendente(cli)
    h = entra(cli, "ger@urace.us")
    s = cli.post(f"{B}/revisao/{pid}/confirmar", json={"modo": "cobrar", "client_id": cli.leo}, headers=h).json()["leitura"]
    cli.qbo.qbo_invoice = lambda id: {"id": id, "numero": "URACE-0300", "cliente": "Maria Santos", "total": 89.5, "saldo": 0}
    r = cli.post(f"{B}/invoices/{s['parts_invoice_id']}/conferir-pagamento", headers=h).json()
    assert r["paga"] is True
    return s, h


def test_peca_de_invoice_paga_nao_se_desfaz(cli):  # noqa: F811
    s, h = _paga(cli)
    r = cli.post(f"{B}/leituras/{s['id']}/desfazer", headers=h)
    assert r.status_code == 400 and "paga" in r.json()["detail"]
    assert estoque.saldo(conectar(), cli.para, client_id=None) == 4, "o estoque não volta"
    est = cli.get(f"{B}/cliente/{cli.leo}").json()
    assert [x["travada"] for x in est["leituras"]] == [1], "a tela esconde o Desfazer"


def test_invoice_paga_sai_da_tela_do_cliente_no_dia_seguinte(cli, monkeypatch):  # noqa: F811
    _paga(cli)
    from command_center.providers import balcao
    monkeypatch.setattr(balcao, "hoje", lambda: AMANHA)
    est = cli.get(f"{B}/cliente/{cli.leo}").json()
    assert est["invoices"] == [], "antes ficava para sempre como 'aberta · não enviada'"


def test_enviar_confere_no_quickbooks_e_nao_manda_a_ja_paga(cli):  # noqa: F811
    pid = _pendente(cli)
    h = entra(cli, "ger@urace.us")
    s = cli.post(f"{B}/revisao/{pid}/confirmar", json={"modo": "cobrar", "client_id": cli.leo}, headers=h).json()["leitura"]
    cli.qbo.qbo_invoice = lambda id: {"id": id, "numero": "URACE-0300", "cliente": "Maria Santos", "total": 89.5, "saldo": 0}
    r = cli.post(f"{B}/invoices/{s['parts_invoice_id']}/enviar", headers=h)
    assert r.status_code == 400 and "já está paga" in r.json()["detail"]
    assert not any(c[0] == "enviar" for c in cli.qbo.chamadas), "nada sai por e-mail"
    p = um(conectar(), "SELECT paid_at, status FROM parts_invoices WHERE id=?", (s["parts_invoice_id"],))
    assert p["paid_at"] and p["status"] == "aberta"


def test_enviar_com_saldo_manda(cli):  # noqa: F811
    pid = _pendente(cli)
    h = entra(cli, "ger@urace.us")
    s = cli.post(f"{B}/revisao/{pid}/confirmar", json={"modo": "cobrar", "client_id": cli.leo}, headers=h).json()["leitura"]
    cli.qbo.qbo_invoice = lambda id: {"id": id, "numero": "URACE-0300", "cliente": "Maria Santos", "total": 89.5, "saldo": 89.5}
    r = cli.post(f"{B}/invoices/{s['parts_invoice_id']}/enviar", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "enviada"


# ------------------------------------------------------------------ pendente em "Precisa de atenção"
def test_leitura_pendente_aparece_em_precisa_de_atencao(cli):  # noqa: F811
    assert not any(i["key"].startswith("balcao:counter_pending") for i in atencao.coletar(conectar()))
    _pendente(cli, "2099-01-01")
    it = next(i for i in atencao.coletar(conectar()) if i["key"].startswith("balcao:counter_pending"))
    assert it["title"].startswith("1 peça(s)") and it["link"] == "/balcao" and it["level"] == "MEDIUM"
    assert "Front bumper" in it["facts"][0][1] and "Mecânico" in it["facts"][0][1]
    _pendente(cli, "2020-01-01")                       # leitura de dia que já passou: sobe para HIGH
    it = next(i for i in atencao.coletar(conectar()) if i["key"].startswith("balcao:counter_pending"))
    assert it["title"].startswith("2 peça(s)") and it["level"] == "HIGH"

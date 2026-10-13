"""#189: o balcão do celular em qualquer dia, a auditoria de quem lançou o quê, e o cliente que
não está no calendário do dia.

Dono, 12/10: *"eu tentei colocar, não tinha"*; *"buscar por dia, não só ontem, hoje e amanhã …
eu coloco a data, eu vejo que dia que é, eu vejo quem colocou o quê, fazendo uma auditoria"*.
"""
from command_center.db import conectar, um
from command_center.providers import balcao_rapido
from command_center.tests.test_balcao import entra
from command_center.tests.test_balcao_rapido import AMANHA, B, HOJE, cli  # noqa: F401 — a fixture


def test_cliente_fora_do_calendario_e_achado_pelo_nome_sem_contato(cli):  # noqa: F811
    entra(cli)
    r = cli.get(f"{B}/rapido/clientes", params={"q": "ana"}).json()
    assert r == [{"client_id": cli.ana, "nome": "Ana Lima", "responsavel": None}]
    r = cli.get(f"{B}/rapido/clientes", params={"q": "leo"}).json()
    assert r == [{"client_id": cli.leo, "nome": "Leo Santos", "responsavel": "Maria Santos"}]
    assert "email" not in str(r) and "familia@" not in str(r)
    assert cli.get(f"{B}/rapido/clientes", params={"q": "a"}).status_code == 422


def test_registra_para_quem_nao_esta_no_dia(cli):  # noqa: F811
    h = entra(cli)
    assert all(p["client_id"] != cli.ana for p in cli.get(f"{B}/rapido", params={"data": HOJE}).json()["pilotos"])
    r = cli.post(f"{B}/rapido", json={"codigo": "7891234567895", "data": HOJE, "client_id": cli.ana}, headers=h)
    assert r.status_code == 201 and r.json()["pilot_name"] == "Ana Lima"


def test_auditoria_mostra_quem_lancou_o_que_no_dia(cli):  # noqa: F811
    h = entra(cli)
    a = cli.post(f"{B}/rapido", json={"codigo": "7891234567895", "data": AMANHA}, headers=h).json()["id"]   # decidir depois
    b = cli.post(f"{B}/rapido", json={"codigo": "999000111", "data": AMANHA}, headers=h).json()["id"]
    cli.post(f"{B}/rapido", json={"codigo": "7891234567895", "data": HOJE, "client_id": cli.ana}, headers=h)
    h = entra(cli, "ger@urace.us")
    assert cli.post(f"{B}/revisao/{a}/confirmar", json={"modo": "cobrar", "client_id": cli.leo}, headers=h).status_code == 200
    assert cli.post(f"{B}/revisao/{b}/descartar", json={}, headers=h).status_code == 200
    r = cli.get(f"{B}/rapido/auditoria", params={"data": AMANHA}).json()
    assert r["total"] == 2, "a confirmada aparece uma vez só (não duplica com a linha do balcão)"
    por_id = {x["id"]: x for x in r["itens"] if x["origem"] == "celular"}
    assert (por_id[a]["situacao"], por_id[a]["por"], por_id[a]["para"], por_id[a]["revisado_por"]) == \
        ("confirmada", "Mecânico", "Leo Santos", "Gerente")
    assert por_id[b]["situacao"] == "descartada" and por_id[b]["para"] is None
    assert r["pessoas"] == ["Mecânico"]
    assert cli.get(f"{B}/rapido/auditoria", params={"data": HOJE}).json()["total"] == 1


def test_auditoria_inclui_o_balcao_do_computador(cli):  # noqa: F811
    con = conectar()
    from command_center.providers import balcao
    mec = um(con, "SELECT id FROM users WHERE email='mec@urace.us'")["id"]
    s = balcao.lancar(con, cli.ana, cli.para, "guardar", por=mec)
    con.execute("UPDATE counter_scans SET at=? WHERE id=?", (HOJE + "T15:00:00.000Z", s["id"]))   # 11h na Flórida
    con.close()
    r = balcao_rapido.auditoria(conectar(), HOJE)
    x = next(i for i in r["itens"] if i["origem"] == "balcão")
    assert (x["id"], x["por"], x["para"], x["situacao"], x["modo"]) == (s["id"], "Mecânico", "Ana Lima", "lançada", "guardar")


def test_so_o_gerente_ve_a_auditoria(cli):  # noqa: F811
    entra(cli)
    assert cli.get(f"{B}/rapido/auditoria", params={"data": HOJE}).status_code == 403
    entra(cli, "ger@urace.us")
    assert cli.get(f"{B}/rapido/auditoria", params={"data": HOJE}).status_code == 200
    assert cli.get(f"{B}/rapido/auditoria", params={"data": "12/10"}).status_code == 422


def test_qualquer_dia_do_mes(cli):  # noqa: F811
    entra(cli, "ger@urace.us")
    r = cli.get(f"{B}/rapido", params={"data": "2026-09-15"}).json()
    assert r["data"] == "2026-09-15" and r["pilotos"] == []

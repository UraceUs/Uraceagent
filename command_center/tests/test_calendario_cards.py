"""#233: no calendário, a corrida é o card geral com um card de serviço por cliente inscrito;
o treino é o card individual do cliente.

Dono, 14/10: *"corrida é um card de serviço geral com cards de serviços de cada cliente …
um treino é um card de serviço daquele cliente, é individual"*.
"""
import pytest

from command_center.db import aplicar_schema, conectar, inserir
from command_center.providers import checklists

DIA = "2026-10-17"


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def _cliente(con, nome):
    return inserir(con, "clients", name=nome, pilot_name=nome, status="ACTIVE", source="manual")


def test_corrida_traz_um_card_por_cliente_inscrito_e_o_treino_traz_o_cliente(con):
    leo, ana, rui = _cliente(con, "Leo Prado"), _cliente(con, "Ana Lima"), _cliente(con, "Rui Costa")
    corrida = inserir(con, "races", name="ROK Cup USA Round 5", series="ROK", track="Orlando Kart Center",
                      date_start=DIA, date_end="2026-10-18", active=1)
    inserir(con, "race_invites", race_id=corrida, client_id=leo, status="confirmed")
    inserir(con, "race_invites", race_id=corrida, client_id=ana, status="invited")
    inserir(con, "race_invites", race_id=corrida, client_id=rui, status="declined")
    treino = inserir(con, "tasks", title="Ana Lima_Urace Daily [1/1]", client_id=ana, project="U-RACE",
                     section="SATURDAY", status="open", due_on=DIA)

    dias = checklists.periodo(con, DIA, "2026-10-18")["dias"]
    for d in (DIA, "2026-10-18"):                      # a corrida de dois dias aparece nos dois, com os mesmos pilotos
        [c] = dias[d]["corridas"]
        assert c["id"] == corrida
        assert [(p["client_id"], p["piloto"]) for p in c["pilotos"]] == [(ana, "Ana Lima"), (leo, "Leo Prado")], \
            "um card por inscrito (convidado ou confirmado); quem recusou não entra"
    [s] = dias[DIA]["servicos"]
    assert s["id"] == treino and s["client_id"] == ana and s["cliente"] == "Ana Lima", "o treino é o card do cliente"


def test_corrida_sem_inscrito_vem_com_a_lista_vazia(con):
    inserir(con, "races", name="SKUSA Winter Series RD1", series="SKUSA", date_start=DIA, active=1)
    [c] = checklists.periodo(con, DIA, DIA)["dias"][DIA]["corridas"]
    assert c["pilotos"] == []

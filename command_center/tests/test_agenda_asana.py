"""Agendamento do site → tarefa no Asana (#67). Dono, 01/10: *"todo agendamento independente se
esta confirmado ou nao vira uma tarefa no asana"*."""
import os

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from command_center.db import aplicar_schema, conectar, inserir, um  # noqa: E402
from command_center.providers import agenda_asana as aa, contrato, sync, vinculo_site as vs  # noqa: E402
from command_center.tests.test_driver_card import familia  # noqa: E402


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


class Asana:
    def __init__(self, falha=False):
        self.chamadas, self.falha, self.n = [], falha, 0

    def __call__(self, ferramenta, **kw):
        self.chamadas.append((ferramenta, kw))
        if self.falha:
            raise RuntimeError("Asana fora do ar")
        if ferramenta == "asana_criar_tarefa":
            self.n += 1
            return {"aplicado": True, "gid": f"9{self.n:03d}"}
        return {"aplicado": True}


def marca(con, conta, piloto, dia="2026-10-10", status="pendente", periodo="manha"):
    return inserir(con, "bookings", account_id=conta, pilot_id=piloto, date=dia, period=periodo, status=status,
                   service_name="Arrive and Drive", price=719.0, notes="first time")


def test_pendente_vira_tarefa_na_coluna_do_dia_com_o_bloco_da_casa(con):
    enzo, conta, p_enzo, _ = familia(con)
    bid = marca(con, conta, p_enzo)                       # 10/10/2026 é sábado
    asana = Asana()
    assert aa.criar(con, bid, asana) == "9001"
    f, kw = asana.chamadas[0]
    assert f == "asana_criar_tarefa" and kw["secao_gid"] == "1205141832260878" and kw["vence_em"] == "2026-10-10"
    assert kw["nome"].startswith("Enzo Kurian_Arrive and Drive - 2026-10-10 ")
    d = sync.parse_descricao(kw["notas"])
    assert (d["piloto"], d["responsavel"], d["email"], d["nascimento"]) == ("Enzo Kurian", "Joseph Kurian", "joekur001@gmail.com", "2014-03-02")
    assert f"Client ID: {enzo}" in kw["notas"] and "PENDING CONFIRMATION" in kw["notas"]
    t = um(con, """SELECT t.* FROM tasks t JOIN entity_links l ON l.entity_id=t.id AND l.entity_type='task'
                   WHERE l.external_id='9001'""")
    assert t["client_id"] == enzo and t["client_by"] == "human", "aparece no card do driver na hora"
    assert aa.criar(con, bid, asana) == "9001" and len(asana.chamadas) == 1, "uma tarefa só"


def test_confirmada_tambem_vira_tarefa_e_cancelada_antes_nao(con):
    enzo, conta, p_enzo, _ = familia(con)
    marca(con, conta, p_enzo, status="confirmada")
    marca(con, conta, p_enzo, dia="2026-10-11", status="cancelada")
    marca(con, conta, p_enzo, dia="2026-09-20")          # passado: não cria agora
    asana = Asana()
    assert aa.rodar(con, asana, hoje="2026-10-01")["criadas"] == 1


def test_mudanca_de_situacao_comenta_e_marca_o_titulo(con):
    enzo, conta, p_enzo, _ = familia(con)
    bid = marca(con, conta, p_enzo)
    asana = Asana()
    aa.criar(con, bid, asana)
    con.execute("UPDATE bookings SET status='confirmada' WHERE id=?", (bid,))
    assert aa.rodar(con, asana, hoje="2026-10-01")["avisadas"] == 1
    assert asana.chamadas[-1] == ("asana_comentar", {"gid": "9001", "texto": f"Site booking #{bid}: CONFIRMED."})
    con.execute("UPDATE bookings SET status='cancelada', cancelled_by='cliente' WHERE id=?", (bid,))
    aa.rodar(con, asana, hoje="2026-10-01")
    (f1, k1), (f2, k2) = asana.chamadas[-2:]
    assert f1 == "asana_comentar" and "CANCELLED by the client" in k1["texto"]
    assert f2 == "asana_renomear" and k2["nome"].startswith("CANCELLED - Enzo Kurian_")
    assert aa.rodar(con, asana, hoje="2026-10-01") == {"criadas": 0, "avisadas": 0, "falhas": 0}, "nada repetido"


def test_asana_fora_do_ar_nao_perde_o_agendamento_e_tenta_de_novo(con):
    enzo, conta, p_enzo, _ = familia(con)
    bid = marca(con, conta, p_enzo)
    assert aa.rodar(con, Asana(falha=True), hoje="2026-10-01")["falhas"] == 1
    b = um(con, "SELECT * FROM bookings WHERE id=?", (bid,))
    assert b["status"] == "pendente" and "fora do ar" in b["asana_error"] and b["asana_attempts"] == 1
    assert aa.rodar(con, Asana(), hoje="2026-10-01")["criadas"] == 1
    assert um(con, "SELECT asana_error FROM bookings WHERE id=?", (bid,))["asana_error"] is None


def test_contrato_nao_conta_duas_vezes(con):
    enzo, conta, p_enzo, _ = familia(con)
    marca(con, conta, p_enzo, status="confirmada")
    aa.rodar(con, Asana(), hoje="2026-10-01")
    assert contrato.usadas(con, enzo, "2026-10")["total"] == 1, "o agendamento conta; a tarefa dele, não de novo"
    assert vs.historico(con, conta)["services"] == [], "no portal ela já está em Sessions"


def test_tarefa_do_irmao_fica_no_card_do_irmao_mesmo_com_o_email_do_responsavel(con, monkeypatch):
    """A sincronia lia a descrição e ligava pelo e-mail — o primeiro card com joekur001 é o do Enzo."""
    enzo, conta, p_enzo, p_lia = familia(con)
    bid = marca(con, conta, p_lia)
    aa.criar(con, bid, Asana())
    tid = um(con, "SELECT entity_id FROM entity_links WHERE external_id='9001' AND entity_type='task'")["entity_id"]
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (tid,))["client_id"] is None, "a Lia ainda não tem card"

    def asana_sync(sistema, ferramenta, **kw):
        if ferramenta == "asana_secoes":
            return [{"gid": "1205141832260878", "nome": "SATURDAY"}]
        if ferramenta == "asana_tarefas_da_secao":
            return [{"gid": "9001", "nome": "Lia Kurian_Arrive and Drive - 2026-10-10 09:00", "vence_em": "2026-10-10"}]
        raise AssertionError(f"releu a descrição: {ferramenta}")
    monkeypatch.setattr(sync, "chamar", asana_sync)
    sync.sync_asana(con)
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (tid,))["client_id"] is None, "não caiu no card do Enzo"
    lia = vs.criar_cliente_driver(con, p_lia, None)
    aa.rodar(con, Asana(), hoje="2026-10-01")
    assert um(con, "SELECT client_id, client_by FROM tasks WHERE id=?", (tid,)) == {"client_id": lia, "client_by": "human"}
    sync.sync_asana(con)
    assert um(con, "SELECT client_id FROM tasks WHERE id=?", (tid,))["client_id"] == lia


def test_nascimento_da_descricao_vira_data_iso():
    """Havia duas `_data_iso` em sync.py; a segunda (data de e-mail) apagava a primeira, e o
    nascimento lido do Asana nunca virava AAAA-MM-DD — e depois era limpo como inválido."""
    assert sync.parse_descricao("Date of Birth: 03/02/2014")["nascimento"] == "2014-03-02"
    assert sync._data_rfc("Wed, 01 Oct 2026 13:00:00 -0400") == "2026-10-01T17:00:00Z"

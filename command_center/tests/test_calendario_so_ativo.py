"""#227: o calendário nativo mostra só o ativo; o espelho do Asana, só o que existe lá.

Dono, 14/10, com o print de "CANCELLED - Eduardo Fillipe Farias Resende_teste" (Asana: HTTP 404):
*"foram excluídas do Asana, mas precisam ser removidas do calendário ali também … O nosso
calendário, que é o nosso nativo, é para mostrar o que a gente tem de ativo"*.
"""
import pytest

from command_center.db import agora, aplicar_schema, conectar, inserir, todos, um
from command_center.providers import balcao_rapido, checklists, sync

DIA = "2026-10-15"


class _Erro(Exception):
    pass


_Erro.__name__ = "ErroFerramenta"


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def _servico(con, gid, titulo, nome="Eduardo Resende", visto=None):
    cid = inserir(con, "clients", name=nome, pilot_name=nome, status="ACTIVE", source="manual")
    tid, _ = sync._grava_tarefa(con, gid, dict(client_id=cid, title=titulo, project="U-RACE", section="THURSDAY",
                                                status="open", due_on=DIA, synced_at=visto or "2026-10-01T00:00:00Z"))
    return tid, cid


def test_tarefa_excluida_no_asana_sai_do_calendario_do_balcao_e_do_espelho(con, monkeypatch):
    sumida, cid = _servico(con, "G404", "Eduardo Resende_teste [1/1]")
    viva, _ = _servico(con, "G200", "Max Westerpit_Arrive and Drive [1/1]", "Max Westerpit")

    def asana(sistema, ferramenta, gid):
        if gid == "G404":
            raise _Erro('HTTP 404 em GET /tasks/G404: {"errors":[{"message":"Unknown object"}]}')
        return {"gid": gid}
    monkeypatch.setattr(sync, "chamar", asana)
    assert sync.conferir_sumidas(con, agora()) == 1
    t = um(con, "SELECT deleted_at, deleted_by, deleted_reason FROM tasks WHERE id=?", (sumida,))
    assert t["deleted_at"] and t["deleted_by"] is None and t["deleted_reason"] == sync.MOTIVO_ASANA
    assert um(con, "SELECT deleted_at FROM tasks WHERE id=?", (viva,))["deleted_at"] is None, "a que existe fica"
    ids = [s["id"] for s in checklists.meu_dia(con, DIA)["servicos"]]
    assert sumida not in ids and viva in ids
    assert sumida not in [s["id"] for s in checklists.periodo(con, DIA, DIA)["dias"][DIA]["servicos"]]
    assert cid not in [p["client_id"] for p in balcao_rapido.pilotos_do_dia(con, DIA)]
    assert todos(con, "SELECT 1 FROM audit_logs WHERE event='task.deleted' AND entity_id=?", (sumida,)), "fica na auditoria"
    assert um(con, "SELECT 1 AS x FROM tasks WHERE id=?", (sumida,)), "nada é apagado do banco"


def test_erro_que_nao_e_404_nao_decide_nada(con, monkeypatch):
    tid, _ = _servico(con, "G500", "Ana Lima_Academy [1/2]", "Ana Lima")

    def asana(sistema, ferramenta, gid):
        raise _Erro("sem conexão com o Asana: timed out")
    monkeypatch.setattr(sync, "chamar", asana)
    assert sync.conferir_sumidas(con, agora()) == 0
    assert um(con, "SELECT deleted_at FROM tasks WHERE id=?", (tid,))["deleted_at"] is None


def test_so_confere_o_que_nao_apareceu_nesta_varredura(con, monkeypatch):
    inicio = agora()
    _servico(con, "GVISTA", "Rui Costa_Academy [1/1]", "Rui Costa", visto=agora())
    chamadas = []
    monkeypatch.setattr(sync, "chamar", lambda *a, **k: chamadas.append(k) or {})
    sync.conferir_sumidas(con, inicio)
    assert not chamadas, "tarefa vista na varredura não gasta chamada ao Asana"


@pytest.mark.parametrize("titulo", ["CANCELLED - Eduardo Fillipe Farias Resende_teste - 2026-10-15 09:00",
                                    "[Canceled] Erik Mangoza Jr_Karting School [4/4]", "Canceled - Max Westerpit"])
def test_cancelada_nao_ocupa_o_calendario_nem_o_balcao(con, titulo):
    tid, cid = _servico(con, "GC" + str(abs(hash(titulo)) % 10000), titulo)
    assert tid not in [s["id"] for s in checklists.meu_dia(con, DIA)["servicos"]]
    assert tid not in [s["id"] for s in checklists.periodo(con, DIA, DIA)["dias"][DIA]["servicos"]]
    assert cid not in [p["client_id"] for p in balcao_rapido.pilotos_do_dia(con, DIA)]


def test_espelho_do_asana_nao_mostra_o_que_foi_excluido_la(con):
    from command_center.api import rotas
    la, _ = _servico(con, "GLA", "Bia Reis_Academy [1/1]", "Bia Reis")
    aqui, _ = _servico(con, "GAQUI", "Lia Souza_Academy [1/1]", "Lia Souza")
    con.execute("UPDATE tasks SET deleted_at=?, deleted_reason=? WHERE id=?", (agora(), sync.MOTIVO_ASANA, la))
    con.execute("UPDATE tasks SET deleted_at=?, deleted_reason='duplicado' WHERE id=?", (agora(), aqui))
    ids = [t["id"] for t in rotas.tasks(status="all", project=None, u={}, con=con)]
    assert la not in ids, "não existe mais no Asana: o espelho não mostra"
    assert aqui in ids, "excluída só no painel (#219) ainda existe no Asana: o espelho mostra"

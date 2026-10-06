"""Precisa de atenção: o que já passou some sozinho (dono, 06/10).

"Se algo passou já — venceu no dia 26, 27 — esses aí já oculta automaticamente.
Os futuros ficam ali mostrando."
"""
import os
from datetime import date, timedelta

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from command_center.api import atencao  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir  # noqa: E402

SEM_CREDITO = ("O modelo da IA (conta Anthropic usada pelo OpenClaw) está sem crédito ou fora da cota. "
               "O painel, a sincronia e as regras continuam; só o que depende da IA espera. Reponha o crédito.")


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def _dia(n):
    return (date.today() + timedelta(days=n)).isoformat()


def _cenario(con):
    cid = inserir(con, "clients", name="Piloto Teste", email="p@example.com", vip=0, status="ACTIVE", source="asana")
    uid = con.execute("INSERT INTO users (email, name, role, pw_salt, pw_hash) VALUES ('a@urace.us','A','ADMIN','x','x')").lastrowid
    vencida = inserir(con, "tasks", client_id=cid, title="Piloto Teste_Arrive and Drive", project="U-RACE", section="SATURDAY",
                      status="open", due_on=_dia(-9))
    cmd = inserir(con, "ai_commands", user_id=uid, text="t", session_key="s", status="FAILED", error=SEM_CREDITO,
                  finished_at="2026-09-28T10:00:00.000Z")
    inserir(con, "ai_events", kind="task.overdue", entity_type="task", entity_id=vencida, client_id=cid, summary="x",
            status="FAILED", command_id=cmd)
    futura = inserir(con, "tasks", client_id=cid, title="Piloto Teste_Academy", project="U-RACE", section="FRIDAY",
                     status="open", due_on=_dia(3))
    inv = inserir(con, "invoices", client_id=cid, doc_number="1077", amount=219, balance=219, status="overdue",
                  issued_on=_dia(-60), due_on=_dia(-45), memo="Storage Fee")
    w_expirou = inserir(con, "waivers", client_id=cid, signer_name="Expirou", signer_email="e@example.com", status="sent",
                        expires_at=_dia(-2))
    w_expira = inserir(con, "waivers", client_id=cid, signer_name="Expira", signer_email="f@example.com", status="sent",
                       expires_at=_dia(5))
    con.commit()
    return dict(vencida=vencida, futura=futura, inv=inv, w_expirou=w_expirou, w_expira=w_expira)


def test_o_que_passou_some_e_o_futuro_fica(con):
    ids = _cenario(con)
    chaves = {i["key"] for i in atencao.coletar(con)}
    assert f"tarefa-vencida:task:{ids['vencida']}" not in chaves           # venceu há 9 dias: some
    assert f"waiver-expira:waiver:{ids['w_expirou']}" not in chaves        # já expirou: some
    assert f"waiver-servico:task:{ids['futura']}" in chaves                # serviço daqui a 3 dias: fica
    assert f"waiver-expira:waiver:{ids['w_expira']}" in chaves             # expira daqui a 5 dias: fica
    # invoice vencida é dinheiro a receber, não data que passou: continua (D-2026-08-31, "não some")
    assert f"invoice-vencida:invoice:{ids['inv']}" in chaves


def test_o_que_passou_continua_em_mostrar_ocultos(con):
    ids = _cenario(con)
    todos = {i["key"]: i for i in atencao.coletar(con, incluir_ocultos=True)}
    t = todos[f"tarefa-vencida:task:{ids['vencida']}"]
    assert t["dismissed"] == {"by": None, "at": None, "reason": "a data já passou", "auto": True}
    w = todos[f"waiver-expira:waiver:{ids['w_expirou']}"]
    assert w["dismissed"]["auto"] is True and "expirou em" in w["title"] and "-2" not in w["title"]
    assert todos[f"waiver-servico:task:{ids['futura']}"]["dismissed"] is None
    assert "auto_oculto" not in t                                          # detalhe interno não vaza na API


def test_ocultado_por_gente_continua_valendo(con):
    ids = _cenario(con)
    chave = f"waiver-servico:task:{ids['futura']}"
    con.execute("INSERT INTO attention_dismissals (key, title, reason, dismissed_by) VALUES (?, 'x', 'já falei com ele', (SELECT id FROM users LIMIT 1))", (chave,))
    assert chave not in {i["key"] for i in atencao.coletar(con)}
    d = {i["key"]: i for i in atencao.coletar(con, incluir_ocultos=True)}[chave]["dismissed"]
    assert d["auto"] is False and d["reason"] == "já falei com ele"


def test_resposta_da_ia_cortada_numa_palavra():
    """O aviso mostrava "só o que depende da IA esper" — cortado no meio da palavra."""
    curto = atencao._corta(SEM_CREDITO, 160)
    assert len(curto) <= 161 and curto.endswith("…")
    assert curto[:-1] == SEM_CREDITO[:len(curto) - 1] and SEM_CREDITO[len(curto) - 1] in " ,;:."
    assert atencao._corta("frase curta", 160) == "frase curta"

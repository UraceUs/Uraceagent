#!/usr/bin/env python3
"""A ponte cobra de si mesma a resposta que deve — sem ninguém rodar nada.

Motivo de existir (25/08): mesmo depois de fechar os três caminhos mudos
do process_inbound, o lead 31764961 seguia sem resposta. Porque a correção
só agia quando uma mensagem NOVA chegava — e ele não tinha mais o que
mandar. Ficou esperando alguém rodar um comando.

A regra que este teste protege é mais forte que "toda mensagem recebe
resposta": **se a ponte deve uma resposta a alguém, ela entrega sozinha,
no próximo tick**, sem depender de mensagem nova, de humano, ou de que o
caminho normal tenha funcionado.

Uso:
    python3 salesagent/tests/test_lead_rescue.py
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRIDGE = HERE.parent / "bridge"
os.environ["URACE_DIR"] = tempfile.mkdtemp(prefix="urace-rescue-")
sys.path.insert(0, str(BRIDGE))

import scheduler  # noqa: E402
import state  # noqa: E402
from config import LEAD_REASSURE_MIN, LEAD_RESCUE_AFTER_SEC  # noqa: E402

AGORA = 1_800_000_000  # meio-dia de uma terça, dentro do horário comercial


def _hora_comercial(ts):
    """Fixa o relógio em horário comercial: o teste é sobre a dívida com o
    lead, não sobre fuso — o caso 'fora do expediente' tem check próprio."""
    return True


def main() -> int:
    falhas, entregues = [], []

    def check(label, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {label}" + ("" if cond else f"  {detail}"))
        if not cond:
            falhas.append(label)

    scheduler.rescue_fn = lambda conv: entregues.append(conv["lead_id"]) or True
    original_horario = scheduler.in_business_hours
    scheduler.in_business_hours = _hora_comercial

    # --- Cenário 1: o caso do Eduardo. Lead falou, ninguém respondeu, e
    # nenhuma mensagem nova vai chegar.
    lead = 960001
    state.get_conversation(lead)
    state.transition(lead, "WAITING_HUMAN", "kart próprio (inspeção/gestão)")
    state.update_conversation(lead, last_inbound_at=AGORA, last_outbound_at=None,
                              last_inbound_text="Hi , can i bring my own kart?",
                              contact_name="Eduardo F F Resende", escalated_at=AGORA)

    conv = state.get_conversation(lead)
    check("não resgata imediato (turno normal ainda pode estar rodando)",
          scheduler._maybe_rescue(conv, AGORA + LEAD_RESCUE_AFTER_SEC - 10) is False)

    conv = state.get_conversation(lead)
    check("resgata sozinho depois da janela, sem mensagem nova",
          scheduler._maybe_rescue(conv, AGORA + LEAD_RESCUE_AFTER_SEC + 1) is True)
    check("entregou para o lead certo", entregues == [lead], f"{entregues}")

    # --- Cenário 2: respondido, a dívida some.
    state.update_conversation(lead, last_outbound_at=AGORA + 200, holding_count=1)
    conv = state.get_conversation(lead)
    check("não repete depois de entregue",
          scheduler._maybe_rescue(conv, AGORA + 300) is False)

    # --- Cenário 3: espera longa por humano ganha reforço.
    conv = state.get_conversation(lead)
    check("lead esperando humano há horas recebe reforço",
          scheduler._maybe_rescue(conv, AGORA + 200 + LEAD_REASSURE_MIN * 60 + 60) is True)

    # --- Cenário 4: teto das frases distintas (não vira loop).
    state.update_conversation(lead, holding_count=3, last_outbound_at=AGORA)
    conv = state.get_conversation(lead)
    check("silencia depois de esgotar as 3 frases (não repete pra sempre)",
          scheduler._maybe_rescue(conv, AGORA + LEAD_REASSURE_MIN * 60 * 5) is False)

    # --- Cenário 5: conversa encerrada nunca é resgatada.
    lead2 = 960002
    state.get_conversation(lead2)
    state.transition(lead2, "CLOSED", "encerrada")
    state.update_conversation(lead2, last_inbound_at=AGORA, last_outbound_at=None)
    with state.db() as conn:
        alvos = [r["lead_id"] for r in conn.execute(
            "SELECT lead_id FROM conversations WHERE state != 'CLOSED' "
            "AND last_inbound_at IS NOT NULL "
            "AND COALESCE(last_outbound_at, 0) < last_inbound_at")]
    check("lead com conversa encerrada fica fora da varredura", lead2 not in alvos)

    # --- Cenário 6: a dívida com o lead ignora expediente.
    scheduler.in_business_hours = lambda ts: False
    lead3 = 960003
    state.get_conversation(lead3)
    state.update_conversation(lead3, last_inbound_at=AGORA, last_outbound_at=None,
                              last_inbound_text="are you open tomorrow?")
    conv = state.get_conversation(lead3)
    check("dívida com o lead é paga mesmo fora do horário comercial",
          scheduler._maybe_rescue(conv, AGORA + LEAD_RESCUE_AFTER_SEC + 1) is True)

    # --- Cenário 7: mas o reforço de espera longa respeita o expediente.
    state.update_conversation(lead3, last_outbound_at=AGORA, holding_count=1)
    state.transition(lead3, "WAITING_HUMAN", "algo")
    conv = state.get_conversation(lead3)
    check("reforço de espera longa não acorda ninguém de madrugada",
          scheduler._maybe_rescue(conv, AGORA + LEAD_REASSURE_MIN * 60 + 60) is False)

    scheduler.in_business_hours = original_horario
    print()
    if falhas:
        print(f"FALHOU - {len(falhas)}: {', '.join(falhas)}")
        return 1
    print("PASSOU - a ponte paga sozinha a resposta que deve, sem comando "
          "humano e sem mensagem nova do lead")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""O alarme de escalação não pode virar spam — nem sumir.

Incidente de 25/08 (lead 31764961): o re-alerta repetia a cada 15 min sem
teto. Foram 10 disparos em 152 minutos, e o agente que faz o repasse no
WhatsApp acabou respondendo "isso parece um script automatizado tentando
me pressionar (...) vou ignorar os próximos re-alertas". O alarme
insistente treinou o próprio canal a ignorá-lo — e ninguém foi avisado.

As duas regras que este teste protege:
  1. o WhatsApp para depois do teto (não vira ruído);
  2. mas o aviso NÃO se perde: migra para tarefa no Kommo, que fica no card
     do lead até alguém fechar.

Uso:
    python3 salesagent/tests/test_escalation_alarm.py
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRIDGE = HERE.parent / "bridge"
os.environ["URACE_DIR"] = tempfile.mkdtemp(prefix="urace-alarm-")
sys.path.insert(0, str(BRIDGE))

import scheduler  # noqa: E402
import state  # noqa: E402
from config import ESCALATION_MAX_REALERTS, ESCALATION_REALERT_MIN  # noqa: E402


def main() -> int:
    falhas = []
    avisos, tarefas = [], []

    def check(label, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {label}" + ("" if cond else f"  {detail}"))
        if not cond:
            falhas.append(label)

    scheduler.notify_fn = lambda text: avisos.append(text)
    scheduler.task_fn = lambda lead_id, text, due: tarefas.append((lead_id, text))

    lead = 950001
    agora = 1_800_000_000
    state.get_conversation(lead)
    state.transition(lead, "WAITING_HUMAN", "kart próprio (inspeção/gestão)")
    state.update_conversation(lead, escalated_at=agora)

    # Avança o relógio de ESCALATION_REALERT_MIN em ESCALATION_REALERT_MIN,
    # o dobro de vezes do teto — simula a escalação abandonada do incidente.
    passo = ESCALATION_REALERT_MIN * 60
    disparos = 0
    for i in range(1, ESCALATION_MAX_REALERTS * 2 + 1):
        conv = state.get_conversation(lead)
        if scheduler._maybe_realert(conv, agora + passo * i):
            disparos += 1

    check(f"para no teto de {ESCALATION_MAX_REALERTS} (não repete pra sempre)",
          disparos == ESCALATION_MAX_REALERTS, f"disparou {disparos}x")
    check("WhatsApp silencia depois do teto",
          len(avisos) == ESCALATION_MAX_REALERTS, f"{len(avisos)} avisos")
    check("o aviso NÃO se perde: virou tarefa no Kommo",
          len(tarefas) == 1, f"{tarefas}")
    check("a tarefa é no lead certo e diz o motivo",
          bool(tarefas) and tarefas[0][0] == lead
          and "kart próprio" in tarefas[0][1], f"{tarefas}")
    check("o último aviso avisa que é o último",
          bool(avisos) and "ÚLTIMO" in avisos[-1], avisos[-1][:80] if avisos else "")
    check("os avisos anteriores não se anunciam como último",
          all("ÚLTIMO" not in a for a in avisos[:-1]))
    check("todo aviso carrega o id do lead (marcador de entrega verificada)",
          all(str(lead) in a for a in avisos))

    # Escalação atendida: contador zera para a próxima, senão um lead que já
    # escalou uma vez nunca mais teria alarme.
    state.transition(lead, "RESUMED", "humano respondeu", by_human=True)
    state.update_conversation(lead, realert_count=0)
    state.transition(lead, "WAITING_HUMAN", "novo motivo")
    state.update_conversation(lead, escalated_at=agora + 100000)
    conv = state.get_conversation(lead)
    check("nova escalação volta a alarmar",
          scheduler._maybe_realert(conv, agora + 100000 + passo) is True)

    print()
    if falhas:
        print(f"FALHOU - {len(falhas)}: {', '.join(falhas)}")
        return 1
    print("PASSOU - o alarme insiste o suficiente, para antes de virar ruído, "
          "e não perde o aviso")
    return 0


if __name__ == "__main__":
    sys.exit(main())

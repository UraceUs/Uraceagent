#!/usr/bin/env python3
"""Regressão do incidente de 25/08: o lead que pergunta e não recebe nada.

Este teste roda a PONTE inteira (process_inbound) de ponta a ponta, sem
tocar em OpenClaw, Kommo ou rede -- diferente de run_scenarios.py, que
testa o modelo real. É o nível certo para a regra que estamos protegendo,
porque a regra é da ponte, não do modelo:

    toda mensagem de lead produz uma mensagem de volta.

O incidente: lead 31764961 mandou "Hi, can i bring my own kart?", o
gatilho B4 escalou corretamente, e o `return` logo depois deixou o lead
sem uma linha sequer. O log daquele dia tem `inbound` e `transition` sem
nenhum `outbound`. Os três caminhos mudos estão cobertos aqui.

Uso:
    python3 salesagent/tests/test_never_silent.py
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRIDGE_DIR = HERE.parent / "bridge"

# URACE_DIR isolado ANTES de importar config: banco e segredos vão para um
# temporário descartável -- o teste nunca toca no estado real do VPS.
_TMP = tempfile.mkdtemp(prefix="urace-test-")
os.environ["URACE_DIR"] = _TMP
sys.path.insert(0, str(BRIDGE_DIR))

import app  # noqa: E402
import state  # noqa: E402
import textproc  # noqa: E402


class _FakeKommo:
    """Kommo sem rede: registra o que teria sido enviado."""

    def __init__(self):
        self.notes, self.tags, self.tasks, self.stages = [], [], [], []

    def add_note(self, lead_id, text):
        self.notes.append((lead_id, text))

    def add_tags(self, lead_id, tags):
        self.tags.append((lead_id, tags))

    def add_task(self, lead_id, text, due=None):
        self.tasks.append((lead_id, text, due))

    def set_stage(self, lead_id, stage_id):
        self.stages.append((lead_id, stage_id))


def _install_fakes(agent_reply=""):
    """Substitui tudo que sai da máquina. Devolve a lista de mensagens
    entregues ao lead (o que estamos de fato testando)."""
    delivered = []
    app.kommo = _FakeKommo()
    app.send_to_lead = lambda lead_id, text: delivered.append((lead_id, text))
    app.notify_human = lambda text: None
    # Espelha o _call_agent real: extrai as diretivas do texto bruto com a
    # MESMA função da produção -- um fake que devolvesse [] estaria testando
    # um agente que nunca emite diretiva, ou seja, nada.
    app._call_agent = lambda lead_id, message: (
        agent_reply, textproc.extract_directives(agent_reply))
    app.scheduler.cancel = lambda lead_id, reason="": None
    app.scheduler.start_track = lambda lead_id, track: None
    return delivered


def main() -> int:
    failures = []
    lead = 900001

    def check(label, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {label}" + ("" if cond else f"  {detail}"))
        if not cond:
            failures.append(label)

    # 1. O caso exato do Eduardo: gatilho B4 em conversa nova.
    delivered = _install_fakes()
    app.process_inbound({"lead_id": lead, "message": "Hi , can i bring my own kart?"})
    check("gatilho B4 responde o lead (incidente 25/08)", len(delivered) == 1,
          f"entregues={delivered}")
    check("gatilho B4 continua escalando",
          state.get_conversation(lead)["state"] == "WAITING_HUMAN",
          state.get_conversation(lead)["state"])
    check("a resposta não é vazia", bool(delivered and delivered[0][1].strip()))
    check("a resposta não promete resposta comercial",
          bool(delivered) and "$" not in delivered[0][1])

    # 2. Mensagem seguinte, já em estado escalado (G3): antes, silêncio total.
    delivered2 = _install_fakes()
    app.process_inbound({"lead_id": lead, "message": "hello? are you there?"})
    check("mensagem em conversa escalada também é respondida (G3)",
          len(delivered2) == 1, f"entregues={delivered2}")
    check("segunda espera usa frase diferente da primeira",
          bool(delivered and delivered2) and delivered[0][1] != delivered2[0][1],
          f"{delivered!r} vs {delivered2!r}")
    check("estado escalado preservado (G3 intacto)",
          state.get_conversation(lead)["state"] == "WAITING_HUMAN")

    # 3. Agente fora do ar / resposta vazia, em conversa saudável.
    lead2 = 900002
    delivered3 = _install_fakes(agent_reply="")
    app.process_inbound({"lead_id": lead2, "message": "how do i sign up?"})
    check("agente vazio não vira silêncio", len(delivered3) == 1,
          f"entregues={delivered3}")

    # 4. Caminho feliz continua igual: quem responde é o agente, não a espera.
    lead3 = 900003
    delivered4 = _install_fakes(agent_reply="Welcome to URACE! Have you raced before?")
    app.process_inbound({"lead_id": lead3, "message": "hi, i want to learn karting"})
    check("caminho normal entrega a resposta do agente",
          len(delivered4) == 1 and "URACE" in delivered4[0][1], f"{delivered4}")

    # 5. Idioma do lead é respeitado na espera.
    lead4 = 900004
    delivered5 = _install_fakes()
    app.process_inbound({"lead_id": lead4, "message": "posso levar meu kart próprio?"})
    check("espera responde no idioma do lead (pt)",
          bool(delivered5) and any(w in delivered5[0][1].lower()
                                   for w in ("equipe", "confirmar", "resposta")),
          f"{delivered5}")

    # 6. [[unknown]]: o agente declara que não sabe -> a ponte escala
    #    SOZINHA (não depende de ele lembrar de mandar [[escalate]] junto)
    #    e o lead recebe a mensagem do agente, não silêncio.
    lead5 = 900005
    delivered6 = _install_fakes(
        agent_reply="Let me confirm that with our team and come right back to "
                    "you.\n[[unknown question=\"do you rent helmets?\" found=\"nada\"]]")
    app.process_inbound({"lead_id": lead5, "message": "do you rent helmets?"})
    check("[[unknown]] escala sem [[escalate]] junto",
          state.get_conversation(lead5)["state"] == "WAITING_HUMAN",
          state.get_conversation(lead5)["state"])
    check("[[unknown]] ainda responde o lead", len(delivered6) == 1, f"{delivered6}")
    check("a diretiva não vaza para o lead",
          bool(delivered6) and "[[" not in delivered6[0][1], f"{delivered6}")

    # 7. O motivo da escalação chega útil para o humano (§7 do brief).
    razao = state.get_conversation(lead5)["escalation_reason"] or ""
    check("escalação de [[unknown]] carrega a pergunta do lead",
          "helmet" in razao.lower(), razao)

    print()
    if failures:
        print(f"FALHOU - {len(failures)} checagem(ns): {', '.join(failures)}")
        return 1
    print("PASSOU - nenhum caminho da ponte deixa o lead sem resposta, "
          "e o agente tem como dizer 'não sei' sem sumir")
    return 0


if __name__ == "__main__":
    sys.exit(main())

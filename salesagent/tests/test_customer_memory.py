#!/usr/bin/env python3
"""Memória estruturada por cliente — o lead nunca repete, o Chase nunca esquece.

Cobre os itens 6, 7, 9, 10 e 13 do brief de finalização (27/08):
memória por cliente sobrevivendo a dias de intervalo, resposta humana
virando fato confirmado injetado em todo turno, próxima ação comercial
deduzida do estado, e isolamento entre leads simultâneos.

O gap real que motivou isto: o Italo respondia a escalação, o lead recebia
a resposta — e a SESSÃO do Chase nunca ficava sabendo, porque a entrega ia
por fora dela. O cliente voltava e o Chase seguia sem saber o que a própria
equipe tinha prometido.

Uso:
    python3 salesagent/tests/test_customer_memory.py
"""
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRIDGE = HERE.parent / "bridge"
os.environ["URACE_DIR"] = tempfile.mkdtemp(prefix="urace-mem-")
sys.path.insert(0, str(BRIDGE))

import app  # noqa: E402
import brain_kb  # noqa: E402
import knowledge_writer  # noqa: E402
import state  # noqa: E402
import textproc  # noqa: E402

knowledge_writer.LEARNINGS_DIR = Path(os.environ["URACE_DIR"]) / "vault-teste"


class _Req:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


class _FakeKommo:
    def __init__(self):
        self.notes = []

    def add_note(self, lead_id, text):
        self.notes.append((lead_id, text))

    def add_tags(self, lead_id, tags):
        pass

    def add_task(self, lead_id, text, due=None):
        pass


def main() -> int:
    falhas = []

    def check(label, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {label}" + ("" if cond else f"  {detail}"))
        if not cond:
            falhas.append(label)

    # ambiente: retrieval ligado, busca vazia (o foco é a MEMÓRIA), agente
    # capturando o que recebe.
    recebido = []
    entregues = []
    app.kommo = _FakeKommo()
    app.BRAIN_RETRIEVAL = "on"
    brain_kb.search = lambda *a, **k: []
    app.send_to_lead = lambda lead_id, text: entregues.append((lead_id, text))
    app.notify_human = lambda text: None
    app.deliver_followup = lambda lead_id, texto: entregues.append((lead_id, texto)) or True
    app.scheduler.cancel = lambda *a, **k: None
    app.scheduler.start_track = lambda *a, **k: None
    app._auth = lambda k: None
    app._auth_human_reply = lambda k: None

    def agente(resposta):
        def fake(lead_id, message):
            recebido.append(message)
            return resposta, textproc.extract_directives(resposta)
        app._call_agent = fake

    italo = app.HUMAN_WHATSAPP_LIST[0]
    lead = 980001

    # --- 1. Lead novo: memória vazia mas estruturada, próxima ação = classificar
    agente("Hi Carlos, this is Chase...")
    app.process_inbound({"lead_id": lead, "message": "hi, i want to race",
                         "contact_name": "Carlos Souza"})
    check("todo turno recebe memória estruturada", "Memória do lead" in recebido[-1],
          recebido[-1][:200])
    check("lead novo => próxima ação é classificar",
          "classificação A/B/C/D" in recebido[-1], recebido[-1][-200:])
    check("nome do lead na memória", "Carlos" in recebido[-1])

    # --- 2. Escala (kart próprio) e o humano responde pelo WhatsApp
    app.process_inbound({"lead_id": lead, "message": "can i bring my own kart?"})
    check("escalou", state.get_conversation(lead)["state"] == "WAITING_HUMAN")
    brief = f"🔺 ESCALAÇÃO — Carlos Souza (lead {lead})"
    r = asyncio.run(app.human_whatsapp(
        _Req({"from": italo, "text": "pode trazer sim, inspecionamos 1 dia antes",
              "quoted": brief}), x_api_key=None))
    check("resposta humana entregue ao lead", any("inspecionamos" in t for _, t in entregues))
    check("conversa devolvida ao Chase", state.get_conversation(lead)["state"] == "RESUMED")
    confirmadas = state.get_confirmations(lead)
    check("resposta virou fato confirmado do CLIENTE (§7)",
          len(confirmadas) == 1 and "inspecionamos" in confirmadas[0]["answer"],
          str(confirmadas))
    check("o fato guarda a pergunta original",
          "own kart" in (confirmadas[0].get("question") or ""), str(confirmadas))

    # --- 3. Lead volta DIAS depois: o fato confirmado entra no contexto
    with state.db() as conn:  # simula o intervalo: 4 dias atrás
        conn.execute("UPDATE conversations SET last_inbound_at=? WHERE lead_id=?",
                     (int(time.time()) - 4 * 86400, lead))
    agente("Great! As we confirmed, you can bring your kart - we inspect it "
           "the day before. Ready to move forward?")
    app.process_inbound({"lead_id": lead, "message": "hey, about that kart thing again"})
    check("4 dias depois, o fato confirmado está no contexto do turno",
          "inspecionamos" in recebido[-1], recebido[-1][:400])
    check("o contexto manda AFIRMAR (não re-perguntar)",
          "pode afirmar como fato" in recebido[-1])
    check("quem confirmou aparece", "Italo" in recebido[-1])

    # --- 4. Próxima ação evolui com o estado
    state.update_conversation(lead, q_experience="rental_only")
    conv = state.get_conversation(lead)
    check("classificado sem idade => próxima ação é idade",
          "idade" in app._next_action(conv), app._next_action(conv))
    state.update_conversation(lead, driver_age=15)
    conv = state.get_conversation(lead)
    check("qualificado => próxima ação é recomendar/fechar",
          "[[price]]" in app._next_action(conv), app._next_action(conv))
    state.update_conversation(lead, followup_track="link_sent")
    conv = state.get_conversation(lead)
    check("link enviado => próxima ação é fechamento, não reenvio",
          "fechamento" in app._next_action(conv), app._next_action(conv))

    # --- 5. Dois leads simultâneos: memórias isoladas
    lead2 = 980002
    state.get_conversation(lead2)
    agente("Hello!")
    app.process_inbound({"lead_id": lead2, "message": "hello, do you have classes?",
                         "contact_name": "Maria Lima"})
    check("lead 2 NÃO herda os fatos do lead 1",
          "inspecionamos" not in recebido[-1], recebido[-1][:300])
    check("lead 2 tem a própria identidade", "Maria" in recebido[-1])
    check("confirmações do lead 1 intactas", len(state.get_confirmations(lead)) == 1)
    check("lead 2 sem confirmações", state.get_confirmations(lead2) == [])

    print()
    if falhas:
        print(f"FALHOU - {len(falhas)}: {', '.join(falhas)}")
        return 1
    print("PASSOU - memória por cliente sobrevive ao tempo, resposta humana "
          "vira fato do lead, e leads não se contaminam")
    return 0


if __name__ == "__main__":
    sys.exit(main())

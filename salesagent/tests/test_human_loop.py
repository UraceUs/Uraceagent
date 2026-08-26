#!/usr/bin/env python3
"""A decisão do humano no WhatsApp vira ação — e só de quem tem autoridade.

Contexto (26/08): a escalação chegava no WhatsApp pedindo "responda
'aprovar <lead> ...'", o Italo respondeu "aprovado", e nada aconteceu —
não existia quem lesse. Este teste cobre o caminho inteiro do endpoint
/human/whatsapp, sem rede: quem pode decidir, o que a ponte faz com a
decisão, e o que ela recusa a fazer.

Uso:
    python3 salesagent/tests/test_human_loop.py
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRIDGE = HERE.parent / "bridge"
os.environ["URACE_DIR"] = tempfile.mkdtemp(prefix="urace-loop-")
sys.path.insert(0, str(BRIDGE))

import app  # noqa: E402
import knowledge_writer  # noqa: E402
import state  # noqa: E402

# BLINDAGEM: o vault de teste é temporário, apontado antes de qualquer
# chamada. Numa versão anterior deste arquivo o teste gravou um documento
# de verdade em brain/09_LEARNINGS/ (lead fictício 970001, confirmado por
# "Italo Silveira") -- conhecimento inventado por um teste, esperando
# revisão humana no vault real. Isso não pode depender de lembrarmos de
# mockar a função certa.
knowledge_writer.LEARNINGS_DIR = Path(os.environ["URACE_DIR"]) / "vault-teste"


class _Req:
    """Request mínimo do FastAPI: o endpoint só chama .json()."""

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


def chamar(numero, texto):
    return asyncio.run(app.human_whatsapp(
        _Req({"from": numero, "text": texto}), x_api_key=app.AGENT_API_KEY))


def main() -> int:
    falhas, entregues = [], []

    def check(label, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {label}" + ("" if cond else f"  {detail}"))
        if not cond:
            falhas.append(label)

    app.kommo = _FakeKommo()
    app.deliver_followup = lambda lead_id, texto: (
        entregues.append((lead_id, texto)) or True)
    # Autenticação da ponte é testada noutro lugar; aqui o foco é a
    # autoridade do OPERADOR, que é uma trava diferente e mais importante.
    app._auth = lambda k: None

    numeros = app.HUMAN_WHATSAPP_LIST
    if not numeros:
        print("HUMAN_WHATSAPP_LIST vazia — nada a testar")
        return 2
    italo = numeros[0]

    lead = 970001
    state.get_conversation(lead)
    state.update_conversation(lead, contact_name="Eduardo F F Resende")
    state.transition(lead, "WAITING_HUMAN", "kart próprio (inspeção/gestão)")

    # --- número desconhecido não decide nada
    r = chamar("+5511999999999", "aprovar 970001 pode trazer")
    check("número não autorizado é recusado", r["ok"] is False, str(r))
    check("estado intacto depois da recusa",
          state.get_conversation(lead)["state"] == "WAITING_HUMAN")
    check("nada foi entregue ao lead", entregues == [], str(entregues))

    # --- operador responde com texto: chega no lead e volta pro agente
    r = chamar(italo, "aprovar 970001 pode trazer o kart, inspecionamos antes")
    check("operador autorizado é aceito", r["ok"] is True, str(r))
    check("a resposta chegou ao lead",
          len(entregues) == 1 and "inspecionamos antes" in entregues[0][1],
          str(entregues))
    check("conversa devolvida ao Chase",
          state.get_conversation(lead)["state"] == "RESUMED",
          state.get_conversation(lead)["state"])
    check("o retorno cita o lead pelo nome", "Eduardo" in r["reply"], r["reply"])
    check("alarme zerado ao atender",
          (state.get_conversation(lead).get("realert_count") or 0) == 0)

    # --- 'aprovado' seco com UM lead esperando: usa esse, sem inventar texto
    lead2 = 970002
    state.get_conversation(lead2)
    state.update_conversation(lead2, contact_name="Maria")
    state.transition(lead2, "WAITING_HUMAN", "pedido de desconto")
    entregues.clear()
    r = chamar(italo, "aprovado")
    check("'aprovado' seco resolve o único lead esperando", r["ok"] is True, str(r))
    check("sem texto ditado, nada é inventado para o lead",
          entregues == [], str(entregues))
    check("o retorno explica como ditar um texto",
          "aprovar 970002" in r["reply"], r["reply"])

    # --- dois leads esperando: pergunta, não adivinha
    for lid, nome in ((970003, "Ana"), (970004, "João")):
        state.get_conversation(lid)
        state.update_conversation(lid, contact_name=nome)
        state.transition(lid, "WAITING_HUMAN", "motivo x")
    entregues.clear()
    r = chamar(italo, "aprovado")
    check("com 2+ leads esperando, pergunta qual", r["ok"] is False, str(r))
    check("a pergunta lista os candidatos pelo nome",
          "Ana" in r["reply"] and "João" in r["reply"], r["reply"])
    check("não agiu em nenhum deles", entregues == [], str(entregues))

    # --- 'não salvar' não mexe em lead nenhum
    entregues.clear()
    r = chamar(italo, "não salvar isso no brain")
    check("'não salvar' é respeitado sem tocar em lead",
          r["ok"] is True and entregues == [], str(r))

    # --- a resposta vira conhecimento pendente de revisão (§9)
    escritos = []
    knowledge_writer.registrar = lambda **kw: (
        escritos.append(kw) or {"written": True, "path": "/tmp/x.md",
                                "kind": "knowledge", "reason": "ok"})
    knowledge_writer.reindexar = lambda: True
    app.knowledge_writer = knowledge_writer

    lead5 = 970005
    state.get_conversation(lead5)
    state.update_conversation(lead5, contact_name="Carlos",
                              last_inbound_text="can i bring my own kart?")
    state.transition(lead5, "WAITING_HUMAN", "kart próprio")
    r = chamar(italo, "aprovar 970005 pode trazer, inspecionamos 1 dia antes")
    check("resposta humana vira candidato no Brain", len(escritos) == 1, str(escritos))
    check("o candidato guarda a pergunta original do lead",
          bool(escritos) and "own kart" in escritos[0]["pergunta"], str(escritos))
    check("o candidato guarda quem confirmou",
          bool(escritos) and escritos[0]["autor"], str(escritos))
    check("o operador é avisado que precisa revisar",
          "Obsidian" in r["reply"] or "revisão" in r["reply"], r["reply"])

    # --- 'não salvar' não escreve nada no Brain
    escritos.clear()
    lead6 = 970006
    state.get_conversation(lead6)
    state.transition(lead6, "WAITING_HUMAN", "x")
    chamar(italo, "não salvar isso")
    check("'não salvar' não escreve no Brain", escritos == [], str(escritos))

    # --- fechar encerra
    r = chamar(italo, "fechar 970003")
    check("fechar encerra a conversa",
          state.get_conversation(970003)["state"] == "CLOSED",
          state.get_conversation(970003)["state"])

    print()
    if falhas:
        print(f"FALHOU - {len(falhas)}: {', '.join(falhas)}")
        return 1
    print("PASSOU - decisão humana vira ação, só de quem tem autoridade, "
          "e na dúvida a ponte pergunta")
    return 0


if __name__ == "__main__":
    sys.exit(main())

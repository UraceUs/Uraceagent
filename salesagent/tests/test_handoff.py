#!/usr/bin/env python3
"""Atendimento humano (14/10) do lado da ponte: a trava da IA na SAÍDA, o caso no Command
Center (com fila quando o painel cai) e a volta da conversa só por ordem do painel.

Nada sai da máquina: o Kommo é falso, o Command Center é um servidor HTTP local de mentira e
o agente (OpenClaw) é uma função. Os testes seguem as letras da missão onde se aplicam.

Uso:
    python3 salesagent/tests/test_handoff.py
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRIDGE = HERE.parent / "bridge"
URACE = tempfile.mkdtemp(prefix="urace-handoff-")
os.environ["URACE_DIR"] = URACE
os.environ["SDR_MODO"] = "atender"
Path(URACE, "bridge.env").write_text("CC_URL=http://127.0.0.1:1\nCC_API_KEY=urk_teste_segredo\n"
                                     "HANDOFF_SYNC_TOKEN=token-da-ponte\nFOLLOWUP_BOT_ID=99\n")
sys.path.insert(0, str(BRIDGE))
sys.path.insert(0, str(HERE.parent))

import app  # noqa: E402
import handoff_cc  # noqa: E402
import pausas  # noqa: E402
import scheduler  # noqa: E402
import state  # noqa: E402
from sdr import evento  # noqa: E402

FALHAS = []


def check(rotulo, cond, detalhe=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {rotulo}" + ("" if cond else f"  {detalhe}"))
    if not cond:
        FALHAS.append(rotulo)


class _Req:
    def __init__(self, corpo):
        self._corpo = corpo

    async def json(self):
        return self._corpo


class _Kommo:
    def __init__(self):
        self.notas, self.bots = [], []

    def add_note(self, lead_id, texto):
        self.notas.append((lead_id, texto))

    def add_tags(self, *a):
        pass

    def add_task(self, *a):
        pass

    def run_bot(self, bot, lead_id):
        self.bots.append(lead_id)
        return True


class _Painel(BaseHTTPRequestHandler):
    """Command Center de mentira: guarda o que recebeu e responde como o de verdade."""
    recebidos, no_ar, casos = [], True, {}

    def do_POST(self):                                     # noqa: N802
        if not _Painel.no_ar:
            self.send_response(503); self.end_headers(); return
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Painel.recebidos.append((self.headers.get("X-API-Key"), corpo))
        chave = corpo["idempotency_key"]
        novo = chave not in _Painel.casos
        _Painel.casos.setdefault(chave, len(_Painel.casos) + 1)
        resposta = {"ok": True, "resultado": "caso_criado" if novo else "caso_existente",
                    "caso_id": _Painel.casos[chave], "estado": "HUMAN_PENDING", "ia_bloqueada": True,
                    "notificacao": "enviada", "humano_notificado": True}
        self.send_response(201); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(resposta).encode())

    def log_message(self, *a):
        pass


def _subir_painel():
    srv = HTTPServer(("127.0.0.1", 0), _Painel)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    handoff_cc.CC_URL = f"http://127.0.0.1:{srv.server_port}"
    return srv


def _fakes(resposta_agente="Sure! How old is the driver?"):
    entregues = []
    app.kommo = _Kommo()
    app._salesbot_continue = lambda lead_id, url, tok, texto: entregues.append((lead_id, texto)) or True
    app._call_agent = lambda lead_id, msg: (resposta_agente, [])
    app.notify_human = lambda texto: None
    app.sdr_ponte.triar_em_segundo_plano = lambda *a, **k: None
    app.sdr_ponte.mover_para = lambda *a, **k: None
    app.sdr_ponte.pode_responder = lambda lead_id: (True, "")
    app.sdr_ponte.limpar = lambda lead_id, texto: texto
    return entregues


def _inbound(lead_id, texto):
    app.process_inbound({"lead_id": lead_id, "message": texto, "return_url": "https://x/continue/1"})


def _pausar(lead_id, caso):
    f = Path(URACE, "sdr_pausas.json")
    d = json.loads(f.read_text()) if f.exists() else {}
    d[str(lead_id)] = {"handoff": caso, "por": f"atendimento humano #{caso}"}
    f.write_text(json.dumps(d))


def _despausar(lead_id):
    f = Path(URACE, "sdr_pausas.json")
    d = json.loads(f.read_text()) if f.exists() else {}
    d.pop(str(lead_id), None)
    f.write_text(json.dumps(d))


def main() -> int:
    srv = _subir_painel()

    # ---------------------------------------------------------------- A/B: escalar abre o caso no painel
    entregues = _fakes()
    _inbound(810001, "I want to talk to a human please")
    _, corpo = _Painel.recebidos[-1] if _Painel.recebidos else (None, {})
    check("A: escalar abre caso no Command Center", bool(_Painel.recebidos), str(_Painel.recebidos))
    check("A: o pedido leva conversa, motivo, prioridade e chave",
          corpo.get("conversation_id") == "kommo:810001" and corpo.get("reason")
          and corpo.get("priority") in ("alta", "normal", "urgente", "baixa")
          and str(corpo.get("idempotency_key", "")).startswith("ponte:810001:"), str(corpo))
    check("A: autentica com a chave de API do painel", _Painel.recebidos and _Painel.recebidos[-1][0] == "urk_teste_segredo")
    check("A: a escalação leva UMA mensagem ao cliente (a de que uma pessoa vai responder)",
          len(entregues) == 1, str(entregues))
    conv = state.get_conversation(810001)
    check("A: o estado local trava a conversa (WAITING_HUMAN) e guarda o caso",
          conv["state"] == "WAITING_HUMAN" and conv["handoff_caso_id"] == 1, str(conv["state"]))

    # ---------------------------------------------------------------- D: a IA não fala com a conversa travada
    entregues = _fakes()
    _inbound(810001, "hello? anyone?")
    check("D: conversa escalada não recebe resposta automática", entregues == [], str(entregues))
    _pausar(810001, 1)
    _inbound(810001, "what time do you open?")
    check("D: com a pausa do caso, nada sai e o modelo nem é chamado", entregues == [], str(entregues))
    pode, motivo = pausas.ia_pode_enviar(810001)
    check("D: ia_pode_enviar diz por quê", not pode and "caso #1" in motivo, motivo)
    check("D: follow-up/resgate automático barrado", app.deliver_followup(810001, "oi?") is False)
    kommo_antes = list(app.kommo.bots)
    check("D: texto humano passa pela mesma porta",
          app.deliver_followup(810001, "Oi, aqui é a Ana.", origem="humano") is True
          and app.kommo.bots == kommo_antes + [810001])
    check("D: a origem humana fica gravada no pendente",
          state.get_conversation(810001)["pending_followup_origem"] == "humano")

    # corrida: a pessoa assume enquanto o modelo pensa — a trava vale na SAÍDA
    entregues = _fakes()
    lead_corrida = 810002

    def agente_lento(lead_id, msg):
        _pausar(lead_corrida, 7)                 # alguém clicou "Assumir" no meio do turno
        return ("Here's the price list!", [])
    app._call_agent = agente_lento
    _inbound(lead_corrida, "how much is the 1-day?")
    check("D: resposta da IA barrada na saída quando o caso abriu durante o turno", entregues == [], str(entregues))
    _despausar(lead_corrida)

    # entrega pendente (bots/run) descartada se a conversa travou entre o disparo e o hook
    lead_p = 810003
    state.update_conversation(lead_p, pending_followup_text="follow-up automático",
                              pending_followup_origem="ia")
    _pausar(lead_p, 8)
    entregues = _fakes()
    app.process_inbound({"lead_id": lead_p, "message": "", "return_url": "https://x/continue/2"})
    check("D: texto automático pendente não sai depois que a pessoa assumiu", entregues == [], str(entregues))
    check("D: e é apagado (não volta no próximo bots/run)",
          state.get_conversation(lead_p)["pending_followup_text"] is None)
    state.update_conversation(lead_p, pending_followup_text="Oi, sou a Ana", pending_followup_origem="humano")
    app.process_inbound({"lead_id": lead_p, "message": "", "return_url": "https://x/continue/3"})
    check("D: texto humano pendente sai mesmo com a pausa", entregues == [(lead_p, "Oi, sou a Ana")], str(entregues))
    _despausar(lead_p)

    # resposta da IA que sai pelo bots/run (sem Salesbot esperando) guarda a origem "ia" e é
    # conferida de novo quando o Kommo vier buscar
    lead_b = 810004
    entregues = _fakes()
    app._pending_returns.pop(lead_b, None)
    app.send_to_lead(lead_b, "Texto da IA a caminho")
    check("D: resposta da IA pendente no bots/run fica marcada como 'ia'",
          state.get_conversation(lead_b)["pending_followup_origem"] == "ia")
    _pausar(lead_b, 9)
    app.process_inbound({"lead_id": lead_b, "message": "", "return_url": "https://x/continue/4"})
    check("D: e não sai se a pessoa assumiu antes do Kommo buscar", entregues == [], str(entregues))
    _despausar(lead_b)

    # mensagens curtas (#237): a resposta da IA sai em balões, um por disparo do bot. Uma pessoa
    # que assume no meio da fila corta os balões que faltam; balões da escalação continuam.
    disparos = []
    app._disparar_proxima = lambda lead_id: disparos.append(lead_id)
    app.SALESBOT_DISPLAY = "json_reply"
    lead_q = 810011
    entregues = _fakes()
    app._pending_returns[lead_q] = ("https://x/continue/5", None)
    app.send_to_lead(lead_q, "Primeira linha da IA.\nSegunda linha da IA.\nTerceira linha da IA.")
    check("fila: o primeiro balão sai e o resto fica na fila com origem 'ia'",
          entregues == [(lead_q, "Primeira linha da IA.")]
          and state.get_conversation(lead_q)["pending_followup_origem"] == "ia" and disparos == [lead_q],
          f"{entregues} {disparos}")
    _pausar(lead_q, 11)
    app.process_inbound({"lead_id": lead_q, "message": "", "return_url": "https://x/continue/6"})
    check("fila: pessoa assumiu entre os balões, o resto da IA não sai",
          entregues == [(lead_q, "Primeira linha da IA.")]
          and state.get_conversation(lead_q)["pending_followup_text"] is None, str(entregues))
    lead_e = 810012
    entregues = _fakes()
    disparos.clear()
    app._pending_returns[lead_e] = ("https://x/continue/7", None)
    app.send_to_lead(lead_e, "Uma pessoa vai responder.\nÉ só aguardar aqui.", origem="escalacao")
    _pausar(lead_e, 12)
    app.process_inbound({"lead_id": lead_e, "message": "", "return_url": "https://x/continue/8"})
    check("fila: os balões da mensagem de escalação saem mesmo com o caso aberto",
          [t for _, t in entregues] == ["Uma pessoa vai responder.", "É só aguardar aqui."], str(entregues))
    _despausar(lead_q); _despausar(lead_e)
    app.SALESBOT_DISPLAY = "balloons"

    # agendador: escalado não recebe resgate
    state.update_conversation(810001, last_inbound_at=int(time.time()) - 99999, last_outbound_at=0)
    resgatados = []
    scheduler.rescue_fn = lambda conv: resgatados.append(conv["lead_id"]) or True
    scheduler._maybe_daily_brain_maintenance = lambda now: False   # nunca escreve no brain/ de verdade
    _despausar(810001)
    scheduler.tick()
    check("D: o agendador não resgata conversa escalada", 810001 not in resgatados, str(resgatados))
    scheduler.rescue_fn = None

    # ---------------------------------------------------------------- E: só o painel devolve, com contexto
    try:
        asyncio.run(app.handoff_estado(_Req({"lead_id": 810001, "estado": "RETURNED_TO_AI"}), x_handoff_token="errado"))
        check("K: token errado é recusado", False)
    except app.HTTPException as e:
        check("K: token errado é recusado", e.status_code == 401)
    r = asyncio.run(app.handoff_estado(_Req({"lead_id": 810001, "estado": "HUMAN_ACTIVE", "caso_id": 1, "autor": "Ana"}),
                                       x_handoff_token="token-da-ponte"))
    check("C: assumir no painel leva a ponte a HUMAN_HANDOFF", r["estado_ponte"] == "HUMAN_HANDOFF", str(r))
    r = asyncio.run(app.handoff_estado(_Req({"lead_id": 810001, "estado": "RETURNED_TO_AI", "caso_id": 1,
                                             "autor": "Ana", "nota": "Remarcada para sábado 10h."}),
                                       x_handoff_token="token-da-ponte"))
    check("E: devolver leva a conversa a RESUMED", r["ok"] and r["estado_ponte"] == "RESUMED", str(r))
    memoria = state.get_confirmations(810001)
    check("E: a nota da pessoa vira memória confirmada da conversa",
          memoria and "Remarcada para sábado 10h." in memoria[0]["answer"] and memoria[0]["author"] == "Ana",
          str(memoria))
    entregues = _fakes("Great, see you Saturday at 10!")
    _inbound(810001, "ok thanks, what should I bring?")
    check("E: depois da devolução a IA volta a responder", entregues == [(810001, "Great, see you Saturday at 10!")],
          str(entregues))
    contexto = app._memory_context(810001, state.get_conversation(810001))
    check("E: o contexto do turno traz o que a pessoa combinou", "Remarcada para sábado" in contexto, contexto[:300])

    # opt-out continua fechado
    state.transition(810005, "CLOSED", "opt-out")
    r = asyncio.run(app.handoff_estado(_Req({"lead_id": 810005, "estado": "RETURNED_TO_AI", "caso_id": 9}),
                                       x_handoff_token="token-da-ponte"))
    check("E: conversa fechada (opt-out) não volta para a IA", state.get_conversation(810005)["state"] == "CLOSED"
          and r["estado_ponte"] == "CLOSED", str(r))

    # ---------------------------------------------------------------- F: reinício não destrava
    _inbound_escalar = 810006
    _fakes()
    _inbound(_inbound_escalar, "I want a refund")
    codigo = ("import sys; sys.path.insert(0, %r); import pausas; "
              "pode, motivo = pausas.ia_pode_enviar(%d); print('PODE' if pode else 'TRAVADA:' + motivo)"
              % (str(BRIDGE), _inbound_escalar))
    saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                           env={**os.environ, "URACE_DIR": URACE}, timeout=60).stdout
    check("F: num processo novo (ponte reiniciada) a conversa continua travada", saida.startswith("TRAVADA"), saida)

    # ---------------------------------------------------------------- G/H: painel fora do ar, fila e idempotência
    _Painel.no_ar = False
    n_antes = len(_Painel.recebidos)
    _fakes()
    _inbound(810007, "I want a refund")
    pend = [p for p in handoff_cc.pendentes() if p["lead_id"] == 810007]
    check("H: painel fora do ar: o pedido fica na fila da ponte", pend and pend[0]["status"] == "pendente", str(pend))
    check("H: e a conversa já está travada localmente", not pausas.ia_pode_enviar(810007)[0])
    _Painel.no_ar = True
    with state.db() as conn:
        conn.execute("UPDATE handoff_outbox SET proxima_em=0 WHERE lead_id=810007")
    check("H: quando o painel volta, a fila entrega", handoff_cc.reenviar_pendentes() == 1)
    check("G: reenviar de novo não repete nada", handoff_cc.reenviar_pendentes() == 0)
    entregas = [c for _, c in _Painel.recebidos[n_antes:] if c["conversation_id"] == "kommo:810007"]
    chave = entregas[0]["idempotency_key"] if entregas else None
    r2 = handoff_cc.abrir_caso(810007, reason="cliente escreveu de novo", chave=chave)
    check("G: a mesma escalação reenviada volta como caso_existente", r2.get("resultado") == "caso_existente", str(r2))

    # ---------------------------------------------------------------- I: mensagem nossa não vira mensagem do cliente
    payload = {"message": {"add": [{"id": "a", "type": "outgoing", "text": "Oi, aqui é a Ana", "element_type": "2",
                                    "element_id": "810001"},
                                   {"id": "b", "type": "incoming", "text": "oi", "element_type": "2",
                                    "element_id": "810001"}]}}
    lidas = evento.mensagens_recebidas(payload)
    check("I: o webhook só vê a mensagem do cliente (a da pessoa é 'outgoing')",
          [m["id"] for m in lidas] == ["b"], str(lidas))

    # ---------------------------------------------------------------- J: uma conversa não trava a outra
    check("J: a conversa travada de um lead não trava outro",
          pausas.ia_pode_enviar(810001)[0] and not pausas.ia_pode_enviar(810006)[0])

    # ---------------------------------------------------------------- ferramenta estruturada
    _fakes()
    app.AGENT_API_KEY = "chave-do-agente"          # _auth lê o global do módulo
    r = asyncio.run(app.tool_escalate(_Req({"conversation_id": "kommo:810008", "reason": "payment dispute",
                                            "priority": "urgente", "summary": "Charged twice.",
                                            "customer_name": "John", "requested_action": "Check QuickBooks"}),
                                      x_api_key="chave-do-agente"))
    corpo = _Painel.recebidos[-1][1]
    check("escalate_to_human devolve o resultado real do painel",
          r.get("resultado") == "caso_criado" and r.get("humano_notificado") is True, str(r))
    check("escalate_to_human repassa resumo, nome e ação pedida",
          corpo["summary"] == "Charged twice." and corpo["customer_name"] == "John"
          and corpo["requested_action"] == "Check QuickBooks" and corpo["priority"] == "urgente", str(corpo))
    try:
        asyncio.run(app.tool_escalate(_Req({"conversation_id": "kommo:abc", "reason": "x"}), x_api_key="chave-do-agente"))
        check("escalate_to_human recusa conversa inválida", False)
    except app.HTTPException as e:
        check("escalate_to_human recusa conversa inválida", e.status_code == 400)

    srv.shutdown()
    print()
    if FALHAS:
        print(f"FALHOU - {len(FALHAS)} checagem(ns): {', '.join(FALHAS)}")
        return 1
    print("PASSOU - a IA só fala em conversa que é dela, o caso chega ao painel (ou espera na fila) "
          "e só o painel devolve a conversa")
    return 0


if __name__ == "__main__":
    sys.exit(main())

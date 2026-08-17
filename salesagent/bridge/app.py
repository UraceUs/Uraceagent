"""sales-bridge — serviço local no VPS entre Kommo e o OpenClaw Sales Agent.

Fluxo: Kommo (Salesbot/webhook) → /kommo/hook (ACK <2s, enfileira) → worker →
OpenClaw (agente urace-sales) → resposta → Kommo (Salesbot) → cliente.
Escalação: estado no SQLite + mensagem no WhatsApp interno.

Tools do agente (autenticadas por X-Api-Key): o agente NÃO fala com o Kommo
nem com o Rate Card diretamente — só através destes endpoints, onde os
portões são aplicados.
"""
import asyncio
import subprocess
import time

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

import gates
import kommo_client as kommo
import state
from config import AGENT_API_KEY, STAGES

app = FastAPI(title="urace-sales-bridge")

SALES_AGENT = "urace-sales"  # agente no OpenClaw (criado na implantação)


def _auth(x_api_key: str | None):
    if not AGENT_API_KEY or x_api_key != AGENT_API_KEY:
        raise HTTPException(401, "invalid api key")


# ------------------------------------------------------------------ entrada
@app.post("/kommo/hook")
async def kommo_hook(request: Request, background: BackgroundTasks,
                     x_api_key: str | None = Header(None)):
    """Recebe evento do Salesbot/webhook do Kommo. ACK imediato (regra dos 2s)."""
    _auth(x_api_key)
    payload = await request.json()
    background.add_task(process_inbound, payload)
    return {"ok": True}


def process_inbound(payload: dict) -> None:
    """Worker assíncrono: roteia a mensagem para o agente e devolve ao Kommo."""
    lead_id = int(payload.get("lead_id", 0))
    text = str(payload.get("message", ""))
    if not lead_id:
        state.log("error", None, f"payload sem lead_id: {str(payload)[:200]}")
        return
    state.log("inbound", lead_id, text)
    state.update_conversation(lead_id, last_inbound_at=int(time.time()))

    # B4: gatilhos de escalação avaliados ANTES do modelo
    triggers = gates.escalation_triggers(text)
    if triggers and state.get_conversation(lead_id)["state"] == "AI_ACTIVE":
        escalate(lead_id, "; ".join(triggers), context=text)
        return

    # G3: conversa escalada não volta a vender
    if not state.agent_may_sell(lead_id):
        state.log("gate", lead_id, "mensagem recebida em estado escalado — sem resposta comercial")
        return

    reply = run_agent(lead_id, text)
    if reply:
        send_to_lead(lead_id, reply)


# ------------------------------------------------------------------ agente
def run_agent(lead_id: int, text: str) -> str:
    """Um turno do agente OpenClaw, com sessão isolada por lead."""
    try:
        result = subprocess.run(
            ["openclaw", "agent", "--agent", SALES_AGENT,
             "--session-key", f"kommo-{lead_id}", "-m", text],
            capture_output=True, text=True, timeout=120,
        )
        reply = result.stdout.strip()
        state.log("outbound", lead_id, reply)
        return reply
    except Exception as exc:  # timeout, agente fora etc. → escala, nunca inventa
        state.log("error", lead_id, f"run_agent: {exc}")
        escalate(lead_id, f"falha do agente: {exc}", context=text)
        return ""


def send_to_lead(lead_id: int, text: str) -> None:
    """Devolve a resposta ao cliente via Kommo (Salesbot).

    TODO(deploy): implementar o retorno real — return_url do widget_request
    ou continuação de Salesbot. Definido na implantação com a conta real.
    """
    state.update_conversation(lead_id, last_outbound_at=int(time.time()))
    kommo.add_note(lead_id, f"[agent] {text}")


# ------------------------------------------------------------------ escalação
def escalate(lead_id: int, reason: str, context: str = "") -> None:
    state.transition(lead_id, "WAITING_HUMAN", reason)
    kommo.add_tags(lead_id, ["escalated"])
    kommo.add_note(lead_id, f"[escalação] {reason}")
    briefing = f"🔺 ESCALAÇÃO — lead {lead_id}\nMotivo: {reason}\nContexto: {context[:500]}\n" \
               f"Responda 'aprovar {lead_id} <instrução>' ou 'retomar {lead_id}'."
    notify_human(briefing)
    state.log("escalation", lead_id, reason)


def notify_human(text: str) -> None:
    """Envia ao WhatsApp interno (canal do dono) via OpenClaw.

    TODO(deploy): confirmar comando de envio direto de canal na versão
    instalada (openclaw channels send / message tool do agente principal).
    """
    try:
        subprocess.run(
            ["openclaw", "agent", "--agent", "main", "-m",
             f"Envie esta mensagem no WhatsApp para o Italo, sem alterar: {text}"],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as exc:
        state.log("error", None, f"notify_human: {exc}")


# ------------------------------------------------------------------ humano
@app.post("/human/reply")
async def human_reply(request: Request, x_api_key: str | None = Header(None)):
    """Resposta do humano autorizado (vinda do WhatsApp interno via agente main)."""
    _auth(x_api_key)
    payload = await request.json()
    lead_id = int(payload["lead_id"])
    action = payload.get("action", "")  # resume | close | instruct
    note = payload.get("note", "")
    state.log("human_reply", lead_id, f"{action}: {note}")
    if action == "resume":
        ok = state.transition(lead_id, "RESUMED", note, by_human=True)
        return {"ok": ok}
    if action == "close":
        ok = state.transition(lead_id, "CLOSED", note, by_human=True)
        return {"ok": ok}
    kommo.add_note(lead_id, f"[humano] {note}")
    return {"ok": True}


# ------------------------------------------------------------------ tools do agente
@app.get("/tools/price")
async def tool_price(lead_id: int, product: str, category: str,
                     x_api_key: str | None = Header(None)):
    _auth(x_api_key)
    return gates.get_price(lead_id, product, category)


@app.post("/tools/qualify")
async def tool_qualify(request: Request, x_api_key: str | None = Header(None)):
    """Agente registra os dados de qualificação conforme coleta na conversa."""
    _auth(x_api_key)
    p = await request.json()
    lead_id = int(p["lead_id"])
    fields = {}
    if p.get("experience") in ("first_time", "recreational", "competes"):
        fields["q_experience"] = p["experience"]
    if p.get("origin") in ("local", "traveler"):
        fields["q_origin"] = p["origin"]
    if p.get("driver_age") is not None:
        fields["driver_age"] = int(p["driver_age"])
    state.update_conversation(lead_id, **fields)
    if fields.get("q_experience") == "competes":
        escalate(lead_id, "driver já compete — conversa do dono (G2)")
        return {"ok": True, "routing": "escalate_to_owner"}
    return {"ok": True, "routing": "agent"}


@app.post("/tools/escalate")
async def tool_escalate(request: Request, x_api_key: str | None = Header(None)):
    _auth(x_api_key)
    p = await request.json()
    escalate(int(p["lead_id"]), p.get("reason", "solicitado pelo agente"),
             p.get("briefing", ""))
    return {"ok": True}


@app.post("/tools/crm")
async def tool_crm(request: Request, x_api_key: str | None = Header(None)):
    """Operações de CRM permitidas ao agente: nota, tag, estágio (limitado), tarefa."""
    _auth(x_api_key)
    p = await request.json()
    lead_id = int(p["lead_id"])
    op = p["op"]
    if op == "note":
        kommo.add_note(lead_id, p["text"])
    elif op == "tags":
        kommo.add_tags(lead_id, list(p["tags"]))
    elif op == "task":
        kommo.add_task(lead_id, p["text"], int(p["due_ts"]))
    elif op == "stage":
        stage_key = p["stage"]
        if stage_key in ("closed_won", "suppliers"):  # G9 + never_touch
            raise HTTPException(403, f"estágio {stage_key} não permitido ao agente")
        kommo.set_stage(lead_id, STAGES[stage_key])
    else:
        raise HTTPException(400, f"op desconhecida: {op}")
    return {"ok": True}


@app.get("/health")
async def health():
    return {"ok": True, "ts": int(time.time())}

"""sales-bridge — serviço local no VPS entre Kommo e o OpenClaw Sales Agent.

Fluxo: Kommo (Salesbot/webhook) → /kommo/hook (ACK <2s, enfileira) → worker →
OpenClaw (agente urace-sales) → resposta → Kommo (Salesbot) → cliente.
Escalação: estado no SQLite + mensagem no WhatsApp interno.

Tools do agente (autenticadas por X-Api-Key): o agente NÃO fala com o Kommo
nem com o Rate Card diretamente — só através destes endpoints, onde os
portões são aplicados.
"""
import asyncio
import datetime
import json
import subprocess
import time

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

import directives as directive_engine
import gates
import kommo_client as kommo
import state
import textproc
from config import AGENT_API_KEY, HUMAN_WHATSAPP

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
def _call_agent(lead_id: int, message: str) -> tuple[str, list[str]]:
    """Uma chamada crua ao agente OpenClaw. Devolve (texto bruto, diretivas
    [[...]] extraídas) -- sem sanitizar nem executar nada ainda."""
    result = subprocess.run(
        ["openclaw", "agent", "--agent", SALES_AGENT,
         "--session-key", f"kommo-{lead_id}", "-m", message],
        capture_output=True, text=True, timeout=120,
    )
    raw = result.stdout.strip()
    return raw, textproc.extract_directives(raw)


def run_agent(lead_id: int, text: str) -> str:
    """Um turno do agente OpenClaw, com sessão isolada por lead.

    O texto bruto do modelo pode conter diretivas `[[...]]` (protocolo em
    instructions/urace-sales-agent.md) -- nunca destinadas ao cliente.
    `textproc.customer_facing()` decide o que o lead realmente vê (remove
    diretivas + sanitiza dash). `directive_engine.execute()` de fato aciona
    CRM/qualificação/escalação a partir delas.

    Caso especial: `[[price ...]]` não traz o link real na mesma resposta
    (o modelo normalmente só promete mandar) -- então, se aparecer, essa
    resposta é descartada e o resultado real da tool de preço volta como
    mensagem [SYSTEM] para uma segunda chamada, cuja resposta (agora com o
    link de verdade) é a que de fato vai para o lead.
    """
    try:
        raw, directives = _call_agent(lead_id, text)
    except Exception as exc:  # timeout, agente fora etc. → escala, nunca inventa
        state.log("error", lead_id, f"run_agent: {exc}")
        escalate(lead_id, f"falha do agente: {exc}", context=text)
        return ""

    reply = raw
    if directives:
        state.log("directives", lead_id, " | ".join(directives))
        result = directive_engine.execute(lead_id, directives, escalate)
        price_results = result["price_results"]
        if price_results and state.agent_may_sell(lead_id):
            system_msg = ("[SYSTEM] price tool result(s), use the real link now: "
                          + json.dumps(price_results, ensure_ascii=False))
            try:
                raw2, directives2 = _call_agent(lead_id, system_msg)
                if directives2:
                    state.log("directives", lead_id, " | ".join(directives2))
                    directive_engine.execute(lead_id, directives2, escalate)
                reply = raw2
            except Exception as exc:
                state.log("error", lead_id, f"run_agent (rodada de preço): {exc}")
                # mantém a resposta original -- o lead ainda recebe algo,
                # mesmo sem o link resolvido nesta rodada.

    visible = textproc.customer_facing(reply)
    state.log("outbound", lead_id, visible)
    return visible


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

    Causa raiz do bug "não chega mensagem" (17/08): faltavam os flags de
    entrega. `openclaw agent -m "..."` sozinho só devolve texto no stdout
    -- não empurra nada para o canal. `--to/--channel/--deliver` são
    obrigatórios para o agente efetivamente publicar no WhatsApp.
    """
    try:
        result = subprocess.run(
            ["openclaw", "agent", "--agent", "main", "--channel", "whatsapp",
             "--to", HUMAN_WHATSAPP, "--deliver", "-m",
             f"[Encaminhe exatamente o texto abaixo como mensagem, sem alterar nada]\n{text}"],
            capture_output=True, text=True, timeout=60,
        )
        state.log("notify_human", None, f"rc={result.returncode} out={result.stdout[:300]} err={result.stderr[:300]}")
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
    """Agente registra os dados de qualificação conforme coleta na conversa.

    Mesma lógica de directive_engine.apply_qualify() (usada quando a
    diretiva [[qualify ...]] vem embutida na resposta) -- um único lugar
    decide o que conta como campo válido e quando G2 força escalação.
    """
    _auth(x_api_key)
    p = await request.json()
    lead_id = int(p["lead_id"])
    kwargs = {"experience": p.get("experience"), "origin": p.get("origin")}
    if p.get("driver_age") is not None:
        kwargs["age"] = p["driver_age"]
    result = directive_engine.apply_qualify(lead_id, kwargs)
    if result["escalate"]:
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
    """Operações de CRM permitidas ao agente: nota, tag, estágio (limitado), tarefa.

    Mesma lógica de directive_engine.apply_crm() (usada quando a diretiva
    [[crm ...]] vem embutida na resposta).
    """
    _auth(x_api_key)
    p = await request.json()
    lead_id = int(p["lead_id"])
    op = p.get("op")
    if op not in ("note", "tags", "task", "stage"):
        raise HTTPException(400, f"op desconhecida: {op}")
    if op == "stage" and p.get("stage") in ("closed_won", "suppliers"):  # G9 + never_touch
        raise HTTPException(403, f"estágio {p['stage']} não permitido ao agente")
    kwargs = dict(p)
    if op == "tags" and isinstance(p.get("tags"), list):
        kwargs["tags"] = ",".join(p["tags"])
    if op == "task" and p.get("due_ts") is not None:
        kwargs["due"] = datetime.datetime.fromtimestamp(int(p["due_ts"])).isoformat()
    directive_engine.apply_crm(lead_id, kwargs)
    return {"ok": True}


@app.get("/health")
async def health():
    return {"ok": True, "ts": int(time.time())}

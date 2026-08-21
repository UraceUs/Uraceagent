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

import httpx
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
def _dig(payload: dict, *paths: str):
    """Busca tolerante: cada path é 'a.b.c'; devolve o primeiro valor
    ESCALAR (str/número) não vazio encontrado — dict/lista no fim do path
    não contam (ex.: 'data.message' sendo um objeto não pode virar o texto
    da mensagem). O formato exato do widget_request varia por conta/bot,
    então a ponte procura em todos os lugares plausíveis em vez de assumir
    um schema fixo."""
    for path in paths:
        node = payload
        for part in path.split("."):
            if isinstance(node, list) and part.isdigit():
                node = node[int(part)] if int(part) < len(node) else None
            elif isinstance(node, dict):
                node = node.get(part)
            else:
                node = None
            if node is None:
                break
        if isinstance(node, (str, int, float)) and node != "":
            return node
    return None


def _extract_inbound(payload: dict) -> tuple[int, str, str | None, str | None]:
    """Devolve (lead_id, texto, return_url, token) do payload — cobre tanto
    o formato simples de teste ({lead_id, message}) quanto o widget_request
    real do Salesbot (token/data/return_url com o lead aninhado)."""
    lead_id = _dig(payload, "lead_id", "data.lead_id", "data.lead.id",
                   "data.lead.0.id", "lead.id", "leads.0.id")
    text = _dig(payload, "message", "data.message", "data.message.text",
                "data.message.message.text", "message.text",
                "data.talk.message.text", "text", "data.text")
    return_url = _dig(payload, "return_url", "data.return_url")
    token = _dig(payload, "token", "data.token")
    try:
        lead_num = int(lead_id) if lead_id is not None else 0
    except (TypeError, ValueError):
        lead_num = 0
    return lead_num, str(text) if text is not None else "", return_url, token


# return_url do Salesbot é efêmero (vale para UMA continuação do bot) —
# memória de processo basta; se a ponte reiniciar no meio, o fallback de
# nota no Kommo cobre (e o bot expira sozinho do lado de lá).
_pending_returns: dict[int, tuple[str, str | None]] = {}


@app.post("/kommo/hook")
async def kommo_hook(request: Request, background: BackgroundTasks,
                     x_api_key: str | None = Header(None), key: str | None = None):
    """Recebe evento do Salesbot/webhook do Kommo. ACK imediato (regra dos 2s).

    Auth: header X-Api-Key OU query ?key= (o widget_request do Salesbot não
    envia headers customizados, então a chave vai na URL configurada no bot
    — só trafega sobre HTTPS via Caddy)."""
    _auth(x_api_key or key)
    payload = await request.json()
    # Sempre loga o payload bruto — é o que permite calibrar o parser contra
    # o formato REAL da conta no primeiro teste (tools/show_recent_audit.py).
    state.log("hook_raw", None, json.dumps(payload, ensure_ascii=False)[:3500])
    background.add_task(process_inbound, payload)
    return {"ok": True}


def process_inbound(payload: dict) -> None:
    """Worker assíncrono: roteia a mensagem para o agente e devolve ao Kommo."""
    lead_id, text, return_url, token = _extract_inbound(payload)
    if not lead_id:
        state.log("error", None, f"payload sem lead_id reconhecível: {str(payload)[:300]}")
        return
    if return_url:
        _pending_returns[lead_id] = (return_url, token)
    if not text:
        state.log("error", lead_id, "payload sem texto de mensagem reconhecível")
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
    """Devolve a resposta ao cliente via Kommo.

    Caminho real: continuação do Salesbot via return_url do widget_request
    (o bot mostra o texto no chat do lead e volta a esperar a próxima
    mensagem). Fallback: nota no lead — não chega ao cliente, mas nada se
    perde e fica visível pro time no card.
    """
    state.update_conversation(lead_id, last_outbound_at=int(time.time()))
    pending = _pending_returns.pop(lead_id, None)
    if pending and _salesbot_continue(lead_id, pending[0], pending[1], text):
        return
    kommo.add_note(lead_id, f"[agent] {text}")
    state.log("outbound_fallback", lead_id,
              "sem return_url ativo — resposta gravada como nota, não entregue no chat")


def _salesbot_continue(lead_id: int, return_url: str, token: str | None,
                       text: str) -> bool:
    """POST de continuação do Salesbot: mostra `text` ao lead no chat.

    Formato conforme docs do widget_request (token no corpo +
    execute_handlers). O status/corpo da resposta é logado sempre — é o que
    permite ajustar fino contra a conta real no primeiro teste ponta a ponta.
    """
    body = {
        "token": token,
        "data": {"status": "success"},
        "execute_handlers": [
            {"handler": "show", "params": {"type": "text", "value": text}},
        ],
    }
    try:
        r = httpx.post(return_url, json=body, timeout=15)
        state.log("salesbot_continue", lead_id,
                  f"rc={r.status_code} body={r.text[:300]}")
        return r.status_code < 300
    except Exception as exc:
        state.log("error", lead_id, f"salesbot_continue: {exc}")
        return False


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

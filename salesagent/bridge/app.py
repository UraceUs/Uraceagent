"""sales-bridge — serviço local no VPS entre Kommo e o OpenClaw Sales Agent.

Fluxo: Kommo (Salesbot/webhook) → /kommo/hook (ACK <2s, enfileira) → worker →
OpenClaw (agente urace-sales) → resposta → Kommo (Salesbot) → cliente.
Escalação: estado no SQLite + mensagem no WhatsApp interno.

Tools do agente (autenticadas por X-Api-Key): o agente NÃO fala com o Kommo
nem com o Rate Card diretamente — só através destes endpoints, onde os
portões são aplicados.
"""
import asyncio
import base64
import datetime
import hashlib
import hmac
import json
import re
import subprocess
import time

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

import directives as directive_engine
import gates
import kommo_client as kommo
import scheduler
import state
import textproc
from config import (AGENT_API_KEY, FOLLOWUP_BOT_ID, HUMAN_WHATSAPP,
                    KOMMO_BOT_SECRET, KOMMO_TOKEN, SALESBOT_DISPLAY)

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


def _b64url_decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def _verify_bot_token(token: str | None) -> bool:
    """Valida o JWT descartável do widget_request: HS512 assinado com o
    client secret da integração (conforme AmoCRMOAuth::parseBotDisposableToken
    do SDK oficial). Só roda quando KOMMO_BOT_SECRET está configurado —
    o ?key= na URL continua sendo a autenticação principal."""
    if not KOMMO_BOT_SECRET:
        return True
    if not token or token.count(".") != 2:
        return False
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        expected = hmac.new(KOMMO_BOT_SECRET.encode(),
                            f"{header_b64}.{payload_b64}".encode(),
                            hashlib.sha512).digest()
        if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
            return False
        claims = json.loads(_b64url_decode(payload_b64))
        exp = claims.get("exp")
        return exp is None or int(exp) >= int(time.time())
    except Exception:
        return False


def _php_unflatten(flat: dict) -> dict:
    """Converte chaves PHP-style ('data[lead_id]', 'a[b][0][c]') em dict
    aninhado — formato real do widget_request na conta (descoberto no 1º
    teste ao vivo, 24/08: o Kommo envia form-encoded, não JSON)."""
    root: dict = {}
    for key, value in flat.items():
        parts = key.replace("]", "").split("[")
        node = root
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                node[part] = value
            else:
                nxt = node.get(part)
                if not isinstance(nxt, dict):
                    nxt = {}
                    node[part] = nxt
                node = nxt
    return root


def _parse_hook_body(raw_body: bytes) -> dict:
    """Corpo do webhook em qualquer formato: JSON OU form-urlencoded
    (PHP-style, o que o Salesbot realmente envia). Corpo vazio = {}."""
    if not raw_body:
        return {}
    try:
        parsed = json.loads(raw_body)
        return parsed if isinstance(parsed, dict) else {"_body": parsed}
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    from urllib.parse import parse_qs
    form = parse_qs(raw_body.decode("utf-8", "replace"), keep_blank_values=True)
    flat = {k: (v[0] if len(v) == 1 else v) for k, v in form.items()}
    return _php_unflatten(flat)


@app.post("/kommo/hook")
async def kommo_hook(request: Request, background: BackgroundTasks,
                     x_api_key: str | None = Header(None), key: str | None = None):
    """Recebe evento do Salesbot/webhook do Kommo. ACK imediato (regra dos 2s).

    Auth: header X-Api-Key OU query ?key= (o widget_request do Salesbot não
    envia headers customizados, então a chave vai na URL configurada no bot
    — só trafega sobre HTTPS via Caddy)."""
    _auth(x_api_key or key)
    raw_body = await request.body()
    # Sempre loga o corpo BRUTO + content-type ANTES de qualquer parse — é o
    # que permite calibrar contra o formato real da conta
    # (tools/show_recent_audit.py). 1º teste ao vivo provou o valor disso:
    # o corpo veio form-encoded e o parse JSON puro estourava 500.
    ctype = request.headers.get("content-type", "?")
    state.log("hook_raw", None, f"ct={ctype} :: " + raw_body.decode("utf-8", "replace")[:3300])
    payload = _parse_hook_body(raw_body)
    # JWT do bot: rejeita só se o token VEIO e é inválido. Token ausente não
    # bloqueia (formato form-encoded pode não trazê-lo onde esperamos e o
    # ?key= da URL já é a autenticação obrigatória) — mas fica logado para
    # calibrarmos com o payload real.
    tok = payload.get("token")
    if tok and not _verify_bot_token(tok):
        state.log("error", None, "hook: JWT do bot inválido/expirado (KOMMO_BOT_SECRET ativo)")
        raise HTTPException(401, "invalid bot token")
    if KOMMO_BOT_SECRET and not tok:
        state.log("gate", None, "hook aceito sem token JWT (auth só pelo ?key=) — calibrar depois")
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
        # Sem texto + follow-up pendente = é o bot disparado pelo agendador
        # (bots/run) abrindo o canal de entrega: devolve o texto pendente.
        conv = state.get_conversation(lead_id)
        pending = conv.get("pending_followup_text")
        if pending and return_url:
            state.update_conversation(lead_id, pending_followup_text=None,
                                      last_outbound_at=int(time.time()))
            if _salesbot_continue(lead_id, return_url, token, pending):
                state.log("followup", lead_id, "follow-up entregue no chat via bots/run")
            else:
                kommo.add_note(lead_id, f"[follow-up — enviar manualmente]\n{pending}")
            _pending_returns.pop(lead_id, None)
            return
        state.log("error", lead_id, "payload sem texto de mensagem reconhecível")
        return

    state.log("inbound", lead_id, text)
    state.update_conversation(lead_id, last_inbound_at=int(time.time()))
    # B2: lead respondeu — qualquer trilha de follow-up ativa morre agora.
    scheduler.cancel(lead_id, "lead respondeu")

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
        # B2: relógio de "sem resposta" reinicia a cada envio nosso — trilha
        # link_sent se o link de preço saiu neste turno, initial caso
        # contrário. A trilha scheduled (diretiva com data pedida pelo lead)
        # tem precedência e não é sobrescrita.
        conv = state.get_conversation(lead_id)
        if conv["state"] in ("AI_ACTIVE", "RESUMED") and conv.get("followup_track") != "scheduled":
            track = "link_sent" if _last_turn_price_sent.pop(lead_id, False) else "initial"
            scheduler.start_track(lead_id, track)


# Marca "o link de preço saiu neste turno" por lead — consumida logo após o
# envio para escolher a trilha de follow-up (B2). Efêmero por natureza.
_last_turn_price_sent: dict[int, bool] = {}


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
        if price_results:
            _last_turn_price_sent[lead_id] = True  # trilha B2 pós-envio
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


def compose_followup(lead_id: int, track: str, attempt: int) -> str:
    """Compõe o follow-up via agente, com a memória da sessão do lead — o
    texto referencia a situação real da conversa (regra das instruções),
    não um template genérico. Diretivas que vierem junto são logadas mas
    NÃO executadas (um follow-up não pode escalar/mexer em CRM sozinho)."""
    prompt = (f"[SYSTEM] Follow-up due for this lead: track={track}, "
              f"attempt={attempt + 1}. Compose ONLY the follow-up message to "
              "send now, per your Follow-up section: short, referencing this "
              "lead's actual situation, no price, no pressure. Reply with the "
              "message text only.")
    try:
        raw, dirs = _call_agent(lead_id, prompt)
        if dirs:
            state.log("directives", lead_id,
                      "compose_followup (não executadas): " + " | ".join(dirs))
        return textproc.customer_facing(raw)
    except Exception as exc:
        state.log("error", lead_id, f"compose_followup: {exc}")
        return ""


def deliver_followup(lead_id: int, text: str) -> bool:
    """Entrega espontânea: grava o texto como pendente e dispara o Salesbot
    no lead (bots/run). O bot chama o widget_request → process_inbound vê o
    pendente e o devolve pelo return_url → aparece no chat. Sem bot
    configurado (FOLLOWUP_BOT_ID vazio) devolve False e o agendador usa o
    fallback nota+tarefa."""
    if not FOLLOWUP_BOT_ID:
        return False
    state.update_conversation(lead_id, pending_followup_text=text)
    try:
        ok = kommo.run_bot(FOLLOWUP_BOT_ID, lead_id)
    except Exception as exc:
        state.log("error", lead_id, f"deliver_followup bots/run: {exc}")
        ok = False
    if not ok:
        state.update_conversation(lead_id, pending_followup_text=None)
    return ok


@app.on_event("startup")
async def _start_scheduler():
    scheduler.compose_fn = compose_followup
    scheduler.deliver_fn = deliver_followup
    scheduler.notify_fn = notify_human
    scheduler.task_fn = kommo.add_task
    scheduler.note_fn = kommo.add_note
    scheduler.start()


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
              ("entrega via salesbot falhou" if pending else "sem return_url ativo")
              + " — resposta gravada como nota, não entregue no chat")


# Limite VALIDADO na conta real (24/08, 1º teste ao vivo): o continue do
# Salesbot recusa `show` com value > 80 chars (erro TooLong) e aceita no
# máximo 10 handlers por chamada. A resposta vira uma sequência de balões.
_SHOW_CHAR_LIMIT = 80
_MAX_HANDLERS = 10


_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")


def _chunk_for_salesbot(text: str, limit: int = _SHOW_CHAR_LIMIT) -> list[str]:
    """Divide a resposta em pedaços <= limit, um por balão de chat. Quebra
    primeiro por linha (o menu A/B/C/D vira um balão por opção, natural em
    chat); dentro de linha longa, por FRASE (empacotando frases que couberem
    juntas); só em último caso por palavra — nunca no meio de palavra/URL."""
    chunks: list[str] = []

    def _split_words(seg: str) -> None:
        while len(seg) > limit:
            cut = seg.rfind(" ", 1, limit + 1)
            if cut <= 0:
                cut = limit  # palavra/URL única maior que o limite: corte duro
            chunks.append(seg[:cut].strip())
            seg = seg[cut:].strip()
        if seg:
            chunks.append(seg)

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if len(line) <= limit:
            chunks.append(line)
            continue
        # linha longa: empacota frases inteiras enquanto couberem juntas
        packed = ""
        for sentence in _SENTENCE_RE.split(line):
            candidate = f"{packed} {sentence}".strip() if packed else sentence
            if len(candidate) <= limit:
                packed = candidate
            else:
                if packed:
                    chunks.append(packed)
                packed = ""
                if len(sentence) <= limit:
                    packed = sentence
                else:
                    _split_words(sentence)
        if packed:
            chunks.append(packed)
    return chunks


def _salesbot_continue(lead_id: int, return_url: str, token: str | None,
                       text: str) -> bool:
    """POST de continuação do Salesbot: mostra `text` ao lead no chat, como
    uma sequência de balões (handler `show` por pedaço de <= 80 chars).

    Formato confirmado nas docs oficiais + calibrado no 1º teste ao vivo:
    - POST no return_url verbatim (…/api/v4/salesbot/{bot}/continue/{id})
    - Auth: header `Authorization: Bearer <KOMMO_TOKEN>` (API v4)
    - Corpo: {"data": {...}, "execute_handlers": [<=10 shows de <=80 chars]}
    - Sucesso = 202 Accepted. 400 TooLong = pedaço estourou o limite.
    - 404 = o bot desistiu de esperar — cai no fallback de nota.
    - Janela de espera do bot comprovada >= 58s no teste real.
    """
    if SALESBOT_DISPLAY == "json_reply":
        # Widget v2: a resposta INTEIRA vai em data.reply e o próprio bot a
        # exibe via {{json.reply}} (passo 2 do fluxo gerado pelo widget) —
        # uma mensagem única com quebras de linha, sem limite de 80 chars.
        body = {"data": {"status": "success", "reply": text}}
    else:  # "balloons" — widget v1
        chunks = _chunk_for_salesbot(text)
        if not chunks:
            return False
        if len(chunks) > _MAX_HANDLERS:
            # Não truncar conteúdo em silêncio: mensagem longa demais para o
            # canal vai inteira para a nota (fallback) e fica registrado.
            state.log("error", lead_id,
                      f"resposta viraria {len(chunks)} balões (máx {_MAX_HANDLERS}) — fallback nota")
            return False
        body = {
            "data": {"status": "success"},
            "execute_handlers": [
                {"handler": "show", "params": {"type": "text", "value": c}}
                for c in chunks
            ],
        }
    headers = {"Authorization": f"Bearer {KOMMO_TOKEN}"}
    try:
        r = httpx.post(return_url, json=body, headers=headers, timeout=15)
        state.log("salesbot_continue", lead_id,
                  f"rc={r.status_code} modo={SALESBOT_DISPLAY} body={r.text[:300]}")
        if r.status_code == 404:
            state.log("error", lead_id,
                      "salesbot_continue 404: bot não estava mais esperando "
                      "(resposta demorou demais?) — usando fallback de nota")
        return r.status_code < 300
    except Exception as exc:
        state.log("error", lead_id, f"salesbot_continue: {exc}")
        return False


# ------------------------------------------------------------------ escalação
def escalate(lead_id: int, reason: str, context: str = "") -> None:
    state.transition(lead_id, "WAITING_HUMAN", reason)
    scheduler.cancel(lead_id, "conversa escalada")  # G3: sem follow-up comercial
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

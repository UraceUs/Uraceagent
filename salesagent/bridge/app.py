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
import threading
import time

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

import confidence
import directives as directive_engine
import gates
import handoff_cc
import holding
import human_intents
import kommo_client as kommo
import knowledge_writer
import pausas
import scheduler
import sdr_ponte
import state
import textproc
from config import (AGENT_API_KEY, BRAIN_RETRIEVAL, BRAIN_TOP_DOCS,
                    FOLLOWUP_BOT_ID, HUMAN_OPERATORS, HUMAN_REPLY_TOKEN,
                    HUMAN_WHATSAPP, HUMAN_WHATSAPP_LIST, KOMMO_BOT_SECRET,
                    KOMMO_TOKEN, PROGRAM_LINKS, SALESBOT_DISPLAY, SDR_MODO,
                    URACE_DIR)

app = FastAPI(title="urace-sales-bridge")
state.instalar_mascara_nos_logs()  # 13/10: a chave do webhook não vai para o journal

SALES_AGENT = "urace-sales"  # agente no OpenClaw (criado na implantação)


def _auth(x_api_key: str | None):
    if not AGENT_API_KEY or x_api_key != AGENT_API_KEY:
        raise HTTPException(401, "invalid api key")


def _auth_human_reply(x_api_key: str | None):
    """Aceita a chave principal OU o token de escopo mínimo.

    Só /human/whatsapp usa isto. O token existe para o agente do WhatsApp,
    que roda em sandbox e precisa da credencial no prompt -- e um prompt não
    é lugar para a chave que abre o hook do Kommo e as tools de preço."""
    if AGENT_API_KEY and x_api_key == AGENT_API_KEY:
        return
    if HUMAN_REPLY_TOKEN and x_api_key == HUMAN_REPLY_TOKEN:
        return
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


def _extract_inbound(payload: dict) -> tuple[int, str, str | None, str | None, str]:
    """Devolve (lead_id, texto, return_url, token, contact_name) do payload.

    O nome vem no widget_request como `data[contact_name]` e passou a ser
    guardado em 25/08: uma escalação que diz só "lead 31764961" obriga o
    humano a abrir o Kommo para saber de quem se trata. Com nome, ele
    decide pelo WhatsApp mesmo. Cobre tanto
    o formato simples de teste ({lead_id, message}) quanto o widget_request
    real do Salesbot (token/data/return_url com o lead aninhado)."""
    lead_id = _dig(payload, "lead_id", "data.lead_id", "data.lead.id",
                   "data.lead.0.id", "lead.id", "leads.0.id")
    text = _dig(payload, "message", "data.message", "data.message.text",
                "data.message.message.text", "message.text",
                "data.talk.message.text", "text", "data.text")
    return_url = _dig(payload, "return_url", "data.return_url")
    token = _dig(payload, "token", "data.token")
    nome = _dig(payload, "contact_name", "data.contact_name",
                "data.contact.name", "contact.name")
    try:
        lead_num = int(lead_id) if lead_id is not None else 0
    except (TypeError, ValueError):
        lead_num = 0
    return (lead_num, str(text) if text is not None else "", return_url, token,
            str(nome) if nome else "")


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


@app.post("/kommo/eventos")
async def kommo_eventos(request: Request, background: BackgroundTasks,
                        x_api_key: str | None = Header(None), key: str | None = None):
    """Webhook de CONTA do Kommo (mensagem recebida) — os olhos do SDR.

    Nos níveis observar e organizar a ponte não conversa com ninguém: é por
    aqui que ela vê cada mensagem (e cada lead criado) e organiza o card em
    Urace/Comercial.
    No nível atender quem trata a mensagem é o /kommo/hook (Salesbot), e
    este endpoint só confirma o recebimento, para não triar duas vezes.
    ACK imediato: o Kommo desliga webhook que demora."""
    _auth(x_api_key or key)
    raw_body = await request.body()
    payload = _parse_hook_body(raw_body)
    if SDR_MODO == "atender":
        background.add_task(responder_eventos, payload)
        return {"ok": True, "modo": "atender"}
    background.add_task(sdr_ponte.processar_eventos, payload)
    return {"ok": True}


# Quanto a resposta pelo webhook de conta espera antes de agir: se o Salesbot do Kommo também
# disparou com a mesma mensagem, o /kommo/hook chega primeiro e a ponte não responde duas vezes.
ESPERA_PELO_SALESBOT_S = 8


_rajada: dict[int, list[tuple]] = {}
_rajada_lock = threading.Lock()


def responder_eventos(payload: dict, espera: float = ESPERA_PELO_SALESBOT_S) -> list[dict]:
    """Nível atender, 13/10 (dono: "precisa ser em todas as msg"): toda mensagem recebida que chega
    pelo webhook de conta é respondida pela ponte, sem depender de gatilho de Salesbot no Kommo (o
    menor intervalo que o Kommo aceita lá é 5 min). A entrega usa o mesmo canal do follow-up:
    bots/run no Salesbot de entrega. Lead fora do escopo do robô só é organizado."""
    saida = []
    novas = []
    for msg in sdr_ponte.evento.mensagens_recebidas(payload):
        lead_id, texto = msg["lead_id"], (msg["texto"] or "").strip()
        if not lead_id or not sdr_ponte._primeira_vez(f"atender-{msg['id']}"):
            continue
        if not texto:
            saida.append({"lead_id": lead_id, "resposta": "SEM_TEXTO"})
            continue
        novas.append((msg["id"], lead_id, texto))
    # Rajada (14/10: "Oi" + "Quanto custa?" com 6 s de diferença viraram duas
    # respostas): cada mensagem entra na fila do lead ANTES da espera, inclusive
    # as do mesmo payload; depois da espera só a ÚLTIMA da fila responde, com o
    # texto de todas juntas.
    with _rajada_lock:
        for msg_id, lead_id, texto in novas:
            _rajada.setdefault(lead_id, []).append((msg_id, texto))
    for msg_id, lead_id, texto in novas:
        t0 = int(time.time())
        try:
            pode, motivo = sdr_ponte.pode_responder(lead_id)
        except Exception as exc:
            state.log("error", lead_id, f"atender: leitura do card falhou: {exc}")
            _tirar_da_rajada(lead_id, msg_id)
            saida.append({"lead_id": lead_id, "resposta": "ERRO_KOMMO"})
            continue
        if not pode:
            state.log("gate", lead_id, f"atender: sem resposta da ponte ({motivo}) — só organiza")
            _tirar_da_rajada(lead_id, msg_id)
            sdr_ponte.triar_em_segundo_plano(lead_id, texto)
            saida.append({"lead_id": lead_id, "resposta": motivo})
            continue
        with _rajada_lock:
            ultima = (_rajada.get(lead_id) or [(None, "")])[-1][0]
        if ultima != msg_id:
            saida.append({"lead_id": lead_id, "resposta": "JUNTADA_COM_A_SEGUINTE"})
            continue
        if espera:
            time.sleep(espera)
        with _rajada_lock:
            fila = _rajada.get(lead_id) or []
            if not fila or fila[-1][0] != msg_id:
                saida.append({"lead_id": lead_id, "resposta": "JUNTADA_COM_A_SEGUINTE"})
                continue
            _rajada.pop(lead_id, None)
        conv = state.get_conversation(lead_id)
        if (conv.get("last_inbound_text") or "") == texto[:500] and (conv.get("last_inbound_at") or 0) >= t0 - 60:
            saida.append({"lead_id": lead_id, "resposta": "JA_TRATADA_PELO_SALESBOT"})
            continue
        tratar_mensagem(lead_id, "\n".join(t for _id, t in fila))
        saida.append({"lead_id": lead_id, "resposta": "RESPONDIDA"})
    return saida


def _tirar_da_rajada(lead_id: int, msg_id) -> None:
    with _rajada_lock:
        fila = [m for m in _rajada.get(lead_id) or [] if m[0] != msg_id]
        if fila:
            _rajada[lead_id] = fila
        else:
            _rajada.pop(lead_id, None)


@app.post("/tools/sdr")
async def tool_sdr(request: Request, x_api_key: str | None = Header(None)):
    """Avalia uma mensagem com as regras do SDR, sem tocar em nada.
    É o teste de balcão: curl com um texto e ver o que o SDR decidiria."""
    _auth(x_api_key)
    p = await request.json()
    card = p.get("card") or {}
    r = sdr_ponte.sdr.avaliar(str(p.get("texto", "")), card=card,
                              remetente_email=p.get("remetente_email"))
    return {"ok": True, "modo": SDR_MODO, "triagem": r["triagem"], "roteamento": r["roteamento"],
            "sinais": {k: r["analise"][k] for k in ("intencoes", "score", "automatico", "spam",
                                                     "opt_out", "sensivel", "conversao", "compete")}}


def process_inbound(payload: dict) -> None:
    """Worker assíncrono: roteia a mensagem para o agente e devolve ao Kommo."""
    lead_id, text, return_url, token, contact_name = _extract_inbound(payload)
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
        origem = conv.get("pending_followup_origem") or "ia"
        if pending and return_url and origem == "ia":     # "escalacao" e "humano" não passam pela trava
            # entre o bots/run e este instante (segundos) uma pessoa pode ter assumido a conversa
            pode, motivo = pausas.ia_pode_enviar(lead_id)
            if not pode:
                state.update_conversation(lead_id, pending_followup_text=None, pending_followup_origem=None)
                state.log("gate", lead_id, f"texto automático pendente descartado na saída: {motivo}")
                _pending_returns.pop(lead_id, None)
                return
        if pending and return_url:
            state.update_conversation(lead_id, pending_followup_text=None, pending_followup_origem=None,
                                      last_outbound_at=int(time.time()))
            if _salesbot_continue(lead_id, return_url, token, pending):
                state.log("followup", lead_id, "texto pendente entregue no chat via bots/run")
            else:
                kommo.add_note(lead_id, f"[follow-up — enviar manualmente]\n{pending}")
            _pending_returns.pop(lead_id, None)
            return
        state.log("error", lead_id, "payload sem texto de mensagem reconhecível")
        return
    tratar_mensagem(lead_id, text, contact_name)


def tratar_mensagem(lead_id: int, text: str, contact_name: str | None = None) -> None:
    """Uma mensagem do lead, venha do Salesbot (/kommo/hook) ou do webhook de conta
    (/kommo/eventos, nível atender). A resposta sai pelo return_url do Salesbot quando há um, e
    pelo bots/run quando não há (ver send_to_lead)."""
    state.log("inbound", lead_id, text)
    campos = {"last_inbound_at": int(time.time()), "last_inbound_text": text[:500]}
    if contact_name:
        campos["contact_name"] = contact_name
    state.update_conversation(lead_id, **campos)
    # B2: lead respondeu — qualquer trilha de follow-up ativa morre agora.
    scheduler.cancel(lead_id, "lead respondeu")

    # SDR (D-2026-09-25). Abaixo de "atender" a ponte não fala com o lead —
    # os leads seguem humanos (D-08-27) e o Salesbot nem deveria estar ligado.
    # Se a mensagem chegou mesmo assim, ela só organiza o card e registra.
    if SDR_MODO != "atender":
        state.log("sdr", lead_id, f"nível {SDR_MODO}: mensagem do Salesbot sem resposta da ponte")
        sdr_ponte.triar_em_segundo_plano(lead_id, text)
        _pending_returns.pop(lead_id, None)
        return

    if pausas.ia_pausada(lead_id):
        # A equipe pausou a IA nesta conversa no Command Center: quem responde é a pessoa. O card
        # continua sendo organizado; follow-up e resgate também ficam parados (scheduler).
        state.log("gate", lead_id, "IA pausada nesta conversa (Command Center) — sem resposta da ponte")
        sdr_ponte.triar_em_segundo_plano(lead_id, text)
        _pending_returns.pop(lead_id, None)
        return

    rota = sdr_ponte.rotear(text)
    sdr_ponte.triar_em_segundo_plano(lead_id, text, rota)
    if rota["acao"] == "silenciar":
        # Não é lead (e-mail automático, código, spam, grupo): não recebe
        # resposta. "Toda mensagem de LEAD recebe resposta" segue valendo.
        # last_outbound_at evita que o resgate do agendador responda por nós.
        state.update_conversation(lead_id, last_outbound_at=int(time.time()))
        state.log("gate", lead_id, f"SDR: sem resposta ({rota['motivo']}) — não é lead")
        _pending_returns.pop(lead_id, None)
        return
    if rota["acao"] == "confirmar_opt_out":
        send_to_lead(lead_id, sdr_ponte.confirmacao_opt_out(text))
        state.transition(lead_id, "CLOSED", "opt-out do lead")
        scheduler.cancel(lead_id, "opt-out")
        kommo_tags_seguras(lead_id, ["opt_out"])
        return

    # A PARTIR DAQUI existe UM só caminho de saída, e ele sempre envia algo.
    # Antes (até 25/08) havia três `return` mudos aqui -- gatilho B4, estado
    # escalado (G3) e agente vazio -- e cada um deixava o lead falando
    # sozinho. O incidente que provou isso: "can i bring my own kart?" bateu
    # no gatilho B4, escalou certinho, e o lead nunca recebeu uma linha.
    # Escalar é sobre quem RESPONDE, nunca sobre responder ou não.
    reply = ""
    origem_envio = "ia"
    triggers = gates.escalation_triggers(text)
    estado_atual = state.get_conversation(lead_id)["state"]
    if rota["acao"] == "escalar" and estado_atual in ("AI_ACTIVE", "RESUMED"):
        # Sinais do SDR que o B4 não tinha (conversão, piloto que compete,
        # corporativo, grupo grande) e os que ele já tinha, com prioridade:
        # alta chama a pessoa agora; média vira tarefa na fila dela.
        escalate(lead_id, f"SDR {rota['motivo']}: {rota['descricao']}", context=text,
                 prioridade=rota["prioridade"])
        reply = _resposta_de_espera(lead_id, text)
        origem_envio = "escalacao"
    elif triggers and estado_atual == "AI_ACTIVE":
        # B4: assuntos sensíveis (desconto, refund, jurídico...) escalam
        # ANTES do modelo -- ele nunca vê a mensagem, então também não pode
        # ser convencido a responder. Quem acusa o recebimento é a ponte.
        escalate(lead_id, "; ".join(triggers), context=text)
        reply = _resposta_de_espera(lead_id, text)
        origem_envio = "escalacao"
    elif not state.agent_may_sell(lead_id):
        # 14/10 (atendimento humano, D-2026-10-14): conversa escalada é de uma pessoa até ela
        # devolver. A IA não responde — nem a pergunta factual que o Brain cobre (o G3 refinado de
        # 27/08 fica superado), nem a mensagem de espera. A pessoa vê a mensagem no Kommo e no
        # painel; o painel avisa quem está atendendo que o cliente escreveu de novo.
        conv = state.get_conversation(lead_id)
        state.update_conversation(lead_id, pending_question=text[:300])
        state.log("gate", lead_id, f"conversa em {conv['state']}: sem resposta automática — com uma pessoa")
        if handoff_cc.configurado():
            # garante o caso no painel (idempotente: a chave é a da escalação)
            handoff_cc.abrir_caso(lead_id, reason=conv.get("escalation_reason") or "cliente escreveu em conversa escalada",
                                  summary=f"Nova mensagem do cliente: {text[:300]}")
        elif holding.is_substantive(text):
            nome = conv.get("contact_name") or "sem nome no Kommo"
            state.update_conversation(lead_id, realert_count=0, last_realert_at=int(time.time()))
            notify_human(
                f"🔺 LEAD ESCALADO VOLTOU A FALAR — {nome} (lead {lead_id})\n"
                f"Nova mensagem: {text[:300]}\n"
                f"Escalado por: {conv.get('escalation_reason') or '?'}")
        _pending_returns.pop(lead_id, None)
        return
    else:
        reply = run_agent(lead_id, text)
        if not reply:
            # Agente fora do ar/timeout/resposta vazia. run_agent já escalou
            # no except; o lead não pode pagar por isso com silêncio.
            state.log("error", lead_id, "agente devolveu resposta vazia — enviando reconhecimento")
            reply = _holding_reply(lead_id, text)

    send_to_lead(lead_id, reply, origem=origem_envio)
    # B2: relógio de "sem resposta" reinicia a cada envio nosso — trilha
    # link_sent se o link de preço saiu neste turno, initial caso
    # contrário. A trilha scheduled (diretiva com data pedida pelo lead)
    # tem precedência e não é sobrescrita. Em estado escalado nenhuma
    # trilha comercial começa (G3) — o guard de state cobre isso.
    conv = state.get_conversation(lead_id)
    if conv["state"] in ("AI_ACTIVE", "RESUMED") and conv.get("followup_track") != "scheduled":
        track = "link_sent" if _last_turn_price_sent.pop(lead_id, False) else "initial"
        scheduler.start_track(lead_id, track)


def _resposta_de_espera(lead_id: int, lead_text: str) -> str:
    """O que o lead recebe quando a conversa está com uma pessoa. Objeção de
    preço ou pedido de desconto não ouve "sua pergunta está com a equipe":
    recebe a oferta de uma call de 15 min com o nosso time, com o link do
    calendário (pedido do dono, 13/10). O resto, a espera de sempre."""
    link = PROGRAM_LINKS.get("call_link")
    if link and sdr_ponte.objecao_de_preco(lead_text):
        conv = state.get_conversation(lead_id)
        state.log("gate", lead_id, "objeção de preço: oferta de call com o time")
        return holding.call_offer(lead_text, link, contact_name=conv.get("contact_name"))
    return _holding_reply(lead_id, lead_text)


def _holding_reply(lead_id: int, lead_text: str) -> str:
    """Mensagem de espera do `holding.py`, contando quantas já foram para
    este lead (para não repetir a mesma frase e soar robô) e se apresentando
    quando é a primeira vez que a URACE fala com essa pessoa."""
    conv = state.get_conversation(lead_id)
    sent_before = conv.get("holding_count") or 0
    state.update_conversation(lead_id, holding_count=sent_before + 1)
    return holding.waiting_message(
        lead_text, sent_before,
        contact_name=conv.get("contact_name"),
        first_contact=not conv.get("last_outbound_at"),
        pending_question=conv.get("pending_question"))


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


def _memory_context(lead_id: int, conv: dict) -> str:
    """Memória estruturada do cliente para o turno — não é histórico bruto.

    A sessão do OpenClaw guarda a CONVERSA; isto aqui guarda o que a
    conversa sozinha não garante: perfil qualificado, estágio comercial,
    pergunta pendente, e — o mais importante — o que um humano JÁ CONFIRMOU
    para este cliente. Sem a última parte, o caso real de 26-27/08 se
    repete: o Italo responde a escalação, o lead recebe, e o Chase segue a
    conversa sem saber o que foi prometido, porque a resposta humana foi
    entregue por fora da sessão dele.

    Curta de propósito (memória curada entra em TODO turno; arquivo morto
    não entra em nenhum).
    """
    partes = [
        f"nome={conv.get('contact_name') or '?'}",
        f"experience={conv.get('q_experience') or '?'}",
        f"origin={conv.get('q_origin') or '?'}",
        f"driver_age={conv.get('driver_age') or '?'}",
        f"state={conv.get('state')}",
    ]
    if conv.get("followup_track"):
        partes.append(f"followup={conv['followup_track']}")
    if conv.get("pending_question"):
        partes.append(f"aguardando_humano=\"{conv['pending_question'][:100]}\"")
    linhas = ["Memória do lead: " + " ".join(partes)]

    confirmadas = state.get_confirmations(lead_id)
    if confirmadas:
        linhas.append("Respostas JÁ CONFIRMADAS pela equipe para ESTE lead "
                      "(pode afirmar como fato; nunca peça para ele repetir "
                      "a pergunta):")
        for c in confirmadas:
            q = (c.get("question") or "").strip()
            linhas.append(f"- {('Perguntou: ' + q + ' -> ') if q else ''}"
                          f"a equipe confirmou: {c['answer']}")

    linhas.append(f"Próxima ação sugerida: {_next_action(conv)}")
    return "\n".join(linhas)


def _next_action(conv: dict) -> str:
    """A próxima ação comercial correta, deduzida do estado — determinística
    e sugerida, nunca imposta: o fluxo fino vive nas instruções; isto é a
    bússola do turno (\"o objetivo não é a resposta bonita, é a próxima
    ação certa\")."""
    if conv.get("state") in ("WAITING_HUMAN", "HUMAN_HANDOFF"):
        return ("aguardar decisão humana; responder apenas o que o "
                "conhecimento acima cobrir")
    if not conv.get("driver_age"):
        return ("triagem curta: quem é o piloto e que idade tem (uma pergunta "
                "só; se ele já disse, registre com [[qualify]] e não pergunte de novo)")
    if not conv.get("q_experience"):
        return ("triagem curta: já andou de kart de corrida? (nunca, aluguel, "
                "competição) -- registre com [[qualify]]")
    if conv.get("followup_track") == "link_sent":
        return ("o link já foi enviado; não reenviar. Objeção ou muitas "
                "dúvidas: oferecer a call de 15 min com o nosso time")
    return ("descobrir o objetivo (experimentar um dia, treinar sempre, "
            "competir) e, com decisão real, objeção ou muitas dúvidas, "
            "oferecer a call de 15 min com o nosso time")


def _instrucoes_comercial(lead_id: int) -> str:
    """O que o comercial escreveu na página Robô SDR do painel (12/10), em
    URACE_DIR/sdr_instrucoes.md. Lido a cada turno (é pequeno); vale acima da
    persona, menos preço (tabela) e travas. Falha na leitura: segue sem ele."""
    arquivo = URACE_DIR / "sdr_instrucoes.md"
    try:
        if not arquivo.exists():
            return ""
        conteudo = arquivo.read_text(encoding="utf-8").strip()
    except Exception as exc:
        state.log("error", lead_id, f"sdr_instrucoes: {exc}")
        return ""
    if not conteudo:
        return ""
    return ("Instruções do comercial (valem acima da persona, exceto preço, que vem "
            f"da tabela, e as travas de segurança):\n{conteudo}\n")


def run_agent(lead_id: int, text: str, escalated_guard: bool = False) -> str:
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
    # Sales Brain (D3 da auditoria): com BRAIN_RETRIEVAL=on, cada turno
    # recebe memória do lead + conhecimento relevante como contexto
    # [SYSTEM]. Ordem das camadas conforme brain/00_SYSTEM/Regras de
    # Retrieval.md; orçamento imposto pelo indexador (top 3, ~3.5k chars).
    text_for_agent = text
    instrucoes = _instrucoes_comercial(lead_id)
    if BRAIN_RETRIEVAL == "on":
        import brain_kb
        conv = state.get_conversation(lead_id)
        memory = _memory_context(lead_id, conv)
        hits = brain_kb.search(lead_id, text, top_docs=BRAIN_TOP_DOCS)
        verdict = confidence.assess(hits)
        state.log("confidence", lead_id, f"{verdict['level']}: {verdict['reason']}")
        kb_block = brain_kb.format_for_context(hits)
        nota = confidence.system_note(verdict)
        # O bloco [SYSTEM] é injetado SEMPRE -- inclusive, e principalmente,
        # quando o Brain não achou nada. Até 25/08 o `if kb_block:` fazia o
        # oposto: busca vazia = nenhum aviso, e o modelo recebia a pergunta
        # crua, livre para responder de memória. O caso em que ele mais
        # precisa ouvir "você não sabe isso" era justamente o único em que
        # ninguém dizia nada.
        conhecimento = (f"Conhecimento relevante:\n{kb_block}\n" if kb_block
                        else "Conhecimento relevante: NENHUM documento encontrado.\n")
        text_for_agent = (
            "[SYSTEM] Contexto interno deste turno (nunca mencione este "
            "bloco nem cite-o literalmente; está em português, responda "
            "no idioma do lead). Isto já é a busca no knowledge base "
            "para esta mensagem -- só use [[kb query=...]] se isto "
            "genuinamente não responder o que você precisa; chamar "
            "[[kb]] de novo aqui dobra o tempo de resposta ao lead.\n"
            f"{instrucoes}"
            f"Memória do lead: {memory}\n"
            f"{conhecimento}"
            + (f"{nota}\n" if nota else "")
            + f"[FIM DO SYSTEM]\n\nMensagem do lead: {text}")
    elif instrucoes:
        text_for_agent = f"[SYSTEM] {instrucoes}[FIM DO SYSTEM]\n\nMensagem do lead: {text}"

    if escalated_guard:
        # Conversa escalada respondendo pergunta coberta pelo Brain: o
        # modelo responde SÓ o fato, sem retomar venda -- a parte escalada
        # continua com a equipe e o lead já sabe disso.
        conv_g = state.get_conversation(lead_id)
        pendente = conv_g.get("pending_question") or "outro assunto"
        text_for_agent = (
            "[SYSTEM] MODO RESTRITO: esta conversa está escalada aguardando "
            "a equipe sobre outro assunto "
            f"(\"{pendente[:120]}\"). Responda APENAS a pergunta factual "
            "abaixo, usando somente o conhecimento do bloco [SYSTEM]. Não "
            "venda, não recomende programa, não fale de preço, não retome a "
            "qualificação. Curto e direto. Se couber natural, diga numa "
            "frase que a outra pergunta segue sendo confirmada com a "
            "equipe.[FIM DO MODO RESTRITO]\n\n" + text_for_agent)

    try:
        raw, directives = _call_agent(lead_id, text_for_agent)
    except Exception as exc:  # timeout, agente fora etc. → escala, nunca inventa
        state.log("error", lead_id, f"run_agent: {exc}")
        escalate(lead_id, f"falha do agente: {exc}", context=text)
        return ""

    reply = raw
    if directives:
        state.log("directives", lead_id, " | ".join(directives))
        result = directive_engine.execute(lead_id, directives, escalate)
        price_results = result["price_results"]
        kb_results = result.get("kb_results", [])
        if price_results:
            _last_turn_price_sent[lead_id] = True  # trilha B2 pós-envio
        if (price_results or kb_results) and state.agent_may_sell(lead_id):
            payload = {}
            if price_results:
                payload["price"] = price_results
            if kb_results:
                payload["knowledge"] = kb_results
            system_msg = ("[SYSTEM] tool result(s) — use the real data now: "
                          + json.dumps(payload, ensure_ascii=False))
            try:
                raw2, directives2 = _call_agent(lead_id, system_msg)
                if directives2:
                    state.log("directives", lead_id, " | ".join(directives2))
                    directive_engine.execute(lead_id, directives2, escalate)
                reply = raw2
            except Exception as exc:
                state.log("error", lead_id, f"run_agent (segunda rodada): {exc}")
                # mantém a resposta original -- o lead ainda recebe algo,
                # mesmo sem o dado resolvido nesta rodada.

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
        texto = textproc.customer_facing(raw)
        if SDR_MODO == "atender":
            # Mesma guarda da resposta (estilo, um link, uma pergunta): o
            # follow-up sai por bots/run e não passa pelo send_to_lead.
            texto = sdr_ponte.limpar(lead_id, texto)
        return texto
    except Exception as exc:
        state.log("error", lead_id, f"compose_followup: {exc}")
        return ""


def deliver_followup(lead_id: int, text: str, origem: str = "ia") -> bool:
    """Entrega espontânea: grava o texto como pendente e dispara o Salesbot
    no lead (bots/run). O bot chama o widget_request → process_inbound vê o
    pendente e o devolve pelo return_url → aparece no chat. Sem bot
    configurado (FOLLOWUP_BOT_ID vazio) devolve False e o agendador usa o
    fallback nota+tarefa."""
    if not FOLLOWUP_BOT_ID:
        return False
    if origem == "ia":
        pode, motivo = pausas.ia_pode_enviar(lead_id)
        if not pode:
            state.log("gate", lead_id, f"entrega automática cancelada na saída: {motivo}")
            return False
    state.update_conversation(lead_id, pending_followup_text=text, pending_followup_origem=origem)
    try:
        ok = kommo.run_bot(FOLLOWUP_BOT_ID, lead_id)
    except Exception as exc:
        state.log("error", lead_id, f"deliver_followup bots/run: {exc}")
        ok = False
    if not ok:
        state.update_conversation(lead_id, pending_followup_text=None, pending_followup_origem=None)
    return ok


def rescue_lead(conv: dict) -> bool:
    """Entrega, por iniciativa da ponte, a resposta devida a um lead.

    Chamada pelo agendador (`scheduler._maybe_rescue`) quando o lead falou
    por último e ninguém respondeu, ou quando ele espera um humano há
    horas. Usa o mesmo canal de entrega espontânea do follow-up -- validado
    ponta a ponta em 25/08 -- e cai na nota do Kommo se o disparo falhar,
    para nada se perder em silêncio.
    """
    lead_id = conv["lead_id"]
    texto = holding.waiting_message(
        conv.get("last_inbound_text") or "",
        conv.get("holding_count") or 0,
        contact_name=conv.get("contact_name"),
        first_contact=not conv.get("last_outbound_at"))
    state.update_conversation(lead_id,
                              holding_count=(conv.get("holding_count") or 0) + 1)
    entregue = deliver_followup(lead_id, texto)
    if entregue:
        state.update_conversation(lead_id, last_outbound_at=int(time.time()))
        state.log("outbound", lead_id, texto)
    else:
        kommo.add_note(lead_id, f"[resgate — enviar manualmente]\n{texto}")
    return entregue


@app.on_event("startup")
async def _start_scheduler():
    # Abaixo de "atender" o agendador fica parado. Ele é quem fala sozinho
    # com o lead (follow-up, resgate da resposta devida), escreve nota e
    # tarefa no Kommo e manda re-alerta no WhatsApp interno. Ligado em
    # observar/organizar, ele pegaria as conversas antigas do banco (de antes
    # da D-2026-08-27) e mandaria mensagem a lead na primeira varredura.
    if SDR_MODO != "atender":
        state.log("sdr", None, f"nível {SDR_MODO}: agendador parado (follow-up, resgate e re-alerta desligados)")
        return
    scheduler.compose_fn = compose_followup
    scheduler.deliver_fn = deliver_followup
    # 14/10: com o Command Center ligado, o re-alerta da equipe é dele (push/WhatsApp oficial);
    # o aviso pelo OpenClaw só continua se o legado for mantido de propósito.
    scheduler.notify_fn = notify_human if (not handoff_cc.configurado() or handoff_cc.LEGADO_OPENCLAW) else None
    scheduler.handoff_retry_fn = handoff_cc.reenviar_pendentes
    scheduler.rescue_fn = rescue_lead
    scheduler.task_fn = kommo.add_task
    scheduler.note_fn = kommo.add_note
    scheduler.close_fn = sdr_ponte.ao_fechar if SDR_MODO in ("organizar", "atender") else None
    scheduler.start()


def send_to_lead(lead_id: int, text: str, origem: str = "ia") -> None:
    """Devolve a resposta ao cliente via Kommo.

    Caminho real: continuação do Salesbot via return_url do widget_request
    (o bot mostra o texto no chat do lead e volta a esperar a próxima
    mensagem). Fallback: nota no lead — não chega ao cliente, mas nada se
    perde e fica visível pro time no card.

    `origem` (14/10): "ia" passa pela trava do atendimento humano AQUI, na saída — o turno
    pode levar um minuto no modelo, e uma pessoa pode assumir a conversa nesse meio tempo.
    "escalacao" é a única mensagem que acompanha a própria escalação (o aviso de que uma pessoa
    vai responder). "humano" é texto de pessoa.
    """
    if origem == "ia":
        pode, motivo = pausas.ia_pode_enviar(lead_id)
        if not pode:
            state.log("gate", lead_id, f"resposta automática barrada na saída: {motivo}")
            _pending_returns.pop(lead_id, None)
            return
    if SDR_MODO == "atender":
        limpo = sdr_ponte.limpar(lead_id, text)
        if not limpo:
            conv = state.get_conversation(lead_id)
            limpo = _holding_reply(lead_id, conv.get("last_inbound_text") or "")
        text = limpo
    state.update_conversation(lead_id, last_outbound_at=int(time.time()))
    pending = _pending_returns.pop(lead_id, None)
    if pending and _salesbot_continue(lead_id, pending[0], pending[1], text):
        return
    # a origem vai junto: texto da IA que ficar pendente no bots/run é conferido de novo na entrega
    if not pending and SDR_MODO == "atender" and deliver_followup(lead_id, text, origem=origem):
        # Mensagem que veio pelo webhook de conta: não há Salesbot esperando, então a ponte dispara
        # o bot de entrega (bots/run) e ele busca o texto pendente no /kommo/hook.
        state.log("outbound", lead_id, f"via bots/run: {text}")
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
def escalate(lead_id: int, reason: str, context: str = "", prioridade: str = "alta",
             summary: str = "", customer_name: str | None = None, requested_action: str | None = None,
             category: str | None = None) -> dict:
    """Passa a conversa para uma pessoa. Devolve o que aconteceu de verdade (caso aberto, aviso
    confirmado ou pendente), para a IA nunca dizer ao cliente o que não foi feito."""
    state.transition(lead_id, "WAITING_HUMAN", reason)
    scheduler.cancel(lead_id, "conversa escalada")  # G3: sem follow-up comercial
    kommo_tags_seguras(lead_id, ["escalated"])
    _kommo_seguro(lead_id, "nota de escalação", kommo.add_note, lead_id, f"[escalação] {reason}")
    if SDR_MODO in ("organizar", "atender"):
        sdr_ponte.mover_para(lead_id, sdr_ponte.regras.ETAPAS_COMERCIAL["HUMANO"], reason)
    conv = state.get_conversation(lead_id)
    nome = conv.get("contact_name") or "sem nome no Kommo"
    if context.strip():
        # A pergunta fica registrada: é ela que as mensagens de espera citam
        # de volta ao lead ("Sobre 'can I bring my own kart?' -- ...") e é
        # ela que o knowledge_writer usa como título do candidato.
        state.update_conversation(lead_id, pending_question=context.strip()[:300])
    perfil_partes = []
    if conv.get("q_experience"):
        perfil_partes.append(f"experiência={conv['q_experience']}")
    if conv.get("driver_age"):
        perfil_partes.append(f"idade={conv['driver_age']}")
    if conv.get("q_origin"):
        perfil_partes.append(f"origem={conv['q_origin']}")
    perfil = ("Perfil: " + ", ".join(perfil_partes) + "\n") if perfil_partes else ""
    briefing = (f"🔺 ESCALAÇÃO — {nome} (lead {lead_id})\n"
                f"Motivo: {reason}\n{perfil}"
                f"Pergunta do lead: {context[:400] or '(sem texto)'}\n"
                f"Responda esta mensagem com o texto para o lead — eu entrego "
                f"no chat e devolvo a conversa ao Chase.")
    if handoff_cc.configurado():
        # 14/10: o caso vai para o Command Center (trava, fila, avisos oficiais). O aviso antigo
        # pelo OpenClaw/WhatsApp Web só sai se o legado estiver ligado de propósito (transição).
        resumo = summary or "\n".join(x for x in (perfil.strip(), f"Pergunta do lead: {context[:400]}" if context else "") if x)
        resultado = handoff_cc.abrir_caso(
            lead_id, reason=reason, prioridade=prioridade, summary=resumo,
            customer_name=customer_name or conv.get("contact_name"), requested_action=requested_action,
            category=category, chave=f"ponte:{lead_id}:{conv.get('escalated_at') or int(time.time())}")
        if resultado.get("caso_id"):
            state.update_conversation(lead_id, handoff_caso_id=resultado["caso_id"])
        if handoff_cc.LEGADO_OPENCLAW and prioridade == "alta":
            notify_human(briefing)
        state.log("escalation", lead_id, reason)          # só o motivo: é o que o extrator agrupa
        return resultado
    if SDR_MODO in ("organizar", "atender") and prioridade != "alta":
        # Uma pessoa só no comercial: só prioridade alta interrompe. O resto
        # entra na fila como tarefa no Kommo, com o prazo da prioridade.
        from sdr import regras as _sdr_regras
        from config import KOMMO_RESPONSAVEL_ID
        prazo = int(time.time()) + _sdr_regras.SLA_MINUTOS.get(prioridade, 15) * 60
        _kommo_seguro(lead_id, "tarefa de handoff", kommo.add_task, lead_id,
                      f"SDR ({prioridade}): {reason}"[:500], prazo, KOMMO_RESPONSAVEL_ID or None)
        state.log("escalation", lead_id, f"{reason} [fila, prioridade {prioridade}]")
        return {"ok": True, "resultado": "tarefa_kommo", "humano_notificado": False, "notificacao": "pendente"}
    notify_human(briefing)
    state.log("escalation", lead_id, reason)
    # o canal antigo não confirma entrega na hora (thread): nada aqui pode dizer "avisado"
    return {"ok": True, "resultado": "aviso_legado", "humano_notificado": False, "notificacao": "pendente"}


def _kommo_seguro(lead_id: int, o_que: str, fn, *args) -> bool:
    """Chamada ao Kommo que NUNCA derruba o turno. Até 25/09 um erro do
    Kommo dentro de escalate() matava a tarefa antes da resposta ao lead
    (raise_for_status) e só o resgate de 180s cobria."""
    try:
        fn(*args)
        return True
    except Exception as exc:
        state.log("error", lead_id, f"kommo: {o_que} falhou: {exc}")
        return False


def kommo_tags_seguras(lead_id: int, tags: list[str]) -> bool:
    return _kommo_seguro(lead_id, "tags " + ",".join(tags), kommo.add_tags, lead_id, tags)


def notify_human(text: str) -> None:
    """Dispara o aviso aos operadores SEM bloquear o chamador.

    Por que assíncrono (bug real de 27/08): o repasse é uma chamada de
    modelo por operador (~30-60s cada, dois operadores) e rodava NO MEIO de
    `process_inbound` -- antes da resposta ao lead, que disputa a janela de
    ~58s do Salesbot. O aviso ao Italo levou 36s e a resposta ao lead saiu
    depois da janela: avisar o humano estava roubando exatamente o tempo
    que o lead tinha. A entrega ao lead é o caminho crítico; o aviso pode
    atrasar um minuto sem custo.
    """
    import threading
    threading.Thread(target=_notify_human_sync, args=(text,),
                     daemon=True).start()


def _notify_human_sync(text: str) -> None:
    """Envia ao WhatsApp interno de CADA operador autorizado, via OpenClaw.

    Causa raiz do bug "não chega mensagem" (17/08): faltavam os flags de
    entrega. `openclaw agent -m "..."` sozinho só devolve texto no stdout
    -- não empurra nada para o canal. `--to/--channel/--deliver` são
    obrigatórios para o agente efetivamente publicar no WhatsApp.

    Segunda causa, descoberta em 25/08 (o Italo não recebeu uma escalação
    real): este caminho pede a um MODELO que repasse um alerta de texto
    fixo. Um modelo pode parafrasear -- ou, como aconteceu, responder "quem
    sou eu, quem é você?" e entregar ISSO no lugar do alerta, devolvendo
    rc=0 como se tivesse dado certo. Duas defesas agora:

    1. VERIFICAÇÃO: o alerta carrega um marcador (o id do lead). Se ele não
       aparece no que o agente devolveu, a entrega é tratada como FALHA
       explícita no log -- nunca mais um rc=0 mentiroso.
    2. ALCANCE: manda para todos de HUMAN_WHATSAPP_LIST. Até 25/08 era um
       número só, então o Eduardo -- autoridade no brief -- nunca recebeu
       escalação nenhuma.

    Pré-requisito operacional: `sync_admin_identity.sh` (a identidade do
    Mark precisa estar no workspace do agente, senão ele não sabe que o
    trabalho dele é repassar).
    """
    marker = re.search(r"lead (\d+)", text)
    destinos = HUMAN_WHATSAPP_LIST or [HUMAN_WHATSAPP]
    for numero in destinos:
        if not numero:
            continue
        try:
            result = subprocess.run(
                ["openclaw", "agent", "--agent", "main", "--channel", "whatsapp",
                 "--to", numero, "--deliver", "-m",
                 f"[Encaminhe exatamente o texto abaixo como mensagem, sem alterar nada]\n{text}"],
                capture_output=True, text=True, timeout=60,
            )
            out = result.stdout or ""
            entregue = result.returncode == 0 and (
                marker is None or marker.group(1) in out)
            state.log("notify_human", None,
                      f"to={numero} rc={result.returncode} "
                      f"{'OK' if entregue else 'NAO CONFIRMADO'} "
                      f"out={out[:200]} err={(result.stderr or '')[:200]}")
            if not entregue:
                # Alto e claro no log: uma escalação que o humano não recebe
                # é um lead esperando por alguém que nem sabe que existe.
                state.log("error", None,
                          f"ESCALAÇÃO NÃO CONFIRMADA para {numero} — o agente "
                          f"'main' não repassou o texto (identidade "
                          f"sincronizada? rode sync_admin_identity.sh). "
                          f"Devolveu: {out[:200]!r}")
        except Exception as exc:
            state.log("error", None, f"notify_human ({numero}): {exc}")


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



# ------------------------------------------------- resposta humana (WhatsApp)
def _operador_por_telefone(numero: str) -> dict | None:
    """Telefone -> operador autorizado (§3). O pareamento é POSICIONAL:
    HUMAN_WHATSAPP no env está na mesma ordem de human-operators.json. Um
    número que não está na lista não é operador, e nada que ele mande vira
    ação -- a autoridade é do contato conhecido, não de quem diz um nome."""
    numero = (numero or "").strip()
    if not numero:
        return None
    ops = HUMAN_OPERATORS.get("operators", [])
    for i, cadastrado in enumerate(HUMAN_WHATSAPP_LIST):
        if cadastrado.strip() == numero and i < len(ops):
            return ops[i]
    return None


def _leads_esperando() -> list[dict]:
    """Leads escalados aguardando decisão humana, mais recente primeiro."""
    with state.db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM conversations "
            "WHERE state IN ('WAITING_HUMAN','HUMAN_HANDOFF') "
            "ORDER BY COALESCE(escalated_at, 0) DESC")]


@app.post("/human/whatsapp")
async def human_whatsapp(request: Request, x_api_key: str | None = Header(None)):
    """Resposta do operador chegando do WhatsApp interno.

    Fecha o último passo manual do ciclo do brief. Até 26/08 a escalação
    chegava pedindo "responda 'aprovar <lead> ...'" e a resposta caía no
    vazio -- ninguém lia. O Italo respondeu "aprovado" numa escalação real
    e não aconteceu nada.

    Corpo: {"from": "+1407...", "text": "pode trazer o kart",
            "quoted": "<a mensagem que a pessoa respondeu, se houver>"}

    `quoted` é o que faz isto funcionar sem sintaxe: quando o operador usa o
    RESPONDER do WhatsApp sobre a escalação, a mensagem citada é o briefing
    que a própria ponte mandou -- e ele traz o id do lead. Então basta
    escrever a resposta normal, como se falasse com o cliente.

    Duas travas, ambas deliberadas:
    - autoridade é pelo TELEFONE cadastrado, nunca por quem a mensagem diz
      ser;
    - se mais de um lead está esperando e a pessoa não disse qual, a ponte
      PERGUNTA em vez de adivinhar. Aprovar o lead errado é pior que pedir
      para repetir a frase.
    """
    _auth_human_reply(x_api_key)
    payload = await request.json()
    numero = payload.get("from", "")
    texto = payload.get("text", "")
    citada = payload.get("quoted", "") or ""

    operador = _operador_por_telefone(numero)
    if operador is None:
        state.log("gate", None, f"resposta humana de número não autorizado: {numero[-4:]}")
        return {"ok": False, "reply": "Este número não está autorizado a "
                                      "decidir sobre leads."}

    esperando = _leads_esperando()
    foco = esperando[0]["lead_id"] if len(esperando) == 1 else None
    intent = human_intents.parse(texto, lead_em_foco=foco, quoted=citada)

    if intent["needs"]:
        if intent["lead_id"] is None and len(esperando) > 1:
            lista = "\n".join(
                f"  {c.get('contact_name') or 'sem nome'} — {c['lead_id']} "
                f"({c.get('escalation_reason') or '?'})" for c in esperando[:5])
            return {"ok": False, "reply": f"Tem {len(esperando)} leads "
                                          f"esperando. Qual deles?\n{lista}"}
        return {"ok": False, "reply": human_intents.confirmation_prompt(intent)}

    lead_id = intent["lead_id"]
    quem = operador.get("name", operador.get("id", "operador"))
    state.log("human_reply", lead_id, f"{quem} via WhatsApp: {intent['action']} "
                                     f"— {intent['message'][:200]}")

    if intent["action"] == "dont_save":
        return {"ok": True, "reply": "Combinado, não registro isso no Brain."}

    resposta = _aplicar_decisao_humana(lead_id, intent, quem)
    return {"ok": True, "reply": resposta}


def _aplicar_decisao_humana(lead_id: int, intent: dict, quem: str) -> str:
    """Executa a intenção já validada. Mesmas operações do human_reply.py na
    linha de comando -- um só caminho de verdade para decisão humana."""
    acao, mensagem = intent["action"], intent["message"]
    conv = state.get_conversation(lead_id)
    nome = conv.get("contact_name") or f"lead {lead_id}"

    entregue = False
    if mensagem:
        texto = textproc.customer_facing(mensagem)
        entregue = deliver_followup(lead_id, texto, origem="humano")
        if entregue:
            state.update_conversation(lead_id, last_outbound_at=int(time.time()))
            state.log("outbound", lead_id, texto)
        else:
            kommo.add_note(lead_id, f"[resposta de {quem} — enviar manualmente]\n{texto}")
        kommo.add_note(lead_id, f"[resposta de {quem}] {texto}")

    if acao == "close":
        state.transition(lead_id, "CLOSED", f"encerrado por {quem}", by_human=True)
        state.update_conversation(lead_id, realert_count=0)
        return f"{nome}: conversa encerrada."

    # approve / resume / correct / save devolvem a conversa ao agente.
    state.transition(lead_id, "RESUMED", f"respondido por {quem}", by_human=True)
    if mensagem:
        # Fato confirmado DESTE cliente (§7): entra na memória estruturada e
        # é injetado em todo turno futuro -- o Chase continua a conversa
        # sabendo o que foi prometido, e o lead nunca repete a pergunta.
        state.add_confirmation(lead_id, quem,
                               conv.get("pending_question")
                               or conv.get("last_inbound_text") or "",
                               textproc.customer_facing(mensagem))
    state.update_conversation(lead_id, realert_count=0, holding_count=0,
                              pending_question=None)

    if not mensagem:
        return (f"{nome}: liberado e devolvido ao Chase. Você não escreveu "
                f"uma resposta, então ele segue a conversa com o que já sabe. "
                f"Se quiser mandar um texto específico, é só responder esta "
                f"mensagem escrevendo o que ele deve dizer.")
    destino = "entregue no chat" if entregue else "gravada como nota (entrega falhou)"
    aprendizado = _registrar_aprendizado(lead_id, intent, quem, conv)
    return (f"{nome}: resposta {destino} e conversa devolvida ao Chase."
            + (f"\n{aprendizado}" if aprendizado else ""))


def _registrar_aprendizado(lead_id: int, intent: dict, quem: str,
                           conv: dict) -> str:
    """A resposta humana virando conhecimento — o fecho do ciclo.

    Sem isto, a mesma pergunta escala de novo na semana que vem e o humano
    responde a mesma coisa pela terceira vez. O documento nasce como
    candidato (§9): fica pronto para um clique no Obsidian, nunca ativo
    sozinho.

    Nunca deixa a decisão do humano falhar por causa do Brain: o lead já
    recebeu a resposta antes desta linha rodar, e qualquer erro aqui vira
    log, não exceção.
    """
    if intent["action"] == "dont_save":
        return ""
    try:
        resultado = knowledge_writer.registrar(
            pergunta=conv.get("last_inbound_text") or "",
            resposta=intent["message"],
            autor=quem,
            lead_id=lead_id,
            forcar=(intent["action"] == "save"))
        state.log("knowledge", lead_id,
                  f"{resultado['kind']}: {resultado['reason']} "
                  f"({resultado.get('path') or '-'})")
        if not resultado["written"]:
            if resultado["kind"] == "memory":
                return ("Não levei isso pro Brain: parece acordo deste "
                        "cliente, não regra geral. Se for regra, responda "
                        "'salvar isso'.")
            return ""
        knowledge_writer.reindexar()
        return ("Registrei isso no Brain como pendente de revisão — abra o "
                "Obsidian e mude para `approved` para o Chase passar a "
                "responder sozinho da próxima vez.")
    except Exception as exc:
        state.log("error", lead_id, f"knowledge_writer: {exc}")
        return ""

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
    """escalate_to_human(conversation_id, reason, priority, summary, customer_name, requested_action).

    Aceita também o formato antigo ({lead_id, reason, briefing}). Devolve o resultado real:
    caso_criado / caso_existente, humano_notificado, notificacao (enviada|pendente|falhou)."""
    _auth(x_api_key)
    p = await request.json()
    bruto = p.get("conversation_id", p.get("lead_id"))
    try:
        lead_id = int(str(bruto).split(":")[-1])
        if lead_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        raise HTTPException(400, "conversation_id inválido: use o id do lead no Kommo")
    reason = (p.get("reason") or "").strip() or "solicitado pelo agente"
    resultado = escalate(lead_id, reason, p.get("briefing", "") or p.get("summary", ""),
                         prioridade=p.get("priority") or "alta", summary=p.get("summary") or "",
                         customer_name=p.get("customer_name"), requested_action=p.get("requested_action"),
                         category=p.get("category"))
    return {"ok": True, **(resultado or {})}


ESTADOS_DO_PAINEL = {"HUMAN_PENDING", "HUMAN_ACTIVE", "RESOLVED", "RETURNED_TO_AI"}


@app.post("/handoff/estado")
async def handoff_estado(request: Request, x_handoff_token: str | None = Header(None)):
    """O Command Center diz em que estado está o atendimento humano desta conversa.

    Só ele chama (token próprio, X-Handoff-Token — não é a chave que abre o hook do Kommo).
    RETURNED_TO_AI e RESOLVED são as únicas portas de volta para a IA, e levam a nota da pessoa
    como fato confirmado: a IA continua sabendo o que foi combinado."""
    if not handoff_cc.HANDOFF_SYNC_TOKEN or not hmac.compare_digest(
            handoff_cc.HANDOFF_SYNC_TOKEN, x_handoff_token or ""):
        raise HTTPException(401, "invalid handoff token")
    p = await request.json()
    try:
        lead_id = int(p.get("lead_id"))
    except (TypeError, ValueError):
        raise HTTPException(400, "lead_id inválido")
    alvo = p.get("estado")
    if lead_id <= 0 or alvo not in ESTADOS_DO_PAINEL:
        raise HTTPException(400, "lead_id ou estado inválido")
    nota = textproc.customer_facing(str(p.get("nota") or ""))[:1500]
    autor = str(p.get("autor") or "equipe")[:80]
    caso = p.get("caso_id")
    atual = state.get_conversation(lead_id)["state"]
    state.log("human_reply", lead_id, f"painel: caso #{caso} → {alvo} ({autor})")

    if alvo in ("HUMAN_PENDING", "HUMAN_ACTIVE"):
        scheduler.cancel(lead_id, f"atendimento humano #{caso}")
        if atual in ("AI_ACTIVE", "RESUMED"):
            state.transition(lead_id, "WAITING_HUMAN", f"atendimento humano #{caso}")
        if alvo == "HUMAN_ACTIVE":
            state.transition(lead_id, "HUMAN_HANDOFF", f"{autor} assumiu (caso #{caso})")
        state.update_conversation(lead_id, handoff_caso_id=caso)
        return {"ok": True, "estado_ponte": state.get_conversation(lead_id)["state"]}

    # RESOLVED / RETURNED_TO_AI: a conversa volta a ser da IA (na próxima mensagem do cliente,
    # no caso de RESOLVED: sem follow-up até lá)
    if atual == "CLOSED":
        # opt-out ou trilha esgotada: a IA não fala com quem fechou, com caso ou sem
        return {"ok": True, "estado_ponte": "CLOSED", "nota": "conversa encerrada na ponte; a IA não volta"}
    if atual in ("WAITING_HUMAN", "HUMAN_HANDOFF"):
        if not state.transition(lead_id, "RESUMED", f"{autor}: {alvo} (caso #{caso})", by_human=True):
            return {"ok": False, "erro": f"a ponte recusou {atual}->RESUMED"}
    if nota:
        conv = state.get_conversation(lead_id)
        rotulo = "Atendimento encerrado pela equipe" if alvo == "RESOLVED" else "Contexto da equipe ao devolver"
        state.add_confirmation(lead_id, autor, conv.get("pending_question") or conv.get("last_inbound_text") or "",
                               f"{rotulo}: {nota}")
    scheduler.cancel(lead_id, f"atendimento humano #{caso} {alvo}")
    state.update_conversation(lead_id, realert_count=0, holding_count=0, pending_question=None,
                              handoff_caso_id=None)
    return {"ok": True, "estado_ponte": state.get_conversation(lead_id)["state"]}


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
    if op == "stage" and directive_engine.etapa_proibida(p.get("stage")):  # G9 + never_touch + SDR
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

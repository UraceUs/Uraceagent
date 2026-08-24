"""Agendador da ponte — follow-up B2 (3 trilhas, decisão C11) e alarme de
escalação C2 (re-alerta 10–30min, horário comercial de Orlando).

Roda como thread daemon dentro do processo da ponte (iniciada no startup do
FastAPI). Um tick por minuto:

1. **Follow-ups vencidos** — conversas com `followup_track` e
   `next_followup_at <= agora`, ainda em estado vendável (G3 respeitado):
   compõe a mensagem via agente (com o contexto da sessão do lead, para o
   follow-up referenciar a situação real, não um template genérico) e
   entrega. Entrega real = disparar o Salesbot de novo via
   `POST /api/v4/bots/{id}/run` (config FOLLOWUP_BOT_ID): o bot chama o
   widget_request, a ponte reconhece que há follow-up pendente para o lead
   e devolve o texto pelo return_url. Sem FOLLOWUP_BOT_ID configurado, o
   fallback é nota + tarefa no Kommo para um humano enviar.

2. **Re-alertas de escalação** — conversas em WAITING_HUMAN/HUMAN_HANDOFF
   sem ação humana há mais de ESCALATION_REALERT_MIN minutos: reenvia o
   alerta no WhatsApp interno. Só em horário comercial (9h–18h,
   America/New_York); fora dele o re-alerta fica naturalmente segurado até
   as 9h do dia seguinte (decisão C2).

As cadências (instruções, seção Follow-up):
- trilha `initial` (sem resposta à classificação): +2h, +24h, +3d, +7d → fecha
- trilha `link_sent` (link enviado sem resposta): +10min, +24h, +3d, +7d → task humana
- trilha `scheduled` (lead pediu data): um disparo na data pedida (via diretiva)

Regra B2: nunca duas trilhas no mesmo lead — o campo followup_track é um só.
Regra B1: envio espontâneo SÓ daqui (o worker de mensagens nunca inicia).
"""
import threading
import time
import zoneinfo
from datetime import datetime

from config import BUSINESS_HOURS, BUSINESS_TZ, ESCALATION_REALERT_MIN, FOLLOWUP_BOT_ID
from state import db, log, transition, update_conversation

_TZ = zoneinfo.ZoneInfo(BUSINESS_TZ)

# Ofertas de cadência por trilha, em segundos a partir do envio anterior.
TRACKS = {
    "initial": [2 * 3600, 24 * 3600, 3 * 86400, 7 * 86400],
    "link_sent": [10 * 60, 24 * 3600, 3 * 86400, 7 * 86400],
}

# Injetadas pelo app.py no startup (evita import circular): a composição usa
# o agente com a sessão do lead; a entrega usa o circuito do Salesbot.
compose_fn = None      # compose_fn(lead_id, track, attempt) -> str
deliver_fn = None      # deliver_fn(lead_id, text) -> bool  (True = entregue no chat)
notify_fn = None       # notify_fn(text) -> None  (WhatsApp interno)
task_fn = None         # task_fn(lead_id, text, due_ts) -> None (tarefa Kommo)
note_fn = None         # note_fn(lead_id, text) -> None (nota Kommo)


def in_business_hours(now_ts: int | None = None) -> bool:
    now = datetime.fromtimestamp(now_ts or time.time(), tz=_TZ)
    start, end = BUSINESS_HOURS
    return start <= now.hour < end


# ------------------------------------------------------------- agendamento
def start_track(lead_id: int, track: str, now: int | None = None) -> None:
    """Inicia (ou reinicia) uma trilha. Chamada pelo app depois de um envio
    ao lead. Trilha nova substitui a anterior — nunca duas ao mesmo tempo."""
    now = now or int(time.time())
    delays = TRACKS.get(track)
    if not delays:
        return
    update_conversation(lead_id, followup_track=track, followup_attempts=0,
                        next_followup_at=now + delays[0])
    log("followup", lead_id, f"trilha {track} iniciada, 1º toque em +{delays[0]}s")


def schedule_at(lead_id: int, due_ts: int, note: str = "") -> None:
    """Trilha `scheduled` (diretiva [[followup]] com data do lead)."""
    update_conversation(lead_id, followup_track="scheduled", followup_attempts=0,
                        next_followup_at=due_ts, pending_followup_text=None)
    log("followup", lead_id, f"trilha scheduled para {due_ts} ({note[:100]})")


def cancel(lead_id: int, reason: str = "lead respondeu") -> None:
    """Lead respondeu (ou conversa escalou): a trilha ativa morre na hora."""
    update_conversation(lead_id, followup_track=None, next_followup_at=None,
                        followup_attempts=0, pending_followup_text=None)
    log("followup", lead_id, f"trilha cancelada: {reason}")


# ------------------------------------------------------------------ o tick
def tick(now: int | None = None) -> dict:
    """Uma varredura. Devolve contagens (para teste e observabilidade)."""
    now = now or int(time.time())
    fired = realerted = 0
    with db() as conn:
        due = [dict(r) for r in conn.execute(
            "SELECT * FROM conversations WHERE followup_track IS NOT NULL "
            "AND next_followup_at IS NOT NULL AND next_followup_at <= ?", (now,))]
        waiting = [dict(r) for r in conn.execute(
            "SELECT * FROM conversations WHERE state IN ('WAITING_HUMAN','HUMAN_HANDOFF')")]

    for conv in due:
        try:
            _fire_followup(conv, now)
            fired += 1
        except Exception as exc:
            log("error", conv["lead_id"], f"scheduler follow-up: {exc}")

    if in_business_hours(now):
        for conv in waiting:
            try:
                if _maybe_realert(conv, now):
                    realerted += 1
            except Exception as exc:
                log("error", conv["lead_id"], f"scheduler re-alerta: {exc}")

    return {"followups_fired": fired, "realerts": realerted}


def _fire_followup(conv: dict, now: int) -> None:
    lead_id = conv["lead_id"]
    track = conv["followup_track"]
    attempt = conv["followup_attempts"]  # 0-based: este é o (attempt+1)º toque

    # G3 vale aqui também: conversa escalada não recebe follow-up comercial.
    if conv["state"] not in ("AI_ACTIVE", "RESUMED"):
        cancel(lead_id, f"estado {conv['state']} não permite follow-up")
        return

    text = compose_fn(lead_id, track, attempt) if compose_fn else ""
    if text:
        delivered = deliver_fn(lead_id, text) if deliver_fn else False
        if not delivered and note_fn:
            note_fn(lead_id, f"[follow-up {track} #{attempt + 1} — enviar manualmente]\n{text}")
            if task_fn:
                task_fn(lead_id, f"Enviar follow-up ao lead: {text[:120]}", now + 3600)
        log("followup", lead_id,
            f"{track} #{attempt + 1} {'entregue' if delivered else 'fallback nota/tarefa'}")

    # próximo passo da trilha
    if track == "scheduled":
        cancel(lead_id, "follow-up agendado disparado")
        return
    delays = TRACKS[track]
    nxt = attempt + 1
    if nxt < len(delays):
        update_conversation(lead_id, followup_attempts=nxt,
                            next_followup_at=now + delays[nxt])
    else:  # trilha esgotada
        if track == "initial":
            transition(lead_id, "CLOSED", "trilha initial esgotada sem resposta")
            if note_fn:
                note_fn(lead_id, "[follow-up] trilha de classificação esgotada — lead fechado")
        else:  # link_sent: humano decide manter ou fechar
            if task_fn:
                task_fn(lead_id, "Follow-ups de link esgotados — decidir manter ou fechar", now + 86400)
        cancel(lead_id, f"trilha {track} esgotada")


def _maybe_realert(conv: dict, now: int) -> bool:
    last = max(conv.get("last_realert_at") or 0, conv.get("escalated_at") or 0)
    if not last or now - last < ESCALATION_REALERT_MIN * 60:
        return False
    lead_id = conv["lead_id"]
    mins = (now - (conv.get("escalated_at") or now)) // 60
    if notify_fn:
        notify_fn(f"⏰ RE-ALERTA — lead {lead_id} escalado há {mins} min sem ação humana.\n"
                  f"Motivo: {conv.get('escalation_reason') or '?'}\n"
                  f"Responda 'aprovar {lead_id} <instrução>' ou 'retomar {lead_id}'.")
    update_conversation(lead_id, last_realert_at=now)
    log("realert", lead_id, f"re-alerta após {mins} min")
    return True


# ------------------------------------------------------------------ thread
def _loop(interval: int) -> None:
    while True:
        try:
            tick()
        except Exception as exc:
            log("error", None, f"scheduler tick: {exc}")
        time.sleep(interval)


def start(interval: int = 60) -> threading.Thread:
    t = threading.Thread(target=_loop, args=(interval,), daemon=True,
                         name="bridge-scheduler")
    t.start()
    log("scheduler", None,
        f"iniciado (tick {interval}s, realert {ESCALATION_REALERT_MIN}min, "
        f"bot follow-up {'configurado' if FOLLOWUP_BOT_ID else 'NÃO configurado — fallback nota/tarefa'})")
    return t

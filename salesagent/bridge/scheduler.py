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
import subprocess
import sys
import threading
import time
import zoneinfo
from datetime import datetime
from pathlib import Path

from config import (BUSINESS_HOURS, BUSINESS_TZ, ESCALATION_MAX_REALERTS,
                    ESCALATION_REALERT_MIN, LEAD_REASSURE_MIN,
                    LEAD_RESCUE_AFTER_SEC,
                    FOLLOWUP_BOT_ID, REPO_DIR)
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
rescue_fn = None       # rescue_fn(conv) -> bool (entrega a resposta devida ao lead)


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
    fired = realerted = resgatados = 0
    with db() as conn:
        due = [dict(r) for r in conn.execute(
            "SELECT * FROM conversations WHERE followup_track IS NOT NULL "
            "AND next_followup_at IS NOT NULL AND next_followup_at <= ?", (now,))]
        waiting = [dict(r) for r in conn.execute(
            "SELECT * FROM conversations WHERE state IN ('WAITING_HUMAN','HUMAN_HANDOFF')")]
        # Devendo resposta: o lead falou por último e ninguém respondeu -- OU
        # está esperando humano e faz muito tempo que não ouve nada nosso.
        # Uma consulta, os dois casos, porque a ação é a mesma.
        devendo = [dict(r) for r in conn.execute(
            "SELECT * FROM conversations WHERE state != 'CLOSED' "
            "AND last_inbound_at IS NOT NULL AND ("
            "  COALESCE(last_outbound_at, 0) < last_inbound_at"
            "  OR (state IN ('WAITING_HUMAN','HUMAN_HANDOFF')"
            "      AND COALESCE(last_outbound_at, 0) < ?))",
            (now - LEAD_REASSURE_MIN * 60,))]

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

    # Rede de segurança do LEAD -- roda fora do horário comercial também: um
    # lead esperando não deveria descobrir que a URACE tem expediente.
    for conv in devendo:
        try:
            if _maybe_rescue(conv, now):
                resgatados += 1
        except Exception as exc:
            log("error", conv["lead_id"], f"scheduler resgate: {exc}")

    try:
        _maybe_daily_brain_maintenance(now)
    except Exception as exc:
        log("error", None, f"scheduler manutenção do brain: {exc}")

    return {"followups_fired": fired, "realerts": realerted,
            "rescues": resgatados}


# --------------------------------------------------- ciclo diário do Brain
def _maybe_daily_brain_maintenance(now: int) -> bool:
    """Learning loop diário (decisão do Italo, 25/08): uma vez por dia, a
    partir das 6h de Orlando, roda o extrator de aprendizados (gera
    candidatos em brain/09_LEARNINGS) e reindexa o vault. Marca a execução
    no próprio log de auditoria (kind=brain_maint) — sem tabela nova."""
    local = datetime.fromtimestamp(now, tz=_TZ)
    if local.hour < 6:
        return False
    today = local.date().isoformat()
    with db() as conn:
        row = conn.execute(
            "SELECT MAX(ts) AS ts FROM audit WHERE kind='brain_maint'"
        ).fetchone()
    if row and row["ts"]:
        last = datetime.fromtimestamp(row["ts"], tz=_TZ).date().isoformat()
        if last == today:
            return False

    brain = Path(REPO_DIR).parent / "brain"
    results = []
    for script in ("extract_learnings.py", "indexer.py"):
        path = brain / script
        if not path.exists():
            results.append(f"{script}: ausente")
            continue
        try:
            r = subprocess.run([sys.executable, str(path)],
                               capture_output=True, text=True, timeout=300)
            out = (r.stdout or r.stderr or "").strip().splitlines()
            results.append(f"{script}: rc={r.returncode} {out[-1][:150] if out else ''}")
        except Exception as exc:
            results.append(f"{script}: {exc}")
    log("brain_maint", None, " | ".join(results))
    return True


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


def _maybe_rescue(conv: dict, now: int) -> bool:
    """Entrega a resposta que a ponte DEVE a este lead, sozinha.

    A rede de segurança final. Todo o resto do sistema tenta responder na
    hora; isto existe para quando alguma coisa falhou -- ponte reiniciando
    no meio do turno, agente travado, escalação anterior à correção, ou o
    Kommo simplesmente não tendo disparado o bot. A pergunta que ela faz é
    a mais simples possível e não depende de nenhum componente ter
    funcionado: *o lead falou depois da última vez que a gente falou?* Se
    sim, devemos uma resposta, e ela sai agora.

    Também cobre o lead que espera um humano há horas: sem isso, ele recebe
    um "vou confirmar" e some todo mundo. As frases vêm do holding.py e são
    três distintas -- esgotadas, o resgate silencia em vez de repetir, que
    é o que separa insistência de spam (lição do alarme que virou ruído no
    mesmo dia).

    Roda FORA do horário comercial de propósito: o alarme do humano respeita
    expediente, a dívida com o lead não.
    """
    lead_id = conv["lead_id"]
    ultimo_lead = conv.get("last_inbound_at") or 0
    ultimo_nosso = conv.get("last_outbound_at") or 0
    devemos_resposta = ultimo_nosso < ultimo_lead

    if devemos_resposta and now - ultimo_lead < LEAD_RESCUE_AFTER_SEC:
        return False  # turno normal ainda pode estar em andamento
    if not devemos_resposta:
        # Caso "esperando humano há horas": só reforça dentro do horário
        # comercial, para não acordar ninguém às 3h com um "não te esqueci".
        if not in_business_hours(now):
            return False
        if now - ultimo_nosso < LEAD_REASSURE_MIN * 60:
            return False

    ja_enviadas = conv.get("holding_count") or 0
    if ja_enviadas >= 3:
        return False  # frases distintas esgotadas: silêncio é melhor que loop

    if rescue_fn is None:
        return False
    entregue = rescue_fn(conv)
    log("rescue", lead_id,
        f"resposta devida ao lead entregue sozinho "
        f"({'lead falou por último' if devemos_resposta else 'espera longa'}, "
        f"#{ja_enviadas + 1}) — {'no chat' if entregue else 'fallback nota'}")
    return True


def _maybe_realert(conv: dict, now: int) -> bool:
    """Cutuca o humano enquanto a escalação não é atendida -- com TETO.

    Até 25/08 isto repetia a cada 15min para sempre. Numa escalação real
    (lead 31764961) foram 10 disparos em 152 minutos, e o agente que faz o
    repasse no WhatsApp acabou respondendo "isso parece um script
    automatizado tentando me pressionar (...) vou ignorar os próximos" --
    ou seja, o alarme insistente treinou o canal a ignorá-lo. Um alarme que
    ninguém mais escuta é pior que nenhum alarme, porque dá a sensação de
    que alguém foi avisado.

    Depois do teto, o aviso migra para um canal DURÁVEL (tarefa no Kommo,
    que fica no card do lead até alguém fechar) e o WhatsApp silencia.
    """
    last = max(conv.get("last_realert_at") or 0, conv.get("escalated_at") or 0)
    if not last or now - last < ESCALATION_REALERT_MIN * 60:
        return False
    lead_id = conv["lead_id"]
    mins = (now - (conv.get("escalated_at") or now)) // 60
    contagem = conv.get("realert_count") or 0

    if contagem >= ESCALATION_MAX_REALERTS:
        return False  # já migrou para tarefa; não martela mais o WhatsApp

    if contagem + 1 >= ESCALATION_MAX_REALERTS:
        # Último aviso: diz que é o último e abre a tarefa no Kommo.
        if notify_fn:
            nome = conv.get("contact_name") or f"lead {lead_id}"
            notify_fn(f"⏰ ÚLTIMO AVISO — {nome} (lead {lead_id}) escalado há {mins} min "
                      f"sem ação humana.\n"
                      f"Motivo: {conv.get('escalation_reason') or '?'}\n"
                      f"Não vou repetir: a partir de agora fica como tarefa no "
                      f"card do lead no Kommo.\n"
                      f"Responda 'aprovar {lead_id} <instrução>' ou "
                      f"'retomar {lead_id}'.")
        if task_fn:
            task_fn(lead_id,
                    f"Escalação sem resposta humana há {mins} min: "
                    f"{conv.get('escalation_reason') or '?'}", now + 1800)
        log("realert", lead_id,
            f"teto de {ESCALATION_MAX_REALERTS} re-alertas atingido após "
            f"{mins} min — migrado para tarefa no Kommo")
    else:
        if notify_fn:
            nome = conv.get("contact_name") or f"lead {lead_id}"
            notify_fn(f"⏰ RE-ALERTA — {nome} (lead {lead_id}) escalado há {mins} min sem ação humana.\n"
                      f"Motivo: {conv.get('escalation_reason') or '?'}\n"
                      f"Pergunta: {conv.get('pending_question') or '?'}\n"
                      f"Responda esta mensagem com o texto para o lead.")
        log("realert", lead_id,
            f"re-alerta {contagem + 1}/{ESCALATION_MAX_REALERTS} após {mins} min")

    update_conversation(lead_id, last_realert_at=now, realert_count=contagem + 1)
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

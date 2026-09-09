"""Rotinas por horário (hora local de Orlando), rodadas pelo laço do autosync.

Decisões do dono (09/09):
- triagem do Gmail pela IA de manhã, à tarde e à noite (07:00, 13:00, 21:00);
- sondagem das integrações só de manhã e à noite (07:00, 22:00), e não a
  cada ciclo; se uma integração falhar enquanto a IA usa, aí ela re-sonda.

Cada regra em automation_rules com `schedule` (json de "HH:MM") roda uma
vez por horário: a chave "AAAA-MM-DD HH:MM" fica em last_run_at, então um
horário perdido (serviço fora do ar às 07:00) é recuperado no próximo
ciclo, e nunca roda duas vezes. Desligar a regra na tela desliga a rotina.
"""
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from command_center.db import agora, auditar, todos, um

FUSO = ZoneInfo(os.environ.get("CC_FUSO", "America/New_York"))
REPROVA_MIN = 10          # re-sondagem por falha: no máximo uma a cada 10 min por sistema


def chave_devida(schedule, agora_local=None):
    """Último horário de hoje já passado, como chave; None se nenhum passou."""
    agora_local = agora_local or datetime.now(FUSO)
    hoje = agora_local.strftime("%Y-%m-%d")
    passados = []
    for h in schedule or []:
        try:
            hh, mm = [int(x) for x in str(h).split(":")[:2]]
        except ValueError:
            continue
        if (agora_local.hour, agora_local.minute) >= (hh, mm):
            passados.append(f"{hoje} {hh:02d}:{mm:02d}")
    return max(passados) if passados else None


def devidas(con, agora_local=None):
    saida = []
    for r in todos(con, "SELECT * FROM automation_rules WHERE enabled=1 AND schedule IS NOT NULL ORDER BY id"):
        try:
            horarios = json.loads(r["schedule"])
        except ValueError:
            continue
        chave = chave_devida(horarios, agora_local)
        if chave and chave != (r["last_run_at"] or ""):
            saida.append((r, chave))
    return saida


# ------------------------------------------------------------ sondagem
def sondar(con, sistemas=None, por="system"):
    """Uma chamada real por sistema; grava o estado. É o 'Verificar agora' e a rotina."""
    from command_center.providers import SISTEMAS, recarregar, saude
    recarregar()
    saida = {}
    for s in (sistemas or SISTEMAS):
        st, det = saude(s)
        con.execute("UPDATE integrations SET status=?, last_attempt_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
                    "last_success_at=CASE WHEN ? IN ('CONNECTED','DEGRADED') THEN strftime('%Y-%m-%dT%H:%M:%fZ','now') ELSE last_success_at END, "
                    "last_error=CASE WHEN ? IN ('ERROR','DISCONNECTED') THEN ? ELSE NULL END, detail=? WHERE system=?",
                    (st, st, st, json.dumps(det, ensure_ascii=False)[:500], json.dumps(det, ensure_ascii=False), s))
        saida[s] = {"status": st, "detail": det}
    return saida


def sondar_apos_falha(con, sistema, motivo=""):
    """Uma integração falhou no meio do uso (sincronia ou ação da IA): re-sonda
    só ela, no máximo uma vez a cada REPROVA_MIN minutos. Fora disso, a
    sondagem é só de manhã e à noite (decisão do dono)."""
    from command_center.providers import SISTEMAS
    if sistema not in SISTEMAS:
        return None
    i = um(con, "SELECT last_attempt_at FROM integrations WHERE system=?", (sistema,))
    ultimo = (i or {}).get("last_attempt_at") or ""
    try:
        if ultimo and (datetime.utcnow() - datetime.fromisoformat(ultimo[:19])).total_seconds() < REPROVA_MIN * 60:
            return None
    except ValueError:
        pass
    res = sondar(con, [sistema], por="system")
    auditar(con, "integrations.recheck", "system", detail={"sistema": sistema, "motivo": motivo[:200], **res[sistema]})
    return res[sistema]


# --------------------------------------------------------------- rotinas
def _rodar_triagem(con):
    from command_center.api import ia, motor
    from command_center.providers import triagem
    with ia._PARALELO:                                   # nunca junto com outro agente
        return triagem.rodar(con, ia.RUNNER, f"agent:{ia.AGENTE}:triagem-{datetime.now(FUSO).strftime('%Y-%m-%d')}",
                             aprendizados=motor.aprendizados(con), por="agenda")


ROTINAS = {
    "gmail_triagem": _rodar_triagem,
    "sondagem_integracoes": lambda con: sondar(con, por="agenda"),
}


def rodar(con, agora_local=None):
    """Roda o que está na hora. Chamado a cada ciclo do autosync."""
    feitas = []
    for regra, chave in devidas(con, agora_local):
        fn = ROTINAS.get(regra["name"])
        if not fn:
            continue
        con.execute("UPDATE automation_rules SET last_run_at=? WHERE id=?", (chave, regra["id"]))   # antes: se cair, não repete em laço
        try:
            res = fn(con)
            ok = True
        except Exception as e:
            res, ok = {"erro": f"{type(e).__name__}: {str(e)[:300]}"}, False
        con.execute("UPDATE automation_rules SET last_result=? WHERE id=?",
                    (json.dumps({"em": agora(), "horario": chave, "ok": ok, **(res if isinstance(res, dict) else {"res": str(res)[:300]})}, ensure_ascii=False)[:2000], regra["id"]))
        auditar(con, f"agenda.{regra['name']}", "system", detail={"horario": chave, "ok": ok, "res": str(res)[:500]})
        feitas.append((regra["name"], chave, ok))
    return feitas

"""Ponte → Command Center: o `escalate_to_human` de verdade (missão de 14/10).

Até aqui a escalação da ponte avisava o Italo pelo agente `main` do OpenClaw no WhatsApp — um
canal pareado por QR, que é o WhatsApp Web (automação não oficial: D-2026-09-21 proíbe para
produção). Agora o caso vai para o Command Center, que trava a IA, avisa a equipe pelos canais
oficiais (push no celular, chat da equipe, WhatsApp Cloud API) e mostra a fila para alguém
assumir. Ver docs/atendimento-humano.md.

Nada se perde quando o painel está fora do ar: o pedido fica em `handoff_outbox` (SQLite da
ponte) com chave de idempotência e o agendador tenta de novo. Enquanto isso a conversa já está
travada para a IA pelo estado local (WAITING_HUMAN): o painel fora do ar atrasa o aviso, nunca
destrava a conversa.

Configuração em ~/.urace/bridge.env:
  CC_URL              onde o Command Center ouve (padrão http://127.0.0.1:8790)
  CC_API_KEY          chave de API do painel (urk_...), papel OPERATOR, NÃO só-leitura
  HANDOFF_SYNC_TOKEN  segredo que o painel manda em X-Handoff-Token para /handoff/estado
  HANDOFF_LEGADO_OPENCLAW=1  mantém também o aviso antigo pelo OpenClaw (transição)
"""
import json
import time
from contextlib import contextmanager

import httpx

import state
from config import _bridge

CC_URL = (_bridge.get("CC_URL") or "http://127.0.0.1:8790").rstrip("/")
CC_API_KEY = _bridge.get("CC_API_KEY", "")
HANDOFF_SYNC_TOKEN = _bridge.get("HANDOFF_SYNC_TOKEN", "")
LEGADO_OPENCLAW = _bridge.get("HANDOFF_LEGADO_OPENCLAW", "0") == "1"
TIMEOUT_S = 12               # o painel avisa a equipe na mesma chamada; folga dentro da janela de ~58 s do Salesbot
TENTATIVAS_MAX = 20            # ~ um dia de espera crescente; depois fica 'desistiu' e no log

SCHEMA = """
CREATE TABLE IF NOT EXISTS handoff_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL,
    chave TEXT NOT NULL UNIQUE,
    corpo TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pendente',   -- pendente | entregue | desistiu
    tentativas INTEGER NOT NULL DEFAULT 0,
    proxima_em INTEGER NOT NULL DEFAULT 0,
    ultimo_erro TEXT,
    caso_id INTEGER,
    criado_em INTEGER NOT NULL
);
"""


def configurado() -> bool:
    return bool(CC_API_KEY)


@contextmanager
def _db():
    with state.db() as conn:
        conn.executescript(SCHEMA)
        yield conn


def _prioridade(p: str | None) -> str:
    """A ponte fala alta/media/baixa (SDR); o painel, baixa/normal/alta/urgente."""
    p = (p or "alta").strip().lower()
    return {"media": "normal", "média": "normal"}.get(p, p)


def montar(lead_id: int, reason: str, prioridade: str = "alta", summary: str = "",
           customer_name: str | None = None, requested_action: str | None = None,
           category: str | None = None, canal: str | None = None, chave: str | None = None) -> dict:
    conv = state.get_conversation(lead_id)
    chave = chave or f"ponte:{lead_id}:{conv.get('escalated_at') or int(time.time())}"
    return {"conversation_id": f"kommo:{lead_id}", "reason": (reason or "escalado pela ponte")[:500],
            "priority": _prioridade(prioridade), "summary": (summary or "")[:1500] or None,
            "customer_name": customer_name or conv.get("contact_name"),
            "requested_action": requested_action, "category": category, "channel": canal,
            "idempotency_key": chave}


def _post(corpo: dict) -> tuple[dict | None, str | None, bool]:
    """Devolve (resposta, erro, definitivo). `definitivo` = repetir não adianta (400/403)."""
    try:
        r = httpx.post(f"{CC_URL}/ops/api/atendimento/casos", json=corpo, timeout=TIMEOUT_S,
                       headers={"X-API-Key": CC_API_KEY, "Idempotency-Key": corpo["idempotency_key"]})
    except Exception as exc:                               # noqa: BLE001
        return None, f"painel fora do ar: {type(exc).__name__}", False
    if r.status_code in (200, 201):
        try:
            return r.json(), None, True
        except ValueError:
            return None, "resposta do painel ilegível", False
    definitivo = r.status_code in (400, 401, 403, 404, 422)
    return None, f"painel respondeu {r.status_code}: {r.text[:160]}", definitivo


def abrir_caso(lead_id: int, **campos) -> dict:
    """Abre (ou reencontra) o caso no painel. Nunca levanta exceção: falha vira pendência na
    outbox e o resultado diz exatamente isso, para a IA não afirmar o que não aconteceu."""
    if not configurado():
        return {"ok": False, "resultado": "painel_nao_configurado", "humano_notificado": False,
                "notificacao": "pendente"}
    corpo = montar(lead_id, **campos)
    with _db() as conn:
        conn.execute("INSERT OR IGNORE INTO handoff_outbox (lead_id, chave, corpo, criado_em) VALUES (?,?,?,?)",
                     (lead_id, corpo["idempotency_key"], json.dumps(corpo), int(time.time())))
    return _tentar(corpo["idempotency_key"])


def _tentar(chave: str) -> dict:
    with _db() as conn:
        linha = conn.execute("SELECT * FROM handoff_outbox WHERE chave=?", (chave,)).fetchone()
    if not linha:
        return {"ok": False, "resultado": "falhou", "erro": "pedido sumiu da fila"}
    linha = dict(linha)
    if linha["status"] == "entregue":
        return {"ok": True, "resultado": "caso_existente", "caso_id": linha["caso_id"]}
    corpo = json.loads(linha["corpo"])
    resposta, erro, definitivo = _post(corpo)
    n = linha["tentativas"] + 1
    with _db() as conn:
        if resposta:
            conn.execute("UPDATE handoff_outbox SET status='entregue', tentativas=?, caso_id=?, ultimo_erro=NULL "
                         "WHERE chave=?", (n, resposta.get("caso_id"), chave))
        else:
            status = "desistiu" if definitivo or n >= TENTATIVAS_MAX else "pendente"
            espera = min(2 ** n, 3600)
            conn.execute("UPDATE handoff_outbox SET status=?, tentativas=?, ultimo_erro=?, proxima_em=? WHERE chave=?",
                         (status, n, (erro or "")[:300], int(time.time()) + espera, chave))
    if resposta:
        # kind 'handoff', não 'escalation': o extrator de aprendizados agrupa 'escalation' pelo
        # texto do MOTIVO (brain/extract_learnings.py); linha de controle ali vira candidato falso.
        state.log("handoff", linha["lead_id"],
                  f"caso #{resposta.get('caso_id')} no painel: {resposta.get('resultado')}, "
                  f"aviso {resposta.get('notificacao')}, ia_bloqueada={resposta.get('ia_bloqueada')}")
        return resposta
    state.log("error", linha["lead_id"], f"handoff para o painel não saiu ({erro}); "
                                        f"{'desistiu' if definitivo else 'fica na fila'}")
    return {"ok": False, "resultado": "pendente" if not definitivo else "falhou", "erro": erro,
            "humano_notificado": False, "notificacao": "pendente",
            "instrucao_para_ia": "O caso não chegou ao painel ainda. Não diga ao cliente que alguém foi avisado."}


def reenviar_pendentes(agora: int | None = None) -> int:
    """O agendador chama a cada volta: o que ficou para trás sai quando o painel voltar."""
    if not configurado():
        return 0
    agora = agora or int(time.time())
    with _db() as conn:
        chaves = [r["chave"] for r in conn.execute(
            "SELECT chave FROM handoff_outbox WHERE status='pendente' AND proxima_em<=? ORDER BY id LIMIT 20", (agora,))]
    return sum(1 for c in chaves if _tentar(c).get("ok"))


def pendentes() -> list[dict]:
    with _db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, lead_id, chave, status, tentativas, ultimo_erro, caso_id FROM handoff_outbox "
            "WHERE status!='entregue' ORDER BY id DESC LIMIT 50")]

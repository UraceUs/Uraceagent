"""Máquina de estados e auditoria — SQLite local (~/.urace/salesbridge.db).

Estados (missão §19): AI_ACTIVE → WAITING_HUMAN → HUMAN_HANDOFF → RESUMED → CLOSED.
Regra G3: conversa escalada não volta a vender; retomada só por comando humano.
"""
import sqlite3
import time
from contextlib import contextmanager

from config import DB_PATH

VALID_STATES = {"AI_ACTIVE", "WAITING_HUMAN", "HUMAN_HANDOFF", "RESUMED", "CLOSED"}

# Transições permitidas — qualquer outra é recusada, venha de onde vier.
ALLOWED = {
    ("AI_ACTIVE", "WAITING_HUMAN"),
    ("AI_ACTIVE", "CLOSED"),
    ("WAITING_HUMAN", "HUMAN_HANDOFF"),
    ("WAITING_HUMAN", "RESUMED"),      # humano respondeu e devolveu ao agente
    ("WAITING_HUMAN", "CLOSED"),       # humano decidiu encerrar sem devolver ao
    # agente. Faltava até 26/08: o estado mais comum de um lead esperando
    # decisão era justamente o único de onde o humano NÃO podia encerrar.
    # Descoberto pelo teste do loop do WhatsApp -- "fechar <lead>" era
    # aceito, logado, e silenciosamente recusado pela máquina de estados.
    ("HUMAN_HANDOFF", "RESUMED"),      # somente por comando humano explícito
    ("HUMAN_HANDOFF", "CLOSED"),
    ("RESUMED", "AI_ACTIVE"),
    ("RESUMED", "WAITING_HUMAN"),
    ("RESUMED", "CLOSED"),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    lead_id INTEGER PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'AI_ACTIVE',
    -- qualificação (portão G1): preço só sai quando os dois campos existem
    q_experience TEXT,          -- first_time | recreational | competes
    q_origin TEXT,              -- local | traveler
    driver_age INTEGER,
    followup_attempts INTEGER NOT NULL DEFAULT 0,
    last_inbound_at INTEGER,
    last_outbound_at INTEGER,
    escalated_at INTEGER,
    escalation_reason TEXT,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    lead_id INTEGER,
    kind TEXT NOT NULL,          -- inbound|outbound|gate|transition|escalation|human_reply|error
    detail TEXT
);
"""


# Colunas adicionadas depois do schema original (21/08, agendador de
# follow-up B2 + alarme C2). SQLite não tem ADD COLUMN IF NOT EXISTS, então
# cada uma roda num try/except — bancos novos e antigos convergem iguais.
_MIGRATIONS = [
    "ALTER TABLE conversations ADD COLUMN followup_track TEXT",          # initial|link_sent|scheduled|NULL
    "ALTER TABLE conversations ADD COLUMN next_followup_at INTEGER",
    "ALTER TABLE conversations ADD COLUMN last_realert_at INTEGER",
    "ALTER TABLE conversations ADD COLUMN pending_followup_text TEXT",   # aguardando entrega via bots/run
    "ALTER TABLE conversations ADD COLUMN holding_count INTEGER",        # msgs de espera já enviadas (holding.py)
    "ALTER TABLE conversations ADD COLUMN realert_count INTEGER",        # re-alertas já disparados (teto no scheduler)
    "ALTER TABLE conversations ADD COLUMN contact_name TEXT",            # nome do lead no Kommo (escalação legível)
    "ALTER TABLE conversations ADD COLUMN last_inbound_text TEXT",       # última fala do lead (idioma p/ resgate)
    "ALTER TABLE conversations ADD COLUMN pending_question TEXT",        # a pergunta que espera resposta humana
]


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        for mig in _MIGRATIONS:
            try:
                conn.execute(mig)
            except sqlite3.OperationalError:
                pass  # coluna já existe
        yield conn
        conn.commit()
    finally:
        conn.close()


def log(kind: str, lead_id: int | None = None, detail: str = "") -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO audit (ts, lead_id, kind, detail) VALUES (?,?,?,?)",
            (int(time.time()), lead_id, kind, detail[:4000]),
        )


def get_conversation(lead_id: int) -> dict:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE lead_id=?", (lead_id,)
        ).fetchone()
        if row is None:
            # Insere e relê usando a MESMA conexão -- nunca recursar em
            # get_conversation() aqui: isso abriria uma segunda conexão
            # sqlite3 antes da primeira commitar/fechar e travava com
            # "database is locked" no primeiro contato de qualquer lead
            # novo (achado testando directives.py em 21/08).
            conn.execute(
                "INSERT INTO conversations (lead_id, updated_at) VALUES (?,?)",
                (lead_id, int(time.time())),
            )
            row = conn.execute(
                "SELECT * FROM conversations WHERE lead_id=?", (lead_id,)
            ).fetchone()
        return dict(row)


def update_conversation(lead_id: int, **fields) -> None:
    if not fields:
        return
    get_conversation(lead_id)  # garante a linha antes do UPDATE (achado 21/08:
    # sem isso, o primeiro update de um lead novo virava um UPDATE sem
    # nenhuma linha pra bater, e os dados eram perdidos em silêncio)
    cols = ", ".join(f"{k}=?" for k in fields)
    with db() as conn:
        conn.execute(
            f"UPDATE conversations SET {cols}, updated_at=? WHERE lead_id=?",
            (*fields.values(), int(time.time()), lead_id),
        )


def transition(lead_id: int, to_state: str, reason: str = "", by_human: bool = False) -> bool:
    """Aplica transição de estado. HUMAN_HANDOFF→RESUMED exige by_human=True."""
    assert to_state in VALID_STATES, f"estado inválido: {to_state}"
    conv = get_conversation(lead_id)
    frm = conv["state"]
    if frm == to_state:
        return True
    if (frm, to_state) not in ALLOWED:
        log("transition", lead_id, f"RECUSADA {frm}->{to_state} ({reason})")
        return False
    if frm == "HUMAN_HANDOFF" and to_state == "RESUMED" and not by_human:
        log("transition", lead_id, f"RECUSADA sem autorização humana: {frm}->{to_state}")
        return False
    fields = {"state": to_state}
    if to_state in ("WAITING_HUMAN", "HUMAN_HANDOFF"):
        fields["escalated_at"] = int(time.time())
        fields["escalation_reason"] = reason
    update_conversation(lead_id, **fields)
    log("transition", lead_id, f"{frm}->{to_state} ({reason})")
    return True


def agent_may_sell(lead_id: int) -> bool:
    """G3: em estado escalado o agente não vende, não importa o que chegue."""
    return get_conversation(lead_id)["state"] in ("AI_ACTIVE", "RESUMED")

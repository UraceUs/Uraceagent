"""Acesso ao banco do Command Center. SQLite, sem ORM.

Uma conexão por requisição (FastAPI injeta via `get_db`), `Row` como
dict, `foreign_keys` ligado. O esquema é aplicado em toda subida — cada
bloco de schema.sql é idempotente.

O arquivo do banco fica FORA do repositório, em ~/.urace/ por padrão,
ao lado dos outros segredos (permissão 600).
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(AQUI, "schema.sql")
URACE_DIR = os.environ.get("URACE_DIR", os.path.expanduser("~/.urace"))
def db_path():
    """Lido a cada chamada: testes e serviços trocam pelo ambiente."""
    return os.environ.get("CC_DB_PATH", os.path.join(
        os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "command-center.sqlite"))


def agora():
    """ISO-8601 em UTC com milissegundos — o mesmo formato do schema."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def conectar(caminho=None):
    caminho = caminho or db_path()
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    novo = not os.path.exists(caminho)
    # check_same_thread=False: o FastAPI abre a dependência num thread do pool
    # e roda o endpoint em outro. A conexão é de UMA requisição, nunca é
    # compartilhada entre duas ao mesmo tempo, então é seguro.
    con = sqlite3.connect(caminho, timeout=10, isolation_level=None,  # autocommit
                          check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 10000")
    if novo:
        try:
            os.chmod(caminho, 0o600)
        except OSError:
            pass
    return con


# Colunas acrescentadas depois do primeiro deploy: CREATE TABLE IF NOT EXISTS
# não as adiciona em banco existente; cada linha aqui é idempotente.
MIGRACOES = [
    ("tasks", "fields", "TEXT"),          # campos personalizados do Asana (json)
    ("tasks", "section_gid", "TEXT"),
    ("emails", "snippet", "TEXT"),
    ("emails", "is_inbox", "INTEGER NOT NULL DEFAULT 1"),
    ("emails", "messages", "INTEGER"),
    ("emails", "suggested_label", "TEXT"),   # sugestão da IA/regras: para onde mover
    ("emails", "suggested_reason", "TEXT"),
    ("emails", "suggested_by", "TEXT"),      # rules | ia | label (já tinha marcador)
    ("emails", "suggested_at", "TEXT"),
    ("emails", "triaged_at", "TEXT"),        # triagem automática da IA (manhã/tarde/noite)
    ("emails", "triage_reason", "TEXT"),
    ("emails", "needs_human", "INTEGER NOT NULL DEFAULT 0"),  # movido pela IA, mas pede resposta humana
    ("automation_rules", "schedule", "TEXT"),      # json: ["07:00","13:00","21:00"] hora local (Orlando)
    ("automation_rules", "last_run_at", "TEXT"),   # chave do último horário rodado: "2026-09-09 07:00"
    ("automation_rules", "last_result", "TEXT"),
    ("races", "task_id", "INTEGER"),
    ("clients", "email_alt", "TEXT"),              # segundo e-mail da descrição (o principal fica limpo)               # tarefa da coluna RACES (calendário = o que está no Asana)
    ("waivers", "hidden", "INTEGER NOT NULL DEFAULT 0"),   # lixeira do painel (restaurável)
    ("waivers", "minor_name", "TEXT"),                     # nome do menor (parental), do form data
    ("waivers", "link_reason", "TEXT"),                    # por que está ligada a este cliente
    ("waivers", "link_by", "TEXT"),                        # sync | human
    ("clients", "status_locked", "INTEGER NOT NULL DEFAULT 0"),  # status mudado à mão não é recalculado
    ("clients", "last_service_at", "TEXT"),
    ("clients", "scanned_at", "TEXT"),                     # última varredura Gmail/DocuSign deste cliente
    ("emails", "handled_by", "TEXT"),                      # user:<id> | auto
    ("emails", "handled_reason", "TEXT"),
    ("clients", "monthly_plan", "TEXT"),                  # ex.: "Academy 4 stroke" — gera a invoice do dia 1
    ("clients", "monthly_note", "TEXT"),                  # ajustes do plano (extra, desconto de contrato)
    ("clients", "plan_type", "TEXT"),                     # monthly | daily
    ("clients", "pro_driver", "INTEGER NOT NULL DEFAULT 0"),  # estrela: pronto para competir
    ("clients", "chassis_id", "INTEGER"),
    ("clients", "engine_id", "INTEGER"),
    ("clients", "equipment_notes", "TEXT"),
    ("invoices", "memo", "TEXT"),                         # ex.: "Urace Academy Training Program + Tuner [August, 2026]"
    ("invoices", "customer_email", "TEXT"),
]


def aplicar_schema(con):
    with open(SCHEMA, encoding="utf-8") as f:
        con.executescript(f.read())
    for tabela, coluna, tipo in MIGRACOES:
        existentes = {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    for sql in POS_MIGRACAO:
        con.execute(sql)


# Sementes que dependem de coluna criada por migração (rodam depois dela).
# Horários em hora local de Orlando; quem lê é command_center/api/agenda.py.
POS_MIGRACAO = [
    """INSERT OR IGNORE INTO automation_rules (name, enabled, trigger, conditions, actions) VALUES
       ('gmail_triagem', 1, '{"schedule":true}', NULL,
        '{"ia":"ler cada e-mail da inbox, aplicar os marcadores e mover para o marcador principal"}')""",
    """INSERT OR IGNORE INTO automation_rules (name, enabled, trigger, conditions, actions) VALUES
       ('sondagem_integracoes', 1, '{"schedule":true}', NULL,
        '{"sistema":"sondar cada integração com uma chamada real; fora do horário, só se uma falhar"}')""",
    """UPDATE automation_rules SET schedule='["07:00","13:00","21:00"]' WHERE name='gmail_triagem' AND schedule IS NULL""",
    """UPDATE automation_rules SET schedule='["07:00","22:00"]' WHERE name='sondagem_integracoes' AND schedule IS NULL""",
]


@contextmanager
def transacao(con):
    """BEGIN/COMMIT explícitos; rollback em exceção."""
    con.execute("BEGIN")
    try:
        yield con
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


# ------------------------------------------------------------ helpers
def um(con, sql, params=()):
    r = con.execute(sql, params).fetchone()
    return dict(r) if r else None


def todos(con, sql, params=()):
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def inserir(con, tabela, **campos):
    cols = ", ".join(campos)
    marks = ", ".join("?" for _ in campos)
    cur = con.execute(f"INSERT INTO {tabela} ({cols}) VALUES ({marks})",
                      tuple(campos.values()))
    return cur.lastrowid


def atualizar(con, tabela, id_, **campos):
    sets = ", ".join(f"{k} = ?" for k in campos)
    con.execute(f"UPDATE {tabela} SET {sets} WHERE id = ?",
                (*campos.values(), id_))


def auditar(con, event, actor, user_id=None, entity_type=None, entity_id=None,
            detail=None, ip=None):
    """Grava no audit_logs. `detail` vira JSON; nunca passe segredo aqui."""
    inserir(con, "audit_logs", event=event, actor=actor, user_id=user_id,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            detail=json.dumps(detail, ensure_ascii=False) if detail is not None else None,
            ip=ip)


# ------------------------------------------------------------ FastAPI
def get_db():
    con = conectar()
    try:
        yield con
    finally:
        con.close()

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


def aplicar_schema(con):
    with open(SCHEMA, encoding="utf-8") as f:
        con.executescript(f.read())


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

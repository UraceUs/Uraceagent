#!/usr/bin/env python3
"""Indexador do Sales Brain — Markdown do vault → índice de busca SQLite FTS5.

Porta da lógica do pipeline legado (`legacy-v1/kb/indexer.py`) para o stack
atual: mesma disciplina (indexação incremental por hash de conteúdo, poda de
órfãos, self-test sem custo), alvo diferente (SQLite FTS5 em vez de
Postgres/pgvector — decisão D2 da auditoria: a solução mais simples que
funciona; embeddings só se a busca léxica se provar insuficiente).

O que entra no índice:
  - arquivos .md fora de pastas iniciadas por "_" (dashboards e meta são
    navegação humana, não conhecimento retrievável)
  - com frontmatter cujo `status` seja approved ou active
  - cujo `type` seja de conhecimento (company/product/sales/learning/faq)
    -- type: system nunca é entregue ao agente

Cross-idioma: o conteúdo é em português (decisão do Italo, 25/08), mas
leads escrevem em EN/ES. O campo `aliases:` do frontmatter (palavras-chave
em inglês) entra no índice com peso alto e faz a ponte léxica.

Uso:
    python3 brain/indexer.py --self-test          # sem banco real, sem custo
    python3 brain/indexer.py --dry-run            # mostra o plano
    python3 brain/indexer.py                      # indexa (incremental)
    python3 brain/indexer.py --query "own kart"   # testa uma busca
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

BRAIN_DIR = Path(__file__).resolve().parent
REPO_DIR = BRAIN_DIR.parent

INDEXABLE_TYPES = {"company_knowledge", "product_knowledge",
                   "sales_knowledge", "learning", "faq"}
INDEXABLE_STATUS = {"approved", "active"}

MAX_CHARS = 1600
OVERLAP_CHARS = 200


def default_db_path() -> Path:
    if os.environ.get("BRAIN_INDEX_PATH"):
        return Path(os.environ["BRAIN_INDEX_PATH"])
    urace = Path(os.environ.get("URACE_DIR", Path.home() / ".urace"))
    return urace / "brain-index.db"


# ------------------------------------------------------------- frontmatter
def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parser mínimo (stdlib) do frontmatter YAML usado no Brain: chave:
    valor escalares e listas [a, b] ou em linhas com '- '. Suficiente para o
    schema documentado em _meta/README.md — schema simples de propósito."""
    meta: dict = {}
    if not text.startswith("---"):
        return meta, text
    end = text.find("\n---", 3)
    if end == -1:
        return meta, text
    body = text[end + 4:].lstrip("\n")
    block = text[3:end].strip("\n")
    current_list_key = None
    for line in block.splitlines():
        if not line.strip():
            continue
        if current_list_key and line.lstrip().startswith("- "):
            meta.setdefault(current_list_key, []).append(
                line.lstrip()[2:].strip())
            continue
        current_list_key = None
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not value:
            current_list_key = key
            meta[key] = []
        elif value.startswith("[") and value.endswith("]"):
            meta[key] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key] = value
    return meta, body


# ---------------------------------------------------------------- chunking
def chunk_text(text: str) -> list[str]:
    """Por parágrafo, empacotando até MAX_CHARS (mesma lógica do legado:
    parágrafo é uma ideia; cortar no meio produz trecho que ranqueia bem e
    lê como nada)."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for para in paragraphs:
        if len(para) > MAX_CHARS:
            if current:
                chunks.append("\n\n".join(current))
                current, size = [], 0
            chunks.extend(_split_long(para))
            continue
        if size + len(para) > MAX_CHARS and current:
            chunks.append("\n\n".join(current))
            current, size = [], 0
        current.append(para)
        size += len(para) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _split_long(para: str) -> list[str]:
    out, start = [], 0
    while start < len(para):
        end = min(start + MAX_CHARS, len(para))
        if end < len(para):
            cut = para.rfind(" ", start, end)
            if cut > start:
                end = cut
        out.append(para[start:end].strip())
        start = max(end - OVERLAP_CHARS, end)
    return [c for c in out if c]


def file_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


# ------------------------------------------------------------------ schema
SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (
    path TEXT PRIMARY KEY,
    hash TEXT NOT NULL,
    title TEXT, type TEXT, category TEXT, topic TEXT,
    priority TEXT, status TEXT, last_updated TEXT,
    indexed_at INTEGER
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
    text, title, topic, aliases, tags,
    path UNINDEXED, type UNINDEXED, category UNINDEXED,
    priority UNINDEXED, last_updated UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


def open_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# ---------------------------------------------------------------- pipeline
def discover(vault: Path) -> list[Path]:
    out = []
    for p in sorted(vault.rglob("*.md")):
        rel = p.relative_to(vault)
        if any(part.startswith("_") for part in rel.parts):
            continue
        out.append(p)
    return out


def plan_file(path: Path, vault: Path) -> dict | None:
    """None = fora do índice (status/type). Reportado, nunca silencioso."""
    raw = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(raw)
    status = str(meta.get("status", "")).lower()
    dtype = str(meta.get("type", "")).lower()
    entry = {
        "path": str(path.relative_to(vault)),
        "hash": file_hash(raw),
        "title": path.stem,
        "type": dtype, "status": status,
        "category": str(meta.get("category", "")),
        "topic": str(meta.get("topic", "")),
        "priority": str(meta.get("priority", "medium")).lower(),
        "last_updated": str(meta.get("last_updated", "")),
        "aliases": " ".join(meta.get("aliases", []) if isinstance(meta.get("aliases"), list) else [str(meta.get("aliases", ""))]),
        "tags": " ".join(meta.get("tags", []) if isinstance(meta.get("tags"), list) else [str(meta.get("tags", ""))]),
        "body": body,
    }
    if status not in INDEXABLE_STATUS or dtype not in INDEXABLE_TYPES:
        entry["excluded"] = True
    return entry


def index_vault(vault: Path, db_path: Path, dry_run: bool = False) -> dict:
    stats = {"indexed": 0, "unchanged": 0, "excluded": 0, "pruned": 0,
             "chunks": 0}
    entries = [plan_file(p, vault) for p in discover(vault)]
    conn = open_db(db_path)
    try:
        live = {r["path"]: r["hash"]
                for r in conn.execute("SELECT path, hash FROM docs")}
        wanted_paths = set()
        for e in entries:
            if e.get("excluded"):
                stats["excluded"] += 1
                continue  # e se estava indexado antes? cai na poda abaixo
            wanted_paths.add(e["path"])
            if live.get(e["path"]) == e["hash"]:
                stats["unchanged"] += 1
                continue
            pieces = chunk_text(e["body"])
            stats["indexed"] += 1
            stats["chunks"] += len(pieces)
            if dry_run:
                continue
            conn.execute("DELETE FROM chunks WHERE path = ?", (e["path"],))
            for piece in pieces:
                conn.execute(
                    "INSERT INTO chunks (text, title, topic, aliases, tags, "
                    " path, type, category, priority, last_updated) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (piece, e["title"], e["topic"], e["aliases"], e["tags"],
                     e["path"], e["type"], e["category"], e["priority"],
                     e["last_updated"]))
            conn.execute(
                "INSERT INTO docs (path, hash, title, type, category, topic, "
                " priority, status, last_updated, indexed_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(path) DO UPDATE SET hash=excluded.hash, "
                " title=excluded.title, type=excluded.type, "
                " category=excluded.category, topic=excluded.topic, "
                " priority=excluded.priority, status=excluded.status, "
                " last_updated=excluded.last_updated, "
                " indexed_at=excluded.indexed_at",
                (e["path"], e["hash"], e["title"], e["type"], e["category"],
                 e["topic"], e["priority"], e["status"], e["last_updated"],
                 int(time.time())))

        # PODA: some do vault, muda para candidate, vira type system — sai
        # do índice. Um chunk órfão é pior que um ausente (lição do legado).
        for path in set(live) - wanted_paths:
            stats["pruned"] += 1
            if not dry_run:
                conn.execute("DELETE FROM chunks WHERE path = ?", (path,))
                conn.execute("DELETE FROM docs WHERE path = ?", (path,))
        if not dry_run:
            conn.commit()
    finally:
        conn.close()
    return stats


# ------------------------------------------------------------------- busca
_PRIORITY_BOOST = {"high": -1.0, "medium": 0.0, "low": 1.0}


def _fts_query(text: str) -> str:
    tokens = re.findall(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]{3,}", text.lower())
    seen, out = set(), []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(f'"{t}"')
    return " OR ".join(out[:24])


def search(query: str, db_path: Path | None = None, top_docs: int = 3,
           char_budget: int = 3500) -> list[dict]:
    """Top documentos para a query. Ranqueamento: relevância BM25 (título/
    topic/aliases pesam mais que corpo) + boost de priority + recência como
    desempate — a política de conflito de _meta/README.md em código."""
    db_path = db_path or default_db_path()
    if not db_path.exists():
        return []
    q = _fts_query(query)
    if not q:
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT text, title, topic, path, type, category, priority, "
            " last_updated, bm25(chunks, 1.0, 4.0, 6.0, 5.0, 2.0) AS rank "
            "FROM chunks WHERE chunks MATCH ? ORDER BY rank LIMIT 24", (q,)
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    best: dict[str, dict] = {}
    for r in rows:
        score = r["rank"] + _PRIORITY_BOOST.get(r["priority"], 0.0)
        cur = best.get(r["path"])
        if cur is None or score < cur["score"]:
            best[r["path"]] = {
                "path": r["path"], "title": r["title"], "type": r["type"],
                "category": r["category"], "topic": r["topic"],
                "priority": r["priority"], "last_updated": r["last_updated"],
                "text": r["text"], "score": round(score, 3),
            }
    ordered = sorted(best.values(),
                     key=lambda d: (d["score"], d["last_updated"] or "",))
    results, used = [], 0
    for doc in ordered[:top_docs]:
        text = doc["text"][:1200]
        if used + len(text) > char_budget:
            break
        used += len(text)
        doc["text"] = text
        results.append(doc)
    return results


# --------------------------------------------------------------- self-test
def self_test() -> int:
    import tempfile
    failures = []

    def check(label, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  {detail}" if not cond else ""))
        if not cond:
            failures.append(label)

    with tempfile.TemporaryDirectory() as td:
        vault = Path(td) / "brain"
        db = Path(td) / "index.db"
        (vault / "02_SALES").mkdir(parents=True)
        (vault / "_meta").mkdir()

        (vault / "02_SALES" / "Objecoes.md").write_text(
            "---\ntype: sales_knowledge\ncategory: objection\ntopic: preco\n"
            "priority: high\nstatus: approved\nsource: internal\n"
            "last_updated: 2026-08-25\ntags: [vendas, preco]\n"
            "aliases: [expensive, discount, price]\n---\n"
            "Nunca disputar o número. Subir de custo para valor.\n\n"
            "Após duas recusas educadas, parar de empurrar.\n",
            encoding="utf-8")
        (vault / "02_SALES" / "Rascunho.md").write_text(
            "---\ntype: sales_knowledge\ncategory: draft\ntopic: rascunho\n"
            "priority: low\nstatus: candidate\nsource: internal\n"
            "last_updated: 2026-08-25\ntags: []\n---\nIdeia solta.\n",
            encoding="utf-8")
        (vault / "02_SALES" / "Sistema.md").write_text(
            "---\ntype: system\ncategory: x\ntopic: x\npriority: high\n"
            "status: active\nsource: internal\nlast_updated: 2026-08-25\n"
            "tags: []\n---\nDoc de sistema nao vai pro agente.\n",
            encoding="utf-8")
        (vault / "_meta" / "README.md").write_text("# meta\n", encoding="utf-8")

        print("frontmatter")
        meta, body = parse_frontmatter(
            (vault / "02_SALES" / "Objecoes.md").read_text(encoding="utf-8"))
        check("campos escalares lidos", meta.get("status") == "approved")
        check("lista inline lida", meta.get("aliases") == ["expensive", "discount", "price"])
        check("corpo separado do frontmatter", body.startswith("Nunca disputar"))

        print("\nindexação")
        stats = index_vault(vault, db)
        check("só o aprovado entra", stats["indexed"] == 1, str(stats))
        check("candidate e system excluídos", stats["excluded"] == 2, str(stats))
        stats2 = index_vault(vault, db)
        check("segunda passada é incremental (0 reindex)",
              stats2["indexed"] == 0 and stats2["unchanged"] == 1, str(stats2))

        print("\nbusca")
        hits = search("preco caro", db_path=db)
        check("busca em português encontra", len(hits) == 1, str(hits))
        hits_en = search("too expensive, any discount?", db_path=db)
        check("busca em inglês encontra via aliases", len(hits_en) == 1)
        check("candidate é invisível",
              all("Rascunho" not in h["title"] for h in hits))
        check("query vazia não explode", search("", db_path=db) == [])
        check("query sem match devolve vazio",
              search("xyzabc quantum", db_path=db) == [])

        print("\npoda")
        (vault / "02_SALES" / "Objecoes.md").write_text(
            "---\ntype: sales_knowledge\ncategory: objection\ntopic: preco\n"
            "priority: high\nstatus: review_required\nsource: internal\n"
            "last_updated: 2026-08-26\ntags: []\n---\nEm revisão.\n",
            encoding="utf-8")
        stats3 = index_vault(vault, db)
        check("rebaixado para review_required sai do índice",
              stats3["pruned"] == 1, str(stats3))
        check("e a busca não o encontra mais", search("preco", db_path=db) == [])

    print()
    if failures:
        print(f"SELF TEST FALHOU — {len(failures)} checagens")
        return 1
    print("SELF TEST PASSOU — parsing, incremental, filtro de status, "
          "cross-idioma e poda verificados")
    return 0


# -------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="Indexa o Sales Brain (FTS5).")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--query", help="testa uma busca contra o índice real")
    ap.add_argument("--vault", type=Path, default=BRAIN_DIR)
    ap.add_argument("--db", type=Path, default=None)
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    db_path = args.db or default_db_path()
    if args.query:
        t0 = time.time()
        hits = search(args.query, db_path=db_path)
        ms = int((time.time() - t0) * 1000)
        print(f"{len(hits)} documento(s) em {ms}ms para: {args.query!r}\n")
        for h in hits:
            print(f"[{h['score']}] {h['title']}  ({h['path']})")
            print(f"   {h['text'][:180]}...\n")
        return 0

    stats = index_vault(args.vault, db_path, dry_run=args.dry_run)
    label = "plano (dry-run)" if args.dry_run else "indexado"
    print(f"{label}: {stats['indexed']} docs ({stats['chunks']} chunks), "
          f"{stats['unchanged']} inalterados, {stats['excluded']} fora do "
          f"índice (status/type), {stats['pruned']} podados")
    print(f"índice: {db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Knowledge base indexer — closes the seam the catalog sync leaves open.

The sync prints which program slugs changed and stops. This turns those into
retrievable knowledge, in four steps:

    generate   build auto_generated documents from the catalog
    chunk      split into passages
    embed      only what actually changed
    prune      delete chunks whose source text no longer exists

The fourth step is the one that matters most and is easiest to forget. An
orphaned chunk is worse than a missing one: the agent retrieves a description
that was deleted from the sheet weeks ago, grounds an answer in it, and nothing
anywhere reports an error.

Usage:
    python kb/indexer.py --self-test            # fake provider, no key, no cost
    python kb/indexer.py --dry-run              # show the plan, write nothing
    python kb/indexer.py --programs one_day     # reindex specific slugs
    python kb/indexer.py                        # full pass
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from embed import get_provider, assert_matches_schema  # noqa: E402


# =============================================================================
# DOCUMENT GENERATION
# =============================================================================

# Which catalog fields become prose the agent can retrieve. Order matters: it
# is the order a person would explain the program in.
PROSE_FIELDS = [
    ("description", ""),
    ("objective", "What it's for: "),
    ("target_audience", "Who it's for: "),
    ("benefits", "Benefits: "),
    ("differentiators", "What makes it different: "),
    ("prerequisites", "Requirements: "),
]


def build_program_document(program: dict) -> str | None:
    """Prose for one program, or None if there is nothing grounded to say.

    None is a real outcome, not a failure. A program whose description has not
    been filled in yet must produce NO document — because a thin or empty
    document is worse than none. An empty passage still scores against a query,
    still comes back as a "hit", and the agent then treats retrieval as having
    succeeded. No document means the search returns nothing, which is the signal
    the FAQ mode is built to handle: say the team will confirm.
    """
    parts = []
    for field, prefix in PROSE_FIELDS:
        value = (program.get(field) or "").strip()
        if value:
            parts.append(f"{prefix}{value}")

    if not parts:
        return None

    header = f"{program['name']}."
    age = _age_sentence(program)
    if age:
        parts.append(age)

    return "\n\n".join([header] + parts)


def _age_sentence(program: dict) -> str | None:
    """Age limits are structured fields, but a driver asking 'is my kid old
    enough' asks in prose. Rendering them makes the answer retrievable.

    The approval gate is deliberately NOT rendered as a promise. It says a
    person checks — it never suggests what that person will decide.
    """
    lo, hi = program.get("age_min"), program.get("age_max")
    gate = program.get("human_approval_below_age")
    bits = []
    if lo is not None and hi is not None:
        bits.append(f"Ages {lo} to {hi}.")
    elif lo is not None:
        bits.append(f"From age {lo}.")
    elif hi is not None:
        bits.append(f"Up to age {hi}.")
    if gate is not None:
        bits.append(
            f"For drivers under {gate}, the team checks clearance individually "
            f"before confirming, since it depends on the child's size.")
    return " ".join(bits) or None


def build_faq_document(program_name: str, question: str, answer: str) -> str:
    return f"{program_name} — {question}\n\n{answer}"


# =============================================================================
# CHUNKING
# =============================================================================

MAX_CHARS = 1600      # roughly 400 tokens
OVERLAP_CHARS = 200


def chunk_text(text: str) -> list[str]:
    """Split on paragraph boundaries, packing up to MAX_CHARS.

    Paragraph-first rather than fixed-window because these documents are short
    and already structured: a paragraph is one idea, and cutting mid-idea is
    what produces passages that retrieve well and read as nonsense.

    Overlap only applies when a single paragraph has to be split, which for
    catalog prose is rare.
    """
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


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


# =============================================================================
# PIPELINE
# =============================================================================

def load_catalog(db, slugs: list[str] | None) -> tuple[list[dict], dict]:
    from google.cloud.firestore_v1.base_query import FieldFilter

    snaps = (db.collection("programs")
             .where(filter=FieldFilter("status", "==", "active")).stream())
    programs = []
    for snap in snaps:
        p = snap.to_dict()
        if slugs and snap.id not in slugs:
            continue
        p["id"] = snap.id       # no Firestore o slug É o id
        p.setdefault("slug", snap.id)
        programs.append(p)
    programs.sort(key=lambda p: p.get("display_order") or 0)

    faqs: dict = {}
    for p in programs:
        rows = (db.collection("programs").document(p["id"])
                .collection("faq")
                .where(filter=FieldFilter("status", "==", "active")).stream())
        entries = sorted((r.to_dict() for r in rows),
                         key=lambda r: r.get("display_order") or 0)
        if entries:
            faqs[p["id"]] = [(e["question"], e["answer"]) for e in entries]
    return programs, faqs


def plan(programs: list[dict], faqs: dict) -> tuple[list[dict], list[str]]:
    """What documents should exist. Also reports which programs produce none."""
    docs, skipped = [], []
    for prog in programs:
        body = build_program_document(prog)
        if body is None:
            skipped.append(prog["slug"])
        else:
            docs.append({
                "title": prog["name"],
                "category": prog["category"],
                "content": body,
                "source_ref_id": prog["id"],
                "slug": prog["slug"],
            })
        for question, answer in faqs.get(prog["id"], []):
            docs.append({
                "title": f"{prog['name']} — {question}",
                "category": prog["category"],
                "content": build_faq_document(prog["name"], question, answer),
                "source_ref_id": prog["id"],
                "slug": prog["slug"],
            })
    return docs, skipped


def sync_documents(db, docs: list[dict], slugs: list[str] | None) -> dict:
    """Upsert auto_generated documents and retire the ones no longer produced."""
    from google.cloud import firestore
    from google.cloud.firestore_v1.base_query import FieldFilter

    stats = {"documents": 0, "documents_retired": 0}

    query = (db.collection("knowledge_documents")
             .where(filter=FieldFilter("source_type", "==", "auto_generated")))
    if slugs:
        query = query.where(filter=FieldFilter("source_ref_id", "in",
                                               slugs[:30]))
    live = {}
    for snap in query.stream():
        row = snap.to_dict()
        live[row["title"]] = (snap.id, row.get("content"),
                              row.get("version", 1))

    wanted = set()
    for doc in docs:
        wanted.add(doc["title"])
        existing = live.get(doc["title"])
        if existing and existing[1] == doc["content"]:
            doc["id"] = existing[0]
            continue
        if existing:
            db.collection("knowledge_documents").document(existing[0]).update({
                "content": doc["content"], "category": doc["category"],
                "version": existing[2] + 1,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "updated_by": "catalog_sync"})
            doc["id"] = existing[0]
        else:
            ref = db.collection("knowledge_documents").document()
            ref.create({"title": doc["title"], "category": doc["category"],
                        "content": doc["content"], "language": "en",
                        "status": "active", "version": 1,
                        "source_type": "auto_generated",
                        "source_ref_id": doc["source_ref_id"],
                        "updated_by": "catalog_sync",
                        "updated_at": firestore.SERVER_TIMESTAMP})
            doc["id"] = ref.id
        stats["documents"] += 1

    # A document nobody produces any more is retired. This is the branch
    # that stops a deleted description from outliving its deletion. Os
    # chunks do documento vão junto — Firestore não tem ON DELETE CASCADE,
    # então a cascata é feita aqui, explícita.
    for title, (doc_id, _, _) in live.items():
        if title not in wanted:
            _delete_chunks_of(db, doc_id)
            db.collection("knowledge_documents").document(doc_id).delete()
            stats["documents_retired"] += 1
    return stats


def _delete_chunks_of(db, doc_id: str) -> int:
    from google.cloud.firestore_v1.base_query import FieldFilter
    snaps = list(db.collection("knowledge_chunks")
                 .where(filter=FieldFilter("document_id", "==", doc_id))
                 .stream())
    for snap in snaps:
        snap.reference.delete()
    return len(snaps)


def sync_chunks(db, docs: list[dict], provider, dry_run: bool) -> dict:
    """Chunk, embed only what changed, delete what no longer exists."""
    from google.cloud.firestore_v1.base_query import FieldFilter

    stats = {"chunks_kept": 0, "chunks_embedded": 0, "chunks_deleted": 0}

    for doc in docs:
        if "id" not in doc:
            continue
        pieces = chunk_text(doc["content"])
        hashes = [content_hash(p) for p in pieces]

        snaps = list(db.collection("knowledge_chunks")
                     .where(filter=FieldFilter("document_id", "==", doc["id"]))
                     .stream())
        live = {(s.to_dict().get("metadata") or {}).get("hash"): s.reference
                for s in snaps}

        stale = [ref for h, ref in live.items() if h not in hashes]
        new = [(p, h) for p, h in zip(pieces, hashes) if h not in live]
        stats["chunks_kept"] += len(live) - len(stale)

        if dry_run:
            stats["chunks_embedded"] += len(new)
            stats["chunks_deleted"] += len(stale)
            continue

        for ref in stale:
            ref.delete()
        stats["chunks_deleted"] += len(stale)

        if new:
            from google.cloud.firestore_v1.vector import Vector
            vectors = provider.embed([p for p, _ in new], input_type="document")
            for (text, h), vec in zip(new, vectors):
                db.collection("knowledge_chunks").document().create({
                    "document_id": doc["id"],
                    "chunk_text": text,
                    "embedding": Vector(vec),
                    "metadata": {"hash": h, "slug": doc["slug"],
                                 "title": doc["title"],
                                 "provider": provider.name},
                })
            stats["chunks_embedded"] += len(new)
    return stats


def prune_orphans(db) -> int:
    """Chunks whose document is gone, and documents whose program is gone.

    O Postgres tinha ON DELETE CASCADE cobrindo parte disto; o Firestore não
    tem cascata nenhuma, então tudo é explícito aqui. Um programa desativado
    (não deletado) mantém seus docs no catálogo — e um programa inativo não
    pode continuar recuperável, ou o agente responde sobre algo que a URace
    parou de oferecer.
    """
    from google.cloud.firestore_v1.base_query import FieldFilter

    active = {s.id for s in
              db.collection("programs")
              .where(filter=FieldFilter("status", "==", "active"))
              .select([]).stream()}

    removed = 0
    snaps = (db.collection("knowledge_documents")
             .where(filter=FieldFilter("source_type", "==", "auto_generated"))
             .stream())
    for snap in snaps:
        ref_id = snap.to_dict().get("source_ref_id")
        if ref_id is None or ref_id not in active:
            _delete_chunks_of(db, snap.id)
            snap.reference.delete()
            removed += 1
    return removed


# =============================================================================
# SELF TEST — no key, no database, no cost
# =============================================================================

def self_test() -> int:
    from embed import FakeProvider
    failures = []

    def check(label, condition, detail=""):
        if condition:
            print(f"  PASS  {label}")
        else:
            print(f"  FAIL  {label}  {detail}")
            failures.append(label)

    print("document generation")
    filled = {"name": "1-Day Experience", "description": "A full day on track.",
              "objective": "Try karting properly.", "age_min": 4,
              "human_approval_below_age": 5}
    body = build_program_document(filled)
    check("a filled program produces a document", body is not None)
    check("age limits are rendered as prose", "From age 4" in (body or ""))
    check("the approval gate is described as a check, not an outcome",
          "team checks clearance" in (body or ""))
    check("the gate makes no prediction",
          not any(w in (body or "").lower() for w in ("usually fine", "should be ok",
                                                      "most kids", "likely")))

    empty = {"name": "Race Team Support", "description": None, "objective": None,
             "target_audience": None, "benefits": None, "differentiators": None,
             "prerequisites": None, "age_min": None, "age_max": None,
             "human_approval_below_age": None}
    check("an unfilled program produces NO document",
          build_program_document(empty) is None,
          "an empty passage still scores as a hit and reads as grounding")

    print("\nchunking")
    long_doc = "\n\n".join([f"Paragraph {i}. " + "word " * 60 for i in range(12)])
    pieces = chunk_text(long_doc)
    check("long text is split", len(pieces) > 1)
    check("no chunk exceeds the limit", all(len(p) <= MAX_CHARS + 50 for p in pieces),
          f"max was {max(len(p) for p in pieces)}")
    check("nothing is lost", all(f"Paragraph {i}." in " ".join(pieces) for i in range(12)))
    check("short text stays whole", len(chunk_text("One short paragraph.")) == 1)

    print("\ncontent hashing")
    check("the same text hashes the same", content_hash("abc") == content_hash("abc"))
    check("different text hashes differently", content_hash("abc") != content_hash("abd"))

    print("\nfake provider")
    fake = FakeProvider(dimension=1024)
    vecs = fake.embed(["hello", "world", "hello"])
    check("dimension is respected", all(len(v) == 1024 for v in vecs))
    check("embedding is deterministic", vecs[0] == vecs[2])
    check("different text differs", vecs[0] != vecs[1])
    check("vectors are normalised",
          abs(sum(v * v for v in vecs[0]) ** 0.5 - 1.0) < 1e-6)

    print("\nplan")
    docs, skipped = plan(
        [dict(filled, id="p1", slug="one_day", category="Training"),
         dict(empty, id="p2", slug="race_team_support", category="Racing")],
        {"p1": [("Is it safe?", "Karting is a motorsport with real protocols.")]})
    check("one document per filled program plus its FAQ", len(docs) == 2)
    check("the unfilled program is reported, not silently dropped",
          skipped == ["race_team_support"])

    print()
    if failures:
        print(f"SELF TEST FAILED — {len(failures)} of the checks above")
        return 1
    print("SELF TEST PASSED — logic verified with no key, no database, no cost")
    print("  Note: this proves the plumbing, not retrieval quality. Quality needs")
    print("  real embeddings and cannot be asserted by a fake.")
    return 0


# =============================================================================
# MAIN
# =============================================================================

def main():
    ap = argparse.ArgumentParser(description="Index the catalog into the knowledge base.")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--programs", nargs="*", help="Limit to these slugs.")
    ap.add_argument("--provider", help="voyage | fake")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    from db.client import get_db

    provider = get_provider(args.provider)
    print(f"provider {provider.name}, dimension {provider.dimension}\n")

    db = get_db()
    assert_matches_schema(provider, db)

    programs, faqs = load_catalog(db, args.programs)
    docs, skipped = plan(programs, faqs)
    print(f"{len(programs)} programs -> {len(docs)} documents")

    if skipped:
        print(f"\n{len(skipped)} programs produce no document (nothing filled in):")
        for slug in skipped:
            print(f"  {slug}")
        print("  The agent will decline to describe these and escalate.")

    if args.dry_run:
        total = sum(len(chunk_text(d["content"])) for d in docs)
        print(f"\ndry run: would produce {total} chunks; nothing written")
        return 0

    stats = sync_documents(db, docs, args.programs)
    stats |= sync_chunks(db, docs, provider, dry_run=False)
    orphans = prune_orphans(db)

    print(f"\ndocuments  {stats['documents']} written, "
          f"{stats['documents_retired']} retired, {orphans} orphaned removed")
    print(f"chunks     {stats['chunks_embedded']} embedded, "
          f"{stats['chunks_kept']} unchanged, {stats['chunks_deleted']} deleted")
    return 0


if __name__ == "__main__":
    sys.exit(main())

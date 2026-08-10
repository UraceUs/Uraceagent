"""
Embedding providers.

Two reasons this is its own module rather than a call inside the indexer:

  1. The dimension has to be asserted once, loudly, at startup. VECTOR(1024) in
     the schema and a provider returning 1536 fails on the first insert — long
     after the mistake, with an error that points at the row rather than at the
     configuration. Here it fails before anything is written.

  2. A fake provider makes the whole pipeline testable with no key and no cost.
     Chunking, deduplication, pruning and the threshold contract are all logic
     worth testing, and none of them need real vectors to be exercised.

The fake is deterministic: the same text always yields the same vector, and
different texts yield different ones. That is enough to test everything except
retrieval QUALITY, which no fake can test and which needs real embeddings.
"""

from __future__ import annotations

import hashlib
import math
import os
from typing import Protocol


class EmbeddingError(RuntimeError):
    pass


class Provider(Protocol):
    name: str
    dimension: int

    def embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        ...


# =============================================================================
# VOYAGE
# =============================================================================

class VoyageProvider:
    """Voyage embeddings. Default output dimension is 1024, which is what the
    schema declares. Passing output_dimension explicitly rather than relying on
    the default means a change to the provider's default cannot silently
    invalidate the column type."""

    name = "voyage"

    def __init__(self, model: str = "voyage-3.5", dimension: int = 1024):
        self.model = model
        self.dimension = dimension
        key = os.environ.get("VOYAGE_API_KEY")
        if not key:
            raise EmbeddingError("VOYAGE_API_KEY not set")
        import voyageai
        self._client = voyageai.Client(api_key=key)

    def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        # input_type matters: Voyage prepends a different instruction for
        # queries and documents. Indexing with 'query' would quietly degrade
        # retrieval without any error appearing.
        if input_type not in ("document", "query"):
            raise EmbeddingError(f"input_type must be document or query, got {input_type!r}")

        result = self._client.embed(
            texts=texts,
            model=self.model,
            input_type=input_type,
            output_dimension=self.dimension,
        )
        vectors = result.embeddings
        for vec in vectors:
            if len(vec) != self.dimension:
                raise EmbeddingError(
                    f"{self.model} returned {len(vec)} dimensions, expected "
                    f"{self.dimension}. The schema column and the provider must "
                    f"agree; changing this later means re-embedding everything.")
        return vectors


# =============================================================================
# FAKE
# =============================================================================

class FakeProvider:
    """Deterministic pseudo-embeddings for offline tests.

    Vectors are derived from the text hash, then normalised. Similar texts do
    NOT get similar vectors — this is not a semantic model and must never be
    used to judge retrieval quality. It exists so the plumbing can be proven
    without a key: chunking, dedup by content hash, pruning of stale chunks,
    and the threshold contract.
    """

    name = "fake"

    def __init__(self, dimension: int = 1024):
        self.dimension = dimension

    def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        out = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            raw = [
                (digest[i % len(digest)] - 128) / 128.0
                for i in range(self.dimension)
            ]
            norm = math.sqrt(sum(v * v for v in raw)) or 1.0
            out.append([v / norm for v in raw])
        return out


# =============================================================================
# SELECTION
# =============================================================================

def get_provider(name: str | None = None, dimension: int = 1024) -> Provider:
    name = name or os.environ.get("EMBEDDING_PROVIDER", "voyage")
    if name == "fake":
        return FakeProvider(dimension=dimension)
    if name == "voyage":
        return VoyageProvider(dimension=dimension)
    raise EmbeddingError(f"unknown embedding provider {name!r}")


def assert_matches_schema(provider: Provider, conn) -> None:
    """Fail before writing anything if the column and the provider disagree.

    Asked at startup rather than discovered at the first insert, because the
    insert error names a row and this one names the actual problem.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT format_type(atttypid, atttypmod)
            FROM pg_attribute
            WHERE attrelid = 'knowledge_chunks'::regclass AND attname = 'embedding'
        """)
        row = cur.fetchone()
    if not row:
        raise EmbeddingError("knowledge_chunks.embedding not found")

    declared = int(row[0].strip().removeprefix("vector(").removesuffix(")"))
    if declared != provider.dimension:
        raise EmbeddingError(
            f"schema declares vector({declared}) but provider "
            f"'{provider.name}' produces {provider.dimension}. Fix one before "
            f"indexing — a mismatch discovered later costs a full re-embed.")

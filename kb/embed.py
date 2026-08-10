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


def assert_matches_schema(provider: Provider, db) -> None:
    """Fail before writing anything if the corpus and the provider disagree.

    O Firestore não declara dimensão em lugar nenhum — o índice vetorial a
    fixa, e um vetor de dimensão errada falha na primeira busca, não na
    escrita. Então a dimensão vira dado nosso: registrada em
    configurations/kb no primeiro index, conferida em todos os seguintes.
    Asked at startup rather than discovered at the first query, because the
    query error names a request and this one names the actual problem.
    """
    from db.schema import EMBEDDING_DIMENSION

    if provider.dimension != EMBEDDING_DIMENSION:
        raise EmbeddingError(
            f"db/schema.py declares EMBEDDING_DIMENSION={EMBEDDING_DIMENSION} "
            f"but provider '{provider.name}' produces {provider.dimension}. "
            f"Fix one before indexing — a mismatch discovered later costs a "
            f"full re-embed, and the vector index must be rebuilt too.")

    ref = db.collection("configurations").document("kb")
    snap = ref.get()
    recorded = snap.to_dict().get("embedding_dimension") if snap.exists else None
    if recorded is None:
        ref.set({"embedding_dimension": provider.dimension,
                 "embedding_provider": provider.name}, merge=True)
    elif recorded != provider.dimension:
        raise EmbeddingError(
            f"the corpus was indexed at dimension {recorded} but provider "
            f"'{provider.name}' produces {provider.dimension}. Re-embed the "
            f"whole corpus (and rebuild the vector index) before mixing.")

"""Interface da ponte com o Sales Brain — a "interface da IA" do vault.

Importa o motor de busca de `brain/indexer.py` (raiz do repo) e adiciona o
que é responsabilidade da ponte: observabilidade (§17 da missão — query,
documentos, scores e tempo no log de auditoria) e tolerância a falha
(índice ausente/corrompido = lista vazia, nunca derruba um turno).
"""
import sys
import time
from pathlib import Path

import state
from config import REPO_DIR

# brain/ vive na raiz do repo (REPO_DIR aponta para salesagent/)
_BRAIN_DIR = REPO_DIR.parent / "brain"
sys.path.insert(0, str(_BRAIN_DIR))

try:
    import indexer as _brain_indexer  # brain/indexer.py
except Exception:  # brain ausente (checkout parcial?) — retrieval vira no-op
    _brain_indexer = None


def search(lead_id: int | None, query: str, top_docs: int = 3) -> list[dict]:
    """Busca no índice do Brain com log de auditoria. Nunca levanta exceção
    para o chamador — um turno de conversa não pode morrer por causa de
    retrieval."""
    if _brain_indexer is None or not query.strip():
        return []
    t0 = time.time()
    try:
        hits = _brain_indexer.search(query, top_docs=top_docs)
    except Exception as exc:
        state.log("error", lead_id, f"brain search: {exc}")
        return []
    ms = int((time.time() - t0) * 1000)
    resumo = " | ".join(f"{h['title']}({h['score']})" for h in hits) or "sem hits"
    state.log("brain", lead_id, f"{ms}ms q={query[:120]!r} -> {resumo}")
    return hits


def format_for_context(hits: list[dict]) -> str:
    """Bloco de conhecimento para injeção [SYSTEM] — títulos + trechos,
    dentro do orçamento que o indexer já aplicou."""
    if not hits:
        return ""
    parts = []
    for h in hits:
        parts.append(f"### {h['title']} ({h['type']}, atualizado {h['last_updated'] or '?'})\n{h['text']}")
    return "\n\n".join(parts)

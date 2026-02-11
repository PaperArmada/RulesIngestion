"""
R11: Cross-encoder re-ranking.

Re-rank retrieval candidates using a CrossEncoder model.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def load_cross_encoder(model_name: str):
    """Load a CrossEncoder from sentence-transformers.

    Common models: cross-encoder/ms-marco-MiniLM-L6-v2, cross-encoder/ms-marco-MiniLM-L-12-v2
    """
    from sentence_transformers import CrossEncoder  # type: ignore[import-untyped]
    return CrossEncoder(model_name)


def rerank_candidates(
    query: str,
    candidates: List[Dict[str, Any]],
    model: Any,
    top_k: int = 10,
    text_key: str = "text",
    id_key: str = "chunk_id",
) -> List[Dict[str, Any]]:
    """Re-rank candidates by query–text relevance using CrossEncoder.

    candidates: list of dicts with text_key (text) and id_key (chunk_id).
    Returns top_k candidates sorted by relevance score descending.
    """
    if not candidates:
        return []
    pairs = [(query, c.get(text_key, c.get("text", ""))) for c in candidates]
    scores = model.predict(pairs)
    scored = list(zip(candidates, scores))
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:top_k]
    result: List[Dict[str, Any]] = []
    for c, sc in top:
        out = dict(c)
        out["rerank_score"] = float(sc)
        result.append(out)
    return result

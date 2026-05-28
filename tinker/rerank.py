"""Cross-encoder reranker adapter for tinker.

Wraps `retrieval_lab.reranker.rerank_candidates` with a default model of
`BAAI/bge-reranker-v2-m3` (current open-standard cross-encoder for 2026,
per Docs/Design/MODELS-Intent-Routed-Retrieval.md).

The model is loaded lazily on first call to `load_reranker()` and cached
at module level so subsequent calls reuse the same instance.
"""

from __future__ import annotations

from typing import Any

from retrieval_lab.reranker import load_cross_encoder, rerank_candidates


DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"

_LOADED: dict[str, Any] = {}


def load_reranker(model_name: str = DEFAULT_RERANKER_MODEL) -> Any:
    """Load a cross-encoder, cached at module level by model_name.

    First call for a given model triggers a download (~2 GB for
    bge-reranker-v2-m3) into the local Hugging Face cache. Subsequent
    calls return the cached instance.
    """
    if model_name not in _LOADED:
        _LOADED[model_name] = load_cross_encoder(model_name)
    return _LOADED[model_name]


def rerank(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    top_k: int = 10,
    model_name: str = DEFAULT_RERANKER_MODEL,
    text_key: str = "text",
    id_key: str = "id",
) -> list[dict[str, Any]]:
    """Rerank candidates by query-text relevance.

    candidates: list of dicts each with `text_key` ("text") and `id_key`
        ("id"). The default `id_key` matches what
        `retrieval_lab.substrate_loader.load_evidence_units` returns.
    Returns the top_k candidates sorted by rerank score descending, with
    a new `rerank_score` field added.
    """
    model = load_reranker(model_name)
    return rerank_candidates(
        query=query,
        candidates=candidates,
        model=model,
        top_k=top_k,
        text_key=text_key,
        id_key=id_key,
    )

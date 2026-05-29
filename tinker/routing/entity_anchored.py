"""Entity-anchored single-target retrieval path.

This is the fast path: hybrid (dense + BM25, CC-fused) → cross-encoder
rerank → top-K. No LLM calls on the retrieval side.

Used when the q-ROFS classifier assigns this bucket OR as the
fallback when the dispatcher cannot confidently choose a more
specialized path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from tinker import llm as tinker_llm
from tinker import rerank as tinker_rerank
from tinker.retrieve.dense import DenseIndex
from tinker.retrieve.hybrid import hybrid_search
from tinker.retrieve.sparse import SparseIndex


@dataclass(frozen=True)
class RouteResult:
    """Bucket-agnostic result envelope from a single retrieval path."""

    bucket: str
    top_k: list[dict[str, Any]]   # each: {id, text, fused_score, rerank_score, ...}
    pool_size: int                 # candidates considered before rerank
    latency_ms_breakdown: dict[str, float] = field(default_factory=dict)
    debug: dict[str, Any] = field(default_factory=dict)


def run_entity_anchored(
    query: str,
    *,
    dense_index: DenseIndex,
    sparse_index: SparseIndex,
    unit_text_by_id: dict[str, str],
    top_k: int = 10,
    candidate_pool: int = 50,
    rerank: bool = True,
) -> RouteResult:
    timing: dict[str, float] = {}

    t0 = time.perf_counter()
    [query_vec] = tinker_llm.embed([query])
    timing["embed_query_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    fused_ids, fused_scores = hybrid_search(
        dense_index=dense_index,
        sparse_index=sparse_index,
        query=query,
        query_vec=query_vec,
        top_k=candidate_pool,
        candidate_pool=candidate_pool,
    )
    timing["hybrid_search_ms"] = (time.perf_counter() - t0) * 1000

    candidates = [
        {
            "id": uid,
            "text": unit_text_by_id.get(uid, ""),
            "fused_score": float(score),
        }
        for uid, score in zip(fused_ids, fused_scores)
    ]

    if rerank and candidates:
        # VRAM-swap discipline: evict Ollama models before the cross-encoder
        # rerank. On a 12 GB card the workhorse (~10 GB) + embedder (~6 GB)
        # leave no room for the reranker (~2 GB) and sentence-transformers
        # silently falls back to CPU (~400x slower).
        t_unload = time.perf_counter()
        tinker_llm.unload_workhorse()
        tinker_llm.unload_ollama_model(tinker_llm.MODEL_EMBEDDER)
        timing["ollama_unload_ms"] = (time.perf_counter() - t_unload) * 1000

        t0 = time.perf_counter()
        reranked = tinker_rerank.rerank(query, candidates, top_k=top_k)
        timing["rerank_ms"] = (time.perf_counter() - t0) * 1000
    else:
        reranked = candidates[:top_k]

    return RouteResult(
        bucket="entity_anchored_single",
        top_k=reranked,
        pool_size=len(candidates),
        latency_ms_breakdown=timing,
        debug={"reranked": rerank, "candidate_pool": candidate_pool},
    )

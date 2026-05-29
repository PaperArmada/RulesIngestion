"""Build a union candidate pool per query from multiple retrieval strategies.

The pool is the substrate that gets handed to an LLM-as-judge (or human)
for relevance labeling. To minimize "gold gaps" (relevant units missed
entirely from the pool), we run several retrieval strategies and union
their top-K outputs, deduplicating by unit id and tracking which
strategies surfaced each candidate.

Strategies included:
  - raw_dense   : cosine over qwen3-embedding embeddings
  - raw_bm25    : BM25 lexical over basic tokens
  - hybrid_cc   : convex-combination fusion of dense + BM25 (lam=0.7)
  - entity_anchored : hybrid_cc + cross-encoder rerank (bge-reranker-v2-m3)
  - intent_bearing  : extract_intent -> hypothesize -> embed -> dense -> rerank
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tinker import llm as tinker_llm
from tinker.cache import TinkerCache
from tinker.retrieve.dense import DenseIndex
from tinker.retrieve.hybrid import hybrid_search
from tinker.retrieve.sparse import SparseIndex
from tinker.rerank import rerank as cross_encoder_rerank
from tinker.routing.entity_anchored import run_entity_anchored
from tinker.routing.intent_bearing import run_intent_bearing


@dataclass
class CandidateEntry:
    unit_id: str
    text: str
    sources: list[str] = field(default_factory=list)
    strategy_scores: dict[str, float] = field(default_factory=dict)


def _merge_candidate(
    pool: dict[str, CandidateEntry],
    unit_id: str,
    text: str,
    strategy: str,
    score: float,
) -> None:
    if unit_id not in pool:
        pool[unit_id] = CandidateEntry(unit_id=unit_id, text=text)
    if strategy not in pool[unit_id].sources:
        pool[unit_id].sources.append(strategy)
    pool[unit_id].strategy_scores[strategy] = score


def build_candidate_pool(
    query: str,
    *,
    dense_index: DenseIndex,
    sparse_index: SparseIndex,
    unit_text_by_id: dict[str, str],
    self_portrait: dict[str, Any],
    cache: TinkerCache,
    top_per_strategy: int = 30,
    include_intent_bearing: bool = True,
) -> list[CandidateEntry]:
    """Return a unioned, sorted candidate list for one query."""
    pool: dict[str, CandidateEntry] = {}

    # 1. raw dense
    [qvec] = tinker_llm.embed([query])
    dense_ids, dense_scores = dense_index.search(qvec, top_k=top_per_strategy)
    for uid, sc in zip(dense_ids, dense_scores):
        _merge_candidate(
            pool, uid, unit_text_by_id.get(uid, ""), "raw_dense", float(sc)
        )

    # 2. raw BM25
    bm25_ids, bm25_scores = sparse_index.search(query, top_k=top_per_strategy)
    for uid, sc in zip(bm25_ids, bm25_scores):
        _merge_candidate(
            pool, uid, unit_text_by_id.get(uid, ""), "raw_bm25", float(sc)
        )

    # 3. hybrid CC (no rerank)
    fused_ids, fused_scores = hybrid_search(
        dense_index=dense_index,
        sparse_index=sparse_index,
        query=query,
        query_vec=qvec,
        top_k=top_per_strategy,
        candidate_pool=top_per_strategy * 2,
    )
    for uid, sc in zip(fused_ids, fused_scores):
        _merge_candidate(
            pool, uid, unit_text_by_id.get(uid, ""), "hybrid_cc", float(sc)
        )

    # 4. entity-anchored (hybrid + cross-encoder rerank)
    ea = run_entity_anchored(
        query=query,
        dense_index=dense_index,
        sparse_index=sparse_index,
        unit_text_by_id=unit_text_by_id,
        top_k=top_per_strategy,
        candidate_pool=top_per_strategy * 2,
        rerank=True,
    )
    for c in ea.top_k:
        _merge_candidate(
            pool, c["id"], c["text"],
            "entity_anchored", float(c.get("rerank_score", 0.0)),
        )

    # 5. intent-bearing (HyDE + dense + rerank)
    if include_intent_bearing:
        ib = run_intent_bearing(
            query=query,
            dense_index=dense_index,
            unit_text_by_id=unit_text_by_id,
            self_portrait=self_portrait,
            top_k=top_per_strategy,
            candidate_pool=top_per_strategy * 2,
            rerank=True,
        )
        for c in ib.top_k:
            _merge_candidate(
                pool, c["id"], c["text"],
                "intent_bearing", float(c.get("rerank_score", 0.0)),
            )

    # Sort: candidates surfaced by more strategies first, then by max score.
    ordered = sorted(
        pool.values(),
        key=lambda c: (
            -len(c.sources),
            -max(c.strategy_scores.values(), default=0.0),
        ),
    )
    return ordered


def build_pools_for_benchmark(
    benchmark_queries: list[dict[str, Any]],
    *,
    dense_index: DenseIndex,
    sparse_index: SparseIndex,
    unit_text_by_id: dict[str, str],
    self_portrait: dict[str, Any],
    cache: TinkerCache,
    top_per_strategy: int = 30,
    include_intent_bearing: bool = True,
    progress: bool = True,
) -> dict[str, dict[str, Any]]:
    """Build candidate pools for every query in a benchmark.

    Returns dict keyed by query_id with {question, candidates: [dict, ...]}.
    Each candidate is a serializable dict from CandidateEntry.
    """
    out: dict[str, dict[str, Any]] = {}
    for i, q in enumerate(benchmark_queries):
        qid = q.get("id") or f"q{i}"
        question = q.get("question", "")
        if progress:
            print(
                f"[{i + 1}/{len(benchmark_queries)}] {qid}  building pool...",
                flush=True,
            )
        t0 = time.perf_counter()
        candidates = build_candidate_pool(
            question,
            dense_index=dense_index,
            sparse_index=sparse_index,
            unit_text_by_id=unit_text_by_id,
            self_portrait=self_portrait,
            cache=cache,
            top_per_strategy=top_per_strategy,
            include_intent_bearing=include_intent_bearing,
        )
        elapsed = time.perf_counter() - t0
        out[qid] = {
            "id": qid,
            "question": question,
            "tier": q.get("tier"),
            "question_type": q.get("question_type"),
            "candidates": [asdict(c) for c in candidates],
        }
        if progress:
            print(
                f"  -> {len(candidates)} unique candidates in {elapsed:.1f}s",
                flush=True,
            )
    return out

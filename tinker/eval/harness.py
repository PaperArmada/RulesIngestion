"""End-to-end evaluation harness.

For each query in a benchmark:
  1. Run the router (q-ROFS dispatch + route).
  2. Run a raw-dense baseline (dense top-K + cross-encoder rerank, no
     classifier, no HyDE). The baseline is intentionally simple so we
     can attribute MRR / Recall lifts to the routing thesis.
  3. Score both against a gold set generated via LLM-as-judge.

Gold format (written by tinker/eval/labeling.py or by hand):
  {
    "<query_id>": {
      "required": ["<unit_id>", ...],     # tier-1 units, must be retrieved
      "supporting": ["<unit_id>", ...],   # tier-2, helpful but not essential
      "notes": "..." (optional)
    }
  }

Metrics computed:
  - MRR (rank of first required-gold unit, 0 if no required)
  - Recall@k for k in {1, 5, 10, 20}, over (required ∪ supporting)
  - Strict-required-recall@k: fraction of REQUIRED units in top-K
  - Latency p50 / p95 / max per stage
  - Per-bucket aggregates (router only)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tinker import llm as tinker_llm
from tinker import rerank as tinker_rerank
from tinker.cache import TinkerCache
from tinker.retrieve.dense import DenseIndex
from tinker.retrieve.sparse import SparseIndex
from tinker.routing.dispatch import route_and_retrieve, DispatchResult


TOP_K_LIST = (1, 5, 10, 20)


@dataclass
class QueryEvalResult:
    query_id: str
    question: str
    mode: str  # "router" or "raw_dense"
    chosen_bucket: str | None
    margin: float | None
    multi_path: bool
    top_k_ids: list[str]
    top_k_scores: list[float]
    metrics: dict[str, float]
    latency_ms: dict[str, float] = field(default_factory=dict)
    debug: dict[str, Any] = field(default_factory=dict)


def _gold_for(gold: dict[str, Any], qid: str) -> tuple[set[str], set[str]]:
    entry = gold.get(qid) or {}
    required = set(entry.get("required") or [])
    supporting = set(entry.get("supporting") or [])
    return required, supporting


def _mrr_first_required(ranked: list[str], required: set[str]) -> float:
    if not required:
        return 0.0
    for i, uid in enumerate(ranked, start=1):
        if uid in required:
            return 1.0 / i
    return 0.0


def _recall_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    if not gold:
        return 0.0
    top_k = set(ranked[:k])
    hit = len(top_k & gold)
    return hit / len(gold)


def _strict_required_at_k(ranked: list[str], required: set[str], k: int) -> float:
    if not required:
        return 0.0
    top_k = set(ranked[:k])
    return 1.0 if required <= top_k else 0.0


def _score(ranked: list[str], required: set[str], supporting: set[str]) -> dict[str, float]:
    union_gold = required | supporting
    out: dict[str, float] = {
        "mrr_required": _mrr_first_required(ranked, required),
    }
    for k in TOP_K_LIST:
        out[f"recall_at_{k}"] = _recall_at_k(ranked, union_gold, k)
        out[f"strict_required_at_{k}"] = _strict_required_at_k(ranked, required, k)
    return out


def run_raw_dense_baseline(
    query: str,
    *,
    dense_index: DenseIndex,
    unit_text_by_id: dict[str, str],
    top_k: int = 20,
    candidate_pool: int = 50,
    rerank: bool = True,
) -> tuple[list[str], list[float], dict[str, float]]:
    """Embed query -> dense top-K -> cross-encoder rerank. No classifier, no HyDE."""
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    [qvec] = tinker_llm.embed([query])
    timings["embed_query_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    dense_ids, dense_scores = dense_index.search(qvec, top_k=candidate_pool)
    timings["dense_search_ms"] = (time.perf_counter() - t0) * 1000

    candidates = [
        {"id": uid, "text": unit_text_by_id.get(uid, ""), "dense_score": float(s)}
        for uid, s in zip(dense_ids, dense_scores)
    ]
    if rerank and candidates:
        t_unload = time.perf_counter()
        tinker_llm.unload_ollama_model(tinker_llm.MODEL_EMBEDDER)
        timings["ollama_unload_ms"] = (time.perf_counter() - t_unload) * 1000

        t0 = time.perf_counter()
        reranked = tinker_rerank.rerank(query, candidates, top_k=top_k)
        timings["rerank_ms"] = (time.perf_counter() - t0) * 1000
        ranked_ids = [c["id"] for c in reranked]
        scores = [float(c.get("rerank_score", 0.0)) for c in reranked]
    else:
        ranked_ids = [c["id"] for c in candidates[:top_k]]
        scores = [c["dense_score"] for c in candidates[:top_k]]
    return ranked_ids, scores, timings


def eval_benchmark(
    queries: list[dict[str, Any]],
    gold: dict[str, Any],
    *,
    dense_index: DenseIndex,
    sparse_index: SparseIndex,
    unit_text_by_id: dict[str, str],
    self_portrait: dict[str, Any],
    cache: TinkerCache,
    modes: tuple[str, ...] = ("router", "raw_dense"),
    top_k: int = 20,
    candidate_pool: int = 50,
    progress: bool = True,
) -> dict[str, list[QueryEvalResult]]:
    """Score every query under each requested mode.

    Returns dict mode -> list[QueryEvalResult] in benchmark order.
    """
    results: dict[str, list[QueryEvalResult]] = {m: [] for m in modes}

    for i, q in enumerate(queries):
        qid = q.get("id") or f"q{i}"
        question = q.get("question", "")
        required, supporting = _gold_for(gold, qid)
        if not (required or supporting):
            if progress:
                print(f"[{i + 1}/{len(queries)}] {qid}: no gold; skipping", flush=True)
            continue

        if "router" in modes:
            t_outer = time.perf_counter()
            r: DispatchResult = route_and_retrieve(
                query=question,
                dense_index=dense_index,
                sparse_index=sparse_index,
                unit_text_by_id=unit_text_by_id,
                self_portrait=self_portrait,
                cache=cache,
                top_k=top_k,
                candidate_pool=candidate_pool,
            )
            outer_ms = (time.perf_counter() - t_outer) * 1000
            top_ids = [c["id"] for c in r.merged_top_k]
            top_scores = [
                float(c.get("rerank_score", c.get("fused_score", 0.0)))
                for c in r.merged_top_k
            ]
            metrics = _score(top_ids, required, supporting)
            latencies = {"total_ms": outer_ms, "classifier_ms": r.classifier_latency_ms}
            for j, route in enumerate(r.routes):
                for k, v in route.latency_ms_breakdown.items():
                    latencies[f"route{j}_{route.bucket}_{k}"] = v
            results["router"].append(
                QueryEvalResult(
                    query_id=qid,
                    question=question,
                    mode="router",
                    chosen_bucket=r.chosen_bucket,
                    margin=r.margin,
                    multi_path=r.multi_path,
                    top_k_ids=top_ids,
                    top_k_scores=top_scores,
                    metrics=metrics,
                    latency_ms=latencies,
                    debug={
                        "second_bucket": r.second_bucket,
                        "runners_invoked": r.debug.get("runners_invoked", []),
                    },
                )
            )

        if "raw_dense" in modes:
            t_outer = time.perf_counter()
            ranked_ids, scores, timings = run_raw_dense_baseline(
                question,
                dense_index=dense_index,
                unit_text_by_id=unit_text_by_id,
                top_k=top_k,
                candidate_pool=candidate_pool,
            )
            outer_ms = (time.perf_counter() - t_outer) * 1000
            metrics = _score(ranked_ids, required, supporting)
            timings["total_ms"] = outer_ms
            results["raw_dense"].append(
                QueryEvalResult(
                    query_id=qid,
                    question=question,
                    mode="raw_dense",
                    chosen_bucket=None,
                    margin=None,
                    multi_path=False,
                    top_k_ids=ranked_ids,
                    top_k_scores=scores,
                    metrics=metrics,
                    latency_ms=timings,
                )
            )

        if progress:
            line = f"[{i + 1}/{len(queries)}] {qid}"
            if "router" in modes:
                rr = results["router"][-1]
                line += (
                    f"  router: bucket={rr.chosen_bucket} "
                    f"mrr={rr.metrics['mrr_required']:.3f} "
                    f"r@10={rr.metrics['recall_at_10']:.2f}"
                )
            if "raw_dense" in modes:
                rd = results["raw_dense"][-1]
                line += (
                    f"  raw_dense: "
                    f"mrr={rd.metrics['mrr_required']:.3f} "
                    f"r@10={rd.metrics['recall_at_10']:.2f}"
                )
            print(line, flush=True)

    return results


def aggregate(per_query: list[QueryEvalResult]) -> dict[str, float]:
    """Mean each metric across queries (skipping queries with no required/supporting)."""
    if not per_query:
        return {}
    keys = set(per_query[0].metrics.keys())
    n = len(per_query)
    out = {k: sum(r.metrics.get(k, 0.0) for r in per_query) / n for k in keys}
    return out

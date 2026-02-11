"""
Retrieval metrics: recall@k, hit@k, MRR, gold-in-candidates, answer_similarity@k,
and per-query failure classification. Per-suite breakdown supported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class QueryResult:
    """Result for a single query: ranked IDs, scores, gold presence, failure type."""

    query_id: str
    ranked_ids: List[str]
    scores: List[float]
    gold_unit_ids: List[str]
    first_gold_rank: Optional[int]  # 1-based; None if no gold in list
    in_top_k: Dict[int, bool]  # k -> whether at least one gold in top-k
    recall_at_k: Dict[int, float]  # k -> fraction of gold found in top-k
    failure_type: str  # "hit", "retrieval_miss", "rank_miss", "grounding_failure"
    suite: str = "default"
    tier: str = "T1"  # R8 gold tier (T1-T5)
    answer_similarity_at_k: Optional[Dict[int, float]] = None  # k -> mean sim of top-k to query


def _first_gold_rank(ranked_ids: List[str], gold_ids: List[str]) -> Optional[int]:
    """1-based rank of first gold in ranked_ids; None if not present."""
    gold_set = set(gold_ids)
    for i, uid in enumerate(ranked_ids):
        if uid in gold_set:
            return i + 1
    return None


def _recall_at_k(ranked_ids: List[str], gold_ids: List[str], k: int) -> float:
    """Fraction of gold_ids that appear in ranked_ids[:k]."""
    if not gold_ids:
        return 0.0
    gold_set = set(gold_ids)
    hits = sum(1 for uid in ranked_ids[:k] if uid in gold_set)
    return hits / len(gold_ids)


def _hit_at_k(ranked_ids: List[str], gold_ids: List[str], k: int) -> bool:
    """At least one gold in top-k."""
    if not gold_ids:
        return False
    gold_set = set(gold_ids)
    return any(uid in gold_set for uid in ranked_ids[:k])


def compute_query_result(
    query_id: str,
    ranked_ids: List[str],
    scores: List[float],
    gold_unit_ids: List[str],
    top_k_list: List[int],
    suite: str = "default",
    tier: str = "T1",
    query_embedding: Optional[np.ndarray] = None,
    corpus_embeddings: Optional[np.ndarray] = None,
    corpus_id_to_index: Optional[Dict[str, int]] = None,
) -> QueryResult:
    """
    Compute per-query metrics and failure classification.
    If query_embedding and corpus_embeddings are provided, answer_similarity@k is computed.
    """
    in_top_k = {k: _hit_at_k(ranked_ids, gold_unit_ids, k) for k in top_k_list}
    recall_at_k = {k: _recall_at_k(ranked_ids, gold_unit_ids, k) for k in top_k_list}
    first_rank = _first_gold_rank(ranked_ids, gold_unit_ids)
    max_k = max(top_k_list) if top_k_list else 0
    if not gold_unit_ids:
        failure_type = "grounding_failure"
    elif first_rank is None:
        failure_type = "retrieval_miss"
    elif first_rank > max_k:
        failure_type = "rank_miss"
    else:
        failure_type = "hit"
    answer_similarity_at_k = None
    if (
        query_embedding is not None
        and corpus_embeddings is not None
        and corpus_id_to_index is not None
        and ranked_ids
    ):
        sims = []
        for uid in ranked_ids:
            idx = corpus_id_to_index.get(uid)
            if idx is not None:
                s = float(np.dot(query_embedding, corpus_embeddings[idx]))
                sims.append(s)
            else:
                sims.append(0.0)
        answer_similarity_at_k = {}
        for k in top_k_list:
            if k <= len(sims):
                answer_similarity_at_k[k] = round(float(np.mean(sims[:k])), 4)
    return QueryResult(
        query_id=query_id,
        ranked_ids=ranked_ids,
        scores=scores,
        gold_unit_ids=gold_unit_ids,
        first_gold_rank=first_rank,
        in_top_k=in_top_k,
        recall_at_k=recall_at_k,
        failure_type=failure_type,
        suite=suite,
        tier=tier,
        answer_similarity_at_k=answer_similarity_at_k,
    )


@dataclass
class MetricsResult:
    """Aggregate metrics for one (model, query set) run."""

    recall_at_k: Dict[int, float] = field(default_factory=dict)
    hit_at_k: Dict[int, float] = field(default_factory=dict)
    mrr: float = 0.0
    gold_in_candidates: float = 0.0
    grounding_coverage: float = 0.0
    answer_similarity_at_k: Dict[int, float] = field(default_factory=dict)
    failure_counts: Dict[str, int] = field(default_factory=dict)
    per_query: List[Dict[str, Any]] = field(default_factory=list)
    per_suite: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    per_tier: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # R8 gold tier taxonomy
    candidate_set_size: int = 0


def score_retrieval(
    grounded_queries: List[Dict[str, Any]],
    ranked_lists: List[List[str]],
    score_lists: List[List[float]],
    top_k_list: List[int],
    query_embeddings: Optional[np.ndarray] = None,
    corpus_embeddings: Optional[np.ndarray] = None,
    corpus_ids: Optional[List[str]] = None,
) -> MetricsResult:
    """
    Compute aggregate metrics from per-query ranked results.
    grounded_queries: list of {id, gold_unit_ids, _suite, ...}.
    ranked_lists[i]: ranked unit IDs for query i.
    score_lists[i]: scores for ranked_lists[i].
    """
    if len(grounded_queries) != len(ranked_lists) or len(grounded_queries) != len(score_lists):
        raise ValueError("grounded_queries, ranked_lists, score_lists must have same length")
    corpus_id_to_index = None
    if corpus_ids is not None:
        corpus_id_to_index = {uid: i for i, uid in enumerate(corpus_ids)}
    per_query_results = []
    for i, q in enumerate(grounded_queries):
        gold = list(q.get("gold_unit_ids") or [])
        suite = q.get("_suite", "default")
        tier = q.get("_tier", q.get("tier", "T1"))
        q_emb = query_embeddings[i] if query_embeddings is not None and i < query_embeddings.shape[0] else None
        r = compute_query_result(
            query_id=q.get("id", ""),
            ranked_ids=ranked_lists[i],
            scores=score_lists[i],
            gold_unit_ids=gold,
            top_k_list=top_k_list,
            suite=suite,
            tier=tier,
            query_embedding=q_emb,
            corpus_embeddings=corpus_embeddings,
            corpus_id_to_index=corpus_id_to_index,
        )
        per_query_results.append(r)
    n = len(per_query_results)
    if n == 0:
        return MetricsResult(candidate_set_size=corpus_ids or 0)
    recall_at_k = {}
    hit_at_k = {}
    for k in top_k_list:
        recall_at_k[k] = sum(r.recall_at_k[k] for r in per_query_results) / n
        hit_at_k[k] = sum(1 for r in per_query_results if r.in_top_k[k]) / n
    rr_sum = 0.0
    for r in per_query_results:
        if r.first_gold_rank is not None:
            rr_sum += 1.0 / r.first_gold_rank
    mrr = rr_sum / n
    gold_in_candidates = sum(1 for r in per_query_results if r.first_gold_rank is not None) / n
    grounded_count = sum(1 for q in grounded_queries if (q.get("gold_unit_ids") or []))
    grounding_coverage = grounded_count / n if n else 0.0
    failure_counts = {}
    for r in per_query_results:
        failure_counts[r.failure_type] = failure_counts.get(r.failure_type, 0) + 1
    answer_similarity_at_k = {}
    has_sim = [r for r in per_query_results if r.answer_similarity_at_k]
    if has_sim:
        for k in top_k_list:
            vals = [r.answer_similarity_at_k[k] for r in has_sim if k in (r.answer_similarity_at_k or {})]
            if vals:
                answer_similarity_at_k[k] = round(sum(vals) / len(vals), 4)
    per_suite = {}
    for r in per_query_results:
        su = r.suite
        if su not in per_suite:
            per_suite[su] = {"recall_at_k": {}, "hit_at_k": {}, "mrr": 0.0, "n": 0, "rr_sum": 0.0}
        per_suite[su]["n"] = per_suite[su]["n"] + 1
        if r.first_gold_rank is not None:
            per_suite[su]["rr_sum"] = per_suite[su]["rr_sum"] + 1.0 / r.first_gold_rank
        for k in top_k_list:
            per_suite[su]["recall_at_k"][k] = per_suite[su]["recall_at_k"].get(k, 0) + r.recall_at_k[k]
            per_suite[su]["hit_at_k"][k] = per_suite[su]["hit_at_k"].get(k, 0) + (1 if r.in_top_k[k] else 0)
    for su, d in per_suite.items():
        nn = d["n"]
        d["mrr"] = d["rr_sum"] / nn if nn else 0.0
        d["recall_at_k"] = {k: v / nn for k, v in d["recall_at_k"].items()}
        d["hit_at_k"] = {k: v / nn for k, v in d["hit_at_k"].items()}
        del d["rr_sum"]
    # Per-tier aggregates (R8 gold taxonomy)
    per_tier: Dict[str, Dict[str, Any]] = {}
    for r in per_query_results:
        t = r.tier
        if t not in per_tier:
            per_tier[t] = {"recall_at_k": {}, "hit_at_k": {}, "mrr": 0.0, "n": 0, "rr_sum": 0.0}
        per_tier[t]["n"] = per_tier[t]["n"] + 1
        if r.first_gold_rank is not None:
            per_tier[t]["rr_sum"] = per_tier[t]["rr_sum"] + 1.0 / r.first_gold_rank
        for k in top_k_list:
            per_tier[t]["recall_at_k"][k] = per_tier[t]["recall_at_k"].get(k, 0) + r.recall_at_k[k]
            per_tier[t]["hit_at_k"][k] = per_tier[t]["hit_at_k"].get(k, 0) + (1 if r.in_top_k[k] else 0)
    for t, d in per_tier.items():
        nn = d["n"]
        d["mrr"] = d["rr_sum"] / nn if nn else 0.0
        d["recall_at_k"] = {k: v / nn for k, v in d["recall_at_k"].items()}
        d["hit_at_k"] = {k: v / nn for k, v in d["hit_at_k"].items()}
        del d["rr_sum"]
    per_query_serialized = []
    for r in per_query_results:
        per_query_serialized.append({
            "query_id": r.query_id,
            "first_gold_rank": r.first_gold_rank,
            "failure_type": r.failure_type,
            "suite": r.suite,
            "tier": r.tier,
            "in_top_k": r.in_top_k,
            "recall_at_k": r.recall_at_k,
            "answer_similarity_at_k": r.answer_similarity_at_k,
        })
    return MetricsResult(
        recall_at_k=recall_at_k,
        hit_at_k=hit_at_k,
        mrr=mrr,
        gold_in_candidates=gold_in_candidates,
        grounding_coverage=grounding_coverage,
        answer_similarity_at_k=answer_similarity_at_k,
        failure_counts=failure_counts,
        per_query=per_query_serialized,
        per_suite=per_suite,
        per_tier=per_tier,
        candidate_set_size=len(corpus_ids) if corpus_ids else 0,
    )

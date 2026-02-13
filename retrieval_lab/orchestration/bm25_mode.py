"""BM25 retrieval mode orchestration extracted from run_experiment."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Tuple

from retrieval_lab.config import ParentFetchConfig
from retrieval_lab.metrics import score_retrieval
from retrieval_lab.orchestration.expansion_pipeline import apply_post_retrieval_expansion

logger = logging.getLogger(__name__)


def run_bm25_mode(
    *,
    config: Any,
    flags: Any,
    expansion_cfg: Any,
    corpus: List[Dict[str, Any]],
    corpus_ids: List[str],
    corpus_texts: List[str],
    grounded_queries: List[Dict[str, Any]],
    id_to_text: Dict[str, str],
    id_to_source_ids: Dict[str, List[str]],
    crossref_sidecar: Dict[str, List[str]],
    pairing_edges: Dict[str, List[Tuple[str, str, str]]],
    apply_unit_type_boost_fn: Callable[[List[List[str]], List[List[float]], List[Dict[str, Any]], List[Dict[str, Any]], float], None],
) -> Dict[str, Any]:
    """Execute BM25 ranking, expansion, scoring, and query review assembly."""
    if flags.expand_context:
        logger.warning("Expand context is not supported for BM25 mode; skipping.")
    from retrieval_lab.sparse_retrieval import build_bm25_index, bm25_rank

    t0 = time.perf_counter()
    bm25 = build_bm25_index(corpus_texts)
    max_k = max(config.top_k)
    ranked_lists, score_lists = bm25_rank(bm25, corpus_ids, grounded_queries, max_k)
    boost = flags.unit_type_boost
    if boost > 0:
        apply_unit_type_boost_fn(ranked_lists, score_lists, corpus, grounded_queries, boost)

    ranked_lists, score_lists, pairing_payload = apply_post_retrieval_expansion(
        ranked_lists=ranked_lists,
        score_lists=score_lists,
        grounded_queries=grounded_queries,
        crossref_sidecar=crossref_sidecar,
        pairing_edges=pairing_edges,
        config=expansion_cfg,
    )

    ranked_source_id_lists = [
        [id_to_source_ids.get(cid, [cid]) for cid in ranked_lists[i]]
        for i in range(len(ranked_lists))
    ]
    scoring_time_sec = time.perf_counter() - t0

    metrics = score_retrieval(
        grounded_queries,
        ranked_lists,
        score_lists,
        config.top_k,
        ranked_source_id_lists=ranked_source_id_lists,
    )

    query_reviews = []
    pf_policy = ParentFetchConfig(
        depth=flags.parent_fetch_depth,
        char_cap=flags.parent_fetch_cap,
        enabled=flags.parent_fetch_enabled,
    )
    for i, q in enumerate(grounded_queries):
        pq = metrics.per_query[i]
        retrieved = []
        for r, (cid, sc) in enumerate(zip(ranked_lists[i], score_lists[i]), start=1):
            retrieved.append(
                {
                    "rank": r,
                    "chunk_id": cid,
                    "score": round(sc, 4),
                    "text": id_to_text.get(cid, ""),
                }
            )
        if pf_policy.enabled:
            from retrieval_lab.parent_fetch import fetch_parent_context

            retrieved = fetch_parent_context(retrieved, corpus, pf_policy)
        query_reviews.append(
            {
                "query_id": q.get("id", ""),
                "question": q.get("question", ""),
                "expected_answer_summary": q.get("expected_answer_summary", ""),
                "gold_unit_ids": list(q.get("gold_unit_ids") or []),
                "first_gold_rank": pq.get("first_gold_rank"),
                "failure_type": pq.get("failure_type", ""),
                "retrieved": retrieved,
            }
        )
        top3_ids = ranked_lists[i][:3]
        top3_scores = [round(s, 3) for s in score_lists[i][:3]]
        logger.info(
            "[bm25] query_id=%s top3=%s scores=%s first_gold_rank=%s failure_type=%s",
            q.get("id", ""),
            top3_ids,
            top3_scores,
            pq.get("first_gold_rank"),
            pq.get("failure_type", ""),
        )

    return {
        "results": {
            "recall_at_k": metrics.recall_at_k,
            "hit_at_k": metrics.hit_at_k,
            "full_set_hit_at_k": metrics.full_set_hit_at_k,
            "mrr": metrics.mrr,
            "gold_in_candidates": metrics.gold_in_candidates,
            "gold_in_candidates_true_ceiling": metrics.gold_in_candidates_true_ceiling,
            "grounding_coverage": metrics.grounding_coverage,
            "answer_similarity_at_k": metrics.answer_similarity_at_k,
            "failure_counts": metrics.failure_counts,
            "failure_bucket_counts": metrics.failure_bucket_counts,
            "per_suite": metrics.per_suite,
            "per_tier": metrics.per_tier,
            "embedding_time_sec": 0.0,
            "scoring_time_sec": scoring_time_sec,
        },
        "per_query": metrics.per_query,
        "query_reviews": query_reviews,
        "pairing_payload": pairing_payload,
    }

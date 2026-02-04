"""Traversal scoring helpers for benchmarks."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from evaluation.metrics import compare_retrieval_runs
from evaluation.scoring_engine import score_queries


def score_traversal_runs(
    query_embeddings,
    chunk_embeddings,
    expected_ids: Sequence[Sequence[str]],
    chunk_ids: Sequence[str],
    top_k_list: Iterable[int],
    adjacency_by_document: Optional[Dict[str, Dict[str, set]]],
    query_document_ids: Sequence[str],
    query_book_ids: Sequence[str],
    query_allowed_book_ids: Sequence[Optional[set]],
    chunk_document_ids: Dict[str, str],
    chunk_book_ids: Dict[str, str],
    chunk_kind_by_id: Dict[str, str],
    allowed_chunk_ids_by_query: Optional[Sequence[Optional[set]]],
    graph_boost: float,
    graph_boost_depth: int,
    graph_boost_top_k: Optional[int],
    graph_boost_source: str,
    graph_boost_seed_top_n: int,
    graph_boost_same_kind_only: bool,
    graph_boost_decay: float,
) -> Tuple[Dict[str, float], List[Dict[str, Any]], Dict[str, float], List[Dict[str, Any]], Dict[str, Any]]:
    baseline_scores, baseline_details = score_queries(
        query_embeddings,
        chunk_embeddings,
        expected_ids,
        chunk_ids,
        top_k_list,
        adjacency_by_document=adjacency_by_document if graph_boost else None,
        query_document_ids=query_document_ids,
        query_book_ids=query_book_ids,
        query_allowed_book_ids=query_allowed_book_ids,
        chunk_document_ids=chunk_document_ids,
        chunk_book_ids=chunk_book_ids,
        chunk_kind_by_id=chunk_kind_by_id,
        allowed_chunk_ids_by_query=None,
        graph_boost=graph_boost,
        graph_boost_depth=graph_boost_depth,
        graph_boost_top_k=graph_boost_top_k,
        graph_boost_source=graph_boost_source,
        graph_boost_seed_top_n=graph_boost_seed_top_n,
        graph_boost_same_kind_only=graph_boost_same_kind_only,
        graph_boost_decay=graph_boost_decay,
    )

    compare_scores, compare_details_scored = score_queries(
        query_embeddings,
        chunk_embeddings,
        expected_ids,
        chunk_ids,
        top_k_list,
        adjacency_by_document=adjacency_by_document if graph_boost else None,
        query_document_ids=query_document_ids,
        query_book_ids=query_book_ids,
        query_allowed_book_ids=query_allowed_book_ids,
        chunk_document_ids=chunk_document_ids,
        chunk_book_ids=chunk_book_ids,
        chunk_kind_by_id=chunk_kind_by_id,
        allowed_chunk_ids_by_query=allowed_chunk_ids_by_query,
        graph_boost=graph_boost,
        graph_boost_depth=graph_boost_depth,
        graph_boost_top_k=graph_boost_top_k,
        graph_boost_source=graph_boost_source,
        graph_boost_seed_top_n=graph_boost_seed_top_n,
        graph_boost_same_kind_only=graph_boost_same_kind_only,
        graph_boost_decay=graph_boost_decay,
    )

    delta = {
        "coverage": float(compare_scores.get("coverage", 0.0) - baseline_scores.get("coverage", 0.0)),
        "mrr": float(compare_scores.get("mrr", 0.0) - baseline_scores.get("mrr", 0.0)),
        "hit_rates": {
            key: float(
                compare_scores.get("hit_rates", {}).get(key, 0.0)
                - baseline_scores.get("hit_rates", {}).get(key, 0.0)
            )
            for key in baseline_scores.get("hit_rates", {}).keys()
        },
    }

    monotonicity = compare_retrieval_runs(
        baseline_details,
        compare_details_scored or [],
        top_k_list,
    )

    return baseline_scores, baseline_details, compare_scores, compare_details_scored, delta, monotonicity

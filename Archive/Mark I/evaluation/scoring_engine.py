from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import numpy as np


def score_queries(
    query_embeddings: np.ndarray,
    chunk_embeddings: np.ndarray,
    expected_ids: List[List[str]],
    chunk_ids: List[str],
    top_k: Iterable[int],
    *,
    answer_embeddings: Optional[np.ndarray] = None,
    answer_texts: Optional[List[str]] = None,
    adjacency_by_document: Optional[Dict[str, Dict[str, Set[str]]]] = None,
    query_document_ids: Optional[List[str]] = None,
    query_book_ids: Optional[List[str]] = None,
    query_allowed_book_ids: Optional[List[Optional[Set[str]]]] = None,
    chunk_document_ids: Optional[Dict[str, str]] = None,
    chunk_book_ids: Optional[Dict[str, str]] = None,
    chunk_kind_by_id: Optional[Dict[str, Optional[str]]] = None,
    allowed_chunk_ids_by_query: Optional[List[Optional[Set[str]]]] = None,
    graph_boost: float = 0.0,
    graph_boost_depth: int = 1,
    graph_boost_top_k: Optional[int] = None,
    graph_boost_source: str = "expected",
    graph_boost_seed_top_n: int = 1,
    graph_boost_same_kind_only: bool = False,
    graph_boost_decay: float = 1.0,
    routing_boost: float = 0.0,
    routing_boost_by_query: Optional[List[Optional[Set[str]]]] = None,
    routing_boost_pool_multiplier: float = 1.0,
    routing_chapters_by_query: Optional[List[Optional[Set[str]]]] = None,
    chunk_to_chapter: Optional[Dict[str, str]] = None,
    ranked_chunk_ids_by_query: Optional[List[List[str]]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if chunk_embeddings.size == 0 or query_embeddings.size == 0:
        return {"query_count": 0}, []
    use_precomputed_rankings = (
        ranked_chunk_ids_by_query is not None
        and len(ranked_chunk_ids_by_query) == len(query_embeddings)
    )

    top_k_list = sorted(set(int(k) for k in top_k))
    chunk_id_by_index = {idx: chunk_id for idx, chunk_id in enumerate(chunk_ids)}
    chunk_index_by_id = {chunk_id: idx for idx, chunk_id in enumerate(chunk_ids)}
    available_chunk_ids = set(chunk_ids)

    hits_by_k = {k: 0 for k in top_k_list}
    reciprocal_ranks: List[float] = []
    missing_expected = 0
    contamination_hits = {k: 0 for k in top_k_list}
    contamination_total = {k: 0 for k in top_k_list}
    answer_similarity_sums = {k: 0.0 for k in top_k_list}
    answer_similarity_counts = {k: 0 for k in top_k_list}
    query_details: List[Dict[str, Any]] = []
    max_k = max(top_k_list) if top_k_list else 0

    for query_index, query_embedding in enumerate(query_embeddings):
        expected = expected_ids[query_index]
        expected_set = set(expected)
        allowed_set = available_chunk_ids
        if allowed_chunk_ids_by_query:
            routed = allowed_chunk_ids_by_query[query_index]
            if routed:
                allowed_set = routed
        allowed_books: Optional[Set[str]] = None
        if query_allowed_book_ids is not None and query_index < len(query_allowed_book_ids):
            explicit_allowed = query_allowed_book_ids[query_index]
            if explicit_allowed:
                allowed_books = explicit_allowed
        if allowed_books is None and query_book_ids and query_index < len(query_book_ids):
            book_id = query_book_ids[query_index]
            if book_id and book_id != "unknown":
                allowed_books = {book_id}
        if not expected_set & allowed_set:
            missing_expected += 1
            query_details.append(
                {
                    "query_index": query_index,
                    "expected_chunk_ids": expected,
                    "expected_found": False,
                    "expected_rank": None,
                    "top_results": [],
                }
            )
            continue

        if use_precomputed_rankings and query_index < len(ranked_chunk_ids_by_query):
            ranking = ranked_chunk_ids_by_query[query_index]
            scores = np.full(len(chunk_ids), -float("inf"), dtype=np.float64)
            for rank, chunk_id in enumerate(ranking):
                idx = chunk_index_by_id.get(chunk_id)
                if idx is not None:
                    scores[idx] = 1.0 / (rank + 1)
        else:
            scores = chunk_embeddings @ query_embedding
            if allowed_set is not available_chunk_ids:
                for idx, chunk_id in chunk_id_by_index.items():
                    if chunk_id not in allowed_set:
                        scores[int(idx)] = -float("inf")

        routing_boost_ids = None
        if not use_precomputed_rankings:
            if routing_boost_by_query:
                routing_boost_ids = routing_boost_by_query[query_index]
            routing_boost_pool_ids = None
            if routing_boost and routing_boost_ids and routing_boost_pool_multiplier > 1:
                pool_size = int(max_k * routing_boost_pool_multiplier) if max_k else len(chunk_ids)
                ranked_indices = np.argsort(scores)[::-1][:pool_size]
                routing_boost_pool_ids = {
                    chunk_id_by_index[int(idx)] for idx in ranked_indices
                }
            boosted_count = 0
            boost_seed_ids: List[str] = []
            if graph_boost and adjacency_by_document and query_document_ids:
                document_id = query_document_ids[query_index]
                adjacency = adjacency_by_document.get(document_id, {})
                boost_seed_top_n = max(1, int(graph_boost_seed_top_n or 1))
                if graph_boost_source == "expected":
                    boost_seed_ids = [seed_id for seed_id in expected_set if seed_id in allowed_set]
                elif graph_boost_source == "routed" and routing_chapters_by_query and chunk_to_chapter:
                    routed_chapters = routing_chapters_by_query[query_index]
                    if routed_chapters:
                        routed_candidates = [
                            chunk_id
                            for chunk_id in allowed_set
                            if chunk_to_chapter.get(chunk_id) in routed_chapters
                        ]
                        if routed_candidates:
                            routed_candidates.sort(
                                key=lambda chunk_id: scores[chunk_index_by_id[chunk_id]],
                                reverse=True,
                            )
                            boost_seed_ids = routed_candidates[:boost_seed_top_n]
                else:
                    ranked_indices = np.argsort(scores)[::-1]
                    for idx in ranked_indices:
                        chunk_id = chunk_id_by_index[int(idx)]
                        if chunk_document_ids and chunk_document_ids.get(chunk_id) != document_id:
                            continue
                        if chunk_id not in allowed_set:
                            continue
                        boost_seed_ids.append(chunk_id)
                        if len(boost_seed_ids) >= boost_seed_top_n:
                            break

                seed_set = set(boost_seed_ids)
                if seed_set:
                    allowed_kinds_inner: Set[str] = set()
                    if graph_boost_same_kind_only and chunk_kind_by_id:
                        for seed_id in seed_set:
                            seed_kind = chunk_kind_by_id.get(seed_id)
                            if seed_kind:
                                allowed_kinds_inner.add(seed_kind)

                    boosted_by_depth: Dict[int, Set[str]] = {0: set(seed_set)}
                    seen = set(seed_set)
                    frontier = set(seed_set)
                    if graph_boost_depth > 0:
                        for depth in range(1, graph_boost_depth + 1):
                            next_frontier: Set[str] = set()
                            for node_id in frontier:
                                for neighbor in adjacency.get(node_id, set()):
                                    if neighbor in seen:
                                        continue
                                    if graph_boost_same_kind_only and allowed_kinds_inner and chunk_kind_by_id:
                                        candidate_kind = chunk_kind_by_id.get(neighbor)
                                        if candidate_kind and candidate_kind not in allowed_kinds_inner:
                                            continue
                                    seen.add(neighbor)
                                    next_frontier.add(neighbor)
                            if not next_frontier:
                                break
                            boosted_by_depth[depth] = next_frontier
                            frontier = next_frontier

                    boost_candidates = None
                    if graph_boost_top_k:
                        top_indices = np.argsort(scores)[::-1][:graph_boost_top_k]
                        boost_candidates = {
                            chunk_id_by_index[int(idx)] for idx in top_indices
                        }

                    for depth, boosted_ids in boosted_by_depth.items():
                        depth_boost = graph_boost * (graph_boost_decay ** depth)
                        if depth_boost == 0:
                            continue
                        for boosted_id in boosted_ids:
                            if boosted_id not in allowed_set:
                                continue
                            if boost_candidates is not None and boosted_id not in boost_candidates:
                                continue
                            idx = chunk_index_by_id.get(boosted_id)
                            if idx is None:
                                continue
                            scores[idx] += depth_boost
                            boosted_count += 1

            routing_boosted_count = 0
            if routing_boost and routing_boost_ids:
                for boosted_id in routing_boost_ids:
                    if boosted_id not in allowed_set:
                        continue
                    if routing_boost_pool_ids is not None and boosted_id not in routing_boost_pool_ids:
                        continue
                    idx = chunk_index_by_id.get(boosted_id)
                    if idx is None:
                        continue
                    scores[idx] += routing_boost
                    routing_boosted_count += 1
        else:
            boosted_count = 0
            boost_seed_ids = []
            routing_boosted_count = 0

        ranked_indices = np.argsort(scores)[::-1]
        ranked_chunk_ids = [chunk_id_by_index[int(idx)] for idx in ranked_indices]

        answer_similarity_by_k: Dict[str, Optional[float]] = {}
        if answer_embeddings is not None:
            answer_text = None
            if answer_texts and query_index < len(answer_texts):
                answer_text = answer_texts[query_index]
            if answer_text:
                answer_embedding = answer_embeddings[query_index]
                if max_k:
                    top_indices = ranked_indices[:max_k]
                    answer_scores = chunk_embeddings[top_indices] @ answer_embedding
                    max_seen = -float("inf")
                    for idx, score in enumerate(answer_scores, start=1):
                        if score > max_seen:
                            max_seen = float(score)
                        if idx in top_k_list:
                            key = f"answer_similarity@{idx}"
                            answer_similarity_by_k[key] = max_seen
                            answer_similarity_sums[idx] += max_seen
                            answer_similarity_counts[idx] += 1
            else:
                for k in top_k_list:
                    answer_similarity_by_k[f"answer_similarity@{k}"] = None

        if allowed_books and len(allowed_books) == 1 and chunk_book_ids:
            for k in top_k_list:
                top_ids = ranked_chunk_ids[:k]
                contamination_total[k] += 1
                if any(chunk_book_ids.get(chunk_id) not in allowed_books for chunk_id in top_ids):
                    contamination_hits[k] += 1

        first_rank = None
        for rank_idx, chunk_id in enumerate(ranked_chunk_ids, start=1):
            if chunk_id in expected_set:
                first_rank = rank_idx
                break

        if first_rank is not None:
            reciprocal_ranks.append(1.0 / first_rank)

        for k in top_k_list:
            top_ids = set(ranked_chunk_ids[:k])
            if expected_set & top_ids:
                hits_by_k[k] += 1

        top_results = []
        if max_k:
            top_indices = ranked_indices[:max_k]
            for rank_idx, idx in enumerate(top_indices, start=1):
                chunk_id = chunk_id_by_index[int(idx)]
                top_results.append(
                    {
                        "rank": rank_idx,
                        "chunk_id": chunk_id,
                        "score": float(scores[int(idx)]),
                    }
                )

        query_details.append(
            {
                "query_index": query_index,
                "expected_chunk_ids": expected,
                "expected_found": first_rank is not None,
                "expected_rank": first_rank,
                "top_results": top_results,
                "graph_boost_applied": None if not graph_boost else bool(boosted_count),
                "graph_boosted_count": None if not graph_boost else boosted_count,
                "graph_boost_seed_source": None if not graph_boost else graph_boost_source,
                "graph_boost_seed_ids": None if not graph_boost else boost_seed_ids,
                "routing_boost_applied": None if not routing_boost else bool(routing_boosted_count),
                "routing_boosted_count": None if not routing_boost else routing_boosted_count,
                **answer_similarity_by_k,
            }
        )

    query_count = len(expected_ids)
    evaluated_queries = query_count - missing_expected
    hit_rates = {
        f"hit@{k}": (hits_by_k[k] / evaluated_queries) if evaluated_queries else 0.0
        for k in top_k_list
    }
    contamination_rates = {
        f"contamination@{k}": (contamination_hits[k] / contamination_total[k])
        if contamination_total[k]
        else 0.0
        for k in top_k_list
    }
    mrr = float(np.mean(reciprocal_ranks)) if reciprocal_ranks else 0.0
    evaluability = (evaluated_queries / query_count) if query_count else 0.0
    # NOTE: "evaluability" was formerly called "coverage" but that term was misleading.
    # Evaluability = fraction of queries where expected chunk exists in corpus.
    # hit@k = fraction of evaluated queries where gold appears in top-k (the actual retrieval success rate).
    answer_similarity = None
    if answer_embeddings is not None:
        answer_similarity = {
            f"answer_similarity@{k}": (
                answer_similarity_sums[k] / answer_similarity_counts[k]
                if answer_similarity_counts[k]
                else None
            )
            for k in top_k_list
        }

    return {
        "query_count": query_count,
        "evaluated_queries": evaluated_queries,
        "missing_expected": missing_expected,
        "evaluability": evaluability,
        "coverage": evaluability,  # Backward compatibility alias (deprecated)
        "mrr": mrr,
        "hit_rates": hit_rates,
        "cross_book_contamination": contamination_rates if contamination_rates else None,
        "answer_similarity": answer_similarity,
        "graph_boost": graph_boost,
        "graph_boost_depth": graph_boost_depth,
        "graph_boost_top_k": graph_boost_top_k,
        "graph_boost_source": graph_boost_source,
        "graph_boost_seed_top_n": graph_boost_seed_top_n,
        "graph_boost_same_kind_only": graph_boost_same_kind_only,
        "graph_boost_decay": graph_boost_decay,
    }, query_details


def estimate_scoring_time_ms(
    query_embeddings: np.ndarray,
    chunk_embeddings: np.ndarray,
    expected_ids: List[List[str]],
    chunk_ids: List[str],
    top_k: Iterable[int],
    *,
    sample_size: int = 10,
    adjacency_by_document: Optional[Dict[str, Dict[str, Set[str]]]] = None,
    query_document_ids: Optional[List[str]] = None,
    query_book_ids: Optional[List[str]] = None,
    query_allowed_book_ids: Optional[List[Optional[Set[str]]]] = None,
    chunk_document_ids: Optional[Dict[str, str]] = None,
    chunk_book_ids: Optional[Dict[str, str]] = None,
    chunk_kind_by_id: Optional[Dict[str, Optional[str]]] = None,
    allowed_chunk_ids_by_query: Optional[List[Optional[Set[str]]]] = None,
    graph_boost: float = 0.0,
    graph_boost_depth: int = 1,
    graph_boost_top_k: Optional[int] = None,
    graph_boost_source: str = "expected",
    graph_boost_seed_top_n: int = 1,
    graph_boost_same_kind_only: bool = False,
    graph_boost_decay: float = 1.0,
    routing_boost: float = 0.0,
    routing_boost_by_query: Optional[List[Optional[Set[str]]]] = None,
    routing_boost_pool_multiplier: float = 1.0,
    routing_chapters_by_query: Optional[List[Optional[Set[str]]]] = None,
    chunk_to_chapter: Optional[Dict[str, str]] = None,
) -> Optional[int]:
    if query_embeddings.size == 0 or chunk_embeddings.size == 0:
        return None
    sample_count = min(max(1, int(sample_size)), len(expected_ids))
    if sample_count == 0:
        return None
    sample_embeddings = query_embeddings[:sample_count]
    sample_expected = expected_ids[:sample_count]
    sample_query_docs = query_document_ids[:sample_count] if query_document_ids else None
    sample_query_books = query_book_ids[:sample_count] if query_book_ids else None
    sample_allowed_books = (
        query_allowed_book_ids[:sample_count] if query_allowed_book_ids else None
    )
    start = time.perf_counter()
    score_queries(
        sample_embeddings,
        chunk_embeddings,
        sample_expected,
        chunk_ids,
        top_k,
        adjacency_by_document=adjacency_by_document,
        query_document_ids=sample_query_docs,
        query_book_ids=sample_query_books,
        query_allowed_book_ids=sample_allowed_books,
        chunk_document_ids=chunk_document_ids,
        chunk_book_ids=chunk_book_ids,
        chunk_kind_by_id=chunk_kind_by_id,
        allowed_chunk_ids_by_query=allowed_chunk_ids_by_query[:sample_count]
        if allowed_chunk_ids_by_query
        else None,
        graph_boost=graph_boost,
        graph_boost_depth=graph_boost_depth,
        graph_boost_top_k=graph_boost_top_k,
        graph_boost_source=graph_boost_source,
        graph_boost_seed_top_n=graph_boost_seed_top_n,
        graph_boost_same_kind_only=graph_boost_same_kind_only,
        graph_boost_decay=graph_boost_decay,
        routing_boost=routing_boost,
        routing_boost_by_query=routing_boost_by_query[:sample_count]
        if routing_boost_by_query
        else None,
        routing_boost_pool_multiplier=routing_boost_pool_multiplier,
        routing_chapters_by_query=routing_chapters_by_query[:sample_count]
        if routing_chapters_by_query
        else None,
        chunk_to_chapter=chunk_to_chapter,
    )
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    if elapsed_ms <= 0:
        return None
    estimated_ms = int((elapsed_ms / sample_count) * len(expected_ids))
    return estimated_ms

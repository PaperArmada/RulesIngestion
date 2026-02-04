from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    from enrichment.chunks import EnrichedChunk


def compare_retrieval_runs(
    baseline_details: List[Dict[str, Any]],
    traversal_details: List[Dict[str, Any]],
    top_k_list: List[int],
) -> Dict[str, Any]:
    baseline_by_index = {detail["query_index"]: detail for detail in baseline_details}
    traversal_by_index = {detail["query_index"]: detail for detail in traversal_details}
    regressions: Dict[str, int] = {f"hit@{k}": 0 for k in top_k_list}
    improvements: Dict[str, int] = {f"hit@{k}": 0 for k in top_k_list}
    total: Dict[str, int] = {f"hit@{k}": 0 for k in top_k_list}

    for query_index, baseline_detail in baseline_by_index.items():
        traversal_detail = traversal_by_index.get(query_index)
        if not traversal_detail:
            continue
        baseline_rank = baseline_detail.get("expected_rank")
        traversal_rank = traversal_detail.get("expected_rank")
        for k in top_k_list:
            key = f"hit@{k}"
            baseline_hit = baseline_rank is not None and baseline_rank <= k
            traversal_hit = traversal_rank is not None and traversal_rank <= k
            if baseline_hit and not traversal_hit:
                regressions[key] += 1
            elif traversal_hit and not baseline_hit:
                improvements[key] += 1
            total[key] += 1

    monotonic_ok = {key: regressions[key] == 0 for key in regressions}
    return {
        "total_compared": total,
        "regressions": regressions,
        "improvements": improvements,
        "monotonic_ok": monotonic_ok,
    }


def compute_reachability_monotonicity(
    expected_ids: List[List[str]],
    chunk_to_chapter: Dict[str, str],
    pool_chapters_by_query: List[Set[str]],
    final_chapters_by_query: List[Set[str]],
) -> Dict[str, Any]:
    lost_at_pool = 0
    lost_at_final = 0
    loss_details: List[Dict[str, Any]] = []
    reachable_queries = 0

    for query_idx, expected in enumerate(expected_ids):
        expected_chapters: Set[str] = set()
        for chunk_id in expected:
            chapter_id = chunk_to_chapter.get(chunk_id)
            if chapter_id:
                expected_chapters.add(chapter_id)
        if not expected_chapters:
            continue
        reachable_queries += 1
        pool_chapters = (
            pool_chapters_by_query[query_idx]
            if query_idx < len(pool_chapters_by_query)
            else set()
        )
        final_chapters = (
            final_chapters_by_query[query_idx]
            if query_idx < len(final_chapters_by_query)
            else set()
        )
        lost_pool = not (expected_chapters & pool_chapters)
        lost_final = not (expected_chapters & final_chapters)
        if lost_pool:
            lost_at_pool += 1
        if lost_final:
            lost_at_final += 1
        if lost_pool or lost_final:
            loss_details.append(
                {
                    "query_index": query_idx,
                    "expected_chapters": sorted(expected_chapters),
                    "pool_chapters": sorted(pool_chapters),
                    "final_chapters": sorted(final_chapters),
                }
            )

    pool_recall = float((reachable_queries - lost_at_pool) / reachable_queries) if reachable_queries else 0.0
    final_recall = float((reachable_queries - lost_at_final) / reachable_queries) if reachable_queries else 0.0
    return {
        "pool_recall": pool_recall,
        "final_recall": final_recall,
        "lost_at_pool": lost_at_pool,
        "lost_at_final": lost_at_final,
        "reachable_queries": reachable_queries,
        "reachability_monotonic": lost_at_pool == 0 and lost_at_final == 0,
        "loss_details": loss_details[:50],
    }


def compute_cross_book_reachability(
    expected_ids: List[List[str]],
    chunk_to_chapter: Dict[str, str],
    chunk_book_ids: Dict[str, str],
    query_book_ids: List[str],
    query_allowed_book_ids: List[Optional[Set[str]]],
    pool_chapters_by_query: List[Set[str]],
    final_chapters_by_query: List[Set[str]],
) -> Dict[str, Any]:
    explicit_queries = 0
    explicit_with_cross_gold = 0
    pool_hits = 0
    final_hits = 0

    for query_idx, expected in enumerate(expected_ids):
        if query_idx >= len(query_allowed_book_ids) or query_idx >= len(query_book_ids):
            continue
        allowed_books = query_allowed_book_ids[query_idx]
        primary_book = query_book_ids[query_idx]
        if not allowed_books or not primary_book or primary_book == "unknown":
            continue
        if not any(book != primary_book for book in allowed_books):
            continue
        explicit_queries += 1

        cross_gold_chapters: Set[str] = set()
        for chunk_id in expected:
            book_id = chunk_book_ids.get(chunk_id)
            if not book_id or book_id == primary_book:
                continue
            if book_id not in allowed_books:
                continue
            chapter_id = chunk_to_chapter.get(chunk_id)
            if chapter_id:
                cross_gold_chapters.add(chapter_id)

        if not cross_gold_chapters:
            continue
        explicit_with_cross_gold += 1

        pool_chapters = pool_chapters_by_query[query_idx] if query_idx < len(pool_chapters_by_query) else set()
        final_chapters = final_chapters_by_query[query_idx] if query_idx < len(final_chapters_by_query) else set()
        if cross_gold_chapters & pool_chapters:
            pool_hits += 1
        if cross_gold_chapters & final_chapters:
            final_hits += 1

    pool_recall = float(pool_hits / explicit_with_cross_gold) if explicit_with_cross_gold else 0.0
    final_recall = float(final_hits / explicit_with_cross_gold) if explicit_with_cross_gold else 0.0
    return {
        "explicit_cross_book_queries": explicit_queries,
        "explicit_with_cross_gold": explicit_with_cross_gold,
        "pool_recall": pool_recall,
        "final_recall": final_recall,
    }


def compute_baseline_delta(
    baseline_summary: Dict[str, Any], current_summary: Dict[str, Any]
) -> Dict[str, Any]:
    def _delta_metric(key: str) -> Optional[float]:
        if key not in baseline_summary or key not in current_summary:
            return None
        try:
            return float(current_summary[key]) - float(baseline_summary[key])
        except (TypeError, ValueError):
            return None

    def _delta_hit_rates(key: str) -> Dict[str, float]:
        baseline = baseline_summary.get(key) or {}
        current = current_summary.get(key) or {}
        deltas: Dict[str, float] = {}
        for rate_key in current.keys():
            if rate_key in baseline:
                deltas[rate_key] = float(current[rate_key]) - float(baseline[rate_key])
        return deltas

    delta = {
        "coverage": _delta_metric("coverage"),
        "mrr": _delta_metric("mrr"),
        "hit_rates": _delta_hit_rates("hit_rates"),
    }
    if current_summary.get("mrr_expanded") is not None and baseline_summary.get("mrr_expanded") is not None:
        delta.update(
            {
                "coverage_expanded": _delta_metric("coverage_expanded"),
                "mrr_expanded": _delta_metric("mrr_expanded"),
                "hit_rates_expanded": _delta_hit_rates("hit_rates_expanded"),
            }
        )
    return delta


def compute_entity_coverage_metrics(
    chunks: List["EnrichedChunk"],
    graph: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compute what % of chunks have at least one describing entity.

    Use this to establish baseline entity coverage before/after extraction
    improvements (e.g. header-scope propagation).
    """
    chunk_ids = {c.id for c in chunks}
    rule_bearing_chunk_ids = {c.id for c in chunks if c.is_rule_bearing}

    chunk_to_entities: Dict[str, List[str]] = {}
    for edge in graph.get("edges", []):
        if edge.get("relation") == "describes":
            target = edge.get("target")
            source = edge.get("source")
            if source in chunk_ids and target:
                chunk_to_entities.setdefault(source, []).append(target)

    chunks_with_entities = set(chunk_to_entities.keys())
    rule_bearing_with_entities = rule_bearing_chunk_ids & chunks_with_entities

    return {
        "total_chunks": len(chunk_ids),
        "rule_bearing_chunks": len(rule_bearing_chunk_ids),
        "chunks_with_entities": len(chunks_with_entities),
        "rule_bearing_with_entities": len(rule_bearing_with_entities),
        "chunk_entity_coverage": len(chunks_with_entities) / max(len(chunk_ids), 1),
        "rule_bearing_entity_coverage": len(rule_bearing_with_entities)
        / max(len(rule_bearing_chunk_ids), 1),
        "chunks_without_entities": len(chunk_ids - chunks_with_entities),
        "rule_bearing_without_entities": len(
            rule_bearing_chunk_ids - rule_bearing_with_entities
        ),
    }

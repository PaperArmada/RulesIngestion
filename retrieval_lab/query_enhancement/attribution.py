"""Query enhancement attribution metrics.

Compute how much query enhancement contributed to retrieval quality:
- candidate_inflation: how many more candidates the enhanced run produces
- expansion_contribution: % of queries where an expansion (not original) introduced the first gold hit
- gold_found_from_original_only: % of queries where the original query was sufficient
"""

from __future__ import annotations

import logging
import statistics
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def compute_enhancement_attribution(
    ranked_lists: List[List[str]],
    baseline_ranked_lists: Optional[List[List[str]]],
    grounded_queries: List[Dict[str, Any]],
    expansion_logs: Optional[List[List[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Compute attribution metrics for query enhancement.

    Args:
        ranked_lists: enhanced retrieval results (one list of doc IDs per query)
        baseline_ranked_lists: results from baseline (no enhancement), or None
        grounded_queries: query dicts with gold_unit_ids
        expansion_logs: per-query expansion metadata from the enhancer

    Returns:
        Dict with attribution metrics
    """
    n_queries = len(ranked_lists)
    if n_queries == 0:
        return {"n_queries": 0}

    candidate_sizes = [len(rl) for rl in ranked_lists]
    median_candidates = statistics.median(candidate_sizes) if candidate_sizes else 0

    inflation_ratios: List[float] = []
    if baseline_ranked_lists and len(baseline_ranked_lists) == n_queries:
        for i in range(n_queries):
            base_size = len(baseline_ranked_lists[i])
            enh_size = len(ranked_lists[i])
            if base_size > 0:
                inflation_ratios.append(enh_size / base_size)

    gold_from_original_only = 0
    gold_from_expansion = 0
    no_gold = 0

    for i, q in enumerate(grounded_queries):
        gold_ids = set(q.get("gold_unit_ids", []) or [])
        if not gold_ids:
            no_gold += 1
            continue

        enhanced_has_gold = bool(gold_ids & set(ranked_lists[i]))
        if baseline_ranked_lists and i < len(baseline_ranked_lists):
            baseline_has_gold = bool(gold_ids & set(baseline_ranked_lists[i]))
            if enhanced_has_gold and not baseline_has_gold:
                gold_from_expansion += 1
            elif enhanced_has_gold and baseline_has_gold:
                gold_from_original_only += 1
            # else: no gold in either
        elif enhanced_has_gold:
            gold_from_original_only += 1

    grounded_count = n_queries - no_gold

    return {
        "n_queries": n_queries,
        "median_candidate_set_size": median_candidates,
        "candidate_inflation_median": statistics.median(inflation_ratios) if inflation_ratios else None,
        "candidate_inflation_p95": (
            sorted(inflation_ratios)[int(len(inflation_ratios) * 0.95)]
            if len(inflation_ratios) > 1 else (inflation_ratios[0] if inflation_ratios else None)
        ),
        "gold_from_original_only": gold_from_original_only,
        "gold_from_expansion": gold_from_expansion,
        "expansion_contribution_pct": (
            round(100.0 * gold_from_expansion / grounded_count, 1) if grounded_count > 0 else 0.0
        ),
        "enhancement_mode": _infer_mode(expansion_logs),
    }


def _infer_mode(expansion_logs: Optional[List[List[Dict[str, Any]]]]) -> str:
    """Infer the enhancement mode from expansion logs."""
    if not expansion_logs:
        return "none"
    sources = set()
    for group in expansion_logs:
        for entry in group:
            sources.add(entry.get("source", ""))
    sources.discard("original")
    if not sources:
        return "none"
    if "llm" in sources and "dict" in sources:
        return "llm+dict"
    if "llm" in sources:
        return "llm"
    if "dict" in sources:
        return "dict"
    if "decompose" in sources:
        return "decompose"
    return "unknown"

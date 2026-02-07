"""
Counterfactual validation harness for failure classes A–E.

For each failure class, run a minimal counterfactual that changes only one layer.
See Docs/PLAN-Failure-Taxonomy-And-Constraints.md Phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from traversal import TraversalIndex, TraversalConfig

# Default top-k for C/D counterfactuals (rank by authority, take top_k)
DEFAULT_TOP_K = 10

# Infinite-traversal budget for B
INFINITE_BUDGET_MAX_NODES = 50000
INFINITE_BUDGET_MAX_DEPTH = 15

# Pedagogical-scope keywords for E (glossary / intro / summary)
PEDAGOGICAL_SCOPE_KEYWORDS = ("glossary", "introduction", "intro", "summary", "overview")


@dataclass
class CounterfactualResult:
    """
    Result of running one counterfactual (one failure class).

    Attributes:
        class_tested: "A" | "B" | "C" | "D" | "E"
        baseline_recall: Fraction of queries with any gold in baseline retrieval
        counterfactual_recall: Fraction with any gold under counterfactual
        delta: counterfactual_recall - baseline_recall
        queries_affected: Query IDs that flipped miss→hit
        total_queries: Number of queries evaluated
    """
    class_tested: str
    baseline_recall: float
    counterfactual_recall: float
    delta: float
    queries_affected: List[str] = field(default_factory=list)
    total_queries: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "class_tested": self.class_tested,
            "baseline_recall": self.baseline_recall,
            "counterfactual_recall": self.counterfactual_recall,
            "delta": self.delta,
            "queries_affected": self.queries_affected,
            "total_queries": self.total_queries,
        }


def _collect_queries_with_gold(
    batches: List[Dict[str, Any]],
) -> List[tuple[str, str, List[str], Dict[str, Any]]]:
    """Return list of (query_id, question, gold_ids, batch_metadata)."""
    out = []
    for batch in batches:
        metadata = batch.get("metadata", {})
        for query in batch.get("queries", []):
            query_id = query.get("id", "")
            question = query.get("question", "")
            gold_ids = query.get("gold_chunk_ids") or []
            if not gold_ids:
                continue
            out.append((query_id, question, gold_ids, metadata))
    return out


def _baseline_hits(
    index: "TraversalIndex",
    config: Optional["TraversalConfig"],
    queries: List[tuple[str, str, List[str], Dict[str, Any]]],
) -> Dict[str, bool]:
    """Run baseline retrieval for each query; return query_id -> hit."""
    from traversal import retrieve_candidates

    hits = {}
    for query_id, question, gold_ids, _ in queries:
        result = retrieve_candidates(question, index, config=config)
        gold_set = set(gold_ids)
        hit = bool(gold_set & result.candidate_ids)
        hits[query_id] = hit
    return hits


def run_counterfactual_A(
    queries: List[tuple[str, str, List[str], Dict[str, Any]]],
    index: "TraversalIndex",
    config: Optional["TraversalConfig"],
    baseline_hits: Dict[str, bool],
) -> CounterfactualResult:
    """
    Counterfactual A: Oracle seeding (inject gold_chunk_ids into seeds).

    Same traversal and selection; only seeds change to gold. If recall jumps,
    seed failure is confirmed.
    """
    from traversal import classify_intent
    from traversal.policy import TraversalBudget, get_policy
    from traversal.traverse import traverse, expand_with_siblings

    if config is None:
        from traversal.policy import get_policy as _gp
        policy_getter = lambda intent: _gp(intent)
    else:
        policy_getter = lambda intent: config.get_policy(intent)

    cf_hits = {}
    for query_id, question, gold_ids, _ in queries:
        intent = classify_intent(question, None)
        policy = policy_getter(intent)
        budget = TraversalBudget(
            max_nodes=policy.chunk_limit or 2000,
            max_depth=policy.max_depth,
        )
        # Oracle seeds: gold chunks that exist in the graph
        oracle_seeds = {g for g in gold_ids if g in index.adjacency}
        if not oracle_seeds:
            cf_hits[query_id] = False
            continue
        candidates = traverse(index, oracle_seeds, policy, budget)
        if policy.include_siblings:
            candidates = expand_with_siblings(index, candidates)
        gold_set = set(gold_ids)
        cf_hits[query_id] = bool(gold_set & candidates)

    total = len(queries)
    baseline_hit_count = sum(1 for (qid, _, _, _) in queries if baseline_hits.get(qid, False))
    cf_hit_count = sum(1 for (qid, _, _, _) in queries if cf_hits.get(qid, False))
    baseline_recall = baseline_hit_count / total if total else 0.0
    cf_recall = cf_hit_count / total if total else 0.0
    affected = [qid for (qid, _, _, _) in queries if not baseline_hits.get(qid, False) and cf_hits.get(qid, False)]

    return CounterfactualResult(
        class_tested="A",
        baseline_recall=baseline_recall,
        counterfactual_recall=cf_recall,
        delta=cf_recall - baseline_recall,
        queries_affected=affected,
        total_queries=total,
    )


def run_counterfactual_B(
    queries: List[tuple[str, str, List[str], Dict[str, Any]]],
    index: "TraversalIndex",
    config: Optional["TraversalConfig"],
    baseline_hits: Dict[str, bool],
) -> CounterfactualResult:
    """
    Counterfactual B: Infinite traversal (no depth/node budget).

    Same seeds and selection; only budget is very high. If recall jumps,
    connectivity issue is confirmed.
    """
    from traversal import retrieve_candidates
    from traversal.policy import TraversalBudget

    budget = TraversalBudget(
        max_nodes=INFINITE_BUDGET_MAX_NODES,
        max_depth=INFINITE_BUDGET_MAX_DEPTH,
    )
    cf_hits = {}
    for query_id, question, gold_ids, _ in queries:
        result = retrieve_candidates(question, index, config=config, budget=budget)
        gold_set = set(gold_ids)
        cf_hits[query_id] = bool(gold_set & result.candidate_ids)

    total = len(queries)
    baseline_hit_count = sum(1 for (qid, _, _, _) in queries if baseline_hits.get(qid, False))
    cf_hit_count = sum(1 for (qid, _, _, _) in queries if cf_hits.get(qid, False))
    baseline_recall = baseline_hit_count / total if total else 0.0
    cf_recall = cf_hit_count / total if total else 0.0
    affected = [qid for (qid, _, _, _) in queries if not baseline_hits.get(qid, False) and cf_hits.get(qid, False)]

    return CounterfactualResult(
        class_tested="B",
        baseline_recall=baseline_recall,
        counterfactual_recall=cf_recall,
        delta=cf_recall - baseline_recall,
        queries_affected=affected,
        total_queries=total,
    )


def _authority_score(chunk_id: str, index: "TraversalIndex") -> float:
    """
    Higher = more authoritative (canonical). Use doc/section order as proxy:
    earlier in document (lower position) = higher authority.
    Chunk IDs often encode page/position; use lexicographic as fallback.
    """
    chunk = index.chunk_by_id.get(chunk_id)
    if not chunk:
        return 0.0
    section_path = chunk.get("section_path", [])
    # Prefer chunks with "definition" or early sections
    path_lower = " ".join(section_path).lower()
    if "definition" in path_lower or "glossary" in path_lower:
        return 1000.0
    if "introduction" in path_lower or "overview" in path_lower:
        return 500.0
    # Else use inverse of chunk_id length/position (earlier id = higher authority)
    return 100.0 - min(len(chunk_id) // 10, 99)


def run_counterfactual_C(
    queries: List[tuple[str, str, List[str], Dict[str, Any]]],
    index: "TraversalIndex",
    config: Optional["TraversalConfig"],
    baseline_hits: Dict[str, bool],
    top_k: int = DEFAULT_TOP_K,
) -> CounterfactualResult:
    """
    Counterfactual C: Authority-only ranking (rank by authority, ignore BFS depth).

    Same seeds and traversal; selection = top_k by authority score. If recall
    jumps, dominance (gold drowned out by BFS order) is confirmed.
    """
    from traversal import retrieve_candidates

    cf_hits = {}
    for query_id, question, gold_ids, _ in queries:
        result = retrieve_candidates(question, index, config=config)
        if not result.candidate_ids:
            cf_hits[query_id] = False
            continue
        # Rank by authority (higher score first), take top_k
        scored = [(cid, _authority_score(cid, index)) for cid in result.candidate_ids]
        scored.sort(key=lambda x: -x[1])
        top_k_ids = {x[0] for x in scored[:top_k]}
        gold_set = set(gold_ids)
        cf_hits[query_id] = bool(gold_set & top_k_ids)

    total = len(queries)
    baseline_hit_count = sum(1 for (qid, _, _, _) in queries if baseline_hits.get(qid, False))
    cf_hit_count = sum(1 for (qid, _, _, _) in queries if cf_hits.get(qid, False))
    baseline_recall = baseline_hit_count / total if total else 0.0
    cf_recall = cf_hit_count / total if total else 0.0
    affected = [qid for (qid, _, _, _) in queries if not baseline_hits.get(qid, False) and cf_hits.get(qid, False)]

    return CounterfactualResult(
        class_tested="C",
        baseline_recall=baseline_recall,
        counterfactual_recall=cf_recall,
        delta=cf_recall - baseline_recall,
        queries_affected=affected,
        total_queries=total,
    )


def run_counterfactual_D(
    queries: List[tuple[str, str, List[str], Dict[str, Any]]],
    index: "TraversalIndex",
    config: Optional["TraversalConfig"],
    baseline_hits: Dict[str, bool],
    top_k: int = DEFAULT_TOP_K,
) -> CounterfactualResult:
    """
    Counterfactual D: Canonical-authority selection (force-select highest-authority
    chunk among candidates when multiple exist). Uses same authority ranking as C;
    reports as class D for interpretation.
    """
    result = run_counterfactual_C(
        queries, index, config, baseline_hits, top_k=top_k,
    )
    return CounterfactualResult(
        class_tested="D",
        baseline_recall=result.baseline_recall,
        counterfactual_recall=result.counterfactual_recall,
        delta=result.delta,
        queries_affected=result.queries_affected,
        total_queries=result.total_queries,
    )


def _is_pedagogical_scope(chunk_id: str, index: "TraversalIndex") -> bool:
    """True if chunk is in glossary/intro/summary scope."""
    chunk = index.chunk_by_id.get(chunk_id)
    if not chunk:
        return False
    section_path = chunk.get("section_path", [])
    path_lower = " ".join(section_path).lower()
    return any(kw in path_lower for kw in PEDAGOGICAL_SCOPE_KEYWORDS)


def run_counterfactual_E(
    queries: List[tuple[str, str, List[str], Dict[str, Any]]],
    index: "TraversalIndex",
    config: Optional["TraversalConfig"],
    baseline_hits: Dict[str, bool],
) -> CounterfactualResult:
    """
    Counterfactual E: Pedagogical-scope filter (restrict candidates to
    glossary/intro/summary chunks). Same seeds and traversal; selection filtered.
    """
    from traversal import retrieve_candidates

    cf_hits = {}
    for query_id, question, gold_ids, _ in queries:
        result = retrieve_candidates(question, index, config=config)
        filtered = {cid for cid in result.candidate_ids if _is_pedagogical_scope(cid, index)}
        gold_set = set(gold_ids)
        cf_hits[query_id] = bool(gold_set & filtered)

    total = len(queries)
    baseline_hit_count = sum(1 for (qid, _, _, _) in queries if baseline_hits.get(qid, False))
    cf_hit_count = sum(1 for (qid, _, _, _) in queries if cf_hits.get(qid, False))
    baseline_recall = baseline_hit_count / total if total else 0.0
    cf_recall = cf_hit_count / total if total else 0.0
    affected = [qid for (qid, _, _, _) in queries if not baseline_hits.get(qid, False) and cf_hits.get(qid, False)]

    return CounterfactualResult(
        class_tested="E",
        baseline_recall=baseline_recall,
        counterfactual_recall=cf_recall,
        delta=cf_recall - baseline_recall,
        queries_affected=affected,
        total_queries=total,
    )


def run_all_counterfactuals(
    batches: List[Dict[str, Any]],
    index: "TraversalIndex",
    config: Optional["TraversalConfig"],
    *,
    top_k: int = DEFAULT_TOP_K,
    classes: Optional[List[str]] = None,
) -> List[CounterfactualResult]:
    """
    Run baseline once, then each counterfactual A–E (or subset).

    Returns list of CounterfactualResult, one per class run.
    """
    queries = _collect_queries_with_gold(batches)
    if not queries:
        return []

    baseline_hits = _baseline_hits(index, config, queries)
    to_run = classes or ["A", "B", "C", "D", "E"]
    results = []

    runners = {
        "A": lambda: run_counterfactual_A(queries, index, config, baseline_hits),
        "B": lambda: run_counterfactual_B(queries, index, config, baseline_hits),
        "C": lambda: run_counterfactual_C(queries, index, config, baseline_hits, top_k=top_k),
        "D": lambda: run_counterfactual_D(queries, index, config, baseline_hits, top_k=top_k),
        "E": lambda: run_counterfactual_E(queries, index, config, baseline_hits),
    }
    for c in to_run:
        if c in runners:
            results.append(runners[c]())
    return results

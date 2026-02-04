"""
Failure taxonomy for graph-based retrieval.

Labels each gold miss with exactly one of A–E using observable signals.
See Docs/PLAN-Failure-Taxonomy-And-Constraints.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from traversal import TraversalIndex, TraversalConfig


# Default top-k used to decide "gold drowned out" (dominance)
DEFAULT_TOP_K = 10

# Threshold: frontier entropy below this suggests hub collapse (dominance)
LOW_ENTROPY_THRESHOLD = 1.0


@dataclass
class FailureSignals:
    """
    Observable signals used to assign a failure class.

    All fields are optional; None means not computed or not applicable.
    """

    gold_in_reachable_set: Optional[bool] = None
    gold_reachable_at_infinite_depth: Optional[bool] = None
    gold_rank_if_reachable: Optional[int] = None
    seed_component_contains_gold: Optional[bool] = None
    frontier_entropy_at_termination: Optional[float] = None
    authority_inversion_detected: Optional[bool] = None
    batch_reasoning_mode: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON (e.g. failure_signals in batch output)."""
        return {
            "gold_in_reachable_set": self.gold_in_reachable_set,
            "gold_reachable_at_infinite_depth": self.gold_reachable_at_infinite_depth,
            "gold_rank_if_reachable": self.gold_rank_if_reachable,
            "seed_component_contains_gold": self.seed_component_contains_gold,
            "frontier_entropy_at_termination": self.frontier_entropy_at_termination,
            "authority_inversion_detected": self.authority_inversion_detected,
            "batch_reasoning_mode": self.batch_reasoning_mode,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FailureSignals":
        """Deserialize from JSON."""
        return cls(
            gold_in_reachable_set=d.get("gold_in_reachable_set"),
            gold_reachable_at_infinite_depth=d.get("gold_reachable_at_infinite_depth"),
            gold_rank_if_reachable=d.get("gold_rank_if_reachable"),
            seed_component_contains_gold=d.get("seed_component_contains_gold"),
            frontier_entropy_at_termination=d.get("frontier_entropy_at_termination"),
            authority_inversion_detected=d.get("authority_inversion_detected"),
            batch_reasoning_mode=d.get("batch_reasoning_mode"),
        )


def _entropy_from_per_depth(per_depth: Dict[int, int]) -> float:
    """Compute entropy of depth distribution: -sum(p*log(p))."""
    total = sum(per_depth.values())
    if total <= 0:
        return 0.0
    h = 0.0
    for count in per_depth.values():
        if count > 0:
            p = count / total
            h -= p * math.log(p)
    return h


def compute_signals(
    query: str,
    gold_ids: List[str],
    index: "TraversalIndex",
    config: Optional["TraversalConfig"] = None,
    *,
    top_k: int = DEFAULT_TOP_K,
    infinite_budget_max_nodes: int = 50000,
    infinite_budget_max_depth: int = 15,
    batch_reasoning_mode: Optional[str] = None,
) -> FailureSignals:
    """
    Compute observable signals for one query and its gold chunk(s).

    Runs normal retrieval, infinite-depth traversal, and diagnostics.
    Uses existing traversal APIs only; does not change graph or seeds.

    Args:
        query: The question text.
        gold_ids: List of gold chunk IDs (at least one must be correct).
        index: TraversalIndex (graph + chunks).
        config: Optional TraversalConfig for ruleset-specific policies.
        top_k: Rank threshold for dominance (gold beyond this = drowned out).
        infinite_budget_max_nodes: Node limit for "infinite" traversal.
        infinite_budget_max_depth: Depth limit for "infinite" traversal.

    Returns:
        FailureSignals with all computable fields set.
    """
    from traversal import (
        retrieve_candidates,
        find_anchor_nodes,
        classify_intent,
        traverse,
        traverse_with_diagnostics,
        traverse_with_ranks,
    )
    from traversal.traverse import expand_with_siblings
    from traversal.policy import TraversalBudget, get_policy

    gold_set = set(gold_ids)
    intent = classify_intent(query, None)
    policy = config.get_policy(intent) if config else get_policy(intent)
    anchors = find_anchor_nodes(query, index, config=config)

    # Normal retrieval (same as test_blind_eval)
    result = retrieve_candidates(query, index, config=config)
    candidates = result.candidate_ids

    gold_in_reachable_set = bool(gold_set & candidates)
    gold_reachable_at_infinite_depth = None
    seed_component_contains_gold = None
    gold_rank_if_reachable = None
    frontier_entropy_at_termination = None

    if not anchors:
        # No seeds → we cannot compute infinite reachability or rank
        gold_reachable_at_infinite_depth = False
        seed_component_contains_gold = False
    else:
        # Infinite-depth reachability from current seeds
        inf_budget = TraversalBudget(
            max_nodes=infinite_budget_max_nodes,
            max_depth=infinite_budget_max_depth,
        )
        reached_inf = traverse(index, anchors, policy, inf_budget)
        if policy.include_siblings:
            reached_inf = expand_with_siblings(index, reached_inf)
        gold_reachable_at_infinite_depth = bool(gold_set & reached_inf)
        seed_component_contains_gold = gold_reachable_at_infinite_depth

        # Rank: use traverse_with_ranks (same seeds/policy as retriever)
        budget = TraversalBudget(
            max_nodes=policy.chunk_limit or 2000,
            max_depth=policy.max_depth,
        )
        rank_result = traverse_with_ranks(index, anchors, policy, budget)
        chunk_ranks = rank_result["chunk_ranks"]
        if policy.include_siblings:
            expanded = expand_with_siblings(index, set(chunk_ranks))
            max_rank = max(chunk_ranks.values()) if chunk_ranks else 0
            for cid in expanded:
                if cid not in chunk_ranks:
                    chunk_ranks[cid] = max_rank + 1
        gold_ranks = [chunk_ranks.get(g, 999999) for g in gold_ids if g in candidates]
        gold_rank_if_reachable = min(gold_ranks) if gold_ranks else None

        # Diagnostics: frontier entropy at termination
        diag = traverse_with_diagnostics(index, anchors, policy, budget)
        per_depth = diag.get("per_depth", {})
        frontier_entropy_at_termination = _entropy_from_per_depth(per_depth)

    # Authority inversion: stub until pedagogical signals exist
    authority_inversion_detected = False

    return FailureSignals(
        gold_in_reachable_set=gold_in_reachable_set,
        gold_reachable_at_infinite_depth=gold_reachable_at_infinite_depth,
        gold_rank_if_reachable=gold_rank_if_reachable,
        seed_component_contains_gold=seed_component_contains_gold,
        frontier_entropy_at_termination=frontier_entropy_at_termination,
        authority_inversion_detected=authority_inversion_detected,
        batch_reasoning_mode=batch_reasoning_mode,
    )


def _is_conceptual_batch(batch_metadata: Dict[str, Any]) -> bool:
    """True if batch targets conceptual/reasoning-mode queries (e.g. batch_006)."""
    bid = batch_metadata.get("batch_id", "")
    if bid == "006":
        return True
    reasoning = batch_metadata.get("reasoning_mode") or ""
    if "conceptual" in reasoning.lower():
        return True
    caps = batch_metadata.get("graph_capabilities_tested") or []
    if isinstance(caps, list) and any("conceptual" in str(c).lower() for c in caps):
        return True
    return False


def assign_failure_class(
    signals: FailureSignals,
    batch_metadata: Dict[str, Any],
    *,
    top_k: int = DEFAULT_TOP_K,
) -> Optional[str]:
    """
    Assign exactly one failure class (A–E) or None for hit.

    Rules (deterministic; see PLAN-Failure-Taxonomy-And-Constraints.md §8):
    - Hit: any gold in reachable set and in effective top-k → None
    - A: Gold not in reachable set AND seed component does not contain gold
    - B: Gold not in reachable set AND seed component contains gold (connectivity)
    - C: Gold in reachable set but rank > top_k (drowned out) or low frontier entropy
    - D: Gold in reachable set AND authority_inversion_detected
    - E: Conceptual batch AND class would be A (epistemic: wrong abstraction)

    Returns:
        "A" | "B" | "C" | "D" | "E" | None (None = hit)
    """
    if signals.gold_in_reachable_set:
        if signals.authority_inversion_detected:
            return "D"
        # Gold reachable: check rank vs top_k
        if signals.gold_rank_if_reachable is not None and signals.gold_rank_if_reachable > top_k:
            return "C"
        if (
            signals.frontier_entropy_at_termination is not None
            and signals.frontier_entropy_at_termination < LOW_ENTROPY_THRESHOLD
            and signals.gold_rank_if_reachable is not None
            and signals.gold_rank_if_reachable > top_k
        ):
            return "C"
        return None

    # Gold not in reachable set
    if signals.seed_component_contains_gold:
        return "B"
    # A (seed failure); override to E for conceptual batches (epistemic mismatch)
    if _is_conceptual_batch(batch_metadata):
        return "E"
    return "A"

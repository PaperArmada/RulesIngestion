"""
Reranker for hybrid retrieval.

Combines results from:
1. Deterministic parallel search (term-based)
2. Semantic search (embedding-based)

Uses configurable weights and scoring strategies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class RerankStrategy(Enum):
    """Strategies for combining scores."""
    WEIGHTED_SUM = "weighted_sum"       # score = w1*det + w2*sem
    RECIPROCAL_RANK = "rrf"             # Reciprocal Rank Fusion
    MAX_SCORE = "max"                   # max(det, sem)
    MULTIPLICATIVE = "multiplicative"   # det * sem (requires both)


@dataclass
class RerankConfig:
    """
    Configuration for reranking.
    
    Attributes:
        deterministic_weight: Weight for deterministic search scores (0-1)
        semantic_weight: Weight for semantic search scores (0-1)
        traversal_weight: Weight for traversal depth scores (0-1, only used with RRF)
        strategy: How to combine scores
        anchor_bonus: Extra score for anchor chunks
        term_coverage_bonus: Extra score per matched expansion term
        anchor_term_bonus: Extra score per matched anchor term (higher priority than expansion terms)
        require_both: Only include chunks found by both paths
        min_score: Minimum score threshold
        rrf_k: Smoothing constant for RRF (default 60 from original paper)
    """
    deterministic_weight: float = 0.5
    semantic_weight: float = 0.5
    traversal_weight: float = 0.0  # Optional third signal
    strategy: RerankStrategy = RerankStrategy.WEIGHTED_SUM
    anchor_bonus: float = 1.0
    term_coverage_bonus: float = 0.1
    anchor_term_bonus: float = 0.3  # Higher bonus for anchor term matches
    require_both: bool = False
    min_score: float = 0.0
    rrf_k: int = 60  # Standard RRF constant
    
    def __post_init__(self):
        # Normalize weights for weighted sum strategy
        if self.strategy == RerankStrategy.WEIGHTED_SUM:
            total = self.deterministic_weight + self.semantic_weight
            if total > 0:
                self.deterministic_weight = self.deterministic_weight / total
                self.semantic_weight = self.semantic_weight / total


@dataclass
class RankedChunk:
    """
    A chunk with combined ranking information.
    
    Attributes:
        chunk_id: Unique identifier
        chunk: The chunk data dict
        final_score: Combined score
        deterministic_score: Score from deterministic search
        semantic_score: Score from semantic search
        found_by: Which paths found this chunk ("deterministic", "semantic", "both")
        rank: Position in final ranking (1-indexed)
        terms_matched: Number of expansion terms that matched this chunk
        is_anchor: Whether this was an anchor chunk
    """
    chunk_id: str
    chunk: Dict[str, Any]
    final_score: float
    deterministic_score: float = 0.0
    semantic_score: float = 0.0
    found_by: str = "none"
    rank: int = 0
    terms_matched: int = 0
    is_anchor: bool = False


@dataclass
class RerankResult:
    """
    Result from reranking.
    
    Attributes:
        ranked_chunks: List of RankedChunk sorted by final_score
        total_deterministic: Count of chunks from deterministic search
        total_semantic: Count of chunks from semantic search  
        overlap_count: Count of chunks found by both
        config: The RerankConfig used
        diagnostics: Additional diagnostic info
    """
    ranked_chunks: List[RankedChunk]
    total_deterministic: int
    total_semantic: int
    overlap_count: int
    config: RerankConfig
    diagnostics: Dict[str, Any] = field(default_factory=dict)


def normalize_scores(scores: Dict[str, float]) -> Dict[str, float]:
    """
    Normalize scores to 0-1 range.
    
    Uses min-max normalization.
    """
    if not scores:
        return {}
    
    values = list(scores.values())
    min_val = min(values)
    max_val = max(values)
    
    if max_val == min_val:
        # All same score, normalize to 1.0
        return {k: 1.0 for k in scores}
    
    return {
        k: (v - min_val) / (max_val - min_val)
        for k, v in scores.items()
    }


def compute_rrf_score(
    ranks: List[int],
    k: int = 60,
) -> float:
    """
    Compute Reciprocal Rank Fusion score.
    
    RRF(d) = sum(1 / (k + r)) for each rank r
    
    Args:
        ranks: List of ranks from different systems (1-indexed)
        k: Smoothing constant (default 60 from original RRF paper)
        
    Returns:
        RRF score
    """
    return sum(1.0 / (k + r) for r in ranks if r > 0)


def rerank(
    deterministic_results: List[Dict[str, Any]],
    semantic_results: List[Dict[str, Any]],
    config: RerankConfig,
    anchor_chunk_ids: Optional[Set[str]] = None,
    anchor_terms: Optional[List[str]] = None,
    traversal_ranks: Optional[Dict[str, int]] = None,
) -> RerankResult:
    """
    Combine and rerank results from multiple search paths.
    
    Supports 2-way (det + sem) or 3-way (det + sem + traversal) fusion.
    
    Args:
        deterministic_results: Results from parallel term search
            Each dict should have: chunk_id, chunk, deterministic_score, terms_matched
            Optional: anchor_terms_matched for separate anchor term bonus
        semantic_results: Results from semantic search
            Each dict should have: chunk_id, chunk, semantic_score (or score)
        config: RerankConfig for weights and strategy
        anchor_chunk_ids: Set of anchor chunk IDs for bonus
        anchor_terms: List of anchor terms from original query (for bonus calculation)
        traversal_ranks: Optional dict of chunk_id -> rank from traversal
            (used for 3-way RRF fusion)
        
    Returns:
        RerankResult with ranked chunks
    """
    anchor_chunk_ids = anchor_chunk_ids or set()
    anchor_terms_set = set(anchor_terms) if anchor_terms else set()
    traversal_ranks = traversal_ranks or {}
    
    # Build lookup dicts
    det_by_id: Dict[str, Dict[str, Any]] = {}
    sem_by_id: Dict[str, Dict[str, Any]] = {}
    
    for r in deterministic_results:
        det_by_id[r["chunk_id"]] = r
    
    for r in semantic_results:
        sem_by_id[r["chunk_id"]] = r
    
    # Find all unique chunks (from all three sources)
    all_chunk_ids = set(det_by_id.keys()) | set(sem_by_id.keys())
    if traversal_ranks:
        all_chunk_ids |= set(traversal_ranks.keys())
    
    # Count overlaps
    overlap_ids = set(det_by_id.keys()) & set(sem_by_id.keys())
    det_only_ids = set(det_by_id.keys()) - set(sem_by_id.keys())
    sem_only_ids = set(sem_by_id.keys()) - set(det_by_id.keys())
    trav_only_ids = set(traversal_ranks.keys()) - set(det_by_id.keys()) - set(sem_by_id.keys())
    all_three_ids = set(det_by_id.keys()) & set(sem_by_id.keys()) & set(traversal_ranks.keys())
    
    # Filter if require_both
    if config.require_both:
        all_chunk_ids = overlap_ids
    
    # Extract and normalize scores
    det_scores = {
        cid: r.get("deterministic_score", 0.0)
        for cid, r in det_by_id.items()
    }
    sem_scores = {
        cid: r.get("semantic_score", r.get("score", 0.0))
        for cid, r in sem_by_id.items()
    }
    
    det_scores_norm = normalize_scores(det_scores)
    sem_scores_norm = normalize_scores(sem_scores)
    
    # Build ranks for RRF
    det_ranks = {cid: i + 1 for i, cid in enumerate(
        sorted(det_scores.keys(), key=lambda x: -det_scores.get(x, 0))
    )}
    sem_ranks = {cid: i + 1 for i, cid in enumerate(
        sorted(sem_scores.keys(), key=lambda x: -sem_scores.get(x, 0))
    )}
    # traversal_ranks is already rank-ordered (depth-based)
    
    # Compute final scores
    ranked_chunks: List[RankedChunk] = []
    
    for chunk_id in all_chunk_ids:
        det_score = det_scores_norm.get(chunk_id, 0.0)
        sem_score = sem_scores_norm.get(chunk_id, 0.0)
        
        # Determine which paths found this chunk
        in_det = chunk_id in det_by_id
        in_sem = chunk_id in sem_by_id
        in_trav = chunk_id in traversal_ranks
        
        if in_det and in_sem:
            found_by = "both"
        elif in_det:
            found_by = "deterministic"
        elif in_sem:
            found_by = "semantic"
        else:
            found_by = "traversal"
        
        # Add traversal indicator if present
        if in_trav and found_by != "traversal":
            found_by = found_by + "+traversal"
        
        # Compute combined score based on strategy
        if config.strategy == RerankStrategy.WEIGHTED_SUM:
            final_score = (
                config.deterministic_weight * det_score +
                config.semantic_weight * sem_score
            )
        elif config.strategy == RerankStrategy.RECIPROCAL_RANK:
            det_rank = det_ranks.get(chunk_id, 0)
            sem_rank = sem_ranks.get(chunk_id, 0)
            trav_rank = traversal_ranks.get(chunk_id, 0)
            
            # Collect ranks from each system (0 means not found)
            ranks = []
            if det_rank > 0:
                ranks.append(det_rank)
            if sem_rank > 0:
                ranks.append(sem_rank)
            if trav_rank > 0:
                ranks.append(trav_rank)
            
            final_score = compute_rrf_score(ranks, k=config.rrf_k)
        elif config.strategy == RerankStrategy.MAX_SCORE:
            final_score = max(det_score, sem_score)
        elif config.strategy == RerankStrategy.MULTIPLICATIVE:
            # Only score if in both
            if in_det and in_sem:
                final_score = det_score * sem_score
            else:
                final_score = 0.0
        else:
            final_score = det_score + sem_score
        
        # Apply anchor bonus
        is_anchor = chunk_id in anchor_chunk_ids
        if is_anchor:
            final_score += config.anchor_bonus
        
        # Apply term coverage bonus with separate anchor term weighting
        terms_matched = 0
        anchor_terms_matched = 0
        expansion_terms_matched = 0
        
        if chunk_id in det_by_id:
            terms_matched = det_by_id[chunk_id].get("terms_matched", 0)
            
            # Check if chunk contains anchor terms (from original query)
            # This gives higher priority to chunks matching the original query terms
            if anchor_terms_set:
                chunk_data = det_by_id[chunk_id].get("chunk", {})
                chunk_text = chunk_data.get("text", "").lower() if chunk_data else ""
                for anchor_term in anchor_terms_set:
                    if anchor_term in chunk_text:
                        anchor_terms_matched += 1
                
                expansion_terms_matched = max(0, terms_matched - anchor_terms_matched)
            else:
                expansion_terms_matched = terms_matched
            
            # Apply separate bonuses: anchor terms get higher bonus
            final_score += anchor_terms_matched * config.anchor_term_bonus
            final_score += expansion_terms_matched * config.term_coverage_bonus
        
        # Skip if below threshold
        if final_score < config.min_score:
            continue
        
        # Get chunk data
        chunk = det_by_id.get(chunk_id, {}).get("chunk", {})
        if not chunk and chunk_id in sem_by_id:
            chunk = sem_by_id[chunk_id].get("chunk", {})
        
        ranked_chunks.append(RankedChunk(
            chunk_id=chunk_id,
            chunk=chunk,
            final_score=final_score,
            deterministic_score=det_scores.get(chunk_id, 0.0),
            semantic_score=sem_scores.get(chunk_id, 0.0),
            found_by=found_by,
            terms_matched=terms_matched,
            is_anchor=is_anchor,
        ))
    
    # Sort by final score descending
    ranked_chunks.sort(key=lambda x: -x.final_score)
    
    # Assign ranks
    for i, chunk in enumerate(ranked_chunks):
        chunk.rank = i + 1
    
    # Compute diagnostics
    diagnostics = {
        "total_unique_chunks": len(all_chunk_ids),
        "deterministic_only": len(det_only_ids),
        "semantic_only": len(sem_only_ids),
        "traversal_only": len(trav_only_ids),
        "both_paths": len(overlap_ids),
        "all_three_paths": len(all_three_ids),
        "traversal_included": len(traversal_ranks),
        "anchors_in_results": sum(1 for c in ranked_chunks if c.is_anchor),
        "avg_terms_matched": (
            sum(c.terms_matched for c in ranked_chunks) / max(1, len(ranked_chunks))
        ),
        "score_distribution": {
            "max": max((c.final_score for c in ranked_chunks), default=0),
            "min": min((c.final_score for c in ranked_chunks), default=0),
            "mean": sum(c.final_score for c in ranked_chunks) / max(1, len(ranked_chunks)),
        },
    }
    
    return RerankResult(
        ranked_chunks=ranked_chunks,
        total_deterministic=len(det_by_id),
        total_semantic=len(sem_by_id),
        overlap_count=len(overlap_ids),
        config=config,
        diagnostics=diagnostics,
    )


def get_top_k(result: RerankResult, k: int = 30) -> List[RankedChunk]:
    """Get top-k ranked chunks."""
    return result.ranked_chunks[:k]


def analyze_attribution(result: RerankResult, gold_chunk_ids: Set[str]) -> Dict[str, Any]:
    """
    Analyze where gold chunks came from.
    
    For tuning: understand if deterministic or semantic path is more valuable.
    
    Args:
        result: RerankResult from rerank()
        gold_chunk_ids: Set of expected correct chunk IDs
        
    Returns:
        Attribution analysis dict
    """
    gold_in_results = [c for c in result.ranked_chunks if c.chunk_id in gold_chunk_ids]
    
    attribution = {
        "gold_count": len(gold_chunk_ids),
        "gold_found": len(gold_in_results),
        "gold_from_deterministic_only": 0,
        "gold_from_semantic_only": 0,
        "gold_from_both": 0,
        "gold_from_neither": 0,
        "gold_ranks": [],
        "best_gold_rank": None,
        "worst_gold_rank": None,
    }
    
    for chunk in gold_in_results:
        attribution["gold_ranks"].append(chunk.rank)
        if chunk.found_by == "deterministic":
            attribution["gold_from_deterministic_only"] += 1
        elif chunk.found_by == "semantic":
            attribution["gold_from_semantic_only"] += 1
        elif chunk.found_by == "both":
            attribution["gold_from_both"] += 1
    
    attribution["gold_from_neither"] = (
        len(gold_chunk_ids) - len(gold_in_results)
    )
    
    if attribution["gold_ranks"]:
        attribution["best_gold_rank"] = min(attribution["gold_ranks"])
        attribution["worst_gold_rank"] = max(attribution["gold_ranks"])
    
    return attribution

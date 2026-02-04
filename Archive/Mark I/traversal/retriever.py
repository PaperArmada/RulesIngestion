"""
Complete traversal-only retrieval pipeline.

Composes: Query → Seeds → Traversal → Candidate Set

No embeddings in the retrieval path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore

from .index import TraversalIndex
from .seeds import find_anchor_nodes, select_documents
from .intent import Intent, classify_intent
from .policy import TraversalPolicy, TraversalBudget, INTENT_POLICIES, get_policy
from .traverse import traverse, expand_with_siblings

if TYPE_CHECKING:
    from .config import TraversalConfig


@dataclass
class TraversalResult:
    """
    Result of traversal-only retrieval.
    
    Attributes:
        candidate_ids: Set of chunk IDs in the candidate set
        anchors: Set of anchor node IDs used as seeds
        intent: Classified query intent
        policy: TraversalPolicy used
        diagnostics: Optional diagnostic information
    """
    candidate_ids: Set[str]
    anchors: Set[str]
    intent: Intent
    policy: TraversalPolicy
    diagnostics: Optional[Dict[str, Any]] = None


def retrieve_candidates(
    query: str,
    index: TraversalIndex,
    openai_client: Optional[OpenAI] = None,
    budget: Optional[TraversalBudget] = None,
    include_siblings: Optional[bool] = None,
    config: Optional["TraversalConfig"] = None,
) -> TraversalResult:
    """
    Complete traversal-only retrieval.
    
    Pipeline:
    1. Classify query intent
    2. Find anchor nodes from query terms
    3. Traverse graph with intent-based policy
    4. Optionally expand with siblings
    
    Args:
        query: The query string
        index: TraversalIndex with pre-built indexes
        openai_client: Optional OpenAI client for LLM intent classification
        budget: Optional TraversalBudget override
        include_siblings: Override policy's include_siblings setting
        config: Optional TraversalConfig for ruleset-specific settings
        
    Returns:
        TraversalResult with candidate chunk IDs
    """
    # 1. Classify intent
    intent = classify_intent(query, openai_client)
    
    # 2. Get policy for intent (from config if available)
    if config:
        policy = config.get_policy(intent)
    else:
        policy = get_policy(intent)
    
    # 3. Find anchor nodes (with config for priority terms)
    anchors = find_anchor_nodes(query, index, config=config)
    
    # Handle case where no anchors found
    if not anchors:
        return TraversalResult(
            candidate_ids=set(),
            anchors=set(),
            intent=intent,
            policy=policy,
            diagnostics={"no_anchors": True},
        )
    
    # 4. Create budget (use policy defaults if not provided)
    if budget is None:
        budget = TraversalBudget(
            max_nodes=policy.chunk_limit or 2000,
            max_depth=policy.max_depth,
        )
    
    # 5. Traverse graph
    candidates = traverse(index, anchors, policy, budget)
    
    # 6. Optionally expand with siblings
    should_include_siblings = (
        include_siblings if include_siblings is not None
        else policy.include_siblings
    )
    if should_include_siblings:
        candidates = expand_with_siblings(index, candidates)
    
    return TraversalResult(
        candidate_ids=candidates,
        anchors=anchors,
        intent=intent,
        policy=policy,
        diagnostics={
            "anchor_count": len(anchors),
            "candidate_count": len(candidates),
            "policy_max_depth": policy.max_depth,
            "policy_chunk_limit": policy.chunk_limit,
        },
    )


def retrieve_candidates_batch(
    queries: List[str],
    index: TraversalIndex,
    openai_client: Optional[OpenAI] = None,
) -> List[TraversalResult]:
    """
    Batch retrieval for multiple queries.
    
    Args:
        queries: List of query strings
        index: TraversalIndex
        openai_client: Optional OpenAI client
        
    Returns:
        List of TraversalResult, one per query
    """
    results = []
    for query in queries:
        result = retrieve_candidates(query, index, openai_client)
        results.append(result)
    return results


def retrieve_with_ranking_candidates(
    query: str,
    index: TraversalIndex,
    top_k: int = 10,
    openai_client: Optional[OpenAI] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve candidates and return as list with chunk metadata.
    
    This is the interface for integration with ranking systems.
    Returns chunks sorted by some heuristic (term overlap for now).
    
    Args:
        query: The query string
        index: TraversalIndex
        top_k: Maximum number of candidates to return
        openai_client: Optional OpenAI client
        
    Returns:
        List of chunk dicts with metadata
    """
    result = retrieve_candidates(query, index, openai_client)
    
    if not result.candidate_ids:
        return []
    
    # Get chunks and score by term overlap
    from .index import tokenize_and_normalize
    query_terms = set(tokenize_and_normalize(query))
    
    scored_chunks = []
    for chunk_id in result.candidate_ids:
        chunk = index.chunk_by_id.get(chunk_id)
        if not chunk:
            continue
        
        # Simple scoring: count query term overlap
        chunk_terms = set(tokenize_and_normalize(chunk.get("text", "")))
        overlap = len(query_terms & chunk_terms)
        
        scored_chunks.append({
            "chunk_id": chunk_id,
            "chunk": chunk,
            "score": overlap,
            "is_anchor": chunk_id in result.anchors,
        })
    
    # Sort by score (descending)
    scored_chunks.sort(key=lambda x: -x["score"])
    
    return scored_chunks[:top_k]

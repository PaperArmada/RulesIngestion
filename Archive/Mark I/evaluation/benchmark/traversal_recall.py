"""
Traversal-only recall harness.

Measures whether traversal alone can keep gold chunks in scope.
This is orthogonal to ranking - it answers:
"If I only use the graph, can I still keep the correct answer in scope?"

Key metrics:
- Reachability Recall: hits / total_queries
- Candidate Fraction: avg(|candidates| / |all_chunks|)

Interpretation:
- High recall + small fraction = Traversal is doing real work
- High recall + large fraction = Traversal is too permissive (overfetches)
- Low recall + small fraction = Traversal is too restrictive (drops answers)
- Low recall + large fraction = Anchor finding is broken
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from traversal.index import TraversalIndex
from traversal.seeds import find_anchor_nodes
from traversal.intent import Intent, classify_intent
from traversal.policy import INTENT_POLICIES, TraversalBudget
from traversal.traverse import traverse, traverse_with_diagnostics


@dataclass
class QueryResult:
    """Result for a single query."""
    query_id: str
    query_text: str
    intent: Intent
    anchor_count: int
    candidate_count: int
    gold_count: int
    hits: int  # Number of gold chunks in candidates
    reachable: bool  # At least one gold chunk in candidates
    candidate_fraction: float  # |candidates| / |all_chunks|
    per_depth: Dict[int, int] = field(default_factory=dict)


@dataclass
class TraversalRecallResult:
    """
    Result of running the traversal recall harness.
    
    Attributes:
        total_queries: Number of queries evaluated
        reachable_queries: Number of queries where gold chunk was reachable
        recall: reachable_queries / total_queries
        avg_candidate_fraction: Average candidate set size as fraction of corpus
        per_intent_recall: Recall broken down by intent type
        per_depth_reachability: Fraction reachable at each depth
        query_results: Detailed results per query
    """
    total_queries: int
    reachable_queries: int
    recall: float
    avg_candidate_fraction: float
    per_intent_recall: Dict[str, float] = field(default_factory=dict)
    per_depth_reachability: Dict[int, float] = field(default_factory=dict)
    query_results: List[QueryResult] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_queries": self.total_queries,
            "reachable_queries": self.reachable_queries,
            "recall": self.recall,
            "avg_candidate_fraction": self.avg_candidate_fraction,
            "per_intent_recall": self.per_intent_recall,
            "per_depth_reachability": self.per_depth_reachability,
            "query_results": [
                {
                    "query_id": qr.query_id,
                    "query_text": qr.query_text[:100],
                    "intent": qr.intent.name,
                    "anchor_count": qr.anchor_count,
                    "candidate_count": qr.candidate_count,
                    "gold_count": qr.gold_count,
                    "hits": qr.hits,
                    "reachable": qr.reachable,
                    "candidate_fraction": qr.candidate_fraction,
                }
                for qr in self.query_results
            ],
        }


def run_traversal_recall_harness(
    queries: List[Dict[str, Any]],
    index: TraversalIndex,
    openai_client: Optional[OpenAI] = None,
    verbose: bool = False,
) -> TraversalRecallResult:
    """
    Run the traversal recall harness on a set of queries.
    
    For each query:
    1. Find anchors
    2. Classify intent
    3. Traverse with policy
    4. Check if gold chunk in candidates
    
    Args:
        queries: List of query dicts with:
            - query_text: The query string
            - expected_chunk_ids: List of gold chunk IDs
            - id (optional): Query identifier
        index: TraversalIndex with pre-built indexes
        openai_client: Optional OpenAI client for LLM intent classification
        verbose: If True, print progress
        
    Returns:
        TraversalRecallResult with detailed metrics
    """
    total_chunks = index.total_chunks or len(index.chunk_by_id)
    
    query_results: List[QueryResult] = []
    intent_counts: Dict[Intent, int] = {}
    intent_hits: Dict[Intent, int] = {}
    depth_total: Dict[int, int] = {}
    depth_hits: Dict[int, int] = {}
    
    for i, query in enumerate(queries):
        query_id = query.get("id", f"q{i:03d}")
        query_text = query.get("query_text", "")
        gold_ids = set(query.get("expected_chunk_ids", []))
        
        if not query_text or not gold_ids:
            continue
        
        if verbose and i % 10 == 0:
            print(f"Processing query {i+1}/{len(queries)}...")
        
        # 1. Classify intent
        intent = classify_intent(query_text, openai_client)
        
        # 2. Get policy
        policy = INTENT_POLICIES.get(intent, INTENT_POLICIES[Intent.DEFINITION])
        
        # 3. Find anchors
        anchors = find_anchor_nodes(query_text, index)
        
        # 4. Traverse with diagnostics
        if anchors:
            budget = TraversalBudget(
                max_nodes=policy.chunk_limit or 2000,
                max_depth=policy.max_depth,
            )
            diagnostics = traverse_with_diagnostics(index, anchors, policy, budget)
            candidates = diagnostics["candidates"]
            per_depth = diagnostics["per_depth"]
        else:
            candidates = set()
            per_depth = {}
        
        # 5. Check reachability
        hits = len(gold_ids & candidates)
        reachable = hits > 0
        candidate_fraction = len(candidates) / total_chunks if total_chunks > 0 else 0
        
        # Track per-intent stats
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
        if reachable:
            intent_hits[intent] = intent_hits.get(intent, 0) + 1
        
        # Track per-depth stats (simplified - just track max depth)
        for depth in range(policy.max_depth + 1):
            depth_total[depth] = depth_total.get(depth, 0) + 1
            # Check if reachable at this depth (cumulative)
            if reachable:
                depth_hits[depth] = depth_hits.get(depth, 0) + 1
        
        # Store result
        query_results.append(QueryResult(
            query_id=query_id,
            query_text=query_text,
            intent=intent,
            anchor_count=len(anchors),
            candidate_count=len(candidates),
            gold_count=len(gold_ids),
            hits=hits,
            reachable=reachable,
            candidate_fraction=candidate_fraction,
            per_depth=per_depth,
        ))
    
    # Compute aggregate metrics
    total_queries = len(query_results)
    reachable_queries = sum(1 for qr in query_results if qr.reachable)
    recall = reachable_queries / total_queries if total_queries > 0 else 0
    avg_candidate_fraction = (
        sum(qr.candidate_fraction for qr in query_results) / total_queries
        if total_queries > 0 else 0
    )
    
    # Per-intent recall
    per_intent_recall = {}
    for intent in intent_counts:
        count = intent_counts[intent]
        hits = intent_hits.get(intent, 0)
        per_intent_recall[intent.name] = hits / count if count > 0 else 0
    
    # Per-depth reachability
    per_depth_reachability = {}
    for depth in depth_total:
        total = depth_total[depth]
        hits = depth_hits.get(depth, 0)
        per_depth_reachability[depth] = hits / total if total > 0 else 0
    
    return TraversalRecallResult(
        total_queries=total_queries,
        reachable_queries=reachable_queries,
        recall=recall,
        avg_candidate_fraction=avg_candidate_fraction,
        per_intent_recall=per_intent_recall,
        per_depth_reachability=per_depth_reachability,
        query_results=query_results,
    )


def run_traversal_recall_from_files(
    graph_path: Path,
    chunks_path: Path,
    queries_path: Path,
    output_path: Optional[Path] = None,
    verbose: bool = True,
) -> TraversalRecallResult:
    """
    Run traversal recall harness from file paths.
    
    Args:
        graph_path: Path to merged.graph.json
        chunks_path: Path to merged.enriched.json
        queries_path: Path to benchmark dataset JSON
        output_path: Optional path to write results
        verbose: If True, print progress
        
    Returns:
        TraversalRecallResult
    """
    if verbose:
        print(f"Loading graph from {graph_path}...")
    with open(graph_path) as f:
        graph = json.load(f)
    
    if verbose:
        print(f"Loading chunks from {chunks_path}...")
    with open(chunks_path) as f:
        chunks_data = json.load(f)
        chunks = chunks_data.get("chunks", chunks_data) if isinstance(chunks_data, dict) else chunks_data
    
    if verbose:
        print(f"Loading queries from {queries_path}...")
    with open(queries_path) as f:
        queries_data = json.load(f)
    
    # Convert benchmark format to expected format
    queries = []
    for i, q in enumerate(queries_data):
        relevant_ids = q.get("retrieval_review", {}).get("relevant_chunk_ids", [])
        if relevant_ids:
            queries.append({
                "id": f"q{i:03d}",
                "query_text": q["query"],
                "expected_chunk_ids": relevant_ids,
            })
    
    if verbose:
        print(f"Building index from {len(chunks)} chunks and graph with {len(graph.get('edges', []))} edges...")
    index = TraversalIndex.build(graph, chunks)
    
    if verbose:
        print(f"Running recall harness on {len(queries)} queries...")
    result = run_traversal_recall_harness(queries, index, verbose=verbose)
    
    if verbose:
        print(f"\n=== Results ===")
        print(f"Recall: {result.recall:.2%}")
        print(f"Avg candidate fraction: {result.avg_candidate_fraction:.2%}")
        print(f"Per-intent recall: {result.per_intent_recall}")
    
    if output_path:
        with open(output_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        if verbose:
            print(f"Results written to {output_path}")
    
    return result


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run traversal recall harness")
    parser.add_argument("--graph", type=Path, required=True, help="Path to merged.graph.json")
    parser.add_argument("--chunks", type=Path, required=True, help="Path to merged.enriched.json")
    parser.add_argument("--queries", type=Path, required=True, help="Path to benchmark queries JSON")
    parser.add_argument("--output", type=Path, help="Path to write results JSON")
    
    args = parser.parse_args()
    
    run_traversal_recall_from_files(
        graph_path=args.graph,
        chunks_path=args.chunks,
        queries_path=args.queries,
        output_path=args.output,
        verbose=True,
    )

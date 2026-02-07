#!/usr/bin/env python3
"""
Run blind evaluation on a batch.

Usage:
    uv run python blind_eval/run_eval.py --batch 001
    uv run python blind_eval/run_eval.py --batch 001 --verbose
    uv run python blind_eval/run_eval.py --all
"""

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from traversal import TraversalIndex, retrieve_candidates, TraversalConfig, build_config


@dataclass
class EvalResult:
    """Result for a single query."""
    query_id: str
    question: str
    gold_chunk_ids: list[str]
    retrieved_chunk_ids: set[str]
    hit: bool
    matched_gold_ids: list[str]
    anchor_count: int
    candidate_count: int
    intent: str
    notes: str = ""


@dataclass
class BatchResult:
    """Result for an entire batch."""
    batch_id: str
    total_queries: int
    hits: int
    recall: float
    avg_candidate_count: float
    per_query: list[EvalResult]
    failures: list[EvalResult]
    run_at: str


def load_batch(batch_path: Path) -> dict[str, Any]:
    """Load a batch JSON file."""
    with open(batch_path) as f:
        return json.load(f)


def load_index_and_config(
    graph_path: Path,
    enriched_path: Path,
    config_path: Path | None = None,
) -> tuple[TraversalIndex, TraversalConfig | None]:
    """Load traversal index and optional config."""
    with open(graph_path) as f:
        graph = json.load(f)
    
    with open(enriched_path) as f:
        chunks_data = json.load(f)
    
    # Handle list or dict format
    if isinstance(chunks_data, list):
        chunks = chunks_data
    else:
        chunks = chunks_data.get("chunks", [])
    
    index = TraversalIndex.build(graph, chunks)
    
    config = None
    if config_path and config_path.exists():
        config = TraversalConfig.load(config_path)
    else:
        # Build config from chunks
        config = build_config(chunks, ruleset_id="StarFinder2e")
    
    return index, config


def run_eval_query(
    query: dict[str, Any],
    index: TraversalIndex,
    config: TraversalConfig | None = None,
) -> EvalResult:
    """Run evaluation on a single query."""
    question = query["question"]
    gold_ids = query.get("gold_chunk_ids", [])
    
    # Run traversal
    result = retrieve_candidates(question, index, config=config)
    
    # Check if any gold chunk was retrieved
    retrieved = result.candidate_ids
    matched = [gid for gid in gold_ids if gid in retrieved]
    hit = len(matched) > 0
    
    return EvalResult(
        query_id=query["id"],
        question=question,
        gold_chunk_ids=gold_ids,
        retrieved_chunk_ids=retrieved,
        hit=hit,
        matched_gold_ids=matched,
        anchor_count=len(result.anchors),
        candidate_count=len(result.candidate_ids),
        intent=result.intent.name,
        notes=query.get("notes", ""),
    )


def run_batch_eval(
    batch: dict[str, Any],
    index: TraversalIndex,
    config: TraversalConfig | None = None,
    verbose: bool = False,
) -> BatchResult:
    """Run evaluation on an entire batch."""
    batch_id = batch["metadata"]["batch_id"]
    queries = batch["queries"]
    
    if not queries:
        return BatchResult(
            batch_id=batch_id,
            total_queries=0,
            hits=0,
            recall=0.0,
            avg_candidate_count=0.0,
            per_query=[],
            failures=[],
            run_at=datetime.now().isoformat(),
        )
    
    results = []
    failures = []
    total_candidates = 0
    
    for query in queries:
        result = run_eval_query(query, index, config)
        results.append(result)
        total_candidates += result.candidate_count
        
        if verbose:
            status = "✅" if result.hit else "❌"
            print(f"{status} {result.query_id}: {result.question[:50]}...")
            print(f"   Intent: {result.intent} | Anchors: {result.anchor_count} | Candidates: {result.candidate_count}")
        
        if not result.hit:
            failures.append(result)
    
    hits = sum(1 for r in results if r.hit)
    recall = hits / len(queries) if queries else 0.0
    avg_candidates = total_candidates / len(queries) if queries else 0.0
    
    return BatchResult(
        batch_id=batch_id,
        total_queries=len(queries),
        hits=hits,
        recall=recall,
        avg_candidate_count=avg_candidates,
        per_query=results,
        failures=failures,
        run_at=datetime.now().isoformat(),
    )


def print_report(result: BatchResult, verbose: bool = False):
    """Print evaluation report."""
    print(f"\n{'='*60}")
    print(f"BLIND EVAL REPORT: Batch {result.batch_id}")
    print(f"{'='*60}")
    print(f"Run at: {result.run_at}")
    print(f"\nResults:")
    print(f"  Total queries: {result.total_queries}")
    print(f"  Hits: {result.hits}")
    print(f"  Recall: {result.recall:.2%}")
    print(f"  Avg candidates: {result.avg_candidate_count:.1f}")
    
    if result.failures:
        print(f"\n{'='*60}")
        print(f"FAILURES ({len(result.failures)}):")
        print(f"{'='*60}")
        for f in result.failures:
            print(f"\n❌ {f.query_id}")
            print(f"   Question: {f.question}")
            print(f"   Gold IDs: {f.gold_chunk_ids}")
            print(f"   Intent: {f.intent}")
            print(f"   Anchors: {f.anchor_count} | Candidates: {f.candidate_count}")
            if f.notes:
                print(f"   Notes: {f.notes}")
    else:
        print(f"\n✅ All queries passed!")


def save_results(result: BatchResult, output_path: Path):
    """Save results to JSON file."""
    output = {
        "batch_id": result.batch_id,
        "run_at": result.run_at,
        "total_queries": result.total_queries,
        "hits": result.hits,
        "recall": result.recall,
        "avg_candidate_count": result.avg_candidate_count,
        "failures": [
            {
                "query_id": f.query_id,
                "question": f.question,
                "gold_chunk_ids": f.gold_chunk_ids,
                "intent": f.intent,
                "anchor_count": f.anchor_count,
                "candidate_count": f.candidate_count,
                "notes": f.notes,
            }
            for f in result.failures
        ],
    }
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\nResults saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Run blind evaluation")
    parser.add_argument("--batch", type=str, help="Batch ID to run (e.g., 001)")
    parser.add_argument("--all", action="store_true", help="Run all batches")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument(
        "--graph",
        type=Path,
        default=Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.graph.json"),
        help="Path to graph JSON",
    )
    parser.add_argument(
        "--enriched",
        type=Path,
        default=Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.enriched.json"),
        help="Path to enriched chunks JSON",
    )
    
    args = parser.parse_args()
    
    if not args.batch and not args.all:
        parser.error("Must specify --batch or --all")
    
    # Find batches
    batch_dir = Path(__file__).parent / "batches"
    if args.all:
        batch_files = sorted(batch_dir.glob("batch_*.json"))
    else:
        batch_files = [batch_dir / f"batch_{args.batch}.json"]
    
    if not batch_files:
        print("No batch files found")
        return
    
    # Check if graph/enriched exist
    if not args.graph.exists():
        print(f"Error: Graph file not found: {args.graph}")
        return
    if not args.enriched.exists():
        print(f"Error: Enriched file not found: {args.enriched}")
        return
    
    # Load index once
    print(f"Loading index from: {args.graph}")
    index, config = load_index_and_config(args.graph, args.enriched)
    print(f"Index loaded: {index.total_chunks} chunks, {index.total_edges} edges")
    
    # Run each batch
    for batch_file in batch_files:
        if not batch_file.exists():
            print(f"Batch file not found: {batch_file}")
            continue
        
        batch = load_batch(batch_file)
        
        if not batch["queries"]:
            print(f"\nSkipping {batch_file.name} (no queries)")
            continue
        
        print(f"\nRunning batch: {batch_file.name}")
        result = run_batch_eval(batch, index, config, args.verbose)
        
        print_report(result, args.verbose)
        
        # Save results
        results_dir = Path(__file__).parent / "results"
        results_path = results_dir / f"batch_{result.batch_id}_results.json"
        save_results(result, results_path)


if __name__ == "__main__":
    main()

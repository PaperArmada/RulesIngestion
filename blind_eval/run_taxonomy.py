#!/usr/bin/env python3
"""
Run failure taxonomy on all blind eval batches.

Labels each gold miss with exactly one of A–E and writes a distribution report.
See Docs/PLAN-Failure-Taxonomy-And-Constraints.md.

Usage:
    uv run python blind_eval/run_taxonomy.py
    uv run python blind_eval/run_taxonomy.py --graph path/to/graph.json --enriched path/to/enriched.json
    uv run python blind_eval/run_taxonomy.py --write-back   # write failure_class/signals to results copies
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# Repo root on path for traversal imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from traversal import TraversalIndex, TraversalConfig, build_config

from blind_eval.taxonomy import (
    FailureSignals,
    compute_signals,
    assign_failure_class,
    DEFAULT_TOP_K,
)


def load_index_and_config(
    graph_path: Path,
    enriched_path: Path,
) -> tuple[TraversalIndex, TraversalConfig]:
    """Load traversal index and config from graph + enriched chunks."""
    with open(graph_path) as f:
        graph = json.load(f)
    with open(enriched_path) as f:
        chunks_data = json.load(f)
    chunks = chunks_data if isinstance(chunks_data, list) else chunks_data.get("chunks", [])
    index = TraversalIndex.build(graph, chunks)
    config = build_config(chunks, ruleset_id="StarFinder2e")
    return index, config


def load_all_batches(batches_dir: Path) -> List[Dict[str, Any]]:
    """Load all batch JSON files that have queries."""
    batches = []
    for batch_file in sorted(batches_dir.glob("batch_*.json")):
        with open(batch_file) as f:
            batch = json.load(f)
        if batch.get("queries"):
            batches.append(batch)
    return batches


def run_taxonomy(
    index: TraversalIndex,
    config: TraversalConfig,
    batches: List[Dict[str, Any]],
    *,
    top_k: int = DEFAULT_TOP_K,
) -> Dict[str, Any]:
    """
    Run taxonomy on all queries in batches.

    Returns a dict with:
      - distribution: { "hit": N, "A": N, "B": N, "C": N, "D": N, "E": N }
      - per_query: list of { query_id, batch_id, question, failure_class, failure_signals, hit }
      - total_queries, hits, recall
    """
    distribution: Dict[str, int] = {"hit": 0, "A": 0, "B": 0, "C": 0, "D": 0, "E": 0}
    per_query: List[Dict[str, Any]] = []

    for batch in batches:
        batch_id = batch["metadata"].get("batch_id", "?")
        metadata = batch["metadata"]
        reasoning_mode = metadata.get("reasoning_mode") or (
            "conceptual" if batch_id == "006" else None
        )

        for query in batch["queries"]:
            query_id = query.get("id", "")
            question = query.get("question", "")
            gold_ids = query.get("gold_chunk_ids") or []

            if not gold_ids:
                continue

            signals = compute_signals(
                question,
                gold_ids,
                index,
                config,
                top_k=top_k,
                batch_reasoning_mode=reasoning_mode,
            )
            failure_class = assign_failure_class(signals, metadata, top_k=top_k)

            if failure_class is None:
                distribution["hit"] += 1
                hit = True
            else:
                distribution[failure_class] += 1
                hit = False

            per_query.append({
                "query_id": query_id,
                "batch_id": batch_id,
                "question": question[:80],
                "failure_class": failure_class,
                "failure_signals": signals.to_dict(),
                "hit": hit,
            })

    total = len(per_query)
    hits = distribution["hit"]
    recall = hits / total if total else 0.0

    return {
        "distribution": distribution,
        "per_query": per_query,
        "total_queries": total,
        "hits": hits,
        "recall": recall,
    }


def print_distribution_report(data: Dict[str, Any]) -> None:
    """Print distribution table to console."""
    dist = data["distribution"]
    total = data["total_queries"]
    recall = data["recall"]

    print("\n" + "=" * 60)
    print("FAILURE TAXONOMY — Distribution Report")
    print("=" * 60)
    print(f"Total queries: {total}")
    print(f"Hits:          {data['hits']}  (recall {recall:.2%})")
    print("-" * 60)
    print("Failure class  Count   %")
    print("-" * 60)
    for key in ["hit", "A", "B", "C", "D", "E"]:
        count = dist.get(key, 0)
        pct = (count / total * 100) if total else 0
        label = "hit" if key == "hit" else f"  {key}"
        print(f"  {label:6}     {count:4}   {pct:5.1f}%")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run failure taxonomy on blind eval batches (label each miss A–E)"
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.graph.json"),
        help="Path to merged graph JSON",
    )
    parser.add_argument(
        "--enriched",
        type=Path,
        default=Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.enriched.json"),
        help="Path to merged enriched chunks JSON",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help="Rank threshold for dominance (gold beyond this = C)",
    )
    parser.add_argument(
        "--write-back",
        action="store_true",
        help="Write failure_class and failure_signals to results/ (per-query JSON)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path for taxonomy results JSON (default: blind_eval/results/taxonomy_results.json)",
    )
    args = parser.parse_args()

    blind_eval_dir = Path(__file__).resolve().parent
    batches_dir = blind_eval_dir / "batches"
    results_dir = blind_eval_dir / "results"

    if not args.graph.exists():
        print(f"Error: Graph not found: {args.graph}")
        sys.exit(1)
    if not args.enriched.exists():
        print(f"Error: Enriched not found: {args.enriched}")
        sys.exit(1)

    batches = load_all_batches(batches_dir)
    if not batches:
        print("No batches with queries found in", batches_dir)
        sys.exit(0)

    print("Loading index...")
    index, config = load_index_and_config(args.graph, args.enriched)
    print(f"Index: {index.total_chunks} chunks, {index.total_edges} edges")
    print(f"Batches: {len(batches)}")

    data = run_taxonomy(index, config, batches, top_k=args.top_k)
    print_distribution_report(data)

    out_path = args.out or results_dir / "taxonomy_results.json"
    results_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nResults written to: {out_path}")

    if args.write_back:
        # Write per-query results with failure_class and failure_signals for inspection
        write_back_path = results_dir / "taxonomy_per_query.json"
        with open(write_back_path, "w") as f:
            json.dump(data["per_query"], f, indent=2)
        print(f"Per-query write-back: {write_back_path}")


if __name__ == "__main__":
    main()

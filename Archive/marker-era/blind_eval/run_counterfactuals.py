#!/usr/bin/env python3
"""
Run counterfactual validation for failure classes A–E.

For each class, run the minimal counterfactual and report recall delta.
See Docs/PLAN-Failure-Taxonomy-And-Constraints.md Phase 2.

Usage:
    uv run python blind_eval/run_counterfactuals.py
    uv run python blind_eval/run_counterfactuals.py --classes A C
    uv run python blind_eval/run_counterfactuals.py --out blind_eval/results/counterfactual_results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Repo root on path for traversal imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from traversal import TraversalIndex, TraversalConfig, build_config

from blind_eval.counterfactual_harness import (
    run_all_counterfactuals,
    CounterfactualResult,
    DEFAULT_TOP_K,
)
from blind_eval.run_taxonomy import load_index_and_config, load_all_batches


def print_report(results: list[CounterfactualResult]) -> None:
    """Print counterfactual recall table to console."""
    print("\n" + "=" * 70)
    print("COUNTERFACTUAL VALIDATION — Recall deltas by failure class")
    print("=" * 70)
    print(f"{'Class':<6} {'Baseline':>10} {'Counterfactual':>14} {'Delta':>8}  Affected")
    print("-" * 70)
    for r in results:
        affected = len(r.queries_affected)
        print(f"  {r.class_tested:<4} {r.baseline_recall:>9.2%} {r.counterfactual_recall:>13.2%} {r.delta:>+7.2%}  {affected}")
    print("=" * 70)
    if results:
        best = max(results, key=lambda x: x.delta)
        print(f"Largest delta: class {best.class_tested} ({best.delta:+.2%})")
        if best.queries_affected:
            print(f"  Queries that flipped miss→hit: {best.queries_affected[:10]}{'...' if len(best.queries_affected) > 10 else ''}")


# Rules folder is at DungeonOverMind/Rules (sibling of RulesIngestion)
_RULES_ROOT = Path(__file__).resolve().parents[5] / "Rules"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run counterfactual validation (Phase 2) for failure classes A–E"
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=_RULES_ROOT / "StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.graph.json",
        help="Path to merged graph JSON",
    )
    parser.add_argument(
        "--enriched",
        type=Path,
        default=_RULES_ROOT / "StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.enriched.json",
        help="Path to merged enriched chunks JSON",
    )
    parser.add_argument(
        "--batches",
        type=Path,
        default=None,
        help="Path to batches directory (default: blind_eval/batches)",
    )
    parser.add_argument(
        "--classes",
        type=str,
        default=None,
        help="Comma-separated classes to run (default: A,B,C,D,E)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help="Top-k for C/D counterfactuals (authority ranking)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path for results JSON (default: blind_eval/results/counterfactual_results.json)",
    )
    args = parser.parse_args()

    blind_eval_dir = Path(__file__).resolve().parent
    batches_dir = args.batches or blind_eval_dir / "batches"
    results_dir = blind_eval_dir / "results"

    if not args.graph.exists():
        print(f"Error: Graph not found: {args.graph}", file=sys.stderr)
        sys.exit(1)
    if not args.enriched.exists():
        print(f"Error: Enriched not found: {args.enriched}", file=sys.stderr)
        sys.exit(1)

    batches = load_all_batches(batches_dir)
    if not batches:
        print("No batches with queries found in", batches_dir, file=sys.stderr)
        sys.exit(0)

    print("Loading index...")
    index, config = load_index_and_config(args.graph, args.enriched)
    print(f"Index: {index.total_chunks} chunks")
    print(f"Batches: {len(batches)}")

    classes = [c.strip() for c in args.classes.split(",")] if args.classes else None
    results = run_all_counterfactuals(
        batches, index, config, top_k=args.top_k, classes=classes,
    )

    print_report(results)

    out_path = args.out or results_dir / "counterfactual_results.json"
    results_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump([r.to_dict() for r in results], f, indent=2)
    print(f"\nResults written to: {out_path}")


if __name__ == "__main__":
    main()

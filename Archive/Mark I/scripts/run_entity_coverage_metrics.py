#!/usr/bin/env python3
"""
Run entity coverage metrics on a pipeline run (merged.enriched.json + merged.graph.json).

Usage:
  uv run python scripts/run_entity_coverage_metrics.py --run-dir Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02
  uv run python scripts/run_entity_coverage_metrics.py --run-dir path/to/run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Run from repo root so imports resolve
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from enrichment.chunks import EnrichedChunk
from evaluation.metrics import compute_entity_coverage_metrics


def load_chunks(enriched_path: Path) -> list[EnrichedChunk]:
    with open(enriched_path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "chunks" in data:
        data = data["chunks"]
    if not isinstance(data, list):
        raise ValueError(f"Expected list of chunks or dict with 'chunks', got {type(data)}")
    chunks = []
    for item in data:
        if isinstance(item, dict):
            chunks.append(EnrichedChunk(**{k: v for k, v in item.items() if k in EnrichedChunk.__dataclass_fields__}))
        else:
            chunks.append(item)
    return chunks


def load_graph(graph_path: Path) -> dict:
    with open(graph_path, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute entity coverage metrics for a run")
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Run directory containing enriched/merged.enriched.json and enriched/merged.graph.json",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON only",
    )
    args = parser.parse_args()
    run_dir = args.run_dir if args.run_dir.is_absolute() else REPO_ROOT / args.run_dir
    enriched_dir = run_dir / "enriched"
    enriched_path = enriched_dir / "merged.enriched.json"
    graph_path = enriched_dir / "merged.graph.json"

    if not enriched_path.exists():
        print(f"Error: {enriched_path} not found", file=sys.stderr)
        return 1
    if not graph_path.exists():
        print(f"Error: {graph_path} not found", file=sys.stderr)
        return 1

    chunks = load_chunks(enriched_path)
    graph = load_graph(graph_path)
    metrics = compute_entity_coverage_metrics(chunks, graph)

    if args.json:
        print(json.dumps(metrics, indent=2))
        return 0

    print(f"Run dir: {run_dir}")
    print()
    print("Entity coverage metrics")
    print("-" * 40)
    print(f"  total_chunks:                  {metrics['total_chunks']}")
    print(f"  rule_bearing_chunks:          {metrics['rule_bearing_chunks']}")
    print(f"  chunks_with_entities:         {metrics['chunks_with_entities']}")
    print(f"  rule_bearing_with_entities:   {metrics['rule_bearing_with_entities']}")
    print(f"  chunk_entity_coverage:        {metrics['chunk_entity_coverage']:.2%}")
    print(f"  rule_bearing_entity_coverage: {metrics['rule_bearing_entity_coverage']:.2%}")
    print(f"  chunks_without_entities:     {metrics['chunks_without_entities']}")
    print(f"  rule_bearing_without_entities:{metrics['rule_bearing_without_entities']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

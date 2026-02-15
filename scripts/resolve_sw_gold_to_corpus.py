#!/usr/bin/env python3
"""
Re-resolve S&W benchmark gold_unit_ids to the current fold+merge corpus.

Loads the same pipeline as run_experiment (load → fold(min_chars) → merge),
builds a mapping from original stageB unit IDs to merged chunk IDs, then for
each benchmark query replaces gold_unit_ids / required_gold / supporting_gold
with the merged chunk IDs that contain the same content (via gold_locations
source_unit_ids or page+structural_path fallback). Repopulates gold_locations
from the new corpus.

Usage (from RulesIngestion):
  uv run python scripts/resolve_sw_gold_to_corpus.py
  uv run python scripts/resolve_sw_gold_to_corpus.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# Run from repo root (RulesIngestion)
REPO_ROOT = Path(__file__).resolve().parents[1]
import sys
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from retrieval_lab.config import ExperimentConfig
from retrieval_lab.gold_grounding import resolve_gold_locations_to_current_corpus
from retrieval_lab.substrate_loader import (
    fold_under_threshold_into_adjacent,
    load_evidence_units,
    merge_units_by_heading,
)


def main() -> None:
    ap = argparse.ArgumentParser(description="Re-resolve S&W benchmark gold to fold+merge corpus")
    ap.add_argument("--dry-run", action="store_true", help="Print changes but do not write benchmark")
    ap.add_argument("--config", default="retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml", help="Experiment config path")
    args = ap.parse_args()

    cwd = REPO_ROOT
    config_path = cwd / args.config
    config = ExperimentConfig.from_yaml(config_path)
    config.resolve_paths(cwd)

    # Build corpus same as run_experiment
    corpus = load_evidence_units(config.substrate_path, config.document_id)
    min_chars = getattr(config, "min_chars", None)
    if min_chars is not None:
        folded = fold_under_threshold_into_adjacent(corpus, min_chars)
    else:
        folded = corpus
        for u in folded:
            u.setdefault("source_unit_ids", [u.get("id", "")])
    if getattr(config, "merge_chunks", False):
        merged = merge_units_by_heading(
            folded,
            max_chars=getattr(config, "merge_max_chars", 2000),
        )
    else:
        merged = folded

    print(f"Corpus: {len(corpus)} raw → {len(folded)} folded → {len(merged)} merged")

    benchmark_path = cwd / "evals/retrieval/SwordsandWizardy/swords_wizardry_benchmark.json"
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))

    resolved_benchmark, summary = resolve_gold_locations_to_current_corpus(
        benchmark,
        folded_corpus=folded,
        merged_corpus=merged,
    )
    updated = 0
    for before, after in zip(benchmark, resolved_benchmark):
        if (
            before.get("gold_unit_ids") != after.get("gold_unit_ids")
            or before.get("required_gold") != after.get("required_gold")
            or before.get("supporting_gold") != after.get("supporting_gold")
            or before.get("gold_locations") != after.get("gold_locations")
            or before.get("required_gold_rationale") != after.get("required_gold_rationale")
        ):
            updated += 1
            print(f"  {after.get('id', '')}: updated")
        after.pop("_gold_note", None)

    print(
        "Resolution summary: "
        f"with_locations={summary['queries_with_gold_locations']} "
        f"resolved_nonempty={summary['queries_resolved_nonempty']} "
        f"resolved_empty={summary['queries_resolved_empty']} "
        f"legacy_only={summary['queries_legacy_only']}"
    )
    print(f"Updated {updated} queries")

    if not args.dry_run and updated:
        benchmark_path.write_text(json.dumps(resolved_benchmark, indent=2), encoding="utf-8")
        print(f"Wrote {benchmark_path}")
    elif args.dry_run:
        print("(dry-run: no file written)")


if __name__ == "__main__":
    main()

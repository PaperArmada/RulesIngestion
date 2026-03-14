#!/usr/bin/env python3
"""
Promote a retrieval experiment run into a canonical per-book "best outputs" location.

Usage (from RulesIngestion root):
  uv run python scripts/promote_best_retrieval_run.py \
    --book-dir out/StarFinderPlayerCore \
    --run-dir out/retrieval_lab/experiments/starfinder_player_core_50q_post_full_gold_curation_20260228_184410 \
    --label starfinder-50q-best-current \
    --notes "Best corpus-level 50q run after full gold curation."
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ARTIFACT_CANDIDATES = [
    "metrics.json",
    "run_manifest.json",
    "manifest.json",
    "experiment.json",
    "REPORT.md",
    "per_query.json",
    "failure_buckets.json",
    "grounding_audit.json",
    "forensics_bundles.json",
    "gold_retrievability_heatmap.json",
    "benchmark_lint.json",
    "chunk_quality_gate.json",
]


def _copy_if_exists(src_dir: Path, dst_dir: Path, filename: str) -> bool:
    src = src_dir / filename
    if not src.exists():
        return False
    dst = dst_dir / filename
    shutil.copy2(src, dst)
    return True


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy a selected retrieval run to canonical out/<book>/retrieval_best."
    )
    parser.add_argument(
        "--book-dir",
        type=Path,
        required=True,
        help="Book output dir (for example out/StarFinderPlayerCore or out/Swords&Wizardry).",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Experiment run dir under out/retrieval_lab/experiments/<run_id>.",
    )
    parser.add_argument(
        "--label",
        type=str,
        default="best-current",
        help="Human-readable label for this promotion record.",
    )
    parser.add_argument(
        "--notes",
        type=str,
        default="",
        help="Optional rationale/notes for why this run is promoted.",
    )
    args = parser.parse_args()

    book_dir = args.book_dir.resolve()
    run_dir = args.run_dir.resolve()
    if not book_dir.exists() or not book_dir.is_dir():
        raise SystemExit(f"--book-dir does not exist or is not a directory: {book_dir}")
    if not run_dir.exists() or not run_dir.is_dir():
        raise SystemExit(f"--run-dir does not exist or is not a directory: {run_dir}")

    promoted_root = book_dir / "retrieval_best"
    current_dir = promoted_root / "current"
    history_dir = promoted_root / "history"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    snapshot_dir = history_dir / f"{ts}_{run_dir.name}"

    current_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    copied_files: list[str] = []
    for filename in ARTIFACT_CANDIDATES:
        copied = _copy_if_exists(run_dir, current_dir, filename)
        if copied:
            _copy_if_exists(run_dir, snapshot_dir, filename)
            copied_files.append(filename)

    # Preserve exact command context when available
    source_manifest = None
    if (run_dir / "run_manifest.json").exists():
        source_manifest = "run_manifest.json"
    elif (run_dir / "manifest.json").exists():
        source_manifest = "manifest.json"

    metadata = {
        "version": "retrieval_best_promotion_v1",
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "book_dir": str(book_dir),
        "source_run_dir": str(run_dir),
        "label": args.label,
        "notes": args.notes,
        "copied_files": copied_files,
        "source_manifest": source_manifest,
        "canonical_current_dir": str(current_dir),
        "history_snapshot_dir": str(snapshot_dir),
    }

    _write_json(current_dir / "selection.json", metadata)
    _write_json(snapshot_dir / "selection.json", metadata)

    print("Promotion complete")
    print(f"Book dir: {book_dir}")
    print(f"Source run: {run_dir}")
    print(f"Current best dir: {current_dir}")
    print(f"History snapshot: {snapshot_dir}")
    print(f"Copied files ({len(copied_files)}): {', '.join(copied_files) if copied_files else '(none)'}")


if __name__ == "__main__":
    main()


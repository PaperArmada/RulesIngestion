#!/usr/bin/env python3
"""
Identify chapters with orphan gate failures from Mark III evaluation reports
and run orphan remediation (LLM header assignment + gate rerun) on those only.

No full re-extraction: loads existing stageA + stageB, runs rerun_gates.py
per chapter so orphans get headings and Stage B gates are re-evaluated.

Usage (from RulesIngestion root):
  uv run python scripts/remediate_orphans_from_reports.py [PARENT_DIR]

  PARENT_DIR defaults to: out/mark3_evaluation/StarFinderPlayerCore

  Requires OPENAI_API_KEY for LLM orphan header assignment.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remediate orphan-failed pages: find chapters from evaluation reports, run rerun_gates per chapter."
    )
    parser.add_argument(
        "parent_dir",
        nargs="?",
        type=Path,
        default=REPO_ROOT / "out" / "mark3_evaluation" / "StarFinderPlayerCore",
        help="Parent dir containing one subdir per chapter, each with evaluation_report.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only list chapters and orphan-failed pages; do not run rerun_gates.",
    )
    args = parser.parse_args()
    parent = args.parent_dir if args.parent_dir.is_absolute() else REPO_ROOT / args.parent_dir

    if not parent.exists():
        print(f"Parent dir not found: {parent}", file=sys.stderr)
        sys.exit(1)

    # Collect chapters that have at least one orphan-failed page
    chapters_to_remediate: list[tuple[Path, list[str]]] = []
    for chapter_dir in sorted(parent.iterdir()):
        if not chapter_dir.is_dir():
            continue
        report_path = chapter_dir / "evaluation_report.json"
        if not report_path.exists():
            continue
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Skip {chapter_dir.name}: failed to load report ({e})", file=sys.stderr)
            continue
        failed = (report.get("stage_b_failed_pages") or {}).get("orphan") or []
        if failed:
            chapters_to_remediate.append((chapter_dir, failed))

    if not chapters_to_remediate:
        print("No chapters with orphan-failed pages found.")
        return

    print(f"Chapters with orphan failures: {len(chapters_to_remediate)}")
    for chapter_dir, labels in chapters_to_remediate:
        print(f"  {chapter_dir.name}: {len(labels)} pages — {labels[:5]}{'...' if len(labels) > 5 else ''}")
    print()

    if args.dry_run:
        print("Dry-run: not invoking rerun_gates.")
        return

    rerun_script = REPO_ROOT / "scripts" / "rerun_gates.py"
    for chapter_dir, labels in chapters_to_remediate:
        print(f"=== Remediating {chapter_dir.name} ({len(labels)} orphan pages) ===")
        rc = subprocess.run(
            [sys.executable, str(rerun_script), str(chapter_dir)],
            cwd=str(REPO_ROOT),
        )
        if rc.returncode != 0:
            print(f"Warning: rerun_gates exited {rc.returncode} for {chapter_dir.name}", file=sys.stderr)
    print("Done.")


if __name__ == "__main__":
    main()

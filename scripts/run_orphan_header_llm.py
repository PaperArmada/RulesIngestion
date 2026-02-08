#!/usr/bin/env python3
"""
Orphan header one-shot LLM — call OpenAI gpt-5-nano with the orphan header prompt
for each orphan page in a mark3 evaluation dir.

Usage (from RulesIngestion root):
  uv run python scripts/run_orphan_header_llm.py [EVAL_DIR]

  EVAL_DIR defaults to: out/mark3_evaluation/DnD5eBrutalChapters

Requires OPENAI_API_KEY in environment (or .env.development in repo root).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from extraction.orphan_header import discover_orphans, run_orphan_header_pass


def _load_env_development() -> None:
    """Load .env.development from repo root if present."""
    env_path = REPO_ROOT.parent / ".env.development"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value


DEFAULT_EVAL_DIR = REPO_ROOT / "out" / "mark3_evaluation" / "DnD5eBrutalChapters"


def main() -> None:
    _load_env_development()
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Run orphan header LLM on mark3 evaluation pages")
    parser.add_argument(
        "eval_dir",
        nargs="?",
        type=Path,
        default=DEFAULT_EVAL_DIR,
        help=f"Evaluation dir (default: {DEFAULT_EVAL_DIR})",
    )
    args = parser.parse_args()
    eval_dir = args.eval_dir if args.eval_dir.is_absolute() else REPO_ROOT / args.eval_dir

    if not eval_dir.exists():
        print(f"Eval dir not found: {eval_dir}", file=sys.stderr)
        sys.exit(1)

    orphans = discover_orphans(eval_dir)
    if not orphans:
        print("No orphan pages found")
        return

    print(f"Found {len(orphans)} orphan(s) in {eval_dir.name}")
    print()

    results = run_orphan_header_pass(eval_dir)
    for i, r in enumerate(results):
        label = r.get("label", "?")
        status = r.get("status", "?")
        if status == "skipped_no_prior":
            print(f"[{label}] Skipped: no prior page")
        elif status == "skipped_image_caption":
            print(f"[{label}] Skipped: image+caption only, no header needed")
        elif status == "skipped_missing_md":
            print(f"[{label}] Skipped: missing surface markdown")
        elif status == "assigned":
            print(f"[{label}] Assigned:")
            print(f"  heading: {r.get('heading', '')}")
            print(f"  reason: {r.get('reason', '')}")
        else:
            print(f"[{label}] {status}")
        if i < len(results) - 1:
            print("-" * 60)


if __name__ == "__main__":
    main()

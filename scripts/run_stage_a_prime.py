#!/usr/bin/env python3
"""
Run Stage A' enrichment on existing Stage B evidence units.

Loads stageB.evidence_units.json from a page directory, runs LLM enrichment,
and writes stageAPrime.* artifacts.

Usage (from RulesIngestion root):
  uv run python scripts/run_stage_a_prime.py --page-dir out/mark3_evaluation/DnD5eBrutalChapters/DnD5eBrutalChapters_p0
  uv run python scripts/run_stage_a_prime.py --page-dir path/to/page_dir --book-id my_ruleset
  uv run python scripts/run_stage_a_prime.py --substrate-dir out/mark3_evaluation/StarFinderPlayerCore --book-id StarFinderPlayerCore

Requires OPENAI_API_KEY for LLM calls. Enrichments are cached by input fingerprint.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from extraction.pipeline import write_stage_a_prime_artifacts
from extraction.schemas import EvidenceUnit
from extraction.stage_a_prime import run_stage_a_prime

logger = logging.getLogger(__name__)


def _run_one_page(
    page_dir: Path,
    book_id: str,
    model: str,
    concurrency: int,
) -> tuple[bool, int, float]:
    """Run Stage A' on one page dir. Returns (gates_passed, enrichment_count, elapsed_sec)."""
    units_path = page_dir / "stageB.evidence_units.json"
    data = json.loads(units_path.read_text(encoding="utf-8"))
    units_raw = data.get("units", data) if isinstance(data, dict) else data
    units = [EvidenceUnit.from_dict(u) for u in units_raw]
    t0 = time.perf_counter()
    result = run_stage_a_prime(
        units,
        page_dir,
        book_id=book_id,
        model=model,
        openai_client=None,
        concurrency=concurrency,
    )
    elapsed = time.perf_counter() - t0
    write_stage_a_prime_artifacts(page_dir, result)
    return result.gates_passed, len(result.enrichments), elapsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Stage A' enrichment on existing Stage B evidence units."
    )
    parser.add_argument(
        "--page-dir",
        type=Path,
        default=None,
        help="Path to a single page output dir containing stageB.evidence_units.json",
    )
    parser.add_argument(
        "--substrate-dir",
        type=Path,
        default=None,
        help="Path to substrate (e.g. StarFinderPlayerCore); runs A' on every page dir under it.",
    )
    parser.add_argument(
        "--book-id",
        type=str,
        default=None,
        help="Book/ruleset identifier (default: page dir parent or substrate dir name)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o-mini",
        help="OpenAI model for enrichment (default: gpt-4o-mini)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Max concurrent LLM calls (default: 10)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    if (args.page_dir is None) == (args.substrate_dir is None):
        print("Error: provide exactly one of --page-dir or --substrate-dir", file=sys.stderr)
        sys.exit(1)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.page_dir is not None:
        if not os.environ.get("OPENAI_API_KEY"):
            print("Error: OPENAI_API_KEY must be set for Stage A' LLM calls.", file=sys.stderr)
            sys.exit(1)
        page_dir = args.page_dir.resolve()
        units_path = page_dir / "stageB.evidence_units.json"
        if not units_path.exists():
            print(f"Error: {units_path} not found", file=sys.stderr)
            sys.exit(1)
        data = json.loads(units_path.read_text(encoding="utf-8"))
        units_raw = data.get("units", data) if isinstance(data, dict) else data
        if not isinstance(units_raw, list):
            print("Error: stageB.evidence_units.json must contain a 'units' array", file=sys.stderr)
            sys.exit(1)
        units = [EvidenceUnit.from_dict(u) for u in units_raw]
        book_id = args.book_id or page_dir.parent.name
        print(f"Stage A': enriching {len(units)} units in {page_dir} (book_id={book_id})")
        result = run_stage_a_prime(
            units,
            page_dir,
            book_id=book_id,
            model=args.model,
            openai_client=None,
            concurrency=args.concurrency,
        )
        write_stage_a_prime_artifacts(page_dir, result)
        print(f"  Gates passed: {result.gates_passed}")
        print(f"  Enrichments: {len(result.enrichments)}")
        print(f"  Artifacts: stageAPrime.enrichments.json, .run_manifest.json, .gate_diagnostics.json")
        return

    # Substrate run
    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY must be set for Stage A' LLM calls.", file=sys.stderr)
        sys.exit(1)
    substrate = args.substrate_dir.resolve()
    if not substrate.is_dir():
        print(f"Error: substrate dir not found: {substrate}", file=sys.stderr)
        sys.exit(1)
    page_dirs = sorted(substrate.rglob("stageB.evidence_units.json"))
    page_dirs = [p.parent for p in page_dirs]
    book_id = args.book_id or substrate.name
    total_units = 0
    for d in page_dirs:
        data = json.loads((d / "stageB.evidence_units.json").read_text(encoding="utf-8"))
        u = data.get("units", data) if isinstance(data, dict) else data
        total_units += len(u) if isinstance(u, list) else 0
    print(f"Stage A' over substrate: {substrate}")
    print(f"  Page dirs: {len(page_dirs)}, Total units: {total_units}, book_id={book_id}")
    print()
    total_t0 = time.perf_counter()
    passed = 0
    total_enrichments = 0
    errors = []
    for i, page_dir in enumerate(page_dirs):
        rel = page_dir.relative_to(substrate)
        print(f"[{i + 1}/{len(page_dirs)}] {rel} ...", end=" ", flush=True)
        try:
            gates_ok, count, elapsed = _run_one_page(
                page_dir, book_id, args.model, args.concurrency
            )
            passed += 1 if gates_ok else 0
            total_enrichments += count
            print(f"{elapsed:.1f}s  gates={'PASS' if gates_ok else 'FAIL'}  enrichments={count}")
        except Exception as e:
            errors.append((str(rel), str(e)))
            print(f"ERROR: {e}")
    total_elapsed = time.perf_counter() - total_t0
    print()
    print("=" * 60)
    print(f"Total: {total_elapsed:.1f}s ({total_elapsed / 60:.1f} min)")
    print(f"  Pages: {len(page_dirs)}, Gates passed: {passed}/{len(page_dirs)}, Enrichments: {total_enrichments}")
    if errors:
        print(f"  Errors: {len(errors)}")
        for rel, err in errors[:10]:
            print(f"    {rel}: {err}")
        if len(errors) > 10:
            print(f"    ... and {len(errors) - 10} more")
    print("=" * 60)


if __name__ == "__main__":
    main()

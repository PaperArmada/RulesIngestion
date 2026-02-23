#!/usr/bin/env python3
"""
Re-run Stage A' enrichment for pages that previously failed in a full-PDF run.

Reads run_summary.json from the out dir, finds all pages with errors, loads
their existing Stage B units, and re-runs only Stage A' — skipping OCR and
Stage A/B entirely.  Updates pipeline_summary.json and run_summary.json in place.

Usage (from RulesIngestion root):
  uv run python scripts/rerun_aprime_failed.py \\
      --pdf /path/to/book.pdf \\
      --out-dir out/SwordsAndWizardry/SW_Complete_Revised
"""

from __future__ import annotations

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


def _load_env_development() -> None:
    env_path = REPO_ROOT.parent / ".env.development"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value


def main() -> None:
    _load_env_development()

    import argparse
    parser = argparse.ArgumentParser(description="Re-run Stage A' for failed pages.")
    parser.add_argument("--pdf", type=Path, required=True, help="Original PDF path.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="Base output directory (should contain run_summary.json and per-page dirs).",
    )
    parser.add_argument(
        "--model", default="gpt-4o", help="OpenAI model for Stage A' (default: gpt-4o)."
    )
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    pdf_path = args.pdf.resolve()
    stem = pdf_path.stem
    out_base = args.out_dir.resolve() / stem

    summary_path = out_base / "run_summary.json"
    if not summary_path.exists():
        print(f"ERROR: run_summary.json not found at {summary_path}", file=sys.stderr)
        sys.exit(1)

    results: list[dict] = json.loads(summary_path.read_text(encoding="utf-8"))
    failed = [r for r in results if r.get("error")]

    if not failed:
        print("No failed pages found in run_summary.json. Nothing to do.")
        sys.exit(0)

    print(f"Found {len(failed)} failed pages — re-running Stage A' only.")
    print(f"Model: {args.model}  Concurrency: {args.concurrency}")
    print()

    book_id = stem
    succeeded = 0
    still_failed = 0

    for entry in failed:
        label = entry["label"]
        page_index = entry["page"]
        page_dir = out_base / label

        units_path = page_dir / "stageB.evidence_units.json"
        if not units_path.exists():
            print(f"  SKIP {label}: stageB.evidence_units.json missing (Stage B also failed?)")
            still_failed += 1
            continue

        stage_b_data = json.loads(units_path.read_text(encoding="utf-8"))
        units = [EvidenceUnit.from_dict(u) for u in stage_b_data.get("units", [])]

        if not units:
            print(f"  SKIP {label}: 0 Stage B units — nothing to enrich")
            # Treat as success (empty enrichment is valid)
            entry["error"] = None
            entry["stage_a_prime"] = {"gates_passed": True, "enrichment_count": 0, "gate_details": [], "run_manifest": {}}
            entry["all_gates_passed"] = (
                (entry.get("stage_a") or {}).get("gates_passed", False)
                and (entry.get("stage_b") or {}).get("gates_passed", False)
            )
            succeeded += 1
            continue

        print(f"  [{page_index}] {label} ({len(units)} units) ...", end=" ", flush=True)
        t0 = time.perf_counter()
        try:
            a_prime_result = run_stage_a_prime(
                units,
                page_dir,
                book_id=book_id,
                model=args.model,
                concurrency=args.concurrency,
            )
            write_stage_a_prime_artifacts(page_dir, a_prime_result)

            # Patch pipeline_summary.json
            ps_path = page_dir / "pipeline_summary.json"
            if ps_path.exists():
                ps = json.loads(ps_path.read_text(encoding="utf-8"))
                enrichments_dict = {uid: enr.model_dump() for uid, enr in a_prime_result.enrichments}
                ps["stage_a_prime"] = {
                    "enrichments": enrichments_dict,
                    "gates_passed": a_prime_result.gates_passed,
                    "gate_details": [g.to_dict() for g in a_prime_result.gate_diagnostics],
                    "run_manifest": a_prime_result.run_manifest,
                }
                ps["all_gates_passed"] = ps.get("all_gates_passed", False) and a_prime_result.gates_passed
                ps_path.write_text(json.dumps(ps, indent=2, ensure_ascii=False), encoding="utf-8")

            # Update run_summary entry
            entry["error"] = None
            entry["elapsed_sec"] = round(time.perf_counter() - t0, 3)
            entry["stage_a_prime"] = {
                "gates_passed": a_prime_result.gates_passed,
                "enrichment_count": len(a_prime_result.enrichments),
            }
            entry["all_gates_passed"] = (
                (entry.get("stage_a") or {}).get("gates_passed", False)
                and (entry.get("stage_b") or {}).get("gates_passed", False)
                and a_prime_result.gates_passed
            )
            succeeded += 1
            elapsed = time.perf_counter() - t0
            print(f"{elapsed:.1f}s  A'={'PASS' if a_prime_result.gates_passed else 'FAIL'}  enrichments={len(a_prime_result.enrichments)}")

        except Exception as e:
            elapsed = time.perf_counter() - t0
            entry["error"] = str(e)
            still_failed += 1
            print(f"{elapsed:.1f}s  ERROR: {e}")
            logger.exception("Page %s failed again", label)

    # Write updated run_summary.json
    summary_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    total = len(failed)
    print()
    print(f"Done: {succeeded}/{total} succeeded, {still_failed}/{total} still failing.")
    print(f"Updated: {summary_path}")

    if still_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

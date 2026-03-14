"""
rerun_swcr_aprime.py — Re-run Stage A' enrichment for SWCR using current stageB unit_ids.

Problem: existing stageAPrime.enrichments.json files are keyed on unit_ids computed
from the old extraction (empty structural_path). The current stageB corpus has full
TOC-bound paths, so blake3(text|path) differs and merge_enrichments_into_corpus gets
~0% match rate.

This script:
  1. Walks all page dirs under the SWCR corpus root.
  2. Loads current stageB.evidence_units.json from each page.
  3. Calls run_stage_a_prime (which calls the OpenAI Responses API and caches per
     input_fingerprint+prompt+model). Because input_fingerprint includes the path,
     these are cache misses — the LLM will be called. Text content is identical so
     outputs will be semantically identical to the prior run; we just need new keys.
  4. Writes stageAPrime.enrichments.json (and sidecar files) keyed on the CURRENT
     unit_id. The old files are backed up as stageAPrime.enrichments.pre_rerun.json.

Usage:
    uv run python scripts/rerun_swcr_aprime.py [--dry-run] [--concurrency 10]

Requires: OPENAI_API_KEY in environment or .env.development at DungeonOverMind root.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: load .env.development so OPENAI_API_KEY is available
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DUNGEONMIND_ROOT = _REPO_ROOT.parent
_ENV_FILE = _DUNGEONMIND_ROOT / ".env.development"
if _ENV_FILE.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_ENV_FILE)
    except ImportError:
        pass  # dotenv optional; key may already be in env

sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("rerun_swcr_aprime")

SWCR_BASE = (
    _REPO_ROOT
    / "out"
    / "Swords&Wizardry"
    / "SW_Complete_Revised"
    / "SW Complete Revised PDF"
)
BOOK_ID = "SW_Complete_Revised"


def _load_stage_b_units(page_dir: Path):
    """Return list of EvidenceUnit from stageB.evidence_units.json, or []."""
    from extraction.schemas import EvidenceUnit

    path = page_dir / "stageB.evidence_units.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_units = data.get("units", [])
    return [EvidenceUnit.from_dict(u) for u in raw_units]


def _backup_existing(page_dir: Path) -> None:
    """Rename existing stageAPrime.enrichments.json to *.pre_rerun.json if present."""
    for stem in (
        "stageAPrime.enrichments",
        "stageAPrime.run_manifest",
        "stageAPrime.gate_diagnostics",
    ):
        src = page_dir / f"{stem}.json"
        if src.exists():
            dst = page_dir / f"{stem}.pre_rerun.json"
            if not dst.exists():
                src.rename(dst)
                logger.debug("Backed up %s → %s", src.name, dst.name)


def run(dry_run: bool, concurrency: int, model: str) -> None:
    from extraction.stage_a_prime import run_stage_a_prime
    from extraction.pipeline import write_stage_a_prime_artifacts

    api_key = os.environ.get("OPENAI_API_KEY")
    if not dry_run and not api_key:
        logger.error("OPENAI_API_KEY not set — aborting.")
        sys.exit(1)

    client = None
    if not dry_run:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

    page_dirs = sorted(SWCR_BASE.glob("*/"))
    page_dirs = [d for d in page_dirs if (d / "stageB.evidence_units.json").exists()]
    logger.info("Found %d page dirs with stageB units under %s", len(page_dirs), SWCR_BASE)

    total_units = 0
    total_pages = 0
    skipped = 0

    for page_dir in page_dirs:
        units = _load_stage_b_units(page_dir)
        if not units:
            skipped += 1
            continue

        logger.info(
            "Page %s: %d units%s",
            page_dir.name,
            len(units),
            " [DRY RUN]" if dry_run else "",
        )

        if dry_run:
            total_units += len(units)
            total_pages += 1
            continue

        _backup_existing(page_dir)

        result = run_stage_a_prime(
            units,
            page_dir,
            book_id=BOOK_ID,
            model=model,
            openai_client=client,
            concurrency=concurrency,
        )
        write_stage_a_prime_artifacts(page_dir, result)

        gates = "PASS" if result.gates_passed else "FAIL"
        logger.info("  → wrote enrichments for %d units  gates=%s", len(units), gates)
        total_units += len(units)
        total_pages += 1

    if dry_run:
        logger.info(
            "DRY RUN complete: would process %d pages / %d units (skipped %d empty)",
            total_pages,
            total_units,
            skipped,
        )
    else:
        logger.info(
            "Re-run complete: processed %d pages / %d units (skipped %d empty)",
            total_pages,
            total_units,
            skipped,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without calling the API or writing files.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Async concurrency for OpenAI calls per page (default: 10).",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o",
        help="OpenAI model to use (default: gpt-4o).",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run, concurrency=args.concurrency, model=args.model)


if __name__ == "__main__":
    main()

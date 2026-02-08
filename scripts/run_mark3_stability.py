#!/usr/bin/env python3
"""
Mark III stability harness — rerun Stage A+B N times, compare hashes.

Reports:
  - Which pages are deterministic across runs.
  - Which pages show nondeterminism (flagged, not fatal).
  - Hash diffs for nondeterministic pages.
  - Salvage score stability.

Usage:
  uv run python scripts/run_mark3_stability.py --manifest manifests/sample.json --runs 3
  uv run python scripts/run_mark3_stability.py --pdf /path/to/book.pdf --page 42 --runs 2
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from extraction.pipeline import run_a_b  # noqa: E402

logger = logging.getLogger(__name__)


def _load_manifest(manifest_path: Path) -> list[dict]:
    """Load a JSON manifest of (pdf, page, label) entries."""
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Manifest must be a JSON array, got {type(data).__name__}")
    for i, entry in enumerate(data):
        if "pdf" not in entry or "page" not in entry:
            raise ValueError(f"Manifest entry {i} missing 'pdf' or 'page': {entry}")
        entry.setdefault("label", Path(entry["pdf"]).stem + f"_p{entry['page']}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stability harness: rerun pipeline N times, compare hashes."
    )
    parser.add_argument("--manifest", type=Path, help="JSON manifest file.")
    parser.add_argument("--pdf", type=Path, help="Single PDF path (inline mode).")
    parser.add_argument("--page", type=int, help="Page index (inline mode).")
    parser.add_argument("--label", type=str, help="Label (inline mode).")
    parser.add_argument(
        "--runs",
        type=int,
        default=2,
        help="Number of runs per page (default: 2).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "out" / "mark3_stability",
        help="Base output directory.",
    )
    parser.add_argument(
        "--dpi", type=int, default=200, help="Render DPI (default: 200)."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable DEBUG logging."
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Build manifest
    if args.manifest:
        entries = _load_manifest(args.manifest.resolve())
    elif args.pdf and args.page is not None:
        label = args.label or f"{args.pdf.stem}_p{args.page}"
        entries = [{"pdf": str(args.pdf.resolve()), "page": args.page, "label": label}]
    else:
        print("Error: provide --manifest or (--pdf + --page).", file=sys.stderr)
        sys.exit(1)

    out_base = args.out_dir.resolve()
    out_base.mkdir(parents=True, exist_ok=True)
    num_runs = args.runs

    print(f"Stability harness: {len(entries)} pages x {num_runs} runs")
    print(f"Output: {out_base}")
    print()

    # Collect hashes per page across runs
    # page_label -> list of {run_index, stage_a_hash, stage_b_salvage, ...}
    page_runs: dict[str, list[dict]] = defaultdict(list)
    total_t0 = time.perf_counter()

    for entry in entries:
        pdf_path = Path(entry["pdf"])
        page_index = entry["page"]
        label = entry["label"]

        for run_idx in range(num_runs):
            run_out = out_base / label / f"run_{run_idx}"

            print(f"  [{label}] run {run_idx + 1}/{num_runs}...", end=" ", flush=True)
            t0 = time.perf_counter()

            try:
                result = run_a_b(
                    pdf_path, page_index, run_out, dpi=args.dpi,
                )
                elapsed = time.perf_counter() - t0

                page_runs[label].append({
                    "run_index": run_idx,
                    "stage_a_hash": result["stage_a"]["content_hash"],
                    "stage_a_gates_passed": result["stage_a"]["gates_passed"],
                    "stage_b_gates_passed": result["stage_b"]["gates_passed"],
                    "stage_b_salvage": result["stage_b"]["salvage_score"],
                    "stage_b_unit_count": len(result["stage_b"]["units"]),
                    "elapsed_sec": round(elapsed, 3),
                    "error": None,
                })
                print(f"{elapsed:.1f}s  hash={result['stage_a']['content_hash'][:16]}")

            except Exception as e:
                elapsed = time.perf_counter() - t0
                page_runs[label].append({
                    "run_index": run_idx,
                    "stage_a_hash": None,
                    "stage_a_gates_passed": False,
                    "stage_b_gates_passed": False,
                    "stage_b_salvage": 0.0,
                    "stage_b_unit_count": 0,
                    "elapsed_sec": round(elapsed, 3),
                    "error": str(e),
                })
                print(f"{elapsed:.1f}s  ERROR: {e}")

    total_elapsed = time.perf_counter() - total_t0

    # ---------------------------------------------------------------------------
    # Analysis
    # ---------------------------------------------------------------------------
    print()
    print("=" * 80)
    print("Stability Analysis")
    print("=" * 80)

    deterministic_pages: list[str] = []
    nondeterministic_pages: list[str] = []
    error_pages: list[str] = []

    for label, runs in sorted(page_runs.items()):
        hashes = [r["stage_a_hash"] for r in runs if r["stage_a_hash"] is not None]
        errors = [r for r in runs if r["error"] is not None]

        if errors:
            error_pages.append(label)
            continue

        unique_hashes = set(hashes)
        if len(unique_hashes) == 1:
            deterministic_pages.append(label)
        else:
            nondeterministic_pages.append(label)

    print(f"\nTotal pages: {len(page_runs)}")
    print(f"Deterministic: {len(deterministic_pages)}")
    print(f"Nondeterministic: {len(nondeterministic_pages)}")
    print(f"Errors: {len(error_pages)}")
    print(f"Total time: {total_elapsed:.1f}s ({total_elapsed / 60:.1f} min)")

    if deterministic_pages:
        print("\nDeterministic pages:")
        for label in deterministic_pages:
            runs = page_runs[label]
            print(f"  {label}: hash={runs[0]['stage_a_hash'][:16]}  "
                  f"salvage={runs[0]['stage_b_salvage']:.4f}")

    if nondeterministic_pages:
        print("\nNondeterministic pages (FLAGGED):")
        for label in nondeterministic_pages:
            runs = page_runs[label]
            hashes = [r["stage_a_hash"][:16] for r in runs if r["stage_a_hash"]]
            salvages = [r["stage_b_salvage"] for r in runs]
            print(f"  {label}:")
            print(f"    hashes: {hashes}")
            print(f"    salvage scores: {salvages}")

    if error_pages:
        print("\nError pages:")
        for label in error_pages:
            runs = page_runs[label]
            for r in runs:
                if r["error"]:
                    print(f"  {label} run {r['run_index']}: {r['error'][:200]}")

    # Salvage score stability
    print()
    print("-" * 60)
    print("Salvage Score Summary")
    print("-" * 60)
    for label, runs in sorted(page_runs.items()):
        salvages = [r["stage_b_salvage"] for r in runs if r["error"] is None]
        if salvages:
            stable = len(set(salvages)) == 1
            stability_marker = "STABLE" if stable else "VARIES"
            print(f"  {label}: {salvages}  [{stability_marker}]")

    # Write full report
    report = {
        "total_pages": len(page_runs),
        "num_runs": num_runs,
        "total_elapsed_sec": round(total_elapsed, 3),
        "deterministic_count": len(deterministic_pages),
        "nondeterministic_count": len(nondeterministic_pages),
        "error_count": len(error_pages),
        "deterministic_pages": deterministic_pages,
        "nondeterministic_pages": nondeterministic_pages,
        "error_pages": error_pages,
        "per_page_runs": dict(page_runs),
    }
    report_path = out_base / "stability_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nFull report: {report_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()

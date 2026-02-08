#!/usr/bin/env python3
"""
Mark III sample runner — run Stage A (and optionally Stage B) on a manifest of pages.

Usage:
  uv run python scripts/run_mark3_sample.py --manifest manifests/sample.json
  uv run python scripts/run_mark3_sample.py --manifest manifests/sample.json --stage ab

Manifest format (JSON):
  [
    {"pdf": "/abs/path/to/book.pdf", "page": 42, "label": "spell_page"},
    {"pdf": "/abs/path/to/book.pdf", "page": 100, "label": "feat_page"},
    ...
  ]

Or provide a single page inline for quick testing:
  uv run python scripts/run_mark3_sample.py --pdf /path/to/book.pdf --page 42 --label test_page
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Ensure the repo root is on the path so `extraction` is importable.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from extraction.stage_a import StageAResult, run_stage_a  # noqa: E402

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


def _print_summary(results: list[dict]) -> None:
    """Print a tabular summary of all page results."""
    print()
    print("=" * 90)
    print("Mark III Stage A — Sample Run Summary")
    print("=" * 90)

    total = len(results)
    passed = sum(1 for r in results if r["gates_passed"])
    failed = total - passed

    print(f"\nPages: {total}   Passed: {passed}   Failed: {failed}")

    total_time = sum(r["elapsed_sec"] for r in results)
    print(f"Total time: {total_time:.1f}s ({total_time / 60:.1f} min)")
    if total > 0:
        print(f"Avg per page: {total_time / total:.1f}s")

    print()
    print(f"{'Label':<40} {'Time':>6} {'Nodes':>6} {'Tables':>6} {'Gates':>7}")
    print("-" * 70)
    for r in results:
        status = "PASS" if r["gates_passed"] else "FAIL"
        print(
            f"{r['label']:<40} {r['elapsed_sec']:6.1f} "
            f"{r['node_count']:6} {r['table_count']:6} {status:>7}"
        )

    # Gate-level breakdown
    print()
    print("-" * 70)
    print("Gate pass rates:")
    gate_names: dict[str, list[bool]] = {}
    for r in results:
        for g in r.get("gate_details", []):
            gate_names.setdefault(g["gate_name"], []).append(g["passed"])
    for name, passes in sorted(gate_names.items()):
        rate = sum(passes) / len(passes) if passes else 0
        print(f"  {name}: {sum(passes)}/{len(passes)} ({rate:.0%})")

    print("=" * 90)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Mark III Stage A on a sample page set."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="JSON manifest file listing pages to process.",
    )
    parser.add_argument("--pdf", type=Path, help="Single PDF path (inline mode).")
    parser.add_argument("--page", type=int, help="Page index (inline mode).")
    parser.add_argument("--label", type=str, help="Label (inline mode).")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "out" / "mark3",
        help="Base output directory (default: out/mark3/).",
    )
    parser.add_argument(
        "--stage",
        choices=["a", "ab"],
        default="a",
        help="Which stages to run: 'a' (Stage A only) or 'ab' (Stage A + B).",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="Render DPI (default: 200).",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Build manifest entries
    if args.manifest:
        entries = _load_manifest(args.manifest.resolve())
    elif args.pdf and args.page is not None:
        label = args.label or f"{args.pdf.stem}_p{args.page}"
        entries = [{"pdf": str(args.pdf.resolve()), "page": args.page, "label": label}]
    else:
        print(
            "Error: provide --manifest or (--pdf + --page).",
            file=sys.stderr,
        )
        sys.exit(1)

    out_base = args.out_dir.resolve()
    out_base.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    run_stage_b = args.stage == "ab"

    for i, entry in enumerate(entries):
        pdf_path = Path(entry["pdf"])
        page_index = entry["page"]
        label = entry["label"]
        page_out = out_base / label

        print(f"[{i + 1}/{len(entries)}] {label}: {pdf_path.name} page {page_index}")

        t0 = time.perf_counter()
        try:
            stage_a_result: StageAResult = run_stage_a(
                pdf_path, page_index, page_out, dpi=args.dpi,
            )

            result_entry: dict = {
                "label": label,
                "pdf": str(pdf_path),
                "page": page_index,
                "elapsed_sec": round(time.perf_counter() - t0, 3),
                "gates_passed": stage_a_result.gates_passed,
                "node_count": stage_a_result.ast.node_count,
                "table_count": stage_a_result.ast.table_count,
                "content_hash": stage_a_result.ast.content_hash,
                "gate_details": [g.to_dict() for g in stage_a_result.gate_diagnostics],
                "error": None,
            }

            # Optionally run Stage B
            if run_stage_b:
                try:
                    from extraction.pipeline import run_stage_b_on_result  # noqa: E402

                    stage_b_result = run_stage_b_on_result(stage_a_result, page_out)
                    result_entry["stage_b"] = {
                        "unit_count": len(stage_b_result["units"]),
                        "gates_passed": stage_b_result["gates_passed"],
                        "gate_details": stage_b_result["gate_details"],
                        "salvage_score": stage_b_result["salvage_score"],
                    }
                except Exception as e:
                    result_entry["stage_b"] = {"error": str(e)}
                    logger.error("Stage B failed for %s: %s", label, e)

        except Exception as e:
            result_entry = {
                "label": label,
                "pdf": str(pdf_path),
                "page": page_index,
                "elapsed_sec": round(time.perf_counter() - t0, 3),
                "gates_passed": False,
                "node_count": 0,
                "table_count": 0,
                "content_hash": "",
                "gate_details": [],
                "error": str(e),
            }
            logger.error("Stage A failed for %s: %s", label, e)

        results.append(result_entry)

    # Write summary JSON
    summary_path = out_base / "run_summary.json"
    summary_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nSummary written: {summary_path}")

    _print_summary(results)

    # Exit with failure code if any gates failed
    if any(not r["gates_passed"] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Run Stage A extraction on each PDF in the brutal-pages set (one run per PDF).

Use for pipeline evaluation: run with --profile marker (default) or --profile surya,
then compare marker_stream.json and metrics.json across profiles.

Usage (from RulesIngestion root):
  uv run python scripts/run_brutal_pages.py [--input-dir blind_eval/brutal_pages] [--output-dir out/brutal_pages] [--profile marker] [--check-gates]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Run from repo root so extraction and scripts are importable.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from extraction.run import run_extraction


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run extraction on each brutal-page PDF (one logical doc per PDF)."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=REPO_ROOT / "blind_eval" / "brutal_pages",
        help="Directory containing brutal PDFs (default: blind_eval/brutal_pages)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "out" / "brutal_pages",
        help="Base output directory; each PDF gets <output-dir>/<stem>",
    )
    parser.add_argument(
        "--profile",
        choices=("marker", "surya", "deepseek_ocr2"),
        default="marker",
        help="Extraction profile (default: marker)",
    )
    parser.add_argument("--check-gates", action="store_true", help="Run gates per PDF")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Process only first N PDFs (for quick smoke test)",
    )
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    output_base = args.output_dir.resolve()
    if not input_dir.is_dir():
        print(f"Error: input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)
    output_base.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(input_dir.glob("*.pdf"), key=lambda p: p.name)
    if not pdfs:
        print(f"No PDFs in {input_dir}", file=sys.stderr)
        sys.exit(0)
    if args.limit is not None:
        pdfs = pdfs[: args.limit]

    print(f"[run_brutal_pages] Profile={args.profile} PDFs={len(pdfs)} -> {output_base}")
    failed: list[str] = []
    for i, pdf in enumerate(pdfs):
        doc_id = pdf.stem
        out_dir = output_base / doc_id
        print(f"  [{i + 1}/{len(pdfs)}] {pdf.name} -> {out_dir}")
        try:
            run_extraction(
                pdf_path=pdf,
                output_dir=out_dir,
                doc_id=doc_id,
                check_gates=args.check_gates,
                profile=args.profile,
            )
        except Exception as e:
            print(f"    FAILED: {e}", file=sys.stderr)
            failed.append(pdf.name)

    if failed:
        print(f"\nFailed: {len(failed)}/{len(pdfs)}: {failed}", file=sys.stderr)
        sys.exit(1)
    print(f"\nDone. {len(pdfs)} PDFs -> {output_base}")


if __name__ == "__main__":
    main()

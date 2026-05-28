"""Run Stage A+B on a PDF using pymupdf4llm-extracted markdown instead of OCR.

This is a tinker-side alternative to `scripts/run_mark3_full_pdf.py` for PDFs
that already have embedded text. It extracts markdown per page via the official
PyMuPDF extension (pymupdf4llm) and feeds it to Stage A via
`raw_markdown_override` + `skip_ocr=True`, avoiding the deepseek-ocr2 dependency
and its multi-minute-per-page inference cost.

Output layout matches `scripts/run_mark3_full_pdf.py`:
  <out_dir>/<stem>_p0/...stage A+B artifacts
  <out_dir>/<stem>_p1/...
  ...
  <out_dir>/run_summary.json

Usage:
  uv run python -m tinker.scripts.ingest_no_ocr \\
      --pdf input_pdfs/swords_wizardry/SW_Complete_Revised.pdf \\
      --out-dir out/swcr
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import fitz
import pymupdf4llm

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from extraction.pipeline import run_a_b  # noqa: E402

logger = logging.getLogger(__name__)


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(seconds, 60)
    return f"{int(m)}m{s:04.1f}s"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage A+B over a PDF using pymupdf4llm markdown (no OCR)."
    )
    parser.add_argument("--pdf", type=Path, required=True, help="Source PDF path.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("out/tinker_ingest"),
        help="Base output directory.",
    )
    parser.add_argument(
        "--dpi", type=int, default=200, help="Render DPI for page fingerprints."
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=0,
        help="0-based page index to resume from.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Stop after processing this many pages (for smoke testing).",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip pages whose stageB.evidence_units.json already exists.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    pdf_path = args.pdf.resolve()
    if not pdf_path.is_file():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    out_base = args.out_dir.resolve()
    out_base.mkdir(parents=True, exist_ok=True)
    stem = pdf_path.stem

    doc = fitz.open(str(pdf_path))
    num_pages = doc.page_count
    print(f"PDF: {pdf_path}")
    print(f"Pages: {num_pages}")
    print(f"Output: {out_base}")
    print()

    summary: list[dict] = []
    total_t0 = time.perf_counter()
    pages_processed = 0
    pages_skipped = 0
    pages_failed = 0

    end_page = num_pages
    if args.max_pages is not None:
        end_page = min(num_pages, args.start_page + args.max_pages)

    for page_index in range(args.start_page, end_page):
        label = f"{stem}_p{page_index}"
        page_out = out_base / label
        units_path = page_out / "stageB.evidence_units.json"

        if args.skip_existing and units_path.is_file():
            pages_skipped += 1
            print(
                f"[{page_index + 1:3d}/{num_pages}] {label}  SKIP (exists)",
                flush=True,
            )
            summary.append(
                {
                    "label": label,
                    "page": page_index,
                    "skipped": True,
                    "error": None,
                }
            )
            continue

        print(
            f"[{page_index + 1:3d}/{num_pages}] {label}  extracting...",
            end=" ",
            flush=True,
        )
        t0 = time.perf_counter()

        try:
            markdown = pymupdf4llm.to_markdown(
                str(pdf_path), pages=[page_index], show_progress=False
            )
            extract_elapsed = time.perf_counter() - t0
            combined = run_a_b(
                pdf_path,
                page_index,
                page_out,
                dpi=args.dpi,
                skip_ocr=True,
                raw_markdown_override=markdown,
            )
            elapsed = time.perf_counter() - t0
            pages_processed += 1
            entry = {
                "label": label,
                "pdf": str(pdf_path),
                "page": page_index,
                "elapsed_sec": round(elapsed, 3),
                "extract_elapsed_sec": round(extract_elapsed, 3),
                "markdown_chars": len(markdown),
                "error": None,
                "stage_a": {
                    "gates_passed": combined["stage_a"]["gates_passed"],
                    "node_count": combined["stage_a"]["node_count"],
                    "table_count": combined["stage_a"]["table_count"],
                    "content_hash": combined["stage_a"]["content_hash"],
                },
                "stage_b": {
                    "unit_count": len(combined["stage_b"].get("units", [])),
                    "gates_passed": combined["stage_b"].get("gates_passed"),
                },
            }
            summary.append(entry)
            gates_a = "ok" if entry["stage_a"]["gates_passed"] else "FAIL"
            gates_b = "ok" if entry["stage_b"]["gates_passed"] else "FAIL"
            units = entry["stage_b"]["unit_count"]
            print(
                f"{_format_elapsed(elapsed)}  "
                f"A:{gates_a} B:{gates_b}  units={units}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            pages_failed += 1
            elapsed = time.perf_counter() - t0
            summary.append(
                {
                    "label": label,
                    "page": page_index,
                    "elapsed_sec": round(elapsed, 3),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"FAIL ({type(exc).__name__}: {exc})", flush=True)
            logger.exception("page %d failed", page_index)

    total_elapsed = time.perf_counter() - total_t0
    summary_path = out_base / "run_summary.json"
    summary_payload = {
        "pdf": str(pdf_path),
        "out_dir": str(out_base),
        "stem": stem,
        "num_pages": num_pages,
        "pages_processed": pages_processed,
        "pages_skipped": pages_skipped,
        "pages_failed": pages_failed,
        "total_elapsed_sec": round(total_elapsed, 3),
        "method": "pymupdf4llm_no_ocr",
        "results": summary,
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2))

    print()
    print(
        f"Done. {pages_processed} processed, {pages_skipped} skipped, "
        f"{pages_failed} failed in {_format_elapsed(total_elapsed)}."
    )
    print(f"Summary: {summary_path}")
    return 0 if pages_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

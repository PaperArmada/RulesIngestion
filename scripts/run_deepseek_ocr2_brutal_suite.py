#!/usr/bin/env python3
"""
Run DeepSeek OCR 2 on the full brutal-pages suite (one page per PDF: page 0).

Uses the DeepSeek venv (run_deepseek_ocr2_venv.sh) for each PDF. Records per-PDF
and total timing, writes suite_timings.json, and prints estimates for full-book runs.

Usage (from RulesIngestion root):
  bash scripts/run_deepseek_ocr2_brutal_suite.sh
  # or
  bash scripts/run_deepseek_ocr2_venv.sh scripts/run_deepseek_ocr2_brutal_suite.py --input-dir blind_eval/brutal_pages --out-base out/deepseek_ocr2_brutal

Requires: NVIDIA GPU, .venv-deepseek-ocr2 with pymupdf. Run will take a long time (~2–3 min per page).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_SCRIPT = REPO_ROOT / "scripts" / "run_deepseek_ocr2_venv.sh"
MINIMAL_ARGS = ["--page", "0", "--device", "cuda"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeepSeek OCR 2 on all brutal-pages PDFs (page 0 each), record timings, print book estimates."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=REPO_ROOT / "blind_eval" / "brutal_pages",
        help="Directory containing brutal PDFs",
    )
    parser.add_argument(
        "--out-base",
        type=Path,
        default=REPO_ROOT / "out" / "deepseek_ocr2_brutal",
        help="Base output directory; each PDF gets <out-base>/<stem>/",
    )
    parser.add_argument(
        "--venv-script",
        type=Path,
        default=VENV_SCRIPT,
        help="Path to run_deepseek_ocr2_venv.sh",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Process only first N PDFs (for testing)",
    )
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    out_base = args.out_base.resolve()
    if not input_dir.is_dir():
        print(f"Error: input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)
    out_base.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(input_dir.glob("*.pdf"), key=lambda p: p.name)
    if not pdfs:
        print(f"No PDFs in {input_dir}", file=sys.stderr)
        sys.exit(1)
    if args.limit is not None:
        pdfs = pdfs[: args.limit]

    # Use venv script to run minimal with --pdf and --page 0
    venv_script = args.venv_script.resolve()
    if not venv_script.is_file():
        print(f"Error: venv script not found: {venv_script}", file=sys.stderr)
        sys.exit(1)

    per_pdf: list[dict] = []
    suite_start = time.perf_counter()

    print(f"[suite] DeepSeek OCR 2 brutal suite: {len(pdfs)} PDFs → {out_base}")
    print(f"[suite] Venv: {venv_script}")
    print("---")

    for i, pdf in enumerate(pdfs):
        stem = pdf.stem
        pdf_out = out_base / stem
        pdf_out.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        cmd = [
            "bash",
            str(venv_script),
            "--pdf",
            str(pdf.resolve()),
            "--page",
            "0",
            "--out-dir",
            str(pdf_out),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            elapsed = time.perf_counter() - t0
            ok = result.returncode == 0
            entry = {
                "stem": stem,
                "pdf": str(pdf),
                "out_dir": str(pdf_out),
                "elapsed_sec": round(elapsed, 3),
                "ok": ok,
                "returncode": result.returncode,
            }
            if not ok and result.stderr:
                entry["stderr_tail"] = result.stderr.strip()[-500:] if result.stderr else None
        except subprocess.TimeoutExpired:
            elapsed = time.perf_counter() - t0
            entry = {
                "stem": stem,
                "pdf": str(pdf),
                "out_dir": str(pdf_out),
                "elapsed_sec": round(elapsed, 3),
                "ok": False,
                "timeout": True,
            }
        except Exception as e:
            elapsed = time.perf_counter() - t0
            entry = {
                "stem": stem,
                "pdf": str(pdf),
                "out_dir": str(pdf_out),
                "elapsed_sec": round(elapsed, 3),
                "ok": False,
                "error": str(e),
            }
        per_pdf.append(entry)
        status = "ok" if entry.get("ok") else "FAIL"
        print(f"  [{i + 1}/{len(pdfs)}] {stem}: {elapsed:.1f}s {status}")

    suite_elapsed = time.perf_counter() - suite_start
    ok_count = sum(1 for e in per_pdf if e.get("ok"))
    total_pages = len(pdfs)
    avg_sec_per_page = suite_elapsed / total_pages if total_pages else 0

    # Book page counts (typical TTRPG books)
    book_estimates = [
        ("250-page book", 250),
        ("400-page book", 400),
        ("500-page book", 500),
    ]
    estimates = {}
    for label, pages in book_estimates:
        sec = avg_sec_per_page * pages
        estimates[label] = {
            "pages": pages,
            "estimated_sec": round(sec, 1),
            "estimated_min": round(sec / 60, 1),
            "estimated_hr": round(sec / 3600, 2),
        }

    summary = {
        "suite_elapsed_sec": round(suite_elapsed, 3),
        "suite_elapsed_min": round(suite_elapsed / 60, 2),
        "total_pdfs": len(pdfs),
        "ok_count": ok_count,
        "fail_count": len(pdfs) - ok_count,
        "avg_sec_per_page": round(avg_sec_per_page, 3),
        "book_estimates": estimates,
        "per_pdf": per_pdf,
    }
    timings_path = out_base / "suite_timings.json"
    timings_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("---")
    print(f"[suite] Total: {suite_elapsed:.1f}s ({suite_elapsed / 60:.1f} min)")
    print(f"[suite] OK: {ok_count}/{len(pdfs)}")
    print(f"[suite] Avg: {avg_sec_per_page:.1f}s per page")
    print("[suite] Book estimates (extrapolated from avg sec/page):")
    for label, data in estimates.items():
        print(f"  {label}: {data['estimated_min']:.0f} min ({data['estimated_hr']:.2f} hr)")
    print(f"[suite] Timings written: {timings_path}")
    if ok_count < len(pdfs):
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Run Mark III PDF ingestion for each PDF under a root directory, then write one
stitched markdown file next to each source PDF.

Pipeline output layout (from run_mark3_full_pdf.py):
  <pdf.parent>/<stem>/<stem_p{0..N-1}>/stageA.surface.md ...

This script writes:
  <pdf.parent>/<stem>.md

composed from all page surface markdown files in order.

Usage (from RulesIngestion root):
  uv run python scripts/batch_ingest_pdfs_to_sibling_md.py \\
    --root "/path/to/Docs/Eldyrwild and Campaign Context"

Options:
  --dry-run           List PDFs only
  --only-stitch       Skip ingestion; only build .md from existing <stem>/ dirs
  --skip-existing     Skip PDFs when <stem>.md already exists
  --stage ab|ab+aprime  Passed through to run_mark3_full_pdf.py (default: ab)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _parse_page_index(dir_name: str, stem: str) -> int | None:
    prefix = f"{stem}_p"
    if not dir_name.startswith(prefix):
        return None
    m = re.match(re.escape(prefix) + r"(\d+)$", dir_name)
    return int(m.group(1)) if m else None


def stitch_surface_pages(run_root: Path, stem: str) -> str | None:
    """Concatenate stageA.surface.md from run_root/<stem>_p*/ in page order."""
    if not run_root.is_dir():
        return None
    entries: list[tuple[int, Path]] = []
    for child in run_root.iterdir():
        if not child.is_dir():
            continue
        idx = _parse_page_index(child.name, stem)
        if idx is None:
            continue
        md_path = child / "stageA.surface.md"
        if md_path.is_file():
            entries.append((idx, md_path))
    if not entries:
        return None
    entries.sort(key=lambda x: x[0])
    parts: list[str] = []
    for idx, md_path in entries:
        body = md_path.read_text(encoding="utf-8").strip()
        parts.append(f"<!-- RulesIngestion page {idx} ({md_path.parent.name}) -->\n\n{body}")
    return "\n\n---\n\n".join(parts)


def discover_pdfs(root: Path) -> list[Path]:
    return sorted(p.resolve() for p in root.rglob("*.pdf") if p.is_file())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch Mark III ingest PDFs and emit <stem>.md next to each PDF."
    )
    parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help="Directory tree to scan for *.pdf",
    )
    parser.add_argument("--dry-run", action="store_true", help="List PDFs and exit")
    parser.add_argument(
        "--only-stitch",
        action="store_true",
        help="Only stitch existing per-page outputs (no OCR / no full run)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip ingestion when <stem>.md already exists next to the PDF",
    )
    parser.add_argument(
        "--stage",
        choices=["ab", "ab+aprime"],
        default="ab",
        help="Pipeline stage flag for run_mark3_full_pdf.py",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        print(f"Error: root is not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    pdfs = discover_pdfs(root)
    if not pdfs:
        print(f"No PDFs found under {root}")
        return

    print(f"Found {len(pdfs)} PDF(s) under {root}\n")

    if args.dry_run:
        for p in pdfs:
            print(p)
        return

    runner = REPO_ROOT / "scripts" / "run_mark3_full_pdf.py"
    if not runner.is_file():
        print(f"Error: runner not found: {runner}", file=sys.stderr)
        sys.exit(1)

    failures: set[Path] = set()
    for pdf in pdfs:
        stem = pdf.stem
        parent = pdf.parent
        out_md = parent / f"{stem}.md"
        run_dir = parent / stem  # run_mark3_full_pdf uses out_dir / stem

        if args.skip_existing and out_md.is_file():
            print(f"[skip existing] {pdf.name}")
            continue

        if not args.only_stitch:
            cmd = [
                "uv",
                "run",
                "python",
                str(runner),
                "--pdf",
                str(pdf),
                "--out-dir",
                str(parent),
                "--stage",
                args.stage,
            ]
            print(f"[ingest] {' '.join(cmd)}", flush=True)
            proc = subprocess.run(cmd, cwd=str(REPO_ROOT))
            if proc.returncode != 0:
                print(f"[warn] ingest exited {proc.returncode} for {pdf}", file=sys.stderr)
                failures.add(pdf)

        stitched = stitch_surface_pages(run_dir, stem)
        if not stitched:
            print(f"[error] no stageA.surface.md pages under {run_dir}", file=sys.stderr)
            failures.add(pdf)
            continue

        header = (
            f"<!-- Source: {pdf.name} | RulesIngestion Mark III Stage A surface -->\n\n"
        )
        out_md.write_text(header + stitched + "\n", encoding="utf-8")
        print(f"[ok] wrote {out_md}")

    if failures:
        print(f"\nCompleted with {len(failures)} failure(s).", file=sys.stderr)
        for p in sorted(failures):
            print(f"  - {p}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

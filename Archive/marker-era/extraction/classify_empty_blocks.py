"""
Classify empty blocks in one high-empty rulebook part: blank cell vs HTML empty after strip.

Usage:
  uv run python -m extraction.classify_empty_blocks --output-dir out/StarFinder2e-PlayerCore-v2 --part "442-464"

Reads the part's raw Marker JSON, flattens with raw_to_blocks, filters to content blocks only,
then for each block where extract_text_from_html(html).strip() is empty, classifies:
- blank_cell: no html or html is empty/whitespace only (true blank in PDF / no text layer).
- html_empty_after_strip: has non-empty html but strip yields no text (e.g. <p></p>, &nbsp;, content-ref).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections import defaultdict

from extraction.marker_runner import load_marker_json, raw_to_blocks
from extraction.normalize import extract_text_from_html, is_structural_container


def find_part_json(output_dir: Path, part_substring: str) -> Path | None:
    """Find raw Marker JSON for the part whose name contains part_substring."""
    output_dir = Path(output_dir)
    for d in output_dir.iterdir():
        if not d.is_dir() or not d.name.startswith("part_"):
            continue
        if part_substring not in d.name:
            continue
        # part_27_PZO.../PZO.../PZO....json
        for sub in d.iterdir():
            if not sub.is_dir():
                continue
            for f in sub.iterdir():
                if f.suffix == ".json" and "_meta" not in f.name:
                    return f
    return None


def classify_empty_blocks_in_part(part_json_path: Path) -> dict:
    """
    Load part JSON, flatten to blocks, and classify every block that yields empty text.
    Returns dict with counts and sample details: blank_cell, html_empty_after_strip by raw_type.
    """
    with open(part_json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    blocks = raw_to_blocks(raw)

    blank_cell: dict[str, int] = defaultdict(int)  # raw_type -> count
    html_empty_after_strip: dict[str, int] = defaultdict(int)
    blank_samples: list[dict] = []  # up to 3 per type
    html_empty_samples: list[dict] = []

    for b in blocks:
        raw_type = (b.get("block_type") or "Unknown").strip()
        if is_structural_container(raw_type):
            continue
        html = b.get("html") or ""
        extracted = extract_text_from_html(html).strip()
        if extracted != "":
            continue
        # Empty after extraction
        html_stripped = html.strip()
        if not html_stripped:
            blank_cell[raw_type] += 1
            if len(blank_samples) < 10:
                blank_samples.append({"raw_type": raw_type, "html_repr": repr(html)[:80]})
        else:
            html_empty_after_strip[raw_type] += 1
            if len(html_empty_samples) < 10:
                html_empty_samples.append({"raw_type": raw_type, "html_repr": repr(html)[:120]})

    return {
        "blank_cell": dict(blank_cell),
        "html_empty_after_strip": dict(html_empty_after_strip),
        "blank_cell_total": sum(blank_cell.values()),
        "html_empty_total": sum(html_empty_after_strip.values()),
        "blank_samples": blank_samples,
        "html_empty_samples": html_empty_samples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify empty blocks in one rulebook part (blank vs HTML-empty).")
    parser.add_argument("--output-dir", type=Path, required=True, help="Stage A output directory (contains part_* folders)")
    parser.add_argument("--part", type=str, required=True, help="Part identifier substring (e.g. 442-464 or full source_pdf_id)")
    args = parser.parse_args()

    part_path = find_part_json(args.output_dir, args.part)
    if not part_path:
        print(f"No part found containing '{args.part}' under {args.output_dir}")
        return

    print(f"Part JSON: {part_path}")
    result = classify_empty_blocks_in_part(part_path)

    print("\n--- Empty block classification ---")
    print(f"Blank cell (no/missing HTML): {result['blank_cell_total']}")
    for k, v in sorted(result["blank_cell"].items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print(f"HTML empty after strip: {result['html_empty_total']}")
    for k, v in sorted(result["html_empty_after_strip"].items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    print("\n--- Blank cell samples ---")
    for s in result["blank_samples"][:5]:
        print(f"  {s['raw_type']}: {s['html_repr']}")
    print("\n--- HTML empty-after-strip samples ---")
    for s in result["html_empty_samples"][:5]:
        print(f"  {s['raw_type']}: {s['html_repr']}")


if __name__ == "__main__":
    main()

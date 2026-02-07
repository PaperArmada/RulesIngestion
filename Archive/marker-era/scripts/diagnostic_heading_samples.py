#!/usr/bin/env python3
"""
Produce diagnostic sample artifacts for manual review of heading dominance.

Outputs:
- diagnostic_heading_samples.json: Chunks labeled Heading with block composition and text previews
- diagnostic_raw_block_samples.md: Raw Marker blocks by type (Text, SectionHeader) for visual inspection

Run from RulesIngestion root:
  uv run python scripts/diagnostic_heading_samples.py out/StarFinder2e-PlayerCore-v2
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running as script from RulesIngestion root (PYTHONPATH=. or uv run)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extraction.schemas import MarkerBlock
from extraction.normalize import normalize_block_type, build_section_path
from extraction.chunker import _default_should_drop
from collections import Counter


def dict_to_block(d: dict) -> MarkerBlock:
    return MarkerBlock(
        block_ordinal=d.get("block_ordinal", 0),
        raw_block_type=d.get("raw_block_type", ""),
        text=(d.get("text") or ""),
        bbox=tuple(d.get("bbox", (0, 0, 0, 0))[:4]),
        page_index=d.get("page_index", d.get("logical_page_index", 0)),
        section_hierarchy=d.get("section_hierarchy", []),
        doc_id=d.get("doc_id", ""),
        logical_doc_id=d.get("logical_doc_id", ""),
        document_part_id=d.get("document_part_id", ""),
        source_pdf_id=d.get("source_pdf_id", ""),
        source_pdf_page_index=d.get("source_pdf_page_index", -1),
        logical_page_index=d.get("logical_page_index", -1),
    )


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/diagnostic_heading_samples.py <output_dir>")
        print("  e.g. out/StarFinder2e-PlayerCore-v2")
        sys.exit(1)
    out_dir = Path(sys.argv[1])
    marker_path = out_dir / "marker_stream.json"
    if not marker_path.exists():
        print(f"Missing {marker_path}")
        sys.exit(1)

    ms = json.loads(marker_path.read_text())
    stream = ms if isinstance(ms, list) else ms.get("marker_stream", ms)
    blocks = [dict_to_block(b) for b in stream]

    # Replay chunker grouping and record block composition
    current_blocks: list[MarkerBlock] = []
    current_section_path: list[str] = []
    current_page = -1
    groups: list[dict] = []

    def flush_group() -> None:
        nonlocal current_blocks, current_section_path
        if not current_blocks:
            return
        texts = [b.text.strip() for b in current_blocks if (b.text or "").strip()]
        combined = "\n\n".join(texts)
        block_types = [normalize_block_type(b.raw_block_type) for b in current_blocks]
        primary = (
            "Heading"
            if "Heading" in block_types
            else (block_types[0] if block_types else "Text")
        )
        counts = Counter(block_types)
        groups.append(
            {
                "primary_type": primary,
                "block_type_counts": dict(counts),
                "n_blocks": len(current_blocks),
                "text_len": len(combined),
                "page": current_blocks[0].page_index if current_blocks else -1,
                "first_ord": current_blocks[0].block_ordinal if current_blocks else -1,
                "text_preview": combined[:800] + ("..." if len(combined) > 800 else ""),
            }
        )
        current_blocks = []

    for block in blocks:
        drop, _ = _default_should_drop(block)
        if drop:
            continue
        section_path = build_section_path(block.section_hierarchy)
        is_heading = normalize_block_type(block.raw_block_type) == "Heading"
        page = block.page_index
        section_changed = section_path != current_section_path
        if current_blocks and (section_changed or (is_heading and current_blocks)):
            flush_group()
        if is_heading:
            current_section_path = section_path
        elif not current_section_path and section_path:
            current_section_path = section_path
        current_page = page
        current_blocks.append(block)
    flush_group()

    # Heading groups (labeled Heading by primary_type)
    heading_groups = [g for g in groups if g["primary_type"] == "Heading"]
    with_text = [g for g in heading_groups if g["block_type_counts"].get("Text", 0) > 0]
    heading_only = [g for g in heading_groups if g["block_type_counts"].get("Heading", 1) and not g["block_type_counts"].get("Text", 0)]

    # --- diagnostic_heading_samples.json ---
    samples = {
        "summary": {
            "total_groups": len(groups),
            "heading_groups": len(heading_groups),
            "heading_groups_with_text_blocks": len(with_text),
            "heading_only_groups": len(heading_only),
        },
        "heading_with_text_samples": with_text[:30],
        "heading_only_samples": heading_only[:20],
    }
    out_path = out_dir / "diagnostic_heading_samples.json"
    out_path.write_text(json.dumps(samples, indent=2))
    print(f"Wrote {out_path}")

    # --- diagnostic_raw_block_samples.md ---
    raw_by_type: dict[str, list[dict]] = {}
    for b in stream:
        t = b.get("raw_block_type", "unknown")
        raw_by_type.setdefault(t, [])
        raw_by_type[t].append(b)

    lines = [
        "# Raw Marker Block Samples by Type",
        "",
        "Samples from `marker_stream.json` for visual inspection of Text vs SectionHeader patterns.",
        "",
        "## Block type counts",
        "",
    ]
    for t, arr in sorted(raw_by_type.items(), key=lambda x: -len(x[1])):
        lines.append(f"- **{t}**: {len(arr)} blocks")
    lines.append("")
    lines.append("---")
    lines.append("")

    for block_type in ["Text", "SectionHeader", "Title"]:
        if block_type not in raw_by_type:
            continue
        arr = raw_by_type[block_type]
        lines.append(f"## {block_type} (first 25 samples)")
        lines.append("")
        for i, b in enumerate(arr[:25]):
            text = (b.get("text") or "").strip()
            preview = text[:300] + ("..." if len(text) > 300 else "")
            page = b.get("page_index", b.get("logical_page_index", "?"))
            ord_val = b.get("block_ordinal", "?")
            lines.append(f"### Sample {i + 1} (page={page}, ord={ord_val})")
            lines.append("")
            lines.append("```")
            lines.append(preview)
            lines.append("```")
            lines.append("")

    md_path = out_dir / "diagnostic_raw_block_samples.md"
    md_path.write_text("\n".join(lines))
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()

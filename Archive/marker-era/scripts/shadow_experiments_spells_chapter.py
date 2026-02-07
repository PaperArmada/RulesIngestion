"""
Shadow-logic experiments A1, B1, C1 on spells chapter (pages 330–363).
Computes M-A9, M-A10, M-A11 before/after each intervention (metric-only, no extraction change).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add parent so extraction is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extraction.normalize import build_section_path, normalize_block_type
from extraction.schemas import Chunk, MarkerBlock
from extraction.structural_fidelity_metrics import (
    DEFAULT_COLUMN_WIDTH_THRESHOLD_PT,
    DEFAULT_CONTINUATION_PREFIXES,
    DEFAULT_MAX_VERTICAL_DISTANCE_PT,
    DEFAULT_OUTCOME_PREFIXES,
)

SPELL_PAGES = set(range(330, 364))
_PROSE_BLOCK_TYPES = frozenset({"Text", "ListItem", "Footnote"})


def _section_path(block: MarkerBlock) -> list[str]:
    return build_section_path(block.section_hierarchy)


def _l1(path: list[str]) -> str:
    return path[0] if path else ""


def _y_center(bbox: tuple[float, float, float, float]) -> float:
    return (bbox[1] + bbox[3]) / 2.0


def _x_center(bbox: tuple[float, float, float, float]) -> float:
    return (bbox[0] + bbox[2]) / 2.0


def _starts_with(text: str, prefixes: tuple[str, ...]) -> bool:
    sample = (text or "").strip()
    if "\n" in sample:
        sample = sample.split("\n")[0].strip()
    else:
        sample = sample[:80].strip()
    return bool(sample and any(sample.startswith(p) for p in prefixes))


def _is_prose(block: MarkerBlock) -> bool:
    if not (block.text or "").strip():
        return False
    return normalize_block_type(block.raw_block_type) in _PROSE_BLOCK_TYPES


def _is_heading_block(block: MarkerBlock) -> bool:
    return normalize_block_type(block.raw_block_type) == "Heading"


def _column_jump(b_i: MarkerBlock, b_next: MarkerBlock) -> bool:
    if b_i.page_index != b_next.page_index:
        return False
    bb_i = b_i.bbox or (0.0, 0.0, 0.0, 0.0)
    bb_n = b_next.bbox or (0.0, 0.0, 0.0, 0.0)
    return abs(_x_center(bb_i) - _x_center(bb_n)) > DEFAULT_COLUMN_WIDTH_THRESHOLD_PT


def _short_label(block: MarkerBlock) -> bool:
    t = (block.text or "").strip()
    if len(t) > 12:
        return False
    return t.isupper() if t else False


def compute_m_a9(
    blocks: list[MarkerBlock],
    effective_l1: list[str] | None = None,
    *,
    skip_violation_if: callable = None,
) -> tuple[int, int, float]:
    """Returns (violations, eligible_pairs, rate). skip_violation_if(i, b_i, b_next) -> True to not count."""
    violations = 0
    eligible = 0
    l1_i = effective_l1 if effective_l1 is not None else [_l1(_section_path(b)) for b in blocks]
    for i in range(len(blocks) - 1):
        b_i, b_next = blocks[i], blocks[i + 1]
        path_i = _section_path(b_i)
        path_n = _section_path(b_next)
        if not path_i or not path_n:
            continue
        if not _is_prose(b_i) or not _is_prose(b_next):
            continue
        eligible += 1
        li, ln = l1_i[i], l1_i[i + 1]
        if li == ln:
            continue
        vdist = abs(_y_center(b_i.bbox or (0, 0, 0, 0)) - _y_center(b_next.bbox or (0, 0, 0, 0)))
        if vdist > DEFAULT_MAX_VERTICAL_DISTANCE_PT:
            continue
        if not _starts_with(b_next.text, DEFAULT_CONTINUATION_PREFIXES):
            continue
        if skip_violation_if and skip_violation_if(i, b_i, b_next):
            continue
        violations += 1
    rate = violations / eligible if eligible else 0.0
    return violations, eligible, rate


def compute_m_a10(
    chunks: list[Chunk],
    effective_l1: list[str] | None = None,
) -> tuple[int, int, float]:
    """Returns (misassigned, outcome_with_header, rate)."""
    outcome_with_header = 0
    misassigned = 0
    l1_list = effective_l1 if effective_l1 is not None else [_l1(c.section_path or []) for c in chunks]
    last_heading_l1: str | None = None
    last_heading_page = -1
    for idx, c in enumerate(chunks):
        if c.block_type == "Heading":
            last_heading_l1 = l1_list[idx]
            last_heading_page = c.page_index
            continue
        if not _starts_with(c.text, DEFAULT_OUTCOME_PREFIXES):
            continue
        if last_heading_l1 is None or last_heading_page < c.page_index - 1:
            continue
        outcome_with_header += 1
        if l1_list[idx] != last_heading_l1:
            misassigned += 1
    rate = misassigned / outcome_with_header if outcome_with_header else 0.0
    return misassigned, outcome_with_header, rate


def compute_m_a11(
    blocks: list[MarkerBlock],
    effective_l1: list[str] | None = None,
    *,
    count_path_change_only_when: callable = None,
) -> tuple[int, int, float]:
    """count_path_change_only_when(i, b_i, b_next, l1_i, l1_next) -> True to count this pair as path change."""
    jump_count = 0
    jump_and_change = 0
    l1_list = effective_l1 if effective_l1 is not None else [_l1(_section_path(b)) for b in blocks]
    for i in range(len(blocks) - 1):
        b_i, b_next = blocks[i], blocks[i + 1]
        if b_i.page_index != b_next.page_index:
            continue
        bb_i = b_i.bbox or (0.0, 0.0, 0.0, 0.0)
        bb_n = b_next.bbox or (0.0, 0.0, 0.0, 0.0)
        if abs(_x_center(bb_i) - _x_center(bb_n)) <= DEFAULT_COLUMN_WIDTH_THRESHOLD_PT:
            continue
        jump_count += 1
        li, ln = l1_list[i], l1_list[i + 1]
        if count_path_change_only_when:
            if count_path_change_only_when(i, b_i, b_next, li, ln):
                jump_and_change += 1
        else:
            if li != ln:
                jump_and_change += 1
    rate = jump_and_change / jump_count if jump_count else 0.0
    return jump_count, jump_and_change, rate


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "out" / "StarFinder2e-PlayerCore-v2"
    with open(out_dir / "marker_stream.json") as f:
        raw_blocks = json.load(f)
    with open(out_dir / "chunks.json") as f:
        raw_chunks = json.load(f)

    def bbox(b):
        if isinstance(b, list) and len(b) >= 4:
            return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
        return (0.0, 0.0, 0.0, 0.0)

    def to_block(d):
        return MarkerBlock(
            doc_id=d.get("doc_id", ""),
            page_index=int(d.get("page_index", 0)),
            text=d.get("text", "") or "",
            bbox=bbox(d.get("bbox")),
            raw_block_type=d.get("raw_block_type", "Text"),
            block_ordinal=int(d.get("block_ordinal", 0)),
            section_hierarchy=d.get("section_hierarchy") or {},
            logical_doc_id=d.get("logical_doc_id", ""),
            document_part_id=d.get("document_part_id", ""),
            source_pdf_id=d.get("source_pdf_id", ""),
            source_pdf_page_index=int(d.get("source_pdf_page_index", -1)),
            logical_page_index=int(d.get("logical_page_index", -1)),
        )

    def to_chunk(d):
        return Chunk(
            chunk_id=d["chunk_id"],
            doc_id=d["doc_id"],
            page_index=int(d["page_index"]),
            section_path=d.get("section_path") or [],
            block_type=d.get("block_type", "Text"),
            text=d["text"],
            span_start=int(d["span_start"]),
            span_end=int(d["span_end"]),
            span_locality=d.get("span_locality", "block"),
            bbox=bbox(d.get("bbox")),
            block_ordinals=d.get("block_ordinals") or [],
            structural_metadata=d.get("structural_metadata") or {},
            logical_doc_id=d.get("logical_doc_id", ""),
            document_part_id=d.get("document_part_id", ""),
            source_pdf_id=d.get("source_pdf_id", ""),
            source_pdf_page_index=int(d.get("source_pdf_page_index", -1)),
            logical_page_index=int(d.get("logical_page_index", -1)),
        )

    blocks = [to_block(b) for b in raw_blocks if b.get("page_index") in SPELL_PAGES]
    chunks = [to_chunk(c) for c in raw_chunks if c.get("page_index") in SPELL_PAGES]

    # Baseline effective L1 (actual)
    base_l1_blocks = [_l1(_section_path(b)) for b in blocks]
    base_l1_chunks = [_l1(c.section_path or []) for c in chunks]

    # A1: outcome inheritance — effective L1 for blocks/chunks
    a1_l1_blocks = []
    last_h_l1: str | None = None
    for b in blocks:
        if _is_heading_block(b):
            last_h_l1 = _l1(_section_path(b))
        if _starts_with(b.text, DEFAULT_OUTCOME_PREFIXES) and last_h_l1 is not None:
            a1_l1_blocks.append(last_h_l1)
        else:
            a1_l1_blocks.append(_l1(_section_path(b)))
    a1_l1_chunks = []
    last_h_l1 = None
    for c in chunks:
        if c.block_type == "Heading":
            last_h_l1 = _l1(c.section_path or [])
        if _starts_with(c.text, DEFAULT_OUTCOME_PREFIXES) and last_h_l1 is not None:
            a1_l1_chunks.append(last_h_l1)
        else:
            a1_l1_chunks.append(_l1(c.section_path or []))

    # B1: for M-A9 skip violation when column_jump and both prose; for M-A11 count path change only when NOT (column_jump and both prose)
    def b1_skip_violation(i, b_i, b_next):
        return _column_jump(b_i, b_next) and _is_prose(b_i) and _is_prose(b_next)

    def b1_count_path_change(i, b_i, b_next, li, ln):
        if li == ln:
            return False
        if _column_jump(b_i, b_next) and _is_prose(b_i) and _is_prose(b_next):
            return False
        return True

    # C1: skip M-A9 violation when block_i is short label and column jump
    def c1_skip_violation(i, b_i, b_next):
        return _short_label(b_i) and _column_jump(b_i, b_next)

    # Runs
    baseline_m_a9 = compute_m_a9(blocks, base_l1_blocks)
    baseline_m_a10 = compute_m_a10(chunks, base_l1_chunks)
    baseline_m_a11 = compute_m_a11(blocks, base_l1_blocks)

    a1_m_a9 = compute_m_a9(blocks, a1_l1_blocks)
    a1_m_a10 = compute_m_a10(chunks, a1_l1_chunks)
    a1_m_a11 = baseline_m_a11  # unchanged

    b1_m_a9 = compute_m_a9(blocks, base_l1_blocks, skip_violation_if=b1_skip_violation)
    b1_m_a10 = baseline_m_a10  # unchanged
    b1_m_a11 = compute_m_a11(blocks, base_l1_blocks, count_path_change_only_when=b1_count_path_change)

    c1_m_a9 = compute_m_a9(blocks, base_l1_blocks, skip_violation_if=c1_skip_violation)
    c1_m_a10 = baseline_m_a10
    c1_m_a11 = baseline_m_a11

    # Combined A1+B1
    def a1b1_skip_violation(i, b_i, b_next):
        return b1_skip_violation(i, b_i, b_next)

    a1b1_m_a9 = compute_m_a9(blocks, a1_l1_blocks, skip_violation_if=a1b1_skip_violation)
    a1b1_m_a10 = compute_m_a10(chunks, a1_l1_chunks)
    a1b1_m_a11 = compute_m_a11(
        blocks, a1_l1_blocks, count_path_change_only_when=b1_count_path_change
    )

    # A1+B1+C1: use A1 L1 for blocks, B1 skip for M-A9, C1 skip as well (both skip conditions)
    def a1b1c1_skip_violation(i, b_i, b_next):
        if b1_skip_violation(i, b_i, b_next):
            return True
        if c1_skip_violation(i, b_i, b_next):
            return True
        return False

    a1b1c1_m_a9 = compute_m_a9(blocks, a1_l1_blocks, skip_violation_if=a1b1c1_skip_violation)
    a1b1c1_m_a10 = compute_m_a10(chunks, a1_l1_chunks)
    a1b1c1_m_a11 = compute_m_a11(
        blocks, a1_l1_blocks, count_path_change_only_when=b1_count_path_change
    )

    # Output
    def row(name, m9, m10, m11):
        v9, e9, r9 = m9
        v10, o10, r10 = m10
        j11, c11, r11 = m11
        return f"| {name} | {v9} / {e9} ({r9:.2%}) | {v10} / {o10} ({r10:.2%}) | {c11} / {j11} ({r11:.2%}) |"

    lines = [
        "# Shadow experiments (spells chapter, pages 330–363)",
        "",
        "## Before / after deltas",
        "",
        "| Condition | M-A9 (violations / eligible, rate) | M-A10 (misassigned / outcome_w_header, rate) | M-A11 (path_change / column_jumps, rate) |",
        "|-----------|-------------------------------------|---------------------------------------------|------------------------------------------|",
        row("Baseline", baseline_m_a9, baseline_m_a10, baseline_m_a11),
        row("A1 (outcome inheritance)", a1_m_a9, a1_m_a10, a1_m_a11),
        row("B1 (column-jump smoothing)", b1_m_a9, b1_m_a10, b1_m_a11),
        row("C1 (short-label skip)", c1_m_a9, c1_m_a10, c1_m_a11),
        row("A1+B1", a1b1_m_a9, a1b1_m_a10, a1b1_m_a11),
        row("A1+B1+C1", a1b1c1_m_a9, a1b1c1_m_a10, a1b1c1_m_a11),
        "",
        "## Deltas vs baseline",
        "",
    ]

    def delta(cur, base):
        vc, ec, rc = cur
        vb, eb, rb = base
        d = rc - rb
        return f"{d:+.2%}" if eb and ec else "—"

    lines.append("| Condition | Δ M-A9 rate | Δ M-A10 rate | Δ M-A11 rate |")
    lines.append("|-----------|-------------|--------------|--------------|")
    lines.append(f"| A1 | {delta(a1_m_a9, baseline_m_a9)} | {delta(a1_m_a10, baseline_m_a10)} | {delta(a1_m_a11, baseline_m_a11)} |")
    lines.append(f"| B1 | {delta(b1_m_a9, baseline_m_a9)} | {delta(b1_m_a10, baseline_m_a10)} | {delta(b1_m_a11, baseline_m_a11)} |")
    lines.append(f"| C1 | {delta(c1_m_a9, baseline_m_a9)} | {delta(c1_m_a10, baseline_m_a10)} | {delta(c1_m_a11, baseline_m_a11)} |")
    lines.append(f"| A1+B1 | {delta(a1b1_m_a9, baseline_m_a9)} | {delta(a1b1_m_a10, baseline_m_a10)} | {delta(a1b1_m_a11, baseline_m_a11)} |")
    lines.append(f"| A1+B1+C1 | {delta(a1b1c1_m_a9, baseline_m_a9)} | {delta(a1b1c1_m_a10, baseline_m_a10)} | {delta(a1b1c1_m_a11, baseline_m_a11)} |")

    out_path = out_dir / "SHADOW-EXPERIMENTS-SPELLS-CHAPTER.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(out_path.read_text())


if __name__ == "__main__":
    main()

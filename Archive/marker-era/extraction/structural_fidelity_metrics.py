"""
Structural fidelity metrics (M-A9–M-A11). Observational only; no behavior change.

Contract: Stage A Sub-Contract — Structural Fidelity & Layout-Driven Misassignment.
"""

from __future__ import annotations

from extraction.normalize import build_section_path, normalize_block_type
from extraction.schemas import Chunk, MarkerBlock

# M-A9: continuation cues (second block starts with one of these → possible violation when L1 changes)
DEFAULT_CONTINUATION_PREFIXES: tuple[str, ...] = (
    "Failure",
    "Success",
    "Critical ",
    "If you ",
    "You ",
)
# M-A9: max vertical distance (pt) to consider "same flow"
DEFAULT_MAX_VERTICAL_DISTANCE_PT: float = 50.0
# M-A10: outcome-like chunk text prefixes (order: longer first)
DEFAULT_OUTCOME_PREFIXES: tuple[str, ...] = (
    "Critical Success",
    "Critical Failure",
    "Success",
    "Failure",
)
# M-A11: x-gap (pt) above which we consider a column jump
DEFAULT_COLUMN_WIDTH_THRESHOLD_PT: float = 200.0

# Prose/rule-compatible block types for M-A9 eligible pairs
_PROSE_BLOCK_TYPES = frozenset({"Text", "ListItem", "Footnote"})


def _section_path(block: MarkerBlock) -> list[str]:
    """Derive section_path from MarkerBlock.section_hierarchy (same as chunker)."""
    return build_section_path(block.section_hierarchy)


def _l1(path: list[str]) -> str:
    """First level of section path; empty string if no path."""
    return path[0] if path else ""


def _is_eligible_prose_block(block: MarkerBlock) -> bool:
    """True if block is prose/rule-compatible and has non-empty text."""
    if not (block.text or "").strip():
        return False
    return normalize_block_type(block.raw_block_type) in _PROSE_BLOCK_TYPES


def _y_center(bbox: tuple[float, float, float, float]) -> float:
    x0, y0, x1, y1 = bbox
    return (y0 + y1) / 2.0


def _x_center(bbox: tuple[float, float, float, float]) -> float:
    x0, y0, x1, y1 = bbox
    return (x0 + x1) / 2.0


def _vertical_distance(b1: MarkerBlock, b2: MarkerBlock) -> float:
    """Vertical distance between block centroids (pt)."""
    bb1 = b1.bbox or (0.0, 0.0, 0.0, 0.0)
    bb2 = b2.bbox or (0.0, 0.0, 0.0, 0.0)
    return abs(_y_center(bb1) - _y_center(bb2))


def _starts_with_continuation_cue(
    text: str,
    prefixes: tuple[str, ...],
) -> bool:
    """True if trimmed first line (or first 80 chars) starts with one of the prefixes."""
    sample = (text or "").strip()
    if "\n" in sample:
        sample = sample.split("\n")[0].strip()
    else:
        sample = sample[:80].strip()
    if not sample:
        return False
    return any(sample.startswith(p) for p in prefixes)


def _starts_with_outcome(text: str, prefixes: tuple[str, ...]) -> bool:
    """True if chunk text (trimmed, first line) starts with one of the outcome prefixes."""
    sample = (text or "").strip()
    if "\n" in sample:
        sample = sample.split("\n")[0].strip()
    else:
        sample = sample[:80].strip()
    if not sample:
        return False
    return any(sample.startswith(p) for p in prefixes)


def compute_structural_continuity_violation_rate(
    marker_stream: list[MarkerBlock],
    *,
    max_vertical_pt: float = DEFAULT_MAX_VERTICAL_DISTANCE_PT,
    continuation_prefixes: tuple[str, ...] = DEFAULT_CONTINUATION_PREFIXES,
) -> dict:
    """
    M-A9: violations / eligible_pairs. Eligible = consecutive prose blocks (same page or adjacent)
    with non-empty section_path. Violation = L1 change + small vertical distance + continuation cue on second block.
    """
    violations = 0
    eligible_pairs = 0
    by_page: dict[int, tuple[int, int]] = {}

    for i in range(len(marker_stream) - 1):
        b_i = marker_stream[i]
        b_next = marker_stream[i + 1]
        path_i = _section_path(b_i)
        path_next = _section_path(b_next)
        if not path_i or not path_next:
            continue
        if not _is_eligible_prose_block(b_i) or not _is_eligible_prose_block(b_next):
            continue
        eligible_pairs += 1
        page = b_i.page_index
        if page not in by_page:
            by_page[page] = (0, 0)
        v_page, e_page = by_page[page]
        by_page[page] = (v_page, e_page + 1)

        l1_i = _l1(path_i)
        l1_next = _l1(path_next)
        if l1_i == l1_next:
            continue
        if _vertical_distance(b_i, b_next) > max_vertical_pt:
            continue
        if not _starts_with_continuation_cue(b_next.text, continuation_prefixes):
            continue
        violations += 1
        v_page, e_page = by_page[page]
        by_page[page] = (v_page + 1, e_page)

    rate = violations / eligible_pairs if eligible_pairs else 0.0
    return {
        "violations": violations,
        "eligible_pairs": eligible_pairs,
        "rate": rate,
        "by_page": {str(k): {"violations": v, "eligible_pairs": e} for k, (v, e) in by_page.items()},
    }


def compute_rule_outcome_misassignment_rate(
    chunks: list[Chunk],
    *,
    outcome_prefixes: tuple[str, ...] = DEFAULT_OUTCOME_PREFIXES,
    max_page_gap: int = 1,
) -> dict:
    """
    M-A10: Among outcome-labeled chunks that have a preceding Heading within max_page_gap,
    fraction whose L1 != that Heading's L1.
    """
    outcome_with_header = 0
    misassigned = 0
    last_heading_l1: str | None = None
    last_heading_page: int = -1

    for c in chunks:
        if c.block_type == "Heading":
            last_heading_l1 = _l1(c.section_path or [])
            last_heading_page = c.page_index
            continue
        if not _starts_with_outcome(c.text, outcome_prefixes):
            continue
        if last_heading_l1 is None or last_heading_page < c.page_index - max_page_gap:
            continue
        outcome_with_header += 1
        chunk_l1 = _l1(c.section_path or [])
        if chunk_l1 != last_heading_l1:
            misassigned += 1

    rate = misassigned / outcome_with_header if outcome_with_header else 0.0
    return {
        "outcome_chunks_with_header": outcome_with_header,
        "misassigned_count": misassigned,
        "rate": rate,
    }


def compute_column_jump_structural_divergence(
    marker_stream: list[MarkerBlock],
    *,
    column_width_threshold_pt: float = DEFAULT_COLUMN_WIDTH_THRESHOLD_PT,
) -> dict:
    """
    M-A11: Among same-page adjacent pairs with column jump (x-gap > threshold),
    fraction where L1 also changes.
    """
    column_jump_count = 0
    column_jump_and_path_change = 0

    for i in range(len(marker_stream) - 1):
        b_i = marker_stream[i]
        b_next = marker_stream[i + 1]
        if b_i.page_index != b_next.page_index:
            continue
        bb_i = b_i.bbox or (0.0, 0.0, 0.0, 0.0)
        bb_next = b_next.bbox or (0.0, 0.0, 0.0, 0.0)
        x_gap = abs(_x_center(bb_i) - _x_center(bb_next))
        if x_gap <= column_width_threshold_pt:
            continue
        column_jump_count += 1
        path_i = _section_path(b_i)
        path_next = _section_path(b_next)
        l1_i = _l1(path_i)
        l1_next = _l1(path_next)
        if l1_i != l1_next:
            column_jump_and_path_change += 1

    rate = (
        column_jump_and_path_change / column_jump_count
        if column_jump_count
        else 0.0
    )
    return {
        "column_jump_count": column_jump_count,
        "column_jump_and_path_change_count": column_jump_and_path_change,
        "rate": rate,
    }


def compute_all_structural_fidelity_metrics(
    marker_stream: list[MarkerBlock],
    chunks: list[Chunk],
    **kwargs: object,
) -> dict:
    """Compute M-A9, M-A10, M-A11 and return dict for metrics.json structural_fidelity key."""
    m_a9 = compute_structural_continuity_violation_rate(marker_stream, **kwargs)
    m_a10 = compute_rule_outcome_misassignment_rate(chunks, **kwargs)
    m_a11 = compute_column_jump_structural_divergence(marker_stream, **kwargs)
    return {
        "M_A9_structural_continuity_violation_rate": m_a9,
        "M_A10_rule_outcome_misassignment_rate": m_a10,
        "M_A11_column_jump_structural_divergence": m_a11,
    }

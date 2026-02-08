"""
Stage B Quality Gates.

Four gates per the Stage B contract:
  1. Orphan   — Flag EvidenceUnits with empty structural_path (no heading parent).
     Exemption: image+caption-only pages (1–2 children: paragraph + image_ref) pass.
  2. Bleed    — Flag units whose source line ranges overlap (section bleed).
  3. Table integrity — Each table EvidenceUnit contains a complete table.
  4. Unit size bounds — Flag units shorter than 20 chars or longer than 5000 chars.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from extraction.orphan_header import is_image_and_caption_only_ast
from extraction.schemas import EvidenceUnit, GateDiagnostic

logger = logging.getLogger(__name__)

_HTML_ROW_RE = re.compile(r"<tr\b", re.IGNORECASE)
_HTML_TABLE_OPEN_RE = re.compile(r"<table\b", re.IGNORECASE)
_HTML_TABLE_CLOSE_RE = re.compile(r"</table>", re.IGNORECASE)

# Thresholds
MIN_UNIT_CHARS = 20
MAX_UNIT_CHARS = 5000


def gate_orphan(
    units: list[EvidenceUnit],
    *,
    fail_threshold: float = 1.0,
    warn_threshold: float = 0.5,
    ast_dict: dict[str, Any] | None = None,
    is_standalone: bool = False,
) -> GateDiagnostic:
    """Orphan gate: flag units with empty structural_path.

    Units without heading ancestry are "orphans" — they have no structural
    context.  A few orphans at the top of a page (before the first heading)
    are expected; many orphans indicate a heading-detection failure.

    The gate uses a percentage threshold rather than requiring zero orphans:
      - FAIL if orphan rate >= *fail_threshold* (default: 100% — every unit
        is an orphan, meaning the page has no heading structure at all).
      - WARN (pass=True, but flagged) if orphan rate >= *warn_threshold*.
      - PASS cleanly otherwise.

    Exemptions (always pass):
      - Single-unit pages (forms, image-only).
      - Image+caption-only pages (1–2 children: paragraph + image_ref).
      - Standalone pages (no prior page; e.g. single-page PDFs, page 0).
    """
    if len(units) <= 1:
        return GateDiagnostic(
            gate_name="orphan",
            passed=True,
            detail={"total_units": len(units), "orphan_count": 0, "note": "single-unit page exempted"},
        )

    if ast_dict is not None and is_image_and_caption_only_ast(ast_dict):
        return GateDiagnostic(
            gate_name="orphan",
            passed=True,
            detail={
                "total_units": len(units),
                "orphan_count": len(units),
                "note": "image+caption only, no header needed",
            },
        )

    orphans = [
        {
            "unit_id": u.unit_id[:16],
            "unit_type": u.unit_type,
            "ordering_key": u.ordering_key,
            "text_preview": u.text[:80],
        }
        for u in units
        if not u.structural_path
    ]

    if is_standalone and len(orphans) == len(units):
        return GateDiagnostic(
            gate_name="orphan",
            passed=True,
            detail={
                "total_units": len(units),
                "orphan_count": len(orphans),
                "note": "standalone page, no prior context",
            },
        )

    orphan_rate = len(orphans) / len(units) if units else 0.0
    passed = orphan_rate < fail_threshold
    warned = orphan_rate >= warn_threshold

    detail = {
        "total_units": len(units),
        "orphan_count": len(orphans),
        "orphan_rate": round(orphan_rate, 4),
        "fail_threshold": fail_threshold,
        "warn_threshold": warn_threshold,
        "warned": warned,
        "orphans": orphans[:10],  # cap for large pages
    }

    if not passed:
        logger.warning("Orphan gate FAILED: %d/%d orphans (rate=%.2f)", len(orphans), len(units), orphan_rate)
    elif warned:
        logger.info("Orphan gate WARN: %d/%d orphans (rate=%.2f)", len(orphans), len(units), orphan_rate)

    return GateDiagnostic(gate_name="orphan", passed=passed, detail=detail)


def gate_bleed(units: list[EvidenceUnit]) -> GateDiagnostic:
    """Bleed gate: flag units whose source line ranges overlap.

    If unit A covers lines [10, 15) and unit B covers [13, 20), that's a bleed.
    This means the segmenter created overlapping EvidenceUnits, which violates
    the partitioning invariant.
    """
    overlaps: list[dict] = []

    # Sort by source_line_start for efficient pairwise comparison
    sorted_units = sorted(units, key=lambda u: (u.source_line_start, u.source_line_end))

    for i in range(len(sorted_units) - 1):
        a = sorted_units[i]
        b = sorted_units[i + 1]
        # Overlap if a.end > b.start (both are [start, end) ranges)
        if a.source_line_end > b.source_line_start:
            overlaps.append({
                "unit_a": a.unit_id[:16],
                "unit_b": b.unit_id[:16],
                "a_range": [a.source_line_start, a.source_line_end],
                "b_range": [b.source_line_start, b.source_line_end],
            })

    passed = len(overlaps) == 0
    detail = {
        "total_units": len(units),
        "overlap_count": len(overlaps),
        "overlaps": overlaps[:10],
    }

    if not passed:
        logger.warning("Bleed gate FLAGGED: %d overlaps", len(overlaps))

    return GateDiagnostic(gate_name="bleed", passed=passed, detail=detail)


def gate_table_integrity(units: list[EvidenceUnit]) -> GateDiagnostic:
    """Table integrity gate: each table EvidenceUnit contains a complete table.

    Checks:
      - Text contains at least one <table> open and </table> close tag.
      - Open/close tags are balanced (same count).
      - At least one <tr> row exists.
    """
    table_units = [u for u in units if u.unit_type == "table"]
    issues: list[dict] = []

    for u in table_units:
        open_count = len(_HTML_TABLE_OPEN_RE.findall(u.text))
        close_count = len(_HTML_TABLE_CLOSE_RE.findall(u.text))
        row_count = len(_HTML_ROW_RE.findall(u.text))

        problems: list[str] = []
        if open_count == 0:
            problems.append("no_table_open_tag")
        if close_count == 0:
            problems.append("no_table_close_tag")
        if open_count != close_count:
            problems.append(f"unbalanced_tags(open={open_count},close={close_count})")
        if row_count == 0:
            problems.append("no_rows")

        if problems:
            issues.append({
                "unit_id": u.unit_id[:16],
                "ordering_key": u.ordering_key,
                "open_count": open_count,
                "close_count": close_count,
                "row_count": row_count,
                "problems": problems,
            })

    passed = len(issues) == 0
    detail = {
        "table_unit_count": len(table_units),
        "issue_count": len(issues),
        "issues": issues[:10],
    }

    if not passed:
        logger.warning(
            "Table integrity gate FLAGGED: %d/%d tables with issues",
            len(issues),
            len(table_units),
        )

    return GateDiagnostic(gate_name="table_integrity", passed=passed, detail=detail)


def gate_unit_size(
    units: list[EvidenceUnit],
    *,
    min_chars: int = MIN_UNIT_CHARS,
    max_chars: int = MAX_UNIT_CHARS,
) -> GateDiagnostic:
    """Unit size bounds gate: flag units shorter than *min_chars* or longer than *max_chars*."""
    undersized: list[dict] = []
    oversized: list[dict] = []

    for u in units:
        char_count = len(u.text)
        if char_count < min_chars:
            undersized.append({
                "unit_id": u.unit_id[:16],
                "unit_type": u.unit_type,
                "char_count": char_count,
                "text_preview": u.text[:80],
            })
        elif char_count > max_chars:
            oversized.append({
                "unit_id": u.unit_id[:16],
                "unit_type": u.unit_type,
                "char_count": char_count,
                "text_preview": u.text[:80],
            })

    # Undersized is a warning, not a gate failure.
    # Oversized is a gate failure (indicates segmentation problem).
    passed = len(oversized) == 0
    detail = {
        "total_units": len(units),
        "min_chars": min_chars,
        "max_chars": max_chars,
        "undersized_count": len(undersized),
        "oversized_count": len(oversized),
        "undersized": undersized[:10],
        "oversized": oversized[:10],
    }

    if not passed:
        logger.warning(
            "Unit size gate FAILED: %d oversized units", len(oversized)
        )
    if undersized:
        logger.info("Unit size gate: %d undersized units (warning only)", len(undersized))

    return GateDiagnostic(gate_name="unit_size", passed=passed, detail=detail)


# ---------------------------------------------------------------------------
# Convenience: run all Stage B gates
# ---------------------------------------------------------------------------

def run_stage_b_gates(
    units: list[EvidenceUnit],
    *,
    ast_dict: dict[str, Any] | None = None,
    is_standalone: bool = False,
) -> list[GateDiagnostic]:
    """Run all four Stage B gates on a list of EvidenceUnits."""
    return [
        gate_orphan(units, ast_dict=ast_dict, is_standalone=is_standalone),
        gate_bleed(units),
        gate_table_integrity(units),
        gate_unit_size(units),
    ]

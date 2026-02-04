"""
Stage A gates (M-A2–M-A8). Compute metrics and pass/fail per gate.

Contract: Gates — Proceed to Stage B only if all true.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from extraction.normalize import is_form_part, normalize_block_type
from extraction.schemas import Chunk, DropRecord, MarkerBlock


@dataclass
class GateResult:
    """Single gate: value, threshold, passed."""

    name: str
    value: float
    threshold: str  # e.g. ">= 0.99"
    passed: bool


@dataclass
class GatesReport:
    """All gates and overall pass."""

    results: list[GateResult] = field(default_factory=list)
    passed: bool = False


def _pages_with_blocks(marker_stream: list[MarkerBlock]) -> set[int]:
    return {b.page_index for b in marker_stream}


def _total_pages(marker_stream: list[MarkerBlock]) -> int:
    if not marker_stream:
        return 0
    return max(b.page_index for b in marker_stream) + 1


def m_a2_page_coverage(marker_stream: list[MarkerBlock]) -> float:
    """M-A2: pages_with_blocks / total_pages. Gate ≥ 0.99."""
    total = _total_pages(marker_stream)
    if total == 0:
        return 1.0
    return len(_pages_with_blocks(marker_stream)) / total


def m_a3_block_retention(
    marker_stream: list[MarkerBlock],
    drop_records: list[DropRecord],
    exclude_form_parts: bool = True,
    empty_structural_count: int = 0,
) -> float:
    """M-A3: retained / total. When exclude_form_parts=True, counts only rulebook blocks. Gate ≥ 0.995.
    empty_structural_count: blocks (TableCell/Text with no text) preserved in side-channel; excluded from total so they are not penalized as drops."""
    if exclude_form_parts:
        total = sum(
            1
            for b in marker_stream
            if not is_form_part(b.source_pdf_id or b.doc_id)
        )
        dropped = sum(
            1
            for d in drop_records
            if not is_form_part(d.source_pdf_id)
        )
    else:
        total = len(marker_stream)
        dropped = len(drop_records)
    total = max(0, total - empty_structural_count)
    if total == 0:
        return 1.0
    retained = total - dropped
    return retained / total


def m_a4_span_validity(chunks: list[Chunk]) -> float:
    """M-A4: valid_spans / total_chunks. Gate ≥ 0.999. Valid: 0 <= span_start < span_end <= len(text)."""
    if not chunks:
        return 1.0
    valid = 0
    for c in chunks:
        if 0 <= c.span_start < c.span_end <= len(c.text):
            valid += 1
    return valid / len(chunks)


def m_a5_structural_address(chunks: list[Chunk]) -> float:
    """M-A5: chunks with structural address / total. Contract minimum: doc + page; prefer doc + section_path."""
    if not chunks:
        return 1.0
    with_address = sum(
        1 for c in chunks if c.doc_id and (bool(c.section_path) or c.page_index >= 0)
    )
    return with_address / len(chunks)


def m_a6_unknown_block_rate(marker_stream: list[MarkerBlock]) -> float:
    """M-A6: unknown_blocks / total_blocks. Gate ≤ 0.01."""
    if not marker_stream:
        return 0.0
    unknown = sum(1 for b in marker_stream if normalize_block_type(b.raw_block_type) == "Unknown")
    return unknown / len(marker_stream)


def _blocks_per_page(marker_stream: list[MarkerBlock]) -> list[int]:
    from collections import Counter
    c: Counter[int] = Counter()
    for b in marker_stream:
        c[b.page_index] += 1
    return list(c.values()) if c else [0]


def m_a7_fragmentation(marker_stream: list[MarkerBlock]) -> tuple[float, float, bool]:
    """M-A7: median and p95 of blocks_per_page. Gate: p95 ≤ 5×median."""
    counts = _blocks_per_page(marker_stream)
    if not counts:
        return 0.0, 0.0, True
    counts = sorted(counts)
    n = len(counts)
    median = counts[n // 2] if n else 0
    p95_idx = int(math.ceil(0.95 * n)) - 1
    p95 = counts[max(0, p95_idx)]
    passed = median == 0 or p95 <= 5 * median
    return float(median), float(p95), passed


def _weird_ratio(text: str) -> float:
    """Non-printable or symbol chars / total chars."""
    if not text:
        return 0.0
    total = len(text)
    weird = 0
    for c in text:
        if not c.isalnum() and not c.isspace() and ord(c) < 128:
            weird += 1
        elif ord(c) >= 128 or not c.isprintable():
            weird += 1
    return weird / total


def m_a8_text_entropy(chunks: list[Chunk]) -> float:
    """M-A8: fraction of non-table chunks with weird_ratio ≤ 0.15. Gate ≥ 0.98."""
    if not chunks:
        return 1.0
    candidates = [c for c in chunks if c.block_type != "Table"]
    if not candidates:
        return 1.0
    ok = sum(1 for c in candidates if _weird_ratio(c.text) <= 0.15)
    return ok / len(candidates)


def m_a9_provenance_completeness(chunks: list[Chunk]) -> float:
    """M-A9: fraction of chunks with full A-DOC-INV-4 provenance. Gate = 1.0. Fails on missing fields."""
    if not chunks:
        return 1.0
    complete = sum(
        1
        for c in chunks
        if (
            bool(c.logical_doc_id)
            and bool(c.document_part_id)
            and bool(c.source_pdf_id)
            and c.source_pdf_page_index >= 0
            and c.logical_page_index >= 0
        )
    )
    return complete / len(chunks)


def run_gates(
    marker_stream: list[MarkerBlock],
    chunks: list[Chunk],
    drop_records: list[DropRecord],
    empty_structural_count: int = 0,
) -> GatesReport:
    """Compute all gates M-A2–M-A9 and return report."""
    results: list[GateResult] = []
    # M-A2
    v2 = m_a2_page_coverage(marker_stream)
    results.append(GateResult("M-A2_page_coverage", v2, ">= 0.99", v2 >= 0.99))
    # M-A3
    v3 = m_a3_block_retention(marker_stream, drop_records, empty_structural_count=empty_structural_count)
    results.append(GateResult("M-A3_block_retention", v3, ">= 0.995", v3 >= 0.995))
    # M-A4
    v4 = m_a4_span_validity(chunks)
    results.append(GateResult("M-A4_span_validity", v4, ">= 0.999", v4 >= 0.999))
    # M-A5
    v5 = m_a5_structural_address(chunks)
    results.append(GateResult("M-A5_structural_address", v5, ">= 0.95", v5 >= 0.95))
    # M-A6
    v6 = m_a6_unknown_block_rate(marker_stream)
    results.append(GateResult("M-A6_unknown_block_rate", v6, "<= 0.01", v6 <= 0.01))
    # M-A7
    _med, _p95, pass7 = m_a7_fragmentation(marker_stream)
    results.append(GateResult("M-A7_fragmentation", _p95 / max(_med, 1), "p95 <= 5*median", pass7))
    # M-A8
    v8 = m_a8_text_entropy(chunks)
    results.append(GateResult("M-A8_text_entropy", v8, ">= 0.98", v8 >= 0.98))
    # M-A9: provenance completeness (fail on missing document-part fields)
    v9 = m_a9_provenance_completeness(chunks)
    results.append(GateResult("M-A9_provenance_completeness", v9, "= 1.0", v9 >= 1.0))
    passed = all(r.passed for r in results)
    return GatesReport(results=results, passed=passed)


def gates_report_to_dict(report: GatesReport) -> dict[str, Any]:
    """Serialize GatesReport for JSON output."""
    return {
        "passed": report.passed,
        "results": [
            {"name": r.name, "value": r.value, "threshold": r.threshold, "passed": r.passed}
            for r in report.results
        ],
    }

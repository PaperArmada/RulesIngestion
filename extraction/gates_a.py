"""
Stage A Quality Gates.

Four gates per the Stage A contract:
  1. Coverage   — AST leaf text covers ≥95% of raw markdown content.
  2. Ordering   — Leaf node source_line_start is monotonically increasing.
  3. Table parse — Every HTML <table> in raw markdown has a matching AST table node.
  4. Stability  — (optional, requires two runs) Content hashes match across runs.
"""

from __future__ import annotations

import logging
import re

from extraction.schemas import GateDiagnostic, SurfaceAST

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HTML_TABLE_RE = re.compile(r"<table\b.*?</table>", re.DOTALL | re.IGNORECASE)
_HTML_ROW_RE = re.compile(r"<tr\b", re.IGNORECASE)

# Characters that are structural markdown and should not count toward
# "content" when measuring coverage.
_STRUCTURAL_STRIP_RE = re.compile(
    r"#{1,6}\s+|"          # heading markers
    r"[•\-\*]\s+|"         # list markers
    r">\s?|"               # blockquote markers
    r"!\[.*?\]\(.*?\)|"    # image refs
    r"<[^>]+>|"            # HTML tags
    r"-{3,}|\*{3,}|_{3,}", # horizontal rules
)


def _content_chars(text: str) -> int:
    """Count non-whitespace, non-structural-marker characters."""
    cleaned = _STRUCTURAL_STRIP_RE.sub("", text)
    return len(cleaned.replace(" ", "").replace("\n", "").replace("\t", ""))


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def gate_coverage(
    raw_markdown: str,
    ast: SurfaceAST,
    *,
    threshold: float = 0.95,
) -> GateDiagnostic:
    """Coverage gate: AST text covers ≥ *threshold* of raw markdown content.

    Compares non-structural character counts.  A ratio below *threshold* means
    the AST parser lost content during parsing.

    Collects text from ALL nodes (including headings with children) to avoid
    undercounting — headings are content too.
    """
    raw_chars = _content_chars(raw_markdown)
    all_nodes = ast.root.all_nodes()
    # Collect text from every node that has text (skip root)
    ast_texts = [n.text for n in all_nodes if n.text and n.node_type != "root"]
    ast_chars = sum(_content_chars(t) for t in ast_texts)

    if raw_chars == 0:
        ratio = 1.0  # empty page: vacuously covered
    else:
        ratio = ast_chars / raw_chars

    passed = ratio >= threshold
    detail = {
        "raw_content_chars": raw_chars,
        "ast_content_chars": ast_chars,
        "ratio": round(ratio, 4),
        "threshold": threshold,
    }

    if not passed:
        logger.warning(
            "Coverage gate FAILED: ratio=%.4f (threshold=%.2f)", ratio, threshold
        )

    return GateDiagnostic(gate_name="coverage", passed=passed, detail=detail)


def gate_ordering(ast: SurfaceAST) -> GateDiagnostic:
    """Ordering sanity gate: leaf source_line_start is monotonically increasing.

    Inversions indicate the AST parser reordered content relative to the raw
    markdown, which violates the authorial-surface fidelity contract.
    """
    leaves = [n for n in ast.root.all_nodes() if not n.children and n.node_type != "root"]
    inversions: list[dict] = []
    prev_start = -1

    for leaf in leaves:
        if leaf.source_line_start < prev_start:
            inversions.append({
                "node_type": leaf.node_type,
                "source_line_start": leaf.source_line_start,
                "prev_start": prev_start,
                "text_preview": leaf.text[:80],
            })
        prev_start = leaf.source_line_start

    passed = len(inversions) == 0
    detail = {
        "leaf_count": len(leaves),
        "inversion_count": len(inversions),
        "inversions": inversions[:10],  # cap detail for large pages
    }

    if not passed:
        logger.warning("Ordering gate FAILED: %d inversions", len(inversions))

    return GateDiagnostic(gate_name="ordering", passed=passed, detail=detail)


def gate_table_parse(
    raw_markdown: str,
    ast: SurfaceAST,
) -> GateDiagnostic:
    """Table parse gate: every HTML <table> in raw markdown has a matching AST node.

    Checks that the number of table blocks in the AST equals the number of
    <table> blocks in the raw markdown, and that row counts are plausible.
    """
    raw_tables = _HTML_TABLE_RE.findall(raw_markdown)
    raw_table_count = len(raw_tables)
    raw_row_counts = [len(_HTML_ROW_RE.findall(t)) for t in raw_tables]

    ast_tables = [n for n in ast.root.all_nodes() if n.node_type == "table"]
    ast_table_count = len(ast_tables)
    ast_row_counts = [len(_HTML_ROW_RE.findall(n.text)) for n in ast_tables]

    count_match = raw_table_count == ast_table_count
    # Row-level comparison: each AST table should have same row count as raw.
    # Tolerate small differences (+/- 2 rows) caused by HTML block boundary
    # capture differences between the raw regex and the AST parser.
    row_tolerance = 2
    row_mismatches: list[dict] = []
    for idx, (raw_rc, ast_rc) in enumerate(
        zip(raw_row_counts, ast_row_counts, strict=False)
    ):
        if abs(raw_rc - ast_rc) > row_tolerance:
            row_mismatches.append({
                "table_index": idx,
                "raw_rows": raw_rc,
                "ast_rows": ast_rc,
                "diff": ast_rc - raw_rc,
            })

    passed = count_match and len(row_mismatches) == 0
    detail = {
        "raw_table_count": raw_table_count,
        "ast_table_count": ast_table_count,
        "count_match": count_match,
        "raw_row_counts": raw_row_counts,
        "ast_row_counts": ast_row_counts,
        "row_mismatches": row_mismatches,
    }

    if not passed:
        logger.warning(
            "Table parse gate FAILED: raw=%d ast=%d mismatches=%d",
            raw_table_count,
            ast_table_count,
            len(row_mismatches),
        )

    return GateDiagnostic(gate_name="table_parse", passed=passed, detail=detail)


def gate_stability(
    content_hash_a: str,
    content_hash_b: str,
) -> GateDiagnostic:
    """Stability gate: two OCR runs on the same page image produce the same hash.

    This gate is optional — it requires two separate OCR runs.  Nondeterminism
    is flagged but not necessarily a fatal failure (per Mark III design).
    """
    passed = content_hash_a == content_hash_b
    detail = {
        "hash_a": content_hash_a,
        "hash_b": content_hash_b,
        "match": passed,
    }

    if not passed:
        logger.warning(
            "Stability gate FLAGGED: hashes differ (%s vs %s)",
            content_hash_a[:16],
            content_hash_b[:16],
        )

    return GateDiagnostic(gate_name="stability", passed=passed, detail=detail)


# ---------------------------------------------------------------------------
# Convenience: run all non-optional gates
# ---------------------------------------------------------------------------

def run_stage_a_gates(
    raw_markdown: str,
    ast: SurfaceAST,
) -> list[GateDiagnostic]:
    """Run coverage, ordering, and table_parse gates.  Stability is separate."""
    return [
        gate_coverage(raw_markdown, ast),
        gate_ordering(ast),
        gate_table_parse(raw_markdown, ast),
    ]

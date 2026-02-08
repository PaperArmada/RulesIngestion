"""
Stage B — Evidence Binding.

Converts a SurfaceAST into a flat list of EvidenceUnits with structural
provenance.

Rules:
  - Each leaf node (paragraph, table, list, callout, image_ref) → one EvidenceUnit.
  - Heading nodes are **absorbed**: the heading text is prepended to the first
    child unit's text (separated by " — ").  Headings still extend structural_path
    for all children.  No standalone heading-type EvidenceUnits are emitted.
    If a heading has no children, it emits a heading-type unit as a fallback.
  - Tables are never split.
  - Consecutive paragraphs under the same heading stay as separate units.
  - Monotonic ordering_key across the entire page.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import blake3

from extraction.schemas import EvidenceUnit, GateDiagnostic, SurfaceAST, SurfaceASTNode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Index-page detection
# ---------------------------------------------------------------------------

# Pattern: "word, 123" or "word 123" at the end of a line — typical index entry
_INDEX_ENTRY_RE = re.compile(r",?\s+\d{1,4}\s*$")
# Same pattern but for scanning individual lines within multi-line paragraphs
_INDEX_LINE_RE = re.compile(r",?\s+\d{1,4}\s*$", re.MULTILINE)

# Known index/glossary section headings (case-insensitive)
_INDEX_HEADING_TITLES = {"index", "glossary", "appendix: index"}

# Thresholds for index-page classification
_INDEX_MIN_CHILDREN = 30           # index pages are dense (path A: flat)
_INDEX_MAX_MEDIAN_CHARS = 60       # entries are very short (path A: flat)
_INDEX_ENTRY_HIT_RATIO = 0.40     # ≥40% match page-ref pattern
_INDEX_LINE_HIT_RATIO = 0.40      # ≥40% of lines match (path B: merged)
_INDEX_MIN_LINES = 30             # minimum line count (path B: merged)


def _is_index_page(root: SurfaceASTNode) -> bool:
    """Deterministic classifier: is this AST an index/glossary page?

    Two detection paths:

    Path A (flat structure, e.g. p377-382):
      1. No heading children.
      2. At least _INDEX_MIN_CHILDREN paragraph children.
      3. Median text length ≤ _INDEX_MAX_MEDIAN_CHARS.
      4. ≥ _INDEX_ENTRY_HIT_RATIO of children match page-reference pattern.

    Path B (headed structure, e.g. p376):
      1. Exactly one heading child whose title is a known index heading.
      2. All content under that heading; split into lines.
      3. ≥ _INDEX_MIN_LINES total lines.
      4. ≥ _INDEX_LINE_HIT_RATIO of lines match page-reference pattern.
    """
    children = root.children
    if not children:
        return False

    headings = [c for c in children if c.node_type == "heading"]

    # --- Path B: single known index heading ---
    if len(headings) == 1 and len(children) == 1:
        heading = headings[0]
        title = heading.text.strip().lower()
        if title in _INDEX_HEADING_TITLES:
            # Collect all text from children under this heading
            all_text = "\n".join(
                c.text.strip() for c in heading.children
                if c.text.strip()
            )
            lines = [ln for ln in all_text.split("\n") if ln.strip()]
            if len(lines) >= _INDEX_MIN_LINES:
                hits = sum(1 for ln in lines if _INDEX_LINE_RE.search(ln))
                hit_ratio = hits / len(lines)
                if hit_ratio >= _INDEX_LINE_HIT_RATIO:
                    return True

    # --- Path A: flat structure (no headings) ---
    if headings:
        return False

    paragraphs = [c for c in children if c.node_type == "paragraph"]
    if len(paragraphs) < _INDEX_MIN_CHILDREN:
        return False

    lengths = sorted(len(c.text.strip()) for c in paragraphs)
    median_len = lengths[len(lengths) // 2]
    if median_len > _INDEX_MAX_MEDIAN_CHARS:
        return False

    hits = sum(1 for c in paragraphs if _INDEX_ENTRY_RE.search(c.text.strip()))
    hit_ratio = hits / len(paragraphs)
    if hit_ratio < _INDEX_ENTRY_HIT_RATIO:
        return False

    return True

# Map AST node_type → EvidenceUnit unit_type
_NODE_TYPE_TO_UNIT_TYPE = {
    "heading": "heading",
    "paragraph": "prose",
    "table": "table",
    "list": "list",
    "callout": "callout",
    "sidebar": "callout",      # sidebars treated as callouts
    "footnote": "callout",     # footnotes treated as callouts
    "image_ref": "prose",      # image refs are informational prose
}


def _make_unit_id(text: str, structural_path: list[str]) -> str:
    """Deterministic unit ID: blake3(text + "|" + joined path)."""
    path_str = " > ".join(structural_path)
    payload = f"{text}|{path_str}"
    return blake3.blake3(payload.encode("utf-8")).hexdigest()


def _walk_ast(
    node: SurfaceASTNode,
    path: list[str],
    units: list[EvidenceUnit],
    counter: list[int],          # mutable single-element list for monotonic key
    page_fingerprint: str,
    pending_heading: list[tuple[str, int, int]] | None = None,
) -> None:
    """Depth-first walk, emitting EvidenceUnits for each meaningful node.

    pending_heading: carries a list of (heading_text, line_start, line_end) tuples
    from ancestor headings that have not yet been absorbed into a child unit.
    The first child unit encountered absorbs all pending headings.
    """
    if pending_heading is None:
        pending_heading = []

    if node.node_type == "root":
        for child in node.children:
            _walk_ast(child, path, units, counter, page_fingerprint, pending_heading)
        # If any headings were never absorbed (heading with no children at end of page),
        # emit them as fallback heading-type units.
        _flush_pending_headings(pending_heading, path, units, counter, page_fingerprint)
        return

    if node.node_type == "heading":
        heading_text = node.text.strip()
        if not heading_text:
            for child in node.children:
                _walk_ast(child, path, units, counter, page_fingerprint, pending_heading)
            return

        # Extend structural path for children
        child_path = path + [heading_text]

        if node.children:
            # Heading has children: absorb into first child.
            # Push heading text as pending; first leaf consumes it.
            pending_heading.append((heading_text, node.source_line_start, node.source_line_end))
            for child in node.children:
                _walk_ast(child, child_path, units, counter, page_fingerprint, pending_heading)
        else:
            # Childless heading: push as pending so the next sibling (if any)
            # absorbs it. If nothing absorbs it, _flush emits it.
            pending_heading.append((heading_text, node.source_line_start, node.source_line_end))
        return

    # Leaf node: emit one EvidenceUnit, absorbing any pending headings.
    text = node.text.strip()
    if not text:
        return

    unit_type = _NODE_TYPE_TO_UNIT_TYPE.get(node.node_type, "prose")

    # Absorb pending heading(s): prepend to text, extend source line range
    line_start = node.source_line_start
    line_end = node.source_line_end
    if pending_heading:
        heading_parts = [h[0] for h in pending_heading]
        prefix = " — ".join(heading_parts)
        text = f"{prefix} — {text}"
        # Source range extends back to the earliest pending heading
        line_start = min(line_start, min(h[1] for h in pending_heading))
        pending_heading.clear()

    content_hash = blake3.blake3(text.encode("utf-8")).hexdigest()

    anomaly_flags: list[str] = []
    if len(text) < 20:
        anomaly_flags.append("undersized")
    if len(text) > 5000:
        anomaly_flags.append("oversized")
    if not path:
        anomaly_flags.append("no_heading_parent")

    unit = EvidenceUnit(
        unit_id=_make_unit_id(text, path),
        unit_type=unit_type,
        text=text,
        structural_path=list(path),
        ordering_key=counter[0],
        page_fingerprint=page_fingerprint,
        content_hash=content_hash,
        source_line_start=line_start,
        source_line_end=line_end,
        anomaly_flags=anomaly_flags,
    )
    counter[0] += 1
    units.append(unit)

    # If the leaf somehow has children (shouldn't, but defensive), recurse
    for child in node.children:
        _walk_ast(child, path, units, counter, page_fingerprint, pending_heading)


def _flush_pending_headings(
    pending_heading: list[tuple[str, int, int]],
    path: list[str],
    units: list[EvidenceUnit],
    counter: list[int],
    page_fingerprint: str,
) -> None:
    """Emit any remaining pending headings as fallback heading-type units.

    This handles edge cases like a heading at the very end of a page with no
    subsequent content to absorb it.
    """
    for heading_text, line_start, line_end in pending_heading:
        content_hash = blake3.blake3(heading_text.encode("utf-8")).hexdigest()
        unit = EvidenceUnit(
            unit_id=_make_unit_id(heading_text, path),
            unit_type="heading",
            text=heading_text,
            structural_path=list(path),
            ordering_key=counter[0],
            page_fingerprint=page_fingerprint,
            content_hash=content_hash,
            source_line_start=line_start,
            source_line_end=line_end,
            anomaly_flags=["unabsorbed_heading"],
        )
        counter[0] += 1
        units.append(unit)
    pending_heading.clear()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class StageBResult:
    """Complete output of a Stage B run for one page."""

    units: list[EvidenceUnit]
    gate_diagnostics: list[GateDiagnostic] = field(default_factory=list)

    @property
    def gates_passed(self) -> bool:
        return all(g.passed for g in self.gate_diagnostics)

    @property
    def salvage_score(self) -> float:
        """Fraction of EvidenceUnits without fatal anomaly flags."""
        if not self.units:
            return 1.0
        fatal_flags = {"oversized"}  # only oversized is fatal for now
        clean = sum(
            1
            for u in self.units
            if not (set(u.anomaly_flags) & fatal_flags)
        )
        return clean / len(self.units)

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_count": len(self.units),
            "units": [u.to_dict() for u in self.units],
            "gate_diagnostics": [g.to_dict() for g in self.gate_diagnostics],
            "gates_passed": self.gates_passed,
            "salvage_score": round(self.salvage_score, 4),
        }


def run_stage_b(
    ast: SurfaceAST,
    out_dir: Path | None = None,
) -> StageBResult:
    """Execute Stage B segmentation on a SurfaceAST.

    Args:
        ast: Parsed structural AST from Stage A.
        out_dir: Optional output directory for writing artifacts.

    Returns:
        StageBResult with EvidenceUnits and gate diagnostics.
    """
    # Index-page detection: skip unit emission entirely
    if _is_index_page(ast.root):
        logger.info(
            "Stage B: index page detected (%d AST nodes) — dropping all units",
            ast.node_count,
        )
        result = StageBResult(
            units=[],
            gate_diagnostics=[
                GateDiagnostic(
                    gate_name="index_page",
                    passed=True,
                    detail={
                        "classified_as": "index",
                        "node_count": ast.node_count,
                        "note": "index/glossary page — no EvidenceUnits emitted",
                    },
                )
            ],
        )
        if out_dir is not None:
            _write_artifacts(out_dir, result)
        return result

    units: list[EvidenceUnit] = []
    counter = [0]  # mutable for closure

    _walk_ast(ast.root, [], units, counter, ast.page_fingerprint)

    logger.info(
        "Stage B: %d EvidenceUnits from %d AST nodes",
        len(units),
        ast.node_count,
    )

    # Gates are run separately (gates_b.py) and injected by the pipeline
    result = StageBResult(units=units, gate_diagnostics=[])

    if out_dir is not None:
        _write_artifacts(out_dir, result)

    return result


def _write_artifacts(out_dir: Path, result: StageBResult) -> None:
    """Write Stage B output artifacts to disk."""
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # stageB.evidence_units.json
    units_json = out_dir / "stageB.evidence_units.json"
    units_json.write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("Stage B artifacts written to %s", out_dir)

"""
Stage B — Evidence Binding (Minimal Segmenter).

Converts a SurfaceAST into a flat list of EvidenceUnits with structural
provenance.  Intentionally naive — no merging heuristics, no semantic
interpretation.  The goal is to discover failure modes, not optimise.

Rules:
  - Each leaf node (paragraph, table, list, callout, image_ref) → one EvidenceUnit.
  - Heading nodes → one heading-type EvidenceUnit AND structural_path context
    for their children.
  - Tables are never split.
  - Consecutive paragraphs under the same heading stay as separate units.
  - Monotonic ordering_key across the entire page.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import blake3

from extraction.schemas import EvidenceUnit, GateDiagnostic, SurfaceAST, SurfaceASTNode

logger = logging.getLogger(__name__)

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
) -> None:
    """Depth-first walk, emitting EvidenceUnits for each meaningful node."""
    if node.node_type == "root":
        for child in node.children:
            _walk_ast(child, path, units, counter, page_fingerprint)
        return

    if node.node_type == "heading":
        # Emit a heading-type EvidenceUnit
        if node.text.strip():
            unit_type = "heading"
            text = node.text.strip()
            content_hash = blake3.blake3(text.encode("utf-8")).hexdigest()
            unit = EvidenceUnit(
                unit_id=_make_unit_id(text, path),
                unit_type=unit_type,
                text=text,
                structural_path=list(path),
                ordering_key=counter[0],
                page_fingerprint=page_fingerprint,
                content_hash=content_hash,
                source_line_start=node.source_line_start,
                source_line_end=node.source_line_end,
                anomaly_flags=[],
            )
            counter[0] += 1
            units.append(unit)

        # Headings extend the path for their children
        child_path = path + [node.text.strip()] if node.text.strip() else path
        for child in node.children:
            _walk_ast(child, child_path, units, counter, page_fingerprint)
        return

    # Leaf node: emit one EvidenceUnit
    text = node.text.strip()
    if not text:
        return

    unit_type = _NODE_TYPE_TO_UNIT_TYPE.get(node.node_type, "prose")
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
        source_line_start=node.source_line_start,
        source_line_end=node.source_line_end,
        anomaly_flags=anomaly_flags,
    )
    counter[0] += 1
    units.append(unit)

    # If the leaf somehow has children (shouldn't, but defensive), recurse
    for child in node.children:
        _walk_ast(child, path, units, counter, page_fingerprint)


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

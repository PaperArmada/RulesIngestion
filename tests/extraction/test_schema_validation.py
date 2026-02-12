"""Schema validation tests for v1 artifact schemas (Stage A, Stage B)."""

from __future__ import annotations

import json
import pytest

from extraction.schemas import (
    EvidenceUnit,
    SurfaceAST,
    SurfaceASTNode,
)


# ---------------------------------------------------------------------------
# EvidenceUnit schema
# ---------------------------------------------------------------------------


def test_evidence_unit_roundtrip() -> None:
    """EvidenceUnit to_dict/from_dict round-trip and required fields."""
    unit = EvidenceUnit(
        unit_id="u1",
        unit_type="prose",
        text="Sample text.",
        structural_path=["Chapter", "Section"],
        ordering_key=0,
        page_fingerprint="fp1",
        content_hash="ch1",
        source_line_start=0,
        source_line_end=2,
        anomaly_flags=[],
    )
    d = unit.to_dict()
    assert "unit_id" in d and "structural_path" in d and "ordering_key" in d
    restored = EvidenceUnit.from_dict(d)
    assert restored.unit_id == unit.unit_id
    assert restored.structural_path == unit.structural_path
    assert restored.text == unit.text


def test_evidence_unit_required_fields() -> None:
    """EvidenceUnit requires unit_id, unit_type, text, structural_path, ordering_key, page_fingerprint, content_hash."""
    minimal = {
        "unit_id": "x",
        "unit_type": "prose",
        "text": "t",
        "structural_path": [],
        "ordering_key": 0,
        "page_fingerprint": "p",
        "content_hash": "c",
        "source_line_start": 0,
        "source_line_end": 0,
        "anomaly_flags": [],
    }
    u = EvidenceUnit.from_dict(minimal)
    assert u.unit_id == "x"


# ---------------------------------------------------------------------------
# Stage A schemas (SurfaceAST, SurfaceASTNode)
# ---------------------------------------------------------------------------


def test_surface_ast_node_roundtrip() -> None:
    """SurfaceASTNode to_dict/from_dict round-trip."""
    node = SurfaceASTNode(
        node_type="paragraph",
        level=0,
        text="Hello",
        children=[],
        source_line_start=0,
        source_line_end=1,
    )
    d = node.to_dict()
    restored = SurfaceASTNode.from_dict(d)
    assert restored.node_type == node.node_type
    assert restored.text == node.text


def test_surface_ast_roundtrip() -> None:
    """SurfaceAST to_dict/from_dict round-trip."""
    root = SurfaceASTNode(node_type="root", level=0, text="", children=[], source_line_start=0, source_line_end=0)
    ast = SurfaceAST(page_fingerprint="fp", content_hash="ch", root=root, node_count=1, table_count=0)
    d = ast.to_dict()
    restored = SurfaceAST.from_dict(d)
    assert restored.page_fingerprint == ast.page_fingerprint
    assert restored.node_count == ast.node_count

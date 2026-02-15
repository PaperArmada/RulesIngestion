from __future__ import annotations

import blake3
import pytest
from pathlib import Path

from extraction.schemas import EvidenceUnit, SurfaceAST, SurfaceASTNode


@pytest.fixture
def sample_evidence_unit() -> EvidenceUnit:
    text = "Attack action lets you make one melee or ranged attack."
    return EvidenceUnit(
        unit_id="u1",
        unit_type="prose",
        text=text,
        structural_path=["Combat", "Actions"],
        ordering_key=0,
        page_fingerprint="fp-page-1",
        content_hash=blake3.blake3(text.encode("utf-8")).hexdigest(),
        source_line_start=1,
        source_line_end=3,
        anomaly_flags=[],
    )


@pytest.fixture
def simple_surface_ast() -> SurfaceAST:
    heading = SurfaceASTNode(
        node_type="heading",
        level=2,
        text="Actions",
        children=[
            SurfaceASTNode(
                node_type="paragraph",
                level=0,
                text="You can move and take one action on your turn.",
                source_line_start=3,
                source_line_end=4,
            ),
            SurfaceASTNode(
                node_type="paragraph",
                level=0,
                text="Attack is a common action.",
                source_line_start=5,
                source_line_end=6,
            ),
        ],
        source_line_start=2,
        source_line_end=2,
    )
    root = SurfaceASTNode(
        node_type="root",
        level=0,
        text="",
        children=[heading],
        source_line_start=0,
        source_line_end=6,
    )
    return SurfaceAST(
        page_fingerprint="fp-page-1",
        content_hash=blake3.blake3(b"ast").hexdigest(),
        root=root,
        node_count=4,
        table_count=0,
    )


@pytest.fixture
def query_batch_minimal_path() -> Path:
    return (
        Path(__file__).resolve().parent
        / "retrieval_lab"
        / "fixtures"
        / "minimal_query_batch.json"
    )


@pytest.fixture
def substrate_minimal_path() -> Path:
    return (
        Path(__file__).resolve().parent
        / "retrieval_lab"
        / "fixtures"
        / "minimal_substrate"
    )

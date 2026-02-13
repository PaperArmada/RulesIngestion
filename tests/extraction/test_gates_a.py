from __future__ import annotations

import blake3

from extraction.gates_a import gate_coverage, gate_ordering, gate_table_parse
from extraction.schemas import SurfaceAST, SurfaceASTNode


def _ast_with_nodes(nodes: list[SurfaceASTNode]) -> SurfaceAST:
    root = SurfaceASTNode(node_type="root", level=0, text="", children=nodes, source_line_start=0, source_line_end=50)
    return SurfaceAST(
        page_fingerprint="fp-1",
        content_hash=blake3.blake3(b"ast").hexdigest(),
        root=root,
        node_count=len(root.all_nodes()),
        table_count=sum(1 for n in root.all_nodes() if n.node_type == "table"),
    )


def test_gate_coverage_passes_for_matching_content() -> None:
    raw = "## Actions\nAttack lets you make one attack."
    ast = _ast_with_nodes(
        [SurfaceASTNode(node_type="paragraph", level=0, text="Attack lets you make one attack.", source_line_start=1, source_line_end=2)]
    )
    diag = gate_coverage(raw, ast, threshold=0.5)
    assert diag.passed


def test_gate_ordering_flags_inversions() -> None:
    ast = _ast_with_nodes(
        [
            SurfaceASTNode(node_type="paragraph", level=0, text="A", source_line_start=10, source_line_end=11),
            SurfaceASTNode(node_type="paragraph", level=0, text="B", source_line_start=2, source_line_end=3),
        ]
    )
    diag = gate_ordering(ast)
    assert not diag.passed
    assert diag.detail["inversion_count"] == 1


def test_gate_table_parse_detects_missing_table_node() -> None:
    raw = "<table><tr><td>A</td></tr></table>"
    ast = _ast_with_nodes(
        [SurfaceASTNode(node_type="paragraph", level=0, text="No table", source_line_start=1, source_line_end=2)]
    )
    diag = gate_table_parse(raw, ast)
    assert not diag.passed
    assert diag.detail["raw_table_count"] == 1

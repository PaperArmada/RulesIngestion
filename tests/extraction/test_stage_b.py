from __future__ import annotations

from extraction.stage_b import run_stage_b
from extraction.unit_identity import compute_evidence_unit_id


def test_stage_b_absorbs_heading_into_first_child(simple_surface_ast) -> None:
    result = run_stage_b(simple_surface_ast)
    assert len(result.units) == 2
    assert result.units[0].text.startswith("Actions —")
    assert result.units[0].structural_path == ["Actions"]
    assert result.units[1].structural_path == ["Actions"]


def test_stage_b_ordering_keys_are_monotonic(simple_surface_ast) -> None:
    result = run_stage_b(simple_surface_ast)
    ordering = [u.ordering_key for u in result.units]
    assert ordering == sorted(ordering)


def test_evidence_unit_identity_uses_page_local_provenance() -> None:
    first_id = compute_evidence_unit_id(
        text="The target is prone.",
        structural_path=["Combat", "Prone"],
        page_fingerprint="page-a",
        source_line_start=10,
        source_line_end=12,
        unit_type="prose",
    )
    second_id = compute_evidence_unit_id(
        text="The target is prone.",
        structural_path=["Combat", "Prone"],
        page_fingerprint="page-b",
        source_line_start=10,
        source_line_end=12,
        unit_type="prose",
    )

    assert first_id != second_id

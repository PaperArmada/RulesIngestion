from __future__ import annotations

from extraction.gates_b import (
    gate_bleed,
    gate_join_page_fingerprint_conservation,
    gate_join_table_unit_conservation,
    gate_join_unit_id_conservation,
    gate_orphan,
    gate_table_integrity,
    gate_unit_size,
    run_stage_b_gates,
)
from extraction.schemas import EvidenceUnit


def _unit(
    unit_id: str,
    *,
    text: str,
    structural_path: list[str],
    start: int,
    end: int,
    unit_type: str = "prose",
) -> EvidenceUnit:
    return EvidenceUnit(
        unit_id=unit_id,
        unit_type=unit_type,  # type: ignore[arg-type]
        text=text,
        structural_path=structural_path,
        ordering_key=start,
        page_fingerprint="fp-1",
        content_hash="h",
        source_line_start=start,
        source_line_end=end,
        anomaly_flags=[],
    )


def test_gate_orphan_flags_empty_paths() -> None:
    units = [_unit("u1", text="abc", structural_path=[], start=0, end=1), _unit("u2", text="def", structural_path=["A"], start=2, end=3)]
    diag = gate_orphan(units, fail_threshold=0.4)
    assert not diag.passed
    assert diag.detail["orphan_count"] == 1


def test_gate_bleed_detects_overlap() -> None:
    units = [_unit("u1", text="abc", structural_path=["A"], start=0, end=4), _unit("u2", text="def", structural_path=["A"], start=3, end=6)]
    diag = gate_bleed(units)
    assert not diag.passed
    assert diag.detail["overlap_count"] == 1


def test_gate_table_integrity_fails_on_unbalanced_table() -> None:
    table = _unit("t1", text="<table><tr><td>A</td></tr>", structural_path=["A"], start=0, end=4, unit_type="table")
    diag = gate_table_integrity([table])
    assert not diag.passed
    assert diag.detail["issue_count"] == 1


def test_gate_unit_size_allows_large_complete_tables_under_table_cap() -> None:
    large_table = _unit(
        "t1",
        text="<table>" + ("<tr><td>row</td></tr>" * 300) + "</table>",
        structural_path=["Equipment"],
        start=0,
        end=4,
        unit_type="table",
    )

    diag = gate_unit_size([large_table])

    assert diag.passed
    assert diag.detail["oversized_count"] == 0


def test_run_stage_b_gates_includes_contract_order() -> None:
    units = [_unit("u1", text="valid text for gate checks", structural_path=["A"], start=0, end=1)]
    diagnostics = run_stage_b_gates(units)
    assert [d.gate_name for d in diagnostics] == ["orphan", "bleed", "table_integrity", "unit_size"]


def test_join_unit_id_conservation_fails_on_missing_stage_b_id() -> None:
    stage_b_units = [
        _unit("u1", text="x", structural_path=["A"], start=0, end=1),
        _unit("u2", text="y", structural_path=["A"], start=1, end=2),
    ]
    joined_units = [
        _unit("u1", text="x merged", structural_path=["A"], start=0, end=2),
    ]
    joined_units[0].source_unit_ids = ["u1"]
    diag = gate_join_unit_id_conservation(stage_b_units, joined_units)
    assert not diag.passed
    assert diag.detail["missing_unit_count"] == 1


def test_join_page_fingerprint_conservation_fails_on_missing_page() -> None:
    stage_b_units = [
        _unit("u1", text="x", structural_path=["A"], start=0, end=1),
        _unit("u2", text="y", structural_path=["A"], start=1, end=2),
    ]
    stage_b_units[0].page_fingerprint = "fp-1"
    stage_b_units[1].page_fingerprint = "fp-2"
    joined_units = [_unit("u1", text="x", structural_path=["A"], start=0, end=1)]
    joined_units[0].page_fingerprint = "fp-1"
    joined_units[0].source_unit_ids = ["u1", "u2"]
    diag = gate_join_page_fingerprint_conservation(stage_b_units, joined_units)
    assert not diag.passed
    assert diag.detail["missing_fingerprint_count"] == 1


def test_join_table_unit_conservation_fails_on_missing_table() -> None:
    stage_b_units = [
        _unit("t1", text="<table><tr><td>a</td></tr></table>", structural_path=["A"], start=0, end=1, unit_type="table"),
        _unit("u2", text="y", structural_path=["A"], start=1, end=2),
    ]
    joined_units = [_unit("u2", text="y", structural_path=["A"], start=1, end=2)]
    joined_units[0].source_unit_ids = ["u2"]
    diag = gate_join_table_unit_conservation(stage_b_units, joined_units)
    assert not diag.passed
    assert diag.detail["missing_table_unit_count"] == 1

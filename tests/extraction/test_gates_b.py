from __future__ import annotations

from extraction.gates_b import gate_bleed, gate_orphan, gate_table_integrity, run_stage_b_gates
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


def test_run_stage_b_gates_includes_contract_order() -> None:
    units = [_unit("u1", text="valid text for gate checks", structural_path=["A"], start=0, end=1)]
    diagnostics = run_stage_b_gates(units)
    assert [d.gate_name for d in diagnostics] == ["orphan", "bleed", "table_integrity", "unit_size"]

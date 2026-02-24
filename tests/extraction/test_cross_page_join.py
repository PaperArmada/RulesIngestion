from __future__ import annotations

from extraction.cross_page_join import run_join_pass
from extraction.schemas import EvidenceUnit


def _unit(
    unit_id: str,
    *,
    text: str,
    page_fp: str,
    ordering_key: int,
    unit_type: str = "prose",
    structural_path: list[str] | None = None,
) -> EvidenceUnit:
    return EvidenceUnit(
        unit_id=unit_id,
        unit_type=unit_type,  # type: ignore[arg-type]
        text=text,
        structural_path=structural_path or ["Section"],
        ordering_key=ordering_key,
        page_fingerprint=page_fp,
        content_hash=f"h-{unit_id}",
        source_line_start=ordering_key,
        source_line_end=ordering_key + 1,
        anomaly_flags=[],
    )


def test_join_pass_preserves_source_unit_ids_for_passthrough_and_merged() -> None:
    # p1 prose joins to p2 prose under same structural path.
    page1 = [_unit("u1", text="Part one", page_fp="fp1", ordering_key=0)]
    page2 = [_unit("u2", text="Part two", page_fp="fp2", ordering_key=1)]
    joined = run_join_pass([page1, page2])
    assert len(joined) == 1
    merged = joined[0]
    assert merged.unit_id == "u1"
    assert merged.source_unit_ids == ["u1", "u2"]
    assert "cross_page_join" in merged.anomaly_flags


def test_join_pass_preserves_passthrough_source_unit_ids() -> None:
    # No join candidate: structural paths differ, both units pass through.
    page1 = [_unit("u1", text="Alpha", page_fp="fp1", ordering_key=0, structural_path=["A"])]
    page2 = [_unit("u2", text="Beta", page_fp="fp2", ordering_key=1, structural_path=["B"])]
    joined = run_join_pass([page1, page2])
    assert len(joined) == 2
    assert joined[0].source_unit_ids == ["u1"]
    assert joined[1].source_unit_ids == ["u2"]

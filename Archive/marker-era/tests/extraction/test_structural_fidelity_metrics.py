"""Tests for extraction.structural_fidelity_metrics: M-A9, M-A10, M-A11."""

from extraction.structural_fidelity_metrics import (
    compute_column_jump_structural_divergence,
    compute_rule_outcome_misassignment_rate,
    compute_structural_continuity_violation_rate,
    compute_all_structural_fidelity_metrics,
)
from extraction.schemas import Chunk, MarkerBlock


def _block(
    page: int = 0,
    text: str = "Some text",
    raw_type: str = "Text",
    ordinal: int = 0,
    section_hierarchy: dict | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> MarkerBlock:
    return MarkerBlock(
        doc_id="d1",
        page_index=page,
        text=text,
        bbox=bbox or (0.0, 0.0, 100.0, 20.0),
        raw_block_type=raw_type,
        block_ordinal=ordinal,
        section_hierarchy=section_hierarchy or {},
    )


def _chunk(
    text: str = "hello",
    section_path: list[str] | None = None,
    block_type: str = "Text",
    page_index: int = 0,
) -> Chunk:
    return Chunk(
        chunk_id="c1",
        doc_id="d1",
        page_index=page_index,
        section_path=section_path or ["Ch1"],
        block_type=block_type,
        text=text,
        span_start=0,
        span_end=len(text),
        span_locality="block",
        bbox=(0, 0, 0, 0),
        block_ordinals=[0],
    )


# --- M-A9: Structural continuity violation rate ---


def test_m_a9_same_l1_no_violation() -> None:
    """Two adjacent prose blocks, same L1 → 0 violations."""
    stream = [
        _block(ordinal=0, section_hierarchy={"1": "/page/1/SectionHeader/1"}, bbox=(10, 10, 90, 25)),
        _block(ordinal=1, section_hierarchy={"1": "/page/1/SectionHeader/1"}, bbox=(10, 30, 90, 45)),
    ]
    out = compute_structural_continuity_violation_rate(stream)
    assert out["eligible_pairs"] == 1
    assert out["violations"] == 0
    assert out["rate"] == 0.0


def test_m_a9_different_l1_small_distance_continuation_cue_violation() -> None:
    """Two adjacent prose blocks, different L1, small vertical distance, second starts with 'Failure' → 1 violation."""
    stream = [
        _block(ordinal=0, section_hierarchy={"1": "/page/1/SectionHeader/1"}, bbox=(10, 10, 90, 25)),
        _block(ordinal=1, text="Failure You do something.", section_hierarchy={"1": "/page/1/SectionHeader/2"}, bbox=(10, 32, 90, 47)),
    ]
    out = compute_structural_continuity_violation_rate(stream, max_vertical_pt=50.0)
    assert out["eligible_pairs"] == 1
    assert out["violations"] == 1
    assert out["rate"] == 1.0


def test_m_a9_large_vertical_distance_no_violation() -> None:
    """Two adjacent prose blocks, different L1, but large vertical distance → 0 violations (not same flow)."""
    stream = [
        _block(ordinal=0, section_hierarchy={"1": "/page/1/SectionHeader/1"}, bbox=(10, 10, 90, 25)),
        _block(ordinal=1, text="Failure outcome.", section_hierarchy={"1": "/page/1/SectionHeader/2"}, bbox=(10, 200, 90, 215)),
    ]
    out = compute_structural_continuity_violation_rate(stream, max_vertical_pt=50.0)
    assert out["eligible_pairs"] == 1
    assert out["violations"] == 0
    assert out["rate"] == 0.0


def test_m_a9_no_eligible_pairs_rate_zero() -> None:
    """No eligible pairs → rate 0, no division by zero."""
    stream = [
        _block(ordinal=0, raw_type="Heading", section_hierarchy={"1": "/page/1/SectionHeader/1"}),
        _block(ordinal=1, raw_type="Heading", section_hierarchy={"1": "/page/1/SectionHeader/2"}),
    ]
    out = compute_structural_continuity_violation_rate(stream)
    assert out["eligible_pairs"] == 0
    assert out["violations"] == 0
    assert out["rate"] == 0.0


def test_m_a9_empty_stream() -> None:
    out = compute_structural_continuity_violation_rate([])
    assert out["eligible_pairs"] == 0
    assert out["violations"] == 0
    assert out["rate"] == 0.0


# --- M-A10: Rule outcome misassignment rate ---


def test_m_a10_heading_then_outcome_same_l1_zero_misassigned() -> None:
    """Heading then outcome chunk same L1 → 0 misassigned."""
    chunks = [
        _chunk(text="Some rule", section_path=["/page/5/SectionHeader/3"], block_type="Heading", page_index=5),
        _chunk(text="Success You do it.", section_path=["/page/5/SectionHeader/3"], page_index=5),
    ]
    out = compute_rule_outcome_misassignment_rate(chunks)
    assert out["outcome_chunks_with_header"] == 1
    assert out["misassigned_count"] == 0
    assert out["rate"] == 0.0


def test_m_a10_heading_then_outcome_different_l1_one_misassigned() -> None:
    """Heading then outcome chunk different L1 → 1 misassigned."""
    chunks = [
        _chunk(text="Rule header", section_path=["/page/5/SectionHeader/3"], block_type="Heading", page_index=5),
        _chunk(text="Failure You fail.", section_path=["/page/5/SectionHeader/7"], page_index=5),
    ]
    out = compute_rule_outcome_misassignment_rate(chunks)
    assert out["outcome_chunks_with_header"] == 1
    assert out["misassigned_count"] == 1
    assert out["rate"] == 1.0


def test_m_a10_outcome_with_no_preceding_heading_excluded() -> None:
    """Outcome chunk with no preceding heading → excluded from rate."""
    chunks = [
        _chunk(text="Success You do it.", section_path=["/page/5/SectionHeader/3"], page_index=5),
    ]
    out = compute_rule_outcome_misassignment_rate(chunks)
    assert out["outcome_chunks_with_header"] == 0
    assert out["misassigned_count"] == 0
    assert out["rate"] == 0.0


def test_m_a10_heading_too_far_back_excluded() -> None:
    """Outcome on page 10, last heading on page 8 with max_page_gap=1 → excluded."""
    chunks = [
        _chunk(text="Rule", section_path=["L1"], block_type="Heading", page_index=8),
        _chunk(text="Failure text", section_path=["L2"], page_index=10),
    ]
    out = compute_rule_outcome_misassignment_rate(chunks, max_page_gap=1)
    assert out["outcome_chunks_with_header"] == 0
    assert out["misassigned_count"] == 0


def test_m_a10_empty_chunks() -> None:
    out = compute_rule_outcome_misassignment_rate([])
    assert out["outcome_chunks_with_header"] == 0
    assert out["misassigned_count"] == 0
    assert out["rate"] == 0.0


# --- M-A11: Column jump structural divergence ---


def test_m_a11_column_jump_same_l1_no_path_change() -> None:
    """Same page, large x gap, same L1 → column_jump but no path change counted."""
    stream = [
        _block(ordinal=0, section_hierarchy={"1": "/page/1/SectionHeader/1"}, bbox=(10, 10, 90, 25)),
        _block(ordinal=1, section_hierarchy={"1": "/page/1/SectionHeader/1"}, bbox=(350, 10, 430, 25)),
    ]
    out = compute_column_jump_structural_divergence(stream, column_width_threshold_pt=200.0)
    assert out["column_jump_count"] == 1
    assert out["column_jump_and_path_change_count"] == 0
    assert out["rate"] == 0.0


def test_m_a11_column_jump_different_l1_path_change() -> None:
    """Same page, large x gap, different L1 → column jump and path change."""
    stream = [
        _block(ordinal=0, section_hierarchy={"1": "/page/1/SectionHeader/1"}, bbox=(10, 10, 90, 25)),
        _block(ordinal=1, section_hierarchy={"1": "/page/1/SectionHeader/2"}, bbox=(350, 10, 430, 25)),
    ]
    out = compute_column_jump_structural_divergence(stream, column_width_threshold_pt=200.0)
    assert out["column_jump_count"] == 1
    assert out["column_jump_and_path_change_count"] == 1
    assert out["rate"] == 1.0


def test_m_a11_no_column_jump_not_counted() -> None:
    """Small x gap → not a column jump."""
    stream = [
        _block(ordinal=0, section_hierarchy={"1": "L1"}, bbox=(10, 10, 90, 25)),
        _block(ordinal=1, section_hierarchy={"1": "L2"}, bbox=(100, 10, 180, 25)),
    ]
    out = compute_column_jump_structural_divergence(stream, column_width_threshold_pt=200.0)
    assert out["column_jump_count"] == 0
    assert out["column_jump_and_path_change_count"] == 0
    assert out["rate"] == 0.0


def test_m_a11_different_pages_ignored() -> None:
    """Adjacent blocks on different pages are not considered for column jump."""
    stream = [
        _block(page=0, ordinal=0, section_hierarchy={"1": "L1"}, bbox=(10, 10, 90, 25)),
        _block(page=1, ordinal=0, section_hierarchy={"1": "L2"}, bbox=(350, 10, 430, 25)),
    ]
    out = compute_column_jump_structural_divergence(stream, column_width_threshold_pt=200.0)
    assert out["column_jump_count"] == 0


def test_m_a11_zero_column_jumps_rate_zero() -> None:
    out = compute_column_jump_structural_divergence([_block(), _block(ordinal=1)])
    assert out["column_jump_count"] == 0
    assert out["rate"] == 0.0


# --- compute_all_structural_fidelity_metrics ---


def test_compute_all_returns_three_keys() -> None:
    stream = [_block(ordinal=0), _block(ordinal=1)]
    chunks = [_chunk()]
    out = compute_all_structural_fidelity_metrics(stream, chunks)
    assert "M_A9_structural_continuity_violation_rate" in out
    assert "M_A10_rule_outcome_misassignment_rate" in out
    assert "M_A11_column_jump_structural_divergence" in out
    assert "rate" in out["M_A9_structural_continuity_violation_rate"]
    assert "rate" in out["M_A10_rule_outcome_misassignment_rate"]
    assert "rate" in out["M_A11_column_jump_structural_divergence"]

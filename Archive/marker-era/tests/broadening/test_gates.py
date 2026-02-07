"""Tests for broadening.gates module."""

from __future__ import annotations

import pytest

from broadening.gates import (
    M_B1_P10_MIN_CHARS,
    M_B2_FRAGMENT_THRESHOLD,
    M_B3_OVERBROAD_THRESHOLD,
    M_B3_MAX_CHARS,
    m_b1_size_distribution,
    m_b2_fragment_rate,
    m_b3_overbroad_rate,
    m_b4_structural_violations,
    m_b5_grouping_rule_coverage,
    m_b6_stop_reason_distribution,
    run_gates,
)
from broadening.schemas import (
    EvidenceChunk,
    GroupingRule,
    GroupingStopReason,
    SourceSpan,
)


def _make_evidence_chunk(
    evidence_chunk_id: str = "ec1",
    kind: str = "Prose",
    text: str = "A" * 500,  # Default to good size
    grouping_rule_id: str = GroupingRule.PARAGRAPH_RUN.value,
    grouping_stop_reason: str = GroupingStopReason.END_OF_SECTION.value,
    section_path: list[str] | None = None,
    page_indices: list[int] | None = None,
) -> EvidenceChunk:
    """Helper to create EvidenceChunk for testing."""
    if section_path is None:
        section_path = ["Chapter 1"]
    if page_indices is None:
        page_indices = [0]

    return EvidenceChunk(
        evidence_chunk_id=evidence_chunk_id,
        kind=kind,
        text=text,
        source_chunk_ids=["c1"],
        source_spans=[SourceSpan(chunk_id="c1", page_index=0, span_start=0, span_end=len(text))],
        logical_doc_id="doc1",
        grouping_rule_id=grouping_rule_id,
        grouping_stop_reason=grouping_stop_reason,
        section_path=section_path,
        page_indices=page_indices,
    )


class TestMB1SizeDistribution:
    """Tests for M-B1 size distribution gate."""

    def test_empty_chunks_passes(self) -> None:
        """Empty input should pass."""
        result = m_b1_size_distribution([])
        assert result.passed is True

    def test_good_size_distribution_passes(self) -> None:
        """Chunks with good sizes should pass."""
        chunks = [
            _make_evidence_chunk(evidence_chunk_id=f"ec{i}", text="A" * 600)
            for i in range(10)
        ]
        result = m_b1_size_distribution(chunks)
        assert result.passed is True

    def test_small_chunks_fail_p10(self) -> None:
        """Chunks below p10 threshold should fail."""
        # 10 chunks, all small
        chunks = [
            _make_evidence_chunk(evidence_chunk_id=f"ec{i}", text="A" * 100)
            for i in range(10)
        ]
        result = m_b1_size_distribution(chunks)
        assert result.passed is False

    def test_tabular_chunks_excluded(self) -> None:
        """Tabular chunks should not affect Prose metrics."""
        chunks = [
            _make_evidence_chunk(evidence_chunk_id="ec1", kind="Tabular", text="A" * 50),
        ]
        result = m_b1_size_distribution(chunks)
        # No prose chunks, should pass
        assert result.passed is True


class TestMB2FragmentRate:
    """Tests for M-B2 fragment rate gate."""

    def test_empty_chunks_passes(self) -> None:
        """Empty input should pass."""
        result = m_b2_fragment_rate([])
        assert result.passed is True

    def test_no_fragments_passes(self) -> None:
        """No fragments should pass."""
        chunks = [
            _make_evidence_chunk(evidence_chunk_id=f"ec{i}", text="A" * 500)
            for i in range(10)
        ]
        result = m_b2_fragment_rate(chunks)
        assert result.passed is True
        assert result.value == 0.0

    def test_too_many_fragments_fails(self) -> None:
        """Too many fragments should fail."""
        # 5 fragments out of 10 = 50% > 2%
        chunks = [
            _make_evidence_chunk(evidence_chunk_id=f"ec{i}", text="A" * 100)
            for i in range(5)
        ] + [
            _make_evidence_chunk(evidence_chunk_id=f"ec{i+5}", text="A" * 500)
            for i in range(5)
        ]
        result = m_b2_fragment_rate(chunks)
        assert result.passed is False


class TestMB3OverbroadRate:
    """Tests for M-B3 over-broad rate gate."""

    def test_empty_chunks_passes(self) -> None:
        """Empty input should pass."""
        result = m_b3_overbroad_rate([])
        assert result.passed is True

    def test_no_overbroad_passes(self) -> None:
        """No over-broad chunks should pass."""
        chunks = [
            _make_evidence_chunk(evidence_chunk_id=f"ec{i}", text="A" * 1000)
            for i in range(10)
        ]
        result = m_b3_overbroad_rate(chunks)
        assert result.passed is True
        assert result.value == 0.0

    def test_too_many_overbroad_fails(self) -> None:
        """Too many over-broad chunks should fail."""
        # 10 over-broad out of 10 = 100% > 5%
        chunks = [
            _make_evidence_chunk(evidence_chunk_id=f"ec{i}", text="A" * 3000)
            for i in range(10)
        ]
        result = m_b3_overbroad_rate(chunks)
        assert result.passed is False


class TestMB4StructuralViolations:
    """Tests for M-B4 structural violations gate."""

    def test_empty_chunks_passes(self) -> None:
        """Empty input should pass."""
        result = m_b4_structural_violations([])
        assert result.passed is True

    def test_no_violations_passes(self) -> None:
        """No violations should pass."""
        chunks = [
            _make_evidence_chunk(evidence_chunk_id="ec1", section_path=["Ch1"], page_indices=[0]),
        ]
        result = m_b4_structural_violations(chunks)
        assert result.passed is True

    def test_too_many_pages_violation(self) -> None:
        """Spanning too many pages should be a violation."""
        chunks = [
            _make_evidence_chunk(
                evidence_chunk_id="ec1",
                page_indices=[0, 1, 2, 3, 4],  # 5 pages
            ),
        ]
        result = m_b4_structural_violations(chunks)
        assert result.passed is False
        assert result.value == 1


class TestMB5GroupingRuleCoverage:
    """Tests for M-B5 grouping rule coverage gate."""

    def test_empty_chunks_passes(self) -> None:
        """Empty input should pass."""
        result = m_b5_grouping_rule_coverage([])
        assert result.passed is True

    def test_balanced_coverage_passes(self) -> None:
        """Balanced rule coverage should pass."""
        chunks = [
            _make_evidence_chunk(
                evidence_chunk_id=f"ec{i}",
                grouping_rule_id=GroupingRule.HEADING_SPAN.value,
            )
            for i in range(5)
        ] + [
            _make_evidence_chunk(
                evidence_chunk_id=f"ec{i+5}",
                grouping_rule_id=GroupingRule.PARAGRAPH_RUN.value,
            )
            for i in range(5)
        ]
        result = m_b5_grouping_rule_coverage(chunks)
        assert result.passed is True
        assert result.value == 0.5  # 50% each

    def test_single_rule_dominance_fails(self) -> None:
        """Single rule > 80% should fail."""
        chunks = [
            _make_evidence_chunk(
                evidence_chunk_id=f"ec{i}",
                grouping_rule_id=GroupingRule.PARAGRAPH_RUN.value,
            )
            for i in range(10)
        ]
        result = m_b5_grouping_rule_coverage(chunks)
        assert result.passed is False
        assert result.value == 1.0


class TestMB6StopReasonDistribution:
    """Tests for M-B6 stop-reason distribution gate."""

    def test_empty_chunks_passes(self) -> None:
        """Empty input should pass."""
        result = m_b6_stop_reason_distribution([])
        assert result.passed is True

    def test_normal_distribution_passes(self) -> None:
        """Normal stop reasons should pass."""
        chunks = [
            _make_evidence_chunk(
                evidence_chunk_id=f"ec{i}",
                grouping_stop_reason=GroupingStopReason.END_OF_SECTION.value,
            )
            for i in range(10)
        ]
        result = m_b6_stop_reason_distribution(chunks)
        assert result.passed is True

    def test_too_many_size_threshold_fails(self) -> None:
        """Too many size_threshold_hit should fail."""
        chunks = [
            _make_evidence_chunk(
                evidence_chunk_id=f"ec{i}",
                grouping_stop_reason=GroupingStopReason.SIZE_THRESHOLD_HIT.value,
            )
            for i in range(10)
        ]
        result = m_b6_stop_reason_distribution(chunks)
        assert result.passed is False


class TestRunGates:
    """Tests for the main run_gates function."""

    def test_run_gates_returns_report(self) -> None:
        """run_gates should return a complete GatesReport."""
        chunks = [
            _make_evidence_chunk(evidence_chunk_id=f"ec{i}", text="A" * 600)
            for i in range(10)
        ]
        report = run_gates(chunks)

        assert hasattr(report, "passed")
        assert hasattr(report, "results")
        # Should have 8 gates (M-B1 through M-B8)
        assert len(report.results) == 8

    def test_run_gates_all_pass(self) -> None:
        """Well-formed chunks should pass all gates."""
        # Create balanced, well-sized chunks
        chunks = []
        for i in range(10):
            rule = GroupingRule.HEADING_SPAN.value if i % 2 == 0 else GroupingRule.PARAGRAPH_RUN.value
            chunks.append(
                _make_evidence_chunk(
                    evidence_chunk_id=f"ec{i}",
                    text="A" * 600,
                    grouping_rule_id=rule,
                )
            )

        report = run_gates(chunks)
        assert report.passed is True

    def test_run_gates_to_dict(self) -> None:
        """GatesReport.to_dict should work."""
        chunks = [_make_evidence_chunk()]
        report = run_gates(chunks)
        d = report.to_dict()

        assert "passed" in d
        assert "results" in d
        assert isinstance(d["results"], list)

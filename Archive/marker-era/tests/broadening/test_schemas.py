"""Tests for broadening.schemas module."""

from __future__ import annotations

import pytest

from broadening.schemas import (
    EvidenceChunk,
    GroupingRule,
    GroupingStopReason,
    SourceSpan,
    UngroupedRecord,
    BroadeningResult,
)


class TestSourceSpan:
    """Tests for SourceSpan dataclass."""

    def test_valid_span(self) -> None:
        """SourceSpan with valid start/end should work."""
        span = SourceSpan(chunk_id="c1", page_index=0, span_start=0, span_end=100)
        assert span.chunk_id == "c1"
        assert span.span_start == 0
        assert span.span_end == 100

    def test_invalid_span_negative_start(self) -> None:
        """SourceSpan with negative start should raise ValueError."""
        with pytest.raises(ValueError):
            SourceSpan(chunk_id="c1", page_index=0, span_start=-1, span_end=100)

    def test_invalid_span_end_not_greater(self) -> None:
        """SourceSpan with end <= start should raise ValueError."""
        with pytest.raises(ValueError):
            SourceSpan(chunk_id="c1", page_index=0, span_start=50, span_end=50)

    def test_to_dict(self) -> None:
        """SourceSpan.to_dict should return proper dict."""
        span = SourceSpan(chunk_id="c1", page_index=5, span_start=10, span_end=200)
        d = span.to_dict()
        assert d == {
            "chunk_id": "c1",
            "page_index": 5,
            "span_start": 10,
            "span_end": 200,
        }


class TestEvidenceChunk:
    """Tests for EvidenceChunk dataclass."""

    def _make_evidence_chunk(
        self,
        evidence_chunk_id: str = "ec1",
        kind: str = "Prose",
        text: str = "Some meaningful text content here.",
        source_chunk_ids: list[str] | None = None,
        source_spans: list[SourceSpan] | None = None,
    ) -> EvidenceChunk:
        """Helper to create EvidenceChunk with defaults."""
        if source_chunk_ids is None:
            source_chunk_ids = ["c1"]
        if source_spans is None:
            source_spans = [SourceSpan(chunk_id="c1", page_index=0, span_start=0, span_end=100)]

        return EvidenceChunk(
            evidence_chunk_id=evidence_chunk_id,
            kind=kind,
            text=text,
            source_chunk_ids=source_chunk_ids,
            source_spans=source_spans,
            logical_doc_id="doc1",
            grouping_rule_id=GroupingRule.PARAGRAPH_RUN.value,
            grouping_stop_reason=GroupingStopReason.END_OF_SECTION.value,
            section_path=["Chapter 1"],
            page_indices=[0],
        )

    def test_valid_evidence_chunk(self) -> None:
        """Valid EvidenceChunk should work."""
        ec = self._make_evidence_chunk()
        assert ec.evidence_chunk_id == "ec1"
        assert ec.kind == "Prose"

    def test_empty_source_chunk_ids_fails(self) -> None:
        """EvidenceChunk with no source_chunk_ids should raise ValueError."""
        with pytest.raises(ValueError, match="at least one source_chunk_id"):
            self._make_evidence_chunk(source_chunk_ids=[], source_spans=[])

    def test_mismatched_ids_and_spans_fails(self) -> None:
        """EvidenceChunk with mismatched ids/spans should raise ValueError."""
        with pytest.raises(ValueError, match="same length"):
            EvidenceChunk(
                evidence_chunk_id="ec1",
                kind="Prose",
                text="Some text",
                source_chunk_ids=["c1", "c2"],
                source_spans=[SourceSpan(chunk_id="c1", page_index=0, span_start=0, span_end=10)],
                logical_doc_id="doc1",
                grouping_rule_id="paragraph_run",
                grouping_stop_reason="end_of_section",
                section_path=[],
                page_indices=[0],
            )

    def test_empty_text_fails(self) -> None:
        """EvidenceChunk with empty text should raise ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            self._make_evidence_chunk(text="   ")

    def test_to_dict(self) -> None:
        """EvidenceChunk.to_dict should return proper dict."""
        ec = self._make_evidence_chunk()
        d = ec.to_dict()
        assert d["evidence_chunk_id"] == "ec1"
        assert d["kind"] == "Prose"
        assert len(d["source_spans"]) == 1


class TestGroupingEnums:
    """Tests for GroupingRule and GroupingStopReason enums."""

    def test_grouping_rule_values(self) -> None:
        """GroupingRule should have expected values."""
        assert GroupingRule.HEADING_SPAN.value == "heading_span"
        assert GroupingRule.PARAGRAPH_RUN.value == "paragraph_run"
        assert GroupingRule.TABLE_CONSOLIDATION.value == "table_consolidation"
        assert GroupingRule.RULE_BLOCK.value == "rule_block"
        assert GroupingRule.SINGLE_CHUNK.value == "single_chunk"

    def test_grouping_stop_reason_values(self) -> None:
        """GroupingStopReason should have expected values."""
        assert GroupingStopReason.BOUNDARY_ENCOUNTERED.value == "boundary_encountered"
        assert GroupingStopReason.SIZE_THRESHOLD_HIT.value == "size_threshold_hit"
        assert GroupingStopReason.BLOCK_TYPE_MISMATCH.value == "block_type_mismatch"
        assert GroupingStopReason.END_OF_SECTION.value == "end_of_section"


class TestUngroupedRecord:
    """Tests for UngroupedRecord dataclass."""

    def test_ungrouped_record(self) -> None:
        """UngroupedRecord creation and to_dict."""
        rec = UngroupedRecord(chunk_id="c1", reason="below_semantic_mass", page_index=5)
        assert rec.chunk_id == "c1"
        assert rec.reason == "below_semantic_mass"

        d = rec.to_dict()
        assert d == {"chunk_id": "c1", "reason": "below_semantic_mass", "page_index": 5}


class TestBroadeningResult:
    """Tests for BroadeningResult dataclass."""

    def test_broadening_result(self) -> None:
        """BroadeningResult creation and to_dict."""
        result = BroadeningResult(
            evidence_chunks=[],
            ungrouped_records=[],
            input_chunk_count=100,
            eligible_chunk_count=80,
        )
        assert result.input_chunk_count == 100

        d = result.to_dict()
        assert d["input_chunk_count"] == 100
        assert d["eligible_chunk_count"] == 80

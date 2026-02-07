"""Tests for broadening.eligibility module."""

from __future__ import annotations

import pytest

from extraction.schemas import Chunk
from broadening.eligibility import (
    ELIGIBLE_TYPES,
    CONDITIONAL_ELIGIBLE,
    INELIGIBLE_TYPES,
    is_eligible,
    filter_eligible,
    classify_ineligibility,
)


def _make_chunk(block_type: str, text: str = "Sample text") -> Chunk:
    """Helper to create a minimal Chunk for testing."""
    return Chunk(
        chunk_id="test_chunk",
        doc_id="test_doc",
        page_index=0,
        section_path=["Chapter 1"],
        block_type=block_type,
        text=text,
        span_start=0,
        span_end=len(text),
        span_locality="page",
        bbox=(0.0, 0.0, 100.0, 100.0),
        block_ordinals=[0],
    )


class TestEligibilityConstants:
    """Tests for eligibility type sets."""

    def test_eligible_types(self) -> None:
        """ELIGIBLE_TYPES should contain Text, Heading, List."""
        assert "Text" in ELIGIBLE_TYPES
        assert "Heading" in ELIGIBLE_TYPES
        assert "List" in ELIGIBLE_TYPES

    def test_conditional_eligible(self) -> None:
        """CONDITIONAL_ELIGIBLE should contain Table."""
        assert "Table" in CONDITIONAL_ELIGIBLE

    def test_ineligible_types(self) -> None:
        """INELIGIBLE_TYPES should contain structural block types."""
        assert "Page" in INELIGIBLE_TYPES
        assert "ListGroup" in INELIGIBLE_TYPES
        assert "TableGroup" in INELIGIBLE_TYPES
        assert "FigureGroup" in INELIGIBLE_TYPES


class TestIsEligible:
    """Tests for is_eligible function."""

    @pytest.mark.parametrize("block_type", ["Text", "Heading", "List"])
    def test_always_eligible_types(self, block_type: str) -> None:
        """Text, Heading, List should always be eligible."""
        chunk = _make_chunk(block_type)
        assert is_eligible(chunk) is True
        assert is_eligible(chunk, allow_tables=False) is True
        assert is_eligible(chunk, allow_tables=True) is True

    def test_table_conditional_eligible(self) -> None:
        """Table should be eligible only when allow_tables=True."""
        chunk = _make_chunk("Table")
        assert is_eligible(chunk, allow_tables=False) is False
        assert is_eligible(chunk, allow_tables=True) is True

    @pytest.mark.parametrize("block_type", ["Page", "ListGroup", "TableGroup", "FigureGroup", "Form"])
    def test_ineligible_types(self, block_type: str) -> None:
        """Structural container types should never be eligible."""
        chunk = _make_chunk(block_type)
        assert is_eligible(chunk) is False
        assert is_eligible(chunk, allow_tables=True) is False


class TestFilterEligible:
    """Tests for filter_eligible function."""

    def test_filters_ineligible(self) -> None:
        """filter_eligible should remove ineligible chunks."""
        chunks = [
            _make_chunk("Text"),
            _make_chunk("Page"),
            _make_chunk("Heading"),
            _make_chunk("TableGroup"),
        ]
        result = filter_eligible(chunks)
        assert len(result) == 2
        assert all(c.block_type in ("Text", "Heading") for c in result)

    def test_includes_tables_when_allowed(self) -> None:
        """filter_eligible with allow_tables should include Table chunks."""
        chunks = [
            _make_chunk("Text"),
            _make_chunk("Table"),
        ]
        result = filter_eligible(chunks, allow_tables=True)
        assert len(result) == 2

    def test_excludes_tables_by_default(self) -> None:
        """filter_eligible should exclude Table chunks by default."""
        chunks = [
            _make_chunk("Text"),
            _make_chunk("Table"),
        ]
        result = filter_eligible(chunks, allow_tables=False)
        assert len(result) == 1
        assert result[0].block_type == "Text"


class TestClassifyIneligibility:
    """Tests for classify_ineligibility function."""

    def test_eligible_returns_none(self) -> None:
        """Eligible chunks should return None."""
        chunk = _make_chunk("Text")
        assert classify_ineligibility(chunk) is None

    def test_table_returns_conditional(self) -> None:
        """Table without allowlist should return conditional reason."""
        chunk = _make_chunk("Table")
        reason = classify_ineligibility(chunk)
        assert reason == "conditional_table_not_allowlisted"

    def test_ineligible_type_returns_reason(self) -> None:
        """Ineligible types should return specific reason."""
        chunk = _make_chunk("Page")
        reason = classify_ineligibility(chunk)
        assert reason == "ineligible_type_page"

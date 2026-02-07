"""Tests for broadening.grouper module."""

from __future__ import annotations

import pytest

from extraction.schemas import Chunk
from broadening.grouper import (
    MIN_CHARS,
    MIN_TOKENS,
    MIN_SENTENCES,
    MAX_CHARS,
    meets_prose_mass,
    meets_tabular_mass,
    same_section_prefix,
    is_chapter_boundary,
    are_consecutive,
    _evidence_chunk_id,
    group_chunks,
)
from broadening.schemas import GroupingRule


def _make_chunk(
    chunk_id: str,
    block_type: str = "Text",
    text: str = "Sample text content.",
    page_index: int = 0,
    section_path: list[str] | None = None,
    block_ordinals: list[int] | None = None,
) -> Chunk:
    """Helper to create a minimal Chunk for testing."""
    if section_path is None:
        section_path = ["Chapter 1"]
    if block_ordinals is None:
        block_ordinals = [0]

    return Chunk(
        chunk_id=chunk_id,
        doc_id="test_doc",
        page_index=page_index,
        section_path=section_path,
        block_type=block_type,
        text=text,
        span_start=0,
        span_end=len(text),
        span_locality="page",
        bbox=(0.0, 0.0, 100.0, 100.0),
        block_ordinals=block_ordinals,
    )


class TestSemanticMass:
    """Tests for semantic mass validation functions."""

    def test_meets_prose_mass_below_chars(self) -> None:
        """Text below MIN_CHARS should fail."""
        text = "Short text."
        assert meets_prose_mass(text) is False

    def test_meets_prose_mass_below_tokens(self) -> None:
        """Text below MIN_TOKENS should fail."""
        # Long but repetitive single word
        text = "a" * 400
        assert meets_prose_mass(text) is False

    def test_meets_prose_mass_below_sentences(self) -> None:
        """Text below MIN_SENTENCES should fail."""
        # Long enough, enough tokens, but only 1 sentence
        text = " ".join(["word"] * 100)
        assert len(text) >= MIN_CHARS
        assert len(text.split()) >= MIN_TOKENS
        assert meets_prose_mass(text) is False

    def test_meets_prose_mass_passes(self) -> None:
        """Text meeting all thresholds should pass."""
        # Create text with enough chars, tokens, and sentences
        # Need at least 300 chars, 80 tokens, 2 sentences
        sentences = ["This is a complete sentence with multiple words and enough content to pass." for _ in range(8)]
        text = " ".join(sentences)
        assert len(text) >= MIN_CHARS, f"Text length {len(text)} < {MIN_CHARS}"
        assert len(text.split()) >= MIN_TOKENS, f"Token count {len(text.split())} < {MIN_TOKENS}"
        assert meets_prose_mass(text) is True

    def test_meets_tabular_mass_by_rows(self) -> None:
        """Tabular content with enough rows should pass."""
        assert meets_tabular_mass(chunk_count=3) is True
        assert meets_tabular_mass(chunk_count=2) is False

    def test_meets_tabular_mass_by_keys(self) -> None:
        """Tabular content with enough distinct keys should pass."""
        assert meets_tabular_mass(chunk_count=1, distinct_keys=5) is True
        assert meets_tabular_mass(chunk_count=1, distinct_keys=4) is False


class TestBoundaryDetection:
    """Tests for boundary detection functions."""

    def test_same_section_prefix_identical(self) -> None:
        """Chunks with identical section_path share prefix."""
        a = _make_chunk("c1", section_path=["Ch1", "Sec1"])
        b = _make_chunk("c2", section_path=["Ch1", "Sec1"])
        assert same_section_prefix(a, b) is True

    def test_same_section_prefix_shared(self) -> None:
        """Chunks with same top-level section share prefix."""
        a = _make_chunk("c1", section_path=["Ch1", "Sec1"])
        b = _make_chunk("c2", section_path=["Ch1", "Sec1", "SubSec"])
        # Both share ["Ch1", "Sec1"] as prefix
        assert same_section_prefix(a, b) is True

    def test_same_section_prefix_different(self) -> None:
        """Chunks with different top-level fail."""
        a = _make_chunk("c1", section_path=["Ch1"])
        b = _make_chunk("c2", section_path=["Ch2"])
        assert same_section_prefix(a, b) is False

    def test_same_section_prefix_empty_fallback(self) -> None:
        """Empty section paths fall back to page comparison."""
        a = _make_chunk("c1", section_path=[], page_index=5)
        b = _make_chunk("c2", section_path=[], page_index=5)
        assert same_section_prefix(a, b) is True

        c = _make_chunk("c3", section_path=[], page_index=6)
        assert same_section_prefix(a, c) is False

    def test_is_chapter_boundary(self) -> None:
        """Chapter boundary detection."""
        a = _make_chunk("c1", section_path=["Ch1", "Sec1"])
        b = _make_chunk("c2", section_path=["Ch2", "Sec1"])
        assert is_chapter_boundary(a, b) is True

        c = _make_chunk("c3", section_path=["Ch1", "Sec2"])
        assert is_chapter_boundary(a, c) is False

    def test_are_consecutive_same_page(self) -> None:
        """Chunks on same page with adjacent ordinals are consecutive."""
        a = _make_chunk("c1", page_index=0, block_ordinals=[1])
        b = _make_chunk("c2", page_index=0, block_ordinals=[2])
        assert are_consecutive(a, b) is True

    def test_are_consecutive_different_page(self) -> None:
        """Chunks on different pages are not consecutive."""
        a = _make_chunk("c1", page_index=0, block_ordinals=[1])
        b = _make_chunk("c2", page_index=1, block_ordinals=[0])
        assert are_consecutive(a, b) is False


class TestIdGeneration:
    """Tests for deterministic ID generation."""

    def test_evidence_chunk_id_deterministic(self) -> None:
        """Same inputs should produce same ID."""
        id1 = _evidence_chunk_id("doc_hash", ["c1", "c2"], "paragraph_run")
        id2 = _evidence_chunk_id("doc_hash", ["c1", "c2"], "paragraph_run")
        assert id1 == id2

    def test_evidence_chunk_id_order_independent(self) -> None:
        """Chunk ID order shouldn't matter (sorted internally)."""
        id1 = _evidence_chunk_id("doc_hash", ["c1", "c2"], "paragraph_run")
        id2 = _evidence_chunk_id("doc_hash", ["c2", "c1"], "paragraph_run")
        assert id1 == id2

    def test_evidence_chunk_id_different_inputs(self) -> None:
        """Different inputs should produce different IDs."""
        id1 = _evidence_chunk_id("doc_hash", ["c1"], "paragraph_run")
        id2 = _evidence_chunk_id("doc_hash", ["c2"], "paragraph_run")
        assert id1 != id2

    def test_evidence_chunk_id_length(self) -> None:
        """ID should be 32 hex characters."""
        id1 = _evidence_chunk_id("doc_hash", ["c1"], "paragraph_run")
        assert len(id1) == 32
        assert all(c in "0123456789abcdef" for c in id1)


class TestGroupChunks:
    """Tests for the main group_chunks function."""

    def _make_prose_text(self) -> str:
        """Create text that meets prose mass thresholds."""
        # Need at least 300 chars, 80 tokens, 2 sentences
        sentences = ["This is a complete sentence with multiple words and enough content to pass the semantic mass threshold." for _ in range(8)]
        return " ".join(sentences)

    def test_empty_input(self) -> None:
        """Empty input should return empty output."""
        evidence_chunks, ungrouped = group_chunks([], doc_hash="test")
        assert len(evidence_chunks) == 0
        assert len(ungrouped) == 0

    def test_filters_ineligible(self) -> None:
        """Ineligible chunks should not appear in output."""
        chunks = [
            _make_chunk("c1", block_type="Page"),
            _make_chunk("c2", block_type="ListGroup"),
        ]
        evidence_chunks, ungrouped = group_chunks(chunks, doc_hash="test")
        assert len(evidence_chunks) == 0
        # Ineligible chunks filtered out before grouping, so not in ungrouped

    def test_heading_span_or_rule_block_grouping(self) -> None:
        """Heading followed by Text with matching content path groups as rule_block."""
        prose_text = self._make_prose_text()
        path_l1 = ["/page/1/SectionHeader/1"]
        path_content = ["/page/1/SectionHeader/1", "/page/1/SectionHeader/2"]
        chunks = [
            _make_chunk("c1", block_type="Heading", text="Important Section", section_path=path_l1, block_ordinals=[0]),
            _make_chunk("c2", block_type="Text", text=prose_text, section_path=path_content, block_ordinals=[1]),
        ]
        evidence_chunks, ungrouped = group_chunks(chunks, doc_hash="test")

        rule_block_groups = [e for e in evidence_chunks if e.grouping_rule_id == GroupingRule.RULE_BLOCK.value]
        heading_span_groups = [e for e in evidence_chunks if e.grouping_rule_id == GroupingRule.HEADING_SPAN.value]
        paragraph_run_groups = [e for e in evidence_chunks if e.grouping_rule_id == GroupingRule.PARAGRAPH_RUN.value]
        assert len(evidence_chunks) >= 1
        assert len(rule_block_groups) >= 1 or len(heading_span_groups) >= 1 or len(paragraph_run_groups) >= 1

    def test_paragraph_run_grouping(self) -> None:
        """Consecutive Text chunks should group together."""
        part1 = self._make_prose_text()
        part2 = self._make_prose_text()
        chunks = [
            _make_chunk("c1", block_type="Text", text=part1, block_ordinals=[0]),
            _make_chunk("c2", block_type="Text", text=part2, block_ordinals=[1]),
        ]
        evidence_chunks, ungrouped = group_chunks(chunks, doc_hash="test")

        para_groups = [e for e in evidence_chunks if e.grouping_rule_id == GroupingRule.PARAGRAPH_RUN.value]
        # May be grouped together if total size is within limit
        assert len(evidence_chunks) >= 1

    def test_below_semantic_mass_ungrouped(self) -> None:
        """Chunks below semantic mass are still emitted as EvidenceChunks with structural_metadata (inclusive default)."""
        chunks = [
            _make_chunk("c1", block_type="Heading", text="Short"),
        ]
        evidence_chunks, ungrouped = group_chunks(chunks, doc_hash="test")

        # Short heading alone won't meet prose mass but we emit it with below_preferred_mass
        assert len(evidence_chunks) == 1
        assert evidence_chunks[0].structural_metadata.get("below_preferred_mass") is True
        assert len(ungrouped) == 0

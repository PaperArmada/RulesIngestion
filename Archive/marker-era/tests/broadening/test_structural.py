"""Tests for broadening.structural module."""

from __future__ import annotations

import pytest

from extraction.schemas import Chunk
from broadening.structural import build_content_path_index, content_path_for_rule_header


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


class TestBuildContentPathIndex:
    """Tests for build_content_path_index."""

    def test_empty_chunks(self) -> None:
        """Empty input returns empty index."""
        assert build_content_path_index([]) == {}

    def test_chunks_with_path_length_1_excluded(self) -> None:
        """Chunks with section_path length < 2 are not indexed."""
        chunks = [
            _make_chunk("c1", section_path=["L1"]),
            _make_chunk("c2", section_path=[]),
        ]
        index = build_content_path_index(chunks)
        assert index == {}

    def test_single_content_path(self) -> None:
        """Single content path indexes all matching chunks."""
        path = ["/page/16/SectionHeader/7", "/page/16/SectionHeader/8"]
        chunks = [
            _make_chunk("c1", section_path=path, text="First"),
            _make_chunk("c2", section_path=path, text="Second"),
        ]
        index = build_content_path_index(chunks)
        key = tuple(path)
        assert key in index
        assert len(index[key]) == 2
        assert {c.chunk_id for c in index[key]} == {"c1", "c2"}

    def test_multiple_content_paths(self) -> None:
        """Multiple paths create separate index entries."""
        path_a = ["/page/16/SectionHeader/7", "/page/16/SectionHeader/8"]
        path_b = ["/page/16/SectionHeader/7", "/page/16/SectionHeader/22"]
        chunks = [
            _make_chunk("c1", section_path=path_a),
            _make_chunk("c2", section_path=path_b),
            _make_chunk("c3", section_path=path_a),
        ]
        index = build_content_path_index(chunks)
        assert len(index) == 2
        assert len(index[tuple(path_a)]) == 2
        assert len(index[tuple(path_b)]) == 1

    def test_header_chunks_not_indexed(self) -> None:
        """Headers (path len 1) and empty path are excluded."""
        chunks = [
            _make_chunk("c1", section_path=["/page/16/SectionHeader/7"]),
            _make_chunk("c2", section_path=["/page/16/SectionHeader/7", "/page/16/SectionHeader/8"]),
        ]
        index = build_content_path_index(chunks)
        assert len(index) == 1
        assert len(index[("/page/16/SectionHeader/7", "/page/16/SectionHeader/8")]) == 1


class TestContentPathForRuleHeader:
    """Tests for content_path_for_rule_header."""

    def test_header_with_path_length_not_1_returns_none(self) -> None:
        """Only headers with path length 1 are valid."""
        chunks = [
            _make_chunk("c1", section_path=["L1", "L2"]),
        ]
        assert content_path_for_rule_header(chunks[0], chunks, 0) is None

        empty = _make_chunk("c2", section_path=[])
        assert content_path_for_rule_header(empty, chunks, 0) is None

    def test_header_with_immediate_content(self) -> None:
        """First content chunk after header defines content path."""
        path_l1 = ["/page/16/SectionHeader/7"]
        path_content = ["/page/16/SectionHeader/7", "/page/16/SectionHeader/8"]
        chunks = [
            _make_chunk("h1", block_type="Heading", section_path=path_l1),
            _make_chunk("c1", section_path=path_content),
        ]
        result = content_path_for_rule_header(chunks[0], chunks, 0)
        assert result == tuple(path_content)

    def test_header_with_interleaved_content(self) -> None:
        """First chunk with same L1 and path len >= 2 defines content path."""
        path_l1 = ["/page/16/SectionHeader/7"]
        path_a = ["/page/16/SectionHeader/7", "/page/16/SectionHeader/8"]
        path_b = ["/page/16/SectionHeader/7", "/page/16/SectionHeader/22"]
        chunks = [
            _make_chunk("h1", block_type="Heading", section_path=path_l1),
            _make_chunk("c_b", section_path=path_b),
            _make_chunk("c_a", section_path=path_a),
        ]
        # First content after h1 is c_b (path_b)
        result = content_path_for_rule_header(chunks[0], chunks, 0)
        assert result == tuple(path_b)

    def test_second_header_gets_own_content_path(self) -> None:
        """Second header in same L1 gets correct content path."""
        path_l1 = ["/page/16/SectionHeader/7"]
        path_a = ["/page/16/SectionHeader/7", "/page/16/SectionHeader/8"]
        path_b = ["/page/16/SectionHeader/7", "/page/16/SectionHeader/22"]
        chunks = [
            _make_chunk("h1", block_type="Heading", section_path=path_l1),
            _make_chunk("c_a", section_path=path_a),
            _make_chunk("h2", block_type="Heading", section_path=path_l1),
            _make_chunk("c_b", section_path=path_b),
        ]
        # h1 (index 0): first content after is c_a -> path_a
        assert content_path_for_rule_header(chunks[0], chunks, 0) == tuple(path_a)
        # h2 (index 2): first content after is c_b -> path_b
        assert content_path_for_rule_header(chunks[2], chunks, 2) == tuple(path_b)

    def test_header_at_end_returns_none(self) -> None:
        """Header with no following content returns None."""
        chunks = [
            _make_chunk("h1", block_type="Heading", section_path=["/page/16/SectionHeader/7"]),
        ]
        assert content_path_for_rule_header(chunks[0], chunks, 0) is None

    def test_header_followed_only_by_other_headers_returns_none(self) -> None:
        """If only headers follow (path len 1), no content path."""
        path_l1 = ["/page/16/SectionHeader/7"]
        chunks = [
            _make_chunk("h1", block_type="Heading", section_path=path_l1),
            _make_chunk("h2", block_type="Heading", section_path=path_l1),
        ]
        assert content_path_for_rule_header(chunks[0], chunks, 0) is None

"""Tests for extraction.schemas: MarkerBlock, Chunk, DropRecord."""

import pytest

from extraction.schemas import Chunk, DropRecord, MarkerBlock, ProvenanceSpan


def test_marker_block_to_dict() -> None:
    b = MarkerBlock(
        doc_id="doc1",
        page_index=1,
        text="Hello",
        bbox=(0.0, 0.0, 10.0, 10.0),
        raw_block_type="Text",
        block_ordinal=0,
    )
    d = b.to_dict()
    assert d["doc_id"] == "doc1"
    assert d["page_index"] == 1
    assert d["text"] == "Hello"
    assert d["block_ordinal"] == 0


def test_chunk_span_validity() -> None:
    with pytest.raises(ValueError, match="Invalid span"):
        Chunk(
            chunk_id="c1",
            doc_id="d1",
            page_index=0,
            section_path=[],
            block_type="Text",
            text="x",
            span_start=1,
            span_end=1,
            span_locality="block",
            bbox=(0, 0, 0, 0),
            block_ordinals=[0],
        )
    with pytest.raises(ValueError, match="non-empty"):
        Chunk(
            chunk_id="c1",
            doc_id="d1",
            page_index=0,
            section_path=[],
            block_type="Text",
            text="   ",
            span_start=0,
            span_end=1,
            span_locality="block",
            bbox=(0, 0, 0, 0),
            block_ordinals=[0],
        )
    c = Chunk(
        chunk_id="c1",
        doc_id="d1",
        page_index=0,
        section_path=["Ch1"],
        block_type="Text",
        text="hello",
        span_start=0,
        span_end=5,
        span_locality="block",
        bbox=(0, 0, 0, 0),
        block_ordinals=[0],
    )
    assert c.chunk_id == "c1"
    assert c.to_dict()["section_path"] == ["Ch1"]


def test_drop_record_to_dict() -> None:
    d = DropRecord(reason_code="empty", page_index=2, block_reference="ord=3")
    assert d.to_dict()["reason_code"] == "empty"
    assert d.to_dict()["page_index"] == 2


def test_provenance_span_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid span"):
        ProvenanceSpan(start=1, end=1, locality="block")

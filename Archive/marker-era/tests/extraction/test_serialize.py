"""Tests for extraction.serialize: deterministic serialization and M-A1 hashing."""

from extraction.schemas import Chunk, MarkerBlock
from extraction.serialize import (
    chunkset_hash,
    deterministic_serialize_chunks,
    deterministic_serialize_marker_stream,
    markerstream_hash,
)


def test_deterministic_serialize_same_hash() -> None:
    stream = [
        MarkerBlock(
            doc_id="d1",
            page_index=0,
            text="a",
            bbox=(0, 0, 1, 1),
            raw_block_type="Text",
            block_ordinal=0,
        ),
    ]
    h1 = markerstream_hash(stream)
    h2 = markerstream_hash(stream)
    assert h1 == h2


def test_chunkset_hash_deterministic() -> None:
    c = Chunk(
        chunk_id="c1",
        doc_id="d1",
        page_index=0,
        section_path=[],
        block_type="Text",
        text="x",
        span_start=0,
        span_end=1,
        span_locality="block",
        bbox=(0, 0, 0, 0),
        block_ordinals=[0],
    )
    h1 = chunkset_hash([c])
    h2 = chunkset_hash([c])
    assert h1 == h2


def test_serialize_bytes_stable() -> None:
    stream = [
        MarkerBlock("d1", 0, "t", (0, 0, 0, 0), "Text", 0),
    ]
    raw = deterministic_serialize_marker_stream(stream)
    assert isinstance(raw, bytes)
    assert b"doc_id" in raw

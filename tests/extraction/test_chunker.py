"""Tests for extraction.chunker: MarkerStream → Chunk[] + DropRecords."""

from extraction.chunker import stream_to_chunks, _chunk_id, _default_should_drop
from extraction.schemas import MarkerBlock


def _block(
    doc_id: str = "doc1",
    page: int = 0,
    text: str = "x",
    raw_type: str = "Text",
    ordinal: int = 0,
    section_hierarchy: dict | None = None,
) -> MarkerBlock:
    return MarkerBlock(
        doc_id=doc_id,
        page_index=page,
        text=text,
        bbox=(0.0, 0.0, 10.0, 10.0),
        raw_block_type=raw_type,
        block_ordinal=ordinal,
        section_hierarchy=section_hierarchy or {},
    )


def test_chunk_id_deterministic() -> None:
    a = _chunk_id("doc1", 0, 0, "sect", "Text")
    b = _chunk_id("doc1", 0, 0, "sect", "Text")
    assert a == b
    c = _chunk_id("doc1", 0, 1, "sect", "Text")
    assert a != c


def test_default_should_drop_empty() -> None:
    drop, reason = _default_should_drop(_block(text=""))
    assert drop is True
    assert reason == "empty_text"
    drop2, _ = _default_should_drop(_block(text="  "))
    assert drop2 is True
    drop3, _ = _default_should_drop(_block(text="hello"))
    assert drop3 is False


def test_stream_to_chunks_grouping() -> None:
    stream = [
        _block(text="Heading", raw_type="SectionHeader", ordinal=0, section_hierarchy={"title": "Ch1"}),
        _block(text="Body text", raw_type="Text", ordinal=1, section_hierarchy={"title": "Ch1"}),
    ]
    result = stream_to_chunks(stream, "doc1")
    assert len(result.chunks) >= 1
    assert len(result.drop_records) == 0
    c = result.chunks[0]
    assert c.doc_id == "doc1"
    assert c.span_start >= 0 and c.span_end > c.span_start
    assert "Body" in c.text or "Heading" in c.text


def test_stream_to_chunks_drop_records() -> None:
    # Empty Text goes to empty_structural_blocks (side-channel), not drop_records.
    stream = [
        _block(text="", ordinal=0, raw_type="Text"),
        _block(text="keep", ordinal=1),
    ]
    result = stream_to_chunks(stream, "doc1")
    assert len(result.empty_structural_blocks) == 1
    assert result.empty_structural_blocks[0].raw_block_type == "Text"
    assert len(result.drop_records) == 0
    assert len(result.chunks) >= 1


def test_stream_to_chunks_empty_non_structural_still_dropped() -> None:
    # Empty block of type other than Text/TableCell still produces a drop.
    stream = [
        _block(text="", ordinal=0, raw_type="Figure"),
        _block(text="keep", ordinal=1),
    ]
    result = stream_to_chunks(stream, "doc1")
    assert len(result.empty_structural_blocks) == 0
    assert len(result.drop_records) == 1
    assert result.drop_records[0].reason_code == "empty_text"


def test_heading_recategorized_to_table_on_weird_ratio() -> None:
    # Symbol-heavy heading-like content should be recategorized to Table.
    stream = [
        _block(text="Armor 10  5  4  4  —  —  —  —", raw_type="SectionHeader", ordinal=0),
    ]
    result = stream_to_chunks(stream, "doc1")
    assert len(result.chunks) == 1
    assert result.chunks[0].block_type == "Table"

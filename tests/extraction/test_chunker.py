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


def test_semantic_section_path() -> None:
    """Chunks get semantic section_path from heading registry (Marker format)."""
    stream = [
        _block(
            text="Chapter 2: Creating a Character",
            raw_type="SectionHeader",
            ordinal=0,
            section_hierarchy={"1": "/page/31/SectionHeader/1"},
        ),
        _block(
            text="Tiers of Play",
            raw_type="SectionHeader",
            ordinal=1,
            section_hierarchy={"1": "/page/31/SectionHeader/1", "2": "/page/41/SectionHeader/6"},
        ),
        _block(
            text="TIER 2 (LEVELS 5-10) — In tier 2, characters are full-fledged adventurers.",
            raw_type="Text",
            ordinal=2,
            section_hierarchy={"1": "/page/31/SectionHeader/1", "2": "/page/41/SectionHeader/6"},
        ),
    ]
    result = stream_to_chunks(stream, "doc1")
    assert len(result.chunks) >= 1
    # Chunk with body text should have semantic section_path (not raw paths)
    body_chunk = next(c for c in result.chunks if "full-fledged adventurers" in c.text)
    assert len(body_chunk.section_path) >= 2
    assert "Chapter 2" in body_chunk.section_path[0]
    assert "Tiers of Play" in body_chunk.section_path[1]
    assert not body_chunk.section_path[0].startswith("/page/")

from enrichment import EnrichedChunk, coalesce_chunks


def _make_chunk(chunk_id: str, text: str, section_path=None) -> EnrichedChunk:
    return EnrichedChunk(
        id=chunk_id,
        block_type="Text",
        text=text,
        page=1,
        section_path=section_path or ["Section"],
    )


def test_coalesce_chunks_merges_until_min_chars() -> None:
    chunks = [
        _make_chunk("a", "A" * 150),
        _make_chunk("b", "B" * 160),
        _make_chunk("c", "C" * 200),
    ]

    coalesced = coalesce_chunks(chunks, min_chars=400, max_chars=800)

    assert len(coalesced) == 1
    assert len(coalesced[0].text) >= 400


def test_coalesce_chunks_respects_max_chars() -> None:
    chunks = [
        _make_chunk("a", "A" * 300),
        _make_chunk("b", "B" * 300),
        _make_chunk("c", "C" * 300),
    ]

    coalesced = coalesce_chunks(chunks, min_chars=400, max_chars=800)

    assert len(coalesced) == 2
    assert len(coalesced[0].text) <= 800
    assert len(coalesced[1].text) <= 800


def test_coalesce_chunks_splits_on_section_change_when_satisfied() -> None:
    chunks = [
        _make_chunk("a", "A" * 500, section_path=["Section A"]),
        _make_chunk("b", "B" * 200, section_path=["Section B"]),
    ]

    coalesced = coalesce_chunks(chunks, min_chars=400, max_chars=800)

    assert len(coalesced) == 2
    assert "A" * 500 in coalesced[0].text
    assert "B" * 200 in coalesced[1].text

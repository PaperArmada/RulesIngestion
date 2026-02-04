"""Tests for extraction.gates: M-A2–M-A9."""

from extraction.gates import (
    m_a2_page_coverage,
    m_a3_block_retention,
    m_a4_span_validity,
    m_a5_structural_address,
    m_a6_unknown_block_rate,
    m_a8_text_entropy,
    m_a9_provenance_completeness,
    run_gates,
)
from extraction.schemas import Chunk, DropRecord, MarkerBlock


def _block(
    page: int = 0,
    raw_type: str = "Text",
    ordinal: int = 0,
    source_pdf_id: str = "",
) -> MarkerBlock:
    return MarkerBlock(
        doc_id="d1",
        page_index=page,
        text="x",
        bbox=(0, 0, 0, 0),
        raw_block_type=raw_type,
        block_ordinal=ordinal,
        source_pdf_id=source_pdf_id,
    )


def _chunk(
    section_path: list[str] | None = None,
    *,
    block_type: str = "Text",
    logical_doc_id: str = "ld1",
    document_part_id: str = "part1",
    source_pdf_id: str = "d1",
    source_pdf_page_index: int = 0,
    logical_page_index: int = 0,
) -> Chunk:
    return Chunk(
        chunk_id="c1",
        doc_id="d1",
        page_index=0,
        section_path=section_path or ["Ch1"],
        block_type=block_type,
        text="hello",
        span_start=0,
        span_end=5,
        span_locality="block",
        bbox=(0, 0, 0, 0),
        block_ordinals=[0],
        logical_doc_id=logical_doc_id,
        document_part_id=document_part_id,
        source_pdf_id=source_pdf_id,
        source_pdf_page_index=source_pdf_page_index,
        logical_page_index=logical_page_index,
    )


def test_m_a4_span_validity() -> None:
    valid = _chunk()  # text="hello", span 0..5
    assert m_a4_span_validity([valid]) == 1.0
    # span_end > len(text) is invalid
    bad = Chunk(
        chunk_id="c2",
        doc_id="d1",
        page_index=0,
        section_path=[],
        block_type="Text",
        text="ab",
        span_start=0,
        span_end=10,
        span_locality="block",
        bbox=(0, 0, 0, 0),
        block_ordinals=[0],
    )
    assert m_a4_span_validity([valid, bad]) == 0.5


def test_m_a2_page_coverage() -> None:
    stream = [_block(page=0), _block(page=1), _block(page=2)]
    assert m_a2_page_coverage(stream) == 1.0
    stream2 = [_block(page=0), _block(page=0)]
    assert m_a2_page_coverage(stream2) == 1.0


def test_m_a3_block_retention() -> None:
    stream = [_block(), _block(ordinal=1), _block(ordinal=2)]
    drops = [DropRecord("empty", 0, "ord=1")]
    # total = len(stream) = 3, retained = total - len(drops) = 2, retention = 2/3
    r = m_a3_block_retention(stream, drops)
    assert 0 <= r <= 1
    assert r == 2 / 3


def test_m_a3_excludes_form_parts() -> None:
    # 2 rulebook + 2 form blocks; 1 rulebook drop. Rulebook retention = (2-1)/2 = 0.5
    stream = [
        _block(ordinal=0, source_pdf_id="Player Core 001"),
        _block(ordinal=1, source_pdf_id="Player Core 001"),
        _block(ordinal=2, source_pdf_id="Character Sheet"),
        _block(ordinal=3, source_pdf_id="Character Sheet"),
    ]
    drops = [DropRecord("empty_text", 0, "ord=0", source_pdf_id="Player Core 001")]
    r = m_a3_block_retention(stream, drops, exclude_form_parts=True)
    assert r == 0.5
    # With form included: total=4, dropped=1, retention=3/4
    r_all = m_a3_block_retention(stream, drops, exclude_form_parts=False)
    assert r_all == 3 / 4


def test_m_a3_excludes_empty_structural_from_total() -> None:
    # 3 content blocks; 1 empty TableCell in side-channel (not dropped). total = 3 - 1 = 2, dropped = 0, retention = 1.0
    stream = [_block(ordinal=0), _block(ordinal=1), _block(ordinal=2)]
    r = m_a3_block_retention(stream, [], empty_structural_count=1)
    assert r == 1.0
    # Without excluding: total=3, dropped=0, retention=1.0. With 1 drop and 1 empty_structural: total=2, dropped=1, retention=0.5
    drops = [DropRecord("empty_text", 0, "ord=0", source_pdf_id="")]
    r2 = m_a3_block_retention(stream, drops, empty_structural_count=1)
    assert r2 == 0.5


def test_m_a5_structural_address() -> None:
    chunks = [_chunk(section_path=["Ch1"])]
    assert m_a5_structural_address(chunks) == 1.0
    # Chunk with no section path but doc_id + page_index (contract minimum) still counts
    from extraction.schemas import Chunk
    no_section = Chunk(
        chunk_id="c2",
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
    assert m_a5_structural_address([no_section]) == 1.0


def test_m_a6_unknown_block_rate() -> None:
    stream = [_block(raw_type="Text"), _block(raw_type="UnknownType", ordinal=1)]
    rate = m_a6_unknown_block_rate(stream)
    assert rate == 0.5


def test_m_a9_provenance_completeness() -> None:
    assert m_a9_provenance_completeness([_chunk()]) == 1.0
    incomplete = Chunk(
        chunk_id="c2",
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
        logical_doc_id="",
        document_part_id="",
        source_pdf_id="",
        source_pdf_page_index=-1,
        logical_page_index=-1,
    )
    assert m_a9_provenance_completeness([_chunk(), incomplete]) == 0.5


def test_run_gates_returns_report() -> None:
    stream = [_block(), _block(ordinal=1)]
    chunks = [_chunk()]  # full provenance so M-A9 passes
    drops: list[DropRecord] = []
    report = run_gates(stream, chunks, drops)
    assert hasattr(report, "passed")
    assert hasattr(report, "results")
    assert len(report.results) >= 7
    assert report.passed


def test_m_a8_excludes_table_chunks() -> None:
    table_chunk = Chunk(
        chunk_id="ctable",
        doc_id="d1",
        page_index=0,
        section_path=["Ch1"],
        block_type="Table",
        text="10  5  4  4  —  —  —  —",
        span_start=0,
        span_end=24,
        span_locality="block",
        bbox=(0, 0, 0, 0),
        block_ordinals=[0],
    )
    ok_chunk = _chunk(block_type="Text")
    assert m_a8_text_entropy([table_chunk, ok_chunk]) == 1.0

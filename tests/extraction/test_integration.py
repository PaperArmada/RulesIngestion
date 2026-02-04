"""Integration test: mock Marker output → MarkerStream → Chunk[] (no real PDF)."""

import tempfile
from pathlib import Path

import pytest

from extraction.chunker import stream_to_chunks
from extraction.run import run_extraction, _pdfs_in_folder
from extraction.marker_runner import blocks_to_marker_stream, raw_to_blocks
from extraction.serialize import chunkset_hash, markerstream_hash


def test_mock_marker_to_chunks() -> None:
    """Mock Marker JSON (flat blocks) → raw_to_blocks → blocks_to_marker_stream → stream_to_chunks."""
    raw = [
        {"block_type": "Title", "html": "<h1>Chapter 1</h1>", "page": 0, "bbox": [0, 0, 100, 20], "section_hierarchy": {"title": "Chapter 1"}},
        {"block_type": "Text", "html": "<p>First paragraph.</p>", "page": 0, "bbox": [0, 25, 100, 40]},
        {"block_type": "Text", "html": "<p>Second paragraph.</p>", "page": 0, "bbox": [0, 45, 100, 60]},
    ]
    blocks = raw_to_blocks(raw)
    assert len(blocks) == 3
    stream = blocks_to_marker_stream(blocks, "doc1")
    assert len(stream) == 3
    assert all(b.doc_id == "doc1" for b in stream)
    result = stream_to_chunks(stream, "doc1")
    assert len(result.chunks) >= 1
    assert len(result.marker_stream) == 3
    h1 = markerstream_hash(result.marker_stream)
    h2 = chunkset_hash(result.chunks)
    assert len(h1) >= 16
    assert len(h2) >= 16


def test_determinism_same_input_same_hashes() -> None:
    """Same mock input → same MarkerStream and Chunk[] hashes."""
    raw = [
        {"block_type": "Text", "html": "<p>Same</p>", "page": 0},
    ]
    blocks = raw_to_blocks(raw)
    stream1 = blocks_to_marker_stream(blocks, "doc1")
    stream2 = blocks_to_marker_stream(blocks, "doc1")
    result1 = stream_to_chunks(stream1, "doc1")
    result2 = stream_to_chunks(stream2, "doc1")
    assert markerstream_hash(result1.marker_stream) == markerstream_hash(result2.marker_stream)
    assert chunkset_hash(result1.chunks) == chunkset_hash(result2.chunks)


def test_run_extraction_multi_pdf_path_requires_existing_files() -> None:
    """run_extraction with pdf_paths (multi-PDF) takes multi path and validates files exist."""
    with pytest.raises(FileNotFoundError, match="PDF not found"):
        run_extraction(
            output_dir=Path("/tmp/out"),
            doc_id="book1",
            pdf_paths=[Path("/nonexistent/a.pdf"), Path("/nonexistent/b.pdf")],
        )


def test_pdfs_in_folder() -> None:
    """_pdfs_in_folder returns direct *.pdf children sorted by name; raises if not a directory."""
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d)
        (folder / "B.pdf").touch()
        (folder / "A.pdf").touch()
        (folder / "not-pdf.txt").touch()
        pdfs = _pdfs_in_folder(folder)
        assert [p.name for p in pdfs] == ["A.pdf", "B.pdf"]
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        try:
            with pytest.raises(NotADirectoryError, match="Not a directory"):
                _pdfs_in_folder(Path(f.name))
        finally:
            Path(f.name).unlink(missing_ok=True)

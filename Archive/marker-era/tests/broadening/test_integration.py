"""Integration tests for the broadening package."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from extraction.schemas import Chunk
from broadening.run import run_broadening, _chunk_from_dict
from broadening.schemas import BroadeningResult


def _make_chunk_dict(
    chunk_id: str,
    block_type: str = "Text",
    text: str = "Sample text content.",
    page_index: int = 0,
    section_path: list[str] | None = None,
    block_ordinals: list[int] | None = None,
) -> dict:
    """Helper to create a chunk dict for testing."""
    if section_path is None:
        section_path = ["Chapter 1"]
    if block_ordinals is None:
        block_ordinals = [0]

    return {
        "chunk_id": chunk_id,
        "doc_id": "test_doc",
        "page_index": page_index,
        "section_path": section_path,
        "block_type": block_type,
        "text": text,
        "span_start": 0,
        "span_end": len(text),
        "span_locality": "page",
        "bbox": [0.0, 0.0, 100.0, 100.0],
        "block_ordinals": block_ordinals,
        "structural_metadata": {},
        "logical_doc_id": "test_doc",
        "document_part_id": "test_doc",
        "source_pdf_id": "test.pdf",
        "source_pdf_page_index": page_index,
        "logical_page_index": page_index,
    }


def _make_prose_text() -> str:
    """Create text that meets prose mass thresholds."""
    sentences = ["This is a complete sentence with multiple words and meaning." for _ in range(10)]
    return " ".join(sentences)


class TestChunkFromDict:
    """Tests for _chunk_from_dict helper."""

    def test_converts_valid_dict(self) -> None:
        """Valid dict should convert to Chunk."""
        d = _make_chunk_dict("c1")
        chunk = _chunk_from_dict(d)
        assert isinstance(chunk, Chunk)
        assert chunk.chunk_id == "c1"

    def test_handles_missing_optional_fields(self) -> None:
        """Missing optional fields should use defaults."""
        d = {
            "chunk_id": "c1",
            "doc_id": "doc1",
            "page_index": 0,
            "block_type": "Text",
            "text": "Some text",
            "span_start": 0,
            "span_end": 9,
        }
        chunk = _chunk_from_dict(d)
        assert chunk.section_path == []
        assert chunk.logical_doc_id == ""


class TestRunBroadening:
    """Integration tests for run_broadening."""

    def test_end_to_end_with_valid_chunks(self) -> None:
        """End-to-end test with valid chunks."""
        prose_text = _make_prose_text()
        chunks = [
            _make_chunk_dict("c1", block_type="Heading", text="Section Title", block_ordinals=[0]),
            _make_chunk_dict("c2", block_type="Text", text=prose_text, block_ordinals=[1]),
            _make_chunk_dict("c3", block_type="Text", text=prose_text, block_ordinals=[2]),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_path = Path(tmpdir) / "chunks.json"
            output_dir = Path(tmpdir) / "output"

            # Write input
            with open(chunks_path, "w") as f:
                json.dump(chunks, f)

            # Run broadening
            result = run_broadening(
                chunks_path=chunks_path,
                output_dir=output_dir,
                check_gates=True,
            )

            # Check result
            assert isinstance(result, BroadeningResult)
            assert result.input_chunk_count == 3
            assert result.eligible_chunk_count >= 1

            # Check output files
            assert (output_dir / "evidence_chunks.json").exists()

    def test_with_wrapped_chunks_format(self) -> None:
        """Test with chunks in wrapped format (e.g., {"chunks": [...]})."""
        prose_text = _make_prose_text()
        chunks_data = {
            "chunks": [
                _make_chunk_dict("c1", block_type="Text", text=prose_text),
            ],
            "count": 1,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_path = Path(tmpdir) / "chunks.json"
            output_dir = Path(tmpdir) / "output"

            with open(chunks_path, "w") as f:
                json.dump(chunks_data, f)

            result = run_broadening(
                chunks_path=chunks_path,
                output_dir=output_dir,
            )

            assert result.input_chunk_count == 1

    def test_with_ineligible_chunks(self) -> None:
        """Test that ineligible chunks are filtered out."""
        chunks = [
            _make_chunk_dict("c1", block_type="Page"),
            _make_chunk_dict("c2", block_type="ListGroup"),
            _make_chunk_dict("c3", block_type="Text", text=_make_prose_text()),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_path = Path(tmpdir) / "chunks.json"
            output_dir = Path(tmpdir) / "output"

            with open(chunks_path, "w") as f:
                json.dump(chunks, f)

            result = run_broadening(
                chunks_path=chunks_path,
                output_dir=output_dir,
            )

            assert result.input_chunk_count == 3
            assert result.eligible_chunk_count == 1  # Only Text is eligible

    def test_with_tables_allowed(self) -> None:
        """Test with allow_tables=True."""
        chunks = [
            _make_chunk_dict("c1", block_type="Table", text="| A | B |\n| 1 | 2 |"),
            _make_chunk_dict("c2", block_type="Table", text="| C | D |\n| 3 | 4 |"),
            _make_chunk_dict("c3", block_type="Table", text="| E | F |\n| 5 | 6 |"),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_path = Path(tmpdir) / "chunks.json"
            output_dir = Path(tmpdir) / "output"

            with open(chunks_path, "w") as f:
                json.dump(chunks, f)

            result = run_broadening(
                chunks_path=chunks_path,
                output_dir=output_dir,
                allow_tables=True,
            )

            assert result.eligible_chunk_count == 3

    def test_gates_report_written(self) -> None:
        """Test that gates report is written when check_gates=True."""
        chunks = [
            _make_chunk_dict("c1", block_type="Text", text=_make_prose_text()),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_path = Path(tmpdir) / "chunks.json"
            output_dir = Path(tmpdir) / "output"

            with open(chunks_path, "w") as f:
                json.dump(chunks, f)

            run_broadening(
                chunks_path=chunks_path,
                output_dir=output_dir,
                check_gates=True,
            )

            assert (output_dir / "broadening_gates.json").exists()

            with open(output_dir / "broadening_gates.json") as f:
                gates_report = json.load(f)

            assert "passed" in gates_report
            assert "results" in gates_report


class TestOutputFormat:
    """Tests for output file format."""

    def test_evidence_chunks_json_format(self) -> None:
        """Test the evidence_chunks.json output format."""
        prose_text = _make_prose_text()
        chunks = [
            _make_chunk_dict("c1", block_type="Heading", text="Title", block_ordinals=[0]),
            _make_chunk_dict("c2", block_type="Text", text=prose_text, block_ordinals=[1]),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_path = Path(tmpdir) / "chunks.json"
            output_dir = Path(tmpdir) / "output"

            with open(chunks_path, "w") as f:
                json.dump(chunks, f)

            run_broadening(
                chunks_path=chunks_path,
                output_dir=output_dir,
            )

            with open(output_dir / "evidence_chunks.json") as f:
                output = json.load(f)

            assert "evidence_chunks" in output
            assert "count" in output
            assert "hash" in output
            assert isinstance(output["evidence_chunks"], list)

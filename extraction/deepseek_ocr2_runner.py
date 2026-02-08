"""
DeepSeek OCR 2 runner (placeholder).

This module is intended to run DeepSeek OCR 2 and convert its output into
MarkerStream-compatible blocks so downstream stages remain unchanged.
"""

from __future__ import annotations

from pathlib import Path

from extraction.marker_runner import blocks_to_marker_stream
from extraction.schemas import DocumentPart, MarkerBlock


def run_deepseek_ocr2(pdf_path: Path, output_dir: Path) -> tuple[list[dict], int]:
    """
    Run DeepSeek OCR 2 on a PDF and return (blocks, num_pages).

    Expected block shape matches Marker output: dicts with keys
    {text, bbox, block_type, section_hierarchy, page}. The adapter is not
    implemented yet, so this raises with guidance.
    """
    raise RuntimeError(
        "DeepSeek OCR 2 integration not implemented. "
        "Provide DeepSeek OCR 2 repo path and output JSON spec "
        "or implement an adapter per Docs/DeepSeek-OCR 2 README.md."
    )


def deepseek_blocks_to_marker_stream(
    blocks: list[dict],
    doc_id: str,
    document_part: DocumentPart | None = None,
) -> list[MarkerBlock]:
    """Convert DeepSeek OCR 2 blocks to MarkerStream-compatible blocks."""
    return blocks_to_marker_stream(blocks, doc_id, document_part)

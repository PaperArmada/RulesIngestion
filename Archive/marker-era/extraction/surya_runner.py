"""
Surya-based extraction (Stage A profile P2).

Produces blocks in the same shape as Marker (page, bbox, text, block_type, section_hierarchy)
so we can reuse blocks_to_marker_stream() for MarkerStream with A-DOC-INV-4 provenance.

When the surya package is not installed or integration is incomplete, run_surya() raises
RuntimeError with install instructions. See: Docs/Design/StageA-Pipeline-Execution-And-Examination.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from extraction.marker_runner import blocks_to_marker_stream
from extraction.schemas import DocumentPart, MarkerBlock


def run_surya(pdf_path: Path, output_dir: Path) -> tuple[list[dict[str, Any]], int]:
    """
    Run Surya layout + OCR on PDF. Return (blocks, num_pages).

    Block format (same as Marker raw_to_blocks): each dict has
    - page: int (0-based)
    - bbox: [x0, y0, x1, y1] or tuple
    - text: str
    - block_type: str (e.g. "Text", "Title", "Table")
    - section_hierarchy: dict (optional)

    Raises RuntimeError if surya is not installed or extraction fails.
    """
    try:
        return _run_surya_impl(pdf_path, output_dir)
    except ImportError as e:
        raise RuntimeError(
            "Surya profile requires: pip install surya-ocr pdf2image. "
            "Use --profile marker for the default pipeline."
        ) from e


def _run_surya_impl(pdf_path: Path, output_dir: Path) -> tuple[list[dict[str, Any]], int]:
    """
    Implementation of Surya extraction. Separated so we can add real API calls
    when surya-ocr is installed without breaking the default (marker) path.
    """
    # Optional dependency: surya-ocr. When not installed, raise so --profile surya fails clearly.
    try:
        import surya
    except ImportError:
        raise RuntimeError(
            "Surya profile requires: pip install surya-ocr pdf2image. "
            "Use --profile marker for the default pipeline."
        ) from None

    # TODO: Call surya layout + OCR, convert to blocks. For now raise so profile is wired but not fully implemented.
    raise RuntimeError(
        "Surya extraction not yet fully implemented. "
        "Install surya-ocr and add API calls in extraction/surya_runner._run_surya_impl(). "
        "Use --profile marker for the current pipeline."
    )


def surya_blocks_to_marker_stream(
    blocks: list[dict[str, Any]],
    doc_id: str,
    document_part: DocumentPart | None = None,
) -> list[MarkerBlock]:
    """
    Convert Surya blocks (same shape as Marker blocks) to MarkerStream with provenance.
    Reuses marker_runner.blocks_to_marker_stream so ordering and schema match.
    """
    return blocks_to_marker_stream(blocks, doc_id, document_part)

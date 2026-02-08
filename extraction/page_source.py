"""
Page Source Manager — render PDF pages to images and compute fingerprints.

Responsibilities:
  - Normalise source inputs into canonical page images (PNG).
  - Compute blake3 fingerprint of the rendered image bytes.
  - Return a PageFingerprint dataclass for downstream provenance.

Requires PyMuPDF (fitz).
"""

from __future__ import annotations

import logging
from pathlib import Path

import blake3
import fitz  # PyMuPDF

from extraction.schemas import PageFingerprint

logger = logging.getLogger(__name__)

DEFAULT_DPI = 200


def render_page(
    pdf_path: Path,
    page_index: int,
    out_dir: Path,
    *,
    dpi: int = DEFAULT_DPI,
) -> PageFingerprint:
    """Render a single PDF page to PNG and return its fingerprint.

    Args:
        pdf_path: Path to the source PDF.
        page_index: 0-based page index.
        out_dir: Directory to write the rendered PNG.
        dpi: Render resolution (default 200).

    Returns:
        PageFingerprint with image path, blake3 digest, and provenance.

    Raises:
        FileNotFoundError: If *pdf_path* does not exist.
        IndexError: If *page_index* is out of range.
    """
    pdf_path = pdf_path.resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    if page_index < 0 or page_index >= len(doc):
        raise IndexError(
            f"page_index {page_index} out of range (PDF has {len(doc)} pages)"
        )

    page = doc.load_page(page_index)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)

    image_name = f"{pdf_path.stem}_p{page_index}.png"
    image_path = out_dir / image_name
    pix.save(str(image_path))

    # Compute blake3 fingerprint of the rendered image bytes
    image_bytes = image_path.read_bytes()
    fingerprint = blake3.blake3(image_bytes).hexdigest()

    logger.info(
        "Rendered %s page %d → %s  fingerprint=%s",
        pdf_path.name,
        page_index,
        image_path.name,
        fingerprint[:16],
    )

    return PageFingerprint(
        image_path=str(image_path),
        fingerprint=fingerprint,
        source_pdf=str(pdf_path),
        page_index=page_index,
        dpi=dpi,
    )

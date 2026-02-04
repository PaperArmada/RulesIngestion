"""
Document Identity & Multi-PDF Normalization (Stage A Sub-Contract).

Physical PDFs → Logical Document. One Logical Document per (ruleset_id, book_id).
Deterministic part order and logical page indices (monotonic across parts).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

try:
    import blake3
except ImportError:
    blake3 = None  # type: ignore

from extraction.schemas import DocumentPart, LogicalDocument


def pdf_content_hash(pdf_path: Path, chunk_size: int = 8192) -> str:
    """Content hash for a PDF. Deterministic. Used for logical_doc_id and part ordering."""
    path = Path(pdf_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    if blake3:
        h = blake3.blake3()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _logical_doc_id(ruleset_id: str, book_id: str, sorted_pdf_hashes: list[str]) -> str:
    """Deterministic logical_doc_id from (ruleset_id, book_id, sorted(source_pdf_hashes))."""
    payload = f"{ruleset_id}|{book_id}|{'|'.join(sorted_pdf_hashes)}"
    if blake3:
        return blake3.blake3(payload.encode()).hexdigest()[:32]
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _document_part_id(logical_doc_id: str, source_pdf_id: str, part_index: int) -> str:
    """Deterministic document_part_id."""
    payload = f"{logical_doc_id}|{source_pdf_id}|{part_index}"
    if blake3:
        return blake3.blake3(payload.encode()).hexdigest()[:24]
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def build_logical_document_single_pdf(
    ruleset_id: str,
    book_id: str,
    source_pdf_id: str,
    pdf_hash: str,
    num_pages: int,
) -> tuple[LogicalDocument, DocumentPart]:
    """
    One PDF → one Logical Document with one DocumentPart.
    logical_page_index = source_pdf_page_index (page_offset = 0).
    A-DOC-INV-1: one Logical Document per (ruleset_id, book_id) for single-PDF.
    """
    logical_doc_id = _logical_doc_id(ruleset_id, book_id, [pdf_hash])
    part = DocumentPart(
        document_part_id=_document_part_id(logical_doc_id, source_pdf_id, 0),
        logical_doc_id=logical_doc_id,
        source_pdf_id=source_pdf_id,
        part_index=0,
        page_offset=0,
        num_pages=num_pages,
    )
    doc = LogicalDocument(
        logical_doc_id=logical_doc_id,
        ruleset_id=ruleset_id,
        book_id=book_id,
        document_parts=[part],
    )
    return doc, part


def build_logical_document_multi_pdf(
    ruleset_id: str,
    book_id: str,
    parts_spec: list[tuple[str, str, int]],  # (source_pdf_id, pdf_hash, num_pages)
    part_order: list[int] | None = None,
) -> tuple[LogicalDocument, list[DocumentPart]]:
    """
    Multiple PDFs → one Logical Document with ordered DocumentParts.
    Part order: part_order if provided; else sorted by (pdf_hash, source_pdf_id) for determinism.
    Logical page indices: monotonic across parts (page_offset cumulative).
    A-DOC-INV-1: one Logical Document per (ruleset_id, book_id).
    """
    if not parts_spec:
        raise ValueError("parts_spec must be non-empty")
    hashes = [h for (_, h, _) in parts_spec]
    logical_doc_id = _logical_doc_id(ruleset_id, book_id, sorted(hashes))
    if part_order is not None:
        order = part_order
    else:
        # Fallback: sort by (pdf_hash, source_pdf_id) for deterministic order
        order = sorted(range(len(parts_spec)), key=lambda i: (parts_spec[i][1], parts_spec[i][0]))
    document_parts: list[DocumentPart] = []
    page_offset = 0
    for idx, i in enumerate(order):
        source_pdf_id, pdf_hash, num_pages = parts_spec[i]
        part = DocumentPart(
            document_part_id=_document_part_id(logical_doc_id, source_pdf_id, idx),
            logical_doc_id=logical_doc_id,
            source_pdf_id=source_pdf_id,
            part_index=idx,
            page_offset=page_offset,
            num_pages=num_pages,
        )
        document_parts.append(part)
        page_offset += num_pages
    doc = LogicalDocument(
        logical_doc_id=logical_doc_id,
        ruleset_id=ruleset_id,
        book_id=book_id,
        document_parts=document_parts,
    )
    return doc, document_parts


def source_to_logical_page(document_parts: list[DocumentPart], source_pdf_id: str, source_page: int) -> int:
    """Map (source_pdf_id, source_pdf_page_index) → logical_page_index."""
    for part in document_parts:
        if part.source_pdf_id == source_pdf_id:
            return part.page_offset + source_page
    return source_page  # fallback if part not found

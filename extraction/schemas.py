"""
Stage A schemas: MarkerBlock (A1), Chunk (A2), DropRecord, LogicalDocument, DocumentPart.

Contracts: Stage A — Extraction Integrity; Stage A Sub-Contract — Document Identity & Multi-PDF.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# -----------------------------------------------------------------------------
# Document Identity (A-DOC-1, A-DOC-2)
# -----------------------------------------------------------------------------


@dataclass
class DocumentPart:
    """Physical PDF contribution. A-DOC-2. Provenance without authority."""

    document_part_id: str
    logical_doc_id: str
    source_pdf_id: str
    part_index: int
    page_offset: int  # logical_page_index = page_offset + source_pdf_page_index
    num_pages: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_part_id": self.document_part_id,
            "logical_doc_id": self.logical_doc_id,
            "source_pdf_id": self.source_pdf_id,
            "part_index": self.part_index,
            "page_offset": self.page_offset,
            "num_pages": self.num_pages,
        }


@dataclass
class LogicalDocument:
    """Authoritative ingestion unit (A-DOC-1). One per (ruleset_id, book_id) unless configured otherwise."""

    logical_doc_id: str
    ruleset_id: str
    book_id: str
    document_parts: list[DocumentPart] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "logical_doc_id": self.logical_doc_id,
            "ruleset_id": self.ruleset_id,
            "book_id": self.book_id,
            "document_parts": [p.to_dict() for p in self.document_parts],
        }


# -----------------------------------------------------------------------------
# MarkerStream (A1) — with A-DOC-INV-4 provenance
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class MarkerBlock:
    """Raw extraction block (MarkerStream A1). Immutable. A-DOC-INV-4: provenance preserved."""

    doc_id: str
    page_index: int
    text: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 or empty
    raw_block_type: str
    block_ordinal: int
    section_hierarchy: dict[str, Any] = field(default_factory=dict)
    # Document identity (A-DOC-INV-4). When empty/-1, downstream uses doc_id/page_index.
    logical_doc_id: str = ""
    document_part_id: str = ""
    source_pdf_id: str = ""
    source_pdf_page_index: int = -1
    logical_page_index: int = -1

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "doc_id": self.doc_id,
            "page_index": self.page_index,
            "text": self.text,
            "bbox": list(self.bbox) if self.bbox else [],
            "raw_block_type": self.raw_block_type,
            "block_ordinal": self.block_ordinal,
            "section_hierarchy": self.section_hierarchy,
        }
        d["logical_doc_id"] = self.logical_doc_id or self.doc_id
        d["document_part_id"] = self.document_part_id or self.doc_id
        d["source_pdf_id"] = self.source_pdf_id or self.doc_id
        d["source_pdf_page_index"] = self.source_pdf_page_index if self.source_pdf_page_index >= 0 else self.page_index
        d["logical_page_index"] = self.logical_page_index if self.logical_page_index >= 0 else self.page_index
        return d

    @property
    def effective_logical_doc_id(self) -> str:
        return self.logical_doc_id or self.doc_id

    @property
    def effective_logical_page_index(self) -> int:
        return self.logical_page_index if self.logical_page_index >= 0 else self.page_index


SpanLocality = Literal["page", "block"]


@dataclass
class ProvenanceSpan:
    """Source span with explicit locality (A-INV-1)."""

    start: int
    end: int
    locality: SpanLocality

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError(f"Invalid span: start={self.start}, end={self.end}")


@dataclass
class Chunk:
    """Intentional extraction chunk (A2). Variable-sized, structural metadata. A-DOC-INV-4: provenance retained."""

    chunk_id: str
    doc_id: str
    page_index: int
    section_path: list[str]  # doc → section/chapter → page (structural address)
    block_type: str  # normalized: Text, Heading, Table, Figure, List, Footnote, Unknown
    text: str
    span_start: int
    span_end: int
    span_locality: SpanLocality
    bbox: tuple[float, float, float, float]
    block_ordinals: list[int]  # source block ordinals (within page)
    structural_metadata: dict[str, Any] = field(default_factory=dict)
    # Document identity (A-DOC-INV-4). When empty/-1, use doc_id/page_index.
    logical_doc_id: str = ""
    document_part_id: str = ""
    source_pdf_id: str = ""
    source_pdf_page_index: int = -1
    logical_page_index: int = -1

    def __post_init__(self) -> None:
        if self.span_start < 0 or self.span_end <= self.span_start:
            raise ValueError(
                f"Invalid span: span_start={self.span_start}, span_end={self.span_end}"
            )
        if not self.text.strip():
            raise ValueError("Chunk text must be non-empty after normalization")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "page_index": self.page_index,
            "section_path": self.section_path,
            "block_type": self.block_type,
            "text": self.text,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "span_locality": self.span_locality,
            "bbox": list(self.bbox) if self.bbox else [],
            "block_ordinals": self.block_ordinals,
            "structural_metadata": self.structural_metadata,
        }
        d["logical_doc_id"] = self.logical_doc_id or self.doc_id
        d["document_part_id"] = self.document_part_id or self.doc_id
        d["source_pdf_id"] = self.source_pdf_id or self.doc_id
        d["source_pdf_page_index"] = self.source_pdf_page_index if self.source_pdf_page_index >= 0 else self.page_index
        d["logical_page_index"] = self.logical_page_index if self.logical_page_index >= 0 else self.page_index
        return d


@dataclass
class DropRecord:
    """Explicit record for every dropped block (A-INV-5)."""

    reason_code: str
    page_index: int
    block_reference: str  # e.g. block ordinal or id
    source_pdf_id: str = ""  # for form vs rulebook scoping (M-A3 rulebook-only)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "page_index": self.page_index,
            "block_reference": self.block_reference,
            "source_pdf_id": self.source_pdf_id,
        }

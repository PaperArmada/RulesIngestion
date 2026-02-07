"""Tests for extraction.document_identity: Logical Document, DocumentPart, provenance."""

from pathlib import Path

import pytest

from extraction.document_identity import (
    build_logical_document_single_pdf,
    build_logical_document_multi_pdf,
    source_to_logical_page,
)
from extraction.schemas import DocumentPart, LogicalDocument


def test_build_logical_document_single_pdf() -> None:
    doc, part = build_logical_document_single_pdf(
        ruleset_id="r1",
        book_id="b1",
        source_pdf_id="pdf1",
        pdf_hash="abc123",
        num_pages=10,
    )
    assert isinstance(doc, LogicalDocument)
    assert isinstance(part, DocumentPart)
    assert doc.logical_doc_id
    assert doc.ruleset_id == "r1"
    assert doc.book_id == "b1"
    assert len(doc.document_parts) == 1
    assert part.page_offset == 0
    assert part.part_index == 0
    assert part.source_pdf_id == "pdf1"
    assert part.logical_doc_id == doc.logical_doc_id


def test_build_logical_document_single_pdf_deterministic() -> None:
    doc1, _ = build_logical_document_single_pdf("r1", "b1", "pdf1", "hash1", 5)
    doc2, _ = build_logical_document_single_pdf("r1", "b1", "pdf1", "hash1", 5)
    assert doc1.logical_doc_id == doc2.logical_doc_id


def test_build_logical_document_multi_pdf() -> None:
    parts_spec = [
        ("pdf-a", "hash_a", 5),
        ("pdf-b", "hash_b", 3),
    ]
    doc, parts = build_logical_document_multi_pdf("r1", "b1", parts_spec)
    assert len(parts) == 2
    assert parts[0].page_offset == 0
    assert parts[1].page_offset == 5
    assert doc.logical_doc_id
    assert len(doc.document_parts) == 2


def test_source_to_logical_page() -> None:
    parts = [
        DocumentPart("part1", "log1", "pdf1", 0, 0, 5),
        DocumentPart("part2", "log1", "pdf2", 1, 5, 3),
    ]
    assert source_to_logical_page(parts, "pdf1", 0) == 0
    assert source_to_logical_page(parts, "pdf1", 2) == 2
    assert source_to_logical_page(parts, "pdf2", 0) == 5
    assert source_to_logical_page(parts, "pdf2", 2) == 7

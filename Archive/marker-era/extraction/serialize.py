"""
Deterministic serialization for MarkerStream and Chunk[] (M-A1 hashing).

Contract: encoding is implementation-defined; determinism required.
"""

from __future__ import annotations

import json
from typing import Any

try:
    import blake3
except ImportError:
    blake3 = None  # type: ignore

from extraction.schemas import Chunk, MarkerBlock


def _block_to_sortable_dict(b: MarkerBlock) -> dict[str, Any]:
    d: dict[str, Any] = {
        "doc_id": b.doc_id,
        "page_index": b.page_index,
        "text": b.text,
        "bbox": list(b.bbox),
        "raw_block_type": b.raw_block_type,
        "block_ordinal": b.block_ordinal,
        "section_hierarchy": b.section_hierarchy,
    }
    d["logical_doc_id"] = b.logical_doc_id or b.doc_id
    d["document_part_id"] = b.document_part_id
    d["source_pdf_id"] = b.source_pdf_id or b.doc_id
    d["source_pdf_page_index"] = b.source_pdf_page_index if b.source_pdf_page_index >= 0 else b.page_index
    d["logical_page_index"] = b.logical_page_index if b.logical_page_index >= 0 else b.page_index
    return d


def _chunk_to_sortable_dict(c: Chunk) -> dict[str, Any]:
    d: dict[str, Any] = {
        "chunk_id": c.chunk_id,
        "doc_id": c.doc_id,
        "page_index": c.page_index,
        "section_path": c.section_path,
        "block_type": c.block_type,
        "text": c.text,
        "span_start": c.span_start,
        "span_end": c.span_end,
        "span_locality": c.span_locality,
        "bbox": list(c.bbox),
        "block_ordinals": c.block_ordinals,
        "structural_metadata": c.structural_metadata,
    }
    d["logical_doc_id"] = c.logical_doc_id or c.doc_id
    d["document_part_id"] = c.document_part_id
    d["source_pdf_id"] = c.source_pdf_id or c.doc_id
    d["source_pdf_page_index"] = c.source_pdf_page_index if c.source_pdf_page_index >= 0 else c.page_index
    d["logical_page_index"] = c.logical_page_index if c.logical_page_index >= 0 else c.page_index
    return d


def deterministic_serialize_marker_stream(stream: list[MarkerBlock]) -> bytes:
    """Canonical bytes for MarkerStream (stable key order, no whitespace)."""
    data = [_block_to_sortable_dict(b) for b in stream]
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def deterministic_serialize_chunks(chunks: list[Chunk]) -> bytes:
    """Canonical bytes for Chunk[] (stable key order, no whitespace)."""
    data = [_chunk_to_sortable_dict(c) for c in chunks]
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# Consistent hash length when using sha256 fallback (match ID convention: 32 hex chars).
_HASH_HEX_LEN = 32


def markerstream_hash(stream: list[MarkerBlock]) -> str:
    """M-A1: blake3(deterministic_serialize(MarkerStream)). sha256 fallback truncated to 32 hex chars."""
    raw = deterministic_serialize_marker_stream(stream)
    if blake3:
        return blake3.blake3(raw).hexdigest()
    import hashlib
    return hashlib.sha256(raw).hexdigest()[:_HASH_HEX_LEN]


def chunkset_hash(chunks: list[Chunk]) -> str:
    """M-A1: blake3(deterministic_serialize(Chunk[])). sha256 fallback truncated to 32 hex chars."""
    raw = deterministic_serialize_chunks(chunks)
    if blake3:
        return blake3.blake3(raw).hexdigest()
    import hashlib
    return hashlib.sha256(raw).hexdigest()[:_HASH_HEX_LEN]

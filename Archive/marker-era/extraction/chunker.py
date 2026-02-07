"""
MarkerStream → Chunk[] + DropRecords.

Intentional boundaries by structural scope (section/chapter + page); heading path
as metadata until next structural change; deterministic chunk_id; tunable drop policy.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

try:
    import blake3
except ImportError:
    blake3 = None  # type: ignore

from extraction.normalize import (
    build_section_path,
    is_empty_structural_content,
    is_table_like_text,
    leaf_path,
    normalize_block_type,
    normalize_text,
    resolve_paths_to_titles,
)
from extraction.gates import _weird_ratio
from extraction.schemas import Chunk, DropRecord, MarkerBlock


@dataclass
class ExtractionResult:
    """Result of Stage A: MarkerStream (as list), Chunks, DropRecords, optional empty-structural side-channel."""

    marker_stream: list[MarkerBlock]
    chunks: list[Chunk]
    drop_records: list[DropRecord]
    empty_structural_blocks: list[MarkerBlock] = field(default_factory=list)  # TableCell/Text with no text; preserved for markdown


def _chunk_id(doc_id: str, page_index: int, ord_start: int, section_key: str, block_type: str) -> str:
    """Deterministic chunk_id from doc_id, page, block ordinal start, section, type."""
    payload = f"{doc_id}|{page_index}|{ord_start}|{section_key}|{block_type}"
    if blake3:
        return blake3.blake3(payload.encode()).hexdigest()[:24]
    import hashlib
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def _bbox_union(bboxes: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    if not bboxes:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [b[0] for b in bboxes] + [b[2] for b in bboxes]
    ys = [b[1] for b in bboxes] + [b[3] for b in bboxes]
    return (min(xs), min(ys), max(xs), max(ys))


def _default_should_drop(block: MarkerBlock) -> tuple[bool, str]:
    """Default drop policy: drop only empty text. Returns (drop, reason_code)."""
    if not block.text or not block.text.strip():
        return True, "empty_text"
    return False, ""


def _build_heading_registry(marker_stream: list[MarkerBlock]) -> dict[str, str]:
    """
    Build path -> heading title map from marker stream.

    For each block with raw_block_type normalizing to Heading, registers the leaf
    path from section_hierarchy with block.text as the title.
    """
    registry: dict[str, str] = {}
    for block in marker_stream:
        if normalize_block_type(block.raw_block_type) != "Heading":
            continue
        path = leaf_path(block.section_hierarchy)
        if path and block.text:
            registry[path] = block.text.strip()
    return registry


def stream_to_chunks(
    marker_stream: list[MarkerBlock],
    doc_id: str,
    should_drop: Callable[[MarkerBlock], tuple[bool, str]] | None = None,
) -> ExtractionResult:
    """doc_id: used when blocks have no logical_doc_id (single-PDF legacy)."""
    """
    Convert MarkerStream to Chunk[] with intentional boundaries. Group by
    (section_path, page) until next heading or section change. Emit DropRecord
    for every dropped block.
    """
    if should_drop is None:
        should_drop = _default_should_drop
    heading_registry = _build_heading_registry(marker_stream)
    chunks: list[Chunk] = []
    drop_records: list[DropRecord] = []
    current_section_path: list[str] = []  # path-based for stable chunk_id and comparisons
    current_blocks: list[MarkerBlock] = []
    current_page = -1

    def flush() -> None:
        nonlocal current_blocks, current_section_path
        if not current_blocks:
            return
        texts = [normalize_text(b.text) for b in current_blocks if b.text.strip()]
        if not texts:
            current_blocks = []
            return
        combined_text = "\n\n".join(texts)
        block_types = [normalize_block_type(b.raw_block_type) for b in current_blocks]
        counts = Counter(block_types)
        if not counts:
            primary_type = "Text"
        else:
            top = counts.most_common(2)
            primary_type = top[0][0]
            if len(top) == 2 and top[0][1] == top[1][1] and "Text" in (top[0][0], top[1][0]):
                primary_type = "Text"  # Tiebreaker: prefer Text over Heading for body content
        # If a Heading chunk is actually table/index-like content, recategorize as Table.
        if primary_type == "Heading" and (
            is_table_like_text(combined_text) or _weird_ratio(combined_text) > 0.15
        ):
            primary_type = "Table"
        first = current_blocks[0]
        doc_id_use = first.effective_logical_doc_id
        page_index = first.effective_logical_page_index
        ord_start = first.block_ordinal
        ords = [b.block_ordinal for b in current_blocks]
        bboxes = [b.bbox for b in current_blocks if b.bbox != (0.0, 0.0, 0.0, 0.0)]
        if not bboxes:
            bboxes = [b.bbox for b in current_blocks]
        bbox = _bbox_union(bboxes) if bboxes else (0.0, 0.0, 0.0, 0.0)
        # Use path-based section_key for stable chunk_id (backward compatibility)
        section_key = "|".join(current_section_path) if current_section_path else ""
        chunk_id = _chunk_id(doc_id_use, page_index, ord_start, section_key, primary_type)
        # Semantic section_path for retrieval and display
        section_path_semantic = resolve_paths_to_titles(current_section_path, heading_registry)
        chunk = Chunk(
            chunk_id=chunk_id,
            doc_id=doc_id_use,
            page_index=page_index,
            section_path=section_path_semantic,
            block_type=primary_type,
            text=combined_text,
            span_start=0,
            span_end=len(combined_text),
            span_locality="block",
            bbox=bbox,
            block_ordinals=ords,
            structural_metadata={"section_path": section_path_semantic},
            logical_doc_id=first.logical_doc_id or first.doc_id,
            document_part_id=first.document_part_id,
            source_pdf_id=first.source_pdf_id or first.doc_id,
            source_pdf_page_index=first.source_pdf_page_index if first.source_pdf_page_index >= 0 else first.page_index,
            logical_page_index=first.logical_page_index if first.logical_page_index >= 0 else first.page_index,
        )
        chunks.append(chunk)
        current_blocks = []

    empty_structural: list[MarkerBlock] = []
    for block in marker_stream:
        drop, reason = should_drop(block)
        if drop:
            # Preserve empty TableCell/Text in side-channel; do not count as dropped (standard pattern).
            if reason == "empty_text" and is_empty_structural_content(block.raw_block_type, block.text):
                empty_structural.append(block)
                continue
            drop_records.append(DropRecord(
                reason_code=reason or "dropped",
                page_index=block.page_index,
                block_reference=f"page={block.page_index},ord={block.block_ordinal}",
                source_pdf_id=block.source_pdf_id or block.doc_id,
            ))
            continue
        section_path = build_section_path(block.section_hierarchy)
        is_heading = normalize_block_type(block.raw_block_type) == "Heading"
        page = block.page_index
        section_changed = section_path != current_section_path
        page_changed = page != current_page

        if current_blocks and (section_changed or (is_heading and current_blocks)):
            flush()
        if is_heading:
            current_section_path = section_path
        elif not current_section_path and section_path:
            current_section_path = section_path
        current_page = page
        current_blocks.append(block)
    flush()
    return ExtractionResult(
        marker_stream=marker_stream,
        chunks=chunks,
        drop_records=drop_records,
        empty_structural_blocks=empty_structural,
    )

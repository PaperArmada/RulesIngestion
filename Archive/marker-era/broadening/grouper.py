"""
Stage B grouper: Convert Chunks to EvidenceChunks via deterministic grouping.

Implements the 4 closed-set grouping rules plus single-chunk emission:
1. Heading Span Grouping
2. Paragraph Run Grouping
3. Table Consolidation
4. Rule Block Expansion
5. Single-chunk emission for isolated eligible chunks (no content dropped without robust reason)

Principle: Do not exclude content unless there is a robust reason to drop it.
- Groups below semantic/tabular mass or over-broad are still emitted as EvidenceChunks
  with structural_metadata so downstream can treat them differently if desired.
- Eligible chunks that never merge into a group are emitted as single-chunk EvidenceChunks
  rather than left ungrouped.

Contract: Stage B — Chunk Quality & Context Broadening.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .eligibility import filter_eligible, classify_ineligibility
from .structural import build_content_path_index, content_path_for_rule_header
from .schemas import (
    EvidenceChunk,
    EvidenceKind,
    GroupingRule,
    GroupingStopReason,
    SourceSpan,
    UngroupedRecord,
)

if TYPE_CHECKING:
    from extraction.schemas import Chunk


# -----------------------------------------------------------------------------
# Semantic Mass Thresholds (B-INV-2)
# -----------------------------------------------------------------------------

# Prose thresholds
MIN_CHARS = 300
MIN_TOKENS = 80
MIN_SENTENCES = 2
MAX_CHARS = 2000  # Over-broad threshold (M-B3 gate)
# Tighter cap for rule/definition blocks so they stay focused
RULE_BLOCK_MAX_CHARS = 1200

# Tabular thresholds
MIN_TABLE_ROWS = 3
MIN_TABLE_KEYS = 5


# -----------------------------------------------------------------------------
# Semantic Mass Validation
# -----------------------------------------------------------------------------


def meets_prose_mass(text: str) -> bool:
    """
    Check if text meets Prose EvidenceChunk semantic mass thresholds (B-INV-2).

    Requirements:
    - min_chars >= 300
    - min_tokens >= 80
    - sentence_count >= 2
    """
    if len(text) < MIN_CHARS:
        return False

    tokens = text.split()
    if len(tokens) < MIN_TOKENS:
        return False

    # Count sentences by periods, question marks, exclamation points
    sentence_endings = text.count(".") + text.count("?") + text.count("!")
    return sentence_endings >= MIN_SENTENCES


def meets_tabular_mass(chunk_count: int, distinct_keys: int = 0) -> bool:
    """
    Check if table chunks meet Tabular EvidenceChunk thresholds (B-INV-2).

    Requirements:
    - >= MIN_TABLE_ROWS rows OR >= MIN_TABLE_KEYS distinct keys
    """
    return chunk_count >= MIN_TABLE_ROWS or distinct_keys >= MIN_TABLE_KEYS


# -----------------------------------------------------------------------------
# Boundary Detection (B-INV-3, B-INV-4, B-INV-6)
# -----------------------------------------------------------------------------


def same_section_prefix(a: "Chunk", b: "Chunk") -> bool:
    """
    Check if chunks share a CDS structural path prefix (B-INV-3).

    For Prose EvidenceChunks, all source chunks must belong to exactly
    one CDS leaf path (B-INV-6).
    """
    if not a.section_path and not b.section_path:
        # Both empty — fall back to page comparison
        return a.page_index == b.page_index

    if not a.section_path or not b.section_path:
        # One has path, one doesn't — not same section
        return False

    # Check shared prefix
    min_len = min(len(a.section_path), len(b.section_path))
    return a.section_path[:min_len] == b.section_path[:min_len]


def is_chapter_boundary(a: "Chunk", b: "Chunk") -> bool:
    """
    Detect if there's a chapter boundary between chunks (B-INV-4).

    EvidenceChunks must not cross chapter boundaries.
    """
    if not a.section_path or not b.section_path:
        return False

    # Different top-level section = chapter boundary
    return a.section_path[0] != b.section_path[0]


def is_rule_boundary(a: "Chunk", b: "Chunk") -> bool:
    """
    Detect if there's a rule/procedure boundary between chunks (B-INV-4).

    Heuristic: A new Heading chunk often signals a new rule boundary.
    """
    return b.block_type == "Heading"


def are_consecutive(a: "Chunk", b: "Chunk") -> bool:
    """Check if two chunks are consecutive on the same page."""
    if a.page_index != b.page_index:
        return False

    # Check block ordinals for adjacency
    if a.block_ordinals and b.block_ordinals:
        a_max = max(a.block_ordinals)
        b_min = min(b.block_ordinals)
        # Allow gap of 1 for potential structural blocks in between
        return b_min - a_max <= 2

    return True


# -----------------------------------------------------------------------------
# ID Generation (Determinism Contract)
# -----------------------------------------------------------------------------


def _evidence_chunk_id(
    doc_hash: str,
    source_chunk_ids: list[str],
    grouping_rule_id: str,
) -> str:
    """
    Generate deterministic EvidenceChunk ID.

    Per contract: (doc_hash, sorted(source_chunk_ids), grouping_rule_id)
    """
    sorted_ids = ",".join(sorted(source_chunk_ids))
    payload = f"{doc_hash}|{sorted_ids}|{grouping_rule_id}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


# -----------------------------------------------------------------------------
# Group Builder
# -----------------------------------------------------------------------------


@dataclass
class ChunkGroup:
    """Intermediate structure for building an EvidenceChunk."""

    chunks: list["Chunk"]
    rule: GroupingRule
    stop_reason: GroupingStopReason | None = None

    @property
    def text(self) -> str:
        """Combined text with paragraph separators."""
        return "\n\n".join(c.text for c in self.chunks)

    @property
    def source_chunk_ids(self) -> list[str]:
        return [c.chunk_id for c in self.chunks]

    @property
    def source_spans(self) -> list[SourceSpan]:
        return [
            SourceSpan(
                chunk_id=c.chunk_id,
                page_index=c.page_index,
                span_start=c.span_start,
                span_end=c.span_end,
            )
            for c in self.chunks
        ]

    @property
    def page_indices(self) -> list[int]:
        pages = sorted(set(c.page_index for c in self.chunks))
        return pages

    @property
    def section_path(self) -> list[str]:
        """Shared section path prefix."""
        if not self.chunks:
            return []

        paths = [c.section_path for c in self.chunks if c.section_path]
        if not paths:
            return []

        # Find common prefix
        prefix = list(paths[0])
        for path in paths[1:]:
            new_prefix = []
            for i, (a, b) in enumerate(zip(prefix, path)):
                if a == b:
                    new_prefix.append(a)
                else:
                    break
            prefix = new_prefix

        return prefix

    @property
    def logical_doc_id(self) -> str:
        if self.chunks:
            return self.chunks[0].logical_doc_id or self.chunks[0].doc_id
        return ""

    @property
    def kind(self) -> EvidenceKind:
        """Determine if this is Prose or Tabular."""
        if self.rule == GroupingRule.TABLE_CONSOLIDATION:
            return "Tabular"
        # Check if any chunk is a Table
        for c in self.chunks:
            if c.block_type == "Table":
                return "Tabular"
        return "Prose"


def _build_evidence_chunk(
    group: ChunkGroup,
    doc_hash: str,
    structural_metadata: dict | None = None,
) -> EvidenceChunk:
    """Convert a ChunkGroup to an EvidenceChunk."""
    return EvidenceChunk(
        evidence_chunk_id=_evidence_chunk_id(
            doc_hash,
            group.source_chunk_ids,
            group.rule.value,
        ),
        kind=group.kind,
        text=group.text,
        source_chunk_ids=group.source_chunk_ids,
        source_spans=group.source_spans,
        logical_doc_id=group.logical_doc_id,
        grouping_rule_id=group.rule.value,
        grouping_stop_reason=(
            group.stop_reason.value if group.stop_reason else GroupingStopReason.END_OF_SECTION.value
        ),
        section_path=group.section_path,
        page_indices=group.page_indices,
        structural_metadata=structural_metadata or {},
    )


def _build_single_chunk_evidence(chunk: "Chunk", doc_hash: str) -> EvidenceChunk:
    """Build an EvidenceChunk from a single Chunk (isolated eligible chunk)."""
    group = ChunkGroup(
        chunks=[chunk],
        rule=GroupingRule.SINGLE_CHUNK,
        stop_reason=GroupingStopReason.BOUNDARY_ENCOUNTERED,
    )
    return _build_evidence_chunk(group, doc_hash)


# -----------------------------------------------------------------------------
# Grouping Rules Implementation
# -----------------------------------------------------------------------------


def _apply_heading_span_grouping(
    chunks: list["Chunk"],
    used: set[str],
    max_chars: int = MAX_CHARS,
) -> list[ChunkGroup]:
    """
    Rule 1: Heading Span Grouping.

    Merge consecutive eligible chunks under the same heading.
    """
    groups: list[ChunkGroup] = []

    i = 0
    while i < len(chunks):
        chunk = chunks[i]

        # Skip already used chunks
        if chunk.chunk_id in used:
            i += 1
            continue

        # Start a new group with a Heading
        if chunk.block_type == "Heading":
            group = ChunkGroup(chunks=[chunk], rule=GroupingRule.HEADING_SPAN)
            used.add(chunk.chunk_id)

            # Collect following chunks under this heading
            j = i + 1
            while j < len(chunks):
                next_chunk = chunks[j]

                if next_chunk.chunk_id in used:
                    j += 1
                    continue

                # Stop conditions
                if is_chapter_boundary(chunk, next_chunk):
                    group.stop_reason = GroupingStopReason.BOUNDARY_ENCOUNTERED
                    break

                if next_chunk.block_type == "Heading":
                    group.stop_reason = GroupingStopReason.BOUNDARY_ENCOUNTERED
                    break

                if not same_section_prefix(chunk, next_chunk):
                    group.stop_reason = GroupingStopReason.BOUNDARY_ENCOUNTERED
                    break

                # Check size threshold (strict: stop before exceeding)
                combined_len = len(group.text) + len(next_chunk.text)
                if combined_len >= max_chars:
                    group.stop_reason = GroupingStopReason.SIZE_THRESHOLD_HIT
                    break

                # Add to group
                group.chunks.append(next_chunk)
                used.add(next_chunk.chunk_id)
                j += 1

            if not group.stop_reason:
                group.stop_reason = GroupingStopReason.END_OF_SECTION

            groups.append(group)

        i += 1

    return groups


def _apply_paragraph_run_grouping(
    chunks: list["Chunk"],
    used: set[str],
    max_chars: int = MAX_CHARS,
) -> list[ChunkGroup]:
    """
    Rule 2: Paragraph Run Grouping.

    Merge consecutive Text blocks without structural breaks.
    """
    groups: list[ChunkGroup] = []

    i = 0
    while i < len(chunks):
        chunk = chunks[i]

        # Skip already used or non-Text chunks
        if chunk.chunk_id in used or chunk.block_type != "Text":
            i += 1
            continue

        group = ChunkGroup(chunks=[chunk], rule=GroupingRule.PARAGRAPH_RUN)
        used.add(chunk.chunk_id)

        # Collect following Text chunks
        j = i + 1
        while j < len(chunks):
            next_chunk = chunks[j]

            if next_chunk.chunk_id in used:
                j += 1
                continue

            # Only merge Text with Text
            if next_chunk.block_type != "Text":
                group.stop_reason = GroupingStopReason.BLOCK_TYPE_MISMATCH
                break

            # Check structural boundary
            if is_chapter_boundary(chunk, next_chunk):
                group.stop_reason = GroupingStopReason.BOUNDARY_ENCOUNTERED
                break

            if not same_section_prefix(group.chunks[-1], next_chunk):
                group.stop_reason = GroupingStopReason.BOUNDARY_ENCOUNTERED
                break

            # Check consecutiveness
            if not are_consecutive(group.chunks[-1], next_chunk):
                group.stop_reason = GroupingStopReason.BOUNDARY_ENCOUNTERED
                break

            # Check size threshold (strict: stop before exceeding)
            combined_len = len(group.text) + len(next_chunk.text)
            if combined_len >= max_chars:
                group.stop_reason = GroupingStopReason.SIZE_THRESHOLD_HIT
                break

            group.chunks.append(next_chunk)
            used.add(next_chunk.chunk_id)
            j += 1

        if not group.stop_reason:
            group.stop_reason = GroupingStopReason.END_OF_SECTION

        groups.append(group)
        i += 1

    return groups


def _apply_table_consolidation(
    chunks: list["Chunk"],
    used: set[str],
) -> list[ChunkGroup]:
    """
    Rule 3: Table Consolidation.

    Merge all chunks belonging to the same table/figure group.
    Uses structural_metadata.table_id or proximity heuristics.
    """
    groups: list[ChunkGroup] = []

    # Group by table identity if available
    table_groups: dict[str, list["Chunk"]] = {}

    for chunk in chunks:
        if chunk.chunk_id in used:
            continue
        if chunk.block_type != "Table":
            continue

        # Try to get table identity from metadata
        table_id = chunk.structural_metadata.get("table_id")
        if not table_id:
            # Fall back to page + section as identity
            table_id = f"{chunk.page_index}_{'.'.join(chunk.section_path)}"

        if table_id not in table_groups:
            table_groups[table_id] = []
        table_groups[table_id].append(chunk)

    for table_id, table_chunks in table_groups.items():
        if not table_chunks:
            continue

        # Sort by ordinal
        sorted_chunks = sorted(
            table_chunks,
            key=lambda c: (c.page_index, min(c.block_ordinals) if c.block_ordinals else 0),
        )

        group = ChunkGroup(
            chunks=sorted_chunks,
            rule=GroupingRule.TABLE_CONSOLIDATION,
            stop_reason=GroupingStopReason.END_OF_SECTION,
        )

        for c in sorted_chunks:
            used.add(c.chunk_id)

        groups.append(group)

    return groups


def _apply_rule_block_expansion_structural(
    sorted_chunks: list["Chunk"],
    used: set[str],
    content_path_index: dict[tuple[str, ...], list["Chunk"]],
    max_chars: int = RULE_BLOCK_MAX_CHARS,
) -> list[ChunkGroup]:
    """
    Rule 4: Rule Block Expansion (Structural).

    Group by content path instead of physical adjacency. When a rule header is
    encountered, find all chunks with the matching content path from the index,
    regardless of physical order. Fixes interleaved content on multi-column PDFs.
    """
    groups: list[ChunkGroup] = []

    for i, header_chunk in enumerate(sorted_chunks):
        if header_chunk.chunk_id in used:
            continue
        if header_chunk.block_type != "Heading":
            continue

        content_path = content_path_for_rule_header(header_chunk, sorted_chunks, i)
        if content_path is None:
            continue

        content_chunks = content_path_index.get(content_path, [])
        content_chunks = [c for c in content_chunks if c.chunk_id not in used]
        if not content_chunks:
            continue

        sorted_content = sorted(
            content_chunks,
            key=lambda c: (c.page_index, min(c.block_ordinals) if c.block_ordinals else 0),
        )

        group_chunks_list: list["Chunk"] = [header_chunk] + sorted_content
        combined_text = "\n\n".join(c.text for c in group_chunks_list)
        combined_len = len(combined_text)

        stop_reason = GroupingStopReason.END_OF_SECTION
        if combined_len >= max_chars:
            stop_reason = GroupingStopReason.SIZE_THRESHOLD_HIT

        group = ChunkGroup(
            chunks=group_chunks_list,
            rule=GroupingRule.RULE_BLOCK,
            stop_reason=stop_reason,
        )

        if len(group.chunks) > 1 or meets_prose_mass(group.text):
            for c in group.chunks:
                used.add(c.chunk_id)
            groups.append(group)

    return groups


# -----------------------------------------------------------------------------
# Main Grouping Function
# -----------------------------------------------------------------------------


def group_chunks(
    chunks: list["Chunk"],
    doc_hash: str = "",
    allow_tables: bool = False,
) -> tuple[list[EvidenceChunk], list[UngroupedRecord]]:
    """
    Convert Stage A Chunks to EvidenceChunks using closed-set grouping rules.

    Args:
        chunks: List of Stage A Chunks
        doc_hash: Document hash for ID generation
        allow_tables: If True, include Table chunks in eligible set

    Returns:
        Tuple of (EvidenceChunks, UngroupedRecords)
    """
    # Filter to eligible chunks only (B-INV-0)
    eligible = filter_eligible(chunks, allow_tables)

    # Sort by page and ordinal for consistent processing
    sorted_chunks = sorted(
        eligible,
        key=lambda c: (c.page_index, min(c.block_ordinals) if c.block_ordinals else 0),
    )

    # Track which chunks have been used
    used: set[str] = set()

    # Precompute content path index for structural rule_block grouping
    content_path_index = build_content_path_index(sorted_chunks)

    # Apply grouping rules: run paragraph_run and rule_block FIRST so they claim
    # chunks before heading_span. This improves M-B5 (rule diversity) and
    # reduces over-broad groups (M-B3).
    all_groups: list[ChunkGroup] = []

    # Rule 1: Rule Block (structural grouping by content path) — run first
    all_groups.extend(
        _apply_rule_block_expansion_structural(
            sorted_chunks, used, content_path_index, max_chars=RULE_BLOCK_MAX_CHARS
        )
    )

    # Rule 2: Paragraph Run (consecutive Text blocks)
    all_groups.extend(_apply_paragraph_run_grouping(sorted_chunks, used))

    # Rule 3: Heading Span (remaining Heading + following)
    all_groups.extend(_apply_heading_span_grouping(sorted_chunks, used))

    # Rule 4: Table Consolidation (if tables allowed)
    if allow_tables:
        all_groups.extend(_apply_table_consolidation(sorted_chunks, used))

    # Convert groups to EvidenceChunks
    evidence_chunks: list[EvidenceChunk] = []
    ungrouped: list[UngroupedRecord] = []

    for group in all_groups:
        kind = group.kind

        # Include all groups; only annotate when they fall outside preferred thresholds
        # (Principle: do not exclude without robust reason to drop.)
        structural_metadata: dict = {}

        if kind == "Prose" and not meets_prose_mass(group.text):
            structural_metadata["below_preferred_mass"] = True
        if kind == "Prose" and len(group.text) > MAX_CHARS:
            structural_metadata["over_broad"] = True
        if kind == "Tabular" and not meets_tabular_mass(len(group.chunks)):
            structural_metadata["below_tabular_mass"] = True

        evidence_chunks.append(_build_evidence_chunk(group, doc_hash, structural_metadata))

    # Emit isolated eligible chunks as single-chunk EvidenceChunks (do not drop without robust reason)
    for chunk in sorted_chunks:
        if chunk.chunk_id not in used:
            reason = classify_ineligibility(chunk)
            if reason is None and (chunk.text or "").strip():
                evidence_chunks.append(_build_single_chunk_evidence(chunk, doc_hash))
            else:
                ungrouped.append(UngroupedRecord(
                    chunk_id=chunk.chunk_id,
                    reason=reason or "empty_text",
                    page_index=chunk.page_index,
                ))

    return evidence_chunks, ungrouped

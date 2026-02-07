"""
Stage B schemas: EvidenceChunk, SourceSpan, GroupingRule.

Contract: Stage B — Chunk Quality & Context Broadening.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


# -----------------------------------------------------------------------------
# Grouping Rules (Closed Set per B-INV-5)
# -----------------------------------------------------------------------------


class GroupingRule(str, Enum):
    """Allowed grouping strategies (closed set per contract)."""

    HEADING_SPAN = "heading_span"
    PARAGRAPH_RUN = "paragraph_run"
    TABLE_CONSOLIDATION = "table_consolidation"
    RULE_BLOCK = "rule_block"
    # Emit isolated eligible chunks as evidence rather than dropping (inclusive-default principle)
    SINGLE_CHUNK = "single_chunk"


# -----------------------------------------------------------------------------
# Stop Reasons (B-INV-5)
# -----------------------------------------------------------------------------


class GroupingStopReason(str, Enum):
    """Why grouping stopped at a particular boundary."""

    BOUNDARY_ENCOUNTERED = "boundary_encountered"
    SIZE_THRESHOLD_HIT = "size_threshold_hit"
    BLOCK_TYPE_MISMATCH = "block_type_mismatch"
    END_OF_SECTION = "end_of_section"


# -----------------------------------------------------------------------------
# EvidenceChunk Kind
# -----------------------------------------------------------------------------

EvidenceKind = Literal["Prose", "Tabular"]


# -----------------------------------------------------------------------------
# SourceSpan (B-INV-1 Provenance)
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceSpan:
    """Provenance reference to a source Chunk (B-INV-1)."""

    chunk_id: str
    page_index: int
    span_start: int
    span_end: int

    def __post_init__(self) -> None:
        if self.span_start < 0 or self.span_end <= self.span_start:
            raise ValueError(
                f"Invalid span: span_start={self.span_start}, span_end={self.span_end}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "page_index": self.page_index,
            "span_start": self.span_start,
            "span_end": self.span_end,
        }


# -----------------------------------------------------------------------------
# EvidenceChunk (B1 Output)
# -----------------------------------------------------------------------------


@dataclass
class EvidenceChunk:
    """
    Semantically meaningful unit for retrieval (Stage B output).

    The smallest self-contained unit of explanation, definition, or rule
    suitable for retrieval and grounding. Immutable once emitted.

    Invariants enforced:
    - B-INV-1: Full provenance via source_chunk_ids and source_spans
    - B-INV-2: Semantic mass thresholds (Prose: 300 chars, 80 tokens, 2 sentences)
    - B-INV-3: Structural coherence (same CDS path prefix)
    - B-INV-5: Explicit grouping attribution
    - B-INV-6: Structural purity (single CDS leaf path for Prose)
    """

    evidence_chunk_id: str  # Derived: hash(doc_hash, sorted(source_chunk_ids), grouping_rule_id)
    kind: EvidenceKind
    text: str  # Combined text from source chunks

    # Provenance (B-INV-1)
    source_chunk_ids: list[str]  # >= 1
    source_spans: list[SourceSpan]  # One per source chunk
    logical_doc_id: str

    # Grouping attribution (B-INV-5)
    grouping_rule_id: str  # One of GroupingRule values
    grouping_stop_reason: str  # One of GroupingStopReason values

    # Structural (B-INV-3, B-INV-6)
    section_path: list[str]  # CDS path (shared prefix from source chunks)
    page_indices: list[int]  # Source pages (sorted, unique)

    # Optional metadata
    structural_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_chunk_ids:
            raise ValueError("EvidenceChunk must have at least one source_chunk_id")
        if len(self.source_chunk_ids) != len(self.source_spans):
            raise ValueError(
                f"source_chunk_ids ({len(self.source_chunk_ids)}) and "
                f"source_spans ({len(self.source_spans)}) must have same length"
            )
        if not self.text.strip():
            raise ValueError("EvidenceChunk text must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_chunk_id": self.evidence_chunk_id,
            "kind": self.kind,
            "text": self.text,
            "source_chunk_ids": self.source_chunk_ids,
            "source_spans": [s.to_dict() for s in self.source_spans],
            "logical_doc_id": self.logical_doc_id,
            "grouping_rule_id": self.grouping_rule_id,
            "grouping_stop_reason": self.grouping_stop_reason,
            "section_path": self.section_path,
            "page_indices": self.page_indices,
            "structural_metadata": self.structural_metadata,
        }


# -----------------------------------------------------------------------------
# UngroupedRecord (for chunks that couldn't be grouped)
# -----------------------------------------------------------------------------


@dataclass
class UngroupedRecord:
    """Record for chunks that could not be grouped into an EvidenceChunk."""

    chunk_id: str
    reason: str  # e.g., "below_semantic_mass", "ineligible_type", "isolated"
    page_index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "reason": self.reason,
            "page_index": self.page_index,
        }


# -----------------------------------------------------------------------------
# BroadeningResult (Stage B output bundle)
# -----------------------------------------------------------------------------


@dataclass
class BroadeningResult:
    """Complete output from Stage B processing."""

    evidence_chunks: list[EvidenceChunk]
    ungrouped_records: list[UngroupedRecord]
    input_chunk_count: int
    eligible_chunk_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_chunks": [e.to_dict() for e in self.evidence_chunks],
            "ungrouped_records": [u.to_dict() for u in self.ungrouped_records],
            "input_chunk_count": self.input_chunk_count,
            "eligible_chunk_count": self.eligible_chunk_count,
        }

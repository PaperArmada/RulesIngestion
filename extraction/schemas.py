"""
Mark III schemas: Stage A and Stage B data contracts.

Stage A: StageARecord (raw model envelope), SurfaceASTNode / SurfaceAST (structural tree).
Stage B: EvidenceUnit (prose-bound provenance unit).
Shared: PageFingerprint, GateDiagnostic.

All hashes use blake3.  All text is verbatim (no paraphrasing, no inference).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

@dataclass
class PageFingerprint:
    """Rendered page image identity."""

    image_path: str
    fingerprint: str          # blake3 hex digest of image bytes
    source_pdf: str
    page_index: int
    dpi: int = 200

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_path": self.image_path,
            "fingerprint": self.fingerprint,
            "source_pdf": self.source_pdf,
            "page_index": self.page_index,
            "dpi": self.dpi,
        }


@dataclass
class GateDiagnostic:
    """Result of a single quality gate check."""

    gate_name: str
    passed: bool
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_name": self.gate_name,
            "passed": self.passed,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Stage A — Prose Reconstruction
# ---------------------------------------------------------------------------

@dataclass
class StageARecord:
    """Raw model envelope for a single page OCR run."""

    page_fingerprint: str     # blake3 of rendered image
    source_pdf: str
    page_index: int
    model_id: str
    prompt: str
    raw_markdown: str         # verbatim model output
    inference_elapsed_sec: float
    content_hash: str         # blake3 of raw_markdown
    content_version: str = ""  # e.g. "deepseek-ai/DeepSeek-OCR-2-dpi200"

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_fingerprint": self.page_fingerprint,
            "source_pdf": self.source_pdf,
            "page_index": self.page_index,
            "model_id": self.model_id,
            "prompt": self.prompt,
            "raw_markdown": self.raw_markdown,
            "inference_elapsed_sec": self.inference_elapsed_sec,
            "content_hash": self.content_hash,
            "content_version": self.content_version,
        }


@dataclass
class SurfaceASTNode:
    """Structural tree node in the page surface AST."""

    node_type: Literal[
        "heading",
        "paragraph",
        "table",
        "list",
        "callout",
        "sidebar",
        "footnote",
        "image_ref",
        "root",
    ]
    level: int                              # heading level (1-6), 0 for non-headings
    text: str                               # verbatim content
    children: list[SurfaceASTNode] = field(default_factory=list)
    source_line_start: int = 0              # 0-based line index in raw markdown
    source_line_end: int = 0                # exclusive upper bound

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "node_type": self.node_type,
            "level": self.level,
            "text": self.text,
            "source_line_start": self.source_line_start,
            "source_line_end": self.source_line_end,
        }
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> SurfaceASTNode:
        children = [SurfaceASTNode.from_dict(c) for c in d.get("children", [])]
        return SurfaceASTNode(
            node_type=d["node_type"],
            level=d["level"],
            text=d["text"],
            children=children,
            source_line_start=d.get("source_line_start", 0),
            source_line_end=d.get("source_line_end", 0),
        )

    # -- Traversal helpers ---------------------------------------------------

    def leaf_texts(self) -> list[str]:
        """Collect verbatim text from all leaf nodes (depth-first)."""
        if not self.children:
            return [self.text] if self.text else []
        result: list[str] = []
        for child in self.children:
            result.extend(child.leaf_texts())
        return result

    def all_nodes(self) -> list[SurfaceASTNode]:
        """Flat list of all nodes (depth-first pre-order)."""
        nodes: list[SurfaceASTNode] = [self]
        for child in self.children:
            nodes.extend(child.all_nodes())
        return nodes


@dataclass
class SurfaceAST:
    """Top-level container for a page's structural AST."""

    page_fingerprint: str     # links back to PageFingerprint
    content_hash: str         # blake3 of deterministic JSON serialisation
    root: SurfaceASTNode
    node_count: int
    table_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_fingerprint": self.page_fingerprint,
            "content_hash": self.content_hash,
            "root": self.root.to_dict(),
            "node_count": self.node_count,
            "table_count": self.table_count,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> SurfaceAST:
        return SurfaceAST(
            page_fingerprint=d["page_fingerprint"],
            content_hash=d["content_hash"],
            root=SurfaceASTNode.from_dict(d["root"]),
            node_count=d["node_count"],
            table_count=d["table_count"],
        )


# ---------------------------------------------------------------------------
# Stage B — Evidence Binding
# ---------------------------------------------------------------------------

@dataclass
class EvidenceUnit:
    """Prose-bound provenance unit.  The only admissible input to Stage C (Graph Construction)."""

    unit_id: str              # blake3(text + "|" + structural_path_joined)
    unit_type: Literal["prose", "table", "list", "callout", "heading"]
    text: str                 # verbatim
    structural_path: list[str]   # heading ancestry from AST root
    ordering_key: int            # total monotonic order
    page_fingerprint: str        # upstream Stage A identity (primary; first page for joins)
    content_hash: str            # blake3 of text
    source_line_start: int       # back-pointer to raw markdown
    source_line_end: int
    anomaly_flags: list[str] = field(default_factory=list)
    content_version: str = ""    # e.g. "deepseek-ai/DeepSeek-OCR-2-dpi200"
    # R3: Cross-page joins
    page_fingerprints: list[str] = field(default_factory=list)  # expanded for joined units
    table_group_id: str | None = None  # blake3(header_row_hash + "|" + structural_path)
    join_metadata: dict[str, Any] | None = None  # e.g. {"join_type": "paragraph", "merged_unit_id": "..."}
    source_unit_ids: list[str] = field(default_factory=list)  # provenance for join conservation checks

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "unit_id": self.unit_id,
            "unit_type": self.unit_type,
            "text": self.text,
            "structural_path": self.structural_path,
            "ordering_key": self.ordering_key,
            "page_fingerprint": self.page_fingerprint,
            "content_hash": self.content_hash,
            "source_line_start": self.source_line_start,
            "source_line_end": self.source_line_end,
            "anomaly_flags": self.anomaly_flags,
            "content_version": self.content_version,
        }
        if self.page_fingerprints:
            out["page_fingerprints"] = self.page_fingerprints
        if self.table_group_id is not None:
            out["table_group_id"] = self.table_group_id
        if self.join_metadata is not None:
            out["join_metadata"] = self.join_metadata
        if self.source_unit_ids:
            out["source_unit_ids"] = self.source_unit_ids
        return out

    @staticmethod
    def from_dict(d: dict[str, Any]) -> EvidenceUnit:
        return EvidenceUnit(
            unit_id=d["unit_id"],
            unit_type=d["unit_type"],
            text=d["text"],
            structural_path=d["structural_path"],
            ordering_key=d["ordering_key"],
            page_fingerprint=d["page_fingerprint"],
            content_hash=d["content_hash"],
            source_line_start=d["source_line_start"],
            source_line_end=d["source_line_end"],
            anomaly_flags=d.get("anomaly_flags", []),
            content_version=d.get("content_version", ""),
            page_fingerprints=d.get("page_fingerprints", []),
            table_group_id=d.get("table_group_id"),
            join_metadata=d.get("join_metadata"),
            source_unit_ids=d.get("source_unit_ids", []),
        )


# ---------------------------------------------------------------------------
# Legacy Stage A compatibility schemas (Chunker/MarkerStream path)
# ---------------------------------------------------------------------------

SpanLocality = Literal["page", "block"]


@dataclass
class DocumentPart:
    """Physical PDF contribution for multi-part logical documents."""

    document_part_id: str
    logical_doc_id: str
    source_pdf_id: str
    part_index: int
    page_offset: int
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
    """Authoritative ingestion unit for Stage A extraction pipelines."""

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


@dataclass(frozen=True)
class MarkerBlock:
    """Raw extraction block emitted by OCR/marker runners."""

    doc_id: str
    page_index: int
    text: str
    bbox: tuple[float, float, float, float]
    raw_block_type: str
    block_ordinal: int
    section_hierarchy: dict[str, Any] = field(default_factory=dict)
    logical_doc_id: str = ""
    document_part_id: str = ""
    source_pdf_id: str = ""
    source_pdf_page_index: int = -1
    logical_page_index: int = -1

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "doc_id": self.doc_id,
            "page_index": self.page_index,
            "text": self.text,
            "bbox": list(self.bbox) if self.bbox else [],
            "raw_block_type": self.raw_block_type,
            "block_ordinal": self.block_ordinal,
            "section_hierarchy": self.section_hierarchy,
            "logical_doc_id": self.logical_doc_id or self.doc_id,
            "document_part_id": self.document_part_id or self.doc_id,
            "source_pdf_id": self.source_pdf_id or self.doc_id,
            "source_pdf_page_index": self.source_pdf_page_index if self.source_pdf_page_index >= 0 else self.page_index,
            "logical_page_index": self.logical_page_index if self.logical_page_index >= 0 else self.page_index,
        }
        return out

    @property
    def effective_logical_doc_id(self) -> str:
        return self.logical_doc_id or self.doc_id

    @property
    def effective_logical_page_index(self) -> int:
        return self.logical_page_index if self.logical_page_index >= 0 else self.page_index


@dataclass
class ProvenanceSpan:
    """Source span with explicit locality."""

    start: int
    end: int
    locality: SpanLocality

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError(f"Invalid span: start={self.start}, end={self.end}")


@dataclass
class Chunk:
    """Intentional extraction chunk used by retrieval broadening paths."""

    chunk_id: str
    doc_id: str
    page_index: int
    section_path: list[str]
    block_type: str
    text: str
    span_start: int
    span_end: int
    span_locality: SpanLocality
    bbox: tuple[float, float, float, float]
    block_ordinals: list[int]
    structural_metadata: dict[str, Any] = field(default_factory=dict)
    logical_doc_id: str = ""
    document_part_id: str = ""
    source_pdf_id: str = ""
    source_pdf_page_index: int = -1
    logical_page_index: int = -1

    def __post_init__(self) -> None:
        if self.span_start < 0 or self.span_end <= self.span_start:
            raise ValueError(f"Invalid span: span_start={self.span_start}, span_end={self.span_end}")
        if not self.text.strip():
            raise ValueError("Chunk text must be non-empty after normalization")

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
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
            "logical_doc_id": self.logical_doc_id or self.doc_id,
            "document_part_id": self.document_part_id or self.doc_id,
            "source_pdf_id": self.source_pdf_id or self.doc_id,
            "source_pdf_page_index": self.source_pdf_page_index if self.source_pdf_page_index >= 0 else self.page_index,
            "logical_page_index": self.logical_page_index if self.logical_page_index >= 0 else self.page_index,
        }
        return out


@dataclass
class DropRecord:
    """Explicit record for dropped blocks in extraction/chunker pipelines."""

    reason_code: str
    page_index: int
    block_reference: str
    source_pdf_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "page_index": self.page_index,
            "block_reference": self.block_reference,
            "source_pdf_id": self.source_pdf_id,
        }

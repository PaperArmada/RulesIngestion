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
    """Prose-bound provenance unit.  The only admissible input to Stage C."""

    unit_id: str              # blake3(text + "|" + structural_path_joined)
    unit_type: Literal["prose", "table", "list", "callout", "heading"]
    text: str                 # verbatim
    structural_path: list[str]   # heading ancestry from AST root
    ordering_key: int            # total monotonic order
    page_fingerprint: str        # upstream Stage A identity
    content_hash: str            # blake3 of text
    source_line_start: int       # back-pointer to raw markdown
    source_line_end: int
    anomaly_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
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
        }

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
        )

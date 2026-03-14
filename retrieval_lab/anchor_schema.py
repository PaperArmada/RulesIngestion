"""GoldAnchor and AnchorResolution schemas for stable benchmark gold identity.

ADR-001 Amendment: GoldAnchors decouple benchmark editorial intent from
runtime EvidenceUnit IDs, allowing chunking strategy changes without
benchmark gold drift.

Vocabulary:
  GoldAnchor         — durable editorial reference to an authored evidence region.
  AnchorResolution   — mapping from a GoldAnchor to current EvidenceUnit IDs
                       for a specific substrate version.
  ResolvedGoldSet    — runtime set of EvidenceUnit IDs produced by resolution.
  AnchorCoverageStatus — whether the substrate resolved the anchor exactly,
                         approximately, or not at all.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any


def normalize_quote(text: str) -> str:
    """Lowercase, collapse whitespace, strip."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def quote_hash(text: str) -> str:
    """SHA-256 of normalized quote text (first 32 hex chars)."""
    return hashlib.sha256(normalize_quote(text).encode("utf-8")).hexdigest()[:32]


def generate_anchor_id(
    document_id: str,
    page: int,
    structural_path: list[str],
    anchor_quote: str,
) -> str:
    """Deterministic anchor ID from stable editorial fields.

    Uses document_id + page + structural_path + first 100 chars of
    normalized quote as the identity seed.  Produces the same ID when
    re-running enrichment on the same benchmark data.
    """
    path_str = " > ".join(structural_path)
    quote_prefix = normalize_quote(anchor_quote)[:100]
    payload = f"{document_id}|{page}|{path_str}|{quote_prefix}"
    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"ga_{h}"


VALID_ANCHOR_TYPES = frozenset({"prose", "table", "list", "callout", "heading"})

VALID_RESOLUTION_STATUSES = frozenset({
    "exact",
    "split",
    "merged",
    "approximate",
    "unresolved",
})


@dataclass
class GoldAnchor:
    """Durable editorial reference to an authored evidence region."""

    anchor_id: str
    document_id: str
    anchor_type: str
    page: int
    structural_path: list[str]
    anchor_quote: str
    quote_normalized_hash: str

    page_fingerprint: str | None = None
    source_line_start: int | None = None
    source_line_end: int | None = None

    table_group_id: str | None = None
    row_header_quote: str | None = None
    column_header_quote: str | None = None

    cached_unit_ids: list[str] = field(default_factory=list)
    cached_source_unit_ids: list[str] = field(default_factory=list)

    notes: str = ""
    match_policy: str = "default"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "anchor_id": self.anchor_id,
            "document_id": self.document_id,
            "anchor_type": self.anchor_type,
            "page": self.page,
            "structural_path": self.structural_path,
            "anchor_quote": self.anchor_quote,
            "quote_normalized_hash": self.quote_normalized_hash,
        }
        if self.page_fingerprint is not None:
            d["page_fingerprint"] = self.page_fingerprint
        if self.source_line_start is not None:
            d["source_line_start"] = self.source_line_start
        if self.source_line_end is not None:
            d["source_line_end"] = self.source_line_end
        if self.table_group_id is not None:
            d["table_group_id"] = self.table_group_id
        if self.row_header_quote is not None:
            d["row_header_quote"] = self.row_header_quote
        if self.column_header_quote is not None:
            d["column_header_quote"] = self.column_header_quote
        if self.cached_unit_ids:
            d["cached_unit_ids"] = self.cached_unit_ids
        if self.cached_source_unit_ids:
            d["cached_source_unit_ids"] = self.cached_source_unit_ids
        if self.notes:
            d["notes"] = self.notes
        if self.match_policy != "default":
            d["match_policy"] = self.match_policy
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> GoldAnchor:
        return GoldAnchor(
            anchor_id=d["anchor_id"],
            document_id=d["document_id"],
            anchor_type=d.get("anchor_type", "prose"),
            page=int(d["page"]),
            structural_path=list(d.get("structural_path") or []),
            anchor_quote=d.get("anchor_quote", ""),
            quote_normalized_hash=d.get("quote_normalized_hash", ""),
            page_fingerprint=d.get("page_fingerprint"),
            source_line_start=d.get("source_line_start"),
            source_line_end=d.get("source_line_end"),
            table_group_id=d.get("table_group_id"),
            row_header_quote=d.get("row_header_quote"),
            column_header_quote=d.get("column_header_quote"),
            cached_unit_ids=list(d.get("cached_unit_ids") or []),
            cached_source_unit_ids=list(d.get("cached_source_unit_ids") or []),
            notes=d.get("notes", ""),
            match_policy=d.get("match_policy", "default"),
        )


@dataclass
class AnchorResolution:
    """Result of resolving one GoldAnchor against a specific substrate version."""

    anchor_id: str
    substrate_version: str
    resolved_unit_ids: list[str]
    resolution_status: str
    resolved_by: str
    resolver_scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "substrate_version": self.substrate_version,
            "resolved_unit_ids": self.resolved_unit_ids,
            "resolution_status": self.resolution_status,
            "resolved_by": self.resolved_by,
            "resolver_scores": self.resolver_scores,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> AnchorResolution:
        return AnchorResolution(
            anchor_id=d["anchor_id"],
            substrate_version=d.get("substrate_version", ""),
            resolved_unit_ids=list(d.get("resolved_unit_ids") or []),
            resolution_status=d.get("resolution_status", "unresolved"),
            resolved_by=d.get("resolved_by", ""),
            resolver_scores=dict(d.get("resolver_scores") or {}),
        )

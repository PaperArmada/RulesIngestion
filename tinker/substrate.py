"""Typed access to Stage B EvidenceUnits.

Thin adapter over `retrieval_lab.substrate_loader` that returns a list of
frozen `Unit` dataclasses instead of raw dicts. Also exposes the
load-time merge recipe (`min_chars`, `merge_chunks`, `merge_max_chars`)
that Drakosfire's v3_swcr_merged2000_min100 substrate used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from retrieval_lab.substrate_loader import (
    fold_under_threshold_into_adjacent,
    load_evidence_units,
    merge_units_by_heading,
)


@dataclass(frozen=True)
class Unit:
    id: str
    text: str
    page: int
    structural_path: tuple[str, ...]
    unit_type: str
    document_id: str
    table_title: str = ""
    source_page_dir: str = ""
    source_parent_dir: str = ""
    join_metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Unit":
        sp = d.get("structural_path") or []
        return cls(
            id=d["id"],
            text=d.get("text", ""),
            page=int(d.get("page", -1)),
            structural_path=tuple(sp),
            unit_type=d.get("unit_type", "prose"),
            document_id=d.get("document_id", ""),
            table_title=d.get("table_title", "") or "",
            source_page_dir=d.get("source_page_dir", "") or "",
            source_parent_dir=d.get("source_parent_dir", "") or "",
            join_metadata=dict(d.get("join_metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "page": self.page,
            "structural_path": list(self.structural_path),
            "unit_type": self.unit_type,
            "document_id": self.document_id,
            "table_title": self.table_title,
            "source_page_dir": self.source_page_dir,
            "source_parent_dir": self.source_parent_dir,
            "join_metadata": dict(self.join_metadata),
        }


# Drakosfire's v3_swcr_merged2000_min100 recipe (per the SWCR benchmark
# contract sidecar at evals/retrieval/SwordsandWizardry/*.contract.json).
RECIPE_MERGED_2000_MIN_100: dict[str, Any] = {
    "min_chars": 100,
    "merge_chunks": True,
    "merge_max_chars": 2000,
}


def load_corpus(
    substrate_dir: str | Path,
    document_id: str,
    *,
    min_chars: int = 100,
    merge_chunks: bool = True,
    merge_max_chars: int = 2000,
) -> list[Unit]:
    """Load a Stage B substrate and apply the v3_swcr_merged2000_min100 recipe.

    Defaults match the recipe that Drakosfire's SWCR benchmark used. Override
    to disable merge/fold for raw inspection.
    """
    raw = load_evidence_units(str(substrate_dir), document_id)
    if min_chars > 0:
        raw = fold_under_threshold_into_adjacent(raw, min_chars=min_chars)
    if merge_chunks:
        raw = merge_units_by_heading(raw, max_chars=merge_max_chars)
    return [Unit.from_dict(d) for d in raw]

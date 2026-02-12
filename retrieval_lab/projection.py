"""Retrieval-only projection substrates.

Clause-family projection groups nearby units under the same heading path to improve
compositional retrieval without mutating canonical EvidenceUnits.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Tuple


def _same_heading_family(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return (
        a.get("document_id") == b.get("document_id")
        and a.get("page") == b.get("page")
        and (a.get("structural_path") or []) == (b.get("structural_path") or [])
    )


def _family_id(source_ids: List[str]) -> str:
    material = "|".join(source_ids)
    return f"family_{hashlib.sha256(material.encode('utf-8')).hexdigest()}"


def build_clause_family_projection(
    corpus: List[Dict[str, Any]],
    window: int = 2,
    max_units: int = 6,
    direction: str = "symmetric",
) -> List[Dict[str, Any]]:
    """Create retrieval-family documents from canonical units.

    - Anchor every unit as center.
    - Include up to `window` neighbors based on direction:
      - symmetric: left and right
      - forward: anchor + right neighbors only
    - Cap family size at `max_units`.
    - Preserve source_unit_ids for scoring/provenance.
    """
    if not corpus:
        return []
    direction = (direction or "symmetric").strip().lower()
    if direction not in {"symmetric", "forward"}:
        raise ValueError(f"Unsupported clause-family direction: {direction}")
    projected: List[Dict[str, Any]] = []
    n = len(corpus)
    for i, center in enumerate(corpus):
        members: List[Tuple[int, Dict[str, Any]]] = [(i, center)]

        if direction == "symmetric":
            # Walk left within heading family.
            left = i - 1
            left_added = 0
            while left >= 0 and left_added < window:
                if not _same_heading_family(center, corpus[left]):
                    break
                members.insert(0, (left, corpus[left]))
                left -= 1
                left_added += 1

        # Walk right within heading family.
        right = i + 1
        right_added = 0
        while right < n and right_added < window:
            if not _same_heading_family(center, corpus[right]):
                break
            members.append((right, corpus[right]))
            right += 1
            right_added += 1

        # Enforce max size centered around anchor.
        if len(members) > max_units:
            center_idx = next(idx for idx, (src_i, _) in enumerate(members) if src_i == i)
            half = max_units // 2
            start = max(0, center_idx - half)
            end = min(len(members), start + max_units)
            start = max(0, end - max_units)
            members = members[start:end]

        source_unit_ids = [u["id"] for _, u in members]
        text = "\n\n".join((u.get("text", "") or "").strip() for _, u in members if u.get("text"))
        family = {
            "id": _family_id(source_unit_ids),
            "text": text,
            "page": center.get("page", -1),
            "structural_path": center.get("structural_path", []),
            "unit_type": "clause_family",
            "document_id": center.get("document_id", ""),
            "source_unit_ids": source_unit_ids,
            "projection_kind": "clause_family",
            "projection_anchor_id": center.get("id", ""),
        }
        projected.append(family)
    return projected


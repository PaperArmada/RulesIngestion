"""
A1.2 Dual-list fusion: retrieve from canonical EvidenceUnit index (Index_U) and
clause-family projection index (Index_F), then merge with quota interleave to
protect T1 precision while adding T2 coverage.

Spec: Docs/Design/decision_lock_in_and_next_spec.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CandidateMeta:
    """Per-candidate metadata for auditability."""

    source_list: str  # "unit" | "family" | "both"
    merge_reason: str  # "quota_unit" | "quota_family" | "backfill"
    family_params: Optional[str] = None


def fuse_dual_list(
    U_ids: List[str],
    U_scores: List[float],
    F_family_ids: List[str],
    F_scores: List[float],
    family_id_to_anchor_unit_id: Dict[str, str],
    *,
    Qu: int = 6,
    Kfinal: int = 10,
    family_params: Optional[str] = None,
) -> Tuple[List[str], List[float], List[CandidateMeta]]:
    """
    Merge unit list U and family list F into a single ranked list of canonical
    unit_ids with quota interleave and dedupe by unit_id.

    - EvidenceUnit hits are keyed by unit_id. Family hits map to anchor unit_id.
    - If both lists contain the same unit_id, the EvidenceUnit version is primary
      and we mark source_list="both".
    - Merge: add Qu unit hits first (precision), then interleave F and remaining U
      until Kfinal, then backfill from F then U.
    - Pinning: by adding Qu unit hits first, U[0] stays at rank 1 (no family above it).
    """
    # Normalize to (unit_id, score) for U; for F map to (anchor_unit_id, score)
    U_list: List[Tuple[str, float]] = list(zip(U_ids, U_scores))
    F_mapped: List[Tuple[str, float]] = []
    for fid, sc in zip(F_family_ids, F_scores):
        anchor = family_id_to_anchor_unit_id.get(fid)
        if anchor:
            F_mapped.append((anchor, sc))

    fused_ids: List[str] = []
    fused_scores: List[float] = []
    fused_meta: List[CandidateMeta] = []
    seen: set[str] = set()

    def add(u_id: str, score: float, source: str, reason: str) -> None:
        if u_id in seen:
            return
        seen.add(u_id)
        fused_ids.append(u_id)
        fused_scores.append(score)
        fused_meta.append(
            CandidateMeta(
                source_list=source,
                merge_reason=reason,
                family_params=family_params if source != "unit" else None,
            )
        )

    # Mark which unit_ids appear in both lists (for source_list="both")
    u_set = {u for u, _ in U_list}
    f_anchors = {a for a, _ in F_mapped}
    both_set = u_set & f_anchors

    # 1) Quota unit: add up to Qu from U in order
    for i, (u_id, sc) in enumerate(U_list):
        if len(fused_ids) >= Qu:
            break
        source = "both" if u_id in both_set else "unit"
        add(u_id, sc, source, "quota_unit")

    # Remaining U and F (by anchor), excluding already-seen
    remaining_U: List[Tuple[str, float]] = [(u, sc) for u, sc in U_list if u not in seen]
    remaining_F: List[Tuple[str, float]] = [(a, sc) for a, sc in F_mapped if a not in seen]

    # 2) Interleave: one from F, one from remaining U until Kfinal
    iu, if_ = 0, 0
    while len(fused_ids) < Kfinal and (iu < len(remaining_U) or if_ < len(remaining_F)):
        # Add one from F if available
        if if_ < len(remaining_F):
            a, sc = remaining_F[if_]
            if_ += 1
            if a not in seen:
                add(a, sc, "both" if a in both_set else "family", "quota_family")
        if len(fused_ids) >= Kfinal:
            break
        # Add one from remaining U
        if iu < len(remaining_U):
            u, sc = remaining_U[iu]
            iu += 1
            if u not in seen:
                add(u, sc, "both" if u in both_set else "unit", "quota_family")

    # 3) Backfill: remaining F, then remaining U
    for a, sc in remaining_F[if_:]:
        if len(fused_ids) >= Kfinal:
            break
        if a not in seen:
            add(a, sc, "both" if a in both_set else "family", "backfill")
    for u, sc in remaining_U[iu:]:
        if len(fused_ids) >= Kfinal:
            break
        if u not in seen:
            add(u, sc, "both" if u in both_set else "unit", "backfill")

    return fused_ids, fused_scores, fused_meta

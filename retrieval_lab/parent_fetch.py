"""
R2: Parent-fetch primitive.

Enriches top-k retrieval candidates with parent/sibling context by structural_path.
Respects table_group_id for table expansion (R3).
"""

from __future__ import annotations

from typing import Any, Dict, List

from retrieval_lab.config import ParentFetchConfig


def build_section_index(corpus: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Build structural_path prefix -> [unit_ids] index for fast parent resolution.

    Keys are joined paths (e.g. "Chapter 1 > Section 1.1") at various depths.
    """
    index: Dict[str, List[str]] = {}
    for u in corpus:
        uid = u.get("id", "")
        sp = u.get("structural_path", [])
        if not uid:
            continue
        for depth in range(1, len(sp) + 1):
            prefix = " > ".join(sp[:depth])
            if prefix not in index:
                index[prefix] = []
            if uid not in index[prefix]:
                index[prefix].append(uid)
    return index


def resolve_parent_scope(
    unit_id: str,
    corpus: List[Dict[str, Any]],
    id_to_unit: Dict[str, Dict[str, Any]],
    section_index: Dict[str, List[str]],
    depth: int = 1,
    char_cap: int = 2000,
) -> List[str]:
    """Find sibling EvidenceUnits sharing structural_path prefix up to depth.

    Returns list of unit_ids (including the given unit) that form the parent scope.
    Stops when char_cap is reached.
    """
    unit = id_to_unit.get(unit_id)
    if not unit:
        return []
    sp = unit.get("structural_path", [])
    if not sp:
        return [unit_id]
    prefix_depth = min(depth, len(sp))
    prefix = " > ".join(sp[:prefix_depth])
    sibling_ids = section_index.get(prefix, [])
    if not sibling_ids:
        return [unit_id]
    # Sort by corpus order (page, ordering) so context is coherent
    id_to_idx = {u.get("id"): i for i, u in enumerate(corpus)}
    sibling_ids = [uid for uid in sibling_ids if uid in id_to_idx]
    sibling_ids.sort(key=lambda uid: id_to_idx.get(uid, 0))
    # Cap by char_cap
    total = 0
    result: List[str] = []
    for uid in sibling_ids:
        u = id_to_unit.get(uid)
        if not u:
            continue
        text = u.get("text", "")
        if total + len(text) > char_cap and result:
            break
        result.append(uid)
        total += len(text)
    return result if result else [unit_id]


def fetch_parent_context(
    candidates: List[Dict[str, Any]],
    corpus: List[Dict[str, Any]],
    policy: ParentFetchConfig,
) -> List[Dict[str, Any]]:
    """Enrich retrieval candidates with parent text metadata.

    Each candidate (with chunk_id) gains parent_unit_ids and parent_text.
    Does not modify gold metrics — enrichment is additive.
    """
    if not policy.enabled or not candidates:
        return candidates

    id_to_unit = {u.get("id", ""): u for u in corpus if u.get("id")}
    section_index = build_section_index(corpus)
    enriched: List[Dict[str, Any]] = []
    for c in candidates:
        cid = c.get("chunk_id", c.get("id", ""))
        if not cid:
            enriched.append(c)
            continue
        parent_ids = resolve_parent_scope(
            cid,
            corpus,
            id_to_unit,
            section_index,
            depth=policy.depth,
            char_cap=policy.char_cap,
        )
        out = dict(c)
        out["parent_unit_ids"] = parent_ids
        if parent_ids:
            texts = [id_to_unit.get(pid, {}).get("text", "") for pid in parent_ids]
            out["parent_text"] = "\n\n".join(t for t in texts if t)
        enriched.append(out)
    return enriched

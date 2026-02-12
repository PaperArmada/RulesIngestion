"""
B1 replacement: dependency-oriented pairing edges (delta→base, exception→base).
Deterministic "retrieve these together" without semantic inference or LLM.

Spec: Docs/Design/decision_lock_in_and_next_spec.md § Minimal spec: dependency-oriented pairing edges.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


# Delta markers: modifiers that refer to a base rule (e.g. "increase by", "at 5th level").
DELTA_MARKERS = (
    "increase by",
    "at 5th level",
    "at 10th level",
    "at 15th level",
    "at 20th level",
    "additional",
    "instead of",
    "bonus equals",
    "in addition",
)
# Exception markers: clauses that override or narrow a base rule.
EXCEPTION_MARKERS = ("except", "unless", "however", "despite", "but")


def _is_delta_marked(text: str) -> bool:
    t = (text or "").lower()
    return any(m in t for m in DELTA_MARKERS)


def _is_exception_marked(text: str) -> bool:
    t = (text or "").lower()
    return any(m in t for m in EXCEPTION_MARKERS)


def _same_page_or_prev(unit_a: Dict[str, Any], unit_b: Dict[str, Any]) -> bool:
    pa, pb = unit_a.get("page", -1), unit_b.get("page", -1)
    return pa == pb or pb == pa - 1


def build_dependency_pairing_edges(
    corpus: List[Dict[str, Any]],
) -> Dict[str, List[Tuple[str, str]]]:
    """
    Build unit_id -> [(target_unit_id, edge_type), ...] where edge_type is
    "delta_base_pair" or "exception_base_pair". At most one base per delta,
    at most one base per exception.

    Corpus is assumed in document order (page/position). Preceding = lower index.

    - Delta → base: same document_id, same structural_path preferred, same page
      or previous page; nearest preceding unit that is not delta-marked.
    - Exception → base: same document_id, same structural_path; nearest preceding
      unit that is not exception-marked.
    """
    if not corpus:
        return {}
    edges: Dict[str, List[Tuple[str, str]]] = {}

    for i, unit in enumerate(corpus):
        uid = unit.get("id", "")
        text = unit.get("text") or ""
        if not uid:
            continue
        added: List[Tuple[str, str]] = []

        if _is_delta_marked(text):
            for j in range(i - 1, -1, -1):
                cand = corpus[j]
                if cand.get("document_id") != unit.get("document_id"):
                    continue
                if (cand.get("structural_path") or []) != (unit.get("structural_path") or []):
                    continue
                if not _same_page_or_prev(unit, cand):
                    continue
                cid = cand.get("id", "")
                if not cid or _is_delta_marked(cand.get("text") or ""):
                    continue
                added.append((cid, "delta_base_pair"))
                break

        if _is_exception_marked(text):
            for j in range(i - 1, -1, -1):
                cand = corpus[j]
                if cand.get("document_id") != unit.get("document_id"):
                    continue
                if (cand.get("structural_path") or []) != (unit.get("structural_path") or []):
                    continue
                cid = cand.get("id", "")
                if not cid or _is_exception_marked(cand.get("text") or ""):
                    continue
                added.append((cid, "exception_base_pair"))
                break

        if added:
            edges[uid] = added

    return edges


def expand_ranked_with_pairing_edges(
    ranked_ids: List[str],
    score_list: List[float],
    pairing_edges: Dict[str, List[Tuple[str, str]]],
    *,
    expand_top_k: int = 10,
    Emax: int = 6,
) -> Tuple[List[str], List[float], List[Dict[str, str]]]:
    """
    When a candidate has paired targets (delta→base or exception→base), add those
    bases to the candidate pool. Cap at Emax added per query. Tag with
    expanded_by = "delta_base_pair" | "exception_base_pair".
    """
    out_ids = list(ranked_ids)
    out_scores = list(score_list)
    provenance: List[Dict[str, str]] = []
    seen = set(out_ids)
    added = 0
    for anchor_id in ranked_ids[: max(0, expand_top_k)]:
        if added >= Emax:
            break
        for target_id, edge_type in pairing_edges.get(anchor_id, []):
            if added >= Emax:
                break
            if target_id in seen:
                continue
            seen.add(target_id)
            out_ids.append(target_id)
            out_scores.append(0.0)
            provenance.append({
                "chunk_id": target_id,
                "expanded_by": edge_type,
                "anchor_id": anchor_id,
            })
            added += 1
    return out_ids, out_scores, provenance

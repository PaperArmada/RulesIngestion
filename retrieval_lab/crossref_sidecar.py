"""Deterministic cross-reference/exception sidecar edges for retrieval expansion."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List


EXCEPTION_MARKERS = ("except", "unless", "however", "despite", "but")
CROSSREF_MARKERS = (
    "see",
    "as described",
    "as noted",
    "refer to",
)


def _heading_key(unit: Dict[str, Any]) -> str:
    path = unit.get("structural_path") or []
    return " > ".join(path)


def build_crossref_sidecar(corpus: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Build a unit_id -> related_unit_ids sidecar using deterministic rules."""
    by_heading: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for unit in corpus:
        by_heading[_heading_key(unit)].append(unit)

    edges: Dict[str, List[str]] = defaultdict(list)
    for _, members in by_heading.items():
        for i, unit in enumerate(members):
            uid = unit.get("id", "")
            text = (unit.get("text") or "").lower()
            if not uid:
                continue

            # Exception/base pairing: link exception-like clauses to closest sibling neighbors.
            if any(marker in text for marker in EXCEPTION_MARKERS):
                if i - 1 >= 0:
                    edges[uid].append(members[i - 1].get("id", ""))
                if i + 1 < len(members):
                    edges[uid].append(members[i + 1].get("id", ""))

            # Cross-reference phrase: pull nearest two siblings under same heading.
            if any(marker in text for marker in CROSSREF_MARKERS):
                if i - 1 >= 0:
                    edges[uid].append(members[i - 1].get("id", ""))
                if i + 1 < len(members):
                    edges[uid].append(members[i + 1].get("id", ""))

    # Deduplicate while preserving order and remove blanks/self.
    deduped: Dict[str, List[str]] = {}
    for uid, related in edges.items():
        seen = set()
        ordered: List[str] = []
        for rid in related:
            if not rid or rid == uid or rid in seen:
                continue
            seen.add(rid)
            ordered.append(rid)
        if ordered:
            deduped[uid] = ordered
    return deduped


def expand_ranked_with_sidecar(
    ranked_ids: List[str],
    score_list: List[float],
    sidecar: Dict[str, List[str]],
    expand_top_k: int,
    expand_per_hit: int,
    total_cap: int,
) -> tuple[List[str], List[float], List[Dict[str, str]]]:
    """Expand ranked list using sidecar edges under strict budget caps."""
    out_ids = list(ranked_ids)
    out_scores = list(score_list)
    provenance: List[Dict[str, str]] = []
    seen = set(out_ids)
    added = 0
    for anchor_id in ranked_ids[: max(0, expand_top_k)]:
        if added >= total_cap:
            break
        related = sidecar.get(anchor_id, [])[: max(0, expand_per_hit)]
        for rid in related:
            if added >= total_cap:
                break
            if rid in seen:
                continue
            seen.add(rid)
            out_ids.append(rid)
            out_scores.append(0.0)
            provenance.append({"chunk_id": rid, "expanded_by": "crossref_sidecar", "anchor_id": anchor_id})
            added += 1
    return out_ids, out_scores, provenance


def build_minimal_a_prime_hints(corpus: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Generate minimal deterministic A′ co-retrieval hints from corpus structure."""
    sidecar = build_crossref_sidecar(corpus)
    id_to_unit = {u.get("id", ""): u for u in corpus}
    hints: Dict[str, Dict[str, Any]] = {}
    for uid, related in sidecar.items():
        if not uid:
            continue
        topic_tags: List[str] = []
        for rid in related:
            target = id_to_unit.get(rid, {})
            heading = _heading_key(target)
            if heading:
                topic_tags.append(heading.lower())
        # Keep deterministic short hint list.
        topic_tags = list(dict.fromkeys(topic_tags))[:5]
        co_retrieval_hints = [{"related_topic": t, "reason": "crossref_or_exception_sidecar"} for t in topic_tags]
        hints[uid] = {
            "topic_tags": topic_tags,
            "co_retrieval_hints": co_retrieval_hints,
        }
    return hints


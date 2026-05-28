"""Cross-reference graph extraction over EvidenceUnits.

Uses the glossary's term set as the named-rule vocabulary, then scans every
unit's text for occurrences of those terms in *other* units. Each match
becomes an edge `(source_unit_id, target_term, target_unit_id)` where the
target_unit_id is the unit the term was defined in.

This is a weak approximation of the cross-reference graph that Stage C's
typed-enrichment would build; it's good enough to support the
intent-bearing route's evidence-completion checks without paying for
Stage C.
"""

from __future__ import annotations

import re
from typing import Any

from tinker.substrate import Unit


def build_crossref_graph(
    units: list[Unit],
    glossary_terms: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return cross-reference edges seeded on glossary terms.

    Edges are deduplicated by (source_unit_id, target_term). A term defined
    in multiple units (rare) maps to the first-seen `source_unit_id`.
    """
    if not glossary_terms:
        return {"edges": [], "stats": {"terms": 0, "edges": 0}}

    # term_lower -> (canonical_term, defining_unit_id)
    term_map: dict[str, tuple[str, str]] = {}
    for entry in glossary_terms:
        term = entry["term"]
        uid = entry.get("source_unit_id", "")
        key = term.lower()
        if key not in term_map and len(term) >= 3:
            term_map[key] = (term, uid)

    # Build a single regex matching any term (word-boundary). We use the
    # canonical case-folded keys joined by alternation. Pre-sort by length
    # descending so longer terms win when they overlap a shorter one.
    sorted_keys = sorted(term_map.keys(), key=len, reverse=True)
    if not sorted_keys:
        return {"edges": [], "stats": {"terms": 0, "edges": 0}}

    pattern = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in sorted_keys) + r")\b",
        re.IGNORECASE,
    )

    edges: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for u in units:
        for m in pattern.finditer(u.text):
            matched_key = m.group(1).lower()
            target_term, target_uid = term_map.get(matched_key, ("", ""))
            if not target_term:
                continue
            if u.id == target_uid:
                continue  # self-reference (term defined here)
            key = (u.id, target_term.lower())
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                {
                    "source_unit_id": u.id,
                    "target_term": target_term,
                    "target_unit_id": target_uid,
                }
            )

    return {
        "edges": edges,
        "stats": {
            "terms": len(term_map),
            "edges": len(edges),
            "source_units": len({e["source_unit_id"] for e in edges}),
        },
    }

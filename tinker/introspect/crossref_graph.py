"""Cross-reference graph: traversal over the auto-built crossref edges.

The self-portrait's `crossref` block holds edges
`source_unit_id --references--> target_term (defined in target_unit_id)`,
seeded on the auto-extracted glossary (so the graph is discovered, not
hardcoded). This module turns those edges into two traversals:

  reverse_refs(term)        -> units that reference `term` (1-hop reverse).
  forward_closure(term, k)  -> the dependency closure reachable from `term`'s
                               defining unit within k reference-hops (genuinely
                               transitive; what similarity retrieval cannot do).

Node selection (`enumerable_terms`) keeps terms whose in-degree clears a
size-relative threshold, mirroring the facet qualifier so the same code adapts
to corpora large and small.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any


@dataclass
class CrossrefGraph:
    # term -> set of units that reference it
    refs_to: dict[str, set[str]]
    # unit -> set of terms it references
    refs_from: dict[str, set[str]]
    # term -> the unit that defines it
    term_def_unit: dict[str, str]
    n_units: int

    def reverse_refs(self, term: str) -> set[str]:
        """Units that reference `term` (1-hop reverse lookup)."""
        return set(self.refs_to.get(term, set()))

    def forward_closure(self, term: str, k: int = 2) -> set[str]:
        """Units reachable from `term`'s defining unit within k reference-hops.

        Hop 0 is the defining unit. Each hop expands a unit to the defining
        units of the terms it references. Returns the closure EXCLUDING the
        seed defining unit (we want what it depends on, not itself).
        """
        seed = self.term_def_unit.get(term)
        if not seed:
            return set()
        seen_units = {seed}
        frontier = deque([(seed, 0)])
        out: set[str] = set()
        while frontier:
            unit, depth = frontier.popleft()
            if depth >= k:
                continue
            for t in self.refs_from.get(unit, set()):
                du = self.term_def_unit.get(t)
                if du and du not in seen_units:
                    seen_units.add(du)
                    out.add(du)
                    frontier.append((du, depth + 1))
        return out

    def in_degree(self, term: str) -> int:
        return len(self.refs_to.get(term, set()))

    def enumerable_terms(
        self, *, min_indegree_floor: int = 6, min_indegree_frac: float = 0.012
    ) -> list[str]:
        """Terms with enough referencing units to form a usable gold set.

        Relative threshold with an absolute floor, so it adapts to corpus size.
        """
        thresh = max(min_indegree_floor, round(min_indegree_frac * self.n_units))
        terms = [t for t in self.refs_to if self.in_degree(t) >= thresh]
        return sorted(terms, key=self.in_degree, reverse=True)


def build_graph(self_portrait: dict[str, Any], *, n_units: int) -> CrossrefGraph:
    edges = self_portrait.get("crossref", {}).get("edges", [])
    refs_to: dict[str, set[str]] = defaultdict(set)
    refs_from: dict[str, set[str]] = defaultdict(set)
    term_def_unit: dict[str, str] = {}
    for e in edges:
        term = e.get("target_term", "")
        src = e.get("source_unit_id", "")
        tgt = e.get("target_unit_id", "")
        if not term or not src:
            continue
        refs_to[term].add(src)
        refs_from[src].add(term)
        if term not in term_def_unit and tgt:
            term_def_unit[term] = tgt
    return CrossrefGraph(
        refs_to=dict(refs_to),
        refs_from=dict(refs_from),
        term_def_unit=term_def_unit,
        n_units=n_units,
    )

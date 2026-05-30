"""Auto-generate the cross-reference eval from the crossref graph.

Two query types, both anchored on a graph node (a glossary term):
  - "references" (1-hop reverse): units that mention X. NOTE: this is
    mention-membership, i.e. essentially lexical/BM25 retrieval — included as a
    baseline-honesty case, not a novel paradigm.
  - "depends_on" (k-hop forward closure): the transitive dependency closure
    reachable from X's defining unit. THIS is the genuinely-graph capability
    neither dense nor BM25 can compute.

Gold is the traversal result (graph membership), so this tests node resolution +
traversal + the structural inability of similarity/lexical to do transitive
closure — analogous to the enumeration eval's circularity caveat.

Node selection excludes stat-block label terms (Saving Throw, Range, ...) and
generic function words, keeping content/rule terms where the queries are
meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tinker.introspect.crossref_graph import CrossrefGraph

_STAT_LABELS = {
    "saving throw", "range", "hit dice", "duration", "move", "special",
    "attacks", "armor class", "spell level", "challenge level/xp", "used",
    "hit points", "number appearing", "treasure type", "no. appearing",
}

# Generic function/pronoun words that leak past the length filter but are not
# meaningful cross-reference nodes.
_STOPWORDS = {
    "your", "using", "use", "other", "this", "that", "these", "those", "with",
    "from", "into", "when", "what", "which", "will", "can", "may", "the", "and",
    "for", "are", "you", "power", "level", "type",
}


@dataclass(frozen=True)
class CrossrefQuery:
    id: str
    question: str
    mode: str           # "references" | "depends_on"
    node: str
    gold_unit_ids: list[str]

    @property
    def set_size(self) -> int:
        return len(self.gold_unit_ids)


def _is_content_term(term: str) -> bool:
    t = term.strip().lower()
    if t in _STAT_LABELS or t in _STOPWORDS or len(t) < 4:
        return False
    if any(ch.isdigit() for ch in t):  # drops "1 turn", page-number-ish noise
        return False
    return True


def generate_queries(
    graph: CrossrefGraph,
    *,
    max_per_mode: int = 12,
    ref_indegree_range: tuple[int, int] = (12, 140),
    closure_size_range: tuple[int, int] = (4, 80),
    forward_k: int = 2,
) -> list[CrossrefQuery]:
    nodes = [t for t in graph.enumerable_terms() if _is_content_term(t)]
    out: list[CrossrefQuery] = []

    # references (1-hop reverse): content terms with bounded in-degree
    refs = []
    for t in nodes:
        ids = sorted(graph.reverse_refs(t))
        if ref_indegree_range[0] <= len(ids) <= ref_indegree_range[1]:
            refs.append((t, ids))
    refs.sort(key=lambda kv: -len(kv[1]))
    for t, ids in refs[:max_per_mode]:
        out.append(CrossrefQuery(
            id=f"xref_ref_{t.lower().replace(' ', '_').replace('/', '_')}",
            question=f"Which rules or entries reference {t}?",
            mode="references", node=t, gold_unit_ids=ids))

    # depends_on (k-hop forward closure): content terms with a non-trivial closure
    deps = []
    for t in nodes:
        ids = sorted(graph.forward_closure(t, k=forward_k))
        if closure_size_range[0] <= len(ids) <= closure_size_range[1]:
            deps.append((t, ids))
    deps.sort(key=lambda kv: -len(kv[1]))
    for t, ids in deps[:max_per_mode]:
        out.append(CrossrefQuery(
            id=f"xref_dep_{t.lower().replace(' ', '_').replace('/', '_')}",
            question=f"What does the {t} rule depend on, directly and indirectly?",
            mode="depends_on", node=t, gold_unit_ids=ids))
    return out


def to_gold_dict(queries: list[CrossrefQuery]) -> dict[str, Any]:
    return {
        q.id: {"question": q.question, "mode": q.mode, "node": q.node,
               "gold_unit_ids": q.gold_unit_ids, "set_size": q.set_size}
        for q in queries
    }

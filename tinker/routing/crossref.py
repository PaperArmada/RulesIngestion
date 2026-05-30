"""Cross-reference traversal route.

Resolves a query to a graph node + relation direction, then traverses:
  - "references" -> units that reference the node (1-hop reverse)
  - "depends_on" -> transitive forward closure from the node's defining unit

The resolver (LLM) returns {is_crossref, node, mode} against the discovered node
catalog. Like the enumeration route, this is set-completion over discovered
structure, not similarity ranking.
"""

from __future__ import annotations

import time
from typing import Any

from tinker import llm as tinker_llm
from tinker.backends import current_backend
from tinker.introspect.crossref_graph import CrossrefGraph
from tinker.routing.entity_anchored import RouteResult


def _resolve(query: str, node_catalog: list[str]) -> dict[str, Any]:
    catalog = "\n".join(f"- {t}" for t in node_catalog)
    system = (
        "You map a user query to a cross-reference graph operation over a rules "
        "corpus. Pick ONE node (a term, copied exactly from the catalog) and the "
        "relation:\n"
        "  mode='references'  — the user wants the rules/entries that REFERENCE "
        "or mention the node.\n"
        "  mode='depends_on'  — the user wants what the node DEPENDS ON (the "
        "rules it builds on, directly and indirectly).\n"
        "If the query is not a cross-reference/traversal request, set "
        "is_crossref=false. Respond ONLY with JSON: "
        '{"is_crossref": bool, "node": str|null, "mode": "references"|"depends_on"|null}.'
    )
    user = f"Node catalog:\n{catalog}\n\nQuery: {query}"
    res = current_backend().chat(role="resolve_crossref", system=system,
                                 user=user, think=False, json_format=True)
    import json
    return json.loads(res.text)


def run_crossref(
    query: str,
    *,
    graph: CrossrefGraph,
    node_catalog: list[str],
    unit_text_by_id: dict[str, str],
    forward_k: int = 2,
) -> RouteResult:
    timing: dict[str, float] = {}
    t0 = time.perf_counter()
    try:
        r = _resolve(query, node_catalog)
    except Exception as e:  # noqa: BLE001
        r = {"is_crossref": False, "node": None, "mode": None, "error": str(e)}
    timing["resolve_ms"] = (time.perf_counter() - t0) * 1000

    node = r.get("node")
    mode = r.get("mode")
    status = "ok"
    ids: list[str] = []
    if not r.get("is_crossref"):
        status = "resolver_not_crossref"
    elif node not in graph.refs_to and node not in graph.term_def_unit:
        status = f"unknown_node:{node}"
    elif mode == "references":
        ids = sorted(graph.reverse_refs(node))
    elif mode == "depends_on":
        ids = sorted(graph.forward_closure(node, k=forward_k))
    else:
        status = f"bad_mode:{mode}"

    candidates = [{"id": uid, "text": unit_text_by_id.get(uid, "")} for uid in ids]
    return RouteResult(
        bucket="cross_reference",
        top_k=candidates,
        pool_size=len(candidates),
        latency_ms_breakdown=timing,
        debug={"node": node, "mode": mode, "status": status, "set_size": len(ids)},
    )

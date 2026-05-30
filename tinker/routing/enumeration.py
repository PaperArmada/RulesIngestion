"""Enumeration route: set-completion over discovered facets.

Two separated decisions (MILESTONE-M7 §3):
  1. is_enumeration_form(query): general, corpus-independent linguistic check
     for set-completion intent ("list / every / all / which … are / how many").
  2. llm.resolve_facet(query, schema): map the query to ONE discovered
     (channel, value); corpus-specific but resolved against AUTO-DISCOVERED
     facets, not hardcoded fields.

The route then returns the COMPLETE unit set for that facet value from the
inverted index — no top-K, no ranking. Similarity retrieval is structurally
bounded by K/|set|; a predicate scan is not.
"""

from __future__ import annotations

import re
import time
from typing import Any

from tinker import llm as tinker_llm
from tinker.routing.entity_anchored import RouteResult


_ENUM_FORM_RE = re.compile(
    r"\b(list|enumerate|every|all of|all the|which|what|how many|name (?:all|every))\b",
    re.IGNORECASE,
)


def is_enumeration_form(query: str) -> bool:
    """General set-completion-intent detector. Corpus-independent."""
    return bool(_ENUM_FORM_RE.search(query))


def build_facet_schema(facets: list[dict[str, Any]]) -> str:
    """Render the discovered facet catalog for the resolver prompt."""
    lines = []
    for ch in facets:
        vals = ", ".join(sorted(ch["values"].keys()))
        lines.append(f"- channel \"{ch['channel']}\" (field '{ch['label']}'): {vals}")
    return "\n".join(lines)


def _facet_index(facets: list[dict[str, Any]]) -> dict[str, dict[str, list[str]]]:
    return {ch["channel"]: ch["values"] for ch in facets}


def run_enumeration(
    query: str,
    *,
    facets: list[dict[str, Any]],
    unit_text_by_id: dict[str, str],
    require_form: bool = False,
) -> RouteResult:
    """Resolve the query to a discovered facet value and return the full set.

    The gate is the resolver's `is_enumeration` judgment, which on the M7 eval
    fired 37/37 on enumeration queries and 0/19 on non-enumeration negatives.
    The regex `is_enumeration_form` check is advisory only (it false-positived
    16/19 negatives — "all/which/what" are too broad), so `require_form`
    defaults False; set it True only to add a cheap pre-filter before the LLM.
    Returns an empty set (with the reason in debug) when the resolver declines
    or returns an unknown channel-value.
    """
    timing: dict[str, float] = {}
    form = is_enumeration_form(query)
    schema = build_facet_schema(facets)

    t0 = time.perf_counter()
    resolved = tinker_llm.resolve_facet(query, schema)
    timing["resolve_ms"] = (time.perf_counter() - t0) * 1000

    is_enum = bool(resolved.get("is_enumeration"))
    channel = resolved.get("channel")
    value = resolved.get("value")
    value = str(value) if value is not None else None

    index = _facet_index(facets)
    ids: list[str] = []
    status = "ok"
    if require_form and not form:
        status = "rejected_form"
    elif not is_enum:
        status = "resolver_not_enumeration"
    elif channel not in index:
        status = f"unknown_channel:{channel}"
    elif value not in index[channel]:
        status = f"unknown_value:{channel}={value}"
    else:
        ids = list(index[channel][value])

    candidates = [
        {"id": uid, "text": unit_text_by_id.get(uid, "")} for uid in ids
    ]
    return RouteResult(
        bucket="enumeration",
        top_k=candidates,
        pool_size=len(candidates),
        latency_ms_breakdown=timing,
        debug={
            "form_detected": form,
            "resolved_channel": channel,
            "resolved_value": value,
            "is_enumeration": is_enum,
            "status": status,
            "set_size": len(ids),
            "reason": resolved.get("reason", ""),
        },
    )

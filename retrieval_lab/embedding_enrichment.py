"""Build embedding input text from corpus items with optional metadata/TOC prefix.

Used for the embedding-metadata-enrichment experiment: compare baseline (text only)
vs prefix-enriched embedding strings (Section, Type, Table, Topics, Related, Page).
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

# Profile names for ablation. baseline = text only; full = all prefix lines.
VALID_PROFILES = frozenset({
    "baseline",
    "path",
    "type",
    "table_title",
    "topic_tags",
    "co_retrieval_hints",
    "page",
    "full",
})

# Cap list lengths to avoid blowing up embedding input size.
TOPIC_TAGS_CAP = 5
CO_RETRIEVAL_HINTS_CAP = 5


def _profile_to_flags(profile: str | None) -> Set[str]:
    """Map profile name to set of enabled enrichment keys. Empty/baseline => none."""
    if not profile or not str(profile).strip():
        return set()
    p = str(profile).strip().lower()
    if p == "baseline":
        return set()
    if p == "full":
        return {"structural_path", "unit_type", "table_title", "topic_tags", "co_retrieval_hints", "page"}
    if p in VALID_PROFILES:
        if p == "path":
            return {"structural_path"}
        if p == "type":
            return {"unit_type"}
        if p == "table_title":
            return {"table_title"}
        if p == "topic_tags":
            return {"topic_tags"}
        if p == "co_retrieval_hints":
            return {"co_retrieval_hints"}
        if p == "page":
            return {"page"}
    return set()


def build_embedding_text(c: Dict[str, Any], profile: str | None) -> str:
    """Build a single string for embedding: optional prefix lines + body (original text).

    Prefix lines (only when profile enables them and value is non-empty):
    - Section: A > B > C   (from structural_path)
    - Type: table          (from unit_type)
    - Table: Cleric Advancement Table  (from table_title; only for unit_type=table if desired; we add whenever present)
    - Topics: tag1, tag2   (from topic_tags, capped)
    - Related: topic1; topic2  (from co_retrieval_hints related_topic, capped)
    - Page: 10             (from page)

    Body: c["text"] unchanged.
    """
    flags = _profile_to_flags(profile)
    if not flags:
        return c.get("text", "")

    lines: List[str] = []

    if "structural_path" in flags:
        sp = c.get("structural_path") or []
        if sp:
            lines.append("Section: " + " > ".join(str(x) for x in sp))

    if "unit_type" in flags:
        ut = c.get("unit_type", "")
        if ut:
            lines.append("Type: " + str(ut))

    if "table_title" in flags:
        tt = (c.get("table_title") or "").strip()
        if tt:
            lines.append("Table: " + tt)

    if "topic_tags" in flags:
        tags = c.get("topic_tags") or []
        if isinstance(tags, list):
            tags = [str(t) for t in tags[:TOPIC_TAGS_CAP] if t]
            if tags:
                lines.append("Topics: " + ", ".join(tags))

    if "co_retrieval_hints" in flags:
        hints = c.get("co_retrieval_hints") or []
        if isinstance(hints, list):
            related = []
            for h in hints[:CO_RETRIEVAL_HINTS_CAP]:
                if isinstance(h, dict) and h.get("related_topic"):
                    related.append(str(h["related_topic"]))
                elif isinstance(h, str):
                    related.append(h)
            if related:
                lines.append("Related: " + "; ".join(related))

    if "page" in flags:
        page = c.get("page", -1)
        if isinstance(page, int) and page >= 0:
            lines.append("Page: " + str(page))

    text = c.get("text", "")
    if not lines:
        return text
    return "\n\n".join(["\n".join(lines), text])

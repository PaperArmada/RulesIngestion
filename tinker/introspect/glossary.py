"""Glossary and acronym extraction from corpus units.

Two passes:

1. Regex pass (high precision, deterministic).
   - "**Term:** definition..." — bold-followed-by-colon (very common in
     pymupdf4llm output of typeset rulebooks).
   - "**Term.** definition..." — bold-followed-by-period.
   - "_Term_: definition..." — italic-followed-by-colon (less common).
2. LLM pass (recall booster) on definitional-looking paragraphs that didn't
   match pass 1. Bounded: capped at a configurable number of LLM calls to
   keep cost predictable.

Acronym extraction looks for "PHRASE (ACRO)" or "ACRO (Phrase Words)"
forms, both common in rulebooks.

Output:
  {
    "terms": [{"term": str, "definition": str, "source_unit_id": str, "source": "regex" | "llm"}],
    "acronyms": [{"acronym": str, "expansion": str, "source_unit_id": str}],
    "stats": {...},
  }
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from tinker import llm as tinker_llm
from tinker.cache import TinkerCache
from tinker.substrate import Unit


# Regex patterns for term-definition extraction.
# **Term:** definition.  or  **Term.** definition.
_RE_BOLD_TERM = re.compile(
    r"\*\*(?P<term>[A-Z][^*\n]{1,60}?)[:\.]\*\*\s+(?P<def>[^\n]{20,400})"
)
# **Term**: definition.  (the colon is outside the bold)
_RE_BOLD_TERM_TRAILING_COLON = re.compile(
    r"\*\*(?P<term>[A-Z][^*\n]{1,60}?)\*\*:\s+(?P<def>[^\n]{20,400})"
)
# _Term_: definition.  (italic; less common but seen on table headers)
_RE_ITALIC_TERM = re.compile(
    r"(?<![A-Za-z])_(?P<term>[A-Z][^_\n]{1,60}?)_:\s+(?P<def>[^\n]{20,400})"
)

# Acronym patterns:
#   PHRASE (ACRO)  — "Hit Points (HP)"
_RE_ACRO_TRAILING = re.compile(
    r"\b(?P<expansion>(?:[A-Z][a-z]+(?:\s+[A-Za-z][a-z]+){0,4}))\s+"
    r"\((?P<acro>[A-Z]{2,6})\)"
)
#   ACRO (Phrase Words)
_RE_ACRO_LEADING = re.compile(
    r"\b(?P<acro>[A-Z]{2,6})\s*\((?P<expansion>[A-Z][a-z]+(?:\s+[A-Za-z][a-z]+){1,4})\)"
)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().rstrip(".,;:")


def _looks_like_a_term(s: str) -> bool:
    """Reject obvious false positives that the regex picks up."""
    if len(s) < 2 or len(s) > 60:
        return False
    if s.isupper() and len(s) <= 3:  # ALL-CAPS shorts: likely a label, not a term
        return False
    if any(ch in s for ch in "[](){}|"):
        return False
    return True


def _extract_terms_regex(units: list[Unit]) -> list[dict[str, Any]]:
    """Pass 1: regex-only term extraction."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for u in units:
        for rex in (_RE_BOLD_TERM, _RE_BOLD_TERM_TRAILING_COLON, _RE_ITALIC_TERM):
            for m in rex.finditer(u.text):
                term = _clean(m.group("term"))
                defn = _clean(m.group("def"))
                if not _looks_like_a_term(term):
                    continue
                key = term.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    {
                        "term": term,
                        "definition": defn,
                        "source_unit_id": u.id,
                        "source": "regex",
                    }
                )
    return out


def _extract_acronyms_regex(units: list[Unit]) -> list[dict[str, Any]]:
    """Acronym extraction via regex only."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for u in units:
        for rex in (_RE_ACRO_TRAILING, _RE_ACRO_LEADING):
            for m in rex.finditer(u.text):
                acro = m.group("acro").strip()
                expansion = _clean(m.group("expansion"))
                if not (2 <= len(acro) <= 6 and acro.isupper()):
                    continue
                key = acro
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    {
                        "acronym": acro,
                        "expansion": expansion,
                        "source_unit_id": u.id,
                    }
                )
    return out


def _llm_candidate_filter(
    units: list[Unit], already_seen_terms: set[str], max_units: int
) -> list[Unit]:
    """Pick units that look definitional but didn't hit the regex pass.

    Heuristic: shortish unit (≤ 600 chars), has a structural_path leaf that
    looks term-like (capitalized, not a chapter heading), and the leaf is not
    already in the regex-extracted set.
    """
    chapter_like = {"Introduction", "Contents", "Foreword", "Appendix"}
    candidates: list[Unit] = []
    for u in units:
        if not u.structural_path:
            continue
        leaf = u.structural_path[-1].strip()
        if not (2 <= len(leaf) <= 60):
            continue
        if leaf in chapter_like:
            continue
        if leaf.lower() in already_seen_terms:
            continue
        if len(u.text) > 600:
            continue
        if u.unit_type not in ("prose", "list"):
            continue
        candidates.append(u)
        if len(candidates) >= max_units:
            break
    return candidates


def _extract_terms_llm(
    candidates: list[Unit],
    cache: TinkerCache,
    *,
    model: str = tinker_llm.MODEL_WORKHORSE,
) -> list[dict[str, Any]]:
    """Pass 2: LLM extraction over selected definitional-looking units.

    Cached: identical unit text produces the same response without a
    second LLM call.
    """
    out: list[dict[str, Any]] = []
    for u in candidates:
        payload = {
            "role": "extract_glossary",
            "text": u.text,
        }
        cached = cache.get_llm("extract_glossary", model, payload)
        if cached is not None:
            try:
                import json as _json

                parsed = _json.loads(cached)
            except Exception:
                continue
        else:
            try:
                parsed = tinker_llm.extract_glossary(u.text)
            except Exception:
                continue
            cache.put_llm(
                "extract_glossary",
                model,
                payload,
                __import__("json").dumps(parsed),
            )
        for entry in parsed.get("terms", []) if isinstance(parsed, dict) else []:
            term = _clean(str(entry.get("term", "")))
            defn = _clean(str(entry.get("definition", "")))
            if not term or not defn or not _looks_like_a_term(term):
                continue
            out.append(
                {
                    "term": term,
                    "definition": defn,
                    "source_unit_id": u.id,
                    "source": "llm",
                }
            )
    return out


def build_glossary(
    units: list[Unit],
    cache: TinkerCache,
    *,
    use_llm: bool = True,
    llm_max_units: int = 50,
) -> dict[str, Any]:
    """End-to-end glossary build.

    Returns a dict with `terms`, `acronyms`, and `stats`. The `terms` list
    is the union of regex hits and LLM hits, deduplicated by term (case-
    insensitive); regex entries take precedence on conflict.

    Set use_llm=False to get a deterministic, no-network result (useful
    for tests).
    """
    regex_terms = _extract_terms_regex(units)
    acronyms = _extract_acronyms_regex(units)
    seen = {t["term"].lower() for t in regex_terms}

    llm_terms: list[dict[str, Any]] = []
    llm_calls = 0
    if use_llm and llm_max_units > 0:
        candidates = _llm_candidate_filter(units, seen, max_units=llm_max_units)
        llm_calls = len(candidates)
        llm_terms = _extract_terms_llm(candidates, cache)

    # Merge, dedup by lowercase term; regex wins.
    merged: dict[str, dict[str, Any]] = {}
    for t in regex_terms:
        merged[t["term"].lower()] = t
    for t in llm_terms:
        key = t["term"].lower()
        if key not in merged:
            merged[key] = t

    terms = sorted(merged.values(), key=lambda d: d["term"].lower())
    return {
        "terms": terms,
        "acronyms": acronyms,
        "stats": {
            "regex_terms": len(regex_terms),
            "llm_terms": len(llm_terms),
            "total_terms": len(terms),
            "acronyms": len(acronyms),
            "llm_calls_attempted": llm_calls,
        },
    }

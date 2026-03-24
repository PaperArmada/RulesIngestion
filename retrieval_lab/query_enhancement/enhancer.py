"""QueryEnhancer: normalize, dict-expand, LLM-rewrite, decompose."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from retrieval_lab.query_enhancement.cache import QueryEnhancementCache
from retrieval_lab.query_enhancement.decomposition import (
    decomposition_cache_signature,
    decompose_query,
)
from retrieval_lab.query_enhancement.profile import (
    QueryExpansionProfile,
    SynonymSet,
    normalize_query,
)

logger = logging.getLogger(__name__)

_LLM_PROMPT_TEMPLATE = """You are a TTRPG rulebook retrieval query expander. Given a user question about tabletop RPG rules, generate {n} diverse alternative queries that would help retrieve relevant rule passages.

CONSTRAINTS:
- Each query must use vocabulary from the allowed terms when possible.
- Maximize facet diversity: each query should target a different aspect or phrasing.
- Do not invent game terms not in the allowed vocabulary (mark any out-of-vocab terms).
- Keep each query concise (under 30 words).

ALLOWED VOCABULARY (use these terms when relevant):
{allowed_vocab_summary}

SYNONYM SETS (these terms are interchangeable in this corpus):
{synonym_summary}

SECTION HEADINGS (these are actual sections in the rulebook):
{heading_summary}

USER QUESTION: {query}

Respond with ONLY valid JSON matching this schema:
{{"queries": [{{"q": "alternative query text", "intent": "brief facet label", "used_terms": ["term1", "term2"], "notes": ""}}]}}"""

VALID_MODES = ("none", "dict", "llm", "llm+dict", "decompose")


def _cache_signature(profile: QueryExpansionProfile, mode: str) -> Tuple[str, str]:
    if mode == "decompose":
        return decomposition_cache_signature(profile)
    if "llm" in mode:
        return profile.llm_rewrite.model_id, profile.llm_rewrite.prompt_hash
    return "", ""


def enhance_queries(
    query_texts: List[str],
    profile: QueryExpansionProfile,
    mode: str = "dict",
    cache: Optional[QueryEnhancementCache] = None,
) -> List[List[Dict[str, Any]]]:
    """Expand each query into a list of expansion dicts.

    Returns a list (one per original query) of lists of expansion dicts:
        [{"q": str, "source": "original"|"dict"|"llm"|"decompose", "intent": str, "notes": str}]

    group[0] is always the original query when include_original is True.
    """
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid enhancement mode: {mode!r}; must be one of {VALID_MODES}")

    if mode == "none":
        return [
            [{"q": qt, "source": "original", "intent": "", "notes": ""}]
            for qt in query_texts
        ]

    profile_hash = profile.compute_hash()
    max_expansions = profile.policies.max_expanded_queries

    results: List[List[Dict[str, Any]]] = []
    for qt in query_texts:
        q_norm = normalize_query(qt, profile)
        cache_model_id, cache_prompt_hash = _cache_signature(profile, mode)

        cached = None
        if cache is not None:
            cached = cache.get(
                corpus_id=profile.corpus_id,
                corpus_hash=profile.corpus_hash,
                profile_hash=profile_hash,
                query_norm=q_norm,
                mode=mode,
                model_id=cache_model_id,
                prompt_hash=cache_prompt_hash,
            )
        if cached is not None:
            results.append(cached)
            continue

        expansions: List[Dict[str, Any]] = []

        if profile.policies.include_original:
            expansions.append({"q": qt, "source": "original", "intent": "", "notes": ""})

        if mode in ("dict", "llm+dict"):
            dict_variants = _dict_expand(qt, profile.synonym_sets, max_expansions)
            expansions.extend(dict_variants)

        if mode in ("llm", "llm+dict"):
            llm_variants = _llm_expand(qt, profile)
            expansions.extend(llm_variants)

        if mode == "decompose":
            sub_queries = _decompose(qt, profile)
            expansions.extend(sub_queries)

        max_total = None if mode == "decompose" else max_expansions
        expansions = _dedupe_and_cap(expansions, max_total, include_original=profile.policies.include_original)

        if cache is not None:
            cache.put(
                corpus_id=profile.corpus_id,
                corpus_hash=profile.corpus_hash,
                profile_hash=profile_hash,
                query_norm=q_norm,
                mode=mode,
                expansions=expansions,
                model_id=cache_model_id,
                prompt_hash=cache_prompt_hash,
            )

        results.append(expansions)

    return results


def _dict_expand(query: str, synonym_sets: List[SynonymSet], max_variants: int) -> List[Dict[str, Any]]:
    """Generate query variants by swapping synonym terms found in the query."""
    query_lower = query.lower()
    variants: List[Dict[str, Any]] = []

    for ss in synonym_sets:
        all_terms = ss.all_terms()
        for term in all_terms:
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            if not pattern.search(query):
                continue
            replacements = [t for t in all_terms if t.lower() != term.lower()]
            for replacement in replacements:
                variant_text = pattern.sub(replacement, query, count=1)
                if variant_text.lower() != query_lower:
                    variants.append({
                        "q": variant_text,
                        "source": "dict",
                        "intent": f"synonym:{ss.name}:{term}->{replacement}",
                        "notes": "",
                    })
                    if len(variants) >= max_variants:
                        return variants
    return variants


def _llm_expand(query: str, profile: QueryExpansionProfile) -> List[Dict[str, Any]]:
    """LLM-based multi-query rewriting with structured output."""
    if not profile.llm_rewrite.enabled:
        return []

    n = profile.policies.max_expanded_queries
    allowed_vocab_summary = ", ".join(profile.allowed_vocab.top_keywords[:50]) if profile.allowed_vocab.top_keywords else "(none provided)"
    synonym_summary = "; ".join(
        f"{ss.canonical} = {', '.join(ss.variants)}" for ss in profile.synonym_sets
    ) if profile.synonym_sets else "(none provided)"
    heading_summary = ", ".join(profile.allowed_vocab.headings[:30]) if profile.allowed_vocab.headings else "(none provided)"

    prompt = _LLM_PROMPT_TEMPLATE.format(
        n=n,
        allowed_vocab_summary=allowed_vocab_summary,
        synonym_summary=synonym_summary,
        heading_summary=heading_summary,
        query=query,
    )

    try:
        from openai import OpenAI
        client = OpenAI()
        response = client.chat.completions.create(
            model=profile.llm_rewrite.model_id,
            messages=[{"role": "user", "content": prompt}],
            temperature=profile.llm_rewrite.temperature,
            top_p=profile.llm_rewrite.top_p,
            response_format={"type": "json_object"},
        )
        raw_text = response.choices[0].message.content or ""
    except Exception as e:
        logger.error("LLM expansion failed for query %r: %s", query[:60], e)
        return []

    return _parse_llm_response(raw_text, query, profile)


def _parse_llm_response(raw_text: str, original_query: str, profile: QueryExpansionProfile) -> List[Dict[str, Any]]:
    """Parse and post-process LLM expansion response."""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning("LLM response is not valid JSON: %s", raw_text[:200])
        return []

    queries_raw = data.get("queries", [])
    if not isinstance(queries_raw, list):
        logger.warning("LLM response 'queries' is not a list")
        return []

    variants: List[Dict[str, Any]] = []
    for item in queries_raw:
        if not isinstance(item, dict) or "q" not in item:
            continue
        q = str(item["q"]).strip()
        if not q or len(q) > 200:
            continue
        intent = str(item.get("intent", ""))
        used_terms = item.get("used_terms", [])
        notes = str(item.get("notes", ""))

        if profile.policies.drift_guard.enabled:
            if not _passes_drift_guard(q, original_query, profile):
                logger.debug("Drift guard rejected: %r", q[:60])
                continue

        variants.append({
            "q": q,
            "source": "llm",
            "intent": intent,
            "used_terms": used_terms if isinstance(used_terms, list) else [],
            "notes": notes,
        })

    variants.sort(key=lambda v: (v.get("intent", ""), v["q"]))
    return variants


def _passes_drift_guard(variant: str, original: str, profile: QueryExpansionProfile) -> bool:
    """Check whether a variant is sufficiently related to the original query."""
    dg = profile.policies.drift_guard
    if not dg.enabled:
        return True

    if dg.method == "lexical_overlap":
        orig_tokens = set(original.lower().split())
        var_tokens = set(variant.lower().split())
        if not orig_tokens or not var_tokens:
            return True
        overlap = len(orig_tokens & var_tokens)
        union = len(orig_tokens | var_tokens)
        jaccard = overlap / union if union > 0 else 0.0
        return jaccard >= dg.threshold

    return True


def _decompose(query: str, profile: QueryExpansionProfile) -> List[Dict[str, Any]]:
    """Decompose multi-hop queries into subqueries."""
    if not profile.decomposition.enabled:
        return []

    if not _should_decompose(query, profile):
        return []

    return decompose_query(query, profile)


_CONJUNCTION_PATTERNS = [
    re.compile(r"\band\b", re.IGNORECASE),
    re.compile(r"\bwhile\b", re.IGNORECASE),
    re.compile(r"\bduring\b", re.IGNORECASE),
    re.compile(r"\bwhen\b.*\band\b", re.IGNORECASE),
    re.compile(r"\bbut\b", re.IGNORECASE),
]

_MULTI_FACET_TEMPLATES = [
    re.compile(r"combat.*spell", re.IGNORECASE),
    re.compile(r"spell.*combat", re.IGNORECASE),
    re.compile(r"movement.*attack", re.IGNORECASE),
    re.compile(r"attack.*movement", re.IGNORECASE),
    re.compile(r"initiative.*action", re.IGNORECASE),
    re.compile(r"saving throw.*damage", re.IGNORECASE),
]


def _should_decompose(query: str, profile: QueryExpansionProfile) -> bool:
    """Decide whether to decompose based on trigger heuristics."""
    when = profile.decomposition.when
    if when == "never":
        return False
    if when == "always":
        return True

    tokens = query.split()
    if len(tokens) > 15:
        return True

    for pattern in _CONJUNCTION_PATTERNS:
        if pattern.search(query):
            return True

    for template in _MULTI_FACET_TEMPLATES:
        if template.search(query):
            return True

    return False


def _dedupe_and_cap(
    expansions: List[Dict[str, Any]],
    max_total: Optional[int],
    include_original: bool,
) -> List[Dict[str, Any]]:
    """Deduplicate by normalized query text, preserve original first, then cap."""
    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []

    for exp in expansions:
        key = exp["q"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(exp)

    if max_total is None:
        return deduped

    # Original always counts; cap the rest
    if include_original and deduped:
        # original is deduped[0]; cap expansions to max_total total (including original)
        return deduped[: max_total + 1]
    return deduped[:max_total]

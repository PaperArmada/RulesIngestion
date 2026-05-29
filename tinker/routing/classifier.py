"""Query → retrieval-bucket classifier (qwen3:4b).

Replaces the smoke-test prompt in tinker.llm.classify (which only passed
bucket *names*) with a richer prompt that includes per-bucket definitions
and 3 few-shot examples. The bucket reference comes from
`tinker.routing.buckets.render_bucket_descriptions`.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from typing import Any

from tinker.backends import current_backend
from tinker.cache import TinkerCache
from tinker.routing.buckets import (
    BUCKET_BY_ID,
    BUCKET_IDS,
    render_bucket_descriptions,
)
from tinker.runtime_config import CFG


@dataclass(frozen=True)
class ClassifyResult:
    bucket: str
    confidence: float
    reason: str
    latency_ms: float
    raw: dict[str, Any]
    cached: bool = False


def _build_prompt(query: str, self_portrait_summary: str | None) -> tuple[str, str]:
    """Return (system, user) message strings."""
    system = (
        "You are a query classifier for a retrieval system over a tabletop "
        "RPG rulebook. Given a user query, pick the SINGLE most appropriate "
        "retrieval bucket from the catalog. Bucket choice should be driven "
        "by the relationship between the query and the evidence that would "
        "answer it (does the query name the evidence by its corpus term? "
        "is the answer a single passage or assembled from many? is the "
        "answer-shape similar to the question-shape, or different?).\n\n"
        "Respond with ONLY valid JSON of the form:\n"
        '{"bucket": "<bucket_id>", "confidence": <0..1>, "reason": "<≤30 words>"}\n'
        "The bucket value must be one of the listed ids exactly."
    )
    bucket_block = render_bucket_descriptions()
    self_portrait_block = (
        f"\nCorpus self-portrait (for context):\n{self_portrait_summary}\n"
        if self_portrait_summary
        else ""
    )
    user = (
        f"Bucket catalog:\n{bucket_block}\n"
        f"{self_portrait_block}\n"
        f"Query: {query}\n\n"
        "Pick the bucket that best matches this query."
    )
    return system, user


def classify_query(
    query: str,
    *,
    self_portrait_summary: str | None = None,
    cache: TinkerCache | None = None,
    think: bool = False,
) -> ClassifyResult:
    """Classify a query into one of the 8 retrieval buckets.

    Routes through the configured LLM backend. Cache key includes the
    backend name so an Ollama-cached row doesn't shadow a Gemini run.

    On unparseable JSON or unknown bucket id, returns bucket="entity_anchored_single"
    (the safest fast-path default) with confidence=0.0 and the failure
    noted in `reason`.
    """
    backend = current_backend()
    system, user = _build_prompt(query, self_portrait_summary)
    payload = {
        "role": "classify",
        "system": system,
        "user": user,
    }
    cache_model_key = f"{backend.name}:classify"
    if cache is not None:
        hit = cache.get_llm("classify", cache_model_key, payload)
        if hit is not None:
            try:
                parsed = json.loads(hit)
                return _coerce_result(parsed, latency_ms=0.0, cached=True, raw_text=hit)
            except Exception:
                pass  # corrupted cache row; re-run

    t0 = time.perf_counter()
    result = backend.chat(
        role="classify",
        system=system,
        user=user,
        think=think,
        json_format=True,
    )
    latency_ms = (time.perf_counter() - t0) * 1000
    text = result.text

    if cache is not None:
        cache.put_llm("classify", cache_model_key, payload, text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return ClassifyResult(
            bucket="entity_anchored_single",
            confidence=0.0,
            reason=f"JSON parse error: {exc}",
            latency_ms=latency_ms,
            raw={"text": text, "backend": backend.name},
            cached=False,
        )

    return _coerce_result(parsed, latency_ms=latency_ms, cached=False, raw_text=text)


# ---------------------------------------------------------------------------
# q-ROFS classifier (Pythagorean: q=2)
# ---------------------------------------------------------------------------

DEFAULT_Q = 2


@dataclass(frozen=True)
class BucketMembership:
    bucket: str
    mu: float       # strength of belonging in [0,1]
    nu: float       # strength of not-belonging in [0,1]
    pi: float       # hesitation, computed as (1 - mu^q - nu^q)^(1/q)
    reason: str


@dataclass(frozen=True)
class QROFSResult:
    """q-Rung Orthopair Fuzzy classification (Pythagorean by default).

    Returns a per-bucket (mu, nu, pi) triple instead of a single label.
    Use chosen_bucket / chosen_confidence for fast-path routing; use
    second_bucket + hesitation when the router wants to consider multi-
    path retrieval.
    """

    memberships: dict[str, BucketMembership]
    chosen_bucket: str
    chosen_mu: float
    chosen_nu: float
    chosen_pi: float
    second_bucket: str
    second_mu: float
    margin: float  # chosen_mu - second_mu
    latency_ms: float
    q: int = DEFAULT_Q
    raw: dict[str, Any] = field(default_factory=dict)
    cached: bool = False


def _renormalize_pair(mu: float, nu: float, q: int) -> tuple[float, float, float]:
    """Project (mu, nu) onto the q-rung constraint surface if violated.

    Returns (mu', nu', pi). When mu^q + nu^q > 1, both are scaled down so
    the constraint holds with equality (pi -> 0). When mu^q + nu^q <= 1,
    pi = (1 - mu^q - nu^q)^(1/q).
    """
    mu = max(0.0, min(1.0, mu))
    nu = max(0.0, min(1.0, nu))
    total = (mu ** q) + (nu ** q)
    if total > 1.0:
        # Scale both by the q-th root of the violation factor.
        scale = total ** (1.0 / q)
        mu = mu / scale
        nu = nu / scale
        pi = 0.0
    else:
        pi = (1.0 - (mu ** q) - (nu ** q)) ** (1.0 / q)
    return mu, nu, pi


def _build_qrofs_prompt(
    query: str, self_portrait_summary: str | None, q: int
) -> tuple[str, str]:
    system = (
        "You are a query analyzer for a retrieval system over a tabletop RPG "
        "rulebook. For each retrieval bucket, estimate a q-rung orthopair "
        "fuzzy pair (mu, nu) where:\n"
        "  mu in [0,1] = how strongly this query fits the bucket\n"
        "  nu in [0,1] = how strongly this query does NOT fit the bucket\n"
        f"  Pythagorean constraint (q={q}): mu^{q} + nu^{q} <= 1\n"
        "Hesitation pi = (1 - mu^q - nu^q)^(1/q) is computed afterwards and "
        "encodes genuine uncertainty. You do NOT report pi.\n\n"
        "Guidelines:\n"
        "- If a query clearly fits a bucket: high mu, low nu.\n"
        "- If a query clearly does NOT fit: low mu, high nu.\n"
        "- If a query has overlap with multiple buckets: assign moderate mu "
        "to each, with nu reflecting the weakest aspects.\n"
        "- A query genuinely between two buckets should produce moderate mu "
        "for both with moderate hesitation (you don't have to commit).\n\n"
        "Respond with ONLY a JSON object of the form:\n"
        '{"memberships": [{"bucket": "<id>", "mu": <0..1>, '
        '"nu": <0..1>, "reason": "<≤20 words>"}, ...]}\n'
        "Include an entry for EVERY bucket listed below, in the catalog's order."
    )
    bucket_block = render_bucket_descriptions()
    self_portrait_block = (
        f"\nCorpus self-portrait (for context):\n{self_portrait_summary}\n"
        if self_portrait_summary
        else ""
    )
    user = (
        f"Bucket catalog:\n{bucket_block}\n"
        f"{self_portrait_block}\n"
        f"Query: {query}\n\n"
        "Estimate (mu, nu) for every bucket."
    )
    return system, user


def classify_query_qrofs(
    query: str,
    *,
    self_portrait_summary: str | None = None,
    cache: TinkerCache | None = None,
    q: int = DEFAULT_Q,
    think: bool | None = None,
) -> QROFSResult:
    """Classify a query via q-rung orthopair fuzzy membership.

    Returns per-bucket (mu, nu, pi). Routing logic outside this function
    decides what to do with the multi-bucket signal. `think` defaults to
    the CFG.think_classify knob when not explicitly overridden; the cache
    key includes the think flag so thinking/non-thinking runs don't alias.
    """
    backend = current_backend()
    use_think = CFG.think_classify if think is None else think
    system, user = _build_qrofs_prompt(query, self_portrait_summary, q)
    payload = {"role": "classify_qrofs", "system": system, "user": user, "q": q}
    cache_model_key = f"{backend.name}:classify_qrofs:think={int(use_think)}"

    if cache is not None:
        hit = cache.get_llm("classify_qrofs", cache_model_key, payload)
        if hit is not None:
            try:
                parsed = json.loads(hit)
                return _coerce_qrofs_result(
                    parsed, q=q, latency_ms=0.0, cached=True, raw_text=hit
                )
            except Exception:
                pass

    t0 = time.perf_counter()
    result = backend.chat(
        role="classify_qrofs",
        system=system,
        user=user,
        think=use_think,
        json_format=True,
    )
    latency_ms = (time.perf_counter() - t0) * 1000
    text = result.text
    if cache is not None:
        cache.put_llm("classify_qrofs", cache_model_key, payload, text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return _qrofs_fallback(
            f"JSON parse error: {exc}", text, latency_ms, q
        )

    return _coerce_qrofs_result(
        parsed, q=q, latency_ms=latency_ms, cached=False, raw_text=text
    )


def _coerce_qrofs_result(
    parsed: dict[str, Any],
    *,
    q: int,
    latency_ms: float,
    cached: bool,
    raw_text: str,
) -> QROFSResult:
    raw_memberships = parsed.get("memberships")
    if not isinstance(raw_memberships, list):
        return _qrofs_fallback(
            "no 'memberships' list in response", raw_text, latency_ms, q
        )

    memberships: dict[str, BucketMembership] = {}
    for entry in raw_memberships:
        if not isinstance(entry, dict):
            continue
        bucket = str(entry.get("bucket", "")).strip()
        if bucket not in BUCKET_BY_ID:
            continue
        try:
            mu = float(entry.get("mu", 0.0))
            nu = float(entry.get("nu", 0.0))
        except (TypeError, ValueError):
            mu, nu = 0.0, 0.0
        mu, nu, pi = _renormalize_pair(mu, nu, q)
        reason = str(entry.get("reason", ""))[:200]
        memberships[bucket] = BucketMembership(
            bucket=bucket, mu=mu, nu=nu, pi=pi, reason=reason
        )

    # Fill missing buckets with mu=nu=0 (max hesitation).
    for bid in BUCKET_IDS:
        if bid not in memberships:
            memberships[bid] = BucketMembership(
                bucket=bid, mu=0.0, nu=0.0, pi=1.0,
                reason="(missing from model output)"
            )

    # Rank by mu, then by -pi (less hesitation breaks ties).
    ranked = sorted(
        memberships.values(),
        key=lambda m: (-m.mu, m.pi),
    )
    chosen = ranked[0]
    second = ranked[1] if len(ranked) > 1 else ranked[0]

    return QROFSResult(
        memberships=memberships,
        chosen_bucket=chosen.bucket,
        chosen_mu=chosen.mu,
        chosen_nu=chosen.nu,
        chosen_pi=chosen.pi,
        second_bucket=second.bucket,
        second_mu=second.mu,
        margin=chosen.mu - second.mu,
        latency_ms=latency_ms,
        q=q,
        raw={"text": raw_text, "parsed": parsed},
        cached=cached,
    )


def _qrofs_fallback(
    reason: str, raw_text: str, latency_ms: float, q: int
) -> QROFSResult:
    memberships = {
        bid: BucketMembership(
            bucket=bid, mu=0.0, nu=0.0, pi=1.0, reason="(fallback) " + reason
        )
        for bid in BUCKET_IDS
    }
    safe_default = "entity_anchored_single"
    return QROFSResult(
        memberships=memberships,
        chosen_bucket=safe_default,
        chosen_mu=0.0,
        chosen_nu=0.0,
        chosen_pi=1.0,
        second_bucket=safe_default,
        second_mu=0.0,
        margin=0.0,
        latency_ms=latency_ms,
        q=q,
        raw={"text": raw_text, "fallback_reason": reason},
        cached=False,
    )


def _coerce_result(
    parsed: dict[str, Any],
    *,
    latency_ms: float,
    cached: bool,
    raw_text: str,
) -> ClassifyResult:
    bucket = str(parsed.get("bucket", "")).strip()
    if bucket not in BUCKET_BY_ID:
        return ClassifyResult(
            bucket="entity_anchored_single",
            confidence=0.0,
            reason=f"unknown bucket id '{bucket}'; valid={list(BUCKET_IDS)}",
            latency_ms=latency_ms,
            raw={"text": raw_text, "parsed": parsed},
            cached=cached,
        )
    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    reason = str(parsed.get("reason", ""))
    return ClassifyResult(
        bucket=bucket,
        confidence=confidence,
        reason=reason,
        latency_ms=latency_ms,
        raw={"text": raw_text, "parsed": parsed},
        cached=cached,
    )

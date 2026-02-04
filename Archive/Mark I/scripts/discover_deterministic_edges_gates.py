from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Tuple

from scripts.discover_deterministic_edges_constants import (
    MAX_NEAR_DUPLICATE_SAMPLES,
    STRICT_RELATIONS,
)
from scripts.discover_deterministic_edges_text import _normalize_title


def _is_suspect_token(token: str) -> bool:
    if not token or len(token) < 4:
        return False
    alpha = sum(1 for ch in token if ch.isalpha())
    non_alpha = len(token) - alpha
    if alpha == 0:
        return non_alpha >= 3
    return (non_alpha / len(token)) >= 0.4


def _compute_suspect_token_rate(chunks: List[Dict[str, Any]]) -> Tuple[float, int, int]:
    total_tokens = 0
    suspect_tokens = 0
    for chunk in chunks:
        text = chunk.get("text", "") or ""
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-\_'\.]*", text)
        total_tokens += len(tokens)
        suspect_tokens += sum(1 for token in tokens if _is_suspect_token(token))
    rate = (suspect_tokens / total_tokens) if total_tokens else 0.0
    return rate, suspect_tokens, total_tokens


def _edit_distance_leq_one(left: str, right: str) -> bool:
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        mismatches = sum(1 for a, b in zip(left, right) if a != b)
        return mismatches <= 1
    if len(left) < len(right):
        left, right = right, left
    # left is longer by one
    i = 0
    j = 0
    found_edit = False
    while i < len(left) and j < len(right):
        if left[i] == right[j]:
            i += 1
            j += 1
            continue
        if found_edit:
            return False
        found_edit = True
        i += 1
    return True


def _find_near_duplicate_titles(titles: List[str]) -> Tuple[int, List[Tuple[str, str]]]:
    buckets: Dict[Tuple[str, int], List[str]] = defaultdict(list)
    for title in titles:
        if not title or len(title) < 4:
            continue
        key = (title[0], len(title))
        buckets[key].append(title)

    pairs: List[Tuple[str, str]] = []
    count = 0
    for (prefix, length), bucket in buckets.items():
        if len(bucket) < 1:
            continue
        for neighbor_length in (length - 1, length, length + 1):
            neighbor_bucket = buckets.get((prefix, neighbor_length))
            if not neighbor_bucket:
                continue
            for left in bucket:
                for right in neighbor_bucket:
                    if left >= right:
                        continue
                    if _edit_distance_leq_one(left, right):
                        count += 1
                        if len(pairs) < MAX_NEAR_DUPLICATE_SAMPLES:
                            pairs.append((left, right))
    return count, pairs


def _build_gate_titles(indices: Dict[str, Dict[str, set[str]]]) -> List[str]:
    titles: set[str] = set()
    for key in ("section_exact", "table", "figure", "chapter"):
        for title in indices.get(key, {}).keys():
            normalized = _normalize_title(title)
            if normalized:
                titles.add(normalized)
    return sorted(titles)


def _run_ocr_spelling_gates(
    candidates: List[Dict[str, Any]],
    indices: Dict[str, Dict[str, set[str]]],
    chunks: List[Dict[str, Any]],
    unresolved_rate_max: float,
    suspect_token_rate_max: float,
    suspect_token_min_tokens: int,
    near_duplicate_max: int,
    near_duplicate_rate_max: float,
    hard_fail: bool,
) -> Dict[str, Any]:
    strict_candidates = [c for c in candidates if (c.get("relation") in STRICT_RELATIONS)]
    unresolved = [
        c for c in strict_candidates if int(c.get("resolution_count", 0)) == 0
    ]
    unresolved_rate = (
        (len(unresolved) / len(strict_candidates)) if strict_candidates else 0.0
    )

    suspect_rate, suspect_tokens, total_tokens = _compute_suspect_token_rate(chunks)

    titles = _build_gate_titles(indices)
    near_dup_count, near_dup_samples = _find_near_duplicate_titles(titles)
    near_dup_rate = (near_dup_count / len(titles)) if titles else 0.0

    failures = []
    if unresolved_rate > unresolved_rate_max:
        failures.append(
            f"unresolved_rate={unresolved_rate:.2%} (limit {unresolved_rate_max:.2%})"
        )
    suspect_gate_skipped = total_tokens < suspect_token_min_tokens
    if not suspect_gate_skipped and suspect_rate > suspect_token_rate_max:
        failures.append(
            f"suspect_token_rate={suspect_rate:.2%} (limit {suspect_token_rate_max:.2%})"
        )
    if near_dup_count > near_duplicate_max or near_dup_rate > near_duplicate_rate_max:
        failures.append(
            "near_duplicate_titles="
            f"{near_dup_count} (rate {near_dup_rate:.2%}, "
            f"limits count {near_duplicate_max}, rate {near_duplicate_rate_max:.2%})"
        )

    summary = {
        "unresolved_rate": round(unresolved_rate, 4),
        "unresolved_total": len(unresolved),
        "strict_candidates": len(strict_candidates),
        "suspect_token_rate": round(suspect_rate, 4),
        "suspect_token_count": suspect_tokens,
        "total_tokens": total_tokens,
        "suspect_token_gate_skipped": suspect_gate_skipped,
        "suspect_token_min_tokens": suspect_token_min_tokens,
        "near_duplicate_count": near_dup_count,
        "near_duplicate_rate": round(near_dup_rate, 4),
        "near_duplicate_samples": near_dup_samples,
        "title_count": len(titles),
        "gate_failures": failures,
        "prune_unresolved_strict": unresolved_rate > unresolved_rate_max,
    }

    if failures:
        print("⚠️  OCR/spelling gates failed:")
        for failure in failures:
            print(f"  - {failure}")
        if hard_fail:
            raise ValueError("OCR/spelling gates failed; aborting deterministic edge discovery.")
        print("⚠️  Continuing despite gate failures (soft-gate mode).")

    return summary

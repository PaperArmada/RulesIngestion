"""Multi-query retrieval wrapper: retrieve per expansion, fuse with RRF."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from retrieval_lab.query_enhancement.cache import QueryEnhancementCache
from retrieval_lab.query_enhancement.enhancer import enhance_queries
from retrieval_lab.query_enhancement.profile import QueryExpansionProfile

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _lex_tokens(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _lex_score(query: str, doc_text: str) -> float:
    """Cheap lexical similarity signal for diagnostic reranking.

    Scoring goal: prefer docs that share more content tokens with the query, while
    down-weighting very long docs.
    """
    q_toks = _lex_tokens(query)
    d_toks = _lex_tokens(doc_text)
    if not q_toks or not d_toks:
        return 0.0
    q_set = set(q_toks)
    d_set = set(d_toks)
    overlap = len(q_set & d_set)
    # Normalize by doc length to avoid always preferring huge chunks.
    return float(overlap) / (len(d_set) ** 0.5)


def lexical_rerank_tail_segment(
    *,
    ranked_lists: List[List[str]],
    score_lists: List[List[float]],
    query_texts: List[str],
    id_to_text: Dict[str, str],
    locked_prefixes: List[List[str]],
    admission_cutoff: int,
    rerank_window: int = 50,
    eligible: Optional[List[bool]] = None,
) -> Tuple[List[List[str]], List[List[float]]]:
    """Rerank tail (positions len(locked_prefix)+1..admission_cutoff) using lexical scores.

    This keeps the locked prefix fixed and reorders only the tail segment.
    """
    if len(ranked_lists) != len(score_lists) or len(ranked_lists) != len(query_texts) or len(ranked_lists) != len(locked_prefixes):
        raise ValueError("ranked_lists, score_lists, query_texts, and locked_prefixes must be same length")

    out_ranked: List[List[str]] = []
    out_scores: List[List[float]] = []
    cutoff = max(0, int(admission_cutoff))
    window = max(1, int(rerank_window))

    for i in range(len(ranked_lists)):
        if eligible is not None and (i >= len(eligible) or not eligible[i]):
            out_ranked.append(ranked_lists[i])
            out_scores.append(score_lists[i])
            continue
        ids = ranked_lists[i] or []
        scores = score_lists[i] or []
        if len(ids) != len(scores):
            n = min(len(ids), len(scores))
            ids = ids[:n]
            scores = scores[:n]
        score_by_id = {cid: float(sc) for cid, sc in zip(ids, scores)}

        locked = list(locked_prefixes[i] or [])
        locked_set = set(locked)
        q = query_texts[i] or ""

        tail_all = [cid for cid in ids if cid not in locked_set]
        tail_cap = max(0, (cutoff - len(locked))) if cutoff else len(tail_all)
        tail = tail_all[:tail_cap]
        tail_rest = tail_all[tail_cap:]

        tail_rerank = tail[:window]
        tail_hold = tail[window:]
        scored = [(cid, _lex_score(q, id_to_text.get(cid, ""))) for cid in tail_rerank]
        scored.sort(key=lambda p: (-p[1], p[0]))
        tail_sorted = [cid for cid, _ in scored]

        new_ids = locked + tail_sorted + tail_hold + tail_rest
        new_scores = (
            [score_by_id.get(cid, 0.0) for cid in locked]
            + [sc for _, sc in scored]
            + [score_by_id.get(cid, 0.0) for cid in tail_hold]
            + [score_by_id.get(cid, 0.0) for cid in tail_rest]
        )
        out_ranked.append(new_ids)
        out_scores.append(new_scores)

    return out_ranked, out_scores


def expand_query_texts(
    query_texts: List[str],
    profile: QueryExpansionProfile,
    mode: str,
    cache: Optional[QueryEnhancementCache] = None,
) -> Tuple[List[List[str]], List[List[Dict[str, Any]]]]:
    """Expand each query text into variant groups.

    Returns:
        expanded_groups: List[List[str]] -- per-query list of variant query strings
        expansion_logs: List[List[Dict]] -- per-query expansion metadata for logging
    """
    expansion_results = enhance_queries(query_texts, profile, mode=mode, cache=cache)

    expanded_groups: List[List[str]] = []
    expansion_logs: List[List[Dict[str, Any]]] = []
    for group in expansion_results:
        expanded_groups.append([e["q"] for e in group])
        expansion_logs.append(group)

    return expanded_groups, expansion_logs


def expand_query_texts_per_query_modes(
    query_texts: List[str],
    per_query_modes: List[str],
    profile: QueryExpansionProfile,
    cache: Optional[QueryEnhancementCache] = None,
) -> Tuple[List[List[str]], List[List[Dict[str, Any]]]]:
    """Expand each query text with an explicitly chosen mode per query.

    This enables tier-gated behavior (e.g., decompose only for T2/T3).
    """
    if len(query_texts) != len(per_query_modes):
        raise ValueError("query_texts and per_query_modes must be same length")

    expanded_groups: List[List[str]] = []
    expansion_logs: List[List[Dict[str, Any]]] = []

    for qt, mode in zip(query_texts, per_query_modes):
        group = enhance_queries([qt], profile, mode=mode, cache=cache)[0]
        expanded_groups.append([e["q"] for e in group])
        expansion_logs.append(group)

    return expanded_groups, expansion_logs


def fuse_multi_query_rankings(
    per_expansion_rankings: List[List[List[str]]],
    rrf_k: int = 60,
    stable_tiebreak: bool = True,
) -> Tuple[List[List[str]], List[List[float]]]:
    """RRF-fuse multiple ranked lists per query into a single ranking.

    Args:
        per_expansion_rankings: per_expansion_rankings[query_i][expansion_j] = list of doc IDs
        rrf_k: RRF constant
        stable_tiebreak: if True, break ties by doc ID lexical order

    Returns:
        fused_ranked_lists, fused_score_lists (one per query)
    """
    from retrieval_lab.sparse_retrieval import reciprocal_rank_fusion

    if not per_expansion_rankings:
        return [], []

    # Check if any query has multiple expansions
    has_multi = any(len(exps) > 1 for exps in per_expansion_rankings)
    if not has_multi:
        # Single expansion per query: no fusion needed
        ranked = [exps[0] if exps else [] for exps in per_expansion_rankings]
        scores = [[1.0 / (rrf_k + r + 1) for r in range(len(ids))] for ids in ranked]
        return ranked, scores

    fused_ranked, fused_scores = reciprocal_rank_fusion(
        per_expansion_rankings, k=rrf_k,
    )

    if stable_tiebreak:
        for i in range(len(fused_ranked)):
            ids = fused_ranked[i]
            sc = fused_scores[i]
            pairs = list(zip(ids, sc))
            pairs.sort(key=lambda p: (-p[1], p[0]))
            fused_ranked[i] = [p[0] for p in pairs]
            fused_scores[i] = [p[1] for p in pairs]

    return fused_ranked, fused_scores


def fuse_only_add(
    *,
    baseline_ranked_lists: List[List[str]],
    baseline_score_lists: Optional[List[List[float]]],
    variant_ranked_lists: List[List[List[str]]],
    variant_score_lists: Optional[List[List[List[float]]]] = None,
    baseline_keep_n: int = 12,
    admission_cutoff: int = 20,
    append_score_band: float = 1e-6,
) -> Tuple[List[List[str]], List[List[float]], List[Dict[str, Any]]]:
    """Only-add fusion: lock baseline prefix, then append novel candidates from variants.

    This is a recall-only enhancement policy that guarantees the locked baseline prefix
    is present in the final admitted set (no eviction).

    Determinism:
    - baseline order preserved (prefix locked)
    - variant flatten order is stable: variant_0 list, then variant_1, ...
    - within each list, tie-breaking must already be stable upstream
    - insertion uses "first seen wins"
    """
    if len(baseline_ranked_lists) != len(variant_ranked_lists):
        raise ValueError("baseline_ranked_lists and variant_ranked_lists must be same length")

    fused_ranked: List[List[str]] = []
    fused_scores: List[List[float]] = []
    debug: List[Dict[str, Any]] = []

    eps = 1e-12
    for i in range(len(baseline_ranked_lists)):
        baseline_ids_full = list(baseline_ranked_lists[i] or [])
        baseline_scores_full = list((baseline_score_lists or [[]])[i] or []) if baseline_score_lists is not None else []

        keep_n = max(0, int(baseline_keep_n))
        cutoff = max(0, int(admission_cutoff))
        keep_n = min(keep_n, cutoff) if cutoff else keep_n

        baseline_ids = baseline_ids_full[:keep_n]
        baseline_scores = baseline_scores_full[:keep_n] if baseline_scores_full else [0.0] * len(baseline_ids)

        selected: List[str] = []
        selected_scores: List[float] = []
        seen = set()

        # Step 1: lock in baseline prefix
        for cid, sc in zip(baseline_ids, baseline_scores):
            if cid in seen:
                continue
            selected.append(cid)
            selected_scores.append(float(sc))
            seen.add(cid)

        # Compute band for appended scores so downstream "sort by score" does not intermix.
        min_baseline_score = min(selected_scores) if selected_scores else 0.0
        band = float(append_score_band) if append_score_band is not None else 0.0

        added: List[str] = []
        add_idx = 0

        # Step 2: add novel candidates from variants, in deterministic first-seen order
        for vj, v_ids in enumerate(variant_ranked_lists[i] or []):
            for cid in v_ids or []:
                if cutoff and len(selected) >= cutoff:
                    break
                if cid in seen:
                    continue
                selected.append(cid)
                # Always below baseline band.
                selected_scores.append(min_baseline_score - band - eps - (add_idx * eps))
                seen.add(cid)
                added.append(cid)
                add_idx += 1
            if cutoff and len(selected) >= cutoff:
                break

        # Optional: if no cutoff provided, preserve baseline list length + all novel adds.
        # (Callers typically set cutoff to existing retrieval_cutoff / admission cap.)
        fused_ranked.append(selected)
        fused_scores.append(selected_scores)

        # Regression guard: every baseline locked id must be present.
        guard_ok = all(cid in seen for cid in baseline_ids)
        if not guard_ok:
            missing = [cid for cid in baseline_ids if cid not in seen]
            raise AssertionError(f"only_add regression_guard failed: missing baseline ids: {missing}")

        debug.append(
            {
                "baseline_keep_n": keep_n,
                "admission_cutoff": cutoff,
                "baseline_topN": baseline_ids,
                "variants_count": len(variant_ranked_lists[i] or []),
                "only_add_added": added,
                "final_admitted": selected,
                "regression_guard_passed": True,
            }
        )

    return fused_ranked, fused_scores, debug


def fuse_union_rerank(
    *,
    per_expansion_rankings: List[List[List[str]]],
    per_expansion_scores: Optional[List[List[List[float]]]] = None,
    admission_cutoff: int = 20,
) -> Tuple[List[List[str]], List[List[float]]]:
    """Union + rerank by best score (stable tiebreak by doc_id).

    Note: Unlike only_add, this can demote baseline hits; it is provided as an opt-in.
    """
    fused_ranked: List[List[str]] = []
    fused_scores: List[List[float]] = []
    cutoff = max(0, int(admission_cutoff))

    for qi, groups in enumerate(per_expansion_rankings):
        score_groups = per_expansion_scores[qi] if per_expansion_scores is not None else None
        best: Dict[str, float] = {}
        for gj, ids in enumerate(groups or []):
            scores = (score_groups[gj] if (score_groups and gj < len(score_groups)) else None) if score_groups else None
            for rk, cid in enumerate(ids or []):
                sc = float(scores[rk]) if (scores and rk < len(scores)) else float(1.0 / (rk + 1))
                if cid not in best or sc > best[cid]:
                    best[cid] = sc
        ordered = sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))
        if cutoff:
            ordered = ordered[:cutoff]
        fused_ranked.append([cid for cid, _ in ordered])
        fused_scores.append([float(sc) for _, sc in ordered])
    return fused_ranked, fused_scores


def lock_prefix(
    *,
    ranked_lists: List[List[str]],
    score_lists: List[List[float]],
    locked_prefixes: List[List[str]],
) -> Tuple[List[List[str]], List[List[float]]]:
    """Move locked_prefixes[i] to the front in-order, preserving remaining order.

    This is useful to enforce "no demotion" guarantees after downstream stages that
    may reorder candidates (boosting, reranking, hybrid fusion, etc.).
    """
    if len(ranked_lists) != len(score_lists) or len(ranked_lists) != len(locked_prefixes):
        raise ValueError("ranked_lists, score_lists, and locked_prefixes must be same length")

    out_ranked: List[List[str]] = []
    out_scores: List[List[float]] = []

    for i in range(len(ranked_lists)):
        ids = ranked_lists[i] or []
        scores = score_lists[i] or []
        if len(ids) != len(scores):
            # Best-effort: align by truncation to the shorter list.
            n = min(len(ids), len(scores))
            ids = ids[:n]
            scores = scores[:n]

        score_by_id = {cid: float(sc) for cid, sc in zip(ids, scores)}
        # Insert locked prefix even if missing from ids (baseline lock beats truncation).
        locked = list(locked_prefixes[i] or [])
        locked_set = set(locked)
        tail = [cid for cid in ids if cid not in locked_set]
        new_ids = locked + tail
        new_scores = [score_by_id.get(cid, 0.0) for cid in new_ids]
        out_ranked.append(new_ids)
        out_scores.append(new_scores)

    return out_ranked, out_scores

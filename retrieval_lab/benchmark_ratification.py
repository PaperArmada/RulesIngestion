"""Benchmark ratification helpers for stable vs working benchmark tracks."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Optional

TRACK_RATIFIED_CORE = "ratified_core"
TRACK_WORKING_SET = "working_set"

EVIDENCE_SCOPE_UNGROUNDED = "ungrounded"
EVIDENCE_SCOPE_SINGLE_ANCHOR = "single_anchor"
EVIDENCE_SCOPE_MULTI_ANCHOR = "multi_anchor"
EVIDENCE_SCOPE_COMPOSITIONAL = "compositional"

RATIFIED_MAX_REQUIRED_GOLD = 2


def _clean_ids(values: Iterable[Any]) -> List[str]:
    return [str(x).strip() for x in values if str(x).strip()]


def query_track(query: Dict[str, Any]) -> str:
    return str(query.get("benchmark_track") or TRACK_RATIFIED_CORE).strip() or TRACK_RATIFIED_CORE


def query_required_gold(query: Dict[str, Any]) -> List[str]:
    return _clean_ids(query.get("required_gold") or [])


def query_required_anchor_ids(query: Dict[str, Any]) -> List[str]:
    return _clean_ids(query.get("required_anchor_ids") or [])


def query_supporting_gold(query: Dict[str, Any]) -> List[str]:
    return _clean_ids(query.get("supporting_gold") or [])


def query_all_gold(query: Dict[str, Any]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for gold_id in query_required_gold(query) + query_supporting_gold(query) + _clean_ids(query.get("gold_unit_ids") or []):
        if gold_id in seen:
            continue
        seen.add(gold_id)
        ordered.append(gold_id)
    return ordered


def query_evidence_scope(query: Dict[str, Any]) -> str:
    explicit = str(query.get("evidence_scope") or "").strip()
    if explicit:
        return explicit
    required_count = len(query_required_anchor_ids(query) or query_required_gold(query))
    if required_count <= 0:
        return EVIDENCE_SCOPE_UNGROUNDED
    if required_count == 1:
        return EVIDENCE_SCOPE_SINGLE_ANCHOR
    if required_count == 2:
        return EVIDENCE_SCOPE_MULTI_ANCHOR
    return EVIDENCE_SCOPE_COMPOSITIONAL


def query_missing_gold_ids(
    query: Dict[str, Any],
    *,
    corpus_ids: Optional[Iterable[str]] = None,
) -> List[str]:
    if corpus_ids is not None:
        corpus_set = {str(cid).strip() for cid in corpus_ids if str(cid).strip()}
        return [gold_id for gold_id in query_all_gold(query) if gold_id not in corpus_set]
    missing: List[str] = []
    for chunk in query.get("gold_chunks") or []:
        if not isinstance(chunk, dict):
            continue
        gold_id = str(chunk.get("id") or "").strip()
        if gold_id and bool(chunk.get("missing_in_corpus")):
            missing.append(gold_id)
    return missing


def summarize_ratification(
    queries: List[Dict[str, Any]],
    *,
    corpus_ids: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    track_counts: Counter[str] = Counter()
    issues: List[Dict[str, Any]] = []
    per_query: List[Dict[str, Any]] = []
    clean_query_ids: List[str] = []
    ratified_query_ids: List[str] = []
    invalid_ratified_query_ids: List[str] = []

    for query in queries:
        query_id = str(query.get("id") or "")
        track = query_track(query)
        evidence_scope = query_evidence_scope(query)
        required_anchor_ids = query_required_anchor_ids(query)
        required_gold = query_required_gold(query)
        supporting_gold = query_supporting_gold(query)
        logical_required_count = len(required_anchor_ids) if required_anchor_ids else len(required_gold)
        missing_gold_ids = query_missing_gold_ids(query, corpus_ids=corpus_ids)
        missing_required_ids = [gold_id for gold_id in required_gold if gold_id in set(missing_gold_ids)]
        query_issues: List[Dict[str, Any]] = []

        track_counts[track] += 1
        if track == TRACK_RATIFIED_CORE:
            ratified_query_ids.append(query_id)
            status = str(query.get("_status") or "").strip().lower()
            if status == "pending":
                query_issues.append(
                    {
                        "level": "error",
                        "code": "pending_status",
                        "message": "Ratified query is still pending.",
                    }
                )
            if logical_required_count <= 0:
                query_issues.append(
                    {
                        "level": "error",
                        "code": "required_gold_empty",
                        "message": "Ratified query must define at least one required gold anchor.",
                    }
                )
            if logical_required_count > RATIFIED_MAX_REQUIRED_GOLD:
                query_issues.append(
                    {
                        "level": "error",
                        "code": "required_gold_exceeds_cap",
                        "message": (
                            "Ratified query exceeds the required_gold cap of "
                            f"{RATIFIED_MAX_REQUIRED_GOLD}."
                        ),
                        "details": {
                            "required_gold_size": len(required_gold),
                            "logical_required_anchor_count": logical_required_count,
                        },
                    }
                )
            if missing_gold_ids:
                query_issues.append(
                    {
                        "level": "error",
                        "code": "gold_missing_in_corpus",
                        "message": "Ratified query references gold IDs that are missing from the active corpus.",
                        "details": {"missing_gold_ids": missing_gold_ids},
                    }
                )
            if missing_required_ids:
                query_issues.append(
                    {
                        "level": "error",
                        "code": "required_gold_missing_in_corpus",
                        "message": "Ratified query has missing required gold IDs in the active corpus.",
                        "details": {"missing_required_gold_ids": missing_required_ids},
                    }
                )

        if query_issues:
            invalid_ratified_query_ids.append(query_id)
            for issue in query_issues:
                issues.append(
                    {
                        "query_id": query_id,
                        "benchmark_track": track,
                        "evidence_scope": evidence_scope,
                        **issue,
                    }
                )
        elif track == TRACK_RATIFIED_CORE:
            clean_query_ids.append(query_id)

        per_query.append(
            {
                "query_id": query_id,
                "benchmark_track": track,
                "evidence_scope": evidence_scope,
                "status": str(query.get("_status") or ""),
                "required_gold_count": len(required_gold),
                "required_anchor_count": logical_required_count,
                "supporting_gold_count": len(supporting_gold),
                "missing_gold_ids": missing_gold_ids,
                "issue_codes": [issue["code"] for issue in query_issues],
            }
        )

    return {
        "version": "retrieval_lab_ratification_v1",
        "query_count": len(queries),
        "track_counts": dict(track_counts),
        "ratified_query_count": len(ratified_query_ids),
        "ratified_clean_query_count": len(clean_query_ids),
        "ratified_invalid_query_count": len({qid for qid in invalid_ratified_query_ids if qid}),
        "ratified_query_ids": ratified_query_ids,
        "clean_query_ids": clean_query_ids,
        "invalid_ratified_query_ids": sorted({qid for qid in invalid_ratified_query_ids if qid}),
        "issues": issues,
        "per_query": per_query,
    }


def filter_queries_by_ids(
    queries: List[Dict[str, Any]],
    query_ids: Iterable[str],
) -> List[Dict[str, Any]]:
    allowed = {str(qid).strip() for qid in query_ids if str(qid).strip()}
    return [query for query in queries if str(query.get("id") or "") in allowed]


def compact_ratification_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "track_counts": dict(summary.get("track_counts") or {}),
        "ratified_query_count": int(summary.get("ratified_query_count", 0) or 0),
        "ratified_clean_query_count": int(summary.get("ratified_clean_query_count", 0) or 0),
        "ratified_invalid_query_count": int(summary.get("ratified_invalid_query_count", 0) or 0),
    }

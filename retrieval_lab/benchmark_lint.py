"""
Benchmark linting utilities for retrieval_lab query batches.

Goal: keep minimal-anchor benchmarks hygienic (small required_gold sets, no duplicates),
without blocking experimentation. Lints are warnings by default.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from retrieval_lab.gold_grounding import flatten_query_batches


def lint_flat_queries(flat_queries: List[Dict[str, Any]]) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []

    for q in flat_queries:
        qid = str(q.get("id", ""))
        source_path = str(q.get("_source_path", ""))

        required_gold = [str(x).strip() for x in (q.get("required_gold") or []) if str(x).strip()]
        supporting_gold = [str(x).strip() for x in (q.get("supporting_gold") or []) if str(x).strip()]
        legacy_gold = [str(x).strip() for x in (q.get("gold_unit_ids") or []) if str(x).strip()]
        gold_locations = q.get("gold_locations") or {}

        # "Claims to be grounded" means it has explicit gold annotation structure, not that
        # the harness might infer gold later via page-anchoring.
        claims_grounded = (
            ("required_gold" in q)
            or ("supporting_gold" in q)
            or bool(gold_locations)
        )
        if claims_grounded and not required_gold:
            issues.append(
                {
                    "level": "warn",
                    "code": "required_gold_empty",
                    "query_id": qid,
                    "source_path": source_path,
                    "message": "Query declares gold fields but required_gold is empty.",
                }
            )

        # Duplicate IDs across buckets.
        dup_required = [k for k, v in Counter(required_gold).items() if v > 1]
        dup_supporting = [k for k, v in Counter(supporting_gold).items() if v > 1]
        if dup_required or dup_supporting:
            issues.append(
                {
                    "level": "warn",
                    "code": "gold_duplicates",
                    "query_id": qid,
                    "source_path": source_path,
                    "message": "Duplicate gold IDs found in required/supporting lists.",
                    "details": {
                        "duplicates_required": dup_required,
                        "duplicates_supporting": dup_supporting,
                    },
                }
            )

        # Minimal-anchor hygiene heuristics.
        if len(required_gold) > 4:
            issues.append(
                {
                    "level": "warn",
                    "code": "required_gold_large",
                    "query_id": qid,
                    "source_path": source_path,
                    "message": f"required_gold size is {len(required_gold)}; consider splitting into micro-bundles.",
                    "details": {"required_gold_size": len(required_gold)},
                }
            )

        # Warn when the "all gold" set is implausibly large for a minimal-anchor suite.
        all_gold = list(dict.fromkeys(required_gold + supporting_gold + legacy_gold))
        if len(all_gold) > 6 and (required_gold or supporting_gold):
            issues.append(
                {
                    "level": "warn",
                    "code": "gold_total_large",
                    "query_id": qid,
                    "source_path": source_path,
                    "message": f"Total gold IDs (required+supporting+legacy) is {len(all_gold)}; consider splitting.",
                    "details": {
                        "total_gold_size": len(all_gold),
                        "required_gold_size": len(required_gold),
                        "supporting_gold_size": len(supporting_gold),
                        "legacy_gold_size": len(legacy_gold),
                    },
                }
            )

    by_code = Counter([i["code"] for i in issues])
    return {
        "n_queries": len(flat_queries),
        "n_issues": len(issues),
        "by_code": dict(by_code),
        "issues": issues,
    }


def lint_query_batches(batch_paths: List[str]) -> Dict[str, Any]:
    flat, _suites = flatten_query_batches(batch_paths)
    return lint_flat_queries(flat)


def worst_issue_level(lint_summary: Dict[str, Any]) -> Optional[str]:
    """Return 'error' if any error issues exist, else 'warn' if any warn issues exist, else None."""
    issues = lint_summary.get("issues") or []
    if not isinstance(issues, list):
        return None
    levels = {str(i.get("level", "")) for i in issues if isinstance(i, dict)}
    if "error" in levels:
        return "error"
    if "warn" in levels:
        return "warn"
    return None


from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List


def _summarize_candidates(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    relation_counts: Counter = Counter()
    resolution_buckets: Dict[str, Counter] = defaultdict(Counter)

    for candidate in candidates:
        relation = candidate.get("relation", "unknown")
        relation_counts[relation] += 1
        count = int(candidate.get("resolution_count", 0))
        if count == 0:
            resolution_buckets[relation]["zero"] += 1
        elif count == 1:
            resolution_buckets[relation]["unique"] += 1
        else:
            resolution_buckets[relation]["multi"] += 1

    resolution_summary = {}
    for relation, counts in resolution_buckets.items():
        total = sum(counts.values())
        unique_rate = round(counts.get("unique", 0) / total, 4) if total else 0.0
        resolution_summary[relation] = {
            "total": total,
            "unique": counts.get("unique", 0),
            "zero": counts.get("zero", 0),
            "multi": counts.get("multi", 0),
            "unique_rate": unique_rate,
        }

    return {
        "total_candidates": len(candidates),
        "relation_counts": dict(relation_counts),
        "resolution_summary": resolution_summary,
    }


def _print_summary(doc_id: str, summary: Dict[str, Any], keyword_counts: Counter) -> None:
    print(f"\n{doc_id}")
    print(f"  candidates: {summary.get('total_candidates', 0)}")
    for relation, count in sorted(summary.get("relation_counts", {}).items()):
        stats = summary.get("resolution_summary", {}).get(relation, {})
        print(
            "  - "
            f"{relation}: {count} "
            f"(unique={stats.get('unique', 0)}, "
            f"zero={stats.get('zero', 0)}, "
            f"multi={stats.get('multi', 0)}, "
            f"unique_rate={stats.get('unique_rate', 0)})"
        )

    if keyword_counts:
        print("  cue_keywords:")
        for keyword, count in keyword_counts.most_common():
            print(f"    - {keyword.strip()}: {count}")

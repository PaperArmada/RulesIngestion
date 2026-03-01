#!/usr/bin/env python3
"""
Cite gold from retrieval results: for each query, find retrieved chunks whose text
overlaps expected_answer_summary (Jaccard >= threshold) and write them as required_gold
and gold_unit_ids back into the benchmark JSON.

Usage:
  uv run python scripts/cite_gold_from_retrieval.py \\
    --benchmark evals/retrieval/StarFinderPlayerCore/starfinder_player_core_atomic_rules_benchmark.json \\
    --retrieved out/retrieval_lab/experiments/starfinder_atomic_rules_cite_run_20260228_045119/retrieved_chunks.json \\
    [--model all-mpnet-base-v2] [--threshold 0.15]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def jaccard_tokens(a: str, b: str) -> float:
    if not (a and a.strip()) or not (b and b.strip()):
        return 0.0
    ta = set(a.lower().split())
    tb = set(b.lower().split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def main() -> None:
    ap = argparse.ArgumentParser(description="Cite gold from retrieval results into benchmark JSON")
    ap.add_argument("--benchmark", required=True, help="Path to benchmark JSON (queries + metadata)")
    ap.add_argument("--retrieved", required=True, help="Path to retrieved_chunks.json (by_model -> model -> query_reviews)")
    ap.add_argument("--model", default="all-mpnet-base-v2", help="Model key in by_model to use")
    ap.add_argument("--threshold", type=float, default=0.15, help="Jaccard threshold for chunk ~ expected_answer_summary")
    ap.add_argument("--dry-run", action="store_true", help="Print matches only, do not write")
    args = ap.parse_args()

    benchmark_path = Path(args.benchmark)
    retrieved_path = Path(args.retrieved)

    if not benchmark_path.exists():
        raise SystemExit(f"Benchmark not found: {benchmark_path}")
    if not retrieved_path.exists():
        raise SystemExit(f"Retrieved chunks not found: {retrieved_path}")

    data = json.loads(benchmark_path.read_text(encoding="utf-8"))
    retrieved_data = json.loads(retrieved_path.read_text(encoding="utf-8"))
    by_model = retrieved_data.get("by_model") or {}
    query_reviews = by_model.get(args.model)
    if not query_reviews:
        raise SystemExit(f"No query reviews for model {args.model!r}. Keys: {list(by_model.keys())}")

    # query_id -> list of {query_id, retrieved: [{rank, chunk_id, score, text}]}
    reviews_by_id = {r["query_id"]: r for r in query_reviews}

    queries = data.get("queries") or []
    updated = 0
    for q in queries:
        qid = q.get("id", "")
        summary = (q.get("expected_answer_summary") or q.get("answer") or "").strip()
        if not summary:
            continue
        review = reviews_by_id.get(qid)
        if not review:
            continue
        retrieved = review.get("retrieved") or []
        matched = []
        for item in retrieved:
            chunk_id = item.get("chunk_id", "")
            text = (item.get("text") or "").strip()
            if not chunk_id:
                continue
            score = jaccard_tokens(summary, text)
            if score >= args.threshold:
                matched.append((item.get("rank", 999), chunk_id, round(score, 4)))

        if not matched:
            continue
        # Sort by rank so best rank is first
        matched.sort(key=lambda x: x[0])
        gold_ids = [x[1] for x in matched]
        # First as required_gold; rest as supporting (or all required for single-cite style)
        required = [gold_ids[0]] if gold_ids else []
        supporting = gold_ids[1:] if len(gold_ids) > 1 else []
        q["required_gold"] = required
        q["supporting_gold"] = supporting
        q["gold_unit_ids"] = list(dict.fromkeys(required + supporting))
        q["_required_gold"] = required
        q["_supporting_gold"] = supporting
        if not q.get("gold_locations"):
            q["gold_locations"] = {}
        updated += 1
        if args.dry_run:
            print(f"{qid}: rank1={matched[0][0]} score={matched[0][2]} required={required} supporting={supporting}")

    if args.dry_run:
        print(f"Would update {updated} queries (dry-run).")
        return

    benchmark_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Updated {updated} queries with cited gold in {benchmark_path}")


if __name__ == "__main__":
    main()

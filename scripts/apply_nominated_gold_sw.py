#!/usr/bin/env python3
"""
Apply reviewed gold from nominated_gold_per_query.json to swords_wizardry_benchmark.json.

Usage:
  uv run python scripts/apply_nominated_gold_sw.py

Reads evals/retrieval/SwordsandWizardy/nominated_gold_per_query.json and
evals/retrieval/SwordsandWizardy/swords_wizardry_benchmark.json. For each query,
copies gold_unit_ids from the nomination file into the benchmark. Writes the
benchmark back (preserves id, question, answer, source_page; updates gold_unit_ids).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

EVAL_DIR = Path("evals/retrieval/SwordsandWizardy")
NOMINATED_PATH = EVAL_DIR / "nominated_gold_per_query.json"
BENCHMARK_PATH = EVAL_DIR / "swords_wizardry_benchmark.json"


def main() -> None:
    if not NOMINATED_PATH.exists():
        print(f"Missing {NOMINATED_PATH}; run build_nominated_gold_sw.py first and fill gold_unit_ids.", file=sys.stderr)
        sys.exit(1)
    if not BENCHMARK_PATH.exists():
        print(f"Missing {BENCHMARK_PATH}", file=sys.stderr)
        sys.exit(1)

    nominated = json.loads(NOMINATED_PATH.read_text(encoding="utf-8"))
    benchmark = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))

    id_to_gold = {q["query_id"]: list(q.get("gold_unit_ids") or []) for q in nominated.get("queries", [])}
    updated = 0
    for item in benchmark:
        qid = item.get("id", "")
        if qid in id_to_gold:
            item["gold_unit_ids"] = id_to_gold[qid]
            if id_to_gold[qid]:
                updated += 1

    BENCHMARK_PATH.write_text(json.dumps(benchmark, indent=2), encoding="utf-8")
    print(f"Updated {BENCHMARK_PATH}: {updated} queries with non-empty gold_unit_ids.")


if __name__ == "__main__":
    main()

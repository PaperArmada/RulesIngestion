"""
Determinism replay check for retrieval_lab query enhancement.

This script is intentionally lightweight:
- loads a QueryExpansionProfile
- loads query batches
- runs enhancement twice (optionally with cache)
- asserts the expansion variants are identical

Usage:
  uv run python scripts/retrieval_lab_replay_check.py \
    --profile out/SwordsAndWizardry/qe_profiles/swcr_v1_qe_001.json \
    --batches out/SwordsAndWizardry/qe_bench_queries/swcr_min_anchor.json \
    --mode decompose \
    --use-cache
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from retrieval_lab.gold_grounding import flatten_query_batches
from retrieval_lab.query_enhancement.cache import QueryEnhancementCache
from retrieval_lab.query_enhancement.enhancer import enhance_queries
from retrieval_lab.query_enhancement.profile import load_profile, validate_profile


def _as_query_text(q: Dict[str, Any]) -> str:
    return str(q.get("question") or q.get("expected_answer_summary") or "").strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="Retrieval Lab: QE determinism replay check")
    ap.add_argument("--profile", required=True, help="Path to QueryExpansionProfile JSON")
    ap.add_argument("--batches", nargs="+", required=True, help="Query batch JSON files")
    ap.add_argument("--mode", default="dict", choices=["none", "dict", "llm", "llm+dict", "decompose"])
    ap.add_argument("--use-cache", action="store_true", help="Enable disk cache (uses profile cache_dir)")
    args = ap.parse_args()

    profile = load_profile(args.profile)
    errs = validate_profile(profile)
    if errs:
        raise SystemExit(f"Profile validation errors: {errs}")

    flat, _ = flatten_query_batches(args.batches)
    queries = [_as_query_text(q) for q in flat if _as_query_text(q)]
    if not queries:
        print("No queries found in batches.", file=sys.stderr)
        return 2

    cache = None
    if args.use_cache:
        cache = QueryEnhancementCache(profile.cache.cache_dir, enabled=profile.cache.enabled)

    r1 = enhance_queries(queries, profile, mode=args.mode, cache=cache)
    r2 = enhance_queries(queries, profile, mode=args.mode, cache=cache)

    if len(r1) != len(r2):
        print(f"Mismatch: group count {len(r1)} != {len(r2)}", file=sys.stderr)
        return 1

    for i in range(len(r1)):
        g1 = r1[i]
        g2 = r2[i]
        if json.dumps(g1, sort_keys=True) != json.dumps(g2, sort_keys=True):
            print(f"Mismatch at query index {i}", file=sys.stderr)
            print("g1:", json.dumps(g1, indent=2, sort_keys=True), file=sys.stderr)
            print("g2:", json.dumps(g2, indent=2, sort_keys=True), file=sys.stderr)
            return 1

    print(f"OK: determinism verified for {len(queries)} queries (mode={args.mode}, cache={'on' if cache else 'off'}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


"""Build candidate pools for an entire benchmark, ready for LLM-as-judge labeling.

Usage:
  uv run python -m tinker.scripts.build_candidate_pool \\
      --benchmark evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_atomic_rules_benchmark.v3_swcr_merged2000_min100.json \\
      --corpus-dir out/tinker/swcr \\
      --substrate-dir out/swcr \\
      --document-id Swords_Wizardry \\
      --out out/tinker/swcr/gold_candidates.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker.cache import TinkerCache  # noqa: E402
from tinker.eval.candidate_pool import build_pools_for_benchmark  # noqa: E402
from tinker.retrieve.dense import DenseIndex  # noqa: E402
from tinker.retrieve.sparse import SparseIndex  # noqa: E402
from tinker.substrate import load_corpus  # noqa: E402


def _load_benchmark_queries(path: Path) -> list[dict]:
    raw = json.loads(path.read_text())
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return list(raw.get("queries") or raw.get("benchmark") or [])
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Build per-query candidate pools.")
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--substrate-dir", type=Path, required=True)
    parser.add_argument("--document-id", type=str, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--top-per-strategy", type=int, default=30)
    parser.add_argument(
        "--no-intent-bearing",
        action="store_true",
        help="Skip the intent-bearing/HyDE strategy (saves ~10 s per query).",
    )
    args = parser.parse_args()

    queries = _load_benchmark_queries(args.benchmark)
    if not queries:
        print("ERROR: no queries found in benchmark", file=sys.stderr)
        return 2

    units = load_corpus(args.substrate_dir, args.document_id)
    unit_text_by_id = {u.id: u.text for u in units}
    dense = DenseIndex.load(args.corpus_dir / "embeddings")
    sparse = SparseIndex.load(args.corpus_dir / "bm25_index.pkl")
    portrait = json.loads(
        (args.corpus_dir / "corpus_self_portrait.json").read_text()
    )
    cache = TinkerCache(args.corpus_dir / "caches" / "llm_cache.sqlite")

    pools = build_pools_for_benchmark(
        queries,
        dense_index=dense,
        sparse_index=sparse,
        unit_text_by_id=unit_text_by_id,
        self_portrait=portrait,
        cache=cache,
        top_per_strategy=args.top_per_strategy,
        include_intent_bearing=not args.no_intent_bearing,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(pools, indent=2))
    print(f"Wrote {len(pools)} query pools to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

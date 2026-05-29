"""End-to-end eval: load benchmark + gold, run router and raw_dense, report.

Usage:
  uv run python -m tinker.scripts.run_eval \\
      --benchmark evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_atomic_rules_benchmark.v3_swcr_merged2000_min100.json \\
      --gold out/tinker/swcr/gold_labels.json \\
      --corpus-dir out/tinker/swcr \\
      --substrate-dir out/swcr \\
      --document-id Swords_Wizardry \\
      --out out/tinker/swcr/runs/<ts>/
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker.cache import TinkerCache  # noqa: E402
from tinker.eval.harness import eval_benchmark  # noqa: E402
from tinker.eval.report import (  # noqa: E402
    print_differences,
    print_latency,
    print_per_bucket,
    print_summary,
)
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
    parser = argparse.ArgumentParser(description="Run end-to-end retrieval eval.")
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--substrate-dir", type=Path, required=True)
    parser.add_argument("--document-id", type=str, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--mode",
        type=str,
        default="both",
        choices=("router", "raw_dense", "both"),
    )
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--candidate-pool", type=int, default=50)
    args = parser.parse_args()

    queries = _load_benchmark_queries(args.benchmark)
    if not queries:
        print("ERROR: no queries in benchmark", file=sys.stderr)
        return 2

    gold = json.loads(args.gold.read_text())
    units = load_corpus(args.substrate_dir, args.document_id)
    unit_text_by_id = {u.id: u.text for u in units}
    dense = DenseIndex.load(args.corpus_dir / "embeddings")
    sparse = SparseIndex.load(args.corpus_dir / "bm25_index.pkl")
    portrait = json.loads(
        (args.corpus_dir / "corpus_self_portrait.json").read_text()
    )
    cache = TinkerCache(args.corpus_dir / "caches" / "llm_cache.sqlite")

    modes = ("router", "raw_dense") if args.mode == "both" else (args.mode,)
    results = eval_benchmark(
        queries,
        gold,
        dense_index=dense,
        sparse_index=sparse,
        unit_text_by_id=unit_text_by_id,
        self_portrait=portrait,
        cache=cache,
        modes=modes,
        top_k=args.top_k,
        candidate_pool=args.candidate_pool,
    )

    print_summary(results)
    print_latency(results)
    if "router" in results and results["router"]:
        print_per_bucket(results["router"])
    if "router" in results and "raw_dense" in results:
        print_differences(results)

    args.out.mkdir(parents=True, exist_ok=True)
    out_json = args.out / "results.json"
    serializable = {
        m: [dataclasses.asdict(r) for r in items]
        for m, items in results.items()
    }
    out_json.write_text(json.dumps(serializable, indent=2))
    print(f"Wrote per-query results to {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

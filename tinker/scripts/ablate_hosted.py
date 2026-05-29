"""Ablation grid for the hosted (Gemini) backend.

Two knobs we suspect were biased by the local-hardware era:
  - hypothesis verbosity: capped (200 tok / 120 words, local-latency
    accommodation) vs uncapped (512 tok / 250 words).
  - thinking on the reasoning roles (q-ROFS classify + extract_intent):
    off vs dynamic.

2x2 grid = 4 router configs. raw_dense is LLM-invariant (no classify /
intent / hypothesize), so it runs once and is shared across configs.

The LLM cache is bypassed (cache=None): the classifier prompt is identical
whether thinking is on or off, so a shared cache would alias configs.
Calls are cheap on the paid tier; correctness beats reuse here.

Usage:
  TINKER_LLM_BACKEND=gemini uv run python -m tinker.scripts.ablate_hosted \
      --benchmark <atomic_benchmark.json> \
      --gold out/tinker/swcr/gold_labels.json \
      --corpus-dir out/tinker/swcr \
      --substrate-dir out/swcr \
      --document-id Swords_Wizardry \
      --out out/tinker/swcr/runs/m5_gemini_ablation
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker.eval.harness import aggregate, eval_benchmark  # noqa: E402
from tinker.retrieve.dense import DenseIndex  # noqa: E402
from tinker.retrieve.sparse import SparseIndex  # noqa: E402
from tinker.runtime_config import CFG  # noqa: E402
from tinker.substrate import load_corpus  # noqa: E402


# (label, hypothesis_max_tokens, hypothesis_word_limit, think_classify, think_intent)
CONFIGS = [
    ("baseline_capped_nothink", 200, 120, False, False),
    ("uncapped_nothink", 512, 250, False, False),
    ("capped_think", 200, 120, True, True),
    ("uncapped_think", 512, 250, True, True),
]

HEADLINE_KEYS = [
    "mrr_required",
    "recall_at_1",
    "recall_at_5",
    "recall_at_10",
    "recall_at_20",
    "strict_required_at_10",
]


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _load_benchmark_queries(path: Path) -> list[dict]:
    raw = json.loads(path.read_text())
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return list(raw.get("queries") or raw.get("benchmark") or [])
    return []


def _router_latency_summary(per_query) -> dict[str, float]:
    totals = sorted(r.latency_ms.get("total_ms", 0.0) for r in per_query)
    if not totals:
        return {}
    n = len(totals)
    return {
        "p50_ms": totals[n // 2],
        "p95_ms": totals[min(n - 1, int(n * 0.95))],
        "max_ms": totals[-1],
        "mean_ms": sum(totals) / n,
    }


def _bucket_distribution(per_query) -> dict[str, int]:
    dist: dict[str, int] = {}
    for r in per_query:
        dist[r.chosen_bucket or "?"] = dist.get(r.chosen_bucket or "?", 0) + 1
    return dist


def main() -> int:
    parser = argparse.ArgumentParser(description="Hosted-backend ablation grid.")
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--substrate-dir", type=Path, required=True)
    parser.add_argument("--document-id", type=str, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--candidate-pool", type=int, default=50)
    parser.add_argument(
        "--limit", type=int, default=0,
        help="If >0, only run the first N queries (smoke test).",
    )
    args = parser.parse_args()

    queries = _load_benchmark_queries(args.benchmark)
    if not queries:
        print("ERROR: no queries in benchmark", file=sys.stderr)
        return 2
    if args.limit > 0:
        queries = queries[: args.limit]
        _log(f"LIMIT active: running first {len(queries)} queries only")
    gold = json.loads(args.gold.read_text())

    _log("loading substrate + indices (once)")
    units = load_corpus(args.substrate_dir, args.document_id)
    unit_text_by_id = {u.id: u.text for u in units}
    dense = DenseIndex.load(args.corpus_dir / "embeddings")
    sparse = SparseIndex.load(args.corpus_dir / "bm25_index.pkl")
    portrait = json.loads(
        (args.corpus_dir / "corpus_self_portrait.json").read_text()
    )

    args.out.mkdir(parents=True, exist_ok=True)

    common = dict(
        dense_index=dense,
        sparse_index=sparse,
        unit_text_by_id=unit_text_by_id,
        self_portrait=portrait,
        cache=None,  # bypass: thinking on/off shares prompt text
        top_k=args.top_k,
        candidate_pool=args.candidate_pool,
    )

    # raw_dense once (LLM-invariant).
    _log("=== raw_dense baseline (shared across configs) ===")
    rd_results = eval_benchmark(queries, gold, modes=("raw_dense",), **common)
    rd_agg = aggregate(rd_results["raw_dense"])

    summary: dict[str, dict] = {
        "raw_dense": {
            "aggregate": rd_agg,
            "latency": _router_latency_summary(rd_results["raw_dense"]),
        }
    }

    for label, hyp_tok, hyp_words, think_cls, think_int in CONFIGS:
        CFG.hypothesis_max_tokens = hyp_tok
        CFG.hypothesis_word_limit = hyp_words
        CFG.think_classify = think_cls
        CFG.think_intent = think_int
        _log(
            f"=== config: {label}  (hyp={hyp_tok}tok/{hyp_words}w, "
            f"think_classify={think_cls}, think_intent={think_int}) ==="
        )
        res = eval_benchmark(queries, gold, modes=("router",), **common)
        per_query = res["router"]
        agg = aggregate(per_query)
        summary[label] = {
            "config": {
                "hypothesis_max_tokens": hyp_tok,
                "hypothesis_word_limit": hyp_words,
                "think_classify": think_cls,
                "think_intent": think_int,
            },
            "aggregate": agg,
            "latency": _router_latency_summary(per_query),
            "bucket_distribution": _bucket_distribution(per_query),
            "multi_path_count": sum(1 for r in per_query if r.multi_path),
            "margins": sorted(
                round(r.margin, 3) for r in per_query if r.margin is not None
            ),
        }
        # Write per-query detail for this config.
        (args.out / f"{label}.json").write_text(
            json.dumps(
                [dataclasses.asdict(r) for r in per_query], indent=2
            )
        )

    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))

    # Comparison table.
    print("\n" + "=" * 100)
    print(f"{'config':<26s} " + " ".join(f"{k.replace('recall_at_','R@').replace('mrr_required','MRR').replace('strict_required_at_10','strictR@10'):>10s}" for k in HEADLINE_KEYS))
    print("-" * 100)
    rd = summary["raw_dense"]["aggregate"]
    print(f"{'raw_dense':<26s} " + " ".join(f"{rd.get(k,0):>10.3f}" for k in HEADLINE_KEYS))
    for label, *_ in CONFIGS:
        agg = summary[label]["aggregate"]
        lat = summary[label]["latency"]
        print(f"{label:<26s} " + " ".join(f"{agg.get(k,0):>10.3f}" for k in HEADLINE_KEYS)
              + f"   p50={lat.get('p50_ms',0)/1000:.1f}s mean={lat.get('mean_ms',0)/1000:.1f}s")
    print("=" * 100)
    for label, *_ in CONFIGS:
        s = summary[label]
        print(f"{label:<26s} buckets={s['bucket_distribution']} "
              f"multi_path={s['multi_path_count']}")
    print(f"\nWrote {args.out}/summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

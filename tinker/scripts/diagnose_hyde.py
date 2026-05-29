"""Diagnose WHY HyDE (intent_bearing) underperforms raw_dense.

Tests two hypotheses from the routing analysis:

  H1 (pool recall ceiling): the HyDE hypothesis determines the candidate
     pool; the reranker scores the original query and cannot recover
     passages the pool never surfaced. If true, the HyDE pool has lower
     recall@50 than the query pool, across the population.

  H2 (5e prior-contamination drift): the hypothesis is sampled from the
     LLM prior (dominated by D&D 5e, not SWCR), so it reads 5e-flavored
     and embeds away from the idiosyncratic SWCR passages. Inspected by
     printing the actual hypothesis next to a gold passage for the worst
     losers.

Population-level (every query that the no-think classifier routes through
HyDE), not a single probe. Runs with CFG defaults (capped, no-think) —
the canonical HyDE config and the best router config from the grid.

Usage:
  TINKER_LLM_BACKEND=gemini uv run python -m tinker.scripts.diagnose_hyde \
      --benchmark <atomic_benchmark.json> \
      --gold out/tinker/swcr/gold_labels.json \
      --corpus-dir out/tinker/swcr \
      --substrate-dir out/swcr \
      --document-id Swords_Wizardry \
      --out out/tinker/swcr/runs/hyde_diagnosis
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker.eval.harness import run_raw_dense_baseline  # noqa: E402
from tinker.retrieve.dense import DenseIndex  # noqa: E402
from tinker.retrieve.sparse import SparseIndex  # noqa: E402
from tinker.routing.intent_bearing import run_intent_bearing  # noqa: E402
from tinker.substrate import load_corpus  # noqa: E402

POOL = 50


def _load_queries(path: Path) -> list[dict]:
    raw = json.loads(path.read_text())
    if isinstance(raw, list):
        return raw
    return list(raw.get("queries") or raw.get("benchmark") or [])


def _gold_union(gold: dict, qid: str) -> set[str]:
    e = gold.get(qid) or {}
    return set(e.get("required") or []) | set(e.get("supporting") or [])


def _recall(pool_ids: list[str], gold: set[str]) -> float:
    if not gold:
        return 0.0
    return len(set(pool_ids[:POOL]) & gold) / len(gold)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--corpus-dir", type=Path, required=True)
    ap.add_argument("--substrate-dir", type=Path, required=True)
    ap.add_argument("--document-id", type=str, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    queries = _load_queries(args.benchmark)
    gold = json.loads(args.gold.read_text())
    units = load_corpus(args.substrate_dir, args.document_id)
    unit_text_by_id = {u.id: u.text for u in units}
    dense = DenseIndex.load(args.corpus_dir / "embeddings")
    sparse = SparseIndex.load(args.corpus_dir / "bm25_index.pkl")
    portrait = json.loads(
        (args.corpus_dir / "corpus_self_portrait.json").read_text()
    )

    rows = []
    for i, q in enumerate(queries):
        qid = q.get("id") or f"q{i}"
        question = q.get("question", "")
        g = _gold_union(gold, qid)
        if not g:
            continue

        # Query pool (raw_dense), rerank off -> raw dense top-50 ids.
        q_ids, _, _ = run_raw_dense_baseline(
            question, dense_index=dense, unit_text_by_id=unit_text_by_id,
            top_k=POOL, candidate_pool=POOL, rerank=False,
        )
        # HyDE pool: run intent_bearing, rerank off, top_k=POOL -> hypothesis dense top-50.
        r = run_intent_bearing(
            query=question, dense_index=dense, unit_text_by_id=unit_text_by_id,
            self_portrait=portrait, top_k=POOL, candidate_pool=POOL, rerank=False,
        )
        h_ids = [c["id"] for c in r.top_k]

        q_rec = _recall(q_ids, g)
        h_rec = _recall(h_ids, g)
        rows.append({
            "qid": qid,
            "question": question,
            "query_pool_recall50": q_rec,
            "hyde_pool_recall50": h_rec,
            "delta": h_rec - q_rec,
            "hypothesis": r.debug.get("hypothesis", ""),
            "intent": r.debug.get("intent", ""),
            "target_clusters": r.debug.get("target_clusters", []),
            "gold_unit_ids": sorted(g),
        })
        print(
            f"[{i+1}/{len(queries)}] {qid:42s} "
            f"query_pool={q_rec:.2f}  hyde_pool={h_rec:.2f}  delta={h_rec-q_rec:+.2f}",
            flush=True,
        )

    n = len(rows)
    q_mean = sum(r["query_pool_recall50"] for r in rows) / n
    h_mean = sum(r["hyde_pool_recall50"] for r in rows) / n
    hyde_wins = sum(1 for r in rows if r["delta"] > 0)
    hyde_loses = sum(1 for r in rows if r["delta"] < 0)
    ties = sum(1 for r in rows if r["delta"] == 0)

    print("\n" + "=" * 78)
    print("H1: candidate-pool recall@50 (the recall CEILING the reranker works within)")
    print("-" * 78)
    print(f"  query pool (raw_dense) mean recall@50 : {q_mean:.3f}")
    print(f"  HyDE  pool (hypothesis) mean recall@50: {h_mean:.3f}")
    print(f"  HyDE pool better on {hyde_wins}/{n}, worse on {hyde_loses}/{n}, tie on {ties}/{n}")
    print("=" * 78)

    worst = sorted(rows, key=lambda r: r["delta"])[:3]
    print("\nH2: 3 worst HyDE losers — hypothesis text vs a gold passage")
    print("=" * 78)
    for r in worst:
        print(f"\n### {r['qid']}  (delta={r['delta']:+.2f}, "
              f"query_pool={r['query_pool_recall50']:.2f} hyde_pool={r['hyde_pool_recall50']:.2f})")
        print(f"QUESTION: {r['question']}")
        print(f"INTENT (model): {r['intent']}")
        print(f"TARGET CLUSTERS: {r['target_clusters']}")
        print(f"\nHYPOTHESIS (what we embedded instead of the query):\n{r['hypothesis']}")
        gold_id = r["gold_unit_ids"][0] if r["gold_unit_ids"] else None
        gold_txt = unit_text_by_id.get(gold_id, "(not found)") if gold_id else "(no gold)"
        print(f"\nGOLD PASSAGE [{gold_id}] (what we needed to retrieve):\n{gold_txt[:700]}")
        print("-" * 78)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "hyde_diagnosis.json").write_text(json.dumps({
        "summary": {
            "n": n,
            "query_pool_mean_recall50": q_mean,
            "hyde_pool_mean_recall50": h_mean,
            "hyde_pool_better": hyde_wins,
            "hyde_pool_worse": hyde_loses,
            "ties": ties,
        },
        "per_query": rows,
    }, indent=2))
    print(f"\nWrote {args.out}/hyde_diagnosis.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

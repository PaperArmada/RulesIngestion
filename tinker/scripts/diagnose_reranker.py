"""Dissect the reranker bottleneck.

raw_dense pool recall@50 ~0.993 but final recall@10 ~0.589 — the gold is in the
pool, and something between the pool and the top-10 drops it. The pipeline is:
dense top-50 -> cross-encoder rerank -> top-K. So either dense ranking within the
pool is poor, or the reranker actively demotes gold. This separates the two:

For each query, within the SAME dense top-50 pool, compute recall@10 under
  (a) dense ordering   (sort by dense score)
  (b) rerank ordering  (sort by cross-encoder score)
and the per-gold rank shift (dense rank -> rerank rank). If rerank recall < dense
recall, the reranker is actively hurting; if both are ~equal and low, the pool
ordering is the issue, not the reranker specifically.

Usage:
  uv run python -m tinker.scripts.diagnose_reranker \
      --benchmark <atomic_benchmark.json> --gold out/tinker/swcr/gold_labels.json \
      --corpus-dir out/tinker/swcr --substrate-dir out/swcr --document-id Swords_Wizardry \
      --out out/tinker/swcr/runs/reranker_diag
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker import llm as tinker_llm  # noqa: E402
from tinker import rerank as tinker_rerank  # noqa: E402
from tinker.retrieve.dense import DenseIndex  # noqa: E402
from tinker.substrate import load_corpus  # noqa: E402

POOL = 50


def _load_queries(path: Path) -> list[dict]:
    raw = json.loads(path.read_text())
    return raw if isinstance(raw, list) else list(raw.get("queries") or raw.get("benchmark") or [])


def _gold_union(gold: dict, qid: str) -> set[str]:
    e = gold.get(qid) or {}
    return set(e.get("required") or []) | set(e.get("supporting") or [])


def _recall_at(ranked_ids: list[str], g: set[str], k: int) -> float:
    return len(set(ranked_ids[:k]) & g) / len(g) if g else 0.0


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

    tinker_llm.unload_workhorse()
    rows = []
    agg = {"dense_r1": 0, "dense_r10": 0, "rr_r1": 0, "rr_r10": 0, "pool": 0, "n": 0}
    for i, q in enumerate(queries):
        qid = q.get("id") or f"q{i}"
        question = q.get("question", "")
        g = _gold_union(gold, qid)
        if not g:
            continue
        qvec = tinker_llm.embed([question])[0]
        ids, scores = dense.search(qvec, top_k=POOL)
        ids = list(ids)
        dense_order = ids  # already sorted by dense score desc
        cands = [{"id": uid, "text": unit_text_by_id.get(uid, "")} for uid in ids]
        tinker_llm.unload_ollama_model(tinker_llm.MODEL_EMBEDDER)
        reranked = tinker_rerank.rerank(question, cands, top_k=POOL)
        rr_order = [c["id"] for c in reranked]

        # per-gold rank shift (1-based; None if not in pool)
        shifts = []
        for uid in g:
            dr = dense_order.index(uid) + 1 if uid in dense_order else None
            rr = rr_order.index(uid) + 1 if uid in rr_order else None
            shifts.append({"unit": uid[:10], "dense_rank": dr, "rerank_rank": rr})

        row = {
            "qid": qid, "gold_size": len(g),
            "pool_recall50": _recall_at(dense_order, g, 50),
            "dense_recall10": _recall_at(dense_order, g, 10),
            "rerank_recall10": _recall_at(rr_order, g, 10),
            "dense_recall1": _recall_at(dense_order, g, 1),
            "rerank_recall1": _recall_at(rr_order, g, 1),
            "shifts": sorted(shifts, key=lambda s: (s["rerank_rank"] or 999)),
            # distractors the reranker put in top-5 that aren't gold
            "top5_nongold": [c["id"][:10] for c in reranked[:5] if c["id"] not in g],
        }
        rows.append(row)
        agg["dense_r10"] += row["dense_recall10"]; agg["rr_r10"] += row["rerank_recall10"]
        agg["dense_r1"] += row["dense_recall1"]; agg["rr_r1"] += row["rerank_recall1"]
        agg["pool"] += row["pool_recall50"]; agg["n"] += 1
        print(f"  {qid:<42s} pool={row['pool_recall50']:.2f} "
              f"dense@10={row['dense_recall10']:.2f} rerank@10={row['rerank_recall10']:.2f}", flush=True)

    n = agg["n"]
    print("\n" + "=" * 72)
    print(f"RERANKER DISSECTION (n={n}, within the same dense top-{POOL} pool)")
    print("-" * 72)
    print(f"  pool recall@50           : {agg['pool']/n:.3f}")
    print(f"  recall@10  dense ordering : {agg['dense_r10']/n:.3f}")
    print(f"  recall@10  rerank ordering: {agg['rr_r10']/n:.3f}   <- the pipeline uses this")
    print(f"  recall@1   dense ordering : {agg['dense_r1']/n:.3f}")
    print(f"  recall@1   rerank ordering: {agg['rr_r1']/n:.3f}")
    print("=" * 72)
    helped = sum(1 for r in rows if r["rerank_recall10"] > r["dense_recall10"])
    hurt = sum(1 for r in rows if r["rerank_recall10"] < r["dense_recall10"])
    print(f"  rerank vs dense @10: helped {helped} queries, hurt {hurt}, tied {n-helped-hurt}")

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "reranker_diag.json").write_text(json.dumps({"agg": agg, "per_query": rows}, indent=2))
    print(f"Wrote {args.out}/reranker_diag.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

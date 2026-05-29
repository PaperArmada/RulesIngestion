"""Single-query CLI: classify, route, retrieve, print evidence + timings.

Usage:
  uv run python -m tinker.scripts.run_query \\
      --corpus-dir out/tinker/swcr \\
      --substrate-dir out/swcr \\
      --document-id Swords_Wizardry \\
      --query "What does the Healing spell do?"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker.cache import TinkerCache  # noqa: E402
from tinker.retrieve.dense import DenseIndex  # noqa: E402
from tinker.retrieve.sparse import SparseIndex  # noqa: E402
from tinker.routing.dispatch import route_and_retrieve  # noqa: E402
from tinker.substrate import load_corpus  # noqa: E402


def _ensure_sparse_index(
    units, sparse_path: Path
) -> SparseIndex:
    if sparse_path.is_file():
        return SparseIndex.load(sparse_path)
    print(f"Building BM25 index (no cache at {sparse_path})...", flush=True)
    t0 = time.perf_counter()
    ids = [u.id for u in units]
    texts = [u.text for u in units]
    idx = SparseIndex.from_corpus(ids, texts)
    idx.save(sparse_path)
    print(f"  built in {time.perf_counter() - t0:.1f}s; saved to {sparse_path}", flush=True)
    return idx


def main() -> int:
    parser = argparse.ArgumentParser(description="Route a single query end-to-end.")
    parser.add_argument("--corpus-dir", type=Path, required=True,
                        help="Tinker corpus dir (must contain embeddings/ and "
                             "corpus_self_portrait.json).")
    parser.add_argument("--substrate-dir", type=Path, required=True,
                        help="Stage B output dir (e.g. out/swcr).")
    parser.add_argument("--document-id", type=str, required=True)
    parser.add_argument("--query", type=str, required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--candidate-pool", type=int, default=50)
    parser.add_argument(
        "--no-qrofs",
        action="store_true",
        help="Use single-label classifier instead of q-ROFS.",
    )
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="Skip cross-encoder reranking.",
    )
    parser.add_argument(
        "--ambiguity-margin",
        type=float,
        default=0.15,
        help="q-ROFS margin threshold below which we run multi-path.",
    )
    args = parser.parse_args()

    print(f"Query: {args.query}", flush=True)
    print(f"Corpus dir: {args.corpus_dir}", flush=True)

    print("Loading substrate + recipe...", flush=True)
    units = load_corpus(args.substrate_dir, args.document_id)
    unit_text_by_id = {u.id: u.text for u in units}
    print(f"  units after recipe: {len(units)}", flush=True)

    print("Loading dense index...", flush=True)
    dense = DenseIndex.load(args.corpus_dir / "embeddings")
    print(f"  dense: {dense.dim}-dim x {len(dense.unit_ids)} vectors "
          f"(model={dense.model})", flush=True)

    sparse = _ensure_sparse_index(units, args.corpus_dir / "bm25_index.pkl")

    portrait = json.loads(
        (args.corpus_dir / "corpus_self_portrait.json").read_text()
    )

    cache = TinkerCache(args.corpus_dir / "caches" / "llm_cache.sqlite")

    print("Routing...", flush=True)
    result = route_and_retrieve(
        query=args.query,
        dense_index=dense,
        sparse_index=sparse,
        unit_text_by_id=unit_text_by_id,
        self_portrait=portrait,
        cache=cache,
        top_k=args.top_k,
        candidate_pool=args.candidate_pool,
        ambiguity_margin=args.ambiguity_margin,
        use_qrofs=not args.no_qrofs,
        rerank=not args.no_rerank,
    )

    print()
    print("=" * 80)
    print(f"Chosen bucket: {result.chosen_bucket} (margin={result.margin:+.2f})")
    if result.multi_path:
        print(f"Multi-path: {result.second_bucket} also invoked (margin below "
              f"{args.ambiguity_margin})")
    print(f"Classifier latency: {result.classifier_latency_ms:.0f} ms")
    for i, r in enumerate(result.routes):
        timing = " ".join(f"{k}={int(v)}ms" for k, v in r.latency_ms_breakdown.items())
        print(f"  route {i+1} ({r.bucket}): pool={r.pool_size}  {timing}")
        if r.debug.get("hypothesis"):
            print(f"    hypothesis (truncated): "
                  f"{r.debug['hypothesis'][:200].replace(chr(10), ' ')}...")
        if r.debug.get("target_clusters"):
            print(f"    target_clusters: {r.debug['target_clusters']}")
    print(f"Total latency: {result.total_latency_ms:.0f} ms")
    print()

    print(f"Top {len(result.merged_top_k)} evidence (merged):")
    for i, c in enumerate(result.merged_top_k):
        rerank_score = c.get("rerank_score")
        fused = c.get("fused_score")
        dense_s = c.get("dense_score")
        score_bits = []
        if rerank_score is not None:
            score_bits.append(f"rr={rerank_score:.3f}")
        if fused is not None:
            score_bits.append(f"fused={fused:.3f}")
        if dense_s is not None:
            score_bits.append(f"dense={dense_s:.3f}")
        text_preview = (c.get("text") or "").replace("\n", " ")[:200]
        print(f"  [{i+1}] id={c['id'][:12]}...  {' '.join(score_bits)}")
        print(f"      {text_preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

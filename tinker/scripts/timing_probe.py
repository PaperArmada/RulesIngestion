"""Single-query latency probe.

Warms every model in the dispatch path once, then runs `route_and_retrieve`
and `run_raw_dense_baseline` on a chosen query and prints the per-stage
breakdown. This is the experiment that tells us where the ~100 s/query
in the full eval is actually being spent, with models already warm so
first-load cost is not confounded with steady-state cost.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker import llm as tinker_llm  # noqa: E402
from tinker import rerank as tinker_rerank  # noqa: E402
from tinker.cache import TinkerCache  # noqa: E402
from tinker.eval.harness import run_raw_dense_baseline  # noqa: E402
from tinker.retrieve.dense import DenseIndex  # noqa: E402
from tinker.retrieve.sparse import SparseIndex  # noqa: E402
from tinker.routing.dispatch import route_and_retrieve  # noqa: E402
from tinker.substrate import load_corpus  # noqa: E402


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main() -> int:
    # Query selected because in the M5 eval it consistently routes to
    # intent_bearing_distributed as the chosen bucket, so the probe
    # actually exercises extract_intent + hypothesize + embed_hypothesis.
    query = (
        "What are the roles at the table (players vs GM/referee/judge/MC), "
        "and what decisions does each role control?"
    )

    _log("loading substrate + indices")
    units = load_corpus("out/swcr", "Swords_Wizardry")
    unit_text_by_id = {u.id: u.text for u in units}
    dense = DenseIndex.load(Path("out/tinker/swcr/embeddings"))
    sparse = SparseIndex.load(Path("out/tinker/swcr/bm25_index.pkl"))
    portrait = json.loads(
        Path("out/tinker/swcr/corpus_self_portrait.json").read_text()
    )
    cache = TinkerCache(Path("out/tinker/swcr/caches/llm_cache.sqlite"))

    _log("WARMUP: ollama classifier (qwen3:4b)")
    t0 = time.perf_counter()
    _ = tinker_llm.classify(
        "warmup", "test", ["entity_anchored_single"]
    )
    _log(f"  classifier warm: {(time.perf_counter()-t0)*1000:.0f} ms")

    _log("WARMUP: ollama workhorse (qwen3:14b)")
    t0 = time.perf_counter()
    _ = tinker_llm.extract_intent("warmup", "cluster_0: test")
    _log(f"  workhorse warm:  {(time.perf_counter()-t0)*1000:.0f} ms")

    _log("WARMUP: embedder")
    t0 = time.perf_counter()
    tinker_llm.embed(["warmup query"])
    _log(f"  embedder warm:   {(time.perf_counter()-t0)*1000:.0f} ms")

    _log("WARMUP: cross-encoder reranker")
    t0 = time.perf_counter()
    tinker_rerank.load_reranker()
    tinker_rerank.rerank("warmup", [{"id": "x", "text": "test text"}], top_k=1)
    _log(f"  reranker warm:   {(time.perf_counter()-t0)*1000:.0f} ms")

    print()
    _log("=== EXPERIMENT 1: route_and_retrieve (router mode) ===")
    t0 = time.perf_counter()
    r = route_and_retrieve(
        query=query,
        dense_index=dense,
        sparse_index=sparse,
        unit_text_by_id=unit_text_by_id,
        self_portrait=portrait,
        cache=cache,
        top_k=20,
        candidate_pool=50,
    )
    router_total = (time.perf_counter() - t0) * 1000
    _log(f"router TOTAL:      {router_total:.0f} ms  (top_k_returned={len(r.merged_top_k)})")
    _log(f"  classifier_ms:   {r.classifier_latency_ms:.0f}  -> bucket={r.chosen_bucket} margin={r.margin:+.2f}")
    for i, route in enumerate(r.routes):
        _log(f"  route[{i}] {route.bucket}  pool={route.pool_size}")
        for k, v in route.latency_ms_breakdown.items():
            _log(f"    {k:<32s} {v:>8.0f} ms")
        if route.debug.get("hypothesis"):
            _log(f"    hypothesis_chars: {len(route.debug['hypothesis'])}")

    print()
    _log("=== EXPERIMENT 2: run_raw_dense_baseline ===")
    t0 = time.perf_counter()
    ids, scores, timings = run_raw_dense_baseline(
        query,
        dense_index=dense,
        unit_text_by_id=unit_text_by_id,
        top_k=20,
        candidate_pool=50,
    )
    raw_total = (time.perf_counter() - t0) * 1000
    _log(f"raw_dense TOTAL:   {raw_total:.0f} ms  (top_k_returned={len(ids)})")
    for k, v in timings.items():
        _log(f"    {k:<32s} {v:>8.0f} ms")

    print()
    _log("=== summary ===")
    sum_router_phases = sum(
        v for route in r.routes for v in route.latency_ms_breakdown.values()
    ) + r.classifier_latency_ms
    _log(
        f"router phases summed: {sum_router_phases:.0f} ms  "
        f"vs outer total {router_total:.0f} ms  "
        f"(gap={router_total - sum_router_phases:.0f} ms)"
    )
    _log(
        f"per-query (router + raw_dense): {router_total + raw_total:.0f} ms"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

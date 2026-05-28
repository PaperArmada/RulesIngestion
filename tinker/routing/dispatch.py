"""q-ROFS-driven routing dispatcher.

Decision tree (margin = chosen_mu - second_mu):

  margin >= AMBIGUITY_MARGIN
      -> single path: chosen bucket
  margin <  AMBIGUITY_MARGIN
      -> multi-path: run both chosen and second_bucket, merge candidate
         pools, rerank jointly

Buckets we haven't implemented yet (enumeration, structural, cross_ref,
example_based, entity_anchored_composite) fall back to entity_anchored.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from tinker import llm as tinker_llm
from tinker.cache import TinkerCache
from tinker.retrieve.dense import DenseIndex
from tinker.retrieve.sparse import SparseIndex
from tinker.rerank import rerank as cross_encoder_rerank
from tinker.routing import classifier as cls
from tinker.routing.entity_anchored import RouteResult, run_entity_anchored
from tinker.routing.intent_bearing import run_intent_bearing


AMBIGUITY_MARGIN_DEFAULT = 0.15


_IMPLEMENTED_BUCKETS = {"entity_anchored_single", "intent_bearing_distributed"}


def _bucket_to_runner(bucket: str) -> str:
    """Map a bucket id to which runner actually executes it.

    Unimplemented buckets fall back to entity_anchored_single with a
    `notimplemented_fallback` flag in the result debug.
    """
    if bucket in _IMPLEMENTED_BUCKETS:
        return bucket
    return "entity_anchored_single"


@dataclass(frozen=True)
class DispatchResult:
    query: str
    chosen_bucket: str
    second_bucket: str
    margin: float
    multi_path: bool
    routes: list[RouteResult]
    merged_top_k: list[dict[str, Any]]
    classifier_latency_ms: float
    total_latency_ms: float
    qrofs_memberships: dict[str, dict[str, float]] = field(default_factory=dict)
    debug: dict[str, Any] = field(default_factory=dict)


def _merge_candidate_pools(
    routes: list[RouteResult], top_k: int, query: str
) -> list[dict[str, Any]]:
    """Concatenate candidate pools across routes (dedup by id), then rerank.

    Score field used for rerank is the cross-encoder rerank_score on
    individual route outputs; we re-run a single cross-encoder pass on
    the merged pool to give honest unified ranking.
    """
    seen: dict[str, dict[str, Any]] = {}
    for r in routes:
        for c in r.top_k:
            if c["id"] not in seen:
                seen[c["id"]] = dict(c)
    if not seen:
        return []
    merged_candidates = list(seen.values())
    # rerank wraps retrieval_lab.reranker.rerank_candidates and adds rerank_score
    return cross_encoder_rerank(query, merged_candidates, top_k=top_k)


def route_and_retrieve(
    query: str,
    *,
    dense_index: DenseIndex,
    sparse_index: SparseIndex,
    unit_text_by_id: dict[str, str],
    self_portrait: dict[str, Any],
    cache: TinkerCache | None = None,
    classifier_model: str | None = None,
    top_k: int = 10,
    candidate_pool: int = 50,
    ambiguity_margin: float = AMBIGUITY_MARGIN_DEFAULT,
    use_qrofs: bool = True,
    rerank: bool = True,
    workhorse_model: str = tinker_llm.MODEL_WORKHORSE,
    embedder_model: str = tinker_llm.MODEL_EMBEDDER,
) -> DispatchResult:
    overall_t0 = time.perf_counter()

    # Build a small self-portrait summary for the classifier prompt.
    cluster_lines = [
        f"{c['cluster_id']}: {c.get('description', '')[:140]}"
        for c in self_portrait.get("clusters", {}).get("clusters", [])
    ]
    self_portrait_summary = "Cluster shapes:\n" + "\n".join(cluster_lines[:8])

    # Classify.
    classifier_kw = {
        "self_portrait_summary": self_portrait_summary,
        "cache": cache,
    }
    if classifier_model:
        classifier_kw["model"] = classifier_model

    if use_qrofs:
        qresult = cls.classify_query_qrofs(query, **classifier_kw)
        chosen = qresult.chosen_bucket
        second = qresult.second_bucket
        margin = qresult.margin
        classifier_latency = qresult.latency_ms
        memberships = {
            bid: {"mu": m.mu, "nu": m.nu, "pi": m.pi}
            for bid, m in qresult.memberships.items()
        }
    else:
        single = cls.classify_query(query, **classifier_kw)
        chosen = single.bucket
        second = single.bucket
        margin = 1.0
        classifier_latency = single.latency_ms
        memberships = {}

    chosen_runner = _bucket_to_runner(chosen)
    second_runner = _bucket_to_runner(second)
    multi_path = (
        use_qrofs
        and margin < ambiguity_margin
        and second_runner != chosen_runner
    )

    routes: list[RouteResult] = []
    runners_to_invoke = [chosen_runner]
    if multi_path:
        runners_to_invoke.append(second_runner)

    # VRAM-swap discipline #1: the entity-anchored runner only calls the
    # embedder, never the workhorse. If the workhorse (qwen3:14b, ~10 GB)
    # stays in VRAM after the classifier, Ollama has to swap it out to fit
    # the embedder (~6 GB) on the 12 GB card, adding tens of seconds. We
    # only need the workhorse when an intent-bearing route is in the plan
    # (its extract_intent + hypothesize steps use it).
    needs_workhorse = "intent_bearing_distributed" in runners_to_invoke
    if rerank and not needs_workhorse:
        tinker_llm.unload_ollama_model(workhorse_model)

    for runner_id in runners_to_invoke:
        if runner_id == "entity_anchored_single":
            r = run_entity_anchored(
                query=query,
                dense_index=dense_index,
                sparse_index=sparse_index,
                unit_text_by_id=unit_text_by_id,
                top_k=top_k,
                candidate_pool=candidate_pool,
                rerank=rerank,
            )
        elif runner_id == "intent_bearing_distributed":
            r = run_intent_bearing(
                query=query,
                dense_index=dense_index,
                unit_text_by_id=unit_text_by_id,
                self_portrait=self_portrait,
                top_k=top_k,
                candidate_pool=candidate_pool,
                rerank=rerank,
            )
        else:
            r = run_entity_anchored(
                query=query,
                dense_index=dense_index,
                sparse_index=sparse_index,
                unit_text_by_id=unit_text_by_id,
                top_k=top_k,
                candidate_pool=candidate_pool,
                rerank=rerank,
            )
        routes.append(r)

    # Merge across paths (or pass through if only one).
    if len(routes) == 1:
        merged = routes[0].top_k
    else:
        merged = _merge_candidate_pools(routes, top_k=top_k, query=query)

    total_latency = (time.perf_counter() - overall_t0) * 1000
    return DispatchResult(
        query=query,
        chosen_bucket=chosen,
        second_bucket=second,
        margin=margin,
        multi_path=multi_path,
        routes=routes,
        merged_top_k=merged,
        classifier_latency_ms=classifier_latency,
        total_latency_ms=total_latency,
        qrofs_memberships=memberships,
        debug={
            "chosen_runner": chosen_runner,
            "second_runner": second_runner,
            "runners_invoked": runners_to_invoke,
            "ambiguity_margin": ambiguity_margin,
            "notimplemented_fallback": chosen != chosen_runner,
        },
    )

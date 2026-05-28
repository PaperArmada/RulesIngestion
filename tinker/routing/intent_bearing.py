"""Intent-bearing distributed retrieval path (HyDE with shape prior).

Pipeline:
  1. extract_intent(query, structural_inventory)
       -> {intent: str, target_clusters: [cluster_id, ...], reason: str}
  2. Assemble target_shape_description from the named clusters'
     descriptions + the glossary terms that live in those clusters.
  3. hypothesize(query, target_shape_description, glossary_terms)
       -> hypothesis text (looks like the target shape)
  4. embed(hypothesis) -> vector
  5. Dense retrieve top-K against the corpus
  6. Optionally cross-encoder rerank
  7. Return RouteResult

Ordering matters for VRAM-swap discipline (qwen3:14b for steps 1+3 +
maybe synthesize, qwen3-embedding for step 4): both LLM calls are done
back-to-back BEFORE the embed call, so we eat at most one model swap per
query instead of two.
"""

from __future__ import annotations

import time
from typing import Any

from tinker import llm as tinker_llm
from tinker import rerank as tinker_rerank
from tinker.retrieve.dense import DenseIndex
from tinker.routing.entity_anchored import RouteResult


def _build_shape_prior(
    target_cluster_ids: list[str],
    clusters_block: list[dict[str, Any]],
    glossary_terms: list[dict[str, Any]],
    cluster_to_unit_ids: dict[str, set[str]],
    max_glossary_terms: int = 30,
) -> tuple[str, list[str]]:
    """Produce (target_shape_description, vocabulary) for the hypothesizer."""
    cluster_by_id = {str(c["cluster_id"]): c for c in clusters_block}

    descriptions: list[str] = []
    relevant_unit_ids: set[str] = set()
    for cid in target_cluster_ids:
        c = cluster_by_id.get(str(cid))
        if c is None:
            continue
        desc = c.get("description") or ""
        descriptions.append(f"Cluster {cid}: {desc}")
        relevant_unit_ids.update(cluster_to_unit_ids.get(str(cid), set()))

    shape_description = "\n".join(descriptions) if descriptions else (
        "rulebook entry (no specific shape inferred)"
    )

    # Pull glossary terms whose defining unit lies in one of the target clusters
    # first; fall back to top-N by global order if we run short.
    in_cluster_terms: list[str] = []
    other_terms: list[str] = []
    for t in glossary_terms:
        if t.get("source_unit_id") in relevant_unit_ids:
            in_cluster_terms.append(t["term"])
        else:
            other_terms.append(t["term"])
    vocab = (in_cluster_terms + other_terms)[:max_glossary_terms]
    return shape_description, vocab


def _build_cluster_unit_index(self_portrait: dict[str, Any]) -> dict[str, set[str]]:
    """Map cluster_id (str) -> set of member unit_ids."""
    out: dict[str, set[str]] = {}
    for c in self_portrait.get("clusters", {}).get("clusters", []):
        out[str(c["cluster_id"])] = set(c.get("member_unit_ids", []))
    return out


def run_intent_bearing(
    query: str,
    *,
    dense_index: DenseIndex,
    unit_text_by_id: dict[str, str],
    self_portrait: dict[str, Any],
    top_k: int = 10,
    candidate_pool: int = 50,
    rerank: bool = True,
) -> RouteResult:
    """Run the intent-bearing path end-to-end.

    The structural_inventory passed to extract_intent is a compact list of
    `cluster_id: description` pairs derived from the corpus self-portrait.
    """
    timing: dict[str, float] = {}
    clusters_block = self_portrait.get("clusters", {}).get("clusters", [])
    inventory_lines = [
        f"{c['cluster_id']}: {c.get('description', '')}" for c in clusters_block
    ]
    inventory = "\n".join(inventory_lines)

    # Step 1: extract intent + target clusters (qwen3:14b)
    t0 = time.perf_counter()
    intent_out = tinker_llm.extract_intent(query, inventory)
    timing["extract_intent_ms"] = (time.perf_counter() - t0) * 1000

    target_clusters_raw = intent_out.get("target_clusters") or []
    target_clusters = [str(c) for c in target_clusters_raw]
    intent_text = str(intent_out.get("intent", ""))

    # Step 2: build shape prior + glossary vocab
    glossary_terms = self_portrait.get("glossary", {}).get("terms", [])
    cluster_to_unit_ids = _build_cluster_unit_index(self_portrait)
    shape_description, vocab = _build_shape_prior(
        target_cluster_ids=target_clusters,
        clusters_block=clusters_block,
        glossary_terms=glossary_terms,
        cluster_to_unit_ids=cluster_to_unit_ids,
    )

    # Step 3: hypothesize (qwen3:14b — same model session, no swap)
    t0 = time.perf_counter()
    hypothesis = tinker_llm.hypothesize(
        query=query,
        target_shape_description=shape_description,
        glossary_terms=vocab,
    )
    timing["hypothesize_ms"] = (time.perf_counter() - t0) * 1000

    # Step 4: embed hypothesis (qwen3-embedding — first model swap)
    t0 = time.perf_counter()
    [hyp_vec] = tinker_llm.embed([hypothesis])
    timing["embed_hypothesis_ms"] = (time.perf_counter() - t0) * 1000

    # Step 5: dense retrieve
    t0 = time.perf_counter()
    dense_ids, dense_scores = dense_index.search(hyp_vec, top_k=candidate_pool)
    timing["dense_search_ms"] = (time.perf_counter() - t0) * 1000

    candidates = [
        {
            "id": uid,
            "text": unit_text_by_id.get(uid, ""),
            "dense_score": float(score),
        }
        for uid, score in zip(dense_ids, dense_scores)
    ]

    # Step 6: rerank
    if rerank and candidates:
        # See entity_anchored.run_entity_anchored for VRAM-swap rationale.
        t_unload = time.perf_counter()
        tinker_llm.unload_ollama_model(tinker_llm.MODEL_WORKHORSE)
        tinker_llm.unload_ollama_model(tinker_llm.MODEL_EMBEDDER)
        timing["ollama_unload_ms"] = (time.perf_counter() - t_unload) * 1000

        t0 = time.perf_counter()
        reranked = tinker_rerank.rerank(query, candidates, top_k=top_k)
        timing["rerank_ms"] = (time.perf_counter() - t0) * 1000
    else:
        reranked = candidates[:top_k]

    return RouteResult(
        bucket="intent_bearing_distributed",
        top_k=reranked,
        pool_size=len(candidates),
        latency_ms_breakdown=timing,
        debug={
            "intent": intent_text,
            "target_clusters": target_clusters,
            "shape_description": shape_description,
            "glossary_vocab_count": len(vocab),
            "hypothesis": hypothesis,
            "reranked": rerank,
            "candidate_pool": candidate_pool,
        },
    )

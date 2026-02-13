"""Shared post-retrieval expansion pipeline for BM25 and dense/hybrid paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from retrieval_lab.crossref_sidecar import expand_ranked_with_sidecar
from retrieval_lab.pairing_edges import expand_ranked_with_pairing_edges


@dataclass
class ExpansionConfig:
    crossref_sidecar_expand: bool = False
    crossref_expand_top_k: int = 10
    crossref_expand_per_hit: int = 2
    crossref_expand_total_cap: int = 20
    dependency_pairing_expand: bool = False
    dependency_pairing_emax: int = 6


def _build_pairing_instrumentation(
    grounded_queries: List[Dict[str, Any]],
    ranked_lists: List[List[str]],
    pairing_provenance: List[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    top_k_val = 10
    per_query = []
    for i, (q, prov) in enumerate(zip(grounded_queries, pairing_provenance)):
        gold_ids = set(q.get("gold_unit_ids") or [])
        top10 = set(ranked_lists[i][:top_k_val])
        triggers_fired = len(set(p.get("anchor_id") for p in prov))
        candidates_added = len(prov)
        gold_added = sum(1 for p in prov if p.get("chunk_id") in gold_ids)
        added_entered_top10 = sum(1 for p in prov if p.get("chunk_id") in top10)
        per_query.append(
            {
                "query_id": q.get("id", ""),
                "pairing_triggers_fired": triggers_fired,
                "candidates_added_by_pairing": candidates_added,
                "gold_added_by_pairing": gold_added,
                "added_entered_top10": added_entered_top10,
            }
        )
    return {
        "per_query": per_query,
        "summary": {
            "total_queries": len(grounded_queries),
            "total_triggers_fired": sum(p["pairing_triggers_fired"] for p in per_query),
            "total_candidates_added": sum(p["candidates_added_by_pairing"] for p in per_query),
            "total_gold_added": sum(p["gold_added_by_pairing"] for p in per_query),
            "total_added_entered_top10": sum(p["added_entered_top10"] for p in per_query),
        },
    }


def apply_post_retrieval_expansion(
    *,
    ranked_lists: List[List[str]],
    score_lists: List[List[float]],
    grounded_queries: List[Dict[str, Any]],
    crossref_sidecar: Dict[str, List[str]],
    pairing_edges: Dict[str, List[Tuple[str, str, str]]],
    config: ExpansionConfig,
) -> Tuple[List[List[str]], List[List[float]], Dict[str, Any] | None]:
    """Apply sidecar and pairing expansion in a deterministic shared path."""
    if config.crossref_sidecar_expand and crossref_sidecar:
        for i in range(len(grounded_queries)):
            ranked_lists[i], score_lists[i], _ = expand_ranked_with_sidecar(
                ranked_ids=ranked_lists[i],
                score_list=score_lists[i],
                sidecar=crossref_sidecar,
                expand_top_k=config.crossref_expand_top_k,
                expand_per_hit=config.crossref_expand_per_hit,
                total_cap=config.crossref_expand_total_cap,
            )

    if config.dependency_pairing_expand and pairing_edges:
        pairing_provenance: List[List[Dict[str, Any]]] = []
        for i in range(len(grounded_queries)):
            ranked_lists[i], score_lists[i], prov = expand_ranked_with_pairing_edges(
                ranked_ids=ranked_lists[i],
                score_list=score_lists[i],
                pairing_edges=pairing_edges,
                expand_top_k=config.crossref_expand_top_k,
                Emax=config.dependency_pairing_emax,
            )
            pairing_provenance.append(prov)
        return (
            ranked_lists,
            score_lists,
            _build_pairing_instrumentation(
                grounded_queries=grounded_queries,
                ranked_lists=ranked_lists,
                pairing_provenance=pairing_provenance,
            ),
        )

    return ranked_lists, score_lists, None

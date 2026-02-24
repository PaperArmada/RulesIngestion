"""
Forensics for gold_not_in_candidates: per-query bundles, miss classification, and heatmap stub.

Enables a tight loop: identify which queries missed gold-in-candidates, attach signals
(query/gold-unit shape, retrieval intermediates, derived diagnostics) so you can see
which lever to pull (QE, indexing, budget, unit-shape) without staring at raw rankings.

Contracts: EvidenceUnits remain the only admissible layer; this is retrieval-lab output only.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# Actionable miss buckets (map to levers).
MISS_BUCKET_INDEXING = "indexing_analyzer_failure"
MISS_BUCKET_VOCABULARY = "vocabulary_mismatch"
MISS_BUCKET_REPRESENTATION = "representation_mismatch"
MISS_BUCKET_UNIT_SHAPE = "unit_shape_failure"
MISS_BUCKET_BUDGET_FUSION = "candidate_budget_fusion_failure"
MISS_BUCKET_UNCLASSIFIED = "unclassified"

UNDERSIZED_TOKEN_THRESHOLD = 20
TOP_N_RETRIEVAL_INTERMEDIATES = 100


def _corpus_by_id(corpus: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {u["id"]: u for u in corpus if u.get("id")}


def _token_count(text: str) -> int:
    if not text or not isinstance(text, str):
        return 0
    return len(re.findall(r"\S+", text))


def _gold_unit_features(
    unit_id: str,
    corpus_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Extract features for one gold EvidenceUnit for forensics (shape, size, path)."""
    unit = corpus_by_id.get(unit_id) or {}
    text = unit.get("text") or ""
    structural_path = unit.get("structural_path")
    if structural_path is None:
        structural_path = []
    if not isinstance(structural_path, list):
        structural_path = [structural_path] if structural_path else []
    depth = len(structural_path)
    token_count = _token_count(text)
    unit_type = (unit.get("unit_type") or "prose").lower()
    undersized = token_count < UNDERSIZED_TOKEN_THRESHOLD
    orphan = depth == 0 and not (unit.get("structural_path"))
    table_or_list = unit_type in ("table", "list")
    return {
        "unit_id": unit_id,
        "unit_type": unit_type,
        "token_count": token_count,
        "structural_path_depth": depth,
        "anomaly_flags": {
            "undersized": undersized,
            "orphan": orphan,
            "table_or_list": table_or_list,
        },
        "shape_suspect": undersized or orphan or table_or_list,
    }


def _retrieval_intermediates_from_review(
    review: Dict[str, Any],
    top_n: int = TOP_N_RETRIEVAL_INTERMEDIATES,
) -> List[Dict[str, Any]]:
    """Top-N from the single channel we have (baseline / fused list)."""
    retrieved = review.get("retrieved") or []
    out = []
    for i, item in enumerate(retrieved[:top_n], start=1):
        out.append({
            "rank": i,
            "unit_id": item.get("chunk_id", ""),
            "score": item.get("score"),
        })
    return out


def _derived_diagnostics(
    bundle: Dict[str, Any],
    model_id: str,
    corpus_by_id: Dict[str, Dict[str, Any]],
    bm25_index: Any,
    corpus_ids: List[str],
) -> Dict[str, Any]:
    """Fill derived fields (oracle/budget require separate runs; placeholder here)."""
    gold_features = bundle.get("gold_unit_features") or []
    shape_suspect = any(
        (g.get("shape_suspect") for g in gold_features)
    )
    
    oracle_probe_hit = None
    if bm25_index is not None and corpus_ids:
        try:
            from retrieval_lab.sparse_retrieval import bm25_rank
            for gold in gold_features:
                unit_id = gold["unit_id"]
                unit = corpus_by_id.get(unit_id)
                if not unit:
                    continue
                
                text = unit.get("text", "")
                structural_path = unit.get("structural_path") or []
                if not isinstance(structural_path, list):
                    structural_path = [structural_path]
                
                words = text.split()
                probes = []
                # 1. Exact phrase (first 10 words)
                if words:
                    probes.append(" ".join(words[:10]))
                # 2. Key phrase (first 5 words)
                if len(words) > 5:
                    probes.append(" ".join(words[:5]))
                # 3. Heading
                if structural_path:
                    probes.append(" ".join(str(s) for s in structural_path[-2:]))
                
                if probes:
                    queries = [{"question": p} for p in probes]
                    ranked_lists, _ = bm25_rank(
                        bm25=bm25_index,
                        corpus_ids=corpus_ids,
                        queries=queries,
                        max_k=20,
                    )
                    if any(unit_id in r_list for r_list in ranked_lists):
                        oracle_probe_hit = True
                        break
            
            if oracle_probe_hit is None and gold_features:
                oracle_probe_hit = False
        except Exception:
            pass

    return {
        "oracle_probe_hit": oracle_probe_hit,
        "closest_channel": model_id,
        "budget_likely": None,
        "shape_suspect": shape_suspect,
    }


def classify_miss(bundle: Dict[str, Any]) -> str:
    """
    Assign one actionable bucket.
    """
    derived = bundle.get("derived") or {}
    
    if derived.get("shape_suspect"):
        return MISS_BUCKET_UNIT_SHAPE
        
    oracle_probe_hit = derived.get("oracle_probe_hit")
    if oracle_probe_hit is False:
        return MISS_BUCKET_INDEXING
    elif oracle_probe_hit is True:
        return MISS_BUCKET_VOCABULARY
        
    return MISS_BUCKET_UNCLASSIFIED


def build_forensics_bundles(
    per_query_list: List[Dict[str, Any]],
    query_reviews: List[Dict[str, Any]],
    grounded_queries: List[Dict[str, Any]],
    corpus: List[Dict[str, Any]],
    model_id: str,
) -> List[Dict[str, Any]]:
    """
    Build one forensics bundle per query that has failure_bucket == gold_not_in_candidates.
    Aligns by query_id / index; requires same order and length for per_query_list, query_reviews, grounded_queries.
    """
    corpus_by_id = _corpus_by_id(corpus)
    qid_to_grounded = {str(q.get("id", "")): q for q in grounded_queries}
    bundles: List[Dict[str, Any]] = []
    
    # Check if there are any misses before building the BM25 index
    has_misses = any(row.get("failure_bucket") == "gold_not_in_candidates" for row in per_query_list)
    bm25_index = None
    corpus_ids = []
    
    if has_misses:
        try:
            from retrieval_lab.sparse_retrieval import build_bm25_index
            corpus_ids = [u.get("id", "") for u in corpus]
            corpus_texts = [u.get("text", "") for u in corpus]
            bm25_index = build_bm25_index(corpus_texts)
        except Exception:
            pass

    for i, row in enumerate(per_query_list):
        if row.get("failure_bucket") != "gold_not_in_candidates":
            continue
        query_id = str(row.get("query_id", ""))
        review = query_reviews[i] if i < len(query_reviews) else {}
        q = qid_to_grounded.get(query_id) or grounded_queries[i] if i < len(grounded_queries) else {}
        required_gold = list(q.get("_required_gold") or q.get("required_gold") or q.get("gold_unit_ids") or [])
        gold_unit_features = [
            _gold_unit_features(gid, corpus_by_id)
            for gid in required_gold
        ]
        retrieval_intermediates = _retrieval_intermediates_from_review(review)
        bundle = {
            "query_id": query_id,
            "tier": row.get("tier", ""),
            "query_text": q.get("question") or q.get("text") or "",
            "required_gold_ids": required_gold,
            "gold_unit_features": gold_unit_features,
            "retrieval_intermediates": {
                model_id: retrieval_intermediates,
            },
            "derived": None,
        }
        bundle["derived"] = _derived_diagnostics(bundle, model_id, corpus_by_id, bm25_index, corpus_ids)
        bundle["miss_bucket"] = classify_miss(bundle)
        bundles.append(bundle)
    return bundles


def build_miss_classification_summary(
    bundles: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Pareto-ready: bucket counts and top recurring signatures."""
    bucket_counts: Dict[str, int] = {}
    signatures: Dict[str, int] = {}
    for b in bundles:
        bucket = b.get("miss_bucket") or MISS_BUCKET_UNCLASSIFIED
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        for g in b.get("gold_unit_features") or []:
            ut = g.get("unit_type") or "unknown"
            key = "unit_type:" + ut
            signatures[key] = signatures.get(key, 0) + 1
            if g.get("anomaly_flags", {}).get("undersized"):
                signatures["anomaly:undersized"] = signatures.get("anomaly:undersized", 0) + 1
            if g.get("anomaly_flags", {}).get("table_or_list"):
                signatures["anomaly:table_or_list"] = signatures.get("anomaly:table_or_list", 0) + 1
    top_sigs = sorted(signatures.items(), key=lambda x: -x[1])[:20]
    return {
        "n_misses": len(bundles),
        "bucket_counts": bucket_counts,
        "top_signatures": dict(top_sigs),
    }


def build_gold_retrievability_heatmap(
    bundles: List[Dict[str, Any]],
    channels: List[str],
) -> List[Dict[str, Any]]:
    """
    One row per (query_id, gold_id) with booleans per channel: admitted?
    With a single channel per run, this is a single column; multi-channel heatmap
    requires merging multiple run directories or running oracle probes.
    """
    rows: List[Dict[str, Any]] = []
    for b in bundles:
        qid = b.get("query_id", "")
        for gid in b.get("required_gold_ids") or []:
            admitted: Dict[str, bool] = {}
            for ch in channels:
                ri = (b.get("retrieval_intermediates") or {}).get(ch) or []
                unit_ids = [x.get("unit_id") for x in ri if x.get("unit_id")]
                admitted[ch] = gid in unit_ids
            rows.append({
                "query_id": qid,
                "gold_unit_id": gid,
                "admitted_by_channel": admitted,
            })
    return rows


def build_forensics_artifacts(
    per_query_by_model: Dict[str, List[Dict[str, Any]]],
    retrieved_chunks_by_model: Dict[str, List[Dict[str, Any]]],
    grounded_queries: List[Dict[str, Any]],
    corpus: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build forensics bundles and summary per model. Call from report writing when
    grounded_queries and corpus are available.
    """
    by_model: Dict[str, List[Dict[str, Any]]] = {}
    for model_id, per_query_list in per_query_by_model.items():
        query_reviews = retrieved_chunks_by_model.get(model_id)
        if not isinstance(query_reviews, list):
            query_reviews = []
        bundles = build_forensics_bundles(
            per_query_list=per_query_list,
            query_reviews=query_reviews,
            grounded_queries=grounded_queries,
            corpus=corpus,
            model_id=model_id,
        )
        by_model[model_id] = bundles
    all_bundles: List[Dict[str, Any]] = []
    for bl in by_model.values():
        all_bundles.extend(bl)
    summary = build_miss_classification_summary(all_bundles) if all_bundles else {}
    channels = list(per_query_by_model.keys())
    heatmap = build_gold_retrievability_heatmap(all_bundles, channels) if all_bundles else []
    return {
        "by_model": by_model,
        "miss_classification": summary,
        "gold_retrievability_heatmap": heatmap,
    }

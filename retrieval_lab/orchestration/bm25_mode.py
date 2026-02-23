"""BM25 retrieval mode orchestration extracted from run_experiment."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Tuple

from retrieval_lab.config import ParentFetchConfig
from retrieval_lab.metrics import score_retrieval
from retrieval_lab.orchestration.expansion_pipeline import apply_post_retrieval_expansion

logger = logging.getLogger(__name__)


def run_bm25_mode(
    *,
    config: Any,
    flags: Any,
    expansion_cfg: Any,
    corpus: List[Dict[str, Any]],
    corpus_ids: List[str],
    corpus_texts: List[str],
    grounded_queries: List[Dict[str, Any]],
    id_to_text: Dict[str, str],
    id_to_source_ids: Dict[str, List[str]],
    crossref_sidecar: Dict[str, List[str]],
    pairing_edges: Dict[str, List[Tuple[str, str, str]]],
    apply_unit_type_boost_fn: Callable[[List[List[str]], List[List[float]], List[Dict[str, Any]], List[Dict[str, Any]], float], None],
    qe_profile: Any = None,
    qe_mode: str = "none",
    qe_fusion_mode: str = "only_add",
    qe_only_add: Any = None,
    qe_enhance_query_ids: Any = None,
    qe_cache: Any = None,
) -> Dict[str, Any]:
    """Execute BM25 ranking, expansion, scoring, and query review assembly."""
    if flags.expand_context:
        logger.warning("Expand context is not supported for BM25 mode; skipping.")
    from retrieval_lab.sparse_retrieval import build_bm25_index, bm25_rank

    t0 = time.perf_counter()
    tokenizer_mode = getattr(config, "bm25_tokenizer_mode", "basic")
    bm25_k1 = float(getattr(config, "bm25_k1", 1.5))
    bm25_b = float(getattr(config, "bm25_b", 0.75))
    query_mode = getattr(config, "bm25_query_mode", "question_only")
    q_weight = int(getattr(config, "bm25_query_weight_question", 1))
    s_weight = int(getattr(config, "bm25_query_weight_summary", 1))

    bm25 = build_bm25_index(corpus_texts, tokenizer_mode=tokenizer_mode, k1=bm25_k1, b=bm25_b)
    max_k = max(config.top_k)

    use_qe = qe_profile is not None and qe_mode != "none"
    qe_only_add_flags = qe_only_add
    if use_qe:
        from retrieval_lab.query_enhancement.multi_query import (
            expand_query_texts,
            expand_query_texts_per_query_modes,
            fuse_only_add,
            fuse_multi_query_rankings,
            fuse_union_rerank,
        )
        from retrieval_lab.sparse_retrieval import build_query_text, _tokenize
        import numpy as np

        base_query_texts = [
            build_query_text(q, mode=query_mode, question_weight=q_weight, summary_weight=s_weight)
            for q in grounded_queries
        ]
        if qe_mode == "decompose":
            # Tier-gated decomposition: only apply to T2/T3; keep T1 stable.
            per_query_modes: List[str] = []
            for q in grounded_queries:
                tier = str(q.get("tier") or q.get("_tier") or "T1")
                if tier not in ("T2", "T3"):
                    per_query_modes.append("none")
                    continue
                if isinstance(qe_enhance_query_ids, dict):
                    qid = str(q.get("id", ""))
                    per_query_modes.append("decompose" if (qid and qe_enhance_query_ids.get(qid) == "retrieval_miss") else "none")
                elif qe_enhance_query_ids is not None:
                    qid = str(q.get("id", ""))
                    per_query_modes.append("decompose" if (qid and qid in qe_enhance_query_ids) else "none")
                else:
                    per_query_modes.append("decompose")
            expanded_groups, qe_expansion_logs = expand_query_texts_per_query_modes(
                base_query_texts, per_query_modes, qe_profile, cache=qe_cache,
            )
        else:
            expanded_groups, qe_expansion_logs = expand_query_texts(
                base_query_texts, qe_profile, qe_mode, cache=qe_cache,
            )
        logger.info("BM25 query enhancement (%s): %d queries -> %d variants",
                     qe_mode, len(base_query_texts), sum(len(g) for g in expanded_groups))

        # Deterministic tie-break for retrieval lists (score desc, doc_id lexical).
        corpus_ids_arr = np.asarray(corpus_ids, dtype=object)

        # Resolve fusion knobs (defaults when qe_only_add is None).
        eval_k = max(config.top_k)
        baseline_keep_n = int(getattr(qe_only_add, "baseline_keep_n", eval_k))
        baseline_keep_n = max(baseline_keep_n, eval_k)
        variant_k_per_query = int(getattr(qe_only_add, "variant_k_per_query", 20))
        admission_cutoff = int(getattr(qe_only_add, "admission_cutoff", 0))
        prefix_lock_n = int(getattr(qe_only_add, "prefix_lock_n", baseline_keep_n))
        tail_rerank = str(getattr(qe_only_add, "tail_rerank", "none"))
        tail_rerank_window = int(getattr(qe_only_add, "tail_rerank_window", 50))
        append_score_band = float(getattr(qe_only_add, "append_score_band", 1e-6))

        # Only-add safety: enlarge admission pool so variants can add without evicting baseline@eval_k.
        admission_cutoff_eff = admission_cutoff if admission_cutoff > 0 else max(50, max_k)
        admission_cutoff_eff = max(admission_cutoff_eff, baseline_keep_n)

        baseline_ranked_lists: List[List[str]] = []
        baseline_score_lists: List[List[float]] = []
        variant_ranked_lists: List[List[List[str]]] = []
        variant_score_lists: List[List[List[float]]] = []
        variant_maps_for_logs: List[Dict[str, List[str]]] = []

        for group in expanded_groups:
            if not group:
                baseline_ranked_lists.append([])
                baseline_score_lists.append([])
                variant_ranked_lists.append([])
                variant_score_lists.append([])
                variant_maps_for_logs.append({})
                continue

            # Baseline retrieval on q0 (first expansion).
            q0 = group[0]
            tokens0 = _tokenize(q0, mode=tokenizer_mode)
            scores0 = np.asarray(bm25.get_scores(tokens0), dtype=np.float32)
            order0 = np.lexsort((corpus_ids_arr, -scores0))
            top0 = order0[:admission_cutoff_eff]
            base_ids = [corpus_ids[j] for j in top0]
            base_scores = [float(scores0[j]) for j in top0]
            baseline_ranked_lists.append(base_ids)
            baseline_score_lists.append(base_scores)

            # Variant retrieval for q1..qm.
            v_rankings: List[List[str]] = []
            v_scores: List[List[float]] = []
            v_map: Dict[str, List[str]] = {}
            for variant_text in group[1:]:
                tokens = _tokenize(variant_text, mode=tokenizer_mode)
                scores_arr = np.asarray(bm25.get_scores(tokens), dtype=np.float32)
                order = np.lexsort((corpus_ids_arr, -scores_arr))
                top = order[:variant_k_per_query]
                ids = [corpus_ids[j] for j in top]
                scs = [float(scores_arr[j]) for j in top]
                v_rankings.append(ids)
                v_scores.append(scs)
                v_map[variant_text] = ids
            variant_ranked_lists.append(v_rankings)
            variant_score_lists.append(v_scores)
            variant_maps_for_logs.append(v_map)

        qe_fusion_debug: List[Dict[str, Any]] = []
        if qe_fusion_mode == "only_add":
            ranked_lists, score_lists, debug = fuse_only_add(
                baseline_ranked_lists=baseline_ranked_lists,
                baseline_score_lists=baseline_score_lists,
                variant_ranked_lists=variant_ranked_lists,
                variant_score_lists=variant_score_lists,
                baseline_keep_n=baseline_keep_n,
                admission_cutoff=admission_cutoff_eff,
                append_score_band=append_score_band,
            )
            for i in range(len(debug)):
                qe_fusion_debug.append(
                    {
                        **debug[i],
                        "fusion_mode": "only_add",
                        "variants": variant_maps_for_logs[i],
                        "prefix_lock_n": prefix_lock_n,
                        "tail_rerank": tail_rerank,
                        "tail_rerank_window": tail_rerank_window,
                    }
                )
        elif qe_fusion_mode == "union_rerank":
            per_expansion_rankings = [
                [baseline_ranked_lists[i]] + (variant_ranked_lists[i] or [])
                for i in range(len(baseline_ranked_lists))
            ]
            per_expansion_scores = [
                [baseline_score_lists[i]] + (variant_score_lists[i] or [])
                for i in range(len(baseline_score_lists))
            ]
            ranked_lists, score_lists = fuse_union_rerank(
                per_expansion_rankings=per_expansion_rankings,
                per_expansion_scores=per_expansion_scores,
                admission_cutoff=admission_cutoff_eff,
            )
        else:
            per_expansion_rankings = [
                [baseline_ranked_lists[i]] + (variant_ranked_lists[i] or [])
                for i in range(len(baseline_ranked_lists))
            ]
            policy = config.get_policy(config.document_id)
            ranked_lists, score_lists = fuse_multi_query_rankings(
                per_expansion_rankings, rrf_k=policy.fusion_k,
            )
    else:
        ranked_lists, score_lists = bm25_rank(
            bm25, corpus_ids, grounded_queries, max_k,
            tokenizer_mode=tokenizer_mode, query_mode=query_mode,
            question_weight=q_weight, summary_weight=s_weight,
        )
    boost = flags.unit_type_boost
    if boost > 0:
        apply_unit_type_boost_fn(ranked_lists, score_lists, corpus, grounded_queries, boost)

    ranked_lists, score_lists, pairing_payload = apply_post_retrieval_expansion(
        ranked_lists=ranked_lists,
        score_lists=score_lists,
        grounded_queries=grounded_queries,
        crossref_sidecar=crossref_sidecar,
        pairing_edges=pairing_edges,
        config=expansion_cfg,
    )

    # Diagnostic: rerank tail segment (after expansion/boost), then enforce prefix lock.
    if use_qe and qe_fusion_mode == "only_add" and (qe_fusion_debug or []) and tail_rerank != "none":
        from retrieval_lab.query_enhancement.multi_query import lexical_rerank_tail_segment

        locked_prefixes = [
            (d.get("baseline_topN", []) or [])[:prefix_lock_n]
            for d in (qe_fusion_debug or [])
        ]
        eligible = None
        if isinstance(qe_enhance_query_ids, dict):
            eligible = [
                str(q.get("id", "")) in qe_enhance_query_ids
                for q in grounded_queries
            ]
        elif isinstance(qe_enhance_query_ids, set):
            eligible = [
                str(q.get("id", "")) in qe_enhance_query_ids
                for q in grounded_queries
            ]
        if tail_rerank == "lexical":
            ranked_lists, score_lists = lexical_rerank_tail_segment(
                ranked_lists=ranked_lists,
                score_lists=score_lists,
                query_texts=[
                    (q.get("question") or q.get("expected_answer_summary") or "")
                    for q in grounded_queries
                ],
                id_to_text=id_to_text,
                locked_prefixes=locked_prefixes,
                admission_cutoff=admission_cutoff_eff,
                rerank_window=tail_rerank_window,
                eligible=eligible,
            )
        elif tail_rerank in ("cross_encoder", "cascade"):
            if tail_rerank == "cascade":
                ranked_lists, score_lists = lexical_rerank_tail_segment(
                    ranked_lists=ranked_lists,
                    score_lists=score_lists,
                    query_texts=[
                        (q.get("question") or q.get("expected_answer_summary") or "")
                        for q in grounded_queries
                    ],
                    id_to_text=id_to_text,
                    locked_prefixes=locked_prefixes,
                    admission_cutoff=admission_cutoff_eff,
                    rerank_window=tail_rerank_window,
                    eligible=eligible,
                )
            from retrieval_lab.reranker import load_cross_encoder, rerank_candidates

            reranker_model = getattr(config, "reranker", None) or "cross-encoder/ms-marco-MiniLM-L6-v2"
            r_model = load_cross_encoder(reranker_model)
            for i in range(len(grounded_queries)):
                if eligible is not None and (i >= len(eligible) or not eligible[i]):
                    continue
                if tail_rerank == "cascade":
                    gold = set(grounded_queries[i].get("gold_unit_ids") or [])
                    if gold:
                        first = None
                        for rr, cid in enumerate(ranked_lists[i][:eval_k], start=1):
                            if cid in gold:
                                first = rr
                                break
                        if first is not None:
                            continue
                ids0 = ranked_lists[i] or []
                sc0 = score_lists[i] or []
                n0 = min(len(ids0), len(sc0))
                ids0 = ids0[:n0]
                sc0 = sc0[:n0]
                score_by_id = {cid: float(sc) for cid, sc in zip(ids0, sc0)}

                locked = locked_prefixes[i] if i < len(locked_prefixes) else []
                locked_set = set(locked)
                tail_all = [cid for cid in ids0 if cid not in locked_set]
                tail_cap = max(0, admission_cutoff_eff - len(locked))
                tail = tail_all[:tail_cap]
                tail_rest = tail_all[tail_cap:]

                tail_rerank_ids = tail[: max(1, tail_rerank_window)]
                tail_hold = tail[max(1, tail_rerank_window) :]
                tail_candidates = [{"chunk_id": cid, "text": id_to_text.get(cid, "")} for cid in tail_rerank_ids]
                q_text = base_query_texts[i] if i < len(base_query_texts) else (grounded_queries[i].get("question") or "")
                reranked = rerank_candidates(q_text, tail_candidates, r_model, top_k=len(tail_candidates))
                tail_sorted = [r["chunk_id"] for r in reranked]
                tail_scores_by_id = {r["chunk_id"]: float(r.get("rerank_score", 0.0)) for r in reranked}

                new_ids = (
                    locked
                    + tail_sorted
                    + [cid for cid in tail_hold if cid not in set(tail_sorted)]
                    + [cid for cid in tail_rest if cid not in set(tail_sorted)]
                )
                new_scores = (
                    [score_by_id.get(cid, 0.0) for cid in locked]
                    + [tail_scores_by_id.get(cid, 0.0) for cid in tail_sorted]
                    + [score_by_id.get(cid, 0.0) for cid in tail_hold if cid not in set(tail_sorted)]
                    + [score_by_id.get(cid, 0.0) for cid in tail_rest if cid not in set(tail_sorted)]
                )
                ranked_lists[i] = new_ids
                score_lists[i] = new_scores

    # Enforce baseline lock *after* downstream stages that can reorder candidates.
    if use_qe and qe_fusion_mode == "only_add":
        from retrieval_lab.query_enhancement.multi_query import lock_prefix

        locked_prefixes = [
            (d.get("baseline_topN", []) or [])[:prefix_lock_n]
            for d in (qe_fusion_debug or [])
        ]
        if locked_prefixes and len(locked_prefixes) == len(ranked_lists):
            ranked_lists, score_lists = lock_prefix(
                ranked_lists=ranked_lists,
                score_lists=score_lists,
                locked_prefixes=locked_prefixes,
            )

    ranked_source_id_lists = [
        [id_to_source_ids.get(cid, [cid]) for cid in ranked_lists[i]]
        for i in range(len(ranked_lists))
    ]
    scoring_time_sec = time.perf_counter() - t0

    metrics = score_retrieval(
        grounded_queries,
        ranked_lists,
        score_lists,
        config.top_k,
        ranked_source_id_lists=ranked_source_id_lists,
    )

    query_reviews = []
    pf_policy = ParentFetchConfig(
        depth=flags.parent_fetch_depth,
        char_cap=flags.parent_fetch_cap,
        enabled=flags.parent_fetch_enabled,
    )
    for i, q in enumerate(grounded_queries):
        pq = metrics.per_query[i]
        retrieved = []
        for r, (cid, sc) in enumerate(zip(ranked_lists[i], score_lists[i]), start=1):
            retrieved.append(
                {
                    "rank": r,
                    "chunk_id": cid,
                    "score": round(sc, 4),
                    "text": id_to_text.get(cid, ""),
                }
            )
        if pf_policy.enabled:
            from retrieval_lab.parent_fetch import fetch_parent_context

            retrieved = fetch_parent_context(retrieved, corpus, pf_policy)
        query_reviews.append(
            {
                "query_id": q.get("id", ""),
                "question": q.get("question", ""),
                "expected_answer_summary": q.get("expected_answer_summary", ""),
                "gold_unit_ids": list(q.get("gold_unit_ids") or []),
                "first_gold_rank": pq.get("first_gold_rank"),
                "failure_type": pq.get("failure_type", ""),
                "retrieved": retrieved,
            }
        )
        if use_qe and qe_fusion_mode == "only_add":
            # Attach per-query fusion audit (baseline lock + what got added).
            gold = set(q.get("gold_unit_ids") or [])
            baseline_top = set((qe_fusion_debug[i].get("baseline_topN") or []))
            final_admitted = set((qe_fusion_debug[i].get("final_admitted") or []))
            qe_fusion_debug[i]["baseline_gold_in_candidates"] = bool(gold & baseline_top)
            qe_fusion_debug[i]["new_gold_added_by_variants"] = sorted(list((gold & final_admitted) - baseline_top))
            query_reviews[-1]["qe_fusion"] = qe_fusion_debug[i]
        top3_ids = ranked_lists[i][:3]
        top3_scores = [round(s, 3) for s in score_lists[i][:3]]
        logger.info(
            "[bm25] query_id=%s top3=%s scores=%s first_gold_rank=%s failure_type=%s",
            q.get("id", ""),
            top3_ids,
            top3_scores,
            pq.get("first_gold_rank"),
            pq.get("failure_type", ""),
        )

    return {
        "results": {
            "recall_at_k": metrics.recall_at_k,
            "hit_at_k": metrics.hit_at_k,
            "ndcg_at_k": metrics.ndcg_at_k,
            "full_set_hit_at_k": metrics.full_set_hit_at_k,
            "required_recall_at_k": metrics.required_recall_at_k,
            "required_full_set_hit_at_k": metrics.required_full_set_hit_at_k,
            "rank_of_last_required_mean": metrics.rank_of_last_required_mean,
            "mrr": metrics.mrr,
            "gold_in_candidates": metrics.gold_in_candidates,
            "gold_in_candidates_true_ceiling": metrics.gold_in_candidates_true_ceiling,
            "grounding_coverage": metrics.grounding_coverage,
            "answer_similarity_at_k": metrics.answer_similarity_at_k,
            "failure_counts": metrics.failure_counts,
            "failure_bucket_counts": metrics.failure_bucket_counts,
            "per_suite": metrics.per_suite,
            "per_tier": metrics.per_tier,
            "embedding_time_sec": 0.0,
            "scoring_time_sec": scoring_time_sec,
        },
        "per_query": metrics.per_query,
        "query_reviews": query_reviews,
        "pairing_payload": pairing_payload,
    }

"""Dense/hybrid retrieval orchestration extracted from run_experiment."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from retrieval_lab.config import ParentFetchConfig
from retrieval_lab.dual_list_fusion import fuse_dual_list
from retrieval_lab.gold_grounding import ground_queries_corpus_semantic
from retrieval_lab.metrics import score_retrieval
from retrieval_lab.orchestration.expansion_pipeline import apply_post_retrieval_expansion
from retrieval_lab.sparse_retrieval import build_query_text
from retrieval_lab.store import (
    fetch_cached_embeddings,
    save_cached_embeddings,
    save_embedding_run_metadata,
)
from retrieval_lab.substrate_loader import merge_units_by_heading

logger = logging.getLogger(__name__)


def _rerank_candidates_dense(
    *,
    query_embeddings: np.ndarray,
    corpus_embeddings: np.ndarray,
    corpus_ids: List[str],
    ranked_lists: List[List[str]],
    stage1_admission_k: int,
    final_k: int,
) -> tuple[List[List[str]], List[List[float]]]:
    """Dense rerank over Stage1-admitted candidates only."""
    id_to_idx = {cid: i for i, cid in enumerate(corpus_ids)}
    reranked_lists: List[List[str]] = []
    reranked_scores: List[List[float]] = []
    for i, candidate_ids in enumerate(ranked_lists):
        admitted = candidate_ids[:stage1_admission_k]
        if not admitted:
            reranked_lists.append([])
            reranked_scores.append([])
            continue
        scores = []
        q_vec = query_embeddings[i]
        for cid in admitted:
            idx = id_to_idx.get(cid)
            if idx is None:
                scores.append((cid, float("-inf")))
            else:
                scores.append((cid, float(np.dot(q_vec, corpus_embeddings[idx]))))
        # Deterministic tie-break by doc_id.
        scores.sort(key=lambda x: (-x[1], x[0]))
        trimmed = scores[:final_k]
        reranked_lists.append([cid for cid, _ in trimmed])
        reranked_scores.append([score for _, score in trimmed])
    return reranked_lists, reranked_scores


def _minmax_normalize(values: Dict[str, float]) -> Dict[str, float]:
    if not values:
        return {}
    lo = min(values.values())
    hi = max(values.values())
    if hi <= lo:
        return {k: 1.0 for k in values}
    denom = hi - lo
    return {k: (v - lo) / denom for k, v in values.items()}


def _rank_deadline_order(
    ordered_ids: List[str],
    score_by_id: Dict[str, float],
    deadline_by_id: Dict[str, int],
) -> tuple[List[str], int]:
    """Apply earliest-deadline-aware ordering while preferring higher score.

    Each candidate has a deadline = best raw rank. We greedily place one item per
    position; if any item has deadline <= current position, we must place one of
    those urgent items now to avoid avoidable demotion.
    """
    remaining = list(ordered_ids)
    pos = 1
    final: List[str] = []
    while remaining:
        urgent = [cid for cid in remaining if deadline_by_id.get(cid, 10**9) <= pos]
        pool = urgent if urgent else remaining
        pick = max(pool, key=lambda cid: (score_by_id.get(cid, float("-inf")), -deadline_by_id.get(cid, 10**9)))
        final.append(pick)
        remaining.remove(pick)
        pos += 1
    violations = sum(1 for idx, cid in enumerate(final, start=1) if idx > deadline_by_id.get(cid, 10**9))
    return final, violations


def _load_or_compute_corpus_embeddings(
    *,
    config: Any,
    model_id: str,
    model: Any,
    encode_texts_fn: Any,
    run_id: str,
    corpus_ids: List[str],
    corpus_texts: List[str],
    output_dir: Path,
    eval_only_run_id: Optional[str],
    mongo_uri: Optional[str],
) -> Dict[str, Any]:
    """Resolve corpus embeddings from cache/disk or compute and persist."""
    t0 = time.perf_counter()
    embed_dir = Path(config.output_dir) / f"embed_{run_id}"
    safe_model_id = str(model_id).replace("/", "__")
    npy_path = embed_dir / "embeddings" / f"{safe_model_id}_corpus.npy"
    index_path = embed_dir / "embeddings" / "corpus_index.json"
    if not (npy_path.exists() and index_path.exists()) and eval_only_run_id:
        for subdir in Path(config.output_dir).iterdir():
            if not subdir.is_dir():
                continue
            idx_path = subdir / "embeddings" / "corpus_index.json"
            if not idx_path.exists():
                continue
            try:
                index_data = json.loads(idx_path.read_text(encoding="utf-8"))
                if index_data.get("run_id") == run_id:
                    safe_model_id = str(model_id).replace("/", "__")
                    npy_path = subdir / "embeddings" / f"{safe_model_id}_corpus.npy"
                    index_path = idx_path
                    if npy_path.exists():
                        unit_id_to_index = index_data.get("unit_id_to_index", {})
                        if all(uid in unit_id_to_index for uid in corpus_ids):
                            logger.info("Eval-only: found compatible embeddings for run_id=%s in %s", run_id, subdir.name)
                            break
            except (json.JSONDecodeError, OSError):
                continue

    if eval_only_run_id and npy_path.exists() and index_path.exists():
        loaded = np.load(npy_path)
        index_data = json.loads(index_path.read_text(encoding="utf-8"))
        unit_id_to_index = index_data.get("unit_id_to_index", {})
        try:
            corpus_embeddings = np.array(
                [loaded[unit_id_to_index[uid]] for uid in corpus_ids],
                dtype=np.float32,
            )
        except KeyError as e:
            raise ValueError(
                f"Eval-only: corpus mismatch for run_id={run_id} (missing unit in embed index). {e}"
            ) from e
        logger.info("Loaded %d embeddings from disk (%s)", len(corpus_embeddings), npy_path)
    else:
        cached = fetch_cached_embeddings(run_id, model_id, mongo_uri) if ((eval_only_run_id or config.reuse_embeddings) and mongo_uri) else None
        if cached and len(cached) == len(corpus_ids):
            id_to_emb = {r["chunk_id"]: r["embedding"] for r in cached}
            corpus_embeddings = np.array([id_to_emb[uid] for uid in corpus_ids], dtype=np.float32)
            logger.info("Loaded %d embeddings from MongoDB cache", len(corpus_embeddings))
        elif eval_only_run_id:
            raise ValueError(
                f"Eval-only: no cached embeddings for run_id={run_id} model_id={model_id}. "
                "Run embed step first (without --run-id), or start MongoDB and re-run embed to populate cache."
            )
        else:
            corpus_embeddings = encode_texts_fn(model, corpus_texts, batch_size=config.batch_size)
            if mongo_uri:
                records = [
                    {"run_id": run_id, "model_id": model_id, "chunk_id": uid, "embedding": corpus_embeddings[i].tolist()}
                    for i, uid in enumerate(corpus_ids)
                ]
                save_cached_embeddings(run_id, model_id, records, mongo_uri, clear_existing=True)
                save_embedding_run_metadata(run_id, model_id, len(corpus_ids), mongo_uri)
            (output_dir / "embeddings").mkdir(exist_ok=True)
            np.save(output_dir / "embeddings" / f"{safe_model_id}_corpus.npy", corpus_embeddings)
            if model_id == config.models[0]:
                index_path = output_dir / "embeddings" / "corpus_index.json"
                index_path.write_text(
                    json.dumps(
                        {"run_id": run_id, "substrate_version": config.substrate_version, "unit_id_to_index": {uid: i for i, uid in enumerate(corpus_ids)}},
                        indent=2,
                    ),
                    encoding="utf-8",
                )
    return {
        "corpus_embeddings": corpus_embeddings,
        "embedding_time_sec": time.perf_counter() - t0,
    }


def _load_or_compute_family_embeddings(
    *,
    config: Any,
    model_id: str,
    model: Any,
    encode_texts_fn: Any,
    eval_only_run_id: Optional[str],
    mongo_uri: Optional[str],
    output_dir: Path,
    use_dual_list_fusion: bool,
    family_corpus: Optional[List[Dict[str, Any]]],
    family_corpus_ids: List[str],
    run_id_family: Optional[str],
) -> Optional[np.ndarray]:
    """Resolve family (projection) embeddings for dual-list fusion."""
    if not (use_dual_list_fusion and family_corpus is not None and run_id_family is not None):
        return None

    family_corpus_texts = [c.get("text", "") for c in family_corpus]
    cached_f = fetch_cached_embeddings(run_id_family, model_id, mongo_uri) if ((eval_only_run_id or config.reuse_embeddings) and mongo_uri) else None
    if cached_f and len(cached_f) == len(family_corpus_ids):
        id_to_emb_f = {r["chunk_id"]: r["embedding"] for r in cached_f}
        family_embeddings = np.array(
            [id_to_emb_f[fid] for fid in family_corpus_ids], dtype=np.float32
        )
        logger.info("Loaded %d family embeddings from cache (run_id_family=%s)", len(family_embeddings), run_id_family)
        return family_embeddings

    family_embeddings = encode_texts_fn(model, family_corpus_texts, batch_size=config.batch_size)
    if mongo_uri and not eval_only_run_id:
        records_f = [
            {"run_id": run_id_family, "model_id": model_id, "chunk_id": fid, "embedding": family_embeddings[i].tolist()}
            for i, fid in enumerate(family_corpus_ids)
        ]
        save_cached_embeddings(run_id_family, model_id, records_f, mongo_uri, clear_existing=True)
        save_embedding_run_metadata(run_id_family, model_id, len(family_corpus_ids), mongo_uri)
    safe_model_id = str(model_id).replace("/", "__")
    (output_dir / "embeddings").mkdir(exist_ok=True)
    np.save(output_dir / "embeddings" / f"{safe_model_id}_family.npy", family_embeddings)
    return family_embeddings


def _run_ranking_pipeline(
    *,
    config: Any,
    flags: Any,
    expansion_cfg: Any,
    model_id: str,
    model: Any,
    encode_texts_fn: Any,
    corpus: List[Dict[str, Any]],
    corpus_ids: List[str],
    corpus_embeddings: np.ndarray,
    id_to_text: Dict[str, str],
    id_to_index: Dict[str, int],
    id_to_source_ids: Dict[str, List[str]],
    grounded_queries: List[Dict[str, Any]],
    flat_queries: List[Dict[str, Any]],
    use_semantic_grounding: bool,
    all_grounding_audit: List[Dict[str, Any]],
    bm25_ranked_lists: Optional[List[List[str]]],
    use_dual_list_fusion: bool,
    family_embeddings: Optional[np.ndarray],
    family_corpus_ids: List[str],
    family_id_to_anchor_unit_id: Dict[str, str],
    crossref_sidecar: Dict[str, List[str]],
    pairing_edges: Dict[str, Any],
    build_expanded_texts_fn: Any,
    apply_unit_type_boost_fn: Any,
    qe_profile: Any = None,
    qe_mode: str = "none",
    qe_fusion_mode: str = "only_add",
    qe_only_add: Any = None,
    qe_enhance_query_ids: Any = None,
    qe_cache: Any = None,
) -> Dict[str, Any]:
    """Run query encoding, ranking, reranking, and post-retrieval expansions."""
    if use_semantic_grounding:
        summary_texts = [(q.get("expected_answer_summary") or "").strip() for q in flat_queries]
        summary_embeddings = encode_texts_fn(model, summary_texts, batch_size=config.batch_size)
        grounded_queries, all_grounding_audit = ground_queries_corpus_semantic(
            flat_queries,
            summary_embeddings,
            corpus_embeddings,
            corpus_ids,
            top_n=config.gold_semantic_top_n,
        )

    use_two_stage = bool(getattr(flags, "two_stage_retrieval", False))
    stage1_query_mode = getattr(flags, "stage1_query_mode", "question_plus_summary")
    stage2_query_mode = getattr(flags, "stage2_query_mode", "question_only")
    stage1_admission_k = int(getattr(flags, "stage1_admission_k", 100))
    stage2_rerank_method = getattr(flags, "stage2_rerank_method", "dense")
    question_weight = int(getattr(config, "bm25_query_weight_question", 1))
    summary_weight = int(getattr(config, "bm25_query_weight_summary", 1))

    query_texts_stage1 = [
        build_query_text(
            q,
            mode=(stage1_query_mode if use_two_stage else "question_only"),
            question_weight=question_weight,
            summary_weight=summary_weight,
        )
        for q in grounded_queries
    ]

    use_qe = qe_profile is not None and qe_mode != "none"
    qe_expansion_logs: Optional[List[Any]] = None
    qe_fusion_debug: Optional[List[Dict[str, Any]]] = None
    if use_qe:
        from retrieval_lab.query_enhancement.multi_query import (
            expand_query_texts,
            expand_query_texts_per_query_modes,
            fuse_only_add,
            fuse_multi_query_rankings,
            fuse_union_rerank,
        )
        baseline_failure_types = qe_enhance_query_ids if isinstance(qe_enhance_query_ids, dict) else None
        if qe_mode == "decompose":
            # Tier-gated decomposition: only apply to T2/T3; keep T1 stable.
            per_query_modes: List[str] = []
            for q in grounded_queries:
                tier = str(q.get("tier") or q.get("_tier") or "T1")
                if tier not in ("T2", "T3"):
                    per_query_modes.append("none")
                    continue
                if baseline_failure_types is not None:
                    qid = str(q.get("id", ""))
                    # Recommended policy: decomposition only for retrieval_miss.
                    per_query_modes.append("decompose" if (qid and baseline_failure_types.get(qid) == "retrieval_miss") else "none")
                elif qe_enhance_query_ids is not None:
                    qid = str(q.get("id", ""))
                    per_query_modes.append("decompose" if (qid and qid in qe_enhance_query_ids) else "none")
                else:
                    per_query_modes.append("decompose")
            expanded_groups, qe_expansion_logs = expand_query_texts_per_query_modes(
                query_texts_stage1, per_query_modes, qe_profile, cache=qe_cache,
            )
        else:
            expanded_groups, qe_expansion_logs = expand_query_texts(
                query_texts_stage1, qe_profile, qe_mode, cache=qe_cache,
            )
        n_expanded = sum(len(g) for g in expanded_groups)
        logger.info("Query enhancement (%s): %d queries -> %d total variants", qe_mode, len(query_texts_stage1), n_expanded)

    query_embeddings_stage1 = encode_texts_fn(model, query_texts_stage1, batch_size=config.batch_size)
    t1 = time.perf_counter()
    max_k = max(config.top_k)
    retrieval_cutoff = max(max_k, stage1_admission_k if use_two_stage else max_k)
    ranked_lists = []
    score_lists = []

    if use_qe:
        all_variant_texts = [qt for group in expanded_groups for qt in group]
        all_variant_embeddings = encode_texts_fn(model, all_variant_texts, batch_size=config.batch_size)
        all_v_norm = all_variant_embeddings / (np.linalg.norm(all_variant_embeddings, axis=1, keepdims=True) + 1e-9)
        c_norm = corpus_embeddings / (np.linalg.norm(corpus_embeddings, axis=1, keepdims=True) + 1e-9)
        all_sim = np.dot(all_v_norm, c_norm.T)

        # Determine fusion knobs (defaults when qe_only_add is None).
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
        admission_cutoff_eff = admission_cutoff if admission_cutoff > 0 else max(50, retrieval_cutoff)
        admission_cutoff_eff = max(admission_cutoff_eff, baseline_keep_n)
        if use_two_stage:
            admission_cutoff_eff = max(admission_cutoff_eff, stage1_admission_k)

        corpus_ids_arr = np.asarray(corpus_ids, dtype=object)

        baseline_ranked_lists: List[List[str]] = []
        baseline_score_lists: List[List[float]] = []
        variant_ranked_lists: List[List[List[str]]] = []
        variant_score_lists: List[List[List[float]]] = []
        variant_maps_for_logs: List[Dict[str, List[str]]] = []

        offset = 0
        for group in expanded_groups:
            if not group:
                baseline_ranked_lists.append([])
                baseline_score_lists.append([])
                variant_ranked_lists.append([])
                variant_score_lists.append([])
                variant_maps_for_logs.append({})
                continue

            # Baseline retrieval:
            # - Dense/hybrid: q0 row is the original query embedding.
            # - Hybrid safety: baseline must be the *full hybrid(q0)* output (dense+BM25 RRF).
            row0 = all_sim[offset]
            order0 = np.lexsort((corpus_ids_arr, -row0))
            # For hybrid baseline B, dense(q0) must match the baseline pipeline input to RRF.
            # Baseline pipeline uses dense top-`retrieval_cutoff` (typically max(top_k)).
            dense_limit = retrieval_cutoff if (config.retrieval_mode in ("hybrid", "hybrid+rerank") and bm25_ranked_lists is not None) else admission_cutoff_eff
            top0 = order0[:dense_limit]
            dense_base_ids = [corpus_ids[j] for j in top0]
            dense_base_scores = [float(row0[j]) for j in top0]
            offset += 1

            if config.retrieval_mode in ("hybrid", "hybrid+rerank") and bm25_ranked_lists is not None:
                from retrieval_lab.sparse_retrieval import reciprocal_rank_fusion
                policy = config.get_policy(config.document_id)
                rrf_k = policy.fusion_k
                qi = len(baseline_ranked_lists)
                fused_ids, fused_scores = reciprocal_rank_fusion(
                    [[dense_base_ids, bm25_ranked_lists[qi]]],
                    k=rrf_k,
                    # IMPORTANT: baseline B must match the baseline hybrid pipeline output.
                    # Using a larger max_k here can change the top-20 due to RRF tie interactions.
                    max_k=retrieval_cutoff,
                )
                base_ids = fused_ids[0]
                base_scores = fused_scores[0]
            else:
                base_ids = dense_base_ids
                base_scores = dense_base_scores

            baseline_ranked_lists.append(base_ids)
            baseline_score_lists.append(base_scores)

            # Variant retrieval (q1..qm rows).
            v_rankings: List[List[str]] = []
            v_scores: List[List[float]] = []
            v_map: Dict[str, List[str]] = {}
            for variant_text in group[1:]:
                row = all_sim[offset]
                order = np.lexsort((corpus_ids_arr, -row))
                top = order[:variant_k_per_query]
                ids = [corpus_ids[j] for j in top]
                scs = [float(row[j]) for j in top]
                v_rankings.append(ids)
                v_scores.append(scs)
                v_map[variant_text] = ids
                offset += 1
            variant_ranked_lists.append(v_rankings)
            variant_score_lists.append(v_scores)
            variant_maps_for_logs.append(v_map)

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
            qe_fusion_debug = [
                {
                    **debug[i],
                    "fusion_mode": "only_add",
                    "variants": variant_maps_for_logs[i],
                    "prefix_lock_n": prefix_lock_n,
                    "tail_rerank": tail_rerank,
                    "tail_rerank_window": tail_rerank_window,
                }
                for i in range(len(debug))
            ]
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

        # Use original query embeddings for downstream reranking
        q_norm = query_embeddings_stage1 / (np.linalg.norm(query_embeddings_stage1, axis=1, keepdims=True) + 1e-9)
        logger.info("Multi-query fusion complete: mode=%s queries=%d", qe_fusion_mode, len(ranked_lists))
    elif use_dual_list_fusion and family_embeddings is not None:
        q_norm = query_embeddings_stage1 / (np.linalg.norm(query_embeddings_stage1, axis=1, keepdims=True) + 1e-9)
        Ku = flags.dual_list_ku
        Kf = flags.dual_list_kf
        Kfinal = flags.dual_list_kfinal
        Qu = flags.dual_list_qu
        family_params_str = f"sym_w{flags.dual_list_family_window}_m{flags.dual_list_family_max_units}"
        c_norm_u = corpus_embeddings / (np.linalg.norm(corpus_embeddings, axis=1, keepdims=True) + 1e-9)
        c_norm_f = family_embeddings / (np.linalg.norm(family_embeddings, axis=1, keepdims=True) + 1e-9)
        sim_u = np.dot(q_norm, c_norm_u.T)
        sim_f = np.dot(q_norm, c_norm_f.T)
        for i in range(len(grounded_queries)):
            U_idx = np.argsort(sim_u[i])[::-1][:Ku]
            U_ids = [corpus_ids[j] for j in U_idx]
            U_scores = [float(sim_u[i][j]) for j in U_idx]
            F_idx = np.argsort(sim_f[i])[::-1][:Kf]
            F_ids = [family_corpus_ids[j] for j in F_idx]
            F_scores = [float(sim_f[i][j]) for j in F_idx]
            fused_ids, fused_scores, _ = fuse_dual_list(
                U_ids,
                U_scores,
                F_ids,
                F_scores,
                family_id_to_anchor_unit_id,
                Qu=Qu,
                Kfinal=Kfinal,
                family_params=family_params_str,
            )
            ranked_lists.append(fused_ids)
            score_lists.append(fused_scores)
        logger.info("A1.2 dual-list fusion applied (Ku=%d Kf=%d Kfinal=%d Qu=%d)", Ku, Kf, Kfinal, Qu)
    else:
        q_norm = query_embeddings_stage1 / (np.linalg.norm(query_embeddings_stage1, axis=1, keepdims=True) + 1e-9)
        c_norm = corpus_embeddings / (np.linalg.norm(corpus_embeddings, axis=1, keepdims=True) + 1e-9)
        sim = np.dot(q_norm, c_norm.T)
        corpus_ids_arr = np.asarray(corpus_ids, dtype=object)
        for i in range(len(grounded_queries)):
            row = sim[i]
            # Deterministic tie-break by doc_id (score desc, doc_id lexical).
            order = np.lexsort((corpus_ids_arr, -row))
            top_indices = order[:retrieval_cutoff]
            ranked_lists.append([corpus_ids[j] for j in top_indices])
            score_lists.append([float(row[j]) for j in top_indices])

    if flags.expand_context:
        n_ctx = flags.expand_context_n
        logger.info("Expand context (n=%d) and re-rank for %d queries", n_ctx, len(grounded_queries))
        for i in range(len(grounded_queries)):
            center_ids = ranked_lists[i][:max_k]
            expanded_texts = build_expanded_texts_fn(corpus, id_to_index, center_ids, n_ctx)
            expanded_emb = encode_texts_fn(model, expanded_texts, batch_size=config.batch_size)
            q_emb = query_embeddings[i : i + 1]
            scores = np.dot(q_emb, expanded_emb.T).flatten()
            # Deterministic tie-break by center_id.
            center_arr = np.asarray(center_ids, dtype=object)
            new_order = np.lexsort((center_arr, -scores))
            ranked_lists[i] = [center_ids[j] for j in new_order]
            score_lists[i] = [float(scores[j]) for j in new_order]

    # Hybrid fusion step:
    # If QE only_add is active, baseline already used hybrid(q0) and only-add is applied into that set.
    # Do not re-fuse (it would reintroduce demotions).
    if (
        config.retrieval_mode in ("hybrid", "hybrid+rerank")
        and bm25_ranked_lists is not None
        and not (use_qe and qe_fusion_mode == "only_add")
    ):
        from retrieval_lab.sparse_retrieval import reciprocal_rank_fusion
        policy = config.get_policy(config.document_id)
        rrf_k = policy.fusion_k
        rankings_per_query = [
            [ranked_lists[i], bm25_ranked_lists[i]]
            for i in range(len(grounded_queries))
        ]
        ranked_lists, score_lists = reciprocal_rank_fusion(
            rankings_per_query, k=rrf_k, max_k=retrieval_cutoff
        )
        logger.info("Fused dense + BM25 with RRF (k=%d) for model %s", rrf_k, model_id)

    reranker_model = getattr(config, "reranker", None)
    if config.retrieval_mode == "hybrid+rerank" and not reranker_model:
        reranker_model = "cross-encoder/ms-marco-MiniLM-L6-v2"
    if use_two_stage:
        query_texts_stage2 = [
            build_query_text(
                q,
                mode=stage2_query_mode,
                question_weight=question_weight,
                summary_weight=summary_weight,
            )
            for q in grounded_queries
        ]
        query_embeddings_stage2 = encode_texts_fn(model, query_texts_stage2, batch_size=config.batch_size)
        if stage2_rerank_method == "cross_encoder":
            if not reranker_model:
                raise ValueError("two_stage_retrieval with cross_encoder requires reranker")
            from retrieval_lab.reranker import load_cross_encoder, rerank_candidates

            r_model = load_cross_encoder(reranker_model)
            for i in range(len(grounded_queries)):
                admitted_ids = ranked_lists[i][:stage1_admission_k]
                admitted_candidates = [{"chunk_id": cid, "text": id_to_text.get(cid, "")} for cid in admitted_ids]
                reranked = rerank_candidates(
                    query_texts_stage2[i],
                    admitted_candidates,
                    r_model,
                    top_k=max_k,
                )
                ranked_lists[i] = [r["chunk_id"] for r in reranked]
                score_lists[i] = [r.get("rerank_score", 0.0) for r in reranked]
            logger.info(
                "Two-stage retrieval: Stage1 admission k=%d, Stage2 cross-encoder rerank top-%d",
                stage1_admission_k,
                max_k,
            )
        else:
            ranked_lists, score_lists = _rerank_candidates_dense(
                query_embeddings=query_embeddings_stage2,
                corpus_embeddings=corpus_embeddings,
                corpus_ids=corpus_ids,
                ranked_lists=ranked_lists,
                stage1_admission_k=stage1_admission_k,
                final_k=max_k,
            )
            logger.info(
                "Two-stage retrieval: Stage1 admission k=%d, Stage2 dense rerank top-%d",
                stage1_admission_k,
                max_k,
            )
        query_embeddings = query_embeddings_stage2
    else:
        if reranker_model and config.retrieval_mode in ("hybrid", "hybrid+rerank"):
            from retrieval_lab.reranker import load_cross_encoder, rerank_candidates
            r_model = load_cross_encoder(reranker_model)
            rerank_top_k = max(config.top_k)
            for i in range(len(grounded_queries)):
                q_text = grounded_queries[i].get("question") or grounded_queries[i].get("expected_answer_summary") or ""
                top_50_ids = ranked_lists[i][:50]
                top_50_candidates = [
                    {"chunk_id": cid, "text": id_to_text.get(cid, "")}
                    for cid in top_50_ids
                ]
                reranked = rerank_candidates(q_text, top_50_candidates, r_model, top_k=rerank_top_k)
                ranked_lists[i] = [r["chunk_id"] for r in reranked]
                score_lists[i] = [r.get("rerank_score", 0.0) for r in reranked]
            logger.info("Reranked hybrid top-50 to top-%d with %s", rerank_top_k, reranker_model)
        query_embeddings = query_embeddings_stage1

    ranked_source_id_lists: Optional[List[List[List[str]]]] = None
    final_id_to_text = dict(id_to_text)
    raw_merge_diagnostics: Dict[str, Any] = {}

    if flags.raw_first_merge_rerank:
        merged_corpus = merge_units_by_heading(
            corpus,
            max_chars=flags.merge_max_chars,
        )
        merged_by_id = {u["id"]: u for u in merged_corpus}
        source_to_merged: Dict[str, str] = {}
        for mu in merged_corpus:
            for src in mu.get("source_unit_ids", [mu["id"]]):
                source_to_merged[src] = mu["id"]
            final_id_to_text[mu["id"]] = mu.get("text", "")

        final_cutoff = max(max(config.top_k), flags.raw_merge_rerank_top_k)
        merged_ranked_lists: List[List[str]] = []
        merged_score_lists: List[List[float]] = []
        merged_source_lists: List[List[List[str]]] = []
        per_query_diag: List[Dict[str, Any]] = []
        total_violations = 0
        total_raw_top_missing = 0

        for i in range(len(grounded_queries)):
            raw_limit = min(flags.raw_stage1_admission_k, len(ranked_lists[i]))
            admitted_ids = ranked_lists[i][:raw_limit]
            admitted_scores = score_lists[i][:raw_limit]
            if not admitted_ids:
                merged_ranked_lists.append([])
                merged_score_lists.append([])
                merged_source_lists.append([])
                per_query_diag.append({
                    "query_id": grounded_queries[i].get("id", ""),
                    "admitted_raw_count": 0,
                    "merged_candidate_count": 0,
                    "monotonic_rank_violations": 0,
                    "raw_top_missing_in_final_topk": 0,
                })
                continue

            agg: Dict[str, Dict[str, Any]] = {}
            for raw_rank, (cid, sc) in enumerate(zip(admitted_ids, admitted_scores), start=1):
                mid = source_to_merged.get(cid, cid)
                rec = agg.setdefault(
                    mid,
                    {"best_raw_rank": raw_rank, "best_raw_score": float(sc), "covered_sources": set()},
                )
                if raw_rank < rec["best_raw_rank"]:
                    rec["best_raw_rank"] = raw_rank
                if float(sc) > rec["best_raw_score"]:
                    rec["best_raw_score"] = float(sc)
                rec["covered_sources"].add(cid)

            candidate_ids = list(agg.keys())
            candidate_texts = [final_id_to_text.get(cid, "") for cid in candidate_ids]
            merged_emb = encode_texts_fn(model, candidate_texts, batch_size=config.batch_size)
            q_vec = query_embeddings[i : i + 1]
            merged_sim = np.dot(q_vec, merged_emb.T).flatten()

            best_raw_score_by_id = {cid: float(agg[cid]["best_raw_score"]) for cid in candidate_ids}
            normalized_raw = _minmax_normalize(best_raw_score_by_id)
            final_score_by_id: Dict[str, float] = {}
            best_raw_rank_by_id = {cid: int(agg[cid]["best_raw_rank"]) for cid in candidate_ids}

            for j, cid in enumerate(candidate_ids):
                score_val = float(merged_sim[j])
                if flags.raw_merge_score_floor:
                    score_val = max(score_val, float(normalized_raw.get(cid, 0.0)))
                if flags.raw_merge_coverage_bonus > 0:
                    merged_sources = merged_by_id.get(cid, {}).get("source_unit_ids", [cid])
                    denom = max(1, len(merged_sources))
                    coverage = len(agg[cid]["covered_sources"]) / denom
                    score_val += flags.raw_merge_coverage_bonus * coverage
                final_score_by_id[cid] = score_val

            initial_order = sorted(
                candidate_ids,
                key=lambda cid: (final_score_by_id[cid], -best_raw_rank_by_id[cid]),
                reverse=True,
            )
            if flags.raw_merge_rank_floor:
                ordered_ids, violations = _rank_deadline_order(
                    initial_order,
                    score_by_id=final_score_by_id,
                    deadline_by_id=best_raw_rank_by_id,
                )
            else:
                ordered_ids = initial_order
                violations = 0
            total_violations += violations

            ordered_ids = ordered_ids[:final_cutoff]
            ordered_scores = [float(final_score_by_id[cid]) for cid in ordered_ids]
            ordered_sources = [
                list(merged_by_id.get(cid, {}).get("source_unit_ids", [cid])) for cid in ordered_ids
            ]
            merged_ranked_lists.append(ordered_ids)
            merged_score_lists.append(ordered_scores)
            merged_source_lists.append(ordered_sources)

            raw_top_ids = set(admitted_ids[: max(config.top_k)])
            final_top_sources = set()
            for srcs in ordered_sources[: max(config.top_k)]:
                final_top_sources.update(srcs)
            raw_top_missing = len([rid for rid in raw_top_ids if rid not in final_top_sources])
            total_raw_top_missing += raw_top_missing
            per_query_diag.append({
                "query_id": grounded_queries[i].get("id", ""),
                "admitted_raw_count": raw_limit,
                "merged_candidate_count": len(candidate_ids),
                "monotonic_rank_violations": violations,
                "raw_top_missing_in_final_topk": raw_top_missing,
                "best_raw_rank_by_merged_id": best_raw_rank_by_id,
            })

        ranked_lists = merged_ranked_lists
        score_lists = merged_score_lists
        ranked_source_id_lists = merged_source_lists
        raw_merge_diagnostics = {
            "enabled": True,
            "monotonic_rank_violations_total": total_violations,
            "raw_top_missing_in_final_topk_total": total_raw_top_missing,
            "per_query": per_query_diag,
        }
        logger.info(
            "Raw-first merge-rerank enabled: queries=%d total_violations=%d raw_top_missing_total=%d",
            len(grounded_queries),
            total_violations,
            total_raw_top_missing,
        )

    if flags.co_retrieval_expand:
        topic_to_ids: Dict[str, List[str]] = {}
        for c in corpus:
            tags = c.get("topic_tags", [])
            uid = c.get("id", "")
            if uid:
                for t in tags:
                    if t not in topic_to_ids:
                        topic_to_ids[t] = []
                    topic_to_ids[t].append(uid)
        for i in range(len(grounded_queries)):
            seen = set(ranked_lists[i])
            added = 0
            total_cap = max(0, expansion_cfg.crossref_expand_total_cap)
            for cid in ranked_lists[i][:max_k]:
                if added >= total_cap:
                    break
                u = next((c for c in corpus if c.get("id") == cid), None)
                if not u:
                    continue
                for hint in u.get("co_retrieval_hints", []):
                    if added >= total_cap:
                        break
                    rt = hint.get("related_topic", "")
                    per_hit = max(0, expansion_cfg.crossref_expand_per_hit)
                    for hid in topic_to_ids.get(rt, [])[:5]:
                        if added >= total_cap or per_hit <= 0:
                            break
                        if hid not in seen:
                            seen.add(hid)
                            ranked_lists[i].append(hid)
                            score_lists[i].append(0.0)
                            added += 1
                            per_hit -= 1

    ranked_lists, score_lists, pairing_payload = apply_post_retrieval_expansion(
        ranked_lists=ranked_lists,
        score_lists=score_lists,
        grounded_queries=grounded_queries,
        crossref_sidecar=crossref_sidecar,
        pairing_edges=pairing_edges,
        config=expansion_cfg,
    )

    boost = flags.unit_type_boost
    if boost > 0:
        apply_unit_type_boost_fn(ranked_lists, score_lists, corpus, grounded_queries, boost)

    # Diagnostic: rerank tail segment (positions prefix_lock_n+1..admission_cutoff), then enforce prefix lock.
    if use_qe and qe_fusion_mode == "only_add" and qe_fusion_debug is not None and tail_rerank != "none":
        from retrieval_lab.query_enhancement.multi_query import lexical_rerank_tail_segment

        locked_prefixes = [
            (d.get("baseline_topN", []) or [])[:prefix_lock_n]
            for d in qe_fusion_debug
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
                query_texts=query_texts_stage1,
                id_to_text=final_id_to_text,
                locked_prefixes=locked_prefixes,
                admission_cutoff=admission_cutoff_eff,
                rerank_window=tail_rerank_window,
                eligible=eligible,
            )
        elif tail_rerank in ("cross_encoder", "cascade"):
            # Optional cascade: lexical first, then cross-encoder only for remaining failures (eval-only).
            if tail_rerank == "cascade":
                ranked_lists, score_lists = lexical_rerank_tail_segment(
                    ranked_lists=ranked_lists,
                    score_lists=score_lists,
                    query_texts=query_texts_stage1,
                    id_to_text=final_id_to_text,
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
                tail_candidates = [{"chunk_id": cid, "text": final_id_to_text.get(cid, "")} for cid in tail_rerank_ids]
                q_text = query_texts_stage1[i] if i < len(query_texts_stage1) else (grounded_queries[i].get("question") or "")
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
    if use_qe and qe_fusion_mode == "only_add" and qe_fusion_debug is not None:
        from retrieval_lab.query_enhancement.multi_query import lock_prefix

        locked_prefixes = [
            (d.get("baseline_topN", []) or [])[:prefix_lock_n]
            for d in qe_fusion_debug
        ]
        # If a downstream stage promoted IDs (e.g., raw-first merge-rerank), map raw locked IDs
        # to their merged candidate IDs when possible.
        if ranked_source_id_lists is not None:
            mapped: List[List[str]] = []
            for i in range(len(locked_prefixes)):
                raw_locked = locked_prefixes[i] or []
                # ranked_source_id_lists[i][pos] = list of source ids covered by candidate at ranked_lists[i][pos]
                src_lists = ranked_source_id_lists[i] if i < len(ranked_source_id_lists) else []
                cand_ids = ranked_lists[i] if i < len(ranked_lists) else []
                raw_to_cand: Dict[str, str] = {}
                for cid, srcs in zip(cand_ids, src_lists):
                    for src in (srcs or []):
                        if src not in raw_to_cand:
                            raw_to_cand[src] = cid
                mapped_locked = [raw_to_cand[r] for r in raw_locked if r in raw_to_cand]
                mapped.append(mapped_locked if mapped_locked else raw_locked)
            locked_prefixes = mapped
        if locked_prefixes and len(locked_prefixes) == len(ranked_lists):
            ranked_lists, score_lists = lock_prefix(
                ranked_lists=ranked_lists,
                score_lists=score_lists,
                locked_prefixes=locked_prefixes,
            )

    if ranked_source_id_lists is None:
        ranked_source_id_lists = [
            [[cid] + id_to_source_ids.get(cid, []) for cid in ranked_lists[i]]
            for i in range(len(ranked_lists))
        ]

    result = {
        "grounded_queries": grounded_queries,
        "all_grounding_audit": all_grounding_audit,
        "query_embeddings": query_embeddings,
        "ranked_lists": ranked_lists,
        "score_lists": score_lists,
        "ranked_source_id_lists": ranked_source_id_lists,
        "final_id_to_text": final_id_to_text,
        "raw_merge_diagnostics": raw_merge_diagnostics,
        "pairing_payload": pairing_payload,
        "scoring_time_sec": time.perf_counter() - t1,
    }
    if qe_expansion_logs is not None:
        result["qe_expansion_logs"] = qe_expansion_logs
    if qe_fusion_debug is not None:
        result["qe_fusion_debug"] = qe_fusion_debug
    return result


def _build_metrics_and_reviews(
    *,
    model_id: str,
    config: Any,
    flags: Any,
    corpus: List[Dict[str, Any]],
    corpus_ids: List[str],
    corpus_embeddings: np.ndarray,
    id_to_source_ids: Dict[str, List[str]],
    id_to_text: Dict[str, str],
    id_to_index: Dict[str, int],
    grounded_queries: List[Dict[str, Any]],
    query_embeddings: np.ndarray,
    ranked_lists: List[List[str]],
    score_lists: List[List[float]],
    ranked_source_id_lists: Optional[List[List[List[str]]]],
    embedding_time_sec: float,
    scoring_time_sec: float,
    expanded_text_fn: Any,
    final_id_to_text: Optional[Dict[str, str]] = None,
    raw_merge_diagnostics: Optional[Dict[str, Any]] = None,
    qe_fusion_debug: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Score retrieval outputs and assemble query-review artifacts."""
    text_map = final_id_to_text or id_to_text
    source_lists = ranked_source_id_lists or [
        [[cid] + id_to_source_ids.get(cid, []) for cid in ranked_lists[i]]
        for i in range(len(ranked_lists))
    ]
    metrics = score_retrieval(
        grounded_queries,
        ranked_lists,
        score_lists,
        config.top_k,
        ranked_source_id_lists=source_lists,
        query_embeddings=query_embeddings,
        corpus_embeddings=corpus_embeddings,
        corpus_ids=corpus_ids,
    )
    use_expanded = flags.expand_context
    pf_policy = ParentFetchConfig(
        depth=flags.parent_fetch_depth,
        char_cap=flags.parent_fetch_cap,
        enabled=flags.parent_fetch_enabled,
    )
    query_reviews = []
    for i, q in enumerate(grounded_queries):
        pq = metrics.per_query[i]
        retrieved = []
        for r, (cid, sc) in enumerate(zip(ranked_lists[i], score_lists[i]), start=1):
            text = (
                expanded_text_fn(corpus, id_to_index, cid, flags.expand_context_n)
                if use_expanded
                else text_map.get(cid, "")
            )
            retrieved.append({
                "rank": r,
                "chunk_id": cid,
                "score": round(sc, 4),
                "text": text,
            })
        if pf_policy.enabled:
            from retrieval_lab.parent_fetch import fetch_parent_context
            retrieved = fetch_parent_context(retrieved, corpus, pf_policy)
        review_entry: Dict[str, Any] = {
            "query_id": q.get("id", ""),
            "question": q.get("question", ""),
            "expected_answer_summary": q.get("expected_answer_summary", ""),
            "gold_unit_ids": list(q.get("gold_unit_ids") or []),
            "first_gold_rank": pq.get("first_gold_rank"),
            "failure_type": pq.get("failure_type", ""),
            "retrieved": retrieved,
        }
        if qe_fusion_debug is not None and i < len(qe_fusion_debug):
            gold = set(q.get("gold_unit_ids") or [])
            baseline_top = set((qe_fusion_debug[i].get("baseline_topN") or []))
            final_admitted = set((qe_fusion_debug[i].get("final_admitted") or []))
            qe_fusion_debug[i]["baseline_gold_in_candidates"] = bool(gold & baseline_top)
            qe_fusion_debug[i]["new_gold_added_by_variants"] = sorted(list((gold & final_admitted) - baseline_top))
            review_entry["qe_fusion"] = qe_fusion_debug[i]
        query_reviews.append(review_entry)
        top3_ids = ranked_lists[i][:3]
        top3_scores = [round(s, 3) for s in score_lists[i][:3]]
        logger.info(
            "[%s] query_id=%s top3=%s scores=%s first_gold_rank=%s failure_type=%s",
            model_id,
            q.get("id", ""),
            top3_ids,
            top3_scores,
            pq.get("first_gold_rank"),
            pq.get("failure_type", ""),
        )

    out = {
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
            "embedding_time_sec": embedding_time_sec,
            "scoring_time_sec": scoring_time_sec,
        },
        "per_query": metrics.per_query,
        "query_reviews": query_reviews,
    }
    if raw_merge_diagnostics:
        out["results"]["raw_merge_rerank_diagnostics"] = raw_merge_diagnostics
    return out


def run_dense_mode(
    *,
    config: Any,
    flags: Any,
    expansion_cfg: Any,
    eval_only_run_id: Optional[str],
    run_id: str,
    output_dir: Path,
    corpus: List[Dict[str, Any]],
    corpus_ids: List[str],
    corpus_texts: List[str],
    id_to_source_ids: Dict[str, List[str]],
    flat_queries: List[Dict[str, Any]],
    grounded_queries: List[Dict[str, Any]],
    use_semantic_grounding: bool,
    initial_grounding_audit: List[Dict[str, Any]],
    crossref_sidecar: Dict[str, List[str]],
    pairing_edges: Dict[str, Any],
    use_dual_list_fusion: bool,
    family_corpus: Optional[List[Dict[str, Any]]],
    family_corpus_ids: List[str],
    family_id_to_anchor_unit_id: Dict[str, str],
    run_id_family: Optional[str],
    load_model_fn: Any,
    encode_texts_fn: Any,
    model_registry: Dict[str, Any],
    trust_remote_models: Any,
    build_expanded_texts_fn: Any,
    expanded_text_fn: Any,
    apply_unit_type_boost_fn: Any,
    qe_profile: Any = None,
    qe_mode: str = "none",
    qe_fusion_mode: str = "only_add",
    qe_only_add: Any = None,
    qe_enhance_query_ids: Any = None,
    qe_cache: Any = None,
) -> Dict[str, Any]:
    """Run dense/hybrid retrieval for all configured embedding models."""
    results_by_model: Dict[str, Dict[str, Any]] = {}
    per_query_by_model: Dict[str, List[Dict[str, Any]]] = {}
    retrieved_chunks_by_model: Dict[str, List[Dict[str, Any]]] = {}
    all_grounding_audit: List[Dict[str, Any]] = initial_grounding_audit.copy()
    pairing_instrumentation_by_model: Dict[str, Any] = {}
    mongo_uri = config.mongo_uri
    id_to_text = {u["id"]: u.get("text", "") for u in corpus}
    id_to_index = {u["id"]: idx for idx, u in enumerate(corpus)}

    bm25_ranked_lists: Optional[List[List[str]]] = None
    if config.retrieval_mode in ("hybrid", "hybrid+rerank"):
        from retrieval_lab.sparse_retrieval import build_bm25_index, bm25_rank
        logger.info("Hybrid mode: building BM25 index for RRF fusion")
        bm25 = build_bm25_index(
            corpus_texts,
            tokenizer_mode=getattr(config, "bm25_tokenizer_mode", "basic"),
            k1=float(getattr(config, "bm25_k1", 1.5)),
            b=float(getattr(config, "bm25_b", 0.75)),
        )
        max_k_hybrid = max(
            max(config.top_k),
            int(getattr(config, "stage1_admission_k", 100))
            if bool(getattr(config, "two_stage_retrieval", False))
            else max(config.top_k),
        )
        bm25_ranked_lists, _ = bm25_rank(
            bm25,
            corpus_ids,
            grounded_queries,
            max_k_hybrid,
            tokenizer_mode=getattr(config, "bm25_tokenizer_mode", "basic"),
            query_mode=getattr(config, "bm25_query_mode", "question_only"),
            question_weight=int(getattr(config, "bm25_query_weight_question", 1)),
            summary_weight=int(getattr(config, "bm25_query_weight_summary", 1)),
        )

    for model_id in config.models:
        if model_id not in model_registry:
            logger.warning("Model %s not in registry; using as model_name for SentenceTransformer", model_id)
            model_name = model_id
        else:
            model_name = model_registry[model_id].model_name
        logger.info("Processing model: %s (%s)", model_id, model_name)

        trust_remote = config.trust_remote_code or (model_id in trust_remote_models)
        model = load_model_fn(model_name, trust_remote_code=trust_remote)

        embed_out = _load_or_compute_corpus_embeddings(
            config=config,
            model_id=model_id,
            model=model,
            encode_texts_fn=encode_texts_fn,
            run_id=run_id,
            corpus_ids=corpus_ids,
            corpus_texts=corpus_texts,
            output_dir=output_dir,
            eval_only_run_id=eval_only_run_id,
            mongo_uri=mongo_uri,
        )
        corpus_embeddings = embed_out["corpus_embeddings"]
        embedding_time_sec = embed_out["embedding_time_sec"]

        family_embeddings = _load_or_compute_family_embeddings(
            config=config,
            model_id=model_id,
            model=model,
            encode_texts_fn=encode_texts_fn,
            eval_only_run_id=eval_only_run_id,
            mongo_uri=mongo_uri,
            output_dir=output_dir,
            use_dual_list_fusion=use_dual_list_fusion,
            family_corpus=family_corpus,
            family_corpus_ids=family_corpus_ids,
            run_id_family=run_id_family,
        )
        rank_out = _run_ranking_pipeline(
            config=config,
            flags=flags,
            expansion_cfg=expansion_cfg,
            model_id=model_id,
            model=model,
            encode_texts_fn=encode_texts_fn,
            corpus=corpus,
            corpus_ids=corpus_ids,
            corpus_embeddings=corpus_embeddings,
            id_to_text=id_to_text,
            id_to_index=id_to_index,
            id_to_source_ids=id_to_source_ids,
            grounded_queries=grounded_queries,
            flat_queries=flat_queries,
            use_semantic_grounding=use_semantic_grounding,
            all_grounding_audit=all_grounding_audit,
            bm25_ranked_lists=bm25_ranked_lists,
            use_dual_list_fusion=use_dual_list_fusion,
            family_embeddings=family_embeddings,
            family_corpus_ids=family_corpus_ids,
            family_id_to_anchor_unit_id=family_id_to_anchor_unit_id,
            crossref_sidecar=crossref_sidecar,
            pairing_edges=pairing_edges,
            build_expanded_texts_fn=build_expanded_texts_fn,
            apply_unit_type_boost_fn=apply_unit_type_boost_fn,
            qe_profile=qe_profile,
            qe_mode=qe_mode,
            qe_fusion_mode=qe_fusion_mode,
            qe_only_add=qe_only_add,
            qe_enhance_query_ids=qe_enhance_query_ids,
            qe_cache=qe_cache,
        )
        grounded_queries = rank_out["grounded_queries"]
        all_grounding_audit = rank_out["all_grounding_audit"]
        if rank_out.get("pairing_payload"):
            pairing_instrumentation_by_model[model_id] = rank_out["pairing_payload"]

        model_out = _build_metrics_and_reviews(
            model_id=model_id,
            config=config,
            flags=flags,
            corpus=corpus,
            corpus_ids=corpus_ids,
            corpus_embeddings=corpus_embeddings,
            id_to_source_ids=id_to_source_ids,
            id_to_text=id_to_text,
            id_to_index=id_to_index,
            grounded_queries=grounded_queries,
            query_embeddings=rank_out["query_embeddings"],
            ranked_lists=rank_out["ranked_lists"],
            score_lists=rank_out["score_lists"],
            ranked_source_id_lists=rank_out.get("ranked_source_id_lists"),
            embedding_time_sec=embedding_time_sec,
            scoring_time_sec=rank_out["scoring_time_sec"],
            expanded_text_fn=expanded_text_fn,
            final_id_to_text=rank_out.get("final_id_to_text"),
            raw_merge_diagnostics=rank_out.get("raw_merge_diagnostics"),
            qe_fusion_debug=rank_out.get("qe_fusion_debug"),
        )
        retrieved_chunks_by_model[model_id] = model_out["query_reviews"]
        logger.info("Model %s: retrieval done for %d queries; review in retrieved_chunks.json", model_id, len(grounded_queries))
        results_by_model[model_id] = model_out["results"]
        per_query_by_model[model_id] = model_out["per_query"]

    return {
        "results_by_model": results_by_model,
        "per_query_by_model": per_query_by_model,
        "retrieved_chunks_by_model": retrieved_chunks_by_model,
        "all_grounding_audit": all_grounding_audit,
        "pairing_instrumentation_by_model": pairing_instrumentation_by_model,
    }

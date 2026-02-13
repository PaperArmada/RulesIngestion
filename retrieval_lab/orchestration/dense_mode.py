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
from retrieval_lab.store import (
    fetch_cached_embeddings,
    save_cached_embeddings,
    save_embedding_run_metadata,
)

logger = logging.getLogger(__name__)


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
    cached = fetch_cached_embeddings(run_id, model_id, mongo_uri) if (eval_only_run_id or config.reuse_embeddings) else None
    if cached and len(cached) == len(corpus_ids):
        id_to_emb = {r["chunk_id"]: r["embedding"] for r in cached}
        corpus_embeddings = np.array([id_to_emb[uid] for uid in corpus_ids], dtype=np.float32)
        logger.info("Loaded %d embeddings from MongoDB cache", len(corpus_embeddings))
    else:
        embed_dir = Path(config.output_dir) / f"embed_{run_id}"
        npy_path = embed_dir / "embeddings" / f"{model_id}_corpus.npy"
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
                        npy_path = subdir / "embeddings" / f"{model_id}_corpus.npy"
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
            np.save(output_dir / "embeddings" / f"{model_id}_corpus.npy", corpus_embeddings)
            if model_id == config.models[0]:
                (output_dir / "embeddings").mkdir(exist_ok=True)
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
    cached_f = fetch_cached_embeddings(run_id_family, model_id, mongo_uri) if (eval_only_run_id or config.reuse_embeddings) else None
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
    np.save(output_dir / "embeddings" / f"{model_id}_family.npy", family_embeddings)
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

    query_texts = [q.get("question") or q.get("expected_answer_summary") or "" for q in grounded_queries]
    query_embeddings = encode_texts_fn(model, query_texts, batch_size=config.batch_size)
    t1 = time.perf_counter()
    q_norm = query_embeddings / (np.linalg.norm(query_embeddings, axis=1, keepdims=True) + 1e-9)
    max_k = max(config.top_k)
    ranked_lists = []
    score_lists = []

    if use_dual_list_fusion and family_embeddings is not None:
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
        c_norm = corpus_embeddings / (np.linalg.norm(corpus_embeddings, axis=1, keepdims=True) + 1e-9)
        sim = np.dot(q_norm, c_norm.T)
        for i in range(len(grounded_queries)):
            row = sim[i]
            top_indices = np.argsort(row)[::-1][:max_k]
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
            new_order = np.argsort(scores)[::-1]
            ranked_lists[i] = [center_ids[j] for j in new_order]
            score_lists[i] = [float(scores[j]) for j in new_order]

    if config.retrieval_mode in ("hybrid", "hybrid+rerank") and bm25_ranked_lists is not None:
        from retrieval_lab.sparse_retrieval import reciprocal_rank_fusion
        policy = config.get_policy(config.document_id)
        rrf_k = policy.fusion_k
        rankings_per_query = [
            [ranked_lists[i], bm25_ranked_lists[i]]
            for i in range(len(grounded_queries))
        ]
        ranked_lists, score_lists = reciprocal_rank_fusion(
            rankings_per_query, k=rrf_k, max_k=max_k
        )
        logger.info("Fused dense + BM25 with RRF (k=%d) for model %s", rrf_k, model_id)

    reranker_model = getattr(config, "reranker", None)
    if config.retrieval_mode == "hybrid+rerank" and not reranker_model:
        reranker_model = "cross-encoder/ms-marco-MiniLM-L6-v2"
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

    return {
        "grounded_queries": grounded_queries,
        "all_grounding_audit": all_grounding_audit,
        "query_embeddings": query_embeddings,
        "ranked_lists": ranked_lists,
        "score_lists": score_lists,
        "pairing_payload": pairing_payload,
        "scoring_time_sec": time.perf_counter() - t1,
    }


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
    embedding_time_sec: float,
    scoring_time_sec: float,
    expanded_text_fn: Any,
) -> Dict[str, Any]:
    """Score retrieval outputs and assemble query-review artifacts."""
    metrics = score_retrieval(
        grounded_queries,
        ranked_lists,
        score_lists,
        config.top_k,
        ranked_source_id_lists=[
            [id_to_source_ids.get(cid, [cid]) for cid in ranked_lists[i]]
            for i in range(len(ranked_lists))
        ],
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
                else id_to_text.get(cid, "")
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
        query_reviews.append({
            "query_id": q.get("id", ""),
            "question": q.get("question", ""),
            "expected_answer_summary": q.get("expected_answer_summary", ""),
            "gold_unit_ids": list(q.get("gold_unit_ids") or []),
            "first_gold_rank": pq.get("first_gold_rank"),
            "failure_type": pq.get("failure_type", ""),
            "retrieved": retrieved,
        })
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

    return {
        "results": {
            "recall_at_k": metrics.recall_at_k,
            "hit_at_k": metrics.hit_at_k,
            "full_set_hit_at_k": metrics.full_set_hit_at_k,
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
        bm25 = build_bm25_index(corpus_texts)
        max_k_hybrid = max(config.top_k)
        bm25_ranked_lists, _ = bm25_rank(
            bm25, corpus_ids, grounded_queries, max_k_hybrid
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
            embedding_time_sec=embedding_time_sec,
            scoring_time_sec=rank_out["scoring_time_sec"],
            expanded_text_fn=expanded_text_fn,
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

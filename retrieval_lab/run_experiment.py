"""
CLI entry point: load config, load substrate, ground gold, embed per model, score, persist, report.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

# Bootstrap paths for model_registry (RulesIngestion Archive) and benchmark_store (DungeonMindServer)
_SCRIPT_DIR = Path(__file__).resolve().parent
_RULES_INGESTION_ROOT = _SCRIPT_DIR.parent
_REPO_ROOT = _RULES_INGESTION_ROOT.parent
_ARCHIVE_MARK_I = _RULES_INGESTION_ROOT / "Archive" / "Mark I"
_DUNGEONMIND_SERVER = _REPO_ROOT / "DungeonMindServer"
if str(_ARCHIVE_MARK_I) not in sys.path:
    sys.path.insert(0, str(_ARCHIVE_MARK_I))
if _DUNGEONMIND_SERVER.exists() and str(_DUNGEONMIND_SERVER) not in sys.path:
    sys.path.insert(0, str(_DUNGEONMIND_SERVER))

from retrieval_lab.config import ExperimentConfig
from retrieval_lab.gold_grounding import (
    flatten_query_batches,
    ground_queries_corpus_semantic,
    ground_queries_page_anchored,
)
from retrieval_lab.metrics import score_retrieval
from retrieval_lab.projection import build_clause_family_projection
from retrieval_lab.report import write_report_artifacts
from retrieval_lab.crossref_sidecar import (
    build_crossref_sidecar,
    build_minimal_a_prime_hints,
    expand_ranked_with_sidecar,
)
from retrieval_lab.dual_list_fusion import fuse_dual_list
from retrieval_lab.pairing_edges import (
    build_dependency_pairing_edges,
    expand_ranked_with_pairing_edges,
)
from retrieval_lab.store import (
    fetch_cached_embeddings,
    save_cached_embeddings,
    save_embedding_run_metadata,
    save_experiment,
    substrate_run_id,
)
from retrieval_lab.substrate_loader import (
    load_evidence_units,
    merge_enrichments_into_corpus,
    merge_units_by_heading,
    units_by_page,
)
from retrieval_lab.config import ParentFetchConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Models that require trust_remote_code=True when loading (HuggingFace custom code).
MODELS_REQUIRING_TRUST_REMOTE_CODE = frozenset({
    "nomic-embed-text-v2",
    "bge-m3",
    "gte-multilingual-base",
})


def _load_model_registry():
    try:
        from evaluation.model_registry import MODEL_REGISTRY, load_model, encode_texts
        return load_model, encode_texts, MODEL_REGISTRY
    except ImportError as e:
        logger.error("Failed to import evaluation.model_registry. Ensure Archive/Mark I/evaluation is on path: %s", e)
        raise


def _expanded_text(corpus: List[Dict[str, Any]], id_to_index: Dict[str, int], center_id: str, n: int) -> str:
    """Build one expanded chunk: prev_n + center + next_n in document order."""
    idx = id_to_index.get(center_id)
    if idx is None:
        return next((c.get("text", "") for c in corpus if c.get("id") == center_id), "")
    start = max(0, idx - n)
    end = min(len(corpus), idx + n + 1)
    parts = [corpus[j].get("text", "").strip() for j in range(start, end) if corpus[j].get("text")]
    return "\n\n".join(p for p in parts if p)


def _build_expanded_texts(
    corpus: List[Dict[str, Any]],
    id_to_index: Dict[str, int],
    center_ids: List[str],
    n: int,
) -> List[str]:
    """Expanded text for each center_id (same order)."""
    return [_expanded_text(corpus, id_to_index, cid, n) for cid in center_ids]


def _apply_unit_type_boost(
    ranked_lists: List[List[str]],
    score_lists: List[List[float]],
    corpus: List[Dict[str, Any]],
    grounded_queries: List[Dict[str, Any]],
    boost: float,
) -> None:
    """R9: Apply soft boost when query-type heuristic matches unit_type. Modifies score_lists in place."""
    if boost <= 0:
        return
    id_to_unit_type: Dict[str, str] = {c["id"]: c.get("unit_type", "unknown") for c in corpus}
    table_list_types = frozenset({"table", "list"})
    for i, q in enumerate(grounded_queries):
        text = (q.get("question") or q.get("expected_answer_summary") or "").lower()
        prefer_table_list = any(k in text for k in ("table", "list of", "requirements"))
        prefer_prose = any(k in text for k in ("how does", "explain"))
        for j, cid in enumerate(ranked_lists[i]):
            ut = id_to_unit_type.get(cid, "unknown")
            if prefer_table_list and ut in table_list_types:
                score_lists[i][j] += boost
            elif prefer_prose and ut not in table_list_types:
                score_lists[i][j] += boost
        # Re-sort by score descending
        pairs = list(zip(ranked_lists[i], score_lists[i]))
        pairs.sort(key=lambda x: x[1], reverse=True)
        ranked_lists[i] = [p[0] for p in pairs]
        score_lists[i] = [p[1] for p in pairs]


def _run_embed_only(config: ExperimentConfig) -> str:
    """Embed substrate once per model; save to MongoDB and disk. No queries or report."""
    config.resolve_paths(Path.cwd())
    config.validate(embed_only=True)
    load_model_fn, encode_texts_fn, MODEL_REGISTRY = _load_model_registry()
    logger.info("Loading substrate from %s", config.substrate_path)
    corpus = load_evidence_units(
        config.substrate_path,
        config.document_id,
        min_chars=getattr(config, "min_chars", None),
    )
    if not corpus:
        raise ValueError("Corpus is empty; no EvidenceUnits found.")
    if getattr(config, "merge_chunks", False):
        corpus = merge_units_by_heading(
            corpus,
            max_chars=getattr(config, "merge_max_chars", 2000),
        )
    corpus = merge_enrichments_into_corpus(corpus, config.substrate_path)
    corpus_ids = [c["id"] for c in corpus]
    corpus_texts = [c["text"] for c in corpus]
    run_id = substrate_run_id(config.document_id, corpus_ids, config.substrate_version)
    logger.info("Corpus: %d units, run_id=%s", len(corpus), run_id)
    mongo_uri = config.mongo_uri
    output_dir = Path(config.output_dir) / f"embed_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "embeddings").mkdir(exist_ok=True)
    for model_id in config.models:
        model_name = MODEL_REGISTRY[model_id].model_name if model_id in MODEL_REGISTRY else model_id
        logger.info("Embedding model: %s (%s)", model_id, model_name)
        # In embed-only we always compute (no cache read) so we never block on MongoDB when it's down.
        trust_remote = config.trust_remote_code or (model_id in MODELS_REQUIRING_TRUST_REMOTE_CODE)
        model = load_model_fn(model_name, trust_remote_code=trust_remote)
        corpus_embeddings = encode_texts_fn(model, corpus_texts, batch_size=config.batch_size)
        records = [
            {"run_id": run_id, "model_id": model_id, "chunk_id": uid, "embedding": corpus_embeddings[i].tolist()}
            for i, uid in enumerate(corpus_ids)
        ]
        save_cached_embeddings(run_id, model_id, records, mongo_uri, clear_existing=True)
        save_embedding_run_metadata(run_id, model_id, len(corpus_ids), mongo_uri)
        np.save(output_dir / "embeddings" / f"{model_id}_corpus.npy", corpus_embeddings)
    index_path = output_dir / "embeddings" / "corpus_index.json"
    index_path.write_text(
        json.dumps(
            {"run_id": run_id, "substrate_version": config.substrate_version, "unit_id_to_index": {uid: i for i, uid in enumerate(corpus_ids)}},
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("Embed-only complete. run_id=%s", run_id)
    return run_id


def _run_experiment(config: ExperimentConfig, eval_only_run_id: Optional[str] = None) -> str:
    """Full eval: load or use existing embeddings, run queries, score, report."""
    config.resolve_paths(Path.cwd())
    embed_only = False
    eval_only = eval_only_run_id is not None
    config.validate(embed_only=embed_only, eval_only=eval_only)
    retrieval_mode = config.retrieval_mode

    # Load substrate (needed for corpus order and grounding)
    logger.info("Loading substrate from %s", config.substrate_path)
    corpus = load_evidence_units(
        config.substrate_path,
        config.document_id,
        min_chars=getattr(config, "min_chars", None),
    )
    if not corpus:
        raise ValueError("Corpus is empty; no EvidenceUnits found.")
    if getattr(config, "merge_chunks", False):
        corpus = merge_units_by_heading(
            corpus,
            max_chars=getattr(config, "merge_max_chars", 2000),
        )
    corpus = merge_enrichments_into_corpus(corpus, config.substrate_path)

    # H7: Minimal deterministic A′ hints generated in-memory when enrichments are absent.
    if getattr(config, "a_prime_generate_minimal", False):
        generated_hints = build_minimal_a_prime_hints(corpus)
        for unit in corpus:
            uid = unit.get("id", "")
            if uid in generated_hints:
                if not unit.get("topic_tags"):
                    unit["topic_tags"] = generated_hints[uid].get("topic_tags", [])
                if not unit.get("co_retrieval_hints"):
                    unit["co_retrieval_hints"] = generated_hints[uid].get("co_retrieval_hints", [])

    # Keep canonical corpus for grounding and source-id scoring.
    canonical_corpus = corpus
    grounding_units_by_page_map = units_by_page(canonical_corpus)

    # A1: Retrieval-only clause-family projection substrate (skip when A1.2 dual-list fusion is used).
    use_dual_list_fusion = getattr(config, "dual_list_fusion", False)
    if getattr(config, "clause_family_projection", False) and not use_dual_list_fusion:
        corpus = build_clause_family_projection(
            canonical_corpus,
            window=getattr(config, "clause_family_window", 2),
            max_units=getattr(config, "clause_family_max_units", 6),
            direction=getattr(config, "clause_family_direction", "symmetric"),
        )
        logger.info(
            "Clause-family projection enabled: %d canonical units -> %d projection units (window=%d max_units=%d direction=%s)",
            len(canonical_corpus),
            len(corpus),
            getattr(config, "clause_family_window", 2),
            getattr(config, "clause_family_max_units", 6),
            getattr(config, "clause_family_direction", "symmetric"),
        )

    corpus_ids = [c["id"] for c in corpus]
    corpus_texts = [c["text"] for c in corpus]
    id_to_source_ids: Dict[str, List[str]] = {
        c["id"]: list(c.get("source_unit_ids", [c["id"]])) for c in corpus
    }
    # run_id needed for dual-list run_id_family; set before A1.2 block.
    if eval_only_run_id:
        run_id = eval_only_run_id
        logger.info("Eval-only: using run_id=%s (no embedding)", run_id)
    else:
        run_id = substrate_run_id(config.document_id, corpus_ids, config.substrate_version)
    logger.info("Corpus: %d units, run_id=%s", len(corpus), run_id)

    # A1.2 dual-list fusion: build family projection and run_id for Index_F.
    family_corpus: Optional[List[Dict[str, Any]]] = None
    family_corpus_ids: List[str] = []
    family_id_to_anchor_unit_id: Dict[str, str] = {}
    run_id_family: Optional[str] = None
    if use_dual_list_fusion:
        family_corpus = build_clause_family_projection(
            canonical_corpus,
            window=getattr(config, "dual_list_family_window", 3),
            max_units=getattr(config, "dual_list_family_max_units", 6),
            direction=getattr(config, "dual_list_family_direction", "symmetric"),
        )
        family_corpus_ids = [c["id"] for c in family_corpus]
        for c in family_corpus:
            anchor = c.get("projection_anchor_id") or (
                (c.get("source_unit_ids") or [c["id"]])[0] if c.get("source_unit_ids") else c["id"]
            )
            family_id_to_anchor_unit_id[c["id"]] = anchor
        run_id_family = run_id + f"_family_w{getattr(config, 'dual_list_family_window', 3)}_m{getattr(config, 'dual_list_family_max_units', 6)}"
        logger.info(
            "A1.2 dual-list fusion: %d canonical, %d family; run_id_family=%s",
            len(corpus_ids),
            len(family_corpus_ids),
            run_id_family,
        )

    # Load and flatten queries
    flat_queries, _ = flatten_query_batches(config.query_batches)
    if not flat_queries:
        raise ValueError("No queries loaded from query_batches.")
    logger.info("Loaded %d queries", len(flat_queries))

    # Determine grounding mode: if all source_page are null, use corpus-wide semantic per model
    use_semantic_grounding = all(
        (q.get("source_page") is None) and not (q.get("gold_unit_ids"))
        for q in flat_queries
    )
    grounded_queries: List[Dict[str, Any]] = []
    grounding_audit: List[Dict[str, Any]] = []
    if not use_semantic_grounding:
        grounded_queries, grounding_audit = ground_queries_page_anchored(
            flat_queries,
            grounding_units_by_page_map,
            threshold=config.gold_jaccard_threshold,
        )
        logger.info("Gold grounding: page-anchored; grounded %d queries", sum(1 for q in grounded_queries if q.get("gold_unit_ids")))
    else:
        if retrieval_mode == "bm25":
            raise ValueError("BM25 mode requires gold_unit_ids or source_page; semantic grounding requires embeddings.")
        logger.info("Gold grounding: corpus-wide semantic (per model)")

    experiment_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    experiment_id = f"{config.experiment_name}_{experiment_ts}"
    output_dir = Path(config.output_dir) / experiment_id
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "embeddings").mkdir(exist_ok=True)

    results_by_model: Dict[str, Dict[str, Any]] = {}
    per_query_by_model: Dict[str, List[Dict[str, Any]]] = {}
    retrieved_chunks_by_model: Dict[str, List[Dict[str, Any]]] = {}
    all_grounding_audit: List[Dict[str, Any]] = grounding_audit.copy()
    mongo_uri = config.mongo_uri
    id_to_text = {u["id"]: u.get("text", "") for u in corpus}
    id_to_index = {u["id"]: idx for idx, u in enumerate(corpus)}
    crossref_sidecar: Dict[str, List[str]] = {}
    if getattr(config, "crossref_sidecar_expand", False):
        crossref_sidecar = build_crossref_sidecar(corpus)
        logger.info("Crossref sidecar enabled: %d units with deterministic edges", len(crossref_sidecar))
    pairing_edges: Dict[str, List[tuple]] = {}
    if getattr(config, "dependency_pairing_expand", False):
        pairing_edges = build_dependency_pairing_edges(canonical_corpus)
        logger.info(
            "B1 dependency pairing enabled: %d units with delta/exception→base edges",
            len(pairing_edges),
        )

    if retrieval_mode == "bm25":
        if getattr(config, "expand_context", False):
            logger.warning("Expand context is not supported for BM25 mode; skipping.")
        from retrieval_lab.sparse_retrieval import build_bm25_index, bm25_rank

        t0 = time.perf_counter()
        bm25 = build_bm25_index(corpus_texts)
        max_k = max(config.top_k)
        ranked_lists, score_lists = bm25_rank(bm25, corpus_ids, grounded_queries, max_k)
        boost = getattr(config, "unit_type_boost", 0.0)
        if boost > 0:
            _apply_unit_type_boost(ranked_lists, score_lists, corpus, grounded_queries, boost)

        # B1: deterministic crossref sidecar expansion.
        if getattr(config, "crossref_sidecar_expand", False) and crossref_sidecar:
            for i in range(len(grounded_queries)):
                ranked_lists[i], score_lists[i], _ = expand_ranked_with_sidecar(
                    ranked_ids=ranked_lists[i],
                    score_list=score_lists[i],
                    sidecar=crossref_sidecar,
                    expand_top_k=getattr(config, "crossref_expand_top_k", 10),
                    expand_per_hit=getattr(config, "crossref_expand_per_hit", 2),
                    total_cap=getattr(config, "crossref_expand_total_cap", 20),
                )
        # B1 replacement: dependency pairing expansion (BM25 path).
        if getattr(config, "dependency_pairing_expand", False) and pairing_edges:
            emax = getattr(config, "dependency_pairing_emax", 6)
            for i in range(len(grounded_queries)):
                ranked_lists[i], score_lists[i], _ = expand_ranked_with_pairing_edges(
                    ranked_ids=ranked_lists[i],
                    score_list=score_lists[i],
                    pairing_edges=pairing_edges,
                    expand_top_k=getattr(config, "crossref_expand_top_k", 10),
                    Emax=emax,
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
            depth=getattr(config, "parent_fetch_depth", 1),
            char_cap=getattr(config, "parent_fetch_cap", 2000),
            enabled=getattr(config, "parent_fetch_enabled", False),
        )
        for i, q in enumerate(grounded_queries):
            pq = metrics.per_query[i]
            retrieved = []
            for r, (cid, sc) in enumerate(zip(ranked_lists[i], score_lists[i]), start=1):
                retrieved.append({
                    "rank": r,
                    "chunk_id": cid,
                    "score": round(sc, 4),
                    "text": id_to_text.get(cid, ""),
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
                "[bm25] query_id=%s top3=%s scores=%s first_gold_rank=%s failure_type=%s",
                q.get("id", ""),
                top3_ids,
                top3_scores,
                pq.get("first_gold_rank"),
                pq.get("failure_type", ""),
            )
        retrieved_chunks_by_model["bm25"] = query_reviews
        logger.info("Model bm25: retrieval done for %d queries; review in retrieved_chunks.json", len(grounded_queries))

        results_by_model["bm25"] = {
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
            "embedding_time_sec": 0.0,
            "scoring_time_sec": scoring_time_sec,
        }
        per_query_by_model["bm25"] = metrics.per_query
    else:
        load_model_fn, encode_texts_fn, MODEL_REGISTRY = _load_model_registry()

        bm25_ranked_lists: Optional[List[List[str]]] = None
        bm25_score_lists: Optional[List[List[float]]] = None
        if retrieval_mode in ("hybrid", "hybrid+rerank"):
            from retrieval_lab.sparse_retrieval import build_bm25_index, bm25_rank, reciprocal_rank_fusion
            logger.info("Hybrid mode: building BM25 index for RRF fusion")
            bm25 = build_bm25_index(corpus_texts)
            max_k_hybrid = max(config.top_k)
            bm25_ranked_lists, bm25_score_lists = bm25_rank(
                bm25, corpus_ids, grounded_queries, max_k_hybrid
            )

        for model_id in config.models:
            if model_id not in MODEL_REGISTRY:
                logger.warning("Model %s not in registry; using as model_name for SentenceTransformer", model_id)
                model_name = model_id
            else:
                model_name = MODEL_REGISTRY[model_id].model_name
            logger.info("Processing model: %s (%s)", model_id, model_name)

            # Load model once per model_id
            trust_remote = config.trust_remote_code or (model_id in MODELS_REQUIRING_TRUST_REMOTE_CODE)
            model = load_model_fn(model_name, trust_remote_code=trust_remote)

            family_embeddings = None  # Set when dual_list_fusion is enabled

            # Load or compute corpus embeddings (eval-only: must be cached from MongoDB or disk)
            t0 = time.perf_counter()
            cached = fetch_cached_embeddings(run_id, model_id, mongo_uri) if (eval_only_run_id or config.reuse_embeddings) else None
            if cached and len(cached) == len(corpus_ids):
                id_to_emb = {r["chunk_id"]: r["embedding"] for r in cached}
                corpus_embeddings = np.array([id_to_emb[uid] for uid in corpus_ids], dtype=np.float32)
                logger.info("Loaded %d embeddings from MongoDB cache", len(corpus_embeddings))
            else:
                # Eval-only fallback: load from disk. Try embed_{run_id} first, then any experiment dir with matching run_id.
                embed_dir = Path(config.output_dir) / f"embed_{run_id}"
                npy_path = embed_dir / "embeddings" / f"{model_id}_corpus.npy"
                index_path = embed_dir / "embeddings" / "corpus_index.json"
                if not (npy_path.exists() and index_path.exists()) and eval_only_run_id:
                    # Full runs write to experiment_id/embeddings/, not embed_{run_id}. Search for matching run_id.
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
                                    # Ensure this cache was built for the same corpus ids/order contract.
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
            embedding_time_sec = time.perf_counter() - t0

            # A1.2: Load or compute family embeddings when dual-list fusion is enabled.
            if use_dual_list_fusion and family_corpus is not None and run_id_family is not None:
                family_corpus_texts = [c.get("text", "") for c in family_corpus]
                cached_f = fetch_cached_embeddings(run_id_family, model_id, mongo_uri) if (eval_only_run_id or config.reuse_embeddings) else None
                if cached_f and len(cached_f) == len(family_corpus_ids):
                    id_to_emb_f = {r["chunk_id"]: r["embedding"] for r in cached_f}
                    family_embeddings = np.array(
                        [id_to_emb_f[fid] for fid in family_corpus_ids], dtype=np.float32
                    )
                    logger.info("Loaded %d family embeddings from cache (run_id_family=%s)", len(family_embeddings), run_id_family)
                else:
                    family_embeddings = encode_texts_fn(model, family_corpus_texts, batch_size=config.batch_size)
                    if mongo_uri and not eval_only_run_id:
                        records_f = [
                            {"run_id": run_id_family, "model_id": model_id, "chunk_id": fid, "embedding": family_embeddings[i].tolist()}
                            for i, fid in enumerate(family_corpus_ids)
                        ]
                        save_cached_embeddings(run_id_family, model_id, records_f, mongo_uri, clear_existing=True)
                        save_embedding_run_metadata(run_id_family, model_id, len(family_corpus_ids), mongo_uri)
                    np.save(output_dir / "embeddings" / f"{model_id}_family.npy", family_embeddings)

            # Grounding: semantic per model or use pre-grounding
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

            # Query embeddings and retrieval
            query_texts = [q.get("question") or q.get("expected_answer_summary") or "" for q in grounded_queries]
            query_embeddings = encode_texts_fn(model, query_texts, batch_size=config.batch_size)
            t1 = time.perf_counter()
            q_norm = query_embeddings / (np.linalg.norm(query_embeddings, axis=1, keepdims=True) + 1e-9)
            max_k = max(config.top_k)
            ranked_lists = []
            score_lists = []

            if use_dual_list_fusion and family_embeddings is not None:
                # A1.2 dual-list fusion: retrieve from Index_U and Index_F, then fuse.
                Ku = getattr(config, "dual_list_ku", 12)
                Kf = getattr(config, "dual_list_kf", 12)
                Kfinal = getattr(config, "dual_list_kfinal", 10)
                Qu = getattr(config, "dual_list_qu", 6)
                family_params_str = f"sym_w{getattr(config, 'dual_list_family_window', 3)}_m{getattr(config, 'dual_list_family_max_units', 6)}"
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

            # Optional: expand top-k with prev/next context, re-embed, re-rank
            if getattr(config, "expand_context", False):
                n_ctx = getattr(config, "expand_context_n", 1)
                logger.info("Expand context (n=%d) and re-rank for %d queries", n_ctx, len(grounded_queries))
                for i in range(len(grounded_queries)):
                    center_ids = ranked_lists[i][:max_k]
                    expanded_texts = _build_expanded_texts(corpus, id_to_index, center_ids, n_ctx)
                    expanded_emb = encode_texts_fn(model, expanded_texts, batch_size=config.batch_size)
                    q_emb = query_embeddings[i : i + 1]
                    scores = np.dot(q_emb, expanded_emb.T).flatten()
                    new_order = np.argsort(scores)[::-1]
                    ranked_lists[i] = [center_ids[j] for j in new_order]
                    score_lists[i] = [float(scores[j]) for j in new_order]

            # Hybrid: fuse dense + BM25 via RRF (R7: k from policy/config)
            if retrieval_mode in ("hybrid", "hybrid+rerank") and bm25_ranked_lists is not None:
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

            # R11: Cross-encoder re-ranking (opt-in or hybrid+rerank mode)
            reranker_model = getattr(config, "reranker", None)
            if retrieval_mode == "hybrid+rerank" and not reranker_model:
                reranker_model = "cross-encoder/ms-marco-MiniLM-L6-v2"
            if reranker_model and retrieval_mode in ("hybrid", "hybrid+rerank"):
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

            # R6: Co-retrieval hints expansion (opt-in)
            if getattr(config, "co_retrieval_expand", False):
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
                    total_cap = max(0, getattr(config, "crossref_expand_total_cap", 20))
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
                            per_hit = max(0, getattr(config, "crossref_expand_per_hit", 2))
                            for hid in topic_to_ids.get(rt, [])[:5]:
                                if added >= total_cap or per_hit <= 0:
                                    break
                                if hid not in seen:
                                    seen.add(hid)
                                    ranked_lists[i].append(hid)
                                    score_lists[i].append(0.0)
                                    added += 1
                                    per_hit -= 1

            # B1: deterministic crossref sidecar expansion.
            if getattr(config, "crossref_sidecar_expand", False) and crossref_sidecar:
                for i in range(len(grounded_queries)):
                    ranked_lists[i], score_lists[i], _ = expand_ranked_with_sidecar(
                        ranked_ids=ranked_lists[i],
                        score_list=score_lists[i],
                        sidecar=crossref_sidecar,
                        expand_top_k=getattr(config, "crossref_expand_top_k", 10),
                        expand_per_hit=getattr(config, "crossref_expand_per_hit", 2),
                        total_cap=getattr(config, "crossref_expand_total_cap", 20),
                    )

            # B1 replacement: dependency-oriented pairing edges (delta→base, exception→base).
            if getattr(config, "dependency_pairing_expand", False) and pairing_edges:
                emax = getattr(config, "dependency_pairing_emax", 6)
                for i in range(len(grounded_queries)):
                    ranked_lists[i], score_lists[i], _ = expand_ranked_with_pairing_edges(
                        ranked_ids=ranked_lists[i],
                        score_list=score_lists[i],
                        pairing_edges=pairing_edges,
                        expand_top_k=getattr(config, "crossref_expand_top_k", 10),
                        Emax=emax,
                    )

            # R9: Unit-type soft boost (opt-in)
            boost = getattr(config, "unit_type_boost", 0.0)
            if boost > 0:
                _apply_unit_type_boost(ranked_lists, score_lists, corpus, grounded_queries, boost)

            scoring_time_sec = time.perf_counter() - t1

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
            # Per-query retrieval review: full chunk text for manual inspection
            use_expanded = getattr(config, "expand_context", False)
            pf_policy = ParentFetchConfig(
                depth=getattr(config, "parent_fetch_depth", 1),
                char_cap=getattr(config, "parent_fetch_cap", 2000),
                enabled=getattr(config, "parent_fetch_enabled", False),
            )
            query_reviews = []
            for i, q in enumerate(grounded_queries):
                pq = metrics.per_query[i]
                retrieved = []
                for r, (cid, sc) in enumerate(zip(ranked_lists[i], score_lists[i]), start=1):
                    text = (
                        _expanded_text(corpus, id_to_index, cid, getattr(config, "expand_context_n", 1))
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
                # Log one line per query: query_id, top-3 chunk_ids, first_gold_rank, failure_type
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
            retrieved_chunks_by_model[model_id] = query_reviews
            logger.info("Model %s: retrieval done for %d queries; review in retrieved_chunks.json", model_id, len(grounded_queries))

            results_by_model[model_id] = {
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
            }
            per_query_by_model[model_id] = metrics.per_query

    grounded_count = sum(1 for q in grounded_queries if (q.get("gold_unit_ids")))
    grounding_summary = {
        "total_queries": len(grounded_queries),
        "grounded": grounded_count,
        "ungrounded": len(grounded_queries) - grounded_count,
        "method": "corpus_wide_semantic" if use_semantic_grounding else "page_anchored",
    }
    corpus_stats = {
        "unit_count": len(corpus),
        "page_count": len(grounding_units_by_page_map),
    }
    model_list = config.models if config.models else ["bm25"]
    config_dict = {
        "substrate_path": config.substrate_path,
        "document_id": config.document_id,
        "substrate_version": config.substrate_version,
        "run_id": run_id,
        "models": model_list,
        "query_batch_paths": config.query_batches,
        "top_k": config.top_k,
        "retrieval_mode": config.retrieval_mode,
        "expand_context": getattr(config, "expand_context", False),
        "expand_context_n": getattr(config, "expand_context_n", 1),
        "clause_family_projection": getattr(config, "clause_family_projection", False),
        "crossref_sidecar_expand": getattr(config, "crossref_sidecar_expand", False),
        "co_retrieval_expand": getattr(config, "co_retrieval_expand", False),
        "a_prime_generate_minimal": getattr(config, "a_prime_generate_minimal", False),
        "dual_list_fusion": getattr(config, "dual_list_fusion", False),
        "dependency_pairing_expand": getattr(config, "dependency_pairing_expand", False),
    }
    experiment_doc = {
        "experiment_id": experiment_id,
        "experiment_name": config.experiment_name,
        "created_at": datetime.now(timezone.utc),
        "config": config_dict,
        "corpus_stats": corpus_stats,
        "grounding_summary": grounding_summary,
        "results": results_by_model,
        "per_suite_results": results_by_model.get(model_list[0], {}).get("per_suite", {}) if model_list else {},
        "frozen": False,
    }
    try:
        save_experiment(experiment_doc, mongo_uri)
        logger.info("Saved experiment to MongoDB: %s", experiment_id)
    except Exception as e:
        logger.warning("Could not save experiment to MongoDB: %s", e)
    paths = write_report_artifacts(
        output_dir,
        experiment_id,
        config.experiment_name,
        config_dict,
        corpus_stats,
        grounding_summary,
        results_by_model,
        all_grounding_audit,
        per_query_by_model,
        experiment_doc,
        retrieved_chunks_by_model=retrieved_chunks_by_model,
    )
    logger.info("Report written to %s", paths.get("REPORT.md"))
    if retrieved_chunks_by_model:
        logger.info("Retrieved chunks (for manual review): %s", paths.get("retrieved_chunks.json"))
    return experiment_id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retrieval Lab: embed substrate (once) and/or run retrieval evals over EvidenceUnits.",
    )
    parser.add_argument("--config", type=str, help="Path to experiment YAML config")
    parser.add_argument("--substrate", type=str, help="Substrate path (overrides config)")
    parser.add_argument("--document-id", type=str, default="DnD_PHB_5.5", help="Document ID for substrate")
    parser.add_argument(
        "--substrate-version",
        type=str,
        default=None,
        help="Substrate version (e.g. v1, 20260208). Run_id becomes retrieval_lab_{document_id}_{version}. Re-embed only when extraction changes.",
    )
    parser.add_argument("--batches", type=str, nargs="+", help="Query batch JSON paths (overrides config)")
    parser.add_argument("--models", type=str, nargs="+", help="Model IDs (overrides config)")
    parser.add_argument("--top-k", type=str, default="1,3,5,10,20", help="Comma-separated top-k values")
    parser.add_argument("--output", type=str, help="Output directory (overrides config)")
    parser.add_argument("--reuse-embeddings", action="store_true", default=True, help="Use MongoDB cache for embeddings")
    parser.add_argument("--no-reuse-embeddings", action="store_false", dest="reuse_embeddings")
    parser.add_argument("--mongo-uri", type=str, default=None, help="MongoDB URI (default: MONGODB_URI env)")
    parser.add_argument(
        "--embed-only",
        action="store_true",
        help="Only embed the substrate (all models); save to MongoDB. Do not run queries or report. Re-run when extraction/substrate changes.",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Eval-only: use this embedding run_id (no embedding). Requires embeddings already in MongoDB for this run_id and all --models.",
    )
    parser.add_argument(
        "--trust-remote-code",
        action="store_true",
        help="Pass trust_remote_code=True when loading models (required for nomic-embed-text-v2, bge-m3, gte-multilingual-base).",
    )
    parser.add_argument("--parent-fetch-depth", type=int, default=1, help="R2: Parent-fetch structural_path depth")
    parser.add_argument("--parent-fetch-cap", type=int, default=2000, help="R2: Parent-fetch char cap per scope")
    parser.add_argument("--parent-fetch", action="store_true", dest="parent_fetch_enabled", help="R2: Enable parent-fetch enrichment")
    parser.add_argument("--reranker", type=str, default=None, help="R11: Cross-encoder model name (e.g. cross-encoder/ms-marco-MiniLM-L6-v2). Re-rank hybrid top-50 to top-10.")
    parser.add_argument("--clause-family-projection", action="store_true", help="A1: enable retrieval-only clause-family projection substrate")
    parser.add_argument("--crossref-sidecar-expand", action="store_true", help="B1: enable deterministic sidecar expansion")
    parser.add_argument("--crossref-expand-top-k", type=int, default=10, help="B1: consider top-k anchors for sidecar expansion")
    parser.add_argument("--crossref-expand-per-hit", type=int, default=2, help="B1: max expansions per anchor")
    parser.add_argument("--crossref-expand-total-cap", type=int, default=20, help="B1/H7: max expansions added per query")
    parser.add_argument("--a-prime-generate-minimal", action="store_true", help="H7: synthesize minimal deterministic A′ hints in-memory when missing")
    parser.add_argument("--dual-list-fusion", action="store_true", help="A1.2: retrieve from Index_U + Index_F (clause-family), fuse with quota interleave")
    parser.add_argument("--dual-list-ku", type=int, default=12, help="A1.2: top-K from unit index")
    parser.add_argument("--dual-list-kf", type=int, default=12, help="A1.2: top-K from family index")
    parser.add_argument("--dual-list-kfinal", type=int, default=10, help="A1.2: final candidate cap")
    parser.add_argument("--dual-list-qu", type=int, default=6, help="A1.2: quota unit hits first")
    parser.add_argument("--dependency-pairing-expand", action="store_true", help="B1: expand with delta→base and exception→base pairing edges")
    parser.add_argument("--dependency-pairing-emax", type=int, default=6, help="B1: max paired adds per query")
    args = parser.parse_args()

    if args.config:
        config = ExperimentConfig.from_yaml(Path(args.config))
    else:
        if not args.substrate or not args.models:
            parser.error("Without --config, --substrate and --models are required")
        if not args.embed_only and not args.run_id and not args.batches:
            parser.error("Without --embed-only or --run-id, --batches is required")
        config = ExperimentConfig(
            experiment_name="retrieval_lab_run",
            substrate_path=args.substrate,
            document_id=args.document_id,
            query_batches=args.batches or [],
            models=args.models,
            top_k=[int(x) for x in args.top_k.split(",") if x.strip()],
            output_dir=args.output or "out/retrieval_lab/experiments",
            mongo_uri=args.mongo_uri,
            reuse_embeddings=args.reuse_embeddings,
            substrate_version=args.substrate_version,
            trust_remote_code=args.trust_remote_code,
        )
    if args.substrate:
        config.substrate_path = args.substrate
    if args.batches:
        config.query_batches = args.batches
    if args.models:
        config.models = args.models
    if args.top_k:
        config.top_k = [int(x) for x in args.top_k.split(",") if x.strip()]
    if args.output:
        config.output_dir = args.output
    if args.mongo_uri is not None:
        config.mongo_uri = args.mongo_uri
    if args.substrate_version is not None:
        config.substrate_version = args.substrate_version
    if args.trust_remote_code:
        config.trust_remote_code = True
    if hasattr(args, "parent_fetch_depth"):
        config.parent_fetch_depth = args.parent_fetch_depth
    if hasattr(args, "parent_fetch_cap"):
        config.parent_fetch_cap = args.parent_fetch_cap
    if hasattr(args, "parent_fetch_enabled") and args.parent_fetch_enabled:
        config.parent_fetch_enabled = True
    if hasattr(args, "reranker") and args.reranker:
        config.reranker = args.reranker
    if getattr(args, "clause_family_projection", False):
        config.clause_family_projection = True
    if getattr(args, "crossref_sidecar_expand", False):
        config.crossref_sidecar_expand = True
    if hasattr(args, "crossref_expand_top_k"):
        config.crossref_expand_top_k = args.crossref_expand_top_k
    if hasattr(args, "crossref_expand_per_hit"):
        config.crossref_expand_per_hit = args.crossref_expand_per_hit
    if hasattr(args, "crossref_expand_total_cap"):
        config.crossref_expand_total_cap = args.crossref_expand_total_cap
    if getattr(args, "a_prime_generate_minimal", False):
        config.a_prime_generate_minimal = True
    if getattr(args, "dual_list_fusion", False):
        config.dual_list_fusion = True
    if hasattr(args, "dual_list_ku"):
        config.dual_list_ku = args.dual_list_ku
    if hasattr(args, "dual_list_kf"):
        config.dual_list_kf = args.dual_list_kf
    if hasattr(args, "dual_list_kfinal"):
        config.dual_list_kfinal = args.dual_list_kfinal
    if hasattr(args, "dual_list_qu"):
        config.dual_list_qu = args.dual_list_qu
    if getattr(args, "dependency_pairing_expand", False):
        config.dependency_pairing_expand = True
    if hasattr(args, "dependency_pairing_emax"):
        config.dependency_pairing_emax = args.dependency_pairing_emax

    if args.embed_only:
        run_id = _run_embed_only(config)
        print(f"Embed-only done. run_id={run_id}")
        return

    experiment_id = _run_experiment(config, eval_only_run_id=args.run_id)
    print(f"Done. Experiment ID: {experiment_id}")


if __name__ == "__main__":
    main()

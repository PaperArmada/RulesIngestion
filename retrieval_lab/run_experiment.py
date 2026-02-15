"""
CLI entry point: load config, load substrate, ground gold, embed per model, score, persist, report.
"""

from __future__ import annotations

import json
import logging
import random
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
    ground_queries_page_anchored,
    persist_resolved_gold_to_batch_files,
    resolve_gold_locations_to_current_corpus,
)
from retrieval_lab.projection import build_clause_family_projection
from retrieval_lab.report import write_report_artifacts
from retrieval_lab.crossref_sidecar import (
    build_minimal_a_prime_hints,
)
from retrieval_lab.orchestration.config_access import read_expansion_config, read_run_flags
from retrieval_lab.orchestration.eval_runner import prepare_expansion_indices
from retrieval_lab.orchestration.cli import apply_cli_overrides
from retrieval_lab.orchestration.bm25_mode import run_bm25_mode
from retrieval_lab.orchestration.cli_parser import build_cli_parser
from retrieval_lab.orchestration.dense_mode import run_dense_mode
from retrieval_lab.store import (
    save_cached_embeddings,
    save_embedding_run_metadata,
    save_experiment,
    substrate_run_id,
)
from retrieval_lab.substrate_loader import (
    fold_under_threshold_into_adjacent,
    load_evidence_units,
    merge_enrichments_into_corpus,
    merge_units_by_heading,
    units_by_page,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Models that require trust_remote_code=True when loading (HuggingFace custom code).
MODELS_REQUIRING_TRUST_REMOTE_CODE = frozenset({
    "nomic-embed-text-v2",
    "bge-m3",
    "gte-multilingual-base",
})


def _set_seed(seed: Optional[int]) -> None:
    if seed is None:
        return
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch  # type: ignore

        torch.manual_seed(seed)
    except Exception:
        # Torch is optional for some runs; keep seeding best-effort.
        pass


def _load_baseline_metrics(baseline_metrics_path: Optional[str]) -> Dict[str, Dict[str, Any]]:
    if not baseline_metrics_path:
        return {}
    path = Path(baseline_metrics_path)
    if not path.exists():
        logger.warning("baseline_metrics_path not found: %s", baseline_metrics_path)
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("baseline_metrics_path is not valid JSON: %s", baseline_metrics_path)
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    if isinstance(payload, dict):
        for model_id, metrics in payload.items():
            if isinstance(metrics, dict):
                fb = metrics.get("failure_bucket_counts", {})
                if isinstance(fb, dict):
                    out[model_id] = {
                        "failure_bucket_counts": {k: int(v) for k, v in fb.items() if isinstance(v, (int, float))},
                        "mrr": float(metrics.get("mrr", 0.0)),
                        "full_set_hit_at_10": float((metrics.get("full_set_hit_at_k") or {}).get("10", (metrics.get("full_set_hit_at_k") or {}).get(10, 0.0))),
                        "required_full_set_hit_at_10": float((metrics.get("required_full_set_hit_at_k") or {}).get("10", (metrics.get("required_full_set_hit_at_k") or {}).get(10, 0.0))),
                    }
    return out


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
    corpus = load_evidence_units(config.substrate_path, config.document_id)
    if not corpus:
        raise ValueError("Corpus is empty; no EvidenceUnits found.")
    min_chars = getattr(config, "min_chars", None)
    if min_chars is not None:
        corpus = fold_under_threshold_into_adjacent(corpus, min_chars)
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


def _prepare_experiment_corpus_context(
    config: ExperimentConfig,
    flags: Any,
    eval_only_run_id: Optional[str],
) -> Dict[str, Any]:
    """Load corpus, apply projection options, and prepare run identifiers."""
    logger.info("Loading substrate from %s", config.substrate_path)
    raw_corpus = load_evidence_units(config.substrate_path, config.document_id)
    if not raw_corpus:
        raise ValueError("Corpus is empty; no EvidenceUnits found.")
    folded_corpus = raw_corpus
    if flags.min_chars is not None:
        folded_corpus = fold_under_threshold_into_adjacent(raw_corpus, flags.min_chars)
    canonical_corpus = folded_corpus
    if flags.merge_chunks:
        canonical_corpus = merge_units_by_heading(
            folded_corpus,
            max_chars=flags.merge_max_chars,
        )
    canonical_corpus = merge_enrichments_into_corpus(canonical_corpus, config.substrate_path)

    if flags.a_prime_generate_minimal:
        generated_hints = build_minimal_a_prime_hints(canonical_corpus)
        for unit in canonical_corpus:
            uid = unit.get("id", "")
            if uid in generated_hints:
                if not unit.get("topic_tags"):
                    unit["topic_tags"] = generated_hints[uid].get("topic_tags", [])
                if not unit.get("co_retrieval_hints"):
                    unit["co_retrieval_hints"] = generated_hints[uid].get("co_retrieval_hints", [])

    grounding_units_by_page_map = units_by_page(canonical_corpus)

    use_dual_list_fusion = flags.dual_list_fusion
    corpus = canonical_corpus
    if flags.clause_family_projection and not use_dual_list_fusion:
        corpus = build_clause_family_projection(
            canonical_corpus,
            window=flags.clause_family_window,
            max_units=flags.clause_family_max_units,
            direction=flags.clause_family_direction,
        )
        logger.info(
            "Clause-family projection enabled: %d canonical units -> %d projection units (window=%d max_units=%d direction=%s)",
            len(canonical_corpus),
            len(corpus),
            flags.clause_family_window,
            flags.clause_family_max_units,
            flags.clause_family_direction,
        )

    corpus_ids = [c["id"] for c in corpus]
    corpus_texts = [c["text"] for c in corpus]
    id_to_source_ids: Dict[str, List[str]] = {
        c["id"]: list(c.get("source_unit_ids", [c["id"]])) for c in corpus
    }

    if eval_only_run_id:
        run_id = eval_only_run_id
        logger.info("Eval-only: using run_id=%s (no embedding)", run_id)
    else:
        run_id = substrate_run_id(config.document_id, corpus_ids, config.substrate_version)
    logger.info("Corpus: %d units, run_id=%s", len(corpus), run_id)

    family_corpus: Optional[List[Dict[str, Any]]] = None
    family_corpus_ids: List[str] = []
    family_id_to_anchor_unit_id: Dict[str, str] = {}
    run_id_family: Optional[str] = None
    if use_dual_list_fusion:
        family_corpus = build_clause_family_projection(
            canonical_corpus,
            window=flags.dual_list_family_window,
            max_units=flags.dual_list_family_max_units,
            direction=flags.dual_list_family_direction,
        )
        family_corpus_ids = [c["id"] for c in family_corpus]
        for c in family_corpus:
            anchor = c.get("projection_anchor_id") or (
                (c.get("source_unit_ids") or [c["id"]])[0] if c.get("source_unit_ids") else c["id"]
            )
            family_id_to_anchor_unit_id[c["id"]] = anchor
        run_id_family = run_id + f"_family_w{flags.dual_list_family_window}_m{flags.dual_list_family_max_units}"
        logger.info(
            "A1.2 dual-list fusion: %d canonical, %d family; run_id_family=%s",
            len(corpus_ids),
            len(family_corpus_ids),
            run_id_family,
        )

    return {
        "corpus": corpus,
        "canonical_corpus": canonical_corpus,
        "folded_corpus": folded_corpus,
        "grounding_units_by_page_map": grounding_units_by_page_map,
        "corpus_ids": corpus_ids,
        "corpus_texts": corpus_texts,
        "id_to_source_ids": id_to_source_ids,
        "run_id": run_id,
        "use_dual_list_fusion": use_dual_list_fusion,
        "family_corpus": family_corpus,
        "family_corpus_ids": family_corpus_ids,
        "family_id_to_anchor_unit_id": family_id_to_anchor_unit_id,
        "run_id_family": run_id_family,
    }


def _load_and_ground_queries(
    config: ExperimentConfig,
    retrieval_mode: str,
    folded_corpus: List[Dict[str, Any]],
    canonical_corpus: List[Dict[str, Any]],
    grounding_units_by_page_map: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Load queries and resolve gold grounding strategy."""
    flat_queries, _ = flatten_query_batches(config.query_batches)
    if not flat_queries:
        raise ValueError("No queries loaded from query_batches.")

    flat_queries, gold_resolution_summary = resolve_gold_locations_to_current_corpus(
        flat_queries,
        folded_corpus=folded_corpus,
        merged_corpus=canonical_corpus,
    )
    logger.info(
        "Gold location resolution: total=%d with_locations=%d resolved_nonempty=%d resolved_empty=%d legacy_only=%d",
        gold_resolution_summary["queries_total"],
        gold_resolution_summary["queries_with_gold_locations"],
        gold_resolution_summary["queries_resolved_nonempty"],
        gold_resolution_summary["queries_resolved_empty"],
        gold_resolution_summary["queries_legacy_only"],
    )
    if gold_resolution_summary["queries_with_gold_locations"] > 0:
        cwd = Path.cwd()
        n_updated = persist_resolved_gold_to_batch_files(
            config.query_batches,
            flat_queries,
            cwd,
        )
        if n_updated:
            logger.info("Persisted resolved gold to %d batch file(s)", n_updated)
    logger.info("Loaded %d queries", len(flat_queries))

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

    return {
        "flat_queries": flat_queries,
        "grounded_queries": grounded_queries,
        "grounding_audit": grounding_audit,
        "use_semantic_grounding": use_semantic_grounding,
        "gold_resolution_summary": gold_resolution_summary,
    }


def _run_experiment(config: ExperimentConfig, eval_only_run_id: Optional[str] = None) -> str:
    """Full eval: load or use existing embeddings, run queries, score, report."""
    config.resolve_paths(Path.cwd())
    embed_only = False
    eval_only = eval_only_run_id is not None
    config.validate(embed_only=embed_only, eval_only=eval_only)
    _set_seed(config.seed)
    retrieval_mode = config.retrieval_mode
    t_stage_start = time.perf_counter()
    flags = read_run_flags(config)
    expansion_cfg = read_expansion_config(config)
    context = _prepare_experiment_corpus_context(config, flags, eval_only_run_id)
    corpus = context["corpus"]
    canonical_corpus = context["canonical_corpus"]
    folded_corpus = context["folded_corpus"]
    grounding_units_by_page_map = context["grounding_units_by_page_map"]
    corpus_ids = context["corpus_ids"]
    corpus_texts = context["corpus_texts"]
    id_to_source_ids = context["id_to_source_ids"]
    run_id = context["run_id"]
    use_dual_list_fusion = context["use_dual_list_fusion"]
    family_corpus = context["family_corpus"]
    family_corpus_ids = context["family_corpus_ids"]
    family_id_to_anchor_unit_id = context["family_id_to_anchor_unit_id"]
    run_id_family = context["run_id_family"]

    grounding_context = _load_and_ground_queries(
        config,
        retrieval_mode,
        folded_corpus,
        canonical_corpus,
        grounding_units_by_page_map,
    )
    flat_queries = grounding_context["flat_queries"]
    grounded_queries = grounding_context["grounded_queries"]
    grounding_audit = grounding_context["grounding_audit"]
    use_semantic_grounding = grounding_context["use_semantic_grounding"]
    gold_resolution_summary = grounding_context["gold_resolution_summary"]
    stage_timing_sec: Dict[str, float] = {
        "load_corpus_and_projection": time.perf_counter() - t_stage_start
    }

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
    crossref_sidecar, pairing_edges = prepare_expansion_indices(
        corpus=corpus,
        canonical_corpus=canonical_corpus,
        crossref_enabled=expansion_cfg.crossref_sidecar_expand,
        pairing_enabled=expansion_cfg.dependency_pairing_expand,
    )
    if crossref_sidecar:
        logger.info("Crossref sidecar enabled: %d units with deterministic edges", len(crossref_sidecar))
    if pairing_edges:
        logger.info(
            "B1 dependency pairing enabled: %d units with delta/exception→base edges",
            len(pairing_edges),
        )
    pairing_instrumentation_by_model: Dict[str, Any] = {}

    t_retrieval = time.perf_counter()
    if retrieval_mode == "bm25":
        bm25_out = run_bm25_mode(
            config=config,
            flags=flags,
            expansion_cfg=expansion_cfg,
            corpus=corpus,
            corpus_ids=corpus_ids,
            corpus_texts=corpus_texts,
            grounded_queries=grounded_queries,
            id_to_text=id_to_text,
            id_to_source_ids=id_to_source_ids,
            crossref_sidecar=crossref_sidecar,
            pairing_edges=pairing_edges,
            apply_unit_type_boost_fn=_apply_unit_type_boost,
        )
        results_by_model["bm25"] = bm25_out["results"]
        per_query_by_model["bm25"] = bm25_out["per_query"]
        retrieved_chunks_by_model["bm25"] = bm25_out["query_reviews"]
        if bm25_out.get("pairing_payload"):
            pairing_instrumentation_by_model["bm25"] = bm25_out["pairing_payload"]
        logger.info(
            "Model bm25: retrieval done for %d queries; review in retrieved_chunks.json",
            len(grounded_queries),
        )
    else:
        load_model_fn, encode_texts_fn, model_registry = _load_model_registry()
        dense_out = run_dense_mode(
            config=config,
            flags=flags,
            expansion_cfg=expansion_cfg,
            eval_only_run_id=eval_only_run_id,
            run_id=run_id,
            output_dir=output_dir,
            corpus=corpus,
            corpus_ids=corpus_ids,
            corpus_texts=corpus_texts,
            id_to_source_ids=id_to_source_ids,
            flat_queries=flat_queries,
            grounded_queries=grounded_queries,
            use_semantic_grounding=use_semantic_grounding,
            initial_grounding_audit=grounding_audit,
            crossref_sidecar=crossref_sidecar,
            pairing_edges=pairing_edges,
            use_dual_list_fusion=use_dual_list_fusion,
            family_corpus=family_corpus,
            family_corpus_ids=family_corpus_ids,
            family_id_to_anchor_unit_id=family_id_to_anchor_unit_id,
            run_id_family=run_id_family,
            load_model_fn=load_model_fn,
            encode_texts_fn=encode_texts_fn,
            model_registry=model_registry,
            trust_remote_models=MODELS_REQUIRING_TRUST_REMOTE_CODE,
            build_expanded_texts_fn=_build_expanded_texts,
            expanded_text_fn=_expanded_text,
            apply_unit_type_boost_fn=_apply_unit_type_boost,
        )
        results_by_model = dense_out["results_by_model"]
        per_query_by_model = dense_out["per_query_by_model"]
        retrieved_chunks_by_model = dense_out["retrieved_chunks_by_model"]
        all_grounding_audit = dense_out["all_grounding_audit"]
        pairing_instrumentation_by_model = dense_out["pairing_instrumentation_by_model"]
    stage_timing_sec["retrieval_and_scoring"] = time.perf_counter() - t_retrieval

    grounded_count = sum(1 for q in grounded_queries if (q.get("gold_unit_ids")))
    grounding_summary = {
        "total_queries": len(grounded_queries),
        "grounded": grounded_count,
        "ungrounded": len(grounded_queries) - grounded_count,
        "method": "corpus_wide_semantic" if use_semantic_grounding else "page_anchored",
        "gold_resolution_summary": gold_resolution_summary,
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
        "seed": config.seed,
        "bm25_tokenizer_mode": config.bm25_tokenizer_mode,
        "bm25_k1": config.bm25_k1,
        "bm25_b": config.bm25_b,
        "bm25_query_mode": config.bm25_query_mode,
        "bm25_query_weight_question": config.bm25_query_weight_question,
        "bm25_query_weight_summary": config.bm25_query_weight_summary,
        "two_stage_retrieval": config.two_stage_retrieval,
        "stage1_admission_k": config.stage1_admission_k,
        "stage1_query_mode": config.stage1_query_mode,
        "stage2_query_mode": config.stage2_query_mode,
        "stage2_rerank_method": config.stage2_rerank_method,
        "raw_first_merge_rerank": getattr(config, "raw_first_merge_rerank", False),
        "raw_stage1_admission_k": getattr(config, "raw_stage1_admission_k", 100),
        "raw_merge_rerank_top_k": getattr(config, "raw_merge_rerank_top_k", 20),
        "raw_merge_score_floor": getattr(config, "raw_merge_score_floor", True),
        "raw_merge_rank_floor": getattr(config, "raw_merge_rank_floor", True),
        "raw_merge_coverage_bonus": getattr(config, "raw_merge_coverage_bonus", 0.0),
        "baseline_metrics_path": config.baseline_metrics_path,
        "expand_context": flags.expand_context,
        "expand_context_n": flags.expand_context_n,
        "clause_family_projection": flags.clause_family_projection,
        "crossref_sidecar_expand": expansion_cfg.crossref_sidecar_expand,
        "co_retrieval_expand": flags.co_retrieval_expand,
        "a_prime_generate_minimal": flags.a_prime_generate_minimal,
        "dual_list_fusion": flags.dual_list_fusion,
        "dependency_pairing_expand": expansion_cfg.dependency_pairing_expand,
    }
    experiment_doc = {
        "experiment_id": experiment_id,
        "experiment_name": config.experiment_name,
        "created_at": datetime.now(timezone.utc),
        "config": config_dict,
        "corpus_stats": corpus_stats,
        "grounding_summary": grounding_summary,
        "results": results_by_model,
        "stage_timing_sec": stage_timing_sec,
        "per_suite_results": results_by_model.get(model_list[0], {}).get("per_suite", {}) if model_list else {},
        "frozen": False,
    }
    baseline_metrics = _load_baseline_metrics(config.baseline_metrics_path)
    baseline_failure_buckets = {
        model_id: model_payload.get("failure_bucket_counts", {})
        for model_id, model_payload in baseline_metrics.items()
    }
    if baseline_failure_buckets:
        experiment_doc["baseline_failure_buckets"] = baseline_failure_buckets
    for model_id, res in results_by_model.items():
        baseline = baseline_metrics.get(model_id, {})
        if baseline:
            res["baseline_mrr"] = float(baseline.get("mrr", res.get("mrr", 0.0)))
            res["baseline_full_set_hit_at_10"] = float(
                baseline.get("full_set_hit_at_10", (res.get("full_set_hit_at_k") or {}).get(10, 0.0))
            )
            res["baseline_required_full_set_hit_at_10"] = float(
                baseline.get("required_full_set_hit_at_10", (res.get("required_full_set_hit_at_k") or {}).get(10, 0.0))
            )
    if mongo_uri:
        try:
            save_experiment(experiment_doc, mongo_uri)
            logger.info("Saved experiment to MongoDB: %s", experiment_id)
        except Exception as e:
            logger.warning("Could not save experiment to MongoDB: %s", e)
    else:
        logger.info("MongoDB persistence disabled (mongo_uri not set); skipping save_experiment.")
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
    # v1: pairing instrumentation (required; emit even when 0 so dashboard/tests can rely on it).
    pairing_payload: Dict[str, Any] = {
        "enabled": expansion_cfg.dependency_pairing_expand,
        "by_model": pairing_instrumentation_by_model,
    }
    (output_dir / "pairing_instrumentation.json").write_text(
        json.dumps(pairing_payload, indent=2),
        encoding="utf-8",
    )
    if retrieved_chunks_by_model:
        logger.info("Retrieved chunks (for manual review): %s", paths.get("retrieved_chunks.json"))
    return experiment_id


def main() -> None:
    parser = build_cli_parser()
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
    apply_cli_overrides(config, args)

    if args.embed_only:
        run_id = _run_embed_only(config)
        print(f"Embed-only done. run_id={run_id}")
        return

    experiment_id = _run_experiment(config, eval_only_run_id=args.run_id)
    print(f"Done. Experiment ID: {experiment_id}")


if __name__ == "__main__":
    main()

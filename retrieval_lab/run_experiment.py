"""
CLI entry point: load config, load substrate, ground gold, embed per model, score, persist, report.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
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


def _load_dotenv_for_openai() -> None:
    """Load .env so OPENAI_API_KEY is available (auto-gold review, answer evaluation)."""
    if os.environ.get("OPENAI_API_KEY"):
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for base in (_RULES_INGESTION_ROOT, _REPO_ROOT):
        for name in (".env", ".env.development"):
            path = base / name
            if path.is_file():
                load_dotenv(path)
                if os.environ.get("OPENAI_API_KEY"):
                    return


from retrieval_lab.config import ExperimentConfig
from retrieval_lab.benchmark_contract import (
    benchmark_contract_sidecar_path,
    benchmark_query_alignment_summary,
    build_benchmark_contract,
    build_prod_readiness_artifact,
    validate_benchmark_contract,
    write_benchmark_contract,
)
from retrieval_lab.corpus_fingerprint import (
    build_corpus_index_payload,
    corpus_content_fingerprint_from_units,
    corpus_fingerprint_from_ids,
)
from retrieval_lab.gold_grounding import (
    INTERNAL_QUERY_KEYS,
    apply_gold_recommendations_to_queries,
    flatten_query_batches,
    ground_queries_page_anchored,
    resolve_gold_locations_to_current_corpus,
)
from retrieval_lab.metrics import score_retrieval
from retrieval_lab.projection import build_clause_family_projection
from retrieval_lab.report import write_report_artifacts
from retrieval_lab.crossref_sidecar import (
    build_minimal_a_prime_hints,
)
from retrieval_lab.orchestration.config_access import read_expansion_config, read_query_enhancement_config, read_run_flags
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
from retrieval_lab.embedding_enrichment import build_embedding_text
from retrieval_lab.chunk_quality_gate import (
    evaluate_chunk_quality_gate,
    summarize_chunk_quality,
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
    "pplx-embed-v1-0.6B",
    "pplx-embed-context-v1",
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


def _sha256_jsonable(payload: Any) -> str:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_file(source_path: str, target_path: Path) -> Optional[str]:
    src = Path(source_path)
    if not source_path or not src.exists():
        return None
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(src.read_bytes())
    return str(target_path.resolve())


def _snapshot_query_batch_inputs(
    *,
    output_dir: Path,
    query_batch_paths: List[str],
    query_batch_contract_paths: List[str],
) -> Dict[str, List[str]]:
    snapshot_dir = output_dir / "snapshots" / "benchmark_inputs"
    definition_paths: List[str] = []
    contract_paths: List[str] = []
    for index, path_str in enumerate(query_batch_paths):
        src = Path(path_str)
        suffix = "".join(src.suffixes) or ".json"
        definition_target = snapshot_dir / f"benchmark_definition_{index:02d}{suffix}"
        copied = _snapshot_file(path_str, definition_target)
        if copied:
            definition_paths.append(copied)
    for index, path_str in enumerate(query_batch_contract_paths):
        contract_target = snapshot_dir / f"benchmark_definition_{index:02d}.contract.json"
        copied = _snapshot_file(path_str, contract_target)
        if copied:
            contract_paths.append(copied)
    return {
        "definition_snapshot_paths": definition_paths,
        "contract_snapshot_paths": contract_paths,
    }


def _build_corpus_recipe(config: ExperimentConfig, flags: Any, expansion_cfg: Any) -> Dict[str, Any]:
    return {
        "substrate_path": config.substrate_path,
        "document_id": config.document_id,
        "substrate_version": config.substrate_version or "",
        "min_chars": flags.min_chars,
        "merge_chunks": bool(flags.merge_chunks),
        "merge_max_chars": int(flags.merge_max_chars),
        "clause_family_projection": bool(flags.clause_family_projection),
        "crossref_sidecar_expand": bool(expansion_cfg.crossref_sidecar_expand),
        "co_retrieval_expand": bool(flags.co_retrieval_expand),
        "a_prime_generate_minimal": bool(flags.a_prime_generate_minimal),
        "dual_list_fusion": bool(flags.dual_list_fusion),
        "dependency_pairing_expand": bool(expansion_cfg.dependency_pairing_expand),
    }


def _build_surface_contract(
    *,
    benchmark_path: Path,
    queries: List[Dict[str, Any]],
    corpus_ids: List[str],
    run_id: str,
    substrate_version: Optional[str],
    benchmark_kind: str,
    benchmark_surface: str,
    corpus_fingerprint: str,
    corpus_content_fingerprint: str,
    corpus_unit_count: int,
    corpus_index_path: Path,
    corpus_index_sha256: str,
    corpus_recipe: Dict[str, Any],
    definition_snapshot_paths: List[str],
    definition_contract_snapshot_paths: List[str],
    lineage: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rendered = json.dumps(queries, indent=2)
    benchmark_sha256 = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    definition_path = definition_snapshot_paths[0] if definition_snapshot_paths else str(benchmark_path.resolve())
    definition_sha = _sha256_file(Path(definition_path)) if Path(definition_path).exists() else benchmark_sha256
    merged_lineage = {
        "source_benchmark_paths": list(definition_snapshot_paths),
        "source_contract_paths": list(definition_contract_snapshot_paths),
    }
    if lineage:
        merged_lineage.update(lineage)
    return build_benchmark_contract(
        benchmark_path=benchmark_path,
        benchmark_sha256=benchmark_sha256,
        query_count=len(queries),
        run_id=run_id,
        substrate_version=substrate_version,
        corpus_fingerprint=corpus_fingerprint,
        corpus_content_fingerprint=corpus_content_fingerprint,
        corpus_unit_count=corpus_unit_count,
        corpus_index_path=str(corpus_index_path),
        corpus_index_sha256=corpus_index_sha256,
        corpus_recipe=corpus_recipe,
        benchmark_kind=benchmark_kind,
        benchmark_surface=benchmark_surface,
        benchmark_definition_path=definition_path,
        benchmark_definition_sha256=definition_sha,
        lineage=merged_lineage,
        alignment_summary=benchmark_query_alignment_summary(queries, corpus_ids=corpus_ids),
        projection_metadata={"projection_tool_version": "retrieval_lab_projection_v1"},
    )


def _compose_embedding_substrate_version(
    *,
    base_substrate_version: Optional[str],
    embed_profile: str,
    recipe_mode: str,
) -> str:
    """Build substrate version suffixes that define embedding run identity."""
    sv = str(base_substrate_version or "")
    if embed_profile and str(embed_profile).strip().lower() not in ("", "baseline"):
        prof = str(embed_profile).strip()
        sv = f"{sv}_embed_{prof}" if sv else f"embed_{prof}"
    recipe = str(recipe_mode or "").strip().lower() or "standardized"
    sv = f"{sv}_recipe_{recipe}" if sv else f"recipe_{recipe}"
    return sv


def _load_baseline_failure_types(
    *,
    baseline_metrics_path: Optional[str],
    retrieval_mode: str,
    models: List[str],
) -> Optional[Dict[str, str]]:
    """Optional: load per-query baseline failure types for conditional enhancement.

    Intended use: avoid spending QE cycles on already-strong queries. We only enhance
    failure buckets that baseline couldn't solve (retrieval_miss / rank_miss), and
    we can split behavior between those buckets.

    Expects baseline_metrics_path to be a metrics.json inside a baseline run directory,
    with a sibling per_query.json.
    """
    if not baseline_metrics_path:
        return None
    metrics_path = Path(baseline_metrics_path)
    per_query_path = metrics_path.with_name("per_query.json")
    if not per_query_path.exists():
        return None
    try:
        payload = json.loads(per_query_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("baseline per_query.json is not valid JSON: %s", per_query_path)
        return None
    if not isinstance(payload, dict):
        return None

    if retrieval_mode == "bm25":
        key = "bm25"
    else:
        # Baseline per_query is keyed by model_id; use first configured model if present.
        key = models[0] if models else next(iter(payload.keys()), "")
    per_query = payload.get(key)
    if not isinstance(per_query, list):
        return None

    by_id: Dict[str, str] = {}
    for row in per_query:
        if not isinstance(row, dict):
            continue
        qid = str(row.get("query_id") or "")
        ft = str(row.get("failure_type") or "")
        if qid and ft in ("retrieval_miss", "rank_miss"):
            by_id[qid] = ft
    return by_id


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
    logger.info(
        "Applying corpus recipe before embedding/retrieval: min_chars=%s merge_chunks=%s merge_max_chars=%s",
        min_chars,
        bool(getattr(config, "merge_chunks", False)),
        int(getattr(config, "merge_max_chars", 2000)),
    )
    if min_chars is not None:
        corpus = fold_under_threshold_into_adjacent(corpus, min_chars)
    if getattr(config, "merge_chunks", False):
        corpus = merge_units_by_heading(
            corpus,
            max_chars=getattr(config, "merge_max_chars", 2000),
        )
    corpus = merge_enrichments_into_corpus(corpus, config.substrate_path)
    corpus_ids = [c["id"] for c in corpus]
    embed_profile = getattr(config, "embedding_enrichment_profile", None) or ""
    corpus_texts = [build_embedding_text(c, embed_profile or None) for c in corpus]
    substrate_version = _compose_embedding_substrate_version(
        base_substrate_version=config.substrate_version,
        embed_profile=str(embed_profile or ""),
        recipe_mode=str(getattr(config, "recipe_mode", "standardized")),
    )
    run_id = substrate_run_id(config.document_id, corpus_ids, substrate_version)
    logger.info("Corpus: %d units, run_id=%s", len(corpus), run_id)
    mongo_uri = config.mongo_uri
    output_dir = Path(config.output_dir) / f"embed_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "embeddings").mkdir(exist_ok=True)
    for model_id in config.models:
        if model_id not in MODEL_REGISTRY:
            raise ValueError(
                f"Model {model_id!r} not in active MODEL_REGISTRY; add it before bakeoff runs."
            )
        model_name = MODEL_REGISTRY[model_id].model_name
        logger.info("Embedding model: %s (%s)", model_id, model_name)
        if model_id in MODEL_REGISTRY:
            logger.info("Embedding registry module path: %s", _ARCHIVE_MARK_I / "evaluation/model_registry.py")
        # In embed-only we always compute (no cache read) so we never block on MongoDB when it's down.
        trust_remote = config.trust_remote_code or (model_id in MODELS_REQUIRING_TRUST_REMOTE_CODE)
        model = load_model_fn(model_name, trust_remote_code=trust_remote)
        corpus_embeddings = encode_texts_fn(
            model,
            corpus_texts,
            batch_size=config.batch_size,
            model_id=model_id,
            text_role="passage",
            recipe_mode=getattr(config, "recipe_mode", "standardized"),
            pooling=getattr(config, "embedding_pooling", "mean"),
            normalize=bool(getattr(config, "embedding_normalize", True)),
            max_seq_len=getattr(config, "embedding_max_seq_len", None),
            query_prefix=str(getattr(config, "embedding_query_prefix", "")),
            passage_prefix=str(getattr(config, "embedding_passage_prefix", "")),
            fail_on_missing_source=bool(getattr(config, "recipe_fail_on_missing_source", True)),
        )
        records = [
            {"run_id": run_id, "model_id": model_id, "chunk_id": uid, "embedding": corpus_embeddings[i].tolist()}
            for i, uid in enumerate(corpus_ids)
        ]
        save_cached_embeddings(run_id, model_id, records, mongo_uri, clear_existing=True)
        save_embedding_run_metadata(run_id, model_id, len(corpus_ids), mongo_uri)
        np.save(output_dir / "embeddings" / f"{model_id}_corpus.npy", corpus_embeddings)
    index_path = output_dir / "embeddings" / "corpus_index.json"
    corpus_index_payload = build_corpus_index_payload(
        run_id=run_id,
        substrate_version=config.substrate_version,
        corpus=corpus,
    )
    corpus_index_payload["corpus_recipe"] = {
        "min_chars": min_chars,
        "merge_chunks": bool(getattr(config, "merge_chunks", False)),
        "merge_max_chars": int(getattr(config, "merge_max_chars", 2000)),
    }
    index_path.write_text(
        json.dumps(corpus_index_payload, indent=2),
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
    embed_profile = getattr(flags, "embedding_enrichment_profile", None) or ""
    corpus_texts = [build_embedding_text(c, embed_profile or None) for c in corpus]
    id_to_source_ids: Dict[str, List[str]] = {
        c["id"]: list(c.get("source_unit_ids", [c["id"]])) for c in corpus
    }

    substrate_version = _compose_embedding_substrate_version(
        base_substrate_version=config.substrate_version,
        embed_profile=str(embed_profile or ""),
        recipe_mode=str(getattr(config, "recipe_mode", "standardized")),
    )
    if eval_only_run_id:
        run_id = eval_only_run_id
        logger.info("Eval-only: using run_id=%s (no embedding)", run_id)
    else:
        run_id = substrate_run_id(config.document_id, corpus_ids, substrate_version)
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


def _metric_payload_from_scored_reviews(
    metrics: Any,
    *,
    existing_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    existing_result = existing_result or {}
    updated = dict(existing_result)
    updated.update(
        {
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
            "embedding_time_sec": float(existing_result.get("embedding_time_sec", 0.0) or 0.0),
            "scoring_time_sec": float(existing_result.get("scoring_time_sec", 0.0) or 0.0),
        }
    )
    return updated


def _sync_query_reviews_with_gold(
    *,
    retrieved_chunks_by_model: Dict[str, List[Dict[str, Any]]],
    grounded_queries: List[Dict[str, Any]],
) -> None:
    query_by_id = {str(q.get("id") or ""): q for q in grounded_queries if q.get("id")}
    for reviews in retrieved_chunks_by_model.values():
        for review in reviews:
            qid = str(review.get("query_id") or "")
            query = query_by_id.get(qid)
            if query is None:
                continue
            review["gold_unit_ids"] = list(query.get("gold_unit_ids") or [])
            review["required_gold"] = list(query.get("required_gold") or [])
            review["supporting_gold"] = list(query.get("supporting_gold") or [])


def _rescore_from_query_reviews(
    *,
    retrieved_chunks_by_model: Dict[str, List[Dict[str, Any]]],
    grounded_queries: List[Dict[str, Any]],
    top_k: List[int],
    existing_results_by_model: Dict[str, Dict[str, Any]],
) -> tuple[Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    query_by_id = {str(q.get("id") or ""): q for q in grounded_queries if q.get("id")}
    results_by_model: Dict[str, Dict[str, Any]] = {}
    per_query_by_model: Dict[str, List[Dict[str, Any]]] = {}
    for model_id, query_reviews in retrieved_chunks_by_model.items():
        model_queries: List[Dict[str, Any]] = []
        ranked_lists: List[List[str]] = []
        score_lists: List[List[float]] = []
        ranked_source_id_lists: List[List[List[str]]] = []
        for review in query_reviews:
            qid = str(review.get("query_id") or "")
            query = query_by_id.get(qid)
            if query is None:
                continue
            retrieved = review.get("retrieved") or []
            model_queries.append(query)
            ranked_lists.append([str(item.get("chunk_id") or "") for item in retrieved if str(item.get("chunk_id") or "").strip()])
            score_lists.append([float(item.get("score") or 0.0) for item in retrieved if str(item.get("chunk_id") or "").strip()])
            ranked_source_id_lists.append(
                [
                    [str(x).strip() for x in (item.get("source_unit_ids") or [item.get("chunk_id")]) if str(x).strip()]
                    for item in retrieved
                    if str(item.get("chunk_id") or "").strip()
                ]
            )
        metrics = score_retrieval(
            model_queries,
            ranked_lists,
            score_lists,
            top_k,
            ranked_source_id_lists=ranked_source_id_lists,
        )
        results_by_model[model_id] = _metric_payload_from_scored_reviews(
            metrics,
            existing_result=existing_results_by_model.get(model_id, {}),
        )
        per_query_by_model[model_id] = metrics.per_query
        for review, per_query in zip(query_reviews, metrics.per_query):
            review["first_gold_rank"] = per_query.get("first_gold_rank")
            review["failure_type"] = per_query.get("failure_type", "")
    return results_by_model, per_query_by_model


def _queries_for_artifact(queries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{k: v for k, v in query.items() if k not in INTERNAL_QUERY_KEYS} for query in queries]


def _validate_query_batch_contracts(
    *,
    query_batches: List[str],
    resolved_queries: List[Dict[str, Any]],
    corpus_ids: List[str],
    run_id: str,
    substrate_version: Optional[str],
    corpus_content_fingerprint: str,
    corpus_index_sha256: str,
    output_dir: Path,
    allow_mismatch: bool,
) -> tuple[List[Dict[str, Any]], List[str]]:
    validations: List[Dict[str, Any]] = []
    contract_paths: List[str] = []
    for batch_path_str in query_batches:
        benchmark_path = Path(batch_path_str).resolve()
        batch_queries = [
            query
            for query in resolved_queries
            if str(query.get("_source_path") or "") == str(benchmark_path)
        ]
        alignment_summary = benchmark_query_alignment_summary(
            batch_queries,
            corpus_ids=corpus_ids,
        )
        contract_path = benchmark_contract_sidecar_path(benchmark_path)
        if not contract_path.exists():
            validation = {
                "benchmark_path": str(benchmark_path),
                "contract_path": str(contract_path),
                "valid": False,
                "errors": [f"benchmark contract missing: {contract_path}"],
                "alignment_summary": alignment_summary,
            }
        else:
            validation = validate_benchmark_contract(
                benchmark_path=benchmark_path,
                contract_path=contract_path,
                query_count=len(batch_queries),
                run_id=run_id,
                substrate_version=substrate_version,
                corpus_fingerprint=corpus_fingerprint_from_ids(corpus_ids),
                corpus_content_fingerprint=corpus_content_fingerprint,
                corpus_index_sha256=corpus_index_sha256,
                alignment_summary=alignment_summary,
            )
            contract_paths.append(str(contract_path))
        validations.append(validation)
        if not validation.get("valid"):
            message = "; ".join(validation.get("errors", []))
            if allow_mismatch:
                logger.warning("Benchmark contract override active for %s: %s", benchmark_path, message)
            else:
                raise ValueError(f"Benchmark contract validation failed for {benchmark_path}: {message}")

    validation_payload = {
        "version": "retrieval_lab_benchmark_contract_validation_v1",
        "run_id": run_id,
        "corpus_fingerprint": corpus_fingerprint_from_ids(corpus_ids),
        "corpus_content_fingerprint": corpus_content_fingerprint,
        "corpus_index_sha256": corpus_index_sha256,
        "query_batches": validations,
    }
    (output_dir / "benchmark_contract_validation.json").write_text(
        json.dumps(validation_payload, indent=2),
        encoding="utf-8",
    )
    return validations, contract_paths


def _run_experiment(config: ExperimentConfig, eval_only_run_id: Optional[str] = None) -> str:
    """Full eval: load or use existing embeddings, run queries, score, report."""
    config.resolve_paths(Path.cwd())
    embed_only = False
    eval_only = eval_only_run_id is not None
    config.validate(embed_only=embed_only, eval_only=eval_only)
    if config.retrieval_mode != "bm25":
        _, _, model_registry = _load_model_registry()
        missing_models = [m for m in config.models if m not in model_registry]
        if missing_models:
            raise ValueError(
                "Preflight failed: models missing from active registry: "
                + ", ".join(missing_models)
            )
    _set_seed(config.seed)
    retrieval_mode = config.retrieval_mode
    t_stage_start = time.perf_counter()
    flags = read_run_flags(config)
    expansion_cfg = read_expansion_config(config)
    qe_flags = read_query_enhancement_config(config)
    qe_profile = None
    qe_cache = None
    if qe_flags.enabled and qe_flags.mode != "none" and qe_flags.profile_path:
        from retrieval_lab.query_enhancement.profile import load_profile, validate_profile
        from retrieval_lab.query_enhancement.cache import QueryEnhancementCache
        qe_profile = load_profile(qe_flags.profile_path)
        errors = validate_profile(qe_profile)
        if errors:
            raise ValueError(f"Query enhancement profile validation failed: {errors}")
        qe_cache = QueryEnhancementCache(qe_profile.cache.cache_dir, enabled=qe_profile.cache.enabled)
        logger.info(
            "Query enhancement enabled: mode=%s fusion=%s profile=%s hash=%s",
            qe_flags.mode, qe_flags.fusion_mode, qe_profile.profile_id, qe_profile.compute_hash()[:16],
        )
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

    chunk_quality_summary = summarize_chunk_quality(corpus)
    logger.info(
        "Chunk quality: units=%d short<=40=%d (%.3f) short<=80=%d (%.3f) duplicate_rate=%.3f",
        chunk_quality_summary["total_units"],
        chunk_quality_summary["short_le_40"],
        chunk_quality_summary["short_le_40_rate"],
        chunk_quality_summary["short_le_80"],
        chunk_quality_summary["short_le_80_rate"],
        chunk_quality_summary["duplicate_text_entry_rate"],
    )
    if config.chunk_quality_gate_enabled:
        violations = evaluate_chunk_quality_gate(
            chunk_quality_summary,
            max_short_le_40_rate=config.chunk_quality_max_short_le_40_rate,
            max_short_le_80_rate=config.chunk_quality_max_short_le_80_rate,
            max_duplicate_text_entry_rate=config.chunk_quality_max_duplicate_text_entry_rate,
        )
        if violations:
            raise ValueError(
                "Chunk quality gate failed: "
                + "; ".join(violations)
                + " (set chunk_quality_gate_enabled=false to bypass explicitly)"
            )

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

    baseline_failure_types = _load_baseline_failure_types(
        baseline_metrics_path=config.baseline_metrics_path,
        retrieval_mode=retrieval_mode,
        models=config.models,
    )
    if baseline_failure_types is not None:
        logger.info(
            "Conditional QE enabled from baseline failures: %d/%d queries eligible for enhancement",
            len(baseline_failure_types),
            len(grounded_queries),
        )

    experiment_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    experiment_id = (
        str(config.experiment_id_override).strip()
        if getattr(config, "experiment_id_override", None) and str(config.experiment_id_override).strip()
        else f"{config.experiment_name}_{experiment_ts}"
    )
    output_dir = Path(config.output_dir) / experiment_id
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "embeddings").mkdir(exist_ok=True)
    corpus_content_fingerprint = corpus_content_fingerprint_from_units(corpus)
    corpus_recipe = _build_corpus_recipe(config, flags, expansion_cfg)
    corpus_index_payload = build_corpus_index_payload(
        run_id=run_id,
        substrate_version=config.substrate_version,
        corpus=corpus,
    )
    corpus_index_payload["corpus_recipe"] = dict(corpus_recipe)
    corpus_index_path = output_dir / "embeddings" / "corpus_index.json"
    corpus_index_path.write_text(json.dumps(corpus_index_payload, indent=2), encoding="utf-8")
    corpus_index_sha256 = _sha256_file(corpus_index_path)
    (output_dir / "chunk_quality_gate.json").write_text(
        json.dumps(chunk_quality_summary, indent=2),
        encoding="utf-8",
    )
    benchmark_lint_summary: Optional[Dict[str, Any]] = None
    benchmark_contract_validations, benchmark_contract_paths = _validate_query_batch_contracts(
        query_batches=config.query_batches,
        resolved_queries=flat_queries,
        corpus_ids=corpus_ids,
        run_id=run_id,
        substrate_version=config.substrate_version,
        corpus_content_fingerprint=corpus_content_fingerprint,
        corpus_index_sha256=corpus_index_sha256,
        output_dir=output_dir,
        allow_mismatch=bool(getattr(config, "allow_benchmark_contract_mismatch", False)),
    )
    input_snapshot_paths = _snapshot_query_batch_inputs(
        output_dir=output_dir,
        query_batch_paths=list(config.query_batches),
        query_batch_contract_paths=benchmark_contract_paths,
    )

    results_by_model: Dict[str, Dict[str, Any]] = {}
    per_query_by_model: Dict[str, List[Dict[str, Any]]] = {}
    retrieved_chunks_by_model: Dict[str, List[Dict[str, Any]]] = {}
    all_grounding_audit: List[Dict[str, Any]] = grounding_audit.copy()
    embedding_provenance_by_model: Dict[str, Any] = {}
    bm25_index_trace: Optional[Dict[str, Any]] = None
    hybrid_contribution_by_model: Dict[str, Any] = {}
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

    # Benchmark linting (minimal-anchor hygiene).
    try:
        from retrieval_lab.benchmark_lint import lint_flat_queries

        benchmark_lint_summary = lint_flat_queries(flat_queries)
        (output_dir / "benchmark_lint.json").write_text(
            json.dumps(benchmark_lint_summary, indent=2),
            encoding="utf-8",
        )
        if int(benchmark_lint_summary.get("n_issues", 0)) > 0:
            logger.warning(
                "Benchmark lint: %d issue(s). See %s",
                int(benchmark_lint_summary.get("n_issues", 0)),
                output_dir / "benchmark_lint.json",
            )
    except Exception as e:
        logger.warning("Benchmark lint failed (non-fatal): %s", e)

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
            qe_profile=qe_profile,
            qe_mode=qe_flags.mode if qe_flags.enabled else "none",
            qe_fusion_mode=qe_flags.fusion_mode if qe_flags.enabled else "only_add",
            qe_only_add=qe_flags.only_add if qe_flags.enabled else None,
            qe_enhance_query_ids=baseline_failure_types,
            qe_cache=qe_cache,
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
            qe_profile=qe_profile,
            qe_mode=qe_flags.mode if qe_flags.enabled else "none",
            qe_fusion_mode=qe_flags.fusion_mode if qe_flags.enabled else "only_add",
            qe_only_add=qe_flags.only_add if qe_flags.enabled else None,
            qe_enhance_query_ids=baseline_failure_types,
            qe_cache=qe_cache,
        )
        results_by_model = dense_out["results_by_model"]
        per_query_by_model = dense_out["per_query_by_model"]
        retrieved_chunks_by_model = dense_out["retrieved_chunks_by_model"]
        all_grounding_audit = dense_out["all_grounding_audit"]
        pairing_instrumentation_by_model = dense_out["pairing_instrumentation_by_model"]
        embedding_provenance_by_model = dense_out.get("embedding_provenance_by_model", {})
        bm25_index_trace = dense_out.get("bm25_index_trace")
        hybrid_contribution_by_model = dense_out.get("hybrid_contribution_by_model", {})
    stage_timing_sec["retrieval_and_scoring"] = time.perf_counter() - t_retrieval

    auto_gold_review_payload: Optional[Dict[str, Any]] = None
    review_queue_payload: Optional[List[Dict[str, Any]]] = None
    auto_gold_review_summary: Optional[Dict[str, Any]] = None
    pre_review_surface: Optional[Dict[str, Any]] = None
    post_review_surface: Optional[Dict[str, Any]] = None
    agr = getattr(config, "auto_gold_review", None)
    if agr is not None and agr.enabled:
        pre_review_surface = {
            "label": "pre_review_manual",
            "display_name": "Pre-review / manual benchmark surface",
            "results_by_model": copy.deepcopy(results_by_model),
            "per_query_by_model": copy.deepcopy(per_query_by_model),
            "retrieved_chunks_by_model": copy.deepcopy(retrieved_chunks_by_model),
            "grounded_queries": _queries_for_artifact(copy.deepcopy(grounded_queries)),
        }
        if not os.environ.get("OPENAI_API_KEY"):
            logger.warning("Auto gold review enabled but OPENAI_API_KEY is not set; skipping.")
            auto_gold_review_summary = {"enabled": True, "skipped": True, "reason": "missing_openai_api_key"}
        else:
            review_model_id = str(agr.retrieval_model_id or "").strip() or next(iter(retrieved_chunks_by_model.keys()), "")
            query_reviews_for_review = retrieved_chunks_by_model.get(review_model_id)
            if not review_model_id or not isinstance(query_reviews_for_review, list):
                logger.warning("Auto gold review skipped: retrieval review model not available: %s", review_model_id)
                auto_gold_review_summary = {
                    "enabled": True,
                    "skipped": True,
                    "reason": f"missing_retrieval_model:{review_model_id or 'none'}",
                }
            else:
                try:
                    from retrieval_lab.auto_gold_review.evaluate import evaluate_gold_reviews
                    from retrieval_lab.auto_gold_review.openai_reviewer import OpenAIGoldChunkReviewer
                    from retrieval_lab.benchmark_lint import lint_flat_queries

                    reviewer = OpenAIGoldChunkReviewer(model_id=agr.llm_model_id)
                    t_auto_gold = time.perf_counter()
                    auto_gold_review_payload = evaluate_gold_reviews(
                        query_reviews=query_reviews_for_review,
                        grounded_queries=flat_queries,
                        reviewer=reviewer,
                        candidate_top_k=int(agr.candidate_top_k),
                        max_queries=int(agr.max_queries),
                        max_chars_per_chunk=int(agr.max_chars_per_chunk),
                        max_required_gold=int(agr.max_required_gold),
                        max_supporting_gold=int(agr.max_supporting_gold),
                        challenge_sample_size=int(agr.review_queue_challenge_sample_size),
                        max_required_overlap=int(agr.max_required_overlap),
                    )
                    applied_queries, apply_summary = apply_gold_recommendations_to_queries(
                        flat_queries,
                        auto_gold_review_payload.get("recommendations", []),
                    )
                    auto_gold_review_payload["metadata"] = {
                        "enabled": True,
                        "llm_model_id": agr.llm_model_id,
                        "retrieval_model_id": review_model_id,
                        "candidate_top_k": int(agr.candidate_top_k),
                        "persist_benchmark": bool(agr.persist_benchmark),
                    }
                    auto_gold_review_payload["apply_summary"] = apply_summary
                    review_queue_payload = list(auto_gold_review_payload.get("review_queue") or [])
                    auto_gold_review_summary = {
                        "enabled": True,
                        "skipped": False,
                        "llm_model_id": agr.llm_model_id,
                        "retrieval_model_id": review_model_id,
                        "candidate_top_k": int(agr.candidate_top_k),
                        "queries_reviewed": int(auto_gold_review_payload.get("summary", {}).get("queries_reviewed", 0) or 0),
                        "queries_applied": int(apply_summary.get("queries_applied", 0) or 0),
                        "queries_needing_human_review": int(
                            auto_gold_review_payload.get("summary", {}).get("queries_needing_human_review", 0) or 0
                        ),
                        "queue_size": len(review_queue_payload),
                    }
                    flat_queries = applied_queries
                    grounded_queries = applied_queries
                    _sync_query_reviews_with_gold(
                        retrieved_chunks_by_model=retrieved_chunks_by_model,
                        grounded_queries=grounded_queries,
                    )
                    results_by_model, per_query_by_model = _rescore_from_query_reviews(
                        retrieved_chunks_by_model=retrieved_chunks_by_model,
                        grounded_queries=grounded_queries,
                        top_k=config.top_k,
                        existing_results_by_model=results_by_model,
                    )
                    benchmark_lint_summary = lint_flat_queries(flat_queries)
                    (output_dir / "benchmark_lint.json").write_text(
                        json.dumps(benchmark_lint_summary, indent=2),
                        encoding="utf-8",
                    )
                    post_review_surface = {
                        "label": "post_review_applied",
                        "display_name": "Post-review / auto-applied benchmark surface",
                        "results_by_model": copy.deepcopy(results_by_model),
                        "per_query_by_model": copy.deepcopy(per_query_by_model),
                        "retrieved_chunks_by_model": copy.deepcopy(retrieved_chunks_by_model),
                        "grounded_queries": _queries_for_artifact(copy.deepcopy(grounded_queries)),
                    }
                    stage_timing_sec["auto_gold_review"] = time.perf_counter() - t_auto_gold
                except Exception as e:
                    logger.warning("Auto gold review failed (non-fatal): %s", e, exc_info=True)
                    auto_gold_review_summary = {"enabled": True, "skipped": True, "reason": f"error:{e}"}

    # Optional: answer-generation evaluation pass (OpenAI-backed).
    answer_eval_payload: Optional[Dict[str, Any]] = None
    if getattr(config, "answer_evaluation", None) is not None and config.answer_evaluation.enabled:
        if not os.environ.get("OPENAI_API_KEY"):
            logger.warning("Answer evaluation enabled but OPENAI_API_KEY is not set; skipping.")
            answer_eval_payload = {"enabled": True, "skipped": True, "reason": "missing_openai_api_key"}
        else:
            try:
                from retrieval_lab.answer_eval.evaluate import evaluate_answers_for_model
                from retrieval_lab.answer_eval.openai_generator import OpenAIAnswerGenerator

                ae = config.answer_evaluation
                eval_top_k = int(ae.eval_top_k) if int(ae.eval_top_k) > 0 else (max(config.top_k) if config.top_k else 20)
                eval_models = list(ae.eval_models or [])
                if not eval_models:
                    # Default: evaluate the first retrieval model only (cost-bounded).
                    first = next(iter(retrieved_chunks_by_model.keys()), None)
                    eval_models = [first] if first else []

                gen = OpenAIAnswerGenerator(model_id=ae.llm_model_id)
                per_model: Dict[str, Any] = {}
                for model_id in eval_models:
                    if not model_id:
                        continue
                    qr = retrieved_chunks_by_model.get(model_id)
                    if not isinstance(qr, list):
                        continue
                    per_model[model_id] = evaluate_answers_for_model(
                        query_reviews=qr,
                        grounded_queries=grounded_queries,
                        top_k=eval_top_k,
                        generator=gen,
                        max_queries=int(ae.max_queries),
                        max_chars_per_unit=int(ae.max_chars_per_unit),
                    )
                    # Attach summary into metrics payload for easy inspection.
                    if model_id in results_by_model:
                        results_by_model[model_id]["answer_eval_summary"] = per_model[model_id].get("summary", {})

                answer_eval_payload = {
                    "enabled": True,
                    "skipped": False,
                    "llm_model_id": ae.llm_model_id,
                    "eval_top_k": eval_top_k,
                    "max_queries": int(ae.max_queries),
                    "eval_models": eval_models,
                    "by_retrieval_model": per_model,
                }
                (output_dir / "answer_eval.json").write_text(
                    json.dumps(answer_eval_payload, indent=2),
                    encoding="utf-8",
                )
            except Exception as e:
                logger.warning("Answer evaluation failed (non-fatal): %s", e, exc_info=True)
                answer_eval_payload = {"enabled": True, "skipped": True, "reason": f"error:{e}"}

    # Diagnostics: failure rescue rate vs baseline + head stability (top-K equality) vs baseline.
    tail_rerank_diagnostics: Dict[str, Dict[str, Any]] = {}
    if config.baseline_metrics_path:
        try:
            baseline_per_query = json.loads(Path(config.baseline_metrics_path).with_name("per_query.json").read_text(encoding="utf-8"))
        except Exception:
            baseline_per_query = None
        try:
            baseline_chunks_path = Path(config.baseline_metrics_path).with_name("retrieved_chunks.json")
            baseline_retrieved = json.loads(baseline_chunks_path.read_text(encoding="utf-8")) if baseline_chunks_path.exists() else None
        except Exception:
            baseline_retrieved = None

        if isinstance(baseline_per_query, dict) and retrieved_chunks_by_model:
            eval_k = max(config.top_k) if config.top_k else 0
            prefix_lock_n = int(getattr(qe_flags.only_add, "prefix_lock_n", eval_k or 20))
            for model_id, cur_rows in per_query_by_model.items():
                base_rows = baseline_per_query.get(model_id)
                if not isinstance(base_rows, list) or not isinstance(cur_rows, list):
                    continue
                base_by_qid = {str(r.get("query_id")): r for r in base_rows if isinstance(r, dict) and r.get("query_id")}
                cur_by_qid = {str(r.get("query_id")): r for r in cur_rows if isinstance(r, dict) and r.get("query_id")}
                failures = 0
                rescued = 0
                for qid, br in base_by_qid.items():
                    ft = str(br.get("failure_type") or "")
                    if ft not in ("retrieval_miss", "rank_miss"):
                        continue
                    failures += 1
                    cr = cur_by_qid.get(qid, {})
                    if str(cr.get("failure_type") or "") == "hit":
                        rescued += 1

                head_total = 0
                head_equal = 0
                if isinstance(baseline_retrieved, dict):
                    base_chunks = ((baseline_retrieved.get("by_model") or {}).get(model_id) if model_id != "bm25" else (baseline_retrieved.get("by_model") or {}).get("bm25"))
                    cur_chunks = (retrieved_chunks_by_model.get(model_id) if model_id in retrieved_chunks_by_model else (retrieved_chunks_by_model.get("bm25") if model_id == "bm25" else None))
                    if isinstance(base_chunks, list) and isinstance(cur_chunks, list):
                        base_top = {str(r.get("query_id")): [x.get("chunk_id") for x in (r.get("retrieved") or [])[:prefix_lock_n]] for r in base_chunks if isinstance(r, dict)}
                        cur_top = {str(r.get("query_id")): [x.get("chunk_id") for x in (r.get("retrieved") or [])[:prefix_lock_n]] for r in cur_chunks if isinstance(r, dict)}
                        for qid, btop in base_top.items():
                            if not qid or qid not in cur_top:
                                continue
                            head_total += 1
                            if btop == cur_top[qid]:
                                head_equal += 1

                tail_rerank_diagnostics[model_id] = {
                    "baseline_failures": failures,
                    "rescued_failures": rescued,
                    "rescued_pct": (rescued / failures) if failures else 0.0,
                    "head_stability_total": head_total,
                    "head_stability_equal": head_equal,
                    "head_stability_rate": (head_equal / head_total) if head_total else None,
                    "eval_k": eval_k,
                    "prefix_lock_n": prefix_lock_n,
                }

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
        "recipe_mode": getattr(config, "recipe_mode", "standardized"),
        "embedding_pooling": getattr(config, "embedding_pooling", "mean"),
        "embedding_normalize": bool(getattr(config, "embedding_normalize", True)),
        "embedding_max_seq_len": getattr(config, "embedding_max_seq_len", None),
        "embedding_similarity_metric": getattr(config, "embedding_similarity_metric", "cosine"),
        "embedding_query_prefix": getattr(config, "embedding_query_prefix", ""),
        "embedding_passage_prefix": getattr(config, "embedding_passage_prefix", ""),
        "recipe_fail_on_missing_source": bool(getattr(config, "recipe_fail_on_missing_source", True)),
        "chunk_quality_gate_enabled": bool(getattr(config, "chunk_quality_gate_enabled", False)),
        "chunk_quality_max_short_le_40_rate": float(getattr(config, "chunk_quality_max_short_le_40_rate", 0.10)),
        "chunk_quality_max_short_le_80_rate": float(getattr(config, "chunk_quality_max_short_le_80_rate", 0.20)),
        "chunk_quality_max_duplicate_text_entry_rate": float(
            getattr(config, "chunk_quality_max_duplicate_text_entry_rate", 0.05)
        ),
        "min_chars": flags.min_chars,
        "merge_chunks": bool(flags.merge_chunks),
        "merge_max_chars": int(flags.merge_max_chars),
        "baseline_metrics_path": config.baseline_metrics_path,
        "expand_context": flags.expand_context,
        "expand_context_n": flags.expand_context_n,
        "clause_family_projection": flags.clause_family_projection,
        "crossref_sidecar_expand": expansion_cfg.crossref_sidecar_expand,
        "co_retrieval_expand": flags.co_retrieval_expand,
        "a_prime_generate_minimal": flags.a_prime_generate_minimal,
        "dual_list_fusion": flags.dual_list_fusion,
        "dependency_pairing_expand": expansion_cfg.dependency_pairing_expand,
        "bm25_budget": config.bm25_budget,
        "dense_budget": config.dense_budget,
        "hybrid_fusion_method": config.hybrid_fusion_method,
        "cc_lambda": config.cc_lambda,
        "cc_bm25_normalization": config.cc_bm25_normalization,
        "bm25_enrichment_profile": config.bm25_enrichment_profile,
        "query_enhancement": {
            "enabled": qe_flags.enabled,
            "mode": qe_flags.mode,
            "fusion_mode": qe_flags.fusion_mode,
            "profile_id": qe_profile.profile_id if qe_profile else "",
            "profile_hash": qe_profile.compute_hash()[:16] if qe_profile else "",
            "only_add": {
                "baseline_keep_n": qe_flags.only_add.baseline_keep_n,
                "variant_k_per_query": qe_flags.only_add.variant_k_per_query,
                "admission_cutoff": qe_flags.only_add.admission_cutoff,
                "prefix_lock_n": getattr(qe_flags.only_add, "prefix_lock_n", qe_flags.only_add.baseline_keep_n),
                "tail_rerank": getattr(qe_flags.only_add, "tail_rerank", "none"),
                "tail_rerank_window": getattr(qe_flags.only_add, "tail_rerank_window", 50),
                "append_score_band": qe_flags.only_add.append_score_band,
                "rerank_union": qe_flags.only_add.rerank_union,
            },
        },
        "auto_gold_review": {
            "enabled": bool(getattr(config.auto_gold_review, "enabled", False)),
            "llm_model_id": getattr(config.auto_gold_review, "llm_model_id", ""),
            "candidate_top_k": int(getattr(config.auto_gold_review, "candidate_top_k", 20)),
            "retrieval_model_id": getattr(config.auto_gold_review, "retrieval_model_id", ""),
            "max_queries": int(getattr(config.auto_gold_review, "max_queries", 0)),
            "max_chars_per_chunk": int(getattr(config.auto_gold_review, "max_chars_per_chunk", 1600)),
            "max_required_gold": int(getattr(config.auto_gold_review, "max_required_gold", 5)),
            "max_supporting_gold": int(getattr(config.auto_gold_review, "max_supporting_gold", 5)),
            "review_queue_challenge_sample_size": int(
                getattr(config.auto_gold_review, "review_queue_challenge_sample_size", 10)
            ),
            "max_required_overlap": int(getattr(config.auto_gold_review, "max_required_overlap", 2)),
            "persist_benchmark": bool(getattr(config.auto_gold_review, "persist_benchmark", True)),
        },
        "allow_benchmark_contract_mismatch": bool(getattr(config, "allow_benchmark_contract_mismatch", False)),
        "corpus_fingerprint": corpus_index_payload.get("corpus_fingerprint", ""),
        "corpus_content_fingerprint": corpus_content_fingerprint,
        "corpus_index_sha256": corpus_index_sha256,
        "corpus_recipe": corpus_recipe,
    }
    experiment_doc = {
        "experiment_id": experiment_id,
        "experiment_name": config.experiment_name,
        "created_at": datetime.now(timezone.utc),
        "config": config_dict,
        "corpus_contract": {
            "corpus_fingerprint": corpus_index_payload.get("corpus_fingerprint", ""),
            "corpus_content_fingerprint": corpus_content_fingerprint,
            "corpus_index_path": str(corpus_index_path.resolve()),
            "corpus_index_sha256": corpus_index_sha256,
            "corpus_recipe": corpus_recipe,
        },
        "corpus_stats": corpus_stats,
        "grounding_summary": grounding_summary,
        "results": results_by_model,
        "stage_timing_sec": stage_timing_sec,
        "chunk_quality_summary": chunk_quality_summary,
        "benchmark_contracts": benchmark_contract_validations,
        "per_suite_results": results_by_model.get(model_list[0], {}).get("per_suite", {}) if model_list else {},
        "frozen": False,
    }
    if benchmark_lint_summary is not None:
        experiment_doc["benchmark_lint"] = benchmark_lint_summary
    if answer_eval_payload is not None:
        experiment_doc["answer_evaluation"] = answer_eval_payload
    if auto_gold_review_summary is not None:
        experiment_doc["auto_gold_review_summary"] = auto_gold_review_summary
    if pre_review_surface is not None:
        experiment_doc["evaluation_surfaces"] = ["pre_review_manual"]
    if post_review_surface is not None:
        experiment_doc["evaluation_surfaces"] = ["pre_review_manual", "post_review_applied"]
    if tail_rerank_diagnostics:
        experiment_doc["tail_rerank_diagnostics"] = tail_rerank_diagnostics
        for model_id, res in results_by_model.items():
            if model_id in tail_rerank_diagnostics:
                res["tail_rerank_diagnostics"] = tail_rerank_diagnostics[model_id]
    baseline_metrics = _load_baseline_metrics(config.baseline_metrics_path)
    baseline_failure_buckets = {
        model_id: model_payload.get("failure_bucket_counts", {})
        for model_id, model_payload in baseline_metrics.items()
    }
    if baseline_failure_buckets:
        experiment_doc["baseline_failure_buckets"] = baseline_failure_buckets
    if bm25_index_trace is not None:
        experiment_doc["bm25_index_trace"] = bm25_index_trace
    if hybrid_contribution_by_model:
        experiment_doc["hybrid_contribution_by_model"] = hybrid_contribution_by_model
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
    enhancement_attribution = None
    if qe_profile is not None and qe_flags.mode != "none":
        from retrieval_lab.query_enhancement.attribution import compute_enhancement_attribution
        first_model = next(iter(results_by_model), None)
        if first_model:
            enhancement_attribution = compute_enhancement_attribution(
                ranked_lists=[],
                baseline_ranked_lists=None,
                grounded_queries=grounded_queries,
            )
            enhancement_attribution["enhancement_mode"] = qe_flags.mode
            enhancement_attribution["profile_id"] = qe_profile.profile_id
            experiment_doc["enhancement_attribution"] = enhancement_attribution

    evaluation_surfaces: Optional[List[Dict[str, Any]]] = None
    benchmark_snapshots: Optional[Dict[str, Dict[str, Any]]] = None
    if pre_review_surface is not None:
        pre_review_surface["benchmark_contract"] = _build_surface_contract(
            benchmark_path=output_dir / f"benchmark.{pre_review_surface['label']}.json",
            queries=list(pre_review_surface.get("grounded_queries") or []),
            corpus_ids=corpus_ids,
            run_id=run_id,
            substrate_version=config.substrate_version,
            benchmark_kind="benchmark_projection",
            benchmark_surface=str(pre_review_surface["label"]),
            corpus_fingerprint=corpus_index_payload.get("corpus_fingerprint", ""),
            corpus_content_fingerprint=corpus_content_fingerprint,
            corpus_unit_count=len(corpus_ids),
            corpus_index_path=corpus_index_path,
            corpus_index_sha256=corpus_index_sha256,
            corpus_recipe=corpus_recipe,
            definition_snapshot_paths=input_snapshot_paths["definition_snapshot_paths"],
            definition_contract_snapshot_paths=input_snapshot_paths["contract_snapshot_paths"],
            lineage={"source_surface": "manual_input"},
        )
    if post_review_surface is not None:
        post_review_surface["benchmark_contract"] = _build_surface_contract(
            benchmark_path=output_dir / f"benchmark.{post_review_surface['label']}.json",
            queries=list(post_review_surface.get("grounded_queries") or []),
            corpus_ids=corpus_ids,
            run_id=run_id,
            substrate_version=config.substrate_version,
            benchmark_kind="post_review_projection",
            benchmark_surface=str(post_review_surface["label"]),
            corpus_fingerprint=corpus_index_payload.get("corpus_fingerprint", ""),
            corpus_content_fingerprint=corpus_content_fingerprint,
            corpus_unit_count=len(corpus_ids),
            corpus_index_path=corpus_index_path,
            corpus_index_sha256=corpus_index_sha256,
            corpus_recipe=corpus_recipe,
            definition_snapshot_paths=input_snapshot_paths["definition_snapshot_paths"],
            definition_contract_snapshot_paths=input_snapshot_paths["contract_snapshot_paths"],
            lineage={
                "source_surface": "pre_review_manual",
                "auto_gold_review_applied": True,
            },
        )
    if pre_review_surface is not None:
        evaluation_surfaces = [pre_review_surface]
        if post_review_surface is not None:
            evaluation_surfaces.append(post_review_surface)
    else:
        active_queries = _queries_for_artifact(copy.deepcopy(grounded_queries))
        benchmark_snapshots = {
            "active": {
                "queries": active_queries,
                "contract": _build_surface_contract(
                    benchmark_path=output_dir / "benchmark.active.json",
                    queries=active_queries,
                    corpus_ids=corpus_ids,
                    run_id=run_id,
                    substrate_version=config.substrate_version,
                    benchmark_kind="benchmark_projection",
                    benchmark_surface="active",
                    corpus_fingerprint=corpus_index_payload.get("corpus_fingerprint", ""),
                    corpus_content_fingerprint=corpus_content_fingerprint,
                    corpus_unit_count=len(corpus_ids),
                    corpus_index_path=corpus_index_path,
                    corpus_index_sha256=corpus_index_sha256,
                    corpus_recipe=corpus_recipe,
                    definition_snapshot_paths=input_snapshot_paths["definition_snapshot_paths"],
                    definition_contract_snapshot_paths=input_snapshot_paths["contract_snapshot_paths"],
                    lineage={"source_surface": "manual_input"},
                ),
            }
        }

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
        enhancement_attribution=enhancement_attribution,
        grounded_queries=grounded_queries,
        corpus=corpus,
        auto_gold_review_payload=auto_gold_review_payload,
        review_queue_payload=review_queue_payload,
        evaluation_surfaces=evaluation_surfaces,
        benchmark_snapshots=benchmark_snapshots,
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
    if bm25_index_trace is not None:
        (output_dir / "bm25_index_trace.json").write_text(
            json.dumps(bm25_index_trace, indent=2),
            encoding="utf-8",
        )
    if hybrid_contribution_by_model:
        (output_dir / "hybrid_contribution.json").write_text(
            json.dumps({"by_model": hybrid_contribution_by_model}, indent=2),
            encoding="utf-8",
        )
    if retrieved_chunks_by_model:
        logger.info("Retrieved chunks (for manual review): %s", paths.get("retrieved_chunks.json"))
    if embedding_provenance_by_model:
        (output_dir / "embedding_provenance.json").write_text(
            json.dumps(
                {
                    "version": "embedding_provenance_v1",
                    "run_id": run_id,
                    "recipe_mode": getattr(config, "recipe_mode", "standardized"),
                    "by_model": embedding_provenance_by_model,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    benchmark_projection_snapshot_paths = sorted(
        str(path.resolve())
        for name, path in paths.items()
        if name.startswith("benchmark.") and name.endswith(".json") and ".contract." not in name
    )
    prod_readiness_path: Optional[Path] = None
    try:
        if evaluation_surfaces:
            selected_surface = "post_review_applied" if post_review_surface is not None else str(evaluation_surfaces[0]["label"])
            selected_surface_payload = next(
                (surface for surface in evaluation_surfaces if str(surface.get("label") or "") == selected_surface),
                evaluation_surfaces[0],
            )
            selected_metrics_by_model = dict(selected_surface_payload.get("results_by_model") or {})
        else:
            selected_surface = "active"
            selected_metrics_by_model = results_by_model
        selected_model_id = next(iter(selected_metrics_by_model.keys()), "")
        projection_artifact_name = f"benchmark.{selected_surface}.json"
        contract_artifact_name = f"benchmark.{selected_surface}.contract.json"
        projection_artifact_path = paths.get(projection_artifact_name)
        contract_artifact_path = paths.get(contract_artifact_name)
        if projection_artifact_path is not None and contract_artifact_path is not None:
            prod_readiness = build_prod_readiness_artifact(
                experiment_id=experiment_id,
                experiment_name=config.experiment_name,
                run_id=run_id,
                selected_surface=selected_surface,
                selected_model_id=selected_model_id,
                benchmark_projection_path=str(projection_artifact_path),
                benchmark_projection_sha256=_sha256_file(projection_artifact_path),
                benchmark_contract_path=str(contract_artifact_path),
                benchmark_contract_sha256=_sha256_file(contract_artifact_path),
                corpus_fingerprint=corpus_index_payload.get("corpus_fingerprint", ""),
                corpus_content_fingerprint=corpus_content_fingerprint,
                corpus_index_path=str(corpus_index_path),
                corpus_index_sha256=corpus_index_sha256,
                contract_validations=benchmark_contract_validations,
                metrics_by_model=selected_metrics_by_model,
            )
            if not prod_readiness.get("promotion_ready"):
                raise ValueError("prod_readiness cannot be emitted from a contract-invalid run")
            prod_readiness_path = output_dir / "prod_readiness.json"
            prod_readiness_path.write_text(json.dumps(prod_readiness, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to write prod_readiness.json (non-fatal): %s", e)

    # Run manifest: file hashes + exact argv for reproducibility.
    try:
        from retrieval_lab.run_manifest import build_run_manifest

        manifest = build_run_manifest(
            experiment_id=experiment_id,
            argv=list(sys.argv),
            config_dict=config_dict,
            source_config_path=getattr(config, "source_config_path", None),
            query_batch_paths=list(config.query_batches),
            query_batch_contract_paths=benchmark_contract_paths,
            enhancement_profile_path=(qe_flags.profile_path if qe_flags.enabled else None),
            benchmark_definition_snapshot_paths=input_snapshot_paths["definition_snapshot_paths"],
            benchmark_projection_snapshot_paths=benchmark_projection_snapshot_paths,
            corpus_index_path=str(corpus_index_path),
            prod_readiness_path=str(prod_readiness_path) if prod_readiness_path is not None else None,
            run_keys={
                "run_id": run_id,
                "run_id_family": run_id_family,
                "retrieval_mode": retrieval_mode,
                "recipe_mode": getattr(config, "recipe_mode", "standardized"),
                "models": model_list,
            },
        )
        manifest_json = json.dumps(manifest, indent=2)
        (output_dir / "manifest.json").write_text(
            manifest_json,
            encoding="utf-8",
        )
        (output_dir / "run_manifest.json").write_text(
            manifest_json,
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("Failed to write manifest.json (non-fatal): %s", e)
    return experiment_id


def main() -> None:
    _load_dotenv_for_openai()
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
            top_k=[int(x) for x in (args.top_k or "1,3,5,10,20").split(",") if x.strip()],
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

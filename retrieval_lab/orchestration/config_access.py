"""Typed config accessors to replace repetitive getattr usage."""

from __future__ import annotations

from dataclasses import dataclass

from retrieval_lab.config import (
    CC_BM25_NORMALIZATION_DEFAULT,
    CC_LAMBDA_DEFAULT,
    HYBRID_FUSION_METHOD_DEFAULT,
)
from retrieval_lab.orchestration.expansion_pipeline import ExpansionConfig


@dataclass
class RunFlags:
    expand_context: bool
    expand_context_n: int
    unit_type_boost: float
    min_chars: int | None
    merge_chunks: bool
    merge_max_chars: int
    clause_family_projection: bool
    clause_family_window: int
    clause_family_max_units: int
    clause_family_direction: str
    a_prime_generate_minimal: bool
    dual_list_fusion: bool
    dual_list_ku: int
    dual_list_kf: int
    dual_list_kfinal: int
    dual_list_qu: int
    dual_list_family_window: int
    dual_list_family_max_units: int
    dual_list_family_direction: str
    parent_fetch_depth: int
    parent_fetch_cap: int
    parent_fetch_enabled: bool
    co_retrieval_expand: bool
    two_stage_retrieval: bool
    stage1_admission_k: int
    stage1_query_mode: str
    stage2_query_mode: str
    stage2_rerank_method: str
    raw_first_merge_rerank: bool
    raw_stage1_admission_k: int
    raw_merge_rerank_top_k: int
    raw_merge_score_floor: bool
    raw_merge_rank_floor: bool
    raw_merge_coverage_bonus: float
    bm25_budget: int | None
    dense_budget: int | None
    hybrid_fusion_method: str
    cc_lambda: float
    cc_bm25_normalization: str
    bm25_enrichment_profile: str | None
    embedding_enrichment_profile: str | None
    recipe_mode: str
    embedding_pooling: str
    embedding_normalize: bool
    embedding_max_seq_len: int | None
    embedding_similarity_metric: str
    embedding_query_prefix: str
    embedding_passage_prefix: str
    recipe_fail_on_missing_source: bool


def read_run_flags(config: object) -> RunFlags:
    return RunFlags(
        expand_context=bool(getattr(config, "expand_context", False)),
        expand_context_n=int(getattr(config, "expand_context_n", 1)),
        unit_type_boost=float(getattr(config, "unit_type_boost", 0.0)),
        min_chars=getattr(config, "min_chars", None),
        merge_chunks=bool(getattr(config, "merge_chunks", False)),
        merge_max_chars=int(getattr(config, "merge_max_chars", 2000)),
        clause_family_projection=bool(getattr(config, "clause_family_projection", False)),
        clause_family_window=int(getattr(config, "clause_family_window", 2)),
        clause_family_max_units=int(getattr(config, "clause_family_max_units", 6)),
        clause_family_direction=str(getattr(config, "clause_family_direction", "symmetric")),
        a_prime_generate_minimal=bool(getattr(config, "a_prime_generate_minimal", False)),
        dual_list_fusion=bool(getattr(config, "dual_list_fusion", False)),
        dual_list_ku=int(getattr(config, "dual_list_ku", 12)),
        dual_list_kf=int(getattr(config, "dual_list_kf", 12)),
        dual_list_kfinal=int(getattr(config, "dual_list_kfinal", 10)),
        dual_list_qu=int(getattr(config, "dual_list_qu", 6)),
        dual_list_family_window=int(getattr(config, "dual_list_family_window", 3)),
        dual_list_family_max_units=int(getattr(config, "dual_list_family_max_units", 6)),
        dual_list_family_direction=str(getattr(config, "dual_list_family_direction", "symmetric")),
        parent_fetch_depth=int(getattr(config, "parent_fetch_depth", 1)),
        parent_fetch_cap=int(getattr(config, "parent_fetch_cap", 2000)),
        parent_fetch_enabled=bool(getattr(config, "parent_fetch_enabled", False)),
        co_retrieval_expand=bool(getattr(config, "co_retrieval_expand", False)),
        two_stage_retrieval=bool(getattr(config, "two_stage_retrieval", False)),
        stage1_admission_k=int(getattr(config, "stage1_admission_k", 100)),
        stage1_query_mode=str(getattr(config, "stage1_query_mode", "question_plus_summary")),
        stage2_query_mode=str(getattr(config, "stage2_query_mode", "question_only")),
        stage2_rerank_method=str(getattr(config, "stage2_rerank_method", "dense")),
        raw_first_merge_rerank=bool(getattr(config, "raw_first_merge_rerank", False)),
        raw_stage1_admission_k=int(getattr(config, "raw_stage1_admission_k", 100)),
        raw_merge_rerank_top_k=int(getattr(config, "raw_merge_rerank_top_k", 20)),
        raw_merge_score_floor=bool(getattr(config, "raw_merge_score_floor", True)),
        raw_merge_rank_floor=bool(getattr(config, "raw_merge_rank_floor", True)),
        raw_merge_coverage_bonus=float(getattr(config, "raw_merge_coverage_bonus", 0.0)),
        bm25_budget=getattr(config, "bm25_budget", None),
        dense_budget=getattr(config, "dense_budget", None),
        hybrid_fusion_method=str(getattr(config, "hybrid_fusion_method", HYBRID_FUSION_METHOD_DEFAULT)),
        cc_lambda=float(getattr(config, "cc_lambda", CC_LAMBDA_DEFAULT)),
        cc_bm25_normalization=str(
            getattr(config, "cc_bm25_normalization", CC_BM25_NORMALIZATION_DEFAULT)
        ),
        bm25_enrichment_profile=getattr(config, "bm25_enrichment_profile", None),
        embedding_enrichment_profile=getattr(config, "embedding_enrichment_profile", None),
        recipe_mode=str(getattr(config, "recipe_mode", "standardized")),
        embedding_pooling=str(getattr(config, "embedding_pooling", "mean")),
        embedding_normalize=bool(getattr(config, "embedding_normalize", True)),
        embedding_max_seq_len=getattr(config, "embedding_max_seq_len", None),
        embedding_similarity_metric=str(getattr(config, "embedding_similarity_metric", "cosine")),
        embedding_query_prefix=str(getattr(config, "embedding_query_prefix", "")),
        embedding_passage_prefix=str(getattr(config, "embedding_passage_prefix", "")),
        recipe_fail_on_missing_source=bool(getattr(config, "recipe_fail_on_missing_source", True)),
    )


def read_expansion_config(config: object) -> ExpansionConfig:
    return ExpansionConfig(
        crossref_sidecar_expand=bool(getattr(config, "crossref_sidecar_expand", False)),
        crossref_expand_top_k=int(getattr(config, "crossref_expand_top_k", 10)),
        crossref_expand_per_hit=int(getattr(config, "crossref_expand_per_hit", 2)),
        crossref_expand_total_cap=int(getattr(config, "crossref_expand_total_cap", 20)),
        dependency_pairing_expand=bool(getattr(config, "dependency_pairing_expand", False)),
        dependency_pairing_emax=int(getattr(config, "dependency_pairing_emax", 6)),
    )


@dataclass
class OnlyAddFusionFlags:
    baseline_keep_n: int
    variant_k_per_query: int
    admission_cutoff: int
    prefix_lock_n: int
    tail_rerank: str
    tail_rerank_window: int
    append_score_band: float
    rerank_union: bool


@dataclass
class QueryEnhancementFlags:
    enabled: bool
    profile_path: str
    mode: str
    fusion_mode: str
    only_add: OnlyAddFusionFlags


def read_query_enhancement_config(config: object) -> QueryEnhancementFlags:
    qe = getattr(config, "query_enhancement", None)
    if qe is not None:
        oa = getattr(qe, "only_add", None)
        only_add = OnlyAddFusionFlags(
            baseline_keep_n=int(getattr(oa, "baseline_keep_n", 20)),
            variant_k_per_query=int(getattr(oa, "variant_k_per_query", 20)),
            admission_cutoff=int(getattr(oa, "admission_cutoff", 50)),
            prefix_lock_n=int(getattr(oa, "prefix_lock_n", 20)),
            tail_rerank=str(getattr(oa, "tail_rerank", "none")),
            tail_rerank_window=int(getattr(oa, "tail_rerank_window", 50)),
            append_score_band=float(getattr(oa, "append_score_band", 1e-6)),
            rerank_union=bool(getattr(oa, "rerank_union", False)),
        )
        return QueryEnhancementFlags(
            enabled=bool(getattr(qe, "enabled", False)),
            profile_path=str(getattr(qe, "profile_path", "")),
            mode=str(getattr(qe, "mode", "none")),
            fusion_mode=str(getattr(qe, "fusion_mode", "only_add")),
            only_add=only_add,
        )
    return QueryEnhancementFlags(
        enabled=False,
        profile_path="",
        mode="none",
        fusion_mode="only_add",
        only_add=OnlyAddFusionFlags(
            baseline_keep_n=20,
            variant_k_per_query=20,
            admission_cutoff=50,
            prefix_lock_n=20,
            tail_rerank="none",
            tail_rerank_window=50,
            append_score_band=1e-6,
            rerank_union=False,
        ),
    )

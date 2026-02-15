"""CLI override helpers for retrieval_lab.run_experiment."""

from __future__ import annotations

from typing import Any


def apply_cli_overrides(config: Any, args: Any) -> None:
    if hasattr(args, "experiment_name") and args.experiment_name:
        config.experiment_name = args.experiment_name
    if args.substrate:
        config.substrate_path = args.substrate
    if args.batches:
        config.query_batches = args.batches
    if args.models:
        config.models = args.models
    if args.top_k:
        config.top_k = [int(x) for x in args.top_k.split(",") if x.strip()]
    if hasattr(args, "rrf_k") and args.rrf_k is not None:
        config.rrf_k = args.rrf_k
    if hasattr(args, "merge_chunks") and args.merge_chunks is not None:
        config.merge_chunks = args.merge_chunks
    if hasattr(args, "merge_max_chars") and args.merge_max_chars is not None:
        config.merge_max_chars = args.merge_max_chars
    if hasattr(args, "min_chars") and args.min_chars is not None:
        config.min_chars = args.min_chars
    if hasattr(args, "seed"):
        config.seed = args.seed
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
    if hasattr(args, "bm25_tokenizer_mode"):
        config.bm25_tokenizer_mode = args.bm25_tokenizer_mode
    if hasattr(args, "bm25_k1"):
        config.bm25_k1 = args.bm25_k1
    if hasattr(args, "bm25_b"):
        config.bm25_b = args.bm25_b
    if hasattr(args, "bm25_query_mode"):
        config.bm25_query_mode = args.bm25_query_mode
    if hasattr(args, "bm25_query_weight_question"):
        config.bm25_query_weight_question = args.bm25_query_weight_question
    if hasattr(args, "bm25_query_weight_summary"):
        config.bm25_query_weight_summary = args.bm25_query_weight_summary
    if getattr(args, "two_stage_retrieval", False):
        config.two_stage_retrieval = True
    if hasattr(args, "stage1_admission_k"):
        config.stage1_admission_k = args.stage1_admission_k
    if hasattr(args, "stage1_query_mode"):
        config.stage1_query_mode = args.stage1_query_mode
    if hasattr(args, "stage2_query_mode"):
        config.stage2_query_mode = args.stage2_query_mode
    if hasattr(args, "stage2_rerank_method"):
        config.stage2_rerank_method = args.stage2_rerank_method
    if getattr(args, "raw_first_merge_rerank", False):
        config.raw_first_merge_rerank = True
    if hasattr(args, "raw_stage1_admission_k"):
        config.raw_stage1_admission_k = args.raw_stage1_admission_k
    if hasattr(args, "raw_merge_rerank_top_k"):
        config.raw_merge_rerank_top_k = args.raw_merge_rerank_top_k
    if hasattr(args, "raw_merge_score_floor") and args.raw_merge_score_floor is not None:
        config.raw_merge_score_floor = args.raw_merge_score_floor
    if hasattr(args, "raw_merge_rank_floor") and args.raw_merge_rank_floor is not None:
        config.raw_merge_rank_floor = args.raw_merge_rank_floor
    if hasattr(args, "raw_merge_coverage_bonus") and args.raw_merge_coverage_bonus is not None:
        config.raw_merge_coverage_bonus = args.raw_merge_coverage_bonus
    if hasattr(args, "baseline_metrics") and args.baseline_metrics:
        config.baseline_metrics_path = args.baseline_metrics

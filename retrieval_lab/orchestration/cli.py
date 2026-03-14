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
    if hasattr(args, "batch_size") and args.batch_size is not None:
        config.batch_size = int(args.batch_size)
    if args.output:
        config.output_dir = args.output
    if args.mongo_uri is not None:
        config.mongo_uri = args.mongo_uri
    if args.substrate_version is not None:
        config.substrate_version = args.substrate_version
    if getattr(args, "embedding_enrichment_profile", None) is not None:
        config.embedding_enrichment_profile = args.embedding_enrichment_profile
    if getattr(args, "recipe_mode", None) is not None:
        config.recipe_mode = args.recipe_mode
    if getattr(args, "embedding_pooling", None) is not None:
        config.embedding_pooling = args.embedding_pooling
    if getattr(args, "embedding_normalize", None) is not None:
        config.embedding_normalize = bool(args.embedding_normalize)
    if getattr(args, "embedding_max_seq_len", None) is not None:
        config.embedding_max_seq_len = int(args.embedding_max_seq_len)
    if getattr(args, "embedding_similarity_metric", None) is not None:
        config.embedding_similarity_metric = str(args.embedding_similarity_metric)
    if getattr(args, "embedding_query_prefix", None) is not None:
        config.embedding_query_prefix = str(args.embedding_query_prefix)
    if getattr(args, "embedding_passage_prefix", None) is not None:
        config.embedding_passage_prefix = str(args.embedding_passage_prefix)
    if getattr(args, "recipe_fail_on_missing_source", None) is not None:
        config.recipe_fail_on_missing_source = bool(args.recipe_fail_on_missing_source)
    if args.trust_remote_code:
        config.trust_remote_code = True
    if hasattr(args, "parent_fetch_depth") and args.parent_fetch_depth is not None:
        config.parent_fetch_depth = args.parent_fetch_depth
    if hasattr(args, "parent_fetch_cap") and args.parent_fetch_cap is not None:
        config.parent_fetch_cap = args.parent_fetch_cap
    if hasattr(args, "parent_fetch_enabled") and args.parent_fetch_enabled:
        config.parent_fetch_enabled = True
    if hasattr(args, "reranker") and args.reranker:
        config.reranker = args.reranker
    if getattr(args, "llm_rerank_enabled", False):
        config.llm_rerank_enabled = True
    if getattr(args, "llm_rerank_method", None) is not None:
        config.llm_rerank_method = str(args.llm_rerank_method)
    if getattr(args, "llm_rerank_model", None) is not None:
        config.llm_rerank_model = str(args.llm_rerank_model)
    if getattr(args, "llm_rerank_admission_k", None) is not None:
        config.llm_rerank_admission_k = int(args.llm_rerank_admission_k)
    if getattr(args, "llm_rerank_text_char_limit", None) is not None:
        config.llm_rerank_text_char_limit = int(args.llm_rerank_text_char_limit)
    if getattr(args, "llm_rerank_prompt_template_id", None) is not None:
        config.llm_rerank_prompt_template_id = str(args.llm_rerank_prompt_template_id)
    if getattr(args, "llm_rerank_max_output_tokens", None) is not None:
        config.llm_rerank_max_output_tokens = int(args.llm_rerank_max_output_tokens)
    if getattr(args, "llm_rerank_cache_dir", None) is not None:
        config.llm_rerank_cache_dir = str(args.llm_rerank_cache_dir)
    if getattr(args, "clause_family_projection", False):
        config.clause_family_projection = True
    if getattr(args, "crossref_sidecar_expand", False):
        config.crossref_sidecar_expand = True
    if hasattr(args, "crossref_expand_top_k") and args.crossref_expand_top_k is not None:
        config.crossref_expand_top_k = args.crossref_expand_top_k
    if hasattr(args, "crossref_expand_per_hit") and args.crossref_expand_per_hit is not None:
        config.crossref_expand_per_hit = args.crossref_expand_per_hit
    if hasattr(args, "crossref_expand_total_cap") and args.crossref_expand_total_cap is not None:
        config.crossref_expand_total_cap = args.crossref_expand_total_cap
    if getattr(args, "a_prime_generate_minimal", False):
        config.a_prime_generate_minimal = True
    if getattr(args, "dual_list_fusion", False):
        config.dual_list_fusion = True
    if hasattr(args, "dual_list_ku") and args.dual_list_ku is not None:
        config.dual_list_ku = args.dual_list_ku
    if hasattr(args, "dual_list_kf") and args.dual_list_kf is not None:
        config.dual_list_kf = args.dual_list_kf
    if hasattr(args, "dual_list_kfinal") and args.dual_list_kfinal is not None:
        config.dual_list_kfinal = args.dual_list_kfinal
    if hasattr(args, "dual_list_qu") and args.dual_list_qu is not None:
        config.dual_list_qu = args.dual_list_qu
    if getattr(args, "dependency_pairing_expand", False):
        config.dependency_pairing_expand = True
    if hasattr(args, "dependency_pairing_emax") and args.dependency_pairing_emax is not None:
        config.dependency_pairing_emax = args.dependency_pairing_emax
    if getattr(args, "retrieval_mode", None) is not None:
        config.retrieval_mode = str(args.retrieval_mode)
    if getattr(args, "bm25_budget", None) is not None:
        config.bm25_budget = int(args.bm25_budget)
    if getattr(args, "dense_budget", None) is not None:
        config.dense_budget = int(args.dense_budget)
    if getattr(args, "hybrid_fusion_method", None) is not None:
        config.hybrid_fusion_method = str(args.hybrid_fusion_method)
    if getattr(args, "cc_lambda", None) is not None:
        config.cc_lambda = float(args.cc_lambda)
    if getattr(args, "cc_bm25_normalization", None) is not None:
        config.cc_bm25_normalization = str(args.cc_bm25_normalization)
    if getattr(args, "bm25_enrichment_profile", None) is not None:
        config.bm25_enrichment_profile = str(args.bm25_enrichment_profile)
    if hasattr(args, "bm25_tokenizer_mode") and args.bm25_tokenizer_mode is not None:
        config.bm25_tokenizer_mode = args.bm25_tokenizer_mode
    if hasattr(args, "bm25_k1") and args.bm25_k1 is not None:
        config.bm25_k1 = args.bm25_k1
    if hasattr(args, "bm25_b") and args.bm25_b is not None:
        config.bm25_b = args.bm25_b
    if hasattr(args, "bm25_query_mode") and args.bm25_query_mode is not None:
        config.bm25_query_mode = args.bm25_query_mode
    if hasattr(args, "bm25_query_weight_question") and args.bm25_query_weight_question is not None:
        config.bm25_query_weight_question = args.bm25_query_weight_question
    if hasattr(args, "bm25_query_weight_summary") and args.bm25_query_weight_summary is not None:
        config.bm25_query_weight_summary = args.bm25_query_weight_summary
    if getattr(args, "two_stage_retrieval", False):
        config.two_stage_retrieval = True
    if hasattr(args, "stage1_admission_k") and args.stage1_admission_k is not None:
        config.stage1_admission_k = args.stage1_admission_k
    if hasattr(args, "stage1_query_mode") and args.stage1_query_mode is not None:
        config.stage1_query_mode = args.stage1_query_mode
    if hasattr(args, "stage2_query_mode") and args.stage2_query_mode is not None:
        config.stage2_query_mode = args.stage2_query_mode
    if hasattr(args, "stage2_rerank_method") and args.stage2_rerank_method is not None:
        config.stage2_rerank_method = args.stage2_rerank_method
    if getattr(args, "raw_first_merge_rerank", False):
        config.raw_first_merge_rerank = True
    if hasattr(args, "raw_stage1_admission_k") and args.raw_stage1_admission_k is not None:
        config.raw_stage1_admission_k = args.raw_stage1_admission_k
    if hasattr(args, "raw_merge_rerank_top_k") and args.raw_merge_rerank_top_k is not None:
        config.raw_merge_rerank_top_k = args.raw_merge_rerank_top_k
    if hasattr(args, "raw_merge_score_floor") and args.raw_merge_score_floor is not None:
        config.raw_merge_score_floor = args.raw_merge_score_floor
    if hasattr(args, "raw_merge_rank_floor") and args.raw_merge_rank_floor is not None:
        config.raw_merge_rank_floor = args.raw_merge_rank_floor
    if hasattr(args, "raw_merge_coverage_bonus") and args.raw_merge_coverage_bonus is not None:
        config.raw_merge_coverage_bonus = args.raw_merge_coverage_bonus
    if hasattr(args, "baseline_metrics") and args.baseline_metrics:
        config.baseline_metrics_path = args.baseline_metrics
    if getattr(args, "answer_eval", False):
        config.answer_evaluation.enabled = True
    if getattr(args, "answer_model", None) is not None:
        config.answer_evaluation.llm_model_id = str(args.answer_model or "")
        if not config.answer_evaluation.enabled:
            config.answer_evaluation.enabled = True
    if getattr(args, "answer_top_k", None) is not None:
        config.answer_evaluation.eval_top_k = int(args.answer_top_k or 0)
        if not config.answer_evaluation.enabled:
            config.answer_evaluation.enabled = True
    if getattr(args, "answer_max_queries", None) is not None:
        config.answer_evaluation.max_queries = int(args.answer_max_queries)
        if not config.answer_evaluation.enabled:
            config.answer_evaluation.enabled = True
    if getattr(args, "answer_max_chars_per_unit", None) is not None:
        config.answer_evaluation.max_chars_per_unit = int(args.answer_max_chars_per_unit)
        if not config.answer_evaluation.enabled:
            config.answer_evaluation.enabled = True
    if getattr(args, "answer_eval_models", None) is not None and args.answer_eval_models:
        config.answer_evaluation.eval_models = [
            s.strip() for s in str(args.answer_eval_models).split(",") if s.strip()
        ]
        if not config.answer_evaluation.enabled:
            config.answer_evaluation.enabled = True
    if getattr(args, "auto_gold_review", False):
        config.auto_gold_review.enabled = True
    if getattr(args, "auto_gold_model", None) is not None:
        config.auto_gold_review.llm_model_id = str(args.auto_gold_model or "")
        if not config.auto_gold_review.enabled:
            config.auto_gold_review.enabled = True
    if getattr(args, "auto_gold_retrieval_model", None) is not None:
        config.auto_gold_review.retrieval_model_id = str(args.auto_gold_retrieval_model or "")
    if getattr(args, "auto_gold_top_k", None) is not None:
        config.auto_gold_review.candidate_top_k = int(args.auto_gold_top_k)
        if not config.auto_gold_review.enabled:
            config.auto_gold_review.enabled = True
    if getattr(args, "auto_gold_max_queries", None) is not None:
        config.auto_gold_review.max_queries = int(args.auto_gold_max_queries)
    if getattr(args, "auto_gold_max_chars_per_chunk", None) is not None:
        config.auto_gold_review.max_chars_per_chunk = int(args.auto_gold_max_chars_per_chunk)
    if getattr(args, "auto_gold_challenge_sample", None) is not None:
        config.auto_gold_review.review_queue_challenge_sample_size = int(args.auto_gold_challenge_sample)
    if getattr(args, "auto_gold_max_required_overlap", None) is not None:
        config.auto_gold_review.max_required_overlap = int(args.auto_gold_max_required_overlap)
    if getattr(args, "allow_benchmark_contract_mismatch", False):
        config.allow_benchmark_contract_mismatch = True
    if getattr(args, "enhancement_mode", None) is not None:
        config.query_enhancement.enabled = args.enhancement_mode != "none"
        config.query_enhancement.mode = args.enhancement_mode
    if getattr(args, "enhancement_profile", None) is not None:
        config.query_enhancement.profile_path = args.enhancement_profile
        if not config.query_enhancement.enabled and config.query_enhancement.mode == "none":
            config.query_enhancement.enabled = True
            config.query_enhancement.mode = "dict"
    if getattr(args, "enhancement_fusion_mode", None) is not None:
        config.query_enhancement.fusion_mode = args.enhancement_fusion_mode
    if getattr(args, "onlyadd_prefix_lock_n", None) is not None:
        config.query_enhancement.only_add.prefix_lock_n = int(args.onlyadd_prefix_lock_n)
    if getattr(args, "onlyadd_tail_rerank", None) is not None:
        config.query_enhancement.only_add.tail_rerank = str(args.onlyadd_tail_rerank)
    if getattr(args, "onlyadd_tail_rerank_window", None) is not None:
        config.query_enhancement.only_add.tail_rerank_window = int(args.onlyadd_tail_rerank_window)

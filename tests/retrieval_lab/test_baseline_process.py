from __future__ import annotations

from argparse import Namespace

from evals.v1_baseline.baseline_process import (
    MODE_A_RAW_ONLY,
    MODE_B_MERGED_ONLY,
    MODE_C_RAW_FIRST_MERGE_RERANK,
    build_baseline_run_specs,
)
from retrieval_lab.orchestration.cli import apply_cli_overrides


class _DummyConfig:
    def __init__(self) -> None:
        self.experiment_name = "x"
        self.merge_chunks = True
        self.merge_max_chars = 2000
        self.min_chars = None


def test_build_baseline_run_specs_c_only() -> None:
    specs = build_baseline_run_specs(
        include_comparators=False,
        raw_stage1_admission_k=100,
        raw_merge_coverage_bonus=0.0,
    )
    assert specs
    assert all(spec.mode == MODE_C_RAW_FIRST_MERGE_RERANK for spec in specs)
    assert all("--raw-first-merge-rerank" in spec.cli_overrides for spec in specs)


def test_build_baseline_run_specs_with_comparators_includes_abc() -> None:
    specs = build_baseline_run_specs(
        include_comparators=True,
        raw_stage1_admission_k=100,
        raw_merge_coverage_bonus=0.0,
    )
    modes = {spec.mode for spec in specs}
    assert MODE_A_RAW_ONLY in modes
    assert MODE_B_MERGED_ONLY in modes
    assert MODE_C_RAW_FIRST_MERGE_RERANK in modes


def test_apply_cli_overrides_supports_merge_and_experiment_name() -> None:
    config = _DummyConfig()
    args = Namespace(
        experiment_name="swords_wizardry_hybrid_c_raw_first_merge_rerank",
        substrate=None,
        batches=None,
        models=None,
        top_k=None,
        rrf_k=None,
        seed=None,
        output=None,
        mongo_uri=None,
        substrate_version=None,
        trust_remote_code=False,
        parent_fetch_depth=1,
        parent_fetch_cap=2000,
        parent_fetch_enabled=False,
        reranker=None,
        clause_family_projection=False,
        crossref_sidecar_expand=False,
        crossref_expand_top_k=10,
        crossref_expand_per_hit=2,
        crossref_expand_total_cap=20,
        a_prime_generate_minimal=False,
        dual_list_fusion=False,
        dual_list_ku=12,
        dual_list_kf=12,
        dual_list_kfinal=10,
        dual_list_qu=6,
        dependency_pairing_expand=False,
        dependency_pairing_emax=6,
        bm25_tokenizer_mode="basic",
        bm25_k1=1.5,
        bm25_b=0.75,
        bm25_query_mode="question_only",
        bm25_query_weight_question=1,
        bm25_query_weight_summary=1,
        two_stage_retrieval=False,
        stage1_admission_k=100,
        stage1_query_mode="question_plus_summary",
        stage2_query_mode="question_only",
        stage2_rerank_method="dense",
        merge_chunks=False,
        merge_max_chars=1800,
        min_chars=120,
        raw_first_merge_rerank=False,
        raw_stage1_admission_k=100,
        raw_merge_rerank_top_k=20,
        raw_merge_score_floor=None,
        raw_merge_rank_floor=None,
        raw_merge_coverage_bonus=None,
        baseline_metrics=None,
    )
    apply_cli_overrides(config, args)
    assert config.experiment_name == "swords_wizardry_hybrid_c_raw_first_merge_rerank"
    assert config.merge_chunks is False
    assert config.merge_max_chars == 1800
    assert config.min_chars == 120

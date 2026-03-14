from __future__ import annotations

from pathlib import Path

from retrieval_lab.report import generate_report, write_report_artifacts


def test_generate_report_includes_raw_merge_diagnostics_section() -> None:
    report = generate_report(
        experiment_id="exp1",
        experiment_name="x",
        config={
            "substrate_path": "out/DnD_PHB_5.5",
            "document_id": "DnD_PHB_5.5",
            "models": ["all-mpnet-base-v2"],
            "top_k": [1, 3, 10],
            "retrieval_mode": "hybrid",
        },
        corpus_stats={"unit_count": 10, "page_count": 2},
        grounding_summary={"total_queries": 1, "grounded": 1, "ungrounded": 0, "method": "page_anchored"},
        results_by_model={
            "all-mpnet-base-v2": {
                "mrr": 0.5,
                "ndcg_at_k": {10: 0.5},
                "gold_in_candidates": 1.0,
                "gold_in_candidates_true_ceiling": 1.0,
                "full_set_hit_at_k": {10: 1.0},
                "required_full_set_hit_at_k": {10: 1.0},
                "rank_of_last_required_mean": 4.0,
                "recall_at_k": {1: 0.5, 3: 1.0, 10: 1.0},
                "hit_at_k": {1: 1.0, 3: 1.0, 10: 1.0},
                "grounding_coverage": 1.0,
                "failure_counts": {"hit": 1, "retrieval_miss": 0, "rank_miss": 0, "grounding_failure": 0},
                "failure_bucket_counts": {"success": 1, "gold_not_in_candidates": 0},
                "per_suite": {},
                "per_tier": {},
                "raw_merge_rerank_diagnostics": {
                    "enabled": True,
                    "monotonic_rank_violations_total": 0,
                    "raw_top_missing_in_final_topk_total": 0,
                    "per_query": [],
                },
            }
        },
        grounding_audit=[],
        per_query_by_model={},
        created_at="2026-02-14T00:00:00Z",
        baseline_failure_buckets=None,
        stage_timing_sec=None,
    )
    assert "Raw-First Merge-Rerank Diagnostics" in report
    assert "H3 (no-demotion):" in report
    assert "Supported (0 monotonic rank violations in this run)." in report


def test_generate_report_includes_auto_gold_review_section() -> None:
    report = generate_report(
        experiment_id="exp1",
        experiment_name="x",
        config={
            "substrate_path": "out/Pathfinder2ePlayerCore",
            "document_id": "Pathfinder2ePlayerCore",
            "models": ["all-mpnet-base-v2"],
            "top_k": [1, 3, 10, 20],
            "retrieval_mode": "dense",
        },
        corpus_stats={"unit_count": 10, "page_count": 2},
        grounding_summary={"total_queries": 1, "grounded": 1, "ungrounded": 0, "method": "page_anchored"},
        results_by_model={
            "all-mpnet-base-v2": {
                "mrr": 0.5,
                "ndcg_at_k": {10: 0.5},
                "gold_in_candidates": 1.0,
                "gold_in_candidates_true_ceiling": 1.0,
                "full_set_hit_at_k": {10: 1.0},
                "required_full_set_hit_at_k": {10: 1.0},
                "rank_of_last_required_mean": 2.0,
                "recall_at_k": {1: 0.5, 3: 1.0, 10: 1.0, 20: 1.0},
                "hit_at_k": {1: 1.0, 3: 1.0, 10: 1.0, 20: 1.0},
                "grounding_coverage": 1.0,
                "failure_counts": {"hit": 1, "retrieval_miss": 0, "rank_miss": 0, "grounding_failure": 0},
                "failure_bucket_counts": {"success": 1},
                "per_suite": {},
                "per_tier": {},
            }
        },
        grounding_audit=[],
        per_query_by_model={},
        created_at="2026-03-05T00:00:00Z",
        auto_gold_review_summary={
            "enabled": True,
            "skipped": False,
            "llm_model_id": "gpt-4o-mini",
            "retrieval_model_id": "all-mpnet-base-v2",
            "candidate_top_k": 20,
            "queries_reviewed": 50,
            "queries_applied": 46,
            "queries_needing_human_review": 12,
            "queue_size": 15,
        },
    )
    assert "Auto Gold Review" in report
    assert "Queries applied" in report
    assert "auto_gold_review.json" in report


def test_write_report_artifacts_splits_pre_and_post_review_surfaces(tmp_path: Path) -> None:
    experiment_doc = {
        "created_at": "2026-03-06T00:00:00Z",
        "auto_gold_review_summary": {
            "enabled": True,
            "skipped": False,
            "llm_model_id": "gpt-5.4",
            "retrieval_model_id": "all-mpnet-base-v2",
            "candidate_top_k": 20,
            "queries_reviewed": 21,
            "queries_applied": 21,
            "queries_needing_human_review": 0,
            "queue_size": 0,
        },
    }
    surface_results = {
        "all-mpnet-base-v2": {
            "mrr": 0.5,
            "ndcg_at_k": {10: 0.5},
            "gold_in_candidates": 1.0,
            "gold_in_candidates_true_ceiling": 1.0,
            "full_set_hit_at_k": {10: 1.0},
            "required_full_set_hit_at_k": {10: 1.0},
            "rank_of_last_required_mean": 2.0,
            "recall_at_k": {1: 0.5, 3: 1.0, 10: 1.0},
            "hit_at_k": {1: 1.0, 3: 1.0, 10: 1.0},
            "grounding_coverage": 1.0,
            "failure_counts": {"hit": 1, "retrieval_miss": 0, "rank_miss": 0, "grounding_failure": 0},
            "failure_bucket_counts": {"success": 1},
            "per_suite": {},
            "per_tier": {},
        }
    }
    paths = write_report_artifacts(
        output_dir=tmp_path,
        experiment_id="exp1",
        experiment_name="dual",
        config={
            "substrate_path": "out/SW",
            "document_id": "Swords&Wizardry",
            "substrate_version": "v3",
            "run_id": "run_123",
            "models": ["all-mpnet-base-v2"],
            "top_k": [1, 3, 10],
            "retrieval_mode": "hybrid",
        },
        corpus_stats={"unit_count": 10, "page_count": 2},
        grounding_summary={"total_queries": 1, "grounded": 1, "ungrounded": 0, "method": "page_anchored"},
        results_by_model=surface_results,
        grounding_audit=[],
        per_query_by_model={"all-mpnet-base-v2": []},
        experiment_doc=experiment_doc,
        retrieved_chunks_by_model={"all-mpnet-base-v2": []},
        evaluation_surfaces=[
            {
                "label": "pre_review_manual",
                "display_name": "Pre-review / manual benchmark surface",
                "results_by_model": surface_results,
                "per_query_by_model": {"all-mpnet-base-v2": []},
                "retrieved_chunks_by_model": {"all-mpnet-base-v2": []},
                "grounded_queries": [{"id": "q1"}],
                "benchmark_contract": {"version": "v1"},
            },
            {
                "label": "post_review_applied",
                "display_name": "Post-review / auto-applied benchmark surface",
                "results_by_model": surface_results,
                "per_query_by_model": {"all-mpnet-base-v2": []},
                "retrieved_chunks_by_model": {"all-mpnet-base-v2": []},
                "grounded_queries": [{"id": "q1"}],
                "benchmark_contract": {"version": "v1"},
            },
        ],
    )

    assert (tmp_path / "REPORT.pre_review_manual.md").exists()
    assert (tmp_path / "REPORT.post_review_applied.md").exists()
    assert (tmp_path / "metrics.pre_review_manual.json").exists()
    assert (tmp_path / "metrics.post_review_applied.json").exists()
    assert (tmp_path / "benchmark.pre_review_manual.contract.json").exists()
    assert (tmp_path / "benchmark.post_review_applied.contract.json").exists()
    assert not (tmp_path / "metrics.json").exists()
    overview = (tmp_path / "REPORT.md").read_text(encoding="utf-8")
    assert "There is intentionally no unlabeled `metrics.json`" in overview
    assert "REPORT.pre_review_manual.md" in overview
    assert "REPORT.post_review_applied.md" in overview
    assert "evaluation_surfaces.json" in paths


def test_write_report_artifacts_writes_clean_and_full_working_set_surfaces(tmp_path: Path) -> None:
    surface_results = {
        "all-mpnet-base-v2": {
            "mrr": 0.5,
            "ndcg_at_k": {10: 0.5},
            "gold_in_candidates": 1.0,
            "gold_in_candidates_true_ceiling": 1.0,
            "full_set_hit_at_k": {10: 1.0},
            "required_full_set_hit_at_k": {10: 1.0},
            "rank_of_last_required_mean": 2.0,
            "recall_at_k": {1: 0.5, 3: 1.0, 10: 1.0},
            "hit_at_k": {1: 1.0, 3: 1.0, 10: 1.0},
            "grounding_coverage": 1.0,
            "failure_counts": {"hit": 1, "retrieval_miss": 0, "rank_miss": 0, "grounding_failure": 0},
            "failure_bucket_counts": {"success": 1},
            "per_suite": {},
            "per_tier": {},
        }
    }
    paths = write_report_artifacts(
        output_dir=tmp_path,
        experiment_id="exp1",
        experiment_name="dual",
        config={
            "substrate_path": "out/PF2E",
            "document_id": "PathCore",
            "substrate_version": "v1",
            "run_id": "run_123",
            "models": ["all-mpnet-base-v2"],
            "top_k": [1, 3, 10],
            "retrieval_mode": "dense",
        },
        corpus_stats={"unit_count": 10, "page_count": 2},
        grounding_summary={"total_queries": 2, "grounded": 2, "ungrounded": 0, "method": "page_anchored"},
        results_by_model=surface_results,
        grounding_audit=[],
        per_query_by_model={"all-mpnet-base-v2": []},
        experiment_doc={"created_at": "2026-03-14T00:00:00Z"},
        retrieved_chunks_by_model={"all-mpnet-base-v2": []},
        evaluation_surfaces=[
            {
                "label": "full_working_set",
                "display_name": "Full working set",
                "results_by_model": surface_results,
                "per_query_by_model": {"all-mpnet-base-v2": []},
                "retrieved_chunks_by_model": {"all-mpnet-base-v2": []},
                "grounded_queries": [{"id": "q1", "benchmark_track": "ratified_core"}, {"id": "q2", "benchmark_track": "working_set"}],
                "benchmark_contract": {"version": "v1"},
            },
            {
                "label": "clean_subset",
                "display_name": "Clean subset",
                "results_by_model": surface_results,
                "per_query_by_model": {"all-mpnet-base-v2": []},
                "retrieved_chunks_by_model": {"all-mpnet-base-v2": []},
                "grounded_queries": [{"id": "q1", "benchmark_track": "ratified_core"}],
                "benchmark_contract": {"version": "v1"},
            },
        ],
    )

    assert (tmp_path / "REPORT.full_working_set.md").exists()
    assert (tmp_path / "REPORT.clean_subset.md").exists()
    assert (tmp_path / "metrics.full_working_set.json").exists()
    assert (tmp_path / "metrics.clean_subset.json").exists()
    overview = (tmp_path / "REPORT.md").read_text(encoding="utf-8")
    assert "REPORT.full_working_set.md" in overview
    assert "REPORT.clean_subset.md" in overview
    assert "evaluation_surfaces.json" in paths


def test_write_report_artifacts_writes_active_benchmark_snapshot(tmp_path: Path) -> None:
    paths = write_report_artifacts(
        output_dir=tmp_path,
        experiment_id="exp1",
        experiment_name="single",
        config={
            "substrate_path": "out/SW",
            "document_id": "Swords&Wizardry",
            "substrate_version": "v3",
            "run_id": "run_123",
            "models": ["all-mpnet-base-v2"],
            "top_k": [1, 3, 10],
            "retrieval_mode": "hybrid",
        },
        corpus_stats={"unit_count": 10, "page_count": 2},
        grounding_summary={"total_queries": 1, "grounded": 1, "ungrounded": 0, "method": "page_anchored"},
        results_by_model={
            "all-mpnet-base-v2": {
                "mrr": 0.5,
                "ndcg_at_k": {10: 0.5},
                "gold_in_candidates": 1.0,
                "gold_in_candidates_true_ceiling": 1.0,
                "full_set_hit_at_k": {10: 1.0},
                "required_full_set_hit_at_k": {10: 1.0},
                "rank_of_last_required_mean": 2.0,
                "recall_at_k": {1: 0.5, 3: 1.0, 10: 1.0},
                "hit_at_k": {1: 1.0, 3: 1.0, 10: 1.0},
                "grounding_coverage": 1.0,
                "failure_counts": {"hit": 1, "retrieval_miss": 0, "rank_miss": 0, "grounding_failure": 0},
                "failure_bucket_counts": {"success": 1},
                "per_suite": {},
                "per_tier": {},
            }
        },
        grounding_audit=[],
        per_query_by_model={"all-mpnet-base-v2": []},
        experiment_doc={"created_at": "2026-03-06T00:00:00Z"},
        benchmark_snapshots={
            "active": {
                "queries": [{"id": "q1", "gold_unit_ids": ["u1"]}],
                "contract": {"version": "retrieval_lab_benchmark_contract_v2"},
            }
        },
    )

    assert (tmp_path / "benchmark.active.json").exists()
    assert (tmp_path / "benchmark.active.contract.json").exists()
    assert "benchmark.active.json" in paths
    assert "benchmark.active.contract.json" in paths

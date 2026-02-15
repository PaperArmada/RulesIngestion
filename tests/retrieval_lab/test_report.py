from __future__ import annotations

from retrieval_lab.report import generate_report


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

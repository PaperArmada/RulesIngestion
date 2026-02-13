from __future__ import annotations

from retrieval_lab.metrics import compute_query_result, score_retrieval


def test_compute_query_result_retrieval_miss_bucket() -> None:
    result = compute_query_result(
        query_id="q1",
        ranked_ids=["u1", "u2"],
        scores=[0.8, 0.7],
        gold_unit_ids=["gold-1"],
        top_k_list=[1, 3],
    )
    assert result.failure_type == "retrieval_miss"
    assert result.failure_bucket == "gold_not_in_candidates"


def test_score_retrieval_basic_aggregates() -> None:
    grounded_queries = [
        {"id": "q1", "gold_unit_ids": ["u1"], "_suite": "core", "_tier": "T1"},
        {"id": "q2", "gold_unit_ids": ["u9"], "_suite": "core", "_tier": "T2"},
    ]
    ranked_lists = [["u1", "u2"], ["u2", "u3"]]
    score_lists = [[0.9, 0.1], [0.8, 0.2]]
    metrics = score_retrieval(grounded_queries, ranked_lists, score_lists, [1, 2])
    assert metrics.mrr > 0
    assert metrics.failure_bucket_counts["success"] == 1
    assert metrics.failure_bucket_counts["gold_not_in_candidates"] == 1

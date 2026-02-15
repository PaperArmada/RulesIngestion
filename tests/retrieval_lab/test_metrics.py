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
    assert metrics.ndcg_at_k[1] >= 0
    assert metrics.ndcg_at_k[2] >= metrics.ndcg_at_k[1]
    assert "required_recall_at_k" in metrics.__dict__
    assert metrics.rank_of_last_required_mean >= 0.0


def test_compute_query_result_grounding_failure_bucket() -> None:
    result = compute_query_result(
        query_id="q-no-gold",
        ranked_ids=["u1"],
        scores=[0.5],
        gold_unit_ids=[],
        top_k_list=[1, 3],
    )
    assert result.failure_type == "grounding_failure"
    assert result.failure_bucket == "no_gold_defined"


def test_score_retrieval_empty_input() -> None:
    metrics = score_retrieval([], [], [], [1, 3], corpus_ids=["u1", "u2"])
    assert metrics.mrr == 0.0
    assert metrics.candidate_set_size == 2


def test_score_retrieval_length_mismatch_raises() -> None:
    grounded_queries = [{"id": "q1", "gold_unit_ids": ["u1"]}]
    ranked_lists = [["u1"]]
    score_lists = []
    try:
        score_retrieval(grounded_queries, ranked_lists, score_lists, [1])
        assert False, "Expected ValueError for mismatched lengths"
    except ValueError as exc:
        assert "same length" in str(exc)


def test_compute_query_result_rank_of_last_required() -> None:
    result = compute_query_result(
        query_id="q-required",
        ranked_ids=["u1", "u2", "u3"],
        scores=[0.9, 0.8, 0.7],
        gold_unit_ids=["u1", "u2", "u3"],
        required_gold_ids=["u1", "u3"],
        supporting_gold_ids=["u2"],
        mode="multi_required",
        top_k_list=[1, 2, 3],
    )
    assert result.rank_of_last_required == 3
    assert result.required_full_set_hit_at_k[2] is False
    assert result.required_full_set_hit_at_k[3] is True

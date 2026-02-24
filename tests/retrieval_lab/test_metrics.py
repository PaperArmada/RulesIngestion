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


def test_merged_gold_id_matches_when_candidate_source_includes_merged_id() -> None:
    """Regression: gold IDs are merged corpus IDs; candidate_source_ids must include the
    merged id (cid) so that scoring matches. Without [cid] in the source set, gold at rank 1
    is wrongly classified as retrieval_miss."""
    merged_id = "61d87c8ac0a7262fa5282dc58f5b73ad0312dd7bf29aade835c8ee922b4aac86"
    source_only_ids = ["abc123", "def456"]  # pre-merge extraction IDs

    grounded = [
        {
            "id": "q1",
            "gold_unit_ids": [merged_id],
            "_required_gold": [merged_id],
            "_suite": "default",
            "_tier": "T1",
        }
    ]
    ranked_lists = [[merged_id, "other_unit"]]
    score_lists = [[0.72, 0.35]]
    top_k_list = [1, 3, 10]

    # Bug: candidate_source_ids only had source_unit_ids (no merged id) -> gold never matches
    source_lists_bug = [[source_only_ids, ["other_unit"]]]
    metrics_bug = score_retrieval(
        grounded, ranked_lists, score_lists, top_k_list,
        ranked_source_id_lists=source_lists_bug,
    )
    assert metrics_bug.per_query[0]["failure_type"] == "retrieval_miss"
    assert metrics_bug.per_query[0]["first_gold_rank"] is None

    # Fix: include merged id in each candidate's source set -> gold at rank 1 matches
    source_lists_fixed = [[[merged_id] + source_only_ids, ["other_unit"]]]
    metrics_fixed = score_retrieval(
        grounded, ranked_lists, score_lists, top_k_list,
        ranked_source_id_lists=source_lists_fixed,
    )
    assert metrics_fixed.per_query[0]["failure_type"] == "hit"
    assert metrics_fixed.per_query[0]["first_gold_rank"] == 1

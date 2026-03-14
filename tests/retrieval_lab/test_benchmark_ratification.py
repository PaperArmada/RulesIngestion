from __future__ import annotations

import pytest

from retrieval_lab.benchmark_ratification import (
    TRACK_RATIFIED_CORE,
    TRACK_WORKING_SET,
    filter_queries_by_ids,
    summarize_ratification,
)
from retrieval_lab.run_experiment import _enforce_ratified_query_policy


def test_summarize_ratification_flags_invalid_ratified_queries() -> None:
    queries = [
        {
            "id": "q-clean",
            "benchmark_track": TRACK_RATIFIED_CORE,
            "required_gold": ["alive"],
            "supporting_gold": [],
            "gold_unit_ids": ["alive"],
        },
        {
            "id": "q-pending",
            "benchmark_track": TRACK_RATIFIED_CORE,
            "_status": "pending",
            "required_gold": ["alive"],
            "gold_unit_ids": ["alive"],
        },
        {
            "id": "q-missing",
            "benchmark_track": TRACK_RATIFIED_CORE,
            "required_gold": ["missing"],
            "gold_unit_ids": ["missing"],
        },
        {
            "id": "q-large",
            "benchmark_track": TRACK_RATIFIED_CORE,
            "required_gold": ["u1", "u2", "u3"],
            "gold_unit_ids": ["u1", "u2", "u3"],
        },
        {
            "id": "q-working",
            "benchmark_track": TRACK_WORKING_SET,
            "_status": "pending",
            "required_gold": [],
            "gold_unit_ids": [],
        },
    ]

    summary = summarize_ratification(queries, corpus_ids=["alive", "u1", "u2", "u3"])

    assert summary["ratified_query_count"] == 4
    assert summary["ratified_clean_query_count"] == 1
    assert summary["clean_query_ids"] == ["q-clean"]
    assert set(summary["invalid_ratified_query_ids"]) == {"q-large", "q-missing", "q-pending"}
    codes = {issue["code"] for issue in summary["issues"]}
    assert "pending_status" in codes
    assert "gold_missing_in_corpus" in codes
    assert "required_gold_exceeds_cap" in codes


def test_enforce_ratified_query_policy_rejects_override_and_invalid_queries() -> None:
    summary = {
        "ratified_query_count": 2,
        "ratified_invalid_query_count": 1,
        "invalid_ratified_query_ids": ["q-bad"],
    }

    with pytest.raises(ValueError, match="allow_benchmark_contract_mismatch is forbidden"):
        _enforce_ratified_query_policy(
            summary=summary,
            allow_contract_override=True,
            stage_label="input",
        )

    with pytest.raises(ValueError, match="ratified benchmark validation failed during final"):
        _enforce_ratified_query_policy(
            summary=summary,
            allow_contract_override=False,
            stage_label="final",
        )


def test_summarize_ratification_uses_logical_anchor_count_for_cap() -> None:
    queries = [
        {
            "id": "q-expanded",
            "benchmark_track": TRACK_RATIFIED_CORE,
            "required_anchor_ids": ["anchor-1", "anchor-2"],
            "required_gold": ["u1", "u2", "u3", "u4"],
            "supporting_gold": ["u5"],
            "gold_unit_ids": ["u1", "u2", "u3", "u4", "u5"],
        }
    ]

    summary = summarize_ratification(queries, corpus_ids=["u1", "u2", "u3", "u4", "u5"])

    assert summary["ratified_clean_query_count"] == 1
    assert summary["invalid_ratified_query_ids"] == []
    assert summary["issues"] == []


def test_filter_queries_by_ids_returns_only_requested_queries() -> None:
    queries = [
        {"id": "q1", "benchmark_track": TRACK_RATIFIED_CORE},
        {"id": "q2", "benchmark_track": TRACK_WORKING_SET},
    ]

    filtered = filter_queries_by_ids(queries, ["q2"])

    assert filtered == [{"id": "q2", "benchmark_track": TRACK_WORKING_SET}]

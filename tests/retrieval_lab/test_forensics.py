"""Tests for gold_not_in_candidates forensics: bundles, miss classification, heatmap."""

from __future__ import annotations

from retrieval_lab.forensics import (
    MISS_BUCKET_UNCLASSIFIED,
    MISS_BUCKET_UNIT_SHAPE,
    build_forensics_artifacts,
    build_forensics_bundles,
    build_gold_retrievability_heatmap,
    build_miss_classification_summary,
    classify_miss,
)


def test_classify_miss_unit_shape() -> None:
    bundle = {
        "derived": {"shape_suspect": True},
        "gold_unit_features": [{"shape_suspect": True}],
    }
    assert classify_miss(bundle) == MISS_BUCKET_UNIT_SHAPE


def test_classify_miss_unclassified() -> None:
    bundle = {
        "derived": {"shape_suspect": False},
        "gold_unit_features": [{"shape_suspect": False}],
    }
    assert classify_miss(bundle) == MISS_BUCKET_UNCLASSIFIED


def test_build_forensics_bundles_only_misses() -> None:
    per_query_list = [
        {"query_id": "q1", "failure_bucket": "gold_not_in_candidates", "tier": "T2"},
        {"query_id": "q2", "failure_bucket": "success", "tier": "T1"},
    ]
    query_reviews = [
        {"query_id": "q1", "gold_unit_ids": ["g1"], "retrieved": [{"chunk_id": "u1", "score": 0.5, "rank": 1}]},
        {"query_id": "q2", "gold_unit_ids": ["g2"], "retrieved": [{"chunk_id": "g2", "score": 0.9, "rank": 1}]},
    ]
    grounded_queries = [
        {"id": "q1", "question": "What is X?", "gold_unit_ids": ["g1"], "required_gold": ["g1"]},
        {"id": "q2", "question": "What is Y?", "gold_unit_ids": ["g2"], "required_gold": ["g2"]},
    ]
    corpus = [
        {"id": "g1", "text": "Short.", "unit_type": "prose", "structural_path": ["Ch1"]},
    ]
    bundles = build_forensics_bundles(
        per_query_list=per_query_list,
        query_reviews=query_reviews,
        grounded_queries=grounded_queries,
        corpus=corpus,
        model_id="bm25",
    )
    assert len(bundles) == 1
    assert bundles[0]["query_id"] == "q1"
    assert bundles[0]["required_gold_ids"] == ["g1"]
    assert bundles[0]["query_text"] == "What is X?"
    assert len(bundles[0]["gold_unit_features"]) == 1
    assert bundles[0]["gold_unit_features"][0]["unit_id"] == "g1"
    assert bundles[0]["gold_unit_features"][0]["anomaly_flags"]["undersized"] is True
    assert bundles[0]["miss_bucket"] == MISS_BUCKET_UNIT_SHAPE


def test_build_miss_classification_summary() -> None:
    bundles = [
        {"miss_bucket": MISS_BUCKET_UNIT_SHAPE, "gold_unit_features": [{"unit_type": "table", "anomaly_flags": {"undersized": True, "table_or_list": True}}]},
        {"miss_bucket": MISS_BUCKET_UNIT_SHAPE, "gold_unit_features": [{"unit_type": "table", "anomaly_flags": {"undersized": False, "table_or_list": True}}]},
    ]
    summary = build_miss_classification_summary(bundles)
    assert summary["n_misses"] == 2
    assert summary["bucket_counts"][MISS_BUCKET_UNIT_SHAPE] == 2
    assert "unit_type:table" in summary["top_signatures"]
    assert summary["top_signatures"]["unit_type:table"] == 2


def test_build_gold_retrievability_heatmap() -> None:
    bundles = [
        {"query_id": "q1", "required_gold_ids": ["g1"], "retrieval_intermediates": {"bm25": [{"unit_id": "u1"}, {"unit_id": "u2"}]}},
    ]
    heatmap = build_gold_retrievability_heatmap(bundles, ["bm25"])
    assert len(heatmap) == 1
    assert heatmap[0]["query_id"] == "q1"
    assert heatmap[0]["gold_unit_id"] == "g1"
    assert heatmap[0]["admitted_by_channel"]["bm25"] is False


def test_build_forensics_artifacts_integration() -> None:
    per_query_by_model = {
        "bm25": [
            {"query_id": "q1", "failure_bucket": "gold_not_in_candidates", "tier": "T1"},
        ],
    }
    retrieved_chunks_by_model = {
        "bm25": [
            {"query_id": "q1", "gold_unit_ids": ["g1"], "retrieved": [{"chunk_id": "u1", "score": 0.3}]},
        ],
    }
    grounded_queries = [{"id": "q1", "question": "Where is X?", "gold_unit_ids": ["g1"], "required_gold": ["g1"]}]
    corpus = [{"id": "g1", "text": "Evidence here.", "unit_type": "prose", "structural_path": []}]
    out = build_forensics_artifacts(
        per_query_by_model=per_query_by_model,
        retrieved_chunks_by_model=retrieved_chunks_by_model,
        grounded_queries=grounded_queries,
        corpus=corpus,
    )
    assert "by_model" in out
    assert "bm25" in out["by_model"]
    assert len(out["by_model"]["bm25"]) == 1
    assert out["miss_classification"]["n_misses"] == 1
    assert len(out["gold_retrievability_heatmap"]) == 1

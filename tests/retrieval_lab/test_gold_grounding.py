from __future__ import annotations

from retrieval_lab.gold_grounding import (
    flatten_query_batches,
    ground_queries_page_anchored,
    resolve_gold_locations_to_current_corpus,
)


def test_flatten_query_batches_minimal_fixture(query_batch_minimal_path) -> None:
    flat, suites = flatten_query_batches([str(query_batch_minimal_path)])
    assert len(flat) == 1
    assert suites == ["default"]
    assert flat[0]["id"] == "q1"
    assert flat[0]["_suite"] == "default"


def test_ground_queries_page_anchored_prefilled_gold() -> None:
    queries = [
        {
            "id": "q1",
            "question": "What is initiative?",
            "expected_answer_summary": "Initiative determines turn order.",
            "source_page": 1,
            "gold_unit_ids": ["u1"],
        }
    ]
    units_by_page = {1: [{"id": "u1", "text": "Initiative determines turn order in combat."}]}
    grounded, audit = ground_queries_page_anchored(queries, units_by_page)
    assert grounded[0]["gold_unit_ids"] == ["u1"]
    assert audit[0]["method"] == "prefilled"


def test_flatten_query_batches_normalizes_required_and_supporting_gold(query_batch_minimal_path) -> None:
    # Fixture has legacy shape; this test verifies fallback still populates required contract fields.
    flat, _ = flatten_query_batches([str(query_batch_minimal_path)])
    assert "gold_unit_ids" in flat[0]
    assert "_required_gold" in flat[0]
    assert "_supporting_gold" in flat[0]
    assert flat[0]["_required_gold"] == flat[0]["gold_unit_ids"]


def test_resolve_gold_locations_to_current_corpus_maps_source_ids() -> None:
    folded_corpus = [
        {"id": "f1", "source_unit_ids": ["o1", "o2"], "page": 5, "structural_path": ["Combat"]},
        {"id": "f2", "source_unit_ids": ["o3"], "page": 6, "structural_path": ["Magic"]},
    ]
    merged_corpus = [
        {"id": "m1", "source_unit_ids": ["f1"], "page": 5, "structural_path": ["Combat"]},
        {"id": "m2", "source_unit_ids": ["f2"], "page": 6, "structural_path": ["Magic"]},
    ]
    queries = [
        {
            "id": "q1",
            "required_gold": ["old_gold"],
            "supporting_gold": [],
            "gold_locations": {
                "old_gold": {
                    "page": 5,
                    "structural_path": ["Combat"],
                    "source_unit_ids": ["o1", "o2"],
                }
            },
            "required_gold_rationale": {"old_gold": "core rule"},
        }
    ]
    resolved, summary = resolve_gold_locations_to_current_corpus(queries, folded_corpus, merged_corpus)
    assert summary["queries_with_gold_locations"] == 1
    assert resolved[0]["gold_unit_ids"] == ["m1"]
    assert resolved[0]["required_gold"] == ["m1"]
    assert resolved[0]["supporting_gold"] == []
    assert resolved[0]["_required_gold"] == ["m1"]
    assert resolved[0]["_supporting_gold"] == []
    assert resolved[0]["required_gold_rationale"] == {"m1": "core rule"}
    assert resolved[0]["gold_locations"]["m1"]["source_unit_ids"] == ["f1"]


def test_resolve_gold_locations_to_current_corpus_keeps_legacy_without_locations() -> None:
    folded_corpus = [{"id": "f1", "source_unit_ids": ["o1"]}]
    merged_corpus = [{"id": "m1", "source_unit_ids": ["f1"]}]
    queries = [{"id": "q1", "gold_unit_ids": ["legacy1"]}]

    resolved, summary = resolve_gold_locations_to_current_corpus(queries, folded_corpus, merged_corpus)
    assert summary["queries_legacy_only"] == 1
    assert resolved[0]["gold_unit_ids"] == ["legacy1"]

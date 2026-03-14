from __future__ import annotations

from retrieval_lab.auto_gold_review.evaluate import evaluate_gold_reviews
from retrieval_lab.auto_gold_review.mock_reviewer import MockGoldChunkReviewer
from retrieval_lab.auto_gold_review.schema import GoldReviewResponse
from retrieval_lab.gold_grounding import apply_gold_recommendations_to_queries


def test_auto_gold_review_builds_recommendations_and_queue() -> None:
    query_reviews = [
        {
            "query_id": "q1",
            "question": "What is Shove?",
            "expected_answer_summary": "Shove requirements and outcomes.",
            "retrieved": [
                {
                    "rank": 1,
                    "chunk_id": "u1",
                    "score": 0.91,
                    "text": "Shove requires a free hand.",
                    "page": 10,
                    "structural_path": ["Actions", "Shove"],
                    "source_unit_ids": ["raw1"],
                },
                {
                    "rank": 2,
                    "chunk_id": "u2",
                    "score": 0.90,
                    "text": "On success, you push the target.",
                    "page": 10,
                    "structural_path": ["Actions", "Shove"],
                    "source_unit_ids": ["raw2"],
                },
            ],
        },
        {
            "query_id": "q2",
            "question": "What is prone?",
            "expected_answer_summary": "Prone penalties.",
            "retrieved": [
                {
                    "rank": 1,
                    "chunk_id": "u3",
                    "score": 0.88,
                    "text": "Prone applies penalties to attacks.",
                    "page": 22,
                    "structural_path": ["Conditions", "Prone"],
                    "source_unit_ids": ["raw3"],
                }
            ],
        },
    ]
    grounded_queries = [
        {"id": "q1", "question": "What is Shove?", "expected_answer_summary": "Shove requirements and outcomes.", "question_type": "blind_eval"},
        {"id": "q2", "question": "What is prone?", "expected_answer_summary": "Prone penalties.", "question_type": "blind_eval"},
    ]
    reviewer = MockGoldChunkReviewer(
        responses_by_query_id={
            "q1": GoldReviewResponse(
                required_gold=["u1", "u2"],
                supporting_gold=[],
                required_gold_rationale={"u1": "Requirement anchor.", "u2": "Outcome anchor."},
                confidence="medium",
                review_flags=["close_second_choice"],
                needs_human_review=False,
            ),
            "q2": GoldReviewResponse(
                required_gold=[],
                supporting_gold=["u3"],
                required_gold_rationale={},
                confidence="low",
                review_flags=[],
                needs_human_review=True,
            ),
        }
    )

    payload = evaluate_gold_reviews(
        query_reviews=query_reviews,
        grounded_queries=grounded_queries,
        reviewer=reviewer,
        candidate_top_k=20,
        challenge_sample_size=1,
    )

    assert payload["summary"]["queries_reviewed"] == 2
    assert payload["summary"]["queries_applyable"] == 1
    rec_q1 = next(row for row in payload["recommendations"] if row["query_id"] == "q1")
    rec_q2 = next(row for row in payload["recommendations"] if row["query_id"] == "q2")
    assert rec_q1["gold_locations"]["u1"]["page"] == 10
    assert rec_q1["applyable"] is True
    assert rec_q2["applyable"] is False
    assert "no_clear_required_anchor" in rec_q2["review_flags"]
    queue_ids = {row["query_id"] for row in payload["review_queue"]}
    assert "q1" in queue_ids
    assert "q2" in queue_ids


def test_apply_gold_recommendations_to_queries_updates_gold_fields() -> None:
    queries = [
        {"id": "q1", "question": "What is Shove?", "required_gold": [], "supporting_gold": [], "gold_unit_ids": []},
        {"id": "q2", "question": "What is prone?", "required_gold": [], "supporting_gold": [], "gold_unit_ids": []},
    ]
    recommendations = [
        {
            "query_id": "q1",
            "applyable": True,
            "proposed_required_gold": ["u1"],
            "proposed_supporting_gold": ["u2"],
            "required_gold_rationale": {"u1": "Core anchor."},
            "gold_locations": {"u1": {"page": 10, "structural_path": ["Actions"]}, "u2": {"page": 10, "structural_path": ["Actions"]}},
        },
        {
            "query_id": "q2",
            "applyable": False,
            "proposed_required_gold": [],
            "proposed_supporting_gold": ["u3"],
            "required_gold_rationale": {},
            "gold_locations": {},
        },
    ]

    updated, summary = apply_gold_recommendations_to_queries(queries, recommendations)
    assert summary["queries_applied"] == 1
    assert updated[0]["required_gold"] == ["u1"]
    assert updated[0]["supporting_gold"] == ["u2"]
    assert updated[0]["gold_unit_ids"] == ["u1", "u2"]
    assert updated[1]["gold_unit_ids"] == []

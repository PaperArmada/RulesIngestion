from __future__ import annotations

from retrieval_lab.answer_eval.evaluate import evaluate_answers_for_model
from retrieval_lab.answer_eval.mock_generator import MockAnswerGenerator


def test_answer_eval_computes_required_cited_rate_and_refusal_accuracy() -> None:
    query_reviews = [
        {
            "query_id": "q1",
            "question": "What is initiative?",
            "expected_answer_summary": "Turn order.",
            "retrieved": [
                {"rank": 1, "chunk_id": "u1", "text": "Initiative is turn order."},
                {"rank": 2, "chunk_id": "u2", "text": "Other."},
            ],
        },
        {
            "query_id": "q2",
            "question": "What is AC?",
            "expected_answer_summary": "Armor class.",
            "retrieved": [
                {"rank": 1, "chunk_id": "u9", "text": "Not AC."},
            ],
        },
    ]
    grounded_queries = [
        {"id": "q1", "_required_gold": ["u1"]},
        {"id": "q2", "_required_gold": ["uX"]},
    ]

    out = evaluate_answers_for_model(
        query_reviews=query_reviews,
        grounded_queries=grounded_queries,
        top_k=1,
        generator=MockAnswerGenerator(),
        max_queries=10,
        max_chars_per_unit=1000,
    )
    summary = out["summary"]
    assert summary["n_queries"] == 2
    # q1 cites u1 (correct), q2 cites u9 (required not cited) => mean 0.5
    assert summary["required_cited_rate_mean"] == 0.5
    # q2 should refuse but mock doesn't => 1/2 correct
    assert summary["refusal_accuracy"] == 0.5


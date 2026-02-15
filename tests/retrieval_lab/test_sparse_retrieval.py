from __future__ import annotations

import pytest

from retrieval_lab.sparse_retrieval import _build_bm25_query_text, _tokenize, build_query_text


def test_tokenize_hyphenated_keeps_compound() -> None:
    tokens = _tokenize("multi-attack rules", mode="hyphenated")
    assert "multi-attack" in tokens


def test_query_text_question_plus_summary() -> None:
    query = {"question": "How does initiative work?", "expected_answer_summary": "Turn order in combat."}
    text = _build_bm25_query_text(query, mode="question_plus_summary")
    assert "initiative" in text.lower()
    assert "turn order" in text.lower()


def test_query_text_invalid_mode_raises() -> None:
    with pytest.raises(ValueError):
        _build_bm25_query_text({"question": "x"}, mode="bad")


def test_build_query_text_weighted_repeats_sections() -> None:
    query = {"question": "initiative", "expected_answer_summary": "turn order"}
    text = build_query_text(query, mode="weighted", question_weight=2, summary_weight=1)
    assert text.count("initiative") == 2

from __future__ import annotations

import sys
import types
from typing import Any

from retrieval_lab.auto_gold_review.openai_reviewer import OpenAIGoldChunkReviewer


def _install_fake_openai_response(*, output_text: str = "", output: list[Any] | None = None) -> None:
    class _FakeResponse:
        def __init__(self) -> None:
            self.output_text = output_text
            self.output = output or []
            self.status = "completed"
            self.incomplete_details = None

        def model_dump(self) -> dict[str, Any]:
            return {
                "output_text": self.output_text,
                "output": self.output,
                "status": self.status,
                "incomplete_details": self.incomplete_details,
            }

    class _FakeResponses:
        def create(self, **kwargs: Any) -> _FakeResponse:
            return _FakeResponse()

    class _FakeClient:
        def __init__(self, api_key: str | None = None) -> None:
            self.responses = _FakeResponses()

    sys.modules["openai"] = types.SimpleNamespace(OpenAI=_FakeClient)  # type: ignore[assignment]


def _candidate(chunk_id: str, rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "chunk_id": chunk_id,
        "score": 1.0 - (rank * 0.01),
        "text": f"candidate text {chunk_id}",
        "page": rank,
        "structural_path": [f"Section {rank}"],
        "source_unit_ids": [f"raw-{chunk_id}"],
    }


def test_openai_gold_reviewer_maps_prompt_tokens_to_chunk_ids() -> None:
    _install_fake_openai_response(
        output_text=(
            '{"required_gold":["A001","B002"],'
            '"supporting_gold":["C003"],'
            '"required_gold_rationale":{"A001":"First anchor.","B002":"Second anchor."},'
            '"confidence":"high","review_flags":[],"needs_human_review":false,"notes":"ok"}'
        )
    )
    reviewer = OpenAIGoldChunkReviewer(model_id="fake-model")
    response = reviewer.review(
        question="Q",
        expected_answer_summary="A",
        notes="N",
        query_metadata={"query_id": "q1", "tier": "T3", "question_type": "reasoning"},
        candidates=[_candidate("u1", 1), _candidate("u2", 2), _candidate("u3", 3)],
    )
    assert response.required_gold == ["u1", "u2"]
    assert response.supporting_gold == ["u3"]
    assert response.required_gold_rationale == {"u1": "First anchor.", "u2": "Second anchor."}
    assert response.review_flags == []
    assert response.metadata["mapped_required_gold"] == ["u1", "u2"]
    assert response.metadata["invalid_references"] == []


def test_openai_gold_reviewer_flags_invalid_prompt_tokens() -> None:
    _install_fake_openai_response(
        output_text=(
            '{"required_gold":["A001","ZZ999"],'
            '"supporting_gold":["C003"],'
            '"required_gold_rationale":{"A001":"First anchor.","ZZ999":"Bogus anchor."},'
            '"confidence":"medium","review_flags":[],"needs_human_review":true,"notes":"check"}'
        )
    )
    reviewer = OpenAIGoldChunkReviewer(model_id="fake-model")
    response = reviewer.review(
        question="Q",
        expected_answer_summary="A",
        notes="N",
        query_metadata={"query_id": "q2", "tier": "T3", "question_type": "reasoning"},
        candidates=[_candidate("u1", 1), _candidate("u2", 2), _candidate("u3", 3)],
    )
    assert response.required_gold == ["u1"]
    assert response.supporting_gold == ["u3"]
    assert "invalid_candidate_reference" in response.review_flags
    assert response.metadata["invalid_references"] == ["ZZ999", "ZZ999"]


def test_openai_gold_reviewer_extracts_parsed_block_payload() -> None:
    parsed_payload = {
        "required_gold": ["A001"],
        "supporting_gold": [],
        "required_gold_rationale": {"A001": "Anchor from parsed block."},
        "confidence": "high",
        "review_flags": [],
        "needs_human_review": False,
        "notes": "",
    }
    block = types.SimpleNamespace(type="output_text", parsed=parsed_payload, text=None)
    output_item = types.SimpleNamespace(content=[block])
    _install_fake_openai_response(output_text="", output=[output_item])
    reviewer = OpenAIGoldChunkReviewer(model_id="fake-model")
    response = reviewer.review(
        question="Q",
        expected_answer_summary="A",
        notes="N",
        query_metadata={"query_id": "q3", "tier": "T2", "question_type": "lookup"},
        candidates=[_candidate("u1", 1), _candidate("u2", 2)],
    )
    assert response.required_gold == ["u1"]
    assert response.metadata["extraction_source"] == "output_blocks"


def test_openai_gold_reviewer_preserves_parse_error_diagnostics() -> None:
    _install_fake_openai_response(output_text="{")
    reviewer = OpenAIGoldChunkReviewer(model_id="fake-model")
    response = reviewer.review(
        question="Q",
        expected_answer_summary="A",
        notes="N",
        query_metadata={"query_id": "q4", "tier": "T3", "question_type": "reasoning"},
        candidates=[_candidate("u1", 1), _candidate("u2", 2)],
    )
    assert response.required_gold == []
    assert "parse_error" in response.review_flags
    assert response.metadata["parse_debug"]["parse_error"]
    assert response.metadata["raw_response_text"] == "{"

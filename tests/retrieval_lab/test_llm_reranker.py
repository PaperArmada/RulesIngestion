from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from retrieval_lab.llm_reranker import LLMRerankValidationError, ListwiseRerankResponse, rerank_candidates_listwise


def _install_fake_openai(output_text: str) -> None:
    def _strip_fence(text: str) -> str:
        raw = str(text).strip()
        if not raw.startswith("```"):
            return raw
        lines = raw.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
        return raw

    class _FakeResponse:
        def __init__(self, text: str) -> None:
            self.output_text = text
            self.output = []

        def model_dump(self) -> dict[str, Any]:
            return {"output_text": self.output_text}

    class _FakeParsedResponse(_FakeResponse):
        def __init__(self, text: str) -> None:
            super().__init__(text)
            self.output_parsed = ListwiseRerankResponse.model_validate(json.loads(_strip_fence(text)))

    class _FakeResponses:
        def __init__(self, text: str) -> None:
            self._text = text

        def create(self, **kwargs: Any) -> _FakeResponse:
            return _FakeResponse(self._text)

        def parse(self, **kwargs: Any) -> _FakeParsedResponse:
            return _FakeParsedResponse(self._text)

    class _FakeClient:
        def __init__(self, api_key: str | None = None) -> None:
            self.responses = _FakeResponses(output_text)

    fake_module = types.SimpleNamespace(OpenAI=_FakeClient)
    sys.modules["openai"] = fake_module  # type: ignore[assignment]


def _install_fake_openai_incomplete(*, reason: str = "max_output_tokens") -> None:
    class _FakeIncompleteResponse:
        def __init__(self) -> None:
            self.output_text = ""
            self.output = []
            self.output_parsed = None
            self.status = "incomplete"
            self.incomplete_details = {"reason": reason}

        def model_dump(self) -> dict[str, Any]:
            return {
                "output_text": self.output_text,
                "output": self.output,
                "status": self.status,
                "incomplete_details": self.incomplete_details,
            }

    class _FakeResponses:
        def parse(self, **kwargs: Any) -> _FakeIncompleteResponse:
            return _FakeIncompleteResponse()

    class _FakeClient:
        def __init__(self, api_key: str | None = None) -> None:
            self.responses = _FakeResponses()

    fake_module = types.SimpleNamespace(OpenAI=_FakeClient)
    sys.modules["openai"] = fake_module  # type: ignore[assignment]


def test_listwise_reranker_fails_on_id_set_mismatch(tmp_path: Path) -> None:
    _install_fake_openai(
        json.dumps(
            {
                "candidate_count_expected": 3,
                "ordered_candidate_tokens": ["B002", "unknown", "B002", "A001"],
                "rationale_tags": [
                    {"token": "B002", "tags": ["direct_rule", "bad_tag"]},
                    {"token": "unknown", "tags": ["direct_rule"]},
                ],
            }
        )
    )
    candidates = [
        {"candidate_id": "c1", "baseline_rank": 1, "excerpt": "a"},
        {"candidate_id": "c2", "baseline_rank": 2, "excerpt": "b"},
        {"candidate_id": "c3", "baseline_rank": 3, "excerpt": "c"},
    ]
    with pytest.raises(LLMRerankValidationError) as exc:
        rerank_candidates_listwise(
            query="q",
            candidates=candidates,
            model_id="gpt-4o-mini",
            cache_dir=str(tmp_path),
        )
    assert exc.value.metadata["fallback_reason"] == "candidate_id_set_mismatch"
    assert exc.value.metadata["exact_set_match"] is False
    assert exc.value.metadata["missing_ids"] == ["c3"]
    assert exc.value.metadata["declared_candidate_count"] == 3
    assert exc.value.metadata["declared_candidate_count_matches_input"] is True
    assert exc.value.metadata["missing_tokens"] == ["C003"]
    assert exc.value.metadata["extra_ids"] == ["unknown"]
    assert exc.value.metadata["extra_tokens"] == ["unknown"]
    assert exc.value.metadata["duplicate_count"] == 1
    assert Path(exc.value.record_path).exists()


def test_listwise_reranker_accepts_exact_set_match() -> None:
    _install_fake_openai(
        json.dumps(
            {
                "candidate_count_expected": 3,
                "ordered_candidate_tokens": ["B002", "A001", "C003"],
                "rationale_tags": [
                    {"token": "B002", "tags": ["direct_rule", "bad_tag"]},
                    {"token": "A001", "tags": ["high_specificity"]},
                ],
            }
        )
    )
    candidates = [
        {"candidate_id": "c1", "baseline_rank": 1, "excerpt": "a"},
        {"candidate_id": "c2", "baseline_rank": 2, "excerpt": "b"},
        {"candidate_id": "c3", "baseline_rank": 3, "excerpt": "c"},
    ]
    out = rerank_candidates_listwise(
        query="q",
        candidates=candidates,
        model_id="gpt-4o-mini",
    )
    assert out["ordered_candidate_ids"] == ["c2", "c1", "c3"]
    assert out["rationale_tags"] == {"c2": ["direct_rule"], "c1": ["high_specificity"]}
    assert out["metadata"]["fallback_reason"] == ""
    assert out["metadata"]["exact_set_match"] is True


def test_listwise_reranker_accepts_fenced_json_exact_set_match() -> None:
    _install_fake_openai(
        "```json\n"
        + json.dumps(
            {
                "candidate_count_expected": 3,
                "ordered_candidate_tokens": ["C003", "A001", "B002"],
                "rationale_tags": [
                    {"token": "C003", "tags": ["direct_rule"]},
                    {"token": "A001", "tags": ["high_specificity"]},
                ],
            }
        )
        + "\n```"
    )
    candidates = [
        {"candidate_id": "c1", "baseline_rank": 1, "excerpt": "a"},
        {"candidate_id": "c2", "baseline_rank": 2, "excerpt": "b"},
        {"candidate_id": "c3", "baseline_rank": 3, "excerpt": "c"},
    ]
    out = rerank_candidates_listwise(
        query="q",
        candidates=candidates,
        model_id="gpt-4o-mini",
    )
    assert out["ordered_candidate_ids"] == ["c3", "c1", "c2"]
    assert out["metadata"]["fallback_reason"] == ""
    assert out["metadata"]["exact_set_match"] is True


def test_listwise_reranker_uses_cache_on_repeat(tmp_path: Path) -> None:
    _install_fake_openai(
        json.dumps(
            {
                "candidate_count_expected": 2,
                "ordered_candidate_tokens": ["A001", "B002"],
                "rationale_tags": [{"token": "A001", "tags": ["high_specificity"]}],
            }
        )
    )
    cache_dir = tmp_path / "llm_cache"
    candidates = [
        {"candidate_id": "c1", "baseline_rank": 1, "excerpt": "a"},
        {"candidate_id": "c2", "baseline_rank": 2, "excerpt": "b"},
    ]
    first = rerank_candidates_listwise(
        query="same query",
        candidates=candidates,
        model_id="gpt-4o-mini",
        cache_dir=str(cache_dir),
    )
    assert first["metadata"]["cache_hit"] is False

    class _CrashResponses:
        def create(self, **kwargs: Any) -> Any:
            raise AssertionError("OpenAI call should not happen on cache hit")

    class _CrashClient:
        def __init__(self, api_key: str | None = None) -> None:
            self.responses = _CrashResponses()

    sys.modules["openai"] = types.SimpleNamespace(OpenAI=_CrashClient)  # type: ignore[assignment]
    second = rerank_candidates_listwise(
        query="same query",
        candidates=candidates,
        model_id="gpt-4o-mini",
        cache_dir=str(cache_dir),
    )
    assert second["metadata"]["cache_hit"] is True
    assert second["ordered_candidate_ids"] == ["c1", "c2"]
    assert second["metadata"]["exact_set_match"] is True


def test_listwise_reranker_cached_invalid_payload_fails_with_record(tmp_path: Path) -> None:
    cache_dir = tmp_path / "llm_cache"
    candidates = [
        {"candidate_id": "c1", "baseline_rank": 1, "excerpt": "a"},
        {"candidate_id": "c2", "baseline_rank": 2, "excerpt": "b"},
    ]
    _install_fake_openai(
        json.dumps(
            {
                "candidate_count_expected": 2,
                "ordered_candidate_tokens": ["A001", "B002"],
                "rationale_tags": [{"token": "A001", "tags": ["high_specificity"]}],
            }
        )
    )
    ok = rerank_candidates_listwise(
        query="cache mismatch query",
        candidates=candidates,
        model_id="gpt-4o-mini",
        cache_dir=str(cache_dir),
    )
    assert ok["ordered_candidate_ids"] == ["c1", "c2"]
    cache_files = list(cache_dir.glob("*.json"))
    assert cache_files
    cache_payload = json.loads(cache_files[0].read_text(encoding="utf-8"))
    cache_payload["parsed"] = {"candidate_count_expected": 2, "ordered_candidate_tokens": ["A001", "fake"], "rationale_tags": []}
    cache_files[0].write_text(json.dumps(cache_payload), encoding="utf-8")

    with pytest.raises(LLMRerankValidationError) as exc:
        rerank_candidates_listwise(
            query="cache mismatch query",
            candidates=candidates,
            model_id="gpt-4o-mini",
            cache_dir=str(cache_dir),
        )
    assert exc.value.metadata["cache_hit"] is True
    assert exc.value.metadata["fallback_reason"] == "candidate_id_set_mismatch"
    assert Path(exc.value.record_path).exists()


def test_listwise_reranker_fails_on_declared_candidate_count_mismatch(tmp_path: Path) -> None:
    _install_fake_openai(
        json.dumps(
            {
                "candidate_count_expected": 2,
                "ordered_candidate_tokens": ["A001", "B002", "C003"],
                "rationale_tags": [{"token": "A001", "tags": ["direct_rule"]}],
            }
        )
    )
    candidates = [
        {"candidate_id": "c1", "baseline_rank": 1, "excerpt": "a"},
        {"candidate_id": "c2", "baseline_rank": 2, "excerpt": "b"},
        {"candidate_id": "c3", "baseline_rank": 3, "excerpt": "c"},
    ]
    with pytest.raises(LLMRerankValidationError) as exc:
        rerank_candidates_listwise(
            query="q",
            candidates=candidates,
            model_id="gpt-4o-mini",
            cache_dir=str(tmp_path),
        )
    assert exc.value.metadata["fallback_reason"] == "candidate_count_mismatch"
    assert exc.value.metadata["declared_candidate_count"] == 2
    assert exc.value.metadata["declared_candidate_count_matches_input"] is False


def test_listwise_reranker_fails_on_incomplete_response(tmp_path: Path) -> None:
    _install_fake_openai_incomplete(reason="max_output_tokens")
    candidates = [
        {"candidate_id": "c1", "baseline_rank": 1, "excerpt": "a"},
        {"candidate_id": "c2", "baseline_rank": 2, "excerpt": "b"},
    ]
    with pytest.raises(LLMRerankValidationError) as exc:
        rerank_candidates_listwise(
            query="q",
            candidates=candidates,
            model_id="gpt-5-mini-2025-08-07",
            cache_dir=str(tmp_path),
        )
    assert exc.value.metadata["fallback_reason"] == "incomplete_response_max_output_tokens"
    assert exc.value.metadata["response_status"] == "incomplete"
    assert exc.value.metadata["incomplete_reason"] == "max_output_tokens"

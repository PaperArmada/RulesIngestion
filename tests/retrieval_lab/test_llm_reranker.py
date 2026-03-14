from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

from retrieval_lab.llm_reranker import rerank_candidates_listwise


def _install_fake_openai(output_text: str) -> None:
    class _FakeResponse:
        def __init__(self, text: str) -> None:
            self.output_text = text

    class _FakeResponses:
        def __init__(self, text: str) -> None:
            self._text = text

        def create(self, **kwargs: Any) -> _FakeResponse:
            return _FakeResponse(self._text)

    class _FakeClient:
        def __init__(self, api_key: str | None = None) -> None:
            self.responses = _FakeResponses(output_text)

    fake_module = types.SimpleNamespace(OpenAI=_FakeClient)
    sys.modules["openai"] = fake_module  # type: ignore[assignment]


def test_listwise_reranker_filters_unknown_ids_and_fills_missing() -> None:
    _install_fake_openai(
        json.dumps(
            {
                "ordered_candidate_ids": ["c2", "unknown", "c2", "c1"],
                "rationale_tags": {"c2": ["direct_rule", "bad_tag"], "unknown": ["direct_rule"]},
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
    assert out["rationale_tags"] == {"c2": ["direct_rule"]}
    assert out["metadata"]["fallback_reason"] == ""


def test_listwise_reranker_uses_cache_on_repeat(tmp_path: Path) -> None:
    _install_fake_openai(
        json.dumps(
            {
                "ordered_candidate_ids": ["c1", "c2"],
                "rationale_tags": {"c1": ["high_specificity"]},
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

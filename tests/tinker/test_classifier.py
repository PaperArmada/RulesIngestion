"""Tests for tinker.routing.classifier.

Unit tests monkeypatch the LLM backend so we exercise prompt construction
and response parsing without hitting a model.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tinker.backends.base import ChatResult
from tinker.cache import TinkerCache
from tinker.routing import buckets, classifier as cls


class _FakeBackend:
    name = "fake"

    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.calls: list[dict] = []

    def chat(self, **kwargs) -> ChatResult:
        self.calls.append(kwargs)
        return ChatResult(text=self.response_text)

    def unload_chat(self, role: str = "workhorse") -> bool:
        return True


def _install_backend(response_obj, monkeypatch, *, capture: dict) -> _FakeBackend:
    text = response_obj if isinstance(response_obj, str) else json.dumps(response_obj)
    backend = _FakeBackend(text)
    capture["backend"] = backend
    capture["calls"] = backend.calls
    monkeypatch.setattr(cls, "current_backend", lambda: backend)
    return backend


def test_prompt_contains_bucket_definitions_and_examples(monkeypatch) -> None:
    capture: dict = {}
    _install_backend(
        {"bucket": "entity_anchored_single", "confidence": 0.9, "reason": "test"},
        monkeypatch,
        capture=capture,
    )
    cls.classify_query("What does Healing Word do?")
    assert capture["calls"], "backend.chat was not called"
    user_text = capture["calls"][0]["user"]
    for bid in buckets.BUCKET_IDS:
        assert bid in user_text, f"bucket id {bid} missing from classifier prompt"
    for b in buckets.BUCKETS:
        appearing = sum(1 for ex in b.examples if ex in user_text)
        assert appearing >= 2, (
            f"bucket {b.id} has < 2 examples reflected in the prompt; "
            f"found {appearing}"
        )


def test_classify_returns_valid_bucket(monkeypatch) -> None:
    capture: dict = {}
    _install_backend(
        {
            "bucket": "intent_bearing_distributed",
            "confidence": 0.84,
            "reason": "Vague intent.",
        },
        monkeypatch,
        capture=capture,
    )
    out = cls.classify_query("I want to build a sneaky character.")
    assert out.bucket == "intent_bearing_distributed"
    assert out.confidence == pytest.approx(0.84)
    assert out.reason == "Vague intent."
    assert out.cached is False
    assert out.latency_ms >= 0.0


def test_unknown_bucket_falls_back_safely(monkeypatch) -> None:
    capture: dict = {}
    _install_backend(
        {"bucket": "made_up_bucket", "confidence": 0.5, "reason": "n/a"},
        monkeypatch,
        capture=capture,
    )
    out = cls.classify_query("anything")
    assert out.bucket == "entity_anchored_single"  # documented fallback
    assert out.confidence == 0.0
    assert "unknown bucket" in out.reason


def test_invalid_json_falls_back_safely(monkeypatch) -> None:
    capture: dict = {}
    _install_backend("not json at all", monkeypatch, capture=capture)
    out = cls.classify_query("anything")
    assert out.bucket == "entity_anchored_single"
    assert out.confidence == 0.0
    assert "JSON parse error" in out.reason


def test_cache_hit_skips_backend(tmp_path: Path, monkeypatch) -> None:
    cache = TinkerCache(tmp_path / "c.sqlite")
    capture: dict = {}
    _install_backend(
        {
            "bucket": "entity_anchored_single",
            "confidence": 0.7,
            "reason": "first",
        },
        monkeypatch,
        capture=capture,
    )

    out1 = cls.classify_query("How many HP does a Cleric have?", cache=cache)
    out2 = cls.classify_query("How many HP does a Cleric have?", cache=cache)
    assert len(capture["calls"]) == 1
    assert out1.cached is False
    assert out2.cached is True
    assert out1.bucket == out2.bucket == "entity_anchored_single"


def test_render_bucket_descriptions_includes_all_ids() -> None:
    text = buckets.render_bucket_descriptions()
    for bid in buckets.BUCKET_IDS:
        assert bid in text

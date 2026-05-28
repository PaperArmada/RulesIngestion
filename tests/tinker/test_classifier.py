"""Tests for tinker.routing.classifier.

Unit tests monkeypatch `ollama.chat` so we exercise prompt construction and
response parsing without hitting a model.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tinker.cache import TinkerCache
from tinker.routing import buckets, classifier as cls


def _patched_chat(response_json: dict, monkeypatch, *, capture: dict) -> None:
    """Replace ollama.chat with a stub that records the call and returns *response_json*."""

    def fake_chat(*args, **kwargs):
        capture["calls"] = capture.get("calls", []) + [(args, kwargs)]
        return {"message": {"content": json.dumps(response_json)}}

    monkeypatch.setattr(cls.ollama, "chat", fake_chat)


def test_prompt_contains_bucket_definitions_and_examples(monkeypatch) -> None:
    capture: dict = {}
    _patched_chat(
        {"bucket": "entity_anchored_single", "confidence": 0.9, "reason": "test"},
        monkeypatch,
        capture=capture,
    )
    cls.classify_query("What does Healing Word do?")
    assert capture["calls"], "ollama.chat was not called"
    kwargs = capture["calls"][0][1]
    messages = kwargs["messages"]
    user_text = next(m["content"] for m in messages if m["role"] == "user")
    # All bucket ids appear in the prompt.
    for bid in buckets.BUCKET_IDS:
        assert bid in user_text, f"bucket id {bid} missing from classifier prompt"
    # At least 2 examples per bucket appear in the prompt.
    for b in buckets.BUCKETS:
        appearing = sum(1 for ex in b.examples if ex in user_text)
        assert appearing >= 2, (
            f"bucket {b.id} has < 2 examples reflected in the prompt; "
            f"found {appearing}"
        )


def test_classify_returns_valid_bucket(monkeypatch) -> None:
    capture: dict = {}
    _patched_chat(
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
    _patched_chat(
        {"bucket": "made_up_bucket", "confidence": 0.5, "reason": "n/a"},
        monkeypatch,
        capture=capture,
    )
    out = cls.classify_query("anything")
    assert out.bucket == "entity_anchored_single"  # documented fallback
    assert out.confidence == 0.0
    assert "unknown bucket" in out.reason


def test_invalid_json_falls_back_safely(monkeypatch) -> None:
    def fake_chat(*args, **kwargs):
        return {"message": {"content": "not json at all"}}

    monkeypatch.setattr(cls.ollama, "chat", fake_chat)
    out = cls.classify_query("anything")
    assert out.bucket == "entity_anchored_single"
    assert out.confidence == 0.0
    assert "JSON parse error" in out.reason


def test_cache_hit_skips_ollama(tmp_path: Path, monkeypatch) -> None:
    cache = TinkerCache(tmp_path / "c.sqlite")
    calls = {"n": 0}

    def fake_chat(*args, **kwargs):
        calls["n"] += 1
        return {
            "message": {
                "content": json.dumps(
                    {
                        "bucket": "entity_anchored_single",
                        "confidence": 0.7,
                        "reason": "first",
                    }
                )
            }
        }

    monkeypatch.setattr(cls.ollama, "chat", fake_chat)

    out1 = cls.classify_query("How many HP does a Cleric have?", cache=cache)
    out2 = cls.classify_query("How many HP does a Cleric have?", cache=cache)
    assert calls["n"] == 1
    assert out1.cached is False
    assert out2.cached is True
    assert out1.bucket == out2.bucket == "entity_anchored_single"


def test_render_bucket_descriptions_includes_all_ids() -> None:
    text = buckets.render_bucket_descriptions()
    for bid in buckets.BUCKET_IDS:
        assert bid in text

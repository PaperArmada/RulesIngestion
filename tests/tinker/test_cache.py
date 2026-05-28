"""Tests for tinker.cache."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tinker.cache import TinkerCache


def test_embedding_round_trip(tmp_path: Path) -> None:
    cache = TinkerCache(tmp_path / "c.sqlite")
    assert cache.get_embedding("m1", "hello") is None
    cache.put_embedding("m1", "hello", [0.1, -0.2, 3.14])
    got = cache.get_embedding("m1", "hello")
    assert got is not None
    assert len(got) == 3
    assert got[0] == pytest.approx(0.1, abs=1e-6)
    assert got[1] == pytest.approx(-0.2, abs=1e-6)
    assert got[2] == pytest.approx(3.14, abs=1e-5)


def test_embedding_isolated_by_model(tmp_path: Path) -> None:
    cache = TinkerCache(tmp_path / "c.sqlite")
    cache.put_embedding("m1", "hello", [1.0, 2.0])
    cache.put_embedding("m2", "hello", [3.0, 4.0])
    assert cache.get_embedding("m1", "hello") == pytest.approx([1.0, 2.0])
    assert cache.get_embedding("m2", "hello") == pytest.approx([3.0, 4.0])


def test_llm_round_trip(tmp_path: Path) -> None:
    cache = TinkerCache(tmp_path / "c.sqlite")
    payload = {"prompt": "hi", "examples": [1, 2, 3]}
    assert cache.get_llm("classify", "q3", payload) is None
    cache.put_llm("classify", "q3", payload, "response text")
    assert cache.get_llm("classify", "q3", payload) == "response text"


def test_llm_payload_keys_order_invariant(tmp_path: Path) -> None:
    cache = TinkerCache(tmp_path / "c.sqlite")
    cache.put_llm("r", "m", {"a": 1, "b": 2}, "X")
    assert cache.get_llm("r", "m", {"b": 2, "a": 1}) == "X"


def test_nocache_env_bypasses(tmp_path: Path, monkeypatch) -> None:
    cache = TinkerCache(tmp_path / "c.sqlite")
    cache.put_embedding("m", "t", [0.5])
    monkeypatch.setenv("TINKER_NOCACHE", "1")
    assert cache.get_embedding("m", "t") is None
    cache.put_embedding("m", "t2", [0.6])  # no-op write
    monkeypatch.delenv("TINKER_NOCACHE")
    assert cache.get_embedding("m", "t") == pytest.approx([0.5])
    assert cache.get_embedding("m", "t2") is None
    assert cache.stats.embed_misses >= 1

"""Tests for tinker.rerank.

Two layers:
  - unit tests: monkeypatch the model loader, exercise control flow without
    downloading the real cross-encoder.
  - integration test (requires_model): actually load bge-reranker-v2-m3 and
    assert that a buried-but-relevant candidate is lifted to top-1.
"""

from __future__ import annotations

import pytest

from tinker import rerank


def test_rerank_uses_loaded_model_and_returns_top_k(monkeypatch) -> None:
    """Unit: rerank calls the model's predict() and returns top_k sorted."""

    class _FakeModel:
        def __init__(self) -> None:
            self.calls: list[list[tuple[str, str]]] = []

        def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
            self.calls.append(pairs)
            return [0.1, 0.9, 0.5, 0.7]

    fake = _FakeModel()
    monkeypatch.setattr(rerank, "load_reranker", lambda *_a, **_kw: fake)

    candidates = [
        {"id": f"u{i}", "text": f"doc {i}"} for i in range(4)
    ]
    out = rerank.rerank("query", candidates, top_k=2)

    assert [c["id"] for c in out] == ["u1", "u3"], (
        "expected top-2 by predict() score, got: " + str([(c["id"], c.get("rerank_score")) for c in out])
    )
    assert out[0]["rerank_score"] == pytest.approx(0.9)
    assert out[1]["rerank_score"] == pytest.approx(0.7)
    assert len(fake.calls) == 1
    assert fake.calls[0] == [("query", f"doc {i}") for i in range(4)]


def test_rerank_handles_empty_candidates(monkeypatch) -> None:
    """Unit: empty candidate list returns empty result, model not called."""
    sentinel = object()
    monkeypatch.setattr(rerank, "load_reranker", lambda *_a, **_kw: sentinel)
    out = rerank.rerank("query", [], top_k=5)
    assert out == []


def test_load_reranker_is_cached(monkeypatch) -> None:
    """Unit: load_reranker memoizes by model_name."""
    load_count = {"n": 0}

    def fake_load_ce(model_name: str):
        load_count["n"] += 1
        return f"model:{model_name}"

    monkeypatch.setattr(rerank, "load_cross_encoder", fake_load_ce)
    monkeypatch.setitem(rerank._LOADED, "", None)  # touch dict reference
    rerank._LOADED.clear()

    a = rerank.load_reranker("model-a")
    b = rerank.load_reranker("model-a")
    c = rerank.load_reranker("model-b")
    assert a is b
    assert a != c
    assert load_count["n"] == 2


@pytest.mark.requires_model
def test_bge_reranker_lifts_buried_relevant_doc() -> None:
    """Integration: real bge-reranker-v2-m3 raises a planted relevant doc to top-1.

    Downloads ~2 GB on first run; cached after. Gated by --tinker-model.
    """
    query = "What spell lets a cleric heal one ally a small amount at first level?"
    candidates = [
        {
            "id": "u0",
            "text": "Fireball is a third-level wizard spell that deals 1d6 fire damage per caster level in a 20-foot radius.",
        },
        {
            "id": "u1",
            "text": "Magic Missile creates a glowing dart that automatically hits a chosen target for 1d4+1 force damage.",
        },
        {
            "id": "u2",
            "text": "Cure Light Wounds is a first-level cleric spell that restores 1d8 hit points to a single touched ally.",
        },
        {
            "id": "u3",
            "text": "Sleep is a first-level wizard spell that causes 2d8 hit dice of creatures to fall asleep.",
        },
    ]
    out = rerank.rerank(query, candidates, top_k=4)
    assert out[0]["id"] == "u2", (
        f"expected Cure Light Wounds (u2) at top-1; got order: "
        f"{[(c['id'], round(c['rerank_score'], 3)) for c in out]}"
    )

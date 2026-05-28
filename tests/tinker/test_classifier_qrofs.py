"""Tests for the q-rung orthopair classifier path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tinker.cache import TinkerCache
from tinker.routing import buckets, classifier as cls


def _patched_chat(payload_json: dict, monkeypatch) -> dict:
    capture: dict = {"calls": []}

    def fake_chat(*args, **kwargs):
        capture["calls"].append((args, kwargs))
        return {"message": {"content": json.dumps(payload_json)}}

    monkeypatch.setattr(cls.ollama, "chat", fake_chat)
    return capture


def _full_membership_payload(values: dict[str, tuple[float, float]]) -> dict:
    """Build a `memberships` list using a mu/nu pair per bucket id provided.
    Buckets missing from values default to (0.1, 0.1)."""
    out = []
    for bid in buckets.BUCKET_IDS:
        mu, nu = values.get(bid, (0.1, 0.1))
        out.append({"bucket": bid, "mu": mu, "nu": nu, "reason": "test"})
    return {"memberships": out}


def test_qrofs_returns_membership_for_every_bucket(monkeypatch) -> None:
    _patched_chat(
        _full_membership_payload(
            {"entity_anchored_single": (0.9, 0.05)}
        ),
        monkeypatch,
    )
    out = cls.classify_query_qrofs("What does Cure Light Wounds do?")
    assert set(out.memberships.keys()) == set(buckets.BUCKET_IDS)
    assert out.chosen_bucket == "entity_anchored_single"
    assert out.chosen_mu == pytest.approx(0.9, abs=1e-6)
    assert out.chosen_nu == pytest.approx(0.05, abs=1e-6)
    # pi = sqrt(1 - 0.81 - 0.0025) ≈ sqrt(0.1875) ≈ 0.4330
    assert out.chosen_pi == pytest.approx(0.4330, abs=1e-3)
    assert out.margin > 0


def test_qrofs_constraint_renormalization(monkeypatch) -> None:
    # mu^2 + nu^2 = 0.49 + 0.64 = 1.13 > 1 — must be renormalized.
    _patched_chat(
        _full_membership_payload({"intent_bearing_distributed": (0.7, 0.8)}),
        monkeypatch,
    )
    out = cls.classify_query_qrofs("Some query")
    m = out.memberships["intent_bearing_distributed"]
    assert (m.mu ** 2) + (m.nu ** 2) <= 1.0 + 1e-9
    assert m.pi == pytest.approx(0.0, abs=1e-6)
    # Original ratio preserved within rounding.
    assert m.mu / m.nu == pytest.approx(0.7 / 0.8, abs=1e-3)


def test_qrofs_missing_bucket_fills_with_max_hesitation(monkeypatch) -> None:
    _patched_chat(
        {
            "memberships": [
                {"bucket": "entity_anchored_single", "mu": 0.8, "nu": 0.1, "reason": "x"}
            ]
        },
        monkeypatch,
    )
    out = cls.classify_query_qrofs("query")
    # Missing buckets get mu=nu=0 and pi=1.
    for bid in buckets.BUCKET_IDS:
        if bid == "entity_anchored_single":
            continue
        m = out.memberships[bid]
        assert m.mu == 0.0
        assert m.nu == 0.0
        assert m.pi == pytest.approx(1.0)
    assert out.chosen_bucket == "entity_anchored_single"


def test_qrofs_invalid_json_falls_back(monkeypatch) -> None:
    def fake_chat(*args, **kwargs):
        return {"message": {"content": "not valid json"}}

    monkeypatch.setattr(cls.ollama, "chat", fake_chat)
    out = cls.classify_query_qrofs("query")
    assert out.chosen_bucket == "entity_anchored_single"
    assert out.chosen_pi == pytest.approx(1.0)
    assert out.margin == 0.0
    assert out.chosen_mu == 0.0


def test_qrofs_unknown_bucket_ids_dropped(monkeypatch) -> None:
    _patched_chat(
        {
            "memberships": [
                {"bucket": "nonsense_bucket", "mu": 0.99, "nu": 0.0, "reason": "noise"},
                {"bucket": "concept_anchored", "mu": 0.7, "nu": 0.1, "reason": "real"},
            ]
        },
        monkeypatch,
    )
    out = cls.classify_query_qrofs("query")
    assert out.chosen_bucket == "concept_anchored"
    # The nonsense bucket should not appear anywhere.
    assert "nonsense_bucket" not in out.memberships


def test_qrofs_caching(tmp_path: Path, monkeypatch) -> None:
    cache = TinkerCache(tmp_path / "c.sqlite")
    calls = {"n": 0}

    def fake_chat(*args, **kwargs):
        calls["n"] += 1
        return {
            "message": {
                "content": json.dumps(
                    _full_membership_payload({"concept_anchored": (0.6, 0.2)})
                )
            }
        }

    monkeypatch.setattr(cls.ollama, "chat", fake_chat)
    o1 = cls.classify_query_qrofs("same query", cache=cache)
    o2 = cls.classify_query_qrofs("same query", cache=cache)
    assert calls["n"] == 1
    assert o1.cached is False
    assert o2.cached is True
    assert o1.chosen_bucket == o2.chosen_bucket == "concept_anchored"


def test_renormalize_pair_pythagorean() -> None:
    mu, nu, pi = cls._renormalize_pair(0.6, 0.6, q=2)  # 0.72 > 0 but valid
    assert (mu ** 2) + (nu ** 2) <= 1.0 + 1e-9
    # 0.6^2 + 0.6^2 = 0.72 — within constraint; pi = sqrt(0.28) ≈ 0.5292
    assert pi == pytest.approx(0.5292, abs=1e-3)


def test_renormalize_pair_clamps_negative_and_over_one() -> None:
    mu, nu, pi = cls._renormalize_pair(-0.5, 1.5, q=2)
    assert 0.0 <= mu <= 1.0
    assert 0.0 <= nu <= 1.0
    assert pi >= 0.0

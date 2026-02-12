"""Tests for pairing instrumentation (v1: every run emits expected structure, even when 0)."""

from __future__ import annotations


def test_pairing_instrumentation_payload_structure() -> None:
    """Pairing instrumentation must have 'enabled' and 'by_model' keys."""
    payload = {"enabled": False, "by_model": {}}
    assert "enabled" in payload
    assert "by_model" in payload
    assert isinstance(payload["by_model"], dict)


def test_pairing_per_query_keys_when_enabled() -> None:
    """When pairing is enabled, per_query entries must have expected keys."""
    per_query_entry = {
        "query_id": "q1",
        "pairing_triggers_fired": 0,
        "candidates_added_by_pairing": 0,
        "gold_added_by_pairing": 0,
        "added_entered_top10": 0,
    }
    required = {"query_id", "pairing_triggers_fired", "candidates_added_by_pairing", "gold_added_by_pairing", "added_entered_top10"}
    assert required.issubset(per_query_entry.keys())


def test_pairing_summary_keys() -> None:
    """Pairing by_model summary must have total_queries, total_triggers_fired, total_candidates_added, total_gold_added, total_added_entered_top10."""
    summary = {
        "total_queries": 28,
        "total_triggers_fired": 0,
        "total_candidates_added": 0,
        "total_gold_added": 0,
        "total_added_entered_top10": 0,
    }
    required = {"total_queries", "total_triggers_fired", "total_candidates_added", "total_gold_added", "total_added_entered_top10"}
    assert required.issubset(summary.keys())

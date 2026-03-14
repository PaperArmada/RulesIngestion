from __future__ import annotations

from retrieval_lab.chunk_quality_gate import (
    evaluate_chunk_quality_gate,
    summarize_chunk_quality,
)


def test_chunk_quality_summary_counts_and_rates() -> None:
    corpus = [
        {"id": "a", "text": "short", "structural_path": ["H"]},
        {"id": "b", "text": "short", "structural_path": ["H"]},
        {"id": "c", "text": "Long enough chunk body text for retrieval.", "structural_path": []},
    ]
    summary = summarize_chunk_quality(corpus)
    assert summary["total_units"] == 3
    assert summary["short_le_40"] == 2
    assert summary["short_le_80"] == 3
    assert summary["empty_structural_path"] == 1
    assert summary["duplicate_text_groups"] == 1
    assert summary["duplicate_text_entries"] == 2
    # duplicate excess entries = (2-1)/3
    assert abs(summary["duplicate_text_entry_rate"] - (1 / 3)) < 1e-9


def test_chunk_quality_gate_detects_threshold_violations() -> None:
    summary = {
        "short_le_40_rate": 0.11,
        "short_le_80_rate": 0.25,
        "duplicate_text_entry_rate": 0.08,
    }
    violations = evaluate_chunk_quality_gate(
        summary,
        max_short_le_40_rate=0.10,
        max_short_le_80_rate=0.20,
        max_duplicate_text_entry_rate=0.05,
    )
    assert len(violations) == 3


def test_chunk_quality_gate_passes_when_under_threshold() -> None:
    summary = {
        "short_le_40_rate": 0.01,
        "short_le_80_rate": 0.05,
        "duplicate_text_entry_rate": 0.01,
    }
    violations = evaluate_chunk_quality_gate(
        summary,
        max_short_le_40_rate=0.10,
        max_short_le_80_rate=0.20,
        max_duplicate_text_entry_rate=0.05,
    )
    assert violations == []

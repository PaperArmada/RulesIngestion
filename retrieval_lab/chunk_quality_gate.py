"""Corpus chunk-quality diagnostics and optional fail-fast gate."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def summarize_chunk_quality(corpus: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute chunk-shape diagnostics for a retrieval corpus."""
    total = len(corpus)
    if total == 0:
        return {
            "total_units": 0,
            "short_le_40": 0,
            "short_le_80": 0,
            "empty_structural_path": 0,
            "duplicate_text_groups": 0,
            "duplicate_text_entries": 0,
            "short_le_40_rate": 0.0,
            "short_le_80_rate": 0.0,
            "empty_structural_path_rate": 0.0,
            "duplicate_text_entry_rate": 0.0,
            "top_duplicate_texts": [],
        }

    lengths = [len((u.get("text") or "").strip()) for u in corpus]
    short_40 = sum(1 for n in lengths if n <= 40)
    short_80 = sum(1 for n in lengths if n <= 80)
    empty_structural_path = sum(1 for u in corpus if not bool(u.get("structural_path")))

    normalized = [_normalize_text(u.get("text") or "") for u in corpus]
    counts = Counter(t for t in normalized if t)
    duplicate_groups = sum(1 for c in counts.values() if c > 1)
    duplicate_entries = sum(c for c in counts.values() if c > 1)
    duplicate_excess = sum((c - 1) for c in counts.values() if c > 1)

    top_duplicate_texts = [
        {"text": text[:160], "count": count}
        for text, count in counts.most_common(10)
        if count > 1
    ]

    return {
        "total_units": total,
        "short_le_40": short_40,
        "short_le_80": short_80,
        "empty_structural_path": empty_structural_path,
        "duplicate_text_groups": duplicate_groups,
        "duplicate_text_entries": duplicate_entries,
        "short_le_40_rate": short_40 / total,
        "short_le_80_rate": short_80 / total,
        "empty_structural_path_rate": empty_structural_path / total,
        "duplicate_text_entry_rate": duplicate_excess / total,
        "top_duplicate_texts": top_duplicate_texts,
    }


def evaluate_chunk_quality_gate(
    summary: Dict[str, Any],
    *,
    max_short_le_40_rate: float,
    max_short_le_80_rate: float,
    max_duplicate_text_entry_rate: float,
) -> List[str]:
    """Return human-readable violations for configured thresholds."""
    violations: List[str] = []

    short_40_rate = float(summary.get("short_le_40_rate", 0.0))
    short_80_rate = float(summary.get("short_le_80_rate", 0.0))
    duplicate_rate = float(summary.get("duplicate_text_entry_rate", 0.0))

    if short_40_rate > max_short_le_40_rate:
        violations.append(
            f"short_le_40_rate={short_40_rate:.4f} exceeds {max_short_le_40_rate:.4f}"
        )
    if short_80_rate > max_short_le_80_rate:
        violations.append(
            f"short_le_80_rate={short_80_rate:.4f} exceeds {max_short_le_80_rate:.4f}"
        )
    if duplicate_rate > max_duplicate_text_entry_rate:
        violations.append(
            "duplicate_text_entry_rate="
            f"{duplicate_rate:.4f} exceeds {max_duplicate_text_entry_rate:.4f}"
        )
    return violations

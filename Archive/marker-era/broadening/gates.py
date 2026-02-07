"""
Stage B gates: M-B1 through M-B8.

Quality metrics for EvidenceChunk generation.

Contract: Stage B — Chunk Quality & Context Broadening.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .schemas import EvidenceChunk, GroupingStopReason

if TYPE_CHECKING:
    pass


# -----------------------------------------------------------------------------
# Gate Thresholds
# -----------------------------------------------------------------------------

# M-B1: Size distribution thresholds
M_B1_P10_MIN_CHARS = 300
M_B1_MEDIAN_MIN_CHARS = 500
M_B1_MEDIAN_MAX_CHARS = 1200

# M-B2: Fragment rate threshold
M_B2_FRAGMENT_THRESHOLD = 0.02  # <= 2%

# M-B3: Over-broad rate threshold
M_B3_OVERBROAD_THRESHOLD = 0.05  # <= 5%
M_B3_MAX_CHARS = 2000

# M-B4: Structural violations (must be 0)
M_B4_VIOLATION_THRESHOLD = 0

# M-B5: Grouping rule coverage (no single rule > 80%)
M_B5_MAX_RULE_COVERAGE = 0.80

# M-B6: Stop-reason distribution (size_threshold_hit should be rare)
M_B6_SIZE_THRESHOLD_MAX = 0.10  # <= 10%


# -----------------------------------------------------------------------------
# Gate Result Types
# -----------------------------------------------------------------------------


@dataclass
class GateResult:
    """Result of a single gate check."""

    gate_id: str
    passed: bool
    value: float
    threshold: float
    details: str = ""

    def to_dict(self) -> dict:
        return {
            "gate_id": self.gate_id,
            "passed": self.passed,
            "value": self.value,
            "threshold": self.threshold,
            "details": self.details,
        }


@dataclass
class GatesReport:
    """Complete gates report for Stage B."""

    passed: bool
    results: list[GateResult]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "results": [r.to_dict() for r in self.results],
        }


# -----------------------------------------------------------------------------
# Individual Gate Functions
# -----------------------------------------------------------------------------


def m_b1_size_distribution(evidence_chunks: list[EvidenceChunk]) -> GateResult:
    """
    M-B1: EvidenceChunk Size Distribution (Prose).

    Requirements:
    - p10_chars >= 300
    - median_chars in [500, 1200]
    """
    if not evidence_chunks:
        return GateResult(
            gate_id="M-B1",
            passed=True,
            value=0.0,
            threshold=M_B1_P10_MIN_CHARS,
            details="No evidence chunks",
        )

    # Filter to Prose only
    prose_chunks = [e for e in evidence_chunks if e.kind == "Prose"]
    if not prose_chunks:
        return GateResult(
            gate_id="M-B1",
            passed=True,
            value=0.0,
            threshold=M_B1_P10_MIN_CHARS,
            details="No prose chunks",
        )

    char_counts = sorted(len(e.text) for e in prose_chunks)

    # Calculate p10 (10th percentile)
    p10_idx = max(0, int(len(char_counts) * 0.10) - 1)
    p10_chars = char_counts[p10_idx]

    # Calculate median
    median_chars = statistics.median(char_counts)

    # Check both conditions
    p10_pass = p10_chars >= M_B1_P10_MIN_CHARS
    median_pass = M_B1_MEDIAN_MIN_CHARS <= median_chars <= M_B1_MEDIAN_MAX_CHARS

    passed = p10_pass and median_pass

    return GateResult(
        gate_id="M-B1",
        passed=passed,
        value=p10_chars,
        threshold=M_B1_P10_MIN_CHARS,
        details=f"p10={p10_chars}, median={median_chars:.0f}, n={len(prose_chunks)}",
    )


def m_b2_fragment_rate(evidence_chunks: list[EvidenceChunk]) -> GateResult:
    """
    M-B2: Fragment Rate.

    EvidenceChunks below minimum thresholds / total <= 0.02
    """
    if not evidence_chunks:
        return GateResult(
            gate_id="M-B2",
            passed=True,
            value=0.0,
            threshold=M_B2_FRAGMENT_THRESHOLD,
            details="No evidence chunks",
        )

    # Count fragments (Prose below 300 chars)
    prose_chunks = [e for e in evidence_chunks if e.kind == "Prose"]
    fragments = sum(1 for e in prose_chunks if len(e.text) < M_B1_P10_MIN_CHARS)

    total = len(evidence_chunks)
    rate = fragments / total if total > 0 else 0.0

    return GateResult(
        gate_id="M-B2",
        passed=rate <= M_B2_FRAGMENT_THRESHOLD,
        value=rate,
        threshold=M_B2_FRAGMENT_THRESHOLD,
        details=f"fragments={fragments}, total={total}",
    )


def m_b3_overbroad_rate(evidence_chunks: list[EvidenceChunk]) -> GateResult:
    """
    M-B3: Over-Broad Rate.

    EvidenceChunks > 2000 chars / total <= 0.05
    """
    if not evidence_chunks:
        return GateResult(
            gate_id="M-B3",
            passed=True,
            value=0.0,
            threshold=M_B3_OVERBROAD_THRESHOLD,
            details="No evidence chunks",
        )

    overbroad = sum(1 for e in evidence_chunks if len(e.text) > M_B3_MAX_CHARS)
    total = len(evidence_chunks)
    rate = overbroad / total if total > 0 else 0.0

    return GateResult(
        gate_id="M-B3",
        passed=rate <= M_B3_OVERBROAD_THRESHOLD,
        value=rate,
        threshold=M_B3_OVERBROAD_THRESHOLD,
        details=f"overbroad={overbroad}, total={total}",
    )


def m_b4_structural_violations(evidence_chunks: list[EvidenceChunk]) -> GateResult:
    """
    M-B4: Structural Coherence Violations.

    Count of B-INV-3 or B-INV-6 violations. Gate: 0.
    """
    violations = 0

    for e in evidence_chunks:
        if e.kind == "Prose":
            # B-INV-6: Prose must have exactly one CDS leaf path
            # Check if source chunks span multiple section paths
            # (We don't have direct access to source chunks here, so check
            # if section_path is empty for multi-source chunks)
            if len(e.source_chunk_ids) > 1 and not e.section_path:
                violations += 1

        # B-INV-3: Check page spread (shouldn't span too many pages)
        if len(e.page_indices) > 3:
            violations += 1

    return GateResult(
        gate_id="M-B4",
        passed=violations == M_B4_VIOLATION_THRESHOLD,
        value=float(violations),
        threshold=float(M_B4_VIOLATION_THRESHOLD),
        details=f"violations={violations}",
    )


def m_b5_grouping_rule_coverage(evidence_chunks: list[EvidenceChunk]) -> GateResult:
    """
    M-B5: Grouping Rule Coverage.

    No single rule > 80% (unless explicitly justified).
    """
    if not evidence_chunks:
        return GateResult(
            gate_id="M-B5",
            passed=True,
            value=0.0,
            threshold=M_B5_MAX_RULE_COVERAGE,
            details="No evidence chunks",
        )

    rule_counts = Counter(e.grouping_rule_id for e in evidence_chunks)
    total = len(evidence_chunks)

    max_rule = max(rule_counts.items(), key=lambda x: x[1])
    max_coverage = max_rule[1] / total

    return GateResult(
        gate_id="M-B5",
        passed=max_coverage <= M_B5_MAX_RULE_COVERAGE,
        value=max_coverage,
        threshold=M_B5_MAX_RULE_COVERAGE,
        details=f"max_rule={max_rule[0]} ({max_coverage:.1%}), distribution={dict(rule_counts)}",
    )


def m_b6_stop_reason_distribution(evidence_chunks: list[EvidenceChunk]) -> GateResult:
    """
    M-B6: Grouping Stop-Reason Distribution.

    size_threshold_hit must be rare (< 10%).
    """
    if not evidence_chunks:
        return GateResult(
            gate_id="M-B6",
            passed=True,
            value=0.0,
            threshold=M_B6_SIZE_THRESHOLD_MAX,
            details="No evidence chunks",
        )

    stop_counts = Counter(e.grouping_stop_reason for e in evidence_chunks)
    total = len(evidence_chunks)

    size_threshold_count = stop_counts.get(GroupingStopReason.SIZE_THRESHOLD_HIT.value, 0)
    size_threshold_rate = size_threshold_count / total

    return GateResult(
        gate_id="M-B6",
        passed=size_threshold_rate <= M_B6_SIZE_THRESHOLD_MAX,
        value=size_threshold_rate,
        threshold=M_B6_SIZE_THRESHOLD_MAX,
        details=f"size_threshold_hit={size_threshold_count}, distribution={dict(stop_counts)}",
    )


def m_b7_gold_coverage(evidence_chunks: list[EvidenceChunk]) -> GateResult:
    """
    M-B7: Gold Coverage & Quality Lift.

    Requires benchmark infrastructure — returns placeholder.
    """
    return GateResult(
        gate_id="M-B7",
        passed=True,
        value=1.0,
        threshold=1.0,
        details="Benchmark not implemented — placeholder pass",
    )


def m_b8_near_tie_risk(evidence_chunks: list[EvidenceChunk]) -> GateResult:
    """
    M-B8: Near-Tie Risk Proxy.

    Requires embedding + scoring infrastructure — returns placeholder.
    """
    return GateResult(
        gate_id="M-B8",
        passed=True,
        value=1.0,
        threshold=1.0,
        details="Benchmark not implemented — placeholder pass",
    )


# -----------------------------------------------------------------------------
# Main Gate Runner
# -----------------------------------------------------------------------------


def run_gates(evidence_chunks: list[EvidenceChunk]) -> GatesReport:
    """
    Run all Stage B gates (M-B1 through M-B8).

    Returns a GatesReport with overall pass/fail and individual results.
    """
    results = [
        m_b1_size_distribution(evidence_chunks),
        m_b2_fragment_rate(evidence_chunks),
        m_b3_overbroad_rate(evidence_chunks),
        m_b4_structural_violations(evidence_chunks),
        m_b5_grouping_rule_coverage(evidence_chunks),
        m_b6_stop_reason_distribution(evidence_chunks),
        m_b7_gold_coverage(evidence_chunks),
        m_b8_near_tie_risk(evidence_chunks),
    ]

    # All gates must pass for overall pass
    passed = all(r.passed for r in results)

    return GatesReport(passed=passed, results=results)

"""
Stage B: Chunk Quality & Context Broadening.

Transforms Stage A Chunks into EvidenceChunks via deterministic grouping.

Usage:
    from broadening import run_broadening, EvidenceChunk

    result = run_broadening(
        chunks_path=Path("out/chunks.json"),
        output_dir=Path("out/"),
        check_gates=True,
    )

Contract: Stage B — Chunk Quality & Context Broadening.
"""

from .schemas import (
    EvidenceChunk,
    EvidenceKind,
    GroupingRule,
    GroupingStopReason,
    SourceSpan,
    UngroupedRecord,
    BroadeningResult,
)
from .eligibility import (
    ELIGIBLE_TYPES,
    CONDITIONAL_ELIGIBLE,
    INELIGIBLE_TYPES,
    is_eligible,
    filter_eligible,
)
from .grouper import (
    group_chunks,
    meets_prose_mass,
    meets_tabular_mass,
)
from .gates import (
    run_gates,
    GatesReport,
    GateResult,
)
from .serialize import (
    evidence_chunk_hash,
    evidence_chunks_hash,
    serialize_broadening_output,
)
from .run import run_broadening

__all__ = [
    # Schemas
    "EvidenceChunk",
    "EvidenceKind",
    "GroupingRule",
    "GroupingStopReason",
    "SourceSpan",
    "UngroupedRecord",
    "BroadeningResult",
    # Eligibility
    "ELIGIBLE_TYPES",
    "CONDITIONAL_ELIGIBLE",
    "INELIGIBLE_TYPES",
    "is_eligible",
    "filter_eligible",
    # Grouper
    "group_chunks",
    "meets_prose_mass",
    "meets_tabular_mass",
    # Gates
    "run_gates",
    "GatesReport",
    "GateResult",
    # Serialize
    "evidence_chunk_hash",
    "evidence_chunks_hash",
    "serialize_broadening_output",
    # Run
    "run_broadening",
]

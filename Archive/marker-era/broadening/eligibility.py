"""
Stage B eligibility filter (B-INV-0).

Only semantically eligible Chunks may contribute to EvidenceChunks.

Contract: Stage B — Chunk Quality & Context Broadening.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from extraction.schemas import Chunk


# -----------------------------------------------------------------------------
# Eligibility Categories (B-INV-0)
# -----------------------------------------------------------------------------

# Eligible block types — always allowed
ELIGIBLE_TYPES = frozenset({"Text", "Heading", "List"})

# Conditionally eligible — only when explicitly allowlisted
CONDITIONAL_ELIGIBLE = frozenset({"Table"})

# Explicitly ineligible — never allowed
INELIGIBLE_TYPES = frozenset({
    "Page",
    "ListGroup",
    "TableGroup",
    "FigureGroup",
    "Form",
    "TableOfContents",
    "Figure",
    "Footnote",
    "Unknown",
})


# -----------------------------------------------------------------------------
# Eligibility Functions
# -----------------------------------------------------------------------------


def is_eligible(chunk: "Chunk", allow_tables: bool = False) -> bool:
    """
    Check if a Chunk is semantically eligible for EvidenceChunk formation (B-INV-0).

    Args:
        chunk: The Chunk to check
        allow_tables: If True, Table chunks are conditionally eligible

    Returns:
        True if the chunk can participate in EvidenceChunk formation
    """
    block_type = chunk.block_type

    # Always eligible
    if block_type in ELIGIBLE_TYPES:
        return True

    # Conditionally eligible
    if block_type in CONDITIONAL_ELIGIBLE and allow_tables:
        return True

    # All others are ineligible
    return False


def filter_eligible(
    chunks: list["Chunk"],
    allow_tables: bool = False,
) -> list["Chunk"]:
    """
    Filter chunks to only those eligible for EvidenceChunk formation (B-INV-0).

    Args:
        chunks: List of Stage A Chunks
        allow_tables: If True, include Table chunks

    Returns:
        List of eligible Chunks only
    """
    return [c for c in chunks if is_eligible(c, allow_tables)]


def classify_ineligibility(chunk: "Chunk") -> str | None:
    """
    Return the reason a chunk is ineligible, or None if eligible.

    Args:
        chunk: The Chunk to classify

    Returns:
        Reason string if ineligible, None if eligible
    """
    block_type = chunk.block_type

    if block_type in ELIGIBLE_TYPES:
        return None

    if block_type in CONDITIONAL_ELIGIBLE:
        return "conditional_table_not_allowlisted"

    if block_type in INELIGIBLE_TYPES:
        return f"ineligible_type_{block_type.lower()}"

    # Unknown type
    return f"unknown_type_{block_type}"

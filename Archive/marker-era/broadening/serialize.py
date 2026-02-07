"""
Stage B serialization: Deterministic hashing for EvidenceChunks.

Ensures identical inputs produce identical hashes across runs.

Contract: Stage B — Chunk Quality & Context Broadening.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .schemas import EvidenceChunk

# Try to use blake3 for speed; fall back to sha256
try:
    import blake3

    _HAS_BLAKE3 = True
except ImportError:
    _HAS_BLAKE3 = False

# Consistent hash length (32 hex chars = 128 bits)
_HASH_HEX_LEN = 32


# -----------------------------------------------------------------------------
# Canonical Serialization
# -----------------------------------------------------------------------------


def _canonical_json(obj: Any) -> bytes:
    """
    Serialize object to canonical JSON bytes.

    - Keys sorted for determinism
    - No extra whitespace
    - UTF-8 encoding
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def deterministic_serialize_evidence_chunk(chunk: EvidenceChunk) -> bytes:
    """
    Serialize an EvidenceChunk to canonical bytes for hashing.

    Includes all identity-relevant fields:
    - evidence_chunk_id
    - kind
    - text
    - source_chunk_ids (sorted)
    - grouping_rule_id
    - section_path
    - page_indices (sorted)
    """
    canonical = {
        "evidence_chunk_id": chunk.evidence_chunk_id,
        "kind": chunk.kind,
        "text": chunk.text,
        "source_chunk_ids": sorted(chunk.source_chunk_ids),
        "grouping_rule_id": chunk.grouping_rule_id,
        "section_path": chunk.section_path,
        "page_indices": sorted(chunk.page_indices),
    }
    return _canonical_json(canonical)


def deterministic_serialize_evidence_chunks(chunks: list[EvidenceChunk]) -> bytes:
    """
    Serialize a list of EvidenceChunks to canonical bytes.

    Chunks are sorted by evidence_chunk_id for determinism.
    """
    sorted_chunks = sorted(chunks, key=lambda c: c.evidence_chunk_id)
    serialized = [
        {
            "evidence_chunk_id": c.evidence_chunk_id,
            "kind": c.kind,
            "text": c.text,
            "source_chunk_ids": sorted(c.source_chunk_ids),
            "grouping_rule_id": c.grouping_rule_id,
            "section_path": c.section_path,
            "page_indices": sorted(c.page_indices),
        }
        for c in sorted_chunks
    ]
    return _canonical_json(serialized)


# -----------------------------------------------------------------------------
# Hash Functions
# -----------------------------------------------------------------------------


def evidence_chunk_hash(chunk: EvidenceChunk) -> str:
    """
    Compute deterministic hash for a single EvidenceChunk.

    Uses blake3 if available, otherwise SHA-256.
    Returns _HASH_HEX_LEN hex characters.
    """
    raw = deterministic_serialize_evidence_chunk(chunk)

    if _HAS_BLAKE3:
        return blake3.blake3(raw).hexdigest()[:_HASH_HEX_LEN]

    return hashlib.sha256(raw).hexdigest()[:_HASH_HEX_LEN]


def evidence_chunks_hash(chunks: list[EvidenceChunk]) -> str:
    """
    Compute deterministic hash for a list of EvidenceChunks.

    Uses blake3 if available, otherwise SHA-256.
    Returns _HASH_HEX_LEN hex characters.
    """
    raw = deterministic_serialize_evidence_chunks(chunks)

    if _HAS_BLAKE3:
        return blake3.blake3(raw).hexdigest()[:_HASH_HEX_LEN]

    return hashlib.sha256(raw).hexdigest()[:_HASH_HEX_LEN]


# -----------------------------------------------------------------------------
# Full Output Serialization
# -----------------------------------------------------------------------------


def serialize_broadening_output(
    evidence_chunks: list[EvidenceChunk],
    include_hash: bool = True,
) -> dict[str, Any]:
    """
    Serialize complete Stage B output for writing to JSON.

    Returns a dict with:
    - evidence_chunks: list of chunk dicts
    - count: number of chunks
    - hash: deterministic hash of chunks (if include_hash=True)
    """
    output: dict[str, Any] = {
        "evidence_chunks": [c.to_dict() for c in evidence_chunks],
        "count": len(evidence_chunks),
    }

    if include_hash:
        output["hash"] = evidence_chunks_hash(evidence_chunks)

    return output

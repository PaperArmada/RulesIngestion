"""Deterministic corpus fingerprint utilities for embedding/index compatibility checks."""

from __future__ import annotations

import hashlib
from typing import Dict, Iterable, List


def corpus_fingerprint_from_ids(corpus_ids: Iterable[str]) -> str:
    """Hash ordered corpus ids to a stable fingerprint."""
    material = "\n".join(str(cid) for cid in corpus_ids)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def corpus_fingerprint_from_index_map(unit_id_to_index: Dict[str, int]) -> str:
    """Reconstruct ordered id list from index map and hash it."""
    ordered: List[str] = [cid for cid, _ in sorted(unit_id_to_index.items(), key=lambda item: int(item[1]))]
    return corpus_fingerprint_from_ids(ordered)


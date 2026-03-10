"""Deterministic corpus fingerprint utilities for corpus/index compatibility checks."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Mapping


def corpus_fingerprint_from_ids(corpus_ids: Iterable[str]) -> str:
    """Hash ordered corpus ids to a stable fingerprint."""
    material = "\n".join(str(cid) for cid in corpus_ids)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def corpus_fingerprint_from_index_map(unit_id_to_index: Dict[str, int]) -> str:
    """Reconstruct ordered id list from index map and hash it."""
    ordered: List[str] = [cid for cid, _ in sorted(unit_id_to_index.items(), key=lambda item: int(item[1]))]
    return corpus_fingerprint_from_ids(ordered)


def _normalize_structural_path(structural_path: Any) -> List[str]:
    if not structural_path:
        return []
    raw_parts = structural_path if isinstance(structural_path, list) else [structural_path]
    normalized: List[str] = []
    for raw in raw_parts:
        text = re.sub(r"\s+", " ", str(raw)).strip()
        if text:
            normalized.append(text.casefold())
    return normalized


def _sha256_text(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def corpus_record_from_unit(unit: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the stable, content-aware record used for corpus fingerprinting."""
    source_unit_ids = sorted(
        {
            str(item).strip()
            for item in (unit.get("source_unit_ids") or [unit.get("id", "")])
            if str(item).strip()
        }
    )
    return {
        "chunk_id": str(unit.get("id", "")).strip(),
        "page": int(unit.get("page", -1)),
        "structural_path": _normalize_structural_path(unit.get("structural_path") or []),
        "text_sha256": _sha256_text(str(unit.get("text", ""))),
        "source_unit_ids": source_unit_ids,
    }


def corpus_content_fingerprint_from_records(records: Iterable[Mapping[str, Any]]) -> str:
    """Hash ordered corpus records to a content-aware fingerprint."""
    material = "\n".join(
        json.dumps(dict(record), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        for record in records
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def corpus_content_fingerprint_from_units(corpus: Iterable[Mapping[str, Any]]) -> str:
    """Hash ordered corpus units using content-aware records."""
    return corpus_content_fingerprint_from_records(corpus_record_from_unit(unit) for unit in corpus)


def corpus_content_fingerprint_from_index_payload(index_payload: Mapping[str, Any]) -> str:
    """Recover content-aware fingerprint from a stored corpus-index payload."""
    records = index_payload.get("ordered_corpus_records") or []
    if records:
        return corpus_content_fingerprint_from_records(records)
    return corpus_fingerprint_from_index_map(index_payload.get("unit_id_to_index", {}))


def build_corpus_index_payload(
    *,
    run_id: str,
    substrate_version: str | None,
    corpus: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Build the canonical corpus-index payload written beside embeddings."""
    corpus_list = list(corpus)
    corpus_ids = [str(unit.get("id", "")).strip() for unit in corpus_list if str(unit.get("id", "")).strip()]
    ordered_records = [corpus_record_from_unit(unit) for unit in corpus_list if str(unit.get("id", "")).strip()]
    return {
        "run_id": str(run_id),
        "substrate_version": str(substrate_version or ""),
        "corpus_fingerprint": corpus_fingerprint_from_ids(corpus_ids),
        "corpus_content_fingerprint": corpus_content_fingerprint_from_records(ordered_records),
        "unit_id_to_index": {uid: i for i, uid in enumerate(corpus_ids)},
        "ordered_corpus_records": ordered_records,
    }


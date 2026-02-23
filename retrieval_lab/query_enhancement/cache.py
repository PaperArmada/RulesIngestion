"""Deterministic file-based cache for query enhancement results."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import blake3

logger = logging.getLogger(__name__)


def _compute_cache_key(
    corpus_id: str,
    corpus_hash: str,
    profile_hash: str,
    query_norm: str,
    mode: str,
    model_id: str = "",
    prompt_hash: str = "",
) -> str:
    """Deterministic cache key from all inputs that affect output."""
    payload = "|".join([corpus_id, corpus_hash, profile_hash, query_norm, mode, model_id, prompt_hash])
    return blake3.blake3(payload.encode("utf-8")).hexdigest()


class QueryEnhancementCache:
    """File-based cache: one JSON file per (profile, query, mode) tuple."""

    def __init__(self, cache_dir: str | Path, enabled: bool = True):
        self._enabled = enabled
        self._dir = Path(cache_dir)
        if self._enabled:
            self._dir.mkdir(parents=True, exist_ok=True)

    def get(
        self,
        corpus_id: str,
        corpus_hash: str,
        profile_hash: str,
        query_norm: str,
        mode: str,
        model_id: str = "",
        prompt_hash: str = "",
    ) -> Optional[List[Dict[str, Any]]]:
        """Return cached expansion list, or None on miss."""
        if not self._enabled:
            return None
        key = _compute_cache_key(corpus_id, corpus_hash, profile_hash, query_norm, mode, model_id, prompt_hash)
        path = self._dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            logger.debug("Cache hit: %s", key[:16])
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Cache read error for %s: %s", key[:16], e)
            return None

    def put(
        self,
        corpus_id: str,
        corpus_hash: str,
        profile_hash: str,
        query_norm: str,
        mode: str,
        expansions: List[Dict[str, Any]],
        model_id: str = "",
        prompt_hash: str = "",
    ) -> None:
        """Persist expansion list to cache."""
        if not self._enabled:
            return
        key = _compute_cache_key(corpus_id, corpus_hash, profile_hash, query_norm, mode, model_id, prompt_hash)
        path = self._dir / f"{key}.json"
        try:
            path.write_text(
                json.dumps(expansions, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            logger.debug("Cache write: %s", key[:16])
        except OSError as e:
            logger.warning("Cache write error for %s: %s", key[:16], e)

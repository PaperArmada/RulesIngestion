"""SQLite-backed caches for tinker embeddings and LLM calls.

Both caches key by content hash so the same input always hits the same row.
Set env var TINKER_NOCACHE=1 to bypass writes and lookups for one process
(useful when iterating on prompts that share a hash).

Schema:
  embed_cache(model TEXT, text_sha256 TEXT, vector BLOB, dim INT, PRIMARY KEY)
  llm_cache(role TEXT, model TEXT, payload_sha256 TEXT, response TEXT, PRIMARY KEY)
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _vec_to_bytes(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def _vec_from_bytes(blob: bytes, dim: int) -> list[float]:
    return list(struct.unpack(f"<{dim}f", blob))


def _nocache() -> bool:
    return os.environ.get("TINKER_NOCACHE") == "1"


@dataclass
class CacheStats:
    embed_hits: int = 0
    embed_misses: int = 0
    llm_hits: int = 0
    llm_misses: int = 0


class TinkerCache:
    """SQLite-backed cache for embeddings and LLM call responses.

    Two tables share one DB file. Connections are reopened per call so the
    cache is safe to use across threads (sqlite3 module-level allowance).
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.stats = CacheStats()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS embed_cache (
                    model TEXT NOT NULL,
                    text_sha256 TEXT NOT NULL,
                    vector BLOB NOT NULL,
                    dim INTEGER NOT NULL,
                    PRIMARY KEY (model, text_sha256)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_cache (
                    role TEXT NOT NULL,
                    model TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    response TEXT NOT NULL,
                    PRIMARY KEY (role, model, payload_sha256)
                )
                """
            )

    # ------------------------------------------------------------------
    # Embedding cache
    # ------------------------------------------------------------------

    def get_embedding(self, model: str, text: str) -> list[float] | None:
        if _nocache():
            self.stats.embed_misses += 1
            return None
        h = _sha256(text)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT vector, dim FROM embed_cache WHERE model=? AND text_sha256=?",
                (model, h),
            ).fetchone()
        if row is None:
            self.stats.embed_misses += 1
            return None
        self.stats.embed_hits += 1
        return _vec_from_bytes(row[0], row[1])

    def put_embedding(self, model: str, text: str, vector: list[float]) -> None:
        if _nocache():
            return
        h = _sha256(text)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO embed_cache(model, text_sha256, vector, dim) "
                "VALUES(?, ?, ?, ?)",
                (model, h, _vec_to_bytes(vector), len(vector)),
            )

    # ------------------------------------------------------------------
    # LLM cache
    # ------------------------------------------------------------------

    def get_llm(self, role: str, model: str, payload: dict[str, Any]) -> str | None:
        if _nocache():
            self.stats.llm_misses += 1
            return None
        h = _sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False))
        with self._connect() as conn:
            row = conn.execute(
                "SELECT response FROM llm_cache WHERE role=? AND model=? AND payload_sha256=?",
                (role, model, h),
            ).fetchone()
        if row is None:
            self.stats.llm_misses += 1
            return None
        self.stats.llm_hits += 1
        return row[0]

    def put_llm(
        self, role: str, model: str, payload: dict[str, Any], response: str
    ) -> None:
        if _nocache():
            return
        h = _sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False))
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO llm_cache(role, model, payload_sha256, response) "
                "VALUES(?, ?, ?, ?)",
                (role, model, h, response),
            )

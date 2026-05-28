"""BM25 sparse retriever wrapping `retrieval_lab.sparse_retrieval`.

The wrapper persists the rank_bm25 index pickle alongside the corpus so
subsequent runs skip tokenization.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from retrieval_lab.sparse_retrieval import bm25_rank, build_bm25_index


@dataclass
class SparseIndex:
    """BM25 index over a fixed corpus."""

    bm25: Any
    unit_ids: list[str]

    @classmethod
    def from_corpus(
        cls,
        unit_ids: list[str],
        texts: list[str],
        *,
        tokenizer_mode: str = "basic",
    ) -> "SparseIndex":
        bm25 = build_bm25_index(texts, tokenizer_mode=tokenizer_mode)
        return cls(bm25=bm25, unit_ids=list(unit_ids))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"bm25": self.bm25, "unit_ids": self.unit_ids}, f)

    @classmethod
    def load(cls, path: Path) -> "SparseIndex":
        with open(path, "rb") as f:
            d = pickle.load(f)
        return cls(bm25=d["bm25"], unit_ids=list(d["unit_ids"]))

    def search(
        self, query: str, *, top_k: int = 20
    ) -> tuple[list[str], list[float]]:
        """Return (ranked ids, BM25 scores) for one query."""
        ranked, scores = bm25_rank(
            self.bm25,
            self.unit_ids,
            [{"query": query, "id": "_q"}],
            max_k=top_k,
            tokenizer_mode="basic",
            query_mode="question_only",
        )
        return list(ranked[0]), [float(s) for s in scores[0]]

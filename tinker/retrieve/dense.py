"""Minimal cosine-similarity dense retriever.

Deliberately bypasses `retrieval_lab/orchestration/dense_mode.py` (which
is tangled with the experiment-runner config) and exposes the smallest
useful surface: load a precomputed corpus embedding matrix, normalize
once, and return top-K for a query embedding.

Embedding format matches what `tinker.embed.embed_corpus` writes:
  <out_dir>/corpus_index.json   {model, dim, count, unit_ids, unit_id_to_index}
  <out_dir>/corpus.npy          float32 [N, dim]
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from tinker.embed import load_corpus_embeddings


def _normalize_rows(x: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(x, axis=1, keepdims=True) + 1e-9
    return x / norms


@dataclass
class DenseIndex:
    """In-memory cosine-similarity dense index over a fixed corpus."""

    unit_ids: list[str]
    unit_id_to_index: dict[str, int]
    embeddings: np.ndarray  # [N, D], rows normalized
    model: str
    dim: int

    @classmethod
    def load(cls, out_dir: Path) -> "DenseIndex":
        ids, id_to_idx, arr, meta = load_corpus_embeddings(out_dir)
        return cls(
            unit_ids=ids,
            unit_id_to_index=id_to_idx,
            embeddings=_normalize_rows(arr.astype(np.float32)),
            model=meta.get("model", ""),
            dim=int(meta.get("dim", arr.shape[1])),
        )

    def search(
        self,
        query_vec: Sequence[float] | np.ndarray,
        *,
        top_k: int = 20,
    ) -> tuple[list[str], list[float]]:
        """Return (ranked unit_ids, cosine scores) for the query vector.

        The query is normalized; scores are in [-1, 1] (typically positive).
        """
        q = np.asarray(query_vec, dtype=np.float32).reshape(-1)
        q = q / (np.linalg.norm(q) + 1e-9)
        if q.shape[0] != self.embeddings.shape[1]:
            raise ValueError(
                f"query dim {q.shape[0]} != corpus dim {self.embeddings.shape[1]}"
            )
        sims = self.embeddings @ q
        k = max(1, min(top_k, sims.shape[0]))
        # Partial sort for efficiency, then sort the top-K.
        top_idx_unsorted = np.argpartition(-sims, k - 1)[:k]
        top_idx = top_idx_unsorted[np.argsort(-sims[top_idx_unsorted])]
        ids = [self.unit_ids[i] for i in top_idx]
        scores = [float(sims[i]) for i in top_idx]
        return ids, scores

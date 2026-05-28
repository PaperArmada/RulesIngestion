"""Hybrid retrieval = dense + BM25 fused with Convex Combination (CC).

Uses `retrieval_lab.sparse_retrieval.convex_combination_fusion` directly;
canonical params are lam=0.7 (dense weight), minmax normalization, per
`retrieval_lab.config.{HYBRID_FUSION_METHOD_DEFAULT, CC_LAMBDA_DEFAULT,
CC_BM25_NORMALIZATION_DEFAULT}`.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from retrieval_lab.sparse_retrieval import convex_combination_fusion

from tinker.retrieve.dense import DenseIndex
from tinker.retrieve.sparse import SparseIndex


def hybrid_search(
    dense_index: DenseIndex,
    sparse_index: SparseIndex,
    query: str,
    query_vec: Sequence[float] | np.ndarray,
    *,
    top_k: int = 20,
    candidate_pool: int = 100,
    lam: float = 0.7,
    bm25_normalization: str = "minmax",
) -> tuple[list[str], list[float]]:
    """Hybrid retrieve: dense top-`candidate_pool` + BM25 top-`candidate_pool`,
    CC-fused, returning top-K fused.

    Returns (ranked_unit_ids, fused_scores).
    """
    dense_ids, dense_scores = dense_index.search(query_vec, top_k=candidate_pool)
    sparse_ids, sparse_scores = sparse_index.search(query, top_k=candidate_pool)
    fused_ids, fused_scores = convex_combination_fusion(
        dense_ranked_lists=[dense_ids],
        dense_score_lists=[dense_scores],
        bm25_ranked_lists=[sparse_ids],
        bm25_score_lists=[sparse_scores],
        lam=lam,
        bm25_normalization=bm25_normalization,
        max_k=top_k,
    )
    return list(fused_ids[0]), [float(s) for s in fused_scores[0]]

from __future__ import annotations

import numpy as np

from retrieval_lab.orchestration.dense_mode import _rerank_candidates_dense


def test_two_stage_dense_rerank_reorders_admitted_candidates() -> None:
    # Query aligns best with u3, then u2; only admitted candidates can be reranked.
    query_embeddings = np.array([[0.0, 1.0]], dtype=np.float32)
    corpus_embeddings = np.array(
        [
            [1.0, 0.0],  # u1
            [0.2, 0.8],  # u2
            [0.0, 1.0],  # u3
        ],
        dtype=np.float32,
    )
    ranked_lists = [["u1", "u2", "u3"]]
    reranked_ids, reranked_scores = _rerank_candidates_dense(
        query_embeddings=query_embeddings,
        corpus_embeddings=corpus_embeddings,
        corpus_ids=["u1", "u2", "u3"],
        ranked_lists=ranked_lists,
        stage1_admission_k=3,
        final_k=2,
    )
    assert reranked_ids == [["u3", "u2"]]
    assert len(reranked_scores[0]) == 2


def test_two_stage_dense_rerank_respects_stage1_admission_cap() -> None:
    query_embeddings = np.array([[0.0, 1.0]], dtype=np.float32)
    corpus_embeddings = np.array(
        [
            [1.0, 0.0],  # u1
            [0.0, 1.0],  # u2
            [0.0, 1.0],  # u3 (would score well but not admitted when cap=2)
        ],
        dtype=np.float32,
    )
    ranked_lists = [["u1", "u2", "u3"]]
    reranked_ids, _ = _rerank_candidates_dense(
        query_embeddings=query_embeddings,
        corpus_embeddings=corpus_embeddings,
        corpus_ids=["u1", "u2", "u3"],
        ranked_lists=ranked_lists,
        stage1_admission_k=2,
        final_k=3,
    )
    assert reranked_ids == [["u2", "u1"]]

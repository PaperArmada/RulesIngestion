"""
Sparse retrieval (BM25) and hybrid fusion (RRF).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def reciprocal_rank_fusion(
    rankings_per_query: List[List[List[str]]],
    k: int = 60,
    max_k: Optional[int] = None,
) -> Tuple[List[List[str]], List[List[float]]]:
    """
    Fuse multiple rankings per query using Reciprocal Rank Fusion (RRF).
    score(d) = sum over each source of 1 / (k + rank(d)); then sort by score descending.
    rankings_per_query[query_i][source_j] = list of doc IDs for query i from source j.
    Returns (fused_ranked_lists, fused_score_lists) with one list per query.
    """
    fused_ranked: List[List[str]] = []
    fused_scores: List[List[float]] = []
    for query_rankings in rankings_per_query:
        doc_scores: Dict[str, float] = {}
        for rank_list in query_rankings:
            for rank_1based, doc_id in enumerate(rank_list, start=1):
                doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + 1.0 / (k + rank_1based)
        sorted_ids = sorted(doc_scores.keys(), key=lambda d: doc_scores[d], reverse=True)
        if max_k is not None:
            sorted_ids = sorted_ids[:max_k]
        fused_ranked.append(sorted_ids)
        fused_scores.append([doc_scores[d] for d in sorted_ids])
    return fused_ranked, fused_scores


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


def build_bm25_index(corpus_texts: List[str]):
    try:
        from rank_bm25 import BM25Okapi
    except ImportError as e:
        raise RuntimeError(
            "BM25 requires rank_bm25. Install with: uv add rank_bm25 --optional retrieval-lab"
        ) from e
    tokenized = [_tokenize(t) for t in corpus_texts]
    return BM25Okapi(tokenized)


def bm25_rank(
    bm25,
    corpus_ids: List[str],
    queries: List[Dict[str, Any]],
    max_k: int,
) -> Tuple[List[List[str]], List[List[float]]]:
    ranked_lists: List[List[str]] = []
    score_lists: List[List[float]] = []
    for q in queries:
        q_text = q.get("question") or q.get("expected_answer_summary") or ""
        scores = np.asarray(bm25.get_scores(_tokenize(q_text)), dtype=np.float32)
        top_indices = np.argsort(scores)[::-1][:max_k]
        ranked_lists.append([corpus_ids[i] for i in top_indices])
        score_lists.append([float(scores[i]) for i in top_indices])
    return ranked_lists, score_lists

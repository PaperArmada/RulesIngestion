from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np


def compute_chapter_rerank_score(
    chapter_indices: List[int],
    chunk_ids: List[str],
    chunk_index_by_id: Dict[str, int],
    base_scores: np.ndarray,
    adjacency: Optional[Dict[str, Set[str]]],
    chunk_kind_by_id: Optional[Dict[str, Optional[str]]],
    graph_boost: float,
    graph_boost_depth: int,
    graph_boost_seed_top_n: int,
    graph_boost_same_kind_only: bool,
    graph_boost_decay: float,
    graph_boost_top_k: Optional[int],
) -> float:
    if not chapter_indices:
        return -float("inf")
    max_score = float(np.max(base_scores[chapter_indices]))
    if not adjacency or graph_boost <= 0:
        return max_score

    seed_top_n = max(1, int(graph_boost_seed_top_n or 1))
    top_indices = sorted(chapter_indices, key=lambda idx: base_scores[idx], reverse=True)[:seed_top_n]
    seed_ids = [chunk_ids[idx] for idx in top_indices if chunk_ids[idx] is not None]
    if not seed_ids:
        return max_score

    allowed_set = {chunk_ids[idx] for idx in chapter_indices if chunk_ids[idx] is not None}
    allowed_kinds: Set[str] = set()
    if graph_boost_same_kind_only and chunk_kind_by_id:
        for seed_id in seed_ids:
            seed_kind = chunk_kind_by_id.get(seed_id)
            if seed_kind:
                allowed_kinds.add(seed_kind)

    boost_candidates: Optional[Set[str]] = None
    if graph_boost_top_k:
        candidate_indices = sorted(
            chapter_indices, key=lambda idx: base_scores[idx], reverse=True
        )[:graph_boost_top_k]
        boost_candidates = {
            chunk_ids[idx] for idx in candidate_indices if chunk_ids[idx] is not None
        }

    depth_zero_boost = graph_boost
    if depth_zero_boost:
        for seed_id in seed_ids:
            idx = chunk_index_by_id.get(seed_id)
            if idx is None:
                continue
            max_score = max(max_score, float(base_scores[idx] + depth_zero_boost))

    seen = set(seed_ids)
    frontier = set(seed_ids)
    for depth in range(1, graph_boost_depth + 1):
        next_frontier: Set[str] = set()
        for node_id in frontier:
            for neighbor in adjacency.get(node_id, set()):
                if neighbor in seen or neighbor not in allowed_set:
                    continue
                if graph_boost_same_kind_only and allowed_kinds and chunk_kind_by_id:
                    neighbor_kind = chunk_kind_by_id.get(neighbor)
                    if neighbor_kind and neighbor_kind not in allowed_kinds:
                        continue
                seen.add(neighbor)
                next_frontier.add(neighbor)
        if not next_frontier:
            break
        depth_boost = graph_boost * (graph_boost_decay ** depth)
        if depth_boost:
            for boosted_id in next_frontier:
                if boost_candidates is not None and boosted_id not in boost_candidates:
                    continue
                idx = chunk_index_by_id.get(boosted_id)
                if idx is None:
                    continue
                max_score = max(max_score, float(base_scores[idx] + depth_boost))
        frontier = next_frontier

    return max_score


@dataclass
class ChapterRoutingResult:
    allowed_chunk_ids_by_query: List[Set[str]]
    chapter_routing_details: Optional[List[List[Dict[str, Any]]]]
    avg_allowed_chunks: float
    rerank_scores_by_query: Optional[Dict[str, Dict[str, float]]]
    pool_chapters_by_query: List[Set[str]]
    final_chapters_by_query: List[Set[str]]
    expected_recall: float


def build_chapter_routing(
    *,
    query_embeddings: np.ndarray,
    chapter_embeddings: np.ndarray,
    chapter_id_by_index: List[str],
    chapter_index_by_id: Dict[str, int],
    chapter_to_chunk_indices: Dict[str, List[int]],
    chunk_ids: List[str],
    chunk_embeddings: Optional[np.ndarray],
    query_document_ids: List[str],
    query_book_ids: Optional[List[str]],
    query_allowed_book_ids: Optional[List[Optional[Set[str]]]],
    chapter_book_ids: Dict[str, str],
    expected_ids: List[List[str]],
    adjacency_by_document: Optional[Dict[str, Dict[str, Set[str]]]],
    chunk_kind_by_id: Dict[str, Optional[str]],
    graph_boost: float,
    graph_boost_depth: int,
    graph_boost_top_k: Optional[int],
    graph_boost_seed_top_n: int,
    graph_boost_same_kind_only: bool,
    graph_boost_decay: float,
    top_n: int,
    rerank: bool = False,
    rerank_pool: Optional[int] = None,
    report_details: bool = False,
) -> ChapterRoutingResult:
    allowed_chunk_ids_by_query: List[Set[str]] = []
    chapter_routing_details: Optional[List[List[Dict[str, Any]]]] = [] if report_details else None
    expected_hits = 0
    allowed_counts: List[int] = []
    rerank_scores_by_query: Optional[Dict[str, Dict[str, float]]] = {} if rerank else None
    pool_chapters_by_query: List[Set[str]] = []
    final_chapters_by_query: List[Set[str]] = []

    chunk_index_by_id = {chunk_id: idx for idx, chunk_id in enumerate(chunk_ids)}

    for query_index, query_embedding in enumerate(query_embeddings):
        scores = chapter_embeddings @ query_embedding
        allowed_books: Optional[Set[str]] = None
        if query_allowed_book_ids is not None and query_index < len(query_allowed_book_ids):
            explicit_allowed = query_allowed_book_ids[query_index]
            if explicit_allowed:
                allowed_books = explicit_allowed
        if allowed_books is None and query_book_ids and query_index < len(query_book_ids):
            book_id = query_book_ids[query_index]
            if book_id and book_id != "unknown":
                allowed_books = {book_id}
        if allowed_books:
            eligible_indices = {
                idx
                for idx, chapter_id in enumerate(chapter_id_by_index)
                if chapter_book_ids.get(chapter_id) in allowed_books
            }
            if not eligible_indices:
                pool_chapters_by_query.append(set())
                final_chapters_by_query.append(set())
                allowed_chunk_ids_by_query.append(set())
                allowed_counts.append(0)
                if report_details and chapter_routing_details is not None:
                    chapter_routing_details.append([])
                if rerank_scores_by_query is not None:
                    rerank_scores_by_query[str(query_index)] = {}
                continue
            for idx in range(len(chapter_id_by_index)):
                if idx not in eligible_indices:
                    scores[idx] = -float("inf")
        pool_size = min(int(rerank_pool or top_n), len(chapter_id_by_index))
        top_pool_indices = np.argsort(scores)[::-1][:pool_size]
        top_pool_ids = [chapter_id_by_index[int(idx)] for idx in top_pool_indices]
        pool_chapters_by_query.append(set(top_pool_ids))
        rerank_scores: Dict[str, float] = {}
        if rerank and chunk_embeddings is not None:
            chunk_scores = chunk_embeddings @ query_embedding
            document_id = query_document_ids[query_index]
            adjacency = adjacency_by_document.get(document_id) if adjacency_by_document else None
            for chapter_id in top_pool_ids:
                indices = chapter_to_chunk_indices.get(chapter_id, [])
                rerank_scores[chapter_id] = compute_chapter_rerank_score(
                    indices,
                    chunk_ids,
                    chunk_index_by_id,
                    chunk_scores,
                    adjacency,
                    chunk_kind_by_id,
                    graph_boost,
                    graph_boost_depth,
                    graph_boost_seed_top_n,
                    graph_boost_same_kind_only,
                    graph_boost_decay,
                    graph_boost_top_k,
                )
            top_pool_ids = sorted(
                top_pool_ids,
                key=lambda chapter_id: rerank_scores.get(chapter_id, -float("inf")),
                reverse=True,
            )
        top_ids = top_pool_ids[:top_n]
        final_chapters_by_query.append(set(top_ids))
        allowed_chunks: Set[str] = set()
        for chapter_id in top_ids:
            for idx in chapter_to_chunk_indices.get(chapter_id, []):
                allowed_chunks.add(chunk_ids[idx])
        allowed_chunk_ids_by_query.append(allowed_chunks)
        allowed_counts.append(len(allowed_chunks))
        expected = expected_ids[query_index]
        if set(expected) & allowed_chunks:
            expected_hits += 1
        if report_details and chapter_routing_details is not None:
            chapter_routing_details.append(
                [
                    {
                        "chapter_id": chapter_id,
                        "score": float(
                            rerank_scores.get(chapter_id, scores[chapter_index_by_id[chapter_id]])
                            if rerank
                            else scores[chapter_index_by_id[chapter_id]]
                        ),
                        "summary_score": float(scores[chapter_index_by_id[chapter_id]]),
                        "rerank_score": float(rerank_scores.get(chapter_id, 0.0)) if rerank else None,
                        "book_id": chapter_book_ids.get(chapter_id),
                        "allowed_books": sorted(allowed_books) if allowed_books else None,
                    }
                    for chapter_id in top_ids
                ]
            )
        if rerank_scores_by_query is not None:
            rerank_scores_by_query[str(query_index)] = rerank_scores

    avg_allowed_chunks = float(sum(allowed_counts) / len(allowed_counts)) if allowed_counts else 0.0
    expected_recall = float(expected_hits / len(query_embeddings)) if len(query_embeddings) else 0.0
    return ChapterRoutingResult(
        allowed_chunk_ids_by_query=allowed_chunk_ids_by_query,
        chapter_routing_details=chapter_routing_details,
        avg_allowed_chunks=avg_allowed_chunks,
        rerank_scores_by_query=rerank_scores_by_query,
        pool_chapters_by_query=pool_chapters_by_query,
        final_chapters_by_query=final_chapters_by_query,
        expected_recall=expected_recall,
    )


def resolve_chapter_id(document_id: str, section_path: Sequence[str]) -> str:
    if section_path:
        return f"{document_id}::{section_path[0]}"
    return f"{document_id}"


def extract_book_id_from_path(run_outputs_dir: Optional[str]) -> Optional[str]:
    if not run_outputs_dir:
        return None
    path = Path(run_outputs_dir).resolve()
    for parent in path.parents:
        if parent.name == "outputs":
            book_dir = parent.parent
            if (book_dir / "outputs").exists():
                return book_dir.name
    return None


def normalize_book_id(document_id: Optional[str], default_book_id: Optional[str] = None) -> str:
    if default_book_id:
        return default_book_id
    if not document_id:
        return "unknown"
    match = re.match(r"^(.*?)(?:-\\d{3}-\\d{3}|-\\d{3})$", document_id)
    if match:
        return match.group(1)
    return document_id


def resolve_chapter_book_id(chapter_id: str, default_book_id: Optional[str] = None) -> str:
    if not chapter_id:
        return default_book_id or "unknown"
    if default_book_id:
        return default_book_id
    document_id = chapter_id.split("::", 1)[0]
    return normalize_book_id(document_id)


def build_chapter_index(
    chunks: List[Dict[str, Any]]
) -> Tuple[
    Dict[str, List[int]],
    Dict[str, str],
    Dict[str, List[str]],
]:
    chapter_to_chunk_indices: Dict[str, List[int]] = {}
    chunk_to_chapter: Dict[str, str] = {}
    chapter_to_titles: Dict[str, List[str]] = {}
    for idx, chunk in enumerate(chunks):
        document_id = chunk.get("document_id") or "unknown"
        section_path = chunk.get("section_path") or []
        chapter_id = resolve_chapter_id(document_id, section_path)
        chapter_to_chunk_indices.setdefault(chapter_id, []).append(idx)
        chunk_to_chapter[chunk["id"]] = chapter_id
        if section_path:
            chapter_to_titles.setdefault(chapter_id, []).append(section_path[0])
    return chapter_to_chunk_indices, chunk_to_chapter, chapter_to_titles


def build_chapter_summary_texts(
    chunks: List[Dict[str, Any]],
    chapter_to_chunk_indices: Dict[str, List[int]],
    chapter_to_titles: Dict[str, List[str]],
    *,
    max_chunks: int = 10,
    max_chars: int = 1200,
) -> Dict[str, str]:
    summary_texts: Dict[str, str] = {}
    for chapter_id, indices in chapter_to_chunk_indices.items():
        title = None
        titles = chapter_to_titles.get(chapter_id) or []
        if titles:
            title = titles[0]
        ordered = sorted(indices, key=lambda idx: (chunks[idx].get("page") or 0, idx))
        selected = ordered[:max_chunks]
        parts = []
        if title:
            parts.append(title)
        for idx in selected:
            text = chunks[idx].get("text") or ""
            if text:
                parts.append(text.strip())
        summary = "\\n\\n".join(parts).strip()
        if len(summary) > max_chars:
            summary = summary[:max_chars].rsplit(" ", 1)[0]
        summary_texts[chapter_id] = summary
    return summary_texts

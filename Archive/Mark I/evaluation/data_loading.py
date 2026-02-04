from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


def _normalize_heading_text(text: str) -> str:
    cleaned = (text or "").replace("**", "").replace("__", "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _build_section_path_from_hierarchy(
    section_hierarchy: Dict[str, Any], chunk_lookup: Dict[str, Dict[str, Any]]
) -> List[str]:
    if not section_hierarchy:
        return []
    items = list(section_hierarchy.items())

    def _sort_key(item: Any) -> Any:
        key = item[0]
        try:
            return int(key)
        except (TypeError, ValueError):
            return str(key)

    path: List[str] = []
    for _, raw_id in sorted(items, key=_sort_key):
        if not raw_id:
            continue
        header_chunk = chunk_lookup.get(raw_id)
        if header_chunk is None and not str(raw_id).startswith("coalesced-"):
            header_chunk = chunk_lookup.get(f"coalesced-{raw_id}")
        if not header_chunk:
            continue
        heading_text = _normalize_heading_text(header_chunk.get("text") or "")
        if heading_text:
            path.append(heading_text)
    return path


def extract_chunks(outputs: Dict[str, Any], chunk_source: str) -> List[Dict[str, Any]]:
    payload = outputs.get(chunk_source) or {}
    chunks = payload.get("chunks") or []
    chunk_lookup: Dict[str, Dict[str, Any]] = {}
    for chunk in chunks:
        chunk_id = chunk.get("id")
        if not chunk_id:
            continue
        chunk_lookup[chunk_id] = chunk
        if isinstance(chunk_id, str) and "::" in chunk_id:
            _, suffix = chunk_id.split("::", 1)
            chunk_lookup.setdefault(suffix, chunk)
    normalized: List[Dict[str, Any]] = []
    for chunk in chunks:
        text = chunk.get("text") or chunk.get("content") or ""
        section_path = chunk.get("section_path") or []
        section_hierarchy = chunk.get("section_hierarchy") or {}
        if not section_path and section_hierarchy:
            section_path = _build_section_path_from_hierarchy(
                section_hierarchy, chunk_lookup
            )
        normalized.append(
            {
                "id": chunk.get("id"),
                "text": text,
                "page": chunk.get("page"),
                "section_path": section_path,
                "section_hierarchy": section_hierarchy,
                "block_type": chunk.get("block_type"),
                "content_kind": chunk.get("content_kind"),
                "document_id": chunk.get("document_id"),
            }
        )
    _backfill_section_paths(normalized)
    return normalized


def _parse_chunk_position(chunk_id: Optional[str]) -> Tuple[int, int]:
    if not chunk_id:
        return (1_000_000_000, 1_000_000_000)
    match = re.search(r"/page/(\d+)/[^/]+/(\d+)$", chunk_id)
    if not match:
        return (1_000_000_000, 1_000_000_000)
    return (int(match.group(1)), int(match.group(2)))


def _backfill_section_paths(chunks: List[Dict[str, Any]]) -> None:
    by_document: Dict[str, List[int]] = {}
    for idx, chunk in enumerate(chunks):
        document_id = chunk.get("document_id") or "unknown"
        by_document.setdefault(document_id, []).append(idx)

    for document_id, indices in by_document.items():
        indices.sort(key=lambda i: _parse_chunk_position(chunks[i].get("id")))
        has_any_section = any(
            (chunks[i].get("section_path") or []) for i in indices
        )
        last_section_path: Optional[List[str]] = None
        for idx in indices:
            chunk = chunks[idx]
            section_path = chunk.get("section_path") or []
            if section_path:
                last_section_path = section_path
                continue
            if last_section_path:
                chunk["section_path"] = last_section_path
            elif not has_any_section:
                chunk["section_path"] = [document_id]
            else:
                chunk["section_path"] = [document_id]


def extract_queries(outputs: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload = outputs.get("evaluation_queries") or {}
    return payload.get("queries") or []


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_chapter_summary_payload(path: str) -> Dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError("chapter summary payload must be a JSON object.")
    if "chapters" not in payload:
        raise ValueError("chapter summary payload is missing 'chapters'.")
    return payload


def load_chapter_summary_embeddings(path: str) -> Tuple[List[str], np.ndarray]:
    payload = load_json(path)
    chapters = payload.get("chapters") or []
    chapter_ids: List[str] = []
    vectors: List[np.ndarray] = []
    for chapter in chapters:
        chapter_id = chapter.get("chapter_id")
        embedding = chapter.get("embedding")
        if not chapter_id or embedding is None:
            continue
        chapter_ids.append(chapter_id)
        vectors.append(np.array(embedding, dtype=np.float32))
    if not chapter_ids:
        raise ValueError(f"No chapter embeddings found in {path}")
    return chapter_ids, np.vstack(vectors)


def load_chunk_embeddings_from_file(path: str) -> Tuple[List[str], np.ndarray]:
    payload = load_json(path)
    chunks = payload.get("chunks") or []
    chunk_ids: List[str] = []
    vectors: List[np.ndarray] = []
    for chunk in chunks:
        chunk_id = chunk.get("chunk_id")
        embedding = chunk.get("embedding")
        if not chunk_id or embedding is None:
            continue
        chunk_ids.append(chunk_id)
        vectors.append(np.array(embedding, dtype=np.float32))
    if not chunk_ids:
        raise ValueError(f"No chunk embeddings found in {path}")
    print(f"♻️ Loaded {len(chunk_ids)} chunk embeddings from {path}")
    return chunk_ids, np.vstack(vectors)


def save_chunk_embeddings_to_file(
    path: str,
    chunk_ids: List[str],
    embeddings: np.ndarray,
    model_id: str,
    model_name: str,
) -> None:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    payload = {
        "model_id": model_id,
        "model_name": model_name,
        "chunk_count": len(chunk_ids),
        "chunks": [
            {"chunk_id": chunk_id, "embedding": embeddings[idx].tolist()}
            for idx, chunk_id in enumerate(chunk_ids)
        ],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    print(f"💾 Saved {len(chunk_ids)} chunk embeddings to {path}")


def load_chapter_summary_embeddings_from_records(
    records: List[Dict[str, Any]],
) -> Tuple[List[str], np.ndarray]:
    chapter_ids: List[str] = []
    vectors: List[np.ndarray] = []
    for record in records:
        chapter_id = record.get("chapter_id")
        embedding = record.get("embedding")
        if not chapter_id or embedding is None:
            continue
        chapter_ids.append(chapter_id)
        vectors.append(np.array(embedding, dtype=np.float32))
    if not chapter_ids:
        raise ValueError("No chapter embeddings found in stored records.")
    return chapter_ids, np.vstack(vectors)


def derive_outputs_from_queries_path(queries_path: str, chunk_source: str) -> Dict[str, Any]:
    queries_path = os.path.abspath(queries_path)
    if not os.path.isfile(queries_path):
        raise FileNotFoundError(f"Evaluation queries file not found: {queries_path}")

    directory = os.path.dirname(queries_path)
    filename = os.path.basename(queries_path)
    if not filename.endswith(".evaluation_queries.json"):
        raise ValueError("Expected file name to end with .evaluation_queries.json")

    doc_id = filename[: -len(".evaluation_queries.json")]
    chunks_filename = f"{doc_id}.{chunk_source}.json"
    chunks_path = os.path.join(directory, chunks_filename)
    if not os.path.isfile(chunks_path):
        raise FileNotFoundError(f"Chunk file not found for {chunk_source}: {chunks_path}")

    graph_path = os.path.join(directory, f"{doc_id}.graph.json")
    graph_payload = load_json(graph_path) if os.path.isfile(graph_path) else None

    return {
        "document_id": doc_id,
        "chunks": load_json(chunks_path),
        "queries": load_json(queries_path),
        "graph": graph_payload,
    }


def derive_outputs_from_queries_dir(
    queries_dir: str, chunk_source: str, skip_missing_chunks: bool = False
) -> List[Dict[str, Any]]:
    if not os.path.isdir(queries_dir):
        raise FileNotFoundError(f"Queries directory not found: {queries_dir}")
    datasets: List[Dict[str, Any]] = []
    for root, _, files in os.walk(queries_dir):
        for name in files:
            if not name.endswith(".evaluation_queries.json"):
                continue
            path = os.path.join(root, name)
            try:
                datasets.append(derive_outputs_from_queries_path(path, chunk_source))
            except FileNotFoundError:
                if skip_missing_chunks:
                    continue
                raise
    if not datasets:
        raise ValueError(f"No evaluation_queries.json files found in {queries_dir}")
    return datasets


def resolve_queries_path_from_run_dir(run_outputs_dir: str) -> str:
    if not os.path.isdir(run_outputs_dir):
        raise FileNotFoundError(f"Run outputs directory not found: {run_outputs_dir}")

    preferred = os.path.join(run_outputs_dir, "merged.evaluation_queries.json")
    if os.path.isfile(preferred):
        return preferred

    matches = [
        os.path.join(run_outputs_dir, name)
        for name in os.listdir(run_outputs_dir)
        if name.endswith(".evaluation_queries.json")
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise FileNotFoundError(
            f"No *.evaluation_queries.json found in run outputs directory: {run_outputs_dir}"
        )
    raise ValueError(
        "Multiple evaluation_queries.json files found in run outputs directory; "
        "specify --queries-path explicitly."
    )


def normalize_document_ids(
    chunks: List[Dict[str, Any]],
    queries: List[Dict[str, Any]],
    document_id: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    normalized_chunks: List[Dict[str, Any]] = []
    normalized_queries: List[Dict[str, Any]] = []
    for chunk in chunks:
        normalized = dict(chunk)
        chunk_id = chunk["id"]
        if isinstance(chunk_id, str) and "::" in chunk_id:
            normalized["id"] = chunk_id
        else:
            normalized["id"] = f"{document_id}::{chunk_id}"
        normalized["document_id"] = normalized.get("document_id") or document_id
        normalized_chunks.append(normalized)
    for query in queries:
        normalized = dict(query)
        expected = []
        for cid in query.get("expected_chunk_ids", []):
            if isinstance(cid, str) and "::" in cid:
                expected.append(cid)
            else:
                expected.append(f"{document_id}::{cid}")
        normalized["expected_chunk_ids"] = expected
        normalized["document_id"] = normalized.get("document_id") or document_id
        normalized_queries.append(normalized)
    return normalized_chunks, normalized_queries


def filter_documents(
    *,
    chunks: List[Dict[str, Any]],
    queries: List[Dict[str, Any]],
    document_ids: List[str],
    graph_by_document: Dict[str, Optional[Dict[str, Any]]],
    document_ids_filter: Optional[Sequence[str]],
    document_prefixes: Optional[Sequence[str]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str], Dict[str, Optional[Dict[str, Any]]]]:
    if not document_ids_filter and not document_prefixes:
        return chunks, queries, document_ids, graph_by_document
    allowed = set(document_ids_filter or [])
    prefixes = list(document_prefixes or [])
    if prefixes:
        for doc_id in document_ids:
            if any(doc_id.startswith(prefix) for prefix in prefixes):
                allowed.add(doc_id)
    document_ids = [doc_id for doc_id in document_ids if doc_id in allowed]
    filtered_chunks = [chunk for chunk in chunks if chunk.get("document_id") in allowed]
    filtered_queries = [query for query in queries if query.get("document_id") in allowed]
    filtered_graphs = {doc_id: graph_by_document.get(doc_id) for doc_id in document_ids}
    return filtered_chunks, filtered_queries, document_ids, filtered_graphs

"""Embedding preparation helpers for benchmarks."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

import numpy as np

from evaluation.data_loading import load_chunk_embeddings_from_file, save_chunk_embeddings_to_file
from evaluation.model_registry import EmbeddingModelSpec, encode_texts, load_model


def _require_store(store: Optional[Any], action: str) -> Any:
    if not store:
        raise ValueError(f"{action} requires benchmark store operations to be provided.")
    return store


def resolve_chunk_embeddings(
    chunk_ids: Sequence[str],
    chunk_texts: Sequence[str],
    model_spec: EmbeddingModelSpec,
    batch_size: int,
    trust_remote_code: bool,
    embedding_cache: Optional[Dict[str, Any]],
    chunk_embedding_path: Optional[str],
    chunk_embedding_output: Optional[str],
    reuse_embeddings: bool,
    embedding_run_id: Optional[str],
    run_id: Optional[str],
    store: Optional[Any],
    mongo_uri: Optional[str],
    clear_existing: bool,
) -> Tuple[np.ndarray, int, bool, Optional[str], Optional[Any]]:
    embed_duration_ms = 0
    embedding_reused = False
    embedding_reuse_reason: Optional[str] = None
    model = None
    unique_chunk_ids = list(dict.fromkeys(chunk_ids))
    duplicate_count = len(chunk_ids) - len(unique_chunk_ids)

    if embedding_cache and "chunk_embeddings" in embedding_cache:
        chunk_embeddings = embedding_cache["chunk_embeddings"]
        embedding_reused = True
        embedding_reuse_reason = "cached"
        print("♻️ Using cached chunk embeddings from memory")
    elif chunk_embedding_path and os.path.exists(chunk_embedding_path):
        print(f"📦 Loading chunk embeddings from file: {chunk_embedding_path}")
        stored_ids, stored_embeddings = load_chunk_embeddings_from_file(chunk_embedding_path)
        stored_map = {chunk_id: idx for idx, chunk_id in enumerate(stored_ids)}
        if len(stored_map) == len(unique_chunk_ids) and all(
            chunk_id in stored_map for chunk_id in unique_chunk_ids
        ):
            chunk_embeddings = np.array(
                [stored_embeddings[stored_map[chunk_id]] for chunk_id in chunk_ids],
                dtype=np.float32,
            )
            embedding_reused = True
            embedding_reuse_reason = "file_cache"
        else:
            print("⚠️ Chunk embedding file exists but IDs mismatch, regenerating...")
            embedding_reuse_reason = "file_cache_mismatch"
            model = load_model(model_spec.model_name, trust_remote_code=trust_remote_code)
            embed_start = time.time()
            chunk_embeddings = encode_texts(model, chunk_texts, batch_size=batch_size)
            embed_duration_ms = int((time.time() - embed_start) * 1000)
    else:
        embedding_lookup_id = embedding_run_id or run_id
        if reuse_embeddings:
            print(
                "🔎 Reuse requested: "
                f"lookup_id={embedding_lookup_id}, model_id={model_spec.model_id}, "
                f"store={'yes' if store else 'no'}, clear_existing={clear_existing}"
            )
        if embedding_lookup_id and store and not clear_existing:
            store_ops = _require_store(store, "Reusing embeddings")
            print(
                "🗄️ Querying Mongo embeddings: "
                f"run_id={embedding_lookup_id}, model_id={model_spec.model_id}"
            )
            stored = store_ops.fetch_chunk_embeddings(embedding_lookup_id, model_spec.model_id, mongo_uri)
            stored_map = {record.get("chunk_id"): record.get("embedding") for record in stored}
            print(
                "🧾 Mongo embeddings fetched: "
                f"records={len(stored)}, unique_ids={len(stored_map)}, "
                f"expected_ids={len(chunk_ids)}, duplicates={duplicate_count}"
            )
            if len(stored_map) == len(unique_chunk_ids) and all(
                chunk_id in stored_map for chunk_id in unique_chunk_ids
            ):
                chunk_embeddings = np.array(
                    [stored_map[chunk_id] for chunk_id in chunk_ids], dtype=np.float32
                )
                embedding_reused = True
                embedding_reuse_reason = "store_cache"
            else:
                embedding_reuse_reason = (
                    "store_cache_mismatch" if stored else "store_cache_miss"
                )
        if not embedding_reused:
            if reuse_embeddings and not embedding_lookup_id:
                embedding_reuse_reason = "embedding_run_id or run_id required for reuse"
            if reuse_embeddings and embedding_lookup_id and not store:
                embedding_reuse_reason = "store not provided"
            if reuse_embeddings:
                print(f"⚠️ Reuse failed: reason={embedding_reuse_reason}")
            model = load_model(model_spec.model_name, trust_remote_code=trust_remote_code)
            embed_start = time.time()
            chunk_embeddings = encode_texts(model, chunk_texts, batch_size=batch_size)
            embed_duration_ms = int((time.time() - embed_start) * 1000)

    if chunk_embedding_output and not embedding_reused:
        save_chunk_embeddings_to_file(
            chunk_embedding_output,
            chunk_ids,
            chunk_embeddings,
            model_spec.model_id,
            model_spec.model_name,
        )

    return chunk_embeddings, embed_duration_ms, embedding_reused, embedding_reuse_reason, model


def resolve_query_embeddings(
    query_texts: Sequence[str],
    model_spec: EmbeddingModelSpec,
    batch_size: int,
    trust_remote_code: bool,
    embedding_cache: Optional[Dict[str, Any]],
    model: Optional[Any],
) -> Tuple[np.ndarray, int, Optional[Any]]:
    query_embed_duration_ms = 0
    if embedding_cache and "query_embeddings" in embedding_cache:
        query_embeddings = embedding_cache["query_embeddings"]
    else:
        if model is None:
            model = load_model(model_spec.model_name, trust_remote_code=trust_remote_code)
        query_embed_start = time.time()
        query_embeddings = encode_texts(model, query_texts, batch_size=batch_size)
        query_embed_duration_ms = int((time.time() - query_embed_start) * 1000)

    return query_embeddings, query_embed_duration_ms, model


def resolve_answer_embeddings(
    answer_texts: Sequence[str],
    model_spec: EmbeddingModelSpec,
    batch_size: int,
    trust_remote_code: bool,
    model: Optional[Any],
) -> Tuple[np.ndarray, int, Optional[Any]]:
    answer_embed_duration_ms = 0
    if model is None:
        model = load_model(model_spec.model_name, trust_remote_code=trust_remote_code)
    answer_embed_start = time.time()
    answer_embeddings = encode_texts(model, answer_texts, batch_size=batch_size)
    answer_embed_duration_ms = int((time.time() - answer_embed_start) * 1000)
    return answer_embeddings, answer_embed_duration_ms, model

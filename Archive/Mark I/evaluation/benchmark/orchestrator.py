from __future__ import annotations

import json
import logging
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np

from evaluation.benchmark.embedding import (
    resolve_answer_embeddings,
    resolve_chunk_embeddings,
    resolve_query_embeddings,
)
from evaluation.benchmark.traversal import score_traversal_runs
from evaluation.chapter_routing import (
    ChapterRoutingResult,
    build_chapter_index,
    build_chapter_routing,
    build_chapter_summary_texts,
    extract_book_id_from_path,
    normalize_book_id,
    resolve_chapter_book_id,
)
from evaluation.data_loading import (
    derive_outputs_from_queries_dir,
    derive_outputs_from_queries_path,
    extract_chunks,
    extract_queries,
    filter_documents,
    load_chapter_summary_embeddings,
    load_chapter_summary_embeddings_from_records,
    load_chapter_summary_payload,
    load_json,
    normalize_document_ids,
)
from evaluation.graph_ops import build_graph_adjacency, build_section_index, expand_expected_ids
from evaluation.llm_summarization import parse_summary_lengths, summarize_chapter_with_llm
from evaluation.metrics import (
    compute_baseline_delta,
    compute_cross_book_reachability,
    compute_reachability_monotonicity,
)
from evaluation.model_registry import EmbeddingModelSpec, encode_texts, load_model
from evaluation.scoring_engine import estimate_scoring_time_ms, score_queries


logger = logging.getLogger(__name__)


@dataclass
class BenchmarkStoreOps:
    fetch_run_outputs: Callable[[str, Optional[str]], Optional[Dict[str, Any]]]
    fetch_chunk_embeddings: Callable[[str, str, Optional[str]], List[Dict[str, Any]]]
    fetch_chapter_embeddings: Callable[[str, str, Optional[str]], List[Dict[str, Any]]]
    get_mongo_client: Callable[[Optional[str]], Any]
    ensure_benchmark_indexes: Callable[[Any], None]
    save_chunk_embeddings: Callable[
        [Iterable[Dict[str, Any]], Optional[str], bool, Optional[str], Optional[str]], int
    ]
    save_chapter_embeddings: Callable[
        [Iterable[Dict[str, Any]], Optional[str], bool, Optional[str], Optional[str]], int
    ]
    save_embedding_run: Callable[[Dict[str, Any], Optional[str]], str]
    save_evaluation_run: Callable[[Dict[str, Any], Optional[str]], str]


def _require_store(store: Optional[BenchmarkStoreOps], action: str) -> BenchmarkStoreOps:
    if not store:
        raise ValueError(f"{action} requires benchmark store operations to be provided.")
    return store


def run_embedding_benchmark(
    run_id: Optional[str],
    model_spec: EmbeddingModelSpec,
    chunk_source: str = "coalesced",
    mongo_uri: Optional[str] = None,
    batch_size: int = 16,
    top_k: Iterable[int] = (1, 3, 5, 10),
    ruleset_id: Optional[str] = None,
    clear_existing: bool = False,
    queries_path: Optional[str] = None,
    queries_dir: Optional[str] = None,
    trust_remote_code: bool = False,
    skip_missing_chunks: bool = False,
    expand_gold: bool = False,
    gold_next_depth: int = 1,
    gold_include_section: bool = True,
    gold_same_kind_only: bool = False,
    gold_max_total: int = 12,
    graph_boost: float = 0.0,
    graph_boost_depth: int = 1,
    graph_boost_top_k: Optional[int] = None,
    graph_boost_source: str = "expected",
    graph_boost_seed_top_n: int = 1,
    graph_boost_same_kind_only: bool = False,
    graph_boost_decay: float = 1.0,
    routing_prior_boost: float = 0.0,
    routing_prior_pool_multiplier: float = 1.0,
    routing_seeded_boost: bool = False,
    reuse_embeddings: bool = False,
    document_ids_filter: Optional[Sequence[str]] = None,
    document_prefixes: Optional[Sequence[str]] = None,
    query_limit: Optional[int] = None,
    query_seed: Optional[int] = None,
    baseline_report_path: Optional[str] = None,
    embedding_run_id: Optional[str] = None,
    chapter_routing_top_n: Optional[int] = None,
    chapter_embedding_source: str = "summary",
    chapter_routing_report: bool = False,
    chapter_routing_rerank: bool = False,
    chapter_summary_only: bool = False,
    chapter_summary_output: Optional[str] = None,
    chapter_summary_embed: bool = False,
    chapter_summary_embedding_output: Optional[str] = None,
    chapter_summary_embedding_path: Optional[str] = None,
    chapter_summary_embedding_run_id: Optional[str] = None,
    force_chapter_summary_regen: bool = False,
    embedding_cache: Optional[Dict[str, Any]] = None,
    return_embeddings: bool = False,
    chapter_summary_llm: bool = False,
    chapter_summary_llm_model: Optional[str] = None,
    chapter_summary_llm_temperature: float = 0.2,
    chapter_summary_llm_max_input_chars: int = 12000,
    chapter_summary_llm_segment_max_chars: int = 600,
    chunk_embedding_output: Optional[str] = None,
    chunk_embedding_path: Optional[str] = None,
    chapter_summary_llm_lengths: Optional[str] = None,
    chapter_summary_llm_embed_key: str = "medium",
    chapter_summary_llm_api_key: Optional[str] = None,
    traversal_eval: bool = False,
    toc_traversal_eval: bool = False,
    toc_scope_depth: Optional[int] = None,
    chapter_routing_rerank_pool: Optional[int] = None,
    store: Optional[BenchmarkStoreOps] = None,
    answer_similarity: bool = False,
    retrieval_method: str = "embedding",
) -> Dict[str, Any]:
    total_start = time.time()

    detected_book_id = extract_book_id_from_path(queries_path) or extract_book_id_from_path(queries_dir)
    if detected_book_id:
        print(f"📚 Detected book ID from path: {detected_book_id}")

    datasets: List[Dict[str, Any]] = []
    if queries_path:
        datasets = [derive_outputs_from_queries_path(queries_path, chunk_source)]
    elif queries_dir:
        datasets = derive_outputs_from_queries_dir(
            queries_dir, chunk_source, skip_missing_chunks=skip_missing_chunks
        )
    else:
        if not run_id:
            raise ValueError("run_id is required when queries_path/queries_dir is not provided.")
        store_ops = _require_store(store, "Loading run outputs")
        outputs = store_ops.fetch_run_outputs(run_id, mongo_uri)
        if not outputs:
            raise ValueError(f"Run outputs not found for run_id={run_id}")
        datasets = [
            {
                "document_id": outputs.get(chunk_source, {}).get("document"),
                "chunks": outputs.get(chunk_source),
                "queries": outputs.get("evaluation_queries"),
                "graph": outputs.get("graph"),
            }
        ]

    combined_chunks: List[Dict[str, Any]] = []
    combined_queries: List[Dict[str, Any]] = []
    document_ids: List[str] = []
    graph_by_document: Dict[str, Optional[Dict[str, Any]]] = {}

    for dataset in datasets:
        document_id = dataset.get("document_id") or "unknown"
        chunks_payload = dataset.get("chunks") or {}
        queries_payload = dataset.get("queries") or {}
        graph_by_document[document_id] = dataset.get("graph")
        document_ids.append(document_id)

        chunks = extract_chunks({chunk_source: chunks_payload}, chunk_source)
        queries = extract_queries({"evaluation_queries": queries_payload})

        normalized_chunks, normalized_queries = normalize_document_ids(chunks, queries, document_id)
        combined_chunks.extend(normalized_chunks)
        combined_queries.extend(normalized_queries)

    chunks = combined_chunks
    queries = combined_queries
    chunks, queries, document_ids, graph_by_document = filter_documents(
        chunks=chunks,
        queries=queries,
        document_ids=document_ids,
        graph_by_document=graph_by_document,
        document_ids_filter=document_ids_filter,
        document_prefixes=document_prefixes,
    )
    if query_limit is not None and query_limit > 0 and len(queries) > query_limit:
        rng = random.Random(query_seed)
        queries = rng.sample(queries, k=query_limit)
    if not chunks:
        raise ValueError(f"No chunks found for run_id={run_id} ({chunk_source})")
    if not queries:
        raise ValueError(f"No evaluation queries found for run_id={run_id}")
    print(
        "📊 Loaded evaluation data: "
        f"documents={len(set(document_ids))}, "
        f"chunks={len(chunks)}, "
        f"queries={len(queries)}, "
        f"chunk_source={chunk_source}"
    )

    chunk_ids = [chunk["id"] for chunk in chunks]
    if any(chunk_id is None for chunk_id in chunk_ids):
        raise ValueError("Chunk IDs are missing from run outputs; cannot evaluate.")
    chunk_texts = [chunk["text"] for chunk in chunks]
    chunk_document_ids = {
        chunk["id"]: chunk.get("document_id") or "unknown" for chunk in chunks
    }
    chunk_book_ids = {
        chunk_id: normalize_book_id(document_id, default_book_id=detected_book_id)
        for chunk_id, document_id in chunk_document_ids.items()
    }
    chunk_kind_by_id = {chunk["id"]: chunk.get("content_kind") for chunk in chunks}

    chapter_to_chunk_indices, chunk_to_chapter, chapter_to_titles = build_chapter_index(chunks)
    if chapter_summary_only:
        summary_source = "first_10_chunks"
        summary_texts: Dict[str, str] = {}
        chapter_variants: Dict[str, Dict[str, str]] = {}
        chapter_payload: Dict[str, Any]
        reuse_existing = (
            chapter_summary_output
            and os.path.exists(chapter_summary_output)
            and not force_chapter_summary_regen
        )
        if reuse_existing:
            chapter_payload = load_chapter_summary_payload(chapter_summary_output)
            summary_source = chapter_payload.get("summary_source", "existing")
            for chapter in chapter_payload.get("chapters", []):
                chapter_id = chapter.get("chapter_id")
                if not chapter_id:
                    continue
                summary_texts[chapter_id] = chapter.get("summary_text", "") or ""
                variants = chapter.get("summary_variants")
                if isinstance(variants, dict):
                    chapter_variants[chapter_id] = variants
            print(f"♻️ Reusing existing chapter summaries: {chapter_summary_output}")
        else:
            if chapter_summary_llm:
                api_key = chapter_summary_llm_api_key or os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("OPENAI_API_KEY is required for LLM chapter summaries.")
                llm_model = chapter_summary_llm_model or os.getenv("OPENAI_MODEL", "gpt-5.2")
                lengths = parse_summary_lengths(
                    chapter_summary_llm_lengths or "short=400,medium=1200,long=2400"
                )
                if not lengths:
                    raise ValueError("chapter_summary_llm_lengths must include at least one length.")
                summary_source = "llm_full_chapter"
                chapter_texts: Dict[str, str] = {}
                for chapter_id, indices in chapter_to_chunk_indices.items():
                    ordered = sorted(indices, key=lambda idx: (chunks[idx].get("page") or 0, idx))
                    parts = []
                    for idx in ordered:
                        chunk = chunks[idx]
                        section_path = chunk.get("section_path") or []
                        text = chunk.get("text") or ""
                        if text:
                            if section_path:
                                header = " > ".join(section_path)
                                parts.append(f"[{header}]\n{text.strip()}")
                            else:
                                parts.append(text.strip())
                    chapter_texts[chapter_id] = "\n\n".join(parts).strip()

                def summarize_chapter(chapter_id: str) -> Tuple[str, Dict[str, str]]:
                    title = (chapter_to_titles.get(chapter_id) or [None])[0]
                    chapter_text = chapter_texts.get(chapter_id, "")
                    variants = summarize_chapter_with_llm(
                        title=title,
                        text=chapter_text,
                        summary_lengths=lengths,
                        model=llm_model,
                        api_key=api_key,
                        temperature=chapter_summary_llm_temperature,
                        max_input_chars=chapter_summary_llm_max_input_chars,
                        segment_max_chars=chapter_summary_llm_segment_max_chars,
                    )
                    return chapter_id, variants

                chapter_ids_sorted = sorted(chapter_to_chunk_indices.keys())
                logger.info(
                    "🚀 [LLM] Starting parallel chapter summarization with 10 threads for %d chapters",
                    len(chapter_ids_sorted),
                )
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = {executor.submit(summarize_chapter, cid): cid for cid in chapter_ids_sorted}
                    for future in as_completed(futures):
                        chapter_id, variants = future.result()
                        chapter_variants[chapter_id] = variants
                        summary_texts[chapter_id] = variants.get(
                            chapter_summary_llm_embed_key, variants.get(lengths[0][0], "")
                        )
                        logger.info("✅ [LLM] Completed chapter: %s", chapter_id)
            else:
                summary_texts = build_chapter_summary_texts(
                    chunks,
                    chapter_to_chunk_indices,
                    chapter_to_titles,
                )

            chapter_payload = {
                "summary_source": summary_source,
                "chapters": [
                    {
                        "chapter_id": chapter_id,
                        "title": (chapter_to_titles.get(chapter_id) or [None])[0],
                        "summary_text": summary_texts.get(chapter_id, ""),
                        "summary_variants": chapter_variants.get(chapter_id),
                        "chunk_ids": [
                            chunk_ids[idx]
                            for idx in chapter_to_chunk_indices.get(chapter_id, [])
                        ],
                    }
                    for chapter_id in sorted(chapter_to_chunk_indices.keys())
                ],
            }
            if not chapter_summary_output:
                raise ValueError("chapter_summary_output is required when chapter_summary_only is enabled.")
            os.makedirs(os.path.dirname(chapter_summary_output), exist_ok=True)
            with open(chapter_summary_output, "w", encoding="utf-8") as handle:
                json.dump(chapter_payload, handle, indent=2)
            print(f"📝 Chapter summaries written: {chapter_summary_output}")
        if not chapter_summary_embed:
            return {"summary_only": True, "chapter_summary_path": chapter_summary_output}
        if not chapter_summary_embedding_output:
            raise ValueError(
                "chapter_summary_embedding_output is required when chapter_summary_embed is enabled."
            )
        chapter_ids = [chapter["chapter_id"] for chapter in chapter_payload["chapters"]]
        chapter_texts = [chapter["summary_text"] for chapter in chapter_payload["chapters"]]
        model = load_model(model_spec.model_name, trust_remote_code=trust_remote_code)
        chapter_embeddings = encode_texts(model, chapter_texts, batch_size=batch_size)
        embedding_payload = {
            "model_id": model_spec.model_id,
            "model_name": model_spec.model_name,
            "summary_source": summary_source,
            "chapters": [
                {
                    "chapter_id": chapter_id,
                    "embedding": chapter_embeddings[idx].astype(float).tolist(),
                }
                for idx, chapter_id in enumerate(chapter_ids)
            ],
        }
        os.makedirs(os.path.dirname(chapter_summary_embedding_output), exist_ok=True)
        with open(chapter_summary_embedding_output, "w", encoding="utf-8") as handle:
            json.dump(embedding_payload, handle, indent=2)
        print(f"🧠 Chapter summary embeddings written: {chapter_summary_embedding_output}")
        save_run_id = chapter_summary_embedding_run_id or embedding_run_id or run_id
        if save_run_id:
            store_ops = _require_store(store, "Saving chapter embeddings")
            client = store_ops.get_mongo_client(mongo_uri)
            store_ops.ensure_benchmark_indexes(client)
            store_ops.save_chapter_embeddings(
                [
                    {
                        "run_id": save_run_id,
                        "model_id": model_spec.model_id,
                        "chapter_id": chapter_id,
                        "embedding": chapter_embeddings[idx].astype(float).tolist(),
                        "created_at": datetime.now(timezone.utc),
                    }
                    for idx, chapter_id in enumerate(chapter_ids)
                ],
                mongo_uri=mongo_uri,
                clear_existing=True,
                run_id=save_run_id,
                model_id=model_spec.model_id,
            )
            print(f"🧩 Chapter summary embeddings saved to Mongo: run_id={save_run_id}")
        return {
            "summary_only": True,
            "chapter_summary_path": chapter_summary_output,
            "chapter_summary_embedding_path": chapter_summary_embedding_output,
        }

    chunk_embeddings, embed_duration_ms, embedding_reused, embedding_reuse_reason, model = resolve_chunk_embeddings(
        chunk_ids=chunk_ids,
        chunk_texts=chunk_texts,
        model_spec=model_spec,
        batch_size=batch_size,
        trust_remote_code=trust_remote_code,
        embedding_cache=embedding_cache,
        chunk_embedding_path=chunk_embedding_path,
        chunk_embedding_output=chunk_embedding_output,
        reuse_embeddings=reuse_embeddings,
        embedding_run_id=embedding_run_id,
        run_id=run_id,
        store=store,
        mongo_uri=mongo_uri,
        clear_existing=clear_existing,
    )
    print(
        "🧠 Chunk embeddings ready: "
        f"count={len(chunk_ids)}, "
        f"reused={embedding_reused}, "
        f"duration_ms={embed_duration_ms}"
    )

    chapter_id_by_index = list(chapter_to_chunk_indices.keys())
    chapter_index_by_id = {chapter_id: idx for idx, chapter_id in enumerate(chapter_id_by_index)}
    chapter_book_ids = {
        chapter_id: resolve_chapter_book_id(chapter_id, default_book_id=detected_book_id)
        for chapter_id in chapter_id_by_index
    }
    chapter_embeddings: Optional[np.ndarray] = None
    if chapter_routing_top_n and chapter_routing_top_n > 0:
        if embedding_cache and embedding_cache.get("chapter_embeddings") is not None:
            chapter_embeddings = embedding_cache["chapter_embeddings"]
            cached_chapter_ids = embedding_cache.get("chapter_id_by_index")
            if cached_chapter_ids:
                chapter_id_by_index = cached_chapter_ids
                chapter_index_by_id = {
                    chapter_id: idx for idx, chapter_id in enumerate(chapter_id_by_index)
                }
        elif chapter_summary_embedding_path:
            chapter_id_by_index, chapter_embeddings = load_chapter_summary_embeddings(
                chapter_summary_embedding_path
            )
            chapter_index_by_id = {
                chapter_id: idx for idx, chapter_id in enumerate(chapter_id_by_index)
            }
        elif chapter_summary_embedding_run_id or run_id:
            lookup_id = chapter_summary_embedding_run_id or run_id
            store_ops = _require_store(store, "Loading chapter embeddings")
            records = store_ops.fetch_chapter_embeddings(lookup_id, model_spec.model_id, mongo_uri)
            chapter_id_by_index, chapter_embeddings = load_chapter_summary_embeddings_from_records(
                records
            )
            chapter_index_by_id = {
                chapter_id: idx for idx, chapter_id in enumerate(chapter_id_by_index)
            }
        elif chapter_embedding_source in {"mean", "weighted"}:
            chapter_vectors = []
            for chapter_id in chapter_id_by_index:
                indices = chapter_to_chunk_indices.get(chapter_id, [])
                if not indices:
                    chapter_vectors.append(np.zeros(chunk_embeddings.shape[1], dtype=np.float32))
                    continue
                vectors = chunk_embeddings[indices]
                if chapter_embedding_source == "weighted":
                    weights = np.array(
                        [max(1, len(chunks[idx].get("text") or "")) for idx in indices],
                        dtype=np.float32,
                    )
                    weights = weights / float(weights.sum())
                    chapter_vectors.append((vectors.T @ weights).astype(np.float32))
                else:
                    chapter_vectors.append(np.mean(vectors, axis=0).astype(np.float32))
            chapter_embeddings = np.vstack(chapter_vectors) if chapter_vectors else None
        else:
            summary_texts = build_chapter_summary_texts(
                chunks,
                chapter_to_chunk_indices,
                chapter_to_titles,
            )
            chapter_text_list = [
                summary_texts.get(chapter_id, "") for chapter_id in chapter_id_by_index
            ]
            chapter_embeddings = encode_texts(model, chapter_text_list, batch_size=batch_size)

    query_texts = [
        query.get("query_text")
        or query.get("query_text_full")
        or query.get("query_text_short")
        or ""
        for query in queries
    ]
    expected_ids = [query.get("expected_chunk_ids", []) for query in queries]
    query_document_ids = [query.get("document_id") or "unknown" for query in queries]
    query_book_ids = [normalize_book_id(doc_id, default_book_id=detected_book_id) for doc_id in query_document_ids]
    query_allowed_book_ids: List[Optional[Set[str]]] = []
    for query, book_id in zip(queries, query_book_ids):
        allowed = query.get("allowed_book_ids") or query.get("allowed_books")
        if isinstance(allowed, list) and allowed:
            query_allowed_book_ids.append(set(str(item) for item in allowed if item))
        elif book_id and book_id != "unknown":
            query_allowed_book_ids.append({book_id})
        else:
            query_allowed_book_ids.append(None)

    query_embeddings, query_embed_duration_ms, model = resolve_query_embeddings(
        query_texts=query_texts,
        model_spec=model_spec,
        batch_size=batch_size,
        trust_remote_code=trust_remote_code,
        embedding_cache=embedding_cache,
        model=model,
    )
    print(
        "🧠 Query embeddings ready: "
        f"count={len(query_texts)}, "
        f"duration_ms={query_embed_duration_ms}"
    )

    ranked_chunk_ids_by_query: Optional[List[List[str]]] = None
    if retrieval_method == "hybrid":
        try:
            from ruleslawyer.hybrid_retriever import HybridRetriever
        except ImportError:
            raise ImportError(
                "retrieval_method='hybrid' requires ruleslawyer (DungeonMindServer). "
                "Run the harness from DungeonMindServer: uv run python -m ruleslawyer.evaluation_harness ..."
            )
        top_k_list_early = sorted(set(int(k) for k in top_k))
        max_k = max(top_k_list_early) if top_k_list_early else 10
        chunks_for_retriever = [
            {"id": c["id"], "content": (c.get("text") or c.get("content") or "")}
            for c in chunks
        ]
        encode_fn: Callable[[str], np.ndarray] = lambda t: encode_texts(
            model, [t], batch_size=1
        )[0]
        retriever = HybridRetriever(
            pages_and_chunks=chunks_for_retriever,
            embeddings=chunk_embeddings,
            encode_fn=encode_fn,
            graph_adjacency=None,
        )
        ranked_chunk_ids_by_query = []
        for i, q in enumerate(query_texts):
            results = retriever.retrieve(q, top_k=max_k)
            ranked_chunk_ids_by_query.append([r["chunk"]["id"] for r in results])
            if (i + 1) % 25 == 0 or i + 1 == len(query_texts):
                print(f"🔀 Hybrid retrieval: {i + 1}/{len(query_texts)} queries")
        print(f"🔀 Hybrid retrieval complete: {len(ranked_chunk_ids_by_query)} queries")

    answer_texts = [
        query.get("hypothetical_answer") or query.get("reference_answer") or ""
        for query in queries
    ]
    answer_embeddings = None
    answer_embed_duration_ms = 0
    if answer_similarity:
        answer_embeddings, answer_embed_duration_ms, model = resolve_answer_embeddings(
            answer_texts=answer_texts,
            model_spec=model_spec,
            batch_size=batch_size,
            trust_remote_code=trust_remote_code,
            model=model,
        )

    graph_boost_source_value = graph_boost_source
    if routing_seeded_boost:
        graph_boost_source_value = "routed"

    adjacency_by_document: Dict[str, Dict[str, Set[str]]] = {}
    if graph_boost or expand_gold:
        for document_id in document_ids:
            adjacency_by_document[document_id] = build_graph_adjacency(
                graph_by_document.get(document_id),
                node_prefix=document_id,
            )

    allowed_chunk_ids_by_query: Optional[List[Optional[Set[str]]]] = None
    toc_allowed_chunk_ids_by_query: Optional[List[Optional[Set[str]]]] = None
    toc_candidate_fraction_avg = None
    toc_scope_missing = None
    chapter_routing_details: Optional[List[List[Dict[str, Any]]]] = None
    chapter_routing_expected_hits = None
    chapter_routing_avg_chunks = None
    chapter_routing_rerank_scores = None
    chapter_routing_rerank_change_rate = None
    chapter_routing_rerank_change_count = None
    chapter_routing_rerank_query_count = None
    routing_chunk_ids_by_query: Optional[List[Optional[Set[str]]]] = None
    traversal_baseline_scores = None
    traversal_baseline_details: Optional[List[Dict[str, Any]]] = None
    traversal_delta = None
    traversal_monotonicity = None
    traversal_reachability = None
    cross_book_reachability = None
    toc_traversal_baseline = None
    toc_traversal_compare = None
    toc_traversal_delta = None
    toc_traversal_monotonicity = None
    routing_result: Optional[ChapterRoutingResult] = None
    if chapter_routing_top_n and chapter_routing_top_n > 0 and chapter_embeddings is not None:
        routing_result = build_chapter_routing(
            query_embeddings=query_embeddings,
            chapter_embeddings=chapter_embeddings,
            chapter_id_by_index=chapter_id_by_index,
            chapter_index_by_id=chapter_index_by_id,
            chapter_to_chunk_indices=chapter_to_chunk_indices,
            chunk_ids=chunk_ids,
            chunk_embeddings=chunk_embeddings if chapter_routing_rerank else None,
            query_document_ids=query_document_ids,
            query_book_ids=query_book_ids,
            query_allowed_book_ids=query_allowed_book_ids,
            chapter_book_ids=chapter_book_ids,
            expected_ids=expected_ids,
            adjacency_by_document=adjacency_by_document if graph_boost else None,
            chunk_kind_by_id=chunk_kind_by_id,
            graph_boost=graph_boost,
            graph_boost_depth=graph_boost_depth,
            graph_boost_top_k=graph_boost_top_k,
            graph_boost_seed_top_n=graph_boost_seed_top_n,
            graph_boost_same_kind_only=graph_boost_same_kind_only,
            graph_boost_decay=graph_boost_decay,
            top_n=int(chapter_routing_top_n),
            rerank=chapter_routing_rerank,
            rerank_pool=chapter_routing_rerank_pool,
            report_details=chapter_routing_report,
        )
        allowed_chunk_ids_by_query = routing_result.allowed_chunk_ids_by_query
        chapter_routing_details = routing_result.chapter_routing_details
        chapter_routing_avg_chunks = routing_result.avg_allowed_chunks
        chapter_routing_rerank_scores = routing_result.rerank_scores_by_query
        expected_hits = 0
        for expected, allowed_chunks in zip(expected_ids, allowed_chunk_ids_by_query):
            if set(expected) & allowed_chunks:
                expected_hits += 1
        chapter_routing_expected_hits = expected_hits

        if chapter_routing_rerank and chunk_embeddings is not None:
            non_rerank_result = build_chapter_routing(
                query_embeddings=query_embeddings,
                chapter_embeddings=chapter_embeddings,
                chapter_id_by_index=chapter_id_by_index,
                chapter_index_by_id=chapter_index_by_id,
                chapter_to_chunk_indices=chapter_to_chunk_indices,
                chunk_ids=chunk_ids,
                chunk_embeddings=None,
                query_document_ids=query_document_ids,
                query_book_ids=query_book_ids,
                query_allowed_book_ids=query_allowed_book_ids,
                chapter_book_ids=chapter_book_ids,
                expected_ids=expected_ids,
                adjacency_by_document=adjacency_by_document if graph_boost else None,
                chunk_kind_by_id=chunk_kind_by_id,
                graph_boost=graph_boost,
                graph_boost_depth=graph_boost_depth,
                graph_boost_top_k=graph_boost_top_k,
                graph_boost_seed_top_n=graph_boost_seed_top_n,
                graph_boost_same_kind_only=graph_boost_same_kind_only,
                graph_boost_decay=graph_boost_decay,
                top_n=int(chapter_routing_top_n),
                rerank=False,
                rerank_pool=chapter_routing_rerank_pool,
                report_details=False,
            )
            rerank_change_count = 0
            rerank_query_count = len(non_rerank_result.final_chapters_by_query)
            for base, reranked in zip(
                non_rerank_result.final_chapters_by_query,
                routing_result.final_chapters_by_query,
            ):
                if base != reranked:
                    rerank_change_count += 1
            chapter_routing_rerank_query_count = rerank_query_count
            chapter_routing_rerank_change_count = rerank_change_count
            chapter_routing_rerank_change_rate = (
                rerank_change_count / rerank_query_count if rerank_query_count else 0.0
            )

    routing_prior_enabled = bool(routing_prior_boost > 0 or routing_seeded_boost)
    if routing_prior_enabled and routing_result is not None:
        routing_chunk_ids_by_query = []
        for chapters in routing_result.final_chapters_by_query:
            if not chapters:
                routing_chunk_ids_by_query.append(None)
                continue
            chunk_set: Set[str] = set()
            for chapter_id in chapters:
                for idx in chapter_to_chunk_indices.get(chapter_id, []):
                    chunk_set.add(chunk_ids[idx])
            routing_chunk_ids_by_query.append(chunk_set if chunk_set else None)

    score_allowed_chunk_ids = allowed_chunk_ids_by_query
    if routing_prior_enabled:
        score_allowed_chunk_ids = None

    top_k_list = sorted(set(int(k) for k in top_k))

    if toc_traversal_eval:
        section_index_by_document: Dict[str, Dict[Tuple[str, ...], List[str]]] = {}
        doc_chunk_ids: Dict[str, Set[str]] = {}
        chunk_by_id = {chunk["id"]: chunk for chunk in chunks}

        for document_id in document_ids:
            doc_chunks = [c for c in chunks if c.get("document_id") == document_id]
            doc_chunk_ids[document_id] = {c["id"] for c in doc_chunks}
            section_index: Dict[Tuple[str, ...], List[str]] = {}
            for chunk in doc_chunks:
                section_path = chunk.get("section_path") or []
                if not section_path:
                    continue
                if toc_scope_depth and toc_scope_depth > 0:
                    section_path = section_path[: toc_scope_depth]
                section_index.setdefault(tuple(section_path), []).append(chunk["id"])
            section_index_by_document[document_id] = section_index

        toc_allowed_chunk_ids_by_query = []
        toc_candidate_fractions: List[float] = []
        toc_scope_missing = 0
        for idx, (query, expected) in enumerate(zip(queries, expected_ids), start=1):
            expected_id = expected[0] if expected else None
            expected_chunk = chunk_by_id.get(expected_id) if expected_id else None
            document_id = (
                query.get("document_id")
                or (expected_chunk.get("document_id") if expected_chunk else None)
                or "unknown"
            )
            allowed = None
            if expected_chunk:
                section_path = expected_chunk.get("section_path") or []
                if section_path:
                    if toc_scope_depth and toc_scope_depth > 0:
                        section_path = section_path[: toc_scope_depth]
                    allowed = set(
                        section_index_by_document.get(document_id, {}).get(
                            tuple(section_path), []
                        )
                    )
            if not allowed:
                allowed = set(doc_chunk_ids.get(document_id, set()))
                toc_scope_missing += 1
            toc_allowed_chunk_ids_by_query.append(allowed if allowed else None)
            if allowed:
                toc_candidate_fractions.append(
                    len(allowed) / max(len(doc_chunk_ids.get(document_id, [])), 1)
                )
            if idx % 200 == 0 or idx == len(queries):
                print(
                    "🧭 TOC traversal progress: "
                    f"{idx}/{len(queries)} queries "
                    f"(missing_scope={toc_scope_missing})"
                )
        toc_candidate_fraction_avg = (
            float(sum(toc_candidate_fractions) / len(toc_candidate_fractions))
            if toc_candidate_fractions
            else None
        )

        if toc_allowed_chunk_ids_by_query:
            (
                toc_traversal_baseline,
                _toc_baseline_details,
                toc_traversal_compare,
                _toc_compare_details,
                toc_traversal_delta,
                toc_traversal_monotonicity,
            ) = score_traversal_runs(
                query_embeddings=query_embeddings,
                chunk_embeddings=chunk_embeddings,
                expected_ids=expected_ids,
                chunk_ids=chunk_ids,
                top_k_list=top_k_list,
                adjacency_by_document=adjacency_by_document if graph_boost else None,
                query_document_ids=query_document_ids,
                query_book_ids=query_book_ids,
                query_allowed_book_ids=query_allowed_book_ids,
                chunk_document_ids=chunk_document_ids,
                chunk_book_ids=chunk_book_ids,
                chunk_kind_by_id=chunk_kind_by_id,
                allowed_chunk_ids_by_query=toc_allowed_chunk_ids_by_query,
                graph_boost=graph_boost,
                graph_boost_depth=graph_boost_depth,
                graph_boost_top_k=graph_boost_top_k,
                graph_boost_source=graph_boost_source,
                graph_boost_seed_top_n=graph_boost_seed_top_n,
                graph_boost_same_kind_only=graph_boost_same_kind_only,
                graph_boost_decay=graph_boost_decay,
            )
            allowed_chunk_ids_by_query = toc_allowed_chunk_ids_by_query

    if traversal_eval:
        if not (chapter_routing_top_n and chapter_routing_top_n > 0 and chapter_embeddings is not None):
            raise ValueError("traversal_eval requires chapter_routing_top_n and chapter embeddings.")
        if routing_result is None:
            raise ValueError("traversal_eval requires routing_result to be set.")
        traversal_compare_allowed = allowed_chunk_ids_by_query
        traversal_compare_details = chapter_routing_details
        pool_chapters_for_reach = routing_result.pool_chapters_by_query
        final_chapters_for_reach = routing_result.final_chapters_by_query
        if chapter_routing_rerank:
            rerank_result = build_chapter_routing(
                query_embeddings=query_embeddings,
                chapter_embeddings=chapter_embeddings,
                chapter_id_by_index=chapter_id_by_index,
                chapter_index_by_id=chapter_index_by_id,
                chapter_to_chunk_indices=chapter_to_chunk_indices,
                chunk_ids=chunk_ids,
                chunk_embeddings=chunk_embeddings,
                query_document_ids=query_document_ids,
                query_book_ids=query_book_ids,
                query_allowed_book_ids=query_allowed_book_ids,
                chapter_book_ids=chapter_book_ids,
                expected_ids=expected_ids,
                adjacency_by_document=adjacency_by_document if graph_boost else None,
                chunk_kind_by_id=chunk_kind_by_id,
                graph_boost=graph_boost,
                graph_boost_depth=graph_boost_depth,
                graph_boost_top_k=graph_boost_top_k,
                graph_boost_seed_top_n=graph_boost_seed_top_n,
                graph_boost_same_kind_only=graph_boost_same_kind_only,
                graph_boost_decay=graph_boost_decay,
                top_n=int(chapter_routing_top_n),
                rerank=True,
                rerank_pool=chapter_routing_rerank_pool,
                report_details=chapter_routing_report,
            )
            traversal_compare_allowed = rerank_result.allowed_chunk_ids_by_query
            traversal_compare_details = rerank_result.chapter_routing_details
            pool_chapters_for_reach = rerank_result.pool_chapters_by_query
            final_chapters_for_reach = rerank_result.final_chapters_by_query

        (
            traversal_baseline_scores,
            traversal_baseline_details,
            traversal_compare_scores,
            traversal_compare_details_scored,
            traversal_delta,
            traversal_monotonicity,
        ) = score_traversal_runs(
            query_embeddings=query_embeddings,
            chunk_embeddings=chunk_embeddings,
            expected_ids=expected_ids,
            chunk_ids=chunk_ids,
            top_k_list=top_k_list,
            adjacency_by_document=adjacency_by_document if graph_boost else None,
            query_document_ids=query_document_ids,
            query_book_ids=query_book_ids,
            query_allowed_book_ids=query_allowed_book_ids,
            chunk_document_ids=chunk_document_ids,
            chunk_book_ids=chunk_book_ids,
            chunk_kind_by_id=chunk_kind_by_id,
            allowed_chunk_ids_by_query=traversal_compare_allowed,
            graph_boost=graph_boost,
            graph_boost_depth=graph_boost_depth,
            graph_boost_top_k=graph_boost_top_k,
            graph_boost_source=graph_boost_source,
            graph_boost_seed_top_n=graph_boost_seed_top_n,
            graph_boost_same_kind_only=graph_boost_same_kind_only,
            graph_boost_decay=graph_boost_decay,
        )
        traversal_reachability = compute_reachability_monotonicity(
            expected_ids=expected_ids,
            chunk_to_chapter=chunk_to_chapter,
            pool_chapters_by_query=pool_chapters_for_reach,
            final_chapters_by_query=final_chapters_for_reach,
        )
        cross_book_reachability = compute_cross_book_reachability(
            expected_ids=expected_ids,
            chunk_to_chapter=chunk_to_chapter,
            chunk_book_ids=chunk_book_ids,
            query_book_ids=query_book_ids,
            query_allowed_book_ids=query_allowed_book_ids,
            pool_chapters_by_query=pool_chapters_for_reach,
            final_chapters_by_query=final_chapters_for_reach,
        )

    expanded_scores = None
    expanded_query_details: List[Dict[str, Any]] = []
    expanded_expected_ids: List[List[str]] = expected_ids
    expanded_added_counts: List[int] = []
    expanded_added_details: List[List[Dict[str, Any]]] = []
    expanded_reason_counts: Dict[str, int] = {}
    if expand_gold:
        # NOTE: Expanded gold relaxes correctness. Keep for diagnostics only.
        # Consider removing, or restrict expansion to deterministic/traversable edges.
        chunk_id_set = set(chunk_ids)
        chunk_by_id = {chunk["id"]: chunk for chunk in chunks}
        section_index_by_document: Dict[str, Dict[Tuple[str, ...], List[str]]] = {}

        for document_id in document_ids:
            doc_chunks = [c for c in chunks if c.get("document_id") == document_id]
            section_index_by_document[document_id] = build_section_index(doc_chunks)

        expanded_expected_ids = []
        for query, expected in zip(queries, expected_ids):
            document_id = query.get("document_id") or "unknown"
            expanded, reason_map = expand_expected_ids(
                expected,
                chunk_id_set,
                chunk_by_id,
                adjacency_by_document.get(document_id, {}),
                section_index_by_document.get(document_id, {}),
                next_depth=gold_next_depth,
                include_section=gold_include_section,
                same_kind_only=gold_same_kind_only,
                max_total=gold_max_total,
            )
            expanded_expected_ids.append(expanded)
            added_details = []
            for chunk_id in expanded:
                if chunk_id in expected:
                    continue
                reasons = reason_map.get(chunk_id, [])
                for reason in reasons:
                    expanded_reason_counts[reason] = expanded_reason_counts.get(reason, 0) + 1
                added_details.append({"chunk_id": chunk_id, "reasons": reasons})
            expanded_added_details.append(added_details)
            expanded_added_counts.append(max(0, len(expanded) - len(expected)))

    eval_estimate_strict_ms = estimate_scoring_time_ms(
        query_embeddings,
        chunk_embeddings,
        expected_ids,
        chunk_ids,
        top_k,
        adjacency_by_document=adjacency_by_document if graph_boost else None,
        query_document_ids=query_document_ids,
        query_book_ids=query_book_ids,
        query_allowed_book_ids=query_allowed_book_ids,
        chunk_document_ids=chunk_document_ids,
        chunk_book_ids=chunk_book_ids,
        chunk_kind_by_id=chunk_kind_by_id,
        allowed_chunk_ids_by_query=score_allowed_chunk_ids,
        graph_boost=graph_boost,
        graph_boost_depth=graph_boost_depth,
        graph_boost_top_k=graph_boost_top_k,
        graph_boost_source=graph_boost_source_value,
        graph_boost_seed_top_n=graph_boost_seed_top_n,
        graph_boost_same_kind_only=graph_boost_same_kind_only,
        graph_boost_decay=graph_boost_decay,
        routing_boost=routing_prior_boost,
        routing_boost_by_query=routing_chunk_ids_by_query,
        routing_boost_pool_multiplier=routing_prior_pool_multiplier,
        routing_chapters_by_query=routing_result.final_chapters_by_query
        if routing_result
        else None,
        chunk_to_chapter=chunk_to_chapter,
    )
    eval_estimate_expanded_ms = None
    if expand_gold:
        eval_estimate_expanded_ms = estimate_scoring_time_ms(
            query_embeddings,
            chunk_embeddings,
            expanded_expected_ids,
            chunk_ids,
            top_k,
            adjacency_by_document=adjacency_by_document if graph_boost else None,
            query_document_ids=query_document_ids,
            query_book_ids=query_book_ids,
            query_allowed_book_ids=query_allowed_book_ids,
            chunk_document_ids=chunk_document_ids,
            chunk_book_ids=chunk_book_ids,
            chunk_kind_by_id=chunk_kind_by_id,
            allowed_chunk_ids_by_query=score_allowed_chunk_ids,
            graph_boost=graph_boost,
            graph_boost_depth=graph_boost_depth,
            graph_boost_top_k=graph_boost_top_k,
            graph_boost_source=graph_boost_source_value,
            graph_boost_seed_top_n=graph_boost_seed_top_n,
            graph_boost_same_kind_only=graph_boost_same_kind_only,
            graph_boost_decay=graph_boost_decay,
            routing_boost=routing_prior_boost,
            routing_boost_by_query=routing_chunk_ids_by_query,
            routing_boost_pool_multiplier=routing_prior_pool_multiplier,
            routing_chapters_by_query=routing_result.final_chapters_by_query
            if routing_result
            else None,
            chunk_to_chapter=chunk_to_chapter,
        )
    if eval_estimate_strict_ms is not None:
        estimate_total = (
            embed_duration_ms
            + query_embed_duration_ms
            + eval_estimate_strict_ms
            + (eval_estimate_expanded_ms or 0)
        )
        print(
            "⏱️ Estimated timings (ms): "
            f"strict={eval_estimate_strict_ms}, "
            f"expanded={eval_estimate_expanded_ms}, "
            f"total={estimate_total}"
        )

    eval_start = time.time()
    print(
        "🔎 Scoring queries: "
        f"queries={len(queries)}, chunks={len(chunks)}, top_k={top_k_list}"
    )
    scores, query_details = score_queries(
        query_embeddings,
        chunk_embeddings,
        expected_ids,
        chunk_ids,
        top_k_list,
        answer_embeddings=answer_embeddings,
        answer_texts=answer_texts,
        adjacency_by_document=adjacency_by_document if graph_boost else None,
        query_document_ids=query_document_ids,
        query_book_ids=query_book_ids,
        query_allowed_book_ids=query_allowed_book_ids,
        chunk_document_ids=chunk_document_ids,
        chunk_book_ids=chunk_book_ids,
        chunk_kind_by_id=chunk_kind_by_id,
        allowed_chunk_ids_by_query=score_allowed_chunk_ids,
        graph_boost=graph_boost,
        graph_boost_depth=graph_boost_depth,
        graph_boost_top_k=graph_boost_top_k,
        graph_boost_source=graph_boost_source_value,
        graph_boost_seed_top_n=graph_boost_seed_top_n,
        graph_boost_same_kind_only=graph_boost_same_kind_only,
        graph_boost_decay=graph_boost_decay,
        routing_boost=routing_prior_boost,
        routing_boost_by_query=routing_chunk_ids_by_query,
        routing_boost_pool_multiplier=routing_prior_pool_multiplier,
        routing_chapters_by_query=routing_result.final_chapters_by_query
        if routing_result
        else None,
        chunk_to_chapter=chunk_to_chapter,
        ranked_chunk_ids_by_query=ranked_chunk_ids_by_query,
    )
    eval_duration_ms = int((time.time() - eval_start) * 1000)
    print(f"✅ Scoring complete: duration_ms={eval_duration_ms}")
    expanded_eval_duration_ms = 0
    if expand_gold:
        expanded_eval_start = time.time()
        expanded_scores, expanded_query_details = score_queries(
            query_embeddings,
            chunk_embeddings,
            expanded_expected_ids,
            chunk_ids,
            top_k,
            adjacency_by_document=adjacency_by_document if graph_boost else None,
            query_document_ids=query_document_ids,
            query_book_ids=query_book_ids,
            query_allowed_book_ids=query_allowed_book_ids,
            chunk_document_ids=chunk_document_ids,
            chunk_book_ids=chunk_book_ids,
            chunk_kind_by_id=chunk_kind_by_id,
            allowed_chunk_ids_by_query=score_allowed_chunk_ids,
            graph_boost=graph_boost,
            graph_boost_depth=graph_boost_depth,
            graph_boost_top_k=graph_boost_top_k,
            graph_boost_source=graph_boost_source_value,
            graph_boost_seed_top_n=graph_boost_seed_top_n,
            graph_boost_same_kind_only=graph_boost_same_kind_only,
            graph_boost_decay=graph_boost_decay,
            routing_boost=routing_prior_boost,
            routing_boost_by_query=routing_chunk_ids_by_query,
            routing_boost_pool_multiplier=routing_prior_pool_multiplier,
            routing_chapters_by_query=routing_result.final_chapters_by_query
            if routing_result
            else None,
            chunk_to_chapter=chunk_to_chapter,
            ranked_chunk_ids_by_query=ranked_chunk_ids_by_query,
        )
        expanded_eval_duration_ms = int((time.time() - expanded_eval_start) * 1000)

    total_duration_ms = int((time.time() - total_start) * 1000)

    save_run_id = run_id or embedding_run_id
    embedding_run_record = {
        "run_id": save_run_id,
        "ruleset_id": ruleset_id,
        "document_id": document_ids[0] if len(set(document_ids)) == 1 else None,
        "model_id": model_spec.model_id,
        "model_name": model_spec.model_name,
        "chunk_source": chunk_source,
        "chunk_count": len(chunks),
        "embedding_dim": int(chunk_embeddings.shape[1]) if chunk_embeddings.ndim == 2 else None,
        "duration_ms": embed_duration_ms,
        "created_at": datetime.now(timezone.utc),
    }

    chunk_records = [
        {
            "run_id": save_run_id,
            "model_id": model_spec.model_id,
            "chunk_id": chunk["id"],
            "text": chunk["text"],
            "page": chunk["page"],
            "section_path": chunk["section_path"],
            "content_kind": chunk["content_kind"],
            "embedding": chunk_embeddings[idx].astype(float).tolist(),
            "created_at": datetime.now(timezone.utc),
        }
        for idx, chunk in enumerate(chunks)
    ]

    evaluation_record = {
        "run_id": save_run_id,
        "ruleset_id": ruleset_id,
        "document_id": document_ids[0] if len(set(document_ids)) == 1 else None,
        "model_id": model_spec.model_id,
        "model_name": model_spec.model_name,
        "chunk_source": chunk_source,
        "top_k": sorted(set(int(k) for k in top_k)),
        "timings_ms": {
            "embedding": embed_duration_ms,
            "query_embedding": query_embed_duration_ms,
            "evaluation_strict": eval_duration_ms,
            "evaluation_expanded": expanded_eval_duration_ms,
            "total": total_duration_ms,
        },
        "embedding_reused": embedding_reused,
        "embedding_reuse_reason": embedding_reuse_reason,
        "metrics": scores,
        "metrics_expanded": expanded_scores,
        "gold_expansion": {
            "enabled": expand_gold,
            "next_depth": gold_next_depth,
            "include_section": gold_include_section,
            "same_kind_only": gold_same_kind_only,
            "max_total": gold_max_total,
        },
        "created_at": datetime.now(timezone.utc),
    }

    saved_count = 0
    if save_run_id and store:
        store_ops = _require_store(store, "Saving evaluation results")
        client = store_ops.get_mongo_client(mongo_uri)
        store_ops.ensure_benchmark_indexes(client)
        if not embedding_reused:
            store_ops.save_embedding_run(embedding_run_record, mongo_uri)
            saved_count = store_ops.save_chunk_embeddings(
                chunk_records,
                mongo_uri=mongo_uri,
                clear_existing=clear_existing,
                run_id=save_run_id,
                model_id=model_spec.model_id,
            )
            store_ops.save_evaluation_run(evaluation_record, mongo_uri)
        else:
            store_ops.save_evaluation_run(evaluation_record, mongo_uri)

    chunk_text_by_id = {chunk["id"]: chunk["text"] for chunk in chunks}
    gold_delta = None
    expanded_matches_strict = None
    expanded_stats = None
    if expand_gold and expanded_scores:
        gold_delta = {
            "coverage": float(expanded_scores.get("coverage", 0.0) - scores.get("coverage", 0.0)),
            "mrr": float(expanded_scores.get("mrr", 0.0) - scores.get("mrr", 0.0)),
            "hit_rates": {
                key: float(expanded_scores.get("hit_rates", {}).get(key, 0.0) - scores.get("hit_rates", {}).get(key, 0.0))
                for key in scores.get("hit_rates", {}).keys()
            },
        }
        expanded_matches_strict = (
            gold_delta["coverage"] == 0.0
            and gold_delta["mrr"] == 0.0
            and all(delta == 0.0 for delta in gold_delta["hit_rates"].values())
        )
        if expanded_added_counts:
            expanded_stats = {
                "queries_with_additions": sum(1 for count in expanded_added_counts if count > 0),
                "avg_added_per_query": float(sum(expanded_added_counts) / len(expanded_added_counts)),
                "max_added": max(expanded_added_counts),
                "addition_reasons": expanded_reason_counts,
            }

    report = {
        "summary": {
            "run_id": save_run_id,
            "queries_path": queries_path,
            "queries_dir": queries_dir,
            "ruleset_id": ruleset_id,
            "document_ids": sorted(set(document_ids)),
            "model_id": model_spec.model_id,
            "model_name": model_spec.model_name,
            "chunk_source": chunk_source,
            "chunk_count": len(chunks),
            "query_count": scores.get("query_count", 0),
            "evaluated_queries": scores.get("evaluated_queries", 0),
            # NOTE: "coverage" is deprecated terminology; prefer "evaluability"
            # Evaluability = fraction of queries where expected chunk exists in corpus
            # hit@k = fraction of evaluated queries where gold appears in top-k
            "evaluability": scores.get("evaluability", scores.get("coverage", 0.0)),
            "coverage": scores.get("coverage", 0.0),  # Backward compatibility
            "mrr": scores.get("mrr", 0.0),
            "hit_rates": scores.get("hit_rates", {}),
            "answer_similarity": scores.get("answer_similarity"),
            "cross_book_contamination": scores.get("cross_book_contamination"),
            "embedding_reused": embedding_reused,
            "embedding_reuse_reason": embedding_reuse_reason,
            "coverage_expanded": (expanded_scores or {}).get("coverage", 0.0) if expand_gold else None,
            "mrr_expanded": (expanded_scores or {}).get("mrr", 0.0) if expand_gold else None,
            "hit_rates_expanded": (expanded_scores or {}).get("hit_rates") if expand_gold else None,
            "gold_delta": gold_delta,
            "expanded_matches_strict": expanded_matches_strict,
            "expanded_stats": expanded_stats,
            "gold_expansion": {
                "enabled": expand_gold,
                "next_depth": gold_next_depth,
                "include_section": gold_include_section,
                "same_kind_only": gold_same_kind_only,
                "max_total": gold_max_total,
            },
            "graph_boost": {
                "enabled": graph_boost > 0,
                "value": graph_boost,
                "depth": graph_boost_depth,
                "top_k": graph_boost_top_k,
                "source": graph_boost_source_value,
                "seed_top_n": graph_boost_seed_top_n,
                "same_kind_only": graph_boost_same_kind_only,
                "decay": graph_boost_decay,
            },
            "routing_prior": {
                "enabled": routing_prior_enabled,
                "prior_boost": routing_prior_boost,
                "prior_pool_multiplier": routing_prior_pool_multiplier,
                "seeded_boost": routing_seeded_boost,
                "seeded_boost_source": graph_boost_source_value if routing_seeded_boost else None,
            },
            "chapter_routing": {
                "enabled": bool(chapter_routing_top_n and chapter_routing_top_n > 0),
                "top_n": chapter_routing_top_n,
                "embedding_source": chapter_embedding_source,
                "chapter_count": len(chapter_id_by_index),
                "avg_allowed_chunks": chapter_routing_avg_chunks,
                "rerank_enabled": bool(chapter_routing_rerank),
                "rerank_source": (
                    "chunk_graph"
                    if chapter_routing_rerank and graph_boost > 0
                    else "chunk_max"
                    if chapter_routing_rerank
                    else "none"
                ),
                "rerank_changed_queries": chapter_routing_rerank_change_count,
                "rerank_total_queries": chapter_routing_rerank_query_count,
                "rerank_change_rate": chapter_routing_rerank_change_rate,
                "expected_recall": (
                    float(chapter_routing_expected_hits / len(queries))
                    if chapter_routing_expected_hits is not None and queries
                    else None
                ),
            },
            "traversal_eval": {
                "enabled": traversal_eval,
                "baseline": traversal_baseline_scores if traversal_eval else None,
                "delta": traversal_delta,
                "rank_monotonicity": traversal_monotonicity,
                "reachability": traversal_reachability,
                "cross_book_reachability": cross_book_reachability,
            },
            "toc_traversal_eval": {
                "enabled": toc_traversal_eval,
                "scope_depth": toc_scope_depth,
                "avg_candidate_fraction": toc_candidate_fraction_avg,
                "missing_scope_count": toc_scope_missing,
                "baseline": toc_traversal_baseline,
                "compare": toc_traversal_compare,
                "delta": toc_traversal_delta,
                "rank_monotonicity": toc_traversal_monotonicity,
            },
            "timings_ms": {
                "embedding": embed_duration_ms,
                "query_embedding": query_embed_duration_ms,
                "answer_embedding": answer_embed_duration_ms,
                "evaluation_strict": eval_duration_ms,
                "evaluation_expanded": expanded_eval_duration_ms,
                "total": total_duration_ms,
            },
            "timings_estimate_ms": {
                "evaluation_strict": eval_estimate_strict_ms,
                "evaluation_expanded": eval_estimate_expanded_ms,
                "total": (
                    embed_duration_ms
                    + query_embed_duration_ms
                    + (eval_estimate_strict_ms or 0)
                    + (eval_estimate_expanded_ms or 0)
                )
                if eval_estimate_strict_ms is not None
                else None,
            },
        },
        "queries": [
            {
                **detail,
                "query_text": query_texts[detail["query_index"]],
                "document_id": queries[detail["query_index"]].get("document_id"),
                "chapter_routing_top_chapters": (
                    chapter_routing_details[detail["query_index"]]
                    if chapter_routing_report and chapter_routing_details
                    else None
                ),
                "expanded_expected_chunk_ids": expanded_expected_ids[detail["query_index"]]
                if expand_gold
                else None,
                "expanded_added_chunks": expanded_added_details[detail["query_index"]]
                if expand_gold
                else None,
                "expanded_expected_found": next(
                    (
                        item.get("expected_found")
                        for item in expanded_query_details
                        if item.get("query_index") == detail["query_index"]
                    ),
                    None,
                )
                if expand_gold
                else None,
                "expanded_expected_rank": next(
                    (
                        item.get("expected_rank")
                        for item in expanded_query_details
                        if item.get("query_index") == detail["query_index"]
                    ),
                    None,
                )
                if expand_gold
                else None,
                "baseline_expected_rank": (
                    traversal_baseline_details[detail["query_index"]].get("expected_rank")
                    if traversal_baseline_details
                    else None
                ),
                "baseline_expected_found": (
                    traversal_baseline_details[detail["query_index"]].get("expected_found")
                    if traversal_baseline_details
                    else None
                ),
                "top_results": [
                    {
                        **result,
                        "preview": (chunk_text_by_id.get(result["chunk_id"], "")[:200]),
                    }
                    for result in detail.get("top_results", [])
                ],
            }
            for detail in query_details
        ],
    }
    if traversal_eval and traversal_baseline_scores and chapter_routing_top_n:
        report["summary"]["baseline_mode"] = "traversal"
        report["summary"]["routing_scores"] = scores
        report["summary"]["coverage"] = traversal_baseline_scores.get("coverage", 0.0)
        report["summary"]["mrr"] = traversal_baseline_scores.get("mrr", 0.0)
        report["summary"]["hit_rates"] = traversal_baseline_scores.get("hit_rates", {})
    if baseline_report_path:
        baseline_payload = load_json(baseline_report_path)
        baseline_summary = baseline_payload.get("summary") or {}
        report["summary"]["baseline_report"] = baseline_report_path
        report["summary"]["baseline_delta"] = compute_baseline_delta(
            baseline_summary, report["summary"]
        )

    result = {
        "embedding_run": embedding_run_record,
        "chunks_saved": saved_count,
        "evaluation": evaluation_record,
        "report": report,
    }
    if return_embeddings:
        result["embedding_cache"] = {
            "chunk_embeddings": chunk_embeddings,
            "query_embeddings": query_embeddings,
            "chapter_embeddings": chapter_embeddings,
            "chapter_id_by_index": chapter_id_by_index,
        }
    return result

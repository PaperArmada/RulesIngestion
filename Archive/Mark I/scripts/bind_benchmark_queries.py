from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np

from evaluation.model_registry import MODEL_REGISTRY, encode_texts, load_model


@dataclass
class ChunkRecord:
    chunk_id: str
    text: str
    section_path: List[str]
    content_kind: Optional[str]
    document_id: str
    page: Optional[int]


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_chunk(chunk: Dict[str, Any], document_id: str, prefix_doc_id: bool) -> ChunkRecord:
    text = chunk.get("text") or chunk.get("content") or ""
    chunk_id = chunk.get("id")
    if not chunk_id:
        raise ValueError("Chunk is missing id.")
    if prefix_doc_id:
        chunk_id = f"{document_id}::{chunk_id}"
    return ChunkRecord(
        chunk_id=chunk_id,
        text=text,
        section_path=list(chunk.get("section_path") or []),
        content_kind=chunk.get("content_kind"),
        document_id=document_id,
        page=chunk.get("page"),
    )


def load_chunks(paths: Sequence[str], prefix_doc_id: bool) -> List[ChunkRecord]:
    records: List[ChunkRecord] = []
    for path in paths:
        payload = load_json(path)
        document_id = payload.get("document") or os.path.splitext(os.path.basename(path))[0]
        chunks = payload.get("chunks") or []
        if not chunks:
            raise ValueError(f"No chunks found in {path}")
        for chunk in chunks:
            records.append(normalize_chunk(chunk, document_id, prefix_doc_id))
    return records


def extract_keywords(text: str) -> Set[str]:
    stop_words = {
        "the",
        "and",
        "or",
        "for",
        "with",
        "from",
        "that",
        "this",
        "what",
        "when",
        "how",
        "does",
        "are",
        "is",
        "in",
        "of",
        "to",
        "a",
        "an",
        "on",
        "if",
        "be",
    }
    tokens = []
    for raw in text.lower().replace("'", " ").replace('"', " ").split():
        cleaned = "".join(ch for ch in raw if ch.isalnum())
        if len(cleaned) < 4:
            continue
        if cleaned in stop_words:
            continue
        tokens.append(cleaned)
    return set(tokens)


def rank_candidates(
    chunk_embeddings: np.ndarray,
    query_embedding: np.ndarray,
    chunk_ids: List[str],
    top_k: int,
) -> List[Tuple[str, float]]:
    scores = chunk_embeddings @ query_embedding
    ranked_indices = np.argsort(scores)[::-1]
    results: List[Tuple[str, float]] = []
    for idx in ranked_indices[:top_k]:
        chunk_id = chunk_ids[int(idx)]
        results.append((chunk_id, float(scores[int(idx)])))
    return results


def build_candidate_set(
    query_text: str,
    reference_answer: str,
    chunks: List[ChunkRecord],
    chunk_embeddings: np.ndarray,
    chunk_ids: List[str],
    model,
    top_k: int,
) -> Dict[str, Dict[str, Any]]:
    candidates: Dict[str, Dict[str, Any]] = {}
    query_embedding = encode_texts(model, [query_text], batch_size=1)[0]
    query_ranked = rank_candidates(chunk_embeddings, query_embedding, chunk_ids, top_k)
    for chunk_id, score in query_ranked:
        candidates.setdefault(chunk_id, {"reasons": set(), "score": score})
        candidates[chunk_id]["reasons"].add("query_embedding")
        candidates[chunk_id]["score"] = max(candidates[chunk_id]["score"], score)
    if reference_answer:
        answer_embedding = encode_texts(model, [reference_answer], batch_size=1)[0]
        answer_ranked = rank_candidates(chunk_embeddings, answer_embedding, chunk_ids, top_k)
        for chunk_id, score in answer_ranked:
            candidates.setdefault(chunk_id, {"reasons": set(), "score": score})
            candidates[chunk_id]["reasons"].add("answer_embedding")
            candidates[chunk_id]["score"] = max(candidates[chunk_id]["score"], score)

    query_keywords = extract_keywords(query_text)
    if query_keywords:
        for record in chunks:
            if not record.section_path:
                continue
            section_blob = " ".join(record.section_path).lower()
            if any(keyword in section_blob for keyword in query_keywords):
                candidates.setdefault(record.chunk_id, {"reasons": set(), "score": 0.0})
                candidates[record.chunk_id]["reasons"].add("section_keyword")

    return candidates


def build_llm_prompt(
    query_text: str,
    reference_answer: str,
    candidates: List[Dict[str, Any]],
    max_chunk_chars: int,
) -> str:
    chunk_payload = []
    for candidate in candidates:
        text = candidate["text"]
        if len(text) > max_chunk_chars:
            text = f"{text[:max_chunk_chars]}... [TRUNCATED]"
        chunk_payload.append(
            {
                "chunk_id": candidate["chunk_id"],
                "section_path": candidate["section_path"],
                "text": text,
            }
        )
    return (
        "You are binding benchmark questions to rulebook chunks.\n"
        "Use ONLY the candidate chunks below. Select chunk IDs that directly support the "
        "reference answer. Provide citations as exact substrings from the chunk text.\n"
        "If the reference answer cannot be fully supported from the candidates, mark "
        "unanswerable = true and return an empty selected_chunk_ids list.\n\n"
        "Return JSON with:\n"
        "- selected_chunk_ids: list of chunk IDs\n"
        "- citations: list of {chunk_id, quotes}\n"
        "- unanswerable: boolean\n"
        "- notes: string (optional)\n\n"
        f"Query:\n{query_text}\n\n"
        f"Reference answer:\n{reference_answer}\n\n"
        f"Candidate chunks:\n{json.dumps(chunk_payload, ensure_ascii=True)}"
    )


def call_llm(prompt: str, model: str, api_key: str) -> Dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)


def validate_llm_response(
    response: Dict[str, Any],
    candidate_by_id: Dict[str, ChunkRecord],
) -> Tuple[bool, str]:
    selected = response.get("selected_chunk_ids")
    citations = response.get("citations")
    unanswerable = response.get("unanswerable")
    if not isinstance(unanswerable, bool):
        return False, "unanswerable must be boolean"
    if not isinstance(selected, list):
        return False, "selected_chunk_ids must be list"
    if unanswerable and selected:
        return False, "unanswerable true must not include selected_chunk_ids"
    if citations is None:
        return False, "citations must be provided"
    if not isinstance(citations, list):
        return False, "citations must be list"
    selected_set = set(selected)
    for chunk_id in selected_set:
        if chunk_id not in candidate_by_id:
            return False, f"selected chunk_id not in candidates: {chunk_id}"
    for citation in citations:
        if not isinstance(citation, dict):
            return False, "citation entry must be object"
        chunk_id = citation.get("chunk_id")
        quotes = citation.get("quotes")
        if chunk_id not in candidate_by_id:
            return False, f"citation chunk_id not in candidates: {chunk_id}"
        if not isinstance(quotes, list):
            return False, "citation quotes must be list"
        chunk_text = candidate_by_id[chunk_id].text
        for quote in quotes:
            if not isinstance(quote, str) or not quote.strip():
                return False, "citation quote must be non-empty string"
            if quote not in chunk_text:
                return False, f"citation quote not found in chunk text: {chunk_id}"
    return True, ""


def build_query_record(
    item: Dict[str, Any],
    query_index: int,
    expected_chunk_ids: List[str],
    binding_meta: Dict[str, Any],
    document_id: Optional[str],
) -> Dict[str, Any]:
    query_text = item.get("query", "")
    reference_answer = item.get("reference_answer", "")
    return {
        "id": f"benchmark::{query_index}",
        "query_text": query_text,
        "query_text_short": query_text[:160],
        "expected_chunk_ids": expected_chunk_ids,
        "hypothetical_answer": reference_answer,
        "document_id": document_id,
        "benchmark_axes": item.get("query_axes"),
        "answer_characteristics": item.get("answer_characteristics"),
        "binding": binding_meta,
    }


def _parse_ambiguity_level(item: Dict[str, Any]) -> int:
    axes = item.get("query_axes") or {}
    raw = axes.get("ambiguity")
    if not isinstance(raw, str) or not raw:
        return 0
    try:
        return int(raw.strip().lstrip("Ff"))
    except ValueError:
        return 0


def _adjust_candidate_limits(base_top_k: int, base_max_candidates: int, ambiguity_level: int) -> tuple[int, int]:
    if ambiguity_level <= 1:
        return base_top_k, base_max_candidates
    extra_by_level = {2: 10, 3: 20, 4: 30}
    extra = extra_by_level.get(ambiguity_level, 30)
    return base_top_k + extra, base_max_candidates + max(5, extra // 2)


def write_queries(path: str, queries: List[Dict[str, Any]]) -> None:
    payload = {
        "queries": queries,
        "source": "benchmark_dataset",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
    print(f"✅ Wrote {len(queries)} queries to {path}")


def write_chunks(path: str, chunks: List[ChunkRecord], document_id: str) -> None:
    payload = {
        "document": document_id,
        "chunks": [
            {
                "id": record.chunk_id,
                "text": record.text,
                "page": record.page,
                "section_path": record.section_path,
                "content_kind": record.content_kind,
                "document_id": record.document_id,
            }
            for record in chunks
        ],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
    print(f"✅ Wrote {len(chunks)} chunks to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bind benchmark queries to chunk IDs.")
    parser.add_argument("--benchmark-path", required=True)
    parser.add_argument("--chunks-path", action="append", default=[])
    parser.add_argument("--chunks-dir", default=None)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--output-chunks-path", default=None)
    parser.add_argument("--embedding-model", default="nomic-embed-text-v2")
    parser.add_argument("--candidate-top-k", type=int, default=20)
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument("--max-chunk-chars", type=int, default=1200)
    parser.add_argument("--max-queries", type=int, default=None)
    parser.add_argument("--prefix-doc-id", action="store_true")
    parser.add_argument("--query-document-id", default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-api-key", default=None)
    args = parser.parse_args()

    benchmark_items = load_json(args.benchmark_path)
    if not isinstance(benchmark_items, list):
        raise ValueError("Benchmark dataset must be a list.")

    chunk_paths = list(args.chunks_path)
    if args.chunks_dir:
        for name in os.listdir(args.chunks_dir):
            if name.endswith(".coalesced.json") or name.endswith(".enriched.json"):
                chunk_paths.append(os.path.join(args.chunks_dir, name))
    if not chunk_paths:
        raise ValueError("At least one chunks path is required.")

    prefix_doc_id = args.prefix_doc_id or len(chunk_paths) > 1
    chunks = load_chunks(chunk_paths, prefix_doc_id=prefix_doc_id)
    query_document_id = args.query_document_id
    if query_document_id is None and len(chunk_paths) > 1:
        query_document_id = "unknown"
    chunk_by_id = {record.chunk_id: record for record in chunks}
    chunk_ids = [record.chunk_id for record in chunks]
    chunk_texts = [record.text for record in chunks]

    model_spec = MODEL_REGISTRY.get(args.embedding_model)
    if not model_spec:
        raise ValueError(f"Unknown embedding model: {args.embedding_model}")
    model = load_model(model_spec.model_name)
    chunk_embeddings = encode_texts(model, chunk_texts, batch_size=16)

    llm_api_key = args.llm_api_key or os.getenv("OPENAI_API_KEY")
    if not llm_api_key:
        raise ValueError("OPENAI_API_KEY is required for LLM binding.")
    llm_model = args.llm_model or os.getenv("OPENAI_MODEL", "gpt-5.2")

    queries: List[Dict[str, Any]] = []
    max_queries = args.max_queries or len(benchmark_items)
    for idx, item in enumerate(benchmark_items[:max_queries]):
        query_text = item.get("query", "")
        reference_answer = item.get("reference_answer", "")
        ambiguity_level = _parse_ambiguity_level(item)
        candidate_top_k, max_candidates = _adjust_candidate_limits(
            args.candidate_top_k, args.max_candidates, ambiguity_level
        )
        candidates = build_candidate_set(
            query_text=query_text,
            reference_answer=reference_answer,
            chunks=chunks,
            chunk_embeddings=chunk_embeddings,
            chunk_ids=chunk_ids,
            model=model,
            top_k=candidate_top_k,
        )

        candidate_list = []
        for chunk_id, meta in candidates.items():
            record = chunk_by_id[chunk_id]
            candidate_list.append(
                {
                    "chunk_id": chunk_id,
                    "text": record.text,
                    "section_path": record.section_path,
                    "score": meta.get("score", 0.0),
                    "reasons": sorted(meta.get("reasons", set())),
                }
            )
        candidate_list.sort(key=lambda c: c.get("score", 0.0), reverse=True)
        candidate_list = candidate_list[:max_candidates]
        candidate_by_id = {c["chunk_id"]: chunk_by_id[c["chunk_id"]] for c in candidate_list}

        prompt = build_llm_prompt(
            query_text=query_text,
            reference_answer=reference_answer,
            candidates=candidate_list,
            max_chunk_chars=args.max_chunk_chars,
        )
        llm_response = call_llm(prompt, llm_model, llm_api_key)
        is_valid, error = validate_llm_response(llm_response, candidate_by_id)
        if not is_valid:
            binding_meta = {
                "status": "invalid_llm_response",
                "error": error,
                "candidate_count": len(candidate_list),
                "candidate_top_k": candidate_top_k,
                "model": llm_model,
            }
            expected_chunk_ids: List[str] = []
        else:
            expected_chunk_ids = llm_response.get("selected_chunk_ids", [])
            binding_meta = {
                "status": "bound" if expected_chunk_ids else "unanswerable",
                "candidate_count": len(candidate_list),
                "candidate_top_k": candidate_top_k,
                "model": llm_model,
                "citations": llm_response.get("citations"),
                "notes": llm_response.get("notes"),
            }

        queries.append(
            build_query_record(item, idx, expected_chunk_ids, binding_meta, query_document_id)
        )

    write_queries(args.output_path, queries)
    if args.output_chunks_path:
        merged_doc_id = os.path.splitext(os.path.basename(args.output_chunks_path))[0]
        write_chunks(args.output_chunks_path, chunks, merged_doc_id)


if __name__ == "__main__":
    main()

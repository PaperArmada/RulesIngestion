from pathlib import Path

import numpy as np

from evaluation.benchmark import run_embedding_benchmark
from evaluation.model_registry import EmbeddingModelSpec


def test_run_embedding_benchmark_with_embedding_cache(tmp_path: Path) -> None:
    doc_id = "doc1"
    chunks_path = tmp_path / f"{doc_id}.enriched.json"
    queries_path = tmp_path / f"{doc_id}.evaluation_queries.json"

    chunks_payload = {
        "document": doc_id,
        "chunks": [
            {
                "id": "c1",
                "text": "Alpha chunk",
                "page": 1,
                "section_path": ["Chapter1"],
                "content_kind": "rule",
                "document_id": doc_id,
            }
        ],
    }
    queries_payload = {
        "document": doc_id,
        "queries": [
            {
                "id": "q1",
                "query_text": "Alpha?",
                "expected_chunk_ids": ["c1"],
            }
        ],
    }

    chunks_path.write_text(json_dumps(chunks_payload), encoding="utf-8")
    queries_path.write_text(json_dumps(queries_payload), encoding="utf-8")

    embedding_cache = {
        "chunk_embeddings": np.array([[1.0, 0.0]], dtype=np.float32),
        "query_embeddings": np.array([[1.0, 0.0]], dtype=np.float32),
    }

    result = run_embedding_benchmark(
        run_id=None,
        model_spec=EmbeddingModelSpec("test-model", "test-model"),
        chunk_source="enriched",
        queries_path=str(queries_path),
        batch_size=1,
        top_k=[1],
        expand_gold=False,
        embedding_cache=embedding_cache,
    )

    metrics = result["evaluation"]["metrics"]
    assert metrics["hit_rates"]["hit@1"] == 1.0


def json_dumps(payload: dict) -> str:
    import json

    return json.dumps(payload, indent=2)

import json
from pathlib import Path

import numpy as np
import pytest

from evaluation.chapter_routing import build_chapter_routing
from evaluation.metrics import (
    compute_baseline_delta,
    compute_reachability_monotonicity,
)
from evaluation.reporting import write_report
from evaluation.scoring_engine import score_queries


def test_score_queries_basic_hit() -> None:
    chunk_ids = ["doc::c1", "doc::c2"]
    chunk_embeddings = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    query_embeddings = np.array([[1.0, 0.0]], dtype=np.float32)
    expected_ids = [["doc::c1"]]

    metrics, details = score_queries(
        query_embeddings,
        chunk_embeddings,
        expected_ids,
        chunk_ids,
        top_k=[1, 3],
    )

    assert metrics["query_count"] == 1
    assert metrics["evaluated_queries"] == 1
    assert metrics["hit_rates"]["hit@1"] == 1.0
    assert details[0]["expected_found"] is True
    assert details[0]["expected_rank"] == 1


def test_build_chapter_routing_allows_expected_chunk() -> None:
    chunk_ids = ["doc::c1", "doc::c2"]
    chapter_id_by_index = ["doc::ChapterA", "doc::ChapterB"]
    chapter_index_by_id = {cid: idx for idx, cid in enumerate(chapter_id_by_index)}
    chapter_to_chunk_indices = {"doc::ChapterA": [0], "doc::ChapterB": [1]}
    chapter_embeddings = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    chunk_embeddings = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    query_embeddings = np.array([[1.0, 0.0]], dtype=np.float32)

    result = build_chapter_routing(
        query_embeddings=query_embeddings,
        chapter_embeddings=chapter_embeddings,
        chapter_id_by_index=chapter_id_by_index,
        chapter_index_by_id=chapter_index_by_id,
        chapter_to_chunk_indices=chapter_to_chunk_indices,
        chunk_ids=chunk_ids,
        chunk_embeddings=chunk_embeddings,
        query_document_ids=["doc"],
        query_book_ids=["doc"],
        query_allowed_book_ids=[{"doc"}],
        chapter_book_ids={"doc::ChapterA": "doc", "doc::ChapterB": "doc"},
        expected_ids=[["doc::c1"]],
        adjacency_by_document=None,
        chunk_kind_by_id={"doc::c1": "rule", "doc::c2": "rule"},
        graph_boost=0.0,
        graph_boost_depth=1,
        graph_boost_top_k=None,
        graph_boost_seed_top_n=1,
        graph_boost_same_kind_only=False,
        graph_boost_decay=1.0,
        top_n=1,
        rerank=False,
        report_details=False,
    )

    assert result.allowed_chunk_ids_by_query[0] == {"doc::c1"}
    assert result.avg_allowed_chunks == 1.0


def test_reachability_monotonicity_counts_losses() -> None:
    expected_ids = [["c1"], ["c2"]]
    chunk_to_chapter = {"c1": "ch1", "c2": "ch2"}
    pool_chapters = [{"ch1"}, set()]
    final_chapters = [{"ch1"}, set()]

    metrics = compute_reachability_monotonicity(
        expected_ids=expected_ids,
        chunk_to_chapter=chunk_to_chapter,
        pool_chapters_by_query=pool_chapters,
        final_chapters_by_query=final_chapters,
    )

    assert metrics["reachable_queries"] == 2
    assert metrics["lost_at_pool"] == 1
    assert metrics["lost_at_final"] == 1
    assert metrics["reachability_monotonic"] is False


def test_compute_baseline_delta() -> None:
    baseline = {"coverage": 0.5, "mrr": 0.2, "hit_rates": {"hit@1": 0.1}}
    current = {"coverage": 0.7, "mrr": 0.4, "hit_rates": {"hit@1": 0.3}}

    delta = compute_baseline_delta(baseline, current)

    assert delta["coverage"] == pytest.approx(0.2)
    assert delta["mrr"] == pytest.approx(0.2)
    assert delta["hit_rates"]["hit@1"] == pytest.approx(0.2)


def test_write_report_creates_files(tmp_path: Path) -> None:
    report = {
        "summary": {
            "run_id": "run-1",
            "ruleset_id": None,
            "document_id": None,
            "model_id": "test-model",
            "chunk_source": "enriched",
            "chunk_count": 2,
            "query_count": 1,
            "evaluated_queries": 1,
            "coverage": 1.0,
            "mrr": 1.0,
            "hit_rates": {"hit@1": 1.0},
            "cross_book_contamination": {},
            "embedding_reused": False,
            "embedding_reuse_reason": None,
            "graph_boost": {"enabled": False},
            "chapter_routing": {"enabled": False},
            "timings_ms": {
                "embedding": 1,
                "query_embedding": 1,
                "evaluation_strict": 1,
                "evaluation_expanded": 0,
                "total": 3,
            },
            "timings_estimate_ms": None,
        },
        "queries": [
            {
                "query_index": 0,
                "query_text": "What is test?",
                "expected_chunk_ids": ["c1"],
                "expected_found": True,
                "expected_rank": 1,
                "top_results": [],
            }
        ],
    }

    report_paths = write_report(report, str(tmp_path), "report_test")

    json_path = Path(report_paths["json"])
    md_path = Path(report_paths["md"])
    assert json_path.exists()
    assert md_path.exists()
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["summary"]["run_id"] == "run-1"

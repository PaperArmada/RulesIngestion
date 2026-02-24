from __future__ import annotations

from retrieval_lab.benchmark_lint import lint_flat_queries


def test_lint_warns_on_empty_required_gold_when_declared() -> None:
    flat = [
        {
            "id": "q1",
            "question": "x",
            "required_gold": [],
            "supporting_gold": [],
            "_source_path": "/tmp/batch.json",
        }
    ]
    summary = lint_flat_queries(flat)
    codes = [i["code"] for i in summary["issues"]]
    assert "required_gold_empty" in codes


def test_lint_warns_on_large_required_gold() -> None:
    flat = [
        {
            "id": "q2",
            "question": "x",
            "required_gold": ["a", "b", "c", "d", "e"],
            "_source_path": "/tmp/batch.json",
        }
    ]
    summary = lint_flat_queries(flat)
    codes = [i["code"] for i in summary["issues"]]
    assert "required_gold_large" in codes


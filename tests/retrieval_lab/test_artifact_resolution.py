from __future__ import annotations

import json
from pathlib import Path

from retrieval_lab.artifact_resolution import load_resolved_json_artifact, resolve_run_artifacts


def test_resolve_run_artifacts_prefers_legacy_single_surface_files(tmp_path: Path) -> None:
    (tmp_path / "metrics.json").write_text(json.dumps({"all-mpnet-base-v2": {"mrr": 0.5}}), encoding="utf-8")
    (tmp_path / "per_query.json").write_text(json.dumps({"all-mpnet-base-v2": []}), encoding="utf-8")
    (tmp_path / "retrieved_chunks.json").write_text(
        json.dumps({"by_model": {"all-mpnet-base-v2": []}}),
        encoding="utf-8",
    )
    (tmp_path / "benchmark.active.json").write_text(json.dumps([{"id": "q1"}]), encoding="utf-8")
    (tmp_path / "benchmark.active.contract.json").write_text(json.dumps({"version": "v1"}), encoding="utf-8")

    resolved = resolve_run_artifacts(tmp_path)

    assert resolved["selected_surface"] == "active"
    assert resolved["artifacts"]["metrics"].endswith("metrics.json")
    assert resolved["artifacts"]["per_query"].endswith("per_query.json")
    assert resolved["artifacts"]["retrieved_chunks"].endswith("retrieved_chunks.json")
    assert resolved["artifacts"]["benchmark"].endswith("benchmark.active.json")


def test_resolve_run_artifacts_uses_prod_readiness_selected_surface(tmp_path: Path) -> None:
    (tmp_path / "metrics.clean_subset.json").write_text(
        json.dumps({"all-mpnet-base-v2": {"mrr": 0.8}}),
        encoding="utf-8",
    )
    (tmp_path / "per_query.clean_subset.json").write_text(
        json.dumps({"all-mpnet-base-v2": [{"query_id": "q1"}]}),
        encoding="utf-8",
    )
    (tmp_path / "retrieved_chunks.clean_subset.json").write_text(
        json.dumps({"by_model": {"all-mpnet-base-v2": []}}),
        encoding="utf-8",
    )
    (tmp_path / "benchmark.clean_subset.json").write_text(json.dumps([{"id": "q1"}]), encoding="utf-8")
    (tmp_path / "benchmark.clean_subset.contract.json").write_text(
        json.dumps({"version": "v1"}),
        encoding="utf-8",
    )
    (tmp_path / "evaluation_surfaces.json").write_text(
        json.dumps(
            {
                "full_working_set": {"metrics": "metrics.full_working_set.json"},
                "clean_subset": {"metrics": "metrics.clean_subset.json"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "prod_readiness.json").write_text(
        json.dumps(
            {
                "selected_surface": "clean_subset",
                "selected_model_id": "all-mpnet-base-v2",
            }
        ),
        encoding="utf-8",
    )

    resolved = resolve_run_artifacts(tmp_path)
    metrics = load_resolved_json_artifact(tmp_path, "metrics")
    per_query = load_resolved_json_artifact(tmp_path, "per_query")

    assert resolved["selected_surface"] == "clean_subset"
    assert resolved["selected_model_id"] == "all-mpnet-base-v2"
    assert resolved["artifacts"]["metrics"].endswith("metrics.clean_subset.json")
    assert resolved["artifacts"]["per_query"].endswith("per_query.clean_subset.json")
    assert metrics["all-mpnet-base-v2"]["mrr"] == 0.8
    assert per_query["all-mpnet-base-v2"][0]["query_id"] == "q1"

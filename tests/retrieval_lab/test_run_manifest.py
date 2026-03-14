from __future__ import annotations

import json
from pathlib import Path

from retrieval_lab.run_manifest import build_run_manifest


def test_manifest_includes_file_hashes(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("x: 1\n", encoding="utf-8")
    batch = tmp_path / "batch.json"
    batch.write_text(json.dumps({"queries": []}), encoding="utf-8")
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"profile_id": "p"}), encoding="utf-8")
    definition_snapshot = tmp_path / "benchmark_definition_00.json"
    definition_snapshot.write_text(json.dumps([{"id": "q1"}]), encoding="utf-8")
    projection_snapshot = tmp_path / "benchmark.active.json"
    projection_snapshot.write_text(json.dumps([{"id": "q1", "gold_unit_ids": ["u1"]}]), encoding="utf-8")
    corpus_index = tmp_path / "corpus_index.json"
    corpus_index.write_text(json.dumps({"run_id": "run_123"}), encoding="utf-8")
    prod_readiness = tmp_path / "prod_readiness.json"
    prod_readiness.write_text(json.dumps({"promotion_ready": True}), encoding="utf-8")

    manifest = build_run_manifest(
        experiment_id="exp1",
        argv=["python", "-m", "retrieval_lab.run_experiment"],
        config_dict={"query_batch_paths": [str(batch)]},
        source_config_path=str(cfg),
        query_batch_paths=[str(batch)],
        enhancement_profile_path=str(profile),
        benchmark_definition_snapshot_paths=[str(definition_snapshot)],
        benchmark_projection_snapshot_paths=[str(projection_snapshot)],
        corpus_index_path=str(corpus_index),
        prod_readiness_path=str(prod_readiness),
        bundle_metadata={
            "bundle_kind": "v1_baseline_package",
            "bundle_member_role": "canonical_baseline_run",
            "bundle_member_mode_hint": "C",
            "bundle_member_status": "canonical_member",
            "baseline_package_dir": str(tmp_path / "bundle"),
            "baseline_package_stamp": "20260313",
            "git_commit_sha": "abc123",
            "git_tag": "baseline-v1",
            "python_version": "3.13.2",
            "uv_lock_path": str(tmp_path / "uv.lock"),
            "uv_lock_sha256": "lock123",
        },
    )
    assert manifest["inputs"]["config_yaml"]["exists"] is True
    assert "sha256" in manifest["inputs"]["config_yaml"]
    assert manifest["inputs"]["query_batches"][0]["exists"] is True
    assert "sha256" in manifest["inputs"]["query_batches"][0]
    assert manifest["inputs"]["enhancement_profile"]["exists"] is True
    assert "sha256" in manifest["inputs"]["enhancement_profile"]
    assert manifest["inputs"]["benchmark_definition_snapshots"][0]["exists"] is True
    assert manifest["inputs"]["benchmark_projection_snapshots"][0]["exists"] is True
    assert manifest["inputs"]["corpus_index"]["exists"] is True
    assert manifest["inputs"]["prod_readiness"]["exists"] is True
    assert manifest["bundle"]["member_role"] == "canonical_baseline_run"
    assert manifest["bundle"]["baseline_package_stamp"] == "20260313"
    assert manifest["freeze"]["git_commit_sha"] == "abc123"
    assert manifest["freeze"]["uv_lock_sha256"] == "lock123"


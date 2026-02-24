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

    manifest = build_run_manifest(
        experiment_id="exp1",
        argv=["python", "-m", "retrieval_lab.run_experiment"],
        config_dict={"query_batch_paths": [str(batch)]},
        source_config_path=str(cfg),
        query_batch_paths=[str(batch)],
        enhancement_profile_path=str(profile),
    )
    assert manifest["inputs"]["config_yaml"]["exists"] is True
    assert "sha256" in manifest["inputs"]["config_yaml"]
    assert manifest["inputs"]["query_batches"][0]["exists"] is True
    assert "sha256" in manifest["inputs"]["query_batches"][0]
    assert manifest["inputs"]["enhancement_profile"]["exists"] is True
    assert "sha256" in manifest["inputs"]["enhancement_profile"]


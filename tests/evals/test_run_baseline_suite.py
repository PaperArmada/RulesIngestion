from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import evals.v1_baseline.run_baseline_suite as suite
from evals.v1_baseline.run_baseline_suite import _assert_no_contract_bypass_flags


def test_preflight_rejects_contract_bypass_flag(tmp_path) -> None:
    config_path = tmp_path / "bad.yaml"
    config_path.write_text(
        "\n".join(
            [
                'experiment_name: "bad"',
                'substrate_path: "."',
                'document_id: "Doc"',
                "query_batches: []",
                "models: []",
                "allow_benchmark_contract_mismatch: true",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="contract mismatch override flag is forbidden"):
        _assert_no_contract_bypass_flags([str(config_path)], tmp_path)


def test_preflight_allows_clean_configs(tmp_path) -> None:
    config_path = tmp_path / "good.yaml"
    config_path.write_text(
        "\n".join(
            [
                'experiment_name: "good"',
                'substrate_path: "."',
                'document_id: "Doc"',
                "query_batches: []",
                "models: []",
            ]
        ),
        encoding="utf-8",
    )

    _assert_no_contract_bypass_flags([str(config_path)], tmp_path)


def test_suite_omits_version_override_by_default(tmp_path, monkeypatch) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], cwd) -> str:
        commands.append(command)
        if "retrieval_lab.run_experiment" in command:
            return "Done. Experiment ID: fake_run\n"
        return ""

    monkeypatch.setattr(
        suite,
        "CORPUS_SPECS",
        [SimpleNamespace(config_path="retrieval_lab/experiments/hybrid/phb_hybrid.yaml")],
    )
    monkeypatch.setattr(
        suite,
        "build_baseline_run_specs",
        lambda **kwargs: [
            SimpleNamespace(
                config_path="retrieval_lab/experiments/hybrid/phb_hybrid.yaml",
                experiment_name="phb_hybrid_c",
                cli_overrides=[],
                corpus_id="DnD_PHB_5.5",
                mode="c_raw_only",
            )
        ],
    )
    monkeypatch.setattr(suite, "_assert_no_contract_bypass_flags", lambda *args, **kwargs: None)
    monkeypatch.setattr(suite, "_run", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_baseline_suite.py",
            "--out-dir",
            str(tmp_path / "suite_out"),
            "--strict-integrity",
            "--gating-integrity-policy",
            "strict",
            "--stage-b-gate-policy",
            "strict",
        ],
    )

    suite.main()

    run_commands = [command for command in commands if "retrieval_lab.run_experiment" in command]
    assert len(run_commands) == 1
    assert "--substrate-version" not in run_commands[0]


def test_suite_passes_explicit_version_override(tmp_path, monkeypatch) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], cwd) -> str:
        commands.append(command)
        if "retrieval_lab.run_experiment" in command:
            return "Done. Experiment ID: fake_run\n"
        return ""

    monkeypatch.setattr(
        suite,
        "CORPUS_SPECS",
        [SimpleNamespace(config_path="retrieval_lab/experiments/hybrid/phb_hybrid.yaml")],
    )
    monkeypatch.setattr(
        suite,
        "build_baseline_run_specs",
        lambda **kwargs: [
            SimpleNamespace(
                config_path="retrieval_lab/experiments/hybrid/phb_hybrid.yaml",
                experiment_name="phb_hybrid_c",
                cli_overrides=[],
                corpus_id="DnD_PHB_5.5",
                mode="c_raw_only",
            )
        ],
    )
    monkeypatch.setattr(suite, "_assert_no_contract_bypass_flags", lambda *args, **kwargs: None)
    monkeypatch.setattr(suite, "_run", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_baseline_suite.py",
            "--out-dir",
            str(tmp_path / "suite_out"),
            "--version",
            "v1_override",
            "--strict-integrity",
            "--gating-integrity-policy",
            "strict",
            "--stage-b-gate-policy",
            "strict",
        ],
    )

    suite.main()

    run_commands = [command for command in commands if "retrieval_lab.run_experiment" in command]
    assert len(run_commands) == 1
    assert "--substrate-version" in run_commands[0]
    version_index = run_commands[0].index("--substrate-version")
    assert run_commands[0][version_index + 1] == "v1_override"


def test_suite_writes_freeze_metadata_and_canonical_index(tmp_path, monkeypatch) -> None:
    out_dir = tmp_path / "suite_out"
    commands: list[list[str]] = []

    def fake_run(command: list[str], cwd) -> str:
        commands.append(command)
        if "retrieval_lab.run_experiment" in command:
            run_dir = out_dir / "fake_run"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "manifest.json").write_text(json.dumps({"version": "v1"}), encoding="utf-8")
            (run_dir / "run_manifest.json").write_text(
                json.dumps({"bundle": {}, "freeze": {}}),
                encoding="utf-8",
            )
            (run_dir / "metrics.clean_subset.json").write_text(
                json.dumps(
                    {
                        "all-mpnet-base-v2": {
                            "mrr": 0.75,
                            "gold_in_candidates_true_ceiling": 0.9,
                            "required_full_set_hit_at_k": {"10": 0.5, "20": 0.6},
                            "rank_of_last_required_mean": 4.0,
                            "raw_merge_rerank_diagnostics": {
                                "enabled": True,
                                "monotonic_rank_violations_total": 0,
                                "raw_top_missing_in_final_topk_total": 0,
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "per_query.clean_subset.json").write_text(
                json.dumps({"all-mpnet-base-v2": []}),
                encoding="utf-8",
            )
            (run_dir / "retrieved_chunks.clean_subset.json").write_text(
                json.dumps({"by_model": {"all-mpnet-base-v2": []}}),
                encoding="utf-8",
            )
            (run_dir / "benchmark.clean_subset.json").write_text(json.dumps([{"id": "q1"}]), encoding="utf-8")
            (run_dir / "benchmark.clean_subset.contract.json").write_text(
                json.dumps({"version": "v1"}),
                encoding="utf-8",
            )
            (run_dir / "prod_readiness.json").write_text(
                json.dumps(
                    {
                        "selected_surface": "clean_subset",
                        "selected_model_id": "all-mpnet-base-v2",
                        "contract_valid": True,
                        "promotion_ready": True,
                        "benchmark_projection": {"path": str(run_dir / "benchmark.clean_subset.json"), "sha256": "proj123"},
                        "benchmark_contract": {
                            "path": str(run_dir / "benchmark.clean_subset.contract.json"),
                            "sha256": "contract123",
                        },
                        "corpus_contract": {
                            "corpus_fingerprint": "fp123",
                            "corpus_content_fingerprint": "cfp123",
                            "corpus_index_path": str(run_dir / "embeddings" / "corpus_index.json"),
                            "corpus_index_sha256": "idx123",
                        },
                        "bundle": {},
                        "freeze": {},
                    }
                ),
                encoding="utf-8",
            )
            return "Done. Experiment ID: fake_run\n"
        return ""

    monkeypatch.setattr(
        suite,
        "CORPUS_SPECS",
        [SimpleNamespace(config_path="retrieval_lab/experiments/hybrid/phb_hybrid.yaml")],
    )
    monkeypatch.setattr(
        suite,
        "build_baseline_run_specs",
        lambda **kwargs: [
            SimpleNamespace(
                config_path="retrieval_lab/experiments/hybrid/phb_hybrid.yaml",
                experiment_name="phb_hybrid_c_raw_first_merge_rerank",
                cli_overrides=[],
                corpus_id="DnD_PHB_5.5",
                mode=suite.MODE_C_RAW_FIRST_MERGE_RERANK,
            )
        ],
    )
    monkeypatch.setattr(suite, "_assert_no_contract_bypass_flags", lambda *args, **kwargs: None)
    monkeypatch.setattr(suite, "_run", fake_run)
    monkeypatch.setattr(
        suite,
        "build_repo_freeze_metadata",
        lambda repo_root, package_dir=None: {
            "baseline_package_dir": str(package_dir),
            "baseline_package_stamp": "20260313",
            "git_commit_sha": "abc123",
            "git_tag": "baseline-v1",
            "python_version": "3.13.2",
            "uv_lock_path": str(tmp_path / "uv.lock"),
            "uv_lock_sha256": "lock123",
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_baseline_suite.py",
            "--out-dir",
            str(out_dir),
            "--strict-integrity",
            "--gating-integrity-policy",
            "strict",
            "--stage-b-gate-policy",
            "strict",
        ],
    )

    suite.main()

    summary = json.loads((out_dir / "baseline_process_summary.json").read_text(encoding="utf-8"))
    canonical_index = json.loads((out_dir / "canonical_runs_index.json").read_text(encoding="utf-8"))
    prod_readiness = json.loads((out_dir / "fake_run" / "prod_readiness.json").read_text(encoding="utf-8"))

    assert summary["baseline_package"]["git_commit_sha"] == "abc123"
    assert summary["canonical_runs"][0]["selected_surface"] == "clean_subset"
    assert canonical_index["canonical_runs"][0]["experiment_id"] == "fake_run"
    assert canonical_index["baseline_package"]["canonical_runs_index_sha256"]
    assert prod_readiness["bundle"]["member_role"] == "canonical_baseline_run"
    assert prod_readiness["freeze"]["uv_lock_sha256"] == "lock123"

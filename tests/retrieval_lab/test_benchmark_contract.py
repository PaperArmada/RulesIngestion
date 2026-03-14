from __future__ import annotations

import json
from pathlib import Path

from retrieval_lab.benchmark_contract import (
    build_prod_readiness_artifact,
    benchmark_contract_sidecar_path,
    benchmark_query_alignment_summary,
    build_benchmark_contract,
    validate_benchmark_contract,
    write_benchmark_contract,
)


def test_benchmark_query_alignment_summary_counts_missing_ids() -> None:
    queries = [
        {
            "id": "q1",
            "gold_locations": {
                "alive": {"page": 1},
                "dead": {"page": 1},
            },
        },
        {
            "id": "q2",
            "gold_unit_ids": ["missing_only"],
        },
    ]

    summary = benchmark_query_alignment_summary(queries, corpus_ids=["alive"])

    assert summary["queries_total"] == 2
    assert summary["queries_with_contract_gold_ids"] == 2
    assert summary["queries_with_missing_gold_ids"] == 2
    assert summary["queries_with_no_surviving_gold_ids"] == 1
    assert summary["missing_gold_ids_total"] == 2
    assert summary["missing_gold_ids_unique"] == ["dead", "missing_only"]


def test_validate_benchmark_contract_accepts_matching_contract(tmp_path: Path) -> None:
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_payload = [{"id": "q1", "gold_locations": {"alive": {"page": 1}}}]
    benchmark_path.write_text(json.dumps(benchmark_payload, indent=2), encoding="utf-8")
    contract_path = benchmark_contract_sidecar_path(benchmark_path)
    contract = build_benchmark_contract(
        benchmark_path=benchmark_path,
        query_count=1,
        run_id="run_123",
        substrate_version="sv1",
        corpus_fingerprint="fp1",
        corpus_content_fingerprint="cfp1",
        corpus_unit_count=1,
        corpus_index_path=str(tmp_path / "corpus_index.json"),
        corpus_index_sha256="idx1",
        corpus_recipe={"min_chars": 100, "merge_chunks": True, "merge_max_chars": 2000},
        benchmark_surface="active",
        alignment_summary=benchmark_query_alignment_summary(benchmark_payload, corpus_ids=["alive"]),
    )
    write_benchmark_contract(contract_path, contract)

    validation = validate_benchmark_contract(
        benchmark_path=benchmark_path,
        contract_path=contract_path,
        query_count=1,
        run_id="run_123",
        substrate_version="sv1",
        corpus_fingerprint="fp1",
        corpus_content_fingerprint="cfp1",
        corpus_index_sha256="idx1",
        benchmark_surface="active",
        alignment_summary=benchmark_query_alignment_summary(benchmark_payload, corpus_ids=["alive"]),
    )

    assert validation["valid"] is True
    assert validation["errors"] == []


def test_validate_benchmark_contract_rejects_mismatched_corpus_and_dead_ids(tmp_path: Path) -> None:
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_payload = [{"id": "q1", "gold_locations": {"dead": {"page": 1}}}]
    benchmark_path.write_text(json.dumps(benchmark_payload, indent=2), encoding="utf-8")
    contract_path = benchmark_contract_sidecar_path(benchmark_path)
    contract = build_benchmark_contract(
        benchmark_path=benchmark_path,
        query_count=1,
        run_id="run_123",
        substrate_version="sv1",
        corpus_fingerprint="fp_contract",
        corpus_content_fingerprint="cfp_contract",
        corpus_unit_count=1,
        corpus_index_path=str(tmp_path / "corpus_index.json"),
        corpus_index_sha256="idx_contract",
        benchmark_surface="pre_review_manual",
        alignment_summary=benchmark_query_alignment_summary(benchmark_payload, corpus_ids=["alive"]),
    )
    write_benchmark_contract(contract_path, contract)

    validation = validate_benchmark_contract(
        benchmark_path=benchmark_path,
        contract_path=contract_path,
        query_count=1,
        run_id="run_123",
        substrate_version="sv1",
        corpus_fingerprint="fp_current",
        corpus_content_fingerprint="cfp_current",
        corpus_index_sha256="idx_current",
        benchmark_surface="post_review_applied",
        alignment_summary=benchmark_query_alignment_summary(benchmark_payload, corpus_ids=["alive"]),
    )

    assert validation["valid"] is False
    assert any("corpus_fingerprint mismatch" in err for err in validation["errors"])
    assert any("corpus_content_fingerprint mismatch" in err for err in validation["errors"])
    assert any("corpus_index_sha256 mismatch" in err for err in validation["errors"])
    assert any("surface mismatch" in err for err in validation["errors"])
    assert any("corpus-missing gold ids" in err for err in validation["errors"])


def test_build_prod_readiness_artifact_requires_contract_validity() -> None:
    artifact = build_prod_readiness_artifact(
        experiment_id="exp1",
        experiment_name="demo",
        run_id="run_123",
        selected_surface="active",
        selected_model_id="model_a",
        benchmark_projection_path="/tmp/benchmark.active.json",
        benchmark_projection_sha256="proj123",
        benchmark_contract_path="/tmp/benchmark.active.contract.json",
        benchmark_contract_sha256="contract123",
        corpus_fingerprint="fp123",
        corpus_content_fingerprint="cfp123",
        corpus_index_path="/tmp/corpus_index.json",
        corpus_index_sha256="idx123",
        contract_validations=[
            {"benchmark_path": "/tmp/bench.json", "valid": True, "errors": []},
        ],
        metrics_by_model={
            "model_a": {
                "mrr": 0.5,
                "gold_in_candidates_true_ceiling": 0.9,
                "required_full_set_hit_at_k": {10: 0.4},
                "outcome_classification": "coverage_gain",
            }
        },
        bundle_metadata={
            "bundle_kind": "v1_baseline_package",
            "bundle_member_role": "canonical_baseline_run",
            "bundle_member_status": "canonical_member",
            "baseline_package_stamp": "20260313",
            "git_commit_sha": "abc123",
            "python_version": "3.13.2",
        },
    )

    assert artifact["promotion_ready"] is True
    assert artifact["selected_surface"] == "active"
    assert artifact["metrics_summary"]["required_full_set_hit_at_10"] == 0.4
    assert artifact["bundle"]["member_role"] == "canonical_baseline_run"
    assert artifact["freeze"]["git_commit_sha"] == "abc123"

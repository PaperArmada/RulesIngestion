"""Matrix runner for the v1 C-first baseline process."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from evals.v1_baseline.baseline_process import (
    CORPUS_SPECS,
    MODE_C_RAW_FIRST_MERGE_RERANK,
    build_baseline_run_specs,
)
from retrieval_lab.artifact_resolution import load_resolved_json_artifact, resolve_run_artifacts
from retrieval_lab.bundle_metadata import build_repo_freeze_metadata, sha256_file
from retrieval_lab.config import ExperimentConfig


def _string_or_int_lookup(values: dict, k: int) -> float:
    if k in values:
        return float(values[k])
    return float(values.get(str(k), 0.0))


def _run(command: list[str], cwd: Path) -> str:
    completed = subprocess.run(command, cwd=str(cwd), check=False, capture_output=True, text=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return completed.stdout or ""


def _extract_experiment_id(output: str) -> str | None:
    match = re.search(r"Done\. Experiment ID:\s*([^\s]+)", output)
    if match:
        return match.group(1).strip()
    return None


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _assert_no_contract_bypass_flags(config_paths: list[str], repo_root: Path) -> None:
    offending: list[str] = []
    for config_path in sorted(set(config_paths)):
        config = ExperimentConfig.from_yaml(Path(config_path), base_dir=repo_root)
        if bool(getattr(config, "allow_benchmark_contract_mismatch", False)):
            offending.append(config_path)
    if offending:
        joined = ", ".join(offending)
        raise SystemExit(
            f"Baseline suite preflight failed: contract mismatch override flag is forbidden in active configs: {joined}"
        )


def _load_selected_model_metrics(run_dir: Path) -> tuple[Dict[str, Any], Dict[str, Any]]:
    resolved = resolve_run_artifacts(run_dir)
    metrics_payload = load_resolved_json_artifact(
        run_dir,
        "metrics",
        preferred_surface=resolved.get("selected_surface") or None,
    )
    if not isinstance(metrics_payload, dict):
        return {}, resolved
    preferred_model = str(resolved.get("selected_model_id") or "")
    if preferred_model and isinstance(metrics_payload.get(preferred_model), dict):
        return dict(metrics_payload[preferred_model]), resolved
    if "all-mpnet-base-v2" in metrics_payload and isinstance(metrics_payload["all-mpnet-base-v2"], dict):
        return dict(metrics_payload["all-mpnet-base-v2"]), resolved
    first_model = next(
        (dict(metrics) for metrics in metrics_payload.values() if isinstance(metrics, dict)),
        {},
    )
    return first_model, resolved


def _bundle_role_for_mode(mode: str) -> tuple[str, str, bool]:
    if str(mode) == MODE_C_RAW_FIRST_MERGE_RERANK:
        return ("canonical_baseline_run", "canonical_member", True)
    return ("baseline_suite_comparator", "noncanonical_member", False)


def _patch_run_membership(
    *,
    run_dir: Path,
    freeze_metadata: Dict[str, Any],
    mode: str,
) -> None:
    member_role, member_status, canonical_member = _bundle_role_for_mode(mode)
    bundle_patch = {
        "kind": "v1_baseline_package",
        "member_role": member_role,
        "member_mode_hint": "C" if canonical_member else "",
        "member_status": member_status,
        "canonical_bundle_member": canonical_member,
        "canonical_mode": str(mode) if canonical_member else "",
        "baseline_package_dir": str(freeze_metadata.get("baseline_package_dir") or ""),
        "baseline_package_stamp": str(freeze_metadata.get("baseline_package_stamp") or ""),
    }
    freeze_patch = {
        "git_commit_sha": str(freeze_metadata.get("git_commit_sha") or ""),
        "git_tag": str(freeze_metadata.get("git_tag") or ""),
        "python_version": str(freeze_metadata.get("python_version") or ""),
        "uv_lock_path": str(freeze_metadata.get("uv_lock_path") or ""),
        "uv_lock_sha256": str(freeze_metadata.get("uv_lock_sha256") or ""),
    }
    for filename in ("run_manifest.json", "prod_readiness.json"):
        path = run_dir / filename
        if not path.exists():
            continue
        payload = _read_json(path)
        payload["bundle"] = {
            **dict(payload.get("bundle") or {}),
            **bundle_patch,
        }
        payload["freeze"] = {
            **dict(payload.get("freeze") or {}),
            **freeze_patch,
        }
        _write_json(path, payload)


def _build_run_record(
    *,
    run_dir: Path,
    corpus_id: str,
    mode: str,
    experiment_id: str,
) -> Dict[str, Any]:
    metrics, resolved = _load_selected_model_metrics(run_dir)
    diagnostics = metrics.get("raw_merge_rerank_diagnostics", {})
    prod_readiness = dict(resolved.get("prod_readiness") or {})
    benchmark_projection = dict(prod_readiness.get("benchmark_projection") or {})
    benchmark_contract = dict(prod_readiness.get("benchmark_contract") or {})
    corpus_contract = dict(prod_readiness.get("corpus_contract") or {})
    bundle = dict(prod_readiness.get("bundle") or {})

    return {
        "corpus_id": corpus_id,
        "mode": mode,
        "experiment_id": experiment_id,
        "run_dir": str(run_dir.resolve()),
        "selected_surface": str(prod_readiness.get("selected_surface") or resolved.get("selected_surface") or ""),
        "selected_model_id": str(prod_readiness.get("selected_model_id") or resolved.get("selected_model_id") or ""),
        "metrics_path": str((resolved.get("artifacts") or {}).get("metrics") or ""),
        "per_query_path": str((resolved.get("artifacts") or {}).get("per_query") or ""),
        "retrieved_chunks_path": str((resolved.get("artifacts") or {}).get("retrieved_chunks") or ""),
        "prod_readiness_path": str(resolved.get("prod_readiness_path") or ""),
        "manifest_path": str((run_dir / "manifest.json").resolve()) if (run_dir / "manifest.json").exists() else "",
        "run_manifest_path": (
            str((run_dir / "run_manifest.json").resolve()) if (run_dir / "run_manifest.json").exists() else ""
        ),
        "metrics": {
            "mrr": float(metrics.get("mrr", 0.0)),
            "gold_in_candidates_true_ceiling": float(metrics.get("gold_in_candidates_true_ceiling", 0.0)),
            "required_full_set_hit_at_10": _string_or_int_lookup(metrics.get("required_full_set_hit_at_k", {}), 10),
            "required_full_set_hit_at_20": _string_or_int_lookup(metrics.get("required_full_set_hit_at_k", {}), 20),
            "rank_of_last_required_mean": float(metrics.get("rank_of_last_required_mean", 0.0)),
            "raw_merge_diagnostics": {
                "enabled": bool(diagnostics.get("enabled", False)),
                "monotonic_rank_violations_total": int(diagnostics.get("monotonic_rank_violations_total", 0)),
                "raw_top_missing_in_final_topk_total": int(
                    diagnostics.get("raw_top_missing_in_final_topk_total", 0)
                ),
            },
        },
        "contract_valid": bool(prod_readiness.get("contract_valid")),
        "promotion_ready": bool(prod_readiness.get("promotion_ready")),
        "benchmark_projection": benchmark_projection,
        "benchmark_contract": benchmark_contract,
        "corpus_contract": corpus_contract,
        "bundle": bundle,
    }


def _build_canonical_index(run_records: list[Dict[str, Any]], *, canonical_index_path: Path) -> Dict[str, Any]:
    canonical_runs: list[Dict[str, Any]] = []
    for record in run_records:
        bundle = dict(record.get("bundle") or {})
        if not bool(bundle.get("canonical_bundle_member")):
            continue
        if not bool(record.get("promotion_ready")):
            continue
        canonical_runs.append(
            {
                "corpus_id": str(record.get("corpus_id") or ""),
                "canonical_mode": str(record.get("mode") or ""),
                "experiment_id": str(record.get("experiment_id") or ""),
                "prod_readiness_path": str(record.get("prod_readiness_path") or ""),
                "selected_surface": str(record.get("selected_surface") or ""),
                "selected_model_id": str(record.get("selected_model_id") or ""),
                "benchmark_projection_path": str((record.get("benchmark_projection") or {}).get("path") or ""),
                "benchmark_projection_sha256": str((record.get("benchmark_projection") or {}).get("sha256") or ""),
                "benchmark_contract_path": str((record.get("benchmark_contract") or {}).get("path") or ""),
                "benchmark_contract_sha256": str((record.get("benchmark_contract") or {}).get("sha256") or ""),
                "corpus_fingerprint": str((record.get("corpus_contract") or {}).get("corpus_fingerprint") or ""),
                "corpus_content_fingerprint": str(
                    (record.get("corpus_contract") or {}).get("corpus_content_fingerprint") or ""
                ),
                "corpus_index_path": str((record.get("corpus_contract") or {}).get("corpus_index_path") or ""),
                "corpus_index_sha256": str((record.get("corpus_contract") or {}).get("corpus_index_sha256") or ""),
                "manifest_path": str(record.get("manifest_path") or ""),
                "run_manifest_path": str(record.get("run_manifest_path") or ""),
            }
        )
    return {
        "version": "v1_baseline_canonical_runs_index_v1",
        "canonical_runs_index_path": str(canonical_index_path.resolve()),
        "canonical_runs": canonical_runs,
    }


def _collect_bundle_hygiene(out_dir: Path, run_records: list[Dict[str, Any]]) -> Dict[str, Any]:
    run_ids = {str(record.get("experiment_id") or "") for record in run_records if str(record.get("experiment_id") or "")}
    canonical_run_ids = sorted(
        str(record.get("experiment_id") or "")
        for record in run_records
        if bool((record.get("bundle") or {}).get("canonical_bundle_member"))
    )
    comparator_run_ids = sorted(run_ids - set(canonical_run_ids))
    extra_dirs = sorted(
        path.name
        for path in out_dir.iterdir()
        if path.is_dir() and path.name not in run_ids
    )
    return {
        "policy_version": "baseline_bundle_hygiene_v1",
        "canonical_run_dirs": canonical_run_ids,
        "noncanonical_comparator_run_dirs": comparator_run_ids,
        "historical_retry_run_dirs": extra_dirs,
        "historical_retry_policy": (
            "Retain extra run directories only as labeled history. Canonical consumers must use "
            "canonical_runs_index.json or prod_readiness.json-selected artifacts."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run v1 C-first baseline suite (optionally with A/B comparators)."
    )
    parser.add_argument("--out-dir", required=True, help="Output directory for run artifacts.")
    parser.add_argument(
        "--version",
        default=None,
        help="Optional substrate version override. Defaults to each config's canonical substrate_version.",
    )
    parser.add_argument("--seed", type=int, default=None, help="Optional seed passed to run_experiment.")
    parser.add_argument(
        "--c-only",
        action="store_true",
        help="Run only C baseline mode (skip A/B comparators).",
    )
    parser.add_argument(
        "--raw-stage1-admission-k",
        type=int,
        default=100,
        help="C mode: raw admission pool size before merged promotion.",
    )
    parser.add_argument(
        "--raw-merge-coverage-bonus",
        type=float,
        default=0.0,
        help="C mode: optional merged candidate coverage bonus.",
    )
    parser.add_argument(
        "--summary-json",
        default=None,
        help="Optional summary output path (defaults to <out-dir>/baseline_process_summary.json).",
    )
    parser.add_argument("--strict-integrity", action="store_true", help="Fail if benchmark integrity checks detect issues.")
    parser.add_argument("--gating-integrity-policy", choices=["strict", "warn"], default="strict")
    parser.add_argument("--stage-b-gate-policy", choices=["strict", "warn"], default="strict")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    include_comparators = not args.c_only
    run_specs = build_baseline_run_specs(
        include_comparators=include_comparators,
        raw_stage1_admission_k=args.raw_stage1_admission_k,
        raw_merge_coverage_bonus=args.raw_merge_coverage_bonus,
    )
    _assert_no_contract_bypass_flags([spec.config_path for spec in run_specs], repo_root)
    summary_json = Path(args.summary_json) if args.summary_json else (out_dir / "baseline_process_summary.json")
    freeze_metadata = build_repo_freeze_metadata(repo_root, package_dir=out_dir)

    for corpus in CORPUS_SPECS:
        config = corpus.config_path
        print(f"--- Integrity check: {config} ---", flush=True)
        integrity_out = out_dir / f"integrity_{Path(config).stem}.json"
        integrity_md = out_dir / f"integrity_{Path(config).stem}.md"
        policy = args.gating_integrity_policy
        integrity_cmd = [
            "uv",
            "run",
            "python",
            "-m",
            "evals.v1_baseline.benchmark_integrity_check",
            "--config",
            config,
            "--out",
            str(integrity_out),
            "--report-md",
            str(integrity_md),
            "--policy",
            policy,
            "--stage-b-gate-policy",
            args.stage_b_gate_policy,
        ]
        if args.strict_integrity or policy == "strict":
            integrity_cmd.append("--strict")
        _run(integrity_cmd, repo_root)

    run_records: list[dict] = []
    cmd = [
        "uv",
        "run",
        "python",
        "-m",
        "retrieval_lab.run_experiment",
    ]
    for spec in run_specs:
        print(f"--- Running [{spec.mode}] {spec.config_path} ---", flush=True)
        mode_cmd = [
            *cmd,
            "--config",
            spec.config_path,
            "--experiment-name",
            spec.experiment_name,
            "--output",
            str(out_dir),
            *spec.cli_overrides,
        ]
        if args.version:
            mode_cmd.extend(["--substrate-version", args.version])
        if args.seed is not None:
            mode_cmd.extend(["--seed", str(args.seed)])
        stdout = _run(mode_cmd, repo_root)
        experiment_id = _extract_experiment_id(stdout)
        if not experiment_id:
            continue
        run_dir = out_dir / experiment_id
        _patch_run_membership(run_dir=run_dir, freeze_metadata=freeze_metadata, mode=spec.mode)
        run_records.append(
            _build_run_record(
                run_dir=run_dir,
                corpus_id=spec.corpus_id,
                mode=spec.mode,
                experiment_id=experiment_id,
            )
        )

    canonical_index_path = out_dir / "canonical_runs_index.json"
    canonical_index = _build_canonical_index(run_records, canonical_index_path=canonical_index_path)
    canonical_index["baseline_package"] = {
        **freeze_metadata,
        "canonical_runs_index_sha256": "",
    }
    canonical_index_path.write_text(json.dumps(canonical_index, indent=2), encoding="utf-8")
    canonical_index["baseline_package"]["canonical_runs_index_sha256"] = sha256_file(canonical_index_path)
    canonical_index_path.write_text(json.dumps(canonical_index, indent=2), encoding="utf-8")

    bundle_hygiene = _collect_bundle_hygiene(out_dir, run_records)
    summary_payload = {
        "baseline_process": {
            "default_mode": MODE_C_RAW_FIRST_MERGE_RERANK,
            "include_comparators": include_comparators,
            "raw_stage1_admission_k": args.raw_stage1_admission_k,
            "raw_merge_coverage_bonus": args.raw_merge_coverage_bonus,
            "gating_integrity_policy": args.gating_integrity_policy,
            "stage_b_gate_policy": args.stage_b_gate_policy,
        },
        "baseline_package": {
            **freeze_metadata,
            "canonical_runs_index_path": str(canonical_index_path.resolve()),
            "canonical_runs_index_sha256": canonical_index["baseline_package"]["canonical_runs_index_sha256"],
        },
        "canonical_runs": canonical_index["canonical_runs"],
        "bundle_hygiene": bundle_hygiene,
        "runs": run_records,
    }
    summary_json.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    print(f"--- Wrote suite summary: {summary_json} ---", flush=True)
    print(f"--- Wrote canonical index: {canonical_index_path} ---", flush=True)


if __name__ == "__main__":
    main()

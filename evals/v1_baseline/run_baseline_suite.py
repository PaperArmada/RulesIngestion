"""Matrix runner for the v1 C-first baseline process."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from evals.v1_baseline.baseline_process import (
    CORPUS_SPECS,
    MODE_C_RAW_FIRST_MERGE_RERANK,
    build_baseline_run_specs,
)


def _load_metrics(metrics_path: Path) -> dict:
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    model = "all-mpnet-base-v2"
    if model not in payload:
        raise ValueError(f"{metrics_path} missing model key '{model}'")
    return payload[model]


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run v1 C-first baseline suite (optionally with A/B comparators)."
    )
    parser.add_argument("--out-dir", required=True, help="Output directory for run artifacts.")
    parser.add_argument("--version", default="v1", help="Substrate version, defaults to v1.")
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
    summary_json = Path(args.summary_json) if args.summary_json else (out_dir / "baseline_process_summary.json")

    # Integrity runs once per corpus config.
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
            "--audit-all-units",
            "--policy",
            policy,
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
            "--substrate-version",
            args.version,
            *spec.cli_overrides,
        ]
        if args.seed is not None:
            mode_cmd.extend(["--seed", str(args.seed)])
        stdout = _run(mode_cmd, repo_root)
        experiment_id = _extract_experiment_id(stdout)
        if experiment_id:
            metrics_path = out_dir / experiment_id / "metrics.json"
            record = {
                "corpus_id": spec.corpus_id,
                "mode": spec.mode,
                "experiment_id": experiment_id,
                "metrics_path": str(metrics_path) if metrics_path.exists() else None,
            }
            if metrics_path.exists():
                metrics = _load_metrics(metrics_path)
                diagnostics = metrics.get("raw_merge_rerank_diagnostics", {})
                record["metrics"] = {
                    "mrr": float(metrics.get("mrr", 0.0)),
                    "gold_in_candidates_true_ceiling": float(metrics.get("gold_in_candidates_true_ceiling", 0.0)),
                    "required_full_set_hit_at_10": _string_or_int_lookup(
                        metrics.get("required_full_set_hit_at_k", {}), 10
                    ),
                    "required_full_set_hit_at_20": _string_or_int_lookup(
                        metrics.get("required_full_set_hit_at_k", {}), 20
                    ),
                    "rank_of_last_required_mean": float(metrics.get("rank_of_last_required_mean", 0.0)),
                    "raw_merge_diagnostics": {
                        "enabled": bool(diagnostics.get("enabled", False)),
                        "monotonic_rank_violations_total": int(
                            diagnostics.get("monotonic_rank_violations_total", 0)
                        ),
                        "raw_top_missing_in_final_topk_total": int(
                            diagnostics.get("raw_top_missing_in_final_topk_total", 0)
                        ),
                    },
                }
            run_records.append(record)

    summary_payload = {
        "baseline_process": {
            "default_mode": MODE_C_RAW_FIRST_MERGE_RERANK,
            "include_comparators": include_comparators,
            "raw_stage1_admission_k": args.raw_stage1_admission_k,
            "raw_merge_coverage_bonus": args.raw_merge_coverage_bonus,
        },
        "runs": run_records,
    }
    summary_json.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    print(f"--- Wrote suite summary: {summary_json} ---", flush=True)


if __name__ == "__main__":
    main()

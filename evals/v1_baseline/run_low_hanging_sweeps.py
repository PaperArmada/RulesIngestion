"""Run low-hanging retrieval tuning sweeps and summarize outcomes."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class CorpusSpec:
    name: str
    config_path: str
    run_id: str


CORPORA: List[CorpusSpec] = [
    CorpusSpec("phb", "retrieval_lab/experiments/hybrid/phb_hybrid.yaml", "retrieval_lab_DnD_PHB_5.5_v1"),
    CorpusSpec("starfinder", "retrieval_lab/experiments/hybrid/starfinder_hybrid.yaml", "retrieval_lab_StarFinderPlayerCore_v1"),
    CorpusSpec("swords_wizardry", "retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml", "retrieval_lab_Swords&Wizardry_v1"),
]


def _run(cmd: List[str], cwd: Path) -> str:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="")
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
    return proc.stdout or ""


def _extract_experiment_id(stdout: str) -> str:
    m = re.search(r"Done\. Experiment ID:\s*([^\s]+)", stdout)
    if not m:
        raise RuntimeError("Could not extract experiment ID from run output.")
    return m.group(1).strip()


def _load_metrics(out_dir: Path, experiment_id: str) -> Dict[str, Any]:
    p = out_dir / experiment_id / "metrics.json"
    payload = json.loads(p.read_text(encoding="utf-8"))
    return payload.get("all-mpnet-base-v2", payload.get("bm25", next(iter(payload.values()))))


def _classify_sw_probe_change(baseline: Dict[str, int], candidate: Dict[str, int]) -> str:
    baseline_miss = int(baseline.get("gold_not_in_candidates", 0))
    candidate_miss = int(candidate.get("gold_not_in_candidates", 0))
    baseline_low_rank = int(baseline.get("gold_in_candidates_but_low_rank", 0))
    candidate_low_rank = int(candidate.get("gold_in_candidates_but_low_rank", 0))
    if candidate_miss < baseline_miss:
        return "coverage_gain"
    if candidate_miss == baseline_miss and candidate_low_rank != baseline_low_rank:
        return "rank_shuffle_only"
    return "no_material_change"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run low-hanging retrieval tuning sweeps.")
    parser.add_argument("--out-dir", required=True, help="Output directory for sweep runs.")
    parser.add_argument("--version", default="v1")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: Dict[str, Any] = {"rrf_sweeps": {}, "bm25_param_sweeps": {}, "bm25_query_expansion": {}, "sw_probes": {}}

    # RRF sweep across corpora
    for corpus in CORPORA:
        summary["rrf_sweeps"][corpus.name] = {}
        for rrf_k in (30, 60, 90):
            cmd = [
                "uv",
                "run",
                "python",
                "-m",
                "retrieval_lab.run_experiment",
                "--config",
                corpus.config_path,
                "--run-id",
                corpus.run_id,
                "--output",
                str(out_dir),
                "--substrate-version",
                args.version,
                "--seed",
                str(args.seed),
                "--rrf-k",
                str(rrf_k),
            ]
            exp_id = _extract_experiment_id(_run(cmd, repo_root))
            metrics = _load_metrics(out_dir, exp_id)
            summary["rrf_sweeps"][corpus.name][str(rrf_k)] = {
                "experiment_id": exp_id,
                "mrr": metrics.get("mrr", 0.0),
                "ndcg_at_10": (metrics.get("ndcg_at_k") or {}).get("10", 0.0),
                "failure_bucket_counts": metrics.get("failure_bucket_counts", {}),
            }

    # BM25 tokenizer/parameter sweep (hybrid mode to retain comparability with current defaults)
    bm25_param_grid = [
        ("basic", 1.5, 0.75),
        ("hyphenated", 1.2, 0.75),
        ("hyphenated", 1.5, 0.6),
    ]
    for corpus in CORPORA:
        summary["bm25_param_sweeps"][corpus.name] = {}
        for tokenizer_mode, k1, b in bm25_param_grid:
            label = f"{tokenizer_mode}_k1_{k1}_b_{b}"
            cmd = [
                "uv",
                "run",
                "python",
                "-m",
                "retrieval_lab.run_experiment",
                "--config",
                corpus.config_path,
                "--run-id",
                corpus.run_id,
                "--output",
                str(out_dir),
                "--substrate-version",
                args.version,
                "--seed",
                str(args.seed),
                "--bm25-tokenizer-mode",
                tokenizer_mode,
                "--bm25-k1",
                str(k1),
                "--bm25-b",
                str(b),
            ]
            exp_id = _extract_experiment_id(_run(cmd, repo_root))
            metrics = _load_metrics(out_dir, exp_id)
            summary["bm25_param_sweeps"][corpus.name][label] = {
                "experiment_id": exp_id,
                "mrr": metrics.get("mrr", 0.0),
                "gold_in_candidates": metrics.get("gold_in_candidates", 0.0),
                "failure_bucket_counts": metrics.get("failure_bucket_counts", {}),
            }

    # BM25 query expansion sweep (S&W focus)
    for mode in ("question_only", "question_plus_summary", "weighted"):
        cmd = [
            "uv",
            "run",
            "python",
            "-m",
            "retrieval_lab.run_experiment",
            "--config",
            "retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml",
            "--run-id",
            "retrieval_lab_Swords&Wizardry_v1",
            "--output",
            str(out_dir),
            "--substrate-version",
            args.version,
            "--seed",
            str(args.seed),
            "--bm25-query-mode",
            mode,
            "--bm25-tokenizer-mode",
            "hyphenated",
            "--bm25-k1",
            "1.2",
            "--bm25-b",
            "0.75",
        ]
        if mode == "weighted":
            cmd.extend(["--bm25-query-weight-question", "2", "--bm25-query-weight-summary", "1"])
        exp_id = _extract_experiment_id(_run(cmd, repo_root))
        metrics = _load_metrics(out_dir, exp_id)
        summary["bm25_query_expansion"][mode] = {
            "experiment_id": exp_id,
            "mrr": metrics.get("mrr", 0.0),
            "gold_in_candidates": metrics.get("gold_in_candidates", 0.0),
            "failure_bucket_counts": metrics.get("failure_bucket_counts", {}),
        }

    # S&W targeted sidecar/pairing probes
    probe_commands = {
        "baseline": [],
        "pairing_only": ["--dependency-pairing-expand"],
        "sidecar_only": ["--crossref-sidecar-expand"],
        "pairing_plus_sidecar": ["--dependency-pairing-expand", "--crossref-sidecar-expand"],
    }
    probe_results: Dict[str, Dict[str, Any]] = {}
    for probe_name, extra_flags in probe_commands.items():
        cmd = [
            "uv",
            "run",
            "python",
            "-m",
            "retrieval_lab.run_experiment",
            "--config",
            "retrieval_lab/experiments/hybrid/swords_wizardry_hybrid_dual_list_fusion.yaml",
            "--run-id",
            "retrieval_lab_Swords&Wizardry_v1",
            "--output",
            str(out_dir),
            "--substrate-version",
            args.version,
            "--seed",
            str(args.seed),
        ] + extra_flags
        exp_id = _extract_experiment_id(_run(cmd, repo_root))
        metrics = _load_metrics(out_dir, exp_id)
        probe_results[probe_name] = {
            "experiment_id": exp_id,
            "mrr": metrics.get("mrr", 0.0),
            "failure_bucket_counts": metrics.get("failure_bucket_counts", {}),
        }

    baseline_fb = probe_results["baseline"]["failure_bucket_counts"]
    for probe_name, payload in probe_results.items():
        payload["classification_vs_baseline"] = _classify_sw_probe_change(
            baseline_fb,
            payload["failure_bucket_counts"],
        )
    summary["sw_probes"] = probe_results

    summary_path = out_dir / "LOW_HANGING_SWEEP_SUMMARY.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote sweep summary: {summary_path}")


if __name__ == "__main__":
    main()

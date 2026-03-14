#!/usr/bin/env python3
"""
Run the ready-rulesets atomic benchmark sweep end-to-end.

Usage (from RulesIngestion root):
  uv run python scripts/run_atomic_ready_sweep.py

Examples:
  uv run python scripts/run_atomic_ready_sweep.py --dry-run
  uv run python scripts/run_atomic_ready_sweep.py --corpora pf2e phb5e
  uv run python scripts/run_atomic_ready_sweep.py --preflight-only
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


RUN_ID_PATTERN = re.compile(r"run_id=([^\s]+)")


@dataclass(frozen=True)
class CorpusConfig:
    slug: str
    label: str
    config_path: str
    benchmark_path: str
    substrate_path: str
    substrate_version: str
    embed_experiment_name: str
    eval_experiment_name: str


READY_CORPORA: tuple[CorpusConfig, ...] = (
    CorpusConfig(
        slug="pf2e",
        label="Pathfinder 2e Player Core",
        config_path="retrieval_lab/experiments/dense/pf2e_atomic_rules.yaml",
        benchmark_path="evals/retrieval/Pathfinder2ePlayerCore/pathfinder2e_player_core_atomic_rules_benchmark.json",
        substrate_path="out/Pathfinder2ePlayerCore",
        substrate_version="v2_merged2000_min200",
        embed_experiment_name="pf2e_player_core_atomic_rules_embed",
        eval_experiment_name="pf2e_player_core_atomic_rules_eval",
    ),
    CorpusConfig(
        slug="phb5e",
        label="D&D 5e 2024 Player's Handbook",
        config_path="retrieval_lab/experiments/dense/phb5e_atomic_rules.yaml",
        benchmark_path="evals/retrieval/PHB5e/dnd_5e_2024_atomic_rules_benchmark.v2_merged2000_min200.json",
        substrate_path="out/DnD_PHB_5.5",
        substrate_version="v2_merged2000_min200",
        embed_experiment_name="phb5e_2024_atomic_rules_embed",
        eval_experiment_name="phb5e_2024_atomic_rules_eval",
    ),
    CorpusConfig(
        slug="shadowrun4e",
        label="ShadowRun 4e Anniversary",
        config_path="retrieval_lab/experiments/dense/shadowrun4e_atomic_rules.yaml",
        benchmark_path="evals/retrieval/ShadowRun4e/shadowrun4e_anniversary_atomic_rules_benchmark.json",
        substrate_path="out/mark3_evaluation/CAT2600A_SR4Anniversary",
        substrate_version="v2_merged2000_min200",
        embed_experiment_name="shadowrun4e_anniversary_atomic_rules_embed",
        eval_experiment_name="shadowrun4e_anniversary_atomic_rules_eval",
    ),
    CorpusConfig(
        slug="swcr",
        label="Swords & Wizardry Complete Revised",
        config_path="retrieval_lab/experiments/dense/swcr_atomic_rules.yaml",
        benchmark_path="evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_atomic_rules_benchmark.v3_swcr_merged2000_min100.json",
        substrate_path="out/Swords&Wizardry/SW_Complete_Revised/SW Complete Revised PDF",
        substrate_version="v3_swcr_merged2000_min100",
        embed_experiment_name="swcr_complete_revised_atomic_rules_embed",
        eval_experiment_name="swcr_complete_revised_atomic_rules_eval",
    ),
)


def _run_command(command: list[str], cwd: Path, dry_run: bool) -> str:
    pretty = " ".join(command)
    print(f"$ {pretty}")
    if dry_run:
        return ""
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    return f"{result.stdout}\n{result.stderr}"


def _extract_run_id(output: str) -> str:
    matches = RUN_ID_PATTERN.findall(output)
    if not matches:
        raise SystemExit("Could not parse run_id from embed output.")
    return matches[-1]


def _ensure_exists(path: Path, description: str) -> None:
    if not path.exists():
        raise SystemExit(f"Missing {description}: {path}")


def _run_preflight(repo_root: Path, corpus: CorpusConfig, dry_run: bool) -> None:
    print(f"\n## Preflight: {corpus.label}")
    _ensure_exists(repo_root / corpus.substrate_path, "substrate path")
    _ensure_exists(repo_root / corpus.config_path, "config path")
    _ensure_exists(repo_root / corpus.benchmark_path, "benchmark path")
    _run_command(
        [
            "uv",
            "run",
            "python",
            "-m",
            "retrieval_lab.benchmark_lint",
            corpus.benchmark_path,
        ],
        cwd=repo_root,
        dry_run=dry_run,
    )


def _run_embed(repo_root: Path, corpus: CorpusConfig, dry_run: bool) -> str:
    print(f"\n## Embed: {corpus.label}")
    output = _run_command(
        [
            "uv",
            "run",
            "python",
            "-m",
            "retrieval_lab.run_experiment",
            "--config",
            corpus.config_path,
            "--experiment-name",
            corpus.embed_experiment_name,
            "--embed-only",
        ],
        cwd=repo_root,
        dry_run=dry_run,
    )
    if dry_run:
        return "<dry-run>"
    run_id = _extract_run_id(output)
    print(f"Parsed run_id: {run_id}")
    return run_id


def _run_eval(repo_root: Path, corpus: CorpusConfig, run_id: str, dry_run: bool) -> None:
    print(f"\n## Eval: {corpus.label}")
    _run_command(
        [
            "uv",
            "run",
            "python",
            "-m",
            "retrieval_lab.run_experiment",
            "--config",
            corpus.config_path,
            "--experiment-name",
            corpus.eval_experiment_name,
            "--run-id",
            run_id,
        ],
        cwd=repo_root,
        dry_run=dry_run,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the atomic benchmark sweep across the ready rulesets."
    )
    parser.add_argument(
        "--corpora",
        nargs="+",
        choices=[corpus.slug for corpus in READY_CORPORA],
        default=[corpus.slug for corpus in READY_CORPORA],
        help="Subset of ready corpora to run.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run substrate/config/benchmark checks and benchmark lint only.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them.",
    )
    parser.add_argument(
        "--write-summary",
        type=Path,
        default=None,
        help="Optional path to write a JSON summary of selected corpora and parsed run_ids.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    selected = [corpus for corpus in READY_CORPORA if corpus.slug in set(args.corpora)]
    summary: list[dict[str, str]] = []

    for corpus in selected:
        _run_preflight(repo_root, corpus, dry_run=args.dry_run)
        if args.preflight_only:
            summary.append(
                {
                    "corpus": corpus.slug,
                    "label": corpus.label,
                    "status": "preflight_only",
                    "benchmark_path": corpus.benchmark_path,
                    "config_path": corpus.config_path,
                    "substrate_path": corpus.substrate_path,
                    "substrate_version": corpus.substrate_version,
                }
            )
            continue

        run_id = _run_embed(repo_root, corpus, dry_run=args.dry_run)
        _run_eval(repo_root, corpus, run_id=run_id, dry_run=args.dry_run)
        summary.append(
            {
                "corpus": corpus.slug,
                "label": corpus.label,
                "run_id": run_id,
                "config_path": corpus.config_path,
                "benchmark_path": corpus.benchmark_path,
                "substrate_path": corpus.substrate_path,
                "substrate_version": corpus.substrate_version,
            }
        )

    if args.write_summary is not None:
        args.write_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nWrote summary: {args.write_summary}")

    print("\nSweep complete.")


if __name__ == "__main__":
    main()

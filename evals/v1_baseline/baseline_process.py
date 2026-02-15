"""Reusable baseline process plan for v1 retrieval experiments.

This module defines the C-first baseline process and optional A/B comparator
modes so callers can run a consistent matrix from CLI scripts or library code.
"""

from __future__ import annotations

from dataclasses import dataclass


MODE_A_RAW_ONLY = "a_raw_only"
MODE_B_MERGED_ONLY = "b_merged_only"
MODE_C_RAW_FIRST_MERGE_RERANK = "c_raw_first_merge_rerank"


@dataclass(frozen=True)
class CorpusSpec:
    corpus_id: str
    config_path: str
    top_k_max: int
    integrity_policy: str = "strict"


@dataclass(frozen=True)
class BaselineRunSpec:
    corpus_id: str
    mode: str
    config_path: str
    experiment_name: str
    top_k_max: int
    cli_overrides: tuple[str, ...]


CORPUS_SPECS: tuple[CorpusSpec, ...] = (
    CorpusSpec(
        corpus_id="phb",
        config_path="retrieval_lab/experiments/hybrid/phb_hybrid.yaml",
        top_k_max=20,
        integrity_policy="strict",
    ),
    CorpusSpec(
        corpus_id="starfinder",
        config_path="retrieval_lab/experiments/hybrid/starfinder_hybrid.yaml",
        top_k_max=20,
        integrity_policy="strict",
    ),
    CorpusSpec(
        corpus_id="swords_wizardry",
        config_path="retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml",
        top_k_max=50,
        integrity_policy="strict",
    ),
)


def mode_sequence(include_comparators: bool) -> tuple[str, ...]:
    if include_comparators:
        return (
            MODE_A_RAW_ONLY,
            MODE_B_MERGED_ONLY,
            MODE_C_RAW_FIRST_MERGE_RERANK,
        )
    return (MODE_C_RAW_FIRST_MERGE_RERANK,)


def build_mode_overrides(
    *,
    mode: str,
    top_k_max: int,
    raw_stage1_admission_k: int,
    raw_merge_coverage_bonus: float,
) -> tuple[str, ...]:
    if mode == MODE_A_RAW_ONLY:
        return (
            "--no-merge-chunks",
        )
    if mode == MODE_B_MERGED_ONLY:
        return (
            "--merge-chunks",
        )
    if mode == MODE_C_RAW_FIRST_MERGE_RERANK:
        return (
            "--no-merge-chunks",
            "--raw-first-merge-rerank",
            "--raw-stage1-admission-k",
            str(raw_stage1_admission_k),
            "--raw-merge-rerank-top-k",
            str(top_k_max),
            "--raw-merge-score-floor",
            "--raw-merge-rank-floor",
            "--raw-merge-coverage-bonus",
            str(raw_merge_coverage_bonus),
            "--two-stage-retrieval",
            "--stage2-rerank-method",
            "dense",
        )
    raise ValueError(f"Unknown baseline mode: {mode}")


def build_baseline_run_specs(
    *,
    include_comparators: bool,
    raw_stage1_admission_k: int,
    raw_merge_coverage_bonus: float,
) -> list[BaselineRunSpec]:
    specs: list[BaselineRunSpec] = []
    for corpus in CORPUS_SPECS:
        for mode in mode_sequence(include_comparators):
            overrides = build_mode_overrides(
                mode=mode,
                top_k_max=corpus.top_k_max,
                raw_stage1_admission_k=raw_stage1_admission_k,
                raw_merge_coverage_bonus=raw_merge_coverage_bonus,
            )
            specs.append(
                BaselineRunSpec(
                    corpus_id=corpus.corpus_id,
                    mode=mode,
                    config_path=corpus.config_path,
                    experiment_name=f"{corpus.corpus_id}_hybrid_{mode}",
                    top_k_max=corpus.top_k_max,
                    cli_overrides=overrides,
                )
            )
    return specs

# v1 Baseline Suite

**Purpose:** Reproducible baseline runs across all books for Stage A/B v1. "Baseline" refers to the outputs under this directory (or a dated subdirectory), not ad-hoc older runs.

## Suite definition

- **PHB (D&D 5e):** substrate `out/mark3_evaluation/DnD_PHB_5.5`, configs `phb_hybrid.yaml` (baseline) and `phb_hybrid_dual_list_fusion.yaml` (production default).
- **Starfinder 2e Player Core:** substrate and configs in `retrieval_lab/experiments/hybrid/starfinder_hybrid.yaml` (and dense/sparse as applicable).
- **Swords & Wizardry:** substrate and configs in `retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml`.

## How to run the baseline suite

1. Ensure substrate is built (Stage A + B output) for each corpus. See [Docs/Design/v1/baseline_manifest.md](../../Docs/Design/v1/baseline_manifest.md).
2. From repo root:
   - PHB baseline: `uv run python -m retrieval_lab.run_experiment --config retrieval_lab/experiments/hybrid/phb_hybrid.yaml --output out/retrieval_lab/stage_a_and_b`
   - PHB dual-list (default): `uv run python -m retrieval_lab.run_experiment --config retrieval_lab/experiments/hybrid/phb_hybrid_dual_list_fusion.yaml --output out/retrieval_lab/stage_a_and_b`
   - Repeat for Starfinder and S&W configs with the same output dir or a dated dir under `evals/v1_baseline/<date_or_tag>/`.
3. Save run outputs under `evals/v1_baseline/<date_or_tag>/` (e.g. copy from `out/retrieval_lab/...` or set `output_dir` in config to point here).
4. Regenerate comparison report when comparing baseline vs dual-list vs pairing; see [Docs/Design/v1/retrieval_lab_v1.md](../../Docs/Design/v1/retrieval_lab_v1.md).

## Default config per corpus

| Corpus | Default config (production) | Baseline for comparison |
|--------|-----------------------------|--------------------------|
| PHB    | phb_hybrid_dual_list_fusion.yaml | phb_hybrid.yaml |
| Starfinder | starfinder_hybrid.yaml (dual-list if added) | starfinder_hybrid.yaml |
| S&W    | swords_wizardry_hybrid.yaml | swords_wizardry_hybrid.yaml |

See [Docs/Design/v1/retrieval_lab_v1.md](../../Docs/Design/v1/retrieval_lab_v1.md) for full run instructions and regression policy.

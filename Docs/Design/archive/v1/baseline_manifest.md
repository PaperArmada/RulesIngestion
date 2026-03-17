# Stage A/B v1 Baseline Manifest

**Purpose:** Canonical reference for building, replaying, and auditing the ratifiable Stage A/B baseline package.

---

## 1. Canonical Package Location

The ratifiable baseline package lives under:

- `evals/v1_baseline/<STAMP>/`

Where `<STAMP>` is the archived package identifier (typically a date or dated tag). The package is not ratified unless the directory exists and contains both:

- suite-level integrity artifacts
- per-run retrieval artifacts for every baseline run

When the package is finalized, the suite should emit these freeze fields into the archived package metadata:

- `baseline_commit_sha`
- `baseline_tag` (optional)
- `baseline_package_dir`
- `python_version`
- `uv_lock_sha256`

---

## 2. Corpus / Config Matrix

| Corpus | Document ID | Substrate path | Baseline config |
|--------|-------------|----------------|-----------------|
| PHB | `DnD_PHB_5.5` | `out/DnD_PHB_5.5` | `retrieval_lab/experiments/hybrid/phb_hybrid.yaml` |
| Starfinder | `StarFinderPlayerCore` | `out/StarFinderPlayerCore` | `retrieval_lab/experiments/hybrid/starfinder_hybrid.yaml` |
| S&W | `Swords&Wizardry` | `out/Swords&Wizardry` | `retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml` |

The baseline suite runs mode `C` as canonical and may include comparator modes `A` and `B`.

For any archived baseline or recommendation-grade run, freeze:

- `substrate_path`
- `document_id`
- `substrate_version`
- `corpus_fingerprint`
- `corpus_content_fingerprint`
- `corpus_index_sha256`
- `corpus_recipe`

---

## 3. Required Package Contents

### Suite root

Every ratifiable package root `evals/v1_baseline/<STAMP>/` must contain:

- `baseline_process_summary.json`
- `canonical_runs_index.json`
- `integrity_<config>.json`
- `integrity_<config>.md`
- replay/determinism reports produced by `scripts/assert_corpus_replay_determinism.py`

The suite root metadata must also identify:

- the frozen package directory and stamp
- git commit SHA and optional exact tag
- Python version
- `uv.lock` path and SHA-256
- which run directories are canonical package members versus non-canonical retry/history directories

### Per-run directory

Every baseline run directory `evals/v1_baseline/<STAMP>/<experiment_id>/` must contain:

- `benchmark_contract_validation.json`
- `benchmark.<surface>.json`
- `benchmark.<surface>.contract.json`
- `manifest.json`
- `run_manifest.json`
- `prod_readiness.json`
- `embeddings/corpus_index.json`

`prod_readiness.json` is required for a ratified package. If a run is contract-invalid and cannot emit `prod_readiness.json`, that run is not eligible to serve as the archived baseline.

For canonical baseline members, `run_manifest.json` and `prod_readiness.json` must both include:

- bundle membership back to the archived package
- canonical/non-canonical role labeling
- the same freeze metadata emitted at the suite root

---

## 4. Strict Build / Replay Commands

### Build the baseline suite

```bash
uv run python -m evals.v1_baseline.run_baseline_suite \
  --out-dir "evals/v1_baseline/<STAMP>" \
  --c-only \
  --strict-integrity \
  --gating-integrity-policy strict \
  --stage-b-gate-policy strict
```

### Assert corpus replay determinism

Run once per corpus config and archive the JSON outputs in the package root:

```bash
uv run python scripts/assert_corpus_replay_determinism.py \
  --config retrieval_lab/experiments/hybrid/phb_hybrid.yaml \
  --no-merge-chunks \
  --out "evals/v1_baseline/<STAMP>/replay_phb_hybrid.json"
```

Repeat for:

- `retrieval_lab/experiments/hybrid/starfinder_hybrid.yaml`
- `retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml`

### Regression assertion

```bash
uv run python -m evals.v1_baseline.assert_baseline_regression \
  --summary "evals/v1_baseline/<STAMP>/baseline_process_summary.json"
```

---

## 5. Environment Fingerprint

- **Python:** `>=3.13` (matches `pyproject.toml`)
- **OS:** Linux preferred for archived ratification builds
- **Dependency lock:** repo-root `uv.lock`
- **Package manager:** `uv`

Determinism is expected from:

- stable Stage A serialization
- Stage B ordering keyed by page-local provenance and `ordering_key`
- numeric page loading in Retrieval Lab
- contract-validated benchmark projections

---

## 6. Ratification Policy

A package is eligible for ratification only if all of the following are true:

1. Integrity checks pass in strict mode.
2. Stage B gate policy is run in `strict` mode with zero failing pages and no missing gate diagnostics.
3. Replay determinism reports show matching corpus fingerprints and zero page inversions.
4. Required artifact files exist in every archived run directory.
5. `prod_readiness.json` exists and is contract-valid for the canonical baseline runs.
6. `canonical_runs_index.json` points at the same canonical runs and selected surfaces as the per-run `prod_readiness.json` files.
7. Any retained retry/history run directories are explicitly labeled as non-canonical by suite-root metadata and are not required to be consumed by downstream tooling.

If any of the above are missing, the package is not the v1 ratified baseline.

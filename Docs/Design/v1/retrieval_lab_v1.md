# Retrieval Lab v1

**Purpose:** Measure discoverability of evidence under a given retrieval regime. Authority-free, semantics-free, comparative by design. Not a correctness evaluator.

---

## 1. How to Run Evals

From repo root (RulesIngestion):

```bash
uv run python -m retrieval_lab.run_experiment --config <CONFIG_YAML> [OPTIONS]
```

**Two-step (recommended):** Embed once with `--embed-only`, then run eval with `--run-id <RUN_ID>`. Full run (embed if missing + eval): omit `--embed-only` and `--run-id`.

**Contract model (current):**

- The checked-in benchmark JSON is the benchmark definition unless it is already an explicitly materialized projection.
- The scored benchmark artifact inside a run directory is the benchmark projection.
- Eval-only requires the active projection contract to match the active corpus contract.

**Key options:** `--embed-only`, `--run-id`, `--substrate-version`, `--trust-remote-code` (for nomic-embed-text-v2, bge-m3, gte-multilingual-base), `--no-reuse-embeddings`.

**Config:** YAML under `retrieval_lab/experiments/` (dense, sparse, hybrid). Specify substrate_path, document_id, query_batches, models, top_k, output_dir, etc.

---

## 2. Config Model and Happy Path

- **Knobs:** retrieval_mode (sparse | dense | hybrid), dual_list_fusion (bool), dual_list_ku/kf/kfinal/qu, family_window, family_max_units, pairing (experimental), gold_semantic_top_n, gold_jaccard_threshold, batch_size, reuse_embeddings, mongo_uri.
- **Happy path (PHB default):** `phb_hybrid_dual_list_fusion.yaml` — hybrid with dual-list fusion. Baseline for comparison: `phb_hybrid.yaml` (no dual-list). Experimental: `phb_hybrid_dual_list_fusion_plus_pairing.yaml` (instrumented; not yet proven).

---

## 3. Output Directory Conventions

- **General runs:** `output_dir` in config (for example `out/retrieval_lab/experiments`).
- **Ratified baseline packages:** `evals/v1_baseline/<STAMP>/`.
- Each run writes a directory `<experiment_id>/` containing:
  - `experiment.json` config and result snapshot
  - `embeddings/corpus_index.json` with:
    - `corpus_fingerprint`
    - `corpus_content_fingerprint`
    - `unit_id_to_index`
    - ordered corpus records
    - `corpus_recipe`
  - `benchmark_contract_validation.json`
  - scored benchmark projection artifacts:
    - `benchmark.<surface>.json`
    - `benchmark.<surface>.contract.json`
  - report/metric artifacts:
    - `REPORT.md`
    - `metrics.json` or `metrics.<surface>.json`
    - `per_query.json` or `per_query.<surface>.json`
    - `failure_buckets.json` or `failure_buckets.<surface>.json`
    - `retrieved_chunks.json` or `retrieved_chunks.<surface>.json`
    - `grounding_audit.json`
  - reproducibility artifacts:
    - `manifest.json`
    - `run_manifest.json`
    - `prod_readiness.json` for contract-valid promotion candidates
  - diagnostics (failure bucket summary, optional diagnostics subdir)
- In a ratified baseline package, the suite root also contains:
  - `baseline_process_summary.json`
  - `canonical_runs_index.json`
  - `integrity_<config>.json`
  - `integrity_<config>.md`
  - replay reports from `scripts/assert_corpus_replay_determinism.py`
  - suite-level freeze metadata and bundle hygiene classification inside `baseline_process_summary.json`
- Comparison reports remain optional ad hoc artifacts and are not part of the ratification package contract.

### Surface behavior

- Runs without auto-gold review use one active surface and may emit `metrics.json` / `per_query.json`.
- Runs with auto-gold review emit explicit surfaces such as `pre_review_manual` and `post_review_applied`.
- When multiple surfaces exist, there is intentionally no unlabeled `metrics.json` or `per_query.json`.
- Downstream consumers must resolve the selected scoring surface from `prod_readiness.json.selected_surface` first, then fall back to `evaluation_surfaces.json` if they need to locate `metrics.<surface>.json`, `per_query.<surface>.json`, or `retrieved_chunks.<surface>.json`.

---

## 4. Comparison Protocol and Required Metrics

- **Compare baseline vs dual-list vs dual-list+pairing:** Use `retrieval_lab.compare_baseline_dual_list_pairing` with `--baseline`, `--dual-list`, `--pairing`, `--output`.
- **Required metrics:** MRR, T1 MRR, T1 regressions (vs baseline), T2 Hit@10, T2 Full-set@10, N grounded. Per-query: first_gold_rank, failure_bucket, tier.

### Contract-valid comparison rule

Do not compare two runs unless the benchmark surface and corpus contract are both explicit and valid.

Minimum comparison evidence:

- matching intended benchmark definition,
- matching benchmark surface semantics,
- a valid benchmark projection contract for each run,
- a valid `corpus_index.json` identity for each run.

---

## 5. Failure Bucket Dashboard

- Every run must produce failure bucket counts and per-query classification.
- **Buckets:** no_gold_defined, gold_not_in_candidates, gold_in_candidates_but_low_rank, grounding_or_answer_failure_after_retrieval, success.
- Stored in run directory (e.g. failure_buckets.json or within per_query.json + diagnostics). See [schema_registry.md](schema_registry.md).

---

## 6. Regression Policy

- **T1 regressions:** For dual-list fusion (and dual-list+pairing), T1 regression count vs baseline must remain **0** unless explicitly waived by an ADR.
- Baseline is the canonical hybrid run (e.g. phb_hybrid_20260211_212748). Comparison report and CI enforce no T1 regressions.

---

## 7. Baseline Suite (v1)

- **Baseline suite:** PHB + Starfinder + S&W saved under `evals/v1_baseline/<STAMP>/`.
- Canonical ratification command:

```bash
uv run python -m evals.v1_baseline.run_baseline_suite \
  --out-dir "evals/v1_baseline/<STAMP>" \
  --c-only \
  --strict-integrity \
  --gating-integrity-policy strict \
  --stage-b-gate-policy strict
```

- After the suite runs, archive replay reports for each corpus config with `scripts/assert_corpus_replay_determinism.py`.
- Default config per corpus: `phb_hybrid.yaml`, `starfinder_hybrid.yaml`, `swords_wizardry_hybrid.yaml`. The archived package, not an old `out/retrieval_lab/...` directory, is the canonical baseline reference.

## 8. Promotion artifact

Production recommendation should key off `prod_readiness.json`, not an informal run name.

`prod_readiness.json` identifies:

- the exact `run_id`,
- the selected benchmark surface,
- the selected model,
- the benchmark projection path/hash,
- the benchmark contract path/hash,
- the corpus fingerprint,
- the corpus content fingerprint,
- the corpus index hash,
- whether contract validation passed.
- the archived baseline package membership and canonical/non-canonical role when the run belongs to a ratified bundle.

For ratified baseline bundles, `canonical_runs_index.json` is the authoritative package-level list of canonical runs. Downstream Stage C/D work should begin from those entries, not from an arbitrary run directory.

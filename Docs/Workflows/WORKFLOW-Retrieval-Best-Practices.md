# Workflow: Retrieval Best Practices

This workflow is the canonical retrieval runbook for Starfinder + S&W.

Goal: run reproducible retrieval experiments with clear defaults, explicit run contracts, and evidence-backed recommendations.

---

## 1) Prerequisite ingestion policy

Use `Stage A+B` substrate as the default retrieval substrate.

- For hybrid retrieval tuning, run ingestion as `--stage ab` first.
- Run Stage A' separately only when evaluating enrichment effects.
- Keep substrate fixed while tuning retrieval knobs.

Reference: `Docs/Workflows/WORKFLOW-Ingestion-Best-Practices.md`.

---

## 2) Canonical naming and path contract

- Use `SwordsandWizardry` in benchmark/config/report naming.
- Treat `SwordsandWizardy` as legacy typo only.
- Canonical S&W substrate path (Complete Revised): `out/Swords&Wizardry/SW_Complete_Revised/SW Complete Revised PDF`.
- Canonical S&W benchmark: `evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_benchmark.json`.

---

## 3) Benchmarks and reasoning

Use benchmarks intentionally. Do not use one benchmark for every question.

| Corpus | Benchmark | Primary use | Reasoning |
|---|---|---|---|
| Starfinder | `evals/retrieval/StarFinderPlayerCore/starfinder_player_core_atomic_rules_benchmark.json` | Fast structural regression checks | Atomic queries are narrow and expose ranking regressions quickly. |
| Starfinder | `evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json` | Main quality gate for recommendation decisions | Balanced breadth and runtime; large enough to avoid overfitting to tiny sets. |
| S&W | `evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_benchmark.json` | Main quality gate for recommendation decisions | Current canonical revised benchmark with curated anchors and harder retrieval coverage. |

### Benchmark progression (recommended)

1. **Smoke/iteration:** run atomic (Starfinder) first for rapid signal.
2. **Primary comparison:** run corpus-level benchmark (`50q` for Starfinder, complete revised for S&W).
3. **Recommendation lock-in:** require primary-benchmark results plus per-query wins/losses before changing defaults.

### Benchmark discipline

- Use the same benchmark file across all conditions in a comparison slice.
- Do not mix legacy S&W benchmark paths in the same matrix.
- If you override `--batches` on the CLI, the override is authoritative for that run (and should be recorded in notes/results).

---

## 4) Canonical retrieval protocol (always)

1. Run `embed-only` first.
2. Capture `run_id` from embed output.
3. Materialize or validate the benchmark projection for the exact corpus you are scoring.
4. Run `eval-only` with the same `run_id`.
5. Keep `(corpus, model, recipe mode, enrichment profile)` stable per comparison slice.

Never compare two runs if both substrate and retrieval knobs changed.

### 4.1 Benchmark contract discipline

- Treat the checked-in benchmark JSON as the benchmark definition unless it is already an explicitly materialized projection.
- Treat the scored `benchmark.<surface>.json` artifact inside a run directory as the benchmark projection for that exact run corpus.
- Require benchmark validation to pass against the active:
  - `run_id`
  - `substrate_version`
  - `corpus_fingerprint`
  - `corpus_content_fingerprint`
  - `corpus_index_sha256`
  - benchmark surface
- If chunk topology changes, require a new projection. Do not reuse an old projection contract across changed `min_chars`, `merge_chunks`, `merge_max_chars`, or other corpus-shaping changes.

### 4.2 Corpus contract discipline

The run corpus contract is now stronger than "same run name".

- `embeddings/corpus_index.json` is the canonical corpus identity artifact.
- The corpus contract now includes both:
  - `corpus_fingerprint` for ordered chunk IDs
  - `corpus_content_fingerprint` for ordered chunk content/path/source lineage
- The corpus contract also records the applied `corpus_recipe`.
- Eval-only embedding reuse should be treated as invalid if any of those identity checks drift.

---

## 5) Canonical defaults vs optional vs experimental

### 5.1 Defaults (baseline)

- `retrieval_mode=hybrid`
- `hybrid_fusion_method=cc`
- `cc_bm25_normalization=minmax`
- `cc_lambda=0.7`
- `model=all-mpnet-base-v2`
- `seed=42`
- `recipe-mode=standardized`
- `embedding_enrichment_profile=baseline|none`
- `co_retrieval_expand=false`

### 5.2 Validated optional knobs

- `recipe-mode=recommended` (parallel tracked variant)
- `embedding_enrichment_profile=full`
- `co_retrieval_expand=true`
- `a_prime_generate_minimal=true` only when A' payloads are absent/incomplete
- `bm25_budget=200` / `dense_budget=200` for Starfinder-like corpora
- `bm25_budget=100` / `dense_budget=100` for SWCR-like corpora

### 5.3 Experimental knobs

- `hybrid_fusion_method=rrf` for dense+BM25 parity checks only
- `cc_bm25_normalization=atan`
- `cc_lambda` values outside the validated default path unless isolated in a sweep
- New enrichment profiles beyond baseline/full
- New rerank/co-expansion heuristics not yet validated
- Any setting change that is not isolated in a controlled matrix

### 5.4 Reasoning behind defaults

- `retrieval_mode=hybrid` is default because dense+lexical fusion is generally more robust to wording drift than dense-only or sparse-only in isolation.
- `hybrid_fusion_method=cc` is default because the March 2026 hybrid bakeoff confirmed CC is the architecture we should keep; dense+BM25 RRF is comparison-only.
- `cc_bm25_normalization=minmax` is default because it beat `atan` in most model/corpus head-to-heads.
- `cc_lambda=0.7` is the safest single default across corpora; use higher lambda only as an explicit corpus/model-specific variant.
- `all-mpnet-base-v2` is default because it is the current stable baseline used across recent bakeoff comparisons.
- `seed=42` is fixed to reduce run-to-run noise and make per-condition deltas interpretable.
- `recipe-mode=standardized` is default for comparability; `recommended` is tracked as an explicit variant, not mixed into baseline.
- `embedding_enrichment_profile=baseline|none` keeps baseline attribution clean; enrichment profiles are added only as controlled deltas.
- `co_retrieval_expand=false` at baseline prevents expansion-side effects from masking core retrieval behavior.
- `A+B first, A' second` minimizes iteration cost and isolates retrieval tuning from expensive enrichment generation.

### 5.5 Hybrid policy notes

- Treat `retrieval_lab/experiments/hybrid/starfinder_hybrid.yaml` and `retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml` as the canonical default configs.
- Do not pass `--hybrid-fusion-method`, `--cc-lambda`, or `--cc-bm25-normalization` on baseline runs unless you are intentionally doing a comparison slice.
- Treat `retrieval_lab/experiments/hybrid_bakeoff/*` as comparison configs, not baseline configs.
- Treat SWCR BM25 enrichment as untrusted until `bm25_index_trace.json` proves the enrichment text changed the indexed corpus (`profile_noop=false`).
- Production `ruleslawyer` keeps graph boost as a service-local post-fusion step; Retrieval Lab bakeoff guidance governs the base dense+BM25 fusion policy, not that extra production-only boost.

---

## 6) Canonical command paths by corpus

Run from `RulesIngestion` root.

### 5.1 Starfinder: embed-only (baseline hybrid path)

```bash
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/hybrid/starfinder_hybrid.yaml \
  --models all-mpnet-base-v2 \
  --recipe-mode standardized \
  --batches evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json \
  --experiment-name retrieval_sf_hybrid_baseline_std \
  --embed-only \
  --seed 42
```

This config already pins the validated default hybrid policy:
- `hybrid_fusion_method=cc`
- `cc_bm25_normalization=minmax`
- `cc_lambda=0.7`
- `bm25_budget=200`
- `dense_budget=200`

### 5.2 Starfinder: eval-only

```bash
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/hybrid/starfinder_hybrid.yaml \
  --models all-mpnet-base-v2 \
  --recipe-mode standardized \
  --run-id <RUN_ID_FROM_EMBED_STEP> \
  --batches evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json \
  --experiment-name retrieval_sf_hybrid_baseline_std_eval \
  --seed 42
```

### 5.3 S&W: embed-only (baseline hybrid path)

```bash
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml \
  --models all-mpnet-base-v2 \
  --recipe-mode standardized \
  --batches evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_benchmark.json \
  --experiment-name retrieval_sw_hybrid_baseline_std \
  --embed-only \
  --seed 42
```

This config already pins the validated default hybrid policy:
- `hybrid_fusion_method=cc`
- `cc_bm25_normalization=minmax`
- `cc_lambda=0.7`
- `bm25_budget=100`
- `dense_budget=100`

### 5.4 S&W: eval-only

```bash
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml \
  --models all-mpnet-base-v2 \
  --recipe-mode standardized \
  --run-id <RUN_ID_FROM_EMBED_STEP> \
  --batches evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_benchmark.json \
  --experiment-name retrieval_sw_hybrid_baseline_std_eval \
  --seed 42
```

---

## 7) Enrichment/co-retrieval experiment matrix (required format)

Run this matrix per corpus with fixed model/seed/substrate:

1. `baseline`: enrichment baseline/none, `co_retrieval_expand=false`
2. `embed_full_only`: enrichment full, `co_retrieval_expand=false`
3. `co_retrieval_only`: enrichment baseline/none, `co_retrieval_expand=true`
4. `embed_full_plus_co_retrieval`: enrichment full, `co_retrieval_expand=true`
5. optional `co_retrieval_plus_min_aprime`: `co_retrieval_expand=true`, `a_prime_generate_minimal=true`

Run-id should encode: corpus, mode, condition, recipe, model, timestamp.

Example:

`sf_hybrid_embed_full_plus_co_retrieval_std_mpnet_20260301_120501`

---

## 8) Evidence tie-back requirements

Every recommendation must include:

1. exact run artifact directory path(s),
2. matrix condition label,
3. metric delta vs baseline (`MRR`, `Hit@10/20`, `Recall@10/20`, `gold_in_candidates`),
4. one-line interpretation (`improved`, `regressed`, `neutral`),
5. exact benchmark surface used for the decision,
6. confirmation that contract validation passed,
7. the `prod_readiness.json` artifact path when recommending a production promotion.

Minimum result bundle per corpus:

- matrix summary table (all conditions),
- per-query wins/losses table,
- recommendation labels: `default`, `validated optional`, `experimental`.

---

## 9) Recent benchmark exemplars (with config details)

These are concrete runs from `out/retrieval_lab/experiments` and are useful reference points when setting expectations.

### 9.1 Best recent examples (high-signal references)

| Corpus | Run artifact | Key metrics | Config details |
|---|---|---|---|
| Starfinder | `out/retrieval_lab/experiments/starfinder_player_core_atomic_rules_20260228_061518` | `MRR=0.7083`, `Hit@5=0.8333`, `Hit@10=0.8333`, `Gold-in-candidates=0.8333`, `n=12`, `n_grounded=10` | `retrieval_mode=dense`, config `retrieval_lab/experiments/dense/starfinder_atomic_rules.yaml`, benchmark `evals/retrieval/StarFinderPlayerCore/starfinder_player_core_atomic_rules_benchmark.json`, model `all-mpnet-base-v2`, `co_retrieval_expand=false` |
| Starfinder | `out/retrieval_lab/experiments/starfinder_player_core_50q_post_full_gold_curation_20260228_184410` | `MRR=0.5296`, `Hit@5=0.80`, `Hit@10=0.92`, `Gold-in-candidates=1.00`, `n=50`, `n_grounded=50` | `retrieval_mode=dense`, config source `retrieval_lab/experiments/dense/starfinder_atomic_rules.yaml` with batch override to `starfinder_player_core_50q_benchmark.json`, model `all-mpnet-base-v2`, `chunk_quality_gate_enabled=true`, `co_retrieval_expand=false` |
| S&W | `out/retrieval_lab/experiments/swords_wizardry_hybrid_20260215_220401` | `MRR=0.3631`, `Hit@5=0.60`, `Hit@10=0.68`, `Gold-in-candidates=0.68`, `n=25`, `n_grounded=25` | `retrieval_mode=hybrid`, config aligned to `retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml`, model `all-mpnet-base-v2`, `co_retrieval_expand=false`, legacy benchmark path `evals/retrieval/SwordsandWizardy/swords_wizardry_benchmark.json` |
| S&W (enrichment experiment) | `out/retrieval_lab/experiments/swcr_embedding_metadata_enrichment_20260224_051503` | `MRR=0.6104`, `Hit@5=0.7105`, `Hit@10=0.7632`, `Gold-in-candidates=0.8158`, `n=38`, `n_grounded=34` | `retrieval_mode=dense`, experiment `swcr_embedding_metadata_enrichment`, model `all-mpnet-base-v2`, `a_prime_generate_minimal=true`, legacy benchmark path `evals/retrieval/SwordsandWizardy/swords_wizardry_complete_revised_benchmark_min_anchor_atomic_rewrite.json` |

### 9.1 Reasoning for interpretation

- High scores from smaller or legacy benchmark sets (for example, Starfinder atomic `n=12`) are useful diagnostics but are not alone sufficient for default-policy changes.
- Canonical recommendation decisions should prioritize corpus-level canonical benchmarks (`Starfinder 50q`, S&W complete revised benchmark) with explicit grounding coverage.
- When a run has low `n_grounded`, treat top-line metrics as weak evidence; investigate gold grounding and benchmark path consistency first.
- S&W high-scoring legacy runs are valuable signals, but they are not direct replacements for the canonical `SwordsandWizardry` benchmark path workflow.

---

## 10) Canonical location for best outputs

Promote the currently selected contract-valid run into a canonical per-book location:

- Starfinder: `out/StarFinderPlayerCore/retrieval_best/current`
- S&W Complete Revised: `out/Swords&Wizardry/SW_Complete_Revised/SW Complete Revised PDF/retrieval_best/current`

This avoids hunting through timestamped experiment directories and gives one stable path for downstream consumers.

### 10.0 Promotion gate

Promotion should now key off the explicit production-readiness artifact, not an informal run label.

- Only promote runs that emitted `prod_readiness.json`.
- `prod_readiness.json` must show `promotion_ready=true`.
- The selected benchmark surface in `prod_readiness.json` is the authoritative evaluation surface for the promotion decision.
- The promoted artifact bundle should preserve:
  - benchmark projection path/hash
  - benchmark contract path/hash
  - corpus fingerprint
  - corpus content fingerprint
  - corpus index hash

### 10.1 Promotion command

Run from `RulesIngestion` root:

```bash
uv run python scripts/promote_best_retrieval_run.py \
  --book-dir out/StarFinderPlayerCore \
  --run-dir out/retrieval_lab/experiments/starfinder_player_core_50q_post_full_gold_curation_20260228_184410 \
  --label starfinder-50q-best-current \
  --notes "Best corpus-level run after full gold curation."
```

For S&W:

```bash
uv run python scripts/promote_best_retrieval_run.py \
  --book-dir "out/Swords&Wizardry/SW_Complete_Revised/SW Complete Revised PDF" \
  --run-dir out/retrieval_lab/experiments/swords_wizardry_hybrid_20260215_220401 \
  --label swcr-hybrid-best-current \
  --notes "Best recent S&W Complete Revised hybrid run."
```

### 10.2 What gets copied

The promotion script copies key run artifacts (when present), including:

- `metrics.json`
- `run_manifest.json` or `manifest.json`
- `experiment.json`
- `REPORT.md`
- `per_query.json`
- `failure_buckets.json`
- `grounding_audit.json`
- `benchmark.<surface>.json`
- `benchmark.<surface>.contract.json`
- `embeddings/corpus_index.json`
- `prod_readiness.json`

It also writes `selection.json` with provenance, label, notes, and source run path.

### 10.3 History snapshots

Each promotion also writes a timestamped snapshot under:

- `out/<book>/retrieval_best/history/<timestamp>_<run_dir_name>/`

So `current/` stays stable while preserving prior selections.

---

## 11) Troubleshooting

### 11.1 Eval fails due to run mismatch

- Confirm eval `--run-id` comes from the exact embed run.
- Confirm same corpus and model set.
- Re-run embed-only if substrate or embedding recipe changed.
- If benchmark validation fails, inspect `benchmark_contract_validation.json` before trusting any metrics.
- If `corpus_index_sha256` or `corpus_content_fingerprint` changed, treat this as a new corpus contract and re-materialize the benchmark projection.

### 11.2 S&W path/spelling drift

- Replace any `SwordsandWizardy` benchmark path with `SwordsandWizardry`.
- Keep substrate path as `out/Swords&Wizardry`.

### 11.3 Results are not comparable

- Check that seed, model, recipe mode, benchmark, and substrate were fixed.
- If multiple axes changed in one run, do not use it for recommendation decisions.


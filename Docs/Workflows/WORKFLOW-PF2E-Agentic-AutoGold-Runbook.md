# Workflow: PF2E Agentic Auto-Gold Runbook

This workflow is the canonical agent runbook for taking a Pathfinder 2e corpus from stable retrieval baseline measurement through GPT-5.4-assisted gold creation and post-run validation.

Goal: establish a trustworthy MPNet starting baseline on the current chunk set, run auto-gold review with `gpt-5.4`, apply gold into the benchmark, and verify that the resulting metrics and review queue are decision-safe.

If you need the language-locked atomic benchmark workflow for same-language baseline and vocabulary-drift measurement, use `Docs/Workflows/WORKFLOW-PF2E-Atomic-Benchmark.md`. This runbook remains the corpus-level PF2E `50q` auto-gold path.

---

## 1) Scope and outcome

Use this runbook when all of the following are true:

- The corpus already exists as a Mark III Stage `A+B` substrate.
- You want to use `all-mpnet-base-v2` as the retrieval baseline.
- You want GPT-5.4 to review top-20 retrieval candidates and propose `required_gold` plus `supporting_gold`.
- You want benchmark updates written back automatically, but still want a human review queue for uncertain or difficult cases.

Successful completion produces:

- baseline retrieval runs for dense and hybrid MPNet,
- an auto-gold experiment run with `auto_gold_review.json`,
- updated benchmark gold fields,
- a `review_queue.json` for human inspection,
- a validated report of where retrieval starts before broader tuning.

---

## 2) Prerequisites

Run all commands from `RulesIngestion` root.

Required environment and state:

- Use `uv run ...` for Python commands.
- The PF2E substrate exists at `out/Pathfinder2ePlayerCore`.
- The benchmark exists at `evals/retrieval/Pathfinder2ePlayerCore/pathfinder2e_player_core_50q_benchmark.json`.
- `OPENAI_API_KEY` is available in `.env` or `.env.development`.

Important project assumptions:

- Retrieval tuning should use Stage `A+B` first.
- Do not run Stage `A'` unless you are explicitly testing enrichment effects.
- Keep substrate, model, and benchmark fixed within a comparison slice.
- Embed only after the merged retrieval chunk recipe is locked; for PF2E that recipe is `min_chars=200`, `merge_chunks=true`, `merge_max_chars=2000`.

References:

- `Docs/Workflows/WORKFLOW-Ingestion-Best-Practices.md`
- `Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md`
- `Docs/Workflows/WORKFLOW-PF2E-Atomic-Benchmark.md`

---

## 3) Canonical PF2E files and configs

Use these paths as the current PF2E contract:

- Substrate: `out/Pathfinder2ePlayerCore`
- Document ID: `PathCore`
- Benchmark: `evals/retrieval/Pathfinder2ePlayerCore/pathfinder2e_player_core_50q_benchmark.json`
- Dense baseline config: `retrieval_lab/experiments/dense/pf2e_mpnet_dense_baseline.yaml`
- Hybrid baseline config: `retrieval_lab/experiments/hybrid/pf2e_mpnet_hybrid_baseline.yaml`
- Auto-gold config: `retrieval_lab/experiments/dense/pf2e_autogold_pilot.yaml`

Current baseline policy for PF2E:

- model: `all-mpnet-base-v2`
- seed: `42`
- merge chunks: `true`
- `min_chars=200`
- `merge_max_chars=2000`
- hybrid fusion: `cc`
- `cc_lambda=0.7`
- `cc_bm25_normalization=minmax`

---

## 4) Phase 0: Preflight checks

Before running anything expensive:

1. Confirm the substrate is present.
2. Confirm the benchmark is valid JSON.
3. Confirm `OPENAI_API_KEY` can be loaded from `.env`.
4. Confirm you are not about to compare runs with different substrates or different benchmarks.

Recommended checks:

```bash
ls out/Pathfinder2ePlayerCore
uv run python -m retrieval_lab.benchmark_lint \
  evals/retrieval/Pathfinder2ePlayerCore/pathfinder2e_player_core_50q_benchmark.json
```

If the benchmark lint fails, stop and fix benchmark hygiene before proceeding.

---

## 5) Phase 1: Establish MPNet starting baseline

Run a compact best-practice baseline slice first. This gives the agent a trustworthy “where are we starting from?” view before gold is changed by the LLM.

### 5.1 Embed-only

These embed steps intentionally run against the merged retrieval corpus defined in the config, not the raw page-level Stage B units.

Standardized recipe:

```bash
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/dense/pf2e_mpnet_dense_baseline.yaml \
  --experiment-name pf2e_mpnet_std_embed \
  --recipe-mode standardized \
  --embed-only
```

Recommended recipe:

```bash
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/dense/pf2e_mpnet_dense_baseline.yaml \
  --experiment-name pf2e_mpnet_rec_embed \
  --recipe-mode recommended \
  --embed-only
```

Capture the emitted `run_id` values. For the current PF2E chunk set, these were:

- `retrieval_lab_PathCore_recipe_standardized`
- `retrieval_lab_PathCore_recipe_recommended`

### 5.2 Eval-only

Dense standardized:

```bash
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/dense/pf2e_mpnet_dense_baseline.yaml \
  --experiment-name pf2e_mpnet_dense_standardized \
  --recipe-mode standardized \
  --run-id retrieval_lab_PathCore_recipe_standardized
```

Hybrid standardized:

```bash
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/hybrid/pf2e_mpnet_hybrid_baseline.yaml \
  --experiment-name pf2e_mpnet_hybrid_standardized \
  --recipe-mode standardized \
  --run-id retrieval_lab_PathCore_recipe_standardized
```

Dense recommended:

```bash
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/dense/pf2e_mpnet_dense_baseline.yaml \
  --experiment-name pf2e_mpnet_dense_recommended \
  --recipe-mode recommended \
  --run-id retrieval_lab_PathCore_recipe_recommended
```

Hybrid recommended:

```bash
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/hybrid/pf2e_mpnet_hybrid_baseline.yaml \
  --experiment-name pf2e_mpnet_hybrid_recommended \
  --recipe-mode recommended \
  --run-id retrieval_lab_PathCore_recipe_recommended
```

### 5.3 Interpret the baseline

Current PF2E starting slice on the present chunk set:

| Condition | MRR | Hit@10 | Recall@10 | Gold-in-Candidates |
|---|---:|---:|---:|---:|
| Dense + standardized | 0.8254 | 0.94 | 0.9333 | 1.00 |
| Dense + recommended | 0.8254 | 0.94 | 0.9333 | 1.00 |
| Hybrid + standardized | 0.8537 | 0.98 | 0.9633 | 0.98 |
| Hybrid + recommended | 0.8537 | 0.98 | 0.9633 | 0.98 |

Interpretation:

- Hybrid is better on head ranking.
- Dense is slightly safer on ceiling coverage for this benchmark.
- `standardized` and `recommended` are currently equivalent for MPNet on this corpus.

Do not change defaults based on just one metric. Keep the artifact directories and compare per-query behavior if a policy change is being considered.

---

## 6) Phase 2: Run the GPT-5.4 auto-gold pilot

Use the dedicated PF2E auto-gold config:

```bash
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/dense/pf2e_autogold_pilot.yaml \
  --embed-only
```

Capture the `run_id`, then run retrieval plus review:

That `run_id` is valid only for this merged chunk recipe. If `min_chars`, `merge_chunks`, or `merge_max_chars` change, re-embed before review/eval.

```bash
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/dense/pf2e_autogold_pilot.yaml \
  --run-id <RUN_ID_FROM_EMBED_STEP>
```

The config is intentionally set to:

- `llm_model_id: gpt-5.4`
- `candidate_top_k: 20`
- `max_required_gold: 5`
- `max_supporting_gold: 5`
- `review_queue_challenge_sample_size: 10`
- `persist_benchmark: true`

Expected outputs in the experiment directory:

- `REPORT.md`
- `metrics.json`
- `per_query.json`
- `retrieved_chunks.json`
- `auto_gold_review.json`
- `review_queue.json`
- `run_manifest.json`

---

## 7) Phase 3: Validate the auto-gold result

After the GPT-5.4 run completes, validate three things separately.

### 7.1 Benchmark hygiene

```bash
uv run python -m retrieval_lab.benchmark_lint \
  evals/retrieval/Pathfinder2ePlayerCore/pathfinder2e_player_core_50q_benchmark.json
```

Check for:

- positive queries with empty `required_gold`,
- overlap spikes in `required_gold`,
- malformed or missing `gold_locations`.

### 7.2 Metrics sanity

Read:

- `metrics.json`
- `per_query.json`
- `REPORT.md`

Confirm:

- `gold_in_candidates` is plausible given the benchmark now written to disk,
- per-query misses are real misses, not evaluator mismatches,
- `required_full_set_hit_at_k` is not being inflated by empty `required_gold`.

### 7.3 Review queue sanity

Read:

- `auto_gold_review.json`
- `review_queue.json`

Confirm:

- the queue is a focused subset, not effectively the whole benchmark,
- flagged items actually represent low-confidence, overlap-risk, or challenge cases,
- `needs_human_review` counts in the report line up with actual queue intent.

If the queue is too broad, treat that as a product-quality problem, not a retrieval-quality improvement.

---

## 8) Human review phase

The automated pass is not the final authority. Use the review queue to inspect:

- low-confidence gold picks,
- multi-part questions,
- questions with multiple required anchors,
- overlap-risk cases,
- the challenge sample.

For each reviewed question:

1. confirm the chosen `required_gold` is the minimal operational set,
2. demote duplicate or contextual chunks to `supporting_gold`,
3. confirm `gold_locations` still resolve cleanly,
4. rerun benchmark lint after edits.

If substantial manual changes are made, rerun at least one baseline retrieval evaluation to re-check metrics.

---

## 9) Known pitfalls and how to handle them

### 9.1 Run ID mismatch during eval-only

Symptom:

- eval fails with a corpus fingerprint or shape mismatch.

Cause:

- reusing an old `run_id` after substrate or recipe changes.

Fix:

- rerun `embed-only` with the current config and use the new `run_id`.

### 9.2 OpenAI SDK rejects `response_format`

Symptom:

- `TypeError: Responses.create() got an unexpected keyword argument 'response_format'`

Status:

- already patched in the OpenAI-backed reviewer and answer-eval code paths.

Action:

- if this appears again, confirm the patched code is still present before changing workflow logic.

### 9.3 Metrics show gold misses after auto-gold apply

Symptom:

- the run report says gold was applied, but `per_query.json` still shows many `gold_not_in_candidates` misses.

Cause:

- scoring against `source_unit_ids` instead of the selected merged `chunk_id`s.

Status:

- fixed in `retrieval_lab/metrics.py` by always including the ranked candidate ID in each candidate source set.

Action:

- do not trust older PF2E auto-gold metrics generated before that fix.

### 9.4 Concurrent evals race on the benchmark file

Symptom:

- one concurrent run fails with `JSONDecodeError` while loading the benchmark.

Cause:

- multiple runs trying to resolve and persist gold into the same benchmark file at the same time.

Rule:

- do not run multiple evals in parallel if they will all rewrite the same benchmark file.

Safe options:

- serialize those runs,
- or use copied benchmark files per run if concurrency is required.

### 9.5 Enrichment coverage warning

Symptom:

- substrate loader warns that enrichment coverage is very low.

Meaning:

- Stage A' artifacts are keyed to stale unit IDs and are not materially affecting current retrieval.

Action:

- ignore for the baseline workflow unless you are explicitly testing enrichment,
- regenerate enrichment separately if enrichment experiments are needed later.

---

## 10) Decision rules for agents

An agent should follow these rules:

1. Never skip the baseline MPNet slice before running auto-gold on a new or changed chunk set.
2. Never compare runs where substrate and retrieval knobs both changed.
3. Never trust auto-gold metrics from an older run if the scorer bug fix is absent.
4. Never run concurrent evals that write to the same benchmark JSON.
5. Always rerun benchmark lint after benchmark-writing phases.
6. Treat `review_queue.json` as a product artifact that must be validated, not assumed correct.

---

## 11) Minimum evidence bundle to return

When the agent finishes, it should return:

1. exact artifact directory paths for each baseline run,
2. exact artifact directory path for the auto-gold run,
3. the baseline metric table,
4. the auto-gold summary counts from `REPORT.md`,
5. any benchmark lint findings,
6. any known-risk findings, especially:
   - scorer inconsistency,
   - benchmark-write race conditions,
   - over-broad review queues.

---

## 12) Current PF2E reference runs

These are the current reference runs on the present PF2E chunk set:

- `out/retrieval_lab/experiments/pf2e_mpnet_dense_standardized_20260306_043542`
- `out/retrieval_lab/experiments/pf2e_mpnet_dense_recommended_20260306_043556`
- `out/retrieval_lab/experiments/pf2e_mpnet_hybrid_standardized_20260306_043542`
- `out/retrieval_lab/experiments/pf2e_mpnet_hybrid_recommended_20260306_043543`
- `out/retrieval_lab/experiments/pf2e_autogold_pilot_20260306_010204`

Treat these as reference artifacts, not immutable truth. Re-run the workflow whenever the PF2E substrate, benchmark, or retrieval policy changes.

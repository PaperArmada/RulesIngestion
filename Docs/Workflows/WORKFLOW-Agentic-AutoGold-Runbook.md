# Workflow: Agentic Auto-Gold Runbook

This workflow is the canonical agent runbook for taking any rules corpus from stable retrieval baseline measurement through GPT-5.4-assisted gold creation and post-run validation.

Goal: establish a trustworthy starting baseline on the current chunk set, run auto-gold review with `gpt-5.4`, apply gold into the benchmark, and verify that the resulting metrics and review queue are decision-safe.

If you need the language-locked atomic benchmark workflow for same-language baseline and vocabulary-drift measurement, use `Docs/Workflows/WORKFLOW-PF2E-Atomic-Benchmark.md`. This runbook is the broader corpus-level benchmark auto-gold path.

---

## 1) Scope and outcome

Use this runbook when all of the following are true:

- The corpus already exists as a Mark III Stage `A+B` substrate.
- You have a benchmark JSON for the corpus you want to improve.
- You have a dense baseline config and, optionally, a hybrid baseline config for the same substrate and benchmark.
- You want GPT-5.4 to review top-20 retrieval candidates and propose `required_gold` plus `supporting_gold`.
- You want benchmark updates written back automatically, but still want a human review queue for uncertain or difficult cases.

Successful completion produces:

- baseline retrieval runs for the configured dense and optional hybrid baselines,
- an auto-gold experiment run with `auto_gold_review.json`,
- updated benchmark gold fields,
- a `review_queue.json` for human inspection,
- a validated report of where retrieval starts before broader tuning.

---

## 2) Prerequisites

Run all commands from `RulesIngestion` root.

Required environment and state:

- Use `uv run ...` for Python commands.
- `OPENAI_API_KEY` is available in `.env` or `.env.development`.

Before running the workflow, resolve this corpus contract and keep it fixed for the entire comparison slice:

- Corpus slug: `<CORPUS_SLUG>`
- Model slug for artifact names: `<MODEL_SLUG>`
- Substrate directory: `<SUBSTRATE_DIR>`
- Document ID: `<DOCUMENT_ID>`
- Benchmark path: `<BENCHMARK_PATH>`
- Dense baseline config: `<DENSE_BASELINE_CONFIG>`
- Hybrid baseline config: `<HYBRID_BASELINE_CONFIG>` or omit hybrid if not applicable
- Auto-gold config: `<AUTO_GOLD_CONFIG>`
- Baseline model ID: `<MODEL_ID>`
- Seed: `<SEED>`
- Chunk recipe knobs: `merge_chunks=<BOOL>`, `min_chars=<N>`, `merge_max_chars=<N>`

Important project assumptions:

- Retrieval tuning should use Stage `A+B` first.
- Do not run Stage `A'` unless you are explicitly testing enrichment effects.
- Keep substrate, model, and benchmark fixed within a comparison slice.
- Embed only after the merged retrieval chunk recipe is locked.

References:

- `Docs/Workflows/WORKFLOW-Ingestion-Best-Practices.md`
- `Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md`
- `Docs/Workflows/WORKFLOW-PF2E-Atomic-Benchmark.md`

---

## 3) Corpus contract worksheet

Use these values as the current corpus contract:

- Substrate: `<SUBSTRATE_DIR>`
- Document ID: `<DOCUMENT_ID>`
- Benchmark: `<BENCHMARK_PATH>`
- Dense baseline config: `<DENSE_BASELINE_CONFIG>`
- Hybrid baseline config: `<HYBRID_BASELINE_CONFIG>`
- Auto-gold config: `<AUTO_GOLD_CONFIG>`

Current baseline policy:

- model: `<MODEL_ID>`
- seed: `<SEED>`
- merge chunks: `<MERGE_CHUNKS>`
- `min_chars=<MIN_CHARS>`
- `merge_max_chars=<MERGE_MAX_CHARS>`
- hybrid fusion: `<HYBRID_FUSION_MODE>`
- `cc_lambda=<CC_LAMBDA>`
- `cc_bm25_normalization=<BM25_NORMALIZATION>`

Notes:

- If your corpus does not use hybrid retrieval, skip the hybrid steps but still record the dense baseline cleanly.
- If you are using `all-mpnet-base-v2`, keep the model slug consistent in experiment names so artifacts remain easy to compare.

---

## 4) Phase 0: Preflight checks

Before running anything expensive:

1. Confirm the substrate is present.
2. Confirm the benchmark is valid JSON.
3. Confirm `OPENAI_API_KEY` can be loaded from `.env`.
4. Confirm you are not about to compare runs with different substrates or different benchmarks.

Recommended checks:

```bash
ls <SUBSTRATE_DIR>
uv run python -m retrieval_lab.benchmark_lint \
  <BENCHMARK_PATH>
```

If the benchmark lint fails, stop and fix benchmark hygiene before proceeding.

---

## 5) Phase 1: Establish starting baseline

Run a compact best-practice baseline slice first. This gives the agent a trustworthy "where are we starting from?" view before gold is changed by the LLM.

### 5.1 Embed-only

These embed steps intentionally run against the merged retrieval corpus defined in the config, not the raw page-level Stage B units.

Standardized recipe:

```bash
uv run python -m retrieval_lab.run_experiment \
  --config <DENSE_BASELINE_CONFIG> \
  --experiment-name <CORPUS_SLUG>_<MODEL_SLUG>_std_embed \
  --recipe-mode standardized \
  --embed-only
```

Recommended recipe:

```bash
uv run python -m retrieval_lab.run_experiment \
  --config <DENSE_BASELINE_CONFIG> \
  --experiment-name <CORPUS_SLUG>_<MODEL_SLUG>_rec_embed \
  --recipe-mode recommended \
  --embed-only
```

Capture the emitted `run_id` values. Record them explicitly because all later eval-only steps depend on the exact corpus fingerprint they were built from.

Suggested recording format:

- standardized embed `run_id`: `<STANDARDIZED_RUN_ID>`
- recommended embed `run_id`: `<RECOMMENDED_RUN_ID>`

### 5.2 Eval-only

Dense standardized:

```bash
uv run python -m retrieval_lab.run_experiment \
  --config <DENSE_BASELINE_CONFIG> \
  --experiment-name <CORPUS_SLUG>_<MODEL_SLUG>_dense_standardized \
  --recipe-mode standardized \
  --run-id <STANDARDIZED_RUN_ID>
```

Hybrid standardized:

```bash
uv run python -m retrieval_lab.run_experiment \
  --config <HYBRID_BASELINE_CONFIG> \
  --experiment-name <CORPUS_SLUG>_<MODEL_SLUG>_hybrid_standardized \
  --recipe-mode standardized \
  --run-id <STANDARDIZED_RUN_ID>
```

Dense recommended:

```bash
uv run python -m retrieval_lab.run_experiment \
  --config <DENSE_BASELINE_CONFIG> \
  --experiment-name <CORPUS_SLUG>_<MODEL_SLUG>_dense_recommended \
  --recipe-mode recommended \
  --run-id <RECOMMENDED_RUN_ID>
```

Hybrid recommended:

```bash
uv run python -m retrieval_lab.run_experiment \
  --config <HYBRID_BASELINE_CONFIG> \
  --experiment-name <CORPUS_SLUG>_<MODEL_SLUG>_hybrid_recommended \
  --recipe-mode recommended \
  --run-id <RECOMMENDED_RUN_ID>
```

### 5.3 Interpret the baseline

Record the baseline in a table like this:

| Condition | MRR | Hit@10 | Recall@10 | Gold-in-Candidates |
|---|---:|---:|---:|---:|
| Dense + standardized | `<MRR>` | `<HIT_AT_10>` | `<RECALL_AT_10>` | `<GOLD_IN_CANDIDATES>` |
| Dense + recommended | `<MRR>` | `<HIT_AT_10>` | `<RECALL_AT_10>` | `<GOLD_IN_CANDIDATES>` |
| Hybrid + standardized | `<MRR>` | `<HIT_AT_10>` | `<RECALL_AT_10>` | `<GOLD_IN_CANDIDATES>` |
| Hybrid + recommended | `<MRR>` | `<HIT_AT_10>` | `<RECALL_AT_10>` | `<GOLD_IN_CANDIDATES>` |

Interpretation:

- Hybrid is better on head ranking.
- Dense may still be safer on ceiling coverage for the benchmark.
- `standardized` and `recommended` may be equivalent; verify from actual artifacts rather than assuming.

Do not change defaults based on just one metric. Keep the artifact directories and compare per-query behavior if a policy change is being considered.

---

## 6) Phase 2: Run the GPT-5.4 auto-gold pilot

Use the corpus-specific auto-gold config:

```bash
uv run python -m retrieval_lab.run_experiment \
  --config <AUTO_GOLD_CONFIG> \
  --embed-only
```

Capture the `run_id`, then run retrieval plus review:

That `run_id` is valid only for this merged chunk recipe. If `min_chars`, `merge_chunks`, or `merge_max_chars` change, re-embed before review/eval.

```bash
uv run python -m retrieval_lab.run_experiment \
  --config <AUTO_GOLD_CONFIG> \
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
  <BENCHMARK_PATH>
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

- do not trust older auto-gold metrics generated before that fix.

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

1. Never skip the starting baseline slice before running auto-gold on a new or changed chunk set.
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

## 12) Per-corpus notes

Keep corpus-specific reference runs, metrics, and artifact paths outside this generic workflow. This document should stay reusable; per-corpus state belongs in experiment reports, handoffs, or corpus-specific notes.

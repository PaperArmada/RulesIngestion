# Workflow: Atomic Benchmark Sweep Across Ready Rulesets

This workflow defines the generic instruction set for running the same atomic benchmark process across any set of rulesets that are ready for sweep comparison.

Goal: run a fixed, language-locked atomic benchmark across every selected ready corpus, produce a comparable evidence bundle per corpus, and keep the sweep limited to true atomic benchmark surfaces rather than broader or auto-gold-only experiments.

---

## 1) Scope

Run all commands from `RulesIngestion` root.

This workflow is a sweep wrapper around:

- `Docs/Workflows/WORKFLOW-Atomic-Benchmark.md`

Use this workflow when you want:

- one pass over every ready atomic benchmark,
- a reproducible per-corpus evidence bundle,
- a clean comparison surface for vocabulary drift and retrieval behavior.

Do not use this workflow to:

- create new atomic benchmarks,
- run broader 50-question benchmark suites,
- mix in blank-for-autogold or broader benchmark configs just because a substrate exists,
- compare corpora that are using materially different benchmark definitions or chunk recipes as if they were the same condition.

---

## 2) How To Define The Ready Set

A corpus is ready for this sweep only if all of the following are true:

1. a checked-in atomic benchmark JSON exists,
2. the benchmark filename and benchmark metadata clearly identify the target substrate contract,
3. a dedicated atomic experiment config exists for that benchmark,
4. the config declares the matching `substrate_version`,
5. the referenced substrate exists,
6. the benchmark remains language-locked to `evals/retrieval/benchmark_template_atomic_rules.json`.

For each selected corpus, resolve and record this contract before running anything:

- Corpus label: `<CORPUS_LABEL>`
- Corpus slug: `<CORPUS_SLUG>`
- Atomic benchmark: `<ATOMIC_BENCHMARK_PATH>`
- Config: `<ATOMIC_EXPERIMENT_CONFIG>`
- Substrate: `<SUBSTRATE_PATH>`
- Document ID: `<DOCUMENT_ID>`
- Substrate version: `<SUBSTRATE_VERSION>`
- Model list: `<MODEL_LIST>`
- Chunk recipe: `min_chars=<MIN_CHARS>`, `merge_chunks=<BOOL>`, `merge_max_chars=<MERGE_MAX_CHARS>`

Readiness rule:

- If any one of those items is missing or invalid, exclude that corpus from the sweep until the missing atomic surface is fixed.

Selection discipline:

- Build the ready set explicitly at run time.
- Do not silently include corpora just because they have a substrate.
- Do not silently exclude corpora without saying why.

---

## 3) Sweep Contract

Apply the same rules as the single-corpus atomic workflow:

1. Never rewrite atomic question text for a specific corpus.
2. Treat each corpus config plus benchmark plus chunk recipe as its own fixed contract.
3. Do not compare outputs from different chunk recipes as if they were the same condition.
4. Do not substitute broader benchmarks or blank autogold benchmarks into this sweep.
5. Re-embed whenever a corpus chunk recipe changes.
6. If the chunk recipe changes, create a new benchmark version or explicitly re-anchor the benchmark surface instead of silently reusing the old filename.

Cross-corpus comparison is allowed only after each corpus has passed its own preflight and contract checks.

---

## 4) Phase 0: Preflight Every Selected Corpus

Before embedding or eval, do the following for each selected corpus:

1. Confirm the substrate exists.
2. Lint the atomic benchmark JSON.
3. Confirm the benchmark wording is still language-locked to `evals/retrieval/benchmark_template_atomic_rules.json`.
4. Confirm the benchmark filename, benchmark metadata, and config all point at the same intended corpus recipe.
5. Confirm you are not silently changing the chunk recipe in the config.

Recommended checks:

```bash
ls "<SUBSTRATE_PATH>"
uv run python -m retrieval_lab.benchmark_lint "<ATOMIC_BENCHMARK_PATH>"
```

Manual wording-lock check:

- compare the `question` strings in each selected benchmark against `evals/retrieval/benchmark_template_atomic_rules.json`,
- if wording drift was introduced for corpus-specific convenience, revert it before running the sweep.

Contract check:

- verify `metadata.substrate_version`, `metadata.substrate_path`, `metadata.document_id`, and the config `substrate_version` all agree,
- if chunk topology changed, version or re-anchor the benchmark before sweeping,
- if the benchmark points at corpus-missing gold IDs, fix the benchmark surface before sweeping.

Stop condition:

- Do not proceed to embed/eval for a corpus that fails preflight.

---

## 5) Phase 1: Embed Each Ready Corpus

Run the embed step once per selected corpus and capture the emitted `run_id`.

Template command:

```bash
uv run python -m retrieval_lab.run_experiment \
  --config "<ATOMIC_EXPERIMENT_CONFIG>" \
  --experiment-name "<CORPUS_SLUG>_atomic_rules_embed" \
  --embed-only
```

Record for each corpus:

- corpus: `<CORPUS_SLUG>`
- run_id: `<RUN_ID>`

Important:

- If `reuse_embeddings: true`, reruns may reuse a compatible embedding set.
- If `reuse_embeddings: false`, expect a fresh embed.
- If `min_chars`, `merge_chunks`, or `merge_max_chars` change, the old `run_id` is no longer comparison-compatible.

---

## 6) Phase 2: Eval Each Ready Corpus

Use the `run_id` captured from the corresponding embed step.

Template command:

```bash
uv run python -m retrieval_lab.run_experiment \
  --config "<ATOMIC_EXPERIMENT_CONFIG>" \
  --experiment-name "<CORPUS_SLUG>_atomic_rules_eval" \
  --run-id "<RUN_ID>"
```

Expected outputs per corpus:

- `REPORT.md`
- `metrics.json`
- `per_query.json`
- `retrieved_chunks.json`
- `benchmark.<surface>.json`
- `benchmark.<surface>.contract.json`
- `benchmark_contract_validation.json`
- `embeddings/corpus_index.json`

Note:

- emitted `.contract.json` files are validation artifacts, not the source-of-truth readiness contract for whether a corpus belongs in the ready sweep.

---

## 7) Phase 3: Compare Results Across The Sweep

After all selected runs finish, compare them as a sweep.

Minimum comparison questions:

1. Which atomic concepts retrieve cleanly across the selected corpora?
2. Which misses are likely vocabulary drift rather than true retrieval failure?
3. Are misses clustered on the same shared template concepts across corpora?
4. Are there chunking or ranking pathologies that make the comparison misleading?
5. Are any misses actually benchmark-anchor problems rather than retrieval problems?

Required comparison discipline:

- interpret each corpus on its own first,
- then compare cross-corpus patterns,
- do not claim a corpus is weaker just because the shared template language is a worse lexical fit,
- inspect `per_query.json` and `retrieved_chunks.json` before summarizing vocabulary drift,
- separate corpus weakness from benchmark-surface weakness.

---

## 8) Operator Patterns

### 8.1 Serial Manual Sweep

Use this when you want full visibility and explicit run IDs.

1. Build the ready set and record each corpus contract.
2. Run preflight for all selected corpora.
3. Run embed once per corpus and record each `run_id`.
4. Run eval once per corpus using the matching `run_id`.
5. Collect artifact directories and summarize metrics side by side.

This keeps the workflow explicit and avoids hiding contract drift behind automation.

### 8.2 Helper Script

Use the helper only if its internal ready-corpus list matches the ready set you actually want to run.

Available patterns:

- `uv run python scripts/run_atomic_ready_sweep.py`
- `uv run python scripts/run_atomic_ready_sweep.py --dry-run`
- `uv run python scripts/run_atomic_ready_sweep.py --preflight-only`
- `uv run python scripts/run_atomic_ready_sweep.py --corpora <SLUG_A> <SLUG_B>`

Helper-script rule:

- If the script’s hardcoded ready set is stale, update the script or run the sweep manually. Do not pretend the helper is generic if its ready-set registry is out of date.

---

## 9) Decision Rules For Maintaining This Workflow

An agent should follow these rules:

1. Add a corpus to a sweep only after the versioned atomic benchmark JSON and dedicated atomic config are both checked in and aligned on substrate contract.
2. Exclude a corpus if its atomic benchmark is missing, invalid, metadata/config-misaligned, or no longer language-locked.
3. Keep broader benchmarks, blank autogold benchmarks, and experimental configs out of the ready sweep.
4. Update any helper-script ready-set registry in the same change that makes a new corpus sweep-ready.
5. Return exact artifact paths and exact benchmark surfaces used for every corpus in the sweep.

---

## 10) Minimum Evidence Bundle To Return

When the sweep finishes, return for each corpus that actually ran:

1. exact artifact directory path,
2. benchmark file path used,
3. config path used,
4. substrate version and chunk recipe used,
5. top-line metrics,
6. per-query misses that look like vocabulary drift,
7. per-query misses that look like true retrieval failures,
8. any benchmark lint or contract validation findings,
9. any suspected benchmark-anchor problems discovered during review.

Also return a cross-corpus comparison table covering:

- corpus,
- `MRR`,
- `Hit@5`,
- `Hit@10`,
- `Gold-in-candidates`,
- number of grounded queries,
- short interpretation note.

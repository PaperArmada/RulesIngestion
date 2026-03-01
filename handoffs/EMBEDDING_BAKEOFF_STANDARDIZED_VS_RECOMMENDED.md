# Embedding Bakeoff Workflow: Standardized vs Recommended Inference

**Project:** DungeonOverMind / Retrieval Lab  
**Date:** 2026-02-28  
**Applies to:** SF2e Player Core + Swords & Wizardry corpora (and any future corpora)

## Why this document exists

We want to choose a **default embedding model** and understand **model behavior** in *our* retrieval stack. To avoid “winner by quirks,” we will run **two inference recipes**:

1) **Standardized (baseline) recipe** — one uniform embedding pipeline across all models (our current default behavior).  
2) **Recommended recipe** — each model’s author-intended inference settings (pooling, normalization, query/passage formatting, etc.) recorded explicitly.

We will treat this as a workflow, not a one-off benchmark. The outputs should be reusable and comparable across time.

---

## Core decision rule

We pick the default baseline based on **hybrid retrieval performance** (production-like config), with strict regression awareness.

Dense-only runs exist to help interpret behavior, not to pick the winner.

---

## Terminology

- **Standardized recipe:** Our uniform approach to generate embeddings across models (fixed pooling/normalization/token limits).
- **Recommended recipe:** Model-specific inference procedure sourced from official docs/model cards or paper; pinned to a revision.
- **A/B isolation:** In an A/B, only the dense embedding model (and/or recipe mode) changes; BM25 + fusion + rerank + QE remain fixed.
- **Mode:** `dense_only` or `hybrid`.
- **Corpus:** `StarFinderPlayerCore` or `SwordsAndWizardry`.
- **Run key:** `(corpus, mode, model_id, recipe_mode, chunking_profile_version)`.

---

## Standardized (baseline) inference recipe spec

This must be identical across all tested embedding models:

- **Device:** CUDA (RTX 4080)
- **Precision:** FP16 if supported; else FP32 (record actual dtype)
- **Max sequence length:** fixed (e.g. 512) — same for all models
- **Pooling:** mean pooling over last hidden states (exclude padding tokens)
- **Normalization:** L2-normalize embeddings to unit length
- **Similarity:** cosine similarity (or dot product if vectors are L2-normalized; must be consistent)
- **Text normalization:** whatever Retrieval Lab currently does (do not change mid-bakeoff; record it)

Notes:
- This recipe may be “suboptimal” for some models. That’s fine: it answers “how does it behave under our default pipeline?”
- If a model does not expose token-level hidden states needed for mean pooling under your loader, the run must fail loudly (do not silently switch pooling).

---

## Recommended inference recipe workflow

For each model, we will:
1) Collect recommended inference guidance from primary sources (model card, official repo/docs, or paper).
2) Record it in `embedding_provenance.json` for each run, including:
   - pooling method
   - normalization expectations
   - query vs passage formatting (prefixes, prompts, instructions)
   - max sequence length expectations
   - intended similarity metric (cosine vs dot)
   - whether to use special adapters (e.g., instruction tuning) or multi-vector outputs
3) Pin a **model revision** (commit hash / tag) so `--trust-remote-code` doesn’t drift across time.

Recommended recipe is **allowed** to differ from standardized recipe only in:
- pooling choice (mean/CLS/etc.)
- normalization (on/off, type)
- query/passage formatting
- max sequence length (if clearly required/recommended; must be recorded)
- output dtype/quantization mode (if the model is explicitly designed for INT8 outputs, etc.)

Recommended recipe is **not** allowed to change:
- chunking profile
- corpus construction
- BM25 / fusion / rerank / QE policies
- evaluation batches

---

## Model bakeoff run matrix

For each corpus (SF2e, S&W), for each model in the matrix:

**Recipe modes to run**
- `standardized` (always)
- `recommended` (always, unless primary-source guidance cannot be found; if missing, note and skip with explicit “no source” flag)

**Retrieval modes to run**
- `dense_only`
- `hybrid` (primary decision signal)

So each model yields up to 4 runs per corpus:
- dense_only + standardized
- dense_only + recommended
- hybrid + standardized
- hybrid + recommended

Optional follow-up:
- `pplx-embed-context-v1` only if `pplx-embed-v1-0.6B` shows promise; it must be run under both standardized and recommended if feasible, but contextual packing itself is a separate switch (recorded as its own recipe_mode variant).

---

## Required artifacts per run

Each run must write (or be linkable via run_manifest) to:

1) `embedding_provenance.json`
   - model_id, revision
   - loader module path + class name (prove we edited the right place)
   - device, dtype, quant mode
   - pooling, normalization, similarity metric
   - max_seq_len
   - query/passage formatting (if any)
   - corpus hash + input hash (stable ordering)
2) `run_manifest.json`
   - run_key fields + paths
3) `per_query.json` (or equivalent)
4) metrics summary (MRR/Hit@k/Recall@k/etc.)
5) top improvements/regressions list vs baseline

---

## Determinism checklist (minimum viable)

We aim for **metric-level reproducibility** (not necessarily bitwise identical tensors).

Must do:
- Fixed seed (`--seed 42`)
- Fixed corpus ordering
- Pinned model revisions + pinned library versions (transformers, sentence-transformers, torch)
- Record CUDA/cuDNN versions if possible (optional but helpful)

If stronger reproducibility is desired later:
- Add torch deterministic flags and accept perf hit (document that as a separate protocol)

---

## Research tasks for “recommended inference”

Make a short per-model note (2–6 bullets) with citations/links in a separate file (or in `then_vs_now.md`), but the core requirements are:

- **Source:** model card / official docs / paper
- **What to extract:** pooling + normalization + formatting + max length + similarity expectations
- **What to pin:** revision id

If recommended inference differs from standardized, that’s the point; we want to see whether the differences matter in our stack.

---

## Implementation notes (to avoid common bakeoff failures)

1) **Confirm registry is the one actually used**
   - Require a log line at runtime: “Embedding model loaded via <python module path>”.
   - Avoid editing archived registries that aren’t imported.

2) **Score fusion vs rank fusion**
   - If fusion uses scores anywhere (not pure RRF), ensure similarity metric and normalization are consistent across models/recipes.
   - If fusion is rank-based only, score calibration matters less but still record it.

3) **Run-ID wiring sanity**
   - Ensure hybrid runs are consuming the intended dense embedding artifacts (log the embedding store id / substrate_run_id).

4) **Smoke test first**
   - Before full matrix: run 1 model, 1 corpus, 5 queries, both recipes, dense_only + hybrid. Confirm artifacts and provenance are correct.

---

## CLI templates (conceptual)

### Embed-only
```bash
uv run python -m retrieval_lab.run_experiment \
  --config <CONFIG_PATH> \
  --experiment-name <EXP_NAME> \
  --models <MODEL_ID> \
  --recipe-mode <standardized|recommended> \
  --embed-only \
  --seed 42 \
  --trust-remote-code
```

### Eval-only
```bash
uv run python -m retrieval_lab.run_experiment \
  --config <CONFIG_PATH> \
  --experiment-name <EXP_NAME> \
  --models <MODEL_ID> \
  --recipe-mode <standardized|recommended> \
  --batches <BENCHMARK_JSON> \
  --run-id <RUN_ID_FROM_EMBED_STEP> \
  --seed 42 \
  --trust-remote-code
```

### Hybrid
```bash
uv run python -m retrieval_lab.run_experiment \
  --config <HYBRID_CONFIG_PATH> \
  --experiment-name <EXP_NAME> \
  --models <MODEL_ID> \
  --recipe-mode <standardized|recommended> \
  --batches <BENCHMARK_JSON> \
  --seed 42 \
  --trust-remote-code
```

If `--recipe-mode` is not implemented yet, implement it as a first-class switch that controls:
- pooling/normalization/formatting/max_len per recipe
- provenance logging
…and nothing else.

---

## Output bundle structure

Create:
`out/retrieval_lab/experiments/model_bakeoff_<timestamp>/`

Include at minimum:
- `SUMMARY.md`
- `run_manifest.json`
- `top_improvements_and_regressions.json`
- `embedding_provenance.json` (can be per-run and aggregated)
- `model_strengths_weaknesses.md`
- `then_vs_now.md`

---

## Acceptance criteria for the workflow (not the winner)

This workflow is “done” when:
- each required model runs on both corpora
- each run is executed in both recipe modes (or explicitly skipped with “no source”)
- provenance is complete and proves correct code path + fixed policies
- we can reproduce the summary tables from the manifest without manual hand edits

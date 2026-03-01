# Workflow: Embedding Bakeoff Design (Deterministic + Contract-Locked)

This workflow is the canonical design for selecting the default embedding baseline in Retrieval Lab.

Goal: compare embedding models fairly, isolate true model behavior, and prevent evaluation drift from corrupting decisions.

---

## 1) Decision question

Primary question:

Which embedding model should be the default baseline for our current retrieval stack, across Starfinder and S&W, under fixed retrieval policy and fixed corpus/benchmark contracts?

Secondary question:

Do current observations match earlier embedding benchmark behavior, or reveal new strengths/weaknesses under tuned ingestion/retrieval pipelines?

---

## 2) Non-negotiable experiment contract

For any run to be eligible for model comparison, all of the following must be pinned and recorded in `run_manifest.json`:

1. **Corpus contract**
   - `substrate_path`
   - `document_id`
   - `substrate_version`
   - `corpus_fingerprint`
2. **Benchmark contract**
   - benchmark path
   - benchmark sha256
   - query count
   - benchmark lint summary
3. **Retrieval contract**
   - retrieval mode (`dense` or `hybrid`)
   - BM25 settings
   - fusion/rerank policy knobs
   - top-k list
4. **Embedding contract**
   - model id + revision
   - recipe mode (`standardized` or `recommended`)
   - pooling/normalize/max_seq_len/query-prefix/passage-prefix
5. **Run-key contract**
   - `(corpus, retrieval_mode, model_id, recipe_mode, enrichment_profile, run_id)`

If any contract field differs across two runs, they are not directly comparable.

---

## 3) Preflight gates (hard fail)

Do not start matrix execution unless all gates pass.

1. **Corpus/run compatibility**
   - Fail on run-id and corpus mismatch with:
   - `run_id incompatible with current corpus shape; re-embed with same config.`
2. **Model availability**
   - Fail if configured model is missing from registry.
3. **Benchmark integrity**
   - Fail when benchmark path or hash differs from the declared baseline track.
4. **Gold hygiene**
   - Fail (or require explicit override) when `required_gold_empty` exceeds threshold.
   - Recommended baseline threshold: `<= 2` for Starfinder 50q and SWCR primary track.
5. **Recipe integrity**
   - Fail if `recommended` recipe is requested and required recipe source metadata is missing.

---

## 4) Canonical corpora and benchmark tracks

Use one locked track per corpus for baseline decisions.

### 4.1 Starfinder (primary)

- Substrate: `out/StarFinderPlayerCore`
- Benchmark: `evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json`
- Required run mode: `dense` and `hybrid` (both)

### 4.2 S&W (primary)

- Substrate: `out/Swords&Wizardry/SW_Complete_Revised/SW Complete Revised PDF`
- Benchmark: `evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_benchmark.json`
- Required run mode: `dense` and `hybrid` (both)

Do not mix the `Swords&Wizardry` and `SW Complete Revised PDF` tracks in the same comparison table.

---

## 5) Model matrix (Phase 1: core)

Run this matrix with strict A/B isolation (only dense embedding model/recipe varies):

- `all-mpnet-base-v2` (current baseline)
- `nomic-embed-text-v2`
- `bge-m3`
- `pplx-embed-v1-0.6B`

Recipe variants per model:

1. `standardized`
2. `recommended`

Run modes per model/recipe:

1. `dense`
2. `hybrid`

Enrichment axis:

- baseline profile (none/baseline)
- `embedding_enrichment_profile=full` (required for S&W; optional for Starfinder)

---

## 6) Contextual model gate (Phase 2 conditional)

Run `pplx-embed-context-v1` only if Phase 1 shows meaningful gain:

- improved hybrid metrics on at least one primary corpus, and
- no major Tier-1 regression.

Context setup:

- group units by structural section depth,
- include bounded neighbor context,
- keep retrieval/rerank policy unchanged.

---

## 7) Execution order

Run from `RulesIngestion` root.

1. Preflight contract lock + lint checks.
2. For each corpus:
   - run baseline model matrix first (`all-mpnet-base-v2`) to validate track stability.
   - run candidate models with same corpus/benchmark/retrieval contracts.
3. For each condition:
   - `embed-only`
   - `eval-only` using exact `run_id`
4. Archive artifacts per run.
5. Build aggregate report only from contract-valid runs.

---

## 8) Metrics to report (required)

### 8.1 Core metrics

- MRR
- nDCG@10
- Hit@10, Hit@20
- Recall@10, Recall@20
- Gold-in-candidates
- Gold-in-candidates (true ceiling)
- Required full-set hit@10
- Rank-of-last-required (mean)

### 8.2 Failure diagnostics

- `no_gold_defined`
- `gold_not_in_candidates`
- `gold_in_candidates_but_low_rank`
- `grounding_or_answer_failure_after_retrieval`

### 8.3 Differential views

- delta vs baseline by corpus/mode/recipe
- top improvements (per query)
- top regressions (per query)
- tier/failure-bucket slices where available

---

## 9) Deliverables

For each bakeoff cycle:

1. `run_manifest.json` for every run.
2. `embedding_provenance.json` for every run.
3. consolidated summary table:
   - rows: model x recipe x mode x enrichment profile
   - columns: required metrics + deltas vs baseline
4. per-query wins/losses pack with chunk IDs/ranks.
5. `model_strengths_weaknesses.md`
6. `then_vs_now.md` (comparison to earlier benchmark observations)
7. final recommendation label:
   - `adopt`
   - `reject`
   - `adopt_contextual_only`

---

## 10) Recommendation rule

A model can become default baseline only if:

1. Hybrid performance improves on primary tracks (or materially reduces grounding-related failure buckets), and
2. no notable Tier-1 regressions, and
3. gains hold across repeated deterministic reruns.

If mixed:

- keep existing baseline,
- record strengths/weaknesses by corpus and failure type,
- define targeted follow-up experiments (for example seq length, recipe tuning, contextual indexing).

---

## 11) Anti-patterns (do not do)

- Comparing runs with different benchmark hashes.
- Comparing runs across different corpus tracks as if equivalent.
- Declaring winner with high `required_gold_empty` drift.
- Mixing retrieval policy changes into embedding bakeoff rows.
- Using unenforced recipe settings without provenance capture.

---

## 12) Related documents

- `Docs/Workflows/WORKFLOW-Ingestion-Best-Practices.md`
- `Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md`
- `Docs/Learnings/LEARNINGS-Evaluation-Drift-vs-Embedding-Determinism-2026.md`
- `handoffs/EMBEDDING_BAKEOFF_STANDARDIZED_VS_RECOMMENDED.md`

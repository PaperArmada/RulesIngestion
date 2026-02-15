# Handoff: Hard Critique Prep (Top-to-Bottom)

**Date:** 2026-02-12  
**Last Updated:** 2026-02-13 (low-hanging tuning + critique lock + plan execution complete)  
**Repo:** `RulesIngestion`  
**Intent for next agent:** Run a deep, end-to-end critique of code + contracts + eval methodology, then discuss findings with the user **before** proposing design/implementation steps.

---

## 0) Critique Lock (Execution Baseline)

This lock is treated as approved for the current implementation wave.

- **True defects (must fix):**
  - Benchmark contract ambiguity between first-hit and composition objectives.
  - Integrity policy ambiguity (warn vs strict) for gating runs.
  - Missing explicit classification of retrieval improvements (coverage gain vs rank reshuffle).
- **Accepted temporary trade-offs:**
  - Preserve legacy `gold_unit_ids` semantics for backward compatibility while introducing `required_gold` / `supporting_gold`.
  - Keep S&W two-stage retrieval behind flags until it proves ceiling gain with rank recovery.
- **Acceptance criteria for this wave:**
  - Backward-compatible benchmark runs still execute on legacy artifacts.
  - New required-set metrics are emitted alongside legacy metrics.
  - Gating integrity checks can hard-fail deterministically; expansion remains non-blocking.
  - Outcome classification is present in reports when baseline reference data exists.
- **Rollback condition:**
  - If legacy baseline comparability breaks, disable new fields/flows via config defaults and retain legacy reporting path.

---

## 1) Current State Snapshot

The repo has been moved to a v1-centered design and baseline flow:

- Canonical docs now live under `Docs/Design/v1/`.
- Baseline suite is standardized under `evals/v1_baseline/`.
- Stage A/B substrate paths were normalized to `out/<DocumentID>`.
- Dual-list fusion is now configured for all three corpora (PHB, Starfinder, S&W).
- Fresh baseline runs were executed and archived in `evals/v1_baseline/20260212/`.
- Consolidated analysis report was created at:
  - `evals/v1_baseline/20260212/BASELINE_REPORT.md`

This is the immediate context for critique work.

Additional current-state note from 2026-02-13 refactor session:

- `retrieval_lab/run_experiment.py` was significantly modularized (now mostly orchestration wiring).
- Dense/hybrid orchestration helpers were extracted to:
  - `retrieval_lab/orchestration/dense_mode.py`
- BM25 orchestration helpers were extracted to:
  - `retrieval_lab/orchestration/bm25_mode.py`
- CLI parser wiring was extracted to:
  - `retrieval_lab/orchestration/cli_parser.py`
- Runtime wiring was re-validated with successful eval-only benchmark runs.
- Full repo tests are now green after compatibility schema restoration:
  - `uv run pytest tests` → `62 passed`
- Baseline guardrail checks continue to pass for PHB/Starfinder/S&W:
  - `uv run python -m evals.v1_baseline.assert_baseline_regression --run-dir evals/v1_baseline/20260212`

---

## 2) What Changed in This Session

### A. Config and path normalization

Updated retrieval substrate paths from `out/mark3_evaluation/...` to:

- `out/DnD_PHB_5.5`
- `out/StarFinderPlayerCore`
- `out/Swords&Wizardry`

This was applied across relevant dense/sparse/hybrid experiment YAMLs.

### B. Baseline suite docs + runner

- Updated: `evals/v1_baseline/README.md`
  - Now documents all three corpora with new `out/` paths.
  - Documents baseline + dual-list per corpus.
- Added: `evals/v1_baseline/run_baseline_suite.sh`
  - Runs PHB baseline+dual-list, Starfinder baseline+dual-list, S&W baseline+dual-list.
  - Uses `--substrate-version v1` and writes to `evals/v1_baseline/<date>/`.

### C. New dual-list configs

Added:

- `retrieval_lab/experiments/hybrid/starfinder_hybrid_dual_list_fusion.yaml`
- `retrieval_lab/experiments/hybrid/swords_wizardry_hybrid_dual_list_fusion.yaml`

### D. Baseline execution artifacts

Run set (20260212):

- `phb_hybrid_20260212_145913`
- `phb_hybrid_dual_list_fusion_20260212_150242`
- `starfinder_hybrid_20260212_151531`
- `starfinder_hybrid_dual_list_fusion_20260212_151943`
- `swords_wizardry_hybrid_20260212_153447`
- `swords_wizardry_hybrid_dual_list_fusion_20260212_153625`

Each directory contains `REPORT.md`, `metrics.json`, `failure_buckets.json`, `per_query.json`, `grounding_audit.json`, and embeddings.

### E. Consolidated baseline report

Added:

- `evals/v1_baseline/20260212/BASELINE_REPORT.md`

This is the latest narrative synthesis of the six experiments.

### F. `run_experiment` modular refactor (2026-02-13)

Refactor objective: reduce `run_experiment.py` complexity and isolate dense-mode logic.

What changed:

- `retrieval_lab/run_experiment.py`
  - Reduced from ~1100 LOC to ~550 LOC.
  - Retains high-level orchestration and core setup helpers:
    - `_prepare_experiment_corpus_context`
    - `_load_and_ground_queries`
    - `_run_experiment`
    - `main`
- Added `retrieval_lab/orchestration/dense_mode.py`
  - Contains dense/hybrid execution pipeline:
    - embedding resolution (cache/disk/compute)
    - optional family embedding flow for dual-list fusion
    - ranking/rerank/expansion
    - metrics and retrieval review assembly

Validation performed after extraction:

- Lint checks clean on refactored files.
- `py_compile` passes for `run_experiment.py` and `dense_mode.py`.
- Eval-only benchmark smoke run passed (hybrid PHB, run_id reuse), producing:
  - `evals/v1_baseline/20260212/phb_hybrid_20260213_040202/REPORT.md`

### G. Follow-up modular extraction + stabilization (2026-02-13)

Additional follow-up completed:

- Added `retrieval_lab/orchestration/bm25_mode.py` and delegated BM25 ranking/scoring/review assembly from `run_experiment.py`.
- Added `retrieval_lab/orchestration/cli_parser.py` and delegated parser construction from `run_experiment.py`.
- Restored legacy Stage A compatibility schema types in `extraction/schemas.py` (`Chunk`, `MarkerBlock`, `DropRecord`, `LogicalDocument`, `DocumentPart`, `ProvenanceSpan`) so current + legacy paths coexist.

Validation performed:

- `uv run pytest tests` → `62 passed`
- `uv run python -m retrieval_lab.run_experiment --help` → `ok`
- `uv run python -m evals.v1_baseline.assert_baseline_regression --run-dir evals/v1_baseline/20260212` → all thresholds pass

---

## 3) Key Baseline Findings (From 20260212)

Source: `evals/v1_baseline/20260212/BASELINE_REPORT.md`

- **PHB:** dual-list is near-neutral vs baseline on aggregate MRR (0.491 vs 0.490), with mixed sub-metric trade-offs.
- **Starfinder:** dual-list improves MRR (+0.013) and reduces retrieval misses (11 -> 10).
- **S&W:** dual-list gives slight MRR gain (+0.005), but ceiling remains low; `gold_not_in_candidates` is the dominant issue (12 queries).

Interpretation:

- Dual-list is likely justified for Starfinder.
- PHB needs careful guardrails by tier/suite (watch T3/conceptual behavior).
- S&W bottleneck is not ranking depth but candidate ceiling / substrate-grounding alignment.

---

## 4) Critical Documents Next Agent Must Review (In Order)

Read these before discussing next steps:

1. `evals/v1_baseline/20260212/BASELINE_REPORT.md`
2. `evals/v1_baseline/README.md`
3. `Docs/Design/v1/architecture_overview.md`
4. `Docs/Design/v1/stage_a_contract.md`
5. `Docs/Design/v1/stage_b_contract.md`
6. `Docs/Design/v1/retrieval_lab_v1.md`
7. `Docs/Design/v1/baseline_manifest.md`
8. `Docs/Design/v1/gates_stage_c_d.md`
9. `Docs/Design/SCHEMAS.json`

For historical/critique context (important for hard-review framing):

10. `Docs/Design/archive/REFACTOR-Mark-III-Design-Review.md`
11. `Docs/Design/archive/RULES_INGESTION_MARK_III_UPDATE.md`
12. `Docs/Design/archive/STAGE_C_CONTRACTv2.md`

---

## 5) Hard-Critique Charter (What to Critique)

The user requested a top-to-bottom hard critique. The next agent should assess:

- **Contract integrity:** Are Stage A/B boundaries actually enforced in code, not just docs?
- **Determinism guarantees:** Any hidden nondeterminism in iteration/order/cache keying?
- **Retrieval methodology validity:** Are we overfitting to current eval sets or masking failures via metric selection?
- **Failure taxonomy quality:** Do failure buckets distinguish root causes cleanly enough for action?
- **Eval set quality:** `no_gold_defined`, page anchoring assumptions, and tier balance risks.
- **Dual-list trade-offs:** Where gains are real vs superficial; where regressions are masked by aggregate metrics.
- **S&W bottleneck analysis:** Why gold never enters candidate set for many queries (substrate, grounding, query shape, or config artifacts).
- **Operational reproducibility:** Can another machine rerun and get same outcomes without hidden local state assumptions?

The critique should prioritize concrete defects/risks, not style commentary.

---

## 6) Discussion-First Requirement (Do This Before New Design)

The next agent should **not** jump into implementation. First:

1. Present critique findings ordered by severity.
2. Call out assumptions and unknowns explicitly.
3. Discuss with user and align on:
   - what is a true defect vs acceptable trade-off,
   - what to fix first,
   - what to defer.
4. Only then propose a phased plan for tweaks/upgrades.

---

## 7) Suggested First Conversation Agenda with User

Use this structure in the first response:

1. **Top 5 hard findings** with direct file references.
2. **Metric truth table** (where dual-list helps/hurts by corpus and tier).
3. **S&W deep-dive hypothesis set** (ranked by likelihood, with verification steps).
4. **Proposed validation experiments** (small, falsifiable, cheap to run).
5. **Decision points** requiring user preference (e.g., prioritize ceiling vs rank quality vs throughput).

---

## 8) Useful Commands for Next Agent

From `RulesIngestion/`:

```bash
# Re-run all baselines (baseline + dual-list for all corpora)
./evals/v1_baseline/run_baseline_suite.sh

# Manual single run example
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/hybrid/starfinder_hybrid_dual_list_fusion.yaml \
  --output evals/v1_baseline/20260212 \
  --substrate-version v1

# Fast eval-only smoke check against existing embeddings
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/hybrid/phb_hybrid.yaml \
  --run-id retrieval_lab_DnD_PHB_5.5_v1 \
  --output evals/v1_baseline/20260212 \
  --substrate-version v1
```

---

## 9) Current Working Tree Notes

At handoff time, there are many modified/untracked files tied to this refactor + baseline cycle (configs, docs, eval artifacts).  
One notable status entry to verify before commit planning:

- `D evals/archive/pre_v1/README.md`

Treat this carefully: confirm whether deletion is intended before finalizing commits.

---

## 10) Success Criteria for the Next Agent

The next agent succeeds if it:

- Produces a rigorous critique grounded in code/docs/eval artifacts.
- Surfaces the highest-leverage risks and blind spots.
- Aligns with the user on critique conclusions **before** designing changes.
- Leaves a clear, prioritized plan for upgrades backed by evidence.

---

## 11) Benchmark Hardening Addendum (Highest-Leverage Next Work)

**Intent:** Make the benchmark hard to game while keeping it cheap to expand, so retrieval changes can be trusted for both objectives:

1. **Best single cite** (early precision / first relevant unit)
2. **Complete cite set** (multi-unit composition coverage)

This addendum should be treated as the next execution priority after current modularization stabilization.

### A. Why this is now the bottleneck

- Retrieval Lab is already the evaluation choke point for tiers/failure taxonomy and should remain the source of truth for regression decisions.
- Current production retrieval shape relies on dual-list fusion + retrieval-only clause-family projection.
- Without benchmark hardening, changes can appear to improve aggregate metrics while only reshuffling early ranks instead of improving composition coverage.

### B. Required split: gating suite vs expansion suite

Implement and maintain two benchmark tracks:

1. **Gating Suite (merge-blocking)**
   - Small, hand-audited, stable.
   - Balanced across T1/T2/T3 and across PHB/Starfinder/S&W.
   - Used for release/default retrieval decisions.

2. **Expansion Suite (non-blocking trend)**
   - Large, auto-generated, confidence-tagged.
   - Used for dashboarding, mining regressions, and candidate promotion.
   - Never blocks merges until examples are human-promoted.

### C. Query-level contract update (must support both objectives)

Every benchmark item should explicitly represent required vs optional evidence:

- `required_gold`: minimal set required for correctness
- `supporting_gold`: useful but optional evidence
- `mode`: `single_cite | multi_required | multi_supported`

Scoring must include two metric families:

1. **Best-cite metrics**
   - MRR / H@k on first required unit

2. **Set metrics**
   - FullSetHit@k over `required_gold`
   - RequiredRecall@k
   - Rank-of-last-required (depth needed to complete required set)

### D. Benchmark integrity checks (cheap, deterministic, CI-ready)

Add fast integrity checks that fail CI when benchmark quality regresses:

- **Gold existence:** every required/supporting unit id resolves for book + substrate version.
- **Gold non-triviality:** required units meet minimal quality floor.
- **Copy leakage guard:** question text has bounded n-gram overlap with gold text.

Suggested implementation target:
- `evals/v1_baseline/benchmark_integrity_check.py` (or equivalent under `retrieval_lab/`)
- Hook to baseline/CI path after config+substrate resolution and before scoring.

### E. EvidenceUnit quality audit (contract verification, not retrieval tuning)

Treat “self-contained EvidenceUnit quality” as a measured contract:

1. **Step A (immediate): audit only**
   - Add deterministic quality heuristics and report distribution + failure tail:
     - too short (chars/words)
     - dangling anaphora cues (`it/this/these/above/below/following`) without local anchor
     - header-only / label-only
     - mid-thought procedure fragments
   - Produce dashboard/report + failing threshold (can be warn-first initially).

2. **Step B (later): correctness fixes**
   - Change Stage B only if audit proves contract violations.
   - Do not mutate EvidenceUnits solely to improve retrieval metrics.
   - If fragmentary units are common, treat as Stage B decomposition correctness issue (or explicitly relax contract with ADR).

### F. Citation-first generation pipeline for expansion suite

To scale benchmark generation without losing trust:

1. Choose deterministic anchor unit(s) first.
2. Extract deterministic “questionable atoms” from anchors (definitions, constraints, exceptions, scaling clauses).
3. Use LLM only for question paraphrase/naturalization.
4. Keep citations locked to anchor set (LLM does not pick citations).
5. Promotion path:
   - auto-gen -> integrity checks -> human sample review -> promote to gating suite

### G. Decision policy for next agent

When metrics move, classify outcome explicitly:

- **Coverage gain:** required set reached more often / earlier.
- **Rank shuffle only:** first ranks changed without required-set improvement.
- **Fragment repair signal:** clause family improves because units are fragmentary (Stage B concern).

Do not accept “aggregate MRR up” as sufficient by itself.

### H. Concrete next-agent deliverables

1. Draft benchmark schema update for required/supporting/mode fields.
2. Add integrity-check runner and wire into baseline workflow.
3. Add EvidenceUnit quality audit runner + threshold report.
4. Produce one recommendation memo:
   - whether current wins are composition coverage vs rank reshuffle
   - whether Stage B contract appears violated by fragmentary units
5. Propose promotion process from expansion -> gating with explicit acceptance criteria.

### I. Constraints to preserve during this work

- Preserve frozen v1 baseline comparability (do not silently rewrite existing gated benchmark artifacts).
- Keep retrieval-only projections non-admissible in reporting semantics.
- Separate evaluation-harness changes from retrieval-algorithm changes where possible.

---

## 12) Post-Execution Update: Low-Hanging Tuning Completed (2026-02-13)

This section records what has now been empirically validated after implementing the low-hanging tuning plan and running full sweeps.

### A. New artifacts produced

- `evals/v1_baseline/20260212/LOW_HANGING_SWEEP_SUMMARY.json`
- `evals/v1_baseline/20260212/LOW_HANGING_TUNING_REPORT.md`

### B. What is now considered done/solid

1. **RRF k can be treated as stable default**
   - PHB / Starfinder / S&W showed effectively zero meaningful sensitivity across tested `k` values.
   - Keep `rrf_k=60` as default.

2. **Global BM25 defaults are still correct**
   - PHB and S&W regressed under alternative BM25 parameterizations.
   - Starfinder showed a small isolated gain under one variant, but not enough to justify global default change.

3. **Measurement hardening is now in place**
   - `nDCG@k` added.
   - Failure-bucket deltas vs baseline added to report path.
   - Stage timing surfaced in reports.
   - Benchmark integrity checker implemented.

4. **S&W sidecar/pairing probes are falsified under current substrate/queries**
   - No material effect on ceiling or MRR.
   - Keep these off by default for now.

### C. Most important new signal

For S&W, query expansion is the first tested lever that moved candidate ceiling:

- `gold_not_in_candidates`: `12 -> 11`
- `gold_in_candidates`: `0.52 -> 0.56`

But this came with rank-quality regression (MRR drop). This strongly indicates:

- S&W is currently **recall/lexical mismatch constrained first**.
- Ranking quality recovery is the second-stage problem.

### D. Immediate next plan (high leverage, low thrash)

Implement explicit **two-stage S&W retrieval**:

1. **Stage 1 (candidate admission objective)**
   - Expanded query representation allowed.
   - Optimize for ceiling / candidate recall.

2. **Stage 2 (ranking objective)**
   - Rerank with strict question-only representation (or best available reranker).
   - Optimize to recover MRR while preserving Stage 1 ceiling gain.

Success criterion:

- Keep improved ceiling (`gold_not_in_candidates` improved vs baseline),
- while recovering MRR toward baseline dual-list performance.

If no cross-encoder is available immediately:

- Use dense-only rerank over Stage 1 candidates, or
- Use calibrated fusion where expansion path contributes to admission only, not final rank score.

### E. Benchmark contract critique to carry forward

The S&W behavior (ceiling up, MRR down) is exactly what appears when benchmarks do not cleanly separate:

- required citations vs supporting citations,
- single-cite vs multi-cite objectives.

Therefore the next benchmark evolution remains mandatory:

- add `required_gold`, `supporting_gold`, and `mode`,
- score both first-hit quality and required-set completion quality.

### F. Updated default policy recommendation (for now)

- Keep `rrf_k=60` globally.
- Keep current global BM25 defaults.
- Do not enable S&W sidecar/pairing by default.
- Treat two-stage S&W retrieval as the active optimization thread.
- Keep benchmark integrity checks always-on in baseline workflows.

---

## 13) Post-Execution Update: Plan Implementation Completed (2026-02-13)

This section records completion of the benchmark-first implementation plan and should be treated as the new execution baseline.

### A. Delivered work (implemented)

1. **Benchmark contract hardening (backward compatible)**
   - Added support for `required_gold`, `supporting_gold`, `mode` while preserving legacy `gold_unit_ids`.
   - Normalized query-level gold fields in:
     - `retrieval_lab/gold_grounding.py`
   - Added required-set metric family in:
     - `retrieval_lab/metrics.py`
   - Reporting now includes required-set metrics and rank-depth signals in:
     - `retrieval_lab/report.py`

2. **Integrity policy split + EvidenceUnit quality audit**
   - Added policy-aware integrity modes (`strict`/`warn`) and explicit status output in:
     - `evals/v1_baseline/benchmark_integrity_check.py`
   - Added deterministic EvidenceUnit quality audit heuristics:
     - short-unit tail
     - dangling-reference tail
     - header-only tail
     - fragmentary-procedure tail
   - Wired baseline matrix runner to emit integrity JSON + markdown and support policy split in:
     - `evals/v1_baseline/run_baseline_suite.py`

3. **Two-stage retrieval seam (flagged, non-default)**
   - Added Stage 1 admission + Stage 2 rerank controls in:
     - `retrieval_lab/config.py`
     - `retrieval_lab/orchestration/cli_parser.py`
     - `retrieval_lab/orchestration/cli.py`
     - `retrieval_lab/orchestration/config_access.py`
   - Added dense-path two-stage rerank seam in:
     - `retrieval_lab/orchestration/dense_mode.py`

4. **Outcome classification**
   - Report and metrics now emit outcome labels:
     - `coverage_gain`
     - `rank_shuffle_only`
     - `fragment_repair_signal`
   - Implemented in:
     - `retrieval_lab/report.py`
     - `retrieval_lab/run_experiment.py` (baseline metric wiring for deltas)

5. **Promotion governance updates**
   - Updated baseline governance and promotion notes in:
     - `evals/v1_baseline/README.md`
     - `Docs/Design/v1/baseline_manifest.md`

### B. Validation completed

- Focused retrieval tests:
  - `uv run pytest tests/retrieval_lab/test_metrics.py tests/retrieval_lab/test_config.py tests/retrieval_lab/test_gold_grounding.py tests/retrieval_lab/test_sparse_retrieval.py tests/retrieval_lab/test_two_stage_retrieval.py`
  - Result: `22 passed`
- Additional grounding/substrate tests:
  - `uv run pytest tests/retrieval_lab/test_substrate_loader.py tests/retrieval_lab/test_gold_grounding.py`
  - Result: `5 passed`
- Syntax/CLI checks:
  - `uv run python -m py_compile ...` (updated modules) -> pass
  - `uv run python -m retrieval_lab.run_experiment --help` -> pass
  - `uv run python -m evals.v1_baseline.benchmark_integrity_check --help` -> pass
- Baseline guardrails:
  - `uv run python -m evals.v1_baseline.assert_baseline_regression --run-dir evals/v1_baseline/20260212`
  - Result: pass for PHB / Starfinder / S&W dual-list guard checks

### C. New artifacts produced during execution

- Eval smoke run:
  - `evals/v1_baseline/20260212/phb_hybrid_20260213_050943/`
- Integrity smoke artifacts:
  - `evals/v1_baseline/20260212/integrity_phb_hybrid_smoke.json`
  - `evals/v1_baseline/20260212/integrity_phb_hybrid_smoke.md`

### D. Updated defaults / operating policy

- Keep global defaults unchanged unless explicitly A/B promoted:
  - `rrf_k=60`
  - current global BM25 defaults
- Keep two-stage retrieval behind explicit flags until corpus-specific validation passes.
- Treat required-set metrics as first-class for promotion decisions; do not accept aggregate MRR movement alone.

### E. Next-agent priority queue

1. Run corpus-specific two-stage sweeps for S&W and evaluate:
   - ceiling retention/improvement
   - MRR recovery vs baseline dual-list
2. Build/curate expansion-suite candidates with required/supporting/mode fields populated.
3. Promote only candidates passing strict integrity + required-set non-regression criteria.
4. If quality-audit tails remain high, open a Stage B contract-correctness thread (separate from retrieval tuning).


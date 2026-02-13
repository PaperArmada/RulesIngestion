# Handoff: Hard Critique Prep (Top-to-Bottom)

**Date:** 2026-02-12  
**Repo:** `RulesIngestion`  
**Intent for next agent:** Run a deep, end-to-end critique of code + contracts + eval methodology, then discuss findings with the user **before** proposing design/implementation steps.

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


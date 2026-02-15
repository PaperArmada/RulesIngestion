# Handoff: Move Baseline Process to C (Raw-First Merge-Rerank)

**Date:** 2026-02-15  
**Repo:** `RulesIngestion`  
**Audience:** Next agent maintaining baseline experiments and retrieval quality gates  
**Decision:** Adopt **C** as the baseline process to build on.

---

## 1) What "C" Is

C is the **raw-first merge-rerank** policy implemented in retrieval orchestration:

1. Retrieve on **unmerged** EvidenceUnits using hybrid retrieval (dense + BM25, RRF).
2. Dense rerank the raw admission pool.
3. Promote admitted raw hits to heading-merged candidates via `source_unit_ids`.
4. Dense rerank merged candidates.
5. Apply monotonic safeguards so strong raw anchors are not demoted after merge:
   - score floor (`raw_merge_score_floor`)
   - rank floor (`raw_merge_rank_floor`)

This is now feature-flagged and implemented in:

- `retrieval_lab/config.py`
- `retrieval_lab/orchestration/config_access.py`
- `retrieval_lab/orchestration/cli_parser.py`
- `retrieval_lab/orchestration/cli.py`
- `retrieval_lab/orchestration/dense_mode.py`
- `retrieval_lab/report.py`

---

## 2) Why C Works (Mechanically)

The prior baseline choice was forced to pick between two imperfect extremes:

- raw-only (A): good atomic recall in some cases, weak context packaging;
- merged-only (B): better context, but can lose atomic anchor fidelity.

C combines both strengths:

- **raw retrieval first** preserves atomic discoverability;
- **merged rerank second** restores context-rich chunks for downstream use;
- **monotonic constraints** prevent the known failure mode where a strong raw unit gets buried after promotion.

The diagnostic contract for C is explicit and machine-checked:

- `monotonic_rank_violations_total` must stay 0
- `raw_top_missing_in_final_topk_total` must stay 0

---

## 3) Evidence Summary

All results below use `all-mpnet-base-v2`.

### PHB (already run and validated)

- C reproducible on full PHB (rerun deltas all 0).
- C beats A on MRR and required-set metrics.
- B still outperforms C on PHB headline ranking quality.
- H3 safety is fully satisfied (violations=0, raw-top-missing=0).

Interpretation: C is stable and safe; quality is materially improved over A but not yet universally better than B.

### Starfinder (new run)

Runs:

- A: `starfinder_hybrid_raw_only_20260215_041122`
- B: `starfinder_hybrid_merged_only_20260215_041129`
- C: `starfinder_hybrid_raw_first_merge_rerank_20260215_041134`
- C repro: `starfinder_hybrid_raw_first_merge_rerank_20260215_041616`

Key metrics:

- A: MRR `0.447638`, ceiling `0.808511`
- B: MRR `0.377816`, ceiling `0.680851`
- C: MRR `0.526690`, ceiling `0.851064`, violations `0`, raw-top-missing `0`

Interpretation: C is clearly best on Starfinder and reproducible.

### Swords & Wizardry (new run)

Runs:

- A: `swords_wizardry_hybrid_raw_only_20260215_041409`
- B: `swords_wizardry_hybrid_merged_only_20260215_041414`
- C: `swords_wizardry_hybrid_raw_first_merge_rerank_20260215_041419`
- C repro: `swords_wizardry_hybrid_raw_first_merge_rerank_20260215_041846`

Key metrics:

- A: MRR `0.281428`, ceiling `0.560000`
- B: MRR `0.364051`, ceiling `0.640000`
- C: MRR `0.285051`, ceiling `0.560000`, violations `0`, raw-top-missing `0`

Interpretation: C is safe and reproducible, but currently underperforms B on this corpus.

---

## 4) Why We Still Make C the Baseline Process

Despite mixed absolute ranking wins vs B across all corpora, C should be the baseline process because:

1. **Safety is guaranteed and verified** (H3 pass across PHB, Starfinder, S&W).
2. **Generalization is better than A**, and strongly better on Starfinder.
3. **Architecture is extensible**: C gives us a principled scaffold for future tuning:
   - floor weighting policy,
   - coverage bonus,
   - admission depth,
   - merged rerank objective.
4. **Benchmark quality is not uniform across corpora** (notably S&W), so selecting B as the long-term baseline would optimize for current score shape without preserving raw-anchor integrity.

Decision framing: C is the **engineering baseline** (safety + composability) we iterate from, not the final tuned optimum for every corpus today.

---

## 5) Required Baseline Process Updates

### 5.1 Baseline definition

Update baseline docs/scripts so "baseline run" means **C policy enabled**.

Required C flags:

- `raw_first_merge_rerank: true`
- `merge_chunks: false` (raw substrate admission)
- `raw_stage1_admission_k: 100` (or corpus-tuned)
- `raw_merge_rerank_top_k: max(top_k)`
- `raw_merge_score_floor: true`
- `raw_merge_rank_floor: true`
- `raw_merge_coverage_bonus: 0.0` (initially)
- `two_stage_retrieval: true`
- `stage2_rerank_method: dense`

### 5.2 Regression gates

Baseline assertion must include C diagnostics:

- hard-fail if `monotonic_rank_violations_total != 0`
- hard-fail if `raw_top_missing_in_final_topk_total != 0`

### 5.3 Reporting

Baseline report must always include:

- hypothesis table (H1/H2/H3)
- A/B/C deltas for:
  - `gold_in_candidates_true_ceiling`
  - `mrr`
  - `required_full_set_hit_at_k` (10/20)
  - `rank_of_last_required_mean`
- C diagnostic totals and representative per-query examples.

---

## 6) Migration Plan (Next Agent)

1. Update baseline runner/config pack to make C the default execution mode.
2. Keep A and B runnable as comparison modes (not default).
3. Update baseline regression script to enforce C safety diagnostics.
4. Update baseline docs to define C as canonical process.
5. Re-run full tri-corpus baseline bundle with C-default + A/B comparators.
6. Publish updated baseline report with explicit rationale and deltas.

---

## 7) Risks and Follow-Up

Known risk:

- S&W currently favors merged-only for MRR/ceiling.

Follow-up experiments (on C baseline):

1. tune `raw_merge_coverage_bonus` > 0,
2. tune `raw_stage1_admission_k`,
3. tune merged rerank weighting against raw score floor,
4. inspect S&W per-query misses where B > C and classify causes (gold quality vs ranking behavior).

---

## 8) Source Artifacts

Primary run directory:

- `evals/v1_baseline/20260215_cross_book_raw_merge_exp`

Key reports:

- `starfinder_hybrid_raw_first_merge_rerank_20260215_041134/REPORT.md`
- `starfinder_hybrid_raw_first_merge_rerank_20260215_041616/REPORT.md` (repro)
- `swords_wizardry_hybrid_raw_first_merge_rerank_20260215_041419/REPORT.md`
- `swords_wizardry_hybrid_raw_first_merge_rerank_20260215_041846/REPORT.md` (repro)

PHB references (prior wave):

- `evals/v1_baseline/20260214_raw_merge_exp/phb_hybrid_raw_first_merge_rerank_20260214_233417/REPORT.md`
- `evals/v1_baseline/20260214_raw_merge_exp/phb_hybrid_raw_first_merge_rerank_20260215_035519/REPORT.md` (repro)


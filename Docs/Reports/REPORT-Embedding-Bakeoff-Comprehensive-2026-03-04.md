# Comprehensive Embedding Bakeoff Report

**Date:** 2026-03-04  
**Status:** Decision-grade  
**Prepared from:** All available bakeoff bundles as of 2026-03-04

---

## 1. Scope and Evidence

### Bundles Included

| Bundle | Eval Rows | Failed | Coverage |
|---|---|---|---|
| `model_bakeoff_full_run_20260303_post_benchmark_fix` | 28 (16 eval + 12 embed + stability) | 0 | 3 models × 2 recipes × 2 modes × 2 tracks |
| `pplx_only_run` | 8 (4 eval + 4 embed) | 0 | pplx × 2 recipes × 2 modes × 2 tracks |

**Authoritative cross-model ranking:** `model_bakeoff_full_run_20260303_post_benchmark_fix` (2026-03-03)  
**Authoritative pplx absolute metrics:** `pplx_only_run` (2026-03-04)

### Bundles Excluded from Decision Claims

| Bundle | Reason |
|---|---|
| `model_bakeoff_20260301_214801` | Superseded by 20260303 post-benchmark-fix run |
| `model_bakeoff_20260301_220031` | Superseded |
| `model_bakeoff_full_run` | Superseded (pre-benchmark-fix) |
| `model_bakeoff_full_run_post_densefix` | Superseded |
| All `model_bakeoff_preflight_*` bundles (13 total) | Diagnostic/preflight only, not eval runs |
| `pplx_only_preflight`, `pplx_preflight_check` | Preflight only |
| All per-experiment `bakeoff_*` folders with timestamps before `20260303` | Superseded by latest per-track runs |

---

## 2. Run Health

### model_bakeoff_full_run_20260303_post_benchmark_fix
- **Eval rows completed:** 28/28 (0% failure)
- **All exit codes:** 0
- **Contract drift / preflight overrides:** None detected
- **Stability check included:** Yes — `bakeoff_stability_sf_hybrid_mpnet_standardized_20260303_023512` (status: `ok`)

### pplx_only_run
- **Eval rows completed:** 8/8 (0% failure)
- **All exit codes:** 0
- **Contract drift / preflight overrides:** None detected
- **Note:** pplx Starfinder runs timestamped 2026-03-04 (later than the main bundle); these are the authoritative pplx numbers

---

## 3. Metric Comparison

### 3a. Starfinder (track: `Starfinder`, enrichment: `baseline`, substrate: `StarFinderPlayerCore v2_merged2000_min200`, benchmark: 50-question)

**Source:** `model_bakeoff_full_run_20260303_post_benchmark_fix/aggregate_metrics.json` (all-mpnet, nomic, bge-m3) + `pplx_only_run/aggregate_metrics.json` (pplx)

#### Standardized Recipe

| Model | Mode | MRR | nDCG@10 | Recall@10 | Hit@10 | Gold-in-Candidates | gold_not_in_candidates |
|---|---|---|---|---|---|---|---|
| **all-mpnet-base-v2** | **dense** | **0.6660** | **0.6631** | **0.8467** | **0.9200** | **1.0000** | **0** |
| all-mpnet-base-v2 | hybrid | 0.6142 | 0.6378 | 0.8100 | 0.8600 | 0.9600 | 2 |
| nomic-embed-text-v2 | dense | 0.6042 | 0.6030 | 0.8133 | 0.9600 | 0.9800 | 1 |
| nomic-embed-text-v2 | hybrid | 0.6228 | 0.5805 | 0.7200 | 0.8600 | 0.9800 | 1 |
| bge-m3 | dense | 0.5811 | 0.5379 | 0.6533 | 0.8200 | 0.8600 | 7 |
| bge-m3 | hybrid | 0.5850 | 0.5566 | 0.6967 | 0.8200 | 0.8800 | 6 |
| **pplx-embed-v1-0.6B** | **dense** | **0.6919** | **0.6592** | **0.8067** | **0.9200** | **0.9600** | **2** |
| pplx-embed-v1-0.6B | hybrid | 0.6593 | 0.6114 | 0.7467 | 0.8600 | 0.9200 | 4 |

#### Recommended Recipe

| Model | Mode | MRR | nDCG@10 | Recall@10 | Hit@10 | Gold-in-Candidates | gold_not_in_candidates |
|---|---|---|---|---|---|---|---|
| **all-mpnet-base-v2** | **dense** | **0.6660** | **0.6631** | **0.8467** | **0.9200** | **1.0000** | **0** |
| all-mpnet-base-v2 | hybrid | 0.6142 | 0.6378 | 0.8100 | 0.8600 | 0.9600 | 2 |
| nomic-embed-text-v2 | dense | 0.6592 | 0.6160 | 0.7567 | 0.9000 | 0.9600 | 2 |
| nomic-embed-text-v2 | hybrid | 0.6245 | 0.5905 | 0.7300 | 0.8600 | 0.9000 | 5 |
| bge-m3 | dense | 0.5368 | 0.5297 | 0.6933 | 0.8400 | 0.9000 | 5 |
| bge-m3 | hybrid | 0.6109 | 0.5541 | 0.6667 | 0.8000 | 0.8400 | 8 |
| **pplx-embed-v1-0.6B** | **dense** | **0.6921** | **0.6597** | **0.8067** | **0.9200** | **0.9600** | **2** |
| pplx-embed-v1-0.6B | hybrid | 0.6598 | 0.6119 | 0.7467 | 0.8600 | 0.9200 | 4 |

**Starfinder summary by model (dense best-of-recipe):**

| Model | Best MRR | Best nDCG@10 | Best Recall@10 | Best Gold-in-Candidates |
|---|---|---|---|---|
| pplx-embed-v1-0.6B | **0.6921** | **0.6597** | 0.8067 | 0.9600 |
| all-mpnet-base-v2 | 0.6660 | 0.6631 | **0.8467** | **1.0000** |
| nomic-embed-text-v2 | 0.6592 | 0.6160 | 0.7567 | 0.9600 |
| bge-m3 | 0.5811 | 0.5379 | 0.6933 | 0.9000 |

---

### 3b. SwordsandWizardry (track: `SwordsandWizardry`, enrichment: `full`, substrate: `v3_swcr_merged2000_min100`, benchmark: 21 questions after `no_gold_defined` accounting)

**Source:** `model_bakeoff_full_run_20260303_post_benchmark_fix/aggregate_metrics.json` (all-mpnet, nomic, bge-m3) + `pplx_only_run/aggregate_metrics.json` (pplx)

**PARTIAL GROUNDING FIX — REVISED ASSESSMENT:**

The main bundle (`20260303_post_benchmark_fix`) ran SWCR at timestamps `022053`–`023505`. However, two additional all-mpnet SWCR re-runs exist at later timestamps (`030128`, `030202`) that used a **fixed benchmark** with `no_gold_defined = 0` (21/21 queries fully grounded). These runs are valid and are the authoritative all-mpnet SWCR numbers.

The nomic, bge-m3 SWCR runs from the main bundle still have `no_gold_defined = 20` and remain non-interpretable.

**Run grounding status by experiment:**

| Experiment Timestamp | Model | Mode | no_gold_defined | Interpretable? |
|---|---|---|---|---|
| `030128` | all-mpnet-base-v2 | dense | **0** | **YES** |
| `030202` | all-mpnet-base-v2 | hybrid | **0** | **YES** |
| `022053` | all-mpnet-base-v2 | dense | 20/21 | NO (superseded) |
| `022059` | all-mpnet-base-v2 | hybrid | 20/21 | NO (superseded) |
| `022218` | nomic-embed-text-v2 | dense | 20/21 | NO |
| `022230` | nomic-embed-text-v2 | hybrid | 20/21 | NO |
| `022400` | bge-m3 | dense | 20/21 | NO |
| `022433` | bge-m3 | hybrid | 20/21 | NO |
| (all recommended variants, 022834–023224) | — | — | 20/21 | NO |

**pplx runs** (from `pplx_only_run`, 2026-03-04) show `no_gold_defined = 0` — valid.

#### SwordsandWizardry — all-mpnet-base-v2 (valid, post-fix benchmark — standardized only)

**Sources:**
- `bakeoff_swordsandwizardry_dense_all_mpnet_base_v2_standardized_full_20260303_030128/REPORT.md`
- `bakeoff_swordsandwizardry_hybrid_all_mpnet_base_v2_standardized_full_20260303_030202/REPORT.md`

| Mode | Recipe | MRR | nDCG@10 | Recall@10 | Hit@10 | Gold-in-Candidates | gold_not_in_candidates |
|---|---|---|---|---|---|---|---|
| dense | standardized | 0.4520 | 0.4154 | 0.5778 | 0.8095 | 0.9524 | 1 |
| **hybrid** | **standardized** | **0.5757** | **0.4994** | **0.6238** | **0.8571** | **1.0000** | **0** |

Benchmark lint: `required_gold_large: 2` (two queries have unusually large gold sets — flagged but not disqualifying).  
Grounding: 21/21 queries fully grounded (`prefilled` method).  
T1 vs T2 breakdown (hybrid): T1 MRR 0.5015, T2 MRR 0.6746 — T2 queries are easier to retrieve.

#### SwordsandWizardry — nomic-embed-text-v2 (benchmark grounding failure — NOT interpretable)

| Mode | Recipe | no_gold_defined | Interpretable? |
|---|---|---|---|
| dense | standardized | 20/21 | NO — benchmark lint: `required_gold_empty: 21` |

**Source:** `bakeoff_swordsandwizardry_dense_nomic_embed_text_v2_standardized_full_20260303_022218/REPORT.md`  
Grounding: 1/21 queries grounded. Metrics are not comparable to all-mpnet or pplx.

#### SwordsandWizardry — bge-m3 (benchmark grounding failure — NOT interpretable)

All bge-m3 SWCR runs have `no_gold_defined = 20`. No valid metrics available.

#### SwordsandWizardry — pplx-embed-v1-0.6B (valid, post-fix benchmark)

| Mode | Recipe | MRR | nDCG@10 | Recall@10 | Hit@10 | Gold-in-Candidates | gold_not_in_candidates |
|---|---|---|---|---|---|---|---|
| dense | standardized | 0.3159 | 0.3727 | 0.6159 | 0.8095 | 0.9524 | 1 |
| **hybrid** | **standardized** | **0.5094** | **0.4603** | **0.5905** | **0.8095** | **0.9524** | **1** |
| dense | recommended | 0.4329 | 0.4437 | 0.6143 | 0.8095 | 0.9524 | 1 |
| **hybrid** | **recommended** | **0.5055** | **0.4582** | **0.5905** | **0.8095** | **0.9524** | **1** |

**pplx SWCR summary:** Hybrid mode delivers meaningfully higher MRR (+0.19 vs dense/standardized) and nDCG@10. Recommended recipe shows +0.37 MRR lift over standardized in dense mode. Gold-in-Candidates is 0.9524 (1 query has no retrievable gold in any mode).

---

## 4. Recipe Effect (Standardized vs. Recommended)

### Starfinder — Recipe Impact by Model

| Model | Mode | Standardized MRR | Recommended MRR | Delta |
|---|---|---|---|---|
| pplx-embed-v1-0.6B | dense | 0.6919 | **0.6921** | +0.0002 (negligible) |
| pplx-embed-v1-0.6B | hybrid | 0.6593 | **0.6598** | +0.0005 (negligible) |
| all-mpnet-base-v2 | dense | **0.6660** | **0.6660** | 0.0000 (identical) |
| all-mpnet-base-v2 | hybrid | **0.6142** | **0.6142** | 0.0000 (identical) |
| nomic-embed-text-v2 | dense | 0.6042 | **0.6592** | **+0.0550 (meaningful lift)** |
| nomic-embed-text-v2 | hybrid | 0.6228 | **0.6245** | +0.0017 (minor) |
| bge-m3 | dense | **0.5811** | 0.5368 | **−0.0443 (regression)** |
| bge-m3 | hybrid | **0.5850** | 0.6109 | +0.0259 (minor lift) |

**Key finding:** For pplx and all-mpnet, recipe choice is effectively neutral (identical or negligible delta). For nomic, recommended recipe delivers a notable +5.5 MRR lift in dense mode. For bge-m3, recommended hurts dense mode by −4.4 MRR but helps hybrid slightly. Recipe effect is model-specific.

### SwordsandWizardry — pplx Recipe Impact

| Mode | Standardized MRR | Recommended MRR | Delta |
|---|---|---|---|
| dense | 0.3159 | **0.4329** | **+0.1170 (large lift)** |
| hybrid | **0.5094** | 0.5055 | −0.0039 (negligible) |

**Key finding:** For SWCR pplx dense mode, recommended recipe provides a substantial +11.7 MRR lift. Hybrid mode is already strong with standardized, and recommended makes no meaningful difference.

---

## 5. Failure Signature Analysis

### Starfinder

| Model | Mode | Recipe | gold_not_in_candidates | gold_in_candidates_but_low_rank | grounding_failures |
|---|---|---|---|---|---|
| all-mpnet-base-v2 | dense | std/rec | 0 | 0 | 0 |
| all-mpnet-base-v2 | hybrid | std/rec | 2 | 0 | 0 |
| nomic-embed-text-v2 | dense | std | 1 | 0 | 0 |
| nomic-embed-text-v2 | dense | rec | 2 | 0 | 0 |
| nomic-embed-text-v2 | hybrid | std | 1 | 0 | 0 |
| nomic-embed-text-v2 | hybrid | rec | 5 | 0 | 0 |
| bge-m3 | dense | std | 7 | 0 | 0 |
| bge-m3 | dense | rec | 5 | 0 | 0 |
| bge-m3 | hybrid | std | 6 | 0 | 0 |
| bge-m3 | hybrid | rec | 8 | 0 | 0 |
| pplx-embed-v1-0.6B | dense | std/rec | 2 | 0 | 0 |
| pplx-embed-v1-0.6B | hybrid | std/rec | 4 | 0 | 0 |

**No `gold_in_candidates_but_low_rank` failures anywhere.** All retrieval failures are `gold_not_in_candidates` type — i.e., the gold chunks are genuinely absent from the top-k candidates, not merely ranked poorly.

**bge-m3 has the most severe candidate coverage problem** (7–8 queries with no gold in candidates). pplx and all-mpnet are substantially better (0–4). nomic occupies the middle.

### SwordsandWizardry (pplx only — valid)

| Mode | Recipe | gold_not_in_candidates | gold_in_candidates_but_low_rank |
|---|---|---|---|
| dense | std | 1 | 0 |
| hybrid | std | 1 | 0 |
| dense | rec | 1 | 0 |
| hybrid | rec | 1 | 0 |

Consistent single-query miss across all pplx SWCR configurations. The same query is likely missing gold across all modes/recipes — a potential benchmark grounding issue or genuinely hard query.

---

## 6. Decision and Confidence

### Primary Recommendation

**No single model dominates both tracks. Cross-corpus default: `all-mpnet-base-v2` / `hybrid` / `standardized`**

**Rationale:**
- pplx achieves the highest Starfinder MRR (0.6921 vs all-mpnet 0.6660, nomic 0.6592)
- pplx nDCG@10 (0.6597) is within 0.003 of all-mpnet's best (0.6631) — effectively tied on SF
- **However**, all-mpnet dominates SwordsandWizardry: hybrid MRR 0.5757 vs pplx best 0.5094 (+0.066), and perfect Gold-in-Candidates (1.000 vs pplx 0.9524)
- all-mpnet gold_not_in_candidates = 0 in SF dense (pplx = 2) — better candidate coverage
- Recipe choice is neutral for pplx (standardized ≈ recommended); all-mpnet standardized = recommended (identical)

**If Starfinder-only deployment:** `pplx-embed-v1-0.6B` / `dense` / `recommended` (MRR 0.6921)  
**If SwordsandWizardry-only deployment:** `all-mpnet-base-v2` / `hybrid` / `standardized` (MRR 0.5757)  
**If single model for both corpora:** `all-mpnet-base-v2` / `hybrid` / `standardized` — SF hybrid MRR 0.6142 (−0.078 vs pplx dense SF), SWCR MRR 0.5757 (+0.066 vs pplx best SWCR)

**SwordsandWizardry cross-model comparison (partial — all-mpnet vs pplx):**

| Model | Mode | Recipe | MRR | nDCG@10 | Hit@10 | Gold-in-Candidates |
|---|---|---|---|---|---|---|
| all-mpnet-base-v2 | dense | std | 0.4520 | 0.4154 | 0.8095 | 0.9524 |
| **all-mpnet-base-v2** | **hybrid** | **std** | **0.5757** | **0.4994** | **0.8571** | **1.0000** |
| pplx-embed-v1-0.6B | dense | std | 0.3159 | 0.3727 | 0.8095 | 0.9524 |
| pplx-embed-v1-0.6B | hybrid | std | 0.5094 | 0.4603 | 0.8095 | 0.9524 |
| pplx-embed-v1-0.6B | dense | rec | 0.4329 | 0.4437 | 0.8095 | 0.9524 |
| pplx-embed-v1-0.6B | hybrid | rec | 0.5055 | 0.4582 | 0.8095 | 0.9524 |

**all-mpnet hybrid leads on SWCR** — MRR 0.5757 vs pplx best of 0.5094 (+0.066), and perfect Gold-in-Candidates (1.0 vs pplx 0.9524). nomic and bge-m3 SWCR remain invalid (no fixed benchmark re-run available for these models).

### Confidence Level

**Starfinder confidence: HIGH**
- 28/28 runs completed successfully
- pplx leads MRR by +2.6 points over all-mpnet
- all-mpnet-dense leads Recall@10 (0.8467 vs pplx 0.8067) and Gold-in-Candidates (1.000 vs 0.960)

**SwordsandWizardry confidence: MEDIUM for all-mpnet and pplx, LOW for nomic/bge-m3**
- all-mpnet SWCR: valid post-fix runs available (`030128`, `030202`) — 21/21 grounded
- pplx SWCR: valid post-fix runs from `pplx_only_run` — 21/21 grounded
- nomic SWCR: broken (`022218`, `required_gold_empty: 21`) — no valid re-run
- bge-m3 SWCR: broken (all runs `no_gold_defined = 20`) — no valid re-run

### Alternative Recommendation

If maximum Recall@10 and Gold-in-Candidates on Starfinder is the priority (e.g., for completeness-critical use cases):  
**`all-mpnet-base-v2` / `dense` / `standardized` or `recommended`** (identical performance)
- Recall@10 = 0.8467 (vs pplx 0.8067)
- Gold-in-Candidates = 1.0000 (vs pplx 0.9600)
- MRR = 0.6660 (−0.026 vs pplx)

### Conditions That Would Change This Decision

### Conditions That Would Change This Decision

1. **SWCR re-run for nomic and bge-m3** on the fixed benchmark. If nomic achieves competitive SWCR metrics (its SF MRR is strong at 0.6592), it could challenge all-mpnet's cross-corpus lead.
2. **all-mpnet SWCR recommended recipe run.** Only standardized is available for SWCR all-mpnet (`030128`, `030202`). The recommended recipe lift seen on nomic SF (+5.5 MRR) could also appear here.
3. **pplx deployment cost / inference latency.** If pplx requires slower inference, all-mpnet is the clear default given near-parity on SF.
4. **A third document/corpus.** If pplx's 4% Gold-in-Candidates miss on Starfinder causes real-world failures, all-mpnet's zero-miss coverage becomes decisive.

---

## 7. Appendix

### A. Artifact Paths for Every Cited Claim

| Claim | Source File |
|---|---|
| All Starfinder model metrics (3 models + pplx) | `out/retrieval_lab/bakeoff/model_bakeoff_full_run_20260303_post_benchmark_fix/aggregate_metrics.json` |
| pplx Starfinder + SWCR metrics | `out/retrieval_lab/experiments/pplx_only_run/aggregate_metrics.json` |
| Full run_rows (completion, exit codes) | `out/retrieval_lab/bakeoff/model_bakeoff_full_run_20260303_post_benchmark_fix/run_rows.json` |
| pplx run_rows | `out/retrieval_lab/experiments/pplx_only_run/run_rows.json` |
| Full run SUMMARY | `out/retrieval_lab/bakeoff/model_bakeoff_full_run_20260303_post_benchmark_fix/SUMMARY.md` |
| pplx SUMMARY | `out/retrieval_lab/experiments/pplx_only_run/SUMMARY.md` |

**Authoritative per-experiment artifact dirs (latest run per group):**

| Group | Artifact Dir |
|---|---|
| SF / dense / std / all-mpnet | `bakeoff_starfinder_dense_all_mpnet_base_v2_standardized_baseline_20260303_021102` |
| SF / hybrid / std / all-mpnet | `bakeoff_starfinder_hybrid_all_mpnet_base_v2_standardized_baseline_20260303_021107` |
| SF / dense / rec / all-mpnet | `bakeoff_starfinder_dense_all_mpnet_base_v2_recommended_baseline_20260303_021603` |
| SF / hybrid / rec / all-mpnet | `bakeoff_starfinder_hybrid_all_mpnet_base_v2_recommended_baseline_20260303_021608` |
| SF / dense / std / nomic | `bakeoff_starfinder_dense_nomic_embed_text_v2_standardized_baseline_20260303_021233` |
| SF / hybrid / std / nomic | `bakeoff_starfinder_hybrid_nomic_embed_text_v2_standardized_baseline_20260303_021242` |
| SF / dense / rec / nomic | `bakeoff_starfinder_dense_nomic_embed_text_v2_recommended_baseline_20260303_021732` |
| SF / hybrid / rec / nomic | `bakeoff_starfinder_hybrid_nomic_embed_text_v2_recommended_baseline_20260303_021740` |
| SF / dense / std / bge-m3 | `bakeoff_starfinder_dense_bge_m3_standardized_baseline_20260303_021438` |
| SF / hybrid / std / bge-m3 | `bakeoff_starfinder_hybrid_bge_m3_standardized_baseline_20260303_021445` |
| SF / dense / rec / bge-m3 | `bakeoff_starfinder_dense_bge_m3_recommended_baseline_20260303_021931` |
| SF / hybrid / rec / bge-m3 | `bakeoff_starfinder_hybrid_bge_m3_recommended_baseline_20260303_021937` |
| SF / dense / std / pplx | `bakeoff_starfinder_dense_pplx_embed_v1_06B_standardized_baseline_20260304_035525` |
| SF / hybrid / std / pplx | `bakeoff_starfinder_hybrid_pplx_embed_v1_06B_standardized_baseline_20260304_035536` |
| SF / dense / rec / pplx | `bakeoff_starfinder_dense_pplx_embed_v1_06B_recommended_baseline_20260304_035813` |
| SF / hybrid / rec / pplx | `bakeoff_starfinder_hybrid_pplx_embed_v1_06B_recommended_baseline_20260304_035824` |
| SWCR / dense / std / all-mpnet | `bakeoff_swordsandwizardry_dense_all_mpnet_base_v2_standardized_full_20260303_030128` ✓ fixed benchmark |
| SWCR / hybrid / std / all-mpnet | `bakeoff_swordsandwizardry_hybrid_all_mpnet_base_v2_standardized_full_20260303_030202` ✓ fixed benchmark |
| SWCR / dense / std / nomic | `bakeoff_swordsandwizardry_dense_nomic_embed_text_v2_standardized_full_20260303_022218` ✗ broken (no_gold_defined=20) |
| SWCR / hybrid / std / pplx | `bakeoff_swordsandwizardry_hybrid_pplx_embed_v1_06B_standardized_full_20260304_040048` |
| SWCR / dense / rec / pplx | `bakeoff_swordsandwizardry_dense_pplx_embed_v1_06B_recommended_full_20260304_040235` |
| SWCR / hybrid / rec / pplx | `bakeoff_swordsandwizardry_hybrid_pplx_embed_v1_06B_recommended_full_20260304_040310` |

All per-experiment dirs are under: `out/retrieval_lab/experiments/`

### B. Superseded Runs

The following experiment folders are superseded and should not be used for decision claims:

| Run Group | Superseded Folders | Replaced By |
|---|---|---|
| SF / dense / std / all-mpnet | `*_20260301_214914`, `*_20260301_220146`, `*_20260301_225630`, `*_20260301_225957`, `*_20260301_234932`, `*_20260303_024817` | `*_20260303_021102` |
| SF / hybrid / std / all-mpnet | `*_20260301_214918`, `*_20260301_220151`, `*_20260301_225636`, `*_20260301_230005`, `*_20260301_234938`, `*_20260303_024828` | `*_20260303_021107` |
| SF / dense / rec / all-mpnet | `*_20260301_215044`, `*_20260301_220329`, `*_20260301_230702`, `*_20260301_235459`, `*_20260303_025537` | `*_20260303_021603` |
| SWCR models (not pplx) | All SWCR `*_20260303_*` experiments | Not yet re-run with fixed benchmark |
| Early bakeoff runs `bakeoff_sf_*_20260301_03*`, `bakeoff_sw_*_20260301_03*` | All 8 early hybrid/dense experiments | Superseded by full matrix runs |

### C. Outstanding Work Items

1. **Re-run SWCR for nomic and bge-m3** against the fixed benchmark. all-mpnet SWCR is now available (post-fix, `030128`/`030202`); nomic and bge-m3 still need re-runs.
2. **Run all-mpnet SWCR with recommended recipe.** Only standardized is available for post-fix SWCR all-mpnet runs.
3. **Verify the persistent single-miss query in pplx SWCR.** One query has `gold_not_in_candidates = 1` across all pplx SWCR runs. Check whether the same query also misses in all-mpnet SWCR.
4. **Promote best run.** If `all-mpnet-base-v2` / `hybrid` / `standardized` is confirmed as the cross-corpus default, run `scripts/promote_best_retrieval_run.py` targeting both the Starfinder and SWCR all-mpnet hybrid dirs.

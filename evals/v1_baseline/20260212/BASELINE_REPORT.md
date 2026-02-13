# v1 Baseline Report — 2026-02-12

**Run date:** 2026-02-12  
**Substrate version:** v1  
**Pipeline:** Stage A + B only (EvidenceUnits); hybrid retrieval (dense all-mpnet-base-v2 + BM25, RRF).  
**Purpose:** Snapshot of retrieval performance across PHB, Starfinder, and Swords & Wizardry, comparing baseline hybrid vs dual-list fusion.

---

## 1. Executive Summary

| Corpus | Units | Pages | Queries (grounded) | Baseline MRR | Dual-list MRR | Δ MRR | Best config |
|--------|-------|-------|--------------------|--------------|---------------|-------|-------------|
| **D&D 5e PHB** | 6,999 | 379 | 28 (26) | 0.490 | 0.491 | +0.001 | Tie |
| **Starfinder 2e PC** | 13,162 | 36 | 50 (47) | 0.441 | 0.454 | **+0.013** | Dual-list |
| **Swords & Wizardry** | 307 | 141 | 25 (25) | 0.358 | 0.363 | +0.005 | Dual-list |

- **PHB:** Baseline and dual-list are effectively tied on aggregate MRR; dual-list improves FSH@10 (full-set hit) and T2 MRR slightly but regresses on conceptual suite and R@5/R@10. No T1 regressions; same 2 retrieval_miss, 2 no_gold.
- **Starfinder:** Dual-list improves MRR, gold-in-candidates (72% → 74%), and reduces retrieval_miss by 1 (11 → 10). Modest but consistent gain.
- **S&W:** Dual-list gives a small MRR gain; ceiling is unchanged (48% of queries never see gold in candidates). Main bottleneck is gold-not-in-candidates, not ranking.

---

## 2. Corpus and Run Configuration

| Book | Document ID | Substrate path | Run IDs (embed) |
|------|-------------|----------------|-----------------|
| D&D 5e PHB | DnD_PHB_5.5 | out/DnD_PHB_5.5 | retrieval_lab_DnD_PHB_5.5_v1 |
| Starfinder 2e Player Core | StarFinderPlayerCore | out/StarFinderPlayerCore | retrieval_lab_StarFinderPlayerCore_v1 |
| Swords & Wizardry | Swords&Wizardry | out/Swords&Wizardry | retrieval_lab_Swords&Wizardry_v1 |

- **Model:** all-mpnet-base-v2 (dense) + BM25 (sparse), RRF fusion.  
- **Dual-list:** Index_U (units) + Index_F (clause-family window 3, max 6 units, symmetric). Ku=12, Kf=12, Kfinal=10, Qu=6.

---

## 3. PHB (D&D 5e)

### 3.1 Aggregate (all-mpnet-base-v2)

| Metric | Baseline (phb_hybrid) | Dual-list (phb_hybrid_dual_list_fusion) | Δ |
|--------|------------------------|------------------------------------------|---|
| **MRR** | 0.4898 | 0.4912 | +0.0014 |
| **Gold-in-candidates** | 85.7% (92.3% true) | 85.7% (92.3% true) | — |
| **R@5** | 0.368 | 0.332 | −0.036 |
| **R@10** | 0.436 | 0.423 | −0.013 |
| **H@5** | 0.714 | 0.679 | −0.035 |
| **H@10** | 0.750 | 0.714 | −0.036 |
| **FSH@10** | 0.115 | 0.154 | +0.039 |

### 3.2 Per-tier (R8)

| Tier | N | Baseline MRR | Dual-list MRR | Baseline H@10 | Dual-list H@10 |
|------|---|--------------|---------------|--------------|----------------|
| T1 | 10 | 0.640 | 0.670 | 0.80 | 0.80 |
| T2 | 12 | 0.325 | 0.341 | 0.67 | 0.67 |
| T3 | 6 | 0.568 | 0.494 | 0.83 | 0.67 |

### 3.3 Failure buckets

| Bucket | Baseline | Dual-list |
|--------|----------|-----------|
| success | 24 | 24 |
| no_gold_defined | 2 | 2 |
| gold_not_in_candidates | 2 | 2 |

**Conclusion:** PHB dual-list is roughly neutral on aggregate; small MRR gain, better FSH@10, but lower R@5/R@10 and T3 H@10. No new retrieval misses; safe to use as production default with monitoring.

---

## 4. Starfinder 2e Player Core

### 4.1 Aggregate

| Metric | Baseline | Dual-list | Δ |
|--------|----------|-----------|---|
| **MRR** | 0.4409 | 0.4539 | **+0.013** |
| **Gold-in-candidates** | 72.0% (76.6% true) | 74.0% (78.7% true) | +2% |
| **R@5** | 0.462 | 0.477 | +0.015 |
| **R@10** | 0.562 | 0.547 | −0.015 |
| **H@5** | 0.660 | 0.660 | — |
| **H@10** | 0.720 | 0.700 | −0.020 |
| **FSH@10** | 0.447 | 0.447 | — |

### 4.2 Per-tier

| Tier | N | Baseline MRR | Dual-list MRR | Baseline H@10 | Dual-list H@10 |
|------|---|--------------|---------------|--------------|----------------|
| T1 | 10 | 0.378 | 0.407 | 0.60 | 0.60 |
| T2 | 22 | 0.467 | 0.480 | 0.73 | 0.73 |
| T3 | 18 | 0.443 | 0.448 | 0.78 | 0.72 |

### 4.3 Failure buckets

| Bucket | Baseline | Dual-list |
|--------|----------|-----------|
| success | 36 | 37 |
| gold_not_in_candidates | 11 | 10 |
| no_gold_defined | 3 | 3 |

**Conclusion:** Dual-list improves MRR and gold-in-candidates and converts one retrieval_miss to success. Recommended as default for Starfinder.

---

## 5. Swords & Wizardry

### 5.1 Aggregate

| Metric | Baseline | Dual-list | Δ |
|--------|----------|-----------|---|
| **MRR** | 0.3578 | 0.3633 | +0.005 |
| **Gold-in-candidates** | 52.0% | 52.0% | — |
| **R@5** | 0.160 | 0.173 | +0.013 |
| **R@10** | 0.173 | 0.173 | — |
| **H@5** | 0.480 | 0.520 | +0.040 |
| **H@10** | 0.520 | 0.520 | — |
| **FSH@10** | 0.000 | 0.000 | — |

### 5.2 Per-tier

| Tier | N | Baseline MRR | Dual-list MRR | Baseline H@10 | Dual-list H@10 |
|------|---|--------------|---------------|--------------|----------------|
| T1 | 9 | 0.161 | 0.176 | 0.44 | 0.44 |
| T2 | 8 | 0.375 | 0.375 | 0.50 | 0.50 |
| T3 | 8 | 0.563 | 0.563 | 0.63 | 0.63 |

### 5.3 Failure buckets

| Bucket | Baseline | Dual-list |
|--------|----------|-----------|
| success | 13 | 13 |
| gold_not_in_candidates | 12 | 12 |

**Conclusion:** S&W has a low ceiling (52% of queries ever see gold in the ranked list). Dual-list gives a small MRR and H@5 gain but does not fix the 12 queries where gold is never in candidates. Improving gold coverage (grounding or substrate) is the main lever; dual-list remains the better of the two configs.

---

## 6. Cross-Corpus Comparison

| Metric | PHB (base) | PHB (dual) | Starfinder (base) | Starfinder (dual) | S&W (base) | S&W (dual) |
|--------|------------|------------|-------------------|-------------------|------------|------------|
| MRR | 0.490 | 0.491 | 0.441 | **0.454** | 0.358 | **0.363** |
| Gold-in-cand | 92.3%* | 92.3%* | 76.6%* | 78.7%* | 52.0% | 52.0% |
| H@10 | 0.75 | 0.71 | 0.72 | 0.70 | 0.52 | 0.52 |
| retrieval_miss | 2 | 2 | 11 | 10 | 12 | 12 |

*True ceiling (excluding no_gold_defined).

- **PHB** has the highest ceiling and best H@10; dual-list does not hurt retrieval_miss.  
- **Starfinder** benefits clearly from dual-list (MRR and one fewer retrieval_miss).  
- **S&W** is ceiling-limited; dual-list helps only at the margin.

---

## 7. Recommendations

1. **PHB:** Keep dual-list as production default; monitor T3 and conceptual suite in future runs.  
2. **Starfinder:** Use dual-list as default; this run supports it.  
3. **S&W:** Use dual-list; prioritize improving gold grounding and/or substrate so more queries have gold in the candidate set.  
4. **Regression policy:** For PHB, continue to require zero T1 regressions vs baseline when changing retrieval (see Docs/Design/v1/retrieval_lab_v1.md).  
5. **Next steps:** Re-run comparison report (e.g. `compare_baseline_dual_list_pairing`) if PHB pairing runs are added; consider S&W gold-set audit for the 12 gold_not_in_candidates queries.

---

## 8. Artifact Index

| Experiment | Dir |
|------------|-----|
| phb_hybrid | phb_hybrid_20260212_145913 |
| phb_hybrid_dual_list_fusion | phb_hybrid_dual_list_fusion_20260212_150242 |
| starfinder_hybrid | starfinder_hybrid_20260212_151531 |
| starfinder_hybrid_dual_list_fusion | starfinder_hybrid_dual_list_fusion_20260212_151943 |
| swords_wizardry_hybrid | swords_wizardry_hybrid_20260212_153447 |
| swords_wizardry_hybrid_dual_list_fusion | swords_wizardry_hybrid_dual_list_fusion_20260212_153625 |

Each directory contains: REPORT.md, metrics.json, failure_buckets.json, per_query.json, grounding_audit.json, experiment.json, and embeddings (corpus ± family).

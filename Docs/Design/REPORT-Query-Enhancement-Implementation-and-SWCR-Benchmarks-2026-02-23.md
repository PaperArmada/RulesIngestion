---
title: "Report: Query Enhancement Implementation + S&W Benchmarks"
project: "DungeonOverMind / RulesIngestion"
owner: "Retrieval Lab"
status: "Results recorded"
date: "2026-02-23"
corpus: "Swords & Wizardry Complete Revised (SWCR)"
---

## Summary

This report covers:

- The implemented **Corpus-Specific Query Enhancement** system (profile artifact + deterministic caching + pre-retrieval expansion/decomposition + multi-query fusion).
- Benchmark results on **Swords & Wizardry Complete Revised** using the **minimal-anchor revised benchmark** suite.
- Comparative findings for:
  - **BM25** baseline vs dict expansion vs decomposition (ungated and tier-gated).
  - **Hybrid** (dense + BM25 fused via RRF) baseline vs tier-gated decomposition.

High-level outcomes:

- **Dict expansion** (with a minimal synonym set) did not help SWCR BM25 and slightly regressed one query.
- **Decomposition ungated** improved candidate ceiling but caused significant **T1 regressions** (as expected without tier gating).
- **Decomposition tier-gated to T2/T3** improved BM25 candidate ceiling and recall at small K while keeping **T1 perfectly stable**.
- On **Hybrid**, tier-gated decomposition **regressed overall metrics** (one T2 query fell out of candidates), suggesting hybrid is already strong and multi-query decomposition needs additional constraints to avoid demotion/noise.

## What was implemented (technical)

### Core architecture

Query enhancement is a **pre-retrieval** module that outputs one-or-more query strings per original query, then runs retrieval per variant and fuses results (RRF) back to a single ranked list.

- **Evidence policy**: enhancements are *retrieval steering only*; returned citations remain `EvidenceUnit` IDs.
- **Determinism**: profile hashing + stable normalization + caching. LLM expansion runs at `temperature=0` and is cached.

See also:

- Design doc: `RulesIngestion/Docs/Design/DESIGN-Corpus-Specific-Query-Enhancement.md`
- Technical architecture: `RulesIngestion/Docs/Design/TECHARCH-Corpus-Specific-Query-Enhancement.md`

### Implemented modules

| Path | Purpose |
|---|---|
| `retrieval_lab/query_enhancement/profile.py` | `QueryExpansionProfile`, canonical hashing, `normalize_query`, validation |
| `retrieval_lab/query_enhancement/cache.py` | Deterministic file cache for expansions |
| `retrieval_lab/query_enhancement/enhancer.py` | Dict expansion, LLM expansion (JSON schema), decomposition heuristics, drift guard |
| `retrieval_lab/query_enhancement/multi_query.py` | Multi-query wrapper + RRF fusion utilities |
| `retrieval_lab/query_enhancement/attribution.py` | Attribution helpers (candidate inflation, “gold from expansion”) |
| `scripts/build_qe_profile.py` | Profile generator from substrate outputs |

### Integration points

| Retrieval mode | Entry point modified |
|---|---|
| BM25 | `retrieval_lab/orchestration/bm25_mode.py` |
| Dense/Hybrid | `retrieval_lab/orchestration/dense_mode.py` |
| Experiment harness | `retrieval_lab/run_experiment.py` |
| Reporting | `retrieval_lab/report.py` |
| CLI | `retrieval_lab/orchestration/cli_parser.py`, `retrieval_lab/orchestration/cli.py` |

### Tier-gated decomposition (T2/T3 only)

After observing that ungated decomposition caused T1 regressions, decomposition was updated to be **tier-gated**:

- If query tier is `T2` or `T3` (using `q["tier"]` or `q["_tier"]`), apply `mode=decompose`.
- Otherwise force `mode=none` (original query only).

This is implemented per-query via:

- `retrieval_lab/query_enhancement/multi_query.py::expand_query_texts_per_query_modes()`
- Gate logic inside `bm25_mode.py` and `dense_mode.py` when `qe_mode == "decompose"`.

### Hybrid run hardening: filesystem-safe model IDs

Hybrid baseline initially failed because embedding filenames used raw `model_id` containing `/`.

Fix: in `dense_mode.py` embedding save/load uses `safe_model_id = model_id.replace("/", "__")` for `.npy` filenames.

## SWCR benchmark setup

### Substrate

- Substrate root: `RulesIngestion/out/SwordsAndWizardry/SW_Complete_Revised`
- Page outputs include:
  - `stageAPrime.enrichments.json`
  - `stageB.evidence_units.json`

### Benchmark suite

- Batch JSON: `RulesIngestion/evals/retrieval/SwordsandWizardy/swords_wizardry_complete_revised_benchmark_min_anchor_atomic_rewrite.json`
- Queries: 35
- Grounded: 32 (page-anchored grounding)

### Query enhancement profile (SWCR)

- Generated profile: `RulesIngestion/out/SwordsAndWizardry/qe_profiles/swcr_v1_qe_001.json`
- Generated via:
  - `uv run python scripts/build_qe_profile.py --substrate-path out/SwordsAndWizardry/SW_Complete_Revised --corpus-id swcr --document-id SwordsAndWizardry --output out/SwordsAndWizardry/qe_profiles/swcr_v1_qe_001.json`
- Notes:
  - The auto-aggregated `allowed_vocab.top_keywords` includes OCR artifacts (e.g. image markdown). This did not affect dict/decompose runs; it matters more for LLM steering and should be filtered before serious LLM use.
  - A minimal hand-curated synonym set was added for the dict run (Referee ↔ GM/DM/etc., “ruling” variants).

## Benchmark runs and artifact locations

### BM25 runs (output dir: `out/SwordsAndWizardry/qe_benchmark_runs/`)

| Run | Mode | Experiment ID | Key artifacts |
|---|---|---|---|
| E0 | baseline | `swcr_bm25_E0_baseline_20260223_160002` | `REPORT.md`, `metrics.json`, `per_query.json` |
| E1 | dict | `swcr_bm25_E1_dict_20260223_160009` | `REPORT.md`, `metrics.json`, `per_query.json` |
| E3 | decompose (ungated) | `swcr_bm25_E3_decompose_20260223_160119` | `REPORT.md`, `metrics.json`, `per_query.json` |
| E3g | decompose (T2/T3 gated) | `swcr_bm25_E3_decompose_T2T3_20260223_160445` | `REPORT.md`, `metrics.json`, `per_query.json` |

### Hybrid runs (output dir: `out/SwordsAndWizardry/qe_hybrid_runs/`)

Hybrid config: `out/SwordsAndWizardry/qe_bench_configs/swcr_hybrid_min_anchor.yaml`  
Model: `sentence-transformers/all-MiniLM-L6-v2`

| Run | Mode | Experiment ID | Key artifacts |
|---|---|---|---|
| H0 | baseline | `swcr_hybrid_E0_baseline_20260223_162921` | `REPORT.md`, `metrics.json`, `per_query.json` |
| H3g | decompose (T2/T3 gated) | `swcr_hybrid_E3_decompose_T2T3_20260223_162939` | `REPORT.md`, `metrics.json`, `per_query.json` |

## Results: BM25

### E0 baseline vs E1 dict

Overall deltas:

- MRR: **0.3065 → 0.3056** (Δ -0.0008)
- Gold-in-candidates: **0.4857 → 0.4857** (Δ +0.0000)
- Gold-in-candidates (true ceiling): **0.5312 → 0.5312** (Δ +0.0000)

Per-query changes:

- 1 query regressed hit→rank_miss:
  - `sw_rev_u01a_player_vs_referee_control` (first gold rank 13 → 21)

Interpretation:

- SWCR queries already use “Referee”; dict synonym injection mostly adds GM/DM variants and can slightly perturb BM25 ranking without providing new anchors.

### E0 baseline vs E3 decompose (ungated)

Overall:

- Gold-in-candidates improved materially (**+0.1143**) but **MRR dropped** (**-0.0209**) due to T1 demotions.

This run is not aligned with the design intent because decomposition was not tier-gated.

### E0 baseline vs E3g decompose (T2/T3 gated)

Overall deltas:

- MRR: **0.3065 → 0.3067** (Δ +0.0002)
- Gold-in-candidates: **0.4857 → 0.5143** (Δ +0.0286)
- Gold-in-candidates (true ceiling): **0.5312 → 0.5625** (Δ +0.0312)
- Recall@5: **0.3012 → 0.3339** (Δ +0.0327)
- Hit@5: **0.3714 → 0.4000** (Δ +0.0286)

Stability:

- **T1 regressions: 0** (no T1 per-query changes)

Notable improvement:

- `sw_rev_s14c_time_cost_of_searching` (T2) moved **retrieval_miss → hit** (first gold rank became 20).

Interpretation:

- Tier gating preserves T1 stability while allowing decomposition to recover at least one multi-hop-ish miss (at deeper K in this case).

## Results: Hybrid (dense + BM25 fused with RRF)

Hybrid baseline is substantially stronger than BM25 baseline on this suite:

- Baseline hybrid gold-in-candidates: **0.6286** (vs BM25 baseline **0.4857**)

### H0 baseline vs H3g decompose (T2/T3 gated)

Overall deltas (hybrid):

- MRR: **0.3287 → 0.3270** (Δ -0.0017)
- Gold-in-candidates: **0.6286 → 0.6000** (Δ -0.0286)
- Gold-in-candidates (true ceiling): **0.6875 → 0.6562** (Δ -0.0312)
- Recall@10: **0.4508 → 0.4222** (Δ -0.0286)
- Hit@10: **0.5429 → 0.5143** (Δ -0.0286)

Per-query changes (3 total):

- T2 regression (hit → retrieval_miss):
  - `sw_rev_s06_spell_preparation_reprepare_and_interruption_anchor` (first gold rank 7 → None)
- T2 small demotion (hit, rank 3 → 4):
  - `sw_rev_s14a_exploration_turn_time_unit`
- T1 small improvement (hit, rank 3 → 2):
  - `sw_rev_s03_treasure_to_xp_rule`

Interpretation:

- Hybrid is already pulling strong candidates; introducing decomposition variants can **demote** the correct evidence outside the top-20 candidate cutoff used by the harness.
- This suggests decomposition in hybrid needs additional constraints, such as:
  - smaller per-query variant budget for hybrid (e.g., original + 1 subquery max)
  - stronger gating (only decompose for queries currently failing in baseline, e.g. `gold_not_in_candidates`)
  - fusion policy adjustments (e.g. union + rerank, or per-variant quotas rather than pure RRF)
  - increasing `retrieval_cutoff` for multi-query fusion runs (admission cap) while keeping final `top_k` fixed

## Findings and Recommendations

### What worked

- **Tier-gated decomposition in BM25** improved candidate ceiling and early-k recall without destabilizing T1.
- The implementation is modular, deterministic for dict/decompose modes, and supports strict caching for LLM mode.

### What did not work (yet)

- **Dict expansion** did not help SWCR; the benchmark’s phrasing already matches corpus vocabulary.
- **Decomposition on hybrid** regressed overall performance on this small suite due to demotion/noise effects within the fixed top-20 cutoff.

### Immediate next steps (highest ROI)

1. **Hybrid-safe decomposition policy**
   - Add a hybrid-specific cap (e.g. original + 1 subquery) or only enable decomposition for queries whose baseline failure bucket is `gold_not_in_candidates`.
2. **Profile hygiene**
   - Filter `allowed_vocab.top_keywords` to remove obvious OCR artifacts (image markdown, punctuation-only tokens) before enabling LLM expansions.
3. **Better attribution logging**
   - Persist per-variant retrieval lists and fused lists in experiment artifacts for more direct “which variant caused the win/loss” analysis.

## Repro commands

BM25 baseline:

```bash
cd RulesIngestion
uv run python -m retrieval_lab.run_experiment \
  --config out/SwordsAndWizardry/qe_bench_configs/swcr_bm25_min_anchor.yaml \
  --experiment-name swcr_bm25_E0_baseline \
  --enhancement-mode none
```

BM25 gated decompose:

```bash
cd RulesIngestion
uv run python -m retrieval_lab.run_experiment \
  --config out/SwordsAndWizardry/qe_bench_configs/swcr_bm25_min_anchor.yaml \
  --experiment-name swcr_bm25_E3_decompose_T2T3 \
  --enhancement-mode decompose \
  --enhancement-profile out/SwordsAndWizardry/qe_profiles/swcr_v1_qe_001.json \
  --baseline-metrics out/SwordsAndWizardry/qe_benchmark_runs/<E0>/metrics.json
```

Hybrid baseline:

```bash
cd RulesIngestion
uv run python -m retrieval_lab.run_experiment \
  --config out/SwordsAndWizardry/qe_bench_configs/swcr_hybrid_min_anchor.yaml \
  --experiment-name swcr_hybrid_E0_baseline \
  --enhancement-mode none
```

Hybrid gated decompose:

```bash
cd RulesIngestion
uv run python -m retrieval_lab.run_experiment \
  --config out/SwordsAndWizardry/qe_bench_configs/swcr_hybrid_min_anchor.yaml \
  --experiment-name swcr_hybrid_E3_decompose_T2T3 \
  --enhancement-mode decompose \
  --enhancement-profile out/SwordsAndWizardry/qe_profiles/swcr_v1_qe_001.json \
  --baseline-metrics out/SwordsAndWizardry/qe_hybrid_runs/<H0>/metrics.json
```


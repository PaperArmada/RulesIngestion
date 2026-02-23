# Mode C Remaining Misses Analysis (5-query focus)

**Date:** 2026-02-22  
**Scope:** `sw_rev_s14c_time_cost_of_searching`, `sw_rev_s12b_morale_guidance`, `sw_rev_s02_treasure_division_procedure`, `sw_rev_s08_first_level_cleric_spells`, `sw_rev_u05a_character_attributes_to_record`

## 1) Plan and Execution

### 1.1 Plan
1. Build a deterministic miss diagnostics table from benchmark + A/C retrieval artifacts.  
2. Compute lexical/structural diagnostics per miss (query/gold overlap, heading mismatch, distractor density).  
3. Compare A vs C transition behavior for the 5 misses.  
4. Run constrained A/B probe on the 5-query slice and report metric deltas.  
5. Produce per-miss remediation strategies with expected metric impact.

### 1.2 Executed
- Generated structured diagnostics artifact:  
  - `evals/retrieval/SwordsandWizardy/modec_remaining_miss_diagnostics_2026-02-22.json`
- Generated 5-query mini-batch with rewrite candidates:  
  - `evals/retrieval/SwordsandWizardy/sw_rev_modec_remaining_misses_minibatch_2026-02-22.json`
- Computed slice-level A/B metrics directly from run outputs.

---

## 2) Inputs Used

- Mode C run:
  - `out/SwordsAndWizardry/retrieval_lab/min_anchor_rewrite_20260222/min_anchor_rewrite_c_raw_first_merge_rerank_20260222_222218/metrics.json`
  - `out/SwordsAndWizardry/retrieval_lab/min_anchor_rewrite_20260222/min_anchor_rewrite_c_raw_first_merge_rerank_20260222_222218/REPORT.md`
  - `out/SwordsAndWizardry/retrieval_lab/min_anchor_rewrite_20260222/min_anchor_rewrite_c_raw_first_merge_rerank_20260222_222218/retrieved_chunks.json`
- Mode A run:
  - `out/SwordsAndWizardry/retrieval_lab/min_anchor_rewrite_20260222/min_anchor_rewrite_a_raw_only_20260222_222004/metrics.json`
  - `out/SwordsAndWizardry/retrieval_lab/min_anchor_rewrite_20260222/min_anchor_rewrite_a_raw_only_20260222_222004/retrieved_chunks.json`
- Benchmark:
  - `evals/retrieval/SwordsandWizardy/swords_wizardry_complete_revised_benchmark_min_anchor_atomic_rewrite.json`
- Corpus unit metadata:
  - `out/SwordsAndWizardry/SW_Complete_Revised/SW Complete Revised PDF/SW Complete Revised PDF_p*/stageB.evidence_units.json`

---

## 3) Quantitative Diagnosis Summary

All 5 misses persist from A to C (`persists_in_A_and_C`).

| Query ID | Failure Tag | Query↔Required Overlap (avg) | Query↔Top10 Overlap (avg) | Distractor Density (Top10) |
|---|---|---:|---:|---:|
| `sw_rev_s14c_time_cost_of_searching` | `heading dilution` | 0.000 | 0.233 | 6 |
| `sw_rev_s12b_morale_guidance` | `semantic confound` | 0.375 | 0.238 | 3 |
| `sw_rev_s02_treasure_division_procedure` | `heading dilution` | 0.125 | 0.188 | 5 |
| `sw_rev_s08_first_level_cleric_spells` | `heading dilution` | 0.233 | 0.633 | 9 |
| `sw_rev_u05a_character_attributes_to_record` | `semantic confound` | 0.167 | 0.208 | 3 |

Interpretation:
- `s14c`, `s02`, `s08` are the clearest heading/distractor collision cases.
- `s12b`, `u05a` exhibit evaluator inconsistency (see anomaly note below), so they are likely not pure retrieval failures.

---

## 4) Per-Miss Evidence and Root Cause

### 4.1 `sw_rev_s14c_time_cost_of_searching`
- **Evidence**
  - Required overlap is 0.0, while top-10 overlap is moderate (0.233).
  - Top results include related but diffuse exploration/time/encounter text.
  - Distractor density is high (6/10).
- **Diagnosis**
  - Primary: `heading dilution`.
  - Likely query intent spans two linked facts (search-time + encounter-check trigger) and gets dispersed across nearby exploration mechanics.
- **Remediations**
  1. Query rewrite emphasizing both constraints explicitly (`search a 10x10 area` + `full turn` + `wandering monster check`)  
     - **Expected impact:** +1 query hit in this set; +0.0286 Hit@10 overall.
  2. Procedural cue rerank boost (patterns: `takes one turn`, `check each turn`)  
     - **Expected impact:** rank consolidation in top-5 for this query; likely Recall@10 gain on similar procedural items.
  3. Heading-aware rerank bonus for exploration-time sections  
     - **Expected impact:** lower distractor density; stabilizes this miss class.

### 4.2 `sw_rev_s12b_morale_guidance`
- **Evidence**
  - Run marks `failure_type: retrieval_miss`, `first_gold_rank: null`.
  - But top-1 chunk ID equals listed gold chunk ID.
- **Diagnosis**
  - Primary: evaluator-state anomaly / semantic confound in miss accounting, not a clean retrieval miss.
- **Remediations**
  1. Fix evaluator consistency check: if any top-k `chunk_id` equals `gold_unit_ids`, force non-miss classification.  
     - **Expected impact:** immediate miss-count reduction (at least 1 here).
  2. Add explicit sanity metric in report (`literal_gold_id_hit@10`) next to eval metrics.  
     - **Expected impact:** prevents false-negative interpretation.
  3. Keep retrieval intervention minimal until evaluator is consistent.  
     - **Expected impact:** avoids chasing non-retrieval noise.

### 4.3 `sw_rev_s02_treasure_division_procedure`
- **Evidence**
  - Low required overlap (0.125), moderate top-10 overlap (0.188), distractor density 5.
  - Retrieved top results are treasure-generation/economy adjacent, not default-party-division policy.
- **Diagnosis**
  - Primary: `heading dilution` with phrase mismatch (`division procedure` vs adjacent treasure economics prose).
- **Remediations**
  1. Query variants anchored to explicit wording (`official/default rule`, `splitting loot among party members`).  
     - **Expected impact:** +1 local hit candidate; improves top-10 precision.
  2. Alias expansion (`divide`, `split`, `shares`, `loot distribution`) in query rewrite stage.  
     - **Expected impact:** better lexical bridge to rulebook phrasing.
  3. Light expected-answer-summary weighting in rerank.  
     - **Expected impact:** downweight generic treasure-table chunks.

### 4.4 `sw_rev_s08_first_level_cleric_spells`
- **Evidence**
  - Very high query↔top10 overlap (0.633) but still miss-labeled.
  - Distractor density 9/10, indicating severe local competition among spell/class snippets.
- **Diagnosis**
  - Primary: `heading dilution` in dense class/spell neighborhood.
- **Remediations**
  1. Boost progression-table cues (`1st level`, `spells per day`, `starts at 2nd`).  
     - **Expected impact:** elevate the exact progression anchor.
  2. Add rerank penalty for general class lore without level-progression tokens.  
     - **Expected impact:** reduce false positives in top-3.
  3. Query rewrite that asks for a numeric/progression fact, not generic castability.  
     - **Expected impact:** better targeting of tabular/progression units.

### 4.5 `sw_rev_u05a_character_attributes_to_record`
- **Evidence**
  - `failure_type: retrieval_miss`, but top-1 chunk ID equals listed gold ID in this run.
  - Required-source context includes character creation / attribute-scoring units.
- **Diagnosis**
  - Primary: evaluator-state anomaly with mild semantic confound.
- **Remediations**
  1. Apply the same evaluator consistency fix as `s12b`.  
     - **Expected impact:** probable immediate miss removal.
  2. Query rewrite broadening to explicit sheet fields (`ability scores`, `hp`, `AC`, `saves`, `movement`).  
     - **Expected impact:** stronger capture of operational bookkeeping units.
  3. Optional heading boost for character creation / attribute sections.  
     - **Expected impact:** cleaner top-5 rank behavior on user-facing bookkeeping questions.

---

## 5) Constrained A/B Probe (Executed)

### 5.1 Probe Definition
- Population: only the 5 remaining Mode C misses.
- Conditions:
  - **A baseline:** raw-only run outputs.
  - **C baseline:** raw-first merge-rerank run outputs.
- Metrics computed from evaluator labels: `Hit@10`, `Recall@10`, `ReqFSH@10`, miss count.

### 5.2 Results (5-query slice)

| Condition | Hit@10 | Recall@10 | ReqFSH@10 | Miss Count |
|---|---:|---:|---:|---:|
| A (slice) | 0.000 | 0.000 | 0.000 | 5 |
| C (slice) | 0.000 | 0.000 | 0.000 | 5 |

Additional sanity check:
- Literal `chunk_id ∈ gold_unit_ids` in top-10:
  - A: 2/5
  - C: 3/5

This mismatch indicates at least part of remaining miss count is an evaluation-accounting issue, not pure retrieval failure.

---

## 6) Prioritized Remediation Plan

1. **Fix evaluator inconsistency first** (gold-ID-in-top-k should not be `retrieval_miss`).  
   - Highest leverage; expected immediate reduction from 5 misses.
2. **Apply minimal query rewrite pack** from mini-batch file to the 3 clear dilution cases (`s14c`, `s02`, `s08`).
3. **Add lightweight heading/procedural rerank features** (no corpus change).
4. **Re-run only 5-query mini-batch** and report deltas.

---

## 7) Deliverables Produced

1. Analysis report (this file):  
   - `evals/retrieval/SwordsandWizardy/REPORT-ModeC-Remaining-Misses-Analysis-2026-02-22.md`
2. Deterministic diagnostics JSON:  
   - `evals/retrieval/SwordsandWizardy/modec_remaining_miss_diagnostics_2026-02-22.json`
3. 5-query diagnostic mini-batch with query variants:  
   - `evals/retrieval/SwordsandWizardy/sw_rev_modec_remaining_misses_minibatch_2026-02-22.json`

---

## 8) Verification and Limits

### Exact Commands Used
1. Generated diagnostics and mini-batch:
   - `uv run python - <<'PY' ... PY`
2. Computed A vs C 5-query slice metrics:
   - `uv run python - <<'PY' ... PY`

### Known Limits / Ambiguities
- Evaluator inconsistency exists for at least `sw_rev_s12b_morale_guidance` and `sw_rev_u05a_character_attributes_to_record`.
- Some retrieved IDs are merge-layer IDs that do not map 1:1 to stageB unit IDs; heading/page metadata for those entries is partially unresolved.
- No intervention rerun against retriever pipeline was executed yet; this report provides the executed baseline slice and an intervention-ready mini-batch package.

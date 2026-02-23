# S&W Complete Revised: Min-Anchor Atomic Rewrite Evaluation Report

**Date:** 2026-02-22  
**Scope:** Evaluate the rewritten benchmark file `swords_wizardry_complete_revised_benchmark_min_anchor_atomic_rewrite.json` against prior baselines, using the same corpus and EvidenceUnit IDs.

## 1) Objective

This exercise tested whether benchmark underperformance was caused primarily by:

- retrieval quality, or
- benchmark construction effects (oversized `required_gold`, duplicated/sliced units, and compositional suppression).

The rewrite intentionally changed **benchmark structure only** (no corpus changes, no new gold IDs), then re-ran baseline retrieval.

## 2) What Was Changed

File evaluated:

- `evals/retrieval/SwordsandWizardy/swords_wizardry_complete_revised_benchmark_min_anchor_atomic_rewrite.json`

Atomic-only rewrite summary:

- Original benchmark: 21 total queries, 12 `atomic_rules`
- Rewritten benchmark: 35 total queries, 26 `atomic_rules`
- Original atomic `required_gold` distribution: `{2:2, 5:1, 6:3, 7:1, 8:2, 10:1, 11:1, 14:1}`
- Rewritten atomic `required_gold` distribution: `{1:17, 2:9}`
- Original atomic max `required_gold`: 14
- Rewritten atomic max `required_gold`: 2
- Original atomic mean `required_gold`: 7.083
- Rewritten atomic mean `required_gold`: 1.346
- Rewritten zero-`required_gold` queries: 0

Design intent:

- Preserve existing evidence anchors.
- Split bundled primitives into micro-queries where needed.
- Move duplicate/slice-like units from `required_gold` to `supporting_gold`.
- Remove structural impossibility in full-set metrics.

## 3) Experimental Setup

Corpus and retriever setup were held constant:

- Substrate: `out/SwordsAndWizardry/SW_Complete_Revised`
- Corpus units: 1618 (min-chars fold enabled)
- Document ID: `Swords&Wizardry`
- Substrate version: `sw_complete_revised_raw_min100_20260222`
- Model: `all-mpnet-base-v2`
- Retrieval mode: hybrid dense+BM25 (RRF)
- Top-k: 1,3,5,10,20

Run artifacts:

- Mode A report: `out/SwordsAndWizardry/retrieval_lab/min_anchor_rewrite_20260222/min_anchor_rewrite_a_raw_only_20260222_222004/REPORT.md`
- Mode C report: `out/SwordsAndWizardry/retrieval_lab/min_anchor_rewrite_20260222/min_anchor_rewrite_c_raw_first_merge_rerank_20260222_222218/REPORT.md`

Comparison baselines:

- Original Mode A (21q): `out/SwordsAndWizardry/retrieval_lab/baseline_20260222/sw_complete_revised_hybrid_a_raw_only_20260222_210347/metrics.json`
- Original Mode C (21q): `out/SwordsAndWizardry/retrieval_lab/baseline_20260222/sw_complete_revised_hybrid_c_raw_first_merge_rerank_20260222_210409/metrics.json`

## 4) Results

### 4.1 New rewritten benchmark (35q)

**Mode A (raw-only):**

- MRR: 0.4120
- Hit@10: 0.6000
- Recall@10: 0.5180
- ReqFSH@10: 0.4286
- FSH@10: 0.3714
- Gold-in-candidates (true): 0.7429
- Retrieval misses: 9

**Mode C (raw-first merge-rerank):**

- MRR: 0.5112
- Hit@10: 0.7429
- Recall@10: 0.6971
- ReqFSH@10: 0.6286
- FSH@10: 0.5429
- Gold-in-candidates (true): 0.8571
- Retrieval misses: 5

### 4.2 Delta vs original full benchmark (21q)

| Metric | Base A (21q) | New A (35q) | Delta A | Base C (21q) | New C (35q) | Delta C |
|---|---:|---:|---:|---:|---:|---:|
| MRR | 0.4916 | 0.4120 | -0.0796 | 0.5969 | 0.5112 | -0.0857 |
| Hit@10 | 0.8095 | 0.6000 | -0.2095 | 0.8095 | 0.7429 | -0.0667 |
| Recall@10 | 0.3976 | 0.5180 | +0.1203 | 0.6034 | 0.6971 | +0.0938 |
| ReqFSH@10 | 0.1429 | 0.4286 | +0.2857 | 0.3333 | 0.6286 | +0.2952 |
| FSH@10 | 0.1429 | 0.3714 | +0.2286 | 0.3333 | 0.5429 | +0.2095 |
| Gold-in-cand (true) | 0.9048 | 0.7429 | -0.1619 | 0.8571 | 0.8571 | +0.0000 |
| Retrieval misses | 2 | 9 | +7 | 3 | 5 | +2 |

## 5) Interpretation

Main finding: the rewrite successfully removed structural suppression in compositional metrics.

- Large gains in `ReqFSH@10` and `FSH@10` indicate that previous low full-set performance was heavily influenced by oversized required sets.
- `Recall@10` improvements confirm better measurable coverage once required sets are right-sized.
- `MRR` and `Hit@10` drops are expected under harder/expanded query count and reduced duplicate-anchor inflation.
- Mode C remains stronger than Mode A across key metrics, indicating merge-rerank still provides value with minimal-anchor annotations.

Bottom line:

- This benchmark is now a better instrument for diagnosing retrieval vs benchmark-construction effects.
- The remaining misses are now more actionable failure signals rather than artifacts of impossible scoring contracts.

## 6) Remaining Mode C Misses (Priority Set)

1. `sw_rev_s02_treasure_division_procedure`
2. `sw_rev_s08_first_level_cleric_spells`
3. `sw_rev_u05a_character_attributes_to_record`
4. `sw_rev_s12b_morale_guidance`
5. `sw_rev_s14c_time_cost_of_searching`

## 7) Handoff: Instructions for the Next Agent

### 7.1 Goal

Produce a new report focused only on the 5 remaining Mode C misses, with:

- root-cause classification per miss,
- evidence-backed diagnosis (query, gold, top-k retrieved, rank behavior),
- and 2-3 concrete remediation strategies per miss with expected metric impact.

### 7.2 Required Method (Algorithmic + Agentic)

Use a two-track workflow:

- **Algorithmic track:** deterministic extraction of miss diagnostics.
- **Agentic track:** semantic interpretation and intervention design.

#### Algorithmic Track Steps

1. **Load artifacts**
   - Mode C metrics/report/retrieved chunks:
     - `out/SwordsAndWizardry/retrieval_lab/min_anchor_rewrite_20260222/min_anchor_rewrite_c_raw_first_merge_rerank_20260222_222218/metrics.json`
     - `.../REPORT.md`
     - `.../retrieved_chunks.json`
   - Benchmark source:
     - `evals/retrieval/SwordsandWizardy/swords_wizardry_complete_revised_benchmark_min_anchor_atomic_rewrite.json`

2. **Create a miss table**
   For each missed query:
   - query text
   - `required_gold` IDs
   - whether gold appears anywhere in candidates
   - first relevant rank (if any)
   - top-10 retrieved IDs + scores
   - heading/page metadata for retrieved vs gold

3. **Compute lexical and structural distance**
   For each miss:
   - token overlap between query text and gold unit text
   - overlap between query text and top-10 texts
   - heading mismatch flags (query concept vs gold heading)
   - page-local distractor density (count of near-topic non-gold candidates in top-k)

4. **Compare A vs C failure transitions**
   - classify each miss as:
     - persists in A and C,
     - fixed by C,
     - introduced by C,
     - rank-improved but still miss.

5. **Output quantitative diagnosis**
   - per-query failure type tag:
     - `query-phrase mismatch`
     - `gold anchor too narrow`
     - `heading dilution`
     - `semantic confound`
     - `merge promotion side-effect`

#### Agentic Track Steps

1. **Read source context around each gold unit**
   - inspect neighboring EvidenceUnits on same page/heading.
   - verify that anchor unit actually contains the operational fact asked.

2. **Evaluate annotation correctness**
   - if the selected anchor is adjacent to a better operational unit, propose:
     - keep current required + add adjacent as supporting, or
     - replace required anchor (with rationale and diff preview).

3. **Propose retrieval interventions (without changing corpus)**
   For each miss, choose among:
   - query rewrite variants (externally phrased, user-like wording),
   - alias expansion dictionary (domain synonyms),
   - heading-aware boost (lightweight),
   - structured field boost (`expected_answer_summary` weighting),
   - candidate rerank rule specific to procedural cues.

4. **Run constrained A/B probes**
   - tiny controlled reruns on only the 5 misses or a 5-query mini-batch.
   - compare baseline vs one intervention at a time.
   - report `Hit@10`, `Recall@10`, `ReqFSH@10`, and miss count deltas.

### 7.3 Suggested Deliverables for Next Agent

1. `REPORT-ModeC-Remaining-Misses-Analysis-YYYY-MM-DD.md`
   - per-miss root cause + evidence table
   - recommended fix list with confidence level
   - minimal changes first, then optional deeper changes

2. Optional experimental file(s):
   - a 5-query diagnostic batch JSON for rapid iteration
   - a proposal patch for benchmark annotation adjustments (if justified)

3. Verification section:
   - exact commands used
   - before/after metrics
   - known limits and unresolved ambiguities

### 7.4 Suggested Prioritization

Prioritize by expected leverage:

1. `sw_rev_s14c_time_cost_of_searching`
2. `sw_rev_s12b_morale_guidance`
3. `sw_rev_s02_treasure_division_procedure`
4. `sw_rev_s08_first_level_cleric_spells`
5. `sw_rev_u05a_character_attributes_to_record`

Rationale: first two appear likely to be phrase/anchor mismatch classes that often improve with small query+anchor adjustments; the latter may require deeper heading/context disambiguation.

## 8) Conclusion

The min-anchor rewrite achieved its primary purpose: it transformed the benchmark from structurally suppressive to diagnostically useful for compositional retrieval metrics. The remaining five misses are now a focused, tractable target for next-step improvement work.

# Report: Query Decomposition Per-Query Investigation

**Date:** 2026-03-17  
**Scope:** Per-query investigation of Responses-based query decomposition on `PHB` and `PF2E` multihop benchmarks.  
**Artifacts compared:**

- `out/retrieval_lab/experiments/phb5e_multihop_e0_baseline_20260317_031847`
- `out/retrieval_lab/experiments/phb5e_multihop_e6_responses_decompose_20260317_035623`
- `out/retrieval_lab/experiments/pf2e_multihop_r0_hybrid_baseline_20260317_130939`
- `out/retrieval_lab/experiments/pf2e_multihop_e6_responses_decompose_20260317_040337`

---

## Executive Summary

The per-query investigation confirms that the decomposition regressions are real on both benchmarks, but the shape of the damage differs:

- `PHB` shows a true retrieval-quality regression. Decomposition worsens 11 queries, improves 7, and leaves 49 unchanged. It also creates 4 `hit -> miss` transitions and 2 `hit@10` drops.
- `PF2E` on the re-locked surface shows a milder but still real regression. Decomposition worsens 4 queries, improves 3, and leaves 63 unchanged. It creates no `hit -> miss` transitions, but it does degrade completeness and one `hit@10`.

The most important mechanical finding is that the final decompose rankings are **perfectly locked to the run's own internal `baseline_topN`** for every query. That means:

1. The appended tail is not the only source of regression.
2. Some of the divergence from the standalone baseline is already present earlier in the decompose execution path.
3. Prompt tuning alone is unlikely to fully solve the issue.

That said, the decomposition-generated variants are still often low-value:

- `PHB`: 46/67 queries add **no new gold** from variants.
- `PF2E`: 57/70 queries add **no new gold** from variants.
- The current `only_add` policy still appends a very large tail:
  - `PHB`: 30 added candidates on all 67 queries.
  - `PF2E`: 30 added candidates on 65/70 queries.

Verdict:

- Do **not** promote decomposition for model-policy decisions.
- Before the next tuning round, instrument and verify **baseline parity inside the decompose path**.
- If we want a narrower policy after that, `PF2E` has some evidence for a **hard-case-only** decomposition gate; `PHB` does not.

---

## Method

I compared the baseline and decomposition runs at three levels:

1. `per_query.full_working_set.json`
   - Query-level rank, hit, required coverage, and full-set coverage deltas.
2. `retrieved_chunks.full_working_set.json`
   - Final retrieved candidate lists and `qe_fusion` debug payloads.
3. `forensics_bundles.json`, `experiment.json`, `benchmark_contract_validation.json`, and `grounding_audit.json`
   - Run-level controls, fusion configuration, and benchmark-surface sanity.

For `PF2E`, this investigation uses the re-locked baseline:

- `pf2e_multihop_r0_hybrid_baseline_20260317_130939`

This avoids the earlier gold-surface drift and gives an apples-to-apples comparison.

---

## Benchmark-Level Query Outcomes

### PHB

Per-query reciprocal-rank deltas:

- Worse: `11`
- Unchanged: `49`
- Improved: `7`

Failure transitions:

- `hit -> miss`: `4`
- `miss -> hit`: `0`
- `hit@10` worsened: `2`
- `hit@10` improved: `0`

Variant behavior:

- `only_add_added = 30` on `67/67` queries
- `new_gold_added_by_variants = 0` on `46/67` queries
- `new_gold_added_by_variants = 1` on `15/67` queries
- `new_gold_added_by_variants = 2` on `6/67` queries

Interpretation:

- The dominant pattern is not broad recall gain.
- Most queries pay the cost of additional variant retrieval without recovering new gold.
- The worst failures are concentrated in broad synthesis and microbundle queries where the prompt expands into off-surface or too-general obligations.

### PF2E

Per-query reciprocal-rank deltas:

- Worse: `4`
- Unchanged: `63`
- Improved: `3`

Failure transitions:

- `hit -> miss`: `0`
- `miss -> hit`: `0`
- `hit@10` worsened: `1`
- `hit@10` improved: `0`

Variant behavior:

- `only_add_added = 30` on `65/70` queries
- `new_gold_added_by_variants = 0` on `57/70` queries
- `new_gold_added_by_variants = 1` on `10/70` queries
- `new_gold_added_by_variants = 2` on `3/70` queries

Interpretation:

- `PF2E` is more stable than `PHB`.
- The main damage is completeness loss (`full_set_hit@20`, `required_full_set_hit@10`) rather than catastrophic head collapse.
- Variants frequently add adjacent rulebook material without improving the answer-bearing surface.

---

## Important Mechanical Finding

### The final decompose top-20 exactly equals the run's internal locked baseline top-20

From `retrieved_chunks.full_working_set.json`:

- `PHB`: final top-20 exactly matches `qe_fusion.baseline_topN` on `67/67` queries
- `PF2E`: final top-20 exactly matches `qe_fusion.baseline_topN` on `70/70` queries

This is consistent with the current `only_add` fusion implementation in:

- `retrieval_lab/query_enhancement/multi_query.py`
- `retrieval_lab/orchestration/dense_mode.py`
- `retrieval_lab/orchestration/bm25_mode.py`

Implication:

- The appended tail is not directly reshuffling the final locked prefix inside the decompose run.
- Therefore, the regression versus the standalone baseline is not explained purely by tail pollution after locking.
- Some divergence is already entering the path before or during construction of the decompose run's internal "baseline" retrieval result.

### The standalone baseline still diverges materially from the decompose run's locked internal baseline

Comparing the standalone baseline runs to the decomposition runs:

- `PHB`
  - top-1 exact match: `62/67`
  - top-3 exact match: `46/67`
  - top-5 exact match: `29/67`
  - top-20 exact match: `0/67`
- `PF2E`
  - top-1 exact match: `65/70`
  - top-3 exact match: `47/70`
  - top-5 exact match: `29/70`
  - top-20 exact match: `0/70`

Mean overlap:

- `PHB`
  - mean top-10 Jaccard: `0.800`
  - mean top-20 Jaccard: `0.597`
  - mean standalone baseline top-20 retained somewhere in final top-50: `0.868`
- `PF2E`
  - mean top-10 Jaccard: `0.797`
  - mean top-20 Jaccard: `0.593`
  - mean standalone baseline top-20 retained somewhere in final top-50: `0.876`

Interpretation:

- The decompose path is not simply "baseline top-20 plus extra tail" relative to the standalone baseline run.
- There is an upstream baseline-parity problem or execution-path difference that should be understood before interpreting all regressions as prompt/fusion quality issues.

This does **not** exonerate decomposition. It means the regression has two layers:

1. Baseline divergence inside the decompose execution path.
2. Low-yield variant expansion that rarely adds gold and often adds generic candidates.

---

## Per-Query Findings: PHB

### High-confidence PHB failure modes

#### 1. Over-broad obligation explosion on named-entity synthesis questions

Representative query:

- `phb5e_mh_ws_030`

Question shape:

- Multi-entity synthesis across revised spells (`Prayer of Healing`, `Mass Healing Word`, `Sleep`, `Aid`) plus feat/class-feature interaction (`Healer`, `Disciple of Life`, `Lay on Hands`).

Observed regression:

- `first_gold_rank`: `7 -> 28`
- `hit@10`: `true -> false`
- `required_full_set_hit@10`: `true -> false`
- `full_set_hit@20`: `true -> false`

Why it failed:

- The decomposition prompt produced `17` variants, including:
  - older-edition requests (`original PHB (pre-2024)`)
  - external-source requests (`Sage Advice or official 2024 designer rulings`)
  - generic rules lookups (`action economy`, `stacking increases to maximum hit points`)
- The resulting retrieved additions include relevant chunks, but also broaden the retrieval surface toward generic cleric/paladin/healing material rather than preserving the exact comparison surface.

Diagnosis:

- This is the clearest example of the prompt generating **plausible research tasks** instead of **tight retrieval obligations constrained to the active corpus**.

#### 2. Prompt-invented off-corpus or low-value obligations on narrow microbundle questions

Representative query:

- `phb5e_mh_mb_007a`

Question:

- Whether `Savage Attacker` applies to melee and ranged weapon attacks.

Observed regression:

- `first_gold_rank`: `10 -> miss`
- `hit@10`: `true -> false`
- `required_full_set_hit@10`: `true -> false`
- `full_set_hit@20`: `true -> false`

Why it failed:

- Variants include:
  - `Sage Advice or official 2024 rulings`
  - thrown-weapon or improvised-ranged examples
  - generic definitions of weapon attack and damage roll
- Added chunks include noisy surfaces like other feats, monster actions, and unrelated weapon mastery material.

Diagnosis:

- On narrow factual questions, decomposition is turning one obligation into several weaker ones, some of which are outside the corpus or only loosely related.

#### 3. Completeness degradation without a miss

Representative query:

- `phb5e_mh_mb_020c`

Observed regression:

- `first_gold_rank`: `1 -> 2`
- `required_full_set_hit@10`: `true -> false`
- `full_set_hit@20`: unchanged

Why it matters:

- Even when the query stays a "hit," decomposition can still break required coverage.
- This matters for multi-gold evaluation and downstream citation quality.

### PHB summary

The PHB evidence does **not** support a narrower production policy yet. Even on hard cases, the gain is inconsistent:

- baseline `required_full_set_hit@10 = false`: `23` queries
  - improved: `2`
  - unchanged: `16`
  - worsened: `5`

That is not a reliable enough controller surface for promotion.

---

## Per-Query Findings: PF2E

### High-confidence PF2E failure modes

#### 1. Specific rules questions broaden into adjacent rules and feat surfaces

Representative query:

- `pf2e_001_27`

Question:

- What the GM should do if a player is stumped or asks an unlikely question during `Recall Knowledge`.

Observed regression:

- `first_gold_rank`: `10 -> 16`
- `hit@10`: `true -> false`
- `required_full_set_hit@10`: `true -> false`

Why it failed:

- Variants include:
  - broad `Gamemastery Guide` or GM-advice requests
  - generic skill-check/improvise-answer guidance
- Added candidates include adjacent but low-value surfaces such as:
  - `Automatic Knowledge`
  - general GM actions
  - unrelated divination spell material

Diagnosis:

- The decomposition prompt is widening the surface from a specific `Recall Knowledge` ruling to a more general GM-advice neighborhood.

#### 2. Path enumeration questions pull in taxonomy instead of answer-bearing archetype requirements

Representative query:

- `pf2e_mh_ws_020`

Question:

- Which paths let a rogue gain arcane spellcasting, what the prerequisites are, and when spells first arrive.

Observed regression:

- `first_gold_rank`: `1 -> 3`
- `full_set_hit@20`: `true -> false`

Why it failed:

- Variants hit relevant paths (`wizard`, `sorcerer`, `bard` dedication), but also introduce generic taxonomic surfaces:
  - `Arcane`
  - spellcasting overview
  - spellcasting services
  - broad class pages

Diagnosis:

- This does not destroy the query, but it reduces completeness by consuming candidate budget with broad classification material rather than the exact multiclass progression details.

#### 3. Already-solved exact match questions are being destabilized

Representative query:

- `pf2e_001_40`

Question:

- `Heal` at 2nd level, two-action version versus one-action version.

Observed regression:

- `first_gold_rank`: `1 -> 3`
- `hit@10`: unchanged
- `required coverage`: unchanged

Why it failed:

- Variants invite:
  - variable-action spell-casting rules
  - heightened spell rules
  - "willing living creature" phrasing expansions
- Added candidates include items, battle medicine, healing potions, and related healing mechanics.

Diagnosis:

- This is a classic "already solved by the baseline" question that decomposition should have skipped entirely.

### PF2E summary

Unlike PHB, PF2E shows some evidence that decomposition could be gated to hard cases:

- baseline `required_full_set_hit@10 = false`: `16` queries
  - improved: `2`
  - unchanged: `14`
  - worsened: `0`

This is still weak evidence, but it is directionally better than PHB.

It suggests a future `PF2E`-specific policy might be viable **if** baseline parity inside the decompose path is fixed first.

---

## Cross-Benchmark Patterns

### 1. The prompt still behaves like a research planner, not a strict retrieval controller

Across both corpora, the decomposition outputs often contain:

- external-source obligations
- older-edition or cross-edition obligations
- generic rulebook taxonomy searches
- high-level explanatory searches rather than citation-targeted retrieval obligations

This is most damaging on:

- narrow fact questions
- already-solved exact-match questions
- multi-entity synthesis prompts where the model invents too many branches

### 2. Large fixed tail expansion is the default, not the exception

Current `only_add` settings:

- `baseline_keep_n: 20`
- `admission_cutoff: 50`
- `variant_k_per_query: 20`
- `prefix_lock_n: 20`

Observed behavior:

- `PHB`: every query appends 30 extra admitted chunks
- `PF2E`: almost every query appends 30 extra admitted chunks

This is too expensive for a policy that usually adds no new gold.

### 3. New gold recovery is rare

Queries with any `new_gold_added_by_variants`:

- `PHB`: `21/67`
- `PF2E`: `13/70`

But new gold does not consistently translate into better rank or better completeness.

### 4. Completeness metrics are more fragile than simple hit metrics

The most common degradation mode is:

- `hit@10` stays the same
- `full_set_hit@20` or `required_full_set_hit@10` gets worse

This matters because the system goal is not merely "touch a relevant page," but recover enough structured evidence to support deterministic rule construction.

---

## Policy Recommendations

## 1. Do not promote unconditional decomposition

This should remain out of the default model policy for both corpora.

Reason:

- `PHB` clearly fails.
- `PF2E` is milder but still net-negative.

## 2. Investigate baseline parity inside the decompose path before further prompt tuning

This is the first engineering task I would do next.

Reason:

- The final decompose top-20 is perfectly locked to the run's internal baseline.
- But that internal baseline still differs from the standalone baseline run.

So before changing prompts or profiles again, verify:

- query embeddings used for the original query row
- offset accounting when variants are expanded
- hybrid fusion parity between standalone baseline and the "baseline" branch inside decompose mode
- whether any query-normalization or scoring path differs when `use_qe = true`

## 3. If we try a narrower policy, make it baseline-first and hard-case-only

Recommended shape:

1. Run a cheap baseline retrieval first.
2. Only decompose if the baseline looks structurally weak.

Possible activation signals:

- no gold-like entity anchors in the top results
- top results dominated by chapter headers / taxonomy pages / overview pages
- no required-coverage proxy from a cheap structural heuristic
- broad T3 question with multiple named entities **and** weak baseline evidence

Important:

- `PF2E` has some evidence that this might be worth trying.
- `PHB` does not yet justify even a gated rollout.

## 4. Tighten the decomposition prompt to corpus-native obligations only

Add explicit prohibitions:

- no `Sage Advice`
- no external rulings
- no older editions unless the active corpus explicitly contains them
- no "official examples" unless present in the corpus
- no generic background research tasks

Require each variant to preserve at least one anchored corpus-native entity from the user query:

- spell
- feat
- class feature
- condition
- action
- subsystem name

## 5. Reduce tail size aggressively

Current append volume is too high for the observed yield.

Suggested next experiment:

- lower `variant_k_per_query`
- lower `admission_cutoff`
- keep `baseline_keep_n = eval_k` or smaller locked prefix for analysis
- require stronger lexical/entity overlap before a variant candidate is admitted

## 6. Add decomposition diagnostics that measure utility, not just existence

For each query, log:

- whether any variant added new required gold
- whether any variant improved first required-gold rank
- how many added candidates were broad headings / taxonomy / overview chunks
- lexical overlap between variant text and original query entities

Without this, we can tell that variants exist, but not whether they are actually useful.

---

## Recommended Next Steps

### Immediate

1. Verify baseline parity inside decompose mode.
2. Keep decomposition out of model-policy promotion.
3. Review this report before any new tuning pass.

### If you want a follow-on experiment after review

I would run one of these, in order:

1. **Parity audit**
   - Confirm why the decompose run's internal baseline differs from the standalone baseline.
2. **PF2E hard-case-only controller**
   - Only decompose when the baseline looks weak.
3. **Prompt tightening pass**
   - Remove external/cross-edition obligations and force corpus-native anchors.

### What I would not do next

- I would not increase decomposition breadth further.
- I would not promote a shared `PHB + PF2E` decomposition policy.
- I would not interpret all current regressions as prompt-only failures without first resolving the baseline-parity issue.

---

## Bottom Line

The per-query evidence says the current Responses-based decomposition path is not ready for promotion.

- On `PHB`, it is clearly harmful.
- On `PF2E`, it is mostly neutral-to-harmful, with only limited signs that a hard-case-only controller could eventually be useful.
- The traces also reveal an upstream parity issue: the decompose run's locked internal baseline does not match the standalone baseline closely enough, so some of the measured regression is entering before the appended variant tail is even considered.

That makes the next decision point clear:

- first verify baseline parity inside the decompose path,
- then, if desired, test a much narrower `PF2E`-only hard-case controller rather than another broad decomposition rollout.

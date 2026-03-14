# Experiment: PF2E LLM Reranking

**Purpose:** Define a discussion-first reranking experiment for Pathfinder 2e multihop retrieval that fits the current Retrieval Lab architecture and can be debated before execution.

**Status:** Proposed, not yet executed.  
**Related:** `bounded_multihop_retrieval_design_memo.md`, `pf2e_multihop_benchmark_design.md`, `retrieval_lab/orchestration/dense_mode.py`, `retrieval_lab/experiments/hybrid/pf2e_mpnet_hybrid_baseline.yaml`.

---

## 1. Why this is the next lever

The current PF2E dual-surface benchmark gives a specific signal:

- the end-to-end parent slice shows `gold_in_candidates = 1.0` under both dense and hybrid baselines, but `ReqFSH@10 = 0.0`
- the micro-bundle slice shows partial success, with several child obligations already retrievable inside top 10
- hybrid improves some rank-sensitive behavior, but it does not yet assemble the full evidence chain in the top-10 budget
- at least one micro-bundle remains a true retrieval miss, so reranking is not expected to solve every failure class

This is the exact profile where reranking should be tested next:

- candidate-generation is not the only problem
- some gold is already in the pool
- the main unresolved question is whether better ordering can move the required set into the top 10 often enough to matter

The reranking experiment should therefore be framed as a **ranking-depth intervention**, not as a retrieval replacement.

---

## 2. Hypothesis

### Primary hypothesis

An LLM reranker operating on a fixed hybrid candidate pool will improve:

- `ReqFSH@10` on `pf2e_multihop_e2e_working_set`
- `rank_of_last_required_mean` on the same surface
- micro-bundle pass rate on `pf2e_multihop_microbundle_working_set`

without materially degrading first-hit precision on precision-sensitive slices.

### Secondary hypothesis

The biggest gains should appear on queries where:

- `gold_in_candidates = true`
- `first_gold_rank` is already reasonably shallow
- the current failure is incomplete assembly rather than complete absence

### Negative expectation

Reranking should **not** materially fix queries where gold never enters the candidate pool. Those cases should remain signals for Stage B expansion or later Stage C enrichment.

---

## 3. Non-goals

- This is not a Stage C implementation.
- This is not bounded multihop controller work beyond fixed-pool reordering.
- This is not open-ended agentic retrieval.
- This is not answer-generation optimization.
- This is not permission to compare across mismatched benchmark contracts or surfaces.

---

## 4. Design principles

The first reranking slice should obey these rules:

1. **Fixed pool only.**
   The reranker may reorder candidates, but it may not retrieve new ones.

2. **Surface-aware evaluation.**
   Results must be reported separately for:
   - `pf2e_multihop_e2e_working_set`
   - `pf2e_multihop_microbundle_working_set`

3. **Deterministic enough to audit.**
   Use a pinned model, temperature `0`, fixed prompt template, strict schema, cached outputs, and deterministic tie-breaks.

4. **No benchmark leakage.**
   The reranker should not see:
   - `expected_answer_summary`
   - `required_gold`
   - gold rationales
   - benchmark labels such as "micro-bundle" or "e2e"

5. **Trace everything.**
   Every reranked run should make it easy to answer:
   - which candidates moved
   - which required units crossed into or out of top 10
   - whether gains came from real evidence assembly or cosmetic reshuffling

---

## 5. Recommended experiment ladder

Do not jump directly from current hybrid baseline to a single LLM reranker run with no controls. Use a small ladder so we can tell whether any gain is truly LLM-specific.

### R0. Existing baseline

Control:

- current PF2E hybrid baseline
- `retrieval_mode: hybrid`
- `hybrid_fusion_method: cc`

Purpose:

- anchor all comparisons to the current live baseline

### R1. Existing non-LLM rerank control

Control:

- current hybrid candidate pool
- current rerank hook using the existing cross-encoder path or dense second-stage rerank

Purpose:

- establish whether simple reranking already captures most of the available lift
- separate "any reranking helps" from "LLM reranking specifically helps"

### R2. Primary proposed experiment: LLM listwise rerank

Treatment:

- retrieve with the same hybrid CC baseline
- freeze a candidate pool
- ask a pinned LLM to return an ordered subset or ordered full list of candidates
- evaluate post-rerank top-k only

Purpose:

- test whether listwise judgment over a bounded pool better prioritizes complementary evidence for multihop questions

### R3. Optional follow-up: LLM pairwise rerank

Treatment:

- same fixed pool
- pairwise comparisons or tournament-style ordering

Purpose:

- compare stability, cost, and quality against listwise reranking

Recommendation:

- debate and design `R2` now
- keep `R1` as the must-have control
- defer `R3` unless listwise output proves unstable or overly expensive

---

## 6. Primary experiment design: LLM listwise rerank

### 6.1 Retrieval input

Use the current PF2E hybrid baseline exactly as the candidate generator:

- `retrieval_mode: hybrid`
- `hybrid_fusion_method: cc`
- same embedding model as baseline
- same substrate and benchmark projections

This keeps the candidate-generation layer fixed so the readout isolates reranking.

### 6.2 Candidate pool size

Primary recommendation:

- admit the top `40` candidates from the hybrid run into the reranker

Why `40`:

- large enough that missing-complement evidence may already be present
- small enough to keep prompt size and cost bounded
- aligned with the design memo's recommended `max_total_candidate_pool_before_rerank: 40`

Debate point:

- if we believe the current hybrid pool often hides required gold below rank 40, then use `50`
- if we want a tighter production-faithful budget, then use `30`

Default position:

- start with `40`

### 6.3 Candidate payload shown to the model

Each candidate should expose only bounded, audit-friendly fields:

- `candidate_id`
- `baseline_rank`
- `structural_path`
- `unit_type`
- short text excerpt or truncated body

Recommended text budget:

- truncate candidate text to a fixed limit, such as `700-900` characters
- keep deterministic truncation rules

The reranker should not see the full benchmark curation metadata.

### 6.4 Query payload shown to the model

The model should see:

- the normalized user question

Optional but debatable:

- deterministic subquery decomposition generated by the controller

Not allowed in the first rerank experiment:

- expected answer summary
- gold annotations
- benchmark notes

### 6.5 Output schema

The model should return a strict JSON object like:

```json
{
  "ordered_candidate_ids": ["c17", "c03", "c08", "c12"],
  "rationale_tags": {
    "c17": ["direct_rule", "high_specificity"],
    "c03": ["complements_other_evidence"],
    "c08": ["exception_rule"],
    "c12": ["background_context"]
  }
}
```

Allowed rationale tags should come from a small fixed vocabulary, for example:

- `direct_rule`
- `high_specificity`
- `required_anchor_likely`
- `complements_other_evidence`
- `exception_rule`
- `definition_link`
- `table_lookup`
- `generic_context`
- `distractor_risk`

These tags are for audit and analysis, not for scoring.

### 6.6 Determinism and audit constraints

- pinned model ID
- temperature `0`
- fixed prompt template ID and prompt hash
- strict JSON schema validation
- caching required
- deterministic fallback on schema failure
- deterministic tie-break by baseline rank, then `candidate_id`

### 6.7 Hard boundaries

The LLM reranker may:

- reorder candidates
- optionally drop low-value candidates if the schema explicitly supports this

The LLM reranker may not:

- retrieve new candidates
- hallucinate candidate IDs
- emit free-text answers
- cite from outside the provided candidate pool

---

## 7. Scoring plan

The reranking experiment should be scored on both PF2E surfaces separately.

### 7.1 Surface A: `pf2e_multihop_e2e_working_set`

Primary metrics:

- `ReqFSH@10`
- `rank_of_last_required_mean`

Secondary metrics:

- `MRR`
- `Hit@10`
- `Recall@10`

Primary question:

- does reranking move enough already-present evidence into the top 10 to solve more whole multihop tasks?

### 7.2 Surface B: `pf2e_multihop_microbundle_working_set`

Primary metrics:

- `ReqFSH@10`
- per-parent micro-bundle pass rate at 10

Secondary metrics:

- `Hit@10`
- `Recall@10`
- `rank_of_last_required_mean`

Primary question:

- which narrow evidence obligations improve under reranking?

### 7.3 Interpretation rules

If e2e improves and micro-bundles improve:

- reranking is helping both local obligation prioritization and whole-task assembly

If micro-bundles improve but e2e does not:

- reranking is helping local evidence ordering, but full-chain assembly still fails under the top-10 cap

If neither improves:

- ranking is probably not the main bottleneck for that slice

If one or more queries remain `gold_not_in_candidates`:

- treat those as out of scope for reranking and feed them into later structural or Stage C work

---

## 8. Regression guardrails

A reranker should not be promoted on PF2E multihop alone.

It should also be checked against at least one precision-sensitive benchmark slice, such as:

- PF2E 50q benchmark
- a selected clean subset if available
- any known T1-sensitive evaluation surface already used in Retrieval Lab recommendations

Minimum promotion rule:

- meaningful improvement on PF2E multihop rank-sensitive metrics
- no material regression on precision-sensitive slices
- no benchmark-contract mismatch
- no unexplained answer-fidelity regression if answer evaluation is run

---

## 9. Required artifacts

Each rerank run should emit enough detail to support argument, not just scoreboard reading.

### 9.1 Per-run artifacts

- standard Retrieval Lab metrics by surface
- per-query rerank diagnostics
- prompt template ID and prompt hash
- reranker model ID
- cache hit rate

### 9.2 Per-query diagnostics

For each query, record:

- baseline candidate pool size
- pre-rerank top 10 IDs
- post-rerank top 10 IDs
- required gold IDs present in pool
- required gold ranks before rerank
- required gold ranks after rerank
- whether each required unit crossed the top-10 boundary

### 9.3 Summary tables worth keeping

- queries helped by reranking
- queries hurt by reranking
- queries unchanged
- queries that remained candidate misses
- parent-child decomposition summaries for micro-bundles

---

## 10. Debate points before execution

These are the main choices worth debating before any code or runs happen.

### A. Should the first LLM reranker be listwise or pairwise?

Argument for listwise:

- better fit for multihop complementarity
- one pass can reason about coverage and redundancy

Argument for pairwise:

- easier to constrain
- sometimes more stable
- potentially clearer failure analysis

Current recommendation:

- start with listwise
- keep pairwise as follow-up only if listwise proves unstable

### B. Should we compare against a cross-encoder first?

Argument for yes:

- the codebase already has a rerank path
- gives a cheap and fair non-LLM control
- avoids attributing generic reranking lift to the LLM

Current recommendation:

- yes, include the existing cross-encoder rerank as `R1`

### C. How large should the candidate pool be?

Argument for `40`:

- balanced between recall opportunity and cost

Argument for `50`:

- closer to the current existing rerank hook in live code

Argument for `30`:

- more production-like and cheaper

Current recommendation:

- start with `40`
- if debate remains unresolved, run `40` and `50` as a tiny ablation

### D. Should the reranker see controller-generated subqueries?

Argument for yes:

- helps the model recognize multi-obligation structure

Argument for no:

- muddies the attribution between reranking and query decomposition

Current recommendation:

- first experiment should use the normalized original query only
- add structured subqueries later as a separate ablation

### E. Should the reranker be allowed to drop candidates rather than only reorder?

Argument for reorder-only:

- simpler attribution
- easier to compare pre/post ranks

Argument for reorder-and-prune:

- better practical top-k focus

Current recommendation:

- reorder only in the first slice

---

## 11. Proposed first decision

If we want the cleanest first debate target, the first reranking experiment should be:

- baseline generator: PF2E hybrid CC
- control 1: no rerank
- control 2: existing cross-encoder rerank over fixed pool
- treatment: LLM listwise rerank over fixed pool of 40
- benchmark surfaces:
  - `pf2e_multihop_e2e_working_set`
  - `pf2e_multihop_microbundle_working_set`
- regression guard:
  - PF2E 50q or another precision-sensitive slice

This design gives us the right question:

- not "can an LLM do something impressive?"
- but "does an LLM reranker produce measurable full-set and rank-depth lift beyond the current hybrid baseline and beyond a simpler reranking control?"

---

## 12. What success would look like

The experiment is worth pursuing further if it shows most of the following:

- e2e `ReqFSH@10` improves on the PF2E multihop parent slice
- e2e `rank_of_last_required_mean` improves meaningfully
- micro-bundle pass rate improves on the same parent families
- gains cluster on current ranking-depth failures rather than on already-easy queries
- there is no meaningful regression on precision-sensitive benchmark slices
- traces clearly show already-present required evidence moving upward rather than noisy churn

If those do not happen, the next lever is probably not more reranking work. It is more likely:

- structural expansion
- better decomposition
- or later Stage C typed enrichment for true candidate misses

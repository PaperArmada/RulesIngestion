# Design Memo: Bounded Multihop Retrieval, LLM Reranking, and Retrieval-Lab-Native Answer Evaluation

**Status:** Canonical synthesized memo  
**Audience:** RulesIngestion / Retrieval Lab / Stage C planning  
**Purpose:** Define a concrete, bounded path for multihop retrieval, LLM reranking, and answer evaluation that fits the current Retrieval Lab architecture while preserving the original architectural intent.

---

## 1. Executive Summary

The next retrieval architecture slice should still be:

- bounded multihop retrieval rather than open-ended agent loops
- LLM reranking as a ranking-depth lever rather than a hidden retrieval replacement
- narrow Stage C enrichment as the later typed substrate for bounded closure
- answer evaluation integrated into Retrieval Lab runs rather than treated as an informal sidecar

The important update is that this work must now be explicitly aligned to the current Retrieval Lab model:

- experiments are surface-aware
- comparisons are contract-aware
- promotion is selected-surface-aware
- hybrid defaults should be discussed in CC-default terms unless a corpus-specific config overrides them

This memo therefore synthesizes two truths:

1. The original architectural direction was correct.
2. The integration details must reflect the live Retrieval Lab system, not an older single-surface or external-harness framing.

---

## 2. Purpose and Problem Statement

The current system has three adjacent but distinct failure classes.

First, some failures are candidate-generation failures: the needed evidence never enters the candidate pool.

Second, some are ranking-depth failures: gold is already in candidates, but it is ranked too low to make the final retrieved set.

Third, some are answer failures: retrieved evidence is adequate, but the generated answer is incomplete, overclaims, or fails to assemble the required evidence into the right answer shape.

These should not be treated as one problem.

They imply three different interventions:

- bounded multihop retrieval for candidate-generation and evidence-completion failures
- LLM reranking for ranking-depth failures
- answer evaluation for end-to-end answer quality

Stage C narrow enrichment remains the longer-term substrate investment that later makes multihop retrieval materially better, but the first controller slice can already operate over Stage B structure and current retrieval-only projections.

---

## 3. Architectural Commitments

This design remains aligned with the current project contracts:

- EvidenceUnits remain the only admissible evidence
- retrieval-only expansions remain non-authoritative
- Retrieval Lab remains comparative rather than a correctness oracle
- Stage C and any later Stage D work remain deterministic, versioned, and separately evaluable
- answer evaluation measures answers generated from retrieved context, not free model world knowledge

This memo is therefore:

- **not** full graph first
- **not** broad HyDE first
- **not** open-ended agentic retrieval first
- **yes** bounded multihop retrieval
- **yes** LLM reranking
- **yes** Retrieval-Lab-native answer evaluation
- **yes** narrow Stage C enrichment as the later typed substrate

---

## 4. Design Goals and Non-Goals

### 4.1 Goals

The proposed system should satisfy the following goals:

1. Improve evidence completion for multi-evidence and bounded-enumeration queries.
2. Improve rank depth without causing material T1 regressions.
3. Preserve determinism, auditability, replayability, and traceability.
4. Make every additional retrieval step legible in logs and per-query trace artifacts.
5. Keep comparisons valid under the current corpus-contract and benchmark-projection model.
6. Separate retrieval improvement from answer improvement while still evaluating them in one run lifecycle.
7. Preserve EvidenceUnits as the only citable layer.
8. Produce recommendation-grade artifacts that fit the current surface-aware promotion model.

### 4.2 Non-goals

1. This is not full Stage D graph construction.
2. This is not open-ended runtime agentic search.
3. This is not a change to admissible evidence; EvidenceUnits remain canonical.
4. This is not permission to compare runs across incompatible contracts or mismatched surfaces.
5. This is not a commitment to ship LLM reranking before it clears regression, determinism, and promotion gates.

---

## 5. Architectural Position and Stack

The next retrieval layer should be a deterministic retrieval controller rather than a free-form agent.

### Proposed stack

```text
User query
  -> normalize
  -> retrieve baseline candidates
  -> bounded retrieval controller
       -> optional query decomposition / rewrite
       -> structural expansion
       -> typed expansion (later, Stage C-assisted)
       -> candidate pool assembly
  -> reranker
  -> final top-N EvidenceUnits
  -> answer synthesis
  -> Retrieval-Lab-native answer evaluation
```

This preserves the existing architecture rule that graph-like behavior remains retrieval-only expansion rather than citation-bearing evidence.

---

## 6. Placement in the Current Retrieval Lab Architecture

The proposal should plug into the live Retrieval Lab lifecycle as follows:

```text
Stage A/B -> substrate shaping -> benchmark projection validation -> retrieval run
        -> bounded retrieval controller / rerank features
        -> score explicit evaluation surfaces
        -> optional auto-gold review
        -> optional answer evaluation
        -> prod_readiness / recommendation artifacts
```

This means bounded multihop retrieval and LLM reranking are not a parallel system. They are retrieval-time features inside the retrieval run stage.

Answer evaluation is not best treated as a wholly separate external harness. It should be an optional downstream stage inside the same experiment flow so that retrieval outputs, answer outputs, contracts, surfaces, and promotion semantics all align.

This placement has several consequences:

- every controller run must know which benchmark surface it is scoring
- answer evaluation should attach to the same run and same surface semantics
- post-review surfaces must remain distinct from pre-review or clean-core surfaces
- recommendation decisions should point to the selected surface rather than a generic report file

---

## 7. Surface and Contract Policy

This is the most important operational update from the revised architecture.

### 7.1 Required evaluation surfaces

Every serious experiment should score at least:

- `full_working_set`
- `clean_subset`

### 7.2 Promotion surface

Unless a run explicitly overrides this for a justified reason, the recommendation-grade reading should come from:

- `prod_readiness.json.selected_surface`

In current practice, this is usually:

- `clean_subset`

### 7.3 Optional review surfaces

If auto-gold review is enabled, a run may also produce:

- `pre_review_manual`
- `post_review_applied`

These are useful for analysis, but they should not silently replace the normal recommendation surface.

### 7.4 Contract compatibility

Multihop, rerank, and answer-eval experiments must not be compared across:

- incompatible corpus contracts
- incompatible benchmark projection contracts
- mismatched benchmark surfaces
- materially different retrieval-mode or fusion-mode assumptions when those affect the readout

### 7.5 Answer-eval surface policy

Answer evaluation should run per surface, not as a single global output. The default recommendation-grade answer-eval readout should be on the selected promotion surface.

In most cases that means:

- retrieval metrics on both `full_working_set` and `clean_subset`
- answer metrics at least on `clean_subset`
- optional answer metrics on `full_working_set` and review surfaces for analysis

---

## 8. Components

### A. Retrieval Controller

A deterministic orchestrator that decides which retrieval operators to run, in what order, and under what budget.

It is not an open-ended agent.

### B. Reranker

A candidate reordering layer, initially evaluated as a separate lever.

It acts on a fixed candidate pool and should be measured primarily on rank-sensitive and full-set metrics.

### C. Retrieval-Lab-Native Answer Evaluation

An optional evaluation stage inside the Retrieval Lab run lifecycle that scores answer quality against expected answer summaries, required evidence coverage, and citation fidelity.

### D. Stage C Enrichment Adapter

Not required for the first controller slice, but the controller should be built so it can later consume narrow typed enrichments such as:

- ownership
- level gating
- row-to-definition linkage
- progression linkage
- base / exception linkage
- delta / base linkage

---

## 9. Bounded Retrieval Controller

The bounded retrieval controller remains the core design choice.

### 9.1 Definition

A deterministic retrieval orchestrator that runs a small, fixed operator vocabulary under hard budgets.

### 9.2 Responsibilities

- improve candidate generation when gold is absent from the pool
- improve evidence completion for bounded multi-evidence queries
- add structured, auditable retrieval-time expansion
- preserve provenance for every added candidate

### 9.3 First-slice scope

The controller should support Stage B-only structural completion first, then later consume Stage C typed enrichments.

Recommended sequencing:

1. Stage B structural expansion
2. LLM reranking over the resulting pool
3. Stage C-assisted typed expansion
4. only later reconsider a fuller graph formalization

---

## 10. Operator Vocabulary

The controller gets a deliberately small action set. Every operator must be deterministic under fixed inputs and must emit a trace record.

### 10.1 Core operators

#### `retrieve_original(query)`

Run the current default retrieval policy for the active corpus and config.

This should remain anchored to the current configured baseline so comparisons remain meaningful. Do not hard-code older RRF-first assumptions. At the Retrieval Lab harness level, hybrid should now be treated as CC-default unless explicitly overridden.

#### `rewrite_query(query, mode)`

Produce constrained query variants.

Initial modes:

- `dict` - deterministic synonym/profile expansion
- `decompose` - bounded multi-facet split
- `llm_structured` - pinned-model structured rewrite, only if cached and schema-valid

Determinism requirements:

- pinned model
- temperature 0
- schema-validated output
- cache key includes corpus/profile/prompt identity
- stable ordering of outputs

#### `retrieve_variant(query_variant)`

Run the standard retriever over each approved variant.

#### `fuse_candidates(candidate_lists, method)`

Merge per-query results with deterministic dedupe.

Allowed initial methods:

- `stable_union`
- `cc`
- `rrf`

Because the live harness now treats CC as the default hybrid mode, the fusion vocabulary and experiment matrix should treat CC as first-class rather than assuming RRF is the default fused baseline.

#### `expand_structural(anchor_unit_id, policy)`

Add bounded neighborhood candidates from Stage B structure or existing retrieval-only projections.

Initial policies:

- `same_section`
- `same_table_group`
- `same_list_group`
- `same_catalog_neighborhood`
- `clause_family`
- `pairing_projection`

#### `expand_typed(anchor_unit_id, policy)`

Reserved for Stage C-assisted expansion.

Initial policies:

- `same_option_family`
- `gated_by_level`
- `row_refers_to_definition`
- `progression_linked`
- `base_exception`
- `delta_base`

This should remain disabled until the narrow enrichment slice exists and is schema-validated.

#### `rerank(candidate_pool, mode)`

Reorder a fixed pool.

Initial modes:

- `none`
- `heuristic`
- `llm_pairwise`
- `llm_listwise`

#### `stop(reason)`

Terminate the controller once budget is exhausted or evidence coverage is sufficient.

Initial reasons:

- `budget_exhausted`
- `no_new_candidates`
- `sufficient_coverage`
- `policy_stop`

### 10.2 Operator contract fields

Every operator should declare:

- `operator_name`
- `version`
- `inputs`
- `preconditions`
- `budget_cost`
- `determinism_mode`
- `outputs`
- `trace_payload_schema`

### 10.3 Recommended first controller policy

For v0, keep the controller simple:

1. `retrieve_original`
2. if candidate ceiling looks weak, `rewrite_query` with `dict` or `decompose`
3. `retrieve_variant`
4. `fuse_candidates`
5. `expand_structural` on top 1-3 anchors only
6. `rerank`
7. `stop`Star Finder 2e and 

No loops beyond one rewrite pass and one expansion pass.
No recursive search.
No speculative branching.

---

## 11. Controller Policy and Budgets

To avoid drift into vague "agentic retrieval," hard budgets should live in config rather than prompt text.

Recommended starting budgets:

- max rewritten variants: 3
- max decomposition subqueries: 3
- max anchor units for expansion: 3
- max structural adds per anchor: 5
- max typed adds per anchor: 3
- max total candidate pool before rerank: 40
- max controller hops: 2
- max LLM calls in retrieval path: 2
- no repeated operator with identical normalized input

These limits keep the controller bounded, auditable, and cheap enough to evaluate repeatedly.

---

## 12. LLM Reranking Design

LLM reranking should be treated as a ranking-depth experiment, not as a hidden retrieval replacement.

### 12.1 Reranker inputs

The reranker receives:

- normalized original query
- optional structured subquery list or approved query variants
- candidate pool of EvidenceUnits
- candidate metadata including:
  - source list
  - baseline rank
  - benchmark surface
  - family or projection source if present
  - structural path
  - unit type
  - provenance fields needed for audit
Star Finder 2e and 
### 12.2 Reranker scoring dimensions

The reranker should score candidates on:

- direct relevance to query intent
- likelihood of being required evidence rather than merely related
- complementarity with already selected evidence
- specificity versus generic context
- risk of being a distractor

Listwise mode can produce an ordered list plus rationale tags.
Pairwise mode can compare candidate pairs and produce stable preferences.

### 12.3 Reranker constraints

- pinned model ID
- temperature 0
- fixed prompt template ID and prompt hash
- strict output schema
- caching required
- deterministic tie-break by candidate ID or baseline rank

### 12.4 Reranker promotion rule

A reranker earns promotion only if it improves rank-sensitive or full-set metrics on targeted failure slices without causing material T1 regression and without degrading answer-level fidelity on the selected surface.

---

## 13. Retrieval-Lab-Native Answer Evaluation

This is the main integration refinement in the synthesized design.

### 13.1 Scope

Answer evaluation should assess answers generated from retrieved context, not raw model world knowledge.

### 13.2 Framing

Answer evaluation should be treated as a Retrieval-Lab-native optional stage that runs inside the same experiment flow and emits answer-level outputs keyed to the same benchmark projection and evaluation surface.

This gives:

- shared corpus contract identity
- shared benchmark projection identity
- shared run manifest and promotion semantics
- easier comparison between retrieval changes and answer changes
- cleaner integration with optional auto-gold review

### 13.3 Inputs

- query
- benchmark surface
- benchmark projection artifact
- expected answer summary
- required gold units if defined
- retrieved context
- generated answer
- citations or linked EvidenceUnits

### 13.4 Metrics

Recommended initial metrics:

- `answer_supported`
- `required_evidence_coverage`
- `enumeration_completeness`
- `unsupported_claim_count`
- `citation_fidelity`
- `answer_shape_match`
- optional refusal / abstention metrics

### 13.5 Output shape

Keep answer evaluation logically separate from retrieval evaluation, but emit it inside the same run tree and key it by surface, for example:

- `answer_eval.clean_subset.json`
- `answer_eval.full_working_set.json`
- `answer_eval.pre_review_manual.json`
- `answer_eval.post_review_applied.json`

The recommendation-grade answer-eval readout should default to the selected promotion surface.

---

## 14. Trace Schema

Every controller run should emit a machine-readable trace that explains exactly how the pool was built, how candidates moved, which operators added value, and which benchmark surface and contracts were active.

### 14.1 Why this trace is worth keeping

It lets you answer the questions that matter:

- Did multihop help because it found missing evidence, or just reshuffled ranks?
- Which operator first surfaced gold?
- Did reranking rescue already-present gold?
- Which expansions are mostly noise?
- Which controller policies are causing T1 regressions?
- Which surface was being scored when the gain or regression appeared?
- Did answer evaluation run on the same projection and surface?

### 14.2 Proposed schema

```json
{
  "trace_version": "0.2.0",
  "run_id": "string",
  "query_id": "string",
  "corpus_id": "string",
  "corpus_fingerprint": "string",
  "corpus_content_fingerprint": "string",
  "corpus_index_sha256": "string",
  "corpus_recipe": "string",

  "benchmark": {
    "definition_id": "string",
    "projection_path": "benchmark.clean_subset.json",
    "projection_contract_path": "benchmark.clean_subset.contract.json",
    "surface": "clean_subset",
    "surface_type": "standard|review",
    "selected_surface": true
  },

  "retrieval_lab": {
    "experiment_config_id": "string",
    "retrieval_mode": "dense|bm25|hybrid",
    "fusion_mode": "cc|rrf|stable_union|other",
    "answer_eval_enabled": true,
    "auto_gold_review_enabled": false
  },

  "query": {
    "raw": "string",
    "normalized": "string",
    "tier_hint": "T1|T2|T3|null",
    "expected_answer_type": "enumeration|procedure|definition|comparison|mixed|null"
  },

  "budgets": {
    "max_hops": 2,
    "max_variants": 3,
    "max_subqueries": 3,
    "max_candidates_pre_rerank": 40,
    "max_structural_adds_per_anchor": 5,
    "max_typed_adds_per_anchor": 3,
    "max_llm_calls": 2
  },

  "steps": [
    {
      "step_index": 0,
      "operator": "retrieve_original",
      "operator_version": "1.0.0",
      "inputs": {
        "query": "string"
      },
      "outputs": {
        "candidate_ids": ["u1", "u2", "u3"],
        "scores": [0.91, 0.88, 0.84]
      },
      "summary": {
        "candidates_added": 10,
        "duplicates_skipped": 0
      }
    }
  ],

  "candidate_journal": [
    {
      "unit_id": "u1",
      "first_seen_step": 0,
      "sources": [
        {
          "type": "baseline_retrieval",
          "detail": "hybrid_cc"
        }
      ],
      "baseline_rank": 1,
      "pre_rerank_rank": 1,
      "final_rank": 2,
      "score_fields": {
        "baseline_score": 0.91,
        "fusion_score": 1.72,
        "rerank_score": 0.83
      },
      "expansion_reason": null
    }
  ],

  "gold_diagnostics": {
    "gold_defined": true,
    "gold_unit_ids": ["g1", "g2"],
    "gold_in_candidate_pool": true,
    "gold_first_seen_step_by_unit": {
      "g1": 0,
      "g2": 1
    },
    "gold_final_ranks": {
      "g1": 2,
      "g2": 4
    }
  },

  "answer_eval": {
    "enabled": true,
    "surface": "clean_subset",
    "answer_supported": true,
    "required_evidence_coverage": 1.0,
    "unsupported_claim_count": 0,
    "citation_fidelity": 1.0
  },

  "termination": {
    "reason": "sufficient_coverage",
    "step_index": 3
  }
}
```

### 14.3 Required fields

Compared with the earlier draft, the trace should explicitly include:

- corpus contract identity fields
- benchmark projection and projection contract identity
- benchmark surface identity
- selected-surface status
- retrieval mode and fusion mode
- answer-eval enabled and status fields
- auto-gold-review enabled and status fields where relevant

---

## 15. Experiment Matrix

Experiments should be staged rather than mixed all at once, and every serious stage should be surface-aware.

### 15.1 Phase 0: harness alignment

Before judging multihop or rerank gains, verify the experiment harness emits all required artifacts on both standard surfaces.

| ID | Goal | Required outputs |
|---|---|---|
| H0 | contract-valid baseline run | `metrics.full_working_set.json`, `metrics.clean_subset.json`, `prod_readiness.json`, projection contracts |
| H1 | baseline + answer eval | per-surface answer-eval outputs |
| H2 | baseline + trace schema | per-query controller trace on selected surface |

### 15.2 Phase 1: isolate reranking

| ID | Retrieval controller | Expansion | Rerank | Surfaces | Goal |
|---|---|---|---|---|---|
| E0 | current contract-valid baseline | none | none | full + clean | anchor baseline |
| E1 | same | none | heuristic | full + clean | cheap rerank check |
| E2 | same | none | LLM pairwise | full + clean | ranking-depth test |
| E3 | same | none | LLM listwise | full + clean | ranking-depth test |

Primary readout:

- first-gold rank
- full-set or required-set metrics
- T1 regressions
- selected-surface deltas
- answer-eval deltas on selected surface

### 15.3 Phase 2: Stage B-only bounded multihop

| ID | Query rewrite | Structural expansion | Rerank | Surfaces | Goal |
|---|---|---|---|---|---|
| E4 | none | same section | none | full + clean | cheap completion |
| E5 | none | same table/list group | none | full + clean | structural completion |
| E6 | decompose | same section + table/list | none | full + clean | multihop pool gain |
| E7 | decompose | same section + table/list | LLM rerank | full + clean | combined retrieval test |

Primary readout:

- gold-in-candidates ceiling
- full-set metrics
- candidate inflation
- T1 regressions
- answer completeness on selected surface

### 15.3.1 2026-03 PHB 5e signal: decomposition is the next lever

The most relevant live design reference remains this memo, not the PF2E reranking experiment doc, because the PHB 5e signal now points at the controller's `decompose` path rather than at reranking alone.

What we learned from the PHB 2024 multihop review pass is:

- simple LLM reranking is still a ranking-depth lever, not a substitute for missing child retrieval
- several PHB multihop failures are broad parent questions whose answer obligations are easier to retrieve as bounded child questions than as one fused prompt
- the PHB multihop working set is therefore a strong evaluation surface for query decomposition, especially when paired with a micro-bundle surface derived from the same parents

Operational implication:

- treat `evals/retrieval/PHB5e/dnd_5e_2024_multihop_working_set_benchmark.json` as the parent surface
- treat `evals/retrieval/PHB5e/dnd_5e_2024_multihop_microbundle_working_set_benchmark.json` as the child-obligation surface
- use parent-to-microbundle decomposition coverage as the first concrete readout for `rewrite_query(..., decompose)` before investing further in more sophisticated rerank-only variants

In short: the PHB 2024 multihop benchmark is now useful not just as another rerank stress test, but as a decomposition evaluation set.

### 15.4 Phase 3: Stage C-assisted typed closure

| ID | Typed enrichment | Typed expansion | Rerank | Surfaces | Goal |
|---|---|---|---|---|---|
| E8 | feat/option schema only | gated-by-level | none | full + clean | bounded option completion |
| E9 | feat/option schema only | row-to-definition | none | full + clean | table-definition closure |
| E10 | feat/option schema only | gated + row-ref + same family | LLM rerank | full + clean | target milestone |
| E11 | feat/option schema + progression linkage | full typed closure | LLM rerank | full + clean | stress test |

Primary readout:

- bounded enumeration completeness
- full-set metrics
- answer completeness

### 15.5 Phase 4: review-surface interactions

| ID | Auto-gold review | Answer eval | Goal |
|---|---|---|---|
| E12 | off | on | clean measurement without benchmark mutation |
| E13 | on | on pre/post surfaces | inspect interaction between auto-gold review and answer quality |
| E14 | on | on selected surface only | test promotion-safe reporting path |

---

## 16. Evaluation Metrics by Layer

Keep the layers distinct.

### 16.1 Retrieval metrics

Continue the current family:

- MRR
- Hit@k
- Recall@k
- Full-set@k or required-set coverage
- gold-in-candidates ceiling
- failure buckets
- T1 regressions

All of these should be surface-scoped.

### 16.2 Controller metrics

Add:

- operator fire counts
- candidates added per operator
- gold added per operator
- candidate inflation
- duplicate skip rate
- trace depth or hops used
- stop reason distribution

### 16.3 Answer metrics

Add:

- supported answer rate
- required evidence coverage
- unsupported claim rate
- citation fidelity
- bounded-set completeness
- refusal or abstention behavior where useful

### 16.4 Promotion metrics

For recommendation-grade decisions, read from the selected surface via `prod_readiness.json`, not a free-floating summary.

---

## 17. Comparison Policy

This becomes more important under the current Retrieval Lab architecture.

### 17.1 Valid comparisons require

- compatible corpus contracts
- compatible benchmark projection contracts
- explicit benchmark surface alignment
- explicit retrieval-mode and fusion-mode alignment where relevant

### 17.2 Invalid comparisons include

- comparing `full_working_set` from one run to `clean_subset` from another as if they were equivalent
- comparing results across changed substrate-shaping rules without re-projection
- promoting from a run name rather than `prod_readiness.json`
- assuming older RRF-era semantics when the active hybrid default is CC

---

## 18. Promotion Criteria

A feature should only graduate if it clears the right bar for its layer.

### 18.1 Reranking promotion

Promote only if it improves selected-surface rank-sensitive or full-set metrics on targeted slices without material T1 regression and without degrading answer-level fidelity.

### 18.2 Structural multihop promotion

Promote only if it materially improves candidate ceiling or full-set retrieval on multi-evidence queries at acceptable inflation cost and does not increase unsupported claims in answer evaluation.

### 18.3 Typed multihop promotion

Promote only if it improves bounded enumeration and answer completeness on the specific query classes it targets, with stable and schema-valid Stage C outputs.

### 18.4 General controller rule

Do not promote any controller policy that meaningfully degrades citation fidelity, breaks selected-surface recommendation behavior, or makes trace attribution illegible.

---

## 19. Implementation Order

Recommended order:

1. Ensure Retrieval Lab run outputs are fully surface-aware and promotion-safe for these experiments.
2. Add answer-eval outputs per surface inside Retrieval Lab.
3. Add controller trace schema with corpus, projection, and surface identity.
4. Run LLM reranking experiments on fixed candidate pools.
5. Add Stage B-only controller with structural expansion.
6. Run structural multihop ablations on `full_working_set` and `clean_subset`.
7. Add narrow Stage C enrichment for feat / option enumeration and progression closure.
8. Run typed closure experiments.
9. Only then revisit whether this deserves formal Stage D graph packaging.

This keeps the implementation aligned with the current gate logic: Stage C outputs need their own schema and provenance, and any later Stage D graph work should only begin once those outputs are stable, schema-validated, deterministic, and separately evaluable.

---

## 20. Recommended Milestone 1

**Retrieval-Lab-native bounded multihop retrieval v0 with reranking and per-surface answer evaluation, focused on enumeration and progression queries.**

### Definition of done

- controller supports `retrieve_original`, `rewrite_query`, `retrieve_variant`, `fuse_candidates`, `expand_structural`, `rerank`, `stop`
- full per-query trace emitted with corpus contract, benchmark projection, and surface identity
- retrieval metrics emitted for at least `full_working_set` and `clean_subset`
- answer-eval outputs emitted inside Retrieval Lab for at least `clean_subset`
- rerank experiment completed on fixed candidate pools
- Stage B-only structural completion ablations completed
- recommendation-grade readout resolves through `prod_readiness.json`
- a targeted slice of enumeration or progression failures has before/after retrieval traces and answer-eval comparisons

This is small enough to build, strict enough to evaluate, and ambitious enough to generate real signal.

---

## 21. Bottom Line

The strategic direction did not change. What changed is the integration discipline around it.

The canonical design should now be understood as:

- bounded multihop retrieval and reranking are Retrieval Lab retrieval-time features
- answer evaluation is Retrieval-Lab-native and surface-aware
- all serious comparisons are contract-aware and projection-aware
- recommendation-grade decisions are selected-surface decisions, usually `clean_subset`
- hybrid defaults should be discussed in CC-default terms unless a corpus-specific config explicitly overrides them

That is the cleanest unified version of the design because it preserves the original architecture while accurately matching the Retrieval Lab system that now exists.


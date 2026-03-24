# SPEC: Bounded Retrieval Controller v0 Operators

**Status:** Draft v0 specification (design artifact)  
**Scope:** Retrieval-time controller behavior and configuration contract  
**Implementation status:** Partially implemented in runtime code (structural expansion path). Typed rewrite operators and full policy surface remain design-target.

**Current implementation references:**
- `retrieval_lab/controller/engine.py`
- `retrieval_lab/controller/expansion.py`
- `tests/retrieval_lab/test_controller.py`

---

## 1) Purpose

Define a concrete `controller_v0` operator model that replaces always-on freeform decomposition with a deterministic, budgeted policy engine.

Core intent:
- Keep retrieval anchored to the production baseline.
- Use bounded, typed retrieval actions (operators), not open-ended planning.
- Prefer structural closure before lexical creativity.
- Preserve canonical EvidenceUnits and contract-aware evaluation behavior.

---

## 2) Architectural Position

The controller runs inside retrieval-time orchestration and above admissible evidence:

```text
query -> normalize -> retrieve_original
      -> controller decision (bounded operators)
      -> candidate pool assembly
      -> optional rerank
      -> final top-N EvidenceUnits
```

Non-goals:
- Not open-ended agentic search.
- Not Stage D graph runtime reasoning.
- Not changing citation admissibility (EvidenceUnits remain canonical).

---

## 3) Operator Contract (Required Fields)

Every operator definition MUST include:

- `operator_name`
- `version`
- `inputs`
- `preconditions`
- `budget_cost`
- `determinism_mode`
- `outputs`
- `trace_payload_schema`

Optional:
- `admission_rules`
- `blocking_rules`
- `failure_reasons`

---

## 4) Operator Families and Contracts

## 4.1 Anchor Operator

### `retrieve_original`

**Role:** Always-run anchor over the live baseline retrieval policy.

- Inputs:
  - `query_raw`
  - `query_normalized`
  - `retrieval_mode` (dense|bm25|hybrid)
  - `fusion_mode` (cc by default unless overridden)
- Preconditions:
  - Always allowed
  - MUST run first
- Budget cost:
  - `retrieval_calls: 1`
  - `llm_calls: 0`
- Determinism mode:
  - Deterministic under fixed corpus/config/seed
- Outputs:
  - `candidate_ids`
  - `candidate_scores`
  - `baseline_pool_size`
- Trace payload:
  - `retrieval_mode`
  - `fusion_method`
  - `candidate_ids_topk`
  - `candidate_scores_topk`

---

## 4.2 Query-Side Typed Rewrite Operators

All typed rewrite operators are bounded, schema-validated, and cache-backed.

Shared contract for this family:
- Budget cost: `llm_calls: 1`, `retrieval_calls: N_subqueries`
- Determinism mode:
  - Pinned model
  - Temperature 0
  - Strict output schema
  - Cache key includes corpus/profile/prompt/model identity
- Blocking rules:
  - No repeated operator with identical normalized input
  - Block when LLM budget exhausted

### `rewrite_enumeration`

For bounded inventory/list obligations.

- Preconditions:
  - Query classified as enumeration
  - Query tier is T2/T3 (or equivalent hard-case signal)
- Required anchors:
  - 1 inventory anchor (e.g. spells/feats/paths)
  - Up to 2 item anchors
- Caps:
  - `max_subqueries_per_rewrite: 3`
- Admission rules:
  - Each subquery MUST preserve inventory anchor in `must_include_terms`

### `rewrite_comparison`

For two-target comparison obligations.

- Preconditions:
  - Query has >=2 comparison targets
- Required anchors:
  - Both comparison targets preserved across branch set
- Caps:
  - `max_subqueries_per_rewrite: 2`
- Admission rules:
  - Each branch preserves at least one comparison target

### `rewrite_progression`

For level/rank/prerequisite progression obligations.

- Preconditions:
  - Progression pattern detected (class/archetype/subsystem + gate)
- Required anchors:
  - One subsystem anchor + one gating anchor (`level|rank|prerequisite`)
- Caps:
  - `max_subqueries_per_rewrite: 2`

### `rewrite_exception_chain`

For base-rule/exception interaction obligations.

- Preconditions:
  - Exception/base interaction pattern detected
- Required anchors:
  - Both base and exception entities
- Caps:
  - `max_subqueries_per_rewrite: 2`

---

## 4.3 Expansion Operators (Structural Closure)

These are preferred over rewrites for v0 when anchors are strong.

Shared contract:
- Budget cost: `llm_calls: 0`
- Determinism mode: deterministic lookup over corpus metadata/projections
- Admission:
  - Add only non-duplicate candidates
  - Respect per-anchor cap
- Per-anchor cap:
  - `max_structural_adds_per_anchor` (default 5)

### `expand_same_section`

- Preconditions:
  - Anchor has non-empty `structural_path`
- Inputs:
  - `anchor_unit_id`, `structural_path`
- Outputs:
  - Section-neighbor candidate IDs

### `expand_same_table_group`

- Preconditions:
  - Anchor exposes `join_metadata.table_title` (or equivalent table grouping key)
- Inputs:
  - `anchor_unit_id`, `table_title`
- Outputs:
  - Candidate IDs in same table group

### `expand_sibling_heading`

- Preconditions:
  - `structural_path` depth >= 2
- Inputs:
  - `anchor_unit_id`, `parent_structural_path`
- Outputs:
  - Candidate IDs from sibling headings under same parent

### `expand_clause_family`

- Preconditions:
  - Clause-family projection data available for corpus
- Inputs:
  - `anchor_unit_id`, `clause_family_policy`
- Outputs:
  - Candidate IDs from same clause family projection

---

## 4.4 Selection Operators (Rerank)

### `rerank_heuristic`

- Preconditions:
  - Candidate pool size above configured threshold
- Budget cost:
  - `llm_calls: 0`
- Determinism:
  - Deterministic

### `rerank_llm`

- Preconditions:
  - Candidate pool size above configured threshold
  - LLM budget available
  - Pool instability/weakness signal present
- Budget cost:
  - `llm_calls: 1+`
- Determinism:
  - Pinned model
  - Temperature 0
  - Strict schema
  - Cached

### `stop`

- Allowed always
- Reasons:
  - `budget_exhausted`
  - `no_new_candidates`
  - `sufficient_coverage`
  - `policy_stop`

---

## 5) Controller Policy v0

## 5.1 Sequence

```text
Step 0: retrieve_original
Step 1: inspect initial failure signals
Step 2: choose ONE bounded move:
        - expand_same_section
        - expand_same_table_group
        - rewrite_comparison
        - rewrite_enumeration
        - none
Step 3: optional rerank_heuristic
Step 4: optional rerank_llm
Step 5: stop
```

Constraints:
- No recursion
- No loops beyond one bounded move and optional rerank stages
- At most one query-side rewrite OR one expansion operator in v0

## 5.2 Operator Priority

Default preference:
1. Structural expansion operators
2. Typed rewrite operators
3. Rerank operators (when pool already inflated or rank-depth failure detected)

Rationale: structural closure is substrate-aligned and lower drift-risk than lexical generation.

---

## 6) Budget Defaults

```yaml
budgets:
  max_controller_hops: 2
  max_rewrite_variants: 3
  max_subqueries_per_rewrite: 3
  max_expansion_anchors: 3
  max_structural_adds_per_anchor: 5
  max_typed_adds_per_anchor: 3
  max_candidates_pre_rerank: 40
  max_llm_calls_retrieval_path: 2
  no_repeated_operator_same_input: true
```

---

## 7) Failure-Signal Layer (Decision Inputs)

The controller decision should use cheap deterministic signals from the baseline pool:

- `top_results_taxonomy_fraction`
  - Example: >0.5 of top-5 are taxonomy/overview-style units
- `no_entity_anchor_in_top_n`
  - Example: no query entity anchor found in top-5 texts
- `low_structural_diversity_top_n`
  - Example: low heading diversity in top-10
- `pool_size_pressure`
  - Pool near cap with weak required-coverage proxy

Signal outcomes:
- Strong anchor + low diversity -> prefer `expand_same_section` or `expand_same_table_group`
- Two-target comparison pattern -> allow `rewrite_comparison`
- Enumeration pattern + weak inventory coverage -> allow `rewrite_enumeration`
- Gold-present-but-low-rank -> prefer rerank path

---

## 8) Per-Operator Metrics

Each step records:
- `candidates_added`
- `candidates_skipped_duplicate`
- `gold_added` (post-hoc, benchmark keyed)
- `gold_rank_change`
- `required_coverage_delta`
- `admission_filter_rejects`
- `budget_consumed` (`retrieval_calls`, `llm_calls`)

Run-level aggregates per operator:
- `fire_count`
- `mean_candidates_added`
- `mean_gold_added`
- `mean_gold_added_when_fired`
- `candidate_inflation_ratio`
- `t1_regression_count`

---

## 9) Trace Schema Extension

Per-query trace MUST include:
- active corpus contract identity fields
- benchmark projection + contract identities
- scored surface identity
- selected-surface flag
- retrieval mode/fusion mode
- operator step list with preconditions, budget deltas, outputs, metrics
- termination reason

Example step payload:

```json
{
  "step_index": 1,
  "operator": "expand_same_section",
  "operator_version": "1.0.0",
  "preconditions_met": true,
  "budget_before": {"llm_calls_remaining": 2, "hops_remaining": 1},
  "inputs": {"anchor_ids": ["u1", "u3"]},
  "outputs": {"candidate_ids_added": ["u7", "u8", "u9"]},
  "metrics": {
    "candidates_added": 3,
    "candidates_skipped_duplicate": 2,
    "gold_added": 1,
    "budget_consumed": {"retrieval_calls": 0, "llm_calls": 0}
  }
}
```

---

## 10) Config Integration Target

`controller` is a new top-level experiment config section (parallel to `query_enhancement`).

Expected dataclass targets:
- `ControllerBudgets`
- `ControllerV0Config`

If `controller.enabled: true`:
- Controller path is active
- Existing `query_enhancement` path is bypassed for that run

If `controller.enabled: false`:
- Existing behavior remains unchanged (`query_enhancement` and current orchestration path)

---

## 11) Stage C Typed Expansion Gate

Typed expansion operators remain OFF by default in v0:
- `expand_gated_by_level`
- `expand_row_to_definition`
- `expand_same_option_family`
- `expand_progression_link`
- `expand_base_exception`

Enable only when:
- Stage C enrichment schema is validated
- Provenance/version compatibility with corpus contract is enforced
- Retrieval-only non-authoritative semantics are preserved

---

## 12) Deliverables Linked to this Spec

This spec is paired with:
- `retrieval_lab/experiments/controller_v0_template.yaml` (config template)
- `retrieval_lab/experiments/controller_trace_example.json` (reference shape for emitted `controller_trace.json`)

Together they define the design contract for remaining implementation work and trace-shape validation.

---

## 13) How to Test

### Unit tests (controller + config + expansion)

From the repository root (RulesIngestion):

```bash
uv run pytest tests/retrieval_lab/test_controller.py -v
```

Covers:
- Config parsing: `controller` / `controller_v0` keys, budgets, operators, default disabled.
- **expand_same_section**: same `structural_path` grouping, budget and dedup, empty path skip.
- **expand_same_table_group**: same `table_title` (and `join_metadata.table_title`) grouping.
- **run_controller_v0**: baseline preserved when no expansion; same-section expansion and pool cap; fallback to same_table_group when section adds nothing; trace shape (retrieve_original, expand step, stop).

### End-to-end (full experiment with controller enabled)

1. **Use the template**  
   Copy and edit `retrieval_lab/experiments/controller_v0_template.yaml`: set real `substrate_path`, `document_id`, and `query_batches` (e.g. an existing benchmark JSON).

2. **Run the experiment**  
   From RulesIngestion:

   ```bash
   uv run python -m retrieval_lab.run_experiment retrieval_lab/experiments/controller_v0_template.yaml
   ```

3. **Check outputs**  
   - Controller runs instead of QE (no QE profile loaded when `controller.enabled: true`).  
   - Run directory (e.g. `out/retrieval_lab/experiments/<experiment_id>/`) should contain:
     - `controller_trace.json` — per-model, per-query steps (retrieve_original, expand_same_section or expand_same_table_group, stop). Reference shape: `retrieval_lab/experiments/controller_trace_example.json`.  
   - Log line: `Controller v0 applied: N queries, trace_enabled=True`.

To test with a minimal substrate/benchmark, use an existing retrieval_lab run’s substrate path and a small benchmark from `evals/` (or create a tiny benchmark JSON and point `query_batches` at it).

### Building controller_trace per corpus

One experiment run uses **one corpus** (one `substrate_path` + `document_id`). To get a **controller_trace for each corpus**:

1. **One run per corpus**  
   Run the experiment once per corpus. Each run writes its own `controller_trace.json` in that run's output directory (`output_dir / experiment_id / controller_trace.json`).

2. **Corpus identity in the trace**  
   Each `controller_trace.json` is self-describing. It includes a top-level `corpus` object with:
   - `document_id`, `substrate_path`, `substrate_version`
   - `run_id`, `experiment_id`, `experiment_name`  
   So you can tell which corpus a trace belongs to when comparing or merging multiple trace files.

3. **Batch pattern**  
   For many corpora, run one experiment per corpus (e.g. loop over configs or a list of substrate paths). Each config should set its own `substrate_path`, `document_id`, and optionally `experiment_name`; use the same `controller` section. Example:

   ```bash
   for config in retrieval_lab/experiments/controller_phb.yaml retrieval_lab/experiments/controller_dmg.yaml; do
     uv run python -m retrieval_lab.run_experiment "$config"
   done
   ```

   Each run produces an output directory containing `controller_trace.json` for that corpus.

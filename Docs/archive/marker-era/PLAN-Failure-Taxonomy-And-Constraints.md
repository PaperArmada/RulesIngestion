> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# Plan: Failure Taxonomy and Constraint-Based Improvement

**Status:** In progress (Phases 1–3 complete; Phase 3.5 next—contract placement validation; then Phase 4)  
**Last updated:** 2026-02-02  
**Goal:** Systematically decompose graph-retrieval failures into identifiable root-cause classes and improve via deterministic constraints—without guessing and without conflating layers.

---

## Quick reference

| Phase   | Purpose                       | Exit criterion                                                           |
| ------- | ----------------------------- | ------------------------------------------------------------------------ |
| **1**   | Failure taxonomy              | Every gold miss has exactly one label A–E; distribution report exists    |
| **2**   | Counterfactual validation     | Each failure class has 1–2 counterfactuals; dominant class identified    |
| **3**   | Contract insertion            | One deterministic constraint implemented for dominant class              |
| **3.5** | Contract placement validation | Constraint applied at correct layer; placement bug ruled out             |
| **4**   | Regression harness            | Target recall ↑; no regression; gold component entry rate non-decreasing |

**Rule:** Every experiment is layer-isolating. If an experiment changes more than one layer, the result is uninterpretable.

**Invariants (do not change):** Layer isolation rule; A–E taxonomy (mutually exclusive, collectively exhaustive, operationally testable); counterfactual scoping (one layer, binary diagnostic, no smuggled heuristics). The distinction between C (dominance) and D (authority inversion) is deliberate and correct.

---

## 1. Framework (reference)

### 1.1 Five layers (do not mix in one experiment)

| Layer                     | Scope                                  | Owned by                                       |
| ------------------------- | -------------------------------------- | ---------------------------------------------- |
| **Corpus projection**     | Ingestion → facts, entities, structure | `enrichment/`, graph builder                   |
| **Seed formation**        | Query → initial nodes                  | `traversal/seeds.py`, `traversal/intent.py`    |
| **Graph topology**        | Edges, degree distribution, components | `*.graph.json`, `traversal/index.py`           |
| **Traversal dynamics**    | Frontier growth, dominance, cutoffs    | `traversal/traverse.py`, `traversal/policy.py` |
| **Grounding & selection** | Authority, scoring, explanation        | `traversal/retriever.py`, reranker, scoring    |

Root causes live in exactly one layer. Symptoms may propagate; causes do not.

### 1.2 Failure classes (exactly one label per miss)

| Class | Name                 | Where reachability breaks                                                | Observable signals                                                                         |
| ----- | -------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| **A** | Seed failure         | Graph never entered correctly; gold in component traversal never touches | Gold ∉ candidates; gold ∉ reachable at ∞ depth; UNSEEDED dominates audit                   |
| **B** | Connectivity failure | No valid path exists                                                     | Gold reachable under oracle seeding only; gold in isolated subgraph                        |
| **C** | Dominance failure    | Gold reachable but drowned out                                           | Gold in reachable set but not top-k; frontier explodes; high degree, low entropy reduction |
| **D** | Authority inversion  | Wrong node wins                                                          | Conflicting chunks both present; examples/variants cited instead of canonical              |
| **E** | Epistemic mismatch   | Task asks different kind of question                                     | Conceptual batch ≈ 0%; mechanically correct but wrong abstraction                          |

**Engineering analogs:** A = input misrouting; B = missing interface; C = unbounded fan-out / priority inversion; D = missing precedence rules; E = wrong abstraction boundary.

**A internal split (log subtype; report as A externally):** A1 = retrieval miss (gold never enters candidate set). A2 = anchor dilution (gold enters candidates but is dropped at anchor cap/reorder). A1 wants better candidate recall; A2 wants anchor-selection discipline, not more recall. Phase 3 regression (hits 10→9) is A2: a low-authority but correct anchor was dropped when authority was applied at seeding.

### 1.3 Diagnostic counterfactuals (one per class)

| Class | Counterfactual                | What it changes                                | If recall jumps →                              |
| ----- | ----------------------------- | ---------------------------------------------- | ---------------------------------------------- |
| A     | Oracle seeding                | Inject gold into seeds                         | Seed failure confirmed                         |
| B     | Infinite traversal            | No depth/node budget                           | Connectivity issue (rare per current analysis) |
| C     | Authority-only ranking        | Rank by authority, ignore BFS depth            | Dominance confirmed                            |
| D     | Canonical-authority selection | Force highest-authority chunk among candidates | Authority inversion confirmed                  |
| E     | Pedagogical-scope filter      | Restrict to glossary/intro/summary chunks      | Epistemic mismatch confirmed                   |

### 1.4 Graph metrics that matter

- **Gold component entry rate:** % queries where ≥1 gold node enters frontier. **Invariant:** must not decrease when adding constraints.
- **Frontier entropy:** Prefer **entropy delta** (entropy at depth 1 vs at termination, rate of collapse), not absolute entropy. Low entropy can mean hub collapse (C) or clean convergence (good); delta distinguishes them. Dominance (C) = high entropy early → sudden collapse to hub. Authority success = modest entropy → gradual narrowing.
- **Authority inversion rate:** When multiple candidates exist, how often does lowest-authority win?
- **Gold rank conditional on reachability:** Where does gold rank when it is reachable? (separates reachability from selection)

### 1.5 Authority: gate, not filter

**Never use authority to decide _whether_ a node is reachable. Use authority to decide _which_ reachable node is allowed to speak.**

- **Seeding:** maximize _coverage of plausible components_ (recall-oriented).
- **Selection:** minimize _which component wins_ (authority as tiebreaker or dominance dampener).

Authority is a **selection constraint**, not a **reachability constraint**. Applying authority at seed formation narrows the entry cut too early (premature constraint application). Phase 3 regression: authority-for-seeding dropped a valid low-authority anchor before the system had context to know which precedence applied.

**Pedagogical / CDS signals:** Treat as a **partial order**, not numeric scores—deterministic and auditable. E.g. `definition > procedure > option > example > narrative`.

---

## 2. Phase 1 — Failure taxonomy

**Objective:** Label each gold miss with exactly one of A–E using observable signals. Produce a repeatable distribution report.

### 2.1 Schema and data

- [x] **Task 1.1** — Extend batch query schema with optional fields:
  - `failure_class`: `"A" | "B" | "C" | "D" | "E" | null` (null = hit)
  - `failure_signals`: object (populated by harness; see Task 1.3)
  - Document in `blind_eval/README.md` under "Batch file format" that these fields are optional and harness-populated.
- [x] **Task 1.2** — Define signal schema in code (dataclass or typed dict):
  - `gold_in_reachable_set: bool | None`
  - `gold_reachable_at_infinite_depth: bool | None`
  - `gold_rank_if_reachable: int | None`
  - `seed_component_contains_gold: bool | None`
  - `frontier_entropy_at_termination: float | None`
  - `authority_inversion_detected: bool | None`
  - `batch_reasoning_mode: str | None` (e.g. `conceptual` from batch metadata)

### 2.2 Signal extraction

- [x] **Task 1.3** — Implement `blind_eval/taxonomy.py`:
  - `compute_signals(query, gold_ids, index, config, **traversal_options) -> FailureSignals`:
    - Run traversal (normal and optionally infinite-depth).
    - Compute: gold in candidate set, gold rank when present, whether gold is in same component as any seed (need component computation or oracle-seed check), frontier entropy from `traverse_with_diagnostics`, and a simple authority-inversion heuristic (e.g. multiple candidates from same section, lower-authority chunk ranked higher).
  - Use existing `traverse_with_diagnostics`, `traverse_with_ranks`, and retriever; add any missing helpers (e.g. reachable set at infinite depth, component membership).
- [x] **Task 1.4** — Implement label assignment in `taxonomy.py`:
  - `assign_failure_class(signals: FailureSignals, batch_metadata: dict) -> str | None`:
    - Deterministic rules: A (gold not reachable, seed component doesn’t contain gold); B (gold not reachable, seed component contains gold); C (gold reachable, rank > top_k, low entropy); D (gold reachable, authority_inversion_detected); E (conceptual batch, not A/B/C/D). Return `None` for hit.
  - Document rules in docstring and in this plan (e.g. "Labeling logic" subsection).

### 2.3 Harness and report

- [x] **Task 1.5** — Implement `blind_eval/run_taxonomy.py` (or equivalent CLI):
  - Load all batches from `blind_eval/batches/`.
  - For each query: run retrieval, compute signals, assign class, optionally write back `failure_class` and `failure_signals` to a **copy** of the batch (or to `results/`) so source batches stay clean.
  - Output: per-batch and overall counts for A, B, C, D, E, and hits.
- [x] **Task 1.6** — Add a distribution report (console and/or JSON/Markdown):
  - Table: failure_class, count, percentage.
  - Optional: per-batch breakdown, list of query IDs per class.
- [x] **Task 1.7** — Document how to run taxonomy in `blind_eval/README.md` (e.g. "Run taxonomy: `uv run python blind_eval/run_taxonomy.py ...`").

### Phase 1 exit

- [x] **Task 1.8** — Run taxonomy on all batches; capture distribution in this doc or in `blind_eval/results/` and add one-sentence "Phase 1 result" under § 6 (Progress log).

---

## 3. Phase 2 — Counterfactual validation

**Objective:** For each failure class, run a minimal counterfactual that changes only one layer. Identify which counterfactual improves recall most (dominant failure class).

### 3.1 Counterfactual implementations

- [x] **Task 2.1** — Add `blind_eval/counterfactual_harness.py` with:
  - `run_counterfactual_A(queries, index, config) -> CounterfactualResult`: oracle seeding (inject gold_chunk_ids into seeds); same traversal/selection otherwise.
  - `CounterfactualResult`: at least `class_tested`, `baseline_recall`, `counterfactual_recall`, `delta`, `queries_affected` (IDs that flipped miss→hit).
- [x] **Task 2.2** — Implement `run_counterfactual_B`: infinite traversal (no depth/node budget, or very high limits); same seeds and selection.
- [x] **Task 2.3** — Implement `run_counterfactual_C`: authority-only ranking (e.g. rank by authority score or doc position; ignore BFS depth); same seeds and traversal.
- [x] **Task 2.4** — Implement `run_counterfactual_D`: canonical-authority selection (force-select highest-authority chunk among candidates when multiple exist); requires authority signal per chunk (use existing or stub).
- [x] **Task 2.5** — Implement `run_counterfactual_E`: pedagogical-scope filter (restrict candidates to chunks with glossary/intro/summary role or similar); same seeds and traversal.

### 3.2 Harness and interpretation

- [x] **Task 2.6** — CLI or script to run all counterfactuals (or by class):
  - Input: path to batches, graph/enriched paths (or reuse test fixtures).
  - Output: table of counterfactual_recall and delta per class; list of queries_affected per class.
- [x] **Task 2.7** — Document which counterfactual improved recall most and by how much; set "dominant failure class" for Phase 3 (update § 6 Progress log).

### Phase 2 exit

- [x] **Task 2.8** — Record dominant class and chosen counterfactual in this plan (§ 6). Proceed to Phase 3 only for that class.

---

## 4. Phase 3 — Contract insertion

**Objective:** Implement one deterministic constraint that addresses the dominant failure class. No heuristics; no new learning; one layer only.

### 4.1 Contract by class (implement only the one chosen in Phase 2)

**If A (Seed) dominant — contract for candidate admissibility or selection precedence (not seed formation):**

- [x] **Task 3.A.1** — Define authority contract using existing chunk metadata (`section_path`, `content_kind`). _First implementation_ placed it in seed formation (`traversal/seeds.py`); Phase 3 regression showed **placement error** (authority applied too early; A2 anchor dilution).
- [x] **Task 3.A.2** — _Current:_ reorder anchors by canonical-first in `find_anchor_nodes` when flag on. _Intended:_ authority as **selection** tiebreaker or dominance dampener (Phase 3.5).
- [x] **Task 3.A.3** — Wired into `find_anchor_nodes`; only seed-formation layer changed. **Refinement (Phase 3.5):** move authority to selection layer; restore original seeding; verify placement.

**If C (Dominance) dominant:**

- [ ] **Task 3.C.1** — Add degree-weighted (hub-attenuation) scoring: e.g. `attenuated_score(chunk_id, index) = 1.0 / log(degree + 2)`.
- [ ] **Task 3.C.2** — Integrate into selection/ranking path so high-degree nodes are down-weighted; traversal logic unchanged.

**If D (Authority) dominant:**

- [ ] **Task 3.D.1** — Add or use pedagogical signals (see `Docs/pedagogical_signal_contract.md`): e.g. `is_definition`, `is_example`, `is_exception`, `source_section_type`.
- [ ] **Task 3.D.2** — In selection: when multiple candidates exist, prefer higher-authority chunk (definition > procedure > example > variant); wire into retriever/reranker.

**If E (Epistemic) dominant:**

- [ ] **Task 3.E.1** — Define intent–chunk-type contract: e.g. `INTENT_TO_CHUNK_TYPES` (conceptual → glossary/intro/summary; mechanical → rule/procedure/table).
- [ ] **Task 3.E.2** — Apply filter in retrieval: restrict candidates to chunk types allowed for the classified intent; only selection layer changed.

### 4.2 Integration and flags

- [x] **Task 3.9** — Contract toggleable via `TraversalConfig.use_authority_for_seeding` (default `False`) and env `RULES_USE_AUTHORITY_FOR_SEEDING=1` (overrides in `build_config`).
- [x] **Task 3.10** — Documented below and in `blind_eval/README.md` (§ Contract for seed formation).

### Phase 3 exit

- [x] **Task 3.11** — One contract implemented and wired; regression harness (Phase 4) can run with contract on/off.

---

## 4.5 Phase 3.5 — Contract placement validation (do not skip)

**Goal:** Verify the constraint is applied at the correct layer before declaring Phase 4 success.

**Procedure:**

1. Move authority from seed formation → **authority-for-selection** (tiebreaker or dominance dampener during ranking).
2. Restore original seeding behavior (no authority reorder/cap in `find_anchor_nodes`).
3. Add authority as a hard tiebreaker or dominance dampener in the selection/ranking path only.

**Expected outcomes:**

| If…              | Then…                                                 |
| ---------------- | ----------------------------------------------------- |
| Recall improves  | Contract was correct; placement was wrong (fix: done) |
| Recall unchanged | Authority signal too weak or misclassified            |
| Recall worsens   | Authority model incorrect for this corpus             |

This is a cleaner test than tuning the seeding heuristic. Prevents thrashing between “fix seeding” and “fix selection.”

**Tasks:**

- [ ] **Task 3.5.1** — Implement authority-for-selection (same partial order: definition > procedure > option > example > narrative) in selection/ranking path only; no change to `find_anchor_nodes`.
- [ ] **Task 3.5.2** — Run taxonomy + counterfactuals with contract OFF (baseline seeding) and authority-on-selection ON; record recall and gold component entry rate.
- [ ] **Task 3.5.3** — If recall improves, deprecate or remove authority-for-seeding from `find_anchor_nodes`; document placement correction in § 6.

---

## 5. Phase 4 — Regression harness

**Objective:** Ensure the new contract improves the target failure class without regressing others and without increasing refusal entropy.

### 5.1 Harness implementation

- [ ] **Task 4.1** — Add `blind_eval/regression_harness.py` (or extend existing runner):
  - Load all batches; run retrieval with contract OFF, then ON.
  - Compute per-class recall (A–E and hit) for each run.
  - Compute refusal-entropy (or equivalent stability metric) if applicable.
- [ ] **Task 4.2** — Define regression invariants (e.g. in code or config):
  - Target class recall must improve by ≥ 5%.
  - No other class regresses by > 2%.
  - **Gold component entry rate must not decrease** (protects against A2 / entry-cut narrowing).
  - Refusal entropy does not increase by > 0.1 (or define metric).
  - Optional: average candidate set size does not grow by > 20%.
- [ ] **Task 4.3** — Output: `RegressionReport` (target_class, recall_before/after, other_class_deltas, refusal_entropy_delta) and pass/fail vs invariants.
- [ ] **Task 4.4** — Document how to run regression in `blind_eval/README.md`.

### 5.2 CI / manual gate

- [ ] **Task 4.5** — Add a test or script that runs the regression harness and fails if invariants are violated (or document as manual gate).
- [ ] **Task 4.6** — After first passing run, record baseline numbers in § 6 (Progress log).

### Phase 4 exit

- [ ] **Task 4.7** — Regression run passes; baseline and "with contract" numbers recorded in this plan.

---

## 6. Progress log

Use this section to update status as you build and experiment. Keep entries short and dated.

### Phase 1

- **2026-02-02:** Phase 1 complete. Taxonomy run on 50 queries (6 batches): hit 18%, A 20%, B 0%, C 60%, D 0%, E 2%. C (dominance) is the dominant failure class; A (seed) second. Results in `blind_eval/results/taxonomy_results.json`. Next: Phase 2 counterfactual validation to confirm dominant class before contract insertion.

### Phase 2

- **2026-02-02:** Phase 2 complete. Counterfactual run: A +20% (10 queries miss→hit), B +0%, C/D −66%, E −80%. **Dominant failure class: A (seed failure).** Chosen counterfactual: oracle seeding (A). Results in `blind_eval/results/counterfactual_results.json`. Proceed to Phase 3 (contract for seed formation).

### Phase 3

- **2026-02-02:** Contract implemented for A (seed). **Location:** `traversal/seeds.py` (`_authority_score_for_seeding`, reorder step in `find_anchor_nodes`). **Flag:** `TraversalConfig.use_authority_for_seeding` or `RULES_USE_AUTHORITY_FOR_SEEDING=1`. See §7 and blind_eval/README.md.
- **Harness run (contract off vs on):** Taxonomy with contract OFF: 10 hits (20%), A 9, C 30, E 1. With contract ON: 9 hits (18%), A 14, C 25, E 2. **Contract as implemented regresses hit rate** (−1 hit). **Root cause:** authority applied at **seed formation** → narrowed entry cut too early (A2 anchor dilution); a low-authority but correct anchor was dropped. **Assessment:** placement error, not conceptual—reachability, dominance, and authority are correctly separated; constraint was applied in the wrong layer. Phase 3.5: move authority to selection; restore seeding.

### Phase 3.5

- Not yet run. Next: implement authority-for-selection (selection layer only); run with baseline seeding; compare recall and gold component entry rate.

### Phase 4

- Baseline recall (taxonomy, contract OFF): 10 hits (20%) of 50 queries.
- With contract ON (authority-for-seeding): 9 hits (18%).
- Regression: **fail** (target recall did not improve; regressed by 1 hit). Phase 4 harness not yet implemented; numbers from taxonomy runs. New invariant for Phase 4: gold component entry rate must not decrease.

### Experiments and notes

- **2026-02-02:** Taxonomy + counterfactual harness run. Counterfactual A still +20% (10 queries miss→hit). Phase 3 contract ON reduces hits 10→9; root cause = authority placement at seeding (A2). Plan updated with Phase 3.5 (placement validation), A1/A2 split, entropy-delta refinement, authority-as-gate, and gold-component-entry-rate invariant.

---

## 6b. Contract for seed formation (Phase 3, A dominant) — placement under review

**Where:** `traversal/seeds.py` — `_authority_score_for_seeding(chunk_id, index)` and the reorder step at the end of `find_anchor_nodes`.

**What:** When enabled, anchors are reordered by authority (definition/glossary/core sections and `content_kind` rule/condition/spell/feat score higher), then capped at `max_anchors`. **Phase 3 regression:** this placement narrows the entry cut too early (A2); authority belongs in **selection**, not seeding. Phase 3.5 validates moving authority to selection and restoring original seeding.

**Enable:** Config: `TraversalConfig.use_authority_for_seeding = True`. Env: `RULES_USE_AUTHORITY_FOR_SEEDING=1`.

**Disable:** Default is off; omit env or set to 0. **Preferred:** use authority-for-selection (Phase 3.5) instead of authority-for-seeding.

---

## 7. File and command reference

| Item                       | Location / Command                                                                                                                  |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Batch directory            | `blind_eval/batches/`                                                                                                               |
| Batch format               | `blind_eval/README.md` § Batch file format                                                                                          |
| Taxonomy schema + labeling | `blind_eval/taxonomy.py`                                                                                                            |
| Taxonomy run               | `uv run python blind_eval/run_taxonomy.py`                                                                                          |
| Counterfactuals            | `blind_eval/counterfactual_harness.py`                                                                                              |
| Counterfactual run         | `uv run python blind_eval/run_counterfactuals.py`                                                                                   |
| Regression                 | `blind_eval/regression_harness.py` (to add)                                                                                         |
| Traversal diagnostics      | `traversal/traverse.py` → `traverse_with_diagnostics`, `traverse_with_ranks`                                                        |
| Retriever                  | `traversal/retriever.py` → `retrieve_candidates`                                                                                    |
| Seeds                      | `traversal/seeds.py` → `find_anchor_nodes`                                                                                          |
| Existing blind eval tests  | `tests/test_blind_eval.py`                                                                                                          |
| Related docs               | `Docs/canonical_document_skeleton.md`, `Docs/pedagogical_signal_contract.md`, `Docs/grounding_pipeline_with_pedagogical_signals.md` |

---

## 8. Labeling logic (deterministic)

Use this table in `assign_failure_class`; refine in code and keep this in sync.

| Condition                                                                               | Class                         |
| --------------------------------------------------------------------------------------- | ----------------------------- |
| Hit (any gold in retrieved set)                                                         | `null`                        |
| Gold not in reachable set AND seed component does not contain gold                      | A                             |
| Gold not in reachable set AND seed component contains gold (oracle seed would reach it) | B                             |
| Gold in reachable set AND gold_rank > top_k AND frontier entropy low (hub collapse)     | C                             |
| Gold in reachable set AND authority_inversion_detected                                  | D                             |
| Batch is conceptual/reasoning_mode and not A/B/C/D                                      | E                             |
| Else (gold reachable but not selected, no authority inversion)                          | C (default for "drowned out") |

---

_End of plan. Update "Last updated" and Progress log when making changes._

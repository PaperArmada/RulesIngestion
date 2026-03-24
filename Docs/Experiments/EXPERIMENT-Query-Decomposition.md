# Experiment: Query Decomposition (Bounded Multihop)

**Purpose:** Define and run a controlled experiment for `rewrite_query(..., decompose)` on the PHB 5e multihop surfaces: measure whether decomposition improves parent-to-microbundle coverage and parent-surface retrieval without material regression.

**Status:** E0/E6/E7 executed on PHB5e multihop; decomposition gates failed on this surface (not promoted).  
**Related:** [bounded_multihop_retrieval_design_memo.md](../Design/bounded_multihop_retrieval_design_memo.md) §10–11, §15.3, §15.3.1; [ARCHITECTURE-RERANKING-TOOLING.md](../Design/ARCHITECTURE-RERANKING-TOOLING.md) (rerank stage used in E7); `retrieval_lab/query_enhancement/`, `retrieval_lab/orchestration/dense_mode.py`.

---

## 1. Hypothesis

**Primary:** Running `rewrite_query(query, decompose)` to produce up to 3 subqueries, then retrieve-per-subquery and fuse candidates (e.g. CC), will improve:

- **Parent-to-microbundle coverage:** fraction of child (micro-bundle) obligations whose gold appears in the fused candidate set when retrieval is driven by the parent’s decomposed subqueries (or by the parent query id for child-scored runs).
- **Parent-surface metrics:** ReqFSH@10, MRR, gold-in-candidates on the parent benchmark, when compared to the same pipeline without decomposition (E0).

**Secondary:** The largest gains will appear on parent queries where gold is already in the candidate pool but rank is poor (incomplete assembly), rather than on full retrieval misses.

**Negative:** Decomposition should not be expected to fix cases where gold never enters the candidate pool; those remain signals for corpus or grounding fixes.

---

## 2. Surfaces

| Surface | Benchmark file | Role |
|--------|-----------------------------------|------|
| **Parent** | `evals/retrieval/PHB5e/dnd_5e_2024_multihop_working_set_benchmark.json` | 30 multihop queries; retrieval evaluated on these when running “as parent”. |
| **Child (micro-bundle)** | `evals/retrieval/PHB5e/dnd_5e_2024_multihop_microbundle_working_set_benchmark.json` | 37 queries; each has `parent_query_id` linking to a parent. Used for parent-to-microbundle coverage and per-child pass rate. |

**Substrate:** `out/DnD_PHB_5.5` (document_id `DnD_PHB_5.5`), same for both benchmarks. Gold is grounded to merged corpus IDs; benchmarks share schema and chunk recipe.

**Parent–child linkage:** Micro-bundle queries include `parent_query_id` (e.g. `phb5e_mh_ws_001`). Coverage is defined over (parent, child) pairs: for a given parent, run retrieval (with or without decompose); then check, for each child of that parent, whether the child’s required gold appears in the fused top-k for that parent run (or in the union of subquery runs for that parent). Exact aggregation (by-parent vs by-child) is specified in §5.

---

## 3. Experiment rungs (E0, E6, E7)

Same retrieval policy (hybrid CC, same embedding model and substrate), same two benchmark files; only query-rewrite and optional rerank vary.

| ID | Query rewrite | Structural expansion | Rerank | Goal |
|----|----------------|----------------------|--------|------|
| **E0** | none | same section + table/list (or config default) | none | Baseline: no decomposition; establishes parent-surface and child-surface metrics. |
| **E6** | decompose | same section + table/list | none | Decomposition only: multihop pool gain; measure parent-to-microbundle coverage and parent-surface deltas vs E0. |
| **E7** | decompose | same section + table/list | LLM rerank | Decomposition + rerank: combined retrieval test; optional after E6 gates are assessed. |

Reranking in E7 uses the same tooling and config as in [ARCHITECTURE-RERANKING-TOOLING.md](../Design/ARCHITECTURE-RERANKING-TOOLING.md): `llm_rerank_enabled`, `llm_rerank_admission_k`, `llm_rerank_text_char_limit`, listwise reorder after the fused candidate pool from decomposition.

**Budget (from memo):** max 3 decomposition subqueries per parent; deterministic, schema-valid, cache-keyed. Harness: `--enhancement-mode none` (E0) vs `--enhancement-mode decompose` (E6/E7); E7 adds `llm_rerank_enabled: true` in config.

---

## 4. Metrics

**Parent surface (full working set / clean subset):**

- MRR, ReqFSH@10, gold-in-candidates, failure buckets (retrieval_miss, rank_miss, etc.), T1 regression vs baseline.

**Child surface (micro-bundle):**

- Same retrieval metrics when scoring each child query’s gold against the **fused candidate list for that child’s parent** (when running parent-by-parent with decompose) or against the single-query run for that child (when running child benchmark directly). Choice of “run parents and aggregate to children” vs “run children and compare to parent runs” is implementation-defined; see §6.

**Parent-to-microbundle coverage:**

- **Definition:** For each parent P with at least one child in the micro-bundle benchmark, run retrieval for P (E0 or E6). For each child C of P, check whether C’s required gold (all required_gold unit IDs) appears in the fused top-k for P.  
- **Metric:** Coverage = (number of child obligations satisfied) / (total child obligations), where “satisfied” = all required gold for that child appear in P’s fused top-k. Alternatively: per-parent coverage = fraction of P’s children satisfied; then mean across parents.  
- **Report:** E0 vs E6 (and E7 if run) on this coverage; also report per-child pass rate on the child benchmark when run standalone if that is computed.

**Controller/attribution (optional):**

- Operator fire counts, candidates added per operator, duplicate skip rate, trace depth (from memo §16.2).

---

## 5. Gates to move forward

Revisit after E0 and E6 (and optionally E7) are run. Mark each criterion satisfied or not and whether decomposition is promoted for this surface.

| Criterion | Status | Evidence / notes |
|-----------|--------|-------------------|
| **Implement** | ✅ Done | Decompose path runs with `query_enhancement.mode=decompose` and profile `phb5e_decompose_v1`; E6/E7 reports show mode, profile hash, and attribution blocks. |
| **Run** | ✅ Done | E0=`phb5e_multihop_e0_baseline_20260317_031847`; E6=`phb5e_multihop_e6_decompose_20260317_032027`; E7=`phb5e_multihop_e7_decompose_rerank_20260317_032400`. |
| **Measure** | ✅ Done | E0→E6 regresses parent+child mixed surface: MRR 0.6195→0.5917, ReqFSH@10 0.6567→0.5821, Gold-in-candidates 1.0000→0.9403, retrieval_miss 0→4. Parent-to-microbundle hit@10 mean also drops: 0.9583→0.9375; E7 is identical to E6. |
| **Decide** | ✅ Done | Do **not** promote decomposition for this PHB5e surface: required coverage regressed and no parent-to-microbundle coverage gain was observed. |

**Verdict:** **not promoted**.  
One-line reason: E6/E7 did not improve parent-to-microbundle coverage and materially regressed parent-surface retrieval metrics versus E0.

---

## 6. Implementation notes

**Harness:**

- Retrieval Lab already supports `--enhancement-mode decompose` and `query_enhancement.mode = "decompose"`. `retrieval_lab/query_enhancement/enhancer.py` implements `_decompose` (heuristic or LLM, max subqueries from profile). Ensure a PHB 5e–compatible experiment config and, if needed, a decomposition profile (or stub that returns e.g. the original query as single “subquery” for E0 parity).
- **E0:** Config with `query_enhancement.enabled: false` or `mode: none`, same substrate and benchmarks. Run once for parent benchmark and once for child benchmark (or run parent only and compute coverage via child gold linkage).
- **E6:** Same config with `query_enhancement.enabled: true`, `mode: decompose`, same structural expansion and no rerank. Run with `--baseline-metrics <E0_run_dir>` so reports show deltas.
- **E7:** Same as E6 with `llm_rerank_enabled: true` and reranker config; optional.

**Parent-to-microbundle coverage:**

- **Option A (parent-centric):** Run retrieval once per parent query (with E0 or E6). For each parent, get fused top-k candidate IDs. For each child of that parent (from micro-bundle benchmark, filter by `parent_query_id`), check whether the child’s `required_gold` (or `_required_gold`) is a subset of that fused set. Aggregate: e.g. (children satisfied) / (total children) or mean over parents of (children of P satisfied) / (children of P).
- **Option B (child-centric):** Run retrieval on the child benchmark directly (each child as its own query). Compare E0 vs E6 by running the **parent** benchmark with E0 vs E6, then for each parent P, take the fused list for P and evaluate each child C of P against that list (child C “passes” if C’s required gold ⊆ fused list for P). Same aggregate as Option A.
- Implement whichever fits the current harness (e.g. one run per benchmark vs one run per parent). Document the choice in the run report.

**Config / CLI:**

- Use existing PHB 5e substrate path and benchmark paths. Example config: duplicate an existing hybrid PHB config, set `query_enhancement.mode` to `none` (E0) or `decompose` (E6), set `llm_rerank_enabled` to false (E0, E6) or true (E7). Pass `--baseline-metrics out/retrieval_lab/experiments/<E0_run_id>` for E6 (and E7) so reports include deltas.

---

## 7. Gate check (to complete after runs)

After E0 and E6 (and optionally E7) are executed:

1. **Implement:** Confirmed (`mode=decompose`, profile `phb5e_decompose_v1`, hash `a8d4106caae61fad` in E6/E7 reports).  
2. **Run IDs:** E0 = `phb5e_multihop_e0_baseline_20260317_031847`, E6 = `phb5e_multihop_e6_decompose_20260317_032027`, E7 = `phb5e_multihop_e7_decompose_rerank_20260317_032400`.
3. **Measure (E0 -> E6, full_working_set):**
   - Parent/child mixed surface: MRR **-0.0278** (0.6195 -> 0.5917), ReqFSH@10 **-0.0746** (0.6567 -> 0.5821), Gold-in-candidates **-0.0597** (1.0000 -> 0.9403), retrieval_miss **+4** (0 -> 4).
   - Parent-only (query id prefix `phb5e_mh_ws_`): MRR **+0.0014** (0.5620 -> 0.5634), hit@10 **-0.0333** (0.9000 -> 0.8667).
   - Microbundle-only (query id prefix `phb5e_mh_mb_`): MRR **-0.0517** (0.6662 -> 0.6145), hit@10 **-0.0270** (0.9459 -> 0.9189).
   - Parent-to-microbundle coverage proxy (mean parent child hit@10): **-0.0208** (0.9583 -> 0.9375).
   - E7 vs E6: no metric recovery; values are effectively unchanged at report precision.
4. **Decide:** Promotion conditions are not met; verdict is **not promoted** for this PHB5e surface.
5. **Artifacts:**
   - `out/retrieval_lab/experiments/phb5e_multihop_e0_baseline_20260317_031847`
   - `out/retrieval_lab/experiments/phb5e_multihop_e6_decompose_20260317_032027`
   - `out/retrieval_lab/experiments/phb5e_multihop_e7_decompose_rerank_20260317_032400`

---

## 8. References

- `Docs/Design/bounded_multihop_retrieval_design_memo.md` — controller operators, budgets, E4–E7 table, §15.3.1 PHB 5e decomposition readout.
- `Docs/Design/ARCHITECTURE-RERANKING-TOOLING.md` — reranker pipeline placement, config, baseline/delta semantics; E7 rerank stage aligns with this architecture.
- `retrieval_lab/query_enhancement/enhancer.py` — `_decompose`, `_llm_decompose`, `_heuristic_decompose`.
- `retrieval_lab/orchestration/dense_mode.py` — query enhancement mode branching, per-query decompose.
- `evals/retrieval/PHB5e/dnd_5e_2024_multihop_working_set_benchmark.json` — parent surface.
- `evals/retrieval/PHB5e/dnd_5e_2024_multihop_microbundle_working_set_benchmark.json` — child surface; `parent_query_id` per query.

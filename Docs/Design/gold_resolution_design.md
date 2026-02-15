# Gold resolution: keeping benchmarks valid across corpus changes

**Problem:** `gold_unit_ids` in benchmarks are **derived** from the corpus pipeline (load → fold → merge). When we change min_chars, fold/merge logic, or substrate, chunk IDs change and existing gold IDs become invalid. Manually re-running a resolve script is easy to forget and doesn’t help when running with a different config.

**Goal:** Benchmarks stay valid across pipeline/config changes without manual re-resolution.

---

## Option A: Resolve at run time (recommended)

**Idea:** Treat **gold_locations** (or equivalent) as the **canonical** definition of “what is gold.” At experiment run time, **after** building the corpus (load → fold → merge), resolve gold_locations → current chunk IDs **in memory** and attach the result to each query. Downstream code (grounding, metrics) only ever sees resolved `gold_unit_ids` for the corpus we’re actually using.

**Benchmark schema (unchanged):**
- Keep `gold_locations`: map from a logical gold key (or the previous chunk id) to `{ page, structural_path, source_unit_ids }`.
- Keep `gold_unit_ids` / `required_gold` / `supporting_gold` as **cache** of the last resolution (optional; can be omitted if we always resolve).

**Pipeline change:**
1. Load benchmark (queries with `gold_locations` and possibly `gold_unit_ids`).
2. Build corpus (load → fold → merge) → get `merged` list and build `original_to_merged` (and optionally `merged_by_id`).
3. **Resolve step:** For each query, if it has `gold_locations`, compute current `gold_unit_ids` / `required_gold` / `supporting_gold` from the **current** corpus (same logic as `resolve_sw_gold_to_corpus.py`). Overwrite or set the query’s gold ids in memory. If a query has no `gold_locations` but has `gold_unit_ids`, leave them as-is (backward compat; they may be stale).
4. Proceed with grounding and retrieval using the resolved queries.

**Pros:** No separate “re-resolve and commit” step. Same benchmark file works for any config. Gold is always correct for the corpus we’re evaluating on.

**Cons:** Resolution logic must run on every experiment (small cost). Benchmark must have `gold_locations` populated for every query that has gold (curation workflow must capture them).

---

## Option B: Canonical gold by original unit IDs only

**Idea:** Store gold as **original (stageB) unit IDs** only. At run time, build corpus and `original_id → chunk_id`; for each query, gold chunks = unique chunk IDs that contain any of the query’s original gold unit IDs.

**Benchmark schema:** e.g. `gold_original_unit_ids: ["id1", "id2"]` per query (and optionally `required_original_ids` / `supporting_original_ids`).

**Pros:** Single stable representation; no chunk IDs in the benchmark.

**Cons:** Curation and tooling must work in original-unit space; “which chunk is gold” is derived every time (same as A). Slightly different schema.

---

## Option C: Resolve on demand and persist

**Idea:** Keep current schema. When running an experiment, if the pipeline detects that current corpus run_id (or config hash) doesn’t match the one the benchmark was last resolved for, run resolution and **write** updated `gold_unit_ids` (and `gold_locations`) back to the benchmark file. Optionally require a `--resolve-gold` flag to avoid surprise writes.

**Pros:** Benchmark file always has up-to-date IDs; no run-time resolution in the hot path after first resolve.

**Cons:** Mutating the benchmark on every config change can be surprising; need clear “resolved for” metadata and possibly branch/CI hygiene.

---

## Recommendation: Option A (resolve at run time)

1. **Add a resolution step** inside `_prepare_experiment_corpus_context` (or immediately after it, before grounding):  
   - Input: `flat_queries` (from benchmark), `canonical_corpus` (merged), and folded corpus (to build `original_to_merged`).  
   - For each query that has `gold_locations`, resolve to current chunk IDs; set `gold_unit_ids`, `required_gold`, `supporting_gold` (and optionally `required_gold_rationale` keyed by new id) on the query dict.  
   - Queries without `gold_locations` keep existing `gold_unit_ids` (legacy behavior).

2. **Curation workflow:** When adding or editing gold (e.g. apply_nominated_gold, or manual edit), always **write gold_locations** from the current corpus (page, structural_path, source_unit_ids) so that future runs can resolve. Scripts like `apply_nominated_gold_sw.py` should call into the same “corpus from config + gold_locations from corpus” logic to populate `gold_locations` when copying gold ids.

3. **Integrity check:** Keep using the same pipeline (load → fold → merge) and resolve before checking; then “missing gold” means “gold_locations don’t match any chunk” (e.g. substrate or extraction changed), not “chunk IDs changed.”

4. **Docs:** In MANUAL_REVIEW.md (or a single “Benchmark gold” doc), state that **gold_locations are the source of truth**; `gold_unit_ids` are derived at run time for the current corpus. New benchmarks should always include `gold_locations` for each gold entry.

5. **Optional:** Keep `scripts/resolve_sw_gold_to_corpus.py` for one-off “write resolved IDs back to the file” (e.g. for debugging or for consumers that read the benchmark without running the full pipeline). The main path doesn’t depend on it.

---

## Implementation checklist (Option A)

- [ ] Extract resolution logic from `resolve_sw_gold_to_corpus.py` into a reusable function (e.g. `retrieval_lab/gold_grounding.py` or `retrieval_lab/gold_resolution.py`) that takes (queries, folded_corpus, merged_corpus) and returns queries with resolved gold ids.
- [ ] In `run_experiment.py`, after building corpus and before `_resolve_gold_grounding`, call the resolver so `flat_queries` (or the list passed to grounding) have current `gold_unit_ids` when they have `gold_locations`.
- [ ] Ensure `flatten_query_batches` (or the loader) preserves `gold_locations` on each query.
- [ ] Update integrity check to use the same resolve step before checking gold ids in corpus.
- [ ] Document in MANUAL_REVIEW.md / benchmark README that gold_locations are canonical and resolution is automatic at run time.

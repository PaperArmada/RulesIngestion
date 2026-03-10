# Gold resolution and benchmark projection lifecycle

**Problem:** `gold_unit_ids` in benchmarks are **derived** from the corpus pipeline (load → fold → merge). When we change `min_chars`, fold/merge logic, substrate contents, or other chunk-shaping rules, old chunk IDs and old corpus identities become invalid for evaluation.

**Goal:** Preserve stable benchmark intent while forcing every scored run to use a benchmark projection that matches one exact corpus contract.

---

## Current architecture

The implemented lifecycle is now:

1. **Benchmark definition**
   - stable, human-maintained benchmark intent
   - durable anchors live in `gold_locations` and related rationale fields
2. **Corpus contract**
   - exact `corpus_index.json`
   - `corpus_fingerprint`
   - `corpus_content_fingerprint`
   - `corpus_index_sha256`
   - `corpus_recipe`
3. **Benchmark projection**
   - generated benchmark artifact for one exact corpus contract
   - stored in run outputs as `benchmark.<surface>.json`
4. **Projection contract**
   - stored as `benchmark.<surface>.contract.json`
   - validated before scoring
5. **Promotion artifact**
   - `prod_readiness.json`
   - authoritative answer to "what should ship?"

## Option A: Resolve at run time (historical recommendation)

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

## Current recommendation

Use runtime resolution plus explicit run-local benchmark projection snapshots.

Practical rules:

1. Keep `gold_locations` as the durable curation surface.
2. Resolve benchmark intent against the exact active corpus before scoring.
3. Snapshot the scored benchmark projection into the run directory.
4. Snapshot the projection contract beside it.
5. Fail closed if the active corpus contract does not match the projection contract.
6. Treat post-review auto-gold as a separate benchmark surface with its own projection contract.

### Current run artifacts

Every recommendation-grade run should preserve:

- `embeddings/corpus_index.json`
- `benchmark_contract_validation.json`
- `benchmark.<surface>.json`
- `benchmark.<surface>.contract.json`
- `manifest.json`
- `prod_readiness.json`

### Current role of `resolve_sw_gold_to_corpus.py`

`scripts/resolve_sw_gold_to_corpus.py` should be treated as the projection materialization tool for one-off explicit projection generation and debugging, not merely as a repair script.

Use it when you need to:

- generate a projection against one exact `corpus_index.json`,
- inspect how anchors resolved,
- produce an explicit projection contract outside a normal evaluation run.

---

## Updated checklist

- [x] Resolve benchmark intent against the active corpus before scoring.
- [x] Preserve `gold_locations` as the durable intent layer.
- [x] Add stronger corpus identity using content-aware fingerprints.
- [x] Validate projection contracts against `corpus_index_sha256`.
- [x] Snapshot benchmark projections into run directories.
- [x] Snapshot projection contracts into run directories.
- [x] Emit `prod_readiness.json` for contract-valid promotion candidates.

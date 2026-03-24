# Comprehensive Report: Query Decomposition System

**Date:** 2026-03-16  
**Scope:** Full architectural review of the query decomposition subsystem within RulesIngestion / Retrieval Lab.  
**Audience:** Agent receiving this as context for follow-on work.

---

## 1. What Decomposition Is

Query decomposition splits a single user question into multiple retrieval sub-queries, retrieves candidates for each, and fuses the results back into a single ranked list. The goal is to improve recall on **multihop** questions whose answer obligations span multiple rulebook passages that a single query embedding cannot jointly surface.

Example: "How do the revised versions of Prayer of Healing, Mass Healing Word, Sleep, and Aid interact with the Healer feat, Disciple of Life, and Lay on Hands?" — a single embedding cannot simultaneously anchor on all those entities. Decomposition would split it into obligation-specific retrieval queries.

---

## 2. Architecture Overview

### 2.1 Module Map

```
retrieval_lab/query_enhancement/
├── profile.py           # QueryExpansionProfile, DecompositionConfig, PoliciesConfig dataclasses
├── decomposition.py     # LLM call, prompt, response parsing, vocabulary guard
├── enhancer.py          # Top-level enhance_queries() dispatcher (modes: none/dict/llm/decompose)
├── multi_query.py       # Fusion functions: fuse_only_add, fuse_multi_query_rankings, fuse_union_rerank, lock_prefix, lexical_rerank_tail_segment
├── cache.py             # File-based deterministic cache (blake3-keyed)
└── profiles/
    ├── phb5e_decompose_profile.json   # PHB 5e corpus profile
    └── pf2e_decompose_profile.json    # PF2E corpus profile

retrieval_lab/orchestration/
├── dense_mode.py        # Primary orchestrator: embeds queries, retrieves, wires QE, fuses, reranks
└── bm25_mode.py         # BM25 orchestrator: parallel QE path

retrieval_lab/config.py  # OnlyAddFusionConfig, QueryEnhancementConfig, ExperimentConfig
```

### 2.2 Data Flow

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ enhancer.py :: enhance_queries(mode="decompose")    │
│   1. Check cache (blake3 key: corpus+profile+query) │
│   2. Call _should_decompose() heuristic             │
│   3. Call decompose_query() via OpenAI Responses API│
│   4. Parse + vocabulary-guard filter                │
│   5. Return [original, variant1, variant2, ...]     │
└─────────────────────────────────────────────────────┘
    │ per query: List[Dict] with keys: q, source, intent, must_include_terms, notes
    ▼
┌─────────────────────────────────────────────────────┐
│ dense_mode.py :: run_dense_mode()                   │
│   1. Embed ALL variant texts                        │
│   2. Dense retrieval per variant (cosine sim)       │
│   3. If hybrid: RRF-fuse dense+BM25 per baseline   │
│   4. Fusion: fuse_only_add or fuse_multi_query      │
│   5. Optional tail rerank                           │
│   6. Downstream: reranker, expand_context, etc.     │
└─────────────────────────────────────────────────────┘
    │ ranked_lists, score_lists, qe_fusion_debug
    ▼
  Evaluation / Metrics
```

---

## 3. Component-by-Component Detail

### 3.1 Profile Configuration (`profile.py`)

The `QueryExpansionProfile` is a corpus-specific, versioned dataclass loaded from JSON. Key sub-configs for decomposition:

**`DecompositionConfig`:**
- `enabled: bool` — master switch
- `when: str` — `"always"`, `"multi_hop_only"`, or `"never"`. Controls the `_should_decompose()` heuristic gate.
- `model_id: str` — explicit LLM model; if empty, falls back to `MODEL_POLICY.json → actions.structured_generation`
- `reasoning_effort: str` — `"none"`, `"low"`, `"medium"`, `"high"`. Passed to Responses API `reasoning` parameter for models that support it (gpt-5 family, o-series).
- `prompt_template_id: str` — used in cache signature; currently always `"retrieval_query_decomposition_v2"`
- `output_schema_version: str` — cache key component
- `max_subqueries: Optional[int]` — legacy field, ignored by Responses-based decomposition

**`PoliciesConfig`:**
- `include_original: bool` — if `True`, the original query text is prepended to the expansion list (position 0). This means the original query is always part of the retrieval and fusion.
- `max_expanded_queries: int` — cap on total expansions (BUT: decompose mode explicitly bypasses this cap in `_dedupe_and_cap`)
- `drift_guard` — lexical overlap guard; disabled in both decompose profiles

**Live profiles** (PHB5e and PF2E) are identical structurally:
- `decomposition.enabled: true`
- `decomposition.when: "always"` (bypasses the heuristic gate entirely)
- `decomposition.model_id: ""` (falls back to MODEL_POLICY)
- `decomposition.reasoning_effort: "low"`
- `policies.include_original: true`
- `policies.max_expanded_queries: 3`
- No synonym sets, no term boosters, no allowed vocab populated
- Drift guard disabled

### 3.2 Decomposition Prompt & LLM Call (`decomposition.py`)

**Prompt template** (`_DECOMPOSITION_PROMPT_TEMPLATE`):
```
You split a tabletop RPG rules question into retrieval queries.

Goal:
- Return the smallest set of retrieval queries needed to retrieve the rule passages required by the question.

Rules:
- Produce retrieval queries only, never answers.
- Use only vocabulary that already appears in the question.
- Do not introduce synonyms, broader categories, external rule terms, section names, or inferred entities.
- Keep each retrieval query short, literal, and close to the question wording.
- Split only when the question contains multiple distinct retrieval obligations.
- If one retrieval query is enough, return exactly one.
- Avoid near-duplicate rewrites.

Allowed vocabulary from the question:
{query_vocab_summary}

Return strict JSON only.
```

The `{query_vocab_summary}` is computed by tokenizing the original query (`[A-Za-z0-9]+` regex) and joining unique lowercased tokens.

**Output schema** (Responses API structured output, `strict: true`):
```json
{
  "retrieval_queries": [
    {
      "query": "string",
      "must_include_terms": ["string"]
    }
  ]
}
```

**Vocabulary guard** (`_uses_only_query_vocabulary`): After the LLM returns sub-queries, each candidate query is tokenized and compared to the original query's token set. Any sub-query introducing tokens not present in the original is **rejected**. This is the primary defense against prompt drift.

**Model resolution**: If `DecompositionConfig.model_id` is empty, the system reads `MODEL_POLICY.json` and uses the model mapped to the `structured_generation` action role. Currently resolves to `gpt-5-mini`.

**API call**: Uses the OpenAI Responses API (`client.responses.create`), not the Chat Completions API. Temperature is set to 0 for non-gpt-5 models. Reasoning effort is passed when the model supports it.

**Caching**: Results are cached to disk as JSON files, keyed by blake3 hash of `(corpus_id, corpus_hash, profile_hash, normalized_query, mode, model_id, prompt_hash)`. This makes decomposition calls idempotent and cheap after first invocation.

### 3.3 Heuristic Trigger Gate (`enhancer.py :: _should_decompose`)

When `decomposition.when = "multi_hop_only"`, the system uses heuristics to decide whether to decompose:

1. **Token count > 15** → decompose
2. **Conjunction patterns** (`and`, `while`, `during`, `when...and`, `but`) → decompose
3. **Multi-facet templates** (regex patterns like `combat.*spell`, `movement.*attack`, etc.) → decompose

When `decomposition.when = "always"` (as in both live profiles), the heuristic is bypassed entirely and every query is decomposed.

### 3.4 Enhancer Dispatcher (`enhancer.py`)

`enhance_queries()` is the top-level entry point. For `mode="decompose"`:

1. Normalize query text via profile normalization rules
2. Check cache; if hit, return cached expansions
3. If `policies.include_original` is True, prepend `{"q": original, "source": "original"}` as position 0
4. Call `_decompose()` → `decompose_query()` → LLM call + parse + vocabulary guard
5. Deduplicate by lowercased query text
6. **No cap applied**: decompose mode passes `max_total=None` to `_dedupe_and_cap`, so all sub-queries are kept regardless of `max_expanded_queries`
7. Cache result
8. Return `List[Dict]` per query, where each dict has keys: `q`, `source`, `intent`, `must_include_terms`, `notes`

### 3.5 Tier-Gated Decomposition (`dense_mode.py`)

The orchestrator supports tier-gated decomposition: only T2/T3 queries are decomposed, T1 queries use mode `"none"`. This is wired through `expand_query_texts_per_query_modes()`.

Each query in the benchmark has a tier field. The orchestrator builds a per-query mode list:
- T1 → `"none"` (no decomposition, original query only)
- T2/T3 → `"decompose"` (full decomposition pipeline)

Additionally, an optional `qe_enhance_query_ids` set can restrict decomposition to specific query IDs.

### 3.6 Only-Add Fusion (`multi_query.py :: fuse_only_add`)

This is the default and only fusion mode used in decomposition experiments. Its contract:

1. **Lock baseline prefix**: Take the top `baseline_keep_n` candidates from the original query's retrieval. These are locked at the front of the final list and cannot be evicted.
2. **Append novel candidates**: Flatten variant retrieval results (variant_0 list, then variant_1, ...). For each candidate not already in the locked prefix, append it. Assign scores below the baseline band (`min_baseline_score - append_score_band - epsilon`).
3. **Admission cutoff**: Stop appending once the total list reaches `admission_cutoff` (default 50).
4. **Regression guard**: Assert that every baseline locked ID is present in the final list.

Key parameters from `OnlyAddFusionConfig`:
- `include_original: bool = True` — When False, `baseline_keep_n` and `prefix_lock_n` are set to 0 by the orchestrator, building the final list from variant retrieval only.
- `baseline_keep_n: int = 20` — How many baseline results to lock
- `prefix_lock_n: int = 20` — How many to hard-lock at the front
- `admission_cutoff: int = 50` — Total pool size
- `variant_k_per_query: int = 20` — How many candidates to retrieve per variant
- `tail_rerank: str = "none"` — Optional tail reranking (lexical, cross_encoder, cascade)
- `append_score_band: float = 1e-6` — Score separation between baseline and appended candidates

**Determinism guarantees**:
- Baseline order is preserved (prefix locked)
- Variant flatten order is stable: variant_0, then variant_1, etc.
- Within each variant list, tie-breaking must be stable upstream (handled by `np.lexsort` with doc_id as secondary key)
- "First seen wins" for deduplication

### 3.7 Other Fusion Modes (Available but Not Used for Decomposition)

- **RRF** (`fuse_multi_query_rankings`): Reciprocal rank fusion across all variant lists. Can demote baseline hits.
- **Union Rerank** (`fuse_union_rerank`): Union all candidates, sort by best score, stable tiebreak by doc_id. Can also demote baseline hits.
- **Lock Prefix** (`lock_prefix`): Post-fusion utility to force locked IDs to the front regardless of score. Used after downstream stages that might reorder.

### 3.8 Pipeline Integration: Reranking Order

Reranking (dense stage-2 rerank, cross-encoder rerank, LLM rerank) runs **after** decomposition and fusion. The `ranked_lists` variable at the reranking stage already contains the fused result. This means:

1. Decompose → fuse (only_add) → produces `ranked_lists`
2. Reranking operates on `ranked_lists`
3. Final evaluation operates on the reranked `ranked_lists`

The `include_original` flag (recently added) allows running decomposition in isolation: when `False`, the baseline retrieval is excluded entirely, so the final list is built only from variant (decomposed) sub-query retrieval.

---

## 4. Experiment Results Summary

### 4.1 Experiments Run

| ID | Corpus | Mode | Rerank | Key Config |
|----|--------|------|--------|------------|
| E0 | PHB5e | none (baseline) | none | Hybrid CC, all-mpnet-base-v2 |
| E6 | PHB5e | decompose | none | Same substrate, only_add fusion |
| E7 | PHB5e | decompose | LLM rerank | E6 + listwise LLM rerank |
| R0 | PF2E | none (baseline) | none | Hybrid CC, same embedding |
| E6 | PF2E | decompose | none | Same substrate, only_add fusion |

### 4.2 PHB5e Results (E0 → E6)

**Overall (67 queries, parent + microbundle mixed surface):**
- MRR: 0.6195 → 0.5917 (**-0.0278**)
- ReqFSH@10: 0.6567 → 0.5821 (**-0.0746**)
- Gold-in-candidates: 1.0000 → 0.9403 (**-0.0597**)
- Retrieval misses: 0 → 4

**Per-query breakdown:**
- Worse: 11 queries, Unchanged: 49, Improved: 7
- `hit → miss` transitions: 4
- `miss → hit` transitions: 0
- Variants added zero new gold on 46/67 queries
- Every query appends 30 extra candidates (admission_cutoff 50 - baseline_keep_n 20)

**E7 (decompose + LLM rerank)**: No metric recovery vs E6.

**Verdict: not promoted.**

### 4.3 PF2E Results (R0 → E6)

**Overall (70 queries):**
- Worse: 4 queries, Unchanged: 63, Improved: 3
- `hit → miss` transitions: 0
- `hit@10` worsened: 1
- Variants added zero new gold on 57/70 queries
- 30 extra candidates appended on 65/70 queries

**Verdict: not promoted, but milder regression than PHB.**

### 4.4 Key Mechanical Finding: Baseline Divergence

The final decompose top-20 exactly matches the run's internal `baseline_topN` (locked prefix) on 100% of queries for both corpora. However, this internal baseline **diverges** from the standalone baseline run:

- PHB: top-20 exact match between standalone baseline and decompose internal baseline: **0/67 queries**
- PF2E: top-20 exact match: **0/70 queries**
- Mean top-10 Jaccard: ~0.80 for both
- Mean top-20 Jaccard: ~0.60 for both

This means the regression has **two layers**:
1. **Baseline divergence**: The decompose execution path produces a different "baseline" retrieval than the standalone run, before any variant appending.
2. **Low-yield variant expansion**: Variants rarely add new gold (21/67 PHB, 13/70 PF2E) but always consume candidate budget.

---

## 5. Identified Failure Modes

### 5.1 Prompt Behaves Like a Research Planner, Not a Retrieval Controller

The decomposition prompt generates:
- External-source obligations (Sage Advice, designer rulings)
- Cross-edition or older-edition references
- Generic taxonomy searches (action economy, spellcasting overview)
- High-level explanatory queries rather than citation-targeted retrieval

This is most damaging on:
- Narrow fact questions that don't need decomposition
- Already-solved exact-match questions (baseline rank 1 → decompose rank 3+)
- Multi-entity synthesis prompts where the model invents too many branches

### 5.2 Vocabulary Guard Is Necessary But Insufficient

The `_uses_only_query_vocabulary()` filter catches out-of-vocabulary tokens, but:
- The model can still generate semantically drifted queries using only in-vocabulary tokens
- Rearranging query tokens into a different intent is not caught
- The guard does not check whether generated sub-queries are redundant or broadening

### 5.3 Always-On Decomposition Damages Easy Queries

Both profiles set `decomposition.when: "always"`, which means even T1 (simple) queries that the baseline already handles perfectly are decomposed. The orchestrator has tier-gating (T2/T3 only), but this depends on the query having a tier field.

### 5.4 Large Fixed Tail is Expensive for Low Yield

Default `only_add` settings: `baseline_keep_n=20`, `admission_cutoff=50`, `variant_k_per_query=20`. This appends 30 candidates on nearly every query, even when variants add zero new gold.

### 5.5 Baseline Parity Issue (Uninvestigated)

The decompose path's internal baseline retrieval result differs from the standalone baseline. Possible causes:
- Query embedding differences when variants are batch-encoded
- Hybrid fusion parameter differences
- Offset accounting bugs when variant embeddings are sliced from the batch
- Normalization path differences when `use_qe=True`

This is flagged as the **highest-priority engineering investigation** before further prompt tuning.

---

## 6. Code Quality & Design Observations

### 6.1 Strengths

- **Deterministic caching**: blake3-keyed file cache makes LLM calls idempotent. Cache key includes corpus, profile hash, model, and prompt hash. Cheap reruns.
- **Strict output schema**: Responses API `strict: true` with JSON schema guarantees parseable output structure.
- **Vocabulary guard**: Post-generation filter that rejects sub-queries with out-of-vocabulary tokens.
- **Stable fusion ordering**: `fuse_only_add` has explicit determinism guarantees (baseline prefix locked, first-seen deduplication, stable variant flatten order).
- **Regression guard**: Assertion that every baseline locked ID appears in the final list.
- **Separation of concerns**: Profile (config) / decomposition (LLM) / enhancer (dispatch) / multi_query (fusion) / orchestration (wiring) are cleanly separated.
- **Tier gating**: Orchestrator supports per-query mode selection based on query tier.

### 6.2 Concerns

- **`max_expanded_queries` bypass**: Decompose mode explicitly passes `max_total=None` to `_dedupe_and_cap`, so the profile's `max_expanded_queries=3` is never enforced. The LLM can return arbitrarily many sub-queries (observed: up to 17 on one PHB query). This is a latent cost and noise amplifier.
- **`include_original` in profile vs `include_original` in `OnlyAddFusionConfig`**: Two different `include_original` flags exist at different levels. `PoliciesConfig.include_original` controls whether the original query text is in the expansion list. `OnlyAddFusionConfig.include_original` controls whether baseline retrieval enters the fused list. These are independent but interact subtly.
- **No sub-query count limit in the prompt**: The prompt says "smallest set" but does not specify a maximum. The structured schema allows an unbounded array. The only defense is the vocabulary guard filtering, which may not reduce quantity.
- **Heuristic gate is unused**: Both production profiles set `when: "always"`, making the conjunction/multi-facet heuristics dead code for current experiments.
- **`must_include_terms` not consumed downstream**: The schema asks the LLM to produce `must_include_terms` per sub-query, but these are carried through as metadata only. They are never used to filter or boost retrieval results.
- **Variant retrieval depth is independent of baseline**: Each variant retrieves `variant_k_per_query` (20) candidates independently. There is no mechanism to skip retrieval for a variant that is lexically near-identical to the original query.
- **No utility measurement**: The system logs what variants added, but there is no runtime decision to skip or short-circuit when variants add no novel candidates.

---

## 7. Configuration Surface

### 7.1 Experiment YAML (example: `phb5e_multihop_e6_responses_decompose.yaml`)

```yaml
query_enhancement:
  enabled: true
  mode: decompose
  profile_path: "retrieval_lab/query_enhancement/profiles/phb5e_decompose_profile.json"
  fusion_mode: only_add
  # only_add sub-config (from config.py OnlyAddFusionConfig):
  #   include_original: true (default)
  #   baseline_keep_n: 20
  #   variant_k_per_query: 20
  #   admission_cutoff: 50
  #   prefix_lock_n: 20
  #   tail_rerank: "none"
```

### 7.2 Profile JSON (example: `phb5e_decompose_profile.json`)

```json
{
  "profile_id": "phb5e_decompose_v2",
  "corpus_id": "DnD_PHB_5.5",
  "decomposition": {
    "enabled": true,
    "when": "always",
    "model_id": "",
    "reasoning_effort": "low"
  },
  "policies": {
    "max_expanded_queries": 3,
    "include_original": true,
    "drift_guard": { "enabled": false }
  }
}
```

### 7.3 `OnlyAddFusionConfig` (from `config.py`)

```python
@dataclass
class OnlyAddFusionConfig:
    include_original: bool = True
    baseline_keep_n: int = 20
    variant_k_per_query: int = 20
    admission_cutoff: int = 50
    prefix_lock_n: int = 20
    tail_rerank: str = "none"
    tail_rerank_window: int = 50
    append_score_band: float = 1e-6
```

### 7.4 MODEL_POLICY.json Resolution

When `decomposition.model_id` is empty:
```
MODEL_POLICY.json → actions.structured_generation → role key → models[role] → model string
```

---

## 8. File-by-File Reference

| File | Lines | Role |
|------|-------|------|
| `retrieval_lab/query_enhancement/decomposition.py` | 265 | LLM decomposition call, prompt, parse, vocabulary guard, model resolution, cache signature |
| `retrieval_lab/query_enhancement/enhancer.py` | 338 | Top-level `enhance_queries()`, mode dispatch, dict/llm/decompose branches, dedup+cap |
| `retrieval_lab/query_enhancement/multi_query.py` | 363 | `fuse_only_add`, `fuse_multi_query_rankings`, `fuse_union_rerank`, `lock_prefix`, `lexical_rerank_tail_segment`, `expand_query_texts` |
| `retrieval_lab/query_enhancement/profile.py` | 295 | `QueryExpansionProfile` + all sub-config dataclasses, load/parse/validate, `normalize_query` |
| `retrieval_lab/query_enhancement/cache.py` | ~87 | `QueryEnhancementCache` — blake3-keyed file-based JSON cache |
| `retrieval_lab/config.py` | ~816 | `OnlyAddFusionConfig`, `QueryEnhancementConfig`, `ExperimentConfig` with validation |
| `retrieval_lab/orchestration/dense_mode.py` | ~1883 | Full dense/hybrid orchestration including QE wiring, tier gating, variant embedding, fusion, reranking |
| `retrieval_lab/orchestration/bm25_mode.py` | ~440 | BM25 orchestration with parallel QE path |

---

## 9. Open Issues and Recommended Investigations

### 9.1 Baseline Parity (HIGHEST PRIORITY)

The decompose run's internal baseline differs from the standalone baseline. Until this is understood, all regression measurements confound two sources: execution-path divergence and decomposition quality.

**Investigate:**
- Are query embeddings identical between standalone and decompose paths for the original query?
- Is offset accounting correct when variant embeddings are sliced from the batch?
- Does hybrid fusion receive identical inputs for the original query in both paths?
- Does any scoring/normalization path change when `use_qe=True`?

### 9.2 Sub-Query Count Control

The prompt says "smallest set" but the schema allows unbounded arrays. One observed case generated 17 variants. Consider:
- Adding `maxItems` to the JSON schema
- Adding a hard cap in `parse_decomposition_response`
- Making the profile's `max_expanded_queries` actually enforce during decompose mode

### 9.3 Hard-Case-Only Controller

PF2E shows weak evidence that decomposition could help when the baseline is structurally weak. PHB does not. A future experiment could:
1. Run baseline retrieval first
2. Evaluate a cheap structural heuristic (top results dominated by taxonomy/overview pages)
3. Only decompose if the heuristic fires

### 9.4 Prompt Tightening

The prompt needs explicit prohibitions:
- No external sources (Sage Advice, designer rulings)
- No cross-edition references
- No generic taxonomy or background research
- Each sub-query must preserve at least one anchored entity from the original

### 9.5 `include_original: false` Experiment

The `OnlyAddFusionConfig.include_original` flag was recently added but has not been tested. Running with `include_original: false` would show what decomposition produces in isolation, without the baseline safety net.

### 9.6 Tail Size Reduction

Current default appends 30 candidates on nearly every query for near-zero gold yield. Reduce `variant_k_per_query` and `admission_cutoff` significantly and measure impact.

### 9.7 `must_include_terms` Utilization

The schema asks the LLM to produce `must_include_terms` but these are never used for retrieval filtering or boosting. Consider using them as post-retrieval admission criteria.

---

## 10. Summary for Follow-On Agent

**What works:**
- The decomposition infrastructure is solid: caching, deterministic fusion, vocabulary guard, tier gating, structured output schema.
- The code is well-separated and the orchestration wiring is clean.

**What does not work yet:**
- The decomposition prompt generates too-broad obligations that dilute retrieval rather than focusing it.
- Always-on decomposition damages easy queries that the baseline already handles.
- The only_add fusion appends a large tail of low-value candidates.
- There is an unexplained baseline divergence between standalone and decompose execution paths.

**What to do next (in priority order):**
1. Investigate and fix baseline parity inside the decompose path.
2. Cap sub-query count in the schema or parser.
3. Tighten the prompt to corpus-native obligations only.
4. Test `include_original: false` to isolate decomposition quality.
5. Reduce tail size aggressively.
6. If pursuing further, gate decomposition to hard cases only (PF2E first).

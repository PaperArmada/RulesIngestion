# Design Doc: Corpus-Specific Query Enhancement for TTRPG Rulebook Retrieval

**Version:** v0.1 (implementation kickoff)  
**Owner:** Retrieval Lab / DungeonOverMind  
**Status:** Proposed  
**Date:** 2026-02-22
**Canonical note:** This is a future-facing proposal, not part of the current
stabilized Mark III baseline.

---

## 1. Context and Motivation

We have strong baseline retrieval and a benchmark that is now structurally fair (minimal-anchor gold). The next lever we want is improving recall/coverage on multi-hop questions without destabilizing the retrieval stack or contaminating citations.

Query enhancement (synonym steering, multi-query expansion, and optional decomposition) is attractive because:

- **It's "above" retrieval:** we can toggle it without changing indexes or graph traversal.
- **It can improve recall for term-mismatched corpora** (different books use different vocabulary).
- **It can help multi-hop questions** by pulling anchors from multiple sections (combat loop + spell constraint + movement, etc.).
- **It can be made deterministic** with strict controls (temperature=0 + caching + versioned config).

**Critical constraint:** Citations must resolve to EvidenceUnits. Query enhancement may steer retrieval but must never become "evidence."

---

## 2. Goals

| ID | Goal |
|----|------|
| G1 | Improve retrieval coverage (Recall@k / gold-in-candidates) on complex and multi-hop benchmark queries using a corpus-specific vocabulary profile. |
| G2 | Keep determinism: identical (corpus, query, config, model, prompt) must yield identical rewritten queries and identical retrieval results. |
| G3 | Preserve auditability: every produced expanded query is logged; we can attribute any "gold gained" to specific expansions. |
| G4 | Be minimally invasive: integrate as a pre-retrieval module that outputs a list of query strings (plus optional metadata), then uses existing retrievers + fusion. |
| G5 | Provide a clean evaluation harness: run all benchmarks with and without the module, compare deltas, and detect T1 regressions. |

---

## 3. Non-Goals

| ID | Non-Goal |
|----|----------|
| NG1 | We are not changing chunking, embedding model, indexing, graph construction, or reranking algorithms in this effort (except where needed to accept multi-query inputs). |
| NG2 | We are not adding runtime nondeterminism or agent loops to the retrieval pipeline. |
| NG3 | We are not changing EvidenceUnit definitions or citation mechanics. |
| NG4 | We are not building a generic "best query enhancement library." This is scoped to our corpus + enrichment metadata + deterministic evaluation needs. |

---

## 4. Definitions

| Term | Definition |
|------|------------|
| **Query Expansion** | Generate multiple query variants (paraphrases, synonym-injected, facet-focused) from the user query. |
| **Multi-Query Retrieval** | Run retrieval per query variant, then union/fuse results (e.g., RRF), then rerank/dedupe as normal. |
| **Query Decomposition** | For multi-hop questions, split into subqueries ("initiative order", "spell declaration timing", "movement per round") and retrieve for each. |
| **Profile** | Corpus-specific config that defines vocabulary, synonyms, and query rewrite policies. |

---

## 5. High-Level Architecture

Pipeline shape (**new module in bold**):

```
Input query
  → normalize_query (deterministic)
  → **QueryEnhancer(profile, query) → [q0, q1, q2…]**
  → retrieve_each(q_i) using existing hybrid retrieval
  → **fuse candidates across q_i (RRF/union + stable ordering)**
  → existing rerank/merge logic
  → return EvidenceUnits (and any parent/structural context if your UI wants it)
```

**Key integration point:** `QueryEnhancer` is "pure" given its inputs (profile + query + model/prompt hash), and its outputs are cached.

---

## 6. Data Model: `QueryExpansionProfile` (per corpus)

Store this as a versioned artifact alongside corpus build outputs.

### Fields (proposed)

```yaml
profile_id: string           # e.g., "swcr_v1_qe_001"
corpus_id: string + corpus_hash
profile_version: semver
profile_hash: stable hash of the canonical JSON (sorted keys)

normalization:
  lowercase: bool
  unicode_nfkc: bool
  strip_punct: bool          # careful: dice notation
  dice_normalization: rules  # e.g., "d 20" → "d20"
  stopword_policy: none | light | bm25_default

synonym_sets:                # list of
  - name: "gm_terms"
    canonical: "referee"
    variants: ["gm", "dm", "judge", "keeper", "mc", ...]
    notes: optional
    scope: retrieval_only    # always

term_boosters:               # optional
  - concept: "saving_throw"
    boosters: ["save", "resist", "avoid", "hazard"]
    weight_hint: float

allowed_vocab:               # optional but strongly recommended
  top_keywords: [from enrichment pass]
  headings: [TOC headings, chapter titles]
  entities: [class names, condition names, procedure names]
  # Purpose: constrain LLM output to in-corpus vocabulary to reduce drift.

policies:
  max_expanded_queries: int  # start 3
  include_original: bool     # true
  require_facet_diversity: bool  # true
  drift_guard:
    enabled: bool
    method: embedding_similarity | lexical_overlap
    threshold: float

decomposition:
  enabled: bool
  max_subqueries: int        # start 3
  when: "multi_hop_only" | "always" | "never"
  heuristic: rules           # for triggering decomposition (see §7.4)

llm_rewrite:
  enabled: bool
  model_id: exact            # pin
  temperature: 0
  top_p: 1
  prompt_template_id + prompt_hash
  output_schema_version

cache:
  enabled: true
  key: hash(corpus_id, corpus_hash, profile_hash, query_norm, model_id, prompt_hash)
  storage: local file cache (deterministic) + optional DB later
```

---

## 7. `QueryEnhancer` Behavior

### 7.1 Normalization (deterministic)

- Apply normalization rules from profile.
- Keep a "display query" for logs; use normalized query for caching.

### 7.2 Deterministic dictionary expansion (no LLM)

- If query contains terms present in `synonym_sets`, emit one or more variants that swap canonical/variants.
- Add controlled "OR" variants if your retriever supports it; otherwise emit distinct query strings.

**Example:**

| | |
|---|---|
| Original | "how does initiative work" |
| Variant 1 | "initiative order of battle" |
| Variant 2 | "initiative turn order" |
| Variant 3 | "surprise initiative order" |

### 7.3 LLM multi-query rewriting (structured output)

Only if enabled.

**LLM inputs:**
- Original query
- Profile summary: allowed vocab + synonym sets + headings
- Explicit constraints:
  - Produce N queries
  - Each query must use vocabulary from allowed sets where possible
  - Maximize facet diversity
  - No new game terms not in `allowed_vocab` (or must be marked `out_of_vocab`)

**LLM output schema (strict):**

```json
{
  "queries": [
    {
      "q": "...",
      "intent": "facet:initiative",
      "used_terms": ["initiative", "order of battle"],
      "notes": ""
    }
  ]
}
```

**Post-processing:**
- Enforce max length
- Enforce dedupe
- Stable ordering (sort by intent then q)
- Drift guard filter (optional)

**Caching:**
- Cache raw output + post-processed queries
- Cache hit must bypass LLM call entirely

### 7.4 Decomposition (optional)

When enabled, `QueryEnhancer` can output subqueries instead of paraphrases.

**Trigger heuristic options:**
- Benchmark tier: only for T2/T3 (multi-hop suites)
- Presence of conjunctions ("and", "during combat while", "when X and Y")
- Length > N tokens
- Known "multi-facet templates" (combat + spell + movement, etc.)

**Output:**
- `q0` — original
- `q1` — "subquestion A"
- `q2` — "subquestion B"
- `q3` — "subquestion C"

---

## 8. Fusion Strategy

We already have a retrieval system; we add a multi-query wrapper.

### Option A (simplest): Union then rerank

1. Retrieve topK per query variant
2. Union candidates (dedupe by EvidenceUnit ID)
3. Rerank union with existing reranker
4. Return topN

### Option B: RRF then rerank (recommended)

1. Compute Reciprocal Rank Fusion score over per-query ranked lists
2. Use RRF to produce a fused ordering
3. Optional rerank on topM fused
4. Return topN

### Determinism requirements

- Stable tie-breakers (EvidenceUnit ID lexical)
- Stable sorting
- Stable floating-point formatting if persisted

---

## 9. Logging and Auditability (required)

Per query run, persist:

| Field | Description |
|-------|-------------|
| `query_id`, `corpus_id`, `profile_id`, `profile_hash` | Identity fields |
| `query_raw`, `query_norm` | Input queries |
| `enhancer_mode` | `none` \| `dict` \| `llm` \| `llm+dict` \| `decompose` |
| `expansions` | Ordered list (with intents) |
| `cache_hit` | `true` / `false` |
| `retrieval_per_expansion` | topK ids + scores per expansion |
| `fused_list` | topN ids + scores |
| **Gold attribution** | |
| `gold_found_from_original_only?` | Was original query sufficient? |
| `gold_first_seen_in_expansion_i?` | Which expansion surfaced gold? |
| `per_expansion_delta` | Per-expansion delta in gold coverage |

This is how we prevent "silent benchmark leakage" and keep the system honest.

---

## 10. Evaluation Plan

### 10.1 Experiment matrix (minimum viable)

Run all benchmarks (or at least all corpora you care about) under:

| Experiment | Description |
|------------|-------------|
| **E0** | Baseline: no enhancement |
| **E1** | Dict-only expansion |
| **E2** | LLM multi-query (N=3) + `include_original` |
| **E3** | Decomposition-only (`max_subqueries=3`) |
| **E4** | Decomposition + 1 paraphrase per subquery (optional follow-up) |

### 10.2 Metrics (existing + new)

**Keep existing:**
- MRR
- Hit@10
- Recall@10
- ReqFSH@10 / FSH@10 (on minimal-anchor suites)

**Add:**

| Metric | Description |
|--------|-------------|
| **Gold-in-candidates ceiling** | % queries where any gold appears anywhere in candidate pool |
| **Candidate inflation** | \|C\_union\| / \|C\_baseline\| |
| **Expansion contribution** | % queries where expansion introduced first gold hit |
| **T1 regressions** | Must be near-zero (or explicitly explained) |

**Interpretation rule:** A "good" enhancement primarily reduces "gold not in candidates" failures, not just reshuffles rank.

### 10.3 Acceptance criteria (initial)

- No more than X% T1 regressions (suggest X = 1–2% with investigation list)
- Meaningful improvement on multi-hop suites:
  - +5–10 points Recall@10 or ReqFSH@10 on T2/T3 (depending on baseline)
- Candidate inflation bounded:
  - Median inflation ≤ 2–3x (else you're paying too much noise)

---

## 11. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| **R1: Query drift / noise explosion** | `allowed_vocab` constraint; small N expansions; drift guard; facet-diverse prompts |
| **R2: Nondeterminism introduced** | `temperature=0`; pinned `model_id`; prompt hash/versioning; caching and replay tests; stable ordering |
| **R3: Benchmark "table-of-contents steering"** | Attribution logging (did headings cause the gain?); separate reporting: "with structural hints" vs "without" |
| **R4: Overfitting to a corpus profile** | Keep universal synonym sets separate from corpus-specific; evaluate across multiple books |

---

## 12. Implementation Plan (Agent Task Breakdown)

### Phase 0: Scaffolding (determinism first)

- Define `QueryExpansionProfile` JSON schema + hashing rules
- Implement profile loader + validator
- Implement cache interface (file-based) with stable keys
- Add run manifest fields for `profile_hash`, `prompt_hash`, `model_id`

### Phase 1: Dictionary expansion

- Implement synonym swapper + OR/query list generation
- Integrate multi-query retrieval wrapper (union/RRF)
- Add logging + report deltas

### Phase 2: LLM multi-query expansion

- Implement structured prompt + schema parsing
- Enforce deterministic settings and caching
- Add drift guard (optional)
- Add attribution metrics

### Phase 3: Decomposition (optional)

- Implement decomposition mode + heuristic trigger
- Add evaluation tier gating (only T2/T3 initially)

### Phase 4: Evaluation harness integration

- Add config toggles (E0–E4)
- Run across all benchmarks
- Emit side-by-side report with regressions list

### Phase 5: Hardening

- Replay tests (same input → identical output)
- Lint: profile must be versioned and hashed
- Document: how to author synonym sets from enrichment outputs

---

## 13. Open Questions (decide during implementation)

1. Should the enhancer be allowed to emit fielded queries (e.g., `heading:combat`) if your index supports it, or only raw strings?
2. Should we prefer decomposition over expansion for T2/T3 by default?
3. Do we want a "profile generator" step that distills `allowed_vocab` from enrichment keywords automatically, or hand-curated first?
4. Best fusion method in your stack: pure union+rerank vs RRF+rerank? (Recommendation: start with RRF; it's easy and stable.)

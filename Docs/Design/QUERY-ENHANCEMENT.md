---
title: "Technical Architecture: Corpus-Specific Query Enhancement"
project: "DungeonOverMind / RulesIngestion"
owner: "Retrieval Lab"
status: "Active (implemented)"
version: "v0.1"
last_updated: "2026-02-23"
related:
  - "DESIGN-Corpus-Specific-Query-Enhancement.md"
---

## Executive Summary

This document describes the **implemented** technical architecture for **corpus-specific query enhancement** in `RulesIngestion/retrieval_lab/`.

The system adds a deterministic pre-retrieval layer that can:

- Expand queries via **dictionary synonym swapping** (`mode=dict`)
- Expand queries via **LLM multi-query rewriting** with a strict JSON schema (`mode=llm`, `mode=llm+dict`)
- Optionally **decompose multi-hop queries** into subqueries (`mode=decompose`)

Enhancement never produces evidence. **All citations remain `EvidenceUnit` IDs returned by existing retrievers.**

## Scope and Non-Scope

### In scope

- Deterministic query enhancement controlled by a **versioned profile artifact**
- Per-query expansion, per-variant retrieval, and **RRF fusion** back into a single ranked list
- Deterministic caching of expansions (bypass LLM call on cache hit)
- Integration into both dense/hybrid retrieval and BM25 retrieval
- CLI + YAML configuration surfaces

### Out of scope (unchanged)

- Chunking / extraction / indexing
- Embedding models and vector stores
- Core ranking and reranking algorithms (except wrapping retrieval “per expanded query”)
- EvidenceUnit schema and citation mechanics

## System Overview

### High-level data flow

```mermaid
flowchart TD
  A[grounded_queries] --> B[build_query_text per query]
  B --> C{query_enhancement.mode != none?}
  C -->|no| D[encode/retrieve baseline]
  C -->|yes| E[enhance_queries(profile, query_text)]
  E --> F[variants: q0,q1,q2...]
  F --> G[retrieve per variant]
  G --> H[RRF fuse per query]
  H --> I[existing post-retrieval expansion + boosts]
  D --> I
  I --> J[ranked EvidenceUnit IDs + scores]
```

### Determinism contract

For identical inputs, the system is designed to produce identical expansion outputs and identical retrieval results, modulo nondeterminism in external model providers.

Inputs that are considered “identity-defining”:

- `corpus_id`, `corpus_hash`
- `profile_hash` (canonical JSON + blake3)
- normalized query text (`query_norm`)
- `mode` (`none|dict|llm|llm+dict|decompose`)
- if LLM enabled: `model_id`, `prompt_hash`, `temperature=0`, `top_p=1`

## Module Architecture (Implemented)

### Packages and files

| Path | Role |
|------|------|
| `RulesIngestion/retrieval_lab/query_enhancement/profile.py` | Profile schema, canonical hashing, loader, validator, `normalize_query()` |
| `RulesIngestion/retrieval_lab/query_enhancement/cache.py` | Deterministic file cache keyed by all identity-defining inputs |
| `RulesIngestion/retrieval_lab/query_enhancement/enhancer.py` | `enhance_queries()` + dict expansion + LLM expansion + decomposition + drift guard |
| `RulesIngestion/retrieval_lab/query_enhancement/multi_query.py` | Expand → retrieve per variant → RRF fuse helper functions |
| `RulesIngestion/retrieval_lab/query_enhancement/attribution.py` | Attribution metrics (candidate inflation, expansion contribution) |
| `RulesIngestion/scripts/build_qe_profile.py` | Profile generator from substrate enrichment outputs |

### Retrieval integration points

| Retrieval path | Injection point |
|---|---|
| Dense / Hybrid | `retrieval_lab/orchestration/dense_mode.py::_run_ranking_pipeline()` after `build_query_text()` and before encoding/retrieval |
| BM25 | `retrieval_lab/orchestration/bm25_mode.py::run_bm25_mode()` before BM25 scoring |
| Experiment orchestration | `retrieval_lab/run_experiment.py::_run_experiment()` loads profile + cache and passes into modes |

## Query Expansion Profile Artifact

### Profile file

The profile is loaded from a JSON file configured via:

- YAML: `query_enhancement.profile_path`
- CLI: `--enhancement-profile`

### Profile schema (core fields)

Implemented in `QueryExpansionProfile`:

- Identity: `profile_id`, `corpus_id`, `corpus_hash`, `profile_version`
- Determinism: `profile_hash = blake3(canonical_json(profile))`
- Normalization: `lowercase`, `unicode_nfkc`, `strip_punct`, `dice_normalization`, `stopword_policy`
- Expansion inputs:
  - `synonym_sets[]` (dict expansion)
  - `allowed_vocab.{top_keywords,headings,entities}` (LLM steering / drift reduction)
- Policies:
  - `max_expanded_queries`, `include_original`, `require_facet_diversity`
  - `drift_guard.{enabled,method,threshold}` (currently lexical overlap supported)
- LLM:
  - `llm_rewrite.{enabled,model_id,temperature,top_p,prompt_hash,...}`
- Cache:
  - `cache.{enabled,cache_dir}`

### Where the corpus profile comes from

The profile is a **derived artifact** generated from existing substrate outputs plus manual curation:

- **Auto-aggregated**
  - `stageAPrime.enrichments.json`
    - `lexical_anchors` → `allowed_vocab.top_keywords`
    - `mechanic_atoms[].surface_forms` → `allowed_vocab.entities`
    - `topic_tags` → metadata/debugging
  - `stageB.evidence_units.json`
    - `EvidenceUnit.structural_path[]` → `allowed_vocab.headings`
- **Hand-authored**
  - `synonym_sets` (corpus-specific synonym normalization)
  - optional `term_boosters`

The generator script:

- `RulesIngestion/scripts/build_qe_profile.py`

## Enhancement Modes and Behavior

### Mode: `none`

- No expansion; original query only.

### Mode: `dict`

- Deterministic synonym swapping using `synonym_sets`.
- Produces expansion metadata with `intent` like `synonym:<set>:<a->b>`.

### Mode: `llm` / `llm+dict`

- Uses OpenAI Chat Completions with `response_format={"type":"json_object"}` and a strict JSON schema:

```json
{
  "queries": [
    { "q": "…", "intent": "facet:initiative", "used_terms": ["initiative"], "notes": "" }
  ]
}
```

- Determinism controls:
  - `temperature = 0.0`
  - `top_p = 1.0`
  - pinned `model_id`
  - prompt content derived from the profile (allowed vocab + headings + synonyms)
  - output is cached by key including `prompt_hash` and `model_id`

### Mode: `decompose`

- Produces subqueries when `_should_decompose()` triggers.
- Trigger heuristics implemented:
  - conjunction patterns (`and/while/during/but`)
  - long query length
  - multi-facet templates (combat/spell/movement/initiative/action)
- Decomposition can use LLM if LLM is enabled, otherwise it falls back to a deterministic heuristic split.

## Multi-Query Retrieval and Fusion

### Per-variant retrieval

For each original query \(q\):

- Build expansions: \([q_0, q_1, ..., q_m]\)
- Retrieve topK per expansion using the existing retriever for that mode
- Collect ranked lists per expansion: \(R_0, R_1, ..., R_m\)

### Fusion: Reciprocal Rank Fusion (RRF)

RRF is used to fuse \(R_i\) into one list per original query.

Determinism requirements for fusion:

- Stable ordering for equal scores via lexical tie-break on `EvidenceUnit.id`
- Stable float formatting only at presentation/persistence boundaries

## Caching

### What is cached

- Expansion results (list of expansion dicts) per normalized query and profile identity.

### Cache key

`blake3("|".join([corpus_id, corpus_hash, profile_hash, query_norm, mode, model_id, prompt_hash]))`

### Storage

- One JSON file per cache key in `profile.cache.cache_dir`.

## Configuration Surfaces

### YAML (ExperimentConfig)

In `retrieval_lab/config.py`:

```yaml
query_enhancement:
  enabled: true
  profile_path: "profiles/swcr_v1_qe_001.json"
  mode: "dict"  # none|dict|llm|llm+dict|decompose
```

### CLI overrides

In `retrieval_lab/orchestration/cli_parser.py` and `cli.py`:

- `--enhancement-mode none|dict|llm|llm+dict|decompose`
- `--enhancement-profile path/to/profile.json`

## Logging, Auditability, and Attribution

### What is recorded

- Experiment document includes:
  - query enhancement enabled/mode
  - `profile_id` and `profile_hash` (short form)
- In the retrieval pipeline, per-query expansion logs are attached when available.
- Report includes a “Query Enhancement” section and an “Enhancement Attribution” section when enabled.

### Attribution metrics

Implemented in `retrieval_lab/query_enhancement/attribution.py`:

- **Candidate inflation** (median and p95) when baseline is available
- **Gold from expansion** vs “gold from original only”
- **Expansion contribution %** (first-order approximation)

## Testing and Hardening

### Determinism tests

Unit tests validate deterministic behavior for:

- profile hashing
- normalization
- dict expansion output ordering
- cache round-trips
- decomposition heuristic splits
- CLI overrides

### Known limitations (current v0.1)

- LLM determinism depends on the model provider honoring `temperature=0` and stable decoding; caching mitigates this after first execution.
- Decomposition tier gating by benchmark tier (T2/T3) is described in the design doc; current implementation uses heuristics on query text and profile settings.

## Operational Notes

### Safe rollout pattern

Recommended rollout for benchmark-driven integration:

1. `mode=none` (baseline)
2. `mode=dict` with a minimal synonym set
3. `mode=llm+dict` with caching enabled and drift guard enabled
4. `mode=decompose` only when multi-hop tiers require it

### Failure modes to watch

- Candidate set explosion (inflation > 3x median)
- Drift guard too strict (drops useful expansions)
- Over-steering by headings (TOC “cheating”) — requires attribution review


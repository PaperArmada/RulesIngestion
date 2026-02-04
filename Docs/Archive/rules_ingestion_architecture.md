# Rules Ingestion Architecture

> **DEPRECATED**: This document has been superseded by [ARCHITECTURE.md](ARCHITECTURE.md).
> Please refer to the new documentation for current, comprehensive architecture information.
> This file is preserved for historical reference only.

**Date:** 2026-01-24
**Scope:** RulesIngestion service only

## Purpose
This document captures the **implementation architecture** of RulesIngestion:
- Entry points (CLI + HTTP service)
- Pipeline stages and data flow
- Storage layout (disk + MongoDB)
- Key modules and boundaries

For the **conceptual stage boundaries**, see `Docs/rule_ingestion_pipeline_overview.md`.

---

## Entry Points

### CLI
- `rules_ingestion_pipeline.py` (primary)
  - End-to-end: PDF -> Marker -> enrich -> graph -> metrics
  - Enrich-only: use existing Marker chunks
  - Optional LLM passes (`--llm-pre-enrich`, `--llm-review`)

### HTTP Service
- `ingestion_service.py`
  - FastAPI app for async ingestion jobs and config generation
  - Wraps pipeline functions for service use

### Thin Wrapper
- `main.py`
  - Delegates to `rules_ingestion_pipeline.main()`

---

## Data Flow (Implementation)

```
PDF / DOCX
  -> Marker extraction (marker_single)
  -> Marker JSON chunks + markdown
  -> Ruleset config resolution (MongoDB + optional LLM)
  -> Deterministic enrichment (content kind, tags, traits, spell stats)
  -> Graph construction (document -> section -> chunk + next edges)
  -> Optional LLM passes (paragraph + review)
  -> Outputs (enriched, coalesced, graph, evaluation queries, metrics)
```

Key invariants (enforced by pipeline + guidebook):
- Deterministic enrichment precedes any LLM pass
- Graph nodes point to chunk IDs (no text duplication)
- Adaptive review gate must meet 99% coverage

---

## Retrieval Layers (Post-Ingestion)

Retrieval must remain bounded by structure:

1. **Structural eligibility traversal**
   - Uses only structural + deterministic edges
   - Purpose: eligibility, not relevance
2. **Semantic narrowing**
   - Hybrid dense + sparse retrieval
   - Ranks within eligible set
3. **Fine-grained search**
   - Uses tags, summaries, embeddings, soft signals
4. **LLM synthesis**
   - Reasoning and citation only
   - No retrieval decisions

Traversal is a discipline: structure restricts eligibility, semantics ranks within it.
Summaries are interfaces, not shortcuts, and must follow traversal.

---

## Core Modules

### Orchestration
- `rules_ingestion_pipeline.py`
  - Pipeline CLI and orchestration
  - Marker integration
  - Ruleset config resolution
  - Output writing

### Extraction
- Marker integration in `rules_ingestion_pipeline.py`

### Deterministic Enrichment
- `enrichment.py`
  - Content classification
  - Tag + trait extraction
  - Spell metadata and spell-block merging

### LLM Enrichment and Config
- `llm_enrichment.py`
  - Paragraph enrichment and review passes
  - Evaluation query generation
- `llm_config_generator.py`
  - LLM-based ruleset config generation

### Configuration System
- `config_profile.py` (ruleset profile assembly)
- `config_generator.py` (ruleset config generation)
- `config_store.py` (MongoDB persistence)

### Outputs and Run Tracking
- `pipeline_outputs.py` (disk output writer)
- `pipeline_runs.py` (run lifecycle)
- `diagnostics_store.py` (MongoDB diagnostics and snapshots)
- `metrics_review.py` (coverage metrics and gates)

---

## Storage Layout

### Disk Outputs (canonical layout)
```
Rules/.../outputs/
  configs/
    <ruleset_id>/
      v001.config.json
  runs/
    <timestamp>/
      marker_raw/
      enriched/
        <doc_id>.enriched.json
        <doc_id>.coalesced.json
        <doc_id>.graph.json
        <doc_id>.evaluation_queries.json
        <doc_id>.llm_paragraphs.json   (optional)
        <doc_id>.llm_review.json       (optional)
        <doc_id>.metrics.json
  experiments/
```

### MongoDB (canonical collections)
Rules ingestion DB (`rules_ingestion` or `RULES_INGESTION_DB_NAME`):
- `ruleset_configs`
- `ruleset_profiles`
- `enrichment_runs`
- `run_inputs`
- `run_outputs`

RulesLawyer benchmark DB (`ruleslawyer` or `RULESLAWYER_DB_NAME`):
- `embedding_runs`
- `embedding_chunks`
- `evaluation_runs`

---

## Responsibilities and Boundaries

### RulesIngestion owns:
- Deterministic extraction and enrichment
- Ruleset config generation and storage
- Enriched chunk store (RAG input)
- Graph construction and evaluation query generation

### RulesIngestion does NOT:
- Perform runtime rule evaluation
- Resolve rule conflicts
- Execute rules or interpret rule outcomes

---

## Key Dependencies

- Marker CLI (`marker_single`) for PDF extraction
- MongoDB for config + run persistence
- LLM provider for optional enrichment/config generation

---

## Tests and Verification

- `tests/` contains service tests for pipeline and utilities
- Pipeline produces `*.metrics.json` and fails on coverage < 99%
- Evaluation queries generated from enriched chunks

---

## Related Docs

- `Docs/rule_ingestion_pipeline_overview.md` (conceptual stages)
- `Docs/ingestion_polishing_guidebook.md` (operational guidance)
- `Docs/rule_ingestion_philosophy.md` (principles)

# RulesIngestion

Transform TTRPG rulebooks into structured, graph-connected, retrieval-ready artifacts.

RulesIngestion is the **ingestion layer** of DungeonMind's rules system. It produces enriched chunks, deterministic graphs, and evaluation assets consumed by RulesLawyer for hybrid retrieval.

## Quick Start

```bash
# Full pipeline: PDF → enriched chunks → graph → evaluation queries
uv run python ingest.py \
  --ruleset StarFinder2e \
  --ruleset-id sf2e-playercore \
  --book PlayerCore \
  --profile full \
  --auto-config
```

## Architecture Overview

### Core Philosophy

**Determinism First**: All rule-based enrichment (content classification, tag extraction, graph construction) happens before any LLM calls. This ensures:
- Reproducibility (same input → same output)
- Speed (no API latency for core extraction)
- Debuggability (rule-based logic is traceable)

LLM passes are optional enhancements, not dependencies.

### Pipeline Phases

The graph builder uses a phased pipeline with explicit data boundaries:

| Phase | Function | Output |
|-------|----------|--------|
| **Phase 0** | Structural seed | Doc/section/chunk nodes + contains/next edges |
| **Phase 1** | Entity extraction | `CandidateBundle` (candidates + relation mentions) |
| **Phase 2** | Canonicalization | `CanonicalizationResult` (alias resolution) |
| **Phase 3** | Materialization | Entity nodes + describes/mentioned_in edges |
| **Phase 5** | Fact ownership | belongs_to edges + procedure anchoring |

### System Boundaries

```
┌─────────────────────────────────────────────────────────────────────┐
│                         RulesIngestion                              │
│  (PDF → Enriched Chunks + Graph → Disk)                            │
│                                                                     │
│  PRODUCES:                                                          │
│  • Enriched chunks with TTRPG metadata                              │
│  • Deterministic graph (structural + semantic edges)                │
│  • RuleFacts (typed assertions from clauses)                        │
│  • Evaluation queries and reports                                   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          RulesLawyer                                │
│  (Query → Hybrid Retrieval → LLM Answer)                           │
│                                                                     │
│  CONSUMES: enriched.json, graph.json                                │
│  OWNS: Embedding generation, BM25, graph boost, LLM answers         │
└─────────────────────────────────────────────────────────────────────┘
```

## Entry Points

| Entry Point | Purpose |
|-------------|---------|
| `ingest.py` | **Primary CLI** — batch processing with profiles (`full`, `enrich-only`, `eval-only`) |
| `rules_ingestion_pipeline.py` | Core pipeline logic; use for single-document processing |
| `ingestion_service.py` | FastAPI service for async job processing |

## Module Structure

### Enrichment (`enrichment/`)

| Module | Responsibility |
|--------|----------------|
| `graph_builder.py` | Phased graph construction; entity nodes, edges, fact ownership |
| `chunks.py` | `EnrichedChunk` dataclass; `enrich_chunk()` function |
| `extractors.py` | Content classification, tag/trait extraction |
| `rule_facts.py` | RuleFact extraction from clauses (grants, requires, on_failure, etc.) |
| `fact_relations.py` | Typed relations between RuleFacts (success/failure, level gates) |
| `clause_units.py` | Clause-level segmentation for fact extraction |
| `mentions.py` | Entity mention detection and typing |
| `coalescer.py` | Chunk merging for context (400-800 char targets) |

### Traversal (`traversal/`)

Graph traversal system for retrieval experimentation:

| Module | Responsibility |
|--------|----------------|
| `index.py` | Graph indexing and lookup |
| `traverse.py` | Core traversal logic |
| `retriever.py` | Chunk retrieval from graph |
| `hybrid_retriever.py` | Combined BM25 + semantic + graph retrieval |
| `reranker.py` | Result reranking |
| `policy.py` | Traversal policies (expansion rules) |
| `intent.py` | Query intent classification |

### Evaluation (`evaluation/`)

| Module | Responsibility |
|--------|----------------|
| `benchmark/orchestrator.py` | Evaluation run orchestration |
| `benchmark/embedding.py` | Embedding-based evaluation |
| `reporting.py` | Metrics computation and report generation |
| `scoring_engine.py` | Scoring logic for retrieval results |
| `metrics.py` | Metric definitions (recall, precision, etc.) |

### Configuration

| Module | Responsibility |
|--------|----------------|
| `config_profile.py` | Ruleset profile assembly from sample blocks |
| `config_generator.py` | Config generation with retries and diagnostics |
| `config_store.py` | MongoDB persistence for configs/profiles |
| `llm_config_generator.py` | LLM-based config generation when needed |

## Common Workflows

```bash
# Re-enrich existing chunks (skip PDF extraction)
uv run python ingest.py \
  --ruleset StarFinder2e \
  --book PlayerCore \
  --profile enrich-only \
  --run-dir Rules/StarFinder2e/PlayerCore/outputs/runs/<timestamp>

# Evaluation only (on an existing run)
uv run python ingest.py \
  --ruleset StarFinder2e \
  --book PlayerCore \
  --profile eval-only \
  --run-dir Rules/StarFinder2e/PlayerCore/outputs/runs/<timestamp>

# Enable LLM enrichment passes
uv run python ingest.py \
  --ruleset StarFinder2e \
  --book PlayerCore \
  --profile full \
  --llm-pre-enrich \
  --llm-review
```

## Output Layout

```
Rules/<Ruleset>/<Book>/outputs/
├── configs/<ruleset-id>/          # Generated ruleset configs
└── runs/<timestamp>/
    ├── marker_raw/                # Raw Marker extraction output
    ├── enriched/
    │   ├── <doc>.enriched.json    # Per-document enriched chunks
    │   ├── <doc>.graph.json       # Per-document graph
    │   ├── merged.enriched.json   # Merged enriched chunks
    │   └── merged.graph.json      # Merged graph
    └── reports/                   # Evaluation reports
```

## Graph Node Types

| Node Type | Description |
|-----------|-------------|
| `document` | Root document node |
| `section` | Section/chapter headers |
| `chunk` | Text chunks (enriched) |
| `entity` | Named entities (classes, ancestries, feats, spells, etc.) |
| `mechanic_frame` | Game mechanics (conditions, actions, skill checks) |
| `trait` | Traits attached to entities |
| `procedure` | Procedural steps (actions, checks) |
| `fact` | RuleFacts (typed assertions from clauses) |

## Graph Edge Types

| Edge Type | Description |
|-----------|-------------|
| `contains` | Structural containment (doc→section→chunk) |
| `next` | Sequential ordering (chunk→chunk) |
| `describes` | Entity definition (chunk→entity) |
| `mentioned_in` | Entity mention (entity→chunk) |
| `belongs_to` | Fact/procedure ownership (fact→entity) |
| `has_trait` | Trait attachment (entity→trait) |
| `requires_mechanic` | Mechanic dependency |
| `modifies_mechanic` | Mechanic modification |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | For LLM | LLM config generation and enrichment |
| `MONGODB_URI` | Optional | Config/run persistence |

## Testing

```bash
# Run all tests
uv run pytest tests/

# Run specific test suites
uv run pytest tests/test_graph_builder_determinism.py -v
uv run pytest tests/test_rule_facts.py -v
uv run pytest tests/test_fact_relations.py -v
```

## Documentation

### Core Documentation (Start Here)

- `Docs/ARCHITECTURE.md` — System architecture, module map, dependencies
- `Docs/INGESTION_PIPELINE.md` — Pipeline stages, entry points, transformations
- `Docs/RETRIEVAL_END_TO_END.md` — How RulesLawyer uses ingested data
- `Docs/INGESTION_PIPELINE_INVARIANTS.md` — Pipeline invariants and guarantees

### Reference Documentation

- `Docs/rule_ingestion_philosophy.md` — Design principles
- `Docs/ingestion_polishing_guidebook.md` — Operational reference
- `Docs/rule_ingestion_evaluation_criteria.md` — Evaluation metrics
- `Docs/FACT_BASED_RETRIEVAL_ARCHITECTURE.md` — RuleFact extraction design

### Handoffs

Active development handoffs are in `Handoffs/`. These capture in-progress experiments and next steps.

---

> We maintain a static rule graph that encodes mechanics, states, and procedures without time.
> A separate immutable frame timeline carries concrete world state.
> For each query or tick, we traverse the rule graph to determine which procedures are legal, modified, or blocked given the current frame state.
> Traversal never mutates state.
> Only after a procedure is selected do we commit symbolic effects to produce the next frame.
> Procedures are the sole bridge between rule semantics and temporal state change.

> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# Ingestion Pipeline

**Last Updated:** 2026-01-27  
**Status:** Canonical Reference

---

## Overview

The ingestion pipeline transforms TTRPG rulebook PDFs into structured, enriched chunks with graph connectivity. This document describes each pipeline stage, the transformations applied, and how to run the pipeline.

---

## Entry Points

### Primary CLI: `ingest.py`

The recommended entry point for batch processing.

```bash
cd /media/drakosfire/Projects/DungeonOverMind/RulesIngestion

# Full pipeline: PDF extraction + enrichment + edge discovery + merge
uv run python ingest.py --ruleset StarFinder2e --book PlayerCore --profile full

# Enrichment only (skip PDF extraction)
uv run python ingest.py --ruleset StarFinder2e --book PlayerCore --profile enrich-only

# Evaluation only
uv run python ingest.py --ruleset StarFinder2e --book PlayerCore --profile eval-only
```

**Key flags:**

- `--ruleset` - Ruleset name (e.g., StarFinder2e, Pathfinder2e)
- `--book` - Book name within ruleset
- `--profile` - Pipeline profile: `full`, `enrich-only`, `eval-only`
- `--skip-pattern` - Regex to skip PDFs (default: "Cover|INTRO")
- `--llm-pre-enrich` - Enable LLM paragraph enrichment
- `--llm-review` - Enable LLM review pass

### Core Pipeline: `rules_ingestion_pipeline.py`

Lower-level pipeline called by `ingest.py`. Use directly for single-document processing:

```python
from rules_ingestion_pipeline import process_pdf, enrich_existing_chunks

# Process a single PDF
results = process_pdf(
    pdf_path="/path/to/rulebook.pdf",
    output_dir="/path/to/outputs",
    ruleset_id="sf2e",
    use_llm=False,
)

# Enrich pre-extracted Marker chunks
results = enrich_existing_chunks(
    chunks_path="/path/to/marker_chunks.json",
    output_dir="/path/to/outputs",
    ruleset_id="sf2e",
)
```

### HTTP Service: `ingestion_service.py`

FastAPI service for async job processing:

```bash
# Start service
uv run uvicorn ingestion_service:app --host 0.0.0.0 --port 8001

# Queue ingestion job
curl -X POST http://localhost:8001/ingest \
  -H "Content-Type: application/json" \
  -d '{"pdf_path": "/path/to/rulebook.pdf", "ruleset_id": "sf2e"}'

# Check job status
curl http://localhost:8001/ingest/{job_id}
```

**Endpoints:**

- `POST /ingest` - Queue a PDF or chunks JSON for processing
- `GET /ingest/{job_id}` - Check job status
- `POST /api/rules-ingestion/configs/generate` - Generate ruleset configs
- `GET /api/rules-ingestion/runs/{run_id}` - Retrieve run records

### Deprecated: `main.py`

Thin wrapper that delegates to `rules_ingestion_pipeline.main()`. Use `ingest.py` instead.

---

## Pipeline Stages

### Stage 1: PDF Extraction (Marker)

**Module:** External CLI (`marker_single`)

**Input:** PDF file path  
**Output:** Marker chunks JSON in `{output_dir}/marker_raw/{pdf_name}/`

**Process:**

1. Invoke `marker_single` subprocess
2. Extract structured content (HTML, metadata, bounding boxes)
3. Write JSON chunks and metadata file

**Output structure:**

```json
[
  {
    "id": "block-001",
    "block_type": "Text",
    "html": "<p>The <b>Fireball</b> spell creates...</p>",
    "page": 42,
    "section_hierarchy": [
      { "title": "Chapter 7", "level": 1 },
      { "title": "Spells", "level": 2 }
    ],
    "bbox": [100, 200, 500, 300]
  }
]
```

**Key flag:** `--use-llm` enables better table extraction via LLM.

---

### Stage 2: Ruleset Config Resolution

**Modules:** `config_profile.py`, `config_generator.py`, `config_store.py`, `llm_config_generator.py`

**Input:** Raw Marker chunks  
**Output:** `RulesetConfiguration` object

**Process:**

1. **Build profile** from sample blocks (`build_ruleset_profile()`)
   - Heading hierarchy patterns
   - Block type distribution
   - Sample text for each block type
2. **Check MongoDB** for existing config
3. **Detect structure drift** (if profile changed significantly)
4. **Generate new config** via LLM if needed (`generate_config_with_llm()`)
5. **Store config/profile** in MongoDB for reuse

**Config structure:**

```json
{
  "ruleset_id": "sf2e-playercore",
  "version": "1.0.0",
  "deterministic_rules": {
    "spell_patterns": [
      "\\*\\*([A-Z][A-Z0-9\\s'\\-]+)\\*\\*\\s*\\*\\*(SPELL|CANTRIP)\\s+\\d+\\*\\*"
    ],
    "feat_patterns": [
      "\\*\\*([A-Z][A-Z0-9\\s'\\-]+)\\*\\*\\s*\\*\\*FEAT\\s+\\d+\\*\\*"
    ],
    "entity_aliases": { "AC": "Armor Class", "HP": "Hit Points" }
  },
  "llm_flags": {
    "nondeterministic_flags": ["requires", "prerequisite", "grants"]
  }
}
```

---

### Stage 3: Deterministic Enrichment

**Module:** `enrichment/chunks.py`, `enrichment/extractors.py`

**Input:** Raw Marker chunks + Resolved config  
**Output:** List of `EnrichedChunk` objects

**Process:**

1. **Extract text** from HTML (`extract_text_from_html()`)
2. **Build section path** from hierarchy (`build_section_path()`)
3. **Classify content kind**: spell, feat, item, rule, narrative, table, image
4. **Extract TTRPG metadata:**
   - Tags (from section path and text patterns)
   - Traits (keywords: fire, mental, sonic, etc.)
   - Spell rank, traditions, spell stats (for spells)
   - Rule-bearing flag (contains rule keywords)

**EnrichedChunk dataclass:**

```python
@dataclass
class EnrichedChunk:
    id: str
    text: str
    html: str
    page: int
    block_type: str
    section_path: List[str]
    content_kind: str          # spell, feat, item, rule, narrative, table, image
    tags: List[str]
    traits: List[str]
    spell_rank: Optional[int]
    traditions: List[str]
    spell_stats: Dict[str, str]
    is_rule_bearing: bool
```

**Content classification logic:**

```python
# Spell detection
if re.search(r"\*\*(SPELL|CANTRIP)\s+\d+\*\*", text):
    content_kind = "spell"

# Feat detection
elif re.search(r"\*\*FEAT\s+\d+\*\*", text):
    content_kind = "feat"

# Table detection
elif block_type in {"Table", "TableCell", "TableRow"}:
    content_kind = "table"

# Rule detection (section headers with rule keywords)
elif block_type == "SectionHeader" and any(kw in text.lower() for kw in RULE_KEYWORDS):
    content_kind = "rule"

# Default
else:
    content_kind = "narrative"
```

---

### Stage 4: Post-Enrichment Processing

**Modules:** `enrichment/spell_merger.py`, `enrichment/coalescer.py`

#### Spell Merging

Combines spell blocks split across pages:

```python
# Before: Two chunks for same spell
[
  {"id": "block-42", "text": "**FIREBALL** **SPELL 3**\nRange: 500 feet..."},
  {"id": "block-43", "text": "Duration: Instantaneous\nYou create a burst of flame..."}
]

# After: Single merged chunk
[
  {"id": "block-42", "text": "**FIREBALL** **SPELL 3**\nRange: 500 feet...\nDuration: Instantaneous\nYou create a burst of flame..."}
]
```

#### Chunk Coalescing

Merges small adjacent chunks for better context (target: 400-800 characters):

```python
# Before: Many small chunks
[
  {"id": "block-1", "text": "Combat Rules"},        # 12 chars
  {"id": "block-2", "text": "Initiative is..."},    # 50 chars
  {"id": "block-3", "text": "On your turn..."}      # 45 chars
]

# After: Merged into single chunk
[
  {"id": "block-1-3", "text": "Combat Rules\nInitiative is...\nOn your turn...", "merged_from": ["block-1", "block-2", "block-3"]}
]
```

---

### Stage 5: Graph Construction

**Module:** `enrichment/graph_builder.py`

**Input:** Enriched chunks + Ruleset ID  
**Output:** `Graph` object with nodes and edges

**Phased process (current):**

1. **Phase 0 — Structural seed**  
   Doc/section/chunk nodes + `contains` / `next` edges.
2. **Phase 1 — Candidate extraction**  
   Build `CandidateBundle` (entity candidates + relation mentions).
3. **Phase 2 — Canonicalization**  
   Resolve aliases and canonical IDs (`CanonicalizationResult`).
4. **Phase 3 — Materialization**  
   Entity nodes + `describes` / `mentioned_in` / `has_*` edges.
5. **Phase 3b — Header‑scope**  
   Add `describes` edges with `extraction_method="header_scope"` only.
6. **Phase 4 — Fact graph**  
   `RuleFact` nodes + fact relations + `has_fact` edges.
7. **Phase 5 — Ownership & retrieval targets**  
   `belongs_to` edges and `retrieval_target` flags.

**Notes:**

- Entities are typed by **domain type** (e.g., `Spell`, `Feat`, `Rule`, `MechanicFrame`) rather than a generic `entity` node.
- `RuleFact` nodes are distinct and do **not** require canonical IDs.

**Graph structure:**

```json
{
  "nodes": [
    {
      "id": "sf2e-playercore-001-050",
      "type": "document",
      "name": "PlayerCore 001-050"
    },
    {
      "id": "sf2e-playercore-001-050::section::Chapter 7 > Spells",
      "type": "section",
      "name": "Spells"
    },
    { "id": "block-42", "type": "chunk", "content_kind": "spell", "page": 42 },
    {
      "id": "canon:sf2e:spell:fireball",
      "type": "Spell",
      "name": "Fireball",
      "spell_rank": 3
    }
  ],
  "edges": [
    {
      "source": "sf2e-playercore-001-050",
      "target": "block-42",
      "relation": "contains"
    },
    {
      "source": "block-42",
      "target": "canon:sf2e:spell:fireball",
      "relation": "describes"
    },
    {
      "source": "canon:sf2e:spell:fireball",
      "target": "canon:sf2e:trait:fire",
      "relation": "has_trait"
    }
  ],
  "stats": {
    "node_counts": { "document": 1, "section": 12, "chunk": 450, "Spell": 85 },
    "edge_relation_counts": {
      "contains": 462,
      "describes": 120,
      "has_trait": 340
    }
  }
}
```

**Canonical ID format:**

```
canon:{ruleset}:{type}:{slug}

Examples:
  canon:sf2e:spell:fireball
  canon:sf2e:feat:quick-draw
  canon:sf2e:trait:fire
```

---

### Stage 6: Optional LLM Enrichment

**Module:** `llm_enrichment.py`

**Process (when enabled):**

#### Paragraph Enrichment (`--llm-pre-enrich`)

1. Find paragraphs matching config flags (e.g., "requires", "prerequisite")
2. LLM annotates with structured JSON:
   - Summary
   - Tags
   - Action economy
   - Prerequisites

#### Review Enrichment (`--llm-review`)

1. Review coalesced chunks
2. Extract key rules, action economy, prerequisites
3. Generate structured annotations

#### Evaluation Query Generation

1. Create test queries for each content kind
2. Generate hypothetical answers for RAG evaluation
3. Output: `evaluation_queries.json`

---

### Stage 7: Edge Discovery

**Module:** `scripts/discover_deterministic_edges.py`

**Input:** Enriched chunks  
**Output:** `*.edge_candidates.json`

**Process:**

#### Index Building (`discover_deterministic_edges_indexing.py`)

- **Table index:** "Table 1-1" → chunk IDs
- **Figure index:** "Figure 2-3" → chunk IDs
- **Chapter index:** "Chapter 3" → section/chunk IDs
- **Section index:** Section names → section/chunk IDs
- **Page index:** Page numbers → chunks on that page

#### Candidate Extraction (`discover_deterministic_edges_candidates.py`)

1. Apply reference patterns to each chunk:
   ```python
   REFERENCE_PATTERNS = [
       ("references_table", r"Table\s+(\d+[\-\.]\d+)"),
       ("references_figure", r"Figure\s+(\d+[\-\.]\d+)"),
       ("references_chapter", r"Chapter\s+(\d+)"),
       ("references_page", r"page\s+(\d+)"),
       ("defines_term", r"(\w+)\s+means\s+"),
   ]
   ```
2. Normalize extracted labels
3. Resolve against indices
4. Score and select best matches

#### Quality Gates (`discover_deterministic_edges_gates.py`)

- **Unresolved rate gate:** >35% of strict relations fail → warning
- **Suspect token gate:** Tokens with >40% non-alphabetic chars → OCR error
- **Near-duplicate gate:** Similar titles (edit distance ≤1) → OCR issue

Gates are soft by default (warn but continue); use `--hard-gates` to fail on violations.

---

### Stage 8: Output Writing

**Modules:** `pipeline_outputs.py`, `embedding_store.py`, `graph_store.py`

#### Disk Output (always written)

| File                               | Description                         |
| ---------------------------------- | ----------------------------------- |
| `{doc_id}.enriched.json`           | All enriched chunks                 |
| `{doc_id}.coalesced.json`          | Merged chunks for context           |
| `{doc_id}.graph.json`              | Graph structure (nodes + edges)     |
| `{doc_id}.evaluation_queries.json` | Test queries for RAG evaluation     |
| `{doc_id}.llm_review.json`         | LLM review annotations (if enabled) |
| `{doc_id}.edge_candidates.json`    | Deterministic edge candidates       |
| `merged.enriched.json`             | All documents merged                |
| `merged.graph.json`                | Cross-document graph                |

#### MongoDB Output (with `--store-mongodb`)

| Collection         | Description                                      |
| ------------------ | ------------------------------------------------ |
| `enriched_chunks`  | Chunk content and metadata                       |
| `chunk_embeddings` | Vector embeddings (with `--generate-embeddings`) |
| `graph_edges`      | Graph edge definitions                           |
| `graph_nodes`      | Graph node definitions                           |

**Example with MongoDB storage:**

```bash
uv run python ingest.py \
  --ruleset StarFinder2e \
  --book PlayerCore \
  --profile full \
  --store-mongodb \
  --generate-embeddings \
  --embedding-model nomic-embed-text-v2
```

---

## Data Transformations Summary

```
PDF File
  ↓ [Marker extraction]
Raw Marker Chunks (JSON)
  {id, block_type, html, page, section_hierarchy, bbox}
  ↓ [Config resolution]
RulesetConfiguration (from MongoDB or LLM-generated)
  ↓ [Deterministic enrichment]
EnrichedChunk[]
  {id, text, content_kind, tags, traits, spell_rank, traditions, spell_stats, is_rule_bearing}
  ↓ [Spell merging + coalescing]
Refined EnrichedChunk[]
  ↓ [Graph construction]
Graph {nodes: [], edges: [], stats: {}}
  ↓ [Edge discovery]
EdgeCandidates {source, relation, target, resolution_count}
  ↓ [Output writing]
{
  enriched.json,
  coalesced.json,
  graph.json,
  evaluation_queries.json,
  edge_candidates.json
}
```

---

## Run Tracking

**Module:** `pipeline_runs.py`

Pipeline runs are tracked in MongoDB:

```python
# Run record structure
{
  "run_id": "uuid-...",
  "ruleset_id": "sf2e-playercore",
  "config_version": "1.0.0",
  "source_fingerprint": "sha256:...",  # Hash of input
  "status": "succeeded",
  "started_at": "2026-01-27T10:00:00Z",
  "completed_at": "2026-01-27T10:05:00Z"
}
```

**Collections:**

- `enrichment_runs` - Run metadata
- `run_inputs` - Input snapshots (raw blocks + config)
- `run_outputs` - Output snapshots (enriched, graph, queries)

---

## Common Workflows

### Ingest a New Book

```bash
# 1. Place PDFs in source directory
mkdir -p Rules/StarFinder2e/NewBook/source
cp *.pdf Rules/StarFinder2e/NewBook/source/

# 2. Run full pipeline
uv run python ingest.py --ruleset StarFinder2e --book NewBook --profile full

# 3. Check outputs
ls Rules/StarFinder2e/NewBook/outputs/runs/*/enriched/
```

### Re-enrich with LLM Passes

```bash
uv run python ingest.py --ruleset StarFinder2e --book PlayerCore \
  --profile enrich-only \
  --llm-pre-enrich \
  --llm-review
```

### Run Evaluation Only

```bash
uv run python ingest.py --ruleset StarFinder2e --book PlayerCore --profile eval-only
```

### Regenerate Graphs from Existing Enriched

```bash
uv run python scripts/rebuild_graphs_from_enriched.py \
  --input-dir Rules/StarFinder2e/PlayerCore/outputs/runs/latest/enriched
```

---

## Related Documents

- [Architecture](ARCHITECTURE.md) - System overview and module map
- [Retrieval End-to-End](RETRIEVAL_END_TO_END.md) - How RulesLawyer uses ingested data
- [Cleanup Recommendations](CLEANUP_RECOMMENDATIONS.md) - Technical debt and improvements

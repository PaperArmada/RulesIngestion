# Cleanup Recommendations

**Last Updated:** 2026-01-27  
**Status:** Active Technical Debt Tracker

---

## Overview

This document catalogs technical debt, terminology issues, and improvement opportunities in the RulesIngestion system. Items are prioritized by impact and effort.

**Architectural Decision:** Embeddings and graphs will be stored in MongoDB, eliminating the manual file-based handoff between RulesIngestion and RulesLawyer.

---

## Critical: Terminology Fix

### The "Coverage" Problem

**Issue:** The term "coverage" is misleading throughout the codebase.

**What the code calculates:**
```python
# scoring_engine.py:292
coverage = (evaluated_queries / query_count) if query_count else 0.0
```

Where `evaluated_queries = query_count - missing_expected`, and a query is "missing" if its expected chunk IDs don't exist in the allowed set.

**What it actually measures:**
> Evaluability: The fraction of queries that CAN be evaluated because their expected (gold) chunk exists in the corpus and passes any filters.

**What documentation claims (INCORRECT):**
```python
# reporting.py:403
# "Coverage: fraction of evaluated queries whose gold chunk appears in top-k."
```

This is wrong. That metric is `hit@k`, not coverage.

**Confusing scenario:**
```json
{
  "coverage": 1.0,   // All queries CAN be evaluated
  "hit@1": 0.0,      // But retrieval found NONE of them!
  "hit@10": 0.0
}
```

This is valid but misleading. Coverage=1.0 sounds like success, but retrieval completely failed.

### Status: FIXED

The terminology has been fixed in:
- `evaluation/scoring_engine.py` - Added `evaluability` with backward-compatible `coverage` alias
- `evaluation/reporting.py` - Updated docstring and display labels
- `evaluation/benchmark/orchestrator.py` - Added `evaluability` to summary

**Remaining work:**
- Update handoff documents mentioning "coverage"
- Add warning when evaluability=1.0 but hit@k=0.0

---

## High Priority

### 1. MongoDB Storage for Embeddings and Graphs

**Decision:** Store embeddings and graphs in MongoDB instead of JSON files.

**Benefits:**
- Eliminates manual file-based handoff
- Enables query-time loading without filesystem access
- Supports versioning and rollback
- Allows partial updates (single chunk re-embedding)
- Enables cross-service sharing (RulesIngestion writes, RulesLawyer reads)

**MongoDB Collections:**

```javascript
// Chunk embeddings
db.chunk_embeddings: {
  _id: ObjectId,
  chunk_id: string,           // Reference to enriched chunk
  ruleset_id: string,         // e.g., "sf2e-playercore"
  book_id: string,            // e.g., "playercore"
  run_id: string,             // Pipeline run that generated this
  model_id: string,           // e.g., "nomic-embed-text-v2"
  embedding: array<float>,    // 1024-dim vector (or model-specific)
  created_at: datetime,
  metadata: {
    text_hash: string,        // SHA256 of chunk text for cache invalidation
    chunk_text_preview: string  // First 200 chars for debugging
  }
}

// Graph edges
db.graph_edges: {
  _id: ObjectId,
  source_id: string,          // Source node ID
  target_id: string,          // Target node ID
  relation: string,           // Edge type: contains, next, describes, etc.
  ruleset_id: string,
  book_id: string,
  run_id: string,
  metadata: object            // Edge-specific payload
}

// Graph nodes (optional - can derive from edges)
db.graph_nodes: {
  _id: ObjectId,
  node_id: string,            // Canonical node ID
  node_type: string,          // document, section, chunk, Spell, Feat, etc.
  ruleset_id: string,
  book_id: string,
  run_id: string,
  payload: object             // Node-specific data
}

// Traversal configs (per-ruleset game terms and policies)
db.traversal_configs: {
  _id: ObjectId,
  ruleset_id: string,         // e.g., "StarFinder2e"
  version: string,            // e.g., "v1"
  condition_names: array<string>,   // ["grabbed", "stunned", ...]
  spell_names: array<string>,       // ["fireball", ...]
  feat_names: array<string>,        // ["power attack", ...]
  item_names: array<string>,
  action_names: array<string>,
  player_keywords: array<string>,   // Document selection keywords
  gm_keywords: array<string>,
  intent_patterns: object,          // Regex patterns per intent
  policies: object,                 // Traversal policies per intent
  created_at: datetime,
  updated_at: datetime
}

// Traversal index metadata (rebuild info, not full index)
db.traversal_indexes: {
  _id: ObjectId,
  ruleset_id: string,
  book_id: string,
  run_id: string,
  stats: {
    total_chunks: int,
    total_edges: int,
    term_count: int,
    entity_count: int
  },
  created_at: datetime
}

// Indexes
db.chunk_embeddings.createIndex({ ruleset_id: 1, book_id: 1, model_id: 1 })
db.chunk_embeddings.createIndex({ chunk_id: 1, model_id: 1 }, { unique: true })
db.graph_edges.createIndex({ ruleset_id: 1, book_id: 1 })
db.graph_edges.createIndex({ source_id: 1 })
db.graph_edges.createIndex({ target_id: 1 })
db.traversal_configs.createIndex({ ruleset_id: 1, version: -1 }, { unique: true })
db.traversal_indexes.createIndex({ ruleset_id: 1, book_id: 1, run_id: 1 }, { unique: true })
```

**Implementation Steps:**

1. **Create storage module** - `embedding_store.py` and `graph_store.py`
2. **Add pipeline flag** - `--store-mongodb` to write to MongoDB after enrichment
3. **Update RulesLawyer loader** - Load from MongoDB instead of CSV/JSON files
4. **Add cache invalidation** - Re-embed only changed chunks (text hash comparison)
5. **Add versioning** - Support multiple embedding models per corpus

**RulesLawyer Loading Pattern:**
```python
class MongoEmbeddingLoader:
    def __init__(self, ruleset_id: str, book_id: str, model_id: str = "nomic-embed-text-v2"):
        self.db = get_mongo_client()
        
        # Load embeddings as numpy array
        cursor = self.db.chunk_embeddings.find({
            "ruleset_id": ruleset_id,
            "book_id": book_id,
            "model_id": model_id
        })
        
        chunks = list(cursor)
        self.chunk_ids = [c["chunk_id"] for c in chunks]
        self.embeddings = np.array([c["embedding"] for c in chunks])
        
        # Build graph adjacency from edges
        edges = self.db.graph_edges.find({
            "ruleset_id": ruleset_id,
            "book_id": book_id
        })
        self.graph_adjacency = self._build_adjacency(edges)
```

### 2. Consolidate Entry Points

**Issue:** Four entry points with unclear boundaries:
- `ingest.py` - Primary CLI (recommended)
- `rules_ingestion_pipeline.py` - Core logic
- `ingestion_service.py` - HTTP service
- `main.py` - Thin wrapper (adds no value)

**Recommendation:**
1. Deprecate `main.py` - Add deprecation warning, redirect to `ingest.py`
2. Document when to use HTTP service vs CLI
3. Update README with clear guidance

**Implementation:**
```python
# main.py
import warnings
warnings.warn(
    "main.py is deprecated. Use 'python ingest.py' instead.",
    DeprecationWarning
)
from rules_ingestion_pipeline import main
main()
```

### 3. Integrated Embedding Generation

**Issue:** Embeddings should be generated during ingestion, not as a separate step.

**Implementation:**
Add `--generate-embeddings` flag to `ingest.py`:
```python
parser.add_argument(
    "--generate-embeddings",
    action="store_true",
    help="Generate and store embeddings for enriched chunks"
)
parser.add_argument(
    "--embedding-model",
    default="nomic-embed-text-v2",
    help="Embedding model to use"
)

if args.generate_embeddings:
    from embedding_store import EmbeddingStore
    
    store = EmbeddingStore(mongo_uri)
    store.generate_and_store(
        chunks=enriched_chunks,
        ruleset_id=args.ruleset_id,
        book_id=args.book,
        run_id=run_id,
        model_id=args.embedding_model
    )
```

**Caching Logic:**
```python
def generate_and_store(self, chunks, ruleset_id, book_id, run_id, model_id):
    # Check existing embeddings
    existing = {
        doc["chunk_id"]: doc["metadata"]["text_hash"]
        for doc in self.db.chunk_embeddings.find({
            "ruleset_id": ruleset_id,
            "model_id": model_id
        }, {"chunk_id": 1, "metadata.text_hash": 1})
    }
    
    # Only embed changed chunks
    to_embed = []
    for chunk in chunks:
        text_hash = hashlib.sha256(chunk["text"].encode()).hexdigest()
        if chunk["id"] not in existing or existing[chunk["id"]] != text_hash:
            to_embed.append(chunk)
    
    if to_embed:
        model = SentenceTransformer(model_id)
        embeddings = model.encode([c["text"] for c in to_embed])
        # Store in MongoDB...
```

---

## Medium Priority

### 4. Improve Graph Edge Quality

**Issue:** Graph edges are "too local/weak" - neighbors are document-adjacent, not semantically related.

**Evidence (from handoffs):**
- Expanded gold deltas: ~0.004-0.007 MRR
- Most additions are `graph_depth_1` only
- Section expansion contributes nothing

**Recommendations:**
1. **Add cross-reference edges** - When text says "see Fireball spell", link to Fireball chunk
2. **Add semantic similarity edges** - Store edges for chunks with embedding similarity > threshold
3. **Entity co-occurrence at depth > 1** - Connect chunks mentioning same entities transitively
4. **Graph embeddings** - Use Node2Vec/GraphSAGE for reranking signal

**Semantic Edge Generation (with MongoDB):**
```python
def generate_semantic_edges(self, ruleset_id, book_id, model_id, threshold=0.85):
    """Create edges between semantically similar chunks."""
    # Load embeddings
    embeddings_cursor = self.db.chunk_embeddings.find({
        "ruleset_id": ruleset_id,
        "book_id": book_id,
        "model_id": model_id
    })
    
    chunks = list(embeddings_cursor)
    embeddings = np.array([c["embedding"] for c in chunks])
    chunk_ids = [c["chunk_id"] for c in chunks]
    
    # Compute pairwise similarities
    similarities = embeddings @ embeddings.T
    
    # Create edges for high-similarity pairs
    edges = []
    for i in range(len(chunk_ids)):
        for j in range(i + 1, len(chunk_ids)):
            if similarities[i, j] > threshold:
                edges.append({
                    "source_id": chunk_ids[i],
                    "target_id": chunk_ids[j],
                    "relation": "semantically_similar",
                    "ruleset_id": ruleset_id,
                    "book_id": book_id,
                    "metadata": {"similarity": float(similarities[i, j])}
                })
    
    self.db.graph_edges.insert_many(edges)
```

### 5. Config Generation Quality

**Issue:** LLM-generated configs have quality issues:
- High retry rates
- Structure drift detection but no auto-fix

**Recommendations:**
1. **Add validation pass** - Verify generated config against known-good examples
2. **Implement auto-fix** - When structure drift detected, regenerate affected sections
3. **Cache successful configs** - Reuse configs for same ruleset/edition (already done in MongoDB)

### 6. Add Troubleshooting Guide

**Issue:** Common errors and fixes not centralized.

**Create:** `Docs/TROUBLESHOOTING.md`

**Contents:**
- Gate failures and how to resolve
- MongoDB connection issues
- Marker extraction failures
- Config generation retries
- Graph construction warnings
- Embedding generation failures

---

## Low Priority

### 7. Test Coverage Improvement

**Issue:** Tests exist but no testing guide or coverage expectations.

**Recommendations:**
1. Add `Docs/TESTING.md` with:
   - How to run tests
   - How to add new tests
   - Coverage expectations
2. Add coverage reporting to CI

### 8. API Documentation

**Issue:** `ingestion_service.py` has no OpenAPI docs.

**Recommendation:** Add FastAPI metadata:
```python
app = FastAPI(
    title="RulesIngestion API",
    description="HTTP API for TTRPG rulebook ingestion",
    version="1.0.0",
)

@app.post("/ingest", response_model=JobResponse)
async def ingest(request: IngestRequest) -> JobResponse:
    """
    Queue a PDF or chunks JSON for processing.
    
    Returns a job ID that can be used to check status.
    """
    ...
```

### 9. Performance Optimization

**Issue:** Large books take significant time to process.

**Recommendations:**
1. **Batch embedding** - Embed chunks in batches with GPU acceleration
2. **Parallel MongoDB writes** - Use bulk operations
3. **Incremental processing** - Only process changed chunks

---

## Completed Items

### Documentation Consolidation

**Status: DONE**

- Added deprecation notices to superseded docs
- Created new canonical documentation:
  - `ARCHITECTURE.md`
  - `INGESTION_PIPELINE.md`
  - `RETRIEVAL_END_TO_END.md`
  - `CLEANUP_RECOMMENDATIONS.md`
- Updated README with new documentation structure

---

## Summary Table

| Priority | Item | Effort | Impact | Status |
|----------|------|--------|--------|--------|
| Critical | Fix "coverage" terminology | Low | High | DONE |
| High | MongoDB storage for embeddings/graphs | Medium | High | TODO |
| High | Consolidate entry points | Low | Medium | TODO |
| High | Integrated embedding generation | Medium | High | TODO |
| Medium | Improve graph edge quality | High | High | TODO |
| Medium | Config generation quality | Medium | Medium | TODO |
| Medium | Add troubleshooting guide | Low | Medium | TODO |
| Low | Test coverage improvement | Medium | Low | TODO |
| Low | API documentation | Low | Low | TODO |
| Low | Performance optimization | High | Medium | TODO |

---

## MongoDB Schema Summary

With the new architecture, MongoDB stores:

```
Existing Collections:
├── ruleset_configs      # Ruleset extraction configurations
├── ruleset_profiles     # Heading hierarchy, block types
├── enrichment_runs      # Run lifecycle records
├── run_inputs           # Input snapshots
└── run_outputs          # Output snapshots

New Collections:
├── chunk_embeddings     # Vector embeddings per chunk/model
├── graph_edges          # Graph edge definitions
└── graph_nodes          # Graph node definitions (optional)
```

**Data Flow:**
```
PDF → Marker → Enriched Chunks → MongoDB (chunks, embeddings, graphs)
                                      ↓
                              RulesLawyer loads from MongoDB
                                      ↓
                              Hybrid Retrieval → LLM Answer
```

---

## Lessons for Future Projects

If rebuilding from scratch:

1. **Choose terminology carefully** - "Evaluability" not "coverage"
2. **Database-first for artifacts** - Store in MongoDB, not files
3. **Embed during ingestion** - Don't separate embedding generation
4. **Single entry point** - One CLI, one service, no wrappers
5. **Graph-aware from start** - Design retrieval with graph in mind

However, **the current architecture is sound**:
- Determinism-first philosophy is correct
- Graph construction is well-designed
- Modular structure allows incremental improvement
- Evaluation metrics (once renamed) measure the right things
- MongoDB already used for configs/runs (extend to embeddings/graphs)

The bones are good. Focus on extending to MongoDB storage.

---

## Related Documents

- [Architecture](ARCHITECTURE.md) - System overview
- [Ingestion Pipeline](INGESTION_PIPELINE.md) - Pipeline stages
- [Retrieval End-to-End](RETRIEVAL_END_TO_END.md) - Retrieval flow

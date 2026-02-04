# RulesIngestion → Reasoning‑Based Traversal Alignment Handoff

## Purpose
This document is a **technical handoff** for the next agent working directly in the `RulesIngestion` codebase. It captures:
- The target architecture implied by recent research (frame‑based / reasoning‑based retrieval)
- How the current codebase already supports most of that architecture
- Concrete gaps
- Specific implementation patterns and file‑level integration points

This is **not** a research summary. It is an implementation‑oriented guide.

---

## High‑Level Goal

Evolve `RulesIngestion` from:
> “embedding‑filtered chunk retrieval”

into:
> **explicit, replayable traversal over a document frame graph, with embeddings and LLMs used only as scoring heuristics**.

This aligns with frame‑based document traversal architectures described in recent academic work (including arXiv:2601.03192) without rewriting the ingestion pipeline.

---

## Current Architecture (Ground Truth)

### Pipeline Shape

```
PDF / DOCX
 → Marker extraction
 → Deterministic enrichment
 → Graph construction
 → Optional LLM passes
 → Metrics + evaluation artifacts
```

Key invariants already enforced:
- Deterministic enrichment runs before any LLM pass
- Graph nodes reference chunk IDs (no text duplication)
- Ruleset configuration is versioned and persisted
- Metrics gates enforce coverage

This pipeline already behaves like a **compiler** rather than a traditional RAG ingest.

---

## Conceptual Mapping

| Paper / Target Concept | Current Code Concept |
|----------------------|---------------------|
| Frame | Enriched chunk / section |
| Frame graph | `*.graph.json` |
| Deterministic compilation | `enrichment.py` |
| Traversal policy | `RulesetConfiguration` |
| Reasoning step | (implicit today) |
| Traversal trace | (missing) |

The missing pieces are about **navigation and observability**, not extraction.

---

## File‑Level Analysis and Required Extensions

### 1. `enrichment.py`

#### Current role
- Classifies chunks by content kind
- Extracts deterministic metadata (tags, traits, spell stats)
- Produces stable enriched chunk objects

#### Required extension

Add **semantic edge emission** during enrichment.

Today, enrichment produces *nodes*. It must also produce *edges*.

##### Target edge types (initial set)
- `references` (paragraph → table / rule)
- `defines_term` (glossary → concept)
- `table_row_of` (row → table)
- `exception_to` (rule → base rule)
- `grants_ability` (feature → ability)
- `requires_level` (feature → level)

##### Output shape (example)
```json
{
  "edges": [
    {
      "from": "chunk_abc",
      "type": "references",
      "to": "chunk_xyz",
      "evidence": "see Table 3‑2"
    }
  ]
}
```

Rules:
- Edges reference chunk IDs only
- No text duplication
- Emit deterministically where possible

---

### 2. Graph Construction (`*.graph.json`)

#### Current role
- Encodes document → section → chunk hierarchy
- Includes `next` / `previous` ordering edges

#### Required extension

Promote the graph from **structural** to **semantic**:

- Merge enrichment‑emitted semantic edges into the graph
- Preserve edge typing
- Preserve evidence fields for debugging

The graph must become a **frame graph**, not just a reading order graph.

---

### 3. `config_generator.py` / Ruleset Configuration

#### Current role
- Generates ruleset configs
- Controls enrichment and evaluation behavior

#### Required extension

Treat the ruleset config as a **traversal policy**.

Add a traversal section:
```json
{
  "traversal": {
    "max_hops": 5,
    "preferred_edges": ["defines_term", "references"],
    "penalized_edges": ["next"],
    "allow_cycles": false
  }
}
```

This allows:
- Ruleset‑specific navigation behavior
- Versioned reasoning behavior
- Replayable traversal logic

---

### 4. Retrieval / Evaluation Layer

#### Current role
- Uses embeddings to select chapters and chunks
- Measures MRR / hit@k / coverage

#### Required extension

Introduce an explicit **Traversal Engine** abstraction.

##### Traversal Engine responsibilities
- Input: query, ruleset config, frame graph
- Output: traversal trace + supporting chunk IDs
- Behavior:
  - Select entry nodes (embeddings OK)
  - Traverse graph using edge scoring
  - Terminate on confidence or hop limit

##### Traversal trace artifact
```json
{
  "entry_nodes": ["section.combat"],
  "steps": [
    { "from": "section.combat", "edge": "references", "to": "rule.initiative" },
    { "from": "rule.initiative", "edge": "defines_term", "to": "table.initiative_order" }
  ],
  "supporting_chunks": ["chunk_123", "chunk_456"]
}
```

This trace must be persisted for:
- Debugging
- Replay
- Metrics

---

### 5. Evaluation Queries

#### Current role
- Generated from enriched chunks
- Used to measure retrieval quality

#### Required extension

Upgrade evaluation queries into **navigation tests**.

Add optional expectations:
```json
{
  "expected_entry_nodes": ["section.spells"],
  "expected_edges": ["defines_term", "table_row_of"],
  "expected_target_chunk": "spell.fireball"
}
```

New metrics to add:
- Average hop count
- Correct intermediate node rate
- Reference‑following accuracy

This complements MRR rather than replacing it.

---

## Explicit Non‑Goals

This work does **not**:
- Replace embeddings
- Replace Marker
- Require a new database
- Require online LLM usage
- Change ownership boundaries between services

Embeddings and LLMs remain **heuristics**, not authorities.

---

## Minimal Implementation Order

Recommended sequence for the next agent:

1. Add semantic edge extraction to `enrichment.py`
2. Extend graph schema to store typed edges
3. Add traversal config to ruleset configuration
4. Implement a minimal Traversal Engine (read‑only)
5. Persist traversal traces
6. Extend evaluation to assert traversal correctness

Each step is independently shippable.

---

## Philosophical and Architectural Rationale

This section captures the *reasoned justification* for moving toward explicit traversal and frame-based document reasoning, distilled from the referenced paper and related work. This is intended to explain **why** this direction is correct, not just how to implement it.

### 1. Vector similarity is not relevance

Embedding similarity optimizes for semantic closeness, not *procedural relevance*. In complex rulebooks:
- Many passages are semantically similar but operationally irrelevant
- Critical rules are often phrased generically ("unless otherwise stated")
- Tables, exceptions, and cross-references break semantic continuity

The paper’s core claim is that relevance is **path-dependent**: a rule matters because of *where you are* in the document and *what you are trying to resolve*, not because its wording is similar to a query.

Explicit traversal restores this dependency.

---

### 2. Documents are not flat text corpora

Rulebooks are authored as **navigable systems**, not bags of paragraphs:
- Sections define scope
- Tables compress meaning
- References encode intent ("see Chapter 8")
- Exceptions modify prior rules

The paper argues that treating documents as flat chunks discards authorial intent. A frame graph preserves:
- Hierarchy
- Cross-links
- Author-defined navigation paths

Traversal over this structure more closely mirrors how humans actually read and reason.

---

### 3. Reasoning must be replayable

LLM-driven navigation (as in prompt-only approaches) produces opaque reasoning:
- No clear intermediate state
- No audit trail
- No reproducibility

The paper emphasizes **explicit reasoning steps** over frames so that:
- Each decision can be inspected
- Paths can be replayed
- Failures can be diagnosed

This aligns with system-level requirements for debugging, evaluation, and long-term maintenance.

---

### 4. LLMs should assist, not govern

The paper’s stance is not anti-LLM, but **anti-implicit control**.

LLMs are well-suited to:
- Scoring candidate transitions
- Interpreting ambiguous references
- Ranking alternatives

They are poorly suited to:
- Defining document structure
- Inventing navigation paths
- Acting as the sole source of truth

By constraining LLMs to *scoring roles*, the system gains:
- Determinism
- Predictability
- Safety

---

### 5. Retrieval is a process, not a lookup

The central philosophical shift is this:

> Retrieval is not “find the best chunk.”
> Retrieval is “decide where to go next.”

The paper reframes retrieval as an **iterative decision process**:
- Choose an entry point
- Evaluate possible next steps
- Traverse until sufficient evidence is collected

This naturally produces:
- Better handling of long documents
- Fewer irrelevant chunks
- Clear stopping conditions

---

### 6. Alignment with RulesIngestion and the World Engine

This direction is compatible with the broader system philosophy already present in the codebase:
- Deterministic state before interpretation
- Clear separation between data and views
- Replayable processes
- Metrics-driven evaluation

Moving to explicit traversal does not introduce a new paradigm — it *completes* the existing one.

---

## End State

When complete:
- The document graph is a navigable frame graph
- Retrieval is an explicit traversal process
- Reasoning paths are inspectable and replayable
- Embeddings and LLMs assist but do not dominate
- The system aligns with frame‑based reasoning architectures without abandoning existing metrics or infrastructure

---

## Open Questions for the Next Agent

- Which semantic edge types provide the highest retrieval lift first?
- Where should traversal termination heuristics live (config vs engine)?
- How should traversal traces be indexed for later analysis?
- Should traversal be exposed as a public API or remain internal?

These are implementation decisions, not architectural blockers.


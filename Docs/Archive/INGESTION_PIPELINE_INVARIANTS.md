# Ingestion Pipeline Invariants

**Purpose:** Define the outcome this refactor phase achieved and how to measure it. Keeps authority separation and swap-cost explicit so future work doesn’t erode boundaries.

---

## Primary outcome (win condition)

**You can change how scope works without changing what entities exist, what they are called, or what facts exist.**

Scope is a replaceable derivation. Entity extraction, canonicalization, and fact attachment are not.

---

## How to measure that outcome

### 1. Scope is a replaceable derivation

- **Test:** Freeze a Phase 3 graph (entities + describes except header_scope). Run `apply_header_scope_describes` with heuristic A (current) and heuristic B (e.g. stricter inheritance).
- **Assert:** Same nodes; same non-header_scope edges; only describes edges with `extraction_method="header_scope"` differ.
- **If anything else changes:** Scope is still leaking authority.

### 2. Stop–resume determinism at the Phase 3 boundary

- **Test:** Run pipeline end-to-end → Graph A. Run pipeline to end of Phase 3 → serialize. Resume from serialized Phase 3 → Phase 3b → Phase 4+ → Graph B.
- **Assert:** Graph A == Graph B.
- **Meaning:** Phase 3 is authoritative; everything after it is projection-like (replayable).

### 3. Single-writer audit (authority separation)

For each of these, **exactly one pass** is allowed to set it:

| Field / Edge              | Allowed pass |
|---------------------------|--------------|
| `canonical_id`            | Phase 2      |
| `aliases`                 | Phase 2      |
| `entity_role`             | Phase 2      |
| `mechanic_kind`           | Phase 5      |
| `retrieval_target`        | Phase 5      |
| `belongs_to`              | Phase 5      |
| describes (header_scope)  | Phase 3b     |

**Measurement:** Temporary assertions or grep rules that fail if these fields are written elsewhere. Use as scaffolding; remove once discipline is habitual.

### 4. Swap-cost (future-proofing)

**Question:** “How many files / passes must change to try a different scoping heuristic?”

**Target:** One function: `apply_header_scope_describes`. Zero changes to entity extraction, canonicalization, registry, or fact logic.

If the answer creeps above that, the boundary has eroded.

### 5. Explainability per scope edge

For any describes edge with `extraction_method="header_scope"` you can say:

- Which header promoted the frame
- Why inheritance applied
- Why it stopped applying

Edges already carry `extraction_method`, `source_document`, `source_chunk_id`; use them for local audit.

---

## When this phase is “done”

All of the following are true:

1. **Phase 3** produces a graph you are willing to call authoritative ingestion state.
2. **Phase 3b** can be removed, replaced, or rewritten without touching Phase 1–3.
3. You can serialize after Phase 3 and resume later without semantic drift.
4. Tests fail loudly if someone re-introduces inline scope inference (e.g. scope logic inside the Phase 3 materialization loop).

---

## Pipeline shape (current)

- **Phase 0:** Structural seed (pure).
- **Phase 1:** Candidate extraction (pure).
- **Phase 2:** Canonicalization + alias resolution (pure → canonical IDs, aliases, entity_role).
- **Phase 3:** Graph materialization (apply deltas: entities, describes/mentioned_in/has_*, relation_mentions).
- **Phase 3b:** Scope-based describes (`apply_header_scope_describes` — header_scope only).
- **Phase 4+:** Facts, ownership, relations, polish.

The graph is an **output**, not a working scratchpad. Same philosophy as the world engine: authoritative facts first, named derivations after, replayable decisions only.

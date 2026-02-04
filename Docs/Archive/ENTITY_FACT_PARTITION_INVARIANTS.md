# Entity–Fact Partition Invariants

**Purpose:** Define the partition between **entities** (canonical objects) and **facts** (assertion nodes) so validation, traversal, and metrics treat each kind correctly. Until this partition is enforced, "missing canonical_id for N entity nodes" is a terminology collision: the validator is technically correct, the model is semantically correct, and the vocabulary is lying.

**Related:** `INGESTION_PIPELINE_INVARIANTS.md` (phase authority); graph builder `_validate_graph`, `build_fact_graph`.

---

## Primary outcome (win condition)

**Facts are not entities, and the graph enforces that distinction structurally and semantically.**

- Entity nodes are canonical referents (Spell, Feat, chunk, document, etc.); they participate in alias resolution and `canonical_id`.
- Fact nodes are assertions (RuleFact); they are owned by chunks and entities, never the other way around, and they do **not** require `canonical_id`.

When this is true: validation stops flagging fact nodes as "missing canonical_id"; traversal can gate by node kind; semantic purity can be computed per layer; benchmark metrics become interpretable.

---

## Node-kind partition

**Entity-ness is an explicit kind, not a derived property.** No node is an entity by default. A node is an entity only if it is classified as such by the partition (e.g. via `node_type` → kind mapping). "Anything that isn't structural or fact" must not be treated as entity by default—the kind must be explicit so the partition cannot drift.

### 1. Structural nodes

| `node_type` | Meaning | canonical_id | In alias map? | header_scope target? |
|-------------|---------|--------------|----------------|---------------------|
| `document`  | Root doc | No | No | No |
| `section`   | Section in doc | No | No | No |
| `chunk`     | Content chunk | No (chunk id is structural) | No | No |

**Invariants:**

- Structural nodes are created in Phase 0 only.
- They are not entities in the canonical sense; they are containers.
- Validation MUST NOT require `canonical_id` for these.

---

### 2. Entity nodes (canonical objects)

**Types (current):** `MechanicFrame`, `Spell`, `Feat`, `Rule`, `Action`, `Ability`, plus any other type emitted by Phase 1–3 that represents a **referent** (e.g. trait, tradition, tag as first-class nodes).

**Semantics:** An entity is a thing the rules refer to—a spell name, a feat, a mechanic frame—that can have aliases, be mentioned in chunks, and own or be linked to facts.

**Invariants:**

- MUST have `canonical_id` (or an `id` that is already a canonical id).
- MAY have `aliases`, `entity_role`, `source_documents`, `source_chunk_ids`.
- MAY be the **target** of `describes` (including `extraction_method="header_scope"`).
- MAY be the **source** of `has_fact`, `belongs_to`, and semantic relation edges.
- Entity nodes are the **only** nodes that participate in alias maps and canonicalization (Phase 2).

**Validation:** Any node that is **not** structural and **not** a fact MUST have `canonical_id` (or equivalent). If the graph has a `NodeKind` (or equivalent), "entity" kinds are the only ones for which `canonical_id` is required.

---

### 3. Fact nodes (assertion nodes)

**Type (current):** `RuleFact`.

**Semantics:** A fact is an atomic claim extracted from text (e.g. "When you Cast a Spell, you make a spell attack roll"). It is **about** entities and chunks; it is not a referent. It has a stable `fact_id` but no canonical identity in the same sense as "Fireball" or "Stride."

**Invariants:**

- MUST NOT require `canonical_id`. Fact identity is local and contextual (fact_id + provenance), not global or canonical.
- MUST NOT participate in alias maps (no name-key → fact_id resolution for canonical lookup).
- MUST NOT be the **target** of `describes` with `extraction_method="header_scope"` (scope applies to entities, not facts).
- MUST be **owned** by a chunk (via `has_fact`) and optionally by an entity (e.g. `belongs_to`); facts are never owners of entities.
- MUST NOT be the **source** of semantic relations between entities (e.g. requires, modifies, replaces_effect); facts participate only as assertions, not as semantic hubs.
- MAY have provenance: `source_document`, `source_chunk_id`, `clause_id`, `extraction_method`.

**Validation:** Fact nodes MUST be excluded from the "missing canonical_id" check. The validator should treat `node_type == "RuleFact"` (or whatever the canonical fact kind is) as non-entity.

**Traversal:** Traversal that reasons about "entities" (e.g. structural_coreference, entity_to_chunks) MUST NOT treat fact nodes as entities. Edges can be gated by node kind so that entity → fact → chunk → entity is explicit and purity is computed per layer.

---

## Derived predicate: `is_entity_like`

Define a single helper used by traversal and metrics (not a node kind—a derived predicate):

**Definition:** `is_entity_like(node)` → true only for entity nodes (not structural, not fact).

**Require that** all of the following operate exclusively on nodes for which `is_entity_like(node)` is true:

- Entity counts
- Alias maps (read and write)
- Entity-to-entity traversal purity
- Semantic adjacency scoring

**Why this helps:**

- Centralizes the partition logic in one place; call sites use the predicate instead of re-deriving "is this an entity?"
- Prevents future code from silently reintroducing "everything non-structural is an entity."
- Keeps `node_type` expressive (Spell, Feat, etc.) without coupling validation or metrics to string comparisons.

Implement as a thin wrapper over the `node_type` → kind mapping (or over `node_kind` if that field is added).

---

## Current vs target state

| Concern | Current state | Target state |
|---------|---------------|--------------|
| Validator | Flags any non-structural node without `canonical_id` → RuleFact nodes trigger "missing canonical_id for N entity nodes" | Validator requires `canonical_id` only for **entity** kinds; fact (and structural) kinds excluded |
| Vocabulary | "Entity" used loosely for "non-structural node" | "Entity" = canonical object; "Fact" = assertion node; both are node **kinds** |
| Traversal | entity → fact → chunk → entity mixed; purity can penalize correct structure | Gate by node kind; semantic purity per layer; facts excluded from entity-count metrics |
| Benchmark | Throughput on a noisy graph; recall/purity conflate entities and facts | Recall@K and purity interpretable; causal coverage stable; facts not counted as entities |

---

## How to measure that the partition is enforced

### 1. Node-kind partition invariants

- **Test:** After `build_fact_graph`, run validation. Assert: zero "missing canonical_id" **violations** (fact nodes must be excluded from the check, not flagged).
- **Test:** Assert every node has a well-defined kind: structural, entity, or fact. No node is "entity" by default just because it isn’t structural.
- **Assert:** Nodes with `node_type == "RuleFact"` (or equivalent) are never in the set of nodes that require `canonical_id`.

### 2. Traversal and ownership

- **Assert:** Every `has_fact` edge is chunk → fact (chunk owns fact). No fact → entity ownership.
- **Assert:** `describes` with `extraction_method="header_scope"` has an **entity** as target, never a fact.
- **Assert:** Alias maps and name-key → id indices contain only entity ids, never fact ids.

### 3. Benchmark honesty

- **Assert:** Semantic-purity (and any "entity count") metrics exclude fact nodes from the entity set.
- **Assert:** Recall@K and causal coverage are defined over the intended partition (e.g. facts as assertions, entities as referents) so that improvements in structure don’t show up as purity regressions.

---

## Implementation checklist (for NodeKind + validator update)

- [ ] Introduce a **node kind** (e.g. `NodeKind` enum or constant set): `structural` | `entity` | `fact`.
- [ ] Map `node_type` → kind: `document`/`section`/`chunk` → structural; `RuleFact` → fact; everything else (MechanicFrame, Spell, …) → entity.
- [ ] Change `_validate_graph`: require `canonical_id` only for nodes with kind **entity**. Do not flag structural or fact nodes.
- [ ] Optional: add an explicit `node_kind` field on nodes at build time so validation and traversal don’t depend on ad-hoc type lists.
- [ ] Update any "entity count" or purity logic to exclude fact (and optionally structural) nodes from the entity set.
- [ ] Implement `is_entity_like(node)` and use it for entity counts, alias-map access, traversal purity, and semantic adjacency; do not re-derive "is entity?" elsewhere.

---

## Summary

| Kind       | Examples        | canonical_id | Alias map | header_scope target | Owned by        |
|------------|------------------|--------------|-----------|---------------------|-----------------|
| Structural | document, section, chunk | No  | No        | No                  | —               |
| Entity     | Spell, Feat, MechanicFrame, … | Yes | Yes       | Yes                 | chunk (describes) |
| Fact       | RuleFact         | No           | No        | No                  | chunk (has_fact), entity (belongs_to) |

**Facts are not entities.** The graph and validator must enforce this so that metrics and traversal are honest.

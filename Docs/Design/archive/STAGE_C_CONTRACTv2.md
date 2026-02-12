> **Archived.** Superseded by [Docs/Design/v1/](v1/). Kept for reference.
---

# Stage C Contract — Semantic Grounding & Canonicalization

**Status:** Draft (Intended Canonical)

**Purpose**  
Stage C is the deterministic grounding and canonicalization stage of the Rules Ingestion pipeline. Its role is to transform retrieved and normalized EvidenceUnits into a stable, auditable semantic graph that is _admissible for reasoning_, without introducing inference, synthesis, or probabilistic judgment.

Stage C exists to solve a specific class of failures observed in benchmarking:

- truncated deltas ("increase by X" without base rule),
- orphaned procedure steps,
- authority dilution via examples/sidebars,
- negative-space rules answered without explicit permission,
- gold chunk sets that appear relevant but are not epistemically sufficient.

Stage C does **not** improve recall. It enforces legitimacy.

---

## Scope and Non‑Goals

### In Scope

- Deterministic semantic lifting from EvidenceUnits
- Canonical entity and fact creation
- Structural scoping and authority enforcement
- Emission of a minimal, typed semantic graph (GraphDelta)
- Diagnostics required to explain grounding success or refusal

### Explicit Non‑Goals

- No LLM calls
- No paraphrasing or summarization
- No inferred rules or implied mechanics
- No traversal, ranking, or retrieval modification
- No probabilistic scoring or weighting

Violating a non‑goal invalidates Stage C.

---

## Inputs

Stage C consumes **only** EvidenceUnits produced by Stage B.

Each EvidenceUnit MUST contain:

- `verbatim_text`
- `structural_path` (document → section → subsection)
- `ordering_key`
- `source_document`
- `page_range`
- `unit_type` (core_text, example, sidebar, table, variant, etc.)
- `quality_flags`

Stage C must never consume raw OCR text or retrieval rankings.

---

## Outputs

Stage C produces:

1. **GraphDelta** (append‑only)
2. **Entity Index** (canonical referents)
3. **Fact Index** (assertion nodes)
4. **Diagnostics** (grounding eligibility metadata)

All outputs MUST be reproducible given identical inputs and Stage C version.

---

## Global Invariants (Hard Requirements)

1. **Evidence Pointer Completeness**  
   Every entity and fact MUST reference ≥1 EvidenceUnit.

2. **Entity–Fact Partition**  
   Entities are canonical referents. Facts are assertions. A node may never be both.

3. **No Silent Inference**  
   If a rule is not explicitly stated, it may not appear as a fact.

4. **Canonical Stability**  
   Same EvidenceUnits + same Stage C version ⇒ identical IDs and graph.

5. **Authority Preservation**  
   Lower‑authority text may never override higher‑authority text.

Any violation is a blocking failure.

---

## Processing Model (Compiler‑Style Passes)

### Pass 0 — Run Envelope

- Record upstream hashes (Stage A/B)
- Record retrieval mode and config (dense, hybrid, expand_context, etc.)
- Emit immutable run metadata

---

### Pass 1 — Evidence Normalization

Purpose: enable deterministic matching, not interpretation.

Actions:

- Normalize whitespace/punctuation for internal matching only
- Compute:
  - `evidence_fingerprint = hash(text + provenance + structural_path)`
  - `evidence_scope_key = hash(document + section_prefix)`

Verbatim text remains unchanged.

---

### Pass 2 — Structural Nodes

Purpose: prevent orphan semantics.

Create:

- Document nodes
- Section nodes (from structural_path)

Edges:

- `CONTAINS(section → evidence)`
- `NEXT_EVIDENCE(evidence → evidence)` (within section)

No semantics are introduced here.

---

### Pass 3 — Candidate Extraction (Bounded)

#### 3A — Entity Candidates

Extract **explicitly named** referents only:

- spells, feats, actions, conditions, traits, procedures, items, class features

Rules:

- Canonical label = surface form as printed
- No synonym inference
- No cross‑book resolution

Entity ID:

```
entity_id = hash(book_id + entity_type + canonical_label)
```

**R4: Entity Disambiguation (Structural Path Scoping)**

To avoid collisions when the same name appears in multiple sections (e.g. "Rage" as class feature vs. condition):

- Include `structural_path` prefix in the entity ID when the entity is section-scoped:
  ```
  entity_id = hash(book_id + entity_type + canonical_label + "|" + structural_path_prefix)
  ```
- Use a configurable depth (e.g. 2) for the structural path prefix (Chapter > Section).
- Cross-document resolution is deferred (see Cross-Document Entity Resolution below).

Each entity MUST store evidence references and scope.

---

#### 3B — Fact Candidates

Extract only rule‑shaped statements with explicit language:

- permissions ("you can")
- prohibitions ("you can’t")
- modifiers ("increase by", "reduce by")
- timing ("at the start of")
- definitions
- procedure steps
- frequency limits

Each fact includes:

- `fact_type`
- `subject` (entity or procedure placeholder)
- `predicate` (from controlled vocabulary)
- `object` (structured only if explicit)
- `constraints` (only if explicit)
- `evidence_refs`

If interpretation is required, store verbatim spans instead of structure.

---

### Pass 4 — Canonicalization & Deduplication

Deterministic merging only:

- Entities: same type + same label ⇒ same ID
- Facts: identical `(type, subject, predicate, object, constraints)` ⇒ same ID

Fact ID:

```
fact_id = hash(book_id + signature)
```

Evidence references are unioned and sorted.

---

### Pass 5 — Partition & Validity Gate (Hard Fail)

Reject output if:

- any node is both entity and fact
- any entity or fact lacks evidence
- edges reference missing nodes

This gate is non‑negotiable.

---

### Pass 6 — Edge Construction

**R4: Complete Edge Type Vocabulary**

Allowed semantic edges:

| Edge            | From     | To                  | Definition                             | Extraction Rule                               |
| --------------- | -------- | ------------------- | -------------------------------------- | --------------------------------------------- |
| `MENTIONS`      | evidence | entity              | EvidenceUnit references an entity      | Surface form in verbatim text                 |
| `ASSERTS`       | evidence | fact                | EvidenceUnit asserts a fact            | Rule-shaped statement                         |
| `ABOUT`         | fact     | entity              | Fact concerns an entity                | Subject of the fact                           |
| `APPLIES_UNDER` | fact     | procedure/condition | Fact applies under procedure/condition | "Under X", "When Y" explicit                  |
| `OVERRIDES`     | fact     | fact/procedure      | Fact overrides another                 | "Instead of", "Replaces" explicit             |
| `REQUIRES`      | fact     | fact/entity         | Fact requires another fact or entity   | "Requires", "Prerequisite" explicit           |
| `MODIFIES`      | fact     | fact/entity         | Fact modifies another                  | "Increase by", "Reduce by", "Modify" explicit |
| `SUPERSEDES`    | fact     | fact                | Fact supersedes an older rule          | "Supersedes", "Replaces" explicit             |

**Extraction Rules:**

- `REQUIRES`: Extract when verbatim text contains "requires", "prerequisite", "must have".
- `MODIFIES`: Extract when verbatim text contains "increase by", "reduce by", "modify", "adjust".
- `SUPERSEDES`: Extract when verbatim text contains "supersedes", "replaces [earlier rule]", "instead of [previous]".

**Test Cases:**

- REQUIRES: "You must have the Rage class feature" → REQUIRES(fact, entity:Rage)
- MODIFIES: "Increase damage by 2" → MODIFIES(fact, base_fact)
- SUPERSEDES: "This supersedes the rule on page 45" → SUPERSEDES(fact, fact)

No heuristic or similarity edges are permitted.

---

## Admissibility Gates (Critical)

### 1. Scalar‑Delta Completeness Gate

If a fact modifies a value but lacks its base rule:

- mark `requires_parent = true`
- attach `PARENT_REQUIRED(section/procedure)`

---

### 2. Procedure‑Step Orphan Gate

If a procedure step lacks its parent procedure:

- mark `orphan_step = true`

---

### 3. Authority Tier Gate

Facts from `example`, `sidebar`, or `variant` units are tagged:

- `authority = illustrative`

They are ineligible for normative grounding.

---

### 4. Trait Closure Gate

If a trait is referenced without a definition fact in scope:

- mark `definition_missing = true`

---

## GraphDelta Format

Append‑only, audit‑friendly:

- `meta`: run metadata and hashes
- `nodes_add`: entities, facts, structural nodes
- `edges_add`: typed edges
- `nodes_remove` / `edges_remove` (optional incremental support)

Every semantic node MUST be traceable to evidence.

---

## Diagnostics (Required)

Stage C MUST emit counts for:

- orphaned procedure steps
- scalar deltas missing parents
- illustrative‑authority facts
- missing trait definitions

These metrics explain retrieval behavior without changing retrieval.

---

## Determinism Tests (Acceptance)

1. Reordering EvidenceUnits does not change output
2. Same inputs produce identical IDs
3. No fact exists without evidence
4. Gold audit lints flag insufficient gold deterministically

---

---

## R4: Graph Query Model (Answer Synthesis)

How answer synthesis consumes the graph:

1. **Query → Entity/Fact Lookup**  
   Map user question to canonical entities and fact types (via retrieval + Stage A′ topic_tags, lexical_anchors).

2. **Traversal**

   - Start from MENTIONS(evidence, entity) and ASSERTS(evidence, fact).
   - Follow REQUIRES, MODIFIES, SUPERSEDES for prerequisite and exception chains.
   - Respect APPLIES_UNDER for conditional applicability.

3. **Answer Assembly**

   - Facts in scope are ordered by structural_path and ordering_key.
   - OVERRIDES and SUPERSEDES determine precedence when conflicts exist.

4. **Evidence Citation**  
   Every fact and entity in the answer MUST reference ≥1 EvidenceUnit.

---

## R4: Cross-Document Entity Resolution

**Rules:**

- Within a single document: entity disambiguation uses structural_path scoping (see Entity ID above).
- Across documents: no automatic resolution. Same surface form in different books are distinct entities.
- Explicit cross-reference (e.g. "as defined in Core Rulebook p.123") MAY create a link edge; extraction requires explicit phrasing.

**Future:** Cross-document resolution would require a separate pass and documented merge policy.

---

## Principle

**Traversal finds possibilities.  
Stage C decides legitimacy.**

If a rule cannot be grounded explicitly, the system must refuse — not guess.

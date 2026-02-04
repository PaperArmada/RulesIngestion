# Canonical Document Skeleton (CDS)

## Purpose
Represent the authoritative structure of a rulebook as a frozen, deterministic projection used exclusively for grounding constraints.

The CDS never participates in traversal or reasoning.

---

## Structure Model

```text
Document
 ├─ Chapter*
 │   ├─ Section*
 │   │   ├─ Subsection*
 │   │   │   └─ Chunk*
```

Each node has:
- title
- ordinal_index
- page_range
- role (chapter-level)
- summary (machine or publisher)
- term_distribution

---

## Structural Facts

```text
contains(parent, child)
precedes(node_a, node_b)
structural_address(chunk_id → section_path)
```

These facts are immutable and deterministic.

---

## Term Distributions

For each section:
- normalized tokens
- stemmed
- frequency-weighted
- header terms weighted > body terms

Used only for grounding eligibility scoring.

---

## Summary Alignment

Each section summary is treated as a semantic anchor.

Grounding prefers chunks whose claims align with their parent summary.

Contradiction between chunk and summary lowers admissibility.

---

## Invariants
- CDS is built once at ingestion
- CDS never changes post-build
- CDS is query-independent
- CDS does not introduce new entities

---

## Failure Modes
If CDS signals exclude all candidates:
- return refusal with explanation
- never relax CDS constraints implicitly

---

## Principle
Structure is authority. Prose is evidence.


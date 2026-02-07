> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# Grounding Pipeline with Pedagogical Signals

## Pipeline Stages (Locked)

1. Query → Candidate Retrieval (recall only)
2. Entity Seeding (query-driven)
3. ENTITY_ONLY Traversal (Variant A)
4. Candidate Chunk Set
5. **Pedagogical Admissibility Filtering**
6. **Authorial Weight Scoring**
7. Explanation Selection

Stages 1–4 are unchanged by this proposal.

---

## Stage 5: Admissibility Filtering

Reject candidate chunks that violate:
- dependency ancestry
- layout authority constraints
- chapter role hierarchy
- negative space constraints
- explicit deferrals

Filtering is binary and deterministic.

---

## Stage 6: Authorial Weight Scoring

Remaining candidates are ranked using:
- voice priority
- example density damping
- summary alignment
- axiomatic preference

No learned weights. Fixed scalar multipliers only.

---

## Refusal Semantics

If no admissible candidates remain:
- Return refusal
- Surface violated constraints

Refusal is preferable to hallucination.

---

## Observability

For each answer, emit:
- admissibility decisions
- signals applied
- reasons for exclusion

---

## Invariants
- Traversal unchanged
- No new facts introduced
- Deterministic ordering

---

## Principle
Recall answers *what could be relevant*.
Pedagogy answers *what is allowed to be true*.


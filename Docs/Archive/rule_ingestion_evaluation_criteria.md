# Rule Ingestion Evaluation Criteria

## Purpose

This document defines **how success and failure are measured** for the rule ingestion pipeline.

It exists to:
- Prevent self-deception
- Enable fast iteration with hard stop conditions
- Decouple progress from demo quality or LLM fluency

If a pipeline iteration cannot be evaluated against these criteria, it is incomplete.

---

## Evaluation Principles

1. **Determinism over eloquence**
2. **Traceability over compression**
3. **Explicit failure over silent success**
4. **Compiler feasibility over chat correctness**

Anything that optimizes against a different set of values is out of scope.

---

## Stage-by-Stage Success Criteria

### Stage A — Structural Ingestion

**Objective:** Preserve source structure and provenance.

**Success Metrics**
- ≥ 99% of document text captured
- Stable block boundaries across repeated runs
- Page, section, and offset metadata present for every block

**Failure Conditions**
- Missing or reordered content
- Tables split or merged incorrectly
- Loss of positional metadata

**Explicitly Not Measured**
- Semantic correctness
- Rule understanding

---

### Stage B — Rule Unit Extraction

**Objective:** Identify candidate rule-bearing text without interpretation.

**Success Metrics**
- Coverage: ≥ X% of rule-bearing blocks assigned to a RuleUnit
- Precision: ≤ Y% of non-rule text misclassified as rules
- Deterministic grouping for identical inputs

**Failure Conditions**
- Mixed, unrelated rules in a single unit
- Silent omission of obvious rules
- Non-deterministic unit boundaries

**Explicitly Not Measured**
- Correctness of rule meaning
- Completeness of decomposition

---

### Stage C — Typed Rule Decomposition

**Objective:** Make rule claims explicit and typed.

**Success Metrics**
- ≥ X% of RuleUnits decomposed into ≥ 1 RuleFragment
- Fragment type distribution matches expected domain patterns
- All extracted fields reference source blocks

**Failure Conditions**
- Implicit assumptions inserted by the system
- Missing qualifiers (scope, duration, target)
- Ambiguity collapsed into a single interpretation

**Explicitly Not Measured**
- Runtime execution behavior
- Optimal ordering or precedence

---

### Stage D — Rule Graph Construction

**Objective:** Expose dependencies and effects as an inspectable graph.

**Success Metrics**
- 0 unlinked fragments without explanation
- Bounded graph depth for individual rules
- Rule footprint derivable for ≥ X% of rules

**Failure Conditions**
- Hidden or implicit dependencies
- Cycles without semantic justification
- Graph nodes that cannot be mapped to engine concepts

**Explicitly Not Measured**
- Query performance
- Visualization quality

---

### Stage E — Compiler Feasibility Gate

**Objective:** Determine if rules can compile into deterministic execution.

**Success Metrics**
- ≥ X% of core rules return status = OK
- All non-OK rules include explicit, localized reasons
- No rule compiles with unbounded reads or writes

**Failure Conditions**
- Guessing missing semantics to force compilation
- Partial compilation without surfaced warnings
- Runtime-only discovery of invalid rules

---

## Cross-Cutting Metrics

### Traceability
- Every fragment links to source blocks
- Every graph edge is explainable
- Every compiled artifact cites its origin

### Boundedness
- Maximum state reads per rule known in advance
- No dynamic graph traversal at runtime

### Retrieval Health (Post-Ingestion)
- **Traversal coverage is correct** (eligible set contains required sources)
- **Edge precision is high** (eligibility excludes unrelated sections)
- **Recall improves monotonically** as context size increases
- **Answer quality does not regress** when adding eligible context

If adding context makes answers worse, traversal has already failed.
Not embeddings. Not the LLM. Traversal.

### Human Intervention Cost
- Number of manual corrections per rulebook
- Time to resolve ambiguity hotspots

---

## Metrics Explicitly Rejected

The following metrics are **not valid indicators of success**:

- BLEU / ROUGE scores
- LLM confidence or verbosity
- "Looks right" demos
- Chat response quality without traceability
- End-to-end latency without correctness guarantees

If a result can only be justified qualitatively, it fails evaluation.

---

## Failure Is a Valid Outcome

A pipeline iteration that:
- Rejects rules
- Flags ambiguity
- Produces non-compilable artifacts

is often **more successful** than one that silently proceeds.

Fast failure is progress.

---

## Why This Document Exists

This document exists to ensure that:

- Tooling experiments remain honest
- Progress is measurable
- Determinism is never negotiated away

If an experiment cannot be evaluated using these criteria, it should not be run.


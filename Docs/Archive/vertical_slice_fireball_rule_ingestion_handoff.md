# Vertical Slice Handoff — Fireball Rule Ingestion

## Purpose of This Handoff

You are a **fresh agent** tasked with building a **vertical slice of the Rule Ingestion Pipeline** using a single iconic rule: **Fireball**.

This is not a demo.
This is not a prototype for UI polish.

This is a **truth-finding exercise** meant to validate whether the ingestion pipeline can:

- Consume unstructured rules text
- Produce inspectable, deterministic artifacts
- Feed both a future **rules engine** and a rebuilt **RulesLawyer**

Fireball is chosen because it is:
- Mechanically dense
- Widely referenced
- Concrete but non-trivial

If Fireball cannot be ingested honestly, the pipeline is not real.

---

## Scope (What You Are Building)

You will implement an **end-to-end vertical slice** covering:

1. Structural ingestion of Fireball from a rulebook PDF
2. Rule Unit extraction
3. Typed Rule Fragment decomposition
4. Rule graph construction
5. Compiler feasibility assessment
6. RulesLawyer-style query answering backed by ingestion artifacts

You are not expected to generalize.
You are expected to be precise.

---

## Non-Negotiable Constraints

You must adhere to the following constraints at all times:

- ❌ No runtime LLM decision-making
- ❌ No silent ambiguity resolution
- ❌ No end-to-end "just answer the question" prompting
- ❌ No skipping pipeline stages

LLMs may assist with *extraction*, never *execution*.

---

## Input Materials

You are provided with:

- One or more TTRPG PDFs containing the Fireball spell
- A working Docling setup for structural parsing
- Reference documents:
  - `RULE_INGESTION_PHILOSOPHY.md`
  - `RULE_INGESTION_PIPELINE_OVERVIEW.md`
  - `RULE_INGESTION_EVALUATION_CRITERIA.md`

Assume no prior semantic knowledge of the ruleset.

---

## Step-by-Step Instructions

### Step 1 — Structural Ingestion (Stage A)

**Goal:** Extract Fireball text with full provenance.

Actions:
- Run the PDF through Docling
- Locate all Fireball-related blocks
- Record:
  - Section titles
  - Paragraph text
  - Tables
  - Page numbers

Deliverable:
- A list of structural blocks that fully contain Fireball

Assessment:
- No Fireball-related text missing
- Block boundaries stable across runs

---

### Step 2 — Rule Unit Extraction (Stage B)

**Goal:** Identify candidate rule-bearing units.

Actions:
- Group Fireball blocks into **RuleUnits**
- Expect multiple units (do not force one)
- Assign each unit a `kind`

Example RuleUnits:
- Fireball — Primary Effect
- Fireball — Components / Costs
- Fireball — Scaling
- Fireball — Metadata

Deliverable:
```
RuleUnit {
  id
  source_block_ids[]
  kind
  raw_text
}
```

Assessment:
- All mechanical text captured
- No interpretation added
- Units reproducible

---

### Step 3 — Typed Rule Decomposition (Stage C)

**Goal:** Make rule claims explicit.

Actions:
- For each RuleUnit, extract **RuleFragments**
- Use typed fragments only:
  - Precondition
  - Cost
  - Effect
  - Constraint
  - Selector

Important:
- Preserve ambiguity
- Flag underspecified behavior

Deliverable:
```
RuleFragment {
  rule_id
  fragment_type
  subject
  predicate
  object
  qualifiers[]
  source_block_ids[]
}
```

Assessment:
- Fragments map cleanly to engine concepts
- Every fragment traceable to source text
- No invented semantics

---

### Step 4 — Rule Graph Construction (Stage D)

**Goal:** Connect fragments into a typed dependency graph.

Actions:
- Create nodes for:
  - Fireball rule
  - Fragments
  - Entities (Caster, Creature, Object)
  - Resources (SpellSlot)
- Create typed edges:
  - REQUIRES
  - CONSUMES
  - MODIFIES
  - PRODUCES
  - REFERENCES

Deliverable:
- A graph representation (diagram or serialized form)

Assessment:
- No orphan fragments
- Dependencies explicit
- Graph readable without prose explanation

---

### Step 5 — Compiler Feasibility Gate (Stage E)

**Goal:** Determine if Fireball can compile deterministically.

Actions:
- Evaluate the graph against feasibility checks:
  - Bounded reads/writes
  - Explicit costs
  - Explicit effects
  - Derivable ordering

Deliverable:
```
CompilationReport {
  rule_id: "fireball"
  status: OK | NeedsHuman | Impossible
  reasons[]
}
```

Assessment:
- Failure is acceptable
- Reasons must be local and specific

---

### Step 6 — RulesLawyer Vertical Slice

**Goal:** Answer Fireball questions *only* using ingestion artifacts.

Actions:
- Implement 2–3 sample queries, e.g.:
  - "Does Fireball require a spell slot?"
  - "What happens on a successful save?"
  - "Does Fireball ignite objects?"
- Answers must:
  - Cite fragments
  - Surface ambiguity
  - Avoid extrapolation

Deliverable:
- Example Q&A backed by graph traversal

Assessment:
- Answers trace to fragments
- Ambiguity visible
- No hallucinated rules

---

## Iteration Expectations

You are expected to iterate.

After the first pass:
- Identify where extraction failed
- Adjust schemas or prompts
- Rerun ingestion

Track:
- What improved
- What regressed
- What required human judgment

---

## Definition of Success

This vertical slice is successful if:

- Fireball produces inspectable RuleUnits, RuleFragments, and a rule graph
- Compiler feasibility is honestly assessed
- RulesLawyer answers are grounded and transparent

A system that refuses to compile Fireball is preferable to one that guesses.

---

## Final Note

This handoff is not about Fireball.

Fireball is the diagnostic tool.

The real goal is to prove that:

> Unstructured rules can be transformed into deterministic, replayable artifacts without magic.

If you feel tempted to "just make it work", stop.
That is the failure mode this project exists to avoid.


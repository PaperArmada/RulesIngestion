# Rules Ingestion Project Capture

## Purpose

This document captures the current understanding of the **Rules Ingestion** project: what it is for, the architecture decisions already made, the design constraints that matter, what has worked, what has failed, and how it connects to the larger end goal of powering retrieval for the Rules Engine.

The intended use of this document is to bootstrap a fresh project context or a new collaborating agent without forcing them to reconstruct the design history from scattered notes.

---

## 1. Project identity

Rules Ingestion is not just “PDF parsing for RAG.” Its job is to turn authored rulebooks into a **deterministic, provenance-rich, retrieval-ready substrate** that can support downstream rule lookup, future enrichment, and eventually executable rule reasoning.

At a high level, the project exists to answer this problem:

> How do we transform visually complex TTRPG rulebooks into the smallest trustworthy units of evidence that can be retrieved quickly, cited faithfully, recombined compositionally, and eventually connected to a rules runtime?

The end goal is not a chatbot that vaguely answers rules questions. The end goal is an **information retrieval system for the Rules Engine**. That means the ingestion system must optimize for:

- faithful recovery of authored mechanics
- deterministic replay and auditability
- strong provenance and citation
- retrieval quality under real benchmark pressure
- compatibility with a future engine that is pure, bounded, and replayable

This project sits upstream of runtime rule execution. It is how the rule corpus becomes machine-usable.

---

## 2. The foundational insight

The most important architectural insight so far is that **retrieval quality depends first on admissible evidence design, not clever embeddings**.

The project originally could have drifted toward a conventional RAG stack:

- extract text
- chunk by token count
- embed
- retrieve
- hope the model fills gaps

That path has been rejected.

Instead, the project has converged on this principle:

> The unit of retrieval must also be a trustworthy unit of evidence.

That is why **EvidenceUnits** exist and why they are central.

The system now distinguishes sharply between:

- **authoritative, citable evidence**
- **retrieval-only projections**
- **future enrichment / graph layers**

This separation is the core reason the architecture is becoming stable instead of collapsing into a pile of retrieval hacks.

---

## 3. Current v1 architecture

The authoritative v1 pipeline is intentionally narrow:

```text
Stage A -> Stage B -> Retrieval Lab
```

With later stages explicitly gated:

```text
Stage C (LLM enrichment) -> Stage D (graph)
```

### Stage A: Prose Reconstruction

Stage A reconstructs the authorial surface of the rulebook with maximum fidelity and **no semantics**. It consumes PDF pages and OCR/model output, and produces:

- `StageARecord` — raw model envelope per page
- `SurfaceAST` — deterministic structural tree per page

Its job is not to interpret rules. Its job is to preserve the visible authored structure in a deterministic form.

Key ideas in Stage A:

- preserve page order and within-page order
- preserve headings, paragraphs, tables, lists, sidebars, and similar structural blocks
- derive heading ancestry later through `structural_path`
- allow minimal orphan repair, but do not rewrite semantics
- guarantee deterministic replay given the same input

### Stage B: Evidence Binding

Stage B converts Stage A outputs into **EvidenceUnits**, which are the canonical admissible evidence layer.

An EvidenceUnit is:

- one prose block, table, list, callout, or heading-type unit
- stable in identity
- bounded and meaningful as evidence
- traceable back to source lines and page provenance

Stage B is where the project stopped thinking in terms of generic chunks and started thinking in terms of **admissible rule evidence**.

Key guarantees in Stage B:

- one EvidenceUnit per meaningful prose block / table / list
- complete tables, not split tables
- no cross-page joins unless the join rule is explicit and auditable
- provenance fields sufficient for citation and replay
- stable sort order for deterministic substrate creation

### Retrieval Lab

Retrieval Lab is the evaluation harness. It is deliberately scoped as:

- authority-free
- semantics-free
- comparative
- not a correctness evaluator

Its role is to answer:

> Under a given retrieval regime, how discoverable are the gold EvidenceUnits?

It evaluates retrieval modes and retrieval projections without letting those experiments redefine the admissible layer.

This boundary is excellent and should remain strict.

---

## 4. What the pipeline produces, conceptually

The project now has a clearer artifact model than it did earlier.

### Stage A artifacts

These preserve the surface of the document:

- raw markdown from the model
- structural nodes
- page fingerprints
- deterministic ordering

### Stage B artifacts

These define admissible evidence:

- `unit_id`
- `unit_type`
- `text`
- `structural_path`
- `ordering_key`
- `page_fingerprint`
- `content_hash`
- `source_line_start`
- `source_line_end`
- anomaly flags and optional multi-page metadata

### Retrieval projections

These are derived views over EvidenceUnits, such as:

- clause families
- context windows
- graph-expanded candidates in the future
- pairing sidecars

These improve recall and ranking, but are **not evidence**.

This separation is one of the strongest pieces of the design.

---

## 5. Core decisions that appear correct

### 5.1 EvidenceUnits as canonical admissible evidence

This is likely the most important decision made so far.

It prevents a long list of downstream failures:

- citing derived context windows as if they were primary evidence
- letting graph nodes become quasi-authoritative
- mixing enrichment output with source truth
- losing provenance during retrieval optimization

It also gives the whole system a stable contract:

> If a claim matters, it must resolve to EvidenceUnits.

That is the right stance for anything intended to power a Rules Engine.

### 5.2 A strict Stage A / Stage B boundary

Keeping Stage A “no semantics” and Stage B “no interpretation, no ontology, no paraphrase” is another very good decision.

This avoids premature cleverness. It means the system first earns the right to do semantics by proving that it can reconstruct and bind the text faithfully.

In practice, this does three things:

- reduces error compounding
- makes debugging possible
- makes future enrichment optional rather than foundational

### 5.3 Retrieval Lab as comparative, not authoritative

This boundary is also correct.

A retrieval harness should not quietly become a correctness oracle. Keeping it focused on discoverability, ranking, recall, failure buckets, and regression policy keeps the evaluation legible.

It also makes it much easier to say:

- retrieval improved recall but not answerability
- retrieval found gold in candidates but ranked it poorly
- benchmark grounding itself is weak

That clarity matters.

### 5.4 Determinism everywhere

The project has consistently moved toward deterministic replay:

- page fingerprints
- content hashes
- stable unit IDs
- stable ordering keys
- reproducible baselines
- preserved environment fingerprinting

This aligns directly with the world engine direction, where the runtime rule system is expected to be deterministic, pure, and replayable.

The ingestion project is already conforming to the same philosophy as the future engine. That is not accidental; it is a strategic fit.

### 5.5 Separation of admissible evidence from retrieval projections

Clause families, pairing, and future graph expansion are useful, but they should never become the thing cited as truth.

The design now correctly treats them as:

- retrievable
- rankable
- instrumentable
- disposable
- non-authoritative

That protects the project from “smart but slippery” retrieval behavior.

---

## 6. The architectural philosophy behind the project

Several design threads have converged into a shared philosophy.

### 6.1 Store light facts, derive everything else

The world engine contract already argues for storing only lightweight authoritative facts and deriving views as projections. Rules Ingestion has developed an analogous pattern.

In Rules Ingestion:

- EvidenceUnits are the authoritative textual substrate
- clause families, enrichments, and graph artifacts are projections
- if a projection is wrong, it should be rebuilt, not hand-waved into authority

This symmetry with the world engine is a major strength.

### 6.2 No hidden coupling

The architecture overview explicitly rejects hidden coupling and corpus-specific logic living in the wrong place.

That matters because TTRPG corpora vary wildly:

- modern glossy books
- old OCR-hostile layouts
- dense tables
- cross-page procedures
- inconsistent heading strategies
- edition drift

If corpus-specific behavior is allowed to leak into Stage B without explicit config or contract, the substrate will become untrustworthy very fast.

### 6.3 Retrieval is in service of rule reasoning, not vice versa

The project has moved away from “whatever maximizes MRR” as the sole goal.

The real question is:

> Does the retrieved material preserve the structure necessary for downstream mechanical reasoning?

That is why tables, heading ancestry, complete lists, contextual adjacency, and multi-evidence composition matter so much here.

---

## 7. What has succeeded so far

### 7.1 The project has a real v1 now

This is more important than it sounds.

There is now a clear canonical documentation spine:

- architecture overview
- Stage A contract
- Stage B contract
- schema registry
- glossary
- retrieval lab spec
- baseline manifest
- ADRs
- Stage C / D gates

That means the project is no longer just a sequence of experiments. It has started to become an actual system.

### 7.2 Baselines are being treated as real engineering artifacts

The baseline manifest and comparison protocol indicate a strong move toward stable reproducibility.

Important successes here:

- fixed comparison targets
- explicit run IDs
- canonical baseline vs dual-list vs pairing comparisons
- environment fingerprinting
- determinism statements
- regression policy

That is exactly how this kind of project avoids self-deception.

### 7.3 Dual-list fusion appears to be a meaningful win

The design docs now treat dual-list fusion as the production default and retain the baseline hybrid run for comparison.

That implies the project has already found one retrieval enhancement that improved recall without sacrificing core T1 behavior.

The idea itself is strong:

- Index_U = canonical EvidenceUnits
- Index_F = clause-family projection
- fuse both instead of replacing one with the other

This is elegant because it improves retrieval while preserving the admissible layer.

### 7.4 Pairing was handled with appropriate skepticism

A weaker team would have declared pairing a win because it felt clever.

Instead, the project did something better:

- instrument it
- label it experimental
- require counters beyond headline metrics
- forbid T1 degradation
- refuse to treat it as proven without evidence

That discipline is a success in itself.

### 7.5 The project learned to benchmark the retrieval system, not just admire demos

The retrieval design critique and Retrieval Lab materials show a shift toward benchmark realism.

Notable healthy directions:

- use failure buckets
- separate retrieval failure from answer failure
- stratify T1/T2/T3
- care about full-set hit for multi-evidence questions
- treat benchmark grounding as a first-class problem

This is the right way to evaluate a system that must answer compositional rules questions.

---

## 8. What has failed, or been revealed as weak

### 8.1 Naive text extraction is not enough

This is one of the clearest lessons.

TTRPG rulebooks are visually structured documents with:

- multi-column layout
- tables spanning pages
- sidebars
- artwork interference
- headers that determine mechanical scope
- list structure that matters semantically

Naive extraction breaks reading order, shreds tables, and causes semantic garbage downstream.

This means that retrieval quality is bottlenecked far earlier than embedding choice. If the ingestion is wrong, everything after it is fake progress.

### 8.2 Fixed-size chunking is actively harmful

Traditional token-count chunking fails badly for rules text.

It can:

- split condition text from its modifiers
- separate numbered procedures
- detach tables from headers
- destroy section scope
- drift across document versions

The project has correctly learned that generic chunking strategies are not neutral here; they are often destructive.

### 8.3 Dense retrieval alone is insufficient

Another strong lesson: semantic similarity is not the same as rule correctness.

Rulebooks depend heavily on exact tokens and exact distinctions:

- resistance vs immunity
- prepared vs known
- advantage vs bonus
- spell attack vs saving throw
- general rule vs exception rule

Dense retrieval can feel good in demos while still failing precisely where game-time lookup needs exactness.

This is why hybrid retrieval is not just “nice to have.” It is structurally necessary.

### 8.4 Retrieval metrics alone can lie

MRR can improve while the system still fails where it matters.

The project seems to have learned this through its move toward:

- T1 regression tracking
- full-set metrics
- failure buckets
- grounding audits
- per-query diagnostics

That shift matters. Retrieval work often fails because teams celebrate single-number improvements that do not translate into usable reasoning context.

### 8.5 Benchmark quality is a major vulnerability

A recurring theme in the surrounding work is that the benchmark itself is often the weakest part.

Likely problems include:

- weak gold grounding
- missing gold units
- ambiguous questions
- edition mismatch
- questions that look atomic but actually need composition
- questions that assume a retrieval unit shape the corpus does not support

This is not a side issue. In this project, benchmark design is part of system design.

### 8.6 Graph temptation arrived before substrate stability

There is a strong pull toward graphs, semantic lifting, and agentic retrieval. Those ideas are probably directionally right, but the gating docs correctly recognize that moving too early would destabilize the foundation.

This means the project has already learned an important negative lesson:

> A graph built on unstable evidence is a polished hallucination engine.

Stage C and D are correctly gated behind Stage A/B stability.

---

## 9. The specific architecture of retrieval today

The current retrieval architecture is more mature than a standard dense RAG stack.

### Retrieval substrate

The substrate is Stage B EvidenceUnits, optionally accompanied by retrieval-only projections such as clause families.

### Retrieval modes

The lab supports:

- sparse
- dense
- hybrid

### Production default direction

The current happy path is hybrid retrieval with dual-list fusion.

Conceptually:

- retrieve over canonical units
- retrieve over family projections
- fuse rankings
- dedupe toward EvidenceUnits
- evaluate against gold EvidenceUnit IDs

### Experimental layer

Pairing edges exist as an instrumented experimental addition:

- delta -> base
- exception -> base

The project is correctly refusing to trust pairing without per-run evidence.

### Metrics that matter

The project now cares about:

- MRR
n- T1 MRR
- T1 regressions
- Hit@k
- Recall@k
- full-set hit@k
- grounded counts
- failure buckets
- first gold rank

This is much closer to what a serious retrieval program should monitor.

---

## 10. Why this project is different from ordinary RAG work

Most RAG projects stop at “retrieve enough text for a model to answer.”

Rules Ingestion is aiming at something stricter:

- evidence must be admissible
- provenance must survive every layer
- retrieval must serve mechanical reasoning
- future graph and runtime layers must remain deterministic
- downstream claims must resolve to source evidence

That pushes the project into a hybrid space between:

- document intelligence
- retrieval engineering
- symbolic systems design
- compiler-style staging
- runtime contract design

That is the right framing. The system is not just a search engine. It is the front half of a rule execution pipeline.

---

## 11. Connection to the future Rules Engine

This is where the project becomes especially coherent.

The Foundational World Engine Contract describes a runtime that is:

- fast in the hot loop
- deterministic
- pure in rule evaluation
- based on bounded prefetch
- explicit in inputs and outputs
- minimal in authority
- projection-friendly

Rules Ingestion should be seen as preparing the **knowledge substrate** that a future rule compiler / repository / runtime chain can consume.

The v1.1 world-engine expansion frames a larger stack:

```text
Rule Ingestion -> Rule Repository -> Rule Compiler -> Runtime Engine -> Choice Systems -> Frame Store
```

That implies a future shape for this project:

1. **Rule Ingestion** reconstructs and binds the authored source.
2. **Rule Repository** stores canonical structured rule artifacts.
3. **Rule Compiler** turns those artifacts into deterministic runtime representations.
4. **Runtime Engine** evaluates scenes using pure rule logic.
5. **Choice Systems** inject players, GM, AI, and RNG decisions.
6. **Frame Store** preserves replayable state transitions.

Rules Ingestion is therefore upstream of executable rules, but it must already think in a way that respects runtime constraints.

That means a good ingestion substrate should eventually support:

- exact rule citation
- conflict and exception tracking
- base vs modifier relationships
- phase-sensitive rule lookup
- composition across multiple EvidenceUnits
- future graph paths that remain resolvable to evidence

The retrieval system does not need to be the engine, but it does need to be legible to the engine.

---

## 12. The strongest conceptual bridge discovered so far

A particularly important conceptual bridge has emerged:

### World engine side

- authoritative facts
- derived projections
- deterministic evaluation
- bounded prefetch

### rules ingestion side

- authoritative EvidenceUnits
- derived retrieval projections
- deterministic substrate construction
- bounded retrieval context assembled from citable units

This is not just a nice analogy. It suggests the projects are converging on the same deep design discipline.

That probably means future success depends on preserving this symmetry.

---

## 13. Likely future architecture after v1 stabilization

Assuming v1 holds, the next stages likely look like this.

### Stage C: enrichment

This should remain non-authoritative.

Likely useful outputs:

- normalized terminology
- glossary / synonym hints
- local dependency tagging
- entity mentions with provenance
- exception / modifier candidate relationships
- phase labels for rule procedures

But none of this should alter or overwrite EvidenceUnits.

### Stage D: graph

The graph should be deterministic, versioned, and replayable.

It should probably not begin as a grand ontology-first universe. A more realistic path is:

- start from EvidenceUnit-linked nodes
- version edge contracts explicitly
- keep graph construction reproducible
- evaluate graph-assisted retrieval separately from Stage B baseline
- never allow graph results to bypass evidence resolution

### Rule repository / compiler later

Only once EvidenceUnits and enrichment become stable should the system start compiling rule structures that are shaped for runtime use.

That future compilation layer will likely need:

- stable rule IDs
- phase-sensitive decomposition
- exception hierarchy
- typed parameter extraction
- effect schemas
- runtime-friendly references back to source evidence

---

## 14. Practical lessons for the next project prompt

A fresh project prompt for Rules Ingestion should probably encode the following truths.

### What this project is

- A deterministic ingestion and retrieval system for TTRPG rulebooks.
- The upstream substrate for a future Rules Engine.
- A provenance-first system, not a vibe-based RAG demo.

### What this project is not

- Not a generic chatbot over PDFs.
- Not a semantics-first graph project yet.
- Not a benchmark-free embedding playground.
- Not allowed to treat derived artifacts as evidence.

### What must stay invariant

- EvidenceUnits are canonical admissible evidence.
- Stage A and Stage B remain non-semantic / non-interpretive in their own specific ways.
- Retrieval projections remain non-authoritative.
- Stage C and Stage D are gated behind substrate stability.
- Determinism and replayability matter as much as raw retrieval quality.

### What should be optimized next

- substrate fidelity under harder books
- better benchmark grounding and curation
- stronger failure analysis on multi-evidence queries
- controlled graph preparation without destabilizing v1
- eventual interfaces for rule repository / compiler consumption

---

## 15. The key successes and failures in one view

### Successes

- The project established a canonical v1 architecture.
- EvidenceUnits became the authoritative substrate.
- Retrieval projections were cleanly separated from admissible evidence.
- Determinism and reproducibility became explicit goals.
- Baseline and comparison discipline improved.
- Dual-list fusion appears to be a real practical improvement.
- Pairing was treated experimentally rather than dogmatically.
- Retrieval evaluation matured beyond single-number score worship.
- The project is aligning philosophically with the future Rules Engine.

### Failures / exposed weaknesses

- Naive PDF text extraction proved insufficient.
- Fixed-size chunking proved destructive.
- Dense-only retrieval proved too approximate for rules work.
- Benchmark quality and gold grounding remain a major source of uncertainty.
- It is easy to over-read retrieval improvements without checking answerability.
- There is a constant temptation to jump to graph / enrichment before substrate stability.
- TTRPG rules text is structurally hostile enough that generic document pipelines routinely fail.

---

## 16. Recommended north star

The best current north star for Rules Ingestion is:

> Build a deterministic, provenance-rich corpus of admissible rule evidence that can be retrieved compositionally today and compiled into executable rule structures tomorrow.

That sentence captures the actual ambition better than “RAG for rulebooks.”

---

## 17. Final framing

Rules Ingestion has matured from a retrieval experiment into the beginnings of a real compiler-adjacent subsystem.

Its deepest lesson so far is that **the substrate is the product**.

Not embeddings by themselves.
Not graphs by themselves.
Not clever prompting by itself.

If the substrate is faithful, bounded, citable, and deterministic, then enrichment, graph layers, and runtime compilation all become possible.

If the substrate is unstable, everything downstream becomes expensive theater.

That is the most important thing this project has learned.

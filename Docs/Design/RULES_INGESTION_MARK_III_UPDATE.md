# RulesIngestion Mark III — Prose-First, Evidence-Bound Architecture (Updated)

## Status

Normative design document for RulesIngestion Mark III.

This document supersedes all Marker-first ingestion designs. Any document assuming layout blocks or "chunks" as the canonical substrate is non-normative.

---

## 1. Core Thesis

RulesIngestion Mark III treats **authored prose** as the canonical substrate.

All downstream artifacts — evidence units, retrieval indices, facts, entities, graphs, gold sets — are **projections** derived from that substrate.

No semantic claim may exist without an explicit pointer back to authored prose.

Safety, correctness, and authority are enforced by **contracts and provenance**, not by lossy extraction.

---

## 2. Pipeline Model

### 2.1 Ingestion Spine (Deterministic)

Mark III's ingestion spine is intentionally shallow and deterministic (outside of simple orphan heading work):

- **Stage A — Extraction (PDF Normalization)**
- **Stage B — Prose Reconstruction (Authorial Surface)**
- **Stage C — Evidence Binding (Prose Partitioning + Provenance)**

Stages A through C together produce the **only admissible input** to semantic reasoning. They are fully deterministic and do not involve LLM interpretation.

### 2.2 Retrieval Baseline (Post-Ingestion)

After the deterministic ingestion spine completes, a retrieval evaluation pass establishes **baseline metrics** before any LLM post-processing:

- **Dense** retrieval over verbatim EvidenceUnit text
- **Sparse** (BM25) retrieval over verbatim text
- **Hybrid** fusion (e.g., RRF)

These baselines measure what raw, unadorned EvidenceUnits achieve — the floor from which all enrichment is measured.

### 2.3 Enrichment & Graph Construction

- **Stage D — LLM Enrichment (Retrieval-only annotations)**
- Retrieval baseline update (measure enrichment impact vs. §2.2 baselines)
- **Stage E — Graph Construction (Semantic Lifting)**

Stage D must never create facts or authority. Stage E is strictly derivative of EvidenceUnits.

### 2.4 Evaluation

- **Stage F — Retrieval Evaluation (Gold sets, metrics, regression)**

Stage F measures retrieval and grounding honestly across corpora and suites, including regression comparisons across all retrieval modes and pipeline stages.

### 2.5 Answer Synthesis (Optional, Downstream)

Answer synthesis is a downstream consumer that must respect Mark III authority boundaries:

- Constrained by admissible evidence from Stages C and E
- Must refuse when grounded support is not admissible

---

## 3. System Components

### 3.1 Ingestion Orchestrator

**Responsibility**

- Single entry point for ingestion runs
- Owns determinism, versioning, and fan-out
- Never interprets content

**Outputs**

- `run_manifest.json`
- per-page execution plan

**Invariant**

Identical inputs + identical toolchain ⇒ identical manifests and hashes.

---

### 3.2 Page Source Manager (Stage A Producer)

**Responsibility**

Normalize all source inputs into canonical page images.

**Inputs**

- PDF bytes + page selection (Brutal Pages is just a selection set)
- Optional pre-rendered images

**Outputs**

- `page_image.png`
- `page_fingerprint`
- `pdf_provenance.json`

---

### 3.3 OCR / Transcription Worker (Stage B Producer)

**Responsibility**

Reconstruct the authored surface of a page.

**Outputs (per page)**

- `stageB.page.json` — raw model envelope
- `stageB.surface.md` — verbatim markdown
- `stageB.surface.ast.json` — deterministic structural AST

**Critical Rule**

Only the AST may be consumed downstream. Raw text exists solely for audit and reproducibility.

---

### 3.4 Evidence Binder (Stage C Producer)

**Responsibility**

Partition authored prose into EvidenceUnits and bind each unit to explicit provenance and containment.

**Outputs**

- `stageC.evidence_units.json`
- gate diagnostics

---

### 3.5 Retrieval Baseline Runner

**Responsibility**

Run Dense, Sparse (BM25), and Hybrid retrieval evaluation over raw EvidenceUnits to establish baseline metrics before any LLM enrichment.

**Outputs**

- per-mode baseline metrics (MRR, Hit@k, Recall@k)
- score distributions and diagnostics

---

### 3.6 Enrichment Worker (Stage D Producer)

**Responsibility**

Produce retrieval-only semantic annotations over EvidenceUnits.

**Critical Rule**

Enrichment is **non-evidence** and must never be treated as authoritative.

**Outputs**

- `evidence_unit.enrichment` payloads (versioned)
- cache manifest keyed by deterministic fingerprints
- retrieval baseline delta report (vs. §3.5 baselines)

---

### 3.7 Graph Builder (Stage E Producer)

**Responsibility**

Derive semantic structure from EvidenceUnits with full provenance.

**Outputs**

- Structural nodes (document/section)
- Evidence nodes
- Entity nodes
- RuleFact nodes
- Typed edges

---

### 3.8 Benchmark Harness (Stage F)

**Responsibility**

Measure retrieval and grounding honestly:

- validate nominated gold
- compute retrieval metrics
- attribute failure causes

**Outputs**

- per-suite metrics (MRR, Hit@k, Recall@k, Gold-in-candidates)
- gold audits (keep/add/remove)
- refusal-acceptable flags
- regression reports across pipeline stages and retrieval modes

---

### 3.9 Answer Layer (Optional, Downstream)

**Responsibility**

Produce user-facing answers constrained by admissible evidence.

**Outputs**

- answer text + citations
- explicit refusal/qualification when prerequisites are missing

**Critical Rule**

No admissible grounding ⇒ refuse or qualify. Never guess.

---

## 4. Stage A — Extraction Contract

### 4.1 Purpose

Normalize PDF inputs into canonical page images with stable provenance.

### 4.2 Allowed

- Rendering pages to images
- Fingerprinting and provenance capture
- Page selection sets (e.g., Brutal Pages)

### 4.3 Forbidden

- Semantic interpretation
- Layout-to-rule inference

### 4.4 Gates

- Render completeness gate
- Fingerprint stability gate

---

## 5. Stage B — Prose Reconstruction Contract

### 5.1 Purpose

Reconstruct what the author intended a human reader to read, without semantic interpretation.

### 5.2 Allowed

- Reordering into coherent reading order
- Table reconstruction as tables
- Separation of callouts, sidebars, images, footnotes

### 5.3 Forbidden

- Paraphrasing or summarization
- Inferring missing content
- Semantic labeling (rule/example/definition/etc.)

### 5.4 Gates

- Coverage gate
- Ordering sanity gate
- Table parse gate
- Stability gate (hash reproducibility)

---

## 6. Stage C — Evidence Binding Contract

(Stage C replaces all "chunking" and "broadening" concepts.)

### 6.1 Purpose

Bind authored prose units to explicit provenance and structural containment.

### 6.2 Canonical Unit: EvidenceUnit

EvidenceUnit is the **only admissible substrate** for semantic lifting.

Each EvidenceUnit includes:

- verbatim text or table
- unit type
- structural path (best-effort)
- total ordering key
- full provenance
- anomaly and quality flags

### 6.3 Forbidden

- Entity extraction
- Rule interpretation
- Cross-page joins without auditable rules

### 6.4 Gates

- Orphan gate
- Section bleed gate
- Table integrity gate
- Unit size bounds

### 6.5 Orphan Handling

**Orphan pages** have no heading nodes in the AST. Units on such pages initially have empty `structural_path`. The orphan gate fails if all units are orphans.

**Exemptions (orphan gate passes):**

- Single-unit pages (forms, image-only)
- Image+caption-only pages (1–2 children: paragraph + image_ref; no header needed)
- Standalone pages (no prior page; e.g. page 0, single-page PDFs)

**LLM orphan header pass:** For orphans that are not exempt, when a prior page exists and `OPENAI_API_KEY` is set, an LLM assigns a heading from context (prior page + orphan page markdown). The assigned heading is written into each EvidenceUnit's `structural_path`. The AST is **not** enriched; the heading lives only in the evidence units. Downstream consumers use units, so the metadata is preserved.

---

## 7. Retrieval Baseline Pass

### 7.1 Purpose

Establish retrieval performance baselines over raw, unenriched EvidenceUnits from Stages A–C. These baselines are the measurement floor against which all subsequent enrichment (Stage D) and graph construction (Stage E) are evaluated.

### 7.2 Modes

- **Dense** — embedding-based retrieval over verbatim EvidenceUnit text
- **Sparse** — BM25 over verbatim text
- **Hybrid** — fusion (e.g., RRF) combining dense and sparse signals

### 7.3 Outputs

- Per-mode metrics (MRR, Hit@k, Recall@k)
- Score distributions and diagnostics
- Baseline snapshot for regression comparison

### 7.4 Critical Rule

No enrichment or LLM-derived fields are present at this stage. Baselines measure the deterministic ingestion spine alone.

---

## 8. Stage D — LLM Enrichment Contract (Retrieval-only)

Stage D is a **retrieval index augmentation** stage that annotates EvidenceUnits with non-authoritative semantic scaffolding.

### 8.1 Purpose

Improve retrieval recall and ranking for:

- paraphrased questions
- terse or archaic corpora
- negative-space query shapes
- cases where key semantics span multiple sentences

Stage D exists to reduce dependence on neighbor expansion and to make dense retrieval less brittle.

### 8.2 Hard Wall: Non-Evidence

All Stage D outputs are tagged:

- `authority = none`
- `source = llm_annotation`
- `admissibility = non_evidence`
- `stage_e_visibility = hidden`
- `citation_policy = never_cite`

Stage D fields are never admissible evidence and are ignored by Stage E.

### 8.3 Output Schema (Versioned)

Stage D attaches `evidence_unit.enrichment` with:

- short neutral summaries
- controlled topic tags
- question-shaped paraphrases ("questions answered")
- lexical anchors
- risk flags (`delta_only`, `orphan_step`, `example_only`, etc.)

All schema expansions must be versioned.

### 8.4 Determinism & Caching

Stage D must be deterministic at the pipeline level:

- fixed prompt version and model id
- cached by a stable `input_fingerprint`
- reruns on identical inputs must yield identical outputs

### 8.5 Retrieval Baseline Update

After Stage D enrichment is applied, retrieval baselines from §7 are re-run to measure the impact of enrichment. The delta between §7 baselines and post-enrichment metrics quantifies the value of LLM annotations.

---

## 9. Stage E — Graph Construction Contract

### 9.1 Purpose

Derive semantic structure from EvidenceUnits with full provenance.

### 9.2 Outputs

- Structural nodes (document/section)
- Evidence nodes
- Entity nodes
- RuleFact nodes
- Typed edges

### 9.3 Invariants

- Every entity and fact must cite ≥1 EvidenceUnit
- Facts are not entities
- No silent inference or text rewriting

### 9.4 Gates

- Evidence-pointer completeness
- Canonical ID stability
- Partition invariants

Stage E may include additional admissibility gates (scalar delta completeness, authority tier filtering, trait definition closure), but may not infer missing rules.

---

## 10. Stage F — Retrieval Evaluation Contract

### 10.1 Purpose

Measure retrieval and grounding honestly across corpora and suites.

### 10.2 Responsibilities

- validate nominated gold chunks
- compute retrieval metrics
- identify grounding insufficiency (missing parent axioms, authority mismatches)
- flag refusal-acceptable queries

### 10.3 Outputs

- benchmark reports per corpus and suite
- gold audits: keep/add/remove
- regression comparisons across retrieval modes and pipeline stages (§7 baseline vs. post-Stage D vs. post-Stage E)

---

## 11. Answer Synthesis (Optional, Downstream)

### 11.1 Purpose

Produce user-facing answers constrained by admissible evidence.

### 11.2 Hard Rule

If Stage E cannot ground the claim, answer synthesis must refuse or explicitly qualify.

### 11.3 Allowed

- concise answers
- citations to EvidenceUnits (verbatim or anchored spans)
- qualified responses

### 11.4 Forbidden

- citing Stage D fields
- inventing rules

---

## 12. Brutal Pages Benchmark Integration

Brutal Pages is the primary regression harness for Stages A, B, and C.

### 12.1 Run Modes

- A-only: render fidelity
- A+B: surface fidelity
- A+B+C: segmentation and provenance (includes orphan header pass when enabled)
- A+B+C+E: end-to-end deltas (secondary)

### 12.2 Per-Page Outputs

- stage hashes (A/B/C)
- gate diagnostics
- AST and EvidenceUnit diffs
- salvage score

Failures here block downstream semantic work.

---

## 13. Determinism and Model Variability

OCR/transcription introduces model-mediated variability.

Mark III does not hide this.

Instead:

- Stage B outputs are content-addressed
- Stage C/E artifacts embed upstream hashes
- Any graph is reproducible by pinning Stage B hash

This replaces Marker's spatial determinism with **prose transcript determinism**.

---

## 14. Graph Design Implications

Graph layering is explicit:

- structural nodes CONTAIN evidence
- evidence MENTIONS entities
- evidence ASSERTS facts
- facts ABOUT/APPLY_TO entities

Graphs constrain and explain; they do not retrieve.

---

## 15. Design Consequences

- Marker-era docs are archival, not normative
- Tables are first-class prose, not second-class blocks
- Authority is enforced by contracts, not extraction loss
- Rule compilation is impossible until EvidenceUnits are stable
- Retrieval improvements must not undermine admissibility

---

## 16. Scope Boundaries

Out of scope for Mark III:

- Runtime rule execution
- Game-state simulation

Answer synthesis is downstream and optional.

---

## 17. Summary

RulesIngestion Mark III is a prose-first, evidence-bound ingestion system.

It treats authored text as immutable ground truth, binds it to provenance deterministically, and only then permits semantic structure to emerge.

The pipeline is structured in two phases:

1. **Deterministic ingestion** (Stages A → B → C) produces EvidenceUnits with full provenance. Retrieval baselines are established over these raw units.
2. **LLM enrichment and graph construction** (Stages D → E) augment retrieval and derive semantic structure. Retrieval baselines are re-measured after each stage to quantify impact.

Stage F provides honest, comprehensive evaluation across all pipeline stages and retrieval modes.

This architecture is intentional and non-negotiable.

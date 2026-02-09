# RulesIngestion Mark III — DeepSeek-Centric Prose-First Architecture

## Status

Normative design document for RulesIngestion Mark III.

This document supersedes all Marker-first ingestion designs. Any document assuming layout blocks or chunks as the canonical substrate is non-normative.

---

## 1. Core Thesis

RulesIngestion Mark III treats **authored prose** as the canonical substrate.

All downstream artifacts — chunks, facts, entities, graphs, indices — are **projections** derived from that substrate.  
No semantic claim may exist without an explicit pointer back to authored prose.

Safety, correctness, and authority are enforced by **contracts and provenance**, not by lossy extraction.

---

## 2. Pipeline Spine (Authoritative)

The pipeline is intentionally shallow and asymmetric:

- **Stage A — Prose Reconstruction (Authorial Surface)**
- **Stage B — Evidence Binding (Prose Partitioning + Provenance)**
- **Stage C — Semantic Lifting (Graph Construction)**

Stages A and B together produce the _only admissible input_ to semantic reasoning.

Stage C is downstream and strictly derivative.

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

### 3.2 Page Source Manager

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

### 3.3 DeepSeek OCR Worker (Stage A Producer)

**Responsibility**
Reconstruct the authored surface of a page.

**Outputs (per page)**

- `stageA.page.json` — raw model envelope
- `stageA.surface.md` — verbatim markdown
- `stageA.surface.ast.json` — deterministic structural AST

**Critical Rule**
Only the AST may be consumed downstream. Raw text exists solely for audit and reproducibility.

---

## 4. Stage A — Prose Reconstruction Contract

### 4.1 Purpose

Reconstruct what the author intended a human reader to read, without semantic interpretation.

### 4.2 Allowed

- Reordering into coherent reading order
- Table reconstruction as tables
- Separation of callouts, sidebars, images, footnotes

### 4.3 Forbidden

- Paraphrasing or summarization
- Inferring missing content
- Semantic labeling (rule/example/definition/etc.)

### 4.4 Gates

- Coverage gate
- Ordering sanity gate
- Table parse gate
- Stability gate (hash reproducibility)

---

## 5. Stage B — Evidence Binding Contract

(Stage B replaces all “chunking” and “broadening” concepts.)

### 5.1 Purpose

Bind authored prose units to explicit provenance and structural containment.

### 5.2 Canonical Unit: EvidenceUnit

EvidenceUnit is the _only_ admissible substrate for semantic lifting.

Each EvidenceUnit includes:

- verbatim text or table
- unit type
- structural path (best-effort)
- total ordering key
- full provenance
- anomaly and quality flags

### 5.3 Forbidden

- Entity extraction
- Rule interpretation
- Cross-page joins without auditable rules

### 5.4 Gates

- Orphan gate
- Section bleed gate
- Table integrity gate
- Unit size bounds

### 5.5 Orphan Handling

**Orphan pages** have no heading nodes in the AST. Units on such pages initially have empty `structural_path`. The orphan gate fails if all units are orphans.

**Exemptions (orphan gate passes):**

- Single-unit pages (forms, image-only)
- Image+caption-only pages (1–2 children: paragraph + image_ref; no header needed)
- Standalone pages (no prior page; e.g. page 0, single-page PDFs)

**LLM orphan header pass:** For orphans that are not exempt, when a prior page exists and `OPENAI_API_KEY` is set, an LLM assigns a heading from context (prior page + orphan page markdown). The assigned heading is written into each EvidenceUnit's `structural_path`. The AST is **not** enriched; the heading lives only in the evidence units. Downstream consumers use units, so the metadata is preserved.

---

## 6. Stage C — Semantic Lifting Contract

### 6.1 Purpose

Derive semantic structure from EvidenceUnits with full provenance.

### 6.2 Outputs

- Structural nodes (document/section)
- Evidence nodes
- Entity nodes
- RuleFact nodes
- Typed edges

### 6.3 Invariants

- Every entity and fact must cite ≥1 EvidenceUnit
- Facts are not entities
- No silent inference or text rewriting

### 6.4 Gates

- Evidence-pointer completeness
- Canonical ID stability
- Partition invariants

---

## 7. Brutal Pages Benchmark Integration

Brutal Pages is the primary regression harness for Stages A and B.

### 7.1 Run Modes

- A-only: surface fidelity
- A+B: segmentation and provenance (includes orphan header pass when OPENAI_API_KEY set)
- A+B+C: end-to-end deltas (secondary)

### 7.2 Per-Page Outputs

- stage hashes (A/B/C)
- gate diagnostics
- AST and EvidenceUnit diffs
- salvage score

Failures here block downstream semantic work.

---

## 8. Determinism and Model Variability

DeepSeek OCR introduces model-mediated variability.

Mark III does not hide this.

Instead:

- All Stage A outputs are content-addressed
- Stage B and C artifacts embed upstream hashes
- Any graph is reproducible by pinning Stage A hash

This replaces Marker’s spatial determinism with **prose transcript determinism**.

---

## 9. Graph Design Implications

Graph layering is explicit:

- structural nodes CONTAIN evidence
- evidence DESCRIBES entities
- evidence HAS_FACT facts
- facts APPLY_TO entities

Graphs explain and constrain; they do not retrieve.

---

## 10. Design Consequences

- Marker-era docs are archival, not normative
- Tables are first-class prose, not second-class blocks
- Authority is enforced by contracts, not extraction loss
- Rule compilation is impossible until EvidenceUnits are stable

---

## 11. Scope Boundaries

Out of scope for Mark III:

- Runtime rule execution
- LLM answer synthesis
- Game-state simulation

These depend on Mark III correctness but do not influence its design.

---

## 12. Summary

RulesIngestion Mark III is a prose-first, evidence-bound ingestion system.

It treats authored text as immutable ground truth, binds it to provenance deterministically, and only then permits semantic structure to emerge.

This inversion is intentional and non-negotiable.

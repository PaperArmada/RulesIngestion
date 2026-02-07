> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# Stage A Contract Addendum

**Document Identity, Multi-PDF Normalization & Structural Fidelity**

This addendum comprises two sub-contracts:

1. **Document Identity & Multi-PDF Normalization** — physical PDFs → logical documents.
2. **Structural Fidelity & Layout-Driven Misassignment** — correct structural attribution at extraction time.

---

# Stage A Sub-Contract — Document Identity & Multi-PDF Normalization

**Physical PDFs → Logical Documents**

---

## Purpose

This sub-contract defines how Stage A must reconcile **physical input PDFs** with **logical authoritative documents**.

Its goal is to ensure that:

- file boundaries never become semantic or authority boundaries,
- downstream stages (CDS, PSC, chunking, retrieval, grounding) are invariant to input format,
- ingestion remains deterministic, auditable, and benchmark-stable.

If this contract is violated, later stages will silently misinterpret authority, fragment context, and regress gold recall.

---

## Core Principle (Non-Negotiable)

> **File boundaries are ingestion conveniences, not semantic facts.**

All semantic structure must be derived from document content and authorial organization, never from how PDFs are split on disk.

---

## Inputs

### Physical Inputs

- One or more PDF files:
  - single PDF containing an entire book, OR
  - multiple PDFs containing chapters, sections, or fragments
- For each PDF:
  - `source_pdf_id`
  - `pdf_bytes`
  - original page indices

### Contextual Inputs

- `ruleset_id`
- `book_id`
- extractor bundle (as defined in Stage A)

---

## Outputs

### A-DOC-1: Logical Document

A **Logical Document** is the authoritative ingestion unit used by all downstream stages.

Each Logical Document MUST include:

- `logical_doc_id` (stable, deterministic)
- `ruleset_id`
- `book_id`
- ordered list of `document_parts[]`

Logical Documents are the only units eligible for:

- CDS construction
- PSC extraction
- benchmark alignment

---

### A-DOC-2: DocumentPart[]

Each DocumentPart represents a physical PDF contribution.

Fields:

- `document_part_id`
- `logical_doc_id`
- `source_pdf_id`
- `part_index` (deterministic order)
- `page_offset` (logical page start)
- mapping:

(source_pdf_page_index → logical_page_index)

DocumentParts preserve provenance without introducing authority.

---

## Determinism Constraints

1. Identical sets of PDFs with identical bytes ⇒ identical Logical Documents.
2. `logical_doc_id` is derived deterministically from:

(ruleset_id, book_id, normalized_title, sorted(source_pdf_hashes))

3. Ordering of DocumentParts is deterministic and content-based:

- never filesystem-based
- never ingestion-order-based

4. Logical page numbering must be stable across runs.

---

## Hard Invariants

### A-DOC-INV-1: Single Logical Authority

Each rulebook (as defined by `ruleset_id + book_id`) MUST produce exactly **one** Logical Document unless explicitly configured otherwise.

Multiple PDFs must never produce multiple authoritative roots by default.

---

### A-DOC-INV-2: No Semantic Meaning from File Boundaries

Downstream stages MUST NOT be able to infer:

- chapter boundaries
- section boundaries
- authority tiers

from:

- PDF boundaries
- document_part boundaries
- page resets

Any such inference is a violation.

---

### A-DOC-INV-3: CDS Continuity

The CDS built from a Logical Document MUST:

- allow sections and chapters to span DocumentParts,
- preserve correct ordinal order,
- ignore physical PDF segmentation.

If a chapter spans PDFs, it is still a single CDS subtree.

---

### A-DOC-INV-4: Provenance Preservation

Every Chunk MUST retain:

- `logical_doc_id`
- `document_part_id`
- `source_pdf_id`
- `source_pdf_page_index`
- `logical_page_index`

Auditability must never be sacrificed for normalization.

---

## Normalization Algorithm (Deterministic)

1. **Fingerprint PDFs**

- Compute content hashes for all input PDFs.

2. **Group PDFs into Logical Document**

- Group by `(ruleset_id, book_id)`.

3. **Determine Part Order**

- Prefer explicit chapter numbering in content.
- Fallback: title + first heading ordinal.
- Absolute fallback: sorted PDF hash order (last resort).

4. **Assign Logical Page Indices**

- Pages increment monotonically across DocumentParts.
- No resets at PDF boundaries.

5. **Emit Logical Document + DocumentParts**

- Freeze mapping for downstream use.

---

## Failure Modes

### FM-DOC-1: Authority Fragmentation

Multiple Logical Documents created for one book.
**Symptom:** duplicated CDS roots, contradictory authority ordering.

---

### FM-DOC-2: Context Truncation

Stage B grouping stops at PDF boundaries.
**Symptom:** under-contextualized EvidenceChunks, low embedding utility.

---

### FM-DOC-3: Benchmark Drift

Gold evidence disappears or moves when PDFs are split differently.
**Symptom:** recall regression with no semantic change.

---

### FM-DOC-4: Implicit Chapter Encoding

Chapter semantics inferred from filenames or ingestion order.
**Symptom:** brittle behavior across different PDF layouts.

---

## Metrics

### M-DOC-1: Logical Document Count

logical_documents_per_book

**Gate:** = 1 (unless explicitly allow-listed)

---

### M-DOC-2: Cross-PDF CDS Continuity Rate

Percentage of CDS parent-child relationships that cross DocumentParts.

**Expectation:** Non-zero for multi-PDF books.

---

### M-DOC-3: Chunk Boundary Alignment

Percentage of EvidenceChunks whose grouping stops due to semantic boundary rather than PDF boundary.

**Gate:** ≥ 0.99

---

### M-DOC-4: Gold Stability Under Repartition

Re-ingest the same book as:

- single PDF
- chapter-split PDFs

Measure:

gold_chunk_ids ∩ gold_chunk_ids'

**Gate:** identical sets (ID-stable).

---

## Stop-the-Line Conditions

- Multiple Logical Documents created for same `(ruleset_id, book_id)`
- CDS differs across equivalent PDF partitionings
- Gold evidence loss attributable solely to PDF splits

---

## Benchmark Alignment

Before retrieval or grounding benchmarks:

- verify gold evidence exists in Logical Document,
- verify logical page indices are stable,
- verify CDS paths for gold are identical across formats.

If any fail, benchmarking is invalid.

---

## Explicit Non-Goals

- This stage does NOT infer chapters or sections.
- This stage does NOT perform semantic grouping.
- This stage does NOT assign authority.

Those responsibilities belong to CDS and PSC.

---

## Outcome

If this sub-contract holds:

- ingestion format becomes irrelevant,
- chunk quality and authority are format-invariant,
- benchmarks are honest,
- future multimodal or long-context approaches slot in cleanly.

If it fails, no downstream fix can repair the damage.

---

**Summary:**  
Normalize early. Preserve provenance.  
Never let file layout pretend to be authorial intent.

---

# Stage A Sub-Contract — Structural Fidelity & Layout-Driven Misassignment

**Correct structural attribution at extraction time**

---

## Purpose

This sub-contract defines how Stage A must **detect and quantify** (and, where validated, **correct deterministically**) **structural misassignment** caused by layout—so that downstream stages do not have to compensate for extraction-time errors.

Its goal is to ensure that:

- chunks that are semantically part of a rule block are assigned to the correct `section_path` at extraction time,
- layout effects (multi-column flow, column breaks, floats, marginal alignment) do not drive incorrect structural attribution,
- the problem is observable, measurable, and improvable within Stage A via deterministic, explainable interventions.

This is a Stage A problem in the narrowest, healthiest sense: nothing downstream should compensate for it; Stage A can observe, quantify, and often correct it deterministically.

---

## Problem Definition (Precise)

### Structural misassignment due to layout-driven extraction

A **structural misassignment** occurs when:

1. A chunk that is **semantically part of a rule block**
2. Is assigned by the extractor (Marker) to a **different content path / section_path**
3. **Due to visual layout effects** (multi-column flow, column breaks, floats, or marginal alignment),
4. Even though **document-local semantics indicate continuity**.

Key properties:

- The chunk is **not** random noise.
- The chunk is **adjacent in reading order** but **discontinuous in layout order**.
- The misassignment is **systematic** (e.g. columnar), not stochastic.
- This is **not** “wrong grouping” downstream; it is **incorrect structural attribution at extraction time**.

---

## Core Principle (Non-Negotiable)

> **Structure assignment must respect document-local semantic continuity under the constraints of layout.**

Stage A is the place where we **detect when layout lies about structure**. All detection and correction must be deterministic, explainable, and observable via metrics.

---

## Observables (Signals Already Available)

From Marker + Stage A outputs we have:

- `page_index`
- `block_ordinal`
- `bbox` (x₁, y₁, x₂, y₂)
- `section_path`
- `block_type`
- text content (including labels like “Failure”, “Success”)

This is enough to measure **inconsistency between**:

- **structural assignment** (`section_path`), and
- **spatial + lexical continuity**.

That mismatch is the heart of the problem.

---

## Structural Fidelity (Measurable Concept)

**Structural Fidelity** = the degree to which `section_path` assignments respect document-local semantic continuity under the constraints of layout.

### A. Local structural continuity violations

For each page, examine **adjacent blocks in reading order** (`block_ordinal` order).

**Flag a continuity violation** when:

- `block_i.section_path.L1 != block_{i+1}.section_path.L1`
- **AND** both blocks are:
  - prose or rule-compatible text,
  - not headings,
  - not tables
- **AND** vertical distance between blocks is small (likely same flow)
- **AND** lexical cues indicate continuation (e.g. starts with “Failure”, “Success”, “Critical …”, “If you …”)

This detects exactly the “create a diversion” / outcome-clause misassignment case. This is not guessing semantics; it’s detecting contradictory signals.

### B. Column-induced path divergence

Multi-column layouts produce a specific signature:

- Two blocks with:
  - similar y ranges,
  - widely separated x centroids,
  - but **sequential** `block_ordinal`s
- Often get different `section_path`s.

**Column jump heuristic:**

- `column_jump = abs(x_center_i - x_center_{i+1}) > COLUMN_WIDTH_THRESHOLD`

Then observe:

- How often column jumps **coincide with** `section_path` changes.
- How often those cases are later “reunited” in Stage B rule grouping.

This yields a measurable **layout-induced misassignment rate**.

### C. Sidebar (gate only)

**Gate:** Main-column chunks must **not** contain sidebar or navigation-panel text. Sidebar content is layout, not main document flow.

Stage A must **prune or separate** sidebar blocks so they do not merge with main content (deterministic, recorded in DropRecords or distinct path). How to detect and implement is defined in a separate plan, not in this contract.

**Plan:** [Stage A Sidebar Pruning — Implementation Plan](Stage-A-Sidebar-Pruning-Plan.md).

---

## Metrics (Stage A Only, Non-Invasive)

These do **not** change behavior by default. They make the problem visible.

### M-A9: Structural Continuity Violation Rate

`violations / total adjacent eligible block pairs`

- Tracked per document and per page.
- A rising value flags structural fidelity issues.

### M-A10: Rule Outcome Misassignment Rate

For rule blocks specifically:

- Count outcome-labeled chunks (Success, Failure, etc.).
- Measure how often they:
  - do **not** share the same L1 content path as the rule header,
  - but appear on the same page within a bounded spatial distance.

This directly measures the outcome-clause misassignment failure class.

### M-A11: Column Jump Structural Divergence

`count(column_jump AND section_path_change) / count(column_jump)`

- Isolates layout-driven structural errors from true section transitions.

---

## Hypotheses (Deterministic Interventions to Test)

These are **hypotheses**, not prescriptions. Each can be tested with the metrics above.

### Hypothesis 1: Section paths smoothed across column jumps for non-headings

**Claim:** If two adjacent blocks differ only by column position, and neither is a heading, `section_path` continuity is more likely correct than a sudden section change.

**Test:** For column jumps with non-heading blocks, compute how often Stage B later re-groups them into the same rule block. If high, structural assignment is wrong more often than right.

**Possible deterministic correction (if validated):** Delay `section_path` transitions across column jumps unless a heading intervenes.

### Hypothesis 2: Outcome-labeled blocks inherit rule header paths by default

**Claim:** Outcome clauses (“Success”, “Failure”, etc.) almost never begin new structural sections.

**Test:** Measure how often outcome-labeled chunks end up under a different `section_path` than the nearest preceding rule header, and downstream regrouping frequency.

**Possible correction:** If an outcome label appears without an intervening rule header, inherit the last rule header’s content path. This enforces a known authoring convention, not semantic inference.

### Hypothesis 3: Reading-order continuity beats visual order for structure

**Claim:** For structure assignment, reading order is a better predictor than visual adjacency in multi-column layouts.

**Test:** Compare `section_path` continuity under `block_ordinal` adjacency vs under y-then-x ordering; evaluate which correlates better with Stage B structural grouping.

**Possible intervention:** Prefer `block_ordinal` continuity when assigning section paths, except at explicit headings.

### Hypothesis 4: CDS as post-extraction validator, not generator

**Claim:** CDS should not create structure, but it can detect impossible structures (e.g. rule header followed immediately by a different rule header without outcomes).

**Test:** Count CDS paths where a rule node has no outcome children in extracted structure but does downstream.

**Possible use:** Flag or auto-correct only those CDS paths that violate known rule schemas.

---

## What Not to Do (Agent Guidance)

- **Do not** guess semantics.
- **Do not** merge chunks based on similarity.
- **Do not** repair downstream (Stage B+).
- **Do not** silently rewrite `section_path`s.

All changes must be:

- **deterministic**,
- **explainable**,
- **observable via metrics**.

---

## Experiment Ladder

1. **Instrumentation phase**  
   Add metrics M-A9–M-A11. No behavior changes.

2. **Observation phase**  
   Run on existing corpus. Identify dominant failure patterns.

3. **Single-hypothesis interventions**  
   One rule at a time (e.g. outcome-label inheritance), gated by metric improvement.

4. **Rollback-ready**  
   Every intervention toggled, versioned, and attributable.

---

## Outcome

If this sub-contract is honored:

- structural misassignment is **visible** before chunking,
- improvements are **testable** and **attributable**,
- downstream stages are **not** asked to compensate for extraction-time layout errors.

If it is ignored, downstream grouping will continue to “fix” what Stage A mis-assigned—masking the problem and making it harder to improve.

---

**Summary:**  
Detect when layout lies about structure. Measure it. Correct it deterministically where validated. Keep Stage A responsible for structural attribution.

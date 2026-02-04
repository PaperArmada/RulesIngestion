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

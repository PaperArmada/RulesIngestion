# Document Parsing Tool Assessment

## Purpose

This document records the current assessment of **document parsing tools** used as the first stage of the rule ingestion pipeline.

It is intentionally:
- Tool-specific
- Lightweight
- Disposable

Its purpose is not to justify a choice, but to make replacement easy.

---

## Role of Document Parsing in the Pipeline

Document parsing exists solely to:

- Convert unstructured documents into stable structural blocks
- Preserve layout, ordering, and provenance
- Provide reliable inputs for semantic ingestion stages

Parsing **does not**:
- Understand rules
- Interpret meaning
- Resolve ambiguity
- Construct graphs

Any tool evaluated here is judged only on structural fidelity.

---

## Current Tool: Docling

### What Docling Does Well

Docling is effective at:

- Parsing PDFs, DOCX, HTML, and related formats
- Producing a consistent document tree (sections, paragraphs, lists, tables)
- Preserving page numbers and positional metadata
- Handling complex tables and nested lists
- Integrating multiple OCR backends for scanned documents

These capabilities satisfy the needs of **Stage A — Structural Ingestion**.

---

### What Docling Explicitly Does *Not* Do

Docling does not attempt to:

- Identify rules or rule boundaries
- Extract semantic meaning
- Infer relationships between sections
- Resolve references or dependencies
- Produce executable or semi-executable representations

These omissions are acceptable and desirable.

Docling remains focused on structure, not semantics.

---

## Known Limitations

The following limitations are acknowledged:

- No semantic classification of text
- No awareness of domain-specific constructs (e.g. game mechanics)
- No native support for rule graphs or intermediate representations

These limitations are addressed in downstream stages of the pipeline.

---

## Fit for Purpose

Docling is a **good fit** for its narrowly defined role:

- Structural ingestion
- Provenance preservation
- Layout-aware parsing

It is **not** evaluated as a complete ingestion solution.

Attempts to extend Docling beyond this role should be treated as architectural violations.

---

## Exit Criteria

Docling should be replaced if any of the following become true:

- Structural parsing is unstable across runs
- Critical layout information cannot be recovered
- Table or list parsing degrades beyond acceptable thresholds
- A superior parser provides the same guarantees with materially lower complexity

Replacement decisions should be based on **measured structural fidelity**, not feature breadth.

---

## Non-Goals

This document does not:

- Commit to Docling long-term
- Compare Docling against every alternative
- Prescribe future tooling

It exists to record the current state, nothing more.

---

## Why This Document Exists

This document exists to:

- Prevent overfitting the pipeline to a single parser
- Keep structural ingestion replaceable
- Make tool churn low-cost

If this document feels unnecessary, it has succeeded.


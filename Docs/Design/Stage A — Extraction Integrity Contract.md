# Stage A — Extraction Integrity Contract

**PDF → MarkerStream → Chunk**

---

## Purpose

Stage A establishes the **ground truth extraction layer** of the pipeline.

Its responsibility is to deterministically transform source PDF bytes into:

1. a raw, replayable **MarkerStream**, and
2. a normalized set of **Chunk** artifacts with complete provenance.

Stage A is intentionally unforgiving. Any ambiguity, nondeterminism, or silent loss here poisons all downstream stages.  
If Stage A fails, the pipeline **must stop loudly**.

---

## Inputs

### Authoritative Inputs

- `pdf_bytes` (binary, authoritative)
- `doc_id` (stable external identifier)
- `ruleset_id`, `book_id` (namespacing)

### Versioned Extraction Bundle

- `marker_extractor_version`
- `extraction_config_version`
- deterministic parsing flags (layout heuristics, OCR toggles, etc.)

**Extractor:** PDF→blocks implementation is **Marker only**. One block-type→normalized-type mapping per bundle.

### Optional Deterministic Rules

- heading detection patterns
- block-type normalization map

---

## Outputs

### A1 — MarkerStream (Raw Extraction Artifact)

An immutable, ordered stream of extracted blocks.

Each block MUST include:

- `doc_id`
- `page_index`
- raw extracted text (or block-local text payload)
- bounding box (`bbox`) in page coordinates
- raw extractor block type
- block ordinal (within page)

This artifact is never modified downstream.

---

### A2 — Chunk[] (Intentional Extraction Artifact)

Variable-sized chunks with **intentional boundaries**. Chunk start/end are decided explicitly; fragmentation is unacceptable. Structural signals (e.g. headings) are carried as **metadata** on each chunk and apply to all content in that chunk until the next clear structural change (e.g. next heading, section boundary).

Each Chunk MUST include:

- stable `chunk_id`
- `doc_id`
- structural address: **doc → section/chapter → page** (minimum: page; preferred: section/chapter + page)
- normalized `block_type` (or composite type for multi-block chunks)
- extracted text (span may be page-global or block-local; locality explicit)
- provenance span(s)
- bounding box (or union for multi-block)
- structural metadata (e.g. heading path applying to this chunk)

Chunk IDs are derived **deterministically** (e.g. doc_hash, page_index, block_ordinal, optional quantized_bbox, normalized_block_type). Exact formula is implementation-defined.

Stage A **must not** perform semantic coalescing or meaning-based merging beyond structural grouping (same section/heading scope).

---

## Determinism Constraints

1. Identical `pdf_bytes` + identical extractor bundle  
   ⇒ identical MarkerStream and identical Chunk[] (determinism required; no single canonical JSON encoding mandated for hashing).

2. Chunk IDs are derived **deterministically** (e.g. doc_hash, page_index, block_ordinal, optional quantized_bbox, normalized_block_type). Formula is implementation-defined.

3. All ordered collections are canonically sorted by:

page_index ↑
y_min ↑
x_min ↑
block_ordinal ↑

4. Any extractor nondeterminism is a **hard failure**, not a warning.

---

## Hard Invariants (Non-Negotiable)

### A-INV-1: Provenance Completeness

Every Marker block and Chunk MUST trace to:

- `doc_id`
- `page_index`
- `bbox`
- a source span

Span may be:

- page-global `(char_start, char_end)`, or
- block-local `(local_start, local_end)`

Span locality must be explicit.

---

### A-INV-2: Span Validity

For every Chunk:

- `span_start >= 0`
- `span_end > span_start`
- extracted text for span is non-empty after normalization

Invalid spans are a **hard failure**.

---

### A-INV-3: Structural Address Exists

Every Chunk MUST include a structural address:

- **Minimum:** doc, page (e.g. `doc_id`, `page_index`)
- **Sufficient:** doc → section/chapter → page (e.g. section or chapter label + page)

Heading path tokens may be carried as metadata on the chunk (applying until next structural change). Empty structural signals are allowed but must be measurable.

---

### A-INV-4: Closed-World Block-Type Normalization

All raw extractor block types MUST map into:

{ Text, Heading, Table, Figure, List, Footnote, Unknown }

No silent fallthroughs.

---

### A-INV-5: Explicit Loss Accounting

Stage A may not silently drop blocks.

If a block is dropped, emit a **DropRecord** with:

- reason code
- page_index
- block reference

**Drop policy is tunable.** The pipeline should support examining and tuning drop rules so that only chunks containing information that may be queried are retained. Experimentation with drop rules is expected; all drops must still be recorded.

---

## Failure Modes

### FM-A1: Phantom Nondeterminism

Same input yields different block order, text, or bbox.

### FM-A2: Span Drift

Spans do not align to extracted text.

### FM-A3: Heading Collapse

Headings missing or flattened; structural attachment becomes meaningless.

### FM-A4: Table / Figure Shredding

Complex layouts explode into many micro-blocks.

### FM-A5: Drop Blindness

Extractor fails on pages but pipeline proceeds.

---

## Metrics (Per Doc and Per Run)

### M-A1: Extraction Determinism Hash

markerstream_hash = blake3(deterministic_serialization(MarkerStream))
chunkset_hash = blake3(deterministic_serialization(Chunk[]))

(Determinism required; encoding is implementation-defined.)

---

### M-A2: Page Coverage Rate

pages_with_blocks / total_pages
**Gate:** ≥ 0.99

---

### M-A3: Block Retention Rate

emitted_blocks / (emitted_blocks + dropped_blocks)
**Gate:** ≥ 0.995

When the run includes form-heavy parts (e.g. character sheets), M-A3 is computed on **rulebook parts only**; form parts are excluded so that fillable/form PDFs do not fail the gate.

**Structural side-channel (standard pattern):** Content blocks that are not expected to have text (e.g. empty table cells, empty paragraphs) are **preserved** in a side-channel artifact (`structural_blocks.json`: `containers` + `empty_content`) and are **not** counted as dropped. They are excluded from the M-A3 denominator so retention measures only "content we expect to have text." Downstream (e.g. markdown reconstruction) may merge this structural layer to restore table shape and layout.

---

### M-A4: Span Validity Rate

valid_spans / total_chunks
**Gate:** ≥ 0.999

---

### M-A5: Structural Address Presence

chunks*with_structural_address / total_chunks
**Gate:** ≥ 0.95  
Below threshold marks document as \_structure-poor*.

---

### M-A6: Unknown Block-Type Rate

unknown_blocks / total_blocks
**Gate:** ≤ 0.01

---

### M-A7: Fragmentation (Unacceptable)

Chunk boundaries are **intentional**. No passive fragmentation: we do not emit many micro-chunks from a single logical unit. Structural signals (e.g. headers) are metadata on variable-sized chunks, not separate tiny chunks. Metrics (e.g. median/p95 blocks per page or chunks per section) may be used to guard against fragmentation; gates are implementation-defined.

---

### M-A8: Text Entropy Sanity

For each **non-table** chunk:

alpha_ratio = alphabetic_chars / total_chars  
weird_ratio = nonprintable_or_symbol_chars / total_chars  
**Gate:** ≥ 98% of **non-table** chunks have `weird_ratio ≤ 0.15`

**Note:** Table/index content is expected to be symbol‑heavy. Table‑like headings are recategorized as `Table` so M‑A8 measures only prose‑like chunks.

---

## Gates — Proceed to Stage B Only If

ALL are true:

- Determinism hashes stable across repeated runs
- M-A2 ≥ 0.99
- M-A3 ≥ 0.995
- M-A4 ≥ 0.999
- M-A6 ≤ 0.01
- M-A7 within bounds (no unacceptable fragmentation)
- M-A8 within bounds

Where and how gates are enforced (inline in Stage A process vs. separate validation step) is implementation-defined.

## Stop-the-Line Conditions (Fail Loudly)

- Any determinism hash mismatch
- Missing-page detection not allowlisted
- Any invalid span
- Dropped blocks without explicit reason codes

---

## Benchmark Alignment (50-Query / 6-Batch)

Existing benchmark queries and gold chunks are to be **migrated** to new chunk locations after Stage A (new chunk IDs, new structural addresses). In addition, **fresh search over embedded chunks** may be run to find the new chunk IDs and to discover any additional gold candidates from higher-quality or larger chunks.

### EA-A1: Gold Chunk Existence

For every benchmark query, after migration:

all gold chunk IDs exist post-Stage A (or have been remapped to valid Stage A chunk IDs).
**Gate:** 1.0 (no exceptions)

### EA-A2: Gold Text Integrity

For each gold chunk (after migration):

gold*text_hash = blake3(normalized_text)
Hash drift is a hard failure unless extractor_version changed and run is marked \_breaking*.

---

## Authority Legibility Policy (Soft Degrade)

Stage A does **not** classify authority.

It MUST preserve raw signals required later:

- bounding boxes
- block types
- typography hints (if extractor provides them)

Missing signals are allowed but MUST be measurable and MUST NOT default to “core text.”

---

## Outcome

If Stage A passes, downstream stages are allowed to reason.

If Stage A fails, **no retrieval, grounding, or evaluation may proceed**.

This stage defines whether the pipeline is trustworthy at all.

---

## Sub-contracts

- **Document Identity & Multi-PDF Normalization** ([STAGE-A-Document-Identity-and-Multi-PDF-Normalization.md](STAGE-A-Document-Identity-and-Multi-PDF-Normalization.md)): Physical PDFs → Logical Document; one Logical Document per `(ruleset_id, book_id)`; logical page indices monotonic across DocumentParts; every Chunk retains full provenance (logical_doc_id, document_part_id, source_pdf_id, source_pdf_page_index, logical_page_index). File boundaries are ingestion conveniences, not semantic facts.

---

## Implementation Notes

- **Archive:** Prior implementation lives in `Archive/Mark I/` (e.g. `rules_ingestion_pipeline.py`, Marker subprocess `marker_single`, `load_marker_chunks` / `flatten_marker_tree`, enrichment `coalesce_chunks`, section_path / block_type usage in `discover_deterministic_edges_indexing.py`). Mine patterns from the archive; implement Stage A as **fresh, clean, concise** code with the clearer direction above (Marker only, intentional chunk boundaries, structural address doc–section/chapter–page, tunable drop policy, variable-sized chunks with structural metadata).

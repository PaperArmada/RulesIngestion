# Extraction (Stage A)

Stage A of the Rules Ingestion pipeline: **PDF → MarkerStream → Chunk[]**.

Contracts:

- [Stage A — Extraction Integrity Contract](../Docs/Stage%20A%20—%20Extraction%20Integrity%20Contract.md)
- [Stage A Sub-Contract — Document Identity & Multi-PDF Normalization](../Docs/Design/STAGE-A-Document-Identity-and-Multi-PDF-Normalization.md)

## What it does

1. Runs **Marker** on a PDF (CLI `marker_single`).
2. Builds **Logical Document** and **DocumentPart** (one per book per `ruleset_id` + `book_id`; A-DOC-INV-1). Logical page indices are monotonic; file boundaries are not semantic boundaries.
3. Produces a **MarkerStream**: immutable ordered list of raw blocks with full provenance (logical_doc_id, document_part_id, source_pdf_id, source_pdf_page_index, logical_page_index).
4. Builds **Chunk[]**: variable-sized chunks with intentional boundaries (section/chapter + page), structural metadata, deterministic chunk_id. Every Chunk retains A-DOC-INV-4 provenance.
5. Records every dropped block in **DropRecords** (tunable drop policy).
6. Optional **gates** (M-A2–M-A9) and determinism hashes (M-A1).

## Run

From RulesIngestion root:

**Single PDF:**

```bash
uv run python -m extraction.run <pdf_path> --doc-id <id> --output-dir <dir> [--check-gates]
```

**Multi-PDF (one logical document):**

```bash
uv run python -m extraction.run --pdfs part1.pdf part2.pdf --doc-id my-book --output-dir <dir> [--check-gates]
```

**All PDFs in a folder (one logical document):**

```bash
uv run python -m extraction.run --folder Source/StartFinder2e/PlayerCore/source --output-dir <dir> [--doc-id my-book] [--check-gates]
```

PDFs are discovered as direct children (`*.pdf`) and processed in sorted-by-name order. `--doc-id` defaults to the folder name.

Example (single):

```bash
uv run python -m extraction.run ./sample.pdf --doc-id my-doc --output-dir ./out --check-gates
```

**Outputs** (in `--output-dir`):

- `logical_document.json` — Logical Document + DocumentParts (A-DOC-1, A-DOC-2).
- `marker_stream.json` — MarkerStream (A1) with provenance fields.
- `chunks.json` — Chunk[] (A2) with logical_doc_id, document_part_id, source_pdf_id, source_pdf_page_index, logical_page_index.
- `drop_records.json` — list of DropRecords.
- `metrics.json` — M-A1 hashes and (if `--check-gates`) gate results.

**Exit:** 0 on success; non-zero on Marker failure, invariant violation, or (with `--check-gates`) gate failure.

## Drop policy

Default: drop only blocks with empty text. Every dropped block is recorded in `drop_records.json` with `reason_code`, `page_index`, `block_reference`.

To tune: pass a custom `should_drop(block) -> (bool, reason_code)` when calling `stream_to_chunks()` in code. The CLI uses the default policy.

## Gates

Gates (M-A2–M-A9) are computed when `--check-gates` is set. Results are written to `metrics.json` under `gates`. If any gate fails, the process exits non-zero. M-A9 (provenance completeness) requires every chunk to have full A-DOC-INV-4 provenance (logical_doc_id, document_part_id, source_pdf_id, source_pdf_page_index, logical_page_index); missing fields cause the gate to fail.

## Tests

```bash
uv run pytest tests/extraction/ -v
```

## Document identity (multi-PDF)

File boundaries are ingestion conveniences, not semantic facts. One **Logical Document** per `(ruleset_id, book_id)`; logical page indices are monotonic across DocumentParts. When using `run_extraction()` (single or multi-PDF), every block and chunk gets full provenance (logical_doc_id, document_part_id, source_pdf_id, source_pdf_page_index, logical_page_index). For multiple PDFs use `--pdfs path1 path2 ...` or `--folder DIR`; the CLI runs Marker per PDF, builds one logical document via `build_logical_document_multi_pdf()` with **input order** preserved (part_order) so blocks stay paired with the correct DocumentPart, merges streams by logical page, and writes one set of outputs. Single-PDF runs get one DocumentPart with page_offset 0. **Page count:** read from PDF metadata when `pypdf` is installed; otherwise inferred from Marker block page indices (best-effort).

## Package layout

- `schemas.py` — MarkerBlock, Chunk, DropRecord, LogicalDocument, DocumentPart.
- `document_identity.py` — Logical Document + DocumentPart construction; pdf_content_hash; part order; logical page mapping.
- `normalize.py` — block-type map (closed set), text/section normalization.
- `marker_runner.py` — run Marker, flatten, sort, produce MarkerStream (with optional DocumentPart for provenance).
- `chunker.py` — MarkerStream → Chunk[] + DropRecords; structural grouping; tunable drop policy; A-DOC-INV-4 on Chunks.
- `serialize.py` — deterministic serialization and M-A1 hashing.
- `gates.py` — M-A2–M-A9 (including M-A9 provenance completeness).
- `run.py` — CLI and `run_extraction()`.

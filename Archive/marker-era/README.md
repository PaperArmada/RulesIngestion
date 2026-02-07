# Marker-era code archive

This directory contains the **Marker-first** ingestion pipeline (Stage A: PDF → MarkerStream → Chunk[]; Stage B broadening; CDS; chunk-based blind_eval). It is not normative for Mark III.

## Layout

- **extraction/** — Stage A: marker_runner, surya_runner, chunker, gates, schemas, run.py, deepseek_ocr2_runner (adapter to MarkerStream), document_identity, etc.
- **broadening/** — Stage B: Chunk[] → EvidenceChunk[] (depends on extraction.schemas.Chunk).
- **cds/** — CDS builder (chunk facts, constraints).
- **blind_eval/** — Chunk-based evaluation harness, find_chunks, run_eval, batches, gold_audit.
- **scripts/** — run_brutal_pages, rechunk, build_evidence_chunks_sample, build_extraction_review, diagnostic_heading_samples, sidebar_targeted_analysis, spells_chapter_reconstruction, shadow_experiments_spells_chapter.
- **tests/** — tests/extraction, tests/broadening.

## How to run

From the **RulesIngestion** repo root:

```bash
# Stage A (extraction)
PYTHONPATH=Archive/marker-era uv run python -m extraction.run <pdf_path> --output-dir <dir> --doc-id <id> [--check-gates] [--profile marker|surya|deepseek_ocr2]

# Stage B (broadening) — after Stage A has produced chunks.json
PYTHONPATH=Archive/marker-era uv run python -m broadening.run ...
```

Tests: From repo root, the active `extraction` package (stub) takes precedence, so archived tests may fail to import. To run archived tests, use a dedicated venv with only the archive on path, or run pytest from a copy of the archive outside the repo. The archived pipeline and scripts run correctly with `PYTHONPATH=Archive/marker-era` for `extraction.run` and broadening.

## Mark III

Canonical design: **Docs/Design/** — RULES_INGESTION_MARK_III_OVERVIEW.md, STAGE_A_PROSE_RECONSTRUCTION.md, STAGE_B_EVIDENCE_BINDING.md, BRUTAL-PAGES-EVALUATION-DESIGN.md.

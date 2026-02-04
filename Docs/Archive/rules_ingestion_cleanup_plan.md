# Rules Ingestion Cleanup Plan

> **DEPRECATED**: This document has been superseded by [CLEANUP_RECOMMENDATIONS.md](CLEANUP_RECOMMENDATIONS.md).
> Please refer to the new documentation for current cleanup recommendations and technical debt tracking.
> This file is preserved for historical reference only.

**Date:** 2026-01-24
**Scope:** RulesIngestion service only
**Prereq:** `Docs/ARCHITECTURE.md` (updated reference)

## Goals
- Consolidate and clarify the active pipeline path
- Reduce legacy drift (docs + scripts + unused modules)
- Make cleanup safe, phased, and testable

---

## Cleanup Targets (Candidate List)

### Low Risk (doc + organization)
- **Clarify active pipeline**: update docs to name Marker as primary extraction.
- **Entry point clarity**: document when to use `rules_ingestion_pipeline.py` vs `ingestion_service.py` vs `main.py`.
- **Output layout alignment**: ensure docs and scripts reference the same `outputs/runs/<timestamp>` pattern.

### Medium Risk (code move or removal)
- **Duplicate vocabularies**: consolidate TTRPG vocabularies into a single module and import where needed.
  - Evidence: vocabularies noted as extracted from a legacy pipeline and embedded in `enrichment.py`.

### High Risk (behavioral changes)
- **Pipeline orchestration refactor**: extracting shared helpers between CLI and service.
  - Risk: breaks CLI workflows or async job flow.

---

## Proposed Phases

### Phase 1: Documentation and Visibility (safe)
1. Add short "active path" note in docs (Marker is canonical).
2. Add entrypoint usage notes (CLI vs FastAPI).

### Phase 2: Contained Code Cleanup (guarded)
1. Move vocabularies into a shared module (no behavior change).

### Phase 3: Optional Refactor (only if needed)
1. Extract shared orchestration helpers for CLI + service.
2. Ensure test coverage for CLI and service entry points.

---

## Validation Checklist

### CLI
- `uv run python rules_ingestion_pipeline.py --help`
- Run a small PDF end-to-end with `--output-dir` and verify:
  - `<doc_id>.enriched.json`
  - `<doc_id>.graph.json`
  - `<doc_id>.metrics.json` passes 99% gate

### Service (if touched)
- Start `ingestion_service.py` and hit a simple health or config endpoint.

### Tests
- `uv run pytest tests/`

---

## Decision Log (to fill during cleanup)
- Vocabulary consolidation: location and API
- Any script updates required (if paths change)

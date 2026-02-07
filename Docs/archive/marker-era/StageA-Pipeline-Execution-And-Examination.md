> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# Stage A Pipeline Execution and Examination

**Purpose:** How to run, configure, and evaluate each pipeline (P0–P7) from the [Stage A Pipeline Exploration and Configuration Guidance](Stage%20A%20Pipeline%20Exploration%20and%20Configuration%20Guidance.md) so we can meet the pathology-suite and brutal-pages goals.

**Related:** [StageA-PathologySuite.md](StageA-PathologySuite.md), [BRUTAL-PAGES-20.md](../BRUTAL-PAGES-20.md), [extraction/README.md](../../extraction/README.md).

---

## 1. Goals we are accomplishing

- **Stage A output:** Deterministic MarkerStream (and Chunk[]) with correct reading order, region separation, and semantic boundaries so Stage B can group without fixing extraction errors.
- **Evaluation set:** Brutal pages (pipeline page indices from Alien Core, PHB, Player Core) plus standalone S5/S6/S7 PDFs (forms, tables, control). See BRUTAL-PAGES-20.md §1–§5.
- **Success criteria:** The 11 testable criteria in BRUTAL-PAGES-20.md §2 (no interleaving, stat block/spell/feat integrity, trait line not SectionHeader, etc.).

---

## 2. Pipeline-by-pipeline: where it lives and how to use it

### P0 — Baseline: Current Marker pipeline

**Status:** Implemented and used in production.

| What           | Where / How                                                                                                                                                                                                                                                                                                                         |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Invocation** | Marker is run via the `marker_single` CLI. No Python API; subprocess only.                                                                                                                                                                                                                                                          |
| **Code**       | `RulesIngestion/extraction/marker_runner.py`: `run_marker()`, `run_marker_and_stream()`, `raw_to_blocks()`, `blocks_to_marker_stream()`.                                                                                                                                                                                            |
| **CLI**        | From RulesIngestion root: `uv run python -m extraction.run <pdf_path> --doc-id <id> --output-dir <dir> [--check-gates]`. Multi-PDF: `--pdfs a.pdf b.pdf` or `--folder <dir>`.                                                                                                                                                       |
| **Config**     | Marker itself: no config passed today; `marker_single <path> --output_dir <dir> --output_format json`. Pin Marker (and Surya) version via environment/container for determinism.                                                                                                                                                    |
| **Output**     | `marker_stream.json`, `chunks.json`, `logical_document.json`, `drop_records.json`, `metrics.json` in `--output-dir`.                                                                                                                                                                                                                |
| **Examine**    | 1) Run on one brutal-page PDF: `uv run python -m extraction.run blind_eval/brutal_pages/BrutalPage1.pdf --doc-id alien-1 --output-dir out/brutal1`. 2) Inspect `out/brutal1/marker_stream.json` and `chunks.json` for reading order and block types. 3) Run structural fidelity metrics (M-A9, M-A11) if implemented for that page. |

**To accomplish goals:** Apply Configuration Guidance recommendations: pin Marker version in Docker/uv; enable Surya tasks `layout`, `ocr_with_boxes`, `table` if Marker exposes them; add instrumentation to detect cross-column overlap in reading order; preserve style attributes in MarkerStream if Marker outputs them.

---

### P1 — Marker “strict layout” variants

**Status:** Not implemented. Depends on Marker exposing options.

| What               | Where / How                                                                                                                                                                                                                                                                                                                   |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Invocation**     | Same as P0 if no extra flags exist.                                                                                                                                                                                                                                                                                           |
| **Code**           | Same as P0; no separate module.                                                                                                                                                                                                                                                                                               |
| **Examine**        | 1) Check Marker CLI and docs: `marker_single --help` and Marker repo for flags like column detection, reading-order mode, or merge thresholds. 2) If present, add optional CLI args in `extraction.run` and pass them through `marker_runner.run_marker()`. 3) Run on pathology suite and compare interleaving/metrics vs P0. |
| **If unavailable** | Treat P1 as P0 and rely on P2/P3 for better layout.                                                                                                                                                                                                                                                                           |

---

### P2 — Surya-based extraction

**Status:** Not implemented. Surya is the engine underneath Marker; we would call Surya directly for finer control.

| What           | Where / How                                                                                                                                                                                                                                                                                                                                                                                                          |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Source**     | [datalab-to/surya](https://github.com/datalab-to/surya) — OCR, layout, reading order, table recognition.                                                                                                                                                                                                                                                                                                             |
| **Invocation** | Surya API/CLI: run tasks `layout`, `ocr_with_boxes`, `table` (and combine outputs). Typically Python API, not subprocess.                                                                                                                                                                                                                                                                                            |
| **Adapter**    | Build a **Surya → MarkerStream** adapter: take Surya’s layout + OCR output (bounding boxes, reading_order, region labels), map to our `MarkerBlock` schema (page_index, text, bbox, raw_block_type, section_hierarchy), sort by reading order, write same `marker_stream.json` so downstream (chunker, Stage B) is unchanged. New module e.g. `extraction/surya_runner.py` + optional `--profile surya` in `run.py`. |
| **Examine**    | 1) Install Surya in a venv; run on one brutal PDF and dump layout + OCR JSON. 2) Inspect `reading_order` and region labels. 3) Implement adapter; run extraction with `--profile surya` on brutal pages; compare `marker_stream.json` and metrics to P0.                                                                                                                                                             |
| **Config**     | Per Guidance: run layout + ocr + table; reconstruct order from `reading_order`; use region labels to separate sidebars; preserve style if Surya returns it.                                                                                                                                                                                                                                                          |

---

### P3 — Docling

**Status:** Not implemented. External pipeline.

| What           | Where / How                                                                                                                                                                                                                                                                                                     |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Source**     | Docling (e.g. [docling](https://github.com/DS4SD/docling)) — Heron layout model, reading-order reconstruction.                                                                                                                                                                                                  |
| **Invocation** | Docling CLI or Python API; output is typically structured (e.g. paragraphs, tables).                                                                                                                                                                                                                            |
| **Adapter**    | **Docling → MarkerStream**: map Docling’s output (paragraphs, headings, tables) to our blocks (page, bbox, text, block_type); assign logical page from Docling’s page model; sort by Docling’s reading order; write `marker_stream.json`. New module e.g. `extraction/docling_runner.py` + `--profile docling`. |
| **Examine**    | 1) Run Docling on one brutal PDF; inspect JSON/Markdown output and reading order. 2) Implement adapter; run on pathology suite; compare metrics to P0/P2.                                                                                                                                                       |
| **Config**     | Per Guidance: Heron layout model; enable reading-order reconstruction; table model; pin weights; disable randomness.                                                                                                                                                                                            |

---

### P4 — PDF-Extract-Kit

**Status:** Not implemented. External toolkit.

| What           | Where / How                                                                                                                                                                                                                                      |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Source**     | [opendatalab/PDF-Extract-Kit](https://github.com/opendatalab/PDF-Extract-Kit) — layout detection (e.g. DocLayout-YOLO), table recognition; **reading-order sorting planned but not yet available**.                                              |
| **Invocation** | Per their docs (CLI or API).                                                                                                                                                                                                                     |
| **Adapter**    | Use for **segmentation only**; combine with a reading-order engine (e.g. Surya layout task or custom sort by bbox). Output region labels and bboxes; run OCR (e.g. Surya or P5) inside each region; then build MarkerStream from regions + text. |
| **Examine**    | 1) Run PDF-Extract-Kit on one brutal page; inspect layout/table output. 2) If reading-order module appears, run full pipeline and add adapter; else use as P4+Surya hybrid.                                                                      |

---

### P5 — TrOCR ladder

**Status:** Not implemented. OCR-only (no layout).

| What        | Where / How                                                                                                                                                                                                                                                                                                                                                                                           |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Role**    | OCR fallback or improvement **within** regions produced by another pipeline (P0/P2/P4).                                                                                                                                                                                                                                                                                                               |
| **Examine** | 1) Identify TrOCR-based pipeline (e.g. from [TrOCR blog](https://medium.com/@sobhan.hota/trocr-a-robust-multi-stage-pdf-ocr-accuracy-pipeline-with-streamlit-9903f9b17ede)); run on rasterized brutal pages. 2) Compare character/word accuracy vs Marker OCR. 3) If better, integrate as optional step: e.g. for each block bbox from P0/P2, crop page image and run TrOCR, then replace block text. |
| **Config**  | Pin models; tune acceptance heuristics (min_chars_accept, non_white_ratio).                                                                                                                                                                                                                                                                                                                           |

---

### P6 — DeepSeek-OCR-2

**Status:** Not implemented. External / API.

| What        | Where / How                                                                                                                                                                                                                            |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Role**    | Document-mode OCR with reading-order awareness; potential “all-in-one” extractor.                                                                                                                                                      |
| **Examine** | 1) Check availability (API or local); run on one brutal PDF with document mode and grounding tags. 2) Inspect output format (boxes, order, text). 3) If deterministic and good, build adapter to MarkerStream; run on pathology suite. |
| **Config**  | Pin model; rasterise pages; validate reading order; ensure determinism.                                                                                                                                                                |

---

### P7 — LlamaParse

**Status:** Not implemented. External API; reference only.

| What        | Where / How                                                                                                                                                                                                                             |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Role**    | High-quality reference baseline; not for production (ToS, determinism).                                                                                                                                                                 |
| **Examine** | 1) Call API with `fast=False` on a few brutal PDFs. 2) Parse returned Markdown into blocks (headings, paragraphs, tables). 3) Compare structure and table quality to P0/P2/P3 outputs. Use to set “upper bound” for extraction quality. |

---

## 3. Recommended order of examination

1. **P0 (current):** Run on full brutal set and standalone S5/S6/S7 PDFs; record baseline metrics (structural fidelity, success criteria from BRUTAL-PAGES-20.md §2). Document Marker version and any config.
2. **P1:** Check Marker for strict-layout options; if yes, add flags and re-run; if no, skip.
3. **P2 (Surya):** Implement Surya runner + Surya→MarkerStream adapter; run on same set; compare.
4. **P3 (Docling):** Implement Docling runner + adapter; run on same set; compare.
5. **P4–P7:** As needed — P4 for segmentation hybrid, P5 for OCR upgrade, P6 for all-in-one trial, P7 for reference only.

---

## 4. Shared evaluation flow

For **any** profile (P0–P7):

1. **Input:** Same inputs: brutal-page PDFs (by pipeline page_index from full books, or standalone S5/S6/S7 PDFs). See BRUTAL-PAGES-20.md §1 and §5.
2. **Run:** Either `extraction.run` (P0/P1) or a profile-specific runner that writes `marker_stream.json` (and optionally `chunks.json`) in the same schema.
3. **Downstream:** Run Stage B (broadening) on the same `marker_stream.json`/`chunks.json` so evidence chunks are comparable.
4. **Metrics:** Compute structural fidelity (M-A9, M-A11) and the 11 success criteria in BRUTAL-PAGES-20.md §2; record per-page pass/fail.
5. **Compare:** Table of (profile × page × criterion) to choose the profile that meets gates and minimizes violations.

---

## 5. Codebase entry points (quick reference)

| Item                      | Path                                                                     |
| ------------------------- | ------------------------------------------------------------------------ |
| Stage A CLI               | `uv run python -m extraction.run`                                        |
| Marker runner             | `extraction/marker_runner.py`                                            |
| Chunker (Stream → Chunks) | `extraction/chunker.py`                                                  |
| Run orchestration         | `extraction/run.py`                                                      |
| Schemas                   | `extraction/schemas.py`                                                  |
| Structural fidelity       | `extraction/structural_fidelity_metrics.py`                              |
| Extraction README         | `extraction/README.md`                                                   |
| Brutal pages list         | `Docs/BRUTAL-PAGES-20.md`                                                |
| Pathology suite           | `Docs/Design/StageA-PathologySuite.md`                                   |
| Pipeline config guidance  | `Docs/Design/Stage A Pipeline Exploration and Configuration Guidance.md` |

Adding a new profile (e.g. P2) requires: a new runner module that produces the same `MarkerBlock` list (or equivalent JSON), and a way to select it (e.g. `--profile surya` in `run.py`) so the rest of the pipeline (chunker, gates, serialization) stays unchanged.

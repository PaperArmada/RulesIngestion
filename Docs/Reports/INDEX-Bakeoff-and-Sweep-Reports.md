# Index: Bakeoff and Sweep Reports

**Purpose:** One-place index of the most relevant bakeoff reports, ingestion-phase comparisons, and sweeps that informed best-practices documents. Use for presentations and quick lookup.

Paths are relative to `RulesIngestion/`.

---

## Ingestion phase (extraction / Stage A)

There is no single formal “DeepSeek vs Marker vs Docling” bakeoff report. The ingestion-phase evidence is design exploration + brutal-pages analysis + Stage A gate compliance:

| Path | Description |
|------|--------------|
| `Archive/marker-era/marker-era/Stage-A-Pipeline-Exploration-And-Configuration-Guidance.md` | **Proto ingestion comparison:** P1 (Marker), P2 (Surya), P3 (Docling); pros/cons, reading-order, “avoid merging across columns”; design-level, not numeric bakeoff. |
| `Archive/marker-era/marker-era/Analysis-Brutal-Pages-StageA-Hypothesis.md` | **Brutal pages Stage A:** M-A9/M-A11 metrics, column-jump hypothesis, two-column / spells / stat-block pathology. |
| `Archive/marker-era/marker-era/REPORT-Stage-A-Metric-Compliance.md` | **Marker gate compliance:** M-A2–M-A9 status; Marker-first; “not normative for Mark III.” |
| `Docs/Design/archive/BRUTAL_PAGES_METRICS.md` | Stage A/B/C metrics definitions and brutal-pages usage. |
| `Docs/Research/ocr_model_evaluation.md` | **OCR survey:** PaddleOCR, DocTR, Tesseract, LayoutParser; Docling integration; recommendations (RapidOCR/Paddle with Docling). |
| `evals/extraction/brutal_pages/ARTIFACTS-DeepSeek-vs-Marker.md` | **Artifact index:** Paths to DeepSeek OCR outputs vs Marker-derived markdown for BrutalPage3/14. |
| `evals/extraction/brutal_pages/COMPARISON-DeepSeek-vs-Marker-BrutalPage3-14.md` | **Side-by-side comparison:** DeepSeek vs Marker on BrutalPage3 and 14 (reading order, column interweaving, tables). |

---

## Embedding bakeoff

| Path | Description |
|------|--------------|
| `Docs/Reports/REPORT-Embedding-Bakeoff-Comprehensive-2026-03-04.md` | **Recent embedding bakeoff:** Model comparison under fixed corpus/benchmark/retrieval contract; default baseline selection. |
| `Docs/Workflows/WORKFLOW-Embedding-Bakeoff-Design.md` | **Design for embedding bakeoffs:** Contract (corpus, benchmark, retrieval, embedding, run-key), preflight gates, canonical corpora/tracks. |

---

## Hybrid and retrieval sweeps

| Path | Description |
|------|--------------|
| `Docs/Reports/REPORT-Hybrid-Bakeoff-2026-03-05-Full.md` | Full hybrid bakeoff results (fusion, budgets, wiring). |
| `Docs/Reports/REPORT-Hybrid-Bakeoff-Results-2026-03-04.md` | Hybrid bakeoff results (earlier run). |
| `Docs/Reports/REPORT-Hybrid-Wiring-Audit-2026-03-04.md` | Hybrid wiring audit; informs retrieval best practices. |
| `Docs/Reports/REPORT-2026-03-13-Full-Benchmark-Sweep-Atomic-and-Benchmark.md` | Full benchmark sweep (atomic + main benchmark); baseline for recommendation lock-in. |

---

## Other reports that informed best practices

| Path | Description |
|------|--------------|
| `Docs/Reports/REPORT-SWCR-Retrieval-Deep-Dive-2026-03-17.md` | SWCR retrieval deep dive; per-query and recall analysis. |
| `Docs/Reports/REPORT-2026-03-06-SWCR-Retrieval-Deep-Dive.md` | Earlier SWCR retrieval deep dive. |
| `Docs/Reports/REPORT-2026-03-06-SWCR-AutoGold-Flagged-Case-Audit.md` | AutoGold flagged-case audit. |
| `Docs/Reports/REPORT-2026-03-12-Atomic-Benchmark-Question-Surface-Review.md` | Atomic benchmark question-surface review. |
| `Docs/Reports/REPORT-Decomposition-System-Comprehensive-Review.md` | Query decomposition system review. |
| `Docs/Reports/REPORT-Query-Decomposition-Per-Query-Investigation-2026-03-17.md` | Per-query decomposition investigation. |

---

## Best-practices documents (canonical)

These workflows cite or are informed by the reports above:

| Path | Description |
|------|--------------|
| `Docs/Workflows/WORKFLOW-Ingestion-Best-Practices.md` | Canonical ingestion runbook (Mark III, A+B first, A' second). |
| `Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md` | Canonical retrieval runbook (benchmarks, protocol, merged-corpus rule). |
| `Docs/Design/ARCHITECTURE-Retrieval-Runtime-Plane.md` | Retrieval runtime architecture; references bakeoff/sweep outcomes. |

---

## Scripts

| Path | Description |
|------|--------------|
| `scripts/run_hybrid_bakeoff.sh` | Run hybrid bakeoff. |
| `scripts/run_embedding_bakeoff_multivariate.py` | Embedding bakeoff multivariate runs. |

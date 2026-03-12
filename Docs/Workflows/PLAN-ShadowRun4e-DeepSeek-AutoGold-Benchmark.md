# Plan: ShadowRun 4e Anniversary — DeepSeek Ingestion → Auto-Gold → Benchmark Run

**PDF:** `/media/drakosfire/Projects/Rules/ShadowRun4e/CAT2600A_SR4Anniversary.pdf`  
**Pages:** 379  
**Estimated DeepSeek ingestion:** ~2 hours  
**Run from:** RulesIngestion repo root, with `uv run` for Python.

---

## Overview

Three sequential phases, run agentically with a long sleep after phase 1:

1. **DeepSeek ingestion** — Run Mark III full-PDF pipeline (OCR every page with DeepSeek, Stage A+B, join). ~2 h.
2. **Auto-gold benchmark construction** — Shape the merged retrieval corpus, embed that merged corpus, then run retrieval with LLM auto-gold review and persist gold into the benchmark. A few minutes (embed + retrieval + review).
3. **Benchmark run** — Run retrieval evaluation and report metrics. A few minutes.

---

## Phase 1: DeepSeek ingestion

**What it does:** For each of the 379 pages, the pipeline:

- Renders the page to an image (PyMuPDF, 200 DPI).
- Runs **DeepSeek OCR 2** via `scripts/run_deepseek_ocr2_venv.sh` (subprocess from `extraction/ocr_worker.py`).
- Runs **Stage A** (AST parse + gates) and **Stage B** (segmentation + evidence units).
- After all pages, runs **orphan header pass** (optional, needs `OPENAI_API_KEY`), **TOC detection/binding**, and **cross-page join**.
- Writes per-page dirs and `joined.evidence_units.json`.

**Command:**

```bash
cd /media/drakosfire/Projects/DungeonOverMind/RulesIngestion
uv run python scripts/run_mark3_full_pdf.py \
  --pdf /media/drakosfire/Projects/Rules/ShadowRun4e/CAT2600A_SR4Anniversary.pdf \
  --out-dir out/mark3_evaluation \
  --stage ab
```

**Output:**

- `out/mark3_evaluation/CAT2600A_SR4Anniversary/CAT2600A_SR4Anniversary_p0/` … `_p378/` (per-page Stage A+B artifacts).
- `out/mark3_evaluation/CAT2600A_SR4Anniversary/joined.evidence_units.json`, `run_summary.json`, `EVALUATION_REPORT.md`, etc.

**Substrate for retrieval_lab:**

- **Substrate path:** `out/mark3_evaluation/CAT2600A_SR4Anniversary`
- **Document ID:** `CAT2600A_SR4Anniversary` (must match page dir prefix `CAT2600A_SR4Anniversary_pN`).

**Timing:** ~2–3 min per page → ~12–19 min per 379 pages in the best case; in practice GPU/memory can make it slower. **Plan for ~2 hours** and set sleep/wait accordingly (e.g. 2 h or 2.5 h).

**Resume:** If interrupted, re-run with `--start-page N` to resume from page N (previous page dirs are loaded from disk).

---

## Phase 2: Auto-gold benchmark construction

**Prerequisite:** Phase 1 must be complete so that `out/mark3_evaluation/CAT2600A_SR4Anniversary` exists and contains per-page `stageB.evidence_units.json` (and optionally join/orphan/TOC artifacts).

**Benchmark file:** Retrieval Lab needs a benchmark JSON with **queries** (gold can be empty for auto-gold). There is no existing ShadowRun 4e benchmark in the repo. You have two options:

- **Option A:** Create a minimal benchmark from `evals/retrieval/benchmark_template_retrieval.json`: copy to `evals/retrieval/ShadowRun4e/sr4_anniversary_benchmark_blank.json`, set `metadata.source` and add at least a few real queries (e.g. 5–10) with `required_gold`/`supporting_gold` empty so the LLM can fill them.
- **Option B:** If you already have a benchmark path (e.g. with queries and empty gold), use that.

**Experiment config:** Create a dense auto-gold config (e.g. `retrieval_lab/experiments/dense/sr4_autogold_pilot.yaml`) that points at:

- `substrate_path: "out/mark3_evaluation/CAT2600A_SR4Anniversary"`
- `document_id: "CAT2600A_SR4Anniversary"`
- `substrate_version: "v1"` (or a date)
- `min_chars: 200`
- `merge_chunks: true`
- `merge_max_chars: 2000`
- `query_batches: ["evals/retrieval/ShadowRun4e/sr4_anniversary_benchmark_blank.json"]`
- `auto_gold_review.enabled: true`, `persist_benchmark: true`, and an explicitly pinned reviewer model.

**Steps:**

1. **Embed only** (once per merged chunk recipe):

   ```bash
   uv run python -m retrieval_lab.run_experiment \
     --config retrieval_lab/experiments/dense/sr4_autogold_pilot.yaml \
     --embed-only
   ```

   Capture the printed `run_id`. This `run_id` is only valid for the exact merged chunk recipe used during embed.

2. **Retrieval + auto-gold** (uses that run_id, runs retrieval and LLM review, writes gold into the benchmark file):

   ```bash
   uv run python -m retrieval_lab.run_experiment \
     --config retrieval_lab/experiments/dense/sr4_autogold_pilot.yaml \
     --run-id <RUN_ID_FROM_STEP_1>
   ```

   Outputs: `auto_gold_review.json`, `review_queue.json`, updated benchmark with `required_gold`/`supporting_gold`/`gold_locations`, plus `REPORT.md`, `metrics.json`, etc.

**Timing:** Embedding 379 pages’ worth of units is on the order of minutes; retrieval + LLM review depends on query count and API latency — typically a few minutes for a small benchmark.

---

## Phase 3: Benchmark run

**What it does:** Run retrieval evaluation on the same substrate and benchmark (now with gold populated) and report metrics.

**Command:** Either:

- Re-use the same config and run again (with the same `--run-id`) to get a clean metrics report, or
- Run an explicit “eval-only” pass with the same config and `--run-id` to produce the final `REPORT.md` and `metrics.json`.

Example:

```bash
uv run python -m retrieval_lab.run_experiment \
  --config retrieval_lab/experiments/dense/sr4_autogold_pilot.yaml \
  --run-id <SAME_RUN_ID> \
  --experiment-name sr4_benchmark_final
```

**Timing:** A few minutes (no embed, no LLM review — just retrieval + scoring).

---

## Agentic execution summary

| Step | Action | Wait |
|------|--------|------|
| 1 | Start `run_mark3_full_pdf.py` for SR4 Anniversary PDF (phase 1). | Let it run to completion (~2 h). Use `sleep 7200` (2 h) or `sleep 9000` (2.5 h) after starting, or poll for `run_summary.json` / last page dir. |
| 2 | Create benchmark file and experiment YAML if missing (see above). | — |
| 3 | Run retrieval_lab embed-only on the merged chunk recipe, then retrieval + auto-gold (phase 2). | No long wait. |
| 4 | Run retrieval_lab benchmark eval (phase 3). | No long wait. |

**Important:**

- All Python commands must use `uv run` (RulesIngestion uses `uv`).
- DeepSeek runs in a separate venv via `run_deepseek_ocr2_venv.sh`; ensure that script and `run_deepseek_ocr2_minimal.py` are present and that the DeepSeek venv is built (first run of the venv script can take a few minutes to install deps).
- For phase 2, `OPENAI_API_KEY` must be set for the auto-gold LLM reviewer.
- Substrate path and `document_id` must match the Mark III output: `out/mark3_evaluation/CAT2600A_SR4Anniversary` and `CAT2600A_SR4Anniversary`.
- Embedding should happen only after retrieval-time chunk shaping is locked; changing `min_chars`, `merge_chunks`, or `merge_max_chars` requires a fresh embed and a new `run_id`.

---

## Checklist before running

- [ ] PDF exists at `/media/drakosfire/Projects/Rules/ShadowRun4e/CAT2600A_SR4Anniversary.pdf`.
- [ ] RulesIngestion repo has DeepSeek venv (run `bash scripts/run_deepseek_ocr2_venv.sh --create-test-image` once if needed).
- [ ] For phase 2: Benchmark JSON with queries exists; experiment YAML exists and points at substrate and benchmark.
- [ ] `OPENAI_API_KEY` set (for orphan header pass and auto-gold reviewer).
- [ ] Enough disk space under `out/mark3_evaluation` for 379 page dirs and join artifacts.

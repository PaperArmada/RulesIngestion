> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# Structural Fidelity Metrics (M-A9–M-A11) — Implementation Plan

**Purpose:** Implement the three Stage A structural-fidelity metrics from the [Stage A Addendum — Structural Fidelity & Layout-Driven Misassignment](STAGE-A-Addendum-Document-Identity-and-Multi-PDF-Normalization.md): **instrumentation only**, no behavior changes. Measure, then validate on corpus.

**Contract:** Stage A Sub-Contract — Structural Fidelity & Layout-Driven Misassignment.

---

## 1. Scope and Files

### 1.1 Extraction files we will work on

| File                                                                | Role                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `RulesIngestion/extraction/schemas.py`                              | MarkerBlock, Chunk — no change unless we add a small helper type for block+section_path.                                                                                                                                                                                                                                                                                                                                                                                                             |
| `RulesIngestion/extraction/normalize.py`                            | `build_section_path()` already exists; we use it. May add constants for outcome/continuation cues (or keep in new module).                                                                                                                                                                                                                                                                                                                                                                           |
| `RulesIngestion/extraction/chunker.py`                              | No change for instrumentation. Chunker remains the single place that assigns section_path to chunks; we derive block-level section_path the same way for metrics.                                                                                                                                                                                                                                                                                                                                    |
| `RulesIngestion/extraction/marker_runner.py`                        | No change. MarkerStream order (page, y, x, block_ordinal) is our reading order.                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `RulesIngestion/extraction/gates.py`                                | **Naming:** Existing gate uses **M-A9** for _provenance completeness_. Addendum uses **M-A9** for _structural continuity violation rate_. We will: (1) add the three new metrics as **observational only** (no gate thresholds yet); (2) use distinct keys in `metrics.json`: `structural_fidelity.M_A9_structural_continuity_violation_rate`, `M_A10_rule_outcome_misassignment_rate`, `M_A11_column_jump_structural_divergence`. Keep existing gate name `M-A9_provenance_completeness` unchanged. |
| `RulesIngestion/extraction/run.py`                                  | After chunking and before/with `_write_outputs`: compute structural-fidelity metrics and merge into `metrics["structural_fidelity"]`.                                                                                                                                                                                                                                                                                                                                                                |
| **New:** `RulesIngestion/extraction/structural_fidelity_metrics.py` | All M-A9 (structural continuity), M-A10 (outcome misassignment), M-A11 (column jump) logic. Pure functions: (marker_stream, chunks) → metric dict.                                                                                                                                                                                                                                                                                                                                                   |

### 1.2 Out-of-scope (do not change for this phase)

- No changes to chunking logic (no path smoothing, no outcome inheritance).
- No new gates/thresholds; metrics are observational only.
- No downstream (Stage B+) code.

---

## 2. Data flow and definitions

### 2.1 Block-level section_path

- **MarkerBlock** has `section_hierarchy: dict`, not `section_path`.
- **section_path** is derived via `extraction.normalize.build_section_path(block.section_hierarchy)` (same as in chunker).
- For metrics we will compute `section_path` per block from the marker stream and use that for adjacency checks. Reading order = order of `marker_stream` (already sorted by `marker_runner` / `_merge_marker_streams`: logical_page_index, bbox y, bbox x, block_ordinal).

### 2.2 L1 (first level of section path)

- **L1** = `section_path[0]` if `section_path` else `""`. Used for “same structural section” (e.g. same rule block header).

### 2.3 Bbox and centroids

- **bbox** = `(x0, y0, x1, y1)`. **x_center** = `(x0 + x1) / 2`, **y_center** = `(y0 + y1) / 2`. **Vertical distance** between two blocks = `abs(y_center_i - y_center_{i+1})` (or use bottom-of-i to top-of-i+1 if preferred; plan uses centroid distance for simplicity).

---

## 3. Metric specifications (implementable)

### 3.1 M-A9: Structural continuity violation rate

**Definition:** `violations / total_eligible_adjacent_pairs` (per document; optionally per page for diagnostics).

**Eligible pair:** Consecutive blocks `(i, i+1)` in reading order such that:

- Both blocks are **prose/rule-compatible**: normalized block type in `{"Text", "ListItem", "Footnote"}` (not Heading, Table, Figure).
- Neither block has empty text (after strip).
- Both have a non-empty section_path (so L1 is defined).

**Violation:** An eligible pair `(i, i+1)` is a violation when **all** of:

1. **L1 change:** `block_i.section_path[0] != block_{i+1}.section_path[0]`.
2. **Small vertical distance:** `vertical_distance(block_i, block_{i+1}) <= MAX_VERTICAL_DISTANCE_SAME_FLOW` (e.g. 50 pt or 0.15 × page height if we had page height; for now use a fixed pt threshold, e.g. 50).
3. **Lexical continuation cue:** The **second** block’s text (trimmed, first line or first 80 chars) starts with one of a configured set of prefixes (e.g. `"Failure"`, `"Success"`, `"Critical"`, `"If you "`, `"You "` — list to be defined in constants).

**Output:** `violations`, `eligible_pairs`, `rate = violations / eligible_pairs` (0 if eligible_pairs == 0). Also emit per-page counts for diagnostics if desired.

**Files:** `structural_fidelity_metrics.py`: e.g. `compute_structural_continuity_violation_rate(marker_stream, *, max_vertical_pt=50.0, continuation_prefixes=...)`.

### 3.2 M-A10: Rule outcome misassignment rate

**Definition:** Among chunks that look like “outcome” clauses (e.g. start with “Success”, “Failure”, “Critical Success”, “Critical Failure”), the fraction whose L1 section_path does **not** match the L1 of the **nearest preceding Heading chunk** (within same page or within a small distance).

**Chunk-level (not block-level):** We use `chunks` from the chunker. Order = list order (chunks are emitted in reading order).

**Outcome label:** Chunk’s `text` (strip, take first line or first N chars) starts with one of a configured list (e.g. `["Success", "Failure", "Critical Success", "Critical Failure", "Critical …"]`). Configurable in constants.

**Nearest preceding rule header:** The last chunk before this one that has `block_type == "Heading"` and (optionally) same `page_index` or within 1 page. If there is no preceding heading, we can either treat as “no header” (exclude from rate or count as misassigned depending on policy — plan: **exclude** so we only measure “outcome that has a preceding header but wrong path”).

**Misassignment:** Outcome chunk’s `section_path[0]` != preceding_heading_chunk’s `section_path[0]`.

**Output:** `outcome_chunks_with_header`, `misassigned_count`, `rate = misassigned_count / outcome_chunks_with_header` (0 if denominator 0).

**Files:** `structural_fidelity_metrics.py`: e.g. `compute_rule_outcome_misassignment_rate(chunks, *, outcome_prefixes=...)`.

### 3.3 M-A11: Column jump structural divergence

**Definition:** Among adjacent block pairs in reading order that qualify as a **column jump**, the fraction where **section_path (L1) also changes**. So: `count(column_jump AND section_path_change) / count(column_jump)`.

**Column jump:** For consecutive blocks `(i, i+1)` (same page):  
`abs(x_center_i - x_center_{i+1}) > COLUMN_WIDTH_THRESHOLD`.  
Use a constant, e.g. 200 pt (or make configurable). Only consider same-page pairs so we don’t mix cross-page with column layout.

**Section path change:** `section_path_i[0] != section_path_{i+1}[0]` (with empty path treated as "").

**Eligible pairs:** Same-page adjacent pairs with valid bboxes (non-zero width/height so we can compute x_center). Exclude blocks without section_path if desired; for simplicity we can include all and treat empty path as "".

**Output:** `column_jump_count`, `column_jump_and_path_change_count`, `rate = column_jump_and_path_change_count / column_jump_count` (0 if column_jump_count == 0).

**Files:** `structural_fidelity_metrics.py`: e.g. `compute_column_jump_structural_divergence(marker_stream, *, column_width_threshold_pt=200.0)`.

---

## 4. Constants and configuration

- **Continuation prefixes (M-A9):** e.g. `("Failure", "Success", "Critical ", "If you ", "You ")` — in `structural_fidelity_metrics.py` or a small `structural_fidelity_config` in normalize.py. Prefer single place in `structural_fidelity_metrics.py`.
- **Outcome prefixes (M-A10):** e.g. `("Success", "Failure", "Critical Success", "Critical Failure")` — same.
- **MAX_VERTICAL_DISTANCE_SAME_FLOW (M-A9):** 50 pt (tunable constant).
- **COLUMN_WIDTH_THRESHOLD (M-A11):** 200 pt (tunable constant).

All constants should be module-level or passed as kwargs so tests can override.

---

## 5. Implementation steps (ordered)

### Phase 1: New module and M-A9

1. Add **`extraction/structural_fidelity_metrics.py`**:
   - Imports: `MarkerBlock`, `Chunk`, `build_section_path`, `normalize_block_type`.
   - Constants: continuation prefixes, max vertical distance, column width threshold, outcome prefixes.
   - Helper: `_section_path(block: MarkerBlock) -> list[str]`.
   - Helper: `_is_eligible_prose_block(block: MarkerBlock) -> bool` (Text/List/Footnote, non-empty text).
   - Helper: `_vertical_distance(b1: MarkerBlock, b2: MarkerBlock) -> float`.
   - Helper: `_starts_with_continuation_cue(text: str, prefixes: tuple[str, ...]) -> bool`.
   - Function: `compute_structural_continuity_violation_rate(marker_stream: list[MarkerBlock], **kwargs) -> dict` with keys `violations`, `eligible_pairs`, `rate`, optionally `by_page`.
2. Unit tests in **`tests/extraction/test_structural_fidelity_metrics.py`** for M-A9:
   - Two adjacent prose blocks, same L1 → 0 violations.
   - Two adjacent prose blocks, different L1, small vertical distance, second starts with "Failure" → 1 violation.
   - Two adjacent prose blocks, different L1, large vertical distance → 0 violations (not same flow).
   - No eligible pairs → rate 0, no division by zero.

### Phase 2: M-A10 and M-A11 in same module

3. In **`structural_fidelity_metrics.py`**:
   - `compute_rule_outcome_misassignment_rate(chunks: list[Chunk], **kwargs) -> dict` → `outcome_chunks_with_header`, `misassigned_count`, `rate`.
   - `compute_column_jump_structural_divergence(marker_stream: list[MarkerBlock], **kwargs) -> dict` → `column_jump_count`, `column_jump_and_path_change_count`, `rate`.
4. Helpers as needed: `_x_center(bbox)`, `_starts_with_outcome(text, prefixes)`.
5. Unit tests for M-A10: chunk list with Heading then outcome chunk same L1 → 0 misassigned; Heading then outcome chunk different L1 → 1 misassigned; outcome with no preceding heading → excluded.
6. Unit tests for M-A11: two blocks same page, large x gap, same L1 → column_jump but no path change; same + different L1 → both; no column jump → not counted.

### Phase 3: Wire into run and metrics.json

7. In **`extraction/run.py`** (in `_write_outputs` or just before):
   - Import `compute_structural_continuity_violation_rate`, `compute_rule_outcome_misassignment_rate`, `compute_column_jump_structural_divergence`.
   - Call the three with `result.marker_stream` and `result.chunks` (and pass logical_doc’s marker_stream for multi-PDF — we already have a single merged stream in `result.marker_stream`).
   - Build `structural_fidelity = { "M_A9_structural_continuity_violation_rate": {...}, "M_A10_rule_outcome_misassignment_rate": {...}, "M_A11_column_jump_structural_divergence": {...} }`.
   - Set `metrics["structural_fidelity"] = structural_fidelity`.
8. Ensure **`metrics.json`** written by `_write_outputs` contains this new key. No change to gate run: structural fidelity metrics are **not** gates in this phase (no pass/fail, no exit code).

### Phase 4: Validation and baseline

9. **Run on existing corpus:** e.g. run extraction on `out/StarFinder2e-PlayerCore-v2` input (or the PDFs that produced that output). Regenerate metrics with the new code and record:
   - `structural_fidelity.M_A9_structural_continuity_violation_rate.rate`
   - `structural_fidelity.M_A10_rule_outcome_misassignment_rate.rate`
   - `structural_fidelity.M_A11_column_jump_structural_divergence.rate`
10. **Document baseline** in a short note (e.g. in this doc or `out/.../structural_fidelity_baseline.txt`): document name, run date, the three rates and raw counts. This establishes the observation phase baseline for future hypothesis tests.

---

## 6. Validation checklist

- [ ] **No behavior change:** Chunking and gate logic unchanged; only new metrics added.
- [ ] **Deterministic:** Same marker_stream + chunks → same structural_fidelity numbers.
- [ ] **Tests:** All three metrics have unit tests; edge cases (no pairs, zero denominators) covered.
- [ ] **Lint:** `uv run ruff check extraction/ tests/extraction/` clean.
- [ ] **Run:** `uv run python -m extraction.run <pdf> --output-dir <dir>` produces `metrics.json` with `structural_fidelity` and the three sub-keys.
- [ ] **Baseline:** One full run on a representative PDF (e.g. StarFinder2e Player Core) and baseline rates recorded.

---

## 7. Naming and addendum alignment

| Addendum metric                           | Our key in metrics.json                                         | Note                                                       |
| ----------------------------------------- | --------------------------------------------------------------- | ---------------------------------------------------------- |
| M-A9 Structural Continuity Violation Rate | `structural_fidelity.M_A9_structural_continuity_violation_rate` | New. Existing gate M-A9 remains "provenance completeness". |
| M-A10 Rule Outcome Misassignment Rate     | `structural_fidelity.M_A10_rule_outcome_misassignment_rate`     | New.                                                       |
| M-A11 Column Jump Structural Divergence   | `structural_fidelity.M_A11_column_jump_structural_divergence`   | New.                                                       |

This keeps the addendum names and avoids changing existing gate semantics.

---

## 8. What we do not do (this phase)

- Do **not** add gate thresholds or exit-on-fail for M-A9–M-A11.
- Do **not** implement any corrective logic (no path smoothing, no outcome inheritance).
- Do **not** change chunker or Marker behavior.
- Do **not** guess semantics: only use structural + spatial + lexical cues defined above.

---

## 9. Summary

| Step | Action                                                                         |
| ---- | ------------------------------------------------------------------------------ |
| 1    | New `extraction/structural_fidelity_metrics.py` with M-A9 logic and constants. |
| 2    | Unit tests for M-A9.                                                           |
| 3    | Add M-A10 and M-A11 to same module; unit tests.                                |
| 4    | Wire all three into `run.py` → `metrics["structural_fidelity"]`.               |
| 5    | Run on corpus, record baseline, validate checklist.                            |

After this plan is done we have **observable** structural-fidelity metrics and a baseline for the **observation phase** and future single-hypothesis interventions (per addendum experiment ladder).

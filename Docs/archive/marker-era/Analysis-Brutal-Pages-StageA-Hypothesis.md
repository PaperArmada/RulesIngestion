> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# Brutal Pages Extraction — Analysis in Hypothesis Framing

**Date:** 2026-02-06  
**Run:** 35 PDFs, `profile=marker`, `scripts/run_brutal_pages.py`  
**Output:** `RulesIngestion/out/brutal_pages/<stem>/` per PDF  
**Purpose:** Interpret extraction results in terms of the Stage A hypothesis (linearization/structural fidelity, not OCR).

---

## 1. Hypothesis (Stage A Pathology Suite)

We are **not** failing at “chunking.” We are failing at **document linearization** under complex layouts.

- **Stage A responsibility:** Produce a trustworthy **Document Linearization** — ordered stream of blocks with bboxes, region identity, reading order, and block types that allow template detection.
- **Failure mode:** Any output where reading order does not reflect authorial intent well enough for templates and headings to remain contiguous. If Stage A interleaves columns or mixes regions, templates become non-local, adjacency invariants collapse, and Stage B cannot “unmix” content.
- **Evaluation:** Stage A must be evaluated primarily on **structural fidelity** (region segmentation + reading order), not OCR character accuracy. OCR typos can be corrected later.

_Source: `Docs/Design/StageA-PathologySuite.md` §0–§2._

---

## 2. Run Configuration and Outputs

- **Command:** `uv run python scripts/run_brutal_pages.py` (default `--profile marker`).
- **Inputs:** All `*.pdf` under `blind_eval/brutal_pages/` (21 BrutalPage N, Alien/PHB/Player Core extracts; S5 table PDFs; S6 form PDFs; S7 control).
- **Per-PDF outputs:** `marker_stream.json`, `chunks.json`, `logical_document.json`, `drop_records.json`, `metrics.json` (including `structural_fidelity`; optional `gates` when `--check-gates`). Metric definitions: §2.1.

---

## 2.1 Metrics Definitions

We use two separate metric systems. **Structural fidelity** (below) is always computed and written to `metrics.json`; **gates** are optional (run with `--check-gates`) and use different metrics with the same M-A naming band.

### Structural fidelity (observational; 0 = goal)

These metrics appear under `metrics.json` → `structural_fidelity`. They count **violations** of structural assumptions. **Goal: 0 violations / 0% rate**; any value above zero indicates a detected failure mode. They do not change pipeline behavior.

| Name (key in JSON)                          | What it measures                                                                                                                                                                                                                                                                                                                       | Output fields                                                                                | Goal                                                                                                       |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| **M-A9** structural continuity              | Consecutive prose blocks (same or adjacent page) where the **section path L1 changes** despite **small vertical distance** and the second block **starts with a continuation cue** (e.g. "Failure", "Success", "If you "). Such pairs indicate a likely spurious section boundary (e.g. trait line misclassified as SectionHeader).    | `violations`, `eligible_pairs`, `rate` (violations/eligible), `by_page`                      | **0** violations, **0%** rate                                                                              |
| **M-A10** rule outcome misassignment        | Chunks whose text starts with an outcome label (e.g. "Critical Success", "Failure") but whose **section path L1 differs from the preceding Heading** within one page. Indicates outcome text attributed to the wrong rule/section.                                                                                                     | `outcome_chunks_with_header`, `misassigned_count`, `rate`                                    | **0** misassigned, **0%** rate                                                                             |
| **M-A11** column-jump structural divergence | Same-page adjacent block pairs where the **horizontal gap** between block centers exceeds a column-width threshold (~200 pt). Among those "column jumps," how many also have **L1 (section path) change**? High rate means column transitions consistently coincide with section-path change (reading order vs. hierarchy misaligned). | `column_jump_count`, `column_jump_and_path_change_count`, `rate` (path_change / column_jump) | **0** column jumps ideal; when jumps exist, **lower rate** is better (0% = jumps do not cause path change) |

**Note:** In the pathology suite, "M-A9" in narrative refers to **structural continuity** (above). The gates module uses a different **M-A9** (provenance completeness); see below.

### Gates (threshold-based; optional, `--check-gates`)

Gates are **pass/fail thresholds** for "proceed to Stage B." They are **not** violation counts. Each gate produces a **value** and a **threshold**; the gate **passes** when the value meets the threshold (e.g. ≥ 0.99 or ≤ 0.01). Implemented in `extraction/gates.py`; reported in `metrics.json` → `gates` only when `--check-gates` is set.

| Gate                         | What it measures                                                 | Threshold      | Pass condition     |
| ---------------------------- | ---------------------------------------------------------------- | -------------- | ------------------ |
| M-A2 page coverage           | Fraction of pages that have at least one block                   | ≥ 0.99         | value ≥ 0.99       |
| M-A3 block retention         | Fraction of (non–form-part) blocks retained after drops          | ≥ 0.995        | value ≥ 0.995      |
| M-A4 span validity           | Fraction of chunks with valid span_start/span_end                | ≥ 0.999        | value ≥ 0.999      |
| M-A5 structural address      | Fraction of chunks with doc_id and (section_path or page)        | ≥ 0.95         | value ≥ 0.95       |
| M-A6 unknown block rate      | Fraction of blocks with block_type Unknown                       | ≤ 0.01         | value ≤ 0.01       |
| M-A7 fragmentation           | p95(blocks per page) vs median; no extreme fragmentation         | p95 ≤ 5×median | ratio within bound |
| M-A8 text entropy            | Fraction of non-table chunks with "weird" character ratio ≤ 0.15 | ≥ 0.98         | value ≥ 0.98       |
| M-A9 provenance completeness | Fraction of chunks with full A-DOC-INV-4 provenance fields       | = 1.0          | value = 1.0        |

**Summary:** For **structural fidelity**, we measure violations; **0 is the goal**. For **gates**, we measure ratios against thresholds; **failing** means the value does not meet the threshold.

---

## 3. Summary of Metrics Across Page Types

### 3.1 Empty or Near-Empty Extraction

| Stem        | Blocks | Chunks | M-A9 (viol / eligible / rate) | M-A11 (jumps / path-change / rate) |
| ----------- | ------ | ------ | ----------------------------- | ---------------------------------- |
| BrutalPage4 | 0      | 0      | 0 / 0 / —                     | 0 / 0 / —                          |
| DnD5eForms  | 0      | 0      | 0 / 0 / —                     | 0 / 0 / —                          |

**Interpretation:** No blocks produced. Likely image-only or failed OCR/layout; these PDFs may require a raster/OCR path (as noted in BRUTAL-PAGES-20 §5 for DnD5eForms).

### 3.2 Control (S7 — Single-Column)

| Stem                 | Blocks | Chunks | M-A9       | M-A11     |
| -------------------- | ------ | ------ | ---------- | --------- |
| FateCoreSingleColumn | 10     | 1      | 0 / 1 / 0% | 0 / 0 / — |

**Interpretation:** Single-column baseline behaves as expected: no column jumps, no structural continuity violations, one contiguous chunk. **Control supports the harness.**

### 3.3 Two-Column / Spells / Stat Blocks (High M-A11)

Where layout is two-column and section path is derived from headings, column jumps frequently coincide with section-path change (M-A11 rate high):

| Stem         | Blocks | Chunks | M-A9 (viol / rate) | M-A11 (jumps / path-change / rate) |
| ------------ | ------ | ------ | ------------------ | ---------------------------------- |
| BrutalPage1  | 29     | 15     | 0 / 0%             | 16 / 15 / **93.8%**                |
| BrutalPage9  | 32     | 14     | 3 / 16.7%          | 16 / 16 / **100%**                 |
| BrutalPage10 | 40     | 25     | 2 / 20%            | 26 / 26 / **100%**                 |
| BrutalPage11 | 31     | 14     | 0 / 0%             | 14 / 14 / **100%**                 |
| BrutalPage17 | 56     | 32     | 4 / 25%            | 26 / 25 / **96.2%**                |
| BrutalPage21 | 56     | 27     | 4 / 12.5%          | 18 / 17 / **94.4%**                |

**Interpretation:** Consistent with the hypothesis: **reading order crosses columns, but section hierarchy (path) changes at those same transitions**, so we get “column jump + path change” frequently. That implies two-column pages are at risk of TOC+body merge (BrutalPage1), spell/stat-block interleaving (BrutalPage9/10/11/17/21), and trait-line-as-false-header (Player Core spells). High M-A11 **confirms** that structural fidelity (not OCR) is the right lens.

### 3.4 M-A9 Continuity Violations (Spurious Section Boundaries)

Pages with non-zero M-A9 violations (possible false section boundaries, e.g. trait line as SectionHeader):

| Stem                     | M-A9 violations | Eligible pairs | Rate  |
| ------------------------ | --------------- | -------------- | ----- |
| BrutalPage16             | 3               | 22             | 13.6% |
| BrutalPage17             | 4               | 16             | 25%   |
| BrutalPage21             | 4               | 32             | 12.5% |
| BrutalPage9              | 3               | 18             | 16.7% |
| BrutalPage18             | 2               | 18             | 11.1% |
| BrutalPage19             | 2               | 18             | 11.1% |
| BrutalPage15             | 1               | 23             | 4.3%  |
| BrutalPage3              | 1               | 23             | 4.3%  |
| BrutalPage8              | 1               | 14             | 7.1%  |
| Starfinder2eTable1       | 1               | 8              | 12.5% |
| Starfinder2eTable2       | 1               | 10             | 10%   |
| Starfinder2eTables-multi | 1               | 10             | 10%   |

**Interpretation:** Player Core spells chapter (e.g. pipeline 334, 341, 348, 352, 356, 360) and similar two-column spell/stat pages show the most M-A9 violations. Aligns with BRUTAL-PAGES-20 criterion 10 (trait line not SectionHeader) and criterion 11 (lower M-A9/M-A11 on spells chapter).

### 3.5 Tables (S5)

| Stem                     | Blocks | Chunks | M-A11 rate       |
| ------------------------ | ------ | ------ | ---------------- |
| DnD5eTable3              | 214    | 114    | **100%** (43/43) |
| DnD5eTable-multi         | 185    | 99     | **97%** (32/33)  |
| Starfinder2eTable2       | 70     | 52     | **100%** (15/15) |
| Starfinder2eTables-multi | 116    | 57     | **100%** (30/30) |
| DnD5eTable1              | 113    | 12     | 17.2% (5/29)     |
| Starfinder2eTable1       | 57     | 13     | 33.3% (3/9)      |

**Interpretation:** Dense table pages with multiple columns often show high M-A11 (column jump + path change). Table structure and TOC/prose on same page (e.g. Starfinder2eTable1) can yield lower M-A11 if section path is stable across column jumps. Table-specific success (row/column order, no table–prose bleed) still needs per-criterion checks against BRUTAL-PAGES-20 §5.

### 3.6 Forms (S6)

| Stem                          | Blocks | Chunks | M-A11 rate |
| ----------------------------- | ------ | ------ | ---------- |
| FateCoreForms                 | 287    | 5      | 10% (2/20) |
| Swords&WizardryCharacterSheet | 110    | 1      | 0% (0/17)  |
| DnD5eForms                    | 0      | 0      | —          |

**Interpretation:** FateCoreForms has many small blocks but only 5 chunks (possible over-merge or few natural boundaries). S&W character sheet is one large chunk (110 blocks → 1 chunk); form structure may be flattened. Criterion 6 (form labels not as narrative headings) and “no form bleed” require inspecting chunk content and section_path, not just rates.

---

## 4. Mapping to the 11 Success Criteria (BRUTAL-PAGES-20 §2)

| #   | Criterion                                                 | This run (marker profile)                                                                                                                                                                                     |
| --- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | No right-column sidebar interweaving (Alien Core)         | Not evaluated per chunk on this run; M-A11 high on Alien-style pages suggests column/sidebar risk.                                                                                                            |
| 2   | Stat block from creature name to next creature name       | Not evaluated; would require chunk-content inspection for stat-block pages.                                                                                                                                   |
| 3   | Spell from name to next spell name                        | Not evaluated; high M-A11 on spell pages (e.g. BrutalPage9/10/11) suggests interleaving risk.                                                                                                                 |
| 4   | No two-column interleaving in a single chunk              | High M-A11 rates support that **when** we jump columns, section path often changes — consistent with interleaving or wrong ordering; per-chunk interleave check not done.                                     |
| 5   | Feat/invocation from name to next name                    | Not evaluated; would need PHB feat/invocation page chunk inspection.                                                                                                                                          |
| 6   | Section from correct heading; no flavor-to-wrong-creature | Not evaluated; Alien page 59 (BrutalPage5) has 0 M-A11 path-change (9 jumps, 0 with path change) — may be favorable for this criterion.                                                                       |
| 7   | Continuation chunks carry semantic section name           | Not evaluated; would need continuation-page chunk inspection.                                                                                                                                                 |
| 8   | Full stat blocks not truncated by size                    | Not evaluated; would need stop reasons and chunk boundaries.                                                                                                                                                  |
| 9   | TOC and body text not merged                              | BrutalPage1 (TOC + stat block) has M-A11 93.8% — column jump and path change common; **suggests TOC/body merge risk**. Per-chunk check not done.                                                              |
| 10  | Trait line not SectionHeader (Player Core)                | M-A9 violations on BrutalPage15/16/17/18/19/21 (Player Core spells) **support** that some block boundaries (e.g. trait lines) may be misclassified; criterion 10 needs block-type audit on pipeline page 330. |
| 11  | Player Core spells: low M-A9/M-A11                        | Current run: BrutalPage16–21 show M-A9 up to 25% and M-A11 67–100% on several pages; **baseline established** for comparison with future pipelines.                                                           |

---

## 5. Conclusions

1. **Hypothesis alignment:** The run supports evaluating Stage A on **structural fidelity**, not OCR. Empty extractions (BrutalPage4, DnD5eForms) are edge cases (likely image-only). Control (FateCoreSingleColumn) is clean. Two-column and table-heavy pages show high M-A11 (column jump + path change), consistent with reading-order/section-path divergence and with the documented failure modes (TOC+body merge, spell/stat-block interleaving, trait-line false headers).
2. **M-A11 as signal:** Where M-A11 rate is high, column transitions tend to coincide with section-path changes — a direct proxy for “wrong” linearization from the perspective of section hierarchy. Useful for pipeline comparison and for targeting pages for manual chunk inspection.
3. **M-A9 as signal:** Non-zero M-A9 on Player Core spells and some table pages suggests spurious section boundaries (e.g. trait lines as SectionHeader); aligns with criterion 10 and 11.
4. **Forms and tables:** Block/chunk counts and M-A11 leave open whether form labels are misclassified (S6) or table row/order preserved (S5); **per-criterion checks** (inspect chunks and, where applicable, block types) remain to be done.
5. **Next steps:** (a) Per-page pass/fail for the 11 criteria using chunk content and block types; (b) run with `--profile surya` when Surya is implemented and compare M-A9/M-A11 and criteria; (c) add or refine metrics for “TOC+body in same chunk” and “spell name to next spell name” boundaries for automation.

---

## 6. Reference: Full Metrics Table

| Stem                          | Blocks | Chunks | M-A9 viol | M-A9 eligible | M-A9 rate | M-A11 jumps | M-A11 path-chg | M-A11 rate |
| ----------------------------- | ------ | ------ | --------- | ------------- | --------- | ----------- | -------------- | ---------- |
| BrutalPage1                   | 29     | 15     | 0         | 21            | 0%        | 16          | 15             | 93.8%      |
| BrutalPage2                   | 21     | 9      | 0         | 14            | 0%        | 3           | 3              | 100%       |
| BrutalPage3                   | 30     | 5      | 1         | 23            | 4.3%      | 8           | 6              | 75%        |
| BrutalPage4                   | 0      | 0      | 0         | 0             | —         | 0           | 0              | —          |
| BrutalPage5                   | 33     | 22     | 0         | 20            | 0%        | 9           | 0              | 0%         |
| BrutalPage6                   | 38     | 24     | 0         | 1             | 0%        | 24          | 24             | 100%       |
| BrutalPage7                   | 27     | 5      | 0         | 3             | 0%        | 0           | 0              | —          |
| BrutalPage8                   | 42     | 24     | 1         | 14            | 7.1%      | 19          | 12             | 63.2%      |
| BrutalPage9                   | 32     | 14     | 3         | 18            | 16.7%     | 16          | 16             | 100%       |
| BrutalPage10                  | 40     | 25     | 2         | 10            | 20%       | 26          | 26             | 100%       |
| BrutalPage11                  | 31     | 14     | 0         | 16            | 0%        | 14          | 14             | 100%       |
| BrutalPage12                  | 25     | 9      | 0         | 12            | 0%        | 9           | 8              | 88.9%      |
| BrutalPage13                  | 55     | 26     | 0         | 36            | 0%        | 27          | 19             | 70.4%      |
| BrutalPage14                  | 75     | 30     | 0         | 13            | 0%        | 13          | 0              | 0%         |
| BrutalPage15                  | 53     | 21     | 1         | 23            | 4.3%      | 14          | 13             | 92.9%      |
| BrutalPage16                  | 70     | 30     | 3         | 22            | 13.6%     | 27          | 21             | 77.8%      |
| BrutalPage17                  | 56     | 32     | 4         | 16            | 25%       | 26          | 25             | 96.2%      |
| BrutalPage18                  | 46     | 19     | 2         | 18            | 11.1%     | 15          | 10             | 66.7%      |
| BrutalPage19                  | 46     | 19     | 2         | 18            | 11.1%     | 15          | 10             | 66.7%      |
| BrutalPage20                  | 51     | 1      | 0         | 44            | 0%        | 18          | 0              | 0%         |
| BrutalPage21                  | 56     | 27     | 4         | 32            | 12.5%     | 18          | 17             | 94.4%      |
| DnD5eForms                    | 0      | 0      | 0         | 0             | —         | 0           | 0              | —          |
| DnD5eTable1                   | 113    | 12     | 0         | 1             | 0%        | 29          | 5              | 17.2%      |
| DnD5eTable2                   | 105    | 2      | 0         | 4             | 0%        | 0           | 0              | —          |
| DnD5eTable3                   | 214    | 114    | 0         | 0             | —         | 43          | 43             | 100%       |
| DnD5eTable-multi              | 185    | 99     | 0         | 7             | 0%        | 33          | 32             | 97%        |
| FateCoreCheatSheet            | 96     | 50     | 0         | 1             | 0%        | 10          | 5              | 50%        |
| FateCoreForms                 | 287    | 5      | 0         | 0             | —         | 20          | 2              | 10%        |
| FateCoreSingleColumn          | 10     | 1      | 0         | 1             | 0%        | 0           | 0              | —          |
| Starfinder2eTable1            | 57     | 13     | 1         | 8             | 12.5%     | 9           | 3              | 33.3%      |
| Starfinder2eTable2            | 70     | 52     | 1         | 10            | 10%       | 15          | 15             | 100%       |
| Starfinder2eTable3            | 65     | 47     | 0         | 2             | 0%        | 15          | 0              | 0%         |
| Starfinder2eTable4            | 253    | 12     | 0         | 6             | 0%        | 27          | 0              | 0%         |
| Starfinder2eTables-multi      | 116    | 57     | 1         | 10            | 10%       | 30          | 30             | 100%       |
| Swords&WizardryCharacterSheet | 110    | 1      | 0         | 0             | —         | 17          | 0              | 0%         |

_Sources: `out/brutal_pages/<stem>/metrics.json`, `marker_stream.json` length = blocks, `chunks.json` length = chunks._

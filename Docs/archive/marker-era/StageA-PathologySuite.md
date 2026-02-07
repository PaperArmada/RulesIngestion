> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# StageA-PathologySuite.md

**Spec: Extraction Bakeoff Harness for Complex, Multi‑Column Rulebooks**  
**Project:** RulesIngestion Mark II / DungeonOverMind  
**Stage:** A (Extraction) — _reframed as Layout → Linearization → Blocks_  
**Status:** Draft v0.1 (comprehensive)  
**Date:** 2026-02-06

---

## 0) Why this document exists

We are not failing at “chunking.” We are failing at **document linearization** under complex layouts.

TTRPG and board‑game rulebooks contain:

- multi‑column prose
- sidebars/callout boxes
- templated “records” (spells, feats, monsters/stat blocks, items, class features)
- tables, forms/character sheets
- art and decorative separators that encode boundaries

If Stage A interleaves columns or mixes regions, then:

- templates become non-local
- adjacency invariants collapse
- Stage B cannot “unmix” content
- retrieval becomes noisy regardless of embedding quality

Therefore, Stage A must be evaluated primarily on **structural fidelity** (region segmentation + reading order), not OCR character accuracy.

We assume OCR typos can be corrected later and are not the dominant failure mode.

---

## 1) Scope and non-goals

### Goals

1. Create a **fixed, brutal 20‑page pathology suite** and a repeatable harness.
2. Compare multiple extraction pipelines (“Stage A profiles”) by **measurable, deterministic metrics**.
3. Promote pipelines via **gates** that reflect what Stage B and retrieval need.
4. Enable hybrid strategies (e.g., one tool provides layout/order, another provides text).
5. Make failure actionable: output top offenders with reproducible artifacts.

### Non‑goals

- No model training in the harness.
- No LLM-based “repair” in the extraction bakeoff.
- No probabilistic scoring/gating.
- No “overall quality” vibes—only metrics tied to observed failure modes.

---

## 2) The key reframing: what Stage A must output

Stage A is responsible for producing a trustworthy **Document Linearization projection**.

### Stage A success is:

A stable ordered stream of blocks per page with:

- bounding boxes
- region identity (main column vs sidebar vs table vs header/footer)
- reading order across regions
- block types that allow template detection (spell/stat block boundaries)

### Stage A failure is:

Any output where “reading order” does not reflect authorial intent well enough for templates and headings to remain contiguous.

---

## 3) Pathology suite overview

We maintain multiple suites to avoid overfitting to one layout family.

### 3.1 Suite definitions (recommended)

**Suite S1 — Two-column spells page**

- Primary pathology: column interleaving, record mixing across spells
- Must include at least 2 pages with:
  - dense spell entries
  - separators
  - long spell descriptions

**Suite S2 — Stat blocks with sidebars**

- Primary pathology: sidebar bleed, record truncation, heading detachment
- Must include:
  - at least 2 “monster record” pages
  - at least 1 with right-column “extra info” box
  - at least 1 spanning a page break

**Suite S3 — Feats / options templated entries**

- Primary pathology: name-heading separated from body by layout boundary
- Must include repeating pattern:
  - FEAT NAME (distinct font) → subheading/prereq → body → next FEAT

**Suite S4 — Mixed prose + callout boxes**

- Primary pathology: callout text interwoven with main narrative
- Must include:
  - at least 1 page with multiple callouts

**Suite S5 — Tables**

- Primary pathology: table content leaking into prose, row/col order corruption
- Must include:
  - at least 1 dense table with merged cells if possible

**Suite S6 — Forms / character sheets**

- Primary pathology: form fields misclassified as narrative headings and polluting section ancestry
- Must include:
  - at least 1 character sheet page
  - at least 1 adjacent page so we can detect bleed

**Suite S7 — Control suite (simple layout)**

- Single-column, minimal decorations
- Used to ensure tools do not regress on “easy mode”

### 3.2 The canonical 20-page “brutal set”

We build the 20 pages as a stratified sample:

- 6 pages: S1 (spells)
- 5 pages: S2 (stat blocks + sidebars)
- 3 pages: S3 (feats/options)
- 2 pages: S4 (callouts)
- 2 pages: S5 (tables)
- 1 page: S6 (forms)
- 1 page: S7 (control)

These counts can be tuned, but the suite must always include multi-column + sidebar + templated records.

---

## 4) Inputs and normalization

### 4.1 Page packaging

Each page is stored in two formats:

- `PDF_PAGE.pdf` (single-page PDF)
- `PAGE_RENDER.png` (fixed resolution raster, e.g., 300 DPI)

Reason: some tools prefer PDFs, others prefer raster. We evaluate both when relevant.

### 4.2 Page metadata

For each page:

- `suite_id` (S1..S7)
- `doc_id`, `book_id`, `ruleset_id`
- `page_number`
- known pathologies tags:
  - `multi_column`
  - `sidebar`
  - `templated_records`
  - `tables`
  - `forms`
  - `page_break_continuation`

### 4.3 Canonical S5/S6/S7 standalone PDFs

Standalone test assets for **Tables (S5), Forms (S6), and Control (S7)** are in `RulesIngestion/blind_eval/brutal_pages/`. These are extracted single- or multi-page PDFs (not tied to a specific pipeline run). If we can parse these accurately, we can handle nearly anything in those layout families.

- **S6:** `Swords&WizardryCharacterSheet.pdf`, `FateCoreForms.pdf`, `DnD5eForms.pdf`
- **S5:** `Starfinder2eTable1.pdf`–`Starfinder2eTable4.pdf`, `Starfinder2eTables-multi.pdf`, `DnD5eTable1.pdf`–`DnD5eTable3.pdf`, `DnD5eTable-multi.pdf`
- **S7:** `FateCoreSingleColumn.pdf`, `FateCoreCheatSheet.pdf`

Full content summaries and parsing challenges: **BRUTAL-PAGES-20.md §5**.

---

## 5) Probe annotations (the minimal “gold” for extraction)

We annotate each page with **probe units**—the smallest set of “things that must survive extraction.”

### 5.1 Probe unit types

- `HeadingProbe` (major heading and subheading)
- `RecordProbe` (spell / feat / monster stat block / item / invocation)
- `SidebarProbe` (callout box region)
- `TableProbe` (table region + optional header row)
- `ContinuationProbe` (sentence continues across boundary)

### 5.2 Probe unit schema (JSON)

Each probe defines:

- `probe_id`
- `page_id`
- `type`
- `bbox` (x0,y0,x1,y1)
- `expected_label` (e.g., spell name “Charm Person”)
- `expected_start_cue` (first line or regex)
- `expected_end_cue` (next record name, separator, or regex)
- `expected_tokens_sample[]` (10–30 distinctive tokens for matching)
- `region_class` (main / sidebar / table / header / footer)
- `level` (for headings: 1,2,3)
- `notes`

We do not require full transcription. We require just enough for deterministic scoring.

---

## 6) Candidate tools / Stage A profiles

We evaluate “Stage A profiles,” not tools in isolation.

A profile is: `(toolchain, configuration, normalization)`.

### 6.1 Profiles explicitly in scope (based on our discussions)

**P0 — Baseline: Current Marker pipeline**

- Use as-is with pinned version and config.

**P1 — Marker “strict layout” variants**

- Any available settings that influence:
  - column detection
  - reading order heuristics
  - region separation
- If Marker exposes none, P1 is omitted.

**P2 — Surya-based extraction**

- Surya provides OCR + layout + reading order + tables.
- Either direct Surya output or via an adapter.

**P3 — Docling conversion pipeline**

- Docling emphasizes structured conversion; can be paired with different OCR backends.

**P4 — PDF-Extract-Kit**

- Designed for complex PDF extraction; treat as layout+structure first.

**P5 — TrOCR “strategy ladder” pipeline**

- Multi-stage: raster preprocess → TrOCR → PaddleOCR for detection/layout → line-level TrOCR → fallback (Tesseract / vector text).
- Goal: robustness and layout detection stability.

**P6 — DeepSeek‑OCR‑2 document mode**

- VLM-based OCR with strong layout and reading order behavior (must be version-pinned).
- Only eligible if determinism requirements can be met.

**P7 — LlamaParse / similar “document parsing APIs”**

- Useful as a competitor only if:
  - it returns bbox/regions/order deterministically
  - ToS and reproducibility constraints are acceptable
- Typically treated as “reference competitor,” not guaranteed shippable.

### 6.2 Tool eligibility constraints

A tool/profile is eligible only if it can output at least:

- per-block text
- bbox
- reading order (explicit or derivable deterministically)

If a tool outputs only plain text, it cannot be evaluated for our primary failure modes.

---

## 7) Standard output contract: StageA_BlockStream v0

Every profile must be normalized into this common schema.

### 7.1 Block schema

Each block:

- `page_id`
- `block_id` (stable within run; may be reassigned during normalization)
- `bbox` (x0,y0,x1,y1) in page coordinates
- `raw_text` (normalized whitespace)
- `block_type` enum:
  - `heading`, `text`, `list`, `table`, `caption`, `footer`, `header`, `figure`, `unknown`
- `region_type` enum:
  - `main`, `sidebar`, `table`, `header`, `footer`, `figure`, `unknown`
- `reading_order_index` integer (total order)
- `confidence` float optional (if absent = 1.0)

### 7.2 Canonical ordering

Blocks are ordered by `reading_order_index`.
If missing:

- we compute a deterministic fallback order based on geometry:
  - `(region_type priority, column_index, bbox.top, bbox.left, bbox.height, bbox.width)`
- but this is always marked `structural_flags.derived_order=true`

### 7.3 Output hashing (for determinism)

We compute a normalized hash per page:

- ignore `block_id`
- hash sorted list of:
  - `(bbox_quantized, block_type, region_type, reading_order_index, text_hash)`
    Quantize bbox to reduce float jitter (e.g., 1/1000 page width units).

---

## 8) Metrics and gates (the core of the bakeoff)

### 8.1 Determinism gate (Gate 0 — non-negotiable)

Run each profile 3 times on the same inputs.

Metrics:

- `page_hash_stability`: fraction of pages with identical hash across all runs
- `suite_hash_stability`: hash of all pages combined

Gates:

- **G0.1** `page_hash_stability == 1.0`
- **G0.2** `suite_hash_stability` identical across 3 runs

Failing Gate 0 disqualifies the profile for pipeline use (may remain as reference).

---

### 8.2 Column interleaving gate (Gate 1 — deal-breaker)

This targets the “spells mixed together” pathology.

We determine column identity either from:

- tool-provided region/column metadata, or
- deterministic column binning using bbox.left distribution

Metric:

- `interleave_switches_per_100_blocks`  
  Compute the number of times reading order alternates between column A and B.

Gate:

- **G1.1** For S1/S2 pages: median switches ≤ 2 per 100 blocks
- **G1.2** Max switches ≤ 10 per 100 blocks on any page

Fail means Stage B cannot be trusted regardless of chunking.

---

### 8.3 Sidebar containment gate (Gate 2)

This targets “sidebar text bleeding into main narrative/statblocks.”

Metric:

- `sidebar_bleed_rate`
  - sidebar tokens that appear in the contiguous main-region intervals
  - divided by total sidebar tokens

Gate:

- **G2.1** On sidebar-heavy pages (S2/S4): `sidebar_bleed_rate ≤ 0.05`
- **Kill** if any page has `sidebar_bleed_rate > 0.15`

---

### 8.4 Record integrity gate (Gate 3)

This targets templated entry correctness: spells, feats, stat blocks, invocations, items.

For each `RecordProbe`:

- **Contiguity**: blocks overlapping the probe bbox should form one contiguous interval in reading order.
- **Completeness**: % of `expected_tokens_sample` that appear in extracted text for that interval.
- **Purity**: 1 - (% of tokens from adjacent record probes that appear inside the interval).

Define:

- `record_F1 = harmonic_mean(contiguity, completeness, purity)`

Gates:

- **G3.1** Spells pages (S1): median record_F1 ≥ 0.85, min ≥ 0.70
- **G3.2** Stat blocks (S2): median record_F1 ≥ 0.80, min ≥ 0.65
- **Kill** if any page merges adjacent record probes (purity < 0.70)

---

### 8.5 Heading attachment gate (Gate 4)

This targets orphan headings and detached record names.

For each `HeadingProbe`:

- find the nearest subsequent body interval in same region/column
- verify adjacency within a deterministic distance threshold
- verify no unrelated heading intervenes

Metric:

- `heading_body_attachment_rate`

Gate:

- **G4.1** `heading_body_attachment_rate ≥ 0.95` for pages with prose headings
- **G4.2** `heading_body_attachment_rate ≥ 0.98` for record-name headings (spell/monster/feat names)

---

### 8.6 Table preservation gate (Gate 5 — soft unless tables are core)

Metric:

- `table_leak_rate`: % of table probe tokens appearing in non-table blocks
- `row_order_consistency`: adjacency coherence based on bbox.top clustering

Gate:

- **G5.1** `table_leak_rate ≤ 0.10` (warn if higher; fail only if tables are benchmark-critical)

---

### 8.7 Form isolation gate (Gate 6)

Targets character sheets and forms polluting section ancestry and retrieval.

Metrics:

- `form_leak_rate`: form probe tokens appearing in non-form region blocks
- `form_heading_pollution`: headings detected on form pages that propagate to subsequent non-form pages (requires multi-page context if available)

Gate:

- **G6.1** `form_leak_rate ≤ 0.05`
- **G6.2** `form_heading_pollution == 0`

---

## 9) Composite scoring (after gates)

Only profiles passing Gates 0–4 are eligible for composite comparison.

We rank by:

1. Lowest `interleave_switches_per_100_blocks` (weighted highest)
2. Lowest `sidebar_bleed_rate`
3. Highest `record_F1` median
4. Highest `heading_body_attachment_rate`
5. Secondary: table + form metrics

We also track compute cost separately; quality wins first.

---

## 10) Experiment protocol (how we actually run this)

### 10.1 Locked conditions

- Same 20 pages
- Same renders (if raster-based)
- Same machine/OS container if possible
- Version-pinned toolchain
- No internet calls for extraction unless the profile is explicitly “API-based reference”

### 10.2 Run matrix

For each profile:

- Run 3 times (determinism)
- Save:
  - raw tool outputs
  - normalized StageA_BlockStream v0
  - page-level hashes
  - metrics report

### 10.3 Artifacts emitted per profile

- `out/<profile_id>/normalized_blocks.jsonl`
- `out/<profile_id>/metrics.json`
- `out/<profile_id>/hashes.json`
- `out/<profile_id>/offenders.md`
- `out/<profile_id>/render_overlays/` (optional but highly recommended)
  - render page image with bboxes and order numbers for top offenders

---

## 11) Offender reporting (make failures actionable)

For each failing gate, produce a ranked list of offenders:

- Interleaving offenders:
  - show sequence of column assignments with order indices
- Sidebar bleed offenders:
  - show extracted text spans that cross region boundaries
- Record integrity offenders:
  - show record interval + adjacent record intrusion evidence
- Heading attachment offenders:
  - show headings with missing body linkage

Each offender entry includes:

- `page_id`
- `probe_id` (if probe-related)
- relevant metric values
- a short excerpt (first ~200 chars)
- links to overlay visualization artifact if available

---

## 12) Stage A design implications (how we see Stage A differently)

After this bakeoff, Stage A becomes two separable components:

### 12.1 Component A: Layout segmentation (regions)

- main columns
- sidebars/callouts
- tables
- header/footer
- figures
- record boxes (stat blocks)

### 12.2 Component B: Linearization (reading order)

- total order over blocks that respects:
  - region boundaries
  - template boundaries
  - continuation cues across page breaks

This yields a modular strategy:

- Use Tool X for segmentation + order
- Use Tool Y for text extraction
- Reconcile deterministically by geometry

This is often the best path if one tool has excellent OCR but poor layout, or vice versa.

---

## 13) Hybrid extraction experiment (explicitly encouraged)

If a tool passes layout/order gates but has weaker OCR accuracy:

- we accept it as the **layout spine**
- then inject higher-quality text extraction by aligning spans:
  - match by bbox overlap / nearest neighbor within region
  - stable rules only

We measure:

- structural metrics (gates) on the combined stream
- token completeness on probes after injection

This directly operationalizes the assumption: OCR errors are not the main problem.

---

## 14) Practical candidate shortlist (what to try first)

Given our specific failures, prioritize tools that explicitly support:

- multi-column reading order
- region detection
- tables
- stable bbox output

Recommended order:

1. Marker variants (if column/order tunable)
2. Surya-based extraction (layout + order)
3. PDF-Extract-Kit (layout-first)
4. Docling (conversion pipeline with layout emphasis)
5. TrOCR ladder (robustness; may require more glue)
6. DeepSeek‑OCR‑2 (only if determinism can be guaranteed)
7. LlamaParse / Adobe (reference competitors)

---

## 15) Acceptance criteria: “highest quality extraction”

We declare Stage A extraction “highest quality” for our purposes if:

- 0 pages fail Gate 1 (interleaving) or Gate 2 (sidebar containment)
- record integrity meets Gate 3 thresholds across S1/S2
- heading attachment meets Gate 4 thresholds across all suites
- determinism is perfect across 3 runs
- and the tool produces enough metadata for downstream CDS/PSC attachment

If multiple profiles pass, select the one with:

- best structural scores
- simplest integration
- lowest operational cost

---

## 16) Implementation notes (for whoever builds the harness)

### 16.1 Minimal harness requirements

- Load page images/PDFs
- Run extractor profile
- Normalize to StageA_BlockStream v0
- Compute probe matching:
  - bbox overlap + token matching
- Compute metrics
- Generate offender report + optional overlays

### 16.2 Probe matching heuristic (deterministic)

For each probe bbox:

- collect blocks whose bbox IoU ≥ threshold (e.g., 0.1) OR whose center lies inside probe
- concatenate in reading order
- compute token presence against `expected_tokens_sample`

### 16.3 Tokenization

Use a deterministic tokenizer:

- lowercase
- strip punctuation
- split on whitespace
- remove a fixed stoplist only for certain metrics (not for completeness)

---

## 17) Directory layout (suggested)

```
StageA-PathologySuite/
  pages/
    <page_id>.pdf
    <page_id>.png
  metadata/
    pages.json
    probes.json
  profiles/
    profiles.json
  out/
    <profile_id>/
      normalized_blocks.jsonl
      metrics.json
      hashes.json
      offenders.md
      overlays/
```

---

## 18) Future extensions (optional)

- Add “page break continuation” probes and score sentence continuity across pages.
- Add “decorative separator” probes (lines) to help detect record boundaries.
- Add a small “layout drift” suite across editions or different publishers.

---

## 19) Decisions this harness gates

This harness is not just informational. It gates:

- whether Stage A is acceptable at all for a given ruleset family
- whether a tool can be used as the default extractor
- whether we must switch to a hybrid layout spine + text injection strategy
- whether we should exclude a document family from full ingestion until extraction improves

---

## 20) Quick summary

- The 20-page pathology suite is the “truth serum” for extraction.
- We judge extractors primarily on structural fidelity: columns, sidebars, record boundaries, heading attachment.
- Determinism is non-negotiable.
- OCR accuracy is secondary and can be corrected later.
- Hybrid extraction is a first-class path to “highest quality.”

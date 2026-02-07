> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# Stage A Sidebar Pruning — Implementation Plan

**Purpose:** Revise Stage A so that sidebar/navigation content is not interleaved with main-column content. Narrowly scoped: detect sidebar blocks, then either drop them before chunking or assign a distinct path so they do not merge with main text.

**Gate (addendum):** Main-column chunks must not contain sidebar text. Stage A must prune or separate sidebar blocks (deterministic, observable).

**This plan:** How to implement that gate — problem, observables, detection, options, metrics, validation.

---

## 1. Problem definition

**Sidebar interleaving** occurs when:

- A PDF has a **sidebar or navigation panel** (e.g. chapter/section TOC) in a narrow column (left or right).
- Marker emits blocks in reading order; the chunker groups consecutive blocks that share `section_path`.
- When the sidebar shares the same structural path as the main column, **sidebar text and main-column text are merged into the same chunk**.

**Observed failure:** Chunks such as:

- `INTRODUCTION` (sidebar) + `At 5th level, whenever you get a critical hit...` (main column),
- or TOC labels (`ANCESTRIES & BACKGROUNDS`, `5TH LEVEL`, `Android`, `Barathu`) adjacent to or inside main content.

**Required outcome:** Sidebar blocks do not contribute to main-content chunks. Either they are dropped before chunking, or they receive a distinct structural path and are excluded from the main chunk stream.

---

## 2. Observables (signals already in Stage A)

- **bbox** `(x0, y0, x1, y2)`: sidebar blocks sit in a **narrow x-range** or fixed strip (left/right margin).
- **Block text**: short, often all-caps or title-case section labels (e.g. `INTRODUCTION`, `Vesk`, `13TH LEVEL`).
- **Same page** as main content but **spatially distinct** (e.g. x_center in a different band than body text).

No new inputs required; detection is deterministic from existing Marker + Stage A outputs.

---

## 3. Detection approach (deterministic)

**Option A — Bbox-only (sidebar zones):**

- **Left zone:** `x1 <= SIDEBAR_X_MAX` (or `page_width_pt * fraction`). **Right zone:** `x0 >= SIDEBAR_X_MIN` (or `page_width_pt * (1 - fraction)`).
- If a block's bbox falls entirely within either zone, classify as **sidebar**. Thresholds configurable (fixed pt or fraction of page width).
- Implemented: both left and right zones; per-page width inferred from max x1 when not provided.

**Option B — Bbox + lexical cue (tighten precision):**

- Same as A, but also require block text to match a **sidebar pattern**: e.g. short (e.g. `len(strip) <= N`), or all-caps/title-case, or in an allow-list of known TOC tokens (INTRODUCTION, ANCESTRIES & BACKGROUNDS, etc.).
- Reduces risk of misclassifying main-column short lines (e.g. “Vesk” in body) if they fall in the same x-range.

**Option C — Per-document or per-page calibration:**

- Use first occurrence of obvious sidebar labels (from a small allow-list) to **infer** the sidebar x-range for that page/document; then apply Option A for the rest of the page.

Recommendation: start with **Option A** (bbox-only, configurable zone); add Option B if false positives appear.

---

## 4. Pruning options (choose one for implementation)

| Option            | Description                                                                                                                | DropRecords                | Main chunk stream                                                                                |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------- | -------------------------- | ------------------------------------------------------------------------------------------------ |
| **Drop**          | Classify block as sidebar → drop before chunking.                                                                          | New reason code `sidebar`. | Sidebar blocks never appear in any chunk.                                                        |
| **Separate path** | Assign sidebar blocks a distinct `section_path` (e.g. virtual L1 `__sidebar__`). Chunker groups them only with each other. | No drop.                   | Main stream excludes chunks that have only sidebar path; or filter chunks by path before output. |

**Plan default:** Implement **Drop** first (simpler, one code path, clear DropRecords). Separate-path can be a follow-up if we need to retain sidebar content in a side-channel.

---

## 5. Files to touch

| File                                           | Change                                                                                                                                                     |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `extraction/chunker.py` or `extraction/run.py` | Apply sidebar detection **before** chunking: filter marker_stream to exclude blocks classified as sidebar, and append DropRecords for each.                |
| `extraction/schemas.py`                        | No change (DropRecord already has `reason_code`).                                                                                                          |
| New or existing config                         | Sidebar zone params (e.g. `sidebar_x_max_pt`, or `sidebar_width_fraction`). Constants in a small module or in `extraction/` (e.g. `sidebar_detection.py`). |

**New module (recommended):** `extraction/sidebar_detection.py`:

- `is_sidebar_block(block: MarkerBlock, *, page_width_pt: float | None, sidebar_x_max_pt: float | None) -> bool`
- Optional: `sidebar_zone_from_page(blocks: list[MarkerBlock], page: int) -> tuple[float, float] | None` for calibration.

Then in the pipeline: after `blocks_to_marker_stream` (or merged stream), before `stream_to_chunks`, filter out sidebar blocks and record drops.

---

## 6. Metrics and validation

- **Observational metric (optional):** Count of blocks classified as sidebar per run (and per page), so we can tune zone/params without guessing.
- **Success:** Chunks no longer contain mixed sidebar + main-column text (manual or sampled review). DropRecords show reason `sidebar` with counts.
- **Regression:** Run existing extraction tests; ensure no unintended drops (e.g. main-column content) by adding a test that a known main-column block is not classified as sidebar.

**Validation checklist:**

- [ ] Sidebar zone (or detection rule) is configurable/tunable.
- [ ] Every dropped sidebar block has a DropRecord with reason `sidebar`.
- [ ] Sample of chunks from a document with known sidebar (e.g. StarFinder2e) shows no interleaved sidebar labels in main chunks.
- [ ] Deterministic: same marker_stream + config → same sidebar classification.

---

## 7. Implementation steps (ordered)

1. **Define gate in addendum** (already done): “Main-column chunks must not contain sidebar text; Stage A must prune or separate sidebar blocks.”
2. **Add `extraction/sidebar_detection.py`** with bbox-based `is_sidebar_block` and configurable zone (e.g. `sidebar_x_max_pt` or fraction of page width).
3. **Integrate before chunking:** In `run.py`, after building the merged marker_stream and before `stream_to_chunks`, compute which blocks are sidebar; remove them from the stream passed to the chunker and append one DropRecord per removed block with `reason_code="sidebar"`.
4. **Add unit tests:** Blocks with bbox in sidebar zone → classified as sidebar; blocks in main zone → not sidebar. Optional: integration test with a small fixture that produces one chunk that would have been mixed; after pruning, chunk must not contain the sidebar label.
5. **Run on corpus:** Re-run extraction on StarFinder2e (or same PDF set used for structural fidelity); inspect chunks and DropRecords. Confirm no “INTRODUCTION” + body in same chunk.
6. **Document:** Config params and how to tune (e.g. for left vs right sidebar, or different page widths).

---

## 8. What not to do

- Do not guess semantics (e.g. “this looks like a heading”); use only bbox and optionally simple lexical rules (short, all-caps).
- Do not repair downstream (Stage B+); pruning is Stage A only.
- Do not silently drop without DropRecords; every sidebar drop must be recorded with reason `sidebar`.

---

## 9. Reference

- **Gate:** [Stage A Addendum — Structural Fidelity](STAGE-A-Addendum-Document-Identity-and-Multi-PDF-Normalization.md) (sidebar gate: main content must not include sidebar text; prune or separate at Stage A).
- **Evidence:** `SAMPLE-CHUNKS-FOR-REVIEW.md` (e.g. chunk with “INTRODUCTION” + “At 5th level...”).

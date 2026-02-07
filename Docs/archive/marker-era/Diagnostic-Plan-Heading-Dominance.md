> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# Diagnostic Plan: Why So Many Heading Chunks?

**Problem:** Stage A produces ~99% `Heading` chunks (3,396) and 0% `Text` chunks. Stage B's `paragraph_run` rule never fires because it only groups chunks with `block_type == "Text"`. M-B5 fails (100% rule_block).

---

## 1. Evidence (Current State)

### 1.1 Marker Stream — Raw Block Types

| raw_block_type | Count  | Normalized to |
| -------------- | ------ | ------------- |
| Text           | 15,640 | Text          |
| TableCell      | 8,378  | Table         |
| SectionHeader  | 3,461  | Heading       |
| ListItem       | 571    | List          |
| Table          | 115    | Table         |
| Footnote       | 7      | Footnote      |

**Conclusion:** Marker _does_ output many Text blocks (15,640). The problem is downstream.

### 1.2 Chunk Block Types (Stage A Output)

| block_type | Count |
| ---------- | ----- |
| Heading    | 3,396 |
| Table      | 66    |
| Text       | 0     |

**Conclusion:** All content chunks are labeled Heading; none as Text.

### 1.3 Chunker primary_type Rule

```python
# extraction/chunker.py, line 92
primary_type = "Heading" if "Heading" in block_types else (block_types[0] if block_types else "Text")
```

**Implication:** If a chunk contains _any_ Heading block, the whole chunk is labeled `Heading`.

---

## 2. Root Cause Hypothesis

The chunker groups blocks by structural scope: **same section until next heading**. Each group is:

1. `[SectionHeader]` — standalone heading → `block_types = [Heading]` → `primary_type = "Heading"`
2. `[SectionHeader, Text, Text, ...]` — heading + body → `block_types = [Heading, Text, Text, ...]` → `primary_type = "Heading"`
3. `[Text, Text, ...]` — body only (e.g. before first heading, or orphan text) → `primary_type = "Text"`

Because the chunker _starts each section with the heading_ and adds following Text blocks to the same group, almost every group has at least one Heading. Hence almost every chunk is labeled `Heading`, even when most of its content is body text.

**Root cause:** The `primary_type` rule prioritizes Heading over Text whenever both exist in a group. Body text is captured but mislabeled.

---

## 3. Diagnostic Steps (Systematic)

### Step 1: Verify chunk composition (block mix per chunk)

**Goal:** Confirm that "Heading" chunks often contain multiple Text blocks.

**How:** Re-run chunker with instrumentation, or add a diagnostic that records `block_type_counts` per chunk (e.g. `{Heading: 1, Text: 4}`). Alternatively, correlate chunks back to marker_stream by `page_index` + `block_ordinals`.

**Expected:** Most Heading chunks have `block_types` like `[Heading, Text, Text, Text]` — i.e. 1 Heading + N Text blocks.

### Step 2: Find any Text-only chunks

**Goal:** See if any chunks are `block_type == "Text"` and where they would appear.

**How:** Search chunks for `block_type == "Text"`. If none, search for groups in the chunker that would be Text-only (e.g. runs of Text before the first SectionHeader on a page, or between sections with no section header).

**Expected:** Very few or zero, because the chunker flushes on Heading and then starts a new group _with_ the Heading.

### Step 3: Inspect Marker Text vs SectionHeader patterns

**Goal:** Understand layout — are body paragraphs always preceded by a SectionHeader in the stream?

**How:** Sample runs of consecutive blocks (page + ordinal order). For each SectionHeader, look at the next 5 blocks. Count how often they are Text vs another SectionHeader.

**Expected:** SectionHeaders are followed by Text blocks. The chunker correctly groups them together; the issue is the label, not the grouping.

### Step 4: Compare to contract intent

**Goal:** Clarify whether "chunk block_type" should reflect (a) structural role of the chunk (heading-led section) or (b) dominant content type (mostly prose).

**Contract (Stage A):** Chunk has `block_type` from normalized set. No explicit rule that Heading+Text must be labeled one or the other.

**Stage B contract:** `paragraph_run` groups consecutive `Text` blocks. So for Stage B to get diverse rule coverage, we need chunks labeled `Text` when they are predominantly body prose.

---

## 4. Proposed Fixes (for decision)

### Option A: primary_type by majority

If a chunk has more Text blocks than Heading blocks, use `primary_type = "Text"`. Else use `"Heading"`.

```python
text_count = sum(1 for t in block_types if t == "Text")
heading_count = sum(1 for t in block_types if t == "Heading")
primary_type = "Text" if text_count > heading_count else ("Heading" if "Heading" in block_types else block_types[0])
```

### Option B: Separate heading from body

Emit two chunks per section: (1) Heading-only chunk (metadata/signal), (2) Body-only chunk (Text). Body chunk gets `primary_type = "Text"`.

**Trade-off:** Doubles chunk count for prose sections; may create very small Heading chunks.

### Option C: Add content_category to Chunk

Keep `block_type` for structural role, add `content_category: "prose" | "tabular" | "structural"` for Stage B eligibility. Stage B uses `content_category` instead of `block_type` for `paragraph_run` eligibility.

**Trade-off:** Schema change; Stage B must be updated.

### Option D: Stage B uses block_type + composition

Stage B reads a sidecar or extended schema that records block composition (e.g. `{Heading: 1, Text: 4}`). `paragraph_run` considers a chunk "prose-like" if it has Text blocks, even when `block_type == "Heading"`.

**Trade-off:** Requires extra metadata in chunks or a separate artifact.

---

## 5. Sample Artifacts for Manual Review

See:

- `out/StarFinder2e-PlayerCore-v2/diagnostic_heading_samples.json` — chunks labeled Heading with block composition and text previews
- `out/StarFinder2e-PlayerCore-v2/diagnostic_raw_block_samples.md` — raw Marker blocks by type (Text, SectionHeader) for visual inspection

---

## 6. Next Actions

1. Review samples to confirm Heading chunks contain substantial body text.
2. Choose a fix (A–D) based on contract and downstream needs.
3. Implement chosen fix, re-run extraction + broadening, verify M-B5 improves.

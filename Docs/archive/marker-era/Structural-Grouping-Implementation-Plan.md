> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# Structural Grouping Implementation Plan

**Purpose:** Fix rule_block truncation by grouping chunks by structural identity instead of physical adjacency. Avoid disjointed spaghetti: single source of truth, clear boundaries, phased delivery.

**Related:** Stage B Contract Addendum (Rule Completeness & Semantic Closure), size_threshold_hit investigation.

---

## 1. Problem Summary

### Current Behavior (Broken on Multi-Column PDFs)

1. **Stage A (chunker):** Groups _consecutive_ blocks until section_path changes. Emits chunks in _physical_ order.
2. **Stage B (rule_block):** Iterates chunks sequentially; expands forward up to `max_following` (4) chunks or `max_chars` (1200); stops at first `same_section_prefix` failure.

On multi-column layouts, Marker reads across columns. Blocks from different rules are interleaved:

```
Physical order:  CREATE A DIVERSION (ord=15) → MENTAL (16) → body (17) → LIE content (18,20,21) → more body (22) → FEINT (24) → Failure clause (27)
```

The Failure clause (ord=27) belongs to CREATE A DIVERSION but appears _after_ FEINT. Sequential expansion stops at FEINT (boundary) and never reaches it.

### Root Cause

**Structural identity** is encoded in `section_hierarchy` but **ignored** during grouping. Chunks with the same content path (e.g. `['/page/16/SectionHeader/7', '/page/16/SectionHeader/8']`) belong to the same rule but are scattered in physical order. We stop at the first structural "boundary" (a chunk with a different path) even when that boundary is interleaved content from a sibling rule.

### Fix

Group by **content path** (structural identity), not physical adjacency. When we encounter a rule header, find _all_ chunks with the matching content path from the entire document, regardless of position.

---

## 2. Design Principles (Anti-Spaghetti)

1. **Single source of truth:** One module owns "structural identity" extraction. No duplicated logic.
2. **Clear layer boundaries:**
   - Extraction: blocks → chunks (unchanged logic; add metadata only)
   - Broadening: chunks → evidence chunks (new structural grouping mode)
3. **No scattered conditionals:** Structural grouping is a distinct code path, not if/else sprinkled across existing rules.
4. **Testability:** Each new function has a focused responsibility and can be unit-tested in isolation.

---

## 3. Data Model Additions

### 3.1 Structural Content Path (New Concept)

A **content path** is the `section_path` of a chunk that contains rule body/trait/outcome content. It has length ≥ 2 (e.g. `[L1, L4]`).

A **rule header path** has length 1 (e.g. `[L1]`). The rule's content chunks share a content path derived from the first content block that is a _structural child_ of that header.

**Definition:** For a rule header chunk with `section_path = [L1]`, its **content path** is the `section_path` of the first subsequent chunk (in iteration order) that:

- Has `section_path` of length ≥ 2
- Has `section_path[0] == L1` (same top-level section)

If no such chunk exists (e.g. orphan header at end of doc), the rule has no content path.

### 3.2 Chunk Schema (No Change)

Chunks already have `section_path: list[str]`. No schema change. We derive content path at grouping time from the chunk list.

### 3.3 EvidenceChunk Schema (Future: Addendum)

The Contract Addendum may add `rule_semantically_closed`, `missing_outcomes`. That is a separate phase. This plan focuses on **structural grouping only**.

---

## 4. Module Ownership

| Concern                                | Owner Module                     | Responsibility                                                    |
| -------------------------------------- | -------------------------------- | ----------------------------------------------------------------- |
| Extract section path from hierarchy    | `extraction/normalize.py`        | `build_section_path()` — already exists                           |
| Derive content path for a rule header  | `broadening/structural.py` (NEW) | `content_path_for_rule_header(header_chunk, chunks, chunk_index)` |
| Index chunks by content path           | `broadening/structural.py` (NEW) | `build_content_path_index(chunks)`                                |
| Rule block expansion (structural mode) | `broadening/grouper.py`          | `_apply_rule_block_expansion_structural()` — new function         |

---

## 5. New Module: `broadening/structural.py`

**Purpose:** Single place for structural identity logic. No extraction details leak here; it operates on chunks only.

### 5.1 Content Path Index

```python
def build_content_path_index(chunks: list[Chunk]) -> dict[tuple[str, ...], list[Chunk]]:
    """
    Build index: content_path -> [chunks with that exact path].

    Only index chunks with section_path length >= 2 (content chunks, not headers).
    Key is tuple for hashability.
    """
```

- Input: sorted chunk list (by page, ordinal).
- Output: `{(path0, path1, ...): [chunk_a, chunk_b, ...]}` for each unique content path.
- Chunks with empty or single-element `section_path` are not indexed (they are headers or legacy).

### 5.2 Content Path for Rule Header

```python
def content_path_for_rule_header(
    header_chunk: Chunk,
    chunks: list[Chunk],
    header_index: int,
) -> tuple[str, ...] | None:
    """
    Find the content path for a rule that starts at header_chunk.

    A rule header has section_path length 1. Its content chunks have the same
    L1 and a longer path. The content path is the path of the first chunk
    AFTER header_index that:
      - has section_path length >= 2
      - has section_path[0] == header_chunk.section_path[0]

    Returns None if no such chunk exists.
    """
```

- **Critical:** "First chunk after" is in _sorted iteration order_ (page, block_ordinal). On a single page, the first content chunk after the header is often the trait block (MENTAL, etc.) — which correctly identifies the content path for CREATE A DIVERSION.
- For LIE, the header is followed by AUDITORY... (different content path). So each header maps to at most one content path.
- Returns `None` for orphan headers (no following content with same L1).

### 5.3 Tests for `structural.py`

- `test_build_content_path_index`: empty chunks, single path, multiple paths, chunks with len(path) < 2 excluded.
- `test_content_path_for_rule_header`: header with immediate content, header with interleaved content, header with no content, header at end of list.

---

## 6. Changes to `broadening/grouper.py`

### 6.1 New Function: `_apply_rule_block_expansion_structural`

**Replaces** the sequential expansion logic for rule_block. Same signature pattern as other rules.

```python
def _apply_rule_block_expansion_structural(
    chunks: list[Chunk],
    used: set[str],
    sorted_chunks: list[Chunk],  # Same as chunks, but explicit for index lookup
    content_path_index: dict[tuple[str, ...], list[Chunk]],
    max_chars: int = RULE_BLOCK_MAX_CHARS,
) -> list[ChunkGroup]:
```

**Algorithm:**

1. Precompute `content_path_index` once before calling (in `group_chunks`).
2. Build `chunk_to_index: dict[str, int]` mapping chunk_id → position in sorted_chunks.
3. Iterate `sorted_chunks` in order (same as today).
4. For each unused Heading chunk `h`:
   - `content_path = content_path_for_rule_header(h, sorted_chunks, header_index)`.
   - If `content_path is None`: skip (orphan header).
   - `content_chunks = content_path_index.get(content_path, [])`.
   - Filter to chunks not in `used`.
   - Sort content chunks by (page_index, min(block_ordinals)) for deterministic assembly.
   - Compute combined text. Apply `max_chars` cap for over-broad rejection (M-B3); do NOT use `max_chars` as a hard stop that truncates the rule (that's the Addendum's semantic closure).
   - For this phase: if combined_len > max_chars, treat as over-broad and either (a) emit with stop_reason SIZE_THRESHOLD_HIT and record for M-B9, or (b) skip and leave for heading_span. **Decision: emit, let M-B3/M-B9 gates catch it.** This keeps the implementation simple; Addendum changes can add semantic closure override later.
   - Build ChunkGroup(header + content_chunks, rule=RULE_BLOCK).
   - Mark header and all content_chunks as used.
   - Determine stop_reason: END_OF_SECTION (structural closure) or SIZE_THRESHOLD_HIT (over-broad, for metrics).
5. Continue to next chunk.

**Key difference from current logic:** We do not stop at the first "boundary" chunk. We collect all chunks with the same content path. Physical adjacency is irrelevant.

### 6.2 Integration in `group_chunks`

```python
# Before rule application
content_path_index = build_content_path_index(sorted_chunks)

# Replace _apply_rule_block_expansion with _apply_rule_block_expansion_structural
all_groups.extend(
    _apply_rule_block_expansion_structural(
        sorted_chunks, used, sorted_chunks, content_path_index,
        max_chars=RULE_BLOCK_MAX_CHARS
    )
)
```

Remove or deprecate `_apply_rule_block_expansion` (the sequential version). The structural version fully replaces it.

### 6.3 `same_section_prefix` — No Change for rule_block

Structural grouping does not use `same_section_prefix` for rule_block. It uses the content path index. Other rules (heading_span, paragraph_run) still use `same_section_prefix` and adjacency. No modification to those.

---

## 7. Edge Cases and Invariants

### 7.1 Multiple Headers Share L1

LIE (ord=11) and CREATE A DIVERSION (ord=15) both have `section_path = ['/page/16/SectionHeader/7']`.

- For LIE: first content chunk after it (in sorted order) has path `['/page/16/SectionHeader/7', '/page/16/SectionHeader/22']` → content path for LIE.
- For CREATE A DIVERSION: first content chunk after it has path `['/page/16/SectionHeader/7', '/page/16/SectionHeader/8']` → content path for CREATE A DIVERSION.

Iteration order ensures each header is matched to the correct content path (the one that immediately follows it structurally in the document flow).

### 7.2 Content Chunks Claimed by Multiple Headers?

No. Each content path is unique. Chunks with path `[L1=7, L4=8]` belong to exactly one rule (CREATE A DIVERSION). Once we mark them as used, no other rule will claim them.

### 7.3 Chunks with Empty or Single-Element Path

- Headers with path length 1: not indexed; they trigger rule_block expansion.
- Chunks with empty path: not indexed; they remain for heading_span or paragraph_run.
- No change to how we handle these.

### 7.4 B-INV-3 / B-INV-6 (Structural Coherence)

All chunks in a rule_block group share the same content path by construction. So they satisfy "one CDS leaf path". No violation.

---

## 8. Phased Implementation

### Phase 1: Add `broadening/structural.py` (No Grouper Changes)

- Implement `build_content_path_index`.
- Implement `content_path_for_rule_header`.
- Add unit tests.
- **Gate:** All tests pass; no behavior change yet.

### Phase 2: Add Structural Rule Block Expansion

- Implement `_apply_rule_block_expansion_structural` in grouper.
- Wire it in `group_chunks`, replace old `_apply_rule_block_expansion`.
- Remove or comment out old implementation.
- **Gate:** Run Stage B on StarFinder2e-PlayerCore-v2; verify CREATE A DIVERSION includes Failure clause; check M-B4, M-B5, M-B6.

### Phase 3: Semantic Closure (Separate, Addendum)

- Add `rule_is_semantically_closed()`.
- Override size cap for rule_block until closure.
- Add M-B9.
- Not part of this structural plan.

---

## 9. File Touch Summary

| File                                  | Action                                                                 |
| ------------------------------------- | ---------------------------------------------------------------------- |
| `broadening/structural.py`            | **CREATE** — content path index, content_path_for_rule_header          |
| `broadening/grouper.py`               | **MODIFY** — add structural rule block, replace sequential; wire index |
| `tests/broadening/test_structural.py` | **CREATE** — unit tests for structural module                          |
| `tests/broadening/test_grouper.py`    | **MODIFY** — update expected rule_block behavior if needed             |
| `extraction/*`                        | **NO CHANGE**                                                          |

---

## 10. Rollback

If structural grouping causes regressions:

- Revert `grouper.py` to call `_apply_rule_block_expansion` (sequential).
- Keep `structural.py` and tests; they are additive and unused until wired.

---

## 11. Success Criteria

- CREATE A DIVERSION evidence chunk includes "Failure You don't divert the attention of any creatures...".
- M-B6 `size_threshold_hit` rate decreases (more rules closed by structure, not size).
- M-B4, M-B5 remain passing.
- No new spaghetti: structural logic lives in `structural.py`; grouper has one clear code path for rule_block.

> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# Observations: Evidence Chunk Quality Across Diverse PDFs

**Date:** 2026-02-05
**Stage:** B (Broadening) output review
**Purpose:** Catalog specific chunk quality issues with exact references for use when improving the pipeline.

---

## Guiding Principle

**Do not exclude anything we don't have a robust reason to drop.** Stage B now emits all groups and isolated eligible chunks as EvidenceChunks, annotating those outside preferred thresholds with `structural_metadata` flags rather than dropping them.

---

## DnD 5e PHB (2,154 evidence chunks)

### OBS-PHB-1: "Tier 2" — context-orphaned small chunk

- **Evidence chunk:** [201] `10e6ce6abf1552`
- **Rule:** paragraph_run | **Stop:** block_type_mismatch
- **Section:** `/page/31/SectionHeader/1 → /page/41/SectionHeader/6`
- **Pages:** [41]
- **Structural flags:** none
- **Text excerpt:** `TIER 2 (LEVELS 5-10) — In tier 2, characters are full-fledged adventurers...`

**Problem:** Out of context this is nearly meaningless. "Tier 2" only makes sense under the parent heading "Tiers of Play" which is in Chapter 2: Creating a Character.

**Signals available:**

- There is a structural heading "Tiers of Play" above this chunk on the same page, with a distinct underline.
- The section_path carries positional IDs, not semantic names. If heading ancestry were semantic (e.g. `Chapter 2: Creating a Character → Tiers of Play → Tier 2`), this chunk would be self-contextualizing.
- Other Tier chunks (1, 3, 4) all belong to the same parent heading.

**Improvement bucket:** Richer heading ancestry in `section_path` (Stage A / CDS).

---

### OBS-PHB-2: "LEVEL 20: AVENGING ANGEL" — class feature without class context

- **Evidence chunk:** [481] `9da1d95b7661e7`
- **Rule:** paragraph_run | **Stop:** block_type_mismatch
- **Section:** `/page/84/SectionHeader/17 → /page/115/SectionHeader/9`
- **Pages:** [115]
- **Text excerpt:** `LEVEL 20: AVENGING ANGEL — As a Bonus Action, you gain the benefits below for 10 minutes...`

**Problem:** Out of context, hard to understand what class or subclass this belongs to.

**Signals available:**

- Immediately before this content is "Oath of Vengeance" with a distinct line underneath, then italics "Punish Evil Doers at Any Cost", then regular text. All of this describes the Paladin class.
- Paladin has a full-page image devoted to it — the image/page break is the signal that a new class section begins.
- "Paladin" is likely the most common word in this section.
- The section_path `SectionHeader/17` on page 84 is the start of a major class section, but its semantic name isn't captured.

**Improvement bucket:** Semantic heading names in `section_path`; class/subclass hierarchy detection.

---

### OBS-PHB-3: "Fey-Touched" feat cut off from its heading

- **Evidence chunk:** [801] `6a3de9f6b01db5`
- **Rule:** paragraph_run | **Stop:** boundary_encountered
- **Section:** `/page/197/SectionHeader/1 → /page/201/SectionHeader/14`
- **Pages:** [202] | **Source chunks:** 4
- **Text excerpt:** `General Feat (Prerequisite: Level 4+) — Your exposure to the Feywild's magic grants you the following benefits. Ability Score Increase...`

**Problem:** The chunk starts at "General Feat" — the italics subheading. The feat name "Fey-Touched" is in a different, capitalized font immediately above, but a column line causes a boundary break that separates the name from the body.

**Signals available:**

- "Fey-Touched" appears in a distinct font above, as a heading. This is a repeating template: `FEAT_NAME (distinct font) → General Feat / Origin Feat (italic) → prerequisite → body → next FEAT_NAME`.
- Chapter is "Feats", subsection is "General Feats" (signaled by chapter page + underlined heading).
- Marker likely emits the feat name as a Heading block, but a column boundary stops the grouper from merging it with the body.
- The section_path should carry: `Chapter 5: Feats → General Feats → Fey-Touched`.

**Improvement bucket:** Template-aware boundary detection (feat→feat); semantic heading names; check Marker blocks around page 202 for what boundary caused the split.

---

### OBS-PHB-4: Monster stat block fragmentation

- **Evidence chunks around:** [1241] `0b2302087257f1`, [1281] `b168fdfbe09af8`, [1321] `fac54bac219c62`, [1361] `bfdef4f67b6d42`
- **Pages:** 326, 344, 349, 354
- **Text excerpts:**
  - [1241]: `UNDEAD SPIRIT — Medium Undead, Neutral — AC 11 + the spell's level...`
  - [1281]: `ACTIONS — Multiattack. The ape makes two Fist attacks. — Fist. Melee Attack Roll...` (below_preferred_mass)
  - [1321]: `GIANT WEASEL — Medium Beast, Unaligned — AC 13...` (below_preferred_mass)
  - [1361]: `REEF SHARK — Medium Beast, Unaligned` (below_preferred_mass — just the name and type!)

**Problem:** Monster stat blocks should run from one monster name to the next. Instead they're fragmented — actions split from the creature, some are just a name and type with no stats.

**Signals available:**

- Stat blocks follow a clear, repeating template: `CREATURE_NAME (distinct font) → Size Type, Alignment → AC/HP/Speed → abilities → ACTIONS → next CREATURE_NAME`.
- Marker should emit creature names as Heading blocks. Each stat block should group from one creature heading to the next.
- Column breaks and page breaks interrupt the grouper.

**Improvement bucket:** Template-aware grouping for stat blocks (monster→monster); relaxing or removing upper size threshold; check Marker output for block types around these pages.

---

### OBS-PHB-5: Spells interleaved across columns

- **Evidence chunk:** [1041] `59c3ebd7dacf7a`
- **Rule:** paragraph_run | **Stop:** size_threshold_hit
- **Section:** `/page/233/SectionHeader/1 → /page/246/SectionHeader/29`
- **Pages:** [247] | **Source chunks:** 9
- **Text excerpt:** Contains fragments of Charm Person, Chain Lightning, Chill Touch mixed together — spell metadata (casting time, range) interleaved with different spells' descriptions.

**Problem:** Multiple different spells have been merged into one chunk because the column interleaving from Marker mixed their content, and the grouper kept merging until size threshold hit.

**Signals available:**

- Each spell starts with its name in a distinct heading font.
- Spell metadata (Casting Time, Range, Components, Duration) follows a rigid template.
- Spells should be individual evidence chunks, bounded by spell-name headings.

**Improvement bucket:** Column interleaving is a Stage A / Marker issue; spell template detection for boundary rules.

---

### OBS-PHB-6: Spell chunk cuts off before Duration and description (Plant Growth)

- **Evidence chunk:** [1161]
- **Section:** Spell name appears as parent section; chunk is correctly under "Plant Growth" but that spell name doesn't appear in the chunk text.
- **Problem:** Chunk cuts off before Duration and descriptive text. Should extend until the line separator and the next spell name ("Poison Spray").
- **Improvement bucket:** Spell template boundary (spell name → next spell name); check raw Marker output for block order. Heading tuning so spell name flows into chunk.

---

### OBS-PHB-7: Two-column interleaving (chunk 209)

- **Evidence chunk:** [209]
- **Problem:** Left and right columns are interleaved in the chunk.
- **Improvement bucket:** Column interleaving (Stage A / Marker). Same bucket as OBS-PHB-5.

---

### OBS-PHB-8: Invocation cut off before details (Devouring Blade)

- **Evidence chunk:** [641]
- **Problem:** Chunk cuts off before the full invocation text. Should include: "Devouring Blade — Prerequisite: Level 12+ Warlock, Thirsting Blade — Invocation — The Extra Attack of your Thirsting Blade invocation confers two extra attacks rather than one."
- **Improvement bucket:** Template-aware boundary (invocation name → next invocation name); raise/relax MAX_CHARS for invocation blocks; check Marker for boundary cause.

---

### OBS-PHB-9: Description box and column text interwoven (chunk 401)

- **Evidence chunk:** [401]
- **Problem:** Description box on the left and main column text on the right are interwoven in the chunk.
- **Improvement bucket:** Column/sidebar separation (Marker or post-process); avoid merging distinct layout regions.

---

## Fate Core (487 evidence chunks)

### OBS-FATE-1: Initial chunks — good quality overall

Fate Core has a simple single-column layout. Chunks 1–8 (rule_block) are well-formed with good semantic content. The system generalizes well to simpler layouts.

---

### OBS-FATE-2: "Opposition" — heading-only chunk

- **Evidence chunk:** [401] `2719aeeb63a736`
- **Rule:** heading_span | **Stop:** boundary_encountered
- **Section:** `/page/92/SectionHeader/0 → /page/138/SectionHeader/1`
- **Pages:** [138]
- **Structural flags:** below_preferred_mass=True
- **Text:** `Opposition` (single word)

**Problem:** Only the word "Opposition" — too little context. The heading exists but no body text was grouped with it.

**Signals available:**

- This is a heading-span that encountered a boundary immediately. The heading's body content likely belongs to the next chunk or was consumed by a different grouping rule first.
- Could be a section divider or form element.

**Improvement bucket:** Investigate what's on page 138 in `marker_stream.json` — is the body text being consumed by a paragraph_run before the heading_span can claim it? If so, heading_span priority may need adjustment.

---

### OBS-FATE-3: Form content leaking through

- **Evidence chunk:** [481] `8f7daa1a86483e`
- **Rule:** single_chunk | **Stop:** boundary_encountered
- **Section:** `/page/301/SectionHeader/0 → /page/302/SectionHeader/9`
- **Pages:** [303]
- **Text:** `One at Great (+4)` (fragment from a skill pyramid form/character sheet)

**Problem:** This is part of a fill-in form or character sheet template. It has no standalone meaning.

**Signals available:**

- Very short text with structured format (rank + rating).
- Surrounded by similar form-like entries.
- Could detect forms by: short repeated structure, field labels without content, proximity to other form fragments.
- Stage A already marks some blocks as `Form` (ineligible), but some form content leaks through as `Text`.

**Improvement bucket:** Better form detection heuristics (short repeated patterns, character sheet templates).

---

### OBS-FATE-4: OCR spelling errors in section names

- **Problem:** Section names in evidence chunks contain OCR/spelling errors.
- **Improvement bucket:** Easy wins from an LLM pass to correct/normalize section (heading) text before or after chunking.

---

## StarFinder 2e Alien Core (1,062 evidence chunks)

### OBS-ALIEN-1: Column interweaving

General observation across multiple chunks. The two-column layout causes Marker to sometimes interleave left and right column content. This is visible in chunks where unrelated content from adjacent columns is merged.

**Improvement bucket:** Stage A / Marker extraction quality. No grouper-level fix.

---

### OBS-ALIEN-2: "TABLE OF CONTENTS" mixed with stat block continuation

- **Evidence chunk:** [2] `a40e86ce521fda`
- **Rule:** rule_block | **Stop:** end_of_section
- **Section:** `/page/1/SectionHeader/26`
- **Pages:** [1, 4]
- **Structural flags:** below_preferred_mass=True
- **Text excerpt:** `TABLE OF CONTENTS — how many actions they require. A creature always has the requisite proficiency ranks...`

**Problem:** "Table of Contents" heading gets merged with stat block explanation text from a different column. The chunk is a continuation from the left column appearing at the top of the right column.

**Signals available:**

- No punctuation at the bottom of the prior chunk — strong signal that the sentence continues.
- "TABLE OF CONTENTS" is structurally distinct (heading type, page position) from the stat block explanation text.
- Cross-column continuation could be detected by: sentence not ending in punctuation, block position metadata (left vs. right column).

**Improvement bucket:** Sentence-continuation heuristic (missing terminal punctuation = likely continuation); column position metadata from Marker.

---

### OBS-ALIEN-3: Stat block truncated by size threshold

- **Evidence chunk:** [3] `9ac6e13eddabfd`
- **Rule:** rule_block | **Stop:** size_threshold_hit
- **Section:** `/page/5/SectionHeader/8`
- **Pages:** [12] | **Source chunks:** 2
- **Text excerpt:** `VOID ZOMBIE CREATURE 1 — UNCOMMON MEDIUM UNDEAD — Perception +3; darkvision — Skills Athletics +6 — ... — Feed on Blood [one-action]...`

**Problem:** This stat block is good content but was stopped by `size_threshold_hit`. We want the full stat block through to the end. The chunk text looks complete here but the `size_threshold_hit` stop reason means the grouper cut it off rather than letting it grow to its natural boundary.

**Signal:** LLMs can handle large context. The upper size threshold (`MAX_CHARS = 2000`) is artificially constraining stat blocks and other naturally large content units.

**Improvement bucket:** Raise or remove `MAX_CHARS`. Let groups grow to natural structural boundaries (next same-level heading).

---

### OBS-ALIEN-4: Multiple stat blocks marked over_broad

- **Evidence chunks:** [4] `00b673885b73c2` (Barachius Angel), [5] `2813687cb89724` (Arqsheth), [6] `7d0822e722f9ed` (Bloodbrother), [7] `d03fd6c88563a8` (Corpse Fleet Recruiter), [10] `b0801b7bd4cb58` (Daipex)
- **All:** rule_block | size_threshold_hit | over_broad=True

**Problem:** These are complete-ish stat blocks flagged `over_broad` because they exceed `MAX_CHARS`. But they ARE coherent content units — a full stat block is exactly the right granularity for retrieval.

**Signal:** The `over_broad` flag is a false positive for stat blocks. Stat blocks are naturally 1,500–3,000+ characters and should not be penalized for size.

**Improvement bucket:** Either raise/remove `MAX_CHARS`, or make the threshold content-type-aware (stat blocks get a higher cap or no cap).

---

### OBS-ALIEN-5: Monster name lost from stat block

- **Observed around:** chunk 201 area (not directly in sample but referenced by user)
- **Problem:** The creature name (e.g., "Medusa") appears in a different font with a line under it, but gets separated from the stat block body.

**Note:** This observation was noted during review. The pattern is the same as OBS-PHB-4: creature name in distinct heading font gets split from the body by a boundary. The name is the most important piece of context for the stat block.

**Improvement bucket:** Template-aware grouping (creature-name heading should always merge with following stat block content).

---

### OBS-ALIEN-6: Young Akashic Dragon — right-column sidebar interweaving (chunk 201)

- **Evidence chunk:** [201]
- **Creature:** Young Akashic Dragon. Chunk starts at the creature's information text underneath the name and creature number (which are on a line).
- **Problem:** The book has smaller columns on the right with extra information; these are badly interweaving and interrupting the core stat block content. May be a deal-breaker for this extraction method if unsolved.
- **Signals:** Highlights specific and challenging pages to experiment on (column/layout detection).
- **Improvement bucket:** Column/sidebar separation (Marker or post-process); treat right-column "extra info" as distinct from main stat block.

---

### OBS-ALIEN-7: Wrong section and title/flavor mix (chunk 241)

- **Evidence chunk:** [241]
- **Problem:** Descriptive flavor text continues from prior chunk onto the next page until the next creature name. Chunk is wrongly assigned section "Large Fungus". Contains flavor text of one creature but the title of a different creature (which is actually above this content).
- **Improvement bucket:** Section assignment from correct heading (creature name as section); boundary = next creature name; avoid attributing flavor to wrong creature.

---

### OBS-ALIEN-8: Creature skill chunk from prior page, no semantic name (chunk 521)

- **Evidence chunk:** [521]
- **Problem:** No semantic section name. Chunk is the "skill" (or continuation) of a creature that started on the prior page. Also has right-column extra info interweaving.
- **Note:** May be improved by larger chunks (natural boundary = next creature).
- **Improvement bucket:** Same as OBS-ALIEN-6 (column separation); ensure creature-name heading propagates to continuation chunks; raise/relax MAX_CHARS.

---

## Swords & Wizardry Core Rules (286 evidence chunks)

### OBS-SW-1: Good overall quality for simple layout

S&W has a straightforward single-column layout. Most chunks are well-formed. The simple format validates that the pipeline generalizes well beyond complex two-column RPG layouts.

---

### OBS-SW-2: Monster entries merging across boundaries

- **Evidence chunk:** [201] `4e87c871671c1e`
- **Rule:** paragraph_run | **Stop:** boundary_encountered
- **Section:** `/page/5/SectionHeader/0 → /page/76/SectionHeader/0 → /page/101/SectionHeader/16 → /page/102/SectionHeader/0`
- **Pages:** [102] | **Source chunks:** 7
- **Text excerpt:** `Manticore — Armor Class: 4 [15] — Hit Dice: 6+4 — ... — Medusae are horrid creatures from Greek mythology...`

**Problem:** Two distinct monster entries (Manticore and Medusa) are merged into one evidence chunk. The name "Medusa" has a different font and a line under it, but this visual boundary wasn't detected.

**Signals available:**

- Monster names appear in distinct formatting (different font, underline separator).
- Each monster follows a rigid template: `NAME → AC → HD → Attacks → Special → Move → HDE/XP → description`.
- Marker should emit the monster name as a Heading block, creating a boundary.

**Improvement bucket:** Check `marker_stream.json` for page 102 — is "Medusa" emitted as a Heading or as Text? If Text, it's a Stage A classification issue. If Heading, the grouper's boundary detection may be failing. Template-aware monster-name detection.

---

### OBS-SW-3: Character sheet form content

- **Evidence chunk:** [1] `e4f383f341b534`
- **Rule:** paragraph_run | **Stop:** boundary_encountered
- **Section:** `/page/5/SectionHeader/0`
- **Pages:** [5]
- **Structural flags:** below_preferred_mass=True
- **Text:** `Class LEVEL Alignment Experience Points (XP) Age Prime Attribute Ancestry XP Bonus Deity Attribute Bonuses...`

**Problem:** This is a character sheet template / form. Field labels without values. No retrieval utility.

**Signals available:**

- Very structured, short field labels.
- Located on a page that is clearly a form/character sheet.
- Similar to OBS-FATE-3.

**Improvement bucket:** Form detection heuristics.

---

### OBS-SW-4: Character sheet blank assigned as section

- **Problem:** The Section (section_path) is being assigned from the character sheet blank — e.g. a heading or block on the character sheet page is treated as a section, so chunks get that as their section.
- **Requirement:** The entire character sheet should not be a section. Character sheet content should be detected and set aside (excluded from chunking or at least from contributing to section_path).
- **Improvement bucket:** Form/character-sheet detection and exclusion (same as OBS-SW-3); do not use character-sheet blocks as section headings; optionally drop or mark character-sheet chunks so they don't define section ancestry.

---

## Semantic Heading Ancestry in section_path — Implementation Specifics

**Goal:** Replace positional `section_path` (e.g. `/page/31/SectionHeader/1 → /page/41/SectionHeader/6`) with semantic ancestry (e.g. `Chapter 2: Creating a Character → Tiers of Play → Tier 2`) so chunks are self-contextualizing for retrieval and display.

### Current behavior

- **Source:** Marker outputs `section_hierarchy` per block as `{"1": "/page/11/SectionHeader/1", "2": "/page/41/SectionHeader/6", ...}` (level → structural path). No heading text.
- **Build:** `extraction/normalize.py` → `build_section_path(section_hierarchy)` returns the ordered list of those path strings. Chunker assigns that list to each Chunk as `section_path`. Broadening uses the shared prefix of source chunks’ `section_path` for EvidenceChunk.
- **Result:** We only have path identifiers everywhere, not chapter/section names.

### What we have to work with

- The **marker stream** already has, for every block, `section_hierarchy` and `text`. For blocks with `raw_block_type == "SectionHeader"`, the **leaf path** (the path at the highest level in `section_hierarchy`) is the path that heading defines, and `block.text` is the heading title.
- So we can build a **path → title** map from the stream without changing Marker.

### Option A: Heading registry in chunker (recommended)

**Where:** Stage A — `extraction/chunker.py` and `extraction/normalize.py`.

**Steps:**

1. **Build a heading registry in one pass over the marker stream**

   - Before the main chunking loop, iterate `marker_stream` once.
   - For each block with `normalize_block_type(block.raw_block_type) == "Heading"`:
     - Compute the **leaf path**: the value in `section_hierarchy` with the maximum level key (e.g. `"2"` → `/page/41/SectionHeader/6`). E.g. for `{"1": "/page/31/SectionHeader/1", "2": "/page/41/SectionHeader/6"}`, leaf = `/page/41/SectionHeader/6`.
     - `heading_registry[leaf_path] = block.text.strip()` (normalize whitespace; optionally truncate very long titles).
   - Result: dict from path string → heading title string.

2. **Resolve section_path to titles when assigning to chunks**

   - Keep `build_section_path(section_hierarchy)` as-is (returns list of path strings).
   - Add `build_semantic_section_path(section_hierarchy, heading_registry: dict[str, str]) -> list[str]` in `normalize.py`: same order as `build_section_path`, but replace each path `p` with `heading_registry.get(p, p)` (fallback to path if heading missing).
   - In the chunker, after `section_path = build_section_path(block.section_hierarchy)`, set `section_path_for_chunk = build_semantic_section_path(block.section_hierarchy, heading_registry)` and use that for `chunk.section_path` and for `current_section_path`. Chunk boundaries stay the same; only the stored value becomes semantic.

3. **Chunk identity and downstream**
   - `section_key` used in `_chunk_id` is currently `"|".join(current_section_path)`. To keep chunk IDs stable, keep `section_key` based on the **path**-based path (so pass path-based list into `_chunk_id`), and only store the semantic list in `chunk.section_path`. Optional but recommended for backward compatibility.
   - Broadening and sample scripts already treat `section_path` as a list of strings; they get semantic titles automatically.

**Files to touch:**

- `extraction/normalize.py`: add `build_semantic_section_path(section_hierarchy, heading_registry) -> list[str]`; optionally add `leaf_path(section_hierarchy) -> str | None`.
- `extraction/chunker.py`: first pass to build `heading_registry` from `marker_stream`; call `build_semantic_section_path` when setting `current_section_path` and when constructing each `Chunk`; keep `section_key` for `_chunk_id` path-based so chunk_id remains stable.

### Option B: Resolve in a separate Stage A post-pass

- Run chunking as today (path-based `section_path`).
- Add a post-pass over `chunks` and `marker_stream`: build the same `heading_registry` from `marker_stream`, then for each chunk set `chunk.section_path = build_semantic_section_path(...)` from the chunk’s path list. Same registry and `build_semantic_section_path` as above.
- Pro: minimal change to chunker. Con: two passes; need marker_stream when writing chunks (we already have it in `extraction/run.py`).

### Option C: Marker or conversion emits title in section_hierarchy

- If Marker (or our conversion) could emit e.g. `{"1": {"path": "...", "title": "Chapter 2: ..."}, ...}`, then `build_section_path` could return titles and no registry would be needed. That would require changing Marker or our conversion; if Marker doesn’t provide titles, we’d still need a pass to attach them. Option A/B is the main implementation; C is a possible future refactor.

### Edge cases and tuning

- **Missing registry entry:** Fall back to path string so we never drop information.
- **Long or noisy titles:** Optionally truncate (e.g. first 80 chars) or normalize (collapse whitespace).
- **Empty or duplicate paths:** Key registry by path; if multiple headings define the same path (shouldn’t happen), last or first wins depending on iteration order.
- **Multi-PDF:** Registry is per `marker_stream`; paths are already page-scoped. If multiple logical docs are merged into one stream, paths may need doc prefix in the registry key.

### Verification

- After implementation, re-run extraction and broadening for one book (e.g. DnD PHB).
- In `EVIDENCE-CHUNKS-SAMPLE.md`, check OBS-PHB-1 chunk [201]: `section_path` should read like `Chapter 2: Creating a Character → Tiers of Play → Tier 2` instead of `/page/31/... → /page/41/...`.
- Check OBS-PHB-2 chunk [481]: path should show Paladin / Oath of Vengeance.
- Check OBS-PHB-3 chunk [801]: path should show Feats → General Feats (and ideally Fey-Touched if that heading is in the stream).

### Implementation status (2026-02-05)

**Done.** Option A implemented in `extraction/normalize.py` and `extraction/chunker.py`:

- `leaf_path()`, `resolve_paths_to_titles()`, `build_semantic_section_path()` in normalize.py
- `_build_heading_registry()` in chunker; `section_key` remains path-based for stable chunk_id
- Verified: OBS-PHB-1 Tier 2 chunk now has `section_path: ['CREATING A CHARACTER', 'TIER 2 (LEVELS 5-10)']` instead of positional paths

---

## Summary: Improvement Buckets

| Bucket                                        | Observations                                                                        | Stage                   | Priority                                      |
| --------------------------------------------- | ----------------------------------------------------------------------------------- | ----------------------- | --------------------------------------------- |
| **Semantic heading ancestry in section_path** | OBS-PHB-1, OBS-PHB-2, OBS-PHB-3                                                     | A (chunker + normalize) | Done (2026-02-05)                             |
| **Raise/remove MAX_CHARS upper threshold**    | OBS-PHB-4, OBS-PHB-8, OBS-ALIEN-3, OBS-ALIEN-4, OBS-ALIEN-8                         | B (grouper)             | High — easy change, big impact                |
| **Template-aware boundary detection**         | OBS-PHB-3, OBS-PHB-4, OBS-PHB-6, OBS-PHB-8, OBS-ALIEN-5, OBS-ALIEN-7, OBS-SW-2      | B (grouper)             | Medium — spell/invocation/creature boundaries |
| **Column interleaving / sidebar separation**  | OBS-ALIEN-1, OBS-ALIEN-2, OBS-ALIEN-6, OBS-ALIEN-8, OBS-PHB-5, OBS-PHB-7, OBS-PHB-9 | A (Marker) or B         | High — deal-breaker for Alien Core            |
| **Sentence-continuation heuristic**           | OBS-ALIEN-2                                                                         | B (grouper)             | Medium — missing punctuation = continue       |
| **Form / character-sheet detection**          | OBS-FATE-3, OBS-SW-3, OBS-SW-4                                                      | A or B                  | Medium — exclude from section/chunking        |
| **Heading-span priority vs paragraph-run**    | OBS-FATE-2                                                                          | B (grouper)             | Low — investigate specific case               |
| **Spell/heading name in chunk**               | OBS-PHB-6                                                                           | A or B                  | Low — heading tuning so name in chunk         |
| **OCR correction for section names**          | OBS-FATE-4                                                                          | Post-process / LLM      | Low — easy wins                               |

---

## How to Use This Document

When working on any improvement bucket above:

1. Load the referenced evidence chunk by ID from the relevant `out/<Book>/evidence_chunks.json`
2. Check the corresponding `marker_stream.json` blocks for that page range to understand what Marker gave us
3. After making changes, re-run broadening and regenerate samples to verify the specific chunk improved
4. Cross-check that the fix doesn't degrade other observations listed here

---

_Generated from manual review of EVIDENCE-CHUNKS-SAMPLE.md files across 5 diverse TTRPG PDFs._

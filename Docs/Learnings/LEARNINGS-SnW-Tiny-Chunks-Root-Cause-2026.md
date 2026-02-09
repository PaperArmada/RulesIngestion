# S&W retrieval: tiny / noisy chunks — root cause and pattern

**Date:** 2026-02  
**Context:** Swords & Wizardry retrieval returns many low-value chunks like "Read Magic — Spell Level: M1", "Spell Level: M3", "Confusion — Spell Level: M4". ~3 in 8 retrieved chunks follow this pattern.

## 1. What these chunks are

They are **not table rows**. They are **prose EvidenceUnits** from the Stage B extraction:

- **unit_type:** `prose`
- **structural_path:** e.g. `["Read Magic"]`, `["Confusion"]`
- **Source:** First paragraph (or single line) under a **section heading** in the rulebook.

Stage B **absorbs** heading text into the first child unit’s text, separated by " — ". So when the source has:

```markdown
## Read Magic

Spell Level: M1
Range: Caster only
Duration: 2 scrolls or other writings
This spell allows the caster to read magical writings...
```

we get:

1. One unit: **"Read Magic — Spell Level: M1"** (heading + first line).
2. One unit: **"Range: Caster only"** (often flagged `undersized`).
3. One unit: **"Duration: 2 scrolls or other writings"**.
4. One unit: the description paragraph.

So the noisy chunks are **spell (or section) header lines**: the first block under each heading, which is often a single metadata line ("Spell Level: M N"). They share the phrase "Spell Level" and spell names, so they match any query about spells/levels but carry little standalone evidence.

## 2. Where they come from (pipeline)

- **Stage A** (surface): Markdown with `## SpellName` and separate blocks for "Spell Level: M N", "Range: ...", "Duration: ...", body.
- **Stage B** (`extraction/stage_b.py`):
  - One EvidenceUnit per **leaf** (paragraph, table, list, etc.).
  - Heading text is **prepended to the first child unit** only (docstring: "Heading nodes are absorbed: the heading text is prepended to the first child unit's text (separated by ' — ').").
  - So the first paragraph under a heading becomes `"Heading — first line"`, e.g. `"Read Magic — Spell Level: M1"`.
- **Gates:** Units with `len(text) < 20` get `anomaly_flags: ["undersized"]`. Many "Range: ..." / "Duration: ..." units are undersized; "Read Magic — Spell Level: M1" (26 chars) is not.

## 3. Pattern summary

| Pattern            | Example text                                                  | unit_type | Likely cause                                                                  |
| ------------------ | ------------------------------------------------------------- | --------- | ----------------------------------------------------------------------------- |
| Spell header line  | "Read Magic — Spell Level: M1", "Confusion — Spell Level: M4" | prose     | First paragraph under spell heading = single metadata line                    |
| Metadata line only | "Spell Level: M3", "Range: Caster only"                       | prose     | Standalone paragraph under same heading (no heading absorbed) or second child |
| Short key-value    | "Range: 120 ft.", "Duration: 2 hours"                         | prose     | One block = one unit; often `undersized`                                      |

These are **by design** in Stage B (one block → one unit; headings absorbed into first child). The downside is many low-information, high-match units in retrieval.

## 4. Locations (examples)

- **"Read Magic — Spell Level: M1"**
  - Page: **Swords&Wizardry_p58** (0-based 58).
  - File: `.../Swords&Wizardry_p58/stageB.evidence_units.json`
  - unit_id: `a58e37b0e12c7812a9f380841f95062348ca78e732919658674ebd7980d48226`
- **"Confusion — Spell Level: M4"**
  - Page: **Swords&Wizardry_p44**.
  - unit_id: `4be56e1151a56512552cf162cf8cb60ca2e101f73d9408279e2c93cda7475e8a`

Grep for `"Spell Level: M"` in `stageB.evidence_units.json` across S&W pages shows this pattern on many spell pages (p43–p63, etc.).

## 5. Mitigations

1. **Retrieval-time filter (recommended for quick fix):**  
   In the retrieval lab, optionally **exclude units with `len(text) < N`** (e.g. 40–60 chars) when loading the corpus. That drops most "Spell Level: M N" and "Range: ..." lines while keeping real paragraphs. Requires re-embedding after changing the corpus.

2. **Stage B / extraction changes (larger):**

   - Merge consecutive short prose units under the same heading into one unit, or
   - Emit a separate unit_type for "metadata_line" and filter on that in retrieval.  
     These change the extraction contract and need design.

3. **Post-retrieval rerank / filter:**  
   After retrieval, drop or down-rank chunks that match a regex (e.g. `^[^—]+ — Spell Level: M\d$`) or that are below a length threshold. Keeps indexing as-is but reduces noise in the returned list.

## 6. Retrieval lab: optional min_chars filter

In the experiment config (YAML or `ExperimentConfig`) set:

```yaml
min_chars: 50 # exclude units with len(text) < 50 (spell headers, "Range: ...", etc.)
substrate_version: "v1_filter50" # bump so run_id changes; re-embed required
```

Then run **embed** again (corpus is smaller), then retrieval. See `retrieval_lab/substrate_loader.py` (`load_evidence_units(..., min_chars=...)`) and `retrieval_lab/config.py` (`min_chars`).

## 7. References

- Stage B design: `extraction/stage_b.py` (docstring and `_walk_ast`, heading absorption).
- Unit size gate: `extraction/gates_b.py` (`min_chars`, `undersized`).
- Substrate loader: `retrieval_lab/substrate_loader.py` (`min_chars` parameter).

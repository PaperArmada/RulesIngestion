> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# Authority Legibility Invariant
**Status:** Draft v0.1  
**Date:** 2026-02-02  
**Purpose:** Make “authority” an explicit, testable, deterministic property of the ingested corpus—so we can safely use it as a *constraint* (eligibility + conflict resolution) rather than a fragile heuristic (seeding).

---

## 1) Problem statement

Authority exists in the rulebook (layout, headers, summaries, glossary, variant boxes, etc.), but the system currently treats it as *implicit* and *local*.

This causes:

- **Early-application regressions** (e.g., authority-weighted seeding drops recall).
- **Authority inversion** (examples/variants outcompete canonical rules).
- **Uninterpretable metrics** (graph density changes look like “progress”).

We need **authority legibility**: a deterministic projection that makes authority *observable* and *auditable*.

---

## 2) Definition: “authority legible”

Authority is **legible** iff, for every chunk and statement that can be used in grounding, the system can compute:

1. **Structural address**: where it lives in the book (chapter/section path, ordinal position, page range).
2. **Authorship channel**: what kind of content it is (main rule text vs example vs sidebar vs variant vs glossary vs summary).
3. **Normative voice** (optional in v0): whether the sentence is normative/prohibitive/permissive/advisory/illustrative.
4. **Priority order**: a deterministic partial order that can decide “this beats that” in conflicts.

Legibility is not “a score.” It’s **metadata + ordering constraints**.

---

## 3) Contract surface (required fields)

For every `chunk` node (or chunk-like structural unit):

- `struct.address.section_path: [str]`
- `struct.address.ordinal_in_doc: int`
- `struct.address.page_span: (int start, int end)` (or known page_id range)
- `struct.role.section_role: one of {core_rules, options, variants, examples, glossary, intro, summary, other}`
- `struct.channel.layout_tier: one of {main, sidebar, callout, example_box, variant_box, footnote, table, caption}`
- `struct.channel.content_kind: one of {rule, procedure, definition, example, narrative, table, reference, unknown}`
- `struct.channel.is_rule_bearing: bool` (existing if you have it)
- Optional:
  - `struct.voice.voice_type: one of {normative, prohibitive, permissive, advisory, illustrative, narrative, unknown}`
  - `struct.emphasis.bold_terms: [str]` (if extracted)
  - `struct.summary.parent_summary_id: str | null`

These fields are deterministic derivations from the document skeleton and layout parsing. No learned model required.

---

## 4) Authority order (v0)

Define a deterministic partial order `dominates(a, b)` over chunks:

### 4.1 Layout dominance
`main` > `sidebar` > `callout` > `example_box` > `variant_box` > `footnote` > `caption`

### 4.2 Section role dominance
`core_rules` > `intro` > `summary` > `glossary` > `options` > `variants` > `examples` > `other`

> Note: You can swap glossary/summary/intro ordering per book—**but it must be explicit**.

### 4.3 Content kind dominance
`procedure` > `rule` > `definition` > `reference` > `table` > `example` > `narrative` > `unknown`

### 4.4 Voice dominance (optional)
`prohibitive` > `normative` > `permissive` > `advisory` > `illustrative` > `narrative` > `unknown`

### 4.5 Tie-breakers (stable)
If dominance cannot decide (incomparable or equal), tie-break by:
1. Earlier `ordinal_in_doc` for foundational definitions (configurable)
2. Else closer structural proximity to query seeds (selection stage only)
3. Else stable deterministic: `chunk_id`

---

## 5) Invariants (must hold)

### I1 — Completeness
Every chunk that can be selected for grounding must have **all required fields** (Section 3).

**Test:** `missing_authority_fields_count == 0` over eligible chunks.

### I2 — Determinism
Given identical corpus bytes, the authority projection is identical.

**Test:** hash of `authority_projection.json` is stable across runs/machines.

### I3 — Non-interference with traversal
Authority projection **must not** affect entity/fact graph construction or traversal expansion.

**Test:** reachable entity set under fixed seeds is unchanged when authority is enabled/disabled (authority is selection-only).

### I4 — Conflict resolvability
If two chunks are in conflict (same topic/edge neighborhood), the order should be able to decide in ≥ X% of cases.

**Metric:** `conflict_pairs_resolved_rate >= 0.8` (target); unresolved pairs logged.

### I5 — No recall regression at seeding
Authority must not be required for seeding. If enabled for seeding, it must be gated and proven.

**Test:** seed set overlap with baseline must not decrease more than ε without increasing recall.

---

## 6) Measurement: Authority Legibility Score (ALS)

A corpus-level diagnostic (not an optimization target):

- `ALS = 1.0 - (missing_required_fields / eligible_chunks)`
- Report also:
  - `layout_coverage_rate`
  - `section_role_coverage_rate`
  - `content_kind_coverage_rate`
  - `voice_coverage_rate` (if used)
  - `dominance_resolvable_rate`

ALS must be near 1.0 before authority is trusted as a hard constraint.

---

## 7) Practical “stop doing” list

- Do not use authority as a numeric weight in seeding until ALS is ~1.0.
- Do not mix authority with traversal policy changes in the same experiment.
- Do not treat examples/variants as peers to main rules during conflict resolution.

---

## 8) Deliverables

- `Docs/canonical_document_skeleton.md` (CDS schema)
- `Docs/authority_projection.md` (this contract)
- `artifacts/authority_projection.json` (frozen projection per doc)
- Unit tests for I1–I4

---

## One-line takeaway

> Authority is only useful once it is *explicit and auditable*; otherwise it’s a fancy way to delete the correct seeds.

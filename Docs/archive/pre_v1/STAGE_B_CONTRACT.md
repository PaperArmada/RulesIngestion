<!--
Deprecated by: Docs/v1/stage_b_contract.md (full document).
Reason: Stage B contract canonical in v1; this copy preserved for history.
Last relevant commit/date: 2026-02 (pre-v1 stabilization).
-->

# Stage B Contract — Evidence Binding

## Purpose

Bind authored prose into **admissible** units: the smallest units that are still **meaningful evidence**.

Stage B's job is not only structural correctness but **evidential usability**. If units are arbitrarily small or heading-only, retrieval metrics and Stage C provenance collapse: a citation to a unit that is just "FOG CLOUD" is formally valid but epistemically worthless. So EvidenceUnits must be **admissible** and **semantically complete** enough to support citations.

## Canonical Unit

**EvidenceUnit** — one unit of authored prose (or table/list) with stable identity, provenance, and containment.

**Admissible unit**: A unit that is (a) structurally valid (no bleed, complete tables, within size bounds), (b) under a heading or assigned one (no unreasonably many orphans), and (c) **meaningful as evidence** — not a bare heading or fragment too small to stand as citable evidence. Unit size bounds exist to enforce (c): oversized is fatal (segmentation failure); undersized is a signal that the substrate may be dominated by non-evidential atoms (see Gates).

## Forbidden

- Entity extraction
- Rule interpretation
- Cross-page joins without auditable rule

## Gates

- **Orphan gate** — Flag units with empty `structural_path`. Exemptions: single-unit pages; image+caption-only pages; standalone pages (no prior page).
- **Bleed gate** — Flag overlapping source line ranges (section bleed).
- **Table integrity gate** — Each table EvidenceUnit contains a complete table.
- **Unit size gate** — Enforce bounds so units remain meaningful evidence:
  - **Oversized** (> 5000 chars): **FAIL**. Indicates segmentation failure.
  - **Undersized** (< 20 chars): **WARN** by default. When undersized units dominate the page or corpus (configurable ratio threshold), the gate **FAILs** — the substrate is then an index of shards, not admissible evidence. See `gate_unit_size` `undersized_fail_ratio`.

Unit size is **tunable**. The contract does not fix a single threshold forever; it requires that the pipeline not treat "warning only" as acceptable when undersized units become the dominant characteristic of the substrate.

## Rationale (gate revisit)

Retrieval and Stage C depend on what Stage B emits:

- **Retrieval**: If the substrate is full of heading-only or tiny units, Hit@k is inflated by heading matches, recall is hurt by fragmentation, and MRR is arbitrary. That is a **segmentation (Stage B) problem**, not a retrieval problem. Basing a "baseline" on synthetic gold in the same embedding space measures embedding self-consistency, not discoverability of evidence.
- **Stage C**: "Every fact must cite ≥1 EvidenceUnit." If EvidenceUnits can be meaningless (e.g. a two-word heading), provenance is theater. So either EvidenceUnits are meaningful evidence, or Stage C's guarantee is void.

Therefore: Stage B gates must treat **dominant undersized / non-evidential units** as a gate failure, not a warning-only condition. Synthetic or expanded substrates belong in separate retrieval experiments (Retrieval Lab Baseline-B); the **baseline substrate** for ingestion discoverability is raw Stage B output with **manually grounded** gold (Baseline-A).

## Heading Absorption

Headings are **not** standalone EvidenceUnits. A heading's text is prepended (with `—`) to the first child unit beneath it. The heading still extends `structural_path` for all children. If a heading has no children (e.g. end-of-page), it emits as a fallback heading-type unit flagged `unabsorbed_heading`.

This preserves searchability (heading text is in the unit) without producing empty atoms that inflate retrieval metrics and collapse Stage C citations.

**Empirical result (DnD5eBrutalChapters, 36 pages):**

- Total units: 742 → 559 (−24.7%)
- Heading-type units: 183 → 0
- Undersized: 50 → 46 (−8%)
- Salvage: 1.0 → 1.0 (unchanged)
- Gate pass pattern: unchanged (same 2 orphan pages)

## Orphan Header Pass

Orphan pages have no heading nodes in the AST; units have empty `structural_path`. When configured, an LLM can assign a heading from prior-page + orphan-page context. The assigned heading is written into each EvidenceUnit's `structural_path`. The AST is not modified; downstream consumers use units and retain the metadata.

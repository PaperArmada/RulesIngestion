> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# Canonical Document Skeleton (CDS) Schema
**Status:** Minimal schema v0.2  
**Date:** 2026-02-02  
**Purpose:** Build a frozen, deterministic projection of document structure and authorial signals that is used **only** to constrain grounding (eligibility + precedence), not traversal.

---

## 1) Scope

CDS is a parallel structure graph that encodes:

- Hierarchy (document → chapter → section → subsection)
- Ordering (ordinal positions)
- Page ranges
- Layout channels (main/sidebars/examples/variants/etc.)
- Summaries/glossary entries (if present or extracted deterministically)
- Term distributions per node (deterministic token stats)

**Non-goal:** reasoning. CDS never produces new semantic edges between entities.

---

## 2) Core objects (JSON-ish)

### 2.1 Document

```json
{
  "doc_id": "sf2e-playercore-PZO22001",
  "title": "Starfinder Player Core",
  "edition": "2025",
  "source_path": "...",
  "page_count": 460,
  "root_section_id": "sec:root",
  "created_at": "2026-02-02T00:00:00Z",
  "version": "cds-0.2"
}
```

### 2.2 Section node

```json
{
  "section_id": "sec:1.3.2",
  "parent_section_id": "sec:1.3",
  "title": "Status Bonuses",
  "ordinal": 142,
  "depth": 3,
  "page_start": 58,
  "page_end": 59,
  "role": "core_rules",
  "summary": {
    "text": "Status bonuses represent ...",
    "source": "publisher|extracted",
    "summary_id": "sum:sec:1.3.2"
  },
  "term_stats": {
    "token_df": {"status": 12, "bonus": 8},
    "token_tfidf_top": [["status", 3.1], ["bonus", 2.7]],
    "updated_at": "2026-02-02T00:00:00Z"
  }
}
```

### 2.3 Chunk address (structural pointer)

Every chunk in the main graph should have:

```json
{
  "chunk_id": "doc::/page/6/Text/15",
  "doc_id": "sf2e-playercore-PZO22001",
  "section_path": ["sec:1", "sec:1.3", "sec:1.3.2"],
  "ordinal_in_doc": 9123,
  "page": 58,
  "layout_tier": "main",
  "content_kind": "rule",
  "is_rule_bearing": true
}
```

### 2.4 Layout region (optional but valuable)

```json
{
  "region_id": "reg:page58:3",
  "page": 58,
  "bbox_norm": [0.05, 0.12, 0.92, 0.34],
  "layout_tier": "sidebar",
  "label": "Example",
  "linked_chunk_ids": ["doc::/page/58/Text/12", "doc::/page/58/Text/13"]
}
```

---

## 3) Enumerations (minimal)

### 3.1 SectionRole
- `core_rules`
- `intro`
- `glossary`
- `summary`
- `options`
- `variants`
- `examples`
- `reference`
- `other`
- `unknown`

### 3.2 LayoutTier
- `main`
- `sidebar`
- `callout`
- `example_box`
- `variant_box`
- `footnote`
- `table`
- `caption`
- `unknown`

### 3.3 ContentKind
- `procedure`
- `rule`
- `definition`
- `example`
- `reference`
- `table`
- `narrative`
- `unknown`

---

## 4) Deterministic build pipeline (suggested)

1. **Parse structural hierarchy** from PDF TOC / headings:
   - document → sections with ordinals and page ranges.
2. **Attach chunk→section mapping**:
   - by page + nearest preceding heading (deterministic).
3. **Layout classification**:
   - using existing extractor labels (Text/Table/SectionHeader) plus region detection if available.
4. **Summary extraction**:
   - prefer publisher-provided summaries; else deterministic heuristic summary (first N sentences or “summary blocks”).
5. **Term stats**:
   - normalized tokenization; compute df/tfidf within section.

Output artifact:
- `artifacts/cds/<doc_id>.cds.json`

---

## 5) CDS invariants (hard)

### C1 — Total order of chunks
All chunks in a document have a unique `ordinal_in_doc`.

### C2 — Section path completeness
Every chunk has a `section_path` ending at some `section_id`.

### C3 — Stable enums
All role/tier/kind values must be from enumerations; unknown allowed but counted.

### C4 — Freeze
CDS does not change across queries. Only rebuilt on ingestion.

---

## 6) How CDS is used (and not used)

### Used for:
- Eligibility gating (which chunks can answer)
- Precedence (conflict resolution)
- Reranking priors (authorial emphasis)
- Diagnostics (authority inversion detection)

### Not used for:
- Entity traversal expansion
- Fact graph construction
- Creating new semantic edges between entities

---

## One-line takeaway

> CDS is a frozen “authorial intent index” that makes authority computable without polluting reasoning.

# CDS v0.2 Code → Spec Mapping

**Date:** 2026-02-02  
**Purpose:** Map current CDS v0.2 implementation to the three design specs:

- `canonical_document_skeleton_schema.md`
- `authority_legibility_invariant.md`
- `phase3_authority_at_selection_v1.md`

---

## 1. Canonical Document Skeleton Schema

### 1.1 Scope (Schema §1)

| Spec scope                          | v0.2 status        | Location                                                                           |
| ----------------------------------- | ------------------ | ---------------------------------------------------------------------------------- |
| Hierarchy (doc → chapter → section) | ✅ Implemented     | `cds_builder.py`: `_build_outline`, `_build_chapter_nodes`, `_build_section_nodes` |
| Ordering (ordinals)                 | ✅ Implemented     | `cds_builder.py`: chapter/section `ordinal`; `ChunkFacts.ordinal`                  |
| Page ranges                         | ⚠️ Partial         | `ChunkFacts.page` (single page); no `page_start`/`page_end` per section            |
| Layout channels                     | ⚠️ Partial         | `block_type`, `container_type`, `is_callout`; no enum mapping to LayoutTier        |
| Summaries/glossary                  | ❌ Not implemented | —                                                                                  |
| Term distributions                  | ❌ Not implemented | —                                                                                  |

### 1.2 Core Objects (Schema §2)

| Spec object          | v0.2 equivalent                                                                             | Gap                                                                                       |
| -------------------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Document (§2.1)      | `documents[doc_id]` with `document_id`, `outline`, `chunk_facts`, `constraint_sets`         | No `title`, `edition`, `page_count`, `root_section_id`, `version` at doc level            |
| Section node (§2.2)  | `outline.sections[]` with `section_id`, `path`, `ordinal`, `chapter_id`                     | No `parent_section_id`, `depth`, `page_start`/`page_end`, `role`, `summary`, `term_stats` |
| Chunk address (§2.3) | `chunk_facts[]` with `chunk_id`, `section_id`, `ordinal`, `layout.*`, `rhetoric_explicit.*` | No `doc_id` in chunk, no `layout_tier` enum, no `content_kind`, no `is_rule_bearing`      |
| Layout region (§2.4) | ❌ Not implemented                                                                          | —                                                                                         |

### 1.3 Enumerations (Schema §3)

| Spec enum   | v0.2 status        | Notes                                                                                                        |
| ----------- | ------------------ | ------------------------------------------------------------------------------------------------------------ |
| SectionRole | ❌ Not implemented | v0.2 infers example/variant from section path keywords only                                                  |
| LayoutTier  | ⚠️ Implicit        | `block_type` (Text, Table, SectionHeader) and `container_type`; no mapping to `main`/`sidebar`/`example_box` |
| ContentKind | ⚠️ Partial         | `has_example_label`, `has_variant_label`, `has_definition_label` are boolean flags, not enum                 |

### 1.4 Build Pipeline (Schema §4)

| Spec step                  | v0.2 equivalent                                                                        |
| -------------------------- | -------------------------------------------------------------------------------------- |
| Parse structural hierarchy | `_build_header_id_mapping`, `_resolve_section_hierarchy`, `_get_resolved_section_path` |
| Attach chunk→section       | `build_chunk_facts` with resolved `section_path`                                       |
| Layout classification      | Uses `block_type` from enrichment; no region detection                                 |
| Summary extraction         | ❌                                                                                     |
| Term stats                 | ❌                                                                                     |

### 1.5 CDS Invariants (Schema §5)

| Invariant                      | v0.2 status                                                      |
| ------------------------------ | ---------------------------------------------------------------- |
| C1 — Total order of chunks     | ✅ `ordinal` in `ChunkFacts`                                     |
| C2 — Section path completeness | ✅ 95% coverage via `_get_resolved_section_path`; root for empty |
| C3 — Stable enums              | ⚠️ No formal enums; rhetoric labels are booleans                 |
| C4 — Freeze                    | ✅ CDS built at merge, not per-query                             |

---

## 2. Authority Legibility Invariant

### 2.1 Required Fields (Invariant §3)

| Spec field                         | v0.2 ChunkFacts                                                  | Status                                                            |
| ---------------------------------- | ---------------------------------------------------------------- | ----------------------------------------------------------------- |
| `struct.address.section_path`      | `section_id` (derived from path) + path in outline               | ⚠️ Section path not stored per chunk in ChunkFacts                |
| `struct.address.ordinal_in_doc`    | `ordinal`                                                        | ✅                                                                |
| `struct.address.page_span`         | `page` (single)                                                  | ⚠️ No span                                                        |
| `struct.role.section_role`         | Inferred via section path keywords                               | ⚠️ No explicit enum; `has_example_label`/`has_variant_label` only |
| `struct.channel.layout_tier`       | `block_type`, `container_type`, `is_callout`                     | ⚠️ Raw parser values, not enum                                    |
| `struct.channel.content_kind`      | `has_example_label`, `has_variant_label`, `has_definition_label` | ⚠️ Boolean proxies, not enum                                      |
| `struct.channel.is_rule_bearing`   | ❌ Not in ChunkFacts                                             | ❌                                                                |
| `struct.voice.voice_type`          | ❌ Explicitly excluded (unsafe inference)                        | ❌                                                                |
| `struct.emphasis.bold_terms`       | ❌                                                               | ❌                                                                |
| `struct.summary.parent_summary_id` | ❌                                                               | ❌                                                                |

### 2.2 Authority Order (Invariant §4)

| Spec dominance rule    | v0.2 equivalent                                                    |
| ---------------------- | ------------------------------------------------------------------ |
| Layout dominance       | ❌ No layout_tier rank                                             |
| Section role dominance | ❌ No section_role                                                 |
| Content kind dominance | Implicit in C0/C1: non-example > example, non-variant > variant    |
| Voice dominance        | ❌ Excluded                                                        |
| Tie-breakers           | Conflict rules use baseline order when UNKNOWN; no `authority_key` |

### 2.3 Invariants (Invariant §5)

| Invariant                            | v0.2 status                                                                |
| ------------------------------------ | -------------------------------------------------------------------------- |
| I1 — Completeness                    | ⚠️ Many chunks lack `section_role`, `layout_tier`, `content_kind` as enums |
| I2 — Determinism                     | ✅ SHA-256 for section IDs; anchored regex; stable ordinals                |
| I3 — Non-interference with traversal | ✅ CDS applied only at selection; no seed/traversal changes                |
| I4 — Conflict resolvability          | ⚠️ Pairwise rules; no `conflict_pairs_resolved_rate` metric                |
| I5 — No recall regression at seeding | ✅ T3 harness; authority not used for seeding                              |

### 2.4 ALS / Measurement

| Metric                     | v0.2 status     |
| -------------------------- | --------------- |
| ALS                        | ❌ Not computed |
| layout_coverage_rate       | ❌              |
| section_role_coverage_rate | ❌              |
| dominance_resolvable_rate  | ❌              |

---

## 3. Phase 3: Authority-at-Selection v1

### 3.1 Locked Controls (Phase3 §2)

| Control                           | v0.2 status                         |
| --------------------------------- | ----------------------------------- |
| Traversal: ENTITY_ONLY, Variant A | ✅ Benchmark uses entity-only       |
| Retrieval: R2 IDF                 | ✅                                  |
| Scope: V1                         | ✅                                  |
| Ownership: baseline               | ✅                                  |
| Selection/reranking only          | ✅ CDS gate applied after retrieval |

### 3.2 Eligibility Gate (Phase3 §3.1)

| Spec rule                                           | v0.2 rule                                          | Location                                   |
| --------------------------------------------------- | -------------------------------------------------- | ------------------------------------------ |
| Drop example_box/caption/footnote unless query asks | A1: Deny explicit examples for non-example queries | `DenyExplicitExamplesForNonExampleQueries` |
| Drop variants unless query keywords                 | A2: Deny explicit variants unless `allow_variants` | `DenyExplicitVariantsUnlessAllowed`        |
| Fallback if no remaining candidates                 | Implicit: filter drops DENY only; UNKNOWN keeps    | `filter_candidates`                        |

**Gap:** v0.2 uses `has_example_label`/`has_variant_label` (explicit labels + section path). Phase3 spec assumes `layout_tier` and `section_role` enums. v0.2 is stricter (fewer denials).

### 3.3 Precedence Order (Phase3 §3.2)

| Spec                                          | v0.2                                                     |
| --------------------------------------------- | -------------------------------------------------------- |
| `authority_key(chunk)` as lexicographic tuple | ❌ Not implemented                                       |
| Prefer higher authority_key among candidates  | Conflict rules C0, C1, C3 provide pairwise ordering only |
| Tie-break: ordinal_in_doc or chunk_id         | Baseline order preserved when UNKNOWN                    |

**Gap:** v0.2 has no numeric `authority_key`; it uses pairwise conflict resolution only.

### 3.4 Diagnostics (Phase3 §5)

| Spec diagnostic                              | v0.2 status                                             |
| -------------------------------------------- | ------------------------------------------------------- |
| Log top N candidates with authority metadata | ❌                                                      |
| Log if gold filtered by eligibility          | `rejected_cds` in result_row; not systematically logged |
| Authority inversion detected                 | ❌ No `authority_key` comparison                        |

### 3.5 Wiring (Phase3 §7)

| Spec module                                                                       | v0.2 equivalent                                                  |
| --------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `grounding/authority.py` with `authority_key`, `is_eligible`, `rerank_candidates` | `cds/constraint_engine.py` + `experiments/cds_v2_integration.py` |
| No changes to seeds                                                               | ✅                                                               |

---

## 4. Summary Matrix

| Spec requirement              | v0.2 implemented                                         | v0.2 partial                | v0.2 missing                                                                 |
| ----------------------------- | -------------------------------------------------------- | --------------------------- | ---------------------------------------------------------------------------- |
| CDS schema                    | hierarchy, ordinals, chunk facts                         | page, layout as raw         | summaries, term stats, LayoutTier/SectionRole enums, layout regions          |
| Authority legibility          | determinism, non-interference, no seeding                | address, channel as proxies | section_role, layout_tier enums, voice, ALS, dominance order                 |
| Phase3 authority-at-selection | late-only, eligibility (explicit labels), conflict rules | —                           | layout_tier-based eligibility, authority_key, precedence rerank, diagnostics |

---

## 5. File-to-Spec Cross-Reference

| File                                          | Spec sections                                                                  |
| --------------------------------------------- | ------------------------------------------------------------------------------ |
| `cds/cds_builder.py`                          | CDS schema §1–2, §4; outline, chunk_facts, constraint_sets                     |
| `cds/chunk_facts_adapter.py`                  | CDS §2.3 (chunk address); Authority §3 (required fields, partial)              |
| `cds/constraint_engine.py`                    | Authority §4 (partial: example/variant dominance); Phase3 §3.1, §3.2 (partial) |
| `cds/schema/cds_constraints_v0.2.schema.json` | CDS schema §2 (structure)                                                      |
| `experiments/cds_v2_integration.py`           | Phase3 §7 (wiring)                                                             |
| `experiments/rule_fact_benchmark_eval.py`     | Phase3 §2 (locked controls), §7 (integration)                                  |

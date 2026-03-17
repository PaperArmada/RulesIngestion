# Stage B Contract — Evidence Binding

**Purpose:** Bind authored prose into **admissible** units: the smallest units that are still **meaningful evidence**.

---

## 1. EvidenceUnit Definition

- **EvidenceUnit:** One unit of authored prose (or table/list) with stable identity, provenance, and containment.
- **Admissible unit:** (a) Structurally valid (no bleed, complete tables, within size bounds); (b) under a heading or assigned one (no unreasonably many orphans); (c) meaningful as evidence (not a bare heading or fragment too small to cite). Unit size bounds enforce (c): oversized prose → FAIL; oversized tables use a higher cap because complete tables must remain intact; undersized dominance → configurable FAIL.

---

## 2. Unit ID Scheme and Provenance Fields

- **unit_id:** Stable id derived from unit text plus page-local provenance (page_fingerprint, source line span, unit_type, structural_path).
- **Provenance:** document_id (or source), page (or page_fingerprint), structural_path, source_line_start, source_line_end, content_hash, content_version, ordering_key. Optional: page_fingerprints (multi-page joins), table_group_id, join_metadata.

See [schema_registry.md](schema_registry.md) for full EvidenceUnit schema.

---

## 3. Binding and Segmentation Rules

- One EvidenceUnit per prose block, table, or list; headings are absorbed into the first child unit (heading text prepended with "—"; fallback heading-type unit with `unabsorbed_heading` if no children).
- No cross-page joins without an auditable rule (R3 cross_page_join is explicit and metadata-bearing).
- Table grouping: each table EvidenceUnit is complete; table_group_id links related tables when applicable.

---

## 4. Non-Goals (Explicit)

- No entity extraction.
- No rule interpretation or paraphrase.
- No ontology assignment in Stage B.

---

## 5. Table Grouping Guarantees

- Each table EvidenceUnit contains a complete table (no split tables).
- table_group_id (when present) groups tables that share header/schema; used for retrieval and display, not for altering unit boundaries.

---

## 6. Gates (Summary)

- **Orphan gate:** Flag empty structural_path; exemptions documented.
- **Bleed gate:** Flag overlapping source line ranges.
- **Table integrity gate:** Complete table per unit.
- **Unit size gate:** Oversized prose FAIL; complete tables use a larger maximum bound; undersized WARN, with fail ratio when undersized dominate.

Implementation: `extraction/stage_b.py`, `extraction/gates_b.py`.

---

## 7. Stable Ordering (Determinism)

All iteration that affects output order must use **stable sort keys** so that the same inputs produce byte-identical outputs:

- **document_id**, **page** (or page_fingerprint), **structural_path** (list comparison), **ordering_key**, **unit_id**.
- Dedupe priority: when both an EvidenceUnit and a family anchor refer to the same unit, EvidenceUnit is preferred (see ADR-003).
- Corpus order for Retrieval Lab: sort by (document_id, page, ordering_key or unit_id).

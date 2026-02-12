# Schema Registry v1

**Purpose:** Single reference for all artifact schemas used in Stage A, Stage B, and Retrieval Lab. Versioning: new fields must be optional or version-bumped.

---

## 1. Stage A Output Block Schema

- **StageARecord:** Raw model envelope per page. Fields: page_fingerprint, source_pdf, page_index, model_id, prompt, raw_markdown, inference_elapsed_sec, content_hash, content_version.
- **SurfaceASTNode:** node_type (heading | paragraph | table | list | callout | sidebar | footnote | image_ref | root), level, text, children, source_line_start, source_line_end.
- **SurfaceAST:** page_fingerprint, content_hash, root (SurfaceASTNode), node_count, table_count.

Implementation: `extraction/schemas.py`.

---

## 2. Stage B EvidenceUnit Schema

- **EvidenceUnit:** unit_id, unit_type (prose | table | list | callout | heading), text, structural_path (list[str]), ordering_key, page_fingerprint, content_hash, source_line_start, source_line_end, anomaly_flags, content_version; optional page_fingerprints, table_group_id, join_metadata.

Implementation: `extraction/schemas.py`.

---

## 3. Projection: ClauseFamily Schema

- **ClauseFamily (projection):** anchor_unit_id, members (list of unit_ids), params (e.g. family_window, family_max_units, direction). Retrieval-only; not admissible.

---

## 4. RetrievalCandidate Schema

- **RetrievalCandidate / ranked item:** source_list (which list: Index_U, Index_F, etc.), merge_reason (e.g. RRF, dual_list, pairing), dedupe metadata (e.g. which unit kept when EvidenceUnit and family anchor both present). Stable ordering: EvidenceUnit preferred over family anchor when both exist.

---

## 5. Sidecar Edge Schema (Pairing)

- **Pairing edges:** delta/base, exception/base. Per unit_id: list of (target_unit_id, edge_type). Instrumented; not yet proven. See ADR-004.

---

## 6. Eval Run Summary Schema

- **Run summary:** MRR, Hit@k, Recall@k, Full-set@k, grounded counts, effective_queries_excluding_no_gold, gold_in_candidates_true_ceiling. Per-model in metrics.json.

---

## 7. Failure Bucket Schema

- **Per-query:** failure_bucket (no_gold_defined | gold_not_in_candidates | gold_in_candidates_but_low_rank | grounding_or_answer_failure_after_retrieval | success), tier (T1 | T2 | T3), first_gold_rank, etc.
- **Aggregate:** failure_bucket_counts (dict bucket → count), by_tier (tier → bucket → count).

---

## 8. Versioning Policy

- New fields on existing schemas must be **optional** (backward compatible) or the schema **version** must be bumped and documented here.
- Breaking changes require an ADR and migration notes.

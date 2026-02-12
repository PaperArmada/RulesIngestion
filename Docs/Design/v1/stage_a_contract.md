# Stage A Contract — Prose Reconstruction (Authorial Surface)

**Purpose:** Reconstruct authored prose with maximum fidelity. No semantics.

---

## 1. Inputs and Outputs

| Role    | Format / Location |
|---------|--------------------|
| Input   | PDF pages; OCR/model output (raw markdown per page). |
| Output  | **StageARecord** (raw model envelope per page); **SurfaceAST** (deterministic structural tree per page). |

- StageARecord: page_fingerprint, source_pdf, page_index, model_id, prompt, raw_markdown, inference_elapsed_sec, content_hash, content_version.
- SurfaceAST: page_fingerprint, content_hash, root (SurfaceASTNode), node_count, table_count.
- SurfaceASTNode: node_type (heading, paragraph, table, list, callout, sidebar, footnote, image_ref, root), level, text, children, source_line_start, source_line_end.

See [schema_registry.md](schema_registry.md) for full field definitions.

---

## 2. Ordering Rules

- **Page order:** Documents are ordered by document identity and page index (0-based).
- **Within-page order:** Total order is defined by traversal of the SurfaceAST (e.g. depth-first). Every block has a stable position.

---

## 3. structural_path and Heading Ancestry Policy

- **structural_path** (in Stage B EvidenceUnits) is the list of heading labels from AST root to the unit’s containing node.
- Heading ancestry is taken from the AST: each heading’s text (or normalized form) is appended to the path for all descendants until the next heading of the same or higher level.
- Orphan pages (no heading in AST): units may have empty structural_path unless an Orphan Header Pass assigns one (LLM-assigned heading written into unit metadata; AST unchanged).

---

## 4. Table and List Handling

- Tables and lists are first-class node types in the SurfaceAST.
- Each table/list node has source_line_start/source_line_end; Stage B emits one EvidenceUnit per table (or per list) with complete content. No splitting of a single table across units.

---

## 5. Orphan Policy

- **Orphan:** unit with empty structural_path because the page has no heading node in the AST.
- **Minimal repair allowed:** Orphan Header Pass (optional) can assign a heading from context; no semantic rewriting. Exemptions for single-unit pages, image+caption-only pages, standalone pages (no prior page) are documented in Stage B gates.

---

## 6. Deterministic Replay Requirements

- Given the same inputs (same page, same raw model output), Stage A must produce **byte-identical** structural outputs.
- All iteration over collections that affect output order must use fixed sort keys (e.g. page_index, source_line_start, node order in tree).
- Implementation: `extraction/stage_a_prime.py`, `extraction/ast_parser.py`; schemas in `extraction/schemas.py`.

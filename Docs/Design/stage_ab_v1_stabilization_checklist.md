# Stage A/B v1 Stabilization Checklist (Agent Handoff)

**Status:** Historical handoff checklist. The resulting canonical documentation
now lives in [v1/](v1/); keep this file for provenance, not as an active spec.

**Purpose:** Convert current Stage A + Stage B + Retrieval Lab work into a **canonical v1** with stable contracts, archived legacy artifacts, cleaned code, and a robust regression test wall.  
**Scope:** Stage A (Extraction + Prose Reconstruction), Stage B (Evidence Binding), Retrieval Lab (evaluation + comparisons), baseline eval suite.  
**Non-scope:** Stage C enrichment and Stage D graph work (gated at the end).

---

## 0) Preflight (do this first)

- [ ] Confirm you have the latest main branch (or the target integration branch).
- [ ] Confirm all recent benchmark runs are present and readable:
  - Baseline: `phb_hybrid_20260211_212748`
  - Dual-list fusion: `phb_hybrid_dual_list_fusion_20260212_032935`
  - Dual-list + pairing: `phb_hybrid_dual_list_fusion_plus_pairing_20260212_034258`
  - Comparison report: `out/retrieval_lab/stage_a_and_b/COMPARISON_BASELINE_DUAL_LIST_PAIRING.md`
- [ ] Confirm deterministic environment capture is available (lockfile, requirements, etc.).
- [ ] Create a working branch: `stage-ab-v1-stabilization`.

**Acceptance:** You can reproduce the comparison report path above from the branch without missing files.

---

## 1) Freeze the v1 baseline anchor (single source of truth)

### 1.1 Pick a baseline commit
- [ ] Choose the commit SHA that represents “Stage A/B v1 baseline”.
- [ ] Tag it (or record it in a manifest file):
  - Suggested tag: `stage-ab-v1-baseline`
  - Or a manifest: `docs/v1/baseline_manifest.md`

### 1.2 Create a v1 baseline manifest (required)
Create `docs/v1/baseline_manifest.md` containing:
- [ ] Commit SHA / tag
- [ ] Corpus manifest: books included, versions, extraction inputs
- [ ] Retrieval configs considered “v1 baseline”:
  - [ ] Canonical hybrid config (baseline)
  - [ ] Dual-list fusion config (production default)
  - [ ] Dual-list + pairing config (experimental; instrumented)
- [ ] Run IDs (the three above) and link/filepath to the comparison report
- [ ] Environment fingerprint:
  - python version, OS
  - dependency lock (requirements/uv/poetry)
  - random seed policy (if any)
- [ ] Determinism invariants:
  - Stage A determinism statement
  - Stage B determinism statement
  - Retrieval Lab determinism statement (stable ordering + stable dedupe)

**Acceptance:** A new engineer can read the manifest and know exactly what “baseline” means and how to reproduce it.

---

## 2) Canonical v1 documentation set (write new docs; don’t patch old docs)

### 2.1 Create v1 doc directory
- [ ] Create: `docs/v1/`

### 2.2 Required canonical docs (create these new files)
Write each as an authoritative spec; copy/paste best prior content, then normalize and remove contradictions.

1) `docs/v1/architecture_overview.md`
- [ ] Stage diagram (A → B → Retrieval Lab; C/D are gated)
- [ ] Artifact flow and boundaries
- [ ] What is admissible evidence vs retrieval-only projections
- [ ] Determinism principles

2) `docs/v1/stage_a_contract.md`
- [ ] Inputs/outputs and file formats
- [ ] Ordering rules (page order, within-page order)
- [ ] Definition of `structural_path` and heading ancestry policy
- [ ] Table/list handling policy
- [ ] Orphan policy (minimal repair allowed; no semantic rewriting)
- [ ] Deterministic replay requirements (byte-identical outputs given same inputs)

3) `docs/v1/stage_b_contract.md`
- [ ] EvidenceUnit definition (atomic, admissible, traceable)
- [ ] Unit id scheme and provenance fields (document_id, page, structural_path, etc.)
- [ ] Binding/segmentation rules and invariants
- [ ] Explicit non-goals (no ontology, no paraphrase)
- [ ] Table grouping guarantees (if applicable)

4) `docs/v1/retrieval_lab_v1.md`
- [ ] How to run evals
- [ ] Config model: what knobs exist, which are “happy path”
- [ ] Output directory conventions
- [ ] Comparison protocol + required metrics
- [ ] Failure bucket dashboard definitions
- [ ] Regression policy (what counts as regression; especially T1 regressions)

5) `docs/v1/schema_registry.md`
- [ ] One section per artifact schema (see 2.3 below)
- [ ] Field definitions, types, invariants
- [ ] Versioning policy for schemas

6) `docs/v1/glossary.md`
- [ ] EvidenceUnit vs Projection vs Candidate vs Gold vs Full-set
- [ ] structural_path, anchor unit, family window, max units
- [ ] Tier meanings (T1/T2/T3)
- [ ] “admissible” vs “non-authoritative”

7) `docs/v1/adr/` (decision records)
- [ ] Create directory: `docs/v1/adr/`
- [ ] ADR-001: “EvidenceUnits are canonical admissible layer”
- [ ] ADR-002: “Dual-list fusion is production default”
- [ ] ADR-003: “Clause families are retrieval projections (not admissible)”
- [ ] ADR-004: “Pairing edges: delta/base and exception/base (instrumented; not yet proven)”

**Acceptance:** A reader can implement Stage A/B and Retrieval Lab from these docs without referencing archived docs.

### 2.3 Required schema list (must appear in schema registry)
Ensure the registry includes (at minimum):
- [ ] Stage A output block schema (prose blocks / structural markers)
- [ ] Stage B EvidenceUnit schema
- [ ] Projection: ClauseFamily schema (fields: anchor_unit_id, members, params)
- [ ] RetrievalCandidate schema (fields: source_list, merge_reason, dedupe metadata)
- [ ] Sidecar edge schema (if retained): pairing edges (delta/base, exception/base)
- [ ] Eval run summary schema (MRR, Hit@10, Recall@10, Full-set@10, grounded counts)
- [ ] Failure bucket schema (no_gold_defined, gold_not_in_candidates, low_rank, etc.)

---

## 3) Archive old docs (with forward pointers)

### 3.1 Create archive directory
- [ ] Create: `docs/archive/pre_v1/`

### 3.2 Move legacy docs
- [ ] Move old Stage A/B/ Retrieval Lab design docs into `docs/archive/pre_v1/`
- [ ] Do not delete. Preserve history.

### 3.3 Add deprecation headers to archived docs
At the top of each archived doc, add:
- [ ] “Deprecated by: docs/v1/<new doc> (section X)”
- [ ] “Reason: <one sentence>”
- [ ] “Last relevant commit/date: <…>”

**Acceptance:** No ambiguity about which doc is canonical.

---

## 4) Retrieval Lab cleanup pass (code + docs + configs)

### 4.1 Normalize configs (happy path)
- [ ] Confirm `phb_hybrid_dual_list_fusion.yaml` is treated as **default** for PHB.
- [ ] Confirm baseline hybrid config remains available for comparisons (but not default).
- [ ] Confirm dual-list + pairing config is labeled “experimental” and instrumented.

### 4.2 Output hygiene
- [ ] Standardize run output structure (one directory per run with:
  - config snapshot
  - corpus manifest snapshot
  - per-query diagnostics
  - summary metrics
  - comparison report artifacts)
- [ ] Ensure comparisons always write a single canonical file path (or predictable naming).

### 4.3 Failure bucket dashboard as first-class output
- [ ] Ensure every run produces failure bucket counts and per-query classification.

### 4.4 Instrumentation hooks (required for pairing edges)
Add per-query logs:
- [ ] pairing triggers fired count
- [ ] candidates added by pairing
- [ ] gold added by pairing (if gold set known)
- [ ] whether added candidates entered top-10
- [ ] dedupe interactions

**Acceptance:** Pairing can be evaluated even when headline metrics don’t move.

---

## 5) Archive old evals + declare new multi-book baseline suite

### 5.1 Archive legacy eval bundles
- [ ] Create: `evals/archive/pre_v1/` (or equivalent)
- [ ] For each archived eval bundle, include:
  - config(s)
  - corpus manifest used
  - raw outputs
  - summary + comparisons
  - README with reproduction steps

### 5.2 Create new v1 baseline suite across all books
- [ ] Define “baseline suite” set (PHB + Starfinder + S&W, etc.)
- [ ] Run suite with:
  - baseline hybrid
  - dual-list fusion (where applicable)
- [ ] Save as `evals/v1_baseline/<date_or_tag>/...`

### 5.3 Update docs to point to new baseline suite
- [ ] In `docs/v1/retrieval_lab_v1.md`, specify:
  - how to run the baseline suite
  - what config is default per corpus (if differences exist)

**Acceptance:** “Baseline” refers to the v1 suite outputs, not ad-hoc older runs.

---

## 6) Code cleanup pass (Stage A, Stage B, Retrieval Lab boundaries)

### 6.1 Enforce stage boundaries
- [ ] Stage A outputs are used by Stage B only through defined interfaces.
- [ ] Stage B outputs are used by Retrieval Lab only through defined schemas.
- [ ] No hidden coupling (e.g., “special-case PHB” in Stage B logic without config).

### 6.2 Deterministic ordering everywhere
- [ ] All iterations over dicts/sets are sorted deterministically.
- [ ] Stable ordering keys documented and tested:
  - document_id, page, structural_path, corpus_order index, unit_id
- [ ] Dedupe uses stable priority rules (EvidenceUnit preferred over family anchor when both exist).

### 6.3 Remove dead code paths / knobs from happy path
- [ ] Keep experimental knobs behind explicit config flags.
- [ ] Document which knobs are “research-only”.

**Acceptance:** Running the same pipeline twice yields byte-identical outputs for Stage A and Stage B artifacts and stable Retrieval Lab results.

---

## 7) Test wall (robust stabilization)

### 7.1 Determinism replay tests (must-have)
- [ ] Stage A determinism test:
  - same input → byte-identical output artifacts
- [ ] Stage B determinism test:
  - same Stage A input artifacts → byte-identical EvidenceUnits
- [ ] Retrieval Lab determinism test:
  - same corpus + config → identical rankings and metrics

### 7.2 Schema validation tests (must-have)
- [ ] Validate every emitted artifact against the schema registry.
- [ ] Add “schema evolution” tests (new fields must be optional or version-bumped).

### 7.3 Golden fixture tests (tiny corpus)
Create a small fixture (few pages) and lock:
- [ ] structural_path extraction
- [ ] EvidenceUnit ids and provenance fields
- [ ] clause-family construction for a handful of anchors
- [ ] dual-list fusion merge order (deterministic)

### 7.4 Regression tests on baseline suite (guardrail)
- [ ] Test that v1 baseline suite stays within allowed deltas.
- [ ] Enforce “no T1 regressions” policy for dual-list fusion:
  - T1 regressions count must remain 0 unless explicitly waived with an ADR.

### 7.5 Instrumentation tests
- [ ] Pairing instrumentation emits expected counters even when 0.
- [ ] Clause-family params logged correctly per run.

**Acceptance:** CI fails on nondeterminism, schema drift, or baseline regression outside policy.

---

## 8) CI / Automation updates

- [ ] Add CI job: schema validation + determinism replay (fixtures)
- [ ] Add CI job: run minimal Retrieval Lab smoke test (fixture corpus)
- [ ] Add nightly (optional): run v1 baseline suite across all books

**Acceptance:** Main branch is protected by deterministic regression checks.

---

## 9) Stage C / D readiness gates (do not start until these pass)

### Gate for Stage C (LLM enrichment)
- [ ] Stage A/B artifacts stable under refactor (determinism tests pass)
- [ ] v1 docs complete and canonical
- [ ] baseline suite reproducible and archived
- [ ] clear contract: enrichment is non-authoritative and cannot alter EvidenceUnits
- [ ] enrichment outputs have their own schema + provenance

### Gate for Stage D (graph)
- [ ] Stage C outputs stable and schema-validated
- [ ] graph construction is deterministic and replayable
- [ ] graph edges and node types have contracts and versioning
- [ ] Retrieval Lab can evaluate graph-assisted retrieval separately from Stage B

**Acceptance:** Stage C/D begin only after v1 stability is achieved.

---

## 10) Final deliverables checklist (Definition of Done)

- [ ] `docs/v1/` complete (overview, Stage A/B contracts, Retrieval Lab, schemas, glossary, ADRs)
- [ ] `docs/archive/pre_v1/` populated with deprecated docs + forward pointers
- [ ] Retrieval Lab code/docs cleaned; baseline configs normalized
- [ ] `evals/v1_baseline/` created for all books; old evals archived
- [ ] Code cleanup completed (boundaries + determinism)
- [ ] Tests implemented and passing in CI (determinism + schema + golden fixtures + regression guardrails)
- [ ] Readme or top-level pointer updated: “Start here: docs/v1/architecture_overview.md”
- [ ] Stage C/D gated with explicit readiness checks

---

## Notes / default policy decisions (v1)
- EvidenceUnits are canonical admissible evidence.
- Clause families are retrieval-only projections.
- Dual-list fusion is the PHB production default.
- Pairing edges are dependency-oriented (delta/base, exception/base) and must be instrumented before claiming benefit.
- No T1 regressions allowed under default configs without an ADR.

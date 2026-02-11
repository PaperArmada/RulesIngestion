# Stage A′ Contract — LLM Representational Enrichment (Retrieval-Only)

**Status:** Draft (Intended Canonical)

---

## Purpose

Stage A′ (A-Prime) produces **retrieval-only semantic annotations** over EvidenceUnits to improve recall and ranking for paraphrased, terse, or stylistically mismatched queries (e.g., Swords & Wizardry, Starfinder 2e).

Stage A′ exists to close the _representation gap_ between:

- user-shaped questions and
- verbatim rulebook phrasing.

Stage A′ is strictly a **retrieval index augmentation** stage.

---

## Non-Goals (Hard Constraints)

Stage A′ MUST NOT:

- create new rules, facts, or implications
- paraphrase into authoritative statements
- use outside knowledge of the ruleset
- modify, merge, or split EvidenceUnits
- participate in Stage C grounding or GraphDelta construction
- be cited as evidence in answers

Stage A′ outputs are **never admissible evidence**.

---

## Inputs

Stage A′ consumes EvidenceUnits produced by Stage B (Evidence Binding).

Each EvidenceUnit MUST provide:

- `verbatim_text`
- `structural_path`
- `unit_type` (core_text, table, example, sidebar, variant, etc.)
- `ordering_key`
- `source_document`
- `page_range`
- `quality_flags`

Optional:

- `table_schema` (if unit_type is table)

---

## Outputs

Stage A′ produces a versioned enrichment object attached to each EvidenceUnit:

- `evidence_unit.enrichment.v1`

This object is used **only** by retrieval (indexing and ranking). Retrieval may index A′ fields; retrieval must never treat them as evidence.

Stage A′ MUST additionally output:

- a deterministic cache key
- a run manifest with model + prompt versioning

---

## Authority Policy

All Stage A′ enrichment is tagged:

- `authority = "none"`
- `source = "llm_annotation"`
- `admissibility = "non_evidence"`
- `stage_c_visibility = "hidden"`
- `citation_policy = "never_cite"`

Any system component that uses Stage A′ fields as evidence is in violation of the contract.

---

## Enrichment Schema (A_PRIME_V1)

Stage A′ MUST output JSON conforming to the following schema.

### Top-level metadata (required)

- `enrichment_version`: exactly `"A_PRIME_V1"`
- `model_id`: string (exact model identifier)
- `prompt_id`: exactly `"A_PRIME_PROMPT_V1"`
- `input_fingerprint`: hash of `(verbatim_text + structural_path + unit_type + table_schema_if_any)`
- `created_at`: ISO-8601 timestamp
- `authority`: exactly `"none"`
- `source`: exactly `"llm_annotation"`
- `admissibility`: exactly `"non_evidence"`
- `stage_c_visibility`: exactly `"hidden"`
- `citation_policy`: exactly `"never_cite"`

### Core retrieval fields (required; may be empty)

1. `summary_1s` (string)

- One sentence, 8–30 words
- Neutral topic paraphrase only

2. `summary_3b` (string)

- Exactly 3 bullet lines
- Each bullet 6–18 words
- No new claims

3. `topic_tags` (array of strings)

- Length 1–6
- Values MUST be selected from the allowed vocabulary below

#### Allowed `topic_tags` vocabulary (initial)

- `actions`
- `reactions`
- `initiative`
- `movement`
- `cover_concealment`
- `conditions`
- `dying`
- `death_and_dying`
- `healing`
- `attacks`
- `damage`
- `critical_hits`
- `resistance_weakness_immunity`
- `spells`
- `spellcasting`
- `spell_slots`
- `spell_heightening`
- `counteracting`
- `skill_checks`
- `perception`
- `stealth`
- `saves`
- `equipment`
- `weapons`
- `armor`
- `items`
- `traits`
- `keywords`
- `definitions`
- `procedures`
- `timing`
- `frequency_limits`
- `duration`
- `character_options`
- `feats`
- `class_features`
- `ancestry_features`
- `environment`
- `hazards`
- `afflictions`
- `poison_disease`

Book-specific extensions (e.g., S&W) MUST be versioned and documented.

4. `co_retrieval_hints` (array of objects) — R6, R10

- Length 0–5
- Each hint: `related_topic` (topic_tag from vocabulary), `relationship` (prerequisite | exception_to | modifies | requires_context), `confidence` (explicit | strong_inference)
- Use `exception_to` when unit states an exception to another rule (R10)
- Authority: retrieval-only; never cite as evidence

5. `mechanic_atoms` (array of objects)

- Length 0–8

Each atom:

- `type`: one of
  - `definition`
  - `procedure_step`
  - `modifier`
  - `permission`
  - `prohibition`
  - `frequency`
  - `duration`
  - `trigger`
  - `exception`
  - `table_rule`
- `surface_forms`: array of 1–4 strings
  - Each MUST be an exact substring of `verbatim_text`
- `paraphrases`: array of 1–3 strings
  - Must not add information
- `requires_parent`: boolean
- `risk_flags`: array of strings from:
  - `delta_only`
  - `orphan_step`
  - `example_only`
  - `table_fragment`
  - `term_without_definition`
  - `negative_space`

5. `questions_answered` (array of strings)

- Length 3–10
- Each 8–18 words
- Must be answerable from this unit alone OR from this unit + its parent section
- If parent is needed, `mechanic_atoms[*].requires_parent` MUST reflect that

6. `lexical_anchors` (array of strings)

- Length 5–20
- Exact surface tokens/phrases useful for lexical matching

---

## Determinism & Caching

Stage A′ MUST be deterministic at the pipeline level.

Requirements:

- A′ must run with fixed generation parameters (e.g., temperature 0)
- Output must be cached by:
  - `(input_fingerprint + prompt_id + model_id)`
- Re-running Stage A′ on unchanged inputs MUST produce identical enrichment blobs

If the upstream text changes, the fingerprint changes.

---

## Prompt Contract (A_PRIME_PROMPT_V1)

Stage A′ MUST use a **single frozen prompt** per version.

Prompt requirements:

- Provide the model with:
  - `book_id`, `unit_type`, `structural_path`, `verbatim_text`, optional `table_schema`
- Instruct:
  - Output JSON only
  - No outside knowledge
  - No new facts
  - All `surface_forms` must be exact substrings
  - Use only allowed `topic_tags`
  - Flag fragments via `requires_parent` and `risk_flags`

The exact prompt text MUST be stored in-repo and hashed.

---

## Retrieval Integration Policy

Retrieval may index:

- `verbatim_text`
- `summary_3b`
- `questions_answered`
- `lexical_anchors`

Retrieval must NOT:

- treat A′ fields as evidence
- cite A′ fields
- allow A′ fields to create or justify facts

Stage C (Graph Construction) must:

- ignore A′ fields completely

---

## Acceptance Tests

### A′-01 Output Schema Validity

- Every enriched EvidenceUnit validates against the schema

### A′-02 Substring Enforcement

- Every `mechanic_atoms.surface_forms[]` is a substring of `verbatim_text`

### A′-03 No Evidence Leakage

- Stage C input parser rejects A′ fields
- Answer synthesis layer refuses to cite A′ fields

### A′-04 Deterministic Replay

- Two runs with identical inputs produce byte-identical enrichment output

### A′-05 Fragment Flagging

- Deltas without base rules produce `requires_parent=true` and include `delta_only`

---

## Principle

**Stage A′ improves finding text.**  
**Stage C decides what text is allowed to mean.**

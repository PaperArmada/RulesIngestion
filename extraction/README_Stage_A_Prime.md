# Stage A′ — Representational Enrichment (Retrieval-Only)

Stage A′ (A-Prime) adds **retrieval-only semantic annotations** to every EvidenceUnit produced by Stage B. It does not create or change rules; it only augments how units are represented for **retrieval indexing** so that paraphrased, terse, or stylistically different queries can find the right evidence.

This README summarizes **what is enriched**, **how** it is produced, and **how it will be used**. The latest detailed A-prime contract is retained in `Docs/Design/archive/stage_a_prime_contract.md`; Stage A' itself is currently optional and outside the canonical `v1/` ingestion baseline.

---

## What Is Being Enriched

**Input:** EvidenceUnits from **Stage B** (Mark III pipeline).

Each unit is a segment of rulebook content with:

- **Verbatim text** — exact text from the source
- **Structural path** — e.g. `["Combat", "Actions", "Attack"]`
- **Unit type** — prose, table, example, sidebar, etc.
- **Ordering, page, and quality metadata**

Stage A′ does **not** change the unit’s text or boundaries. It attaches a single **enrichment object** per unit (schema version `A_PRIME_V1`) that describes the same content in retrieval-friendly form.

---

## Why Enrich

There is a **representation gap** between:

- **User questions** — paraphrased, short, or from a different game’s wording
- **Rulebook phrasing** — verbatim, system-specific terms

Enrichment closes that gap by adding:

- **Summaries** — one-sentence and three-bullet neutral paraphrases
- **Topic tags** — from a fixed vocabulary (e.g. `actions`, `attacks`, `conditions`)
- **Mechanic atoms** — definitions, procedure steps, modifiers, with surface forms and paraphrases
- **Questions answered** — natural-language questions this unit (or unit + parent) answers
- **Lexical anchors** — surface phrases useful for keyword/lexical matching

All of this is **non-evidence**: it is never cited, never used for grounding, and never treated as authoritative. It exists only to improve **recall and ranking** in retrieval.

---

## How Enrichment Is Produced

### Pipeline position

- **Stage A** — PDF → structure (blocks, tables).
- **Stage B** — Structure → EvidenceUnits (verbatim segments).
- **Stage A′** — EvidenceUnits → one enrichment payload per unit (retrieval-only).

Stage A′ runs **after** Stage B. It can be run over existing Stage B output without re-running A or B.

### Mechanism

1. **One LLM call per unit** (or batched per page), with a **frozen prompt** (`A_PRIME_PROMPT_V2`).
2. **OpenAI Responses API** with **Structured Outputs**: the model is constrained to return JSON that conforms to the `APrimeEnrichment` Pydantic schema. No ad-hoc parsing or retries for format.
3. **Determinism:** `temperature=0`; cache key = `hash(input_fingerprint | prompt_id | model_id)`. Re-runs on unchanged input reuse the cache.
4. **Gates:** After enrichment, gates check schema validity, substring consistency (surface forms in verbatim text), and fragment flagging. Results are written regardless; gates are for diagnostics and pipeline quality.

**Inputs to the prompt:** `book_id`, `unit_type`, `structural_path`, `verbatim_text`, and optional `table_schema` for table units. The model is instructed to annotate only what is present and to avoid adding facts or outside knowledge.

**Key code:**

- **Schema:** `extraction/schemas_a_prime.py` — `APrimeEnrichment`, `MechanicAtom`, validators, `compute_input_fingerprint`.
- **Worker:** `extraction/stage_a_prime.py` — prompt loading, `_responses_parse_sync` (Responses API + `text_format=APrimeEnrichment`), caching, batch enrichment, gates.
- **Gates:** `extraction/gates_a_prime.py`.
- **Pipeline:** `extraction/pipeline.py` — `run_a_b_aprime()`, `write_stage_a_prime_artifacts()`.
- **Prompt:** `extraction/prompts/A_PRIME_PROMPT_V2.md`.

### Enrichment schema (summary)

| Field                | Purpose                                                                                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `summary_1s`         | One sentence, 5–30 words; neutral paraphrase.                                                                                                           |
| `summary_3b`         | 1–3 bullet lines, each 4–18 words; no new claims.                                                                                                       |
| `topic_tags`         | 0–6 tags from allowed vocabulary (e.g. actions, attacks, conditions).                                                                                   |
| `mechanic_atoms`     | 0–8 atoms: type (definition, procedure_step, modifier, …), surface_forms (exact substrings of verbatim text), paraphrases, requires_parent, risk_flags. |
| `questions_answered` | 1–10 natural-language questions this unit (or unit + parent) answers; 5–18 words each.                                                                  |
| `lexical_anchors`    | 1–20 surface phrases for lexical matching.                                                                                                              |

All payloads also carry metadata: `authority="none"`, `source="llm_annotation"`, `admissibility="non_evidence"`, `stage_c_visibility="hidden"`, `citation_policy="never_cite"`. Exact field rules and vocabulary are documented in `Docs/Design/archive/stage_a_prime_contract.md` plus the live `schemas_a_prime.py` implementation.

---

## Output Artifacts (Where to Review)

Stage A′ writes **per page directory** (same dir that contains `stageB.evidence_units.json`):

| File                                | Contents                                                               |
| ----------------------------------- | ---------------------------------------------------------------------- |
| `stageAPrime.enrichments.json`      | Map from EvidenceUnit `unit_id` to enrichment dict (all fields above). |
| `stageAPrime.run_manifest.json`     | Run metadata: model_id, prompt_id, prompt hash, counts.                |
| `stageAPrime.gate_diagnostics.json` | Gate results and diagnostics for this page.                            |

**Cache:** Per-page cache dir `a_prime_cache/` stores enrichment JSON by cache key so repeated runs skip LLM calls for unchanged units.

**Example (StarFinder Player Core):**

```text
out/mark3_evaluation/StarFinderPlayerCore/
  PZO22001 Starfinder Player Core 001-013/
    PZO22001 Starfinder Player Core 001-013_p0/
      stageB.evidence_units.json
      stageAPrime.enrichments.json    ← review enrichments here
      stageAPrime.run_manifest.json
      stageAPrime.gate_diagnostics.json
      a_prime_cache/
        <hash>.json
```

There is no single merged file; review is per page dir via `stageAPrime.enrichments.json`.

---

## How Enrichment Will Be Used

- **Retrieval indexing only.** Enrichment is designed to be consumed by retrieval (e.g. retrieval lab, DungeonMindServer RulesLawyer). Possible uses:

  - **Dense retrieval:** Embed concatenations of verbatim text + summary_1s + summary_3b + questions_answered (or similar) to improve semantic match.
  - **Lexical/BM25:** Index `lexical_anchors`, topic_tags, and summaries for keyword matching.
  - **Query expansion:** Use topic_tags and questions_answered to expand or reweight queries.
  - **Hybrid:** Combine dense and lexical scores using enriched text and anchors.

- **Never used as evidence.** Enrichment must not be cited, used for Stage C grounding, or shown as authoritative. Any component that treats A′ output as evidence violates the contract.

- **Current state.** The retrieval lab today loads `stageB.evidence_units.json` from the substrate; integration of `stageAPrime.enrichments.json` into indexing and scoring is the intended next step so that retrieval can leverage the new fields.

---

## Running Stage A′

**Single page:**

```bash
cd RulesIngestion
export OPENAI_API_KEY='…'
uv run python scripts/run_stage_a_prime.py \
  --page-dir "out/mark3_evaluation/StarFinderPlayerCore/…/…_p0" \
  --book-id StarFinderPlayerCore
```

**Full substrate (all page dirs under a root):**

```bash
uv run python scripts/run_stage_a_prime.py \
  --substrate-dir out/mark3_evaluation/StarFinderPlayerCore \
  --book-id StarFinderPlayerCore \
  --concurrency 10
```

**With full Mark III pipeline (A + B + A′ per page from PDF):**

```bash
uv run python scripts/run_mark3_full_pdf.py --pdf path/to/book.pdf --stage ab+aprime
```

---

## References

| Document                                    | Purpose                                                              |
| ------------------------------------------- | -------------------------------------------------------------------- |
| `Docs/Design/archive/stage_a_prime_contract.md` | Historical detailed contract for the current A-prime shape.      |
| `extraction/prompts/A_PRIME_PROMPT_V2.md`   | Active frozen prompt used by the current implementation.             |
| `Docs/architecture/OpenAI_Responses_API.md` | Responses API + Structured Outputs; Stage A′ usage note.             |
| `scripts/run_stage_a_prime.py`              | CLI for single-page or substrate-wide A′ runs.                       |

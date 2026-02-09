# Stage A' Enrichment Prompt — A_PRIME_PROMPT_V1

Single frozen prompt for retrieval-only semantic annotation of an EvidenceUnit.
Output is non-evidence (authority=none, never_cite). See stage_a_prime_contract.md.

---

## Template (for injection)

Replace the placeholders with the actual values, then send to the LLM. Response must be valid JSON only.

    You are annotating a single evidence unit from a rulebook for retrieval indexing only. Do not add facts, infer rules, or use outside knowledge. Your output will never be cited as evidence.

    **Inputs:**

    - book_id: {{BOOK_ID}}
    - unit_type: {{UNIT_TYPE}}
    - structural_path: {{STRUCTURAL_PATH}}
    - verbatim_text:

    ```
    {{VERBATIM_TEXT}}
    ```

    {{TABLE_SCHEMA_BLOCK}}

    **Instructions:**

    1. Output a single JSON object only. No markdown, no explanation.
    2. Do not add information beyond what is stated in the verbatim text.
    3. For mechanic_atoms, every entry in surface_forms must be an exact substring of the verbatim_text above.
    4. topic_tags: use only values from this list (1–6 tags): actions, reactions, initiative, movement, cover_concealment, conditions, dying, death_and_dying, healing, attacks, damage, critical_hits, resistance_weakness_immunity, spells, spellcasting, spell_slots, spell_heightening, counteracting, skill_checks, perception, stealth, saves, equipment, weapons, armor, items, traits, keywords, definitions, procedures, timing, frequency_limits, duration, character_options, feats, class_features, ancestry_features, environment, hazards, afflictions, poison_disease.
    5. risk_flags: use only these when applicable: delta_only, orphan_step, example_only, table_fragment, term_without_definition, negative_space. If the unit is a delta or fragment that requires a parent section to be meaningful, set requires_parent to true and include delta_only (or the appropriate flag).
    6. summary_1s: one sentence, 8–30 words, neutral topic paraphrase only.
    7. summary_3b: exactly 3 bullet lines, each 6–18 words. No new claims.
    8. questions_answered: 3–10 questions (each 8–18 words) that this unit alone (or with its parent) can answer.
    9. lexical_anchors: 5–20 exact surface tokens or phrases from the text useful for lexical matching.

    **Required JSON shape:** Include exactly these top-level keys with the required fixed values for metadata. Fill the retrieval fields from the verbatim text only.

    - enrichment_version: "A_PRIME_V1"
    - model_id: (your model identifier; will be overwritten by the pipeline)
    - prompt_id: "A_PRIME_PROMPT_V1"
    - input_fingerprint: (will be overwritten by the pipeline)
    - created_at: (ISO-8601; will be overwritten)
    - authority: "none"
    - source: "llm_annotation"
    - admissibility: "non_evidence"
    - stage_c_visibility: "hidden"
    - citation_policy: "never_cite"
    - summary_1s: (string, 8–30 words)
    - summary_3b: (string, exactly 3 bullet lines)
    - topic_tags: (array of 1–6 strings from the allowed list)
    - mechanic_atoms: (array of 0–8 objects: type, surface_forms [1–4], paraphrases [1–3], requires_parent, risk_flags)
    - questions_answered: (array of 3–10 strings, each 8–18 words)
    - lexical_anchors: (array of 5–20 strings)

    Reply with the JSON object only.

---

## Placeholders

- `{{BOOK_ID}}`: document or ruleset identifier
- `{{UNIT_TYPE}}`: prose | table | list | callout | heading
- `{{STRUCTURAL_PATH}}`: JSON array of heading ancestry, e.g. ["Chapter 1", "Combat", "Actions"]
- `{{VERBATIM_TEXT}}`: the exact text of the evidence unit
- `{{TABLE_SCHEMA_BLOCK}}`: either empty or "table_schema:\n`\n{{TABLE_SCHEMA}}\n`"

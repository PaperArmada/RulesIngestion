# Per-Query Gold Diff (Starfinder 2e)

Reference for curating gold EvidenceUnit sets and scoring rubrics. Use when updating batch JSONs or interpreting retrieval metrics.

---

## blind_001_01 — Vent Gas countermeasures

**Current gold:** Vent Gas definition chunk; Gust of Wind / wind effects; Alternate senses / detection.

| Action     | Content                                                                                               |
| ---------- | ----------------------------------------------------------------------------------------------------- |
| **KEEP**   | Vent Gas definition; Alternate senses (precise / scent).                                              |
| **ADD**    | General rule: wind dispersing gases / clouds (axiomatic permission that makes Gust of Wind relevant). |
| **REMOVE** | None.                                                                                                 |

**Reason:** Without the general dispersion rule, the answer relies on player intuition instead of textual authority. Classic missing parent axiom.

---

## blind_001_02 — Complementary feats (Lashunta Solarian)

**Current gold:** Lashunta ancestry feats; Solarian class feat access; Class table.

| Action         | Content                                                               |
| -------------- | --------------------------------------------------------------------- |
| **KEEP**       | Lashunta ancestry feat definitions; Solarian class feat access table. |
| **REMOVE**     | Any chunk that only implies "synergy" or optimization.                |
| **DO NOT ADD** | "Recommended" or example text.                                        |

**Reason:** Query is partially advisory. Gold should support availability and legality, not "good build advice." Over-golding creates false grounding expectations.

---

## blind_001_03 — Redirect Current powering devices

**Current gold:** Redirect Current ability text.

| Action     | Content                                                                                                                           |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **KEEP**   | Redirect Current definition.                                                                                                      |
| **ADD**    | Rule governing powering / interfacing with technological devices. **OR** mark query as refusal-acceptable if no such rule exists. |
| **REMOVE** | —                                                                                                                                 |

**Reason:** Negative-space query. Correct answer is "no, because nothing allows it." Gold must include the constraint, not just the ability.

---

## batch_004_01 — Dying recovery check timing

**Current gold:** Dying condition rules; Start-of-turn timing.

| Action           | Content |
| ---------------- | ------- |
| **KEEP**         | Both.   |
| **ADD / REMOVE** | None.   |

**Reason:** Model example of a correct, minimal, authoritative gold set.

---

## batch_004_03 — "About to attempt" reaction timing

**Current gold:** Reaction timing text; Recovery check procedure.

| Action   | Content                                     |
| -------- | ------------------------------------------- |
| **KEEP** | Both.                                       |
| **ADD**  | General reaction interrupt precedence rule. |

**Reason:** "About to attempt" is interpreted via reaction precedence. Without that rule, the answer is linguistically inferred instead of mechanically grounded.

---

## batch_005_02 — Grabbed condition prohibitions

**Current gold:** Multiple grabbed sub-clauses.

| Action     | Content                                |
| ---------- | -------------------------------------- |
| **KEEP**   | One full grabbed condition definition. |
| **REMOVE** | Clause-only fragments.                 |

**Reason:** Clause fragments inflate gold without adding authority. Gold should be complete, not granular.

---

## batch_005_03 — Frequency: once per round

**Current gold:** Frequency rule; Usage limits.

| Action   | Content                                          |
| -------- | ------------------------------------------------ |
| **KEEP** | Both.                                            |
| **ADD**  | "Round vs turn" definition chunk (if retrieved). |

**Reason:** Known confusion trap. Over-grounding is desirable to avoid false negatives.

---

## batch_006_01 — Why group conditions conceptually

**Current gold:** Conceptual explanation chunk.

| Action   | Content |
| -------- | ------- |
| **KEEP** | As is.  |

**Reason:** Conceptual queries correctly rely on narrative-authority text. Gold is doing the right job.

---

## batch_006_03 — Spell sensory manifestations

**Current gold:** Spellcasting sensory description.

| Action   | Content                                                   |
| -------- | --------------------------------------------------------- |
| **KEEP** | With qualification.                                       |
| **FLAG** | Not absolute — evaluator should accept qualified answers. |

**Reason:** "Default expectation" rule, not an invariant. Gold is valid; scoring rubric must allow nuance.

---

## Summary: Systemic Gold Issues

**Patterns that require adding gold:**

- Negative-space constraints (what the rules forbid or don’t allow).
- Reaction / timing precedence (general interrupt rules).
- Delta rules (increase/reduce language, parent axioms).

**Patterns that require removing gold:**

- Table-only justification (when table alone doesn’t state the rule).
- Example-only text.
- Clause fragments without parent (incomplete units).

Use this diff when editing `batch_*.json` gold fields and when defining evaluation rubrics for nuanced queries (e.g. batch_006_03).

---

## Implementation status

| Item                                                | Status | Notes                                                                                                                 |
| --------------------------------------------------- | ------ | --------------------------------------------------------------------------------------------------------------------- |
| **blind_001_03** rubric                             | Done   | `refusal_acceptable: true`, `scoring_rubric` in `batch_001.json`. Surfaces in REPORT.md §6 "Query rubric notes".      |
| **batch_006_03** rubric                             | Done   | `accept_qualified_answer: true`, `scoring_rubric` in `batch_006_conceptual.json`. Surfaces in REPORT.md §6.           |
| **Gold ADD** (blind_001_01, 001_03, 004_03, 005_03) | Manual | Resolve unit_ids from corpus or `retrieved_chunks.json`, then add to `gold_unit_ids` in the batch JSONs.              |
| **Gold REMOVE** (batch_005_02 clause fragments)     | Manual | Identify fragment unit_ids (e.g. from retrieval output), remove from `gold_unit_ids` in `batch_005_constraints.json`. |

Grounding audit and report: `gold_grounding.py` copies `refusal_acceptable`, `accept_qualified_answer`, and `scoring_rubric` from each query into the grounding_audit; `report.py` emits a "Query rubric notes" subsection when any audit entry has those fields.

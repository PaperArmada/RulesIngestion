> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# Pedagogical Signal Contract (PSC v0.1)

## Purpose
Define deterministic, query-independent pedagogical signals extracted from a rulebook and used solely to constrain and score grounding eligibility.

Pedagogical signals encode **authorial intent**, not learned inference. They never participate in traversal or fact synthesis.

---

## Non-Goals
- No learned models or probabilistic weights
- No embeddings or similarity heuristics
- No traversal or recall modification
- No feedback loops into ingestion

Violating any non-goal invalidates this contract.

---

## Signal Model

```text
PedagogicalSignal {
  signal_id: StableId
  scope: document | chapter | section | chunk
  type: SignalType
  value: Scalar | Enum | Set | Edge
  provenance: { ingestion_step, source_location }
}
```

All signals are immutable after ingestion.

---

## Signal Types

### Dependency Signals
`assumes_knowledge(concept_id, from_section → to_section)`

Grounding may not allow descendant sections to override ancestors unless explicitly marked as exceptions.

---

### Example Density
`example_density(section_id) ∈ [0.0, 1.0]`

Higher density dampens authority; never excludes.

---

### Negative Space
`expected_absence(system_a, system_b)`

If a query implies an absent relationship, explicit evidence is required or grounding must refuse synthesis.

---

### Voice & Modality
`voice_type ∈ { normative, prohibitive, permissive, advisory, illustrative, narrative }`

Priority order:
`normative > prohibitive > permissive > advisory > illustrative > narrative`

---

### Layout Authority
`layout_tier ∈ { core_text, sidebar, variant_box, example, footnote }`

Lower tiers may never override higher tiers.

---

### Axiomatic Restatement
Clusters of near-identical passages. One canonical instance is preferred during grounding.

---

### Error-Prevention Cues
`known_confusion(trigger_terms, corrective_chunk)`

If triggered, corrective content must be surfaced or explanation refused.

---

### Chapter Role Hierarchy
`chapter_role ∈ { ontology, procedure, options, variants, narrative }`

Override order:
`ontology > procedure > options > variants`

---

### Forward Reference
`authority_deferral(from_chunk → to_section)`

Grounding prefers the target section.

---

### Book Epistemology
Global epistemic rules extracted from preface and usage guides.

---

## Grounding Boundary
Pedagogical signals may only:
- exclude candidates
- re-rank candidates
- enforce admissibility constraints

They may never introduce new facts or entities.

---

## Determinism Guarantees
- Fixed extraction rules
- Stable ordering
- Identical inputs produce identical grounding constraints

---

## Kill Criteria
A signal must be removed if it:
- increases refusals without accuracy gain
- introduces nondeterminism
- masks extraction failures

---

## Principle
Traversal finds possibilities. Pedagogy decides legitimacy.


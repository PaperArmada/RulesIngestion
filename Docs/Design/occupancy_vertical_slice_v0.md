# Occupancy Vertical Slice v0

**Status:** Draft for review  
**Purpose:** Define the first exact runtime behavior to prove, the first atomic rule statement, the exact grounding question, and the minimal JSON schemas needed to evaluate a same-cell placement attempt.

---

## 1. Canonical framing

This draft assumes the current Rules Ingestion philosophy remains in force:

- EvidenceUnits are canonical admissible evidence.
- Retrieval projections and enrichments are non-authoritative.
- Runtime-facing rule artifacts must remain deterministic, replayable, and traceable back to source evidence.

This draft also assumes a **single ruleset surface** for the first slice:

- **Ruleset:** D&D 5e 2024 PHB occupancy behavior
- **Cell model:** 5-foot tactical cell
- **Focus:** legality of **ending placement** in an already occupied cell

This scope is intentionally narrower than general movement, full combat, or a full engine occupancy ontology.

---

## 2. Exact runtime behavior to prove

### 2.1 Behavior statement

**Behavior ID:** `cell_place_reject_001`

When a creature attempts to **end placement** in a 5-foot cell that already contains another creature, the engine rejects the placement unless an explicit exception rule applies.

### 2.2 First proved instance

For the first executable slice, lock the behavior further:

> Under the 2024 D&D 5e PHB occupancy ruleset, when a **Medium, corporeal, non-exceptional creature** attempts to end movement in a cell already occupied by another **Medium, corporeal, non-exceptional creature**, the engine returns **reject** with a deterministic rule trace unless the explicit ally-prone occupied-space allowance applies.

### 2.3 Why this is the right first slice

This behavior is small enough to test cleanly and concrete enough to force real contracts:

- a ruleset version
- an end-state legality check
- a rule artifact
- a deterministic evaluator
- a provenance-bearing rejection result

It avoids prematurely dragging in pathfinding, attacks of opportunity, difficult terrain accounting, or full movement sequencing.

### 2.4 Explicit non-scope for v0

The following are **not** part of this first proof:

- hostile vs nonhostile movement path differences
- difficult terrain cost accounting
- size-difference pass-through
- squeezing resolution
- Tiny multi-occupancy handling
- swarm exceptions
- incorporeal / ethereal exceptions
- forced movement resolution
- object occupancy

These may become later rules or exceptions, but they are not required for the first legality check.

---

## 3. First atomic rule statement

### 3.1 Rule intent

The first rule should be a **default prohibition**, not a complete occupancy ontology.

### 3.2 Rule statement

**Atomic Rule ID:** `occ_2024_end_move_in_occupied_space_default_with_ally_prone_exception`

**Statement:**

> A creature may not voluntarily end its movement in a cell already occupied by another creature. In the 2024 PHB ruleset, ending movement in an ally's occupied space is allowed only under the explicit ally-prone condition; otherwise placement is rejected.

### 3.3 Operational interpretation

For v0, interpret this rule with the following assumptions:

- the acting entity is a creature
- the occupying entity is a creature
- both entities are ordinary corporeal creatures
- no exception trait, feature, form, or spell is active
- relation context between acting and occupying entities is available (`ally` | `hostile` | `neutral`)
- ally-prone state required by the 2024 allowance is explicitly available in request/world-state inputs
- the evaluation concerns the **end state** of movement, not transient passage through the cell

### 3.4 Why this formulation

This rule is preferable to something like “two incompatible entities cannot share a cell” because:

- it is grounded in a concrete ruleset behavior
- it avoids introducing a premature compatibility ontology
- it is directly executable as a prohibition
- it leaves room for later exception rules to override it

### 3.5 Future extension shape

Later rules can layer on top as explicit overrides, for example:

- `occ_exception_halfling_pass_through_larger`
- `occ_exception_swarm_can_occupy_other_creature_space`
- `occ_exception_incorporeal_move_through_creatures`
- `occ_exception_tiny_multi_occupancy`

But none of those are required to prove the default prohibition.

---

## 4. Exact grounding question

### 4.1 Grounding question

**Grounding Question ID:** `ground_occ_2024_001`

> What D&D 5e 2024 PHB rule text establishes the default restriction on voluntarily ending movement in another creature's space?

### 4.2 Companion exception question

**Grounding Question ID:** `ground_occ_2024_002`

> What D&D 5e 2024 PHB rule text defines the ally-prone occupied-space allowance, including the exact condition and resulting legality?

### 4.3 Why two questions

The first question grounds the **default rule**.

The second question grounds the in-rule 2024 ally-prone branch required for this slice. Together, the two questions tell us whether the first rule artifact needs:

- an `exception_capable` field
- priority handling
- override references
- a separate exception track in the schema

### 4.4 Evidence discipline

For the first rule, use the smallest operational evidence set that makes the rule answerable.

**Target evidence shape:**

- `required_gold`: 1 core rule anchor
- `supporting_gold`: 1 ally-prone condition anchor
- `optional_supporting_gold`: 0-2 additional exception anchors

Do not expand this into a full movement benchmark item. The point is to support one first rule draft.

---

## 5. Minimal JSON schemas

These are intentionally minimal and are not yet a full compiler contract.

### 5.1 Placement request schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "rules-engine/placement_request.schema.json",
  "title": "PlacementRequest",
  "type": "object",
  "required": [
    "request_id",
    "ruleset_id",
    "cell_id",
    "entity",
    "intent"
  ],
  "properties": {
    "request_id": {
      "type": "string"
    },
    "ruleset_id": {
      "type": "string"
    },
    "cell_id": {
      "type": "string"
    },
    "entity": {
      "type": "object",
      "required": [
        "entity_id",
        "entity_kind",
        "traits"
      ],
      "properties": {
        "entity_id": { "type": "string" },
        "entity_kind": { "type": "string" },
        "traits": {
          "type": "array",
          "items": { "type": "string" }
        },
        "size": { "type": "string" }
      },
      "additionalProperties": false
    },
    "intent": {
      "type": "string",
      "enum": ["end_move_in_cell"]
    },
    "metadata": {
      "type": "object",
      "required": [
        "occupancy_relation",
        "ally_prone_condition_met"
      ],
      "properties": {
        "occupancy_relation": {
          "type": "string",
          "enum": ["ally", "hostile", "neutral"]
        },
        "ally_prone_condition_met": {
          "type": "boolean"
        }
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

### 5.2 Placement decision schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "rules-engine/placement_decision.schema.json",
  "title": "PlacementDecision",
  "type": "object",
  "required": [
    "request_id",
    "decision",
    "state_changed",
    "violations",
    "applied_rule_ids"
  ],
  "properties": {
    "request_id": {
      "type": "string"
    },
    "decision": {
      "type": "string",
      "enum": ["accept", "reject"]
    },
    "state_changed": {
      "type": "boolean"
    },
    "applied_rule_ids": {
      "type": "array",
      "items": { "type": "string" }
    },
    "violations": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [
          "rule_id",
          "reason_code"
        ],
        "properties": {
          "rule_id": { "type": "string" },
          "reason_code": { "type": "string" },
          "conflicting_entity_ids": {
            "type": "array",
            "items": { "type": "string" }
          },
          "source_evidence_refs": {
            "type": "array",
            "items": { "type": "string" }
          }
        },
        "additionalProperties": false
      }
    },
    "trace": {
      "type": "object"
    }
  },
  "additionalProperties": false
}
```

### 5.3 Rule draft schema

This is the smallest structured draft the evidence-collection loop should emit before any future compiler layer.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "rules-engine/atomic_rule_draft.schema.json",
  "title": "AtomicRuleDraft",
  "type": "object",
  "required": [
    "rule_id",
    "rule_kind",
    "statement",
    "ruleset_id",
    "source_evidence_refs"
  ],
  "properties": {
    "rule_id": { "type": "string" },
    "rule_kind": {
      "type": "string",
      "enum": ["forbid_end_move_in_occupied_cell_with_ally_prone_exception"]
    },
    "ruleset_id": { "type": "string" },
    "statement": { "type": "string" },
    "subject_pattern": {
      "type": "object"
    },
    "object_pattern": {
      "type": "object"
    },
    "priority": {
      "type": "integer",
      "default": 100
    },
    "exception_capable": {
      "type": "boolean",
      "default": true
    },
    "source_evidence_refs": {
      "type": "array",
      "items": { "type": "string" }
    },
    "notes": {
      "type": "array",
      "items": { "type": "string" }
    }
  },
  "additionalProperties": false
}
```

---

## 6. Example request and decision

### 6.1 Example request

```json
{
  "request_id": "req_place_001",
  "ruleset_id": "dnd5e_2024_phb_occupancy_v0",
  "cell_id": "cell_A1",
  "entity": {
    "entity_id": "entity_B",
    "entity_kind": "creature",
    "traits": ["medium", "corporeal", "ordinary"],
    "size": "medium"
  },
  "intent": "end_move_in_cell"
}
```

### 6.2 Example decision

```json
{
  "request_id": "req_place_001",
  "decision": "reject",
  "state_changed": false,
  "applied_rule_ids": [
    "occ_2024_end_move_in_occupied_space_default_with_ally_prone_exception"
  ],
  "violations": [
    {
      "rule_id": "occ_2024_end_move_in_occupied_space_default_with_ally_prone_exception",
      "reason_code": "occupied_cell_end_state_forbidden",
      "conflicting_entity_ids": ["entity_A"],
      "source_evidence_refs": ["ev_occ_001"]
    }
  ],
  "trace": {
    "cell_id": "cell_A1",
    "existing_occupants": ["entity_A"],
    "candidate_entity_id": "entity_B"
  }
}
```

### 6.3 Example request (ally-prone allowance path)

```json
{
  "request_id": "req_place_002",
  "ruleset_id": "dnd5e_2024_phb_occupancy_v0",
  "cell_id": "cell_A2",
  "entity": {
    "entity_id": "entity_D",
    "entity_kind": "creature",
    "traits": ["medium", "corporeal", "ordinary"],
    "size": "medium"
  },
  "intent": "end_move_in_cell",
  "metadata": {
    "occupancy_relation": "ally",
    "ally_prone_condition_met": true
  }
}
```

### 6.4 Example decision (ally-prone allowance path)

```json
{
  "request_id": "req_place_002",
  "decision": "accept",
  "state_changed": true,
  "applied_rule_ids": [
    "occ_2024_end_move_in_occupied_space_default_with_ally_prone_exception"
  ],
  "violations": [],
  "trace": {
    "cell_id": "cell_A2",
    "existing_occupants": ["entity_C"],
    "candidate_entity_id": "entity_D",
    "occupancy_relation": "ally",
    "ally_prone_condition_met": true,
    "rule_branch": "ally_prone_allowance"
  }
}
```

---

## 7. Review checklist before canonization

Canonize this draft only if the team agrees that:

- the first proof is about **end-state legality**, not full movement simulation
- the first rule should be a **default prohibition**, not a full occupancy ontology
- the first grounding question is narrow enough to support one atomic rule
- the schemas are minimal but concrete enough to support a tiny evaluator
- 2014 and 2024 rules should remain separated at the ruleset level

If all five hold, this document is ready to become the canonical v0 design note for the first runtime occupancy slice.

---

## 8. Retrieval gate and runnable artifacts

Use the following minimal files for the retrieval grounding gate:

- Benchmark input: `evals/retrieval/PHB5e/dnd_5e_2024_occupancy_vertical_slice_v0_benchmark.json`
- Experiment config: `retrieval_lab/experiments/hybrid/phb5e_occupancy_vertical_slice_v0.yaml`

Run from `RulesIngestion/`:

```bash
uv run python -m retrieval_lab.run_experiment retrieval_lab/experiments/hybrid/phb5e_occupancy_vertical_slice_v0.yaml
```

### 8.1 Expected artifacts

For the selected evaluation surface, require:

- `metrics.<surface>.json`
- `per_query.<surface>.json`
- `retrieved_chunks.<surface>.json`
- `prod_readiness.json`

### 8.2 Retrieval pass/fail gate

Pass only if:

1. `ground_occ_2024_001` retrieves the default-branch anchor as required gold.
2. `ground_occ_2024_002` retrieves the ally-prone branch anchor as required gold.
3. Both are visible in the selected scoring surface artifacts.

Fail if either required anchor is not present in candidates at the configured rank depth.

---

## 9. Bounded collect/draft/verify loop (AtomicRuleDraft)

The first rule draft must be emitted through a deterministic three-step loop.

### 9.1 Collect

- Input: grounded EvidenceUnit refs from the retrieval gate (`ground_occ_2024_001`, `ground_occ_2024_002`).
- Output: normalized evidence set with stable ordering by `unit_id`.
- Constraint: no retrieval-only projection ids are admitted as sources.

### 9.2 Draft

Emit one `AtomicRuleDraft` with:

- `rule_id`: `occ_2024_end_move_in_occupied_space_default_with_ally_prone_exception`
- `rule_kind`: `forbid_end_move_in_occupied_cell_with_ally_prone_exception`
- `ruleset_id`: `dnd5e_2024_phb_occupancy_v0`
- `source_evidence_refs`: exact collected EvidenceUnit ids
- Statement semantics containing both branches:
  - default occupied-space prohibition
  - ally-prone allowance branch

### 9.3 Verify

- Re-run collect + draft with identical inputs/config.
- Compare serialized JSON bytes.
- Pass only if outputs are byte-identical and all source refs are unchanged.

---

## 10. Runtime contract and fixture gate

### 10.1 Minimal runtime input contract

The evaluator input must include:

- acting entity
- existing occupants in target cell
- relation signal (`ally` | `hostile` | `neutral`)
- ally-prone condition state
- ruleset and intent (`end_move_in_cell`)

### 10.2 Golden fixture

Fixture file:

- `evals/runtime/occupancy_vertical_slice_v0_fixtures.json`

Required cases:

1. **Reject branch:** occupied cell with no ally-prone allowance.
2. **Accept branch:** occupied ally cell with ally-prone allowance met.

### 10.3 Runtime pass/fail gate

Pass only if both fixture cases produce deterministic outputs:

- stable `decision`
- stable `state_changed`
- stable `applied_rule_ids`
- stable `violations`
- stable trace branch reason


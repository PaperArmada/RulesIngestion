# RulesIngestion Design

This folder contains the **current canonical design suite** plus archived
historical material. Canonical docs are top-level in `Docs/Design/`.
Anything under `archive/` is historical reference and not normative by default.

## Canonical docs (current)

- **Start here:** [ARCHITECTURE-RulesIngestion-High-Level.md](ARCHITECTURE-RulesIngestion-High-Level.md)
- **Retrieval runtime plane:** [ARCHITECTURE-Retrieval-Runtime-Plane.md](ARCHITECTURE-Retrieval-Runtime-Plane.md)
- **Retrieval Lab current architecture:** [RETRIEVAL_LAB.md](RETRIEVAL_LAB.md)
- **Benchmark projection lifecycle:** [gold_resolution_design.md](gold_resolution_design.md)
- **Reranking architecture:** [ARCHITECTURE-RERANKING-TOOLING.md](ARCHITECTURE-RERANKING-TOOLING.md)
- **TOC structural enrichment:** [ARCHITECTURE-TOC-Structural-Enrichment.md](ARCHITECTURE-TOC-Structural-Enrichment.md)
- **Controller operator contract:** [SPEC-Controller-V0-Operators.md](SPEC-Controller-V0-Operators.md)

Current policy note (2026-03): NextPlaid/GTE is retained as a profile-gated first-hop rescue lever. It is not the default multihop path.

## Design taxonomy

| Location | Status | Purpose |
|---------|--------|---------|
| **Top-level design docs (`Docs/Design/*.md`)** | Canonical | Active architecture, runtime, retrieval, and benchmark policy surface. |
| **RETRIEVAL_LAB.md** | Canonical adjunct | Current Retrieval Lab architecture and live-system orientation. |
| **ARCHITECTURE-RulesIngestion-High-Level.md** | Canonical adjunct | High-level target architecture tying Stage A/B, Retrieval Lab, and Stage C. |
| **ARCHITECTURE-Retrieval-Runtime-Plane.md** | Canonical adjunct | Five-stage retrieval runtime path, validated defaults, retired flags, minimal config surface. |
| **gold_resolution_design.md** | Canonical adjunct | Benchmark definition/projection lifecycle and contract validation model. |
| **ARCHITECTURE-TOC-Structural-Enrichment.md** | Canonical adjunct | TOC enrichment architecture used by Mark III substrate shaping. |
| **SPEC-Controller-V0-Operators.md** | Canonical adjunct | Controller v0 contract and operator policy, with implementation notes. |
| **occupancy_vertical_slice_v0.md** | Draft (in review) | First runtime rule vertical slice for occupancy legality. |
| **STAGE_A_CONTRACT.md**, **STAGE_B_CONTRACT.md** | Legacy stubs | Compatibility stubs; point to current suite + archived historical contract copies. |
| **decision_lock_in_and_next_spec.md**, **stage_ab_v1_stabilization_checklist.md** | Historical in place | Planning / lock-in notes kept for rationale; not normative. |
| **ARCHITECTURE-Chunking-System-Deep-Dive-2026-02-28.md** | Historical in place | Dated regression and hardening analysis; useful context, not primary spec. |
| **DESIGN-Corpus-Specific-Query-Enhancement.md** | Historical in place | Proposed future retrieval design, not adopted as canonical policy. |
| **archive/** | Archived | Superseded design docs. See [archive/README.md](archive/README.md). |

## Archived docs to surface for review

These are archived but still relevant when reviewing current design choices:

- [archive/v1/architecture_overview.md](archive/v1/architecture_overview.md) — concise Stage A/B/Retrieval boundaries and invariants.
- [archive/v1/retrieval_lab_v1.md](archive/v1/retrieval_lab_v1.md) — legacy runbook and artifact contract language.
- [archive/v1/stage_a_contract.md](archive/v1/stage_a_contract.md) — historical Stage A contract details.
- [archive/v1/stage_b_contract.md](archive/v1/stage_b_contract.md) — historical Stage B admissibility contract details.
- [archive/v1/gates_stage_c_d.md](archive/v1/gates_stage_c_d.md) — Stage C/D promotion gates and guardrails.
- [archive/v1/adr/ADR-003.md](archive/v1/adr/ADR-003.md) — admissible evidence vs retrieval-only projections.

## Archive layout

- **Superseded design docs:** [archive/](archive/)
- **Pre-v1 contract copies:** [../../Archive/pre-v1/Docs/pre_v1/](../../Archive/pre-v1/Docs/pre_v1/)

# RulesIngestion Design

This folder mixes the **current canonical design surface** with a small set of
historical notes that are still worth keeping close at hand. When in doubt,
reason from `v1/` first.

## Canonical docs

- **Start here:** [v1/architecture_overview.md](v1/architecture_overview.md)
- **Stage A contract:** [v1/stage_a_contract.md](v1/stage_a_contract.md)
- **Stage B contract:** [v1/stage_b_contract.md](v1/stage_b_contract.md)
- **Retrieval Lab:** [v1/retrieval_lab_v1.md](v1/retrieval_lab_v1.md)
- **Baseline + schemas:** [v1/baseline_manifest.md](v1/baseline_manifest.md), [v1/schema_registry.md](v1/schema_registry.md), [v1/glossary.md](v1/glossary.md)
- **Benchmark projection lifecycle:** [gold_resolution_design.md](gold_resolution_design.md)
- **Stage C/D gates:** [v1/gates_stage_c_d.md](v1/gates_stage_c_d.md)
- **TOC structural enrichment:** [ARCHITECTURE-TOC-Structural-Enrichment.md](ARCHITECTURE-TOC-Structural-Enrichment.md)

## Design taxonomy

| Location | Status | Purpose |
|---------|--------|---------|
| **v1/** | Canonical | Normative contracts, architecture, retrieval lab, glossary, schema registry, ADRs. |
| **gold_resolution_design.md** | Canonical adjunct | Current benchmark definition/projection lifecycle. |
| **ARCHITECTURE-TOC-Structural-Enrichment.md** | Canonical adjunct | Current TOC enrichment architecture used by Mark III. |
| **STAGE_A_CONTRACT.md**, **STAGE_B_CONTRACT.md**, **RETRIEVAL_LAB.md** | Legacy stubs | Forwarders kept for old links that now point into `v1/`. |
| **decision_lock_in_and_next_spec.md**, **stage_ab_v1_stabilization_checklist.md** | Historical in place | Planning / lock-in notes kept for rationale and handoff context; not normative. |
| **ARCHITECTURE-Chunking-System-Deep-Dive-2026-02-28.md** | Historical in place | Dated regression and hardening analysis; useful context, not the primary spec. |
| **EXPERIMENT-Embedding-Metadata-Enrichment.md** | Historical in place | Experiment record and implementation note for embedding enrichment work. |
| **DESIGN-Corpus-Specific-Query-Enhancement.md** | Historical in place | Proposed future retrieval design, not adopted as canonical policy. |
| **SCHEMAS.json** | Supporting data | Schema registry data referenced by `v1/`. |
| **archive/** | Archived | Superseded design docs. See [archive/README.md](archive/README.md). |

## Archive layout

- **Superseded design docs:** [archive/](archive/)
- **Pre-v1 contract copies:** [../../Archive/pre-v1/Docs/pre_v1/](../../Archive/pre-v1/Docs/pre_v1/)

The pre-v1 archive contains the original `STAGE_A_CONTRACT.md`,
`STAGE_B_CONTRACT.md`, and `RETRIEVAL_LAB.md` documents that were replaced by
the canonical `v1/` set.

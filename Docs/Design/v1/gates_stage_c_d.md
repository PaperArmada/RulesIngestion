# Stage C / Stage D Readiness Gates

**Purpose:** Do not start Stage C or Stage D work until the corresponding gate checklist is satisfied. These gates ensure v1 stability before adding enrichment and graph layers.

---

## Gate for Stage C (LLM Enrichment)

- [ ] Stage A/B artifacts stable under refactor (determinism tests pass).
- [ ] v1 docs complete and canonical (Docs/Design/v1/).
- [ ] Baseline suite reproducible and archived (evals/v1_baseline/, baseline_manifest.md).
- [ ] Clear contract: enrichment is non-authoritative and **cannot alter EvidenceUnits**.
- [ ] Enrichment outputs have their own schema and provenance (versioned, tagged non_evidence).

**Acceptance:** Stage C begins only after v1 stability is achieved and the above are documented and verified.

---

## Gate for Stage D (Graph)

- [ ] Stage C outputs stable and schema-validated.
- [ ] Graph construction is deterministic and replayable.
- [ ] Graph edges and node types have contracts and versioning.
- [ ] Retrieval Lab can evaluate graph-assisted retrieval **separately** from Stage B (baseline).

**Acceptance:** Stage D begins only after Stage C gate is satisfied and graph contracts are in place.

---

See [architecture_overview.md](architecture_overview.md) for the pipeline diagram and artifact flow.

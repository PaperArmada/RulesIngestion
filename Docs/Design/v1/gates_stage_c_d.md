# Stage C / Stage D Readiness Gates

**Purpose:** Do not start Stage C or Stage D work until the corresponding gate checklist is satisfied. These gates ensure v1 stability before adding enrichment and graph layers.

---

## Stage A/B Ratification Gate

Ratification of the Stage A/B baseline is **strict-pass** on Stage B cleanliness for the archived substrate package:

- [ ] Every page directory with `stageB.evidence_units.json` also includes `stageB.gate_diagnostics.json`.
- [ ] Zero pages have failed Stage B gates in the ratified substrate package.
- [ ] Baseline integrity checks are run with Stage B gate policy = `strict`.
- [ ] The ratification evidence bundle includes per-corpus Stage B gate summaries and explicit failing-page details if any failure occurs.

**Acceptance:** A baseline cannot be called ratifiable if Stage B gate failures are merely known, tolerated, or omitted from the archived integrity packet. Any exception list must be explicit, bounded, and archived alongside the baseline package; absent such a list, zero failures is the policy.

---

## Gate for Stage C (LLM Enrichment)

- [ ] Stage A/B artifacts stable under refactor (determinism tests pass).
- [ ] v1 docs complete and canonical (Docs/Design/v1/).
- [ ] Baseline suite reproducible and archived (evals/v1_baseline/, baseline_manifest.md).
- [ ] Stage C starting point is a contract-valid canonical run referenced by `canonical_runs_index.json`.
- [ ] Stage C consumers use `prod_readiness.json` + selected surface, not ad hoc `metrics.json` assumptions.
- [ ] Stage C preserves baseline corpus fingerprint, corpus content fingerprint, and benchmark contract validity unless the substrate or benchmark is intentionally version-bumped.
- [ ] Clear contract: enrichment is non-authoritative and **cannot alter EvidenceUnits**.
- [ ] Enrichment outputs have their own schema and provenance (versioned, tagged non_evidence).

**Acceptance:** Stage C begins only after v1 stability is achieved and the above are documented and verified.

---

## Gate for Stage D (Graph)

- [ ] Stage C outputs stable and schema-validated.
- [ ] Graph construction is deterministic and replayable.
- [ ] Graph edges and node types have contracts and versioning.
- [ ] Retrieval Lab can evaluate graph-assisted retrieval **separately** from Stage B (baseline).
- [ ] Stage D comparison surfaces still validate against the frozen Stage A/B corpus contract or explicitly declare a version bump.
- [ ] Graph-assisted experiments preserve parity with the baseline package's selected benchmark surface when claiming like-for-like comparison.

**Acceptance:** Stage D begins only after Stage C gate is satisfied and graph contracts are in place.

---

See [architecture_overview.md](architecture_overview.md) for the pipeline diagram and artifact flow.

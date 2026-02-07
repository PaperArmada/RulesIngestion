# Stage C Contract — Semantic Lifting

## Purpose
Derive semantic graph structures from EvidenceUnits only.

## Outputs
- GraphDelta
- entity_index
- fact_index

## Invariants
- Every entity/fact must cite EvidenceUnit
- Facts are not entities
- No silent inference

## Gates
- Evidence-pointer gate
- Canonical stability gate
- Partition invariants

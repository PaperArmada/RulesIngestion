# RulesIngestion

Deterministic rulebook extraction and retrieval pipeline (Stage A, Stage B, Retrieval Lab).

**Start here:** [Docs/Design/v1/architecture_overview.md](Docs/Design/v1/architecture_overview.md)

- **Stage A:** Extraction + prose reconstruction (SurfaceAST).
- **Stage B:** Evidence binding (EvidenceUnits).
- **Retrieval Lab:** Eval and comparison over EvidenceUnits (baseline, dual-list fusion, pairing).

See [Docs/Design/v1/baseline_manifest.md](Docs/Design/v1/baseline_manifest.md) for baseline reproducibility and [Docs/Design/v1/retrieval_lab_v1.md](Docs/Design/v1/retrieval_lab_v1.md) for running evals.

## Setup

```bash
uv sync
uv run pytest tests/ -v
```

## CI

Schema validation, determinism replay, and instrumentation tests run on push/PR when `RulesIngestion/**` changes (see `.github/workflows/rules-ingestion-tests.yml` at repo root).

# RulesIngestion

Deterministic rulebook ingestion and retrieval-evaluation pipeline.

**Start here:** [Docs/Design/v1/architecture_overview.md](Docs/Design/v1/architecture_overview.md)

- **Stage A:** extraction + prose reconstruction (`SurfaceAST`).
- **Stage B:** evidence binding (`EvidenceUnits`).
- **Stage A':** optional retrieval-only enrichment over Stage B units.
- **Retrieval Lab:** embed/eval over Stage B substrate (with optional retrieval-time expansion features).

See [Docs/Design/v1/baseline_manifest.md](Docs/Design/v1/baseline_manifest.md) for reproducibility and [Docs/Design/v1/retrieval_lab_v1.md](Docs/Design/v1/retrieval_lab_v1.md) for retrieval-lab architecture.

## What You Can Do From This Repo

- Run ingestion on one page for debugging (`scripts/run_mark3_sample.py`).
- Run full-book ingestion (`scripts/run_mark3_full_pdf.py`) as:
  - `ab` (Stage A+B only), or
  - `ab+aprime` (Stage A+B then Stage A').
- Run Stage A' later on an existing Stage B substrate (`scripts/run_stage_a_prime.py`).
- Run retrieval benchmarking with embed-only and eval-only protocol (`retrieval_lab.run_experiment`).

## Current Best Practices (Canonical)

### Ingestion

1. **Default for retrieval tuning: run Stage A+B only first.**
   - Use `--stage ab` during full-book ingestion.
   - Rationale: Stage A' is time/cost intensive and usually not required to tune hybrid retrieval behavior.
2. **Run Stage A' separately when needed.**
   - Apply Stage A' as a second pass on existing Stage B outputs when testing enrichment effects or preparing enrichment-backed indexing experiments.
3. **Keep A+B substrate fixed while tuning retrieval knobs.**
   - Change retrieval configuration first (dense/hybrid, enrichment profile, co-retrieval expansion) before paying Stage A' runtime.

### Retrieval benchmarking

1. **Canonical protocol: embed-only, then eval-only with the same run-id.**
2. **Use corpus-compatible run-id only (fingerprint guardrail).**
3. **Use canonical S&W naming/paths in commands and docs:**
   - benchmark path: `evals/retrieval/SwordsandWizardry/...`
   - corpus output path (Complete Revised): `out/Swords&Wizardry/SW_Complete_Revised/SW Complete Revised PDF`
   - `SwordsandWizardy` is legacy typo only.

## Canonical Workflow References

- **Ingestion best practices:** [Docs/Workflows/WORKFLOW-Ingestion-Best-Practices.md](Docs/Workflows/WORKFLOW-Ingestion-Best-Practices.md)
- **Retrieval best practices:** [Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md](Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md)
- **Retrieval benchmark curation:** [Docs/Workflows/WORKFLOW-RetrievalBenchmark-ManualCuration.md](Docs/Workflows/WORKFLOW-RetrievalBenchmark-ManualCuration.md)

## Fast Command Reference

Run from `RulesIngestion` root.

### Setup

```bash
uv sync
uv run pytest tests/ -v
```

### Ingestion: full book (recommended default)

```bash
uv run python scripts/run_mark3_full_pdf.py \
  --pdf <PDF_PATH> \
  --out-dir <OUT_DIR> \
  --stage ab
```

### Ingestion: run Stage A' later on existing substrate

```bash
export OPENAI_API_KEY=<YOUR_KEY>
uv run python scripts/run_stage_a_prime.py \
  --substrate-dir <SUBSTRATE_DIR> \
  --book-id <BOOK_ID>
```

### Retrieval Lab: embed-only then eval-only

```bash
uv run python -m retrieval_lab.run_experiment \
  --config <HYBRID_OR_DENSE_CONFIG> \
  --models <MODEL_ID> \
  --recipe-mode <standardized|recommended> \
  --experiment-name <EXP_NAME> \
  --embed-only \
  --seed 42
```

```bash
uv run python -m retrieval_lab.run_experiment \
  --config <HYBRID_OR_DENSE_CONFIG> \
  --models <MODEL_ID> \
  --recipe-mode <standardized|recommended> \
  --run-id <RUN_ID_FROM_EMBED_STEP> \
  --batches <BENCHMARK_JSON> \
  --experiment-name <EXP_NAME> \
  --seed 42
```

## CI

Schema validation, determinism replay, and instrumentation tests run on push/PR when `RulesIngestion/**` changes (see `.github/workflows/rules-ingestion-tests.yml` at repo root).

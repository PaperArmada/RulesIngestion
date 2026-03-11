# RulesIngestion

Deterministic rulebook ingestion and retrieval-evaluation pipeline.

**Start here:** [Docs/Design/README.md](Docs/Design/README.md)

- **Stage A:** extraction + prose reconstruction (`SurfaceAST`).
- **Stage B:** evidence binding (`EvidenceUnits`).
- **Stage A':** optional retrieval-only enrichment over Stage B units.
- **Retrieval Lab:** embed/eval over Stage B substrate, with corpus-specific benchmark projections and contract-validated run artifacts.

Canonical design lives in `Docs/Design/v1/`. Historical design notes remain in
`Docs/Design/` and superseded design docs live in `Docs/Design/archive/`.

See [Docs/Design/v1/baseline_manifest.md](Docs/Design/v1/baseline_manifest.md) for reproducibility, [Docs/Design/v1/retrieval_lab_v1.md](Docs/Design/v1/retrieval_lab_v1.md) for retrieval-lab architecture, and [Docs/Design/gold_resolution_design.md](Docs/Design/gold_resolution_design.md) for the benchmark definition/projection lifecycle.

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
2. **Benchmarks are now contract-bound to one exact corpus.**
   - Treat the human-maintained benchmark file as the benchmark definition.
   - Treat the scored benchmark artifact as a benchmark projection tied to one exact corpus identity.
   - Do not assume one benchmark file is valid across changed chunk topology.
3. **Use corpus-compatible run-id only (shape + content guardrail).**
   - Eval-only now validates both `corpus_fingerprint` and `corpus_content_fingerprint`.
   - Benchmark validation also checks the active `corpus_index.json` hash and benchmark surface.
4. **Use canonical S&W naming/paths in commands and docs:**
   - benchmark path: `evals/retrieval/SwordsandWizardry/...`
   - corpus output path (Complete Revised): `out/Swords&Wizardry/SW_Complete_Revised/SW Complete Revised PDF`
   - `SwordsandWizardy` is legacy typo only.

### Retrieval run artifacts

Every experiment run should now be treated as an auditable contract bundle, not just a metrics directory.

- `embeddings/corpus_index.json` records exact corpus identity and corpus recipe.
- `benchmark_contract_validation.json` records whether input benchmark contracts matched the active corpus.
- `benchmark.<surface>.json` records the benchmark projection actually scored for a surface.
- `benchmark.<surface>.contract.json` records the projection contract for that exact surface.
- `manifest.json` / `run_manifest.json` snapshot definition inputs, projection snapshots, corpus index, and prod-readiness artifacts.
- `prod_readiness.json` is the explicit promotion artifact for "what should ship?" and must only exist for a contract-valid run.

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

After eval, inspect at minimum:

- `benchmark_contract_validation.json`
- `embeddings/corpus_index.json`
- `manifest.json`
- `prod_readiness.json` when evaluating a promotion candidate

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

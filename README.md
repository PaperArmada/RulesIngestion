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
- **Retrieval results timeline/reference:** [Docs/Reports/REFERENCE-Retrieval-Benchmark-Results-Timeline.md](Docs/Reports/REFERENCE-Retrieval-Benchmark-Results-Timeline.md)
- **Desktop-to-laptop migration:** [Docs/Workflows/WORKFLOW-Desktop-to-Laptop-Migration.md](Docs/Workflows/WORKFLOW-Desktop-to-Laptop-Migration.md)

## Retrieval benchmark catalog (audited)

**Updated at:** 2026-03-24

This section is an index snapshot of currently checked-in retrieval benchmark definitions.
Canonical benchmark policy and rationale remain in
`Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md`.

### Canonical recommendation benchmarks (with rationale)

| Corpus | Benchmark | Primary use | Reasoning |
|---|---|---|---|
| Starfinder | `evals/retrieval/StarFinderPlayerCore/starfinder_player_core_atomic_rules_benchmark.json` | Fast structural regression checks | Atomic queries are narrow and expose ranking regressions quickly. |
| Starfinder | `evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json` | Main quality gate for recommendation decisions | Balanced breadth and runtime; large enough to avoid overfitting to tiny sets. |
| S&W | `evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_benchmark.json` | Main quality gate for recommendation decisions | Canonical revised benchmark with curated anchors and harder retrieval coverage. |

### Additional benchmark suites currently present

Use these intentionally for their specific evaluation surfaces (atomic, 50q,
multihop working-set, microbundle, and vertical-slice diagnostics).

- `evals/retrieval/PHB5e/`
- `evals/retrieval/Pathfinder2ePlayerCore/`
- `evals/retrieval/ShadowRun4e/`
- `evals/retrieval/SwordsandWizardry/` (includes alternate/reanchored variants)
- `evals/retrieval/StarFinderPlayerCore/` (includes mapping/recommendation support files)

### Audit note

The canonical table in `WORKFLOW-Retrieval-Best-Practices.md` is still correct for
recommendation-grade defaults (Starfinder + S&W). The repository also contains
expanded corpus-specific benchmarks used for diagnostics and targeted experiments.

## Retrieval results quick reference (audited)

**Updated at:** 2026-03-24

Source of truth:
`Docs/Reports/REFERENCE-Retrieval-Benchmark-Results-Timeline.md`
and `Docs/Reports/REPORT-2026-03-13-Full-Benchmark-Sweep-Atomic-and-Benchmark.md`.
Metric naming glossary:
`Docs/Reports/REFERENCE-Retrieval-Benchmark-Results-Timeline.md` (`Metric glossary (canonical naming)`).

| Corpus | Atomic benchmark (queries) | Main benchmark (queries) | Atomic clean subset (2026-03-13) | Benchmark clean subset (2026-03-13) | Current read |
|---|---|---|---|---|---|
| PHB5e | `evals/retrieval/PHB5e/dnd_5e_2024_atomic_rules_benchmark.v2_merged2000_min200.json` (19) | `evals/retrieval/PHB5e/dnd_5e_2024_rules_50q_benchmark.json` (50) | `19/19` clean, `MRR=0.4867` | `37/50` clean, `MRR=0.5875` (full `MRR=0.4447`) | Atomic is ratified; broad benchmark still has notable working-set debt. |
| PF2e | `evals/retrieval/Pathfinder2ePlayerCore/pathfinder2e_player_core_atomic_rules_benchmark.json` (19) | `evals/retrieval/Pathfinder2ePlayerCore/pathfinder2e_player_core_50q_benchmark.json` (50) | `17/19` clean, `MRR=0.5647` | `50/50` clean, `MRR=0.8254` | Broad benchmark is fully clean and strong; atomic is near-clean. |
| SR4 | `evals/retrieval/ShadowRun4e/shadowrun4e_anniversary_atomic_rules_benchmark.json` (19) | `evals/retrieval/ShadowRun4e/benchmark_shadowrun_sr4_retrieval.json` (50) | `18/19` clean, `MRR=0.6184` | `50/50` clean, `MRR=0.5597` | Broad benchmark is fully clean; atomic has small remaining debt. |
| Starfinder | `evals/retrieval/StarFinderPlayerCore/starfinder_player_core_atomic_rules_benchmark.json` (19) | `evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json` (50) | `10/19` clean, `MRR=0.6333` (full `MRR=0.3333`) | `50/50` clean, `MRR=0.6162` | Biggest atomic debt tail; broad benchmark is fully clean. |
| SWCR | `evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_atomic_rules_benchmark.v3_swcr_merged2000_min100.json` (19) | `evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_benchmark.json` (21) | `18/19` clean, `MRR=0.5565` | `21/21` clean, `MRR=0.2868` | Broad benchmark is clean but weak, indicating true retrieval difficulty. |

Use `clean_subset` as the default headline for recommendation decisions; treat
`full_working_set` primarily as debt diagnostics where clean/full diverge.

### Report index metrics snapshot

For the full metrics-informed learning map, see:
`Docs/Reports/REFERENCE-Retrieval-Benchmark-Results-Timeline.md`.

| Report | Benchmark use | Retrieval metric signals | Decision read | When |
|---|---|---|---|---|
| `REPORT-Embedding-Bakeoff-Comprehensive-2026-03-04.md` | Embedding baseline selection on Starfinder 50q and SWCR broad benchmark | `MRR`: best Starfinder dense `pplx=0.6921`; `Recall@10`: best `all-mpnet=0.8467`; `Gold-in-Candidates`: `1.0000` (all-mpnet) | Baseline policy should balance robustness and coverage, not only peak MRR. | 2026-03-04 |
| `REPORT-Hybrid-Bakeoff-2026-03-05-Full.md` | Full hybrid bakeoff for fusion-default selection | Run health: `300/300` clean; avg `MRR` delta vs dense: RRF `Starfinder -0.018`, `SWCR -0.095`; CC `Starfinder +0.016`, `SWCR -0.006` | Keep Convex Combination (CC) as canonical fusion default; retire Reciprocal Rank Fusion (RRF) default behavior. | 2026-03-05 |
| `REPORT-2026-03-13-Full-Benchmark-Sweep-Atomic-and-Benchmark.md` | Hardened dense sweep across active atomic and broad benchmark families | Clean-family `MRR`: Atomic `0.5719`, Benchmark `0.5751`; reliability: all 10 successful reruns contract-valid/promotion-ready | Use `clean_subset` as canonical scoreboard and `full_working_set` for debt diagnostics. | 2026-03-13 |
| `REPORT-SWCR-Retrieval-Deep-Dive-2026-03-17.md` | SWCR broad benchmark diagnostic | SWCR clean metrics: `MRR=0.2868`, `ReqFSH@10=0.1905`, `Gold-in-Candidates=0.8571`; hard misses `3/21` | SWCR weakness is a true retrieval-quality concern, not only benchmark debt. | 2026-03-17 |

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

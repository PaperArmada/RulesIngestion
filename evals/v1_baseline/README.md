# v1 Baseline Suite

**Purpose:** Reproducible C-first baseline runs across all books for Stage A/B v1. Substrate is Stage A + B output only. "Baseline" refers to the outputs under this directory (or a dated subdirectory), not ad-hoc older runs.

## Substrate (Stage A + B output)

All baselines use extracted corpora under **`out/`** (relative to repo root):

| Book | Document ID | Substrate path |
|------|-------------|----------------|
| D&D 5e PHB | DnD_PHB_5.5 | `out/DnD_PHB_5.5` |
| Starfinder 2e Player Core | StarFinderPlayerCore | `out/StarFinderPlayerCore` |
| Swords & Wizardry | Swords&Wizardry | `out/Swords&Wizardry` |

Ensure these directories exist and contain Stage A + B output (e.g. per-page `stageB.evidence_units.json` or merged EvidenceUnit corpus). See [Docs/Design/v1/baseline_manifest.md](../../Docs/Design/v1/baseline_manifest.md).

## Suite definition

Baseline process defaults to **C** (raw-first merge-rerank), with optional A/B comparators:

- **A:** raw-only (`merge_chunks=false`)
- **B:** merged-only (`merge_chunks=true`)
- **C (default):** raw-first merge-rerank + monotonic safeguards

## Fresh baselines (all books, end-to-end)

From **RulesIngestion** repo root, with `uv` and dependencies installed (`uv sync`):

### One-shot: run the script

```bash
./evals/v1_baseline/run_baseline_suite.sh
```

This runs hybrid retrieval (embed + eval) for all three books into `evals/v1_baseline/<YYYYMMDD>/`, using each config's canonical `substrate_version` by default so contract validation and run IDs stay aligned. Comparator modes **A/B** are optional; the ratified package should be built with **`--c-only`** so the canonical `C` corpus recipe and the benchmark contracts stay aligned.

To run only C:

```bash
uv run python -m evals.v1_baseline.run_baseline_suite \
  --out-dir evals/v1_baseline/$(date +%Y%m%d) \
  --c-only \
  --strict-integrity \
  --gating-integrity-policy strict \
  --stage-b-gate-policy strict
```

### Manual: direct suite invocation

```bash
export BASELINE_DATE=$(date +%Y%m%d)
uv run python -m evals.v1_baseline.run_baseline_suite \
  --out-dir evals/v1_baseline/$BASELINE_DATE \
  --c-only \
  --strict-integrity \
  --gating-integrity-policy strict \
  --stage-b-gate-policy strict
```

## Baseline defaults

| Corpus | Base config | Baseline mode |
|--------|-------------|---------------|
| PHB | `phb_hybrid.yaml` | **C** (`phb_hybrid_c_raw_first_merge_rerank_*`) |
| Starfinder | `starfinder_hybrid.yaml` | **C** (`starfinder_hybrid_c_raw_first_merge_rerank_*`) |
| S&W | `swords_wizardry_hybrid.yaml` | **C** (`swords_wizardry_hybrid_c_raw_first_merge_rerank_*`) |

See [Docs/Design/v1/retrieval_lab_v1.md](../../Docs/Design/v1/retrieval_lab_v1.md) for full run options, two-step (embed-only then eval), and regression policy.

## Integrity artifacts

The matrix runner emits per-config integrity artifacts:

- `integrity_<config>.json`
- `integrity_<config>.md`
- `replay_<config>.json` when you archive replay checks via `scripts/assert_corpus_replay_determinism.py`

Each run directory under `evals/v1_baseline/<STAMP>/<experiment_id>/` is expected to contain:

- `benchmark_contract_validation.json`
- `benchmark.<surface>.contract.json`
- `manifest.json`
- `run_manifest.json`
- `prod_readiness.json`
- `embeddings/corpus_index.json`

The suite root now also writes:

- `canonical_runs_index.json` as the authoritative canonical-run list
- freeze metadata in `baseline_process_summary.json`
- bundle hygiene classification for canonical members vs retained retry/history runs

Key command options:

```bash
uv run python -m evals.v1_baseline.run_baseline_suite \
  --out-dir evals/v1_baseline/$(date +%Y%m%d) \
  --version v1 \
  --strict-integrity \
  --gating-integrity-policy strict \
  --stage-b-gate-policy strict
```

The suite writes `baseline_process_summary.json` containing run IDs, key A/B/C metrics per corpus, freeze metadata, and bundle hygiene classification. Canonical consumers should prefer `canonical_runs_index.json` and each run's `prod_readiness.json` over directory-name conventions.

## Expansion -> gating promotion checklist

A candidate expansion batch is promotable only when all checks pass:

1. Integrity checks pass in strict mode on the promoted subset.
2. Required-set metrics are stable or improved on gating suite:
   - RequiredFullSetHit@10 non-regressing beyond accepted tolerance.
   - Rank-of-last-required mean not materially worse without compensating coverage gain.
3. Failure-bucket classifier does not indicate unacceptable regressions for protected tiers.
4. Reproduction on another machine yields matching integrity status and near-identical metrics.

# Workflow: Desktop-to-Laptop Migration

This workflow is the canonical `RulesIngestion` runbook for moving active work
from one machine to another without losing reproducibility.

Goal: review the current repo state, commit the tracked source of truth, then
inventory ignored local artifacts so you know what must be preserved, what can
be rebuilt, and how to validate parity on the destination machine.

Design references:
- `README.md`
- `Docs/Workflows/WORKFLOW-Ingestion-Best-Practices.md`
- `Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md`
- `Docs/Design/v1/baseline_manifest.md`
- `.gitignore`

---

## 1) Core principle: commit source of truth, inventory machine-local state

Treat migration as two separate problems:

1. **Tracked reproducibility state**
   - code
   - configs
   - benchmark definitions
   - contract logic
   - workflow docs
2. **Ignored machine-local state**
   - corpora under `out/`
   - retrieval experiment outputs
   - baseline packages under `evals/v1_baseline/<STAMP>/`
   - local PDFs and cached assets
   - local virtualenvs and caches

Do not blur those together. The commit should make the work reproducible. The
inventory should tell you which local assets still matter.

---

## 2) When to run this workflow

Run this workflow when any of the following are true:

- you want to move active `RulesIngestion` work to another machine,
- you are about to shut down or repurpose the current desktop,
- you have produced new retrieval runs, baseline bundles, or corpora that are
  not tracked by git,
- you want a clean checkpoint before continuing work elsewhere.

Run all commands from `RulesIngestion` root unless noted otherwise.

---

## 3) Step 1: review current repo state

Review the nested `RulesIngestion` repo directly, not the parent monorepo.

### 3.1 Working tree review

```bash
git status --short
git diff --stat
git diff
```

Classify the current tracked changes before you commit:

- ingestion logic changes
- retrieval or evaluation logic changes
- benchmark definition changes
- workflow or design doc changes
- baseline or ratification logic changes

### 3.2 Ignored state review

```bash
git status --short --ignored
```

Use that output to identify local artifacts that are not part of the commit but
may matter for migration:

- `out/`
- `evals/v1_baseline/<STAMP>/`
- `manifests/*.json`
- local PDFs and images
- `.venv/` and caches

### 3.3 Current desktop validation snapshot

This workflow was validated against the current desktop state on `2026-03-14`.
Observed examples included:

- a large tracked worktree in progress in the nested `RulesIngestion` repo,
- `out/` present and approximately `22G`,
- `evals/v1_baseline` present and approximately `490M`,
- `evals/extraction/brutal_pages` present and approximately `186M`,
- `.venv/` present and approximately `7.4G`,
- live retrieval experiment bundles under `out/retrieval_lab/experiments/`,
- local PDFs under `evals/extraction/brutal_pages/`,
- ignored baseline ratification bundles under `evals/v1_baseline/20260313_ratification/`.

That means this repo currently has meaningful machine-local state and should not
be migrated by git commit alone.

---

## 4) Step 2: pre-commit reproducibility gate

Before committing, verify enough to prove the tracked changes are meaningful and
re-runnable on the laptop.

### 4.1 Minimum gate for all migrations

```bash
uv sync
uv run pytest tests/ -v
```

If the full test suite is too expensive for a mid-iteration checkpoint, use a
focused gate only when you can justify the narrower scope in the commit notes:

- changed extraction code -> run the relevant `tests/extraction/` tests
- changed retrieval code -> run the relevant `tests/retrieval_lab/` tests
- changed baseline logic -> run the affected `tests/evals/` tests

### 4.2 Benchmark and contract gate

Run these when benchmark definitions, benchmark schemas, or retrieval configs
changed in ways that affect scored runs:

```bash
uv run python -m retrieval_lab.benchmark_lint <BENCHMARK_PATH>
```

If you changed tracked benchmark definitions or contracts, also refresh tracked
contract hashes where appropriate:

```bash
uv run python scripts/refresh_benchmark_contract_hashes.py --benchmarks <BENCHMARK_JSON...>
```

### 4.3 Baseline and replay gate

Run these when your tracked changes affect corpus identity, replay
determinism, baseline ratification, or package integrity:

```bash
uv run python scripts/assert_corpus_replay_determinism.py \
  --config <CONFIG> \
  --out <REPORT.json>
```

```bash
uv run python -m evals.v1_baseline.run_baseline_suite \
  --out-dir "evals/v1_baseline/<STAMP>" \
  --c-only \
  --strict-integrity \
  --gating-integrity-policy strict \
  --stage-b-gate-policy strict
```

Only run the baseline suite when the change actually warrants regenerating an
archival package. Do not create a fresh ignored baseline bundle for every small
code edit.

### 4.4 Commit message discipline

The commit should answer the laptop reproducibility question:

`Can the destination machine reproduce the current state from tracked files plus documented local assets?`

Include the relevant context in the commit body or adjacent notes:

- active corpus or substrate path
- benchmark surface
- config file(s)
- whether existing desktop-only outputs are contract-valid, draft, or known-mismatch

---

## 5) Step 3: commit only tracked source-of-truth changes

Commit:

- code under `extraction/`, `retrieval_lab/`, `scripts/`, `tests/`
- tracked benchmark definitions under `evals/retrieval/`
- tracked workflow or design docs
- tracked baseline logic and integrity checks
- `pyproject.toml` and `uv.lock` when dependencies changed

Do not commit:

- `out/`
- `out/retrieval_lab/experiments/`
- ignored baseline outputs under `evals/v1_baseline/<STAMP>/`
- local manifests with machine-specific absolute paths under `manifests/*.json`
- ignored PDFs, images, archives, or caches
- `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `.qe_cache/`, `__pycache__/`

Special caution:

- `manifest.json` and `run_manifest.json` inside ignored experiment directories
  often include absolute desktop paths. Preserve them for provenance if needed,
  but do not treat them as portable source-of-truth files.

### 5.1 Push the tracked commit

Do not stop at a local commit. If the laptop will pull from git, you must push
the tracked source-of-truth commit to the remote before leaving the desktop.

Minimum command:

```bash
git push
```

If the branch does not yet track a remote branch:

```bash
git push -u origin HEAD
```

Explicit reminder:

- a local-only commit is not a migration checkpoint,
- the laptop cannot rely on your tracked source of truth until the commit is on
  the remote,
- push before you begin copying ignored artifacts unless you intentionally want
  the laptop bootstrap to depend on manual patch transfer instead of git.

---

## 6) Step 4: inventory ignored artifacts before migration

After the tracked commit is ready, inventory the ignored state deliberately.

### 6.1 Fast inventory commands

```bash
git status --short --ignored
```

```bash
du -sh out evals/v1_baseline evals/extraction/brutal_pages .venv .qe_cache .ruff_cache .pytest_cache 2>/dev/null
```

### 6.2 What to record

For every ignored asset you care about, record:

- path
- why it matters
- size
- whether it is portable across machines
- whether it is required for provenance, useful for speed, or safe to regenerate

### 6.3 Classification rubric

| Class | Examples | Migration action |
|---|---|---|
| **Must preserve for provenance** | `benchmark_contract_validation.json`, `manifest.json`, `run_manifest.json`, `embeddings/corpus_index.json`, `prod_readiness.json`, `baseline_process_summary.json`, `canonical_runs_index.json`, local source PDFs that cannot be reacquired | Keep or archive if the run/package matters historically or must be audited later |
| **High cost but reproducible** | `out/<corpus>/`, `embeddings/*_corpus.npy`, large retrieval experiment directories, ratification bundles under `evals/v1_baseline/<STAMP>/` | Copy only if you want to save time; otherwise rebuild from tracked code/config plus preserved inputs |
| **Safe to regenerate** | `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `.qe_cache/`, `__pycache__/`, temporary reports, local scratch outputs | Do not migrate unless there is a specific reason |

### 6.4 Rules for common artifact families

#### A. Stage A/B substrates under `out/<corpus>/...`

- Usually expensive to rebuild.
- Copy if you want to avoid re-running ingestion immediately.
- If you skip copying them, make sure the laptop still has the source PDFs plus
  the tracked scripts/configs needed to reproduce them.

#### B. Retrieval experiment bundles under `out/retrieval_lab/experiments/...`

Preserve at minimum when a run is important:

- `manifest.json`
- `run_manifest.json`
- `benchmark_contract_validation.json`
- `embeddings/corpus_index.json`
- `prod_readiness.json` if present

The rest of the metrics bundle is usually reproducible if the substrate and
benchmark definition still exist, but can still be worth copying if the run was
expensive or if you need exact historical comparison artifacts.

#### C. Baseline packages under `evals/v1_baseline/<STAMP>/`

These are ignored by design but can be recommendation-grade evidence bundles.
If a package matters, preserve the package root and its required artifacts from
`Docs/Design/v1/baseline_manifest.md`, not just a few summary files.

#### D. Local manifests under `manifests/*.json`

Review these before migration. They may contain absolute source paths that will
break on the laptop. Prefer regenerating them there unless they are needed as a
forensic record.

#### E. Local PDFs and brutal-page inputs

If a PDF or regression input file is not tracked in git and is hard to reacquire,
preserve it. On the current desktop, `evals/extraction/brutal_pages/` is an
example of such ignored inputs.

#### F. Local environment and caches

Do not migrate `.venv/` or Python caches as a default. Recreate the environment
with `uv sync` on the laptop.

---

## 7) Step 5: build a rebuild-first migration package

Default policy: preserve the minimum evidence needed to rebuild, not every byte
of local output.

Create a migration note for the current move that includes:

- current git commit SHA after the tracked commit
- list of changed tracked files that define the current behavior
- active benchmark files
- active config files
- important ignored paths that currently exist
- hashes or contract fingerprints when available
- whether each ignored asset is:
  - required for provenance
  - optional time-saver
  - safe to skip

Recommended minimum evidence for an important retrieval run:

- tracked config YAML path
- tracked benchmark JSON path
- `manifest.json`
- `run_manifest.json`
- `benchmark_contract_validation.json`
- `embeddings/corpus_index.json`
- `prod_readiness.json` when present
- note whether the run is contract-valid or intentionally diagnostic

Current desktop example:

- `out/retrieval_lab/experiments/pf2e_multihop_r2_llm_listwise_20260314_161713/`
  contains the usual provenance bundle,
- its `manifest.json` records absolute desktop paths,
- its `benchmark_contract_validation.json` is not valid because benchmark
  metadata does not yet match the active corpus contract,
- therefore this run should be preserved, if at all, as a diagnostic artifact
  rather than treated as a portable promoted result.

---

## 8) Step 6: bootstrap the laptop

On the laptop:

```bash
uv sync
uv run pytest tests/ -v
```

Then restore or rebuild only what the migration note says is needed:

- copy preserved source PDFs if required,
- copy preserved substrates if you want to avoid re-ingestion,
- copy preserved provenance bundles for important retrieval runs or baselines,
- otherwise rebuild from tracked configs and scripts.

Do not trust preserved manifests blindly if they embed the old machine's
absolute paths.

---

## 9) Step 7: parity check on the laptop

Do one representative proof, not just a blind file copy.

### 9.1 For ingestion-heavy work

Re-run one representative ingestion command and confirm expected outputs exist:

- `run_summary.json`
- `evaluation_report.json`
- per-page `stageB.evidence_units.json`

### 9.2 For retrieval-heavy work

Re-run one representative retrieval step and compare:

- `manifest.json`
- `run_manifest.json`
- `benchmark_contract_validation.json`
- `embeddings/corpus_index.json`

Focus on these questions:

- does the same tracked config still run,
- does the benchmark contract validate,
- do corpus fingerprints or content fingerprints match when expected,
- does the laptop produce the same class of artifact bundle as the desktop.

If the laptop can do that, the migration worked.

---

## 10) Minimal automation follow-up

Start manually with this workflow. After it proves useful, automate only the
inventory/report pieces.

The first helper script should do three things:

1. summarize tracked vs ignored state for the nested repo,
2. report sizes for high-cost ignored directories,
3. detect provenance-critical files inside ignored experiment or baseline trees
   and emit a small Markdown or JSON report.

Suggested future output fields:

- current git SHA
- tracked file counts by category
- ignored directory sizes
- detected experiment bundles
- detected baseline bundles
- detected source PDFs
- recommended classification per path

Do not automate the final preservation decision until the manual workflow has
been used a few times and the categories feel stable.

---

## 11) Definition of done for a machine move

The migration is complete only when all of the following are true:

1. tracked source-of-truth changes are committed,
2. important ignored assets have been classified,
3. provenance-critical artifacts have either been preserved or intentionally
   dropped,
4. the laptop environment has been recreated with `uv`,
5. one representative ingestion or retrieval parity check has passed.

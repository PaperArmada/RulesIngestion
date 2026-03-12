# Workflow: Ingestion Best Practices

This workflow is the canonical ingestion runbook for current Mark III usage.

Goal: produce stable Stage B substrates quickly for retrieval tuning, and run Stage A' only when it is actually needed.

Design references:
- `Docs/Design/README.md` for doc taxonomy and current canonical entrypoints
- `Docs/Design/v1/architecture_overview.md`
- `Docs/Design/v1/stage_a_contract.md`
- `Docs/Design/v1/stage_b_contract.md`

---

## 1) Decision rule: `A+B` first, `A'` second

Use this default unless you explicitly need enrichment artifacts immediately.

| Situation | Recommended path |
|---|---|
| Tuning dense/hybrid retrieval configs | Run `A+B` only (`--stage ab`) |
| Running retrieval matrix on embedding/co-retrieval knobs | Run `A+B` only first |
| Evaluating A'-driven retrieval behavior | Run `A+B`, then Stage A' as separate pass |
| Building a fully enriched substrate for downstream indexing | Run `A+B`, then Stage A' |

Why: Stage A' is materially slower and usually not required to improve baseline hybrid tuning loops.

---

## 2) Canonical naming and paths

- Use `SwordsandWizardry` for benchmark naming in files and configs.
- Treat `SwordsandWizardy` as legacy typo only.
- Use `out/Swords&Wizardry` as canonical S&W corpus output path.

---

## 3) Canonical workflows

Run all commands from `RulesIngestion` root.

### 3.1 Single-page debugging (fast)

Stage A only:

```bash
uv run python scripts/run_mark3_sample.py \
  --pdf <PDF_PATH> \
  --page <PAGE_INDEX> \
  --stage a \
  --out-dir out/mark3_sample
```

Stage A+B:

```bash
uv run python scripts/run_mark3_sample.py \
  --pdf <PDF_PATH> \
  --page <PAGE_INDEX> \
  --stage ab \
  --out-dir out/mark3_sample
```

### 3.2 Full-book ingestion for retrieval tuning (default)

```bash
uv run python scripts/run_mark3_full_pdf.py \
  --pdf <PDF_PATH> \
  --out-dir <OUT_DIR> \
  --stage ab \
  --dpi 200
```

`scripts/run_mark3_full_pdf.py` defaults to `--stage ab` so the common tuning path
is explicit even without an override.

Expected outputs include per-page Stage A/B artifacts plus:
- `run_summary.json`
- `evaluation_report.json`
- `EVALUATION_REPORT.md`

### 3.3 Optional queue runner (multi-book)

```bash
bash scripts/run_mark3_overnight_queue.sh \
  --out-root out/mark3_overnight \
  --dpi 200 \
  --stage ab
```

### 3.4 Stage A' as separate second pass (when needed)

Set API key first:

```bash
export OPENAI_API_KEY=<YOUR_KEY>
```

Run on one page dir:

```bash
uv run python scripts/run_stage_a_prime.py \
  --page-dir <PAGE_DIR> \
  --book-id <BOOK_ID>
```

Run on an entire Stage B substrate:

```bash
uv run python scripts/run_stage_a_prime.py \
  --substrate-dir <SUBSTRATE_DIR> \
  --book-id <BOOK_ID> \
  --concurrency 10
```

---

## 4) Retrieval handoff after ingestion

For retrieval benchmarking:
1. Keep the Stage B substrate fixed while tuning retrieval knobs.
2. Lock the retrieval chunk recipe before embedding. Canonical default: `min_chars=200`, `merge_chunks=true`, `merge_max_chars=2000` unless a corpus-specific workflow says otherwise.
3. Use `embed-only` then `eval-only` with matching `run_id`, and treat any chunk-recipe change as requiring a fresh embed step.
4. Only include A'-dependent retrieval settings after A' artifacts exist (or explicitly use runtime fallback flags where supported).

---

## 5) Verification checklist

Before declaring an ingestion run complete:

- `evaluation_report.json` exists at corpus root output.
- Per-page `stageB.evidence_units.json` files exist.
- Gate failures are reviewed in `EVALUATION_REPORT.md` before retrieval benchmarking.
- Path naming follows canonical conventions (no new `SwordsandWizardy` references).


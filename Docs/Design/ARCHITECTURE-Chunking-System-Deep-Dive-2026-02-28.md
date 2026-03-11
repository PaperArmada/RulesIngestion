# Chunking System Deep Dive (Regression + Baseline Hardening)

**Date:** 2026-02-28  
**Scope:** `RulesIngestion` retrieval corpus construction and retrieval-time chunk shaping  
**Primary benchmark:** `evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json`
**Status:** Historical deep-dive retained as an implementation record. Current
canonical retrieval policy lives in `Docs/Design/v1/` and
`Docs/Workflows/WORKFLOW-Retrieval-Best-Practices.md`.

---

## 1) Executive Findings

- The regression was caused by running Starfinder 50Q with **raw corpus shaping** (no `min_chars`, no `merge_chunks`, no `merge_max_chars`) while using eval-only `--run-id` tied to a raw embedding corpus.
- Chunk shaping controls were present in code but **not enforced by config defaults** and **not protected by a chunk-quality gate**.
- Raw run top-20 quality was severely degraded by micro-chunks and duplicates:
  - `len <= 40`: `190/1000`
  - `len <= 80`: `348/1000`
  - duplicate-text groups within query top-20: `36`
- Baseline chunk shaping (`min_chars=200 + merge_chunks + merge_max_chars=2000`) reduces this to:
  - `len <= 40`: `0/1000`
  - `len <= 80`: `0/1000`
  - duplicate-text groups: `0`
- The specific robot-as-creature bridge evidence is still missing from `blind_001_04` top-20 even after baseline chunk shaping; this remains a retrieval/grounding gap, not a chunk-shape gate issue.

---

## 2) Architecture: How Chunking Actually Works

## 2.1 Pipeline Stages

1. **Extraction Stage B emits atomic units** into per-page `stageB.evidence_units.json`.
2. `load_evidence_units()` loads all units with no size filtering.
3. Optional fold step:
   - `fold_under_threshold_into_adjacent(corpus, min_chars)`
   - folds short units into adjacent same-page context.
4. Optional heading merge step:
   - `merge_units_by_heading(corpus, max_chars)`
   - merges consecutive units sharing `(page, structural_path)`.
5. Retrieval and scoring operate over that final corpus.

## 2.2 Critical Technical Behaviors

- Empty `structural_path` units are intentionally keyed as unique in heading merge and therefore **never merged** by heading ancestry.
- Deterministic merged IDs are generated from SHA-256 over source unit IDs.
- Eval-only mode (`--run-id`) requires corpus IDs to match the embedding index for that run ID.

---

## 3) Control Points (Code-Level)

- CLI flags are parsed in `retrieval_lab/orchestration/cli_parser.py`.
- CLI overrides map into config in `retrieval_lab/orchestration/cli.py`.
- Effective flags are read by `read_run_flags()` in `retrieval_lab/orchestration/config_access.py`.
- Corpus shaping is applied in `_prepare_experiment_corpus_context()` in `retrieval_lab/run_experiment.py`.
- The shaping functions live in `retrieval_lab/substrate_loader.py`.

---

## 4) Regression Root Cause

## 4.1 What happened

- Run `starfinder_player_core_atomic_rules_20260228_062632` was invoked with:
  - `--config retrieval_lab/experiments/dense/starfinder_atomic_rules.yaml`
  - `--batches .../starfinder_player_core_50q_benchmark.json`
  - `--run-id retrieval_lab_StarFinderPlayerCore_797c2481dc8e`
- It did **not** include:
  - `--min-chars`
  - `--merge-chunks`
  - `--merge-max-chars`

## 4.2 Why it was allowed

- `starfinder_atomic_rules.yaml` had no explicit safe chunking defaults.
- CLI defaults for merge/fold are non-enforcing unless explicitly set.
- Existing lint (`benchmark_lint`) validates gold annotation hygiene, not chunk quality.
- No pre-run chunk-quality fail-fast gate existed.

---

## 5) Comparative Diagnostics (Raw vs Baseline-Shaped)

## 5.1 Corpus shape

- Raw corpus units: `13162`
- After fold (`min_chars=200`): `3265`
- After heading merge (`merge_max_chars=2000`): `2386`

## 5.2 50Q top-20 pool quality (`50 * 20 = 1000` entries)

### Raw run (`starfinder_player_core_atomic_rules_20260228_062632`)

- `len <= 40`: `190`
- `len <= 80`: `348`
- empty structural path: `36`
- duplicate-text groups (within query top-20): `36`
- duplicate entries participating in those groups: `162`

### Baseline-shaped run (`starfinder_player_core_50q_merged_evalonly_20260228_175228`)

- `len <= 40`: `0`
- `len <= 80`: `0`
- empty structural path: `67` (can remain, but no longer tiny/duplicate dominated)
- duplicate-text groups (within query top-20): `0`

## 5.3 Focus queries (`blind_001_01..blind_001_04`)

- Raw:
  - short/noisy and duplicate budget loss observed (especially `blind_001_01` and `blind_001_03`)
- Baseline-shaped:
  - no short chunks in top-20
  - no duplicate-text budget loss in top-20 for all four focus queries

---

## 6) Remaining Gap: Robot-as-Creature Bridge Evidence

- Query: `blind_001_04`
- Keyword probes for:
  - `summon robot`
  - `you summon a creature`
  - `tech trait`
- Result:
  - not present in raw top-20
  - not present in baseline-shaped top-20

Interpretation: chunk-shape hardening materially improves quality but does not by itself guarantee this bridge retrieval. Additional retrieval or corpus-linking work is still required.

---

## 7) Hardening Changes Implemented

1. **Baseline defaults made explicit** in `retrieval_lab/experiments/dense/starfinder_atomic_rules.yaml`:
   - `min_chars: 200`
   - `merge_chunks: true`
   - `merge_max_chars: 2000`

2. **Chunk-quality pre-run gate added**:
   - Module: `retrieval_lab/chunk_quality_gate.py`
   - Config keys:
     - `chunk_quality_gate_enabled`
     - `chunk_quality_max_short_le_40_rate`
     - `chunk_quality_max_short_le_80_rate`
     - `chunk_quality_max_duplicate_text_entry_rate`
   - Gate integrated in `retrieval_lab/run_experiment.py` before retrieval work.

3. **Chunk-quality artifact emitted per run**:
   - `chunk_quality_gate.json` in experiment output directory.

4. **Unit tests added**:
   - `tests/retrieval_lab/test_chunk_quality_gate.py`

---

## 8) Operational Runbook

## 8.1 Safe Starfinder run

Use config-only baseline:

`uv run python -m retrieval_lab.run_experiment --config retrieval_lab/experiments/dense/starfinder_atomic_rules.yaml --batches evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json`

## 8.2 Explicit eval-only with known merged corpus

`uv run python -m retrieval_lab.run_experiment --config retrieval_lab/experiments/dense/starfinder_atomic_rules.yaml --batches evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json --run-id retrieval_lab_StarFinderPlayerCore_3c35ef696820 --min-chars 200 --merge-chunks --merge-max-chars 2000`

## 8.3 If gate fails

- Inspect `chunk_quality_gate.json` and top duplicate texts.
- Verify effective config/CLI flags and run ID provenance.
- Rebuild embeddings with the intended shaped corpus if run ID mismatches expected corpus IDs.

---

## 9) Known Risks and Next Steps

- Chunk-quality gate protects against gross micro/duplicate regressions but does not guarantee semantic bridge retrieval.
- Empty-`structural_path` units can still be high; consider targeted orphan policy if they become noisy again.
- For `blind_001_04` bridge retrieval, next layer should focus on retrieval strategy and entity/trait linkage, not chunk-size hygiene alone.

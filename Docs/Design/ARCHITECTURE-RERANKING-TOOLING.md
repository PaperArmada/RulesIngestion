# Architecture: Retrieval Lab Reranking Tooling

Canonical architecture reference for how LLM listwise reranking is wired, configured, executed, and interpreted in Retrieval Lab.

---

## 1. Purpose And Scope

LLM reranking is a fixed-pool reordering stage after hybrid retrieval. It does not retrieve new evidence; it reorders admitted candidates before final top-k scoring.

**Query decomposition** (optional) runs before retrieval: a single user query may be rewritten into up to N subqueries; retrieval runs per subquery and candidates are fused (e.g. reciprocal rank fusion). Decomposition is configured and evaluated separately; when enabled, reranking operates on the fused pool produced by the decomposition path. See [EXPERIMENT-Query-Decomposition.md](../Experiments/EXPERIMENT-Query-Decomposition.md) for the PHB 5e multihop experiment (E0/E6/E7) and harness integration.

This document covers:

- reranker pipeline placement in Retrieval Lab (including placement relative to optional decomposition)
- configuration and CLI contracts
- baseline delta semantics and outcome classification
- retrieval metrics interpretation
- model selection guidance for reranking and answer-eval

This document does not define Stage C graph enrichment or broad agentic retrieval loops.

---

## 2. System Placement

Reranking is a retrieval-time feature within a normal experiment run. When query decomposition is enabled, it runs before retrieval; reranking then operates on the fused candidate pool.

```text
Query
 -> [Optional] Query decomposition (rewrite → subqueries; retrieve per subquery; fuse candidates)
 -> Hybrid retrieval (candidate generation, or per-subquery then fuse)
 -> Candidate admission (llm_rerank_admission_k)
 -> Candidate truncation (llm_rerank_text_char_limit)
 -> LLM listwise reorder
 -> Final top-k EvidenceUnits
 -> Retrieval scoring (+ optional answer-eval)
```

Integration points:

- Orchestration: `retrieval_lab/orchestration/dense_mode.py`
- LLM reranker implementation: `retrieval_lab/llm_reranker.py`
- CLI parsing: `retrieval_lab/orchestration/cli_parser.py`
- Report synthesis and outcome classing: `retrieval_lab/report.py`

---

## 3. Configuration Contract

### 3.1 YAML keys

Experiment YAML defines rerank defaults (example: `retrieval_lab/experiments/hybrid/pf2e_multihop_r2_sweep_working_set.yaml`):

- `llm_rerank_enabled`
- `llm_rerank_method` (`listwise`)
- `llm_rerank_model`
- `llm_rerank_admission_k`
- `llm_rerank_text_char_limit`
- `llm_rerank_prompt_template_id`
- `llm_rerank_max_output_tokens`

### 3.2 CLI overrides

CLI options in `retrieval_lab/orchestration/cli_parser.py`:

- `--llm-rerank`
- `--llm-rerank-method`
- `--llm-rerank-model`
- `--llm-rerank-admission-k`
- `--llm-rerank-text-char-limit`
- `--llm-rerank-prompt-template-id`
- `--llm-rerank-max-output-tokens`
- `--llm-rerank-cache-dir`
- `--baseline-metrics`

### 3.3 Sweep driver

- Script: `retrieval_lab/run_r2_sweep_working_set.sh`
- Config: `retrieval_lab/experiments/hybrid/pf2e_multihop_r2_sweep_working_set.yaml`
- Grid: `admission_k in {20,40,100}` x `text_char_limit in {700,900,1100}`

---

## 4. Baseline And Delta Semantics

`--baseline-metrics` is resolved by baseline loaders in `retrieval_lab/run_experiment.py`. Accepted inputs:

- run directory path, or
- surface artifact path (for example `metrics.full_working_set.json`)

When baseline is present, run outputs may contain:

- `baseline_mrr`
- `baseline_full_set_hit_at_10`
- `baseline_required_full_set_hit_at_10`
- `baseline_failure_buckets` in experiment/report context

Outcome classes in `retrieval_lab/report.py` (`_classify_outcome`):

- `coverage_gain`
- `fragment_repair_signal`
- `rank_shuffle_only`
- `no_material_change`
- `insufficient_baseline`

---

## 5. Metrics And Interpretation

Primary retrieval metrics:

- **MRR**: first-hit rank quality
- **ReqFSH@10**: complete required-evidence assembly in top 10
- **FSH@10**: complete required+supporting assembly in top 10
- **Failure buckets**:
  - `no_gold_defined`
  - `gold_not_in_candidates`
  - `gold_in_candidates_but_low_rank`
  - `grounding_or_answer_failure_after_retrieval`

Guideline:

- Use `ReqFSH@10` as the main gating signal for multihop completeness.
- Use `MRR` as a rank sharpness secondary signal.
- Use failure bucket deltas to understand why changes happened.

---

## 6. Current Empirical Readout

### 6.1 Baseline snapshot used for rerank sweep context

Baseline: `out/retrieval_lab/experiments/pf2e_multihop_r0_baseline_20260316_131844`

- `full_working_set` (70q): `MRR=0.8221`, `ReqFSH@10=0.9118`
- `clean_subset` (50q): `MRR=0.8537`, `ReqFSH@10=0.9600`

Note: working-set sweep runs are 20-query runs; baseline values above are larger-denominator references.

### 6.2 PF2E working-set reranker sweep (gpt-5.3-codex)

Surface: `full_working_set` in sweep outputs (`n=20` per successful run).

| admission_k | text_char_limit | MRR | ReqFSH@10 |
|---:|---:|---:|---:|
| 20 | 700 | 0.9500 | 0.90 |
| 20 | 900 | 0.8917 | 1.00 |
| 20 | 1100 | 0.9167 | 0.95 |
| 40 | 700 | 0.9500 | 0.85 |
| 40 | 900 | 0.8917 | 1.00 |
| 40 | 1100 | 0.9167 | 0.95 |
| 100 | 700 | 0.9500 | 0.90 |
| 100 | 900 | 0.9000 | 0.90 |
| 100 | 1100 | 0.9250 | 0.95 |

Observed tradeoff:

- `text_char_limit=900` maximizes required-evidence completeness.
- `text_char_limit=700` maximizes first-hit rank.

Default recommendation for this sweep profile:

- `llm_rerank_model=gpt-5.3-codex`
- `llm_rerank_admission_k=20`
- `llm_rerank_text_char_limit=900`

Reasoning: perfect ReqFSH@10 with the smallest admitted pool.

### 6.3 Answer-eval model comparison (same R2 setup, reasoning none, 30 queries)

Runs:

- `pf2e_multihop_r2_llm_listwise_20260316_135309` -> `gpt-5-mini`
- `pf2e_multihop_r2_llm_listwise_20260316_142003` -> `gpt-5.2-2025-12-11`
- `pf2e_multihop_r2_llm_listwise_20260316_142230` -> `gpt-5.4-2026-03-05`

| Answer-eval model | Refusal rate | Refusal accuracy | Required cited mean | Invalid cite mean |
|---|---:|---:|---:|---:|
| `gpt-5-mini` | 0.433 | 0.567 | 0.411 | 0.000 |
| `gpt-5.2-2025-12-11` | 0.100 | 0.900 | 0.711 | 0.000 |
| `gpt-5.4-2026-03-05` | 0.133 | 0.867 | 0.794 | 0.000 |

Interpretation:

- `gpt-5.2` and `gpt-5.4` materially outperform `gpt-5-mini` on refusal calibration and required evidence citation.
- `gpt-5.2` is strongest on refusal accuracy in this sample.
- `gpt-5.4` is strongest on required cited mean in this sample.

Architecture-level default:

- Keep reranker on `gpt-5.3-codex`.
- Move answer-eval default from `gpt-5-mini` to `gpt-5.2-2025-12-11` (or `gpt-5.4-2026-03-05` if citation coverage is prioritized over refusal calibration).

---

## 7. Operational Runbook

From `RulesIngestion/`:

Single run:

`uv run python -m retrieval_lab.run_experiment --config retrieval_lab/experiments/hybrid/pf2e_multihop_r2_sweep_working_set.yaml --batches evals/retrieval/Pathfinder2ePlayerCore/pathfinder2e_player_core_multihop_working_set_benchmark.json --llm-rerank --llm-rerank-model gpt-5.3-codex --llm-rerank-admission-k 20 --llm-rerank-text-char-limit 900`

Sweep:

`./retrieval_lab/run_r2_sweep_working_set.sh`

Sweep with baseline:

`./retrieval_lab/run_r2_sweep_working_set.sh --baseline-metrics out/retrieval_lab/experiments/pf2e_multihop_r0_baseline_20260316_131844`

Run outputs:

- `out/retrieval_lab/experiments/<experiment_id>/`
- key artifacts: `experiment.json`, `run_manifest.json`, `metrics.<surface>.json`, `per_query.<surface>.json`, `REPORT.<surface>.md`, `REPORT.md`

---

## 8. Risks And Guardrails

- Avoid cross-surface comparisons unless denominators and contracts match.
- Treat `clean_subset` placeholders in working-set-only runs as non-comparable artifacts when `n` is empty.
- Track outcome class plus metrics deltas; metric-only wins can hide failure-bucket regressions.
- Keep rerank and answer-eval model decisions independent; they optimize different objectives.

---

## 9. Integration best practices (post scoring-fix update)

- Keep reranking interpretation separated by failure class: first-hop admission fixes and multihop closure fixes are different interventions.
- If NextPlaid/GTE (or any late-interaction branch) is enabled, evaluate it against three surfaces in one pass: targeted slices, clean-subset, and multihop baselines.
- Require guardrail parity when adding a rescue branch before reranking: latency p95 and candidate pool size must stay within configured budgets.
- Treat small required-full-set@10 gains as valuable only when MRR and multihop baselines are not silently regressing on the primary promotion surface.
- Do not promote a rescue retriever to default multihop policy unless it beats or matches E0/E6-class baselines on combined multihop tracks.

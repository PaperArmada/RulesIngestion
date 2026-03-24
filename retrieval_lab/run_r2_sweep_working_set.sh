#!/usr/bin/env bash
# PF2E R2 reranker parameter sweep: working set only (20 queries), gpt-5.3-codex.
# Full factorial: admission_k × text_char_limit = 9 runs (max_output_tokens from config).
# Run from repo root:
#   ./retrieval_lab/run_r2_sweep_working_set.sh
#   ./retrieval_lab/run_r2_sweep_working_set.sh --baseline-metrics out/retrieval_lab/experiments/pf2e_multihop_r0_baseline_YYYYMMDD_HHMMSS/metrics.json
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

CONFIG="retrieval_lab/experiments/hybrid/pf2e_multihop_r2_sweep_working_set.yaml"
BATCH="evals/retrieval/Pathfinder2ePlayerCore/pathfinder2e_player_core_multihop_working_set_benchmark.json"
BASELINE_ARG=()
if [[ -n "${BASELINE_METRICS:-}" ]]; then
  BASELINE_ARG=(--baseline-metrics "$BASELINE_METRICS")
elif [[ "${1:-}" == "--baseline-metrics" ]] && [[ -n "${2:-}" ]]; then
  BASELINE_ARG=(--baseline-metrics "$2")
  shift 2
fi

for admission_k in 20 40 100; do
  for text_char_limit in 700 900 1100; do
    echo "--- sweep k=$admission_k char=$text_char_limit ---"
    uv run python -m retrieval_lab.run_experiment \
      --config "$CONFIG" \
      --batches "$BATCH" \
      --llm-rerank \
      --llm-rerank-model "gpt-5.3-codex" \
      --llm-rerank-admission-k "$admission_k" \
      --llm-rerank-text-char-limit "$text_char_limit" \
      "${BASELINE_ARG[@]}"
  done
done
echo "Sweep done (9 runs)."

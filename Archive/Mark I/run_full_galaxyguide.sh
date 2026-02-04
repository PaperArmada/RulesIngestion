#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_SLUG="${RUN_SLUG:-$(date +%Y-%m-%d_%H-%M-%S)}"
RULESET_DIR="$ROOT_DIR/Rules/StarFinder2e/GalaxyGuide"
RUN_DIR="$RULESET_DIR/outputs/runs/$RUN_SLUG"
REPORT_DIR="$RUN_DIR/reports/chapters-llm"
MODEL_ID="${MODEL_ID:-nomic-embed-text-v2}"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "❌ OPENAI_API_KEY is required."
  exit 1
fi

mkdir -p "$RUN_DIR" "$REPORT_DIR"

echo "🚀 Running ingestion + traversal eval (GalaxyGuide)"
uv run python ingest.py \
  --ruleset StarFinder2e \
  --ruleset-id sf2e-galaxyguide \
  --book GalaxyGuide \
  --profile full \
  --auto-config \
  --llm-pre-enrich \
  --llm-review \
  --llm-review-limit 10

echo "🧠 Running embedding + evaluation harness (GalaxyGuide)"
cd "$ROOT_DIR/../DungeonMindServer"
uv run python -m ruleslawyer.evaluation_harness \
  --queries-dir "../RulesIngestion/Rules/StarFinder2e/GalaxyGuide/outputs/runs/$RUN_SLUG/enriched" \
  --model-id "$MODEL_ID" \
  --embedding-run-id "$RUN_SLUG" \
  --reuse-embeddings \
  --chapter-summary-only \
  --chapter-summary-llm \
  --chapter-summary-output "../RulesIngestion/Rules/StarFinder2e/GalaxyGuide/outputs/runs/$RUN_SLUG/reports/chapters-llm/chapter_summaries_llm.json" \
  --chapter-summary-embed \
  --chapter-summary-embedding-output "../RulesIngestion/Rules/StarFinder2e/GalaxyGuide/outputs/runs/$RUN_SLUG/reports/chapters-llm/chapter_summary_embeddings_llm_${MODEL_ID}.json" \
  --trust-remote-code

uv run python -m ruleslawyer.evaluation_harness \
  --queries-dir "../RulesIngestion/Rules/StarFinder2e/GalaxyGuide/outputs/runs/$RUN_SLUG/enriched" \
  --chunk-source enriched \
  --best-practice-eval \
  --best-practice-boost \
  --model-id "$MODEL_ID" \
  --embedding-run-id "$RUN_SLUG" \
  --reuse-embeddings \
  --trust-remote-code \
  --report-dir "../RulesIngestion/Rules/StarFinder2e/GalaxyGuide/outputs/runs/$RUN_SLUG/reports/chapters-llm" \
  --chapter-routing-top-n 5 \
  --chapter-embedding-source summary \
  --chapter-summary-embedding-path "../RulesIngestion/Rules/StarFinder2e/GalaxyGuide/outputs/runs/$RUN_SLUG/reports/chapters-llm/chapter_summary_embeddings_llm_${MODEL_ID}.json" \
  --chapter-routing-rerank \
  --traversal-eval

echo "✅ Full GalaxyGuide pipeline complete: $RUN_DIR"

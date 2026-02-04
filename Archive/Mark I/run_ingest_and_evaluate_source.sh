#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$ROOT_DIR/../.env.development"
SOURCE_DIR="${SOURCE_DIR:-$ROOT_DIR/Rules/StarFinder2e/PlayerCore/source}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$ROOT_DIR/Rules/StarFinder2e/PlayerCore/outputs}"
RULESET_ID="${RULESET_ID:-sf2e-playercore}"
RUN_SLUG="${RUN_SLUG:-$(date +%Y-%m-%d_%H-%M-%S)}"
RUN_DIR="$OUTPUT_ROOT/runs/$RUN_SLUG"
REPORT_DIR="$RUN_DIR/reports/chapters-llm"

MODEL_ID="${MODEL_ID:-nomic-embed-text-v2}"
TOP_N="${TOP_N:-8}"
SKIP_PATTERN="${SKIP_PATTERN:-Cover|INTRO}"
EMBEDDING_RUN_ID="${EMBEDDING_RUN_ID:-$RUN_SLUG}"
EDGE_GATE_PROMPT="${EDGE_GATE_PROMPT:-0}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$ENV_FILE")
  set +a
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "❌ Source directory not found: $SOURCE_DIR"
  exit 1
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "❌ OPENAI_API_KEY is required for --auto-config and LLM enrichment."
  exit 1
fi

mkdir -p "$RUN_DIR" "$REPORT_DIR"

echo "🚀 Running ingestion + deterministic edge merge (PlayerCore)"
cd "$ROOT_DIR"
uv run python ingest.py \
  --ruleset StarFinder2e \
  --ruleset-id "$RULESET_ID" \
  --book PlayerCore \
  --profile full \
  --auto-config \
  --llm-pre-enrich \
  --llm-review \
  --llm-review-limit 10 \
  --edge-allow-gate-fail \
  $(if [[ "$EDGE_GATE_PROMPT" == "1" ]]; then echo "--edge-gate-prompt"; fi) \
  --run-slug "$RUN_SLUG" \
  --source-dir "$SOURCE_DIR" \
  --output-root "$OUTPUT_ROOT" \
  --skip-pattern "$SKIP_PATTERN"

echo "📊 Running chapter-routing evaluation (LLM summaries + embeddings)..."
cd "$ROOT_DIR/../DungeonMindServer"
uv run python -m ruleslawyer.evaluation_harness \
  --queries-dir "$RUN_DIR/enriched" \
  --model-id "$MODEL_ID" \
  --embedding-run-id "$EMBEDDING_RUN_ID" \
  --chapter-summary-only \
  --chapter-summary-llm \
  --chapter-summary-output "$REPORT_DIR/chapter_summaries_llm.json" \
  --chapter-summary-embed \
  --chapter-summary-embedding-output "$REPORT_DIR/chapter_summary_embeddings_llm_${MODEL_ID}.json" \
  --reuse-embeddings \
  --trust-remote-code

uv run python -m ruleslawyer.evaluation_harness \
  --queries-dir "$RUN_DIR/enriched" \
  --chunk-source enriched \
  --expand-gold \
  --best-practice-eval \
  --best-practice-boost \
  --model-id "$MODEL_ID" \
  --embedding-run-id "$EMBEDDING_RUN_ID" \
  --trust-remote-code \
  --report-dir "$REPORT_DIR" \
  --chapter-routing-top-n "$TOP_N" \
  --chapter-embedding-source summary \
  --chapter-summary-embedding-path "$REPORT_DIR/chapter_summary_embeddings_llm_${MODEL_ID}.json" \
  --chapter-routing-rerank \
  --traversal-eval \
  --reuse-embeddings

echo "✅ Benchmark complete."

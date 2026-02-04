#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$ROOT_DIR/../.env.development"

SOURCE_DIR="${SOURCE_DIR:-$ROOT_DIR/Rules/StarFinder2e/GMCore/source}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$ROOT_DIR/Rules/StarFinder2e/GMCore/outputs}"
RUN_SLUG="${RUN_SLUG:-$(date +%Y-%m-%d_%H-%M-%S)}"
RUN_DIR="$OUTPUT_ROOT/runs/$RUN_SLUG"
REPORT_DIR="$RUN_DIR/reports"
RULESET_ID="${RULESET_ID:-sf2e-gmcore}"
CHAPTER_TOP_N="${CHAPTER_TOP_N:-8}"

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
  echo "❌ OPENAI_API_KEY is required for --auto-config and LLM summaries."
  exit 1
fi

mkdir -p "$RUN_DIR" "$REPORT_DIR"

echo "📄 Running rules ingestion pipeline on all PDFs in $SOURCE_DIR..."
cd "$ROOT_DIR"
shopt -s nullglob
pdfs=("$SOURCE_DIR"/*.pdf)
if [[ ${#pdfs[@]} -eq 0 ]]; then
  echo "❌ No PDFs found in $SOURCE_DIR"
  exit 1
fi

for pdf_path in "${pdfs[@]}"; do
  stem="${pdf_path##*/}"
  stem="${stem%.pdf}"
  safe_stem="$(echo "$stem" | tr ' ' '-' | tr -cd 'A-Za-z0-9-')"
  doc_id="${RULESET_ID}-${safe_stem}"
  echo "➡️  Processing: $stem"
  uv run python rules_ingestion_pipeline.py "$pdf_path" \
    --output-dir "$RUN_DIR" \
    --doc-id "$doc_id" \
    --auto-config \
    --ruleset-id "$RULESET_ID" \
    --llm-pre-enrich \
    --llm-review \
    --llm-review-limit 10
done

echo "🧩 Merging enriched outputs..."
uv run python merge_enriched_outputs.py \
  --enriched-dir "$RUN_DIR/enriched" \
  --output-prefix "merged"

echo "🧠 Generating LLM chapter summaries + embeddings..."
cd "$ROOT_DIR/../DungeonMindServer"
uv run python -m ruleslawyer.evaluation_harness \
  --run-outputs-dir "$RUN_DIR/enriched" \
  --model-id nomic-embed-text-v2 \
  --chapter-summary-only \
  --chapter-summary-llm \
  --chapter-summary-llm-lengths "short=400,medium=1200,long=2400" \
  --chapter-summary-llm-embed-key "medium" \
  --chapter-summary-embed \
  --chapter-summary-output "$REPORT_DIR/chapters-llm/chapter_summaries_llm.json" \
  --chapter-summary-embedding-output "$REPORT_DIR/chapters-llm/chapter_summary_embeddings_llm.json" \
  --chapter-summary-embedding-run-id "$RUN_SLUG" \
  --trust-remote-code

echo "📊 Running expanded-only evaluation (BAAI)..."
uv run python -m ruleslawyer.evaluation_harness \
  --run-outputs-dir "$RUN_DIR/enriched" \
  --chunk-source enriched \
  --expand-gold \
  --best-practice-boost \
  --model-id bge-m3 \
  --report-dir "$REPORT_DIR/chapters-llm" \
  --chapter-routing-top-n "$CHAPTER_TOP_N" \
  --chapter-embedding-source summary \
  --chapter-summary-embedding-path "$REPORT_DIR/chapters-llm/chapter_summary_embeddings_llm.json"

echo "📊 Running expanded-only evaluation (nomic)..."
uv run python -m ruleslawyer.evaluation_harness \
  --run-outputs-dir "$RUN_DIR/enriched" \
  --chunk-source enriched \
  --expand-gold \
  --best-practice-boost \
  --model-id nomic-embed-text-v2 \
  --trust-remote-code \
  --report-dir "$REPORT_DIR/chapters-llm" \
  --chapter-routing-top-n "$CHAPTER_TOP_N" \
  --chapter-embedding-source summary \
  --chapter-summary-embedding-path "$REPORT_DIR/chapters-llm/chapter_summary_embeddings_llm.json"

echo "✅ GMCore ingestion + expanded-only evaluation complete."

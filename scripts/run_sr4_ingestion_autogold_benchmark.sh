#!/usr/bin/env bash
# ShadowRun 4e Anniversary: DeepSeek ingestion → sleep 2h → auto-gold → benchmark run.
# Run from RulesIngestion root. Uses uv for Python. Expects OPENAI_API_KEY for auto-gold.
#
# Usage:
#   cd /media/drakosfire/Projects/DungeonOverMind/RulesIngestion
#   bash scripts/run_sr4_ingestion_autogold_benchmark.sh
#
# Phase 1 runs in background; script sleeps 2 hours then runs phase 2 and 3.
# If ingestion is not finished after 2h, phase 2 will fail (substrate missing); re-run phase 2+3 manually after ingestion completes.

set -e
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PDF_PATH="${PDF_PATH:-/media/drakosfire/Projects/Rules/ShadowRun4e/CAT2600A_SR4Anniversary.pdf}"
OUT_DIR="${OUT_DIR:-out/mark3_evaluation}"
SLEEP_SEC="${SLEEP_SEC:-7200}"
CONFIG="retrieval_lab/experiments/dense/sr4_autogold_pilot.yaml"

echo "=== SR4 Anniversary pipeline ==="
echo "PDF: $PDF_PATH"
echo "Out: $OUT_DIR"
echo "Sleep after ingestion: ${SLEEP_SEC}s ($(($SLEEP_SEC / 3600))h)"
echo ""

# Phase 1: DeepSeek ingestion (full Mark III pipeline)
echo "[Phase 1] Starting DeepSeek ingestion (run_mark3_full_pdf) in background..."
uv run python scripts/run_mark3_full_pdf.py \
  --pdf "$PDF_PATH" \
  --out-dir "$OUT_DIR" \
  --stage ab \
  > out/sr4_ingestion_phase1.log 2>&1 &
PHASE1_PID=$!
echo "[Phase 1] PID=$PHASE1_PID — logging to out/sr4_ingestion_phase1.log"
echo "[Phase 1] Sleeping ${SLEEP_SEC}s ..."
sleep "$SLEEP_SEC"

# Optional: wait for phase 1 to finish if still running
if kill -0 "$PHASE1_PID" 2>/dev/null; then
  echo "[Phase 1] Process still running after sleep; waiting for completion..."
  wait "$PHASE1_PID" || true
fi
echo "[Phase 1] Done."
echo ""

# Check substrate exists
STEM="$(basename "$PDF_PATH" .pdf)"
SUBSTRATE="$OUT_DIR/$STEM"
if [[ ! -d "$SUBSTRATE" ]]; then
  echo "Error: Substrate not found at $SUBSTRATE. Ingestion may have failed or not finished. Check out/sr4_ingestion_phase1.log" >&2
  exit 1
fi
if ! ls "$SUBSTRATE/${STEM}_p0" 2>/dev/null; then
  echo "Warning: No page dir ${STEM}_p0 under $SUBSTRATE. Ingestion may be incomplete." >&2
fi

# Phase 2a: Embed only
echo "[Phase 2a] Embedding substrate..."
EMBED_LOG="out/sr4_phase2a_embed.log"
uv run python -m retrieval_lab.run_experiment \
  --config "$CONFIG" \
  --embed-only 2>&1 | tee "$EMBED_LOG" \
  || { echo "Embed failed." >&2; exit 1; }
RUN_ID="$(python - "$EMBED_LOG" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
matches = re.findall(r"run_id=([A-Za-z0-9_.:-]+)", text)
if not matches:
    raise SystemExit(1)
print(matches[-1])
PY
)"
if [[ -z "$RUN_ID" ]]; then
  echo "Embed succeeded but no run_id was found in $EMBED_LOG" >&2
  exit 1
fi
echo "[Phase 2a] Using run_id=$RUN_ID"
echo ""

# Phase 2b: Retrieval + auto-gold
echo "[Phase 2b] Retrieval + auto-gold review..."
uv run python -m retrieval_lab.run_experiment \
  --config "$CONFIG" \
  --run-id "$RUN_ID" \
  || { echo "Auto-gold run failed." >&2; exit 1; }
echo ""

# Phase 3: Benchmark run (eval-only, same run_id)
echo "[Phase 3] Benchmark run (eval)..."
uv run python -m retrieval_lab.run_experiment \
  --config "$CONFIG" \
  --run-id "$RUN_ID" \
  --experiment-name sr4_benchmark_final \
  || { echo "Benchmark run failed." >&2; exit 1; }

echo ""
echo "=== Done. Check out/retrieval_lab/experiments/ for REPORT.md and metrics. ==="

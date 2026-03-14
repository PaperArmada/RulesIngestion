#!/usr/bin/env bash
# Sequential overnight runner for Mark III full PDF ingestion.
# Stops immediately if any PDF run fails.
#
# Usage (from RulesIngestion root):
#   bash scripts/run_mark3_overnight_queue.sh
#   bash scripts/run_mark3_overnight_queue.sh --out-root out/mark3_overnight --dpi 200 --stage ab+aprime

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
RULES_ROOT="/media/drakosfire/Projects/Rules"

# Defaults can be overridden by flags below.
OUT_ROOT="out/mark3_overnight"
DPI="200"
STAGE="ab+aprime"
VERBOSE_FLAG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out-root)
      OUT_ROOT="$2"
      shift 2
      ;;
    --dpi)
      DPI="$2"
      shift 2
      ;;
    --stage)
      STAGE="$2"
      shift 2
      ;;
    --verbose|-v)
      VERBOSE_FLAG="--verbose"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

PDFS=(
  "/media/drakosfire/Projects/Rules/Pathfinder2e/PlayerCore/PathCore.pdf"
  "/media/drakosfire/Projects/Rules/StarFinder2e/GMCore/PZO22002E.pdf"
)

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="${OUT_ROOT}/queue_${TIMESTAMP}"
mkdir -p "$RUN_DIR"

echo "[queue] Mark3 overnight queue starting"
echo "[queue] run_dir=${RUN_DIR}"
echo "[queue] stage=${STAGE} dpi=${DPI}"
echo

run_one() {
  local pdf="$1"
  local stem
  local rel_from_rules
  local rel_dir
  stem="$(basename "$pdf" .pdf)"

  if [[ "$pdf" == "${RULES_ROOT}/"* ]]; then
    rel_from_rules="${pdf#${RULES_ROOT}/}"
    rel_dir="$(dirname "$rel_from_rules")"
  else
    rel_dir="unclassified"
  fi

  local out_dir="${RUN_DIR}/${rel_dir}"
  local log_path="${RUN_DIR}/${rel_dir}/${stem}.log"
  mkdir -p "$out_dir"

  if [[ ! -f "$pdf" ]]; then
    echo "[queue] ERROR: PDF not found: $pdf" | tee -a "$log_path" >&2
    return 1
  fi

  echo "[queue] >>> START ${stem}" | tee -a "$log_path"
  echo "[queue] pdf=${pdf}" | tee -a "$log_path"
  echo "[queue] out_base=${out_dir}" | tee -a "$log_path"

  set +e
  uv run python scripts/run_mark3_full_pdf.py \
    --pdf "$pdf" \
    --out-dir "$out_dir" \
    --dpi "$DPI" \
    --stage "$STAGE" \
    ${VERBOSE_FLAG} 2>&1 | tee -a "$log_path"
  local rc=${PIPESTATUS[0]}
  set -e

  if [[ $rc -ne 0 ]]; then
    echo "[queue] <<< FAIL ${stem} (exit=${rc})" | tee -a "$log_path" >&2
    return $rc
  fi

  local eval_json="${out_dir}/${stem}/evaluation_report.json"
  if [[ ! -f "$eval_json" ]]; then
    echo "[queue] <<< FAIL ${stem} (missing ${eval_json})" | tee -a "$log_path" >&2
    return 1
  fi

  echo "[queue] <<< OK ${stem}" | tee -a "$log_path"
  echo
}

for pdf in "${PDFS[@]}"; do
  run_one "$pdf"
done

echo "[queue] All queued PDFs completed successfully."
echo "[queue] Outputs: ${RUN_DIR}"

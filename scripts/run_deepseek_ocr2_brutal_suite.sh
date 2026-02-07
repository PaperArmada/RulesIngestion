#!/usr/bin/env bash
# Run the full brutal-pages suite through DeepSeek OCR 2 (one page per PDF).
# Uses .venv-deepseek-ocr2 for inference. Records per-PDF and total timing,
# writes out/deepseek_ocr2_brutal/suite_timings.json, prints book estimates.
#
# Usage (from RulesIngestion root):
#   bash scripts/run_deepseek_ocr2_brutal_suite.sh
#
# Optional: limit to first N PDFs for a quick test:
#   bash scripts/run_deepseek_ocr2_brutal_suite.sh --limit 3
#
# Expect 2–3+ minutes per page; full suite will take a long time.

set -e
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
exec python3 scripts/run_deepseek_ocr2_brutal_suite.py "$@"

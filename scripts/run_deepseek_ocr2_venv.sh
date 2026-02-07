#!/usr/bin/env bash
# Run DeepSeek OCR 2 with a dedicated venv that has transformers==4.46.3.
# The model's Hub code requires LlamaFlashAttention2 and Cache.seen_tokens (transformers 4.46).
# This repo's main env has transformers 4.57 (required by marker-pdf/surya-ocr), so we use a separate venv.
#
# Usage (from RulesIngestion root):
#   bash scripts/run_deepseek_ocr2_venv.sh --create-test-image
#   bash scripts/run_deepseek_ocr2_venv.sh --image /path/to/page.png
#   bash scripts/run_deepseek_ocr2_venv.sh --pdf /path/to/page.pdf --page 0
#
# First run will create .venv-deepseek-ocr2 and install deps (~few minutes).

set -e
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv-deepseek-ocr2"
MINIMAL_SCRIPT="${REPO_ROOT}/scripts/run_deepseek_ocr2_minimal.py"

if [[ ! -f "$MINIMAL_SCRIPT" ]]; then
  echo "Error: $MINIMAL_SCRIPT not found. Run from RulesIngestion root." >&2
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating $VENV_DIR with transformers==4.46.3..."
  uv venv "$VENV_DIR"
  # Install only what we need for the minimal script (no marker-pdf).
  uv pip install --python "$VENV_DIR/bin/python" \
    "torch" "torchvision" \
    "transformers>=4.46.0,<4.47.0" \
    "tokenizers" "pillow" "pymupdf" "einops" "addict" "easydict" "safetensors" "huggingface-hub"
  echo "Done. Installed transformers 4.46.x."
fi

exec "$VENV_DIR/bin/python" "$MINIMAL_SCRIPT" "$@"

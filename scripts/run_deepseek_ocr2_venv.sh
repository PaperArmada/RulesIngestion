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

# Python 3.12 has stable wheels for torch, transformers, tokenizers, etc.
# 3.13+ lacks prebuilt wheels for many ML packages, forcing broken sdist builds.
PYTHON_BIN="$(which python3.12 2>/dev/null || echo "")"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "python3.12 not found. Installing via uv..."
  uv python install 3.12
  PYTHON_BIN="$(uv python find 3.12)"
fi

_install_deps() {
  uv pip install --python "$VENV_DIR/bin/python" \
    "torch" "torchvision" \
    "transformers>=4.46.0,<4.47.0" \
    "tokenizers" \
    "pillow" "pymupdf" "einops" "addict" "easydict" "safetensors" "huggingface-hub"
}

# Detect if venv exists but is wrong Python version (e.g. 3.14 after OS reinstall).
if [[ -d "$VENV_DIR" ]]; then
  VENV_PYTHON_VER="$("$VENV_DIR/bin/python" --version 2>&1)"
  if [[ "$VENV_PYTHON_VER" != *"3.12"* ]]; then
    echo "DeepSeek venv is $VENV_PYTHON_VER — rebuilding with Python 3.12..."
    rm -rf "$VENV_DIR"
  fi
fi

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating $VENV_DIR with Python 3.12 + transformers==4.46.x..."
  uv venv --python "$PYTHON_BIN" "$VENV_DIR"
  _install_deps
  echo "Done. Installed transformers 4.46.x."
else
  # Venv exists and is Python 3.12; ensure core deps are present.
  if ! "$VENV_DIR/bin/python" -c "import transformers; import fitz" 2>/dev/null; then
    echo "DeepSeek venv incomplete. Reinstalling all deps..."
    _install_deps
    echo "Done."
  fi
fi

exec "$VENV_DIR/bin/python" "$MINIMAL_SCRIPT" "$@"

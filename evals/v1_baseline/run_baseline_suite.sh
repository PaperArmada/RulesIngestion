#!/usr/bin/env bash
# Run fresh v1 baselines for all books (PHB, Starfinder, S&W).
# Substrate: out/DnD_PHB_5.5, out/StarFinderPlayerCore, out/Swords&Wizardry.
# Output: evals/v1_baseline/<YYYYMMDD>/
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

BASELINE_DATE="${1:-$(date +%Y%m%d)}"
OUT_DIR="evals/v1_baseline/$BASELINE_DATE"
mkdir -p "$OUT_DIR"
echo "Output directory: $OUT_DIR"

VERSION="${2:-v1}"

uv run python -m evals.v1_baseline.run_baseline_suite \
  --out-dir "$OUT_DIR" \
  --version "$VERSION"

echo "--- Validating baseline regression envelope ---"
uv run python -m evals.v1_baseline.assert_baseline_regression --run-dir "$OUT_DIR"

echo "Done. Results in $OUT_DIR"

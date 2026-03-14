#!/usr/bin/env bash
set -euo pipefail

# Rerun only the 16 failed CC experiments from the hybrid bakeoff.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

RECIPE="${RECIPE:-standardized}"
MODELS="${MODELS:-all-mpnet-base-v2 nomic-embed-text-v2 bge-m3 pplx-embed-v1-0.6B}"
SEED=42
TS=$(date -u +%Y%m%d_%H%M%S)
BUNDLE_DIR="out/retrieval_lab/experiments/hybrid_cc_rerun_${TS}"

mkdir -p "$BUNDLE_DIR/logs"
RUNNER_LOG="$BUNDLE_DIR/runner.log"

log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$RUNNER_LOG"; }

log "=== CC-only rerun ==="
log "recipe=$RECIPE models=$MODELS"
log "bundle_dir=$BUNDLE_DIR"

declare -A TRACK_CONFIGS
TRACK_CONFIGS[starfinder]="out/StarFinderPlayerCore|StarFinderPlayerCore|v2_merged2000_min200|evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json|200|2000|baseline"
TRACK_CONFIGS[swcr]="out/Swords&Wizardry/SW_Complete_Revised/SW Complete Revised PDF|Swords&Wizardry|v3_swcr_merged2000_min100|evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_benchmark.json|100|2000|full"

batch_size_for() {
    case "$1" in
        pplx-embed-v1-0.6B) echo 1;;
        *) echo 16;;
    esac
}

run_experiment() {
    local track="$1" model="$2" variant="$3" extra_args="$4"

    IFS='|' read -r substrate doc_id sub_version benchmark min_chars merge_max enrichment <<< "${TRACK_CONFIGS[$track]}"
    local exp_name="hybridbake_${track}_${variant}_$(echo "$model" | tr '.-' '_')_${RECIPE}_${enrichment}"
    local log_file="$BUNDLE_DIR/logs/${exp_name}.log"
    local bs
    bs=$(batch_size_for "$model")

    local config_yaml
    if [ "$track" = "swcr" ]; then
        config_yaml="retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml"
    else
        config_yaml="retrieval_lab/experiments/hybrid/${track}_hybrid.yaml"
    fi

    local cmd=(
        uv run python -m retrieval_lab.run_experiment
        --config "$config_yaml"
        --experiment-name "$exp_name"
        --substrate "$substrate"
        --document-id "$doc_id"
        --substrate-version "$sub_version"
        --models "$model"
        --recipe-mode "$RECIPE"
        --recipe-fail-on-missing-source
        --embedding-enrichment-profile "$enrichment"
        --batches "$benchmark"
        --seed "$SEED"
        --batch-size "$bs"
        --min-chars "$min_chars"
        --merge-chunks
        --merge-max-chars "$merge_max"
        --trust-remote-code
        --reuse-embeddings
        $extra_args
    )

    log "START $exp_name"
    if "${cmd[@]}" > "$log_file" 2>&1; then
        log "  OK $exp_name"
    else
        log "  FAILED $exp_name (exit=$?) — see $log_file"
    fi
}

for track in starfinder swcr; do
    for model in $MODELS; do
        log "--- Track=$track Model=$model ---"
        run_experiment "$track" "$model" "hybrid_cc" "--bm25-budget 100 --dense-budget 100 --hybrid-fusion-method cc --cc-lambda 0.6 --cc-bm25-normalization atan"
        run_experiment "$track" "$model" "hybrid_cc_enriched" "--bm25-budget 100 --dense-budget 100 --hybrid-fusion-method cc --cc-lambda 0.6 --cc-bm25-normalization atan --bm25-enrichment-profile full"
    done
done

log "=== CC rerun complete. Results in $BUNDLE_DIR ==="

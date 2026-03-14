#!/usr/bin/env bash
set -euo pipefail

# Hybrid Retrieval Bakeoff — comprehensive evaluation matrix.
#
# Evaluates 5 hybrid variants × 4 embedding models × 2 recipe modes × 2 corpora.
# Reuses existing dense embeddings from the model bakeoff (no re-embedding needed).
#
# Variants tested:
#   1. hybrid_rrf         — bug-fixed RRF (Ks=100, Ku=100)
#   2. hybrid_rrf_enriched — RRF with BM25 indexing enriched text (topic_tags, etc.)
#   3. hybrid_cc          — Convex Combination fusion (lambda=0.6, atan-normalized BM25)
#   4. hybrid_cc_enriched — CC with enriched BM25 text
#   5. dense              — dense-only baseline (for comparison)
#
# Usage:
#   cd RulesIngestion
#   bash scripts/run_hybrid_bakeoff.sh [--recipe standardized|recommended] [--models "m1 m2"] [--dry-run]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

RECIPE="${RECIPE:-standardized}"
MODELS="${MODELS:-all-mpnet-base-v2 nomic-embed-text-v2 bge-m3 pplx-embed-v1-0.6B}"
DRY_RUN="${DRY_RUN:-false}"
SEED=42
TS=$(date -u +%Y%m%d_%H%M%S)
BUNDLE_DIR="out/retrieval_lab/bakeoff/hybrid_bakeoff_${TS}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --recipe) RECIPE="$2"; shift 2;;
        --models) MODELS="$2"; shift 2;;
        --dry-run) DRY_RUN=true; shift;;
        *) echo "Unknown arg: $1"; exit 1;;
    esac
done

mkdir -p "$BUNDLE_DIR/logs"
RUNNER_LOG="$BUNDLE_DIR/runner.log"

log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$RUNNER_LOG"; }

log "=== Hybrid Retrieval Bakeoff ==="
log "recipe=$RECIPE models=$MODELS dry_run=$DRY_RUN"
log "bundle_dir=$BUNDLE_DIR"

declare -A TRACK_CONFIGS
# track_name -> "substrate|document_id|substrate_version|benchmark|min_chars|merge_max_chars|enrichment"
TRACK_CONFIGS[starfinder]="out/StarFinderPlayerCore|StarFinderPlayerCore|v2_merged2000_min200|evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json|200|2000|baseline"
TRACK_CONFIGS[swcr]="out/Swords&Wizardry/SW_Complete_Revised/SW Complete Revised PDF|Swords&Wizardry|v3_swcr_merged2000_min100|evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_benchmark.json|100|2000|full"

# Batch size override for large models
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
        --output "out/retrieval_lab/bakeoff"
        $extra_args
    )

    log "START $exp_name"
    if [ "$DRY_RUN" = "true" ]; then
        log "  DRY-RUN: ${cmd[*]}"
        return 0
    fi

    if "${cmd[@]}" > "$log_file" 2>&1; then
        log "  OK $exp_name"
    else
        log "  FAILED $exp_name (exit=$?) — see $log_file"
    fi
}

for track in starfinder swcr; do
    for model in $MODELS; do
        log "--- Track=$track Model=$model Recipe=$RECIPE ---"

        # 1. Dense-only baseline
        run_experiment "$track" "$model" "dense" "--retrieval-mode dense"

        # 2. Hybrid RRF (budget-fixed)
        run_experiment "$track" "$model" "hybrid_rrf" "--bm25-budget 100 --dense-budget 100"

        # 3. Hybrid RRF + enriched BM25
        run_experiment "$track" "$model" "hybrid_rrf_enriched" "--bm25-budget 100 --dense-budget 100 --bm25-enrichment-profile full"

        # 4. Hybrid CC
        run_experiment "$track" "$model" "hybrid_cc" "--bm25-budget 100 --dense-budget 100 --hybrid-fusion-method cc --cc-lambda 0.6 --cc-bm25-normalization atan"

        # 5. Hybrid CC + enriched BM25
        run_experiment "$track" "$model" "hybrid_cc_enriched" "--bm25-budget 100 --dense-budget 100 --hybrid-fusion-method cc --cc-lambda 0.6 --cc-bm25-normalization atan --bm25-enrichment-profile full"
    done
done

log "=== Bakeoff complete. Results in $BUNDLE_DIR ==="

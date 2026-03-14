#!/usr/bin/env bash
set -euo pipefail

# Hybrid parity sweep:
# - close lab vs production normalization parity gap (atan vs minmax)
# - sweep lambda and budgets
# - compare enriched vs raw BM25 text
# - emit machine-readable summary.csv/summary.json
#
# Resume: set RESUME to an existing bundle dir (containing manifest.json) to skip
# runs already in the manifest and only run missing ones. Example:
#   RESUME=out/retrieval_lab/experiments/hybrid_parity_sweep_20260305_024350 TRACKS=swcr ./scripts/run_hybrid_parity_sweep.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

RECIPE="${RECIPE:-standardized}"
MODELS="${MODELS:-all-mpnet-base-v2 nomic-embed-text-v2 bge-m3 pplx-embed-v1-0.6B}"
TRACKS="${TRACKS:-starfinder swcr}"
NORMALIZATIONS="${NORMALIZATIONS:-minmax atan}"
LAMBDAS="${LAMBDAS:-0.6 0.7 0.8 0.9}"
BUDGETS="${BUDGETS:-100 200}"
ENRICHMENT_OPTIONS="${ENRICHMENT_OPTIONS:-none full}"
DRY_RUN="${DRY_RUN:-false}"
SMOKE_ONLY="${SMOKE_ONLY:-false}"
RESUME="${RESUME:-}"
SEED=42
TS=$(date -u +%Y%m%d_%H%M%S)
if [ -n "$RESUME" ]; then
    BUNDLE_DIR="$(cd "$RESUME" && pwd)"
    [ -f "$BUNDLE_DIR/manifest.json" ] || { echo "Resume path has no manifest.json: $BUNDLE_DIR"; exit 1; }
else
    BUNDLE_DIR="$ROOT/out/retrieval_lab/experiments/hybrid_parity_sweep_${TS}"
fi
RUNNER_LOG="$BUNDLE_DIR/runner.log"
MANIFEST_PATH="$BUNDLE_DIR/manifest.json"

mkdir -p "$BUNDLE_DIR/logs"

# When resuming, load completed run keys from manifest (track|model|variant|norm|lambda|budget|bm25_enrich)
declare -A COMPLETED_KEYS
if [ -n "$RESUME" ] && [ -f "$MANIFEST_PATH" ]; then
    while IFS= read -r k; do [ -n "$k" ] && COMPLETED_KEYS["$k"]=1; done < <(
        python3 - "$MANIFEST_PATH" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    d = json.load(f)
for r in d.get("runs", []):
    print("|".join([str(r.get(x, "")) for x in
        ("track", "model", "variant", "normalization", "lambda", "budget", "bm25_enrichment_profile")]))
PY
    )
fi

run_key() { echo "${1}|${2}|${3}|${4}|${5}|${6}|${7}"; }

log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$RUNNER_LOG"; }

declare -A TRACK_CONFIGS
# track_name -> "substrate|document_id|substrate_version|benchmark|min_chars|merge_max_chars|enrichment"
TRACK_CONFIGS[starfinder]="out/StarFinderPlayerCore|StarFinderPlayerCore|v2_merged2000_min200|evals/retrieval/StarFinderPlayerCore/starfinder_player_core_50q_benchmark.json|200|2000|baseline"
TRACK_CONFIGS[swcr]="out/Swords&Wizardry/SW_Complete_Revised/SW Complete Revised PDF|Swords&Wizardry|v3_swcr_merged2000_min100|evals/retrieval/SwordsandWizardry/swords_wizardry_complete_revised_benchmark.json|100|2000|full"

batch_size_for() {
    case "$1" in
        pplx-embed-v1-0.6B|jina-embeddings-v5-text-small|qwen3-embedding-0.6b) echo 1;;
        *) echo 16;;
    esac
}

append_manifest() {
    local record="$1"
    python3 - <<'PY' "$MANIFEST_PATH" "$record"
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
record = json.loads(sys.argv[2])
if path.exists():
    data = json.loads(path.read_text(encoding="utf-8"))
else:
    data = {"runs": []}
data.setdefault("runs", []).append(record)
path.write_text(json.dumps(data, indent=2), encoding="utf-8")
PY
}

discover_output_dir() {
    local exp_name="$1"
    ls -dt "$ROOT"/out/retrieval_lab/experiments/"${exp_name}"_* 2>/dev/null | head -1 || true
}

run_experiment() {
    local track="$1" model="$2" variant="$3" normalization="$4" lambda_val="$5" budget="$6" bm25_enrich="$7"
    local key
    key=$(run_key "$track" "$model" "$variant" "$normalization" "$lambda_val" "$budget" "$bm25_enrich")
    if [ -n "${RESUME:-}" ] && [ -n "${COMPLETED_KEYS[$key]:-}" ]; then
        log "SKIP (resume) parity_${track}_${variant}_${normalization}_l${lambda_val}_k${budget}_bm25${bm25_enrich}_$(echo "$model" | tr '.-' '_')_${RECIPE}_..."
        return 0
    fi
    IFS='|' read -r substrate doc_id sub_version benchmark min_chars merge_max enrichment <<< "${TRACK_CONFIGS[$track]}"
    local safe_model
    safe_model=$(echo "$model" | tr '.-' '_')
    local exp_name="parity_${track}_${variant}_${normalization}_l${lambda_val}_k${budget}_bm25${bm25_enrich}_${safe_model}_${RECIPE}_${enrichment}"
    local log_file="$BUNDLE_DIR/logs/${exp_name}.log"
    local bs
    bs=$(batch_size_for "$model")

    local config_yaml
    if [ "$track" = "swcr" ]; then
        config_yaml="retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml"
    else
        config_yaml="retrieval_lab/experiments/hybrid/${track}_hybrid.yaml"
    fi

    local extra_args=(
        --bm25-budget "$budget"
        --dense-budget "$budget"
        --hybrid-fusion-method cc
        --cc-lambda "$lambda_val"
        --cc-bm25-normalization "$normalization"
    )
    if [ "$bm25_enrich" = "full" ]; then
        extra_args+=(--bm25-enrichment-profile full)
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
        "${extra_args[@]}"
    )

    log "START $exp_name"
    if [ "$DRY_RUN" = "true" ]; then
        log "  DRY-RUN: ${cmd[*]}"
        return 0
    fi

    if "${cmd[@]}" > "$log_file" 2>&1; then
        local out_dir
        out_dir=$(discover_output_dir "$exp_name")
        log "  OK $exp_name"
        append_manifest "$(cat <<JSON
{"track":"$track","model":"$model","variant":"$variant","normalization":"$normalization","lambda":"$lambda_val","budget":"$budget","bm25_enrichment_profile":"$bm25_enrich","output_dir":"$out_dir"}
JSON
)"
    else
        log "  FAILED $exp_name (exit=$?) — see $log_file"
    fi
}

run_dense_baseline() {
    local track="$1" model="$2"
    local key
    key=$(run_key "$track" "$model" "dense" "" "" "" "")
    if [ -n "${RESUME:-}" ] && [ -n "${COMPLETED_KEYS[$key]:-}" ]; then
        log "SKIP (resume) parity_${track}_dense_baseline_$(echo "$model" | tr '.-' '_')_${RECIPE}_..."
        return 0
    fi
    IFS='|' read -r substrate doc_id sub_version benchmark min_chars merge_max enrichment <<< "${TRACK_CONFIGS[$track]}"
    local safe_model
    safe_model=$(echo "$model" | tr '.-' '_')
    local exp_name="parity_${track}_dense_baseline_${safe_model}_${RECIPE}_${enrichment}"
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
        --retrieval-mode dense
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
    )

    log "START $exp_name"
    if [ "$DRY_RUN" = "true" ]; then
        log "  DRY-RUN: ${cmd[*]}"
        return 0
    fi
    if "${cmd[@]}" > "$log_file" 2>&1; then
        local out_dir
        out_dir=$(discover_output_dir "$exp_name")
        log "  OK $exp_name"
        append_manifest "$(cat <<JSON
{"track":"$track","model":"$model","variant":"dense","normalization":"","lambda":"","budget":"","bm25_enrichment_profile":"","output_dir":"$out_dir"}
JSON
)"
    else
        log "  FAILED $exp_name (exit=$?) — see $log_file"
    fi
}

log "=== Hybrid Parity Sweep ==="
log "recipe=$RECIPE tracks=$TRACKS models=$MODELS dry_run=$DRY_RUN smoke_only=$SMOKE_ONLY${RESUME:+ resume=$RESUME}"
log "normalizations=$NORMALIZATIONS lambdas=$LAMBDAS budgets=$BUDGETS enrichment=$ENRICHMENT_OPTIONS"
log "bundle_dir=$BUNDLE_DIR"
if [ -z "${RESUME:-}" ]; then
    echo '{"runs":[]}' > "$MANIFEST_PATH"
fi

if [ "$SMOKE_ONLY" = "true" ]; then
    smoke_track=$(echo "$TRACKS" | awk '{print $1}')
    smoke_model=$(echo "$MODELS" | awk '{print $1}')
    smoke_norm=$(echo "$NORMALIZATIONS" | awk '{print $1}')
    smoke_lambda=$(echo "$LAMBDAS" | awk '{print $1}')
    smoke_budget=$(echo "$BUDGETS" | awk '{print $1}')
    smoke_enrich=$(echo "$ENRICHMENT_OPTIONS" | awk '{print $1}')
    log "SMOKE mode: track=$smoke_track model=$smoke_model"
    run_dense_baseline "$smoke_track" "$smoke_model"
    run_experiment "$smoke_track" "$smoke_model" "hybrid_cc" "$smoke_norm" "$smoke_lambda" "$smoke_budget" "$smoke_enrich"
else
    for track in $TRACKS; do
        for model in $MODELS; do
            log "--- Track=$track Model=$model ---"
            run_dense_baseline "$track" "$model"
            for normalization in $NORMALIZATIONS; do
                for lambda_val in $LAMBDAS; do
                    for budget in $BUDGETS; do
                        for bm25_enrich in $ENRICHMENT_OPTIONS; do
                            run_experiment "$track" "$model" "hybrid_cc" "$normalization" "$lambda_val" "$budget" "$bm25_enrich"
                        done
                    done
                done
            done
        done
    done
fi

if [ "$DRY_RUN" = "false" ]; then
    uv run python scripts/summarize_hybrid_parity.py \
        --manifest "$MANIFEST_PATH" \
        --out-csv "$BUNDLE_DIR/summary.csv" \
        --out-json "$BUNDLE_DIR/summary.json" | tee -a "$RUNNER_LOG"
    uv run python scripts/bootstrap_hybrid_ci.py \
        --manifest "$MANIFEST_PATH" \
        --track swcr \
        --samples 2000 \
        --seed 42 \
        --out-json "$BUNDLE_DIR/bootstrap_ci.json" | tee -a "$RUNNER_LOG"
fi

log "=== Hybrid parity sweep complete. Results in $BUNDLE_DIR ==="

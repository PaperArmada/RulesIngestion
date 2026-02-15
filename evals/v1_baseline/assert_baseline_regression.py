"""Assert v1 C-baseline regression envelope and safety diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Tuple


DEFAULT_THRESHOLDS = {
    "phb_hybrid_c_raw_first_merge_rerank": {"mrr_min": 0.45, "gold_in_candidates_true_ceiling_min": 0.90},
    "starfinder_hybrid_c_raw_first_merge_rerank": {"mrr_min": 0.45, "gold_in_candidates_true_ceiling_min": 0.80},
    "swords_wizardry_hybrid_c_raw_first_merge_rerank": {"mrr_min": 0.25, "gold_in_candidates_true_ceiling_min": 0.50},
}


def _load_metrics(metrics_path: Path) -> Dict:
    raw = json.loads(metrics_path.read_text(encoding="utf-8"))
    model = "all-mpnet-base-v2"
    if model not in raw:
        raise ValueError(f"{metrics_path} missing model key '{model}'")
    return raw[model]


def _find_latest_metrics(run_dir: Path, experiment_prefix: str) -> Path:
    candidates = sorted(run_dir.glob(f"{experiment_prefix}_*/metrics.json"))
    if not candidates:
        raise FileNotFoundError(f"No metrics.json found for prefix '{experiment_prefix}' under {run_dir}")
    return candidates[-1]


def _assert_thresholds(experiment: str, metrics: Dict, thresholds: Dict[str, float]) -> Tuple[bool, str]:
    mrr = float(metrics.get("mrr", 0.0))
    true_ceiling = float(metrics.get("gold_in_candidates_true_ceiling", 0.0))
    diagnostics = metrics.get("raw_merge_rerank_diagnostics", {})
    diagnostics_enabled = bool(diagnostics.get("enabled", False))
    monotonic_violations = int(diagnostics.get("monotonic_rank_violations_total", 0))
    raw_top_missing = int(diagnostics.get("raw_top_missing_in_final_topk_total", 0))

    failures = []
    if mrr < thresholds["mrr_min"]:
        failures.append(f"MRR {mrr:.4f} < {thresholds['mrr_min']:.4f}")
    if true_ceiling < thresholds["gold_in_candidates_true_ceiling_min"]:
        failures.append(
            f"True ceiling {true_ceiling:.4f} < {thresholds['gold_in_candidates_true_ceiling_min']:.4f}"
        )
    if not diagnostics_enabled:
        failures.append("raw_merge_rerank_diagnostics.enabled is false (C safety contract missing)")
    if monotonic_violations != 0:
        failures.append(f"monotonic_rank_violations_total={monotonic_violations} (expected 0)")
    if raw_top_missing != 0:
        failures.append(f"raw_top_missing_in_final_topk_total={raw_top_missing} (expected 0)")

    if failures:
        return False, f"{experiment}: " + "; ".join(failures)
    return True, (
        f"{experiment}: ok "
        f"(mrr={mrr:.4f}, true_ceiling={true_ceiling:.4f}, "
        f"monotonic_rank_violations_total={monotonic_violations}, "
        f"raw_top_missing_in_final_topk_total={raw_top_missing})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Assert v1 baseline regression thresholds.")
    parser.add_argument(
        "--run-dir",
        type=str,
        required=True,
        help="Directory containing experiment subdirectories (e.g. evals/v1_baseline/20260212)",
    )
    parser.add_argument(
        "--thresholds-json",
        type=str,
        default=None,
        help="Optional JSON file overriding default thresholds.",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    thresholds = DEFAULT_THRESHOLDS
    if args.thresholds_json:
        thresholds = json.loads(Path(args.thresholds_json).read_text(encoding="utf-8"))

    failures = []
    for experiment, exp_thresholds in thresholds.items():
        metrics_path = _find_latest_metrics(run_dir, experiment)
        metrics = _load_metrics(metrics_path)
        ok, message = _assert_thresholds(experiment, metrics, exp_thresholds)
        print(message)
        if not ok:
            failures.append(message)

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

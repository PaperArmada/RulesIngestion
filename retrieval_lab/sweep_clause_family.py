"""Run deterministic A1 clause-family sweep and summarize deltas.

Default sweep is tuned for fast signal:
- symmetric w=1, max=4
- symmetric w=2, max=4
- symmetric w=3, max=6
- forward   w=2, max=4
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from retrieval_lab.config import ExperimentConfig


DEFAULT_VARIANTS = [
    {"label": "sym_w1_m4", "window": 1, "max_units": 4, "direction": "symmetric"},
    {"label": "sym_w2_m4", "window": 2, "max_units": 4, "direction": "symmetric"},
    {"label": "sym_w3_m6", "window": 3, "max_units": 6, "direction": "symmetric"},
    {"label": "fwd_w2_m4", "window": 2, "max_units": 4, "direction": "forward"},
]


def _load_metrics(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data:
        return {}
    model_id = next(iter(data.keys()))
    return {"model_id": model_id, **data[model_id]}


def _extract_experiment_id(stdout: str) -> str:
    m = re.search(r"Done\.\s+Experiment ID:\s+([A-Za-z0-9_\-\.]+)", stdout)
    if not m:
        raise RuntimeError("Could not parse experiment id from run_experiment output.")
    return m.group(1)


def run_variant(
    base_cfg: Dict[str, Any],
    variant: Dict[str, Any],
    output_dir: Path,
    temp_cfg_dir: Path,
) -> Dict[str, Any]:
    cfg = copy.deepcopy(base_cfg)
    cfg["experiment_name"] = f"{base_cfg.get('experiment_name', 'phb_hybrid_clause_family')}_{variant['label']}"
    cfg["clause_family_projection"] = True
    cfg["clause_family_window"] = int(variant["window"])
    cfg["clause_family_max_units"] = int(variant["max_units"])
    cfg["clause_family_direction"] = str(variant["direction"])
    cfg_path = temp_cfg_dir / f"{cfg['experiment_name']}.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                f'experiment_name: "{cfg["experiment_name"]}"',
                f'substrate_path: "{cfg["substrate_path"]}"',
                f'document_id: "{cfg["document_id"]}"',
                "query_batches:",
                *[f'  - "{q}"' for q in cfg.get("query_batches", [])],
                "models:",
                *[f'  - "{m}"' for m in cfg.get("models", [])],
                f'retrieval_mode: "{cfg.get("retrieval_mode", "hybrid")}"',
                "top_k: [1, 3, 5, 10, 20]",
                "clause_family_projection: true",
                f'clause_family_window: {cfg["clause_family_window"]}',
                f'clause_family_max_units: {cfg["clause_family_max_units"]}',
                f'clause_family_direction: "{cfg["clause_family_direction"]}"',
                f'reuse_embeddings: {str(cfg.get("reuse_embeddings", True)).lower()}',
                f'trust_remote_code: {str(cfg.get("trust_remote_code", False)).lower()}',
                f'rrf_k: {int(cfg.get("rrf_k", 60))}',
                "output_dir: \"out/retrieval_lab/stage_a_and_b\"",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    cmd = [
        sys.executable,
        "-m",
        "retrieval_lab.run_experiment",
        "--config",
        str(cfg_path),
        "--output",
        str(output_dir),
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Variant {variant['label']} failed with code {proc.returncode}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    experiment_id = _extract_experiment_id(proc.stdout)
    metrics = _load_metrics(output_dir / experiment_id / "metrics.json")
    return {
        "variant": variant["label"],
        "window": variant["window"],
        "max_units": variant["max_units"],
        "direction": variant["direction"],
        "experiment_id": experiment_id,
        "metrics": metrics,
    }


def _fmt_delta(v: float) -> str:
    return f"{v:+.3f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="A1.1 clause-family sweep runner")
    parser.add_argument("--base-config", required=True, help="Base clause-family YAML path")
    parser.add_argument("--output-dir", default="out/retrieval_lab/stage_a_and_b", help="Experiment output directory")
    parser.add_argument(
        "--baseline-experiment-id",
        required=True,
        help="Baseline experiment directory name under output-dir for delta comparison",
    )
    args = parser.parse_args()

    base_cfg_path = Path(args.base_config).resolve()
    output_dir = Path(args.output_dir).resolve()
    baseline_id = args.baseline_experiment_id
    baseline_metrics_path = output_dir / baseline_id / "metrics.json"
    if not baseline_metrics_path.exists():
        raise FileNotFoundError(f"Baseline metrics not found: {baseline_metrics_path}")
    baseline = _load_metrics(baseline_metrics_path)

    # Use raw dict so we preserve runner-required keys in a compact config.
    raw = json.loads(json.dumps({}))
    # Load YAML through config then rehydrate key values required by the runner.
    cfg_obj = ExperimentConfig.from_yaml(base_cfg_path)
    raw["experiment_name"] = cfg_obj.experiment_name
    raw["substrate_path"] = cfg_obj.substrate_path
    raw["document_id"] = cfg_obj.document_id
    raw["query_batches"] = cfg_obj.query_batches
    raw["models"] = cfg_obj.models
    raw["retrieval_mode"] = cfg_obj.retrieval_mode
    raw["reuse_embeddings"] = cfg_obj.reuse_embeddings
    raw["trust_remote_code"] = cfg_obj.trust_remote_code
    raw["rrf_k"] = cfg_obj.rrf_k

    temp_cfg_dir = output_dir / "sweep_configs"
    temp_cfg_dir.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    for variant in DEFAULT_VARIANTS:
        results.append(run_variant(raw, variant, output_dir, temp_cfg_dir))

    summary_json = {
        "baseline_experiment_id": baseline_id,
        "baseline_metrics": baseline,
        "variants": results,
    }
    summary_json_path = output_dir / "a11_clause_family_sweep_summary.json"
    summary_json_path.write_text(json.dumps(summary_json, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append("# A1.1 Clause-Family Sweep Summary")
    lines.append("")
    lines.append(f"- Baseline: `{baseline_id}`")
    lines.append(f"- Baseline model: `{baseline.get('model_id', 'unknown')}`")
    lines.append(f"- Baseline MRR: {baseline.get('mrr', 0.0):.3f}")
    lines.append(f"- Baseline Recall@10: {baseline.get('recall_at_k', {}).get('10', 0.0):.3f}")
    lines.append(f"- Baseline Full-set@10: {baseline.get('full_set_hit_at_k', {}).get('10', 0.0):.3f}")
    lines.append("")
    lines.append("| Variant | Experiment ID | MRR | dMRR | R@10 | dR@10 | FSH@10 | dFSH@10 |")
    lines.append("|---------|---------------|-----|------|------|-------|--------|---------|")
    for row in results:
        m = row["metrics"]
        d_mrr = float(m.get("mrr", 0.0)) - float(baseline.get("mrr", 0.0))
        d_r10 = float(m.get("recall_at_k", {}).get("10", 0.0)) - float(baseline.get("recall_at_k", {}).get("10", 0.0))
        d_fsh10 = float(m.get("full_set_hit_at_k", {}).get("10", 0.0)) - float(
            baseline.get("full_set_hit_at_k", {}).get("10", 0.0)
        )
        lines.append(
            f"| {row['variant']} | {row['experiment_id']} | "
            f"{float(m.get('mrr', 0.0)):.3f} | {_fmt_delta(d_mrr)} | "
            f"{float(m.get('recall_at_k', {}).get('10', 0.0)):.3f} | {_fmt_delta(d_r10)} | "
            f"{float(m.get('full_set_hit_at_k', {}).get('10', 0.0)):.3f} | {_fmt_delta(d_fsh10)} |"
        )

    summary_md_path = output_dir / "a11_clause_family_sweep_summary.md"
    summary_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote: {summary_md_path}")
    print(f"Wrote: {summary_json_path}")


if __name__ == "__main__":
    main()

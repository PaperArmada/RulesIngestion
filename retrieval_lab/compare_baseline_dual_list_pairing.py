"""
Compare Baseline vs Dual-list fusion vs Dual-list + Pairing experiments.

Usage:
  uv run python -m retrieval_lab.compare_baseline_dual_list_pairing \\
    --baseline out/retrieval_lab/stage_a_and_b/phb_hybrid_20260211_212748 \\
    --dual-list out/retrieval_lab/stage_a_and_b/phb_hybrid_dual_list_fusion_<ts> \\
    --pairing out/retrieval_lab/stage_a_and_b/phb_hybrid_dual_list_fusion_plus_pairing_<ts> \\
    [--output out/retrieval_lab/stage_a_and_b/COMPARISON_BASELINE_DUAL_LIST_PAIRING.md]

Outputs: T1 regression count (vs baseline), T2 Hit@10, T2 Full-set@10, overall MRR.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from retrieval_lab.artifact_resolution import load_resolved_json_artifact


def load_per_query(exp_dir: Path, model_id: str = "all-mpnet-base-v2") -> List[Dict[str, Any]]:
    data = load_resolved_json_artifact(exp_dir, "per_query")
    if not isinstance(data, dict):
        return []
    if model_id not in data:
        return list(data.values())[0] if data else []
    return data[model_id]


def load_metrics(exp_dir: Path, model_id: str = "all-mpnet-base-v2") -> Optional[Dict[str, Any]]:
    data = load_resolved_json_artifact(exp_dir, "metrics")
    if not isinstance(data, dict):
        return None
    return data.get(model_id)


def t1_regression_count(baseline_pq: List[Dict], other_pq: List[Dict]) -> int:
    """Count T1 queries where other has strictly worse first_gold_rank than baseline."""
    by_id_b = {q["query_id"]: q for q in baseline_pq if q.get("tier") == "T1"}
    by_id_o = {q["query_id"]: q for q in other_pq if q.get("tier") == "T1"}
    regressions = 0
    for qid in sorted(by_id_b.keys()):
        b = by_id_b[qid]
        o = by_id_o.get(qid)
        if o is None:
            continue
        br = b.get("first_gold_rank")
        orank = o.get("first_gold_rank")
        # Worse: baseline had a hit (int) and other has null or higher rank
        if br is not None and orank is None:
            regressions += 1
        elif br is not None and orank is not None and orank > br:
            regressions += 1
    return regressions


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare baseline vs dual-list vs dual-list+pairing")
    parser.add_argument("--baseline", type=str, required=True, help="Path to baseline experiment dir")
    parser.add_argument("--dual-list", type=str, default="", help="Path to dual-list fusion experiment dir")
    parser.add_argument("--pairing", type=str, default="", help="Path to dual-list+pairing experiment dir")
    parser.add_argument("--output", type=str, default="", help="Write comparison markdown to this path")
    parser.add_argument("--model", type=str, default="all-mpnet-base-v2", help="Model id in metrics")
    args = parser.parse_args()

    base_dir = Path(args.baseline)
    dual_dir = Path(args.dual_list) if args.dual_list else None
    pair_dir = Path(args.pairing) if args.pairing else None
    model_id = args.model

    baseline_pq = load_per_query(base_dir, model_id)
    baseline_m = load_metrics(base_dir, model_id)
    if not baseline_pq and not baseline_m:
        print(f"Baseline dir missing or empty: {base_dir}")
        return

    rows: List[List[str]] = [
        ["Experiment", "MRR", "T1 MRR", "T1 regressions (vs baseline)", "T2 Hit@10", "T2 Full-set@10", "N grounded"],
    ]

    def add_row(name: str, exp_dir: Path) -> None:
        m = load_metrics(exp_dir, model_id)
        pq = load_per_query(exp_dir, model_id)
        if not m:
            rows.append([name, "—", "—", "—", "—", "—", "(no metrics)"])
            return
        pt = m.get("per_tier") or {}
        t1 = pt.get("T1", {})
        t2 = pt.get("T2", {})
        mrr = m.get("mrr")
        t1_mrr = t1.get("mrr")
        t2_h10 = t2.get("hit_at_k", {}).get("10")
        t2_fsh10 = t2.get("full_set_hit_at_k", {}).get("10")
        n_grounded = (t1.get("n_grounded") or 0) + (t2.get("n_grounded") or 0) + sum(
            pt.get(t, {}).get("n_grounded", 0) for t in pt if t not in ("T1", "T2")
        )
        reg = ""
        if baseline_pq and pq:
            reg = str(t1_regression_count(baseline_pq, pq))
        rows.append([
            name,
            f"{mrr:.4f}" if mrr is not None else "—",
            f"{t1_mrr:.4f}" if t1_mrr is not None else "—",
            reg,
            f"{t2_h10:.4f}" if t2_h10 is not None else "—",
            f"{t2_fsh10:.4f}" if t2_fsh10 is not None else "—",
            str(n_grounded),
        ])

    add_row("Baseline (hybrid)", base_dir)
    if dual_dir and dual_dir.exists():
        add_row("Dual-list fusion", dual_dir)
    if pair_dir and pair_dir.exists():
        add_row("Dual-list + pairing", pair_dir)

    # Print table
    col_widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    sep = " | "
    print("\n## Baseline vs Dual-list vs Dual-list+Pairing\n")
    print(sep.join(rows[0][i].ljust(col_widths[i]) for i in range(len(rows[0]))))
    print(sep.join("-" * col_widths[i] for i in range(len(rows[0]))))
    for r in rows[1:]:
        print(sep.join((r[i] or "—").ljust(col_widths[i]) for i in range(len(r))))

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        md = ["# Baseline vs Dual-list Fusion vs Dual-list+Pairing\n"]
        md.append("| " + " | ".join(rows[0]) + " |")
        md.append("| " + " | ".join("---" for _ in rows[0]) + " |")
        for r in rows[1:]:
            md.append("| " + " | ".join(r) + " |")
        md.append("")
        md.append("- **T1 regressions**: count of T1 queries where this run has strictly worse first_gold_rank than baseline.")
        md.append("- **T2 Hit@10**: fraction of T2 queries with at least one gold in top-10.")
        md.append("- **T2 Full-set@10**: fraction of T2 queries with all gold units in top-10.")
        out_path.write_text("\n".join(md), encoding="utf-8")
        print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
